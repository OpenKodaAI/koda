"""Additional operational coverage for callback handlers."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from koda.handlers.callbacks import (
    callback_agent_cmd_approval,
    callback_bookmark,
    callback_dbenv,
    callback_feature_model_function,
    callback_feature_model_model,
    callback_feature_model_provider,
    callback_memory_forget,
    callback_model,
    callback_provider,
    callback_setdir,
    callback_settings_featuremodel,
    callback_settings_home,
    callback_settings_mode,
    callback_settings_model,
    callback_settings_newsession,
    callback_settings_provider,
    callback_settings_voice,
    callback_voice_elevenlabs,
)
from koda.utils.approval import _PENDING_AGENT_CMD_OPS
from koda.utils.command_helpers import init_user_data


def _build_callback_update(mock_update, data: str):
    query = AsyncMock()
    query.data = data
    query.message.text = "Response body\n\n———\nfooter"
    query.message.caption = None
    mock_update.callback_query = query
    return mock_update, query


def _runtime_settings(
    *,
    provider: str = "codex",
    model: str = "gpt-5.4",
    function_id: str = "general",
) -> dict[str, object]:
    return {
        "default_provider": provider,
        "general_model": model,
        "default_models_by_provider": {provider: model},
        "functional_defaults": {
            "general": {"provider_id": provider, "model_id": model},
            function_id: {"provider_id": provider, "model_id": model},
        },
        "transcription_provider": "whispercpp",
        "transcription_model": "whisper-cpp-local",
        "audio_provider": "kokoro",
        "audio_model": "kokoro-v1",
        "tts_voice": "pf_dora",
        "tts_voice_label": "Dora",
        "tts_voice_language": "pt-br",
        "selectable_function_options": {
            "general": [
                {"provider_id": provider, "model_id": model, "provider_title": provider.title(), "title": model}
            ],
            function_id: [
                {"provider_id": provider, "model_id": model, "provider_title": provider.title(), "title": model}
            ],
        },
    }


class TestCallbackCoverage:
    @pytest.mark.asyncio
    async def test_settings_callbacks_render_hub_and_submenus(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)

        update, query = _build_callback_update(mock_update, "settings:home")
        await callback_settings_home(update, mock_context)
        assert "Ajustes deste AGENT" in query.edit_message_text.call_args.args[0]

        update, query = _build_callback_update(mock_update, "settings:provider")
        await callback_settings_provider(update, mock_context)
        assert "Selecione o provider padrao" in query.edit_message_text.call_args.args[0]

        update, query = _build_callback_update(mock_update, "settings:model")
        await callback_settings_model(update, mock_context)
        assert "Selecione o modelo geral" in query.edit_message_text.call_args.args[0]

        update, query = _build_callback_update(mock_update, "settings:mode")
        await callback_settings_mode(update, mock_context)
        assert "Selecione o modo deste AGENT" in query.edit_message_text.call_args.args[0]

        update, query = _build_callback_update(mock_update, "settings:voice")
        await callback_settings_voice(update, mock_context)
        assert "Voz deste AGENT" in query.edit_message_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_settings_featuremodel_and_newsession_callbacks(self, mock_update, mock_context):
        settings = _runtime_settings(provider="codex", model="gpt-5.4", function_id="image")
        update, query = _build_callback_update(mock_update, "settings:featuremodel")
        with patch("koda.handlers.callbacks.get_agent_runtime_settings", return_value=settings):
            await callback_settings_featuremodel(update, mock_context)
        assert "Selecione a funcionalidade" in query.edit_message_text.call_args.args[0]

        mock_context.user_data["session_id"] = "sess-123"
        mock_context.user_data["provider_sessions"] = {"codex": "sess-123"}
        update, query = _build_callback_update(mock_update, "settings:newsession")
        await callback_settings_newsession(update, mock_context)
        assert mock_context.user_data["session_id"].startswith("session-")
        assert mock_context.user_data["session_id"] != "sess-123"
        assert mock_context.user_data["provider_sessions"] == {}

    @pytest.mark.asyncio
    async def test_callback_setdir_handles_success_and_missing_directory(self, mock_update, mock_context, tmp_path):
        update, query = _build_callback_update(mock_update, f"setdir:{tmp_path}")
        await callback_setdir(update, mock_context)
        assert mock_context.user_data["work_dir"] == str(tmp_path)

        update, query = _build_callback_update(mock_update, "setdir:/definitely/missing")
        await callback_setdir(update, mock_context)
        assert "Directory not found" in query.edit_message_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_callback_model_auto_and_manual_model_selection(self, mock_update, mock_context):
        update, query = _build_callback_update(mock_update, "model:auto")
        await callback_model(update, mock_context)
        assert mock_context.user_data["auto_model"] is True

        update, query = _build_callback_update(mock_update, "model:claude-sonnet-4-6")
        await callback_model(update, mock_context)
        assert mock_context.user_data["auto_model"] is False
        assert "Model set to" in query.edit_message_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_callback_provider_and_bookmark_paths(self, mock_update, mock_context):
        update, query = _build_callback_update(mock_update, "provider:codex")
        with patch(
            "koda.handlers.callbacks.set_agent_general_provider",
            return_value=_runtime_settings(provider="codex", model="gpt-5.4"),
        ) as mock_persist:
            await callback_provider(update, mock_context)
        mock_persist.assert_called_once_with("codex")
        assert mock_context.user_data["provider"] == "codex"

        update, query = _build_callback_update(mock_update, "bookmark:any")
        with patch("koda.handlers.callbacks.add_bookmark", return_value=77):
            await callback_bookmark(update, mock_context)
        assert "Bookmarked! (#77)" in query.answer.call_args.args[0]

        update, query = _build_callback_update(mock_update, "bookmark:any")
        query.message.text = ""
        await callback_bookmark(update, mock_context)
        assert "Nothing to bookmark." in query.answer.call_args.args[0]

    @pytest.mark.asyncio
    async def test_callback_provider_and_model_do_not_mutate_when_persist_fails(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        update, query = _build_callback_update(mock_update, "provider:codex")
        original_provider = mock_context.user_data["provider"]
        original_model = mock_context.user_data["model"]
        with patch("koda.handlers.callbacks.set_agent_general_provider", side_effect=ValueError("boom")):
            await callback_provider(update, mock_context)
        assert mock_context.user_data["provider"] == original_provider
        assert mock_context.user_data["model"] == original_model

        mock_context.user_data["provider"] = "codex"
        mock_context.user_data["model"] = "o3"
        mock_context.user_data["manual_models_by_provider"]["codex"] = "o3"
        mock_context.user_data["available_models_by_provider"] = {"codex": ["o3", "gpt-5.4"]}
        update, query = _build_callback_update(mock_update, "model:gpt-5.4")
        with patch("koda.handlers.callbacks.set_agent_general_model", side_effect=ValueError("boom")):
            await callback_model(update, mock_context)
        assert mock_context.user_data["model"] == "o3"

    @pytest.mark.asyncio
    async def test_callback_dbenv_and_voice_selection(self, mock_update, mock_context):
        update, query = _build_callback_update(mock_update, "dbenv:prod")
        await callback_dbenv(update, mock_context)
        assert "mcp" in query.edit_message_text.call_args.args[0].lower()

        update, query = _build_callback_update(mock_update, "voiceel:voice-123:Maria")
        with patch(
            "koda.handlers.callbacks.set_agent_voice_default",
            return_value={
                **_runtime_settings(provider="codex", model="gpt-5.4"),
                "tts_voice": "voice-123",
                "tts_voice_label": "Maria",
                "tts_voice_language": "pt",
            },
        ) as mock_persist:
            await callback_voice_elevenlabs(update, mock_context)
        mock_persist.assert_called_once_with("voice-123", voice_label="Maria")
        assert mock_context.user_data["tts_voice"] == "voice-123"
        assert "Maria" in query.edit_message_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_callback_voice_selection_does_not_mutate_when_persist_fails(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        original_voice = mock_context.user_data["tts_voice"]
        update, query = _build_callback_update(mock_update, "voiceel:voice-123:Maria")
        with patch("koda.handlers.callbacks.set_agent_voice_default", side_effect=ValueError("boom")):
            await callback_voice_elevenlabs(update, mock_context)
        assert mock_context.user_data["tts_voice"] == original_voice

    @pytest.mark.asyncio
    async def test_callback_feature_model_flow(self, mock_update, mock_context):
        image_settings = _runtime_settings(provider="codex", model="gpt-5.4", function_id="image")
        image_settings["selectable_function_options"]["image"] = [
            {
                "provider_id": "codex",
                "model_id": "gpt-image-1.5",
                "provider_title": "OpenAI",
                "title": "GPT Image 1.5",
            },
            {
                "provider_id": "gemini",
                "model_id": "imagen-4.0-generate-001",
                "provider_title": "Google",
                "title": "Imagen 4 Standard",
            },
        ]
        image_settings["functional_defaults"]["image"] = {"provider_id": "codex", "model_id": "gpt-image-1.5"}

        update, query = _build_callback_update(mock_update, "fmodelf:image")
        with patch("koda.handlers.callbacks.get_agent_runtime_settings", return_value=image_settings):
            await callback_feature_model_function(update, mock_context)
        assert "Selecione o provider" in query.edit_message_text.call_args.args[0]

        update, query = _build_callback_update(mock_update, "fmodelp:image:codex")
        with patch("koda.handlers.callbacks.get_agent_runtime_settings", return_value=image_settings):
            await callback_feature_model_provider(update, mock_context)
        assert "Selecione o modelo padrao" in query.edit_message_text.call_args.args[0]
        token = next(iter(mock_context.user_data["_feature_model_tokens"]))

        update, query = _build_callback_update(mock_update, f"fmodelm:{token}")
        updated_settings = _runtime_settings(provider="codex", model="gpt-5.4", function_id="image")
        updated_settings["functional_defaults"]["image"] = {"provider_id": "codex", "model_id": "gpt-image-1.5"}
        with patch(
            "koda.handlers.callbacks.set_agent_functional_default",
            return_value=updated_settings,
        ) as mock_set:
            await callback_feature_model_model(update, mock_context)
        mock_set.assert_called_once_with("image", "codex", "gpt-image-1.5")
        assert "Modelo padrao do AGENT atualizado" in query.edit_message_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_callback_memory_forget_cancel_and_missing_store(self, mock_update, mock_context):
        update, query = _build_callback_update(mock_update, "memory_forget:cancel")
        await callback_memory_forget(update, mock_context)
        assert "Cancelled" in query.edit_message_text.call_args.args[0]

        update, query = _build_callback_update(mock_update, "memory_forget:all")
        manager = type("Manager", (), {"store": None})()
        with patch("koda.memory.get_memory_manager", return_value=manager):
            await callback_memory_forget(update, mock_context)
        assert "not initialized" in query.edit_message_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_callback_agent_cmd_approval_timeout_and_wrong_user(self, mock_update, mock_context):
        update, query = _build_callback_update(mock_update, "acmd:ok:op-wrong-user")
        _PENDING_AGENT_CMD_OPS["op-wrong-user"] = {
            "user_id": 222,
            "timestamp": time.time(),
            "event": asyncio.Event(),
            "decision": None,
            "description": "write file",
        }
        await callback_agent_cmd_approval(update, mock_context)
        assert "Somente quem iniciou" in query.answer.call_args.args[0]
        _PENDING_AGENT_CMD_OPS.pop("op-wrong-user", None)

        update, query = _build_callback_update(mock_update, "acmd:ok:op-timeout")
        _PENDING_AGENT_CMD_OPS["op-timeout"] = {
            "user_id": 111,
            "timestamp": time.time() - 9999,
            "event": asyncio.Event(),
            "decision": None,
            "description": "write file",
        }
        await callback_agent_cmd_approval(update, mock_context)
        assert "expirada ou invalida" in query.edit_message_text.call_args.args[0].lower()
        _PENDING_AGENT_CMD_OPS.pop("op-timeout", None)
