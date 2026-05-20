"""Tests for agent-scoped custom skills."""

from __future__ import annotations

from typing import Any

from koda.control_plane.agent_spec import normalize_custom_skills, normalize_skill_policy
from koda.skills._registry import _build_skill_from_dict, build_skill_registry_from_custom_skills


def test_normalize_valid_skill() -> None:
    raw = [
        {
            "id": "my-skill",
            "name": "My Skill",
            "content": "Do the thing.",
            "instruction": "Help with things",
            "category": "ops",
            "aliases": ["ms"],
            "tags": ["automation"],
            "enabled": False,
            "output_format_enforcement": "json",
        }
    ]
    result = normalize_custom_skills(raw)
    assert len(result) == 1
    skill = result[0]
    assert skill["id"] == "my-skill"
    assert skill["name"] == "My Skill"
    assert skill["content"] == "Do the thing."
    assert skill["instruction"] == "Help with things"
    assert skill["category"] == "ops"
    assert skill["aliases"] == ["ms"]
    assert skill["tags"] == ["automation"]
    assert skill["enabled"] is False
    assert skill["output_format_enforcement"] == "json"


def test_normalize_minimal_skill() -> None:
    raw = [{"name": "Quick Helper", "content": "Some content here."}]
    result = normalize_custom_skills(raw)
    assert len(result) == 1
    skill = result[0]
    assert skill["id"] == "quick-helper"
    assert skill["name"] == "Quick Helper"
    assert skill["content"] == "Some content here."
    assert skill["instruction"] == ""
    assert skill["category"] == "general"
    assert skill["aliases"] == []
    assert skill["tags"] == []
    assert skill["enabled"] is True


def test_normalize_filters_invalid() -> None:
    raw: list[Any] = [
        "not a dict",
        {"name": "No Content"},
        {"content": "No Name"},
        {"name": "Valid", "content": "OK"},
    ]
    result = normalize_custom_skills(raw)
    assert len(result) == 1
    assert result[0]["name"] == "Valid"


def test_normalize_slugify_id() -> None:
    raw = [{"name": "My Custom Skill", "content": "body"}]
    result = normalize_custom_skills(raw)
    assert result[0]["id"] == "my-custom-skill"


def test_normalize_empty_list() -> None:
    assert normalize_custom_skills([]) == []


def test_normalize_non_list() -> None:
    assert normalize_custom_skills("not a list") == []
    assert normalize_custom_skills(None) == []
    assert normalize_custom_skills(42) == []


def test_normalize_skill_policy() -> None:
    result = normalize_skill_policy(
        {
            "enabled": False,
            "max_skills": "3",
            "skill_budget_pct": "0.25",
            "enabled_skills": ["review", "", 123],
            "enabled_skill_packages": ["safe_pack", ""],
            "disabled_skills": ["legacy"],
        }
    )

    assert result == {
        "enabled": False,
        "max_skills": 3,
        "skill_budget_pct": 0.25,
        "enabled_skills": ["review", "123"],
        "enabled_skill_packages": ["safe_pack"],
        "disabled_skills": ["legacy"],
    }


def test_build_from_dict_full() -> None:
    raw = {
        "id": "custom-deploy",
        "name": "Deploy Helper",
        "aliases": ["deployer"],
        "tags": ["devops"],
        "category": "ops",
        "instruction": "Guides deployment steps",
        "content": "Full deployment guide content.",
        "output_format_enforcement": "markdown",
    }
    skill = _build_skill_from_dict(raw)
    assert skill.id == "custom-deploy"
    assert skill.name == "Deploy Helper"
    assert skill.aliases == ("deployer",)
    assert skill.tags == ("devops",)
    assert skill.category == "ops"
    assert skill.instruction == "Guides deployment steps"
    assert skill.full_content == "Full deployment guide content."
    assert skill.output_format_enforcement == "markdown"
    assert skill.base_priority == 50
    assert skill.max_token_budget == 2500
    assert skill.version == "1.0.0"


def test_build_from_dict_minimal() -> None:
    raw = {"id": "mini", "content": "Minimal content"}
    skill = _build_skill_from_dict(raw)
    assert skill.id == "mini"
    assert skill.name == "mini"
    assert skill.aliases == ()
    assert skill.category == "general"
    assert skill.awareness_summary == "mini"


def test_build_from_dict_extracts_when_to_use() -> None:
    raw = {
        "id": "wtu-test",
        "name": "WTU Test",
        "content": "Preamble.\n<when_to_use>Use this when deploying to production.</when_to_use>\nMore text.",
    }
    skill = _build_skill_from_dict(raw)
    assert skill.when_to_use == "Use this when deploying to production."
    assert "Use this when deploying" in skill.awareness_summary


def test_build_from_dict_uses_instruction_as_summary() -> None:
    raw = {
        "id": "instr-test",
        "name": "Instruction Test",
        "instruction": "Helps with database migrations",
        "content": "Content without when_to_use.",
    }
    skill = _build_skill_from_dict(raw)
    assert skill.when_to_use == ""
    assert skill.awareness_summary == "Helps with database migrations"


def test_build_registry_has_no_global_fallback() -> None:
    registry = build_skill_registry_from_custom_skills([])
    assert registry.get_all() == {}


def test_build_registry_filters_disabled_custom_skills() -> None:
    registry = build_skill_registry_from_custom_skills(
        [
            {"id": "active", "name": "Active", "content": "body"},
            {"id": "inactive", "name": "Inactive", "content": "body", "enabled": False},
        ],
        {"enabled_skills": ["active", "inactive"]},
    )

    assert sorted(registry.get_all()) == ["active"]


def test_build_registry_filters_by_policy() -> None:
    registry = build_skill_registry_from_custom_skills(
        [
            {"id": "review", "name": "Review", "content": "body"},
            {"id": "security", "name": "Security", "content": "body"},
        ],
        {"enabled_skills": ["review"]},
    )

    assert sorted(registry.get_all()) == ["review"]


def test_build_registry_requires_explicit_skill_allowlist() -> None:
    registry = build_skill_registry_from_custom_skills(
        [{"id": "review", "name": "Review", "content": "body"}],
        {},
    )

    assert registry.get_all() == {}
