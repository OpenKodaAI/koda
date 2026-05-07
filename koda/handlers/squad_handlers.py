"""Telegram command handlers for squad ↔ chat operations.

Operator-driven entry points for binding a Telegram supergroup to a squad
and managing forum-topic-backed squad threads. The actual ingress that
routes user messages from a forum topic into a SquadThread will land in a
follow-up slice (a ``MessageHandler`` that calls
``SquadThreadStore.find_by_telegram_topic`` on supergroup posts).
"""

from __future__ import annotations

from typing import Any

from telegram import Update

from koda.auth import auth_check, reject_unauthorized
from koda.config import AGENT_ID, INTER_AGENT_ENABLED
from koda.logging_config import get_logger
from koda.telegram_types import BotContext

log = get_logger(__name__)


async def _reject_unsupported(update: Update, message: str) -> None:
    if update.message is not None:
        await update.message.reply_text(message)


def _is_supergroup(update: Update) -> bool:
    chat = update.effective_chat
    return chat is not None and chat.type == "supergroup"


def _is_forum(update: Update) -> bool:
    chat = update.effective_chat
    return chat is not None and bool(getattr(chat, "is_forum", False))


async def _gate(update: Update) -> bool:
    if not auth_check(update):
        await reject_unauthorized(update)
        return False
    if not INTER_AGENT_ENABLED:
        await _reject_unsupported(update, "Squad commands are disabled (INTER_AGENT_ENABLED=false).")
        return False
    return True


async def cmd_squad_bind(update: Update, context: BotContext) -> None:
    if not await _gate(update):
        return
    chat = update.effective_chat
    if chat is None or update.message is None:
        return
    if not _is_supergroup(update):
        await _reject_unsupported(update, "Use /squad_bind inside a Telegram supergroup.")
        return
    args = (context.args or []) if context else []
    if not args:
        await update.message.reply_text("Usage: /squad_bind <squad_id>")
        return
    squad_id = str(args[0]).strip()
    if not squad_id:
        await update.message.reply_text("Usage: /squad_bind <squad_id>")
        return

    from koda.squads import TelegramBindingConflictError, get_telegram_binding_service

    service = get_telegram_binding_service()
    if service is None:
        await update.message.reply_text("Squad binding service unavailable (POSTGRES_URL not configured).")
        return
    user = update.effective_user
    try:
        binding = await service.bind(
            squad_id=squad_id,
            telegram_chat_id=chat.id,
            chat_title=chat.title or "",
            is_forum=_is_forum(update),
            bound_by_user_id=user.id if user is not None else None,
            force=False,
        )
    except TelegramBindingConflictError as exc:
        await update.message.reply_text(f"Bind failed: {exc}")
        return
    forum_label = "forum" if binding.is_forum else "non-forum"
    await update.message.reply_text(f"Squad '{binding.squad_id}' bound to this chat ({forum_label}).")


async def cmd_squad_unbind(update: Update, context: BotContext) -> None:
    if not await _gate(update):
        return
    chat = update.effective_chat
    if chat is None or update.message is None:
        return

    from koda.squads import get_telegram_binding_service

    service = get_telegram_binding_service()
    if service is None:
        await update.message.reply_text("Squad binding service unavailable.")
        return
    binding = await service.get_for_chat(chat.id)
    if binding is None:
        await update.message.reply_text("This chat is not bound to a squad.")
        return
    removed = await service.unbind(squad_id=binding.squad_id)
    if removed:
        await update.message.reply_text(f"Squad '{binding.squad_id}' unbound from this chat.")
    else:
        await update.message.reply_text(f"Squad '{binding.squad_id}' was not bound after all.")


async def cmd_squad_status(update: Update, context: BotContext) -> None:
    if not await _gate(update):
        return
    chat = update.effective_chat
    if chat is None or update.message is None:
        return

    from koda.squads import get_telegram_binding_service

    service = get_telegram_binding_service()
    if service is None:
        await update.message.reply_text("Squad binding service unavailable.")
        return
    binding = await service.get_for_chat(chat.id)
    if binding is None:
        await update.message.reply_text("This chat is not bound to a squad.")
        return
    forum_label = "forum" if binding.is_forum else "non-forum"
    await update.message.reply_text(
        f"Squad: {binding.squad_id}\n"
        f"Chat title: {binding.chat_title or '(unknown)'} ({forum_label})\n"
        f"Bound at: {binding.bound_at}"
    )


async def cmd_squad_thread_new(update: Update, context: BotContext) -> None:
    if not await _gate(update):
        return
    chat = update.effective_chat
    if chat is None or update.message is None:
        return
    if not _is_supergroup(update):
        await _reject_unsupported(update, "Use /squad_thread_new in a supergroup bound to a squad.")
        return
    args = (context.args or []) if context else []
    title = " ".join(str(a) for a in args).strip()
    if not title:
        await update.message.reply_text("Usage: /squad_thread_new <title>")
        return

    from koda.squads import get_squad_thread_store, get_telegram_binding_service

    binding_service = get_telegram_binding_service()
    thread_store = get_squad_thread_store()
    if binding_service is None or thread_store is None:
        await update.message.reply_text("Squad services unavailable (POSTGRES_URL not configured).")
        return
    binding = await binding_service.get_for_chat(chat.id)
    if binding is None:
        await update.message.reply_text("This chat is not bound to a squad. Run /squad_bind <squad_id> first.")
        return

    workspace_id = (context.user_data or {}).get("squad_default_workspace_id") or binding.metadata.get("workspace_id")
    if not workspace_id:
        await update.message.reply_text(
            "Cannot create thread: no workspace_id known for this chat. Set "
            "user_data['squad_default_workspace_id'] or binding metadata.workspace_id."
        )
        return

    message_thread_id: int | None = None
    if binding.is_forum:
        try:
            topic = await context.bot.create_forum_topic(chat_id=chat.id, name=title[:128])
            message_thread_id = int(topic.message_thread_id)
        except Exception:
            log.exception("squad_thread_new_create_forum_topic_failed", chat_id=chat.id)
            await update.message.reply_text(
                "Failed to create forum topic — is the bot an admin with topic permissions?"
            )
            return

    user = update.effective_user
    coordinator = AGENT_ID or None
    thread = await thread_store.create_thread(
        workspace_id=str(workspace_id),
        squad_id=binding.squad_id,
        title=title,
        owner_user_id=user.id if user is not None else None,
        coordinator_agent_id=coordinator,
        telegram_chat_id=chat.id,
        telegram_message_thread_id=message_thread_id,
    )
    if message_thread_id is not None:
        await update.message.reply_text(f"Thread '{thread.id}' created in topic {message_thread_id}.")
    else:
        await update.message.reply_text(f"Thread '{thread.id}' created (no forum topic — chat is not a forum).")


async def route_squad_supergroup_message(update: Update, context: BotContext) -> None:
    """MessageHandler entry point for forum-topic posts in bound supergroups.

    Persists each authorized user message into the matching ``SquadThread`` so
    agents can read it via ``squad_thread_history`` / ``squad_context``.
    Routing to a specific agent's queue is deferred to a follow-up slice
    (coordinator + capability-based routing).
    """
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if message is None or chat is None or user is None:
        return
    if user.is_bot:
        return
    if chat.type != "supergroup":
        return
    if not message.is_topic_message:
        return
    if not INTER_AGENT_ENABLED:
        return
    if not auth_check(update):
        return
    text = message.text or message.caption or ""
    if not text.strip():
        return

    from koda.squads import get_squad_thread_store, get_telegram_binding_service

    binding_service = get_telegram_binding_service()
    thread_store = get_squad_thread_store()
    if binding_service is None or thread_store is None:
        return
    binding = await binding_service.get_for_chat(chat.id)
    if binding is None:
        return
    thread = await thread_store.find_by_telegram_topic(
        telegram_chat_id=chat.id,
        telegram_message_thread_id=message.message_thread_id,
    )
    if thread is None:
        return
    if binding.squad_id != thread.squad_id:
        log.warning(
            "squad_inbound_squad_mismatch",
            chat_id=chat.id,
            thread_squad=thread.squad_id,
            binding_squad=binding.squad_id,
        )
        return

    sender_handle = user.username or str(user.id)
    metadata = {
        "telegram_user_id": user.id,
        "telegram_username": user.username,
        "telegram_message_id": message.message_id,
        "telegram_chat_id": chat.id,
        "telegram_message_thread_id": message.message_thread_id,
    }
    try:
        await thread_store.post_thread_message(
            thread_id=thread.id,
            from_agent=f"user:{sender_handle}",
            content=text,
            message_type="user_input",
            metadata=metadata,
        )
    except Exception:
        log.exception(
            "squad_inbound_persist_failed",
            thread_id=thread.id,
            chat_id=chat.id,
        )
        return

    await _notify_squad_targets(
        text=text,
        thread=thread,
        thread_store=thread_store,
        sender_handle=sender_handle,
        telegram_chat_id=chat.id,
        telegram_message_thread_id=message.message_thread_id,
    )


async def _notify_squad_targets(
    *,
    text: str,
    thread: Any,
    thread_store: Any,
    sender_handle: str,
    telegram_chat_id: int,
    telegram_message_thread_id: int | None,
) -> None:
    """Wake up the squad members chosen by the routing logic via the agent
    message bus. Quiet on failure — the user_input row is already in the
    audit log, and the operator can re-trigger by reposting with @mention.
    """
    from koda.agents import get_message_bus
    from koda.squads import select_targets

    try:
        participants = await thread_store.list_participants(thread_id=thread.id)
    except Exception:
        log.exception("squad_routing_participants_lookup_failed", thread_id=thread.id)
        return
    participant_ids = [p.agent_id for p in participants if p.left_at is None]
    targets = select_targets(
        text,
        participant_agent_ids=participant_ids,
        coordinator_agent_id=thread.coordinator_agent_id,
    )
    if not targets:
        log.info("squad_routing_no_targets", thread_id=thread.id, participants=len(participant_ids))
        return

    bus = get_message_bus()
    notification_metadata: dict[str, Any] = {
        "kind": "squad_thread_input",
        "squad_id": thread.squad_id,
        "thread_id": thread.id,
        "telegram_chat_id": telegram_chat_id,
        "telegram_message_thread_id": telegram_message_thread_id,
        "from_user": sender_handle,
    }
    for target in targets:
        try:
            await bus.send(
                from_agent="squad_router",
                to_agent=target,
                content=text,
                metadata=notification_metadata,
            )
        except Exception:
            log.exception(
                "squad_routing_bus_send_failed",
                target=target,
                thread_id=thread.id,
            )


async def cmd_squad_thread_close(update: Update, context: BotContext) -> None:
    if not await _gate(update):
        return
    chat = update.effective_chat
    if chat is None or update.message is None:
        return
    if not _is_supergroup(update):
        await _reject_unsupported(update, "Use /squad_thread_close in a supergroup bound to a squad.")
        return

    from koda.squads import get_squad_thread_store

    thread_store = get_squad_thread_store()
    if thread_store is None:
        await update.message.reply_text("Squad thread store unavailable.")
        return
    topic_id = update.message.message_thread_id
    thread = await thread_store.find_by_telegram_topic(
        telegram_chat_id=chat.id,
        telegram_message_thread_id=topic_id,
    )
    if thread is None:
        await update.message.reply_text("No squad thread is bound to this topic.")
        return
    try:
        updated = await thread_store.update_thread_status(thread.id, "completed")
    except ValueError as exc:
        await update.message.reply_text(f"Cannot close thread: {exc}")
        return
    await update.message.reply_text(f"Thread '{updated.id}' marked completed (status={updated.status}).")
