"""Tests for agent-scoped custom skills: normalization, building, and merging."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from koda.control_plane.agent_spec import normalize_custom_skills
from koda.skills._registry import SkillRegistry, _build_skill_from_dict

# Path to the real skills directory shipped with the repo.
SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "koda" / "skills"


# ---------------------------------------------------------------------------
# normalize_custom_skills
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# _build_skill_from_dict
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# merge_agent_skills
# ---------------------------------------------------------------------------


def test_merge_adds_custom_skills() -> None:
    registry = SkillRegistry(SKILLS_DIR)
    customs = [{"id": "brand-new", "name": "Brand New", "content": "New skill body."}]
    merged = registry.merge_agent_skills(customs)
    assert "brand-new" in merged
    assert merged["brand-new"].name == "Brand New"


def test_merge_overrides_global() -> None:
    registry = SkillRegistry(SKILLS_DIR)
    globals_before = registry.get_all()
    if not globals_before:
        return  # Skip if no global skills exist
    existing_id = next(iter(globals_before))
    customs = [{"id": existing_id, "name": "Override", "content": "Overridden content."}]
    merged = registry.merge_agent_skills(customs)
    assert merged[existing_id].name == "Override"
    assert merged[existing_id].full_content == "Overridden content."


def test_merge_preserves_globals() -> None:
    registry = SkillRegistry(SKILLS_DIR)
    globals_before = registry.get_all()
    merged = registry.merge_agent_skills([{"id": "extra", "name": "Extra", "content": "body"}])
    for gid in globals_before:
        assert gid in merged


def test_merge_empty_customs() -> None:
    registry = SkillRegistry(SKILLS_DIR)
    globals_before = registry.get_all()
    merged = registry.merge_agent_skills([])
    assert merged == globals_before
