"""Pure-logic tests for koda.services.runtime.classifier and constants.

classifier.classify_task is the gate that decides which sandbox shape (light /
standard / heavy) the runtime allocates. constants.py is the contract surface
for phases, event types, and isolation kinds — drift here breaks the state
machine silently.
"""

from __future__ import annotations

import pytest

from koda.services.runtime.classifier import RuntimeClassification, classify_task
from koda.services.runtime.constants import (
    ATTACH_KINDS,
    FINAL_PHASES,
    GUARDRAIL_TYPES,
    MUTATION_BLOCKED_PHASES,
    PAUSE_STATES,
    RECOVERABLE_PHASES,
    RUNTIME_CLASSIFICATIONS,
    RUNTIME_ENVIRONMENT_KINDS,
    RUNTIME_EVENT_TYPES,
    RUNTIME_PHASES,
)

# ---------------------------------------------------------------------------
# classifier.classify_task — heavy keywords
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query,why",
    [
        ("Run playwright tests", "playwright"),
        ("Open the browser to scrape", "browser"),
        ("Take a screenshot of the dashboard", "screenshot"),
        ("Capture a video and trace", "video"),
        ("Spin up a chromium instance", "chromium"),
        ("Use selenium to log in", "selenium"),
        ("Run the full e2e suite", "e2e"),
        ("Validate the deployment with integration test", "integration test"),
        ("npm install all the deps", "npm install"),
        ("pnpm install fresh", "pnpm install"),
        ("uv sync the environment", "uv sync"),
        ("docker compose up the stack", "docker"),
        ("Start the dev server", "dev server"),
        ("Open port 3000 to listen", "open port"),
        ("Run pytest -v", "pytest"),
    ],
)
def test_classify_heavy_keywords(query: str, why: str) -> None:
    out = classify_task(query)
    assert out.classification == "heavy", f"{query!r} ({why}) should be heavy"
    assert out.isolation == "worktree"
    assert out.duration == "long"
    assert out.environment_kind == "dev_worktree_browser"
    assert out.reasons == ["matched_heavy_keywords"]


# ---------------------------------------------------------------------------
# classifier.classify_task — standard keywords
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query,why",
    [
        ("Edit the file to add a comment", "edit"),
        ("Write a small helper", "write"),
        ("Refactor this function", "refactor"),
        ("Patch the module", "patch"),
        ("Fix the bug in the parser", "fix"),
        ("Implement the new endpoint", "implement"),
        ("Build the project locally", "build"),
        ("Compile the protos", "compile"),
        ("Run lint on the repo", "lint"),
        ("Do a typecheck pass", "typecheck"),
        ("Run a unit test", "unit test"),
        ("Check git status", "git"),
        ("Create a new worktree", "worktree"),
        ("Switch the branch", "branch"),
        ("Show the commit log", "commit"),
        ("Inspect the diff", "diff"),
    ],
)
def test_classify_standard_keywords(query: str, why: str) -> None:
    out = classify_task(query)
    assert out.classification == "standard", f"{query!r} ({why}) should be standard"
    assert out.isolation == "worktree"
    assert out.duration == "medium"
    assert out.environment_kind == "dev_worktree"


# ---------------------------------------------------------------------------
# classifier.classify_task — default to light
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "What time is it",
        "Explain decorators in Python",
        "Translate this text to PT-BR",
        "Summarize the document",
        "Tell me a joke",
        "",
        "   ",
    ],
)
def test_classify_default_light(query: str) -> None:
    out = classify_task(query)
    assert out.classification == "light"
    assert out.isolation == "shared"
    assert out.duration == "short"
    assert out.environment_kind == "dev_worktree"
    assert out.reasons == ["default_light"]


# ---------------------------------------------------------------------------
# classifier.classify_task — heavy beats standard when both match
# ---------------------------------------------------------------------------


def test_classify_heavy_wins_over_standard() -> None:
    """A query that matches both heavy and standard keywords resolves to heavy."""
    out = classify_task("Edit the file then run playwright tests")
    assert out.classification == "heavy"


# ---------------------------------------------------------------------------
# classifier.classify_task — explicit override
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("override", ["light", "standard", "heavy"])
def test_classify_override(override: str) -> None:
    out = classify_task("Tell me a joke", override=override)
    assert out.classification == override
    assert out.reasons == [f"user_override:{override}"]


@pytest.mark.parametrize("override", ["", "  ", "ridiculous", "extreme", "huge"])
def test_classify_override_invalid_falls_through(override: str) -> None:
    """Invalid override falls back to keyword-based classification."""
    out = classify_task("Run playwright tests", override=override)
    assert out.classification == "heavy"
    # Reason should NOT be a user_override.
    assert all("user_override" not in r for r in out.reasons)


def test_classify_override_normalizes_case_and_whitespace() -> None:
    out = classify_task("Tell me a joke", override="  HEAVY  ")
    assert out.classification == "heavy"


# ---------------------------------------------------------------------------
# classifier.classify_task — case insensitivity in patterns
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "PLAYWRIGHT",
        "Playwright",
        "pLaYwRiGhT",
        "Open BROWSER",
        "Run PYTEST",
    ],
)
def test_classify_heavy_case_insensitive(query: str) -> None:
    assert classify_task(query).classification == "heavy"


# ---------------------------------------------------------------------------
# classifier.classify_task — return shape
# ---------------------------------------------------------------------------


def test_classify_returns_dataclass() -> None:
    out = classify_task("anything")
    assert isinstance(out, RuntimeClassification)
    d = out.to_dict()
    assert set(d.keys()) == {"classification", "isolation", "duration", "environment_kind", "reasons"}


# ---------------------------------------------------------------------------
# constants — phase enum, mutation-blocked, recoverable, final
# ---------------------------------------------------------------------------


def test_classifications_are_canonical() -> None:
    assert RUNTIME_CLASSIFICATIONS == ("light", "standard", "heavy")


def test_environment_kinds_are_two() -> None:
    assert set(RUNTIME_ENVIRONMENT_KINDS) == {"dev_worktree", "dev_worktree_browser"}


def test_phases_are_unique() -> None:
    assert len(set(RUNTIME_PHASES)) == len(RUNTIME_PHASES), "phase tuple has duplicates"


def test_mutation_blocked_phases_subset_of_phases() -> None:
    assert MUTATION_BLOCKED_PHASES.issubset(set(RUNTIME_PHASES))
    assert "checkpointing" in MUTATION_BLOCKED_PHASES
    assert "cleaning" in MUTATION_BLOCKED_PHASES


def test_final_phases_subset_of_phases() -> None:
    assert FINAL_PHASES.issubset(set(RUNTIME_PHASES))
    expected_final = {
        "completed_retained",
        "cancelled_retained",
        "recoverable_failed_retained",
        "terminal_failed",
        "cleaned",
    }
    assert expected_final == FINAL_PHASES


def test_recoverable_phases_subset_of_final() -> None:
    """Recoverable phases must be reachable for re-attach; they are the failure modes."""
    assert RECOVERABLE_PHASES.issubset(set(RUNTIME_PHASES))
    assert "recoverable_failed_retained" in RECOVERABLE_PHASES
    assert "orphaned" in RECOVERABLE_PHASES


def test_pause_states_are_canonical() -> None:
    assert PAUSE_STATES == ("none", "pause_requested", "paused_for_operator", "operator_attached", "resuming")


def test_attach_kinds_terminal_and_browser() -> None:
    assert set(ATTACH_KINDS) == {"terminal", "browser"}


def test_guardrail_types_complete() -> None:
    expected = {
        "repeated_command",
        "repeated_diff",
        "repeated_failure",
        "no_change",
        "budget_exceeded",
        "retry_exhausted",
    }
    assert set(GUARDRAIL_TYPES) == expected


def test_event_types_unique_and_categorized() -> None:
    """Every event type is unique, and the tuple covers task/env/command/process/
    terminal/browser/validation/checkpoint/recovery/cleanup categories."""
    assert len(set(RUNTIME_EVENT_TYPES)) == len(RUNTIME_EVENT_TYPES)
    categories = {ev.split(".")[0] for ev in RUNTIME_EVENT_TYPES}
    expected_categories = {
        "task",
        "env",
        "worktree",
        "plan",
        "decision",
        "command",
        "process",
        "environment",
        "terminal",
        "browser",
        "validation",
        "checkpoint",
        "retry",
        "warning",
        "resource",
        "recovery",
        "cleanup",
    }
    assert expected_categories.issubset(categories), (
        f"missing categories: {expected_categories - categories}"
    )


def test_event_types_use_dot_separator() -> None:
    for ev in RUNTIME_EVENT_TYPES:
        assert "." in ev, f"event {ev!r} should be category.action"
        assert ev == ev.lower(), f"event {ev!r} must be lowercase"
