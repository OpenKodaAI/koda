"""Central execution-policy gate for tools, MCP, and operator commands.

This module is the one execution-policy engine (ADR-002 AG-06, ADR-008 step 1).
The control plane delegates normalization and validation to it, and its
simulate route evaluates calls with :func:`evaluate_execution_policy`.

Rule semantics:

* ``normalize_execution_policy`` produces the canonical rule shape (``name``,
  ``priority``, ``match``, ``decision``). A rule's ``name`` is its audit
  ``rule_id``.
* Among the rules that match a call, the most restrictive decision wins
  (deny > require_approval > allow_with_preview > allow); ties go to the
  highest priority, then the lowest name.
* Selector values are fnmatch patterns (``*``, ``?``, ``[seq]``), compared
  case-insensitively. A ``path`` selector also covers everything below the
  path. An ``effect_tags`` selector needs every listed pattern to match a tag.
* A selector the engine cannot evaluate (an unknown key, an empty value, or a
  ``^regex`` pattern, which validation rejects) never widens access: a deny rule
  skips it, so it can only match more calls, and any other rule does not match.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from fnmatch import fnmatchcase
from typing import Any, cast

from koda.agent_contract import (
    CORE_TOOL_CATALOG,
    ActionEnvelope,
    IntegrationGrantDecision,
    is_tool_allowed_by_secure_default,
    normalize_string_list,
    resolve_action_envelope,
    resolve_allowed_tool_ids,
    resolve_feature_filtered_tools,
)
from koda.config import (
    AGENT_EXECUTION_POLICY,
    AGENT_ID,
    AGENT_RESOURCE_ACCESS_POLICY,
    AGENT_TOOL_POLICY,
    BROWSER_FEATURES_ENABLED,
    BROWSER_NETWORK_INTERCEPTION_ENABLED,
    BROWSER_SESSION_PERSISTENCE_ENABLED,
    FILEOPS_ENABLED,
    GIT_ENABLED,
    INTER_AGENT_ENABLED,
    PLUGIN_SYSTEM_ENABLED,
    SHELL_ENABLED,
    SNAPSHOT_ENABLED,
    WEBHOOK_ENABLED,
    WORKFLOW_ENABLED,
)
from koda.knowledge.task_policy_defaults import default_execution_policy
from koda.knowledge.types import EffectiveExecutionPolicy

DecisionKind = str

EXECUTION_POLICY_DECISIONS = frozenset({"allow", "allow_with_preview", "require_approval", "deny"})
# Most restrictive first: among the rules that match a call, the first decision in this order wins.
_RULE_DECISION_ORDER: tuple[str, ...] = ("deny", "require_approval", "allow_with_preview", "allow")
EXECUTION_POLICY_SELECTOR_KEYS = frozenset(
    {
        "tool_id",
        "integration_id",
        "action_id",
        "server_key",
        "effect_tags",
        "access_level",
        "risk_class",
        "task_kind",
        "domain",
        "path",
        "db_env",
        "transport",
        "private_network",
        "uses_secrets",
        "bulk_operation",
        "external_side_effect",
    }
)
_BOOLEAN_SELECTOR_KEYS = frozenset({"private_network", "uses_secrets", "bulk_operation", "external_side_effect"})
_PREVIEW_EFFECT_TAGS = frozenset(
    {
        "external_communication",
        "sharing_or_permissions",
        "destructive_change",
        "bulk_write",
        "package_or_plugin_install",
        "mcp_write",
    }
)
_ALWAYS_APPROVAL_EFFECT_TAGS = frozenset(
    {
        "browser_state_mutation",
        "delegation",
        "credential_access",
        "identity_admin",
        "private_network",
    }
)

_GRANT_REASON_MESSAGES: dict[str, str] = {
    "integration_disabled": "Blocked by integration policy: this integration is disabled.",
    "action_denied": "Blocked by integration policy: this action is explicitly denied.",
    "action_not_granted": "Blocked by integration policy: this action is outside the granted scope.",
    "explicit_integration_grant_required": "Blocked by integration policy: this action requires an explicit grant.",
    "read_only_policy": "Blocked by integration policy: this grant allows read-only actions only.",
    "domain_unknown": "Blocked by integration policy: the target domain is unknown for this action.",
    "domain_not_granted": "Blocked by integration policy: the target domain is outside the granted scope.",
    "private_network_not_granted": "Blocked by integration policy: private-network access is not granted.",
    "db_env_not_granted": "Blocked by integration policy: this database environment is outside the granted scope.",
    "path_not_granted": "Blocked by integration policy: this path is outside the granted scope.",
}


@dataclass(frozen=True, slots=True)
class ApprovalScope:
    kind: str = "once"
    ttl_seconds: int = 600
    max_uses: int = 1


@dataclass(frozen=True, slots=True)
class PolicyEvaluation:
    decision: DecisionKind
    reason_code: str
    reason: str
    envelope: ActionEnvelope
    rule_id: str | None = None
    matched_selector: dict[str, Any] | None = None
    approval_scope: ApprovalScope | None = None
    audit_payload: dict[str, Any] = field(default_factory=dict)
    preview_text: str | None = None
    preview_fields: tuple[str, ...] = ()
    legacy_compiled: bool = False

    @property
    def requires_confirmation(self) -> bool:
        return self.decision in {"allow_with_preview", "require_approval"}

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready copy, as the control-plane simulate route returns it."""
        payload = asdict(self)
        payload["requires_confirmation"] = self.requires_confirmation
        return payload


def _configured_feature_flags() -> dict[str, bool]:
    return {
        "browser": BROWSER_FEATURES_ENABLED,
        "browser_network": BROWSER_NETWORK_INTERCEPTION_ENABLED,
        "browser_session": BROWSER_SESSION_PERSISTENCE_ENABLED,
        "snapshots": SNAPSHOT_ENABLED,
        "webhooks": WEBHOOK_ENABLED,
        "fileops": FILEOPS_ENABLED,
        "shell": SHELL_ENABLED,
        "git": GIT_ENABLED,
        "plugins": PLUGIN_SYSTEM_ENABLED,
        "workflows": WORKFLOW_ENABLED,
        "inter_agent": INTER_AGENT_ENABLED,
    }


def _safe_json_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _grant_reason_message(reason_code: str | None) -> str:
    return _GRANT_REASON_MESSAGES.get(
        str(reason_code or "").strip().lower(),
        "Blocked by resource-access policy.",
    )


def _resolve_legacy_mcp_policy(tool_id: str, *, agent_id: str) -> str | None:
    parsed_tool = None
    try:
        from koda.services.mcp_bridge import parse_mcp_tool_id, resolve_mcp_tool_policy

        parsed_tool = parse_mcp_tool_id(tool_id)
        if parsed_tool is None:
            return None
        server_key, tool_name = parsed_tool
        from koda.control_plane.manager import get_control_plane_manager

        policy_map = {
            str(item.get("tool_name") or ""): str(item.get("policy") or "auto")
            for item in get_control_plane_manager().list_mcp_tool_policies(agent_id, server_key)
        }
        return resolve_mcp_tool_policy(policy_map, tool_name, None)
    except Exception:
        return None


def _resolve_mcp_risk_class(tool_id: str, *, agent_id: str) -> str:
    try:
        from koda.services.mcp_bridge import parse_mcp_tool_id
        from koda.services.mcp_risk import normalize_mcp_risk_class

        parsed_tool = parse_mcp_tool_id(tool_id)
        if parsed_tool is None:
            return "unknown"
        server_key, tool_name = parsed_tool
        from koda.control_plane.manager import get_control_plane_manager

        payload = get_control_plane_manager().get_mcp_connection_tools(agent_id, server_key)
        for tool in payload.get("tools") or []:
            if str(tool.get("name") or "") == tool_name:
                return normalize_mcp_risk_class(tool.get("risk_class") or tool.get("risk_level"))
    except Exception:
        return "unknown"
    return "unknown"


def _trimmed(value: Any) -> str:
    return str(value or "").strip()


def _as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return None


def _compact_mapping(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item not in (None, "", [], {}, ())}


def _normalize_selector_value(value: Any, *, key: str) -> Any:
    if key == "effect_tags":
        return [item.lower() for item in normalize_string_list(value)]
    if key in _BOOLEAN_SELECTOR_KEYS:
        parsed = _as_bool(value)
        return parsed if parsed is not None else value
    if isinstance(value, dict):
        return {
            str(sub_key).strip(): _normalize_selector_value(sub_value, key=str(sub_key).strip())
            for sub_key, sub_value in value.items()
            if str(sub_key).strip()
        }
    if isinstance(value, list):
        normalized = [_normalize_selector_value(item, key=key) for item in value]
        return [item for item in normalized if item not in (None, "", [], {}, ())]
    if isinstance(value, str):
        return value.strip()
    return value


def _rule_selectors(rule: dict[str, Any]) -> Any:
    """Return a rule's selectors: ``match``, or the runtime-legacy ``selectors`` when ``match`` is absent."""
    match = rule.get("match")
    return rule.get("selectors") if match is None else match


def _normalize_rule(index: int, rule: dict[str, Any]) -> dict[str, Any] | None:
    """Return one rule in the canonical shape, or ``None`` when it can never apply.

    The runtime-legacy keys ``id``/``rule_id``, ``selectors``, ``action`` and
    ``reason_code`` are migrated to ``name``, ``match``, ``decision`` and
    ``reason``; a canonical key that is present wins.
    """
    match: dict[str, Any] = {}
    for key, value in _safe_json_object(_rule_selectors(rule)).items():
        selector = _trimmed(key)
        if selector:
            match[selector] = _normalize_selector_value(value, key=selector)
    decision = _trimmed(rule.get("decision") or rule.get("action")).lower() or "require_approval"
    if not match or decision not in EXECUTION_POLICY_DECISIONS:
        return None

    normalized: dict[str, Any] = {
        "name": _trimmed(rule.get("name") or rule.get("id") or rule.get("rule_id")) or f"rule_{index}",
        "priority": _as_int(rule.get("priority")) or 0,
        "match": match,
        "decision": decision,
    }
    reason = _trimmed(rule.get("reason") or rule.get("reason_code"))
    if reason:
        normalized["reason"] = reason
    preview_fields = normalize_string_list(rule.get("preview_fields"))
    if preview_fields:
        normalized["preview_fields"] = preview_fields
    approval_scope_kind = _trimmed(rule.get("approval_scope_kind"))
    if approval_scope_kind:
        normalized["approval_scope_kind"] = approval_scope_kind
    approval_ttl_seconds = _as_int(rule.get("approval_ttl_seconds"))
    if approval_ttl_seconds is not None:
        normalized["approval_ttl_seconds"] = approval_ttl_seconds
    return _compact_mapping(normalized)


def normalize_execution_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    """Return the canonical execution-policy document.

    This is the only normalizer: the control plane stores its output and the
    runtime evaluates it. Rules without selectors or with an unknown decision are
    dropped; the others are ordered by priority (highest first), then name.
    Other top-level keys are kept.
    """
    raw = dict(_safe_json_object(policy))
    if not raw:
        return {}

    raw["version"] = _as_int(raw.get("version")) or 1

    default_decision = _trimmed(raw.get("default_decision")).lower()
    if default_decision in EXECUTION_POLICY_DECISIONS:
        raw["default_decision"] = default_decision

    default_approval_mode = _trimmed(_safe_json_object(raw.get("defaults")).get("default_approval_mode")).lower()
    if default_approval_mode:
        defaults = dict(_safe_json_object(raw.get("defaults")))
        defaults["default_approval_mode"] = default_approval_mode
        raw["defaults"] = _compact_mapping(defaults)

    raw_rules = raw.get("rules")
    normalized_rules = [
        rule
        for index, item in enumerate(raw_rules if isinstance(raw_rules, list) else [])
        if isinstance(item, dict) and (rule := _normalize_rule(index, item)) is not None
    ]
    if normalized_rules:
        normalized_rules.sort(key=lambda item: (-int(item.get("priority", 0) or 0), str(item.get("name") or "")))
        raw["rules"] = normalized_rules
    elif "rules" in raw:
        raw["rules"] = []

    source = _trimmed(raw.get("source")).lower()
    if source:
        raw["source"] = source

    return _compact_mapping(raw)


def _selector_items(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple, set, frozenset)) else [value]


def validate_execution_policy(policy: dict[str, Any] | None) -> tuple[list[str], list[str]]:
    """Return ``(errors, warnings)`` for an execution-policy document."""
    raw = _safe_json_object(policy)
    if not raw:
        return [], []

    errors: list[str] = []
    warnings: list[str] = []

    version = _as_int(raw.get("version"))
    if version is not None and version != 1:
        errors.append(f"execution_policy.version is invalid: {version}")

    rules = raw.get("rules")
    if rules is not None and not isinstance(rules, list):
        errors.append("execution_policy.rules must be a list.")
        return errors, warnings

    for index, rule in enumerate(rules or []):
        if not isinstance(rule, dict):
            errors.append(f"execution_policy.rules[{index}] must be a mapping.")
            continue

        decision = _trimmed(rule.get("decision")).lower()
        if decision and decision not in EXECUTION_POLICY_DECISIONS:
            errors.append(
                f"execution_policy.rules[{index}].decision is invalid: {decision}. "
                f"Expected one of: {', '.join(sorted(EXECUTION_POLICY_DECISIONS))}"
            )

        match = _rule_selectors(rule)
        if not isinstance(match, dict):
            errors.append(f"execution_policy.rules[{index}].match must be a mapping.")
            continue

        unknown_selectors = sorted(str(key) for key in match if str(key).strip() not in EXECUTION_POLICY_SELECTOR_KEYS)
        if unknown_selectors:
            warnings.append(
                f"execution_policy.rules[{index}].match contains unsupported selectors: " + ", ".join(unknown_selectors)
            )

        for key, value in match.items():
            regex_patterns = [str(item).strip() for item in _selector_items(value) if str(item).strip().startswith("^")]
            if regex_patterns:
                errors.append(
                    f"execution_policy.rules[{index}].match.{str(key).strip()} uses a regular expression "
                    f"({', '.join(regex_patterns)}); only fnmatch patterns (*, ?, [seq]) are supported."
                )

        for key in ("preview_fields",):
            value = rule.get(key)
            if value is None:
                continue
            if not isinstance(value, list):
                errors.append(f"execution_policy.rules[{index}].{key} must be a list.")

        ttl_value = rule.get("approval_ttl_seconds")
        if ttl_value not in (None, ""):
            ttl = _as_int(ttl_value)
            if ttl is None or ttl <= 0:
                errors.append(f"execution_policy.rules[{index}].approval_ttl_seconds must be a positive integer.")

    return errors, warnings


def _configured_execution_policy(execution_policy: dict[str, Any] | None = None) -> dict[str, Any]:
    if execution_policy is not None:
        return normalize_execution_policy(execution_policy)
    if AGENT_EXECUTION_POLICY:
        return normalize_execution_policy(AGENT_EXECUTION_POLICY)
    return {}


def _configured_tool_policy(tool_policy: dict[str, Any] | None = None) -> dict[str, Any]:
    if tool_policy is not None:
        return dict(tool_policy)
    return dict(AGENT_TOOL_POLICY or {})


def _configured_resource_access_policy(resource_access_policy: dict[str, Any] | None = None) -> dict[str, Any]:
    if resource_access_policy is not None:
        return dict(resource_access_policy)
    return dict(AGENT_RESOURCE_ACCESS_POLICY or {})


def _configured_effective_policy(
    *,
    effective_policy: EffectiveExecutionPolicy | None,
    task_kind: str,
) -> EffectiveExecutionPolicy:
    if effective_policy is not None:
        return effective_policy
    return default_execution_policy(task_kind)


def _normalize_match_values(value: Any) -> tuple[str, ...]:
    """Return a selector's patterns, trimmed and lower-cased, without empty ones."""
    items = value if isinstance(value, (list, tuple, set, frozenset)) else () if value is None else (value,)
    return tuple(str(item).strip().lower() for item in items if str(item).strip())


def _value_matches(value: Any, patterns: tuple[str, ...]) -> bool:
    text = str(value).lower() if isinstance(value, bool) else str(value or "")
    normalized_value = text.strip().lower()
    return bool(normalized_value) and any(fnmatchcase(normalized_value, pattern) for pattern in patterns)


def _path_matches(value: str | None, patterns: tuple[str, ...]) -> bool:
    normalized_value = str(value or "").strip().lower()
    return bool(normalized_value) and any(
        fnmatchcase(normalized_value, pattern) or fnmatchcase(normalized_value, pattern.rstrip("/") + "/*")
        for pattern in patterns
    )


def _effect_tags_match(effect_tags: tuple[str, ...], patterns: tuple[str, ...]) -> bool:
    tags = {item.lower() for item in effect_tags}
    return all(any(fnmatchcase(tag, pattern) for tag in tags) for pattern in patterns)


def _selector_matches(key: str, patterns: tuple[str, ...], *, envelope: ActionEnvelope, task_kind: str) -> bool:
    if key == "effect_tags":
        return _effect_tags_match(envelope.effect_tags, patterns)
    if key == "path":
        return _path_matches(envelope.path, patterns)
    if key == "task_kind":
        return _value_matches(task_kind, patterns)
    return _value_matches(getattr(envelope, key), patterns)


def _rule_matches(rule: dict[str, Any], *, envelope: ActionEnvelope, task_kind: str) -> bool:
    is_deny = rule.get("decision") == "deny"
    for key, value in _safe_json_object(rule.get("match")).items():
        patterns = _normalize_match_values(value)
        if key not in EXECUTION_POLICY_SELECTOR_KEYS or not patterns or any(item.startswith("^") for item in patterns):
            # The engine cannot evaluate this selector. It must never widen access:
            # a deny rule skips it (matching more calls); any other rule does not match.
            if is_deny:
                continue
            return False
        if not _selector_matches(key, patterns, envelope=envelope, task_kind=task_kind):
            return False
    return True


def _find_matching_rule(
    policy: dict[str, Any],
    *,
    envelope: ActionEnvelope,
    task_kind: str,
) -> dict[str, Any] | None:
    """Return the matching rule with the most restrictive decision.

    Rules arrive ordered by priority, then name (``normalize_execution_policy``),
    so ties within one decision go to the highest priority.
    """
    rules = [rule for rule in policy.get("rules") or [] if _rule_matches(rule, envelope=envelope, task_kind=task_kind)]
    if not rules:
        return None
    for decision in _RULE_DECISION_ORDER:
        for rule in rules:
            if rule.get("decision") == decision:
                return cast(dict[str, Any], rule)
    return None


def _build_preview_text(envelope: ActionEnvelope, params: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    preview_fields: tuple[str, ...]
    if "external_communication" in envelope.effect_tags:
        preview_fields = ("to", "subject", "body")
    elif "sharing_or_permissions" in envelope.effect_tags:
        preview_fields = ("target", "email", "role")
    elif "destructive_change" in envelope.effect_tags:
        preview_fields = ("path", "id", "key", "url")
    elif "package_or_plugin_install" in envelope.effect_tags:
        preview_fields = ("name", "package", "version", "args")
    else:
        preview_fields = ("args", "path", "url")
    parts = [
        f"Tool: {envelope.tool_id}",
        f"Action: {envelope.integration_id}/{envelope.action_id}",
    ]
    for field_name in preview_fields:
        value = params.get(field_name)
        if value not in (None, "", [], {}):
            parts.append(f"{field_name}: {value}")
    if len(parts) <= 2:
        parts.append(f"Params: {params}")
    return "\n".join(parts), preview_fields


def _approval_scope_for(
    decision: str,
    *,
    envelope: ActionEnvelope,
    ttl_seconds: int | None = None,
) -> ApprovalScope | None:
    if decision not in {"allow_with_preview", "require_approval"}:
        return None
    allow_scope = (
        decision == "require_approval"
        and envelope.access_level == "write"
        and not envelope.external_side_effect
        and not envelope.bulk_operation
        and not (set(envelope.effect_tags) & (_PREVIEW_EFFECT_TAGS | _ALWAYS_APPROVAL_EFFECT_TAGS))
    )
    if allow_scope:
        return ApprovalScope(kind="scope", ttl_seconds=ttl_seconds or 900, max_uses=10)
    return ApprovalScope(kind="once", ttl_seconds=ttl_seconds or 600, max_uses=1)


def resolve_execution_policy_allowed_tool_ids(
    *,
    tool_policy: dict[str, Any] | None = None,
    execution_policy: dict[str, Any] | None = None,
    feature_flags: dict[str, bool] | None = None,
) -> list[str]:
    """Return the effective prompt/runtime tool allowlist for one agent."""
    flags = feature_flags or _configured_feature_flags()
    available_tool_ids = {
        str(item["id"]) for item in resolve_feature_filtered_tools(flags) if bool(item.get("available"))
    }
    resolved_execution_policy = _configured_execution_policy(execution_policy)
    if resolved_execution_policy.get("rules"):
        allowed: set[str] = {tool_id for tool_id in available_tool_ids if is_tool_allowed_by_secure_default(tool_id)}
        for rule in resolved_execution_policy.get("rules") or []:
            if str(rule.get("decision") or "").strip().lower() == "deny":
                continue
            selectors = _safe_json_object(rule.get("match"))
            for field_name in ("tool_id", "integration_id"):
                for candidate in _normalize_match_values(selectors.get(field_name)):
                    if candidate in available_tool_ids:
                        allowed.add(candidate)
        return sorted(allowed)
    return resolve_allowed_tool_ids(_configured_tool_policy(tool_policy), feature_flags=flags)


def _explicit_rule_decision(
    *,
    rule: dict[str, Any],
    envelope: ActionEnvelope,
    params: dict[str, Any],
) -> PolicyEvaluation:
    decision = str(rule.get("decision") or "deny")
    preview_text, preview_fields = _build_preview_text(envelope, params)
    approval_scope: ApprovalScope | None = None
    if decision in {"allow_with_preview", "require_approval"}:
        # A rule's approval is single-use unless the rule asks for a scope.
        scope_kind = _trimmed(rule.get("approval_scope_kind")).lower()
        if scope_kind not in {"once", "scope"}:
            scope_kind = "once"
        ttl_seconds = _as_int(rule.get("approval_ttl_seconds")) or (900 if scope_kind == "scope" else 600)
        approval_scope = ApprovalScope(
            kind=scope_kind,
            ttl_seconds=max(60, ttl_seconds),
            max_uses=10 if scope_kind == "scope" else 1,
        )
    return PolicyEvaluation(
        decision=decision,
        reason_code=str(rule.get("reason") or "rule_match") or "rule_match",
        reason=str(rule.get("reason") or "Matched execution-policy rule."),
        envelope=envelope,
        rule_id=str(rule.get("name") or ""),
        matched_selector=_safe_json_object(rule.get("match")),
        approval_scope=approval_scope,
        preview_text=preview_text if decision == "allow_with_preview" else None,
        preview_fields=tuple(rule.get("preview_fields") or preview_fields),
        audit_payload={"source": "execution_policy", "rule": rule},
    )


def _legacy_mcp_decision(
    *,
    legacy_mcp_policy: str | None,
    envelope: ActionEnvelope,
    params: dict[str, Any],
    agent_id: str,
) -> PolicyEvaluation | None:
    if not envelope.integration_id.startswith("mcp:"):
        return None
    normalized = str(legacy_mcp_policy or "always_ask").strip().lower() or "always_ask"
    if normalized == "blocked":
        return PolicyEvaluation(
            decision="deny",
            reason_code="mcp_blocked",
            reason="Blocked by legacy MCP tool policy.",
            envelope=envelope,
            approval_scope=None,
            audit_payload={"source": "legacy_mcp_policy", "policy": normalized},
            legacy_compiled=True,
        )
    from koda.services.mcp_risk import HIGH_RISK_MCP_CLASSES

    risk_class = _resolve_mcp_risk_class(envelope.tool_id, agent_id=agent_id)
    if normalized == "always_allow" and risk_class not in HIGH_RISK_MCP_CLASSES:
        return PolicyEvaluation(
            decision="allow",
            reason_code="mcp_always_allow",
            reason="Allowed by legacy MCP tool policy.",
            envelope=envelope,
            audit_payload={"source": "legacy_mcp_policy", "policy": normalized},
            legacy_compiled=True,
        )
    if normalized == "always_allow":
        preview_text, preview_fields = _build_preview_text(envelope, params)
        return PolicyEvaluation(
            decision="require_approval",
            reason_code="mcp_high_risk_requires_approval",
            reason="MCP risk taxonomy requires approval before this action can execute.",
            envelope=envelope,
            approval_scope=ApprovalScope(kind="scope", ttl_seconds=900, max_uses=10),
            preview_text=preview_text,
            preview_fields=preview_fields,
            audit_payload={"source": "mcp_risk_taxonomy", "legacy_policy": normalized, "risk_class": risk_class},
            legacy_compiled=True,
        )
    preview_text, preview_fields = _build_preview_text(envelope, params)
    return PolicyEvaluation(
        decision="allow_with_preview" if envelope.access_level != "read" else "require_approval",
        reason_code="mcp_requires_approval",
        reason="Legacy MCP policy requires human approval.",
        envelope=envelope,
        approval_scope=ApprovalScope(kind="scope", ttl_seconds=900, max_uses=10),
        preview_text=preview_text if envelope.access_level != "read" else None,
        preview_fields=preview_fields,
        audit_payload={"source": "legacy_mcp_policy", "policy": normalized},
        legacy_compiled=True,
    )


def _legacy_policy_decision(
    *,
    envelope: ActionEnvelope,
    params: dict[str, Any],
    grant_decision: IntegrationGrantDecision,
    effective_policy: EffectiveExecutionPolicy,
    tool_policy: dict[str, Any],
    feature_flags: dict[str, bool],
    legacy_mcp_policy: str | None,
    agent_id: str,
) -> PolicyEvaluation:
    mcp_decision = _legacy_mcp_decision(
        legacy_mcp_policy=(
            legacy_mcp_policy
            if legacy_mcp_policy is not None
            else _resolve_legacy_mcp_policy(envelope.tool_id, agent_id=agent_id)
        ),
        envelope=envelope,
        params=params,
        agent_id=agent_id,
    )
    if mcp_decision is not None:
        return mcp_decision

    allowed_tool_ids = set(resolve_allowed_tool_ids(tool_policy, feature_flags=feature_flags))
    tool_allowed = (
        envelope.tool_id in allowed_tool_ids
        or (envelope.tool_id not in CORE_TOOL_CATALOG and envelope.catalogued)
        or is_tool_allowed_by_secure_default(envelope.tool_id)
    )
    if not tool_allowed and not envelope.integration_id.startswith("mcp:"):
        return PolicyEvaluation(
            decision="deny",
            reason_code="tool_not_enabled",
            reason="Tool is outside the secure default tool subset for this agent.",
            envelope=envelope,
            audit_payload={"allowed_tool_ids": sorted(allowed_tool_ids)},
            legacy_compiled=True,
        )

    if not grant_decision.allowed:
        return PolicyEvaluation(
            decision="deny",
            reason_code=str(grant_decision.reason or "integration_policy"),
            reason=_grant_reason_message(str(grant_decision.reason or "integration_policy")),
            envelope=envelope,
            audit_payload={"grant_reason": grant_decision.reason},
            legacy_compiled=True,
        )

    if effective_policy.read_only and envelope.access_level != "read":
        return PolicyEvaluation(
            decision="deny",
            reason_code="read_only_policy",
            reason="The effective task policy is read-only.",
            envelope=envelope,
            legacy_compiled=True,
        )

    if envelope.access_level == "read":
        return PolicyEvaluation(
            decision="allow",
            reason_code="secure_default_read",
            reason="Safe read allowed by the secure default baseline.",
            envelope=envelope,
            legacy_compiled=True,
        )

    preview_text, preview_fields = _build_preview_text(envelope, params)
    needs_preview = bool(set(envelope.effect_tags) & _PREVIEW_EFFECT_TAGS)
    low_risk_local_write = (
        envelope.access_level == "write"
        and not envelope.external_side_effect
        and not envelope.bulk_operation
        and not (
            set(envelope.effect_tags)
            & (
                _PREVIEW_EFFECT_TAGS
                | _ALWAYS_APPROVAL_EFFECT_TAGS
                | {"mcp_write", "external_communication", "sharing_or_permissions"}
            )
        )
    )
    if effective_policy.approval_mode == "guarded" and low_risk_local_write:
        return PolicyEvaluation(
            decision="allow",
            reason_code="guarded_low_risk_write",
            reason="Low-risk local write allowed by guarded legacy policy.",
            envelope=envelope,
            legacy_compiled=True,
        )

    decision = "allow_with_preview" if needs_preview else "require_approval"
    return PolicyEvaluation(
        decision=decision,
        reason_code="legacy_human_factor",
        reason="Legacy autonomy policy requires explicit human approval.",
        envelope=envelope,
        approval_scope=_approval_scope_for(decision, envelope=envelope),
        preview_text=preview_text if decision == "allow_with_preview" else None,
        preview_fields=preview_fields,
        legacy_compiled=True,
    )


def _apply_overlays(
    evaluation: PolicyEvaluation,
    *,
    grant_decision: IntegrationGrantDecision,
    effective_policy: EffectiveExecutionPolicy,
    confidence_report: dict[str, Any] | None,
    approval_grant: dict[str, Any] | None,
    params: dict[str, Any],
) -> PolicyEvaluation:
    envelope = evaluation.envelope
    if not grant_decision.allowed:
        return PolicyEvaluation(
            decision="deny",
            reason_code=str(grant_decision.reason or "integration_policy"),
            reason=_grant_reason_message(str(grant_decision.reason or "integration_policy")),
            envelope=envelope,
            audit_payload={"grant_reason": grant_decision.reason},
            legacy_compiled=evaluation.legacy_compiled,
        )

    if evaluation.decision == "allow" and effective_policy.read_only and envelope.access_level != "read":
        return PolicyEvaluation(
            decision="deny",
            reason_code="read_only_policy",
            reason="The effective task policy is read-only.",
            envelope=envelope,
            legacy_compiled=evaluation.legacy_compiled,
        )

    if (
        evaluation.decision == "allow"
        and envelope.access_level != "read"
        and set(envelope.effect_tags) & _PREVIEW_EFFECT_TAGS
    ):
        preview_text, preview_fields = _build_preview_text(envelope, params)
        evaluation = PolicyEvaluation(
            decision="allow_with_preview",
            reason_code="preview_required",
            reason="This action class requires an explicit runtime preview before execution.",
            envelope=envelope,
            approval_scope=_approval_scope_for("allow_with_preview", envelope=envelope),
            preview_text=preview_text,
            preview_fields=preview_fields,
            audit_payload={"source": "preview_overlay"},
            legacy_compiled=evaluation.legacy_compiled,
        )

    if (
        evaluation.decision == "allow"
        and envelope.access_level != "read"
        and set(envelope.effect_tags) & _ALWAYS_APPROVAL_EFFECT_TAGS
    ):
        _preview_text, preview_fields = _build_preview_text(envelope, params)
        evaluation = PolicyEvaluation(
            decision="require_approval",
            reason_code="human_factor_required",
            reason="This action class requires explicit human approval before execution.",
            envelope=envelope,
            approval_scope=_approval_scope_for("require_approval", envelope=envelope),
            preview_fields=preview_fields,
            audit_payload={"source": "human_factor_overlay"},
            legacy_compiled=evaluation.legacy_compiled,
        )

    if evaluation.decision == "allow" and effective_policy.escalation_required and envelope.access_level != "read":
        preview_text, preview_fields = _build_preview_text(envelope, params)
        evaluation = PolicyEvaluation(
            decision="allow_with_preview" if set(envelope.effect_tags) & _PREVIEW_EFFECT_TAGS else "require_approval",
            reason_code="escalation_required",
            reason="This task kind requires human escalation before writes.",
            envelope=envelope,
            approval_scope=_approval_scope_for("require_approval", envelope=envelope),
            preview_text=preview_text if set(envelope.effect_tags) & _PREVIEW_EFFECT_TAGS else None,
            preview_fields=preview_fields,
            audit_payload={"source": "effective_policy"},
            legacy_compiled=evaluation.legacy_compiled,
        )

    if evaluation.decision == "allow" and confidence_report:
        blocked = bool(confidence_report.get("blocked"))
        requires_human_approval = bool(confidence_report.get("requires_human_approval"))
        if blocked:
            return PolicyEvaluation(
                decision="deny",
                reason_code="confidence_blocked",
                reason="Blocked by execution-confidence overlay.",
                envelope=envelope,
                audit_payload={"confidence": confidence_report},
                legacy_compiled=evaluation.legacy_compiled,
            )
        if requires_human_approval and envelope.access_level != "read":
            preview_text, preview_fields = _build_preview_text(envelope, params)
            decision = "allow_with_preview" if set(envelope.effect_tags) & _PREVIEW_EFFECT_TAGS else "require_approval"
            evaluation = PolicyEvaluation(
                decision=decision,
                reason_code="confidence_requires_human",
                reason="Confidence overlay requires human confirmation.",
                envelope=envelope,
                approval_scope=_approval_scope_for(decision, envelope=envelope),
                preview_text=preview_text if decision == "allow_with_preview" else None,
                preview_fields=preview_fields,
                audit_payload={"confidence": confidence_report},
                legacy_compiled=evaluation.legacy_compiled,
            )

    if approval_grant and evaluation.requires_confirmation:
        return PolicyEvaluation(
            decision="allow",
            reason_code="approval_grant",
            reason="Allowed by active scoped approval grant.",
            envelope=envelope,
            rule_id=str(approval_grant.get("grant_id") or ""),
            audit_payload={"grant": dict(approval_grant)},
            legacy_compiled=evaluation.legacy_compiled,
        )
    return evaluation


def evaluate_execution_policy(
    tool_id: str,
    params: dict[str, Any] | None,
    *,
    task_kind: str = "general",
    effective_policy: EffectiveExecutionPolicy | None = None,
    tool_policy: dict[str, Any] | None = None,
    resource_access_policy: dict[str, Any] | None = None,
    execution_policy: dict[str, Any] | None = None,
    confidence_report: dict[str, Any] | None = None,
    approval_grant: dict[str, Any] | None = None,
    legacy_mcp_policy: str | None = None,
    known_tool: bool = True,
    agent_id: str | None = None,
) -> PolicyEvaluation:
    """Evaluate one tool/action through the central policy gate.

    ``agent_id`` names the agent whose control-plane rows (legacy MCP tool policy
    and MCP risk class) are consulted; it defaults to this worker's ``AGENT_ID``.
    The control-plane simulate route passes it to evaluate on an agent's behalf.
    """
    payload = params or {}
    resolved_agent_id = agent_id or AGENT_ID or "default"
    resolved_effective_policy = _configured_effective_policy(effective_policy=effective_policy, task_kind=task_kind)
    resolved_tool_policy = _configured_tool_policy(tool_policy)
    resolved_resource_policy = _configured_resource_access_policy(resource_access_policy)
    resolved_execution_policy = _configured_execution_policy(execution_policy)
    feature_flags = _configured_feature_flags()
    envelope, grant_decision = resolve_action_envelope(tool_id, payload, resolved_resource_policy)

    if not known_tool:
        return PolicyEvaluation(
            decision="deny",
            reason_code="unknown_action",
            reason="Unknown or uncatalogued action blocked by fail-closed policy.",
            envelope=envelope,
            audit_payload={"tool_id": tool_id, "agent_id": resolved_agent_id},
        )

    matched_rule = _find_matching_rule(resolved_execution_policy, envelope=envelope, task_kind=task_kind)
    if matched_rule is not None:
        base = _explicit_rule_decision(rule=matched_rule, envelope=envelope, params=payload)
    elif resolved_execution_policy.get("rules"):
        if envelope.access_level == "read" and is_tool_allowed_by_secure_default(tool_id):
            base = PolicyEvaluation(
                decision="allow",
                reason_code="secure_default_read",
                reason="Safe read allowed by secure default.",
                envelope=envelope,
            )
        else:
            base = PolicyEvaluation(
                decision="deny",
                reason_code="secure_default_block",
                reason="No execution-policy rule matched a non-safe action.",
                envelope=envelope,
            )
    else:
        base = _legacy_policy_decision(
            envelope=envelope,
            params=payload,
            grant_decision=grant_decision,
            effective_policy=resolved_effective_policy,
            tool_policy=resolved_tool_policy,
            feature_flags=feature_flags,
            legacy_mcp_policy=legacy_mcp_policy,
            agent_id=resolved_agent_id,
        )

    return _apply_overlays(
        base,
        grant_decision=grant_decision,
        effective_policy=resolved_effective_policy,
        confidence_report=confidence_report,
        approval_grant=approval_grant,
        params=payload,
    )
