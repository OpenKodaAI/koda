"""Quality counters and agent-level observability snapshots for memory/runtime governance."""

from __future__ import annotations

from typing import Any

from koda.memory.embedding_queue import get_embedding_job_stats
from koda.state.agent_scope import normalize_agent_scope
from koda.state.knowledge_governance_store import (
    get_knowledge_candidate_counts,
    get_runbook_status_counts,
)
from koda.state.memory_store import (
    get_memory_quality_counters,
    increment_memory_quality_counter,
)
from koda.state.primary import (
    primary_fetch_one,
    require_primary_state_backend,
    run_coro_sync,
)


def _scope(agent_id: str | None) -> str:
    return normalize_agent_scope(agent_id, fallback="default")


def _require_primary(agent_id: str | None = None) -> str:
    scope = _scope(agent_id)
    require_primary_state_backend(agent_id=scope, error="memory quality inspection requires the primary state backend")
    return scope


def _get_memory_rollup(scope: str) -> tuple[int, int, int, int, int]:
    row = (
        run_coro_sync(
            primary_fetch_one(
                """
            SELECT
                COUNT(*) AS total_memories,
                SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) AS active_memories,
                SUM(
                    CASE WHEN COALESCE(memory_status, 'active') = 'superseded' THEN 1 ELSE 0 END
                ) AS superseded_memories,
                SUM(CASE WHEN COALESCE(memory_status, 'active') = 'stale' THEN 1 ELSE 0 END) AS stale_memories,
                SUM(
                    CASE WHEN COALESCE(memory_status, 'active') = 'invalidated' THEN 1 ELSE 0 END
                ) AS invalidated_memories
            FROM napkin_log
            WHERE agent_id = ?
            """,
                (scope,),
                agent_id=scope,
            )
        )
        or {}
    )
    return (
        int(row.get("total_memories") or 0),
        int(row.get("active_memories") or 0),
        int(row.get("superseded_memories") or 0),
        int(row.get("stale_memories") or 0),
        int(row.get("invalidated_memories") or 0),
    )


def _get_recall_rollup(scope: str) -> tuple[int, int, int]:
    row = (
        run_coro_sync(
            primary_fetch_one(
                """
            SELECT
                COALESCE(SUM(total_selected), 0) AS total_selected,
                COALESCE(SUM(total_discarded), 0) AS total_discarded,
                COALESCE(SUM(total_considered), 0) AS total_considered
            FROM memory_recall_audit
            WHERE agent_id = ?
            """,
                (scope,),
                agent_id=scope,
            )
        )
        or {}
    )
    return (
        int(row.get("total_selected") or 0),
        int(row.get("total_discarded") or 0),
        int(row.get("total_considered") or 0),
    )


def _counter_key(*parts: str) -> str:
    return ".".join(part.strip().lower() for part in parts if part.strip())


def record_memory_quality_counter(agent_id: str | None, *parts: str, delta: int = 1) -> None:
    try:
        increment_memory_quality_counter(_scope(agent_id), _counter_key(*parts), delta)
    except Exception:
        return


def record_dedup_decision(agent_id: str | None, reason: str, delta: int = 1) -> None:
    record_memory_quality_counter(agent_id, "dedup", reason, delta=delta)
    try:
        from koda.services import metrics

        metrics.MEMORY_DEDUP_DECISIONS.labels(agent_id=_scope(agent_id), reason=reason).inc(delta)
    except Exception:
        return


def record_status_transition(agent_id: str | None, from_status: str, to_status: str, delta: int = 1) -> None:
    record_memory_quality_counter(agent_id, "status_transition", from_status, to_status, delta=delta)
    try:
        from koda.services import metrics

        metrics.MEMORY_STATUS_TRANSITIONS.labels(
            agent_id=_scope(agent_id),
            from_status=from_status,
            to_status=to_status,
        ).inc(delta)
    except Exception:
        return


def record_conflict_resolution(agent_id: str | None, outcome: str, delta: int = 1) -> None:
    record_memory_quality_counter(agent_id, "conflict", outcome, delta=delta)
    try:
        from koda.services import metrics

        metrics.MEMORY_CONFLICT_RESOLUTIONS.labels(agent_id=_scope(agent_id), outcome=outcome).inc(delta)
    except Exception:
        return


def record_utility_event(agent_id: str | None, outcome: str, delta: int = 1) -> None:
    record_memory_quality_counter(agent_id, "utility", outcome, delta=delta)
    try:
        from koda.services import metrics

        metrics.MEMORY_UTILITY_EVENTS.labels(agent_id=_scope(agent_id), outcome=outcome).inc(delta)
    except Exception:
        return


def record_runbook_governance_action(
    agent_id: str | None, action: str, *, latency_seconds: float | None = None
) -> None:
    record_memory_quality_counter(agent_id, "runbook_governance", action, delta=1)
    try:
        from koda.services import metrics

        metrics.RUNBOOK_GOVERNANCE_ACTIONS.labels(agent_id=_scope(agent_id), action=action).inc()
        if latency_seconds is not None:
            metrics.RUNBOOK_GOVERNANCE_LATENCY.labels(agent_id=_scope(agent_id)).observe(latency_seconds)
    except Exception:
        return


def get_memory_quality_snapshot(agent_id: str | None) -> dict[str, Any]:
    scope = _require_primary(agent_id)
    counters = get_memory_quality_counters(scope)
    candidate_counts = get_knowledge_candidate_counts(agent_id=scope)
    runbook_counts = get_runbook_status_counts(agent_id=scope)
    embedding_jobs = get_embedding_job_stats(scope)
    memory_rows = _get_memory_rollup(scope)
    recall_rows = _get_recall_rollup(scope)

    def counter(*parts: str) -> int:
        return int(counters.get(_counter_key(*parts), 0))

    return {
        "agent_id": scope,
        "memory": {
            "total": int(memory_rows[0] or 0),
            "active": int(memory_rows[1] or 0),
            "superseded": int(memory_rows[2] or 0),
            "stale": int(memory_rows[3] or 0),
            "invalidated": int(memory_rows[4] or 0),
        },
        "extraction": {
            "total": counter("extraction", "total"),
            "accepted": counter("extraction", "accepted"),
            "rejected": counter("extraction", "rejected"),
        },
        "dedup": {
            "canonical_hash": counter("dedup", "canonical_hash"),
            "semantic": counter("dedup", "semantic"),
            "batch": counter("dedup", "batch"),
        },
        "recall": {
            "selected": int(recall_rows[0] or 0),
            "discarded": int(recall_rows[1] or 0),
            "considered": int(recall_rows[2] or 0),
            "conflict_winner": counter("conflict", "winner"),
            "conflict_loser": counter("conflict", "loser"),
        },
        "utility": {
            "useful": counter("utility", "useful"),
            "noise": counter("utility", "noise"),
            "misleading": counter("utility", "misleading"),
        },
        "embedding_jobs": {
            "pending": int(embedding_jobs.get("pending", 0)),
            "processing": int(embedding_jobs.get("processing", 0)),
            "failed": int(embedding_jobs.get("failed", 0)),
            "completed": int(embedding_jobs.get("completed", 0)),
            "cancelled": int(embedding_jobs.get("cancelled", 0)),
            "repaired": counter("embedding", "repaired"),
        },
        "promotions": {
            "pending": int(candidate_counts.get("pending", 0)),
            "approved": int(candidate_counts.get("approved", 0)),
            "rejected": int(candidate_counts.get("rejected", 0)),
            "learning": int(candidate_counts.get("learning", 0)),
        },
        "runbooks": {
            "approved": int(runbook_counts.get("approved", 0)),
            "needs_review": int(runbook_counts.get("needs_review", 0)),
            "expired": int(runbook_counts.get("expired", 0)),
            "deprecated": int(runbook_counts.get("deprecated", 0)),
        },
        "governance": {
            "approved": counter("runbook_governance", "approved"),
            "needs_review": counter("runbook_governance", "needs_review"),
            "expired": counter("runbook_governance", "expired"),
            "deprecated": counter("runbook_governance", "deprecated"),
        },
    }
