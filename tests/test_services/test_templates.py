"""Tests for template management."""

import importlib
import json
from unittest.mock import patch

import pytest

from koda.services.templates import (
    _SKILL_TEMPLATES,
    add_template,
    build_relevant_skills_awareness_prompt,
    build_skills_awareness_prompt,
    delete_template,
    get_all_templates,
    get_skill_template,
    get_template,
    list_template_names,
    select_relevant_skills,
)


@pytest.fixture
def tmp_templates(tmp_path):
    """Use a temporary file for templates."""
    path = tmp_path / "templates.json"
    with patch("koda.services.templates.TEMPLATES_PATH", path):
        yield path


class TestTemplates:
    def test_builtin_templates_exist(self, tmp_templates):
        templates = get_all_templates()
        assert "debug" in templates
        assert "write-tests" in templates
        assert "explain" in templates
        assert "refactor" in templates

    def test_get_builtin_template(self, tmp_templates):
        t = get_template("debug")
        assert t is not None
        assert "debug" in t.lower()

    def test_get_nonexistent_template(self, tmp_templates):
        assert get_template("nonexistent") is None

    def test_add_user_template(self, tmp_templates):
        add_template("my-template", "Custom prompt")
        t = get_template("my-template")
        assert t == "Custom prompt"
        assert get_template("user/my-template") == "Custom prompt"

    def test_add_template_persists(self, tmp_templates):
        add_template("persist-test", "Persistent")
        data = json.loads(tmp_templates.read_text())
        assert "user/persist-test" in data

    def test_delete_user_template(self, tmp_templates):
        add_template("to-delete", "Temporary")
        assert delete_template("to-delete")
        assert get_template("to-delete") is None

    def test_cannot_delete_builtin(self, tmp_templates):
        assert not delete_template("debug")
        assert get_template("debug") is not None

    def test_delete_nonexistent(self, tmp_templates):
        assert not delete_template("nope")

    def test_list_template_names(self, tmp_templates):
        add_template("custom", "My custom")
        skills, builtin, user = list_template_names()
        assert "debug" in builtin
        assert "custom" in user
        assert isinstance(skills, list)

    def test_user_cannot_override_builtin(self, tmp_templates):
        with pytest.raises(ValueError):
            add_template("debug", "My custom debug")
        templates = get_all_templates()
        assert templates["debug"] != "My custom debug"

    def test_empty_file_handled(self, tmp_templates):
        tmp_templates.write_text("")
        templates = get_all_templates()
        # Should still have builtins
        assert "debug" in templates

    def test_inline_templates_json_is_loaded(self, monkeypatch):
        monkeypatch.setenv("TEMPLATES_JSON", json.dumps({"user/inline": "Inline prompt"}))
        import koda.services.templates as templates_module

        reloaded = importlib.reload(templates_module)
        try:
            assert reloaded.get_template("inline") == "Inline prompt"
        finally:
            monkeypatch.delenv("TEMPLATES_JSON", raising=False)
            importlib.reload(templates_module)


class TestSkills:
    def test_skills_loaded(self):
        """Skills should be loaded from the skills directory."""
        assert len(_SKILL_TEMPLATES) > 0

    def test_expected_skills_exist(self):
        """All 17 expected skill files should be loaded."""
        expected = [
            "security",
            "architecture",
            "mobile",
            "best-practices",
            "ddd",
            "tdd",
            "clean-arch",
            "microservices",
            "data-analysis",
            "sql",
            "dynamodb",
            "aws",
            "docs",
            "code-review",
            "design",
            "prototype",
            "deep-research",
        ]
        for name in expected:
            assert name in _SKILL_TEMPLATES, f"Skill '{name}' not found"

    def test_skill_accessible_via_get_template(self, tmp_templates):
        """Skills should be accessible via get_template."""
        t = get_template("security")
        assert t is not None
        assert "OWASP" in t or "security" in t.lower()
        assert get_skill_template("security") == t

    def test_skill_in_get_all_templates(self, tmp_templates):
        """Skills should appear in get_all_templates."""
        templates = get_all_templates()
        assert "security" in templates
        assert "code-review" in templates

    def test_cannot_delete_skill(self, tmp_templates):
        """Skills should be protected from deletion."""
        assert not delete_template("security")
        assert get_template("security") is not None

    def test_skills_in_list_template_names(self, tmp_templates):
        """Skills should appear in the skills section of list_template_names."""
        skills, builtin, user = list_template_names()
        assert "security" in skills
        assert "code-review" in skills
        # code-review should NOT be in builtins (removed)
        assert "code-review" not in builtin

    def test_user_cannot_override_skill(self, tmp_templates):
        with pytest.raises(ValueError):
            add_template("security", "My custom security")
        t = get_template("security")
        assert t is not None
        assert t != "My custom security"

    def test_skill_content_is_markdown(self):
        """Each skill should contain structured markdown content."""
        for name, content in _SKILL_TEMPLATES.items():
            assert content.startswith("#"), f"Skill '{name}' should start with a markdown heading"
            assert "## Approach" in content, f"Skill '{name}' should have an Approach section"
            assert "## Key Principles" in content, f"Skill '{name}' should have Key Principles"

    def test_inline_skills_json_is_loaded(self, monkeypatch):
        monkeypatch.setenv("SKILLS_JSON", json.dumps({"incident": "# Incident\n## Approach\nx\n## Key Principles\ny"}))
        import koda.services.templates as templates_module

        reloaded = importlib.reload(templates_module)
        try:
            assert reloaded.get_template("incident") is not None
        finally:
            monkeypatch.delenv("SKILLS_JSON", raising=False)
            importlib.reload(templates_module)


class TestSkillsAwareness:
    def test_returns_nonempty_string(self):
        result = build_skills_awareness_prompt()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_has_xml_tags(self):
        result = build_skills_awareness_prompt()
        assert "<expert_skills>" in result
        assert "</expert_skills>" in result

    def test_contains_all_skill_names(self):
        result = build_skills_awareness_prompt()
        for name in _SKILL_TEMPLATES:
            assert f"**{name}**" in result

    def test_contains_descriptions(self):
        result = build_skills_awareness_prompt()
        assert "security" in result.lower()
        assert "architecture" in result.lower() or "system design" in result.lower()

    def test_empty_when_no_skills(self):
        with patch("koda.services.templates._SKILL_TEMPLATES", {}):
            assert build_skills_awareness_prompt() == ""

    def test_relevant_skills_awareness_prompt_filters_to_matching_skills(self):
        result = build_relevant_skills_awareness_prompt("Faça um code review com foco em segurança e arquitetura.")
        assert "security" in result.lower()
        assert "architecture" in result.lower()

    def test_relevant_skills_awareness_prompt_returns_empty_when_irrelevant(self):
        assert build_relevant_skills_awareness_prompt("me diga oi") == ""

    def test_select_relevant_skills_returns_scored_entries(self):
        result = select_relevant_skills("Preciso de architecture review com foco em security.")
        assert result
        assert result[0]["name"]
        assert float(result[0]["score"]) >= 1.0
