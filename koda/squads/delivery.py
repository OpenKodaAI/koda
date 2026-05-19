"""Squad delivery v1 contract.

This module defines the stable envelope for a persistent Squad Room delivery:
routing, participant suitability, lifecycle state, and auditable events. It is
intentionally small and additive so existing squad primitives can emit the
contract without a broad orchestration rewrite.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from koda.squads.capabilities import CapabilitySummary

if TYPE_CHECKING:
    from koda.squads.semantic_router import SemanticRoutingResult

SQUAD_DELIVERY_SCHEMA_VERSION = "squad_delivery.v1"

SquadDeliveryStatus = Literal[
    "received",
    "routed",
    "coordinating",
    "delegated",
    "waiting_for_replies",
    "synthesizing",
    "completed",
    "blocked",
    "timed_out",
    "failed",
]
SquadDeliveryIntent = Literal["awareness", "proposal", "execution", "synthesis"]

VALID_DELIVERY_STATUSES: frozenset[str] = frozenset(
    {
        "received",
        "routed",
        "coordinating",
        "delegated",
        "waiting_for_replies",
        "synthesizing",
        "completed",
        "blocked",
        "timed_out",
        "failed",
    }
)

VALID_DELIVERY_INTENTS: frozenset[str] = frozenset({"awareness", "proposal", "execution", "synthesis"})

SOURCE_STATUS_DEFAULTS: dict[str, SquadDeliveryStatus] = {
    "channel_gateway": "blocked",
    "room_binding": "received",
    "explicit_mention": "routed",
    "telegram_mention": "routed",
    "web_mention": "routed",
    "mention_unresolved": "blocked",
    "reply_obligation": "routed",
    "reply": "routed",
    "coordinator_engine": "delegated",
    "coordination_decision": "coordinating",
    "semantic": "routed",
    "proposal_arbitration": "routed",
    "coordinator": "routed",
    "fallback": "routed",
    "squad_triage": "received",
}


def normalize_delivery_status(value: Any, default: SquadDeliveryStatus = "received") -> SquadDeliveryStatus:
    status = str(value or "").strip().lower()
    if status in VALID_DELIVERY_STATUSES:
        return status  # type: ignore[return-value]
    return default


def normalize_delivery_intent(value: Any, default: SquadDeliveryIntent = "execution") -> SquadDeliveryIntent:
    intent = str(value or "").strip().lower()
    if intent in VALID_DELIVERY_INTENTS:
        return intent  # type: ignore[return-value]
    return default


def delivery_status_for_source(source: str, *, has_targets: bool = True) -> SquadDeliveryStatus:
    if not has_targets:
        return "blocked"
    return SOURCE_STATUS_DEFAULTS.get(str(source or "").strip().lower(), "routed")


@dataclass(frozen=True)
class SquadMemberProfile:
    """Routing-facing profile derived from an agent capability summary."""

    agent_id: str
    display_name: str
    role: str
    domains: list[str] = field(default_factory=list)
    primary_outcomes: list[str] = field(default_factory=list)
    tool_categories: list[str] = field(default_factory=list)
    allowed_tool_ids: list[str] = field(default_factory=list)
    integration_ids: list[str] = field(default_factory=list)
    delegate_when: str = ""
    do_not_delegate: str = ""
    is_coordinator: bool = False
    preferred_provider: str = ""
    preferred_model: str = ""
    cost_weight: float = 1.0
    load_score: float = 0.0
    quality_score: float = 0.5
    recent_success_rate: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_summary(
        cls,
        summary: CapabilitySummary,
        *,
        operational: Mapping[str, Any] | None = None,
    ) -> SquadMemberProfile:
        op = dict(operational or {})
        return cls(
            agent_id=summary.agent_id,
            display_name=summary.display_name,
            role=summary.role,
            domains=list(summary.domains),
            primary_outcomes=list(summary.primary_outcomes),
            tool_categories=list(summary.tool_categories),
            allowed_tool_ids=list(summary.allowed_tool_ids),
            integration_ids=list(summary.integration_ids),
            delegate_when=summary.delegate_when,
            do_not_delegate=summary.do_not_delegate,
            is_coordinator=summary.is_coordinator,
            preferred_provider=str(op.get("preferred_provider") or summary.preferred_provider or ""),
            preferred_model=str(op.get("preferred_model") or summary.preferred_model or ""),
            cost_weight=_bounded_float(op.get("cost_weight"), default=summary.cost_weight, low=0.1, high=10.0),
            load_score=_bounded_float(op.get("load_score"), default=summary.load_score, low=0.0, high=1.0),
            quality_score=_bounded_float(op.get("quality_score"), default=summary.quality_score, low=0.0, high=1.0),
            recent_success_rate=_optional_bounded_float(
                op.get("recent_success_rate"),
                default=summary.recent_success_rate,
                low=0.0,
                high=1.0,
            ),
            metadata={**dict(summary.metadata or {}), **dict(op.get("metadata") or {})},
        )

    def suitability_score(self, *, semantic_score: float = 0.0) -> float:
        """Blend semantic relevance with operational signals.

        The weights are deliberately conservative: semantic fit remains the
        dominant signal, while load/cost can only break ties or avoid expensive
        overloaded agents when comparable specialists exist.
        """

        success = self.recent_success_rate if self.recent_success_rate is not None else self.quality_score
        return (
            max(0.0, float(semantic_score)) * 1.0
            + max(0.0, min(1.0, self.quality_score)) * 0.12
            + max(0.0, min(1.0, success)) * 0.08
            - max(0.0, min(1.0, self.load_score)) * 0.16
            - max(0.0, min(10.0, self.cost_weight)) * 0.015
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "display_name": self.display_name,
            "role": self.role,
            "domains": list(self.domains),
            "primary_outcomes": list(self.primary_outcomes),
            "tool_categories": list(self.tool_categories),
            "allowed_tool_ids": list(self.allowed_tool_ids),
            "integration_ids": list(self.integration_ids),
            "delegate_when": self.delegate_when,
            "do_not_delegate": self.do_not_delegate,
            "is_coordinator": self.is_coordinator,
            "preferred_provider": self.preferred_provider,
            "preferred_model": self.preferred_model,
            "cost_weight": self.cost_weight,
            "load_score": self.load_score,
            "quality_score": self.quality_score,
            "recent_success_rate": self.recent_success_rate,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class SquadDeliveryRouteDecision:
    source: str
    targets: list[str]
    status: SquadDeliveryStatus = "routed"
    delivery_intent: SquadDeliveryIntent = "execution"
    confidence: float = 0.0
    reason: str = ""
    coordinator_agent_id: str | None = None
    reply_to_agent_id: str | None = None
    parent_message_id: str | None = None
    explicit_mentions: list[str] = field(default_factory=list)
    unresolved_mentions: list[str] = field(default_factory=list)
    ambiguous_mentions: dict[str, list[str]] = field(default_factory=dict)
    semantic_available: bool = False
    semantic_model: str = ""
    semantic_top_score: float = 0.0
    final_response_strategy: str = ""
    selected_profiles: list[SquadMemberProfile] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SQUAD_DELIVERY_SCHEMA_VERSION,
            "source": self.source,
            "targets": list(self.targets),
            "status": self.status,
            "delivery_intent": self.delivery_intent,
            "confidence": round(float(self.confidence), 6),
            "reason": self.reason,
            "coordinator_agent_id": self.coordinator_agent_id,
            "reply_to_agent_id": self.reply_to_agent_id,
            "parent_message_id": self.parent_message_id,
            "explicit_mentions": list(self.explicit_mentions),
            "unresolved_mentions": list(self.unresolved_mentions),
            "ambiguous_mentions": {key: list(value) for key, value in self.ambiguous_mentions.items()},
            "semantic_available": self.semantic_available,
            "semantic_model": self.semantic_model,
            "semantic_top_score": round(float(self.semantic_top_score), 6),
            "final_response_strategy": self.final_response_strategy,
            "selected_profiles": [profile.to_dict() for profile in self.selected_profiles],
        }


@dataclass(frozen=True)
class SquadDeliveryEvent:
    event_type: str
    status: SquadDeliveryStatus
    source: str
    targets: list[str] = field(default_factory=list)
    delivery_intent: SquadDeliveryIntent = "execution"
    thread_id: str = ""
    squad_id: str = ""
    parent_message_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SQUAD_DELIVERY_SCHEMA_VERSION,
            "event_type": self.event_type,
            "status": self.status,
            "delivery_intent": self.delivery_intent,
            "source": self.source,
            "targets": list(self.targets),
            "thread_id": self.thread_id,
            "squad_id": self.squad_id,
            "parent_message_id": self.parent_message_id,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True)
class SquadDeliveryState:
    delivery_id: str
    thread_id: str
    squad_id: str
    status: SquadDeliveryStatus = "received"
    route_decision: SquadDeliveryRouteDecision | None = None
    task_ids: list[str] = field(default_factory=list)
    reply_obligation_ids: list[str] = field(default_factory=list)
    child_run_ids: list[str] = field(default_factory=list)
    final_response_strategy: str = ""
    events: list[SquadDeliveryEvent] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SQUAD_DELIVERY_SCHEMA_VERSION,
            "delivery_id": self.delivery_id,
            "thread_id": self.thread_id,
            "squad_id": self.squad_id,
            "status": self.status,
            "route_decision": self.route_decision.to_dict() if self.route_decision else None,
            "task_ids": list(self.task_ids),
            "reply_obligation_ids": list(self.reply_obligation_ids),
            "child_run_ids": list(self.child_run_ids),
            "final_response_strategy": self.final_response_strategy,
            "events": [event.to_dict() for event in self.events],
        }


def build_member_profiles(
    summaries: Iterable[CapabilitySummary],
    *,
    operational_by_agent: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[SquadMemberProfile]:
    operations = {str(key).upper(): value for key, value in dict(operational_by_agent or {}).items()}
    return [
        SquadMemberProfile.from_summary(summary, operational=operations.get(summary.agent_id)) for summary in summaries
    ]


def rank_targets_for_delivery(
    targets: Iterable[str],
    *,
    member_profiles: Iterable[SquadMemberProfile] | None = None,
    semantic_result: SemanticRoutingResult | None = None,
) -> list[str]:
    ordered = _dedupe([str(target) for target in targets if str(target or "").strip()])
    if not ordered:
        return []
    profiles = {profile.agent_id: profile for profile in member_profiles or []}
    semantic_scores = _semantic_score_map(semantic_result)

    def _rank_key(agent_id: str) -> tuple[float, int, str]:
        profile = profiles.get(agent_id)
        score = semantic_scores.get(agent_id, 0.0)
        suitability = profile.suitability_score(semantic_score=score) if profile is not None else score
        return (-suitability, ordered.index(agent_id), agent_id)

    return sorted(ordered, key=_rank_key)


def build_route_decision(
    *,
    source: str,
    targets: Iterable[str],
    delivery_intent: SquadDeliveryIntent | str = "execution",
    status: SquadDeliveryStatus | str | None = None,
    reason: str = "",
    coordinator_agent_id: str | None = None,
    reply_to_agent_id: str | None = None,
    parent_message_id: str | None = None,
    explicit_mentions: Iterable[str] | None = None,
    unresolved_mentions: Iterable[str] | None = None,
    ambiguous_mentions: Mapping[str, Iterable[str]] | None = None,
    semantic_result: SemanticRoutingResult | None = None,
    member_profiles: Iterable[SquadMemberProfile] | None = None,
    final_response_strategy: str = "",
) -> SquadDeliveryRouteDecision:
    selected_targets = _dedupe([str(target) for target in targets if str(target or "").strip()])
    ranked_targets = rank_targets_for_delivery(
        selected_targets,
        member_profiles=member_profiles,
        semantic_result=semantic_result,
    )
    profiles_by_agent = {profile.agent_id: profile for profile in member_profiles or []}
    semantic_top_score = (
        float(getattr(semantic_result, "top_score", 0.0) or 0.0) if semantic_result is not None else 0.0
    )
    computed_status = normalize_delivery_status(
        status,
        default=delivery_status_for_source(source, has_targets=bool(ranked_targets)),
    )
    return SquadDeliveryRouteDecision(
        source=str(source or "fallback"),
        targets=ranked_targets,
        status=computed_status,
        delivery_intent=normalize_delivery_intent(delivery_intent),
        confidence=semantic_top_score,
        reason=reason,
        coordinator_agent_id=coordinator_agent_id,
        reply_to_agent_id=reply_to_agent_id,
        parent_message_id=parent_message_id,
        explicit_mentions=_dedupe([str(value) for value in explicit_mentions or [] if str(value or "").strip()]),
        unresolved_mentions=_dedupe([str(value) for value in unresolved_mentions or [] if str(value or "").strip()]),
        ambiguous_mentions={
            str(key): [str(item) for item in value] for key, value in (ambiguous_mentions or {}).items()
        },
        semantic_available=bool(getattr(semantic_result, "available", False)) if semantic_result is not None else False,
        semantic_model=str(getattr(semantic_result, "model_name", "") or "") if semantic_result is not None else "",
        semantic_top_score=semantic_top_score,
        final_response_strategy=final_response_strategy,
        selected_profiles=[profiles_by_agent[target] for target in ranked_targets if target in profiles_by_agent],
    )


def delivery_metric(
    *,
    event_type: str,
    status: str,
    source: str,
) -> None:
    try:
        from koda.services.metrics import SQUAD_DELIVERY_EVENTS

        SQUAD_DELIVERY_EVENTS.labels(
            event_type=str(event_type or "unknown"),
            status=str(status or "unknown"),
            source=str(source or "unknown"),
        ).inc()
    except Exception:
        return


def _semantic_score_map(semantic_result: SemanticRoutingResult | None) -> dict[str, float]:
    if semantic_result is None:
        return {}
    scores = getattr(semantic_result, "scores", []) or []
    out: dict[str, float] = {}
    for item in scores:
        agent_id = str(getattr(item, "agent_id", "") or "")
        if not agent_id:
            continue
        try:
            out[agent_id] = float(getattr(item, "score", 0.0) or 0.0)
        except (TypeError, ValueError):
            out[agent_id] = 0.0
    return out


def _bounded_float(value: Any, *, default: Any, low: float, high: float) -> float:
    try:
        parsed = float(value if value is not None else default)
    except (TypeError, ValueError):
        parsed = float(default if default is not None else low)
    return max(low, min(high, parsed))


def _optional_bounded_float(value: Any, *, default: Any, low: float, high: float) -> float | None:
    candidate = value if value is not None else default
    if candidate is None:
        return None
    return _bounded_float(candidate, default=default, low=low, high=high)


def _dedupe(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        out.append(value)
        seen.add(value)
    return out
