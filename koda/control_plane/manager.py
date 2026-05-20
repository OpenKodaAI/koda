"""High-level control-plane management and materialization."""

from __future__ import annotations

import asyncio
import contextlib
import copy
import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from koda.agent_contract import (
    CORE_INTEGRATION_CATALOG,
    CORE_PROVIDER_CATALOG,
    PROMOTION_MODES,
    normalize_string_list,
    resolve_allowed_tool_ids,
    resolve_core_integration_catalog,
    resolve_core_provider_catalog,
    resolve_feature_filtered_tools,
    serialize_connection_profile,
)
from koda.config import AGENT_ID, SHARED_PLATFORM_PROMPT, STATE_BACKEND
from koda.internal_rpc.retrieval_engine import build_retrieval_engine_client
from koda.knowledge.config import (
    KNOWLEDGE_V2_EMBEDDING_DIMENSION,
    KNOWLEDGE_V2_POSTGRES_DSN,
    KNOWLEDGE_V2_POSTGRES_SCHEMA,
)
from koda.knowledge.v2.common import V2StoreSupport, get_shared_postgres_backend
from koda.logging_config import get_logger
from koda.provider_models import (
    MODEL_FUNCTION_IDS,
    build_function_model_catalog,
    resolve_known_general_model_ids,
    resolve_model_function_catalog,
    resolve_provider_function_model_catalog,
)
from koda.services.elevenlabs_catalog import (
    ELEVENLABS_DEFAULT_TTS_MODEL,
    canonicalize_elevenlabs_language,
    elevenlabs_language_label,
    elevenlabs_languages_for_model,
    elevenlabs_voice_language_matches,
)
from koda.services.embedding_catalog import (
    CATALOG as _EMBEDDING_CATALOG,
)
from koda.services.embedding_catalog import (
    DEFAULT_MODEL_ID as _DEFAULT_EMBEDDING_MODEL_ID,
)
from koda.services.embedding_catalog import (
    catalog_payload as _embedding_catalog_payload,
)
from koda.services.embedding_catalog import (
    delete_model as _delete_embedding_model,
)
from koda.services.embedding_catalog import (
    is_model_installed as _embedding_model_installed,
)
from koda.services.embedding_catalog import (
    model_disk_bytes as _embedding_model_disk_bytes,
)
from koda.services.kokoro_manager import (
    KOKORO_DEFAULT_LANGUAGE_ID,
    KOKORO_DEFAULT_VOICE_ID,
    delete_kokoro_model,
    delete_kokoro_voice,
    ensure_kokoro_model,
    ensure_kokoro_voice_downloaded,
    kokoro_catalog_payload,
    kokoro_managed_voices_storage_path,
    kokoro_model_path,
    kokoro_model_status,
    kokoro_voice_file_path,
    kokoro_voice_metadata,
)
from koda.services.mcp_connection_broker import decrypt_env_values, resolve_mcp_runtime_connection
from koda.services.prompt_budget import PromptSegment, preview_compiled_prompt, preview_modeled_runtime_prompt
from koda.services.provider_auth import (
    MANAGED_PROVIDER_IDS,
    PROVIDER_API_KEY_ENV_KEYS,
    PROVIDER_AUTH_MODE_ENV_KEYS,
    PROVIDER_AUTH_TOKEN_ENV_KEYS,
    PROVIDER_BASE_URL_ENV_KEYS,
    PROVIDER_PROJECT_ENV_KEYS,
    PROVIDER_TITLES,
    PROVIDER_VERIFIED_ENV_KEYS,
    ProviderLoginSessionState,
    ollama_api_url,
    parse_login_session_state,
    provider_command_present,
    provider_default_base_url,
    run_provider_logout,
    start_login_process,
    verify_provider_api_key,
    verify_provider_local_connection,
    verify_provider_subscription_login,
)
from koda.services.runtime.redaction import redact_value
from koda.services.supertonic_manager import (
    SUPERTONIC_DEFAULT_LANGUAGE_ID,
    SUPERTONIC_DEFAULT_MODEL_ID,
    SUPERTONIC_DEFAULT_VOICE_ID,
    delete_supertonic_model,
    delete_supertonic_voice,
    ensure_supertonic_model,
    ensure_supertonic_voice_downloaded,
    import_supertonic_voice_json,
    supertonic_model_catalog_payload,
    supertonic_model_status,
    supertonic_voice_catalog_payload,
    supertonic_voice_metadata,
)
from koda.services.tool_prompt import build_agent_tools_prompt
from koda.services.whisper_manager import (
    KNOWN_WHISPER_VARIANTS,
    WHISPER_DEFAULT_VARIANT,
    delete_whisper_model,
    ensure_whisper_model_downloaded,
    whisper_catalog_payload,
    whisper_model_path,
)

from .agent_spec import (
    _normalize_markdown_block,
    build_agent_spec_from_snapshot,
    compose_agent_prompt,
    merge_agent_documents,
    merge_hierarchical_documents,
    normalize_agent_spec,
    normalize_autonomy_policy,
    normalize_knowledge_policy,
    normalize_legacy_effort_selection,
    normalize_memory_policy,
    normalize_model_effort_selection,
    normalize_resource_access_policy,
    parse_json_env_value,
    render_markdown_documents_from_agent_spec,
    resolve_agent_documents,
    resolve_scope_documents,
    validate_agent_spec,
)
from .crypto import decrypt_secret, encrypt_secret, mask_secret
from .dashboard_memory import (
    apply_memory_curation_action as dashboard_apply_memory_curation_action,
)
from .dashboard_memory import (
    get_memory_curation_cluster_payload as dashboard_get_memory_curation_cluster_payload,
)
from .dashboard_memory import (
    get_memory_curation_detail_payload as dashboard_get_memory_curation_detail_payload,
)
from .dashboard_memory import (
    get_memory_map_payload as dashboard_get_memory_map_payload,
)
from .dashboard_memory import (
    list_memory_curation_payload as dashboard_list_memory_curation_payload,
)
from .database import (
    execute,
    fetch_all,
    fetch_one,
    init_control_plane_db,
    json_dump,
    json_load,
    now_iso,
    run_coro_sync,
    with_connection,
)
from .execution_policy import (
    build_mcp_action_catalog,
    build_policy_catalog,
    evaluate_execution_policy,
    resolve_execution_policy,
)
from .settings import (
    AGENT_SECTIONS,
    CONTROL_PLANE_AUTO_IMPORT,
    CONTROL_PLANE_RUNTIME_DIR,
    DASHBOARD_AGENT_CONSTANTS_PATH,
    DOCUMENT_KINDS,
    ROOT_DIR,
    looks_like_secret_key,
)
from .workspace_import import (
    WORKSPACE_SCAN_SCHEMA_VERSION,
    directory_roots_payload,
    list_directory_payload,
    read_importable_source_content,
    record_workspace_import_metrics,
    scan_workspace_directory,
    validate_workspace_root,
    workspace_source_from_dict,
)

log = get_logger(__name__)


def _embedding_catalog_keys() -> set[str]:
    return set(_EMBEDDING_CATALOG.keys())


_AGENT_PREFIX_RE = re.compile(r"^([A-Z0-9_]+)_(.+)$")
_TELEGRAM_AGENT_TOKEN_RE = re.compile(r"^([A-Z0-9_]+)_AGENT_TOKEN$")
_LOWERCASE_FILE_SAFE_RE = re.compile(r"[^a-z0-9_-]+")
_STATUS_VALUES = frozenset({"active", "paused", "archived"})
_SCOPE_VALUES = frozenset({"agent", "global"})
_ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_WORKSPACE_IMPORT_BLOCK_RE = re.compile(
    r"\n?<!-- koda:workspace-import:start\b.*?<!-- koda:workspace-import:end -->\n?",
    re.DOTALL,
)
_WORKSPACE_IMPORT_START = "<!-- koda:workspace-import:start"
_WORKSPACE_IMPORT_END = "<!-- koda:workspace-import:end -->"


def _redact_workspace_import_error(exc: BaseException) -> str:
    try:
        text = str(redact_value(str(exc)))
    except Exception:  # pragma: no cover - redaction must never mask scan failure handling
        text = str(exc)
    text = re.sub(
        r"(?i)((?:api[_-]?key|secret|token|password|credential|private[_-]?key)\s*[:=]\s*)[^\s,;]+",
        r"\1[REDACTED]",
        text,
    )
    return text[:500] or "workspace import scan failed"


_AGENT_DOCUMENT_LAYOUT: tuple[tuple[str, str], ...] = (
    ("identity_md", "agent_identity"),
    ("soul_md", "agent_soul"),
    ("system_prompt_md", "agent_system_prompt"),
    ("instructions_md", "agent_instructions"),
    ("rules_md", "agent_rules"),
)
_RUNTIME_INLINE_DOCUMENT_KINDS: tuple[str, ...] = (
    "identity_md",
    "soul_md",
    "system_prompt_md",
    "instructions_md",
    "rules_md",
    "voice_prompt_md",
    "image_prompt_md",
    "memory_extraction_prompt_md",
)
_KNOWLEDGE_PACK_CONTROL_KINDS = frozenset({"pack", "pack_defaults", "pack_metadata"})
_KNOWLEDGE_PACK_METADATA_FIELDS: tuple[str, ...] = (
    "pack_id",
    "updated_at",
    "owner",
    "freshness_days",
    "project_key",
    "environment",
    "team",
)
_KNOWLEDGE_ENTRY_METADATA_FIELDS: tuple[str, ...] = (
    "updated_at",
    "owner",
    "freshness_days",
    "project_key",
    "environment",
    "team",
)
_RESERVED_MCP_SERVER_KEYS: frozenset[str] = frozenset(
    {"docker", "filesystem", "github", "gitlab", "memory", "puppeteer"}
)
_ALLOWED_AUTONOMY_TIERS: frozenset[str] = frozenset({"t0", "t1", "t2"})
_ALLOWED_PROVENANCE_POLICIES: frozenset[str] = frozenset({"strict", "standard"})
_ALLOWED_VARIABLE_TYPES: frozenset[str] = frozenset({"text", "secret"})
_ALLOWED_VARIABLE_SCOPES: frozenset[str] = frozenset({"system_only", "agent_grant"})
_PROVIDER_DOWNLOAD_PROVIDER_IDS: frozenset[str] = frozenset({"kokoro", "supertonic", "whispercpp", "embedding"})


class _ProviderDownloadCancelled(RuntimeError):
    """Internal signal used to stop provider downloads cooperatively."""


class GeneralPayloadValidationError(ValueError):
    """Raised when ``put_general_system_settings`` payload fails structural validation.

    Carries a list of ``{field, code, message}`` dicts so the API layer can surface
    per-field errors back to the dashboard.
    """

    def __init__(self, errors: list[dict[str, str]]) -> None:
        self.errors = list(errors)
        super().__init__(f"invalid general settings payload: {len(self.errors)} error(s)")


def _normalize_mcp_server_key(server_key: Any) -> str:
    return str(server_key or "").strip().lower()


def _is_reserved_mcp_server_key(server_key: Any) -> bool:
    return _normalize_mcp_server_key(server_key) in _RESERVED_MCP_SERVER_KEYS


def _mcp_connection_key(server_key: Any) -> str:
    return f"mcp:{_normalize_mcp_server_key(server_key)}"


def _validate_mcp_connection_command_override(command: Any) -> list[str]:
    from koda.integrations.custom_mcp_registry import ValidationError, validate_stdio_command

    if not isinstance(command, list):
        raise ValueError("MCP command_override must be a list of argv strings.")
    try:
        return validate_stdio_command(command)
    except ValidationError as exc:
        raise ValueError(f"Invalid MCP command_override: {exc}") from exc


def _validate_mcp_connection_url_override(url: Any) -> str:
    from koda.services.mcp_client import validate_mcp_http_url

    normalized = str(url or "").strip()
    if not normalized:
        return ""
    try:
        validate_mcp_http_url(normalized)
    except Exception as exc:
        raise ValueError(f"Invalid MCP url_override: {exc}") from exc
    return normalized


def _validate_mcp_connection_env_values(env_values: Any) -> dict[str, str]:
    from koda.integrations.custom_mcp_registry import ValidationError, validate_env_name

    if not isinstance(env_values, dict):
        raise ValueError("MCP env_values must be an object.")
    normalized: dict[str, str] = {}
    for raw_key, raw_value in env_values.items():
        try:
            key = validate_env_name(str(raw_key))
        except ValidationError as exc:
            raise ValueError(f"Invalid MCP env key: {exc}") from exc
        if raw_value in (None, ""):
            continue
        if not isinstance(raw_value, str):
            raise ValueError(f"MCP env value for {key!r} must be a string.")
        normalized[key] = raw_value
    return normalized


def _core_connection_key(integration_id: Any) -> str:
    return f"core:{str(integration_id or '').strip().lower()}"


def _parse_connection_key(connection_key: Any) -> tuple[str, str]:
    raw = str(connection_key or "").strip()
    if not raw:
        raise ValueError("connection_key is required")
    if ":" in raw:
        kind, value = raw.split(":", 1)
        normalized_kind = kind.strip().lower()
        normalized_value = value.strip().lower()
        if normalized_kind in {"mcp", "core"} and normalized_value:
            if normalized_kind == "mcp":
                return "mcp", _normalize_mcp_server_key(normalized_value)
            return "core", normalized_value
    normalized = raw.lower()
    if normalized in CORE_INTEGRATION_CATALOG:
        return "core", normalized
    return "mcp", _normalize_mcp_server_key(normalized)


_CORE_CONNECTION_SOURCE_ORIGINS: frozenset[str] = frozenset(
    {"agent_binding", "imported_default", "local_session", "system_default"}
)
_CORE_LEGACY_AUTH_MODE_ALIASES: dict[str, str] = {
    "cli_auth": "local_session",
    "profile": "local_session",
}


def _normalize_user_id_values(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_items = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        raw_items = []
    normalized: list[str] = []
    for item in raw_items:
        text = str(item or "").strip()
        if not text:
            continue
        if not text.isdigit():
            raise ValueError("allowed user IDs must be numeric")
        if text not in normalized:
            normalized.append(text)
    return normalized


def _shared_platform_prompt() -> str:
    return str(SHARED_PLATFORM_PROMPT or "").strip()


def _infer_preview_provider_and_model(agent_spec: dict[str, Any]) -> tuple[str, str]:
    model_policy = _safe_json_object(agent_spec.get("model_policy"))
    default_provider = _trimmed_text(model_policy.get("default_provider")).lower()
    allowed_providers = [provider.lower() for provider in normalize_string_list(model_policy.get("allowed_providers"))]
    provider = default_provider or (allowed_providers[0] if allowed_providers else "claude")
    default_models = _safe_json_object(model_policy.get("default_models"))
    model = _trimmed_text(default_models.get(provider))
    if not model:
        functional_defaults = _normalize_functional_model_defaults(model_policy.get("functional_defaults"))
        general_default = _safe_json_object(functional_defaults.get("general"))
        if _trimmed_text(general_default.get("provider_id")).lower() == provider:
            model = _trimmed_text(general_default.get("model_id"))
    return provider or "claude", model or provider or "claude"


def _build_runtime_prompt_preview_payload(
    *,
    agent_id: str,
    agent_spec: dict[str, Any],
    compiled_prompt: str,
) -> dict[str, Any]:
    def _optional_positive_int(value: Any) -> int | None:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    provider, model = _infer_preview_provider_and_model(agent_spec)
    immutable_base_prompt = "\n\n".join(
        block for block in (compiled_prompt.strip(), _shared_platform_prompt().strip()) if block
    ).strip()
    static_segments: list[PromptSegment] = []
    tool_contracts = build_agent_tools_prompt(
        tool_policy=_safe_json_object(agent_spec.get("tool_policy")) or None,
        execution_policy=_safe_json_object(agent_spec.get("execution_policy")) or None,
        resource_access_policy=_safe_json_object(agent_spec.get("resource_access_policy")) or None,
    )
    if tool_contracts.strip():
        static_segments.append(
            PromptSegment(
                segment_id="tool_contracts",
                text=tool_contracts,
                category="tool_contracts",
                priority=30,
                compression_strategy="truncate_tail",
                drop_policy="hard_floor",
                metadata={"source": "tool_prompt"},
            )
        )
    memory_policy = _safe_json_object(agent_spec.get("memory_policy"))
    knowledge_policy = _safe_json_object(agent_spec.get("knowledge_policy"))
    category_caps: dict[str, int] = {}
    memory_cap = _optional_positive_int(memory_policy.get("max_context_tokens"))
    knowledge_cap = _optional_positive_int(knowledge_policy.get("context_max_tokens"))
    if memory_cap and memory_cap > 0:
        category_caps["memory"] = memory_cap
    if knowledge_cap and knowledge_cap > 0:
        category_caps["authoritative_knowledge"] = knowledge_cap
        category_caps["supporting_knowledge"] = max(512, int(knowledge_cap * 0.5))
    return preview_modeled_runtime_prompt(
        immutable_base_prompt=immutable_base_prompt,
        provider=provider,
        model=model,
        agent_id=agent_id,
        category_token_caps=category_caps or None,
        static_segments=static_segments,
    )


_MODEL_POLICY_ENV_KEYS: tuple[str, ...] = (
    "AGENT_MODEL_POLICY_JSON",
    "MODEL_FUNCTION_DEFAULTS_JSON",
    "MODEL_EFFORT_DEFAULT_JSON",
    "MODEL_EFFORT_DEFAULTS_JSON",
    "DEFAULT_PROVIDER",
    "PROVIDER_FALLBACK_ORDER",
    "CLAUDE_ENABLED",
    "CODEX_ENABLED",
    "GEMINI_ENABLED",
    "OLLAMA_ENABLED",
    "CLAUDE_AVAILABLE_MODELS",
    "CODEX_AVAILABLE_MODELS",
    "GEMINI_AVAILABLE_MODELS",
    "OLLAMA_AVAILABLE_MODELS",
    "CLAUDE_DEFAULT_MODEL",
    "CODEX_DEFAULT_MODEL",
    "GEMINI_DEFAULT_MODEL",
    "OLLAMA_DEFAULT_MODEL",
    "CLAUDE_MODEL_SMALL",
    "CLAUDE_MODEL_MEDIUM",
    "CLAUDE_MODEL_LARGE",
    "CODEX_MODEL_SMALL",
    "CODEX_MODEL_MEDIUM",
    "CODEX_MODEL_LARGE",
    "GEMINI_MODEL_SMALL",
    "GEMINI_MODEL_MEDIUM",
    "GEMINI_MODEL_LARGE",
    "OLLAMA_MODEL_SMALL",
    "OLLAMA_MODEL_MEDIUM",
    "OLLAMA_MODEL_LARGE",
    "GEMINI_BIN",
    "MAX_BUDGET_USD",
    "MAX_TOTAL_BUDGET_USD",
)
_TOOL_POLICY_ENV_KEYS: tuple[str, ...] = ("AGENT_ALLOWED_TOOLS", "AGENT_TOOL_POLICY_JSON")
_AUTONOMY_POLICY_ENV_KEYS: tuple[str, ...] = ("AGENT_AUTONOMY_POLICY_JSON",)
_MEMORY_POLICY_ENV_KEYS: tuple[str, ...] = (
    "MEMORY_ENABLED",
    "MEMORY_MAX_RECALL",
    "MEMORY_RECALL_THRESHOLD",
    "MEMORY_MAX_CONTEXT_TOKENS",
    "MEMORY_RECENCY_HALF_LIFE_DAYS",
    "MEMORY_MAX_EXTRACTION_ITEMS",
    "MEMORY_EXTRACTION_PROVIDER",
    "MEMORY_EXTRACTION_MODEL",
    "MEMORY_PROACTIVE_ENABLED",
    "MEMORY_PROCEDURAL_ENABLED",
    "MEMORY_PROCEDURAL_MAX_RECALL",
    "MEMORY_RECALL_TIMEOUT",
    "MEMORY_SIMILARITY_DEDUP_THRESHOLD",
    "MEMORY_MAX_PER_USER",
    "MEMORY_MAINTENANCE_ENABLED",
    "MEMORY_DIGEST_ENABLED",
)
_KNOWLEDGE_POLICY_ENV_KEYS: tuple[str, ...] = (
    "KNOWLEDGE_ENABLED",
    "KNOWLEDGE_MAX_RESULTS",
    "KNOWLEDGE_RECALL_THRESHOLD",
    "KNOWLEDGE_RECALL_TIMEOUT",
    "KNOWLEDGE_CONTEXT_MAX_TOKENS",
    "KNOWLEDGE_WORKSPACE_MAX_FILES",
    "KNOWLEDGE_SOURCE_GLOBS",
    "KNOWLEDGE_WORKSPACE_SOURCE_GLOBS",
    "KNOWLEDGE_MAX_OBSERVED_PATTERNS",
    "KNOWLEDGE_ALLOWED_LAYERS",
    "KNOWLEDGE_MAX_SOURCE_AGE_DAYS",
    "KNOWLEDGE_REQUIRE_OWNER_PROVENANCE",
    "KNOWLEDGE_REQUIRE_FRESHNESS_PROVENANCE",
    "KNOWLEDGE_PROMOTION_MODE",
    "KNOWLEDGE_STRATEGY_DEFAULT",
    "KNOWLEDGE_TRACE_SAMPLING_RATE",
    "KNOWLEDGE_GRAPH_ENABLED",
    "KNOWLEDGE_MULTIMODAL_GRAPH_ENABLED",
    "KNOWLEDGE_EVALUATION_SAMPLING_RATE",
    "KNOWLEDGE_CITATION_POLICY",
    "KNOWLEDGE_RETRIEVAL_MIN_QUALITY_TIER",
    "KNOWLEDGE_RETRIEVAL_DENSE_WINDOW",
    "KNOWLEDGE_RETRIEVAL_RERANK_TOP_K",
    "KNOWLEDGE_RETRIEVAL_VECTOR_COVERAGE_MIN",
)
_SYSTEM_SETTINGS_FIELD_SPECS: dict[str, dict[str, tuple[str, str]]] = {
    "general": {
        "owner_name": ("OWNER_NAME", "string"),
        "owner_email": ("OWNER_EMAIL", "string"),
        "owner_github": ("OWNER_GITHUB", "string"),
        "default_work_dir": ("DEFAULT_WORK_DIR", "string"),
        "project_dirs": ("PROJECT_DIRS", "csv"),
        "allowed_user_ids": ("ALLOWED_USER_IDS", "csv"),
        "knowledge_admin_user_ids": ("KNOWLEDGE_ADMIN_USER_IDS", "csv"),
        "rate_limit_per_minute": ("RATE_LIMIT_PER_MINUTE", "int"),
        "time_format": ("TIME_FORMAT", "string"),
    },
    "providers": {
        "functional_defaults": ("MODEL_FUNCTION_DEFAULTS_JSON", "json"),
        "effort_default": ("MODEL_EFFORT_DEFAULT_JSON", "json"),
        "default_provider": ("DEFAULT_PROVIDER", "string"),
        "fallback_order": ("PROVIDER_FALLBACK_ORDER", "csv"),
        "max_budget_usd": ("MAX_BUDGET_USD", "float"),
        "max_total_budget_usd": ("MAX_TOTAL_BUDGET_USD", "float"),
        # Apple Silicon Metal acceleration toggle. Drives the
        # ``is_metal_path_active`` runtime gate; only takes effect on
        # Apple Silicon hardware (no-op on Linux/x86 macOS).
        "metal_enabled": ("METAL_ENABLED", "bool"),
        "elevenlabs_default_language": ("ELEVENLABS_DEFAULT_LANGUAGE", "string"),
        "elevenlabs_default_voice": ("TTS_DEFAULT_VOICE", "string"),
        "kokoro_default_language": ("KOKORO_DEFAULT_LANGUAGE", "string"),
        "kokoro_default_voice": ("KOKORO_DEFAULT_VOICE", "string"),
        "supertonic_default_model": ("SUPERTONIC_DEFAULT_MODEL", "string"),
        "supertonic_default_language": ("SUPERTONIC_DEFAULT_LANGUAGE", "string"),
        "supertonic_default_voice": ("SUPERTONIC_DEFAULT_VOICE", "string"),
        "elevenlabs_model": ("ELEVENLABS_MODEL", "string"),
        "transcript_replay_limit": ("TRANSCRIPT_REPLAY_LIMIT", "int"),
        "claude_enabled": ("CLAUDE_ENABLED", "bool"),
        "claude_timeout": ("CLAUDE_TIMEOUT", "int"),
        "claude_available_models": ("CLAUDE_AVAILABLE_MODELS", "csv"),
        "claude_default_model": ("CLAUDE_DEFAULT_MODEL", "string"),
        "claude_model_small": ("CLAUDE_MODEL_SMALL", "string"),
        "claude_model_medium": ("CLAUDE_MODEL_MEDIUM", "string"),
        "claude_model_large": ("CLAUDE_MODEL_LARGE", "string"),
        "codex_enabled": ("CODEX_ENABLED", "bool"),
        "codex_bin": ("CODEX_BIN", "string"),
        "codex_timeout": ("CODEX_TIMEOUT", "int"),
        "codex_first_chunk_timeout": ("CODEX_FIRST_CHUNK_TIMEOUT", "int"),
        "codex_sandbox": ("CODEX_SANDBOX", "string"),
        "codex_approval_policy": ("CODEX_APPROVAL_POLICY", "string"),
        "codex_skip_git_repo_check": ("CODEX_SKIP_GIT_REPO_CHECK", "bool"),
        "codex_available_models": ("CODEX_AVAILABLE_MODELS", "csv"),
        "codex_default_model": ("CODEX_DEFAULT_MODEL", "string"),
        "codex_model_small": ("CODEX_MODEL_SMALL", "string"),
        "codex_model_medium": ("CODEX_MODEL_MEDIUM", "string"),
        "codex_model_large": ("CODEX_MODEL_LARGE", "string"),
        "gemini_enabled": ("GEMINI_ENABLED", "bool"),
        "gemini_bin": ("GEMINI_BIN", "string"),
        "gemini_timeout": ("GEMINI_TIMEOUT", "int"),
        "gemini_first_chunk_timeout": ("GEMINI_FIRST_CHUNK_TIMEOUT", "int"),
        "gemini_available_models": ("GEMINI_AVAILABLE_MODELS", "csv"),
        "gemini_default_model": ("GEMINI_DEFAULT_MODEL", "string"),
        "gemini_model_small": ("GEMINI_MODEL_SMALL", "string"),
        "gemini_model_medium": ("GEMINI_MODEL_MEDIUM", "string"),
        "gemini_model_large": ("GEMINI_MODEL_LARGE", "string"),
        "ollama_enabled": ("OLLAMA_ENABLED", "bool"),
        "ollama_timeout": ("OLLAMA_TIMEOUT", "int"),
        "ollama_available_models": ("OLLAMA_AVAILABLE_MODELS", "csv"),
        "ollama_default_model": ("OLLAMA_DEFAULT_MODEL", "string"),
        "ollama_model_small": ("OLLAMA_MODEL_SMALL", "string"),
        "ollama_model_medium": ("OLLAMA_MODEL_MEDIUM", "string"),
        "ollama_model_large": ("OLLAMA_MODEL_LARGE", "string"),
        "openrouter_enabled": ("OPENROUTER_ENABLED", "bool"),
        "openrouter_available_models": ("OPENROUTER_AVAILABLE_MODELS", "csv"),
        "openrouter_default_model": ("OPENROUTER_DEFAULT_MODEL", "string"),
        "openrouter_model_small": ("OPENROUTER_MODEL_SMALL", "string"),
        "openrouter_model_medium": ("OPENROUTER_MODEL_MEDIUM", "string"),
        "openrouter_model_large": ("OPENROUTER_MODEL_LARGE", "string"),
        "openrouter_timeout": ("OPENROUTER_TIMEOUT", "int"),
        "openrouter_first_chunk_timeout": ("OPENROUTER_FIRST_CHUNK_TIMEOUT", "int"),
        "openrouter_api_base_url": ("OPENROUTER_API_BASE_URL", "string"),
        "openrouter_http_referer": ("OPENROUTER_HTTP_REFERER", "string"),
        "openrouter_app_title": ("OPENROUTER_APP_TITLE", "string"),
        "openrouter_app_categories": ("OPENROUTER_APP_CATEGORIES", "string"),
    },
    "tools": {
        "default_agent_mode": ("DEFAULT_AGENT_MODE", "string"),
        "shell_enabled": ("SHELL_ENABLED", "bool"),
        "pip_enabled": ("PIP_ENABLED", "bool"),
        "npm_enabled": ("NPM_ENABLED", "bool"),
        "max_agent_tool_iterations": ("MAX_AGENT_TOOL_ITERATIONS", "int"),
        "agent_tool_timeout": ("AGENT_TOOL_TIMEOUT", "int"),
        "browser_tool_timeout": ("BROWSER_TOOL_TIMEOUT", "int"),
        "cache_enabled": ("CACHE_ENABLED", "bool"),
        "cache_ttl_days": ("CACHE_TTL_DAYS", "int"),
        "script_library_enabled": ("SCRIPT_LIBRARY_ENABLED", "bool"),
        "script_max_per_user": ("SCRIPT_MAX_PER_USER", "int"),
    },
    "integrations": {
        "browser_enabled": ("BROWSER_ENABLED", "bool"),
        "whisper_enabled": ("WHISPER_ENABLED", "bool"),
        "tts_enabled": ("TTS_ENABLED", "bool"),
        "link_analysis_enabled": ("LINK_ANALYSIS_ENABLED", "bool"),
        "docker_enabled": ("DOCKER_ENABLED", "bool"),
    },
    "memory": {
        "enabled": ("MEMORY_ENABLED", "bool"),
        "max_recall": ("MEMORY_MAX_RECALL", "int"),
        "recall_threshold": ("MEMORY_RECALL_THRESHOLD", "float"),
        "max_context_tokens": ("MEMORY_MAX_CONTEXT_TOKENS", "int"),
        "max_extraction_items": ("MEMORY_MAX_EXTRACTION_ITEMS", "int"),
        "extraction_provider": ("MEMORY_EXTRACTION_PROVIDER", "string"),
        "extraction_model": ("MEMORY_EXTRACTION_MODEL", "string"),
        "proactive_enabled": ("MEMORY_PROACTIVE_ENABLED", "bool"),
        "procedural_enabled": ("MEMORY_PROCEDURAL_ENABLED", "bool"),
        "procedural_max_recall": ("MEMORY_PROCEDURAL_MAX_RECALL", "int"),
        "recall_timeout": ("MEMORY_RECALL_TIMEOUT", "float"),
        "similarity_dedup_threshold": ("MEMORY_SIMILARITY_DEDUP_THRESHOLD", "float"),
        "max_per_user": ("MEMORY_MAX_PER_USER", "int"),
        "maintenance_enabled": ("MEMORY_MAINTENANCE_ENABLED", "bool"),
        "digest_enabled": ("MEMORY_DIGEST_ENABLED", "bool"),
    },
    "knowledge": {
        "enabled": ("KNOWLEDGE_ENABLED", "bool"),
        "max_results": ("KNOWLEDGE_MAX_RESULTS", "int"),
        "recall_threshold": ("KNOWLEDGE_RECALL_THRESHOLD", "float"),
        "recall_timeout": ("KNOWLEDGE_RECALL_TIMEOUT", "float"),
        "context_max_tokens": ("KNOWLEDGE_CONTEXT_MAX_TOKENS", "int"),
        "workspace_max_files": ("KNOWLEDGE_WORKSPACE_MAX_FILES", "int"),
        "source_globs": ("KNOWLEDGE_SOURCE_GLOBS", "csv"),
        "workspace_source_globs": ("KNOWLEDGE_WORKSPACE_SOURCE_GLOBS", "csv"),
        "max_observed_patterns": ("KNOWLEDGE_MAX_OBSERVED_PATTERNS", "int"),
        "allowed_layers": ("KNOWLEDGE_ALLOWED_LAYERS", "csv"),
        "max_source_age_days": ("KNOWLEDGE_MAX_SOURCE_AGE_DAYS", "int"),
        "require_owner_provenance": ("KNOWLEDGE_REQUIRE_OWNER_PROVENANCE", "bool"),
        "require_freshness_provenance": ("KNOWLEDGE_REQUIRE_FRESHNESS_PROVENANCE", "bool"),
        "promotion_mode": ("KNOWLEDGE_PROMOTION_MODE", "string"),
        "allowed_source_labels": ("KNOWLEDGE_ALLOWED_SOURCE_LABELS", "csv"),
        "allowed_workspace_roots": ("KNOWLEDGE_ALLOWED_WORKSPACE_ROOTS", "csv"),
        "storage_mode": ("KNOWLEDGE_V2_STORAGE_MODE", "string"),
    },
    "runtime": {
        "runtime_environments_enabled": ("RUNTIME_ENVIRONMENTS_ENABLED", "bool"),
        "runtime_event_stream_enabled": ("RUNTIME_EVENT_STREAM_ENABLED", "bool"),
        "runtime_pty_enabled": ("RUNTIME_PTY_ENABLED", "bool"),
        "runtime_browser_live_enabled": ("RUNTIME_BROWSER_LIVE_ENABLED", "bool"),
        "runtime_recovery_enabled": ("RUNTIME_RECOVERY_ENABLED", "bool"),
        "runtime_frontend_api_enabled": ("RUNTIME_FRONTEND_API_ENABLED", "bool"),
        "runtime_heartbeat_interval_seconds": ("RUNTIME_HEARTBEAT_INTERVAL_SECONDS", "int"),
        "runtime_stale_after_seconds": ("RUNTIME_STALE_AFTER_SECONDS", "int"),
        "runtime_resource_sample_interval_seconds": ("RUNTIME_RESOURCE_SAMPLE_INTERVAL_SECONDS", "int"),
        "runtime_recovery_sweep_interval_seconds": ("RUNTIME_RECOVERY_SWEEP_INTERVAL_SECONDS", "int"),
        "runtime_cleanup_sweep_interval_seconds": ("RUNTIME_CLEANUP_SWEEP_INTERVAL_SECONDS", "int"),
        "runtime_local_ui_bind": ("RUNTIME_LOCAL_UI_BIND", "string"),
        "runtime_supervised_attach_enabled": ("RUNTIME_SUPERVISED_ATTACH_ENABLED", "bool"),
        "runtime_operator_session_ttl_seconds": ("RUNTIME_OPERATOR_SESSION_TTL_SECONDS", "int"),
        "runtime_attach_idle_timeout_seconds": ("RUNTIME_ATTACH_IDLE_TIMEOUT_SECONDS", "int"),
        "runtime_browser_transport": ("RUNTIME_BROWSER_TRANSPORT", "string"),
        "runtime_browser_display_base": ("RUNTIME_BROWSER_DISPLAY_BASE", "int"),
        "runtime_browser_vnc_base_port": ("RUNTIME_BROWSER_VNC_BASE_PORT", "int"),
        "runtime_browser_novnc_base_port": ("RUNTIME_BROWSER_NOVNC_BASE_PORT", "int"),
    },
    "scheduler": {
        "scheduler_enabled": ("SCHEDULER_ENABLED", "bool"),
        "scheduler_poll_interval_seconds": ("SCHEDULER_POLL_INTERVAL_SECONDS", "int"),
        "scheduler_lease_seconds": ("SCHEDULER_LEASE_SECONDS", "int"),
        "scheduler_max_catchup_per_cycle": ("SCHEDULER_MAX_CATCHUP_PER_CYCLE", "int"),
        "scheduler_max_dispatch_per_cycle": ("SCHEDULER_MAX_DISPATCH_PER_CYCLE", "int"),
        "scheduler_run_max_attempts": ("SCHEDULER_RUN_MAX_ATTEMPTS", "int"),
        "scheduler_retry_base_delay": ("SCHEDULER_RETRY_BASE_DELAY", "int"),
        "scheduler_retry_max_delay": ("SCHEDULER_RETRY_MAX_DELAY", "int"),
        "scheduler_min_interval_seconds": ("SCHEDULER_MIN_INTERVAL_SECONDS", "int"),
        "scheduler_max_concurrent_runs_per_job": ("SCHEDULER_MAX_CONCURRENT_RUNS_PER_JOB", "int"),
        "scheduler_notification_mode": ("SCHEDULER_NOTIFICATION_MODE", "string"),
        "scheduler_default_timezone": ("SCHEDULER_DEFAULT_TIMEZONE", "string"),
        "runbook_governance_enabled": ("RUNBOOK_GOVERNANCE_ENABLED", "bool"),
        "runbook_governance_hour": ("RUNBOOK_GOVERNANCE_HOUR", "int"),
        "runbook_revalidation_stale_days": ("RUNBOOK_REVALIDATION_STALE_DAYS", "int"),
        "runbook_revalidation_min_verified_runs": ("RUNBOOK_REVALIDATION_MIN_VERIFIED_RUNS", "int"),
        "runbook_revalidation_min_success_rate": ("RUNBOOK_REVALIDATION_MIN_SUCCESS_RATE", "float"),
        "runbook_revalidation_correction_threshold": ("RUNBOOK_REVALIDATION_CORRECTION_THRESHOLD", "int"),
        "runbook_revalidation_rollback_threshold": ("RUNBOOK_REVALIDATION_ROLLBACK_THRESHOLD", "int"),
    },
}
_SYSTEM_SETTINGS_SECTIONS: tuple[str, ...] = tuple(_SYSTEM_SETTINGS_FIELD_SPECS)
_SYSTEM_SETTINGS_KNOWN_ENV_KEYS: frozenset[str] = frozenset(
    {
        *(env_key for section in _SYSTEM_SETTINGS_FIELD_SPECS.values() for env_key, _kind in section.values()),
        *PROVIDER_API_KEY_ENV_KEYS.values(),
        *PROVIDER_AUTH_MODE_ENV_KEYS.values(),
        *PROVIDER_VERIFIED_ENV_KEYS.values(),
        *(value for value in PROVIDER_BASE_URL_ENV_KEYS.values() if value),
        *(value for value in PROVIDER_PROJECT_ENV_KEYS.values() if value),
        # Policy-derived env keys (`AGENT_AUTONOMY_POLICY_JSON`,
        # `MEMORY_RECENCY_HALF_LIFE_DAYS`, `KNOWLEDGE_GRAPH_ENABLED`, …) are
        # written by `_apply_*_policy_to_section` whenever the operator changes
        # a related toggle. They are stored in DB sections and serialized to
        # env to feed runtime workers, but they are not user-defined variables
        # — must not surface in the dashboard's "Variables" list.
        *_MODEL_POLICY_ENV_KEYS,
        *_TOOL_POLICY_ENV_KEYS,
        *_AUTONOMY_POLICY_ENV_KEYS,
        *_MEMORY_POLICY_ENV_KEYS,
        *_KNOWLEDGE_POLICY_ENV_KEYS,
    }
)
_CORE_PROVIDER_ENABLED_DEFAULTS: dict[str, bool] = {
    "claude": True,
    "codex": True,
    "gemini": False,
    "ollama": False,
    "elevenlabs": False,
    "openrouter": False,
    "kokoro": True,
    "supertonic": True,
    "whispercpp": True,
}
_SHARED_ENV_RESERVED_PREFIXES: tuple[str, ...] = (
    "AGENT_",
    "RUNTIME_",
    "MEMORY_",
    "KNOWLEDGE_",
    "SCHEDULER_",
    "RUNBOOK_",
    "CLAUDE_",
    "CODEX_",
    "OPENAI_",
    "ANTHROPIC_",
    "AZURE_OPENAI_",
    "OPENROUTER_",
    "SUPERTONIC_",
)
_LOCAL_ENV_RESERVED_PREFIXES: tuple[str, ...] = tuple(
    prefix for prefix in _SHARED_ENV_RESERVED_PREFIXES if prefix != "AGENT_"
)
_SHARED_ENV_BLOCKED_KEYS: frozenset[str] = frozenset(
    set(_SYSTEM_SETTINGS_KNOWN_ENV_KEYS)
    | set(_MODEL_POLICY_ENV_KEYS)
    | set(_TOOL_POLICY_ENV_KEYS)
    | set(_AUTONOMY_POLICY_ENV_KEYS)
    | set(_MEMORY_POLICY_ENV_KEYS)
    | set(_KNOWLEDGE_POLICY_ENV_KEYS)
    | {
        "AGENT_SPEC_JSON",
        "AGENT_SPEC_PATH",
        "AGENT_TOKEN",
        "AGENT_COMPILED_PROMPT_TEXT",
        "CONTROL_PLANE_ACTIVE_VERSION",
        "CONTROL_PLANE_RUNTIME_INLINE",
        "DEFAULT_IMAGE_PROMPT_TEXT",
        "DEFAULT_MODEL",
        "KNOWLEDGE_PACK_TOML",
        "MEMORY_EXTRACTION_PROMPT_TEXT",
        "MEMORY_PROFILE_TOML",
        "MODEL_PRICING_USD",
        "RUNTIME_LOCAL_UI_TOKEN",
        "TEMPLATES_JSON",
        "TEMPLATES_PATH",
        "VOICE_ACTIVE_PROMPT_TEXT",
    }
)
_NON_SECRET_SYSTEM_ENV_KEYS: frozenset[str] = frozenset(
    set(_SYSTEM_SETTINGS_KNOWN_ENV_KEYS)
    | set(_MODEL_POLICY_ENV_KEYS)
    | set(_TOOL_POLICY_ENV_KEYS)
    | set(_AUTONOMY_POLICY_ENV_KEYS)
    | set(_MEMORY_POLICY_ENV_KEYS)
    | set(_KNOWLEDGE_POLICY_ENV_KEYS)
    | {"DEFAULT_MODEL", "MODEL_PRICING_USD"}
)
_CORE_ONLY_GLOBAL_SECRET_KEYS: frozenset[str] = frozenset({"RUNTIME_LOCAL_UI_TOKEN"})
_REMOVED_GLOBAL_SECRET_KEYS: frozenset[str] = frozenset({"RUNTIME_TOKEN"})
_HIDDEN_GLOBAL_SECRET_KEYS: frozenset[str] = frozenset({"POSTGRES_URL"})
_GENERAL_ALLOWED_USAGE_SCOPES: frozenset[str] = frozenset({"system_only", "agent_grant"})
_GENERAL_ALLOWED_VALUE_TYPES: frozenset[str] = frozenset({"text", "secret"})
_PROVIDER_LOGIN_SESSION_PENDING_TTL = timedelta(hours=1)
_PROVIDER_LOGIN_SESSION_HISTORY_TTL = timedelta(hours=24)
_PROVIDER_LOGIN_SESSION_ENCRYPTED_DETAILS_KEY = "encrypted_details"
_PROVIDER_LOGIN_SESSION_SENSITIVE_KEYS: tuple[str, ...] = (
    "auth_url",
    "user_code",
    "message",
    "instructions",
    "output_preview",
    "last_error",
    "code_verifier",
)
_PROVIDER_DOWNLOAD_HISTORY_TTL = timedelta(hours=24)
_GENERAL_FIELD_SOURCE_ENV_KEYS: dict[str, str] = {
    "account.owner_name": "OWNER_NAME",
    "account.owner_email": "OWNER_EMAIL",
    "account.owner_github": "OWNER_GITHUB",
    "account.default_work_dir": "DEFAULT_WORK_DIR",
    "account.project_dirs": "PROJECT_DIRS",
    "account.scheduler_default_timezone": "SCHEDULER_DEFAULT_TIMEZONE",
    "account.rate_limit_per_minute": "RATE_LIMIT_PER_MINUTE",
    "models.default_provider": "DEFAULT_PROVIDER",
    "models.functional_defaults": "MODEL_FUNCTION_DEFAULTS_JSON",
    "models.effort_default": "MODEL_EFFORT_DEFAULT_JSON",
    "models.max_budget_usd": "MAX_BUDGET_USD",
    "models.max_total_budget_usd": "MAX_TOTAL_BUDGET_USD",
    "models.elevenlabs_default_language": "ELEVENLABS_DEFAULT_LANGUAGE",
    "models.elevenlabs_default_voice": "TTS_DEFAULT_VOICE",
    "models.kokoro_default_language": "KOKORO_DEFAULT_LANGUAGE",
    "models.kokoro_default_voice": "KOKORO_DEFAULT_VOICE",
    "models.supertonic_default_model": "SUPERTONIC_DEFAULT_MODEL",
    "models.supertonic_default_language": "SUPERTONIC_DEFAULT_LANGUAGE",
    "models.supertonic_default_voice": "SUPERTONIC_DEFAULT_VOICE",
    "models.elevenlabs_model": "ELEVENLABS_MODEL",
    "models.metal_enabled": "METAL_ENABLED",
    "memory.memory_enabled": "MEMORY_ENABLED",
    "memory.procedural_enabled": "MEMORY_PROCEDURAL_ENABLED",
    "memory.proactive_enabled": "MEMORY_PROACTIVE_ENABLED",
    "memory.knowledge_enabled": "KNOWLEDGE_ENABLED",
}
_GENERAL_MODEL_USAGE_PROFILES: dict[str, dict[str, Any]] = {
    "economy": {
        "label": "Economia",
        "description": "Prioriza custo e rapidez com modelos menores como default.",
        "tier": "small",
    },
    "balanced": {
        "label": "Equilibrado",
        "description": "Combina custo e qualidade para a maioria dos fluxos.",
        "tier": "medium",
    },
    "quality": {
        "label": "Qualidade",
        "description": "Prioritizes the highest quality with the largest available models.",
        "tier": "large",
    },
}
_GENERAL_MEMORY_PROFILES: dict[str, dict[str, Any]] = {
    "conservative": {
        "label": "Conservador",
        "description": "Smaller memory footprint, more selective recall, and lower maintenance cost.",
        "settings": {
            "max_recall": 8,
            "recall_threshold": 0.78,
            "max_context_tokens": 4000,
            "max_extraction_items": 3,
            "procedural_max_recall": 2,
            "recall_timeout": 2.5,
            "similarity_dedup_threshold": 0.94,
            "max_per_user": 200,
            "maintenance_enabled": True,
            "digest_enabled": False,
        },
    },
    "balanced": {
        "label": "Equilibrado",
        "description": "Perfil recomendado para a maioria dos agentes profissionais.",
        "settings": {
            "max_recall": 18,
            "recall_threshold": 0.68,
            "max_context_tokens": 8000,
            "max_extraction_items": 5,
            "procedural_max_recall": 4,
            "recall_timeout": 4.0,
            "similarity_dedup_threshold": 0.9,
            "max_per_user": 500,
            "maintenance_enabled": True,
            "digest_enabled": True,
        },
    },
    "strong_learning": {
        "label": "Aprendizado forte",
        "description": "Increases retention and recall for agents that must learn continuously.",
        "settings": {
            "max_recall": 30,
            "recall_threshold": 0.55,
            "max_context_tokens": 12000,
            "max_extraction_items": 8,
            "procedural_max_recall": 8,
            "recall_timeout": 5.5,
            "similarity_dedup_threshold": 0.85,
            "max_per_user": 1000,
            "maintenance_enabled": True,
            "digest_enabled": True,
        },
    },
}
_GENERAL_KNOWLEDGE_PROFILES: dict[str, dict[str, Any]] = {
    "curated_only": {
        "label": "Curado apenas",
        "description": "Uses only canonical knowledge and approved runbooks.",
        "settings": {
            "max_results": 4,
            "recall_threshold": 0.7,
            "context_max_tokens": 5000,
            "workspace_max_files": 0,
            "allowed_layers": ["canonical_policy", "approved_runbook"],
            "max_observed_patterns": 0,
            "max_source_age_days": 45,
        },
    },
    "curated_workspace": {
        "label": "Curado + workspace",
        "description": "Mixes approved knowledge with dynamic workspace documents.",
        "settings": {
            "max_results": 6,
            "recall_threshold": 0.63,
            "context_max_tokens": 7000,
            "workspace_max_files": 6,
            "allowed_layers": ["canonical_policy", "approved_runbook", "workspace_doc"],
            "max_observed_patterns": 2,
            "max_source_age_days": 30,
        },
    },
    "curated_workspace_patterns": {
        "label": "Curated + workspace + patterns",
        "description": "Includes observed patterns as an additional weak grounding layer.",
        "settings": {
            "max_results": 8,
            "recall_threshold": 0.57,
            "context_max_tokens": 9000,
            "workspace_max_files": 8,
            "allowed_layers": [
                "canonical_policy",
                "approved_runbook",
                "workspace_doc",
                "observed_pattern",
            ],
            "max_observed_patterns": 6,
            "max_source_age_days": 21,
        },
    },
}
_GENERAL_MEMORY_POLICY_FIELD_NAMES: tuple[str, ...] = (
    "enabled",
    "max_recall",
    "recall_threshold",
    "max_context_tokens",
    "recency_half_life_days",
    "max_extraction_items",
    "extraction_provider",
    "extraction_model",
    "proactive_enabled",
    "procedural_enabled",
    "procedural_max_recall",
    "recall_timeout",
    "similarity_dedup_threshold",
    "max_per_user",
    "maintenance_enabled",
    "digest_enabled",
    "promotion_mode",
)
_GENERAL_KNOWLEDGE_POLICY_FIELD_NAMES: tuple[str, ...] = (
    "enabled",
    "max_results",
    "recall_threshold",
    "recall_timeout",
    "context_max_tokens",
    "workspace_max_files",
    "source_globs",
    "workspace_source_globs",
    "max_observed_patterns",
    "allowed_layers",
    "max_source_age_days",
    "require_owner_provenance",
    "require_freshness_provenance",
    "promotion_mode",
    "strategy_default",
    "trace_sampling_rate",
    "graph_enabled",
    "multimodal_graph_enabled",
    "evaluation_sampling_rate",
    "citation_policy",
    "v2_enabled",
    "v2_max_graph_hops",
    "cross_encoder_model",
    "object_store_root",
    "allowed_source_labels",
    "allowed_workspace_roots",
    "storage_mode",
)
_GENERAL_INTEGRATION_CREDENTIAL_TEMPLATES: dict[str, dict[str, Any]] = {}
_CORE_CONNECTION_RUNTIME_ENV_KEYS: frozenset[str] = frozenset(
    {
        str(field.get("key") or "").strip().upper()
        for template in _GENERAL_INTEGRATION_CREDENTIAL_TEMPLATES.values()
        for field in template.get("fields", ())
        if str(field.get("key") or "").strip()
    }
)


@dataclass(slots=True)
class RuntimeSnapshot:
    agent_id: str
    version: int
    runtime_dir: Path
    process_env: dict[str, str]
    connection_refs: list[dict[str, Any]]
    health_url: str
    runtime_base_url: str
    state_backend: str
    db_file_name: str
    persisted_to_disk: bool = False

    @property
    def env(self) -> dict[str, str]:
        return self.process_env


def _normalize_agent_id(agent_id: str) -> str:
    normalized = re.sub(r"[^A-Z0-9_]+", "_", agent_id.strip().upper()).strip("_")
    if not normalized:
        raise ValueError("agent_id must contain at least one alphanumeric character")
    return normalized


def _slug(value: str) -> str:
    return _LOWERCASE_FILE_SAFE_RE.sub("_", value.lower()).strip("_") or "default"


def _normalize_optional_org_id(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return _slug(text)


def _scope_id(agent_id: str | None) -> str:
    return _normalize_agent_id(agent_id) if agent_id else "global"


def _normalize_status(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in _STATUS_VALUES:
        raise ValueError(f"invalid agent status: {value}")
    return normalized


def _normalize_scope(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in _SCOPE_VALUES:
        raise ValueError(f"invalid scope: {value}")
    return normalized


def _normalize_secret_key(secret_key: str) -> str:
    normalized = secret_key.strip().upper()
    if not _ENV_KEY_RE.fullmatch(normalized):
        raise ValueError("secret key must be an uppercase environment-style key")
    return normalized


def _safe_json_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _row_has_column(row: Any, column: str) -> bool:
    keys = getattr(row, "keys", None)
    return callable(keys) and column in keys()


def _safe_json_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _row_json(row: Any, column: str) -> dict[str, Any]:
    """Safely extract a JSON column from a DB row as a dict."""
    raw = row.get(column) if hasattr(row, "get") else None
    return _safe_json_object(json_load(raw or "{}", {}))


def _row_json_list(row: Any, column: str) -> list[Any]:
    raw = row.get(column) if hasattr(row, "get") else None
    loaded = json_load(raw or "[]", [])
    return loaded if isinstance(loaded, list) else []


def _row_text(row: Any, column: str, default: str = "") -> str:
    if not _row_has_column(row, column):
        return default
    value = row.get(column) if hasattr(row, "get") else None
    return str(value or default)


def _workspace_scan_sources(scan_payload: dict[str, Any]) -> list[dict[str, Any]]:
    sources = scan_payload.get("sources")
    return [item for item in sources if isinstance(item, dict)] if isinstance(sources, list) else []


def _workspace_scan_summary(scan_payload: dict[str, Any]) -> dict[str, Any]:
    summary = scan_payload.get("summary")
    if isinstance(summary, dict):
        return dict(summary)
    sources = _workspace_scan_sources(scan_payload)
    by_kind: dict[str, int] = {}
    by_tool: dict[str, int] = {}
    by_risk: dict[str, int] = {}
    for source in sources:
        kind = str(source.get("kind") or "unknown")
        tool = str(source.get("tool") or "generic")
        risk = str(source.get("risk") or "review")
        by_kind[kind] = by_kind.get(kind, 0) + 1
        by_tool[tool] = by_tool.get(tool, 0) + 1
        by_risk[risk] = by_risk.get(risk, 0) + 1
    return {
        "total_sources": len(sources),
        "by_kind": by_kind,
        "by_tool": by_tool,
        "by_risk": by_risk,
        "review_required": sum(1 for source in sources if str(source.get("risk") or "") in {"review", "high"}),
        "blocked": sum(1 for source in sources if str(source.get("risk") or "") == "blocked"),
        "importable": sum(
            1 for source in sources if str(source.get("import_action") or "") == "append_workspace_prompt"
        ),
    }


def _user_selectable_provider_ids(provider_catalog: dict[str, Any]) -> list[str]:
    return [
        provider_id
        for provider_id, payload in _safe_json_object(provider_catalog.get("providers")).items()
        if _nonempty_text(_safe_json_object(payload).get("category")) != "infra"
    ]


def _downloaded_whisper_catalog_models(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], str]:
    items = [cast(dict[str, Any], _safe_json_object(item)) for item in _safe_json_list(payload.get("items")) if item]
    downloaded = [
        variant_id
        for variant_id in (_nonempty_text(item.get("variant_id")) for item in items if bool(item.get("downloaded")))
        if variant_id
    ]
    default_variant = _nonempty_text(payload.get("default_variant"))
    default_model = default_variant if default_variant in downloaded else (downloaded[0] if downloaded else "")
    return items, downloaded, default_model


def _provider_command_availability_issues(provider_catalog: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for provider, raw_payload in _safe_json_object(provider_catalog.get("providers")).items():
        payload = _safe_json_object(raw_payload)
        if not bool(payload.get("enabled")):
            continue
        category = str(payload.get("category") or "general")
        if category == "infra" or bool(payload.get("command_present")):
            continue
        message = f"provider '{provider}' is enabled but its runtime command is not available"
        if category == "general":
            errors.append(message)
        else:
            warnings.append(message)
    return errors, warnings


def _runtime_endpoint_payload_for_port(port: int) -> dict[str, Any]:
    return {
        "health_port": port,
        "health_url": f"http://127.0.0.1:{port}/health",
        "runtime_base_url": f"http://127.0.0.1:{port}",
    }


def _runtime_health_port_from_endpoint(endpoint: dict[str, Any]) -> int:
    raw_port = endpoint.get("health_port")
    if raw_port not in (None, ""):
        with contextlib.suppress(TypeError, ValueError):
            return int(str(raw_port))
    raw_url = str(endpoint.get("health_url") or endpoint.get("runtime_base_url") or "").strip()
    if raw_url:
        with contextlib.suppress(ValueError):
            parsed = urllib.parse.urlparse(raw_url)
            parsed_port = parsed.port
            if parsed_port:
                return int(parsed_port)
    return 0


def _stringify_env_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, (int, float, str)):
        return str(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _typed_env_value(value: str | None, kind: str) -> Any:
    raw = str(value or "").strip()
    if not raw:
        if kind in {"bool", "int", "float"}:
            return None
        if kind == "csv":
            return []
        if kind == "json":
            return {}
        return ""
    if kind == "bool":
        return raw.lower() in {"1", "true", "yes", "on"}
    if kind == "int":
        try:
            return int(raw)
        except ValueError:
            return None
    if kind == "float":
        try:
            return float(raw)
        except ValueError:
            return None
    if kind == "csv":
        return [item.strip() for item in raw.split(",") if item.strip()]
    if kind == "json":
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return raw


def _normalize_functional_model_defaults(value: Any) -> dict[str, dict[str, str]]:
    normalized: dict[str, dict[str, str]] = {}
    for function_id, payload in _safe_json_object(value).items():
        function_key = str(function_id).strip().lower()
        if function_key not in MODEL_FUNCTION_IDS:
            continue
        item = _safe_json_object(payload)
        provider_id = _trimmed_text(item.get("provider_id")).lower()
        model_id = _trimmed_text(item.get("model_id"))
        if not provider_id or not model_id:
            continue
        normalized[function_key] = {
            "provider_id": provider_id,
            "model_id": model_id,
        }
        model_label = _trimmed_text(item.get("model_label"))
        if model_label:
            normalized[function_key]["model_label"] = model_label
        provider_title = _trimmed_text(item.get("provider_title"))
        if provider_title:
            normalized[function_key]["provider_title"] = provider_title
    return normalized


def _normalize_env_entry_key(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    return "".join(char if char.isalnum() or char == "_" else "_" for char in text).strip("_")


def _normalize_env_entries(items: Any) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in _safe_json_list(items):
        payload = _safe_json_object(item)
        key = _normalize_env_entry_key(payload.get("key"))
        value = str(payload.get("value") or "").strip()
        if key and value:
            normalized.append({"key": key, "value": value})
    return normalized


def _deep_merge_json_objects(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_json_objects(_safe_json_object(existing), _safe_json_object(value))
            continue
        merged[key] = value
    return merged


def _shared_env_key_is_reserved(key: str) -> bool:
    return key in _SHARED_ENV_BLOCKED_KEYS or key.startswith(_SHARED_ENV_RESERVED_PREFIXES)


def _local_env_key_is_reserved(key: str) -> bool:
    return key in _SHARED_ENV_BLOCKED_KEYS or key.startswith(_LOCAL_ENV_RESERVED_PREFIXES)


def _global_secret_is_grantable(secret_key: str) -> bool:
    normalized = str(secret_key or "").strip().upper()
    if (
        normalized in _CORE_ONLY_GLOBAL_SECRET_KEYS
        or normalized in _REMOVED_GLOBAL_SECRET_KEYS
        or normalized in _HIDDEN_GLOBAL_SECRET_KEYS
    ):
        return False
    return not normalized.startswith("CONTROL_PLANE_")


def _normalize_general_usage_scope(value: Any, *, default: str = "agent_grant") -> str:
    normalized = str(value or "").strip().lower()
    if normalized in _GENERAL_ALLOWED_USAGE_SCOPES:
        return normalized
    return default


def _normalize_general_value_type(value: Any, *, default: str = "text") -> str:
    normalized = str(value or "").strip().lower()
    if normalized in _GENERAL_ALLOWED_VALUE_TYPES:
        return normalized
    return default


def _nonempty_text(value: Any) -> str:
    return str(value or "").strip()


def _sanitize_local_env_overrides(value: Any) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    for key, raw_value in _safe_json_object(value).items():
        env_key = _normalize_env_entry_key(key)
        env_value = _nonempty_text(raw_value)
        if not env_key or not env_value:
            continue
        if env_key in {"AGENT_TOKEN", "RUNTIME_LOCAL_UI_TOKEN"}:
            continue
        if looks_like_secret_key(env_key) or _local_env_key_is_reserved(env_key):
            continue
        sanitized[env_key] = env_value
    return sanitized


def _section_env(data: dict[str, Any]) -> dict[str, str]:
    env: dict[str, str] = {}
    explicit = data.get("env")
    if isinstance(explicit, dict):
        for key, value in explicit.items():
            if isinstance(key, str) and key.strip():
                env[key.strip().upper()] = _stringify_env_value(value)
    for key, value in data.items():
        if key == "env":
            continue
        if isinstance(key, str) and key.isupper():
            env[key] = _stringify_env_value(value)
    return env


def _toml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def _toml_list(values: list[Any]) -> str:
    return "[" + ", ".join(_toml_scalar(value) for value in values) + "]"


def _dict_to_toml_lines(data: dict[str, Any], prefix: str = "") -> list[str]:
    lines: list[str] = []
    nested: list[tuple[str, dict[str, Any]]] = []
    for key, value in data.items():
        if isinstance(value, dict):
            nested.append((key, value))
            continue
        if isinstance(value, list):
            lines.append(f"{key} = {_toml_list(value)}")
            continue
        lines.append(f"{key} = {_toml_scalar(value)}")
    for key, value in nested:
        section = f"{prefix}{key}" if prefix else key
        lines.append("")
        lines.append(f"[{section}]")
        lines.extend(_dict_to_toml_lines(value, prefix=f"{section}."))
    return lines


def _render_memory_profile(profile: dict[str, Any]) -> str:
    return "\n".join(_dict_to_toml_lines(profile)).strip() + "\n"


def _memory_profile_from_policy(memory_policy: dict[str, Any]) -> dict[str, Any]:
    profile = dict(_safe_json_object(memory_policy.get("profile")))
    if profile:
        return profile
    derived: dict[str, Any] = {}
    for key in (
        "focus_domains",
        "preferred_layers",
        "forbidden_layers_for_actions",
        "ignored_patterns",
        "risk_posture",
        "memory_density_target",
        "max_items_per_turn",
    ):
        value = memory_policy.get(key)
        if value not in (None, "", [], {}):
            derived[key] = value
    return derived


def _overlay_known_policy_fields(
    base_policy: dict[str, Any],
    overrides: dict[str, Any],
    field_names: tuple[str, ...],
) -> dict[str, Any]:
    merged = dict(base_policy)
    for field_name in field_names:
        if field_name not in overrides:
            continue
        value = overrides.get(field_name)
        if value is None:
            continue
        merged[field_name] = value
    return merged


def _trimmed_text(value: Any) -> str:
    return str(value or "").strip()


def _append_toml_value(lines: list[str], key: str, value: Any) -> None:
    if value is None:
        return
    if isinstance(value, list):
        normalized = [str(item).strip() for item in value if str(item).strip()]
        if normalized:
            lines.append(f"{key} = {_toml_list(normalized)}")
        return
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            lines.append(f"{key} = {_toml_scalar(stripped)}")
        return
    lines.append(f"{key} = {_toml_scalar(value)}")


def _compose_agent_prompt(documents: dict[str, Any]) -> str:
    return compose_agent_prompt(documents)


def _resolve_knowledge_pack_metadata(
    agent_id: str,
    knowledge_section: dict[str, Any],
) -> dict[str, Any]:
    section_data = _safe_json_object(knowledge_section)
    pack_metadata = dict(_safe_json_object(section_data.get("pack_metadata")))
    resolved: dict[str, Any] = {
        "pack_id": str(pack_metadata.get("pack_id") or f"{_slug(agent_id)}_control_plane"),
        "updated_at": str(pack_metadata.get("updated_at") or now_iso()[:10]),
    }
    for field in _KNOWLEDGE_PACK_METADATA_FIELDS:
        if field in {"pack_id", "updated_at"}:
            continue
        value = pack_metadata.get(field)
        if value in (None, "", []):
            continue
        resolved[field] = value
    return resolved


def _render_knowledge_pack(agent_id: str, assets: list[dict[str, Any]], knowledge_section: dict[str, Any]) -> str:
    metadata = _resolve_knowledge_pack_metadata(agent_id, knowledge_section)
    header = [
        f"pack_id = {_toml_scalar(str(metadata['pack_id']))}",
        f'agent_ids = ["{agent_id}"]',
        f"updated_at = {_toml_scalar(str(metadata['updated_at']))}",
    ]
    for field in _KNOWLEDGE_PACK_METADATA_FIELDS:
        if field in {"pack_id", "updated_at"}:
            continue
        _append_toml_value(header, field, metadata.get(field))
    header.append("")
    blocks: list[str] = []
    for asset in assets:
        body = _safe_json_object(asset.get("body"))
        asset_kind = str(asset.get("kind") or body.get("kind") or "entry").strip().lower()
        if asset_kind in _KNOWLEDGE_PACK_CONTROL_KINDS:
            continue
        asset_key = str(asset.get("asset_key") or f"asset-{asset['id']}")
        title = _trimmed_text(asset.get("title") or body.get("title")) or asset_key
        blocks.extend(
            [
                "[[entries]]",
                f'id = "{asset_key}"',
                f"title = {json.dumps(title, ensure_ascii=False)}",
                f"scope = {json.dumps(str(body.get('scope') or 'operational_policy'), ensure_ascii=False)}",
                f"criticality = {json.dumps(str(body.get('criticality') or 'medium'), ensure_ascii=False)}",
            ]
        )
        for field in _KNOWLEDGE_ENTRY_METADATA_FIELDS:
            _append_toml_value(blocks, field, body.get(field))
        tags = body.get("tags")
        if isinstance(tags, list) and tags:
            blocks.append(f"tags = {_toml_list([str(item) for item in tags])}")
        content = str(asset.get("content_text") or body.get("content") or "").strip()
        blocks.append('content = """')
        blocks.append(content)
        blocks.append('"""')
        blocks.append("")
    return "\n".join(header + blocks).strip() + "\n"


def _parse_dashboard_appearance() -> dict[str, dict[str, str]]:
    if not DASHBOARD_AGENT_CONSTANTS_PATH.exists():
        return {}
    content = DASHBOARD_AGENT_CONSTANTS_PATH.read_text(encoding="utf-8")
    matches = re.findall(
        r'\{ id: "([^"]+)", label: "([^"]+)", color: "([^"]+)", colorRgb: "([^"]+)" \}',
        content,
    )
    appearance: dict[str, dict[str, str]] = {}
    for agent_id, label, color, color_rgb in matches:
        appearance[_normalize_agent_id(agent_id)] = {
            "label": label,
            "color": color,
            "color_rgb": color_rgb,
        }
    return appearance


class ControlPlaneManager:
    """CRUD, publishing, seeding, and runtime materialization for agent config."""

    def __init__(self) -> None:
        init_control_plane_db()
        self._seeding_legacy_state = False
        self._elevenlabs_voice_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._elevenlabs_subscription_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._ollama_model_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._global_sections_cache: tuple[float, dict[str, dict[str, Any]]] | None = None
        self._provider_login_processes: dict[str, Any] = {}
        self._claude_oauth_verifiers: dict[str, str] = {}  # session_id → PKCE code_verifier
        self._provider_download_threads: dict[str, threading.Thread] = {}
        self._provider_download_cancel_events: dict[str, threading.Event] = {}

    def _auto_seed_enabled(self) -> bool:
        """Skip auto-seeding for tests that instantiate via ``object.__new__``."""
        return hasattr(self, "_seeding_legacy_state")

    def ensure_seeded(self) -> None:
        if not self._auto_seed_enabled():
            return
        if self._seeding_legacy_state:
            return
        if CONTROL_PLANE_AUTO_IMPORT:
            self.import_legacy_state()
        self._repair_legacy_default_agent_id()
        self._reconcile_global_secret_classification()
        self._cleanup_provider_login_sessions()
        self._cleanup_provider_download_jobs()

    def _repair_legacy_default_agent_id(self) -> None:
        """Normalize legacy default-agent rows from `koda` to canonical `KODA`."""
        legacy_id = "koda"
        canonical_id = _normalize_agent_id(legacy_id)
        legacy_row = fetch_one("SELECT id FROM cp_agent_definitions WHERE id = ?", (legacy_id,))
        if legacy_row is None:
            return
        if fetch_one("SELECT id FROM cp_agent_definitions WHERE id = ?", (canonical_id,)) is None:
            execute(
                "UPDATE cp_agent_definitions SET id = ?, updated_at = ? WHERE id = ?",
                (canonical_id, now_iso(), legacy_id),
            )
        else:
            execute("DELETE FROM cp_agent_definitions WHERE id = ?", (legacy_id,))
        for table in (
            "cp_agent_assignments",
            "cp_agent_config_versions",
            "cp_agent_connections",
            "cp_agent_documents",
            "cp_agent_sections",
            "cp_apply_operations",
            "cp_bot_gateway_tokens",
            "cp_connection_discovery_runs",
            "cp_knowledge_assets",
            "cp_mcp_agent_connections",
            "cp_mcp_capability_policies",
            "cp_mcp_capability_snapshots",
            "cp_mcp_discovered_prompts",
            "cp_mcp_discovered_resources",
            "cp_mcp_discovered_tools",
            "cp_mcp_oauth_sessions",
            "cp_mcp_oauth_tokens",
            "cp_mcp_tool_policies",
            "cp_mcp_user_servers",
            "cp_policy_spend_ledger",
            "cp_secret_values",
            "cp_skill_assets",
            "cp_telegram_offsets",
            "cp_telegram_pending_updates",
            "cp_template_assets",
        ):
            execute(f"UPDATE {table} SET agent_id = ? WHERE agent_id = ?", (canonical_id, legacy_id))

    def _require_agent_row(self, agent_id: str) -> tuple[str, Any]:
        normalized = _normalize_agent_id(agent_id)
        row = fetch_one("SELECT * FROM cp_agent_definitions WHERE id = ?", (normalized,))
        if row is None:
            raise KeyError(normalized)
        return normalized, row

    def _workspace_rows(self) -> list[Any]:
        return fetch_all("SELECT * FROM cp_workspaces ORDER BY lower(name) ASC, id ASC")

    def _workspace_row(self, workspace_id: str) -> Any:
        normalized = _normalize_optional_org_id(workspace_id)
        if not normalized:
            raise ValueError("workspace_id is required")
        row = fetch_one("SELECT * FROM cp_workspaces WHERE id = ?", (normalized,))
        if row is None:
            raise KeyError(normalized)
        return row

    def _squad_rows(self, workspace_id: str | None = None) -> list[Any]:
        if workspace_id:
            normalized = _normalize_optional_org_id(workspace_id)
            return fetch_all(
                """
                SELECT * FROM cp_workspace_squads
                WHERE workspace_id = ?
                ORDER BY lower(name) ASC, id ASC
                """,
                (normalized,),
            )
        return fetch_all("SELECT * FROM cp_workspace_squads ORDER BY lower(name) ASC, id ASC")

    def _squad_row(self, squad_id: str) -> Any:
        normalized = _normalize_optional_org_id(squad_id)
        if not normalized:
            raise ValueError("squad_id is required")
        row = fetch_one("SELECT * FROM cp_workspace_squads WHERE id = ?", (normalized,))
        if row is None:
            raise KeyError(normalized)
        return row

    def _next_workspace_entity_id(self, table: str, base_value: str) -> str:
        base = _slug(base_value)
        candidate = base
        suffix = 2
        while fetch_one(f"SELECT id FROM {table} WHERE id = ?", (candidate,)) is not None:
            candidate = f"{base}_{suffix}"
            suffix += 1
        return candidate

    def _serialize_workspace_row(
        self,
        row: Any,
        *,
        agent_count: int = 0,
        unassigned_agent_count: int = 0,
        squads: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        documents = resolve_scope_documents(
            "workspace",
            _row_json(row, "spec_json"),
            _row_json(row, "documents_json"),
        )
        root_path = _row_text(row, "root_path").strip() or None
        root_exists = bool(root_path and Path(root_path).is_dir())
        scan_payload = _row_json(row, "config_sources_json") if _row_has_column(row, "config_sources_json") else {}
        root_kind = _row_text(row, "root_kind", "local_path" if root_path else "").strip()
        scan_status = _row_text(row, "scan_status", "not_scanned").strip() or "not_scanned"
        if root_path is None:
            root_trust_state = "logical_only"
        elif root_exists:
            root_trust_state = "trusted"
        else:
            root_trust_state = "missing"
        return {
            "id": str(row["id"]),
            "name": str(row["name"]),
            "description": str(row["description"] or ""),
            "spec": {},
            "documents": documents,
            "root_path": root_path,
            "root_exists": root_exists,
            "root_kind": root_kind or ("local_path" if root_path else ""),
            "root_trust_state": root_trust_state,
            "scan_status": scan_status,
            "last_scanned_at": _row_text(row, "last_scanned_at").strip() or None,
            "scan_hash": _row_text(row, "scan_hash"),
            "detected_sources": _workspace_scan_sources(scan_payload),
            "scan_summary": _workspace_scan_summary(scan_payload),
            "runtime_defaults": {
                "source_root_path": root_path,
                "task_execution_mode": "runtime_worktree_or_copy" if root_path else "session_default",
                "isolation_mode": "worktree_or_copy",
            },
            "import_history": _row_json_list(row, "import_history_json")
            if _row_has_column(row, "import_history_json")
            else [],
            "agent_count": agent_count,
            "squads": squads or [],
            "virtual_buckets": {
                "no_squad": {
                    "id": None,
                    "label": "Sem squad",
                    "agent_count": unassigned_agent_count,
                }
            },
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }

    def _serialize_squad_row(self, row: Any, *, agent_count: int = 0) -> dict[str, Any]:
        documents = resolve_scope_documents(
            "squad",
            _row_json(row, "spec_json"),
            _row_json(row, "documents_json"),
        )
        return {
            "id": str(row["id"]),
            "workspace_id": str(row["workspace_id"]),
            "name": str(row["name"]),
            "description": str(row["description"] or ""),
            "spec": {},
            "documents": documents,
            "agent_count": agent_count,
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }

    def _workspace_map(self) -> dict[str, Any]:
        return {str(row["id"]): row for row in self._workspace_rows()}

    def _squad_map(self) -> dict[str, Any]:
        return {str(row["id"]): row for row in self._squad_rows()}

    def _serialize_agent_organization(
        self,
        workspace_id: str | None,
        squad_id: str | None,
        *,
        workspace_map: dict[str, Any] | None = None,
        squad_map: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_workspace_id = _normalize_optional_org_id(workspace_id)
        normalized_squad_id = _normalize_optional_org_id(squad_id)
        workspace_row = (workspace_map or self._workspace_map()).get(normalized_workspace_id or "")
        squad_row = (squad_map or self._squad_map()).get(normalized_squad_id or "")
        if workspace_row is None:
            normalized_workspace_id = None
            normalized_squad_id = None
            squad_row = None
        elif squad_row is None or str(squad_row["workspace_id"]) != normalized_workspace_id:
            normalized_squad_id = None
            squad_row = None
        return {
            "workspace_id": normalized_workspace_id,
            "workspace_name": str(workspace_row["name"]) if workspace_row is not None else None,
            "squad_id": normalized_squad_id,
            "squad_name": str(squad_row["name"]) if squad_row is not None else None,
        }

    def _resolve_agent_organization(
        self,
        payload: dict[str, Any] | None,
        *,
        current_row: Any | None = None,
    ) -> tuple[str | None, str | None]:
        current_workspace_id = (
            _normalize_optional_org_id(current_row["workspace_id"])
            if current_row is not None and _row_has_column(current_row, "workspace_id")
            else None
        )
        current_squad_id = (
            _normalize_optional_org_id(current_row["squad_id"])
            if current_row is not None and _row_has_column(current_row, "squad_id")
            else None
        )
        if payload is None:
            return current_workspace_id, current_squad_id

        workspace_explicit = "workspace_id" in payload
        squad_explicit = "squad_id" in payload
        workspace_id = (
            _normalize_optional_org_id(payload.get("workspace_id")) if workspace_explicit else current_workspace_id
        )
        squad_id = _normalize_optional_org_id(payload.get("squad_id")) if squad_explicit else current_squad_id

        if workspace_explicit and workspace_id is None:
            squad_id = None

        if workspace_id is None and squad_id is not None:
            raise ValueError("squad_id requires a workspace_id")

        workspace_row = None
        if workspace_id is not None:
            workspace_row = fetch_one("SELECT id FROM cp_workspaces WHERE id = ?", (workspace_id,))
            if workspace_row is None:
                raise ValueError("workspace_id not found")

        if squad_id is not None:
            squad_row = fetch_one("SELECT * FROM cp_workspace_squads WHERE id = ?", (squad_id,))
            if squad_row is None:
                raise ValueError("squad_id not found")
            squad_workspace_id = _normalize_optional_org_id(squad_row["workspace_id"])
            if squad_workspace_id != workspace_id:
                raise ValueError("squad_id must belong to the selected workspace")
        elif workspace_id is not None and workspace_explicit and not squad_explicit and current_squad_id is not None:
            current_squad_row = fetch_one("SELECT * FROM cp_workspace_squads WHERE id = ?", (current_squad_id,))
            if current_squad_row is not None:
                current_squad_workspace_id = _normalize_optional_org_id(current_squad_row["workspace_id"])
                if current_squad_workspace_id != workspace_id:
                    squad_id = None

        return workspace_id, squad_id

    def list_workspaces(self) -> dict[str, Any]:
        self.ensure_seeded()
        workspace_rows = self._workspace_rows()
        squad_rows = self._squad_rows()
        workspace_map = {str(row["id"]): row for row in workspace_rows}
        squad_map = {str(row["id"]): row for row in squad_rows}
        workspace_counts: dict[str | None, int] = {}
        squad_counts: dict[str, int] = {}
        unassigned_squad_counts: dict[str, int] = {}
        total_agent_count = 0

        for row in fetch_all(
            """
            SELECT workspace_id, squad_id, COUNT(*) AS agent_count
            FROM cp_agent_definitions
            GROUP BY workspace_id, squad_id
            """
        ):
            workspace_id = _normalize_optional_org_id(row["workspace_id"])
            squad_id = _normalize_optional_org_id(row["squad_id"])
            workspace_row = workspace_map.get(workspace_id or "")
            squad_row = squad_map.get(squad_id or "")
            if workspace_row is None:
                workspace_id = None
                squad_id = None
            elif squad_row is None or str(squad_row["workspace_id"]) != workspace_id:
                squad_id = None
            agent_count = int(row["agent_count"] or 0)
            total_agent_count += agent_count
            workspace_counts[workspace_id] = workspace_counts.get(workspace_id, 0) + agent_count
            if workspace_id and squad_id:
                squad_counts[squad_id] = squad_counts.get(squad_id, 0) + agent_count
            elif workspace_id and not squad_id:
                unassigned_squad_counts[workspace_id] = unassigned_squad_counts.get(workspace_id, 0) + agent_count

        squads_by_workspace: dict[str, list[dict[str, Any]]] = {}
        for squad_row in squad_rows:
            workspace_id = str(squad_row["workspace_id"])
            squads_by_workspace.setdefault(workspace_id, []).append(
                self._serialize_squad_row(
                    squad_row,
                    agent_count=squad_counts.get(str(squad_row["id"]), 0),
                )
            )

        items = [
            self._serialize_workspace_row(
                workspace_row,
                agent_count=workspace_counts.get(str(workspace_row["id"]), 0),
                unassigned_agent_count=unassigned_squad_counts.get(str(workspace_row["id"]), 0),
                squads=squads_by_workspace.get(str(workspace_row["id"]), []),
            )
            for workspace_row in workspace_rows
        ]

        return {
            "items": items,
            "virtual_buckets": {
                "no_workspace": {
                    "id": None,
                    "label": "Sem workspace",
                    "agent_count": workspace_counts.get(None, 0),
                }
            },
            "total_agent_count": total_agent_count,
        }

    def create_workspace(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_seeded()
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("workspace name is required")
        workspace_id = self._next_workspace_entity_id("cp_workspaces", str(payload.get("id") or name))
        now = now_iso()
        root_path = None
        root_kind = ""
        scan_status = "not_scanned"
        if "root_path" in payload and str(payload.get("root_path") or "").strip():
            root_path = str(validate_workspace_root(str(payload.get("root_path") or "")))
            root_kind = "local_path"
            scan_status = "stale"
        execute(
            """
            INSERT INTO cp_workspaces (
                id, name, description, root_path, root_kind, scan_status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workspace_id,
                name,
                str(payload.get("description") or "").strip(),
                root_path,
                root_kind,
                scan_status,
                now,
                now,
            ),
        )
        if root_path and bool(payload.get("scan_on_save")):
            self.rescan_workspace(workspace_id, {})
        return next(item for item in self.list_workspaces()["items"] if item["id"] == workspace_id)

    def update_workspace(self, workspace_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_seeded()
        row = self._workspace_row(workspace_id)
        name = str(payload.get("name") or row["name"]).strip()
        if not name:
            raise ValueError("workspace name is required")
        current_root = _row_text(row, "root_path").strip() or None
        root_path = current_root
        root_kind = _row_text(row, "root_kind")
        scan_status = _row_text(row, "scan_status", "not_scanned") or "not_scanned"
        root_changed = False
        if "root_path" in payload:
            raw_root = str(payload.get("root_path") or "").strip()
            root_path = str(validate_workspace_root(raw_root)) if raw_root else None
            root_kind = "local_path" if root_path else ""
            scan_status = "stale" if root_path else "not_scanned"
            root_changed = root_path != current_root
        execute(
            """
            UPDATE cp_workspaces
            SET name = ?, description = ?, root_path = ?, root_kind = ?, scan_status = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                name,
                str(payload.get("description") if "description" in payload else row["description"] or "").strip(),
                root_path,
                root_kind,
                scan_status,
                now_iso(),
                str(row["id"]),
            ),
        )
        if root_changed and root_path and bool(payload.get("scan_on_save")):
            self.rescan_workspace(str(row["id"]), {})
        return next(item for item in self.list_workspaces()["items"] if item["id"] == str(row["id"]))

    def list_workspace_directory_roots(self) -> dict[str, Any]:
        return directory_roots_payload()

    def list_workspace_directory(self, payload: dict[str, Any]) -> dict[str, Any]:
        path = str(payload.get("path") or "").strip()
        if not path:
            raise ValueError("path is required")
        return list_directory_payload(path)

    def scan_workspace_directory(self, payload: dict[str, Any]) -> dict[str, Any]:
        path = str(payload.get("path") or "").strip()
        if not path:
            raise ValueError("path is required")
        max_depth = int(payload.get("maxDepth") or payload.get("max_depth") or 8)
        return scan_workspace_directory(path, max_depth=max_depth).to_dict()

    def import_workspace_from_directory(self, payload: dict[str, Any]) -> dict[str, Any]:
        path = str(payload.get("path") or "").strip()
        if not path:
            raise ValueError("path is required")
        scan_payload = self.scan_workspace_directory(payload)
        name = str(payload.get("name") or Path(scan_payload["root_path"]).name or "Imported workspace").strip()
        workspace = self.create_workspace(
            {
                "name": name,
                "description": str(payload.get("description") or "").strip(),
                "root_path": scan_payload["root_path"],
            }
        )
        workspace_id = str(workspace["id"])
        self._persist_workspace_scan(workspace_id, scan_payload, status="completed")
        selected = self._selected_source_ids(payload)
        import_result: dict[str, Any] = {"applied": [], "skipped": [], "conflicts": []}
        if selected:
            import_result = self.import_workspace_config(workspace_id, {"selectedSourceIds": selected})
        refreshed = next(item for item in self.list_workspaces()["items"] if item["id"] == workspace_id)
        return {"workspace": refreshed, "scan": scan_payload, "import_result": import_result}

    def rescan_workspace(self, workspace_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        row = self._workspace_row(workspace_id)
        root_path = _row_text(row, "root_path").strip()
        if not root_path:
            raise ValueError("workspace has no root_path")
        try:
            scan_payload = self.scan_workspace_directory(
                {
                    "path": root_path,
                    "maxDepth": payload.get("maxDepth") or payload.get("max_depth") or 8,
                }
            )
        except Exception as exc:
            self._persist_workspace_scan_error(str(row["id"]), root_path, exc)
            raise
        self._persist_workspace_scan(str(row["id"]), scan_payload, status="completed")
        return {
            "workspace": next(item for item in self.list_workspaces()["items"] if item["id"] == str(row["id"])),
            "scan": scan_payload,
        }

    def import_workspace_config(self, workspace_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        row = self._workspace_row(workspace_id)
        if bool(payload.get("rescan")):
            scan_payload = self.rescan_workspace(workspace_id, payload)["scan"]
            row = self._workspace_row(workspace_id)
        else:
            scan_payload = _row_json(row, "config_sources_json")
        if not scan_payload:
            root_path = _row_text(row, "root_path").strip()
            if not root_path:
                raise ValueError("workspace has no scan metadata and no root_path")
            scan_payload = self.rescan_workspace(workspace_id, payload)["scan"]
            row = self._workspace_row(workspace_id)

        selected = self._selected_source_ids(payload)
        if not selected:
            return {"applied": [], "skipped": [], "conflicts": [], "message": "no selected sources"}

        sources = [workspace_source_from_dict(item) for item in _workspace_scan_sources(scan_payload)]
        selected_sources = [source for source in sources if source.source_id in selected]
        selected_source_ids = {source.source_id for source in selected_sources}
        missing = sorted(set(selected) - selected_source_ids)

        result: dict[str, Any] = {"applied": [], "skipped": [], "conflicts": []}
        root_path = _row_text(row, "root_path").strip() or str(scan_payload.get("root_path") or "")
        prompt_sources = [
            source
            for source in selected_sources
            if source.import_action == "append_workspace_prompt" and source.risk == "low"
        ]
        if prompt_sources:
            self._apply_workspace_prompt_import(str(row["id"]), root_path, scan_payload, prompt_sources)
            result["applied"].append({"action": "workspace_prompt", "count": len(prompt_sources)})

        for source in selected_sources:
            if source in prompt_sources:
                continue
            if source.import_action == "create_agent_draft" and source.risk in {"review", "low"}:
                created = self._apply_workspace_agent_import(str(row["id"]), root_path, source)
                result["applied" if created.get("created") else "conflicts"].append(created)
            elif source.import_action == "mcp_review":
                mcp_candidates = self._apply_workspace_mcp_candidates(str(row["id"]), source)
                result["applied"].extend(mcp_candidates)
                if not mcp_candidates:
                    result["skipped"].append({"source_id": source.source_id, "reason": "no safe MCP server shape"})
            else:
                result["skipped"].append(
                    {
                        "source_id": source.source_id,
                        "relative_path": source.relative_path,
                        "reason": "review_required_or_blocked",
                    }
                )
        for source_id in missing:
            result["skipped"].append({"source_id": source_id, "reason": "source_not_found"})
        self._append_workspace_import_history(str(row["id"]), scan_payload, result, selected)
        record_workspace_import_metrics(result)
        return result

    def get_workspace_runtime_root_for_agent(self, agent_id: str | None) -> str | None:
        normalized = _normalize_agent_id(agent_id or "") if str(agent_id or "").strip() else None
        if not normalized:
            return None
        row = fetch_one(
            """
            SELECT w.root_path
            FROM cp_agent_definitions a
            JOIN cp_workspaces w ON w.id = a.workspace_id
            WHERE a.id = ?
            """,
            (normalized,),
        )
        root_path = str((row or {}).get("root_path") or "").strip()
        if not root_path:
            return None
        try:
            return str(validate_workspace_root(root_path))
        except ValueError:
            return None

    def _selected_source_ids(self, payload: dict[str, Any]) -> list[str]:
        raw = payload.get("selectedSourceIds", payload.get("selected_source_ids", []))
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise ValueError("selectedSourceIds must be a list")
        return [str(item) for item in raw if str(item or "").strip()]

    def _persist_workspace_scan(self, workspace_id: str, scan_payload: dict[str, Any], *, status: str) -> None:
        execute(
            """
            UPDATE cp_workspaces
            SET root_path = ?, root_kind = ?, scan_status = ?, last_scanned_at = ?,
                scan_hash = ?, config_sources_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                str(scan_payload.get("root_path") or ""),
                str(scan_payload.get("root_kind") or "local_path"),
                status,
                now_iso(),
                str(scan_payload.get("scan_hash") or ""),
                json_dump(scan_payload),
                now_iso(),
                workspace_id,
            ),
        )

    def _persist_workspace_scan_error(self, workspace_id: str, root_path: str, exc: BaseException) -> None:
        history = _row_json_list(self._workspace_row(workspace_id), "import_history_json")
        history.append(
            {
                "schema_version": "workspace_import_history.v1",
                "event": "scan_error",
                "recorded_at": now_iso(),
                "root_path": root_path,
                "error": _redact_workspace_import_error(exc),
            }
        )
        execute(
            """
            UPDATE cp_workspaces
            SET scan_status = ?, import_history_json = ?, updated_at = ?
            WHERE id = ?
            """,
            ("error", json_dump(history[-25:]), now_iso(), workspace_id),
        )

    def _append_workspace_import_history(
        self,
        workspace_id: str,
        scan_payload: dict[str, Any],
        result: dict[str, Any],
        selected_source_ids: list[str],
    ) -> None:
        row = self._workspace_row(workspace_id)
        history = _row_json_list(row, "import_history_json")
        history.append(
            {
                "schema_version": "workspace_import_history.v1",
                "imported_at": now_iso(),
                "scan_hash": scan_payload.get("scan_hash"),
                "selected_source_ids": selected_source_ids,
                "result": result,
            }
        )
        execute(
            "UPDATE cp_workspaces SET import_history_json = ?, updated_at = ? WHERE id = ?",
            (json_dump(history[-25:]), now_iso(), workspace_id),
        )

    def _apply_workspace_prompt_import(
        self,
        workspace_id: str,
        root_path: str,
        scan_payload: dict[str, Any],
        sources: list[Any],
    ) -> None:
        row = self._workspace_row(workspace_id)
        documents = resolve_scope_documents(
            "workspace",
            _row_json(row, "spec_json"),
            _row_json(row, "documents_json"),
        )
        current = str(documents.get("system_prompt_md") or "")
        body_parts = [
            (
                f"{_WORKSPACE_IMPORT_START} schema={WORKSPACE_SCAN_SCHEMA_VERSION} "
                f"scan_hash={scan_payload.get('scan_hash', '')} -->"
            ),
            "",
            "## Imported Workspace Directory Context",
            "",
        ]
        for source in sources:
            content = read_importable_source_content(root_path, source)
            if not content:
                continue
            body_parts.extend(
                [
                    f"### {source.tool}: {source.relative_path}",
                    "",
                    f"Source ID: `{source.source_id}`",
                    "",
                    content,
                    "",
                ]
            )
        body_parts.append(_WORKSPACE_IMPORT_END)
        block = "\n".join(body_parts).strip()
        cleaned = _WORKSPACE_IMPORT_BLOCK_RE.sub("\n", current).strip()
        documents["system_prompt_md"] = f"{cleaned}\n\n{block}".strip() if cleaned else block
        execute(
            """
            UPDATE cp_workspaces
            SET spec_json = ?, documents_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (json_dump({}), json_dump(documents), now_iso(), workspace_id),
        )

    def _apply_workspace_agent_import(self, workspace_id: str, root_path: str, source: Any) -> dict[str, Any]:
        base_name = source.name or Path(source.relative_path).stem
        agent_id = _normalize_agent_id(f"IMPORTED_{workspace_id}_{base_name}")[:64].strip("_")
        if fetch_one("SELECT id FROM cp_agent_definitions WHERE id = ?", (agent_id,)) is not None:
            return {
                "created": False,
                "action": "agent_draft",
                "agent_id": agent_id,
                "source_id": source.source_id,
                "reason": "agent_exists",
            }
        agent = self.create_agent(
            {
                "id": agent_id,
                "display_name": base_name,
                "status": "paused",
                "organization": {"workspace_id": workspace_id, "squad_id": None},
                "metadata": {
                    "imported_from": {
                        "schema_version": WORKSPACE_SCAN_SCHEMA_VERSION,
                        "source_id": source.source_id,
                        "tool": source.tool,
                        "relative_path": source.relative_path,
                        "risk": source.risk,
                    }
                },
            }
        )
        prompt = read_importable_source_content(root_path, source)
        if prompt:
            self.upsert_document(agent_id, "system_prompt_md", {"content_md": prompt})
        return {
            "created": True,
            "action": "agent_draft",
            "agent_id": agent.get("id", agent_id),
            "source_id": source.source_id,
        }

    def _apply_workspace_mcp_candidates(self, workspace_id: str, source: Any) -> list[dict[str, Any]]:
        created: list[dict[str, Any]] = []
        servers = source.metadata.get("servers") if isinstance(source.metadata, dict) else []
        if not isinstance(servers, list):
            return created
        for server in servers:
            if not isinstance(server, dict):
                continue
            name = str(server.get("name") or "").strip()
            if not name:
                continue
            server_key = _slug(f"imported_{workspace_id}_{name}")
            command = [str(server.get("command") or ""), *[str(item) for item in server.get("args") or []]]
            command = [item for item in command if item]
            payload = {
                "display_name": name,
                "description": f"Imported disabled MCP candidate from {source.relative_path}",
                "transport_type": "stdio" if command else "sse" if server.get("url") else "stdio",
                "transport_kind": "remote" if server.get("url") else "local",
                "command": command,
                "remote_url": str(server.get("url") or "") or None,
                "env_schema": [
                    {"key": str(key), "label": str(key), "required": False} for key in server.get("env_keys") or []
                ],
                "enabled": False,
                "default_policy": "always_ask",
                "metadata": {
                    "imported_from": {
                        "schema_version": WORKSPACE_SCAN_SCHEMA_VERSION,
                        "workspace_id": workspace_id,
                        "source_id": source.source_id,
                        "relative_path": source.relative_path,
                    },
                    "review_required": True,
                },
            }
            entry = self.upsert_mcp_catalog_entry(server_key, payload)
            created.append(
                {
                    "action": "mcp_candidate",
                    "server_key": entry["server_key"],
                    "source_id": source.source_id,
                }
            )
        return created

    def delete_workspace(self, workspace_id: str) -> bool:
        self.ensure_seeded()
        row = self._workspace_row(workspace_id)
        normalized = str(row["id"])
        timestamp = now_iso()

        def _delete(conn: Any) -> None:
            conn.execute(
                """
                UPDATE cp_agent_definitions
                SET workspace_id = NULL, squad_id = NULL, updated_at = ?
                WHERE workspace_id = ?
                """,
                (timestamp, normalized),
            )
            conn.execute("DELETE FROM cp_workspace_squads WHERE workspace_id = ?", (normalized,))
            conn.execute("DELETE FROM cp_workspaces WHERE id = ?", (normalized,))

        with_connection(_delete)
        return True

    def create_workspace_squad(self, workspace_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_seeded()
        workspace_row = self._workspace_row(workspace_id)
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("squad name is required")
        squad_id = self._next_workspace_entity_id(
            "cp_workspace_squads",
            str(payload.get("id") or f"{workspace_row['id']}_{name}"),
        )
        now = now_iso()
        execute(
            """
            INSERT INTO cp_workspace_squads (id, workspace_id, name, description, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                squad_id,
                str(workspace_row["id"]),
                name,
                str(payload.get("description") or "").strip(),
                now,
                now,
            ),
        )
        workspace = next(item for item in self.list_workspaces()["items"] if item["id"] == str(workspace_row["id"]))
        return next(item for item in workspace["squads"] if item["id"] == squad_id)

    def update_workspace_squad(self, workspace_id: str, squad_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_seeded()
        workspace_row = self._workspace_row(workspace_id)
        squad_row = self._squad_row(squad_id)
        if str(squad_row["workspace_id"]) != str(workspace_row["id"]):
            raise ValueError("squad_id must belong to the selected workspace")
        name = str(payload.get("name") or squad_row["name"]).strip()
        if not name:
            raise ValueError("squad name is required")
        execute(
            """
            UPDATE cp_workspace_squads
            SET name = ?, description = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                name,
                str(payload.get("description") if "description" in payload else squad_row["description"] or "").strip(),
                now_iso(),
                str(squad_row["id"]),
            ),
        )
        workspace = next(item for item in self.list_workspaces()["items"] if item["id"] == str(workspace_row["id"]))
        return next(item for item in workspace["squads"] if item["id"] == str(squad_row["id"]))

    def delete_workspace_squad(self, workspace_id: str, squad_id: str) -> bool:
        self.ensure_seeded()
        workspace_row = self._workspace_row(workspace_id)
        squad_row = self._squad_row(squad_id)
        if str(squad_row["workspace_id"]) != str(workspace_row["id"]):
            raise ValueError("squad_id must belong to the selected workspace")
        normalized_squad_id = str(squad_row["id"])
        timestamp = now_iso()

        def _delete(conn: Any) -> None:
            conn.execute(
                "UPDATE cp_agent_definitions SET squad_id = NULL, updated_at = ? WHERE squad_id = ?",
                (timestamp, normalized_squad_id),
            )
            conn.execute("DELETE FROM cp_workspace_squads WHERE id = ?", (normalized_squad_id,))

        with_connection(_delete)
        return True

    # ------------------------------------------------------------------
    # Workspace / Squad hierarchical spec CRUD
    # ------------------------------------------------------------------

    def get_workspace_spec(self, workspace_id: str) -> dict[str, Any]:
        """Return the workspace-level spec and documents."""
        row = self._workspace_row(workspace_id)
        documents = resolve_scope_documents(
            "workspace",
            _row_json(row, "spec_json"),
            _row_json(row, "documents_json"),
        )
        return {"spec": {}, "documents": documents}

    def update_workspace_spec(self, workspace_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Store one effective workspace-level system prompt."""
        self.ensure_seeded()
        row = self._workspace_row(workspace_id)
        normalized_docs = resolve_scope_documents(
            "workspace",
            _safe_json_object(payload.get("spec")),
            _safe_json_object(payload.get("documents")),
        )
        execute(
            """
            UPDATE cp_workspaces
            SET spec_json = ?, documents_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (json_dump({}), json_dump(normalized_docs), now_iso(), str(row["id"])),
        )
        return {"spec": {}, "documents": normalized_docs}

    def get_squad_spec(self, workspace_id: str, squad_id: str) -> dict[str, Any]:
        """Return the squad-level spec and documents."""
        workspace_row = self._workspace_row(workspace_id)
        squad_row = self._squad_row(squad_id)
        if str(squad_row["workspace_id"]) != str(workspace_row["id"]):
            raise ValueError("squad_id must belong to the selected workspace")
        documents = resolve_scope_documents(
            "squad",
            _row_json(squad_row, "spec_json"),
            _row_json(squad_row, "documents_json"),
        )
        return {"spec": {}, "documents": documents}

    def update_squad_spec(self, workspace_id: str, squad_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Store one effective squad-level system prompt."""
        self.ensure_seeded()
        workspace_row = self._workspace_row(workspace_id)
        squad_row = self._squad_row(squad_id)
        if str(squad_row["workspace_id"]) != str(workspace_row["id"]):
            raise ValueError("squad_id must belong to the selected workspace")
        normalized_docs = resolve_scope_documents(
            "squad",
            _safe_json_object(payload.get("spec")),
            _safe_json_object(payload.get("documents")),
        )
        execute(
            """
            UPDATE cp_workspace_squads
            SET spec_json = ?, documents_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (json_dump({}), json_dump(normalized_docs), now_iso(), str(squad_row["id"])),
        )
        return {"spec": {}, "documents": normalized_docs}

    def _resolve_hierarchical_spec(
        self,
        agent_spec: dict[str, Any],
        agent_row: Any,
    ) -> dict[str, Any]:
        """Apply workspace -> squad -> agent system-prompt inheritance to an agent spec."""
        workspace_id = _normalize_optional_org_id(agent_row.get("workspace_id") if hasattr(agent_row, "get") else None)
        squad_id = _normalize_optional_org_id(agent_row.get("squad_id") if hasattr(agent_row, "get") else None)

        workspace_docs: dict[str, str] | None = None
        squad_docs: dict[str, str] | None = None

        if workspace_id:
            try:
                ws_row = self._workspace_row(workspace_id)
                workspace_docs = resolve_scope_documents(
                    "workspace",
                    _row_json(ws_row, "spec_json"),
                    _row_json(ws_row, "documents_json"),
                )
            except (KeyError, ValueError):
                pass

        if squad_id:
            try:
                sq_row = self._squad_row(squad_id)
                if str(sq_row["workspace_id"]) == (workspace_id or ""):
                    squad_docs = resolve_scope_documents(
                        "squad",
                        _row_json(sq_row, "spec_json"),
                        _row_json(sq_row, "documents_json"),
                    )
            except (KeyError, ValueError):
                pass

        merged_spec = dict(agent_spec)

        # Merge documents from all levels
        agent_docs = _safe_json_object(agent_spec.get("documents"))
        merged_docs = merge_hierarchical_documents(workspace_docs, squad_docs, agent_docs)
        if merged_docs:
            merged_spec["documents"] = merged_docs

        return merged_spec

    def _resolve_named_asset_row(self, table: str, agent_id: str, asset_id: int) -> tuple[str, Any]:
        normalized, _ = self._require_agent_row(agent_id)
        row = fetch_one(
            f"""
            SELECT * FROM {table}
            WHERE id = ? AND scope_id IN ('global', ?)
            """,
            (asset_id, normalized),
        )
        if row is None:
            raise KeyError(f"{table}:{asset_id}")
        return normalized, row

    def _resolve_knowledge_asset_row(self, agent_id: str, asset_id: int) -> tuple[str, Any]:
        normalized, _ = self._require_agent_row(agent_id)
        row = fetch_one(
            """
            SELECT * FROM cp_knowledge_assets
            WHERE id = ? AND scope_id IN ('global', ?)
            """,
            (asset_id, normalized),
        )
        if row is None:
            raise KeyError(f"cp_knowledge_assets:{asset_id}")
        return normalized, row

    def _bool_from_env(self, env: dict[str, str], key: str, default: bool = False) -> bool:
        raw = str(env.get(key, os.environ.get(key, str(default)))).strip().lower()
        return raw in {"1", "true", "yes", "on"}

    def _merged_global_env_base(self) -> dict[str, str]:
        env: dict[str, str] = {}
        for section_payload in self._load_global_sections().values():
            env.update(_section_env(_safe_json_object(section_payload)))
        return env

    def _provider_api_key_secret_value(self, provider_id: str) -> str:
        secret_key = PROVIDER_API_KEY_ENV_KEYS.get(cast(Any, provider_id))
        if not secret_key:
            return ""
        row = fetch_one(
            "SELECT encrypted_value FROM cp_secret_values WHERE scope_id = 'global' AND secret_key = ?",
            (secret_key,),
        )
        if row is not None:
            encrypted = str(row["encrypted_value"] or "").strip()
            if encrypted:
                return decrypt_secret(encrypted)
        return _trimmed_text(os.environ.get(secret_key))

    def _persist_provider_secret(self, provider_id: str, api_key: str) -> None:
        """Store a provider API key obtained via OAuth subscription login."""
        env_key = PROVIDER_API_KEY_ENV_KEYS.get(cast(Any, provider_id))
        if not env_key or not api_key:
            return
        self.upsert_global_secret_asset(
            env_key,
            {
                "value": api_key,
                "description": f"Credential for {PROVIDER_TITLES.get(cast(Any, provider_id), provider_id)} (via OAuth)",
                "usage_scope": "system_only",
            },
            persist_sections=True,
        )

    def _global_secret_preview_state(self, secret_key: str) -> tuple[bool, str]:
        normalized_secret_key = _normalize_secret_key(secret_key)
        row = fetch_one(
            "SELECT preview FROM cp_secret_values WHERE scope_id = 'global' AND secret_key = ?",
            (normalized_secret_key,),
        )
        if row is not None:
            preview = str(row["preview"] or "").strip()
            if preview:
                return True, preview
            return True, "Segredo configurado"
        env_value = _trimmed_text(os.environ.get(normalized_secret_key))
        if env_value:
            return True, mask_secret(env_value)
        return False, ""

    def _provider_connection_row(self, provider_id: str) -> Any:
        normalized = provider_id.strip().lower()
        if normalized not in MANAGED_PROVIDER_IDS:
            raise ValueError(f"unsupported provider connection: {provider_id}")
        row = fetch_one(
            "SELECT * FROM cp_provider_connections WHERE provider_id = ?",
            (normalized,),
        )
        return row or self._default_provider_connection_row(normalized)

    def _default_provider_connection_row(self, provider_id: str) -> dict[str, Any]:
        normalized = provider_id.strip().lower()
        catalog_def = CORE_PROVIDER_CATALOG.get(normalized)
        supported_auth_modes = tuple(catalog_def.supported_auth_modes) if catalog_def else ("api_key",)
        if normalized in {"claude", "ollama"}:
            auth_mode = "local"
        elif "subscription_login" in supported_auth_modes:
            auth_mode = "subscription_login"
        else:
            auth_mode = "api_key"
        return {
            "provider_id": normalized,
            "auth_mode": auth_mode,
            "configured": 0,
            "verified": 0,
            "account_label": "",
            "plan_label": "",
            "project_id": "",
            "last_verified_at": "",
            "last_error": "",
            "created_at": "",
            "updated_at": "",
        }

    def _provider_connection_meta(self) -> dict[str, dict[str, Any]]:
        return self._access_meta_map("provider_connection_meta")

    def _resolve_ollama_base_url(
        self,
        *,
        auth_mode: str = "local",
        env: dict[str, str] | None = None,
        sections: dict[str, dict[str, Any]] | None = None,
    ) -> str:
        # API key mode targets Ollama Cloud, which is a fixed endpoint. We
        # ignore every override source (per-env arg, persisted meta, OS env)
        # because they can carry local URLs from a previous local-mode setup
        # or from a stray OLLAMA_BASE_URL=http://localhost:... in the host
        # environment, both of which would make the cloud verify hit the
        # local daemon and fail with `Connection refused`.
        if auth_mode == "api_key":
            return provider_default_base_url("ollama", "api_key")
        source_env = env or {}
        meta = self._access_meta_map("provider_connection_meta", sections=sections).get("OLLAMA", {})
        configured = (
            _trimmed_text(source_env.get("OLLAMA_BASE_URL"))
            or _trimmed_text(meta.get("base_url"))
            or _trimmed_text(os.environ.get("OLLAMA_BASE_URL"))
        )
        if configured:
            return configured
        return provider_default_base_url("ollama", auth_mode)

    def _resolve_ollama_connection_inputs(
        self,
        *,
        env: dict[str, str] | None = None,
    ) -> tuple[str, str, str]:
        row = fetch_one("SELECT auth_mode FROM cp_provider_connections WHERE provider_id = 'ollama'")
        auth_mode = _trimmed_text(row["auth_mode"] if row is not None else "") or "local"
        base_url = self._resolve_ollama_base_url(auth_mode=auth_mode, env=env)
        api_key = self._provider_api_key_secret_value("ollama") if auth_mode == "api_key" else ""
        return auth_mode, base_url, api_key

    def _fetch_ollama_model_catalog(
        self,
        *,
        auth_mode: str,
        base_url: str,
        api_key: str,
    ) -> dict[str, Any]:
        signature = hashlib.sha256(f"{auth_mode}|{base_url}|{api_key}".encode()).hexdigest()[:16]
        cache_key = f"catalog_{signature}"
        now = datetime.now(tz=UTC).timestamp()
        cached = self._ollama_model_cache.get(cache_key)
        if cached and (now - cached[0]) < 300:
            return dict(cached[1])

        if auth_mode == "api_key" and not api_key.strip():
            empty = {
                "items": [],
                "cached": False,
                "provider_connected": False,
                "base_url": base_url,
                "auth_mode": auth_mode,
            }
            self._ollama_model_cache[cache_key] = (now, empty)
            return dict(empty)

        request_headers = {"User-Agent": "koda/control-plane"}
        if auth_mode == "api_key" and api_key.strip():
            request_headers["Authorization"] = f"Bearer {api_key.strip()}"

        request = urllib.request.Request(
            ollama_api_url(base_url, "tags", auth_mode=auth_mode),
            headers=request_headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception:
            if cached:
                stale = dict(cached[1])
                stale["cached"] = True
                return stale
            return {
                "items": [],
                "cached": False,
                "provider_connected": False,
                "base_url": base_url,
                "auth_mode": auth_mode,
            }

        items: list[dict[str, Any]] = []
        for entry in _safe_json_list(data.get("models")):
            payload = _safe_json_object(entry)
            details = _safe_json_object(payload.get("details"))
            model_id = _nonempty_text(payload.get("model") or payload.get("name"))
            if not model_id:
                continue
            items.append(
                {
                    "model_id": model_id,
                    "name": _nonempty_text(payload.get("name")) or model_id,
                    "family": _nonempty_text(details.get("family")),
                    "parameter_size": _nonempty_text(details.get("parameter_size")),
                    "quantization_level": _nonempty_text(details.get("quantization_level")),
                    "format": _nonempty_text(details.get("format")),
                    "modified_at": _nonempty_text(payload.get("modified_at")),
                    "size": int(payload.get("size") or 0),
                }
            )
        items.sort(key=lambda item: str(item["name"]).casefold())
        catalog = {
            "items": items,
            "cached": False,
            "provider_connected": True,
            "base_url": base_url,
            "auth_mode": auth_mode,
        }
        self._ollama_model_cache[cache_key] = (now, catalog)
        return dict(catalog)

    def _merge_detected_ollama_models(
        self,
        catalog: dict[str, Any],
        detected_model_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        detected_ids = normalize_string_list(
            detected_model_ids if detected_model_ids is not None else self._provider_detected_model_ids("ollama")
        )
        if not detected_ids:
            return catalog

        merged = dict(catalog)
        items = [dict(_safe_json_object(item)) for item in _safe_json_list(merged.get("items")) if item]
        seen = {
            _nonempty_text(item.get("model_id") or item.get("name"))
            for item in items
            if _nonempty_text(item.get("model_id") or item.get("name"))
        }
        for model_id in detected_ids:
            if model_id in seen:
                continue
            items.append(
                {
                    "model_id": model_id,
                    "name": model_id,
                    "family": "",
                    "parameter_size": "",
                    "quantization_level": "",
                    "format": "",
                    "modified_at": "",
                    "size": 0,
                }
            )
            seen.add(model_id)
        items.sort(key=lambda item: str(item.get("name") or item.get("model_id") or "").casefold())
        merged["items"] = items
        if items:
            merged["provider_connected"] = True
        return merged

    def get_ollama_model_catalog(self) -> dict[str, Any]:
        auth_mode, base_url, api_key = self._resolve_ollama_connection_inputs(env=self._merged_global_env())
        catalog = self._fetch_ollama_model_catalog(auth_mode=auth_mode, base_url=base_url, api_key=api_key)
        return self._merge_detected_ollama_models(catalog)

    def _provider_auth_work_dir(self, provider_id: str) -> str:
        path = CONTROL_PLANE_RUNTIME_DIR / "_provider_auth" / provider_id.strip().lower()
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def _persist_provider_connection_meta(
        self,
        provider_id: str,
        *,
        project_id: str | None = None,
        base_url: str | None = None,
        detected_models: list[str] | None = None,
    ) -> None:
        sections = self._system_settings_sections()
        access_section = dict(self._access_section(sections))
        meta_map = dict(self._provider_connection_meta())
        normalized = provider_id.strip().upper()
        payload = dict(_safe_json_object(meta_map.get(normalized)))
        if project_id is not None:
            if project_id.strip():
                payload["project_id"] = project_id.strip()
            elif "project_id" in payload:
                payload.pop("project_id", None)
        if base_url is not None:
            if base_url.strip():
                payload["base_url"] = base_url.strip()
            elif "base_url" in payload:
                payload.pop("base_url", None)
        if detected_models is not None:
            normalized_models = list(
                dict.fromkeys(str(model).strip() for model in detected_models if str(model).strip())
            )
            if normalized_models:
                payload["detected_models"] = normalized_models
            else:
                payload.pop("detected_models", None)
        if payload:
            meta_map[normalized] = payload
        else:
            meta_map.pop(normalized, None)
        if meta_map:
            access_section["provider_connection_meta"] = meta_map
        else:
            access_section.pop("provider_connection_meta", None)
        sections["access"] = access_section
        self._persist_global_sections(sections)

    def _provider_detected_model_ids(self, provider_id: str) -> list[str]:
        meta = self._provider_connection_meta().get(provider_id.strip().upper(), {})
        return normalize_string_list(_safe_json_object(meta).get("detected_models"))

    def _provider_connection_env(self) -> dict[str, str]:
        env: dict[str, str] = {}
        rows = fetch_all("SELECT * FROM cp_provider_connections ORDER BY provider_id ASC")
        for row in rows:
            provider_id = str(row["provider_id"]).strip().lower()
            auth_mode_key = PROVIDER_AUTH_MODE_ENV_KEYS.get(cast(Any, provider_id))
            verified_key = PROVIDER_VERIFIED_ENV_KEYS.get(cast(Any, provider_id))
            auth_mode = str(row["auth_mode"] or "subscription_login")
            if auth_mode_key:
                env[auth_mode_key] = auth_mode
            if verified_key:
                env[verified_key] = "true" if bool(int(row["verified"] or 0)) else "false"
            project_key = PROVIDER_PROJECT_ENV_KEYS.get(cast(Any, provider_id))
            project_id = _trimmed_text(row["project_id"])
            if project_key and project_id:
                env[project_key] = project_id
            base_url_key = PROVIDER_BASE_URL_ENV_KEYS.get(cast(Any, provider_id))
            if base_url_key and provider_id == "ollama":
                env[base_url_key] = self._resolve_ollama_base_url(auth_mode=auth_mode)
            api_key_env_key = PROVIDER_API_KEY_ENV_KEYS.get(cast(Any, provider_id))
            if api_key_env_key and auth_mode == "api_key":
                secret_value = self._provider_api_key_secret_value(provider_id)
                if secret_value:
                    env[api_key_env_key] = secret_value
        return env

    def _merged_global_env(self) -> dict[str, str]:
        env = self._merged_global_env_base()
        env.update(self._provider_connection_env())
        return env

    def _provider_connection_status(self, payload: dict[str, Any]) -> str:
        if bool(payload.get("verified")):
            return "verified"
        if bool(payload.get("configured")):
            return "configured"
        if _nonempty_text(payload.get("last_error")):
            return "error"
        return "not_configured"

    def _serialize_provider_connection(self, provider_id: str) -> dict[str, Any]:
        row = self._provider_connection_row(provider_id)
        env = self._merged_global_env_base()
        provider_catalog = _safe_json_object(self._provider_catalog_from_env(env).get("providers"))
        catalog = _safe_json_object(provider_catalog.get(provider_id))
        catalog_def = CORE_PROVIDER_CATALOG.get(provider_id)
        supported_auth_modes_default = tuple(catalog_def.supported_auth_modes) if catalog_def else ("api_key",)
        default_auth_mode = "subscription_login" if "subscription_login" in supported_auth_modes_default else "api_key"
        auth_mode = _trimmed_text(row["auth_mode"]) or default_auth_mode
        provider_api_key_env = PROVIDER_API_KEY_ENV_KEYS.get(cast(Any, provider_id))
        if provider_api_key_env:
            api_key_present = bool(_nonempty_text(self._provider_api_key_secret_value(provider_id)))
        else:
            api_key_present = False
        row_configured = bool(int(row["configured"] or 0))
        row_verified = bool(int(row["verified"] or 0))
        configured = row_configured
        verified = row_verified
        last_error = _trimmed_text(row["last_error"])
        if auth_mode == "api_key" and provider_api_key_env and not api_key_present:
            configured = False
            verified = False
            if row_configured or row_verified:
                last_error = last_error or f"{provider_api_key_env} is not available in secrets or environment."
        payload = {
            "provider_id": provider_id,
            "title": _safe_json_object(catalog).get("title")
            or PROVIDER_TITLES.get(cast(Any, provider_id), provider_id),
            "auth_mode": auth_mode,
            "configured": configured,
            "verified": verified,
            "account_label": _trimmed_text(row["account_label"]),
            "plan_label": _trimmed_text(row["plan_label"]),
            "last_verified_at": _trimmed_text(row["last_verified_at"]),
            "last_error": last_error,
            "project_id": _trimmed_text(row["project_id"]),
            "command_present": provider_command_present(provider_id, base_env=env),
            "supports_api_key": bool(_safe_json_object(catalog).get("supports_api_key", True)),
            "supports_subscription_login": bool(_safe_json_object(catalog).get("supports_subscription_login", True)),
            "supports_local_connection": "local" in (_safe_json_object(catalog).get("supported_auth_modes") or []),
            "supported_auth_modes": _safe_json_object(catalog).get("supported_auth_modes") or ["api_key"],
            "connection_managed": bool(_safe_json_object(catalog).get("connection_managed", False)),
            "login_flow_kind": _safe_json_object(catalog).get("login_flow_kind"),
            "requires_project_id": bool(_safe_json_object(catalog).get("requires_project_id", False)),
            "api_key_present": api_key_present,
            # The masked preview is intentionally stripped from the API contract:
            # the browser only sees whether a key is configured, never its shape.
            # We still compute the local flag `api_key_present` from the same
            # source (`_global_secret_preview_state`) so the UI knows to hide
            # the "Set a key" input and show "Connected" instead.
            "api_key_preview": "",
            "base_url": self._resolve_ollama_base_url(auth_mode=auth_mode, env=env) if provider_id == "ollama" else "",
        }
        payload["connection_status"] = self._provider_connection_status(payload)
        return payload

    def _system_settings_sections(self) -> dict[str, dict[str, Any]]:
        sections = {section: _safe_json_object(self._load_global_sections().get(section)) for section in AGENT_SECTIONS}
        return sections

    def _access_section(self, sections: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
        scoped_sections = sections or self._system_settings_sections()
        return _safe_json_object(scoped_sections.get("access"))

    def _access_meta_map(
        self,
        meta_key: str,
        *,
        sections: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, dict[str, Any]]:
        access_section = self._access_section(sections)
        raw_map = _safe_json_object(access_section.get(meta_key))
        return {str(key).upper(): _safe_json_object(value) for key, value in raw_map.items()}

    def _system_settings_badge(self, env_key: str, *, merged_env: dict[str, str] | None = None) -> str:
        resolved_env = merged_env or self._merged_global_env()
        if env_key in resolved_env:
            return "custom"
        if os.environ.get(env_key):
            return "env"
        return "system_default"

    def _global_secret_usage_scope(
        self,
        secret_key: str,
        *,
        sections: dict[str, dict[str, Any]] | None = None,
    ) -> str:
        normalized = _normalize_secret_key(secret_key)
        if not _global_secret_is_grantable(normalized):
            return "system_only"
        meta = self._access_meta_map("global_secret_meta", sections=sections).get(normalized, {})
        return _normalize_general_usage_scope(meta.get("usage_scope"), default="agent_grant")

    def _current_global_secrets(
        self,
        *,
        sections: dict[str, dict[str, Any]] | None = None,
        include_hidden: bool = False,
    ) -> list[dict[str, Any]]:
        rows = fetch_all("SELECT * FROM cp_secret_values WHERE scope_id = 'global' ORDER BY secret_key ASC")
        secret_meta = self._access_meta_map("global_secret_meta", sections=sections)
        secrets = [
            {
                "id": int(row["id"]),
                "scope": "global",
                "secret_key": str(row["secret_key"]),
                "grantable_to_agents": self._global_secret_usage_scope(str(row["secret_key"]), sections=sections)
                == "agent_grant",
                "usage_scope": self._global_secret_usage_scope(str(row["secret_key"]), sections=sections),
                "description": _nonempty_text(secret_meta.get(str(row["secret_key"]).upper(), {}).get("description")),
                "preview": str(row["preview"] or ""),
                "updated_at": str(row["updated_at"] or ""),
            }
            for row in rows
            if str(row["secret_key"] or "").strip().upper() not in _REMOVED_GLOBAL_SECRET_KEYS
        ]
        if include_hidden:
            return secrets
        return [secret for secret in secrets if secret["secret_key"] not in _HIDDEN_GLOBAL_SECRET_KEYS]

    def _reconcile_global_secret_classification(self) -> None:
        rows = fetch_all("SELECT id, secret_key, encrypted_value FROM cp_secret_values WHERE scope_id = 'global'")
        if not rows:
            return

        sections = self._system_settings_sections()
        sections_changed = False
        secret_ids_to_delete: list[int] = []
        removed_secret_keys: set[str] = set()

        for row in rows:
            secret_key = str(row["secret_key"] or "").strip().upper()
            if secret_key in _REMOVED_GLOBAL_SECRET_KEYS:
                secret_ids_to_delete.append(int(row["id"]))
                removed_secret_keys.add(secret_key)
                continue
            if secret_key not in _NON_SECRET_SYSTEM_ENV_KEYS or looks_like_secret_key(secret_key):
                continue
            target_section = self._infer_section_from_env_key(secret_key)
            section_payload = dict(_safe_json_object(sections.get(target_section)))
            env_map = dict(_safe_json_object(section_payload.get("env")))
            if secret_key not in env_map:
                decrypted = decrypt_secret(str(row["encrypted_value"]))
                if decrypted.strip():
                    env_map[secret_key] = decrypted
                    section_payload["env"] = env_map
                    sections[target_section] = section_payload
                    sections_changed = True
            secret_ids_to_delete.append(int(row["id"]))

        if removed_secret_keys:
            access_section = dict(self._access_section(sections))
            secret_meta = dict(self._access_meta_map("global_secret_meta", sections=sections))
            for secret_key in removed_secret_keys:
                secret_meta.pop(secret_key, None)
            if secret_meta:
                access_section["global_secret_meta"] = secret_meta
            else:
                access_section.pop("global_secret_meta", None)
            sections["access"] = access_section
            sections_changed = True

        if sections_changed:
            for section_name, payload in sections.items():
                execute(
                    """
                    INSERT INTO cp_global_sections (section, data_json, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(section) DO UPDATE SET data_json = excluded.data_json, updated_at = excluded.updated_at
                    """,
                    (section_name, json_dump(_safe_json_object(payload)), now_iso()),
                )
            self._persist_global_default_version(sections)

        for secret_id in secret_ids_to_delete:
            execute("DELETE FROM cp_secret_values WHERE id = ?", (secret_id,))

    def _validate_system_settings_payload(self, payload: dict[str, Any]) -> None:
        errors: list[str] = []

        for entry in _normalize_env_entries(payload.get("shared_variables")):
            key = entry["key"]
            if looks_like_secret_key(key):
                errors.append(f"shared variable '{key}' looks sensitive. Store it in the global secrets vault instead.")
            elif _shared_env_key_is_reserved(key):
                errors.append(
                    f"shared variable '{key}' is reserved for core/provider/runtime behavior "
                    "and cannot be selectively granted."
                )

        for entry in _normalize_env_entries(payload.get("additional_env_vars")):
            key = entry["key"]
            if looks_like_secret_key(key):
                errors.append(
                    f"additional env var '{key}' looks sensitive. Store it in the global secrets vault instead."
                )

        if errors:
            raise ValueError("; ".join(errors))

    def _serialize_system_settings(self) -> dict[str, Any]:
        sections = self._system_settings_sections()
        env = self._merged_global_env()
        payload: dict[str, Any] = {}
        for section_name, field_specs in _SYSTEM_SETTINGS_FIELD_SPECS.items():
            section_payload: dict[str, Any] = {}
            for field_name, (env_key, kind) in field_specs.items():
                section_payload[field_name] = _typed_env_value(env.get(env_key) or os.environ.get(env_key), kind)
            payload[section_name] = section_payload

        additional_env_vars: list[dict[str, str]] = []
        for key, value in sorted(env.items()):
            if key in _SYSTEM_SETTINGS_KNOWN_ENV_KEYS:
                continue
            additional_env_vars.append({"key": key, "value": value})

        access_section = _safe_json_object(sections.get("access"))
        shared_env = _safe_json_object(access_section.get("shared_env"))
        shared_variables = [
            {"key": key, "value": str(value)} for key, value in sorted(shared_env.items()) if str(value).strip()
        ]

        version_row = fetch_one("SELECT id FROM cp_global_default_versions ORDER BY id DESC LIMIT 1")
        return {
            "version": int(version_row["id"]) if version_row else self._persist_global_default_version(sections),
            **payload,
            "shared_variables": shared_variables,
            "additional_env_vars": additional_env_vars,
            "global_secrets": self._current_global_secrets(),
        }

    def _apply_system_settings_to_sections(self, payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
        sections = self._system_settings_sections()
        env_rebuild: dict[str, dict[str, str]] = {section: {} for section in AGENT_SECTIONS}

        for section_name, field_specs in _SYSTEM_SETTINGS_FIELD_SPECS.items():
            section_payload = _safe_json_object(payload.get(section_name))
            for field_name, (env_key, kind) in field_specs.items():
                if field_name not in section_payload:
                    continue
                value = section_payload.get(field_name)
                if kind == "csv":
                    values = normalize_string_list(value)
                    if values:
                        env_rebuild[section_name][env_key] = ",".join(values)
                    continue
                if kind == "bool":
                    if isinstance(value, bool):
                        env_rebuild[section_name][env_key] = _stringify_env_value(value)
                    continue
                if env_key == "MODEL_EFFORT_DEFAULT_JSON":
                    normalized_effort = normalize_model_effort_selection(value)
                    if normalized_effort:
                        env_rebuild[section_name][env_key] = _stringify_env_value(normalized_effort)
                    continue
                if value in (None, ""):
                    continue
                env_rebuild[section_name][env_key] = _stringify_env_value(value)

        for item in _normalize_env_entries(payload.get("additional_env_vars")):
            target_section = self._infer_section_from_env_key(item["key"])
            env_rebuild[target_section][item["key"]] = item["value"]

        for section_name in AGENT_SECTIONS:
            section_payload = dict(_safe_json_object(sections.get(section_name)))
            if section_name == "access":
                shared_env = {
                    item["key"]: item["value"] for item in _normalize_env_entries(payload.get("shared_variables"))
                }
                if shared_env:
                    section_payload["shared_env"] = shared_env
                else:
                    section_payload.pop("shared_env", None)
            section_payload["env"] = env_rebuild.get(section_name, {})
            if not section_payload["env"]:
                section_payload.pop("env", None)
            sections[section_name] = section_payload
        return sections

    def _feature_flags_from_env(self, env: dict[str, str]) -> dict[str, bool]:
        return {
            "browser": self._bool_from_env(env, "BROWSER_FEATURES_ENABLED")
            or self._bool_from_env(env, "BROWSER_ENABLED")
            or self._bool_from_env(env, "RUNTIME_BROWSER_LIVE_ENABLED"),
        }

    def _provider_catalog_from_env(self, env: dict[str, str]) -> dict[str, Any]:
        providers: dict[str, Any] = {}
        enabled_ids: list[str] = []
        for definition in resolve_core_provider_catalog():
            provider = str(definition["id"])
            prefix = provider.upper()
            enabled = self._bool_from_env(
                env, f"{prefix}_ENABLED", _CORE_PROVIDER_ENABLED_DEFAULTS.get(provider, False)
            )
            available_models = [
                item.strip() for item in (env.get(f"{prefix}_AVAILABLE_MODELS") or "").split(",") if item.strip()
            ]
            if not available_models:
                ambient = os.environ.get(f"{prefix}_AVAILABLE_MODELS", "")
                available_models = [item.strip() for item in ambient.split(",") if item.strip()]
            available_models = list(
                dict.fromkeys(
                    available_models
                    + self._provider_detected_model_ids(provider)
                    + resolve_known_general_model_ids(provider)
                )
            )
            default_model = _trimmed_text(
                env.get(f"{prefix}_DEFAULT_MODEL") or os.environ.get(f"{prefix}_DEFAULT_MODEL")
            )
            tier_models = {
                "small": _trimmed_text(env.get(f"{prefix}_MODEL_SMALL") or os.environ.get(f"{prefix}_MODEL_SMALL")),
                "medium": _trimmed_text(env.get(f"{prefix}_MODEL_MEDIUM") or os.environ.get(f"{prefix}_MODEL_MEDIUM")),
                "large": _trimmed_text(env.get(f"{prefix}_MODEL_LARGE") or os.environ.get(f"{prefix}_MODEL_LARGE")),
            }
            if provider == "codex":
                binary = _trimmed_text(env.get("CODEX_BIN") or os.environ.get("CODEX_BIN") or "codex")
            elif provider == "gemini":
                binary = _trimmed_text(env.get("GEMINI_BIN") or os.environ.get("GEMINI_BIN") or "gemini")
            elif provider == "ollama":
                binary = _trimmed_text(env.get("OLLAMA_BASE_URL") or os.environ.get("OLLAMA_BASE_URL") or "ollama")
            elif provider == "whispercpp":
                binary = _trimmed_text(env.get("WHISPER_BIN") or os.environ.get("WHISPER_BIN") or "whisper-cli")
            elif provider in {"kokoro", "supertonic"}:
                binary = ""
            else:
                binary = "claude"
            ollama_catalog_items: list[dict[str, Any]] | None = None
            whisper_catalog_items: list[dict[str, Any]] | None = None
            if provider == "ollama":
                auth_mode, base_url, api_key = self._resolve_ollama_connection_inputs(env=env)
                live_catalog = self._fetch_ollama_model_catalog(
                    auth_mode=auth_mode,
                    base_url=base_url,
                    api_key=api_key,
                )
                live_catalog = self._merge_detected_ollama_models(live_catalog)
                ollama_catalog_items = [
                    cast(dict[str, Any], _safe_json_object(item))
                    for item in _safe_json_list(live_catalog.get("items"))
                    if item
                ]
                live_models = [str(item["model_id"]) for item in ollama_catalog_items if item.get("model_id")]
                if live_models:
                    available_models = live_models
                if not default_model and live_models:
                    default_model = live_models[0]
            elif provider == "whispercpp":
                whisper_catalog_items, downloaded_models, whisper_default_model = _downloaded_whisper_catalog_models(
                    whisper_catalog_payload()
                )
                available_models = downloaded_models
                if not default_model:
                    default_model = whisper_default_model
            elif provider == "supertonic":
                supertonic_catalog = supertonic_model_catalog_payload()
                available_models = []
                for raw_item in _safe_json_list(supertonic_catalog.get("items")):
                    item = _safe_json_object(raw_item)
                    model_id = _trimmed_text(item.get("model_id") or item.get("id"))
                    if model_id:
                        available_models.append(model_id)
                if not default_model:
                    default_model = (
                        _trimmed_text(supertonic_catalog.get("default_model")) or SUPERTONIC_DEFAULT_MODEL_ID
                    )
            command_present = provider_command_present(provider, base_env=env)
            providers[provider] = {
                **definition,
                "provider": provider,
                "enabled": enabled,
                "binary": binary,
                "command_present": command_present,
                "available_models": available_models,
                "default_model": default_model,
                "tier_models": tier_models,
                "functional_models": resolve_provider_function_model_catalog(
                    provider,
                    available_models=available_models,
                    ollama_catalog_items=ollama_catalog_items,
                    whisper_catalog_items=whisper_catalog_items,
                ),
            }
            if enabled and str(definition.get("category") or "general") != "infra":
                enabled_ids.append(provider)

        default_provider = _trimmed_text(
            env.get("DEFAULT_PROVIDER") or os.environ.get("DEFAULT_PROVIDER") or "claude"
        ).lower()
        if default_provider not in enabled_ids and enabled_ids:
            default_provider = enabled_ids[0]
        fallback_order = [
            item.lower()
            for item in normalize_string_list(
                env.get("PROVIDER_FALLBACK_ORDER") or os.environ.get("PROVIDER_FALLBACK_ORDER")
            )
        ]
        return {
            "default_provider": default_provider,
            "enabled_providers": enabled_ids,
            "fallback_order": [provider for provider in fallback_order if provider in enabled_ids],
            "providers": providers,
        }

    def _model_policy_from_env(self, env: dict[str, str]) -> dict[str, Any]:
        explicit = parse_json_env_value(env.get("AGENT_MODEL_POLICY_JSON"))
        provider_catalog = self._provider_catalog_from_env(env)
        providers = {
            provider: payload
            for provider, payload in provider_catalog["providers"].items()
            if str(_safe_json_object(payload).get("category") or "general") == "general"
        }
        allowed_providers = [provider for provider in provider_catalog["enabled_providers"] if provider in providers]
        available_models_by_provider = {
            provider: list(payload["available_models"])
            for provider, payload in providers.items()
            if payload["available_models"]
        }
        default_models = {
            provider: payload["default_model"] for provider, payload in providers.items() if payload["default_model"]
        }
        tier_models = {
            provider: {
                tier: model for tier, model in _safe_json_object(payload["tier_models"]).items() if _trimmed_text(model)
            }
            for provider, payload in providers.items()
        }
        policy = {
            "allowed_providers": allowed_providers,
            "default_provider": (
                provider_catalog["default_provider"]
                if provider_catalog["default_provider"] in providers
                else (allowed_providers[0] if allowed_providers else "")
            ),
            "fallback_order": [provider for provider in provider_catalog["fallback_order"] if provider in providers],
            "available_models_by_provider": available_models_by_provider,
            "default_models": default_models,
            "tier_models": tier_models,
        }
        max_budget = _trimmed_text(env.get("MAX_BUDGET_USD") or os.environ.get("MAX_BUDGET_USD"))
        max_total_budget = _trimmed_text(env.get("MAX_TOTAL_BUDGET_USD") or os.environ.get("MAX_TOTAL_BUDGET_USD"))
        if max_budget:
            policy["max_budget_usd"] = max_budget
        if max_total_budget:
            policy["max_total_budget_usd"] = max_total_budget
        functional_defaults = _typed_env_value(
            env.get("MODEL_FUNCTION_DEFAULTS_JSON") or os.environ.get("MODEL_FUNCTION_DEFAULTS_JSON"),
            "json",
        )
        normalized_functional_defaults = _normalize_functional_model_defaults(functional_defaults)
        if normalized_functional_defaults:
            policy["functional_defaults"] = normalized_functional_defaults
        policy.update(explicit)
        return {key: value for key, value in policy.items() if value not in ({}, [], "", None)}

    def _tool_policy_from_env(self, env: dict[str, str]) -> dict[str, Any]:
        explicit = parse_json_env_value(env.get("AGENT_TOOL_POLICY_JSON"))
        allowed_tool_ids = normalize_string_list(env.get("AGENT_ALLOWED_TOOLS")) or normalize_string_list(
            explicit.get("allowed_tool_ids")
        )
        policy = dict(explicit)
        if allowed_tool_ids:
            policy["allowed_tool_ids"] = allowed_tool_ids
        return policy

    def _autonomy_policy_from_env(self, env: dict[str, str]) -> dict[str, Any]:
        return parse_json_env_value(env.get("AGENT_AUTONOMY_POLICY_JSON"))

    def _clear_env_keys(self, payload: dict[str, Any], keys: tuple[str, ...]) -> None:
        env_map = _safe_json_object(payload.get("env"))
        for key in keys:
            env_map.pop(key, None)
            payload.pop(key, None)
        if env_map:
            payload["env"] = env_map
        elif "env" in payload:
            payload.pop("env", None)

    def _set_env_key(self, payload: dict[str, Any], key: str, value: Any) -> None:
        env_map = _safe_json_object(payload.get("env"))
        env_map[key] = value
        payload["env"] = env_map

    def _apply_model_policy_to_section(self, payload: dict[str, Any], model_policy: dict[str, Any]) -> None:
        self._clear_env_keys(payload, _MODEL_POLICY_ENV_KEYS)
        if not model_policy:
            payload.pop("model_policy", None)
            return

        payload["model_policy"] = model_policy
        self._set_env_key(payload, "AGENT_MODEL_POLICY_JSON", json_dump(model_policy))

        allowed_providers = [
            provider.lower() for provider in normalize_string_list(model_policy.get("allowed_providers"))
        ]
        if allowed_providers:
            self._set_env_key(payload, "CLAUDE_ENABLED", "claude" in allowed_providers)
            self._set_env_key(payload, "CODEX_ENABLED", "codex" in allowed_providers)
            self._set_env_key(payload, "GEMINI_ENABLED", "gemini" in allowed_providers)
            self._set_env_key(payload, "OLLAMA_ENABLED", "ollama" in allowed_providers)

        default_provider = _trimmed_text(model_policy.get("default_provider")).lower()
        if default_provider:
            self._set_env_key(payload, "DEFAULT_PROVIDER", default_provider)

        fallback_order = normalize_string_list(model_policy.get("fallback_order"))
        if fallback_order:
            self._set_env_key(payload, "PROVIDER_FALLBACK_ORDER", ",".join(fallback_order))

        for provider, models in _safe_json_object(model_policy.get("available_models_by_provider")).items():
            normalized_models = normalize_string_list(models)
            if normalized_models:
                self._set_env_key(payload, f"{provider.upper()}_AVAILABLE_MODELS", ",".join(normalized_models))

        for provider, model in _safe_json_object(model_policy.get("default_models")).items():
            normalized_model = _trimmed_text(model)
            if normalized_model:
                self._set_env_key(payload, f"{provider.upper()}_DEFAULT_MODEL", normalized_model)

        for provider, tiers in _safe_json_object(model_policy.get("tier_models")).items():
            tier_payload = _safe_json_object(tiers)
            for tier in ("small", "medium", "large"):
                normalized_model = _trimmed_text(tier_payload.get(tier))
                if normalized_model:
                    self._set_env_key(payload, f"{provider.upper()}_MODEL_{tier.upper()}", normalized_model)

        functional_defaults = _normalize_functional_model_defaults(model_policy.get("functional_defaults"))
        if functional_defaults:
            self._set_env_key(payload, "MODEL_FUNCTION_DEFAULTS_JSON", functional_defaults)
            general_default = _safe_json_object(functional_defaults.get("general"))
            general_provider = _trimmed_text(general_default.get("provider_id")).lower()
            general_model = _trimmed_text(general_default.get("model_id"))
            if general_provider and general_model:
                self._set_env_key(payload, "DEFAULT_PROVIDER", general_provider)
                self._set_env_key(payload, f"{general_provider.upper()}_DEFAULT_MODEL", general_model)
            audio_default = _safe_json_object(functional_defaults.get("audio"))
            audio_provider = _trimmed_text(audio_default.get("provider_id")).lower()
            audio_model = _trimmed_text(audio_default.get("model_id"))
            if audio_provider == "elevenlabs" and audio_model:
                self._set_env_key(payload, "ELEVENLABS_MODEL", audio_model)

        if model_policy.get("max_budget_usd") not in (None, ""):
            self._set_env_key(payload, "MAX_BUDGET_USD", model_policy["max_budget_usd"])
        if model_policy.get("max_total_budget_usd") not in (None, ""):
            self._set_env_key(payload, "MAX_TOTAL_BUDGET_USD", model_policy["max_total_budget_usd"])

    def _apply_tool_policy_to_section(self, payload: dict[str, Any], tool_policy: dict[str, Any]) -> None:
        self._clear_env_keys(payload, _TOOL_POLICY_ENV_KEYS)
        if not tool_policy:
            payload.pop("tool_policy", None)
            return

        payload["tool_policy"] = tool_policy
        self._set_env_key(payload, "AGENT_TOOL_POLICY_JSON", json_dump(tool_policy))
        allowed_tool_ids = normalize_string_list(tool_policy.get("allowed_tool_ids"))
        if allowed_tool_ids:
            self._set_env_key(payload, "AGENT_ALLOWED_TOOLS", ",".join(allowed_tool_ids))

    def _apply_autonomy_policy_to_section(self, payload: dict[str, Any], autonomy_policy: dict[str, Any]) -> None:
        self._clear_env_keys(payload, _AUTONOMY_POLICY_ENV_KEYS)
        if not autonomy_policy:
            payload.pop("autonomy_policy", None)
            return
        payload["autonomy_policy"] = autonomy_policy
        self._set_env_key(payload, "AGENT_AUTONOMY_POLICY_JSON", json_dump(autonomy_policy))

    def _apply_memory_policy_to_section(self, payload: dict[str, Any], memory_policy: dict[str, Any]) -> None:
        self._clear_env_keys(payload, _MEMORY_POLICY_ENV_KEYS)
        # Drop top-level shadows of policy fields that historic seeds wrote at
        # the section root. They duplicate `policy.*` and the env map, so any
        # divergence between them is a bug surface — source of truth must be
        # `policy` + `env` only.
        for legacy_field in (
            "enabled",
            "proactive_enabled",
            "procedural_enabled",
            "maintenance_enabled",
            "digest_enabled",
            "max_recall",
            "max_per_user",
            "recall_threshold",
            "max_context_tokens",
            "max_extraction_items",
            "procedural_max_recall",
            "recall_timeout",
            "similarity_dedup_threshold",
        ):
            payload.pop(legacy_field, None)
        if not memory_policy:
            payload.pop("policy", None)
            return

        payload["policy"] = memory_policy
        if memory_policy.get("enabled") is not None:
            self._set_env_key(payload, "MEMORY_ENABLED", bool(memory_policy.get("enabled")))
        if memory_policy.get("max_recall") is not None:
            self._set_env_key(payload, "MEMORY_MAX_RECALL", memory_policy["max_recall"])
        if memory_policy.get("recall_threshold") is not None:
            self._set_env_key(payload, "MEMORY_RECALL_THRESHOLD", memory_policy["recall_threshold"])
        if memory_policy.get("max_context_tokens") is not None:
            self._set_env_key(payload, "MEMORY_MAX_CONTEXT_TOKENS", memory_policy["max_context_tokens"])
        if memory_policy.get("recency_half_life_days") is not None:
            self._set_env_key(payload, "MEMORY_RECENCY_HALF_LIFE_DAYS", memory_policy["recency_half_life_days"])
        if memory_policy.get("max_extraction_items") is not None:
            self._set_env_key(payload, "MEMORY_MAX_EXTRACTION_ITEMS", memory_policy["max_extraction_items"])
        if memory_policy.get("extraction_provider") not in (None, ""):
            self._set_env_key(payload, "MEMORY_EXTRACTION_PROVIDER", memory_policy["extraction_provider"])
        if memory_policy.get("extraction_model") not in (None, ""):
            self._set_env_key(payload, "MEMORY_EXTRACTION_MODEL", memory_policy["extraction_model"])
        if memory_policy.get("proactive_enabled") is not None:
            self._set_env_key(payload, "MEMORY_PROACTIVE_ENABLED", bool(memory_policy.get("proactive_enabled")))
        if memory_policy.get("procedural_enabled") is not None:
            self._set_env_key(payload, "MEMORY_PROCEDURAL_ENABLED", bool(memory_policy.get("procedural_enabled")))
        if memory_policy.get("procedural_max_recall") is not None:
            self._set_env_key(payload, "MEMORY_PROCEDURAL_MAX_RECALL", memory_policy["procedural_max_recall"])
        if memory_policy.get("recall_timeout") is not None:
            self._set_env_key(payload, "MEMORY_RECALL_TIMEOUT", memory_policy["recall_timeout"])
        if memory_policy.get("similarity_dedup_threshold") is not None:
            self._set_env_key(
                payload,
                "MEMORY_SIMILARITY_DEDUP_THRESHOLD",
                memory_policy["similarity_dedup_threshold"],
            )
        if memory_policy.get("max_per_user") is not None:
            self._set_env_key(payload, "MEMORY_MAX_PER_USER", memory_policy["max_per_user"])
        if memory_policy.get("maintenance_enabled") is not None:
            self._set_env_key(payload, "MEMORY_MAINTENANCE_ENABLED", bool(memory_policy.get("maintenance_enabled")))
        if memory_policy.get("digest_enabled") is not None:
            self._set_env_key(payload, "MEMORY_DIGEST_ENABLED", bool(memory_policy.get("digest_enabled")))

    def _apply_knowledge_policy_to_section(self, payload: dict[str, Any], knowledge_policy: dict[str, Any]) -> None:
        self._clear_env_keys(payload, _KNOWLEDGE_POLICY_ENV_KEYS)
        # Same legacy-shadow cleanup as the memory branch — keep `policy` + `env`
        # as the only sources of truth; drop top-level duplicates left by older
        # seeds.
        for legacy_field in (
            "enabled",
            "max_results",
            "recall_threshold",
            "context_max_tokens",
            "workspace_max_files",
            "max_observed_patterns",
            "max_source_age_days",
            "promotion_mode",
            "require_owner_provenance",
            "require_freshness_provenance",
            "allowed_layers",
        ):
            payload.pop(legacy_field, None)
        if not knowledge_policy:
            payload.pop("policy", None)
            return

        payload["policy"] = knowledge_policy
        if knowledge_policy.get("enabled") is not None:
            self._set_env_key(payload, "KNOWLEDGE_ENABLED", bool(knowledge_policy.get("enabled")))
        if knowledge_policy.get("max_results") is not None:
            self._set_env_key(payload, "KNOWLEDGE_MAX_RESULTS", knowledge_policy["max_results"])
        if knowledge_policy.get("recall_threshold") is not None:
            self._set_env_key(payload, "KNOWLEDGE_RECALL_THRESHOLD", knowledge_policy["recall_threshold"])
        if knowledge_policy.get("recall_timeout") is not None:
            self._set_env_key(payload, "KNOWLEDGE_RECALL_TIMEOUT", knowledge_policy["recall_timeout"])
        if knowledge_policy.get("context_max_tokens") is not None:
            self._set_env_key(payload, "KNOWLEDGE_CONTEXT_MAX_TOKENS", knowledge_policy["context_max_tokens"])
        if knowledge_policy.get("workspace_max_files") is not None:
            self._set_env_key(payload, "KNOWLEDGE_WORKSPACE_MAX_FILES", knowledge_policy["workspace_max_files"])
        source_globs = normalize_string_list(knowledge_policy.get("source_globs"))
        if source_globs:
            self._set_env_key(payload, "KNOWLEDGE_SOURCE_GLOBS", ",".join(source_globs))
        workspace_source_globs = normalize_string_list(knowledge_policy.get("workspace_source_globs"))
        if workspace_source_globs:
            self._set_env_key(payload, "KNOWLEDGE_WORKSPACE_SOURCE_GLOBS", ",".join(workspace_source_globs))
        if knowledge_policy.get("max_observed_patterns") is not None:
            self._set_env_key(
                payload,
                "KNOWLEDGE_MAX_OBSERVED_PATTERNS",
                knowledge_policy["max_observed_patterns"],
            )
        allowed_layers = normalize_string_list(knowledge_policy.get("allowed_layers"))
        if allowed_layers:
            self._set_env_key(payload, "KNOWLEDGE_ALLOWED_LAYERS", ",".join(allowed_layers))
        allowed_source_labels = normalize_string_list(knowledge_policy.get("allowed_source_labels"))
        if allowed_source_labels:
            self._set_env_key(payload, "KNOWLEDGE_ALLOWED_SOURCE_LABELS", ",".join(allowed_source_labels))
        allowed_workspace_roots = normalize_string_list(knowledge_policy.get("allowed_workspace_roots"))
        if allowed_workspace_roots:
            self._set_env_key(payload, "KNOWLEDGE_ALLOWED_WORKSPACE_ROOTS", ",".join(allowed_workspace_roots))
        if knowledge_policy.get("max_source_age_days") is not None:
            self._set_env_key(payload, "KNOWLEDGE_MAX_SOURCE_AGE_DAYS", knowledge_policy["max_source_age_days"])
        if knowledge_policy.get("require_owner_provenance") is not None:
            self._set_env_key(
                payload,
                "KNOWLEDGE_REQUIRE_OWNER_PROVENANCE",
                bool(knowledge_policy.get("require_owner_provenance")),
            )
        if knowledge_policy.get("require_freshness_provenance") is not None:
            self._set_env_key(
                payload,
                "KNOWLEDGE_REQUIRE_FRESHNESS_PROVENANCE",
                bool(knowledge_policy.get("require_freshness_provenance")),
            )
        if knowledge_policy.get("promotion_mode") not in (None, ""):
            self._set_env_key(payload, "KNOWLEDGE_PROMOTION_MODE", knowledge_policy["promotion_mode"])
        if knowledge_policy.get("strategy_default") not in (None, ""):
            self._set_env_key(payload, "KNOWLEDGE_STRATEGY_DEFAULT", knowledge_policy["strategy_default"])
        if knowledge_policy.get("trace_sampling_rate") is not None:
            self._set_env_key(payload, "KNOWLEDGE_TRACE_SAMPLING_RATE", knowledge_policy["trace_sampling_rate"])
        if knowledge_policy.get("graph_enabled") is not None:
            self._set_env_key(payload, "KNOWLEDGE_GRAPH_ENABLED", bool(knowledge_policy.get("graph_enabled")))
        if knowledge_policy.get("multimodal_graph_enabled") is not None:
            self._set_env_key(
                payload,
                "KNOWLEDGE_MULTIMODAL_GRAPH_ENABLED",
                bool(knowledge_policy.get("multimodal_graph_enabled")),
            )
        if knowledge_policy.get("evaluation_sampling_rate") is not None:
            self._set_env_key(
                payload,
                "KNOWLEDGE_EVALUATION_SAMPLING_RATE",
                knowledge_policy["evaluation_sampling_rate"],
            )
        if knowledge_policy.get("citation_policy") not in (None, ""):
            self._set_env_key(payload, "KNOWLEDGE_CITATION_POLICY", knowledge_policy["citation_policy"])
        if knowledge_policy.get("v2_enabled") is not None:
            self._set_env_key(payload, "KNOWLEDGE_V2_ENABLED", bool(knowledge_policy.get("v2_enabled")))
        if knowledge_policy.get("v2_max_graph_hops") is not None:
            self._set_env_key(payload, "KNOWLEDGE_V2_MAX_GRAPH_HOPS", knowledge_policy["v2_max_graph_hops"])
        if knowledge_policy.get("cross_encoder_model") not in (None, ""):
            self._set_env_key(payload, "KNOWLEDGE_V2_CROSS_ENCODER_MODEL", knowledge_policy["cross_encoder_model"])
        if knowledge_policy.get("storage_mode") not in (None, ""):
            self._set_env_key(payload, "KNOWLEDGE_V2_STORAGE_MODE", knowledge_policy["storage_mode"])
        if knowledge_policy.get("object_store_root") not in (None, ""):
            self._set_env_key(payload, "KNOWLEDGE_V2_OBJECT_STORE_ROOT", knowledge_policy["object_store_root"])

    def _validation_inputs(self, snapshot: dict[str, Any]) -> tuple[dict[str, bool], dict[str, list[str]], list[str]]:
        env = {key: _stringify_env_value(value) for key, value in _safe_json_object(snapshot.get("env")).items()}
        feature_flags = self._feature_flags_from_env(env)
        provider_catalog = self._provider_catalog_from_env(env)
        available_models = {
            provider: list(payload["available_models"])
            for provider, payload in _safe_json_object(provider_catalog.get("providers")).items()
        }
        enabled_providers = list(provider_catalog.get("enabled_providers") or [])
        return feature_flags, available_models, enabled_providers

    def _build_validation_report(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        agent_id = _trimmed_text(_safe_json_object(snapshot.get("agent")).get("id"))
        agent_spec = self.get_agent_spec(agent_id, snapshot=snapshot)
        agent_row = fetch_one("SELECT * FROM cp_agent_definitions WHERE id = ?", (_normalize_agent_id(agent_id),))
        if agent_row is not None:
            agent_spec = self._resolve_hierarchical_spec(agent_spec, agent_row)
        feature_flags, available_models, enabled_providers = self._validation_inputs(snapshot)
        validation = validate_agent_spec(
            agent_spec,
            feature_flags=feature_flags,
            available_models_by_provider=available_models,
            enabled_providers=enabled_providers,
        )
        validation["feature_flags"] = feature_flags
        validation["provider_catalog"] = self._provider_catalog_from_env(
            {key: _stringify_env_value(value) for key, value in _safe_json_object(snapshot.get("env")).items()}
        )
        return validation

    def _knowledge_governance_store(self) -> Any:
        from koda.state import knowledge_governance_store

        return knowledge_governance_store

    def _knowledge_repository(self, agent_id: str) -> Any:
        from koda.knowledge.repository import KnowledgeRepository

        return KnowledgeRepository(_normalize_agent_id(agent_id))

    def _improvement_proposal_service(self, agent_id: str) -> Any:
        from koda.services.improvement_proposals import ImprovementProposalService

        return ImprovementProposalService(self._knowledge_repository(agent_id))

    def _dashboard_store(self) -> Any:
        from koda.state.dashboard_store import get_dashboard_store

        return get_dashboard_store()

    def _require_dashboard_agent(self, agent_id: str) -> tuple[str, dict[str, Any]]:
        normalized = _normalize_agent_id(agent_id)
        row = fetch_one("SELECT * FROM cp_agent_definitions WHERE id = ?", (normalized,))
        if row is None:
            raise KeyError(normalized)
        return normalized, cast(dict[str, Any], row)

    def list_agents(self) -> list[dict[str, Any]]:
        self.ensure_seeded()
        workspace_map = self._workspace_map()
        squad_map = self._squad_map()
        rows = fetch_all("SELECT * FROM cp_agent_definitions ORDER BY id ASC")
        items: list[dict[str, Any]] = []
        for row in rows:
            agent_id = str(row["id"])
            items.append(
                self._serialize_agent_summary(
                    row,
                    workspace_map=workspace_map,
                    squad_map=squad_map,
                    default_model_summary=self._resolve_agent_default_model_summary(agent_id),
                )
            )
        return items

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        self.ensure_seeded()
        normalized = _normalize_agent_id(agent_id)
        row = fetch_one("SELECT * FROM cp_agent_definitions WHERE id = ?", (normalized,))
        if row is None:
            return None
        sections = {section: self.get_section(normalized, section)["data"] for section in AGENT_SECTIONS}
        documents = {kind: self.get_document(normalized, kind) for kind in DOCUMENT_KINDS}
        knowledge_assets = self.list_knowledge_assets(normalized)
        has_materialized_runtime = bool(int(row["applied_version"] or row["desired_version"] or 0))
        templates = self.list_template_assets(normalized)
        skills = self.list_skill_assets(normalized)
        knowledge_candidates: list[dict[str, Any]] = []
        runbooks: list[dict[str, Any]] = []
        if has_materialized_runtime:
            try:
                knowledge_candidates = self.list_knowledge_candidates(normalized, review_status="pending", limit=50)
                runbooks = self.list_runbooks(normalized, limit=50)
            except Exception as exc:
                log.warning(
                    "control_plane_runtime_governance_unavailable",
                    agent_id=normalized,
                    error=str(exc),
                )
        secrets = self.list_secret_assets(normalized)
        published_snapshot = self.get_published_snapshot(normalized)
        draft_snapshot = self.build_draft_snapshot(normalized)
        agent_spec = self.get_agent_spec(normalized, snapshot=draft_snapshot)
        validation = self._build_validation_report(draft_snapshot)
        return {
            **self._serialize_agent_summary(
                row,
                workspace_map=self._workspace_map(),
                squad_map=self._squad_map(),
                default_model_summary=self._resolve_agent_default_model_summary(normalized, snapshot=draft_snapshot),
            ),
            "sections": sections,
            "documents": {key: value["content_md"] if value else "" for key, value in documents.items()},
            "knowledge_assets": knowledge_assets,
            "knowledge_candidates": knowledge_candidates,
            "templates": templates,
            "skills": skills,
            "runbooks": runbooks,
            "secrets": secrets,
            "draft_snapshot": self._redact_snapshot_for_client(draft_snapshot),
            "published_snapshot": self._redact_snapshot_for_client(published_snapshot),
            "versions": self.list_versions(normalized),
            "agent_spec": agent_spec,
            "compiled_prompt": validation["compiled_prompt"],
            "validation": validation,
        }

    def get_dashboard_agent_summary(self, agent_id: str, *, recent_task_limit: int = 5) -> dict[str, Any]:
        normalized, row = self._require_dashboard_agent(agent_id)
        stats = self._dashboard_store().get_agent_stats(normalized, recent_task_limit=recent_task_limit)
        return {
            **stats,
            "agent": self._serialize_agent_summary(
                row,
                workspace_map=self._workspace_map(),
                squad_map=self._squad_map(),
                default_model_summary=self._resolve_agent_default_model_summary(normalized),
            ),
        }

    def list_dashboard_executions(
        self,
        agent_id: str,
        *,
        status: str | None = None,
        search: str | None = None,
        session_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        return cast(
            list[dict[str, Any]],
            self._dashboard_store().list_executions(
                normalized,
                status=status,
                search=search,
                session_id=session_id,
                limit=limit,
                offset=offset,
            ),
        )

    def get_dashboard_execution(self, agent_id: str, task_id: int) -> dict[str, Any] | None:
        normalized, _ = self._require_dashboard_agent(agent_id)
        # Delegate to the control-plane dashboard_service, which uses the
        # canonical uppercase agent_id convention. dashboard_store's
        # _normalize_scope lowercases and misses rows written by the runtime
        # (``tasks.agent_id = 'PIXIE_COPY'`` after the recent case-fix
        # migration), returning 404 for existing executions.
        from koda.control_plane.dashboard_service import get_dashboard_execution_detail

        return get_dashboard_execution_detail(normalized, task_id)

    def get_dashboard_execution_run_graph(self, agent_id: str, task_id: int) -> dict[str, Any] | None:
        normalized, _ = self._require_dashboard_agent(agent_id)
        from koda.control_plane.dashboard_service import get_dashboard_execution_run_graph

        return get_dashboard_execution_run_graph(normalized, task_id)

    def get_dashboard_execution_replay(self, agent_id: str, task_id: int) -> dict[str, Any] | None:
        normalized, _ = self._require_dashboard_agent(agent_id)
        from koda.control_plane.dashboard_service import get_dashboard_execution_replay

        return get_dashboard_execution_replay(normalized, task_id)

    def get_dashboard_execution_sandbox_doctor(self, agent_id: str, task_id: int) -> dict[str, Any] | None:
        normalized, _ = self._require_dashboard_agent(agent_id)
        from koda.control_plane.dashboard_service import get_dashboard_execution_sandbox_doctor

        return get_dashboard_execution_sandbox_doctor(normalized, task_id)

    def list_dashboard_sessions(
        self,
        agent_id: str,
        *,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        return cast(
            list[dict[str, Any]],
            self._dashboard_store().list_sessions(
                normalized,
                search=search,
                limit=limit,
                offset=offset,
            ),
        )

    def list_dashboard_session_summaries(
        self,
        *,
        agent_ids: list[str],
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        seen_agent_ids: set[str] = set()
        for agent_id in agent_ids:
            normalized, _ = self._require_dashboard_agent(agent_id)
            if normalized in seen_agent_ids:
                continue
            seen_agent_ids.add(normalized)
            items.extend(
                cast(
                    list[dict[str, Any]],
                    self._dashboard_store().list_sessions(
                        normalized,
                        search=search,
                        limit=5000,
                        offset=0,
                    ),
                )
            )
        items.sort(
            key=lambda item: str(item.get("last_activity_at") or ""),
            reverse=True,
        )
        deduped_items: list[dict[str, Any]] = []
        seen_sessions: set[tuple[str, str]] = set()
        for item in items:
            key = (
                str(item.get("bot_id") or item.get("agent_id") or ""),
                str(item.get("session_id") or ""),
            )
            if not key[0] or not key[1] or key in seen_sessions:
                continue
            seen_sessions.add(key)
            deduped_items.append(item)
        return deduped_items[offset : offset + limit]

    def get_dashboard_session(
        self,
        agent_id: str,
        session_id: str,
        *,
        limit: int | None = None,
        before: str | None = None,
    ) -> dict[str, Any] | None:
        normalized, _ = self._require_dashboard_agent(agent_id)
        return cast(
            dict[str, Any] | None,
            self._dashboard_store().get_session(
                normalized,
                session_id,
                limit=limit,
                before=before,
            ),
        )

    def delete_dashboard_session(self, agent_id: str, session_id: str) -> int:
        normalized, _ = self._require_dashboard_agent(agent_id)
        return int(self._dashboard_store().delete_session(normalized, session_id))

    def get_dashboard_runtime_artifact_for_download(
        self,
        agent_id: str,
        artifact_id: int,
    ) -> dict[str, Any] | None:
        normalized, _ = self._require_dashboard_agent(agent_id)
        row = fetch_one(
            """
            SELECT id, agent_id, task_id, env_id, artifact_kind, label, path,
                   metadata_json, created_at, expires_at
              FROM runtime_artifacts
             WHERE id = ? AND lower(agent_id) = lower(?)
            """,
            (artifact_id, normalized),
        )
        if row is None:
            return None
        item = dict(row)
        item["metadata"] = _safe_json_object(json_load(item.get("metadata_json"), {}))
        return item

    def _wait_for_dashboard_runtime_api(
        self,
        runtime_base_url: str,
        runtime_token: str,
        *,
        timeout_seconds: float = 8.0,
    ) -> bool:
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        readiness_url = f"{runtime_base_url}/api/runtime/readiness"
        while True:
            request = urllib.request.Request(
                readiness_url,
                headers={
                    "X-Runtime-Token": runtime_token,
                    "User-Agent": "koda/control-plane",
                },
                method="GET",
            )
            try:
                with urllib.request.urlopen(request, timeout=1.5) as response:
                    status = int(getattr(response, "status", 200) or 200)
                    if 200 <= status < 300:
                        return True
            except urllib.error.HTTPError as exc:
                if exc.code in {401, 403, 404}:
                    return False
            except urllib.error.URLError:
                pass
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.35)

    def _wake_dashboard_runtime(self, agent_id: str) -> None:
        try:
            from koda.control_plane.lifecycle_events import notify_lifecycle_change

            notify_lifecycle_change(reason=f"dashboard-chat:{agent_id}")
        except Exception:
            log.exception("dashboard_runtime_wake_failed", agent_id=agent_id)

    @staticmethod
    def _runtime_http_error_message(exc: urllib.error.HTTPError) -> str:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            payload = None
        if isinstance(payload, dict) and payload.get("error"):
            return str(payload["error"])
        return f"runtime request failed with status {exc.code}"

    def _post_runtime_session_message(
        self,
        *,
        agent_id: str,
        runtime_base_url: str,
        runtime_token: str,
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        def build_request() -> urllib.request.Request:
            return urllib.request.Request(
                f"{runtime_base_url}/api/runtime/sessions/messages",
                data=json.dumps(request_payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "X-Runtime-Token": runtime_token,
                    "User-Agent": "koda/control-plane",
                },
                method="POST",
            )

        for attempt in range(2):
            try:
                with urllib.request.urlopen(build_request(), timeout=20) as response:
                    return cast(dict[str, Any], json.loads(response.read().decode("utf-8")))
            except urllib.error.HTTPError as exc:
                message = self._runtime_http_error_message(exc)
                if exc.code in {502, 503, 504} and attempt == 0:
                    self._wake_dashboard_runtime(agent_id)
                    self._wait_for_dashboard_runtime_api(runtime_base_url, runtime_token)
                    continue
                if 400 <= exc.code < 500:
                    raise ValueError(f"runtime rejected dashboard message: {message}") from exc
                raise RuntimeError(message) from exc
            except urllib.error.URLError as exc:
                if attempt == 0:
                    self._wake_dashboard_runtime(agent_id)
                    if self._wait_for_dashboard_runtime_api(runtime_base_url, runtime_token):
                        continue
                raise RuntimeError(f"runtime is unavailable for agent {agent_id}") from exc

        raise RuntimeError(f"runtime is unavailable for agent {agent_id}")

    def send_dashboard_session_message(
        self,
        agent_id: str,
        *,
        text: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        normalized, agent_row = self._require_dashboard_agent(agent_id)
        payload_text = str(text or "").strip()
        if not payload_text:
            raise ValueError("text is required")
        agent_status = (
            str(agent_row["status"] or "").strip().lower()
            if _row_has_column(agent_row, "status")
            else str(_safe_json_object(agent_row).get("status") or "").strip().lower()
        )
        if agent_status and agent_status != "active":
            raise ValueError(f"agent {normalized} is {agent_status}; activate it before sending messages")

        runtime_access = self.get_runtime_access(normalized, capability="mutate")
        runtime_base_url = str(runtime_access.get("runtime_base_url") or "").rstrip("/")
        runtime_token = str(runtime_access.get("runtime_request_token") or "").strip()
        if not runtime_base_url:
            raise RuntimeError("runtime base URL is unavailable for this agent")
        if not runtime_token:
            raise RuntimeError("runtime token is not configured for this agent")

        request_payload = {"text": payload_text}
        if session_id:
            request_payload["session_id"] = str(session_id).strip()

        return self._post_runtime_session_message(
            agent_id=normalized,
            runtime_base_url=runtime_base_url,
            runtime_token=runtime_token,
            request_payload=request_payload,
        )

    def send_dashboard_squad_message(
        self,
        agent_id: str,
        *,
        text: str,
        squad_thread_id: str,
        session_id: str | None = None,
        squad_task_id: str | None = None,
        parent_message_id: str | None = None,
        delegation_chain: list[str] | None = None,
        delegation_request_id: str | None = None,
        delegation_origin_agent_id: str | None = None,
        telegram_message_thread_id: int | None = None,
        user_id: int | None = None,
        chat_id: int | None = None,
    ) -> dict[str, Any]:
        normalized, agent_row = self._require_dashboard_agent(agent_id)
        payload_text = str(text or "").strip()
        if not payload_text:
            raise ValueError("text is required")
        thread_id = str(squad_thread_id or "").strip()
        if not thread_id:
            raise ValueError("squad_thread_id is required")
        agent_status = (
            str(agent_row["status"] or "").strip().lower()
            if _row_has_column(agent_row, "status")
            else str(_safe_json_object(agent_row).get("status") or "").strip().lower()
        )
        if agent_status and agent_status != "active":
            raise ValueError(f"agent {normalized} is {agent_status}; activate it before sending messages")

        runtime_access = self.get_runtime_access(normalized, capability="mutate")
        runtime_base_url = str(runtime_access.get("runtime_base_url") or "").rstrip("/")
        runtime_token = str(runtime_access.get("runtime_request_token") or "").strip()
        if not runtime_base_url:
            raise RuntimeError("runtime base URL is unavailable for this agent")
        if not runtime_token:
            raise RuntimeError("runtime token is not configured for this agent")

        session_seed = f"{thread_id}:{normalized}:{squad_task_id or parent_message_id or uuid4().hex}"
        resolved_session_id = (
            str(session_id or "").strip() or f"squad-{hashlib.sha256(session_seed.encode()).hexdigest()[:24]}"
        )
        request_payload: dict[str, Any] = {
            "text": payload_text,
            "session_id": resolved_session_id,
            "squad": {
                "thread_id": thread_id,
                "target_agent_id": normalized,
                "squad_task_id": str(squad_task_id).strip() if squad_task_id else None,
                "parent_message_id": str(parent_message_id).strip() if parent_message_id else None,
                "delegation_chain": list(delegation_chain or []),
                "delegation_request_id": str(delegation_request_id).strip() if delegation_request_id else None,
                "delegation_origin_agent_id": str(delegation_origin_agent_id).strip()
                if delegation_origin_agent_id
                else None,
                "telegram_message_thread_id": telegram_message_thread_id,
                "user_id": user_id,
                "chat_id": chat_id,
            },
        }

        try:
            return self._post_runtime_session_message(
                agent_id=normalized,
                runtime_base_url=runtime_base_url,
                runtime_token=runtime_token,
                request_payload=request_payload,
            )
        except ValueError as exc:
            carrier_agent_id = str(AGENT_ID or "").strip().upper()
            if "invalid runtime token" not in str(exc) or not carrier_agent_id or carrier_agent_id == normalized:
                raise
            carrier_access = self.get_runtime_access(carrier_agent_id, capability="mutate")
            carrier_base_url = str(carrier_access.get("runtime_base_url") or "").rstrip("/")
            carrier_token = str(carrier_access.get("runtime_request_token") or "").strip()
            if not carrier_base_url or not carrier_token:
                raise
            log.warning(
                "dashboard_squad_runtime_carrier_fallback",
                target_agent_id=normalized,
                carrier_agent_id=carrier_agent_id,
            )
            return self._post_runtime_session_message(
                agent_id=carrier_agent_id,
                runtime_base_url=carrier_base_url,
                runtime_token=carrier_token,
                request_payload=request_payload,
            )

    def list_dashboard_dlq(
        self,
        agent_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        retry_eligible: bool | None = None,
    ) -> list[dict[str, Any]]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        return cast(
            list[dict[str, Any]],
            self._dashboard_store().list_dlq(
                normalized,
                limit=limit,
                offset=offset,
                retry_eligible=retry_eligible,
            ),
        )

    def get_dashboard_costs(self, agent_id: str, *, days: int = 30) -> dict[str, Any]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        return cast(dict[str, Any], self._dashboard_store().get_costs(normalized, days=days))

    def list_dashboard_schedules(self, agent_id: str, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        return cast(
            list[dict[str, Any]],
            self._dashboard_store().list_schedules(normalized, limit=limit, offset=offset),
        )

    def list_dashboard_audit(
        self,
        agent_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        event_type: str | None = None,
        user_id: int | None = None,
    ) -> list[dict[str, Any]]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        return cast(
            list[dict[str, Any]],
            self._dashboard_store().list_audit(
                normalized,
                limit=limit,
                offset=offset,
                event_type=event_type,
                user_id=user_id,
            ),
        )

    def list_dashboard_audit_types(self, agent_id: str) -> list[str]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        return cast(list[str], self._dashboard_store().list_audit_types(normalized))

    def get_dashboard_memory_map(
        self,
        agent_id: str,
        *,
        user_id: int | None = None,
        session_id: str | None = None,
        days: int = 30,
        include_inactive: bool = False,
        limit: int = 160,
    ) -> dict[str, Any]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        return cast(
            dict[str, Any],
            dashboard_get_memory_map_payload(
                normalized,
                user_id=user_id,
                session_id=session_id,
                days=days,
                include_inactive=include_inactive,
                limit=limit,
            ),
        )

    def list_dashboard_memory_curation(
        self,
        agent_id: str,
        *,
        search: str | None = None,
        status: str | None = None,
        memory_type: str | None = None,
        kind: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        return cast(
            dict[str, Any],
            dashboard_list_memory_curation_payload(
                normalized,
                query_text=search or "",
                memory_status=status,
                memory_type=memory_type,
                kind=kind,
                limit=limit,
                offset=offset,
            ),
        )

    def get_dashboard_memory_curation_detail(self, agent_id: str, memory_id: int) -> dict[str, Any] | None:
        normalized, _ = self._require_dashboard_agent(agent_id)
        try:
            return cast(
                dict[str, Any] | None,
                dashboard_get_memory_curation_detail_payload(normalized, memory_id),
            )
        except KeyError:
            return None

    def get_dashboard_memory_cluster_detail(self, agent_id: str, cluster_id: str) -> dict[str, Any] | None:
        normalized, _ = self._require_dashboard_agent(agent_id)
        try:
            return cast(
                dict[str, Any] | None,
                dashboard_get_memory_curation_cluster_payload(normalized, cluster_id),
            )
        except KeyError:
            return None

    def apply_dashboard_memory_curation_action(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        return cast(dict[str, Any], dashboard_apply_memory_curation_action(normalized, payload))

    def _serialize_core_catalog_entry(self, definition: dict[str, Any]) -> dict[str, Any]:
        integration_id = str(definition.get("id") or "").strip().lower()
        auth_modes = [str(item).strip() for item in definition.get("auth_modes") or [] if str(item).strip()]
        default_auth = auth_modes[0] if auth_modes else "none"
        return {
            "connection_key": _core_connection_key(integration_id),
            "kind": "core",
            "integration_key": integration_id,
            "display_name": str(definition.get("title") or integration_id),
            "description": str(definition.get("description") or ""),
            "category": str(definition.get("category") or "general"),
            "transport_kind": str(definition.get("transport") or "core"),
            "auth_capabilities": {"modes": auth_modes},
            "auth_strategy_default": default_auth,
            "official_support_level": "core",
            "oauth_mode": "confidential" if any("oauth" in mode for mode in auth_modes) else "none",
            "remote_url": None,
            "vendor_notes": "",
            "default_policy": "always_ask",
            "env_schema": [],
            "headers_schema": [],
            "documentation_url": str(definition.get("documentation_url") or "") or None,
            "logo_key": str(definition.get("logo_key") or integration_id) or None,
            "metadata": {
                "supports_persistence": bool(definition.get("supports_persistence")),
                "health_probe": str(definition.get("health_probe") or ""),
            },
            # Pass through the declarative connection profile and runtime
            # constraints so the UI can render the right form (URL+email+
            # token for Atlassian, OAuth-only for hosted servers, etc.)
            # rather than falling back to a meaningless "Activate" button.
            "connection_profile": definition.get("connection_profile"),
            "runtime_constraints": list(definition.get("runtime_constraints") or []),
        }

    def _serialize_core_connection_payload(self, integration_id: str) -> dict[str, Any]:
        normalized = integration_id.strip().lower()
        definition = CORE_INTEGRATION_CATALOG.get(normalized)
        if definition is None:
            raise KeyError(normalized)
        row = self._integration_connection_row(normalized)
        metadata = (
            _safe_json_object(json_load(row.get("metadata_json"), {}))
            if row is not None and _row_has_column(row, "metadata_json")
            else {}
        )
        auth_method = self._resolve_integration_auth_mode(normalized)
        configured = (
            bool(int(row.get("configured") or 0))
            if row is not None and _row_has_column(row, "configured")
            else self._integration_configured(normalized)
        )
        verified = (
            bool(int(row.get("verified") or 0)) if row is not None and _row_has_column(row, "verified") else False
        )
        if not configured:
            verified = False
        status = self._integration_connection_status(
            {
                "configured": configured,
                "verified": verified,
                "last_error": _trimmed_text(row.get("last_error")) if row is not None else "",
            }
        )
        return {
            "connection_key": _core_connection_key(normalized),
            "kind": "core",
            "integration_key": normalized,
            "status": status,
            "transport_kind": str(definition.transport or "core"),
            "auth_strategy": auth_method,
            "auth_method": auth_method,
            "official_support_level": "core",
            "source_origin": "system_default",
            "account_label": _trimmed_text(row.get("account_label")) if row is not None else None,
            "provider_account_id": _nonempty_text(
                (
                    _trimmed_text(row.get("provider_account_id"))
                    if row is not None and _row_has_column(row, "provider_account_id")
                    else ""
                )
                or metadata.get("provider_account_id")
                or metadata.get("account")
                or metadata.get("account_id")
            )
            or None,
            "expires_at": (
                _trimmed_text(row.get("expires_at"))
                if row is not None and _row_has_column(row, "expires_at")
                else _nonempty_text(metadata.get("expires_at"))
            )
            or None,
            "last_verified_at": _trimmed_text(row.get("last_verified_at")) if row is not None else None,
            "last_error": _trimmed_text(row.get("last_error")) if row is not None else None,
            "tool_count": 0,
            "connected": configured,
            "enabled": configured,
            "fields": self._integration_fields_payload(normalized),
            "metadata": {
                **metadata,
                "verified": verified,
                "configured": configured,
                "supports_persistence": bool(definition.supports_persistence),
                "health_probe": str(definition.health_probe or ""),
            },
        }

    def _serialize_agent_core_connection_payload(self, agent_id: str, integration_id: str) -> dict[str, Any]:
        try:
            normalized_agent, _ = self._require_agent_row(agent_id)
            agent_exists = True
        except KeyError:
            normalized_agent = _normalize_agent_id(agent_id)
            agent_exists = False
        normalized = integration_id.strip().lower()
        definition = CORE_INTEGRATION_CATALOG.get(normalized)
        if definition is None:
            raise KeyError(normalized)
        row = self._core_agent_connection_row(normalized_agent, normalized) if agent_exists else None
        metadata = (
            _safe_json_object(json_load(row.get("metadata_json"), {}))
            if row is not None and _row_has_column(row, "metadata_json")
            else {}
        )
        auth_method = (
            self._resolve_agent_core_auth_method(normalized_agent, normalized)
            if agent_exists
            else (definition.auth_modes[0] if definition.auth_modes else "none")
        )
        enabled = bool(int(row.get("enabled") or 0)) if row is not None else False
        configured = (
            self._agent_core_connection_configured(normalized_agent, normalized)
            if row is not None and agent_exists
            else False
        )
        verified = bool(int(row.get("verified") or 0)) if row is not None else False
        if not enabled:
            verified = False
        source_origin = (
            _trimmed_text(row.get("source_origin")) if row is not None and _row_has_column(row, "source_origin") else ""
        )
        if not source_origin:
            source_origin = "local_session" if auth_method == "local_session" else "agent_binding"
        runtime_connected = bool(enabled and configured)
        payload = {
            "connection_key": _core_connection_key(normalized),
            "kind": "core",
            "integration_key": normalized,
            "status": self._integration_connection_status(
                {
                    "verified": verified and runtime_connected,
                    "configured": runtime_connected,
                    "last_error": _trimmed_text(row.get("last_error")) if row is not None else "",
                }
            ),
            "transport_kind": str(definition.transport or "core"),
            "auth_strategy": auth_method,
            "auth_method": auth_method,
            "official_support_level": "core",
            "source_origin": source_origin,
            "account_label": _trimmed_text(row.get("account_label")) if row is not None else None,
            "provider_account_id": (
                _trimmed_text(row.get("provider_account_id"))
                if row is not None and _row_has_column(row, "provider_account_id")
                else _nonempty_text(
                    metadata.get("provider_account_id") or metadata.get("account") or metadata.get("account_id")
                )
            )
            or None,
            "expires_at": (
                _trimmed_text(row.get("expires_at"))
                if row is not None and _row_has_column(row, "expires_at")
                else _nonempty_text(metadata.get("expires_at"))
            )
            or None,
            "last_verified_at": _trimmed_text(row.get("last_verified_at")) if row is not None else None,
            "last_error": _trimmed_text(row.get("last_error")) if row is not None else None,
            "tool_count": 0,
            "connected": runtime_connected,
            "enabled": enabled,
            "fields": self._agent_core_fields_payload(normalized_agent, normalized) if agent_exists else [],
            "metadata": {
                **metadata,
                "verified": verified,
                "configured": configured,
                "supports_persistence": bool(definition.supports_persistence),
                "health_probe": str(definition.health_probe or ""),
            },
        }
        return payload

    def resolve_agent_core_runtime_connection(self, agent_id: str, integration_id: str) -> dict[str, Any] | None:
        normalized_agent, _ = self._require_agent_row(agent_id)
        normalized = integration_id.strip().lower()
        definition = CORE_INTEGRATION_CATALOG.get(normalized)
        if definition is None:
            raise KeyError(normalized)
        row = self._core_agent_connection_row(normalized_agent, normalized)
        if row is None or not bool(int(row.get("enabled") or 0)):
            return None

        config_values = {
            str(key): _stringify_env_value(value)
            for key, value in self._agent_core_connection_config(normalized_agent, normalized).items()
            if _stringify_env_value(value).strip()
        }
        secret_refs: dict[str, str] = {}
        secret_values: dict[str, str] = {}
        template = _GENERAL_INTEGRATION_CREDENTIAL_TEMPLATES.get(normalized, {})
        for field in template.get("fields", ()):
            if str(field.get("storage") or "env") != "secret":
                continue
            secret_key = str(field.get("key") or "").strip().upper()
            if not secret_key:
                continue
            secret_refs[secret_key] = f"agent:{normalized_agent}:{secret_key}"
            value = self.get_decrypted_secret_value(normalized_agent, secret_key)
            if value:
                secret_values[secret_key] = value

        metadata = (
            _safe_json_object(json_load(row.get("metadata_json"), {})) if _row_has_column(row, "metadata_json") else {}
        )
        auth_method = self._resolve_agent_core_auth_method(normalized_agent, normalized)
        configured = self._agent_core_connection_configured(normalized_agent, normalized)
        connected = bool(configured and int(row.get("enabled") or 0))
        source_origin = _trimmed_text(row.get("source_origin")) or (
            "local_session" if auth_method == "local_session" else "agent_binding"
        )
        return {
            "agent_id": normalized_agent,
            "connection_key": _core_connection_key(normalized),
            "kind": "core",
            "integration_key": normalized,
            "auth_method": auth_method,
            "source_origin": source_origin,
            "status": self._integration_connection_status(
                {
                    "verified": bool(int(row.get("verified") or 0)) and connected,
                    "configured": connected,
                    "last_error": _trimmed_text(row.get("last_error")),
                }
            ),
            "connected": connected,
            "account_label": _trimmed_text(row.get("account_label")) or None,
            "provider_account_id": (
                _trimmed_text(row.get("provider_account_id"))
                or _nonempty_text(
                    metadata.get("provider_account_id") or metadata.get("account") or metadata.get("account_id")
                )
                or None
            ),
            "expires_at": _trimmed_text(row.get("expires_at")) or _nonempty_text(metadata.get("expires_at")) or None,
            "last_verified_at": _trimmed_text(row.get("last_verified_at")) or None,
            "last_error": _trimmed_text(row.get("last_error")) or None,
            "config_values": config_values,
            "secret_refs": secret_refs,
            "secret_values": secret_values,
            "metadata": metadata,
            "tool_policies": {},
        }

    def list_connection_catalog(self) -> dict[str, Any]:
        self.ensure_seeded()
        items = [self._serialize_core_catalog_entry(dict(item)) for item in resolve_core_integration_catalog()]
        items.extend(self._serialize_unified_mcp_catalog_entry(row) for row in self.list_mcp_catalog())
        return {
            "items": items,
            "governance": {
                "catalog_source": "backend",
                "default_policy": "always_ask",
            },
        }

    def list_connection_defaults(self) -> dict[str, Any]:
        self.ensure_seeded()
        items = [
            self._serialize_core_connection_payload(str(definition.get("id") or ""))
            for definition in resolve_core_integration_catalog()
        ]
        return {"items": items}

    def import_agent_connection_default(self, agent_id: str, connection_key: str) -> dict[str, Any]:
        kind, value = _parse_connection_key(connection_key)
        if kind != "core":
            raise ValueError("connection_defaults_supported_only_for_core")
        normalized_agent, _ = self._require_agent_row(agent_id)
        normalized = value.strip().lower()
        row = self._integration_connection_row(normalized)
        if row is None or not bool(int(row.get("configured") or 0)):
            raise ValueError("connection_default_not_configured")

        template = _GENERAL_INTEGRATION_CREDENTIAL_TEMPLATES.get(normalized, {})
        sections = self._system_settings_sections()
        import_fields: list[dict[str, Any]] = []
        for field in template.get("fields", ()):
            key = str(field.get("key") or "").strip().upper()
            if not key:
                continue
            if str(field.get("storage") or "env") == "secret":
                secret_row = fetch_one(
                    "SELECT encrypted_value FROM cp_secret_values WHERE scope_id = 'global' AND secret_key = ?",
                    (key,),
                )
                encrypted = _trimmed_text(secret_row["encrypted_value"]) if secret_row is not None else ""
                if encrypted:
                    import_fields.append({"key": key, "value": decrypt_secret(encrypted)})
                continue
            section_name = self._infer_section_from_env_key(key)
            section_payload = _safe_json_object(sections.get(section_name))
            env_map = _safe_json_object(section_payload.get("env"))
            value_text = _nonempty_text(env_map.get(key))
            if value_text:
                import_fields.append({"key": key, "value": value_text})

        config = self._persist_agent_core_connection_fields(normalized_agent, normalized, import_fields)
        metadata = (
            _safe_json_object(json_load(row.get("metadata_json"), {})) if _row_has_column(row, "metadata_json") else {}
        )
        auth_method = self._resolve_agent_core_auth_method(
            normalized_agent,
            normalized,
            requested_auth_method=_trimmed_text(row.get("auth_method") or row.get("auth_mode")),
        )
        source_origin = "local_session" if auth_method == "local_session" else "imported_default"
        if auth_method == "local_session":
            metadata["allow_local_session"] = bool(metadata.get("allow_local_session"))
        self._persist_core_agent_connection_row(
            normalized_agent,
            normalized,
            auth_method=auth_method,
            source_origin=source_origin,
            configured=(
                True
                if normalized == "browser"
                else self._agent_core_connection_configured(normalized_agent, normalized)
            ),
            verified=False,
            account_label="",
            provider_account_id="",
            expires_at="",
            last_verified_at="",
            last_error="",
            auth_expired=False,
            checked_via="",
            config=config,
            metadata=metadata,
            enabled=True,
        )
        return {"connection": self._serialize_agent_core_connection_payload(normalized_agent, normalized)}

    def list_agent_connections(self, agent_id: str) -> dict[str, Any]:
        self.ensure_seeded()
        items = [
            self._serialize_agent_core_connection_payload(agent_id, str(definition.get("id") or ""))
            for definition in resolve_core_integration_catalog()
        ]
        items.extend(self.list_mcp_agent_connections(agent_id))
        return {"items": items}

    def get_agent_connection(self, agent_id: str, connection_key: str) -> dict[str, Any]:
        kind, value = _parse_connection_key(connection_key)
        if kind == "core":
            return self._serialize_agent_core_connection_payload(agent_id, value)
        return self.get_mcp_agent_connection(agent_id, value)

    def put_agent_connection(self, agent_id: str, connection_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        kind, value = _parse_connection_key(connection_key)
        if kind == "core":
            normalized_agent, _ = self._require_agent_row(agent_id)
            normalized = value.strip().lower()
            definition = CORE_INTEGRATION_CATALOG.get(normalized)
            if definition is None:
                raise KeyError(normalized)
            request_payload = payload or {}
            existing_row = self._core_agent_connection_row(normalized_agent, normalized)
            existing_metadata = (
                _safe_json_object(json_load(existing_row.get("metadata_json"), {}))
                if existing_row is not None and _row_has_column(existing_row, "metadata_json")
                else {}
            )
            merged_metadata = {
                **existing_metadata,
                **_safe_json_object(request_payload.get("metadata")),
            }
            requested_auth_method = _trimmed_text(request_payload.get("auth_method")) or _trimmed_text(
                request_payload.get("auth_mode")
            )
            auth_method = self._resolve_agent_core_auth_method(
                normalized_agent,
                normalized,
                requested_auth_method=requested_auth_method,
            )
            if auth_method == "local_session":
                merged_metadata["allow_local_session"] = bool(
                    request_payload.get("allow_local_session", merged_metadata.get("allow_local_session", False))
                )
            updated_config = self._persist_agent_core_connection_fields(
                normalized_agent,
                normalized,
                _safe_json_list(request_payload.get("fields")),
            )
            enabled = bool(
                request_payload.get(
                    "enabled",
                    existing_row.get("enabled") if existing_row is not None else True,
                )
            )
            configured = enabled and (
                True
                if normalized == "browser"
                else self._agent_core_connection_configured(normalized_agent, normalized)
            )
            source_origin = str(request_payload.get("source_origin") or "").strip().lower()
            if auth_method == "local_session":
                source_origin = "local_session"
            elif not source_origin:
                if existing_row is not None and _row_has_column(existing_row, "source_origin"):
                    source_origin = _trimmed_text(existing_row.get("source_origin"))
                source_origin = source_origin or "agent_binding"
            self._persist_core_agent_connection_row(
                normalized_agent,
                normalized,
                auth_method=auth_method,
                source_origin=source_origin,
                configured=configured,
                verified=False,
                account_label="",
                provider_account_id="",
                expires_at="",
                last_verified_at="",
                last_error="",
                auth_expired=False,
                checked_via="",
                config=updated_config,
                metadata=merged_metadata,
                enabled=enabled,
            )
            return self._serialize_agent_core_connection_payload(normalized_agent, normalized)
        return self.upsert_mcp_agent_connection(agent_id, value, payload)

    def delete_agent_connection(self, agent_id: str, connection_key: str) -> dict[str, Any]:
        kind, value = _parse_connection_key(connection_key)
        if kind == "core":
            normalized_agent, _ = self._require_agent_row(agent_id)
            normalized = value.strip().lower()
            self._clear_agent_core_connection_fields(normalized_agent, normalized)
            execute(
                "DELETE FROM cp_agent_connections WHERE agent_id = ? AND connection_key = ?",
                (normalized_agent, _core_connection_key(normalized)),
            )
            return {"connection": self._serialize_agent_core_connection_payload(normalized_agent, normalized)}
        return self.delete_mcp_agent_connection(agent_id, value)

    def verify_agent_connection(self, agent_id: str, connection_key: str) -> dict[str, Any]:
        kind, value = _parse_connection_key(connection_key)
        if kind == "core":
            return self.verify_agent_core_connection(agent_id, value)
        return self.test_mcp_connection(agent_id, value)

    def _integration_connection_row(self, integration_id: str) -> Any:
        normalized = integration_id.strip().lower()
        try:
            return fetch_one(
                "SELECT * FROM cp_connection_defaults WHERE connection_key = ?",
                (_core_connection_key(normalized),),
            )
        except Exception:
            return None

    def _persist_integration_connection_row(
        self,
        integration_id: str,
        *,
        auth_mode: str,
        configured: bool,
        verified: bool,
        account_label: str = "",
        last_verified_at: str = "",
        last_error: str = "",
        auth_expired: bool = False,
        checked_via: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        normalized = integration_id.strip().lower()
        now = now_iso()
        metadata_json = json_dump(_safe_json_object(metadata))
        execute(
            """
            INSERT INTO cp_connection_defaults (
                connection_key,
                kind,
                integration_key,
                auth_method,
                configured,
                verified,
                account_label,
                provider_account_id,
                expires_at,
                source_origin,
                last_verified_at,
                last_error,
                auth_expired,
                checked_via,
                metadata_json,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(connection_key) DO UPDATE SET
                auth_method = excluded.auth_method,
                configured = excluded.configured,
                verified = excluded.verified,
                account_label = excluded.account_label,
                provider_account_id = excluded.provider_account_id,
                expires_at = excluded.expires_at,
                source_origin = excluded.source_origin,
                last_verified_at = excluded.last_verified_at,
                last_error = excluded.last_error,
                auth_expired = excluded.auth_expired,
                checked_via = excluded.checked_via,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                _core_connection_key(normalized),
                "core",
                normalized,
                auth_mode.strip() or "none",
                1 if configured else 0,
                1 if verified else 0,
                account_label.strip(),
                _nonempty_text(_safe_json_object(metadata).get("provider_account_id")),
                _nonempty_text(_safe_json_object(metadata).get("expires_at")),
                "system_default",
                last_verified_at.strip(),
                last_error.strip(),
                1 if auth_expired else 0,
                checked_via.strip(),
                metadata_json,
                now,
                now,
            ),
        )

    def _core_agent_connection_row(self, agent_id: str, integration_id: str) -> Any:
        normalized_agent, _ = self._require_agent_row(agent_id)
        normalized_integration = integration_id.strip().lower()
        return fetch_one(
            "SELECT * FROM cp_agent_connections WHERE agent_id = ? AND connection_key = ?",
            (normalized_agent, _core_connection_key(normalized_integration)),
        )

    def _persist_core_agent_connection_row(
        self,
        agent_id: str,
        integration_id: str,
        *,
        auth_method: str,
        source_origin: str,
        configured: bool,
        verified: bool,
        account_label: str = "",
        provider_account_id: str = "",
        expires_at: str = "",
        last_verified_at: str = "",
        last_error: str = "",
        auth_expired: bool = False,
        checked_via: str = "",
        config: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> None:
        normalized_agent, _ = self._require_agent_row(agent_id)
        normalized_integration = integration_id.strip().lower()
        normalized_origin = str(source_origin or "agent_binding").strip().lower() or "agent_binding"
        if normalized_origin not in _CORE_CONNECTION_SOURCE_ORIGINS:
            normalized_origin = "agent_binding"
        now = now_iso()
        execute(
            """
            INSERT INTO cp_agent_connections (
                agent_id,
                connection_key,
                kind,
                integration_key,
                auth_method,
                source_origin,
                enabled,
                configured,
                verified,
                account_label,
                provider_account_id,
                expires_at,
                last_verified_at,
                last_error,
                auth_expired,
                checked_via,
                config_json,
                metadata_json,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(agent_id, connection_key) DO UPDATE SET
                auth_method = excluded.auth_method,
                source_origin = excluded.source_origin,
                enabled = excluded.enabled,
                configured = excluded.configured,
                verified = excluded.verified,
                account_label = excluded.account_label,
                provider_account_id = excluded.provider_account_id,
                expires_at = excluded.expires_at,
                last_verified_at = excluded.last_verified_at,
                last_error = excluded.last_error,
                auth_expired = excluded.auth_expired,
                checked_via = excluded.checked_via,
                config_json = excluded.config_json,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                normalized_agent,
                _core_connection_key(normalized_integration),
                "core",
                normalized_integration,
                auth_method.strip() or "none",
                normalized_origin,
                1 if enabled else 0,
                1 if configured else 0,
                1 if verified else 0,
                account_label.strip(),
                provider_account_id.strip(),
                expires_at.strip(),
                last_verified_at.strip(),
                last_error.strip(),
                1 if auth_expired else 0,
                checked_via.strip(),
                json_dump(_safe_json_object(config)),
                json_dump(_safe_json_object(metadata)),
                now,
                now,
            ),
        )

    def _agent_secret_preview_state(self, agent_id: str, secret_key: str) -> tuple[bool, str]:
        secret = self.get_secret_asset(agent_id, secret_key, scope="agent")
        if secret is None:
            return False, ""
        preview = _nonempty_text(secret.get("preview")) or "Segredo configurado"
        return True, preview

    def _record_integration_health_check(self, integration_id: str, payload: dict[str, Any]) -> None:
        _ = (integration_id, payload)

    def _stored_global_secret_preview_state(self, secret_key: str) -> tuple[bool, str]:
        secret = self.get_global_secret_asset(secret_key)
        if secret is None:
            return False, ""
        preview = _nonempty_text(secret.get("preview")) or "Segredo configurado"
        return True, preview

    def _stored_global_secret_value(self, secret_key: str) -> str:
        secret = self.get_global_secret_asset(secret_key)
        if secret is None:
            return ""
        return _nonempty_text(secret.get("value"))

    def _global_secret_value(self, secret_key: str) -> str:
        normalized_secret_key = _normalize_secret_key(secret_key)
        row = fetch_one(
            "SELECT encrypted_value FROM cp_secret_values WHERE scope_id = 'global' AND secret_key = ?",
            (normalized_secret_key,),
        )
        if row is not None:
            encrypted = _trimmed_text(row["encrypted_value"])
            if encrypted:
                return decrypt_secret(encrypted)
        return _trimmed_text(os.environ.get(normalized_secret_key))

    def _system_default_connection_config(self, integration_id: str) -> dict[str, str]:
        normalized = integration_id.strip().lower()
        template = _GENERAL_INTEGRATION_CREDENTIAL_TEMPLATES.get(normalized)
        if template is None:
            return {}
        sections = self._system_settings_sections()
        values: dict[str, str] = {}
        for field in template["fields"]:
            if str(field.get("storage") or "env") == "secret":
                continue
            key = str(field.get("key") or "").strip().upper()
            if not key:
                continue
            section_name = self._infer_section_from_env_key(key)
            section_payload = _safe_json_object(sections.get(section_name))
            env_map = _safe_json_object(section_payload.get("env"))
            value = _nonempty_text(env_map.get(key))
            if value:
                values[key] = value
        return values

    def _integration_fields_payload(self, integration_id: str) -> list[dict[str, Any]]:
        normalized = integration_id.strip().lower()
        template = _GENERAL_INTEGRATION_CREDENTIAL_TEMPLATES.get(normalized)
        if template is None:
            return []
        config = self._system_default_connection_config(normalized)
        payload: list[dict[str, Any]] = []
        for field in template["fields"]:
            entry = dict(field)
            key = str(field["key"])
            if str(field.get("storage") or "env") == "secret":
                value_present, _preview = self._stored_global_secret_preview_state(key)
                payload.append(
                    {
                        **entry,
                        "value": "",
                        # Preview intentionally stripped — UI only shows
                        # "configured" / replace actions, never the value.
                        "preview": "",
                        "value_present": value_present,
                        "usage_scope": "system_only",
                    }
                )
                continue
            payload.append(
                {
                    **entry,
                    "value": _trimmed_text(config.get(key)),
                }
            )
        return payload

    def _agent_core_connection_config(self, agent_id: str, integration_id: str) -> dict[str, Any]:
        row = self._core_agent_connection_row(agent_id, integration_id)
        if row is None:
            return {}
        return _safe_json_object(json_load(row.get("config_json"), {}))

    def _agent_core_fields_payload(self, agent_id: str, integration_id: str) -> list[dict[str, Any]]:
        normalized = integration_id.strip().lower()
        template = _GENERAL_INTEGRATION_CREDENTIAL_TEMPLATES.get(normalized)
        if template is None:
            return []
        config = self._agent_core_connection_config(agent_id, normalized)
        payload: list[dict[str, Any]] = []
        for field in template["fields"]:
            entry = dict(field)
            key = str(field["key"])
            storage = str(field.get("storage") or "env")
            if storage == "secret":
                value_present, _preview = self._agent_secret_preview_state(agent_id, key)
                payload.append(
                    {
                        **entry,
                        "value": "",
                        # Preview stripped — per-agent integrations follow
                        # the same "no preview, replace-only" rule.
                        "preview": "",
                        "value_present": value_present,
                        "usage_scope": "agent_only",
                    }
                )
                continue
            payload.append({**entry, "value": _trimmed_text(config.get(key))})
        return payload

    def _persist_agent_core_connection_fields(
        self,
        agent_id: str,
        integration_id: str,
        payload_fields: list[dict[str, Any]],
    ) -> dict[str, Any]:
        normalized_agent, _ = self._require_agent_row(agent_id)
        normalized_integration = integration_id.strip().lower()
        template = _GENERAL_INTEGRATION_CREDENTIAL_TEMPLATES.get(normalized_integration)
        if template is None:
            return self._agent_core_connection_config(normalized_agent, normalized_integration)
        row = self._core_agent_connection_row(normalized_agent, normalized_integration)
        config = _safe_json_object(json_load(row.get("config_json"), {})) if row is not None else {}
        provided_fields = {
            str(_safe_json_object(field).get("key") or ""): _safe_json_object(field)
            for field in payload_fields
            if str(_safe_json_object(field).get("key") or "")
        }
        for field in template["fields"]:
            key = str(field["key"])
            entry = provided_fields.get(key)
            if entry is None:
                continue
            clear = bool(entry.get("clear"))
            value = _nonempty_text(entry.get("value"))
            storage = str(field.get("storage") or "env")
            if storage == "secret":
                if clear:
                    self.delete_secret_asset(normalized_agent, key)
                elif value:
                    self.upsert_secret_asset(normalized_agent, key, {"value": value})
                continue
            if clear:
                config.pop(key, None)
            elif value:
                config[key] = value
        return config

    def _clear_agent_core_connection_fields(self, agent_id: str, integration_id: str) -> None:
        normalized = integration_id.strip().lower()
        template = _GENERAL_INTEGRATION_CREDENTIAL_TEMPLATES.get(normalized)
        if template is None:
            return
        for field in template["fields"]:
            key = str(field["key"])
            if str(field.get("storage") or "env") == "secret":
                self.delete_secret_asset(agent_id, key)

    def _resolve_agent_core_auth_method(
        self,
        agent_id: str,
        integration_id: str,
        *,
        requested_auth_method: str | None = None,
    ) -> str:
        normalized = integration_id.strip().lower()
        definition = CORE_INTEGRATION_CATALOG.get(normalized)
        if definition is None:
            raise KeyError(normalized)
        supported_modes = {str(mode).strip().lower() for mode in definition.auth_modes}
        raw_requested = str(requested_auth_method or "").strip().lower()
        requested = _CORE_LEGACY_AUTH_MODE_ALIASES.get(raw_requested, raw_requested)
        if requested and requested in supported_modes:
            return requested
        row = self._core_agent_connection_row(agent_id, normalized)
        persisted_raw = _trimmed_text(row.get("auth_method") if row is not None else "").lower()
        persisted = _CORE_LEGACY_AUTH_MODE_ALIASES.get(persisted_raw, persisted_raw)
        config = self._agent_core_connection_config(agent_id, normalized)
        if normalized == "browser":
            return "none"
        _ = config
        if persisted in supported_modes:
            return persisted
        return definition.auth_modes[0] if definition.auth_modes else "none"

    def _agent_core_connection_configured(self, agent_id: str, integration_id: str) -> bool:
        normalized = integration_id.strip().lower()
        definition = CORE_INTEGRATION_CATALOG.get(normalized)
        if definition is None:
            raise KeyError(normalized)
        row = self._core_agent_connection_row(agent_id, normalized)
        if normalized == "browser":
            return bool(row and int(row.get("configured") or 0))
        config = self._agent_core_connection_config(agent_id, normalized)
        auth_method = self._resolve_agent_core_auth_method(agent_id, normalized)
        _ = (config, auth_method)
        return bool(row)

    def _resolve_integration_auth_mode(
        self,
        integration_id: str,
        *,
        requested_auth_mode: str | None = None,
    ) -> str:
        normalized = integration_id.strip().lower()
        definition = CORE_INTEGRATION_CATALOG.get(normalized)
        if definition is None:
            raise KeyError(normalized)
        supported_modes = {mode.strip().lower() for mode in definition.auth_modes}
        requested = _nonempty_text(requested_auth_mode).lower()
        if requested and requested in supported_modes:
            return requested

        row = self._integration_connection_row(normalized)
        persisted_raw_auth_method = (
            _trimmed_text(row.get("auth_method")).lower()
            if row is not None and _row_has_column(row, "auth_method")
            else ""
        )
        persisted_auth_mode = _CORE_LEGACY_AUTH_MODE_ALIASES.get(
            persisted_raw_auth_method,
            persisted_raw_auth_method,
        )
        config = self._system_default_connection_config(normalized)
        if normalized == "browser":
            return "none"
        _ = config
        if persisted_auth_mode in supported_modes:
            return persisted_auth_mode
        return definition.auth_modes[0] if definition.auth_modes else "none"

    def _persist_integration_credential_fields(self, integration_id: str, payload_fields: list[dict[str, Any]]) -> None:
        normalized = integration_id.strip().lower()
        template = _GENERAL_INTEGRATION_CREDENTIAL_TEMPLATES.get(normalized)
        if template is None:
            return
        provided_fields = {
            str(_safe_json_object(field).get("key") or ""): _safe_json_object(field)
            for field in payload_fields
            if str(_safe_json_object(field).get("key") or "")
        }
        sections = self._system_settings_sections()
        access_section = dict(self._access_section(sections))
        system_env_meta = dict(self._access_meta_map("system_env_meta", sections=sections))
        global_secret_meta = dict(self._access_meta_map("global_secret_meta", sections=sections))

        for field in template["fields"]:
            env_key = str(field["key"])
            entry = provided_fields.get(env_key)
            if entry is None:
                continue
            clear = bool(entry.get("clear"))
            value = _nonempty_text(entry.get("value"))
            storage = str(field.get("storage") or "env")
            title = str(template["title"])

            if storage == "secret":
                if clear:
                    global_secret_meta.pop(env_key, None)
                    self.delete_global_secret_asset(env_key, persist_sections=False)
                    continue
                if not value:
                    continue
                global_secret_meta[env_key] = {
                    "description": f"Credencial global de {title}",
                    "usage_scope": "system_only",
                }
                self.upsert_global_secret_asset(
                    env_key,
                    {
                        "value": value,
                        "description": f"Credencial global de {title}",
                        "usage_scope": "system_only",
                    },
                    persist_sections=False,
                )
                continue

            section_name = self._infer_section_from_env_key(env_key)
            section_payload = dict(_safe_json_object(sections.get(section_name)))
            env_map = dict(_safe_json_object(section_payload.get("env")))
            if clear:
                env_map.pop(env_key, None)
                system_env_meta.pop(env_key, None)
            elif value:
                env_map[env_key] = value
                system_env_meta[env_key] = {"description": f"Global configuration for {title}"}
            if env_map:
                section_payload["env"] = env_map
            else:
                section_payload.pop("env", None)
            sections[section_name] = section_payload

        if global_secret_meta:
            access_section["global_secret_meta"] = global_secret_meta
        else:
            access_section.pop("global_secret_meta", None)
        if system_env_meta:
            access_section["system_env_meta"] = system_env_meta
        else:
            access_section.pop("system_env_meta", None)
        sections["access"] = access_section
        self._persist_global_sections(sections)

    def _clear_integration_credential_fields(self, integration_id: str) -> None:
        normalized = integration_id.strip().lower()
        template = _GENERAL_INTEGRATION_CREDENTIAL_TEMPLATES.get(normalized)
        if template is None:
            return
        self._persist_integration_credential_fields(
            normalized,
            [{"key": str(field["key"]), "clear": True} for field in template["fields"]],
        )

    def _integration_configured(self, integration_id: str) -> bool:
        normalized = integration_id.strip().lower()
        row = self._integration_connection_row(normalized)
        fields = {
            str(item.get("key") or ""): _safe_json_object(item) for item in self._integration_fields_payload(normalized)
        }
        template = _GENERAL_INTEGRATION_CREDENTIAL_TEMPLATES.get(normalized)
        if template is None:
            if normalized == "browser":
                if row is None:
                    return False
                return bool(int(row["configured"] or 0))
            return True
        for field in template["fields"]:
            if not bool(field.get("required")):
                continue
            key = str(field["key"])
            if str(field.get("storage") or "env") == "secret":
                if not self._stored_global_secret_value(key):
                    return False
                continue
            if not _nonempty_text(fields.get(key, {}).get("value")):
                return False
        return True

    def _integration_connection_status(self, payload: dict[str, Any]) -> str:
        if bool(payload.get("verified")):
            return "verified"
        if bool(payload.get("configured")):
            return "configured"
        if _nonempty_text(payload.get("last_error")):
            return "error"
        return "not_configured"

    def get_connection_default(self, connection_key: str) -> dict[str, Any]:
        kind, value = _parse_connection_key(connection_key)
        if kind != "core":
            raise KeyError(connection_key)
        return self._serialize_core_connection_payload(value)

    def put_connection_default(self, connection_key: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        kind, value = _parse_connection_key(connection_key)
        if kind != "core":
            raise KeyError(connection_key)
        normalized = value.strip().lower()
        definition = CORE_INTEGRATION_CATALOG.get(normalized)
        if definition is None:
            raise KeyError(normalized)
        request_payload = payload or {}
        self._persist_integration_credential_fields(normalized, _safe_json_list(request_payload.get("fields")))
        configured = self._integration_configured(normalized)
        if normalized == "browser" and not configured:
            configured = True
        auth_method = self._resolve_integration_auth_mode(
            normalized,
            requested_auth_mode=_trimmed_text(
                request_payload.get("auth_method") or request_payload.get("auth_strategy")
            ),
        )
        self._persist_integration_connection_row(
            normalized,
            auth_mode=auth_method,
            configured=configured,
            verified=False,
            account_label="",
            last_verified_at="",
            last_error="",
            auth_expired=False,
            checked_via="",
            metadata=_safe_json_object(request_payload.get("metadata")),
        )
        return self.get_connection_default(connection_key)

    def delete_connection_default(self, connection_key: str) -> dict[str, Any]:
        kind, value = _parse_connection_key(connection_key)
        if kind != "core":
            raise KeyError(connection_key)
        normalized = value.strip().lower()
        definition = CORE_INTEGRATION_CATALOG.get(normalized)
        if definition is None:
            raise KeyError(normalized)
        self._clear_integration_credential_fields(normalized)
        self._persist_integration_connection_row(
            normalized,
            auth_mode=definition.auth_modes[0] if definition.auth_modes else "none",
            configured=False,
            verified=False,
            account_label="",
            last_verified_at="",
            last_error="",
            auth_expired=False,
            checked_via="",
            metadata={},
        )
        return {"connection": self.get_connection_default(connection_key)}

    def set_integration_system_enabled(self, integration_id: str, enabled: bool) -> dict[str, Any]:
        normalized = integration_id.strip().lower()
        payload = dict(self.get_system_settings())
        integrations = dict(_safe_json_object(payload.get("integrations")))
        integrations[f"{normalized}_enabled"] = bool(enabled)
        payload["integrations"] = integrations
        sections = self._apply_system_settings_to_sections(payload)
        self._persist_global_sections(sections)
        return {
            "integration_id": normalized,
            "enabled": bool(enabled),
            "connection": self.get_connection_default(_core_connection_key(normalized)),
        }

    def _verify_agent_core_connection_configuration(self, agent_id: str, integration_id: str) -> dict[str, Any]:
        normalized_agent, _ = self._require_agent_row(agent_id)
        normalized = integration_id.strip().lower()
        row = self._core_agent_connection_row(normalized_agent, normalized)
        if row is None or not bool(int(row.get("enabled") or 0)):
            return {
                "verified": False,
                "account_label": "",
                "last_error": f"{normalized} connection is not enabled for this agent.",
                "checked_via": "agent_binding",
                "auth_expired": False,
                "details": {"auth_method": self._resolve_agent_core_auth_method(normalized_agent, normalized)},
            }

        if normalized == "browser":
            return {
                "verified": self._agent_core_connection_configured(normalized_agent, normalized),
                "account_label": "",
                "last_error": "",
                "checked_via": "agent_binding",
                "auth_expired": False,
                "details": {"auth_method": "none"},
            }

        return {
            "verified": self._agent_core_connection_configured(normalized_agent, normalized),
            "account_label": "",
            "last_error": "",
            "checked_via": "agent_binding",
            "auth_expired": False,
            "details": {"auth_method": self._resolve_agent_core_auth_method(normalized_agent, normalized)},
        }

    def verify_agent_core_connection(self, agent_id: str, integration_id: str) -> dict[str, Any]:
        normalized_agent, _ = self._require_agent_row(agent_id)
        normalized = integration_id.strip().lower()
        row = self._core_agent_connection_row(normalized_agent, normalized)
        if row is None:
            raise KeyError(_core_connection_key(normalized))
        result = self._verify_agent_core_connection_configuration(normalized_agent, normalized)
        existing_metadata = (
            _safe_json_object(json_load(row.get("metadata_json"), {})) if _row_has_column(row, "metadata_json") else {}
        )
        merged_metadata = {
            **existing_metadata,
            **_safe_json_object(result.get("details")),
        }
        auth_method = self._resolve_agent_core_auth_method(normalized_agent, normalized)
        source_origin = _trimmed_text(row.get("source_origin")) or (
            "local_session" if auth_method == "local_session" else "agent_binding"
        )
        self._persist_core_agent_connection_row(
            normalized_agent,
            normalized,
            auth_method=auth_method,
            source_origin=source_origin,
            configured=self._agent_core_connection_configured(normalized_agent, normalized),
            verified=bool(result.get("verified")),
            account_label=_nonempty_text(result.get("account_label")),
            provider_account_id=_nonempty_text(
                _safe_json_object(result.get("details")).get("provider_account_id")
                or _safe_json_object(result.get("details")).get("account")
                or _safe_json_object(result.get("details")).get("account_id")
            ),
            expires_at=_nonempty_text(_safe_json_object(result.get("details")).get("expires_at")),
            last_verified_at=now_iso() if bool(result.get("verified")) else "",
            last_error=_nonempty_text(result.get("last_error")),
            auth_expired=bool(result.get("auth_expired")),
            checked_via=_nonempty_text(result.get("checked_via")),
            config=self._agent_core_connection_config(normalized_agent, normalized),
            metadata=merged_metadata,
            enabled=bool(int(row.get("enabled") or 0)),
        )
        return {
            "connection": self._serialize_agent_core_connection_payload(normalized_agent, normalized),
            "verification": result,
        }

    def _verify_integration_configuration(self, integration_id: str) -> dict[str, Any]:
        normalized = integration_id.strip().lower()
        return {
            "verified": self._integration_configured(normalized),
            "account_label": "",
            "last_error": "",
            "checked_via": "static",
            "auth_expired": False,
            "details": {},
        }

    def verify_connection_default(self, connection_key: str) -> dict[str, Any]:
        kind, value = _parse_connection_key(connection_key)
        if kind != "core":
            raise KeyError(connection_key)
        normalized = value.strip().lower()
        result = self._verify_integration_configuration(normalized)
        self._record_integration_health_check(normalized, result)
        self._persist_integration_connection_row(
            normalized,
            auth_mode=self._resolve_integration_auth_mode(
                normalized,
                requested_auth_mode=_trimmed_text(self.get_connection_default(connection_key).get("auth_method")),
            ),
            configured=self._integration_configured(normalized),
            verified=bool(result.get("verified")),
            account_label=_nonempty_text(result.get("account_label")),
            last_verified_at=now_iso() if bool(result.get("verified")) else "",
            last_error=_nonempty_text(result.get("last_error")),
            auth_expired=bool(result.get("auth_expired")),
            checked_via=_nonempty_text(result.get("checked_via")),
            metadata=_safe_json_object(result.get("details")),
        )
        return {
            "connection": self.get_connection_default(connection_key),
            "verification": result,
        }

    def get_core_tools(self) -> dict[str, Any]:
        env = self._merged_global_env()
        return {
            "items": resolve_feature_filtered_tools(self._feature_flags_from_env(env)),
            "governance": {
                "ownership": "core",
                "agent_control": "subset_only",
            },
        }

    def get_core_providers(self) -> dict[str, Any]:
        env = self._merged_global_env()
        catalog = self._provider_catalog_from_env(env)
        for provider_id, payload in _safe_json_object(catalog.get("providers")).items():
            if provider_id in MANAGED_PROVIDER_IDS:
                # Fetch the connection defensively — ``_provider_connection_row``
                # raises ``KeyError`` when the row hasn't been seeded yet
                # (fresh install, migration race). Treat a missing row as
                # "not configured" rather than letting the KeyError bubble up
                # into ``control_plane_error_middleware`` where it would turn
                # a valid endpoint into a bogus 404.
                try:
                    connection = self.get_provider_connection(provider_id)
                except KeyError:
                    connection = {
                        "provider_id": provider_id,
                        "auth_mode": "api_key",
                        "configured": False,
                        "verified": False,
                        "connection_status": {"state": "not_configured"},
                    }
                payload["connection_status"] = connection.get("connection_status")
                payload["connection"] = connection
                # Add extra models when using API key authentication
                auth_mode = str(connection.get("auth_mode") or "").strip().lower()
                if auth_mode == "api_key":
                    from koda.provider_models import resolve_api_key_extra_model_ids

                    extra = resolve_api_key_extra_model_ids(provider_id)
                    if extra:
                        current = payload.get("available_models") or []
                        payload["available_models"] = list(dict.fromkeys(current + extra))
            whisper_catalog_items: list[dict[str, Any]] | None = None
            if provider_id == "whispercpp":
                whisper_catalog_items, downloaded_models, whisper_default_model = _downloaded_whisper_catalog_models(
                    whisper_catalog_payload()
                )
                payload["available_models"] = downloaded_models
                payload["default_model"] = whisper_default_model
            payload["functional_models"] = resolve_provider_function_model_catalog(
                provider_id,
                available_models=[str(item) for item in _safe_json_object(payload).get("available_models") or []],
                whisper_catalog_items=whisper_catalog_items,
            )
        catalog["model_functions"] = resolve_model_function_catalog()
        catalog["functional_model_catalog"] = self._functional_model_catalog(catalog)
        catalog["governance"] = {
            "ownership": "core",
            "agent_control": "envelope_only",
            "source_of_truth": "provider_runtime_registry",
        }
        return catalog

    def _database_health_payload(self) -> dict[str, Any]:
        if not KNOWLEDGE_V2_POSTGRES_DSN.strip():
            return {
                "enabled": False,
                "ready": False,
                "reason": "postgres_dsn_missing",
            }
        backend = get_shared_postgres_backend(
            agent_id="CONTROL_PLANE",
            dsn=KNOWLEDGE_V2_POSTGRES_DSN,
            schema=KNOWLEDGE_V2_POSTGRES_SCHEMA,
            embedding_dimension=KNOWLEDGE_V2_EMBEDDING_DIMENSION,
        )
        try:
            bootstrapped = bool(run_coro_sync(backend.bootstrap()))
            health = dict(run_coro_sync(backend.health()))
        except Exception as exc:
            return {
                "enabled": True,
                "ready": False,
                "reason": str(exc),
            }
        return {
            "enabled": True,
            "ready": bool(health.get("ready")) and bootstrapped,
            "bootstrap_state": health.get("bootstrap_state"),
            "reason": health.get("error") or health.get("reason"),
        }

    def _object_storage_health_payload(self) -> dict[str, Any]:
        support = V2StoreSupport(
            agent_id="CONTROL_PLANE",
            storage_mode=self._merged_global_env().get("KNOWLEDGE_V2_STORAGE_MODE", "primary"),
        )
        return dict(support.object_store_health())

    def get_onboarding_status(self) -> dict[str, Any]:
        self.ensure_seeded()
        provider_catalog = self.get_core_providers()
        system_settings = self.get_system_settings()
        merged_env = self._merged_global_env()
        database = self._database_health_payload()
        object_storage = self._object_storage_health_payload()
        providers = [
            {
                "provider_id": str(provider_id),
                "title": str(_safe_json_object(payload).get("title") or provider_id),
                "supported_auth_modes": list(_safe_json_object(payload).get("supported_auth_modes") or []),
                "configured": bool(_safe_json_object(_safe_json_object(payload).get("connection")).get("configured")),
                "verified": bool(_safe_json_object(_safe_json_object(payload).get("connection")).get("verified")),
                "connection_status": _safe_json_object(_safe_json_object(payload).get("connection")) or {},
            }
            for provider_id, payload in _safe_json_object(provider_catalog.get("providers")).items()
        ]
        allowed_user_ids = _normalize_user_id_values(merged_env.get("ALLOWED_USER_IDS", ""))
        agent_summaries: list[dict[str, Any]] = []
        for agent in self.list_agents():
            agent_id = str(agent["id"])
            secret_present = self.get_secret_asset(agent_id, "AGENT_TOKEN", scope="agent") is not None
            agent_summaries.append(
                {
                    "id": agent_id,
                    "display_name": str(agent.get("display_name") or agent_id),
                    "status": str(agent.get("status") or "paused"),
                    "telegram_token_configured": secret_present,
                    "desired_version": agent.get("desired_version"),
                    "applied_version": agent.get("applied_version"),
                }
            )
        provider_ready = any(bool(item.get("verified")) for item in providers)
        agent_ready = any(bool(item.get("telegram_token_configured")) for item in agent_summaries)
        return {
            "control_plane": {
                "ready": True,
            },
            "storage": {
                "database": database,
                "object_storage": object_storage,
            },
            "providers": providers,
            "agents": agent_summaries,
            "system": {
                "owner_name": _safe_json_object(_safe_json_object(system_settings.get("values")).get("account")).get(
                    "owner_name"
                ),
                "owner_email": _safe_json_object(_safe_json_object(system_settings.get("values")).get("account")).get(
                    "owner_email"
                ),
                "owner_github": _safe_json_object(_safe_json_object(system_settings.get("values")).get("account")).get(
                    "owner_github"
                ),
                "default_provider": _safe_json_object(
                    _safe_json_object(system_settings.get("values")).get("models")
                ).get("default_provider"),
                "allowed_user_ids": allowed_user_ids,
            },
            "steps": {
                "provider_configured": provider_ready,
                "access_configured": bool(allowed_user_ids),
                "agent_ready": agent_ready,
                "storage_ready": bool(database.get("ready")) and bool(object_storage.get("ready")),
                "onboarding_complete": bool(database.get("ready"))
                and bool(object_storage.get("ready"))
                and provider_ready
                and bool(allowed_user_ids)
                and agent_ready,
            },
            "openapi_url": "/openapi/control-plane.json",
            "setup_url": "/setup",
        }

    def get_channel_gateway_state(self, agent_id: str) -> dict[str, Any]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        from koda.channels.gateway import gateway_state

        allowed_raw = self.get_decrypted_secret_value(normalized, "ALLOWED_USER_IDS") or ""
        return gateway_state(
            normalized,
            legacy_allowed_user_ids=[str(item) for item in _normalize_user_id_values(allowed_raw)],
        )

    def create_channel_gateway_pairing_code(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        from koda.channels.gateway import create_pairing_code

        ttl_seconds = int(payload.get("ttl_seconds") or 15 * 60)
        return create_pairing_code(
            normalized,
            channel_type=str(payload.get("channel_type") or "telegram"),
            created_by=str(payload.get("created_by") or ""),
            ttl_seconds=ttl_seconds,
        )

    def list_channel_gateway_unknown_senders(self, agent_id: str) -> dict[str, Any]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        from koda.channels.gateway import CHANNEL_GATEWAY_SCHEMA_VERSION, list_unknown_senders

        return {
            "schema_version": CHANNEL_GATEWAY_SCHEMA_VERSION,
            "agent_id": normalized,
            "items": list_unknown_senders(normalized),
        }

    def approve_channel_gateway_identity(
        self,
        agent_id: str,
        identity_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        from koda.channels.gateway import approve_identity

        return {
            "schema_version": "channel_gateway.v1",
            "identity": approve_identity(
                normalized,
                identity_id,
                approved_by=str(payload.get("approved_by") or ""),
                rationale=str(payload.get("rationale") or ""),
            ),
        }

    def block_channel_gateway_identity(
        self,
        agent_id: str,
        identity_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        from koda.channels.gateway import block_identity

        return {
            "schema_version": "channel_gateway.v1",
            "identity": block_identity(
                normalized,
                identity_id,
                blocked_by=str(payload.get("blocked_by") or ""),
                rationale=str(payload.get("rationale") or ""),
            ),
        }

    def revoke_channel_gateway_identity(
        self,
        agent_id: str,
        identity_id: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        from koda.channels.gateway import revoke_identity

        request_payload = payload or {}
        return {
            "schema_version": "channel_gateway.v1",
            "identity": revoke_identity(
                normalized,
                identity_id,
                revoked_by=str(request_payload.get("revoked_by") or ""),
                rationale=str(request_payload.get("rationale") or ""),
            ),
        }

    def get_onboarding_readiness(self) -> dict[str, Any]:
        from koda.services.onboarding_readiness import build_onboarding_readiness

        status = self.get_onboarding_status()
        agents = [dict(item) for item in status.get("agents") or [] if isinstance(item, dict)]
        primary_agent_id = str((agents[0] if agents else {}).get("id") or "")
        channel_gateway = self.get_channel_gateway_state(primary_agent_id) if primary_agent_id else None
        release_quality = None
        if primary_agent_id:
            try:
                release_quality = self.get_release_quality_latest(primary_agent_id)
            except Exception:
                release_quality = None
        payload = build_onboarding_readiness(
            status=status,
            channel_gateway=channel_gateway,
            release_quality=release_quality,
        )
        self._persist_onboarding_readiness(payload)
        return payload

    def create_onboarding_first_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        status = self.get_onboarding_status()
        agents = [dict(item) for item in status.get("agents") or [] if isinstance(item, dict)]
        requested_agent = str(payload.get("agent_id") or "").strip()
        agent_id = requested_agent or str((agents[0] if agents else {}).get("id") or "")
        if not agent_id:
            raise ValueError("no agent is available for first task")
        text = str(payload.get("text") or "Summarize the Koda setup status and list the next safe action.").strip()
        session_id = str(payload.get("session_id") or "onboarding:first-task").strip()
        result = self.send_dashboard_session_message(agent_id, text=text, session_id=session_id)
        return {
            "schema_version": "onboarding_readiness.v1",
            "agent_id": _normalize_agent_id(agent_id),
            "status": "created",
            "task_id": result.get("task_id"),
            "session_id": result.get("session_id") or session_id,
            "result": result,
        }

    def _persist_onboarding_readiness(self, payload: dict[str, Any]) -> None:
        agent_id = str(payload.get("primary_agent_id") or payload.get("agent_id") or "default")
        try:
            from koda.state.primary import get_primary_state_backend, run_coro_sync

            backend = get_primary_state_backend(agent_id=agent_id)
            if backend is not None and hasattr(backend, "persist_onboarding_readiness_run"):
                run_coro_sync(backend.persist_onboarding_readiness_run(agent_id, payload))
        except Exception:
            log.debug("onboarding_readiness_primary_persist_skipped", exc_info=True)

    def complete_onboarding(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_seeded()
        account = _safe_json_object(payload.get("account"))
        access = _safe_json_object(payload.get("access"))
        provider = _safe_json_object(payload.get("provider"))
        agent_payload = _safe_json_object(payload.get("agent"))

        provider_id = _nonempty_text(provider.get("provider_id")).lower()
        if not provider_id:
            raise ValueError("provider_id is required")
        auth_mode = _nonempty_text(provider.get("auth_mode")).lower() or "api_key"
        if auth_mode == "local":
            self.put_provider_local_connection(
                provider_id,
                {
                    "base_url": _nonempty_text(provider.get("base_url")),
                },
            )
        elif auth_mode == "api_key":
            self.put_provider_api_key_connection(
                provider_id,
                {
                    "api_key": _nonempty_text(provider.get("api_key")),
                    "project_id": _nonempty_text(provider.get("project_id")),
                    "base_url": _nonempty_text(provider.get("base_url")),
                },
            )
        else:
            raise ValueError("onboarding currently supports api_key and local auth modes")

        verified_provider = self.verify_provider_connection(provider_id)
        if not bool(verified_provider.get("verified")):
            raise ValueError(
                str(verified_provider.get("last_error") or "provider verification failed; check credentials or URL")
            )

        variables: list[dict[str, str]] = []
        allowed_user_ids = _normalize_user_id_values(access.get("allowed_user_ids"))
        if allowed_user_ids:
            joined = ",".join(allowed_user_ids)
            variables.append({"key": "ALLOWED_USER_IDS", "value": joined, "type": "string", "scope": "system_only"})
            variables.append(
                {
                    "key": "KNOWLEDGE_ADMIN_USER_IDS",
                    "value": joined,
                    "type": "string",
                    "scope": "system_only",
                }
            )

        account_payload = {
            key: value
            for key, value in {
                "owner_name": _nonempty_text(account.get("owner_name")),
                "owner_email": _nonempty_text(account.get("owner_email")),
                "owner_github": _nonempty_text(account.get("owner_github")),
            }.items()
            if value
        }
        self.put_general_system_settings(
            {
                "account": account_payload,
                "models": {
                    "providers_enabled": [provider_id],
                    "default_provider": provider_id,
                    "fallback_order": [provider_id],
                },
                "variables": variables,
            }
        )

        created_agent: dict[str, Any] | None = None
        telegram_token = _nonempty_text(agent_payload.get("telegram_token"))
        agent_id_value = _nonempty_text(agent_payload.get("agent_id")) or "AGENT_A"
        display_name = _nonempty_text(agent_payload.get("display_name")) or agent_id_value
        if telegram_token:
            created_agent = self.get_agent(agent_id_value)
            if created_agent is None:
                created_agent = self.create_agent(
                    {
                        "id": agent_id_value,
                        "display_name": display_name,
                        "status": "paused",
                    }
                )
            else:
                created_agent = self.update_agent(agent_id_value, {"display_name": display_name})
            self.upsert_secret_asset(agent_id_value, "AGENT_TOKEN", {"value": telegram_token})
            self.publish_agent(agent_id_value)
            created_agent = self.activate_agent(agent_id_value)

        return {
            "ok": True,
            "provider": self.get_provider_connection(provider_id),
            "agent": created_agent,
            "status": self.get_onboarding_status(),
        }

    def get_core_policies(self) -> dict[str, Any]:
        return {
            "autonomy": {
                "default_mode": "guarded",
                "allowed_approval_modes": sorted(["guarded", "read_only", "escalation_required", "supervised"]),
                "allowed_autonomy_tiers": sorted(["t0", "t1", "t2"]),
                "deploy_requires_explicit_approval": True,
            },
            "knowledge": {
                "promotion_mode": "review_queue",
                "auto_promote_canonical": False,
                "runbook_governance": True,
            },
            "publish": {
                "requires_validation": True,
                "requires_provider_compatibility": True,
                "blocks_on_errors": True,
            },
            "tools": {
                "ownership": "core",
                "agent_control": "subset_only",
            },
            "resource_scope": {
                "shared_variables_require_grant": True,
                "global_secrets_require_grant": True,
                "llm_subprocess_env_sanitized": True,
                "tool_subprocess_env_sanitized": True,
                "prompt_injection_secret_barrier": (
                    "secrets never exposed through prompt layers or ambient subprocess inheritance"
                ),
            },
        }

    def get_core_capabilities(self) -> dict[str, Any]:
        providers = self.get_core_providers()
        return {
            "providers": [
                {
                    "provider": provider,
                    "vendor": _safe_json_object(payload).get("vendor"),
                    "runtime_adapter": _safe_json_object(payload).get("runtime_adapter"),
                    "command_present": bool(payload.get("command_present")),
                    "supports_streaming": bool(_safe_json_object(payload).get("supports_streaming", True)),
                    "supports_native_resume": bool(_safe_json_object(payload).get("supports_native_resume", True))
                    and bool(payload.get("command_present")),
                    "supports_fallback_bootstrap": bool(
                        _safe_json_object(payload).get("supports_fallback_bootstrap", True)
                    ),
                    "supports_tool_loop": bool(_safe_json_object(payload).get("supports_tool_loop", True)),
                    "supports_long_context": bool(_safe_json_object(payload).get("supports_long_context", True)),
                    "supports_images": bool(_safe_json_object(payload).get("supports_images", True)),
                    "supports_structured_output": bool(
                        _safe_json_object(payload).get("supports_structured_output", True)
                    ),
                    "supported_auth_modes": _safe_json_object(payload).get("supported_auth_modes") or [],
                    "connection_status": _safe_json_object(payload).get("connection_status") or {},
                    "status": "ready" if payload.get("enabled") and payload.get("command_present") else "degraded",
                }
                for provider, payload in _safe_json_object(providers.get("providers")).items()
            ]
        }

    def _persist_provider_connection_row(
        self,
        provider_id: str,
        *,
        auth_mode: str,
        configured: bool,
        verified: bool,
        account_label: str = "",
        plan_label: str = "",
        project_id: str = "",
        last_verified_at: str = "",
        last_error: str = "",
    ) -> None:
        normalized = provider_id.strip().lower()
        now = now_iso()
        execute(
            """
            INSERT INTO cp_provider_connections (
                provider_id, auth_mode, configured, verified, account_label, plan_label,
                project_id, last_verified_at, last_error, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider_id) DO UPDATE SET
                auth_mode = excluded.auth_mode,
                configured = excluded.configured,
                verified = excluded.verified,
                account_label = excluded.account_label,
                plan_label = excluded.plan_label,
                project_id = excluded.project_id,
                last_verified_at = excluded.last_verified_at,
                last_error = excluded.last_error,
                updated_at = excluded.updated_at
            """,
            (
                normalized,
                auth_mode,
                1 if configured else 0,
                1 if verified else 0,
                account_label,
                plan_label,
                project_id,
                last_verified_at or None,
                last_error,
                now,
                now,
            ),
        )

    def _provider_login_session_dict(self, state: ProviderLoginSessionState) -> dict[str, Any]:
        d: dict[str, Any] = {
            "session_id": state.session_id,
            "provider_id": state.provider_id,
            "auth_mode": state.auth_mode,
            "status": state.status,
            "command": state.command,
            "auth_url": state.auth_url,
            "user_code": state.user_code,
            "message": state.message,
            "instructions": state.instructions,
            "output_preview": state.output_preview,
            "last_error": state.last_error,
        }
        if state.code_verifier:
            d["code_verifier"] = state.code_verifier
        return d

    def _provider_login_session_storage_dict(self, state: ProviderLoginSessionState) -> dict[str, Any]:
        payload = {
            "session_id": state.session_id,
            "provider_id": state.provider_id,
            "auth_mode": state.auth_mode,
            "status": state.status,
            "command": state.command,
        }
        sensitive = {
            key: value
            for key, value in self._provider_login_session_dict(state).items()
            if key in _PROVIDER_LOGIN_SESSION_SENSITIVE_KEYS and _nonempty_text(value)
        }
        if sensitive:
            payload[_PROVIDER_LOGIN_SESSION_ENCRYPTED_DETAILS_KEY] = encrypt_secret(json_dump(sensitive))
        return payload

    def _inflate_provider_login_session_details(self, payload: dict[str, Any]) -> dict[str, Any]:
        details = dict(_safe_json_object(payload))
        encrypted_details = _nonempty_text(details.pop(_PROVIDER_LOGIN_SESSION_ENCRYPTED_DETAILS_KEY))
        if encrypted_details:
            try:
                decrypted = decrypt_secret(encrypted_details)
                details.update(_safe_json_object(json_load(decrypted, {})))
            except Exception:
                log.warning("Failed to decrypt provider login session details", exc_info=True)
        return details

    def _cleanup_provider_login_sessions(self) -> None:
        now = datetime.now(UTC)
        pending_cutoff = (now - _PROVIDER_LOGIN_SESSION_PENDING_TTL).isoformat()
        history_cutoff = (now - _PROVIDER_LOGIN_SESSION_HISTORY_TTL).isoformat()
        active_session_ids = tuple(self._provider_login_processes)
        if active_session_ids:
            placeholders = ",".join("?" for _ in active_session_ids)
            execute(
                f"""
                DELETE FROM cp_provider_login_sessions
                WHERE status IN ('pending', 'awaiting_browser')
                  AND COALESCE(updated_at, created_at) < ?
                  AND id NOT IN ({placeholders})
                """,
                (pending_cutoff, *active_session_ids),
            )
        else:
            execute(
                """
                DELETE FROM cp_provider_login_sessions
                WHERE status IN ('pending', 'awaiting_browser')
                  AND COALESCE(updated_at, created_at) < ?
                """,
                (pending_cutoff,),
            )
        execute(
            """
            DELETE FROM cp_provider_login_sessions
            WHERE status IN ('completed', 'error', 'cancelled')
              AND COALESCE(completed_at, updated_at, created_at) < ?
            """,
            (history_cutoff,),
        )

    def _persist_provider_login_session(self, state: ProviderLoginSessionState) -> None:
        self._cleanup_provider_login_sessions()
        now = now_iso()
        completed_at = now if state.status in {"completed", "error", "cancelled"} else None
        execute(
            """
            INSERT INTO cp_provider_login_sessions (
                id, provider_id, auth_mode, status, details_json, created_at, updated_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                details_json = excluded.details_json,
                updated_at = excluded.updated_at,
                completed_at = excluded.completed_at
            """,
            (
                state.session_id,
                state.provider_id,
                state.auth_mode,
                state.status,
                json_dump(self._provider_login_session_storage_dict(state)),
                now,
                now,
                completed_at,
            ),
        )

    def _sync_provider_login_session(self, provider_id: str, session_id: str) -> dict[str, Any]:
        self._cleanup_provider_login_sessions()
        normalized_provider = provider_id.strip().lower()
        row = fetch_one(
            "SELECT * FROM cp_provider_login_sessions WHERE id = ? AND provider_id = ?",
            (session_id, normalized_provider),
        )
        if row is None:
            raise KeyError(session_id)
        handle = self._provider_login_processes.get(session_id)
        if handle is not None:
            state = parse_login_session_state(session_id, handle)
            if state.auth_mode == "subscription_login" and state.status in {"awaiting_browser", "completed"}:
                connection_row = self._provider_connection_row(normalized_provider)
                verification = verify_provider_subscription_login(
                    cast(Any, normalized_provider),
                    project_id=_trimmed_text(connection_row["project_id"]),
                    base_env=self._merged_global_env(),
                    work_dir=self._provider_auth_work_dir(normalized_provider),
                )
                if verification.verified:
                    with contextlib.suppress(Exception):
                        handle.terminate()
                    self._provider_login_processes.pop(session_id, None)
                    state = ProviderLoginSessionState(
                        session_id=session_id,
                        provider_id=cast(Any, normalized_provider),
                        auth_mode="subscription_login",
                        status="completed",
                        command=state.command,
                        message="Autenticacao confirmada e verificada pelo backend.",
                        instructions=state.instructions,
                        output_preview=state.output_preview,
                    )
                elif state.status == "completed":
                    state = ProviderLoginSessionState(
                        session_id=session_id,
                        provider_id=cast(Any, normalized_provider),
                        auth_mode="subscription_login",
                        status="pending",
                        command=state.command,
                        auth_url=state.auth_url,
                        user_code=state.user_code,
                        message="Login concluido no provedor; validando autenticacao no backend.",
                        instructions=state.instructions,
                        output_preview=state.output_preview,
                        last_error=verification.last_error,
                    )
            self._persist_provider_login_session(state)
            if state.status in {"completed", "error", "cancelled"}:
                self._provider_login_processes.pop(session_id, None)
            row = fetch_one("SELECT * FROM cp_provider_login_sessions WHERE id = ?", (session_id,))
            if row is None:
                raise KeyError(session_id)
        details = self._inflate_provider_login_session_details(_safe_json_object(json_load(row["details_json"], {})))
        # Skip the "no handle → cancel" path when a direct OAuth exchange is
        # pending (code_verifier stored in memory).  The user hasn't submitted
        # the code yet; the session must stay in awaiting_browser.
        has_direct_oauth = session_id in getattr(self, "_claude_oauth_verifiers", {})
        if (
            handle is None
            and not has_direct_oauth
            and str(row["status"] or details.get("status") or "pending")
            in {
                "pending",
                "awaiting_browser",
            }
        ):
            auth_mode = _nonempty_text(details.get("auth_mode")) or "subscription_login"
            if auth_mode == "subscription_login":
                connection_row = self._provider_connection_row(normalized_provider)
                verification = verify_provider_subscription_login(
                    cast(Any, normalized_provider),
                    project_id=_trimmed_text(connection_row["project_id"]),
                    base_env=self._merged_global_env(),
                    work_dir=self._provider_auth_work_dir(normalized_provider),
                )
                if verification.verified:
                    completed_state = ProviderLoginSessionState(
                        session_id=session_id,
                        provider_id=cast(Any, normalized_provider),
                        auth_mode="subscription_login",
                        status="completed",
                        command=_nonempty_text(details.get("command")),
                        message="Autenticacao confirmada e verificada pelo backend.",
                        instructions=_nonempty_text(details.get("instructions")),
                        output_preview=_nonempty_text(details.get("output_preview")),
                    )
                    self._persist_provider_login_session(completed_state)
                    row = fetch_one("SELECT * FROM cp_provider_login_sessions WHERE id = ?", (session_id,))
                    if row is None:
                        raise KeyError(session_id)
                    details = self._inflate_provider_login_session_details(
                        _safe_json_object(json_load(row["details_json"], {}))
                    )
                elif str(row["status"] or details.get("status") or "pending") == "awaiting_browser":
                    cancelled_state = ProviderLoginSessionState(
                        session_id=session_id,
                        provider_id=cast(Any, normalized_provider),
                        auth_mode="subscription_login",
                        status="cancelled",
                        command=_nonempty_text(details.get("command")),
                        message="O fluxo de login expirou antes da autenticacao ser confirmada.",
                        instructions=_nonempty_text(details.get("instructions")),
                        output_preview=_nonempty_text(details.get("output_preview")),
                        last_error=verification.last_error,
                    )
                    self._persist_provider_login_session(cancelled_state)
                    row = fetch_one("SELECT * FROM cp_provider_login_sessions WHERE id = ?", (session_id,))
                    if row is None:
                        raise KeyError(session_id)
                    details = self._inflate_provider_login_session_details(
                        _safe_json_object(json_load(row["details_json"], {}))
                    )
        details.setdefault("session_id", session_id)
        details.setdefault("provider_id", normalized_provider)
        details["status"] = str(row["status"] or details.get("status") or "pending")
        details["completed_at"] = _trimmed_text(row["completed_at"])
        details["created_at"] = _trimmed_text(row["created_at"])
        details["updated_at"] = _trimmed_text(row["updated_at"])
        return details

    def _cleanup_provider_download_jobs(self) -> None:
        cutoff = (datetime.now(UTC) - _PROVIDER_DOWNLOAD_HISTORY_TTL).isoformat()
        execute(
            """
            DELETE FROM cp_provider_download_jobs
            WHERE status IN ('completed', 'error', 'cancelled')
              AND COALESCE(completed_at, updated_at, created_at) < ?
            """,
            (cutoff,),
        )

    def _provider_download_job_payload(self, row: Any) -> dict[str, Any]:
        details = _safe_json_object(json_load(row["details_json"], {}))
        payload = {
            "id": str(row["id"]),
            "job_id": str(row["id"]),
            "provider_id": str(row["provider_id"]),
            "asset_id": str(row["asset_id"]),
            "status": str(row["status"] or "pending"),
            "downloaded_bytes": int(row["downloaded_bytes"] or 0),
            "total_bytes": int(row["total_bytes"] or 0),
            "progress_percent": float(row["progress_percent"] or 0),
            "created_at": _trimmed_text(row["created_at"]),
            "updated_at": _trimmed_text(row["updated_at"]),
            "completed_at": _trimmed_text(row["completed_at"]),
            "details": details,
        }
        payload.update(details)
        return payload

    def _provider_download_cancel_events_ref(self) -> dict[str, threading.Event]:
        events = getattr(self, "_provider_download_cancel_events", None)
        if events is None:
            events = {}
            self._provider_download_cancel_events = events
        return events

    def _provider_download_cancel_requested(self, job_id: str) -> bool:
        event = self._provider_download_cancel_events_ref().get(job_id)
        return bool(event and event.is_set())

    def _raise_if_provider_download_cancelled(self, job_id: str) -> None:
        if self._provider_download_cancel_requested(job_id):
            raise _ProviderDownloadCancelled("download cancelled")

    def _register_provider_download_thread(self, job_id: str, thread: threading.Thread) -> None:
        threads = getattr(self, "_provider_download_threads", None)
        if threads is None:
            threads = {}
            self._provider_download_threads = threads
        threads[job_id] = thread
        self._provider_download_cancel_events_ref()[job_id] = threading.Event()

    def _clear_provider_download_tracking(self, job_id: str) -> None:
        threads = getattr(self, "_provider_download_threads", None)
        if threads is not None:
            threads.pop(job_id, None)
        self._provider_download_cancel_events_ref().pop(job_id, None)

    def _persist_provider_download_job(
        self,
        job_id: str,
        *,
        provider_id: str,
        asset_id: str,
        status: str,
        downloaded_bytes: int = 0,
        total_bytes: int = 0,
        details: dict[str, Any] | None = None,
    ) -> None:
        self._cleanup_provider_download_jobs()
        now = now_iso()
        progress_percent = (
            min(100.0, round((downloaded_bytes / total_bytes) * 100, 2))
            if total_bytes > 0
            else (100.0 if status == "completed" else 0.0)
        )
        execute(
            """
            INSERT INTO cp_provider_download_jobs (
                id, provider_id, asset_id, status, downloaded_bytes, total_bytes,
                progress_percent, details_json, created_at, updated_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                downloaded_bytes = excluded.downloaded_bytes,
                total_bytes = excluded.total_bytes,
                progress_percent = excluded.progress_percent,
                details_json = excluded.details_json,
                updated_at = excluded.updated_at,
                completed_at = excluded.completed_at
            """,
            (
                job_id,
                provider_id,
                asset_id,
                status,
                downloaded_bytes,
                total_bytes,
                progress_percent,
                json_dump(details or {}),
                now,
                now,
                now if status in {"completed", "error", "cancelled"} else None,
            ),
        )

    def _active_provider_download_job(self, provider_id: str, asset_id: str) -> dict[str, Any] | None:
        row = fetch_one(
            """
            SELECT * FROM cp_provider_download_jobs
            WHERE provider_id = ? AND asset_id = ? AND status IN ('pending', 'running')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (provider_id, asset_id),
        )
        return self._provider_download_job_payload(row) if row is not None else None

    def _run_kokoro_voice_download(self, job_id: str, voice_id: str) -> None:
        metadata = kokoro_voice_metadata(voice_id)
        if metadata is None:
            self._persist_provider_download_job(
                job_id,
                provider_id="kokoro",
                asset_id=voice_id,
                status="error",
                details={"last_error": f"unknown kokoro voice: {voice_id}"},
            )
            return

        base_details = {
            "voice_id": str(metadata["voice_id"]),
            "voice_name": str(metadata["name"]),
            "language_id": str(metadata["language_id"]),
            "language_label": str(metadata["language_label"]),
        }

        def _on_progress(downloaded_bytes: int, total_bytes: int) -> None:
            self._raise_if_provider_download_cancelled(job_id)
            self._persist_provider_download_job(
                job_id,
                provider_id="kokoro",
                asset_id=voice_id,
                status="running",
                downloaded_bytes=downloaded_bytes,
                total_bytes=total_bytes,
                details={**base_details, "message": "Baixando voz do Kokoro."},
            )

        try:
            self._raise_if_provider_download_cancelled(job_id)
            self._persist_provider_download_job(
                job_id,
                provider_id="kokoro",
                asset_id=voice_id,
                status="running",
                details={**base_details, "message": "Baixando voz do catalogo oficial do Kokoro."},
            )
            result = ensure_kokoro_voice_downloaded(voice_id, progress_callback=_on_progress)
            downloaded_bytes = int(result.get("bytes") or 0)
            self._raise_if_provider_download_cancelled(job_id)
            self._persist_provider_download_job(
                job_id,
                provider_id="kokoro",
                asset_id=voice_id,
                status="completed",
                downloaded_bytes=downloaded_bytes,
                total_bytes=downloaded_bytes,
                details={
                    **base_details,
                    "local_path": str(result.get("local_path") or ""),
                    "message": "Voz baixada com sucesso.",
                },
            )
        except _ProviderDownloadCancelled:
            self._persist_provider_download_job(
                job_id,
                provider_id="kokoro",
                asset_id=voice_id,
                status="cancelled",
                details={**base_details, "message": "Download cancelado."},
            )
        except Exception as exc:
            self._persist_provider_download_job(
                job_id,
                provider_id="kokoro",
                asset_id=voice_id,
                status="error",
                details={**base_details, "last_error": str(exc)},
            )
        finally:
            self._clear_provider_download_tracking(job_id)

    def get_kokoro_voice_catalog(self, language: str = "") -> dict[str, Any]:
        sections = self._system_settings_sections()
        providers_section = _safe_json_object(sections.get("providers"))
        requested_language = (
            _nonempty_text(language).lower()
            or _nonempty_text(providers_section.get("kokoro_default_language")).lower()
            or KOKORO_DEFAULT_LANGUAGE_ID
        )
        selected_voice = _nonempty_text(providers_section.get("kokoro_default_voice")) or KOKORO_DEFAULT_VOICE_ID
        payload = kokoro_catalog_payload(language_id=requested_language)
        voice_metadata = kokoro_voice_metadata(selected_voice)
        items: list[dict[str, Any]] = []
        for raw_item in _safe_json_list(payload.get("items")):
            item = _safe_json_object(raw_item)
            voice_id = _nonempty_text(item.get("voice_id")).lower()
            try:
                item["active_job"] = self._active_provider_download_job("kokoro", voice_id) if voice_id else None
            except Exception as exc:  # noqa: BLE001 - catalog should survive job table issues
                log.warning("kokoro_catalog_active_job_probe_failed", voice_id=voice_id, error=str(exc))
                item["active_job"] = None
            items.append(item)
        return {
            "items": items,
            "available_languages": _safe_json_list(payload.get("available_languages")),
            "selected_language": requested_language,
            "default_language": KOKORO_DEFAULT_LANGUAGE_ID,
            "default_voice": selected_voice,
            "default_voice_label": _nonempty_text(
                self._general_ui_meta(sections=sections).get("kokoro_default_voice_label")
            )
            or _nonempty_text(_safe_json_object(voice_metadata).get("name")),
            "downloaded_voice_ids": _safe_json_list(payload.get("downloaded_voice_ids")),
            "provider_connected": True,
        }

    def get_kokoro_voice_status(self, voice_id: str) -> dict[str, Any]:
        normalized_voice = _nonempty_text(voice_id).lower()
        metadata = kokoro_voice_metadata(normalized_voice)
        if metadata is None:
            raise ValueError(f"unknown kokoro voice: {voice_id}")

        voice_path = kokoro_voice_file_path(normalized_voice)
        downloaded = voice_path.exists() and voice_path.stat().st_size > 0
        try:
            active_job = self._active_provider_download_job("kokoro", normalized_voice)
        except Exception as exc:  # noqa: BLE001 - status should survive job table issues
            log.warning("kokoro_voice_active_job_probe_failed", voice_id=normalized_voice, error=str(exc))
            active_job = None
        return {
            **dict(metadata),
            "downloaded": downloaded,
            "bytes": int(voice_path.stat().st_size) if downloaded else 0,
            "local_path": str(voice_path) if downloaded else "",
            "active_job": active_job,
            "provider_connected": True,
        }

    def start_kokoro_voice_download(self, voice_id: str) -> dict[str, Any]:
        normalized_voice = _nonempty_text(voice_id).lower()
        metadata = kokoro_voice_metadata(normalized_voice)
        if metadata is None:
            raise ValueError(f"unknown kokoro voice: {voice_id}")

        active = self._active_provider_download_job("kokoro", normalized_voice)
        if active is not None:
            return active

        existing_catalog = self.get_kokoro_voice_catalog()
        downloaded_ids = {
            _nonempty_text(_safe_json_object(item).get("voice_id")).lower()
            for item in _safe_json_list(existing_catalog.get("items"))
            if bool(_safe_json_object(item).get("downloaded"))
        }
        job_id = str(uuid4())
        if normalized_voice in downloaded_ids:
            self._persist_provider_download_job(
                job_id,
                provider_id="kokoro",
                asset_id=normalized_voice,
                status="completed",
                downloaded_bytes=int(kokoro_voice_file_path(normalized_voice).stat().st_size),
                total_bytes=int(kokoro_voice_file_path(normalized_voice).stat().st_size),
                details={
                    "voice_id": normalized_voice,
                    "voice_name": str(metadata["name"]),
                    "language_id": str(metadata["language_id"]),
                    "language_label": str(metadata["language_label"]),
                    "local_path": str(kokoro_voice_file_path(normalized_voice)),
                    "message": "Voz ja disponivel localmente.",
                },
            )
            row = fetch_one("SELECT * FROM cp_provider_download_jobs WHERE id = ?", (job_id,))
            if row is None:
                raise RuntimeError("failed to persist kokoro download job")
            return self._provider_download_job_payload(row)

        self._persist_provider_download_job(
            job_id,
            provider_id="kokoro",
            asset_id=normalized_voice,
            status="pending",
            details={
                "voice_id": normalized_voice,
                "voice_name": str(metadata["name"]),
                "language_id": str(metadata["language_id"]),
                "language_label": str(metadata["language_label"]),
                "message": "Preparando download da voz.",
            },
        )
        thread = threading.Thread(
            target=self._run_kokoro_voice_download,
            args=(job_id, normalized_voice),
            name=f"kokoro-download-{normalized_voice}",
            daemon=True,
        )
        self._register_provider_download_thread(job_id, thread)
        thread.start()
        row = fetch_one("SELECT * FROM cp_provider_download_jobs WHERE id = ?", (job_id,))
        if row is None:
            raise RuntimeError("failed to persist kokoro download job")
        return self._provider_download_job_payload(row)

    # ------------------------------------------------------------------
    # Kokoro base model download — independent of voice downloads. The
    # base ONNX file is required before any voice can be loaded; the UI
    # exposes this as a separate first-time download so operators see
    # exactly what's happening rather than triggering an opaque
    # synchronous fetch the first time they pick a voice.
    # ------------------------------------------------------------------

    def get_kokoro_model_status(self) -> dict[str, Any]:
        status = kokoro_model_status()
        try:
            active = self._active_provider_download_job("kokoro", "model")
        except Exception as exc:  # noqa: BLE001 - status should survive job table issues
            log.warning("kokoro_model_active_job_probe_failed", error=str(exc))
            active = None
        return {**status, "active_job": active}

    def _run_kokoro_model_download(self, job_id: str) -> None:
        base_details = {
            "asset": "model",
            "filename": kokoro_model_path().name,
        }

        def _on_progress(downloaded: int, total: int) -> None:
            self._raise_if_provider_download_cancelled(job_id)
            self._persist_provider_download_job(
                job_id,
                provider_id="kokoro",
                asset_id="model",
                status="running",
                downloaded_bytes=downloaded,
                total_bytes=total,
                details={**base_details, "message": "Baixando modelo base do Kokoro."},
            )

        try:
            self._raise_if_provider_download_cancelled(job_id)
            self._persist_provider_download_job(
                job_id,
                provider_id="kokoro",
                asset_id="model",
                status="running",
                details={**base_details, "message": "Baixando modelo base do Kokoro."},
            )
            ensure_kokoro_model(progress_callback=_on_progress)
            bytes_on_disk = int(kokoro_model_path().stat().st_size)
            self._raise_if_provider_download_cancelled(job_id)
            self._persist_provider_download_job(
                job_id,
                provider_id="kokoro",
                asset_id="model",
                status="completed",
                downloaded_bytes=bytes_on_disk,
                total_bytes=bytes_on_disk,
                details={
                    **base_details,
                    "local_path": str(kokoro_model_path()),
                    "message": "Modelo Kokoro pronto.",
                },
            )
        except _ProviderDownloadCancelled:
            self._persist_provider_download_job(
                job_id,
                provider_id="kokoro",
                asset_id="model",
                status="cancelled",
                details={**base_details, "message": "Download cancelado."},
            )
        except Exception as exc:  # noqa: BLE001 - persist any failure as job error
            self._persist_provider_download_job(
                job_id,
                provider_id="kokoro",
                asset_id="model",
                status="error",
                details={**base_details, "last_error": str(exc)},
            )
        finally:
            self._clear_provider_download_tracking(job_id)

    def start_kokoro_model_download(self) -> dict[str, Any]:
        active = self._active_provider_download_job("kokoro", "model")
        if active is not None:
            return active

        job_id = str(uuid4())
        target = kokoro_model_path()
        if target.exists() and target.stat().st_size > 0:
            bytes_on_disk = int(target.stat().st_size)
            self._persist_provider_download_job(
                job_id,
                provider_id="kokoro",
                asset_id="model",
                status="completed",
                downloaded_bytes=bytes_on_disk,
                total_bytes=bytes_on_disk,
                details={
                    "asset": "model",
                    "filename": target.name,
                    "local_path": str(target),
                    "message": "Modelo ja disponivel localmente.",
                },
            )
            row = fetch_one("SELECT * FROM cp_provider_download_jobs WHERE id = ?", (job_id,))
            if row is None:
                raise RuntimeError("failed to persist kokoro model download job")
            return self._provider_download_job_payload(row)

        self._persist_provider_download_job(
            job_id,
            provider_id="kokoro",
            asset_id="model",
            status="pending",
            details={
                "asset": "model",
                "filename": target.name,
                "message": "Preparando download do modelo base do Kokoro.",
            },
        )
        thread = threading.Thread(
            target=self._run_kokoro_model_download,
            args=(job_id,),
            name="kokoro-model-download",
            daemon=True,
        )
        self._register_provider_download_thread(job_id, thread)
        thread.start()
        row = fetch_one("SELECT * FROM cp_provider_download_jobs WHERE id = ?", (job_id,))
        if row is None:
            raise RuntimeError("failed to persist kokoro model download job")
        return self._provider_download_job_payload(row)

    # ------------------------------------------------------------------
    # Supertonic local model and voice assets. Supertonic snapshots are
    # multi-file Hugging Face repos, while preset voice activation copies a
    # bundled JSON style into Koda-managed storage for explicit offline use.
    # ------------------------------------------------------------------

    def get_supertonic_model_catalog(self) -> dict[str, Any]:
        payload = supertonic_model_catalog_payload()
        items: list[dict[str, Any]] = []
        for entry in _safe_json_list(payload.get("items")):
            item = _safe_json_object(entry)
            model_id = _nonempty_text(item.get("model_id") or item.get("id"))
            try:
                item["active_job"] = self._active_provider_download_job("supertonic", model_id) if model_id else None
            except Exception as exc:  # noqa: BLE001 - catalog should survive job table issues
                log.warning("supertonic_model_active_job_probe_failed", model_id=model_id, error=str(exc))
                item["active_job"] = None
            items.append(item)
        return {**payload, "items": items}

    def _run_supertonic_model_download(self, job_id: str, model_id: str) -> None:
        try:
            metadata = supertonic_model_status(model_id)
        except KeyError:
            self._persist_provider_download_job(
                job_id,
                provider_id="supertonic",
                asset_id=model_id,
                status="error",
                details={"last_error": f"unknown supertonic model: {model_id}"},
            )
            self._clear_provider_download_tracking(job_id)
            return
        base_details = {
            "model_id": _nonempty_text(metadata.get("model_id")),
            "repo_id": _nonempty_text(metadata.get("repo_id")),
            "title": _nonempty_text(metadata.get("title")),
        }

        def _on_progress(downloaded: int, total: int) -> None:
            self._raise_if_provider_download_cancelled(job_id)
            self._persist_provider_download_job(
                job_id,
                provider_id="supertonic",
                asset_id=model_id,
                status="running",
                downloaded_bytes=downloaded,
                total_bytes=total,
                details={**base_details, "message": "Baixando snapshot Supertonic do Hugging Face."},
            )

        try:
            self._raise_if_provider_download_cancelled(job_id)
            self._persist_provider_download_job(
                job_id,
                provider_id="supertonic",
                asset_id=model_id,
                status="running",
                details={**base_details, "message": "Baixando snapshot Supertonic do Hugging Face."},
            )
            ensure_supertonic_model(model_id, progress_callback=_on_progress)
            final_status = supertonic_model_status(model_id)
            bytes_on_disk = int(final_status.get("bytes") or 0)
            self._raise_if_provider_download_cancelled(job_id)
            self._persist_provider_download_job(
                job_id,
                provider_id="supertonic",
                asset_id=model_id,
                status="completed",
                downloaded_bytes=bytes_on_disk,
                total_bytes=bytes_on_disk,
                details={
                    **base_details,
                    "local_path": _nonempty_text(final_status.get("local_path")),
                    "message": "Modelo Supertonic pronto.",
                },
            )
        except _ProviderDownloadCancelled:
            self._persist_provider_download_job(
                job_id,
                provider_id="supertonic",
                asset_id=model_id,
                status="cancelled",
                details={**base_details, "message": "Download cancelado."},
            )
        except Exception as exc:  # noqa: BLE001 - persist any failure as job error
            self._persist_provider_download_job(
                job_id,
                provider_id="supertonic",
                asset_id=model_id,
                status="error",
                details={**base_details, "last_error": str(exc)},
            )
        finally:
            self._clear_provider_download_tracking(job_id)

    def start_supertonic_model_download(self, model_id: str = SUPERTONIC_DEFAULT_MODEL_ID) -> dict[str, Any]:
        normalized = _nonempty_text(model_id) or SUPERTONIC_DEFAULT_MODEL_ID
        try:
            status = supertonic_model_status(normalized)
        except KeyError as exc:
            raise ValueError(f"unknown supertonic model: {model_id}") from exc

        active = self._active_provider_download_job("supertonic", normalized)
        if active is not None:
            return active

        job_id = str(uuid4())
        if bool(status.get("downloaded")):
            bytes_on_disk = int(status.get("bytes") or 0)
            self._persist_provider_download_job(
                job_id,
                provider_id="supertonic",
                asset_id=normalized,
                status="completed",
                downloaded_bytes=bytes_on_disk,
                total_bytes=bytes_on_disk,
                details={
                    "model_id": normalized,
                    "repo_id": _nonempty_text(status.get("repo_id")),
                    "title": _nonempty_text(status.get("title")),
                    "local_path": _nonempty_text(status.get("local_path")),
                    "message": "Modelo ja disponivel localmente.",
                },
            )
            row = fetch_one("SELECT * FROM cp_provider_download_jobs WHERE id = ?", (job_id,))
            if row is None:
                raise RuntimeError("failed to persist supertonic model download job")
            return self._provider_download_job_payload(row)

        self._persist_provider_download_job(
            job_id,
            provider_id="supertonic",
            asset_id=normalized,
            status="pending",
            details={
                "model_id": normalized,
                "repo_id": _nonempty_text(status.get("repo_id")),
                "title": _nonempty_text(status.get("title")),
                "message": "Preparando download do modelo Supertonic.",
            },
        )
        thread = threading.Thread(
            target=self._run_supertonic_model_download,
            args=(job_id, normalized),
            name=f"supertonic-model-download-{normalized}",
            daemon=True,
        )
        self._register_provider_download_thread(job_id, thread)
        thread.start()
        row = fetch_one("SELECT * FROM cp_provider_download_jobs WHERE id = ?", (job_id,))
        if row is None:
            raise RuntimeError("failed to persist supertonic model download job")
        return self._provider_download_job_payload(row)

    @staticmethod
    def _supertonic_voice_asset_id(model_id: str, voice_id: str) -> str:
        return f"{_nonempty_text(model_id) or SUPERTONIC_DEFAULT_MODEL_ID}:{_nonempty_text(voice_id)}"

    def get_supertonic_voice_catalog(self, model_id: str = "", language: str = "") -> dict[str, Any]:
        sections = self._system_settings_sections()
        providers_section = _safe_json_object(sections.get("providers"))
        selected_model = (
            _nonempty_text(model_id)
            or _nonempty_text(providers_section.get("supertonic_default_model"))
            or SUPERTONIC_DEFAULT_MODEL_ID
        )
        requested_language = (
            _nonempty_text(language).lower()
            or _nonempty_text(providers_section.get("supertonic_default_language")).lower()
            or SUPERTONIC_DEFAULT_LANGUAGE_ID
        )
        selected_voice = (
            _nonempty_text(providers_section.get("supertonic_default_voice")) or SUPERTONIC_DEFAULT_VOICE_ID
        )
        payload = supertonic_voice_catalog_payload(model_id=selected_model, language_id=requested_language)
        voice_metadata = supertonic_voice_metadata(selected_voice)
        items: list[dict[str, Any]] = []
        for raw_item in _safe_json_list(payload.get("items")):
            item = _safe_json_object(raw_item)
            voice_id = _nonempty_text(item.get("voice_id"))
            asset_id = self._supertonic_voice_asset_id(selected_model, voice_id)
            try:
                item["active_job"] = self._active_provider_download_job("supertonic", asset_id) if voice_id else None
            except Exception as exc:  # noqa: BLE001 - catalog should survive job table issues
                log.warning("supertonic_voice_active_job_probe_failed", voice_id=voice_id, error=str(exc))
                item["active_job"] = None
            items.append(item)
        return {
            **payload,
            "items": items,
            "selected_model": selected_model,
            "selected_language": requested_language,
            "default_model": selected_model,
            "default_language": SUPERTONIC_DEFAULT_LANGUAGE_ID,
            "default_voice": selected_voice,
            "default_voice_label": _nonempty_text(_safe_json_object(voice_metadata).get("name")),
            "provider_connected": True,
        }

    def _run_supertonic_voice_download(self, job_id: str, voice_id: str, model_id: str) -> None:
        asset_id = self._supertonic_voice_asset_id(model_id, voice_id)
        metadata = supertonic_voice_metadata(voice_id)
        if metadata is None:
            self._persist_provider_download_job(
                job_id,
                provider_id="supertonic",
                asset_id=asset_id,
                status="error",
                details={"last_error": f"unknown supertonic voice: {voice_id}"},
            )
            self._clear_provider_download_tracking(job_id)
            return
        base_details = {
            "voice_id": _nonempty_text(metadata.get("voice_id")),
            "voice_name": _nonempty_text(metadata.get("name")),
            "model_id": model_id,
        }

        def _on_progress(downloaded: int, total: int) -> None:
            self._raise_if_provider_download_cancelled(job_id)
            self._persist_provider_download_job(
                job_id,
                provider_id="supertonic",
                asset_id=asset_id,
                status="running",
                downloaded_bytes=downloaded,
                total_bytes=total,
                details={**base_details, "message": "Ativando voz Supertonic."},
            )

        try:
            self._raise_if_provider_download_cancelled(job_id)
            self._persist_provider_download_job(
                job_id,
                provider_id="supertonic",
                asset_id=asset_id,
                status="running",
                details={**base_details, "message": "Ativando voz Supertonic."},
            )
            result = ensure_supertonic_voice_downloaded(voice_id, model_id, progress_callback=_on_progress)
            downloaded_bytes = int(result.get("bytes") or 0)
            self._raise_if_provider_download_cancelled(job_id)
            self._persist_provider_download_job(
                job_id,
                provider_id="supertonic",
                asset_id=asset_id,
                status="completed",
                downloaded_bytes=downloaded_bytes,
                total_bytes=downloaded_bytes,
                details={
                    **base_details,
                    "local_path": _nonempty_text(result.get("local_path")),
                    "message": "Voz Supertonic pronta.",
                },
            )
        except _ProviderDownloadCancelled:
            self._persist_provider_download_job(
                job_id,
                provider_id="supertonic",
                asset_id=asset_id,
                status="cancelled",
                details={**base_details, "message": "Download cancelado."},
            )
        except Exception as exc:  # noqa: BLE001 - persist any failure as job error
            self._persist_provider_download_job(
                job_id,
                provider_id="supertonic",
                asset_id=asset_id,
                status="error",
                details={**base_details, "last_error": str(exc)},
            )
        finally:
            self._clear_provider_download_tracking(job_id)

    def start_supertonic_voice_download(self, voice_id: str, model_id: str = "") -> dict[str, Any]:
        normalized_voice = _nonempty_text(voice_id)
        selected_model = _nonempty_text(model_id) or SUPERTONIC_DEFAULT_MODEL_ID
        metadata = supertonic_voice_metadata(normalized_voice)
        if metadata is None:
            raise ValueError(f"unknown supertonic voice: {voice_id}")
        asset_id = self._supertonic_voice_asset_id(selected_model, _nonempty_text(metadata.get("voice_id")))

        active = self._active_provider_download_job("supertonic", asset_id)
        if active is not None:
            return active

        job_id = str(uuid4())
        existing = [
            _safe_json_object(item)
            for item in _safe_json_list(self.get_supertonic_voice_catalog(selected_model).get("items"))
        ]
        current = next(
            (
                item
                for item in existing
                if _nonempty_text(item.get("voice_id")) == _nonempty_text(metadata.get("voice_id"))
            ),
            {},
        )
        if bool(current.get("downloaded")):
            bytes_on_disk = int(current.get("bytes") or 0)
            self._persist_provider_download_job(
                job_id,
                provider_id="supertonic",
                asset_id=asset_id,
                status="completed",
                downloaded_bytes=bytes_on_disk,
                total_bytes=bytes_on_disk,
                details={
                    "voice_id": _nonempty_text(metadata.get("voice_id")),
                    "voice_name": _nonempty_text(metadata.get("name")),
                    "model_id": selected_model,
                    "local_path": _nonempty_text(current.get("local_path")),
                    "message": "Voz ja disponivel localmente.",
                },
            )
            row = fetch_one("SELECT * FROM cp_provider_download_jobs WHERE id = ?", (job_id,))
            if row is None:
                raise RuntimeError("failed to persist supertonic voice download job")
            return self._provider_download_job_payload(row)

        self._persist_provider_download_job(
            job_id,
            provider_id="supertonic",
            asset_id=asset_id,
            status="pending",
            details={
                "voice_id": _nonempty_text(metadata.get("voice_id")),
                "voice_name": _nonempty_text(metadata.get("name")),
                "model_id": selected_model,
                "message": "Preparando voz Supertonic.",
            },
        )
        thread = threading.Thread(
            target=self._run_supertonic_voice_download,
            args=(job_id, _nonempty_text(metadata.get("voice_id")), selected_model),
            name=f"supertonic-voice-download-{asset_id}",
            daemon=True,
        )
        self._register_provider_download_thread(job_id, thread)
        thread.start()
        row = fetch_one("SELECT * FROM cp_provider_download_jobs WHERE id = ?", (job_id,))
        if row is None:
            raise RuntimeError("failed to persist supertonic voice download job")
        return self._provider_download_job_payload(row)

    def import_supertonic_voice_asset(self, raw_bytes: bytes, *, model_id: str = "", name: str = "") -> dict[str, Any]:
        selected_model = _nonempty_text(model_id) or SUPERTONIC_DEFAULT_MODEL_ID
        return import_supertonic_voice_json(raw_bytes, name=name, model_id=selected_model)

    # ------------------------------------------------------------------
    # Embedding model catalog & background download. Mirrors the Kokoro
    # provider download pattern (cp_provider_download_jobs row + threading)
    # but talks to the Hugging Face Hub via ``huggingface_hub.snapshot_download``
    # because embedding models are multi-file repos (config + tokenizer +
    # weights + sentence-transformers metadata).
    # ------------------------------------------------------------------

    def _selected_embedding_model_id(self) -> str:
        sections = self._system_settings_sections()
        memory_section = _safe_json_object(sections.get("memory"))
        candidate = _nonempty_text(memory_section.get("embedding_model"))
        if candidate and candidate in _EMBEDDING_CATALOG:
            return candidate
        env_repo = _nonempty_text(os.environ.get("MEMORY_EMBEDDING_MODEL"))
        if env_repo:
            for model_id, definition in _EMBEDDING_CATALOG.items():
                if definition.repo_id == env_repo:
                    return model_id
        return _DEFAULT_EMBEDDING_MODEL_ID

    def get_embedding_model_catalog(self) -> dict[str, Any]:
        active = self._selected_embedding_model_id()
        payload = _embedding_catalog_payload(active_model_id=active)
        items: list[dict[str, Any]] = []
        for entry in _safe_json_list(payload.get("items")):
            item = _safe_json_object(entry)
            model_id = str(item.get("id") or "")
            try:
                item["active_job"] = self._active_provider_download_job("embedding", model_id)
            except Exception as exc:  # noqa: BLE001 - catalog should survive job table issues
                log.warning(
                    "embedding_catalog_active_job_probe_failed",
                    model_id=model_id,
                    error=str(exc),
                )
                item["active_job"] = None
            items.append(item)
        return {**payload, "items": items}

    def _run_embedding_model_download(self, job_id: str, model_id: str) -> None:
        definition = _EMBEDDING_CATALOG.get(model_id)
        if definition is None:
            self._persist_provider_download_job(
                job_id,
                provider_id="embedding",
                asset_id=model_id,
                status="error",
                details={"last_error": f"unknown embedding model: {model_id}"},
            )
            self._clear_provider_download_tracking(job_id)
            return

        base_details = {
            "model_id": definition.id,
            "repo_id": definition.repo_id,
            "title": definition.title,
            "expected_size_mb": definition.size_mb,
        }
        expected_total = int(definition.size_mb) * 1024 * 1024
        if self._provider_download_cancel_requested(job_id):
            self._persist_provider_download_job(
                job_id,
                provider_id="embedding",
                asset_id=definition.id,
                status="cancelled",
                total_bytes=expected_total,
                details={**base_details, "message": "Download cancelado."},
            )
            self._clear_provider_download_tracking(job_id)
            return
        self._persist_provider_download_job(
            job_id,
            provider_id="embedding",
            asset_id=definition.id,
            status="running",
            total_bytes=expected_total,
            details={**base_details, "message": "Baixando modelo de embedding do Hugging Face."},
        )

        # huggingface_hub.snapshot_download exposes no progress callback,
        # so we poll the cache dir from this thread while a sibling worker
        # downloads. Errors are propagated through a holder dict.
        download_error: dict[str, Any] = {}

        def _download() -> None:
            try:
                from huggingface_hub import snapshot_download  # noqa: PLC0415

                snapshot_download(
                    repo_id=definition.repo_id,
                    allow_patterns=[
                        "*.json",
                        "*.txt",
                        "*.md",
                        "*.safetensors",
                        "*.bin",
                        "tokenizer*",
                        "sentencepiece*",
                        "1_Pooling/*",
                        "modules.json",
                        "config_sentence_transformers.json",
                    ],
                )
            except Exception as exc:  # noqa: BLE001
                download_error["exc"] = exc

        worker = threading.Thread(
            target=_download,
            name=f"embedding-download-{definition.id}",
            daemon=True,
        )
        worker.start()

        last_persist = 0.0
        while worker.is_alive():
            downloaded = _embedding_model_disk_bytes(definition.id)
            if self._provider_download_cancel_requested(job_id):
                self._persist_provider_download_job(
                    job_id,
                    provider_id="embedding",
                    asset_id=definition.id,
                    status="cancelled",
                    downloaded_bytes=downloaded,
                    total_bytes=expected_total,
                    details={**base_details, "message": "Download cancelado."},
                )
                self._clear_provider_download_tracking(job_id)
                return
            now = time.monotonic()
            if now - last_persist >= 0.75:
                self._persist_provider_download_job(
                    job_id,
                    provider_id="embedding",
                    asset_id=definition.id,
                    status="running",
                    downloaded_bytes=downloaded,
                    total_bytes=expected_total,
                    details={**base_details, "message": "Baixando modelo de embedding."},
                )
                last_persist = now
            time.sleep(0.5)
        worker.join()

        if self._provider_download_cancel_requested(job_id):
            self._persist_provider_download_job(
                job_id,
                provider_id="embedding",
                asset_id=definition.id,
                status="cancelled",
                downloaded_bytes=_embedding_model_disk_bytes(definition.id),
                total_bytes=expected_total,
                details={**base_details, "message": "Download cancelado."},
            )
            self._clear_provider_download_tracking(job_id)
            return

        if download_error:
            self._persist_provider_download_job(
                job_id,
                provider_id="embedding",
                asset_id=definition.id,
                status="error",
                details={**base_details, "last_error": str(download_error.get("exc"))},
            )
            self._clear_provider_download_tracking(job_id)
            return

        final_bytes = _embedding_model_disk_bytes(definition.id)
        self._persist_provider_download_job(
            job_id,
            provider_id="embedding",
            asset_id=definition.id,
            status="completed",
            downloaded_bytes=final_bytes,
            total_bytes=final_bytes,
            details={**base_details, "message": "Modelo baixado com sucesso."},
        )
        # Drop any stale "this model failed to load" entries the runtime
        # cached before the user explicitly downloaded the weights — without
        # this, embed_text() keeps returning the hash-fallback even though
        # the model is now on disk.
        from koda.utils.embeddings import reset_embedding_load_cache  # noqa: PLC0415

        reset_embedding_load_cache(definition.repo_id)
        bare_name = definition.repo_id.split("/", 1)[-1]
        if bare_name != definition.repo_id:
            reset_embedding_load_cache(bare_name)
        self._clear_provider_download_tracking(job_id)

    def start_embedding_model_download(self, model_id: str) -> dict[str, Any]:
        normalized = _nonempty_text(model_id)
        definition = _EMBEDDING_CATALOG.get(normalized)
        if definition is None:
            raise ValueError(f"unknown embedding model: {model_id}")

        active = self._active_provider_download_job("embedding", definition.id)
        if active is not None:
            return active

        job_id = str(uuid4())
        if _embedding_model_installed(definition.id):
            bytes_on_disk = _embedding_model_disk_bytes(definition.id)
            self._persist_provider_download_job(
                job_id,
                provider_id="embedding",
                asset_id=definition.id,
                status="completed",
                downloaded_bytes=bytes_on_disk,
                total_bytes=bytes_on_disk,
                details={
                    "model_id": definition.id,
                    "repo_id": definition.repo_id,
                    "title": definition.title,
                    "message": "Modelo ja disponivel localmente.",
                },
            )
            row = fetch_one("SELECT * FROM cp_provider_download_jobs WHERE id = ?", (job_id,))
            if row is None:
                raise RuntimeError("failed to persist embedding download job")
            return self._provider_download_job_payload(row)

        self._persist_provider_download_job(
            job_id,
            provider_id="embedding",
            asset_id=definition.id,
            status="pending",
            details={
                "model_id": definition.id,
                "repo_id": definition.repo_id,
                "title": definition.title,
                "expected_size_mb": definition.size_mb,
                "message": "Preparando download do modelo de embedding.",
            },
        )
        thread = threading.Thread(
            target=self._run_embedding_model_download,
            args=(job_id, definition.id),
            name=f"embedding-download-{definition.id}",
            daemon=True,
        )
        self._register_provider_download_thread(job_id, thread)
        thread.start()
        row = fetch_one("SELECT * FROM cp_provider_download_jobs WHERE id = ?", (job_id,))
        if row is None:
            raise RuntimeError("failed to persist embedding download job")
        return self._provider_download_job_payload(row)

    def select_embedding_model(self, model_id: str) -> dict[str, Any]:
        """Persist the operator's choice in ``cp_global_sections.memory.embedding_model``.

        Refuses selection of a model that hasn't been downloaded yet so the
        runtime never points at a missing weights file. Returns the refreshed
        catalog payload so the UI updates state in one round-trip.
        """
        normalized = _nonempty_text(model_id)
        definition = _EMBEDDING_CATALOG.get(normalized)
        if definition is None:
            raise ValueError(f"unknown embedding model: {model_id}")
        if not _embedding_model_installed(definition.id):
            raise ValueError(f"embedding model not installed: {model_id}")
        sections = self._system_settings_sections()
        memory_section = dict(_safe_json_object(sections.get("memory")))
        memory_section["embedding_model"] = definition.id
        execute(
            """
            INSERT INTO cp_global_sections (section, data_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(section) DO UPDATE SET data_json = excluded.data_json, updated_at = excluded.updated_at
            """,
            ("memory", json_dump(memory_section), now_iso()),
        )
        return self.get_embedding_model_catalog()

    def delete_embedding_model_asset(self, model_id: str) -> dict[str, Any]:
        """Wipe the cache directory for a downloaded embedding model.

        Refuses to delete:
          - an unknown model_id;
          - a model with an in-flight download (cancel/wait first).

        The currently-active model *can* be deleted. If it is, we auto-pick
        another installed model as the new active to keep retrieval going;
        if no other model is on disk we clear the operator selection so the
        resolver falls back to env/default (and the runtime falls back to
        the hash-based vector until the operator downloads again).

        Returns the refreshed catalog payload so the UI re-renders without an
        extra round trip.
        """
        normalized = _nonempty_text(model_id)
        definition = _EMBEDDING_CATALOG.get(normalized)
        if definition is None:
            raise ValueError(f"unknown embedding model: {model_id}")
        active = self._active_provider_download_job("embedding", definition.id)
        if active is not None:
            raise ValueError("embedding model download in progress; cancel or wait before deleting")

        was_active = self._selected_embedding_model_id() == definition.id
        _delete_embedding_model(definition.id)

        if was_active:
            replacement: str | None = None
            for other_id in _EMBEDDING_CATALOG:
                if other_id == definition.id:
                    continue
                if _embedding_model_installed(other_id):
                    replacement = other_id
                    break
            sections = self._system_settings_sections()
            memory_section = dict(_safe_json_object(sections.get("memory")))
            if replacement is not None:
                memory_section["embedding_model"] = replacement
            else:
                memory_section.pop("embedding_model", None)
            execute(
                """
                INSERT INTO cp_global_sections (section, data_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(section) DO UPDATE SET data_json = excluded.data_json, updated_at = excluded.updated_at
                """,
                ("memory", json_dump(memory_section), now_iso()),
            )

        # Drop runtime caches so a future ``embed_text`` call doesn't keep
        # using a SentenceTransformer instance backed by files we just wiped.
        from koda.utils.embeddings import reset_embedding_load_cache  # noqa: PLC0415

        reset_embedding_load_cache(definition.repo_id)
        bare_name = definition.repo_id.split("/", 1)[-1]
        if bare_name != definition.repo_id:
            reset_embedding_load_cache(bare_name)

        return self.get_embedding_model_catalog()

    # ------------------------------------------------------------------
    # Whisper.cpp GGML model download. Mirrors the Kokoro pattern: a
    # single-shot job that streams the file to disk with a throttled
    # progress callback. The variant id is the asset_id so the same
    # job table row tracks one specific GGML variant at a time.
    # ------------------------------------------------------------------

    def get_whisper_catalog(self) -> dict[str, Any]:
        payload = whisper_catalog_payload()
        items: list[dict[str, Any]] = []
        for entry in _safe_json_list(payload.get("items")):
            item = _safe_json_object(entry)
            variant_id = str(item.get("variant_id") or "")
            active = self._active_provider_download_job("whispercpp", variant_id)
            items.append({**item, "active_job": active})
        return {**payload, "items": items}

    def _run_whisper_model_download(self, job_id: str, variant_id: str) -> None:
        descriptor = KNOWN_WHISPER_VARIANTS.get(variant_id)
        if descriptor is None:
            self._persist_provider_download_job(
                job_id,
                provider_id="whispercpp",
                asset_id=variant_id,
                status="error",
                details={"variant_id": variant_id, "last_error": f"unknown whisper variant: {variant_id}"},
            )
            return

        base_details = {
            "variant_id": variant_id,
            "filename": str(descriptor["filename"]),
            "label": str(descriptor["label"]),
        }

        def _on_progress(downloaded: int, total: int) -> None:
            self._raise_if_provider_download_cancelled(job_id)
            self._persist_provider_download_job(
                job_id,
                provider_id="whispercpp",
                asset_id=variant_id,
                status="running",
                downloaded_bytes=downloaded,
                total_bytes=total,
                details={**base_details, "message": "Baixando modelo Whisper."},
            )

        try:
            self._raise_if_provider_download_cancelled(job_id)
            self._persist_provider_download_job(
                job_id,
                provider_id="whispercpp",
                asset_id=variant_id,
                status="running",
                details={**base_details, "message": "Baixando modelo Whisper."},
            )
            result = ensure_whisper_model_downloaded(variant_id, progress_callback=_on_progress)
            bytes_on_disk = int(result.get("bytes") or 0)
            self._raise_if_provider_download_cancelled(job_id)
            self._persist_provider_download_job(
                job_id,
                provider_id="whispercpp",
                asset_id=variant_id,
                status="completed",
                downloaded_bytes=bytes_on_disk,
                total_bytes=bytes_on_disk,
                details={
                    **base_details,
                    "local_path": str(result.get("local_path") or ""),
                    "message": "Modelo Whisper pronto.",
                },
            )
        except _ProviderDownloadCancelled:
            self._persist_provider_download_job(
                job_id,
                provider_id="whispercpp",
                asset_id=variant_id,
                status="cancelled",
                details={**base_details, "message": "Download cancelado."},
            )
        except Exception as exc:  # noqa: BLE001 - persist any failure as job error
            self._persist_provider_download_job(
                job_id,
                provider_id="whispercpp",
                asset_id=variant_id,
                status="error",
                details={**base_details, "last_error": str(exc)},
            )
        finally:
            self._clear_provider_download_tracking(job_id)

    def start_whisper_model_download(self, variant_id: str = WHISPER_DEFAULT_VARIANT) -> dict[str, Any]:
        normalized = _nonempty_text(variant_id)
        if normalized not in KNOWN_WHISPER_VARIANTS:
            raise ValueError(f"unknown whisper variant: {variant_id}")

        active = self._active_provider_download_job("whispercpp", normalized)
        if active is not None:
            return active

        descriptor = KNOWN_WHISPER_VARIANTS[normalized]
        target = whisper_model_path(normalized)
        job_id = str(uuid4())
        if target.exists() and target.stat().st_size > 0:
            bytes_on_disk = int(target.stat().st_size)
            self._persist_provider_download_job(
                job_id,
                provider_id="whispercpp",
                asset_id=normalized,
                status="completed",
                downloaded_bytes=bytes_on_disk,
                total_bytes=bytes_on_disk,
                details={
                    "variant_id": normalized,
                    "filename": str(descriptor["filename"]),
                    "label": str(descriptor["label"]),
                    "local_path": str(target),
                    "message": "Modelo ja disponivel localmente.",
                },
            )
            row = fetch_one("SELECT * FROM cp_provider_download_jobs WHERE id = ?", (job_id,))
            if row is None:
                raise RuntimeError("failed to persist whisper download job")
            return self._provider_download_job_payload(row)

        self._persist_provider_download_job(
            job_id,
            provider_id="whispercpp",
            asset_id=normalized,
            status="pending",
            details={
                "variant_id": normalized,
                "filename": str(descriptor["filename"]),
                "label": str(descriptor["label"]),
                "message": "Preparando download do modelo Whisper.",
            },
        )
        thread = threading.Thread(
            target=self._run_whisper_model_download,
            args=(job_id, normalized),
            name=f"whisper-download-{normalized}",
            daemon=True,
        )
        self._register_provider_download_thread(job_id, thread)
        thread.start()
        row = fetch_one("SELECT * FROM cp_provider_download_jobs WHERE id = ?", (job_id,))
        if row is None:
            raise RuntimeError("failed to persist whisper download job")
        return self._provider_download_job_payload(row)

    # ------------------------------------------------------------------
    # Asset removal — counterpart to the download flows. Each helper is
    # idempotent (already-missing == success) so the UI can call it twice
    # without surfacing a confusing error to the operator.
    # ------------------------------------------------------------------

    def delete_kokoro_model_asset(self) -> dict[str, Any]:
        # Refuse while a download for the same asset is in flight — otherwise
        # we'd race the download thread's atomic .tmp → replace.
        active = self._active_provider_download_job("kokoro", "model")
        if active is not None:
            raise ValueError("kokoro model download in progress; cancel or wait before deleting")
        result = delete_kokoro_model()
        return {**result, **kokoro_model_status()}

    def delete_kokoro_voice_asset(self, voice_id: str) -> dict[str, Any]:
        normalized = _nonempty_text(voice_id).lower()
        if not normalized:
            raise ValueError("voice_id is required")
        active = self._active_provider_download_job("kokoro", normalized)
        if active is not None:
            raise ValueError("voice download in progress; cancel or wait before deleting")
        return delete_kokoro_voice(normalized)

    def delete_supertonic_model_asset(self, model_id: str) -> dict[str, Any]:
        normalized = _nonempty_text(model_id) or SUPERTONIC_DEFAULT_MODEL_ID
        active = self._active_provider_download_job("supertonic", normalized)
        if active is not None:
            raise ValueError("supertonic model download in progress; cancel or wait before deleting")
        try:
            result = delete_supertonic_model(normalized)
            return {**result, **supertonic_model_status(normalized)}
        except KeyError as exc:
            raise ValueError(f"unknown supertonic model: {model_id}") from exc

    def delete_supertonic_voice_asset(self, voice_id: str, model_id: str = "") -> dict[str, Any]:
        normalized_voice = _nonempty_text(voice_id)
        if not normalized_voice:
            raise ValueError("voice_id is required")
        selected_model = _nonempty_text(model_id) or SUPERTONIC_DEFAULT_MODEL_ID
        asset_id = self._supertonic_voice_asset_id(selected_model, normalized_voice)
        active = self._active_provider_download_job("supertonic", asset_id)
        if active is not None:
            raise ValueError("supertonic voice download in progress; cancel or wait before deleting")
        return delete_supertonic_voice(normalized_voice, selected_model)

    def delete_whisper_model_asset(self, variant_id: str) -> dict[str, Any]:
        normalized = _nonempty_text(variant_id)
        if normalized not in KNOWN_WHISPER_VARIANTS:
            raise ValueError(f"unknown whisper variant: {variant_id}")
        active = self._active_provider_download_job("whispercpp", normalized)
        if active is not None:
            raise ValueError("whisper download in progress; cancel or wait before deleting")
        return delete_whisper_model(normalized)

    def list_active_provider_downloads(self) -> list[dict[str, Any]]:
        """Return jobs in pending/running state across all known providers.

        Used by the frontend to rebind sticky toasts on page load — without
        this, a hard refresh during a long Whisper download would lose the
        progress UI even though the backend job is still running.
        """
        self._cleanup_provider_download_jobs()
        rows = fetch_all(
            """
            SELECT * FROM cp_provider_download_jobs
            WHERE status IN ('pending', 'running')
            ORDER BY created_at DESC
            """
        )
        return [self._provider_download_job_payload(row) for row in rows]

    def get_provider_download_job(self, provider_id: str, job_id: str) -> dict[str, Any]:
        normalized = provider_id.strip().lower()
        if normalized not in _PROVIDER_DOWNLOAD_PROVIDER_IDS:
            raise ValueError(f"unsupported provider download: {provider_id}")
        self._cleanup_provider_download_jobs()
        row = fetch_one(
            "SELECT * FROM cp_provider_download_jobs WHERE id = ? AND provider_id = ?",
            (job_id, normalized),
        )
        if row is None:
            raise KeyError(job_id)
        return self._provider_download_job_payload(row)

    def cancel_provider_download_job(self, provider_id: str, job_id: str) -> dict[str, Any]:
        normalized = provider_id.strip().lower()
        if normalized not in _PROVIDER_DOWNLOAD_PROVIDER_IDS:
            raise ValueError(f"unsupported provider download: {provider_id}")
        self._cleanup_provider_download_jobs()
        row = fetch_one(
            "SELECT * FROM cp_provider_download_jobs WHERE id = ? AND provider_id = ?",
            (job_id, normalized),
        )
        if row is None:
            raise KeyError(job_id)

        status = str(row["status"] or "pending")
        if status not in {"pending", "running"}:
            return self._provider_download_job_payload(row)

        event = self._provider_download_cancel_events_ref().get(job_id)
        if event is not None:
            event.set()

        details = _safe_json_object(json_load(row["details_json"], {}))
        self._persist_provider_download_job(
            job_id,
            provider_id=normalized,
            asset_id=str(row["asset_id"]),
            status="cancelled",
            downloaded_bytes=int(row["downloaded_bytes"] or 0),
            total_bytes=int(row["total_bytes"] or 0),
            details={**details, "message": "Download cancelado."},
        )

        thread = getattr(self, "_provider_download_threads", {}).get(job_id)
        if thread is None or not thread.is_alive():
            self._clear_provider_download_tracking(job_id)

        refreshed = fetch_one(
            "SELECT * FROM cp_provider_download_jobs WHERE id = ? AND provider_id = ?",
            (job_id, normalized),
        )
        if refreshed is None:
            raise KeyError(job_id)
        return self._provider_download_job_payload(refreshed)

    def get_provider_connection(self, provider_id: str) -> dict[str, Any]:
        return self._serialize_provider_connection(provider_id.strip().lower())

    def put_provider_api_key_connection(self, provider_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = provider_id.strip().lower()
        if normalized not in MANAGED_PROVIDER_IDS:
            raise ValueError(f"unsupported provider connection: {provider_id}")
        api_key = _trimmed_text(payload.get("api_key"))
        clear_api_key = bool(payload.get("clear_api_key"))
        existing_row = self._provider_connection_row(normalized)
        project_id = _trimmed_text(existing_row["project_id"])
        verify_after_save = bool(payload.get("verify_after_save", False))
        # Ollama in api_key mode targets the cloud endpoint (https://ollama.com).
        # The base URL is resolved at verify-time from the auth_mode default,
        # so we don't persist it into meta here — meta is reserved for the
        # operator-configured local endpoint.
        if api_key:
            self.upsert_global_secret_asset(
                PROVIDER_API_KEY_ENV_KEYS[cast(Any, normalized)],
                {
                    "value": api_key,
                    "description": f"Credential for {PROVIDER_TITLES[cast(Any, normalized)]}",
                    "usage_scope": "system_only",
                },
                persist_sections=True,
            )
            configured = True
        elif clear_api_key:
            self.delete_global_secret_asset(PROVIDER_API_KEY_ENV_KEYS[cast(Any, normalized)], persist_sections=True)
            configured = False
        else:
            configured = bool(self._provider_api_key_secret_value(normalized))
        self._persist_provider_connection_row(
            normalized,
            auth_mode="api_key",
            configured=configured,
            verified=False,
            account_label="",
            plan_label="",
            project_id=project_id,
            last_verified_at="",
            last_error="",
        )
        if verify_after_save and configured and api_key:
            try:
                verification = self.verify_provider_connection(normalized)
            except Exception:  # noqa: BLE001 - verify failure must not roll back save
                log.warning(
                    "control_plane_provider_auto_verify_failed",
                    provider=normalized,
                    exc_info=True,
                )
            else:
                return _safe_json_object(verification.get("connection")) or self.get_provider_connection(normalized)
        return self.get_provider_connection(normalized)

    def put_provider_local_connection(self, provider_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = provider_id.strip().lower()
        if normalized == "ollama":
            base_url = self._resolve_ollama_base_url(
                auth_mode="local",
                env={"OLLAMA_BASE_URL": _trimmed_text(payload.get("base_url"))},
            )
            self._persist_provider_connection_meta(normalized, base_url=base_url)
        elif normalized != "claude":
            raise ValueError(f"unsupported local provider connection: {provider_id}")
        self._persist_provider_connection_row(
            normalized,
            auth_mode="local",
            configured=True,
            verified=False,
            account_label="",
            plan_label="",
            project_id="",
            last_verified_at="",
            last_error="",
        )
        return self.get_provider_connection(normalized)

    def start_provider_login(self, provider_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        normalized = provider_id.strip().lower()
        if normalized not in MANAGED_PROVIDER_IDS:
            raise ValueError(f"unsupported provider connection: {provider_id}")
        # Ollama is a self-hosted endpoint — "login" is a base URL configuration.
        if normalized == "ollama":
            title = PROVIDER_TITLES.get(cast(Any, normalized), normalized)
            raise ValueError(f"{title} uses API key or local connection in this interface.")
        del payload
        existing_row = self._provider_connection_row(normalized)
        project_id = _trimmed_text(existing_row["project_id"])

        # Kill any lingering login subprocess for this provider so we never
        # leak a PTY when the operator restarts the wizard.
        self._terminate_provider_login_sessions(normalized)

        handle, state = start_login_process(
            cast(Any, normalized),
            project_id=project_id,
            base_env=self._merged_global_env(),
            work_dir=self._provider_auth_work_dir(normalized),
        )
        self._provider_login_processes[state.session_id] = handle
        self._persist_provider_connection_row(
            normalized,
            auth_mode="subscription_login",
            configured=True,
            verified=False,
            account_label="",
            plan_label="",
            project_id=project_id,
            last_verified_at="",
            last_error="",
        )
        self._persist_provider_connection_meta(normalized, project_id=project_id)
        self._persist_provider_login_session(state)
        return {
            "connection": self.get_provider_connection(normalized),
            "login_session": self._provider_login_session_dict(state),
        }

    def get_provider_login_session(self, provider_id: str, session_id: str) -> dict[str, Any]:
        return self._sync_provider_login_session(provider_id, session_id)

    def reauth_provider_connection(self, provider_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.start_provider_login(provider_id, payload)

    _PROVIDER_LOGIN_CODE_MAX_LEN = 512
    # Give the CLI a short window to either error out (Anthropic rejection is
    # fast — usually ~1s) or emit a success marker, then return. The frontend
    # polls every 2.5s and ``_sync_provider_login_session`` runs verification
    # on each poll, so late transitions (token hitting disk after we've
    # returned) still get reflected in the UI without blocking the submit
    # HTTP request longer than necessary.
    _PROVIDER_LOGIN_SUBMIT_DEADLINE_SECONDS = 6.0

    def submit_provider_login_code(
        self,
        provider_id: str,
        session_id: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized = provider_id.strip().lower()
        code = _trimmed_text(_safe_json_object(payload).get("code"))
        # Cap the payload defensively. Anthropic/OpenAI/Google authorization
        # codes fit in under 200 chars; anything larger is either a paste
        # mishap or a DoS attempt against the subprocess stdin buffer.
        if code and len(code) > self._PROVIDER_LOGIN_CODE_MAX_LEN:
            raise ValueError(f"authorization code is too long (max {self._PROVIDER_LOGIN_CODE_MAX_LEN} chars)")

        # Write code to CLI subprocess (Claude, Codex, Gemini).
        handle = self._provider_login_processes.get(session_id)
        if handle is None:
            # Session is gone from memory — most likely the server restarted,
            # the process died, or the session already reached a terminal
            # state. Return the persisted session snapshot so the UI can show
            # an actionable message ("session expired, start over") instead of
            # a 500 that stalls the spinner.
            log.warning(
                "provider_login_submit_session_missing",
                provider_id=normalized,
                session_id=session_id,
            )
            try:
                return self._sync_provider_login_session(normalized, session_id)
            except KeyError:
                raise KeyError(session_id) from None
        log.info(
            "provider_login_submit_started",
            provider_id=normalized,
            session_id=session_id,
            code_length=len(code or ""),
            code_has_hash_separator=("#" in (code or "")),
        )
        if code:
            handle.write(code + "\n")
            self._await_provider_login_completion(normalized, handle, session_id=session_id)
        return self._sync_provider_login_session(normalized, session_id)

    def _await_provider_login_completion(
        self,
        provider_id: str,
        handle: Any,
        *,
        session_id: str = "",
    ) -> None:
        """Block briefly while the CLI processes the pasted code, then return.

        We only wait for three possible outcomes inside the HTTP request
        window: (1) the CLI exits (success or failure — parse will classify
        by output + returncode), (2) the CLI emits an obvious OAuth error
        line, or (3) the deadline elapses. Verification via
        ``claude auth status --json`` runs in the frontend poll cycle
        (:py:meth:`get_provider_login_session`) rather than here — a separate
        ``claude`` subprocess holds ``.claude.json`` briefly and contending
        for it while ``setup-token`` is mid-exchange can actually slow the
        token write. Short HTTP response + polling is both simpler and
        faster than a long blocking submit.
        """
        proc = getattr(handle, "process", None)
        if proc is None:
            return
        deadline = time.monotonic() + self._PROVIDER_LOGIN_SUBMIT_DEADLINE_SECONDS
        started_at = time.monotonic()
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                log.info(
                    "provider_login_submit_cli_exited",
                    provider_id=provider_id,
                    session_id=session_id,
                    returncode=proc.returncode,
                    elapsed_seconds=round(time.monotonic() - started_at, 2),
                )
                return
            # Short-circuit on OAuth failure — the CLI prints the error line
            # and then sits at "Press Enter to retry", so the process stays
            # alive but the flow is effectively done from the operator's
            # perspective. Returning early lets parse surface the error.
            with contextlib.suppress(Exception):
                output = handle.normalized_output() or ""
                lower_tail = output[-500:].lower()
                if "oauth error:" in lower_tail or "invalid code" in lower_tail:
                    log.info(
                        "provider_login_submit_cli_reported_error",
                        provider_id=provider_id,
                        session_id=session_id,
                        elapsed_seconds=round(time.monotonic() - started_at, 2),
                    )
                    return
            time.sleep(0.2)
        output_tail = ""
        with contextlib.suppress(Exception):
            output_tail = str(handle.normalized_output() or "")[-500:]
        log.warning(
            "provider_login_submit_deadline_reached",
            provider_id=provider_id,
            session_id=session_id,
            elapsed_seconds=round(time.monotonic() - started_at, 2),
            cli_process_alive=proc.poll() is None,
            cli_output_tail=output_tail,
        )

    def _terminate_provider_login_sessions(self, provider_id: str) -> None:
        """Terminate any in-memory login subprocess owned by this provider.

        Called before starting a fresh login to reclaim the PTY / pipe handles
        when an operator restarts the wizard mid-flow.
        """
        normalized = provider_id.strip().lower()
        stale_ids = [
            session_id
            for session_id, handle in self._provider_login_processes.items()
            if getattr(handle, "provider_id", "") == normalized
        ]
        for session_id in stale_ids:
            handle = self._provider_login_processes.pop(session_id, None)
            if handle is None:
                continue
            with contextlib.suppress(Exception):
                handle.terminate()

    def _mark_provider_enabled(self, provider_id: str, *, enabled: bool) -> None:
        """Flip ``cp_global_sections.providers.{id}_enabled`` without going through
        the full ``put_general_system_settings`` flow.

        Writes both the flat ``{id}_enabled`` flag (consumed by
        ``_validate_general_payload``) AND the env-style ``{ID}_ENABLED`` key
        under ``providers.env`` (consumed by ``_provider_catalog_from_env``
        when the agent editor / model selectors build their provider lists).
        Keeping both in sync after a successful verify makes a newly verified
        provider show up immediately in every downstream view.
        """
        normalized = provider_id.strip().lower()
        if not normalized:
            return
        sections = self._system_settings_sections()
        providers_section = dict(_safe_json_object(sections.get("providers")))
        flag_key = f"{normalized}_enabled"
        env_key = f"{normalized.upper()}_ENABLED"
        env_map = dict(_safe_json_object(providers_section.get("env")))
        current_flag = providers_section.get(flag_key)
        current_env = env_map.get(env_key)
        desired_env = "true" if enabled else "false"
        already_in_sync = isinstance(current_flag, bool) and current_flag == enabled and current_env == desired_env
        if already_in_sync:
            return
        providers_section[flag_key] = bool(enabled)
        env_map[env_key] = desired_env
        providers_section["env"] = env_map
        self._persist_global_sections({"providers": providers_section})

    def verify_provider_connection(self, provider_id: str) -> dict[str, Any]:
        normalized = provider_id.strip().lower()
        row = self._provider_connection_row(normalized)
        auth_mode = _trimmed_text(row["auth_mode"]) or "subscription_login"
        if normalized == "elevenlabs":
            auth_mode = "api_key"
        project_id = _trimmed_text(row["project_id"])
        if auth_mode == "local":
            result = verify_provider_local_connection(
                cast(Any, normalized),
                base_url=self._resolve_ollama_base_url(auth_mode="local") if normalized == "ollama" else "",
                base_env=self._merged_global_env(),
                work_dir=self._provider_auth_work_dir(normalized),
            )
            configured = True
        elif auth_mode == "api_key":
            api_key = self._provider_api_key_secret_value(normalized)
            result = verify_provider_api_key(
                cast(Any, normalized),
                api_key,
                project_id=project_id,
                base_url=self._resolve_ollama_base_url(auth_mode="api_key") if normalized == "ollama" else "",
            )
            configured = bool(api_key)
        else:
            result = verify_provider_subscription_login(
                cast(Any, normalized),
                project_id=project_id,
                base_env=self._merged_global_env(),
                work_dir=self._provider_auth_work_dir(normalized),
            )
            configured = bool(int(row["configured"] or 0))
        self._persist_provider_connection_row(
            normalized,
            auth_mode=auth_mode,
            configured=configured,
            verified=result.verified,
            account_label=result.account_label,
            plan_label=result.plan_label,
            project_id=project_id,
            last_verified_at=now_iso() if result.verified else "",
            last_error=result.last_error,
        )
        if result.verified:
            detected_models = normalize_string_list(_safe_json_object(result.details).get("model_ids"))
            if detected_models:
                self._persist_provider_connection_meta(normalized, detected_models=detected_models)
            self._mark_provider_enabled(normalized, enabled=True)
        latest_row = fetch_one(
            """
            SELECT id FROM cp_provider_login_sessions
            WHERE provider_id = ? AND status IN ('pending', 'awaiting_browser', 'completed')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (normalized,),
        )
        if latest_row is not None and result.verified:
            details = self.get_provider_login_session(normalized, str(latest_row["id"]))
            details["status"] = "completed"
            state = ProviderLoginSessionState(
                session_id=str(details["session_id"]),
                provider_id=cast(Any, normalized),
                auth_mode=cast(Any, auth_mode),
                status="completed",
                command=str(details.get("command") or ""),
                auth_url=str(details.get("auth_url") or ""),
                user_code=str(details.get("user_code") or ""),
                message="Autenticacao confirmada e verificada pelo backend.",
                instructions=str(details.get("instructions") or ""),
                output_preview=str(details.get("output_preview") or ""),
                last_error="",
            )
            self._persist_provider_login_session(state)
        return {
            "connection": self.get_provider_connection(normalized),
            "verification": {
                "verified": result.verified,
                "account_label": result.account_label,
                "plan_label": result.plan_label,
                "checked_via": result.checked_via,
                "last_error": result.last_error,
                "auth_expired": result.auth_expired,
                "details": dict(result.details),
            },
        }

    def disconnect_provider_connection(self, provider_id: str) -> dict[str, Any]:
        """Full reset of a provider's connection state.

        Wipes everything Koda persists about the provider so the next
        connection attempt starts from zero:

        1. Terminates any in-flight login subprocess.
        2. Runs the CLI's native logout when available (``claude auth logout``,
           ``codex logout``) so on-disk OAuth tokens are revoked.
        3. Best-effort wipe of provider-owned credential files under the
           runtime HOME (catches tokens left after logout failures).
        4. Deletes ALL provider-scoped global secrets — API key, auth mode,
           base URL, project id, verification flag, auth-token (not only the
           API key as before).
        5. Purges every ``cp_provider_login_sessions`` row for the provider.
        6. Resets the ``cp_provider_connections`` row: cleared labels,
           cleared ``project_id``, cleared ``last_error``, ``configured`` +
           ``verified`` both false.
        """
        normalized = provider_id.strip().lower()
        row = self._provider_connection_row(normalized)
        for session_id, handle in list(self._provider_login_processes.items()):
            if getattr(handle, "provider_id", "") != normalized:
                continue
            handle.terminate()
            self._provider_login_processes.pop(session_id, None)
            cancelled = ProviderLoginSessionState(
                session_id=session_id,
                provider_id=cast(Any, normalized),
                auth_mode="subscription_login",
                status="cancelled",
                command=" ".join(getattr(handle, "command", [])),
                message="Fluxo de login cancelado.",
                output_preview=getattr(handle, "normalized_output", lambda: "")(),
            )
            self._persist_provider_login_session(cancelled)

        logout_performed, logout_message = run_provider_logout(
            cast(Any, normalized),
            base_env=self._merged_global_env(),
            work_dir=self._provider_auth_work_dir(normalized),
        )
        if not logout_performed and logout_message == "logout not supported":
            logout_message = ""

        self._wipe_provider_credential_files(normalized)
        self._purge_provider_global_secrets(normalized)

        with contextlib.suppress(Exception):
            execute(
                "DELETE FROM cp_provider_login_sessions WHERE provider_id = ?",
                (normalized,),
            )

        reset_auth_mode = (
            "api_key"
            if normalized == "elevenlabs"
            # Ollama is a self-hosted endpoint; Claude is authenticated out-of-band
            # by the operator via ``claude auth login`` on the container shell.
            # Both start in ``local`` mode after a reset.
            else "local"
            if normalized in {"ollama", "claude"}
            else "subscription_login"
        )

        self._persist_provider_connection_row(
            normalized,
            auth_mode=reset_auth_mode,
            configured=False,
            verified=False,
            account_label="",
            plan_label="",
            # ``project_id`` was intentionally persisted before. For a clean
            # reset we clear it too — operators explicitly asked for "wipe
            # everything that was persisted".
            project_id="",
            last_verified_at="",
            last_error="" if logout_performed or not logout_message else logout_message,
        )
        del row  # old row snapshot is no longer authoritative after the wipe above
        return {
            "connection": self.get_provider_connection(normalized),
            "logout": {
                "performed": logout_performed,
                "message": logout_message,
            },
        }

    def _purge_provider_global_secrets(self, provider_id: str) -> None:
        """Delete every provider-scoped entry from the global secrets store."""
        provider_key = cast(Any, provider_id)
        secret_env_keys = [
            key
            for key_map in (
                PROVIDER_API_KEY_ENV_KEYS,
                PROVIDER_AUTH_TOKEN_ENV_KEYS,
                PROVIDER_AUTH_MODE_ENV_KEYS,
                PROVIDER_VERIFIED_ENV_KEYS,
                PROVIDER_BASE_URL_ENV_KEYS,
                PROVIDER_PROJECT_ENV_KEYS,
            )
            if (key := key_map.get(provider_key))
        ]
        for env_key in secret_env_keys:
            with contextlib.suppress(Exception):
                self.delete_global_secret_asset(env_key, persist_sections=False)
        if secret_env_keys:
            self._persist_global_sections({})  # flush the provider-section drift

    def _wipe_provider_credential_files(self, provider_id: str) -> None:
        """Best-effort removal of CLI-managed credential files on disk.

        Claude Code / Codex CLIs keep OAuth tokens under the runtime HOME.
        ``*_auth logout`` is supposed to clear them, but failures or older
        CLI versions leave the tokens behind. Wipe the known paths so the
        next login starts from a clean slate.
        """
        import shutil
        from pathlib import Path

        home = os.environ.get("HOME") or ""
        config_dirs: list[Path] = []
        if provider_id == "claude":
            claude_config = os.environ.get("CLAUDE_CONFIG_DIR")
            if claude_config:
                config_dirs.append(Path(claude_config))
            if home:
                config_dirs.append(Path(home) / ".claude")
        elif provider_id == "codex":
            codex_home = os.environ.get("CODEX_HOME")
            if codex_home:
                config_dirs.append(Path(codex_home))
            if home:
                config_dirs.append(Path(home) / ".codex")
        elif provider_id == "gemini":
            if home:
                config_dirs.append(Path(home) / ".gemini")

        for directory in config_dirs:
            with contextlib.suppress(Exception):
                if directory.is_dir():
                    for child in directory.iterdir():
                        with contextlib.suppress(Exception):
                            if child.is_dir():
                                shutil.rmtree(child)
                            else:
                                child.unlink(missing_ok=True)

    def get_agent_spec(self, agent_id: str, *, snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
        normalized = _normalize_agent_id(agent_id)
        resolved_snapshot = snapshot or self.build_draft_snapshot(normalized)
        agent_spec = build_agent_spec_from_snapshot(resolved_snapshot)
        env = {
            key: _stringify_env_value(value) for key, value in _safe_json_object(resolved_snapshot.get("env")).items()
        }

        if not _safe_json_object(agent_spec.get("model_policy")):
            agent_spec["model_policy"] = self._model_policy_from_env(env)
        if not _safe_json_object(agent_spec.get("tool_policy")):
            agent_spec["tool_policy"] = self._tool_policy_from_env(env)
        if not _safe_json_object(agent_spec.get("autonomy_policy")):
            agent_spec["autonomy_policy"] = self._autonomy_policy_from_env(env)

        normalized_spec = normalize_agent_spec(agent_spec)
        documents_state = resolve_agent_documents(normalized_spec)
        normalized_spec["documents"] = documents_state["effective"]
        normalized_spec["document_projections"] = documents_state["projections"]
        normalized_spec["document_overrides"] = documents_state["overrides"]
        normalized_spec["document_sources"] = documents_state["sources"]
        normalized_spec["compiled_prompt"] = compose_agent_prompt(documents_state["effective"])
        normalized_spec["effective_usage"] = {
            "prompt_layers": [
                key
                for key, source in documents_state["sources"].items()
                if bool(_safe_json_object(source).get("affects_prompt"))
            ],
            "runtime_layers": [
                key
                for key, source in documents_state["sources"].items()
                if bool(_safe_json_object(source).get("affects_runtime"))
            ],
            "runtime_governed_sections": [
                key
                for key in (
                    "model_policy",
                    "tool_policy",
                    "autonomy_policy",
                    "execution_policy",
                    "memory_policy",
                    "knowledge_policy",
                    "resource_access_policy",
                    "skill_policy",
                )
                if _safe_json_object(normalized_spec.get(key))
            ],
        }
        return normalized_spec

    def put_agent_spec(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized, _ = self._require_agent_row(agent_id)
        current_snapshot = self.build_draft_snapshot(normalized)
        current_spec = self.get_agent_spec(normalized, snapshot=current_snapshot)

        updated_spec = dict(current_spec)
        for key in (
            "mission_profile",
            "interaction_style",
            "operating_instructions",
            "hard_rules",
            "response_policy",
            "model_policy",
            "tool_policy",
            "memory_policy",
            "knowledge_policy",
            "autonomy_policy",
            "execution_policy",
            "resource_access_policy",
            "voice_policy",
            "image_analysis_policy",
            "memory_extraction_schema",
            "skill_policy",
        ):
            if key in payload:
                updated_spec[key] = _safe_json_object(payload.get(key))
        if "custom_skills" in payload:
            updated_spec["custom_skills"] = _safe_json_list(payload.get("custom_skills"))

        if "documents" in payload:
            updated_spec["documents"] = {
                key: _normalize_markdown_block(value)
                for key, value in _safe_json_object(payload.get("documents")).items()
            }
        updated_spec = normalize_agent_spec(updated_spec)

        identity_payload = dict(self.get_section(normalized, "identity")["data"])
        prompting_payload = dict(self.get_section(normalized, "prompting")["data"])
        providers_payload = dict(self.get_section(normalized, "providers")["data"])
        tools_payload = dict(self.get_section(normalized, "tools")["data"])
        access_payload = dict(self.get_section(normalized, "access")["data"])
        memory_payload = dict(self.get_section(normalized, "memory")["data"])
        knowledge_payload = dict(self.get_section(normalized, "knowledge")["data"])
        runtime_payload = dict(self.get_section(normalized, "runtime")["data"])

        if "mission_profile" in payload:
            if _safe_json_object(updated_spec.get("mission_profile")):
                identity_payload["mission_profile"] = _safe_json_object(updated_spec["mission_profile"])
            else:
                identity_payload.pop("mission_profile", None)
        if "interaction_style" in payload:
            if _safe_json_object(updated_spec.get("interaction_style")):
                identity_payload["interaction_style"] = _safe_json_object(updated_spec["interaction_style"])
            else:
                identity_payload.pop("interaction_style", None)

        if "operating_instructions" in payload:
            if _safe_json_object(updated_spec.get("operating_instructions")):
                prompting_payload["operating_instructions"] = _safe_json_object(updated_spec["operating_instructions"])
            else:
                prompting_payload.pop("operating_instructions", None)
        if "hard_rules" in payload:
            if _safe_json_object(updated_spec.get("hard_rules")):
                prompting_payload["hard_rules"] = _safe_json_object(updated_spec["hard_rules"])
            else:
                prompting_payload.pop("hard_rules", None)
        if "response_policy" in payload:
            if _safe_json_object(updated_spec.get("response_policy")):
                prompting_payload["response_policy"] = _safe_json_object(updated_spec["response_policy"])
            else:
                prompting_payload.pop("response_policy", None)
        if "voice_policy" in payload:
            if _safe_json_object(updated_spec.get("voice_policy")):
                prompting_payload["voice_policy"] = _safe_json_object(updated_spec["voice_policy"])
            else:
                prompting_payload.pop("voice_policy", None)
        if "image_analysis_policy" in payload:
            if _safe_json_object(updated_spec.get("image_analysis_policy")):
                prompting_payload["image_analysis_policy"] = _safe_json_object(updated_spec["image_analysis_policy"])
            else:
                prompting_payload.pop("image_analysis_policy", None)
        if "skill_policy" in payload:
            if _safe_json_object(updated_spec.get("skill_policy")):
                prompting_payload["skill_policy"] = _safe_json_object(updated_spec["skill_policy"])
            else:
                prompting_payload.pop("skill_policy", None)
        if "custom_skills" in payload:
            custom_skills = _safe_json_list(updated_spec.get("custom_skills"))
            if custom_skills:
                prompting_payload["custom_skills"] = custom_skills
            else:
                prompting_payload.pop("custom_skills", None)

        if "model_policy" in payload:
            self._apply_model_policy_to_section(providers_payload, _safe_json_object(updated_spec.get("model_policy")))
        if "tool_policy" in payload:
            self._apply_tool_policy_to_section(tools_payload, _safe_json_object(updated_spec.get("tool_policy")))
        if "resource_access_policy" in payload:
            if _safe_json_object(updated_spec.get("resource_access_policy")):
                access_payload["resource_access_policy"] = _safe_json_object(updated_spec["resource_access_policy"])
            else:
                access_payload.pop("resource_access_policy", None)
        if "memory_policy" in payload:
            self._apply_memory_policy_to_section(memory_payload, _safe_json_object(updated_spec.get("memory_policy")))
        if "knowledge_policy" in payload:
            self._apply_knowledge_policy_to_section(
                knowledge_payload,
                _safe_json_object(updated_spec.get("knowledge_policy")),
            )
        if "autonomy_policy" in payload:
            self._apply_autonomy_policy_to_section(
                runtime_payload,
                _safe_json_object(updated_spec.get("autonomy_policy")),
            )
        if "execution_policy" in payload:
            execution_policy = _safe_json_object(updated_spec.get("execution_policy"))
            if execution_policy:
                runtime_payload["execution_policy"] = execution_policy
            else:
                runtime_payload.pop("execution_policy", None)
        if "memory_extraction_schema" in payload:
            extraction_schema = _safe_json_object(updated_spec.get("memory_extraction_schema"))
            if extraction_schema:
                memory_payload["memory_extraction_schema"] = extraction_schema
            else:
                memory_payload.pop("memory_extraction_schema", None)

        self.put_section(normalized, "identity", {"data": identity_payload})
        self.put_section(normalized, "prompting", {"data": prompting_payload})
        self.put_section(normalized, "providers", {"data": providers_payload})
        self.put_section(normalized, "tools", {"data": tools_payload})
        self.put_section(normalized, "access", {"data": access_payload}, strict_access_validation=False)
        self.put_section(normalized, "memory", {"data": memory_payload})
        self.put_section(normalized, "knowledge", {"data": knowledge_payload})
        self.put_section(normalized, "runtime", {"data": runtime_payload})

        projected_documents = render_markdown_documents_from_agent_spec(updated_spec)
        final_documents = merge_agent_documents(projected_documents, _safe_json_object(updated_spec.get("documents")))
        for kind in DOCUMENT_KINDS:
            content = _trimmed_text(final_documents.get(kind))
            if content:
                self.upsert_document(normalized, kind, {"content_md": content})
            elif self.get_document(normalized, kind):
                self.delete_document(normalized, kind)

        return self.get_agent_spec(normalized)

    def get_compiled_prompt(self, agent_id: str) -> dict[str, Any]:
        normalized = _normalize_agent_id(agent_id)
        snapshot = self.build_draft_snapshot(normalized)
        validation = self._build_validation_report(snapshot)
        compiled_prompt = str(validation["compiled_prompt"] or "")
        documents = dict(validation["documents"] or {})
        agent_contract_prompt_preview = preview_compiled_prompt(
            compiled_prompt=compiled_prompt,
            documents=documents,
            agent_id=normalized,
        )
        runtime_prompt_preview = _build_runtime_prompt_preview_payload(
            agent_id=normalized,
            agent_spec=_safe_json_object(validation.get("agent_spec")),
            compiled_prompt=compiled_prompt,
        )
        return {
            "agent_id": normalized,
            "compiled_prompt": compiled_prompt,
            "documents": documents,
            "document_sources": validation.get("document_sources", {}),
            "sections_present": validation["sections_present"],
            "document_lengths": validation["document_lengths"],
            "prompt_preview": runtime_prompt_preview,
            "agent_contract_prompt_preview": agent_contract_prompt_preview,
            "runtime_prompt_preview": runtime_prompt_preview,
        }

    def validate_agent(self, agent_id: str) -> dict[str, Any]:
        normalized = _normalize_agent_id(agent_id)
        snapshot = self.build_draft_snapshot(normalized)
        return self._build_validation_report(snapshot)

    def publish_checks(self, agent_id: str) -> dict[str, Any]:
        normalized = _normalize_agent_id(agent_id)
        snapshot = self.build_draft_snapshot(normalized)
        validation = self._build_validation_report(snapshot)
        access_state = self.get_section(normalized, "access")
        access_effective = _safe_json_object(access_state.get("effective"))
        access_data = _safe_json_object(access_state.get("data"))
        resource_access_policy = _safe_json_object(
            _safe_json_object(validation.get("agent_spec")).get("resource_access_policy")
        )
        knowledge_section = _safe_json_object(_safe_json_object(snapshot.get("sections")).get("knowledge"))
        pack_metadata = _safe_json_object(knowledge_section.get("pack_metadata"))
        knowledge_assets = _safe_json_list(snapshot.get("knowledge_assets"))
        provenance_warnings: list[str] = []
        for asset in knowledge_assets:
            if not bool(_safe_json_object(asset).get("enabled", True)):
                continue
            body = _safe_json_object(_safe_json_object(asset).get("body"))
            effective_owner = _trimmed_text(body.get("owner") or pack_metadata.get("owner"))
            effective_updated_at = _trimmed_text(body.get("updated_at") or pack_metadata.get("updated_at"))
            effective_freshness = _trimmed_text(body.get("freshness_days") or pack_metadata.get("freshness_days"))
            if not effective_owner:
                provenance_warnings.append(f"knowledge asset '{asset.get('asset_key')}' is missing owner provenance.")
            if not effective_updated_at and not effective_freshness:
                provenance_warnings.append(
                    f"knowledge asset '{asset.get('asset_key')}' is missing updated_at/freshness provenance."
                )

        provider_catalog = _safe_json_object(validation.get("provider_catalog"))
        provider_errors, provider_warnings = _provider_command_availability_issues(provider_catalog)
        resource_warnings: list[str] = []
        resource_errors: list[str] = []
        shared_env = _safe_json_object(access_effective.get("shared_env"))
        for env_key in normalize_string_list(resource_access_policy.get("allowed_shared_env_keys")):
            if _shared_env_key_is_reserved(env_key):
                resource_errors.append(
                    f"shared variable '{env_key}' collides with reserved core/provider/runtime configuration."
                )
            if env_key not in shared_env:
                resource_errors.append(
                    f"shared variable '{env_key}' is granted to the agent but does not exist globally."
                )
        global_secret_index = {
            str(item["secret_key"]): bool(item.get("grantable_to_agents", True))
            for item in self._current_global_secrets()
        }
        for secret_key in normalize_string_list(resource_access_policy.get("allowed_global_secret_keys")):
            if secret_key not in global_secret_index:
                resource_errors.append(
                    f"global secret '{secret_key}' is granted to the agent but does not exist globally."
                )
            elif not global_secret_index[secret_key]:
                resource_errors.append(
                    f"global secret '{secret_key}' is reserved for system-only use and cannot be granted to agents."
                )
        if self._current_global_secrets() and "resource_access_policy" not in access_data:
            resource_warnings.append(
                "This agent has no explicit global resource scope yet. "
                "Until you configure Escopo, it only receives agent-local secrets and no shared variables."
            )

        runtime_access_errors: list[str] = []
        runtime_access_warnings: list[str] = []
        try:
            token_present = self.get_secret_asset(normalized, "AGENT_TOKEN", scope="agent") is not None
        except Exception:
            token_present = False
        if not token_present:
            runtime_access_errors.append(
                "AGENT_TOKEN is not configured. The Telegram channel will fail to start until "
                "a bot token is saved in Identidade → Canal Telegram."
            )
        allowed_raw = ""
        try:
            allowed_raw = self.get_decrypted_secret_value(normalized, "ALLOWED_USER_IDS") or ""
        except Exception:
            allowed_raw = ""
        if not _normalize_user_id_values(allowed_raw):
            runtime_access_warnings.append(
                "ALLOWED_USER_IDS is empty. The agent will reply 'Access denied.' to every "
                "Telegram user until you add at least one numeric user ID in Identidade → Canal Telegram."
            )

        result = {
            **validation,
            "provider_errors": provider_errors,
            "provider_warnings": provider_warnings,
            "provenance_warnings": provenance_warnings,
            "resource_warnings": resource_warnings,
            "resource_errors": resource_errors,
            "agent_contract_prompt_preview": preview_compiled_prompt(
                compiled_prompt=str(validation.get("compiled_prompt") or ""),
                documents=_safe_json_object(validation.get("documents")),
                agent_id=normalized,
            ),
        }
        runtime_prompt_preview = _build_runtime_prompt_preview_payload(
            agent_id=normalized,
            agent_spec=_safe_json_object(validation.get("agent_spec")),
            compiled_prompt=str(validation.get("compiled_prompt") or ""),
        )
        runtime_budget = _safe_json_object(runtime_prompt_preview.get("budget"))
        runtime_prompt_errors: list[str] = []
        if not bool(runtime_budget.get("within_budget", False)):
            overflow_tokens = int(runtime_budget.get("overflow_tokens") or 0)
            gate_reason = str(runtime_budget.get("gate_reason") or "compiled_overflow").strip()
            if gate_reason == "hard_floor_overflow":
                runtime_prompt_errors.append(
                    "modeled runtime prompt hard floor exceeds the configured token budget "
                    f"(overflow={overflow_tokens} tokens)"
                )
            else:
                runtime_prompt_errors.append(
                    f"modeled runtime prompt exceeds the configured token budget (overflow={overflow_tokens} tokens)"
                )
        result["runtime_prompt_preview"] = runtime_prompt_preview
        result["prompt_preview"] = runtime_prompt_preview
        result["warnings"] = [
            *validation["warnings"],
            *provider_warnings,
            *provenance_warnings,
            *resource_warnings,
            *runtime_access_warnings,
        ]
        result["errors"] = [
            *validation["errors"],
            *provider_errors,
            *resource_errors,
            *runtime_prompt_errors,
            *runtime_access_errors,
        ]
        result["ok"] = not result["errors"]
        return result

    def get_tool_policy(self, agent_id: str) -> dict[str, Any]:
        normalized = _normalize_agent_id(agent_id)
        snapshot = self.build_draft_snapshot(normalized)
        feature_flags, _, _ = self._validation_inputs(snapshot)
        policy = _safe_json_object(self.get_agent_spec(normalized, snapshot=snapshot).get("tool_policy"))
        allowed_tool_ids = resolve_allowed_tool_ids(policy, feature_flags=feature_flags)
        return {
            "agent_id": normalized,
            "policy": policy,
            "allowed_tool_ids": allowed_tool_ids,
            "available_tools": resolve_feature_filtered_tools(feature_flags),
        }

    def put_tool_policy(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = _normalize_agent_id(agent_id)
        return self.put_agent_spec(normalized, {"tool_policy": _safe_json_object(payload.get("policy", payload))})

    def get_model_policy(self, agent_id: str) -> dict[str, Any]:
        normalized = _normalize_agent_id(agent_id)
        snapshot = self.build_draft_snapshot(normalized)
        provider_catalog = self._provider_catalog_from_env(
            {key: _stringify_env_value(value) for key, value in _safe_json_object(snapshot.get("env")).items()}
        )
        return {
            "agent_id": normalized,
            "policy": _safe_json_object(self.get_agent_spec(normalized, snapshot=snapshot).get("model_policy")),
            "provider_catalog": provider_catalog,
        }

    def put_model_policy(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = _normalize_agent_id(agent_id)
        return self.put_agent_spec(normalized, {"model_policy": _safe_json_object(payload.get("policy", payload))})

    def get_autonomy_policy(self, agent_id: str) -> dict[str, Any]:
        normalized = _normalize_agent_id(agent_id)
        snapshot = self.build_draft_snapshot(normalized)
        return {
            "agent_id": normalized,
            "policy": _safe_json_object(self.get_agent_spec(normalized, snapshot=snapshot).get("autonomy_policy")),
            "allowed_approval_modes": sorted(["guarded", "read_only", "escalation_required", "supervised"]),
            "allowed_autonomy_tiers": sorted(["t0", "t1", "t2"]),
        }

    def put_autonomy_policy(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = _normalize_agent_id(agent_id)
        return self.put_agent_spec(normalized, {"autonomy_policy": _safe_json_object(payload.get("policy", payload))})

    def _execution_policy_catalog(self, agent_id: str, *, snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
        normalized = _normalize_agent_id(agent_id)
        snapshot = snapshot or self.build_draft_snapshot(normalized)
        feature_flags, _, _ = self._validation_inputs(snapshot)
        mcp_actions: list[dict[str, Any]] = []
        for connection in self.list_mcp_agent_connections(normalized):
            if not bool(connection.get("enabled", True)):
                continue
            server_key = str(connection.get("server_key") or "").strip()
            if not server_key:
                continue
            try:
                connection_catalog = self.get_mcp_catalog_entry(server_key)
            except Exception:
                connection_catalog = {}
            tools_payload = self.get_mcp_connection_tools(normalized, server_key)
            mcp_actions.extend(
                build_mcp_action_catalog(
                    server_key=server_key,
                    tools=[tool for tool in tools_payload.get("tools") or [] if isinstance(tool, dict)],
                    tool_policies=_safe_json_object(tools_payload.get("policies")),
                    transport=str(connection_catalog.get("transport_type") or tools_payload.get("kind") or "mcp"),
                    connection_title=str(connection_catalog.get("display_name") or server_key),
                    connection_description=str(connection_catalog.get("description") or ""),
                )
            )
        return build_policy_catalog(feature_flags=feature_flags, mcp_actions=mcp_actions)

    def get_execution_policy(self, agent_id: str) -> dict[str, Any]:
        normalized = _normalize_agent_id(agent_id)
        snapshot = self.build_draft_snapshot(normalized)
        agent_spec = self.get_agent_spec(normalized, snapshot=snapshot)
        catalog = self._execution_policy_catalog(normalized, snapshot=snapshot)
        validation = self._validation_inputs(snapshot)
        feature_flags = validation[0]
        policy = resolve_execution_policy(agent_spec, feature_flags=feature_flags)
        source = _trimmed_text(_safe_json_object(policy).get("source")) or (
            "execution_policy" if _safe_json_object(agent_spec.get("execution_policy")) else "none"
        )
        return {
            "agent_id": normalized,
            "policy": policy,
            "source": source,
            "catalog": catalog,
            "legacy": {
                "tool_policy": _safe_json_object(agent_spec.get("tool_policy")),
                "autonomy_policy": _safe_json_object(agent_spec.get("autonomy_policy")),
                "resource_access_policy": _safe_json_object(agent_spec.get("resource_access_policy")),
            },
        }

    def put_execution_policy(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = _normalize_agent_id(agent_id)
        return self.put_agent_spec(
            normalized,
            {"execution_policy": _safe_json_object(payload.get("policy", payload))},
        )

    def get_execution_policy_catalog(self, agent_id: str) -> dict[str, Any]:
        normalized = _normalize_agent_id(agent_id)
        snapshot = self.build_draft_snapshot(normalized)
        catalog = self._execution_policy_catalog(normalized, snapshot=snapshot)
        feature_flags, _, _ = self._validation_inputs(snapshot)
        agent_spec = self.get_agent_spec(normalized, snapshot=snapshot)
        policy = resolve_execution_policy(agent_spec, feature_flags=feature_flags)
        return {
            "agent_id": normalized,
            "catalog": catalog,
            "policy": policy,
        }

    def evaluate_execution_policy(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = _normalize_agent_id(agent_id)
        snapshot = self.build_draft_snapshot(normalized)
        feature_flags, _, _ = self._validation_inputs(snapshot)
        agent_spec = self.get_agent_spec(normalized, snapshot=snapshot)
        policy = _safe_json_object(payload.get("policy")) or resolve_execution_policy(
            agent_spec,
            feature_flags=feature_flags,
        )
        catalog = self._execution_policy_catalog(normalized, snapshot=snapshot)
        envelope = _safe_json_object(payload.get("action") or payload.get("envelope") or payload)
        evaluation = evaluate_execution_policy(policy, envelope, policy_catalog=catalog)
        return {
            "agent_id": normalized,
            "policy": policy,
            "catalog": catalog,
            "action": envelope,
            "evaluation": evaluation,
        }

    def list_knowledge_candidates(
        self,
        agent_id: str,
        *,
        review_status: str = "pending",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        normalized = _normalize_agent_id(agent_id)
        return cast(
            list[dict[str, Any]],
            self._knowledge_governance_store().list_knowledge_candidates(
                agent_id=normalized,
                review_status=review_status,
                limit=limit,
            ),
        )

    def get_knowledge_candidate(self, agent_id: str, candidate_id: int) -> dict[str, Any] | None:
        normalized = _normalize_agent_id(agent_id)
        candidate = self._knowledge_governance_store().get_knowledge_candidate(candidate_id)
        if not candidate:
            return None
        candidate_agent_id = _trimmed_text(candidate.get("agent_id") or normalized).upper()
        return candidate if candidate_agent_id in {"", normalized} else None

    def approve_knowledge_candidate(
        self,
        agent_id: str,
        candidate_id: int,
        *,
        reviewer: str = "control-plane",
    ) -> int | None:
        _normalize_agent_id(agent_id)
        return cast(
            int | None,
            self._knowledge_governance_store().approve_knowledge_candidate(candidate_id, reviewer=reviewer),
        )

    def reject_knowledge_candidate(self, agent_id: str, candidate_id: int, *, reviewer: str = "control-plane") -> bool:
        _normalize_agent_id(agent_id)
        return bool(self._knowledge_governance_store().reject_knowledge_candidate(candidate_id, reviewer=reviewer))

    def list_improvement_proposals(
        self,
        agent_id: str,
        *,
        status: str | None = None,
        proposal_type: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        proposals = self._improvement_proposal_service(normalized).list_proposals(
            status=status,
            proposal_type=proposal_type,
            limit=limit,
        )
        return {"schema_version": "improvement_proposal.v1", "items": proposals}

    def create_improvement_proposal(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        proposal = cast(
            dict[str, Any],
            self._improvement_proposal_service(normalized).create(
                {**payload, "agent_id": normalized},
                requested_by=str(payload.get("reviewer") or "control-plane"),
            ),
        )
        self._record_improvement_proposal_event(normalized, "created", proposal)
        return proposal

    def get_improvement_proposal(self, agent_id: str, proposal_id: str) -> dict[str, Any]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        return cast(dict[str, Any], self._improvement_proposal_service(normalized).get(proposal_id))

    def approve_improvement_proposal(
        self,
        agent_id: str,
        proposal_id: str,
        *,
        reviewer: str = "control-plane",
        note: str = "",
    ) -> dict[str, Any]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        proposal = cast(
            dict[str, Any],
            self._improvement_proposal_service(normalized).approve(proposal_id, reviewer=reviewer, note=note),
        )
        self._record_improvement_proposal_event(normalized, "approved", proposal)
        return proposal

    def reject_improvement_proposal(
        self,
        agent_id: str,
        proposal_id: str,
        *,
        reviewer: str = "control-plane",
        note: str = "",
    ) -> dict[str, Any]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        proposal = cast(
            dict[str, Any],
            self._improvement_proposal_service(normalized).reject(proposal_id, reviewer=reviewer, note=note),
        )
        self._record_improvement_proposal_event(normalized, "rejected", proposal)
        return proposal

    def validate_improvement_proposal(
        self,
        agent_id: str,
        proposal_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        reviewer = str(payload.get("reviewer") or "control-plane")
        note = str(payload.get("note") or "")
        validation_result = payload.get("validation_result")
        if validation_result is None and any(key in payload for key in ("status", "passed", "ok", "details")):
            validation_result = {key: value for key, value in payload.items() if key not in {"reviewer", "note"}}
        proposal = cast(
            dict[str, Any],
            self._improvement_proposal_service(normalized).validate(
                proposal_id,
                validation_result=validation_result,
                reviewer=reviewer,
                note=note,
            ),
        )
        status = str(proposal.get("status") or "")
        event = "validating" if status == "validating" else "failed" if status == "failed" else "validated"
        self._record_improvement_proposal_event(normalized, event, proposal)
        return proposal

    def apply_improvement_proposal(
        self,
        agent_id: str,
        proposal_id: str,
        *,
        reviewer: str = "control-plane",
        note: str = "",
    ) -> dict[str, Any]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        proposal = cast(
            dict[str, Any],
            self._improvement_proposal_service(normalized).apply(proposal_id, reviewer=reviewer, note=note),
        )
        self._record_improvement_proposal_event(normalized, "applied", proposal)
        return proposal

    def rollback_improvement_proposal(
        self,
        agent_id: str,
        proposal_id: str,
        *,
        reviewer: str = "control-plane",
        note: str = "",
    ) -> dict[str, Any]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        proposal = cast(
            dict[str, Any],
            self._improvement_proposal_service(normalized).rollback(proposal_id, reviewer=reviewer, note=note),
        )
        self._record_improvement_proposal_event(normalized, "rolled_back", proposal)
        return proposal

    def _record_improvement_proposal_event(
        self,
        agent_id: str,
        event: str,
        proposal: dict[str, Any],
    ) -> None:
        details = {
            "schema_version": "improvement_proposal.v1",
            "proposal_id": proposal.get("proposal_id"),
            "proposal_type": proposal.get("proposal_type"),
            "status": proposal.get("status"),
            "risk_class": proposal.get("risk_class"),
            "source_kind": proposal.get("source_kind"),
            "source_ref": proposal.get("source_ref"),
            "evidence_refs": proposal.get("evidence_refs") or [],
            "validation_status": (proposal.get("validation_result") or {}).get("status")
            if isinstance(proposal.get("validation_result"), dict)
            else "",
            "run_graph_node_ids": proposal.get("run_graph_node_ids") or [],
        }
        self._emit_lifecycle_audit_event(
            agent_id,
            event_type=f"improvement_proposal.{event}",
            details=details,
        )
        try:
            from koda.services.metrics import IMPROVEMENT_PROPOSAL_EVENTS

            IMPROVEMENT_PROPOSAL_EVENTS.labels(
                agent_id=agent_id,
                event=event,
                status=str(proposal.get("status") or ""),
                proposal_type=str(proposal.get("proposal_type") or ""),
            ).inc()
        except Exception:
            log.debug("improvement_proposal_metric_error", exc_info=True)

    def list_runbooks(self, agent_id: str, *, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        normalized = _normalize_agent_id(agent_id)
        governance_store = self._knowledge_governance_store()
        runbooks = cast(
            list[dict[str, Any]],
            governance_store.list_approved_runbooks(
                agent_id=normalized,
                status=status,
                enforce_valid_window=False,
                limit=limit,
            ),
        )
        governance = cast(
            dict[int, dict[str, Any]],
            governance_store.get_latest_runbook_governance_actions(
                [int(item["id"]) for item in runbooks if item.get("id")],
                agent_id=normalized,
            ),
        )
        for runbook in runbooks:
            runbook["latest_governance"] = governance.get(int(runbook["id"]), {})
        return runbooks

    def revalidate_runbook(self, agent_id: str, runbook_id: int, *, reviewer: str = "control-plane") -> bool:
        _normalize_agent_id(agent_id)
        return bool(self._knowledge_governance_store().revalidate_approved_runbook(runbook_id, reviewer=reviewer))

    def _knowledge_storage(self, agent_id: str) -> Any:
        from koda.knowledge.storage_v2 import KnowledgeStorageV2

        normalized = _normalize_agent_id(agent_id)
        return KnowledgeStorageV2(self._knowledge_repository(normalized), normalized)

    def _list_retrieval_traces_local(
        self,
        agent_id: str,
        *,
        task_id: int | None = None,
        strategy: str | None = None,
        experiment_key: str | None = None,
        trace_role: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        repository = self._knowledge_repository(agent_id)
        return cast(
            list[dict[str, Any]],
            repository.list_retrieval_traces(
                task_id=task_id,
                strategy=strategy,
                experiment_key=experiment_key,
                trace_role=trace_role,
                limit=limit,
            ),
        )

    def _list_answer_traces_local(
        self,
        agent_id: str,
        *,
        task_id: int | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            self._knowledge_repository(agent_id).list_answer_traces(
                task_id=task_id,
                limit=limit,
            ),
        )

    def _get_retrieval_trace_local(self, agent_id: str, trace_id: int) -> dict[str, Any] | None:
        normalized = _normalize_agent_id(agent_id)
        trace = cast(dict[str, Any] | None, self._knowledge_repository(normalized).get_retrieval_trace(trace_id))
        if not trace:
            return None
        trace_agent_id = _trimmed_text(trace.get("agent_id") or normalized).upper()
        return trace if trace_agent_id in {"", normalized} else None

    def _get_answer_trace_local(self, agent_id: str, answer_trace_id: int) -> dict[str, Any] | None:
        normalized = _normalize_agent_id(agent_id)
        trace = cast(dict[str, Any] | None, self._knowledge_repository(normalized).get_answer_trace(answer_trace_id))
        if not trace:
            return None
        trace_agent_id = _trimmed_text(trace.get("agent_id") or normalized).upper()
        return trace if trace_agent_id in {"", normalized} else None

    async def list_retrieval_traces_async(
        self,
        agent_id: str,
        *,
        task_id: int | None = None,
        strategy: str | None = None,
        experiment_key: str | None = None,
        trace_role: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        storage = self._knowledge_storage(agent_id)
        if not storage.primary_read_enabled():
            return self._list_retrieval_traces_local(
                agent_id,
                task_id=task_id,
                strategy=strategy,
                experiment_key=experiment_key,
                trace_role=trace_role,
                limit=limit,
            )
        try:
            return cast(
                list[dict[str, Any]],
                await storage.list_retrieval_traces_async(
                    task_id=task_id,
                    strategy=strategy,
                    experiment_key=experiment_key,
                    trace_role=trace_role,
                    limit=limit,
                ),
            )
        except Exception:
            log.exception("control_plane_primary_retrieval_trace_list_failed", agent_id=agent_id)
            return self._list_retrieval_traces_local(
                agent_id,
                task_id=task_id,
                strategy=strategy,
                experiment_key=experiment_key,
                trace_role=trace_role,
                limit=limit,
            )

    async def list_answer_traces_async(
        self,
        agent_id: str,
        *,
        task_id: int | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        storage = self._knowledge_storage(agent_id)
        if not storage.primary_read_enabled():
            return self._list_answer_traces_local(agent_id, task_id=task_id, limit=limit)
        try:
            return cast(list[dict[str, Any]], await storage.list_answer_traces_async(task_id=task_id, limit=limit))
        except Exception:
            log.exception("control_plane_primary_answer_trace_list_failed", agent_id=agent_id)
            return self._list_answer_traces_local(agent_id, task_id=task_id, limit=limit)

    async def get_retrieval_trace_async(self, agent_id: str, trace_id: int) -> dict[str, Any] | None:
        storage = self._knowledge_storage(agent_id)
        if not storage.primary_read_enabled():
            return self._get_retrieval_trace_local(agent_id, trace_id)
        try:
            return cast(dict[str, Any] | None, await storage.get_retrieval_trace_async(trace_id))
        except Exception:
            log.exception("control_plane_primary_retrieval_trace_get_failed", agent_id=agent_id, trace_id=trace_id)
            return self._get_retrieval_trace_local(agent_id, trace_id)

    async def get_answer_trace_async(self, agent_id: str, answer_trace_id: int) -> dict[str, Any] | None:
        storage = self._knowledge_storage(agent_id)
        if not storage.primary_read_enabled():
            return self._get_answer_trace_local(agent_id, answer_trace_id)
        try:
            return cast(dict[str, Any] | None, await storage.get_answer_trace_async(answer_trace_id))
        except Exception:
            log.exception(
                "control_plane_primary_answer_trace_get_failed",
                agent_id=agent_id,
                answer_trace_id=answer_trace_id,
            )
            return self._get_answer_trace_local(agent_id, answer_trace_id)

    async def list_knowledge_graph_async(
        self,
        agent_id: str,
        *,
        entity_type: str | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        try:
            client = build_retrieval_engine_client(agent_id=agent_id)
            await client.start()
            try:
                return cast(dict[str, Any], client.list_graph(entity_type=entity_type, limit=limit))
            finally:
                with contextlib.suppress(Exception):
                    await client.stop()
        except Exception as exc:
            log.exception("control_plane_primary_graph_list_failed", agent_id=agent_id)
            raise RuntimeError("grpc_retrieval_engine_graph_list_failed") from exc

    def list_retrieval_traces(
        self,
        agent_id: str,
        *,
        task_id: int | None = None,
        strategy: str | None = None,
        experiment_key: str | None = None,
        trace_role: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        storage = self._knowledge_storage(agent_id)
        if storage.primary_read_enabled():
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                return asyncio.run(
                    self.list_retrieval_traces_async(
                        agent_id,
                        task_id=task_id,
                        strategy=strategy,
                        experiment_key=experiment_key,
                        trace_role=trace_role,
                        limit=limit,
                    )
                )
        return self._list_retrieval_traces_local(
            agent_id,
            task_id=task_id,
            strategy=strategy,
            experiment_key=experiment_key,
            trace_role=trace_role,
            limit=limit,
        )

    def list_answer_traces(
        self,
        agent_id: str,
        *,
        task_id: int | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        storage = self._knowledge_storage(agent_id)
        if storage.primary_read_enabled():
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                return asyncio.run(self.list_answer_traces_async(agent_id, task_id=task_id, limit=limit))
        return self._list_answer_traces_local(agent_id, task_id=task_id, limit=limit)

    def get_retrieval_trace(self, agent_id: str, trace_id: int) -> dict[str, Any] | None:
        storage = self._knowledge_storage(agent_id)
        if storage.primary_read_enabled():
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                return asyncio.run(self.get_retrieval_trace_async(agent_id, trace_id))
        return self._get_retrieval_trace_local(agent_id, trace_id)

    def get_answer_trace(self, agent_id: str, answer_trace_id: int) -> dict[str, Any] | None:
        storage = self._knowledge_storage(agent_id)
        if storage.primary_read_enabled():
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                return asyncio.run(self.get_answer_trace_async(agent_id, answer_trace_id))
        return self._get_answer_trace_local(agent_id, answer_trace_id)

    def list_evaluation_cases(self, agent_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self._knowledge_repository(agent_id).list_evaluation_cases(limit=limit))

    def update_evaluation_case(self, agent_id: str, case_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = _normalize_agent_id(agent_id)
        repository = self._knowledge_repository(normalized)
        expected_sources = payload.get("expected_sources")
        expected_layers = payload.get("expected_layers")
        updated = repository.update_evaluation_case(
            case_key,
            expected_sources=expected_sources if isinstance(expected_sources, list) else None,
            expected_layers=expected_layers if isinstance(expected_layers, list) else None,
            reference_answer=(
                payload.get("reference_answer") if isinstance(payload.get("reference_answer"), str) else None
            ),
            status=payload.get("status") if isinstance(payload.get("status"), str) else None,
            gold_source_kind=payload.get("gold_source_kind")
            if isinstance(payload.get("gold_source_kind"), str)
            else None,
            validated_by=payload.get("validated_by") if isinstance(payload.get("validated_by"), str) else None,
            validated_at=payload.get("validated_at") if isinstance(payload.get("validated_at"), str) else None,
            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None,
        )
        if not updated:
            raise KeyError(case_key)
        cases = cast(list[dict[str, Any]], repository.list_evaluation_cases(limit=500))
        case = next((item for item in cases if str(item.get("case_key") or "") == case_key), None)
        return case or {"case_key": case_key}

    def list_evaluation_runs(
        self,
        agent_id: str,
        *,
        case_key: str | None = None,
        strategy: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        repository = self._knowledge_repository(agent_id)
        return cast(
            list[dict[str, Any]],
            repository.list_evaluation_runs(
                case_key=case_key,
                strategy=strategy,
                limit=limit,
            ),
        )

    def seed_evaluation_cases(self, agent_id: str, *, limit: int = 50) -> dict[str, Any]:
        normalized = _normalize_agent_id(agent_id)
        from koda.knowledge.evaluation import seed_cases_from_sources

        created = 0
        governance_store = self._knowledge_governance_store()
        repository = self._knowledge_repository(normalized)
        approved_runbooks = cast(
            list[dict[str, Any]],
            governance_store.list_approved_runbooks(agent_id=normalized, limit=limit),
        )
        corrected_episodes = cast(
            list[dict[str, Any]],
            governance_store.list_execution_episodes(agent_id=normalized, feedback_status="corrected", limit=limit),
        )
        promoted_episodes = cast(
            list[dict[str, Any]],
            governance_store.list_execution_episodes(agent_id=normalized, feedback_status="promote", limit=limit),
        )
        failed_episodes = cast(
            list[dict[str, Any]],
            governance_store.list_execution_episodes(agent_id=normalized, feedback_status="failed", limit=limit),
        )
        risky_episodes = cast(
            list[dict[str, Any]],
            governance_store.list_execution_episodes(agent_id=normalized, feedback_status="risky", limit=limit),
        )
        cases = seed_cases_from_sources(
            approved_runbooks=approved_runbooks,
            human_corrected_episodes=corrected_episodes + promoted_episodes,
            negative_control_episodes=failed_episodes + risky_episodes,
        )
        for case_payload in cases[:limit]:
            repository.upsert_evaluation_case(
                case_key=case_payload["case_key"],
                query_text=case_payload["query_text"],
                source_task_id=case_payload["source_task_id"],
                task_kind=case_payload["task_kind"],
                project_key=case_payload["project_key"],
                environment=case_payload["environment"],
                team=case_payload["team"],
                modality=case_payload["modality"],
                expected_sources=case_payload["expected_sources"],
                expected_layers=case_payload["expected_layers"],
                reference_answer=case_payload["reference_answer"],
                status=case_payload["status"],
                gold_source_kind=case_payload["gold_source_kind"],
                metadata=case_payload["metadata"],
            )
            created += 1
        return {"ok": True, "seeded": created}

    def create_eval_case_from_run(self, agent_id: str, task_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        execution = self.get_dashboard_execution(normalized, int(task_id))
        if execution is None:
            raise KeyError(str(task_id))

        from koda.services.evals import build_eval_case_from_run
        from koda.services.metrics import EVAL_CASE_EVENTS

        repository = self._knowledge_repository(normalized)
        run_graph = execution.get("run_graph") if isinstance(execution.get("run_graph"), dict) else None
        replay = execution.get("run_replay") if isinstance(execution.get("run_replay"), dict) else None
        case_payload = build_eval_case_from_run(
            agent_id=normalized,
            task_id=int(task_id),
            execution=execution,
            run_graph=run_graph,
            replay=replay,
            payload=payload,
        )
        repository.upsert_evaluation_case(**case_payload)
        case = repository.get_evaluation_case(str(case_payload["case_key"])) or case_payload
        self._emit_eval_audit_event(
            normalized,
            event_type="eval.case_created",
            task_id=int(task_id),
            details={
                "schema_version": "eval_case.v1",
                "case_key": case_payload["case_key"],
                "source": "execution_run",
            },
        )
        EVAL_CASE_EVENTS.labels(agent_id=normalized, event="created", status=str(case.get("status") or "draft")).inc()
        return {"schema_version": "eval_case.v1", **case}

    def list_eval_cases(self, agent_id: str, *, limit: int = 100) -> dict[str, Any]:
        return {
            "schema_version": "eval_case.v1",
            "items": self.list_evaluation_cases(agent_id, limit=limit),
        }

    def update_eval_case(self, agent_id: str, case_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        case = self.update_evaluation_case(agent_id, case_key, payload)
        return {"schema_version": "eval_case.v1", **case}

    def run_eval_suite(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        from koda.services.evals import OFFLINE_REPLAY_STRATEGY, build_eval_run_batch
        from koda.services.metrics import EVAL_RUN_CASES, KNOWLEDGE_EVALUATION_RUNS, KNOWLEDGE_EVALUATION_SCORE

        repository = self._knowledge_repository(normalized)
        requested_keys = {str(item) for item in payload.get("case_keys") or [] if str(item)}
        raw_cases = repository.list_evaluation_cases(limit=int(payload.get("limit") or 100))
        cases = [
            case
            for case in raw_cases
            if str(case.get("status") or "draft") != "archived"
            and (not requested_keys or str(case.get("case_key") or "") in requested_keys)
        ]
        batch = build_eval_run_batch(
            agent_id=normalized,
            cases=cases,
            suite_id=str(payload.get("suite_id") or "default"),
            requested_by=str(payload.get("requested_by") or ""),
        )
        repository.upsert_eval_run_batch(batch)
        for result in batch.get("case_results") or []:
            if not isinstance(result, dict):
                continue
            status = str(result.get("status") or "failed")
            metrics_payload = dict(result.get("metrics") or {})
            repository.create_evaluation_run(
                case_key=str(result.get("case_key") or ""),
                strategy=OFFLINE_REPLAY_STRATEGY,
                task_success_proxy=float(metrics_payload.get("task_success_proxy") or result.get("score") or 0.0),
                metrics_payload={
                    **metrics_payload,
                    "status": status,
                    "failures": list(result.get("failures") or []),
                    "warnings": list(result.get("warnings") or []),
                    "run_id": batch["run_id"],
                },
            )
            EVAL_RUN_CASES.labels(agent_id=normalized, strategy=OFFLINE_REPLAY_STRATEGY, status=status).inc()
            KNOWLEDGE_EVALUATION_RUNS.labels(agent_id=normalized, strategy=OFFLINE_REPLAY_STRATEGY, result=status).inc()
            for metric, value in metrics_payload.items():
                try:
                    KNOWLEDGE_EVALUATION_SCORE.labels(
                        agent_id=normalized, strategy=OFFLINE_REPLAY_STRATEGY, metric=str(metric)
                    ).observe(float(value))
                except (TypeError, ValueError):
                    continue
        if payload.get("create_improvement_proposals", True):
            proposals = self._create_improvement_proposals_from_eval_failures(normalized, batch)
            if proposals:
                batch["improvement_proposals"] = proposals
                summary = dict(batch.get("summary") or {})
                summary["improvement_proposals_created"] = len(proposals)
                batch["summary"] = summary
                repository.upsert_eval_run_batch(batch)
        self._emit_eval_audit_event(
            normalized,
            event_type="eval.suite_run",
            details={
                "schema_version": "eval_run.v1",
                "run_id": batch["run_id"],
                "status": batch["status"],
                "summary": batch.get("summary") or {},
            },
        )
        return batch

    def _create_improvement_proposals_from_eval_failures(
        self,
        agent_id: str,
        batch: dict[str, Any],
    ) -> list[dict[str, Any]]:
        service = self._improvement_proposal_service(agent_id)
        proposals: list[dict[str, Any]] = []
        run_id = str(batch.get("run_id") or "")
        suite_id = str(batch.get("suite_id") or "default")
        for result in batch.get("case_results") or []:
            if not isinstance(result, dict) or str(result.get("status") or "") != "failed":
                continue
            case_key = str(result.get("case_key") or "")
            failures = [item for item in result.get("failures") or [] if isinstance(item, dict)]
            categories = {str(item.get("category") or "") for item in failures}
            category_key = ",".join(sorted(item for item in categories if item)) or "eval_failure"
            proposal_type = "tool_policy" if categories & {"tool_regression", "policy_regression"} else "eval_case"
            risk_class = "high" if proposal_type == "tool_policy" else "medium"
            raw_metadata = result.get("metadata")
            metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
            source_task_id = metadata.get("source_task_id")
            source_run_graph_id = str(metadata.get("source_run_graph_id") or "").strip()
            source_run_graph_node_ids = [
                str(item) for item in metadata.get("source_run_graph_node_ids") or [] if str(item or "").strip()
            ]
            source_ref = f"eval:{suite_id}:{case_key or 'unknown'}:{category_key}"
            evidence_refs: list[dict[str, Any]] = [
                {"kind": "eval_run", "id": run_id},
                {"kind": "eval_case", "case_key": case_key},
            ]
            if source_task_id is not None:
                evidence_refs.append({"kind": "source_task", "task_id": source_task_id})
            if source_run_graph_id:
                evidence_refs.append({"kind": "run_graph", "id": source_run_graph_id})
            evidence_refs.extend(
                {"kind": "run_graph_node", "id": node_id} for node_id in source_run_graph_node_ids[:20]
            )
            requested_proposal_type = str(metadata.get("proposal_type") or result.get("proposal_type") or "").strip()
            skill_id = str(metadata.get("skill_id") or result.get("skill_id") or "").strip()
            if requested_proposal_type == "skill" or skill_id or "skill_regression" in categories:
                proposal = service.create_skill_proposal_from_evidence(
                    {
                        "source_kind": "eval",
                        "source_ref": source_ref,
                        "skill_id": skill_id or case_key or "skill",
                        "summary": f"Draft skill proposal after eval failure for {case_key or 'unknown case'}.",
                        "observed_count": metadata.get("observed_count") or 1,
                        "evidence_refs": evidence_refs,
                        "instruction_preview": metadata.get("instruction_preview") or "",
                        "validation_plan": {
                            "suite_id": suite_id,
                            "case_key": case_key,
                            "required": ["scanner_allow_or_review", "offline_eval_pass"],
                        },
                        "run_graph_node_ids": source_run_graph_node_ids,
                    },
                    requested_by="eval",
                )
                self._record_improvement_proposal_event(agent_id, "created_from_eval", proposal)
                proposals.append(
                    {
                        "schema_version": "improvement_proposal.v1",
                        "proposal_id": proposal.get("proposal_id"),
                        "status": proposal.get("status"),
                        "proposal_type": proposal.get("proposal_type"),
                        "case_key": case_key,
                    }
                )
                continue
            proposal = service.create(
                {
                    "source_kind": "eval",
                    "source_ref": source_ref,
                    "proposal_type": proposal_type,
                    "summary": f"Review {proposal_type} after eval failure for {case_key or 'unknown case'}.",
                    "evidence_refs": evidence_refs,
                    "diff_preview": {
                        "proposed_change": "Create a reviewed improvement from deterministic eval failure evidence.",
                        "failures": failures[:5],
                        "score": result.get("score"),
                        "metrics": result.get("metrics") or {},
                    },
                    "risk_class": risk_class,
                    "validation_plan": {
                        "strategy": "offline_replay",
                        "suite_id": suite_id,
                        "case_key": case_key,
                    },
                    "rollback_plan": {
                        "strategy": "ledger_only",
                        "effects": [
                            {
                                "effect_kind": "ledger_only",
                                "target_ref": source_ref,
                                "before_ref": {"status": "eval_failure_unreviewed", "case_key": case_key},
                                "after_ref": {"status": "proposal_applied", "proposal_type": proposal_type},
                            }
                        ],
                    },
                    "status": "pending_review",
                    "reviewer": "eval",
                    "run_graph_node_ids": source_run_graph_node_ids,
                },
                requested_by="eval",
            )
            self._record_improvement_proposal_event(agent_id, "created_from_eval", proposal)
            proposals.append(
                {
                    "schema_version": "improvement_proposal.v1",
                    "proposal_id": proposal.get("proposal_id"),
                    "status": proposal.get("status"),
                    "proposal_type": proposal.get("proposal_type"),
                    "case_key": case_key,
                }
            )
        return proposals

    def list_eval_runs(self, agent_id: str, *, limit: int = 50) -> dict[str, Any]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        repository = self._knowledge_repository(normalized)
        return {
            "schema_version": "eval_run.v1",
            "items": repository.list_eval_run_batches(limit=limit),
            "legacy_items": self.list_evaluation_runs(normalized, limit=limit),
        }

    def get_eval_run(self, agent_id: str, run_id: str) -> dict[str, Any]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        batch = self._knowledge_repository(normalized).get_eval_run_batch(run_id)
        if batch is None:
            raise KeyError(run_id)
        return dict(batch)

    def create_trajectory_export(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        from koda.services.evals import build_trajectory_export
        from koda.services.metrics import TRAJECTORY_EXPORTS

        repository = self._knowledge_repository(normalized)
        try:
            task_id = int(payload.get("task_id") or 0)
        except (TypeError, ValueError):
            task_id = 0
        if task_id <= 0:
            case_key = str(payload.get("case_key") or "")
            case = repository.get_evaluation_case(case_key) if case_key else None
            task_id = int((case or {}).get("source_task_id") or 0)
        if task_id <= 0:
            run_id = str(payload.get("run_id") or "").strip()
            batch = repository.get_eval_run_batch(run_id) if run_id else None
            for result in list((batch or {}).get("case_results") or []):
                if not isinstance(result, dict):
                    continue
                case_key = str(result.get("case_key") or "")
                case = repository.get_evaluation_case(case_key) if case_key else None
                task_id = int((case or {}).get("source_task_id") or 0)
                if task_id > 0:
                    break
        if task_id <= 0:
            raise ValueError("trajectory export requires task_id or an eval case with source_task_id")
        execution = self.get_dashboard_execution(normalized, task_id)
        if execution is None:
            raise KeyError(str(task_id))
        export = build_trajectory_export(
            agent_id=normalized,
            task_id=task_id,
            execution=execution,
            run_graph=execution.get("run_graph") if isinstance(execution.get("run_graph"), dict) else None,
            replay=execution.get("run_replay") if isinstance(execution.get("run_replay"), dict) else None,
        )
        export["status"] = "created"
        repository.create_trajectory_export(export)
        self._emit_eval_audit_event(
            normalized,
            event_type="eval.trajectory_export_created",
            task_id=task_id,
            details={
                "schema_version": "trajectory_export.v1",
                "export_id": export["export_id"],
                "record_count": export["record_count"],
                "package_hash": export["package_hash"],
            },
        )
        TRAJECTORY_EXPORTS.labels(agent_id=normalized, status="created").inc()
        return export

    def get_release_quality_latest(self, agent_id: str) -> dict[str, Any]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        from koda.services.evals import build_release_quality_report
        from koda.services.metrics import RELEASE_QUALITY_GATES

        repository = self._knowledge_repository(normalized)
        runs = repository.list_eval_run_batches(limit=20)
        exports = repository.list_trajectory_exports(limit=20)
        run_graphs = self._release_quality_run_graphs(normalized, repository=repository, runs=runs)
        report = build_release_quality_report(
            agent_id=normalized,
            latest_run=runs[0] if runs else None,
            recent_runs=runs,
            trajectory_exports=exports,
            run_graphs=run_graphs,
            require_run_graphs=bool(runs),
        )
        self._emit_eval_audit_event(
            normalized,
            event_type="eval.release_quality_checked",
            details={
                "schema_version": "release_quality.v1",
                "status": report["status"],
                "gates": report.get("gates") or {},
            },
        )
        RELEASE_QUALITY_GATES.labels(agent_id=normalized, status=str(report["status"])).inc()
        return report

    def get_quality_cockpit_overview(self) -> dict[str, Any]:
        from koda.services.quality_cockpit import build_quality_cockpit

        payload: dict[str, Any] = {"agent_quality": [], "eval_runs": []}
        for agent in self.list_agents():
            agent_id = str(agent.get("id") or "").strip()
            if not agent_id:
                continue
            agent_payload = self._quality_cockpit_payload_for_agent(agent_id)
            payload["agent_quality"].extend(agent_payload.get("agent_quality") or [])
            payload["eval_runs"].extend(agent_payload.get("eval_runs") or [])
            for key in ("tool_quality", "skill_quality", "model_quality", "squad_quality"):
                payload.setdefault(key, []).extend(agent_payload.get(key) or [])
        return build_quality_cockpit(payload, agent_id="ALL")

    def get_quality_cockpit_agent(self, agent_id: str) -> dict[str, Any]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        from koda.services.quality_cockpit import build_quality_cockpit

        payload = self._quality_cockpit_payload_for_agent(normalized)
        with contextlib.suppress(Exception):
            payload["release_quality"] = self.get_release_quality_latest(normalized)
        return build_quality_cockpit(payload, agent_id=normalized)

    def create_quality_failure_proposal(
        self,
        *,
        agent_id: str,
        failure_id: str,
        requested_by: str = "quality_cockpit",
    ) -> dict[str, Any]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        from koda.services.quality_cockpit import build_quality_proposal_payload

        cockpit = self.get_quality_cockpit_agent(normalized)
        failure = next(
            (
                item
                for item in cockpit.get("top_failures") or []
                if isinstance(item, dict) and str(item.get("failure_id") or "") == failure_id
            ),
            None,
        )
        if failure is None:
            raise KeyError(failure_id)
        payload = build_quality_proposal_payload(
            failure,
            agent_id=normalized,
            cockpit_id=str(cockpit.get("cockpit_id") or ""),
            status="pending_review",
        )
        proposal = self._improvement_proposal_service(normalized).create(payload, requested_by=requested_by)
        self._record_improvement_proposal_event(normalized, "created_from_quality_cockpit", proposal)
        return cast(dict[str, Any], proposal)

    def _quality_cockpit_payload_for_agent(self, agent_id: str) -> dict[str, Any]:
        repository = self._knowledge_repository(agent_id)
        try:
            eval_runs = repository.list_eval_run_batches(limit=20)
        except Exception:
            eval_runs = []
        execution_rows: list[dict[str, Any]] = []
        route_outcomes: list[dict[str, Any]] = []
        try:
            executions = self.list_dashboard_executions(agent_id, limit=50)
        except Exception:
            executions = []
        for execution in executions:
            status = str(execution.get("status") or "")
            cost = execution.get("cost_usd") or execution.get("costUsd") or 0.0
            execution_rows.append(
                {
                    "dimension": "agent",
                    "entity_id": agent_id,
                    "agent_id": agent_id,
                    "status": "passed" if status in {"completed", "success"} else "failed",
                    "quality_score": 1.0 if status in {"completed", "success"} else 0.0,
                    "cost_usd": cost,
                    "failures": (
                        []
                        if status in {"completed", "success"}
                        else [{"category": "runtime_failure", "message": status or "execution did not complete"}]
                    ),
                    "run_graph_node_ids": execution.get("run_graph_node_ids") or [],
                }
            )
            model = str(execution.get("model") or execution.get("model_id") or "").strip()
            if model:
                execution_rows.append(
                    {
                        "dimension": "model",
                        "entity_id": model,
                        "agent_id": agent_id,
                        "status": "passed" if status in {"completed", "success"} else "failed",
                        "quality_score": 1.0 if status in {"completed", "success"} else 0.0,
                        "cost_usd": cost,
                    }
                )
            route_outcomes.extend(self._route_outcomes_from_execution(agent_id, execution))
        return {
            "agent_quality": execution_rows
            or [{"dimension": "agent", "entity_id": agent_id, "agent_id": agent_id, "quality_score": 0.0}],
            "eval_runs": eval_runs,
            "route_outcomes": route_outcomes,
        }

    def _route_outcomes_from_execution(self, agent_id: str, execution: dict[str, Any]) -> list[dict[str, Any]]:
        raw_outcomes = execution.get("route_outcomes")
        if isinstance(raw_outcomes, list):
            return [dict(item) for item in raw_outcomes if isinstance(item, dict)]
        run_graph = execution.get("run_graph")
        if not isinstance(run_graph, dict):
            return []
        outcomes: list[dict[str, Any]] = []
        for node in run_graph.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            node_type = str(node.get("node_type") or node.get("type") or "")
            if node_type != "agent_request":
                continue
            raw_payload = node.get("payload")
            payload: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else {}
            selected = payload.get("selected_agent_ids") or payload.get("targets") or []
            if isinstance(selected, str):
                selected = [selected]
            for selected_agent in selected:
                selected_id = str(selected_agent or "").strip()
                if not selected_id:
                    continue
                execution_ref = execution.get("id") or execution.get("task_id")
                outcomes.append(
                    {
                        "schema_version": "route_outcome.v1",
                        "outcome_id": f"route_outcome:{agent_id}:{execution_ref}:{selected_id}",
                        "agent_id": selected_id,
                        "route_source": str(payload.get("source") or "run_graph"),
                        "status": "success"
                        if str(execution.get("status") or "") in {"completed", "success"}
                        else "failure",
                        "cost_usd": execution.get("cost_usd") or execution.get("costUsd") or 0.0,
                        "latency_ms": execution.get("duration_ms"),
                        "run_graph_node_id": str(node.get("node_id") or node.get("id") or ""),
                    }
                )
        return outcomes

    def _release_quality_run_graphs(
        self,
        agent_id: str,
        *,
        repository: Any,
        runs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        task_ids: set[int] = set()
        try:
            cases = repository.list_evaluation_cases(limit=50)
        except Exception:
            cases = []
        for case in cases:
            raw_task_id = case.get("source_task_id") if isinstance(case, dict) else None
            try:
                if raw_task_id is not None:
                    task_ids.add(int(raw_task_id))
            except (TypeError, ValueError):
                continue
        for run in runs:
            for result in run.get("case_results") or []:
                if not isinstance(result, dict):
                    continue
                raw_task_id = result.get("source_task_id") or (result.get("metadata") or {}).get("source_task_id")
                try:
                    if raw_task_id is not None:
                        task_ids.add(int(raw_task_id))
                except (TypeError, ValueError):
                    continue
        graphs: list[dict[str, Any]] = []
        for task_id in sorted(task_ids):
            graph = self.get_dashboard_execution_run_graph(agent_id, task_id)
            if isinstance(graph, dict) and graph:
                graphs.append(graph)
            else:
                graphs.append(
                    {
                        "schema_version": "run_graph.v1",
                        "graph_id": f"missing:{agent_id}:{task_id}",
                        "agent_id": agent_id,
                        "task_id": task_id,
                        "scenario": "missing",
                        "nodes": [],
                        "edges": [],
                    }
                )
        return graphs

    def _emit_eval_audit_event(
        self,
        agent_id: str,
        *,
        event_type: str,
        details: dict[str, Any],
        task_id: int | None = None,
    ) -> None:
        from koda.services.audit import AuditEvent, emit

        emit(AuditEvent(event_type=event_type, agent_id=agent_id, task_id=task_id, details=details))

    def _used_runtime_health_ports(self, *, exclude_agent_id: str = "") -> set[int]:
        excluded = _normalize_agent_id(exclude_agent_id) if exclude_agent_id else ""
        used: set[int] = set()
        for row in fetch_all("SELECT id, runtime_endpoint_json FROM cp_agent_definitions ORDER BY id ASC"):
            row_agent_id = _normalize_agent_id(str(row["id"]))
            if excluded and row_agent_id == excluded:
                continue
            port = _runtime_health_port_from_endpoint(
                _safe_json_object(json_load(str(row["runtime_endpoint_json"] or "{}"), {}))
            )
            if port > 0:
                used.add(port)
        return used

    def _normalize_runtime_endpoint_for_agent(
        self,
        agent_id: str,
        runtime_endpoint: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = _normalize_agent_id(agent_id)
        primary_agent = _normalize_agent_id(os.environ.get("AGENT_ID") or AGENT_ID or "KODA")
        endpoint = dict(_safe_json_object(runtime_endpoint))
        requested_port = _runtime_health_port_from_endpoint(endpoint)
        default_port = 8080 if normalized == primary_agent else 8081
        used_ports = self._used_runtime_health_ports(exclude_agent_id=normalized)
        resolved_port = requested_port if requested_port > 0 else default_port
        if normalized == primary_agent:
            endpoint.update(_runtime_endpoint_payload_for_port(resolved_port))
            return endpoint
        if resolved_port in used_ports:
            resolved_port = default_port
            while resolved_port in used_ports:
                resolved_port += 1
        endpoint.update(_runtime_endpoint_payload_for_port(resolved_port))
        return endpoint

    def create_agent(self, payload: dict[str, Any]) -> dict[str, Any]:
        agent_id = _normalize_agent_id(str(payload.get("id") or ""))
        display_name = str(payload.get("display_name") or agent_id.replace("_", " "))
        storage_namespace = str(payload.get("storage_namespace") or _slug(agent_id))
        appearance = _safe_json_object(payload.get("appearance"))
        runtime_endpoint = self._normalize_runtime_endpoint_for_agent(
            agent_id,
            _safe_json_object(payload.get("runtime_endpoint")),
        )
        metadata = _safe_json_object(payload.get("metadata"))
        status = _normalize_status(str(payload.get("status") or "paused"))
        workspace_id, squad_id = self._resolve_agent_organization(
            _safe_json_object(payload.get("organization")) or None
        )
        now = now_iso()
        execute(
            """
            INSERT INTO cp_agent_definitions (
                id, display_name, status, appearance_json, storage_namespace, runtime_endpoint_json,
                applied_version, desired_version, metadata_json, workspace_id, squad_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                agent_id,
                display_name,
                status,
                json_dump(appearance),
                storage_namespace,
                json_dump(runtime_endpoint),
                json_dump(metadata),
                workspace_id,
                squad_id,
                now,
                now,
            ),
        )
        return self.get_agent(agent_id) or {}

    def update_agent(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized, current = self._require_agent_row(agent_id)
        display_name = str(payload.get("display_name") or current["display_name"])
        status = _normalize_status(str(payload.get("status") or current["status"]))
        appearance = _safe_json_object(payload.get("appearance")) or json_load(current["appearance_json"], {})
        runtime_endpoint = _safe_json_object(payload.get("runtime_endpoint")) or json_load(
            current["runtime_endpoint_json"], {}
        )
        runtime_endpoint = self._normalize_runtime_endpoint_for_agent(normalized, runtime_endpoint)
        metadata = json_load(current["metadata_json"], {})
        metadata.update(_safe_json_object(payload.get("metadata")))
        storage_namespace = str(payload.get("storage_namespace") or current["storage_namespace"])
        organization_payload = payload.get("organization")
        workspace_id, squad_id = self._resolve_agent_organization(
            _safe_json_object(organization_payload) if isinstance(organization_payload, dict) else None,
            current_row=current,
        )
        execute(
            """
            UPDATE cp_agent_definitions
            SET display_name = ?, status = ?, appearance_json = ?, storage_namespace = ?,
                runtime_endpoint_json = ?, metadata_json = ?, workspace_id = ?, squad_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                display_name,
                status,
                json_dump(appearance),
                storage_namespace,
                json_dump(runtime_endpoint),
                json_dump(metadata),
                workspace_id,
                squad_id,
                now_iso(),
                normalized,
            ),
        )
        return self.get_agent(normalized) or {}

    def archive_agent(self, agent_id: str) -> bool:
        normalized, _ = self._require_agent_row(agent_id)
        execute(
            "UPDATE cp_agent_definitions SET status = ?, updated_at = ? WHERE id = ?",
            ("archived", now_iso(), normalized),
        )
        return True

    # Tables that hold per-agent state and must be purged on hard delete.
    # Order does not matter — each row is scoped by agent_id — but cp_agent_definitions
    # is written last so the main row survives if any cascade step fails.
    _AGENT_CASCADE_TABLES: tuple[str, ...] = (
        "cp_agent_sections",
        "cp_agent_documents",
        "cp_agent_config_versions",
        "cp_apply_operations",
        "cp_knowledge_assets",
        "cp_template_assets",
        "cp_skill_assets",
        "cp_mcp_agent_connections",
        "cp_mcp_tool_policies",
        "cp_mcp_discovered_tools",
        "cp_mcp_oauth_tokens",
        "cp_mcp_oauth_sessions",
        "cp_agent_connections",
    )

    def delete_agent(self, agent_id: str) -> bool:
        """Hard-delete an agent and every dependent cp_* row.

        Returns True if the agent existed and was removed, False if it was
        already gone (idempotent — repeated DELETE calls should not raise).
        Runtime / audit tables (tasks, query_history, audit_events) are
        intentionally left alone so historical records survive.
        """
        try:
            normalized, _ = self._require_agent_row(agent_id)
        except KeyError:
            return False
        for table in self._AGENT_CASCADE_TABLES:
            execute(f"DELETE FROM {table} WHERE agent_id = ?", (normalized,))
        execute("DELETE FROM cp_agent_definitions WHERE id = ?", (normalized,))
        return True

    def clone_agent(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        source = self.get_agent(agent_id)
        if source is None:
            raise KeyError(agent_id)
        target_id = _normalize_agent_id(str(payload.get("id") or ""))
        cloned = self.create_agent(
            {
                "id": target_id,
                "display_name": payload.get("display_name") or f"{source['display_name']} Copy",
                "appearance": source.get("appearance"),
                "storage_namespace": payload.get("storage_namespace") or _slug(target_id),
                "runtime_endpoint": source.get("runtime_endpoint"),
                "status": payload.get("status") or "paused",
                "metadata": source.get("metadata"),
                "organization": payload["organization"] if "organization" in payload else source.get("organization"),
            }
        )
        for section, data in source.get("sections", {}).items():
            self.put_section(target_id, section, {"data": data})
        for kind, content in source.get("documents", {}).items():
            if content:
                self.upsert_document(target_id, kind, {"content_md": content})
        for asset in source.get("knowledge_assets", []):
            copied = dict(asset)
            copied.pop("id", None)
            self.upsert_knowledge_asset(target_id, copied)
        for asset in source.get("templates", []):
            copied = dict(asset)
            copied.pop("id", None)
            copied.pop("scope", None)
            self.upsert_template_asset(target_id, copied)
        for asset in source.get("skills", []):
            copied = dict(asset)
            copied.pop("id", None)
            copied.pop("scope", None)
            self.upsert_skill_asset(target_id, copied)
        return cloned

    def activate_agent(self, agent_id: str) -> dict[str, Any]:
        result = self.update_agent(agent_id, {"status": "active"})
        # Wake the supervisor immediately so the worker spawns without
        # waiting for the next poll cycle. Items previously rolled back to
        # 'queued' by ``pause_agent`` will be picked up by the fresh runtime.
        from koda.control_plane.lifecycle_events import notify_lifecycle_change

        notify_lifecycle_change(reason=f"activate:{agent_id}")
        self._emit_lifecycle_audit_event(
            agent_id,
            event_type="control_plane.agent_activated",
            details={"agent_id": str(agent_id), "to_status": "active"},
        )
        return result

    def pause_agent(self, agent_id: str) -> dict[str, Any]:
        result = self.update_agent(agent_id, {"status": "paused"})
        # Rollback every in-flight queue item to ``queued`` so the operator
        # can resume from a clean slate. The runtime worker is killed by
        # the supervisor (no idle wait); without this rollback the killed
        # runtime would leave items orphaned in ``running`` forever.
        rolled_back = self._rollback_in_flight_queue_items_for_pause(agent_id)
        from koda.control_plane.lifecycle_events import notify_lifecycle_change

        notify_lifecycle_change(reason=f"pause:{agent_id}")
        self._emit_lifecycle_audit_event(
            agent_id,
            event_type="control_plane.agent_paused",
            details={
                "agent_id": str(agent_id),
                "to_status": "paused",
                "rolled_back_queue_items": int(rolled_back),
            },
        )
        return result

    def _rollback_in_flight_queue_items_for_pause(self, agent_id: str) -> int:
        """Mark every running/retrying queue item back to ``queued``.

        Returns the number of rows rolled back so callers can record it on
        the structured pause audit event.

        Called from ``pause_agent``. The combination of:
          1. supervisor force-stopping the worker process, and
          2. this rollback marking in-flight items back to 'queued'

        gives the operator the guarantee they asked for: pause interrupts
        in the exact moment, and the next activate picks up the queue
        cleanly without leaving zombie 'running' rows or losing pending
        user messages.
        """
        normalized = str(agent_id or "").strip()
        if not normalized:
            return 0
        try:
            return int(
                execute(
                    """
                    UPDATE runtime_queue_items
                    SET status = 'queued',
                        last_error = COALESCE(last_error, '') ||
                                     CASE WHEN COALESCE(last_error, '') = '' THEN ''
                                          ELSE ' | ' END ||
                                     'paused_by_operator',
                        updated_at = ?
                    WHERE agent_id = ? AND status IN ('running', 'retrying')
                    """,
                    (now_iso(), normalized),
                )
                or 0
            )
        except Exception:
            log.exception("control_plane_pause_queue_rollback_failed", agent_id=normalized)
            return 0

    def _emit_lifecycle_audit_event(
        self,
        agent_id: str,
        *,
        event_type: str,
        details: dict[str, Any],
    ) -> None:
        """Append a structured row to ``audit_events`` for lifecycle changes.

        Thin wrapper kept on the manager so existing callers and tests
        keep their entry point. Implementation lives in
        :mod:`koda.control_plane.audit` so the supervisor (crash-loop
        detection) and any future caller emits exactly the same shape.
        """
        from koda.control_plane.audit import record_audit_event

        record_audit_event(agent_id, event_type=event_type, details=details)

    def get_global_defaults(self) -> dict[str, Any]:
        self.ensure_seeded()
        sections = self._load_global_sections()
        version_row = fetch_one("SELECT id FROM cp_global_default_versions ORDER BY id DESC LIMIT 1")
        return {
            "sections": sections,
            "version": int(version_row["id"]) if version_row else self._persist_global_default_version(sections),
        }

    def get_persistence_diagnostics(self) -> dict[str, Any]:
        """Return the real state of the persistence stack.

        Exposed via ``GET /api/control-plane/_diag/persistence`` so an operator
        seeing "saves don't persist" can curl/inspect the truth: is the
        Postgres backend available? How many rows are in cp_global_sections
        and cp_provider_connections? When was the last write? Without this
        endpoint the operator has to read source to figure out why writes
        appear to succeed but revert to defaults.
        """
        from koda.state.primary import get_primary_state_backend, postgres_primary_mode

        warnings: list[str] = []
        backend_available = False
        schema: str | None = None
        try:
            backend = get_primary_state_backend()
            backend_available = backend is not None
            if backend is not None:
                schema = str(getattr(backend, "schema", "") or "") or None
        except Exception as exc:  # noqa: BLE001 - surface diag failures to the caller
            warnings.append(f"backend_resolution_failed: {exc!r}")

        if postgres_primary_mode() and not backend_available:
            warnings.append(
                "STATE_BACKEND=postgres but KNOWLEDGE_V2_POSTGRES_DSN is empty or the shared "
                "backend refused to initialize. Saves will fail loudly with primary_backend_unavailable."
            )

        row_counts: dict[str, int | None] = {}
        last_updated_at: str | None = None
        for table in ("cp_global_sections", "cp_provider_connections", "cp_secret_values", "cp_agent_definitions"):
            try:
                row = fetch_one(f"SELECT COUNT(*) AS count FROM {table}")
                row_counts[table] = int(row["count"]) if row and row.get("count") is not None else 0
            except Exception as exc:  # noqa: BLE001
                row_counts[table] = None
                warnings.append(f"{table}_count_failed: {exc!r}")

        try:
            latest = fetch_one("SELECT MAX(updated_at) AS updated_at FROM cp_global_sections")
            if latest is not None:
                raw = latest.get("updated_at")
                last_updated_at = str(raw) if raw else None
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"last_updated_at_failed: {exc!r}")

        return {
            "state_backend": STATE_BACKEND,
            "postgres_primary_mode": postgres_primary_mode(),
            "primary_backend_available": backend_available,
            "postgres_schema": schema,
            "row_counts": row_counts,
            "last_updated_at": last_updated_at,
            "warnings": warnings,
        }

    def _persist_global_sections(self, sections: dict[str, dict[str, Any]]) -> int:
        for section, value in sections.items():
            execute(
                """
                INSERT INTO cp_global_sections (section, data_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(section) DO UPDATE SET data_json = excluded.data_json, updated_at = excluded.updated_at
                """,
                (section, json_dump(_safe_json_object(value)), now_iso()),
            )
        self._invalidate_global_sections_cache()
        # Post-write verification — read back and confirm the sections we just
        # wrote are visible. A silent failure in the DB layer (missing row,
        # no-op backend) becomes a loud 500 here instead of a 200 OK that
        # mysteriously reverts to defaults on reload.
        written_keys = {str(section) for section in sections}
        if written_keys:
            actual = self._load_global_sections()
            missing = sorted(key for key in written_keys if key not in actual)
            if missing:
                raise RuntimeError(
                    "persist_global_sections_lost: "
                    f"{missing} — write returned success but row is not visible on read. "
                    "Check that STATE_BACKEND=postgres has a working KNOWLEDGE_V2_POSTGRES_DSN."
                )
        return self._persist_global_default_version(sections)

    def _general_ui_meta(self, *, sections: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
        return _safe_json_object(self._access_section(sections).get("general_ui"))

    def _provider_enabled_from_settings(
        self,
        provider_id: str,
        legacy_settings: dict[str, Any],
        core_providers: dict[str, Any],
    ) -> bool:
        explicit = _safe_json_object(legacy_settings.get("providers")).get(f"{provider_id}_enabled")
        if isinstance(explicit, bool):
            return explicit
        provider_entry = _safe_json_object(_safe_json_object(core_providers.get("providers")).get(provider_id))
        return bool(provider_entry.get("enabled"))

    def _infer_usage_profile(
        self,
        legacy_settings: dict[str, Any],
        provider_catalog: dict[str, Any],
        *,
        sections: dict[str, dict[str, Any]] | None = None,
    ) -> str:
        meta_value = _nonempty_text(self._general_ui_meta(sections=sections).get("usage_profile")).lower()
        if meta_value in _GENERAL_MODEL_USAGE_PROFILES:
            return meta_value
        matched_tiers: list[str] = []
        providers_section = _safe_json_object(legacy_settings.get("providers"))
        for provider_id, payload in _safe_json_object(provider_catalog.get("providers")).items():
            if not self._provider_enabled_from_settings(provider_id, legacy_settings, provider_catalog):
                continue
            default_model = _nonempty_text(providers_section.get(f"{provider_id}_default_model"))
            tier_matches = {
                tier_name
                for tier_name in ("small", "medium", "large")
                if default_model
                and default_model == _nonempty_text(_safe_json_object(payload).get("tier_models", {}).get(tier_name))
            }
            if tier_matches:
                matched_tiers.append(next(iter(tier_matches)))
        if matched_tiers and all(tier == "small" for tier in matched_tiers):
            return "economy"
        if matched_tiers and all(tier == "large" for tier in matched_tiers):
            return "quality"
        return "balanced"

    def _infer_profile_from_presets(
        self,
        current_values: dict[str, Any],
        preset_catalog: dict[str, dict[str, Any]],
        *,
        meta_key: str,
        sections: dict[str, dict[str, Any]] | None = None,
        default: str,
    ) -> str:
        meta_value = _nonempty_text(self._general_ui_meta(sections=sections).get(meta_key)).lower()
        if meta_value in preset_catalog:
            return meta_value
        best_profile = default
        best_score = -1
        for profile_key, profile in preset_catalog.items():
            score = 0
            for setting_key, setting_value in _safe_json_object(profile.get("settings")).items():
                if current_values.get(setting_key) == setting_value:
                    score += 1
            if score > best_score:
                best_score = score
                best_profile = profile_key
        return best_profile

    def _custom_global_variables_payload(
        self,
        legacy_settings: dict[str, Any],
        *,
        sections: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        shared_meta = self._access_meta_map("shared_env_meta", sections=sections)
        system_meta = self._access_meta_map("system_env_meta", sections=sections)
        variables: list[dict[str, Any]] = []
        template_keys = {
            str(field["key"])
            for template in _GENERAL_INTEGRATION_CREDENTIAL_TEMPLATES.values()
            for field in template["fields"]
        }
        for entry in _normalize_env_entries(legacy_settings.get("shared_variables")):
            if entry["key"] in template_keys:
                continue
            variables.append(
                {
                    "key": entry["key"],
                    "type": "text",
                    "scope": "agent_grant",
                    "description": _nonempty_text(shared_meta.get(entry["key"], {}).get("description")),
                    "value": entry["value"],
                    "preview": entry["value"],
                    "value_present": True,
                }
            )
        for entry in _normalize_env_entries(legacy_settings.get("additional_env_vars")):
            if entry["key"] in template_keys:
                continue
            variables.append(
                {
                    "key": entry["key"],
                    "type": "text",
                    "scope": "system_only",
                    "description": _nonempty_text(system_meta.get(entry["key"], {}).get("description")),
                    "value": entry["value"],
                    "preview": entry["value"],
                    "value_present": True,
                }
            )
        for secret in self._current_global_secrets(sections=sections):
            if secret["secret_key"] in template_keys:
                continue
            variables.append(
                {
                    "key": str(secret["secret_key"]),
                    "type": "secret",
                    "scope": str(secret.get("usage_scope") or "system_only"),
                    "description": _nonempty_text(secret.get("description")),
                    "value": "",
                    # Never ship the masked preview — the UI shows only
                    # "stored" / action buttons; to see the value the
                    # operator must replace it.
                    "preview": "",
                    "value_present": True,
                }
            )
        return sorted(variables, key=lambda item: (item["type"] != "secret", item["key"]))

    def _general_review_warnings(self, values: dict[str, Any]) -> list[str]:
        warnings: list[str] = []
        models = _safe_json_object(values.get("models"))
        provider_connections: dict[str, dict[str, Any]] = {
            str(key): _safe_json_object(value)
            for key, value in _safe_json_object(values.get("provider_connections")).items()
        }
        enabled_providers = normalize_string_list(models.get("providers_enabled"))
        default_provider = _nonempty_text(models.get("default_provider")).lower()
        fallback_order = normalize_string_list(models.get("fallback_order"))
        if enabled_providers and default_provider not in enabled_providers:
            warnings.append("The default provider must be enabled.")
        if enabled_providers and not fallback_order:
            warnings.append("Defina ao menos uma ordem de fallback entre os providers habilitados.")
        if fallback_order and any(provider not in enabled_providers for provider in fallback_order):
            warnings.append("The fallback order contains providers that are not enabled.")
        for provider_id in enabled_providers:
            connection = provider_connections.get(provider_id, {})
            if provider_id in MANAGED_PROVIDER_IDS and not bool(connection.get("verified")):
                warnings.append(
                    f"{PROVIDER_TITLES[cast(Any, provider_id)]} precisa estar verificado "
                    "antes de ser habilitado globalmente."
                )
        if default_provider in MANAGED_PROVIDER_IDS and not bool(
            _safe_json_object(provider_connections.get(default_provider)).get("verified")
        ):
            warnings.append("The default provider must be connected and verified.")
        if any(
            provider in MANAGED_PROVIDER_IDS
            and not bool(_safe_json_object(provider_connections.get(provider)).get("verified"))
            for provider in fallback_order
        ):
            warnings.append("The fallback order includes providers that have not yet been verified.")
        elevenlabs_voice = _nonempty_text(models.get("elevenlabs_default_voice"))
        if elevenlabs_voice and not bool(_safe_json_object(provider_connections.get("elevenlabs")).get("verified")):
            warnings.append("Connect and verify ElevenLabs before setting the default voice for agents.")
        provider_catalog = self.get_core_providers()
        option_map = self._functional_model_option_map(provider_catalog)
        functional_defaults = _normalize_functional_model_defaults(models.get("functional_defaults"))
        for function_id, selection in functional_defaults.items():
            option = _safe_json_object(
                _safe_json_object(option_map.get(function_id)).get(
                    f"{selection.get('provider_id')}:{selection.get('model_id')}"
                )
            )
            if not option:
                warnings.append(f"O default de {function_id} referencia um provider/modelo desconhecido.")
                continue
            provider_id = _nonempty_text(option.get("provider_id")).lower()
            provider_payload = _safe_json_object(_safe_json_object(provider_catalog.get("providers")).get(provider_id))
            if not self._provider_selectable_for_function(
                function_id,
                provider_id,
                provider_payload,
                provider_connections,
            ):
                warnings.append(
                    f"{option.get('provider_title') or provider_id} precisa estar disponivel "
                    f"para usar o default de {function_id}."
                )

        resources = _safe_json_object(values.get("resources"))
        integrations = _safe_json_object(resources.get("integrations"))
        defaults_by_integration = {
            str(item.get("integration_key") or "").strip().lower(): _safe_json_object(item)
            for item in _safe_json_list(self.list_connection_defaults().get("items"))
            if str(item.get("kind") or "").strip().lower() == "core"
        }
        for integration_key, template in _GENERAL_INTEGRATION_CREDENTIAL_TEMPLATES.items():
            if not bool(integrations.get(f"{integration_key}_enabled")):
                continue
            payload = defaults_by_integration.get(integration_key, {})
            fields = _safe_json_list(payload.get("fields"))
            missing = [
                str(field.get("label") or field.get("key"))
                for field in fields
                if bool(field.get("required")) and not bool(field.get("value") or field.get("value_present"))
            ]
            if missing:
                warnings.append(
                    f"{template['title']} is enabled, but required credentials are missing: {', '.join(missing)}."
                )
        return warnings

    def _functional_model_catalog(self, provider_catalog: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        return build_function_model_catalog(_safe_json_object(provider_catalog.get("providers")))

    def _functional_model_option_map(self, provider_catalog: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
        option_map: dict[str, dict[str, dict[str, Any]]] = {}
        for function_id, items in self._functional_model_catalog(provider_catalog).items():
            function_options: dict[str, dict[str, Any]] = {}
            for item in items:
                provider_id = str(item.get("provider_id") or "").strip().lower()
                model_id = str(item.get("model_id") or "").strip()
                if not provider_id or not model_id:
                    continue
                function_options[f"{provider_id}:{model_id}"] = dict(item)
            option_map[function_id] = function_options
        return option_map

    def _provider_selectable_for_function(
        self,
        function_id: str,
        provider_id: str,
        provider_payload: dict[str, Any],
        provider_connections: dict[str, dict[str, Any]],
    ) -> bool:
        normalized = provider_id.strip().lower()
        if normalized in MANAGED_PROVIDER_IDS:
            connection = _safe_json_object(provider_connections.get(normalized))
            if normalized == "codex" and function_id in {"image", "transcription"}:
                auth_mode = _nonempty_text(connection.get("auth_mode")).lower()
                return bool(connection.get("api_key_present")) and auth_mode in {"", "api_key"}
            return bool(connection.get("verified"))
        command_present = bool(provider_payload.get("command_present", False))
        enabled = bool(provider_payload.get("enabled", False))
        category = str(provider_payload.get("category") or "general")
        if category == "voice" and normalized in {"kokoro", "supertonic"}:
            return True
        if normalized == "whispercpp" and function_id == "transcription":
            return enabled and command_present
        return enabled and (command_present or category in {"voice", "media"})

    def _resolve_general_functional_defaults(
        self,
        *,
        providers_section: dict[str, Any],
        provider_catalog: dict[str, Any],
    ) -> dict[str, dict[str, str]]:
        defaults = _normalize_functional_model_defaults(providers_section.get("functional_defaults"))
        providers = _safe_json_object(provider_catalog.get("providers"))
        if "general" not in defaults:
            default_provider = (
                _nonempty_text(providers_section.get("default_provider")).lower()
                or _nonempty_text(provider_catalog.get("default_provider")).lower()
            )
            if default_provider:
                provider_payload = _safe_json_object(providers.get(default_provider))
                default_model = _nonempty_text(
                    providers_section.get(f"{default_provider}_default_model")
                ) or _nonempty_text(provider_payload.get("default_model"))
                if default_model:
                    defaults["general"] = {
                        "provider_id": default_provider,
                        "model_id": default_model,
                    }
        if "audio" not in defaults:
            elevenlabs_connection = _safe_json_object(_safe_json_object(providers.get("elevenlabs")).get("connection"))
            elevenlabs_available = bool(
                elevenlabs_connection.get("verified")
                or elevenlabs_connection.get("configured")
                or elevenlabs_connection.get("api_key_present")
            )
            audio_provider = "elevenlabs" if elevenlabs_available else "kokoro"
            audio_model = (
                _nonempty_text(providers_section.get("elevenlabs_model"))
                or _nonempty_text(os.environ.get("ELEVENLABS_MODEL"))
                or "eleven_flash_v2_5"
            )
            if audio_provider == "kokoro":
                audio_model = (
                    _nonempty_text(providers_section.get("kokoro_default_model"))
                    or _nonempty_text(os.environ.get("KOKORO_DEFAULT_MODEL"))
                    or "kokoro-v1"
                )
            defaults["audio"] = {
                "provider_id": audio_provider,
                "model_id": audio_model,
            }
        if "transcription" not in defaults:
            whispercpp_payload = _safe_json_object(providers.get("whispercpp"))
            whispercpp_available = self._provider_selectable_for_function(
                "transcription",
                "whispercpp",
                whispercpp_payload,
                {},
            )
            if whispercpp_available:
                whisper_model = _nonempty_text(whispercpp_payload.get("default_model"))
                if not whisper_model:
                    for item in _safe_json_list(whispercpp_payload.get("functional_models")):
                        functional_model = _safe_json_object(item)
                        if _nonempty_text(functional_model.get("function_id")) == "transcription":
                            whisper_model = _nonempty_text(functional_model.get("model_id"))
                            break
                defaults["transcription"] = {
                    "provider_id": "whispercpp",
                    "model_id": whisper_model or "whisper-cpp-local",
                }
            else:
                codex_connection = _safe_json_object(_safe_json_object(providers.get("codex")).get("connection"))
                if self._provider_selectable_for_function(
                    "transcription",
                    "codex",
                    _safe_json_object(providers.get("codex")),
                    {"codex": codex_connection},
                ):
                    defaults["transcription"] = {
                        "provider_id": "codex",
                        "model_id": "whisper-1",
                    }
        return defaults

    def _resolve_general_effort_target(
        self,
        *,
        providers_section: dict[str, Any],
        provider_catalog: dict[str, Any],
    ) -> tuple[str, str]:
        functional_defaults = self._resolve_general_functional_defaults(
            providers_section=providers_section,
            provider_catalog=provider_catalog,
        )
        general_selection = _safe_json_object(functional_defaults.get("general"))
        provider_id = (
            _nonempty_text(general_selection.get("provider_id")).lower()
            or _nonempty_text(providers_section.get("default_provider")).lower()
        )
        providers = _safe_json_object(provider_catalog.get("providers"))
        provider_payload = _safe_json_object(providers.get(provider_id))
        model_id = (
            _nonempty_text(general_selection.get("model_id"))
            or _nonempty_text(providers_section.get(f"{provider_id}_default_model"))
            or _nonempty_text(provider_payload.get("default_model"))
        )
        return provider_id, model_id

    def _resolve_general_effort_default(
        self,
        *,
        providers_section: dict[str, Any],
        provider_catalog: dict[str, Any],
    ) -> dict[str, Any]:
        provider_id, model_id = self._resolve_general_effort_target(
            providers_section=providers_section,
            provider_catalog=provider_catalog,
        )
        effort_default = normalize_model_effort_selection(
            providers_section.get("effort_default"),
            provider_id=provider_id,
            model_id=model_id,
        )
        if effort_default:
            return effort_default
        return normalize_legacy_effort_selection(
            providers_section.get("effort_defaults"),
            provider_id=provider_id,
            model_id=model_id,
        )

    def _resolve_elevenlabs_api_key(self) -> str:
        api_key = self._provider_api_key_secret_value("elevenlabs")
        if api_key:
            return api_key.strip()
        merged = self._merged_global_env()
        return _nonempty_text(merged.get("ELEVENLABS_API_KEY") or os.environ.get("ELEVENLABS_API_KEY"))

    def _elevenlabs_voice_cache_signature(self, api_key: str) -> str:
        if not api_key:
            return "missing"
        return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]

    def _elevenlabs_fetch_subscription(self, api_key: str) -> dict[str, Any]:
        import time as _time

        signature = self._elevenlabs_voice_cache_signature(api_key)
        cache_key = f"subscription_{signature}"
        now = _time.time()
        cached = self._elevenlabs_subscription_cache.get(cache_key)
        if cached and (now - cached[0]) < 900:
            return dict(cached[1])

        if not api_key:
            empty: dict[str, Any] = {}
            self._elevenlabs_subscription_cache[cache_key] = (now, empty)
            return dict(empty)

        try:
            request = urllib.request.Request(
                "https://api.elevenlabs.io/v1/user/subscription",
                headers={
                    "xi-api-key": api_key,
                    "User-Agent": "koda/control-plane",
                },
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                data = json.loads(response.read())
            payload = _safe_json_object(data)
        except Exception:
            if cached:
                return dict(cached[1])
            payload = {}

        self._elevenlabs_subscription_cache[cache_key] = (now, payload)
        return dict(payload)

    @staticmethod
    def _elevenlabs_voice_api_availability(
        voice: dict[str, Any],
        subscription: dict[str, Any],
    ) -> tuple[bool, str]:
        tier = _nonempty_text(subscription.get("tier") or subscription.get("status")).lower()
        status = _nonempty_text(subscription.get("status")).lower()
        category = _nonempty_text(voice.get("category")).lower()
        free_tier = tier == "free" or status == "free"
        if free_tier and category in {"professional", "famous", "high_quality"}:
            return (
                False,
                "Voz da ElevenLabs Voice Library indisponivel via API no plano free.",
            )
        if free_tier and voice.get("free_users_allowed") is False:
            return (
                False,
                "Voz da ElevenLabs indisponivel via API no plano free.",
            )
        return True, ""

    def _elevenlabs_fetch_voice_catalog(self, api_key: str) -> dict[str, Any]:
        import time as _time

        signature = self._elevenlabs_voice_cache_signature(api_key)
        cache_key = f"catalog_{signature}"
        now = _time.time()
        cached = self._elevenlabs_voice_cache.get(cache_key)
        if cached and (now - cached[0]) < 900:
            return dict(cached[1])

        if not api_key:
            empty = {"items": [], "available_languages": [], "cached": False, "provider_connected": False}
            self._elevenlabs_voice_cache[cache_key] = (now, empty)
            return dict(empty)

        try:
            raw_voices: list[Any] = []
            next_page_token = ""
            for _page in range(10):
                params = {"page_size": "100", "include_total_count": "false"}
                if next_page_token:
                    params["next_page_token"] = next_page_token
                url = f"https://api.elevenlabs.io/v2/voices?{urllib.parse.urlencode(params)}"
                request = urllib.request.Request(
                    url,
                    headers={
                        "xi-api-key": api_key,
                        "User-Agent": "koda/control-plane",
                    },
                )
                with urllib.request.urlopen(request, timeout=15) as response:
                    data = json.loads(response.read())
                if isinstance(data, list):
                    raw_voices.extend(data)
                    break
                data_obj = _safe_json_object(data)
                raw_voices.extend(_safe_json_list(data_obj.get("voices")))
                if not bool(data_obj.get("has_more")):
                    break
                next_page_token = _nonempty_text(data_obj.get("next_page_token"))
                if not next_page_token:
                    break
        except Exception:
            if cached:
                stale = dict(cached[1])
                stale["cached"] = True
                return stale
            return {"items": [], "available_languages": [], "cached": False, "provider_connected": True}

        subscription = self._elevenlabs_fetch_subscription(api_key)
        subscription_tier = _nonempty_text(subscription.get("tier") or subscription.get("status"))
        items: list[dict[str, Any]] = []
        for voice in _safe_json_list(raw_voices):
            payload = _safe_json_object(voice)
            labels = _safe_json_object(payload.get("labels"))
            verified_languages = []
            for language_payload in _safe_json_list(payload.get("verified_languages")):
                language_entry = _safe_json_object(language_payload)
                language_code = canonicalize_elevenlabs_language(
                    language_entry.get("language") or language_entry.get("locale")
                )
                if not language_code:
                    continue
                language_label = (
                    _nonempty_text(language_entry.get("name"))
                    or _nonempty_text(language_entry.get("display_name"))
                    or elevenlabs_language_label(language_code)
                )
                verified_languages.append(
                    {
                        "code": language_code,
                        "label": language_label,
                        "locale": _nonempty_text(language_entry.get("locale")),
                        "model_id": _nonempty_text(language_entry.get("model_id")),
                        "accent": _nonempty_text(language_entry.get("accent")),
                        "preview_url": _nonempty_text(language_entry.get("preview_url")),
                    }
                )
            model_ids = normalize_string_list(payload.get("high_quality_base_model_ids"))
            api_available, api_availability_reason = self._elevenlabs_voice_api_availability(payload, subscription)
            items.append(
                {
                    "voice_id": _nonempty_text(payload.get("voice_id")),
                    "name": _nonempty_text(payload.get("name")) or "Sem nome",
                    "gender": _nonempty_text(labels.get("gender")),
                    "accent": _nonempty_text(labels.get("accent")),
                    "category": _nonempty_text(payload.get("category")),
                    "preview_url": _nonempty_text(payload.get("preview_url")),
                    "model_ids": model_ids,
                    "languages": verified_languages,
                    "api_available": api_available,
                    "api_availability_reason": api_availability_reason,
                }
            )

        items = [item for item in items if item["voice_id"]]
        items.sort(key=lambda item: str(item["name"]).casefold())
        catalog = {
            "items": items,
            "cached": False,
            "provider_connected": True,
            "subscription_tier": subscription_tier,
        }
        self._elevenlabs_voice_cache[cache_key] = (now, catalog)
        return dict(catalog)

    def get_elevenlabs_voice_catalog(self, language: str = "", model_id: str = "") -> dict[str, Any]:
        requested_language = canonicalize_elevenlabs_language(language)
        selected_model = _nonempty_text(model_id) or ELEVENLABS_DEFAULT_TTS_MODEL
        catalog = self._elevenlabs_fetch_voice_catalog(self._resolve_elevenlabs_api_key())
        items = list(_safe_json_list(catalog.get("items")))
        model_languages = elevenlabs_languages_for_model(selected_model)
        supported_language_codes = {str(item["code"]) for item in model_languages}
        model_items = []
        for voice in items:
            voice_obj = _safe_json_object(voice)
            model_ids = normalize_string_list(voice_obj.get("model_ids"))
            if model_ids and selected_model not in model_ids:
                continue
            model_items.append(voice_obj)
        if model_items:
            items = model_items
        if requested_language:
            verified_matches = []
            compatible_matches = []
            for voice in items:
                voice_obj = _safe_json_object(voice)
                languages = _safe_json_list(voice_obj.get("languages"))
                language_match = any(
                    elevenlabs_voice_language_matches(requested_language, _safe_json_object(entry))
                    for entry in languages
                )
                if language_match:
                    enriched = dict(voice_obj)
                    enriched["language_match"] = True
                    verified_matches.append(enriched)
                elif requested_language in supported_language_codes:
                    enriched = dict(voice_obj)
                    enriched["language_match"] = False
                    compatible_matches.append(enriched)
            items = verified_matches or compatible_matches
        items.sort(
            key=lambda item: (
                0 if bool(_safe_json_object(item).get("language_match")) else 1,
                str(_safe_json_object(item).get("name") or "").casefold(),
            )
        )
        return {
            "items": items,
            "available_languages": model_languages,
            "selected_language": requested_language,
            "selected_language_label": elevenlabs_language_label(requested_language) if requested_language else "",
            "model_id": selected_model,
            "cached": bool(catalog.get("cached")),
            "provider_connected": bool(catalog.get("provider_connected")),
            "subscription_tier": _nonempty_text(catalog.get("subscription_tier")),
        }

    def list_elevenlabs_voices(self, language: str = "", model_id: str = "") -> list[dict[str, str]]:
        items = self.get_elevenlabs_voice_catalog(language=language, model_id=model_id).get("items")
        return [cast(dict[str, str], _safe_json_object(item)) for item in _safe_json_list(items)]

    def list_ollama_models(self) -> list[dict[str, Any]]:
        items = self.get_ollama_model_catalog().get("items")
        return [cast(dict[str, Any], _safe_json_object(item)) for item in _safe_json_list(items)]

    def get_general_system_settings(self) -> dict[str, Any]:
        self.ensure_seeded()
        legacy_settings = self.get_system_settings()
        sections = self._system_settings_sections()
        merged_env = self._merged_global_env()
        provider_catalog = self.get_core_providers()
        functional_model_catalog = self._functional_model_catalog(provider_catalog)
        enabled_providers = [
            provider_id
            for provider_id in _user_selectable_provider_ids(provider_catalog)
            if self._provider_enabled_from_settings(provider_id, legacy_settings, provider_catalog)
        ]
        tools_section = _safe_json_object(legacy_settings.get("tools"))
        integrations_section = _safe_json_object(legacy_settings.get("integrations"))
        memory_section = _safe_json_object(legacy_settings.get("memory"))
        knowledge_section = _safe_json_object(legacy_settings.get("knowledge"))
        general_section = _safe_json_object(legacy_settings.get("general"))
        scheduler_section = _safe_json_object(legacy_settings.get("scheduler"))
        providers_section = _safe_json_object(legacy_settings.get("providers"))
        runtime_section = _safe_json_object(sections.get("runtime"))
        raw_memory_section = _safe_json_object(sections.get("memory"))
        raw_knowledge_section = _safe_json_object(sections.get("knowledge"))
        memory_policy = normalize_memory_policy(
            _overlay_known_policy_fields(
                normalize_memory_policy(_safe_json_object(raw_memory_section.get("policy"))),
                memory_section,
                _GENERAL_MEMORY_POLICY_FIELD_NAMES,
            )
        )
        raw_memory_profile = _safe_json_object(raw_memory_section.get("profile"))
        if raw_memory_profile and not _safe_json_object(memory_policy.get("profile")):
            memory_policy = normalize_memory_policy(
                _deep_merge_json_objects(memory_policy, {"profile": raw_memory_profile})
            )
        knowledge_policy = normalize_knowledge_policy(
            _overlay_known_policy_fields(
                normalize_knowledge_policy(_safe_json_object(raw_knowledge_section.get("policy"))),
                knowledge_section,
                _GENERAL_KNOWLEDGE_POLICY_FIELD_NAMES,
            )
        )
        autonomy_policy = normalize_autonomy_policy(
            _safe_json_object(runtime_section.get("autonomy_policy")) or self._autonomy_policy_from_env(merged_env)
        )
        account_values = {
            "owner_name": _nonempty_text(general_section.get("owner_name")),
            "owner_email": _nonempty_text(general_section.get("owner_email")),
            "owner_github": _nonempty_text(general_section.get("owner_github")),
            "default_work_dir": _nonempty_text(general_section.get("default_work_dir")),
            "project_dirs": normalize_string_list(general_section.get("project_dirs")),
            "scheduler_default_timezone": (
                _nonempty_text(scheduler_section.get("scheduler_default_timezone"))
                or _nonempty_text(os.environ.get("SCHEDULER_DEFAULT_TIMEZONE"))
                or "America/Sao_Paulo"
            ),
            "rate_limit_per_minute": general_section.get("rate_limit_per_minute"),
            "time_format": _nonempty_text(general_section.get("time_format")) or "24h",
        }
        model_values = {
            "providers_enabled": enabled_providers,
            "default_provider": (
                _nonempty_text(providers_section.get("default_provider"))
                or _nonempty_text(provider_catalog.get("default_provider"))
                or "claude"
            ),
            "fallback_order": (
                normalize_string_list(providers_section.get("fallback_order"))
                or normalize_string_list(provider_catalog.get("fallback_order"))
            ),
            "usage_profile": self._infer_usage_profile(legacy_settings, provider_catalog, sections=sections),
            "max_budget_usd": providers_section.get("max_budget_usd"),
            "max_total_budget_usd": providers_section.get("max_total_budget_usd"),
            "elevenlabs_default_language": _nonempty_text(providers_section.get("elevenlabs_default_language")),
            "elevenlabs_default_voice": _nonempty_text(providers_section.get("elevenlabs_default_voice"))
            or _nonempty_text(providers_section.get("tts_default_voice"))
            or _nonempty_text(os.environ.get("TTS_DEFAULT_VOICE")),
            "elevenlabs_default_voice_label": _nonempty_text(
                self._general_ui_meta(sections=sections).get("elevenlabs_default_voice_label")
            ),
            "kokoro_default_language": _nonempty_text(providers_section.get("kokoro_default_language"))
            or _nonempty_text(os.environ.get("KOKORO_DEFAULT_LANGUAGE"))
            or KOKORO_DEFAULT_LANGUAGE_ID,
            "kokoro_default_voice": _nonempty_text(providers_section.get("kokoro_default_voice"))
            or _nonempty_text(os.environ.get("KOKORO_DEFAULT_VOICE"))
            or KOKORO_DEFAULT_VOICE_ID,
            "kokoro_default_voice_label": _nonempty_text(
                self._general_ui_meta(sections=sections).get("kokoro_default_voice_label")
            )
            or _nonempty_text(
                _safe_json_object(
                    kokoro_voice_metadata(
                        _nonempty_text(providers_section.get("kokoro_default_voice"))
                        or _nonempty_text(os.environ.get("KOKORO_DEFAULT_VOICE"))
                        or KOKORO_DEFAULT_VOICE_ID
                    )
                ).get("name")
            ),
            "supertonic_default_model": _nonempty_text(providers_section.get("supertonic_default_model"))
            or _nonempty_text(os.environ.get("SUPERTONIC_DEFAULT_MODEL"))
            or SUPERTONIC_DEFAULT_MODEL_ID,
            "supertonic_default_language": _nonempty_text(providers_section.get("supertonic_default_language"))
            or _nonempty_text(os.environ.get("SUPERTONIC_DEFAULT_LANGUAGE"))
            or SUPERTONIC_DEFAULT_LANGUAGE_ID,
            "supertonic_default_voice": _nonempty_text(providers_section.get("supertonic_default_voice"))
            or _nonempty_text(os.environ.get("SUPERTONIC_DEFAULT_VOICE"))
            or SUPERTONIC_DEFAULT_VOICE_ID,
            "supertonic_default_voice_label": _nonempty_text(
                _safe_json_object(
                    supertonic_voice_metadata(
                        _nonempty_text(providers_section.get("supertonic_default_voice"))
                        or _nonempty_text(os.environ.get("SUPERTONIC_DEFAULT_VOICE"))
                        or SUPERTONIC_DEFAULT_VOICE_ID
                    )
                ).get("name")
            ),
            "functional_defaults": self._resolve_general_functional_defaults(
                providers_section=providers_section,
                provider_catalog=provider_catalog,
            ),
            "effort_default": self._resolve_general_effort_default(
                providers_section=providers_section,
                provider_catalog=provider_catalog,
            ),
            # Apple Silicon Metal acceleration switch. Defaults to ``True``
            # so the Metal path stays opt-out rather than opt-in for Apple
            # users. Non-Apple hosts ignore the flag at runtime.
            "metal_enabled": (
                bool(providers_section["metal_enabled"]) if "metal_enabled" in providers_section else True
            ),
        }
        resource_values = {
            "global_tools": [
                tool_id
                for tool_id, env_key in {
                    "cache": "cache_enabled",
                    "script_library": "script_library_enabled",
                }.items()
                if bool(tools_section.get(env_key))
            ],
            "integrations": {
                key: bool(integrations_section.get(key))
                for key in (
                    "browser_enabled",
                    "gh_enabled",
                    "glab_enabled",
                    "gws_enabled",
                    "jira_enabled",
                    "confluence_enabled",
                    "aws_enabled",
                    "docker_enabled",
                    "whisper_enabled",
                    "tts_enabled",
                    "link_analysis_enabled",
                )
            },
        }
        memory_values = {
            "memory_enabled": bool(memory_section.get("enabled")),
            "memory_profile": self._infer_profile_from_presets(
                memory_section,
                _GENERAL_MEMORY_PROFILES,
                meta_key="memory_profile",
                sections=sections,
                default="balanced",
            ),
            "procedural_enabled": bool(memory_section.get("procedural_enabled")),
            "proactive_enabled": bool(memory_section.get("proactive_enabled")),
            "embedding_model": (
                _nonempty_text(memory_section.get("embedding_model"))
                or _nonempty_text(os.environ.get("MEMORY_EMBEDDING_MODEL"))
                or _DEFAULT_EMBEDDING_MODEL_ID
            ),
            "knowledge_enabled": bool(knowledge_section.get("enabled")),
            "knowledge_profile": self._infer_profile_from_presets(
                knowledge_section,
                _GENERAL_KNOWLEDGE_PROFILES,
                meta_key="knowledge_profile",
                sections=sections,
                default="curated_workspace",
            ),
            "provenance_policy": (
                _nonempty_text(self._general_ui_meta(sections=sections).get("provenance_policy")).lower()
                or (
                    "strict"
                    if bool(knowledge_section.get("require_owner_provenance"))
                    and bool(knowledge_section.get("require_freshness_provenance"))
                    else "standard"
                )
            ),
            "promotion_mode": _nonempty_text(knowledge_section.get("promotion_mode")) or "review_queue",
            "memory_policy": memory_policy,
            "knowledge_policy": knowledge_policy,
            "autonomy_policy": autonomy_policy,
        }
        provider_connections: dict[str, dict[str, Any]] = {
            provider_id: self.get_provider_connection(provider_id)
            for provider_id in _safe_json_object(provider_catalog.get("providers"))
            if provider_id in MANAGED_PROVIDER_IDS
        }
        elevenlabs_connection = _safe_json_object(provider_connections.get("elevenlabs"))
        elevenlabs_prefill_from_env = (
            _nonempty_text(os.environ.get("TTS_DEFAULT_VOICE"))
            if bool(elevenlabs_connection.get("configured")) or bool(elevenlabs_connection.get("verified"))
            else ""
        )
        model_values["elevenlabs_default_voice"] = (
            _nonempty_text(providers_section.get("elevenlabs_default_voice"))
            or _nonempty_text(providers_section.get("tts_default_voice"))
            or elevenlabs_prefill_from_env
        )
        scheduler_values = {
            "scheduler_enabled": bool(scheduler_section.get("scheduler_enabled", True)),
            "scheduler_poll_interval_seconds": scheduler_section.get("scheduler_poll_interval_seconds"),
            "scheduler_lease_seconds": scheduler_section.get("scheduler_lease_seconds"),
            "scheduler_run_max_attempts": scheduler_section.get("scheduler_run_max_attempts"),
            "scheduler_retry_base_delay": scheduler_section.get("scheduler_retry_base_delay"),
            "scheduler_retry_max_delay": scheduler_section.get("scheduler_retry_max_delay"),
            "scheduler_min_interval_seconds": scheduler_section.get("scheduler_min_interval_seconds"),
            "runbook_governance_enabled": bool(scheduler_section.get("runbook_governance_enabled", False)),
            "runbook_governance_hour": scheduler_section.get("runbook_governance_hour"),
            "runbook_revalidation_stale_days": scheduler_section.get("runbook_revalidation_stale_days"),
            "runbook_revalidation_min_verified_runs": scheduler_section.get("runbook_revalidation_min_verified_runs"),
            "runbook_revalidation_min_success_rate": scheduler_section.get("runbook_revalidation_min_success_rate"),
            "runbook_revalidation_correction_threshold": scheduler_section.get(
                "runbook_revalidation_correction_threshold"
            ),
            "runbook_revalidation_rollback_threshold": scheduler_section.get("runbook_revalidation_rollback_threshold"),
        }
        values = {
            "account": account_values,
            "models": model_values,
            "resources": resource_values,
            "memory_and_knowledge": memory_values,
            "scheduler": scheduler_values,
            "variables": self._custom_global_variables_payload(legacy_settings, sections=sections),
            "provider_connections": provider_connections,
        }
        source_badges = {
            field: self._system_settings_badge(env_key, merged_env=merged_env)
            for field, env_key in _GENERAL_FIELD_SOURCE_ENV_KEYS.items()
        }
        for provider_id in _safe_json_object(provider_catalog.get("providers")):
            source_badges[f"models.providers_enabled.{provider_id}"] = self._system_settings_badge(
                f"{provider_id.upper()}_ENABLED",
                merged_env=merged_env,
            )
        for tool_id, env_key in {
            "cache": "CACHE_ENABLED",
            "script_library": "SCRIPT_LIBRARY_ENABLED",
        }.items():
            source_badges[f"resources.global_tools.{tool_id}"] = self._system_settings_badge(
                env_key,
                merged_env=merged_env,
            )
        for integration_key in resource_values["integrations"]:
            source_badges[f"resources.integrations.{integration_key}"] = self._system_settings_badge(
                integration_key.upper(),
                merged_env=merged_env,
            )
        return {
            "version": legacy_settings["version"],
            "values": values,
            "source_badges": source_badges,
            "catalogs": {
                "providers": [
                    {
                        "id": provider_id,
                        "title": _safe_json_object(payload).get("title"),
                        "vendor": _safe_json_object(payload).get("vendor"),
                        "category": _safe_json_object(payload).get("category", "general"),
                        "enabled_by_default": bool(_safe_json_object(payload).get("enabled")),
                        "command_present": bool(_safe_json_object(payload).get("command_present")),
                        "available_models": _safe_json_object(payload).get("available_models") or [],
                        "default_model": _safe_json_object(payload).get("default_model") or "",
                        "supported_auth_modes": _safe_json_object(payload).get("supported_auth_modes") or [],
                        "supports_api_key": bool(_safe_json_object(payload).get("supports_api_key", False)),
                        "supports_subscription_login": bool(
                            _safe_json_object(payload).get("supports_subscription_login", False)
                        ),
                        "login_flow_kind": _safe_json_object(payload).get("login_flow_kind"),
                        "requires_project_id": bool(_safe_json_object(payload).get("requires_project_id", False)),
                        "connection_managed": bool(_safe_json_object(payload).get("connection_managed", False)),
                        "supports_local_connection": bool(
                            _safe_json_object(payload).get("supports_local_connection", False)
                        ),
                        "connection_status": _safe_json_object(payload).get("connection_status") or {},
                        "connection": _safe_json_object(payload).get("connection") or {},
                        "functional_models": _safe_json_object(payload).get("functional_models") or [],
                    }
                    for provider_id, payload in _safe_json_object(provider_catalog.get("providers")).items()
                ],
                "model_functions": resolve_model_function_catalog(),
                "functional_model_catalog": functional_model_catalog,
                "global_tools": [
                    {
                        "id": "cache",
                        "title": "Cache",
                        "description": "Enables a global cache to speed up repeated executions.",
                        "configurable": True,
                    },
                    {
                        "id": "script_library",
                        "title": "Biblioteca de scripts",
                        "description": "Enables system-approved reusable scripts.",
                        "configurable": True,
                    },
                ],
                "usage_profiles": [
                    {"id": profile_id, **profile} for profile_id, profile in _GENERAL_MODEL_USAGE_PROFILES.items()
                ],
                "memory_profiles": [
                    {"id": profile_id, **profile} for profile_id, profile in _GENERAL_MEMORY_PROFILES.items()
                ],
                "knowledge_profiles": [
                    {"id": profile_id, **profile} for profile_id, profile in _GENERAL_KNOWLEDGE_PROFILES.items()
                ],
                "provenance_policies": [
                    {
                        "id": "strict",
                        "label": "Estrita",
                        "description": "Requires owner and freshness on critical sources.",
                    },
                    {
                        "id": "standard",
                        "label": "Default",
                        "description": "Keeps governance with fewer publication blocks.",
                    },
                ],
                "knowledge_layers": [
                    {
                        "id": "canonical_policy",
                        "label": "Canonical",
                        "description": "Policies, guidelines, and validated system knowledge.",
                    },
                    {
                        "id": "approved_runbook",
                        "label": "Runbooks aprovados",
                        "description": "Approved and traceable operational procedures.",
                    },
                    {
                        "id": "workspace_doc",
                        "label": "Documentos do workspace",
                        "description": "Contextual documentation from the repository and current workspace.",
                    },
                    {
                        "id": "observed_pattern",
                        "label": "Observed patterns",
                        "description": "Semantic insights derived from history, always as the weakest layer.",
                    },
                ],
                "approval_modes": [
                    {
                        "id": "read_only",
                        "label": "Read only",
                        "description": "Investigates and responds without executing mutations.",
                    },
                    {
                        "id": "guarded",
                        "label": "Guarded",
                        "description": "May act with strong verification and additional containment.",
                    },
                    {
                        "id": "supervised",
                        "label": "Supervised",
                        "description": "Executes with human supervision and frequent checkpoints.",
                    },
                    {
                        "id": "escalation_required",
                        "label": "Escalation required",
                        "description": "Must escalate before any sensitive action.",
                    },
                ],
                "autonomy_tiers": [
                    {
                        "id": "t0",
                        "label": "T0",
                        "description": "Research, synthesis, and analysis without writes.",
                    },
                    {
                        "id": "t1",
                        "label": "T1",
                        "description": "Limited actions with strong containment and low risk.",
                    },
                    {
                        "id": "t2",
                        "label": "T2",
                        "description": "Complex execution with tool loop, validation, and operational grounding.",
                    },
                ],
            },
            "review": {
                "warnings": self._general_review_warnings(values),
                "hidden_sections": ["runtime", "scheduler"],
            },
        }

    def get_system_settings(self) -> dict[str, Any]:
        self.ensure_seeded()
        return self._serialize_system_settings()

    def patch_global_defaults(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_seeded()
        sections_payload = _safe_json_object(payload.get("sections"))
        for section, value in sections_payload.items():
            if section not in AGENT_SECTIONS:
                continue
            execute(
                """
                INSERT INTO cp_global_sections (section, data_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(section) DO UPDATE SET data_json = excluded.data_json, updated_at = excluded.updated_at
                """,
                (section, json_dump(_safe_json_object(value)), now_iso()),
            )
        sections = self._load_global_sections()
        version = self._persist_global_default_version(sections)
        return {"sections": sections, "version": version}

    def put_system_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_seeded()
        self._validate_system_settings_payload(payload)
        sections = self._apply_system_settings_to_sections(payload)
        self._persist_global_sections(sections)
        return self.get_system_settings()

    def _validate_general_payload(self, payload: dict[str, Any]) -> None:
        """Validate structural constraints on the general settings payload.

        Raises ``GeneralPayloadValidationError`` with a list of field-level errors
        when the payload would cause surprising or broken runtime behavior. Only
        rejects payloads that are structurally wrong — no business-logic coercion
        happens here (that remains inside ``put_general_system_settings``).
        """
        errors: list[dict[str, str]] = []
        account = _safe_json_object(payload.get("account"))
        models = _safe_json_object(payload.get("models"))
        memory_and_knowledge = _safe_json_object(payload.get("memory_and_knowledge"))
        scheduler = _safe_json_object(payload.get("scheduler"))
        variables_raw = payload.get("variables")

        def _push(field: str, code: str, message: str) -> None:
            errors.append({"field": field, "code": code, "message": message})

        if "time_format" in account and account.get("time_format") not in (None, ""):
            requested_tf = _nonempty_text(account.get("time_format")).lower()
            if requested_tf and requested_tf not in {"24h", "12h"}:
                _push(
                    "account.time_format",
                    "invalid_enum",
                    f"Invalid time format: {requested_tf}. Use 24h or 12h.",
                )

        if "rate_limit_per_minute" in account and account.get("rate_limit_per_minute") not in (None, ""):
            raw = account.get("rate_limit_per_minute")
            try:
                parsed = int(raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                _push("account.rate_limit_per_minute", "invalid_type", "Rate limit must be an integer.")
            else:
                if parsed < 1:
                    _push("account.rate_limit_per_minute", "min_value", "Rate limit deve ser ao menos 1.")

        budget_value: float | None = None
        total_budget_value: float | None = None
        if "max_budget_usd" in models and models.get("max_budget_usd") not in (None, ""):
            try:
                budget_value = float(models.get("max_budget_usd"))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                _push("models.max_budget_usd", "invalid_type", "Per-task budget must be numeric.")
            else:
                if budget_value <= 0:
                    _push("models.max_budget_usd", "must_be_positive", "Per-task budget must be greater than zero.")
        if "max_total_budget_usd" in models and models.get("max_total_budget_usd") not in (None, ""):
            try:
                total_budget_value = float(models.get("max_total_budget_usd"))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                _push("models.max_total_budget_usd", "invalid_type", "Total budget must be numeric.")
            else:
                if total_budget_value < 0:
                    _push(
                        "models.max_total_budget_usd",
                        "must_be_non_negative",
                        "Total budget cannot be negative.",
                    )
        if budget_value is not None and total_budget_value is not None and total_budget_value < budget_value:
            _push(
                "models.max_total_budget_usd",
                "must_gte_max_budget",
                "Total budget must be greater than or equal to per-task budget.",
            )

        enabled_providers_specified = "providers_enabled" in models
        enabled_providers: list[str] = normalize_string_list(models.get("providers_enabled"))
        if enabled_providers_specified:
            managed = set(MANAGED_PROVIDER_IDS)
            for pid in enabled_providers:
                if pid not in managed:
                    _push(
                        "models.providers_enabled",
                        "unknown_provider",
                        f"Provider desconhecido: {pid}.",
                    )
        if "default_provider" in models and models.get("default_provider") not in (None, ""):
            dp = _nonempty_text(models.get("default_provider")).lower()
            if dp and enabled_providers_specified and dp not in enabled_providers:
                _push(
                    "models.default_provider",
                    "must_be_enabled",
                    f"Default provider '{dp}' is not in the list of enabled providers.",
                )

        functional_defaults_payload = _safe_json_object(models.get("functional_defaults"))
        if functional_defaults_payload and enabled_providers_specified:
            for function_id, selection in functional_defaults_payload.items():
                function_key = str(function_id or "").strip().lower()
                if function_key != "general":
                    continue
                selection_obj = _safe_json_object(selection)
                fd_provider = _nonempty_text(selection_obj.get("provider_id")).lower()
                if fd_provider and fd_provider not in enabled_providers:
                    _push(
                        f"models.functional_defaults.{function_id}.provider_id",
                        "must_be_enabled",
                        f"Provider '{fd_provider}' from functional default '{function_id}' is not enabled.",
                    )

        autonomy_policy = _safe_json_object(memory_and_knowledge.get("autonomy_policy"))
        autonomy_tier_raw = autonomy_policy.get("default_autonomy_tier")
        if "default_autonomy_tier" in autonomy_policy and autonomy_tier_raw not in (None, ""):
            tier = _nonempty_text(autonomy_tier_raw).lower()
            if tier and tier not in _ALLOWED_AUTONOMY_TIERS:
                _push(
                    "memory_and_knowledge.autonomy_policy.default_autonomy_tier",
                    "invalid_enum",
                    f"Invalid autonomy tier: {tier}. Use t0, t1, or t2.",
                )

        memory_policy_raw = _safe_json_object(memory_and_knowledge.get("memory_policy"))
        memory_profile = _nonempty_text(
            _safe_json_object(memory_policy_raw.get("profile")).get("id") or memory_policy_raw.get("profile_id")
        )
        if memory_profile and memory_profile not in _GENERAL_MEMORY_PROFILES:
            _push(
                "memory_and_knowledge.memory_policy.profile",
                "unknown_profile",
                f"Unknown memory profile: {memory_profile}.",
            )

        knowledge_policy_raw = _safe_json_object(memory_and_knowledge.get("knowledge_policy"))
        knowledge_profile = _nonempty_text(
            _safe_json_object(knowledge_policy_raw.get("profile")).get("id") or knowledge_policy_raw.get("profile_id")
        )
        if knowledge_profile and knowledge_profile not in _GENERAL_KNOWLEDGE_PROFILES:
            _push(
                "memory_and_knowledge.knowledge_policy.profile",
                "unknown_profile",
                f"Perfil de conhecimento desconhecido: {knowledge_profile}.",
            )
        if "provenance_policy" in knowledge_policy_raw and knowledge_policy_raw.get("provenance_policy") not in (
            None,
            "",
        ):
            provenance = _nonempty_text(knowledge_policy_raw.get("provenance_policy")).lower()
            if provenance and provenance not in _ALLOWED_PROVENANCE_POLICIES:
                _push(
                    "memory_and_knowledge.knowledge_policy.provenance_policy",
                    "invalid_enum",
                    f"Invalid provenance policy: {provenance}. Use strict or standard.",
                )

        _SCHEDULER_POSITIVE_INT_FIELDS = (
            "scheduler_poll_interval_seconds",
            "scheduler_lease_seconds",
            "scheduler_run_max_attempts",
            "scheduler_retry_base_delay",
            "scheduler_retry_max_delay",
            "scheduler_min_interval_seconds",
            "runbook_revalidation_stale_days",
            "runbook_revalidation_min_verified_runs",
            "runbook_revalidation_correction_threshold",
            "runbook_revalidation_rollback_threshold",
        )
        for key in _SCHEDULER_POSITIVE_INT_FIELDS:
            if key in scheduler and scheduler.get(key) not in (None, ""):
                try:
                    parsed = int(scheduler.get(key))  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    _push(f"scheduler.{key}", "invalid_type", f"{key} must be an integer.")
                    continue
                if parsed < 1:
                    _push(f"scheduler.{key}", "min_value", f"{key} deve ser ao menos 1.")
        if "runbook_governance_hour" in scheduler and scheduler.get("runbook_governance_hour") not in (None, ""):
            try:
                hour = int(scheduler.get("runbook_governance_hour"))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                _push(
                    "scheduler.runbook_governance_hour",
                    "invalid_type",
                    "The governance hour must be an integer.",
                )
            else:
                if hour < 0 or hour > 23:
                    _push(
                        "scheduler.runbook_governance_hour",
                        "out_of_range",
                        "The governance hour must be between 0 and 23.",
                    )
        if "runbook_revalidation_min_success_rate" in scheduler and scheduler.get(
            "runbook_revalidation_min_success_rate"
        ) not in (None, ""):
            try:
                rate = float(scheduler.get("runbook_revalidation_min_success_rate"))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                _push(
                    "scheduler.runbook_revalidation_min_success_rate",
                    "invalid_type",
                    "The minimum success rate must be numeric.",
                )
            else:
                if rate < 0 or rate > 1:
                    _push(
                        "scheduler.runbook_revalidation_min_success_rate",
                        "out_of_range",
                        "The minimum success rate must be between 0 and 1.",
                    )

        if variables_raw is not None:
            if not isinstance(variables_raw, list):
                _push("variables", "invalid_type", "Variables must be a list.")
            else:
                for index, entry in enumerate(variables_raw):
                    entry_obj = _safe_json_object(entry)
                    key = _nonempty_text(entry_obj.get("key"))
                    if not key:
                        _push(f"variables[{index}].key", "required", "Variable key is required.")
                    elif not _ENV_KEY_RE.match(key):
                        _push(
                            f"variables[{index}].key",
                            "invalid_format",
                            f"Chave '{key}' must start with an uppercase letter and contain only A-Z, 0-9, and '_'.",
                        )
                    vtype = _nonempty_text(entry_obj.get("type")).lower() or "text"
                    if vtype not in _ALLOWED_VARIABLE_TYPES:
                        _push(
                            f"variables[{index}].type",
                            "invalid_enum",
                            f"Invalid type: {vtype}. Use text or secret.",
                        )
                    vscope = _nonempty_text(entry_obj.get("scope")).lower() or "system_only"
                    if vscope not in _ALLOWED_VARIABLE_SCOPES:
                        _push(
                            f"variables[{index}].scope",
                            "invalid_enum",
                            f"Invalid scope: {vscope}. Use system_only or agent_grant.",
                        )

        if errors:
            raise GeneralPayloadValidationError(errors)

    def put_general_system_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_seeded()
        self._validate_general_payload(payload)
        current = self.get_system_settings()
        sections = self._system_settings_sections()
        general_ui = dict(self._general_ui_meta(sections=sections))
        global_secret_meta = dict(self._access_meta_map("global_secret_meta", sections=sections))

        account = _safe_json_object(payload.get("account"))
        models = _safe_json_object(payload.get("models"))
        resources = _safe_json_object(payload.get("resources"))
        integrations = _safe_json_object(resources.get("integrations"))
        memory_and_knowledge = _safe_json_object(payload.get("memory_and_knowledge"))
        memory_policy_input = normalize_memory_policy(_safe_json_object(memory_and_knowledge.get("memory_policy")))
        knowledge_policy_input = normalize_knowledge_policy(
            _safe_json_object(memory_and_knowledge.get("knowledge_policy"))
        )
        autonomy_policy_input = normalize_autonomy_policy(
            _safe_json_object(memory_and_knowledge.get("autonomy_policy"))
        )
        variables = _safe_json_list(payload.get("variables"))

        current_general = dict(_safe_json_object(current.get("general")))
        current_scheduler = dict(_safe_json_object(current.get("scheduler")))
        current_providers = dict(_safe_json_object(current.get("providers")))
        current_tools = dict(_safe_json_object(current.get("tools")))
        current_integrations = dict(_safe_json_object(current.get("integrations")))
        current_memory = dict(_safe_json_object(current.get("memory")))
        current_knowledge = dict(_safe_json_object(current.get("knowledge")))

        for key in ("owner_name", "owner_email", "owner_github", "default_work_dir"):
            if key in account:
                current_general[key] = _nonempty_text(account.get(key))
        if "project_dirs" in account:
            current_general["project_dirs"] = normalize_string_list(account.get("project_dirs"))
        if "rate_limit_per_minute" in account:
            current_general["rate_limit_per_minute"] = account.get("rate_limit_per_minute")
        if "scheduler_default_timezone" in account:
            current_scheduler["scheduler_default_timezone"] = _nonempty_text(account.get("scheduler_default_timezone"))
        if "time_format" in account:
            requested_time_format = _nonempty_text(account.get("time_format")).lower()
            if requested_time_format in {"24h", "12h"}:
                current_general["time_format"] = requested_time_format

        scheduler_payload = _safe_json_object(payload.get("scheduler"))
        for bool_key in ("scheduler_enabled", "runbook_governance_enabled"):
            if bool_key in scheduler_payload:
                current_scheduler[bool_key] = bool(scheduler_payload.get(bool_key))
        for int_key in (
            "scheduler_poll_interval_seconds",
            "scheduler_lease_seconds",
            "scheduler_run_max_attempts",
            "scheduler_retry_base_delay",
            "scheduler_retry_max_delay",
            "scheduler_min_interval_seconds",
            "runbook_governance_hour",
            "runbook_revalidation_stale_days",
            "runbook_revalidation_min_verified_runs",
            "runbook_revalidation_correction_threshold",
            "runbook_revalidation_rollback_threshold",
        ):
            if int_key in scheduler_payload and scheduler_payload.get(int_key) not in (None, ""):
                with contextlib.suppress(TypeError, ValueError):
                    current_scheduler[int_key] = int(scheduler_payload.get(int_key))  # type: ignore[arg-type]
        if "runbook_revalidation_min_success_rate" in scheduler_payload and scheduler_payload.get(
            "runbook_revalidation_min_success_rate"
        ) not in (None, ""):
            with contextlib.suppress(TypeError, ValueError):
                current_scheduler["runbook_revalidation_min_success_rate"] = float(
                    scheduler_payload.get("runbook_revalidation_min_success_rate")  # type: ignore[arg-type]
                )

        provider_catalog = self.get_core_providers()
        enabled_providers = normalize_string_list(models.get("providers_enabled"))
        provider_connections: dict[str, dict[str, Any]] = {
            provider_id: self.get_provider_connection(provider_id)
            for provider_id in _safe_json_object(provider_catalog.get("providers"))
            if provider_id in MANAGED_PROVIDER_IDS
        }
        for provider_id in _user_selectable_provider_ids(provider_catalog):
            current_providers[f"{provider_id}_enabled"] = provider_id in enabled_providers
        if "default_provider" in models:
            current_providers["default_provider"] = _nonempty_text(models.get("default_provider")).lower()
        if "fallback_order" in models:
            requested_order = [
                provider
                for provider in normalize_string_list(models.get("fallback_order"))
                if provider in enabled_providers
            ]
            current_providers["fallback_order"] = requested_order
        if "max_budget_usd" in models:
            current_providers["max_budget_usd"] = models.get("max_budget_usd")
        if "max_total_budget_usd" in models:
            current_providers["max_total_budget_usd"] = models.get("max_total_budget_usd")
        if "elevenlabs_default_language" in models:
            current_providers["elevenlabs_default_language"] = _nonempty_text(
                models.get("elevenlabs_default_language")
            ).lower()
        if "elevenlabs_default_voice" in models:
            current_providers["elevenlabs_default_voice"] = _nonempty_text(models.get("elevenlabs_default_voice"))
        if "elevenlabs_default_voice_label" in models:
            voice_label = _nonempty_text(models.get("elevenlabs_default_voice_label"))
            if voice_label:
                general_ui["elevenlabs_default_voice_label"] = voice_label
            else:
                general_ui.pop("elevenlabs_default_voice_label", None)
        if "kokoro_default_language" in models:
            current_providers["kokoro_default_language"] = _nonempty_text(models.get("kokoro_default_language")).lower()
        if "kokoro_default_voice" in models:
            current_providers["kokoro_default_voice"] = _nonempty_text(models.get("kokoro_default_voice"))
        if "kokoro_default_voice_label" in models:
            voice_label = _nonempty_text(models.get("kokoro_default_voice_label"))
            if voice_label:
                general_ui["kokoro_default_voice_label"] = voice_label
            else:
                general_ui.pop("kokoro_default_voice_label", None)
        if "supertonic_default_model" in models:
            current_providers["supertonic_default_model"] = _nonempty_text(models.get("supertonic_default_model"))
        if "supertonic_default_language" in models:
            current_providers["supertonic_default_language"] = _nonempty_text(
                models.get("supertonic_default_language")
            ).lower()
        if "supertonic_default_voice" in models:
            current_providers["supertonic_default_voice"] = _nonempty_text(models.get("supertonic_default_voice"))
        # Apple Silicon Metal acceleration toggle. Persisted in
        # ``providers.metal_enabled`` and projected to the ``METAL_ENABLED``
        # env var by ``_apply_system_settings_to_sections`` so the runtime
        # gate in ``runtime_capabilities.is_metal_path_active`` picks it up
        # without a worker restart.
        if "metal_enabled" in models:
            current_providers["metal_enabled"] = bool(models.get("metal_enabled"))
        normalized_kokoro_voice = _nonempty_text(current_providers.get("kokoro_default_voice")).lower()
        if normalized_kokoro_voice:
            voice_metadata = kokoro_voice_metadata(normalized_kokoro_voice)
            if voice_metadata is None:
                raise ValueError("The default Kokoro voice does not exist in the official catalog.")
            current_providers["kokoro_default_voice"] = normalized_kokoro_voice
            current_providers["kokoro_default_language"] = _nonempty_text(voice_metadata.get("language_id")).lower()
            if not _nonempty_text(general_ui.get("kokoro_default_voice_label")):
                general_ui["kokoro_default_voice_label"] = _nonempty_text(voice_metadata.get("name"))
        normalized_supertonic_model = (
            _nonempty_text(current_providers.get("supertonic_default_model")) or SUPERTONIC_DEFAULT_MODEL_ID
        )
        if normalized_supertonic_model:
            try:
                supertonic_model_status(normalized_supertonic_model)
            except KeyError as exc:
                raise ValueError("The default Supertonic model does not exist in the official catalog.") from exc
            current_providers["supertonic_default_model"] = normalized_supertonic_model
        normalized_supertonic_voice = _nonempty_text(current_providers.get("supertonic_default_voice"))
        if normalized_supertonic_voice:
            voice_metadata = supertonic_voice_metadata(normalized_supertonic_voice)
            if voice_metadata is None:
                raise ValueError("The default Supertonic voice does not exist in the official catalog.")
            current_providers["supertonic_default_voice"] = _nonempty_text(voice_metadata.get("voice_id"))
            if not _nonempty_text(current_providers.get("supertonic_default_language")):
                current_providers["supertonic_default_language"] = SUPERTONIC_DEFAULT_LANGUAGE_ID
        functional_defaults_requested = _normalize_functional_model_defaults(models.get("functional_defaults"))
        if functional_defaults_requested:
            current_providers["functional_defaults"] = functional_defaults_requested

        default_provider = _nonempty_text(current_providers.get("default_provider")).lower()
        if default_provider and default_provider not in enabled_providers:
            default_provider = enabled_providers[0] if enabled_providers else ""
            current_providers["default_provider"] = default_provider
        requested_fallback = [
            provider
            for provider in normalize_string_list(current_providers.get("fallback_order"))
            if provider in enabled_providers
        ]
        current_providers["fallback_order"] = requested_fallback

        usage_profile = _nonempty_text(models.get("usage_profile")).lower() or "balanced"
        general_ui["usage_profile"] = usage_profile
        tier_name = str(_safe_json_object(_GENERAL_MODEL_USAGE_PROFILES.get(usage_profile)).get("tier") or "medium")
        for provider_id, provider_payload in _safe_json_object(provider_catalog.get("providers")).items():
            if provider_id not in enabled_providers:
                continue
            tier_models = _safe_json_object(_safe_json_object(provider_payload).get("tier_models"))
            selected_model = _nonempty_text(tier_models.get(tier_name)) or _nonempty_text(
                current_providers.get(f"{provider_id}_default_model")
            )
            if selected_model:
                current_providers[f"{provider_id}_default_model"] = selected_model

        option_map = self._functional_model_option_map(provider_catalog)
        functional_defaults = _normalize_functional_model_defaults(current_providers.get("functional_defaults"))
        normalized_functional_defaults: dict[str, dict[str, str]] = {}
        for function_id, selection in functional_defaults.items():
            option = _safe_json_object(
                _safe_json_object(option_map.get(function_id)).get(
                    f"{selection.get('provider_id')}:{selection.get('model_id')}"
                )
            )
            if not option:
                # Unknown provider/model: drop silently so the operator can still save
                # unrelated settings. A warning is surfaced elsewhere.
                continue
            provider_id = _nonempty_text(option.get("provider_id")).lower()
            provider_payload = _safe_json_object(_safe_json_object(provider_catalog.get("providers")).get(provider_id))
            if function_id in {"general", "transcription"} and not self._provider_selectable_for_function(
                function_id,
                provider_id,
                provider_payload,
                provider_connections,
            ):
                # Provider not ready yet: drop this functional default so save
                # proceeds. Warning is surfaced by _warnings_for_system_settings.
                continue
            normalized_functional_defaults[function_id] = {
                "provider_id": provider_id,
                "model_id": _nonempty_text(option.get("model_id")),
                "provider_title": _nonempty_text(option.get("provider_title")),
                "model_label": _nonempty_text(option.get("title")),
            }

        if normalized_functional_defaults:
            current_providers["functional_defaults"] = normalized_functional_defaults
            general_default = _safe_json_object(normalized_functional_defaults.get("general"))
            general_provider = _nonempty_text(general_default.get("provider_id")).lower()
            general_model = _nonempty_text(general_default.get("model_id"))
            if general_provider and general_model and general_provider in enabled_providers:
                current_providers["default_provider"] = general_provider
                current_providers[f"{general_provider}_default_model"] = general_model
            elif general_provider and general_model:
                # General default points to a provider that is not enabled:
                # drop it from normalized_functional_defaults so the operator
                # can still save.
                normalized_functional_defaults.pop("general", None)
                current_providers["functional_defaults"] = normalized_functional_defaults
            audio_default = _safe_json_object(normalized_functional_defaults.get("audio"))
            audio_provider = _nonempty_text(audio_default.get("provider_id")).lower()
            audio_model = _nonempty_text(audio_default.get("model_id"))
            if audio_provider == "elevenlabs" and audio_model:
                current_providers["elevenlabs_model"] = audio_model
            if audio_provider == "supertonic" and audio_model:
                current_providers["supertonic_default_model"] = audio_model
        elif "functional_defaults" in current_providers:
            current_providers.pop("functional_defaults", None)

        default_provider = _nonempty_text(current_providers.get("default_provider")).lower()
        if default_provider and default_provider not in enabled_providers:
            default_provider = enabled_providers[0] if enabled_providers else ""
            current_providers["default_provider"] = default_provider
        deduped_fallback: list[str] = []
        for provider in [default_provider, *normalize_string_list(current_providers.get("fallback_order"))]:
            if not provider or provider not in enabled_providers or provider in deduped_fallback:
                continue
            deduped_fallback.append(provider)
        current_providers["fallback_order"] = deduped_fallback

        effort_provider, effort_model = self._resolve_general_effort_target(
            providers_section=current_providers,
            provider_catalog=provider_catalog,
        )
        existing_effort_default = normalize_model_effort_selection(
            current_providers.get("effort_default"),
            provider_id=effort_provider,
            model_id=effort_model,
        )
        if existing_effort_default:
            current_providers["effort_default"] = existing_effort_default
        else:
            current_providers.pop("effort_default", None)

        if "effort_default" in models or "effort_defaults" in models:
            normalized_effort_default = normalize_model_effort_selection(
                models.get("effort_default"),
                provider_id=effort_provider,
                model_id=effort_model,
            )
            if not normalized_effort_default and "effort_defaults" in models:
                normalized_effort_default = normalize_legacy_effort_selection(
                    models.get("effort_defaults"),
                    provider_id=effort_provider,
                    model_id=effort_model,
                )
            if normalized_effort_default:
                current_providers["effort_default"] = normalized_effort_default
            else:
                current_providers.pop("effort_default", None)
            current_providers.pop("effort_defaults", None)

        # Deprecated compatibility: accept legacy provider_credentials payloads
        provider_creds = _safe_json_object(payload.get("provider_credentials"))
        for provider_id in _safe_json_object(provider_catalog.get("providers")):
            cred = _safe_json_object(provider_creds.get(provider_id))
            if provider_id in MANAGED_PROVIDER_IDS and (
                _nonempty_text(cred.get("api_key")) or bool(cred.get("clear_api_key"))
            ):
                self.put_provider_api_key_connection(provider_id, cred)
            default_model = _nonempty_text(cred.get("default_model"))
            if default_model:
                current_providers[f"{provider_id}_default_model"] = default_model
            base_url = cred.get("base_url")
            if base_url is not None:
                current_providers[f"{provider_id}_base_url"] = str(base_url)
            if provider_id == "elevenlabs" and "default_voice" in cred:
                current_providers[f"{provider_id}_default_voice"] = _nonempty_text(cred.get("default_voice")) or ""
            if provider_id == "elevenlabs" and "default_language" in cred:
                current_providers[f"{provider_id}_default_language"] = _nonempty_text(
                    cred.get("default_language")
                ).lower()

        selected_tools = set(normalize_string_list(resources.get("global_tools")))
        for tool_key, field_name in {
            "cache": "cache_enabled",
            "script_library": "script_library_enabled",
        }.items():
            current_tools[field_name] = tool_key in selected_tools
        # Core tools are always-on system defaults
        current_tools["shell_enabled"] = True
        current_tools["pip_enabled"] = True
        current_tools["npm_enabled"] = True

        for field_name in (
            "browser_enabled",
            "gh_enabled",
            "glab_enabled",
            "gws_enabled",
            "jira_enabled",
            "confluence_enabled",
            "aws_enabled",
            "docker_enabled",
            "whisper_enabled",
            "tts_enabled",
            "link_analysis_enabled",
        ):
            if field_name in integrations:
                current_integrations[field_name] = bool(integrations.get(field_name))

        if "memory_enabled" in memory_and_knowledge:
            current_memory["enabled"] = bool(memory_and_knowledge.get("memory_enabled"))
        if "procedural_enabled" in memory_and_knowledge:
            current_memory["procedural_enabled"] = bool(memory_and_knowledge.get("procedural_enabled"))
        if "proactive_enabled" in memory_and_knowledge:
            current_memory["proactive_enabled"] = bool(memory_and_knowledge.get("proactive_enabled"))
        if "embedding_model" in memory_and_knowledge:
            requested_model = _nonempty_text(memory_and_knowledge.get("embedding_model"))
            if requested_model and requested_model in _embedding_catalog_keys():
                current_memory["embedding_model"] = requested_model
        if "knowledge_enabled" in memory_and_knowledge:
            current_knowledge["enabled"] = bool(memory_and_knowledge.get("knowledge_enabled"))

        memory_profile = _nonempty_text(memory_and_knowledge.get("memory_profile")).lower() or "balanced"
        general_ui["memory_profile"] = memory_profile
        current_memory.update(_safe_json_object(_GENERAL_MEMORY_PROFILES.get(memory_profile)).get("settings", {}))

        knowledge_profile = _nonempty_text(memory_and_knowledge.get("knowledge_profile")).lower() or "curated_workspace"
        general_ui["knowledge_profile"] = knowledge_profile
        current_knowledge.update(
            _safe_json_object(_GENERAL_KNOWLEDGE_PROFILES.get(knowledge_profile)).get("settings", {})
        )

        provenance_policy = _nonempty_text(memory_and_knowledge.get("provenance_policy")).lower() or "strict"
        promotion_mode = _nonempty_text(memory_and_knowledge.get("promotion_mode")).lower()
        stored_promotion = _nonempty_text(current_knowledge.get("promotion_mode")).lower()
        resolved_promotion = promotion_mode or stored_promotion or "review_queue"
        current_knowledge["promotion_mode"] = (
            resolved_promotion if resolved_promotion in PROMOTION_MODES else "review_queue"
        )
        current_knowledge["require_owner_provenance"] = True
        current_knowledge["require_freshness_provenance"] = provenance_policy == "strict"
        effective_knowledge_policy = normalize_knowledge_policy(
            _overlay_known_policy_fields(
                normalize_knowledge_policy(
                    _safe_json_object(_safe_json_object(sections.get("knowledge")).get("policy"))
                ),
                current_knowledge,
                _GENERAL_KNOWLEDGE_POLICY_FIELD_NAMES,
            )
        )
        if knowledge_policy_input:
            effective_knowledge_policy = normalize_knowledge_policy(
                _deep_merge_json_objects(effective_knowledge_policy, knowledge_policy_input)
            )
        # Re-apply overlay so the operator's `provenance_policy` choice (translated
        # into `current_knowledge.require_*_provenance` above) wins over a stale
        # `knowledge_policy` echoed back by the dashboard.
        effective_knowledge_policy = normalize_knowledge_policy(
            _overlay_known_policy_fields(
                effective_knowledge_policy,
                current_knowledge,
                _GENERAL_KNOWLEDGE_POLICY_FIELD_NAMES,
            )
        )
        general_ui["provenance_policy"] = (
            "strict"
            if bool(effective_knowledge_policy.get("require_owner_provenance"))
            and bool(effective_knowledge_policy.get("require_freshness_provenance"))
            else "standard"
        )

        custom_shared_variables: list[dict[str, str]] = []
        template_keys = {
            str(field["key"])
            for template in _GENERAL_INTEGRATION_CREDENTIAL_TEMPLATES.values()
            for field in template["fields"]
        }
        custom_system_variables = [
            entry
            for entry in _normalize_env_entries(current.get("additional_env_vars"))
            if entry["key"] in template_keys
        ]
        next_shared_meta: dict[str, dict[str, Any]] = {}
        next_system_meta: dict[str, dict[str, Any]] = {
            key: value
            for key, value in self._access_meta_map("system_env_meta", sections=sections).items()
            if key in template_keys
        }
        desired_secret_keys: set[str] = set()

        for item in variables:
            entry = _safe_json_object(item)
            key = _normalize_env_entry_key(entry.get("key"))
            if not key:
                continue
            # Defense-in-depth: never let the dashboard re-introduce a
            # system-managed env key (policy JSON, provider auth flags, field
            # spec keys) into the user-defined variables list. These are
            # produced by `_apply_*_policy_to_section` and serialized for
            # workers; the operator should configure them through the
            # dedicated section toggles, not as free-form variables.
            if key in _SYSTEM_SETTINGS_KNOWN_ENV_KEYS:
                continue
            value_type = _normalize_general_value_type(entry.get("type"))
            usage_scope = _normalize_general_usage_scope(entry.get("scope"), default="system_only")
            description = _nonempty_text(entry.get("description"))
            clear = bool(entry.get("clear"))
            if value_type == "secret":
                desired_secret_keys.add(key)
                global_secret_meta[key] = {"description": description, "usage_scope": usage_scope}
                if clear:
                    global_secret_meta.pop(key, None)
                    self.delete_global_secret_asset(key, persist_sections=False)
                    continue
                value = _nonempty_text(entry.get("value"))
                if value:
                    self.upsert_global_secret_asset(
                        key,
                        {"value": value, "description": description, "usage_scope": usage_scope},
                        persist_sections=False,
                    )
                continue

            value = _nonempty_text(entry.get("value"))
            if not value:
                continue
            if looks_like_secret_key(key):
                raise ValueError(f"variable '{key}' looks sensitive. Store it as a secret instead.")
            target = custom_shared_variables if usage_scope == "agent_grant" else custom_system_variables
            target.append({"key": key, "value": value})
            if usage_scope == "agent_grant":
                next_shared_meta[key] = {"description": description}
            else:
                next_system_meta[key] = {"description": description}

        for secret in self._current_global_secrets(sections=sections, include_hidden=True):
            secret_key = str(secret["secret_key"])
            if secret_key in _HIDDEN_GLOBAL_SECRET_KEYS:
                continue
            if secret_key in template_keys:
                continue
            if secret_key not in desired_secret_keys:
                global_secret_meta.pop(secret_key, None)
                self.delete_global_secret_asset(secret_key, persist_sections=False)

        current["general"] = current_general
        current["scheduler"] = current_scheduler
        current["providers"] = current_providers
        current["tools"] = current_tools
        current["integrations"] = current_integrations
        current["memory"] = current_memory
        current["knowledge"] = current_knowledge
        current["shared_variables"] = sorted(custom_shared_variables, key=lambda item: item["key"])
        current["additional_env_vars"] = sorted(custom_system_variables, key=lambda item: item["key"])
        self._validate_system_settings_payload(current)
        sections = self._apply_system_settings_to_sections(current)
        effective_memory_policy = normalize_memory_policy(
            _overlay_known_policy_fields(
                normalize_memory_policy(_safe_json_object(_safe_json_object(sections.get("memory")).get("policy"))),
                current_memory,
                _GENERAL_MEMORY_POLICY_FIELD_NAMES,
            )
        )
        raw_memory_profile = _safe_json_object(_safe_json_object(sections.get("memory")).get("profile"))
        if raw_memory_profile and not _safe_json_object(effective_memory_policy.get("profile")):
            effective_memory_policy = normalize_memory_policy(
                _deep_merge_json_objects(effective_memory_policy, {"profile": raw_memory_profile})
            )
        if memory_policy_input:
            effective_memory_policy = normalize_memory_policy(
                _deep_merge_json_objects(effective_memory_policy, memory_policy_input)
            )
        # Re-apply overlay so toggle/profile changes from `current_memory` win over
        # any stale fields the dashboard sent inside `memory_policy` (e.g. it
        # only updates `memory_enabled` but echoes back the previous
        # `memory_policy.enabled` from the GET payload).
        effective_memory_policy = normalize_memory_policy(
            _overlay_known_policy_fields(
                effective_memory_policy,
                current_memory,
                _GENERAL_MEMORY_POLICY_FIELD_NAMES,
            )
        )

        effective_knowledge_policy = normalize_knowledge_policy(
            _overlay_known_policy_fields(
                normalize_knowledge_policy(
                    _safe_json_object(_safe_json_object(sections.get("knowledge")).get("policy"))
                ),
                current_knowledge,
                _GENERAL_KNOWLEDGE_POLICY_FIELD_NAMES,
            )
        )
        if knowledge_policy_input:
            effective_knowledge_policy = normalize_knowledge_policy(
                _deep_merge_json_objects(effective_knowledge_policy, knowledge_policy_input)
            )
        # Same final-overlay rationale as the memory branch above.
        effective_knowledge_policy = normalize_knowledge_policy(
            _overlay_known_policy_fields(
                effective_knowledge_policy,
                current_knowledge,
                _GENERAL_KNOWLEDGE_POLICY_FIELD_NAMES,
            )
        )

        effective_autonomy_policy = normalize_autonomy_policy(
            _safe_json_object(_safe_json_object(sections.get("runtime")).get("autonomy_policy"))
        )
        if autonomy_policy_input:
            effective_autonomy_policy = normalize_autonomy_policy(
                _deep_merge_json_objects(effective_autonomy_policy, autonomy_policy_input)
            )

        memory_section = dict(_safe_json_object(sections.get("memory")))
        knowledge_section = dict(_safe_json_object(sections.get("knowledge")))
        runtime_section = dict(_safe_json_object(sections.get("runtime")))
        self._apply_memory_policy_to_section(memory_section, effective_memory_policy)
        if effective_memory_policy:
            memory_section.pop("profile", None)
        self._apply_knowledge_policy_to_section(knowledge_section, effective_knowledge_policy)
        self._apply_autonomy_policy_to_section(runtime_section, effective_autonomy_policy)
        sections["memory"] = memory_section
        sections["knowledge"] = knowledge_section
        sections["runtime"] = runtime_section

        access_section = dict(_safe_json_object(sections.get("access")))
        access_section["general_ui"] = general_ui
        if next_shared_meta:
            access_section["shared_env_meta"] = next_shared_meta
        else:
            access_section.pop("shared_env_meta", None)
        if next_system_meta:
            access_section["system_env_meta"] = next_system_meta
        else:
            access_section.pop("system_env_meta", None)
        if global_secret_meta:
            access_section["global_secret_meta"] = global_secret_meta
        else:
            access_section.pop("global_secret_meta", None)
        sections["access"] = access_section
        self._persist_global_sections(sections)
        return self.get_general_system_settings()

    def get_global_secret_asset(self, secret_key: str) -> dict[str, Any] | None:
        normalized_secret_key = _normalize_secret_key(secret_key)
        if normalized_secret_key in _REMOVED_GLOBAL_SECRET_KEYS:
            return None
        sections = self._system_settings_sections()
        row = fetch_one(
            "SELECT * FROM cp_secret_values WHERE scope_id = 'global' AND secret_key = ?",
            (normalized_secret_key,),
        )
        if row is None:
            return None
        return {
            "id": int(row["id"]),
            "scope": "global",
            "secret_key": normalized_secret_key,
            "grantable_to_agents": self._global_secret_usage_scope(normalized_secret_key, sections=sections)
            == "agent_grant",
            "usage_scope": self._global_secret_usage_scope(normalized_secret_key, sections=sections),
            "description": _nonempty_text(
                self._access_meta_map("global_secret_meta", sections=sections)
                .get(normalized_secret_key, {})
                .get("description")
            ),
            # Preview stripped — the browser never needs the masked shape.
            "preview": "",
            "updated_at": str(row["updated_at"] or ""),
        }

    def upsert_global_secret_asset(
        self,
        secret_key: str,
        payload: dict[str, Any],
        *,
        persist_sections: bool = True,
    ) -> dict[str, Any]:
        normalized_secret_key = _normalize_secret_key(secret_key)
        if normalized_secret_key in _REMOVED_GLOBAL_SECRET_KEYS:
            raise ValueError("RUNTIME_TOKEN is no longer supported. Use RUNTIME_LOCAL_UI_TOKEN.")
        if normalized_secret_key in _NON_SECRET_SYSTEM_ENV_KEYS and not looks_like_secret_key(normalized_secret_key):
            raise ValueError(
                f"'{normalized_secret_key}' is a non-sensitive system setting. Store it in global settings instead."
            )
        value = str(payload.get("value") or "")
        if not value:
            raise ValueError("secret value must not be empty")
        now = now_iso()
        execute(
            """
            INSERT INTO cp_secret_values (
                scope_id, agent_id, secret_key, encrypted_value, preview, created_at, updated_at
            ) VALUES ('global', NULL, ?, ?, ?, ?, ?)
            ON CONFLICT(scope_id, secret_key) DO UPDATE SET
                encrypted_value = excluded.encrypted_value,
                preview = excluded.preview,
                updated_at = excluded.updated_at
            """,
            (
                normalized_secret_key,
                encrypt_secret(value),
                mask_secret(value),
                now,
                now,
            ),
        )
        if persist_sections:
            sections = self._system_settings_sections()
            access_section = dict(self._access_section(sections))
            secret_meta = dict(self._access_meta_map("global_secret_meta", sections=sections))
            secret_meta[normalized_secret_key] = {
                "description": _nonempty_text(payload.get("description")),
                "usage_scope": _normalize_general_usage_scope(
                    payload.get("usage_scope"),
                    default="system_only" if not _global_secret_is_grantable(normalized_secret_key) else "agent_grant",
                ),
            }
            access_section["global_secret_meta"] = secret_meta
            sections["access"] = access_section
            self._persist_global_sections(sections)
        return self.get_global_secret_asset(normalized_secret_key) or {}

    def delete_global_secret_asset(self, secret_key: str, *, persist_sections: bool = True) -> bool:
        normalized_secret_key = _normalize_secret_key(secret_key)
        execute("DELETE FROM cp_secret_values WHERE scope_id = 'global' AND secret_key = ?", (normalized_secret_key,))
        if persist_sections:
            sections = self._system_settings_sections()
            access_section = dict(self._access_section(sections))
            secret_meta = dict(self._access_meta_map("global_secret_meta", sections=sections))
            if normalized_secret_key in secret_meta:
                secret_meta.pop(normalized_secret_key, None)
                if secret_meta:
                    access_section["global_secret_meta"] = secret_meta
                else:
                    access_section.pop("global_secret_meta", None)
                sections["access"] = access_section
                self._persist_global_sections(sections)
        return True

    def get_section(self, agent_id: str, section: str) -> dict[str, Any]:
        normalized, _ = self._require_agent_row(agent_id)
        if section not in AGENT_SECTIONS:
            raise ValueError(section)
        agent_row = fetch_one(
            "SELECT data_json FROM cp_agent_sections WHERE agent_id = ? AND section = ?", (normalized, section)
        )
        global_row = fetch_one("SELECT data_json FROM cp_global_sections WHERE section = ?", (section,))
        global_data = json_load(global_row["data_json"], {}) if global_row else {}
        agent_data = json_load(agent_row["data_json"], {}) if agent_row else {}
        effective = _deep_merge_json_objects(_safe_json_object(global_data), _safe_json_object(agent_data))
        return {
            "agent_id": normalized,
            "section": section,
            "data": agent_data,
            "effective": effective,
            "inherited": global_data,
        }

    def put_section(
        self,
        agent_id: str,
        section: str,
        payload: dict[str, Any],
        *,
        strict_access_validation: bool = True,
    ) -> dict[str, Any]:
        normalized, _ = self._require_agent_row(agent_id)
        if section not in AGENT_SECTIONS:
            raise ValueError(section)
        data = _safe_json_object(payload.get("data", payload))
        if section == "access":
            access_payload = dict(data)
            normalized_policy = normalize_agent_spec(
                {"resource_access_policy": _safe_json_object(access_payload.get("resource_access_policy"))}
            ).get("resource_access_policy", {})
            validation = validate_agent_spec({"resource_access_policy": normalized_policy})
            errors = [
                str(item)
                for item in _safe_json_list(validation.get("errors"))
                if str(item).startswith("resource_access_policy.")
            ]
            if strict_access_validation and errors:
                raise ValueError("; ".join(errors))
            if normalized_policy:
                access_payload["resource_access_policy"] = normalized_policy
            else:
                access_payload.pop("resource_access_policy", None)
            data = access_payload
        execute(
            """
            INSERT INTO cp_agent_sections (agent_id, section, data_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(agent_id, section) DO UPDATE SET
                data_json = excluded.data_json,
                updated_at = excluded.updated_at
            """,
            (normalized, section, json_dump(data), now_iso()),
        )
        return self.get_section(normalized, section)

    def get_document(self, agent_id: str, kind: str) -> dict[str, Any] | None:
        normalized, _ = self._require_agent_row(agent_id)
        if kind not in DOCUMENT_KINDS:
            raise ValueError(kind)
        row = fetch_one("SELECT * FROM cp_agent_documents WHERE agent_id = ? AND kind = ?", (normalized, kind))
        if row is None:
            return None
        return {
            "agent_id": normalized,
            "kind": kind,
            "content_md": str(row["content_md"] or ""),
            "updated_at": str(row["updated_at"] or ""),
        }

    def upsert_document(self, agent_id: str, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized, _ = self._require_agent_row(agent_id)
        if kind not in DOCUMENT_KINDS:
            raise ValueError(kind)
        content_md = str(payload.get("content_md") or payload.get("content") or "")
        execute(
            """
            INSERT INTO cp_agent_documents (agent_id, kind, content_md, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(agent_id, kind) DO UPDATE SET content_md = excluded.content_md, updated_at = excluded.updated_at
            """,
            (normalized, kind, content_md, now_iso()),
        )
        return self.get_document(normalized, kind) or {"agent_id": normalized, "kind": kind, "content_md": content_md}

    def delete_document(self, agent_id: str, kind: str) -> bool:
        normalized, _ = self._require_agent_row(agent_id)
        execute("DELETE FROM cp_agent_documents WHERE agent_id = ? AND kind = ?", (normalized, kind))
        return True

    def list_knowledge_assets(self, agent_id: str, *, include_global: bool = True) -> list[dict[str, Any]]:
        normalized, _ = self._require_agent_row(agent_id)
        scope_ids = ["global", normalized] if include_global else [normalized]
        placeholders = ",".join("?" for _ in scope_ids)
        rows = fetch_all(
            f"""
            SELECT * FROM cp_knowledge_assets
            WHERE scope_id IN ({placeholders})
            ORDER BY CASE scope_id WHEN 'global' THEN 0 ELSE 1 END, asset_key ASC
            """,
            tuple(scope_ids),
        )
        return [self._serialize_knowledge_asset(row) for row in rows]

    def upsert_knowledge_asset(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized, _ = self._require_agent_row(agent_id)
        scope = _normalize_scope(str(payload.get("scope") or "agent"))
        target_agent_id = None if scope == "global" else normalized
        scope_id = _scope_id(target_agent_id)
        asset_id = int(payload.get("id") or 0)
        existing_row = None
        if asset_id:
            _, existing_row = self._resolve_knowledge_asset_row(normalized, asset_id)
            if "scope" not in payload:
                scope = "global" if str(existing_row["scope_id"]) == "global" else "agent"
                target_agent_id = None if scope == "global" else normalized
                scope_id = _scope_id(target_agent_id)
        asset_key = str(
            payload.get("asset_key")
            or payload.get("key")
            or (existing_row["asset_key"] if existing_row is not None else "")
            or payload.get("title")
            or ""
        ).strip()
        if not asset_key:
            raise ValueError("knowledge asset requires asset_key")
        now = now_iso()
        if existing_row is not None:
            execute(
                """
                UPDATE cp_knowledge_assets
                SET scope_id = ?, agent_id = ?, asset_key = ?, title = ?, kind = ?, content_text = ?,
                    body_json = ?, enabled = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    scope_id,
                    target_agent_id,
                    asset_key,
                    str(payload.get("title") or existing_row["title"] or asset_key),
                    str(payload.get("kind") or existing_row["kind"] or "entry"),
                    str(payload.get("content_text") or payload.get("content") or existing_row["content_text"] or ""),
                    json_dump(
                        _safe_json_object(payload.get("body") or payload) or json_load(existing_row["body_json"], {})
                    ),
                    1 if bool(payload.get("enabled", bool(int(existing_row["enabled"] or 0)))) else 0,
                    now,
                    asset_id,
                ),
            )
            row = fetch_one("SELECT * FROM cp_knowledge_assets WHERE id = ?", (asset_id,))
        else:
            execute(
                """
                INSERT INTO cp_knowledge_assets (
                    scope_id, agent_id, asset_key, title, kind, content_text, body_json, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope_id, asset_key) DO UPDATE SET
                    title = excluded.title,
                    kind = excluded.kind,
                    content_text = excluded.content_text,
                    body_json = excluded.body_json,
                    enabled = excluded.enabled,
                    updated_at = excluded.updated_at
                """,
                (
                    scope_id,
                    target_agent_id,
                    asset_key,
                    str(payload.get("title") or asset_key),
                    str(payload.get("kind") or "entry"),
                    str(payload.get("content_text") or payload.get("content") or ""),
                    json_dump(_safe_json_object(payload.get("body") or payload)),
                    1 if bool(payload.get("enabled", True)) else 0,
                    now,
                    now,
                ),
            )
            row = fetch_one(
                "SELECT * FROM cp_knowledge_assets WHERE scope_id = ? AND asset_key = ?", (scope_id, asset_key)
            )
        if row is None:
            raise RuntimeError("failed to persist knowledge asset")
        return self._serialize_knowledge_asset(row)

    def delete_knowledge_asset(self, agent_id: str, asset_id: int) -> bool:
        _, row = self._resolve_knowledge_asset_row(agent_id, asset_id)
        execute("DELETE FROM cp_knowledge_assets WHERE id = ?", (int(row["id"]),))
        return True

    def list_template_assets(self, agent_id: str, *, include_global: bool = True) -> list[dict[str, Any]]:
        return self._list_named_assets("cp_template_assets", agent_id, include_global=include_global)

    def upsert_template_asset(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._upsert_named_asset("cp_template_assets", agent_id, payload)

    def delete_template_asset(self, agent_id: str, asset_id: int) -> bool:
        _, row = self._resolve_named_asset_row("cp_template_assets", agent_id, asset_id)
        execute("DELETE FROM cp_template_assets WHERE id = ?", (int(row["id"]),))
        return True

    def list_skill_assets(self, agent_id: str, *, include_global: bool = True) -> list[dict[str, Any]]:
        return self._list_named_assets("cp_skill_assets", agent_id, include_global=include_global)

    def upsert_skill_asset(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._upsert_named_asset("cp_skill_assets", agent_id, payload)

    def delete_skill_asset(self, agent_id: str, asset_id: int) -> bool:
        _, row = self._resolve_named_asset_row("cp_skill_assets", agent_id, asset_id)
        execute("DELETE FROM cp_skill_assets WHERE id = ?", (int(row["id"]),))
        return True

    def list_secret_assets(self, agent_id: str, *, include_global: bool = True) -> list[dict[str, Any]]:
        normalized, _ = self._require_agent_row(agent_id)
        scope_ids = ["global", normalized] if include_global else [normalized]
        placeholders = ",".join("?" for _ in scope_ids)
        rows = fetch_all(
            f"""
            SELECT * FROM cp_secret_values
            WHERE scope_id IN ({placeholders})
            ORDER BY CASE scope_id WHEN 'global' THEN 0 ELSE 1 END, secret_key ASC
            """,
            tuple(scope_ids),
        )
        return [
            {
                "id": int(row["id"]),
                "scope": "global" if str(row["scope_id"]) == "global" else "agent",
                "secret_key": str(row["secret_key"]),
                # Preview stripped — see _current_global_secrets for rationale.
                "preview": "",
                "updated_at": str(row["updated_at"] or ""),
            }
            for row in rows
        ]

    def get_secret_asset(self, agent_id: str, secret_key: str, *, scope: str = "agent") -> dict[str, Any] | None:
        normalized, _ = self._require_agent_row(agent_id)
        normalized_scope = _normalize_scope(scope)
        if normalized_scope != "agent":
            raise ValueError("global secrets must be managed through /api/control-plane/system-settings.")
        normalized_secret_key = _normalize_secret_key(secret_key)
        scope_id = _scope_id(normalized)
        row = fetch_one(
            "SELECT * FROM cp_secret_values WHERE scope_id = ? AND secret_key = ?",
            (scope_id, normalized_secret_key),
        )
        if row is None:
            return None
        return {
            "id": int(row["id"]),
            "scope": normalized_scope,
            "secret_key": normalized_secret_key,
            # Preview stripped — browser sees only presence, never shape.
            "preview": "",
            "updated_at": str(row["updated_at"] or ""),
        }

    def get_decrypted_secret_value(self, agent_id: str, secret_key: str) -> str | None:
        """Return the decrypted value of an agent secret. Internal use only."""
        normalized, _ = self._require_agent_row(agent_id)
        scope_id = _scope_id(normalized)
        normalized_key = _normalize_secret_key(secret_key)
        row = fetch_one(
            "SELECT encrypted_value FROM cp_secret_values WHERE scope_id = ? AND secret_key = ?",
            (scope_id, normalized_key),
        )
        if row is None:
            return None
        encrypted = str(row["encrypted_value"] or "").strip()
        if not encrypted:
            return None
        log.info("secret_value_accessed", agent_id=agent_id, secret_key=secret_key)
        return decrypt_secret(encrypted)

    def upsert_secret_asset(
        self, agent_id: str, secret_key: str, payload: dict[str, Any], *, scope: str = "agent"
    ) -> dict[str, Any]:
        normalized, _ = self._require_agent_row(agent_id)
        normalized_scope = _normalize_scope(scope)
        if normalized_scope != "agent":
            raise ValueError("global secrets must be managed through /api/control-plane/system-settings.")
        normalized_secret_key = _normalize_secret_key(secret_key)
        scope_id = _scope_id(normalized)
        value = str(payload.get("value") or "")
        if not value:
            raise ValueError("secret value must not be empty")
        now = now_iso()
        execute(
            """
            INSERT INTO cp_secret_values (
                scope_id, agent_id, secret_key, encrypted_value, preview, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(scope_id, secret_key) DO UPDATE SET
                encrypted_value = excluded.encrypted_value,
                preview = excluded.preview,
                updated_at = excluded.updated_at
            """,
            (
                scope_id,
                normalized,
                normalized_secret_key,
                encrypt_secret(value),
                mask_secret(value),
                now,
                now,
            ),
        )
        return self.get_secret_asset(normalized, normalized_secret_key, scope=normalized_scope) or {}

    def delete_secret_asset(self, agent_id: str, secret_key: str, *, scope: str = "agent") -> bool:
        normalized, _ = self._require_agent_row(agent_id)
        normalized_scope = _normalize_scope(scope)
        if normalized_scope != "agent":
            raise ValueError("global secrets must be managed through /api/control-plane/system-settings.")
        normalized_secret_key = _normalize_secret_key(secret_key)
        scope_id = _scope_id(normalized)
        execute("DELETE FROM cp_secret_values WHERE scope_id = ? AND secret_key = ?", (scope_id, normalized_secret_key))
        return True

    def list_versions(self, agent_id: str) -> list[dict[str, Any]]:
        normalized, _ = self._require_agent_row(agent_id)
        rows = fetch_all(
            """
            SELECT version, status, summary, created_at, published_at
            FROM cp_agent_config_versions
            WHERE agent_id = ?
            ORDER BY version DESC
            """,
            (normalized,),
        )
        return [
            {
                "version": int(row["version"]),
                "status": str(row["status"]),
                "summary": str(row["summary"] or ""),
                "created_at": str(row["created_at"] or ""),
                "published_at": str(row["published_at"] or ""),
            }
            for row in rows
        ]

    def get_published_snapshot(self, agent_id: str, version: int | None = None) -> dict[str, Any] | None:
        normalized, _ = self._require_agent_row(agent_id)
        if version is None:
            current = fetch_one(
                "SELECT applied_version, desired_version FROM cp_agent_definitions WHERE id = ?", (normalized,)
            )
            if current is None:
                return None
            version = int(current["applied_version"] or current["desired_version"] or 0)
        if version <= 0:
            return None
        row = fetch_one(
            "SELECT snapshot_json FROM cp_agent_config_versions WHERE agent_id = ? AND version = ?",
            (normalized, version),
        )
        return json_load(str(row["snapshot_json"]), {}) if row else None

    def build_draft_snapshot(self, agent_id: str) -> dict[str, Any]:
        normalized = _normalize_agent_id(agent_id)
        agent_row = fetch_one("SELECT * FROM cp_agent_definitions WHERE id = ?", (normalized,))
        if agent_row is None:
            raise KeyError(normalized)
        section_states = {section: self.get_section(normalized, section) for section in AGENT_SECTIONS}
        sections = {section: _safe_json_object(state.get("effective")) for section, state in section_states.items()}
        env: dict[str, str] = dict(self._merged_global_env())
        for section, data in sections.items():
            if section == "access":
                continue
            env.update(_section_env(_safe_json_object(data)))
        env.update(self._provider_connection_env())
        for env_key in _CORE_CONNECTION_RUNTIME_ENV_KEYS:
            env.pop(env_key, None)
        for api_key_env in PROVIDER_API_KEY_ENV_KEYS.values():
            env.pop(api_key_env, None)
        access_effective = _safe_json_object(section_states["access"]["effective"])
        access_data = _safe_json_object(section_states["access"]["data"])
        access_policy = normalize_agent_spec(
            {"resource_access_policy": _safe_json_object(access_effective.get("resource_access_policy"))}
        ).get("resource_access_policy", {})
        explicit_access_policy = "resource_access_policy" in access_data
        env.update(self._resolved_shared_env_values(_safe_json_object(access_policy), access_effective))
        env.update(_sanitize_local_env_overrides(_safe_json_object(access_policy).get("local_env")))
        documents = {kind: (self.get_document(normalized, kind) or {}).get("content_md", "") for kind in DOCUMENT_KINDS}
        knowledge_assets = [
            asset for asset in self.list_knowledge_assets(normalized) if bool(asset.get("enabled", True))
        ]
        templates = self.list_template_assets(normalized)
        skills = self.list_skill_assets(normalized)
        secrets = self._resolved_secret_values(
            normalized,
            resource_access_policy=_safe_json_object(access_policy),
            explicit_policy=explicit_access_policy,
        )
        latest_global_version = self.get_global_defaults()["version"]
        health_port = int(
            env.get("HEALTH_PORT") or json_load(agent_row["runtime_endpoint_json"], {}).get("health_port") or 8080
        )
        runtime_endpoint = {
            "health_port": health_port,
            "health_url": f"http://127.0.0.1:{health_port}/health",
            "runtime_base_url": f"http://127.0.0.1:{health_port}",
        }
        stored_runtime_endpoint = _safe_json_object(json_load(agent_row["runtime_endpoint_json"], {}))
        runtime_endpoint.update(stored_runtime_endpoint)
        runtime_endpoint = self._normalize_runtime_endpoint_for_agent(normalized, runtime_endpoint)
        if runtime_endpoint != stored_runtime_endpoint:
            execute(
                "UPDATE cp_agent_definitions SET runtime_endpoint_json = ?, updated_at = ? WHERE id = ?",
                (json_dump(runtime_endpoint), now_iso(), normalized),
            )
        # Post-update: re-read health_port in case runtime_endpoint_json overrode it, then
        # propagate to process_env so the spawned worker binds the same port the supervisor
        # expects to poll for liveness/idle checks. Without this the worker falls back to
        # config.HEALTH_PORT default (8080) while the supervisor polls the per-agent value.
        _hp = runtime_endpoint.get("health_port")
        effective_health_port = int(_hp) if isinstance(_hp, (int, str)) else int(health_port)
        runtime_endpoint["health_port"] = effective_health_port
        runtime_endpoint["health_url"] = f"http://127.0.0.1:{effective_health_port}/health"
        runtime_endpoint["runtime_base_url"] = f"http://127.0.0.1:{effective_health_port}"
        env["HEALTH_PORT"] = str(effective_health_port)
        appearance = _safe_json_object(json_load(agent_row["appearance_json"], {}))
        appearance.setdefault("label", str(agent_row["display_name"]))
        connection_refs = self._runtime_connection_refs(normalized)
        return {
            "agent": {
                "id": normalized,
                "display_name": str(agent_row["display_name"]),
                "status": str(agent_row["status"]),
                "storage_namespace": str(agent_row["storage_namespace"]),
                "appearance": appearance,
                "runtime_endpoint": runtime_endpoint,
                "metadata": _safe_json_object(json_load(agent_row["metadata_json"], {})),
            },
            "sections": sections,
            "env": env,
            "process_env": env,
            "connection_refs": connection_refs,
            "documents": documents,
            "knowledge_assets": knowledge_assets,
            "templates": templates,
            "skills": skills,
            "secrets": secrets,
            "resource_access": {
                "policy": access_policy,
                "explicit_policy": explicit_access_policy,
                "shared_variables": [
                    {"key": key, "value": value}
                    for key, value in self._resolved_shared_env_values(
                        _safe_json_object(access_policy),
                        access_effective,
                    ).items()
                ],
                "global_secret_keys": sorted(
                    [
                        key
                        for key, payload in secrets.items()
                        if str(_safe_json_object(payload).get("scope")) == "global"
                    ]
                ),
            },
            "global_defaults_version": latest_global_version,
            "created_at": now_iso(),
        }

    def publish_agent(self, agent_id: str) -> dict[str, Any]:
        normalized, _ = self._require_agent_row(agent_id)
        checks = self.publish_checks(normalized)
        if checks["errors"]:
            raise ValueError("; ".join(str(item) for item in checks["errors"]))
        snapshot = self.build_draft_snapshot(normalized)
        row = fetch_one(
            "SELECT COALESCE(MAX(version), 0) AS version FROM cp_agent_config_versions WHERE agent_id = ?",
            (normalized,),
        )
        next_version = int(row["version"] or 0) + 1 if row else 1
        summary = f"Published control-plane snapshot for {normalized} v{next_version}"
        now = now_iso()
        execute(
            """
            INSERT INTO cp_agent_config_versions (
                agent_id, version, snapshot_json, status, summary, created_at, published_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized,
                next_version,
                json_dump(snapshot),
                "published",
                summary,
                now,
                now,
            ),
        )
        current = fetch_one("SELECT applied_version FROM cp_agent_definitions WHERE id = ?", (normalized,))
        applied_version = int(current["applied_version"] or 0) if current else 0
        execute(
            """
            UPDATE cp_agent_definitions
            SET desired_version = ?, updated_at = ?
            WHERE id = ?
            """,
            (next_version, now, normalized),
        )
        execute(
            """
            INSERT INTO cp_apply_operations (agent_id, target_version, status, requested_at, details_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (normalized, next_version, "pending", now, json_dump({"summary": summary})),
        )
        return {
            "agent_id": normalized,
            "version": next_version,
            "summary": summary,
            "desired_version": next_version,
            "applied_version": applied_version or None,
        }

    def build_runtime_snapshot(self, agent_id: str, version: int | None = None) -> RuntimeSnapshot:
        return self._resolve_runtime_snapshot(agent_id, version=version)

    def _resolve_runtime_snapshot(
        self,
        agent_id: str,
        *,
        version: int | None = None,
    ) -> RuntimeSnapshot:
        normalized = _normalize_agent_id(agent_id)
        snapshot = self.get_published_snapshot(normalized, version=version)
        if snapshot is None:
            publish = self.publish_agent(normalized)
            snapshot = self.get_published_snapshot(normalized, version=int(publish["version"]))
        if snapshot is None:
            raise RuntimeError(f"no published snapshot found for {normalized}")
        actual_version = int(version or self._snapshot_version(normalized, snapshot))
        runtime_dir = CONTROL_PLANE_RUNTIME_DIR / _slug(normalized) / f"version_{actual_version}"
        inline_mode = True
        persisted_to_disk = False

        runtime_env = {
            key: _stringify_env_value(value)
            for key, value in _safe_json_object(snapshot.get("process_env") or snapshot.get("env")).items()
        }
        for env_key in _CORE_CONNECTION_RUNTIME_ENV_KEYS:
            runtime_env.pop(env_key, None)
        connection_refs: list[dict[str, Any]] = []
        for item in _safe_json_list(snapshot.get("connection_refs")):
            if not isinstance(item, dict):
                continue
            ref = _safe_json_object(item)
            kind = str(ref.get("kind") or "").strip().lower()
            connection_key = str(ref.get("connection_key") or "").strip().lower()
            integration_key = str(ref.get("integration_key") or "").strip().lower()
            if kind == "core" or connection_key.startswith("core:"):
                core_id = integration_key or connection_key.split(":", 1)[1]
                if core_id not in CORE_INTEGRATION_CATALOG:
                    continue
            connection_refs.append(ref)
        runtime_snapshot = dict(snapshot)
        runtime_snapshot["env"] = runtime_env
        runtime_snapshot["process_env"] = runtime_env
        runtime_snapshot["connection_refs"] = connection_refs

        agent_spec = self.get_agent_spec(normalized, snapshot=runtime_snapshot)

        # Apply workspace -> squad -> agent hierarchical merge
        try:
            agent_row = fetch_one("SELECT * FROM cp_agent_definitions WHERE id = ?", (normalized,))
            if agent_row is not None:
                agent_spec = self._resolve_hierarchical_spec(agent_spec, agent_row)
        except Exception:
            log.warning("hierarchical_spec_merge_skipped", agent_id=normalized, exc_info=True)

        docs = _safe_json_object(agent_spec.get("documents"))
        composed_prompt = _compose_agent_prompt(docs)

        inline_documents: dict[str, str] = {}
        for kind in _RUNTIME_INLINE_DOCUMENT_KINDS:
            content = _trimmed_text(docs.get(kind))
            if not content:
                continue
            inline_documents[kind] = content

        templates = {str(asset["name"]): str(asset["content"]) for asset in _safe_json_list(snapshot.get("templates"))}

        memory_policy = _safe_json_object(agent_spec.get("memory_policy"))
        env = dict(runtime_env)
        providers_section = _safe_json_object(_safe_json_object(snapshot.get("sections")).get("providers"))
        access_section = _safe_json_object(_safe_json_object(snapshot.get("sections")).get("access"))
        general_ui = _safe_json_object(access_section.get("general_ui"))
        latest_general_ui = self._general_ui_meta(sections=self._system_settings_sections())
        enabled_providers = normalize_string_list(providers_section.get("providers_enabled"))
        functional_defaults_env = _normalize_functional_model_defaults(
            _typed_env_value(env.get("MODEL_FUNCTION_DEFAULTS_JSON"), "json")
        )
        audio_default = _safe_json_object(functional_defaults_env.get("audio"))
        audio_provider = _trimmed_text(audio_default.get("provider_id")).lower() or "kokoro"
        audio_model = _trimmed_text(audio_default.get("model_id"))
        if audio_provider == "elevenlabs" and audio_model:
            env["ELEVENLABS_MODEL"] = audio_model
        if audio_provider == "supertonic" and audio_model:
            env["SUPERTONIC_DEFAULT_MODEL"] = audio_model
        if audio_provider == "elevenlabs" and not _nonempty_text(env.get("ELEVENLABS_API_KEY")):
            # Provider connection secrets are stripped from the persisted snapshot.
            # Rehydrate the selected audio provider key only in process_env so
            # ElevenLabs TTS can run without granting the key as a generic agent
            # resource.
            elevenlabs_api_key = self._provider_api_key_secret_value("elevenlabs")
            if elevenlabs_api_key:
                env["ELEVENLABS_API_KEY"] = elevenlabs_api_key
                env["ELEVENLABS_ENABLED"] = "true"
        elevenlabs_default_voice = _nonempty_text(providers_section.get("elevenlabs_default_voice")) or _nonempty_text(
            providers_section.get("tts_default_voice")
        )
        if not elevenlabs_default_voice and (
            _nonempty_text(general_ui.get("elevenlabs_default_voice_label"))
            or _nonempty_text(latest_general_ui.get("elevenlabs_default_voice_label"))
        ):
            elevenlabs_default_voice = _nonempty_text(env.get("TTS_DEFAULT_VOICE"))
        elevenlabs_ready = self._bool_from_env(env, "ELEVENLABS_CONNECTION_VERIFIED", False) or bool(
            _nonempty_text(env.get("ELEVENLABS_API_KEY"))
        )
        elevenlabs_enabled = "elevenlabs" in enabled_providers
        if audio_provider == "elevenlabs" and not elevenlabs_default_voice:
            audio_provider = "kokoro"
        kokoro_default_voice = (
            _nonempty_text(providers_section.get("kokoro_default_voice"))
            or _nonempty_text(env.get("KOKORO_DEFAULT_VOICE"))
            or KOKORO_DEFAULT_VOICE_ID
        )
        env["KOKORO_DEFAULT_VOICE"] = kokoro_default_voice
        env["KOKORO_DEFAULT_LANGUAGE"] = (
            _nonempty_text(providers_section.get("kokoro_default_language"))
            or _nonempty_text(env.get("KOKORO_DEFAULT_LANGUAGE"))
            or KOKORO_DEFAULT_LANGUAGE_ID
        )
        supertonic_default_model = (
            _nonempty_text(providers_section.get("supertonic_default_model"))
            or _nonempty_text(env.get("SUPERTONIC_DEFAULT_MODEL"))
            or SUPERTONIC_DEFAULT_MODEL_ID
        )
        supertonic_default_voice = (
            _nonempty_text(providers_section.get("supertonic_default_voice"))
            or _nonempty_text(env.get("SUPERTONIC_DEFAULT_VOICE"))
            or SUPERTONIC_DEFAULT_VOICE_ID
        )
        env["SUPERTONIC_DEFAULT_MODEL"] = supertonic_default_model
        env["SUPERTONIC_DEFAULT_VOICE"] = supertonic_default_voice
        env["SUPERTONIC_DEFAULT_LANGUAGE"] = (
            _nonempty_text(providers_section.get("supertonic_default_language"))
            or _nonempty_text(env.get("SUPERTONIC_DEFAULT_LANGUAGE"))
            or SUPERTONIC_DEFAULT_LANGUAGE_ID
        )
        if elevenlabs_default_voice and (
            audio_provider == "elevenlabs" or (elevenlabs_ready and not elevenlabs_enabled)
        ):
            env["TTS_DEFAULT_VOICE"] = elevenlabs_default_voice
        elif audio_provider == "supertonic":
            env["TTS_DEFAULT_VOICE"] = supertonic_default_voice
        else:
            env["TTS_DEFAULT_VOICE"] = kokoro_default_voice
        try:
            env["KOKORO_VOICES_PATH"] = str(kokoro_managed_voices_storage_path())
        except Exception:
            log.warning("control_plane_kokoro_assets_unavailable", agent_id=normalized, exc_info=True)
        resource_access_policy = normalize_resource_access_policy(
            _safe_json_object(agent_spec.get("resource_access_policy"))
        )
        if resource_access_policy and "AGENT_RESOURCE_ACCESS_POLICY_JSON" not in env:
            env["AGENT_RESOURCE_ACCESS_POLICY_JSON"] = json_dump(resource_access_policy)
        if _safe_json_object(agent_spec.get("tool_policy")) and "AGENT_TOOL_POLICY_JSON" not in env:
            env["AGENT_TOOL_POLICY_JSON"] = json_dump(agent_spec["tool_policy"])
        if _safe_json_object(agent_spec.get("model_policy")):
            env["AGENT_MODEL_POLICY_JSON"] = json_dump(agent_spec["model_policy"])
        if _safe_json_object(agent_spec.get("autonomy_policy")) and "AGENT_AUTONOMY_POLICY_JSON" not in env:
            env["AGENT_AUTONOMY_POLICY_JSON"] = json_dump(agent_spec["autonomy_policy"])
        provider_runtime_eligibility = _safe_json_object(snapshot.get("provider_runtime_eligibility"))
        if provider_runtime_eligibility and "AGENT_PROVIDER_RUNTIME_ELIGIBILITY_JSON" not in env:
            env["AGENT_PROVIDER_RUNTIME_ELIGIBILITY_JSON"] = json_dump(provider_runtime_eligibility)
        allowed_tool_ids = normalize_string_list(
            _safe_json_object(agent_spec.get("tool_policy")).get("allowed_tool_ids")
        )
        if allowed_tool_ids and "AGENT_ALLOWED_TOOLS" not in env:
            env["AGENT_ALLOWED_TOOLS"] = ",".join(allowed_tool_ids)
        if memory_policy:
            if memory_policy.get("enabled") is not None:
                env["MEMORY_ENABLED"] = _stringify_env_value(memory_policy["enabled"])
            if memory_policy.get("max_recall") is not None:
                env["MEMORY_MAX_RECALL"] = _stringify_env_value(memory_policy["max_recall"])
            if memory_policy.get("recall_threshold") is not None:
                env["MEMORY_RECALL_THRESHOLD"] = _stringify_env_value(memory_policy["recall_threshold"])
            if memory_policy.get("max_context_tokens") is not None:
                env["MEMORY_MAX_CONTEXT_TOKENS"] = _stringify_env_value(memory_policy["max_context_tokens"])
            if memory_policy.get("recency_half_life_days") is not None:
                env["MEMORY_RECENCY_HALF_LIFE_DAYS"] = _stringify_env_value(memory_policy["recency_half_life_days"])
            if memory_policy.get("max_extraction_items") is not None:
                env["MEMORY_MAX_EXTRACTION_ITEMS"] = _stringify_env_value(memory_policy["max_extraction_items"])
            if memory_policy.get("extraction_provider") not in (None, ""):
                env["MEMORY_EXTRACTION_PROVIDER"] = _stringify_env_value(memory_policy["extraction_provider"])
            if memory_policy.get("extraction_model") not in (None, ""):
                env["MEMORY_EXTRACTION_MODEL"] = _stringify_env_value(memory_policy["extraction_model"])
            if memory_policy.get("proactive_enabled") is not None:
                env["MEMORY_PROACTIVE_ENABLED"] = _stringify_env_value(memory_policy["proactive_enabled"])
            if memory_policy.get("procedural_enabled") is not None:
                env["MEMORY_PROCEDURAL_ENABLED"] = _stringify_env_value(memory_policy["procedural_enabled"])
            if memory_policy.get("procedural_max_recall") is not None:
                env["MEMORY_PROCEDURAL_MAX_RECALL"] = _stringify_env_value(memory_policy["procedural_max_recall"])
            if memory_policy.get("recall_timeout") is not None:
                env["MEMORY_RECALL_TIMEOUT"] = _stringify_env_value(memory_policy["recall_timeout"])
            if memory_policy.get("similarity_dedup_threshold") is not None:
                env["MEMORY_SIMILARITY_DEDUP_THRESHOLD"] = _stringify_env_value(
                    memory_policy["similarity_dedup_threshold"]
                )
            if memory_policy.get("max_per_user") is not None:
                env["MEMORY_MAX_PER_USER"] = _stringify_env_value(memory_policy["max_per_user"])
            if memory_policy.get("maintenance_enabled") is not None:
                env["MEMORY_MAINTENANCE_ENABLED"] = _stringify_env_value(memory_policy["maintenance_enabled"])
            if memory_policy.get("digest_enabled") is not None:
                env["MEMORY_DIGEST_ENABLED"] = _stringify_env_value(memory_policy["digest_enabled"])

        knowledge_policy = _safe_json_object(agent_spec.get("knowledge_policy"))
        if knowledge_policy:
            if knowledge_policy.get("enabled") is not None:
                env["KNOWLEDGE_ENABLED"] = _stringify_env_value(knowledge_policy["enabled"])
            if knowledge_policy.get("max_results") is not None:
                env["KNOWLEDGE_MAX_RESULTS"] = _stringify_env_value(knowledge_policy["max_results"])
            if knowledge_policy.get("recall_threshold") is not None:
                env["KNOWLEDGE_RECALL_THRESHOLD"] = _stringify_env_value(knowledge_policy["recall_threshold"])
            if knowledge_policy.get("recall_timeout") is not None:
                env["KNOWLEDGE_RECALL_TIMEOUT"] = _stringify_env_value(knowledge_policy["recall_timeout"])
            if knowledge_policy.get("context_max_tokens") is not None:
                env["KNOWLEDGE_CONTEXT_MAX_TOKENS"] = _stringify_env_value(knowledge_policy["context_max_tokens"])
            if knowledge_policy.get("workspace_max_files") is not None:
                env["KNOWLEDGE_WORKSPACE_MAX_FILES"] = _stringify_env_value(knowledge_policy["workspace_max_files"])
            source_globs = normalize_string_list(knowledge_policy.get("source_globs"))
            if source_globs:
                env["KNOWLEDGE_SOURCE_GLOBS"] = ",".join(source_globs)
            workspace_source_globs = normalize_string_list(knowledge_policy.get("workspace_source_globs"))
            if workspace_source_globs:
                env["KNOWLEDGE_WORKSPACE_SOURCE_GLOBS"] = ",".join(workspace_source_globs)
            if knowledge_policy.get("max_observed_patterns") is not None:
                env["KNOWLEDGE_MAX_OBSERVED_PATTERNS"] = _stringify_env_value(knowledge_policy["max_observed_patterns"])
            allowed_layers = normalize_string_list(knowledge_policy.get("allowed_layers"))
            if allowed_layers:
                env["KNOWLEDGE_ALLOWED_LAYERS"] = ",".join(allowed_layers)
            allowed_source_labels = normalize_string_list(knowledge_policy.get("allowed_source_labels"))
            if allowed_source_labels:
                env["KNOWLEDGE_ALLOWED_SOURCE_LABELS"] = ",".join(allowed_source_labels)
            allowed_workspace_roots = normalize_string_list(knowledge_policy.get("allowed_workspace_roots"))
            if allowed_workspace_roots:
                env["KNOWLEDGE_ALLOWED_WORKSPACE_ROOTS"] = ",".join(allowed_workspace_roots)
            if knowledge_policy.get("max_source_age_days") is not None:
                env["KNOWLEDGE_MAX_SOURCE_AGE_DAYS"] = _stringify_env_value(knowledge_policy["max_source_age_days"])
            if knowledge_policy.get("require_owner_provenance") is not None:
                env["KNOWLEDGE_REQUIRE_OWNER_PROVENANCE"] = _stringify_env_value(
                    knowledge_policy["require_owner_provenance"]
                )
            if knowledge_policy.get("require_freshness_provenance") is not None:
                env["KNOWLEDGE_REQUIRE_FRESHNESS_PROVENANCE"] = _stringify_env_value(
                    knowledge_policy["require_freshness_provenance"]
                )
            if knowledge_policy.get("promotion_mode") not in (None, ""):
                env["KNOWLEDGE_PROMOTION_MODE"] = _stringify_env_value(knowledge_policy["promotion_mode"])
            if knowledge_policy.get("strategy_default") not in (None, ""):
                env["KNOWLEDGE_STRATEGY_DEFAULT"] = _stringify_env_value(knowledge_policy["strategy_default"])
            if knowledge_policy.get("trace_sampling_rate") is not None:
                env["KNOWLEDGE_TRACE_SAMPLING_RATE"] = _stringify_env_value(knowledge_policy["trace_sampling_rate"])
            if knowledge_policy.get("graph_enabled") is not None:
                env["KNOWLEDGE_GRAPH_ENABLED"] = _stringify_env_value(knowledge_policy["graph_enabled"])
            if knowledge_policy.get("multimodal_graph_enabled") is not None:
                env["KNOWLEDGE_MULTIMODAL_GRAPH_ENABLED"] = _stringify_env_value(
                    knowledge_policy["multimodal_graph_enabled"]
                )
            if knowledge_policy.get("evaluation_sampling_rate") is not None:
                env["KNOWLEDGE_EVALUATION_SAMPLING_RATE"] = _stringify_env_value(
                    knowledge_policy["evaluation_sampling_rate"]
                )
            if knowledge_policy.get("citation_policy") not in (None, ""):
                env["KNOWLEDGE_CITATION_POLICY"] = _stringify_env_value(knowledge_policy["citation_policy"])
            if knowledge_policy.get("v2_enabled") is not None:
                env["KNOWLEDGE_V2_ENABLED"] = _stringify_env_value(knowledge_policy["v2_enabled"])
            if knowledge_policy.get("v2_max_graph_hops") is not None:
                env["KNOWLEDGE_V2_MAX_GRAPH_HOPS"] = _stringify_env_value(knowledge_policy["v2_max_graph_hops"])
            if knowledge_policy.get("cross_encoder_model") not in (None, ""):
                env["KNOWLEDGE_V2_CROSS_ENCODER_MODEL"] = _stringify_env_value(knowledge_policy["cross_encoder_model"])
            if knowledge_policy.get("storage_mode") not in (None, ""):
                env["KNOWLEDGE_V2_STORAGE_MODE"] = _stringify_env_value(knowledge_policy["storage_mode"])
            if knowledge_policy.get("object_store_root") not in (None, ""):
                env["KNOWLEDGE_V2_OBJECT_STORE_ROOT"] = _stringify_env_value(knowledge_policy["object_store_root"])
        for secret_key, secret_payload in _safe_json_object(snapshot.get("secrets")).items():
            if secret_key.strip().upper() in _CORE_CONNECTION_RUNTIME_ENV_KEYS:
                continue
            encrypted_value = str(_safe_json_object(secret_payload).get("encrypted_value") or "").strip()
            if not encrypted_value:
                continue
            env[secret_key] = decrypt_secret(encrypted_value)
        if not str(env.get("RUNTIME_LOCAL_UI_TOKEN") or "").strip():
            try:
                from .runtime_access import ControlPlaneRuntimeAccessBroker

                runtime_ui_secret = ControlPlaneRuntimeAccessBroker(self).resolve_runtime_secret(normalized, snapshot)
            except Exception:
                runtime_ui_secret = ""
                log.debug("runtime_ui_secret_resolve_skipped", agent_id=normalized, exc_info=True)
            if runtime_ui_secret:
                env["RUNTIME_LOCAL_UI_TOKEN"] = runtime_ui_secret
        env["CONTROL_PLANE_RUNTIME_INLINE"] = "true" if inline_mode else "false"
        if composed_prompt:
            env["AGENT_COMPILED_PROMPT_TEXT"] = composed_prompt
        if inline_mode:
            if templates:
                env["TEMPLATES_JSON"] = json.dumps(templates, ensure_ascii=False)
            if inline_documents.get("voice_prompt_md"):
                env["VOICE_ACTIVE_PROMPT_TEXT"] = inline_documents["voice_prompt_md"]
            if inline_documents.get("image_prompt_md"):
                env["DEFAULT_IMAGE_PROMPT_TEXT"] = inline_documents["image_prompt_md"]
            if inline_documents.get("memory_extraction_prompt_md"):
                env["MEMORY_EXTRACTION_PROMPT_TEXT"] = inline_documents["memory_extraction_prompt_md"]
            env["AGENT_SPEC_JSON"] = json_dump(agent_spec)
        env["CONTROL_PLANE_ACTIVE_VERSION"] = str(actual_version)

        agent_config = _safe_json_object(snapshot.get("agent"))
        runtime_endpoint = _safe_json_object(agent_config.get("runtime_endpoint"))
        # Propagate the per-agent health port into the spawned worker's env.
        # Without this the child falls back to config.HEALTH_PORT default (8080)
        # while the supervisor polls runtime_endpoint.health_url for liveness —
        # the poll always misses, _is_agent_idle returns False, and graceful
        # version-bump restarts never fire.
        endpoint_health_port = runtime_endpoint.get("health_port")
        if endpoint_health_port is not None:
            env["HEALTH_PORT"] = str(endpoint_health_port)
        health_url = str(
            runtime_endpoint.get("health_url") or f"http://127.0.0.1:{env.get('HEALTH_PORT', '8080')}/health"
        )
        runtime_base_url = str(
            runtime_endpoint.get("runtime_base_url") or health_url.removesuffix("/health").rstrip("/")
        )
        db_file_name = ""

        return RuntimeSnapshot(
            agent_id=normalized,
            version=actual_version,
            runtime_dir=runtime_dir,
            process_env=self._scoped_env(normalized, env),
            connection_refs=connection_refs,
            health_url=health_url,
            runtime_base_url=runtime_base_url,
            state_backend=STATE_BACKEND,
            db_file_name=db_file_name,
            persisted_to_disk=persisted_to_disk,
        )

    def get_runtime_access(
        self,
        agent_id: str,
        *,
        capability: str = "read",
        include_sensitive: bool = False,
    ) -> dict[str, Any]:
        from .runtime_access import ControlPlaneRuntimeAccessBroker

        return ControlPlaneRuntimeAccessBroker(self).get_runtime_access(
            agent_id,
            capability=capability,
            include_sensitive=include_sensitive,
        )

    def mark_apply_started(self, agent_id: str, version: int) -> None:
        normalized = _normalize_agent_id(agent_id)
        execute(
            """
            UPDATE cp_apply_operations
            SET status = ?, started_at = ?, details_json = ?
            WHERE id = (
                SELECT id FROM cp_apply_operations
                WHERE agent_id = ? AND target_version = ?
                ORDER BY id DESC LIMIT 1
            )
            """,
            ("in_progress", now_iso(), json_dump({"event": "restart_started"}), normalized, version),
        )

    def mark_apply_finished(
        self, agent_id: str, version: int, *, success: bool, details: dict[str, Any] | None = None
    ) -> None:
        normalized = _normalize_agent_id(agent_id)
        status = "applied" if success else "failed"
        execute(
            """
            UPDATE cp_apply_operations
            SET status = ?, applied_at = ?, details_json = ?
            WHERE id = (
                SELECT id FROM cp_apply_operations
                WHERE agent_id = ? AND target_version = ?
                ORDER BY id DESC LIMIT 1
            )
            """,
            (status, now_iso(), json_dump(details or {}), normalized, version),
        )
        if success:
            execute(
                "UPDATE cp_agent_definitions SET applied_version = ?, updated_at = ? WHERE id = ?",
                (version, now_iso(), normalized),
            )

    def import_legacy_state(self) -> None:
        if not self._auto_seed_enabled():
            return
        if self._seeding_legacy_state:
            return
        self._seeding_legacy_state = True
        log.info("control_plane_import_started")
        try:
            env_values = self._load_legacy_env()
            agent_ids = self._discover_legacy_agent_ids(env_values)
            existing_rows = fetch_all("SELECT id FROM cp_agent_definitions ORDER BY id ASC")
            existing_agent_ids = {str(row["id"]) for row in existing_rows}
            target_agent_ids = [agent_id for agent_id in agent_ids if agent_id not in existing_agent_ids]
            has_global_sections = bool(fetch_one("SELECT 1 FROM cp_global_sections LIMIT 1"))
            appearance_map = _parse_dashboard_appearance()

            shared_sections: dict[str, dict[str, Any]] = {section: {} for section in AGENT_SECTIONS}
            shared_secrets: dict[str, str] = {}
            agent_sections: dict[str, dict[str, dict[str, Any]]] = {
                agent_id: {section: {} for section in AGENT_SECTIONS} for agent_id in agent_ids
            }
            agent_secrets: dict[str, dict[str, str]] = {agent_id: {} for agent_id in agent_ids}

            for key, value in env_values.items():
                matched_agent: str | None = None
                remainder = key
                for candidate in sorted(agent_ids, key=len, reverse=True):
                    prefix = f"{candidate}_"
                    if key.startswith(prefix):
                        matched_agent = candidate
                        remainder = key[len(prefix) :]
                        break
                if matched_agent:
                    self._assign_env_value(
                        agent_sections[matched_agent], agent_secrets[matched_agent], remainder, value
                    )
                else:
                    self._assign_env_value(shared_sections, shared_secrets, key, value)

            if target_agent_ids and not has_global_sections:
                self.patch_global_defaults({"sections": shared_sections})

            for agent_id in target_agent_ids:
                general_env = _section_env(agent_sections[agent_id]["general"])
                display_name = str(
                    general_env.get("AGENT_NAME")
                    or appearance_map.get(agent_id, {}).get("label")
                    or agent_id.replace("_", " ")
                )
                storage_namespace = _slug(agent_id)
                health_port = int(general_env.get("HEALTH_PORT") or 8080)
                appearance = {
                    "label": appearance_map.get(agent_id, {}).get("label") or display_name,
                    "color": appearance_map.get(agent_id, {}).get("color") or "#A7ADB4",
                    "color_rgb": appearance_map.get(agent_id, {}).get("color_rgb") or "167, 173, 180",
                }
                runtime_endpoint = {
                    "health_port": health_port,
                    "health_url": f"http://127.0.0.1:{health_port}/health",
                    "runtime_base_url": f"http://127.0.0.1:{health_port}",
                }
                runtime_endpoint = self._normalize_runtime_endpoint_for_agent(agent_id, runtime_endpoint)
                self.create_agent(
                    {
                        "id": agent_id,
                        "display_name": display_name,
                        "appearance": appearance,
                        "storage_namespace": storage_namespace,
                        "runtime_endpoint": runtime_endpoint,
                        "status": "active",
                    }
                )
                for section, data in agent_sections[agent_id].items():
                    if data:
                        self.put_section(agent_id, section, {"data": data})
                for secret_key, value in agent_secrets[agent_id].items():
                    if not str(value).strip():
                        continue
                    self.upsert_secret_asset(agent_id, secret_key, {"value": value})

            global_secret_carrier = next(iter(existing_agent_ids or target_agent_ids), None)
            if global_secret_carrier:
                for secret_key, value in shared_secrets.items():
                    if not str(value).strip():
                        continue
                    self.upsert_global_secret_asset(secret_key, {"value": value})

            if target_agent_ids:
                self._import_legacy_templates(target_agent_ids)

            for agent_id in target_agent_ids:
                publish = self.publish_agent(agent_id)
                execute(
                    """
                    UPDATE cp_agent_definitions
                    SET applied_version = ?, desired_version = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (publish["version"], publish["version"], now_iso(), agent_id),
                )
            log.info(
                "control_plane_import_finished",
                discovered_agent_count=len(agent_ids),
                imported_agent_count=len(target_agent_ids),
            )
        finally:
            self._seeding_legacy_state = False

    def _serialize_agent_summary(
        self,
        row: Any,
        *,
        workspace_map: dict[str, Any] | None = None,
        squad_map: dict[str, Any] | None = None,
        default_model_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        appearance = _safe_json_object(json_load(row["appearance_json"], {}))
        runtime_endpoint = _safe_json_object(json_load(row["runtime_endpoint_json"], {}))
        storage_namespace = str(row["storage_namespace"])
        appearance.setdefault("label", str(row["display_name"]))
        return {
            "id": str(row["id"]),
            "display_name": str(row["display_name"]),
            "status": str(row["status"]),
            "appearance": appearance,
            "storage_namespace": storage_namespace,
            "runtime_endpoint": runtime_endpoint,
            "applied_version": int(row["applied_version"] or 0) or None,
            "desired_version": int(row["desired_version"] or 0) or None,
            "metadata": _safe_json_object(json_load(row["metadata_json"], {})),
            "organization": self._serialize_agent_organization(
                _normalize_optional_org_id(row["workspace_id"]) if _row_has_column(row, "workspace_id") else None,
                _normalize_optional_org_id(row["squad_id"]) if _row_has_column(row, "squad_id") else None,
                workspace_map=workspace_map,
                squad_map=squad_map,
            ),
            **(default_model_summary or {}),
            "state_backend": STATE_BACKEND,
            "db_file_name": "",
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }

    def _resolve_agent_default_model_summary(
        self,
        agent_id: str,
        *,
        snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized = _normalize_agent_id(agent_id)
        resolved_snapshot = snapshot or self.build_draft_snapshot(normalized)
        env_payload = {
            key: _stringify_env_value(value) for key, value in _safe_json_object(resolved_snapshot.get("env")).items()
        }
        provider_catalog = self._provider_catalog_from_env(env_payload)
        providers_section = _safe_json_object(_safe_json_object(resolved_snapshot.get("sections")).get("providers"))
        defaults = self._resolve_general_functional_defaults(
            providers_section=providers_section,
            provider_catalog=provider_catalog,
        )
        selection = _safe_json_object(defaults.get("general"))
        provider_id = _nonempty_text(selection.get("provider_id")).lower()
        model_id = _nonempty_text(selection.get("model_id"))
        if not provider_id or not model_id:
            return {}

        option = _safe_json_object(
            _safe_json_object(self._functional_model_option_map(provider_catalog).get("general")).get(
                f"{provider_id}:{model_id}"
            )
        )
        provider_payload = _safe_json_object(_safe_json_object(provider_catalog.get("providers")).get(provider_id))
        model_label = _nonempty_text(option.get("title")) or model_id
        provider_label = _nonempty_text(provider_payload.get("title")) or provider_id.title()
        return {
            "default_model_provider_id": provider_id,
            "default_model_provider_label": provider_label,
            "default_model_id": model_id,
            "default_model_label": model_label,
        }

    def _serialize_knowledge_asset(self, row: Any) -> dict[str, Any]:
        body = _safe_json_object(json_load(row["body_json"], {}))
        if not body.get("content") and str(row["content_text"] or "").strip():
            body["content"] = str(row["content_text"])
        return {
            "id": int(row["id"]),
            "scope": "global" if str(row["scope_id"]) == "global" else "agent",
            "asset_key": str(row["asset_key"]),
            "title": str(row["title"] or row["asset_key"]),
            "kind": str(row["kind"] or "entry"),
            "content_text": str(row["content_text"] or ""),
            "body": body,
            "enabled": bool(int(row["enabled"] or 0)),
            "updated_at": str(row["updated_at"] or ""),
        }

    def _list_named_assets(self, table: str, agent_id: str, *, include_global: bool) -> list[dict[str, Any]]:
        normalized, _ = self._require_agent_row(agent_id)
        scope_ids = ["global", normalized] if include_global else [normalized]
        placeholders = ",".join("?" for _ in scope_ids)
        rows = fetch_all(
            f"""
            SELECT * FROM {table}
            WHERE scope_id IN ({placeholders})
            ORDER BY CASE scope_id WHEN 'global' THEN 0 ELSE 1 END, name ASC
            """,
            tuple(scope_ids),
        )
        return [
            {
                "id": int(row["id"]),
                "scope": "global" if str(row["scope_id"]) == "global" else "agent",
                "name": str(row["name"]),
                "content": str(row["content"]),
                "updated_at": str(row["updated_at"]),
            }
            for row in rows
        ]

    def _upsert_named_asset(self, table: str, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized, _ = self._require_agent_row(agent_id)
        scope = _normalize_scope(str(payload.get("scope") or "agent"))
        target_agent_id = None if scope == "global" else normalized
        scope_id = _scope_id(target_agent_id)
        asset_id = int(payload.get("id") or 0)
        existing_row = None
        if asset_id:
            _, existing_row = self._resolve_named_asset_row(table, normalized, asset_id)
            if "scope" not in payload:
                scope = "global" if str(existing_row["scope_id"]) == "global" else "agent"
                target_agent_id = None if scope == "global" else normalized
                scope_id = _scope_id(target_agent_id)
        name = str(payload.get("name") or (existing_row["name"] if existing_row is not None else "")).strip()
        if not name:
            raise ValueError("name is required")
        content = str(payload.get("content") or (existing_row["content"] if existing_row is not None else ""))
        now = now_iso()
        if existing_row is not None:
            execute(
                f"""
                UPDATE {table}
                SET scope_id = ?, agent_id = ?, name = ?, content = ?, updated_at = ?
                WHERE id = ?
                """,
                (scope_id, target_agent_id, name, content, now, asset_id),
            )
            row = fetch_one(f"SELECT * FROM {table} WHERE id = ?", (asset_id,))
        else:
            execute(
                f"""
                INSERT INTO {table} (scope_id, agent_id, name, content, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope_id, name) DO UPDATE SET content = excluded.content, updated_at = excluded.updated_at
                """,
                (scope_id, target_agent_id, name, content, now, now),
            )
            row = fetch_one(f"SELECT * FROM {table} WHERE scope_id = ? AND name = ?", (scope_id, name))
        if row is None:
            raise RuntimeError(f"failed to persist asset {name}")
        return {
            "id": int(row["id"]),
            "scope": scope,
            "name": str(row["name"]),
            "content": str(row["content"]),
            "updated_at": str(row["updated_at"]),
        }

    def _persist_global_default_version(self, sections: dict[str, Any]) -> int:
        return execute(
            "INSERT INTO cp_global_default_versions (snapshot_json, created_at) VALUES (?, ?)",
            (json_dump({"sections": sections}), now_iso()),
        )

    def _invalidate_global_sections_cache(self) -> None:
        self._global_sections_cache = None

    def _load_global_sections(self) -> dict[str, dict[str, Any]]:
        now = time.monotonic()
        cached = getattr(self, "_global_sections_cache", None)
        if cached is not None and (now - cached[0]) < 2.0:
            return copy.deepcopy(cached[1])
        rows = fetch_all("SELECT section, data_json, updated_at FROM cp_global_sections ORDER BY section ASC")
        sections = {str(row["section"]): json_load(row["data_json"], {}) for row in rows}
        self._global_sections_cache = (now, copy.deepcopy(sections))
        return copy.deepcopy(sections)

    def _resolved_shared_env_values(
        self,
        resource_access_policy: dict[str, Any],
        access_section: dict[str, Any],
    ) -> dict[str, str]:
        allowed_keys = normalize_string_list(resource_access_policy.get("allowed_shared_env_keys"))
        shared_env = _safe_json_object(access_section.get("shared_env"))
        if not allowed_keys:
            return {}
        resolved: dict[str, str] = {}
        for key in allowed_keys:
            if _shared_env_key_is_reserved(key):
                continue
            value = shared_env.get(key)
            if value in (None, ""):
                continue
            resolved[key] = str(value)
        return resolved

    def _resolved_secret_values(
        self,
        agent_id: str,
        *,
        resource_access_policy: dict[str, Any] | None = None,
        explicit_policy: bool = False,
    ) -> dict[str, dict[str, Any]]:
        normalized = _normalize_agent_id(agent_id)
        access_policy = _safe_json_object(resource_access_policy)
        allowed_global_secret_keys = set(normalize_string_list(access_policy.get("allowed_global_secret_keys")))
        rows = fetch_all(
            """
            SELECT * FROM cp_secret_values
            WHERE scope_id IN ('global', ?)
            ORDER BY CASE scope_id WHEN 'global' THEN 0 ELSE 1 END, secret_key ASC
            """,
            (normalized,),
        )
        resolved: dict[str, dict[str, Any]] = {}
        sections = self._system_settings_sections()
        for row in rows:
            scope = "global" if str(row["scope_id"]) == "global" else "agent"
            secret_key = str(row["secret_key"])
            if scope == "global":
                if self._global_secret_usage_scope(secret_key, sections=sections) != "agent_grant":
                    continue
                if secret_key not in allowed_global_secret_keys:
                    continue
            resolved[secret_key] = {
                "scope": scope,
                "encrypted_value": str(row["encrypted_value"]),
                "preview": str(row["preview"]),
            }
        return resolved

    def _redact_snapshot_for_client(self, snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
        if snapshot is None:
            return None
        sanitized = dict(snapshot)
        secrets = {}
        for secret_key, payload in _safe_json_object(snapshot.get("secrets")).items():
            secret_payload = _safe_json_object(payload)
            secrets[str(secret_key)] = {
                "scope": str(secret_payload.get("scope") or "agent"),
                "preview": str(secret_payload.get("preview") or ""),
                "present": True,
            }
        sanitized["secrets"] = secrets
        return sanitized

    def _runtime_connection_refs(self, agent_id: str) -> list[dict[str, Any]]:
        normalized, _ = self._require_agent_row(agent_id)
        refs: list[dict[str, Any]] = []
        for connection in self.list_agent_connections(normalized).get("items", []):
            item = _safe_json_object(connection)
            refs.append(
                {
                    "connection_key": str(item.get("connection_key") or ""),
                    "kind": str(item.get("kind") or ""),
                    "integration_key": str(item.get("integration_key") or ""),
                    "status": str(item.get("status") or ""),
                    "transport_kind": str(item.get("transport_kind") or ""),
                    "auth_method": str(item.get("auth_method") or ""),
                    "source_origin": str(item.get("source_origin") or ""),
                    "connected": bool(item.get("connected")),
                    "enabled": bool(item.get("enabled", item.get("connected"))),
                    "account_label": _nonempty_text(item.get("account_label")) or None,
                    "provider_account_id": _nonempty_text(item.get("provider_account_id")) or None,
                    "expires_at": _nonempty_text(item.get("expires_at")) or None,
                    "last_verified_at": _nonempty_text(item.get("last_verified_at")) or None,
                    "last_error": _nonempty_text(item.get("last_error")) or None,
                }
            )
        return refs

    def _snapshot_version(self, agent_id: str, snapshot: dict[str, Any]) -> int:
        normalized = _normalize_agent_id(agent_id)
        row = fetch_one(
            "SELECT version FROM cp_agent_config_versions WHERE agent_id = ? ORDER BY version DESC LIMIT 1",
            (normalized,),
        )
        return int(row["version"] or 1) if row else 1

    def _scoped_env(self, agent_id: str, env: dict[str, str]) -> dict[str, str]:
        scoped: dict[str, str] = {}
        for key, value in env.items():
            normalized_key = key.strip().upper()
            scoped[normalized_key] = value
            scoped[f"{agent_id}_{normalized_key}"] = value
        return scoped

    def _load_legacy_env(self) -> dict[str, str]:
        env_path = ROOT_DIR / ".env"
        if not env_path.exists():
            return {}
        values: dict[str, str] = {}
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
        return values

    def _discover_legacy_agent_ids(self, env_values: dict[str, str]) -> list[str]:
        discovered: set[str] = set()
        for key in env_values:
            match = _TELEGRAM_AGENT_TOKEN_RE.match(key)
            if match:
                legacy_id = _normalize_agent_id(match.group(1))
                discovered.add(legacy_id)
        if not discovered and os.environ.get("AGENT_ID"):
            discovered.add(_normalize_agent_id(os.environ["AGENT_ID"]))
        return sorted(discovered)

    def _assign_env_value(
        self,
        sections: dict[str, dict[str, Any]],
        secrets: dict[str, str],
        key: str,
        value: str,
    ) -> None:
        target = self._infer_section_from_env_key(key)
        if looks_like_secret_key(key):
            secrets[key] = value
            return
        section_payload = sections[target]
        env_map = _safe_json_object(section_payload.get("env"))
        env_map[key] = value
        section_payload["env"] = env_map

    def _infer_section_from_env_key(self, key: str) -> str:
        if key.startswith("MEMORY_"):
            return "memory"
        if key.startswith("KNOWLEDGE_"):
            return "knowledge"
        if key.startswith("SCHEDULER_") or key.startswith("RUNBOOK_"):
            return "scheduler"
        if key.startswith("RUNTIME_") or key.startswith("MAX_CONCURRENT_") or key.startswith("TASK_"):
            return "runtime"
        if (
            key.startswith("CLAUDE_")
            or key.startswith("CODEX_")
            or key.startswith("GEMINI_")
            or key.startswith("OPENAI_")
            or key.startswith("ANTHROPIC_")
            or key.startswith("OPENROUTER_")
            or key.startswith("PROVIDER_")
            or key
            in {
                "DEFAULT_PROVIDER",
                "DEFAULT_MODEL",
                "GOOGLE_CLOUD_PROJECT",
                "MODEL_PRICING_USD",
                "TRANSCRIPT_REPLAY_LIMIT",
            }
        ):
            return "providers"
        if key.startswith("OWNER_"):
            return "identity"
        if (
            key.startswith("SHELL_")
            or key.startswith("BLOCKED_")
            or key.startswith("ALLOWED_")
            or key
            in {
                "DEFAULT_AGENT_MODE",
                "MAX_AGENT_TOOL_ITERATIONS",
                "AGENT_TOOL_TIMEOUT",
                "BROWSER_TOOL_TIMEOUT",
            }
        ):
            return "tools"
        if (
            key.startswith("POSTGRES_")
            or key.startswith("DOCKER_")
            or key.startswith("WHISPER_")
            or key.startswith("TTS_")
            or key.startswith("ELEVENLABS_")
            or key.startswith("ARTIFACT_")
            or key.startswith("LINK_ANALYSIS_")
            or key.startswith("BROWSER_")
            or key
            in {
                "AUDIO_PREPROCESS",
            }
        ):
            return "integrations"
        if key in {
            "AGENT_NAME",
            "AGENT_TOKEN",
            "DEFAULT_WORK_DIR",
            "PROJECT_DIRS",
            "HEALTH_PORT",
            "ALLOWED_USER_IDS",
            "KNOWLEDGE_ADMIN_USER_IDS",
            "MAX_BUDGET_USD",
            "MAX_TOTAL_BUDGET_USD",
            "MAX_TURNS",
            "RATE_LIMIT_PER_MINUTE",
        }:
            return "general"
        return "general"

    def _import_legacy_templates(self, agent_ids: list[str]) -> None:
        global_templates = ROOT_DIR / "templates.json"
        if global_templates.exists() and agent_ids:
            data = json.loads(global_templates.read_text(encoding="utf-8"))
            for name, content in data.items():
                self.upsert_template_asset(agent_ids[0], {"scope": "global", "name": name, "content": content})
        for agent_id in agent_ids:
            path = ROOT_DIR / f"templates_{_slug(agent_id)}.json"
            if not path.exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            for name, content in data.items():
                self.upsert_template_asset(agent_id, {"name": name, "content": content})

    # ------------------------------------------------------------------ #
    #  MCP Server Catalog                                                  #
    # ------------------------------------------------------------------ #

    def list_mcp_catalog(self) -> list[dict[str, Any]]:
        self.ensure_seeded()
        rows = fetch_all("SELECT * FROM cp_mcp_server_catalog ORDER BY display_name")
        return [
            self._serialize_mcp_catalog_row(row) for row in rows if not _is_reserved_mcp_server_key(row["server_key"])
        ]

    def get_mcp_catalog_entry(self, server_key: str) -> dict[str, Any]:
        self.ensure_seeded()
        if _is_reserved_mcp_server_key(server_key):
            raise KeyError(f"MCP server not found: {server_key}")
        row = fetch_one("SELECT * FROM cp_mcp_server_catalog WHERE server_key = ?", (server_key,))
        if row is None:
            raise KeyError(f"MCP server not found: {server_key}")
        return self._serialize_mcp_catalog_row(row)

    def upsert_mcp_catalog_entry(self, server_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_seeded()
        normalized_server_key = _normalize_mcp_server_key(server_key)
        if not normalized_server_key:
            raise ValueError("MCP server key must not be empty.")
        if _is_reserved_mcp_server_key(normalized_server_key):
            raise ValueError("This MCP server key is reserved because Koda already supports it natively.")
        now = now_iso()
        display_name = str(payload.get("display_name") or normalized_server_key)
        description = str(payload.get("description") or "")
        transport_type = str(payload.get("transport_type") or "stdio")
        transport_kind = str(payload.get("transport_kind") or ("remote" if payload.get("remote_url") else "local"))
        command = payload.get("command") or []
        command_json = json_dump(command)
        url = payload.get("url") or None
        remote_url = payload.get("remote_url") or url
        env_schema = payload.get("env_schema") or []
        env_schema_json = json_dump(env_schema)
        headers_schema = payload.get("headers_schema") or []
        headers_schema_json = json_dump(headers_schema)
        documentation_url = payload.get("documentation_url") or None
        logo_key = payload.get("logo_key") or None
        category = str(payload.get("category") or "general")
        enabled = 1 if payload.get("enabled", True) else 0
        oauth_enabled = 1 if payload.get("oauth_enabled", False) else 0
        auth_strategy = str(payload.get("auth_strategy") or "no_auth")
        official_support_level = str(payload.get("official_support_level") or "community_manual")
        oauth_mode = str(payload.get("oauth_mode") or "none")
        oauth_metadata_url = payload.get("oauth_metadata_url") or None
        tool_discovery_mode = str(payload.get("tool_discovery_mode") or "runtime")
        vendor_notes = str(payload.get("vendor_notes") or "")
        default_policy = str(payload.get("default_policy") or "always_ask")
        metadata_json = json_dump(payload.get("metadata") or {})
        execute(
            """
            INSERT INTO cp_mcp_server_catalog (
                server_key, display_name, description, transport_type, command_json, url,
                env_schema_json, documentation_url, logo_key, category, enabled,
                metadata_json, created_at, updated_at, oauth_enabled, transport_kind,
                auth_strategy, official_support_level, oauth_mode, oauth_metadata_url,
                remote_url, headers_schema_json, tool_discovery_mode, vendor_notes,
                default_policy
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (server_key) DO UPDATE SET
                display_name = excluded.display_name,
                description = excluded.description,
                transport_type = excluded.transport_type,
                command_json = excluded.command_json,
                url = excluded.url,
                env_schema_json = excluded.env_schema_json,
                documentation_url = excluded.documentation_url,
                logo_key = excluded.logo_key,
                category = excluded.category,
                enabled = excluded.enabled,
                metadata_json = excluded.metadata_json,
                oauth_enabled = excluded.oauth_enabled,
                transport_kind = excluded.transport_kind,
                auth_strategy = excluded.auth_strategy,
                official_support_level = excluded.official_support_level,
                oauth_mode = excluded.oauth_mode,
                oauth_metadata_url = excluded.oauth_metadata_url,
                remote_url = excluded.remote_url,
                headers_schema_json = excluded.headers_schema_json,
                tool_discovery_mode = excluded.tool_discovery_mode,
                vendor_notes = excluded.vendor_notes,
                default_policy = excluded.default_policy,
                updated_at = excluded.updated_at
            """,
            (
                normalized_server_key,
                display_name,
                description,
                transport_type,
                command_json,
                url,
                env_schema_json,
                documentation_url,
                logo_key,
                category,
                enabled,
                metadata_json,
                now,
                now,
                oauth_enabled,
                transport_kind,
                auth_strategy,
                official_support_level,
                oauth_mode,
                oauth_metadata_url,
                remote_url,
                headers_schema_json,
                tool_discovery_mode,
                vendor_notes,
                default_policy,
            ),
        )
        return self.get_mcp_catalog_entry(normalized_server_key)

    def delete_mcp_catalog_entry(self, server_key: str) -> dict[str, Any]:
        execute("DELETE FROM cp_mcp_tool_policies WHERE server_key = ?", (server_key,))
        execute("DELETE FROM cp_mcp_discovered_tools WHERE server_key = ?", (server_key,))
        execute("DELETE FROM cp_mcp_agent_connections WHERE server_key = ?", (server_key,))
        count = execute("DELETE FROM cp_mcp_server_catalog WHERE server_key = ?", (server_key,))
        return {"deleted": bool(count)}

    def _serialize_mcp_catalog_row(self, row: Any) -> dict[str, Any]:
        metadata = json_load(str(row.get("metadata_json") or "{}"), {})
        auth_capabilities = _safe_json_object(metadata.get("auth_capabilities"))
        auth_flow_kind = str(auth_capabilities.get("auth_flow_kind") or metadata.get("auth_flow_kind") or "")
        if not auth_flow_kind:
            oauth_enabled = bool(int(row.get("oauth_enabled") or 0))
            oauth_mode = str(row.get("oauth_mode") or "none")
            transport_kind = str(row.get("transport_kind") or "local")
            auth_strategy = str(row.get("auth_strategy") or "no_auth")
            if oauth_enabled and transport_kind == "remote" and oauth_mode == "dcr":
                auth_flow_kind = "mcp_remote_oauth_dcr"
            elif oauth_enabled and transport_kind == "remote" and oauth_mode == "confidential":
                auth_flow_kind = "mcp_remote_oauth_confidential"
            elif "oauth" in auth_strategy and transport_kind == "local":
                auth_flow_kind = "provider_native_oauth"
            elif auth_strategy in {"api_key", "api_token"}:
                auth_flow_kind = "api_key"
            elif auth_strategy == "local_session":
                auth_flow_kind = "local_session"
            elif auth_strategy in {"manual_header", "header"}:
                auth_flow_kind = "manual_header"
            else:
                auth_flow_kind = "none"
        oauth_available = auth_flow_kind in {"mcp_remote_oauth_dcr", "mcp_remote_oauth_confidential"}
        oauth_availability = str(
            auth_capabilities.get("oauth_availability") or ("available" if oauth_available else "not_available")
        )
        return {
            "server_key": str(row["server_key"]),
            "display_name": str(row.get("display_name") or ""),
            "description": str(row.get("description") or ""),
            "transport_type": str(row.get("transport_type") or "stdio"),
            "transport_kind": str(row.get("transport_kind") or "local"),
            "command": json_load(str(row.get("command_json") or "[]"), []),
            "url": row.get("url") or None,
            "remote_url": row.get("remote_url") or row.get("url") or None,
            "env_schema": json_load(str(row.get("env_schema_json") or "[]"), []),
            "headers_schema": json_load(str(row.get("headers_schema_json") or "[]"), []),
            "documentation_url": row.get("documentation_url") or None,
            "logo_key": row.get("logo_key") or None,
            "category": str(row.get("category") or "general"),
            "enabled": bool(int(row["enabled"])) if row.get("enabled") is not None else True,
            "oauth_enabled": bool(int(row.get("oauth_enabled") or 0)),
            "auth_strategy": str(row.get("auth_strategy") or "no_auth"),
            "official_support_level": str(row.get("official_support_level") or "community_manual"),
            "oauth_mode": str(row.get("oauth_mode") or "none"),
            "oauth_metadata_url": row.get("oauth_metadata_url") or None,
            "tool_discovery_mode": str(row.get("tool_discovery_mode") or "runtime"),
            "vendor_notes": str(row.get("vendor_notes") or ""),
            "default_policy": str(row.get("default_policy") or "always_ask"),
            "metadata": metadata,
            "auth_capabilities": auth_capabilities,
            "auth_flow_kind": auth_flow_kind,
            "oauth_availability": oauth_availability,
            "created_at": str(row.get("created_at") or ""),
            "updated_at": str(row.get("updated_at") or ""),
        }

    def _serialize_unified_mcp_catalog_entry(self, row: dict[str, Any]) -> dict[str, Any]:
        # Merge runtime catalog spec when available so the API exposes the
        # same surface the TS frontend used to ship as a literal: connection
        # profile, curated tool hints, runtime constraints, command template
        # and oauth-supported flag. Runtime spec is the source of truth for
        # those fields; persisted DB row remains authoritative for the rest.
        server_key = str(row.get("server_key") or "")
        spec: Any = None
        try:
            from koda.integrations.mcp_catalog import MCP_CATALOG_BY_KEY

            spec = MCP_CATALOG_BY_KEY.get(server_key)
        except ImportError:
            spec = None

        metadata = _safe_json_object(row.get("metadata"))
        tagline = str(metadata.get("tagline") or (spec.tagline if spec is not None else ""))
        auth_capabilities = _safe_json_object(row.get("auth_capabilities"))
        auth_flow_kind = str(row.get("auth_flow_kind") or auth_capabilities.get("auth_flow_kind") or "")
        if not auth_flow_kind:
            oauth_mode_value = str(row.get("oauth_mode") or "none")
            transport_kind_value = str(row.get("transport_kind") or "local")
            strategy_value = str(row.get("auth_strategy") or "no_auth")
            if (
                bool(auth_capabilities.get("oauth_enabled"))
                and transport_kind_value == "remote"
                and oauth_mode_value == "dcr"
            ):
                auth_flow_kind = "mcp_remote_oauth_dcr"
            elif (
                bool(auth_capabilities.get("oauth_enabled"))
                and transport_kind_value == "remote"
                and oauth_mode_value == "confidential"
            ):
                auth_flow_kind = "mcp_remote_oauth_confidential"
            elif "oauth" in strategy_value and transport_kind_value == "local":
                auth_flow_kind = "provider_native_oauth"
            elif strategy_value in {"api_key", "api_token"}:
                auth_flow_kind = "api_key"
            elif strategy_value == "local_session":
                auth_flow_kind = "local_session"
            elif strategy_value in {"manual_header", "header"}:
                auth_flow_kind = "manual_header"
            else:
                auth_flow_kind = "none"
        oauth_supported = bool(auth_capabilities.get("oauth_enabled")) and auth_flow_kind in {
            "mcp_remote_oauth_dcr",
            "mcp_remote_oauth_confidential",
        }
        oauth_availability = str(
            row.get("oauth_availability")
            or auth_capabilities.get("oauth_availability")
            or ("available" if oauth_supported else "not_available")
        )

        expected_tools: list[dict[str, Any]] = []
        if spec is not None:
            # McpTool stores a `classification` enum string; the public hint
            # shape expects boolean flags. Map read→read_only_hint,
            # destructive→destructive_hint; write tools land as neither
            # (interactive).
            for tool in spec.tools:
                read_only_hint = tool.classification == "read"
                destructive_hint = tool.classification == "destructive"
                expected_tools.append(
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "read_only_hint": read_only_hint or None,
                        "destructive_hint": destructive_hint or None,
                    }
                )

        connection_profile = serialize_connection_profile(spec.connection_profile) if spec is not None else None
        runtime_constraints = list(spec.runtime_constraints) if spec is not None else []
        command_template = list(spec.command_template) if spec is not None else []
        transport_type = str(row.get("transport_type") or (spec.transport_type if spec is not None else "stdio"))

        # i18n keys — frontend looks them up with t(key, { defaultValue: literal }).
        # Convention: mcp.<server_key>.<field>. If the bundle has no entry the
        # literal still renders, so this is a zero-impact additive change.
        i18n_keys = {
            "display_name": f"mcp.{server_key}.display_name" if server_key else None,
            "tagline": f"mcp.{server_key}.tagline" if server_key else None,
            "description": f"mcp.{server_key}.description" if server_key else None,
            "vendor_notes": f"mcp.{server_key}.vendor_notes" if server_key else None,
        }

        return {
            "connection_key": _mcp_connection_key(server_key),
            "kind": "mcp",
            "integration_key": server_key,
            "display_name": str(row.get("display_name") or server_key),
            "description": str(row.get("description") or ""),
            "tagline": tagline,
            "category": str(row.get("category") or "general"),
            "transport_kind": str(row.get("transport_kind") or "local"),
            "transport_type": transport_type,
            "command_template": command_template,
            "auth_capabilities": auth_capabilities,
            "auth_strategy_default": str(row.get("auth_strategy") or "no_auth"),
            "official_support_level": str(row.get("official_support_level") or "community_manual"),
            "oauth_mode": str(row.get("oauth_mode") or "none"),
            "oauth_supported": oauth_supported,
            "auth_flow_kind": auth_flow_kind,
            "oauth_availability": oauth_availability,
            "remote_url": row.get("remote_url") or row.get("url") or None,
            "vendor_notes": str(row.get("vendor_notes") or ""),
            "default_policy": str(row.get("default_policy") or "always_ask"),
            "env_schema": row.get("env_schema") or [],
            "headers_schema": row.get("headers_schema") or [],
            "documentation_url": row.get("documentation_url") or None,
            "logo_key": row.get("logo_key") or None,
            "metadata": metadata,
            "enabled": bool(row.get("enabled", True)),
            "connection_profile": connection_profile,
            "runtime_constraints": runtime_constraints,
            "expected_tools": expected_tools,
            "i18n_keys": i18n_keys,
        }

    # ------------------------------------------------------------------ #
    #  MCP Agent Connections                                               #
    # ------------------------------------------------------------------ #

    def list_mcp_agent_connections(self, agent_id: str) -> list[dict[str, Any]]:
        self.ensure_seeded()
        normalized = _normalize_agent_id(agent_id)
        rows = fetch_all(
            "SELECT * FROM cp_mcp_agent_connections WHERE agent_id = ? ORDER BY server_key",
            (normalized,),
        )
        return [
            self._serialize_mcp_connection_row(row)
            for row in rows
            if not _is_reserved_mcp_server_key(row["server_key"])
        ]

    def get_mcp_agent_connection(self, agent_id: str, server_key: str) -> dict[str, Any]:
        self.ensure_seeded()
        if _is_reserved_mcp_server_key(server_key):
            raise KeyError(f"MCP connection not found: {agent_id}/{server_key}")
        normalized = _normalize_agent_id(agent_id)
        row = fetch_one(
            "SELECT * FROM cp_mcp_agent_connections WHERE agent_id = ? AND server_key = ?",
            (normalized, server_key),
        )
        if row is None:
            raise KeyError(f"MCP connection not found: {normalized}/{server_key}")
        return self._serialize_mcp_connection_row(row)

    def upsert_mcp_agent_connection(self, agent_id: str, server_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_seeded()
        normalized_server_key = _normalize_mcp_server_key(server_key)
        if _is_reserved_mcp_server_key(normalized_server_key):
            raise ValueError("This MCP server key is reserved because Koda already supports it natively.")
        # Verify server exists in catalog
        catalog_row = fetch_one("SELECT * FROM cp_mcp_server_catalog WHERE server_key = ?", (normalized_server_key,))
        if catalog_row is None:
            raise KeyError(f"unknown MCP server: {normalized_server_key}")
        normalized = _normalize_agent_id(agent_id)
        now = now_iso()
        existing_row = fetch_one(
            "SELECT * FROM cp_mcp_agent_connections WHERE agent_id = ? AND server_key = ?",
            (normalized, normalized_server_key),
        )
        enabled = 1 if payload.get("enabled", True) else 0
        transport_override = (
            payload["transport_override"]
            if "transport_override" in payload
            else (existing_row.get("transport_override") if existing_row else None)
        ) or None
        command_override_json: str | None
        if "command_override" in payload:
            command_override_json = json_dump(
                _validate_mcp_connection_command_override(payload.get("command_override"))
            )
        else:
            command_override_json = existing_row.get("command_override_json") if existing_row else None
        if "url_override" in payload:
            url_override = _validate_mcp_connection_url_override(payload.get("url_override")) or None
        else:
            url_override = (existing_row.get("url_override") if existing_row else None) or None
        raw_env = _validate_mcp_connection_env_values(payload.get("env_values") or {})
        encrypted_env = json_load(str(existing_row.get("env_values_json") or "{}"), {}) if existing_row else {}
        clear_env_keys = {str(item).strip() for item in payload.get("clear_env_keys") or [] if str(item).strip()}
        for clear_key in clear_env_keys:
            encrypted_env.pop(clear_key, None)
        for key, value in raw_env.items():
            normalized_key = str(key).strip()
            if normalized_key and value not in (None, ""):
                encrypted_env[normalized_key] = encrypt_secret(str(value))
        env_values_json = json_dump(encrypted_env)
        existing_metadata = json_load(str(existing_row.get("metadata_json") or "{}"), {}) if existing_row else {}
        merged_metadata = {**existing_metadata, **_safe_json_object(payload.get("metadata"))}
        metadata_json = json_dump(merged_metadata)
        auth_method = str(payload.get("auth_method") or "").strip() or (
            str(existing_row.get("auth_method") or "manual") if existing_row else "manual"
        )
        execute(
            """
            INSERT INTO cp_mcp_agent_connections (
                agent_id, server_key, enabled, transport_override, command_override_json,
                url_override, env_values_json, metadata_json, created_at, updated_at, auth_method
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (agent_id, server_key) DO UPDATE SET
                enabled = excluded.enabled,
                transport_override = excluded.transport_override,
                command_override_json = excluded.command_override_json,
                url_override = excluded.url_override,
                env_values_json = excluded.env_values_json,
                metadata_json = excluded.metadata_json,
                auth_method = excluded.auth_method,
                updated_at = excluded.updated_at
            """,
            (
                normalized,
                normalized_server_key,
                enabled,
                transport_override,
                command_override_json,
                url_override,
                env_values_json,
                metadata_json,
                now,
                now,
                auth_method,
            ),
        )
        return self.get_mcp_agent_connection(agent_id, normalized_server_key)

    def delete_mcp_agent_connection(self, agent_id: str, server_key: str) -> dict[str, Any]:
        normalized = _normalize_agent_id(agent_id)
        execute(
            "DELETE FROM cp_mcp_tool_policies WHERE agent_id = ? AND server_key = ?",
            (normalized, server_key),
        )
        execute(
            "DELETE FROM cp_mcp_discovered_tools WHERE agent_id = ? AND server_key = ?",
            (normalized, server_key),
        )
        count = execute(
            "DELETE FROM cp_mcp_agent_connections WHERE agent_id = ? AND server_key = ?",
            (normalized, server_key),
        )
        self.delete_oauth_tokens(normalized, server_key)
        return {"deleted": bool(count)}

    def _serialize_mcp_connection_row(self, row: Any) -> dict[str, Any]:
        env_values_json = str(row.get("env_values_json") or "{}")
        try:
            encrypted = json_load(env_values_json, {})
            masked = {k: mask_secret(v) if v else "" for k, v in encrypted.items()}
        except Exception:
            masked = {}
        server_key = str(row["server_key"])
        catalog_row = fetch_one("SELECT * FROM cp_mcp_server_catalog WHERE server_key = ?", (server_key,))
        catalog = self._serialize_mcp_catalog_row(catalog_row) if catalog_row is not None else {}
        oauth_status = self.get_oauth_token_status(str(row["agent_id"]), server_key)
        tool_count = len(json_load(str(row.get("cached_tools_json") or "[]"), []))
        enabled = bool(int(row["enabled"])) if row.get("enabled") is not None else True
        status = "verified"
        if not enabled:
            status = "disabled"
        elif _nonempty_text(row.get("last_error")):
            status = "error"
        elif not row.get("last_connected_at"):
            status = "configured" if oauth_status.get("connected") or masked else "not_configured"
        return {
            "connection_key": _mcp_connection_key(server_key),
            "kind": "mcp",
            "integration_key": server_key,
            "agent_id": str(row["agent_id"]),
            "server_key": server_key,
            "enabled": enabled,
            "transport_override": row.get("transport_override") or None,
            "command_override": json_load(str(row.get("command_override_json") or "null"), None),
            "command_override_json": row.get("command_override_json") or None,
            "url_override": row.get("url_override") or None,
            "env_values": masked,
            "last_connected_at": row.get("last_connected_at") or None,
            "last_error": row.get("last_error") or None,
            "cached_tools_json": row.get("cached_tools_json") or None,
            "cached_tools_at": row.get("cached_tools_at") or None,
            "auth_method": str(row.get("auth_method") or "manual"),
            "metadata": json_load(str(row.get("metadata_json") or "{}"), {}),
            "tool_count": tool_count,
            "status": status,
            "transport_kind": str(catalog.get("transport_kind") or "local"),
            "auth_strategy": str(catalog.get("auth_strategy") or "no_auth"),
            "official_support_level": str(catalog.get("official_support_level") or "community_manual"),
            "account_label": oauth_status.get("account_label"),
            "provider_account_id": oauth_status.get("provider_account_id"),
            "expires_at": oauth_status.get("expires_at"),
            "last_verified_at": row.get("last_connected_at") or None,
            "connected": enabled,
            "created_at": str(row.get("created_at") or ""),
            "updated_at": str(row.get("updated_at") or ""),
        }

    def _decrypt_mcp_env_values(self, env_values_json: str) -> dict[str, str]:
        return decrypt_env_values(env_values_json)

    def get_mcp_runtime_config(self, agent_id: str) -> list[dict[str, Any]]:
        """Get full MCP config with decrypted credentials for runtime bootstrap."""
        normalized = _normalize_agent_id(agent_id)
        connections = fetch_all(
            "SELECT * FROM cp_mcp_agent_connections WHERE agent_id = ? AND enabled = 1",
            (normalized,),
        )
        result = []
        for row in connections:
            server_key = str(row["server_key"])
            if _is_reserved_mcp_server_key(server_key):
                continue
            catalog_row = fetch_one("SELECT * FROM cp_mcp_server_catalog WHERE server_key = ?", (server_key,))
            resolved = resolve_mcp_runtime_connection(
                normalized,
                server_key,
                connection_row=row,
                catalog_row=catalog_row,
            )
            if resolved:
                result.append(resolved)
        return result

    # ------------------------------------------------------------------ #
    #  MCP Tool Policies                                                   #
    # ------------------------------------------------------------------ #

    def list_mcp_tool_policies(self, agent_id: str, server_key: str) -> list[dict[str, Any]]:
        if _is_reserved_mcp_server_key(server_key):
            return []
        normalized = _normalize_agent_id(agent_id)
        rows = fetch_all(
            "SELECT * FROM cp_mcp_tool_policies WHERE agent_id = ? AND server_key = ? ORDER BY tool_name",
            (normalized, server_key),
        )
        return [self._serialize_mcp_policy_row(row) for row in rows]

    def upsert_mcp_tool_policy(self, agent_id: str, server_key: str, tool_name: str, policy: str) -> dict[str, Any]:
        if _is_reserved_mcp_server_key(server_key):
            raise ValueError("This MCP server key is reserved because Koda already supports it natively.")
        valid_policies = ("auto", "always_allow", "always_ask", "blocked")
        if policy not in valid_policies:
            raise ValueError(f"invalid MCP tool policy: {policy}")
        normalized = _normalize_agent_id(agent_id)
        now = now_iso()
        execute(
            """
            INSERT INTO cp_mcp_tool_policies (agent_id, server_key, tool_name, policy, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (agent_id, server_key, tool_name) DO UPDATE SET
                policy = excluded.policy,
                updated_at = excluded.updated_at
            """,
            (normalized, server_key, tool_name, policy, now),
        )
        row = fetch_one(
            "SELECT * FROM cp_mcp_tool_policies WHERE agent_id = ? AND server_key = ? AND tool_name = ?",
            (normalized, server_key, tool_name),
        )
        return self._serialize_mcp_policy_row(row) if row else {}

    def delete_mcp_tool_policy(self, agent_id: str, server_key: str, tool_name: str) -> dict[str, Any]:
        if _is_reserved_mcp_server_key(server_key):
            return {"deleted": False}
        normalized = _normalize_agent_id(agent_id)
        count = execute(
            "DELETE FROM cp_mcp_tool_policies WHERE agent_id = ? AND server_key = ? AND tool_name = ?",
            (normalized, server_key, tool_name),
        )
        return {"deleted": bool(count)}

    def _serialize_mcp_policy_row(self, row: Any) -> dict[str, Any]:
        return {
            "agent_id": str(row["agent_id"]),
            "server_key": str(row["server_key"]),
            "tool_name": str(row["tool_name"]),
            "policy": str(row.get("policy") or "auto"),
            "updated_at": str(row.get("updated_at") or ""),
        }

    def list_agent_connection_tool_policies(self, agent_id: str, connection_key: str) -> list[dict[str, Any]]:
        kind, value = _parse_connection_key(connection_key)
        if kind == "core":
            return []
        return self.list_mcp_tool_policies(agent_id, value)

    def upsert_agent_connection_tool_policy(
        self,
        agent_id: str,
        connection_key: str,
        tool_name: str,
        policy: str,
    ) -> dict[str, Any]:
        kind, value = _parse_connection_key(connection_key)
        if kind == "core":
            raise ValueError("tool_policies_not_supported_for_core_connections")
        return self.upsert_mcp_tool_policy(agent_id, value, tool_name, policy)

    def delete_agent_connection_tool_policy(self, agent_id: str, connection_key: str, tool_name: str) -> dict[str, Any]:
        kind, value = _parse_connection_key(connection_key)
        if kind == "core":
            return {"deleted": False}
        return self.delete_mcp_tool_policy(agent_id, value, tool_name)

    # ------------------------------------------------------------------ #
    #  MCP Test Connection / Discover Tools                                #
    # ------------------------------------------------------------------ #

    def test_mcp_connection(self, agent_id: str, server_key: str) -> dict[str, Any]:
        """Test an MCP server connection by starting it temporarily."""
        from koda.services.mcp_manager import McpServerInstance

        normalized = _normalize_agent_id(agent_id)
        resolved = self._resolve_mcp_runtime_payload(normalized, server_key)
        if resolved is None:
            return {"success": False, "healthy": False, "error": "connection_not_found", "server_key": server_key}
        instance = McpServerInstance(
            server_key=server_key,
            agent_id=normalized,
            transport_type=str(resolved.get("transport_type") or "stdio"),
            command=resolved.get("command") or None,
            url=resolved.get("url"),
            env=resolved.get("env_values") or None,
            headers=resolved.get("headers") or None,
        )
        try:
            run_coro_sync(instance.start())
            healthy = run_coro_sync(instance.health_check())
            self._record_mcp_runtime_state(
                normalized,
                server_key,
                success=True,
                error="",
                tools=[self._tool_to_payload(tool) for tool in instance.cached_tools],
            )
            return {
                "success": True,
                "healthy": healthy,
                "tool_count": len(instance.cached_tools),
                "server_key": server_key,
            }
        except Exception as exc:
            self._record_mcp_runtime_state(normalized, server_key, success=False, error=str(exc), tools=[])
            return {
                "success": False,
                "healthy": False,
                "error": str(exc),
                "server_key": server_key,
            }
        finally:
            with contextlib.suppress(Exception):
                run_coro_sync(instance.stop())

    def discover_mcp_tools(self, agent_id: str, server_key: str) -> dict[str, Any]:
        """Discover tools from an MCP server and cache them."""
        from koda.services.mcp_manager import McpServerInstance

        normalized = _normalize_agent_id(agent_id)
        before_tools = {
            str(tool.get("name") or ""): str(tool.get("signature_hash") or self._mcp_tool_signature_hash(tool))
            for tool in self._list_active_mcp_discovered_tools(normalized, server_key)
            if str(tool.get("name") or "").strip()
        }
        resolved = self._resolve_mcp_runtime_payload(normalized, server_key)
        if resolved is None:
            return {"success": False, "error": "connection_not_found", "tools": [], "tool_count": 0, "cached_at": None}
        instance = McpServerInstance(
            server_key=server_key,
            agent_id=normalized,
            transport_type=str(resolved.get("transport_type") or "stdio"),
            command=resolved.get("command") or None,
            url=resolved.get("url"),
            env=resolved.get("env_values") or None,
            headers=resolved.get("headers") or None,
        )
        try:
            run_coro_sync(instance.start())
            tools = instance.cached_tools
            tools_data = [self._tool_to_payload(tool) for tool in tools]
            after_tools = {
                str(tool.get("name") or ""): self._mcp_tool_signature_hash(tool)
                for tool in tools_data
                if str(tool.get("name") or "").strip()
            }
            diff = {
                "added": sorted(name for name in after_tools if name not in before_tools),
                "removed": sorted(name for name in before_tools if name not in after_tools),
                "changed": sorted(
                    name
                    for name, signature_hash in after_tools.items()
                    if before_tools.get(name) not in (None, signature_hash)
                ),
            }
            now = self._record_mcp_runtime_state(
                normalized,
                server_key,
                success=True,
                error="",
                tools=tools_data,
            )
            self._reset_changed_tool_policies(normalized, server_key, diff["changed"])
            discovery_run = self._persist_connection_discovery_run(
                normalized,
                _mcp_connection_key(server_key),
                status="succeeded",
                tools=self._list_active_mcp_discovered_tools(normalized, server_key),
                diff=diff,
            )
            tools_payload = self.get_mcp_connection_tools(normalized, server_key)
            return {
                "success": True,
                "tool_count": len(tools_data),
                "tools": tools_payload["tools"],
                "policies": tools_payload["policies"],
                "summary": tools_payload["summary"],
                "cached_at": now,
                "last_discovered_at": discovery_run["discovered_at"],
                "diff": discovery_run["diff"],
            }
        except Exception as exc:
            self._record_mcp_runtime_state(normalized, server_key, success=False, error=str(exc), tools=[])
            self._persist_connection_discovery_run(
                normalized,
                _mcp_connection_key(server_key),
                status="failed",
                tools=[],
                diff={"added": [], "removed": [], "changed": []},
                error=str(exc),
            )
            return {
                "success": False,
                "error": str(exc),
                "tools": [],
                "tool_count": 0,
                "cached_at": None,
            }
        finally:
            with contextlib.suppress(Exception):
                run_coro_sync(instance.stop())

    def _resolve_mcp_runtime_payload(self, agent_id: str, server_key: str) -> dict[str, Any] | None:
        catalog_row = fetch_one("SELECT * FROM cp_mcp_server_catalog WHERE server_key = ?", (server_key,))
        if catalog_row is None:
            raise KeyError(server_key)
        connection_row = fetch_one(
            "SELECT * FROM cp_mcp_agent_connections WHERE agent_id = ? AND server_key = ?",
            (agent_id, server_key),
        )
        if connection_row is None:
            return None
        return resolve_mcp_runtime_connection(
            agent_id,
            server_key,
            connection_row=connection_row,
            catalog_row=catalog_row,
        )

    def _tool_to_payload(self, tool: Any) -> dict[str, Any]:
        from koda.services.mcp_risk import assess_mcp_tool_risk, evaluate_mcp_risk

        assessment = assess_mcp_tool_risk(tool)
        decision = evaluate_mcp_risk(assessment)
        payload: dict[str, Any] = {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
            "risk_class": assessment.risk_class,
            "approval_default": decision.decision,
            "risk_metadata": assessment.to_payload(),
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

    def _mcp_tool_signature_hash(self, tool: dict[str, Any]) -> str:
        signature = {
            "input_schema": tool.get("input_schema") or {},
            "annotations": _safe_json_object(tool.get("annotations")),
        }
        return hashlib.sha256(json_dump(signature).encode("utf-8")).hexdigest()

    def _serialize_mcp_discovered_tool_row(self, row: Any) -> dict[str, Any]:
        annotations = json_load(str(row.get("annotations_json") or "{}"), {})
        tool = {
            "name": str(row.get("tool_name") or ""),
            "description": str(row.get("description") or ""),
            "input_schema": json_load(str(row.get("input_schema_json") or "{}"), {}),
            "annotations": annotations,
            "risk_level": str(row.get("risk_level") or "read"),
            "risk_class": str(row.get("risk_class") or row.get("risk_level") or "unknown"),
            "approval_default": str(row.get("approval_default") or "require_approval"),
            "risk_metadata": json_load(str(row.get("risk_metadata_json") or "{}"), {}),
            "signature_hash": str(row.get("schema_hash") or ""),
            "discovered_at": str(row.get("discovered_at") or ""),
            "updated_at": str(row.get("updated_at") or ""),
        }
        if not annotations:
            tool.pop("annotations", None)
        return tool

    def _list_active_mcp_discovered_tools(self, agent_id: str, server_key: str) -> list[dict[str, Any]]:
        rows = fetch_all(
            """
            SELECT * FROM cp_mcp_discovered_tools
            WHERE agent_id = ? AND server_key = ?
            ORDER BY tool_name
            """,
            (agent_id, server_key),
        )
        return [self._serialize_mcp_discovered_tool_row(row) for row in rows]

    def _build_tool_summary(self, tools: list[dict[str, Any]]) -> dict[str, int]:
        summary = {
            "total": len(tools),
            "read_only": 0,
            "write": 0,
            "destructive": 0,
            "unknown": 0,
            "high_risk": 0,
        }
        for tool in tools:
            risk_class = str(tool.get("risk_class") or tool.get("risk_level") or "unknown")
            if risk_class == "read_context":
                summary["read_only"] += 1
            elif risk_class == "destructive_write":
                summary["destructive"] += 1
                summary["high_risk"] += 1
                summary["write"] += 1
            elif risk_class in {"network_write", "secret_access", "code_execution"}:
                summary["high_risk"] += 1
                summary["write"] += 1
            elif risk_class == "unknown":
                summary["unknown"] += 1
                summary["high_risk"] += 1
                summary["write"] += 1
            else:
                summary["write"] += 1
        return summary

    def _reset_changed_tool_policies(self, agent_id: str, server_key: str, tool_names: list[str]) -> None:
        if not tool_names:
            return
        now = now_iso()
        for tool_name in tool_names:
            execute(
                """
                INSERT INTO cp_mcp_tool_policies (agent_id, server_key, tool_name, policy, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (agent_id, server_key, tool_name) DO UPDATE SET
                    policy = excluded.policy,
                    updated_at = excluded.updated_at
                """,
                (agent_id, server_key, tool_name, "always_ask", now),
            )

    def _persist_connection_discovery_run(
        self,
        agent_id: str,
        connection_key: str,
        *,
        status: str,
        tools: list[dict[str, Any]],
        diff: dict[str, list[str]] | None = None,
        error: str = "",
    ) -> dict[str, Any]:
        run_id = str(uuid4())
        now = now_iso()
        diff_payload = {
            "added": sorted(diff.get("added") or []) if isinstance(diff, dict) else [],
            "removed": sorted(diff.get("removed") or []) if isinstance(diff, dict) else [],
            "changed": sorted(diff.get("changed") or []) if isinstance(diff, dict) else [],
        }
        execute(
            """
            INSERT INTO cp_connection_discovery_runs (
                run_id, agent_id, connection_key, status, tool_count, diff_json,
                error, discovered_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                agent_id,
                connection_key,
                status,
                len(tools),
                json_dump(diff_payload),
                error,
                now,
                now,
                now,
            ),
        )
        for tool in tools:
            annotations = _safe_json_object(tool.get("annotations"))
            risk_class = str(tool.get("risk_class") or "unknown")
            execute(
                """
                INSERT INTO cp_connection_discovery_run_tools (
                    run_id, tool_name, description, input_schema_json, annotations_json,
                    risk_level, signature_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    str(tool.get("name") or ""),
                    str(tool.get("description") or ""),
                    json_dump(tool.get("input_schema") or {}),
                    json_dump(annotations),
                    risk_class if risk_class != "read_context" else "read",
                    str(tool.get("signature_hash") or self._mcp_tool_signature_hash(tool)),
                    now,
                ),
            )
        return {
            "run_id": run_id,
            "status": status,
            "diff": diff_payload,
            "tool_count": len(tools),
            "discovered_at": now,
            "error": error or None,
        }

    def _latest_connection_discovery_run(self, agent_id: str, connection_key: str) -> dict[str, Any] | None:
        row = fetch_one(
            """
            SELECT * FROM cp_connection_discovery_runs
            WHERE agent_id = ? AND connection_key = ?
            ORDER BY discovered_at DESC, created_at DESC
            """,
            (agent_id, connection_key),
        )
        if row is None:
            return None
        return {
            "run_id": str(row.get("run_id") or ""),
            "status": str(row.get("status") or "unknown"),
            "tool_count": int(row.get("tool_count") or 0),
            "diff": json_load(str(row.get("diff_json") or "{}"), {}),
            "error": _nonempty_text(row.get("error")) or None,
            "discovered_at": _nonempty_text(row.get("discovered_at")) or None,
        }

    def get_mcp_connection_tools(self, agent_id: str, server_key: str) -> dict[str, Any]:
        normalized = _normalize_agent_id(agent_id)
        active_tools = self._list_active_mcp_discovered_tools(normalized, server_key)
        policies = {
            str(item.get("tool_name") or ""): str(item.get("policy") or "auto")
            for item in self.list_mcp_tool_policies(normalized, server_key)
        }
        latest_run = self._latest_connection_discovery_run(normalized, _mcp_connection_key(server_key))
        last_discovered_at = None
        if active_tools:
            last_discovered_at = max(str(tool.get("discovered_at") or "") for tool in active_tools) or None
        return {
            "connection_key": _mcp_connection_key(server_key),
            "kind": "mcp",
            "integration_key": server_key,
            "tools": active_tools,
            "policies": policies,
            "summary": self._build_tool_summary(active_tools),
            "last_discovered_at": latest_run.get("discovered_at") if latest_run else last_discovered_at,
            "diff": (
                _safe_json_object(latest_run.get("diff")) if latest_run else {"added": [], "removed": [], "changed": []}
            ),
        }

    def get_agent_connection_tools(self, agent_id: str, connection_key: str) -> dict[str, Any]:
        kind, value = _parse_connection_key(connection_key)
        if kind == "core":
            return {
                "connection_key": _core_connection_key(value),
                "kind": "core",
                "integration_key": value,
                "tools": [],
                "policies": {},
                "summary": {"total": 0, "read_only": 0, "write": 0, "destructive": 0},
                "last_discovered_at": None,
                "diff": {"added": [], "removed": [], "changed": []},
            }
        return self.get_mcp_connection_tools(agent_id, value)

    def discover_agent_connection_tools(self, agent_id: str, connection_key: str) -> dict[str, Any]:
        kind, value = _parse_connection_key(connection_key)
        if kind == "core":
            raise ValueError("tool_discovery_not_supported_for_core_connections")
        return self.discover_mcp_tools(agent_id, value)

    def _persist_default_mcp_tool_policies(self, agent_id: str, server_key: str, tools: list[dict[str, Any]]) -> None:
        now = now_iso()
        for tool in tools:
            tool_name = str(tool.get("name") or "").strip()
            if not tool_name:
                continue
            execute(
                """
                INSERT INTO cp_mcp_tool_policies (agent_id, server_key, tool_name, policy, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (agent_id, server_key, tool_name) DO NOTHING
                """,
                (agent_id, server_key, tool_name, "always_ask", now),
            )

    def _persist_mcp_discovered_tools(
        self,
        agent_id: str,
        server_key: str,
        tools: list[dict[str, Any]],
        discovered_at: str,
    ) -> None:
        execute(
            "DELETE FROM cp_mcp_discovered_tools WHERE agent_id = ? AND server_key = ?",
            (agent_id, server_key),
        )
        for tool in tools:
            annotations = _safe_json_object(tool.get("annotations"))
            from koda.services.mcp_risk import assess_mcp_tool_risk, evaluate_mcp_risk

            assessment = assess_mcp_tool_risk(tool)
            decision = evaluate_mcp_risk(assessment)
            risk_class = str(tool.get("risk_class") or assessment.risk_class)
            approval_default = str(tool.get("approval_default") or decision.decision)
            risk_metadata = _safe_json_object(tool.get("risk_metadata") or assessment.to_payload())
            risk_level = "read" if risk_class == "read_context" else "write"
            if risk_class == "destructive_write":
                risk_level = "destructive"
            schema_json = json_dump(tool.get("input_schema") or {})
            signature_hash = self._mcp_tool_signature_hash(tool)
            execute(
                """
                INSERT INTO cp_mcp_discovered_tools (
                    agent_id, server_key, tool_name, description, input_schema_json,
                    annotations_json, risk_level, schema_hash, discovered_at, updated_at,
                    risk_class, approval_default, risk_metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?::jsonb)
                """,
                (
                    agent_id,
                    server_key,
                    str(tool.get("name") or ""),
                    str(tool.get("description") or ""),
                    schema_json,
                    json_dump(annotations),
                    risk_level,
                    signature_hash,
                    discovered_at,
                    discovered_at,
                    risk_class,
                    approval_default,
                    json_dump(risk_metadata),
                ),
            )

    def _record_mcp_runtime_state(
        self,
        agent_id: str,
        server_key: str,
        *,
        success: bool,
        error: str,
        tools: list[dict[str, Any]],
    ) -> str:
        now = now_iso()
        current = fetch_one(
            "SELECT last_connected_at FROM cp_mcp_agent_connections WHERE agent_id = ? AND server_key = ?",
            (agent_id, server_key),
        )
        last_connected_at = now if success else (str(current.get("last_connected_at") or "") if current else "")
        execute(
            """
            UPDATE cp_mcp_agent_connections
            SET last_connected_at = ?, last_error = ?, cached_tools_json = ?, cached_tools_at = ?, updated_at = ?
            WHERE agent_id = ? AND server_key = ?
            """,
            (
                last_connected_at,
                error,
                json_dump(tools),
                now if tools else None,
                now,
                agent_id,
                server_key,
            ),
        )
        self._persist_mcp_discovered_tools(agent_id, server_key, tools, now)
        self._persist_default_mcp_tool_policies(agent_id, server_key, tools)
        return now

    # ------------------------------------------------------------------ #
    #  MCP OAuth Token Management                                          #
    # ------------------------------------------------------------------ #

    def get_oauth_token_status(self, agent_id: str, server_key: str) -> dict[str, Any]:
        """Return OAuth token metadata for an agent+server pair.

        Never exposes raw tokens -- only connection status, expiry, account
        label, and last error.
        """
        normalized = _normalize_agent_id(agent_id)
        token_row = fetch_one(
            "SELECT * FROM cp_mcp_oauth_tokens WHERE agent_id = ? AND server_key = ?",
            (normalized, server_key),
        )
        if token_row is None:
            conn_row = fetch_one(
                "SELECT auth_method FROM cp_mcp_agent_connections WHERE agent_id = ? AND server_key = ?",
                (normalized, server_key),
            )
            return {
                "connected": False,
                "expires_at": None,
                "provider_account_id": None,
                "account_label": None,
                "last_error": None,
                "auth_method": str(conn_row["auth_method"]) if conn_row and conn_row.get("auth_method") else "manual",
            }
        return {
            "connected": True,
            "expires_at": str(token_row.get("expires_at") or "") or None,
            "provider_account_id": str(token_row.get("provider_account_id") or "") or None,
            "account_label": str(token_row.get("provider_account_label") or "") or None,
            "last_error": str(token_row.get("last_error") or "") or None,
            "auth_method": "oauth",
        }

    def delete_oauth_tokens(self, agent_id: str, server_key: str) -> dict[str, Any]:
        """Delete stored OAuth tokens for an agent+server pair."""
        normalized = _normalize_agent_id(agent_id)
        count = execute(
            "DELETE FROM cp_mcp_oauth_tokens WHERE agent_id = ? AND server_key = ?",
            (normalized, server_key),
        )
        return {"deleted": bool(count)}

    def list_oauth_enabled_servers(self) -> list[str]:
        """Return server keys that have OAuth enabled in the catalog."""
        rows = fetch_all("SELECT server_key FROM cp_mcp_server_catalog WHERE oauth_enabled = 1 ORDER BY server_key")
        return [str(row["server_key"]) for row in rows]

    # ------------------------------------------------------------------ #
    #  MCP Capabilities (Tools + Resources + Prompts)                    #
    # ------------------------------------------------------------------ #

    def discover_mcp_capabilities(
        self,
        agent_id: str,
        server_key: str,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """Live discovery of tools + resources + prompts for an MCP server."""
        from koda.services.mcp_capability_service import verify_capabilities

        normalized = _normalize_agent_id(agent_id)
        snapshot = verify_capabilities(normalized, server_key, force_refresh=force_refresh)
        payload = snapshot.to_payload()
        payload["policies"] = self.list_mcp_capability_policies(normalized, server_key)
        return payload

    def get_mcp_capability_snapshot(self, agent_id: str, server_key: str) -> dict[str, Any]:
        """Return cached snapshot for an agent+server pair, or trigger discovery."""
        from koda.services.mcp_capability_service import get_capability_snapshot

        normalized = _normalize_agent_id(agent_id)
        cached = get_capability_snapshot(normalized, server_key)
        if cached is None:
            return self.discover_mcp_capabilities(normalized, server_key, force_refresh=True)
        payload = cached.to_payload()
        payload["policies"] = self.list_mcp_capability_policies(normalized, server_key)
        return payload

    def list_mcp_resources(self, agent_id: str, server_key: str) -> list[dict[str, Any]]:
        normalized = _normalize_agent_id(agent_id)
        rows = fetch_all(
            "SELECT * FROM cp_mcp_discovered_resources WHERE agent_id = ? AND server_key = ? ORDER BY uri",
            (normalized, server_key),
        )
        return [self._serialize_mcp_resource_row(row) for row in rows]

    def list_mcp_prompts(self, agent_id: str, server_key: str) -> list[dict[str, Any]]:
        normalized = _normalize_agent_id(agent_id)
        rows = fetch_all(
            "SELECT * FROM cp_mcp_discovered_prompts WHERE agent_id = ? AND server_key = ? ORDER BY prompt_name",
            (normalized, server_key),
        )
        return [self._serialize_mcp_prompt_row(row) for row in rows]

    def read_mcp_resource(self, agent_id: str, server_key: str, uri: str) -> dict[str, Any]:
        """Live-read a resource via the MCP server. Honors blocked policy."""
        from koda.services.mcp_capability_service import _uri_hash

        normalized = _normalize_agent_id(agent_id)
        policy = self._get_mcp_capability_policy(normalized, server_key, "resource", _uri_hash(uri))
        if policy == "auto":
            policy = self._get_mcp_capability_policy(normalized, server_key, "resource", uri)
        if policy == "blocked":
            return {"success": False, "error": "resource_blocked", "uri": uri}
        from koda.services.mcp_manager import McpServerInstance

        resolved = self._resolve_mcp_runtime_payload(normalized, server_key)
        if resolved is None:
            return {"success": False, "error": "connection_not_found", "uri": uri}
        instance = McpServerInstance(
            server_key=server_key,
            agent_id=normalized,
            transport_type=str(resolved.get("transport_type") or "stdio"),
            command=resolved.get("command") or None,
            url=resolved.get("url"),
            env=resolved.get("env_values") or None,
            headers=resolved.get("headers") or None,
        )
        try:
            run_coro_sync(instance.start())
            session = instance.session
            if session is None:
                raise RuntimeError("session not started")
            content = run_coro_sync(session.read_resource(uri))
            return {"success": True, "uri": uri, "contents": content.contents}
        except Exception as exc:
            return {"success": False, "error": str(exc), "uri": uri}
        finally:
            with contextlib.suppress(Exception):
                run_coro_sync(instance.stop())

    def render_mcp_prompt(
        self,
        agent_id: str,
        server_key: str,
        prompt_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Live-render a prompt template via the MCP server. Honors blocked policy."""
        normalized = _normalize_agent_id(agent_id)
        policy = self._get_mcp_capability_policy(normalized, server_key, "prompt", prompt_name)
        if policy == "blocked":
            return {"success": False, "error": "prompt_blocked", "prompt": prompt_name}
        from koda.services.mcp_manager import McpServerInstance

        resolved = self._resolve_mcp_runtime_payload(normalized, server_key)
        if resolved is None:
            return {"success": False, "error": "connection_not_found", "prompt": prompt_name}
        instance = McpServerInstance(
            server_key=server_key,
            agent_id=normalized,
            transport_type=str(resolved.get("transport_type") or "stdio"),
            command=resolved.get("command") or None,
            url=resolved.get("url"),
            env=resolved.get("env_values") or None,
            headers=resolved.get("headers") or None,
        )
        try:
            run_coro_sync(instance.start())
            session = instance.session
            if session is None:
                raise RuntimeError("session not started")
            result = run_coro_sync(session.get_prompt(prompt_name, arguments))
            return {
                "success": True,
                "prompt": prompt_name,
                "description": result.description,
                "messages": result.messages,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc), "prompt": prompt_name}
        finally:
            with contextlib.suppress(Exception):
                run_coro_sync(instance.stop())

    # ------------------------------------------------------------------ #
    #  MCP Capability Policies (unified tool/resource/prompt)            #
    # ------------------------------------------------------------------ #

    def list_mcp_capability_policies(self, agent_id: str, server_key: str) -> dict[str, list[dict[str, Any]]]:
        """Return policies grouped by capability_kind."""
        if _is_reserved_mcp_server_key(server_key):
            return {"tools": [], "resources": [], "prompts": []}
        normalized = _normalize_agent_id(agent_id)
        rows = fetch_all(
            (
                "SELECT * FROM cp_mcp_capability_policies "
                "WHERE agent_id = ? AND server_key = ? "
                "ORDER BY capability_kind, capability_name"
            ),
            (normalized, server_key),
        )
        grouped: dict[str, list[dict[str, Any]]] = {"tools": [], "resources": [], "prompts": []}
        kind_to_bucket = {"tool": "tools", "resource": "resources", "prompt": "prompts"}
        for row in rows:
            kind = str(row.get("capability_kind") or "")
            bucket = kind_to_bucket.get(kind)
            if bucket is None:
                continue
            grouped[bucket].append(self._serialize_mcp_capability_policy_row(row))
        return grouped

    def upsert_mcp_capability_policy(
        self,
        agent_id: str,
        server_key: str,
        capability_kind: str,
        capability_name: str,
        policy: str,
        *,
        exposure_mode: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if _is_reserved_mcp_server_key(server_key):
            raise ValueError("This MCP server key is reserved because Koda already supports it natively.")
        if capability_kind not in {"tool", "resource", "prompt"}:
            raise ValueError(f"invalid capability_kind: {capability_kind!r}")
        if policy not in {"auto", "always_allow", "always_ask", "blocked"}:
            raise ValueError(f"invalid MCP capability policy: {policy!r}")
        if exposure_mode is not None and exposure_mode not in {"context", "tool", "auto"}:
            raise ValueError(f"invalid exposure_mode: {exposure_mode!r}")
        normalized = _normalize_agent_id(agent_id)
        now = now_iso()
        execute(
            """
            INSERT INTO cp_mcp_capability_policies
                (agent_id, server_key, capability_kind, capability_name,
                 policy, exposure_mode, metadata_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (agent_id, server_key, capability_kind, capability_name) DO UPDATE SET
                policy = EXCLUDED.policy,
                exposure_mode = EXCLUDED.exposure_mode,
                metadata_json = EXCLUDED.metadata_json,
                updated_at = EXCLUDED.updated_at
            """,
            (
                normalized,
                server_key,
                capability_kind,
                capability_name,
                policy,
                exposure_mode,
                json_dump(metadata or {}),
                now,
            ),
        )
        # Mirror tool policies into the legacy table during transition window
        # so dispatcher reads stay consistent until phase 3 wiring lands.
        if capability_kind == "tool":
            execute(
                """
                INSERT INTO cp_mcp_tool_policies (agent_id, server_key, tool_name, policy, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (agent_id, server_key, tool_name) DO UPDATE SET
                    policy = EXCLUDED.policy,
                    updated_at = EXCLUDED.updated_at
                """,
                (normalized, server_key, capability_name, policy, now),
            )
        row = fetch_one(
            """
            SELECT * FROM cp_mcp_capability_policies
            WHERE agent_id = ? AND server_key = ?
              AND capability_kind = ? AND capability_name = ?
            """,
            (normalized, server_key, capability_kind, capability_name),
        )
        return self._serialize_mcp_capability_policy_row(row) if row else {}

    def delete_mcp_capability_policy(
        self,
        agent_id: str,
        server_key: str,
        capability_kind: str,
        capability_name: str,
    ) -> dict[str, Any]:
        if _is_reserved_mcp_server_key(server_key):
            return {"deleted": False}
        normalized = _normalize_agent_id(agent_id)
        count = execute(
            """
            DELETE FROM cp_mcp_capability_policies
            WHERE agent_id = ? AND server_key = ?
              AND capability_kind = ? AND capability_name = ?
            """,
            (normalized, server_key, capability_kind, capability_name),
        )
        if capability_kind == "tool":
            execute(
                "DELETE FROM cp_mcp_tool_policies WHERE agent_id = ? AND server_key = ? AND tool_name = ?",
                (normalized, server_key, capability_name),
            )
        return {"deleted": bool(count)}

    def _get_mcp_capability_policy(self, agent_id: str, server_key: str, kind: str, name: str) -> str:
        row = fetch_one(
            """
            SELECT policy FROM cp_mcp_capability_policies
            WHERE agent_id = ? AND server_key = ?
              AND capability_kind = ? AND capability_name = ?
            """,
            (agent_id, server_key, kind, name),
        )
        if row is None:
            return "auto"
        return str(row.get("policy") or "auto")

    def _serialize_mcp_capability_policy_row(self, row: Any) -> dict[str, Any]:
        return {
            "capability_kind": str(row.get("capability_kind") or ""),
            "capability_name": str(row.get("capability_name") or ""),
            "policy": str(row.get("policy") or "auto"),
            "exposure_mode": row.get("exposure_mode"),
            "metadata": json_load(str(row.get("metadata_json") or "{}"), {}),
            "updated_at": str(row.get("updated_at") or ""),
        }

    def _serialize_mcp_resource_row(self, row: Any) -> dict[str, Any]:
        return {
            "uri_hash": str(row.get("uri_hash") or ""),
            "uri": str(row.get("uri") or ""),
            "name": row.get("name"),
            "description": row.get("description"),
            "mime_type": row.get("mime_type"),
            "is_template": bool(row.get("is_template")),
            "annotations": json_load(str(row.get("annotations_json") or "{}"), {}),
            "discovered_at": str(row.get("discovered_at") or ""),
        }

    def _serialize_mcp_prompt_row(self, row: Any) -> dict[str, Any]:
        return {
            "name": str(row.get("prompt_name") or ""),
            "description": row.get("description"),
            "arguments": json_load(str(row.get("arguments_json") or "[]"), []),
            "discovered_at": str(row.get("discovered_at") or ""),
        }

    # ------------------------------------------------------------------ #
    #  Custom MCP Servers (system-wide + per-agent)                      #
    # ------------------------------------------------------------------ #

    def list_custom_mcp_servers(self, *, agent_id: str | None = None) -> list[dict[str, Any]]:
        from koda.integrations.custom_mcp_registry import list_custom_servers

        normalized = _normalize_agent_id(agent_id) if agent_id else None
        return list_custom_servers(agent_id=normalized)

    def get_custom_mcp_server(self, server_key: str, *, agent_id: str | None = None) -> dict[str, Any] | None:
        from koda.integrations.custom_mcp_registry import get_custom_server

        normalized = _normalize_agent_id(agent_id) if agent_id else None
        return get_custom_server(server_key, agent_id=normalized)

    def register_custom_mcp_server(
        self,
        payload: dict[str, Any],
        *,
        agent_id: str | None = None,
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        from koda.control_plane.crypto import get_signing_key
        from koda.integrations.custom_mcp_registry import (
            CustomServerPayload,
            normalize_server_key,
            upsert_custom_server,
        )

        normalized_agent = _normalize_agent_id(agent_id) if agent_id else None
        try:
            secret_key = get_signing_key()
        except Exception:
            secret_key = None

        # Detect Claude Desktop import shape and route accordingly.
        if isinstance(payload, dict) and "mcpServers" in payload:
            return {
                "import_result": self.import_claude_desktop_mcp(
                    payload,
                    agent_id=normalized_agent,
                    owner_user_id=owner_user_id,
                )
            }

        normalized_payload = CustomServerPayload(
            server_key=normalize_server_key(str(payload.get("server_key") or "")),
            display_name=str(payload.get("display_name") or ""),
            description=str(payload.get("description") or ""),
            transport_type=str(payload.get("transport_type") or "stdio"),
            command=list(payload.get("command") or []),
            args=list(payload.get("args") or []),
            url=payload.get("url"),
            headers_schema=list(payload.get("headers_schema") or []),
            env_schema=list(payload.get("env_schema") or []),
            auth_strategy=str(payload.get("auth_strategy") or "no_auth"),
            oauth_config=dict(payload.get("oauth_config") or {}),
            isolation_profile=str(payload.get("isolation_profile") or "auto"),
            isolation_constraints=dict(payload.get("isolation_constraints") or {}),
            runtime_constraints=list(payload.get("runtime_constraints") or []),
            metadata=dict(payload.get("metadata") or {}),
            source=str(payload.get("source") or "manual"),
        )
        return upsert_custom_server(
            normalized_payload,
            agent_id=normalized_agent,
            owner_user_id=owner_user_id,
            secret_key=secret_key,
        )

    def import_claude_desktop_mcp(
        self,
        raw: dict[str, Any],
        *,
        agent_id: str | None = None,
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        from koda.control_plane.crypto import get_signing_key
        from koda.integrations.custom_mcp_registry import import_claude_desktop_json

        normalized_agent = _normalize_agent_id(agent_id) if agent_id else None
        try:
            secret_key = get_signing_key()
        except Exception:
            secret_key = None
        result = import_claude_desktop_json(
            raw,
            agent_id=normalized_agent,
            owner_user_id=owner_user_id,
            secret_key=secret_key,
        )
        return {
            "created": list(result.created),
            "updated": list(result.updated),
            "errors": [{"name": err.name, "message": err.message} for err in result.errors],
        }

    def delete_custom_mcp_server(self, server_key: str, *, agent_id: str | None = None) -> dict[str, Any]:
        from koda.integrations.custom_mcp_registry import delete_custom_server

        normalized_agent = _normalize_agent_id(agent_id) if agent_id else None
        deleted = delete_custom_server(server_key, agent_id=normalized_agent)
        return {"deleted": deleted}


_MANAGER: ControlPlaneManager | None = None


def get_control_plane_manager() -> ControlPlaneManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = ControlPlaneManager()
    return _MANAGER
