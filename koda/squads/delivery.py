"""Squad delivery v1 contract.

This module defines the stable envelope for a persistent Squad Room delivery:
routing, participant suitability, lifecycle state, and auditable events. It is
intentionally small and additive so existing squad primitives can emit the
contract without a broad orchestration rewrite.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Literal

from koda.squads.capabilities import CapabilitySummary

if TYPE_CHECKING:
    from koda.squads.semantic_router import SemanticRoutingResult

SQUAD_DELIVERY_SCHEMA_VERSION = "squad_delivery.v1"
HANDOFF_EVENT_SCHEMA_VERSION = "handoff_event.v1"
ROUTE_OUTCOME_SCHEMA_VERSION = "route_outcome.v1"

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
VALID_HANDOFF_KINDS: frozenset[str] = frozenset({"transfer", "consult", "parallel_consult", "return"})
VALID_HANDOFF_STATUSES: frozenset[str] = frozenset(
    {"requested", "accepted", "declined", "timed_out", "returned", "failed"}
)

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
    timeout_rate: float = 0.0
    eval_performance_score: float | None = None
    tool_access_score: float = 1.0
    skill_access_score: float = 1.0
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
            timeout_rate=_bounded_float(op.get("timeout_rate"), default=0.0, low=0.0, high=1.0),
            eval_performance_score=_optional_bounded_float(
                op.get("eval_performance_score"),
                default=None,
                low=0.0,
                high=1.0,
            ),
            tool_access_score=_bounded_float(op.get("tool_access_score"), default=1.0, low=0.0, high=1.0),
            skill_access_score=_bounded_float(op.get("skill_access_score"), default=1.0, low=0.0, high=1.0),
            metadata={**dict(summary.metadata or {}), **dict(op.get("metadata") or {})},
        )

    def suitability_score(self, *, semantic_score: float = 0.0) -> float:
        """Blend semantic relevance with operational signals.

        The weights are deliberately conservative: semantic fit remains the
        dominant signal, while load/cost can only break ties or avoid expensive
        overloaded agents when comparable specialists exist.
        """

        success = self.recent_success_rate if self.recent_success_rate is not None else self.quality_score
        eval_score = self.eval_performance_score if self.eval_performance_score is not None else self.quality_score
        return (
            max(0.0, float(semantic_score)) * 1.0
            + max(0.0, min(1.0, self.quality_score)) * 0.12
            + max(0.0, min(1.0, success)) * 0.08
            + max(0.0, min(1.0, eval_score)) * 0.06
            + max(0.0, min(1.0, self.tool_access_score)) * 0.04
            + max(0.0, min(1.0, self.skill_access_score)) * 0.03
            - max(0.0, min(1.0, self.load_score)) * 0.16
            - max(0.0, min(1.0, self.timeout_rate)) * 0.18
            - max(0.0, min(10.0, self.cost_weight)) * 0.015
        )

    def route_quality_inputs(self, *, semantic_score: float = 0.0) -> dict[str, Any]:
        return {
            "semantic_score": round(float(semantic_score), 6),
            "quality_score": round(float(self.quality_score), 6),
            "recent_success_rate": self.recent_success_rate,
            "timeout_rate": round(float(self.timeout_rate), 6),
            "load_score": round(float(self.load_score), 6),
            "cost_weight": round(float(self.cost_weight), 6),
            "eval_performance_score": self.eval_performance_score,
            "tool_access_score": round(float(self.tool_access_score), 6),
            "skill_access_score": round(float(self.skill_access_score), 6),
        }

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
            "timeout_rate": self.timeout_rate,
            "eval_performance_score": self.eval_performance_score,
            "tool_access_score": self.tool_access_score,
            "skill_access_score": self.skill_access_score,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RouteOutcome:
    """Persistable quality evidence for a routed squad delivery."""

    outcome_id: str
    agent_id: str
    squad_id: str = ""
    task_category: str = ""
    route_source: str = ""
    status: str = "success"
    handoff_returned: bool = False
    timeout: bool = False
    cost_usd: float | None = None
    latency_ms: float | None = None
    eval_score: float | None = None
    load_snapshot: float | None = None
    required_tool_match: bool | None = None
    required_skill_match: bool | None = None
    run_graph_node_id: str | None = None
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ROUTE_OUTCOME_SCHEMA_VERSION,
            "outcome_id": self.outcome_id,
            "agent_id": self.agent_id,
            "squad_id": self.squad_id,
            "task_category": self.task_category,
            "route_source": self.route_source,
            "status": _normalize_route_outcome_status(self.status),
            "handoff_returned": bool(self.handoff_returned),
            "timeout": bool(self.timeout),
            "cost_usd": self.cost_usd,
            "latency_ms": self.latency_ms,
            "eval_score": self.eval_score,
            "load_snapshot": self.load_snapshot,
            "required_tool_match": self.required_tool_match,
            "required_skill_match": self.required_skill_match,
            "run_graph_node_id": self.run_graph_node_id,
            "created_at": self.created_at,
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
    candidate_scores: list[dict[str, Any]] = field(default_factory=list)
    excluded_candidates: list[dict[str, Any]] = field(default_factory=list)
    route_explanation: dict[str, Any] = field(default_factory=dict)
    required_tools: list[str] = field(default_factory=list)
    required_skills: list[str] = field(default_factory=list)
    quality_inputs: dict[str, Any] = field(default_factory=dict)

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
            "candidate_scores": [dict(item) for item in self.candidate_scores],
            "excluded_candidates": [dict(item) for item in self.excluded_candidates],
            "route_explanation": dict(self.route_explanation),
            "required_tools": list(self.required_tools),
            "required_skills": list(self.required_skills),
            "quality_inputs": dict(self.quality_inputs),
        }


@dataclass(frozen=True)
class HandoffEvent:
    handoff_id: str
    thread_id: str
    source_agent_id: str
    destination_agent_ids: list[str]
    reason: str
    handoff_kind: str = "consult"
    context_policy: dict[str, Any] = field(default_factory=dict)
    deadline: str | None = None
    return_criteria: list[str] = field(default_factory=list)
    status: str = "requested"
    run_graph_node_id: str | None = None
    correlation_id: str | None = None
    parent_message_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": HANDOFF_EVENT_SCHEMA_VERSION,
            "handoff_id": self.handoff_id,
            "thread_id": self.thread_id,
            "source_agent_id": self.source_agent_id,
            "destination_agent_ids": list(self.destination_agent_ids),
            "reason": self.reason,
            "handoff_kind": normalize_handoff_kind(self.handoff_kind),
            "context_policy": dict(self.context_policy),
            "deadline": self.deadline,
            "return_criteria": list(self.return_criteria),
            "status": normalize_handoff_status(self.status),
            "run_graph_node_id": self.run_graph_node_id,
            "correlation_id": self.correlation_id,
            "parent_message_id": self.parent_message_id,
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


def build_route_outcome(
    *,
    outcome_id: str,
    agent_id: str,
    squad_id: str = "",
    task_category: str = "",
    route_source: str = "",
    status: str = "success",
    handoff_returned: bool = False,
    timeout: bool = False,
    cost_usd: float | None = None,
    latency_ms: float | None = None,
    eval_score: float | None = None,
    load_snapshot: float | None = None,
    required_tool_match: bool | None = None,
    required_skill_match: bool | None = None,
    run_graph_node_id: str | None = None,
    created_at: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> RouteOutcome:
    outcome = RouteOutcome(
        outcome_id=str(outcome_id or "").strip(),
        agent_id=str(agent_id or "").strip(),
        squad_id=str(squad_id or "").strip(),
        task_category=str(task_category or "").strip(),
        route_source=str(route_source or "").strip(),
        status=_normalize_route_outcome_status(status),
        handoff_returned=bool(handoff_returned),
        timeout=bool(timeout),
        cost_usd=_optional_bounded_float(cost_usd, default=None, low=0.0, high=1_000_000.0),
        latency_ms=_optional_bounded_float(latency_ms, default=None, low=0.0, high=86_400_000.0),
        eval_score=_optional_bounded_float(eval_score, default=None, low=0.0, high=1.0),
        load_snapshot=_optional_bounded_float(load_snapshot, default=None, low=0.0, high=1.0),
        required_tool_match=required_tool_match if isinstance(required_tool_match, bool) else None,
        required_skill_match=required_skill_match if isinstance(required_skill_match, bool) else None,
        run_graph_node_id=str(run_graph_node_id).strip() if run_graph_node_id else None,
        created_at=str(created_at or "").strip(),
        metadata=dict(metadata or {}),
    )
    _route_outcome_metric(outcome)
    return outcome


def _route_outcome_metric(outcome: RouteOutcome) -> None:
    try:
        from koda.services.metrics import ROUTE_OUTCOME_EVENTS

        ROUTE_OUTCOME_EVENTS.labels(
            agent_id=outcome.agent_id or "unknown",
            route_source=outcome.route_source or "unknown",
            status=outcome.status or "unknown",
            timeout="true" if outcome.timeout else "false",
        ).inc()
    except Exception:
        return


def summarize_route_quality_history(
    outcomes: Iterable[Mapping[str, Any] | RouteOutcome],
) -> dict[str, dict[str, Any]]:
    """Aggregate ``route_outcome.v1`` records into bounded scorer inputs."""

    grouped: dict[str, dict[str, Any]] = {}
    for raw_item in outcomes:
        item = raw_item.to_dict() if hasattr(raw_item, "to_dict") else dict(raw_item)
        agent_id = str(item.get("agent_id") or "").strip()
        if not agent_id:
            continue
        current = grouped.setdefault(
            agent_id,
            {
                "schema_version": ROUTE_OUTCOME_SCHEMA_VERSION,
                "agent_id": agent_id,
                "outcome_count": 0,
                "success_count": 0,
                "timeout_count": 0,
                "failure_count": 0,
                "handoff_return_count": 0,
                "cost_values": [],
                "latency_values": [],
                "eval_values": [],
                "load_values": [],
                "run_graph_node_ids": [],
            },
        )
        status = _normalize_route_outcome_status(item.get("status"))
        current["outcome_count"] += 1
        if status == "success":
            current["success_count"] += 1
        if status == "timeout" or bool(item.get("timeout")):
            current["timeout_count"] += 1
        if status == "failure":
            current["failure_count"] += 1
        if bool(item.get("handoff_returned")):
            current["handoff_return_count"] += 1
        for value_field, bucket, high in (
            ("cost_usd", "cost_values", 1_000_000.0),
            ("latency_ms", "latency_values", 86_400_000.0),
            ("eval_score", "eval_values", 1.0),
            ("load_snapshot", "load_values", 1.0),
        ):
            value = _optional_bounded_float(item.get(value_field), default=None, low=0.0, high=high)
            if value is not None:
                current[bucket].append(value)
        node_id = str(item.get("run_graph_node_id") or "").strip()
        if node_id and node_id not in current["run_graph_node_ids"]:
            current["run_graph_node_ids"].append(node_id)
    for item in grouped.values():
        count = max(1, int(item["outcome_count"]))
        item["success_rate"] = round(float(item["success_count"]) / count, 6)
        item["timeout_rate"] = round(float(item["timeout_count"]) / count, 6)
        item["failure_rate"] = round(float(item["failure_count"]) / count, 6)
        item["handoff_return_rate"] = round(float(item["handoff_return_count"]) / count, 6)
        item["avg_cost_usd"] = _mean_or_none(item.pop("cost_values"))
        item["avg_latency_ms"] = _mean_or_none(item.pop("latency_values"))
        item["avg_eval_score"] = _mean_or_none(item.pop("eval_values"))
        item["avg_load"] = _mean_or_none(item.pop("load_values"))
    return grouped


def rank_targets_for_delivery(
    targets: Iterable[str],
    *,
    member_profiles: Iterable[SquadMemberProfile] | None = None,
    semantic_result: SemanticRoutingResult | None = None,
    route_quality_history: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[str]:
    ordered = _dedupe([str(target) for target in targets if str(target or "").strip()])
    if not ordered:
        return []
    profiles = {profile.agent_id: profile for profile in member_profiles or []}
    semantic_scores = _semantic_score_map(semantic_result)

    history = {str(key): dict(value) for key, value in dict(route_quality_history or {}).items()}

    def _rank_key(agent_id: str) -> tuple[float, int, str]:
        profile = profiles.get(agent_id)
        score = semantic_scores.get(agent_id, 0.0)
        suitability = profile.suitability_score(semantic_score=score) if profile is not None else score
        suitability += _route_history_adjustment(history.get(agent_id))
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
    required_tools: Iterable[str] | None = None,
    required_skills: Iterable[str] | None = None,
    min_confidence_for_route: float | None = None,
    route_outcomes: Iterable[Mapping[str, Any] | RouteOutcome] | None = None,
) -> SquadDeliveryRouteDecision:
    selected_targets = _dedupe([str(target) for target in targets if str(target or "").strip()])
    profiles_by_agent = {profile.agent_id: profile for profile in member_profiles or []}
    required_tool_ids = _dedupe([str(value) for value in required_tools or [] if str(value or "").strip()])
    required_skill_ids = _dedupe([str(value) for value in required_skills or [] if str(value or "").strip()])
    selected_targets, excluded_candidates = _filter_candidates_by_requirements(
        selected_targets,
        profiles_by_agent=profiles_by_agent,
        required_tools=required_tool_ids,
        required_skills=required_skill_ids,
    )
    route_history = summarize_route_quality_history(route_outcomes or [])
    profiles_by_agent = _apply_route_quality_history(profiles_by_agent, route_history)
    ranked_targets = rank_targets_for_delivery(
        selected_targets,
        member_profiles=profiles_by_agent.values(),
        semantic_result=semantic_result,
        route_quality_history=route_history,
    )
    semantic_scores = _semantic_score_map(semantic_result)
    semantic_top_score = (
        float(getattr(semantic_result, "top_score", 0.0) or 0.0) if semantic_result is not None else 0.0
    )
    computed_status = normalize_delivery_status(
        status,
        default=delivery_status_for_source(source, has_targets=bool(ranked_targets)),
    )
    normalized_explicit_mentions = _dedupe(
        [str(value) for value in explicit_mentions or [] if str(value or "").strip()]
    )
    clarification_threshold = _optional_bounded_float(
        min_confidence_for_route,
        default=None,
        low=0.0,
        high=1.0,
    )
    low_confidence_clarification = (
        clarification_threshold is not None
        and semantic_top_score < clarification_threshold
        and str(source or "").strip().lower() in {"semantic", "fallback", "coordinator"}
        and not normalized_explicit_mentions
    )
    if low_confidence_clarification:
        computed_status = "blocked"
        ranked_targets = []
    candidate_scores = _candidate_scores(
        [*ranked_targets, *[item["agent_id"] for item in excluded_candidates]],
        profiles_by_agent=profiles_by_agent,
        semantic_scores=semantic_scores,
        route_quality_history=route_history,
    )
    quality_inputs = {
        item["agent_id"]: item["quality_inputs"] for item in candidate_scores if item.get("quality_inputs")
    }
    route_explanation = {
        "schema_version": "route_explanation.v1",
        "source": str(source or "fallback"),
        "status": computed_status,
        "confidence": round(float(semantic_top_score), 6),
        "selected_agent_ids": list(ranked_targets),
        "excluded_agent_ids": [item["agent_id"] for item in excluded_candidates],
        "required_tools": list(required_tool_ids),
        "required_skills": list(required_skill_ids),
        "clarification_required": bool(low_confidence_clarification),
        "summary": (
            "Route confidence below threshold; ask for clarification."
            if low_confidence_clarification
            else "Route selected from semantic, quality, load, cost, timeout, tool and skill signals."
        ),
        "quality_history_refs": {
            agent_id: f"route_outcome:{agent_id}:{history.get('outcome_count', 0)}"
            for agent_id, history in route_history.items()
        },
    }
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
        explicit_mentions=normalized_explicit_mentions,
        unresolved_mentions=_dedupe([str(value) for value in unresolved_mentions or [] if str(value or "").strip()]),
        ambiguous_mentions={
            str(key): [str(item) for item in value] for key, value in (ambiguous_mentions or {}).items()
        },
        semantic_available=bool(getattr(semantic_result, "available", False)) if semantic_result is not None else False,
        semantic_model=str(getattr(semantic_result, "model_name", "") or "") if semantic_result is not None else "",
        semantic_top_score=semantic_top_score,
        final_response_strategy=final_response_strategy,
        selected_profiles=[profiles_by_agent[target] for target in ranked_targets if target in profiles_by_agent],
        candidate_scores=candidate_scores,
        excluded_candidates=excluded_candidates,
        route_explanation=route_explanation,
        required_tools=required_tool_ids,
        required_skills=required_skill_ids,
        quality_inputs=quality_inputs,
    )


def build_handoff_event(
    *,
    handoff_id: str,
    thread_id: str,
    source_agent_id: str,
    destination_agent_ids: Iterable[str],
    reason: str,
    handoff_kind: str = "consult",
    context_policy: Mapping[str, Any] | None = None,
    deadline: str | None = None,
    return_criteria: Iterable[str] | None = None,
    status: str = "requested",
    run_graph_node_id: str | None = None,
    correlation_id: str | None = None,
    parent_message_id: str | None = None,
) -> HandoffEvent:
    return HandoffEvent(
        handoff_id=str(handoff_id or "").strip(),
        thread_id=str(thread_id or "").strip(),
        source_agent_id=str(source_agent_id or "").strip(),
        destination_agent_ids=_dedupe([str(value) for value in destination_agent_ids if str(value or "").strip()]),
        reason=str(reason or "").strip(),
        handoff_kind=normalize_handoff_kind(handoff_kind),
        context_policy=dict(context_policy or {}),
        deadline=str(deadline).strip() if deadline else None,
        return_criteria=_dedupe([str(value) for value in return_criteria or [] if str(value or "").strip()]),
        status=normalize_handoff_status(status),
        run_graph_node_id=str(run_graph_node_id).strip() if run_graph_node_id else None,
        correlation_id=str(correlation_id).strip() if correlation_id else None,
        parent_message_id=str(parent_message_id).strip() if parent_message_id else None,
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


def handoff_metric(*, event_type: str, status: str, handoff_kind: str) -> None:
    try:
        from koda.services.metrics import SQUAD_HANDOFF_EVENTS

        SQUAD_HANDOFF_EVENTS.labels(
            event_type=str(event_type or "unknown"),
            status=str(status or "unknown"),
            handoff_kind=str(handoff_kind or "unknown"),
        ).inc()
    except Exception:
        return


def route_quality_metric(*, source: str, status: str, confidence_band: str) -> None:
    try:
        from koda.services.metrics import SQUAD_ROUTE_QUALITY

        SQUAD_ROUTE_QUALITY.labels(
            source=str(source or "unknown"),
            status=str(status or "unknown"),
            confidence_band=str(confidence_band or "unknown"),
        ).inc()
    except Exception:
        return


def normalize_handoff_kind(value: Any) -> str:
    kind = str(value or "").strip().lower()
    return kind if kind in VALID_HANDOFF_KINDS else "consult"


def normalize_handoff_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    return status if status in VALID_HANDOFF_STATUSES else "requested"


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


def _profile_skill_ids(profile: SquadMemberProfile) -> set[str]:
    metadata = dict(profile.metadata or {})
    values: list[Any] = []
    for key in (
        "enabled_skills",
        "allowed_skill_ids",
        "skill_ids",
        "skills",
        "enabled_skill_packages",
        "skill_packages",
    ):
        raw = metadata.get(key)
        if isinstance(raw, list | tuple | set):
            values.extend(raw)
        elif raw:
            values.append(raw)
    return {str(value).strip() for value in values if str(value or "").strip()}


def _filter_candidates_by_requirements(
    targets: list[str],
    *,
    profiles_by_agent: Mapping[str, SquadMemberProfile],
    required_tools: list[str],
    required_skills: list[str],
) -> tuple[list[str], list[dict[str, Any]]]:
    if not required_tools and not required_skills:
        return targets, []
    allowed: list[str] = []
    excluded: list[dict[str, Any]] = []
    required_tool_set = set(required_tools)
    required_skill_set = set(required_skills)
    for agent_id in targets:
        profile = profiles_by_agent.get(agent_id)
        if profile is None:
            excluded.append(
                {
                    "agent_id": agent_id,
                    "reasons": ["missing_profile_for_required_capabilities"],
                    "missing_tool_ids": sorted(required_tool_set),
                    "missing_skill_ids": sorted(required_skill_set),
                }
            )
            continue
        missing_tools = sorted(required_tool_set - set(profile.allowed_tool_ids))
        missing_skills = sorted(required_skill_set - _profile_skill_ids(profile))
        reasons = []
        if missing_tools:
            reasons.append("missing_required_tools")
        if missing_skills:
            reasons.append("missing_required_skills")
        if reasons:
            excluded.append(
                {
                    "agent_id": agent_id,
                    "reasons": reasons,
                    "missing_tool_ids": missing_tools,
                    "missing_skill_ids": missing_skills,
                }
            )
            continue
        allowed.append(agent_id)
    return allowed, excluded


def _candidate_scores(
    agent_ids: Iterable[str],
    *,
    profiles_by_agent: Mapping[str, SquadMemberProfile],
    semantic_scores: Mapping[str, float],
    route_quality_history: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    history_by_agent = {str(key): dict(value) for key, value in dict(route_quality_history or {}).items()}
    for agent_id in _dedupe([str(value) for value in agent_ids if str(value or "").strip()]):
        semantic_score = float(semantic_scores.get(agent_id, 0.0) or 0.0)
        profile = profiles_by_agent.get(agent_id)
        history = history_by_agent.get(agent_id, {})
        adjustment = _route_history_adjustment(history)
        if profile is None:
            out.append(
                {
                    "agent_id": agent_id,
                    "semantic_score": round(semantic_score, 6),
                    "suitability_score": round(semantic_score + adjustment, 6),
                    "quality_history_ref": _route_history_ref(agent_id, history),
                    "quality_inputs": {},
                }
            )
            continue
        base_score = profile.suitability_score(semantic_score=semantic_score)
        out.append(
            {
                "agent_id": agent_id,
                "semantic_score": round(semantic_score, 6),
                "suitability_score": round(base_score + adjustment, 6),
                "base_suitability_score": round(base_score, 6),
                "quality_history_adjustment": round(adjustment, 6),
                "quality_history_ref": _route_history_ref(agent_id, history),
                "quality_inputs": {
                    **profile.route_quality_inputs(semantic_score=semantic_score),
                    "quality_history": _public_route_history(history),
                },
            }
        )
    return out


def _apply_route_quality_history(
    profiles_by_agent: Mapping[str, SquadMemberProfile],
    route_history: Mapping[str, Mapping[str, Any]],
) -> dict[str, SquadMemberProfile]:
    if not route_history:
        return dict(profiles_by_agent)
    out = dict(profiles_by_agent)
    for agent_id, profile in profiles_by_agent.items():
        history = dict(route_history.get(agent_id) or {})
        if not history:
            continue
        success = _optional_bounded_float(history.get("success_rate"), default=None, low=0.0, high=1.0)
        timeout = _optional_bounded_float(history.get("timeout_rate"), default=None, low=0.0, high=1.0)
        eval_score = _optional_bounded_float(history.get("avg_eval_score"), default=None, low=0.0, high=1.0)
        load = _optional_bounded_float(history.get("avg_load"), default=None, low=0.0, high=1.0)
        out[agent_id] = replace(
            profile,
            recent_success_rate=success if success is not None else profile.recent_success_rate,
            timeout_rate=timeout if timeout is not None else profile.timeout_rate,
            eval_performance_score=eval_score if eval_score is not None else profile.eval_performance_score,
            load_score=load if load is not None else profile.load_score,
            metadata={
                **dict(profile.metadata),
                "route_quality_history": _public_route_history(history),
            },
        )
    return out


def _route_history_adjustment(history: Mapping[str, Any] | None) -> float:
    if not history:
        return 0.0
    success = _optional_bounded_float(history.get("success_rate"), default=0.5, low=0.0, high=1.0) or 0.5
    timeout = _optional_bounded_float(history.get("timeout_rate"), default=0.0, low=0.0, high=1.0) or 0.0
    failure = _optional_bounded_float(history.get("failure_rate"), default=0.0, low=0.0, high=1.0) or 0.0
    handoff_return = _optional_bounded_float(history.get("handoff_return_rate"), default=0.0, low=0.0, high=1.0) or 0.0
    eval_score = _optional_bounded_float(history.get("avg_eval_score"), default=0.5, low=0.0, high=1.0) or 0.5
    latency = _optional_bounded_float(history.get("avg_latency_ms"), default=0.0, low=0.0, high=86_400_000.0) or 0.0
    cost = _optional_bounded_float(history.get("avg_cost_usd"), default=0.0, low=0.0, high=1_000_000.0) or 0.0
    positive = (success - 0.5) * 0.08 + (eval_score - 0.5) * 0.05 + handoff_return * 0.03
    penalty = timeout * 0.10 + failure * 0.08 + min(latency / 120_000.0, 1.0) * 0.03 + min(cost / 10.0, 1.0) * 0.02
    return max(-0.18, min(0.18, positive - penalty))


def _public_route_history(history: Mapping[str, Any]) -> dict[str, Any]:
    if not history:
        return {}
    return {
        "schema_version": ROUTE_OUTCOME_SCHEMA_VERSION,
        "quality_history_ref": _route_history_ref(str(history.get("agent_id") or ""), history),
        "outcome_count": int(history.get("outcome_count") or 0),
        "success_rate": history.get("success_rate"),
        "timeout_rate": history.get("timeout_rate"),
        "failure_rate": history.get("failure_rate"),
        "handoff_return_rate": history.get("handoff_return_rate"),
        "avg_cost_usd": history.get("avg_cost_usd"),
        "avg_latency_ms": history.get("avg_latency_ms"),
        "avg_eval_score": history.get("avg_eval_score"),
        "avg_load": history.get("avg_load"),
        "run_graph_node_ids": list(history.get("run_graph_node_ids") or [])[:20],
    }


def _route_history_ref(agent_id: str, history: Mapping[str, Any]) -> str:
    count = int(history.get("outcome_count") or 0) if history else 0
    return f"route_outcome:{str(agent_id or 'unknown')}:{count}"


def _normalize_route_outcome_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    if status in {"success", "timeout", "failure", "declined", "blocked"}:
        return status
    if status in {"completed", "passed", "returned"}:
        return "success"
    if status in {"failed", "error"}:
        return "failure"
    return "success"


def _mean_or_none(values: Iterable[float]) -> float | None:
    parsed = [float(value) for value in values]
    if not parsed:
        return None
    return round(sum(parsed) / len(parsed), 6)


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
