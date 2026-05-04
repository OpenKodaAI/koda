"""Tests for tool_prompt: dynamic system prompt generation."""

from unittest.mock import patch

from koda.services.tool_prompt import build_agent_tools_prompt


class TestBuildBotToolsPrompt:
    def test_default_prompt_has_secure_read_subset_only(self):
        prompt = build_agent_tools_prompt()
        assert "<agent_tools>" in prompt
        assert "</agent_tools>" in prompt
        assert "job_list" in prompt
        assert "web_search" in prompt
        assert "fetch_url" in prompt
        assert "agent_get_status" in prompt
        assert "job_create" not in prompt
        assert "agent_set_workdir" not in prompt

    def test_default_prompt_has_protocol(self):
        prompt = build_agent_tools_prompt()
        assert "<agent_cmd" in prompt
        assert "tool_result" in prompt
        assert "do NOT tell the user to type" in prompt.lower() or "Do NOT instruct" in prompt

    def test_prompt_never_lists_native_external_saas_tools(self):
        prompt = build_agent_tools_prompt()
        assert "`gws`" not in prompt
        assert "`jira`" not in prompt
        assert "`confluence`" not in prompt
        assert "Third-party SaaS/cloud systems are not native Koda tools" in prompt

    def test_browser_section_when_enabled(self):
        with patch("koda.services.tool_prompt.BROWSER_FEATURES_ENABLED", True):
            prompt = build_agent_tools_prompt()
        assert "### Browser Automation" in prompt
        assert "browser_navigate" in prompt
        assert "browser_screenshot" in prompt
        assert "browser_click" not in prompt
        assert "browser_forward" in prompt
        assert "browser_hover" not in prompt
        assert "browser_press_key" not in prompt
        assert "Browser Workflow Best Practices" in prompt

    def test_no_browser_section_when_disabled(self):
        with patch("koda.services.tool_prompt.BROWSER_FEATURES_ENABLED", False):
            prompt = build_agent_tools_prompt()
        assert "### Browser Automation" not in prompt
        assert "browser_navigate" not in prompt

    def test_prompt_declares_database_access_is_mcp_only(self):
        prompt = build_agent_tools_prompt()
        assert "Database access is MCP-only" in prompt
        assert "db_query" not in prompt
        assert "sqlite_query" not in prompt
        assert "mongo_query" not in prompt
        assert "mysql_query" not in prompt
        assert "redis_query" not in prompt

    def test_prompt_lists_enabled_tool_subset_when_policy_is_present(self):
        with (
            patch("koda.services.tool_prompt.AGENT_TOOL_POLICY", {"allowed_tool_ids": ["web_search", "fetch_url"]}),
            patch("koda.services.tool_prompt.AGENT_ALLOWED_TOOLS", set()),
        ):
            prompt = build_agent_tools_prompt()

        assert "## Enabled Tool Subset" in prompt
        assert "`web_search`" in prompt
        assert "`fetch_url`" in prompt

    def test_fileops_section_when_enabled(self):
        with patch("koda.services.tool_prompt.FILEOPS_ENABLED", True):
            prompt = build_agent_tools_prompt()
        assert "### File Operations" in prompt
        assert "file_read" not in prompt
        assert "file_write" not in prompt

    def test_no_fileops_section_when_disabled(self):
        with patch("koda.services.tool_prompt.FILEOPS_ENABLED", False):
            prompt = build_agent_tools_prompt()
        assert "### File Operations" not in prompt

    def test_prompt_filters_out_disabled_tools_when_policy_is_present(self):
        with (
            patch("koda.services.tool_prompt.AGENT_TOOL_POLICY", {"allowed_tool_ids": ["web_search", "fetch_url"]}),
            patch("koda.services.tool_prompt.AGENT_ALLOWED_TOOLS", set()),
        ):
            prompt = build_agent_tools_prompt()

        assert "cron_list" not in prompt
        assert "cron_add" not in prompt
        assert "browser_navigate" not in prompt
        assert "db_query" not in prompt
        assert "script_save" not in prompt
        assert "cache_clear" not in prompt

    def test_execution_policy_expands_prompt_allowlist_beyond_secure_default(self):
        prompt = build_agent_tools_prompt(
            execution_policy={
                "version": 1,
                "rules": [
                    {
                        "id": "allow-job-write",
                        "decision": "require_approval",
                        "selectors": {"tool_id": ["job_create"]},
                    }
                ],
            }
        )

        assert "## Enabled Tool Subset" in prompt
        assert "`job_create`" in prompt

    def test_prompt_does_not_offer_native_database_sections(self):
        prompt = build_agent_tools_prompt()
        assert "### Database (PostgreSQL)" not in prompt
        assert "### MongoDB" not in prompt
        assert "### Redis" not in prompt
        assert "### SQLite" not in prompt
        assert "### MySQL" not in prompt

    def test_prompt_surfaces_integration_grants_when_present(self):
        with patch(
            "koda.services.tool_prompt.AGENT_RESOURCE_ACCESS_POLICY",
            {
                "integration_grants": {
                    "mcp:atlassian": {
                        "allow_actions": ["search_issues"],
                    }
                }
            },
        ):
            prompt = build_agent_tools_prompt()

        assert "## Integration Grants" in prompt
        assert "`mcp:atlassian`" in prompt
        assert "`search_issues`" in prompt
