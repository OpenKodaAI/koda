"""Scheduler dispatcher loop, leasing, and operational snapshots."""

from __future__ import annotations

import asyncio
import contextlib
import os
import socket
import uuid
from datetime import datetime, timedelta
from typing import Any, cast

from koda.logging_config import get_logger
from koda.state.scheduler_store import get_scheduler_store

log = get_logger(__name__)

_dispatcher_task: asyncio.Task | None = None
_dispatcher_application: Any | None = None
_dispatcher_event = asyncio.Event()
_dispatcher_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def _jobs() -> Any:
    from koda.services import scheduled_jobs

    return scheduled_jobs


def _store() -> Any:
    return get_scheduler_store()


def _materialize_due_runs(now: datetime | None = None) -> int:
    jobs = _jobs()
    now = now or jobs._utcnow()
    cutoff = now - timedelta(hours=jobs.SCHEDULER_CATCHUP_WINDOW_HOURS)
    rows = _store().fetch_all(
        """
        SELECT * FROM scheduled_jobs
        WHERE status = ? AND next_run_at IS NOT NULL AND next_run_at <= ?
        ORDER BY next_run_at ASC
        """,
        (jobs.JOB_STATUS_ACTIVE, jobs._iso(now)),
    )
    materialized = 0
    for row in rows:
        job = jobs._normalize_job(row)
        if not job:
            continue
        due = jobs._parse_dt(job.get("next_run_at"))
        created_this_cycle = 0
        while due and due < cutoff:
            due = jobs.compute_next_run(
                trigger_type=str(job["trigger_type"]),
                schedule_expr=str(job["schedule_expr"]),
                timezone_name=str(job["timezone"]),
                after=due,
            )
        while due and due <= now and created_this_cycle < jobs.SCHEDULER_MAX_CATCHUP_PER_CYCLE:
            trigger_reason = (
                jobs.RUN_TRIGGER_NORMAL
                if due >= now - timedelta(seconds=jobs.SCHEDULER_POLL_INTERVAL_SECONDS)
                else jobs.RUN_TRIGGER_CATCHUP
            )
            _store().execute(
                """
                INSERT INTO scheduled_job_runs (
                    scheduled_job_id, scheduled_for, trigger_reason, status, attempt, max_attempts,
                    next_attempt_at, verification_status, notification_status, metadata_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, 0, ?, ?, 'pending', 'pending', '{}', ?, ?)
                ON CONFLICT (scheduled_job_id, scheduled_for, trigger_reason) DO NOTHING
                """,
                (
                    job["id"],
                    jobs._iso(due),
                    trigger_reason,
                    jobs.RUN_STATUS_QUEUED,
                    jobs.SCHEDULER_RUN_MAX_ATTEMPTS,
                    jobs._iso(due),
                    jobs._iso(now),
                    jobs._iso(now),
                ),
            )
            materialized += 1
            created_this_cycle += 1
            due = jobs.compute_next_run(
                trigger_type=str(job["trigger_type"]),
                schedule_expr=str(job["schedule_expr"]),
                timezone_name=str(job["timezone"]),
                after=due,
            )
        # Single-process assumption: no concurrent dispatcher can race on this update.
        # The run-claiming path below uses optimistic locking via WHERE clause.
        jobs._touch_job(job["id"], next_run_at=jobs._iso(due))
    return materialized


def _claim_due_runs(limit: int | None = None) -> list[dict[str, Any]]:
    jobs = _jobs()
    now = jobs._utcnow()
    lease_expires_at = now + timedelta(seconds=jobs.SCHEDULER_LEASE_SECONDS)
    claimed_job_ids: set[int] = set()
    candidates = _store().fetch_all(
        """
        SELECT r.id, r.scheduled_job_id, r.trigger_reason, j.status AS job_status
        FROM scheduled_job_runs r
        JOIN scheduled_jobs j ON j.id = r.scheduled_job_id
        WHERE j.status IN (?, ?, ?, ?, ?)
          AND r.status IN (?, ?)
          AND COALESCE(r.next_attempt_at, r.scheduled_for) <= ?
          AND (r.lease_expires_at IS NULL OR r.lease_expires_at < ?)
        ORDER BY COALESCE(r.next_attempt_at, r.scheduled_for) ASC, r.id ASC
        LIMIT ?
        """,
        (
            jobs.JOB_STATUS_VALIDATION_PENDING,
            jobs.JOB_STATUS_VALIDATED,
            jobs.JOB_STATUS_ACTIVE,
            jobs.JOB_STATUS_PAUSED,
            jobs.JOB_STATUS_FAILED_OPEN,
            jobs.RUN_STATUS_QUEUED,
            jobs.RUN_STATUS_RETRYING,
            jobs._iso(now),
            jobs._iso(now),
            limit or jobs.SCHEDULER_MAX_DISPATCH_PER_CYCLE,
        ),
    )
    claimed: list[dict[str, Any]] = []
    for candidate in candidates:
        if not jobs._job_status_allows_claim(str(candidate["job_status"]), str(candidate["trigger_reason"])):
            continue
        job_id = int(candidate["scheduled_job_id"])
        if job_id in claimed_job_ids:
            continue
        in_flight = _store().fetch_one(
            """
            SELECT COUNT(*) AS total
            FROM scheduled_job_runs
            WHERE scheduled_job_id = ?
              AND id != ?
              AND status = ?
            """,
            (job_id, int(candidate["id"]), jobs.RUN_STATUS_RUNNING),
        )
        if int((in_flight or {}).get("total") or 0) >= jobs.SCHEDULER_MAX_CONCURRENT_RUNS_PER_JOB:
            continue
        run_id = int(candidate["id"])
        updated = _store().execute(
            """
            UPDATE scheduled_job_runs
            SET status = ?, lease_owner = ?, lease_expires_at = ?,
                started_at = COALESCE(started_at, ?), updated_at = ?
            WHERE id = ?
              AND status IN (?, ?)
              AND (lease_expires_at IS NULL OR lease_expires_at < ?)
            """,
            (
                jobs.RUN_STATUS_RUNNING,
                _dispatcher_id,
                jobs._iso(lease_expires_at),
                jobs._iso(now),
                jobs._iso(now),
                run_id,
                jobs.RUN_STATUS_QUEUED,
                jobs.RUN_STATUS_RETRYING,
                jobs._iso(now),
            ),
        )
        if updated <= 0:
            continue
        joined = jobs._get_run_with_job(run_id)
        if joined:
            claimed.append(joined)
            claimed_job_ids.add(job_id)
    return claimed


def _release_run(
    run_id: int,
    *,
    status: str,
    next_attempt_at: datetime | None = None,
    error_message: str | None = None,
) -> None:
    jobs = _jobs()
    jobs._touch_run(
        run_id,
        status=status,
        next_attempt_at=jobs._iso(next_attempt_at),
        lease_owner=None,
        lease_expires_at=None,
        error_message=error_message,
    )


async def run_dispatch_cycle(application: Any) -> dict[str, int]:
    from koda.services.scheduled_job_runtime import _dispatch_run

    materialized = _materialize_due_runs()
    claimed = _claim_due_runs()
    for run in claimed:
        asyncio.create_task(_dispatch_run(application, run))
    return {"materialized": materialized, "claimed": len(claimed)}


async def _dispatcher_loop(application: Any) -> None:
    jobs = _jobs()
    from koda.services.resilience import (
        check_breaker,
        record_failure,
        record_success,
        scheduler_dispatcher_breaker,
    )

    while True:
        try:
            breaker_error = check_breaker(scheduler_dispatcher_breaker)
            if breaker_error:
                log.warning("scheduler_dispatcher_breaker_open")
                await asyncio.sleep(jobs.SCHEDULER_POLL_INTERVAL_SECONDS)
                continue
            await run_dispatch_cycle(application)
            record_success(scheduler_dispatcher_breaker)
        except asyncio.CancelledError:
            raise
        except Exception:
            record_failure(scheduler_dispatcher_breaker)
            log.exception("scheduler_dispatcher_loop_error")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(_dispatcher_event.wait(), timeout=jobs.SCHEDULER_POLL_INTERVAL_SECONDS)
        _dispatcher_event.clear()


async def start_scheduler_dispatcher(application: Any) -> None:
    """Start the scheduler background dispatcher."""
    jobs = _jobs()
    global _dispatcher_application, _dispatcher_task
    if not jobs.SCHEDULER_ENABLED:
        return
    _dispatcher_application = application
    recover_expired_leases()
    if _dispatcher_task and not _dispatcher_task.done():
        return
    _dispatcher_task = asyncio.create_task(_dispatcher_loop(application))
    log.info("scheduler_dispatcher_started")


async def stop_scheduler_dispatcher() -> None:
    """Stop the scheduler background dispatcher."""
    global _dispatcher_task
    if not _dispatcher_task:
        return
    _dispatcher_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await _dispatcher_task
    _dispatcher_task = None


def wake_dispatcher() -> None:
    _dispatcher_event.set()


def recover_expired_leases() -> int:
    jobs = _jobs()
    now = jobs._utcnow()
    return cast(
        int,
        _store().execute(
            """
            UPDATE scheduled_job_runs
            SET status = CASE WHEN status = ? THEN ? ELSE status END,
                lease_owner = NULL,
                lease_expires_at = NULL,
                updated_at = ?
            WHERE lease_expires_at IS NOT NULL AND lease_expires_at < ?
            """,
            (jobs.RUN_STATUS_RUNNING, jobs.RUN_STATUS_RETRYING, jobs._iso(now), jobs._iso(now)),
        ),
    )


def get_scheduler_snapshot() -> dict[str, Any]:
    """Return a lightweight scheduler operational snapshot."""
    jobs = _jobs()
    now = jobs._utcnow()
    active_jobs = _store().fetch_val(
        "SELECT COUNT(*) FROM scheduled_jobs WHERE status IN (?, ?, ?, ?, ?)",
        (
            jobs.JOB_STATUS_VALIDATION_PENDING,
            jobs.JOB_STATUS_VALIDATED,
            jobs.JOB_STATUS_ACTIVE,
            jobs.JOB_STATUS_PAUSED,
            jobs.JOB_STATUS_FAILED_OPEN,
        ),
    )
    due_runs = _store().fetch_val(
        """
        SELECT COUNT(*) FROM scheduled_job_runs
        WHERE status IN (?, ?) AND COALESCE(next_attempt_at, scheduled_for) <= ?
        """,
        (jobs.RUN_STATUS_QUEUED, jobs.RUN_STATUS_RETRYING, jobs._iso(now)),
    )
    leased_runs = _store().fetch_val(
        "SELECT COUNT(*) FROM scheduled_job_runs WHERE lease_expires_at IS NOT NULL AND lease_expires_at >= ?",
        (jobs._iso(now),),
    )
    failed_open_jobs = _store().fetch_val(
        "SELECT COUNT(*) FROM scheduled_jobs WHERE status = ?",
        (jobs.JOB_STATUS_FAILED_OPEN,),
    )
    validation_pending_jobs = _store().fetch_val(
        "SELECT COUNT(*) FROM scheduled_jobs WHERE status = ?",
        (jobs.JOB_STATUS_VALIDATION_PENDING,),
    )
    snapshot = jobs.SchedulerSnapshot(
        active_jobs=int(active_jobs),
        due_runs=int(due_runs),
        leased_runs=int(leased_runs),
        failed_open_jobs=int(failed_open_jobs),
        validation_pending_jobs=int(validation_pending_jobs),
        dispatcher_running=bool(_dispatcher_task and not _dispatcher_task.done()),
    )
    try:
        from koda.services.metrics import SCHEDULED_ACTIVE_JOBS, SCHEDULED_DUE_RUNS, SCHEDULED_LEASED_RUNS

        agent_id_label = jobs.AGENT_ID or "default"
        SCHEDULED_ACTIVE_JOBS.labels(agent_id=agent_id_label, status="all").set(snapshot.active_jobs)
        SCHEDULED_ACTIVE_JOBS.labels(agent_id=agent_id_label, status="failed_open").set(snapshot.failed_open_jobs)
        SCHEDULED_ACTIVE_JOBS.labels(agent_id=agent_id_label, status="validation_pending").set(
            snapshot.validation_pending_jobs
        )
        SCHEDULED_DUE_RUNS.labels(agent_id=agent_id_label).set(snapshot.due_runs)
        SCHEDULED_LEASED_RUNS.labels(agent_id=agent_id_label).set(snapshot.leased_runs)
    except Exception:
        log.exception("scheduler_metrics_update_error")
    return cast(dict[str, Any], snapshot.to_dict())
