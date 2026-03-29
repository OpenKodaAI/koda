"""Memory-domain counters over the shared primary backend."""

from __future__ import annotations

from datetime import datetime

from koda.config import AGENT_ID
from koda.state.agent_scope import normalize_agent_scope
from koda.state_primary import (
    primary_execute,
    primary_fetch_all,
    require_primary_state_backend,
    run_coro_sync,
)


def _normalize_agent_scope(agent_id: str | None) -> str:
    return normalize_agent_scope(agent_id, fallback=AGENT_ID)


def _require_primary(agent_id: str | None = None) -> str:
    scope = _normalize_agent_scope(agent_id)
    require_primary_state_backend(agent_id=scope, error="memory counters require the primary state backend")
    return scope


def increment_memory_quality_counter(agent_id: str | None, counter_key: str, delta: int = 1) -> None:
    scope = _require_primary(agent_id)
    now = datetime.now().isoformat()
    run_coro_sync(
        primary_execute(
            """
            INSERT INTO memory_quality_counters (agent_id, counter_key, counter_value, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(agent_id, counter_key) DO UPDATE SET
                counter_value = memory_quality_counters.counter_value + EXCLUDED.counter_value,
                updated_at = EXCLUDED.updated_at
            """,
            (scope, counter_key, delta, now),
            agent_id=scope,
        )
    )


def get_memory_quality_counters(agent_id: str | None) -> dict[str, int]:
    scope = _require_primary(agent_id)
    rows = run_coro_sync(
        primary_fetch_all(
            "SELECT counter_key, counter_value FROM memory_quality_counters WHERE agent_id = ?",
            (scope,),
            agent_id=scope,
        )
    )
    return {str(row["counter_key"]): int(row["counter_value"]) for row in rows}
