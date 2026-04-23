"""Tests for koda.skills._composer."""

from __future__ import annotations

import textwrap
from unittest.mock import MagicMock

from koda.skills._composer import (
    _extract_approach,
    compose_output_requirements,
    compose_skill_prompt,
    resolve_skill_graph,
)
from koda.skills._registry import SkillDefinition
from koda.skills._selector import SkillMatch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _skill(
    *,
    sid: str = "testing",
    name: str = "Testing Expert",
    category: str = "engineering",
    awareness_summary: str = "Helps with testing.",
    full_content: str = "# Testing Expert\nFull content here.",
    requires: tuple[str, ...] = (),
    conflicts: tuple[str, ...] = (),
    instruction: str = "",
    output_format_enforcement: str = "",
) -> SkillDefinition:
    return SkillDefinition(
        id=sid,
        name=name,
        category=category,
        awareness_summary=awareness_summary,
        full_content=full_content,
        requires=requires,
        conflicts=conflicts,
        instruction=instruction,
        output_format_enforcement=output_format_enforcement,
    )


def _match(
    skill: SkillDefinition,
    *,
    composite_score: float = 0.8,
    semantic_score: float = 0.7,
    trigger_matched: bool = False,
    alias_matched: bool = False,
    selection_reason: str = "test",
) -> SkillMatch:
    return SkillMatch(
        skill=skill,
        semantic_score=semantic_score,
        trigger_matched=trigger_matched,
        alias_matched=alias_matched,
        composite_score=composite_score,
        selection_reason=selection_reason,
    )


def _registry_from_skills(*skills: SkillDefinition) -> MagicMock:
    """Create a mock SkillRegistry backed by the given skills."""
    lookup = {s.id: s for s in skills}
    mock = MagicMock()
    mock.get.side_effect = lambda sid: lookup.get(sid)
    return mock


# ---------------------------------------------------------------------------
# 2-tier progressive disclosure tests
# ---------------------------------------------------------------------------


class TestTwoTierDisclosure:
    def test_full_content_for_score_above_threshold(self) -> None:
        """Score >= 0.45 gets full content."""
        sk = _skill(full_content="# Full\nDetailed content.")
        m = _match(sk, composite_score=0.5)
        result = compose_skill_prompt([m], token_budget=4000)
        assert "Detailed content." in result

    def test_excluded_for_score_below_threshold(self) -> None:
        """Score < 0.45 is excluded entirely."""
        sk = _skill(
            awareness_summary="Quick summary.",
            full_content="# Skill\nLong detailed content that should not appear.",
        )
        m = _match(sk, composite_score=0.3)
        result = compose_skill_prompt([m], token_budget=4000)
        assert result == ""

    def test_directive_block_present(self) -> None:
        """Output starts with <expert_skills> containing a <directive>."""
        sk = _skill()
        m = _match(sk, composite_score=0.8)
        result = compose_skill_prompt([m], token_budget=4000)
        assert result.startswith("<expert_skills>")
        assert "<directive>" in result
        assert "You MUST follow the methodology" in result

    def test_instruction_tag_present(self) -> None:
        """Skills with instruction get an <instruction> tag."""
        sk = _skill(instruction="Apply TDD. Write failing tests first.")
        m = _match(sk, composite_score=0.8)
        result = compose_skill_prompt([m], token_budget=4000)
        assert "<instruction>Apply TDD. Write failing tests first.</instruction>" in result

    def test_instruction_tag_absent_when_empty(self) -> None:
        """Skills without instruction omit the <instruction> tag."""
        sk = _skill(instruction="")
        m = _match(sk, composite_score=0.8)
        result = compose_skill_prompt([m], token_budget=4000)
        assert "<instruction>" not in result

    def test_mode_active_attribute(self) -> None:
        """All included skills have mode='active'."""
        sk = _skill()
        m = _match(sk, composite_score=0.8)
        result = compose_skill_prompt([m], token_budget=4000)
        assert 'mode="active"' in result


# ---------------------------------------------------------------------------
# Output requirements tests
# ---------------------------------------------------------------------------


class TestOutputRequirements:
    def test_output_requirements_for_high_confidence(self) -> None:
        """Score >= 0.7 with enforcement text generates <output_requirements>."""
        sk = _skill(
            sid="tdd",
            output_format_enforcement="Structure as Red-Green-Refactor cycles.",
        )
        m = _match(sk, composite_score=0.8)
        result = compose_output_requirements([m])
        assert "<output_requirements>" in result
        assert 'source="skill:tdd"' in result
        assert "Structure as Red-Green-Refactor cycles." in result

    def test_output_requirements_empty_when_no_enforcement(self) -> None:
        """Skills without enforcement text produce empty string."""
        sk = _skill(output_format_enforcement="")
        m = _match(sk, composite_score=0.8)
        result = compose_output_requirements([m])
        assert result == ""

    def test_output_requirements_empty_when_low_confidence(self) -> None:
        """Score 0.5 with enforcement text doesn't generate requirements."""
        sk = _skill(output_format_enforcement="Some format requirement.")
        m = _match(sk, composite_score=0.5)
        result = compose_output_requirements([m])
        assert result == ""


# ---------------------------------------------------------------------------
# Token budget tests
# ---------------------------------------------------------------------------


class TestTokenBudget:
    def test_token_budget_truncates_lower_scored(self) -> None:
        # Create 3 skills with large content; budget should force dropping the lowest.
        skills = [
            _skill(sid="high", name="High", full_content="A" * 4000),
            _skill(sid="mid", name="Mid", full_content="B" * 4000),
            _skill(sid="low", name="Low", full_content="C" * 4000),
        ]
        matches = [
            _match(skills[0], composite_score=0.9),
            _match(skills[1], composite_score=0.8),
            _match(skills[2], composite_score=0.7),
        ]
        # Budget of 2500 tokens ~ 10000 chars.  Two skills fit (8000 chars),
        # three do not (12000 chars = 3000 tokens).
        result = compose_skill_prompt(matches, token_budget=2500, progressive=False)
        assert "High" in result
        assert "Mid" in result
        assert 'name="Low"' not in result


# ---------------------------------------------------------------------------
# XML wrapping tests
# ---------------------------------------------------------------------------


class TestXMLWrapping:
    def test_compose_wraps_in_expert_skills_tag(self) -> None:
        sk = _skill()
        m = _match(sk)
        result = compose_skill_prompt([m], token_budget=4000)
        assert result.startswith("<expert_skills>")
        assert result.endswith("</expert_skills>")

    def test_each_skill_has_xml_attributes(self) -> None:
        sk = _skill(name="TDD Expert", category="engineering")
        m = _match(sk, composite_score=0.85)
        result = compose_skill_prompt([m], token_budget=4000)
        assert 'name="TDD Expert"' in result
        assert 'category="engineering"' in result
        assert 'confidence="85%"' in result


# ---------------------------------------------------------------------------
# Graph resolution tests
# ---------------------------------------------------------------------------


class TestResolveGraph:
    def test_resolve_graph_expands_dependencies(self) -> None:
        base = _skill(sid="base", name="Base")
        dependent = _skill(sid="dep", name="Dependent", requires=("base",))
        registry = _registry_from_skills(base, dependent)

        selected = [_match(dependent, composite_score=0.8)]
        resolved = resolve_skill_graph(selected, registry)

        resolved_ids = [m.skill.id for m in resolved]
        assert "base" in resolved_ids
        assert "dep" in resolved_ids
        # Base should come before dependent (topological order).
        assert resolved_ids.index("base") < resolved_ids.index("dep")

    def test_resolve_graph_removes_conflicts(self) -> None:
        a = _skill(sid="a", name="A", conflicts=("b",))
        b = _skill(sid="b", name="B")
        registry = _registry_from_skills(a, b)

        selected = [
            _match(a, composite_score=0.9),
            _match(b, composite_score=0.6),
        ]
        resolved = resolve_skill_graph(selected, registry)
        resolved_ids = [m.skill.id for m in resolved]
        assert "a" in resolved_ids
        assert "b" not in resolved_ids


# ---------------------------------------------------------------------------
# Approach extraction tests
# ---------------------------------------------------------------------------


class TestApproachExtraction:
    def test_approach_section_extraction(self) -> None:
        content = textwrap.dedent("""\
            # Skill Title

            ## Overview
            Some overview.

            ## Approach
            1. First step.
            2. Second step.

            ## Examples
            Some examples.
        """)
        result = _extract_approach(content)
        assert "First step" in result
        assert "Second step" in result
        assert "Some overview" not in result
        assert "Some examples" not in result

    def test_approach_extraction_abordagem(self) -> None:
        content = "## Abordagem\nPassos detalhados.\n\n## Outro\nAlgo."
        result = _extract_approach(content)
        assert "Passos detalhados." in result
        assert "Algo." not in result


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_input_returns_empty_string(self) -> None:
        assert compose_skill_prompt([]) == ""

    def test_resolve_graph_empty_input(self) -> None:
        registry = _registry_from_skills()
        assert resolve_skill_graph([], registry) == []
