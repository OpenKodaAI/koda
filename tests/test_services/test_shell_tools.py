"""Tests for shell execution tool handlers and background process manager."""

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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


def _kernel(result=None, *, side_effect=None):
    kernel = MagicMock()
    kernel.execute_command = AsyncMock(
        return_value=result
        or {"forwarded": True, "stdout": "ok\n", "stderr": "", "exit_code": 0, "timed_out": False, "killed": False},
        side_effect=side_effect,
    )
    return kernel


@pytest.fixture
def use_kernel(monkeypatch):
    def install(kernel):
        monkeypatch.setattr(
            "koda.services.shell_runner.get_runtime_controller",
            lambda: SimpleNamespace(runtime_kernel=kernel),
        )
        return kernel

    return install


async def _finish(mgr, handle_id):
    bg = mgr.get(handle_id)
    assert bg is not None
    await asyncio.wait({bg._collection_task}, timeout=5)
    assert bg.finished
    return bg


class TestBackgroundProcessManagerKernelPath:
    """shell_bg runs through the runtime-kernel ExecuteCommand path (M1-E4-T10)."""

    @pytest.mark.asyncio
    async def test_runs_command_through_runtime_kernel(self, use_kernel, tmp_path):
        from koda.services.shell_tools import BackgroundProcessManager

        kernel = use_kernel(_kernel())
        mgr = BackgroundProcessManager()

        handle_id, error = await mgr.start("echo ok", str(tmp_path), 111, timeout=42)
        bg = await _finish(mgr, handle_id)

        assert error is None
        kwargs = kernel.execute_command.await_args.kwargs
        assert kwargs["command"] == "echo ok"
        assert kwargs["timeout_seconds"] == 42
        assert kwargs["start_new_session"] is True
        assert kwargs["env_labels"] == {"command_kind": "shell_bg"}
        assert (bg.exit_code, bg.stdout_buf, bg.timed_out, bg.killed) == (0, "ok\n", False, False)

    @pytest.mark.asyncio
    async def test_runtime_kernel_unavailable_fails_closed(self, use_kernel, tmp_path):
        from koda.services.shell_tools import BackgroundProcessManager

        use_kernel(_kernel({"forwarded": False, "reason": "runtime-kernel not cutover-ready"}))
        mgr = BackgroundProcessManager()

        handle_id, error = await mgr.start("echo ok", str(tmp_path), 111)
        bg = await _finish(mgr, handle_id)

        assert error is None
        assert bg.exit_code == -1
        assert bg.stdout_buf == ""
        assert bg.stderr_buf == "Error: runtime-kernel not cutover-ready"

    @pytest.mark.asyncio
    async def test_runtime_kernel_error_is_reported(self, use_kernel, tmp_path):
        from koda.services.shell_tools import BackgroundProcessManager

        use_kernel(_kernel(side_effect=RuntimeError("kernel connection reset")))
        mgr = BackgroundProcessManager()

        handle_id, _ = await mgr.start("echo ok", str(tmp_path), 111)
        bg = await _finish(mgr, handle_id)

        assert bg.exit_code == -1
        assert bg.stderr_buf == "Error: kernel connection reset"

    @pytest.mark.asyncio
    async def test_kernel_timeout_is_reported(self, use_kernel, tmp_path):
        from koda.services.shell_tools import BackgroundProcessManager

        use_kernel(
            _kernel(
                {"forwarded": True, "stdout": "", "stderr": "", "exit_code": 124, "timed_out": True, "killed": True}
            )
        )
        mgr = BackgroundProcessManager()

        handle_id, _ = await mgr.start("sleep 100", str(tmp_path), 111, timeout=1)
        bg = await _finish(mgr, handle_id)

        assert bg.timed_out is True
        assert bg.exit_code == -1

    @pytest.mark.asyncio
    async def test_output_is_capped(self, use_kernel, tmp_path):
        from koda.services.shell_tools import BackgroundProcessManager

        use_kernel(
            _kernel({"forwarded": True, "stdout": "x" * 50, "stderr": "y" * 50, "exit_code": 0, "timed_out": False})
        )
        mgr = BackgroundProcessManager()

        with patch("koda.services.shell_tools.SHELL_BG_OUTPUT_MAX", 10):
            handle_id, _ = await mgr.start("cat big", str(tmp_path), 111)
            bg = await _finish(mgr, handle_id)

        assert (bg.stdout_buf, bg.stderr_buf) == ("x" * 10, "y" * 10)

    @pytest.mark.asyncio
    async def test_kill_cancels_the_in_flight_kernel_call(self, use_kernel, tmp_path):
        from koda.services.shell_tools import BackgroundProcessManager

        cancelled = asyncio.Event()

        async def _run_forever(**_kwargs):
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise

        use_kernel(_kernel(side_effect=_run_forever))
        mgr = BackgroundProcessManager()
        handle_id, _ = await mgr.start("sleep 600", str(tmp_path), 111)
        await asyncio.sleep(0)

        assert await mgr.kill(handle_id, user_id=111) is None

        bg = mgr.get(handle_id)
        assert cancelled.is_set()
        assert (bg.finished, bg.killed, bg.exit_code) == (True, True, -1)
        assert mgr.active_count(111) == 0
        assert await mgr.kill(handle_id, user_id=111) == "Process already finished."

    @pytest.mark.asyncio
    async def test_start_prunes_expired_finished_records(self, use_kernel, tmp_path):
        from koda.services.shell_tools import BackgroundProcess, BackgroundProcessManager

        use_kernel(_kernel())
        mgr = BackgroundProcessManager()
        now = time.monotonic()
        for handle_id, finished_ago in (("bg-111-old", 601.0), ("bg-111-recent", 5.0)):
            mgr._processes[handle_id] = BackgroundProcess(
                handle_id=handle_id,
                user_id=111,
                command="true",
                work_dir=str(tmp_path),
                started_at=now - finished_ago - 1,
                finished=True,
                finished_at=now - finished_ago,
            )

        handle_id, _ = await mgr.start("echo ok", str(tmp_path), 111)
        await _finish(mgr, handle_id)

        assert set(mgr._processes) == {"bg-111-recent", handle_id}

    def test_cleanup_keeps_output_of_long_command_that_just_finished(self, tmp_path):
        from koda.services.shell_tools import BackgroundProcess, BackgroundProcessManager

        mgr = BackgroundProcessManager()
        now = time.monotonic()
        mgr._processes["bg-111-1"] = BackgroundProcess(
            handle_id="bg-111-1",
            user_id=111,
            command="make all",
            work_dir=str(tmp_path),
            started_at=now - 3600,
            finished=True,
            finished_at=now - 1,
        )

        assert mgr.cleanup_finished(max_age=600) == 0
        assert "bg-111-1" in mgr._processes

    def test_cleanup_never_drops_running_commands(self, tmp_path):
        from koda.services.shell_tools import BackgroundProcess, BackgroundProcessManager

        mgr = BackgroundProcessManager()
        mgr._processes["bg-111-1"] = BackgroundProcess(
            handle_id="bg-111-1",
            user_id=111,
            command="make all",
            work_dir=str(tmp_path),
            started_at=time.monotonic() - 3600,
        )

        assert mgr.cleanup_finished(max_age=0) == 0


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
