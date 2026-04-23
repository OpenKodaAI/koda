"""Tests for CLI runner service."""

import os
from unittest.mock import AsyncMock, patch

import pytest

from koda.services.cli_runner import run_cli_command


@pytest.mark.asyncio
async def test_empty_args():
    result = await run_cli_command("gh", "", "/tmp")
    assert "Usage" in result


@pytest.mark.asyncio
async def test_metachar_blocked():
    result = await run_cli_command("gh", "pr list; rm -rf /", "/tmp")
    assert "meta-characters" in result.lower()


@pytest.mark.asyncio
async def test_dangerous_pattern_blocked():
    result = await run_cli_command("gh", "rm -rf /", "/tmp")
    assert "Blocked" in result


@pytest.mark.asyncio
async def test_blocked_pattern():
    import re

    pattern = re.compile(r"--force", re.I)
    result = await run_cli_command("gh", "repo delete --force", "/tmp", blocked_pattern=pattern)
    assert "Blocked" in result


@pytest.mark.asyncio
async def test_allowed_cmds_rejected():
    result = await run_cli_command("docker", "evil-cmd foo", "/tmp", allowed_cmds={"ps", "logs"})
    assert "not allowed" in result.lower()


@pytest.mark.asyncio
async def test_allowed_cmds_accepted():
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(b"ok", b""))
    mock_proc.returncode = 0

    with patch("koda.services.cli_runner.asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await run_cli_command("docker", "ps", "/tmp", allowed_cmds={"ps", "logs"})
        mock_exec.assert_called_once()
        call_args = mock_exec.call_args[0]
        assert call_args == ("docker", "ps")
        assert "Exit 0" in result


@pytest.mark.asyncio
async def test_env_passthrough():
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(b"ok", b""))
    mock_proc.returncode = 0

    with patch("koda.services.cli_runner.asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        env = {"GOOGLE_APPLICATION_CREDENTIALS": "/path/to/creds.json"}
        await run_cli_command("gws", "gmail users.messages.list", "/tmp", env=env)
        call_kwargs = mock_exec.call_args
        passed_env = call_kwargs.kwargs.get("env")
        assert passed_env is not None
        assert passed_env["GOOGLE_APPLICATION_CREDENTIALS"] == "/path/to/creds.json"


@pytest.mark.asyncio
async def test_tool_cli_environment_strips_ambient_secrets(monkeypatch):
    monkeypatch.setenv("AGENT_TOKEN", "telegram-secret")
    monkeypatch.setenv("CONFLUENCE_API_TOKEN", "confluence-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "provider-secret")
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(b"ok", b""))
    mock_proc.returncode = 0

    with patch("koda.services.cli_runner.asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        await run_cli_command("gws", "gmail users.messages.list", "/tmp", env={"LOCAL_FLAG": "enabled"})
        passed_env = mock_exec.call_args.kwargs.get("env")

    assert passed_env is not None
    assert passed_env["LOCAL_FLAG"] == "enabled"
    assert "AGENT_TOKEN" not in passed_env
    assert "CONFLUENCE_API_TOKEN" not in passed_env
    assert "ANTHROPIC_API_KEY" not in passed_env


@pytest.mark.asyncio
async def test_normal_execution():
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(b"result", b""))
    mock_proc.returncode = 0

    with patch("koda.services.cli_runner.asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await run_cli_command("gh", "pr list", "/tmp")
        mock_exec.assert_called_once()
        call_args = mock_exec.call_args[0]
        assert call_args == ("gh", "pr", "list")
        assert "Exit 0" in result
        assert "result" in result


@pytest.mark.asyncio
async def test_timeout_handling():
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(side_effect=TimeoutError())
    mock_proc.kill = AsyncMock()
    mock_proc.wait = AsyncMock()

    with patch("koda.services.cli_runner.asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await run_cli_command("gh", "pr list", "/tmp", timeout=5)

    assert "Timeout" in result
