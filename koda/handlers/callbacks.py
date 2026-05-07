"""Inline keyboard callback handlers."""

import contextlib
import hashlib
import os
import re
import time
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest

from koda import config
from koda.auth import auth_check
from koda.config import AVAILABLE_AGENT_MODES, AVAILABLE_MODELS, AVAILABLE_PROVIDERS, PROVIDER_MODELS
from koda.handlers.commands import (
    _settings_home_markup,
    _settings_home_text,
    _voice_apply_elevenlabs_model_selection,
    _voice_apply_provider_selection,
    _voice_apply_selection,
    _voice_as_dict,
    _voice_as_list,
    _voice_download_job_from_payload,
    _voice_elevenlabs_api_available,
    _voice_elevenlabs_catalog,
    _voice_elevenlabs_language_query,
    _voice_elevenlabs_model_label,
    _voice_elevenlabs_models_markup,
    _voice_elevenlabs_models_text,
    _voice_elevenlabs_voice_entry,
    _voice_home_markup,
    _voice_home_text,
    _voice_kokoro_model_download_markup,
    _voice_kokoro_model_download_text,
    _voice_kokoro_model_ready,
    _voice_kokoro_model_status,
    _voice_kokoro_voice_download_markup,
    _voice_kokoro_voice_download_text,
    _voice_kokoro_voice_ready,
    _voice_kokoro_voice_status,
    _voice_label_for_id,
    _voice_language_for_id,
    _voice_languages_markup,
    _voice_provider_label,
    _voice_providers_markup,
    _voice_set_session_enabled,
    _voice_voices_markup,
)
from koda.logging_config import get_logger
from koda.memory.quality import record_utility_event
from koda.provider_models import MODEL_FUNCTION_IDS, resolve_model_function_catalog
from koda.services.agent_settings import (
    get_agent_runtime_settings,
    set_agent_functional_default,
    set_agent_general_model,
    set_agent_general_provider,
)
from koda.services.feedback_policy import (
    build_success_pattern_candidate,
    episode_feedback_gate_reasons,
    episode_source_refs,
)
from koda.state.history_store import add_bookmark
from koda.state.knowledge_governance_store import (
    get_correction_event,
    get_latest_execution_episode,
    record_correction_event,
    update_execution_reliability_stats,
    upsert_knowledge_candidate,
)
from koda.telegram_types import BotContext
from koda.telegram_types import CallbackUpdate as Update
from koda.utils.approval import (
    _PENDING_AGENT_CMD_OPS,
    _PENDING_OPS,
    APPROVAL_TIMEOUT,
    _cleanup_stale_agent_cmd_ops,
    _cleanup_stale_ops,
    _issue_agent_approval_grants,
    dispatch_approved_operation,
    resolve_agent_cmd_approval,
    rotate_session_approval_state,
)
from koda.utils.command_helpers import (
    available_provider_models,
    init_user_data,
    set_provider_model,
    sync_user_data_with_runtime_settings,
)
from koda.utils.formatting import escape_html
from koda.utils.messaging import split_message

log = get_logger(__name__)


def _telegram_bad_request_text(exc: BadRequest) -> str:
    return str(exc).strip().lower()


def _telegram_query_expired(exc: BadRequest) -> bool:
    text = _telegram_bad_request_text(exc)
    return "query is too old" in text or "query id is invalid" in text or "response timeout expired" in text


def _telegram_message_not_modified(exc: BadRequest) -> bool:
    return "message is not modified" in _telegram_bad_request_text(exc)


async def _safe_callback_answer(query: Any, *args: Any, **kwargs: Any) -> bool:
    try:
        await query.answer(*args, **kwargs)
        return True
    except BadRequest as exc:
        if _telegram_query_expired(exc):
            log.debug("telegram_callback_answer_expired", data=getattr(query, "data", None))
            return False
        raise


async def _safe_edit_message_text(query: Any, text: str, **kwargs: Any) -> bool:
    try:
        await query.edit_message_text(text, **kwargs)
        return True
    except BadRequest as exc:
        if _telegram_message_not_modified(exc):
            log.debug("telegram_callback_message_not_modified", data=getattr(query, "data", None))
            return False
        if _telegram_query_expired(exc):
            log.debug("telegram_callback_edit_expired", data=getattr(query, "data", None))
            return False
        raise


def _optional_chat_id(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


_FUNCTION_DEFINITIONS = {str(item["id"]): dict(item) for item in resolve_model_function_catalog()}


def _general_provider_options(user_data: dict[str, object]) -> list[str]:
    providers = user_data.get("available_general_providers")
    if isinstance(providers, list):
        normalized = [str(item).strip().lower() for item in providers if str(item).strip()]
        if normalized:
            return normalized
    return [str(item) for item in AVAILABLE_PROVIDERS]


def _feature_option_map(user_data: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    payload = user_data.get("_agent_selectable_function_options", {})
    if not isinstance(payload, dict):
        return {}
    option_map: dict[str, list[dict[str, object]]] = {}
    for function_id, items in payload.items():
        if not isinstance(items, list):
            continue
        option_map[str(function_id)] = [dict(item) for item in items if isinstance(item, dict)]
    return option_map


def _feature_function_label(function_id: str) -> str:
    meta = _FUNCTION_DEFINITIONS.get(function_id, {})
    return str(meta.get("title") or function_id)


def _feature_selection_label(user_data: dict[str, object], function_id: str) -> str:
    payload = user_data.get("functional_defaults", {})
    selection = payload.get(function_id, {}) if isinstance(payload, dict) else {}
    if not isinstance(selection, dict):
        return "inherited from global"
    provider_id = str(selection.get("provider_id") or "").strip().lower()
    model_id = str(selection.get("model_id") or "").strip()
    if provider_id and model_id:
        return f"{provider_id} / {model_id}"
    return "inherited from global"


def _remember_feature_model_tokens(
    user_data: dict[str, object],
    *,
    function_id: str,
    provider_id: str,
    items: list[dict[str, object]],
) -> dict[str, dict[str, str]]:
    tokens: dict[str, dict[str, str]] = {}
    for item in items:
        model_id = str(item.get("model_id") or "").strip()
        if not model_id:
            continue
        raw = f"{function_id}:{provider_id}:{model_id}"
        token = hashlib.sha256(raw.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
        tokens[token] = {
            "function_id": function_id,
            "provider_id": provider_id,
            "model_id": model_id,
            "title": str(item.get("title") or model_id),
        }
    store = user_data.setdefault("_feature_model_tokens", {})
    if isinstance(store, dict):
        store.update(tokens)
    return tokens


async def callback_setdir(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await query.answer()

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    path = (query.data or "").removeprefix("setdir:")

    # Block sensitive system directories
    resolved = os.path.realpath(path)
    from koda.config import SENSITIVE_DIRS

    if any(resolved == s or resolved.startswith(s + "/") for s in SENSITIVE_DIRS):
        await query.edit_message_text("Access denied: sensitive system directory.")
        return

    if os.path.isdir(path):
        context.user_data["work_dir"] = path
        await query.edit_message_text(
            f"Working directory set to: <code>{escape_html(path)}</code>", parse_mode=ParseMode.HTML
        )
    else:
        await query.edit_message_text(
            f"Directory not found: <code>{escape_html(path)}</code>", parse_mode=ParseMode.HTML
        )


async def callback_model(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await query.answer()

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    model = (query.data or "").removeprefix("model:")
    provider = context.user_data["provider"]

    if model == "auto":
        context.user_data["auto_model"] = True
        await query.edit_message_text("Auto model routing enabled.")
        return

    provider_models = available_provider_models(context.user_data, provider) or PROVIDER_MODELS.get(
        provider, AVAILABLE_MODELS
    )
    if model in provider_models:
        try:
            sync_user_data_with_runtime_settings(context.user_data, set_agent_general_model(provider, model))
        except ValueError as exc:
            await query.edit_message_text(str(exc))
            return
        set_provider_model(context.user_data, provider, model)
        context.user_data["auto_model"] = False
        await query.edit_message_text(
            f"Provider: <code>{escape_html(provider)}</code>\nModel set to: <code>{escape_html(model)}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Back to settings", callback_data="settings:home")]]
            ),
        )


async def callback_provider(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await query.answer()

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    provider = (query.data or "").removeprefix("provider:")
    if provider in _general_provider_options(context.user_data):
        try:
            sync_user_data_with_runtime_settings(context.user_data, set_agent_general_provider(provider))
        except ValueError as exc:
            await query.edit_message_text(str(exc))
            return
        await query.edit_message_text(
            f"Provider set to: <code>{escape_html(provider)}</code>\n"
            f"Model: <code>{escape_html(context.user_data['model'])}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Back to settings", callback_data="settings:home")]]
            ),
        )


async def callback_settings_home(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await query.answer()

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    await query.edit_message_text(
        _settings_home_text(context.user_data),
        parse_mode=ParseMode.HTML,
        reply_markup=_settings_home_markup(),
    )


async def callback_settings_provider(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await query.answer()

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    current_provider = str(context.user_data.get("provider") or "")
    buttons = [
        [
            InlineKeyboardButton(
                f"{'> ' if provider == current_provider else ''}{provider}",
                callback_data=f"provider:{provider}",
            )
        ]
        for provider in _general_provider_options(context.user_data)
    ]
    buttons.append([InlineKeyboardButton("Back", callback_data="settings:home")])
    await query.edit_message_text(
        "Select the default provider for this agent:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def callback_settings_model(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await query.answer()

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    provider = str(context.user_data.get("provider") or "")
    provider_models = available_provider_models(context.user_data, provider) or PROVIDER_MODELS.get(
        provider,
        AVAILABLE_MODELS,
    )
    buttons = [
        [
            InlineKeyboardButton(
                f"{'> ' if model == context.user_data.get('model') else ''}{model}",
                callback_data=f"model:{model}",
            )
        ]
        for model in provider_models
    ]
    buttons.append(
        [
            InlineKeyboardButton(
                f"{'> ' if context.user_data.get('auto_model') else ''}auto (smart routing)",
                callback_data="model:auto",
            )
        ]
    )
    buttons.append([InlineKeyboardButton("Back", callback_data="settings:home")])
    await query.edit_message_text(
        f"Select the general model for <code>{escape_html(provider)}</code>:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def callback_settings_featuremodel(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await query.answer()

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    settings = get_agent_runtime_settings(force_refresh=True)
    if settings is None:
        await query.edit_message_text("Per-feature settings are not available for this agent right now.")
        return
    sync_user_data_with_runtime_settings(context.user_data, settings)
    option_map = _feature_option_map(context.user_data)
    buttons = [
        [
            InlineKeyboardButton(
                f"{_feature_function_label(function_id)} · {_feature_selection_label(context.user_data, function_id)}",
                callback_data=f"fmodelf:{function_id}",
            )
        ]
        for function_id in MODEL_FUNCTION_IDS
        if option_map.get(function_id)
    ]
    buttons.append([InlineKeyboardButton("Back", callback_data="settings:home")])
    await query.edit_message_text(
        "Select a feature to adjust the agent's default model:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def callback_settings_mode(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await query.answer()

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    current_mode = str(context.user_data.get("agent_mode") or "autonomous")
    buttons = [
        [
            InlineKeyboardButton(
                f"{'> ' if mode == current_mode else ''}{mode}",
                callback_data=f"mode:{mode}",
            )
        ]
        for mode in AVAILABLE_AGENT_MODES
    ]
    buttons.append([InlineKeyboardButton("Back", callback_data="settings:home")])
    await query.edit_message_text(
        f"Current mode: <code>{escape_html(current_mode)}</code>\nSelect the mode for this agent:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


def _voice_download_is_active(payload: dict[str, Any] | None) -> bool:
    job = _voice_download_job_from_payload(payload)
    return str(job.get("status") or "").strip().lower() in {"pending", "running"}


def _voice_callback_suffix(data: str | None) -> str:
    return (str(data or "").split(":", 1)[1] if ":" in str(data or "") else "").strip()


async def _render_voice_home(query: Any, context: BotContext) -> None:
    started = time.monotonic()
    try:
        await _safe_edit_message_text(
            query,
            _voice_home_text(context.user_data),
            parse_mode=ParseMode.HTML,
            reply_markup=_voice_home_markup(context.user_data),
        )
    finally:
        log.info(
            "telegram_voice_callback_rendered",
            callback_data=getattr(query, "data", None),
            duration_ms=round((time.monotonic() - started) * 1000),
        )


async def _render_kokoro_voice_download(
    query: Any,
    voice_id: str,
    payload: dict[str, Any] | None = None,
) -> None:
    await _safe_edit_message_text(
        query,
        _voice_kokoro_voice_download_text(voice_id, payload),
        parse_mode=ParseMode.HTML,
        reply_markup=_voice_kokoro_voice_download_markup(voice_id, payload),
    )


async def _render_kokoro_model_download(
    query: Any,
    voice_id: str = "",
    payload: dict[str, Any] | None = None,
) -> None:
    await _safe_edit_message_text(
        query,
        _voice_kokoro_model_download_text(voice_id, payload),
        parse_mode=ParseMode.HTML,
        reply_markup=_voice_kokoro_model_download_markup(voice_id, payload),
    )


async def _select_kokoro_voice_when_ready(
    query: Any,
    context: BotContext,
    voice_id: str,
    voice_payload: dict[str, Any] | None = None,
) -> bool:
    voice_status = voice_payload or _voice_kokoro_voice_status(voice_id)
    if _voice_download_is_active(voice_status) or not _voice_kokoro_voice_ready(voice_id, voice_status):
        await _render_kokoro_voice_download(query, voice_id, voice_status)
        return False

    model_status = _voice_kokoro_model_status()
    if _voice_download_is_active(model_status) or not _voice_kokoro_model_ready(model_status):
        await _render_kokoro_model_download(query, voice_id, model_status)
        return False

    try:
        _voice_apply_selection(
            context.user_data,
            voice_id,
            voice_label=_voice_label_for_id(voice_id),
            voice_language=_voice_language_for_id(voice_id),
        )
    except ValueError as exc:
        await _safe_edit_message_text(query, str(exc))
        return False

    await _render_voice_home(query, context)
    return True


async def callback_settings_voice(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await _safe_callback_answer(query)

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    await _render_voice_home(query, context)


async def callback_voice_home(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await _safe_callback_answer(query)

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    await _render_voice_home(query, context)


async def callback_voice_toggle(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await _safe_callback_answer(query)

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    action = (query.data or "").split(":", 1)[1] if ":" in (query.data or "") else ""
    _voice_set_session_enabled(context.user_data, action == "on")
    await _render_voice_home(query, context)


async def callback_voice_providers(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await _safe_callback_answer(query)

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    await _safe_edit_message_text(
        query,
        "Escolha o provider de voz:",
        reply_markup=_voice_providers_markup(context.user_data),
    )


async def callback_voice_provider(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await _safe_callback_answer(query)

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    provider = (query.data or "").split(":", 1)[1] if ":" in (query.data or "") else ""
    try:
        _voice_apply_provider_selection(context.user_data, provider)
    except ValueError as exc:
        await _safe_edit_message_text(query, str(exc), reply_markup=_voice_providers_markup(context.user_data))
        return
    await _render_voice_home(query, context)


async def callback_voice_elevenlabs_models(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await _safe_callback_answer(query)

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    await _safe_edit_message_text(
        query,
        _voice_elevenlabs_models_text(context.user_data),
        parse_mode=ParseMode.HTML,
        reply_markup=_voice_elevenlabs_models_markup(context.user_data),
    )


async def callback_voice_elevenlabs_model(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await _safe_callback_answer(query)

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    model_id = (query.data or "").split(":", 1)[1] if ":" in (query.data or "") else ""
    try:
        _voice_apply_elevenlabs_model_selection(context.user_data, model_id)
    except ValueError as exc:
        await _safe_edit_message_text(
            query,
            str(exc),
            reply_markup=_voice_elevenlabs_models_markup(context.user_data),
        )
        return
    await _safe_edit_message_text(
        query,
        f"Modelo ElevenLabs definido: <b>{escape_html(_voice_elevenlabs_model_label(model_id))}</b>\n"
        f"<code>{escape_html(model_id)}</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Escolher idioma", callback_data="voicelangs:elevenlabs")],
                [InlineKeyboardButton("Escolher voz", callback_data="voicevoices:elevenlabs:")],
                [InlineKeyboardButton("Voltar", callback_data="voicehome")],
            ]
        ),
    )


async def callback_voice_languages(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await _safe_callback_answer(query)

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    provider = (query.data or "").split(":", 1)[1] if ":" in (query.data or "") else "kokoro"
    await _safe_edit_message_text(
        query,
        f"Escolha o idioma para {_voice_provider_label(provider)}:",
        reply_markup=_voice_languages_markup(provider, context.user_data),
    )


async def callback_voice_language(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await _safe_callback_answer(query)

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    parts = (query.data or "").split(":", 2)
    if len(parts) != 3:
        return
    _, provider, language = parts
    provider = provider.strip().lower()
    language = language.strip().lower()
    if provider == "kokoro":
        await _safe_edit_message_text(
            query,
            f"Vozes Kokoro para <code>{escape_html(language)}</code>:",
            parse_mode=ParseMode.HTML,
            reply_markup=_voice_voices_markup("kokoro", language, context.user_data),
        )
        return

    context.user_data["_voice_pending_elevenlabs_language"] = language
    catalog = _voice_elevenlabs_catalog(language, context.user_data)
    language_label = str(catalog.get("selected_language_label") or language or "idioma selecionado")
    voices = [item for item in _voice_as_list(catalog.get("items")) if _voice_as_dict(item).get("voice_id")]
    if not bool(catalog.get("provider_connected")):
        text = (
            "A conexao ElevenLabs ainda nao esta pronta para listar vozes.\n"
            "Cadastre e verifique a API key do ElevenLabs, depois volte para esta tela."
        )
    elif not voices:
        search_query = _voice_elevenlabs_language_query(language)
        text = (
            f"Nao encontrei vozes ElevenLabs no catalogo para <b>{escape_html(language_label)}</b>.\n"
            f"Voce ainda pode tentar pelo texto: <code>/voice search {escape_html(search_query)}</code>."
        )
    else:
        text = (
            f"Vozes ElevenLabs para <b>{escape_html(language_label)}</b>:\n"
            "<i>Quando nao houver voz verificada especificamente no idioma, listo vozes compativeis "
            "com o modelo de TTS selecionado.</i>"
        )
    await _safe_edit_message_text(
        query,
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=_voice_voices_markup("elevenlabs", language, context.user_data),
    )


async def callback_voice_voices(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await _safe_callback_answer(query)

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    parts = (query.data or "").split(":", 2)
    provider = parts[1] if len(parts) > 1 else "kokoro"
    language = parts[2] if len(parts) > 2 else ""
    if provider.strip().lower() == "elevenlabs":
        catalog = _voice_elevenlabs_catalog(language, context.user_data)
        language_label = str(catalog.get("selected_language_label") or language or "todos os idiomas")
        items = [item for item in _voice_as_list(catalog.get("items")) if _voice_as_dict(item).get("voice_id")]
        if not bool(catalog.get("provider_connected")):
            text = "A conexao ElevenLabs ainda nao esta pronta para listar vozes. Verifique a API key."
        elif not items:
            text = f"Nao encontrei vozes ElevenLabs para <b>{escape_html(language_label)}</b>."
        else:
            text = f"Escolha uma voz ElevenLabs para <b>{escape_html(language_label)}</b>:"
        await _safe_edit_message_text(
            query,
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=_voice_voices_markup(provider, language, context.user_data),
        )
        return
    await _safe_edit_message_text(
        query,
        f"Escolha uma voz em {_voice_provider_label(provider)}:",
        reply_markup=_voice_voices_markup(provider, language, context.user_data),
    )


async def callback_voice_pick(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await _safe_callback_answer(query)

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    voice_id = (query.data or "").split(":", 1)[1] if ":" in (query.data or "") else ""
    from koda.services.kokoro_manager import kokoro_voice_metadata

    if kokoro_voice_metadata(voice_id) is not None:
        await _select_kokoro_voice_when_ready(query, context, voice_id)
        return

    try:
        _voice_apply_selection(context.user_data, voice_id)
    except ValueError as exc:
        await _safe_edit_message_text(query, str(exc))
        return
    await _render_voice_home(query, context)


async def callback_voice_download(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await _safe_callback_answer(query)

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    voice_id = _voice_callback_suffix(query.data)
    if not voice_id:
        await _safe_edit_message_text(query, "Voz Kokoro invalida.")
        return
    try:
        from koda.control_plane.manager import get_control_plane_manager

        job = get_control_plane_manager().start_kokoro_voice_download(voice_id)
    except ValueError as exc:
        await _safe_edit_message_text(query, str(exc))
        return
    await _select_kokoro_voice_when_ready(query, context, voice_id, job)


async def callback_voice_download_status(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await _safe_callback_answer(query)

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    voice_id = _voice_callback_suffix(query.data)
    if not voice_id:
        await _safe_edit_message_text(query, "Voz Kokoro invalida.")
        return
    await _select_kokoro_voice_when_ready(query, context, voice_id)


async def callback_voice_download_cancel(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await _safe_callback_answer(query)

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    voice_id = _voice_callback_suffix(query.data)
    status = _voice_kokoro_voice_status(voice_id)
    job = _voice_download_job_from_payload(status)
    if not job:
        await _render_kokoro_voice_download(query, voice_id, status)
        return
    try:
        from koda.control_plane.manager import get_control_plane_manager

        payload = get_control_plane_manager().cancel_provider_download_job(
            "kokoro",
            str(job.get("job_id") or job.get("id")),
        )
    except (KeyError, ValueError) as exc:
        await _safe_edit_message_text(query, str(exc))
        return
    await _render_kokoro_voice_download(query, voice_id, payload)


async def callback_voice_model_download(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await _safe_callback_answer(query)

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    voice_id = _voice_callback_suffix(query.data)
    try:
        from koda.control_plane.manager import get_control_plane_manager

        job = get_control_plane_manager().start_kokoro_model_download()
    except ValueError as exc:
        await _safe_edit_message_text(query, str(exc))
        return
    if voice_id and _voice_kokoro_model_ready(job) and _voice_kokoro_voice_ready(voice_id):
        await _select_kokoro_voice_when_ready(query, context, voice_id)
        return
    await _render_kokoro_model_download(query, voice_id, job)


async def callback_voice_model_status(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await _safe_callback_answer(query)

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    voice_id = _voice_callback_suffix(query.data)
    model_status = _voice_kokoro_model_status()
    if voice_id and _voice_kokoro_model_ready(model_status) and _voice_kokoro_voice_ready(voice_id):
        await _select_kokoro_voice_when_ready(query, context, voice_id)
        return
    await _render_kokoro_model_download(query, voice_id, model_status)


async def callback_voice_model_cancel(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await _safe_callback_answer(query)

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    voice_id = _voice_callback_suffix(query.data)
    model_status = _voice_kokoro_model_status()
    job = _voice_download_job_from_payload(model_status)
    if not job:
        await _render_kokoro_model_download(query, voice_id, model_status)
        return
    try:
        from koda.control_plane.manager import get_control_plane_manager

        payload = get_control_plane_manager().cancel_provider_download_job(
            "kokoro",
            str(job.get("job_id") or job.get("id")),
        )
    except (KeyError, ValueError) as exc:
        await _safe_edit_message_text(query, str(exc))
        return
    await _render_kokoro_model_download(query, voice_id, payload)


async def callback_settings_newsession(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await query.answer()

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    _previous_session_id, new_session_id = await rotate_session_approval_state(
        user_data=context.user_data,
        user_id=update.effective_user.id,
        chat_id=update.effective_chat.id if getattr(update, "effective_chat", None) else None,
        agent_id=config.AGENT_ID or "default",
    )
    await query.edit_message_text(
        f"Session rotated to <code>{escape_html(new_session_id)}</code>.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to settings", callback_data="settings:home")]]),
    )


async def callback_bookmark(update: Update, context: BotContext) -> None:
    """Handle bookmark button press."""
    query = update.callback_query

    if not auth_check(update):
        await query.answer("Access denied.", show_alert=True)
        return

    user_id = update.effective_user.id

    # The message text is the agent's response
    message_text = str(getattr(query.message, "text", "") or getattr(query.message, "caption", "") or "")
    if not message_text:
        await query.answer("Nothing to bookmark.", show_alert=True)
        return

    # Strip the footer before bookmarking
    footer_idx = message_text.rfind("\n\n———\n")
    if footer_idx != -1:
        message_text = message_text[:footer_idx]

    bk_id = add_bookmark(user_id, message_text)
    await query.answer(f"Bookmarked! (#{bk_id})", show_alert=True)


async def callback_feedback(update: Update, context: BotContext) -> None:
    """Handle structured post-task feedback buttons."""
    query = update.callback_query
    await query.answer()

    if not auth_check(update):
        await query.answer("Access denied.", show_alert=True)
        return

    parts = (query.data or "").split(":", 2)
    if len(parts) != 3:
        await query.answer("Invalid feedback payload.", show_alert=True)
        return

    _, feedback_type, task_id_raw = parts
    try:
        task_id = int(task_id_raw)
    except ValueError:
        await query.answer("Invalid task id.", show_alert=True)
        return

    user_id = update.effective_user.id
    episode = get_latest_execution_episode(task_id)
    if episode is None:
        await query.answer("No execution episode found for this task.", show_alert=True)
        return
    agent_id = (
        (
            str(episode.get("agent_id") or "")
            or str(episode.get("team") or "")
            or (os.environ.get("AGENT_ID") or "")
            or (config.AGENT_ID or "")
            or "default"
        )
        .strip()
        .upper()
    )

    existing_feedback = get_correction_event(
        agent_id=agent_id,
        task_id=task_id,
        feedback_type=feedback_type,
        user_id=user_id,
        episode_id=int(episode["id"]),
    )
    if existing_feedback is not None:
        await query.answer("Feedback already recorded for this execution.", show_alert=True)
        return

    event_id = record_correction_event(
        agent_id=agent_id,
        task_id=task_id,
        feedback_type=feedback_type,
        user_id=user_id,
    )
    if event_id is None:
        await query.answer("Could not record feedback.", show_alert=True)
        return

    created_candidate = False
    feedback_labels = {
        "corrected": "Feedback recorded as a correction. Opened a risk candidate for review.",
        "failed": "Feedback recorded as a failure. Opened a risk candidate for review.",
        "risky": "Feedback recorded as high risk. Opened a guardrail candidate for review.",
        "approved": "Feedback recorded as approved.",
        "promote": "Feedback recorded as a promotion.",
    }

    if feedback_type in {"corrected", "failed", "risky"}:
        update_execution_reliability_stats(
            agent_id=agent_id,
            task_kind=episode["task_kind"],
            project_key=episode["project_key"],
            environment=episode["environment"],
            successful=episode["status"] == "completed",
            verified=episode["verified_before_finalize"],
            count_execution=False,
            correction_delta=1,
        )
        candidate_key = hashlib.sha256(
            f"feedback:{feedback_type}:{task_id}:{episode['task_kind']}:{episode['project_key']}".encode(),
            usedforsecurity=False,
        ).hexdigest()[:24]
        merge_key = hashlib.sha256(
            f"risk:{episode['task_kind']}:{episode['project_key']}:{episode['environment']}".encode(),
            usedforsecurity=False,
        ).hexdigest()[:24]
        upsert_knowledge_candidate(
            candidate_key=candidate_key,
            merge_key=merge_key,
            agent_id=agent_id,
            task_id=task_id,
            task_kind=episode["task_kind"],
            candidate_type="risk_pattern",
            summary=f"Human feedback marked task #{task_id} as {feedback_type}.",
            evidence=[
                {"kind": "human_feedback", "value": feedback_type},
                {"kind": "episode_status", "value": episode["status"]},
            ],
            source_refs=episode_source_refs(episode),
            proposed_runbook={
                "title": f"{episode['task_kind'].replace('_', ' ').title()} risk guardrail",
                "summary": f"Escalate when feedback type '{feedback_type}' matches similar executions.",
            },
            confidence_score=0.95,
            project_key=episode["project_key"],
            environment=episode["environment"],
            team=episode["team"],
            failure_delta=1,
            force_pending=True,
            diff_summary=f"Created from human feedback '{feedback_type}' on task #{task_id}.",
        )
        created_candidate = True
    elif feedback_type == "promote":
        gate_reasons = episode_feedback_gate_reasons(episode)
        if gate_reasons:
            await query.answer(
                "Promotion blocked: missing minimum gates for reusable routine creation.",
                show_alert=True,
            )
        else:
            upsert_knowledge_candidate(
                **build_success_pattern_candidate(
                    episode=episode,
                    feedback_type=feedback_type,
                    task_id=task_id,
                    agent_id=agent_id,
                ),
            )
            created_candidate = True
    elif feedback_type == "approved":
        gate_reasons = episode_feedback_gate_reasons(episode)
        if not gate_reasons:
            upsert_knowledge_candidate(
                **build_success_pattern_candidate(
                    episode=episode,
                    feedback_type=feedback_type,
                    task_id=task_id,
                    agent_id=agent_id,
                ),
            )
            created_candidate = True

    if feedback_type in {"approved", "promote"}:
        update_execution_reliability_stats(
            agent_id=agent_id,
            task_kind=episode["task_kind"],
            project_key=episode["project_key"],
            environment=episode["environment"],
            successful=episode["status"] == "completed",
            verified=episode["verified_before_finalize"],
            count_execution=False,
            human_override_delta=1,
        )

    from koda.services.metrics import HUMAN_CORRECTION_EVENTS

    HUMAN_CORRECTION_EVENTS.labels(agent_id=agent_id or "default", feedback_type=feedback_type).inc()
    utility_outcome = {
        "approved": "useful",
        "promote": "useful" if created_candidate else "noise",
        "risky": "noise",
        "corrected": "misleading",
        "failed": "misleading",
    }.get(feedback_type)
    if utility_outcome:
        record_utility_event(agent_id, utility_outcome)
    if feedback_type == "approved" and not created_candidate:
        await query.answer(
            "Feedback recorded as approved, but minimum gates are missing to promote into a reusable routine.",
            show_alert=True,
        )
        return
    if feedback_type == "promote" and not created_candidate:
        return
    if feedback_type == "approved" and created_candidate:
        await query.answer(
            "Feedback recorded as approved. Opened a positive-routine candidate for review.",
            show_alert=True,
        )
        return
    if feedback_type == "promote" and created_candidate:
        await query.answer(
            "Feedback recorded as a promotion. Opened a runbook candidate for review.",
            show_alert=True,
        )
        return
    await query.answer(feedback_labels.get(feedback_type, "Feedback recorded."), show_alert=True)


async def callback_mode(update: Update, context: BotContext) -> None:
    """Handle mode selection button press."""
    query = update.callback_query
    await query.answer()

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    mode = (query.data or "").removeprefix("mode:")

    if mode in AVAILABLE_AGENT_MODES:
        context.user_data["agent_mode"] = mode
        await query.edit_message_text(
            f"Agent mode set to: <code>{escape_html(mode)}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Back to settings", callback_data="settings:home")]]
            ),
        )


async def callback_dbenv(update: Update, context: BotContext) -> None:
    """Handle database environment selection button press."""
    query = update.callback_query
    await query.answer()

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    await query.edit_message_text(
        "Native database environment switching was removed. Configure a database MCP server instead."
    )


async def callback_supervised(update: Update, context: BotContext) -> None:
    """Handle supervised mode [Continue] / [Stop] buttons."""
    query = update.callback_query
    await query.answer()

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    data = query.data or ""  # supervised:continue or supervised:stop

    if data == "supervised:continue":
        # Edit message to remove buttons
        original_text = update.effective_message.text or ""
        with contextlib.suppress(Exception):
            await query.edit_message_text(
                escape_html(original_text) + "\n\n<i>[Continuing...]</i>", parse_mode=ParseMode.HTML
            )

        # Enqueue a continuation (session_id is in user_data)
        from koda.services.queue_manager import enqueue_continuation

        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        await enqueue_continuation(user_id, chat_id, context)

    elif data == "supervised:stop":
        original_text = update.effective_message.text or ""
        with contextlib.suppress(Exception):
            await query.edit_message_text(
                escape_html(original_text) + "\n\n<i>[Stopped]</i>", parse_mode=ParseMode.HTML
            )


async def callback_voice_elevenlabs(update: Update, context: BotContext) -> None:
    """Handle ElevenLabs voice selection from /voice search results."""
    query = update.callback_query
    await _safe_callback_answer(query)

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    # Format: voiceel:<voice_id>:<display_name>
    parts = (query.data or "").split(":", 2)
    if len(parts) != 3:
        return
    _, voice_id, display_name = parts
    voice_language = str(context.user_data.get("_voice_pending_elevenlabs_language") or "")
    voice_entry = _voice_elevenlabs_voice_entry(voice_id, context.user_data, language_id=voice_language)
    available, unavailable_reason = _voice_elevenlabs_api_available(voice_entry)
    if voice_entry and not available:
        reason = escape_html(unavailable_reason)
        await _safe_edit_message_text(
            query,
            "Essa voz aparece no catalogo do ElevenLabs, mas nao pode ser usada via API nesta conta.\n\n"
            f"<i>{reason}</i>\n\n"
            "Escolha uma voz marcada como <b>premade</b> ou atualize o plano no ElevenLabs.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "Escolher outra voz",
                            callback_data=f"voicevoices:elevenlabs:{voice_language}",
                        )
                    ],
                    [InlineKeyboardButton("Voltar", callback_data="voicehome")],
                ]
            ),
        )
        return

    try:
        _voice_apply_selection(
            context.user_data,
            voice_id,
            voice_label=display_name,
            voice_language=voice_language,
        )
    except ValueError as exc:
        await _safe_edit_message_text(query, str(exc))
        return
    await _safe_edit_message_text(
        query,
        f"Voice set to: <b>{escape_html(display_name)}</b>\n"
        f"ID: <code>{escape_html(voice_id)}</code>\n\n"
        "Voice responses are now ON.",
        parse_mode=ParseMode.HTML,
    )


async def callback_feature_model_home(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await query.answer()

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    settings = get_agent_runtime_settings(force_refresh=True)
    if settings is None:
        await query.edit_message_text("Per-feature settings are not available for this agent right now.")
        return
    sync_user_data_with_runtime_settings(context.user_data, settings)
    option_map = _feature_option_map(context.user_data)
    buttons = [
        [
            InlineKeyboardButton(
                f"{_feature_function_label(function_id)} · {_feature_selection_label(context.user_data, function_id)}",
                callback_data=f"fmodelf:{function_id}",
            )
        ]
        for function_id in MODEL_FUNCTION_IDS
        if option_map.get(function_id)
    ]
    buttons.append([InlineKeyboardButton("Back to settings", callback_data="settings:home")])
    await query.edit_message_text(
        "Select a feature to adjust the agent's default model:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def callback_feature_model_function(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await query.answer()

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    function_id = (query.data or "").removeprefix("fmodelf:")
    if function_id not in MODEL_FUNCTION_IDS:
        await query.edit_message_text("Funcionalidade invalida.")
        return

    settings = get_agent_runtime_settings(force_refresh=True)
    if settings is None:
        await query.edit_message_text("Per-feature settings are not available for this agent right now.")
        return
    sync_user_data_with_runtime_settings(context.user_data, settings)
    options = _feature_option_map(context.user_data).get(function_id, [])
    if not options:
        await query.edit_message_text("Nenhum provider disponivel para esta funcionalidade.")
        return

    providers: dict[str, str] = {}
    for item in options:
        provider_id = str(item.get("provider_id") or "").strip().lower()
        provider_title = str(item.get("provider_title") or provider_id)
        if provider_id:
            providers.setdefault(provider_id, provider_title)
    current = _feature_selection_label(context.user_data, function_id)
    buttons = [
        [InlineKeyboardButton(title, callback_data=f"fmodelp:{function_id}:{provider_id}")]
        for provider_id, title in providers.items()
    ]
    buttons.append([InlineKeyboardButton("Back", callback_data="fmodelhome")])
    await query.edit_message_text(
        f"<b>{escape_html(_feature_function_label(function_id))}</b>\n"
        f"Current: <code>{escape_html(current)}</code>\n\n"
        "Select the provider for this feature:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def callback_feature_model_provider(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await query.answer()

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    parts = (query.data or "").split(":", 2)
    if len(parts) != 3:
        await query.edit_message_text("Selecao invalida. Use /featuremodel novamente.")
        return
    _, function_id, provider_id = parts
    if function_id not in MODEL_FUNCTION_IDS:
        await query.edit_message_text("Funcionalidade invalida.")
        return

    settings = get_agent_runtime_settings(force_refresh=True)
    if settings is None:
        await query.edit_message_text("Per-feature settings are not available for this agent right now.")
        return
    sync_user_data_with_runtime_settings(context.user_data, settings)
    options = [
        item
        for item in _feature_option_map(context.user_data).get(function_id, [])
        if str(item.get("provider_id") or "").strip().lower() == provider_id
    ]
    if not options:
        await query.edit_message_text("Nenhum modelo disponivel para este provider.")
        return

    tokens = _remember_feature_model_tokens(
        context.user_data,
        function_id=function_id,
        provider_id=provider_id,
        items=options,
    )
    provider_title = str(options[0].get("provider_title") or provider_id)
    buttons = [
        [InlineKeyboardButton(str(item.get("title") or item.get("model_id")), callback_data=f"fmodelm:{token}")]
        for token, item in tokens.items()
    ]
    buttons.append([InlineKeyboardButton("Back", callback_data=f"fmodelf:{function_id}")])
    await query.edit_message_text(
        f"<b>{escape_html(_feature_function_label(function_id))}</b>\n"
        f"Provider: <code>{escape_html(provider_title)}</code>\n\n"
        "Select the default model for this agent:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def callback_feature_model_model(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await query.answer()

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    token = (query.data or "").removeprefix("fmodelm:")
    store = context.user_data.get("_feature_model_tokens", {})
    payload = store.get(token, {}) if isinstance(store, dict) else {}
    function_id = str(payload.get("function_id") or "").strip()
    provider_id = str(payload.get("provider_id") or "").strip().lower()
    model_id = str(payload.get("model_id") or "").strip()
    title = str(payload.get("title") or model_id)
    if function_id not in MODEL_FUNCTION_IDS or not provider_id or not model_id:
        await query.edit_message_text("A selecao expirou. Use /featuremodel novamente.")
        return

    try:
        updated = set_agent_functional_default(function_id, provider_id, model_id)
    except ValueError as exc:
        await query.edit_message_text(str(exc))
        return
    sync_user_data_with_runtime_settings(context.user_data, updated)
    await query.edit_message_text(
        f"<b>{escape_html(_feature_function_label(function_id))}</b>\n"
        f"Agent default updated to <code>{escape_html(title)}</code> "
        f"({escape_html(provider_id)} / <code>{escape_html(model_id)}</code>).",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Ajustar outro modelo", callback_data=f"fmodelf:{function_id}")],
                [InlineKeyboardButton("Back to menu", callback_data="fmodelhome")],
            ]
        ),
    )


async def callback_memory_forget(update: Update, context: BotContext) -> None:
    """Handle memory forget confirmation buttons."""
    query = update.callback_query
    await query.answer()

    if not auth_check(update):
        return

    data = query.data or ""  # memory_forget:all or memory_forget:cancel
    action = data.removeprefix("memory_forget:")

    if action == "cancel":
        with contextlib.suppress(Exception):
            await query.edit_message_text("Cancelled. No memories were deleted.")
        return

    if action == "all":
        user_id = update.effective_user.id
        from koda.memory import get_memory_manager
        from koda.memory.recall import clear_recall_cache

        mm = get_memory_manager()
        if mm.store:
            count = await mm.store.deactivate_all_for_user(user_id)
            clear_recall_cache(user_id)
            with contextlib.suppress(Exception):
                await query.edit_message_text(f"All {count} memories forgotten.")
        else:
            with contextlib.suppress(Exception):
                await query.edit_message_text("Memory store not initialized.")


async def callback_link_analysis(update: Update, context: BotContext) -> None:
    """Handle link analysis button press (link:<action>:<url_hash>)."""
    query = update.callback_query
    await query.answer()

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)

    data = query.data or ""  # link:<action>:<url_hash>
    parts = data.split(":", 2)
    if len(parts) != 3:
        return
    _, action, hash_val = parts

    # Retrieve metadata from user_data
    link_meta_store = context.user_data.get("_link_meta", {})
    meta_dict = link_meta_store.get(hash_val)
    if not meta_dict:
        with contextlib.suppress(Exception):
            await query.edit_message_text("⚠️ Metadata expired. Please send the link again.")
        return

    from koda.services.link_analyzer import (
        build_analysis_prompt,
        dict_to_meta,
        fetch_youtube_transcript,
    )
    from koda.services.queue_manager import enqueue_link_analysis

    meta = dict_to_meta(meta_dict)

    # Action labels for status update
    action_labels = {
        "summary": "📝 Summary",
        "main_idea": "💡 Main Idea",
        "key_points": "🔑 Key Points",
        "structure": "📋 Structure",
        "full": "🔍 Full Analysis",
        "transcript": "📜 Transcript",
        "thumbnail": "🖼 Thumbnail",
    }
    label = action_labels.get(action, action)

    # Update original message to show selected action
    original_text = update.effective_message.text or ""
    with contextlib.suppress(Exception):
        await query.edit_message_text(
            escape_html(original_text) + f"\n\n<i>Selected: {label}</i>",
            parse_mode=ParseMode.HTML,
        )

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Thumbnail: direct action without provider execution
    if action == "thumbnail" and meta.youtube_id:
        thumbnail_url = f"https://img.youtube.com/vi/{meta.youtube_id}/maxresdefault.jpg"
        with contextlib.suppress(Exception):
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=thumbnail_url,
                caption=f"Thumbnail: {meta.title}" if meta.title else "Thumbnail",
            )
        return

    # Transcript: direct action without provider execution — send formatted text directly
    if action == "transcript" and meta.youtube_id:
        transcript_text = await fetch_youtube_transcript(meta.url)
        if not transcript_text:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ Could not extract a transcript for this video. Captions may be unavailable.",
            )
            return
        header = f"📜 <b>Transcript: {escape_html(meta.title)}</b>\n\n" if meta.title else "📜 <b>Transcript</b>\n\n"
        full_text = header + escape_html(transcript_text)
        chunks = split_message(full_text)
        for chunk in chunks:
            try:
                await context.bot.send_message(chat_id=chat_id, text=chunk, parse_mode=ParseMode.HTML)
            except Exception:
                plain = re.sub(r"<[^>]+>", "", chunk)
                await context.bot.send_message(chat_id=chat_id, text=plain)
        return

    prompt = build_analysis_prompt(action, meta)
    await enqueue_link_analysis(user_id, chat_id, context, prompt)


async def callback_approval(update: Update, context: BotContext) -> None:
    """Handle approval keyboard button presses (approve:one/scope/deny:<op_id>)."""
    from koda.services.audit import emit_security

    query = update.callback_query
    await query.answer()

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    _cleanup_stale_ops()

    parts = (query.data or "").split(":", 2)  # approve:<action>:<op_id>
    if len(parts) != 3:
        return
    _, action, op_id = parts

    pending = _PENDING_OPS.get(op_id)
    if not pending:
        with contextlib.suppress(Exception):
            await query.edit_message_text("Operacao expirada ou invalida.")
        return

    # Verify the pressing user is the same who initiated the operation
    if pending.get("user_id") and update.effective_user.id != pending["user_id"]:
        await query.answer("Somente quem iniciou o comando pode aprovar.", show_alert=True)
        return

    if time.time() - pending["timestamp"] > APPROVAL_TIMEOUT:
        _PENDING_OPS.pop(op_id, None)
        log.info(
            "approval_expired",
            op_id=op_id,
            user_id=update.effective_user.id,
            cmd=pending.get("cmd_name"),
            args=str(pending.get("args", ""))[:200],
        )
        emit_security(
            "security.approval_timeout",
            user_id=update.effective_user.id,
            op_id=op_id,
            cmd=pending.get("cmd_name"),
        )
        with contextlib.suppress(Exception):
            await query.edit_message_text("Operacao expirada (timeout).")
        return

    if action == "deny":
        _PENDING_OPS.pop(op_id, None)
        log.info(
            "approval_denied",
            op_id=op_id,
            user_id=update.effective_user.id,
            cmd=pending.get("cmd_name"),
            args=str(pending.get("args", ""))[:200],
        )
        emit_security(
            "security.approval_denied",
            user_id=update.effective_user.id,
            op_id=op_id,
            cmd=pending.get("cmd_name"),
        )
        with contextlib.suppress(Exception):
            await query.edit_message_text("Negado.")
        return

    if action not in {"one", "scope"}:
        with contextlib.suppress(Exception):
            await query.edit_message_text("Operacao invalida.")
        return

    grants = _issue_agent_approval_grants(
        user_id=update.effective_user.id,
        agent_id=str(pending.get("agent_id") or "default"),
        session_id=str(pending.get("session_id") or "").strip() or None,
        chat_id=_optional_chat_id(pending.get("chat_id")),
        requests=list(pending.get("requests") or []),
        decision="approved_scope" if action == "scope" else "approved",
        issued_by_op_id=op_id,
    )
    pending["grants"] = grants
    pending["decision"] = "approved_scope" if action == "scope" else "approved"

    log.info(
        "approval_granted",
        op_id=op_id,
        user_id=update.effective_user.id,
        cmd=pending.get("cmd_name"),
        args=str(pending.get("args", ""))[:200],
        mode=action,
    )
    emit_security(
        "security.approval_granted",
        user_id=update.effective_user.id,
        op_id=op_id,
        cmd=pending.get("cmd_name"),
        mode=action,
    )
    with contextlib.suppress(Exception):
        await query.edit_message_text("Aprovado (escopo)." if action == "scope" else "Aprovado uma vez.")
    await dispatch_approved_operation(op_id)


async def callback_agent_cmd_approval(update: Update, context: BotContext) -> None:
    """Handle agent-cmd approval keyboard button presses (acmd:ok/scope/no:<op_id>)."""
    from koda.services.audit import emit_security

    query = update.callback_query
    await query.answer()

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    _cleanup_stale_agent_cmd_ops()

    parts = (query.data or "").split(":", 2)  # acmd:<action>:<op_id>
    if len(parts) != 3:
        return
    _, action, op_id = parts

    pending = _PENDING_AGENT_CMD_OPS.get(op_id)
    if not pending:
        with contextlib.suppress(Exception):
            await query.edit_message_text("Operacao expirada ou invalida.")
        return

    # Verify the pressing user is the same who initiated the operation
    if pending.get("user_id") is not None and update.effective_user.id != pending["user_id"]:
        await query.answer("Somente quem iniciou o comando pode aprovar.", show_alert=True)
        return

    if time.time() - pending["timestamp"] > APPROVAL_TIMEOUT:
        resolve_agent_cmd_approval(op_id, "timeout")
        log.info("agent_cmd_approval_expired", op_id=op_id, user_id=update.effective_user.id)
        emit_security("security.approval_timeout", user_id=update.effective_user.id, op_id=op_id)
        with contextlib.suppress(Exception):
            await query.edit_message_text("Operacao expirada (timeout).")
        return

    if action == "no":
        resolve_agent_cmd_approval(op_id, "denied")
        log.info("agent_cmd_approval_denied", op_id=op_id, user_id=update.effective_user.id)
        emit_security("security.approval_denied", user_id=update.effective_user.id, op_id=op_id)
        with contextlib.suppress(Exception):
            await query.edit_message_text("Negado.")
        return

    session_id = str(pending.get("session_id") or "").strip() or None
    chat_id = _optional_chat_id(pending.get("chat_id"))

    if action == "scope":
        grants = _issue_agent_approval_grants(
            user_id=update.effective_user.id,
            agent_id=str(pending.get("agent_id") or "default"),
            session_id=session_id,
            chat_id=chat_id,
            requests=list(pending.get("requests") or []),
            decision="approved_scope",
            issued_by_op_id=op_id,
        )
        pending["grants"] = grants
        resolve_agent_cmd_approval(op_id, "approved_scope", grants=grants)
        log.info(
            "agent_cmd_approval_granted",
            op_id=op_id,
            user_id=update.effective_user.id,
            mode="scope",
        )
        emit_security("security.approval_granted", user_id=update.effective_user.id, op_id=op_id, mode="scope")
        with contextlib.suppress(Exception):
            await query.edit_message_text("Aprovado (escopo).")
        return

    # action == "ok"
    grants = _issue_agent_approval_grants(
        user_id=update.effective_user.id,
        agent_id=str(pending.get("agent_id") or "default"),
        session_id=session_id,
        chat_id=chat_id,
        requests=list(pending.get("requests") or []),
        decision="approved",
        issued_by_op_id=op_id,
    )
    pending["grants"] = grants
    resolve_agent_cmd_approval(op_id, "approved", grants=grants)
    log.info(
        "agent_cmd_approval_granted",
        op_id=op_id,
        user_id=update.effective_user.id,
        mode="one",
    )
    emit_security("security.approval_granted", user_id=update.effective_user.id, op_id=op_id, mode="one")
    with contextlib.suppress(Exception):
        await query.edit_message_text("Aprovado.")
