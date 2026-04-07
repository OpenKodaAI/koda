"""Tests for MCP governance integration in tool_prompt and queue_manager."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from koda.services.mcp_bridge import (
    classify_mcp_tool_rw,
    is_mcp_tool,
    mcp_tool_id,
    resolve_mcp_tool_policy,
)
from koda.services.mcp_client import McpToolAnnotations, McpToolDefinition

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_instance(
    server_key: str,
    agent_id: str,
    tools: list[McpToolDefinition] | None = None,
    started: bool = True,
) -> MagicMock:
    inst = MagicMock()
    inst.server_key = server_key
    inst.agent_id = agent_id
    inst.started = started
    inst.cached_tools = tools or []
    return inst


# ---------------------------------------------------------------------------
# Task 1 – prompt generation tests
# ---------------------------------------------------------------------------


class TestMcpPromptGeneration:
    def test_mcp_prompt_generation(self):
        """Mock mcp_server_manager with instances, verify prompt contains tool docs."""
        from koda.services.mcp_manager import mcp_server_manager
        from koda.services.tool_prompt import _build_mcp_tools_prompt

        tools = [
            McpToolDefinition(
                name="create_issue",
                description="Create a GitHub issue",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Issue title"},
                        "body": {"type": "string", "description": "Issue body"},
                    },
                    "required": ["title"],
                },
            ),
            McpToolDefinition(
                name="list_repos",
                description="List repositories",
                input_schema={},
            ),
        ]
        instance = _make_instance("github", "agent-1", tools=tools)
        instances = {"agent-1:github": instance}

        original = mcp_server_manager._instances
        mcp_server_manager._instances = instances
        try:
            result = _build_mcp_tools_prompt("agent-1")
        finally:
            mcp_server_manager._instances = original

        assert "## MCP Server Tools" in result
        assert "### MCP Server: github" in result
        assert "mcp_github__create_issue" in result
        assert "Create a GitHub issue" in result
        assert "mcp_github__list_repos" in result
        assert "List repositories" in result

    def test_mcp_prompt_empty_when_no_instances(self):
        """Returns empty when no MCP instances match the agent."""
        from koda.services.mcp_manager import mcp_server_manager
        from koda.services.tool_prompt import _build_mcp_tools_prompt

        original = mcp_server_manager._instances
        mcp_server_manager._instances = {}
        try:
            result = _build_mcp_tools_prompt("agent-1")
        finally:
            mcp_server_manager._instances = original

        assert result == ""

    def test_mcp_prompt_empty_when_not_started(self):
        """Returns empty when instances exist but are not started."""
        from koda.services.mcp_manager import mcp_server_manager
        from koda.services.tool_prompt import _build_mcp_tools_prompt

        tools = [McpToolDefinition(name="some_tool", description="A tool")]
        instance = _make_instance("github", "agent-1", tools=tools, started=False)
        instances = {"agent-1:github": instance}

        original = mcp_server_manager._instances
        mcp_server_manager._instances = instances
        try:
            result = _build_mcp_tools_prompt("agent-1")
        finally:
            mcp_server_manager._instances = original

        assert result == ""

    def test_mcp_prompt_includes_parameters(self):
        """Verify tool parameters are documented in the prompt."""
        from koda.services.mcp_manager import mcp_server_manager
        from koda.services.tool_prompt import _build_mcp_tools_prompt

        tools = [
            McpToolDefinition(
                name="query_data",
                description="Query data from database",
                input_schema={
                    "type": "object",
                    "properties": {
                        "sql": {"type": "string", "description": "SQL query"},
                        "limit": {"type": "integer", "description": "Max rows"},
                    },
                    "required": ["sql"],
                },
            ),
        ]
        instance = _make_instance("db", "agent-1", tools=tools)
        instances = {"agent-1:db": instance}

        original = mcp_server_manager._instances
        mcp_server_manager._instances = instances
        try:
            result = _build_mcp_tools_prompt("agent-1")
        finally:
            mcp_server_manager._instances = original

        assert "Parameters:" in result
        assert "`sql` (string (required)): SQL query" in result
        assert "`limit` (integer): Max rows" in result

    def test_mcp_prompt_skips_other_agents(self):
        """Only includes instances for the requested agent_id."""
        from koda.services.mcp_manager import mcp_server_manager
        from koda.services.tool_prompt import _build_mcp_tools_prompt

        tools_a = [McpToolDefinition(name="tool_a", description="Agent A tool")]
        tools_b = [McpToolDefinition(name="tool_b", description="Agent B tool")]
        instances = {
            "agent-a:server1": _make_instance("server1", "agent-a", tools=tools_a),
            "agent-b:server2": _make_instance("server2", "agent-b", tools=tools_b),
        }

        original = mcp_server_manager._instances
        mcp_server_manager._instances = instances
        try:
            result = _build_mcp_tools_prompt("agent-a")
        finally:
            mcp_server_manager._instances = original

        assert "tool_a" in result
        assert "tool_b" not in result

    def test_build_agent_tools_prompt_includes_mcp_when_enabled(self):
        """Integration test: MCP section appears in full prompt when MCP_ENABLED."""
        from koda.services.mcp_manager import mcp_server_manager
        from koda.services.tool_prompt import build_agent_tools_prompt

        tools = [McpToolDefinition(name="ping", description="Ping server")]
        instance = _make_instance("infra", "agent-1", tools=tools)
        instances = {"agent-1:infra": instance}

        original = mcp_server_manager._instances
        mcp_server_manager._instances = instances
        try:
            with patch("koda.services.tool_prompt.MCP_ENABLED", True):
                prompt = build_agent_tools_prompt(agent_id="agent-1")
        finally:
            mcp_server_manager._instances = original

        assert "## MCP Server Tools" in prompt
        assert "mcp_infra__ping" in prompt

    def test_build_agent_tools_prompt_no_mcp_when_disabled(self):
        """MCP section does not appear when MCP_ENABLED is False."""
        from koda.services.tool_prompt import build_agent_tools_prompt

        with patch("koda.services.tool_prompt.MCP_ENABLED", False):
            prompt = build_agent_tools_prompt(agent_id="agent-1")

        assert "## MCP Server Tools" not in prompt

    def test_mcp_prompt_omits_blocked_tools(self):
        from koda.services.mcp_manager import mcp_server_manager
        from koda.services.tool_prompt import _build_mcp_tools_prompt

        tools = [
            McpToolDefinition(name="create_issue", description="Create a GitHub issue"),
            McpToolDefinition(name="list_repos", description="List repositories"),
        ]
        instance = _make_instance("github", "agent-1", tools=tools)
        instances = {"agent-1:github": instance}
        manager = MagicMock()
        manager.list_mcp_tool_policies.return_value = [
            {"tool_name": "create_issue", "policy": "blocked"},
            {"tool_name": "list_repos", "policy": "always_ask"},
        ]

        original = mcp_server_manager._instances
        mcp_server_manager._instances = instances
        try:
            with patch("koda.control_plane.manager.get_control_plane_manager", return_value=manager):
                result = _build_mcp_tools_prompt("agent-1")
        finally:
            mcp_server_manager._instances = original

        assert "mcp_github__create_issue" not in result
        assert "mcp_github__list_repos" in result


# ---------------------------------------------------------------------------
# Task 2 – policy classification tests
# ---------------------------------------------------------------------------


class TestMcpPolicyClassification:
    def test_classify_blocked_policy(self):
        """Verify blocked policy is returned for explicitly blocked tools."""
        policies = {"dangerous_tool": "blocked"}
        result = resolve_mcp_tool_policy(policies, "dangerous_tool", None)
        assert result == "blocked"

    def test_classify_always_ask_policy(self):
        """Verify always_ask forces approval."""
        policies = {"sensitive_tool": "always_ask"}
        result = resolve_mcp_tool_policy(policies, "sensitive_tool", None)
        assert result == "always_ask"

    def test_classify_always_allow_policy(self):
        """Verify always_allow skips approval."""
        policies = {"safe_tool": "always_allow"}
        result = resolve_mcp_tool_policy(policies, "safe_tool", None)
        assert result == "always_allow"

    def test_classify_auto_uses_annotations(self):
        """Verify auto falls through to annotation classification."""
        policies = {"my_tool": "auto"}
        result = resolve_mcp_tool_policy(policies, "my_tool", None)
        assert result == "auto"

        # With read-only annotation, auto still returns "auto" (the caller
        # applies classify_mcp_tool_rw separately)
        annotations = McpToolAnnotations(read_only_hint=True)
        result = resolve_mcp_tool_policy(policies, "my_tool", annotations)
        assert result == "auto"

    def test_classify_auto_default_when_no_policy(self):
        """Tools not in the policy dict get auto by default."""
        policies = {}
        result = resolve_mcp_tool_policy(policies, "unknown_tool", None)
        assert result == "auto"

    def test_classify_rw_read_only_hint(self):
        """read_only_hint=True makes tool read-only."""
        annotations = McpToolAnnotations(read_only_hint=True)
        assert classify_mcp_tool_rw(annotations) is False

    def test_classify_rw_no_annotations(self):
        """No annotations means conservative write classification."""
        assert classify_mcp_tool_rw(None) is True

    def test_classify_rw_write_tool(self):
        """Without read_only_hint, tool is classified as write."""
        annotations = McpToolAnnotations(destructive_hint=True)
        assert classify_mcp_tool_rw(annotations) is True

    def test_is_mcp_tool_true(self):
        tid = mcp_tool_id("github", "create_issue")
        assert is_mcp_tool(tid) is True

    def test_is_mcp_tool_false(self):
        assert is_mcp_tool("web_search") is False
        assert is_mcp_tool("file_read") is False
