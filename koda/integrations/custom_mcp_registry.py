"""User-defined MCP server registry — both system-wide and per-agent custom
entries.

Two storage tiers:

* **System-wide custom servers** live in ``cp_mcp_server_catalog`` with
  ``is_custom=1``. They're available to every agent and managed by the
  operator/admin.
* **Per-agent custom servers** live in ``cp_mcp_user_servers``. They scope to
  a single agent.

Both tiers accept the same payload shape, including a Claude Desktop
compatible JSON paste so users can copy directly from provider docs.

The registry validates payloads aggressively because a custom entry is the
easiest path to host code execution. See :func:`validate_payload` for the
exact rules; the runtime sandbox in ``mcp_isolation.py`` is the second line of
defense.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass, field
from typing import Any

from koda.control_plane.database import execute, fetch_all, fetch_one, json_dump, json_load, now_iso
from koda.logging_config import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Allowlists / denylists
# ---------------------------------------------------------------------------

# Commands that are permitted as the first argv element for a stdio MCP.
# Reasoning: each is a well-known package runner / interpreter that we'll wrap
# in the OS-level sandbox at runtime. Anything not in this list is rejected
# at registration to neutralize obvious foot-guns (e.g. ``rm`` as command).
SAFE_STDIO_COMMANDS: frozenset[str] = frozenset(
    {
        "npx",
        "uvx",
        "node",
        "python",
        "python3",
        "deno",
        "bun",
        "docker",
    }
)

# Env vars that must NEVER appear in a custom server's env_schema or values.
# These are platform-level escapes (preload libraries, PATH overrides) that
# would let a custom server bypass the sandbox.
FORBIDDEN_ENV_NAMES: frozenset[str] = frozenset(
    {
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "LD_AUDIT",
        "DYLD_INSERT_LIBRARIES",
        "DYLD_LIBRARY_PATH",
        "DYLD_FRAMEWORK_PATH",
        "PATH",
        "NODE_OPTIONS",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "BASH_ENV",
        "ENV",
        "GOPATH",
        "RUBYLIB",
        "RUBYOPT",
    }
)

# HTTP request headers permitted on remote MCP servers (header NAMES, not
# values; values come from env).
SAFE_HTTP_HEADERS: frozenset[str] = frozenset(
    {
        "Authorization",
        "X-API-Key",
        "X-Api-Key",
        "X-Auth-Token",
        "X-OpenAI-Api-Key",
        "User-Agent",
    }
)

# Server-key prefix that all custom (user-defined) entries must start with.
# Prevents collisions with curated keys and makes audit trails greppable.
CUSTOM_SERVER_PREFIX = "custom_"

# Reserved curated keys that cannot be overwritten by custom entries.
# Mirrors koda/control_plane/manager.py::_RESERVED_MCP_SERVER_KEYS so
# callers do not need to import private helpers.
RESERVED_KEYS: frozenset[str] = frozenset(
    {
        "docker",
        "filesystem",
        "github",
        "gitlab",
        "memory",
        "puppeteer",
    }
)

_SLUG_RE = re.compile(r"[^a-z0-9_-]+")
_KEY_FORMAT_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


# ---------------------------------------------------------------------------
# Payload model
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CustomServerPayload:
    """Normalized payload accepted by ``upsert``."""

    server_key: str
    display_name: str
    description: str = ""
    transport_type: str = "stdio"
    command: list[str] = field(default_factory=list)
    args: list[str] = field(default_factory=list)
    url: str | None = None
    headers_schema: list[dict[str, Any]] = field(default_factory=list)
    env_schema: list[dict[str, Any]] = field(default_factory=list)
    auth_strategy: str = "no_auth"
    oauth_config: dict[str, Any] = field(default_factory=dict)
    isolation_profile: str = "auto"
    isolation_constraints: dict[str, Any] = field(default_factory=dict)
    runtime_constraints: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    source: str = "manual"


@dataclass(slots=True)
class ImportError_:
    """Per-server error during Claude Desktop JSON import."""

    name: str
    message: str


@dataclass(slots=True)
class ImportResult:
    """Outcome of a multi-server import (Claude Desktop JSON paste)."""

    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    errors: list[ImportError_] = field(default_factory=list)


class ValidationError(ValueError):
    """Raised when a custom server payload fails validation."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def normalize_server_key(slug: str) -> str:
    """Return a normalized ``custom_<slug>`` key."""
    cleaned = _SLUG_RE.sub("-", str(slug or "").strip().lower()).strip("-_")
    if not cleaned:
        raise ValidationError("server_key cannot be empty")
    if cleaned.startswith(CUSTOM_SERVER_PREFIX):
        return cleaned
    return f"{CUSTOM_SERVER_PREFIX}{cleaned}"


def validate_payload(payload: CustomServerPayload, *, secret_key: bytes | None = None) -> None:
    """Validate a custom server payload, raising :class:`ValidationError`."""
    key = payload.server_key
    if not _KEY_FORMAT_RE.match(key):
        raise ValidationError(f"server_key must match {_KEY_FORMAT_RE.pattern}: {key!r}")
    if not key.startswith(CUSTOM_SERVER_PREFIX):
        raise ValidationError(f"server_key for custom entries must start with '{CUSTOM_SERVER_PREFIX}'")
    if key.removeprefix(CUSTOM_SERVER_PREFIX) in RESERVED_KEYS:
        raise ValidationError(f"server_key {key!r} is reserved")

    if not payload.display_name or not payload.display_name.strip():
        raise ValidationError("display_name is required")

    transport = payload.transport_type
    if transport not in {"stdio", "http_sse"}:
        raise ValidationError(f"unsupported transport_type: {transport!r}")

    if transport == "stdio":
        if not payload.command:
            raise ValidationError("stdio transport requires a command")
        head = payload.command[0]
        if not head:
            raise ValidationError("command[0] cannot be empty")
        if head.startswith("/") or head.startswith("./") or head.startswith("../"):
            raise ValidationError(f"command must not be a filesystem path: {head!r}")
        if head not in SAFE_STDIO_COMMANDS:
            raise ValidationError(f"command {head!r} not in allowlist {sorted(SAFE_STDIO_COMMANDS)}")
        for arg in payload.command[1:] + payload.args:
            if not isinstance(arg, str):
                raise ValidationError("args must be strings")
            if "\x00" in arg:
                raise ValidationError("args cannot contain null bytes")
            if len(arg) > 500:
                raise ValidationError("each arg must be ≤ 500 chars")
    else:  # http_sse
        if not payload.url:
            raise ValidationError("http_sse transport requires a URL")
        # Allow localhost over plain http so devs can register MCP servers
        # they're running on their machine. Public hosts must use HTTPS.
        _validate_http_url(payload.url, allow_localhost=True)
        for header in payload.headers_schema:
            name = str(header.get("key") or header.get("name") or "")
            if not name:
                raise ValidationError("headers_schema entries need a key")
            if name not in SAFE_HTTP_HEADERS:
                raise ValidationError(f"header {name!r} not in allowlist {sorted(SAFE_HTTP_HEADERS)}")

    if len(payload.env_schema) > 64:
        raise ValidationError("env_schema cannot exceed 64 entries")
    total_env_size = 0
    for field_def in payload.env_schema:
        env_name = str(field_def.get("key") or "")
        if not _ENV_NAME_RE.match(env_name):
            raise ValidationError(f"env name {env_name!r} must match {_ENV_NAME_RE.pattern}")
        if env_name in FORBIDDEN_ENV_NAMES:
            raise ValidationError(f"env name {env_name!r} is forbidden")
        if env_name.startswith("KODA_"):
            raise ValidationError(f"env name {env_name!r} is reserved (KODA_*)")
        total_env_size += len(env_name) + len(str(field_def.get("label") or ""))
    if total_env_size > 4096:
        raise ValidationError("env_schema total size exceeds 4KB")

    if payload.auth_strategy not in {"no_auth", "api_key", "oauth", "connection_string", "dual_token"}:
        raise ValidationError(f"unsupported auth_strategy: {payload.auth_strategy!r}")

    # Stamp a HMAC signature on the load-bearing fields so any later runtime
    # tampering with the DB row is detectable.
    if secret_key is not None:
        signature = compute_validation_signature(payload, secret_key)
        payload.metadata["validation_signature"] = signature


def compute_validation_signature(payload: CustomServerPayload, secret: bytes) -> str:
    body = json_dump(
        {
            "server_key": payload.server_key,
            "transport_type": payload.transport_type,
            "command": payload.command,
            "args": payload.args,
            "url": payload.url,
            "env_keys": sorted(str(field_def.get("key") or "") for field_def in payload.env_schema),
            "auth_strategy": payload.auth_strategy,
        }
    )
    return hmac.new(secret, body.encode("utf-8"), hashlib.sha256).hexdigest()


def list_custom_servers(*, agent_id: str | None = None) -> list[dict[str, Any]]:
    """Return all custom servers visible to the caller.

    ``agent_id=None`` → system-wide custom rows from ``cp_mcp_server_catalog``.
    Otherwise: union of system-wide custom rows AND per-agent rows from
    ``cp_mcp_user_servers``, with per-agent winning when keys overlap.
    """
    rows: list[dict[str, Any]] = []
    system_rows = fetch_all("SELECT * FROM cp_mcp_server_catalog WHERE is_custom = 1 ORDER BY server_key")
    for row in system_rows:
        rows.append(_serialize_system_row(row))
    if agent_id:
        agent_rows = fetch_all(
            "SELECT * FROM cp_mcp_user_servers WHERE agent_id = ? ORDER BY server_key",
            (agent_id,),
        )
        keys_seen = {entry["server_key"] for entry in rows}
        for row in agent_rows:
            payload = _serialize_user_row(row)
            if payload["server_key"] in keys_seen:
                # Per-agent overrides system-wide: replace the existing entry.
                rows = [r for r in rows if r["server_key"] != payload["server_key"]]
            rows.append(payload)
    return sorted(rows, key=lambda r: r["server_key"])


def get_custom_server(server_key: str, *, agent_id: str | None = None) -> dict[str, Any] | None:
    if agent_id:
        row = fetch_one(
            "SELECT * FROM cp_mcp_user_servers WHERE agent_id = ? AND server_key = ?",
            (agent_id, server_key),
        )
        if row is not None:
            return _serialize_user_row(row)
    row = fetch_one(
        "SELECT * FROM cp_mcp_server_catalog WHERE server_key = ? AND is_custom = 1",
        (server_key,),
    )
    if row is None:
        return None
    return _serialize_system_row(row)


def upsert_custom_server(
    payload: CustomServerPayload,
    *,
    agent_id: str | None = None,
    owner_user_id: str | None = None,
    secret_key: bytes | None = None,
) -> dict[str, Any]:
    """Persist a custom server (system-wide if ``agent_id`` is None)."""
    payload.server_key = normalize_server_key(payload.server_key)
    validate_payload(payload, secret_key=secret_key)

    now = now_iso()
    if agent_id is None:
        return _upsert_system_row(payload, owner_user_id=owner_user_id, now=now)
    return _upsert_user_row(payload, agent_id=agent_id, owner_user_id=owner_user_id, now=now)


def delete_custom_server(server_key: str, *, agent_id: str | None = None) -> bool:
    """Remove a custom server. Returns True if a row was deleted."""
    if agent_id is not None:
        deleted = execute(
            "DELETE FROM cp_mcp_user_servers WHERE agent_id = ? AND server_key = ?",
            (agent_id, server_key),
        )
        return deleted > 0
    deleted = execute(
        "DELETE FROM cp_mcp_server_catalog WHERE server_key = ? AND is_custom = 1",
        (server_key,),
    )
    if deleted:
        execute("DELETE FROM cp_mcp_user_servers WHERE server_key = ?", (server_key,))
        execute("DELETE FROM cp_mcp_capability_snapshots WHERE server_key = ?", (server_key,))
        execute("DELETE FROM cp_mcp_discovered_resources WHERE server_key = ?", (server_key,))
        execute("DELETE FROM cp_mcp_discovered_prompts WHERE server_key = ?", (server_key,))
        execute("DELETE FROM cp_mcp_capability_policies WHERE server_key = ?", (server_key,))
    return deleted > 0


def import_claude_desktop_json(
    raw: dict[str, Any],
    *,
    agent_id: str | None = None,
    owner_user_id: str | None = None,
    secret_key: bytes | None = None,
) -> ImportResult:
    """Import a Claude Desktop / cursor.config.json compatible payload.

    Expected shape::

        {
          "mcpServers": {
            "linear": {
              "url": "https://mcp.linear.app/mcp",
              "transport": "http_sse"
            },
            "my-server": {
              "command": "npx",
              "args": ["-y", "@org/mcp"],
              "env": { "MY_TOKEN": "" }
            }
          }
        }

    Each entry becomes one custom server row. Multi-server imports are atomic
    per-entry: a failure on one entry does not roll back others.
    """
    result = ImportResult()
    servers = raw.get("mcpServers")
    if not isinstance(servers, dict):
        result.errors.append(ImportError_("(root)", "missing 'mcpServers' object"))
        return result

    for raw_name, spec in servers.items():
        if not isinstance(spec, dict):
            result.errors.append(ImportError_(str(raw_name), "entry must be an object"))
            continue
        try:
            payload = _payload_from_claude_desktop(str(raw_name), spec)
            existed_before = get_custom_server(payload.server_key, agent_id=agent_id) is not None
            saved = upsert_custom_server(
                payload,
                agent_id=agent_id,
                owner_user_id=owner_user_id,
                secret_key=secret_key,
            )
            if existed_before:
                result.updated.append(saved["server_key"])
            else:
                result.created.append(saved["server_key"])
        except ValidationError as exc:
            result.errors.append(ImportError_(str(raw_name), str(exc)))
        except Exception as exc:
            logger.exception("custom_mcp_import_failure", name=raw_name)
            result.errors.append(ImportError_(str(raw_name), f"unexpected_error: {exc}"))
    return result


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _payload_from_claude_desktop(name: str, spec: dict[str, Any]) -> CustomServerPayload:
    server_key = normalize_server_key(name)
    transport_raw = str(spec.get("transport") or "").lower().strip() or None
    has_url = bool(spec.get("url"))
    has_command = bool(spec.get("command"))

    if transport_raw in {"http", "http_sse", "sse", "streamable_http", "streamable-http"}:
        transport = "http_sse"
    elif transport_raw == "stdio":
        transport = "stdio"
    elif has_url and not has_command:
        transport = "http_sse"
    else:
        transport = "stdio"

    command_list: list[str] = []
    args_list: list[str] = []
    if transport == "stdio":
        cmd = spec.get("command")
        if isinstance(cmd, str) and cmd.strip():
            command_list = [cmd.strip()]
        elif isinstance(cmd, list):
            command_list = [str(item) for item in cmd if str(item).strip()]
        args = spec.get("args")
        if isinstance(args, list):
            args_list = [str(item) for item in args]
        # Merge args into command for the canonical argv form.
        full_command = command_list + args_list
        command_list = full_command
        args_list = []

    url = None
    if transport == "http_sse":
        url = str(spec.get("url") or "").strip() or None

    env_dict = spec.get("env") or {}
    env_schema: list[dict[str, Any]] = []
    if isinstance(env_dict, dict):
        for env_name in env_dict:
            env_schema.append(
                {
                    "key": str(env_name),
                    "label": str(env_name),
                    "required": True,
                    "input_type": "password",
                }
            )

    headers_schema: list[dict[str, Any]] = []
    headers_dict = spec.get("headers")
    if isinstance(headers_dict, dict):
        for header_name in headers_dict:
            headers_schema.append({"key": str(header_name)})

    auth_strategy = "no_auth"
    if env_schema or transport == "stdio":
        auth_strategy = "api_key" if env_schema else "no_auth"

    return CustomServerPayload(
        server_key=server_key,
        display_name=str(spec.get("display_name") or _humanize_name(name)),
        description=str(spec.get("description") or ""),
        transport_type=transport,
        command=command_list,
        args=args_list,
        url=url,
        headers_schema=headers_schema,
        env_schema=env_schema,
        auth_strategy=auth_strategy,
        source="claude_desktop_json",
        metadata={"imported_from": "claude_desktop_json"},
    )


def _humanize_name(name: str) -> str:
    cleaned = re.sub(r"[-_]+", " ", str(name or "")).strip()
    return cleaned.title() if cleaned else "Custom MCP"


def _validate_http_url(url: str, *, allow_localhost: bool) -> None:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValidationError(f"URL scheme must be http(s): {url!r}")
    if parsed.scheme == "http":
        host = (parsed.hostname or "").lower()
        if not (allow_localhost and host in {"localhost", "127.0.0.1", "::1"}):
            raise ValidationError("plain http only allowed for localhost")
    if not parsed.hostname:
        raise ValidationError(f"URL must include a host: {url!r}")


def _upsert_system_row(
    payload: CustomServerPayload,
    *,
    owner_user_id: str | None,
    now: str,
) -> dict[str, Any]:
    metadata = dict(payload.metadata)
    metadata.setdefault("connection_profile", {})
    metadata.setdefault("runtime_constraints", payload.runtime_constraints)
    metadata.setdefault("custom_payload", _payload_summary(payload))

    full_command = payload.command + payload.args
    command_json = json_dump(full_command)
    env_schema_json = json_dump(payload.env_schema)
    headers_schema_json = json_dump(payload.headers_schema)
    metadata_json = json_dump(metadata)
    isolation_constraints_json = json_dump(payload.isolation_constraints)
    validation_signature = metadata.get("validation_signature")

    execute(
        """
        INSERT INTO cp_mcp_server_catalog (
            server_key, display_name, description, transport_type,
            command_json, url, env_schema_json, documentation_url,
            logo_key, category, enabled, metadata_json, created_at, updated_at,
            is_custom, isolation_profile, isolation_constraints_json,
            runtime_token_placement, owner_user_id, source, validation_signature,
            headers_schema_json, auth_strategy
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, 1, ?, ?, 'env_var', ?, ?, ?, ?, ?)
        ON CONFLICT (server_key) DO UPDATE SET
            display_name = EXCLUDED.display_name,
            description = EXCLUDED.description,
            transport_type = EXCLUDED.transport_type,
            command_json = EXCLUDED.command_json,
            url = EXCLUDED.url,
            env_schema_json = EXCLUDED.env_schema_json,
            documentation_url = EXCLUDED.documentation_url,
            logo_key = EXCLUDED.logo_key,
            category = EXCLUDED.category,
            metadata_json = EXCLUDED.metadata_json,
            updated_at = EXCLUDED.updated_at,
            is_custom = 1,
            isolation_profile = EXCLUDED.isolation_profile,
            isolation_constraints_json = EXCLUDED.isolation_constraints_json,
            owner_user_id = EXCLUDED.owner_user_id,
            source = EXCLUDED.source,
            validation_signature = EXCLUDED.validation_signature,
            headers_schema_json = EXCLUDED.headers_schema_json,
            auth_strategy = EXCLUDED.auth_strategy
        """,
        (
            payload.server_key,
            payload.display_name,
            payload.description,
            payload.transport_type,
            command_json,
            payload.url,
            env_schema_json,
            None,
            None,
            "general",
            metadata_json,
            now,
            now,
            payload.isolation_profile,
            isolation_constraints_json,
            owner_user_id,
            payload.source,
            validation_signature,
            headers_schema_json,
            payload.auth_strategy,
        ),
    )
    row = fetch_one("SELECT * FROM cp_mcp_server_catalog WHERE server_key = ?", (payload.server_key,))
    if row is None:
        raise RuntimeError(f"row not visible after upsert: {payload.server_key}")
    return _serialize_system_row(row)


def _upsert_user_row(
    payload: CustomServerPayload,
    *,
    agent_id: str,
    owner_user_id: str | None,
    now: str,
) -> dict[str, Any]:
    metadata_json = json_dump(payload.metadata)
    full_command = payload.command + payload.args
    command_json = json_dump(full_command)
    args_json = json_dump([])
    env_schema_json = json_dump(payload.env_schema)
    headers_schema_json = json_dump(payload.headers_schema)
    runtime_constraints_json = json_dump(payload.runtime_constraints)
    oauth_config_json = json_dump(payload.oauth_config)
    isolation_constraints_json = json_dump(payload.isolation_constraints)
    validation_signature = payload.metadata.get("validation_signature")

    execute(
        """
        INSERT INTO cp_mcp_user_servers (
            server_key, agent_id, owner_user_id, display_name, description,
            transport_type, command_json, args_json, url,
            headers_schema_json, env_schema_json, auth_strategy, oauth_config_json,
            isolation_profile, isolation_constraints_json, runtime_constraints_json,
            source, metadata_json, validation_signature, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (server_key, agent_id) DO UPDATE SET
            owner_user_id = EXCLUDED.owner_user_id,
            display_name = EXCLUDED.display_name,
            description = EXCLUDED.description,
            transport_type = EXCLUDED.transport_type,
            command_json = EXCLUDED.command_json,
            args_json = EXCLUDED.args_json,
            url = EXCLUDED.url,
            headers_schema_json = EXCLUDED.headers_schema_json,
            env_schema_json = EXCLUDED.env_schema_json,
            auth_strategy = EXCLUDED.auth_strategy,
            oauth_config_json = EXCLUDED.oauth_config_json,
            isolation_profile = EXCLUDED.isolation_profile,
            isolation_constraints_json = EXCLUDED.isolation_constraints_json,
            runtime_constraints_json = EXCLUDED.runtime_constraints_json,
            source = EXCLUDED.source,
            metadata_json = EXCLUDED.metadata_json,
            validation_signature = EXCLUDED.validation_signature,
            updated_at = EXCLUDED.updated_at
        """,
        (
            payload.server_key,
            agent_id,
            owner_user_id,
            payload.display_name,
            payload.description,
            payload.transport_type,
            command_json,
            args_json,
            payload.url,
            headers_schema_json,
            env_schema_json,
            payload.auth_strategy,
            oauth_config_json,
            payload.isolation_profile,
            isolation_constraints_json,
            runtime_constraints_json,
            payload.source,
            metadata_json,
            validation_signature,
            now,
            now,
        ),
    )
    row = fetch_one(
        "SELECT * FROM cp_mcp_user_servers WHERE agent_id = ? AND server_key = ?",
        (agent_id, payload.server_key),
    )
    if row is None:
        raise RuntimeError(f"row not visible after upsert: {payload.server_key}")
    return _serialize_user_row(row)


def _serialize_system_row(row: dict[str, Any]) -> dict[str, Any]:
    metadata = json_load(str(row.get("metadata_json") or "{}"), {})
    return {
        "server_key": str(row.get("server_key") or ""),
        "display_name": str(row.get("display_name") or ""),
        "description": str(row.get("description") or ""),
        "transport_type": str(row.get("transport_type") or "stdio"),
        "command": json_load(str(row.get("command_json") or "[]"), []),
        "url": row.get("url"),
        "env_schema": json_load(str(row.get("env_schema_json") or "[]"), []),
        "headers_schema": json_load(str(row.get("headers_schema_json") or "[]"), []),
        "auth_strategy": str(row.get("auth_strategy") or "no_auth"),
        "isolation_profile": str(row.get("isolation_profile") or "auto"),
        "isolation_constraints": json_load(str(row.get("isolation_constraints_json") or "{}"), {}),
        "runtime_constraints": metadata.get("runtime_constraints") or [],
        "is_custom": True,
        "scope": "system",
        "source": str(row.get("source") or "manual"),
        "owner_user_id": row.get("owner_user_id"),
        "metadata": metadata,
        "validation_signature": row.get("validation_signature"),
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }


def _serialize_user_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "server_key": str(row.get("server_key") or ""),
        "agent_id": str(row.get("agent_id") or ""),
        "display_name": str(row.get("display_name") or ""),
        "description": str(row.get("description") or ""),
        "transport_type": str(row.get("transport_type") or "stdio"),
        "command": json_load(str(row.get("command_json") or "[]"), []),
        "args": json_load(str(row.get("args_json") or "[]"), []),
        "url": row.get("url"),
        "env_schema": json_load(str(row.get("env_schema_json") or "[]"), []),
        "headers_schema": json_load(str(row.get("headers_schema_json") or "[]"), []),
        "auth_strategy": str(row.get("auth_strategy") or "no_auth"),
        "oauth_config": json_load(str(row.get("oauth_config_json") or "{}"), {}),
        "isolation_profile": str(row.get("isolation_profile") or "auto"),
        "isolation_constraints": json_load(str(row.get("isolation_constraints_json") or "{}"), {}),
        "runtime_constraints": json_load(str(row.get("runtime_constraints_json") or "[]"), []),
        "is_custom": True,
        "scope": "agent",
        "source": str(row.get("source") or "manual"),
        "owner_user_id": row.get("owner_user_id"),
        "metadata": json_load(str(row.get("metadata_json") or "{}"), {}),
        "validation_signature": row.get("validation_signature"),
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }


def _payload_summary(payload: CustomServerPayload) -> dict[str, Any]:
    return {
        "transport_type": payload.transport_type,
        "command": payload.command,
        "url": payload.url,
        "env_keys": [str(field_def.get("key") or "") for field_def in payload.env_schema],
    }
