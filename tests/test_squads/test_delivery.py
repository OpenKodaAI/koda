"""Tests for the squad_delivery.v1 contract."""

from __future__ import annotations

from koda.squads.capabilities import CapabilitySummary
from koda.squads.delivery import (
    SQUAD_DELIVERY_SCHEMA_VERSION,
    SquadDeliveryEvent,
    SquadDeliveryState,
    build_member_profiles,
    build_route_decision,
    delivery_status_for_source,
    rank_targets_for_delivery,
)
from koda.squads.semantic_router import SemanticAgentScore, SemanticRoutingResult


def _semantic_result(*agent_ids: str) -> SemanticRoutingResult:
    return SemanticRoutingResult(
        available=True,
        model_name="test-model",
        scores=[
            SemanticAgentScore(
                agent_id=agent_id,
                score=0.8,
                positive_score=0.8,
                negative_score=0.0,
                summary_text=f"{agent_id} summary",
            )
            for agent_id in agent_ids
        ],
        min_score=0.2,
    )


def test_delivery_route_decision_serializes_contract() -> None:
    profiles = build_member_profiles(
        [
            CapabilitySummary(
                agent_id="FE",
                display_name="Frontend",
                role="Frontend Engineer",
                allowed_tool_ids=["file_read", "browser_navigate"],
                preferred_provider="codex",
                preferred_model="gpt-5.4-mini",
            )
        ]
    )
    decision = build_route_decision(
        source="semantic",
        targets=["FE"],
        reason="best capability match",
        semantic_result=_semantic_result("FE"),
        member_profiles=profiles,
        final_response_strategy="coordinator_synthesis_after_all_task_results",
    )

    payload = decision.to_dict()

    assert payload["schema_version"] == SQUAD_DELIVERY_SCHEMA_VERSION
    assert payload["status"] == "routed"
    assert payload["targets"] == ["FE"]
    assert payload["selected_profiles"][0]["preferred_model"] == "gpt-5.4-mini"
    assert payload["final_response_strategy"] == "coordinator_synthesis_after_all_task_results"


def test_member_profile_ranking_uses_load_quality_and_cost_as_tiebreakers() -> None:
    profiles = build_member_profiles(
        [
            CapabilitySummary(agent_id="FAST", display_name="Fast", role="FE", quality_score=0.9, cost_weight=0.5),
            CapabilitySummary(agent_id="BUSY", display_name="Busy", role="FE", quality_score=0.9, load_score=0.95),
        ]
    )

    ranked = rank_targets_for_delivery(
        ["BUSY", "FAST"],
        member_profiles=profiles,
        semantic_result=_semantic_result("BUSY", "FAST"),
    )

    assert ranked == ["FAST", "BUSY"]


def test_delivery_state_captures_tasks_replies_child_runs_and_events() -> None:
    event = SquadDeliveryEvent(
        event_type="coordination_dispatched",
        status="delegated",
        source="coordinator_engine",
        targets=["COPY", "FE"],
        thread_id="thread-1",
        squad_id="build",
    )
    state = SquadDeliveryState(
        delivery_id="delivery-1",
        thread_id="thread-1",
        squad_id="build",
        status="waiting_for_replies",
        task_ids=["task-1", "task-2"],
        reply_obligation_ids=["reply-1"],
        child_run_ids=["child-1"],
        events=[event],
    )

    payload = state.to_dict()

    assert payload["schema_version"] == SQUAD_DELIVERY_SCHEMA_VERSION
    assert payload["status"] == "waiting_for_replies"
    assert payload["task_ids"] == ["task-1", "task-2"]
    assert payload["events"][0]["event_type"] == "coordination_dispatched"


def test_source_defaults_block_empty_or_unresolved_routes() -> None:
    assert delivery_status_for_source("telegram_mention", has_targets=True) == "routed"
    assert delivery_status_for_source("mention_unresolved", has_targets=True) == "blocked"
    assert delivery_status_for_source("semantic", has_targets=False) == "blocked"
