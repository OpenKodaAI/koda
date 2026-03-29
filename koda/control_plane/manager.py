"""High-level control-plane management and materialization."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import re
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from koda.agent_contract import (
    normalize_string_list,
    resolve_allowed_tool_ids,
    resolve_core_provider_catalog,
    resolve_feature_filtered_tools,
)
from koda.config import SHARED_PLATFORM_PROMPT, STATE_BACKEND
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
from koda.services.kokoro_manager import (
    KOKORO_DEFAULT_LANGUAGE_ID,
    KOKORO_DEFAULT_VOICE_ID,
    ensure_kokoro_voice_downloaded,
    kokoro_catalog_payload,
    kokoro_managed_voices_path,
    kokoro_voice_file_path,
    kokoro_voice_metadata,
)
from koda.services.prompt_budget import PromptSegment, preview_compiled_prompt, preview_modeled_runtime_prompt
from koda.services.provider_auth import (
    MANAGED_PROVIDER_IDS,
    PROVIDER_API_KEY_ENV_KEYS,
    PROVIDER_AUTH_MODE_ENV_KEYS,
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
from koda.services.tool_prompt import build_agent_tools_prompt

from .agent_spec import (
    _normalize_markdown_block,
    build_agent_spec_from_snapshot,
    compose_agent_prompt,
    merge_agent_documents,
    normalize_agent_spec,
    normalize_autonomy_policy,
    normalize_knowledge_policy,
    normalize_memory_policy,
    parse_json_env_value,
    render_markdown_documents_from_agent_spec,
    resolve_agent_documents,
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
from .settings import (
    AGENT_SECTIONS,
    CONTROL_PLANE_AUTO_IMPORT,
    CONTROL_PLANE_RUNTIME_DIR,
    DASHBOARD_AGENT_CONSTANTS_PATH,
    DOCUMENT_KINDS,
    ROOT_DIR,
    looks_like_secret_key,
)

log = get_logger(__name__)

_AGENT_PREFIX_RE = re.compile(r"^([A-Z0-9_]+)_(.+)$")
_TELEGRAM_AGENT_TOKEN_RE = re.compile(r"^([A-Z0-9_]+)_AGENT_TOKEN$")
_LOWERCASE_FILE_SAFE_RE = re.compile(r"[^a-z0-9_-]+")
_STATUS_VALUES = frozenset({"active", "paused", "archived"})
_SCOPE_VALUES = frozenset({"agent", "global"})
_ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
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
    tool_contracts = build_agent_tools_prompt(postgres_env=None)
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
    },
    "providers": {
        "functional_defaults": ("MODEL_FUNCTION_DEFAULTS_JSON", "json"),
        "default_provider": ("DEFAULT_PROVIDER", "string"),
        "fallback_order": ("PROVIDER_FALLBACK_ORDER", "csv"),
        "max_budget_usd": ("MAX_BUDGET_USD", "float"),
        "max_total_budget_usd": ("MAX_TOTAL_BUDGET_USD", "float"),
        "elevenlabs_default_language": ("ELEVENLABS_DEFAULT_LANGUAGE", "string"),
        "elevenlabs_default_voice": ("TTS_DEFAULT_VOICE", "string"),
        "kokoro_default_language": ("KOKORO_DEFAULT_LANGUAGE", "string"),
        "kokoro_default_voice": ("KOKORO_DEFAULT_VOICE", "string"),
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
        "gws_enabled": ("GWS_ENABLED", "bool"),
        "jira_enabled": ("JIRA_ENABLED", "bool"),
        "confluence_enabled": ("CONFLUENCE_ENABLED", "bool"),
        "postgres_enabled": ("POSTGRES_ENABLED", "bool"),
        "aws_enabled": ("AWS_ENABLED", "bool"),
        "whisper_enabled": ("WHISPER_ENABLED", "bool"),
        "tts_enabled": ("TTS_ENABLED", "bool"),
        "link_analysis_enabled": ("LINK_ANALYSIS_ENABLED", "bool"),
        "gh_enabled": ("GH_ENABLED", "bool"),
        "glab_enabled": ("GLAB_ENABLED", "bool"),
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
    }
)
_CORE_PROVIDER_ENABLED_DEFAULTS: dict[str, bool] = {
    "claude": True,
    "codex": True,
    "gemini": False,
    "ollama": False,
    "elevenlabs": False,
    "kokoro": True,
    "whispercpp": True,
    "sora": False,
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
        "SKILLS_JSON",
        "SKILLS_DIR",
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
_CORE_ONLY_GLOBAL_SECRET_KEYS: frozenset[str] = frozenset({"RUNTIME_LOCAL_UI_TOKEN", "RUNTIME_TOKEN"})
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
    "models.max_budget_usd": "MAX_BUDGET_USD",
    "models.max_total_budget_usd": "MAX_TOTAL_BUDGET_USD",
    "models.elevenlabs_default_language": "ELEVENLABS_DEFAULT_LANGUAGE",
    "models.elevenlabs_default_voice": "TTS_DEFAULT_VOICE",
    "models.kokoro_default_language": "KOKORO_DEFAULT_LANGUAGE",
    "models.kokoro_default_voice": "KOKORO_DEFAULT_VOICE",
    "models.elevenlabs_model": "ELEVENLABS_MODEL",
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
        "description": "Prioriza a melhor qualidade possível com os modelos maiores disponíveis.",
        "tier": "large",
    },
}
_GENERAL_MEMORY_PROFILES: dict[str, dict[str, Any]] = {
    "conservative": {
        "label": "Conservador",
        "description": "Memória menor, recall mais seletivo e menor custo de manutenção.",
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
        "description": "Aumenta retenção e recall para agentes que precisam aprender continuamente.",
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
        "description": "Usa somente conhecimento canônico e runbooks aprovados.",
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
        "description": "Mistura conhecimento aprovado com documentos dinâmicos do workspace.",
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
        "label": "Curado + workspace + padrões",
        "description": "Inclui padrões observados como camada fraca adicional de grounding.",
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
_GENERAL_INTEGRATION_CREDENTIAL_TEMPLATES: dict[str, dict[str, Any]] = {
    "jira": {
        "title": "Jira",
        "description": "Credenciais globais para busca, deep context e operacoes governadas no Jira.",
        "fields": (
            {
                "key": "JIRA_URL",
                "label": "URL da instância",
                "input_type": "url",
                "storage": "env",
                "required": True,
            },
            {
                "key": "JIRA_USERNAME",
                "label": "Usuário ou email",
                "input_type": "email",
                "storage": "env",
                "required": True,
            },
            {
                "key": "JIRA_API_TOKEN",
                "label": "API token",
                "input_type": "password",
                "storage": "secret",
                "required": True,
            },
        ),
    },
    "confluence": {
        "title": "Confluence",
        "description": "Credenciais globais para leitura governada de páginas e espaços do Confluence.",
        "fields": (
            {
                "key": "CONFLUENCE_URL",
                "label": "URL da instância",
                "input_type": "url",
                "storage": "env",
                "required": True,
            },
            {
                "key": "CONFLUENCE_USERNAME",
                "label": "Usuário ou email",
                "input_type": "email",
                "storage": "env",
                "required": True,
            },
            {
                "key": "CONFLUENCE_API_TOKEN",
                "label": "API token",
                "input_type": "password",
                "storage": "secret",
                "required": True,
            },
        ),
    },
    "gws": {
        "title": "Google Workspace",
        "description": "Credencial de serviço usada para operacoes aprovadas do Google Workspace.",
        "fields": (
            {
                "key": "GWS_CREDENTIALS_FILE",
                "label": "Arquivo de credenciais",
                "input_type": "path",
                "storage": "env",
                "required": True,
            },
        ),
    },
    "postgres": {
        "title": "Postgres",
        "description": "Conexao global para consultas governadas e inspeção de schema.",
        "fields": (
            {
                "key": "POSTGRES_URL",
                "label": "Connection string",
                "input_type": "password",
                "storage": "secret",
                "required": True,
            },
        ),
    },
    "aws": {
        "title": "AWS",
        "description": "Perfis e regiao padrao usados pelo sistema quando integracoes AWS estiverem habilitadas.",
        "fields": (
            {
                "key": "AWS_DEFAULT_REGION",
                "label": "Região padrão",
                "input_type": "text",
                "storage": "env",
                "required": True,
            },
            {
                "key": "AWS_PROFILE_DEV",
                "label": "Perfil dev",
                "input_type": "text",
                "storage": "env",
                "required": False,
            },
            {
                "key": "AWS_PROFILE_PROD",
                "label": "Perfil prod",
                "input_type": "text",
                "storage": "env",
                "required": False,
            },
        ),
    },
}


@dataclass(slots=True)
class RuntimeSnapshot:
    agent_id: str
    version: int
    runtime_dir: Path
    env: dict[str, str]
    health_url: str
    runtime_base_url: str
    state_backend: str
    db_file_name: str
    persisted_to_disk: bool = False


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


def _user_selectable_provider_ids(provider_catalog: dict[str, Any]) -> list[str]:
    return [
        provider_id
        for provider_id, payload in _safe_json_object(provider_catalog.get("providers")).items()
        if _nonempty_text(_safe_json_object(payload).get("category")) != "infra"
    ]


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
    if normalized in _CORE_ONLY_GLOBAL_SECRET_KEYS:
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
        self._ollama_model_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._provider_login_processes: dict[str, Any] = {}
        self._provider_download_threads: dict[str, threading.Thread] = {}

    def ensure_seeded(self) -> None:
        if self._seeding_legacy_state:
            return
        if CONTROL_PLANE_AUTO_IMPORT:
            self.import_legacy_state()
        self._reconcile_global_secret_classification()
        self._cleanup_provider_login_sessions()
        self._cleanup_provider_download_jobs()

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
        return {
            "id": str(row["id"]),
            "name": str(row["name"]),
            "description": str(row["description"] or ""),
            "color": str(row["color"] or ""),
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
        return {
            "id": str(row["id"]),
            "workspace_id": str(row["workspace_id"]),
            "name": str(row["name"]),
            "description": str(row["description"] or ""),
            "color": str(row["color"] or ""),
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
            "workspace_color": str(workspace_row["color"] or "") if workspace_row is not None else None,
            "squad_id": normalized_squad_id,
            "squad_name": str(squad_row["name"]) if squad_row is not None else None,
            "squad_color": str(squad_row["color"] or "") if squad_row is not None else None,
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
        execute(
            """
            INSERT INTO cp_workspaces (id, name, description, color, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                workspace_id,
                name,
                str(payload.get("description") or "").strip(),
                str(payload.get("color") or "").strip(),
                now,
                now,
            ),
        )
        return next(item for item in self.list_workspaces()["items"] if item["id"] == workspace_id)

    def update_workspace(self, workspace_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_seeded()
        row = self._workspace_row(workspace_id)
        name = str(payload.get("name") or row["name"]).strip()
        if not name:
            raise ValueError("workspace name is required")
        execute(
            """
            UPDATE cp_workspaces
            SET name = ?, description = ?, color = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                name,
                str(payload.get("description") if "description" in payload else row["description"] or "").strip(),
                str(payload.get("color") if "color" in payload else row["color"] or "").strip(),
                now_iso(),
                str(row["id"]),
            ),
        )
        return next(item for item in self.list_workspaces()["items"] if item["id"] == str(row["id"]))

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
            INSERT INTO cp_workspace_squads (id, workspace_id, name, description, color, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                squad_id,
                str(workspace_row["id"]),
                name,
                str(payload.get("description") or "").strip(),
                str(payload.get("color") or "").strip(),
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
            SET name = ?, description = ?, color = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                name,
                str(payload.get("description") if "description" in payload else squad_row["description"] or "").strip(),
                str(payload.get("color") if "color" in payload else squad_row["color"] or "").strip(),
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

    def _ensure_provider_connections_seeded(self) -> None:
        sections = self._system_settings_sections()
        base_env = self._merged_global_env_base()
        now = now_iso()
        for provider_id in MANAGED_PROVIDER_IDS:
            existing = fetch_one(
                "SELECT provider_id FROM cp_provider_connections WHERE provider_id = ?",
                (provider_id,),
            )
            if existing is not None:
                continue
            secret_present = bool(self._provider_api_key_secret_value(provider_id))
            project_id = ""
            project_key = PROVIDER_PROJECT_ENV_KEYS.get(provider_id)
            if project_key:
                project_id = (
                    _trimmed_text(base_env.get(project_key))
                    or _trimmed_text(os.environ.get(project_key))
                    or _trimmed_text(
                        self._access_meta_map("provider_connection_meta", sections=sections)
                        .get(provider_id.upper(), {})
                        .get("project_id")
                    )
                )
            auth_mode = "api_key" if provider_id == "elevenlabs" or secret_present else "subscription_login"
            configured = 1 if secret_present else 0
            if provider_id == "ollama":
                auth_mode = "local"
                configured = 1 if self._bool_from_env(base_env, "OLLAMA_ENABLED", False) else 0
            execute(
                """
                INSERT OR IGNORE INTO cp_provider_connections (
                    provider_id, auth_mode, configured, verified, account_label, plan_label,
                    project_id, last_verified_at, last_error, created_at, updated_at
                ) VALUES (?, ?, ?, 0, '', '', ?, NULL, '', ?, ?)
                """,
                (
                    provider_id,
                    auth_mode,
                    configured,
                    project_id,
                    now,
                    now,
                ),
            )

    def _provider_connection_row(self, provider_id: str) -> Any:
        normalized = provider_id.strip().lower()
        if normalized not in MANAGED_PROVIDER_IDS:
            raise ValueError(f"unsupported provider connection: {provider_id}")
        self._ensure_provider_connections_seeded()
        row = fetch_one(
            "SELECT * FROM cp_provider_connections WHERE provider_id = ?",
            (normalized,),
        )
        if row is None:
            raise KeyError(normalized)
        return row

    def _provider_connection_meta(self) -> dict[str, dict[str, Any]]:
        return self._access_meta_map("provider_connection_meta")

    def _resolve_ollama_base_url(
        self,
        *,
        auth_mode: str = "local",
        env: dict[str, str] | None = None,
        sections: dict[str, dict[str, Any]] | None = None,
    ) -> str:
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
        self._ensure_provider_connections_seeded()
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

    def get_ollama_model_catalog(self) -> dict[str, Any]:
        auth_mode, base_url, api_key = self._resolve_ollama_connection_inputs(env=self._merged_global_env())
        return self._fetch_ollama_model_catalog(auth_mode=auth_mode, base_url=base_url, api_key=api_key)

    def _provider_auth_work_dir(self, provider_id: str) -> str:
        path = CONTROL_PLANE_RUNTIME_DIR / "_provider_auth" / provider_id.strip().lower()
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def _persist_provider_connection_meta(
        self,
        provider_id: str,
        *,
        project_id: str = "",
        base_url: str = "",
    ) -> None:
        sections = self._system_settings_sections()
        access_section = dict(self._access_section(sections))
        meta_map = dict(self._provider_connection_meta())
        normalized = provider_id.strip().upper()
        payload = dict(_safe_json_object(meta_map.get(normalized)))
        if project_id.strip():
            payload["project_id"] = project_id.strip()
        elif "project_id" in payload:
            payload.pop("project_id", None)
        if base_url.strip():
            payload["base_url"] = base_url.strip()
        elif "base_url" in payload:
            payload.pop("base_url", None)
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

    def _provider_connection_env(self) -> dict[str, str]:
        self._ensure_provider_connections_seeded()
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
        auth_mode = _trimmed_text(row["auth_mode"]) or (
            "api_key" if provider_id == "elevenlabs" else "subscription_login"
        )
        provider_api_key_env = PROVIDER_API_KEY_ENV_KEYS.get(cast(Any, provider_id))
        if provider_api_key_env:
            api_key_present, api_key_preview = self._global_secret_preview_state(provider_api_key_env)
        else:
            api_key_present, api_key_preview = False, ""
        payload = {
            "provider_id": provider_id,
            "title": _safe_json_object(catalog).get("title")
            or PROVIDER_TITLES.get(cast(Any, provider_id), provider_id),
            "auth_mode": auth_mode,
            "configured": bool(int(row["configured"] or 0)),
            "verified": bool(int(row["verified"] or 0)),
            "account_label": _trimmed_text(row["account_label"]),
            "plan_label": _trimmed_text(row["plan_label"]),
            "last_verified_at": _trimmed_text(row["last_verified_at"]),
            "last_error": _trimmed_text(row["last_error"]),
            "project_id": _trimmed_text(row["project_id"]),
            "command_present": provider_command_present(provider_id, base_env=env),
            "supports_api_key": bool(_safe_json_object(catalog).get("supports_api_key", True)),
            "supports_subscription_login": bool(_safe_json_object(catalog).get("supports_subscription_login", True)),
            "supports_local_connection": "local" in (_safe_json_object(catalog).get("supported_auth_modes") or []),
            "supported_auth_modes": _safe_json_object(catalog).get("supported_auth_modes") or ["api_key"],
            "login_flow_kind": _safe_json_object(catalog).get("login_flow_kind"),
            "requires_project_id": bool(_safe_json_object(catalog).get("requires_project_id", False)),
            "api_key_present": api_key_present,
            "api_key_preview": api_key_preview,
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

    def _current_global_secrets(self, *, sections: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        rows = fetch_all("SELECT * FROM cp_secret_values WHERE scope_id = 'global' ORDER BY secret_key ASC")
        secret_meta = self._access_meta_map("global_secret_meta", sections=sections)
        return [
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
        ]

    def _reconcile_global_secret_classification(self) -> None:
        rows = fetch_all("SELECT id, secret_key, encrypted_value FROM cp_secret_values WHERE scope_id = 'global'")
        if not rows:
            return

        sections = self._system_settings_sections()
        sections_changed = False
        secret_ids_to_delete: list[int] = []

        for row in rows:
            secret_key = str(row["secret_key"] or "").strip().upper()
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
            "postgres": self._bool_from_env(env, "POSTGRES_ENABLED"),
            "jira": self._bool_from_env(env, "JIRA_ENABLED"),
            "confluence": self._bool_from_env(env, "CONFLUENCE_ENABLED"),
            "gws": self._bool_from_env(env, "GWS_ENABLED"),
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
            available_models = list(dict.fromkeys(available_models + resolve_known_general_model_ids(provider)))
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
            else:
                binary = "claude"
            if provider == "ollama":
                auth_mode, base_url, api_key = self._resolve_ollama_connection_inputs(env=env)
                live_catalog = self._fetch_ollama_model_catalog(
                    auth_mode=auth_mode,
                    base_url=base_url,
                    api_key=api_key,
                )
                live_models = [str(item["model_id"]) for item in _safe_json_list(live_catalog.get("items")) if item]
                if live_models:
                    available_models = live_models
                if not default_model and live_models:
                    default_model = live_models[0]
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
        if not fallback_order:
            fallback_order = enabled_ids.copy()
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

    def get_dashboard_agent_summary(self, agent_id: str) -> dict[str, Any]:
        normalized, row = self._require_dashboard_agent(agent_id)
        stats = self._dashboard_store().get_agent_stats(normalized)
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
        return cast(dict[str, Any] | None, self._dashboard_store().get_execution(normalized, task_id))

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

    def get_dashboard_session(self, agent_id: str, session_id: str) -> dict[str, Any] | None:
        normalized, _ = self._require_dashboard_agent(agent_id)
        return cast(dict[str, Any] | None, self._dashboard_store().get_session(normalized, session_id))

    def send_dashboard_session_message(
        self,
        agent_id: str,
        *,
        text: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        payload_text = str(text or "").strip()
        if not payload_text:
            raise ValueError("text is required")

        runtime_access = self.get_runtime_access(normalized)
        runtime_base_url = str(runtime_access.get("runtime_base_url") or "").rstrip("/")
        runtime_token = str(runtime_access.get("runtime_token") or "").strip()
        if not runtime_base_url:
            raise RuntimeError("runtime base URL is unavailable for this agent")
        if not runtime_token:
            raise RuntimeError("runtime token is unavailable for this agent")

        request_payload = {"text": payload_text}
        if session_id:
            request_payload["session_id"] = str(session_id).strip()

        request = urllib.request.Request(
            f"{runtime_base_url}/api/runtime/sessions/messages",
            data=json.dumps(request_payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Runtime-Token": runtime_token,
                "User-Agent": "koda/control-plane",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return cast(dict[str, Any], json.loads(response.read().decode("utf-8")))
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
            except Exception:
                payload = None
            message = (
                str(payload.get("error"))
                if isinstance(payload, dict) and payload.get("error")
                else f"runtime request failed with status {exc.code}"
            )
            if 400 <= exc.code < 500:
                raise ValueError(message) from exc
            raise RuntimeError(message) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("runtime is unavailable") from exc

    def list_dashboard_dlq(
        self,
        agent_id: str,
        *,
        limit: int = 50,
        retry_eligible: bool | None = None,
    ) -> list[dict[str, Any]]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        return cast(
            list[dict[str, Any]],
            self._dashboard_store().list_dlq(normalized, limit=limit, retry_eligible=retry_eligible),
        )

    def get_dashboard_costs(self, agent_id: str, *, days: int = 30) -> dict[str, Any]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        return cast(dict[str, Any], self._dashboard_store().get_costs(normalized, days=days))

    def list_dashboard_schedules(self, agent_id: str) -> list[dict[str, Any]]:
        normalized, _ = self._require_dashboard_agent(agent_id)
        return cast(list[dict[str, Any]], self._dashboard_store().list_schedules(normalized))

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
                connection = self.get_provider_connection(provider_id)
                payload["connection_status"] = connection.get("connection_status")
                payload["connection"] = connection
            payload["functional_models"] = resolve_provider_function_model_catalog(
                provider_id,
                available_models=[
                    str(item)
                    for item in _safe_json_object(catalog.get("providers")).get(provider_id, {}).get("available_models")
                    or []
                ],
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
        return {
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
        row = fetch_one(
            "SELECT * FROM cp_provider_login_sessions WHERE id = ? AND provider_id = ?",
            (session_id, provider_id.strip().lower()),
        )
        if row is None:
            raise KeyError(session_id)
        handle = self._provider_login_processes.get(session_id)
        if handle is not None:
            state = parse_login_session_state(session_id, handle)
            self._persist_provider_login_session(state)
            if state.status in {"completed", "error", "cancelled"}:
                self._provider_login_processes.pop(session_id, None)
            row = fetch_one("SELECT * FROM cp_provider_login_sessions WHERE id = ?", (session_id,))
            if row is None:
                raise KeyError(session_id)
        details = self._inflate_provider_login_session_details(_safe_json_object(json_load(row["details_json"], {})))
        details.setdefault("session_id", session_id)
        details.setdefault("provider_id", provider_id.strip().lower())
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
        }
        payload.update(details)
        return payload

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
        self._persist_provider_download_job(
            job_id,
            provider_id="kokoro",
            asset_id=voice_id,
            status="running",
            details={**base_details, "message": "Baixando voz do catalogo oficial do Kokoro."},
        )

        def _on_progress(downloaded_bytes: int, total_bytes: int) -> None:
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
            result = ensure_kokoro_voice_downloaded(voice_id, progress_callback=_on_progress)
            downloaded_bytes = int(result.get("bytes") or 0)
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
        except Exception as exc:
            self._persist_provider_download_job(
                job_id,
                provider_id="kokoro",
                asset_id=voice_id,
                status="error",
                details={**base_details, "last_error": str(exc)},
            )
        finally:
            self._provider_download_threads.pop(job_id, None)

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
        return {
            "items": _safe_json_list(payload.get("items")),
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
        self._provider_download_threads[job_id] = thread
        thread.start()
        row = fetch_one("SELECT * FROM cp_provider_download_jobs WHERE id = ?", (job_id,))
        if row is None:
            raise RuntimeError("failed to persist kokoro download job")
        return self._provider_download_job_payload(row)

    def get_provider_download_job(self, provider_id: str, job_id: str) -> dict[str, Any]:
        normalized = provider_id.strip().lower()
        if normalized != "kokoro":
            raise ValueError(f"unsupported provider download: {provider_id}")
        self._cleanup_provider_download_jobs()
        row = fetch_one(
            "SELECT * FROM cp_provider_download_jobs WHERE id = ? AND provider_id = ?",
            (job_id, normalized),
        )
        if row is None:
            raise KeyError(job_id)
        return self._provider_download_job_payload(row)

    def get_provider_connection(self, provider_id: str) -> dict[str, Any]:
        return self._serialize_provider_connection(provider_id.strip().lower())

    def put_provider_api_key_connection(self, provider_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = provider_id.strip().lower()
        if normalized not in MANAGED_PROVIDER_IDS:
            raise ValueError(f"unsupported provider connection: {provider_id}")
        api_key = _trimmed_text(payload.get("api_key"))
        clear_api_key = bool(payload.get("clear_api_key"))
        existing_row = self._provider_connection_row(normalized)
        project_id = _trimmed_text(payload.get("project_id")) or _trimmed_text(existing_row["project_id"])
        base_url = ""
        if normalized == "ollama":
            base_url = self._resolve_ollama_base_url(
                auth_mode="api_key",
                env={"OLLAMA_BASE_URL": _trimmed_text(payload.get("base_url"))},
            )
            self._persist_provider_connection_meta(normalized, base_url=base_url)
        if normalized == "gemini" and project_id:
            self._persist_provider_connection_meta(normalized, project_id=project_id)
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
        return self.get_provider_connection(normalized)

    def put_provider_local_connection(self, provider_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = provider_id.strip().lower()
        if normalized != "ollama":
            raise ValueError(f"unsupported local provider connection: {provider_id}")
        base_url = self._resolve_ollama_base_url(
            auth_mode="local",
            env={"OLLAMA_BASE_URL": _trimmed_text(payload.get("base_url"))},
        )
        self._persist_provider_connection_meta(normalized, base_url=base_url)
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
        if normalized == "ollama":
            raise ValueError("Ollama usa conexão local/servidor ou API key nesta interface.")
        payload = payload or {}
        project_id = _trimmed_text(payload.get("project_id"))
        existing_row = self._provider_connection_row(normalized)
        if not project_id:
            project_id = _trimmed_text(existing_row["project_id"])
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

    def verify_provider_connection(self, provider_id: str) -> dict[str, Any]:
        normalized = provider_id.strip().lower()
        row = self._provider_connection_row(normalized)
        auth_mode = _trimmed_text(row["auth_mode"]) or "subscription_login"
        if normalized == "elevenlabs":
            auth_mode = "api_key"
        project_id = _trimmed_text(row["project_id"])
        if normalized == "ollama" and auth_mode == "local":
            base_url = self._resolve_ollama_base_url(auth_mode="local")
            result = verify_provider_local_connection("ollama", base_url=base_url)
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
            },
        }

    def disconnect_provider_connection(self, provider_id: str) -> dict[str, Any]:
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

        auth_mode = _trimmed_text(row["auth_mode"]) or "subscription_login"
        logout_performed = False
        logout_message = ""
        if auth_mode == "api_key":
            self.delete_global_secret_asset(PROVIDER_API_KEY_ENV_KEYS[cast(Any, normalized)], persist_sections=True)
        else:
            logout_performed, logout_message = run_provider_logout(
                cast(Any, normalized),
                base_env=self._merged_global_env(),
                work_dir=self._provider_auth_work_dir(normalized),
            )
            if not logout_performed and logout_message == "logout not supported":
                logout_message = ""

        reset_auth_mode = (
            "api_key" if normalized == "elevenlabs" else "local" if normalized == "ollama" else "subscription_login"
        )

        self._persist_provider_connection_row(
            normalized,
            auth_mode=reset_auth_mode,
            configured=False,
            verified=False,
            account_label="",
            plan_label="",
            project_id=_trimmed_text(row["project_id"]),
            last_verified_at="",
            last_error="" if logout_performed or not logout_message else logout_message,
        )
        return {
            "connection": self.get_provider_connection(normalized),
            "logout": {
                "performed": logout_performed,
                "message": logout_message,
            },
        }

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
                    "memory_policy",
                    "knowledge_policy",
                    "resource_access_policy",
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
            "resource_access_policy",
            "voice_policy",
            "image_analysis_policy",
            "memory_extraction_schema",
        ):
            if key in payload:
                updated_spec[key] = _safe_json_object(payload.get(key))

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
        provider_errors = [
            f"provider '{provider}' is enabled but its runtime command is not available"
            for provider, payload in _safe_json_object(provider_catalog.get("providers")).items()
            if bool(_safe_json_object(payload).get("enabled"))
            and str(_safe_json_object(payload).get("category") or "general") != "infra"
            and not bool(_safe_json_object(payload).get("command_present"))
        ]
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

        result = {
            **validation,
            "provider_errors": provider_errors,
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
        result["warnings"] = [*validation["warnings"], *provenance_warnings, *resource_warnings]
        result["errors"] = [*validation["errors"], *provider_errors, *resource_errors, *runtime_prompt_errors]
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

    def create_agent(self, payload: dict[str, Any]) -> dict[str, Any]:
        agent_id = _normalize_agent_id(str(payload.get("id") or ""))
        display_name = str(payload.get("display_name") or agent_id.replace("_", " "))
        storage_namespace = str(payload.get("storage_namespace") or _slug(agent_id))
        appearance = _safe_json_object(payload.get("appearance"))
        runtime_endpoint = _safe_json_object(payload.get("runtime_endpoint"))
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
        return self.update_agent(agent_id, {"status": "active"})

    def pause_agent(self, agent_id: str) -> dict[str, Any]:
        return self.update_agent(agent_id, {"status": "paused"})

    def get_global_defaults(self) -> dict[str, Any]:
        self.ensure_seeded()
        sections = self._load_global_sections()
        version_row = fetch_one("SELECT id FROM cp_global_default_versions ORDER BY id DESC LIMIT 1")
        return {
            "sections": sections,
            "version": int(version_row["id"]) if version_row else self._persist_global_default_version(sections),
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

    def _integration_credentials_payload(
        self,
        *,
        merged_env: dict[str, str],
        sections: dict[str, dict[str, Any]],
    ) -> tuple[dict[str, Any], dict[str, str]]:
        global_secrets = {str(item["secret_key"]): item for item in self._current_global_secrets(sections=sections)}
        credentials: dict[str, Any] = {}
        source_badges: dict[str, str] = {}
        for integration_key, template in _GENERAL_INTEGRATION_CREDENTIAL_TEMPLATES.items():
            items: list[dict[str, Any]] = []
            for field in template["fields"]:
                env_key = str(field["key"])
                storage = str(field["storage"])
                if storage == "secret":
                    secret = global_secrets.get(env_key)
                    value_present, preview = self._global_secret_preview_state(env_key)
                    items.append(
                        {
                            **field,
                            "value": "",
                            "preview": str(secret.get("preview") or "") if secret else preview,
                            "value_present": bool(secret) or value_present,
                            "usage_scope": str(secret.get("usage_scope") or "system_only") if secret else "system_only",
                        }
                    )
                    source_badges[f"credentials.{env_key}"] = (
                        "custom" if secret else ("env" if os.environ.get(env_key) else "system_default")
                    )
                else:
                    current_value = _nonempty_text(merged_env.get(env_key) or os.environ.get(env_key))
                    items.append({**field, "value": current_value})
                    source_badges[f"credentials.{env_key}"] = self._system_settings_badge(
                        env_key,
                        merged_env=merged_env,
                    )
            credentials[integration_key] = {
                "title": template["title"],
                "description": template["description"],
                "fields": items,
            }
        return credentials, source_badges

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
                    "preview": str(secret.get("preview") or ""),
                    "value_present": True,
                }
            )
        return sorted(variables, key=lambda item: (item["type"] != "secret", item["key"]))

    def _general_review_warnings(
        self,
        values: dict[str, Any],
        integration_credentials: dict[str, Any],
    ) -> list[str]:
        warnings: list[str] = []
        models = _safe_json_object(values.get("models"))
        provider_connections = {
            str(key): _safe_json_object(value)
            for key, value in _safe_json_object(values.get("provider_connections")).items()
        }
        enabled_providers = normalize_string_list(models.get("providers_enabled"))
        default_provider = _nonempty_text(models.get("default_provider")).lower()
        fallback_order = normalize_string_list(models.get("fallback_order"))
        if enabled_providers and default_provider not in enabled_providers:
            warnings.append("O provider padrão precisa estar habilitado.")
        if enabled_providers and not fallback_order:
            warnings.append("Defina ao menos uma ordem de fallback entre os providers habilitados.")
        if fallback_order and any(provider not in enabled_providers for provider in fallback_order):
            warnings.append("A ordem de fallback contém providers que não estão habilitados.")
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
            warnings.append("O provider padrão precisa estar conectado e verificado.")
        if any(
            provider in MANAGED_PROVIDER_IDS
            and not bool(_safe_json_object(provider_connections.get(provider)).get("verified"))
            for provider in fallback_order
        ):
            warnings.append("A ordem de fallback inclui providers que ainda não foram verificados.")
        elevenlabs_voice = _nonempty_text(models.get("elevenlabs_default_voice"))
        if elevenlabs_voice and not bool(_safe_json_object(provider_connections.get("elevenlabs")).get("verified")):
            warnings.append("Conecte e valide o ElevenLabs antes de definir a voz padrão dos agents.")
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
        for integration_key, template in _GENERAL_INTEGRATION_CREDENTIAL_TEMPLATES.items():
            if not bool(integrations.get(f"{integration_key}_enabled")):
                continue
            payload = _safe_json_object(integration_credentials.get(integration_key))
            fields = _safe_json_list(payload.get("fields"))
            missing = [
                str(field.get("label") or field.get("key"))
                for field in fields
                if bool(field.get("required")) and not bool(field.get("value") or field.get("value_present"))
            ]
            if missing:
                warnings.append(
                    f"{template['title']} está habilitado, mas faltam credenciais obrigatórias: {', '.join(missing)}."
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
        if normalized == "sora":
            # Sora is exposed through OpenAI/Codex model ids for the actual supported path.
            # Avoid advertising a redundant standalone provider until there is a dedicated
            # runtime adapter and connection flow for it.
            return False
        if normalized in MANAGED_PROVIDER_IDS:
            connection = _safe_json_object(provider_connections.get(normalized))
            if normalized == "codex" and function_id == "transcription":
                return bool(connection.get("verified")) and bool(connection.get("api_key_present"))
            return bool(connection.get("verified"))
        command_present = bool(provider_payload.get("command_present", False))
        enabled = bool(provider_payload.get("enabled", False))
        category = str(provider_payload.get("category") or "general")
        if category == "voice" and normalized == "kokoro":
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
                defaults["transcription"] = {
                    "provider_id": "whispercpp",
                    "model_id": "whisper-cpp-local",
                }
            else:
                codex_connection = _safe_json_object(_safe_json_object(providers.get("codex")).get("connection"))
                if bool(codex_connection.get("verified")) and bool(codex_connection.get("api_key_present")):
                    defaults["transcription"] = {
                        "provider_id": "codex",
                        "model_id": "whisper-1",
                    }
        return defaults

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

        url = "https://api.elevenlabs.io/v2/voices?page_size=100"
        request = urllib.request.Request(
            url,
            headers={
                "xi-api-key": api_key,
                "User-Agent": "koda/control-plane",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                data = json.loads(response.read())
        except Exception:
            if cached:
                stale = dict(cached[1])
                stale["cached"] = True
                return stale
            return {"items": [], "available_languages": [], "cached": False, "provider_connected": True}

        items: list[dict[str, Any]] = []
        language_labels: dict[str, str] = {}
        for voice in _safe_json_list(data.get("voices")):
            payload = _safe_json_object(voice)
            labels = _safe_json_object(payload.get("labels"))
            verified_languages = []
            for language_payload in _safe_json_list(payload.get("verified_languages")):
                language_entry = _safe_json_object(language_payload)
                language_code = _nonempty_text(language_entry.get("language")).lower()
                if not language_code:
                    continue
                language_label = (
                    _nonempty_text(language_entry.get("name"))
                    or _nonempty_text(language_entry.get("display_name"))
                    or language_code.upper()
                )
                language_labels.setdefault(language_code, language_label)
                verified_languages.append({"code": language_code, "label": language_label})
            items.append(
                {
                    "voice_id": _nonempty_text(payload.get("voice_id")),
                    "name": _nonempty_text(payload.get("name")) or "Sem nome",
                    "gender": _nonempty_text(labels.get("gender")),
                    "accent": _nonempty_text(labels.get("accent")),
                    "category": _nonempty_text(payload.get("category")),
                    "preview_url": _nonempty_text(payload.get("preview_url")),
                    "languages": verified_languages,
                }
            )

        items = [item for item in items if item["voice_id"]]
        items.sort(key=lambda item: str(item["name"]).casefold())
        available_languages = [
            {"code": code, "label": label}
            for code, label in sorted(language_labels.items(), key=lambda item: item[1].casefold())
        ]
        catalog = {
            "items": items,
            "available_languages": available_languages,
            "cached": False,
            "provider_connected": True,
        }
        self._elevenlabs_voice_cache[cache_key] = (now, catalog)
        return dict(catalog)

    def get_elevenlabs_voice_catalog(self, language: str = "") -> dict[str, Any]:
        requested_language = _nonempty_text(language).lower()
        catalog = self._elevenlabs_fetch_voice_catalog(self._resolve_elevenlabs_api_key())
        items = list(_safe_json_list(catalog.get("items")))
        if requested_language:
            filtered_items = []
            for voice in items:
                languages = {
                    _nonempty_text(_safe_json_object(entry).get("code")).lower()
                    for entry in _safe_json_list(_safe_json_object(voice).get("languages"))
                }
                if requested_language in languages:
                    filtered_items.append(voice)
            items = filtered_items
        return {
            "items": items,
            "available_languages": _safe_json_list(catalog.get("available_languages")),
            "selected_language": requested_language,
            "cached": bool(catalog.get("cached")),
            "provider_connected": bool(catalog.get("provider_connected")),
        }

    def list_elevenlabs_voices(self, language: str = "") -> list[dict[str, str]]:
        items = self.get_elevenlabs_voice_catalog(language=language).get("items")
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
            "functional_defaults": self._resolve_general_functional_defaults(
                providers_section=providers_section,
                provider_catalog=provider_catalog,
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
                    "postgres_enabled",
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
        integration_credentials, credential_badges = self._integration_credentials_payload(
            merged_env=merged_env,
            sections=sections,
        )
        provider_connections = {
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
        values = {
            "account": account_values,
            "models": model_values,
            "resources": resource_values,
            "memory_and_knowledge": memory_values,
            "variables": self._custom_global_variables_payload(legacy_settings, sections=sections),
            "integration_credentials": integration_credentials,
            "provider_connections": provider_connections,
        }
        source_badges = {
            field: self._system_settings_badge(env_key, merged_env=merged_env)
            for field, env_key in _GENERAL_FIELD_SOURCE_ENV_KEYS.items()
        }
        source_badges.update(credential_badges)
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
                        "connection_status": _safe_json_object(payload).get("connection_status") or {},
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
                        "description": "Ativa cache global para acelerar execuções repetidas.",
                        "configurable": True,
                    },
                    {
                        "id": "script_library",
                        "title": "Biblioteca de scripts",
                        "description": "Habilita scripts reutilizáveis aprovados pelo sistema.",
                        "configurable": True,
                    },
                ],
                "usage_profiles": [
                    {"id": profile_id, **profile} for profile_id, profile in _GENERAL_MODEL_USAGE_PROFILES.items()
                ],
                "memory_presets": [
                    {"id": profile_id, **profile} for profile_id, profile in _GENERAL_MEMORY_PROFILES.items()
                ],
                "knowledge_profiles": [
                    {"id": profile_id, **profile} for profile_id, profile in _GENERAL_KNOWLEDGE_PROFILES.items()
                ],
                "provenance_policies": [
                    {
                        "id": "strict",
                        "label": "Estrita",
                        "description": "Exige owner e freshness nas fontes críticas.",
                    },
                    {
                        "id": "standard",
                        "label": "Padrão",
                        "description": "Mantém governança com menos bloqueios de publicação.",
                    },
                ],
                "knowledge_layers": [
                    {
                        "id": "canonical_policy",
                        "label": "Canônico",
                        "description": "Políticas, guidelines e conhecimento validado do sistema.",
                    },
                    {
                        "id": "approved_runbook",
                        "label": "Runbooks aprovados",
                        "description": "Procedimentos operacionais aprovados e rastreáveis.",
                    },
                    {
                        "id": "workspace_doc",
                        "label": "Documentos do workspace",
                        "description": "Documentação contextual do repositório e do workspace atual.",
                    },
                    {
                        "id": "observed_pattern",
                        "label": "Padrões observados",
                        "description": "Aprendizados semânticos derivados do histórico, sempre como camada mais fraca.",
                    },
                ],
                "approval_modes": [
                    {
                        "id": "read_only",
                        "label": "Read only",
                        "description": "Investiga e responde, sem executar mutações.",
                    },
                    {
                        "id": "guarded",
                        "label": "Guarded",
                        "description": "Pode agir com verificação forte e contenção adicional.",
                    },
                    {
                        "id": "supervised",
                        "label": "Supervised",
                        "description": "Executa com supervisão humana e checkpoints frequentes.",
                    },
                    {
                        "id": "escalation_required",
                        "label": "Escalation required",
                        "description": "Precisa escalar antes de qualquer ação sensível.",
                    },
                ],
                "autonomy_tiers": [
                    {
                        "id": "t0",
                        "label": "T0",
                        "description": "Pesquisa, síntese e análise sem escrita.",
                    },
                    {
                        "id": "t1",
                        "label": "T1",
                        "description": "Ações limitadas com forte contenção e baixo risco.",
                    },
                    {
                        "id": "t2",
                        "label": "T2",
                        "description": "Execução complexa com tool loop, validação e grounding operacional.",
                    },
                ],
            },
            "review": {
                "warnings": self._general_review_warnings(values, integration_credentials),
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

    def put_general_system_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_seeded()
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
        integration_credentials = _safe_json_object(payload.get("integration_credentials"))

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

        provider_catalog = self.get_core_providers()
        enabled_providers = normalize_string_list(models.get("providers_enabled"))
        provider_connections = {
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
        normalized_kokoro_voice = _nonempty_text(current_providers.get("kokoro_default_voice")).lower()
        if normalized_kokoro_voice:
            voice_metadata = kokoro_voice_metadata(normalized_kokoro_voice)
            if voice_metadata is None:
                raise ValueError("A voz padrão do Kokoro não existe no catálogo oficial.")
            current_providers["kokoro_default_voice"] = normalized_kokoro_voice
            current_providers["kokoro_default_language"] = _nonempty_text(voice_metadata.get("language_id")).lower()
            if not _nonempty_text(general_ui.get("kokoro_default_voice_label")):
                general_ui["kokoro_default_voice_label"] = _nonempty_text(voice_metadata.get("name"))
        functional_defaults_requested = _normalize_functional_model_defaults(models.get("functional_defaults"))
        if functional_defaults_requested:
            current_providers["functional_defaults"] = functional_defaults_requested

        default_provider = _nonempty_text(current_providers.get("default_provider")).lower()
        if default_provider and default_provider not in enabled_providers:
            raise ValueError("O provider padrão precisa estar habilitado.")
        if default_provider in MANAGED_PROVIDER_IDS and not bool(
            _safe_json_object(provider_connections.get(default_provider)).get("verified")
        ):
            raise ValueError("O provider padrão precisa estar conectado e verificado.")
        requested_fallback = normalize_string_list(current_providers.get("fallback_order"))
        if any(provider not in enabled_providers for provider in requested_fallback):
            raise ValueError("A ordem de fallback contém providers não habilitados.")
        if any(
            provider in MANAGED_PROVIDER_IDS
            and not bool(_safe_json_object(provider_connections.get(provider)).get("verified"))
            for provider in requested_fallback
        ):
            raise ValueError("A ordem de fallback só pode incluir providers verificados.")

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
                raise ValueError(f"O default de {function_id} referencia um provider/modelo invalido.")
            provider_id = _nonempty_text(option.get("provider_id")).lower()
            provider_payload = _safe_json_object(_safe_json_object(provider_catalog.get("providers")).get(provider_id))
            if function_id in {"general", "transcription"} and not self._provider_selectable_for_function(
                function_id,
                provider_id,
                provider_payload,
                provider_connections,
            ):
                raise ValueError(
                    f"{option.get('provider_title') or provider_id} precisa estar disponivel "
                    f"antes de virar default de {function_id}."
                )
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
            if general_provider and general_model:
                if general_provider not in enabled_providers:
                    raise ValueError("O default geral precisa usar um provider habilitado.")
                current_providers["default_provider"] = general_provider
                current_providers[f"{general_provider}_default_model"] = general_model
            audio_default = _safe_json_object(normalized_functional_defaults.get("audio"))
            audio_provider = _nonempty_text(audio_default.get("provider_id")).lower()
            audio_model = _nonempty_text(audio_default.get("model_id"))
            if audio_provider == "elevenlabs" and audio_model:
                current_providers["elevenlabs_model"] = audio_model
        elif "functional_defaults" in current_providers:
            current_providers.pop("functional_defaults", None)

        default_provider = _nonempty_text(current_providers.get("default_provider")).lower()
        if default_provider and default_provider not in enabled_providers:
            raise ValueError("O provider padrão precisa estar habilitado.")
        if default_provider in MANAGED_PROVIDER_IDS and not bool(
            _safe_json_object(provider_connections.get(default_provider)).get("verified")
        ):
            raise ValueError("O provider padrão precisa estar conectado e verificado.")
        deduped_fallback: list[str] = []
        for provider in [default_provider, *normalize_string_list(current_providers.get("fallback_order"))]:
            if not provider or provider not in enabled_providers or provider in deduped_fallback:
                continue
            deduped_fallback.append(provider)
        current_providers["fallback_order"] = deduped_fallback

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
            "postgres_enabled",
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
        current_knowledge["promotion_mode"] = "review_queue"
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
        general_ui["provenance_policy"] = (
            "strict"
            if bool(effective_knowledge_policy.get("require_owner_provenance"))
            and bool(effective_knowledge_policy.get("require_freshness_provenance"))
            else "standard"
        )

        custom_shared_variables: list[dict[str, str]] = []
        custom_system_variables: list[dict[str, str]] = []
        next_shared_meta: dict[str, dict[str, Any]] = {}
        next_system_meta: dict[str, dict[str, Any]] = {}
        desired_secret_keys: set[str] = set()

        for item in variables:
            entry = _safe_json_object(item)
            key = _normalize_env_entry_key(entry.get("key"))
            if not key:
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

        template_keys = {
            str(field["key"])
            for template in _GENERAL_INTEGRATION_CREDENTIAL_TEMPLATES.values()
            for field in template["fields"]
        }
        existing_secrets = {item["secret_key"] for item in self._current_global_secrets(sections=sections)}
        for integration_key, template in _GENERAL_INTEGRATION_CREDENTIAL_TEMPLATES.items():
            payload_fields = _safe_json_object(integration_credentials.get(integration_key))
            provided_fields = {
                str(_safe_json_object(field).get("key")): _safe_json_object(field)
                for field in _safe_json_list(payload_fields.get("fields"))
            }
            for field in template["fields"]:
                env_key = str(field["key"])
                entry = provided_fields.get(env_key, {})
                if str(field["storage"]) == "secret":
                    desired_secret_keys.add(env_key)
                    global_secret_meta[env_key] = {
                        "description": f"Credencial global de {template['title']}",
                        "usage_scope": "system_only",
                    }
                    if bool(entry.get("clear")):
                        global_secret_meta.pop(env_key, None)
                        self.delete_global_secret_asset(env_key, persist_sections=False)
                        continue
                    value = _nonempty_text(entry.get("value"))
                    if value:
                        self.upsert_global_secret_asset(
                            env_key,
                            {
                                "value": value,
                                "description": f"Credencial global de {template['title']}",
                                "usage_scope": "system_only",
                            },
                            persist_sections=False,
                        )
                    elif env_key in existing_secrets:
                        continue
                else:
                    value = _nonempty_text(entry.get("value"))
                    if value:
                        custom_system_variables.append({"key": env_key, "value": value})
                        next_system_meta[env_key] = {"description": f"Configuração global de {template['title']}"}

        for secret in self._current_global_secrets(sections=sections):
            secret_key = str(secret["secret_key"])
            if secret_key in template_keys and secret_key not in desired_secret_keys:
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
            "preview": str(row["preview"] or ""),
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
                "preview": str(row["preview"] or ""),
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
            "preview": str(row["preview"] or ""),
            "updated_at": str(row["updated_at"] or ""),
        }

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
        runtime_endpoint.update(_safe_json_object(json_load(agent_row["runtime_endpoint_json"], {})))
        appearance = _safe_json_object(json_load(agent_row["appearance_json"], {}))
        appearance.setdefault("label", str(agent_row["display_name"]))
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

        runtime_env = dict(self._merged_global_env())
        runtime_env.update(
            {key: _stringify_env_value(value) for key, value in _safe_json_object(snapshot.get("env")).items()}
        )
        runtime_env.update(self._provider_connection_env())
        runtime_snapshot = dict(snapshot)
        runtime_snapshot["env"] = runtime_env

        agent_spec = self.get_agent_spec(normalized, snapshot=runtime_snapshot)
        docs = _safe_json_object(agent_spec.get("documents"))
        composed_prompt = _compose_agent_prompt(docs)

        inline_documents: dict[str, str] = {}
        for kind in _RUNTIME_INLINE_DOCUMENT_KINDS:
            content = _trimmed_text(docs.get(kind))
            if not content:
                continue
            inline_documents[kind] = content

        skills = [asset for asset in _safe_json_list(snapshot.get("skills")) if str(asset.get("content") or "").strip()]
        skills_payload = {str(asset["name"]): str(asset["content"]).strip() for asset in skills}

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
        if audio_provider == "elevenlabs" and (
            not elevenlabs_ready or (not elevenlabs_enabled and not elevenlabs_default_voice)
        ):
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
        if elevenlabs_default_voice and elevenlabs_ready and (audio_provider == "elevenlabs" or not elevenlabs_enabled):
            env["TTS_DEFAULT_VOICE"] = elevenlabs_default_voice
        else:
            env["TTS_DEFAULT_VOICE"] = kokoro_default_voice
        try:
            env["KOKORO_VOICES_PATH"] = str(kokoro_managed_voices_path())
        except Exception:
            log.warning("control_plane_kokoro_assets_unavailable", agent_id=normalized, exc_info=True)
        if _safe_json_object(agent_spec.get("tool_policy")) and "AGENT_TOOL_POLICY_JSON" not in env:
            env["AGENT_TOOL_POLICY_JSON"] = json_dump(agent_spec["tool_policy"])
        if _safe_json_object(agent_spec.get("model_policy")) and "AGENT_MODEL_POLICY_JSON" not in env:
            env["AGENT_MODEL_POLICY_JSON"] = json_dump(agent_spec["model_policy"])
        if _safe_json_object(agent_spec.get("autonomy_policy")) and "AGENT_AUTONOMY_POLICY_JSON" not in env:
            env["AGENT_AUTONOMY_POLICY_JSON"] = json_dump(agent_spec["autonomy_policy"])
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
            encrypted_value = str(_safe_json_object(secret_payload).get("encrypted_value") or "").strip()
            if not encrypted_value:
                continue
            env[secret_key] = decrypt_secret(encrypted_value)
        env["CONTROL_PLANE_RUNTIME_INLINE"] = "true" if inline_mode else "false"
        if composed_prompt:
            env["AGENT_COMPILED_PROMPT_TEXT"] = composed_prompt
        if inline_mode:
            if skills_payload:
                env["SKILLS_JSON"] = json.dumps(skills_payload, ensure_ascii=False)
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
            env=self._scoped_env(normalized, env),
            health_url=health_url,
            runtime_base_url=runtime_base_url,
            state_backend=STATE_BACKEND,
            db_file_name=db_file_name,
            persisted_to_disk=persisted_to_disk,
        )

    def get_runtime_access(self, agent_id: str) -> dict[str, Any]:
        normalized, agent_row = self._require_agent_row(agent_id)
        from koda.services.runtime_access_service import RuntimeAccessService

        applied_version = int(agent_row["applied_version"] or 0)
        desired_version = int(agent_row["desired_version"] or 0)
        selected_version = applied_version or desired_version

        snapshot_candidate = (
            self.get_published_snapshot(normalized, version=selected_version)
            if selected_version > 0
            else self.build_draft_snapshot(normalized)
        )
        snapshot = snapshot_candidate or self.build_draft_snapshot(normalized)
        agent_payload = _safe_json_object(snapshot.get("agent"))
        runtime_endpoint = _safe_json_object(agent_payload.get("runtime_endpoint"))
        health_url = str(
            runtime_endpoint.get("health_url")
            or f"http://127.0.0.1:{runtime_endpoint.get('health_port') or 8080}/health"
        )
        runtime_base_url = str(
            runtime_endpoint.get("runtime_base_url") or health_url.removesuffix("/health").rstrip("/")
        )
        secrets = _safe_json_object(snapshot.get("secrets"))
        runtime_token = ""
        for candidate in ("RUNTIME_LOCAL_UI_TOKEN", "RUNTIME_TOKEN"):
            payload = _safe_json_object(secrets.get(candidate))
            encrypted_value = str(payload.get("encrypted_value") or "").strip()
            if encrypted_value:
                runtime_token = decrypt_secret(encrypted_value)
                break
        if not runtime_token:
            for candidate in ("RUNTIME_LOCAL_UI_TOKEN", "RUNTIME_TOKEN"):
                row = fetch_one(
                    "SELECT encrypted_value FROM cp_secret_values WHERE scope_id = 'global' AND secret_key = ?",
                    (candidate,),
                )
                encrypted_value = str(row["encrypted_value"] or "").strip() if row else ""
                if encrypted_value:
                    runtime_token = decrypt_secret(encrypted_value)
                    break
        sections = _safe_json_object(snapshot.get("sections"))
        knowledge_section = _safe_json_object(sections.get("knowledge"))
        knowledge_policy = normalize_knowledge_policy(_safe_json_object(knowledge_section.get("policy")))
        workspace_scope = tuple(
            item
            for item in [str(agent_row["workspace_id"]).strip() if _row_has_column(agent_row, "workspace_id") else ""]
            if item
        )
        source_scope = tuple(normalize_string_list(knowledge_policy.get("allowed_source_labels")))
        access_scope = {
            "agent_scope": normalized,
            "workspace_scope": list(workspace_scope),
            "source_scope": list(source_scope),
            "sensitive_allowed": bool(runtime_token),
        }
        access_scope_token = None
        access_scope_expires_at = None
        if runtime_token:
            envelope, access_scope_token = RuntimeAccessService(runtime_token).issue(
                agent_scope=normalized,
                workspace_scope=workspace_scope,
                source_scope=source_scope,
                sensitive_allowed=True,
            )
            access_scope_expires_at = envelope.expires_at

        return {
            "agent_id": normalized,
            "applied_version": applied_version or None,
            "desired_version": desired_version or None,
            "selected_version": selected_version or None,
            "health_url": health_url,
            "runtime_base_url": runtime_base_url,
            "runtime_token": runtime_token or None,
            "runtime_token_present": bool(runtime_token),
            "access_scope": access_scope,
            "access_scope_token": access_scope_token,
            "access_scope_expires_at": access_scope_expires_at,
        }

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

            if existing_agent_ids or target_agent_ids:
                self._import_legacy_skills()

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

    def _load_global_sections(self) -> dict[str, dict[str, Any]]:
        rows = fetch_all("SELECT section, data_json, updated_at FROM cp_global_sections ORDER BY section ASC")
        return {str(row["section"]): json_load(row["data_json"], {}) for row in rows}

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
            key.startswith("JIRA_")
            or key.startswith("CONFLUENCE_")
            or key.startswith("AWS_")
            or key.startswith("POSTGRES_")
            or key.startswith("GWS_")
            or key.startswith("GH_")
            or key.startswith("GLAB_")
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

    def _import_legacy_skills(self) -> None:
        skills_dir = ROOT_DIR / "koda" / "skills"
        if not skills_dir.exists():
            return
        seed_agent = "DEFAULT"
        if not fetch_one("SELECT id FROM cp_agent_definitions WHERE id = ?", (seed_agent,)):
            # Do not create an actual agent for skill seeding; use the first agent as scope carrier.
            row = fetch_one("SELECT id FROM cp_agent_definitions ORDER BY id ASC LIMIT 1")
            if row is not None:
                seed_agent = str(row["id"])
            else:
                return
        for path in skills_dir.glob("*.md"):
            self.upsert_skill_asset(
                seed_agent,
                {
                    "scope": "global",
                    "name": path.stem,
                    "content": path.read_text(encoding="utf-8"),
                },
            )


_MANAGER: ControlPlaneManager | None = None


def get_control_plane_manager() -> ControlPlaneManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = ControlPlaneManager()
    return _MANAGER
