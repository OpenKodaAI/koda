"""Resolve MCP connections into the minimal runtime contract."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from koda.control_plane.crypto import decrypt_secret
from koda.control_plane.database import fetch_one, json_load


def decrypt_env_values(env_values_json: str | None) -> dict[str, str]:
    """Decrypt stored env values for one MCP connection."""
    try:
        encrypted = json_load(str(env_values_json or "{}"), {})
        return {str(k): decrypt_secret(str(v)) if v else "" for k, v in encrypted.items()}
    except Exception:
        return {}


def resolve_mcp_runtime_connection(
    agent_id: str,
    server_key: str,
    *,
    connection_row: Any | None = None,
    catalog_row: Any | None = None,
) -> dict[str, Any] | None:
    """Build a runtime-safe MCP connection payload for one agent/server."""
    if connection_row is None:
        connection_row = fetch_one(
            "SELECT * FROM cp_mcp_agent_connections WHERE agent_id = ? AND server_key = ?",
            (agent_id, server_key),
        )
    if connection_row is None:
        return None

    if catalog_row is None:
        catalog_row = fetch_one("SELECT * FROM cp_mcp_server_catalog WHERE server_key = ?", (server_key,))
    if catalog_row is None:
        return None

    metadata = json_load(str(catalog_row.get("metadata_json") or "{}"), {})
    env_values = decrypt_env_values(str(connection_row.get("env_values_json") or "{}"))
    auth_method = str(connection_row.get("auth_method") or "manual")
    transport_type = str(connection_row.get("transport_override") or catalog_row.get("transport_type") or "stdio")
    command = json_load(
        str(connection_row.get("command_override_json") or catalog_row.get("command_json") or "[]"),
        [],
    )
    base_url = (
        str(connection_row.get("url_override") or catalog_row.get("remote_url") or catalog_row.get("url") or "").strip()
        or None
    )
    headers = _resolve_manual_headers(metadata, env_values)
    oauth = _resolve_oauth_payload(agent_id, server_key, auth_method, metadata)
    if oauth:
        headers.update(oauth.get("headers") or {})

    runtime_url = _resolve_runtime_url(base_url, metadata, env_values)
    runtime_env = _resolve_runtime_env(transport_type, env_values, metadata, auth_method)

    return {
        "server_key": server_key,
        "transport_type": transport_type,
        "command": command,
        "command_json": json.dumps(command, ensure_ascii=False),
        "url": runtime_url,
        "env_values": runtime_env,
        "headers": headers,
        "enabled": bool(int(connection_row.get("enabled") or 0)) if connection_row.get("enabled") is not None else True,
        "cached_tools_json": connection_row.get("cached_tools_json") or None,
        "auth_method": auth_method,
        "oauth_connected": bool(oauth),
        "account_label": oauth.get("account_label") if oauth else None,
        "expires_at": oauth.get("expires_at") if oauth else None,
    }


def _resolve_runtime_env(
    transport_type: str,
    env_values: dict[str, str],
    metadata: dict[str, Any],
    auth_method: str,
) -> dict[str, str]:
    if transport_type != "stdio":
        return {}
    if auth_method == "oauth":
        oauth_target = metadata.get("oauth_runtime_target") or {}
        if oauth_target.get("type") == "env" and oauth_target.get("env_key"):
            # This path is reserved for future stdio OAuth-backed servers.
            return {str(k): str(v) for k, v in env_values.items() if k != str(oauth_target.get("env_key"))}
    return {str(k): str(v) for k, v in env_values.items() if v}


def _resolve_runtime_url(base_url: str | None, metadata: dict[str, Any], env_values: dict[str, str]) -> str | None:
    if not base_url:
        return None
    fixed_params = metadata.get("fixed_url_params") or {}
    dynamic_params = metadata.get("url_params") or []
    params: dict[str, str] = {str(key): str(value) for key, value in fixed_params.items() if value not in (None, "")}
    for item in dynamic_params:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        env_key = str(item.get("env_key") or "").strip()
        if not name or not env_key:
            continue
        value = str(env_values.get(env_key) or "").strip()
        if value:
            params[name] = value
    if not params:
        return base_url

    parts = urlsplit(base_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(params)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _resolve_manual_headers(metadata: dict[str, Any], env_values: dict[str, str]) -> dict[str, str]:
    header_cfg = metadata.get("manual_auth_header")
    if not isinstance(header_cfg, dict):
        return {}
    header_name = str(header_cfg.get("header_name") or "").strip()
    value_template = str(header_cfg.get("value_template") or "").strip()
    if not header_name or not value_template:
        return {}
    try:
        value = value_template.format_map(_SafeFormatDict(env_values))
    except Exception:
        return {}
    if "{" in value or not value.strip():
        return {}
    return {header_name: value}


def _resolve_oauth_payload(
    agent_id: str,
    server_key: str,
    auth_method: str,
    metadata: dict[str, Any],
) -> dict[str, Any] | None:
    if auth_method != "oauth":
        return None
    token_row = fetch_one(
        "SELECT * FROM cp_mcp_oauth_tokens WHERE agent_id = ? AND server_key = ?",
        (agent_id, server_key),
    )
    if token_row is None:
        return None
    encrypted_access = str(token_row.get("access_token_encrypted") or "")
    if not encrypted_access:
        return None
    try:
        access_token = decrypt_secret(encrypted_access)
    except Exception:
        return None

    runtime_auth = metadata.get("oauth_runtime_auth") or {"type": "authorization_bearer"}
    headers: dict[str, str] = {}
    auth_type = str(runtime_auth.get("type") or "authorization_bearer")
    if auth_type == "authorization_bearer":
        header_name = str(runtime_auth.get("header_name") or "Authorization")
        prefix = str(runtime_auth.get("prefix") or "Bearer")
        headers[header_name] = f"{prefix} {access_token}".strip()
    elif auth_type == "header":
        header_name = str(runtime_auth.get("header_name") or "").strip()
        if header_name:
            headers[header_name] = access_token

    return {
        "headers": headers,
        "account_label": str(token_row.get("provider_account_label") or "") or None,
        "expires_at": str(token_row.get("expires_at") or "") or None,
    }


class _SafeFormatDict(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"
