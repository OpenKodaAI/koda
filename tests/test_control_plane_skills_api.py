from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest
from aiohttp import web

from koda.control_plane import api as control_plane_api


class _JsonRequest:
    def __init__(
        self,
        payload: dict[str, Any] | None = None,
        *,
        match_info: dict[str, str] | None = None,
    ) -> None:
        self.match_info = match_info or {"agent_id": "KODA", "package_id": "safe_pack"}
        self.query: dict[str, str] = {}
        self._payload = payload or {}
        self.headers: dict[str, str] = {}
        self.can_read_body = True

    async def json(self) -> dict[str, Any]:
        return self._payload


def test_skill_registry_and_eval_routes_are_registered() -> None:
    app = web.Application()
    control_plane_api.setup_control_plane_routes(app)

    routes = {(route.method, route.resource.canonical) for route in app.router.routes()}

    assert ("GET", "/api/control-plane/agents/{agent_id}/skills/registry") in routes
    assert (
        "POST",
        "/api/control-plane/agents/{agent_id}/skills/packages/{package_id}/evals/run",
    ) in routes


@pytest.mark.asyncio
async def test_skill_eval_run_route_returns_skill_eval_payload() -> None:
    expected = {
        "ok": True,
        "schema_version": "skill_eval.v1",
        "package_id": "safe_pack",
        "recommendation_status": "recommended",
    }
    request = _JsonRequest(match_info={"agent_id": "KODA", "package_id": "safe_pack"})

    with patch("koda.skills._package.run_skill_package_evals", return_value=expected) as runner:
        response = await control_plane_api.run_skill_package_evals_route(request)

    assert response.status == 201
    assert json.loads(response.text)["schema_version"] == "skill_eval.v1"
    runner.assert_called_once_with("KODA", "safe_pack")
