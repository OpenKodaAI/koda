"""Read-only aggregate projections for squad dashboards.

Joins ``squad_threads`` / ``squad_tasks`` / ``squad_coordinator_state`` into
shape that operators (and the Web UI) can consume in a single round-trip.
Each function is pure-read — never mutates DB state — so callers can run them
on hot paths without locking concerns.
"""

from __future__ import annotations

import json
import re
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from koda.logging_config import get_logger
from koda.squads.tasks import TaskDescriptor, _row_to_task
from koda.squads.threads import ParticipantInfo, ThreadDescriptor, _row_to_participant, _row_to_thread

log = get_logger(__name__)

_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass
class SquadOverview:
    squad_id: str
    workspace_id: str | None
    coordinator_agent_id: str | None
    thread_counts: dict[str, int]
    task_counts: dict[str, int]
    member_count: int
    last_active_at: datetime | None
    total_cost_usd: Decimal


@dataclass
class ThreadOverview:
    thread: ThreadDescriptor
    participants: list[ParticipantInfo]
    recent_messages: list[dict[str, Any]]
    active_tasks: list[TaskDescriptor]
    coordinator_agent_id: str | None
    open_task_count: int = 0
    done_task_count: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


def _decode_jsonb(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return None
    return value


async def _ensure_pool(dsn: str, schema: str) -> Any:
    if not _SCHEMA_RE.match(schema):
        raise ValueError(f"invalid postgres schema name: {schema!r}")
    import asyncpg  # type: ignore[import-not-found]

    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
    return pool


async def list_squad_overviews(
    *,
    dsn: str,
    schema: str = "knowledge_v2",
    workspace_id: str | None = None,
) -> list[SquadOverview]:
    """Return one ``SquadOverview`` per squad with at least one thread.

    When ``workspace_id`` is provided, only squads with threads in that
    workspace are returned. Squads with no threads (configured but unused)
    are omitted on purpose: the dashboard surfaces *active* squads.
    """
    if not _SCHEMA_RE.match(schema):
        raise ValueError(f"invalid postgres schema name: {schema!r}")
    pool = await _ensure_pool(dsn, schema)
    try:
        async with pool.acquire() as conn:
            sql = f"""
                WITH thread_agg AS (
                    SELECT
                        squad_id,
                        MIN(workspace_id) AS workspace_id,
                        COUNT(*) FILTER (WHERE status = 'open') AS open_threads,
                        COUNT(*) FILTER (WHERE status = 'paused') AS paused_threads,
                        COUNT(*) FILTER (WHERE status = 'completed') AS completed_threads,
                        COUNT(*) FILTER (WHERE status = 'archived') AS archived_threads,
                        MAX(updated_at) AS last_active_at,
                        COALESCE(SUM(cost_usd_accum), 0) AS total_cost
                    FROM "{schema}"."squad_threads"
                    WHERE ($1::text IS NULL OR workspace_id = $1)
                    GROUP BY squad_id
                ),
                task_agg AS (
                    SELECT
                        t.squad_id,
                        COUNT(*) FILTER (WHERE st.status = 'pending') AS pending_tasks,
                        COUNT(*) FILTER (WHERE st.status = 'claimed') AS claimed_tasks,
                        COUNT(*) FILTER (WHERE st.status = 'in_progress') AS in_progress_tasks,
                        COUNT(*) FILTER (WHERE st.status = 'blocked') AS blocked_tasks,
                        COUNT(*) FILTER (WHERE st.status = 'done') AS done_tasks,
                        COUNT(*) FILTER (WHERE st.status = 'failed') AS failed_tasks,
                        COUNT(*) FILTER (WHERE st.status = 'cancelled') AS cancelled_tasks,
                        COUNT(*) FILTER (WHERE st.status = 'escalated') AS escalated_tasks
                    FROM "{schema}"."squad_tasks" AS st
                    JOIN "{schema}"."squad_threads" AS t ON t.id = st.thread_id
                    GROUP BY t.squad_id
                ),
                participant_agg AS (
                    SELECT t.squad_id, COUNT(DISTINCT p.agent_id) AS member_count
                    FROM "{schema}"."squad_thread_participants" AS p
                    JOIN "{schema}"."squad_threads" AS t ON t.id = p.thread_id
                    WHERE p.left_at IS NULL
                    GROUP BY t.squad_id
                )
                SELECT
                    th.squad_id,
                    th.workspace_id,
                    th.open_threads,
                    th.paused_threads,
                    th.completed_threads,
                    th.archived_threads,
                    th.last_active_at,
                    th.total_cost,
                    COALESCE(ta.pending_tasks, 0) AS pending_tasks,
                    COALESCE(ta.claimed_tasks, 0) AS claimed_tasks,
                    COALESCE(ta.in_progress_tasks, 0) AS in_progress_tasks,
                    COALESCE(ta.blocked_tasks, 0) AS blocked_tasks,
                    COALESCE(ta.done_tasks, 0) AS done_tasks,
                    COALESCE(ta.failed_tasks, 0) AS failed_tasks,
                    COALESCE(ta.cancelled_tasks, 0) AS cancelled_tasks,
                    COALESCE(ta.escalated_tasks, 0) AS escalated_tasks,
                    COALESCE(pa.member_count, 0) AS member_count,
                    cs.coordinator_agent_id
                FROM thread_agg AS th
                LEFT JOIN task_agg AS ta ON ta.squad_id = th.squad_id
                LEFT JOIN participant_agg AS pa ON pa.squad_id = th.squad_id
                LEFT JOIN "{schema}"."squad_coordinator_state" AS cs ON cs.squad_id = th.squad_id
                ORDER BY th.last_active_at DESC NULLS LAST, th.squad_id ASC
            """
            rows = await conn.fetch(sql, workspace_id)
    finally:
        with suppress(Exception):
            await pool.close()

    overviews: list[SquadOverview] = []
    for row in rows:
        overviews.append(
            SquadOverview(
                squad_id=row["squad_id"],
                workspace_id=row["workspace_id"],
                coordinator_agent_id=row["coordinator_agent_id"],
                thread_counts={
                    "open": int(row["open_threads"]),
                    "paused": int(row["paused_threads"]),
                    "completed": int(row["completed_threads"]),
                    "archived": int(row["archived_threads"]),
                },
                task_counts={
                    "pending": int(row["pending_tasks"]),
                    "claimed": int(row["claimed_tasks"]),
                    "in_progress": int(row["in_progress_tasks"]),
                    "blocked": int(row["blocked_tasks"]),
                    "done": int(row["done_tasks"]),
                    "failed": int(row["failed_tasks"]),
                    "cancelled": int(row["cancelled_tasks"]),
                    "escalated": int(row["escalated_tasks"]),
                },
                member_count=int(row["member_count"]),
                last_active_at=row["last_active_at"],
                total_cost_usd=row["total_cost"] or Decimal(0),
            )
        )
    return overviews


async def get_thread_overview(
    thread_id: str,
    *,
    dsn: str,
    schema: str = "knowledge_v2",
    message_limit: int = 30,
    task_limit: int = 30,
) -> ThreadOverview | None:
    """Return a denormalized ``ThreadOverview`` or ``None`` if the thread does not exist."""
    if not _SCHEMA_RE.match(schema):
        raise ValueError(f"invalid postgres schema name: {schema!r}")
    pool = await _ensure_pool(dsn, schema)
    try:
        async with pool.acquire() as conn:
            thread_row = await conn.fetchrow(
                f'SELECT * FROM "{schema}"."squad_threads" WHERE id = $1',
                thread_id,
            )
            if thread_row is None:
                return None
            thread = _row_to_thread(thread_row)
            participants_rows = await conn.fetch(
                f"""SELECT * FROM "{schema}"."squad_thread_participants"
                     WHERE thread_id = $1 AND left_at IS NULL
                     ORDER BY joined_at ASC""",
                thread_id,
            )
            message_rows = await conn.fetch(
                f"""SELECT id, from_agent, to_agent, content, message_type,
                            metadata_json, created_at
                       FROM "{schema}"."squad_messages"
                      WHERE thread_id = $1
                      ORDER BY id DESC
                      LIMIT $2""",
                thread_id,
                max(1, min(int(message_limit), 500)),
            )
            task_rows = await conn.fetch(
                f"""SELECT * FROM "{schema}"."squad_tasks"
                     WHERE thread_id = $1
                       AND status IN ('pending', 'claimed', 'in_progress', 'blocked')
                     ORDER BY created_at ASC
                     LIMIT $2""",
                thread_id,
                max(1, min(int(task_limit), 500)),
            )
            counts_row = await conn.fetchrow(
                f"""SELECT
                        COUNT(*) FILTER (WHERE status IN ('pending','claimed','in_progress','blocked')) AS open_count,
                        COUNT(*) FILTER (WHERE status = 'done') AS done_count
                       FROM "{schema}"."squad_tasks"
                      WHERE thread_id = $1""",
                thread_id,
            )
            coord_row = await conn.fetchrow(
                f'SELECT coordinator_agent_id FROM "{schema}"."squad_coordinator_state" WHERE squad_id = $1',
                thread.squad_id,
            )
    finally:
        with suppress(Exception):
            await pool.close()

    recent_messages: list[dict[str, Any]] = []
    for row in message_rows:
        metadata = _decode_jsonb(row["metadata_json"]) or {}
        recent_messages.append(
            {
                "id": int(row["id"]),
                "from": row["from_agent"],
                "to": row["to_agent"],
                "content": row["content"],
                "type": row["message_type"],
                "metadata": metadata if isinstance(metadata, dict) else {},
                "created_at": row["created_at"],
            }
        )
    return ThreadOverview(
        thread=thread,
        participants=[_row_to_participant(r) for r in participants_rows],
        recent_messages=recent_messages,
        active_tasks=[_row_to_task(r) for r in task_rows],
        coordinator_agent_id=coord_row["coordinator_agent_id"] if coord_row else None,
        open_task_count=int(counts_row["open_count"]) if counts_row else 0,
        done_task_count=int(counts_row["done_count"]) if counts_row else 0,
    )


@dataclass
class SquadActivityEntry:
    timestamp: datetime | None
    source: str  # "system_event" | "coordinator"
    event_type: str
    actor: str | None
    summary: str
    thread_id: str | None
    payload: dict[str, Any] = field(default_factory=dict)


async def list_squad_activity(
    *,
    squad_id: str,
    dsn: str,
    schema: str = "knowledge_v2",
    limit: int = 50,
) -> list[SquadActivityEntry]:
    """Return a unified activity timeline for a squad.

    Pulls from two sources:

    - ``squad_messages`` rows with ``message_type = 'system_event'`` posted in
      any thread of the squad (e.g., coordinator change events emitted by the
      ``CoordinatorService`` into open threads).
    - ``squad_coordinator_history`` rows for elect/demote/policy_changed events
      that may not have been broadcast to a thread (e.g., a policy change with
      no open threads at the time).

    Rows are merged via ``UNION ALL`` and ordered by timestamp desc. ``actor``
    is the agent that triggered the event (``from_agent`` for messages, the
    history row's ``triggered_by_agent_id`` for coordinator events).
    """
    if not _SCHEMA_RE.match(schema):
        raise ValueError(f"invalid postgres schema name: {schema!r}")
    pool = await _ensure_pool(dsn, schema)
    capped_limit = max(1, min(int(limit), 500))
    try:
        async with pool.acquire() as conn:
            sql = f"""
                WITH messages AS (
                    SELECT
                        sm.created_at AS ts,
                        'system_event'::text AS source,
                        COALESCE(sm.metadata_json->>'event_type', sm.message_type) AS event_type,
                        sm.from_agent AS actor,
                        sm.content AS summary,
                        sm.thread_id::text AS thread_id,
                        sm.metadata_json AS payload
                      FROM "{schema}"."squad_messages" AS sm
                      JOIN "{schema}"."squad_threads" AS st ON st.id = sm.thread_id
                     WHERE st.squad_id = $1
                       AND sm.message_type = 'system_event'
                ),
                coord_history AS (
                    SELECT
                        ch.created_at AS ts,
                        'coordinator'::text AS source,
                        ch.event_type AS event_type,
                        ch.triggered_by_agent_id AS actor,
                        ('coordinator '
                          || ch.event_type
                          || ': '
                          || COALESCE(ch.previous_coordinator_agent_id, '(none)')
                          || ' -> '
                          || COALESCE(ch.coordinator_agent_id, '(none)')
                        ) AS summary,
                        NULL::text AS thread_id,
                        ch.metadata_json AS payload
                      FROM "{schema}"."squad_coordinator_history" AS ch
                     WHERE ch.squad_id = $1
                )
                SELECT * FROM messages
                UNION ALL
                SELECT * FROM coord_history
                ORDER BY ts DESC NULLS LAST
                LIMIT $2
            """
            rows = await conn.fetch(sql, squad_id, capped_limit)
    finally:
        with suppress(Exception):
            await pool.close()

    entries: list[SquadActivityEntry] = []
    for row in rows:
        payload = _decode_jsonb(row["payload"]) or {}
        entries.append(
            SquadActivityEntry(
                timestamp=row["ts"],
                source=row["source"],
                event_type=row["event_type"] or row["source"],
                actor=row["actor"],
                summary=row["summary"] or "",
                thread_id=row["thread_id"],
                payload=payload if isinstance(payload, dict) else {},
            )
        )
    return entries


@dataclass
class SquadAgentCostRow:
    agent_id: str
    cost_usd: Decimal
    query_count: int


@dataclass
class SquadMetrics:
    squad_id: str
    workspace_ids: list[str]
    total_cost_usd: Decimal
    open_thread_count: int
    completed_thread_count: int
    cost_by_agent: list[SquadAgentCostRow]
    task_count_by_status: dict[str, int]
    last_active_at: datetime | None


async def get_squad_metrics(
    *,
    squad_id: str,
    dsn: str,
    schema: str = "knowledge_v2",
) -> SquadMetrics:
    """Aggregate per-squad operational metrics (single round-trip).

    Pulls thread counts + last-active from ``squad_threads``, task counts by
    status from ``squad_tasks``, and per-agent cost from ``query_history`` rows
    linked to any thread in the squad.
    """
    if not _SCHEMA_RE.match(schema):
        raise ValueError(f"invalid postgres schema name: {schema!r}")
    pool = await _ensure_pool(dsn, schema)
    try:
        async with pool.acquire() as conn:
            thread_row = await conn.fetchrow(
                f"""SELECT
                        COUNT(*) FILTER (WHERE status = 'open') AS open_count,
                        COUNT(*) FILTER (WHERE status = 'completed') AS completed_count,
                        COALESCE(SUM(cost_usd_accum), 0) AS total_cost,
                        MAX(updated_at) AS last_active_at,
                        ARRAY_AGG(DISTINCT workspace_id) FILTER (WHERE workspace_id IS NOT NULL) AS workspaces
                       FROM "{schema}"."squad_threads"
                      WHERE squad_id = $1""",
                squad_id,
            )
            task_rows = await conn.fetch(
                f"""SELECT st.status AS status, COUNT(*) AS count
                       FROM "{schema}"."squad_tasks" AS st
                       JOIN "{schema}"."squad_threads" AS t ON t.id = st.thread_id
                      WHERE t.squad_id = $1
                      GROUP BY st.status""",
                squad_id,
            )
            agent_rows = await conn.fetch(
                f"""SELECT qh.agent_id AS agent_id,
                            COALESCE(SUM(qh.cost_usd), 0) AS cost,
                            COUNT(*) AS query_count
                       FROM "{schema}"."query_history" AS qh
                       JOIN "{schema}"."squad_threads" AS t ON t.id = qh.squad_thread_id
                      WHERE t.squad_id = $1
                      GROUP BY qh.agent_id
                      ORDER BY cost DESC""",
                squad_id,
            )
    finally:
        with suppress(Exception):
            await pool.close()

    task_counts: dict[str, int] = {}
    for row in task_rows:
        task_counts[str(row["status"])] = int(row["count"])
    cost_by_agent = [
        SquadAgentCostRow(
            agent_id=row["agent_id"],
            cost_usd=Decimal(str(row["cost"] or 0)),
            query_count=int(row["query_count"]),
        )
        for row in agent_rows
    ]
    workspaces = thread_row["workspaces"] if thread_row else None
    return SquadMetrics(
        squad_id=squad_id,
        workspace_ids=[str(w) for w in (workspaces or [])],
        total_cost_usd=Decimal(str(thread_row["total_cost"])) if thread_row else Decimal(0),
        open_thread_count=int(thread_row["open_count"]) if thread_row else 0,
        completed_thread_count=int(thread_row["completed_count"]) if thread_row else 0,
        cost_by_agent=cost_by_agent,
        task_count_by_status=task_counts,
        last_active_at=thread_row["last_active_at"] if thread_row else None,
    )


async def get_squad_metrics_default(*, squad_id: str) -> SquadMetrics | None:
    """Convenience wrapper using the configured Postgres DSN."""
    from koda.config import POSTGRES_URL
    from koda.knowledge.config import KNOWLEDGE_V2_POSTGRES_SCHEMA

    if not POSTGRES_URL:
        return None
    schema = (KNOWLEDGE_V2_POSTGRES_SCHEMA or "knowledge_v2").strip() or "knowledge_v2"
    return await get_squad_metrics(squad_id=squad_id, dsn=POSTGRES_URL, schema=schema)


async def list_squad_activity_default(
    *,
    squad_id: str,
    limit: int = 50,
) -> list[SquadActivityEntry] | None:
    """Convenience wrapper using the configured Postgres DSN. Returns ``None``
    when no DSN is set."""
    from koda.config import POSTGRES_URL
    from koda.knowledge.config import KNOWLEDGE_V2_POSTGRES_SCHEMA

    if not POSTGRES_URL:
        return None
    schema = (KNOWLEDGE_V2_POSTGRES_SCHEMA or "knowledge_v2").strip() or "knowledge_v2"
    return await list_squad_activity(
        squad_id=squad_id,
        dsn=POSTGRES_URL,
        schema=schema,
        limit=limit,
    )


async def list_squad_overviews_default(
    *,
    workspace_id: str | None = None,
) -> list[SquadOverview] | None:
    """Convenience wrapper using the configured Postgres DSN. Returns ``None``
    when no DSN is set (caller can degrade to an empty dashboard)."""
    from koda.config import POSTGRES_URL
    from koda.knowledge.config import KNOWLEDGE_V2_POSTGRES_SCHEMA

    if not POSTGRES_URL:
        return None
    schema = (KNOWLEDGE_V2_POSTGRES_SCHEMA or "knowledge_v2").strip() or "knowledge_v2"
    return await list_squad_overviews(dsn=POSTGRES_URL, schema=schema, workspace_id=workspace_id)


async def get_thread_overview_default(
    thread_id: str,
    *,
    message_limit: int = 30,
    task_limit: int = 30,
) -> ThreadOverview | None:
    """Convenience wrapper using the configured Postgres DSN. Returns ``None``
    when DSN is missing OR the thread does not exist."""
    from koda.config import POSTGRES_URL
    from koda.knowledge.config import KNOWLEDGE_V2_POSTGRES_SCHEMA

    if not POSTGRES_URL:
        return None
    schema = (KNOWLEDGE_V2_POSTGRES_SCHEMA or "knowledge_v2").strip() or "knowledge_v2"
    return await get_thread_overview(
        thread_id,
        dsn=POSTGRES_URL,
        schema=schema,
        message_limit=message_limit,
        task_limit=task_limit,
    )
