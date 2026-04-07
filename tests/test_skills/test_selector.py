"""Tests for koda.skills._selector."""

from __future__ import annotations

import re
from typing import Any
from unittest.mock import MagicMock

from koda.skills._index import SkillEmbeddingIndex
from koda.skills._registry import SkillDefinition, SkillRegistry
from koda.skills._selector import SkillSelector

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_skill(
    *,
    id: str = "test-skill",
    name: str = "Test Skill",
    aliases: tuple[str, ...] = (),
    triggers: tuple[re.Pattern[str], ...] = (),
    requires: tuple[str, ...] = (),
    conflicts: tuple[str, ...] = (),
    **kwargs: Any,
) -> SkillDefinition:
    return SkillDefinition(
        id=id,
        name=name,
        aliases=aliases,
        triggers=triggers,
        requires=requires,
        conflicts=conflicts,
        **kwargs,
    )


def _mock_registry(skills: dict[str, SkillDefinition]) -> SkillRegistry:
    registry = MagicMock(spec=SkillRegistry)
    registry.get_all.return_value = dict(skills)
    registry.get.side_effect = lambda sid: skills.get(sid)
    return registry


def _mock_index(
    results: list[tuple[str, float]] | None = None,
) -> SkillEmbeddingIndex:
    index = MagicMock(spec=SkillEmbeddingIndex)
    index.query.return_value = results or []
    return index


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAliasMatch:
    def test_alias_match_returns_max_score(self) -> None:
        """Query containing an alias should produce composite_score=1.0."""
        tdd = _make_skill(id="tdd", name="TDD Expert", aliases=("tdd", "test-driven"))
        registry = _mock_registry({"tdd": tdd})
        index = _mock_index()

        selector = SkillSelector(registry, index)
        matches = selector.select("use tdd for this")

        assert len(matches) >= 1
        m = next(m for m in matches if m.skill.id == "tdd")
        assert m.alias_matched is True
        assert m.composite_score == 1.0
        assert "alias match" in m.selection_reason


class TestTriggerRegex:
    def test_trigger_regex_boosts_score(self) -> None:
        """A trigger match should add 0.4 to the composite score."""
        skill = _make_skill(
            id="sql",
            name="SQL Expert",
            triggers=(re.compile(r"\bquery\b", re.IGNORECASE),),
        )
        registry = _mock_registry({"sql": skill})
        # Semantic returns 0.5 similarity
        index = _mock_index(results=[("sql", 0.5)])

        selector = SkillSelector(registry, index)
        matches = selector.select("run this query")

        assert len(matches) == 1
        m = matches[0]
        assert m.trigger_matched is True
        # 0.5 * 0.6 + 0.4 = 0.7
        assert abs(m.composite_score - 0.7) < 1e-6
        assert "trigger regex matched" in m.selection_reason


class TestSemanticFallback:
    def test_semantic_fallback_when_no_trigger(self) -> None:
        """When only embedding similarity fires, composite = semantic * 0.6."""
        skill = _make_skill(id="design", name="Design Expert")
        registry = _mock_registry({"design": skill})
        index = _mock_index(results=[("design", 0.8)])

        selector = SkillSelector(registry, index)
        matches = selector.select("create a beautiful interface")

        assert len(matches) == 1
        m = matches[0]
        assert m.trigger_matched is False
        assert m.alias_matched is False
        # 0.8 * 0.6 = 0.48
        assert abs(m.composite_score - 0.48) < 1e-6


class TestConflictResolution:
    def test_conflict_resolution_keeps_higher_score(self) -> None:
        """When two skills conflict, only the higher-scored one survives."""
        a = _make_skill(id="skill-a", name="A", conflicts=("skill-b",))
        b = _make_skill(id="skill-b", name="B", conflicts=("skill-a",))
        registry = _mock_registry({"skill-a": a, "skill-b": b})
        # A has higher similarity than B
        index = _mock_index(results=[("skill-a", 0.9), ("skill-b", 0.5)])

        selector = SkillSelector(registry, index)
        matches = selector.select("something relevant")

        ids = [m.skill.id for m in matches]
        assert "skill-a" in ids
        assert "skill-b" not in ids


class TestDependencyExpansion:
    def test_dependency_expansion_pulls_required(self) -> None:
        """If skill A requires skill B, B should appear even if not selected."""
        b = _make_skill(id="skill-b", name="B")
        a = _make_skill(id="skill-a", name="A", requires=("skill-b",))
        registry = _mock_registry({"skill-a": a, "skill-b": b})
        # Only A shows up from semantic search
        index = _mock_index(results=[("skill-a", 0.8)])

        selector = SkillSelector(registry, index)
        matches = selector.select("use skill A")

        ids = [m.skill.id for m in matches]
        assert "skill-a" in ids
        assert "skill-b" in ids

        dep_match = next(m for m in matches if m.skill.id == "skill-b")
        assert "dependency of skill-a" in dep_match.selection_reason


class TestAgentPolicy:
    def test_agent_policy_disabled_skills_filtered(self) -> None:
        """disabled_skills should remove the named skill from results."""
        skill = _make_skill(id="blocked", name="Blocked")
        registry = _mock_registry({"blocked": skill})
        index = _mock_index(results=[("blocked", 0.9)])

        selector = SkillSelector(registry, index)
        matches = selector.select(
            "anything",
            agent_skill_policy={"disabled_skills": ["blocked"]},
        )
        assert len(matches) == 0

    def test_agent_policy_max_skills_respected(self) -> None:
        """max_skills in policy caps the number of returned matches."""
        skills = {f"s{i}": _make_skill(id=f"s{i}", name=f"Skill {i}") for i in range(5)}
        registry = _mock_registry(skills)
        index = _mock_index(results=[(f"s{i}", 0.9 - i * 0.1) for i in range(5)])

        selector = SkillSelector(registry, index)
        matches = selector.select(
            "anything",
            agent_skill_policy={"max_skills": 2},
        )
        assert len(matches) <= 2

    def test_agent_policy_enabled_false_returns_empty(self) -> None:
        """enabled=False should return an empty list."""
        skill = _make_skill(id="any", name="Any")
        registry = _mock_registry({"any": skill})
        index = _mock_index(results=[("any", 0.9)])

        selector = SkillSelector(registry, index)
        matches = selector.select(
            "anything",
            agent_skill_policy={"enabled": False},
        )
        assert matches == []


class TestEdgeCases:
    def test_select_returns_empty_for_irrelevant_query(self) -> None:
        """A nonsense query with no signals should produce no matches."""
        skill = _make_skill(id="sql", name="SQL Expert")
        registry = _mock_registry({"sql": skill})
        # Index returns nothing above threshold
        index = _mock_index(results=[])

        selector = SkillSelector(registry, index)
        matches = selector.select("xyzzy foobarbaz")
        assert matches == []

    def test_composite_score_clamped_to_one(self) -> None:
        """alias + trigger + semantic should not exceed 1.0."""
        skill = _make_skill(
            id="tdd",
            name="TDD",
            aliases=("tdd",),
            triggers=(re.compile(r"\btdd\b", re.IGNORECASE),),
        )
        registry = _mock_registry({"tdd": skill})
        index = _mock_index(results=[("tdd", 0.95)])

        selector = SkillSelector(registry, index)
        matches = selector.select("use tdd here")

        assert len(matches) >= 1
        m = next(m for m in matches if m.skill.id == "tdd")
        assert m.composite_score <= 1.0
