"""Bridge between MCP server capabilities (tools + resources + prompts) and
the Koda tool dispatch pipeline.

Capabilities are surfaced uniformly as runtime tools so the dispatcher and
prompt builder don't need a third code path. The mapping:

* **Tools** → ``mcp_<server>__<tool_name>``. Native MCP tools with read/write
  classification from annotations.
* **Resources** → ``mcp_<server>__read_resource__<uri_hash[:12]>``. Synthetic
  read tool that calls ``resources/read`` on demand. Always classified as
  read-only.
* **Prompts** → ``mcp_<server>__prompt__<prompt_name>``. Synthetic write tool
  that renders the prompt template via ``prompts/get``.

Per-capability policy comes from ``cp_mcp_capability_policies``; ``blocked``
capabilities are skipped at registration so the agent never sees them.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from koda.logging_config import get_logger
from koda.services.mcp_client import McpToolAnnotations
from koda.services.mcp_manager import McpServerInstance, mcp_server_manager

log = get_logger(__name__)

MCP_TOOL_PREFIX = "mcp_"
MCP_TOOL_SEPARATOR = "__"
MCP_RESOURCE_INFIX = "read_resource__"
MCP_PROMPT_INFIX = "prompt__"


def mcp_tool_id(server_key: str, tool_name: str) -> str:
    """Build canonical tool ID: 'mcp_github__create_issue'."""
    return f"{MCP_TOOL_PREFIX}{server_key}{MCP_TOOL_SEPARATOR}{tool_name}"


def mcp_resource_tool_id(server_key: str, uri: str) -> str:
    """Synthetic tool ID for a resource: 'mcp_<server>__read_resource__<uri_hash12>'."""
    digest = hashlib.sha256(uri.encode("utf-8")).hexdigest()[:12]
    return f"{MCP_TOOL_PREFIX}{server_key}{MCP_TOOL_SEPARATOR}{MCP_RESOURCE_INFIX}{digest}"


def mcp_prompt_tool_id(server_key: str, prompt_name: str) -> str:
    """Synthetic tool ID for a prompt: 'mcp_<server>__prompt__<name>'."""
    safe_name = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in prompt_name)
    return f"{MCP_TOOL_PREFIX}{server_key}{MCP_TOOL_SEPARATOR}{MCP_PROMPT_INFIX}{safe_name}"


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


def _blocked_mcp_capability_names(agent_id: str, server_key: str, kind: str) -> set[str]:
    """Return the set of capability_name values whose policy is 'blocked'.

    ``kind`` ∈ {"tool", "resource", "prompt"}. Reads from
    ``cp_mcp_capability_policies`` (the unified table). Returns an empty set
    on any error to avoid blocking the agent on transient DB issues.
    """
    try:
        from koda.control_plane.manager import get_control_plane_manager

        grouped = get_control_plane_manager().list_mcp_capability_policies(agent_id, server_key)
        bucket_key = {"tool": "tools", "resource": "resources", "prompt": "prompts"}[kind]
        return {
            str(row.get("capability_name") or "")
            for row in grouped.get(bucket_key, [])
            if str(row.get("policy") or "") == "blocked"
        }
    except Exception:
        return set()


# Per-agent index of synthetic resource/prompt tool IDs → (uri, prompt_name).
# Populated at registration time so the handlers can resolve the underlying
# capability name without re-hashing each invocation.
_agent_resource_lookup: dict[tuple[str, str], tuple[str, str]] = {}
_agent_prompt_lookup: dict[tuple[str, str], tuple[str, str]] = {}


async def handle_mcp_resource_call(
    tool_id: str,
    params: dict[str, Any],
    agent_id: str,
) -> dict[str, Any]:
    """Read a resource via ``resources/read`` and return its body."""
    parsed = parse_mcp_tool_id(tool_id)
    if parsed is None:
        return {"success": False, "output": f"Invalid MCP resource tool ID: {tool_id}", "metadata": {}}
    server_key, _ = parsed
    pair = _agent_resource_lookup.get((agent_id, tool_id))
    if pair is None:
        return {
            "success": False,
            "output": f"Unknown MCP resource for tool ID {tool_id}",
            "metadata": {"server_key": server_key, "tool_id": tool_id},
        }
    _, uri = pair
    instance = mcp_server_manager.get_instance(server_key, agent_id)
    if instance is None or not instance.started:
        try:
            instance = await _lazy_start_mcp_server(server_key, agent_id)
        except Exception as exc:
            return {
                "success": False,
                "output": f"MCP server '{server_key}' failed to start: {exc}",
                "metadata": {"server_key": server_key, "uri": uri, "error": str(exc)},
            }
    if instance is None or instance.session is None:
        return {
            "success": False,
            "output": f"MCP server '{server_key}' has no active session",
            "metadata": {"server_key": server_key, "uri": uri},
        }
    try:
        result = await instance.session.read_resource(uri)
        instance.touch()
        snippets: list[str] = []
        for content in result.contents:
            if "text" in content:
                snippets.append(str(content.get("text") or ""))
            elif "blob" in content:
                snippets.append(f"[binary content: {content.get('mimeType', 'unknown')}]")
            else:
                snippets.append(json.dumps(content, ensure_ascii=False))
        output = "\n".join(snippets) if snippets else "(empty resource)"
        return {
            "success": True,
            "output": output,
            "metadata": {"integration_id": "mcp", "server_key": server_key, "uri": uri},
        }
    except Exception as exc:
        log.warning("mcp_resource_read_error", server_key=server_key, uri=uri, error=str(exc))
        return {
            "success": False,
            "output": f"MCP resource read error: {exc}",
            "metadata": {"server_key": server_key, "uri": uri, "error": str(exc)},
        }


async def handle_mcp_prompt_call(
    tool_id: str,
    params: dict[str, Any],
    agent_id: str,
) -> dict[str, Any]:
    """Render an MCP prompt template via ``prompts/get`` with the given arguments."""
    parsed = parse_mcp_tool_id(tool_id)
    if parsed is None:
        return {"success": False, "output": f"Invalid MCP prompt tool ID: {tool_id}", "metadata": {}}
    server_key, _ = parsed
    pair = _agent_prompt_lookup.get((agent_id, tool_id))
    if pair is None:
        return {
            "success": False,
            "output": f"Unknown MCP prompt for tool ID {tool_id}",
            "metadata": {"server_key": server_key, "tool_id": tool_id},
        }
    _, prompt_name = pair
    instance = mcp_server_manager.get_instance(server_key, agent_id)
    if instance is None or not instance.started:
        try:
            instance = await _lazy_start_mcp_server(server_key, agent_id)
        except Exception as exc:
            return {
                "success": False,
                "output": f"MCP server '{server_key}' failed to start: {exc}",
                "metadata": {"server_key": server_key, "prompt": prompt_name, "error": str(exc)},
            }
    if instance is None or instance.session is None:
        return {
            "success": False,
            "output": f"MCP server '{server_key}' has no active session",
            "metadata": {"server_key": server_key, "prompt": prompt_name},
        }
    try:
        arguments = params.get("arguments") if isinstance(params, dict) else None
        result = await instance.session.get_prompt(prompt_name, arguments if isinstance(arguments, dict) else None)
        instance.touch()
        rendered_messages = [json.dumps(m, ensure_ascii=False) for m in result.messages]
        output_parts = [result.description or "", *rendered_messages]
        return {
            "success": True,
            "output": "\n".join(part for part in output_parts if part),
            "metadata": {
                "integration_id": "mcp",
                "server_key": server_key,
                "prompt": prompt_name,
                "messages": result.messages,
            },
        }
    except Exception as exc:
        log.warning("mcp_prompt_render_error", server_key=server_key, prompt=prompt_name, error=str(exc))
        return {
            "success": False,
            "output": f"MCP prompt error: {exc}",
            "metadata": {"server_key": server_key, "prompt": prompt_name, "error": str(exc)},
        }


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
    """Create an async handler closure for an MCP tool/resource/prompt.

    The returned callable matches the ``_ToolHandler`` signature used by
    ``tool_dispatcher._TOOL_HANDLERS``:
        async (params: dict, ctx: ToolContext) -> AgentToolResult
    """

    async def handler(params: dict, ctx: Any) -> Any:  # noqa: ANN401
        from koda.services.tool_dispatcher import AgentToolResult

        # Synthetic IDs get routed to the resource / prompt handler. Native
        # MCP tools fall through to handle_mcp_tool_call (the default path).
        if MCP_RESOURCE_INFIX in tool_id:
            result = await handle_mcp_resource_call(tool_id, params, agent_id)
        elif MCP_PROMPT_INFIX in tool_id:
            result = await handle_mcp_prompt_call(tool_id, params, agent_id)
        else:
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
    """Remove all MCP tool/resource/prompt handlers for an agent."""
    agent_tools = _agent_mcp_tools.pop(agent_id, set())
    for tid in agent_tools:
        tool_handlers.pop(tid, None)
        write_tools.discard(tid)
        read_tools.discard(tid)
        _agent_resource_lookup.pop((agent_id, tid), None)
        _agent_prompt_lookup.pop((agent_id, tid), None)
    if agent_tools:
        log.info("mcp_tools_unregistered", agent_id=agent_id, count=len(agent_tools))


def register_mcp_resources_for_agent(
    agent_id: str,
    server_key: str,
    resources: list[dict[str, Any]],
    tool_handlers: dict[str, Any],
    read_tools: set[str],
) -> list[str]:
    """Register synthetic ``read_resource`` tools for the agent's resources.

    Resources are read-only by definition; entries with ``policy='blocked'``
    are skipped so the agent never sees them in the tool prompt.
    """
    blocked = _blocked_mcp_capability_names(agent_id, server_key, "resource")
    registered: list[str] = []
    agent_tools = _agent_mcp_tools.setdefault(agent_id, set())
    for resource in resources:
        uri = str(resource.get("uri") or "")
        if not uri or uri in blocked:
            continue
        tid = mcp_resource_tool_id(server_key, uri)
        tool_handlers[tid] = _make_mcp_handler(tid, agent_id)
        read_tools.add(tid)
        agent_tools.add(tid)
        _agent_resource_lookup[(agent_id, tid)] = (server_key, uri)
        registered.append(tid)
    if registered:
        log.info(
            "mcp_resources_registered",
            agent_id=agent_id,
            server_key=server_key,
            count=len(registered),
        )
    return registered


def register_mcp_prompts_for_agent(
    agent_id: str,
    server_key: str,
    prompts: list[dict[str, Any]],
    tool_handlers: dict[str, Any],
    write_tools: set[str],
) -> list[str]:
    """Register synthetic ``prompt__<name>`` tools for the agent's prompts.

    Prompts are classified as write operations because rendering one feeds
    a multi-message envelope back into the agent's context — a side-effecting
    action from the runtime's perspective. ``policy='blocked'`` prompts are
    skipped.
    """
    blocked = _blocked_mcp_capability_names(agent_id, server_key, "prompt")
    registered: list[str] = []
    agent_tools = _agent_mcp_tools.setdefault(agent_id, set())
    for prompt in prompts:
        name = str(prompt.get("name") or "")
        if not name or name in blocked:
            continue
        tid = mcp_prompt_tool_id(server_key, name)
        tool_handlers[tid] = _make_mcp_handler(tid, agent_id)
        write_tools.add(tid)
        agent_tools.add(tid)
        _agent_prompt_lookup[(agent_id, tid)] = (server_key, name)
        registered.append(tid)
    if registered:
        log.info(
            "mcp_prompts_registered",
            agent_id=agent_id,
            server_key=server_key,
            count=len(registered),
        )
    return registered


def register_mcp_capabilities_for_agent(
    agent_id: str,
    server_key: str,
    cached_tools: list[dict[str, Any]],
    cached_resources: list[dict[str, Any]],
    cached_prompts: list[dict[str, Any]],
    tool_handlers: dict[str, Any],
    write_tools: set[str],
    read_tools: set[str],
) -> dict[str, list[str]]:
    """Register tools + resources + prompts in one call.

    Returns a dict ``{tools: [...], resources: [...], prompts: [...]}`` of the
    registered tool IDs.
    """
    tool_ids = register_mcp_tools_for_agent(
        agent_id,
        [{"server_key": server_key, "cached_tools": cached_tools}],
        tool_handlers,
        write_tools,
        read_tools,
    )
    resource_ids = register_mcp_resources_for_agent(agent_id, server_key, cached_resources, tool_handlers, read_tools)
    prompt_ids = register_mcp_prompts_for_agent(agent_id, server_key, cached_prompts, tool_handlers, write_tools)
    return {"tools": tool_ids, "resources": resource_ids, "prompts": prompt_ids}


def get_registered_mcp_tools(agent_id: str) -> set[str]:
    """Get set of registered MCP tool IDs for an agent."""
    return set(_agent_mcp_tools.get(agent_id, set()))
