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
        body: bytes | None = None,
        content_type: str = "application/json",
    ) -> None:
        self.query = query or {}
        self.match_info: dict[str, str] = {}
        self.headers: dict[str, str] = {}
        self.can_read_body = payload is not None
        self._payload = payload or {}
        self._body = body or b""
        self.content_type = content_type

    async def json(self) -> dict[str, object]:
        return dict(self._payload)

    async def read(self) -> bytes:
        return self._body


@pytest.mark.asyncio
async def test_setup_page_renders_token_free_ui() -> None:
    response = await control_plane_api.setup_page(_Request(query={"token": "bootstrap-token"}))

    assert response.content_type == "text/html"
    assert "Configuration moved into the dashboard" in response.text
    assert "/control-plane" in response.text
    assert "/openapi/control-plane.json" in response.text
    assert "setup code" in response.text.lower()
    assert "bootstrap-token" not in response.text
    assert "localStorage" not in response.text


def test_control_plane_authorization_fails_closed_without_token() -> None:
    with patch("koda.control_plane.operator_auth.CONTROL_PLANE_API_TOKENS", []):
        response = control_plane_api._authorize_request(_Request())

    assert response is not None
    assert response.status == 401
    assert json.loads(response.text) == {"error": "operator session is required"}


@pytest.mark.asyncio
async def test_auth_profile_route_updates_display_name() -> None:
    auth_service = MagicMock()
    auth_service.update_profile.return_value = {
        "ok": True,
        "operator": {"id": "usr_1", "display_name": "Ryan"},
    }
    context = control_plane_api.OperatorAuthContext(
        auth_kind="session",
        subject_type="operator",
        user_id="usr_1",
        username="owner",
        email="owner@example.com",
        display_name="Owner",
    )

    with (
        patch("koda.control_plane.api._auth_service", return_value=auth_service),
        patch("koda.control_plane.api._require_auth_context", return_value=context),
    ):
        response = await control_plane_api.auth_update_profile(_Request(payload={"display_name": "Ryan"}))

    assert json.loads(response.text)["operator"]["display_name"] == "Ryan"
    auth_service.update_profile.assert_called_once_with(context, display_name="Ryan")


@pytest.mark.asyncio
async def test_auth_profile_photo_routes_cover_upload_get_delete() -> None:
    auth_service = MagicMock()
    auth_service.set_profile_photo.return_value = {
        "ok": True,
        "photoUrl": "/api/control-plane/auth/profile/photo?v=abc123",
        "photoHash": "abc123",
        "byteSize": 4,
        "operator": {"id": "usr_1", "profile_photo_hash": "abc123"},
    }
    auth_service.get_profile_photo.return_value = (b"jpeg", "abc123")
    auth_service.delete_profile_photo.return_value = {"ok": True, "removed": True, "operator": {"id": "usr_1"}}
    context = control_plane_api.OperatorAuthContext(
        auth_kind="session",
        subject_type="operator",
        user_id="usr_1",
        username="owner",
        email="owner@example.com",
        display_name="Owner",
    )

    with (
        patch("koda.control_plane.api._auth_service", return_value=auth_service),
        patch("koda.control_plane.api._require_auth_context", return_value=context),
    ):
        upload_response = await control_plane_api.auth_upload_profile_photo(
            _Request(body=b"jpeg", content_type="image/jpeg")
        )
        get_request = _Request(query={"v": "abc123"})
        get_response = await control_plane_api.auth_get_profile_photo(get_request)
        delete_response = await control_plane_api.auth_delete_profile_photo(_Request())

    assert upload_response.status == 201
    assert json.loads(upload_response.text)["photoHash"] == "abc123"
    auth_service.set_profile_photo.assert_called_once_with(context, raw=b"jpeg")
    assert get_response.status == 200
    assert get_response.headers["ETag"] == '"abc123"'
    assert get_response.headers["Cache-Control"] == "public, max-age=31536000, immutable"
    auth_service.get_profile_photo.assert_called_once_with(context, requested_hash="abc123")
    assert json.loads(delete_response.text)["removed"] is True
    auth_service.delete_profile_photo.assert_called_once_with(context)


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

    payload = json.loads(response.text)
    assert payload["steps"] == {"onboarding_complete": False}
    assert payload["has_owner"] is False
    assert payload["bootstrap_required"] is True
    assert payload["auth_mode"] == "local_account"
    assert payload["session_required"] is False
    assert payload["recovery_available"] is False


@pytest.mark.asyncio
async def test_onboarding_readiness_route_proxies_manager_payload() -> None:
    manager = MagicMock()
    manager.get_onboarding_readiness.return_value = {
        "schema_version": "onboarding_readiness.v1",
        "status": "pending",
        "checks": [],
        "summary": {"passed": 0, "warning": 0, "failed": 0, "pending": 1},
    }

    with patch("koda.control_plane.api._manager", return_value=manager):
        response = await control_plane_api.onboarding_readiness(_Request())

    payload = json.loads(response.text)
    assert payload["schema_version"] == "onboarding_readiness.v1"
    assert payload["status"] == "pending"


@pytest.mark.asyncio
async def test_onboarding_first_task_requires_operator_session() -> None:
    with patch("koda.control_plane.operator_auth.CONTROL_PLANE_API_TOKENS", []):
        response = await control_plane_api.onboarding_first_task(_Request(payload={}))

    assert response.status == 401


@pytest.mark.asyncio
async def test_onboarding_bootstrap_route_is_deprecated() -> None:
    """/api/control-plane/onboarding/bootstrap was removed — the setup wizard
    no longer bundles provider/agent setup into first-run. The endpoint must
    return 410 Gone with a helpful migration message."""
    response = await control_plane_api.onboarding_bootstrap(_Request(payload={}))
    assert response.status == 410
    body = json.loads(response.text)
    assert body["error"] == "onboarding_bootstrap_removed"
    assert "register-owner" in body["message"]


@pytest.mark.asyncio
async def test_control_plane_openapi_route_serves_spec() -> None:
    response = await control_plane_api.control_plane_openapi(_Request())
    payload = json.loads(response.text)
    assert payload["openapi"].startswith("3.")
    assert "/api/control-plane/onboarding/status" in payload["paths"]
    assert "/api/control-plane/onboarding/readiness" in payload["paths"]
    assert "/api/control-plane/onboarding/first-task" in payload["paths"]
    assert "/api/control-plane/agents/{agent_id}/channels/gateway" in payload["paths"]
    assert "/api/control-plane/connections/defaults/{connection_key}" in payload["paths"]


def test_setup_control_plane_routes_registers_onboarding_surfaces() -> None:
    app = web.Application()
    control_plane_api.setup_control_plane_routes(app)
    canonicals = {route.resource.canonical for route in app.router.routes()}

    assert "/" in canonicals
    assert "/setup" in canonicals
    assert "/openapi/control-plane.json" in canonicals
    assert "/api/control-plane/onboarding/status" in canonicals
    assert "/api/control-plane/onboarding/readiness" in canonicals
    assert "/api/control-plane/onboarding/first-task" in canonicals
    assert "/api/control-plane/onboarding/bootstrap" in canonicals
    assert "/api/control-plane/auth/status" in canonicals
    assert "/api/control-plane/auth/bootstrap/exchange" in canonicals
    assert "/api/control-plane/auth/bootstrap/codes" in canonicals
    assert "/api/control-plane/auth/register-owner" in canonicals
    assert "/api/control-plane/auth/login" in canonicals
    assert "/api/control-plane/auth/logout" in canonicals
    assert "/api/control-plane/auth/legacy/exchange" not in canonicals
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
    assert "/api/control-plane/agents/{agent_id}/channels/gateway" in canonicals
    assert "/api/control-plane/agents/{agent_id}/channels/gateway/pairing-codes" in canonicals
    assert "/api/control-plane/agents/{agent_id}/channels/gateway/unknown-senders" in canonicals
    assert "/api/control-plane/agents/{agent_id}/channels/gateway/identities/{identity_id}/approve" in canonicals
    assert "/api/control-plane/agents/{agent_id}/channels/gateway/identities/{identity_id}/block" in canonicals
    assert "/api/control-plane/agents/{agent_id}/channels/gateway/identities/{identity_id}" in canonicals


@pytest.mark.asyncio
async def test_channel_gateway_handlers_proxy_to_manager_methods() -> None:
    manager = MagicMock()
    manager.get_channel_gateway_state.return_value = {
        "schema_version": "channel_gateway.v1",
        "agent_id": "ATLAS",
        "identities": [],
        "unknown_senders": [],
        "pairing_codes": [],
    }
    manager.create_channel_gateway_pairing_code.return_value = {
        "schema_version": "channel_gateway.v1",
        "pairing_code_id": "chgpair_1",
        "code": "PAIR123",
    }
    manager.list_channel_gateway_unknown_senders.return_value = {"items": [{"identity_id": "chgid_1"}]}
    manager.approve_channel_gateway_identity.return_value = {"identity_id": "chgid_1", "status": "allowed"}
    manager.block_channel_gateway_identity.return_value = {"identity_id": "chgid_2", "status": "blocked"}
    manager.revoke_channel_gateway_identity.return_value = {"identity_id": "chgid_3", "status": "revoked"}

    with (
        patch("koda.control_plane.api._authorize_request", return_value=None),
        patch("koda.control_plane.api._resolve_owner_user_id", return_value="operator-1"),
        patch("koda.control_plane.api._manager", return_value=manager),
    ):
        state_request = _Request()
        state_request.match_info = {"agent_id": "ATLAS"}
        state_response = await control_plane_api.get_channel_gateway_route(state_request)

        pairing_request = _Request(payload={"ttl_seconds": 600})
        pairing_request.match_info = {"agent_id": "ATLAS"}
        pairing_response = await control_plane_api.create_channel_gateway_pairing_code_route(pairing_request)

        unknown_request = _Request()
        unknown_request.match_info = {"agent_id": "ATLAS"}
        unknown_response = await control_plane_api.list_channel_gateway_unknown_senders_route(unknown_request)

        approve_request = _Request(payload={"rationale": "known user"})
        approve_request.match_info = {"agent_id": "ATLAS", "identity_id": "chgid_1"}
        approve_response = await control_plane_api.approve_channel_gateway_identity_route(approve_request)

        block_request = _Request(payload={"rationale": "spam"})
        block_request.match_info = {"agent_id": "ATLAS", "identity_id": "chgid_2"}
        block_response = await control_plane_api.block_channel_gateway_identity_route(block_request)

        revoke_request = _Request(payload={"rationale": "left workspace"})
        revoke_request.match_info = {"agent_id": "ATLAS", "identity_id": "chgid_3"}
        revoke_response = await control_plane_api.revoke_channel_gateway_identity_route(revoke_request)

    manager.get_channel_gateway_state.assert_called_once_with("ATLAS")
    manager.create_channel_gateway_pairing_code.assert_called_once_with(
        "ATLAS",
        {"ttl_seconds": 600, "created_by": "operator-1"},
    )
    manager.list_channel_gateway_unknown_senders.assert_called_once_with("ATLAS")
    manager.approve_channel_gateway_identity.assert_called_once_with(
        "ATLAS",
        "chgid_1",
        {"rationale": "known user", "approved_by": "operator-1"},
    )
    manager.block_channel_gateway_identity.assert_called_once_with(
        "ATLAS",
        "chgid_2",
        {"rationale": "spam", "blocked_by": "operator-1"},
    )
    manager.revoke_channel_gateway_identity.assert_called_once_with(
        "ATLAS",
        "chgid_3",
        {"rationale": "left workspace", "revoked_by": "operator-1"},
    )

    assert json.loads(state_response.text)["schema_version"] == "channel_gateway.v1"
    assert pairing_response.status == 201
    assert json.loads(pairing_response.text)["code"] == "PAIR123"
    assert json.loads(unknown_response.text) == {"items": [{"identity_id": "chgid_1"}]}
    assert json.loads(approve_response.text)["status"] == "allowed"
    assert json.loads(block_response.text)["status"] == "blocked"
    assert json.loads(revoke_response.text)["status"] == "revoked"


@pytest.mark.asyncio
async def test_channel_gateway_missing_identity_returns_error_envelope() -> None:
    manager = MagicMock()
    manager.approve_channel_gateway_identity.side_effect = KeyError("chgid_missing")

    with (
        patch("koda.control_plane.api._authorize_request", return_value=None),
        patch("koda.control_plane.api._manager", return_value=manager),
    ):
        request = _Request(payload={})
        request.match_info = {"agent_id": "ATLAS", "identity_id": "chgid_missing"}
        response = await control_plane_api.approve_channel_gateway_identity_route(request)

    payload = json.loads(response.text)
    assert response.status == 404
    assert payload["error"]["code"] == "channel.identity_unknown"


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
    assert payload["legacy_setup_url"].endswith("/setup")


@pytest.mark.asyncio
async def test_connection_default_handlers_proxy_to_manager_methods() -> None:
    manager = MagicMock()
    manager.list_connection_catalog.return_value = {"items": [{"connection_key": "core:browser"}]}
    manager.list_connection_defaults.return_value = {"items": [{"connection_key": "core:browser"}]}
    manager.get_connection_default.return_value = {"connection_key": "core:browser", "status": "not_configured"}
    manager.put_connection_default.return_value = {"connection_key": "core:browser", "status": "configured"}
    manager.verify_connection_default.return_value = {
        "connection": {"connection_key": "core:browser", "status": "verified"},
        "verification": {"verified": True},
    }
    manager.delete_connection_default.return_value = {
        "connection": {"connection_key": "core:browser", "status": "not_configured"}
    }
    manager.set_integration_system_enabled.return_value = {
        "integration_id": "browser",
        "enabled": True,
        "connection": {"connection_key": "core:browser", "status": "not_configured"},
    }

    with patch("koda.control_plane.api._manager", return_value=manager):
        catalog_response = await control_plane_api.list_connection_catalog(_Request())

        defaults_response = await control_plane_api.list_connection_defaults_route(_Request())

        get_request = _Request()
        get_request.match_info = {"connection_key": "core:browser"}
        get_response = await control_plane_api.get_connection_default_route(get_request)

        put_request = _Request(payload={"fields": []})
        put_request.match_info = {"connection_key": "core:browser"}
        put_response = await control_plane_api.put_connection_default_route(put_request)

        verify_request = _Request()
        verify_request.match_info = {"connection_key": "core:browser"}
        verify_response = await control_plane_api.verify_connection_default_route(verify_request)

        disconnect_request = _Request()
        disconnect_request.match_info = {"connection_key": "core:browser"}
        disconnect_response = await control_plane_api.delete_connection_default_route(disconnect_request)

        system_request = _Request(payload={"enabled": True})
        system_request.match_info = {"integration_id": "browser"}
        system_response = await control_plane_api.set_integration_system_enabled(system_request)

    manager.list_connection_catalog.assert_called_once_with()
    manager.list_connection_defaults.assert_called_once_with()
    manager.get_connection_default.assert_called_once_with("core:browser")
    manager.put_connection_default.assert_called_once_with(
        "core:browser",
        {"fields": []},
    )
    manager.verify_connection_default.assert_called_once_with("core:browser")
    manager.delete_connection_default.assert_called_once_with("core:browser")
    manager.set_integration_system_enabled.assert_called_once_with("browser", True)

    assert json.loads(catalog_response.text) == {"items": [{"connection_key": "core:browser"}]}
    assert json.loads(defaults_response.text) == {"items": [{"connection_key": "core:browser"}]}
    assert json.loads(get_response.text) == {"connection_key": "core:browser", "status": "not_configured"}
    assert json.loads(put_response.text) == {"connection_key": "core:browser", "status": "configured"}
    assert json.loads(verify_response.text)["verification"] == {"verified": True}
    assert json.loads(disconnect_response.text) == {
        "connection": {"connection_key": "core:browser", "status": "not_configured"}
    }
    assert json.loads(system_response.text)["enabled"] is True


@pytest.mark.asyncio
async def test_agent_connection_handlers_proxy_to_manager_methods() -> None:
    manager = MagicMock()
    manager.list_agent_connections.return_value = {"items": [{"connection_key": "mcp:atlassian"}]}
    manager.get_agent_connection.return_value = {
        "connection_key": "mcp:atlassian",
        "status": "configured",
        "source_origin": "agent_binding",
    }
    manager.put_agent_connection.return_value = {
        "connection_key": "mcp:atlassian",
        "status": "configured",
        "source_origin": "agent_binding",
    }
    manager.verify_agent_connection.return_value = {
        "connection": {"connection_key": "mcp:atlassian", "status": "verified"},
        "verification": {"verified": True},
    }
    manager.delete_agent_connection.return_value = {
        "connection": {"connection_key": "mcp:atlassian", "status": "not_configured"}
    }
    manager.import_agent_connection_default.return_value = {
        "connection": {
            "connection_key": "mcp:atlassian",
            "status": "configured",
            "source_origin": "imported_default",
        }
    }

    with patch("koda.control_plane.api._manager", return_value=manager):
        list_request = _Request()
        list_request.match_info = {"agent_id": "ATLAS"}
        list_response = await control_plane_api.list_agent_connections_route(list_request)

        get_request = _Request()
        get_request.match_info = {"agent_id": "ATLAS", "connection_key": "mcp:atlassian"}
        get_response = await control_plane_api.get_agent_connection_route(get_request)

        put_request = _Request(payload={"auth_method": "api_token", "fields": []})
        put_request.match_info = {"agent_id": "ATLAS", "connection_key": "mcp:atlassian"}
        put_response = await control_plane_api.put_agent_connection_route(put_request)

        verify_request = _Request()
        verify_request.match_info = {"agent_id": "ATLAS", "connection_key": "mcp:atlassian"}
        verify_response = await control_plane_api.verify_agent_connection_route(verify_request)

        delete_request = _Request()
        delete_request.match_info = {"agent_id": "ATLAS", "connection_key": "mcp:atlassian"}
        delete_response = await control_plane_api.delete_agent_connection_route(delete_request)

        import_request = _Request()
        import_request.match_info = {"agent_id": "ATLAS", "connection_key": "mcp:atlassian"}
        import_response = await control_plane_api.import_agent_connection_default_route(import_request)

    manager.list_agent_connections.assert_called_once_with("ATLAS")
    manager.get_agent_connection.assert_called_once_with("ATLAS", "mcp:atlassian")
    manager.put_agent_connection.assert_called_once_with(
        "ATLAS",
        "mcp:atlassian",
        {"auth_method": "api_token", "fields": []},
    )
    manager.verify_agent_connection.assert_called_once_with("ATLAS", "mcp:atlassian")
    manager.delete_agent_connection.assert_called_once_with("ATLAS", "mcp:atlassian")
    manager.import_agent_connection_default.assert_called_once_with("ATLAS", "mcp:atlassian")

    assert json.loads(list_response.text) == {"items": [{"connection_key": "mcp:atlassian"}]}
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
