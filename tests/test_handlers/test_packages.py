"""Tests for package manager command handlers."""

from unittest.mock import AsyncMock, patch

import pytest

from koda.handlers.packages import cmd_npm, cmd_pip


@pytest.mark.asyncio
async def test_pip_disabled(mock_update, mock_context):
    mock_context.args = ["list"]
    with patch("koda.handlers.packages.PIP_ENABLED", False):
        await cmd_pip(mock_update, mock_context)
    assert "disabled" in mock_update.message.reply_text.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_pip_no_args(mock_update, mock_context):
    mock_context.args = []
    with patch("koda.handlers.packages.PIP_ENABLED", True):
        await cmd_pip(mock_update, mock_context)
    assert "Usage" in mock_update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_pip_runs_command(mock_update, mock_context):
    mock_context.args = ["list"]
    with (
        patch("koda.handlers.packages.PIP_ENABLED", True),
        patch("koda.handlers.packages.BLOCKED_PIP_PATTERN", None),
        patch("koda.handlers.packages.run_shell_command", new_callable=AsyncMock) as mock_run,
        patch("koda.handlers.packages.send_long_message", new_callable=AsyncMock),
    ):
        mock_run.return_value = "Exit 0: packages"
        await cmd_pip(mock_update, mock_context)
        mock_run.assert_called_once()
        assert "pip list" in mock_run.call_args[0][0]


@pytest.mark.asyncio
async def test_pip_unknown_subcommand_is_denied(mock_update, mock_context):
    mock_context.args = ["frobnicate"]
    with patch("koda.handlers.packages.PIP_ENABLED", True):
        await cmd_pip(mock_update, mock_context)
    assert "not allowed" in mock_update.message.reply_text.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_pip_blocked_pattern(mock_update, mock_context):
    import re

    mock_context.args = ["install", "evil-package"]
    with (
        patch("koda.handlers.packages.PIP_ENABLED", True),
        patch("koda.handlers.packages.BLOCKED_PIP_PATTERN", re.compile(r"evil", re.I)),
    ):
        await cmd_pip(mock_update, mock_context)
    assert "Blocked" in mock_update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_pip_metachar_blocked(mock_update, mock_context):
    mock_context.args = ["list;", "rm", "-rf"]
    with patch("koda.handlers.packages.PIP_ENABLED", True):
        await cmd_pip(mock_update, mock_context)
    assert "meta-characters" in mock_update.message.reply_text.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_npm_metachar_blocked(mock_update, mock_context):
    mock_context.args = ["list", "|", "cat", "/etc/passwd"]
    with patch("koda.handlers.packages.NPM_ENABLED", True):
        await cmd_npm(mock_update, mock_context)
    assert "meta-characters" in mock_update.message.reply_text.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_npm_disabled(mock_update, mock_context):
    mock_context.args = ["list"]
    with patch("koda.handlers.packages.NPM_ENABLED", False):
        await cmd_npm(mock_update, mock_context)
    assert "disabled" in mock_update.message.reply_text.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_npm_runs_command(mock_update, mock_context):
    mock_context.args = ["list"]
    with (
        patch("koda.handlers.packages.NPM_ENABLED", True),
        patch("koda.handlers.packages.BLOCKED_NPM_PATTERN", None),
        patch("koda.handlers.packages.run_shell_command", new_callable=AsyncMock) as mock_run,
        patch("koda.handlers.packages.send_long_message", new_callable=AsyncMock),
    ):
        mock_run.return_value = "Exit 0: packages"
        await cmd_npm(mock_update, mock_context)
        mock_run.assert_called_once()
        assert "npm list" in mock_run.call_args[0][0]


@pytest.mark.asyncio
async def test_npm_unknown_subcommand_is_denied(mock_update, mock_context):
    mock_context.args = ["frobnicate"]
    with patch("koda.handlers.packages.NPM_ENABLED", True):
        await cmd_npm(mock_update, mock_context)
    assert "not allowed" in mock_update.message.reply_text.call_args[0][0].lower()
