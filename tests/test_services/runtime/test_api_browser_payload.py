"""The browser payload is an explicit projection: no host path and no free-form metadata (M3-E8-T4).

A kernel-forwarded live session stores the kernel's answer as the session ``metadata``. Its own
``metadata`` carries the ``*_log`` paths the kernel sets to ``<runtime_dir>/<name>.log``, and the
kernel may add keys later. None of that may reach a browser through ``GET .../browser``,
``POST .../attach/browser`` or the browser WebSocket's ``browser.snapshot``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from koda.services.runtime.api import (
    _runtime_attach_browser,
    _runtime_browser_ws,
    _runtime_task_browser,
    _runtime_task_sessions,
)
from koda.services.runtime.controller import RuntimeController

_TASK_ID = 7
_ATTACH_TOKEN = "attach-token"
_UNKNOWN_KEYS = ("kernel_future_field", "session_future_field")


class _AllowAll:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def authorize(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"capability": "attach"}


class _Store:
    def __init__(self, sessions: list[dict[str, Any]]) -> None:
        self.sessions = sessions

    def get_environment_by_task(self, task_id: int) -> dict[str, Any]:
        return {"id": 3, "task_id": task_id}

    def list_browser_sessions(self, task_id: int) -> list[dict[str, Any]]:
        return [dict(row) for row in self.sessions]

    def list_artifacts(self, task_id: int) -> list[dict[str, Any]]:
        return []

    def list_attach_sessions(self, task_id: int) -> list[dict[str, Any]]:
        return []

    def list_terminals(self, task_id: int) -> list[dict[str, Any]]:
        return []


class _Controller:
    """The real snapshot and sessions logic over a stub store."""

    get_browser_snapshot = RuntimeController.get_browser_snapshot
    list_sessions = RuntimeController.list_sessions

    def __init__(self, runtime_root: Path, sessions: list[dict[str, Any]]) -> None:
        self.runtime_root = runtime_root
        self.store = _Store(sessions)

    async def create_attach_session(self, **kwargs: Any) -> dict[str, Any]:
        return {"attach_session_id": 1, "token": _ATTACH_TOKEN, "task_id": _TASK_ID, "attach_kind": "browser"}

    def authorize_attach(self, *, token: str, attach_kind: str) -> dict[str, Any] | None:
        return {"task_id": _TASK_ID} if token == _ATTACH_TOKEN else None

    async def close_attach_session(self, *, token: str) -> None:
        return None


def _kernel_forwarded_session(task_root: Path, state_root: Path) -> dict[str, Any]:
    """A session row as ``_start_browser_runtime_state`` stores a kernel-forwarded start."""
    runtime_dir = task_root / "browser"
    live = {
        "session_id": "kbs-7",
        "task_id": str(_TASK_ID),
        "environment_id": "env-7",
        "scope_id": _TASK_ID,
        "transport": "novnc",
        "status": "running",
        "runtime_dir": str(runtime_dir),
        "display_id": 99,
        "vnc_port": 5901,
        "novnc_port": 6081,
        "missing_binaries": [],
        "created_at_ms": 1_700_000_000_000,
        "forwarded": True,
        "metadata": {
            "requested_transport": "novnc",
            "xvfb_pid": "101",
            "xvfb_log": str(runtime_dir / "xvfb.log"),
            "openbox_log": str(runtime_dir / "openbox.log"),
            "x11vnc_log": str(runtime_dir / "x11vnc.log"),
            "websockify_log": str(runtime_dir / "websockify.log"),
            "runtime_dir": str(runtime_dir),
            "scope_id": str(_TASK_ID),
            "kernel_future_field": str(state_root / "kernel" / "secret"),
        },
        "xvfb_pid": 101,
        "kernel_session_id": "kbs-7",
        "kernel_environment_id": "env-7",
        "kernel_status": "running",
        "session_future_field": str(task_root / "profile"),
    }
    return {
        "id": 1,
        "task_id": _TASK_ID,
        "env_id": 3,
        "scope_id": _TASK_ID,
        "transport": "novnc",
        "status": "running",
        "display_id": 99,
        "vnc_port": 5901,
        "novnc_port": 6081,
        "metadata": live,
        "created_at": "2026-11-15T00:00:00+00:00",
        "updated_at": "2026-11-15T00:00:01+00:00",
        "ended_at": None,
    }


@pytest.fixture
def roots(tmp_path: Path) -> tuple[Path, Path, Path]:
    runtime_root = tmp_path / "runtime"
    state_root = tmp_path / "state"
    task_root = runtime_root / "tasks" / str(_TASK_ID)
    (task_root / "browser").mkdir(parents=True)
    return runtime_root, state_root, task_root


@pytest.fixture
async def client(roots: tuple[Path, Path, Path]) -> AsyncIterator[TestClient]:
    runtime_root, state_root, task_root = roots
    controller = _Controller(runtime_root, [_kernel_forwarded_session(task_root, state_root)])
    app = web.Application()
    app.router.add_get("/api/runtime/tasks/{task_id:\\d+}/browser", _runtime_task_browser)
    app.router.add_get("/api/runtime/tasks/{task_id:\\d+}/sessions", _runtime_task_sessions)
    app.router.add_post("/api/runtime/tasks/{task_id:\\d+}/attach/browser", _runtime_attach_browser)
    app.router.add_get("/ws/runtime/tasks/{task_id:\\d+}/browser", _runtime_browser_ws)
    with (
        patch("koda.services.runtime.api.get_runtime_controller", return_value=controller),
        patch("koda.services.runtime.api.RuntimeAccessService", _AllowAll),
        patch("koda.services.runtime.api.RUNTIME_LOCAL_UI_TOKEN", "secret"),
    ):
        async with TestClient(TestServer(app)) as test_client:
            yield test_client


_HEADERS = {"X-Runtime-Token": "signed"}


def _assert_no_host_path_or_unknown_key(text: str, roots: tuple[Path, Path, Path]) -> None:
    for root in roots:
        assert str(root) not in text
    for key in (*_UNKNOWN_KEYS, "xvfb_log", "openbox_log", "x11vnc_log", "websockify_log", '"metadata"'):
        assert key not in text


_EXPECTED_BROWSER = {
    "scope_id": _TASK_ID,
    "transport": "novnc",
    "status": "running",
    "runtime_dir": "browser",
    "display_id": 99,
    "vnc_port": 5901,
    "novnc_port": 6081,
    "missing_binaries": [],
    "screenshot_url": f"/api/runtime/tasks/{_TASK_ID}/browser/screenshot",
    "preview_url": f"/api/runtime/tasks/{_TASK_ID}/browser/screenshot",
    "preview_available": True,
}


async def test_get_browser_projects_the_live_session(client: TestClient, roots: tuple[Path, Path, Path]) -> None:
    response = await client.get(f"/api/runtime/tasks/{_TASK_ID}/browser", headers=_HEADERS)

    text = await response.text()
    assert response.status == 200
    _assert_no_host_path_or_unknown_key(text, roots)
    body = json.loads(text)
    assert body["browser"] == _EXPECTED_BROWSER
    assert body["sessions"] == [
        {
            "id": 1,
            "task_id": _TASK_ID,
            "env_id": 3,
            "scope_id": _TASK_ID,
            "transport": "novnc",
            "status": "running",
            "display_id": 99,
            "vnc_port": 5901,
            "novnc_port": 6081,
            "created_at": "2026-11-15T00:00:00+00:00",
            "updated_at": "2026-11-15T00:00:01+00:00",
            "ended_at": None,
        }
    ]


async def test_task_sessions_projects_the_browser_sessions(client: TestClient, roots: tuple[Path, Path, Path]) -> None:
    response = await client.get(f"/api/runtime/tasks/{_TASK_ID}/sessions", headers=_HEADERS)

    text = await response.text()
    assert response.status == 200
    _assert_no_host_path_or_unknown_key(text, roots)
    assert [row["id"] for row in json.loads(text)["browser_sessions"]] == [1]


async def test_attach_browser_projects_the_live_session(client: TestClient, roots: tuple[Path, Path, Path]) -> None:
    response = await client.post(f"/api/runtime/tasks/{_TASK_ID}/attach/browser", headers=_HEADERS)

    text = await response.text()
    assert response.status == 200
    _assert_no_host_path_or_unknown_key(text, roots)
    body = json.loads(text)
    assert body["browser"] == _EXPECTED_BROWSER
    assert body["ws_url"] == f"/ws/runtime/tasks/{_TASK_ID}/browser"


async def test_browser_websocket_snapshot_projects_the_live_session(
    client: TestClient, roots: tuple[Path, Path, Path]
) -> None:
    async with client.ws_connect(
        f"/ws/runtime/tasks/{_TASK_ID}/browser", headers={**_HEADERS, "X-Koda-Attach-Token": _ATTACH_TOKEN}
    ) as ws:
        message = await ws.receive(timeout=5)

    _assert_no_host_path_or_unknown_key(str(message.data), roots)
    snapshot = json.loads(str(message.data))
    assert snapshot == {"type": "browser.snapshot", "browser": _EXPECTED_BROWSER}


async def test_text_fields_pass_unchanged_and_a_runtime_dir_outside_the_task_is_null(
    client: TestClient, roots: tuple[Path, Path, Path]
) -> None:
    runtime_root, _state_root, _task_root = roots
    with patch.object(
        _Controller,
        "get_browser_snapshot",
        lambda self, task_id: {
            "status": "unavailable",
            "last_known_status": "running",
            "runtime_dir": str(runtime_root.parent / "kernel" / "tasks" / "7" / "browser"),
            "last_title": "/",
            "kernel_error": "/usr/bin/Xvfb: not found",
            "unavailable_reason": "/dev/shm is full",
            "visual_available": False,
            "session_persisted_only": True,
        },
    ):
        response = await client.get(f"/api/runtime/tasks/{_TASK_ID}/browser", headers=_HEADERS)

    browser = json.loads(await response.text())["browser"]
    assert browser["runtime_dir"] is None
    assert (browser["last_title"], browser["kernel_error"], browser["unavailable_reason"]) == (
        "/",
        "/usr/bin/Xvfb: not found",
        "/dev/shm is full",
    )
    assert (browser["status"], browser["last_known_status"]) == ("unavailable", "running")
    assert (browser["visual_available"], browser["session_persisted_only"]) == (False, True)


async def test_the_kernel_unavailable_reason_is_lifted_to_the_top_level(
    client: TestClient, roots: tuple[Path, Path, Path]
) -> None:
    """The kernel answers missing_display_or_ports only in the session's metadata (D-359)."""
    _runtime_root, _state_root, task_root = roots
    unavailable = {
        "session_id": "kbs-7",
        "scope_id": _TASK_ID,
        "transport": "novnc",
        "status": "unavailable",
        "runtime_dir": str(task_root / "browser"),
        "missing_binaries": [],
        "forwarded": True,
        "metadata": {"requested_transport": "novnc", "unavailable_reason": "missing_display_or_ports"},
    }
    with patch.object(_Controller, "get_browser_snapshot", lambda self, task_id: dict(unavailable)):
        response = await client.get(f"/api/runtime/tasks/{_TASK_ID}/browser", headers=_HEADERS)

    browser = json.loads(await response.text())["browser"]
    assert (browser["status"], browser["unavailable_reason"]) == ("unavailable", "missing_display_or_ports")
    assert "metadata" not in browser


async def test_a_top_level_unavailable_reason_is_kept(client: TestClient) -> None:
    snapshot = {
        "status": "unavailable",
        "unavailable_reason": "Browser session metadata was retained.",
        "metadata": {"unavailable_reason": "missing_display_or_ports"},
    }
    with patch.object(_Controller, "get_browser_snapshot", lambda self, task_id: dict(snapshot)):
        response = await client.get(f"/api/runtime/tasks/{_TASK_ID}/browser", headers=_HEADERS)

    assert json.loads(await response.text())["browser"]["unavailable_reason"] == (
        "Browser session metadata was retained."
    )
