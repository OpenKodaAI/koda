"""Primary response cache store scoped by agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from koda.config import AGENT_ID
from koda.state.agent_scope import normalize_agent_scope
from koda.state.primary import (
    primary_execute,
    primary_fetch_all,
    primary_fetch_one,
    primary_fetch_val,
    require_primary_state_backend,
    run_coro_sync,
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _agent_scope(agent_id: str | None = None) -> str:
    return normalize_agent_scope(agent_id, fallback=AGENT_ID)


def _require_primary(agent_id: str | None = None) -> str:
    scope = _agent_scope(agent_id)
    require_primary_state_backend(agent_id=scope, error="response cache requires the primary state backend")
    return scope


def cache_upsert(
    user_id: int,
    query_hash: str,
    query_text: str,
    response_text: str,
    model: str | None,
    cost_usd: float,
    work_dir: str,
    expires_at: str,
    agent_id: str | None = None,
) -> int | None:
    now = _now_iso()
    scope = _require_primary(agent_id)
    row_id = run_coro_sync(
        primary_fetch_val(
            """INSERT INTO response_cache
               (
                   agent_id, user_id, query_hash, query_text, response_text,
                   model, cost_usd, work_dir, created_at, expires_at
               )
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id, query_hash) DO UPDATE SET
                   agent_id = EXCLUDED.agent_id,
                   response_text = EXCLUDED.response_text,
                   model = EXCLUDED.model,
                   cost_usd = EXCLUDED.cost_usd,
                   work_dir = EXCLUDED.work_dir,
                   expires_at = EXCLUDED.expires_at,
                   is_active = TRUE
               RETURNING id""",
            (scope, user_id, query_hash, query_text, response_text, model, cost_usd, work_dir, now, expires_at),
            agent_id=scope,
        )
    )
    return int(row_id) if row_id is not None else None


def cache_lookup_by_hash(user_id: int, query_hash: str, *, agent_id: str | None = None) -> tuple[Any, ...] | None:
    scope = _require_primary(agent_id)
    row = run_coro_sync(
        primary_fetch_one(
            """SELECT id, response_text, cost_usd FROM response_cache
               WHERE user_id = ? AND query_hash = ? AND agent_id = ?
                 AND is_active = TRUE AND expires_at > ?""",
            (user_id, query_hash, scope, _now_iso()),
            agent_id=scope,
        )
    )
    if row is None:
        return None
    return (row["id"], row["response_text"], row["cost_usd"])


def cache_get_by_id(cache_id: int, *, agent_id: str | None = None) -> tuple[Any, ...] | None:
    scope = _require_primary(agent_id)
    row = run_coro_sync(
        primary_fetch_one(
            "SELECT response_text, cost_usd FROM response_cache WHERE id = ? AND agent_id = ? AND is_active = TRUE",
            (cache_id, scope),
            agent_id=scope,
        )
    )
    if row is None:
        return None
    return (row["response_text"], row["cost_usd"])


def cache_record_hit(cache_id: int, *, agent_id: str | None = None) -> None:
    scope = _require_primary(agent_id)
    run_coro_sync(
        primary_execute(
            "UPDATE response_cache SET hit_count = hit_count + 1, last_hit_at = ? WHERE id = ? AND agent_id = ?",
            (_now_iso(), cache_id, scope),
            agent_id=scope,
        )
    )


def cache_invalidate_user(user_id: int, *, agent_id: str | None = None) -> int:
    scope = _require_primary(agent_id)
    updated = run_coro_sync(
        primary_execute(
            "UPDATE response_cache SET is_active = FALSE WHERE user_id = ? AND agent_id = ? AND is_active = TRUE",
            (user_id, scope),
            agent_id=scope,
        )
    )
    return int(updated or 0)


def cache_invalidate_entry(cache_id: int, *, agent_id: str | None = None) -> bool:
    scope = _require_primary(agent_id)
    updated = run_coro_sync(
        primary_execute(
            "UPDATE response_cache SET is_active = FALSE WHERE id = ? AND agent_id = ? AND is_active = TRUE",
            (cache_id, scope),
            agent_id=scope,
        )
    )
    return bool(updated)


def cache_cleanup_expired(*, agent_id: str | None = None) -> int:
    scope = _require_primary(agent_id)
    deleted = run_coro_sync(
        primary_execute(
            "DELETE FROM response_cache WHERE agent_id = ? AND (is_active = FALSE OR expires_at <= ?)",
            (scope, _now_iso()),
            agent_id=scope,
        )
    )
    return int(deleted or 0)


def cache_enforce_user_limit(user_id: int, max_entries: int, *, agent_id: str | None = None) -> int:
    scope = _require_primary(agent_id)
    row = run_coro_sync(
        primary_fetch_one(
            "SELECT COUNT(*) AS total FROM response_cache WHERE user_id = ? AND agent_id = ? AND is_active = TRUE",
            (user_id, scope),
            agent_id=scope,
        )
    )
    count = int((row or {}).get("total") or 0)
    if count <= max_entries:
        return 0
    excess = count - max_entries
    deleted = run_coro_sync(
        primary_execute(
            """DELETE FROM response_cache WHERE id IN (
                   SELECT id FROM response_cache
                   WHERE user_id = ? AND agent_id = ? AND is_active = TRUE
                   ORDER BY hit_count ASC, created_at ASC
                   LIMIT ?
               )""",
            (user_id, scope, excess),
            agent_id=scope,
        )
    )
    return int(deleted or 0)


def cache_get_stats(user_id: int, *, agent_id: str | None = None) -> dict[str, Any]:
    scope = _require_primary(agent_id)
    row = run_coro_sync(
        primary_fetch_one(
            """SELECT COUNT(*) AS entries,
                      COALESCE(SUM(hit_count), 0) AS total_hits,
                      COALESCE(SUM(cost_usd * hit_count), 0) AS estimated_savings_usd
               FROM response_cache
               WHERE user_id = ? AND agent_id = ? AND is_active = TRUE""",
            (user_id, scope),
            agent_id=scope,
        )
    )
    return {
        "entries": int((row or {}).get("entries") or 0),
        "total_hits": int((row or {}).get("total_hits") or 0),
        "estimated_savings_usd": round(float((row or {}).get("estimated_savings_usd") or 0.0), 4),
    }


def cache_get_all_active_user_ids(*, agent_id: str | None = None) -> list[int]:
    scope = _require_primary(agent_id)
    rows = run_coro_sync(
        primary_fetch_all(
            "SELECT DISTINCT user_id FROM response_cache WHERE agent_id = ? AND is_active = TRUE",
            (scope,),
            agent_id=scope,
        )
    )
    return [int(row["user_id"]) for row in rows]


def cache_list_active_entries(
    user_id: int,
    *,
    limit: int = 100,
    agent_id: str | None = None,
) -> list[dict[str, Any]]:
    scope = _require_primary(agent_id)
    rows = run_coro_sync(
        primary_fetch_all(
            """
            SELECT id, user_id, query_hash, query_text, response_text, model, cost_usd, work_dir,
                   created_at, expires_at, hit_count, last_hit_at, is_active, agent_id
            FROM response_cache
            WHERE user_id = ? AND agent_id = ? AND is_active = TRUE
            ORDER BY last_hit_at DESC NULLS LAST, created_at DESC
            LIMIT ?
            """,
            (user_id, scope, limit),
            agent_id=scope,
        )
    )
    return [dict(row) for row in rows]
