"""Postgres-backed message bus for cross-process inter-agent delivery.

Persists every message to ``squad_messages`` so two Koda processes sharing a
DSN can exchange messages even though their in-process queues are isolated.
Wakes receivers via ``LISTEN squad_msg`` (low latency) and falls back to a
short poll loop so a missed NOTIFY (post-disconnect) does not stall delivery.

``delegate()`` matches the in-process semantics of ``InMemoryMessageBus``:
it relies on ``resolve_delegation`` being called in the same process. Auto-
resolution from a cross-process ``delegation_result`` message is deferred to
the squad-orchestration milestone (Phase 2).
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
        poll_interval: float = 2.0,
        pool_min_size: int = 1,
        pool_max_size: int = 4,
    ) -> None:
        if not _SCHEMA_RE.match(schema):
            raise ValueError(f"invalid postgres schema name: {schema!r}")
        self._dsn = dsn
        self._schema = schema
        self._notify_channel = notify_channel
        self._max_inbox_size = max(1, int(max_inbox_size))
        self._poll_interval = max(0.1, float(poll_interval))
        self._pool_min_size = max(1, int(pool_min_size))
        self._pool_max_size = max(self._pool_min_size, int(pool_max_size))
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

    async def _inbox_size(self, agent_id: str) -> int:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            count = await conn.fetchval(
                f'SELECT COUNT(*) FROM "{self._schema}"."squad_messages" WHERE to_agent = $1 AND id > $2',
                agent_id,
                self._cursors.get(agent_id, 0),
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
        async with self._pool.acquire() as conn, conn.transaction():
            row_id = await conn.fetchval(
                f"""INSERT INTO "{self._schema}"."squad_messages"
                            (from_agent, to_agent, content, message_type, metadata_json)
                          VALUES ($1, $2, $3, $4, $5::jsonb)
                          RETURNING id""",
                from_agent,
                to_agent,
                content,
                message_type,
                json.dumps(metadata),
            )
            payload = json.dumps({"to_agent": to_agent, "msg_id": int(row_id)})
            await conn.execute("SELECT pg_notify($1, $2)", self._notify_channel, payload)
        msg_id = f"msg-{int(row_id)}"
        self._record_local(
            AgentMessage(
                from_agent=from_agent,
                to_agent=to_agent,
                content=content,
                message_type=message_type,
                metadata=metadata,
                message_id=msg_id,
            )
        )
        return msg_id

    def _record_local(self, msg: AgentMessage) -> None:
        self._local_log.append(msg)
        if len(self._local_log) > self._max_local_log:
            self._local_log = self._local_log[-self._max_local_log :]

    async def receive(self, agent_id: str, timeout: float = 30.0) -> AgentMessage | None:
        await self._ensure_started()
        deadline = time.monotonic() + min(timeout, 300)
        evt = self._ensure_event(agent_id)
        evt.clear()
        msg = await self._fetch_next(agent_id)
        if msg is not None:
            return msg
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            with suppress(TimeoutError):
                await asyncio.wait_for(evt.wait(), timeout=min(remaining, self._poll_interval))
            evt.clear()
            msg = await self._fetch_next(agent_id)
            if msg is not None:
                return msg

    async def _fetch_next(self, agent_id: str) -> AgentMessage | None:
        assert self._pool is not None
        cursor = self._cursors.get(agent_id, 0)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""SELECT id, from_agent, to_agent, content, message_type,
                            metadata_json, created_at
                       FROM "{self._schema}"."squad_messages"
                      WHERE to_agent = $1 AND id > $2
                      ORDER BY id ASC
                      LIMIT 1""",
                agent_id,
                cursor,
            )
        if row is None:
            return None
        self._cursors[agent_id] = int(row["id"])
        metadata = row["metadata_json"]
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, ValueError):
                metadata = {}
        created = row["created_at"]
        timestamp = created.timestamp() if created is not None else time.time()
        msg = AgentMessage(
            from_agent=row["from_agent"],
            to_agent=row["to_agent"],
            content=row["content"],
            message_type=row["message_type"],
            metadata=metadata or {},
            timestamp=timestamp,
            message_id=f"msg-{int(row['id'])}",
        )
        self._record_local(msg)
        return msg

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
            },
        )
        try:
            await asyncio.wait_for(event.wait(), timeout=min(request.timeout, 300))
            result = self._delegation_data.pop(request.request_id, None)
            if result is not None:
                return result
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
