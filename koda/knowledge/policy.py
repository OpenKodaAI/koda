"""Task classification and execution policy defaults for grounded autonomy."""

from __future__ import annotations

import json
import os
import re
from dataclasses import replace
from typing import Any

from koda.knowledge.types import AutonomyTier, EffectiveExecutionPolicy, KnowledgeLayer

_TASK_KIND_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("deploy", re.compile(r"\b(deploy|release|production|rollback|ship|publish)\b", re.I)),
    ("bugfix", re.compile(r"\b(bug|fix|erro|falha|debug|hotfix|incident)\b", re.I)),
    ("code_change", re.compile(r"\b(refactor|implement|feature|edit|change|alterar|ajustar|code)\b", re.I)),
    ("review", re.compile(r"\b(review|pr|pull request|code review)\b", re.I)),
    ("investigation", re.compile(r"\b(analyze|investigate|root cause|diagnose|investigar|analysis)\b", re.I)),
]


def classify_task_kind(query: str) -> str:
    """Classify a task into a reusable operational bucket."""
    for task_kind, pattern in _TASK_KIND_PATTERNS:
        if pattern.search(query):
            return task_kind
    return "general"


def sanitize_policy_overrides(overrides: dict[str, Any] | None) -> dict[str, Any]:
    """Validate and normalize runbook policy overrides before persistence/runtime use."""
    if not overrides:
        return {}

    sanitized: dict[str, Any] = {}
    for key, value in overrides.items():
        if key == "min_read_evidence":
            parsed = int(value)
            if parsed < 1 or parsed > 20:
                raise ValueError("min_read_evidence must be between 1 and 20")
            sanitized[key] = parsed
        elif key == "required_layers":
            if not isinstance(value, (list, tuple)):
                raise ValueError("required_layers must be a list")
            sanitized[key] = [KnowledgeLayer(str(item)).value for item in value]
        elif key == "required_verifications":
            if not isinstance(value, (list, tuple)):
                raise ValueError("required_verifications must be a list")
            sanitized[key] = [str(item).strip() for item in value if str(item).strip()]
        elif key in {"requires_rollback", "requires_probable_cause"}:
            sanitized[key] = bool(value)
        elif key == "approval_mode":
            normalized = str(value).strip()
            if normalized not in {"read_only", "supervised", "guarded", "escalation_required"}:
                raise ValueError("approval_mode is invalid")
            sanitized[key] = normalized
        elif key == "max_source_age_days":
            parsed = int(value)
            if parsed < 1 or parsed > 3650:
                raise ValueError("max_source_age_days must be between 1 and 3650")
            sanitized[key] = parsed
        elif key == "autonomy_tier":
            sanitized[key] = AutonomyTier(str(value).lower()).value
        else:
            raise ValueError(f"unsupported policy override: {key}")
    return sanitized


def _load_runtime_autonomy_policy() -> dict[str, Any]:
    raw = os.environ.get("AGENT_AUTONOMY_POLICY_JSON", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _apply_runtime_autonomy_policy(
    base_policy: EffectiveExecutionPolicy,
    *,
    task_kind: str,
) -> EffectiveExecutionPolicy:
    payload = _load_runtime_autonomy_policy()
    if not payload:
        return base_policy

    patch: dict[str, Any] = {}
    default_approval_mode = str(payload.get("default_approval_mode") or "").strip().lower()
    if default_approval_mode in {"read_only", "supervised", "guarded", "escalation_required"}:
        patch["approval_mode"] = default_approval_mode

    default_autonomy_tier = str(payload.get("default_autonomy_tier") or "").strip().lower()
    if default_autonomy_tier in {item.value for item in AutonomyTier}:
        patch["autonomy_tier"] = AutonomyTier(default_autonomy_tier)

    task_overrides = payload.get("task_overrides")
    if isinstance(task_overrides, dict):
        candidate_override = task_overrides.get(task_kind) or task_overrides.get("default")
        if isinstance(candidate_override, dict):
            try:
                sanitized = sanitize_policy_overrides(candidate_override)
            except ValueError:
                sanitized = {}
            if "approval_mode" in sanitized:
                patch["approval_mode"] = str(sanitized["approval_mode"])
            if "autonomy_tier" in sanitized:
                patch["autonomy_tier"] = AutonomyTier(str(sanitized["autonomy_tier"]))
            for key in (
                "min_read_evidence",
                "required_layers",
                "required_verifications",
                "requires_rollback",
                "requires_probable_cause",
                "max_source_age_days",
            ):
                if key in sanitized:
                    patch[key] = sanitized[key]

    return replace(base_policy, **patch) if patch else base_policy


def default_execution_policy(task_kind: str, *, environment: str = "") -> EffectiveExecutionPolicy:
    """Return policy defaults for the classified task kind."""
    normalized_env = environment.lower()
    is_production = normalized_env in {"prod", "production"}
    defaults: dict[str, EffectiveExecutionPolicy] = {
        "deploy": EffectiveExecutionPolicy(
            task_kind="deploy",
            autonomy_tier=AutonomyTier.T1 if is_production else AutonomyTier.T2,
            approval_mode="supervised" if is_production else "guarded",
            min_read_evidence=2,
            required_layers=(KnowledgeLayer.CANONICAL_POLICY, KnowledgeLayer.APPROVED_RUNBOOK),
            required_verifications=("read_back", "health_check"),
            requires_rollback=True,
            max_source_age_days=30,
        ),
        "code_change": EffectiveExecutionPolicy(
            task_kind="code_change",
            autonomy_tier=AutonomyTier.T2,
            approval_mode="guarded",
            min_read_evidence=2,
            required_layers=(KnowledgeLayer.CANONICAL_POLICY, KnowledgeLayer.APPROVED_RUNBOOK),
            required_verifications=("read_back", "tests"),
            max_source_age_days=45,
        ),
        "bugfix": EffectiveExecutionPolicy(
            task_kind="bugfix",
            autonomy_tier=AutonomyTier.T2,
            approval_mode="guarded",
            min_read_evidence=2,
            required_layers=(KnowledgeLayer.CANONICAL_POLICY, KnowledgeLayer.APPROVED_RUNBOOK),
            required_verifications=("read_back", "tests"),
            requires_probable_cause=True,
            max_source_age_days=45,
        ),
        "review": EffectiveExecutionPolicy(
            task_kind="review",
            autonomy_tier=AutonomyTier.T0,
            min_read_evidence=1,
            approval_mode="read_only",
        ),
        "investigation": EffectiveExecutionPolicy(
            task_kind="investigation",
            autonomy_tier=AutonomyTier.T0,
            min_read_evidence=1,
            approval_mode="escalation_required",
        ),
    }
    base_policy = defaults.get(
        task_kind,
        EffectiveExecutionPolicy(
            task_kind=task_kind,
            autonomy_tier=AutonomyTier.T1,
            approval_mode="supervised",
        ),
    )
    return _apply_runtime_autonomy_policy(base_policy, task_kind=task_kind)


ExecutionPolicy = EffectiveExecutionPolicy
