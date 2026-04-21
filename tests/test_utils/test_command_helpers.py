"""Tests for command_helpers utility."""

from unittest.mock import patch

import pytest

from koda.utils.command_helpers import (
    authorized,
    authorized_with_rate_limit,
    init_user_data,
    normalize_feature_provider,
    normalize_provider,
)


def test_init_user_data_sets_defaults():
    data = {}
    init_user_data(data)
    assert data["session_id"] is None
    assert data["work_dir"] is not None
    assert data["model"] is not None
    assert data["total_cost"] == 0.0
    assert data["query_count"] == 0
    assert data["system_prompt"] is None
    assert data["last_query"] is None
    assert data["auto_model"] is False
    assert data["agent_mode"] == "autonomous"
    assert data["audio_response"] is False
    assert data["tts_voice"] is not None


def test_init_user_data_preserves_existing():
    data = {"work_dir": "/custom", "model": "claude-opus-4-6"}
    init_user_data(data)
    assert data["work_dir"] == "/custom"
    assert data["model"] == "claude-opus-4-6"


def test_init_user_data_loads_agent_runtime_defaults():
    settings = {
        "default_provider": "codex",
        "general_model": "gpt-5.4",
        "default_models_by_provider": {"codex": "gpt-5.4"},
        "functional_defaults": {
            "general": {"provider_id": "codex", "model_id": "gpt-5.4"},
            "transcription": {"provider_id": "codex", "model_id": "whisper-1"},
        },
        "transcription_provider": "codex",
        "transcription_model": "whisper-1",
        "audio_provider": "kokoro",
        "audio_model": "kokoro-v1",
        "tts_voice": "pm_alex",
        "tts_voice_label": "Alex",
        "tts_voice_language": "pt-br",
        "selectable_function_options": {
            "general": [
                {"provider_id": "codex", "model_id": "gpt-5.4"},
                {"provider_id": "codex", "model_id": "o3"},
            ]
        },
    }
    data = {}
    with patch("koda.services.agent_settings.get_agent_runtime_settings", return_value=settings):
        init_user_data(data)

    assert data["provider"] == "codex"
    assert data["model"] == "gpt-5.4"
    assert data["transcription_provider"] == "codex"
    assert data["transcription_model"] == "whisper-1"
    assert data["tts_voice"] == "pm_alex"
    assert data["tts_voice_label"] == "Alex"
    assert data["tts_voice_language"] == "pt-br"
    assert data["available_general_providers"] == ["codex"]
    assert data["available_models_by_provider"]["codex"] == ["gpt-5.4", "o3"]


def test_init_user_data_refreshes_runtime_backed_fields():
    settings = {
        "default_provider": "codex",
        "general_model": "o3",
        "default_models_by_provider": {"codex": "o3"},
        "functional_defaults": {
            "general": {"provider_id": "codex", "model_id": "o3"},
            "audio": {"provider_id": "kokoro", "model_id": "kokoro-v1"},
        },
        "transcription_provider": "codex",
        "transcription_model": "gpt-4o-transcribe",
        "audio_provider": "kokoro",
        "audio_model": "kokoro-v1",
        "tts_voice": "pf_dora",
        "tts_voice_label": "Dora",
        "tts_voice_language": "pt-br",
        "selectable_function_options": {
            "general": [
                {"provider_id": "codex", "model_id": "o3"},
            ]
        },
    }
    data = {
        "provider": "claude",
        "model": "claude-sonnet-4-6",
        "transcription_provider": "whispercpp",
        "transcription_model": "whisper-cpp-local",
        "tts_voice": "bill",
        "tts_voice_label": "Bill",
        "tts_voice_language": "en",
        "functional_defaults": {"general": {"provider_id": "claude", "model_id": "claude-sonnet-4-6"}},
    }
    with patch("koda.services.agent_settings.get_agent_runtime_settings", return_value=settings):
        init_user_data(data)

    assert data["provider"] == "codex"
    assert data["model"] == "o3"
    assert data["transcription_provider"] == "codex"
    assert data["transcription_model"] == "gpt-4o-transcribe"
    assert data["tts_voice"] == "pf_dora"
    assert data["tts_voice_label"] == "Dora"
    assert data["tts_voice_language"] == "pt-br"


def test_normalize_provider_accepts_brand_aliases():
    assert normalize_provider("anthropic") == "claude"
    assert normalize_provider("openai") == "codex"
    assert normalize_provider("google") == "gemini"


def test_normalize_feature_provider_accepts_function_aliases():
    assert normalize_feature_provider("whisper") == "whispercpp"
    assert normalize_feature_provider("whisper-cpp") == "whispercpp"
    assert normalize_feature_provider("sora") == "codex"


@pytest.mark.asyncio
async def test_authorized_decorator_allows(mock_update, mock_context):
    @authorized
    async def handler(update, context):
        return "ok"

    result = await handler(mock_update, mock_context)
    assert result == "ok"
    # user_data should be initialized
    assert "work_dir" in mock_context.user_data


@pytest.mark.asyncio
async def test_authorized_decorator_rejects(unauthorized_update, mock_context):
    @authorized
    async def handler(update, context):
        return "ok"

    await handler(unauthorized_update, mock_context)
    unauthorized_update.message.reply_text.assert_called_once()


class TestAuthorizedWithRateLimit:
    @pytest.mark.asyncio
    async def test_rejects_unauthorized(self, unauthorized_update, mock_context):
        @authorized_with_rate_limit
        async def handler(update, context):
            return "ok"

        await handler(unauthorized_update, mock_context)
        unauthorized_update.message.reply_text.assert_called_with("Access denied.")

    @pytest.mark.asyncio
    async def test_rate_limited(self, mock_update, mock_context):
        @authorized_with_rate_limit
        async def handler(update, context):
            return "ok"

        with patch("koda.utils.command_helpers.acquire_rate_limit", return_value=False):
            result = await handler(mock_update, mock_context)
            assert result is None
            call_text = mock_update.message.reply_text.call_args[0][0]
            assert "Rate limited" in call_text

    @pytest.mark.asyncio
    async def test_success(self, mock_update, mock_context):
        @authorized_with_rate_limit
        async def handler(update, context):
            return "ok"

        with patch("koda.utils.command_helpers.acquire_rate_limit", return_value=True):
            result = await handler(mock_update, mock_context)
            assert result == "ok"
            assert "work_dir" in mock_context.user_data
