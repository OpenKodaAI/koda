"""Tests for shell command runner."""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from koda.services.shell_runner import run_shell_command


def _runtime_kernel(result: dict[str, object] | None = None):
    kernel = MagicMock()
    kernel.start = AsyncMock(return_value=None)
    kernel.health = MagicMock(
        return_value={
            "ready": True,
            "authoritative": True,
            "production_ready": True,
            "cutover_allowed": True,
            "mode": "rust",
            "transport": "grpc-uds",
        }
    )
    kernel.execute_command = AsyncMock(
        return_value=result
        or {
            "forwarded": True,
            "stdout": "hello world",
            "stderr": "",
            "exit_code": 0,
            "timed_out": False,
            "killed": False,
        }
    )
    return kernel


class TestRunShellCommand:
    @pytest.mark.asyncio
    async def test_successful_command(self, monkeypatch):
        kernel = _runtime_kernel()
        monkeypatch.setattr(
            "koda.services.shell_runner.get_runtime_controller",
            lambda: SimpleNamespace(runtime_kernel=kernel),
        )

        result = await run_shell_command("echo hello", "/tmp")

        kernel.execute_command.assert_awaited_once()
        assert "Exit 0" in result
        assert "hello world" in result

    @pytest.mark.asyncio
    async def test_command_timeout(self, monkeypatch):
        kernel = _runtime_kernel(
            {
                "forwarded": True,
                "stdout": "",
                "stderr": "",
                "exit_code": 124,
                "timed_out": True,
                "killed": True,
            }
        )
        monkeypatch.setattr(
            "koda.services.shell_runner.get_runtime_controller",
            lambda: SimpleNamespace(runtime_kernel=kernel),
        )

        result = await run_shell_command("sleep 100", "/tmp", timeout=1)

        assert "Timeout" in result

    @pytest.mark.asyncio
    async def test_command_error(self, monkeypatch):
        kernel = _runtime_kernel(
            {
                "forwarded": True,
                "stdout": "",
                "stderr": "not found",
                "exit_code": 127,
                "timed_out": False,
                "killed": False,
            }
        )
        monkeypatch.setattr(
            "koda.services.shell_runner.get_runtime_controller",
            lambda: SimpleNamespace(runtime_kernel=kernel),
        )

        result = await run_shell_command("nonexistent", "/tmp")

        assert "Exit 127" in result

    @pytest.mark.asyncio
    async def test_output_truncation(self, monkeypatch):
        long_output = "x" * 5000
        kernel = _runtime_kernel(
            {
                "forwarded": True,
                "stdout": long_output,
                "stderr": "",
                "exit_code": 0,
                "timed_out": False,
                "killed": False,
            }
        )
        monkeypatch.setattr(
            "koda.services.shell_runner.get_runtime_controller",
            lambda: SimpleNamespace(runtime_kernel=kernel),
        )

        result = await run_shell_command("cat big_file", "/tmp")

        assert "truncated" in result
        assert len(result) < 5000

    @pytest.mark.asyncio
    async def test_env_parameter(self, monkeypatch):
        kernel = _runtime_kernel()
        monkeypatch.setattr(
            "koda.services.shell_runner.get_runtime_controller",
            lambda: SimpleNamespace(runtime_kernel=kernel),
        )

        await run_shell_command("echo hello", "/tmp", env={"MY_VAR": "my_value"})

        call_kwargs = kernel.execute_command.call_args.kwargs
        passed_env = call_kwargs.get("environment_overrides")
        assert passed_env is not None
        assert passed_env["MY_VAR"] == "my_value"

    @pytest.mark.asyncio
    async def test_tool_environment_strips_ambient_secrets(self, monkeypatch):
        monkeypatch.setenv("AGENT_TOKEN", "telegram-secret")
        monkeypatch.setenv("JIRA_API_TOKEN", "jira-secret")
        monkeypatch.setenv("OPENAI_API_KEY", "provider-secret")
        monkeypatch.setenv("PATH", os.environ.get("PATH", ""))
        kernel = _runtime_kernel()
        monkeypatch.setattr(
            "koda.services.shell_runner.get_runtime_controller",
            lambda: SimpleNamespace(runtime_kernel=kernel),
        )

        await run_shell_command("echo hello", "/tmp", env={"LOCAL_FLAG": "enabled"})

        passed_env = kernel.execute_command.call_args.kwargs.get("environment_overrides")
        assert passed_env is not None
        assert passed_env["LOCAL_FLAG"] == "enabled"
        assert "AGENT_TOKEN" not in passed_env
        assert "JIRA_API_TOKEN" not in passed_env
        assert "OPENAI_API_KEY" not in passed_env

    @pytest.mark.asyncio
    async def test_no_output(self, monkeypatch):
        kernel = _runtime_kernel(
            {
                "forwarded": True,
                "stdout": "",
                "stderr": "",
                "exit_code": 0,
                "timed_out": False,
                "killed": False,
            }
        )
        monkeypatch.setattr(
            "koda.services.shell_runner.get_runtime_controller",
            lambda: SimpleNamespace(runtime_kernel=kernel),
        )

        result = await run_shell_command("true", "/tmp")

        assert "no output" in result

    @pytest.mark.asyncio
    async def test_runtime_kernel_unavailable_fails_closed(self, monkeypatch):
        kernel = _runtime_kernel({"forwarded": False, "reason": "runtime-kernel unavailable"})
        monkeypatch.setattr(
            "koda.services.shell_runner.get_runtime_controller",
            lambda: SimpleNamespace(runtime_kernel=kernel),
        )

        result = await run_shell_command("echo hello", "/tmp")

        assert "runtime-kernel unavailable" in result
