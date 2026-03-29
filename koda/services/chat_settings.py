"""Natural-language agent-local settings handling for Telegram chat."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from koda.provider_models import MODEL_FUNCTION_IDS
from koda.services.agent_settings import (
    get_agent_runtime_settings,
    set_agent_functional_default,
    set_agent_general_model,
    set_agent_general_provider,
    set_agent_voice_default,
)
from koda.services.kokoro_manager import kokoro_voice_metadata, list_kokoro_voices
from koda.utils.command_helpers import (
    normalize_feature_provider,
    normalize_provider,
    sync_user_data_with_runtime_settings,
)
from koda.utils.tts import AVAILABLE_VOICES

_SETTING_VERBS = (
    "mude",
    "troque",
    "altere",
    "configure",
    "defina",
    "use",
    "usar",
    "ative",
    "desative",
    "quero usar",
    "quero que use",
    "set",
    "change",
    "switch",
    "configure",
    "set up",
)

_FUNCTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "general": ("modelo geral", "modelo padrao", "modelo padrão", "modelo principal", "general model"),
    "image": ("imagem", "image"),
    "video": ("video", "vídeo", "video model"),
    "audio": ("audio", "áudio", "tts"),
    "transcription": ("transcricao", "transcrição", "transcription", "stt"),
    "music": ("musica", "música", "music"),
}

_MODE_KEYWORDS = {
    "supervisionado": "supervised",
    "supervised": "supervised",
    "autonomo": "autonomous",
    "autônomo": "autonomous",
    "autonomous": "autonomous",
}


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_only.lower().split())


def _contains_setting_verb(text: str) -> bool:
    return any(verb in text for verb in _SETTING_VERBS)


def _word_match(text: str, token: str) -> bool:
    escaped = re.escape(_normalize_text(token))
    return re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", text) is not None


def _feature_option_map(settings: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    payload = settings.get("selectable_function_options", {})
    if not isinstance(payload, dict):
        return {}
    option_map: dict[str, list[dict[str, Any]]] = {}
    for function_id, items in payload.items():
        if not isinstance(items, list):
            continue
        option_map[str(function_id)] = [dict(item) for item in items if isinstance(item, dict)]
    return option_map


def _general_provider_ids(settings: dict[str, Any]) -> list[str]:
    option_map = _feature_option_map(settings)
    seen: list[str] = []
    for item in option_map.get("general", []):
        provider_id = normalize_provider(str(item.get("provider_id") or ""))
        if provider_id and provider_id not in seen:
            seen.append(provider_id)
    return seen


def _find_provider_in_text(text: str, candidates: list[str], *, feature: bool = False) -> str | None:
    alias_map = {
        "anthropic": "claude",
        "claude": "claude",
        "openai": "codex",
        "codex": "codex",
        "google": "gemini",
        "gemini": "gemini",
        "ollama": "ollama",
        "elevenlabs": "elevenlabs",
        "kokoro": "kokoro",
        "whisper": "whispercpp",
        "whispercpp": "whispercpp",
        "whisper-cpp": "whispercpp",
        "sora": "codex",
    }
    normalized_candidates = {
        normalize_feature_provider(item) if feature else normalize_provider(item)
        for item in candidates
        if str(item).strip()
    }
    for raw_token, resolved in sorted(alias_map.items(), key=lambda item: len(item[0]), reverse=True):
        normalized = normalize_feature_provider(resolved) if feature else normalize_provider(resolved)
        if normalized in normalized_candidates and _word_match(text, raw_token):
            return normalized
    return None


def _find_model_in_text(text: str, options: list[dict[str, Any]]) -> tuple[str, str | None] | tuple[None, None]:
    candidates: list[tuple[str, str]] = []
    for item in options:
        model_id = str(item.get("model_id") or "").strip()
        provider_id = normalize_feature_provider(str(item.get("provider_id") or ""))
        if not model_id:
            continue
        candidates.append((model_id, provider_id))
    for model_id, provider_id in sorted(candidates, key=lambda item: len(item[0]), reverse=True):
        if _word_match(text, model_id):
            return model_id, provider_id
    return None, None


def _find_feature_from_text(text: str) -> str | None:
    for function_id in MODEL_FUNCTION_IDS:
        for keyword in _FUNCTION_KEYWORDS.get(function_id, ()):
            if keyword in text:
                return function_id
    return None


def _find_voice_in_text(text: str) -> tuple[str, str, str] | None:
    voice_matches: dict[str, tuple[str, str, str]] = {}
    label_hits: dict[str, list[tuple[str, str, str]]] = {}

    for voice_id, config in AVAILABLE_VOICES.items():
        item = (voice_id, str(config.label), "")
        voice_matches[_normalize_text(voice_id)] = item
        label_hits.setdefault(_normalize_text(config.label), []).append(item)

    for voice_item in list_kokoro_voices():
        voice_id = str(voice_item.get("voice_id") or "").strip()
        if not voice_id:
            continue
        language_id = str(voice_item.get("language_id") or "").strip().lower()
        label = str(voice_item.get("name") or voice_id)
        payload = (voice_id, label, language_id)
        voice_matches[_normalize_text(voice_id)] = payload
        label_hits.setdefault(_normalize_text(label), []).append(payload)

    for normalized_id, payload in sorted(voice_matches.items(), key=lambda item: len(item[0]), reverse=True):
        if _word_match(text, normalized_id):
            return payload

    for normalized_label, payloads in sorted(label_hits.items(), key=lambda item: len(item[0]), reverse=True):
        if len(payloads) == 1 and _word_match(text, normalized_label):
            return payloads[0]
    return None


def _apply_mode_change(text: str, user_data: dict[str, Any]) -> str | None:
    if "modo" not in text and "mode" not in text:
        return None
    for keyword, resolved in _MODE_KEYWORDS.items():
        if keyword in text:
            user_data["agent_mode"] = resolved
            return f"Modo deste AGENT atualizado para <code>{resolved}</code>."
    return None


def _apply_provider_change(text: str, user_data: dict[str, Any], settings: dict[str, Any]) -> str | None:
    provider_id = _find_provider_in_text(text, _general_provider_ids(settings))
    if not provider_id:
        return None
    if "provider" not in text and "provedor" not in text:
        if "modelo" in text or "model" in text:
            return None
        if _find_feature_from_text(text):
            return None
    updated = set_agent_general_provider(provider_id)
    sync_user_data_with_runtime_settings(user_data, updated)
    return (
        f"Provider deste AGENT atualizado para <code>{provider_id}</code>.\n"
        f"Modelo geral: <code>{user_data.get('model')}</code>."
    )


def _apply_general_model_change(text: str, user_data: dict[str, Any], settings: dict[str, Any]) -> str | None:
    if "modelo" not in text and "model" not in text:
        return None
    option_map = _feature_option_map(settings)
    general_options = option_map.get("general", [])
    model_id, inferred_provider = _find_model_in_text(text, general_options)
    if not model_id:
        return None
    provider_id = _find_provider_in_text(text, _general_provider_ids(settings))
    provider_id = provider_id or inferred_provider or ""
    if not provider_id:
        matches = {
            normalize_provider(str(item.get("provider_id") or ""))
            for item in general_options
            if str(item.get("model_id") or "").strip() == model_id
        }
        if len(matches) == 1:
            provider_id = next(iter(matches))
    if not provider_id:
        return None
    updated = set_agent_general_model(provider_id, model_id)
    sync_user_data_with_runtime_settings(user_data, updated)
    return f"Modelo geral deste AGENT atualizado para <code>{provider_id}</code> / <code>{model_id}</code>."


def _apply_feature_model_change(text: str, user_data: dict[str, Any], settings: dict[str, Any]) -> str | None:
    function_id = _find_feature_from_text(text)
    if not function_id or function_id == "general":
        return None
    option_map = _feature_option_map(settings)
    options = option_map.get(function_id, [])
    if not options:
        return None

    model_id, inferred_provider = _find_model_in_text(text, options)
    provider_id = _find_provider_in_text(
        text,
        [str(item.get("provider_id") or "") for item in options],
        feature=True,
    )
    provider_id = provider_id or inferred_provider

    if provider_id and not model_id:
        matching_options = [
            item for item in options if normalize_feature_provider(str(item.get("provider_id") or "")) == provider_id
        ]
        if len(matching_options) == 1:
            model_id = str(matching_options[0].get("model_id") or "").strip()

    if not provider_id or not model_id:
        return None

    updated = set_agent_functional_default(function_id, provider_id, model_id)
    sync_user_data_with_runtime_settings(user_data, updated)
    return (
        f"Modelo padrao deste AGENT para <code>{function_id}</code> atualizado para "
        f"<code>{provider_id}</code> / <code>{model_id}</code>."
    )


def _apply_voice_change(text: str, user_data: dict[str, Any]) -> str | None:
    if "voz" not in text and "voice" not in text:
        return None
    voice_payload = _find_voice_in_text(text)
    if not voice_payload:
        return None
    voice_id, voice_label, voice_language = voice_payload
    if not voice_language:
        metadata = kokoro_voice_metadata(voice_id)
        voice_language = str((metadata or {}).get("language_id") or "")
    updated = set_agent_voice_default(voice_id, voice_label=voice_label, voice_language=voice_language)
    sync_user_data_with_runtime_settings(user_data, updated)
    return f"Voz deste AGENT atualizada para <code>{voice_id}</code> ({voice_label})."


def maybe_apply_agent_local_settings_from_chat(query_text: str, user_data: dict[str, Any]) -> str | None:
    """Handle explicit agent-local settings requests expressed in natural language.

    This only mutates the active agent-local runtime settings. It never changes
    global/system provider connections or global defaults.
    """

    normalized_text = _normalize_text(query_text)
    if not normalized_text or not _contains_setting_verb(normalized_text):
        return None

    mode_message = _apply_mode_change(normalized_text, user_data)
    if mode_message:
        return mode_message

    settings = get_agent_runtime_settings(force_refresh=True)
    if settings is None:
        return None

    voice_message = _apply_voice_change(normalized_text, user_data)
    if voice_message:
        return voice_message

    feature_message = _apply_feature_model_change(normalized_text, user_data, settings)
    if feature_message:
        return feature_message

    provider_message = _apply_provider_change(normalized_text, user_data, settings)
    if provider_message:
        return provider_message

    model_message = _apply_general_model_change(normalized_text, user_data, settings)
    if model_message:
        return model_message

    return None
