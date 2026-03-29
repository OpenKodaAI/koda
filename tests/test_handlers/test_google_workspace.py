"""Tests for Google Workspace command handlers."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from koda.handlers.google_workspace import (
    _format_gws_output,
    _gws_env,
    cmd_gcal,
    cmd_gdrive,
    cmd_gmail,
    cmd_gsheets,
    cmd_gws,
)


class TestGwsEnv:
    def test_with_credentials(self):
        with patch("koda.handlers.google_workspace.GWS_CREDENTIALS_FILE", "/path/to/creds.json"):
            result = _gws_env()
        assert result == {"GOOGLE_APPLICATION_CREDENTIALS": "/path/to/creds.json"}

    def test_without_credentials(self):
        with patch("koda.handlers.google_workspace.GWS_CREDENTIALS_FILE", None):
            result = _gws_env()
        assert result is None


class TestFormatGwsOutput:
    def test_json_output(self):
        data = {"messages": [{"id": "1", "snippet": "Hello"}]}
        raw = f"Exit 0:\n{json.dumps(data)}"
        result = _format_gws_output(raw)
        assert '"messages"' in result
        assert "Exit 0:" in result

    def test_non_json_output(self):
        raw = "Exit 0:\nsome plain text output"
        result = _format_gws_output(raw)
        assert result == raw

    def test_truncates_large_json(self):
        data = {"key": "x" * 4000}
        raw = f"Exit 0:\n{json.dumps(data)}"
        result = _format_gws_output(raw)
        assert "truncated" in result
        assert len(result) < 4000


class TestGwsHandler:
    @pytest.mark.asyncio
    async def test_gws_disabled(self, mock_update, mock_context):
        mock_context.args = ["gmail", "users.messages.list"]
        with patch("koda.handlers.google_workspace.GWS_ENABLED", False):
            await cmd_gws(mock_update, mock_context)
        assert "disabled" in mock_update.message.reply_text.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_gws_no_args(self, mock_update, mock_context):
        mock_context.args = []
        with patch("koda.handlers.google_workspace.GWS_ENABLED", True):
            await cmd_gws(mock_update, mock_context)
        assert "Usage" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_gws_runs_command(self, mock_update, mock_context):
        mock_context.args = ["gmail", "users.messages.list"]
        with (
            patch("koda.handlers.google_workspace.GWS_ENABLED", True),
            patch("koda.handlers.google_workspace.run_cli_command", new_callable=AsyncMock) as mock_run,
            patch("koda.handlers.google_workspace.send_long_message", new_callable=AsyncMock),
        ):
            mock_run.return_value = 'Exit 0:\n{"messages": []}'
            await cmd_gws(mock_update, mock_context)
            mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_gmail_prepends_service(self, mock_update, mock_context):
        mock_context.args = ["users.messages.list"]
        with (
            patch("koda.handlers.google_workspace.GWS_ENABLED", True),
            patch("koda.handlers.google_workspace.run_cli_command", new_callable=AsyncMock) as mock_run,
            patch("koda.handlers.google_workspace.send_long_message", new_callable=AsyncMock),
        ):
            mock_run.return_value = "Exit 0:\n{}"
            await cmd_gmail(mock_update, mock_context)
            args_passed = mock_run.call_args[0][1]
            assert args_passed.startswith("gmail ")

    @pytest.mark.asyncio
    async def test_gcal_prepends_service(self, mock_update, mock_context):
        mock_context.args = ["events.list"]
        with (
            patch("koda.handlers.google_workspace.GWS_ENABLED", True),
            patch("koda.handlers.google_workspace.run_cli_command", new_callable=AsyncMock) as mock_run,
            patch("koda.handlers.google_workspace.send_long_message", new_callable=AsyncMock),
        ):
            mock_run.return_value = "Exit 0:\n{}"
            await cmd_gcal(mock_update, mock_context)
            args_passed = mock_run.call_args[0][1]
            assert args_passed.startswith("calendar ")

    @pytest.mark.asyncio
    async def test_gdrive_prepends_service(self, mock_update, mock_context):
        mock_context.args = ["files.list"]
        with (
            patch("koda.handlers.google_workspace.GWS_ENABLED", True),
            patch("koda.handlers.google_workspace.run_cli_command", new_callable=AsyncMock) as mock_run,
            patch("koda.handlers.google_workspace.send_long_message", new_callable=AsyncMock),
        ):
            mock_run.return_value = "Exit 0:\n{}"
            await cmd_gdrive(mock_update, mock_context)
            args_passed = mock_run.call_args[0][1]
            assert args_passed.startswith("drive ")

    @pytest.mark.asyncio
    async def test_gsheets_prepends_service(self, mock_update, mock_context):
        mock_context.args = ["spreadsheets.get"]
        with (
            patch("koda.handlers.google_workspace.GWS_ENABLED", True),
            patch("koda.handlers.google_workspace.run_cli_command", new_callable=AsyncMock) as mock_run,
            patch("koda.handlers.google_workspace.send_long_message", new_callable=AsyncMock),
        ):
            mock_run.return_value = "Exit 0:\n{}"
            await cmd_gsheets(mock_update, mock_context)
            args_passed = mock_run.call_args[0][1]
            assert args_passed.startswith("sheets ")

    @pytest.mark.asyncio
    async def test_gws_passes_env(self, mock_update, mock_context):
        mock_context.args = ["gmail", "users.messages.list"]
        with (
            patch("koda.handlers.google_workspace.GWS_ENABLED", True),
            patch("koda.handlers.google_workspace.GWS_CREDENTIALS_FILE", "/creds.json"),
            patch("koda.handlers.google_workspace.run_cli_command", new_callable=AsyncMock) as mock_run,
            patch("koda.handlers.google_workspace.send_long_message", new_callable=AsyncMock),
        ):
            mock_run.return_value = "Exit 0:\n{}"
            await cmd_gws(mock_update, mock_context)
            call_kwargs = mock_run.call_args.kwargs
            assert call_kwargs["env"] == {"GOOGLE_APPLICATION_CREDENTIALS": "/creds.json"}

    @pytest.mark.asyncio
    async def test_gws_passes_timeout(self, mock_update, mock_context):
        mock_context.args = ["gmail", "users.messages.list"]
        with (
            patch("koda.handlers.google_workspace.GWS_ENABLED", True),
            patch("koda.handlers.google_workspace.GWS_TIMEOUT", 90),
            patch("koda.handlers.google_workspace.run_cli_command", new_callable=AsyncMock) as mock_run,
            patch("koda.handlers.google_workspace.send_long_message", new_callable=AsyncMock),
        ):
            mock_run.return_value = "Exit 0:\n{}"
            await cmd_gws(mock_update, mock_context)
            call_kwargs = mock_run.call_args.kwargs
            assert call_kwargs["timeout"] == 90


class TestBlockedGwsPatterns:
    """Test that BLOCKED_GWS_PATTERN correctly blocks dangerous operations."""

    def test_blocked_admin_user_insert(self):
        from koda.config import BLOCKED_GWS_PATTERN

        assert BLOCKED_GWS_PATTERN.search("admin directory.users.insert --params '{}'")

    def test_blocked_drive_delete(self):
        from koda.config import BLOCKED_GWS_PATTERN

        assert BLOCKED_GWS_PATTERN.search('drive drives.delete --params \'{"driveId": "abc"}\'')

    def test_blocked_chat_delete(self):
        from koda.config import BLOCKED_GWS_PATTERN

        assert BLOCKED_GWS_PATTERN.search('chat spaces.delete --params \'{"name": "spaces/abc"}\'')

    def test_blocked_gmail_forwarding(self):
        from koda.config import BLOCKED_GWS_PATTERN

        assert BLOCKED_GWS_PATTERN.search("gmail users.settings.forwardingAddresses --params '{}'")

    def test_blocked_gmail_send_as_create(self):
        from koda.config import BLOCKED_GWS_PATTERN

        assert BLOCKED_GWS_PATTERN.search("gmail users.settings.sendAs.create --params '{}'")

    def test_blocked_drive_empty_trash(self):
        from koda.config import BLOCKED_GWS_PATTERN

        assert BLOCKED_GWS_PATTERN.search("drive files.emptyTrash")

    def test_allowed_gmail_list(self):
        from koda.config import BLOCKED_GWS_PATTERN

        assert not BLOCKED_GWS_PATTERN.search('gmail users.messages.list --params \'{"userId": "me"}\'')

    def test_allowed_drive_files_list(self):
        from koda.config import BLOCKED_GWS_PATTERN

        assert not BLOCKED_GWS_PATTERN.search('drive files.list --params \'{"q": "name contains test"}\'')

    def test_allowed_calendar_events_list(self):
        from koda.config import BLOCKED_GWS_PATTERN

        assert not BLOCKED_GWS_PATTERN.search("calendar events.list --params '{}'")

    def test_allowed_gmail_send(self):
        from koda.config import BLOCKED_GWS_PATTERN

        assert not BLOCKED_GWS_PATTERN.search("gmail users.messages.send --params '{}'")
