"""Tests for tool_dispatcher: parsing, execution, security."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.agent_contract import resolve_action_envelope, resolve_integration_action
from koda.services import tool_dispatcher as tool_dispatcher_module
from koda.services.tool_dispatcher import (
    AgentToolCall,
    AgentToolResult,
    PolicyEvaluation,
    ToolContext,
    _is_write_tool,
    execute_tool,
    format_tool_results,
    parse_agent_commands,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(**overrides) -> ToolContext:
    defaults = dict(
        user_id=111,
        chat_id=111,
        work_dir="/tmp",
        user_data={
            "work_dir": "/tmp",
            "model": "claude-sonnet-4-6",
            "session_id": "sess-1",
            "total_cost": 0.0,
            "query_count": 5,
        },
        agent=AsyncMock(),
        agent_mode="autonomous",
    )
    defaults.update(overrides)
    return ToolContext(**defaults)


@pytest.fixture(autouse=True)
def _reset_tool_rate_windows():
    tool_dispatcher_module._tool_rate_windows.clear()
    yield
    tool_dispatcher_module._tool_rate_windows.clear()


@pytest.fixture(autouse=True)
def _compat_resource_grants():
    with patch(
        "koda.services.tool_dispatcher.AGENT_RESOURCE_ACCESS_POLICY",
        {
            "integration_grants": {
                "scheduler": {"allow_actions": ["*"]},
                "web": {"allow_actions": ["*"]},
                "browser": {"allow_actions": ["*"]},
                "agent_runtime": {"allow_actions": ["*"]},
            }
        },
    ):
        yield


@pytest.fixture(autouse=True)
def _dispatcher_policy_stub(request: pytest.FixtureRequest):
    if request.node.get_closest_marker("real_policy_gate"):
        yield
        return

    def _allow_policy(tool_id: str, params: dict | None = None, **kwargs):
        envelope, _ = resolve_action_envelope(
            tool_id,
            params or {},
            kwargs.get("resource_access_policy"),
        )
        return PolicyEvaluation(
            decision="allow",
            reason_code="test_stub_allow",
            reason="Dispatcher unit tests stub the central policy gate unless explicitly requested.",
            envelope=envelope,
        )

    with patch("koda.services.tool_dispatcher.evaluate_execution_policy", side_effect=_allow_policy):
        yield


# ---------------------------------------------------------------------------
# Parsing tests
# ---------------------------------------------------------------------------


class TestParseAgentCommands:
    def test_single_tag(self):
        text = 'Hello <agent_cmd tool="cron_list">{}</agent_cmd> world'
        calls, clean = parse_agent_commands(text)
        assert len(calls) == 1
        assert calls[0].tool == "cron_list"
        assert calls[0].params == {}
        assert "<agent_cmd" not in clean
        assert "Hello" in clean
        assert "world" in clean

    def test_multiple_tags(self):
        text = (
            '<agent_cmd tool="cron_list">{}</agent_cmd>\n'
            '<agent_cmd tool="web_search">{"query": "python 3.14"}</agent_cmd>'
        )
        calls, clean = parse_agent_commands(text)
        assert len(calls) == 2
        assert calls[0].tool == "cron_list"
        assert calls[1].tool == "web_search"
        assert calls[1].params == {"query": "python 3.14"}
        assert "<agent_cmd" not in clean

    def test_no_tags(self):
        text = "Just a normal response with no commands."
        calls, clean = parse_agent_commands(text)
        assert calls == []
        assert clean == text

    def test_invalid_json_skipped(self):
        text = '<agent_cmd tool="cron_add">{invalid json}</agent_cmd> rest'
        calls, clean = parse_agent_commands(text)
        assert calls == []
        assert "rest" in clean

    def test_multiline_json(self):
        text = '<agent_cmd tool="cron_add">{\n"expression": "0 3 * * *",\n"command": "echo hi"\n}</agent_cmd>'
        calls, clean = parse_agent_commands(text)
        assert len(calls) == 1
        assert calls[0].params["expression"] == "0 3 * * *"

    def test_empty_body(self):
        text = '<agent_cmd tool="agent_get_status"></agent_cmd>'
        calls, clean = parse_agent_commands(text)
        assert len(calls) == 1
        assert calls[0].params == {}

    def test_clean_text_collapses_whitespace(self):
        text = 'Before\n\n\n<agent_cmd tool="cron_list">{}</agent_cmd>\n\n\nAfter'
        _, clean = parse_agent_commands(text)
        assert "\n\n\n" not in clean

    def test_action_plan_removed_from_clean_text(self):
        text = '<action_plan><summary>plan</summary></action_plan><agent_cmd tool="cron_list">{}</agent_cmd>After'
        _, clean = parse_agent_commands(text)
        assert "action_plan" not in clean
        assert "After" in clean


# ---------------------------------------------------------------------------
# Execution tests — web
# ---------------------------------------------------------------------------


class TestWebTools:
    @pytest.mark.asyncio
    async def test_web_search(self):
        ctx = _make_ctx()
        call = AgentToolCall(tool="web_search", params={"query": "python"}, raw_match="")
        with patch("koda.services.http_client.search_web", new_callable=AsyncMock, return_value="• Result 1"):
            result = await execute_tool(call, ctx)
        assert result.success
        assert "Result 1" in result.output

    @pytest.mark.asyncio
    async def test_web_search_missing_query(self):
        ctx = _make_ctx()
        call = AgentToolCall(tool="web_search", params={}, raw_match="")
        result = await execute_tool(call, ctx)
        assert not result.success
        assert "Missing" in result.output

    @pytest.mark.asyncio
    async def test_fetch_url(self):
        ctx = _make_ctx()
        call = AgentToolCall(tool="fetch_url", params={"url": "https://example.com"}, raw_match="")
        with patch("koda.services.http_client.fetch_url", new_callable=AsyncMock, return_value="<html>..."):
            result = await execute_tool(call, ctx)
        assert result.success

    @pytest.mark.asyncio
    async def test_fetch_url_error(self):
        ctx = _make_ctx()
        call = AgentToolCall(tool="fetch_url", params={"url": "https://bad.com"}, raw_match="")
        with patch("koda.services.http_client.fetch_url", new_callable=AsyncMock, return_value="Error: timeout"):
            result = await execute_tool(call, ctx)
        assert not result.success

    @pytest.mark.asyncio
    async def test_http_request(self):
        ctx = _make_ctx()
        call = AgentToolCall(
            tool="http_request",
            params={"method": "GET", "url": "https://api.example.com/data"},
            raw_match="",
        )
        with patch(
            "koda.services.http_client.make_http_request", new_callable=AsyncMock, return_value="HTTP 200 OK\n{}"
        ):
            result = await execute_tool(call, ctx)
        assert result.success


class TestBrowserScope:
    @pytest.mark.asyncio
    async def test_browser_uses_task_scope_when_available(self):
        ctx = _make_ctx(task_id=987)
        call = AgentToolCall(tool="browser_navigate", params={"url": "https://example.com"}, raw_match="")

        with (
            patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", True),
            patch(
                "koda.services.browser_manager.browser_manager.ensure_started",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "koda.services.browser_manager.browser_manager.navigate",
                new=AsyncMock(return_value="Navigated"),
            ) as navigate,
        ):
            result = await execute_tool(call, ctx)

        assert result.success
        navigate.assert_awaited_once_with(987, "https://example.com", allow_private=False)


# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------


class TestFeatureFlags:
    @pytest.mark.asyncio
    async def test_gws_disabled(self):
        ctx = _make_ctx()
        call = AgentToolCall(tool="gws", params={"args": "gmail users.messages.list"}, raw_match="")
        with (
            patch("koda.services.tool_dispatcher.GWS_ENABLED", False),
            patch(
                "koda.services.tool_dispatcher.AGENT_RESOURCE_ACCESS_POLICY",
                {"integration_grants": {"gws": {"allow_actions": ["*"]}}},
            ),
        ):
            result = await execute_tool(call, ctx)
        assert not result.success
        assert "not enabled" in result.output

    @pytest.mark.asyncio
    async def test_jira_disabled(self):
        ctx = _make_ctx()
        call = AgentToolCall(tool="jira", params={"args": "issues search --jql test"}, raw_match="")
        with (
            patch("koda.services.tool_dispatcher.JIRA_ENABLED", False),
            patch(
                "koda.services.tool_dispatcher.AGENT_RESOURCE_ACCESS_POLICY",
                {"integration_grants": {"jira": {"allow_actions": ["*"]}}},
            ),
        ):
            result = await execute_tool(call, ctx)
        assert not result.success
        assert "not enabled" in result.output

    @pytest.mark.asyncio
    async def test_confluence_disabled(self):
        ctx = _make_ctx()
        call = AgentToolCall(tool="confluence", params={"args": "pages search --cql test"}, raw_match="")
        with (
            patch("koda.services.tool_dispatcher.CONFLUENCE_ENABLED", False),
            patch(
                "koda.services.tool_dispatcher.AGENT_RESOURCE_ACCESS_POLICY",
                {"integration_grants": {"confluence": {"allow_actions": ["*"]}}},
            ),
        ):
            result = await execute_tool(call, ctx)
        assert not result.success
        assert "not enabled" in result.output


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------


class TestSecurity:
    @pytest.mark.asyncio
    async def test_set_workdir_sensitive_dir(self):
        ctx = _make_ctx()
        call = AgentToolCall(tool="agent_set_workdir", params={"path": "/etc"}, raw_match="")
        result = await execute_tool(call, ctx)
        assert not result.success
        assert "sensitive" in result.output.lower() or "Blocked" in result.output

    @pytest.mark.asyncio
    async def test_set_workdir_sensitive_subdir(self):
        ctx = _make_ctx()
        call = AgentToolCall(tool="agent_set_workdir", params={"path": "/etc/ssh"}, raw_match="")
        result = await execute_tool(call, ctx)
        assert not result.success

    @pytest.mark.asyncio
    async def test_set_workdir_valid(self, tmp_path):
        ctx = _make_ctx()
        call = AgentToolCall(tool="agent_set_workdir", params={"path": str(tmp_path)}, raw_match="")
        result = await execute_tool(call, ctx)
        assert result.success
        assert str(tmp_path) in result.output
        assert ctx.user_data["work_dir"] == str(tmp_path)

    @pytest.mark.asyncio
    async def test_set_workdir_nonexistent(self):
        ctx = _make_ctx()
        call = AgentToolCall(tool="agent_set_workdir", params={"path": "/nonexistent/path"}, raw_match="")
        result = await execute_tool(call, ctx)
        assert not result.success
        assert "does not exist" in result.output


# ---------------------------------------------------------------------------
# Supervised mode
# ---------------------------------------------------------------------------


class TestSupervisedMode:
    """Supervised mode no longer blocks writes in execute_tool() — approval
    is handled at the agent loop level. These tests verify that execute_tool()
    passes through to the handler regardless of mode."""

    @pytest.mark.asyncio
    async def test_write_passes_through_in_supervised(self):
        """Write tools now execute in supervised mode (approval is in agent loop)."""
        ctx = _make_ctx(agent_mode="supervised")
        call = AgentToolCall(tool="web_search", params={"query": "test"}, raw_match="")
        with patch("koda.services.http_client.search_web", new_callable=AsyncMock, return_value="results"):
            result = await execute_tool(call, ctx)
        assert result.success

    @pytest.mark.asyncio
    async def test_read_allowed_in_supervised(self):
        ctx = _make_ctx(agent_mode="supervised")
        call = AgentToolCall(tool="web_search", params={"query": "test"}, raw_match="")
        with patch("koda.services.http_client.search_web", new_callable=AsyncMock, return_value="results"):
            result = await execute_tool(call, ctx)
        assert result.success

    @pytest.mark.asyncio
    async def test_http_post_passes_through_in_supervised(self):
        """HTTP POST is no longer blocked at execute_tool level."""
        ctx = _make_ctx(agent_mode="supervised")
        call = AgentToolCall(
            tool="http_request",
            params={"method": "POST", "url": "https://api.example.com", "body": "{}"},
            raw_match="",
        )
        with patch("koda.services.http_client.make_http_request", new_callable=AsyncMock, return_value="HTTP 200 OK"):
            result = await execute_tool(call, ctx)
        assert result.success

    @pytest.mark.asyncio
    async def test_http_get_allowed_in_supervised(self):
        ctx = _make_ctx(agent_mode="supervised")
        call = AgentToolCall(
            tool="http_request",
            params={"method": "GET", "url": "https://api.example.com"},
            raw_match="",
        )
        with patch("koda.services.http_client.make_http_request", new_callable=AsyncMock, return_value="HTTP 200 OK"):
            result = await execute_tool(call, ctx)
        assert result.success


# ---------------------------------------------------------------------------
# Unknown tool / timeout
# ---------------------------------------------------------------------------


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_unknown_tool(self):
        ctx = _make_ctx()
        call = AgentToolCall(tool="nonexistent_tool", params={}, raw_match="")
        result = await execute_tool(call, ctx)
        assert not result.success
        assert "Unknown tool" in result.output

    @pytest.mark.asyncio
    async def test_timeout(self):
        ctx = _make_ctx()

        async def _slow_handler(params, ctx):
            await asyncio.sleep(10)
            return AgentToolResult(tool="slow", success=True, output="done")

        call = AgentToolCall(tool="cron_list", params={}, raw_match="")
        with (
            patch("koda.services.tool_dispatcher._TOOL_HANDLERS", {"cron_list": _slow_handler}),
            patch("koda.services.tool_dispatcher.AGENT_TOOL_TIMEOUT", 0.1),
        ):
            result = await execute_tool(call, ctx)
        assert not result.success
        assert "timed out" in result.output

    @pytest.mark.asyncio
    async def test_agent_get_status(self):
        ctx = _make_ctx()
        call = AgentToolCall(tool="agent_get_status", params={}, raw_match="")
        result = await execute_tool(call, ctx)
        assert result.success
        assert "work_dir" in result.output
        assert "model" in result.output


# ---------------------------------------------------------------------------
# Browser tools
# ---------------------------------------------------------------------------


class TestBrowserTools:
    @pytest.mark.asyncio
    async def test_browser_navigate_disabled(self):
        ctx = _make_ctx()
        call = AgentToolCall(tool="browser_navigate", params={"url": "https://example.com"}, raw_match="")
        with patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", False):
            result = await execute_tool(call, ctx)
        assert not result.success
        assert "disabled" in result.output.lower()

    @pytest.mark.asyncio
    async def test_browser_navigate_not_available(self):
        ctx = _make_ctx()
        call = AgentToolCall(tool="browser_navigate", params={"url": "https://example.com"}, raw_match="")
        mock_bm = MagicMock()
        mock_bm.ensure_started = AsyncMock(return_value=False)
        with (
            patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", True),
            patch("koda.services.browser_manager.browser_manager", mock_bm),
        ):
            result = await execute_tool(call, ctx)
        assert not result.success
        assert "not running" in result.output.lower()

    @pytest.mark.asyncio
    async def test_browser_navigate_missing_url(self):
        ctx = _make_ctx()
        call = AgentToolCall(tool="browser_navigate", params={}, raw_match="")
        mock_bm = MagicMock()
        mock_bm.ensure_started = AsyncMock(return_value=True)
        with (
            patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", True),
            patch("koda.services.browser_manager.browser_manager", mock_bm),
        ):
            result = await execute_tool(call, ctx)
        assert not result.success
        assert "Missing" in result.output

    @pytest.mark.asyncio
    async def test_browser_navigate_success(self):
        ctx = _make_ctx()
        call = AgentToolCall(tool="browser_navigate", params={"url": "https://example.com"}, raw_match="")
        mock_bm = MagicMock()
        mock_bm.ensure_started = AsyncMock(return_value=True)
        mock_bm.navigate = AsyncMock(
            return_value="Navigated to: Example\nURL: https://example.com\nLinks: 5 | Forms: 1 | Inputs: 3"
        )
        with (
            patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", True),
            patch("koda.services.browser_manager.browser_manager", mock_bm),
        ):
            result = await execute_tool(call, ctx)
        assert result.success
        assert "Navigated to" in result.output

    @pytest.mark.asyncio
    async def test_browser_click_success(self):
        ctx = _make_ctx()
        call = AgentToolCall(tool="browser_click", params={"selector": "Submit"}, raw_match="")
        mock_bm = MagicMock()
        mock_bm.ensure_started = AsyncMock(return_value=True)
        mock_bm.smart_click = AsyncMock(return_value="Clicked successfully.\nURL: https://example.com\nTitle: Example")
        with (
            patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", True),
            patch("koda.services.browser_manager.browser_manager", mock_bm),
        ):
            result = await execute_tool(call, ctx)
        assert result.success
        assert "Clicked" in result.output

    @pytest.mark.asyncio
    async def test_browser_screenshot_returns_path(self):
        ctx = _make_ctx()
        call = AgentToolCall(tool="browser_screenshot", params={}, raw_match="")
        mock_bm = MagicMock()
        mock_bm.ensure_started = AsyncMock(return_value=True)
        mock_bm.screenshot_to_file = AsyncMock(return_value="/tmp/browser_111_123.png")
        with (
            patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", True),
            patch("koda.services.browser_manager.browser_manager", mock_bm),
        ):
            result = await execute_tool(call, ctx)
        assert result.success
        assert ".png" in result.output

    @pytest.mark.asyncio
    async def test_browser_supervised_read_ok(self):
        ctx = _make_ctx(agent_mode="supervised")
        call = AgentToolCall(tool="browser_screenshot", params={}, raw_match="")
        mock_bm = MagicMock()
        mock_bm.ensure_started = AsyncMock(return_value=True)
        mock_bm.screenshot_to_file = AsyncMock(return_value="/tmp/browser_111_123.png")
        with (
            patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", True),
            patch("koda.services.browser_manager.browser_manager", mock_bm),
        ):
            result = await execute_tool(call, ctx)
        assert result.success

    @pytest.mark.asyncio
    async def test_browser_supervised_write_passes_through(self):
        """Browser write tools now pass through in supervised mode (approval in agent loop)."""
        ctx = _make_ctx(agent_mode="supervised")
        call = AgentToolCall(tool="browser_click", params={"selector": "Submit"}, raw_match="")
        mock_bm = MagicMock()
        mock_bm.ensure_started = AsyncMock(return_value=True)
        mock_bm.smart_click = AsyncMock(return_value="Clicked Submit")
        with (
            patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", True),
            patch("koda.services.browser_manager.browser_manager", mock_bm),
        ):
            result = await execute_tool(call, ctx)
        assert result.success

    @pytest.mark.asyncio
    async def test_browser_scroll_success(self):
        ctx = _make_ctx()
        call = AgentToolCall(tool="browser_scroll", params={"direction": "down", "amount": "300"}, raw_match="")
        mock_bm = MagicMock()
        mock_bm.ensure_started = AsyncMock(return_value=True)
        mock_bm.scroll = AsyncMock(return_value="Scrolled down. Position: y=300/2000")
        with (
            patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", True),
            patch("koda.services.browser_manager.browser_manager", mock_bm),
        ):
            result = await execute_tool(call, ctx)
        assert result.success
        mock_bm.scroll.assert_called_once_with(ctx.user_id, direction="down", amount=300)

    @pytest.mark.asyncio
    async def test_browser_wait_missing_selector(self):
        ctx = _make_ctx()
        call = AgentToolCall(tool="browser_wait", params={}, raw_match="")
        mock_bm = MagicMock()
        mock_bm.ensure_started = AsyncMock(return_value=True)
        with (
            patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", True),
            patch("koda.services.browser_manager.browser_manager", mock_bm),
        ):
            result = await execute_tool(call, ctx)
        assert not result.success
        assert "Missing" in result.output

    @pytest.mark.asyncio
    async def test_browser_select_invalid_index(self):
        ctx = _make_ctx()
        call = AgentToolCall(tool="browser_select", params={"selector": "select#x", "index": "abc"}, raw_match="")
        mock_bm = MagicMock()
        mock_bm.ensure_started = AsyncMock(return_value=True)
        with (
            patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", True),
            patch("koda.services.browser_manager.browser_manager", mock_bm),
        ):
            result = await execute_tool(call, ctx)
        assert not result.success
        assert "integer" in result.output

    @pytest.mark.asyncio
    async def test_browser_cookies_get(self):
        ctx = _make_ctx()
        call = AgentToolCall(tool="browser_cookies", params={"action": "get"}, raw_match="")
        mock_bm = MagicMock()
        mock_bm.ensure_started = AsyncMock(return_value=True)
        mock_bm.get_cookies = AsyncMock(return_value="No cookies found.")
        with (
            patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", True),
            patch("koda.services.browser_manager.browser_manager", mock_bm),
        ):
            result = await execute_tool(call, ctx)
        assert result.success

    @pytest.mark.asyncio
    async def test_browser_cookies_set_missing_name(self):
        ctx = _make_ctx()
        call = AgentToolCall(tool="browser_cookies", params={"action": "set"}, raw_match="")
        mock_bm = MagicMock()
        mock_bm.ensure_started = AsyncMock(return_value=True)
        with (
            patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", True),
            patch("koda.services.browser_manager.browser_manager", mock_bm),
        ):
            result = await execute_tool(call, ctx)
        assert not result.success
        assert "name" in result.output.lower()

    @pytest.mark.asyncio
    async def test_browser_forward_success(self):
        ctx = _make_ctx()
        call = AgentToolCall(tool="browser_forward", params={}, raw_match="")
        mock_bm = MagicMock()
        mock_bm.ensure_started = AsyncMock(return_value=True)
        mock_bm.go_forward = AsyncMock(return_value="Navigated forward.\nURL: https://example.com\nTitle: Example")
        with (
            patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", True),
            patch("koda.services.browser_manager.browser_manager", mock_bm),
        ):
            result = await execute_tool(call, ctx)
        assert result.success
        assert "forward" in result.output.lower()

    @pytest.mark.asyncio
    async def test_browser_hover_success(self):
        ctx = _make_ctx()
        call = AgentToolCall(tool="browser_hover", params={"selector": "Menu"}, raw_match="")
        mock_bm = MagicMock()
        mock_bm.ensure_started = AsyncMock(return_value=True)
        mock_bm.hover = AsyncMock(return_value="Hovered over 'Menu'.\nURL: https://example.com")
        with (
            patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", True),
            patch("koda.services.browser_manager.browser_manager", mock_bm),
        ):
            result = await execute_tool(call, ctx)
        assert result.success
        assert "Hovered" in result.output

    @pytest.mark.asyncio
    async def test_browser_hover_missing_selector(self):
        ctx = _make_ctx()
        call = AgentToolCall(tool="browser_hover", params={}, raw_match="")
        mock_bm = MagicMock()
        mock_bm.ensure_started = AsyncMock(return_value=True)
        with (
            patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", True),
            patch("koda.services.browser_manager.browser_manager", mock_bm),
        ):
            result = await execute_tool(call, ctx)
        assert not result.success
        assert "Missing" in result.output

    @pytest.mark.asyncio
    async def test_browser_press_key_success(self):
        ctx = _make_ctx()
        call = AgentToolCall(tool="browser_press_key", params={"key": "Enter"}, raw_match="")
        mock_bm = MagicMock()
        mock_bm.ensure_started = AsyncMock(return_value=True)
        mock_bm.press_key = AsyncMock(return_value="Pressed key 'Enter'.")
        with (
            patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", True),
            patch("koda.services.browser_manager.browser_manager", mock_bm),
        ):
            result = await execute_tool(call, ctx)
        assert result.success
        assert "Pressed" in result.output

    @pytest.mark.asyncio
    async def test_browser_press_key_missing_key(self):
        ctx = _make_ctx()
        call = AgentToolCall(tool="browser_press_key", params={}, raw_match="")
        mock_bm = MagicMock()
        mock_bm.ensure_started = AsyncMock(return_value=True)
        with (
            patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", True),
            patch("koda.services.browser_manager.browser_manager", mock_bm),
        ):
            result = await execute_tool(call, ctx)
        assert not result.success
        assert "Missing" in result.output

    @pytest.mark.asyncio
    async def test_browser_press_key_with_selector(self):
        ctx = _make_ctx()
        call = AgentToolCall(
            tool="browser_press_key", params={"key": "Escape", "selector": "input#search"}, raw_match=""
        )
        mock_bm = MagicMock()
        mock_bm.ensure_started = AsyncMock(return_value=True)
        mock_bm.press_key = AsyncMock(return_value="Pressed key 'Escape'.")
        with (
            patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", True),
            patch("koda.services.browser_manager.browser_manager", mock_bm),
        ):
            result = await execute_tool(call, ctx)
        assert result.success
        mock_bm.press_key.assert_called_once_with(ctx.user_id, "Escape", selector="input#search")

    @pytest.mark.asyncio
    async def test_browser_hover_supervised_passes_through(self):
        """Browser hover now passes through in supervised mode."""
        ctx = _make_ctx(agent_mode="supervised")
        call = AgentToolCall(tool="browser_hover", params={"selector": "Menu"}, raw_match="")
        mock_bm = MagicMock()
        mock_bm.ensure_started = AsyncMock(return_value=True)
        mock_bm.hover = AsyncMock(return_value="Hovered over Menu")
        with (
            patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", True),
            patch("koda.services.browser_manager.browser_manager", mock_bm),
        ):
            result = await execute_tool(call, ctx)
        assert result.success

    @pytest.mark.asyncio
    async def test_browser_press_key_supervised_passes_through(self):
        """Browser press_key now passes through in supervised mode."""
        ctx = _make_ctx(agent_mode="supervised")
        call = AgentToolCall(tool="browser_press_key", params={"key": "Enter"}, raw_match="")
        mock_bm = MagicMock()
        mock_bm.ensure_started = AsyncMock(return_value=True)
        mock_bm.press_key = AsyncMock(return_value="Pressed Enter")
        with (
            patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", True),
            patch("koda.services.browser_manager.browser_manager", mock_bm),
        ):
            result = await execute_tool(call, ctx)
        assert result.success

    @pytest.mark.asyncio
    async def test_browser_submit_success(self):
        ctx = _make_ctx()
        call = AgentToolCall(tool="browser_submit", params={"selector": "form#login"}, raw_match="")
        mock_bm = MagicMock()
        mock_bm.ensure_started = AsyncMock(return_value=True)
        mock_bm.submit_form = AsyncMock(return_value="Form submitted.\nURL: https://example.com\nTitle: Example")
        with (
            patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", True),
            patch("koda.services.browser_manager.browser_manager", mock_bm),
        ):
            result = await execute_tool(call, ctx)
        assert result.success
        assert "submitted" in result.output.lower()


# ---------------------------------------------------------------------------
# Database tools
# ---------------------------------------------------------------------------


class TestDBTools:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "tool_name, params",
        [
            ("sqlite_query", {"sql": "SELECT 1", "db_path": "/tmp/test.db"}),
            ("sqlite_schema", {"db_path": "/tmp/test.db"}),
            ("mongo_query", {"database": "app", "collection": "users"}),
            ("db_query", {"sql": "SELECT 1"}),
            ("db_schema", {}),
            ("db_explain", {"sql": "SELECT 1"}),
            ("db_switch_env", {"env": "dev"}),
            ("db_execute", {"sql": "DELETE FROM users"}),
            ("db_execute_plan", {"sql": "DELETE FROM users"}),
            ("db_transaction", {"statements": ["DELETE FROM users"]}),
            ("mysql_query", {"sql": "SELECT 1"}),
            ("mysql_schema", {}),
            ("redis_query", {"command": "GET", "args": ["key"]}),
        ],
    )
    async def test_native_database_tools_are_removed(self, tool_name, params):
        ctx = _make_ctx()
        call = AgentToolCall(tool=tool_name, params=params, raw_match="")
        result = await execute_tool(call, ctx)
        assert not result.success
        assert "removed from koda" in result.output.lower()
        assert "mcp" in result.output.lower()
        assert result.metadata["mcp_only"] is True


# ---------------------------------------------------------------------------
# Format results
# ---------------------------------------------------------------------------


class TestFormatResults:
    def test_format_single_result(self):
        results = [AgentToolResult(tool="cron_list", success=True, output="No jobs")]
        formatted = format_tool_results(results)
        assert '<tool_result tool="cron_list" success="true">' in formatted
        assert "No jobs" in formatted

    def test_format_multiple_results(self):
        results = [
            AgentToolResult(tool="cron_list", success=True, output="jobs"),
            AgentToolResult(tool="web_search", success=False, output="Error: timeout"),
        ]
        formatted = format_tool_results(results)
        assert 'tool="cron_list"' in formatted
        assert 'tool="web_search"' in formatted
        assert 'success="false"' in formatted


# ---------------------------------------------------------------------------
# _is_write_tool classification (arg-aware)
# ---------------------------------------------------------------------------


class TestIsWriteTool:
    """Test the _is_write_tool classifier used by the agent loop."""

    def test_jira_search_is_read(self):
        assert _is_write_tool("jira", {"args": "issues search --jql 'project=PROJ'"}) is False

    def test_jira_get_is_read(self):
        assert _is_write_tool("jira", {"args": "issues get --key PROJ-1"}) is False

    def test_jira_comment_get_is_read(self):
        assert _is_write_tool("jira", {"args": "issues comment_get --key PROJ-1 --comment-id 100"}) is False

    def test_jira_transitions_is_read(self):
        assert _is_write_tool("jira", {"args": "issues transitions --key PROJ-1"}) is False

    def test_jira_transition_is_write(self):
        assert _is_write_tool("jira", {"args": "issues transition --key PROJ-1 --transition-id 31"}) is True

    def test_jira_create_is_write(self):
        assert _is_write_tool("jira", {"args": "issues create --project PROJ --summary 'Test'"}) is True

    def test_jira_update_is_write(self):
        assert _is_write_tool("jira", {"args": "issues update --key PROJ-1 --summary 'New'"}) is True

    def test_jira_delete_is_write(self):
        assert _is_write_tool("jira", {"args": "issues delete --key PROJ-1"}) is True

    def test_jira_comment_reply_is_write(self):
        assert _is_write_tool("jira", {"args": "issues comment_reply --key PROJ-1 --comment-id 100 --body hi"}) is True

    def test_jira_comment_edit_is_write(self):
        assert _is_write_tool("jira", {"args": "issues comment_edit --key PROJ-1 --comment-id 100 --body hi"}) is True

    def test_jira_comment_delete_is_write(self):
        assert _is_write_tool("jira", {"args": "issues comment_delete --key PROJ-1 --comment-id 100"}) is True

    def test_confluence_search_is_read(self):
        assert _is_write_tool("confluence", {"args": "pages search --cql 'space=DEV'"}) is False

    def test_confluence_get_is_read(self):
        assert _is_write_tool("confluence", {"args": "pages get --id 123"}) is False

    def test_confluence_create_is_write(self):
        assert _is_write_tool("confluence", {"args": "pages create --space DEV --title 'New'"}) is True

    def test_confluence_update_is_write(self):
        assert _is_write_tool("confluence", {"args": "pages update --id 123 --title 'Updated'"}) is True

    def test_gws_list_is_read(self):
        assert _is_write_tool("gws", {"args": "gmail users.messages.list"}) is False

    def test_gws_get_is_read(self):
        assert _is_write_tool("gws", {"args": "gmail users.messages.get --id abc"}) is False

    def test_gws_action_resolution_for_list(self):
        resolution = resolve_integration_action("gws", {"args": "gmail users.messages.list"})
        assert resolution.action_id == "gmail.list"
        assert resolution.resource_method == "users.messages.list"
        assert resolution.access_level == "read"

    def test_gws_send_is_write(self):
        assert _is_write_tool("gws", {"args": "gmail users.messages.send"}) is True

    def test_gws_create_event_is_write(self):
        assert _is_write_tool("gws", {"args": "gcal events.insert"}) is True

    def test_gws_drive_delete_is_destructive(self):
        resolution = resolve_integration_action("gws", {"args": "drive files.delete"})
        assert resolution.action_id == "drive.delete"
        assert resolution.resource_method == "files.delete"
        assert resolution.access_level == "destructive"

    def test_gws_admin_insert_is_admin(self):
        resolution = resolve_integration_action("gws", {"args": "admin directory.users.insert"})
        assert resolution.action_id == "admin.insert"
        assert resolution.resource_method == "directory.users.insert"
        assert resolution.access_level == "admin"

    def test_cron_add_is_write(self):
        assert _is_write_tool("cron_add", {}) is True

    def test_cron_list_is_read(self):
        assert _is_write_tool("cron_list", {}) is False

    def test_web_search_is_read(self):
        assert _is_write_tool("web_search", {}) is False

    def test_browser_navigate_is_read(self):
        assert _is_write_tool("browser_navigate", {"url": "https://example.com"}) is False

    def test_browser_screenshot_is_read(self):
        assert _is_write_tool("browser_screenshot", {}) is False

    def test_http_request_get_is_read(self):
        assert _is_write_tool("http_request", {"method": "GET", "url": "https://example.com"}) is False

    def test_http_request_post_is_write(self):
        assert _is_write_tool("http_request", {"method": "POST", "url": "https://example.com"}) is True

    def test_browser_cookies_get_is_read(self):
        assert _is_write_tool("browser_cookies", {"action": "get"}) is False

    def test_browser_cookies_set_is_write(self):
        assert _is_write_tool("browser_cookies", {"action": "set", "name": "x", "value": "y"}) is True

    def test_unknown_tool_is_not_write(self):
        """Unknown tools not in any set default to False."""
        assert _is_write_tool("some_unknown_tool", {}) is False

    # Cache/Script tools read/write classification
    def test_script_save_is_write(self):
        assert _is_write_tool("script_save", {}) is True

    def test_script_search_is_read(self):
        assert _is_write_tool("script_search", {}) is False

    def test_script_list_is_read(self):
        assert _is_write_tool("script_list", {}) is False

    def test_script_delete_is_write(self):
        assert _is_write_tool("script_delete", {}) is True

    def test_cache_stats_is_read(self):
        assert _is_write_tool("cache_stats", {}) is False

    def test_cache_clear_is_write(self):
        assert _is_write_tool("cache_clear", {}) is True


# ---------------------------------------------------------------------------
# Script & Cache tool handler tests
# ---------------------------------------------------------------------------


class TestScriptTools:
    @pytest.mark.asyncio
    @patch("koda.services.cache_config.SCRIPT_LIBRARY_ENABLED", False)
    async def test_script_save_disabled(self):
        from koda.services.tool_dispatcher import _handle_script_save

        ctx = _make_ctx()
        result = await _handle_script_save({"title": "t", "content": "c"}, ctx)
        assert not result.success
        assert "disabled" in result.output

    @pytest.mark.asyncio
    async def test_script_save_missing_params(self):
        from koda.services.tool_dispatcher import _handle_script_save

        with patch("koda.services.cache_config.SCRIPT_LIBRARY_ENABLED", True):
            ctx = _make_ctx()
            result = await _handle_script_save({}, ctx)
            assert not result.success
            assert "Missing" in result.output

    @pytest.mark.asyncio
    @patch("koda.services.cache_config.SCRIPT_LIBRARY_ENABLED", False)
    async def test_script_search_disabled(self):
        from koda.services.tool_dispatcher import _handle_script_search

        ctx = _make_ctx()
        result = await _handle_script_search({"query": "test"}, ctx)
        assert not result.success
        assert "disabled" in result.output

    @pytest.mark.asyncio
    async def test_script_search_missing_query(self):
        from koda.services.tool_dispatcher import _handle_script_search

        with patch("koda.services.cache_config.SCRIPT_LIBRARY_ENABLED", True):
            ctx = _make_ctx()
            result = await _handle_script_search({}, ctx)
            assert not result.success
            assert "Missing" in result.output

    @pytest.mark.asyncio
    async def test_script_delete_invalid_id(self):
        from koda.services.tool_dispatcher import _handle_script_delete

        with patch("koda.services.cache_config.SCRIPT_LIBRARY_ENABLED", True):
            ctx = _make_ctx()
            result = await _handle_script_delete({"script_id": "abc"}, ctx)
            assert not result.success
            assert "integer" in result.output

    @pytest.mark.asyncio
    @patch("koda.services.cache_config.SCRIPT_LIBRARY_ENABLED", False)
    async def test_script_list_disabled(self):
        from koda.services.tool_dispatcher import _handle_script_list

        ctx = _make_ctx()
        result = await _handle_script_list({}, ctx)
        assert not result.success
        assert "disabled" in result.output


class TestCacheTools:
    @pytest.mark.asyncio
    @patch("koda.services.cache_config.CACHE_ENABLED", False)
    async def test_cache_stats_disabled(self):
        from koda.services.tool_dispatcher import _handle_cache_stats

        ctx = _make_ctx()
        result = await _handle_cache_stats({}, ctx)
        assert not result.success
        assert "disabled" in result.output

    @pytest.mark.asyncio
    @patch("koda.services.cache_config.CACHE_ENABLED", False)
    async def test_cache_clear_disabled(self):
        from koda.services.tool_dispatcher import _handle_cache_clear

        ctx = _make_ctx()
        result = await _handle_cache_clear({}, ctx)
        assert not result.success
        assert "disabled" in result.output

    @pytest.mark.asyncio
    async def test_cache_clear_success(self):
        from koda.services.tool_dispatcher import _handle_cache_clear

        with (
            patch("koda.services.cache_config.CACHE_ENABLED", True),
            patch("koda.services.cache_manager.get_cache_manager") as mock_get_cm,
        ):
            mock_cm = AsyncMock()
            mock_cm.invalidate_user.return_value = 3
            mock_get_cm.return_value = mock_cm

            ctx = _make_ctx()
            result = await _handle_cache_clear({}, ctx)
            assert result.success
            assert "3" in result.output


class TestJobTools:
    @pytest.mark.asyncio
    async def test_job_list(self):
        from koda.services.tool_dispatcher import _handle_job_list

        with patch(
            "koda.services.scheduled_jobs.list_jobs",
            return_value=[
                {
                    "id": 9,
                    "job_type": "agent_query",
                    "trigger_type": "interval",
                    "status": "validated",
                    "next_run_at": "2026-03-18T12:00:00+00:00",
                    "payload": {"query": "Check status"},
                }
            ],
        ):
            result = await _handle_job_list({}, _make_ctx())
        assert result.success
        assert "#9" in result.output
        assert "agent_query" in result.output

    @pytest.mark.asyncio
    async def test_dry_run_blocks_write_tool(self):
        ctx = _make_ctx(dry_run=True)
        call = AgentToolCall(
            tool="job_create",
            params={
                "job_type": "agent_query",
                "trigger_type": "interval",
                "schedule_expr": "3600",
                "query": "Check health",
            },
            raw_match="",
        )
        result = await execute_tool(call, ctx)
        assert not result.success
        assert "Dry-run blocked" in result.output
        assert result.metadata["dry_run_blocked"] is True

    @pytest.mark.asyncio
    async def test_shell_command_job_create_queues_validation(self):
        from koda.services.tool_dispatcher import _handle_job_create

        with (
            patch("koda.services.scheduled_jobs.create_shell_command_job", return_value=21) as create_job,
            patch(
                "koda.services.scheduled_jobs.queue_validation_run",
                return_value=(34, "Validation queued."),
            ) as queue_validation,
        ):
            result = await _handle_job_create(
                {
                    "job_type": "shell_command",
                    "trigger_type": "cron",
                    "schedule_expr": "*/5 * * * *",
                    "command": "git status",
                },
                _make_ctx(),
            )

        assert result.success
        assert "validation mode" in result.output
        assert "activate automatically" in result.output
        create_job.assert_called_once()
        assert create_job.call_args.kwargs["auto_activate"] is False
        queue_validation.assert_called_once_with(21, user_id=111, activate_on_success=True)

    @pytest.mark.asyncio
    async def test_agent_job_create_auto_activates_after_validation_by_default(self):
        from koda.services.tool_dispatcher import _handle_job_create

        with patch("koda.services.scheduled_jobs.create_agent_query_job", return_value=44) as create_job:
            result = await _handle_job_create(
                {
                    "job_type": "agent_query",
                    "trigger_type": "interval",
                    "schedule_expr": "3600",
                    "query": "Check health",
                },
                _make_ctx(),
            )

        assert result.success
        assert "activate automatically" in result.output
        assert create_job.call_args.kwargs["auto_activate_after_validation"] is True

    @pytest.mark.asyncio
    async def test_agent_job_create_can_require_manual_activation(self):
        from koda.services.tool_dispatcher import _handle_job_create

        with patch("koda.services.scheduled_jobs.create_agent_query_job", return_value=45) as create_job:
            result = await _handle_job_create(
                {
                    "job_type": "agent_query",
                    "trigger_type": "interval",
                    "schedule_expr": "3600",
                    "query": "Check health",
                    "auto_activate_after_validation": False,
                },
                _make_ctx(),
            )

        assert result.success
        assert "Run /jobs activate 45 after validation." in result.output
        assert create_job.call_args.kwargs["auto_activate_after_validation"] is False

    @pytest.mark.asyncio
    async def test_job_validate_does_not_change_activation_state(self):
        from koda.services.tool_dispatcher import _handle_job_validate

        with patch(
            "koda.services.scheduled_jobs.queue_validation_run",
            return_value=(77, "Validation queued."),
        ) as queue_validation:
            result = await _handle_job_validate({"job_id": 21}, _make_ctx())

        assert result.success
        assert "validation_run_id=77" in result.output
        queue_validation.assert_called_once_with(21, user_id=111, activate_on_success=False)

    @pytest.mark.asyncio
    async def test_reminder_job_create_supports_recurring_trigger(self):
        from koda.services.tool_dispatcher import _handle_job_create

        with patch("koda.services.scheduled_jobs.create_reminder_job", return_value=66) as create_job:
            result = await _handle_job_create(
                {
                    "job_type": "reminder",
                    "trigger_type": "interval",
                    "schedule_expr": "7200",
                    "text": "Check the incident timeline",
                    "auto_activate_after_validation": False,
                },
                _make_ctx(),
            )

        assert result.success
        assert "Reminder job #66" in result.output
        assert "Run /jobs activate 66 after validation." in result.output
        assert create_job.call_args.kwargs["trigger_type"] == "interval"
        assert create_job.call_args.kwargs["schedule_expr"] == "7200"
        assert create_job.call_args.kwargs["auto_activate_after_validation"] is False

    @pytest.mark.asyncio
    async def test_job_get_includes_runs_and_events_metadata(self):
        from koda.services.tool_dispatcher import _handle_job_get

        detail = {
            "job": {
                "id": 17,
                "job_type": "agent_query",
                "trigger_type": "interval",
                "status": "active",
                "schedule_expr": "3600",
                "timezone": "UTC",
                "provider_preference": "claude",
                "model_preference": "claude-sonnet-4-6",
                "config_version": 4,
                "notification_policy": {"mode": "summary_complete"},
                "verification_policy": {"mode": "post_write_if_any"},
                "payload": {"query": "Check deploy health"},
            },
            "runs": [{"id": 101, "status": "succeeded"}],
            "events": [{"id": 201, "event_type": "job.updated"}],
        }
        with patch("koda.services.scheduled_jobs.get_job_detail", return_value=detail):
            result = await _handle_job_get({"job_id": 17}, _make_ctx())

        assert result.success
        assert "config_version=4" in result.output
        assert result.metadata["job"]["id"] == 17
        assert result.metadata["runs"][0]["id"] == 101
        assert result.metadata["events"][0]["event_type"] == "job.updated"

    @pytest.mark.asyncio
    async def test_job_update_passes_patch_and_returns_metadata(self):
        from koda.services.tool_dispatcher import _handle_job_update

        with patch(
            "koda.services.scheduled_jobs.update_job",
            return_value={
                "ok": True,
                "message": "Job updated.",
                "config_version": 8,
                "validation_required": True,
                "validation_run_id": 55,
            },
        ) as update_job:
            result = await _handle_job_update(
                {
                    "job_id": 44,
                    "patch": {"schedule_expr": "10800", "trigger_type": "interval"},
                    "expected_config_version": 7,
                    "reason": "reduce cadence",
                },
                _make_ctx(),
            )

        assert result.success
        assert result.output == "Job updated."
        assert result.metadata["config_version"] == 8
        update_job.assert_called_once_with(
            44,
            user_id=111,
            patch={"schedule_expr": "10800", "trigger_type": "interval"},
            expected_config_version=7,
            actor_type="agent",
            actor_id="111",
            source="agent_tool",
            reason="reduce cadence",
            evidence=None,
        )

    @pytest.mark.asyncio
    async def test_job_create_rejects_invalid_workdir(self):
        from koda.services.tool_dispatcher import _handle_job_create

        result = await _handle_job_create(
            {
                "job_type": "agent_query",
                "trigger_type": "interval",
                "schedule_expr": "3600",
                "query": "Check health",
                "work_dir": "/etc",
            },
            _make_ctx(),
        )

        assert not result.success
        assert "sensitive" in result.output.lower()


@pytest.mark.asyncio
@pytest.mark.real_policy_gate
async def test_execute_tool_blocks_disallowed_tool_by_policy():
    ctx = _make_ctx()
    call = AgentToolCall(
        tool="cron_add",
        params={"expression": "0 3 * * *", "command": "echo backup"},
        raw_match="",
    )

    with patch("koda.services.execution_policy.AGENT_TOOL_POLICY", {"allowed_tool_ids": ["web_search"]}):
        result = await execute_tool(call, ctx)

    assert result.success is False
    assert result.metadata["policy_blocked"] is True
    assert "secure default tool subset" in result.output.lower()


@pytest.mark.asyncio
@pytest.mark.real_policy_gate
async def test_execute_tool_blocks_integration_action_outside_grant():
    ctx = _make_ctx()
    call = AgentToolCall(
        tool="gws",
        params={"args": "gmail users.messages.send"},
        raw_match="",
    )

    with (
        patch(
            "koda.services.tool_dispatcher.AGENT_RESOURCE_ACCESS_POLICY",
            {
                "integration_grants": {
                    "gws": {
                        "allow_actions": ["gmail.list"],
                    }
                }
            },
        ),
        patch(
            "koda.services.execution_policy.AGENT_EXECUTION_POLICY",
            {
                "version": 1,
                "rules": [
                    {
                        "id": "allow-gws",
                        "decision": "allow",
                        "selectors": {"tool_id": ["gws"]},
                    }
                ],
            },
        ),
    ):
        result = await execute_tool(call, ctx)

    assert result.success is False
    assert result.metadata["policy_blocked"] is True
    assert result.metadata["integration_id"] == "gws"
    assert result.metadata["action_id"] == "gmail.send"
    assert result.metadata["resource_method"] == "users.messages.send"
    assert "outside the granted scope" in result.output.lower()


@pytest.mark.asyncio
@pytest.mark.real_policy_gate
async def test_execute_tool_allows_gws_list_under_grant():
    ctx = _make_ctx()
    call = AgentToolCall(
        tool="gws",
        params={"args": "gmail users.messages.list"},
        raw_match="",
    )

    mock_cli_result = MagicMock(
        text='Exit 0:\n{"messages": []}',
        binary="gws",
        args=["gmail", "users.messages.list"],
        exit_code=0,
        timed_out=False,
        truncated=False,
    )

    with (
        patch("koda.services.tool_dispatcher.GWS_ENABLED", True),
        patch(
            "koda.services.tool_dispatcher.AGENT_RESOURCE_ACCESS_POLICY",
            {
                "integration_grants": {
                    "gws": {
                        "allow_actions": ["gmail.list"],
                    }
                }
            },
        ),
        patch(
            "koda.services.execution_policy.AGENT_EXECUTION_POLICY",
            {
                "version": 1,
                "rules": [
                    {
                        "id": "allow-gws",
                        "decision": "allow",
                        "selectors": {"tool_id": ["gws"]},
                    }
                ],
            },
        ),
        patch(
            "koda.services.cli_runner.run_cli_command_detailed", new_callable=AsyncMock, return_value=mock_cli_result
        ),
    ):
        result = await execute_tool(call, ctx)

    assert result.success is True
    assert result.metadata["integration_id"] == "gws"
    assert result.metadata["action_id"] == "gmail.list"
    assert result.metadata["resource_method"] == "users.messages.list"


@pytest.mark.asyncio
@pytest.mark.real_policy_gate
async def test_execute_tool_blocks_gws_drive_delete_outside_grant():
    ctx = _make_ctx()
    call = AgentToolCall(
        tool="gws",
        params={"args": "drive files.delete"},
        raw_match="",
    )

    with (
        patch(
            "koda.services.tool_dispatcher.AGENT_RESOURCE_ACCESS_POLICY",
            {
                "integration_grants": {
                    "gws": {
                        "allow_actions": ["gmail.list"],
                    }
                }
            },
        ),
        patch(
            "koda.services.execution_policy.AGENT_EXECUTION_POLICY",
            {
                "version": 1,
                "rules": [
                    {
                        "id": "allow-gws",
                        "decision": "allow",
                        "selectors": {"tool_id": ["gws"]},
                    }
                ],
            },
        ),
    ):
        result = await execute_tool(call, ctx)

    assert result.success is False
    assert result.metadata["policy_blocked"] is True
    assert result.metadata["action_id"] == "drive.delete"
    assert result.metadata["resource_method"] == "files.delete"


@pytest.mark.asyncio
@pytest.mark.real_policy_gate
async def test_execute_tool_blocks_gws_admin_outside_grant():
    ctx = _make_ctx()
    call = AgentToolCall(
        tool="gws",
        params={"args": "admin directory.users.insert"},
        raw_match="",
    )

    with (
        patch(
            "koda.services.tool_dispatcher.AGENT_RESOURCE_ACCESS_POLICY",
            {
                "integration_grants": {
                    "gws": {
                        "allow_actions": ["gmail.list"],
                    }
                }
            },
        ),
        patch(
            "koda.services.execution_policy.AGENT_EXECUTION_POLICY",
            {
                "version": 1,
                "rules": [
                    {
                        "id": "allow-gws",
                        "decision": "allow",
                        "selectors": {"tool_id": ["gws"]},
                    }
                ],
            },
        ),
    ):
        result = await execute_tool(call, ctx)

    assert result.success is False
    assert result.metadata["policy_blocked"] is True
    assert result.metadata["action_id"] == "admin.insert"
    assert result.metadata["resource_method"] == "directory.users.insert"


@pytest.mark.asyncio
@pytest.mark.real_policy_gate
async def test_execute_tool_blocks_private_network_without_explicit_grant():
    ctx = _make_ctx()
    call = AgentToolCall(
        tool="browser_navigate",
        params={"url": "http://127.0.0.1:3000"},
        raw_match="",
    )

    with patch(
        "koda.services.tool_dispatcher.AGENT_RESOURCE_ACCESS_POLICY",
        {
            "integration_grants": {
                "browser": {
                    "allow_actions": ["navigate"],
                }
            }
        },
    ):
        result = await execute_tool(call, ctx)

    assert result.success is False
    assert result.metadata["policy_blocked"] is True
    assert result.metadata["grant_reason"] == "private_network_not_granted"


@pytest.mark.asyncio
@pytest.mark.real_policy_gate
async def test_execute_tool_blocks_browser_action_when_session_domain_unknown():
    ctx = _make_ctx()
    call = AgentToolCall(
        tool="browser_click",
        params={"selector": "Submit"},
        raw_match="",
    )

    with (
        patch(
            "koda.services.tool_dispatcher.AGENT_RESOURCE_ACCESS_POLICY",
            {
                "integration_grants": {
                    "browser": {
                        "allow_actions": ["click"],
                        "allowed_domains": ["example.com"],
                    }
                }
            },
        ),
        patch(
            "koda.services.execution_policy.AGENT_EXECUTION_POLICY",
            {
                "version": 1,
                "rules": [
                    {
                        "id": "allow-browser-click",
                        "decision": "allow",
                        "selectors": {"tool_id": ["browser_click"]},
                    }
                ],
            },
        ),
        patch("koda.services.browser_manager.browser_manager.get_session_snapshot", return_value=None),
    ):
        result = await execute_tool(call, ctx)

    assert result.success is False
    assert result.metadata["policy_blocked"] is True
    assert result.metadata["grant_reason"] == "domain_unknown"


@pytest.mark.asyncio
@pytest.mark.real_policy_gate
async def test_execute_tool_uses_browser_session_domain_for_grants():
    ctx = _make_ctx()
    call = AgentToolCall(
        tool="browser_click",
        params={"selector": "Submit"},
        raw_match="",
    )
    mock_bm = MagicMock()
    mock_bm.ensure_started = AsyncMock(return_value=True)
    mock_bm.smart_click = AsyncMock(return_value="Clicked successfully.")
    mock_bm.get_session_snapshot.return_value = {
        "url": "https://example.com/dashboard",
        "domain": "example.com",
    }

    with (
        patch(
            "koda.services.tool_dispatcher.AGENT_RESOURCE_ACCESS_POLICY",
            {
                "integration_grants": {
                    "browser": {
                        "allow_actions": ["click"],
                        "allowed_domains": ["example.com"],
                    }
                }
            },
        ),
        patch(
            "koda.services.execution_policy.AGENT_EXECUTION_POLICY",
            {
                "version": 1,
                "rules": [
                    {
                        "id": "allow-browser-click",
                        "decision": "allow",
                        "selectors": {"tool_id": ["browser_click"]},
                    }
                ],
            },
        ),
        patch("koda.services.browser_manager.browser_manager", mock_bm),
    ):
        result = await execute_tool(call, ctx)

    assert result.success is False
    assert result.metadata["approval_required"] is True
    assert result.metadata["grant_decision"] == "allowed"
    mock_bm.smart_click.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.real_policy_gate
async def test_execute_tool_passes_allow_private_to_fetch_url():
    ctx = _make_ctx()
    call = AgentToolCall(
        tool="fetch_url",
        params={"url": "http://127.0.0.1:3000"},
        raw_match="",
    )

    with (
        patch(
            "koda.services.tool_dispatcher.AGENT_RESOURCE_ACCESS_POLICY",
            {
                "integration_grants": {
                    "web": {
                        "allow_actions": ["fetch_url"],
                        "allow_private_network": True,
                    }
                }
            },
        ),
        patch("koda.services.http_client.fetch_url", new_callable=AsyncMock, return_value="ok") as mock_fetch,
    ):
        result = await execute_tool(call, ctx)

    assert result.success is True
    mock_fetch.assert_awaited_once_with("http://127.0.0.1:3000", allow_private=True)


@pytest.mark.asyncio
@pytest.mark.real_policy_gate
async def test_execute_tool_blocks_native_database_tools_even_with_grants():
    ctx = _make_ctx()
    call = AgentToolCall(tool="db_query", params={"sql": "SELECT 1"}, raw_match="")

    with patch(
        "koda.services.tool_dispatcher.AGENT_RESOURCE_ACCESS_POLICY",
        {"integration_grants": {"postgres": {"allow_actions": ["query"]}}},
    ):
        result = await execute_tool(call, ctx)

    assert result.success is False
    assert "mcp" in result.output.lower()


@pytest.mark.asyncio
@pytest.mark.real_policy_gate
async def test_execute_tool_blocks_mcp_tool_via_central_gate_without_queue_manager_injection():
    ctx = _make_ctx()
    call = AgentToolCall(tool="mcp_github__create_issue", params={"title": "Bug"}, raw_match="")
    handler = AsyncMock(return_value=AgentToolResult(tool=call.tool, success=True, output="created"))
    manager = MagicMock()
    manager.list_mcp_tool_policies.return_value = [{"tool_name": "create_issue", "policy": "blocked"}]

    with (
        patch("koda.control_plane.manager.get_control_plane_manager", return_value=manager),
        patch.dict("koda.services.tool_dispatcher._TOOL_HANDLERS", {call.tool: handler}, clear=False),
    ):
        result = await execute_tool(call, ctx)

    assert result.success is False
    assert result.metadata["policy_blocked"] is True
    assert result.metadata["policy_reason_code"] == "mcp_blocked"
    handler.assert_not_awaited()


# ---------------------------------------------------------------------------
# request_skill tests
# ---------------------------------------------------------------------------


class TestRequestSkill:
    """Tests for the request_skill agent tool handler."""

    def _make_skill(self, skill_id="tdd", name="TDD", aliases=("test-driven",), content="# TDD Skill"):
        from koda.skills._registry import SkillDefinition

        return SkillDefinition(
            id=skill_id,
            name=name,
            aliases=aliases,
            full_content=content,
        )

    @pytest.mark.asyncio
    async def test_request_skill_by_name(self):
        """Exact skill ID match returns skill content."""
        skill = self._make_skill()
        mock_registry = MagicMock()
        mock_registry.resolve_alias.return_value = None
        mock_registry.get.side_effect = lambda sid: skill if sid == "tdd" else None
        mock_registry.get_all.return_value = {"tdd": skill}

        ctx = _make_ctx()
        call = AgentToolCall(tool="request_skill", params={"query": "tdd"}, raw_match="")

        with (
            patch("koda.skills._registry.get_shared_registry", return_value=mock_registry),
            patch("koda.skills._telemetry.emit_skill_invocation"),
        ):
            from koda.services.tool_dispatcher import _handle_request_skill

            result = await _handle_request_skill(call.params, ctx)

        assert result.success is True
        assert "# TDD Skill" in result.output

    @pytest.mark.asyncio
    async def test_request_skill_by_alias(self):
        """Alias match resolves to the correct skill."""
        skill = self._make_skill()
        mock_registry = MagicMock()
        mock_registry.resolve_alias.side_effect = lambda q: "tdd" if "test-driven" in q else None
        mock_registry.get.side_effect = lambda sid: skill if sid == "tdd" else None

        ctx = _make_ctx()
        call = AgentToolCall(tool="request_skill", params={"query": "test-driven"}, raw_match="")

        with (
            patch("koda.skills._registry.get_shared_registry", return_value=mock_registry),
            patch("koda.skills._telemetry.emit_skill_invocation"),
        ):
            from koda.services.tool_dispatcher import _handle_request_skill

            result = await _handle_request_skill(call.params, ctx)

        assert result.success is True
        assert "# TDD Skill" in result.output

    @pytest.mark.asyncio
    async def test_request_skill_by_query(self):
        """Semantic fallback returns a matching skill."""
        skill = self._make_skill()
        mock_registry = MagicMock()
        mock_registry.resolve_alias.return_value = None
        mock_registry.get.return_value = None

        from koda.skills._selector import SkillMatch

        mock_match = SkillMatch(
            skill=skill,
            semantic_score=0.8,
            trigger_matched=False,
            alias_matched=False,
            composite_score=0.8,
            selection_reason="semantic",
        )
        mock_selector = MagicMock()
        mock_selector.select.return_value = [mock_match]

        ctx = _make_ctx()
        call = AgentToolCall(tool="request_skill", params={"query": "how to write tests"}, raw_match="")

        with (
            patch("koda.skills._registry.get_shared_registry", return_value=mock_registry),
            patch("koda.skills._selector.get_shared_selector", return_value=mock_selector),
            patch("koda.skills._telemetry.emit_skill_invocation"),
        ):
            from koda.services.tool_dispatcher import _handle_request_skill

            result = await _handle_request_skill(call.params, ctx)

        assert result.success is True
        assert "# TDD Skill" in result.output

    @pytest.mark.asyncio
    async def test_request_skill_not_found(self):
        """Unmatched query returns helpful error with available skills."""
        mock_registry = MagicMock()
        mock_registry.resolve_alias.return_value = None
        mock_registry.get.return_value = None
        mock_registry.get_all.return_value = {
            "tdd": self._make_skill(),
            "security": self._make_skill(skill_id="security"),
        }

        mock_selector = MagicMock()
        mock_selector.select.return_value = []

        ctx = _make_ctx()
        call = AgentToolCall(tool="request_skill", params={"query": "nonexistent_xyz"}, raw_match="")

        with (
            patch("koda.skills._registry.get_shared_registry", return_value=mock_registry),
            patch("koda.skills._selector.get_shared_selector", return_value=mock_selector),
        ):
            from koda.services.tool_dispatcher import _handle_request_skill

            result = await _handle_request_skill(call.params, ctx)

        assert result.success is False
        assert "No matching skill found" in result.output
        assert "nonexistent_xyz" in result.output
        assert "tdd" in result.output
        assert "security" in result.output

    @pytest.mark.asyncio
    async def test_request_skill_empty(self):
        """Empty query returns usage hint."""
        ctx = _make_ctx()

        from koda.services.tool_dispatcher import _handle_request_skill

        result = await _handle_request_skill({"query": ""}, ctx)

        assert result.success is False
        assert "specify a skill" in result.output.lower()

    @pytest.mark.asyncio
    async def test_request_skill_is_read_only(self):
        """request_skill must be classified as a read-only tool."""
        assert not _is_write_tool("request_skill", {})
