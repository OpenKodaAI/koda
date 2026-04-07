"""MCP OAuth flow orchestration service."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import ipaddress
import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from koda.control_plane.crypto import decrypt_secret, encrypt_secret
from koda.control_plane.database import execute, fetch_all, fetch_one, json_dump, json_load, now_iso
from koda.logging_config import get_logger

log = get_logger(__name__)


def _sync_http_get_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        body = resp.read().decode("utf-8")
    return json.loads(body) if body else {}


def _sync_http_post_form(
    url: str,
    data: dict[str, str],
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=encoded, method="POST")
    req.add_header("Accept", "application/json")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        body = resp.read().decode("utf-8")
    return json.loads(body) if body else {}


def _sync_http_post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
    )
    req.add_header("Accept", "application/json")
    req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        body = resp.read().decode("utf-8")
    return json.loads(body) if body else {}


def _basic_auth_header(client_id: str, client_secret: str) -> str:
    credentials = f"{client_id}:{client_secret}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
    return f"Basic {encoded}"


def _catalog_row(server_key: str) -> Any | None:
    return fetch_one("SELECT * FROM cp_mcp_server_catalog WHERE server_key = ?", (server_key,))


def _oauth_enabled_catalog_row(server_key: str) -> Any:
    row = _catalog_row(server_key)
    if row is None:
        raise ValueError(f"Unknown MCP server: {server_key}")
    if not bool(int(row.get("oauth_enabled") or 0)):
        raise ValueError(f"OAuth not enabled for server: {server_key}")
    return row


def _oauth_env(server_key: str, suffix: str) -> str:
    candidates = (
        f"MCP_OAUTH_{server_key.upper()}_{suffix}",
        f"{server_key.upper()}_OAUTH_{suffix}",
    )
    for key in candidates:
        value = str(os.environ.get(key) or "").strip()
        if value:
            return value
    return ""


def _validate_frontend_callback_uri(frontend_callback_uri: str) -> str:
    value = str(frontend_callback_uri or "").strip()
    if not value:
        raise ValueError("frontend_callback_uri is required")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("frontend_callback_uri must be an absolute http(s) URL")
    allowed_bases = [
        str(os.environ.get(name) or "").strip().rstrip("/")
        for name in ("MCP_OAUTH_CALLBACK_BASE_URL", "WEB_PUBLIC_BASE_URL")
    ]
    allowed_bases = [base for base in allowed_bases if base]
    if allowed_bases:
        if not any(
            value == base or value.startswith(f"{base}/") or value.startswith(f"{base}?") for base in allowed_bases
        ):
            raise ValueError("frontend_callback_uri is not allowed")
        return value

    hostname = (parsed.hostname or "").strip().lower()
    if hostname == "localhost":
        return value
    try:
        if ipaddress.ip_address(hostname).is_loopback:
            return value
    except ValueError:
        pass
    raise ValueError("frontend_callback_uri is not allowed without an explicit callback base")
    return value


def _build_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _metadata_candidates(row: Any) -> list[str]:
    explicit = str(row.get("oauth_metadata_url") or "").strip()
    if explicit:
        return [explicit]
    remote_url = str(row.get("remote_url") or row.get("url") or "").strip()
    if not remote_url:
        return []
    parts = urlsplit(remote_url)
    origin = f"{parts.scheme}://{parts.netloc}"
    return [
        f"{origin}/.well-known/oauth-authorization-server",
        f"{origin}/.well-known/openid-configuration",
    ]


async def _discover_oauth_metadata(row: Any) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    last_error: Exception | None = None
    for candidate in _metadata_candidates(row):
        try:
            return await loop.run_in_executor(None, _sync_http_get_json, candidate, None)
        except Exception as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise ValueError(f"oauth_metadata_discovery_failed: {last_error}") from last_error
    raise ValueError("oauth_metadata_not_configured")


def _scopes_for_server(row: Any, metadata: dict[str, Any]) -> str:
    custom = _safe_text(json_load(str(row.get("metadata_json") or "{}"), {}).get("oauth_scopes"))
    if custom:
        return custom
    supported = metadata.get("scopes_supported")
    if isinstance(supported, list):
        return " ".join(str(scope) for scope in supported if str(scope).strip())
    return ""


async def _build_oauth_context(server_key: str, redirect_uri: str) -> dict[str, Any]:
    row = _oauth_enabled_catalog_row(server_key)
    metadata_json = json_load(str(row.get("metadata_json") or "{}"), {})
    oauth_mode = str(row.get("oauth_mode") or "none")
    oauth_metadata = await _discover_oauth_metadata(row)
    authorization_url = _safe_text(
        oauth_metadata.get("authorization_endpoint") or metadata_json.get("authorization_url")
    )
    token_url = _safe_text(oauth_metadata.get("token_endpoint") or metadata_json.get("token_url"))
    revocation_url = _safe_text(oauth_metadata.get("revocation_endpoint") or metadata_json.get("revocation_url"))
    if not authorization_url or not token_url:
        raise ValueError("oauth_endpoints_not_available")

    context: dict[str, Any] = {
        "server_key": server_key,
        "oauth_mode": oauth_mode,
        "authorization_url": authorization_url,
        "token_url": token_url,
        "revocation_url": revocation_url,
        "redirect_uri": redirect_uri,
        "scopes": _scopes_for_server(row, oauth_metadata),
        "extra_auth_params": _safe_json_object(metadata_json.get("extra_auth_params")),
        "token_exchange_auth": "body",
    }

    if oauth_mode == "dcr":
        registration_endpoint = _safe_text(
            oauth_metadata.get("registration_endpoint") or metadata_json.get("registration_endpoint")
        )
        if not registration_endpoint:
            raise ValueError("oauth_registration_endpoint_not_available")
        context.update(await _register_dynamic_client(server_key, registration_endpoint, redirect_uri, metadata_json))
    elif oauth_mode == "confidential":
        client_id = _oauth_env(server_key, "CLIENT_ID")
        client_secret = _oauth_env(server_key, "CLIENT_SECRET")
        if not client_id or not client_secret:
            raise ValueError(f"missing OAuth client credentials for {server_key}")
        methods = oauth_metadata.get("token_endpoint_auth_methods_supported")
        if isinstance(methods, list) and "client_secret_basic" in methods:
            token_exchange_auth = "basic"
        else:
            token_exchange_auth = _safe_text(metadata_json.get("token_exchange_auth")) or "body"
        context.update(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "token_exchange_auth": token_exchange_auth,
            }
        )
    else:
        raise ValueError(f"Unsupported oauth_mode: {oauth_mode}")
    return context


async def _register_dynamic_client(
    server_key: str,
    registration_endpoint: str,
    redirect_uri: str,
    metadata_json: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "client_name": _safe_text(metadata_json.get("oauth_client_name")) or f"Koda MCP ({server_key})",
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": _safe_text(metadata_json.get("token_endpoint_auth_method")) or "none",
    }
    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(None, _sync_http_post_json, registration_endpoint, payload, None)
    client_id = _safe_text(response.get("client_id"))
    if not client_id:
        raise ValueError("dynamic_client_registration_failed")
    return {
        "client_id": client_id,
        "client_secret": _safe_text(response.get("client_secret")),
        "client_registration_response": response,
    }


async def start_oauth_flow(
    agent_id: str,
    server_key: str,
    frontend_callback_uri: str,
    redirect_uri: str | None = None,
) -> dict[str, Any]:
    """Initiate an OAuth authorization-code flow for one MCP server."""
    frontend_callback_uri = _validate_frontend_callback_uri(frontend_callback_uri)
    redirect_uri = _validate_frontend_callback_uri(redirect_uri or frontend_callback_uri)

    agent_row = fetch_one("SELECT id FROM cp_agent_definitions WHERE id = ?", (agent_id,))
    if agent_row is None:
        raise KeyError(agent_id)

    oauth_context = await _build_oauth_context(server_key, redirect_uri)
    state = secrets.token_urlsafe(32)
    session_id = secrets.token_urlsafe(16)
    now = now_iso()
    expires_at = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = _build_code_challenge(code_verifier)

    execute(
        """
        INSERT INTO cp_mcp_oauth_sessions
            (session_id, agent_id, server_key, state_param, code_verifier,
             redirect_uri, frontend_callback_uri, oauth_context_json,
             status, expires_at, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
        """,
        (
            session_id,
            agent_id,
            server_key,
            state,
            code_verifier,
            redirect_uri,
            frontend_callback_uri,
            json_dump(oauth_context),
            expires_at,
            now,
            now,
        ),
    )

    params: dict[str, str] = {
        "client_id": str(oauth_context["client_id"]),
        "redirect_uri": redirect_uri,
        "state": state,
        "response_type": "code",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if oauth_context.get("scopes"):
        params["scope"] = str(oauth_context["scopes"])
    for key, value in _safe_json_object(oauth_context.get("extra_auth_params")).items():
        if value not in (None, ""):
            params[str(key)] = str(value)

    authorization_url = f"{oauth_context['authorization_url']}?{urllib.parse.urlencode(params)}"
    log.info("mcp_oauth_flow_started", agent_id=agent_id, server_key=server_key, session_id=session_id)
    return {
        "session_id": session_id,
        "authorization_url": authorization_url,
        "state": state,
        "redirect_uri": redirect_uri,
        "frontend_callback_uri": frontend_callback_uri,
    }


async def handle_oauth_callback(state: str, code: str, error: str | None = None) -> dict[str, Any]:
    """Exchange an authorization code for tokens after the OAuth redirect."""
    if error:
        return {"success": False, "error": error}
    if not state or not code:
        return {"success": False, "error": "missing_state_or_code"}

    session = fetch_one(
        "SELECT * FROM cp_mcp_oauth_sessions WHERE state_param = ? AND status = 'pending'",
        (state,),
    )
    if session is None:
        return {"success": False, "error": "invalid_or_expired_session"}

    session_id = str(session["session_id"])
    agent_id = str(session["agent_id"])
    server_key = str(session["server_key"])
    redirect_uri = str(session.get("redirect_uri") or "")
    frontend_callback_uri = str(session.get("frontend_callback_uri") or redirect_uri)
    code_verifier = str(session.get("code_verifier") or "")
    oauth_context = _safe_json_object(json_load(str(session.get("oauth_context_json") or "{}"), {}))

    expires_at_str = str(session.get("expires_at") or "")
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if datetime.now(UTC) > expires_at:
                _update_session_status(session_id, "expired", "session expired")
                return {"success": False, "error": "session_expired", "frontend_callback_uri": frontend_callback_uri}
        except (ValueError, TypeError):
            pass

    client_id = _safe_text(oauth_context.get("client_id"))
    token_url = _safe_text(oauth_context.get("token_url"))
    client_secret = _safe_text(oauth_context.get("client_secret"))
    token_exchange_auth = _safe_text(oauth_context.get("token_exchange_auth")) or "body"

    if not client_id or not token_url:
        _update_session_status(session_id, "failed", "oauth_context_incomplete")
        return {"success": False, "error": "oauth_context_incomplete", "frontend_callback_uri": frontend_callback_uri}

    token_data: dict[str, str] = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": code_verifier,
    }
    headers: dict[str, str] = {}
    if client_secret:
        if token_exchange_auth == "basic":
            headers["Authorization"] = _basic_auth_header(client_id, client_secret)
            token_data.pop("client_id", None)
        else:
            token_data["client_secret"] = client_secret

    try:
        loop = asyncio.get_running_loop()
        token_response = await loop.run_in_executor(None, _sync_http_post_form, token_url, token_data, headers)
    except Exception as exc:
        _update_session_status(session_id, "failed", f"token exchange failed: {exc}")
        return {"success": False, "error": "token_exchange_failed", "frontend_callback_uri": frontend_callback_uri}

    access_token = _safe_text(token_response.get("access_token"))
    refresh_token = _safe_text(token_response.get("refresh_token"))
    token_type = _safe_text(token_response.get("token_type")) or "Bearer"
    expires_in = token_response.get("expires_in")
    scopes_granted = _safe_text(token_response.get("scope") or oauth_context.get("scopes"))
    provider_account_id = _safe_text(token_response.get("provider_account_id") or token_response.get("account_id"))
    provider_account_label = _infer_account_label(token_response)
    token_expires_at = _compute_expires_at(expires_in)

    if not access_token:
        _update_session_status(session_id, "failed", "no access_token in response")
        return {"success": False, "error": "no_access_token", "frontend_callback_uri": frontend_callback_uri}

    now = now_iso()
    execute(
        """
        INSERT INTO cp_mcp_oauth_tokens
            (agent_id, server_key, access_token_encrypted, refresh_token_encrypted,
             token_type, expires_at, scopes_granted, provider_account_id,
             provider_account_label, last_refreshed_at, created_at, updated_at,
             oauth_context_json, last_error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        ON CONFLICT (agent_id, server_key) DO UPDATE SET
            access_token_encrypted = excluded.access_token_encrypted,
            refresh_token_encrypted = excluded.refresh_token_encrypted,
            token_type = excluded.token_type,
            expires_at = excluded.expires_at,
            scopes_granted = excluded.scopes_granted,
            provider_account_id = excluded.provider_account_id,
            provider_account_label = excluded.provider_account_label,
            last_refreshed_at = excluded.last_refreshed_at,
            updated_at = excluded.updated_at,
            oauth_context_json = excluded.oauth_context_json,
            last_error = NULL
        """,
        (
            agent_id,
            server_key,
            encrypt_secret(access_token),
            encrypt_secret(refresh_token) if refresh_token else "",
            token_type,
            token_expires_at or "",
            scopes_granted,
            provider_account_id,
            provider_account_label,
            now,
            now,
            now,
            json_dump(oauth_context),
        ),
    )

    _mark_connection_as_oauth(agent_id, server_key)
    _cleanup_legacy_oauth_env_values(agent_id, server_key)
    _update_session_status(session_id, "completed")

    return {
        "success": True,
        "server_key": server_key,
        "agent_id": agent_id,
        "provider_account_id": provider_account_id or None,
        "provider_account_label": provider_account_label or None,
        "frontend_callback_uri": frontend_callback_uri,
    }


async def refresh_oauth_token(agent_id: str, server_key: str) -> dict[str, Any]:
    token_row = fetch_one(
        "SELECT * FROM cp_mcp_oauth_tokens WHERE agent_id = ? AND server_key = ?",
        (agent_id, server_key),
    )
    if token_row is None:
        return {"success": False, "error": "no_token_found"}

    encrypted_refresh = str(token_row.get("refresh_token_encrypted") or "")
    if not encrypted_refresh:
        return {"success": False, "error": "no_refresh_token"}

    oauth_context = _safe_json_object(json_load(str(token_row.get("oauth_context_json") or "{}"), {}))
    client_id = _safe_text(oauth_context.get("client_id"))
    token_url = _safe_text(oauth_context.get("token_url"))
    client_secret = _safe_text(oauth_context.get("client_secret"))
    token_exchange_auth = _safe_text(oauth_context.get("token_exchange_auth")) or "body"
    if not client_id or not token_url:
        return {"success": False, "error": "oauth_context_incomplete"}

    try:
        refresh_token = decrypt_secret(encrypted_refresh)
    except Exception:
        _record_token_error(agent_id, server_key, "decrypt_refresh_failed")
        return {"success": False, "error": "decrypt_refresh_failed"}

    token_data: dict[str, str] = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }
    headers: dict[str, str] = {}
    if client_secret:
        if token_exchange_auth == "basic":
            headers["Authorization"] = _basic_auth_header(client_id, client_secret)
            token_data.pop("client_id", None)
        else:
            token_data["client_secret"] = client_secret

    try:
        loop = asyncio.get_running_loop()
        token_response = await loop.run_in_executor(None, _sync_http_post_form, token_url, token_data, headers)
    except Exception as exc:
        _record_token_error(agent_id, server_key, f"refresh_failed: {exc}")
        return {"success": False, "error": "refresh_failed"}

    access_token = _safe_text(token_response.get("access_token"))
    refreshed_token = _safe_text(token_response.get("refresh_token")) or refresh_token
    token_expires_at = _compute_expires_at(token_response.get("expires_in"))
    if not access_token:
        _record_token_error(agent_id, server_key, "no_access_token")
        return {"success": False, "error": "no_access_token"}

    now = now_iso()
    execute(
        """
        UPDATE cp_mcp_oauth_tokens
        SET access_token_encrypted = ?,
            refresh_token_encrypted = ?,
            expires_at = ?,
            last_refreshed_at = ?,
            updated_at = ?,
            last_error = NULL
        WHERE agent_id = ? AND server_key = ?
        """,
        (
            encrypt_secret(access_token),
            encrypt_secret(refreshed_token),
            token_expires_at or "",
            now,
            now,
            agent_id,
            server_key,
        ),
    )
    return {"success": True, "expires_at": token_expires_at}


async def ensure_valid_token(agent_id: str, server_key: str) -> bool:
    token_row = fetch_one(
        "SELECT * FROM cp_mcp_oauth_tokens WHERE agent_id = ? AND server_key = ?",
        (agent_id, server_key),
    )
    if token_row is None:
        return False

    expires_at_str = str(token_row.get("expires_at") or "")
    if not expires_at_str:
        return True
    try:
        expires_at = datetime.fromisoformat(expires_at_str)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return True
    if datetime.now(UTC) + timedelta(minutes=5) >= expires_at:
        result = await refresh_oauth_token(agent_id, server_key)
        return bool(result.get("success"))
    return True


async def revoke_oauth_token(agent_id: str, server_key: str) -> dict[str, Any]:
    token_row = fetch_one(
        "SELECT * FROM cp_mcp_oauth_tokens WHERE agent_id = ? AND server_key = ?",
        (agent_id, server_key),
    )
    oauth_context = (
        _safe_json_object(json_load(str(token_row.get("oauth_context_json") or "{}"), {})) if token_row else {}
    )
    revocation_url = _safe_text(oauth_context.get("revocation_url"))
    if token_row and revocation_url:
        encrypted_access = str(token_row.get("access_token_encrypted") or "")
        if encrypted_access:
            try:
                access_token = decrypt_secret(encrypted_access)
                client_id = _safe_text(oauth_context.get("client_id"))
                client_secret = _safe_text(oauth_context.get("client_secret"))
                payload = {"token": access_token}
                if client_id:
                    payload["client_id"] = client_id
                if client_secret:
                    payload["client_secret"] = client_secret
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, _sync_http_post_form, revocation_url, payload, None)
            except Exception:
                log.warning("mcp_oauth_revocation_failed", agent_id=agent_id, server_key=server_key, exc_info=True)

    execute(
        "DELETE FROM cp_mcp_oauth_tokens WHERE agent_id = ? AND server_key = ?",
        (agent_id, server_key),
    )
    execute(
        """
        UPDATE cp_mcp_agent_connections
        SET auth_method = 'manual', updated_at = ?
        WHERE agent_id = ? AND server_key = ?
        """,
        (now_iso(), agent_id, server_key),
    )
    _cleanup_legacy_oauth_env_values(agent_id, server_key)
    return {"success": True}


async def refresh_expiring_tokens(buffer_minutes: int = 30) -> dict[str, Any]:
    cutoff = (datetime.now(UTC) + timedelta(minutes=buffer_minutes)).isoformat()
    rows = fetch_all(
        """
        SELECT agent_id, server_key FROM cp_mcp_oauth_tokens
        WHERE expires_at != '' AND expires_at < ?
        """,
        (cutoff,),
    )
    refreshed = 0
    failed = 0
    errors: list[str] = []
    for row in rows:
        agent_id = str(row["agent_id"])
        server_key = str(row["server_key"])
        try:
            result = await refresh_oauth_token(agent_id, server_key)
            if result.get("success"):
                refreshed += 1
            else:
                failed += 1
                errors.append(f"{agent_id}/{server_key}: {result.get('error', 'unknown')}")
        except Exception as exc:
            failed += 1
            errors.append(f"{agent_id}/{server_key}: {exc}")
    return {"refreshed": refreshed, "failed": failed, "errors": errors}


def _update_session_status(session_id: str, status: str, error_message: str | None = None) -> None:
    execute(
        """
        UPDATE cp_mcp_oauth_sessions
        SET status = ?, error_message = ?, updated_at = ?
        WHERE session_id = ?
        """,
        (status, error_message or "", now_iso(), session_id),
    )


def _record_token_error(agent_id: str, server_key: str, error: str) -> None:
    execute(
        """
        UPDATE cp_mcp_oauth_tokens
        SET last_error = ?, updated_at = ?
        WHERE agent_id = ? AND server_key = ?
        """,
        (error, now_iso(), agent_id, server_key),
    )


def _mark_connection_as_oauth(agent_id: str, server_key: str) -> None:
    existing = fetch_one(
        "SELECT 1 FROM cp_mcp_agent_connections WHERE agent_id = ? AND server_key = ?",
        (agent_id, server_key),
    )
    now = now_iso()
    if existing is None:
        execute(
            """
            INSERT INTO cp_mcp_agent_connections
                (agent_id, server_key, enabled, env_values_json, metadata_json, created_at, updated_at, auth_method)
            VALUES (?, ?, 1, '{}', '{}', ?, ?, 'oauth')
            """,
            (agent_id, server_key, now, now),
        )
        return
    execute(
        """
        UPDATE cp_mcp_agent_connections
        SET auth_method = 'oauth', updated_at = ?
        WHERE agent_id = ? AND server_key = ?
        """,
        (now, agent_id, server_key),
    )


async def cleanup_expired_sessions() -> int:
    cutoff = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    execute(
        "DELETE FROM cp_mcp_oauth_sessions WHERE created_at < ? OR (status != 'pending' AND created_at < ?)",
        (cutoff, cutoff),
    )
    return 0


def _infer_account_label(token_response: dict[str, Any]) -> str:
    for key in ("provider_account_label", "account_label", "workspace_name", "team_name", "name"):
        value = _safe_text(token_response.get(key))
        if value:
            return value
    team = token_response.get("team")
    if isinstance(team, dict):
        value = _safe_text(team.get("name"))
        if value:
            return value
    return ""


def _compute_expires_at(expires_in: Any) -> str | None:
    if expires_in in (None, ""):
        return None
    with contextlib.suppress(ValueError, TypeError):
        return (datetime.now(UTC) + timedelta(seconds=int(expires_in))).isoformat()
    return None


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_json_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _legacy_oauth_env_keys(server_key: str) -> list[str]:
    row = _catalog_row(server_key)
    metadata = _safe_json_object(json_load(str(row.get("metadata_json") or "{}"), {})) if row is not None else {}
    keys = metadata.get("legacy_oauth_env_keys")
    if not isinstance(keys, list):
        return []
    result: list[str] = []
    for item in keys:
        key = str(item or "").strip()
        if key and key not in result:
            result.append(key)
    return result


def _cleanup_legacy_oauth_env_values(agent_id: str, server_key: str) -> None:
    legacy_keys = _legacy_oauth_env_keys(server_key)
    if not legacy_keys:
        return
    row = fetch_one(
        "SELECT env_values_json FROM cp_mcp_agent_connections WHERE agent_id = ? AND server_key = ?",
        (agent_id, server_key),
    )
    if row is None:
        return
    env_values = json_load(str(row.get("env_values_json") or "{}"), {})
    changed = False
    for key in legacy_keys:
        if key in env_values:
            env_values.pop(key, None)
            changed = True
    if not changed:
        return
    execute(
        """
        UPDATE cp_mcp_agent_connections
        SET env_values_json = ?, updated_at = ?
        WHERE agent_id = ? AND server_key = ?
        """,
        (json_dump(env_values), now_iso(), agent_id, server_key),
    )
