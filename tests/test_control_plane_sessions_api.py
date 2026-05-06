"""Focused tests for dashboard session API handlers."""

from __future__ import annotations

import asyncio
import json
import threading
import urllib.error
import urllib.request
from typing import Any

import pytest

from koda.control_plane.manager import ControlPlaneManager


class _JsonRequest:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.match_info = {"agent_id": "ATLAS"}
        self._payload = payload
        self.can_read_body = True

    async def json(self) -> dict[str, Any]:
        return self._payload


class _FailingSessionManager:
    def send_dashboard_session_message(self, *_args: object, **_kwargs: object) -> dict[str, Any]:
        raise RuntimeError("runtime token is unavailable for this agent")


@pytest.mark.asyncio
async def test_post_dashboard_session_message_returns_json_for_runtime_token_failure(monkeypatch):
    import koda.control_plane.api as api_mod

    monkeypatch.setattr(api_mod, "_manager", lambda: _FailingSessionManager())

    response = await api_mod.post_dashboard_session_message_route(_JsonRequest({"text": "hello"}))  # type: ignore[arg-type]

    assert response.status == 503
    assert json.loads(response.text) == {"error": "runtime token is unavailable for this agent"}


@pytest.mark.asyncio
async def test_post_dashboard_session_message_does_not_block_control_plane_event_loop(monkeypatch):
    import koda.control_plane.api as api_mod

    called = threading.Event()
    release = threading.Event()

    class BlockingSessionManager:
        def send_dashboard_session_message(self, *_args: object, **_kwargs: object) -> dict[str, Any]:
            called.set()
            if not release.wait(timeout=0.25):
                return {"accepted": False, "session_id": "late", "task_id": -1}
            return {"accepted": True, "session_id": "session-1", "task_id": 7}

    monkeypatch.setattr(api_mod, "_manager", lambda: BlockingSessionManager())

    route_task = asyncio.create_task(
        api_mod.post_dashboard_session_message_route(_JsonRequest({"text": "hello", "session_id": "session-1"}))  # type: ignore[arg-type]
    )
    assert await asyncio.to_thread(called.wait, 1)
    await asyncio.sleep(0)

    assert not route_task.done()

    release.set()
    response = await route_task

    assert response.status == 202
    assert json.loads(response.text) == {
        "accepted": True,
        "session_id": "session-1",
        "task_id": 7,
    }


class _RuntimeResponse:
    def __init__(self, payload: dict[str, Any], *, status: int = 200) -> None:
        self.payload = payload
        self.status = status

    def __enter__(self) -> _RuntimeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_send_dashboard_session_message_wakes_and_retries_active_runtime(monkeypatch):
    manager = object.__new__(ControlPlaneManager)
    monkeypatch.setattr(manager, "_require_dashboard_agent", lambda _agent_id: ("ATLAS", {"status": "active"}))
    monkeypatch.setattr(
        manager,
        "get_runtime_access",
        lambda *_args, **_kwargs: {
            "runtime_base_url": "http://runtime.local",
            "runtime_request_token": "runtime-token",
        },
    )
    wake_reasons: list[str] = []
    monkeypatch.setattr(
        "koda.control_plane.lifecycle_events.notify_lifecycle_change",
        lambda *, reason: wake_reasons.append(reason),
    )
    post_attempts = 0

    def fake_urlopen(request: urllib.request.Request, timeout: float):
        nonlocal post_attempts
        url = request.full_url
        if url.endswith("/api/runtime/sessions/messages"):
            post_attempts += 1
            if post_attempts == 1:
                raise urllib.error.URLError("connection refused")
            return _RuntimeResponse({"accepted": True, "session_id": "session-1", "task_id": 7})
        if url.endswith("/api/runtime/readiness"):
            return _RuntimeResponse({"ready": True})
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = manager.send_dashboard_session_message("ATLAS", text="hello", session_id="session-1")

    assert result == {"accepted": True, "session_id": "session-1", "task_id": 7}
    assert post_attempts == 2
    assert wake_reasons == ["dashboard-chat:ATLAS"]


def test_send_dashboard_session_message_rejects_paused_agent_without_runtime_call(monkeypatch):
    manager = object.__new__(ControlPlaneManager)
    monkeypatch.setattr(manager, "_require_dashboard_agent", lambda _agent_id: ("ATLAS", {"status": "paused"}))

    def fail_urlopen(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("runtime should not be contacted for paused agents")

    monkeypatch.setattr("urllib.request.urlopen", fail_urlopen)

    with pytest.raises(ValueError, match="activate it before sending"):
        manager.send_dashboard_session_message("ATLAS", text="hello", session_id="session-1")


def test_get_dashboard_runtime_artifact_for_download_reads_case_insensitive_agent(monkeypatch, tmp_path):
    manager = object.__new__(ControlPlaneManager)
    image_path = tmp_path / "render.png"
    image_path.write_bytes(b"png bytes")
    monkeypatch.setattr(manager, "_require_dashboard_agent", lambda _agent_id: ("KODA", {"status": "active"}))

    def fake_fetch_one(query: str, params: tuple[Any, ...]) -> dict[str, Any]:
        assert "lower(agent_id) = lower(?)" in query
        assert params == (428, "KODA")
        return {
            "id": 428,
            "agent_id": "koda",
            "task_id": 453,
            "env_id": None,
            "artifact_kind": "image",
            "label": "render.png",
            "path": str(image_path),
            "metadata_json": json.dumps({"mime_type": "image/png"}),
            "created_at": "2026-05-06T00:00:00Z",
            "expires_at": None,
        }

    monkeypatch.setattr("koda.control_plane.manager.fetch_one", fake_fetch_one)

    artifact = manager.get_dashboard_runtime_artifact_for_download("KODA", 428)

    assert artifact is not None
    assert artifact["agent_id"] == "koda"
    assert artifact["path"] == str(image_path)
    assert artifact["metadata"]["mime_type"] == "image/png"
