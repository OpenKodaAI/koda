"""Tests for devops command handlers."""

from unittest.mock import AsyncMock, patch

import pytest

from koda.handlers.devops import cmd_docker, cmd_gh, cmd_glab


@pytest.mark.asyncio
async def test_gh_disabled(mock_update, mock_context):
    mock_context.args = ["pr", "list"]
    with patch("koda.handlers.devops.GH_ENABLED", False):
        await cmd_gh(mock_update, mock_context)
    mock_update.message.reply_text.assert_called_once()
    assert "disabled" in mock_update.message.reply_text.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_gh_no_args(mock_update, mock_context):
    mock_context.args = []
    with patch("koda.handlers.devops.GH_ENABLED", True):
        await cmd_gh(mock_update, mock_context)
    assert "Usage" in mock_update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_gh_runs_command(mock_update, mock_context):
    mock_context.args = ["pr", "list"]
    with (
        patch("koda.handlers.devops.GH_ENABLED", True),
        patch("koda.handlers.devops.run_cli_command", new_callable=AsyncMock) as mock_run,
        patch("koda.handlers.devops.send_long_message", new_callable=AsyncMock),
    ):
        mock_run.return_value = "Exit 0: ok"
        await cmd_gh(mock_update, mock_context)
        mock_run.assert_called_once()


@pytest.mark.asyncio
async def test_gh_unknown_subcommand_is_denied(mock_update, mock_context):
    mock_context.args = ["api", "--method", "POST", "/repos/org/repo"]
    with patch("koda.handlers.devops.GH_ENABLED", True):
        await cmd_gh(mock_update, mock_context)
    assert "not allowed" in mock_update.message.reply_text.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_glab_disabled(mock_update, mock_context):
    mock_context.args = ["mr", "list"]
    with patch("koda.handlers.devops.GLAB_ENABLED", False):
        await cmd_glab(mock_update, mock_context)
    assert "disabled" in mock_update.message.reply_text.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_docker_disabled(mock_update, mock_context):
    mock_context.args = ["ps"]
    with patch("koda.handlers.devops.DOCKER_ENABLED", False):
        await cmd_docker(mock_update, mock_context)
    assert "disabled" in mock_update.message.reply_text.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_docker_uses_allowed_cmds(mock_update, mock_context):
    mock_context.args = ["ps"]
    with (
        patch("koda.handlers.devops.DOCKER_ENABLED", True),
        patch("koda.handlers.devops.run_cli_command", new_callable=AsyncMock) as mock_run,
        patch("koda.handlers.devops.send_long_message", new_callable=AsyncMock),
    ):
        mock_run.return_value = "Exit 0: ok"
        await cmd_docker(mock_update, mock_context)
        # Should pass ALLOWED_DOCKER_CMDS to run_cli_command
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs.get("allowed_cmds") is not None
