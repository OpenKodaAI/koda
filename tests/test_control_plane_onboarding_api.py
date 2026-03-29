"""Tests for public onboarding routes and OpenAPI exposure."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from aiohttp import web

from koda.control_plane import api as control_plane_api


class _Request:
    def __init__(
        self,
        *,
        query: dict[str, str] | None = None,
        payload: dict[str, object] | None = None,
    ) -> None:
        self.query = query or {}
        self.match_info: dict[str, str] = {}
        self.headers: dict[str, str] = {}
        self.can_read_body = payload is not None
        self._payload = payload or {}

    async def json(self) -> dict[str, object]:
        return dict(self._payload)


@pytest.mark.asyncio
async def test_setup_page_renders_token_free_ui() -> None:
    response = await control_plane_api.setup_page(_Request(query={"token": "bootstrap-token"}))

    assert response.content_type == "text/html"
    assert "Koda setup" in response.text
    assert "Infrastructure stays in" in response.text
    assert "/api/control-plane/onboarding/status" in response.text
    assert "bootstrap-token" not in response.text
    assert "localStorage" not in response.text


def test_control_plane_authorization_fails_closed_without_token() -> None:
    with patch.object(control_plane_api, "CONTROL_PLANE_API_TOKEN", ""):
        response = control_plane_api._authorize_request(_Request())

    assert response is not None
    assert response.status == 500
    assert json.loads(response.text) == {"error": "control plane token is not configured"}


@pytest.mark.asyncio
async def test_onboarding_status_route_proxies_manager_payload() -> None:
    manager = MagicMock()
    manager.get_onboarding_status.return_value = {"steps": {"onboarding_complete": False}}

    with patch("koda.control_plane.api._manager", return_value=manager):
        response = await control_plane_api.onboarding_status(_Request())

    assert json.loads(response.text) == {"steps": {"onboarding_complete": False}}


@pytest.mark.asyncio
async def test_onboarding_bootstrap_route_accepts_json_payload() -> None:
    manager = MagicMock()
    manager.complete_onboarding.return_value = {"ok": True}

    with patch("koda.control_plane.api._manager", return_value=manager):
        response = await control_plane_api.onboarding_bootstrap(
            _Request(payload={"provider": {"provider_id": "claude", "auth_mode": "api_key", "api_key": "test"}})
        )

    manager.complete_onboarding.assert_called_once()
    assert json.loads(response.text) == {"ok": True}


@pytest.mark.asyncio
async def test_control_plane_openapi_route_serves_spec() -> None:
    response = await control_plane_api.control_plane_openapi(_Request())
    payload = json.loads(response.text)
    assert payload["openapi"].startswith("3.")
    assert "/api/control-plane/onboarding/status" in payload["paths"]


def test_setup_control_plane_routes_registers_onboarding_surfaces() -> None:
    app = web.Application()
    control_plane_api.setup_control_plane_routes(app)
    canonicals = {route.resource.canonical for route in app.router.routes()}

    assert "/" in canonicals
    assert "/setup" in canonicals
    assert "/openapi/control-plane.json" in canonicals
    assert "/api/control-plane/onboarding/status" in canonicals
    assert "/api/control-plane/onboarding/bootstrap" in canonicals


def test_doctor_script_reports_expected_checks() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "doctor.py"
    spec = importlib.util.spec_from_file_location("doctor_script", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with (
        patch.object(module, "check_socket", return_value={"ok": True}),
        patch.object(module, "fetch_json", return_value={"status": "healthy"}),
    ):
        payload = module.run_doctor(
            env={
                "CONTROL_PLANE_PORT": "8090",
                "CONTROL_PLANE_API_TOKEN": "token",
                "RUNTIME_LOCAL_UI_TOKEN": "runtime",
                "KNOWLEDGE_V2_POSTGRES_DSN": "postgresql://user:pass@postgres:5432/koda",
                "KNOWLEDGE_V2_S3_ENDPOINT_URL": "http://seaweedfs:8333",
                "KNOWLEDGE_V2_S3_BUCKET": "koda-objects",
                "KNOWLEDGE_V2_S3_ACCESS_KEY_ID": "koda",
                "KNOWLEDGE_V2_S3_SECRET_ACCESS_KEY": "secret",
            },
            base_url="http://127.0.0.1:8090",
        )

    assert payload["ok"] is True
    assert payload["setup_url"].endswith("/setup")
