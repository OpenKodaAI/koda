"""Focused tests for MCP OAuth flow orchestration."""

from __future__ import annotations

import json
import urllib.parse

import pytest


def test_parse_www_authenticate_resource_metadata() -> None:
    from koda.services import mcp_oauth as oauth_mod

    parsed = oauth_mod._parse_www_authenticate_header(
        'Bearer realm="mcp", resource_metadata="https://mcp.example.com/.well-known/oauth-protected-resource/mcp"'
    )

    assert parsed["scheme"] == "Bearer"
    assert parsed["realm"] == "mcp"
    assert parsed["resource_metadata"] == "https://mcp.example.com/.well-known/oauth-protected-resource/mcp"


def test_protected_resource_metadata_candidates_include_path_before_root() -> None:
    from koda.services import mcp_oauth as oauth_mod

    row = {"remote_url": "https://mcp.supabase.com/mcp", "metadata_json": "{}"}

    assert oauth_mod._protected_resource_metadata_candidates(row) == [
        "https://mcp.supabase.com/.well-known/oauth-protected-resource/mcp",
        "https://mcp.supabase.com/.well-known/oauth-protected-resource",
    ]


def test_authorization_server_metadata_candidates_support_path_issuers() -> None:
    from koda.services import mcp_oauth as oauth_mod

    candidates = oauth_mod._authorization_server_metadata_candidates("https://github.com/login/oauth")

    assert candidates[0] == "https://github.com/.well-known/oauth-authorization-server/login/oauth"
    assert "https://github.com/.well-known/openid-configuration/login/oauth" in candidates


@pytest.mark.asyncio
async def test_discover_oauth_metadata_follows_protected_resource_metadata(monkeypatch):
    from koda.services import mcp_oauth as oauth_mod

    seen: list[str] = []
    row = {
        "server_key": "supabase",
        "remote_url": "https://mcp.supabase.com/mcp",
        "url": "https://mcp.supabase.com/mcp",
        "oauth_metadata_url": "",
        "metadata_json": "{}",
    }

    async def fake_www_authenticate(_remote_url: str) -> str:
        return 'Bearer resource_metadata="https://mcp.supabase.com/.well-known/oauth-protected-resource/mcp"'

    async def fake_fetch_json(candidate: str):
        seen.append(candidate)
        if candidate.endswith("/oauth-protected-resource/mcp"):
            return {
                "resource": "https://mcp.supabase.com/mcp",
                "authorization_servers": ["https://api.supabase.com"],
                "bearer_methods_supported": ["header"],
                "scopes_supported": ["read", "write"],
            }
        if candidate == "https://api.supabase.com/.well-known/oauth-authorization-server":
            return {
                "authorization_endpoint": "https://api.supabase.com/oauth/authorize",
                "token_endpoint": "https://api.supabase.com/oauth/token",
                "registration_endpoint": "https://api.supabase.com/oauth/register",
                "code_challenge_methods_supported": ["S256"],
            }
        raise RuntimeError(f"unexpected candidate: {candidate}")

    oauth_mod._OAUTH_DISCOVERY_CACHE.clear()
    monkeypatch.setattr(oauth_mod, "_fetch_www_authenticate_header", fake_www_authenticate)
    monkeypatch.setattr(oauth_mod, "_fetch_json_metadata", fake_fetch_json)

    metadata = await oauth_mod._discover_oauth_metadata(row)

    assert metadata["authorization_endpoint"] == "https://api.supabase.com/oauth/authorize"
    assert metadata["__resource"] == "https://mcp.supabase.com/mcp"
    assert metadata["__authorization_server"] == "https://api.supabase.com"
    assert seen[:2] == [
        "https://mcp.supabase.com/.well-known/oauth-protected-resource/mcp",
        "https://api.supabase.com/.well-known/oauth-authorization-server",
    ]


@pytest.mark.asyncio
async def test_start_oauth_flow_includes_resource_parameter(monkeypatch):
    from koda.services import mcp_oauth as oauth_mod

    executed: list[tuple[str, tuple[object, ...]]] = []

    async def fake_context(_server_key: str, redirect_uri: str):
        return {
            "server_key": "linear",
            "oauth_mode": "dcr",
            "authorization_url": "https://linear.example.com/oauth/authorize",
            "token_url": "https://linear.example.com/oauth/token",
            "redirect_uri": redirect_uri,
            "client_id": "client-123",
            "resource": "https://mcp.linear.app/mcp",
            "scopes": "read write",
        }

    monkeypatch.setattr(oauth_mod, "fetch_one", lambda query, params=(): {"id": "ATLAS"})
    monkeypatch.setattr(oauth_mod, "execute", lambda query, params=(): executed.append((query, params)))
    monkeypatch.setattr(oauth_mod, "now_iso", lambda: "2026-04-05T15:30:00+00:00")
    monkeypatch.setattr(oauth_mod, "_build_oauth_context", fake_context)

    result = await oauth_mod.start_oauth_flow(
        "ATLAS",
        "linear",
        "https://app.example.com/oauth/callback",
    )

    query = urllib.parse.parse_qs(urllib.parse.urlparse(result["authorization_url"]).query)
    assert query["resource"] == ["https://mcp.linear.app/mcp"]
    assert query["code_challenge_method"] == ["S256"]
    assert len(executed) == 1


@pytest.mark.asyncio
async def test_handle_oauth_callback_rejects_invalid_or_expired_session(monkeypatch):
    from koda.services import mcp_oauth as oauth_mod

    monkeypatch.setattr(oauth_mod, "fetch_one", lambda query, params=(): None)

    result = await oauth_mod.handle_oauth_callback("state-1", "code-1")

    assert result == {"success": False, "error": "invalid_or_expired_session"}


@pytest.mark.asyncio
async def test_handle_oauth_callback_persists_tokens_and_marks_connection(monkeypatch):
    from koda.services import mcp_oauth as oauth_mod

    executed: list[tuple[str, tuple[object, ...]]] = []
    status_updates: list[tuple[str, str, str | None]] = []
    cleanup_calls: list[tuple[str, str]] = []
    mark_calls: list[tuple[str, str]] = []
    token_payloads: list[dict[str, str]] = []

    session_row = {
        "session_id": "sess-1",
        "agent_id": "ATLAS",
        "server_key": "linear",
        "redirect_uri": "https://app.example.com/oauth/callback",
        "frontend_callback_uri": "https://app.example.com/oauth/callback",
        "code_verifier": "verifier-123",
        "oauth_context_json": json.dumps(
            {
                "client_id": "client-123",
                "token_url": "https://linear.example.com/oauth/token",
                "scopes": "read write",
                "resource": "https://mcp.linear.app/mcp",
            }
        ),
        "expires_at": "2099-01-01T00:00:00+00:00",
    }

    def fake_fetch_one(query, params=()):
        if "FROM cp_mcp_oauth_sessions" in query:
            return session_row
        raise AssertionError(f"Unexpected fetch_one query: {query}")

    monkeypatch.setattr(oauth_mod, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(oauth_mod, "execute", lambda query, params=(): executed.append((query, params)))
    monkeypatch.setattr(oauth_mod, "encrypt_secret", lambda value: f"enc:{value}")
    monkeypatch.setattr(oauth_mod, "_compute_expires_at", lambda expires_in: "2026-04-05T18:00:00+00:00")
    monkeypatch.setattr(oauth_mod, "now_iso", lambda: "2026-04-05T15:30:00+00:00")
    monkeypatch.setattr(
        oauth_mod,
        "_sync_http_post_form",
        lambda url, data, headers=None: (
            token_payloads.append(dict(data))
            or {
                "access_token": "access-123",
                "refresh_token": "refresh-456",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "read write",
                "provider_account_id": "acct-1",
                "account_label": "Linear Workspace",
            }
        ),
    )
    monkeypatch.setattr(
        oauth_mod,
        "_update_session_status",
        lambda session_id, status, error_message=None: status_updates.append((session_id, status, error_message)),
    )
    monkeypatch.setattr(
        oauth_mod,
        "_cleanup_legacy_oauth_env_values",
        lambda agent_id, server_key: cleanup_calls.append((agent_id, server_key)),
    )
    monkeypatch.setattr(
        oauth_mod,
        "_mark_connection_as_oauth",
        lambda agent_id, server_key: mark_calls.append((agent_id, server_key)),
    )

    result = await oauth_mod.handle_oauth_callback("state-1", "code-1")

    assert result == {
        "success": True,
        "server_key": "linear",
        "agent_id": "ATLAS",
        "provider_account_id": "acct-1",
        "provider_account_label": "Linear Workspace",
        "frontend_callback_uri": "https://app.example.com/oauth/callback",
    }
    assert len(executed) == 1
    insert_query, insert_params = executed[0]
    assert "INSERT INTO cp_mcp_oauth_tokens" in insert_query
    assert insert_params[0:2] == ("ATLAS", "linear")
    assert insert_params[2] == "enc:access-123"
    assert insert_params[3] == "enc:refresh-456"
    assert insert_params[5] == "2026-04-05T18:00:00+00:00"
    assert insert_params[7] == "acct-1"
    assert insert_params[8] == "Linear Workspace"
    assert mark_calls == [("ATLAS", "linear")]
    assert cleanup_calls == [("ATLAS", "linear")]
    assert status_updates == [("sess-1", "completed", None)]
    assert token_payloads[0]["resource"] == "https://mcp.linear.app/mcp"


@pytest.mark.asyncio
async def test_refresh_oauth_token_updates_persisted_tokens(monkeypatch):
    from koda.services import mcp_oauth as oauth_mod

    executed: list[tuple[str, tuple[object, ...]]] = []
    token_payloads: list[dict[str, str]] = []

    token_row = {
        "refresh_token_encrypted": "enc:refresh-456",
        "oauth_context_json": json.dumps(
            {
                "client_id": "client-123",
                "token_url": "https://linear.example.com/oauth/token",
                "client_secret": "secret-xyz",
                "resource": "https://mcp.linear.app/mcp",
            }
        ),
    }

    monkeypatch.setattr(oauth_mod, "fetch_one", lambda query, params=(): token_row)
    monkeypatch.setattr(oauth_mod, "decrypt_secret", lambda value: "refresh-456")
    monkeypatch.setattr(oauth_mod, "encrypt_secret", lambda value: f"enc:{value}")
    monkeypatch.setattr(oauth_mod, "_compute_expires_at", lambda expires_in: "2026-04-05T18:30:00+00:00")
    monkeypatch.setattr(oauth_mod, "now_iso", lambda: "2026-04-05T15:35:00+00:00")
    monkeypatch.setattr(oauth_mod, "execute", lambda query, params=(): executed.append((query, params)))
    monkeypatch.setattr(
        oauth_mod,
        "_sync_http_post_form",
        lambda url, data, headers=None: (
            token_payloads.append(dict(data))
            or {
                "access_token": "access-789",
                "refresh_token": "refresh-999",
                "expires_in": 7200,
            }
        ),
    )

    result = await oauth_mod.refresh_oauth_token("ATLAS", "linear")

    assert result == {"success": True, "expires_at": "2026-04-05T18:30:00+00:00"}
    assert len(executed) == 1
    update_query, update_params = executed[0]
    assert "UPDATE cp_mcp_oauth_tokens" in update_query
    assert update_params[0] == "enc:access-789"
    assert update_params[1] == "enc:refresh-999"
    assert update_params[2] == "2026-04-05T18:30:00+00:00"
    assert update_params[5:7] == ("ATLAS", "linear")
    assert token_payloads[0]["resource"] == "https://mcp.linear.app/mcp"


@pytest.mark.asyncio
async def test_revoke_oauth_token_revokes_remote_token_and_clears_local_state(monkeypatch):
    from koda.services import mcp_oauth as oauth_mod

    executed: list[tuple[str, tuple[object, ...]]] = []
    revoked_payloads: list[tuple[str, dict[str, str], dict[str, str] | None]] = []
    cleanup_calls: list[tuple[str, str]] = []

    token_row = {
        "access_token_encrypted": "enc:access-123",
        "oauth_context_json": json.dumps(
            {
                "revocation_url": "https://linear.example.com/oauth/revoke",
                "client_id": "client-123",
                "client_secret": "secret-xyz",
            }
        ),
    }

    monkeypatch.setattr(oauth_mod, "fetch_one", lambda query, params=(): token_row)
    monkeypatch.setattr(oauth_mod, "decrypt_secret", lambda value: "access-123")
    monkeypatch.setattr(oauth_mod, "now_iso", lambda: "2026-04-05T15:40:00+00:00")
    monkeypatch.setattr(oauth_mod, "execute", lambda query, params=(): executed.append((query, params)))
    monkeypatch.setattr(
        oauth_mod,
        "_sync_http_post_form",
        lambda url, data, headers=None: revoked_payloads.append((url, data, headers)) or {},
    )
    monkeypatch.setattr(
        oauth_mod,
        "_cleanup_legacy_oauth_env_values",
        lambda agent_id, server_key: cleanup_calls.append((agent_id, server_key)),
    )

    result = await oauth_mod.revoke_oauth_token("ATLAS", "linear")

    assert result == {"success": True}
    assert revoked_payloads == [
        (
            "https://linear.example.com/oauth/revoke",
            {
                "token": "access-123",
                "client_id": "client-123",
                "client_secret": "secret-xyz",
            },
            None,
        )
    ]
    assert len(executed) == 2
    assert "DELETE FROM cp_mcp_oauth_tokens" in executed[0][0]
    assert executed[0][1] == ("ATLAS", "linear")
    assert "UPDATE cp_mcp_agent_connections" in executed[1][0]
    assert executed[1][1][1:] == ("ATLAS", "linear")
    assert cleanup_calls == [("ATLAS", "linear")]
