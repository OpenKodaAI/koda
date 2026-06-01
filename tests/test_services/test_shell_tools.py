"""Tests for shell execution tool handlers and background process manager."""

from unittest.mock import AsyncMock, patch

import pytest

from koda.services.tool_dispatcher import (
    ToolContext,
)


def _make_ctx(**overrides) -> ToolContext:
    defaults = dict(
        user_id=111,
        chat_id=111,
        work_dir="/tmp",
        user_data={
            "work_dir": "/tmp",
            "model": "claude-sonnet-4-6",
            "session_id": "s",
            "total_cost": 0.0,
            "query_count": 0,
        },
        agent=AsyncMock(),
        agent_mode="autonomous",
    )
    defaults.update(overrides)
    return ToolContext(**defaults)


class TestShellExecuteHandler:
    @pytest.mark.asyncio
    async def test_disabled(self):
        from koda.services.tool_dispatcher import _handle_shell_execute

        ctx = _make_ctx()
        with patch("koda.services.tool_dispatcher.SHELL_ENABLED", False):
            result = await _handle_shell_execute({"command": "ls"}, ctx)
        assert not result.success
        assert "not enabled" in result.output

    @pytest.mark.asyncio
    async def test_missing_command(self):
        from koda.services.tool_dispatcher import _handle_shell_execute

        ctx = _make_ctx()
        with patch("koda.services.tool_dispatcher.SHELL_ENABLED", True):
            result = await _handle_shell_execute({}, ctx)
        assert not result.success
        assert "command" in result.output.lower()

    @pytest.mark.asyncio
    async def test_execute_success(self):
        from koda.services.tool_dispatcher import _handle_shell_execute

        ctx = _make_ctx()
        with (
            patch("koda.services.tool_dispatcher.SHELL_ENABLED", True),
            patch(
                "koda.services.shell_runner.run_shell_command",
                new_callable=AsyncMock,
                return_value="Exit 0:\nfile1.txt\nfile2.txt",
            ),
        ):
            result = await _handle_shell_execute({"command": "ls"}, ctx)
        assert result.success


class TestShellBgHandler:
    @pytest.mark.asyncio
    async def test_disabled(self):
        from koda.services.tool_dispatcher import _handle_shell_bg

        ctx = _make_ctx()
        with patch("koda.services.tool_dispatcher.SHELL_ENABLED", False):
            result = await _handle_shell_bg({"command": "sleep 10"}, ctx)
        assert not result.success

    @pytest.mark.asyncio
    async def test_start_success(self):
        from koda.services.tool_dispatcher import _handle_shell_bg

        ctx = _make_ctx()
        with (
            patch("koda.services.tool_dispatcher.SHELL_ENABLED", True),
            patch("koda.services.shell_tools.bg_process_manager") as mock_mgr,
        ):
            mock_mgr.start = AsyncMock(return_value=("bg-111-1", None))
            result = await _handle_shell_bg({"command": "npm run build"}, ctx)
        assert result.success
        assert "bg-111-1" in result.output


class TestShellStatusHandler:
    @pytest.mark.asyncio
    async def test_disabled(self):
        from koda.services.tool_dispatcher import _handle_shell_status

        ctx = _make_ctx()
        with patch("koda.services.tool_dispatcher.SHELL_ENABLED", False):
            result = await _handle_shell_status({"handle_id": "bg-111-1"}, ctx)
        assert not result.success

    @pytest.mark.asyncio
    async def test_missing_handle(self):
        from koda.services.tool_dispatcher import _handle_shell_status

        ctx = _make_ctx()
        with patch("koda.services.tool_dispatcher.SHELL_ENABLED", True):
            result = await _handle_shell_status({}, ctx)
        assert not result.success
        assert "handle_id" in result.output.lower()


class TestShellKillHandler:
    @pytest.mark.asyncio
    async def test_disabled(self):
        from koda.services.tool_dispatcher import _handle_shell_kill

        ctx = _make_ctx()
        with patch("koda.services.tool_dispatcher.SHELL_ENABLED", False):
            result = await _handle_shell_kill({"handle_id": "bg-111-1"}, ctx)
        assert not result.success


class TestShellOutputHandler:
    @pytest.mark.asyncio
    async def test_disabled(self):
        from koda.services.tool_dispatcher import _handle_shell_output

        ctx = _make_ctx()
        with patch("koda.services.tool_dispatcher.SHELL_ENABLED", False):
            result = await _handle_shell_output({"handle_id": "bg-111-1"}, ctx)
        assert not result.success

    @pytest.mark.asyncio
    async def test_missing_handle(self):
        from koda.services.tool_dispatcher import _handle_shell_output

        ctx = _make_ctx()
        with patch("koda.services.tool_dispatcher.SHELL_ENABLED", True):
            result = await _handle_shell_output({}, ctx)
        assert not result.success


class TestBackgroundProcessManager:
    def test_make_handle(self):
        from koda.services.shell_tools import BackgroundProcessManager

        mgr = BackgroundProcessManager()
        h = mgr._make_handle(42)
        assert h.startswith("bg-42-")

    def test_active_count_empty(self):
        from koda.services.shell_tools import BackgroundProcessManager

        mgr = BackgroundProcessManager()
        assert mgr.active_count(42) == 0

    @pytest.mark.asyncio
    async def test_kill_nonexistent(self):
        from koda.services.shell_tools import BackgroundProcessManager

        mgr = BackgroundProcessManager()
        err = await mgr.kill("bg-0-999")
        assert err is not None
        assert "No process" in err


class TestShellPrompt:
    def test_shell_section_when_enabled(self):
        from koda.services.tool_prompt import build_agent_tools_prompt

        with patch("koda.services.tool_prompt.SHELL_ENABLED", True):
            prompt = build_agent_tools_prompt()
        assert "### Shell Execution" in prompt
        assert "shell_execute" not in prompt

    def test_no_shell_section_when_disabled(self):
        from koda.services.tool_prompt import build_agent_tools_prompt

        with patch("koda.services.tool_prompt.SHELL_ENABLED", False):
            prompt = build_agent_tools_prompt()
        assert "### Shell Execution" not in prompt
