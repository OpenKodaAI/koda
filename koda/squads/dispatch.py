"""Shared squad turn dispatch helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from koda.logging_config import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class SquadTurnDispatchResult:
    target_agent_id: str
    transport: str
    dispatched: bool
    message_id: str | None = None
    enqueued_task_id: int | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_agent_id": self.target_agent_id,
            "transport": self.transport,
            "dispatched": self.dispatched,
            "message_id": self.message_id,
            "enqueued_task_id": self.enqueued_task_id,
            "error": self.error,
        }


async def record_squad_routing_decision(
    thread_store: Any,
    *,
    thread_id: str,
    source: str,
    targets: list[str],
    parent_message_id: str | None = None,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> int | None:
    payload = {
        "event_type": "routing_decision",
        "source": source,
        "targets": list(targets),
        "parent_message_id": parent_message_id,
        "reason": reason,
        "delivery_intent": "execution" if targets else "awareness",
        **dict(metadata or {}),
    }
    try:
        return int(
            await thread_store.post_thread_message(
                thread_id=thread_id,
                from_agent="squad_router",
                content=f"[routing_decision] {source} -> {', '.join(targets) if targets else '(none)'}",
                message_type="system_event",
                metadata={"event_type": "routing_decision", "parent_message_id": parent_message_id, "payload": payload},
            )
        )
    except Exception:
        log.exception("squad_routing_decision_persist_failed", thread_id=thread_id, source=source, targets=targets)
        return None


async def record_squad_dispatch_unavailable(
    thread_store: Any,
    *,
    thread_id: str,
    target_agent_id: str,
    parent_message_id: str | None,
    error: str,
) -> None:
    try:
        await thread_store.post_thread_message(
            thread_id=thread_id,
            from_agent="squad_router",
            content=f"[agent_dispatch_unavailable] {target_agent_id}: {error}",
            message_type="system_event",
            metadata={
                "event_type": "agent_dispatch_unavailable",
                "parent_message_id": parent_message_id,
                "payload": {"target_agent_id": target_agent_id, "error": error},
            },
        )
    except Exception:
        log.exception("squad_dispatch_unavailable_persist_failed", thread_id=thread_id, target=target_agent_id)


async def record_squad_mention_unresolved(
    thread_store: Any,
    *,
    thread_id: str,
    unresolved: list[str],
    ambiguous: dict[str, list[str]] | None = None,
    parent_message_id: str | None = None,
    channel: str = "telegram",
) -> None:
    payload = {
        "event_type": "mention_unresolved",
        "channel": channel,
        "unresolved": list(unresolved),
        "ambiguous": {key: list(value) for key, value in (ambiguous or {}).items()},
        "parent_message_id": parent_message_id,
    }
    try:
        await thread_store.post_thread_message(
            thread_id=thread_id,
            from_agent="squad_router",
            content=f"[mention_unresolved] {', '.join(unresolved) if unresolved else 'ambiguous mention'}",
            message_type="system_event",
            metadata={"event_type": "mention_unresolved", "parent_message_id": parent_message_id, "payload": payload},
        )
    except Exception:
        log.exception("squad_mention_unresolved_persist_failed", thread_id=thread_id, unresolved=unresolved)


async def _telegram_bot_for_agent(
    *,
    agent_id: str,
    chat_id: int,
    fallback_bot: Any | None,
) -> Any | None:
    try:
        from koda.control_plane.manager import get_control_plane_manager
        from koda.squads.telegram_outbound import get_outbound_bot

        token = get_control_plane_manager().get_decrypted_secret_value(agent_id, "AGENT_TOKEN")
        if not token:
            return fallback_bot
        bot = get_outbound_bot(token)
        me = await bot.get_me()
        bot_id = getattr(me, "id", None)
        if bot_id is None:
            return fallback_bot
        member = await bot.get_chat_member(chat_id=chat_id, user_id=bot_id)
        status = str(getattr(member, "status", "") or "").lower()
        if status in {"administrator", "creator"}:
            return bot
    except Exception:
        log.debug("squad_agent_bot_resolution_failed", agent_id=agent_id, chat_id=chat_id, exc_info=True)
    return fallback_bot


async def dispatch_squad_turn(
    *,
    target_agent_id: str,
    thread: Any,
    thread_store: Any,
    query_text: str,
    parent_message_id: str | None,
    metadata: dict[str, Any] | None = None,
    application: Any | None = None,
    user_id: int | None = None,
    chat_id: int | None = None,
    squad_task_id: str | None = None,
    delegation_chain: list[str] | None = None,
    delegation_request_id: str | None = None,
    delegation_origin_agent_id: str | None = None,
    telegram_message_thread_id: int | None = None,
    bot_override: Any | None = None,
) -> SquadTurnDispatchResult:
    """Dispatch one squad-scoped turn to a target agent.

    The local Telegram runtime can execute another squad member in-process by
    setting ``executing_agent_id`` on the queued item. When no runtime
    application is available, delivery falls back to the configured message bus.
    """
    resolved_user_id = int(user_id or getattr(thread, "owner_user_id", 0) or 0)
    resolved_chat_id = int(chat_id or getattr(thread, "telegram_chat_id", 0) or 0)
    thread_id = str(getattr(thread, "id", "") or "")
    base_metadata: dict[str, Any] = {
        "kind": "squad_thread_input",
        "squad_id": getattr(thread, "squad_id", None),
        "thread_id": thread_id,
        "telegram_chat_id": getattr(thread, "telegram_chat_id", None),
        "telegram_message_thread_id": telegram_message_thread_id
        if telegram_message_thread_id is not None
        else getattr(thread, "telegram_message_thread_id", None),
        "from_user": (metadata or {}).get("from_user"),
        "user_id": resolved_user_id,
        "chat_id": resolved_chat_id,
        "parent_message_id": parent_message_id,
        "delivery_intent": "execution",
    }
    base_metadata.update(dict(metadata or {}))

    if application is not None and resolved_user_id and resolved_chat_id:
        try:
            from koda.services.queue_manager import enqueue_squad_agent_task

            resolved_bot = await _telegram_bot_for_agent(
                agent_id=target_agent_id,
                chat_id=resolved_chat_id,
                fallback_bot=bot_override or getattr(application, "bot", None),
            )
            task_id = await enqueue_squad_agent_task(
                application=application,
                user_id=resolved_user_id,
                chat_id=resolved_chat_id,
                query_text=query_text,
                executing_agent_id=target_agent_id,
                squad_thread_id=thread_id,
                squad_task_id=squad_task_id,
                parent_message_id=parent_message_id,
                delegation_chain=list(delegation_chain or []),
                delegation_request_id=delegation_request_id,
                delegation_origin_agent_id=delegation_origin_agent_id,
                telegram_message_thread_id=base_metadata.get("telegram_message_thread_id"),
                bot_override=resolved_bot,
            )
            return SquadTurnDispatchResult(
                target_agent_id=target_agent_id,
                transport="local_queue",
                dispatched=True,
                enqueued_task_id=int(task_id),
            )
        except Exception as exc:
            await record_squad_dispatch_unavailable(
                thread_store,
                thread_id=thread_id,
                target_agent_id=target_agent_id,
                parent_message_id=parent_message_id,
                error=str(exc),
            )
            return SquadTurnDispatchResult(
                target_agent_id=target_agent_id,
                transport="local_queue",
                dispatched=False,
                error=str(exc),
            )

    try:
        from koda.agents import get_message_bus

        msg_id = await get_message_bus().send(
            from_agent=str(base_metadata.get("from_agent") or "squad_router"),
            to_agent=target_agent_id,
            content=query_text,
            metadata=base_metadata,
        )
        if str(msg_id).startswith("Error:"):
            await record_squad_dispatch_unavailable(
                thread_store,
                thread_id=thread_id,
                target_agent_id=target_agent_id,
                parent_message_id=parent_message_id,
                error=str(msg_id),
            )
            return SquadTurnDispatchResult(
                target_agent_id=target_agent_id,
                transport="bus",
                dispatched=False,
                message_id=str(msg_id),
                error=str(msg_id),
            )
        return SquadTurnDispatchResult(
            target_agent_id=target_agent_id,
            transport="bus",
            dispatched=True,
            message_id=str(msg_id),
        )
    except Exception as exc:
        await record_squad_dispatch_unavailable(
            thread_store,
            thread_id=thread_id,
            target_agent_id=target_agent_id,
            parent_message_id=parent_message_id,
            error=str(exc),
        )
        return SquadTurnDispatchResult(
            target_agent_id=target_agent_id,
            transport="bus",
            dispatched=False,
            error=str(exc),
        )
