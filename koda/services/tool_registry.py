"""Schema-first registry helpers for agent tool definitions.

The registry is intentionally side-effect free: callers pass the current
handler IDs and read/write sets so this module can be introduced without
rewiring the dispatcher or prompt builder in the same patch.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any
from xml.sax.saxutils import escape, quoteattr

from koda.agent_contract import CoreToolDefinition

TOOL_SCHEMA_VERSION = "tool-definition.v1"

JsonObject = dict[str, Any]
HandlerCatalog = Mapping[str, object] | Collection[str]

_OBJECT_SCHEMA: JsonObject = {"type": "object", "properties": {}, "additionalProperties": True}
_APPROVAL_ALLOW = "allow"
_APPROVAL_PREVIEW = "allow_with_preview"
_APPROVAL_REQUIRED = "require_approval"
_HIGH_RISK_EFFECT_TAGS = frozenset({"credential_access", "identity_admin", "destructive_change"})
_DEFAULT_CORE_ARGS_SCHEMAS: dict[str, JsonObject] = {
    "web_search": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query."},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    "fetch_url": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch."},
        },
        "required": ["url"],
        "additionalProperties": False,
    },
    "file_read": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path relative to the current workdir or absolute."},
            "offset": {"type": "integer", "description": "Optional zero-based line offset."},
            "limit": {"type": "integer", "description": "Optional maximum number of lines to read."},
        },
        "required": ["path"],
        "additionalProperties": False,
    },
    "file_write": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path relative to the current workdir or absolute."},
            "content": {"type": "string", "description": "Complete file content to write."},
            "create_dirs": {"type": "boolean", "description": "Whether missing parent directories may be created."},
        },
        "required": ["path", "content"],
        "additionalProperties": False,
    },
    "shell_execute": {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute."},
            "timeout": {"type": "integer", "description": "Optional timeout in seconds."},
        },
        "required": ["command"],
        "additionalProperties": False,
    },
    "git_status": {
        "type": "object",
        "properties": {
            "short": {"type": "boolean", "description": "Return concise porcelain status."},
        },
        "additionalProperties": False,
    },
    "task": {
        "type": "object",
        "properties": {
            "goal": {"type": "string", "description": "Short objective for the child run."},
            "prompt": {"type": "string", "description": "Full child-run brief."},
            "tasks": {
                "type": "array",
                "description": "Optional bounded fan-out of child-run briefs.",
                "items": {
                    "type": "object",
                    "properties": {
                        "goal": {"type": "string"},
                        "prompt": {"type": "string"},
                        "target_agent_id": {"type": "string"},
                        "toolset": {"type": "string"},
                        "timeout_seconds": {"type": "integer"},
                        "max_context_tokens": {"type": "integer"},
                        "max_cost_usd": {"type": "number"},
                        "context_policy": {"type": "object", "additionalProperties": True},
                        "return_schema": {"type": "object", "additionalProperties": True},
                    },
                    "additionalProperties": False,
                },
            },
            "target_agent_id": {"type": "string", "description": "Optional target agent prompt/profile."},
            "toolset": {
                "type": "string",
                "description": "Child toolset. Phase 3 allows read_only, analysis, or research.",
            },
            "timeout_seconds": {"type": "integer", "description": "Timeout in seconds, capped by runtime."},
            "max_context_tokens": {"type": "integer", "description": "Maximum governed context tokens."},
            "max_cost_usd": {"type": "number", "description": "Optional cost budget recorded for the child run."},
            "context_policy": {"type": "object", "additionalProperties": True},
            "return_schema": {"type": "object", "additionalProperties": True},
        },
        "additionalProperties": False,
    },
    "squad_reply": {
        "type": "object",
        "properties": {
            "thread_id": {"type": "string", "description": "Optional squad thread id; defaults to current thread."},
            "content": {"type": "string", "description": "Reply content to persist in the thread."},
            "reply_to_message_id": {"type": "string", "description": "Message ref such as msg-42."},
            "target_agent_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional agents expected to respond to this reply.",
            },
            "reply_kind": {
                "type": "string",
                "description": "agent_reply, agent_request, agent_followup, or synthesis.",
            },
            "requires_response_by": {"type": "string", "description": "Optional ISO timestamp deadline."},
            "idempotency_key": {"type": "string"},
            "metadata": {"type": "object", "additionalProperties": True},
        },
        "required": ["content"],
        "additionalProperties": False,
    },
    "squad_request_input": {
        "type": "object",
        "properties": {
            "thread_id": {"type": "string", "description": "Optional squad thread id; defaults to current thread."},
            "target_agent_ids": {"type": "array", "items": {"type": "string"}},
            "question": {"type": "string", "description": "Specific contribution requested from the target agents."},
            "reason": {"type": "string", "description": "Why this input is needed."},
            "urgency": {"type": "string", "description": "Optional urgency label."},
            "requires_response_by": {"type": "string", "description": "Optional ISO timestamp deadline."},
            "parent_message_id": {"type": "string", "description": "Optional parent message ref."},
        },
        "required": ["target_agent_ids", "question"],
        "additionalProperties": False,
    },
    "squad_follow_up": {
        "type": "object",
        "properties": {
            "thread_id": {"type": "string", "description": "Optional squad thread id; defaults to current thread."},
            "obligation_id": {"type": "integer", "description": "Reply obligation id to follow up."},
            "note": {"type": "string", "description": "Optional short follow-up note."},
        },
        "required": ["obligation_id"],
        "additionalProperties": False,
    },
    "squad_synthesize": {
        "type": "object",
        "properties": {
            "thread_id": {"type": "string", "description": "Optional squad thread id; defaults to current thread."},
            "content": {"type": "string", "description": "Final coordinator synthesis."},
            "reply_to_message_id": {"type": "string", "description": "Root user message or request ref."},
            "metadata": {"type": "object", "additionalProperties": True},
        },
        "required": ["content"],
        "additionalProperties": False,
    },
}
_DEFAULT_REGISTRY_CACHE: dict[object, ToolRegistry] = {}


class ToolRegistryError(ValueError):
    """Base error for invalid tool registry input."""


class ToolSchemaError(ToolRegistryError):
    """Raised when a tool args schema is not an object-like JSON Schema."""


class ToolRegistryDriftError(ToolRegistryError):
    """Raised when registry metadata no longer matches handlers or access sets."""


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Canonical Phase 1 tool definition shared by prompts, providers, UI, and policy."""

    id: str
    title: str
    category: str
    description: str
    args_schema: JsonObject = field(default_factory=lambda: copy.deepcopy(_OBJECT_SCHEMA))
    handler_ref: str = ""
    access_level: str = "write"
    effect_tags: tuple[str, ...] = ()
    idempotency: str = "unknown"
    risk_class: str = "write"
    approval_default: str = _APPROVAL_PREVIEW
    timeout_seconds: int | None = None
    feature_flag: str | None = None
    ui_metadata: JsonObject = field(default_factory=dict)
    docs_metadata: JsonObject = field(default_factory=dict)
    schema_version: str = TOOL_SCHEMA_VERSION
    source: str = "core"

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _normalize_required_id(self.id, field_name="id"))
        object.__setattr__(self, "title", str(self.title).strip())
        object.__setattr__(self, "category", str(self.category).strip() or "general")
        object.__setattr__(self, "description", str(self.description).strip())
        object.__setattr__(self, "handler_ref", str(self.handler_ref).strip())
        object.__setattr__(self, "access_level", str(self.access_level).strip().lower() or "write")
        object.__setattr__(self, "effect_tags", _normalize_string_tuple(self.effect_tags))
        object.__setattr__(self, "idempotency", str(self.idempotency).strip().lower() or "unknown")
        object.__setattr__(self, "risk_class", str(self.risk_class).strip().lower() or self.access_level)
        object.__setattr__(self, "approval_default", str(self.approval_default).strip().lower() or _APPROVAL_PREVIEW)
        object.__setattr__(self, "feature_flag", _normalize_optional_string(self.feature_flag))
        object.__setattr__(self, "schema_version", str(self.schema_version).strip() or TOOL_SCHEMA_VERSION)
        object.__setattr__(self, "source", str(self.source).strip() or "core")
        object.__setattr__(self, "args_schema", validate_json_schema_object(self.args_schema))
        object.__setattr__(self, "ui_metadata", dict(self.ui_metadata))
        object.__setattr__(self, "docs_metadata", dict(self.docs_metadata))
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ToolRegistryError(f"{self.id}: timeout_seconds must be positive when set")

    @property
    def read_only(self) -> bool:
        """Whether this tool is classified as a read-only action."""

        return self.access_level == "read"

    def to_xml_prompt_entry(self) -> str:
        """Return a deterministic XML prompt entry for this tool."""

        attrs = {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "access_level": self.access_level,
            "risk_class": self.risk_class,
            "approval_default": self.approval_default,
            "idempotency": self.idempotency,
            "schema_version": self.schema_version,
            "source": self.source,
        }
        if self.feature_flag:
            attrs["feature_flag"] = self.feature_flag
        if self.timeout_seconds is not None:
            attrs["timeout_seconds"] = str(self.timeout_seconds)

        attr_text = " ".join(f"{key}={quoteattr(value)}" for key, value in attrs.items())
        schema_json = json.dumps(self.args_schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        effect_tags = ",".join(self.effect_tags)
        return (
            f"<tool {attr_text}>\n"
            f"  <description>{escape(self.description)}</description>\n"
            f"  <effect_tags>{escape(effect_tags)}</effect_tags>\n"
            f"  <args_schema>{escape(schema_json)}</args_schema>\n"
            "</tool>"
        )

    def to_openai_tool_schema(self) -> JsonObject:
        """Return an OpenAI Chat Completions compatible function tool schema."""

        return {
            "type": "function",
            "function": {
                "name": self.id,
                "description": self.description,
                "parameters": copy.deepcopy(self.args_schema),
            },
        }


@dataclass(frozen=True, slots=True)
class ToolRegistryDrift:
    """Differences between registry entries and runtime catalogs supplied by callers."""

    missing_handlers: tuple[str, ...] = ()
    uncatalogued_handlers: tuple[str, ...] = ()
    missing_access_metadata: tuple[str, ...] = ()
    conflicting_access_metadata: tuple[str, ...] = ()
    uncatalogued_access_metadata: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        """Whether no registry drift was detected."""

        return not (
            self.missing_handlers
            or self.uncatalogued_handlers
            or self.missing_access_metadata
            or self.conflicting_access_metadata
            or self.uncatalogued_access_metadata
        )

    def raise_if_any(self) -> None:
        """Raise a concise error when drift is present."""

        if self.ok:
            return
        parts: list[str] = []
        if self.missing_handlers:
            parts.append(f"missing handlers: {', '.join(self.missing_handlers)}")
        if self.uncatalogued_handlers:
            parts.append(f"uncatalogued handlers: {', '.join(self.uncatalogued_handlers)}")
        if self.missing_access_metadata:
            parts.append(f"missing access metadata: {', '.join(self.missing_access_metadata)}")
        if self.conflicting_access_metadata:
            parts.append(f"conflicting access metadata: {', '.join(self.conflicting_access_metadata)}")
        if self.uncatalogued_access_metadata:
            parts.append(f"uncatalogued access metadata: {', '.join(self.uncatalogued_access_metadata)}")
        raise ToolRegistryDriftError("; ".join(parts))


class ToolRegistry:
    """Immutable-ish in-memory index of schema-first tool definitions."""

    def __init__(self, definitions: Iterable[ToolDefinition]) -> None:
        by_id: dict[str, ToolDefinition] = {}
        for definition in definitions:
            if definition.id in by_id:
                raise ToolRegistryError(f"Duplicate tool definition id: {definition.id}")
            by_id[definition.id] = definition
        self._definitions = dict(sorted(by_id.items()))

    @classmethod
    def from_core_tools(
        cls,
        core_tools: Iterable[CoreToolDefinition],
        *,
        read_tool_ids: Collection[str],
        write_tool_ids: Collection[str],
        handler_ids: HandlerCatalog,
        args_schemas: Mapping[str, Mapping[str, Any]] | None = None,
        handler_refs: Mapping[str, str] | None = None,
        access_levels: Mapping[str, str] | None = None,
        effect_tags: Mapping[str, Iterable[str]] | None = None,
        idempotency: Mapping[str, str] | None = None,
        risk_classes: Mapping[str, str] | None = None,
        approval_defaults: Mapping[str, str] | None = None,
        timeout_seconds: Mapping[str, int | None] | None = None,
        ui_metadata: Mapping[str, Mapping[str, Any]] | None = None,
        docs_metadata: Mapping[str, Mapping[str, Any]] | None = None,
        default_timeout_seconds: int | None = None,
        schema_version: str = TOOL_SCHEMA_VERSION,
        source: str = "core",
    ) -> ToolRegistry:
        """Build a registry from existing core catalog rows and caller-owned runtime sets."""

        return cls(
            build_core_tool_definitions(
                core_tools,
                read_tool_ids=read_tool_ids,
                write_tool_ids=write_tool_ids,
                handler_ids=handler_ids,
                args_schemas=args_schemas,
                handler_refs=handler_refs,
                access_levels=access_levels,
                effect_tags=effect_tags,
                idempotency=idempotency,
                risk_classes=risk_classes,
                approval_defaults=approval_defaults,
                timeout_seconds=timeout_seconds,
                ui_metadata=ui_metadata,
                docs_metadata=docs_metadata,
                default_timeout_seconds=default_timeout_seconds,
                schema_version=schema_version,
                source=source,
            )
        )

    @property
    def definitions(self) -> tuple[ToolDefinition, ...]:
        """Registry definitions in deterministic ID order."""

        return tuple(self._definitions.values())

    @property
    def ids(self) -> tuple[str, ...]:
        """Known tool IDs in deterministic order."""

        return tuple(self._definitions)

    def get(self, tool_id: str) -> ToolDefinition | None:
        """Return one tool definition when present."""

        return self._definitions.get(tool_id)

    def require(self, tool_id: str) -> ToolDefinition:
        """Return one definition or raise a registry error."""

        definition = self.get(tool_id)
        if definition is None:
            raise ToolRegistryError(f"Unknown tool definition: {tool_id}")
        return definition

    def export_xml_prompt_entries(self) -> str:
        """Export all definitions as deterministic XML prompt entries."""

        return export_xml_prompt_entries(self.definitions)

    def export_openai_tool_schemas(self) -> list[JsonObject]:
        """Export all definitions as OpenAI-compatible native tool schemas."""

        return export_openai_tool_schemas(self.definitions)

    def detect_drift(
        self,
        *,
        handler_ids: HandlerCatalog,
        read_tool_ids: Collection[str],
        write_tool_ids: Collection[str],
    ) -> ToolRegistryDrift:
        """Detect drift against caller-owned dispatcher metadata."""

        return detect_tool_registry_drift(
            self.definitions,
            handler_ids=handler_ids,
            read_tool_ids=read_tool_ids,
            write_tool_ids=write_tool_ids,
        )


def build_core_tool_definitions(
    core_tools: Iterable[CoreToolDefinition],
    *,
    read_tool_ids: Collection[str],
    write_tool_ids: Collection[str],
    handler_ids: HandlerCatalog,
    args_schemas: Mapping[str, Mapping[str, Any]] | None = None,
    handler_refs: Mapping[str, str] | None = None,
    access_levels: Mapping[str, str] | None = None,
    effect_tags: Mapping[str, Iterable[str]] | None = None,
    idempotency: Mapping[str, str] | None = None,
    risk_classes: Mapping[str, str] | None = None,
    approval_defaults: Mapping[str, str] | None = None,
    timeout_seconds: Mapping[str, int | None] | None = None,
    ui_metadata: Mapping[str, Mapping[str, Any]] | None = None,
    docs_metadata: Mapping[str, Mapping[str, Any]] | None = None,
    default_timeout_seconds: int | None = None,
    schema_version: str = TOOL_SCHEMA_VERSION,
    source: str = "core",
) -> tuple[ToolDefinition, ...]:
    """Create schema-first definitions from ``CoreToolDefinition`` objects."""

    read_ids = _normalize_id_set(read_tool_ids)
    write_ids = _normalize_id_set(write_tool_ids)
    handler_id_set = _normalize_handler_ids(handler_ids)
    definitions: list[ToolDefinition] = []

    for core_tool in core_tools:
        tool_id = _normalize_required_id(core_tool.id, field_name="CoreToolDefinition.id")
        access_level = _access_level_for_tool(
            core_tool,
            read_tool_ids=read_ids,
            write_tool_ids=write_ids,
            access_levels=access_levels,
        )
        normalized_effect_tags = _normalize_string_tuple(
            (effect_tags or {}).get(tool_id, _default_effect_tags(tool_id, access_level))
        )
        risk_class = str((risk_classes or {}).get(tool_id, access_level)).strip().lower() or access_level
        approval_default = str(
            (approval_defaults or {}).get(tool_id, _default_approval(access_level, normalized_effect_tags))
        )
        schema = copy.deepcopy(dict((args_schemas or {}).get(tool_id, _OBJECT_SCHEMA)))
        tool_ui_metadata = {
            "read_only": access_level == "read",
            "write_capable": access_level != "read",
            **dict((ui_metadata or {}).get(tool_id, {})),
        }
        tool_docs_metadata = {
            "category": core_tool.category,
            **dict((docs_metadata or {}).get(tool_id, {})),
        }
        definitions.append(
            ToolDefinition(
                id=tool_id,
                title=core_tool.title,
                category=core_tool.category,
                description=core_tool.description,
                args_schema=schema,
                handler_ref=_handler_ref_for_tool(tool_id, handler_ids, handler_id_set, handler_refs),
                access_level=access_level,
                effect_tags=normalized_effect_tags,
                idempotency=str((idempotency or {}).get(tool_id, _default_idempotency(access_level))),
                risk_class=risk_class,
                approval_default=approval_default,
                timeout_seconds=(timeout_seconds or {}).get(tool_id, default_timeout_seconds),
                feature_flag=core_tool.feature_flag,
                ui_metadata=tool_ui_metadata,
                docs_metadata=tool_docs_metadata,
                schema_version=schema_version,
                source=source,
            )
        )

    return tuple(definitions)


def validate_json_schema_object(schema: Mapping[str, Any]) -> JsonObject:
    """Validate and return a copy of a top-level object JSON Schema.

    This intentionally checks the basics needed for provider-native tool
    calling without trying to implement a full JSON Schema validator.
    """

    if not isinstance(schema, Mapping):
        raise ToolSchemaError("Tool args_schema must be a JSON object")

    copied = copy.deepcopy(dict(schema))
    schema_type = copied.get("type")
    if schema_type != "object":
        raise ToolSchemaError("Tool args_schema must declare type='object'")

    properties = copied.get("properties", {})
    if not isinstance(properties, Mapping):
        raise ToolSchemaError("Tool args_schema.properties must be an object when present")
    for property_name, property_schema in properties.items():
        if not isinstance(property_name, str) or not property_name:
            raise ToolSchemaError("Tool args_schema.properties keys must be non-empty strings")
        if not isinstance(property_schema, Mapping):
            raise ToolSchemaError(f"Tool args_schema.properties.{property_name} must be an object")

    required = copied.get("required", [])
    if not isinstance(required, list) or any(not isinstance(item, str) or not item for item in required):
        raise ToolSchemaError("Tool args_schema.required must be a list of non-empty strings")
    unknown_required = sorted(set(required) - {str(key) for key in properties})
    if unknown_required:
        raise ToolSchemaError(f"Tool args_schema.required references unknown properties: {', '.join(unknown_required)}")

    additional_properties = copied.get("additionalProperties", True)
    if not isinstance(additional_properties, (bool, dict)):
        raise ToolSchemaError("Tool args_schema.additionalProperties must be a boolean or object when present")

    return copied


def export_xml_prompt_entries(definitions: Iterable[ToolDefinition]) -> str:
    """Export definitions as deterministic XML prompt entries."""

    return "\n".join(definition.to_xml_prompt_entry() for definition in sorted(definitions, key=lambda item: item.id))


def export_openai_tool_schemas(definitions: Iterable[ToolDefinition]) -> list[JsonObject]:
    """Export definitions as OpenAI-compatible function tool schemas."""

    return [definition.to_openai_tool_schema() for definition in sorted(definitions, key=lambda item: item.id)]


def get_default_tool_registry(
    *,
    feature_flags: Mapping[str, bool] | None = None,
    allowed_tool_ids: Collection[str] | None = None,
    skill_policy: Mapping[str, Any] | None = None,
) -> ToolRegistry:
    """Build the runtime registry from the existing core catalog and dispatcher maps.

    The dispatcher remains the compatibility source for handlers and read/write
    sets during Phase 1. This function centralizes the bridge so prompt,
    provider-native schemas, approvals, and drift tests consume one contract.
    """

    normalized_allowed = tuple(sorted(_normalize_id_set(allowed_tool_ids or ())))
    normalized_flags = tuple(sorted((str(key), bool(value)) for key, value in (feature_flags or {}).items()))
    resolved_skill_policy = _resolve_skill_policy(skill_policy)
    enabled_skill_packages = (
        tuple(sorted(_normalize_id_set(resolved_skill_policy.get("enabled_skill_packages", ()))))
        if resolved_skill_policy.get("enabled", True)
        else ()
    )
    installed_signature: tuple[tuple[str, str], ...] = ()
    try:
        from koda.config import AGENT_ID  # noqa: PLC0415
        from koda.skills._package import list_skill_package_locks  # noqa: PLC0415

        installed_signature = tuple(
            sorted(
                (
                    str(lock.get("package_id") or ""),
                    str(lock.get("package_hash") or ""),
                )
                for lock in list_skill_package_locks(AGENT_ID or "default")
            )
        )
    except Exception:
        installed_signature = ()
    cache_key = (normalized_allowed, normalized_flags, enabled_skill_packages, installed_signature)
    cached = _DEFAULT_REGISTRY_CACHE.get(cache_key)
    if cached is not None:
        return cached

    from koda.agent_contract import CORE_TOOL_CATALOG, resolve_feature_filtered_tools  # noqa: PLC0415
    from koda.services import tool_dispatcher  # noqa: PLC0415

    if feature_flags is None:
        selected_ids = set(CORE_TOOL_CATALOG)
    else:
        selected_ids = {
            str(item["id"])
            for item in resolve_feature_filtered_tools(dict(feature_flags))
            if bool(item.get("available"))
        }
    if allowed_tool_ids is not None:
        selected_ids &= set(normalized_allowed)

    registry = ToolRegistry.from_core_tools(
        [CORE_TOOL_CATALOG[tool_id] for tool_id in sorted(selected_ids) if tool_id in CORE_TOOL_CATALOG],
        read_tool_ids=tool_dispatcher._READ_TOOLS,
        write_tool_ids=tool_dispatcher._WRITE_TOOLS,
        handler_ids=tool_dispatcher._TOOL_HANDLERS,
        args_schemas=_DEFAULT_CORE_ARGS_SCHEMAS,
        effect_tags={"task": ("delegation", "fanout", "tool_execution")},
        idempotency={"task": "idempotent"},
        risk_classes={"task": "code_execution"},
        approval_defaults={"task": _APPROVAL_REQUIRED},
        ui_metadata={"task": {"title": "Delegate Task", "ephemeral": True}},
        docs_metadata={"task": {"contract": "child_run.v1"}},
        default_timeout_seconds=30,
    )
    include_package_tools = feature_flags is None or bool(dict(feature_flags).get("plugins", True))
    if include_package_tools and allowed_tool_ids is not None and enabled_skill_packages:
        try:
            from koda.config import AGENT_ID  # noqa: PLC0415
            from koda.skills._package import get_installed_package_tool_definitions  # noqa: PLC0415

            package_definitions = get_installed_package_tool_definitions(AGENT_ID or "default")
        except Exception:
            package_definitions = []
        allowed = set(normalized_allowed)
        allowed_packages = set(enabled_skill_packages)
        package_definitions = [
            definition
            for definition in package_definitions
            if definition.id in allowed
            and str(definition.ui_metadata.get("source_package_id") or "").strip() in allowed_packages
        ]
        if package_definitions:
            registry = ToolRegistry([*registry.definitions, *package_definitions])
    _DEFAULT_REGISTRY_CACHE[cache_key] = registry
    return registry


def get_tool_definition(tool_id: str) -> ToolDefinition | None:
    """Return one default registry definition for runtime approval payloads."""

    return get_default_tool_registry().get(tool_id)


def build_openai_tool_schemas_for_runtime(
    *,
    feature_flags: Mapping[str, bool] | None = None,
    allowed_tool_ids: Collection[str] | None = None,
    skill_policy: Mapping[str, Any] | None = None,
) -> list[JsonObject]:
    """Return OpenAI-compatible native tool schemas for the runtime registry."""

    return get_default_tool_registry(
        feature_flags=feature_flags,
        allowed_tool_ids=allowed_tool_ids,
        skill_policy=skill_policy,
    ).export_openai_tool_schemas()


def detect_tool_registry_drift(
    definitions: Iterable[ToolDefinition],
    *,
    handler_ids: HandlerCatalog,
    read_tool_ids: Collection[str],
    write_tool_ids: Collection[str],
) -> ToolRegistryDrift:
    """Compare registry entries to caller-owned handler and read/write catalogs."""

    definitions_by_id = {definition.id: definition for definition in definitions}
    registry_ids = frozenset(definitions_by_id)
    handler_id_set = _normalize_handler_ids(handler_ids)
    read_ids = _normalize_id_set(read_tool_ids)
    write_ids = _normalize_id_set(write_tool_ids)
    access_ids = read_ids | write_ids

    missing_handlers = tuple(sorted(registry_ids - handler_id_set))
    uncatalogued_handlers = tuple(sorted(handler_id_set - registry_ids))
    missing_access_metadata = tuple(sorted(registry_ids - access_ids))
    conflicting_access_metadata = tuple(sorted(read_ids & write_ids))
    uncatalogued_access_metadata = tuple(sorted(access_ids - registry_ids))

    for tool_id, definition in definitions_by_id.items():
        if definition.access_level == "read" and tool_id in write_ids:
            conflicting_access_metadata = tuple(sorted({*conflicting_access_metadata, tool_id}))
        if definition.access_level != "read" and tool_id in read_ids:
            conflicting_access_metadata = tuple(sorted({*conflicting_access_metadata, tool_id}))

    return ToolRegistryDrift(
        missing_handlers=missing_handlers,
        uncatalogued_handlers=uncatalogued_handlers,
        missing_access_metadata=missing_access_metadata,
        conflicting_access_metadata=conflicting_access_metadata,
        uncatalogued_access_metadata=uncatalogued_access_metadata,
    )


def validate_tool_definition(definition: ToolDefinition) -> ToolDefinition:
    """Validate a definition and return it for pipeline-style callers."""

    validate_json_schema_object(definition.args_schema)
    if not definition.id:
        raise ToolRegistryError("Tool definition id is required")
    return definition


def _normalize_required_id(value: str, *, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ToolRegistryError(f"{field_name} is required")
    return normalized


def _normalize_optional_string(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_string_tuple(values: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value).strip().lower()
        if item and item not in seen:
            normalized.append(item)
            seen.add(item)
    return tuple(normalized)


def _normalize_id_set(values: Collection[str]) -> frozenset[str]:
    return frozenset(str(value).strip() for value in values if str(value).strip())


def _resolve_skill_policy(skill_policy: Mapping[str, Any] | None) -> dict[str, Any]:
    if skill_policy is not None:
        return dict(skill_policy)
    try:
        from koda.skills._runtime import get_runtime_agent_spec, get_runtime_skill_policy  # noqa: PLC0415

        return get_runtime_skill_policy(get_runtime_agent_spec())
    except Exception:
        return {}


def _normalize_handler_ids(handler_ids: HandlerCatalog) -> frozenset[str]:
    if isinstance(handler_ids, Mapping):
        return frozenset(str(value).strip() for value in handler_ids if str(value).strip())
    return _normalize_id_set(handler_ids)


def _access_level_for_tool(
    core_tool: CoreToolDefinition,
    *,
    read_tool_ids: frozenset[str],
    write_tool_ids: frozenset[str],
    access_levels: Mapping[str, str] | None,
) -> str:
    override = (access_levels or {}).get(core_tool.id)
    if override:
        return str(override).strip().lower()
    if core_tool.id in write_tool_ids:
        return "write"
    if core_tool.id in read_tool_ids:
        return "read"
    if core_tool.read_only is True:
        return "read"
    return "write"


def _default_effect_tags(tool_id: str, access_level: str) -> tuple[str, ...]:
    if access_level == "read":
        return ()
    tags: list[str] = []
    if access_level in {"destructive", "admin"} or "delete" in tool_id or "uninstall" in tool_id:
        tags.append("destructive_change")
    if tool_id.startswith("browser_") and access_level != "read":
        tags.append("browser_state_mutation")
    if tool_id.startswith(("http_", "webhook_", "agent_")) and access_level != "read":
        tags.append("external_communication")
    if tool_id.startswith(("file_", "git_")) and access_level != "read":
        tags.append("workspace_mutation")
    if tool_id.startswith("shell_"):
        tags.append("command_execution")
    return tuple(tags)


def _default_idempotency(access_level: str) -> str:
    return "read_only" if access_level == "read" else "non_idempotent"


def _default_approval(access_level: str, effect_tags: Iterable[str]) -> str:
    normalized_tags = set(_normalize_string_tuple(effect_tags))
    if access_level == "read":
        return _APPROVAL_ALLOW
    if access_level in {"admin", "destructive"} or normalized_tags & _HIGH_RISK_EFFECT_TAGS:
        return _APPROVAL_REQUIRED
    return _APPROVAL_PREVIEW


def _handler_ref_for_tool(
    tool_id: str,
    handler_ids: HandlerCatalog,
    handler_id_set: frozenset[str],
    handler_refs: Mapping[str, str] | None,
) -> str:
    if handler_refs and tool_id in handler_refs:
        return str(handler_refs[tool_id]).strip()
    if tool_id not in handler_id_set:
        return ""
    if isinstance(handler_ids, Mapping):
        handler = handler_ids.get(tool_id)
        if isinstance(handler, str):
            return handler
        if handler is not None:
            module = str(getattr(handler, "__module__", "") or "").strip()
            name = str(getattr(handler, "__qualname__", getattr(handler, "__name__", tool_id)) or tool_id).strip()
            return f"{module}.{name}" if module else name
    return tool_id


validate_json_schema_object_basics = validate_json_schema_object
build_tool_definitions_from_core_tools = build_core_tool_definitions
detect_registry_drift = detect_tool_registry_drift
export_openai_native_tool_schemas = export_openai_tool_schemas
export_native_tool_schemas = export_openai_tool_schemas
build_native_tool_schemas_for_runtime = build_openai_tool_schemas_for_runtime
