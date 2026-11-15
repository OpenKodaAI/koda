"""Tests for natural-language AGENT-local settings changes."""

from __future__ import annotations

from unittest.mock import patch

from koda.services.chat_settings import _find_provider_in_text, maybe_apply_agent_local_settings_from_chat


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
    assert "Agent's general model updated" in str(message)


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
    assert "Agent default for" in str(message)


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
    assert "Agent voice updated" in str(message)


def test_natural_language_mode_change_is_agent_local_only() -> None:
    user_data: dict[str, object] = {}
    message = maybe_apply_agent_local_settings_from_chat("ative modo supervisionado", user_data)
    assert user_data["agent_mode"] == "supervised"
    assert "Modo deste AGENT atualizado" in str(message)


def test_non_setting_message_is_ignored() -> None:
    user_data: dict[str, object] = {}
    message = maybe_apply_agent_local_settings_from_chat("qual o melhor modelo para mim?", user_data)
    assert message is None


def test_ordinary_message_with_a_setting_verb_logs_no_unknown_provider() -> None:
    # M6-E3-T2 (D-157): the unknown_provider_id warning must stay a signal. Scanning the text for a
    # general provider used to normalise elevenlabs, kokoro and whispercpp as general providers and warn.
    user_data: dict[str, object] = {}
    with (
        patch("koda.services.chat_settings.get_agent_runtime_settings", return_value=_runtime_settings()),
        patch("koda.utils.command_helpers.log") as mock_log,
    ):
        message = maybe_apply_agent_local_settings_from_chat("can you use the tests", user_data)
        assert _find_provider_in_text("please use the new thing", ["claude", "codex"]) is None

    assert message is None
    mock_log.warning.assert_not_called()


def test_non_general_provider_name_does_not_select_the_default_general_provider() -> None:
    # Before, "elevenlabs" resolved to the default general provider when the text named it.
    with patch("koda.utils.command_helpers.DEFAULT_PROVIDER", "claude"):
        assert _find_provider_in_text("mude o provider para elevenlabs", ["claude", "codex"]) is None
        assert _find_provider_in_text("mude o provider para openai", ["claude", "codex"]) == "codex"


def test_failed_publish_is_reported_instead_of_a_model_change() -> None:
    # M6-E3-T2 (D-068): when the agent cannot be published the chat says so, not "updated".
    user_data: dict[str, object] = {}
    with (
        patch("koda.services.chat_settings.get_agent_runtime_settings", return_value=_runtime_settings()),
        patch(
            "koda.services.chat_settings.set_agent_general_model",
            side_effect=ValueError("A publicacao do agent falhou <detalhe>."),
        ),
    ):
        message = maybe_apply_agent_local_settings_from_chat("use gpt-5.2 como modelo geral", user_data)

    assert message == "A publicacao do agent falhou &lt;detalhe&gt;."
    assert "model" not in user_data


def test_feature_only_provider_without_a_feature_is_not_a_general_provider_change() -> None:
    # D-296: "switch to kokoro" named no feature, and kokoro resolved to the default general provider.
    # Nothing changes, and the reply asks for the feature instead of leaving the answer to the agent.
    user_data: dict[str, object] = {}
    with (
        patch("koda.utils.command_helpers.DEFAULT_PROVIDER", "claude"),
        patch("koda.services.chat_settings.get_agent_runtime_settings", return_value=_runtime_settings()),
        patch("koda.services.chat_settings.set_agent_general_provider") as mock_provider,
        patch("koda.services.chat_settings.set_agent_general_model") as mock_model,
        patch("koda.services.chat_settings.set_agent_functional_default") as mock_feature,
    ):
        message = maybe_apply_agent_local_settings_from_chat("switch to kokoro", user_data)

    assert message == (
        "Nothing changed: <code>kokoro</code> is a provider for <code>audio</code>, not the general provider. "
        "Name the feature, for example: <code>switch audio to kokoro</code>."
    )
    assert user_data == {}
    mock_provider.assert_not_called()
    mock_model.assert_not_called()
    mock_feature.assert_not_called()


def test_feature_only_provider_with_its_feature_changes_that_feature() -> None:
    # D-296: naming the feature routes the feature-only provider to that feature's setting.
    user_data: dict[str, object] = {}
    with (
        patch("koda.utils.command_helpers.DEFAULT_PROVIDER", "claude"),
        patch("koda.services.chat_settings.get_agent_runtime_settings", return_value=_runtime_settings()),
        patch("koda.services.chat_settings.set_agent_general_provider") as mock_provider,
        patch(
            "koda.services.chat_settings.set_agent_functional_default",
            return_value=_runtime_settings(),
        ) as mock_feature,
    ):
        message = maybe_apply_agent_local_settings_from_chat("switch tts to kokoro", user_data)

    mock_feature.assert_called_once_with("audio", "kokoro", "kokoro-v1")
    mock_provider.assert_not_called()
    assert "Agent default for <code>audio</code>" in str(message)
