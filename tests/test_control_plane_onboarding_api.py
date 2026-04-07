"""Tests for public onboarding routes and OpenAPI exposure."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web

from koda.control_plane import api as control_plane_api
from koda.control_plane.operator_auth import OperatorAuthContext


class _Request:
    def __init__(
        self,
        *,
        path: str = "/",
        query: dict[str, str] | None = None,
        payload: dict[str, object] | None = None,
        query_string: str = "",
    ) -> None:
        self.path = path
        self.query = query or {}
        self.query_string = query_string
        self.match_info: dict[str, str] = {}
        self.headers: dict[str, str] = {}
        self.can_read_body = payload is not None
        self._payload = payload or {}
        self._state: dict[str, object] = {}

    async def json(self) -> dict[str, object]:
        return dict(self._payload)

    def __setitem__(self, key: str, value: object) -> None:
        self._state[key] = value

    def __getitem__(self, key: str) -> object:
        return self._state[key]

    def get(self, key: str, default: object | None = None) -> object | None:
        return self._state.get(key, default)


@pytest.mark.asyncio
async def test_setup_page_renders_token_free_ui() -> None:
    response = await control_plane_api.setup_page(_Request(query={"token": "bootstrap-token"}))

    assert response.content_type == "text/html"
    assert "Configuration moved into the dashboard" in response.text
    assert "/control-plane/setup" in response.text
    assert "/openapi/control-plane.json" in response.text
    assert "setup code" in response.text.lower()
    assert "bootstrap-token" not in response.text
    assert "localStorage" not in response.text


def test_public_control_plane_paths_match_exact_and_nested_routes() -> None:
    assert control_plane_api._is_public_control_plane_api_path("/api/control-plane/auth/login")
    assert control_plane_api._is_public_control_plane_api_path("/api/control-plane/auth/login/poll")
    assert not control_plane_api._is_public_control_plane_api_path("/api/control-plane/auth/tokens")


def test_control_plane_authorization_fails_closed_without_token() -> None:
    with (
        patch.object(control_plane_api, "CONTROL_PLANE_AUTH_MODE", "token"),
        patch("koda.control_plane.operator_auth.CONTROL_PLANE_API_TOKENS", []),
    ):
        response = control_plane_api._authorize_request(_Request())

    assert response is not None
    assert response.status == 401
    assert json.loads(response.text) == {"error": "operator session is required"}


@pytest.mark.asyncio
async def test_control_plane_auth_middleware_allows_public_auth_path_without_session() -> None:
    request = _Request(path="/api/control-plane/auth/login")
    handler = AsyncMock(return_value=web.json_response({"ok": True}))

    with patch.object(control_plane_api, "CONTROL_PLANE_AUTH_MODE", "token"):
        response = await control_plane_api.control_plane_auth_middleware(request, handler)

    handler.assert_awaited_once_with(request)
    assert request.get("operator_auth") is None
    assert json.loads(response.text) == {"ok": True}


@pytest.mark.asyncio
async def test_control_plane_auth_middleware_attaches_context_on_public_auth_path() -> None:
    request = _Request(path="/api/control-plane/auth/status")
    request.headers = {"Authorization": "Bearer operator-token"}
    context = OperatorAuthContext(
        auth_kind="token",
        subject_type="personal_token",
        user_id="op_123",
        username="atlas",
        email="atlas@example.com",
        display_name="Atlas",
    )
    auth_service = MagicMock()
    auth_service.resolve_bearer_token.return_value = context
    handler = AsyncMock(return_value=web.json_response({"ok": True}))

    with (
        patch.object(control_plane_api, "CONTROL_PLANE_AUTH_MODE", "token"),
        patch("koda.control_plane.api._auth_service", return_value=auth_service),
    ):
        response = await control_plane_api.control_plane_auth_middleware(request, handler)

    handler.assert_awaited_once_with(request)
    assert request.get("operator_auth") == context
    assert json.loads(response.text) == {"ok": True}


@pytest.mark.asyncio
async def test_control_plane_auth_middleware_rejects_protected_path_without_session() -> None:
    request = _Request(path="/api/control-plane/auth/tokens")
    handler = AsyncMock(return_value=web.json_response({"ok": True}))

    with patch.object(control_plane_api, "CONTROL_PLANE_AUTH_MODE", "token"):
        response = await control_plane_api.control_plane_auth_middleware(request, handler)

    handler.assert_not_awaited()
    assert response.status == 401
    assert json.loads(response.text) == {"error": "operator session is required"}


@pytest.mark.asyncio
async def test_control_plane_auth_middleware_injects_development_context() -> None:
    request = _Request(path="/api/control-plane/auth/tokens")

    async def handler(inner_request: _Request) -> web.Response:
        context = inner_request.get("operator_auth")
        assert isinstance(context, OperatorAuthContext)
        assert context.auth_kind == "development"
        assert context.username == "dev"
        return web.json_response({"ok": True})

    with (
        patch.object(control_plane_api, "CONTROL_PLANE_AUTH_MODE", "development"),
        patch.dict("os.environ", {"NODE_ENV": "development"}, clear=False),
    ):
        response = await control_plane_api.control_plane_auth_middleware(request, handler)

    assert json.loads(response.text) == {"ok": True}


@pytest.mark.asyncio
async def test_onboarding_status_route_proxies_manager_payload() -> None:
    manager = MagicMock()
    manager.get_onboarding_status.return_value = {"steps": {"onboarding_complete": False}}
    auth_service = MagicMock()
    auth_service.onboarding_payload.return_value = {
        "has_owner": False,
        "bootstrap_required": True,
        "auth_mode": "local_account",
        "session_required": False,
        "recovery_available": False,
    }

    with (
        patch("koda.control_plane.api._manager", return_value=manager),
        patch("koda.control_plane.api._auth_service", return_value=auth_service),
    ):
        response = await control_plane_api.onboarding_status(_Request())

    assert json.loads(response.text) == {
        "steps": {"onboarding_complete": False},
        "has_owner": False,
        "bootstrap_required": True,
        "auth_mode": "local_account",
        "session_required": False,
        "recovery_available": False,
    }


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
async def test_auth_issue_bootstrap_code_uses_operator_user_id_as_actor() -> None:
    auth_service = MagicMock()
    auth_service.resolve_bearer_token.return_value = OperatorAuthContext(
        auth_kind="token",
        subject_type="session",
        user_id="op_123",
        username="atlas",
        email="atlas@example.com",
        display_name="Atlas",
    )
    auth_service.issue_bootstrap_code.return_value = {"ok": True, "code": "ABCD-EFGH-IJKL"}
    request = _Request(payload={"label": "desktop"})
    request.headers = {"Authorization": "Bearer operator-token"}

    with patch("koda.control_plane.api._auth_service", return_value=auth_service):
        response = await control_plane_api.auth_issue_bootstrap_code(request)

    auth_service.issue_bootstrap_code.assert_called_once_with(label="desktop", actor="op_123")
    assert response.status == 201
    assert json.loads(response.text)["ok"] is True


@pytest.mark.asyncio
async def test_control_plane_openapi_route_serves_spec() -> None:
    response = await control_plane_api.control_plane_openapi(_Request())
    payload = json.loads(response.text)
    assert payload["openapi"].startswith("3.")
    assert "/api/control-plane/onboarding/status" in payload["paths"]
    assert "/api/control-plane/connections/defaults/{connection_key}" in payload["paths"]


def test_setup_control_plane_routes_registers_onboarding_surfaces() -> None:
    app = web.Application()
    control_plane_api.setup_control_plane_routes(app)
    canonicals = {route.resource.canonical for route in app.router.routes()}

    assert "/" in canonicals
    assert "/setup" in canonicals
    assert "/openapi/control-plane.json" in canonicals
    assert "/api/control-plane/onboarding/status" in canonicals
    assert "/api/control-plane/onboarding/bootstrap" in canonicals
    assert "/api/control-plane/auth/status" in canonicals
    assert "/api/control-plane/auth/bootstrap/exchange" in canonicals
    assert "/api/control-plane/auth/bootstrap/codes" in canonicals
    assert "/api/control-plane/auth/register-owner" in canonicals
    assert "/api/control-plane/auth/login" in canonicals
    assert "/api/control-plane/auth/logout" in canonicals
    assert "/api/control-plane/auth/legacy/exchange" in canonicals
    assert "/api/control-plane/auth/tokens" in canonicals
    assert "/api/control-plane/auth/tokens/{token_id}" in canonicals
    assert "/api/control-plane/auth/sessions" in canonicals
    assert "/api/control-plane/auth/sessions/{session_id}" in canonicals
    assert "/api/control-plane/connections/catalog" in canonicals
    assert "/api/control-plane/connections/defaults" in canonicals
    assert "/api/control-plane/connections/defaults/{connection_key}" in canonicals
    assert "/api/control-plane/connections/defaults/{connection_key}/verify" in canonicals
    assert "/api/control-plane/integrations/{integration_id}/system" in canonicals
    assert "/api/control-plane/integrations/{integration_id}/health" in canonicals


@pytest.mark.asyncio
async def test_setup_landing_redirects_to_setup_page() -> None:
    with pytest.raises(web.HTTPFound) as exc_info:
        await control_plane_api.setup_landing(_Request())

    assert exc_info.value.location == "/setup"


def test_doctor_script_reports_expected_checks() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "doctor.py"
    spec = importlib.util.spec_from_file_location("doctor_script", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with (
        patch.object(module, "check_socket", return_value={"ok": True}),
        patch.object(module, "fetch_json", return_value={"status": "healthy"}),
        patch.object(module, "fetch_status", return_value={"status": 200, "content_type": "text/html"}),
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
    assert payload["dashboard_setup_url"].endswith("/control-plane/setup")
    assert payload["legacy_setup_url"].endswith("/setup")


@pytest.mark.asyncio
async def test_connection_default_handlers_proxy_to_manager_methods() -> None:
    manager = MagicMock()
    manager.list_connection_catalog.return_value = {"items": [{"connection_key": "core:jira"}]}
    manager.list_connection_defaults.return_value = {"items": [{"connection_key": "core:jira"}]}
    manager.get_connection_default.return_value = {"connection_key": "core:jira", "status": "not_configured"}
    manager.put_connection_default.return_value = {"connection_key": "core:jira", "status": "configured"}
    manager.verify_connection_default.return_value = {
        "connection": {"connection_key": "core:jira", "status": "verified"},
        "verification": {"verified": True},
    }
    manager.delete_connection_default.return_value = {
        "connection": {"connection_key": "core:jira", "status": "not_configured"}
    }
    manager.set_integration_system_enabled.return_value = {
        "integration_id": "jira",
        "enabled": True,
        "connection": {"connection_key": "core:jira", "status": "not_configured"},
    }

    with patch("koda.control_plane.api._manager", return_value=manager):
        catalog_response = await control_plane_api.list_connection_catalog(_Request())

        defaults_response = await control_plane_api.list_connection_defaults_route(_Request())

        get_request = _Request()
        get_request.match_info = {"connection_key": "core:jira"}
        get_response = await control_plane_api.get_connection_default_route(get_request)

        put_request = _Request(payload={"fields": [{"key": "JIRA_URL", "value": "https://example.atlassian.net"}]})
        put_request.match_info = {"connection_key": "core:jira"}
        put_response = await control_plane_api.put_connection_default_route(put_request)

        verify_request = _Request()
        verify_request.match_info = {"connection_key": "core:jira"}
        verify_response = await control_plane_api.verify_connection_default_route(verify_request)

        disconnect_request = _Request()
        disconnect_request.match_info = {"connection_key": "core:jira"}
        disconnect_response = await control_plane_api.delete_connection_default_route(disconnect_request)

        system_request = _Request(payload={"enabled": True})
        system_request.match_info = {"integration_id": "jira"}
        system_response = await control_plane_api.set_integration_system_enabled(system_request)

    manager.list_connection_catalog.assert_called_once_with()
    manager.list_connection_defaults.assert_called_once_with()
    manager.get_connection_default.assert_called_once_with("core:jira")
    manager.put_connection_default.assert_called_once_with(
        "core:jira",
        {"fields": [{"key": "JIRA_URL", "value": "https://example.atlassian.net"}]},
    )
    manager.verify_connection_default.assert_called_once_with("core:jira")
    manager.delete_connection_default.assert_called_once_with("core:jira")
    manager.set_integration_system_enabled.assert_called_once_with("jira", True)

    assert json.loads(catalog_response.text) == {"items": [{"connection_key": "core:jira"}]}
    assert json.loads(defaults_response.text) == {"items": [{"connection_key": "core:jira"}]}
    assert json.loads(get_response.text) == {"connection_key": "core:jira", "status": "not_configured"}
    assert json.loads(put_response.text) == {"connection_key": "core:jira", "status": "configured"}
    assert json.loads(verify_response.text)["verification"] == {"verified": True}
    assert json.loads(disconnect_response.text) == {
        "connection": {"connection_key": "core:jira", "status": "not_configured"}
    }
    assert json.loads(system_response.text)["enabled"] is True


@pytest.mark.asyncio
async def test_agent_connection_handlers_proxy_to_manager_methods() -> None:
    manager = MagicMock()
    manager.list_agent_connections.return_value = {"items": [{"connection_key": "core:jira"}]}
    manager.get_agent_connection.return_value = {
        "connection_key": "core:jira",
        "status": "configured",
        "source_origin": "agent_binding",
    }
    manager.put_agent_connection.return_value = {
        "connection_key": "core:jira",
        "status": "configured",
        "source_origin": "agent_binding",
    }
    manager.verify_agent_connection.return_value = {
        "connection": {"connection_key": "core:jira", "status": "verified"},
        "verification": {"verified": True},
    }
    manager.delete_agent_connection.return_value = {
        "connection": {"connection_key": "core:jira", "status": "not_configured"}
    }
    manager.import_agent_connection_default.return_value = {
        "connection": {
            "connection_key": "core:jira",
            "status": "configured",
            "source_origin": "imported_default",
        }
    }

    with patch("koda.control_plane.api._manager", return_value=manager):
        list_request = _Request()
        list_request.match_info = {"agent_id": "ATLAS"}
        list_response = await control_plane_api.list_agent_connections_route(list_request)

        get_request = _Request()
        get_request.match_info = {"agent_id": "ATLAS", "connection_key": "core:jira"}
        get_response = await control_plane_api.get_agent_connection_route(get_request)

        put_request = _Request(payload={"auth_method": "api_token", "fields": []})
        put_request.match_info = {"agent_id": "ATLAS", "connection_key": "core:jira"}
        put_response = await control_plane_api.put_agent_connection_route(put_request)

        verify_request = _Request()
        verify_request.match_info = {"agent_id": "ATLAS", "connection_key": "core:jira"}
        verify_response = await control_plane_api.verify_agent_connection_route(verify_request)

        delete_request = _Request()
        delete_request.match_info = {"agent_id": "ATLAS", "connection_key": "core:jira"}
        delete_response = await control_plane_api.delete_agent_connection_route(delete_request)

        import_request = _Request()
        import_request.match_info = {"agent_id": "ATLAS", "connection_key": "core:jira"}
        import_response = await control_plane_api.import_agent_connection_default_route(import_request)

    manager.list_agent_connections.assert_called_once_with("ATLAS")
    manager.get_agent_connection.assert_called_once_with("ATLAS", "core:jira")
    manager.put_agent_connection.assert_called_once_with(
        "ATLAS",
        "core:jira",
        {"auth_method": "api_token", "fields": []},
    )
    manager.verify_agent_connection.assert_called_once_with("ATLAS", "core:jira")
    manager.delete_agent_connection.assert_called_once_with("ATLAS", "core:jira")
    manager.import_agent_connection_default.assert_called_once_with("ATLAS", "core:jira")

    assert json.loads(list_response.text) == {"items": [{"connection_key": "core:jira"}]}
    assert json.loads(get_response.text)["source_origin"] == "agent_binding"
    assert json.loads(put_response.text)["status"] == "configured"
    assert json.loads(verify_response.text)["verification"] == {"verified": True}
    assert json.loads(delete_response.text)["connection"]["status"] == "not_configured"
    assert json.loads(import_response.text)["connection"]["source_origin"] == "imported_default"


@pytest.mark.asyncio
async def test_mcp_oauth_routes_cover_start_callback_refresh_revoke_and_status() -> None:
    manager = MagicMock()
    manager.get_oauth_token_status.return_value = {
        "connected": True,
        "auth_method": "oauth",
        "account_label": "Workspace",
    }

    async def fake_start(agent_id: str, server_key: str, frontend_callback_uri: str, redirect_uri: str):
        return {
            "session_id": "sess-1",
            "authorization_url": "https://linear.example.com/oauth/authorize",
            "agent_id": agent_id,
            "server_key": server_key,
            "frontend_callback_uri": frontend_callback_uri,
            "redirect_uri": redirect_uri,
        }

    async def fake_callback(state: str, code: str, error: str | None = None):
        if error:
            return {"success": False, "error": error, "frontend_callback_uri": "https://app.example.com/oauth/callback"}
        return {
            "success": True,
            "server_key": "linear",
            "agent_id": "ATLAS",
            "frontend_callback_uri": "https://app.example.com/oauth/callback",
        }

    async def fake_refresh(agent_id: str, server_key: str):
        return {"success": True, "agent_id": agent_id, "server_key": server_key}

    async def fake_revoke(agent_id: str, server_key: str):
        return {"success": True, "agent_id": agent_id, "server_key": server_key}

    with (
        patch("koda.control_plane.api._manager", return_value=manager),
        patch("koda.services.mcp_oauth.start_oauth_flow", side_effect=fake_start),
        patch("koda.services.mcp_oauth.handle_oauth_callback", side_effect=fake_callback),
        patch("koda.services.mcp_oauth.refresh_oauth_token", side_effect=fake_refresh),
        patch("koda.services.mcp_oauth.revoke_oauth_token", side_effect=fake_revoke),
    ):
        start_request = _Request(
            payload={
                "frontend_callback_uri": "https://app.example.com/oauth/callback",
                "redirect_uri": "https://app.example.com/oauth/callback",
            }
        )
        start_request.match_info = {"agent_id": "ATLAS", "connection_key": "mcp:linear"}
        start_response = await control_plane_api.start_oauth_flow_route(start_request)

        callback_request = _Request()
        callback_request.headers = {"Accept": "application/json"}
        callback_request.query = {"state": "state-1", "code": "code-1", "mode": "json"}
        callback_response = await control_plane_api.handle_oauth_callback_route(callback_request)

        refresh_request = _Request()
        refresh_request.match_info = {"agent_id": "ATLAS", "connection_key": "mcp:linear"}
        refresh_response = await control_plane_api.refresh_oauth_token_route(refresh_request)

        revoke_request = _Request()
        revoke_request.match_info = {"agent_id": "ATLAS", "connection_key": "mcp:linear"}
        revoke_response = await control_plane_api.revoke_oauth_token_route(revoke_request)

        status_request = _Request()
        status_request.match_info = {"agent_id": "ATLAS", "connection_key": "mcp:linear"}
        status_response = await control_plane_api.get_oauth_status_route(status_request)

    manager.get_oauth_token_status.assert_called_once_with("ATLAS", "linear")

    assert start_response.status == 201
    assert json.loads(start_response.text)["authorization_url"] == "https://linear.example.com/oauth/authorize"
    assert json.loads(callback_response.text)["success"] is True
    assert json.loads(refresh_response.text) == {"success": True, "agent_id": "ATLAS", "server_key": "linear"}
    assert json.loads(revoke_response.text) == {"success": True, "agent_id": "ATLAS", "server_key": "linear"}
    assert json.loads(status_response.text)["connected"] is True


@pytest.mark.asyncio
async def test_oauth_callback_redirect_validates_frontend_target_and_preserves_query() -> None:
    async def fake_callback(state: str, code: str, error: str | None = None):
        assert state == "state-1"
        assert code == "code-1"
        assert error is None
        return {
            "success": True,
            "server_key": "linear",
            "agent_id": "ATLAS",
            "frontend_callback_uri": "https://app.example.com/oauth/callback?existing=1",
        }

    with (
        patch.dict("os.environ", {"MCP_OAUTH_CALLBACK_BASE_URL": "https://app.example.com"}, clear=False),
        patch("koda.services.mcp_oauth.handle_oauth_callback", side_effect=fake_callback),
    ):
        request = _Request(query={"state": "state-1", "code": "code-1"})

        with pytest.raises(web.HTTPFound) as exc_info:
            await control_plane_api.handle_oauth_callback_route(request)

    assert exc_info.value.location.startswith("https://app.example.com/oauth/callback?existing=1")
    assert "status=success" in exc_info.value.location
    assert "server_key=linear" in exc_info.value.location
    assert "agent_id=ATLAS" in exc_info.value.location


@pytest.mark.asyncio
async def test_oauth_callback_invalid_frontend_target_returns_json_payload() -> None:
    async def fake_callback(state: str, code: str, error: str | None = None):
        return {
            "success": False,
            "error": "token_exchange_failed",
            "frontend_callback_uri": "javascript:alert(1)",
        }

    with patch("koda.services.mcp_oauth.handle_oauth_callback", side_effect=fake_callback):
        request = _Request(query={"state": "state-1", "code": "code-1"})
        response = await control_plane_api.handle_oauth_callback_route(request)

    assert response.status == 400
    assert json.loads(response.text) == {
        "success": False,
        "error": "token_exchange_failed",
        "frontend_callback_uri": "javascript:alert(1)",
    }


@pytest.mark.asyncio
async def test_oauth_relay_handler_hides_internal_exception_details() -> None:
    request = _Request(query_string="code=abc")
    request.match_info = {"session_id": "session-1"}

    with (
        patch("koda.services.provider_auth.get_oauth_relay_target", return_value="http://127.0.0.1:4318/callback"),
        patch("aiohttp.ClientSession", side_effect=RuntimeError("socket refused on 127.0.0.1:4318")),
    ):
        response = await control_plane_api.oauth_relay_handler(request)

    assert response.status == 502
    assert response.text == "Failed to reach CLI auth server."
    assert "127.0.0.1" not in response.text


@pytest.mark.asyncio
async def test_oauth_relay_handler_returns_generic_success_page() -> None:
    class _FakeResponse:
        status = 200
        content_type = "text/html"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def read(self) -> bytes:
            return b"<html>internal success page with stack trace details</html>"

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def get(self, *args, **kwargs):
            return _FakeResponse()

    request = _Request(query_string="code=abc")
    request.match_info = {"session_id": "session-1"}

    with (
        patch("koda.services.provider_auth.get_oauth_relay_target", return_value="http://127.0.0.1:4318/callback"),
        patch("koda.services.provider_auth.clear_oauth_relay_target") as clear_target,
        patch("aiohttp.ClientSession", return_value=_FakeSession()),
    ):
        response = await control_plane_api.oauth_relay_handler(request)

    assert response.status == 200
    assert response.content_type == "text/html"
    assert "Authentication complete" in response.text
    assert "stack trace" not in response.text
    clear_target.assert_called_once_with("session-1")
