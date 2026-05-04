"""Focused tests for dashboard session API handlers."""

from __future__ import annotations

import json
from typing import Any

import pytest


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
