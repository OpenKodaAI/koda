"""Agent-local runtime settings derived from the control plane."""

from __future__ import annotations

import copy
import os
import time
from typing import Any

from koda.config import (
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    ELEVENLABS_DEFAULT_LANGUAGE,
    PROVIDER_DEFAULT_MODELS,
    TRANSCRIPTION_MODEL,
    TRANSCRIPTION_PROVIDER,
    TTS_DEFAULT_VOICE,
)
from koda.control_plane.agent_spec import normalize_model_policy
from koda.control_plane.manager import ControlPlaneManager
from koda.provider_models import MODEL_FUNCTION_IDS
from koda.services.kokoro_manager import (
    KOKORO_DEFAULT_LANGUAGE_ID,
    KOKORO_DEFAULT_VOICE_ID,
    kokoro_voice_metadata,
)
from koda.utils.tts import AVAILABLE_VOICES

_CACHE_TTL_SECONDS = 5.0
_SETTINGS_CACHE: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}


def _safe_json_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_json_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _nonempty_text(value: Any) -> str:
    return str(value or "").strip()


def _current_agent_id() -> str | None:
    raw = _nonempty_text(os.environ.get("AGENT_ID"))
    return raw.upper() if raw else None


def _cache_key(agent_id: str) -> tuple[str, str]:
    return agent_id.upper(), ""


def invalidate_agent_settings_cache(agent_id: str | None = None) -> None:
    if agent_id is None:
        _SETTINGS_CACHE.clear()
        return
    normalized = agent_id.upper()
    for key in list(_SETTINGS_CACHE):
        if key[0] == normalized:
            _SETTINGS_CACHE.pop(key, None)


def _general_settings(manager: ControlPlaneManager) -> dict[str, Any]:
    return _safe_json_object(manager.get_general_system_settings())


def _provider_connections_from_general_settings(settings: dict[str, Any]) -> dict[str, dict[str, Any]]:
    values = _safe_json_object(settings.get("values"))
    provider_connections = _safe_json_object(values.get("provider_connections"))
    return {str(key): _safe_json_object(value) for key, value in provider_connections.items()}


def _functional_catalog_from_general_settings(settings: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    catalogs = _safe_json_object(settings.get("catalogs"))
    payload = _safe_json_object(catalogs.get("functional_model_catalog"))
    return {
        function_id: [dict(_safe_json_object(item)) for item in _safe_json_list(items)]
        for function_id, items in payload.items()
    }


def _provider_catalog_map(provider_catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(provider_id): _safe_json_object(payload)
        for provider_id, payload in _safe_json_object(provider_catalog.get("providers")).items()
    }


def _default_model_for_provider(
    provider_id: str,
    *,
    policy: dict[str, Any],
    provider_catalog_map: dict[str, dict[str, Any]],
) -> str:
    default_models = _safe_json_object(policy.get("default_models"))
    provider_payload = _safe_json_object(provider_catalog_map.get(provider_id))
    return (
        _nonempty_text(default_models.get(provider_id))
        or _nonempty_text(provider_payload.get("default_model"))
        or PROVIDER_DEFAULT_MODELS.get(provider_id, DEFAULT_MODEL)
    )


def _voice_label_for_defaults(voice_id: str, *, provider_id: str) -> str:
    voice_config = AVAILABLE_VOICES.get(voice_id)
    if voice_config is not None:
        return str(voice_config.label)
    if provider_id == "kokoro":
        metadata = _safe_json_object(kokoro_voice_metadata(voice_id))
        if metadata:
            return _nonempty_text(metadata.get("name")) or voice_id
    return voice_id


def _effective_agent_runtime_settings(agent_id: str) -> dict[str, Any]:
    manager = ControlPlaneManager()
    snapshot = manager.build_draft_snapshot(agent_id)
    model_state = manager.get_model_policy(agent_id)
    policy = _safe_json_object(model_state.get("policy"))
    provider_catalog = _safe_json_object(model_state.get("provider_catalog"))
    provider_catalog_map = _provider_catalog_map(provider_catalog)
    providers_effective = _safe_json_object(manager.get_section(agent_id, "providers").get("effective"))
    general_settings = _general_settings(manager)
    provider_connections = _provider_connections_from_general_settings(general_settings)
    functional_catalog = _functional_catalog_from_general_settings(general_settings)
    provider_runtime_eligibility = _safe_json_object(snapshot.get("provider_runtime_eligibility"))

    default_provider = (
        _nonempty_text(
            _safe_json_object(_safe_json_object(policy.get("functional_defaults")).get("general")).get("provider_id")
        ).lower()
        or _nonempty_text(policy.get("default_provider")).lower()
        or _nonempty_text(provider_catalog.get("default_provider")).lower()
        or DEFAULT_PROVIDER
    )
    default_models = {
        provider_id: _default_model_for_provider(provider_id, policy=policy, provider_catalog_map=provider_catalog_map)
        for provider_id in provider_catalog_map
    }
    general_selection = _safe_json_object(_safe_json_object(policy.get("functional_defaults")).get("general"))
    general_model = _nonempty_text(general_selection.get("model_id")) or default_models.get(
        default_provider,
        DEFAULT_MODEL,
    )

    functional_defaults = {
        function_id: dict(_safe_json_object(selection))
        for function_id, selection in _safe_json_object(policy.get("functional_defaults")).items()
        if function_id in MODEL_FUNCTION_IDS
    }
    if "general" not in functional_defaults and default_provider:
        functional_defaults["general"] = {"provider_id": default_provider, "model_id": general_model}

    transcription_selection = _safe_json_object(functional_defaults.get("transcription"))
    transcription_provider = (
        _nonempty_text(transcription_selection.get("provider_id")).lower() or TRANSCRIPTION_PROVIDER
    )
    transcription_model = _nonempty_text(transcription_selection.get("model_id")) or TRANSCRIPTION_MODEL

    audio_selection = _safe_json_object(functional_defaults.get("audio"))
    audio_provider = _nonempty_text(audio_selection.get("provider_id")).lower() or "kokoro"
    audio_model = _nonempty_text(audio_selection.get("model_id")) or (
        _nonempty_text(providers_effective.get("elevenlabs_model")) if audio_provider == "elevenlabs" else "kokoro-v1"
    )
    if audio_provider == "elevenlabs":
        voice_id = (
            _nonempty_text(providers_effective.get("elevenlabs_default_voice"))
            or _nonempty_text(providers_effective.get("tts_default_voice"))
            or TTS_DEFAULT_VOICE
        )
        voice_language = (
            _nonempty_text(providers_effective.get("elevenlabs_default_language")) or ELEVENLABS_DEFAULT_LANGUAGE
        )
    else:
        voice_id = _nonempty_text(providers_effective.get("kokoro_default_voice")) or KOKORO_DEFAULT_VOICE_ID
        voice_language = (
            _nonempty_text(providers_effective.get("kokoro_default_language"))
            or _nonempty_text(_safe_json_object(kokoro_voice_metadata(voice_id)).get("language_id"))
            or KOKORO_DEFAULT_LANGUAGE_ID
        )
    voice_label = _voice_label_for_defaults(voice_id, provider_id=audio_provider)

    selectable_function_options: dict[str, list[dict[str, Any]]] = {}
    for function_id, items in functional_catalog.items():
        filtered: list[dict[str, Any]] = []
        for item in items:
            provider_id = _nonempty_text(item.get("provider_id")).lower()
            if not provider_id:
                continue
            provider_payload = _safe_json_object(provider_catalog_map.get(provider_id))
            if not provider_payload:
                continue
            if manager._provider_selectable_for_function(
                function_id,
                provider_id,
                provider_payload,
                provider_connections,
            ):
                filtered.append(item)
        selectable_function_options[function_id] = filtered

    return {
        "agent_id": agent_id,
        "policy": policy,
        "providers_section": providers_effective,
        "provider_catalog": provider_catalog,
        "provider_catalog_map": provider_catalog_map,
        "provider_connections": provider_connections,
        "provider_runtime_eligibility": provider_runtime_eligibility,
        "available_providers": list(provider_catalog.get("enabled_providers") or []),
        "available_models_by_provider": {
            provider_id: list(_safe_json_object(payload).get("available_models") or [])
            for provider_id, payload in provider_catalog_map.items()
        },
        "default_models_by_provider": default_models,
        "default_provider": default_provider,
        "general_model": general_model,
        "functional_defaults": functional_defaults,
        "transcription_provider": transcription_provider,
        "transcription_model": transcription_model,
        "audio_provider": audio_provider,
        "audio_model": audio_model,
        "tts_voice": voice_id,
        "tts_voice_label": voice_label,
        "tts_voice_language": voice_language,
        "selectable_function_options": selectable_function_options,
    }


def get_agent_runtime_settings(*, force_refresh: bool = False) -> dict[str, Any] | None:
    agent_id = _current_agent_id()
    if not agent_id:
        return None
    key = _cache_key(agent_id)
    now = time.monotonic()
    cached = _SETTINGS_CACHE.get(key)
    if cached and not force_refresh and (now - cached[0]) < _CACHE_TTL_SECONDS:
        return copy.deepcopy(cached[1])
    try:
        payload = _effective_agent_runtime_settings(agent_id)
    except Exception:
        return None
    _SETTINGS_CACHE[key] = (now, payload)
    return copy.deepcopy(payload)


def _ensure_function_option(
    settings: dict[str, Any],
    function_id: str,
    provider_id: str,
    model_id: str,
) -> dict[str, Any]:
    for item in settings.get("selectable_function_options", {}).get(function_id, []):
        payload = _safe_json_object(item)
        if (
            _nonempty_text(payload.get("provider_id")).lower() == provider_id.lower()
            and _nonempty_text(payload.get("model_id")) == model_id
        ):
            return payload
    raise ValueError(f"O modelo '{model_id}' do provider '{provider_id}' nao esta disponivel para {function_id}.")


def _current_local_providers_section(manager: ControlPlaneManager, agent_id: str) -> dict[str, Any]:
    return dict(_safe_json_object(manager.get_section(agent_id, "providers").get("data")))


def _current_local_model_policy(local_section: dict[str, Any]) -> dict[str, Any]:
    return dict(_safe_json_object(local_section.get("model_policy")))


def set_agent_general_provider(provider_id: str) -> dict[str, Any] | None:
    settings = get_agent_runtime_settings(force_refresh=True)
    if settings is None:
        return None
    agent_id = _nonempty_text(settings.get("agent_id"))
    normalized_provider = provider_id.strip().lower()
    available_options = settings.get("selectable_function_options", {}).get("general", [])
    provider_models = [
        _safe_json_object(item)
        for item in available_options
        if _nonempty_text(_safe_json_object(item).get("provider_id")).lower() == normalized_provider
    ]
    if not provider_models:
        raise ValueError(f"O provider '{normalized_provider}' nao esta disponivel para este agent.")
    selected_model = settings.get("default_models_by_provider", {}).get(normalized_provider) or _nonempty_text(
        provider_models[0].get("model_id")
    )
    _ensure_function_option(settings, "general", normalized_provider, selected_model)

    manager = ControlPlaneManager()
    local_section = _current_local_providers_section(manager, agent_id)
    local_policy = _current_local_model_policy(local_section)
    default_models = dict(_safe_json_object(local_policy.get("default_models")))
    if selected_model:
        default_models[normalized_provider] = selected_model
        local_policy["default_models"] = default_models
    local_policy["default_provider"] = normalized_provider
    functional_defaults = dict(_safe_json_object(local_policy.get("functional_defaults")))
    functional_defaults["general"] = {
        "provider_id": normalized_provider,
        "model_id": selected_model,
    }
    local_policy["functional_defaults"] = functional_defaults
    manager.put_model_policy(agent_id, {"policy": normalize_model_policy(local_policy)})
    invalidate_agent_settings_cache(agent_id)
    return get_agent_runtime_settings(force_refresh=True)


def set_agent_general_model(provider_id: str, model_id: str) -> dict[str, Any] | None:
    settings = get_agent_runtime_settings(force_refresh=True)
    if settings is None:
        return None
    agent_id = _nonempty_text(settings.get("agent_id"))
    normalized_provider = provider_id.strip().lower()
    selected = _ensure_function_option(settings, "general", normalized_provider, model_id)

    manager = ControlPlaneManager()
    local_section = _current_local_providers_section(manager, agent_id)
    local_policy = _current_local_model_policy(local_section)
    default_models = dict(_safe_json_object(local_policy.get("default_models")))
    default_models[normalized_provider] = _nonempty_text(selected.get("model_id"))
    local_policy["default_models"] = default_models
    local_policy["default_provider"] = normalized_provider
    functional_defaults = dict(_safe_json_object(local_policy.get("functional_defaults")))
    functional_defaults["general"] = {
        "provider_id": normalized_provider,
        "model_id": _nonempty_text(selected.get("model_id")),
    }
    local_policy["functional_defaults"] = functional_defaults
    manager.put_model_policy(agent_id, {"policy": normalize_model_policy(local_policy)})
    invalidate_agent_settings_cache(agent_id)
    return get_agent_runtime_settings(force_refresh=True)


def set_agent_functional_default(function_id: str, provider_id: str, model_id: str) -> dict[str, Any] | None:
    settings = get_agent_runtime_settings(force_refresh=True)
    if settings is None:
        return None
    if function_id not in MODEL_FUNCTION_IDS:
        raise ValueError(f"Funcionalidade desconhecida: {function_id}")
    selected = _ensure_function_option(settings, function_id, provider_id, model_id)
    agent_id = _nonempty_text(settings.get("agent_id"))

    manager = ControlPlaneManager()
    local_section = _current_local_providers_section(manager, agent_id)
    local_policy = _current_local_model_policy(local_section)
    functional_defaults = dict(_safe_json_object(local_policy.get("functional_defaults")))
    normalized_provider = _nonempty_text(selected.get("provider_id")).lower()
    normalized_model = _nonempty_text(selected.get("model_id"))
    functional_defaults[function_id] = {
        "provider_id": normalized_provider,
        "model_id": normalized_model,
    }
    local_policy["functional_defaults"] = functional_defaults
    if function_id == "general":
        local_policy["default_provider"] = normalized_provider
        default_models = dict(_safe_json_object(local_policy.get("default_models")))
        default_models[normalized_provider] = normalized_model
        local_policy["default_models"] = default_models
    manager.put_model_policy(agent_id, {"policy": normalize_model_policy(local_policy)})
    invalidate_agent_settings_cache(agent_id)
    return get_agent_runtime_settings(force_refresh=True)


def set_agent_voice_default(
    voice_id: str,
    *,
    voice_label: str = "",
    voice_language: str = "",
) -> dict[str, Any] | None:
    settings = get_agent_runtime_settings(force_refresh=True)
    if settings is None:
        return None
    agent_id = _nonempty_text(settings.get("agent_id"))
    normalized_voice = _nonempty_text(voice_id)
    if not normalized_voice:
        raise ValueError("A voz precisa ser informada.")

    voice_config = AVAILABLE_VOICES.get(normalized_voice)
    provider_id = "elevenlabs"
    persisted_voice = normalized_voice
    resolved_label = voice_label.strip()
    resolved_language = voice_language.strip().lower()
    if voice_config is not None:
        provider_id = str(voice_config.engine)
        persisted_voice = str(voice_config.engine_voice_id or normalized_voice)
        if not resolved_label:
            resolved_label = str(voice_config.label)
    elif kokoro_voice_metadata(normalized_voice) is not None:
        provider_id = "kokoro"
    if provider_id == "kokoro":
        metadata = _safe_json_object(kokoro_voice_metadata(persisted_voice))
        resolved_language = (
            resolved_language or _nonempty_text(metadata.get("language_id")).lower() or KOKORO_DEFAULT_LANGUAGE_ID
        )
        resolved_label = resolved_label or _nonempty_text(metadata.get("name")) or persisted_voice
    else:
        resolved_language = resolved_language or settings.get("tts_voice_language", "") or ELEVENLABS_DEFAULT_LANGUAGE
        resolved_label = resolved_label or persisted_voice

    manager = ControlPlaneManager()
    local_section = _current_local_providers_section(manager, agent_id)
    if provider_id == "elevenlabs":
        local_section["elevenlabs_default_voice"] = persisted_voice
        local_section["elevenlabs_default_language"] = resolved_language
    else:
        local_section["kokoro_default_voice"] = persisted_voice
        local_section["kokoro_default_language"] = resolved_language
    manager.put_section(agent_id, "providers", {"data": local_section})

    audio_model = ""
    audio_options = [
        _safe_json_object(item)
        for item in _safe_json_list(_safe_json_object(settings.get("selectable_function_options")).get("audio"))
        if _nonempty_text(_safe_json_object(item).get("provider_id")).lower() == provider_id
    ]
    if provider_id == "elevenlabs":
        audio_model = (
            _nonempty_text(local_section.get("elevenlabs_model"))
            or _nonempty_text(_safe_json_object(settings.get("providers_section")).get("elevenlabs_model"))
            or _nonempty_text(_safe_json_object(audio_options[0] if audio_options else {}).get("model_id"))
            or "eleven_flash_v2_5"
        )
    else:
        audio_model = (
            _nonempty_text(local_section.get("kokoro_default_model"))
            or _nonempty_text(_safe_json_object(audio_options[0] if audio_options else {}).get("model_id"))
            or "kokoro-v1"
        )
    set_agent_functional_default("audio", provider_id, audio_model)
    updated = get_agent_runtime_settings(force_refresh=True)
    if updated is None:
        return None
    updated["tts_voice"] = persisted_voice
    updated["tts_voice_label"] = resolved_label
    updated["tts_voice_language"] = resolved_language
    return updated
