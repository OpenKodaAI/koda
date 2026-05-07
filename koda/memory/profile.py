"""Per-agent memory profiles resolved from TOML with safe defaults."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from koda.logging_config import get_logger
from koda.memory.config import MEMORY_MAX_EXTRACTION_ITEMS
from koda.memory.types import DEFAULT_TTL_DAYS, MemoryType

log = get_logger(__name__)


@dataclass(slots=True)
class MemoryProfile:
    """Policy and weighting envelope for a specific agent's memory behavior."""

    agent_id: str = "default"
    focus_domains: tuple[str, ...] = ()
    ignored_patterns: tuple[str, ...] = ()
    min_importance_by_type: dict[str, float] = field(default_factory=dict)
    ttl_overrides: dict[str, int] = field(default_factory=dict)
    recall_weights_by_type: dict[str, float] = field(default_factory=dict)
    promotion_policy: dict[str, Any] = field(default_factory=dict)
    max_items_per_turn: int = MEMORY_MAX_EXTRACTION_ITEMS
    max_items_per_type: dict[str, int] = field(default_factory=dict)
    risk_posture: str = "balanced"
    preferred_layers: tuple[str, ...] = ()
    forbidden_layers_for_actions: tuple[str, ...] = ()
    memory_density_target: str = "focused"

    def min_importance_for(self, memory_type: MemoryType) -> float:
        return float(self.min_importance_by_type.get(memory_type.value, 0.0))

    def ttl_days_for(self, memory_type: MemoryType) -> int:
        return int(self.ttl_overrides.get(memory_type.value, DEFAULT_TTL_DAYS[memory_type]))

    def recall_weight_for(self, memory_type: MemoryType) -> float:
        return float(self.recall_weights_by_type.get(memory_type.value, 1.0))

    def max_items_for(self, memory_type: MemoryType) -> int:
        return int(self.max_items_per_type.get(memory_type.value, self.max_items_per_turn))

    def preferred_layer_weight(self, layer: str) -> float:
        normalized = (layer or "").strip().lower()
        if normalized and normalized in {item.lower() for item in self.preferred_layers}:
            return 0.05
        return 0.0

    def is_forbidden_for_action(self, layer: str, task_kind: str) -> bool:
        normalized_layer = (layer or "").strip().lower()
        normalized_task = (task_kind or "").strip().lower()
        if not normalized_layer:
            return False
        if normalized_layer in {item.lower() for item in self.forbidden_layers_for_actions}:
            return True
        if normalized_task in {"deploy", "code_change", "bugfix", "db_write", "business_operation"}:
            return normalized_layer in {"conversational", "proactive"} and self.risk_posture == "conservative"
        return False

    def risk_posture_adjustments(self, task_kind: str) -> dict[str, object]:
        normalized_task = (task_kind or "").strip().lower()
        posture = (self.risk_posture or "balanced").strip().lower()
        high_risk_task = normalized_task in {"deploy", "code_change", "bugfix", "db_write", "business_operation"}
        if posture == "conservative":
            return {
                "requires_operable_runbook_for_high_risk": high_risk_task,
                "forces_human_on_weak_memory": True,
                "memory_bonus_cap": 0.04,
            }
        if posture == "aggressive":
            return {
                "requires_operable_runbook_for_high_risk": False,
                "forces_human_on_weak_memory": False,
                "memory_bonus_cap": 0.10,
            }
        return {
            "requires_operable_runbook_for_high_risk": high_risk_task and normalized_task == "deploy",
            "forces_human_on_weak_memory": high_risk_task,
            "memory_bonus_cap": 0.08,
        }

    def density_limits(self) -> tuple[int, int]:
        density = (self.memory_density_target or "focused").strip().lower()
        if density == "sparse":
            return (5, 2)
        if density == "dense":
            return (12, 5)
        return (8, 3)

    def should_ignore(self, content: str) -> bool:
        lowered = " ".join(content.lower().split()).strip(" .,!?:;")
        for pattern in self.ignored_patterns:
            normalized_pattern = " ".join(pattern.lower().split()).strip(" .,!?:;")
            if not normalized_pattern:
                continue
            if lowered == normalized_pattern:
                return True
        return False


def _normalize_mapping(raw: dict[str, Any], *, coerce: Callable[[Any], Any] = float) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in raw.items():
        try:
            memory_type = MemoryType(str(key).lower())
        except ValueError:
            continue
        try:
            normalized[memory_type.value] = coerce(value)
        except (TypeError, ValueError):
            continue
    return normalized


def _normalize_profile(agent_id: str, data: dict[str, Any]) -> MemoryProfile:
    ignored = tuple(str(item).strip() for item in data.get("ignored_patterns", []) if str(item).strip())
    focus = tuple(str(item).strip() for item in data.get("focus_domains", []) if str(item).strip())
    return MemoryProfile(
        agent_id=agent_id,
        focus_domains=focus,
        ignored_patterns=ignored,
        min_importance_by_type=_normalize_mapping(dict(data.get("min_importance_by_type", {}))),
        ttl_overrides=_normalize_mapping(dict(data.get("ttl_overrides", {})), coerce=int),
        recall_weights_by_type=_normalize_mapping(dict(data.get("recall_weights_by_type", {}))),
        promotion_policy=dict(data.get("promotion_policy", {})),
        max_items_per_turn=int(data.get("max_items_per_turn", MEMORY_MAX_EXTRACTION_ITEMS)),
        max_items_per_type=_normalize_mapping(dict(data.get("max_items_per_type", {})), coerce=int),
        risk_posture=str(data.get("risk_posture", "balanced")),
        preferred_layers=tuple(str(item).strip() for item in data.get("preferred_layers", []) if str(item).strip()),
        forbidden_layers_for_actions=tuple(
            str(item).strip() for item in data.get("forbidden_layers_for_actions", []) if str(item).strip()
        ),
        memory_density_target=str(data.get("memory_density_target", "focused")),
    )


def _default_profile(agent_id: str) -> MemoryProfile:
    return MemoryProfile(
        agent_id=agent_id,
        ignored_patterns=(
            "obrigado",
            "thank you",
            "ok",
            "certo",
            "entendido",
            "understood",
        ),
        min_importance_by_type={
            MemoryType.EVENT.value: 0.45,
            MemoryType.TASK.value: 0.50,
            MemoryType.PROCEDURE.value: 0.65,
        },
        recall_weights_by_type={
            MemoryType.PROCEDURE.value: 1.15,
            MemoryType.DECISION.value: 1.10,
            MemoryType.TASK.value: 1.05,
        },
        promotion_policy={
            "observed_pattern_requires_review": True,
            "minimum_verified_successes": 3,
        },
        max_items_per_turn=min(6, MEMORY_MAX_EXTRACTION_ITEMS),
        max_items_per_type={
            MemoryType.PROCEDURE.value: 2,
            MemoryType.TASK.value: 2,
        },
        risk_posture="balanced",
        preferred_layers=("episodic", "procedural", "conversational"),
        forbidden_layers_for_actions=("proactive",),
        memory_density_target="focused",
    )


def load_memory_profile(agent_id: str | None) -> MemoryProfile:
    """Load the agent-specific memory profile with default fallback."""
    resolved_agent_id = (agent_id or "default").strip() or "default"
    inline_toml = os.environ.get("MEMORY_PROFILE_TOML", "").strip()
    if inline_toml:
        try:
            data = tomllib.loads(inline_toml)
            profile = _normalize_profile(resolved_agent_id, data)
        except Exception:
            log.exception("memory_profile_inline_parse_error", agent_id=resolved_agent_id)
            return _default_profile(resolved_agent_id)
        log.info("memory_profile_loaded_inline", agent_id=resolved_agent_id)
        return profile
    return _default_profile(resolved_agent_id)
