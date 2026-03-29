"""Tests for tool_prompt: dynamic system prompt generation."""

from unittest.mock import patch

from koda.services.tool_prompt import build_agent_tools_prompt


class TestBuildBotToolsPrompt:
    def test_default_prompt_has_core_tools(self):
        prompt = build_agent_tools_prompt()
        assert "<agent_tools>" in prompt
        assert "</agent_tools>" in prompt
        assert "cron_list" in prompt
        assert "cron_add" in prompt
        assert "web_search" in prompt
        assert "fetch_url" in prompt
        assert "agent_get_status" in prompt
        assert "agent_set_workdir" in prompt

    def test_default_prompt_has_protocol(self):
        prompt = build_agent_tools_prompt()
        assert "<agent_cmd" in prompt
        assert "tool_result" in prompt
        assert "do NOT tell the user to type" in prompt.lower() or "Do NOT instruct" in prompt

    def test_gws_section_when_enabled(self):
        with patch("koda.services.tool_prompt.GWS_ENABLED", True):
            prompt = build_agent_tools_prompt()
        assert "Google Workspace" in prompt
        assert "`gws`" in prompt

    def test_no_gws_section_when_disabled(self):
        with patch("koda.services.tool_prompt.GWS_ENABLED", False):
            prompt = build_agent_tools_prompt()
        assert "Google Workspace" not in prompt

    def test_jira_section_when_enabled(self):
        with patch("koda.services.tool_prompt.JIRA_ENABLED", True):
            prompt = build_agent_tools_prompt()
        assert "Jira" in prompt
        assert "`jira`" in prompt
        assert "Build the full issue dossier" in prompt
        assert "comment_get" in prompt
        assert "comment_edit" in prompt
        assert "comment_delete" in prompt
        assert "comment_reply" in prompt
        assert "linked top-level comments" in prompt
        assert "build the full issue dossier first" in prompt
        assert "keep the task read-only" in prompt

    def test_no_jira_section_when_disabled(self):
        with patch("koda.services.tool_prompt.JIRA_ENABLED", False):
            prompt = build_agent_tools_prompt()
        assert "### Jira" not in prompt

    def test_confluence_section_when_enabled(self):
        with patch("koda.services.tool_prompt.CONFLUENCE_ENABLED", True):
            prompt = build_agent_tools_prompt()
        assert "Confluence" in prompt

    def test_no_confluence_section_when_disabled(self):
        with patch("koda.services.tool_prompt.CONFLUENCE_ENABLED", False):
            prompt = build_agent_tools_prompt()
        assert "### Confluence" not in prompt

    def test_all_services_enabled(self):
        with (
            patch("koda.services.tool_prompt.GWS_ENABLED", True),
            patch("koda.services.tool_prompt.JIRA_ENABLED", True),
            patch("koda.services.tool_prompt.CONFLUENCE_ENABLED", True),
        ):
            prompt = build_agent_tools_prompt()
        assert "Google Workspace" in prompt
        assert "### Jira" in prompt
        assert "### Confluence" in prompt

    def test_browser_section_when_enabled(self):
        with patch("koda.services.tool_prompt.BROWSER_FEATURES_ENABLED", True):
            prompt = build_agent_tools_prompt()
        assert "### Browser Automation" in prompt
        assert "browser_navigate" in prompt
        assert "browser_click" in prompt
        assert "browser_screenshot" in prompt
        assert "browser_forward" in prompt
        assert "browser_hover" in prompt
        assert "browser_press_key" in prompt
        assert "Browser Workflow Best Practices" in prompt

    def test_no_browser_section_when_disabled(self):
        with patch("koda.services.tool_prompt.BROWSER_FEATURES_ENABLED", False):
            prompt = build_agent_tools_prompt()
        assert "### Browser Automation" not in prompt
        assert "browser_navigate" not in prompt

    def test_postgres_section_when_enabled(self):
        with patch("koda.services.tool_prompt.POSTGRES_ENABLED", True):
            prompt = build_agent_tools_prompt()
        assert "### Database (PostgreSQL)" in prompt
        assert "db_query" in prompt
        assert "db_schema" in prompt
        assert "db_explain" in prompt
        assert "Database Best Practices" in prompt

    def test_no_postgres_section_when_disabled(self):
        with patch("koda.services.tool_prompt.POSTGRES_ENABLED", False):
            prompt = build_agent_tools_prompt()
        assert "### Database (PostgreSQL)" not in prompt
        assert "db_query" not in prompt

    def test_prompt_lists_enabled_tool_subset_when_policy_is_present(self):
        with (
            patch("koda.services.tool_prompt.AGENT_TOOL_POLICY", {"allowed_tool_ids": ["web_search", "fetch_url"]}),
            patch("koda.services.tool_prompt.AGENT_ALLOWED_TOOLS", set()),
        ):
            prompt = build_agent_tools_prompt()

        assert "## Enabled Tool Subset" in prompt
        assert "`web_search`" in prompt
        assert "`fetch_url`" in prompt
