"""Tests for squad routing decisions."""

from __future__ import annotations

from koda.squads.routing import extract_mentions, select_targets


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


def test_select_targets_falls_back_to_coordinator() -> None:
    targets = select_targets(
        "any update on the work?",
        participant_agent_ids=["FE", "PM"],
        coordinator_agent_id="PM",
    )
    assert targets == ["PM"]


def test_select_targets_empty_when_no_mention_and_no_coordinator() -> None:
    targets = select_targets(
        "any update on the work?",
        participant_agent_ids=["FE", "BE"],
        coordinator_agent_id=None,
    )
    assert targets == []


def test_select_targets_skips_coordinator_not_in_participants() -> None:
    # Coordinator was elected but isn't a participant of THIS thread (e.g.,
    # already left). Don't notify them; fall through to no-target.
    targets = select_targets(
        "anyone home?",
        participant_agent_ids=["FE", "BE"],
        coordinator_agent_id="PM",
    )
    assert targets == []


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
