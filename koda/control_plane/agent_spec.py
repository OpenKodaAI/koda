"""Typed agent-spec helpers, markdown projections, and validation."""

from __future__ import annotations

import json
import string
from typing import Any

from koda.agent_contract import (
    APPROVAL_MODES,
    AUTONOMY_TIERS,
    CORE_PROVIDER_CATALOG,
    CORE_PROVIDER_IDS,
    CORE_TOOL_CATALOG,
    PROMOTION_MODES,
    normalize_string_list,
    resolve_allowed_tool_ids,
    tool_subset_summary,
)
from koda.control_plane.settings import looks_like_secret_key
from koda.provider_models import MODEL_FUNCTION_IDS, build_function_model_catalog

_ALLOWED_MEMORY_EXTRACTION_FIELDS = frozenset({"query", "response", "max_items"})
_ALLOWED_KNOWLEDGE_LAYERS = frozenset({"canonical_policy", "approved_runbook", "workspace_doc", "observed_pattern"})
_KNOWLEDGE_LAYER_ALIASES = {
    "canonical_knowledge": "canonical_policy",
    "approved_runbooks": "approved_runbook",
    "workspace_docs": "workspace_doc",
    "observed_patterns": "observed_pattern",
}
_AGENT_DOCUMENT_LAYOUT: tuple[tuple[str, str], ...] = (
    ("identity_md", "agent_identity"),
    ("soul_md", "agent_interaction_style"),
    ("system_prompt_md", "agent_response_policy"),
    ("instructions_md", "agent_operating_instructions"),
    ("rules_md", "agent_hard_rules"),
)
_AGENT_DOCUMENT_LAYOUT_INDEX = {kind: index for index, (kind, _) in enumerate(_AGENT_DOCUMENT_LAYOUT)}
_AGENT_DOCUMENT_RUNTIME_TAGS = {kind: tag for kind, tag in _AGENT_DOCUMENT_LAYOUT}
_DOCUMENT_KINDS: tuple[str, ...] = (
    "identity_md",
    "soul_md",
    "system_prompt_md",
    "instructions_md",
    "rules_md",
    "voice_prompt_md",
    "image_prompt_md",
    "memory_extraction_prompt_md",
)
_BOOLEAN_MEMORY_POLICY_FIELDS = frozenset(
    {
        "enabled",
        "proactive_enabled",
        "procedural_enabled",
        "maintenance_enabled",
        "digest_enabled",
    }
)
_NUMERIC_MEMORY_POLICY_FIELDS = frozenset(
    {
        "max_recall",
        "max_context_tokens",
        "max_extraction_items",
        "procedural_max_recall",
        "recall_timeout",
        "max_per_user",
        "recall_threshold",
        "recency_half_life_days",
        "similarity_dedup_threshold",
    }
)
_BOOLEAN_KNOWLEDGE_POLICY_FIELDS = frozenset(
    {
        "enabled",
        "require_owner_provenance",
        "require_freshness_provenance",
        "graph_enabled",
        "multimodal_graph_enabled",
        "v2_enabled",
    }
)
_NUMERIC_KNOWLEDGE_POLICY_FIELDS = frozenset(
    {
        "max_results",
        "recall_threshold",
        "recall_timeout",
        "context_max_tokens",
        "workspace_max_files",
        "max_observed_patterns",
        "max_source_age_days",
        "trace_sampling_rate",
        "evaluation_sampling_rate",
        "v2_max_graph_hops",
    }
)
_RESOURCE_ACCESS_POLICY_KEYS = frozenset(
    {
        "allowed_global_secret_keys",
        "allowed_shared_env_keys",
        "local_env",
    }
)
_RESERVED_LOCAL_ENV_PREFIXES = (
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
_GENERAL_PROVIDER_IDS = frozenset(
    provider_id for provider_id, definition in CORE_PROVIDER_CATALOG.items() if definition.category == "general"
)


def _safe_json_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_json_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _trimmed(value: Any) -> str:
    return str(value or "").strip()


def _normalize_markdown_block(value: Any) -> str:
    return _trimmed(value)


def _as_bool(value: Any, default: bool | None = None) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return default


def _as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _compact_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    compacted: dict[str, Any] = {}
    for key, value in mapping.items():
        if isinstance(value, dict):
            nested = _compact_mapping(value)
            if nested:
                compacted[key] = nested
            continue
        if isinstance(value, list):
            normalized_list = [item for item in value if item not in ("", None)]
            if normalized_list:
                compacted[key] = normalized_list
            continue
        if value in ("", None):
            continue
        compacted[key] = value
    return compacted


def _normalize_knowledge_layer(value: Any) -> str:
    normalized = _trimmed(value).lower()
    return _KNOWLEDGE_LAYER_ALIASES.get(normalized, normalized)


def _normalize_env_key(value: Any) -> str:
    text = _trimmed(value).upper()
    if not text:
        return ""
    return "".join(char if char.isalnum() or char == "_" else "_" for char in text).strip("_")


def _normalize_env_key_list(value: Any) -> list[str]:
    result: list[str] = []
    for item in normalize_string_list(value):
        normalized = _normalize_env_key(item)
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _normalize_env_mapping(value: Any) -> dict[str, str]:
    payload = _safe_json_object(value)
    normalized: dict[str, str] = {}
    for key, raw_value in payload.items():
        env_key = _normalize_env_key(key)
        if not env_key:
            continue
        text = _trimmed(raw_value)
        if text:
            normalized[env_key] = text
    return normalized


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        lines = [line.strip("- ").strip() for line in value.splitlines()]
        return [line for line in lines if line]
    return normalize_string_list(value)


def _render_section(title: str, mapping: dict[str, Any], *, order: tuple[str, ...] = ()) -> str:
    lines: list[str] = [f"# {title}"]
    ordered_keys = [key for key in order if key in mapping]
    ordered_keys.extend(key for key in mapping if key not in ordered_keys)

    for key in ordered_keys:
        raw = mapping.get(key)
        if raw in (None, "", [], {}):
            continue
        label = key.replace("_", " ").strip().title()
        if isinstance(raw, dict):
            nested = _render_section(label, raw)
            lines.extend(["", nested])
            continue
        if isinstance(raw, list):
            lines.extend(["", f"## {label}"])
            lines.extend(f"- {item}" for item in _as_list(raw))
            continue
        lines.extend(["", f"## {label}", _trimmed(raw)])
    return "\n".join(lines).strip()


def render_markdown_documents_from_agent_spec(agent_spec: dict[str, Any]) -> dict[str, str]:
    """Project the typed agent spec into editable markdown behavior layers."""
    mission_profile = _safe_json_object(agent_spec.get("mission_profile"))
    interaction_style = _safe_json_object(agent_spec.get("interaction_style"))
    operating_instructions = _safe_json_object(agent_spec.get("operating_instructions"))
    hard_rules = _safe_json_object(agent_spec.get("hard_rules"))
    response_policy = _safe_json_object(agent_spec.get("response_policy"))
    voice_policy = _safe_json_object(agent_spec.get("voice_policy"))
    image_analysis_policy = _safe_json_object(agent_spec.get("image_analysis_policy"))
    memory_extraction_schema = _safe_json_object(agent_spec.get("memory_extraction_schema"))

    rendered = {
        "identity_md": _render_section(
            "Mission Profile",
            mission_profile,
            order=("mission", "role", "audience", "primary_outcomes", "kpis", "responsibility_limits"),
        )
        if mission_profile
        else "",
        "soul_md": _render_section(
            "Interaction Style",
            interaction_style,
            order=("tone", "persona", "values", "collaboration_style", "writing_style", "escalation_style"),
        )
        if interaction_style
        else "",
        "instructions_md": _render_section(
            "Operating Instructions",
            operating_instructions,
            order=("default_workflow", "execution_heuristics", "success_criteria", "handoff_expectations"),
        )
        if operating_instructions
        else "",
        "rules_md": _render_section(
            "Hard Rules",
            hard_rules,
            order=("non_negotiables", "forbidden_actions", "approval_requirements", "security_rules"),
        )
        if hard_rules
        else "",
        "system_prompt_md": _render_section(
            "Response Policy",
            response_policy,
            order=("language", "format", "citation_policy", "source_policy", "conciseness", "quality_bar"),
        )
        if response_policy
        else "",
        "voice_prompt_md": _render_section(
            "Voice Policy",
            voice_policy,
            order=("mode", "style", "duration_target", "tts_notes"),
        )
        if voice_policy
        else "",
        "image_prompt_md": _render_section(
            "Image Analysis Policy",
            image_analysis_policy,
            order=("fallback_behavior", "analysis_priorities", "safety_notes"),
        )
        if image_analysis_policy
        else "",
        "memory_extraction_prompt_md": _trimmed(
            memory_extraction_schema.get("template") or memory_extraction_schema.get("content_md")
        ),
    }
    return {key: value for key, value in rendered.items() if value}


def merge_agent_documents(
    typed_projection: dict[str, str],
    explicit_documents: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Merge typed projections with any explicit markdown overrides."""
    merged = dict(typed_projection)
    for kind, value in _safe_json_object(explicit_documents).items():
        content = _normalize_markdown_block(value)
        if content:
            merged[kind] = content
    return merged


def resolve_agent_documents(agent_spec: dict[str, Any]) -> dict[str, Any]:
    """Resolve projections, explicit overrides, and effective document sources."""
    projections = render_markdown_documents_from_agent_spec(agent_spec)
    overrides: dict[str, str] = {}
    for kind, value in _safe_json_object(agent_spec.get("documents")).items():
        if kind not in _DOCUMENT_KINDS:
            continue
        normalized = _normalize_markdown_block(value)
        if not normalized:
            continue
        if normalized == projections.get(kind, ""):
            continue
        overrides[kind] = normalized
    effective = merge_agent_documents(projections, overrides)
    sources: dict[str, dict[str, Any]] = {}
    for kind in _DOCUMENT_KINDS:
        projection = projections.get(kind, "")
        override = overrides.get(kind, "")
        final_value = effective.get(kind, "")
        sources[kind] = {
            "mode": "override" if override else "projection" if projection else "unset",
            "affects_prompt": kind in {name for name, _ in _AGENT_DOCUMENT_LAYOUT} and bool(final_value),
            "affects_runtime": kind in {"voice_prompt_md", "image_prompt_md", "memory_extraction_prompt_md"}
            and bool(final_value),
            "runtime_tag": _AGENT_DOCUMENT_RUNTIME_TAGS.get(kind),
            "prompt_order": _AGENT_DOCUMENT_LAYOUT_INDEX.get(kind),
            "projection_length": len(projection),
            "override_length": len(override),
            "effective_length": len(final_value),
        }
    return {
        "projections": projections,
        "overrides": overrides,
        "effective": effective,
        "sources": sources,
    }


def iter_agent_prompt_blocks(documents: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Return prompt-ready agent contract blocks using the runtime order and tags."""
    blocks: list[tuple[str, str, str]] = []
    for kind, tag in _AGENT_DOCUMENT_LAYOUT:
        content = _trimmed(_safe_json_object(documents).get(kind) if isinstance(documents, dict) else "")
        if not content and isinstance(documents, dict):
            content = _trimmed(documents.get(kind))
        if not content:
            continue
        blocks.append((kind, tag, content))
    return blocks


def compose_agent_prompt(documents: dict[str, Any]) -> str:
    """Compose the published agent-local contract prompt from markdown layers."""
    blocks = [f"<{tag}>\n{content}\n</{tag}>" for _, tag, content in iter_agent_prompt_blocks(documents)]
    if not blocks:
        return ""

    header = [
        "<agent_configuration_contract>",
        "These are the published agent-local mission, interaction, operating, hard-rule, and response-policy layers.",
        "Platform safety, provider compatibility, and runtime guardrails remain authoritative on conflict.",
        "</agent_configuration_contract>",
    ]
    return "\n\n".join([*header, *blocks]).strip()


def _normalize_provider_models(value: Any) -> dict[str, list[str]]:
    payload = _safe_json_object(value)
    normalized: dict[str, list[str]] = {}
    for provider, models in payload.items():
        provider_id = _trimmed(provider).lower()
        model_list = normalize_string_list(models)
        if provider_id and model_list:
            normalized[provider_id] = model_list
    return normalized


def _normalize_default_models(value: Any) -> dict[str, str]:
    payload = _safe_json_object(value)
    normalized: dict[str, str] = {}
    for provider, model in payload.items():
        provider_id = _trimmed(provider).lower()
        model_id = _trimmed(model)
        if provider_id and model_id:
            normalized[provider_id] = model_id
    return normalized


def _normalize_tier_models(value: Any) -> dict[str, dict[str, str]]:
    payload = _safe_json_object(value)
    normalized: dict[str, dict[str, str]] = {}
    for provider, tiers in payload.items():
        provider_id = _trimmed(provider).lower()
        tier_payload = _safe_json_object(tiers)
        normalized_tiers = {
            tier: _trimmed(tier_payload.get(tier))
            for tier in ("small", "medium", "large")
            if _trimmed(tier_payload.get(tier))
        }
        if provider_id and normalized_tiers:
            normalized[provider_id] = normalized_tiers
    return normalized


def _normalize_functional_defaults(value: Any) -> dict[str, dict[str, str]]:
    payload = _safe_json_object(value)
    normalized: dict[str, dict[str, str]] = {}
    for function_id, selection in payload.items():
        function_key = _trimmed(function_id).lower()
        if function_key not in MODEL_FUNCTION_IDS:
            continue
        item = _safe_json_object(selection)
        provider_id = _trimmed(item.get("provider_id")).lower()
        model_id = _trimmed(item.get("model_id"))
        if provider_id and model_id:
            normalized[function_key] = {
                "provider_id": provider_id,
                "model_id": model_id,
            }
    return normalized


def normalize_model_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(_safe_json_object(policy))
    if not raw:
        return {}

    allowed_providers = [provider.lower() for provider in normalize_string_list(raw.get("allowed_providers"))]
    fallback_order = [provider.lower() for provider in normalize_string_list(raw.get("fallback_order"))]
    default_provider = _trimmed(raw.get("default_provider")).lower()

    if allowed_providers:
        raw["allowed_providers"] = allowed_providers
    if fallback_order:
        raw["fallback_order"] = fallback_order
    if default_provider:
        raw["default_provider"] = default_provider

    available_models = _normalize_provider_models(raw.get("available_models_by_provider"))
    if available_models:
        raw["available_models_by_provider"] = available_models

    default_models = _normalize_default_models(raw.get("default_models"))
    if default_models:
        raw["default_models"] = default_models

    tier_models = _normalize_tier_models(raw.get("tier_models"))
    if tier_models:
        raw["tier_models"] = tier_models
    functional_defaults = _normalize_functional_defaults(raw.get("functional_defaults"))
    if functional_defaults:
        raw["functional_defaults"] = functional_defaults

    max_budget = _as_float(raw.get("max_budget_usd"))
    if max_budget is not None:
        raw["max_budget_usd"] = max_budget
    max_total_budget = _as_float(raw.get("max_total_budget_usd"))
    if max_total_budget is not None:
        raw["max_total_budget_usd"] = max_total_budget
    return _compact_mapping(raw)


def normalize_tool_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(_safe_json_object(policy))
    if not raw:
        return {}
    allowed_tool_ids = normalize_string_list(raw.get("allowed_tool_ids"))
    if allowed_tool_ids:
        raw["allowed_tool_ids"] = allowed_tool_ids
    return _compact_mapping(raw)


def normalize_autonomy_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(_safe_json_object(policy))
    if not raw:
        return {}

    approval_mode = _trimmed(raw.get("default_approval_mode")).lower()
    autonomy_tier = _trimmed(raw.get("default_autonomy_tier")).lower()
    if approval_mode:
        raw["default_approval_mode"] = approval_mode
    if autonomy_tier:
        raw["default_autonomy_tier"] = autonomy_tier

    task_overrides: dict[str, Any] = {}
    for task_kind, override in _safe_json_object(raw.get("task_overrides")).items():
        if not isinstance(override, dict):
            continue
        normalized_override = dict(override)
        candidate_mode = _trimmed(normalized_override.get("approval_mode")).lower()
        candidate_tier = _trimmed(normalized_override.get("autonomy_tier")).lower()
        if candidate_mode:
            normalized_override["approval_mode"] = candidate_mode
        if candidate_tier:
            normalized_override["autonomy_tier"] = candidate_tier
        task_overrides[_trimmed(task_kind).lower() or "default"] = _compact_mapping(normalized_override)
    if task_overrides:
        raw["task_overrides"] = task_overrides
    return _compact_mapping(raw)


def normalize_memory_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(_safe_json_object(policy))
    if not raw:
        return {}

    for key in _BOOLEAN_MEMORY_POLICY_FIELDS:
        parsed = _as_bool(raw.get(key))
        if parsed is not None:
            raw[key] = parsed
    for key in _NUMERIC_MEMORY_POLICY_FIELDS:
        parsed_float = _as_float(raw.get(key))
        if parsed_float is None:
            continue
        raw[key] = int(parsed_float) if parsed_float.is_integer() else parsed_float

    extraction_provider = _trimmed(raw.get("extraction_provider")).lower()
    extraction_model = _trimmed(raw.get("extraction_model"))
    if extraction_provider:
        raw["extraction_provider"] = extraction_provider
    if extraction_model:
        raw["extraction_model"] = extraction_model

    profile = dict(_safe_json_object(raw.get("profile")))
    if profile:
        for key in ("focus_domains", "preferred_layers", "forbidden_layers_for_actions", "ignored_patterns"):
            normalized_list = normalize_string_list(profile.get(key))
            if normalized_list:
                profile[key] = normalized_list
        for key in ("risk_posture", "memory_density_target"):
            value = _trimmed(profile.get(key))
            if value:
                profile[key] = value
        for key in ("max_items_per_turn",):
            parsed_int = _as_int(profile.get(key))
            if parsed_int is not None:
                profile[key] = parsed_int
        promotion_policy = _safe_json_object(profile.get("promotion_policy"))
        if promotion_policy:
            parsed_requires_review = _as_bool(promotion_policy.get("observed_pattern_requires_review"))
            if parsed_requires_review is not None:
                promotion_policy["observed_pattern_requires_review"] = parsed_requires_review
            parsed_verified_successes = _as_int(promotion_policy.get("minimum_verified_successes"))
            if parsed_verified_successes is not None:
                promotion_policy["minimum_verified_successes"] = parsed_verified_successes
            profile["promotion_policy"] = _compact_mapping(promotion_policy)
        raw["profile"] = _compact_mapping(profile)

    promotion_mode = _trimmed(raw.get("promotion_mode")).lower()
    if promotion_mode:
        raw["promotion_mode"] = promotion_mode
    for key in ("strategy_default", "citation_policy"):
        value = _trimmed(raw.get(key)).lower()
        if value:
            raw[key] = value
    return _compact_mapping(raw)


def normalize_knowledge_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(_safe_json_object(policy))
    if not raw:
        return {}

    for key in _BOOLEAN_KNOWLEDGE_POLICY_FIELDS:
        parsed = _as_bool(raw.get(key))
        if parsed is not None:
            raw[key] = parsed
    for key in _NUMERIC_KNOWLEDGE_POLICY_FIELDS:
        parsed_float = _as_float(raw.get(key))
        if parsed_float is None:
            continue
        raw[key] = int(parsed_float) if parsed_float.is_integer() else parsed_float

    allowed_layers = [_normalize_knowledge_layer(layer) for layer in normalize_string_list(raw.get("allowed_layers"))]
    if allowed_layers:
        raw["allowed_layers"] = allowed_layers
    source_globs = normalize_string_list(raw.get("source_globs"))
    if source_globs:
        raw["source_globs"] = source_globs
    workspace_source_globs = normalize_string_list(raw.get("workspace_source_globs"))
    if workspace_source_globs:
        raw["workspace_source_globs"] = workspace_source_globs
    allowed_source_labels = normalize_string_list(raw.get("allowed_source_labels"))
    if allowed_source_labels:
        raw["allowed_source_labels"] = allowed_source_labels
    allowed_workspace_roots = normalize_string_list(raw.get("allowed_workspace_roots"))
    if allowed_workspace_roots:
        raw["allowed_workspace_roots"] = allowed_workspace_roots
    promotion_mode = _trimmed(raw.get("promotion_mode")).lower()
    if promotion_mode:
        raw["promotion_mode"] = promotion_mode
    for key in ("strategy_default", "citation_policy", "storage_mode"):
        value = _trimmed(raw.get(key)).lower()
        if value:
            raw[key] = value
    for key in ("cross_encoder_model", "object_store_root"):
        value = _trimmed(raw.get(key))
        if value:
            raw[key] = value
    return _compact_mapping(raw)


def normalize_resource_access_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(_safe_json_object(policy))
    if not raw:
        return {}

    allowed_global_secret_keys = _normalize_env_key_list(raw.get("allowed_global_secret_keys"))
    allowed_shared_env_keys = _normalize_env_key_list(raw.get("allowed_shared_env_keys"))
    local_env = _normalize_env_mapping(raw.get("local_env"))

    normalized: dict[str, Any] = {}
    if allowed_global_secret_keys:
        normalized["allowed_global_secret_keys"] = allowed_global_secret_keys
    if allowed_shared_env_keys:
        normalized["allowed_shared_env_keys"] = allowed_shared_env_keys
    if local_env:
        normalized["local_env"] = local_env
    return normalized


def normalize_agent_spec(agent_spec: dict[str, Any]) -> dict[str, Any]:
    """Return a normalized, runtime-ready AgentSpec payload."""
    normalized = {
        "agent_id": _trimmed(agent_spec.get("agent_id")),
        "mission_profile": _compact_mapping(_safe_json_object(agent_spec.get("mission_profile"))),
        "interaction_style": _compact_mapping(_safe_json_object(agent_spec.get("interaction_style"))),
        "operating_instructions": _compact_mapping(_safe_json_object(agent_spec.get("operating_instructions"))),
        "hard_rules": _compact_mapping(_safe_json_object(agent_spec.get("hard_rules"))),
        "response_policy": _compact_mapping(_safe_json_object(agent_spec.get("response_policy"))),
        "model_policy": normalize_model_policy(_safe_json_object(agent_spec.get("model_policy"))),
        "tool_policy": normalize_tool_policy(_safe_json_object(agent_spec.get("tool_policy"))),
        "memory_policy": normalize_memory_policy(_safe_json_object(agent_spec.get("memory_policy"))),
        "knowledge_policy": normalize_knowledge_policy(_safe_json_object(agent_spec.get("knowledge_policy"))),
        "autonomy_policy": normalize_autonomy_policy(_safe_json_object(agent_spec.get("autonomy_policy"))),
        "resource_access_policy": normalize_resource_access_policy(
            _safe_json_object(agent_spec.get("resource_access_policy"))
        ),
        "voice_policy": _compact_mapping(_safe_json_object(agent_spec.get("voice_policy"))),
        "image_analysis_policy": _compact_mapping(_safe_json_object(agent_spec.get("image_analysis_policy"))),
        "memory_extraction_schema": _compact_mapping(_safe_json_object(agent_spec.get("memory_extraction_schema"))),
        "documents": {
            kind: _normalize_markdown_block(value)
            for kind, value in _safe_json_object(agent_spec.get("documents")).items()
            if kind in _DOCUMENT_KINDS and _normalize_markdown_block(value)
        },
    }
    return _compact_mapping(normalized)


def build_agent_spec_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Derive a typed agent spec from the current draft or published snapshot."""
    sections = _safe_json_object(snapshot.get("sections"))
    identity = _safe_json_object(sections.get("identity"))
    prompting = _safe_json_object(sections.get("prompting"))
    providers = _safe_json_object(sections.get("providers"))
    tools = _safe_json_object(sections.get("tools"))
    access = _safe_json_object(sections.get("access"))
    memory = _safe_json_object(sections.get("memory"))
    knowledge = _safe_json_object(sections.get("knowledge"))
    runtime = _safe_json_object(sections.get("runtime"))
    documents = {
        key: _trimmed(value) for key, value in _safe_json_object(snapshot.get("documents")).items() if _trimmed(value)
    }

    return normalize_agent_spec(
        {
            "agent_id": _trimmed(_safe_json_object(snapshot.get("agent")).get("id")),
            "mission_profile": _safe_json_object(identity.get("mission_profile")),
            "interaction_style": _safe_json_object(identity.get("interaction_style")),
            "operating_instructions": _safe_json_object(prompting.get("operating_instructions")),
            "hard_rules": _safe_json_object(prompting.get("hard_rules")),
            "response_policy": _safe_json_object(prompting.get("response_policy")),
            "model_policy": _safe_json_object(providers.get("model_policy")),
            "tool_policy": _safe_json_object(tools.get("tool_policy")),
            "resource_access_policy": _safe_json_object(access.get("resource_access_policy")),
            "memory_policy": _safe_json_object(memory.get("policy")) or _safe_json_object(memory.get("profile")),
            "knowledge_policy": _safe_json_object(knowledge.get("policy")) or knowledge,
            "autonomy_policy": _safe_json_object(runtime.get("autonomy_policy")),
            "voice_policy": _safe_json_object(prompting.get("voice_policy")),
            "image_analysis_policy": _safe_json_object(prompting.get("image_analysis_policy")),
            "memory_extraction_schema": _safe_json_object(memory.get("memory_extraction_schema")),
            "documents": documents,
        }
    )


def _formatter_fields(template: str) -> set[str]:
    fields: set[str] = set()
    formatter = string.Formatter()
    for _, field_name, _, _ in formatter.parse(template):
        if field_name:
            fields.add(field_name)
    return fields


def _positive_number_warning(name: str, value: Any, *, allow_zero: bool = False) -> str | None:
    parsed = _as_float(value)
    if parsed is None:
        return None
    if allow_zero and parsed >= 0:
        return None
    if parsed > 0:
        return None
    return f"{name} must be greater than {'or equal to ' if allow_zero else ''}0."


def validate_agent_spec(
    agent_spec: dict[str, Any],
    *,
    feature_flags: dict[str, bool] | None = None,
    available_models_by_provider: dict[str, list[str]] | None = None,
    enabled_providers: list[str] | None = None,
) -> dict[str, Any]:
    """Validate typed config, markdown projections, and publish safety rules."""
    normalized_spec = normalize_agent_spec(agent_spec)
    errors: list[str] = []
    warnings: list[str] = []

    mission_profile = _safe_json_object(normalized_spec.get("mission_profile"))
    interaction_style = _safe_json_object(normalized_spec.get("interaction_style"))
    operating_instructions = _safe_json_object(normalized_spec.get("operating_instructions"))
    hard_rules = _safe_json_object(normalized_spec.get("hard_rules"))
    response_policy = _safe_json_object(normalized_spec.get("response_policy"))
    model_policy = _safe_json_object(normalized_spec.get("model_policy"))
    tool_policy = _safe_json_object(normalized_spec.get("tool_policy"))
    memory_policy = _safe_json_object(normalized_spec.get("memory_policy"))
    knowledge_policy = _safe_json_object(normalized_spec.get("knowledge_policy"))
    autonomy_policy = _safe_json_object(normalized_spec.get("autonomy_policy"))
    resource_access_policy = _safe_json_object(normalized_spec.get("resource_access_policy"))
    memory_extraction_schema = _safe_json_object(normalized_spec.get("memory_extraction_schema"))

    documents_state = resolve_agent_documents(normalized_spec)
    documents = _safe_json_object(documents_state.get("effective"))
    compiled_prompt = compose_agent_prompt(documents)

    if not any(documents.get(kind) for kind, _ in _AGENT_DOCUMENT_LAYOUT):
        warnings.append("No mission/style/instructions/rules/system documents are set for this agent.")
    if mission_profile and not _trimmed(mission_profile.get("mission")):
        warnings.append("mission_profile.mission is empty.")
    if interaction_style and not any(_trimmed(value) for value in interaction_style.values()):
        warnings.append("interaction_style is present but empty.")
    if hard_rules and not any(
        _safe_json_list(hard_rules.get(key)) or _trimmed(hard_rules.get(key)) for key in hard_rules
    ):
        warnings.append("hard_rules is present but empty.")
    if response_policy and not any(_trimmed(value) or _safe_json_list(value) for value in response_policy.values()):
        warnings.append("response_policy is present but empty.")

    available_models = {
        provider.lower(): list(models) for provider, models in (available_models_by_provider or {}).items()
    }
    enabled_provider_set = {provider.lower() for provider in (enabled_providers or available_models.keys())}
    provider_universe = enabled_provider_set or set(CORE_PROVIDER_IDS)
    function_model_options = build_function_model_catalog(
        {
            provider: {
                "title": provider,
                "vendor": provider,
                "category": "general",
                "enabled": provider in provider_universe,
                "command_present": True,
                "available_models": available_models.get(provider, []),
            }
            for provider in CORE_PROVIDER_IDS
        }
    )

    if model_policy:
        allowed_providers = [
            provider.lower() for provider in normalize_string_list(model_policy.get("allowed_providers"))
        ]
        non_general_allowed = [provider for provider in allowed_providers if provider not in _GENERAL_PROVIDER_IDS]
        if non_general_allowed:
            errors.append(
                "model_policy.allowed_providers only accepts general reasoning providers: "
                + ", ".join(non_general_allowed)
            )
        invalid_allowed = [provider for provider in allowed_providers if provider not in CORE_PROVIDER_IDS]
        if invalid_allowed:
            errors.append(f"model_policy.allowed_providers contains unknown providers: {', '.join(invalid_allowed)}")
        unavailable = [provider for provider in allowed_providers if provider not in provider_universe]
        if unavailable:
            errors.append(f"model_policy.allowed_providers contains unavailable providers: {', '.join(unavailable)}")

        default_provider = _trimmed(model_policy.get("default_provider")).lower()
        if default_provider and default_provider not in CORE_PROVIDER_IDS:
            errors.append(f"model_policy.default_provider is invalid: {default_provider}")
        if default_provider and default_provider not in _GENERAL_PROVIDER_IDS:
            errors.append("model_policy.default_provider must reference a general reasoning provider.")
        if default_provider and allowed_providers and default_provider not in allowed_providers:
            errors.append("model_policy.default_provider must be included in allowed_providers.")

        fallback_order = [provider.lower() for provider in normalize_string_list(model_policy.get("fallback_order"))]
        invalid_fallback = [provider for provider in fallback_order if provider not in CORE_PROVIDER_IDS]
        if invalid_fallback:
            errors.append(f"model_policy.fallback_order contains unknown providers: {', '.join(invalid_fallback)}")
        if allowed_providers:
            disallowed_fallback = [provider for provider in fallback_order if provider not in allowed_providers]
            if disallowed_fallback:
                errors.append(
                    "model_policy.fallback_order contains providers outside allowed_providers: "
                    + ", ".join(disallowed_fallback)
                )

        for provider, models in _normalize_provider_models(model_policy.get("available_models_by_provider")).items():
            known_models = set(available_models.get(provider.lower(), []))
            invalid_models = [model for model in models if known_models and model not in known_models]
            if invalid_models:
                errors.append(
                    f"model_policy.available_models_by_provider.{provider} contains unsupported models: "
                    + ", ".join(invalid_models)
                )

        for provider, default_model in _normalize_default_models(model_policy.get("default_models")).items():
            known_models = set(available_models.get(provider.lower(), []))
            if known_models and _trimmed(default_model) not in known_models:
                errors.append(f"model_policy.default_models.{provider} references unknown model '{default_model}'.")

        for provider, tiers in _normalize_tier_models(model_policy.get("tier_models")).items():
            known_models = set(available_models.get(provider.lower(), []))
            invalid_models = [
                model
                for model in _safe_json_object(tiers).values()
                if known_models and _trimmed(model) not in known_models
            ]
            if invalid_models:
                errors.append(
                    f"model_policy.tier_models.{provider} contains unsupported models: {', '.join(invalid_models)}"
                )

        for function_id, selection in _normalize_functional_defaults(model_policy.get("functional_defaults")).items():
            provider_id = _trimmed(selection.get("provider_id")).lower()
            model_id = _trimmed(selection.get("model_id"))
            if provider_id not in CORE_PROVIDER_IDS:
                errors.append(f"model_policy.functional_defaults.{function_id}.provider_id is invalid: {provider_id}")
                continue
            known_options = {
                (str(item.get("provider_id")).lower(), _trimmed(item.get("model_id")))
                for item in function_model_options.get(function_id, [])
            }
            if known_options and (provider_id, model_id) not in known_options:
                errors.append(
                    "model_policy.functional_defaults."
                    f"{function_id} references unknown model '{model_id}' "
                    f"for provider '{provider_id}'."
                )

        for budget_key in ("max_budget_usd", "max_total_budget_usd"):
            warning = _positive_number_warning(f"model_policy.{budget_key}", model_policy.get(budget_key))
            if warning:
                errors.append(warning)

    allowed_tool_ids = resolve_allowed_tool_ids(tool_policy, feature_flags=feature_flags)
    requested_tool_ids = normalize_string_list(tool_policy.get("allowed_tool_ids"))
    invalid_tool_ids = [tool_id for tool_id in requested_tool_ids if tool_id not in CORE_TOOL_CATALOG]
    if invalid_tool_ids:
        errors.append(f"tool_policy.allowed_tool_ids contains unknown core tools: {', '.join(invalid_tool_ids)}")
    unavailable_requested = [tool_id for tool_id in requested_tool_ids if tool_id not in allowed_tool_ids]
    if unavailable_requested:
        warnings.append(
            "tool_policy.allowed_tool_ids includes tools currently unavailable by feature flags: "
            + ", ".join(unavailable_requested)
        )

    if autonomy_policy:
        default_approval_mode = _trimmed(autonomy_policy.get("default_approval_mode")).lower()
        if default_approval_mode and default_approval_mode not in APPROVAL_MODES:
            errors.append(f"autonomy_policy.default_approval_mode is invalid: {default_approval_mode}")
        default_tier = _trimmed(autonomy_policy.get("default_autonomy_tier")).lower()
        if default_tier and default_tier not in AUTONOMY_TIERS:
            errors.append(f"autonomy_policy.default_autonomy_tier is invalid: {default_tier}")
        for task_kind, override in _safe_json_object(autonomy_policy.get("task_overrides")).items():
            candidate_mode = _trimmed(_safe_json_object(override).get("approval_mode")).lower()
            candidate_tier = _trimmed(_safe_json_object(override).get("autonomy_tier")).lower()
            if candidate_mode and candidate_mode not in APPROVAL_MODES:
                errors.append(f"autonomy_policy.task_overrides.{task_kind}.approval_mode is invalid: {candidate_mode}")
            if candidate_tier and candidate_tier not in AUTONOMY_TIERS:
                errors.append(f"autonomy_policy.task_overrides.{task_kind}.autonomy_tier is invalid: {candidate_tier}")

    if memory_policy:
        extraction_provider = _trimmed(memory_policy.get("extraction_provider")).lower()
        if extraction_provider and extraction_provider not in CORE_PROVIDER_IDS:
            errors.append(f"memory_policy.extraction_provider is invalid: {extraction_provider}")
        if extraction_provider and enabled_provider_set and extraction_provider not in enabled_provider_set:
            errors.append(
                f"memory_policy.extraction_provider references an unavailable provider: {extraction_provider}"
            )
        for numeric_key in (
            "max_recall",
            "max_context_tokens",
            "max_extraction_items",
            "procedural_max_recall",
            "recency_half_life_days",
        ):
            warning = _positive_number_warning(f"memory_policy.{numeric_key}", memory_policy.get(numeric_key))
            if warning:
                errors.append(warning)
        for bounded_key in ("recall_threshold", "similarity_dedup_threshold"):
            value = _as_float(memory_policy.get(bounded_key))
            if value is not None and not 0 <= value <= 1:
                errors.append(f"memory_policy.{bounded_key} must be between 0 and 1.")
        promotion_mode = _trimmed(memory_policy.get("promotion_mode")).lower()
        if promotion_mode and promotion_mode not in PROMOTION_MODES:
            errors.append(f"memory_policy.promotion_mode is invalid: {promotion_mode}")

    if knowledge_policy:
        invalid_layers = [
            _normalize_knowledge_layer(layer)
            for layer in normalize_string_list(agent_spec.get("knowledge_policy", {}).get("allowed_layers"))
            if _normalize_knowledge_layer(layer) not in _ALLOWED_KNOWLEDGE_LAYERS
        ]
        if invalid_layers:
            errors.append(f"knowledge_policy.allowed_layers contains invalid layers: {', '.join(invalid_layers)}")
        for numeric_key in (
            "max_results",
            "recall_timeout",
            "context_max_tokens",
            "max_source_age_days",
        ):
            warning = _positive_number_warning(
                f"knowledge_policy.{numeric_key}",
                knowledge_policy.get(numeric_key),
            )
            if warning:
                errors.append(warning)
        workspace_max_files_warning = _positive_number_warning(
            "knowledge_policy.workspace_max_files",
            knowledge_policy.get("workspace_max_files"),
            allow_zero=True,
        )
        if workspace_max_files_warning:
            errors.append(workspace_max_files_warning)
        threshold = _as_float(knowledge_policy.get("recall_threshold"))
        if threshold is not None and not 0 <= threshold <= 1:
            errors.append("knowledge_policy.recall_threshold must be between 0 and 1.")
        promotion_mode = _trimmed(knowledge_policy.get("promotion_mode")).lower()
        if promotion_mode and promotion_mode not in PROMOTION_MODES:
            errors.append(f"knowledge_policy.promotion_mode is invalid: {promotion_mode}")

    if resource_access_policy:
        unexpected_keys = sorted(key for key in resource_access_policy if key not in _RESOURCE_ACCESS_POLICY_KEYS)
        if unexpected_keys:
            warnings.append(
                "resource_access_policy contains unsupported keys that will be ignored: " + ", ".join(unexpected_keys)
            )
        for list_key in ("allowed_global_secret_keys", "allowed_shared_env_keys"):
            invalid_keys = [
                key for key in _normalize_env_key_list(resource_access_policy.get(list_key)) if not key[:1].isalpha()
            ]
            if invalid_keys:
                errors.append(f"resource_access_policy.{list_key} contains invalid environment keys.")
        local_env = _normalize_env_mapping(resource_access_policy.get("local_env"))
        if "AGENT_TOKEN" in local_env:
            errors.append("resource_access_policy.local_env cannot override AGENT_TOKEN.")
        if "RUNTIME_LOCAL_UI_TOKEN" in local_env:
            errors.append("resource_access_policy.local_env cannot override RUNTIME_LOCAL_UI_TOKEN.")
        for env_key in sorted(local_env):
            if looks_like_secret_key(env_key):
                errors.append(
                    f"resource_access_policy.local_env.{env_key} looks like a secret. Use the secrets vault instead."
                )
            if env_key.startswith(_RESERVED_LOCAL_ENV_PREFIXES):
                errors.append(f"resource_access_policy.local_env.{env_key} uses a reserved core/provider prefix.")

    if memory_extraction_schema:
        template = _trimmed(
            memory_extraction_schema.get("template")
            or memory_extraction_schema.get("content_md")
            or documents.get("memory_extraction_prompt_md")
        )
        if template:
            fields = _formatter_fields(template)
            invalid_fields = sorted(field for field in fields if field not in _ALLOWED_MEMORY_EXTRACTION_FIELDS)
            missing_fields = sorted(field for field in ("query", "response", "max_items") if field not in fields)
            if invalid_fields:
                errors.append(
                    "memory_extraction_schema contains unsupported placeholders: " + ", ".join(invalid_fields)
                )
            if missing_fields:
                warnings.append("memory_extraction_schema is missing placeholders: " + ", ".join(missing_fields))
        else:
            warnings.append("memory_extraction_schema is empty; the runtime default extraction prompt will be used.")

    sections_present = [
        name
        for name, payload in (
            ("mission_profile", mission_profile),
            ("interaction_style", interaction_style),
            ("operating_instructions", operating_instructions),
            ("hard_rules", hard_rules),
            ("response_policy", response_policy),
            ("model_policy", model_policy),
            ("tool_policy", tool_policy),
            ("knowledge_policy", knowledge_policy),
            ("memory_policy", memory_policy),
            ("autonomy_policy", autonomy_policy),
            ("resource_access_policy", resource_access_policy),
        )
        if payload
    ]
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "compiled_prompt": compiled_prompt,
        "documents": documents,
        "document_projections": documents_state["projections"],
        "document_overrides": documents_state["overrides"],
        "document_sources": documents_state["sources"],
        "tool_policy_summary": {
            "requested_tool_ids": requested_tool_ids,
            "allowed_tool_ids": allowed_tool_ids,
            **tool_subset_summary(allowed_tool_ids),
        },
        "sections_present": sections_present,
        "document_lengths": {kind: len(content) for kind, content in documents.items()},
        "agent_spec": normalized_spec,
    }


def parse_json_env_value(value: str | None) -> dict[str, Any]:
    """Parse one JSON env blob into a dict safely."""
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
