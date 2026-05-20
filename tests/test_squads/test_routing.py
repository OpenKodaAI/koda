"""Tests for squad routing decisions."""

from __future__ import annotations

from koda.squads.capabilities import CapabilitySummary
from koda.squads.delivery import build_member_profiles
from koda.squads.routing import extract_mentions, select_targets
from koda.squads.semantic_router import SemanticAgentScore, SemanticRoutingResult


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
            )
            for idx, agent_id in enumerate(agent_ids)
        ],
    )


def test_extract_mentions_empty_text() -> None:
    assert extract_mentions("", ["FE", "BE"]) == []


def test_extract_mentions_no_match() -> None:
    assert extract_mentions("Hi team, please review", ["FE", "BE"]) == []


def test_extract_mentions_single_match() -> None:
    assert extract_mentions("hey @frontend please look", ["FRONTEND", "BACKEND"]) == ["FRONTEND"]


def test_extract_mentions_case_insensitive() -> None:
    assert extract_mentions("@Backend pls deploy", ["BACKEND"]) == ["BACKEND"]


def test_extract_mentions_preserves_first_appearance_order() -> None:
    result = extract_mentions("@be will fix; @fe please style", ["FE", "BE"])
    assert result == ["BE", "FE"]


def test_extract_mentions_dedupes() -> None:
    result = extract_mentions("@FE @fe @FE @bE", ["FE", "BE"])
    assert result == ["FE", "BE"]


def test_extract_mentions_skips_unknown_agents() -> None:
    result = extract_mentions("@ghost @fe", ["FE"])
    assert result == ["FE"]


def test_extract_mentions_does_not_match_email_like() -> None:
    # An @ embedded in word-character context (e.g., email) is not a mention.
    assert extract_mentions("send to alice@frontend.com", ["FRONTEND"]) == []


def test_extract_mentions_with_hyphen() -> None:
    assert extract_mentions("@build-pm please triage", ["BUILD-PM"]) == ["BUILD-PM"]


def test_select_targets_returns_empty_with_no_participants() -> None:
    assert select_targets("hi @fe", participant_agent_ids=[]) == []


def test_select_targets_mention_takes_priority_over_coordinator() -> None:
    targets = select_targets(
        "hey @fe please look",
        participant_agent_ids=["FE", "PM"],
        coordinator_agent_id="PM",
    )
    assert targets == ["FE"]


def test_select_targets_resolved_channel_mention_takes_priority() -> None:
    targets = select_targets(
        "@frontend_bot please look",
        participant_agent_ids=["FE", "PM"],
        coordinator_agent_id="PM",
        semantic_result=_semantic_result("PM"),
        explicit_mention_agent_ids=["FE"],
    )
    assert targets == ["FE"]


def test_select_targets_falls_back_to_coordinator() -> None:
    targets = select_targets(
        "any update on the work?",
        participant_agent_ids=["FE", "PM"],
        coordinator_agent_id="PM",
    )
    assert targets == ["PM"]


def test_select_targets_routes_capability_match_before_coordinator() -> None:
    targets = select_targets(
        "preciso de uma UI frontend polida",
        participant_agent_ids=["FE", "PM"],
        coordinator_agent_id="PM",
        semantic_result=_semantic_result("FE"),
    )
    assert targets == ["FE"]


def test_select_targets_routes_multiple_capability_matches() -> None:
    targets = select_targets(
        "build frontend React and backend API",
        participant_agent_ids=["FE", "BE", "PM"],
        coordinator_agent_id="PM",
        semantic_result=_semantic_result("FE", "BE"),
    )
    assert targets == ["FE", "BE"]


def test_select_targets_reply_continuation_before_coordinator() -> None:
    targets = select_targets(
        "can you clarify?",
        participant_agent_ids=["FE", "PM"],
        coordinator_agent_id="PM",
        reply_to_agent_id="FE",
    )
    assert targets == ["FE"]


def test_select_targets_reply_continuation_beats_semantic_ranking() -> None:
    targets = select_targets(
        "chame os agentes especializados para planejamento e frontend landing page",
        participant_agent_ids=["PM", "PLANNER", "FE"],
        coordinator_agent_id="PM",
        reply_to_agent_id="PM",
        semantic_result=_semantic_result("FE", "PLANNER"),
    )
    assert targets == ["PM"]


def test_select_targets_falls_back_to_reply_without_semantic_result() -> None:
    targets = select_targets(
        "chame eles e trabalhem em conjunto",
        participant_agent_ids=["PM", "PLANNER", "FE", "BE"],
        coordinator_agent_id="PM",
        reply_to_agent_id="PM",
    )
    assert targets == ["PM"]


def test_select_targets_semantic_does_not_include_coordinator_by_default() -> None:
    targets = select_targets(
        "chame os agentes especializados e trabalhem em conjunto",
        participant_agent_ids=["PM", "PLANNER", "FE"],
        coordinator_agent_id="PM",
        semantic_result=SemanticRoutingResult(
            available=True,
            model_name="test-model",
            scores=[
                SemanticAgentScore(
                    agent_id="PM",
                    score=0.95,
                    positive_score=0.95,
                    negative_score=0.0,
                    summary_text="pm",
                    is_coordinator=True,
                ),
                SemanticAgentScore(
                    agent_id="FE",
                    score=0.9,
                    positive_score=0.9,
                    negative_score=0.0,
                    summary_text="fe",
                ),
            ],
        ),
    )
    assert targets == ["FE"]


def test_select_targets_semantic_single_specialist_match() -> None:
    targets = select_targets(
        "chame o frontend e trabalhem em conjunto",
        participant_agent_ids=["PM", "PLANNER", "FE"],
        coordinator_agent_id="PM",
        semantic_result=_semantic_result("FE"),
    )
    assert targets == ["FE"]


def test_select_targets_capability_fallback_when_no_coordinator() -> None:
    targets = select_targets(
        "please build the API",
        participant_agent_ids=["FE", "BE"],
        coordinator_agent_id=None,
        semantic_result=_semantic_result("BE"),
    )
    assert targets == ["BE"]


def test_select_targets_uses_member_profiles_to_break_semantic_ties() -> None:
    profiles = build_member_profiles(
        [
            CapabilitySummary(agent_id="FE_SLOW", display_name="Slow", role="Frontend", load_score=0.95),
            CapabilitySummary(agent_id="FE_FAST", display_name="Fast", role="Frontend", quality_score=0.9),
        ]
    )
    targets = select_targets(
        "please implement the frontend",
        participant_agent_ids=["FE_SLOW", "FE_FAST"],
        semantic_result=_semantic_result("FE_SLOW", "FE_FAST"),
        member_profiles=profiles,
    )

    assert targets == ["FE_FAST", "FE_SLOW"]


def test_select_targets_skips_coordinator_not_in_participants() -> None:
    # Coordinator was elected but isn't a participant of THIS thread (e.g.,
    # already left). Don't notify them; fall through to deterministic fallback.
    targets = select_targets(
        "anyone home?",
        participant_agent_ids=["FE", "BE"],
        coordinator_agent_id="PM",
    )
    assert targets == ["FE"]


def test_select_targets_multiple_mentions() -> None:
    targets = select_targets(
        "@fe and @be sync up please",
        participant_agent_ids=["FE", "BE", "PM"],
        coordinator_agent_id="PM",
    )
    assert targets == ["FE", "BE"]


def test_select_targets_skips_unknown_mentions_and_falls_back() -> None:
    # @ghost isn't a participant; with no other valid mentions and a
    # coordinator, the coordinator gets notified.
    targets = select_targets(
        "@ghost where are you?",
        participant_agent_ids=["FE", "PM"],
        coordinator_agent_id="PM",
    )
    assert targets == ["PM"]
