"""Inline keyboard callback handlers."""

import contextlib
import hashlib
import os
import re
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from koda import config
from koda.auth import auth_check
from koda.config import AVAILABLE_AGENT_MODES, AVAILABLE_MODELS, AVAILABLE_PROVIDERS, PROVIDER_MODELS
from koda.handlers.commands import _settings_home_markup, _settings_home_text
from koda.logging_config import get_logger
from koda.memory.quality import record_utility_event
from koda.provider_models import MODEL_FUNCTION_IDS, resolve_model_function_catalog
from koda.services.agent_settings import (
    get_agent_runtime_settings,
    set_agent_functional_default,
    set_agent_general_model,
    set_agent_general_provider,
    set_agent_voice_default,
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
    dispatch_approved_operation,
    resolve_agent_cmd_approval,
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
        return "herdado do global"
    provider_id = str(selection.get("provider_id") or "").strip().lower()
    model_id = str(selection.get("model_id") or "").strip()
    if provider_id and model_id:
        return f"{provider_id} / {model_id}"
    return "herdado do global"


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
                [[InlineKeyboardButton("Voltar aos ajustes", callback_data="settings:home")]]
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
                [[InlineKeyboardButton("Voltar aos ajustes", callback_data="settings:home")]]
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
    buttons.append([InlineKeyboardButton("Voltar", callback_data="settings:home")])
    await query.edit_message_text(
        "Selecione o provider padrao deste AGENT:",
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
    buttons.append([InlineKeyboardButton("Voltar", callback_data="settings:home")])
    await query.edit_message_text(
        f"Selecione o modelo geral para <code>{escape_html(provider)}</code>:",
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
        await query.edit_message_text("As configuracoes por funcionalidade deste AGENT nao estao disponiveis agora.")
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
    buttons.append([InlineKeyboardButton("Voltar", callback_data="settings:home")])
    await query.edit_message_text(
        "Selecione a funcionalidade para ajustar o modelo padrao deste AGENT:",
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
    buttons.append([InlineKeyboardButton("Voltar", callback_data="settings:home")])
    await query.edit_message_text(
        f"Modo atual: <code>{escape_html(current_mode)}</code>\nSelecione o modo deste AGENT:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def callback_settings_voice(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await query.answer()

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    voice_id = str(context.user_data.get("tts_voice") or "")
    voice_label = str(context.user_data.get("tts_voice_label") or voice_id or "n/a")
    language = str(context.user_data.get("tts_voice_language") or "n/a")
    await query.edit_message_text(
        (
            "<b>Voz deste AGENT</b>\n\n"
            f"Atual: <code>{escape_html(voice_id)}</code> ({escape_html(voice_label)})\n"
            f"Idioma: <code>{escape_html(language)}</code>\n\n"
            "Para trocar por chat, diga algo como:\n"
            "• mude a voz para pm_alex\n"
            "• mude a voz para Dora\n\n"
            "Ou use /voice voices para listar e /voice search &lt;termo&gt; para buscar."
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Voltar", callback_data="settings:home")]]),
    )


async def callback_settings_newsession(update: Update, context: BotContext) -> None:
    query = update.callback_query
    await query.answer()

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    context.user_data["session_id"] = None
    context.user_data["provider_sessions"] = {}
    context.user_data["_supervised_session_id"] = None
    context.user_data["_supervised_provider"] = None
    await query.edit_message_text(
        "Sessao limpa. A proxima mensagem inicia uma conversa nova.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Voltar aos ajustes", callback_data="settings:home")]]
        ),
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
    agent_id = (os.environ.get("AGENT_ID") or "").strip().upper() or config.AGENT_ID
    episode = get_latest_execution_episode(task_id)
    if episode is None:
        await query.answer("No execution episode found for this task.", show_alert=True)
        return

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
        "corrected": "Feedback registrado como correção. Abri um candidato de risco para revisão.",
        "failed": "Feedback registrado como falha. Abri um candidato de risco para revisão.",
        "risky": "Feedback registrado como risco alto. Abri um candidato de guardrail para revisão.",
        "approved": "Feedback registrado como aprovado.",
        "promote": "Feedback registrado como promoção.",
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
            "Feedback registrado como aprovado, mas faltam gates mínimos para promover em rotina reutilizável.",
            show_alert=True,
        )
        return
    if feedback_type == "promote" and not created_candidate:
        return
    if feedback_type == "approved" and created_candidate:
        await query.answer(
            "Feedback registrado como aprovado. Abri um candidato de rotina positiva para revisão.",
            show_alert=True,
        )
        return
    if feedback_type == "promote" and created_candidate:
        await query.answer(
            "Feedback registrado como promoção. Abri um candidato de runbook para revisão.",
            show_alert=True,
        )
        return
    await query.answer(feedback_labels.get(feedback_type, "Feedback registrado."), show_alert=True)


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
                [[InlineKeyboardButton("Voltar aos ajustes", callback_data="settings:home")]]
            ),
        )


async def callback_dbenv(update: Update, context: BotContext) -> None:
    """Handle database environment selection button press."""
    query = update.callback_query
    await query.answer()

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)

    from koda.config import POSTGRES_AVAILABLE_ENVS

    env = (query.data or "").removeprefix("dbenv:")
    if env in POSTGRES_AVAILABLE_ENVS:
        context.user_data["postgres_env"] = env
        await query.edit_message_text(f"Database env: <code>{env}</code>", parse_mode=ParseMode.HTML)


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
    await query.answer()

    if not auth_check(update):
        return

    init_user_data(context.user_data, user_id=update.effective_user.id)
    # Format: voiceel:<voice_id>:<display_name>
    parts = (query.data or "").split(":", 2)
    if len(parts) != 3:
        return
    _, voice_id, display_name = parts

    try:
        sync_user_data_with_runtime_settings(
            context.user_data,
            set_agent_voice_default(voice_id, voice_label=display_name),
        )
    except ValueError as exc:
        await query.edit_message_text(str(exc))
        return
    await query.edit_message_text(
        f"Voice set to: <b>{escape_html(display_name)}</b>\n"
        f"ID: <code>{escape_html(voice_id)}</code>\n\n"
        f"Use /voice on to enable voice responses.",
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
        await query.edit_message_text("As configuracoes por funcionalidade deste AGENT nao estao disponiveis agora.")
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
    buttons.append([InlineKeyboardButton("Voltar aos ajustes", callback_data="settings:home")])
    await query.edit_message_text(
        "Selecione a funcionalidade para ajustar o modelo padrao deste AGENT:",
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
        await query.edit_message_text("As configuracoes por funcionalidade deste AGENT nao estao disponiveis agora.")
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
    buttons.append([InlineKeyboardButton("Voltar", callback_data="fmodelhome")])
    await query.edit_message_text(
        f"<b>{escape_html(_feature_function_label(function_id))}</b>\n"
        f"Atual: <code>{escape_html(current)}</code>\n\n"
        "Selecione o provider para esta funcionalidade:",
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
        await query.edit_message_text("As configuracoes por funcionalidade deste AGENT nao estao disponiveis agora.")
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
    buttons.append([InlineKeyboardButton("Voltar", callback_data=f"fmodelf:{function_id}")])
    await query.edit_message_text(
        f"<b>{escape_html(_feature_function_label(function_id))}</b>\n"
        f"Provider: <code>{escape_html(provider_title)}</code>\n\n"
        "Selecione o modelo padrao para este AGENT:",
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
        f"Modelo padrao do AGENT atualizado para <code>{escape_html(title)}</code> "
        f"({escape_html(provider_id)} / <code>{escape_html(model_id)}</code>).",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Ajustar outro modelo", callback_data=f"fmodelf:{function_id}")],
                [InlineKeyboardButton("Voltar ao menu", callback_data="fmodelhome")],
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
            await query.edit_message_text("⚠️ Metadados expirados. Envie o link novamente.")
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
        "summary": "📝 Resumo",
        "main_idea": "💡 Ideia Principal",
        "key_points": "🔑 Pontos-Chave",
        "structure": "📋 Estrutura",
        "full": "🔍 Análise Completa",
        "transcript": "📜 Transcrição",
        "thumbnail": "🖼 Thumbnail",
    }
    label = action_labels.get(action, action)

    # Update original message to show selected action
    original_text = update.effective_message.text or ""
    with contextlib.suppress(Exception):
        await query.edit_message_text(
            escape_html(original_text) + f"\n\n<i>Selecionado: {label}</i>",
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
                text="⚠️ Não foi possível extrair a transcrição deste vídeo. Legendas podem não estar disponíveis.",
            )
            return
        header = f"📜 <b>Transcrição: {escape_html(meta.title)}</b>\n\n" if meta.title else "📜 <b>Transcrição</b>\n\n"
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
    """Handle approval keyboard button presses (approve:one/all/deny:<op_id>)."""
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

    if action == "all":
        context.user_data["_approve_all"] = True

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
        await query.edit_message_text("Aprovado.")
    await dispatch_approved_operation(op_id)


async def callback_agent_cmd_approval(update: Update, context: BotContext) -> None:
    """Handle agent-cmd approval keyboard button presses (acmd:ok/all/no:<op_id>)."""
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

    if action == "all":
        context.user_data["_approve_all_agent_tools"] = True
        resolve_agent_cmd_approval(op_id, "approved_all")
        log.info(
            "agent_cmd_approval_granted",
            op_id=op_id,
            user_id=update.effective_user.id,
            mode="all",
        )
        emit_security("security.approval_granted", user_id=update.effective_user.id, op_id=op_id, mode="all")
        with contextlib.suppress(Exception):
            await query.edit_message_text("Aprovado (todos).")
        return

    # action == "ok"
    resolve_agent_cmd_approval(op_id, "approved")
    log.info(
        "agent_cmd_approval_granted",
        op_id=op_id,
        user_id=update.effective_user.id,
        mode="one",
    )
    emit_security("security.approval_granted", user_id=update.effective_user.id, op_id=op_id, mode="one")
    with contextlib.suppress(Exception):
        await query.edit_message_text("Aprovado.")
