"""Shared squad turn dispatch helpers."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from typing import Any

from koda.logging_config import get_logger
from koda.squads.delivery import (
    HANDOFF_EVENT_SCHEMA_VERSION,
    SQUAD_DELIVERY_SCHEMA_VERSION,
    build_handoff_event,
    build_route_decision,
    delivery_metric,
    delivery_status_for_source,
    handoff_metric,
    normalize_delivery_intent,
    route_quality_metric,
)

log = get_logger(__name__)


class _SilentSquadDispatchMessage:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.message_id = int(hashlib.sha1(text.encode(), usedforsecurity=False).hexdigest()[:8], 16) or 1

    async def edit_text(self, text: str, *_args: object, **_kwargs: object) -> _SilentSquadDispatchMessage:
        self.text = text
        return self

    async def delete(self, *_args: object, **_kwargs: object) -> None:
        return None


class _SilentSquadDispatchBot:
    """No-op bot for dashboard-originated squad turns."""

    async def send_message(self, *_args: object, text: str = "", **_kwargs: object) -> _SilentSquadDispatchMessage:
        return _SilentSquadDispatchMessage(text=text)

    async def send_document(
        self,
        *_args: object,
        caption: str | None = None,
        **_kwargs: object,
    ) -> _SilentSquadDispatchMessage:
        return _SilentSquadDispatchMessage(text=caption or "")

    async def send_voice(
        self,
        *_args: object,
        caption: str | None = None,
        **_kwargs: object,
    ) -> _SilentSquadDispatchMessage:
        return _SilentSquadDispatchMessage(text=caption or "")

    async def send_photo(
        self,
        *_args: object,
        caption: str | None = None,
        **_kwargs: object,
    ) -> _SilentSquadDispatchMessage:
        return _SilentSquadDispatchMessage(text=caption or "")

    async def send_animation(
        self,
        *_args: object,
        caption: str | None = None,
        **_kwargs: object,
    ) -> _SilentSquadDispatchMessage:
        return _SilentSquadDispatchMessage(text=caption or "")

    async def send_video(
        self,
        *_args: object,
        caption: str | None = None,
        **_kwargs: object,
    ) -> _SilentSquadDispatchMessage:
        return _SilentSquadDispatchMessage(text=caption or "")

    async def send_audio(
        self,
        *_args: object,
        caption: str | None = None,
        **_kwargs: object,
    ) -> _SilentSquadDispatchMessage:
        return _SilentSquadDispatchMessage(text=caption or "")

    async def send_chat_action(self, *_args: object, **_kwargs: object) -> None:
        return None

    async def delete_message(self, *_args: object, **_kwargs: object) -> None:
        return None


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
    raw_metadata = dict(metadata or {})
    semantic_result = raw_metadata.pop("semantic_result_object", raw_metadata.get("semantic_result"))
    member_profiles = raw_metadata.pop("member_profiles", None)
    delivery_intent = normalize_delivery_intent(raw_metadata.get("delivery_intent"), default="execution")
    delivery_status = delivery_status_for_source(source, has_targets=bool(targets))
    route_decision = build_route_decision(
        source=source,
        targets=targets,
        delivery_intent=delivery_intent,
        status=delivery_status,
        reason=reason or "",
        parent_message_id=parent_message_id,
        explicit_mentions=raw_metadata.get("explicit_mentions") or (),
        unresolved_mentions=raw_metadata.get("unresolved_mentions") or (),
        ambiguous_mentions=raw_metadata.get("ambiguous_mentions") or {},
        semantic_result=semantic_result,
        member_profiles=member_profiles,
        final_response_strategy=str(raw_metadata.get("final_response_strategy") or ""),
        required_tools=raw_metadata.get("required_tools") or raw_metadata.get("required_tool_ids") or (),
        required_skills=raw_metadata.get("required_skills") or raw_metadata.get("required_skill_ids") or (),
        min_confidence_for_route=raw_metadata.get("min_confidence_for_route"),
    )
    payload = {
        "schema_version": SQUAD_DELIVERY_SCHEMA_VERSION,
        "event_type": "routing_decision",
        "source": source,
        "targets": route_decision.targets,
        "parent_message_id": parent_message_id,
        "reason": reason,
        "delivery_status": delivery_status,
        "delivery_intent": route_decision.delivery_intent,
        "route_decision": route_decision.to_dict(),
        **raw_metadata,
    }
    try:
        message_id = int(
            await thread_store.post_thread_message(
                thread_id=thread_id,
                from_agent="squad_router",
                content=f"[routing_decision] {source} -> {', '.join(route_decision.targets) if targets else '(none)'}",
                message_type="system_event",
                metadata={
                    "event_type": "routing_decision",
                    "schema_version": SQUAD_DELIVERY_SCHEMA_VERSION,
                    "delivery_status": delivery_status,
                    "delivery_intent": route_decision.delivery_intent,
                    "parent_message_id": parent_message_id,
                    "payload": payload,
                    "squad_delivery": route_decision.to_dict(),
                },
            )
        )
        delivery_metric(event_type="routing_decision", status=delivery_status, source=source)
        route_quality_metric(
            source=source,
            status=route_decision.status,
            confidence_band=_confidence_band(route_decision.confidence),
        )
        return message_id
    except Exception:
        log.exception("squad_routing_decision_persist_failed", thread_id=thread_id, source=source, targets=targets)
        return None


async def record_squad_handoff_event(
    thread_store: Any,
    *,
    thread_id: str,
    source_agent_id: str,
    destination_agent_ids: list[str],
    reason: str,
    handoff_kind: str = "consult",
    context_policy: dict[str, Any] | None = None,
    deadline: str | None = None,
    return_criteria: list[str] | None = None,
    status: str = "requested",
    parent_message_id: str | None = None,
    correlation_id: str | None = None,
) -> int | None:
    event_id_seed = {
        "thread_id": thread_id,
        "source_agent_id": source_agent_id,
        "destination_agent_ids": destination_agent_ids,
        "reason": reason,
        "handoff_kind": handoff_kind,
        "parent_message_id": parent_message_id,
        "correlation_id": correlation_id,
    }
    handoff_id = (
        "handoff-"
        + hashlib.sha256(
            repr(sorted(event_id_seed.items())).encode("utf-8"),
            usedforsecurity=False,
        ).hexdigest()[:24]
    )
    run_graph_node_id = f"handoff_event:{handoff_id}"
    event = build_handoff_event(
        handoff_id=handoff_id,
        thread_id=thread_id,
        source_agent_id=source_agent_id,
        destination_agent_ids=destination_agent_ids,
        reason=reason,
        handoff_kind=handoff_kind,
        context_policy=context_policy,
        deadline=deadline,
        return_criteria=return_criteria,
        status=status,
        run_graph_node_id=run_graph_node_id,
        correlation_id=correlation_id,
        parent_message_id=parent_message_id,
    )
    payload = event.to_dict()
    try:
        message_id = int(
            await thread_store.post_thread_message(
                thread_id=thread_id,
                from_agent=source_agent_id,
                content=(
                    f"[handoff_event] {payload['handoff_kind']} "
                    f"{source_agent_id} -> {', '.join(payload['destination_agent_ids'])}: {reason}"
                ),
                message_type="system_event",
                metadata={
                    "event_type": "handoff_event",
                    "schema_version": HANDOFF_EVENT_SCHEMA_VERSION,
                    "delivery_status": "waiting_for_replies",
                    "delivery_intent": "execution",
                    "parent_message_id": parent_message_id,
                    "correlation_id": payload.get("correlation_id"),
                    "payload": payload,
                    "handoff_event": payload,
                },
                to_agent_ids=payload["destination_agent_ids"],
                correlation_id=payload.get("correlation_id"),
                in_reply_to=parent_message_id,
            )
        )
        handoff_metric(
            event_type="handoff_event",
            status=str(payload["status"]),
            handoff_kind=str(payload["handoff_kind"]),
        )
        return message_id
    except Exception:
        log.exception(
            "squad_handoff_event_persist_failed",
            thread_id=thread_id,
            source_agent_id=source_agent_id,
            destination_agent_ids=destination_agent_ids,
        )
        return None


async def record_squad_dispatch_unavailable(
    thread_store: Any,
    *,
    thread_id: str,
    target_agent_id: str,
    parent_message_id: str | None,
    error: str,
) -> None:
    delivery_metric(event_type="agent_dispatch_unavailable", status="failed", source="dispatch")
    try:
        await thread_store.post_thread_message(
            thread_id=thread_id,
            from_agent="squad_router",
            content=f"[agent_dispatch_unavailable] {target_agent_id}: {error}",
            message_type="system_event",
            metadata={
                "event_type": "agent_dispatch_unavailable",
                "schema_version": SQUAD_DELIVERY_SCHEMA_VERSION,
                "delivery_status": "failed",
                "delivery_intent": "execution",
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
        "schema_version": SQUAD_DELIVERY_SCHEMA_VERSION,
        "event_type": "mention_unresolved",
        "delivery_status": "blocked",
        "delivery_intent": "execution",
        "channel": channel,
        "unresolved": list(unresolved),
        "ambiguous": {key: list(value) for key, value in (ambiguous or {}).items()},
        "parent_message_id": parent_message_id,
    }
    delivery_metric(event_type="mention_unresolved", status="blocked", source=f"{channel}_mention")
    try:
        await thread_store.post_thread_message(
            thread_id=thread_id,
            from_agent="squad_router",
            content=f"[mention_unresolved] {', '.join(unresolved) if unresolved else 'ambiguous mention'}",
            message_type="system_event",
            metadata={
                "event_type": "mention_unresolved",
                "schema_version": SQUAD_DELIVERY_SCHEMA_VERSION,
                "delivery_status": "blocked",
                "delivery_intent": "execution",
                "parent_message_id": parent_message_id,
                "payload": payload,
            },
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


def _dashboard_actor_ids(thread_id: str) -> tuple[int, int]:
    digest = hashlib.sha256(f"squad-dashboard:{thread_id}".encode()).hexdigest()
    user_id = int(digest[:8], 16) % 2_000_000_000
    user_id = max(100_000, user_id)
    return user_id, -user_id


def _confidence_band(value: float) -> str:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence >= 0.8:
        return "high"
    if confidence >= 0.5:
        return "medium"
    if confidence > 0:
        return "low"
    return "none"


def _runtime_application_or_none() -> Any | None:
    try:
        from koda.services.runtime import get_runtime_controller

        return getattr(get_runtime_controller(), "_application", None)
    except Exception:
        log.debug("squad_runtime_application_unavailable", exc_info=True)
        return None


def _runtime_http_session_id(
    *,
    thread_id: str,
    target_agent_id: str,
    squad_task_id: str | None,
    delegation_request_id: str | None,
    parent_message_id: str | None,
) -> str:
    seed = ":".join(
        [
            "squad",
            thread_id,
            target_agent_id,
            squad_task_id or "",
            delegation_request_id or "",
            parent_message_id or "",
        ]
    )
    digest = hashlib.sha256(seed.encode()).hexdigest()[:24]
    return f"squad-{digest}"


async def _dispatch_via_runtime_http(
    *,
    target_agent_id: str,
    thread_id: str,
    query_text: str,
    parent_message_id: str | None,
    squad_task_id: str | None,
    delegation_chain: list[str] | None,
    delegation_request_id: str | None,
    delegation_origin_agent_id: str | None,
    telegram_message_thread_id: int | None,
    user_id: int | None,
    chat_id: int | None,
) -> SquadTurnDispatchResult:
    from koda.control_plane.manager import get_control_plane_manager

    session_id = _runtime_http_session_id(
        thread_id=thread_id,
        target_agent_id=target_agent_id,
        squad_task_id=squad_task_id,
        delegation_request_id=delegation_request_id,
        parent_message_id=parent_message_id,
    )
    manager = get_control_plane_manager()
    result = await asyncio.to_thread(
        manager.send_dashboard_squad_message,
        target_agent_id,
        text=query_text,
        session_id=session_id,
        squad_thread_id=thread_id,
        squad_task_id=squad_task_id,
        parent_message_id=parent_message_id,
        delegation_chain=list(delegation_chain or []),
        delegation_request_id=delegation_request_id,
        delegation_origin_agent_id=delegation_origin_agent_id,
        telegram_message_thread_id=telegram_message_thread_id,
        user_id=user_id,
        chat_id=chat_id,
    )
    raw_task_id = result.get("task_id") if isinstance(result, dict) else None
    enqueued_task_id = int(raw_task_id) if isinstance(raw_task_id, int | str) and str(raw_task_id).isdigit() else None
    return SquadTurnDispatchResult(
        target_agent_id=target_agent_id,
        transport="runtime_http",
        dispatched=True,
        message_id=str(result.get("session_id")) if isinstance(result, dict) and result.get("session_id") else None,
        enqueued_task_id=enqueued_task_id,
    )


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
    thread_id = str(getattr(thread, "id", "") or "")
    runtime_application = application or _runtime_application_or_none()
    resolved_user_id = int(user_id or getattr(thread, "owner_user_id", 0) or 0)
    resolved_chat_id = int(chat_id or getattr(thread, "telegram_chat_id", 0) or 0)
    if runtime_application is not None and thread_id and (not resolved_user_id or not resolved_chat_id):
        synthetic_user_id, synthetic_chat_id = _dashboard_actor_ids(thread_id)
        resolved_user_id = resolved_user_id or synthetic_user_id
        resolved_chat_id = resolved_chat_id or synthetic_chat_id
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

    if runtime_application is not None and resolved_user_id and resolved_chat_id:
        try:
            from koda.services.queue_manager import enqueue_squad_agent_task

            if getattr(thread, "telegram_chat_id", None):
                resolved_bot = await _telegram_bot_for_agent(
                    agent_id=target_agent_id,
                    chat_id=resolved_chat_id,
                    fallback_bot=bot_override or getattr(runtime_application, "bot", None),
                )
            else:
                resolved_bot = bot_override or _SilentSquadDispatchBot()
            task_id = await enqueue_squad_agent_task(
                application=runtime_application,
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

    runtime_http_error: str | None = None
    if thread_id:
        try:
            return await _dispatch_via_runtime_http(
                target_agent_id=target_agent_id,
                thread_id=thread_id,
                query_text=query_text,
                parent_message_id=parent_message_id,
                squad_task_id=squad_task_id,
                delegation_chain=delegation_chain,
                delegation_request_id=delegation_request_id,
                delegation_origin_agent_id=delegation_origin_agent_id,
                telegram_message_thread_id=base_metadata.get("telegram_message_thread_id"),
                user_id=resolved_user_id or None,
                chat_id=resolved_chat_id or None,
            )
        except Exception as exc:
            runtime_http_error = str(exc)
            log.warning(
                "squad_runtime_http_dispatch_failed",
                target_agent_id=target_agent_id,
                thread_id=thread_id,
                error=runtime_http_error,
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
                error=f"{msg_id}; runtime_http={runtime_http_error}" if runtime_http_error else str(msg_id),
            )
            return SquadTurnDispatchResult(
                target_agent_id=target_agent_id,
                transport="bus",
                dispatched=False,
                message_id=str(msg_id),
                error=f"{msg_id}; runtime_http={runtime_http_error}" if runtime_http_error else str(msg_id),
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
            error=f"{exc}; runtime_http={runtime_http_error}" if runtime_http_error else str(exc),
        )
        return SquadTurnDispatchResult(
            target_agent_id=target_agent_id,
            transport="bus",
            dispatched=False,
            error=f"{exc}; runtime_http={runtime_http_error}" if runtime_http_error else str(exc),
        )
