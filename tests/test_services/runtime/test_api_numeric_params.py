"""Every numeric query parameter of the runtime API answers a bad value with 400, never 500."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from aiohttp import WSServerHandshakeError, web
from aiohttp.test_utils import TestClient, TestServer

from koda.services.runtime.api import setup_runtime_routes


class _AllowAllRuntimeAccess:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def authorize(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"capability": "attach"}


class _Store:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def list_events(self, **_kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append("list_events")
        return []

    def list_terminals(self, _task_id: int) -> list[dict[str, Any]]:
        self.calls.append("list_terminals")
        return []


@pytest.fixture
def controller() -> Iterator[SimpleNamespace]:
    stub = SimpleNamespace(
        store=_Store(),
        authorize_attach=lambda **_kwargs: {"task_id": 7, "terminal_id": 3, "can_write": 0},
    )
    with (
        patch("koda.services.runtime.api.get_runtime_controller", return_value=stub),
        patch("koda.services.runtime.api.RuntimeAccessService", _AllowAllRuntimeAccess),
        patch("koda.services.runtime.api.RUNTIME_LOCAL_UI_TOKEN", "test-token"),
    ):
        yield stub


@pytest.fixture
async def client(controller: SimpleNamespace) -> AsyncIterator[TestClient]:
    app = web.Application()
    setup_runtime_routes(app)
    async with TestClient(TestServer(app)) as test_client:
        yield test_client


_HEADERS = {"X-Runtime-Token": "signed", "X-Koda-Attach-Token": "attach"}

# Each HTTP route and numeric query parameter read through ``_parse_positive_int``.
_HTTP_PARAMETERS = [
    ("/api/runtime/schedules", "limit"),
    ("/api/runtime/schedules/1", "run_limit"),
    ("/api/runtime/schedules/1", "run_offset"),
    ("/api/runtime/schedules/1", "offset"),
    ("/api/runtime/schedules/1", "event_limit"),
    ("/api/runtime/tasks/7/events", "after_seq"),
    ("/api/runtime/stream", "after_seq"),
    ("/api/runtime/stream", "task_id"),
    ("/api/runtime/stream", "env_id"),
]

_WS_PARAMETERS = [
    ("/ws/runtime", "after_seq"),
    ("/ws/runtime", "task_id"),
    ("/ws/runtime", "env_id"),
    ("/ws/runtime/events", "after_seq"),
    ("/ws/runtime/events", "task_id"),
    ("/ws/runtime/events", "env_id"),
    ("/ws/runtime/tasks/7/terminals/3", "after_offset"),
]


@pytest.mark.parametrize("value", ["abc", "1.5", "-"])
@pytest.mark.parametrize(("path", "name"), _HTTP_PARAMETERS)
async def test_http_numeric_parameter_rejects_a_non_numeric_value(
    client: TestClient, controller: SimpleNamespace, path: str, name: str, value: str
) -> None:
    response = await client.get(path, params={name: value}, headers=_HEADERS)

    assert response.status == 400
    assert f"invalid {name}" in await response.text()
    assert controller.store.calls == []


@pytest.mark.parametrize("value", ["abc", "1.5", "-"])
@pytest.mark.parametrize(("path", "name"), _WS_PARAMETERS)
async def test_ws_numeric_parameter_rejects_a_non_numeric_value_before_upgrade(
    client: TestClient, controller: SimpleNamespace, path: str, name: str, value: str
) -> None:
    with pytest.raises(WSServerHandshakeError) as excinfo:
        await client.ws_connect(f"{path}?{name}={value}", headers=_HEADERS)

    assert excinfo.value.status == 400
    assert controller.store.calls == []
