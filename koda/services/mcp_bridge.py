"""Bridge between MCP server tools and the Koda tool dispatch pipeline."""

from __future__ import annotations

import json
from typing import Any

from koda.logging_config import get_logger
from koda.services.mcp_client import McpToolAnnotations
from koda.services.mcp_manager import McpServerInstance, mcp_server_manager

log = get_logger(__name__)

MCP_TOOL_PREFIX = "mcp_"
MCP_TOOL_SEPARATOR = "__"


def mcp_tool_id(server_key: str, tool_name: str) -> str:
    """Build canonical tool ID: 'mcp_github__create_issue'."""
    return f"{MCP_TOOL_PREFIX}{server_key}{MCP_TOOL_SEPARATOR}{tool_name}"


def parse_mcp_tool_id(tool_id: str) -> tuple[str, str] | None:
    """Extract (server_key, tool_name) from an MCP tool ID, or None if not MCP."""
    if not tool_id.startswith(MCP_TOOL_PREFIX):
        return None
    rest = tool_id[len(MCP_TOOL_PREFIX) :]
    if MCP_TOOL_SEPARATOR not in rest:
        return None
    server_key, tool_name = rest.split(MCP_TOOL_SEPARATOR, 1)
    if not server_key or not tool_name:
        return None
    return server_key, tool_name


def is_mcp_tool(tool_id: str) -> bool:
    """Check if a tool ID is an MCP tool."""
    return parse_mcp_tool_id(tool_id) is not None


def classify_mcp_tool_rw(annotations: McpToolAnnotations | None) -> bool:
    """Return True if the tool should be classified as a write operation.

    Conservative default: unknown tools are write operations.
    Only readOnlyHint=True makes a tool read-only.
    """
    if annotations is None:
        return True  # conservative: unknown = write
    return annotations.read_only_hint is not True


def resolve_mcp_tool_policy(
    tool_policies: dict[str, str],
    tool_name: str,
    annotations: McpToolAnnotations | None,
) -> str:
    """Resolve effective governance policy for an MCP tool.

    Returns: 'blocked' | 'always_ask' | 'always_allow' | 'auto'

    tool_policies: dict mapping tool_name -> policy from cp_mcp_tool_policies
    """
    explicit = tool_policies.get(tool_name, "auto")
    if explicit in ("blocked", "always_ask", "always_allow"):
        return explicit
    return "auto"


def _blocked_mcp_tool_names(agent_id: str, server_key: str) -> set[str]:
    try:
        from koda.control_plane.manager import get_control_plane_manager

        return {
            str(item.get("tool_name") or "")
            for item in get_control_plane_manager().list_mcp_tool_policies(agent_id, server_key)
            if str(item.get("policy") or "") == "blocked"
        }
    except Exception:
        return set()


async def handle_mcp_tool_call(
    tool_id: str,
    params: dict[str, Any],
    agent_id: str,
) -> dict[str, Any]:
    """Execute an MCP tool call through the bridge.

    Returns a dict with keys: success, output, metadata
    """
    parsed = parse_mcp_tool_id(tool_id)
    if parsed is None:
        return {
            "success": False,
            "output": f"Invalid MCP tool ID: {tool_id}",
            "metadata": {},
        }
    server_key, tool_name = parsed
    instance = mcp_server_manager.get_instance(server_key, agent_id)
    if instance is None or not instance.started:
        # Lazy start: try to start the server on-demand
        try:
            instance = await _lazy_start_mcp_server(server_key, agent_id)
        except Exception as exc:
            return {
                "success": False,
                "output": f"MCP server '{server_key}' failed to start for agent '{agent_id}': {exc}",
                "metadata": {"server_key": server_key, "tool_name": tool_name, "error": str(exc)},
            }
        if instance is None or not instance.started:
            return {
                "success": False,
                "output": f"MCP server '{server_key}' could not be started for agent '{agent_id}'",
                "metadata": {"server_key": server_key, "tool_name": tool_name},
            }

    try:
        session = instance.session
        if session is None:
            return {
                "success": False,
                "output": f"MCP server '{server_key}' has no active session for agent '{agent_id}'",
                "metadata": {"server_key": server_key, "tool_name": tool_name},
            }
        result = await session.call_tool(tool_name, params)
        # Format content into a readable string
        output_parts: list[str] = []
        for item in result.content:
            content_type = item.get("type", "text")
            if content_type == "text":
                output_parts.append(str(item.get("text", "")))
            elif content_type == "image":
                output_parts.append(f"[Image: {item.get('mimeType', 'unknown')}]")
            elif content_type == "resource":
                resource = item.get("resource", {})
                output_parts.append(f"[Resource: {resource.get('uri', 'unknown')}]")
            else:
                output_parts.append(json.dumps(item, ensure_ascii=False))

        output = "\n".join(output_parts) if output_parts else "(empty result)"

        return {
            "success": not result.is_error,
            "output": output,
            "metadata": {
                "integration_id": "mcp",
                "server_key": server_key,
                "tool_name": tool_name,
                "is_error": result.is_error,
            },
        }
    except Exception as exc:
        log.warning(
            "mcp_tool_call_error",
            server_key=server_key,
            tool_name=tool_name,
            error=str(exc),
        )
        return {
            "success": False,
            "output": f"MCP tool error: {exc}",
            "metadata": {
                "integration_id": "mcp",
                "server_key": server_key,
                "tool_name": tool_name,
                "error": str(exc),
            },
        }


# --- Lazy start helper ---


async def _lazy_start_mcp_server(server_key: str, agent_id: str) -> McpServerInstance | None:
    """Start an MCP server on-demand using catalog + connection config."""
    try:
        from koda.services.mcp_bootstrap import (
            _decrypt_connection_env,
            _load_agent_mcp_connections,
            _load_catalog_entry,
        )

        catalog = _load_catalog_entry(server_key)
        if catalog is None:
            raise ValueError(f"No catalog entry for server '{server_key}'")

        connections = _load_agent_mcp_connections(agent_id)
        conn = next((c for c in connections if c.get("server_key") == server_key and c.get("enabled")), None)
        if conn is None:
            raise ValueError(f"No enabled connection for server '{server_key}' and agent '{agent_id}'")

        transport_type = (
            conn.get("transport_override") or conn.get("transport_type") or catalog.get("transport_type", "stdio")
        )
        command_list = conn.get("command_override") or conn.get("command") or catalog.get("command") or []
        command = command_list if isinstance(command_list, list) else None
        url = conn.get("url_override") or conn.get("url") or catalog.get("remote_url") or catalog.get("url")
        env_values = _decrypt_connection_env(conn)
        headers = conn.get("headers") if isinstance(conn.get("headers"), dict) else None

        instance = await mcp_server_manager.ensure_started(
            server_key=server_key,
            agent_id=agent_id,
            transport_type=transport_type,
            command=command,
            url=url,
            env=env_values if env_values else None,
            headers=headers,
        )

        # Also register the tools in the dispatcher
        from koda.services.tool_dispatcher import _MCP_READ_TOOLS, _MCP_WRITE_TOOLS, _TOOL_HANDLERS

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

        register_mcp_tools_for_agent(
            agent_id,
            [{"server_key": server_key, "cached_tools": cached_tools_data}],
            _TOOL_HANDLERS,
            _MCP_WRITE_TOOLS,
            _MCP_READ_TOOLS,
        )

        log.info("mcp_lazy_start_success", server_key=server_key, agent_id=agent_id, tools=len(instance.cached_tools))
        return instance
    except Exception as exc:
        log.warning("mcp_lazy_start_failed", server_key=server_key, agent_id=agent_id, error=str(exc))
        raise


# --- Tool registration helpers ---


def _make_mcp_handler(tool_id: str, agent_id: str) -> Any:
    """Create an async handler closure for an MCP tool.

    The returned callable matches the ``_ToolHandler`` signature used by
    ``tool_dispatcher._TOOL_HANDLERS``:
        async (params: dict, ctx: ToolContext) -> AgentToolResult
    """

    async def handler(params: dict, ctx: Any) -> Any:  # noqa: ANN401
        from koda.services.tool_dispatcher import AgentToolResult

        result = await handle_mcp_tool_call(tool_id, params, agent_id)
        return AgentToolResult(
            tool=tool_id,
            success=result["success"],
            output=result["output"],
            metadata=result.get("metadata", {}),
        )

    return handler


# Track which tools were registered by which agent (for cleanup)
_agent_mcp_tools: dict[str, set[str]] = {}


def register_mcp_tools_for_agent(
    agent_id: str,
    connections: list[dict[str, Any]],
    tool_handlers: dict[str, Any],
    write_tools: set[str],
    read_tools: set[str],
) -> list[str]:
    """Register MCP tool handlers into the tool dispatch pipeline.

    connections: list of dicts with keys: server_key, cached_tools (list of tool dicts with name, annotations)
    tool_handlers: reference to _TOOL_HANDLERS dict from tool_dispatcher
    write_tools: reference to _WRITE_TOOLS set from tool_dispatcher
    read_tools: reference to _READ_TOOLS set from tool_dispatcher

    Returns list of registered tool IDs.
    """
    registered: list[str] = []
    agent_tools: set[str] = set()

    for conn in connections:
        server_key = conn.get("server_key", "")
        cached_tools = conn.get("cached_tools") or []
        blocked_tool_names = _blocked_mcp_tool_names(agent_id, server_key)

        for tool_data in cached_tools:
            name = tool_data.get("name", "")
            if not name:
                continue
            if name in blocked_tool_names:
                continue

            tid = mcp_tool_id(server_key, name)

            # Parse annotations
            raw_ann = tool_data.get("annotations")
            annotations = None
            if raw_ann and isinstance(raw_ann, dict):
                annotations = McpToolAnnotations(
                    title=raw_ann.get("title"),
                    read_only_hint=raw_ann.get("read_only_hint"),
                    destructive_hint=raw_ann.get("destructive_hint"),
                    idempotent_hint=raw_ann.get("idempotent_hint"),
                )

            # Register handler (closure captures tool_id and agent_id)
            tool_handlers[tid] = _make_mcp_handler(tid, agent_id)

            # Classify read/write
            if classify_mcp_tool_rw(annotations):
                write_tools.add(tid)
                read_tools.discard(tid)
            else:
                read_tools.add(tid)
                write_tools.discard(tid)

            agent_tools.add(tid)
            registered.append(tid)

    _agent_mcp_tools.setdefault(agent_id, set()).update(agent_tools)
    log.info("mcp_tools_registered", agent_id=agent_id, count=len(registered))
    return registered


def unregister_mcp_tools_for_agent(
    agent_id: str,
    tool_handlers: dict[str, Any],
    write_tools: set[str],
    read_tools: set[str],
) -> None:
    """Remove all MCP tool handlers for an agent."""
    agent_tools = _agent_mcp_tools.pop(agent_id, set())
    for tid in agent_tools:
        tool_handlers.pop(tid, None)
        write_tools.discard(tid)
        read_tools.discard(tid)
    if agent_tools:
        log.info("mcp_tools_unregistered", agent_id=agent_id, count=len(agent_tools))


def get_registered_mcp_tools(agent_id: str) -> set[str]:
    """Get set of registered MCP tool IDs for an agent."""
    return set(_agent_mcp_tools.get(agent_id, set()))
