"""Focused tests for MCP OAuth flow orchestration."""

from __future__ import annotations

import json

import pytest


def test_validate_frontend_callback_uri_allows_loopback_without_allowlist(monkeypatch):
    from koda.services import mcp_oauth as oauth_mod

    monkeypatch.delenv("MCP_OAUTH_CALLBACK_BASE_URL", raising=False)
    monkeypatch.delenv("WEB_PUBLIC_BASE_URL", raising=False)

    assert (
        oauth_mod._validate_frontend_callback_uri("http://127.0.0.1:3000/oauth/callback")
        == "http://127.0.0.1:3000/oauth/callback"
    )


def test_validate_frontend_callback_uri_rejects_remote_origin_without_allowlist(monkeypatch):
    from koda.services import mcp_oauth as oauth_mod

    monkeypatch.delenv("MCP_OAUTH_CALLBACK_BASE_URL", raising=False)
    monkeypatch.delenv("WEB_PUBLIC_BASE_URL", raising=False)

    with pytest.raises(ValueError, match="not allowed"):
        oauth_mod._validate_frontend_callback_uri("https://app.example.com/oauth/callback")


def test_validate_frontend_callback_uri_allows_configured_remote_origin(monkeypatch):
    from koda.services import mcp_oauth as oauth_mod

    monkeypatch.setenv("MCP_OAUTH_CALLBACK_BASE_URL", "https://app.example.com")
    monkeypatch.delenv("WEB_PUBLIC_BASE_URL", raising=False)

    assert (
        oauth_mod._validate_frontend_callback_uri("https://app.example.com/oauth/callback")
        == "https://app.example.com/oauth/callback"
    )


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
        lambda url, data, headers=None: {
            "access_token": "access-123",
            "refresh_token": "refresh-456",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "read write",
            "provider_account_id": "acct-1",
            "account_label": "Linear Workspace",
        },
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


@pytest.mark.asyncio
async def test_refresh_oauth_token_updates_persisted_tokens(monkeypatch):
    from koda.services import mcp_oauth as oauth_mod

    executed: list[tuple[str, tuple[object, ...]]] = []

    token_row = {
        "refresh_token_encrypted": "enc:refresh-456",
        "oauth_context_json": json.dumps(
            {
                "client_id": "client-123",
                "token_url": "https://linear.example.com/oauth/token",
                "client_secret": "secret-xyz",
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
        lambda url, data, headers=None: {
            "access_token": "access-789",
            "refresh_token": "refresh-999",
            "expires_in": 7200,
        },
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
