"""MCP server bootstrap for agent startup."""

from __future__ import annotations

import contextlib
from typing import Any

from koda.logging_config import get_logger

log = get_logger(__name__)


async def bootstrap_mcp_for_agent(agent_id: str) -> dict[str, Any]:
    """Start MCP servers and register their tools for a specific agent.

    Called during agent _post_init() to initialize all configured MCP connections.
    Returns summary dict with started_servers, total_tools, errors.
    """
    from koda.config import MCP_ENABLED

    if not MCP_ENABLED:
        return {"skipped": True, "reason": "MCP_ENABLED is false"}

    from koda.services.mcp_bridge import register_mcp_tools_for_agent
    from koda.services.mcp_manager import mcp_server_manager
    from koda.services.tool_dispatcher import _MCP_READ_TOOLS, _MCP_WRITE_TOOLS, _TOOL_HANDLERS

    started_servers = 0
    total_tools = 0
    errors: list[str] = []
    connections_for_registration: list[dict[str, Any]] = []

    try:
        connections = _load_agent_mcp_connections(agent_id)
    except Exception as exc:
        log.warning("mcp_bootstrap_load_failed", agent_id=agent_id, error=str(exc))
        return {"started_servers": 0, "total_tools": 0, "errors": [str(exc)]}

    for conn in connections:
        if not conn.get("enabled", True):
            continue
        server_key = conn.get("server_key", "")
        if not server_key:
            continue

        try:
            catalog = _load_catalog_entry(server_key)
            if catalog is None:
                errors.append(f"{server_key}: catalog entry not found")
                continue

            transport_type = conn.get("transport_override") or catalog.get("transport_type", "stdio")
            command_list = conn.get("command_override") or conn.get("command") or catalog.get("command") or []
            command = command_list if isinstance(command_list, list) else None
            url = conn.get("url_override") or conn.get("url") or catalog.get("remote_url") or catalog.get("url")
            env_values = _decrypt_connection_env(conn)
            headers = conn.get("headers") if isinstance(conn.get("headers"), dict) else None

            # Token freshness check for OAuth connections
            auth_method = conn.get("auth_method", "manual")
            if auth_method == "oauth":
                from koda.services.mcp_oauth import ensure_valid_token

                try:
                    valid = await ensure_valid_token(agent_id, server_key)
                    if not valid:
                        errors.append(f"{server_key}: OAuth token expired and could not be refreshed")
                        continue
                    # Re-load env values since they may have been refreshed
                    refreshed_conn = _load_single_connection(agent_id, server_key)
                    if refreshed_conn:
                        env_values = _decrypt_connection_env(refreshed_conn)
                        headers = (
                            refreshed_conn.get("headers")
                            if isinstance(refreshed_conn.get("headers"), dict)
                            else headers
                        )
                except Exception as exc:
                    errors.append(f"{server_key}: OAuth token refresh failed: {exc}")
                    continue

            instance = await mcp_server_manager.ensure_started(
                server_key=server_key,
                agent_id=agent_id,
                transport_type=transport_type,
                command=command,
                url=url,
                env=env_values if env_values else None,
                headers=headers,
            )

            started_servers += 1
            tool_count = len(instance.cached_tools)
            total_tools += tool_count

            cached_tools_data: list[dict[str, Any]] = []
            for tool in instance.cached_tools:
                tool_dict: dict[str, Any] = {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                }
                if tool.annotations:
                    tool_dict["annotations"] = {
                        "read_only_hint": tool.annotations.read_only_hint,
                        "destructive_hint": tool.annotations.destructive_hint,
                        "idempotent_hint": tool.annotations.idempotent_hint,
                    }
                cached_tools_data.append(tool_dict)

            connections_for_registration.append(
                {
                    "server_key": server_key,
                    "cached_tools": cached_tools_data,
                }
            )

            log.info(
                "mcp_bootstrap_server_started",
                agent_id=agent_id,
                server_key=server_key,
                tool_count=tool_count,
            )
            with contextlib.suppress(Exception):
                from koda.control_plane.manager import get_control_plane_manager

                get_control_plane_manager()._record_mcp_runtime_state(  # type: ignore[attr-defined]
                    agent_id,
                    server_key,
                    success=True,
                    error="",
                    tools=cached_tools_data,
                )
        except Exception as exc:
            errors.append(f"{server_key}: {exc}")
            log.warning(
                "mcp_bootstrap_server_failed",
                agent_id=agent_id,
                server_key=server_key,
                error=str(exc),
            )
            with contextlib.suppress(Exception):
                from koda.control_plane.manager import get_control_plane_manager

                get_control_plane_manager()._record_mcp_runtime_state(  # type: ignore[attr-defined]
                    agent_id,
                    server_key,
                    success=False,
                    error=str(exc),
                    tools=[],
                )

    if connections_for_registration:
        registered = register_mcp_tools_for_agent(
            agent_id,
            connections_for_registration,
            _TOOL_HANDLERS,
            _MCP_WRITE_TOOLS,
            _MCP_READ_TOOLS,
        )
        total_tools = len(registered)

    summary: dict[str, Any] = {
        "started_servers": started_servers,
        "total_tools": total_tools,
        "errors": errors,
    }
    log.info("mcp_bootstrap_complete", agent_id=agent_id, **summary)
    return summary


def _load_agent_mcp_connections(agent_id: str) -> list[dict[str, Any]]:
    """Load MCP connections for an agent.

    Always resolves through the control-plane manager so worker startup,
    verification, discovery, and runtime execution all use the same path.
    """
    try:
        from koda.control_plane.manager import get_control_plane_manager

        manager = get_control_plane_manager()
        return manager.get_mcp_runtime_config(agent_id)
    except Exception:
        return []


def _load_catalog_entry(server_key: str) -> dict[str, Any] | None:
    """Load a catalog entry by server key."""
    try:
        from koda.control_plane.manager import get_control_plane_manager

        manager = get_control_plane_manager()
        return manager.get_mcp_catalog_entry(server_key)
    except Exception:
        return None


def _load_single_connection(agent_id: str, server_key: str) -> dict[str, Any] | None:
    """Reload a single MCP connection from the control-plane manager."""
    try:
        from koda.control_plane.manager import get_control_plane_manager

        manager = get_control_plane_manager()
        return manager.get_mcp_agent_connection(agent_id, server_key)
    except Exception:
        return None


def _decrypt_connection_env(conn: dict[str, Any]) -> dict[str, str]:
    """Extract environment values from a connection.

    Runtime snapshots may inline already-decrypted values under ``env_values``.
    Manager-backed rows still store encrypted ``env_values_json`` that must be
    decrypted on demand.
    """
    # Already-decrypted values from the runtime snapshot payload.
    plain = conn.get("env_values")
    if isinstance(plain, dict) and plain:
        return {str(k): str(v) for k, v in plain.items()}

    raw_json = conn.get("env_values_json", "{}")
    if not raw_json or raw_json == "{}":
        return {}
    try:
        from koda.control_plane.manager import get_control_plane_manager

        manager = get_control_plane_manager()
        return manager._decrypt_mcp_env_values(raw_json)
    except Exception:
        return {}
