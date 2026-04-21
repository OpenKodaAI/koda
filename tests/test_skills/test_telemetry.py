"""Tests for koda.skills._telemetry."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from koda.skills._registry import SkillDefinition
from koda.skills._selector import SkillMatch
from koda.skills._telemetry import (
    _extract_format_markers,
    emit_skill_compliance,
    emit_skill_invocation,
    emit_skill_reload,
    emit_skill_selection,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _skill(sid: str = "tdd") -> SkillDefinition:
    return SkillDefinition(id=sid, name="TDD Expert")


def _match(
    skill: SkillDefinition,
    *,
    composite_score: float = 0.8,
    semantic_score: float = 0.7,
    trigger_matched: bool = True,
    selection_reason: str = "test",
) -> SkillMatch:
    return SkillMatch(
        skill=skill,
        semantic_score=semantic_score,
        trigger_matched=trigger_matched,
        alias_matched=False,
        composite_score=composite_score,
        selection_reason=selection_reason,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEmitSkillSelection:
    @patch("koda.skills._telemetry.emit")
    def test_emit_skill_selection_fires_event(self, mock_emit: MagicMock) -> None:
        sk = _skill("architecture")
        m = _match(sk, composite_score=0.85, semantic_score=0.72, trigger_matched=True)

        emit_skill_selection(
            user_id=42,
            task_id=7,
            query_text="design a microservice",
            matches=[m, m],
            resolved=[m],
            included_in_prompt=True,
        )

        mock_emit.assert_called_once()
        event = mock_emit.call_args[0][0]
        assert event.event_type == "skill.selection"
        assert event.user_id == 42
        assert event.task_id == 7

        details = event.details
        assert details["query_length"] == len("design a microservice")
        assert details["candidates_evaluated"] == 2
        assert details["included_in_prompt"] is True
        assert len(details["skills_selected"]) == 1

        sel = details["skills_selected"][0]
        assert sel["id"] == "architecture"
        assert sel["composite_score"] == 0.85
        assert sel["semantic_score"] == 0.72
        assert sel["trigger_matched"] is True
        assert sel["reason"] == "test"


class TestEmitSkillInvocation:
    @patch("koda.skills._telemetry.emit")
    def test_emit_skill_invocation_fires_event(self, mock_emit: MagicMock) -> None:
        emit_skill_invocation(user_id=1, task_id=2, skill_id="tdd", explicit=True)

        mock_emit.assert_called_once()
        event = mock_emit.call_args[0][0]
        assert event.event_type == "skill.invocation"
        assert event.details["skill_id"] == "tdd"
        assert event.details["explicit"] is True


class TestEmitSkillReload:
    @patch("koda.skills._telemetry.emit")
    def test_emit_skill_reload_only_when_changes(self, mock_emit: MagicMock) -> None:
        # No changes should NOT emit.
        emit_skill_reload(skills_added=[], skills_removed=[], skills_modified=[])
        mock_emit.assert_not_called()

        # With changes should emit.
        emit_skill_reload(skills_added=["new-skill"], skills_removed=[], skills_modified=["old-skill"])
        mock_emit.assert_called_once()
        event = mock_emit.call_args[0][0]
        assert event.event_type == "skill.reload"
        assert event.details["added"] == ["new-skill"]
        assert event.details["removed"] == []
        assert event.details["modified"] == ["old-skill"]


# ---------------------------------------------------------------------------
# Format marker extraction
# ---------------------------------------------------------------------------


class TestExtractFormatMarkers:
    def test_extract_format_markers_bold(self) -> None:
        markers = _extract_format_markers("**Strengths** then **Issues**")
        assert markers == ["Strengths", "Issues"]

    def test_extract_format_markers_bracketed(self) -> None:
        markers = _extract_format_markers("[Severity: Critical]")
        assert markers == ["Severity: Critical"]

    def test_extract_format_markers_mixed(self) -> None:
        markers = _extract_format_markers("**Risk Assessment** with [OWASP] references")
        assert "Risk Assessment" in markers
        assert "OWASP" in markers
        assert len(markers) == 2

    def test_extract_format_markers_fallback_then(self) -> None:
        markers = _extract_format_markers("list problems, then propose fixes, then summarize")
        assert len(markers) == 3

    def test_extract_format_markers_empty(self) -> None:
        assert _extract_format_markers("") == []

    def test_extract_format_markers_no_structure(self) -> None:
        # Single phrase without bold/bracketed/then => no markers
        assert _extract_format_markers("just write a summary") == []


# ---------------------------------------------------------------------------
# Skill compliance emission
# ---------------------------------------------------------------------------


class TestEmitSkillCompliance:
    @patch("koda.skills._telemetry.emit")
    def test_emit_skill_compliance_high(self, mock_emit: MagicMock) -> None:
        score = emit_skill_compliance(
            user_id=1,
            task_id=2,
            skill_id="code-review",
            response_text="**Strengths**: good. **Issues**: none.",
            output_format_enforcement="**Strengths** then **Issues**",
        )
        assert score == 1.0
        mock_emit.assert_called_once()
        event = mock_emit.call_args[0][0]
        assert event.event_type == "skill.compliance"
        assert event.details["markers_found"] == 2
        assert event.details["markers_total"] == 2
        assert event.details["compliance_score"] == 1.0

    @patch("koda.skills._telemetry.emit")
    def test_emit_skill_compliance_partial(self, mock_emit: MagicMock) -> None:
        score = emit_skill_compliance(
            user_id=1,
            task_id=2,
            skill_id="code-review",
            response_text="**Strengths**: good stuff here.",
            output_format_enforcement="**Strengths** then **Issues**",
        )
        assert score == 0.5
        event = mock_emit.call_args[0][0]
        assert event.details["markers_found"] == 1
        assert event.details["compliance_score"] == 0.5

    @patch("koda.skills._telemetry.emit")
    def test_emit_skill_compliance_zero(self, mock_emit: MagicMock) -> None:
        score = emit_skill_compliance(
            user_id=1,
            task_id=2,
            skill_id="code-review",
            response_text="Here is a plain answer with no structure.",
            output_format_enforcement="**Strengths** then **Issues**",
        )
        assert score == 0.0
        mock_emit.assert_called_once()
        assert mock_emit.call_args[0][0].details["compliance_score"] == 0.0

    def test_emit_skill_compliance_empty_enforcement(self) -> None:
        score = emit_skill_compliance(
            user_id=1,
            task_id=2,
            skill_id="code-review",
            response_text="Some response",
            output_format_enforcement="",
        )
        assert score == 0.0

    def test_emit_skill_compliance_empty_response(self) -> None:
        score = emit_skill_compliance(
            user_id=1,
            task_id=2,
            skill_id="code-review",
            response_text="",
            output_format_enforcement="**Strengths**",
        )
        assert score == 0.0
