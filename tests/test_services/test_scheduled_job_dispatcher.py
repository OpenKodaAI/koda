"""Focused tests for scheduler materialization and lease recovery."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

from koda.services import scheduled_job_dispatcher


class _JobsStub:
    JOB_STATUS_ACTIVE = "active"
    JOB_STATUS_VALIDATION_PENDING = "validation_pending"
    JOB_STATUS_VALIDATED = "validated"
    JOB_STATUS_PAUSED = "paused"
    JOB_STATUS_FAILED_OPEN = "failed_open"
    RUN_STATUS_QUEUED = "queued"
    RUN_STATUS_RUNNING = "running"
    RUN_STATUS_RETRYING = "retrying"
    RUN_STATUS_FAILED = "failed"
    RUN_TRIGGER_NORMAL = "normal"
    RUN_TRIGGER_CATCHUP = "catchup"
    SCHEDULER_CATCHUP_WINDOW_HOURS = 24
    SCHEDULER_POLL_INTERVAL_SECONDS = 60
    SCHEDULER_MAX_CATCHUP_PER_CYCLE = 5
    SCHEDULER_RUN_MAX_ATTEMPTS = 3
    SCHEDULER_LEASE_SECONDS = 120
    AGENT_ID = "AGENT_A"

    def __init__(self, now: datetime) -> None:
        self._now = now
        self.events: list[dict[str, Any]] = []

    def _utcnow(self) -> datetime:
        return self._now

    def _iso(self, dt: datetime | None) -> str | None:
        if dt is None:
            return None
        return dt.astimezone(UTC).isoformat()

    def _normalize_job(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    def _parse_dt(self, value: str | None) -> datetime | None:
        return datetime.fromisoformat(value) if value else None

    def compute_next_run(self, **_kwargs: Any) -> datetime:
        return self._now + timedelta(hours=1)

    def _new_scheduler_trace_id(self, prefix: str = "sched") -> str:
        return f"{prefix}_trace_token"

    def _record_scheduler_event(self, **kwargs: Any) -> None:
        self.events.append(dict(kwargs))


class _MaterializeStore:
    def __init__(self, job_rows: list[dict[str, Any]]) -> None:
        self.job_rows = list(job_rows)
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self.lookup: dict[tuple[int, str, str], dict[str, Any]] = {}

    def fetch_all(self, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        if "FROM scheduled_jobs" in query:
            return list(self.job_rows)
        raise AssertionError(f"Unexpected fetch_all query: {query}")

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> int:
        self.executed.append((query, params))
        if "INSERT INTO scheduled_job_runs" in query:
            key = (int(params[0]), str(params[1]), str(params[2]))
            self.lookup[key] = {"id": 901, "trace_id": params[6]}
            return 1
        return 1

    def fetch_one(self, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        if "FROM scheduled_job_runs" in query:
            return self.lookup.get((int(params[0]), str(params[1]), str(params[2])))
        raise AssertionError(f"Unexpected fetch_one query: {query}")


class _LeaseRecoveryStore:
    def __init__(
        self,
        *,
        rows: list[dict[str, Any]],
        task_statuses: dict[int, str] | None = None,
        runtime_queue_statuses: dict[int, str] | None = None,
    ) -> None:
        self.rows = list(rows)
        self.task_statuses = dict(task_statuses or {})
        self.runtime_queue_statuses = dict(runtime_queue_statuses or {})
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    def fetch_all(self, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        if "lease_expires_at IS NOT NULL" in query:
            return list(self.rows)
        raise AssertionError(f"Unexpected fetch_all query: {query}")

    def fetch_one(self, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        task_id = int(params[0])
        if query.strip() == "SELECT status FROM tasks WHERE id = ?":
            status = self.task_statuses.get(task_id)
            return {"status": status} if status is not None else None
        if query.strip() == "SELECT status FROM runtime_queue_items WHERE task_id = ?":
            status = self.runtime_queue_statuses.get(task_id)
            return {"status": status} if status is not None else None
        raise AssertionError(f"Unexpected fetch_one query: {query}")

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> int:
        self.executed.append((query, params))
        return 1


def test_materialize_due_runs_assigns_trace_id_and_emits_history() -> None:
    now = datetime(2026, 3, 30, 12, 0, tzinfo=UTC)
    jobs = _JobsStub(now)
    store = _MaterializeStore(
        [
            {
                "id": 17,
                "status": jobs.JOB_STATUS_ACTIVE,
                "trigger_type": "interval",
                "schedule_expr": "3600",
                "timezone": "UTC",
                "next_run_at": (now - timedelta(minutes=1)).isoformat(),
            }
        ]
    )

    with (
        patch("koda.services.scheduled_job_dispatcher._jobs", return_value=jobs),
        patch("koda.services.scheduled_job_dispatcher._store", return_value=store),
    ):
        materialized = scheduled_job_dispatcher._materialize_due_runs(now)

    assert materialized == 1
    insert_query, insert_params = next(
        (query, params) for query, params in store.executed if "INSERT INTO scheduled_job_runs" in query
    )
    assert "trace_id" in insert_query
    assert insert_params[6] == "schedrun_trace_token"
    assert jobs.events == [
        {
            "scheduled_job_id": 17,
            "scheduled_run_id": 901,
            "trace_id": "schedrun_trace_token",
            "event_type": "run.created",
            "source": "scheduler_dispatcher",
            "status_to": "queued",
            "details": {
                "scheduled_for": (now - timedelta(minutes=1)).isoformat(),
                "trigger_reason": "normal",
                "max_attempts": 3,
            },
        }
    ]


def test_recover_expired_leases_refreshes_live_runtime_task() -> None:
    now = datetime(2026, 3, 30, 12, 0, tzinfo=UTC)
    jobs = _JobsStub(now)
    store = _LeaseRecoveryStore(
        rows=[
            {
                "id": 51,
                "scheduled_job_id": 17,
                "task_id": 7001,
                "max_attempts": 3,
                "lease_recovery_count": 0,
                "trace_id": "schedrun_live",
                "trigger_reason": "normal",
            }
        ],
        task_statuses={7001: "running"},
    )

    with (
        patch("koda.services.scheduled_job_dispatcher._jobs", return_value=jobs),
        patch("koda.services.scheduled_job_dispatcher._store", return_value=store),
    ):
        recovered = scheduled_job_dispatcher.recover_expired_leases()

    assert recovered == 1
    assert any("lease_heartbeat_at" in query for query, _params in store.executed)
    assert jobs.events[0]["event_type"] == "run.lease_refreshed"
    assert jobs.events[0]["trace_id"] == "schedrun_live"


def test_recover_expired_leases_exhausts_budget_without_requeue_loop() -> None:
    now = datetime(2026, 3, 30, 12, 0, tzinfo=UTC)
    jobs = _JobsStub(now)
    store = _LeaseRecoveryStore(
        rows=[
            {
                "id": 52,
                "scheduled_job_id": 19,
                "task_id": 7002,
                "max_attempts": 1,
                "lease_recovery_count": 0,
                "trace_id": "schedrun_dead",
                "trigger_reason": "normal",
            }
        ],
        task_statuses={7002: "failed"},
    )

    with (
        patch("koda.services.scheduled_job_dispatcher._jobs", return_value=jobs),
        patch("koda.services.scheduled_job_dispatcher._store", return_value=store),
    ):
        recovered = scheduled_job_dispatcher.recover_expired_leases()

    assert recovered == 0
    assert any("UPDATE scheduled_jobs SET status = ?" in query for query, _params in store.executed)
    assert jobs.events[0]["event_type"] == "run.lease_recovery_exhausted"
    assert jobs.events[0]["status_to"] == "failed"
