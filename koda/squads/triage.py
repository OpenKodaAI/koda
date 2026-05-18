"""Lightweight squad triage for collective awareness and controlled proactivity."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from koda.config import SQUAD_SEMANTIC_TOP_K
from koda.logging_config import get_logger
from koda.squads.capabilities import CapabilitySummary
from koda.squads.semantic_router import SemanticAgentScore, SemanticRoutingResult

log = get_logger(__name__)


@dataclass(frozen=True)
class ContributionProposal:
    agent_id: str
    score: float
    display_name: str
    role: str
    suggested_contribution: str
    delivery_intent: str = "proposal"

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "score": round(float(self.score), 6),
            "display_name": self.display_name,
            "role": self.role,
            "suggested_contribution": self.suggested_contribution,
            "delivery_intent": self.delivery_intent,
        }


@dataclass(frozen=True)
class SquadTriageResult:
    awareness_agent_ids: list[str] = field(default_factory=list)
    excluded_agent_ids: dict[str, str] = field(default_factory=dict)
    proposal_candidates: list[ContributionProposal] = field(default_factory=list)
    execution_targets: list[str] = field(default_factory=list)
    routing_source: str = "triage"
    event_ids: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "awareness_agent_ids": list(self.awareness_agent_ids),
            "excluded_agent_ids": dict(self.excluded_agent_ids),
            "proposal_candidates": [item.to_dict() for item in self.proposal_candidates],
            "execution_targets": list(self.execution_targets),
            "routing_source": self.routing_source,
            "event_ids": list(self.event_ids),
        }


class SquadTriageService:
    """Persist collective awareness and lightweight contribution proposals.

    Triage is intentionally not execution. It records which active participants
    received visibility into a user turn and which specialists looked relevant
    enough for the coordinator/arbitrator to consider.
    """

    async def triage_user_input(
        self,
        *,
        thread_store: Any,
        thread: Any,
        participants: list[Any],
        text: str,
        user_input_message_id: str | int | None,
        channel: str,
        channel_context: dict[str, Any] | None = None,
        capability_summaries: list[CapabilitySummary] | None = None,
        semantic_result: SemanticRoutingResult | None = None,
        execution_targets: list[str] | None = None,
        routing_source: str = "triage",
        allow_proposals: bool = True,
    ) -> SquadTriageResult:
        active_ids: list[str] = []
        excluded: dict[str, str] = {}
        for participant in participants:
            agent_id = str(getattr(participant, "agent_id", "") or "").strip()
            if not agent_id:
                continue
            if getattr(participant, "left_at", None) is None:
                active_ids.append(agent_id)
            else:
                excluded[agent_id] = "left_thread"
        active_ids = _dedupe(active_ids)
        execution = [agent_id for agent_id in _dedupe(execution_targets or []) if agent_id in set(active_ids)]
        summaries = {summary.agent_id: summary for summary in capability_summaries or []}
        proposals: list[ContributionProposal] = []
        if allow_proposals and semantic_result is not None and semantic_result.available:
            proposals = _build_proposals(
                semantic_result=semantic_result,
                active_agent_ids=active_ids,
                summaries=summaries,
                execution_targets=execution,
            )
        event_ids: list[int] = []
        awareness_id = await _post_awareness_event(
            thread_store=thread_store,
            thread_id=str(getattr(thread, "id", "") or ""),
            active_ids=active_ids,
            excluded=excluded,
            user_input_message_id=user_input_message_id,
            channel=channel,
            channel_context=channel_context or {},
            execution_targets=execution,
            proposal_agent_ids=[item.agent_id for item in proposals],
        )
        if awareness_id is not None:
            event_ids.append(awareness_id)
        if proposals and semantic_result is not None:
            proposal_id = await _post_proposal_event(
                thread_store=thread_store,
                thread_id=str(getattr(thread, "id", "") or ""),
                user_input_message_id=user_input_message_id,
                channel=channel,
                proposals=proposals,
                semantic_result=semantic_result,
            )
            if proposal_id is not None:
                event_ids.append(proposal_id)
        return SquadTriageResult(
            awareness_agent_ids=active_ids,
            excluded_agent_ids=excluded,
            proposal_candidates=proposals,
            execution_targets=execution,
            routing_source=routing_source,
            event_ids=event_ids,
        )


def _build_proposals(
    *,
    semantic_result: SemanticRoutingResult,
    active_agent_ids: list[str],
    summaries: dict[str, CapabilitySummary],
    execution_targets: list[str],
) -> list[ContributionProposal]:
    active = set(active_agent_ids)
    already_executing = set(execution_targets)
    proposals: list[ContributionProposal] = []
    for score in semantic_result.scores:
        if score.agent_id not in active or score.agent_id in already_executing:
            continue
        if score.is_coordinator or score.score < semantic_result.min_score:
            continue
        summary = summaries.get(score.agent_id)
        proposals.append(_proposal_from_score(score=score, summary=summary))
        if len(proposals) >= max(1, int(semantic_result.top_k or SQUAD_SEMANTIC_TOP_K)):
            break
    return proposals


def _proposal_from_score(
    *,
    score: SemanticAgentScore,
    summary: CapabilitySummary | None,
) -> ContributionProposal:
    display_name = summary.display_name if summary is not None else score.agent_id
    role = summary.role if summary is not None else ""
    contribution_parts = []
    if summary is not None:
        contribution_parts.extend(summary.primary_outcomes[:2])
        if summary.delegate_when:
            contribution_parts.append(summary.delegate_when)
        if not contribution_parts:
            contribution_parts.extend(summary.domains[:2])
    if not contribution_parts:
        contribution_parts.append(score.summary_text)
    contribution = " ".join(part.strip() for part in contribution_parts if part and part.strip())
    return ContributionProposal(
        agent_id=score.agent_id,
        score=score.score,
        display_name=display_name,
        role=role,
        suggested_contribution=contribution[:500],
    )


async def _post_awareness_event(
    *,
    thread_store: Any,
    thread_id: str,
    active_ids: list[str],
    excluded: dict[str, str],
    user_input_message_id: str | int | None,
    channel: str,
    channel_context: dict[str, Any],
    execution_targets: list[str],
    proposal_agent_ids: list[str],
) -> int | None:
    payload = {
        "event_type": "squad_awareness_fanout",
        "delivery_intent": "awareness",
        "user_input_message_id": str(user_input_message_id) if user_input_message_id is not None else None,
        "channel": channel,
        "awareness_agent_ids": list(active_ids),
        "excluded_agent_ids": dict(excluded),
        "execution_targets": list(execution_targets),
        "proposal_agent_ids": list(proposal_agent_ids),
        "channel_context": _safe_channel_context(channel_context),
    }
    try:
        return int(
            await thread_store.post_thread_message(
                thread_id=thread_id,
                from_agent="squad_triage",
                content=f"[squad_awareness_fanout] {len(active_ids)} participant(s) considered",
                message_type="system_event",
                metadata={
                    "event_type": "squad_awareness_fanout",
                    "parent_message_id": str(user_input_message_id) if user_input_message_id is not None else None,
                    "delivery_intent": "awareness",
                    "payload": payload,
                },
            )
        )
    except Exception:
        log.exception("squad_awareness_fanout_persist_failed", thread_id=thread_id)
        return None


async def _post_proposal_event(
    *,
    thread_store: Any,
    thread_id: str,
    user_input_message_id: str | int | None,
    channel: str,
    proposals: list[ContributionProposal],
    semantic_result: SemanticRoutingResult,
) -> int | None:
    payload = {
        "event_type": "contribution_proposal",
        "delivery_intent": "proposal",
        "user_input_message_id": str(user_input_message_id) if user_input_message_id is not None else None,
        "channel": channel,
        "proposals": [item.to_dict() for item in proposals],
        "semantic_model": semantic_result.model_name,
        "semantic_available": semantic_result.available,
    }
    try:
        return int(
            await thread_store.post_thread_message(
                thread_id=thread_id,
                from_agent="squad_triage",
                content=f"[contribution_proposal] {', '.join(item.agent_id for item in proposals)}",
                message_type="system_event",
                metadata={
                    "event_type": "contribution_proposal",
                    "parent_message_id": str(user_input_message_id) if user_input_message_id is not None else None,
                    "delivery_intent": "proposal",
                    "payload": payload,
                },
            )
        )
    except Exception:
        log.exception("squad_contribution_proposal_persist_failed", thread_id=thread_id)
        return None


def _safe_channel_context(channel_context: dict[str, Any]) -> dict[str, Any]:
    chat = channel_context.get("chat")
    message = channel_context.get("message")
    return {
        "chat_id": _safe_scalar(getattr(chat, "id", None)),
        "chat_type": _safe_scalar(getattr(chat, "type", None)),
        "message_id": _safe_scalar(getattr(message, "message_id", None)),
        "message_thread_id": _safe_scalar(getattr(message, "message_thread_id", None)),
    }


def _safe_scalar(value: Any) -> str | int | None:
    if value is None or isinstance(value, (str, int)):
        return value
    return str(value)


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


_default_triage_service: SquadTriageService | None = None


def get_squad_triage_service() -> SquadTriageService:
    global _default_triage_service  # noqa: PLW0603
    if _default_triage_service is None:
        _default_triage_service = SquadTriageService()
    return _default_triage_service
