"""Tests for the squad_delivery.v1 contract."""

from __future__ import annotations

from koda.squads.capabilities import CapabilitySummary
from koda.squads.delivery import (
    HANDOFF_EVENT_SCHEMA_VERSION,
    ROUTE_OUTCOME_SCHEMA_VERSION,
    SQUAD_DELIVERY_SCHEMA_VERSION,
    SquadDeliveryEvent,
    SquadDeliveryState,
    build_handoff_event,
    build_member_profiles,
    build_route_decision,
    build_route_outcome,
    delivery_status_for_source,
    rank_targets_for_delivery,
    summarize_route_quality_history,
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
    assert payload["route_explanation"]["schema_version"] == "route_explanation.v1"
    assert payload["candidate_scores"][0]["agent_id"] == "FE"


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


def test_route_outcomes_adjust_ranking_bounded_and_emit_history_refs() -> None:
    from koda.services.metrics import ROUTE_OUTCOME_EVENTS

    child = ROUTE_OUTCOME_EVENTS.labels(
        agent_id="FAST",
        route_source="semantic",
        status="success",
        timeout="false",
    )
    before = float(child._value.get()) if hasattr(child, "_value") else 0.0
    profiles = build_member_profiles(
        [
            CapabilitySummary(agent_id="FAST", display_name="Fast", role="FE", quality_score=0.8),
            CapabilitySummary(agent_id="TIMEOUT", display_name="Timeout", role="FE", quality_score=0.8),
        ]
    )
    outcomes = [
        build_route_outcome(
            outcome_id="route-outcome-1",
            agent_id="FAST",
            route_source="semantic",
            status="success",
            eval_score=0.92,
            latency_ms=800,
            run_graph_node_id="agent_request:1",
        ).to_dict(),
        build_route_outcome(
            outcome_id="route-outcome-2",
            agent_id="TIMEOUT",
            route_source="semantic",
            status="timeout",
            timeout=True,
            latency_ms=120_000,
            run_graph_node_id="dependency_call:timeout",
        ).to_dict(),
    ]

    decision = build_route_decision(
        source="semantic",
        targets=["TIMEOUT", "FAST"],
        member_profiles=profiles,
        semantic_result=_semantic_result("TIMEOUT", "FAST"),
        route_outcomes=outcomes,
    )
    payload = decision.to_dict()

    assert payload["targets"] == ["FAST", "TIMEOUT"]
    assert payload["route_explanation"]["quality_history_refs"]["FAST"] == "route_outcome:FAST:1"
    fast_score = next(item for item in payload["candidate_scores"] if item["agent_id"] == "FAST")
    timeout_score = next(item for item in payload["candidate_scores"] if item["agent_id"] == "TIMEOUT")
    assert fast_score["quality_history_adjustment"] > timeout_score["quality_history_adjustment"]
    assert fast_score["quality_inputs"]["quality_history"]["schema_version"] == ROUTE_OUTCOME_SCHEMA_VERSION
    after = float(child._value.get()) if hasattr(child, "_value") else 0.0
    if after > before:
        assert after == before + 1


def test_route_quality_history_summarizes_success_timeout_cost_latency_and_graph_refs() -> None:
    history = summarize_route_quality_history(
        [
            {
                "schema_version": "route_outcome.v1",
                "agent_id": "OPS",
                "status": "success",
                "handoff_returned": True,
                "cost_usd": 0.2,
                "latency_ms": 1000,
                "eval_score": 0.8,
                "run_graph_node_id": "agent_request:ops",
            },
            {
                "schema_version": "route_outcome.v1",
                "agent_id": "OPS",
                "status": "timeout",
                "timeout": True,
                "cost_usd": 0.4,
                "latency_ms": 3000,
                "eval_score": 0.4,
                "run_graph_node_id": "dependency_call:ops",
            },
        ]
    )

    assert history["OPS"]["schema_version"] == ROUTE_OUTCOME_SCHEMA_VERSION
    assert history["OPS"]["success_rate"] == 0.5
    assert history["OPS"]["timeout_rate"] == 0.5
    assert history["OPS"]["avg_cost_usd"] == 0.3
    assert history["OPS"]["avg_latency_ms"] == 2000.0
    assert history["OPS"]["run_graph_node_ids"] == ["agent_request:ops", "dependency_call:ops"]


def test_route_decision_excludes_agents_without_required_tool_or_skill() -> None:
    profiles = build_member_profiles(
        [
            CapabilitySummary(
                agent_id="FE",
                display_name="Frontend",
                role="Frontend",
                allowed_tool_ids=["read_file"],
                metadata={"enabled_skills": ["react-build"]},
            ),
            CapabilitySummary(
                agent_id="COPY",
                display_name="Copy",
                role="Content",
                allowed_tool_ids=[],
                metadata={"enabled_skills": []},
            ),
        ]
    )

    decision = build_route_decision(
        source="semantic",
        targets=["COPY", "FE"],
        member_profiles=profiles,
        semantic_result=_semantic_result("COPY", "FE"),
        required_tools=["read_file"],
        required_skills=["react-build"],
    )
    payload = decision.to_dict()

    assert payload["targets"] == ["FE"]
    assert payload["excluded_candidates"][0]["agent_id"] == "COPY"
    assert set(payload["excluded_candidates"][0]["reasons"]) == {"missing_required_tools", "missing_required_skills"}


def test_route_decision_low_confidence_requires_clarification() -> None:
    decision = build_route_decision(
        source="semantic",
        targets=["FE"],
        semantic_result=SemanticRoutingResult(
            available=True,
            model_name="test-model",
            scores=[
                SemanticAgentScore(
                    agent_id="FE",
                    score=0.2,
                    positive_score=0.2,
                    negative_score=0.0,
                    summary_text="weak match",
                )
            ],
            min_score=0.1,
        ),
        min_confidence_for_route=0.6,
    )
    payload = decision.to_dict()

    assert payload["status"] == "blocked"
    assert payload["targets"] == []
    assert payload["route_explanation"]["clarification_required"] is True


def test_handoff_event_serializes_contract() -> None:
    event = build_handoff_event(
        handoff_id="handoff-1",
        thread_id="thread-1",
        source_agent_id="PM",
        destination_agent_ids=["FE", "QA", "FE"],
        reason="Need implementation and verification.",
        handoff_kind="parallel_consult",
        context_policy={"visibility": "thread", "context_refs": ["msg-1"]},
        deadline="2026-05-19T20:00:00+00:00",
        return_criteria=["reply with task_result"],
        parent_message_id="msg-1",
    )

    payload = event.to_dict()

    assert payload["schema_version"] == HANDOFF_EVENT_SCHEMA_VERSION
    assert payload["destination_agent_ids"] == ["FE", "QA"]
    assert payload["handoff_kind"] == "parallel_consult"
    assert payload["status"] == "requested"


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
