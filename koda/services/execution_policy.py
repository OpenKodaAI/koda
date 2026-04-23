"""Central execution-policy gate for tools, MCP, and operator commands."""

from __future__ import annotations

from dataclasses import dataclass, field
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
    CONFLUENCE_ENABLED,
    FILEOPS_ENABLED,
    GIT_ENABLED,
    GWS_ENABLED,
    INTER_AGENT_ENABLED,
    JIRA_ENABLED,
    PLUGIN_SYSTEM_ENABLED,
    SHELL_ENABLED,
    SNAPSHOT_ENABLED,
    WEBHOOK_ENABLED,
    WORKFLOW_ENABLED,
)
from koda.knowledge.task_policy_defaults import default_execution_policy
from koda.knowledge.types import EffectiveExecutionPolicy

DecisionKind = str

_RULE_DECISION_ORDER: tuple[str, ...] = ("deny", "allow_with_preview", "require_approval", "allow")
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


def _configured_feature_flags() -> dict[str, bool]:
    return {
        "browser": BROWSER_FEATURES_ENABLED,
        "browser_network": BROWSER_NETWORK_INTERCEPTION_ENABLED,
        "browser_session": BROWSER_SESSION_PERSISTENCE_ENABLED,
        "jira": JIRA_ENABLED,
        "confluence": CONFLUENCE_ENABLED,
        "gws": GWS_ENABLED,
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


def _resolve_legacy_mcp_policy(tool_id: str) -> str | None:
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
            for item in get_control_plane_manager().list_mcp_tool_policies(AGENT_ID or "default", server_key)
        }
        return resolve_mcp_tool_policy(policy_map, tool_name, None)
    except Exception:
        return None


def normalize_execution_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize the first-class execution-policy document."""
    raw = dict(_safe_json_object(policy))
    normalized_rules: list[dict[str, Any]] = []
    for index, item in enumerate(raw.get("rules") or []):
        if not isinstance(item, dict):
            continue
        selectors = dict(_safe_json_object(item.get("selectors") or item.get("match")))
        decision = str(item.get("decision") or item.get("action") or "").strip().lower()
        if decision not in {"allow", "allow_with_preview", "require_approval", "deny"}:
            continue
        preview_fields = tuple(normalize_string_list(item.get("preview_fields")))
        approval_scope_kind = str(item.get("approval_scope_kind") or "").strip().lower() or "once"
        ttl_seconds = int(item.get("approval_ttl_seconds") or (900 if approval_scope_kind == "scope" else 600))
        normalized_rules.append(
            {
                "id": str(item.get("id") or item.get("rule_id") or f"rule_{index + 1}").strip() or f"rule_{index + 1}",
                "priority": int(item.get("priority") or 0),
                "decision": decision,
                "selectors": selectors,
                "reason": str(item.get("reason") or item.get("reason_code") or "").strip(),
                "preview_fields": preview_fields,
                "approval_scope_kind": approval_scope_kind if approval_scope_kind in {"once", "scope"} else "once",
                "approval_ttl_seconds": max(60, ttl_seconds),
            }
        )
    normalized_rules.sort(key=lambda item: int(item.get("priority") or 0), reverse=True)
    return {"version": int(raw.get("version") or 1), "rules": normalized_rules}


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
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(str(item).strip().lower() for item in value if str(item).strip())
    if value in (None, ""):
        return ()
    return (str(value).strip().lower(),)


def _value_matches(value: str | None, selector: Any) -> bool:
    candidates = _normalize_match_values(selector)
    if not candidates:
        return True
    normalized_value = str(value or "").strip().lower()
    if not normalized_value:
        return False
    for candidate in candidates:
        if candidate == "*":
            return True
        if candidate.endswith(".*"):
            prefix = candidate[:-2]
            if normalized_value == prefix or normalized_value.startswith(prefix + "."):
                return True
        elif candidate.endswith("*"):
            if normalized_value.startswith(candidate[:-1]):
                return True
        elif normalized_value == candidate:
            return True
    return False


def _path_matches(value: str | None, selector: Any) -> bool:
    candidates = _normalize_match_values(selector)
    if not candidates:
        return True
    normalized_value = str(value or "").strip().lower()
    if not normalized_value:
        return False
    return any(
        normalized_value == candidate or normalized_value.startswith(candidate.rstrip("/") + "/")
        for candidate in candidates
    )


def _effect_tags_match(effect_tags: tuple[str, ...], selector: Any) -> bool:
    required = set(_normalize_match_values(selector))
    if not required:
        return True
    return required.issubset({item.lower() for item in effect_tags})


def _rule_matches(rule: dict[str, Any], *, envelope: ActionEnvelope, task_kind: str) -> bool:
    selectors = _safe_json_object(rule.get("selectors"))
    return (
        _value_matches(envelope.tool_id, selectors.get("tool_id"))
        and _value_matches(envelope.integration_id, selectors.get("integration_id"))
        and _value_matches(envelope.action_id, selectors.get("action_id"))
        and _value_matches(envelope.server_key, selectors.get("server_key"))
        and _value_matches(envelope.transport, selectors.get("transport"))
        and _value_matches(envelope.access_level, selectors.get("access_level"))
        and _value_matches(envelope.risk_class, selectors.get("risk_class"))
        and _value_matches(task_kind, selectors.get("task_kind"))
        and _value_matches(envelope.domain, selectors.get("domain"))
        and _path_matches(envelope.path, selectors.get("path"))
        and _value_matches(envelope.db_env, selectors.get("db_env"))
        and _value_matches(str(envelope.private_network).lower(), selectors.get("private_network"))
        and _value_matches(str(envelope.uses_secrets).lower(), selectors.get("uses_secrets"))
        and _value_matches(str(envelope.bulk_operation).lower(), selectors.get("bulk_operation"))
        and _value_matches(str(envelope.external_side_effect).lower(), selectors.get("external_side_effect"))
        and _effect_tags_match(envelope.effect_tags, selectors.get("effect_tags"))
    )


def _find_matching_rule(
    policy: dict[str, Any],
    *,
    envelope: ActionEnvelope,
    task_kind: str,
) -> dict[str, Any] | None:
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
            selectors = _safe_json_object(rule.get("selectors"))
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
    approval_scope = _approval_scope_for(
        decision,
        envelope=envelope,
        ttl_seconds=int(rule.get("approval_ttl_seconds") or 0) or None,
    )
    explicit_scope_kind = str(rule.get("approval_scope_kind") or "").strip().lower()
    if approval_scope is not None and explicit_scope_kind in {"once", "scope"}:
        approval_scope = ApprovalScope(
            kind=explicit_scope_kind,
            ttl_seconds=approval_scope.ttl_seconds,
            max_uses=10 if explicit_scope_kind == "scope" else 1,
        )
    return PolicyEvaluation(
        decision=decision,
        reason_code=str(rule.get("reason") or "rule_match") or "rule_match",
        reason=str(rule.get("reason") or "Matched execution-policy rule."),
        envelope=envelope,
        rule_id=str(rule.get("id") or ""),
        matched_selector=_safe_json_object(rule.get("selectors")),
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
    if normalized == "always_allow":
        return PolicyEvaluation(
            decision="allow",
            reason_code="mcp_always_allow",
            reason="Allowed by legacy MCP tool policy.",
            envelope=envelope,
            audit_payload={"source": "legacy_mcp_policy", "policy": normalized},
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
) -> PolicyEvaluation:
    mcp_decision = _legacy_mcp_decision(
        legacy_mcp_policy=legacy_mcp_policy,
        envelope=envelope,
        params=params,
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
) -> PolicyEvaluation:
    """Evaluate one tool/action through the central policy gate."""
    payload = params or {}
    resolved_effective_policy = _configured_effective_policy(effective_policy=effective_policy, task_kind=task_kind)
    resolved_tool_policy = _configured_tool_policy(tool_policy)
    resolved_resource_policy = _configured_resource_access_policy(resource_access_policy)
    resolved_execution_policy = _configured_execution_policy(execution_policy)
    resolved_legacy_mcp_policy = (
        legacy_mcp_policy if legacy_mcp_policy is not None else _resolve_legacy_mcp_policy(tool_id)
    )
    feature_flags = _configured_feature_flags()
    envelope, grant_decision = resolve_action_envelope(tool_id, payload, resolved_resource_policy)

    if not known_tool:
        return PolicyEvaluation(
            decision="deny",
            reason_code="unknown_action",
            reason="Unknown or uncatalogued action blocked by fail-closed policy.",
            envelope=envelope,
            audit_payload={"tool_id": tool_id, "agent_id": AGENT_ID or "default"},
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
            legacy_mcp_policy=resolved_legacy_mcp_policy,
        )

    return _apply_overlays(
        base,
        grant_decision=grant_decision,
        effective_policy=resolved_effective_policy,
        confidence_report=confidence_report,
        approval_grant=approval_grant,
        params=payload,
    )
