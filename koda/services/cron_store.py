"""Cron wrapper over unified scheduled jobs."""

from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime
from typing import Any

from koda.config import (
    DEFAULT_WORK_DIR,
    SCHEDULER_DEFAULT_TIMEZONE,
)
from koda.logging_config import get_logger
from koda.services.scheduled_jobs import (
    JOB_STATUS_ACTIVE,
    JOB_STATUS_ARCHIVED,
    JOB_STATUS_PAUSED,
    _get_job,
    _touch_job,
    compute_next_run,
    create_shell_command_job,
    is_read_only_shell_command,
    list_jobs,
    queue_validation_run,
    wake_dispatcher,
)
from koda.state.scheduler_store import get_scheduler_store

log = get_logger(__name__)

MAX_CRON_JOBS_PER_USER = 10


def _store() -> Any:
    return get_scheduler_store()


def _payload(command: str, description: str) -> str:
    return json.dumps({"command": command, "description": description}, ensure_ascii=True)


def _status_from_enabled(enabled: bool) -> str:
    return JOB_STATUS_ACTIVE if enabled else JOB_STATUS_PAUSED


def create_cron_job(
    user_id: int,
    chat_id: int,
    cron_expression: str,
    command: str,
    description: str = "",
    work_dir: str = "/tmp",
    auto_activate_after_validation: bool = True,
) -> int:
    """Create a read-only shell command job in the unified scheduler."""
    if not is_read_only_shell_command(command):
        raise ValueError("Cron jobs now require a read-only command for safe activation.")
    existing = [
        job
        for job in list_jobs(user_id)
        if str(job.get("job_type") or "") == "shell_command" and str(job.get("status") or "") != JOB_STATUS_ARCHIVED
    ]
    if len(existing) >= MAX_CRON_JOBS_PER_USER:
        raise ValueError(f"Maximum of {MAX_CRON_JOBS_PER_USER} cron jobs per user reached.")
    job_id = create_shell_command_job(
        user_id=user_id,
        chat_id=chat_id,
        expression=cron_expression,
        command=command,
        description=description,
        work_dir=work_dir or DEFAULT_WORK_DIR,
        auto_activate=False,
        safety_mode="restricted_wrapper",
        verification_policy={"mode": "task_success"},
        notification_policy={"mode": "summary_complete"},
    )
    queue_validation_run(job_id, user_id=user_id, activate_on_success=auto_activate_after_validation)
    wake_dispatcher()
    return job_id


def list_cron_jobs(user_id: int) -> list[tuple]:
    """Return shell command jobs as (id, cron_expression, command, description, enabled)."""
    jobs: list[tuple] = []
    for row in list_jobs(user_id):
        if str(row.get("job_type") or "") != "shell_command" or str(row.get("status") or "") == JOB_STATUS_ARCHIVED:
            continue
        payload = row.get("payload") or {}
        jobs.append(
            (
                row["id"],
                row["schedule_expr"],
                payload.get("command", ""),
                payload.get("description", ""),
                1 if row["status"] == JOB_STATUS_ACTIVE else 0,
            )
        )
    return jobs


def get_cron_job(job_id: int) -> tuple | None:
    """Return (id, user_id, chat_id, cron_expression, command, description, enabled, work_dir)."""
    row = _get_job(job_id)
    if (
        not row
        or str(row.get("job_type") or "") != "shell_command"
        or str(row.get("status") or "") == JOB_STATUS_ARCHIVED
    ):
        return None
    payload = row.get("payload") or {}
    return (
        row["id"],
        row["user_id"],
        row["chat_id"],
        row["schedule_expr"],
        payload.get("command", ""),
        payload.get("description", ""),
        1 if row["status"] == JOB_STATUS_ACTIVE else 0,
        row["work_dir"],
    )


def delete_cron_job(user_id: int, job_id: int) -> bool:
    """Archive a cron job."""
    job = _get_job(job_id, user_id)
    if (
        not job
        or str(job.get("job_type") or "") != "shell_command"
        or str(job.get("status") or "") == JOB_STATUS_ARCHIVED
    ):
        return False
    _touch_job(job_id, status=JOB_STATUS_ARCHIVED)
    wake_dispatcher()
    return True


def toggle_cron_job(user_id: int, job_id: int, enabled: bool) -> bool:
    """Enable or disable a cron job."""
    now = datetime.now(UTC)
    existing = _get_job(job_id, user_id)
    if (
        not existing
        or str(existing.get("job_type") or "") != "shell_command"
        or str(existing.get("status") or "") == JOB_STATUS_ARCHIVED
    ):
        return False
    next_run = None
    if enabled:
        with contextlib.suppress(Exception):
            next_run = compute_next_run(
                trigger_type="cron",
                schedule_expr=str(existing["schedule_expr"]),
                timezone_name=SCHEDULER_DEFAULT_TIMEZONE,
                after=now,
            )
    _touch_job(
        job_id,
        status=_status_from_enabled(enabled),
        next_run_at=next_run.isoformat() if next_run else None,
    )
    wake_dispatcher()
    return True


def get_all_enabled_jobs() -> list[tuple]:
    """Return active shell command jobs for restore flows."""
    enabled: list[tuple] = []
    for row in _store().fetch_all(
        """
        SELECT id, user_id, chat_id, schedule_expr, payload_json, work_dir
        FROM scheduled_jobs
        WHERE job_type = 'shell_command' AND status = ?
        ORDER BY id
        """,
        (JOB_STATUS_ACTIVE,),
    ):
        payload = json.loads(str(row.get("payload_json") or "{}"))
        enabled.append(
            (
                row["id"],
                row["user_id"],
                row["chat_id"],
                row["schedule_expr"],
                payload.get("command", ""),
                payload.get("description", ""),
                row["work_dir"],
            )
        )
    return enabled


def schedule_cron_task(
    job_id: int,
    agent: Any,
    chat_id: int,
    cron_expression: str,
    command: str,
    work_dir: str = "/tmp",
) -> None:
    """Compatibility no-op. The unified dispatcher wakes up and owns execution."""
    wake_dispatcher()
    log.info("cron_job_schedule_requested", job_id=job_id, expression=cron_expression)


def cancel_cron_task(job_id: int) -> None:
    """Compatibility no-op. The unified dispatcher reads state from the database."""
    wake_dispatcher()
    log.info("cron_job_cancel_requested", job_id=job_id)


async def restore_all_jobs(agent: Any) -> int:
    """Restore hook retained for startup compatibility."""
    enabled = get_all_enabled_jobs()
    wake_dispatcher()
    log.info("cron_jobs_restored", migrated=0, enabled=len(enabled))
    return len(enabled)
