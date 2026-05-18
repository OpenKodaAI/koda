"""Tests for lightweight squad triage."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from koda.squads.capabilities import CapabilitySummary
from koda.squads.semantic_router import SemanticAgentScore, SemanticRoutingResult
from koda.squads.triage import SquadTriageService


def _participant(agent_id: str, *, active: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        agent_id=agent_id,
        left_at=None if active else datetime.now(UTC),
    )


def _semantic_result(*agent_ids: str) -> SemanticRoutingResult:
    return SemanticRoutingResult(
        available=True,
        model_name="test-model",
        scores=[
            SemanticAgentScore(
                agent_id=agent_id,
                score=0.9 - (idx * 0.05),
                positive_score=0.9 - (idx * 0.05),
                negative_score=0.0,
                summary_text=f"{agent_id} semantic summary",
                is_coordinator=agent_id == "PM",
            )
            for idx, agent_id in enumerate(agent_ids)
        ],
        min_score=0.2,
    )


def _summary(agent_id: str, *, role: str = "", delegate_when: str = "") -> CapabilitySummary:
    return CapabilitySummary(
        agent_id=agent_id,
        display_name=agent_id.title(),
        role=role,
        delegate_when=delegate_when,
        is_coordinator=agent_id == "PM",
    )


@pytest.mark.asyncio
async def test_triage_records_awareness_for_all_active_participants() -> None:
    store = AsyncMock()
    store.post_thread_message = AsyncMock(return_value=10)
    thread = SimpleNamespace(id="thread-1")

    result = await SquadTriageService().triage_user_input(
        thread_store=store,
        thread=thread,
        participants=[_participant("PM"), _participant("FE"), _participant("OLD", active=False)],
        text="build a page",
        user_input_message_id="msg-1",
        channel="telegram",
        capability_summaries=[_summary("PM"), _summary("FE", role="Frontend")],
        semantic_result=_semantic_result("FE", "PM"),
    )

    assert result.awareness_agent_ids == ["PM", "FE"]
    assert result.excluded_agent_ids == {"OLD": "left_thread"}
    first_payload = store.post_thread_message.await_args_list[0].kwargs["metadata"]["payload"]
    assert first_payload["event_type"] == "squad_awareness_fanout"
    assert first_payload["delivery_intent"] == "awareness"
    assert first_payload["awareness_agent_ids"] == ["PM", "FE"]


@pytest.mark.asyncio
async def test_triage_builds_proposals_from_top_semantic_specialists() -> None:
    store = AsyncMock()
    store.post_thread_message = AsyncMock(side_effect=[10, 11])
    thread = SimpleNamespace(id="thread-1")

    result = await SquadTriageService().triage_user_input(
        thread_store=store,
        thread=thread,
        participants=[_participant("PM"), _participant("COPY"), _participant("FE")],
        text="build a landing page",
        user_input_message_id="msg-1",
        channel="web",
        capability_summaries=[
            _summary("PM", role="Coordinator"),
            _summary("COPY", role="Copy", delegate_when="positioning and hero copy"),
            _summary("FE", role="Frontend", delegate_when="interface implementation"),
        ],
        semantic_result=_semantic_result("PM", "COPY", "FE"),
    )

    assert [item.agent_id for item in result.proposal_candidates] == ["COPY", "FE"]
    proposal_payload = store.post_thread_message.await_args_list[1].kwargs["metadata"]["payload"]
    assert proposal_payload["event_type"] == "contribution_proposal"
    assert proposal_payload["delivery_intent"] == "proposal"
    assert [item["agent_id"] for item in proposal_payload["proposals"]] == ["COPY", "FE"]


@pytest.mark.asyncio
async def test_triage_mentions_create_awareness_but_not_proposals() -> None:
    store = AsyncMock()
    store.post_thread_message = AsyncMock(return_value=10)
    thread = SimpleNamespace(id="thread-1")

    result = await SquadTriageService().triage_user_input(
        thread_store=store,
        thread=thread,
        participants=[_participant("PM"), _participant("FE")],
        text="@fe build a page",
        user_input_message_id="msg-1",
        channel="telegram",
        capability_summaries=[_summary("PM"), _summary("FE")],
        semantic_result=_semantic_result("FE"),
        execution_targets=["FE"],
        allow_proposals=False,
    )

    assert result.execution_targets == ["FE"]
    assert result.proposal_candidates == []
    assert store.post_thread_message.await_count == 1
