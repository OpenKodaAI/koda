"""Runtime events are an explicit projection: no host path and no free-form kernel data (D-357).

``browser.started`` records the whole kernel-forwarded browser session, with its ``metadata``
``*_log`` paths and its absolute ``runtime_dir``; ``browser.frame``, ``browser.video_ready`` and
``browser.trace_ready`` record the file's absolute path; ``runtime_kernel.start_browser_session``
records the kernel's whole answer and health. The events route, the SSE stream and the event
WebSockets answer each from named fields, with paths relative to the task's runtime directory.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from koda.services.runtime.api import _runtime_stream_sse, _runtime_stream_ws, _runtime_task_events
from koda.services.runtime.events import RuntimeEventBroker

_TASK_ID = 7
_HEADERS = {"X-Runtime-Token": "signed"}


class _AllowAll:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def authorize(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"capability": "read"}


def _event(seq: int, event_type: str, payload: dict[str, Any], refs: list[str] | None = None) -> dict[str, Any]:
    """An event as ``PostgresRuntimeStore.list_events`` returns it."""
    return {
        "task_id": _TASK_ID,
        "env_id": 3,
        "attempt": None,
        "phase": "provisioning",
        "severity": "info",
        "resource_snapshot_ref": None,
        "seq": seq,
        "type": event_type,
        "ts": "2026-11-15T00:00:00+00:00",
        "payload": payload,
        "artifact_refs": refs or [],
    }


def _seeded_events(task_root: Path, state_root: Path) -> list[dict[str, Any]]:
    runtime_dir = task_root / "browser"
    metadata = {
        "requested_transport": "novnc",
        "xvfb_log": str(runtime_dir / "xvfb.log"),
        "openbox_log": str(runtime_dir / "openbox.log"),
        "x11vnc_log": str(runtime_dir / "x11vnc.log"),
        "websockify_log": str(runtime_dir / "websockify.log"),
        "runtime_dir": str(runtime_dir),
        "kernel_future_field": str(state_root / "kernel" / "secret"),
    }
    session = {
        "session_id": "kbs-7",
        "scope_id": _TASK_ID,
        "transport": "novnc",
        "status": "running",
        "runtime_dir": str(runtime_dir),
        "display_id": 99,
        "vnc_port": 5901,
        "novnc_port": 6081,
        "missing_binaries": [],
        "forwarded": True,
        "metadata": metadata,
        "kernel_session_id": "kbs-7",
    }
    frame = str(runtime_dir / "frame_1.png")
    video = str(runtime_dir / "session.webm")
    trace = str(runtime_dir / "trace.zip")
    return [
        _event(1, "browser.started", session),
        _event(2, "browser.frame", {"path": frame}, [frame]),
        _event(3, "browser.video_ready", {"path": video}, [video]),
        _event(4, "browser.trace_ready", {"path": trace}, [trace]),
        _event(
            5,
            "runtime_kernel.start_browser_session",
            {
                "operation": "start_browser_session",
                "recorded_at": "2026-11-15T00:00:00+00:00",
                "required": True,
                "forwarded": True,
                "ok": True,
                "status": "running",
                "runtime_kernel": {"details": {"socket_path": str(state_root / "kernel.sock")}},
                "cutover": {"mode": "rust"},
                **session,
            },
        ),
    ]


_EXPECTED_PAYLOADS = [
    {
        "scope_id": _TASK_ID,
        "transport": "novnc",
        "status": "running",
        "display_id": 99,
        "vnc_port": 5901,
        "novnc_port": 6081,
        "missing_binaries": [],
        "runtime_dir": "browser",
    },
    {"path": "browser/frame_1.png"},
    {"path": "browser/session.webm"},
    {"path": "browser/trace.zip"},
    {
        "operation": "start_browser_session",
        "recorded_at": "2026-11-15T00:00:00+00:00",
        "required": True,
        "forwarded": True,
        "ok": True,
        "status": "running",
    },
]
_EXPECTED_REFS = [[], ["browser/frame_1.png"], ["browser/session.webm"], ["browser/trace.zip"], []]


class _Store:
    def __init__(self, events: list[dict[str, Any]]) -> None:
        self.events = events

    def list_events(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return [dict(event) for event in self.events]

    def add_event(self, **kwargs: Any) -> dict[str, Any]:
        """As the store answers a publish: the payload is the stored JSON text."""
        return {
            **_event(99, kwargs["event_type"], {}, list(kwargs.get("artifact_refs") or [])),
            "payload": json.dumps(kwargs.get("payload") or {}),
        }


class _Controller:
    def __init__(self, runtime_root: Path, events: list[dict[str, Any]]) -> None:
        self.runtime_root = runtime_root
        self.store = _Store(events)
        self.events = RuntimeEventBroker(self.store, runtime_root)  # type: ignore[arg-type]


@pytest.fixture
def roots(tmp_path: Path) -> tuple[Path, Path, Path]:
    runtime_root = tmp_path / "runtime"
    state_root = tmp_path / "state"
    task_root = runtime_root / "tasks" / str(_TASK_ID)
    (task_root / "browser").mkdir(parents=True)
    return runtime_root, state_root, task_root


@pytest.fixture
def controller(roots: tuple[Path, Path, Path]) -> _Controller:
    runtime_root, state_root, task_root = roots
    return _Controller(runtime_root, _seeded_events(task_root, state_root))


@pytest.fixture
async def client(controller: _Controller) -> AsyncIterator[TestClient]:
    app = web.Application()
    app.router.add_get("/api/runtime/tasks/{task_id:\\d+}/events", _runtime_task_events)
    app.router.add_get("/api/runtime/stream", _runtime_stream_sse)
    app.router.add_get("/ws/runtime", _runtime_stream_ws)
    with (
        patch("koda.services.runtime.api.get_runtime_controller", return_value=controller),
        patch("koda.services.runtime.api.RuntimeAccessService", _AllowAll),
        patch("koda.services.runtime.api.RUNTIME_LOCAL_UI_TOKEN", "secret"),
        patch("koda.services.runtime.events.RUNTIME_EVENT_STREAM_ENABLED", True),
    ):
        async with TestClient(TestServer(app)) as test_client:
            yield test_client


def _assert_no_host_path_or_free_form_data(text: str, roots: tuple[Path, Path, Path]) -> None:
    for root in roots:
        assert str(root) not in text
    for key in ("_log", '"metadata"', "kernel_future_field", '"runtime_kernel"', '"cutover"', "session_id"):
        assert key not in text


def _assert_projected(events: list[dict[str, Any]]) -> None:
    assert [event["seq"] for event in events] == [1, 2, 3, 4, 5]
    assert [event["payload"] for event in events] == _EXPECTED_PAYLOADS
    assert [event["artifact_refs"] for event in events] == _EXPECTED_REFS
    assert set(events[0]) == {
        "seq",
        "ts",
        "task_id",
        "env_id",
        "attempt",
        "phase",
        "type",
        "severity",
        "resource_snapshot_ref",
        "payload",
        "artifact_refs",
    }


async def test_task_events_route_projects_each_event(client: TestClient, roots: tuple[Path, Path, Path]) -> None:
    response = await client.get(f"/api/runtime/tasks/{_TASK_ID}/events", headers=_HEADERS)

    text = await response.text()
    assert response.status == 200
    _assert_no_host_path_or_free_form_data(text, roots)
    _assert_projected(json.loads(text)["items"])


async def test_sse_stream_projects_stored_and_live_events(
    client: TestClient, controller: _Controller, roots: tuple[Path, Path, Path]
) -> None:
    _runtime_root, _state_root, task_root = roots
    response = await client.get(f"/api/runtime/stream?task_id={_TASK_ID}", headers=_HEADERS)
    chunks = [await asyncio.wait_for(response.content.readuntil(b"\n\n"), timeout=5) for _ in range(5)]
    # A live event reaches subscribers as the store returned it, with the payload as JSON text.
    frame = str(task_root / "browser" / "frame_2.png")
    await controller.events.publish(
        task_id=_TASK_ID,
        env_id=3,
        attempt=None,
        phase="executing",
        event_type="browser.frame",
        payload={"path": frame},
        artifact_refs=[frame],
    )
    chunks.append(await asyncio.wait_for(response.content.readuntil(b"\n\n"), timeout=5))
    response.close()

    text = b"".join(chunks).decode()
    _assert_no_host_path_or_free_form_data(text, roots)
    events = [json.loads(chunk.decode().removeprefix("data: ")) for chunk in chunks]
    _assert_projected(events[:5])
    assert (events[5]["payload"], events[5]["artifact_refs"]) == (
        {"path": "browser/frame_2.png"},
        ["browser/frame_2.png"],
    )


async def test_event_websocket_projects_each_event(client: TestClient, roots: tuple[Path, Path, Path]) -> None:
    async with client.ws_connect(f"/ws/runtime?task_id={_TASK_ID}", headers=_HEADERS) as ws:
        messages = [await ws.receive(timeout=5) for _ in range(5)]

    text = "".join(str(message.data) for message in messages)
    _assert_no_host_path_or_free_form_data(text, roots)
    _assert_projected([json.loads(str(message.data)) for message in messages])


async def test_browser_started_lifts_the_kernel_unavailable_reason(client: TestClient, controller: _Controller) -> None:
    """The kernel answers missing_display_or_ports only in the session's metadata (D-359)."""
    controller.store.events = [
        _event(
            1,
            "browser.started",
            {"status": "unavailable", "metadata": {"unavailable_reason": "missing_display_or_ports"}},
        )
    ]

    response = await client.get(f"/api/runtime/tasks/{_TASK_ID}/events", headers=_HEADERS)

    assert json.loads(await response.text())["items"][0]["payload"] == {
        "status": "unavailable",
        "unavailable_reason": "missing_display_or_ports",
    }


async def test_other_event_types_send_only_their_scalar_fields_and_paths_outside_the_task_are_dropped(
    client: TestClient, controller: _Controller, roots: tuple[Path, Path, Path]
) -> None:
    """A type without its own projection sends its top-level scalars, never a nested record (D-357)."""
    runtime_root, state_root, task_root = roots
    controller.store.events = [
        _event(
            1,
            "plan.updated",
            {"goal": "ship", "steps": ["a", "b"], "context": {"cwd": str(state_root / "agents" / "A")}},
            [str(task_root / "decision_trace.jsonl"), str(runtime_root / "worktrees" / "task-7")],
        ),
        _event(
            2,
            "worktree.created",
            {
                "workspace_path": str(runtime_root / "worktrees" / "task-7-x"),
                "branch_name": "task/7-x",
                "created": True,
                "mode": "worktree",
                "metadata_path": str(task_root / "worktree.json"),
            },
        ),
    ]

    response = await client.get(f"/api/runtime/tasks/{_TASK_ID}/events", headers=_HEADERS)

    items = json.loads(await response.text())["items"]
    assert items[0]["payload"] == {"goal": "ship"}
    assert items[0]["artifact_refs"] == ["decision_trace.jsonl"]
    assert items[1]["payload"] == {
        "branch_name": "task/7-x",
        "created": True,
        "mode": "worktree",
        "workspace_path": None,
        "metadata_path": "worktree.json",
    }


def _kernel_operation_record(runtime_root: Path, state_root: Path) -> dict[str, Any]:
    """A failed required operation as ``_forward_runtime_kernel_operation`` records it."""
    return {
        "operation": "restore_checkpoint",
        "recorded_at": "2026-11-15T00:00:00+00:00",
        "required": True,
        "runtime_kernel": {
            "details": {"runtime_root": str(runtime_root), "socket_path": str(state_root / "kernel.sock")}
        },
        "cutover": {"mode": "rust", "socket": str(state_root / "kernel.sock")},
        "forwarded": True,
        "restored": False,
        "workspace_path": str(runtime_root / "worktrees" / "task-7"),
        "reason": "checkpoint missing",
        "ok": False,
    }


async def test_warning_and_artifact_events_send_named_fields_with_task_relative_paths(
    client: TestClient, controller: _Controller, roots: tuple[Path, Path, Path]
) -> None:
    """``warning.issued`` carries a kernel record and ``artifact_ready`` a file path (D-357)."""
    runtime_root, state_root, task_root = roots
    voice = str(task_root / "artifacts" / "voice-response-7.ogg")
    artifact = {
        "id": "12",
        "kind": "audio",
        "label": "voice-response-7.ogg",
        "mime_type": "audio/ogg",
        "size_bytes": 2048,
        "created_at": "2026-11-15T00:00:00+00:00",
        "source_session_id": "s-1",
        "source_execution_id": "7",
        "download_url": "/api/runtime/artifacts/12/download",
        "preview_state": "available",
    }
    controller.store.events = [
        _event(
            1,
            "warning.issued",
            {
                "warning_type": "runtime_kernel_restore_checkpoint_failed",
                "message": "checkpoint missing",
                "details": _kernel_operation_record(runtime_root, state_root),
            },
        ),
        _event(2, "warning.issued", {"message": "stop", "actor": "operator", "kind": "cancel_requested"}),
        _event(3, "artifact_ready", {"artifact": {**artifact, "path": voice}}, [voice]),
        # A provider output file lives in the agent's work directory, outside the task.
        _event(4, "artifact_ready", {"artifact": {**artifact, "path": str(state_root / "work" / "out.png")}}),
    ]

    response = await client.get(f"/api/runtime/tasks/{_TASK_ID}/events", headers=_HEADERS)

    text = await response.text()
    for root in roots:
        assert str(root) not in text
    for key in ('"runtime_kernel"', '"cutover"', '"restored"', '"workspace_path"'):
        assert key not in text
    items = json.loads(text)["items"]
    assert items[0]["payload"] == {
        "warning_type": "runtime_kernel_restore_checkpoint_failed",
        "message": "checkpoint missing",
        "details": {
            "operation": "restore_checkpoint",
            "recorded_at": "2026-11-15T00:00:00+00:00",
            "required": True,
            "forwarded": True,
            "ok": False,
            "reason": "checkpoint missing",
        },
    }
    assert items[1]["payload"] == {"message": "stop", "actor": "operator", "kind": "cancel_requested"}
    assert items[2]["payload"] == {"artifact": {**artifact, "path": "artifacts/voice-response-7.ogg"}}
    assert items[2]["artifact_refs"] == ["artifacts/voice-response-7.ogg"]
    assert items[3]["payload"] == {"artifact": {**artifact, "path": None}}
