"""Operational replies for squad threads.

``thread_reply.v1`` is intentionally layered over the existing squad message
envelope. Messages still live in ``squad_messages``; this service only tracks
the response obligations that make agent-to-agent replies actionable.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from koda.logging_config import get_logger
from koda.squads.threads import SquadThreadStore

log = get_logger(__name__)

THREAD_REPLY_SCHEMA_VERSION = "thread_reply.v1"
DEFAULT_REPLY_DEADLINE_SECONDS = 600
MAX_REPLY_DEPTH = 6
MAX_OPEN_OBLIGATIONS_PER_THREAD = 20
MAX_FOLLOWUPS_PER_OBLIGATION = 2

_MESSAGE_REF_RE = re.compile(r"(\d+)$")
_VALID_OBLIGATION_STATUSES = {"open", "answered", "timed_out", "cancelled"}


class ThreadReplyError(ValueError):
    """Typed, user-facing thread reply failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def to_error_envelope(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "category": "thread_reply",
            "message": self.message,
            "retryable": self.code in {"reply.deadline_exceeded"},
            "user_action": "Check the room thread, target agents, and open reply obligations.",
        }


@dataclass(frozen=True)
class ReplyObligation:
    id: int
    obligation_key: str
    thread_id: str
    source_message_id: int
    target_agent_id: str
    status: str
    requires_response_by: datetime | None = None
    resolved_by_message_id: int | None = None
    followup_count: int = 0
    last_followup_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "obligationId": self.id,
            "obligationKey": self.obligation_key,
            "threadId": self.thread_id,
            "sourceMessageId": self.source_message_id,
            "targetAgentId": self.target_agent_id,
            "status": self.status,
            "requiresResponseBy": self.requires_response_by.isoformat() if self.requires_response_by else None,
            "resolvedByMessageId": self.resolved_by_message_id,
            "followupCount": self.followup_count,
            "lastFollowupAt": self.last_followup_at.isoformat() if self.last_followup_at else None,
            "metadata": dict(self.metadata),
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }


def message_ref_to_id(value: int | str | None) -> int | None:
    """Accept ``42`` or ``msg-42`` style refs."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return int(raw)
    match = _MESSAGE_REF_RE.search(raw)
    return int(match.group(1)) if match else None


def message_ref(value: int | str | None) -> str | None:
    msg_id = message_ref_to_id(value)
    return f"msg-{msg_id}" if msg_id is not None else None


def _decode_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return None
    return value


def _row_to_obligation(row: Any) -> ReplyObligation:
    metadata = _decode_json(row["metadata_json"]) or {}
    return ReplyObligation(
        id=int(row["id"]),
        obligation_key=str(row["obligation_key"]),
        thread_id=str(row["thread_id"]),
        source_message_id=int(row["source_message_id"]),
        target_agent_id=str(row["target_agent_id"]),
        status=str(row["status"]),
        requires_response_by=row["requires_response_by"],
        resolved_by_message_id=(
            int(row["resolved_by_message_id"]) if row["resolved_by_message_id"] is not None else None
        ),
        followup_count=int(row["followup_count"] or 0),
        last_followup_at=row["last_followup_at"],
        metadata=metadata if isinstance(metadata, dict) else {},
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _normalize_target_agent_ids(values: list[str] | tuple[str, ...] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        agent_id = str(value or "").strip()
        key = agent_id.lower()
        if not agent_id or key in seen:
            continue
        seen.add(key)
        out.append(agent_id)
    return out


def _parse_deadline(value: str | datetime | None) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        raw = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(raw)
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
        except ValueError as exc:
            raise ThreadReplyError("reply.policy_denied", "Invalid requires_response_by timestamp.") from exc
    return datetime.now(UTC) + timedelta(seconds=DEFAULT_REPLY_DEADLINE_SECONDS)


def _audit_reply_event(event_type: str, **details: Any) -> None:
    try:
        from koda.services.audit import AuditEvent, emit

        emit(AuditEvent(event_type=event_type, details=details))
    except Exception:
        log.debug("thread_reply_audit_failed", event_type=event_type, exc_info=True)


def _metric_reply_event(event_type: str, status: str) -> None:
    try:
        from koda.config import AGENT_ID
        from koda.services.metrics import SQUAD_REPLY_EVENTS

        SQUAD_REPLY_EVENTS.labels(agent_id=AGENT_ID or "default", event_type=event_type, status=status).inc()
    except Exception:
        log.debug("thread_reply_metric_failed", event_type=event_type, exc_info=True)


class ThreadReplyService:
    def __init__(self, thread_store: SquadThreadStore) -> None:
        self._thread_store = thread_store

    async def _conn_and_schema(self) -> tuple[Any, str]:
        pool = await self._thread_store._ensure_pool()  # noqa: SLF001 - service composes the store.
        return pool, self._thread_store._schema  # noqa: SLF001

    async def _reply_depth(self, conn: Any, schema: str, *, thread_id: str, source_message_id: int) -> int:
        depth = 0
        current = source_message_id
        visited: set[int] = set()
        while current and current not in visited:
            visited.add(current)
            parent_ref = await conn.fetchval(
                f"""SELECT in_reply_to
                      FROM "{schema}"."squad_messages"
                     WHERE thread_id = $1 AND id = $2""",
                thread_id,
                current,
            )
            parent_id = message_ref_to_id(parent_ref)
            if parent_id is None:
                break
            depth += 1
            if depth > MAX_REPLY_DEPTH:
                return depth
            current = parent_id
        return depth

    async def create_obligations(
        self,
        *,
        thread_id: str,
        source_message_id: int | str,
        target_agent_ids: list[str] | tuple[str, ...],
        source_agent_id: str | None = None,
        requires_response_by: str | datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> list[ReplyObligation]:
        source_id = message_ref_to_id(source_message_id)
        if source_id is None:
            raise ThreadReplyError("reply.parent_not_found", "Reply source message was not found.")
        targets = _normalize_target_agent_ids(list(target_agent_ids))
        if not targets:
            return []
        deadline = _parse_deadline(requires_response_by)
        meta = {
            "schema_version": THREAD_REPLY_SCHEMA_VERSION,
            "source_agent_id": source_agent_id,
            **dict(metadata or {}),
        }
        pool, schema = await self._conn_and_schema()
        async with pool.acquire() as conn, conn.transaction():
            thread = await conn.fetchrow(
                f'SELECT id, status, coordinator_agent_id FROM "{schema}"."squad_threads" WHERE id = $1 FOR UPDATE',
                thread_id,
            )
            if thread is None:
                raise ThreadReplyError("reply.parent_not_found", "Thread was not found.")
            if str(thread["status"]) != "open":
                raise ThreadReplyError("reply.policy_denied", f"Thread is {thread['status']}.")
            source = await conn.fetchrow(
                f'SELECT id, thread_id FROM "{schema}"."squad_messages" WHERE thread_id = $1 AND id = $2',
                thread_id,
                source_id,
            )
            if source is None:
                raise ThreadReplyError("reply.parent_not_found", "Reply source message was not found.")
            reply_depth = await self._reply_depth(
                conn,
                schema,
                thread_id=thread_id,
                source_message_id=source_id,
            )
            if reply_depth >= MAX_REPLY_DEPTH:
                raise ThreadReplyError("reply.loop_detected", "Reply depth limit reached for this thread.")
            participants = await conn.fetch(
                f"""SELECT agent_id
                      FROM "{schema}"."squad_thread_participants"
                     WHERE thread_id = $1 AND left_at IS NULL AND paused = FALSE""",
                thread_id,
            )
            allowed = {str(row["agent_id"]) for row in participants}
            coordinator = str(thread["coordinator_agent_id"] or "")
            if coordinator:
                allowed.add(coordinator)
            missing = [target for target in targets if target not in allowed]
            if missing:
                raise ThreadReplyError(
                    "reply.target_not_participant",
                    f"Target agent is not an active participant: {', '.join(missing)}.",
                )
            open_count = int(
                await conn.fetchval(
                    f"""SELECT COUNT(*)
                          FROM "{schema}"."squad_reply_obligations"
                         WHERE thread_id = $1 AND status = 'open'""",
                    thread_id,
                )
                or 0
            )
            if open_count + len(targets) > MAX_OPEN_OBLIGATIONS_PER_THREAD:
                raise ThreadReplyError("reply.policy_denied", "Too many open reply obligations in this thread.")
            rows = []
            for target in targets:
                obligation_key = str(meta.get("obligation_key") or f"reply:{thread_id}:{source_id}:{target}")
                row = await conn.fetchrow(
                    f"""INSERT INTO "{schema}"."squad_reply_obligations"
                            (obligation_key, thread_id, source_message_id, target_agent_id,
                             status, requires_response_by, metadata_json, updated_at)
                          VALUES ($1, $2, $3, $4, 'open', $5, $6::jsonb, NOW())
                          ON CONFLICT (obligation_key) DO NOTHING
                          RETURNING *""",
                    obligation_key,
                    thread_id,
                    source_id,
                    target,
                    deadline,
                    json.dumps(meta, default=str),
                )
                if row is None:
                    row = await conn.fetchrow(
                        f"""SELECT *
                              FROM "{schema}"."squad_reply_obligations"
                             WHERE obligation_key = $1""",
                        obligation_key,
                    )
                rows.append(row)
        obligations = [_row_to_obligation(row) for row in rows]
        for obligation in obligations:
            _audit_reply_event("squad.reply.obligation_created", **obligation.to_dict())
            _metric_reply_event("obligation_created", obligation.status)
        await self._thread_store.notify_event(
            thread_id=thread_id,
            event_type="reply_obligation_updated",
            data={"obligations": [item.to_dict() for item in obligations]},
        )
        return obligations

    async def list_obligations(
        self,
        *,
        thread_id: str,
        message_ids: list[int] | None = None,
        status: str | None = None,
    ) -> list[ReplyObligation]:
        pool, schema = await self._conn_and_schema()
        params: list[Any] = [thread_id]
        sql = f"""SELECT *
                    FROM "{schema}"."squad_reply_obligations"
                   WHERE thread_id = $1"""
        if message_ids:
            params.append(message_ids)
            message_ids_param = len(params)
            sql += (
                f" AND (source_message_id = ANY(${message_ids_param}::bigint[])"
                f" OR resolved_by_message_id = ANY(${message_ids_param}::bigint[]))"
            )
        if status:
            if status not in _VALID_OBLIGATION_STATUSES:
                raise ThreadReplyError("reply.policy_denied", "Invalid reply obligation status.")
            params.append(status)
            sql += f" AND status = ${len(params)}"
        sql += " ORDER BY created_at ASC"
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [_row_to_obligation(row) for row in rows]

    async def resolve_for_reply(
        self,
        *,
        thread_id: str,
        reply_message_id: int | str,
        from_agent: str,
        in_reply_to: int | str | None = None,
        correlation_id: str | None = None,
    ) -> list[ReplyObligation]:
        reply_id = message_ref_to_id(reply_message_id)
        if reply_id is None or not from_agent:
            return []
        parent_id = message_ref_to_id(in_reply_to)
        pool, schema = await self._conn_and_schema()
        async with pool.acquire() as conn, conn.transaction():
            rows = await conn.fetch(
                f"""UPDATE "{schema}"."squad_reply_obligations"
                       SET status = 'answered',
                           resolved_by_message_id = $1,
                           updated_at = NOW()
                     WHERE thread_id = $2
                       AND target_agent_id = $3
                       AND status = 'open'
                       AND (
                            ($4::bigint IS NOT NULL AND source_message_id = $4::bigint)
                            OR ($5::text IS NOT NULL AND obligation_key = $5::text)
                            OR ($5::text IS NOT NULL AND metadata_json->>'correlation_id' = $5::text)
                       )
                     RETURNING *""",
                reply_id,
                thread_id,
                from_agent,
                parent_id,
                str(correlation_id) if correlation_id else None,
            )
        obligations = [_row_to_obligation(row) for row in rows]
        if obligations:
            for obligation in obligations:
                _audit_reply_event("squad.reply.obligation_resolved", **obligation.to_dict())
                _metric_reply_event("obligation_resolved", obligation.status)
            await self._thread_store.notify_event(
                thread_id=thread_id,
                event_type="reply_obligation_updated",
                data={"obligations": [item.to_dict() for item in obligations]},
            )
        return obligations

    async def follow_up(
        self,
        *,
        thread_id: str,
        obligation_id: int,
        actor_id: str,
        note: str | None = None,
    ) -> ReplyObligation:
        pool, schema = await self._conn_and_schema()
        async with pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                f"""SELECT *
                      FROM "{schema}"."squad_reply_obligations"
                     WHERE id = $1 AND thread_id = $2
                     FOR UPDATE""",
                int(obligation_id),
                thread_id,
            )
            if row is None:
                raise ThreadReplyError("reply.parent_not_found", "Reply obligation was not found.")
            obligation = _row_to_obligation(row)
            if obligation.status != "open":
                raise ThreadReplyError("reply.policy_denied", "Only open reply obligations can be followed up.")
            if obligation.followup_count >= MAX_FOLLOWUPS_PER_OBLIGATION:
                raise ThreadReplyError("reply.policy_denied", "Follow-up limit reached for this obligation.")
            metadata = dict(obligation.metadata)
            metadata.setdefault("followups", [])
            if isinstance(metadata["followups"], list):
                metadata["followups"].append(
                    {"actor_id": actor_id, "note": note or "", "at": datetime.now(UTC).isoformat()}
                )
            row = await conn.fetchrow(
                f"""UPDATE "{schema}"."squad_reply_obligations"
                       SET followup_count = followup_count + 1,
                           last_followup_at = NOW(),
                           metadata_json = $3::jsonb,
                           updated_at = NOW()
                     WHERE id = $1 AND thread_id = $2
                     RETURNING *""",
                int(obligation_id),
                thread_id,
                json.dumps(metadata, default=str),
            )
        updated = _row_to_obligation(row)
        _audit_reply_event("squad.reply.followup_sent", **updated.to_dict())
        _metric_reply_event("followup_sent", updated.status)
        await self._thread_store.notify_event(
            thread_id=thread_id,
            event_type="reply_obligation_updated",
            data={"obligations": [updated.to_dict()]},
        )
        return updated

    async def cancel(
        self,
        *,
        thread_id: str,
        obligation_id: int,
        actor_id: str,
        reason: str | None = None,
    ) -> ReplyObligation:
        pool, schema = await self._conn_and_schema()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""UPDATE "{schema}"."squad_reply_obligations"
                       SET status = 'cancelled',
                           metadata_json = metadata_json || $3::jsonb,
                           updated_at = NOW()
                     WHERE id = $1 AND thread_id = $2 AND status = 'open'
                     RETURNING *""",
                int(obligation_id),
                thread_id,
                json.dumps({"cancelled_by": actor_id, "cancel_reason": reason or ""}),
            )
        if row is None:
            raise ThreadReplyError("reply.policy_denied", "Reply obligation cannot be cancelled.")
        updated = _row_to_obligation(row)
        _audit_reply_event("squad.reply.obligation_cancelled", **updated.to_dict())
        _metric_reply_event("obligation_cancelled", updated.status)
        await self._thread_store.notify_event(
            thread_id=thread_id,
            event_type="reply_obligation_updated",
            data={"obligations": [updated.to_dict()]},
        )
        return updated

    async def mark_timeouts(self, *, limit: int = 50) -> list[ReplyObligation]:
        pool, schema = await self._conn_and_schema()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""UPDATE "{schema}"."squad_reply_obligations"
                       SET status = 'timed_out',
                           updated_at = NOW()
                     WHERE id IN (
                           SELECT id
                             FROM "{schema}"."squad_reply_obligations"
                            WHERE status = 'open'
                              AND requires_response_by IS NOT NULL
                              AND requires_response_by < NOW()
                            ORDER BY requires_response_by ASC
                            LIMIT $1
                     )
                     RETURNING *""",
                max(1, min(int(limit), 500)),
            )
        obligations = [_row_to_obligation(row) for row in rows]
        by_thread: dict[str, list[ReplyObligation]] = {}
        for obligation in obligations:
            by_thread.setdefault(obligation.thread_id, []).append(obligation)
            _audit_reply_event("squad.reply.timeout", **obligation.to_dict())
            _metric_reply_event("obligation_timeout", obligation.status)
        for thread_id, items in by_thread.items():
            await self._thread_store.notify_event(
                thread_id=thread_id,
                event_type="reply_obligation_updated",
                data={"obligations": [item.to_dict() for item in items]},
            )
        return obligations


def get_thread_reply_service(thread_store: SquadThreadStore | None = None) -> ThreadReplyService | None:
    if thread_store is None:
        from koda.squads.threads import get_squad_thread_store

        thread_store = get_squad_thread_store()
    return ThreadReplyService(thread_store) if thread_store is not None else None
