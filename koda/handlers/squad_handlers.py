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


async def _bot_is_admin(update: Update, context: BotContext) -> bool:
    chat = update.effective_chat
    if chat is None:
        return False
    try:
        me = await context.bot.get_me()
        member = await context.bot.get_chat_member(chat.id, me.id)
        status = str(getattr(member, "status", "") or "")
        return status in {"administrator", "creator"}
    except Exception:
        log.exception("squad_bind_admin_check_failed", chat_id=getattr(chat, "id", None))
        return False


async def _all_member_bots_are_admin(update: Update, *, squad_id: str) -> tuple[bool, str | None]:
    from koda.config import SQUAD_TELEGRAM_STRICT_ADMIN_CHECK

    if not SQUAD_TELEGRAM_STRICT_ADMIN_CHECK:
        return True, None
    chat = update.effective_chat
    if chat is None:
        return False, "No chat available for admin validation."
    try:
        from telegram import Bot

        from koda.control_plane.manager import get_control_plane_manager

        manager = get_control_plane_manager()
        agent_ids = [
            str(agent.get("id") or agent.get("agent_id") or "")
            for agent in manager.list_agents()
            if str(agent.get("squad_id") or "") == squad_id
        ]
        missing: list[str] = []
        not_admin: list[str] = []
        for agent_id in [aid for aid in agent_ids if aid]:
            token = manager.get_decrypted_secret_value(agent_id, "AGENT_TOKEN")
            if not token:
                missing.append(agent_id)
                continue
            bot = Bot(token)
            try:
                me = await bot.get_me()
                member = await bot.get_chat_member(chat.id, me.id)
                status = str(getattr(member, "status", "") or "")
                if status not in {"administrator", "creator"}:
                    not_admin.append(agent_id)
            except Exception:
                log.exception("squad_bind_member_admin_check_failed", chat_id=chat.id, agent_id=agent_id)
                not_admin.append(agent_id)
        if missing:
            return False, "Missing AGENT_TOKEN for squad bots: " + ", ".join(sorted(missing))
        if not_admin:
            return False, "These squad bots are not admins in this supergroup: " + ", ".join(sorted(not_admin))
    except Exception as exc:
        log.exception("squad_bind_strict_admin_check_failed", chat_id=getattr(chat, "id", None), squad_id=squad_id)
        return False, f"Strict admin validation failed: {exc}"
    return True, None


def _resolve_workspace_and_squad(args: list[Any]) -> tuple[str | None, str | None, str | None]:
    if len(args) >= 2:
        return str(args[0]).strip(), str(args[1]).strip(), None
    if len(args) == 1:
        squad_id = str(args[0]).strip()
        try:
            from koda.control_plane.manager import get_control_plane_manager

            row = get_control_plane_manager()._squad_row(squad_id)
            return str(row["workspace_id"]), squad_id, None
        except Exception as exc:
            return None, squad_id, f"Cannot resolve workspace for squad {squad_id!r}: {exc}"
    return None, None, "Usage: /squad_bind <workspace_id> <squad_id>"


async def cmd_squad_bind(update: Update, context: BotContext) -> None:
    if not await _gate(update):
        return
    chat = update.effective_chat
    if chat is None or update.message is None:
        return
    if not _is_supergroup(update):
        await _reject_unsupported(update, "Use /squad_bind inside a Telegram supergroup.")
        return
    if not _is_forum(update):
        await _reject_unsupported(update, "This supergroup must have forum topics enabled before /squad_bind.")
        return
    if not await _bot_is_admin(update, context):
        await _reject_unsupported(update, "The bot must be an admin in this supergroup before /squad_bind.")
        return
    args = (context.args or []) if context else []
    workspace_id, squad_id, error = _resolve_workspace_and_squad(list(args))
    if error:
        await update.message.reply_text(error)
        return
    if not workspace_id or not squad_id:
        await update.message.reply_text("Usage: /squad_bind <workspace_id> <squad_id>")
        return
    all_admin, admin_error = await _all_member_bots_are_admin(update, squad_id=squad_id)
    if not all_admin:
        await _reject_unsupported(update, admin_error or "All squad bots must be admins in this supergroup.")
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
            metadata={"workspace_id": workspace_id},
        )
    except TelegramBindingConflictError as exc:
        await update.message.reply_text(f"Bind failed: {exc}")
        return
    forum_label = "forum" if binding.is_forum else "non-forum"
    await update.message.reply_text(
        f"Squad '{binding.squad_id}' bound to this chat ({forum_label}, workspace={workspace_id})."
    )


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

    from koda.squads import (
        get_squad_thread_store,
        get_telegram_binding_service,
        sync_thread_participants_from_squad,
    )

    binding_service = get_telegram_binding_service()
    thread_store = get_squad_thread_store()
    if binding_service is None or thread_store is None:
        await update.message.reply_text("Squad services unavailable (POSTGRES_URL not configured).")
        return
    binding = await binding_service.get_for_chat(chat.id)
    if binding is None:
        await update.message.reply_text(
            "This chat is not bound to a squad. Run /squad_bind <workspace_id> <squad_id> first."
        )
        return

    workspace_id = (context.user_data or {}).get("squad_default_workspace_id") or binding.metadata.get("workspace_id")
    if not workspace_id:
        await update.message.reply_text(
            "Cannot create thread: no workspace_id known for this chat. Set "
            "user_data['squad_default_workspace_id'] or binding metadata.workspace_id."
        )
        return
    title_key = " ".join(title.casefold().split())
    try:
        existing_threads = await thread_store.list_threads(
            workspace_id=str(workspace_id),
            squad_id=binding.squad_id,
            limit=200,
        )
        for existing in existing_threads:
            if (
                existing.telegram_chat_id == chat.id
                and existing.metadata.get("telegram_title_key") == title_key
                and existing.status in {"open", "paused"}
            ):
                await update.message.reply_text(
                    f"Thread '{existing.id}' already exists for this topic title "
                    f"(topic={existing.telegram_message_thread_id or 'general'})."
                )
                return
    except Exception:
        log.exception("squad_thread_new_idempotency_lookup_failed", squad_id=binding.squad_id)

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
    participants: list[tuple[str, str]] = []
    try:
        from koda.control_plane.manager import get_control_plane_manager

        for agent in get_control_plane_manager().list_agents():
            if str(agent.get("squad_id") or "") == binding.squad_id:
                agent_id = str(agent.get("id") or agent.get("agent_id") or "")
                if agent_id:
                    role = "coordinator" if agent_id == coordinator else "worker"
                    participants.append((agent_id, role))
    except Exception:
        log.exception("squad_thread_new_member_lookup_failed", squad_id=binding.squad_id)
    thread = await thread_store.create_thread(
        workspace_id=str(workspace_id),
        squad_id=binding.squad_id,
        title=title,
        owner_user_id=user.id if user is not None else None,
        coordinator_agent_id=coordinator,
        telegram_chat_id=chat.id,
        telegram_message_thread_id=message_thread_id,
        metadata={"telegram_title_key": title_key},
        participants=participants,
    )
    try:
        await sync_thread_participants_from_squad(thread_store, thread=thread)
    except Exception:
        log.exception("squad_thread_new_member_sync_failed", thread_id=thread.id, squad_id=binding.squad_id)
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

    from koda.squads import (
        get_squad_thread_store,
        get_telegram_binding_service,
        sync_thread_participants_from_squad,
    )

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
    participants = await sync_thread_participants_from_squad(thread_store, thread=thread)

    sender_handle = user.username or str(user.id)
    metadata = {
        "telegram_user_id": user.id,
        "telegram_username": user.username,
        "telegram_message_id": message.message_id,
        "telegram_chat_id": chat.id,
        "telegram_message_thread_id": message.message_thread_id,
    }
    try:
        user_msg_id = await thread_store.post_thread_message(
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

    reply_to_agent_id: str | None = None
    if message.reply_to_message is not None:
        reply_msg_id = getattr(message.reply_to_message, "message_id", None)
        try:
            recent = await thread_store.thread_history(thread_id=thread.id, limit=50)
            for row in recent:
                row_meta = row.get("metadata") or {}
                if row_meta.get("telegram_message_id") == reply_msg_id:
                    candidate = str(row.get("from") or "")
                    if candidate and not candidate.startswith("user:") and candidate != "squad_router":
                        reply_to_agent_id = candidate
                    break
        except Exception:
            log.exception("squad_reply_continuation_lookup_failed", thread_id=thread.id)

    await _notify_squad_targets(
        text=text,
        thread=thread,
        thread_store=thread_store,
        participants=participants,
        sender_handle=sender_handle,
        telegram_chat_id=chat.id,
        telegram_message_thread_id=message.message_thread_id,
        reply_to_agent_id=reply_to_agent_id,
        bot_context=context,
        user_id=user.id,
        parent_message_id=f"msg-{user_msg_id}",
        channel="telegram",
        channel_context={"message": message, "chat": chat, "bot": getattr(context, "bot", None)},
    )


async def _notify_squad_targets(
    *,
    text: str,
    thread: Any,
    thread_store: Any,
    sender_handle: str,
    telegram_chat_id: int,
    telegram_message_thread_id: int | None,
    reply_to_agent_id: str | None = None,
    bot_context: BotContext | None = None,
    user_id: int | None = None,
    parent_message_id: str | None = None,
    participants: list[Any] | None = None,
    channel: str = "telegram",
    channel_context: dict[str, Any] | None = None,
) -> None:
    """Wake up the squad members chosen by the routing logic via the agent
    message bus. Quiet on failure — the user_input row is already in the
    audit log, and the operator can re-trigger by reposting with @mention.
    """
    from koda.config import SQUAD_COORDINATOR_MODE
    from koda.squads import (
        SquadCoordinatorEngine,
        build_squad_capability_summaries,
        dispatch_squad_turn,
        get_squad_mention_resolver,
        get_squad_semantic_router,
        get_squad_task_store,
        get_squad_triage_service,
        record_squad_mention_unresolved,
        record_squad_routing_decision,
        select_targets,
        should_use_coordinator_engine,
    )

    if participants is None:
        try:
            participants = await thread_store.list_participants(thread_id=thread.id)
        except Exception:
            log.exception("squad_routing_participants_lookup_failed", thread_id=thread.id)
            return
    participant_ids = [p.agent_id for p in participants if p.left_at is None]
    capability_summaries = await build_squad_capability_summaries(
        squad_id=thread.squad_id,
        participant_agent_ids=participant_ids,
        coordinator_agent_id=thread.coordinator_agent_id,
    )
    capability_hints = {
        summary.agent_id: " ".join(str(value) for value in summary.to_dict().values())
        for summary in capability_summaries
    }
    semantic_router = get_squad_semantic_router()
    semantic_result = await semantic_router.rank_agents(
        text,
        capability_summaries,
        squad_id=thread.squad_id,
        coordinator_agent_id=thread.coordinator_agent_id,
    )
    mention_resolution = await get_squad_mention_resolver().resolve(
        text,
        participants=participants,
        channel=channel,
        channel_context=channel_context,
        capability_summaries=capability_summaries,
    )
    triage_result = await get_squad_triage_service().triage_user_input(
        thread_store=thread_store,
        thread=thread,
        participants=participants,
        text=text,
        user_input_message_id=parent_message_id,
        channel=channel,
        channel_context=channel_context,
        capability_summaries=capability_summaries,
        semantic_result=semantic_result,
        execution_targets=mention_resolution.resolved_agent_ids if mention_resolution.has_resolved_mentions else [],
        routing_source=f"{channel}_mention" if mention_resolution.has_resolved_mentions else "triage",
        allow_proposals=not mention_resolution.has_mentions,
    )
    if mention_resolution.has_mentions and (
        (mention_resolution.unresolved or mention_resolution.ambiguous) and not mention_resolution.has_resolved_mentions
    ):
        await record_squad_mention_unresolved(
            thread_store,
            thread_id=thread.id,
            unresolved=mention_resolution.unresolved,
            ambiguous=mention_resolution.ambiguous,
            parent_message_id=parent_message_id,
            channel=channel,
        )
        if bot_context is not None:
            message = (channel_context or {}).get("message")
            reply = getattr(message, "reply_text", None)
            if callable(reply):
                await reply("Não encontrei esse agente no squad. Use o nome/username de um membro ativo do squad.")
        return
    if mention_resolution.unresolved or mention_resolution.ambiguous:
        await record_squad_mention_unresolved(
            thread_store,
            thread_id=thread.id,
            unresolved=mention_resolution.unresolved,
            ambiguous=mention_resolution.ambiguous,
            parent_message_id=parent_message_id,
            channel=channel,
        )
    if mention_resolution.has_resolved_mentions:
        targets = [agent_id for agent_id in mention_resolution.resolved_agent_ids if agent_id in participant_ids]
        await record_squad_routing_decision(
            thread_store,
            thread_id=thread.id,
            source=f"{channel}_mention",
            targets=targets,
            parent_message_id=parent_message_id,
            metadata={"mention_resolution": mention_resolution.to_dict()},
        )
        for target in targets:
            await dispatch_squad_turn(
                target_agent_id=target,
                thread=thread,
                thread_store=thread_store,
                query_text=text,
                parent_message_id=parent_message_id,
                metadata={"from_user": sender_handle, "source": f"{channel}_mention", "delivery_intent": "execution"},
                application=getattr(bot_context, "application", None) if bot_context is not None else None,
                user_id=user_id,
                chat_id=telegram_chat_id,
                delegation_chain=["squad_router"],
                telegram_message_thread_id=telegram_message_thread_id,
                bot_override=getattr(bot_context, "bot", None) if bot_context is not None else None,
            )
        return
    if (
        SQUAD_COORDINATOR_MODE == "supervisor"
        and thread.coordinator_agent_id
        and should_use_coordinator_engine(
            text,
            participant_agent_ids=participant_ids,
            coordinator_agent_id=thread.coordinator_agent_id,
            reply_to_agent_id=reply_to_agent_id,
            semantic_result=semantic_result,
        )
    ):
        task_store = get_squad_task_store()
        if task_store is not None:
            try:
                coordinator_id = thread.coordinator_agent_id
                if not coordinator_id:
                    raise RuntimeError("coordinator unavailable")
                engine = SquadCoordinatorEngine(thread_store=thread_store, task_store=task_store)

                async def dispatch_task(request: Any) -> str | int | None:
                    result = await dispatch_squad_turn(
                        target_agent_id=request.agent_id,
                        thread=thread,
                        thread_store=thread_store,
                        query_text=request.content,
                        parent_message_id=parent_message_id,
                        metadata={**dict(request.metadata or {}), "from_agent": coordinator_id},
                        application=getattr(bot_context, "application", None) if bot_context is not None else None,
                        user_id=user_id,
                        chat_id=telegram_chat_id,
                        squad_task_id=request.task_descriptor.id,
                        delegation_chain=[coordinator_id],
                        delegation_request_id=request.request_id,
                        delegation_origin_agent_id=coordinator_id,
                        telegram_message_thread_id=telegram_message_thread_id,
                        bot_override=getattr(bot_context, "bot", None) if bot_context is not None else None,
                    )
                    return result.enqueued_task_id or result.message_id

                execution = await engine.coordinate_user_input(
                    text=text,
                    thread=thread,
                    participants=participants,
                    coordinator_agent_id=coordinator_id,
                    capability_hints=capability_hints,
                    capability_summaries=capability_summaries,
                    semantic_result=semantic_result,
                    dispatch=dispatch_task,
                    parent_message_id=parent_message_id,
                    user_id=user_id,
                    chat_id=telegram_chat_id,
                    telegram_message_thread_id=telegram_message_thread_id,
                    awareness_agent_ids=triage_result.awareness_agent_ids,
                    contribution_proposals=[item.to_dict() for item in triage_result.proposal_candidates],
                )
                if execution.coordinated:
                    await record_squad_routing_decision(
                        thread_store,
                        thread_id=thread.id,
                        source="coordinator_engine",
                        targets=execution.dispatched_agents,
                        parent_message_id=parent_message_id,
                        metadata={"mode": execution.decision.mode, "task_ids": execution.task_ids},
                    )
                    log.info(
                        "squad_supervisor_coordinated",
                        thread_id=thread.id,
                        coordinator=thread.coordinator_agent_id,
                        agents=execution.dispatched_agents,
                        tasks=execution.task_ids,
                    )
                    return
            except Exception:
                log.exception(
                    "squad_supervisor_coordination_failed",
                    thread_id=thread.id,
                    coordinator=thread.coordinator_agent_id,
                )
    if not thread.coordinator_agent_id and triage_result.proposal_candidates and not reply_to_agent_id:
        targets = [triage_result.proposal_candidates[0].agent_id]
    else:
        targets = select_targets(
            text,
            participant_agent_ids=participant_ids,
            coordinator_agent_id=thread.coordinator_agent_id,
            reply_to_agent_id=reply_to_agent_id,
            capability_hints=capability_hints,
            semantic_result=semantic_result,
            explicit_mention_agent_ids=mention_resolution.resolved_agent_ids,
        )
    if not targets:
        log.info("squad_routing_no_targets", thread_id=thread.id, participants=len(participant_ids))
        return

    routing_source = (
        "reply"
        if reply_to_agent_id and targets == [reply_to_agent_id]
        else "proposal_arbitration"
        if not thread.coordinator_agent_id and triage_result.proposal_candidates
        else "semantic"
        if semantic_result.available and targets == semantic_result.top_agents(include_coordinator=False)
        else "coordinator"
        if thread.coordinator_agent_id and targets == [thread.coordinator_agent_id]
        else "fallback"
    )
    await record_squad_routing_decision(
        thread_store,
        thread_id=thread.id,
        source=routing_source,
        targets=targets,
        parent_message_id=parent_message_id,
        metadata={
            "semantic_result": semantic_result.to_dict(),
            "reply_to_agent_id": reply_to_agent_id,
            "triage": triage_result.to_dict(),
        },
    )
    for target in targets:
        await dispatch_squad_turn(
            target_agent_id=target,
            thread=thread,
            thread_store=thread_store,
            query_text=text,
            parent_message_id=parent_message_id,
            metadata={"from_user": sender_handle, "source": routing_source, "delivery_intent": "execution"},
            application=getattr(bot_context, "application", None) if bot_context is not None else None,
            user_id=user_id,
            chat_id=telegram_chat_id,
            delegation_chain=["squad_router"],
            telegram_message_thread_id=telegram_message_thread_id,
            bot_override=getattr(bot_context, "bot", None) if bot_context is not None else None,
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
