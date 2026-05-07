"""Squad thread store.

Persists squad conversations as ``squad_threads`` rows, manages their
``squad_thread_participants`` membership, and renders thread posts on top of
the existing ``squad_messages`` table (``thread_id`` set, ``to_agent`` null).
This module is the read/write layer for thread state — orchestration and
prompt assembly live elsewhere.
"""

from __future__ import annotations

import json
import re
import uuid
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from koda.logging_config import get_logger

log = get_logger(__name__)

_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_VALID_STATUSES = {"open", "paused", "completed", "archived"}
_VALID_VISIBILITIES = {"squad", "private"}
_VALID_ROLES = {"coordinator", "worker", "observer"}
_ALLOWED_TRANSITIONS = {
    "open": {"paused", "completed"},
    "paused": {"open", "completed"},
    "completed": {"archived"},
    "archived": set(),
}


@dataclass
class ThreadDescriptor:
    id: str
    workspace_id: str
    squad_id: str
    owner_user_id: int | None
    title: str
    status: str
    coordinator_agent_id: str | None
    current_owner_agent_id: str | None
    parent_thread_id: str | None
    visibility: str
    telegram_chat_id: int | None
    telegram_message_thread_id: int | None
    budget_usd_cap: Decimal | None
    cost_usd_accum: Decimal
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    archived_at: datetime | None = None


@dataclass
class ParticipantInfo:
    thread_id: str
    agent_id: str
    role: str
    joined_at: datetime | None
    left_at: datetime | None
    last_read_message_id: int | None
    inbox_cursor: int | None
    paused: bool


def _row_to_thread(row: Any) -> ThreadDescriptor:
    metadata = row["metadata_json"]
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except (json.JSONDecodeError, ValueError):
            metadata = {}
    return ThreadDescriptor(
        id=str(row["id"]),
        workspace_id=row["workspace_id"],
        squad_id=row["squad_id"],
        owner_user_id=row["owner_user_id"],
        title=row["title"] or "",
        status=row["status"],
        coordinator_agent_id=row["coordinator_agent_id"],
        current_owner_agent_id=row["current_owner_agent_id"],
        parent_thread_id=str(row["parent_thread_id"]) if row["parent_thread_id"] is not None else None,
        visibility=row["visibility"],
        telegram_chat_id=row["telegram_chat_id"],
        telegram_message_thread_id=row["telegram_message_thread_id"],
        budget_usd_cap=row["budget_usd_cap"],
        cost_usd_accum=row["cost_usd_accum"] or Decimal(0),
        metadata=metadata or {},
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        completed_at=row["completed_at"],
        archived_at=row["archived_at"],
    )


def _row_to_participant(row: Any) -> ParticipantInfo:
    return ParticipantInfo(
        thread_id=str(row["thread_id"]),
        agent_id=row["agent_id"],
        role=row["role"],
        joined_at=row["joined_at"],
        left_at=row["left_at"],
        last_read_message_id=row["last_read_message_id"],
        inbox_cursor=row["inbox_cursor"],
        paused=bool(row["paused"]),
    )


class SquadThreadStore:
    def __init__(
        self,
        *,
        dsn: str,
        schema: str = "knowledge_v2",
        pool_min_size: int = 1,
        pool_max_size: int = 4,
    ) -> None:
        if not _SCHEMA_RE.match(schema):
            raise ValueError(f"invalid postgres schema name: {schema!r}")
        self._dsn = dsn
        self._schema = schema
        self._pool_min_size = max(1, int(pool_min_size))
        self._pool_max_size = max(self._pool_min_size, int(pool_max_size))
        self._pool: Any | None = None

    async def _ensure_pool(self) -> Any:
        if self._pool is None:
            import asyncpg  # type: ignore[import-not-found]

            self._pool = await asyncpg.create_pool(
                self._dsn,
                min_size=self._pool_min_size,
                max_size=self._pool_max_size,
            )
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            with suppress(Exception):
                await self._pool.close()
            self._pool = None

    async def create_thread(
        self,
        *,
        workspace_id: str,
        squad_id: str,
        title: str,
        owner_user_id: int | None = None,
        coordinator_agent_id: str | None = None,
        parent_thread_id: str | None = None,
        visibility: str = "squad",
        telegram_chat_id: int | None = None,
        telegram_message_thread_id: int | None = None,
        budget_usd_cap: Decimal | None = None,
        metadata: dict[str, Any] | None = None,
        participants: list[tuple[str, str]] | None = None,
    ) -> ThreadDescriptor:
        if not workspace_id or not squad_id:
            raise ValueError("workspace_id and squad_id are required")
        if visibility not in _VALID_VISIBILITIES:
            raise ValueError(f"visibility must be one of {sorted(_VALID_VISIBILITIES)}")
        for _, role in participants or []:
            if role not in _VALID_ROLES:
                raise ValueError(f"participant role must be one of {sorted(_VALID_ROLES)}")
        thread_id = str(uuid.uuid4())
        pool = await self._ensure_pool()
        async with pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                f"""INSERT INTO "{self._schema}"."squad_threads"
                        (id, workspace_id, squad_id, owner_user_id, title, status,
                         coordinator_agent_id, parent_thread_id, visibility,
                         telegram_chat_id, telegram_message_thread_id,
                         budget_usd_cap, metadata_json)
                      VALUES ($1, $2, $3, $4, $5, 'open', $6, $7, $8, $9, $10, $11, $12::jsonb)
                      RETURNING *""",
                thread_id,
                workspace_id,
                squad_id,
                owner_user_id,
                title or "",
                coordinator_agent_id,
                parent_thread_id,
                visibility,
                telegram_chat_id,
                telegram_message_thread_id,
                budget_usd_cap,
                json.dumps(metadata or {}),
            )
            for agent_id, role in participants or []:
                await conn.execute(
                    f"""INSERT INTO "{self._schema}"."squad_thread_participants"
                            (thread_id, agent_id, role)
                          VALUES ($1, $2, $3)
                          ON CONFLICT (thread_id, agent_id) DO UPDATE SET
                              role = EXCLUDED.role,
                              left_at = NULL""",
                    thread_id,
                    agent_id,
                    role,
                )
            if coordinator_agent_id:
                await conn.execute(
                    f"""INSERT INTO "{self._schema}"."squad_thread_participants"
                            (thread_id, agent_id, role)
                          VALUES ($1, $2, 'coordinator')
                          ON CONFLICT (thread_id, agent_id) DO UPDATE SET
                              role = 'coordinator',
                              left_at = NULL""",
                    thread_id,
                    coordinator_agent_id,
                )
        return _row_to_thread(row)

    async def get_thread(self, thread_id: str) -> ThreadDescriptor | None:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f'SELECT * FROM "{self._schema}"."squad_threads" WHERE id = $1',
                thread_id,
            )
        return _row_to_thread(row) if row is not None else None

    async def list_threads(
        self,
        *,
        workspace_id: str | None = None,
        squad_id: str | None = None,
        status: str | None = None,
        owner_user_id: int | None = None,
        limit: int = 50,
    ) -> list[ThreadDescriptor]:
        clauses: list[str] = []
        params: list[Any] = []
        if workspace_id:
            params.append(workspace_id)
            clauses.append(f"workspace_id = ${len(params)}")
        if squad_id:
            params.append(squad_id)
            clauses.append(f"squad_id = ${len(params)}")
        if status:
            params.append(status)
            clauses.append(f"status = ${len(params)}")
        if owner_user_id is not None:
            params.append(owner_user_id)
            clauses.append(f"owner_user_id = ${len(params)}")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(int(limit), 500)))
        sql = f'SELECT * FROM "{self._schema}"."squad_threads" {where} ORDER BY updated_at DESC LIMIT ${len(params)}'
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [_row_to_thread(r) for r in rows]

    async def update_thread_status(self, thread_id: str, new_status: str) -> ThreadDescriptor:
        if new_status not in _VALID_STATUSES:
            raise ValueError(f"status must be one of {sorted(_VALID_STATUSES)}")
        pool = await self._ensure_pool()
        async with pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                f'SELECT status FROM "{self._schema}"."squad_threads" WHERE id = $1 FOR UPDATE',
                thread_id,
            )
            if row is None:
                raise KeyError(f"thread {thread_id!r} not found")
            current = row["status"]
            if new_status == current:
                row = await conn.fetchrow(
                    f'SELECT * FROM "{self._schema}"."squad_threads" WHERE id = $1',
                    thread_id,
                )
                return _row_to_thread(row)
            if new_status not in _ALLOWED_TRANSITIONS.get(current, set()):
                raise ValueError(f"illegal transition {current!r} -> {new_status!r}")
            extras = ""
            if new_status == "completed":
                extras = ", completed_at = NOW()"
            elif new_status == "archived":
                extras = ", archived_at = NOW()"
            row = await conn.fetchrow(
                f"""UPDATE "{self._schema}"."squad_threads"
                       SET status = $2, updated_at = NOW(){extras}
                     WHERE id = $1
                     RETURNING *""",
                thread_id,
                new_status,
            )
        return _row_to_thread(row)

    async def add_participant(
        self,
        *,
        thread_id: str,
        agent_id: str,
        role: str = "worker",
    ) -> ParticipantInfo:
        if role not in _VALID_ROLES:
            raise ValueError(f"role must be one of {sorted(_VALID_ROLES)}")
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""INSERT INTO "{self._schema}"."squad_thread_participants"
                        (thread_id, agent_id, role)
                      VALUES ($1, $2, $3)
                      ON CONFLICT (thread_id, agent_id) DO UPDATE SET
                          role = EXCLUDED.role,
                          left_at = NULL,
                          paused = FALSE
                      RETURNING *""",
                thread_id,
                agent_id,
                role,
            )
        return _row_to_participant(row)

    async def remove_participant(self, *, thread_id: str, agent_id: str) -> bool:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                f"""UPDATE "{self._schema}"."squad_thread_participants"
                       SET left_at = NOW()
                     WHERE thread_id = $1 AND agent_id = $2 AND left_at IS NULL""",
                thread_id,
                agent_id,
            )
        return isinstance(result, str) and result.endswith(" 1")

    async def list_participants(
        self,
        *,
        thread_id: str,
        active_only: bool = True,
    ) -> list[ParticipantInfo]:
        pool = await self._ensure_pool()
        sql = f'SELECT * FROM "{self._schema}"."squad_thread_participants" WHERE thread_id = $1'
        if active_only:
            sql += " AND left_at IS NULL"
        sql += " ORDER BY joined_at ASC"
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, thread_id)
        return [_row_to_participant(r) for r in rows]

    async def post_thread_message(
        self,
        *,
        thread_id: str,
        from_agent: str,
        content: str,
        message_type: str = "agent_text",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn, conn.transaction():
            exists = await conn.fetchval(
                f'SELECT 1 FROM "{self._schema}"."squad_threads" WHERE id = $1',
                thread_id,
            )
            if not exists:
                raise KeyError(f"thread {thread_id!r} not found")
            row_id = await conn.fetchval(
                f"""INSERT INTO "{self._schema}"."squad_messages"
                        (thread_id, from_agent, to_agent, content, message_type, metadata_json)
                      VALUES ($1, $2, NULL, $3, $4, $5::jsonb)
                      RETURNING id""",
                thread_id,
                from_agent,
                content,
                message_type,
                json.dumps(metadata or {}),
            )
            await conn.execute(
                f"""UPDATE "{self._schema}"."squad_threads"
                       SET updated_at = NOW(), current_owner_agent_id = $2
                     WHERE id = $1""",
                thread_id,
                from_agent,
            )
        return int(row_id)

    async def find_by_telegram_topic(
        self,
        *,
        telegram_chat_id: int,
        telegram_message_thread_id: int | None,
    ) -> ThreadDescriptor | None:
        pool = await self._ensure_pool()
        if telegram_message_thread_id is None:
            sql = (
                f'SELECT * FROM "{self._schema}"."squad_threads" '
                "WHERE telegram_chat_id = $1 AND telegram_message_thread_id IS NULL "
                "ORDER BY updated_at DESC LIMIT 1"
            )
            args: tuple[Any, ...] = (int(telegram_chat_id),)
        else:
            sql = (
                f'SELECT * FROM "{self._schema}"."squad_threads" '
                "WHERE telegram_chat_id = $1 AND telegram_message_thread_id = $2"
            )
            args = (int(telegram_chat_id), int(telegram_message_thread_id))
        async with pool.acquire() as conn:
            row = await conn.fetchrow(sql, *args)
        return _row_to_thread(row) if row is not None else None

    async def notify_event(
        self,
        *,
        thread_id: str,
        event_type: str,
        data: dict[str, Any] | None = None,
        channel: str = "squad_thread_events",
    ) -> None:
        """Emit a ``pg_notify`` so SSE subscribers can push state to clients.

        Payload format: ``{"thread_id": str, "event_type": str, "data": dict}``.
        Fire-and-forget — failures are logged but never raised so a downstream
        notification glitch can't fail an otherwise-successful mutation.
        """
        payload = json.dumps(
            {"thread_id": thread_id, "event_type": event_type, "data": data or {}},
            default=str,
        )
        try:
            pool = await self._ensure_pool()
            async with pool.acquire() as conn:
                await conn.execute("SELECT pg_notify($1, $2)", channel, payload)
        except Exception:
            log.exception("squad_thread_notify_failed", thread_id=thread_id, event_type=event_type)

    async def thread_history(
        self,
        *,
        thread_id: str,
        limit: int = 50,
        before_id: int | None = None,
    ) -> list[dict[str, Any]]:
        params: list[Any] = [thread_id]
        sql = f"""SELECT id, from_agent, to_agent, content, message_type,
                       metadata_json, created_at
                  FROM "{self._schema}"."squad_messages"
                 WHERE thread_id = $1"""
        if before_id is not None:
            params.append(int(before_id))
            sql += f" AND id < ${len(params)}"
        params.append(max(1, min(int(limit), 500)))
        sql += f" ORDER BY id DESC LIMIT ${len(params)}"
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        out: list[dict[str, Any]] = []
        for row in rows:
            metadata = row["metadata_json"]
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except (json.JSONDecodeError, ValueError):
                    metadata = {}
            out.append(
                {
                    "id": int(row["id"]),
                    "from": row["from_agent"],
                    "to": row["to_agent"],
                    "content": row["content"],
                    "type": row["message_type"],
                    "metadata": metadata or {},
                    "created_at": row["created_at"],
                }
            )
        return out


async def list_squad_threads_default(
    *,
    squad_id: str,
    workspace_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[ThreadDescriptor] | None:
    """Convenience wrapper using the configured Postgres DSN. Returns ``None``
    when no DSN is set so callers can degrade to an empty list."""
    store = get_squad_thread_store()
    if store is None:
        return None
    return await store.list_threads(
        workspace_id=workspace_id,
        squad_id=squad_id,
        status=status,
        limit=limit,
    )


_store: SquadThreadStore | None = None


def _build_store() -> SquadThreadStore | None:
    from koda.config import POSTGRES_URL
    from koda.knowledge.config import KNOWLEDGE_V2_POSTGRES_SCHEMA

    if not POSTGRES_URL:
        return None
    schema = (KNOWLEDGE_V2_POSTGRES_SCHEMA or "knowledge_v2").strip() or "knowledge_v2"
    return SquadThreadStore(dsn=POSTGRES_URL, schema=schema)


def get_squad_thread_store() -> SquadThreadStore | None:
    """Return the singleton thread store, or None if no Postgres DSN is configured."""
    global _store  # noqa: PLW0603
    if _store is None:
        _store = _build_store()
    return _store
