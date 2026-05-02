"""Capability discovery service for MCP servers.

Coordinates the live discovery of all three MCP primitives — tools, resources,
and prompts — as well as server identity (``initialize``) for an
``(agent_id, server_key)`` pair, persisting the result into
``cp_mcp_capability_snapshots`` (with a TTL) and into the per-kind discovered
tables (``cp_mcp_discovered_tools``, ``cp_mcp_discovered_resources``,
``cp_mcp_discovered_prompts``).

This module is the source of truth for "what does this MCP server expose?".
The legacy ``manager.discover_mcp_tools`` continues to work for
backwards-compat with existing routes, but new code should call
:func:`verify_capabilities` instead.
"""

from __future__ import annotations

import contextlib
import hashlib
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from koda.control_plane.database import execute, fetch_one, json_dump, json_load, now_iso, run_coro_sync
from koda.logging_config import get_logger
from koda.services.mcp_client import (
    McpPrompt,
    McpResource,
    McpResourceTemplate,
    McpToolDefinition,
)
from koda.services.mcp_manager import McpServerInstance

logger = get_logger(__name__)

DEFAULT_SNAPSHOT_TTL_SECONDS = 3600


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CapabilitySnapshot:
    """Cached snapshot of a server's discovered capabilities."""

    agent_id: str
    server_key: str
    server_info: dict[str, Any] = field(default_factory=dict)
    server_capabilities: dict[str, Any] = field(default_factory=dict)
    tools: list[dict[str, Any]] = field(default_factory=list)
    resources: list[dict[str, Any]] = field(default_factory=list)
    resource_templates: list[dict[str, Any]] = field(default_factory=list)
    prompts: list[dict[str, Any]] = field(default_factory=list)
    captured_at: str = ""
    ttl_seconds: int = DEFAULT_SNAPSHOT_TTL_SECONDS
    error: str | None = None
    protocol_version: str | None = None

    def to_payload(self) -> dict[str, Any]:
        """Serialize to a dict suitable for HTTP responses."""
        return {
            "agent_id": self.agent_id,
            "server_key": self.server_key,
            "server_info": self.server_info,
            "server_capabilities": self.server_capabilities,
            "tools": self.tools,
            "resources": self.resources,
            "resource_templates": self.resource_templates,
            "prompts": self.prompts,
            "captured_at": self.captured_at,
            "ttl_seconds": self.ttl_seconds,
            "error": self.error,
            "protocol_version": self.protocol_version,
            "summary": {
                "tool_count": len(self.tools),
                "resource_count": len(self.resources),
                "resource_template_count": len(self.resource_templates),
                "prompt_count": len(self.prompts),
            },
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def verify_capabilities(
    agent_id: str,
    server_key: str,
    *,
    force_refresh: bool = False,
    ttl_seconds: int = DEFAULT_SNAPSHOT_TTL_SECONDS,
) -> CapabilitySnapshot:
    """Return capabilities for the given agent/server pair.

    Behavior:

    - If ``force_refresh=False`` and a fresh snapshot exists in
      ``cp_mcp_capability_snapshots``, returns it without spawning the server.
    - Otherwise resolves the runtime payload (catalog + agent connection),
      starts a temporary :class:`McpServerInstance`, runs ``initialize`` plus
      ``tools/list``, ``resources/list``, ``resources/templates/list``, and
      ``prompts/list``, persists results, and returns the new snapshot.
    """
    cached = _load_snapshot(agent_id, server_key)
    if cached is not None and not force_refresh and not _is_stale(cached):
        return cached

    payload = _resolve_runtime_payload(agent_id, server_key)
    if payload is None:
        snapshot = CapabilitySnapshot(
            agent_id=agent_id,
            server_key=server_key,
            captured_at=now_iso(),
            ttl_seconds=ttl_seconds,
            error="connection_not_found",
        )
        _persist_snapshot(snapshot)
        return snapshot

    instance = McpServerInstance(
        server_key=server_key,
        agent_id=agent_id,
        transport_type=str(payload.get("transport_type") or "stdio"),
        command=payload.get("command") or None,
        url=payload.get("url"),
        env=payload.get("env_values") or None,
        headers=payload.get("headers") or None,
    )

    snapshot = CapabilitySnapshot(
        agent_id=agent_id,
        server_key=server_key,
        captured_at=now_iso(),
        ttl_seconds=ttl_seconds,
    )

    try:
        run_coro_sync(instance.start())
        session = instance.session
        if session is None:
            raise RuntimeError("session not available after start")

        snapshot.server_info = session.server_info
        snapshot.server_capabilities = session.server_capabilities
        snapshot.protocol_version = session.protocol_version

        snapshot.tools = [_tool_to_payload(tool) for tool in instance.cached_tools]

        # resources / prompts are best-effort: servers that don't advertise
        # the capability return empty lists; method-not-found errors are
        # silently treated as "not supported" by the session itself.
        with contextlib.suppress(Exception):
            resources = run_coro_sync(session.list_resources())
            snapshot.resources = [_resource_to_payload(r) for r in resources]
        with contextlib.suppress(Exception):
            templates = run_coro_sync(session.list_resource_templates())
            snapshot.resource_templates = [_resource_template_to_payload(t) for t in templates]
        with contextlib.suppress(Exception):
            prompts = run_coro_sync(session.list_prompts())
            snapshot.prompts = [_prompt_to_payload(p) for p in prompts]
    except Exception as exc:
        snapshot.error = str(exc)
        logger.warning(
            "mcp_capability_discovery_failed",
            agent_id=agent_id,
            server_key=server_key,
            error=str(exc),
        )
    finally:
        with contextlib.suppress(Exception):
            run_coro_sync(instance.stop())

    snapshot.captured_at = now_iso()
    _persist_snapshot(snapshot)
    if snapshot.error is None:
        _persist_discovered_resources(agent_id, server_key, snapshot.resources, snapshot.resource_templates)
        _persist_discovered_prompts(agent_id, server_key, snapshot.prompts)
    return snapshot


def get_capability_snapshot(agent_id: str, server_key: str) -> CapabilitySnapshot | None:
    """Return the cached snapshot, if any, regardless of staleness."""
    return _load_snapshot(agent_id, server_key)


def invalidate_snapshot(agent_id: str, server_key: str) -> None:
    """Remove cached snapshot + discovered tables for an agent/server pair."""
    execute(
        "DELETE FROM cp_mcp_capability_snapshots WHERE agent_id = ? AND server_key = ?",
        (agent_id, server_key),
    )
    execute(
        "DELETE FROM cp_mcp_discovered_resources WHERE agent_id = ? AND server_key = ?",
        (agent_id, server_key),
    )
    execute(
        "DELETE FROM cp_mcp_discovered_prompts WHERE agent_id = ? AND server_key = ?",
        (agent_id, server_key),
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _is_stale(snapshot: CapabilitySnapshot) -> bool:
    if snapshot.error:
        return True  # always retry on previous error
    captured_at = snapshot.captured_at
    if not captured_at:
        return True
    try:
        from datetime import datetime

        ts = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
        age = time.time() - ts.timestamp()
        return age > snapshot.ttl_seconds
    except Exception:
        return True


def _resolve_runtime_payload(agent_id: str, server_key: str) -> dict[str, Any] | None:
    """Reuse manager's resolution path to avoid duplicating credential glue."""
    from koda.control_plane.manager import get_control_plane_manager

    try:
        return get_control_plane_manager()._resolve_mcp_runtime_payload(agent_id, server_key)
    except KeyError:
        return None
    except Exception as exc:
        logger.warning(
            "mcp_runtime_payload_resolution_failed",
            agent_id=agent_id,
            server_key=server_key,
            error=str(exc),
        )
        return None


def _persist_snapshot(snapshot: CapabilitySnapshot) -> None:
    execute(
        """
        INSERT INTO cp_mcp_capability_snapshots
            (agent_id, server_key, server_info_json, server_capabilities_json,
             tools_json, resources_json, resource_templates_json, prompts_json,
             captured_at, ttl_seconds, error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (agent_id, server_key) DO UPDATE SET
            server_info_json = EXCLUDED.server_info_json,
            server_capabilities_json = EXCLUDED.server_capabilities_json,
            tools_json = EXCLUDED.tools_json,
            resources_json = EXCLUDED.resources_json,
            resource_templates_json = EXCLUDED.resource_templates_json,
            prompts_json = EXCLUDED.prompts_json,
            captured_at = EXCLUDED.captured_at,
            ttl_seconds = EXCLUDED.ttl_seconds,
            error = EXCLUDED.error
        """,
        (
            snapshot.agent_id,
            snapshot.server_key,
            json_dump(snapshot.server_info),
            json_dump(snapshot.server_capabilities),
            json_dump(snapshot.tools),
            json_dump(snapshot.resources),
            json_dump(snapshot.resource_templates),
            json_dump(snapshot.prompts),
            snapshot.captured_at,
            int(snapshot.ttl_seconds),
            snapshot.error,
        ),
    )


def _load_snapshot(agent_id: str, server_key: str) -> CapabilitySnapshot | None:
    row = fetch_one(
        "SELECT * FROM cp_mcp_capability_snapshots WHERE agent_id = ? AND server_key = ?",
        (agent_id, server_key),
    )
    if row is None:
        return None
    return CapabilitySnapshot(
        agent_id=str(row.get("agent_id") or agent_id),
        server_key=str(row.get("server_key") or server_key),
        server_info=json_load(str(row.get("server_info_json") or "{}"), {}),
        server_capabilities=json_load(str(row.get("server_capabilities_json") or "{}"), {}),
        tools=json_load(str(row.get("tools_json") or "[]"), []),
        resources=json_load(str(row.get("resources_json") or "[]"), []),
        resource_templates=json_load(str(row.get("resource_templates_json") or "[]"), []),
        prompts=json_load(str(row.get("prompts_json") or "[]"), []),
        captured_at=str(row.get("captured_at") or ""),
        ttl_seconds=int(row.get("ttl_seconds") or DEFAULT_SNAPSHOT_TTL_SECONDS),
        error=row.get("error"),
    )


def _persist_discovered_resources(
    agent_id: str,
    server_key: str,
    resources: list[dict[str, Any]],
    templates: list[dict[str, Any]],
) -> None:
    execute(
        "DELETE FROM cp_mcp_discovered_resources WHERE agent_id = ? AND server_key = ?",
        (agent_id, server_key),
    )
    now = now_iso()
    for res in resources:
        uri = str(res.get("uri") or "")
        if not uri:
            continue
        uri_hash = _uri_hash(uri)
        execute(
            """
            INSERT INTO cp_mcp_discovered_resources
                (agent_id, server_key, uri_hash, uri, name, description,
                 mime_type, is_template, annotations_json, schema_hash,
                 discovered_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (agent_id, server_key, uri_hash) DO UPDATE SET
                uri = EXCLUDED.uri,
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                mime_type = EXCLUDED.mime_type,
                is_template = EXCLUDED.is_template,
                annotations_json = EXCLUDED.annotations_json,
                schema_hash = EXCLUDED.schema_hash,
                updated_at = EXCLUDED.updated_at
            """,
            (
                agent_id,
                server_key,
                uri_hash,
                uri,
                res.get("name"),
                res.get("description"),
                res.get("mime_type"),
                0,
                json_dump(res.get("annotations") or {}),
                _resource_schema_hash(res),
                now,
                now,
            ),
        )
    for tmpl in templates:
        uri_template = str(tmpl.get("uri_template") or "")
        if not uri_template:
            continue
        uri_hash = _uri_hash(uri_template)
        execute(
            """
            INSERT INTO cp_mcp_discovered_resources
                (agent_id, server_key, uri_hash, uri, name, description,
                 mime_type, is_template, annotations_json, schema_hash,
                 discovered_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (agent_id, server_key, uri_hash) DO UPDATE SET
                uri = EXCLUDED.uri,
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                mime_type = EXCLUDED.mime_type,
                is_template = EXCLUDED.is_template,
                schema_hash = EXCLUDED.schema_hash,
                updated_at = EXCLUDED.updated_at
            """,
            (
                agent_id,
                server_key,
                uri_hash,
                uri_template,
                tmpl.get("name"),
                tmpl.get("description"),
                tmpl.get("mime_type"),
                1,
                "{}",
                _resource_schema_hash(tmpl),
                now,
                now,
            ),
        )


def _persist_discovered_prompts(
    agent_id: str,
    server_key: str,
    prompts: list[dict[str, Any]],
) -> None:
    execute(
        "DELETE FROM cp_mcp_discovered_prompts WHERE agent_id = ? AND server_key = ?",
        (agent_id, server_key),
    )
    now = now_iso()
    for prompt in prompts:
        name = str(prompt.get("name") or "")
        if not name:
            continue
        execute(
            """
            INSERT INTO cp_mcp_discovered_prompts
                (agent_id, server_key, prompt_name, description, arguments_json,
                 schema_hash, discovered_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (agent_id, server_key, prompt_name) DO UPDATE SET
                description = EXCLUDED.description,
                arguments_json = EXCLUDED.arguments_json,
                schema_hash = EXCLUDED.schema_hash,
                updated_at = EXCLUDED.updated_at
            """,
            (
                agent_id,
                server_key,
                name,
                prompt.get("description"),
                json_dump(prompt.get("arguments") or []),
                _prompt_schema_hash(prompt),
                now,
                now,
            ),
        )


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------


def _tool_to_payload(tool: McpToolDefinition) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.input_schema,
    }
    if tool.annotations:
        payload["annotations"] = {
            "title": tool.annotations.title,
            "read_only_hint": tool.annotations.read_only_hint,
            "destructive_hint": tool.annotations.destructive_hint,
            "idempotent_hint": tool.annotations.idempotent_hint,
            "open_world_hint": tool.annotations.open_world_hint,
        }
    return payload


def _resource_to_payload(resource: McpResource) -> dict[str, Any]:
    return {
        "uri": resource.uri,
        "name": resource.name,
        "description": resource.description,
        "mime_type": resource.mime_type,
        "annotations": dict(resource.annotations or {}),
    }


def _resource_template_to_payload(template: McpResourceTemplate) -> dict[str, Any]:
    return {
        "uri_template": template.uri_template,
        "name": template.name,
        "description": template.description,
        "mime_type": template.mime_type,
    }


def _prompt_to_payload(prompt: McpPrompt) -> dict[str, Any]:
    return {
        "name": prompt.name,
        "description": prompt.description,
        "arguments": [asdict(arg) for arg in (prompt.arguments or ())],
    }


def _uri_hash(uri: str) -> str:
    return hashlib.sha256(uri.encode("utf-8")).hexdigest()


def _resource_schema_hash(resource: dict[str, Any]) -> str:
    payload = {
        "name": resource.get("name"),
        "mime_type": resource.get("mime_type"),
        "is_template": bool(resource.get("uri_template")),
    }
    return hashlib.sha256(json_dump(payload).encode("utf-8")).hexdigest()


def _prompt_schema_hash(prompt: dict[str, Any]) -> str:
    payload = {
        "arguments": prompt.get("arguments") or [],
    }
    return hashlib.sha256(json_dump(payload).encode("utf-8")).hexdigest()
