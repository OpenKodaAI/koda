"""Tests for template management."""

import importlib
import json
from unittest.mock import patch

import pytest

from koda.services.templates import (
    add_template,
    build_skills_awareness_prompt,
    delete_template,
    get_all_templates,
    get_skill_template,
    get_template,
    list_template_names,
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
        assert skills == []
        assert "debug" in builtin
        assert "custom" in user

    def test_user_cannot_override_builtin(self, tmp_templates):
        with pytest.raises(ValueError):
            add_template("debug", "My custom debug")
        templates = get_all_templates()
        assert templates["debug"] != "My custom debug"

    def test_user_can_use_former_skill_name_as_template(self, tmp_templates):
        add_template("security", "Custom security prompt")

        assert get_template("security") == "Custom security prompt"

    def test_empty_file_handled(self, tmp_templates):
        tmp_templates.write_text("")
        templates = get_all_templates()
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


class TestSkillsCompatibility:
    def test_global_skill_templates_are_empty(self, tmp_templates):
        skills, _, _ = list_template_names()
        assert skills == []
        assert get_skill_template("security") is None
        assert get_template("security") is None

    def test_skills_awareness_prompt_is_empty(self):
        assert build_skills_awareness_prompt() == ""
