"""Postgres-backed message bus for cross-process inter-agent delivery.

Persists every message to ``squad_messages`` so two Koda processes sharing a
DSN can exchange messages even though their in-process queues are isolated.
Wakes receivers via ``LISTEN squad_msg`` (low latency) and falls back to a
short poll loop so a missed NOTIFY (post-disconnect) does not stall delivery.

The durable cursor lives in ``squad_thread_participants.inbox_cursor`` and is
advanced only by ``ack()``. ``receive()`` is therefore at-least-once: a process
crash after delivery but before ack will replay the message on restart.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from contextlib import suppress
from typing import Any

from koda.agents.listen_notify import AgentInboxListener
from koda.agents.models import AgentMessage, DelegationRequest, DelegationResult
from koda.logging_config import get_logger

log = get_logger(__name__)

_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DEFAULT_CHANNEL = "squad_msg"


class PostgresMessageBus:
    def __init__(
        self,
        *,
        dsn: str,
        schema: str = "knowledge_v2",
        notify_channel: str = _DEFAULT_CHANNEL,
        max_inbox_size: int = 100,
        max_delivery_attempts: int = 5,
        lease_seconds: int = 30,
        poll_interval: float = 2.0,
        pool_min_size: int = 0,
        pool_max_size: int = 4,
        listen_enabled: bool = True,
    ) -> None:
        if not _SCHEMA_RE.match(schema):
            raise ValueError(f"invalid postgres schema name: {schema!r}")
        self._dsn = dsn
        self._schema = schema
        self._notify_channel = notify_channel
        self._max_inbox_size = max(1, int(max_inbox_size))
        self._max_delivery_attempts = max(1, int(max_delivery_attempts))
        self._lease_seconds = max(1, int(lease_seconds))
        self._poll_interval = max(0.1, float(poll_interval))
        self._pool_min_size = max(0, int(pool_min_size))
        self._pool_max_size = max(self._pool_min_size, int(pool_max_size))
        self._listen_enabled = bool(listen_enabled)
        self._pool: Any | None = None
        self._listener: AgentInboxListener | None = None
        self._inbox_events: dict[str, asyncio.Event] = {}
        self._cursors: dict[str, int] = {}
        self._delegation_results: dict[str, asyncio.Event] = {}
        self._delegation_data: dict[str, DelegationResult] = {}
        self._local_log: list[AgentMessage] = []
        self._max_local_log = 500
        self._started = False
        self._start_lock = asyncio.Lock()

    async def _ensure_started(self) -> None:
        if self._started:
            return
        async with self._start_lock:
            if self._started:
                return
            import asyncpg  # type: ignore[import-not-found]

            self._pool = await asyncpg.create_pool(
                self._dsn,
                min_size=self._pool_min_size,
                max_size=self._pool_max_size,
            )
            if self._listen_enabled:
                self._listener = AgentInboxListener(self._dsn, self._notify_channel, self._on_notify)
                await self._listener.start()
            self._started = True

    async def close(self) -> None:
        if self._listener is not None:
            await self._listener.stop()
            self._listener = None
        if self._pool is not None:
            with suppress(Exception):
                await self._pool.close()
            self._pool = None
        self._started = False

    async def _on_notify(self, payload: dict[str, Any]) -> None:
        to = payload.get("to_agent")
        if isinstance(to, str):
            event = self._inbox_events.get(to)
            if event is not None:
                event.set()

    def _ensure_event(self, agent_id: str) -> asyncio.Event:
        evt = self._inbox_events.get(agent_id)
        if evt is None:
            evt = asyncio.Event()
            self._inbox_events[agent_id] = evt
        return evt

    def _message_row_id(self, message_id: str) -> int | None:
        match = re.search(r"(\d+)$", str(message_id or ""))
        return int(match.group(1)) if match else None

    async def _cursor_for(self, agent_id: str) -> int:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            cursor = await conn.fetchval(
                f"""SELECT MAX(COALESCE(inbox_cursor, 0))
                      FROM "{self._schema}"."squad_thread_participants"
                     WHERE agent_id = $1
                       AND left_at IS NULL""",
                agent_id,
            )
        durable = int(cursor or 0)
        cached = int(self._cursors.get(agent_id, 0))
        if durable > cached:
            self._cursors[agent_id] = durable
        return max(durable, cached)

    async def _inbox_size(self, agent_id: str) -> int:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            count = await conn.fetchval(
                f"""SELECT COUNT(*)
                      FROM "{self._schema}"."squad_message_recipients"
                     WHERE to_agent_id = $1
                       AND acked_at IS NULL
                       AND delivery_status NOT IN ('acked', 'enqueued', 'dead')""",
                agent_id,
            )
        return int(count or 0)

    async def send(
        self,
        from_agent: str,
        to_agent: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        await self._ensure_started()
        if await self._inbox_size(to_agent) >= self._max_inbox_size:
            return f"Error: inbox full for agent '{to_agent}'."
        return await self._insert(from_agent, to_agent, content, "text", metadata or {})

    async def _insert(
        self,
        from_agent: str,
        to_agent: str,
        content: str,
        message_type: str,
        metadata: dict[str, Any],
    ) -> str:
        assert self._pool is not None
        metadata = dict(metadata or {})
        kind = str(metadata.get("kind") or ("agent_text" if message_type == "text" else message_type))
        payload = metadata.get("payload")
        if not isinstance(payload, dict):
            payload = {"markdown" if kind == "agent_text" else "text": content}
        thread_id = metadata.get("thread_id") or metadata.get("squad_thread_id")
        causation_id = metadata.get("causation_id") or metadata.get("parent_message_id")
        correlation_id = metadata.get("correlation_id") or metadata.get("request_id")
        in_reply_to = metadata.get("in_reply_to")
        idempotency_key = metadata.get("idempotency_key")
        message_uuid = str(metadata.get("message_uuid") or metadata.get("message_id") or uuid.uuid4())
        async with self._pool.acquire() as conn, conn.transaction():
            if idempotency_key:
                existing = await conn.fetchval(
                    f"""SELECT id
                          FROM "{self._schema}"."squad_messages"
                         WHERE idempotency_key = $1
                           AND from_agent = $2
                           AND to_agent = $3
                           AND created_at > NOW() - INTERVAL '60 seconds'
                      ORDER BY id DESC
                         LIMIT 1""",
                    str(idempotency_key),
                    from_agent,
                    to_agent,
                )
                if existing is not None:
                    return f"msg-{int(existing)}"
            row_id = await conn.fetchval(
                f"""INSERT INTO "{self._schema}"."squad_messages"
                            (message_uuid, thread_id, from_agent, to_agent, to_agent_ids,
                             content, message_type, kind, payload_json, metadata_json,
                             causation_id, correlation_id, in_reply_to, idempotency_key)
                          VALUES ($1, $2::uuid, $3, $4, $5::jsonb,
                                  $6, $7, $8, $9::jsonb, $10::jsonb,
                                  $11, $12, $13, $14)
                          RETURNING id""",
                message_uuid,
                str(thread_id) if thread_id else None,
                from_agent,
                to_agent,
                json.dumps([to_agent]),
                str(content or ""),
                message_type,
                kind,
                json.dumps(payload),
                json.dumps(metadata),
                str(causation_id) if causation_id else None,
                str(correlation_id) if correlation_id else None,
                str(in_reply_to) if in_reply_to else None,
                str(idempotency_key) if idempotency_key else None,
            )
            await conn.execute(
                f"""INSERT INTO "{self._schema}"."squad_message_recipients" (message_id, to_agent_id)
                      VALUES ($1, $2)
                      ON CONFLICT DO NOTHING""",
                int(row_id),
                to_agent,
            )
            notify_payload = json.dumps({"to_agent": to_agent, "msg_id": int(row_id)})
            await conn.execute("SELECT pg_notify($1, $2)", self._notify_channel, notify_payload)
        msg_id = f"msg-{int(row_id)}"
        self._record_local(
            AgentMessage(
                from_agent=from_agent,
                to_agent=to_agent,
                content=content,
                message_type=message_type,
                metadata=metadata,
                message_id=msg_id,
                thread_id=str(thread_id) if thread_id else None,
                to_agent_ids=[to_agent],
                kind=kind,
                payload=payload if isinstance(payload, dict) else {},
                causation_id=str(causation_id) if causation_id else None,
                correlation_id=str(correlation_id) if correlation_id else None,
                in_reply_to=str(in_reply_to) if in_reply_to else None,
                idempotency_key=str(idempotency_key) if idempotency_key else None,
            )
        )
        return msg_id

    def _record_local(self, msg: AgentMessage) -> None:
        self._local_log.append(msg)
        if len(self._local_log) > self._max_local_log:
            self._local_log = self._local_log[-self._max_local_log :]

    async def receive(self, agent_id: str, timeout: float = 30.0) -> AgentMessage | None:
        messages = await self.receive_batch(agent_id, limit=1, timeout=timeout)
        return messages[0] if messages else None

    async def receive_batch(
        self,
        agent_id: str,
        *,
        limit: int = 50,
        timeout: float = 30.0,
    ) -> list[AgentMessage]:
        await self._ensure_started()
        deadline = time.monotonic() + min(timeout, 300)
        evt = self._ensure_event(agent_id)
        evt.clear()
        messages = await self._fetch_batch(agent_id, limit=limit)
        if messages:
            return messages
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return []
            with suppress(TimeoutError):
                await asyncio.wait_for(evt.wait(), timeout=min(remaining, self._poll_interval))
            evt.clear()
            messages = await self._fetch_batch(agent_id, limit=limit)
            if messages:
                return messages

    async def _fetch_next(self, agent_id: str) -> AgentMessage | None:
        batch = await self._fetch_batch(agent_id, limit=1)
        return batch[0] if batch else None

    async def _fetch_batch(self, agent_id: str, *, limit: int = 50) -> list[AgentMessage]:
        assert self._pool is not None
        bounded_limit = max(1, min(int(limit), 50))
        async with self._pool.acquire() as conn, conn.transaction():
            leased = await conn.fetch(
                f"""WITH next AS (
                        SELECT r.message_id, r.to_agent_id
                          FROM "{self._schema}"."squad_message_recipients" AS r
                         WHERE r.to_agent_id = $1
                           AND r.acked_at IS NULL
                           AND r.delivery_status IN ('pending', 'leased')
                           AND (
                               r.lease_expires_at IS NULL
                               OR r.lease_expires_at <= NOW()
                           )
                         ORDER BY r.message_id ASC
                         LIMIT $2
                         FOR UPDATE SKIP LOCKED
                    )
                    UPDATE "{self._schema}"."squad_message_recipients" AS r
                       SET delivery_status = 'leased',
                           delivery_attempts = r.delivery_attempts + 1,
                           lease_expires_at = NOW() + ($3 || ' seconds')::interval,
                           delivered_at = COALESCE(r.delivered_at, NOW()),
                           last_error = NULL
                      FROM next
                     WHERE r.message_id = next.message_id
                       AND r.to_agent_id = next.to_agent_id
                 RETURNING r.message_id""",
                agent_id,
                bounded_limit,
                str(self._lease_seconds),
            )
            ids = [int(row["message_id"]) for row in leased]
            if not ids:
                return []
            rows = await conn.fetch(
                f"""SELECT m.id, m.thread_id, m.from_agent, m.to_agent, m.to_agent_ids,
                            m.content, m.message_type, m.kind, m.payload_json,
                            m.metadata_json, m.causation_id, m.correlation_id, m.in_reply_to,
                            m.idempotency_key, m.created_at
                       FROM "{self._schema}"."squad_messages" AS m
                      WHERE m.id = ANY($1::bigint[])
                   ORDER BY m.id ASC""",
                ids,
            )
        messages = [self._row_to_message(row) for row in rows]
        for msg in messages:
            self._record_local(msg)
        return messages

    def _row_to_message(self, row: Any) -> AgentMessage:
        metadata = row["metadata_json"]
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, ValueError):
                metadata = {}
        payload = row["payload_json"]
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (json.JSONDecodeError, ValueError):
                payload = {}
        to_agent_ids = row["to_agent_ids"]
        if isinstance(to_agent_ids, str):
            try:
                to_agent_ids = json.loads(to_agent_ids)
            except (json.JSONDecodeError, ValueError):
                to_agent_ids = []
        if not isinstance(to_agent_ids, list):
            to_agent_ids = []
        to_agent = row["to_agent"] or (str(to_agent_ids[0]) if to_agent_ids else "")
        created = row["created_at"]
        timestamp = created.timestamp() if created is not None else time.time()
        return AgentMessage(
            from_agent=row["from_agent"],
            to_agent=to_agent,
            content=row["content"],
            message_type=row["message_type"],
            metadata=metadata or {},
            timestamp=timestamp,
            message_id=f"msg-{int(row['id'])}",
            thread_id=str(row["thread_id"]) if row["thread_id"] else None,
            to_agent_ids=[str(value) for value in to_agent_ids] if to_agent_ids else ([to_agent] if to_agent else []),
            kind=str(row["kind"] or row["message_type"] or "agent_text"),
            payload=payload or {},
            causation_id=str(row["causation_id"]) if row["causation_id"] else None,
            correlation_id=str(row["correlation_id"]) if row["correlation_id"] else None,
            in_reply_to=str(row["in_reply_to"]) if row["in_reply_to"] else None,
            idempotency_key=str(row["idempotency_key"]) if row["idempotency_key"] else None,
        )

    async def ack(self, agent_id: str, message_id: str, *, enqueued_task_id: int | None = None) -> None:
        await self._ensure_started()
        row_id = self._message_row_id(message_id)
        if row_id is None:
            return
        self._cursors[agent_id] = max(int(row_id), self._cursors.get(agent_id, 0))
        assert self._pool is not None
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                f"""UPDATE "{self._schema}"."squad_thread_participants"
                           SET inbox_cursor = GREATEST(COALESCE(inbox_cursor, 0), $1)
                         WHERE agent_id = $2
                           AND left_at IS NULL""",
                int(row_id),
                agent_id,
            )
            await conn.execute(
                f"""UPDATE "{self._schema}"."squad_message_recipients"
                           SET acked_at = NOW(),
                               delivery_status = CASE
                                   WHEN $3::bigint IS NULL THEN 'acked'
                                   ELSE 'enqueued'
                               END,
                               enqueued_task_id = COALESCE($3::bigint, enqueued_task_id),
                               lease_expires_at = NULL
                         WHERE message_id = $1
                           AND to_agent_id = $2""",
                int(row_id),
                agent_id,
                int(enqueued_task_id) if enqueued_task_id is not None else None,
            )

    async def nack(
        self,
        agent_id: str,
        message_id: str,
        *,
        error: str,
        retry_after: float | None = None,
    ) -> None:
        await self._ensure_started()
        row_id = self._message_row_id(message_id)
        if row_id is None:
            return
        delay = max(0.0, float(retry_after or 0.0))
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            await conn.execute(
                f"""UPDATE "{self._schema}"."squad_message_recipients"
                       SET delivery_status = CASE
                               WHEN delivery_attempts >= $4 THEN 'dead'
                               ELSE 'pending'
                           END,
                           lease_expires_at = CASE
                               WHEN delivery_attempts >= $4 THEN NULL
                               ELSE NOW() + ($5 || ' seconds')::interval
                           END,
                           last_error = $3
                     WHERE message_id = $1
                       AND to_agent_id = $2
                       AND delivery_status = 'leased'""",
                int(row_id),
                agent_id,
                str(error or "")[:1000],
                self._max_delivery_attempts,
                str(delay),
            )

    async def delegate(self, request: DelegationRequest) -> DelegationResult:
        from koda.config import INTER_AGENT_MAX_DELEGATION_DEPTH

        if request.delegation_depth >= INTER_AGENT_MAX_DELEGATION_DEPTH:
            return DelegationResult(
                request_id=request.request_id,
                from_agent=request.from_agent,
                to_agent=request.to_agent,
                success=False,
                error=f"Max delegation depth ({INTER_AGENT_MAX_DELEGATION_DEPTH}) exceeded.",
            )
        await self._ensure_started()
        if not request.request_id:
            request.request_id = f"req-{uuid.uuid4().hex}"
        if await self._inbox_size(request.to_agent) >= self._max_inbox_size:
            return DelegationResult(
                request_id=request.request_id,
                from_agent=request.from_agent,
                to_agent=request.to_agent,
                success=False,
                error=f"Agent '{request.to_agent}' inbox full.",
            )
        event = asyncio.Event()
        self._delegation_results[request.request_id] = event
        await self._insert(
            request.from_agent,
            request.to_agent,
            request.task,
            "delegation_request",
            {
                "request_id": request.request_id,
                "context": request.context,
                "delegation_depth": request.delegation_depth,
                "thread_id": request.thread_id,
                "squad_task_id": request.squad_task_id,
                "parent_message_id": request.parent_message_id,
                "correlation_id": request.correlation_id or request.request_id,
                "idempotency_key": request.idempotency_key,
                "kind": "task_request",
                "payload": {
                    "task_id": request.squad_task_id,
                    "description": request.task,
                    "acceptance_criteria": request.context.get("acceptance_criteria", []),
                    "context_refs": request.context.get("context_refs", []),
                },
            },
        )
        try:
            deadline = time.monotonic() + min(request.timeout, 300)
            while True:
                result = self._delegation_data.pop(request.request_id, None)
                if result is not None:
                    return result
                result = await self._fetch_delegation_result(request)
                if result is not None:
                    return result
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError
                with suppress(TimeoutError):
                    await asyncio.wait_for(event.wait(), timeout=min(remaining, self._poll_interval, 1.0))
                    event.clear()
            return DelegationResult(
                request_id=request.request_id,
                from_agent=request.from_agent,
                to_agent=request.to_agent,
                success=False,
                error="No result received.",
            )
        except TimeoutError:
            return DelegationResult(
                request_id=request.request_id,
                from_agent=request.from_agent,
                to_agent=request.to_agent,
                success=False,
                error=f"Delegation timeout ({request.timeout}s).",
            )
        finally:
            self._delegation_results.pop(request.request_id, None)

    def resolve_delegation(self, request_id: str, result: DelegationResult) -> None:
        self._delegation_data[request_id] = result
        event = self._delegation_results.get(request_id)
        if event is not None:
            event.set()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._persist_delegation_result(request_id, result))

    async def _persist_delegation_result(self, request_id: str, result: DelegationResult) -> None:
        await self._ensure_started()
        await self._insert(
            result.from_agent,
            result.to_agent,
            result.result if result.success else (result.error or ""),
            "delegation_result",
            {
                "request_id": request_id,
                "success": result.success,
                "error": result.error,
                "duration_ms": result.duration_ms,
                "metadata": result.metadata,
                "correlation_id": request_id,
                "kind": "task_result",
                "payload": {
                    "task_id": result.metadata.get("task_id"),
                    "status": "ok" if result.success else "failed",
                    "output_md": result.result,
                    "artifact_ids": result.metadata.get("artifact_ids", []),
                    "cost_usd": result.metadata.get("cost_usd", 0),
                    "evidence": result.metadata.get("evidence"),
                },
            },
        )

    async def _fetch_delegation_result(self, request: DelegationRequest) -> DelegationResult | None:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""SELECT id, from_agent, to_agent, content, message_type,
                            kind, payload_json, metadata_json, created_at
                      FROM "{self._schema}"."squad_messages"
                     WHERE to_agent = $1
                       AND (
                            correlation_id = $2
                            OR metadata_json->>'request_id' = $2
                       )
                       AND (
                            message_type = 'delegation_result'
                            OR kind IN ('task_result', 'delegation_result')
                       )
                  ORDER BY id ASC
                     LIMIT 1""",
                request.from_agent,
                request.request_id,
            )
        if row is None:
            return None
        metadata = row["metadata_json"]
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, ValueError):
                metadata = {}
        metadata = dict(metadata or {})
        payload = row["payload_json"]
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (json.JSONDecodeError, ValueError):
                payload = {}
        payload = dict(payload or {})
        status = str(payload.get("status") or "").lower()
        success = bool(metadata.get("success", status not in {"failed", "error"} and row["content"] != ""))
        output = str(payload.get("output_md") or row["content"] or "")
        error = metadata.get("error") or (output if not success else None)
        result_metadata = dict(metadata.get("metadata") or {})
        if payload.get("artifact_ids") is not None:
            result_metadata.setdefault("artifact_ids", payload.get("artifact_ids"))
        if payload.get("cost_usd") is not None:
            result_metadata.setdefault("cost_usd", payload.get("cost_usd"))
        result = DelegationResult(
            request_id=request.request_id,
            from_agent=request.from_agent,
            to_agent=request.to_agent,
            success=success,
            result=output,
            error=str(error) if error else None,
            duration_ms=float(metadata["duration_ms"]) if metadata.get("duration_ms") is not None else None,
            metadata=result_metadata,
        )
        await self.ack(request.from_agent, f"msg-{int(row['id'])}")
        return result

    async def broadcast(
        self,
        from_agent: str,
        content: str,
        exclude: set[str] | None = None,
    ) -> int:
        await self._ensure_started()
        skip = set(exclude or set())
        skip.add(from_agent)
        agents = await self._list_known_agents()
        count = 0
        for agent_id in agents:
            if agent_id in skip:
                continue
            try:
                if await self._inbox_size(agent_id) >= self._max_inbox_size:
                    continue
                await self._insert(from_agent, agent_id, content, "text", {})
                count += 1
            except Exception:
                log.exception("postgres_bus_broadcast_send_failed", to=agent_id)
        return count

    async def _list_known_agents(self) -> list[str]:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"""SELECT DISTINCT agent FROM (
                       SELECT from_agent AS agent FROM "{self._schema}"."squad_messages"
                       UNION
                       SELECT to_agent  AS agent FROM "{self._schema}"."squad_messages"
                    ) AS s
                    ORDER BY agent"""
            )
        return [row["agent"] for row in rows]

    def list_agents(self) -> list[dict[str, Any]]:
        # Best-effort in-process snapshot. Cross-process state lives in DB and
        # is exposed via ``async list_known_agents`` for callers that need it.
        return [
            {"agent_id": aid, "inbox_size": -1, "inbox_max": self._max_inbox_size} for aid in sorted(self._inbox_events)
        ]

    def get_message_log(
        self,
        limit: int = 50,
        agent_id: str | None = None,
    ) -> list[dict[str, Any]]:
        # Best-effort in-process tail. The canonical log is `squad_messages`.
        msgs = self._local_log
        if agent_id:
            msgs = [m for m in msgs if m.from_agent == agent_id or m.to_agent == agent_id]
        return [
            {
                "from": m.from_agent,
                "to": m.to_agent,
                "content": m.content[:200],
                "type": m.message_type,
                "timestamp": m.timestamp,
                "id": m.message_id,
            }
            for m in msgs[-limit:]
        ]
