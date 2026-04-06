"""Tests for structured git tool handlers."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest

from koda.services.tool_dispatcher import ToolContext


@dataclass
class FakeCliResult:
    binary: str = "git"
    args: str = ""
    text: str = ""
    exit_code: int | None = 0
    timed_out: bool = False
    blocked: bool = False
    error: bool = False
    truncated: bool = False


def _make_ctx(work_dir: str = "/tmp", **overrides) -> ToolContext:
    defaults = dict(
        user_id=111,
        chat_id=111,
        work_dir=work_dir,
        user_data={
            "work_dir": work_dir,
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


class TestGitStatus:
    @pytest.mark.asyncio
    async def test_disabled(self):
        from koda.services.tool_dispatcher import _handle_git_status

        with patch("koda.services.tool_dispatcher.GIT_ENABLED", False):
            result = await _handle_git_status({}, _make_ctx())
        assert not result.success
        assert "not enabled" in result.output

    @pytest.mark.asyncio
    async def test_success(self):
        from koda.services.tool_dispatcher import _handle_git_status

        with (
            patch("koda.services.tool_dispatcher.GIT_ENABLED", True),
            patch(
                "koda.services.cli_runner.run_cli_command_detailed",
                new_callable=AsyncMock,
            ) as mock_run,
        ):
            mock_run.return_value = FakeCliResult(text="On branch main\nnothing to commit")
            result = await _handle_git_status({}, _make_ctx())
        assert result.success
        assert "main" in result.output


class TestGitDiff:
    @pytest.mark.asyncio
    async def test_staged(self):
        from koda.services.tool_dispatcher import _handle_git_diff

        with (
            patch("koda.services.tool_dispatcher.GIT_ENABLED", True),
            patch(
                "koda.services.cli_runner.run_cli_command_detailed",
                new_callable=AsyncMock,
            ) as mock_run,
        ):
            mock_run.return_value = FakeCliResult(text="diff --cached output")
            result = await _handle_git_diff({"staged": True}, _make_ctx())
        assert result.success
        # Verify --cached was passed in the args string
        call_args = mock_run.call_args
        assert "--cached" in call_args[0][1]


class TestGitLog:
    @pytest.mark.asyncio
    async def test_default(self):
        from koda.services.tool_dispatcher import _handle_git_log

        with (
            patch("koda.services.tool_dispatcher.GIT_ENABLED", True),
            patch(
                "koda.services.cli_runner.run_cli_command_detailed",
                new_callable=AsyncMock,
            ) as mock_run,
        ):
            mock_run.return_value = FakeCliResult(text="abc1234 Initial commit\ndef5678 Add feature")
            result = await _handle_git_log({}, _make_ctx())
        assert result.success


class TestGitCommit:
    @pytest.mark.asyncio
    async def test_missing_message(self):
        from koda.services.tool_dispatcher import _handle_git_commit

        with patch("koda.services.tool_dispatcher.GIT_ENABLED", True):
            result = await _handle_git_commit({}, _make_ctx())
        assert not result.success
        assert "message" in result.output.lower()

    @pytest.mark.asyncio
    async def test_success(self):
        from koda.services.tool_dispatcher import _handle_git_commit

        with (
            patch("koda.services.tool_dispatcher.GIT_ENABLED", True),
            patch(
                "koda.services.cli_runner.run_cli_command_detailed",
                new_callable=AsyncMock,
            ) as mock_run,
        ):
            mock_run.return_value = FakeCliResult(text="[main abc1234] fix: login bug\n 1 file changed")
            result = await _handle_git_commit({"message": "fix: login bug"}, _make_ctx())
        assert result.success


class TestGitBranch:
    @pytest.mark.asyncio
    async def test_list(self):
        from koda.services.tool_dispatcher import _handle_git_branch

        with (
            patch("koda.services.tool_dispatcher.GIT_ENABLED", True),
            patch(
                "koda.services.cli_runner.run_cli_command_detailed",
                new_callable=AsyncMock,
            ) as mock_run,
        ):
            mock_run.return_value = FakeCliResult(text="* main\n  feature/x")
            result = await _handle_git_branch({}, _make_ctx())
        assert result.success

    @pytest.mark.asyncio
    async def test_create(self):
        from koda.services.tool_dispatcher import _handle_git_branch

        with (
            patch("koda.services.tool_dispatcher.GIT_ENABLED", True),
            patch(
                "koda.services.cli_runner.run_cli_command_detailed",
                new_callable=AsyncMock,
            ) as mock_run,
        ):
            mock_run.return_value = FakeCliResult(text="")
            result = await _handle_git_branch({"name": "feature/new"}, _make_ctx())
        assert result.success


class TestGitCheckout:
    @pytest.mark.asyncio
    async def test_missing_target(self):
        from koda.services.tool_dispatcher import _handle_git_checkout

        with patch("koda.services.tool_dispatcher.GIT_ENABLED", True):
            result = await _handle_git_checkout({}, _make_ctx())
        assert not result.success

    @pytest.mark.asyncio
    async def test_success(self):
        from koda.services.tool_dispatcher import _handle_git_checkout

        with (
            patch("koda.services.tool_dispatcher.GIT_ENABLED", True),
            patch(
                "koda.services.cli_runner.run_cli_command_detailed",
                new_callable=AsyncMock,
            ) as mock_run,
        ):
            mock_run.return_value = FakeCliResult(text="Switched to branch 'main'")
            result = await _handle_git_checkout({"target": "main"}, _make_ctx())
        assert result.success


class TestGitPush:
    @pytest.mark.asyncio
    async def test_default(self):
        from koda.services.tool_dispatcher import _handle_git_push

        with (
            patch("koda.services.tool_dispatcher.GIT_ENABLED", True),
            patch(
                "koda.services.cli_runner.run_cli_command_detailed",
                new_callable=AsyncMock,
            ) as mock_run,
        ):
            mock_run.return_value = FakeCliResult(text="Everything up-to-date")
            result = await _handle_git_push({}, _make_ctx())
        assert result.success


class TestGitPull:
    @pytest.mark.asyncio
    async def test_with_rebase(self):
        from koda.services.tool_dispatcher import _handle_git_pull

        with (
            patch("koda.services.tool_dispatcher.GIT_ENABLED", True),
            patch(
                "koda.services.cli_runner.run_cli_command_detailed",
                new_callable=AsyncMock,
            ) as mock_run,
        ):
            mock_run.return_value = FakeCliResult(text="Already up to date.")
            result = await _handle_git_pull({"rebase": True}, _make_ctx())
        assert result.success
        call_args = mock_run.call_args
        assert "--rebase" in call_args[0][1]


class TestGitPrompt:
    def test_git_section_when_enabled(self):
        from koda.services.tool_prompt import build_agent_tools_prompt

        with patch("koda.services.tool_prompt.GIT_ENABLED", True):
            prompt = build_agent_tools_prompt()
        assert "### Git Operations" in prompt
        assert "git_status" not in prompt
        assert "git_commit" not in prompt

    def test_no_git_section_when_disabled(self):
        from koda.services.tool_prompt import build_agent_tools_prompt

        with patch("koda.services.tool_prompt.GIT_ENABLED", False):
            prompt = build_agent_tools_prompt()
        assert "### Git Operations" not in prompt
