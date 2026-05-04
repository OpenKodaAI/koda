"""Tests for koda.skills._registry."""

from __future__ import annotations

from koda.skills._registry import (
    SkillDefinition,
    SkillRegistry,
    _build_skill_from_dict,
    build_skill_registry_from_custom_skills,
    get_shared_registry,
)


def test_empty_registry_has_no_skills() -> None:
    registry = SkillRegistry()

    assert registry.get_all() == {}
    assert registry.get("security") is None
    assert registry.resolve_alias("security") is None
    assert registry.reload_if_stale() is False


def test_registry_resolves_ids_and_aliases() -> None:
    skill = SkillDefinition(
        id="review",
        name="Code Review",
        aliases=("code-review", "revisao"),
        full_content="# Review",
    )
    registry = SkillRegistry([skill])

    assert registry.get("review") == skill
    assert registry.resolve_alias("review") == "review"
    assert registry.resolve_alias("Code Review") == "review"
    assert registry.resolve_alias("CODE-REVIEW") == "review"
    assert registry.resolve_alias("revisao") == "review"


def test_build_skill_from_dict_extracts_when_to_use_and_instruction() -> None:
    skill = _build_skill_from_dict(
        {
            "id": "deploy-helper",
            "name": "Deploy Helper",
            "aliases": ["deploy"],
            "tags": ["ops"],
            "instruction": "Guide deployments",
            "content": "Intro\n<when_to_use>Use when planning production deploys.</when_to_use>",
            "output_format_enforcement": "Use a checklist",
        }
    )

    assert skill.id == "deploy-helper"
    assert skill.aliases == ("deploy",)
    assert skill.tags == ("ops",)
    assert skill.instruction == "Guide deployments"
    assert skill.when_to_use == "Use when planning production deploys."
    assert skill.awareness_summary == "Use when planning production deploys."
    assert skill.output_format_enforcement == "Use a checklist"
    assert "Deploy Helper" in skill.embedding_text
    assert "production deploys" in skill.embedding_text


def test_build_registry_uses_only_custom_skills() -> None:
    registry = build_skill_registry_from_custom_skills(
        [
            {
                "id": "agent-only",
                "name": "Agent Only",
                "aliases": ["only"],
                "content": "# Agent Only",
            }
        ]
    )

    assert sorted(registry.get_all()) == ["agent-only"]
    assert registry.resolve_alias("only") == "agent-only"
    assert registry.get("security") is None


def test_build_registry_ignores_disabled_and_empty_skills() -> None:
    registry = build_skill_registry_from_custom_skills(
        [
            {"id": "enabled", "name": "Enabled", "content": "body"},
            {"id": "disabled", "name": "Disabled", "content": "body", "enabled": False},
            {"id": "empty", "name": "Empty", "content": ""},
        ]
    )

    assert sorted(registry.get_all()) == ["enabled"]


def test_build_registry_applies_skill_policy() -> None:
    registry = build_skill_registry_from_custom_skills(
        [
            {"id": "allowed", "name": "Allowed", "content": "body"},
            {"id": "blocked", "name": "Blocked", "content": "body"},
        ],
        {"enabled_skills": ["allowed"], "disabled_skills": ["blocked"]},
    )

    assert sorted(registry.get_all()) == ["allowed"]


def test_build_registry_policy_disabled_returns_empty() -> None:
    registry = build_skill_registry_from_custom_skills(
        [{"id": "any", "name": "Any", "content": "body"}],
        {"enabled": False},
    )

    assert registry.get_all() == {}


def test_shared_registry_is_empty_compatibility_shim() -> None:
    assert get_shared_registry().get_all() == {}
