"""Planning and confidence heuristics before sensitive autonomous writes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from koda.knowledge.types import EffectiveExecutionPolicy, KnowledgeLayer
from koda.memory.profile import MemoryProfile
from koda.memory.types import MemoryLayer
from koda.services.confidence_config import (
    EXECUTION_CONFIDENCE_ENABLED,
    EXECUTION_CONFIDENCE_REQUIRE_FRESH_SOURCES,
    EXECUTION_CONFIDENCE_REQUIRE_PLAN_FOR_WRITES,
    EXECUTION_CONFIDENCE_THRESHOLD,
)

_ACTION_PLAN_RE = re.compile(r"<action_plan>(.*?)</action_plan>", re.DOTALL | re.IGNORECASE)
_TAG_FIELDS = (
    "summary",
    "assumptions",
    "evidence",
    "sources",
    "risk",
    "verification",
    "rollback",
    "probable_cause",
    "escalation",
    "success",
)
_NATIVE_READ_TOOLS = frozenset({"Glob", "Grep", "LS", "Read", "read_file"})
_WEAK_MEMORY_LAYERS = frozenset({MemoryLayer.CONVERSATIONAL.value, MemoryLayer.PROACTIVE.value})
_SUPPORTIVE_MEMORY_LAYERS = frozenset({MemoryLayer.PROCEDURAL.value, MemoryLayer.EPISODIC.value})


@dataclass(slots=True)
class ActionPlan:
    """Structured mini-plan emitted by the assistant before writes."""

    summary: str = ""
    assumptions: str = ""
    evidence: str = ""
    sources: str = ""
    risk: str = ""
    verification: str = ""
    rollback: str = ""
    probable_cause: str = ""
    escalation: str = ""
    success: str = ""
    raw: str = ""

    @property
    def missing_fields(self) -> list[str]:
        missing: list[str] = []
        for field_name in ("summary", "evidence", "sources", "risk", "success"):
            if not getattr(self, field_name).strip():
                missing.append(field_name)
        return missing


@dataclass(slots=True)
class ConfidenceReport:
    """Heuristic confidence score for a write-capable iteration."""

    score: float
    blocked: bool
    reasons: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    source_count: int = 0
    fresh_source_count: int = 0
    read_evidence_count: int = 0
    plan_valid: bool = False
    task_kind: str = "general"
    source_layers: list[str] = field(default_factory=list)
    required_source_layers: list[str] = field(default_factory=list)
    operable_source_layers: list[str] = field(default_factory=list)
    non_operable_source_layers: list[str] = field(default_factory=list)
    verification_required: list[str] = field(default_factory=list)
    verification_plan_present: bool = False
    write_mode: str = "standard"
    ungrounded_operationally: bool = False
    autonomy_tier: str = "t0"
    stale_sources_present: bool = False
    guardrail_count: int = 0
    requires_human_approval: bool = False
    memory_trust_score: float = 0.0
    memory_layers: list[str] = field(default_factory=list)
    memory_explainable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 4),
            "blocked": self.blocked,
            "reasons": self.reasons,
            "missing_fields": self.missing_fields,
            "source_count": self.source_count,
            "fresh_source_count": self.fresh_source_count,
            "read_evidence_count": self.read_evidence_count,
            "plan_valid": self.plan_valid,
            "task_kind": self.task_kind,
            "source_layers": self.source_layers,
            "required_source_layers": self.required_source_layers,
            "operable_source_layers": self.operable_source_layers,
            "non_operable_source_layers": self.non_operable_source_layers,
            "verification_required": self.verification_required,
            "verification_plan_present": self.verification_plan_present,
            "write_mode": self.write_mode,
            "ungrounded_operationally": self.ungrounded_operationally,
            "autonomy_tier": self.autonomy_tier,
            "stale_sources_present": self.stale_sources_present,
            "guardrail_count": self.guardrail_count,
            "requires_human_approval": self.requires_human_approval,
            "memory_trust_score": round(self.memory_trust_score, 4),
            "memory_layers": self.memory_layers,
            "memory_explainable": self.memory_explainable,
        }

    def to_tool_message(self) -> str:
        reason_text = "; ".join(self.reasons) if self.reasons else "low confidence"
        if self.missing_fields:
            missing = ", ".join(self.missing_fields)
            return (
                "Write blocked by confidence gate. "
                f"Missing required <action_plan> fields: {missing}. "
                f"Why blocked: {reason_text}."
            )
        return f"Write blocked by confidence gate. Why blocked: {reason_text}."


def strip_internal_blocks(text: str) -> str:
    """Remove internal orchestration blocks that should not reach the user."""
    return _ACTION_PLAN_RE.sub("", text)


def parse_action_plan(text: str) -> ActionPlan | None:
    """Parse the assistant's <action_plan> block."""
    match = _ACTION_PLAN_RE.search(text)
    if not match:
        return None

    raw = match.group(1).strip()
    values: dict[str, str] = {}
    for field_name in _TAG_FIELDS:
        tag_match = re.search(
            rf"<{field_name}>(.*?)</{field_name}>",
            raw,
            re.DOTALL | re.IGNORECASE,
        )
        if tag_match:
            values[field_name] = tag_match.group(1).strip()
            continue

        label_match = re.search(
            rf"^{field_name}\s*:\s*(.+)$",
            raw,
            re.MULTILINE | re.IGNORECASE,
        )
        values[field_name] = label_match.group(1).strip() if label_match else ""

    return ActionPlan(raw=raw, **values)


def evaluate_write_confidence(
    *,
    action_plan: ActionPlan | None,
    task_kind: str,
    policy: EffectiveExecutionPolicy,
    read_calls: list[Any],
    prior_tool_steps: list[dict[str, Any]],
    native_tool_uses: list[dict[str, Any]],
    knowledge_hits: list[dict[str, Any]] | list[Any],
    memory_resolution: Any | None = None,
    memory_profile: MemoryProfile | None = None,
    warnings: list[str],
    guardrails: list[Any] | None = None,
    stale_sources_present: bool = False,
    ungrounded_operationally: bool = False,
) -> ConfidenceReport:
    """Score whether the current write iteration is sufficiently grounded."""
    if not EXECUTION_CONFIDENCE_ENABLED:
        return ConfidenceReport(
            score=1.0,
            blocked=False,
            reasons=["confidence gate disabled"],
            plan_valid=True,
            task_kind=task_kind,
            write_mode=policy.approval_mode,
            autonomy_tier=policy.autonomy_tier.value,
        )

    missing_fields = (
        action_plan.missing_fields if action_plan else ["summary", "evidence", "sources", "risk", "success"]
    )
    plan_valid = bool(action_plan) and not missing_fields

    source_count = 0
    fresh_source_count = 0
    source_layers: set[str] = set()
    non_operable_source_layers: set[str] = set()
    policy_stale_sources_present = False
    for hit in knowledge_hits:
        freshness = getattr(hit, "freshness", None)
        layer = getattr(getattr(hit, "entry", None), "layer", None)
        updated_at = getattr(getattr(hit, "entry", None), "updated_at", None)
        operable = getattr(hit, "operable", None)
        if freshness is None and isinstance(hit, dict):
            freshness = hit.get("freshness")
            layer = hit.get("layer")
            updated_at = hit.get("updated_at")
            operable = hit.get("operable")
        if operable is None:
            operable = True
        source_count += 1
        if freshness == "fresh":
            fresh_source_count += 1
        normalized_layer = ""
        if isinstance(layer, KnowledgeLayer):
            normalized_layer = layer.value
        elif isinstance(layer, str):
            normalized_layer = layer
        if normalized_layer:
            if bool(operable):
                source_layers.add(normalized_layer)
            else:
                non_operable_source_layers.add(normalized_layer)
        if updated_at:
            try:
                updated_dt = (
                    updated_at
                    if isinstance(updated_at, datetime)
                    else datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
                )
                if updated_dt.tzinfo is not None:
                    updated_dt = updated_dt.astimezone(UTC).replace(tzinfo=None)
                if (datetime.now() - updated_dt).days > policy.max_source_age_days:
                    policy_stale_sources_present = True
            except ValueError:
                pass

    prior_read_count = sum(
        1 for step in prior_tool_steps if step.get("success") and not step.get("metadata", {}).get("write")
    )
    native_read_count = sum(1 for tool in native_tool_uses if tool.get("name") in _NATIVE_READ_TOOLS)
    read_evidence_count = len(read_calls) + prior_read_count + native_read_count

    score = 0.35
    reasons: list[str] = []
    verification_plan_present = bool(action_plan and (action_plan.verification.strip() or action_plan.success.strip()))
    required_source_layers = [layer.value for layer in policy.required_layers]
    guardrail_count = len(guardrails or [])
    requires_human_approval = policy.approval_mode == "supervised"
    risky_task = task_kind in {"deploy", "code_change", "bugfix", "db_write", "business_operation"}
    risk_adjustments = memory_profile.risk_posture_adjustments(task_kind) if memory_profile else {}
    memory_trust_score = float(getattr(memory_resolution, "trust_score", 0.0) or 0.0)
    memory_layers = [str(item) for item in (getattr(memory_resolution, "selected_layers", []) or [])]
    memory_explainable = bool(getattr(memory_resolution, "explanations", []) or [])

    if plan_valid:
        score += 0.25
    else:
        reasons.append("missing structured action plan")
        score -= 0.25

    if policy.read_only:
        reasons.append("task policy is read-only")
        score = 0.0

    if policy.escalation_required and not (action_plan and action_plan.escalation.strip()):
        reasons.append("task requires explicit escalation before writes")
        score -= 0.20

    if action_plan and action_plan.sources.strip():
        score += 0.10
    else:
        reasons.append("no declared sources in action plan")
        score -= 0.10

    if action_plan and action_plan.evidence.strip():
        score += 0.10
    else:
        reasons.append("no execution evidence captured")
        score -= 0.05

    if policy.requires_probable_cause and not (action_plan and action_plan.probable_cause.strip()):
        reasons.append("probable cause is required for this task kind")
        score -= 0.10

    if policy.requires_rollback and not (action_plan and action_plan.rollback.strip()):
        reasons.append("rollback note is required for this task kind")
        score -= 0.10

    if policy.required_verifications and verification_plan_present:
        score += 0.05
    elif policy.required_verifications:
        reasons.append("verification plan is required for this task kind")
        score -= 0.10

    if source_count:
        score += min(0.15, source_count * 0.05)
    else:
        reasons.append("knowledge retrieval returned no sources")
        score -= 0.10

    if required_source_layers and not ungrounded_operationally:
        if source_layers.intersection(required_source_layers):
            score += 0.10
        else:
            reasons.append("required policy/source layer is missing")
            score -= 0.20

    if fresh_source_count:
        score += min(0.10, fresh_source_count * 0.05)
    elif EXECUTION_CONFIDENCE_REQUIRE_FRESH_SOURCES:
        reasons.append("no fresh sources available")
        score -= 0.10

    if non_operable_source_layers and not source_layers:
        reasons.append("only non-operable sources are grounding this action")
        requires_human_approval = True
        if risky_task:
            score -= 0.20

    if read_evidence_count >= policy.min_read_evidence:
        score += min(0.10, read_evidence_count * 0.05)
    else:
        reasons.append("insufficient read-only evidence gathered before write")
        score -= 0.10

    if warnings:
        score -= min(0.15, len(warnings) * 0.05)
        reasons.append("runtime warnings reduce confidence")

    raw_memory_bonus_cap = risk_adjustments.get("memory_bonus_cap", 0.08)
    memory_bonus_cap = float(raw_memory_bonus_cap if isinstance(raw_memory_bonus_cap, (int, float)) else 0.08)
    if memory_trust_score:
        score += min(memory_bonus_cap, memory_trust_score * memory_bonus_cap)
    if memory_trust_score and memory_explainable:
        score += 0.03
    elif memory_trust_score:
        reasons.append("memory recall is not explainable enough")
        score -= 0.05
    if memory_trust_score and memory_layers and set(memory_layers).issubset(_WEAK_MEMORY_LAYERS):
        reasons.append("only weak memory layers are supporting this action")
        requires_human_approval = True
    if memory_trust_score and memory_layers and set(memory_layers).intersection(_SUPPORTIVE_MEMORY_LAYERS):
        score += 0.04
    forbidden_memory_layers: list[str] = []
    if memory_profile:
        forbidden_memory_layers = [
            layer for layer in memory_layers if memory_profile.is_forbidden_for_action(layer, task_kind)
        ]
    if forbidden_memory_layers:
        reasons.append("memory profile forbids these layers for this action")
        requires_human_approval = True
        score -= 0.10
    if (
        bool(risk_adjustments.get("forces_human_on_weak_memory"))
        and memory_layers
        and set(memory_layers).issubset(_WEAK_MEMORY_LAYERS)
    ):
        requires_human_approval = True
    if bool(risk_adjustments.get("requires_operable_runbook_for_high_risk")) and not source_layers.intersection(
        {"canonical_policy", "approved_runbook"}
    ):
        reasons.append("high-risk action lacks operable canonical policy or approved runbook")
        requires_human_approval = True
        score -= 0.15

    if ungrounded_operationally:
        reasons.append("operationally ungrounded policy fallback")
        score -= 0.10
        requires_human_approval = True

    stale_sources_present = stale_sources_present or policy_stale_sources_present

    if stale_sources_present:
        reasons.append("stale sources present")
        score -= 0.15
        requires_human_approval = True

    if guardrail_count:
        reasons.append("approved guardrail matched this task context")
        score -= 0.20
        requires_human_approval = True

    score = max(0.0, min(1.0, score))
    blocked = False
    if EXECUTION_CONFIDENCE_REQUIRE_PLAN_FOR_WRITES and not plan_valid:
        blocked = True
    if read_evidence_count < policy.min_read_evidence:
        blocked = True
    if policy.read_only:
        blocked = True
    if policy.escalation_required and not (action_plan and action_plan.escalation.strip()):
        blocked = True
    if policy.requires_probable_cause and not (action_plan and action_plan.probable_cause.strip()):
        blocked = True
    if policy.requires_rollback and not (action_plan and action_plan.rollback.strip()):
        blocked = True
    if policy.required_verifications and not verification_plan_present:
        blocked = True
    if (
        required_source_layers
        and not ungrounded_operationally
        and not source_layers.intersection(required_source_layers)
    ):
        blocked = True
    if risky_task and non_operable_source_layers and not source_layers:
        blocked = True
    if bool(risk_adjustments.get("requires_operable_runbook_for_high_risk")) and not source_layers.intersection(
        {"canonical_policy", "approved_runbook"}
    ):
        blocked = True
    if score < EXECUTION_CONFIDENCE_THRESHOLD:
        requires_human_approval = True
        reasons.append("confidence below autonomous threshold")

    return ConfidenceReport(
        score=score,
        blocked=blocked,
        reasons=reasons,
        missing_fields=missing_fields if not plan_valid else [],
        source_count=source_count,
        fresh_source_count=fresh_source_count,
        read_evidence_count=read_evidence_count,
        plan_valid=plan_valid,
        task_kind=task_kind,
        source_layers=sorted(source_layers | non_operable_source_layers),
        required_source_layers=required_source_layers,
        operable_source_layers=sorted(source_layers),
        non_operable_source_layers=sorted(non_operable_source_layers),
        verification_required=list(policy.required_verifications),
        verification_plan_present=verification_plan_present,
        write_mode=policy.approval_mode,
        ungrounded_operationally=ungrounded_operationally,
        autonomy_tier=policy.autonomy_tier.value,
        stale_sources_present=stale_sources_present,
        guardrail_count=guardrail_count,
        requires_human_approval=requires_human_approval,
        memory_trust_score=memory_trust_score,
        memory_layers=memory_layers,
        memory_explainable=memory_explainable,
    )
