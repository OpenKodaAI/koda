"""Persistent embedding repair queue for canonical memory records."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

import koda.config as config_module
from koda.state.agent_scope import normalize_agent_scope
from koda.state_primary import (
    primary_execute,
    primary_fetch_all,
    primary_fetch_val,
    require_primary_state_backend,
    run_coro_sync,
)


def _current_agent_scope(agent_id: str | None = None) -> str:
    return normalize_agent_scope(agent_id, fallback=config_module.AGENT_ID)


def _require_primary(agent_id: str | None = None) -> str:
    scope = _current_agent_scope(agent_id)
    require_primary_state_backend(agent_id=scope, error="memory embedding jobs require the primary state backend")
    return scope


def _write(query: str, params: Sequence[object], *, agent_id: str | None = None) -> int:
    scope = _require_primary(agent_id)
    return int(run_coro_sync(primary_execute(query, tuple(params), agent_id=scope)) or 0)


def _fetch_rows(query: str, params: Sequence[object], *, agent_id: str | None = None) -> list[Any]:
    scope = _require_primary(agent_id)
    return cast(list[Any], run_coro_sync(primary_fetch_all(query, tuple(params), agent_id=scope)) or [])


@dataclass(slots=True)
class EmbeddingJob:
    id: int
    memory_id: int
    agent_id: str
    status: str
    attempt_count: int
    last_error: str
    next_retry_at: datetime | None
    last_attempt_at: datetime | None
    claimed_at: datetime | None
    created_at: datetime
    updated_at: datetime


def _row_to_job(row: tuple[object, ...] | dict[str, Any]) -> EmbeddingJob:
    if isinstance(row, dict):
        return EmbeddingJob(
            id=int(cast(int | str, row.get("id") or 0)),
            memory_id=int(cast(int | str, row.get("memory_id") or 0)),
            agent_id=str(row.get("agent_id") or "default"),
            status=str(row.get("status") or "pending"),
            attempt_count=int(cast(int | str, row.get("attempt_count") or 0)),
            last_error=str(row.get("last_error") or ""),
            next_retry_at=datetime.fromisoformat(str(row["next_retry_at"])) if row.get("next_retry_at") else None,
            last_attempt_at=datetime.fromisoformat(str(row["last_attempt_at"])) if row.get("last_attempt_at") else None,
            claimed_at=datetime.fromisoformat(str(row["claimed_at"])) if row.get("claimed_at") else None,
            created_at=datetime.fromisoformat(str(row.get("created_at"))),
            updated_at=datetime.fromisoformat(str(row.get("updated_at"))),
        )
    return EmbeddingJob(
        id=int(cast(int | str, row[0])),
        memory_id=int(cast(int | str, row[1])),
        agent_id=str(row[2] or "default"),
        status=str(row[3] or "pending"),
        attempt_count=int(cast(int | str, row[4] or 0)),
        last_error=str(row[5] or ""),
        next_retry_at=datetime.fromisoformat(str(row[6])) if row[6] else None,
        last_attempt_at=datetime.fromisoformat(str(row[7])) if row[7] else None,
        claimed_at=datetime.fromisoformat(str(row[8])) if row[8] else None,
        created_at=datetime.fromisoformat(str(row[9])),
        updated_at=datetime.fromisoformat(str(row[10])),
    )


def enqueue_embedding_job(
    memory_id: int,
    *,
    agent_id: str | None = None,
    status: str = "pending",
    last_error: str = "",
    next_retry_at: datetime | None = None,
) -> int:
    scope = _require_primary(agent_id)
    now = datetime.now().isoformat()
    retry_iso = next_retry_at.isoformat() if next_retry_at else None
    inserted = run_coro_sync(
        primary_fetch_val(
            """
            INSERT INTO memory_embedding_jobs
                (memory_id, agent_id, status, attempt_count, last_error, next_retry_at, created_at, updated_at)
            VALUES (?, ?, ?, 0, ?, ?, ?, ?)
            ON CONFLICT(memory_id, agent_id) DO UPDATE SET
                status = excluded.status,
                last_error = excluded.last_error,
                next_retry_at = excluded.next_retry_at,
                claimed_at = NULL,
                updated_at = excluded.updated_at
            RETURNING id
            """,
            (memory_id, scope, status, last_error, retry_iso, now, now),
            agent_id=scope,
        )
    )
    return int(inserted or 0)


def mark_embedding_job_completed(memory_id: int, *, agent_id: str | None = None) -> None:
    scope = _require_primary(agent_id)
    now = datetime.now().isoformat()
    _write(
        """
        UPDATE memory_embedding_jobs
        SET status = 'completed',
            next_retry_at = NULL,
            claimed_at = NULL,
            updated_at = ?
        WHERE memory_id = ? AND agent_id = ?
        """,
        (now, memory_id, scope),
        agent_id=scope,
    )


def cancel_embedding_job(memory_id: int, *, agent_id: str | None = None) -> None:
    scope = _require_primary(agent_id)
    now = datetime.now().isoformat()
    _write(
        """
        UPDATE memory_embedding_jobs
        SET status = 'cancelled', claimed_at = NULL, updated_at = ?
        WHERE memory_id = ? AND agent_id = ?
        """,
        (now, memory_id, scope),
        agent_id=scope,
    )


def cancel_embedding_jobs_for_user(user_id: int, *, agent_id: str | None = None) -> int:
    scope = _require_primary(agent_id)
    now = datetime.now().isoformat()
    return _write(
        """
        UPDATE memory_embedding_jobs
        SET status = 'cancelled', claimed_at = NULL, updated_at = ?
        WHERE agent_id = ?
          AND memory_id IN (
              SELECT id FROM napkin_log
              WHERE user_id = ? AND agent_id = ?
          )
        """,
        (now, scope, user_id, scope),
        agent_id=scope,
    )


def reschedule_embedding_job(
    memory_id: int,
    *,
    agent_id: str | None = None,
    last_error: str,
    next_retry_at: datetime,
) -> None:
    scope = _require_primary(agent_id)
    now = datetime.now().isoformat()
    updated = _write(
        """
        UPDATE memory_embedding_jobs
        SET status = 'failed',
            attempt_count = attempt_count + 1,
            last_error = ?,
            next_retry_at = ?,
            last_attempt_at = ?,
            claimed_at = NULL,
            updated_at = ?
        WHERE memory_id = ? AND agent_id = ?
        """,
        (last_error, next_retry_at.isoformat(), now, now, memory_id, scope),
        agent_id=scope,
    )
    if updated == 0:
        run_coro_sync(
            primary_execute(
                """
                INSERT INTO memory_embedding_jobs
                    (
                        memory_id,
                        agent_id,
                        status,
                        attempt_count,
                        last_error,
                        next_retry_at,
                        last_attempt_at,
                        created_at,
                        updated_at
                    )
                VALUES (?, ?, 'failed', 1, ?, ?, ?, ?, ?)
                """,
                (memory_id, scope, last_error, next_retry_at.isoformat(), now, now, now),
                agent_id=scope,
            )
        )


def claim_embedding_jobs(agent_id: str | None, limit: int = 16) -> list[EmbeddingJob]:
    scope = _require_primary(agent_id)
    now_iso = datetime.now().isoformat()
    # _fetch_rows delegates to asyncpg's conn.fetch() which supports DML with
    # RETURNING in autocommit mode — the UPDATE is committed automatically.
    rows = _fetch_rows(
        """
        UPDATE memory_embedding_jobs
        SET status = 'processing', claimed_at = ?, last_attempt_at = ?, updated_at = ?
        WHERE id IN (
            SELECT id FROM memory_embedding_jobs
            WHERE agent_id = ?
              AND status IN ('pending', 'failed')
              AND (next_retry_at IS NULL OR next_retry_at <= ?)
            ORDER BY COALESCE(next_retry_at, created_at) ASC, id ASC
            LIMIT ?
        )
        RETURNING id, memory_id, agent_id, status, attempt_count, last_error,
                  next_retry_at, last_attempt_at, claimed_at, created_at, updated_at
        """,
        (now_iso, now_iso, now_iso, scope, now_iso, limit),
        agent_id=scope,
    )
    return [_row_to_job(row) for row in rows]


def get_embedding_job_stats(agent_id: str | None = None) -> dict[str, int]:
    scope = _require_primary(agent_id)
    rows = _fetch_rows(
        """
        SELECT status, COUNT(*) AS total
        FROM memory_embedding_jobs
        WHERE agent_id = ?
        GROUP BY status
        """,
        (scope,),
        agent_id=scope,
    )
    stats: dict[str, int] = {}
    for row in rows:
        if isinstance(row, dict):
            stats[str(row.get("status") or "")] = int(cast(int | str, row.get("total") or 0))
        else:
            stats[str(row[0])] = int(cast(int | str, row[1]))
    return stats
