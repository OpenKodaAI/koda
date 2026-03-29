"""Tests for natural-language AGENT-local settings changes."""

from __future__ import annotations

from unittest.mock import patch

from koda.services.chat_settings import maybe_apply_agent_local_settings_from_chat


def _runtime_settings() -> dict[str, object]:
    return {
        "agent_id": "AGENT_A",
        "default_provider": "codex",
        "general_model": "gpt-5.2",
        "default_models_by_provider": {
            "codex": "gpt-5.2",
            "claude": "claude-sonnet-4-6",
            "kokoro": "kokoro-v1",
        },
        "functional_defaults": {
            "general": {"provider_id": "codex", "model_id": "gpt-5.2"},
            "image": {"provider_id": "codex", "model_id": "gpt-image-1.5"},
            "audio": {"provider_id": "kokoro", "model_id": "kokoro-v1"},
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
                {
                    "provider_id": "codex",
                    "model_id": "gpt-5.2",
                    "provider_title": "OpenAI",
                    "title": "GPT-5.2",
                },
                {
                    "provider_id": "claude",
                    "model_id": "claude-sonnet-4-6",
                    "provider_title": "Anthropic",
                    "title": "Claude Sonnet 4.6",
                },
            ],
            "image": [
                {
                    "provider_id": "codex",
                    "model_id": "gpt-image-1.5",
                    "provider_title": "OpenAI",
                    "title": "GPT Image 1.5",
                }
            ],
            "audio": [
                {
                    "provider_id": "kokoro",
                    "model_id": "kokoro-v1",
                    "provider_title": "Kokoro",
                    "title": "Kokoro v1",
                }
            ],
        },
    }


def test_natural_language_provider_change_uses_agent_local_provider_setter() -> None:
    user_data: dict[str, object] = {}
    with (
        patch("koda.services.chat_settings.get_agent_runtime_settings", return_value=_runtime_settings()),
        patch(
            "koda.services.chat_settings.set_agent_general_provider",
            return_value=_runtime_settings(),
        ) as mock_setter,
    ):
        message = maybe_apply_agent_local_settings_from_chat("mude o provider para OpenAI", user_data)

    mock_setter.assert_called_once_with("codex")
    assert "Provider deste AGENT atualizado" in str(message)


def test_natural_language_general_model_change_uses_agent_local_model_setter() -> None:
    user_data: dict[str, object] = {}
    with (
        patch("koda.services.chat_settings.get_agent_runtime_settings", return_value=_runtime_settings()),
        patch(
            "koda.services.chat_settings.set_agent_general_model",
            return_value=_runtime_settings(),
        ) as mock_setter,
    ):
        message = maybe_apply_agent_local_settings_from_chat("use gpt-5.2 como modelo geral", user_data)

    mock_setter.assert_called_once_with("codex", "gpt-5.2")
    assert "Modelo geral deste AGENT atualizado" in str(message)


def test_natural_language_feature_model_change_uses_agent_local_feature_setter() -> None:
    user_data: dict[str, object] = {}
    with (
        patch("koda.services.chat_settings.get_agent_runtime_settings", return_value=_runtime_settings()),
        patch(
            "koda.services.chat_settings.set_agent_functional_default",
            return_value=_runtime_settings(),
        ) as mock_setter,
    ):
        message = maybe_apply_agent_local_settings_from_chat("para imagem use codex gpt-image-1.5", user_data)

    mock_setter.assert_called_once_with("image", "codex", "gpt-image-1.5")
    assert "Modelo padrao deste AGENT para" in str(message)


def test_natural_language_voice_change_uses_agent_local_voice_setter() -> None:
    user_data: dict[str, object] = {}
    with (
        patch("koda.services.chat_settings.get_agent_runtime_settings", return_value=_runtime_settings()),
        patch(
            "koda.services.chat_settings.list_kokoro_voices",
            return_value=[{"voice_id": "pm_alex", "name": "Alex", "language_id": "pt-br"}],
        ),
        patch(
            "koda.services.chat_settings.set_agent_voice_default",
            return_value=_runtime_settings(),
        ) as mock_setter,
    ):
        message = maybe_apply_agent_local_settings_from_chat("mude a voz para pm_alex", user_data)

    mock_setter.assert_called_once_with("pm_alex", voice_label="Alex", voice_language="pt-br")
    assert "Voz deste AGENT atualizada" in str(message)


def test_natural_language_mode_change_is_agent_local_only() -> None:
    user_data: dict[str, object] = {}
    message = maybe_apply_agent_local_settings_from_chat("ative modo supervisionado", user_data)
    assert user_data["agent_mode"] == "supervised"
    assert "Modo deste AGENT atualizado" in str(message)


def test_non_setting_message_is_ignored() -> None:
    user_data: dict[str, object] = {}
    message = maybe_apply_agent_local_settings_from_chat("qual o melhor modelo para mim?", user_data)
    assert message is None
