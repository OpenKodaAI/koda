"""Regression tests for the runtime event resume cursor (``after_seq``).

``after_seq`` carries the global ``runtime_events.id`` of the last event a
client saw, so it grows past any page-size limit once the agent has produced
more than a thousand events. Streams and the polling endpoint must accept it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from aiohttp import WSServerHandshakeError, web
from aiohttp.test_utils import TestClient, TestServer

from koda.services.runtime.api import (
    _parse_positive_int,
    _runtime_stream_sse,
    _runtime_stream_ws,
    _runtime_task_events,
)

_INT64_MAX = 2**63 - 1


class _StubRuntimeAccessService:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def authorize(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"capability": "read"}


class _StubBroker:
    def __init__(self, events: list[dict[str, Any]]) -> None:
        self.events = events
        self.calls: list[dict[str, Any]] = []

    async def iter_events(self, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        self.calls.append(kwargs)
        after_seq = int(kwargs.get("after_seq") or 0)
        for event in self.events:
            if int(event["seq"]) > after_seq:
                yield event


class _StubStore:
    def __init__(self, events: list[dict[str, Any]]) -> None:
        self.events = events
        self.calls: list[dict[str, Any]] = []

    def list_events(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(kwargs)
        after_seq = int(kwargs.get("after_seq") or 0)
        return [event for event in self.events if int(event["seq"]) > after_seq]

    def list_task_ids_for_session(self, _session_id: str) -> list[int]:
        return [7]


_EVENTS = [
    {"seq": 1_000, "task_id": 7, "type": "task_started", "payload": {}},
    {"seq": 1_001, "task_id": 7, "type": "task_progress", "payload": {}},
    {"seq": 1_002, "task_id": 7, "type": "task_complete", "payload": {}},
]


@pytest.fixture
def controller() -> Iterator[SimpleNamespace]:
    stub = SimpleNamespace(store=_StubStore(_EVENTS), events=_StubBroker(_EVENTS))
    with (
        patch("koda.services.runtime.api.get_runtime_controller", return_value=stub),
        patch("koda.services.runtime.api.RuntimeAccessService", _StubRuntimeAccessService),
        patch("koda.services.runtime.api.RUNTIME_LOCAL_UI_TOKEN", "test-token"),
    ):
        yield stub


@pytest.fixture
async def client(controller: SimpleNamespace) -> AsyncIterator[TestClient]:
    app = web.Application()
    app.router.add_get("/api/runtime/tasks/{task_id:\\d+}/events", _runtime_task_events)
    app.router.add_get("/api/runtime/stream", _runtime_stream_sse)
    app.router.add_get("/ws/runtime", _runtime_stream_ws)
    app.router.add_get("/ws/runtime/events", _runtime_stream_ws)
    async with TestClient(TestServer(app)) as test_client:
        yield test_client


_HEADERS = {"X-Runtime-Token": "signed"}


def test_parse_positive_int_rejects_non_numeric_values_with_400() -> None:
    with pytest.raises(web.HTTPBadRequest):
        _parse_positive_int("abc", name="limit", default=10)


@pytest.mark.parametrize("after_seq", ["1001", "250000", str(_INT64_MAX)])
async def test_task_events_accept_cursor_beyond_page_size(
    client: TestClient, controller: SimpleNamespace, after_seq: str
) -> None:
    response = await client.get(f"/api/runtime/tasks/7/events?after_seq={after_seq}", headers=_HEADERS)

    assert response.status == 200
    assert controller.store.calls[-1]["after_seq"] == int(after_seq)


async def test_sse_stream_resumes_after_event_id_1000(client: TestClient, controller: SimpleNamespace) -> None:
    response = await client.get("/api/runtime/stream?task_id=7&after_seq=1001", headers=_HEADERS)

    assert response.status == 200
    assert response.headers["Content-Type"].startswith("text/event-stream")
    body = await response.text()
    assert '"seq": 1002' in body
    assert '"seq": 1001' not in body
    assert controller.events.calls[-1]["after_seq"] == 1001


@pytest.mark.parametrize("path", ["/ws/runtime", "/ws/runtime/events"])
async def test_ws_stream_resumes_after_event_id_1000(
    client: TestClient, controller: SimpleNamespace, path: str
) -> None:
    async with client.ws_connect(f"{path}?task_id=7&after_seq=1001", headers=_HEADERS) as ws:
        message = await ws.receive_json(timeout=5)

    assert message["seq"] == 1002
    assert controller.events.calls[-1]["after_seq"] == 1001
    assert controller.events.calls[-1]["task_id"] == 7


@pytest.mark.parametrize("after_seq", ["abc", "1.5", "-1", str(_INT64_MAX + 1)])
@pytest.mark.parametrize("path", ["/api/runtime/stream", "/api/runtime/tasks/7/events"])
async def test_invalid_cursor_is_a_client_error(
    client: TestClient, controller: SimpleNamespace, path: str, after_seq: str
) -> None:
    response = await client.get(f"{path}?after_seq={after_seq}", headers=_HEADERS)

    assert response.status == 400
    assert "invalid after_seq" in await response.text()
    assert controller.events.calls == []
    assert controller.store.calls == []


@pytest.mark.parametrize(
    "query",
    ["after_seq=abc", "after_seq=-1", f"after_seq={_INT64_MAX + 1}", "task_id=abc", "env_id=1.5", "task_id=-3"],
)
@pytest.mark.parametrize("path", ["/ws/runtime", "/ws/runtime/events"])
async def test_ws_rejects_invalid_query_before_upgrade(
    client: TestClient, controller: SimpleNamespace, path: str, query: str
) -> None:
    with pytest.raises(WSServerHandshakeError) as excinfo:
        await client.ws_connect(f"{path}?{query}", headers=_HEADERS)

    assert excinfo.value.status == 400
    assert controller.events.calls == []


@pytest.mark.parametrize("query", ["task_id=abc", "env_id=1.5", "task_id=-3", f"env_id={_INT64_MAX + 1}"])
async def test_sse_rejects_invalid_filter_before_streaming(
    client: TestClient, controller: SimpleNamespace, query: str
) -> None:
    # A bad filter used to raise only after the 200 headers were sent, so the
    # client saw an empty stream and reconnected forever.
    response = await client.get(f"/api/runtime/stream?{query}", headers=_HEADERS)

    assert response.status == 400
    assert f"invalid {query.split('=')[0]}" in await response.text()
    assert controller.events.calls == []


async def test_sse_passes_numeric_filters_to_the_broker(client: TestClient, controller: SimpleNamespace) -> None:
    response = await client.get("/api/runtime/stream?task_id=7&env_id=0&after_seq=1001", headers=_HEADERS)

    assert response.status == 200
    await response.text()
    call = controller.events.calls[-1]
    assert (call["task_id"], call["env_id"], call["after_seq"]) == (7, 0, 1001)
    assert call["task_ids_refresh"] is None
