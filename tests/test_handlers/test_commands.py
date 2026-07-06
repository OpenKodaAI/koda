"""Tests for command handlers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.config import DEFAULT_MODEL
from koda.handlers.commands import (
    cmd_cancel,
    cmd_cost,
    cmd_newsession,
    cmd_provider,
    cmd_resetcost,
    cmd_settings,
    cmd_shell,
    cmd_start,
    cmd_system,
    init_user_data,
)


class TestInitUserData:
    def test_sets_defaults(self):
        data = {}
        init_user_data(data)
        assert data["session_id"] is None
        assert data["model"] == DEFAULT_MODEL
        assert data["total_cost"] == 0.0
        assert data["query_count"] == 0

    def test_preserves_existing(self):
        data = {"model": "claude-opus-4-6", "total_cost": 1.5}
        init_user_data(data)
        assert data["model"] == "claude-opus-4-6"
        assert data["total_cost"] == 1.5


class TestCmdStart:
    @pytest.mark.asyncio
    async def test_authorized_user(self, mock_update, mock_context):
        await cmd_start(mock_update, mock_context)
        mock_update.message.reply_text.assert_called_once()
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "Ready." in call_text
        assert "/settings" in call_text

    @pytest.mark.asyncio
    async def test_unauthorized_user(self, unauthorized_update, mock_context):
        await cmd_start(unauthorized_update, mock_context)
        unauthorized_update.message.reply_text.assert_called_with("Access denied.")


class TestCmdSettings:
    @pytest.mark.asyncio
    async def test_shows_agent_local_settings_hub(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        await cmd_settings(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args.args[0]
        reply_markup = mock_update.message.reply_text.call_args.kwargs["reply_markup"]
        assert "Agent settings" in call_text
        assert reply_markup.inline_keyboard


class TestCmdNewsession:
    @pytest.mark.asyncio
    async def test_clears_session(self, mock_update, mock_context):
        mock_context.user_data["session_id"] = "old-session"
        mock_context.user_data["provider_sessions"] = {"claude": "native-old"}
        with patch("koda.utils.approval.revoke_scoped_approval_state", new=AsyncMock()) as mock_revoke:
            await cmd_newsession(mock_update, mock_context)
        mock_revoke.assert_awaited_once()
        kwargs = mock_revoke.await_args.kwargs
        assert kwargs["session_id"] == "old-session"
        assert kwargs["user_id"] == 111
        assert kwargs["chat_id"] == 111
        assert isinstance(mock_context.user_data["session_id"], str)
        assert mock_context.user_data["session_id"].startswith("session-")
        assert mock_context.user_data["session_id"] != "old-session"
        assert mock_context.user_data["provider_sessions"] == {}


class TestCmdCost:
    @pytest.mark.asyncio
    async def test_shows_cost(self, mock_update, mock_context):
        mock_context.user_data["total_cost"] = 1.2345
        mock_context.user_data["query_count"] = 10
        init_user_data(mock_context.user_data)
        await cmd_cost(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "1.2345" in call_text
        assert "10" in call_text


class TestCmdProvider:
    @pytest.mark.asyncio
    async def test_sets_provider_and_model(self, mock_update, mock_context):
        mock_context.args = ["codex"]
        init_user_data(mock_context.user_data)

        with patch(
            "koda.handlers.commands.set_agent_general_provider",
            return_value={
                "default_provider": "codex",
                "general_model": "gpt-5.4",
                "default_models_by_provider": {"codex": "gpt-5.4"},
                "functional_defaults": {"general": {"provider_id": "codex", "model_id": "gpt-5.4"}},
                "transcription_provider": "whispercpp",
                "transcription_model": "whisper-cpp-local",
                "audio_provider": "kokoro",
                "audio_model": "kokoro-v1",
                "tts_voice": "pf_dora",
                "tts_voice_label": "Dora",
                "tts_voice_language": "pt-br",
                "selectable_function_options": {
                    "general": [
                        {
                            "provider_id": "codex",
                            "model_id": "gpt-5.4",
                            "provider_title": "Codex",
                            "title": "gpt-5.4",
                        }
                    ]
                },
            },
        ):
            await cmd_provider(mock_update, mock_context)

        assert mock_context.user_data["provider"] == "codex"
        assert mock_context.user_data["model"].startswith("gpt-")


class TestCmdResetcost:
    @pytest.mark.asyncio
    async def test_resets(self, mock_update, mock_context):
        mock_context.user_data["total_cost"] = 5.0
        mock_context.user_data["query_count"] = 20
        init_user_data(mock_context.user_data)
        await cmd_resetcost(mock_update, mock_context)
        assert mock_context.user_data["total_cost"] == 0.0
        assert mock_context.user_data["query_count"] == 0


class TestCmdSystem:
    @pytest.mark.asyncio
    async def test_set_prompt(self, mock_update, mock_context):
        mock_context.args = ["You", "are", "helpful"]
        init_user_data(mock_context.user_data)
        await cmd_system(mock_update, mock_context)
        assert mock_context.user_data["system_prompt"] == "You are helpful"

    @pytest.mark.asyncio
    async def test_clear_prompt(self, mock_update, mock_context):
        mock_context.args = ["clear"]
        mock_context.user_data["system_prompt"] = "old prompt"
        init_user_data(mock_context.user_data)
        await cmd_system(mock_update, mock_context)
        assert mock_context.user_data["system_prompt"] is None

    @pytest.mark.asyncio
    async def test_view_prompt(self, mock_update, mock_context):
        mock_context.args = []
        mock_context.user_data["system_prompt"] = "my prompt"
        init_user_data(mock_context.user_data)
        await cmd_system(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "my prompt" in call_text


class TestCmdShell:
    @pytest.mark.asyncio
    async def test_blocked_command(self, mock_update, mock_context):
        mock_context.args = ["rm", "-rf", "/"]
        init_user_data(mock_context.user_data)
        await cmd_shell(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "Blocked" in call_text

    @pytest.mark.asyncio
    async def test_no_args(self, mock_update, mock_context):
        mock_context.args = []
        init_user_data(mock_context.user_data)
        await cmd_shell(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "Usage" in call_text


class TestCmdCancel:
    @pytest.mark.asyncio
    async def test_nothing_running(self, mock_update, mock_context):
        await cmd_cancel(mock_update, mock_context)
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "Nothing running" in call_text

    @pytest.mark.asyncio
    async def test_kills_process(self, mock_update, mock_context):
        mock_proc = MagicMock()
        mock_proc.returncode = None
        mock_proc.kill = MagicMock()

        with patch("koda.handlers.commands.active_processes", {111: mock_proc}):
            await cmd_cancel(mock_update, mock_context)

        mock_proc.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_specific_task_uses_runtime_controller(self, mock_update, mock_context):
        task_id = 77
        mock_context.args = [str(task_id)]
        controller = MagicMock()
        controller.cancel_task = AsyncMock(
            return_value={
                "ok": True,
                "action": "cancelled",
                "task_id": task_id,
                "env_id": None,
                "final_phase": "cancelled_retained",
            }
        )

        with (
            patch("koda.handlers.commands.get_task_info", return_value=SimpleNamespace(user_id=111)),
            patch("koda.handlers.commands.get_task", return_value=(task_id, 111)),
            patch("koda.services.runtime.get_runtime_controller", return_value=controller),
        ):
            await cmd_cancel(mock_update, mock_context)

        controller.cancel_task.assert_awaited_once()
        call_text = mock_update.message.reply_text.call_args[0][0]
        assert "cancelled_retained" in call_text
