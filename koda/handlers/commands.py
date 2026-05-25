"""Telegram command handlers."""

import contextlib
import json
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from koda.auth import auth_check, reject_unauthorized
from koda.config import (
    AGENT_ID,
    AGENT_NAME,
    ALLOWED_GIT_CMDS,
    AVAILABLE_AGENT_MODES,
    AVAILABLE_MODELS,
    AVAILABLE_PROVIDERS,
    GIT_META_CHARS,
    KNOWLEDGE_ADMIN_USER_IDS,
    MAX_BUDGET_USD,
    PROJECT_DIRS,
    PROVIDER_MODELS,
    SENSITIVE_DIRS,
    SHELL_ENABLED,
    TTS_DEFAULT_VOICE,
)
from koda.logging_config import get_logger
from koda.provider_models import MODEL_FUNCTION_IDS, resolve_model_function_catalog
from koda.services.agent_settings import (
    get_agent_runtime_settings,
    set_agent_functional_default,
    set_agent_general_model,
    set_agent_general_provider,
    set_agent_voice_default,
    set_agent_voice_policy_enabled,
)
from koda.services.elevenlabs_catalog import (
    ELEVENLABS_DEFAULT_TTS_MODEL,
    canonicalize_elevenlabs_language,
    elevenlabs_language_label,
    elevenlabs_languages_for_model,
    elevenlabs_model_label,
    elevenlabs_tts_model_ids,
    elevenlabs_tts_models,
)
from koda.services.queue_manager import (
    active_processes,
    agent_start_time,
    enqueue,
    get_active_tasks,
    get_queue_depth,
    get_task_info,
    is_process_running,
    requeue_dlq_entry,
)
from koda.services.shell_runner import run_shell_command
from koda.services.templates import (
    add_template,
    delete_template,
    get_template,
    list_template_names,
)
from koda.state.history_store import (
    delete_bookmark,
    dlq_get_dict,
    dlq_list,
    get_bookmarks,
    get_full_history,
    get_history,
    get_session_by_id,
    get_sessions,
    get_task,
    get_user_tasks,
    rename_session,
    reset_user_cost,
)
from koda.state.knowledge_governance_store import (
    approve_knowledge_candidate,
    deprecate_approved_runbook,
    get_knowledge_candidate,
    get_latest_runbook_governance_actions,
    list_approved_runbooks,
    list_knowledge_candidates,
    list_knowledge_sources,
    reject_knowledge_candidate,
    revalidate_approved_runbook,
)
from koda.telegram_types import BotContext
from koda.telegram_types import MessageUpdate as Update
from koda.utils.approval import rotate_session_approval_state, with_approval
from koda.utils.command_helpers import (
    authorized,
    available_provider_models,
    init_user_data,
    normalize_feature_provider,
    normalize_provider,
    set_provider,
    set_provider_model,
    sync_user_data_with_runtime_settings,
)
from koda.utils.files import list_directory, safe_resolve
from koda.utils.formatting import escape_html
from koda.utils.messaging import send_long_message
from koda.utils.rate_limiter import acquire_rate_limit

log = get_logger(__name__)
_FUNCTION_DEFINITIONS = {str(item["id"]): dict(item) for item in resolve_model_function_catalog()}
_FUNCTION_ALIASES = {
    "geral": "general",
    "general": "general",
    "imagem": "image",
    "image": "image",
    "video": "video",
    "vídeo": "video",
    "audio": "audio",
    "áudio": "audio",
    "transcricao": "transcription",
    "transcrição": "transcription",
    "transcription": "transcription",
    "stt": "transcription",
    "musica": "music",
    "música": "music",
    "music": "music",
}


def _is_knowledge_admin(user_id: int) -> bool:
    return user_id in KNOWLEDGE_ADMIN_USER_IDS


def _normalize_scope_label(value: str | None, *, uppercase: bool = False) -> str:
    normalized = (value or "default").strip()
    normalized = normalized.upper() if uppercase else normalized.lower()
    return normalized or ("DEFAULT" if uppercase else "default")


def _current_runtime_agent_id(*, uppercase: bool = False) -> str | None:
    raw_value = os.environ.get("AGENT_ID")
    if raw_value is None:
        return None
    normalized = raw_value.strip()
    if not normalized:
        return None
    return normalized.upper() if uppercase else normalized.lower()


def _resolve_memory_agent_scope(requested_agent: str | None, user_id: int) -> tuple[str, str | None]:
    current_scope = _current_memory_agent_scope()
    requested_scope = _normalize_scope_label(requested_agent, uppercase=False) if requested_agent else current_scope
    if requested_scope != current_scope and not _is_knowledge_admin(user_id):
        return current_scope, "Access denied: cross-agent memory inspection is restricted to operators."
    return requested_scope, None


def _resolve_knowledge_agent_scope(requested_agent: str | None, user_id: int) -> tuple[str | None, str | None]:
    current_scope = _current_runtime_agent_id(uppercase=True)
    requested_scope = _normalize_scope_label(requested_agent, uppercase=True) if requested_agent else current_scope
    if requested_scope and current_scope and requested_scope != current_scope and not _is_knowledge_admin(user_id):
        return current_scope, "Access denied: cross-agent knowledge inspection is restricted to operators."
    return requested_scope, None


def _general_provider_options(user_data: dict[str, Any]) -> list[str]:
    providers = user_data.get("available_general_providers")
    if isinstance(providers, list):
        normalized = [normalize_provider(item) for item in providers if str(item).strip()]
        if normalized:
            return normalized
    return [str(item) for item in AVAILABLE_PROVIDERS]


def _feature_option_map(user_data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    payload = user_data.get("_agent_selectable_function_options", {})
    if not isinstance(payload, dict):
        return {}
    option_map: dict[str, list[dict[str, Any]]] = {}
    for function_id, items in payload.items():
        if not isinstance(items, list):
            continue
        option_map[str(function_id)] = [dict(item) for item in items if isinstance(item, dict)]
    return option_map


def _feature_function_label(function_id: str) -> str:
    meta = _FUNCTION_DEFINITIONS.get(function_id, {})
    return str(meta.get("title") or function_id)


def _normalize_feature_function_id(value: str) -> str:
    normalized = str(value or "").strip().lower()
    return _FUNCTION_ALIASES.get(normalized, normalized)


def _feature_selection_label(user_data: dict[str, Any], function_id: str) -> str:
    selection = {}
    if isinstance(user_data.get("functional_defaults"), dict):
        selection = dict(cast(dict[str, Any], user_data["functional_defaults"]).get(function_id) or {})
    provider_id = str(selection.get("provider_id") or "").strip().lower()
    model_id = str(selection.get("model_id") or "").strip()
    if provider_id and model_id:
        return f"{provider_id} / {model_id}"
    return "herdado do global"


def _featuremodel_usage_text() -> str:
    return (
        "Uso:\n"
        "/featuremodel — abrir seletor interativo\n"
        "/featuremodel list — listar configuracoes do AGENT\n"
        "/featuremodel <funcionalidade> — listar opcoes disponiveis\n"
        "/featuremodel <funcionalidade> <provider> <modelo> — definir override do AGENT"
    )


def _settings_examples_text() -> str:
    return (
        "You can also ask in natural language, for example:\n"
        "• switch the provider to OpenAI\n"
        "• use gpt-5.2 as the general model\n"
        "• for images, use codex gpt-image-2\n"
        "• change the voice to pm_alex\n"
        "• enable supervised mode"
    )


def _settings_home_text(user_data: dict[str, Any]) -> str:
    lines = [
        "<b>Agent settings</b>",
        "",
        f"General provider: <code>{escape_html(str(user_data.get('provider') or ''))}</code>",
        f"General model: <code>{escape_html(str(user_data.get('model') or ''))}</code>",
        f"Mode: <code>{escape_html(str(user_data.get('agent_mode') or 'autonomous'))}</code>",
        f"Voice: <code>{escape_html(str(user_data.get('tts_voice') or TTS_DEFAULT_VOICE))}</code>",
        "",
        "<b>Per-feature models</b>",
    ]
    for function_id in MODEL_FUNCTION_IDS:
        if function_id == "general":
            continue
        label = _feature_function_label(function_id)
        selection = _feature_selection_label(user_data, function_id)
        lines.append(f"• {escape_html(label)}: <code>{escape_html(selection)}</code>")
    lines.extend(
        [
            "",
            "These changes only affect this agent. Credentials and global defaults remain in the web interface.",
            "",
            _settings_examples_text(),
        ]
    )
    return "\n".join(lines)


def _settings_home_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Provider", callback_data="settings:provider"),
                InlineKeyboardButton("Model", callback_data="settings:model"),
            ],
            [
                InlineKeyboardButton("Features", callback_data="settings:featuremodel"),
                InlineKeyboardButton("Mode", callback_data="settings:mode"),
            ],
            [
                InlineKeyboardButton("Voice", callback_data="settings:voice"),
                InlineKeyboardButton("New session", callback_data="settings:newsession"),
            ],
        ]
    )


def _remember_feature_model_tokens(
    user_data: dict[str, Any],
    *,
    function_id: str,
    provider_id: str,
    items: list[dict[str, Any]],
) -> dict[str, dict[str, str]]:
    import hashlib

    tokens: dict[str, dict[str, str]] = {}
    for item in items:
        model_id = str(item.get("model_id") or "").strip()
        if not model_id:
            continue
        raw = f"{function_id}:{provider_id}:{model_id}"
        token = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        tokens[token] = {
            "function_id": function_id,
            "provider_id": provider_id,
            "model_id": model_id,
            "title": str(item.get("title") or model_id),
        }
    user_data.setdefault("_feature_model_tokens", {}).update(tokens)
    return tokens


async def cmd_start(update: Update, context: BotContext) -> None:
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)
    from koda.services.agent_welcome import build_start_message

    await update.message.reply_text(build_start_message(AGENT_ID))


async def cmd_help(update: Update, context: BotContext) -> None:
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)
    work_dir = context.user_data["work_dir"]
    provider = context.user_data["provider"]
    model = context.user_data["model"]
    session = context.user_data["session_id"] or "none"
    auto = " (auto)" if context.user_data.get("auto_model") else ""

    await update.message.reply_text(
        f"<b>{escape_html(AGENT_NAME)} Agent</b>\n\n"
        f"Working dir: <code>{escape_html(work_dir)}</code>\n"
        f"Provider: <code>{escape_html(provider)}</code>\n"
        f"Model: <code>{escape_html(model)}</code>{auto}\n"
        f"Session: <code>{escape_html(session)}</code>\n\n"
        f"Commands\n"
        f"/settings — adjust provider, model, mode and defaults for this agent\n"
        f"/newsession — new session\n"
        f"/sessions — list sessions\n"
        f"/setdir [path] — change working directory\n"
        f"/voice — voice &amp; TTS\n"
        f"/tasks — running tasks\n"
        f"/cancel — cancel execution\n"
        f"/help — this help\n\n"
        + f"{escape_html(_settings_examples_text())}\n\n"
        + ("Advanced commands are still available, but the idea is to use natural language for most of the work."),
        parse_mode=ParseMode.HTML,
    )


@authorized
async def cmd_settings(update: Update, context: BotContext) -> None:
    await update.message.reply_text(
        _settings_home_text(context.user_data),
        reply_markup=_settings_home_markup(),
        parse_mode=ParseMode.HTML,
    )


async def cmd_newsession(update: Update, context: BotContext) -> None:
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)
    _previous_session_id, new_session_id = await rotate_session_approval_state(
        user_data=context.user_data,
        user_id=update.effective_user.id,
        chat_id=update.effective_chat.id if getattr(update, "effective_chat", None) else None,
        agent_id=AGENT_ID or "default",
    )
    await update.message.reply_text(f"Session rotated to {new_session_id}. Next message starts a new conversation.")


async def cmd_setdir(update: Update, context: BotContext) -> None:
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)
    args = context.args

    if args:
        path = " ".join(args)
        path = os.path.expanduser(path)
        # Block sensitive system directories (use resolved path consistently)
        resolved = os.path.realpath(path)
        if any(resolved == s or resolved.startswith(s + "/") for s in SENSITIVE_DIRS):
            await update.message.reply_text("Access denied: sensitive system directory.")
            return
        if os.path.isdir(resolved):
            context.user_data["work_dir"] = resolved
            await update.message.reply_text(
                f"Working directory set to: <code>{escape_html(resolved)}</code>", parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text(
                f"Directory not found: <code>{escape_html(resolved)}</code>", parse_mode=ParseMode.HTML
            )
        return

    if not PROJECT_DIRS:
        await update.message.reply_text("Usage: /setdir /path/to/directory\n\nNo PROJECT_DIRS configured in .env.")
        return

    buttons = [
        [InlineKeyboardButton(os.path.basename(d) or d, callback_data=f"setdir:{d}")]
        for d in PROJECT_DIRS
        if os.path.isdir(d)
    ]
    if not buttons:
        await update.message.reply_text("No valid directories found in PROJECT_DIRS.")
        return

    await update.message.reply_text(
        "Select a working directory:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def cmd_cost(update: Update, context: BotContext) -> None:
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)
    cost = context.user_data["total_cost"]
    count = context.user_data["query_count"]

    from koda.config import MAX_TOTAL_BUDGET_USD

    note = "\nNote: some Codex runs may report usage without pricing and appear as $0.0000."
    await update.message.reply_text(
        f"Queries: {count}\n"
        f"Total cost: ${cost:.4f}\n"
        f"Budget: ${MAX_TOTAL_BUDGET_USD:.2f} (${MAX_BUDGET_USD:.2f}/query)"
        f"{note}"
    )


async def cmd_provider(update: Update, context: BotContext) -> None:
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)
    args = context.args
    available_providers = _general_provider_options(context.user_data)

    if args:
        provider = normalize_provider(args[0])
        if provider not in available_providers:
            await update.message.reply_text(f"Unknown provider. Available: {', '.join(available_providers)}")
            return
        try:
            sync_user_data_with_runtime_settings(context.user_data, set_agent_general_provider(provider))
        except ValueError as exc:
            await update.message.reply_text(str(exc))
            return
        await update.message.reply_text(
            f"Provider set to: <code>{escape_html(provider)}</code>\n"
            f"Model: <code>{escape_html(context.user_data['model'])}</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    current_provider = context.user_data["provider"]
    buttons = [
        [
            InlineKeyboardButton(
                f"{'> ' if provider == current_provider else ''}{provider}",
                callback_data=f"provider:{provider}",
            )
        ]
        for provider in available_providers
    ]
    await update.message.reply_text(
        "Select a provider:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def cmd_model(update: Update, context: BotContext) -> None:
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)
    args = context.args
    provider = context.user_data["provider"]
    provider_models = available_provider_models(context.user_data, provider) or PROVIDER_MODELS.get(
        provider, AVAILABLE_MODELS
    )

    if args:
        model = args[0]

        # Handle "auto" mode
        if model == "auto":
            context.user_data["auto_model"] = True
            await update.message.reply_text(
                "Auto model routing enabled. Model will be selected based on query complexity."
            )
            return

        if model == "manual":
            context.user_data["auto_model"] = False
            await update.message.reply_text(
                f"Auto model routing disabled. Using: <code>{escape_html(context.user_data['model'])}</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        if model not in provider_models:
            await update.message.reply_text(
                f"Unknown model for {provider}. Available: {', '.join(provider_models)}\nAlso: auto, manual"
            )
            return
        try:
            sync_user_data_with_runtime_settings(context.user_data, set_agent_general_model(provider, model))
        except ValueError as exc:
            await update.message.reply_text(str(exc))
            return
        set_provider_model(context.user_data, provider, model)
        context.user_data["auto_model"] = False
        await update.message.reply_text(f"Model set to: <code>{escape_html(model)}</code>", parse_mode=ParseMode.HTML)
        return

    buttons = [
        [
            InlineKeyboardButton(
                f"{'> ' if m == context.user_data['model'] else ''}{m}",
                callback_data=f"model:{m}",
            )
        ]
        for m in provider_models
    ]
    # Add auto option
    auto_active = context.user_data.get("auto_model", False)
    buttons.append(
        [
            InlineKeyboardButton(
                f"{'> ' if auto_active else ''}auto (smart routing)",
                callback_data="model:auto",
            )
        ]
    )
    await update.message.reply_text(
        f"Select a model for <code>{escape_html(provider)}</code>:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.HTML,
    )


@authorized
async def cmd_featuremodel(update: Update, context: BotContext) -> None:
    """Show per-function model defaults for this agent only."""
    settings = get_agent_runtime_settings(force_refresh=True)
    if settings is None:
        await update.message.reply_text("Per-feature settings are not available for this agent right now.")
        return

    sync_user_data_with_runtime_settings(context.user_data, settings)
    option_map = _feature_option_map(context.user_data)
    if not option_map:
        await update.message.reply_text("No per-feature models are available for this agent.")
        return

    args = [str(item).strip() for item in (context.args or []) if str(item).strip()]
    if args:
        command = args[0].lower()
        if command == "list":
            lines = ["Default per-feature models for this agent:\n"]
            for function_id in MODEL_FUNCTION_IDS:
                if option_map.get(function_id):
                    lines.append(
                        f"- <b>{escape_html(_feature_function_label(function_id))}</b>: "
                        f"<code>{escape_html(_feature_selection_label(context.user_data, function_id))}</code>"
                    )
            await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
            return

        function_id = _normalize_feature_function_id(command)
        if function_id not in MODEL_FUNCTION_IDS:
            await update.message.reply_text(_featuremodel_usage_text())
            return

        function_options = option_map.get(function_id, [])
        if not function_options:
            await update.message.reply_text("No models available for this feature on this agent.")
            return

        if len(args) >= 3:
            provider_id = normalize_feature_provider(args[1])
            model_id = " ".join(args[2:]).strip()
            try:
                updated = set_agent_functional_default(function_id, provider_id, model_id)
            except ValueError as exc:
                await update.message.reply_text(str(exc))
                return
            sync_user_data_with_runtime_settings(context.user_data, updated)
            await update.message.reply_text(
                f"<b>{escape_html(_feature_function_label(function_id))}</b>\n"
                f"Agent default updated to <code>{escape_html(provider_id)}</code> / "
                f"<code>{escape_html(model_id)}</code>.",
                parse_mode=ParseMode.HTML,
            )
            return

        lines = [f"<b>{escape_html(_feature_function_label(function_id))}</b>\n"]
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in function_options:
            provider_title = str(item.get("provider_title") or item.get("provider_id") or "")
            grouped.setdefault(provider_title, []).append(item)
        current_selection = _feature_selection_label(context.user_data, function_id)
        lines.append(f"Current: <code>{escape_html(current_selection)}</code>\n")
        for provider_title, items in grouped.items():
            lines.append(f"<b>{escape_html(provider_title)}</b>")
            for item in items:
                provider_id = str(item.get("provider_id") or "").strip().lower()
                model_id = str(item.get("model_id") or "").strip()
                title = str(item.get("title") or model_id)
                marker = " ◀" if current_selection == f"{provider_id} / {model_id}" else ""
                lines.append(
                    "  "
                    f"<code>{escape_html(provider_id)}</code> / "
                    f"<code>{escape_html(model_id)}</code> — "
                    f"{escape_html(title)}{marker}"
                )
            lines.append("")
        lines.append(f"To change via text:\n/featuremodel {function_id} <provider> <model>")
        await update.message.reply_text("\n".join(lines).strip(), parse_mode=ParseMode.HTML)
        return

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
    if not buttons:
        await update.message.reply_text("No configurable features are available for this agent.")
        return

    await update.message.reply_text(
        "Select a feature to adjust the agent's default model:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def cmd_mode(update: Update, context: BotContext) -> None:
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)
    args = context.args

    if args:
        mode = args[0].lower()
        if mode not in AVAILABLE_AGENT_MODES:
            await update.message.reply_text(f"Unknown mode. Available: {', '.join(AVAILABLE_AGENT_MODES)}")
            return
        context.user_data["agent_mode"] = mode
        await update.message.reply_text(
            f"Agent mode set to: <code>{escape_html(mode)}</code>", parse_mode=ParseMode.HTML
        )
        return

    current_mode = context.user_data.get("agent_mode", "autonomous")
    buttons = [
        [
            InlineKeyboardButton(
                f"{'> ' if m == current_mode else ''}{m}",
                callback_data=f"mode:{m}",
            )
        ]
        for m in AVAILABLE_AGENT_MODES
    ]
    await update.message.reply_text(
        f"Current agent mode: <code>{escape_html(current_mode)}</code>\nSelect agent mode:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.HTML,
    )


async def cmd_dbenv(update: Update, context: BotContext) -> None:
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)
    await update.message.reply_text(
        ("Native database environment switching was removed. Configure a database MCP server instead."),
        parse_mode=ParseMode.HTML,
    )


async def cmd_cancel(update: Update, context: BotContext) -> None:
    if not auth_check(update):
        return await reject_unauthorized(update)

    user_id = update.effective_user.id
    args = context.args

    if args:
        # /cancel <task_id> — cancel a specific task
        try:
            target_id = int(args[0].lstrip("#"))
        except ValueError:
            await update.message.reply_text("Usage: /cancel <task_id>")
            return
        ti = get_task_info(target_id)
        row = get_task(target_id)
        owner_user_id = ti.user_id if ti else (int(row[1]) if row else None)
        if owner_user_id != user_id:
            await update.message.reply_text(f"Task #{target_id} not found.")
            return
        from koda.services.runtime import get_runtime_controller

        result = await get_runtime_controller().cancel_task(
            task_id=target_id,
            actor="telegram_command",
            reason="Cancelled by /cancel command.",
        )
        if result is None:
            await update.message.reply_text(f"Task #{target_id} not found.")
            return
        await update.message.reply_text(f"Task #{target_id} cancelled. Final phase: {result['final_phase']}.")
        return

    # /cancel — cancel all running tasks
    tasks = get_active_tasks(user_id)
    if not tasks:
        # Fallback: check legacy active_processes by user_id
        proc = active_processes.get(user_id)
        if proc and proc.returncode is None:
            proc.kill()
            await update.message.reply_text("Cancelled.")
        else:
            await update.message.reply_text("Nothing running.")
        return

    cancelled = 0
    from koda.services.runtime import get_runtime_controller

    for ti in tasks:
        result = await get_runtime_controller().cancel_task(
            task_id=ti.task_id,
            actor="telegram_command",
            reason="Cancelled by /cancel command.",
        )
        if result is not None:
            cancelled += 1
    await update.message.reply_text(f"Cancelled {cancelled} task(s)." if cancelled else "Nothing running.")


async def cmd_tasks(update: Update, context: BotContext) -> None:
    if not auth_check(update):
        return await reject_unauthorized(update)

    from koda.utils.formatting import escape_html

    user_id = update.effective_user.id

    # Active (in-memory) tasks
    active = get_active_tasks(user_id)
    # Recent tasks from DB
    db_tasks = get_user_tasks(user_id, limit=10)

    if not active and not db_tasks:
        await update.message.reply_text("No tasks.")
        return

    lines: list[str] = []
    status_icons = {
        "queued": "\u23f3",
        "running": "\u2699\ufe0f",
        "completed": "\u2705",
        "failed": "\u274c",
        "retrying": "\U0001f504",
    }

    # Show active tasks first
    active_ids = set()
    for ti in active:
        icon = status_icons.get(ti.status, "\u2753")
        preview = (ti.query_text[:40] + "...") if len(ti.query_text) > 40 else ti.query_text
        extra = ""
        if ti.status == "running" and ti.started_at:
            import time as _t

            elapsed = _t.time() - ti.started_at
            extra = f" ({elapsed:.0f}s)"
        if ti.status == "retrying":
            extra = f" (attempt {ti.attempt})"
        lines.append(f"{icon} #{ti.task_id} \u2014 {escape_html(preview)}{extra}")
        active_ids.add(ti.task_id)

    # Add recent DB tasks (skip active ones already shown)
    for row in db_tasks:
        if len(row) == 13:
            tid, status, qtext, provider, model, cost, err, created, started, completed, attempt, max_att, wdir = row
        else:
            tid, status, qtext, model, cost, err, created, started, completed, attempt, max_att, wdir = row
            provider = None
        if tid in active_ids:
            continue
        icon = status_icons.get(status, "\u2753")
        preview = (qtext[:40] + "...") if qtext and len(qtext) > 40 else (qtext or "")
        extra = ""
        if status == "completed" and cost:
            extra = f" (${cost:.4f})"
        elif status == "failed" and err:
            short_err = (err[:30] + "...") if len(err) > 30 else err
            extra = f" ({escape_html(short_err)})"
        suffix = f" [{provider}/{model}]" if provider and model else ""
        lines.append(f"{icon} #{tid} \u2014 {escape_html(preview)}{extra}{escape_html(suffix)}")

    text = "\n".join(lines)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_task(update: Update, context: BotContext) -> None:
    if not auth_check(update):
        return await reject_unauthorized(update)

    from koda.utils.formatting import escape_html

    args = context.args
    if not args:
        await update.message.reply_text("Usage: /task <id>")
        return

    try:
        task_id = int(args[0].lstrip("#"))
    except ValueError:
        await update.message.reply_text("Usage: /task <id>")
        return

    # Check in-memory first, then DB
    ti = get_task_info(task_id)
    row = get_task(task_id)

    if not row:
        await update.message.reply_text(f"Task #{task_id} not found.")
        return

    if len(row) == 17:
        (
            _id,
            user_id,
            chat_id,
            status,
            qtext,
            provider,
            model,
            wdir,
            attempt,
            max_att,
            cost,
            err,
            created,
            started,
            completed,
            session_id,
            provider_session_id,
        ) = row
    else:
        (
            _id,
            user_id,
            chat_id,
            status,
            qtext,
            model,
            wdir,
            attempt,
            max_att,
            cost,
            err,
            created,
            started,
            completed,
            session_id,
        ) = row
        provider = None

    if user_id != update.effective_user.id:
        await update.message.reply_text(f"Task #{task_id} not found.")
        return

    status_icons = {
        "queued": "\u23f3",
        "running": "\u2699\ufe0f",
        "completed": "\u2705",
        "failed": "\u274c",
        "retrying": "\U0001f504",
    }
    icon = status_icons.get(status, "\u2753")

    # Use in-memory data for elapsed time if running
    elapsed_str = ""
    if ti and ti.started_at and status == "running":
        import time as _t

        elapsed = _t.time() - ti.started_at
        mins, secs = divmod(int(elapsed), 60)
        elapsed_str = f"\nElapsed: {mins}m{secs:02d}s" if mins else f"\nElapsed: {secs}s"

    attempt_str = f" (attempt {attempt}/{max_att})" if attempt and max_att and max_att > 1 else ""
    cost_str = f"\nCost: ${cost:.4f}" if cost else ""
    err_str = f"\nError: {escape_html(err)}" if err else ""
    query_preview = escape_html(qtext[:200]) if qtext else ""

    lines = [
        f"<b>Task #{task_id}</b>",
        f"Status: {icon} {status}{attempt_str}",
        f"Query: {query_preview}",
    ]
    if provider:
        lines.append(f"Provider: {escape_html(provider)}")
    if model:
        lines.append(f"Model: {escape_html(model)}")
    if wdir:
        lines.append(f"Dir: {escape_html(os.path.basename(wdir))}")
    if cost_str:
        lines.append(cost_str.strip())
    if elapsed_str:
        lines.append(elapsed_str.strip())
    if started:
        lines.append(f"Started: {started[11:19]}")
    if completed:
        lines.append(f"Completed: {completed[11:19]}")
    if err_str:
        lines.append(err_str.strip())

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_system(update: Update, context: BotContext) -> None:
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)
    text = " ".join(context.args) if context.args else ""

    if not text:
        current = context.user_data.get("system_prompt")
        if current:
            await update.message.reply_text(
                f"Default system prompt is always active.\n\nYour custom addition:\n\n{current}"
            )
        else:
            await update.message.reply_text(
                "Default system prompt is active. No custom addition set.\n"
                "Use /system <text> to add custom instructions."
            )
        return

    if text.strip().lower() == "clear":
        context.user_data["system_prompt"] = None
        await update.message.reply_text("System prompt cleared.")
        return

    context.user_data["system_prompt"] = text
    await update.message.reply_text(f"System prompt set to:\n\n{text}")


@authorized
@with_approval("shell")
async def cmd_shell(update: Update, context: BotContext) -> None:
    if not SHELL_ENABLED:
        await update.message.reply_text("Shell commands are disabled.")
        return

    command = " ".join(context.args) if context.args else ""
    if not command:
        await update.message.reply_text("Usage: /shell <command>")
        return

    from koda.services.blocked_patterns import is_blocked_shell

    if is_blocked_shell(command):
        await update.message.reply_text("Blocked: this command is not allowed for safety reasons.")
        return

    work_dir = context.user_data["work_dir"]
    result = await run_shell_command(command, work_dir)
    await send_long_message(update, f"```\n{result}\n```")


@authorized
@with_approval("git")
async def cmd_git(update: Update, context: BotContext) -> None:
    args = " ".join(context.args) if context.args else ""
    if not args:
        await update.message.reply_text("Usage: /git <args>")
        return

    first_token = args.split()[0]
    if first_token not in ALLOWED_GIT_CMDS:
        await update.message.reply_text(
            f"Git subcommand <code>{escape_html(first_token)}</code> is not allowed.\n"
            f"Allowed: {', '.join(sorted(ALLOWED_GIT_CMDS))}",
            parse_mode=ParseMode.HTML,
        )
        return

    if GIT_META_CHARS.search(args):
        await update.message.reply_text("Shell meta-characters are not allowed in git commands.")
        return

    work_dir = context.user_data["work_dir"]
    result = await run_shell_command(f"git {args}", work_dir)
    await send_long_message(update, f"```\n{result}\n```")


async def cmd_ping(update: Update, context: BotContext) -> None:
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)
    import time

    uptime_secs = int(time.time() - agent_start_time)
    hours, remainder = divmod(uptime_secs, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        uptime_str = f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        uptime_str = f"{minutes}m {secs}s"
    else:
        uptime_str = f"{secs}s"

    user_id = update.effective_user.id
    work_dir = context.user_data["work_dir"]
    provider = context.user_data["provider"]
    model = context.user_data["model"]
    auto = " (auto)" if context.user_data.get("auto_model") else ""
    session_id = context.user_data["session_id"] or "none"
    queue_depth = get_queue_depth(user_id)
    running = is_process_running(user_id)

    await update.message.reply_text(
        f"Pong!\n\n"
        f"Agent: {AGENT_NAME}\n"
        f"Uptime: {uptime_str}\n"
        f"Work dir: {work_dir}\n"
        f"Provider: {provider}\n"
        f"Model: {model}{auto}\n"
        f"Session: {session_id}\n"
        f"Queue depth: {queue_depth}\n"
        f"Process running: {'yes' if running else 'no'}"
    )


async def cmd_resetcost(update: Update, context: BotContext) -> None:
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)
    context.user_data["total_cost"] = 0.0
    context.user_data["query_count"] = 0

    reset_user_cost(update.effective_user.id)
    await update.message.reply_text("Cost and query count reset to zero.")


async def cmd_retry(update: Update, context: BotContext) -> None:
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)
    last = context.user_data.get("last_query")
    if not last:
        await update.message.reply_text("No previous query to retry.")
        return

    query_text = last["text"]
    image_paths = last.get("image_paths")
    artifact_bundle = last.get("artifact_bundle")

    if image_paths:
        missing = [p for p in image_paths if not Path(p).exists()]
        if missing:
            await update.message.reply_text("Image files from last query no longer exist. Send the image again.")
            return

    user_id = update.effective_user.id

    if not await acquire_rate_limit(user_id):
        await update.message.reply_text("Rate limited. Please wait before sending more messages.")
        return

    await update.message.reply_text("Retrying last query...")
    await enqueue(user_id, update, context, query_text, image_paths, artifact_bundle)


async def cmd_history(update: Update, context: BotContext) -> None:
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)
    user_id = update.effective_user.id

    n = 10
    if context.args:
        try:
            n = int(context.args[0])
            n = max(1, min(n, 50))
        except ValueError:
            pass

    rows = get_history(user_id, n)

    if not rows:
        await update.message.reply_text("No query history found.")
        return

    lines = []
    for row in rows:
        if len(row) == 6:
            ts, provider, model, cost, query, error = row
        else:
            ts, model, cost, query, error = row
            provider = "claude"
        try:
            dt = datetime.fromisoformat(ts)
            ts_fmt = dt.strftime("%m/%d %H:%M")
        except Exception:
            ts_fmt = ts[:16]
        preview = query[:60].replace("\n", " ")
        if len(query) > 60:
            preview += "..."
        err_mark = " [ERR]" if error else ""
        short_model = model.split("-")[1] if model and "-" in model else model
        lines.append(f"{ts_fmt} | {provider}/{short_model} | ${cost:.4f}{err_mark}\n  {preview}")

    header = f"Last {len(rows)} queries:\n\n"
    await send_long_message(update, header + "\n\n".join(lines))


async def cmd_export(update: Update, context: BotContext) -> None:
    """Export full history. Bug fix: uses `with` for file handle."""
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)
    user_id = update.effective_user.id

    rows = get_full_history(user_id)

    if not rows:
        await update.message.reply_text("No query history to export.")
        return

    lines = []
    for row in rows:
        if len(row) == 8:
            ts, provider, model, cost, query, response, work_dir, error = row
        else:
            ts, model, cost, query, response, work_dir, error = row
            provider = "claude"
        lines.append(
            f"=== {ts} ===\n"
            f"Provider: {provider} | Model: {model} | Cost: ${cost:.4f} | Dir: {work_dir}"
            f"{' | ERROR' if error else ''}\n\n"
            f"QUERY:\n{query}\n\n"
            f"RESPONSE:\n{response}\n"
        )

    content = "\n" + ("=" * 60 + "\n").join(lines)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", prefix="claude_history_", delete=False) as f:
        f.write(content)
        tmp_path = f.name

    try:
        # Bug fix: use `with` to avoid file handle leak
        with open(tmp_path, "rb") as fh:
            await update.message.reply_document(
                document=fh,
                filename=f"claude_history_{user_id}.txt",
                caption=f"Full history: {len(rows)} queries",
            )
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# --- File commands ---


async def cmd_file(update: Update, context: BotContext) -> None:
    """Send a file from the working directory."""
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)
    args = " ".join(context.args) if context.args else ""
    if not args:
        await update.message.reply_text("Usage: /file <path>")
        return

    work_dir = context.user_data["work_dir"]
    target = safe_resolve(args, work_dir)

    if target is None:
        await update.message.reply_text("Access denied: path is outside working directory.")
        return

    if not target.exists():
        await update.message.reply_text(f"File not found: {args}")
        return

    if target.is_dir():
        await update.message.reply_text("That's a directory. Use /ls to list contents.")
        return

    # Check file size (Telegram limit ~50MB)
    size = target.stat().st_size
    if size > 50 * 1024 * 1024:
        await update.message.reply_text(f"File too large ({size / (1024 * 1024):.1f}MB). Telegram limit is 50MB.")
        return

    try:
        with open(target, "rb") as fh:
            await update.message.reply_document(
                document=fh,
                filename=target.name,
                caption=f"📄 {args}",
            )
    except Exception as e:
        await update.message.reply_text(f"Error sending file: {e}")


async def cmd_ls(update: Update, context: BotContext) -> None:
    """List directory contents within work_dir."""
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)
    path_arg = " ".join(context.args) if context.args else None
    work_dir = context.user_data["work_dir"]

    listing, success = list_directory(path_arg, work_dir)

    if success:
        header = f"📁 {path_arg or work_dir}\n\n"
        await send_long_message(update, header + listing)
    else:
        await update.message.reply_text(listing)


# --- Template commands ---


async def cmd_templates(update: Update, context: BotContext) -> None:
    """List available templates."""
    if not auth_check(update):
        return await reject_unauthorized(update)

    _, builtin, user = list_template_names()
    lines = []

    lines.append("Built-in templates:")
    for name in builtin:
        lines.append(f"  • {name}")

    if user:
        lines.append("\nUser templates:")
        for name in user:
            lines.append(f"  • {name}")

    lines.append("\nUsage: /template use <name> [your question]")
    lines.append("       /template add <name> <prompt text>")
    lines.append("       /template del <name>")
    await update.message.reply_text("\n".join(lines))


async def cmd_template(update: Update, context: BotContext) -> None:
    """Manage and use templates."""
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)
    args = context.args
    if not args:
        await cmd_templates(update, context)
        return

    action = args[0].lower()

    if action == "use":
        if len(args) < 2:
            await update.message.reply_text("Usage: /template use <name> [your question]")
            return
        name = args[1]
        template = get_template(name)
        if not template:
            await update.message.reply_text(f"Template '{name}' not found. Use /templates to see available.")
            return

        # Optional user question appended
        user_text = " ".join(args[2:]) if len(args) > 2 else ""
        query = f"{template}\n\n{user_text}" if user_text else template

        user_id = update.effective_user.id
        if not await acquire_rate_limit(user_id):
            await update.message.reply_text("Rate limited. Please wait.")
            return

        await update.message.reply_text(f"Using template: {name}")
        await enqueue(user_id, update, context, query)

    elif action == "add":
        if len(args) < 3:
            await update.message.reply_text("Usage: /template add <name> <prompt text>")
            return
        name = args[1]
        content = " ".join(args[2:])
        try:
            add_template(name, content)
        except ValueError as exc:
            await update.message.reply_text(str(exc))
            return
        await update.message.reply_text(f"Template '{name}' saved under the user namespace.")

    elif action == "del":
        if len(args) < 2:
            await update.message.reply_text("Usage: /template del <name>")
            return
        name = args[1]
        if delete_template(name):
            await update.message.reply_text(f"Template '{name}' deleted.")
        else:
            await update.message.reply_text(f"Cannot delete '{name}' (built-in or not found).")

    else:
        # Treat as "use" shorthand: /template <name> [question]
        name = action
        template = get_template(name)
        if template:
            user_text = " ".join(args[1:]) if len(args) > 1 else ""
            query = f"{template}\n\n{user_text}" if user_text else template

            user_id = update.effective_user.id
            if not await acquire_rate_limit(user_id):
                await update.message.reply_text("Rate limited. Please wait.")
                return

            await update.message.reply_text(f"Using template: {name}")
            await enqueue(user_id, update, context, query)
        else:
            await update.message.reply_text(
                f"Unknown action '{action}'. Use: use, add, del\nOr use template name directly: /template <name>"
            )


async def cmd_skill(update: Update, context: BotContext) -> None:
    """Use an expert skill."""
    if not auth_check(update):
        return await reject_unauthorized(update)

    from koda.skills._index import SkillEmbeddingIndex
    from koda.skills._registry import SkillDefinition, build_skill_registry_from_custom_skills
    from koda.skills._runtime import get_runtime_agent_spec, get_runtime_custom_skills, get_runtime_skill_policy
    from koda.skills._selector import SkillSelector
    from koda.skills._telemetry import emit_skill_invocation

    init_user_data(context.user_data, user_id=update.effective_user.id)
    args = context.args
    agent_spec = get_runtime_agent_spec()
    skill_policy = get_runtime_skill_policy(agent_spec) or None
    registry = build_skill_registry_from_custom_skills(get_runtime_custom_skills(agent_spec), skill_policy)
    skills = registry.get_all()

    if not args:
        # List available skills
        if not skills:
            await update.message.reply_text("No expert skills configured for this agent.")
            return
        lines = ["Expert Skills:"]
        for skill_def in sorted(skills.values(), key=lambda item: item.id):
            label = (
                f"{skill_def.id} - {skill_def.name}"
                if skill_def.name and skill_def.name != skill_def.id
                else skill_def.id
            )
            lines.append(f"  • {label}")
        lines.append("\nUsage: /skill <name> [your question]")
        await update.message.reply_text("\n".join(lines))
        return

    def _resolve_direct_skill(candidate: str) -> SkillDefinition | None:
        skill_id = registry.resolve_alias(candidate.lower().replace(" ", "-")) or registry.resolve_alias(
            candidate.lower()
        )
        resolved = registry.get(skill_id) if skill_id else None
        if resolved is not None:
            return resolved

        normalized_name = candidate.lower().strip()
        normalized_slug = normalized_name.replace(" ", "-")
        return next(
            (
                skill_candidate
                for skill_candidate in skills.values()
                if (
                    skill_candidate.name.lower() == normalized_name
                    or skill_candidate.name.lower().replace(" ", "-") == normalized_slug
                )
            ),
            None,
        )

    name = args[0]
    skill: SkillDefinition | None = None
    consumed_args = 1
    for end in range(len(args), 0, -1):
        candidate_name = " ".join(args[:end])
        skill = _resolve_direct_skill(candidate_name)
        if skill is not None:
            name = candidate_name
            consumed_args = end
            break

    if skill is None:
        try:
            skill_index = SkillEmbeddingIndex()
            skill_index.rebuild(skills)
            selector = SkillSelector(registry, skill_index)
            match = selector.select_by_name_or_query(name)
            if match and match.composite_score >= 0.4:
                skill = match.skill
        except Exception:
            log.exception("skill_command_resolution_failed")

    if skill is None:
        await update.message.reply_text(f"Skill '{name}' not found. Use /skill to see available skills.")
        return

    user_text = " ".join(args[consumed_args:]) if len(args) > consumed_args else ""
    parts: list[str] = []
    if skill.instruction:
        parts.append(f"<instruction>{skill.instruction}</instruction>")
    parts.append(skill.full_content)
    if skill.output_format_enforcement:
        parts.append(f"\n<output_format>{skill.output_format_enforcement}</output_format>")
    template = "\n\n".join(parts)
    query = f"{template}\n\n{user_text}" if user_text else template

    user_id = update.effective_user.id
    if not await acquire_rate_limit(user_id):
        await update.message.reply_text("Rate limited. Please wait.")
        return

    emit_skill_invocation(skill_id=skill.id, explicit=True, user_id=user_id)
    await update.message.reply_text(f"Using skill: {skill.id}")
    await enqueue(user_id, update, context, query)


# --- Bookmark commands ---


async def cmd_bookmarks(update: Update, context: BotContext) -> None:
    """View saved bookmarks."""
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)
    user_id = update.effective_user.id

    rows = get_bookmarks(user_id)
    if not rows:
        await update.message.reply_text("No bookmarks saved. Use the 📌 button on agent responses to bookmark.")
        return

    lines = ["📌 Your bookmarks:\n"]
    for bk_id, text, ts in rows:
        try:
            dt = datetime.fromisoformat(ts)
            ts_fmt = dt.strftime("%m/%d %H:%M")
        except Exception:
            ts_fmt = ts[:16]
        preview = text[:80].replace("\n", " ")
        if len(text) > 80:
            preview += "..."
        lines.append(f"#{bk_id} ({ts_fmt})\n  {preview}\n")

    await send_long_message(update, "\n".join(lines))


async def cmd_delbookmark(update: Update, context: BotContext) -> None:
    """Delete a bookmark by ID."""
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text("Usage: /delbookmark <id>")
        return

    try:
        bk_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid bookmark ID.")
        return

    if delete_bookmark(user_id, bk_id):
        await update.message.reply_text(f"Bookmark #{bk_id} deleted.")
    else:
        await update.message.reply_text(f"Bookmark #{bk_id} not found.")


# --- Session commands ---


async def cmd_sessions(update: Update, context: BotContext) -> None:
    """List saved sessions."""
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)
    user_id = update.effective_user.id

    rows = get_sessions(user_id)
    if not rows:
        await update.message.reply_text("No saved sessions. Sessions are auto-saved when you start conversations.")
        return

    current = context.user_data.get("session_id")
    lines = ["📋 Your sessions:\n"]
    for row in rows:
        if len(row) == 7:
            row_id, session_id, name, provider, last_model, _created_at, last_used = row
        else:
            row_id, session_id, name, _created_at, last_used = row
            provider = None
            last_model = None
        try:
            dt = datetime.fromisoformat(last_used)
            ts_fmt = dt.strftime("%m/%d %H:%M")
        except Exception:
            ts_fmt = last_used[:16] if last_used else "?"
        display_name = name or session_id[:12]
        marker = " ◀ current" if session_id == current else ""
        provider_info = f" | {provider}/{last_model}" if provider and last_model else ""
        lines.append(f"#{row_id} | {display_name}{provider_info} | {ts_fmt}{marker}")

    lines.append("\nUse /session <id> to resume a session.")
    await send_long_message(update, "\n".join(lines))


async def cmd_session(update: Update, context: BotContext) -> None:
    """Resume a saved session by ID."""
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text("Usage: /session <id>")
        return

    try:
        row_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid session ID.")
        return

    row = get_session_by_id(user_id, row_id)
    if not row:
        await update.message.reply_text(f"Session #{row_id} not found.")
        return

    if len(row) == 4:
        session_id, name, provider, model = row
    else:
        session_id, name = row
        provider = None
        model = None
    context.user_data["session_id"] = session_id
    context.user_data["provider_sessions"] = {}
    context.user_data["_supervised_session_id"] = None
    context.user_data["_supervised_provider"] = None
    if provider:
        set_provider(context.user_data, provider)
        if model:
            with contextlib.suppress(ValueError):
                set_provider_model(context.user_data, provider, model)
    display = name or session_id[:12]
    await update.message.reply_text(f"Resumed session: {display}")


async def cmd_name(update: Update, context: BotContext) -> None:
    """Name the current session."""
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)
    user_id = update.effective_user.id
    session_id = context.user_data.get("session_id")

    if not session_id:
        await update.message.reply_text("No active session. Send a message first to start a session.")
        return

    name = " ".join(context.args) if context.args else ""
    if not name:
        await update.message.reply_text("Usage: /name <session name>")
        return

    if rename_session(user_id, session_id, name):
        await update.message.reply_text(f"Session named: {name}")
    else:
        await update.message.reply_text("Could not rename session (not found in database).")


# --- Scheduling commands ---


async def cmd_remind(update: Update, context: BotContext) -> None:
    """Set a reminder."""
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)

    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Usage: /remind <time> <text>\nExample: /remind 30m Check the build")
        return

    from koda.services.scheduler import parse_time_delta, schedule_reminder

    time_str = context.args[0]
    text = " ".join(context.args[1:])

    delta = parse_time_delta(time_str)
    if not delta:
        await update.message.reply_text("Invalid time format. Use: 30s, 5m, 2h, 1d")
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    try:
        msg = await schedule_reminder(cast(Any, context), chat_id, user_id, delta, text)
    except Exception:
        log.exception("reminder_scheduler_create_failed", user_id=user_id, chat_id=chat_id)
        await update.message.reply_text(
            "Could not persist this reminder in the canonical scheduler right now. Please try again shortly."
        )
        return
    await update.message.reply_text(msg)


async def cmd_schedule(update: Update, context: BotContext) -> None:
    """Schedule a recurring query."""
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)

    if not context.args or len(context.args) < 3:
        await update.message.reply_text(
            "Usage: /schedule every <interval> <query>\nExample: /schedule every 2h Check system status"
        )
        return

    from koda.services.scheduler import parse_interval, schedule_recurring

    # Parse "every <interval>" prefix
    if context.args[0].lower() == "every":
        interval_str = f"every {context.args[1]}"
        query = " ".join(context.args[2:])
    else:
        await update.message.reply_text("Usage: /schedule every <interval> <query>")
        return

    interval = parse_interval(interval_str)
    if not interval:
        await update.message.reply_text("Invalid interval. Use: every 30m, every 2h, every 1d")
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    msg = await schedule_recurring(cast(Any, context), chat_id, user_id, interval, query)
    await update.message.reply_text(msg)


async def cmd_jobs(update: Update, context: BotContext) -> None:
    """Inspect and control unified scheduled jobs."""
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)
    user_id = update.effective_user.id

    from koda.services.scheduled_jobs import (
        activate_job,
        delete_job,
        get_job,
        list_job_runs,
        pause_job,
        queue_validation_run,
        resume_job,
        run_job_now,
    )
    from koda.services.scheduler import cancel_user_jobs, list_user_jobs

    args = context.args or []
    if not args or args[0].lower() == "list":
        jobs = list_user_jobs(cast(Any, context), user_id)
        if not jobs:
            await update.message.reply_text("No scheduled jobs found.")
            return
        lines = ["Scheduled jobs:\n"]
        lines.extend(jobs)
        await send_long_message(update, "\n".join(lines))
        return

    action = args[0].lower()
    if len(args) < 2:
        await update.message.reply_text("Usage: /jobs [show|runs|validate|activate|pause|resume|delete|run] <id>")
        return
    if action == "pause" and args[1].lower() == "all":
        paused = cancel_user_jobs(cast(Any, context), user_id)
        await update.message.reply_text(
            f"Paused {paused} active jobs." if paused else "No active jobs were eligible for pause."
        )
        return
    try:
        job_id = int(args[1])
    except ValueError:
        await update.message.reply_text("Job ID must be an integer.")
        return

    if action == "show":
        job_details = get_job(job_id, user_id)
        if not job_details:
            await update.message.reply_text("Job not found.")
            return
        payload = job_details["payload"]
        detail = payload.get("query") or payload.get("text") or payload.get("command") or ""
        await update.message.reply_text(
            f"Job #{job_details['id']}\n"
            f"Type: {job_details['job_type']} / {job_details['trigger_type']}\n"
            f"Status: {job_details['status']}\n"
            f"Schedule: {job_details['schedule_expr']} ({job_details['timezone']})\n"
            f"Provider/model: {job_details.get('provider_preference') or 'n/a'} / "
            f"{job_details.get('model_preference') or 'n/a'}\n"
            f"Work dir: {job_details.get('work_dir') or 'n/a'}\n"
            f"Next run: {job_details.get('next_run_at') or 'pending validation'}\n"
            f"Last success: {job_details.get('last_success_at') or 'n/a'}\n"
            f"Last failure: {job_details.get('last_failure_at') or 'n/a'}\n"
            f"Payload: {detail[:350]}"
        )
        return

    if action == "runs":
        runs = list_job_runs(job_id, user_id, limit=10)
        if not runs:
            await update.message.reply_text("No runs found for this job.")
            return
        lines = [f"Runs for job #{job_id}:\n"]
        for run in runs:
            lines.append(
                f"#{run['id']} [{run['status']}] {run['trigger_reason']} | "
                f"scheduled: {run['scheduled_for']} | task: {run.get('task_id') or 'n/a'} | "
                f"verify: {run.get('verification_status') or 'pending'}"
            )
        await send_long_message(update, "\n".join(lines))
        return

    if action == "validate":
        _run_id, msg = queue_validation_run(job_id, user_id=user_id, activate_on_success=False)
        await update.message.reply_text(msg)
        return

    if action == "activate":
        _ok, msg = activate_job(job_id, user_id)
        await update.message.reply_text(msg)
        return

    if action == "pause":
        _ok, msg = pause_job(job_id, user_id)
        await update.message.reply_text(msg)
        return

    if action == "resume":
        _ok, msg = resume_job(job_id, user_id)
        await update.message.reply_text(msg)
        return

    if action == "delete":
        _ok, msg = delete_job(job_id, user_id)
        await update.message.reply_text(msg)
        return

    if action == "run":
        _run_id, msg = run_job_now(job_id, user_id)
        await update.message.reply_text(msg)
        return

    await update.message.reply_text(
        "Unknown action. Use: list, show, runs, validate, activate, pause, resume, delete, run"
    )


# --- Voice/TTS commands ---


_ELEVENLABS_LANGUAGE_QUERIES = {
    "pt": "portuguese",
    "pt-br": "portuguese",
    "pt-pt": "portuguese",
    "en": "english",
    "en-us": "english",
    "en-gb": "english",
    "es": "spanish",
    "fr": "french",
    "de": "german",
    "it": "italian",
    "ja": "japanese",
}


def _voice_provider_label(provider_id: str) -> str:
    provider = provider_id.strip().lower()
    if provider == "kokoro":
        return "Kokoro local"
    if provider == "elevenlabs":
        return "ElevenLabs"
    return provider or "automatico"


def _voice_current_provider(user_data: dict[str, Any]) -> str:
    provider = str(user_data.get("audio_provider") or "").strip().lower()
    if provider:
        return provider
    voice_id = str(user_data.get("tts_voice") or TTS_DEFAULT_VOICE).strip()
    from koda.services.kokoro_manager import kokoro_voice_metadata
    from koda.utils.tts import AVAILABLE_VOICES

    voice_config = AVAILABLE_VOICES.get(voice_id)
    if voice_config is not None:
        return str(voice_config.engine)
    if kokoro_voice_metadata(voice_id) is not None:
        return "kokoro"
    return "elevenlabs" if len(voice_id) >= 20 and voice_id.isalnum() else "kokoro"


def _voice_as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _voice_as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _voice_format_bytes(value: Any) -> str:
    try:
        size = float(value or 0)
    except (TypeError, ValueError):
        size = 0.0
    units = ("B", "KB", "MB", "GB")
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def _voice_download_status_label(status: str) -> str:
    return {
        "pending": "preparando",
        "running": "baixando",
        "completed": "concluido",
        "error": "erro",
        "cancelled": "cancelado",
        "idle": "nao baixado",
    }.get(str(status or "").strip().lower(), str(status or "desconhecido"))


def _voice_download_compact(job: dict[str, Any] | None) -> str:
    job = _voice_as_dict(job)
    status = str(job.get("status") or "idle").strip().lower()
    if status in {"pending", "running"}:
        percent = float(job.get("progress_percent") or 0.0)
        return f"{_voice_download_status_label(status)} {percent:.0f}%"
    return _voice_download_status_label(status)


def _voice_download_job_from_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = _voice_as_dict(payload)
    active = _voice_as_dict(payload.get("active_job"))
    if active:
        return active
    if "status" in payload and ("downloaded_bytes" in payload or "progress_percent" in payload):
        return payload
    return {}


def _voice_kokoro_model_status() -> dict[str, Any]:
    try:
        from koda.control_plane.manager import get_control_plane_manager

        return dict(get_control_plane_manager().get_kokoro_model_status() or {})
    except Exception:
        log.debug("telegram_voice_kokoro_model_status_fallback", exc_info=True)
        from koda.services.kokoro_manager import kokoro_model_status

        try:
            return {**dict(kokoro_model_status()), "active_job": None}
        except Exception as exc:
            log.debug("telegram_voice_kokoro_model_status_unavailable", error=str(exc))
            return {
                "downloaded": False,
                "bytes": 0,
                "local_path": "",
                "url": "",
                "version": "",
                "active_job": None,
                "last_error": str(exc),
            }


def _voice_kokoro_model_ready(status: dict[str, Any] | None = None) -> bool:
    payload = _voice_as_dict(status) or _voice_kokoro_model_status()
    job = _voice_download_job_from_payload(payload)
    return bool(payload.get("downloaded")) or str(job.get("status") or "").lower() == "completed"


def _voice_kokoro_voice_items(language_id: str = "") -> list[dict[str, Any]]:
    try:
        from koda.control_plane.manager import get_control_plane_manager

        catalog = get_control_plane_manager().get_kokoro_voice_catalog(language=language_id)
        items = [dict(item) for item in _voice_as_list(catalog.get("items")) if isinstance(item, dict)]
        if items:
            return items
    except Exception:
        log.debug("telegram_voice_kokoro_catalog_fallback", language_id=language_id, exc_info=True)

    from koda.services.kokoro_manager import list_kokoro_voices

    try:
        return [dict(item) for item in list_kokoro_voices(language_id)]
    except Exception as exc:
        log.debug("telegram_voice_kokoro_catalog_unavailable", language_id=language_id, error=str(exc))
        return []


def _voice_elevenlabs_model(user_data: dict[str, Any]) -> str:
    provider = str(user_data.get("audio_provider") or "").strip().lower()
    model = str(user_data.get("audio_model") or "").strip()
    if provider == "elevenlabs" and model:
        return model
    return ELEVENLABS_DEFAULT_TTS_MODEL


def _voice_elevenlabs_model_options(user_data: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """Return Telegram-safe ElevenLabs TTS model choices.

    The provider catalog also includes ElevenLabs speech-to-speech,
    text-to-voice, sound-effect and transcription models. Those are valid
    ElevenLabs models, but not safe choices for the Text-to-Speech path used
    by Telegram voice replies.
    """
    allowed_ids = elevenlabs_tts_model_ids()
    static_by_id = {str(item["model_id"]): dict(item) for item in elevenlabs_tts_models()}
    merged = dict(static_by_id)
    selectable = _voice_as_dict((user_data or {}).get("selectable_function_options")).get("audio")
    for item in _voice_as_list(selectable):
        option = _voice_as_dict(item)
        if str(option.get("provider_id") or "").strip().lower() != "elevenlabs":
            continue
        model_id = str(option.get("model_id") or "").strip()
        if model_id not in allowed_ids:
            continue
        merged[model_id] = {
            **static_by_id.get(model_id, {}),
            "model_id": model_id,
            "title": str(option.get("title") or static_by_id.get(model_id, {}).get("title") or model_id),
            "description": str(option.get("description") or static_by_id.get(model_id, {}).get("description") or ""),
            "languages": str(static_by_id.get(model_id, {}).get("languages") or ""),
            "status": str(option.get("status") or static_by_id.get(model_id, {}).get("status") or "current"),
        }
    return [
        merged[str(item["model_id"])] for item in elevenlabs_tts_models() if str(item.get("model_id") or "") in merged
    ]


def _voice_elevenlabs_model_label(model_id: str) -> str:
    return elevenlabs_model_label(model_id)


def _voice_elevenlabs_models_text(user_data: dict[str, Any]) -> str:
    current_model = _voice_elevenlabs_model(user_data)
    lines = [
        "<b>Modelo de voz ElevenLabs</b>",
        "",
        (
            f"Atual: <code>{escape_html(current_model)}</code> "
            f"({escape_html(_voice_elevenlabs_model_label(current_model))})"
        ),
        "",
        "Escolha o modelo usado para sintetizar as respostas em audio no Telegram.",
    ]
    for item in _voice_elevenlabs_model_options(user_data):
        model_id = str(item.get("model_id") or "")
        marker = "•" if model_id != current_model else "• atual"
        status = str(item.get("status") or "").strip().lower()
        status_label = f" · {status}" if status and status not in {"current"} else ""
        languages = str(item.get("languages") or "").strip()
        languages_label = f" · {languages}" if languages else ""
        lines.append(
            f"\n{marker} <b>{escape_html(str(item.get('title') or model_id))}</b>"
            f"{escape_html(status_label)}{escape_html(languages_label)}\n"
            f"<code>{escape_html(model_id)}</code>\n"
            f"{escape_html(str(item.get('description') or ''))}"
        )
    return "\n".join(lines)


def _voice_elevenlabs_models_markup(user_data: dict[str, Any]) -> InlineKeyboardMarkup:
    current_model = _voice_elevenlabs_model(user_data)
    buttons: list[list[InlineKeyboardButton]] = []
    for item in _voice_elevenlabs_model_options(user_data):
        model_id = str(item.get("model_id") or "")
        if not model_id:
            continue
        title = str(item.get("title") or model_id)
        marker = "> " if model_id == current_model else ""
        languages = str(item.get("languages") or "").strip()
        suffix = f" · {languages}" if languages else ""
        buttons.append(
            [
                InlineKeyboardButton(
                    f"{marker}{title}{suffix}"[:64],
                    callback_data=f"voiceelmodel:{model_id}",
                )
            ]
        )
    buttons.append([InlineKeyboardButton("Idiomas do modelo", callback_data="voicelangs:elevenlabs")])
    buttons.append([InlineKeyboardButton("Voltar", callback_data="voicehome")])
    return InlineKeyboardMarkup(buttons)


def _voice_apply_elevenlabs_model_selection(user_data: dict[str, Any], model_id: str) -> dict[str, Any]:
    normalized_model = str(model_id or "").strip()
    available = {str(item.get("model_id") or "") for item in _voice_elevenlabs_model_options(user_data)}
    if normalized_model not in available:
        raise ValueError(f"Modelo ElevenLabs indisponivel para TTS: {normalized_model or 'vazio'}")

    try:
        updated = set_agent_functional_default("audio", "elevenlabs", normalized_model, publish=True)
    except ValueError:
        raise
    except Exception:
        log.warning("telegram_voice_elevenlabs_model_persist_failed", model_id=normalized_model, exc_info=True)
        updated = None

    if updated is not None:
        sync_user_data_with_runtime_settings(user_data, updated)
    user_data["audio_provider"] = "elevenlabs"
    user_data["audio_model"] = normalized_model
    selected_language = canonicalize_elevenlabs_language(
        user_data.get("tts_voice_language") or user_data.get("_voice_pending_elevenlabs_language")
    )
    supported_languages = elevenlabs_languages_for_model(normalized_model)
    supported_codes = {str(item.get("code") or "") for item in supported_languages}
    if selected_language and selected_language not in supported_codes and supported_languages:
        selected_language = str(supported_languages[0].get("code") or "")
        user_data["tts_voice_language"] = selected_language
        user_data["_voice_pending_elevenlabs_language"] = selected_language
    return user_data


def _voice_elevenlabs_catalog(language_id: str = "", user_data: dict[str, Any] | None = None) -> dict[str, Any]:
    model_id = _voice_elevenlabs_model(user_data or {})
    try:
        from koda.control_plane.manager import get_control_plane_manager

        return dict(
            get_control_plane_manager().get_elevenlabs_voice_catalog(
                language=language_id,
                model_id=model_id,
            )
            or {}
        )
    except Exception:
        log.debug("telegram_voice_elevenlabs_catalog_unavailable", language_id=language_id, exc_info=True)
        return {
            "items": [],
            "available_languages": elevenlabs_languages_for_model(model_id),
            "selected_language": canonicalize_elevenlabs_language(language_id),
            "selected_language_label": elevenlabs_language_label(language_id) if language_id else "",
            "model_id": model_id,
            "cached": False,
            "provider_connected": False,
        }


def _voice_elevenlabs_api_available(voice: dict[str, Any]) -> tuple[bool, str]:
    if voice.get("api_available") is False:
        reason = str(voice.get("api_availability_reason") or "").strip()
        return False, reason or "Esta voz nao esta disponivel para uso via API nesta conta."
    return True, ""


def _voice_elevenlabs_voice_entry(
    voice_id: str,
    user_data: dict[str, Any],
    *,
    language_id: str = "",
) -> dict[str, Any]:
    normalized_voice = str(voice_id or "").strip()
    if not normalized_voice:
        return {}
    catalog = _voice_elevenlabs_catalog(language_id or str(user_data.get("tts_voice_language") or ""), user_data)
    for item in _voice_as_list(catalog.get("items")):
        voice = _voice_as_dict(item)
        if str(voice.get("voice_id") or "") == normalized_voice:
            return voice
    if language_id:
        catalog = _voice_elevenlabs_catalog("", user_data)
        for item in _voice_as_list(catalog.get("items")):
            voice = _voice_as_dict(item)
            if str(voice.get("voice_id") or "") == normalized_voice:
                return voice
    return {}


def _voice_kokoro_voice_status(voice_id: str) -> dict[str, Any]:
    normalized_voice = str(voice_id or "").strip().lower()
    try:
        from koda.control_plane.manager import get_control_plane_manager

        return dict(get_control_plane_manager().get_kokoro_voice_status(normalized_voice) or {})
    except Exception:
        log.debug("telegram_voice_kokoro_voice_status_fallback", voice_id=normalized_voice, exc_info=True)

    from koda.services.kokoro_manager import kokoro_voice_file_path, kokoro_voice_metadata

    metadata = kokoro_voice_metadata(normalized_voice)
    if metadata is None:
        return {"voice_id": normalized_voice, "downloaded": False, "active_job": None}
    try:
        path = kokoro_voice_file_path(normalized_voice)
        downloaded = path.exists() and path.stat().st_size > 0
        bytes_on_disk = int(path.stat().st_size) if downloaded else 0
        local_path = str(path) if downloaded else ""
    except Exception as exc:
        log.debug("telegram_voice_kokoro_voice_storage_unavailable", voice_id=normalized_voice, error=str(exc))
        downloaded = False
        bytes_on_disk = 0
        local_path = ""
    return {
        **dict(metadata),
        "downloaded": downloaded,
        "bytes": bytes_on_disk,
        "local_path": local_path,
        "active_job": None,
    }


def _voice_kokoro_voice_ready(voice_id: str, status: dict[str, Any] | None = None) -> bool:
    payload = _voice_as_dict(status) or _voice_kokoro_voice_status(voice_id)
    job = _voice_download_job_from_payload(payload)
    return bool(payload.get("downloaded")) or str(job.get("status") or "").lower() == "completed"


_VOICE_KOKORO_STATUS_CACHE_TTL_SECONDS = 3.0


def _voice_kokoro_status_cache(user_data: dict[str, Any]) -> dict[str, Any]:
    cache = user_data.get("_voice_kokoro_status_cache")
    if not isinstance(cache, dict):
        cache = {}
        user_data["_voice_kokoro_status_cache"] = cache
    return cache


def _voice_cached_kokoro_status(
    user_data: dict[str, Any],
    key: str,
    loader: Any,
) -> dict[str, Any]:
    cache = _voice_kokoro_status_cache(user_data)
    now = time.monotonic()
    cached = _voice_as_dict(cache.get(key))
    if cached and (now - float(cached.get("ts") or 0.0)) <= _VOICE_KOKORO_STATUS_CACHE_TTL_SECONDS:
        return dict(_voice_as_dict(cached.get("payload")))
    payload = dict(loader() or {})
    cache[key] = {"ts": now, "payload": dict(payload)}
    return payload


def _voice_kokoro_model_status_cached(user_data: dict[str, Any]) -> dict[str, Any]:
    return _voice_cached_kokoro_status(user_data, "model", _voice_kokoro_model_status)


def _voice_kokoro_voice_status_cached(user_data: dict[str, Any], voice_id: str) -> dict[str, Any]:
    normalized_voice = str(voice_id or "").strip().lower()
    return _voice_cached_kokoro_status(
        user_data,
        f"voice:{normalized_voice}",
        lambda: _voice_kokoro_voice_status(normalized_voice),
    )


def _voice_download_text(title: str, payload: dict[str, Any], *, ready_label: str, missing_label: str) -> str:
    job = _voice_download_job_from_payload(payload)
    status = str(job.get("status") or ("completed" if payload.get("downloaded") else "idle")).strip().lower()
    downloaded = int(job.get("downloaded_bytes") or payload.get("bytes") or 0)
    total = int(job.get("total_bytes") or downloaded or 0)
    percent = float(job.get("progress_percent") or (100.0 if status == "completed" else 0.0))
    details = _voice_as_dict(job.get("details"))
    message = str(job.get("message") or details.get("message") or "").strip()
    error = str(job.get("last_error") or details.get("last_error") or "").strip()
    local_path = str(job.get("local_path") or details.get("local_path") or payload.get("local_path") or "").strip()

    lines = [f"<b>{escape_html(title)}</b>", "", f"Status: <b>{escape_html(_voice_download_status_label(status))}</b>"]
    if status in {"pending", "running", "completed"} or total:
        lines.append(
            "Progresso: "
            f"<code>{percent:.0f}%</code> "
            f"({escape_html(_voice_format_bytes(downloaded))}/{escape_html(_voice_format_bytes(total))})"
        )
    if local_path:
        lines.append(f"Arquivo: <code>{escape_html(local_path)}</code>")
    if message:
        lines.append(f"\n{escape_html(message)}")
    elif status == "completed":
        lines.append(f"\n{escape_html(ready_label)}")
    elif status == "idle":
        lines.append(f"\n{escape_html(missing_label)}")
    if error:
        lines.append(f"\nErro: <code>{escape_html(error)}</code>")
    return "\n".join(lines)


def _voice_kokoro_voice_download_text(voice_id: str, payload: dict[str, Any] | None = None) -> str:
    status = _voice_as_dict(payload) or _voice_kokoro_voice_status(voice_id)
    voice_name = str(status.get("voice_name") or status.get("name") or _voice_label_for_id(voice_id))
    language = str(status.get("language_label") or status.get("language_id") or _voice_language_for_id(voice_id))
    return _voice_download_text(
        f"Voz Kokoro: {voice_name} ({language})",
        status,
        ready_label="Voz baixada. Ela pode ser usada assim que o modelo Kokoro tambem estiver pronto.",
        missing_label="Esta voz ainda precisa ser baixada para uso local.",
    )


def _voice_kokoro_model_download_text(voice_id: str = "", payload: dict[str, Any] | None = None) -> str:
    status = _voice_as_dict(payload) or _voice_kokoro_model_status()
    text = _voice_download_text(
        "Modelo Kokoro local",
        status,
        ready_label="Modelo Kokoro pronto para sintetizar audio local.",
        missing_label="O modelo base precisa ser baixado antes de usar Kokoro.",
    )
    if voice_id:
        text += f"\n\nVoz escolhida: <code>{escape_html(voice_id)}</code>"
    return text


def _voice_kokoro_voice_download_markup(
    voice_id: str,
    payload: dict[str, Any] | None = None,
) -> InlineKeyboardMarkup:
    status = _voice_as_dict(payload) or _voice_kokoro_voice_status(voice_id)
    job = _voice_download_job_from_payload(status)
    job_status = str(job.get("status") or "").strip().lower()
    language = str(status.get("language_id") or _voice_language_for_id(voice_id) or "")
    buttons: list[list[InlineKeyboardButton]] = []
    if job_status in {"pending", "running"}:
        buttons.append(
            [
                InlineKeyboardButton("Atualizar", callback_data=f"voicedlstatus:{voice_id}"),
                InlineKeyboardButton("Cancelar", callback_data=f"voicedlcancel:{voice_id}"),
            ]
        )
    elif _voice_kokoro_voice_ready(voice_id, status):
        buttons.append([InlineKeyboardButton("Usar voz", callback_data=f"voicepick:{voice_id}")])
    else:
        buttons.append([InlineKeyboardButton("Baixar voz", callback_data=f"voicedl:{voice_id}")])
    buttons.append([InlineKeyboardButton("Vozes do idioma", callback_data=f"voicevoices:kokoro:{language}")])
    buttons.append([InlineKeyboardButton("Voltar", callback_data="voicehome")])
    return InlineKeyboardMarkup(buttons)


def _voice_kokoro_model_download_markup(
    voice_id: str = "",
    payload: dict[str, Any] | None = None,
) -> InlineKeyboardMarkup:
    status = _voice_as_dict(payload) or _voice_kokoro_model_status()
    job = _voice_download_job_from_payload(status)
    job_status = str(job.get("status") or "").strip().lower()
    suffix = f":{voice_id}" if voice_id else ":"
    buttons: list[list[InlineKeyboardButton]] = []
    if job_status in {"pending", "running"}:
        buttons.append(
            [
                InlineKeyboardButton("Atualizar", callback_data=f"voicemodelstatus{suffix}"),
                InlineKeyboardButton("Cancelar", callback_data=f"voicemodelcancel{suffix}"),
            ]
        )
    elif _voice_kokoro_model_ready(status):
        if voice_id:
            buttons.append([InlineKeyboardButton("Continuar com a voz", callback_data=f"voicepick:{voice_id}")])
        else:
            buttons.append([InlineKeyboardButton("Modelo pronto", callback_data="voicemodelstatus:")])
    else:
        buttons.append([InlineKeyboardButton("Baixar modelo Kokoro", callback_data=f"voicemodeldl{suffix}")])
    buttons.append([InlineKeyboardButton("Vozes Kokoro", callback_data="voicevoices:kokoro:")])
    buttons.append([InlineKeyboardButton("Voltar", callback_data="voicehome")])
    return InlineKeyboardMarkup(buttons)


def _voice_label_for_id(voice_id: str, *, fallback: str = "") -> str:
    from koda.services.kokoro_manager import kokoro_voice_metadata
    from koda.utils.tts import AVAILABLE_VOICES

    voice_config = AVAILABLE_VOICES.get(voice_id)
    if voice_config is not None:
        return str(voice_config.label)
    metadata = kokoro_voice_metadata(voice_id)
    if metadata:
        return str(metadata.get("name") or voice_id)
    return fallback or voice_id


def _voice_language_for_id(voice_id: str, *, fallback: str = "") -> str:
    from koda.services.kokoro_manager import kokoro_voice_metadata

    metadata = kokoro_voice_metadata(voice_id)
    if metadata:
        return str(metadata.get("language_id") or fallback)
    return fallback


def _voice_default_for_provider(provider_id: str, user_data: dict[str, Any]) -> tuple[str, str, str]:
    provider = provider_id.strip().lower()
    current_voice = str(user_data.get("tts_voice") or TTS_DEFAULT_VOICE).strip()
    current_label = str(user_data.get("tts_voice_label") or "").strip()
    from koda.services.kokoro_manager import KOKORO_DEFAULT_VOICE_ID, kokoro_voice_metadata
    from koda.utils.tts import AVAILABLE_VOICES

    if provider == "kokoro":
        voice_id = current_voice if kokoro_voice_metadata(current_voice) is not None else KOKORO_DEFAULT_VOICE_ID
        return voice_id, _voice_label_for_id(voice_id), _voice_language_for_id(voice_id, fallback="pt-br")

    if provider == "elevenlabs":
        voice_config = AVAILABLE_VOICES.get(current_voice)
        if voice_config is not None and voice_config.engine == "elevenlabs":
            return current_voice, str(voice_config.label), str(user_data.get("tts_voice_language") or "en")
        if len(current_voice) >= 20 and current_voice.isalnum():
            current_entry = _voice_elevenlabs_voice_entry(
                current_voice,
                user_data,
                language_id=str(user_data.get("tts_voice_language") or ""),
            )
            current_available, _reason = _voice_elevenlabs_api_available(current_entry)
            if current_entry and not current_available:
                catalog = _voice_elevenlabs_catalog(str(user_data.get("tts_voice_language") or ""), user_data)
                for item in _voice_as_list(catalog.get("items")):
                    voice = _voice_as_dict(item)
                    voice_id = str(voice.get("voice_id") or "")
                    available, _reason = _voice_elevenlabs_api_available(voice)
                    if voice_id and available:
                        return (
                            voice_id,
                            str(voice.get("name") or voice_id),
                            str(user_data.get("tts_voice_language") or "en"),
                        )
            return current_voice, current_label or current_voice, str(user_data.get("tts_voice_language") or "en")
        return "brian", _voice_label_for_id("brian"), str(user_data.get("tts_voice_language") or "en")

    raise ValueError("Provider de voz desconhecido. Use kokoro ou elevenlabs.")


def _voice_apply_selection(
    user_data: dict[str, Any],
    voice_id: str,
    *,
    voice_label: str = "",
    voice_language: str = "",
) -> dict[str, Any]:
    normalized_voice = str(voice_id or "").strip()
    if not normalized_voice:
        raise ValueError("A voz precisa ser informada.")

    try:
        updated = set_agent_voice_default(
            normalized_voice,
            voice_label=voice_label,
            voice_language=voice_language,
        )
    except ValueError:
        raise
    except Exception:
        log.warning("telegram_voice_persist_failed", voice_id=normalized_voice, exc_info=True)
        updated = None

    if updated is not None:
        sync_user_data_with_runtime_settings(user_data, updated)
    else:
        from koda.services.kokoro_manager import kokoro_voice_metadata
        from koda.utils.tts import AVAILABLE_VOICES

        voice_config = AVAILABLE_VOICES.get(normalized_voice)
        metadata = kokoro_voice_metadata(normalized_voice)
        provider_id = str(voice_config.engine) if voice_config is not None else ("kokoro" if metadata else "elevenlabs")
        user_data["audio_provider"] = provider_id
        user_data["audio_model"] = (
            "kokoro-v1" if provider_id == "kokoro" else str(user_data.get("audio_model") or "eleven_flash_v2_5")
        )
        user_data["tts_voice"] = normalized_voice
        user_data["tts_voice_label"] = voice_label or _voice_label_for_id(normalized_voice)
        user_data["tts_voice_language"] = voice_language or _voice_language_for_id(
            normalized_voice,
            fallback=str(user_data.get("tts_voice_language") or ""),
        )

    user_data["audio_response"] = True
    user_data["tts_enabled"] = True
    user_data["_audio_response_user_override"] = True
    return user_data


def _voice_apply_provider_selection(user_data: dict[str, Any], provider_id: str) -> dict[str, Any]:
    voice_id, voice_label, voice_language = _voice_default_for_provider(provider_id, user_data)
    return _voice_apply_selection(
        user_data,
        voice_id,
        voice_label=voice_label,
        voice_language=voice_language,
    )


def _voice_set_session_enabled(user_data: dict[str, Any], enabled: bool) -> dict[str, Any]:
    try:
        updated = set_agent_voice_policy_enabled(enabled)
    except Exception:
        log.warning("telegram_voice_policy_persist_failed", enabled=enabled, exc_info=True)
        updated = None
    if updated is not None:
        sync_user_data_with_runtime_settings(user_data, updated)
    user_data["audio_response"] = enabled
    user_data["_audio_response_user_override"] = True
    user_data["voice_policy_active"] = enabled
    user_data["voice_policy_mode"] = "voice_active" if enabled else "disabled"
    user_data["tts_enabled"] = bool(enabled)
    return user_data


def _voice_session_enabled(user_data: dict[str, Any]) -> bool:
    mode = str(user_data.get("voice_policy_mode") or "").strip().lower()
    policy_active = bool(user_data.get("voice_policy_active")) or mode in {"tts", "voice_active"}
    return bool(user_data.get("audio_response")) or policy_active


def _voice_home_text(user_data: dict[str, Any]) -> str:
    enabled = _voice_session_enabled(user_data)
    voice_id = str(user_data.get("tts_voice") or TTS_DEFAULT_VOICE)
    voice_label = str(user_data.get("tts_voice_label") or _voice_label_for_id(voice_id))
    provider = _voice_current_provider(user_data)
    language = str(user_data.get("tts_voice_language") or _voice_language_for_id(voice_id) or "n/a")
    extra = ""
    if provider == "kokoro":
        model_status = _voice_kokoro_model_status_cached(user_data)
        model_job = _voice_download_job_from_payload(model_status)
        model_state = (
            _voice_download_compact(model_job)
            if model_job
            else ("pronto" if _voice_kokoro_model_ready(model_status) else "nao baixado")
        )
        voice_status = _voice_kokoro_voice_status_cached(user_data, voice_id)
        voice_job = _voice_download_job_from_payload(voice_status)
        voice_state = (
            _voice_download_compact(voice_job)
            if voice_job
            else ("baixada" if _voice_kokoro_voice_ready(voice_id, voice_status) else "nao baixada")
        )
        extra = (
            "\n"
            f"Modelo Kokoro: <code>{escape_html(model_state)}</code>\n"
            f"Voz local: <code>{escape_html(voice_state)}</code>"
        )
    elif provider == "elevenlabs":
        model = _voice_elevenlabs_model(user_data)
        extra = f"\nModelo: <code>{escape_html(model)}</code> ({escape_html(_voice_elevenlabs_model_label(model))})"
    return (
        "<b>Voz e TTS</b>\n\n"
        f"Estado: <b>{'ligado' if enabled else 'desligado'}</b>\n"
        f"Provider: <code>{escape_html(_voice_provider_label(provider))}</code>\n"
        f"Idioma: <code>{escape_html(language)}</code>\n"
        f"Voz: <code>{escape_html(voice_id)}</code> ({escape_html(voice_label)})"
        f"{extra}\n\n"
        "Use os botoes abaixo ou os atalhos:\n"
        "<code>/voice on</code>, <code>/voice off</code>, <code>/voice provider kokoro</code>, "
        "<code>/voice model eleven_flash_v2_5</code>, <code>/voice language pt-br</code>, "
        "<code>/voice search portugues feminino</code>."
    )


def _voice_home_markup(user_data: dict[str, Any]) -> InlineKeyboardMarkup:
    enabled = _voice_session_enabled(user_data)
    provider = _voice_current_provider(user_data)
    buttons: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                "Desligar" if enabled else "Ligar",
                callback_data=f"voicetoggle:{'off' if enabled else 'on'}",
            )
        ],
        [InlineKeyboardButton(f"Provider: {_voice_provider_label(provider)}", callback_data="voiceproviders")],
        [
            InlineKeyboardButton("Idioma", callback_data=f"voicelangs:{provider}"),
            InlineKeyboardButton("Voz", callback_data=f"voicevoices:{provider}:"),
        ],
    ]
    if provider == "kokoro":
        model_status = _voice_kokoro_model_status_cached(user_data)
        model_job = _voice_download_job_from_payload(model_status)
        if model_job and str(model_job.get("status") or "").lower() in {"pending", "running"}:
            model_label = f"Modelo Kokoro: {_voice_download_compact(model_job)}"
            model_callback = "voicemodelstatus:"
        elif _voice_kokoro_model_ready(model_status):
            model_label = "Modelo Kokoro pronto"
            model_callback = "voicemodelstatus:"
        else:
            model_label = "Baixar modelo Kokoro"
            model_callback = "voicemodeldl:"
        buttons.append([InlineKeyboardButton(model_label, callback_data=model_callback)])
    elif provider == "elevenlabs":
        model = _voice_elevenlabs_model(user_data)
        buttons.append(
            [
                InlineKeyboardButton(
                    f"Modelo: {_voice_elevenlabs_model_label(model)}",
                    callback_data="voiceelmodels",
                )
            ]
        )
    buttons.append(
        [
            InlineKeyboardButton("Kokoro local", callback_data="voiceprovider:kokoro"),
            InlineKeyboardButton("ElevenLabs", callback_data="voiceprovider:elevenlabs"),
        ]
    )
    return InlineKeyboardMarkup(buttons)


def _voice_providers_markup(user_data: dict[str, Any]) -> InlineKeyboardMarkup:
    current = _voice_current_provider(user_data)
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"{'> ' if current == 'kokoro' else ''}Kokoro local",
                    callback_data="voiceprovider:kokoro",
                )
            ],
            [
                InlineKeyboardButton(
                    f"{'> ' if current == 'elevenlabs' else ''}ElevenLabs",
                    callback_data="voiceprovider:elevenlabs",
                )
            ],
            [InlineKeyboardButton("Voltar", callback_data="voicehome")],
        ]
    )


def _voice_languages_markup(provider_id: str, user_data: dict[str, Any] | None = None) -> InlineKeyboardMarkup:
    provider = provider_id.strip().lower()
    buttons: list[list[InlineKeyboardButton]] = []
    if provider == "kokoro":
        from koda.services.kokoro_manager import kokoro_voice_languages

        buttons = [
            [InlineKeyboardButton(str(item["label"]), callback_data=f"voicelang:kokoro:{item['id']}")]
            for item in kokoro_voice_languages()
        ]
    else:
        catalog = _voice_elevenlabs_catalog(user_data=user_data)
        languages = [
            _voice_as_dict(item)
            for item in _voice_as_list(catalog.get("available_languages"))
            if _voice_as_dict(item).get("code")
        ]
        if not languages:
            languages = elevenlabs_languages_for_model(_voice_elevenlabs_model(user_data or {}))
        for index in range(0, len(languages), 2):
            row = []
            for item in languages[index : index + 2]:
                language_id = str(item["code"])
                label = str(item.get("label") or elevenlabs_language_label(language_id))
                row.append(InlineKeyboardButton(label, callback_data=f"voicelang:elevenlabs:{language_id}"))
            buttons.append(row)
    buttons.append([InlineKeyboardButton("Voltar", callback_data="voicehome")])
    return InlineKeyboardMarkup(buttons)


def _voice_voices_markup(provider_id: str, language_id: str, user_data: dict[str, Any]) -> InlineKeyboardMarkup:
    provider = provider_id.strip().lower()
    current_voice = str(user_data.get("tts_voice") or "")
    buttons: list[list[InlineKeyboardButton]] = []
    if provider == "kokoro":
        model_status = _voice_kokoro_model_status()
        model_job = _voice_download_job_from_payload(model_status)
        if model_job and str(model_job.get("status") or "").lower() in {"pending", "running"}:
            model_label = f"Modelo Kokoro: {_voice_download_compact(model_job)}"
            model_callback = "voicemodelstatus:"
        elif _voice_kokoro_model_ready(model_status):
            model_label = "Modelo Kokoro pronto"
            model_callback = "voicemodelstatus:"
        else:
            model_label = "Baixar modelo Kokoro"
            model_callback = "voicemodeldl:"
        buttons.append([InlineKeyboardButton(model_label, callback_data=model_callback)])

        for item in _voice_kokoro_voice_items(language_id)[:40]:
            voice_id = str(item["voice_id"])
            name = str(item.get("name") or voice_id)
            marker = "> " if voice_id == current_voice else ""
            active_job = _voice_as_dict(item.get("active_job"))
            if active_job and str(active_job.get("status") or "").lower() in {"pending", "running"}:
                label = f"{marker}{name} ({_voice_download_compact(active_job)})"
                callback_data = f"voicedlstatus:{voice_id}"
            elif bool(item.get("downloaded")):
                label = f"{marker}{name}"
                callback_data = f"voicepick:{voice_id}"
            else:
                label = f"{marker}Baixar {name}"
                callback_data = f"voicedl:{voice_id}"
            buttons.append(
                [
                    InlineKeyboardButton(
                        label,
                        callback_data=callback_data,
                    )
                ]
            )
    else:
        selected_language = canonicalize_elevenlabs_language(language_id or user_data.get("tts_voice_language"))
        if selected_language:
            user_data["_voice_pending_elevenlabs_language"] = selected_language
        catalog = _voice_elevenlabs_catalog(selected_language, user_data)
        for item in _voice_as_list(catalog.get("items"))[:40]:
            voice = _voice_as_dict(item)
            voice_id = str(voice.get("voice_id") or "")
            if not voice_id:
                continue
            name = str(voice.get("name") or voice_id)
            marker = "> " if voice_id == current_voice else ""
            details = []
            for key in ("gender", "accent", "category"):
                value = str(voice.get(key) or "").strip()
                if value:
                    details.append(value)
            if selected_language and not bool(voice.get("language_match")):
                details.append("modelo compativel")
            available, _reason = _voice_elevenlabs_api_available(voice)
            if not available:
                details.append("requer plano pago")
            suffix = f" ({', '.join(details)})" if details else ""
            callback_name = name.replace(":", " ")[:20]
            buttons.append(
                [
                    InlineKeyboardButton(
                        f"{marker}{name[:36]}{suffix}"[:64],
                        callback_data=f"voiceel:{voice_id}:{callback_name}",
                    )
                ]
            )
        if not buttons:
            buttons.append([InlineKeyboardButton("Conferir idiomas ElevenLabs", callback_data="voicelangs:elevenlabs")])
        buttons.append([InlineKeyboardButton("Pesquisar ElevenLabs", callback_data="voicelang:elevenlabs:pt")])
    buttons.append([InlineKeyboardButton("Idiomas", callback_data=f"voicelangs:{provider}")])
    buttons.append([InlineKeyboardButton("Voltar", callback_data="voicehome")])
    return InlineKeyboardMarkup(buttons)


def _voice_elevenlabs_language_query(language_id: str) -> str:
    raw = language_id.strip().lower()
    canonical = canonicalize_elevenlabs_language(raw)
    return _ELEVENLABS_LANGUAGE_QUERIES.get(raw) or _ELEVENLABS_LANGUAGE_QUERIES.get(canonical, canonical or "voice")


async def cmd_voice(update: Update, context: BotContext) -> None:
    """Toggle voice responses or configure TTS voice."""
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)
    settings = get_agent_runtime_settings()
    if settings is not None:
        sync_user_data_with_runtime_settings(context.user_data, settings)

    args = context.args
    from koda.services.kokoro_manager import kokoro_voice_metadata, list_kokoro_voices
    from koda.utils.tts import AVAILABLE_VOICES

    def _voice_label(ud: dict[str, Any]) -> str:
        voice = ud.get("tts_voice", TTS_DEFAULT_VOICE)
        vc = AVAILABLE_VOICES.get(voice)
        if vc:
            return str(vc.label)
        metadata = kokoro_voice_metadata(str(voice))
        if metadata:
            return str(metadata.get("name") or voice)
        return str(ud.get("tts_voice_label", voice))

    if not args or args[0].lower() in {"status", "config", "settings", "menu"}:
        await update.message.reply_text(
            _voice_home_text(context.user_data),
            parse_mode=ParseMode.HTML,
            reply_markup=_voice_home_markup(context.user_data),
        )
        return

    arg = args[0].lower()

    if arg == "toggle":
        current = _voice_session_enabled(context.user_data)
        _voice_set_session_enabled(context.user_data, not current)
        state = "ON" if not current else "OFF"
        voice = context.user_data.get("tts_voice", TTS_DEFAULT_VOICE)
        msg = f"Voice responses: <b>{state}</b>"
        if not current:
            msg += f"\nVoice: <code>{escape_html(voice)}</code> ({escape_html(_voice_label(context.user_data))})"
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return

    if arg == "on":
        _voice_set_session_enabled(context.user_data, True)
        voice = context.user_data.get("tts_voice", TTS_DEFAULT_VOICE)
        await update.message.reply_text(
            "Voice responses: <b>ON</b>\n"
            f"Voice: <code>{escape_html(voice)}</code> "
            f"({escape_html(_voice_label(context.user_data))})",
            parse_mode=ParseMode.HTML,
        )
    elif arg == "off":
        _voice_set_session_enabled(context.user_data, False)
        await update.message.reply_text("Voice responses: <b>OFF</b>", parse_mode=ParseMode.HTML)
    elif arg == "provider":
        if len(args) < 2:
            await update.message.reply_text(
                "Escolha o provider de voz:",
                reply_markup=_voice_providers_markup(context.user_data),
            )
            return
        provider = args[1].strip().lower()
        try:
            _voice_apply_provider_selection(context.user_data, provider)
        except ValueError as exc:
            await update.message.reply_text(str(exc))
            return
        await update.message.reply_text(
            _voice_home_text(context.user_data),
            parse_mode=ParseMode.HTML,
            reply_markup=_voice_home_markup(context.user_data),
        )
    elif arg in {"model", "modelo"}:
        if len(args) < 2:
            await update.message.reply_text(
                _voice_elevenlabs_models_text(context.user_data),
                parse_mode=ParseMode.HTML,
                reply_markup=_voice_elevenlabs_models_markup(context.user_data),
            )
            return
        model_id = args[1].strip()
        try:
            _voice_apply_elevenlabs_model_selection(context.user_data, model_id)
        except ValueError as exc:
            await update.message.reply_text(str(exc))
            return
        await update.message.reply_text(
            _voice_home_text(context.user_data),
            parse_mode=ParseMode.HTML,
            reply_markup=_voice_home_markup(context.user_data),
        )
    elif arg in {"language", "lang", "idioma"}:
        provider = _voice_current_provider(context.user_data)
        if len(args) < 2:
            await update.message.reply_text(
                f"Escolha o idioma para {_voice_provider_label(provider)}:",
                reply_markup=_voice_languages_markup(provider, context.user_data),
            )
            return
        language = args[1].strip().lower()
        if provider == "kokoro":
            await update.message.reply_text(
                f"Vozes Kokoro para <code>{escape_html(language)}</code>:",
                parse_mode=ParseMode.HTML,
                reply_markup=_voice_voices_markup("kokoro", language, context.user_data),
            )
            return
        context.user_data["_voice_pending_elevenlabs_language"] = canonicalize_elevenlabs_language(language)
        catalog = _voice_elevenlabs_catalog(language, context.user_data)
        language_label = str(catalog.get("selected_language_label") or language)
        voices = [item for item in _voice_as_list(catalog.get("items")) if _voice_as_dict(item).get("voice_id")]
        if not bool(catalog.get("provider_connected")):
            text = (
                "A conexao ElevenLabs ainda nao esta pronta para listar vozes.\n"
                "Cadastre e verifique a API key do ElevenLabs, depois tente novamente."
            )
        elif not voices:
            query = _voice_elevenlabs_language_query(language)
            text = (
                f"Nao encontrei vozes ElevenLabs no catalogo para <b>{escape_html(language_label)}</b>.\n"
                f"Voce ainda pode tentar pelo texto: <code>/voice search {escape_html(query)}</code>."
            )
        else:
            text = f"Vozes ElevenLabs para <b>{escape_html(language_label)}</b>:"
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=_voice_voices_markup("elevenlabs", language, context.user_data),
        )
    elif arg == "voices":
        provider_filter = args[1].strip().lower() if len(args) > 1 else ""
        language_filter = args[2].strip().lower() if len(args) > 2 else ""
        lines = ["Available voices:\n"]
        current_voice = context.user_data.get("tts_voice", TTS_DEFAULT_VOICE)
        if provider_filter in {"", "elevenlabs"}:
            catalog = _voice_elevenlabs_catalog(language_filter, context.user_data)
            elevenlabs_items = [
                _voice_as_dict(item)
                for item in _voice_as_list(catalog.get("items"))
                if _voice_as_dict(item).get("voice_id")
            ]
            lines.append("\n<b>☁️ ElevenLabs:</b>")
            if not bool(catalog.get("provider_connected")):
                lines.append("  API key ausente ou conexao ainda nao verificada.")
            elif not elevenlabs_items:
                selected_label = str(catalog.get("selected_language_label") or language_filter or "catalogo")
                lines.append(f"  Nenhuma voz encontrada para {escape_html(selected_label)}.")
            else:
                for item in elevenlabs_items[:40]:
                    voice_id = str(item["voice_id"])
                    marker = " ◀" if voice_id == current_voice else ""
                    details = ", ".join(
                        value
                        for value in (
                            str(item.get("gender") or ""),
                            str(item.get("accent") or ""),
                            str(item.get("category") or ""),
                            "requer plano pago" if item.get("api_available") is False else "",
                        )
                        if value
                    )
                    suffix = f" ({escape_html(details)})" if details else ""
                    lines.append(
                        f"  <code>{escape_html(voice_id)}</code> — "
                        f"{escape_html(str(item.get('name') or voice_id))}{suffix}{marker}"
                    )
        kokoro_languages: dict[str, list[dict[str, Any]]] = {}
        for item in list_kokoro_voices(language_filter if provider_filter in {"", "kokoro"} else ""):
            kokoro_languages.setdefault(str(item["language_label"]), []).append(item)
        if kokoro_languages and provider_filter in {"", "kokoro"}:
            lines.append("\n<b>💻 Kokoro (local):</b>")
            for language_label, items in kokoro_languages.items():
                lines.append(f"\n<i>{escape_html(language_label)}</i>")
                for item in items:
                    voice_id = str(item["voice_id"])
                    marker = " ◀" if voice_id == current_voice else ""
                    downloaded = "" if bool(item.get("downloaded")) else " ⬇"
                    lines.append(
                        f"  <code>{escape_html(voice_id)}</code> — "
                        f"{escape_html(str(item.get('name') or voice_id))}{downloaded}{marker}"
                    )
        # Show custom ElevenLabs voice if active and not in preset list
        if (
            current_voice not in AVAILABLE_VOICES
            and kokoro_voice_metadata(str(current_voice)) is None
            and context.user_data.get("tts_voice_label")
        ):
            custom_label = context.user_data["tts_voice_label"]
            lines.append("\n<b>🎯 Custom (via search):</b>")
            lines.append(f"  <code>{escape_html(current_voice)}</code> — {escape_html(custom_label)} ◀")
        lines.append("\nUsage: /voice <voice_id> or /voice search <query>")
        lines.append("No Kokoro, use os botoes de baixar para acompanhar o status do modelo e da voz local.")
        current_provider = provider_filter or _voice_current_provider(context.user_data)
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=_voice_voices_markup(current_provider, language_filter, context.user_data),
        )
    elif arg == "search":
        query = " ".join(args[1:]) if len(args) > 1 else ""
        if not query:
            await update.message.reply_text("Usage: /voice search <query>\nExample: /voice search portuguese female")
            return

        from koda.utils.tts import search_elevenlabs_voices

        await update.message.reply_text(
            f"Searching ElevenLabs voices for: <i>{escape_html(query)}</i>...", parse_mode=ParseMode.HTML
        )
        voices = await search_elevenlabs_voices(query)
        if not voices:
            await update.message.reply_text("No voices found. Try a different query.")
            return

        current_voice = context.user_data.get("tts_voice", TTS_DEFAULT_VOICE)
        lines = [f"🔍 Results for <i>{escape_html(query)}</i>:\n"]
        buttons = []
        for v in voices:
            voice_details: list[str] = []
            if v.gender:
                voice_details.append(v.gender)
            if v.accent:
                voice_details.append(v.accent)
            if v.language:
                voice_details.append(v.language)
            detail_str = f" ({', '.join(voice_details)})" if voice_details else ""
            marker = " ◀" if v.voice_id == current_voice else ""
            lines.append(f"  <b>{escape_html(v.name)}</b>{detail_str}{marker}")

            btn_label = f"{v.name}"
            if v.gender:
                btn_label += f" ({v.gender})"
            # Callback data max 64 bytes — truncate name if needed
            cb_data = f"voiceel:{v.voice_id}:{v.name[:20]}"
            buttons.append([InlineKeyboardButton(btn_label, callback_data=cb_data)])

        lines.append("\nTap a button to select:")
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    elif arg in AVAILABLE_VOICES or kokoro_voice_metadata(arg) is not None:
        voice_config = AVAILABLE_VOICES.get(arg)
        voice_label = str(voice_config.label) if voice_config is not None else ""
        voice_language = ""
        metadata = kokoro_voice_metadata(arg)
        if metadata:
            voice_label = str(metadata.get("name") or voice_label or arg)
            voice_language = str(metadata.get("language_id") or "") if metadata else ""
            voice_status = _voice_kokoro_voice_status(arg)
            if not _voice_kokoro_voice_ready(arg, voice_status):
                await update.message.reply_text(
                    _voice_kokoro_voice_download_text(arg, voice_status),
                    parse_mode=ParseMode.HTML,
                    reply_markup=_voice_kokoro_voice_download_markup(arg, voice_status),
                )
                return
            model_status = _voice_kokoro_model_status()
            if not _voice_kokoro_model_ready(model_status):
                await update.message.reply_text(
                    _voice_kokoro_model_download_text(arg, model_status),
                    parse_mode=ParseMode.HTML,
                    reply_markup=_voice_kokoro_model_download_markup(arg, model_status),
                )
                return
        elif not voice_label:
            voice_label = arg
        try:
            _voice_apply_selection(context.user_data, arg, voice_label=voice_label, voice_language=voice_language)
        except ValueError as exc:
            await update.message.reply_text(str(exc))
            return
        await update.message.reply_text(f"Voice set to: <code>{arg}</code> ({voice_label})", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(
            f"Unknown option: {arg}\n\nUsage:\n"
            "/voice - abrir painel de configuracao\n"
            "/voice toggle - ligar/desligar\n"
            "/voice on|off - definir explicitamente\n"
            "/voice provider kokoro|elevenlabs - escolher provider\n"
            "/voice model <id> - escolher modelo TTS ElevenLabs\n"
            "/voice language <id> - escolher idioma/voz\n"
            "/voice voices - listar vozes disponiveis\n"
            "/voice search <query> - buscar vozes ElevenLabs\n"
            "/voice <voice_id> - alterar voz"
        )


# --- Memory commands ---


async def cmd_knowledge(update: Update, context: BotContext) -> None:
    """Review learned knowledge candidates and registered sources."""
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)
    user_id = update.effective_user.id
    if not _is_knowledge_admin(user_id):
        await update.message.reply_text("Access denied: knowledge review is restricted to operators.")
        return

    command = context.args[0].lower() if context.args else "review"
    filters, _unused = _parse_memory_filter_tokens(context.args[1:] if len(context.args) > 1 else [])
    agent_id, scope_error = _resolve_knowledge_agent_scope(filters.get("agent"), user_id)
    if scope_error:
        await update.message.reply_text(scope_error)
        return

    if command == "review":
        candidates = list_knowledge_candidates(agent_id=agent_id, review_status="pending", limit=20)
        if not candidates:
            await update.message.reply_text("No pending knowledge candidates.")
            return
        lines = ["🧠 Pending knowledge candidates\n"]
        for candidate in candidates:
            lines.append(
                f"<b>#{candidate['id']}</b> [{escape_html(candidate['task_kind'])}] "
                f"{escape_html(candidate['candidate_type'])}\n"
                f"  support: {candidate['support_count']} | success: {candidate['success_count']} | "
                f"failure: {candidate['failure_count']} | confidence: {candidate['confidence_score']:.2f}\n"
                f"  {escape_html(candidate['summary'][:180])}\n"
            )
        lines.append("\nUse /knowledge approve <id> or /knowledge reject <id>.")
        await send_long_message(update, "\n".join(lines), parse_mode=ParseMode.HTML)
        return

    if command == "diff":
        if len(context.args) < 2:
            await update.message.reply_text("Usage: /knowledge diff <candidate_id>")
            return
        try:
            candidate_id = int(context.args[1])
        except ValueError:
            await update.message.reply_text("Candidate id must be an integer.")
            return
        candidate_details = get_knowledge_candidate(candidate_id)
        if not candidate_details:
            await update.message.reply_text(f"Candidate #{candidate_id} was not found.")
            return
        lines = [f"🧠 Candidate diff #{candidate_id}\n"]
        lines.append(f"<b>Task kind:</b> {escape_html(candidate_details['task_kind'])}")
        lines.append(f"<b>Type:</b> {escape_html(candidate_details['candidate_type'])}")
        lines.append(f"<b>Summary:</b> {escape_html(candidate_details['summary'])}")
        if candidate_details["diff_summary"]:
            lines.append(f"<b>Diff summary:</b> {escape_html(candidate_details['diff_summary'])}")
        proposed = cast(dict[str, Any], candidate_details["proposed_runbook"] or {})
        if proposed:
            lines.append(f"<b>Proposed title:</b> {escape_html(str(proposed.get('title') or '-'))}")
            steps = [str(item) for item in proposed.get("steps", [])[:5]]
            if steps:
                lines.append("<b>Steps:</b>")
                lines.extend(f"  • {escape_html(step)}" for step in steps)
        await send_long_message(update, "\n".join(lines), parse_mode=ParseMode.HTML)
        return

    if command == "approve":
        if len(context.args) < 2:
            await update.message.reply_text("Usage: /knowledge approve <candidate_id>")
            return
        try:
            candidate_id = int(context.args[1])
        except ValueError:
            await update.message.reply_text("Candidate id must be an integer.")
            return
        promoted_kind = "Runbook"
        with contextlib.suppress(Exception):
            risk_candidate = get_knowledge_candidate(candidate_id)
            if risk_candidate and risk_candidate.get("candidate_type") == "risk_pattern":
                promoted_kind = "Guardrail"
        promoted_id = approve_knowledge_candidate(candidate_id, reviewer=f"user:{user_id}")
        if promoted_id is None:
            await update.message.reply_text(f"Candidate #{candidate_id} was not found or is no longer approvable.")
            return
        from koda.services.metrics import CANDIDATE_PROMOTIONS

        CANDIDATE_PROMOTIONS.labels(agent_id=agent_id or "default", status="approved").inc()
        await update.message.reply_text(
            f"Approved candidate #{candidate_id}. {promoted_kind} #{promoted_id} is now active."
        )
        return

    if command == "revalidate":
        if len(context.args) < 2:
            await update.message.reply_text("Usage: /knowledge revalidate <runbook_id> [agent:<id>]")
            return
        try:
            runbook_id = int(context.args[1])
        except ValueError:
            await update.message.reply_text("Runbook id must be an integer.")
            return
        if not revalidate_approved_runbook(runbook_id, reviewer=f"user:{user_id}"):
            await update.message.reply_text(f"Runbook #{runbook_id} was not found.")
            return
        await update.message.reply_text(f"Runbook #{runbook_id} marked as approved after manual revalidation.")
        return

    if command == "reject":
        if len(context.args) < 2:
            await update.message.reply_text("Usage: /knowledge reject <candidate_id>")
            return
        try:
            candidate_id = int(context.args[1])
        except ValueError:
            await update.message.reply_text("Candidate id must be an integer.")
            return
        if not reject_knowledge_candidate(candidate_id, reviewer=f"user:{user_id}"):
            await update.message.reply_text(f"Candidate #{candidate_id} was not found.")
            return
        from koda.services.metrics import CANDIDATE_PROMOTIONS

        CANDIDATE_PROMOTIONS.labels(agent_id=agent_id or "default", status="rejected").inc()
        await update.message.reply_text(f"Rejected candidate #{candidate_id}.")
        return

    if command == "runbooks":
        runbooks = list_approved_runbooks(agent_id=agent_id, status=None, enforce_valid_window=False, limit=30)
        if not runbooks:
            await update.message.reply_text("No runbooks found.")
            return
        governance = get_latest_runbook_governance_actions(
            [int(runbook["id"]) for runbook in runbooks if isinstance(runbook.get("id"), (int, str))],
            agent_id=agent_id,
        )
        lines = [f"📘 Approved runbooks\n  agent: {escape_html(str(agent_id or 'default'))}\n"]
        for runbook in runbooks:
            latest = governance.get(int(runbook["id"]), {})
            approved_at = str(runbook.get("approved_at") or "-")[:19]
            approved_by = str(runbook.get("approved_by") or "-")
            validated_at = str(runbook.get("last_validated_at") or runbook.get("approved_at") or "-")[:19]
            validated_by = str(runbook.get("last_validated_by") or runbook.get("approved_by") or "-")
            lines.append(
                f"<b>#{runbook['id']}</b> v{runbook['version']} [{escape_html(runbook['task_kind'])}] "
                f"{escape_html(runbook['title'])}\n"
                f"  status: {escape_html(runbook['status'])} | lifecycle: {escape_html(runbook['lifecycle_status'])} | "
                f"project: {escape_html(runbook['project_key'] or '-')}\n"
                f"  approved: {escape_html(approved_at)} by {escape_html(approved_by)}\n"
                f"  last validated: {escape_html(validated_at)} by {escape_html(validated_by)}\n"
                + (
                    f"  last governance: {escape_html(str(latest.get('action') or '-'))} | "
                    f"{escape_html(str(latest.get('reason') or '-'))}\n"
                    if latest
                    else ""
                )
            )
        await send_long_message(update, "\n".join(lines), parse_mode=ParseMode.HTML)
        return

    if command == "health":
        runbooks = list_approved_runbooks(agent_id=agent_id, status=None, enforce_valid_window=False, limit=200)
        governance = get_latest_runbook_governance_actions(
            [int(runbook["id"]) for runbook in runbooks if isinstance(runbook.get("id"), (int, str))],
            agent_id=agent_id,
        )
        by_status: dict[str, int] = {}
        for runbook in runbooks:
            lifecycle = str(runbook.get("lifecycle_status") or runbook.get("status") or "approved")
            by_status[lifecycle] = by_status.get(lifecycle, 0) + 1
        lines = [f"🩺 Runbook health\n  agent: {escape_html(str(agent_id or 'default'))}\n"]
        for status_key in ("approved", "needs_review", "expired", "deprecated"):
            lines.append(f"  • {status_key}: {by_status.get(status_key, 0)}")
        review_samples = [
            runbook
            for runbook in runbooks
            if str(runbook.get("lifecycle_status") or runbook.get("status")) != "approved"
        ][:8]
        if review_samples:
            lines.append("\nRequires attention:")
            for runbook in review_samples:
                latest = governance.get(int(runbook["id"]), {})
                validated_at = str(runbook.get("last_validated_at") or runbook.get("approved_at") or "-")[:19]
                lines.append(
                    f"  • #{runbook['id']} {runbook['title']} "
                    f"[{runbook.get('lifecycle_status') or runbook.get('status')}]: "
                    f"{latest.get('reason') or 'no governance reason'} "
                    f"(last validated {validated_at})"
                )
        await send_long_message(update, "\n".join(lines), parse_mode=ParseMode.HTML)
        return

    if command == "deprecate":
        if len(context.args) < 2:
            await update.message.reply_text("Usage: /knowledge deprecate <runbook_id> [agent:<id>]")
            return
        try:
            runbook_id = int(context.args[1])
        except ValueError:
            await update.message.reply_text("Runbook id must be an integer.")
            return
        if not deprecate_approved_runbook(runbook_id, reviewer=f"user:{user_id}"):
            await update.message.reply_text(f"Runbook #{runbook_id} was not found.")
            return
        await update.message.reply_text(f"Runbook #{runbook_id} deprecated.")
        return

    if command == "sources":
        source_args = [arg for arg in context.args[1:] if not arg.lower().startswith("agent:")]
        source_filter = source_args[0].lower() if source_args else "all"
        freshness = None
        canonical_only = source_filter not in {"all", "stale", "errors"}
        if source_filter in {"stale", "errors"}:
            freshness = source_filter
            canonical_only = False
        sources = list_knowledge_sources(
            agent_id=agent_id, canonical_only=canonical_only, freshness=freshness, limit=30
        )
        if not sources:
            await update.message.reply_text("No canonical knowledge sources registered.")
            return
        lines = [f"📚 Knowledge sources\n  agent: {escape_html(str(agent_id or 'default'))}\n"]
        for source in sources:
            updated = source["updated_at"][:10] if source["updated_at"] else "unknown"
            owner = source["owner"] or "unknown"
            project = source["project_key"] or "-"
            extra = []
            if source.get("stale_after"):
                extra.append(f"stale after {source['stale_after'][:10]}")
            if source.get("last_error"):
                extra.append(f"error {source['last_error'][:60]}")
            lines.append(
                f"<b>{escape_html(source['source_label'])}</b>\n"
                "  layer: "
                f"{escape_html(source['layer'])} | project: {escape_html(project)} | "
                f"owner: {escape_html(owner)}\n"
                f"  updated: {escape_html(updated)} | path: <code>{escape_html(source['source_path'])}</code>\n"
                + (f"  {' | '.join(escape_html(item) for item in extra)}\n" if extra else "")
            )
        await send_long_message(update, "\n".join(lines), parse_mode=ParseMode.HTML)
        return

    await update.message.reply_text(
        "Usage:\n"
        "/knowledge review\n"
        "/knowledge diff <candidate_id>\n"
        "/knowledge approve <candidate_id>\n"
        "/knowledge revalidate <runbook_id>\n"
        "/knowledge reject <candidate_id>\n"
        "/knowledge runbooks\n"
        "/knowledge health\n"
        "/knowledge deprecate <runbook_id>\n"
        "/knowledge sources [all|stale|errors]"
    )


def _parse_memory_filter_tokens(args: list[str]) -> tuple[dict[str, str], str]:
    """Parse key:value memory filters while preserving free-text query."""
    filters: dict[str, str] = {}
    free_text: list[str] = []
    for arg in args:
        if ":" not in arg:
            free_text.append(arg)
            continue
        key, value = arg.split(":", 1)
        key = key.lower()
        value = value.strip()
        allowed = {
            "agent",
            "type",
            "origin",
            "project",
            "env",
            "team",
            "task",
            "episode",
            "status",
            "retrieval",
            "layer",
            "query",
        }
        if key in allowed and value:
            filters[key] = value.lower() if key in {"type", "origin"} else value
            continue
        free_text.append(arg)
    return filters, " ".join(free_text).strip()


def _format_memory_provenance(memory: object) -> str:
    provenance: list[str] = []
    origin_kind = getattr(memory, "origin_kind", "") or ""
    agent_id = getattr(memory, "agent_id", "") or ""
    project_key = getattr(memory, "project_key", "") or ""
    environment = getattr(memory, "environment", "") or ""
    team = getattr(memory, "team", "") or ""
    quality_score = getattr(memory, "quality_score", None)
    memory_status = getattr(memory, "memory_status", "") or ""
    source_query_id = getattr(memory, "source_query_id", None)
    source_task_id = getattr(memory, "source_task_id", None)
    source_episode_id = getattr(memory, "source_episode_id", None)
    if agent_id:
        provenance.append(f"agent: {agent_id}")
    if origin_kind:
        provenance.append(f"origin: {origin_kind}")
    if project_key:
        provenance.append(f"project: {project_key}")
    if environment:
        provenance.append(f"environment: {environment}")
    if team:
        provenance.append(f"team: {team}")
    if source_query_id is not None:
        provenance.append(f"query: {source_query_id}")
    if source_task_id is not None:
        provenance.append(f"task: {source_task_id}")
    if source_episode_id is not None:
        provenance.append(f"episode: {source_episode_id}")
    if isinstance(quality_score, (int, float)):
        provenance.append(f"quality: {quality_score:.2f}")
    if memory_status:
        provenance.append(f"status: {memory_status}")
    return " | ".join(provenance)


def _current_memory_agent_scope() -> str:
    return _current_runtime_agent_id(uppercase=False) or "default"


async def cmd_memory(update: Update, context: BotContext) -> None:
    """Show memory stats or search memories."""
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)
    user_id = update.effective_user.id

    from koda.memory.config import MEMORY_ENABLED

    if not MEMORY_ENABLED:
        await update.message.reply_text("Memory system is disabled (MEMORY_ENABLED=false).")
        return

    args = context.args
    subcommand = args[0].lower() if args else ""
    root_filters, _unused = _parse_memory_filter_tokens(
        args[1:] if subcommand in {"audit", "search", "types", "quality"} else args
    )

    requested_agent = root_filters.get("agent")
    agent_scope, scope_error = _resolve_memory_agent_scope(requested_agent, user_id)
    if scope_error:
        await update.message.reply_text(scope_error)
        return

    if subcommand == "quality":
        from koda.memory.quality import get_memory_quality_snapshot

        snapshot = get_memory_quality_snapshot(agent_scope)
        lines = [f"📈 Memory quality snapshot\n  agent: {escape_html(agent_scope)}\n"]
        lines.append(
            "Extraction: "
            f"total {snapshot['extraction']['total']} | accepted {snapshot['extraction']['accepted']} | "
            f"rejected {snapshot['extraction']['rejected']}"
        )
        lines.append(
            "Dedup: "
            f"exact {snapshot['dedup']['exact']} | semantic {snapshot['dedup']['semantic']} | "
            f"batch {snapshot['dedup']['batch']}"
        )
        lines.append(
            "Recall: "
            f"considered {snapshot['recall']['considered']} | selected {snapshot['recall']['selected']} | "
            f"discarded {snapshot['recall']['discarded']}"
        )
        lines.append(
            "Memory lifecycle: "
            f"active {snapshot['memory']['active']} | superseded {snapshot['memory']['superseded']} | "
            f"stale {snapshot['memory']['stale']} | invalidated {snapshot['memory']['invalidated']}"
        )
        lines.append(
            "Embedding jobs: "
            f"pending {snapshot['embedding_jobs']['pending']} | failed {snapshot['embedding_jobs']['failed']} | "
            f"repaired {snapshot['embedding_jobs']['repaired']}"
        )
        lines.append(
            "Promotions: "
            f"pending {snapshot['promotions']['pending']} | approved {snapshot['promotions']['approved']} | "
            f"rejected {snapshot['promotions']['rejected']}"
        )
        lines.append(
            "Utility: "
            f"useful {snapshot['utility']['useful']} | noise {snapshot['utility']['noise']} | "
            f"misleading {snapshot['utility']['misleading']}"
        )
        safety = snapshot.get("safety", {})
        lines.append(
            "Safety: "
            f"blocked {safety.get('blocked_total', 0)} | injection {safety.get('prompt_injection', 0)} | "
            f"secrets {safety.get('credential_leakage', 0)}"
        )
        lines.append(
            "Runbooks: "
            f"approved {snapshot['runbooks']['approved']} | review {snapshot['runbooks']['needs_review']} | "
            f"expired {snapshot['runbooks']['expired']} | deprecated {snapshot['runbooks']['deprecated']}"
        )
        lines.append(
            "Governance: "
            f"approved {snapshot['governance']['approved']} | review {snapshot['governance']['needs_review']} | "
            f"expired {snapshot['governance']['expired']} | deprecated {snapshot['governance']['deprecated']}"
        )
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
        return

    if subcommand == "audit":
        from koda.memory.napkin import get_memory_recall_audits

        filters = root_filters
        audits = get_memory_recall_audits(
            user_id,
            agent_id=agent_scope,
            limit=8,
            task_id=int(filters["task"]) if filters.get("task", "").isdigit() else None,
            query_contains=filters.get("query", ""),
            episode=filters.get("episode", ""),
            layer=filters.get("layer", ""),
            retrieval=filters.get("retrieval", ""),
        )
        if not audits:
            await update.message.reply_text("No memory recall audits found yet.")
            return
        lines = [f"🧾 Memory recall audits\n  agent: {escape_html(agent_scope)}\n"]
        for audit in audits:
            considered = cast(list[dict[str, object]], audit.get("considered", []))
            selected = cast(list[dict[str, object]], audit.get("selected", []))
            discarded = cast(list[dict[str, object]], audit.get("discarded", []))
            conflicts = cast(list[dict[str, object]], audit.get("conflicts", []))
            selected_layers = cast(list[str], audit.get("selected_layers", []))
            retrieval_sources = cast(list[str], audit.get("retrieval_sources", []))
            considered_count = int(cast(int, audit.get("total_considered", len(considered))))
            selected_count = int(cast(int, audit.get("total_selected", len(selected))))
            discarded_count = int(cast(int, audit.get("total_discarded", len(discarded))))
            trust_score = float(cast(float | int | str, audit.get("trust_score", 0.0)))
            conflict_count = int(cast(int, audit.get("conflict_group_count", len(conflicts))))
            layers = ", ".join(selected_layers[:4]) or "-"
            retrievals = ", ".join(retrieval_sources[:4]) or "-"
            lines.append(
                f"<b>#{audit['id']}</b> trust {trust_score:.2f} | "
                f"considered {considered_count} | selected {selected_count} | discarded {discarded_count}\n"
                f"  query: {escape_html(str(audit['query_preview'])[:90])}\n"
                f"  scope: {escape_html(str(audit['project_key'] or '-'))} | "
                f"{escape_html(str(audit['environment'] or '-'))} | "
                f"{escape_html(str(audit['team'] or '-'))}\n"
                f"  layers: {escape_html(layers)} | retrieval: {escape_html(retrievals)}\n"
                + (f"  conflicts: {escape_html(str(conflict_count))}\n" if conflicts or conflict_count > 0 else "")
            )
        await send_long_message(update, "\n".join(lines), parse_mode=ParseMode.HTML)
        return

    if subcommand == "search":
        filters, query = _parse_memory_filter_tokens(args[1:])
        if not query:
            await update.message.reply_text(
                "Usage: /memory search [agent:<id>] [type:<type>] [origin:<kind>] [project:<key>] [task:<id>] "
                "[episode:<id>] [status:<state>] [retrieval:<source>] [layer:<name>] <query>"
            )
            return

        from koda.memory import get_memory_manager
        from koda.memory.store import MemoryStore
        from koda.memory.types import MemoryType

        mm = get_memory_manager()
        if agent_scope == _current_memory_agent_scope():
            store = mm.store
        else:
            store = MemoryStore(agent_scope)
        if not store:
            await update.message.reply_text("Memory store not initialized.")
            return

        session_scope = context.user_data.get("session_id") if agent_scope == _current_memory_agent_scope() else None
        memory_types = None
        if filters.get("type"):
            try:
                memory_types = [MemoryType(filters["type"])]
            except ValueError:
                valid = ", ".join(t.value for t in MemoryType)
                await update.message.reply_text(f"Invalid type: {filters['type']}\nValid: {valid}")
                return

        results = await store.search(
            query,
            user_id,
            n_results=10,
            memory_types=memory_types,
            project_key=filters.get("project", ""),
            environment=filters.get("env", ""),
            team=filters.get("team", ""),
            origin_kinds=[filters["origin"]] if filters.get("origin") else None,
            session_id=session_scope,
            source_query_id=int(filters["query"]) if filters.get("query", "").isdigit() else None,
            source_task_id=int(filters["task"]) if filters.get("task", "").isdigit() else None,
            source_episode_id=int(filters["episode"]) if filters.get("episode", "").isdigit() else None,
            memory_statuses=[filters["status"]] if filters.get("status") else None,
            allowed_layers=[filters["layer"]] if filters.get("layer") else None,
            allowed_retrieval_sources=[filters["retrieval"]] if filters.get("retrieval") else None,
        )
        if not results:
            await update.message.reply_text("No memories found matching your query.")
            return

        lines = [f"🔍 Memory search: <i>{escape_html(query)}</i>\n  agent: {escape_html(agent_scope)}\n"]
        for r in results:
            similarity = max(0, 1.0 - r.relevance_score)
            date_str = r.memory.created_at.strftime("%Y-%m-%d")
            mid = r.memory.id or "?"
            provenance = _format_memory_provenance(r.memory)
            retrieval = getattr(r, "retrieval_source", "vector")
            layer = getattr(r, "layer", "conversational")
            score = getattr(r, "combined_score", 0.0)
            lines.append(
                f"<b>#{mid}</b> [{r.memory.memory_type.value}] "
                f"({similarity:.0%}) {date_str}\n"
                f"  <i>{escape_html(provenance or f'origem: {retrieval}')}</i>\n"
                f"  <i>{escape_html(f'layer: {layer} | retrieval: {retrieval} | score: {score:.2f}')}</i>\n"
                f"  {escape_html(r.memory.content[:120])}\n"
            )
        await send_long_message(update, "\n".join(lines), parse_mode=ParseMode.HTML)
        return

    if subcommand == "types":
        from koda.memory.napkin import get_stats as napkin_stats

        stats = napkin_stats(user_id, agent_id=agent_scope)
        lines = [f"📊 Memory breakdown by type\n  agent: {escape_html(agent_scope)}\n"]
        for mem_type, count in sorted(stats["by_type"].items()):
            lines.append(f"  • {mem_type}: {count}")
        if not stats["by_type"]:
            lines.append("  No memories stored yet.")
        await update.message.reply_text("\n".join(lines))
        return

    # Default: show stats
    from koda.memory.napkin import get_stats as napkin_stats

    stats = napkin_stats(user_id, agent_id=agent_scope)
    type_lines = [f"  • {t}: {c}" for t, c in sorted(stats["by_type"].items())]
    type_section = "\n".join(type_lines) if type_lines else "  None"
    origin_lines = [f"  • {t}: {c}" for t, c in sorted(stats.get("by_origin", {}).items())]
    origin_section = "\n".join(origin_lines) if origin_lines else "  None"
    embedding_lines = [f"  • {t}: {c}" for t, c in sorted(stats.get("embedding_status", {}).items())]
    embedding_section = "\n".join(embedding_lines) if embedding_lines else "  None"
    memory_status_lines = [f"  • {t}: {c}" for t, c in sorted(stats.get("memory_status", {}).items())]
    memory_status_section = "\n".join(memory_status_lines) if memory_status_lines else "  None"

    await update.message.reply_text(
        f"🧠 Memory Stats\n\n"
        f"Agent scope: {agent_scope}\n"
        f"Total memories: {stats['total']}\n"
        f"Active: {stats['active']}\n"
        f"Inactive: {stats['total'] - stats['active']}\n\n"
        f"By type:\n{type_section}\n\n"
        f"By origin:\n{origin_section}\n\n"
        f"Lifecycle state:\n{memory_status_section}\n\n"
        f"Embedding sync:\n{embedding_section}\n\n"
        f"Commands:\n"
        f"/memory search [agent:<id>] [type:<type>] [origin:<kind>] [project:<key>] "
        f"[layer:<name>] <query> — Hybrid search\n"
        f"/memory quality [agent:<id>] — Quality snapshot by agent\n"
        f"/memory types — Breakdown by type\n"
        f"/memory audit [agent:<id>] [task:<id>] [episode:<id>] [layer:<name>] "
        f"[retrieval:<source>] [query:<text>] — Recall audit\n"
        f"/napkin [type] — View recent memories\n"
        f"/forget <id> — Remove a memory"
    )


async def cmd_napkin(update: Update, context: BotContext) -> None:
    """View recent napkin log entries."""
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)
    user_id = update.effective_user.id

    from koda.memory.config import MEMORY_ENABLED

    if not MEMORY_ENABLED:
        await update.message.reply_text("Memory system is disabled (MEMORY_ENABLED=false).")
        return

    from koda.memory.napkin import get_entries
    from koda.memory.types import MemoryType

    # Optional type filter
    memory_type = None
    filters, _free_text = _parse_memory_filter_tokens(context.args)
    agent_scope, scope_error = _resolve_memory_agent_scope(filters.get("agent"), user_id)
    if scope_error:
        await update.message.reply_text(scope_error)
        return
    type_arg = filters.get("type") or (context.args[0].lower() if context.args and ":" not in context.args[0] else "")
    if type_arg:
        type_str = type_arg.lower()
        try:
            memory_type = MemoryType(type_str)
        except ValueError:
            valid = ", ".join(t.value for t in MemoryType)
            await update.message.reply_text(f"Unknown type: {type_str}\nValid: {valid}")
            return

    entries = get_entries(
        user_id,
        limit=20,
        memory_type=memory_type,
        agent_id=agent_scope,
        origin_kind=filters.get("origin"),
        project_key=filters.get("project"),
        environment=filters.get("env"),
        team=filters.get("team"),
    )
    if not entries:
        msg = "No memories found."
        if memory_type:
            msg += f" (type: {memory_type.value})"
        await update.message.reply_text(msg)
        return

    filter_parts = []
    if memory_type:
        filter_parts.append(f"type: {memory_type.value}")
    if filters.get("origin"):
        filter_parts.append(f"origin: {filters['origin']}")
    if filters.get("agent"):
        filter_parts.append(f"agent: {agent_scope}")
    if filters.get("project"):
        filter_parts.append(f"project: {filters['project']}")
    if filters.get("env"):
        filter_parts.append(f"env: {filters['env']}")
    if filters.get("team"):
        filter_parts.append(f"team: {filters['team']}")
    filter_label = f" ({', '.join(filter_parts)})" if filter_parts else ""
    lines = [f"📝 Napkin Log{filter_label}\n  agent: {escape_html(agent_scope)}\n"]
    for m in entries:
        date_str = m.created_at.strftime("%Y-%m-%d %H:%M")
        imp_bar = "●" * round(m.importance * 5) + "○" * (5 - round(m.importance * 5))
        provenance = _format_memory_provenance(m)
        lines.append(
            f"<b>#{m.id}</b> [{m.memory_type.value}] {imp_bar}\n"
            f"  {escape_html(m.content[:150])}\n"
            f"  <i>{escape_html(provenance or 'origem: conversation')} | {date_str} | views: {m.access_count}</i>\n"
        )

    await send_long_message(update, "\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_forget(update: Update, context: BotContext) -> None:
    """Deactivate a memory by ID or all memories."""
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)
    user_id = update.effective_user.id

    from koda.memory.config import MEMORY_ENABLED

    if not MEMORY_ENABLED:
        await update.message.reply_text("Memory system is disabled (MEMORY_ENABLED=false).")
        return

    if not context.args:
        await update.message.reply_text("Usage: /forget <id> or /forget all")
        return

    arg = context.args[0].lower()

    from koda.memory import get_memory_manager

    mm = get_memory_manager()
    if not mm.store:
        await update.message.reply_text("Memory store not initialized.")
        return

    if arg == "all":
        # Confirmation via inline button
        buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Yes, forget all", callback_data="memory_forget:all"),
                    InlineKeyboardButton("Cancel", callback_data="memory_forget:cancel"),
                ]
            ]
        )
        await update.message.reply_text(
            "⚠️ This will deactivate ALL your memories. Are you sure?",
            reply_markup=buttons,
        )
        return

    try:
        memory_id = int(arg)
    except ValueError:
        await update.message.reply_text("Invalid ID. Usage: /forget <id> or /forget all")
        return

    success = await mm.store.deactivate(memory_id, user_id=user_id)
    if success:
        from koda.memory.recall import clear_recall_cache

        clear_recall_cache(user_id)
        await update.message.reply_text(f"Memory #{memory_id} forgotten.")
    else:
        await update.message.reply_text(f"Memory #{memory_id} not found or already inactive.")


async def cmd_digest(update: Update, context: BotContext) -> None:
    """Configure and send daily digest."""
    if not auth_check(update):
        return await reject_unauthorized(update)

    init_user_data(context.user_data, user_id=update.effective_user.id)
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    from koda.memory.config import MEMORY_DIGEST_ENABLED, MEMORY_ENABLED

    if not MEMORY_ENABLED or not MEMORY_DIGEST_ENABLED:
        await update.message.reply_text("Digest is disabled.")
        return

    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    from koda.memory.digest_store import get_preference, set_preference

    if not context.args:
        # Show current config
        pref = get_preference(user_id)
        if pref:
            _uid, _cid, enabled, hour, minute, timezone_name, last_sent = pref
            status = "✅ Active" if enabled else "❌ Disabled"
            await update.message.reply_text(
                f"<b>📋 Digest Config</b>\n\n"
                f"Status: {status}\n"
                f"Time: {hour:02d}:{minute:02d}\n"
                f"Timezone: {escape_html(str(timezone_name or 'UTC'))}\n"
                f"Last sent: {last_sent or 'never'}\n\n"
                f"Commands:\n"
                f"/digest on — Enable\n"
                f"/digest off — Disable\n"
                f"/digest time HH:MM — Change time\n"
                f"/digest timezone Area/City — Change timezone\n"
                f"/digest now — Send now",
                parse_mode=ParseMode.HTML,
            )
        else:
            await update.message.reply_text("Digest is not configured.\nUse /digest on to enable (default: 09:00).")
        return

    cmd = context.args[0].lower()

    if cmd == "on":
        existing = get_preference(user_id)
        timezone_name = existing[5] if existing else "UTC"
        hour = existing[3] if existing else 9
        minute = existing[4] if existing else 0
        set_preference(user_id, chat_id, enabled=True, send_hour=hour, send_minute=minute, timezone=timezone_name)
        await update.message.reply_text(f"✅ Digest enabled. Daily delivery at {hour:02d}:{minute:02d}.")

    elif cmd == "off":
        pref = get_preference(user_id)
        if pref:
            set_preference(
                user_id,
                chat_id,
                enabled=False,
                send_hour=pref[3],
                send_minute=pref[4],
                timezone=pref[5],
            )
            await update.message.reply_text("❌ Digest disabled.")
        else:
            await update.message.reply_text("Digest was not configured.")

    elif cmd == "time":
        if len(context.args) < 2:
            await update.message.reply_text("Usage: /digest time HH:MM")
            return
        try:
            parts = context.args[1].split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
        except (ValueError, IndexError):
            await update.message.reply_text("Invalid time. Use HH:MM (e.g. 09:00)")
            return
        pref = get_preference(user_id)
        timezone_name = pref[5] if pref else "UTC"
        set_preference(user_id, chat_id, enabled=True, send_hour=hour, send_minute=minute, timezone=timezone_name)
        await update.message.reply_text(f"✅ Digest scheduled for {hour:02d}:{minute:02d}")

    elif cmd == "timezone":
        if len(context.args) < 2:
            await update.message.reply_text("Usage: /digest timezone Area/City")
            return
        timezone_name = context.args[1]
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            await update.message.reply_text("Invalid timezone. Example: America/Sao_Paulo")
            return
        pref = get_preference(user_id)
        hour = pref[3] if pref else 9
        minute = pref[4] if pref else 0
        enabled = bool(pref[2]) if pref else True
        set_preference(
            user_id,
            chat_id,
            enabled=enabled,
            send_hour=hour,
            send_minute=minute,
            timezone=timezone_name,
        )
        await update.message.reply_text(f"✅ Digest timezone set to {timezone_name}")

    elif cmd == "now":
        from koda.memory.digest import build_digest

        digest = build_digest(user_id, agent_id=_current_memory_agent_scope())
        if digest:
            await update.message.reply_text(digest, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text("Nothing to report right now.")

    else:
        await update.message.reply_text("Usage: /digest [on|off|time HH:MM|timezone Area/City|now]")


async def cmd_dlq(update: Update, context: BotContext) -> None:
    """Inspect and manage the dead letter queue (admin only)."""
    if not auth_check(update):
        return await reject_unauthorized(update)

    def _load_metadata(raw_json: str | None) -> dict[str, Any]:
        with contextlib.suppress(TypeError, ValueError):
            loaded = json.loads(raw_json or "{}")
            if isinstance(loaded, dict):
                return loaded
        return {}

    from koda.utils.formatting import escape_html

    arg = context.args[0] if context.args else ""

    if arg == "retry" and len(context.args) >= 2:
        try:
            dlq_id = int(context.args[1])
        except ValueError:
            await update.message.reply_text("Usage: /dlq retry <id>")
            return
        entry = dlq_get_dict(dlq_id)
        if not entry:
            await update.message.reply_text(f"DLQ entry #{dlq_id} not found.")
            return
        if not entry["retry_eligible"]:
            await update.message.reply_text(f"DLQ #{dlq_id} is not eligible for retry.")
            return
        application = getattr(context, "application", None)
        if application is None:
            await update.message.reply_text("DLQ retry is unavailable because the application context is missing.")
            return
        new_task_id = await requeue_dlq_entry(
            entry,
            application=application,
            actor=update.effective_user.id,
            bot_override=context.bot,
        )
        await update.message.reply_text(
            f"DLQ #{dlq_id} reprocessada com sucesso para o usuario {entry['user_id']} como tarefa #{new_task_id}."
        )
        return

    if arg == "inspect" and len(context.args) >= 2:
        try:
            dlq_id = int(context.args[1])
        except ValueError:
            await update.message.reply_text("Usage: /dlq inspect <id>")
            return
        entry = dlq_get_dict(dlq_id)
        if not entry:
            await update.message.reply_text(f"DLQ entry #{dlq_id} not found.")
            return
        metadata = _load_metadata(entry.get("metadata_json"))
        history = list(metadata.get("history") or [])
        lines = [
            f"<b>DLQ #{entry['id']}</b>",
            f"Task: #{entry['task_id']}",
            f"User: {entry['user_id']}",
            f"Query: {escape_html(entry['query_text'][:200])}",
            f"Model: {entry['model'] or 'unknown'}",
            f"Error: {escape_html(entry['error_message'] or 'n/a')}",
            f"Attempts: {entry['attempt_count']}",
            f"Failed: {entry['failed_at']}",
            f"Retry eligible: {'yes' if entry['retry_eligible'] else 'no'}",
        ]
        if metadata.get("last_reprocessed_task_id"):
            lines.append(f"Last reprocess task: #{metadata['last_reprocessed_task_id']}")
        if metadata.get("last_reprocessed_at"):
            lines.append(f"Last reprocess at: {metadata['last_reprocessed_at']}")
        if history:
            lines.append(f"History events: {len(history)}")
            latest = history[-1]
            if isinstance(latest, dict):
                latest_event = escape_html(str(latest.get("event") or "unknown"))
                latest_time = escape_html(str(latest.get("at") or ""))
                lines.append(f"Latest event: {latest_event} {latest_time}".strip())
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
        return

    # Default: list entries
    entries = dlq_list(limit=20)
    if not entries:
        await update.message.reply_text("Dead letter queue is empty.")
        return

    lines = ["<b>Dead Letter Queue</b>\n"]
    for e in entries:
        dlq_id, task_id, user_id, _chat_id, query, error, attempts, failed_at, eligible = e
        preview = escape_html((query or "")[:60])
        status = "retry" if eligible else "done"
        lines.append(f"#{dlq_id} (task #{task_id}) [{status}] {preview}")
        if error:
            lines.append(f"  Error: {escape_html(error[:80])}")

    lines.append("\nCommands: /dlq inspect <id>, /dlq retry <id>")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
