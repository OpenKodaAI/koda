"""Shared command handler utilities."""

import copy
import functools
import uuid
from collections.abc import Callable, Coroutine
from typing import Any, Concatenate, ParamSpec, TypeVar, cast

from telegram import Message, Update, User

from koda.auth import auth_check, reject_unauthorized
from koda.config import (
    AVAILABLE_PROVIDERS,
    DEFAULT_AGENT_MODE,
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    DEFAULT_WORK_DIR,
    ELEVENLABS_DEFAULT_LANGUAGE,
    PROVIDER_DEFAULT_MODELS,
    PROVIDER_MODELS,
    TRANSCRIPTION_MODEL,
    TRANSCRIPTION_PROVIDER,
    TTS_DEFAULT_VOICE,
)
from koda.state.history_store import get_user_cost
from koda.telegram_types import BotContext, MessageUpdate
from koda.utils.rate_limiter import acquire_rate_limit

P = ParamSpec("P")
R = TypeVar("R")

_GENERAL_PROVIDER_ALIASES: dict[str, str] = {
    "anthropic": "claude",
    "claude": "claude",
    "openai": "codex",
    "codex": "codex",
    "google": "gemini",
    "gemini": "gemini",
    "ollama": "ollama",
}

_FUNCTION_PROVIDER_ALIASES: dict[str, str] = {
    **_GENERAL_PROVIDER_ALIASES,
    "elevenlabs": "elevenlabs",
    "kokoro": "kokoro",
    "whispercpp": "whispercpp",
    "whisper-cpp": "whispercpp",
    "whisper_cpp": "whispercpp",
    "whisper": "whispercpp",
    "sora": "codex",
}

_KNOWN_GENERAL_PROVIDER_IDS: frozenset[str] = frozenset(
    {
        *PROVIDER_MODELS.keys(),
        *_GENERAL_PROVIDER_ALIASES.values(),
        DEFAULT_PROVIDER,
    }
)


def require_user(update: Update) -> User:
    """Return the effective Telegram user or fail fast on unexpected updates."""
    user = update.effective_user
    if user is None:
        raise RuntimeError("Telegram update has no effective user.")
    return user


def require_user_id(update: Update) -> int:
    """Return the effective Telegram user id."""
    return require_user(update).id


def require_message(update: Update) -> Message:
    """Return the message/effective_message for command handlers."""
    message = update.message or update.effective_message
    if message is None:
        raise RuntimeError("Telegram update has no effective message.")
    return message


def require_user_data(context: BotContext) -> dict[str, Any]:
    """Return a mutable user_data mapping from the Telegram context."""
    user_data = context.user_data
    if user_data is None:
        raise RuntimeError("Telegram context has no user_data mapping.")
    return cast(dict[str, Any], user_data)


def normalize_provider(provider: str | None) -> str:
    """Normalize a provider name and fall back to the configured default."""
    normalized = str(provider or DEFAULT_PROVIDER).strip().lower()
    normalized = _GENERAL_PROVIDER_ALIASES.get(normalized, normalized)
    if normalized not in _KNOWN_GENERAL_PROVIDER_IDS:
        return DEFAULT_PROVIDER
    return normalized


def normalize_feature_provider(provider: str | None) -> str:
    """Normalize providers used by per-function agent-local defaults."""
    normalized = str(provider or "").strip().lower()
    return _FUNCTION_PROVIDER_ALIASES.get(normalized, normalized)


def infer_provider_from_model(model: str | None) -> str:
    """Infer the provider that owns the given model."""
    for provider, models in PROVIDER_MODELS.items():
        if model in models:
            return provider
    return DEFAULT_PROVIDER


def available_provider_models(user_data: dict[str, Any], provider: str | None = None) -> list[str]:
    """Return the available models for a provider, preferring agent-local runtime settings."""
    resolved_provider = normalize_provider(provider or user_data.get("provider"))
    dynamic_models = user_data.get("available_models_by_provider", {})
    if isinstance(dynamic_models, dict):
        models = dynamic_models.get(resolved_provider)
        if isinstance(models, list):
            normalized = [str(item).strip() for item in models if str(item).strip()]
            if normalized:
                return normalized
    models = PROVIDER_MODELS.get(resolved_provider, [])
    return [str(item).strip() for item in models if str(item).strip()]


def sync_user_data_with_runtime_settings(user_data: dict[str, Any], settings: dict[str, Any] | None) -> dict[str, Any]:
    """Overwrite session state from effective agent-local runtime settings."""
    if not settings:
        return user_data

    general_items = (
        settings.get("selectable_function_options", {}).get("general", [])
        if isinstance(settings.get("selectable_function_options"), dict)
        else []
    )
    available_general_providers: list[str] = []
    available_models_by_provider: dict[str, list[str]] = {}
    for item in general_items:
        if not isinstance(item, dict):
            continue
        provider_id = normalize_provider(str(item.get("provider_id") or ""))
        model_id = str(item.get("model_id") or "").strip()
        if not provider_id or not model_id:
            continue
        if provider_id not in available_general_providers:
            available_general_providers.append(provider_id)
        available_models_by_provider.setdefault(provider_id, [])
        if model_id not in available_models_by_provider[provider_id]:
            available_models_by_provider[provider_id].append(model_id)

    if available_general_providers:
        user_data["available_general_providers"] = list(available_general_providers)
    if available_models_by_provider:
        user_data["available_models_by_provider"] = {
            provider_id: list(models) for provider_id, models in available_models_by_provider.items()
        }
    user_data["_agent_selectable_function_options"] = copy.deepcopy(settings.get("selectable_function_options", {}))
    user_data["functional_defaults"] = copy.deepcopy(settings.get("functional_defaults", {}))

    manual_models = user_data.setdefault("manual_models_by_provider", {})
    for provider_id, model_id in settings.get("default_models_by_provider", {}).items():
        normalized_provider = normalize_provider(provider_id)
        normalized_model = str(model_id).strip()
        if normalized_model:
            manual_models[normalized_provider] = normalized_model

    provider = normalize_provider(settings.get("default_provider") or user_data.get("provider"))
    user_data["provider"] = provider
    user_data["model"] = str(settings.get("general_model") or get_provider_model(user_data, provider))
    user_data["transcription_provider"] = str(settings.get("transcription_provider") or TRANSCRIPTION_PROVIDER)
    user_data["transcription_model"] = str(settings.get("transcription_model") or TRANSCRIPTION_MODEL)
    user_data["audio_provider"] = str(settings.get("audio_provider") or "")
    user_data["audio_model"] = str(settings.get("audio_model") or "")
    user_data["tts_voice"] = str(settings.get("tts_voice") or TTS_DEFAULT_VOICE)
    if settings.get("tts_voice_label"):
        user_data["tts_voice_label"] = str(settings.get("tts_voice_label"))
    user_data["tts_voice_language"] = str(settings.get("tts_voice_language") or ELEVENLABS_DEFAULT_LANGUAGE)
    return user_data


def get_provider_model(user_data: dict[str, Any], provider: str | None = None) -> str:
    """Return the remembered manual/default model for a provider."""
    resolved_provider = normalize_provider(provider or user_data.get("provider"))
    manual_models = user_data.setdefault("manual_models_by_provider", {})
    provider_models = available_provider_models(user_data, resolved_provider)
    model = manual_models.get(resolved_provider) or PROVIDER_DEFAULT_MODELS.get(resolved_provider, DEFAULT_MODEL)
    if provider_models and model not in provider_models:
        model = provider_models[0]
    elif not provider_models and model not in PROVIDER_MODELS.get(resolved_provider, []):
        model = PROVIDER_DEFAULT_MODELS.get(resolved_provider, DEFAULT_MODEL)
    if provider_models:
        manual_models[resolved_provider] = model
    return model


def set_provider(user_data: dict[str, Any], provider: str) -> str:
    """Switch the user's preferred provider while keeping per-provider model memory."""
    resolved_provider = normalize_provider(provider)
    user_data["provider"] = resolved_provider
    user_data["model"] = get_provider_model(user_data, resolved_provider)
    return resolved_provider


def set_provider_model(user_data: dict[str, Any], provider: str, model: str) -> None:
    """Persist the last manual model for a provider and refresh the active model if needed."""
    resolved_provider = normalize_provider(provider)
    if model not in available_provider_models(user_data, resolved_provider):
        raise ValueError(f"Unknown model '{model}' for provider '{resolved_provider}'")
    manual_models = user_data.setdefault("manual_models_by_provider", {})
    manual_models[resolved_provider] = model
    if normalize_provider(user_data.get("provider")) == resolved_provider:
        user_data["model"] = model


def ensure_canonical_session_id(user_data: dict[str, Any]) -> str:
    """Ensure the user has a canonical session id."""
    session_id = user_data.get("session_id")
    if not session_id:
        session_id = f"session-{uuid.uuid4()}"
        user_data["session_id"] = session_id
        user_data["provider_sessions"] = {}
    return session_id


def rotate_canonical_session_id(user_data: dict[str, Any]) -> tuple[str | None, str]:
    """Rotate the canonical session id and clear provider session bindings."""
    current_session_id = str(user_data.get("session_id") or "").strip() or None
    new_session_id = f"session-{uuid.uuid4()}"
    user_data["session_id"] = new_session_id
    user_data["provider_sessions"] = {}
    return current_session_id, new_session_id


def init_user_data(user_data: dict[str, Any] | None, user_id: int | None = None) -> dict[str, Any]:
    """Ensure user_data has required keys.

    On first init (total_cost missing), loads persisted cost from the canonical state store
    so that budget survives agent restarts.
    """
    if user_data is None:
        raise RuntimeError("Telegram context has no user_data mapping.")

    needs_cost_load = "total_cost" not in user_data
    runtime_settings: dict[str, Any] | None = None
    try:
        from koda.services.agent_settings import get_agent_runtime_settings

        runtime_settings = get_agent_runtime_settings()
    except Exception:
        runtime_settings = None

    available_general_providers = [str(item) for item in AVAILABLE_PROVIDERS]
    available_models_by_provider: dict[str, list[str]] = {}
    runtime_default_provider = DEFAULT_PROVIDER
    runtime_default_models: dict[str, str] = {}
    if runtime_settings:
        sync_user_data_with_runtime_settings(user_data, runtime_settings)
        available_general_providers = [
            str(item)
            for item in user_data.get("available_general_providers", available_general_providers)
            if str(item).strip()
        ]
        available_models_by_provider = {
            str(provider_id): [str(model_id) for model_id in models if str(model_id).strip()]
            for provider_id, models in cast(
                dict[str, list[str]],
                user_data.get("available_models_by_provider", available_models_by_provider),
            ).items()
        }
        runtime_default_provider = normalize_provider(
            runtime_settings.get("default_provider") or user_data.get("provider")
        )
        default_models = runtime_settings.get("default_models_by_provider", {})
        if isinstance(default_models, dict):
            runtime_default_models = {
                normalize_provider(provider_id): str(model_id).strip()
                for provider_id, model_id in default_models.items()
                if str(model_id).strip()
            }

    user_data.setdefault("session_id", None)
    user_data.setdefault("work_dir", DEFAULT_WORK_DIR)
    provider = normalize_provider(user_data.get("provider") or infer_provider_from_model(user_data.get("model")))
    if available_general_providers and provider not in available_general_providers:
        provider = (
            runtime_default_provider
            if runtime_default_provider in available_general_providers
            else available_general_providers[0]
        )
    user_data.setdefault("provider", provider)
    if available_general_providers and user_data["provider"] not in available_general_providers:
        user_data["provider"] = provider
    user_data.setdefault("manual_models_by_provider", {})
    for known_provider in available_general_providers:
        if known_provider == provider and user_data.get("model"):
            default_model = str(user_data["model"])
        elif known_provider == provider:
            default_model = runtime_default_models.get(known_provider) or DEFAULT_MODEL
        else:
            default_model = runtime_default_models.get(known_provider) or PROVIDER_DEFAULT_MODELS.get(
                known_provider, DEFAULT_MODEL
            )
        user_data["manual_models_by_provider"].setdefault(
            known_provider,
            default_model,
        )
    if user_data.get("model") not in available_provider_models(user_data, provider):
        user_data["model"] = get_provider_model(user_data, provider)
    else:
        user_data["manual_models_by_provider"][provider] = user_data["model"]
    user_data.setdefault("provider_sessions", {})
    user_data.setdefault("total_cost", 0.0)
    user_data.setdefault("query_count", 0)
    user_data.setdefault("system_prompt", None)
    user_data.setdefault("last_query", None)
    user_data.setdefault("auto_model", False)
    user_data.setdefault("agent_mode", DEFAULT_AGENT_MODE)
    user_data.setdefault("audio_response", False)
    user_data.setdefault("tts_voice", TTS_DEFAULT_VOICE)
    user_data.setdefault("tts_voice_language", ELEVENLABS_DEFAULT_LANGUAGE)
    # Restore persisted cost from the canonical state store on first load
    if needs_cost_load and user_id is not None:
        try:
            persisted_cost, persisted_count = get_user_cost(user_id)
        except RuntimeError:
            persisted_cost, persisted_count = (0.0, 0)
        if persisted_cost > 0:
            user_data["total_cost"] = persisted_cost
            user_data["query_count"] = max(user_data["query_count"], persisted_count)
    return user_data


def authorized(
    func: Callable[Concatenate[MessageUpdate, BotContext, P], Coroutine[Any, Any, R]],
) -> Callable[Concatenate[MessageUpdate, BotContext, P], Coroutine[Any, Any, R | None]]:
    """Decorator that checks auth and initializes user_data."""

    @functools.wraps(func)
    async def wrapper(
        update: MessageUpdate,
        context: BotContext,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> R | None:
        if not auth_check(update):
            await reject_unauthorized(update)
            return None
        init_user_data(require_user_data(context), user_id=require_user_id(update))
        return await func(update, context, *args, **kwargs)

    return cast(Callable[Concatenate[MessageUpdate, BotContext, P], Coroutine[Any, Any, R | None]], wrapper)


def authorized_with_rate_limit(
    func: Callable[Concatenate[MessageUpdate, BotContext, P], Coroutine[Any, Any, R]],
) -> Callable[Concatenate[MessageUpdate, BotContext, P], Coroutine[Any, Any, R | None]]:
    """Decorator: auth check + init_user_data + rate limit."""

    @functools.wraps(func)
    async def wrapper(
        update: MessageUpdate,
        context: BotContext,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> R | None:
        if not auth_check(update):
            await reject_unauthorized(update)
            return None
        init_user_data(require_user_data(context), user_id=require_user_id(update))
        user_id = require_user_id(update)
        if not await acquire_rate_limit(user_id):
            await require_message(update).reply_text("Rate limited. Please wait before sending more messages.")
            return None
        return await func(update, context, *args, **kwargs)

    return cast(Callable[Concatenate[MessageUpdate, BotContext, P], Coroutine[Any, Any, R | None]], wrapper)
