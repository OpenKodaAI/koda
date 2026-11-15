"""Cron wrapper over unified scheduled jobs."""

from __future__ import annotations

from typing import Any

from koda.config import DEFAULT_WORK_DIR
from koda.services.scheduled_jobs import (
    JOB_STATUS_ARCHIVED,
    _get_job,
    create_shell_command_job,
    delete_job,
    is_read_only_shell_command,
    list_jobs,
    pause_job,
    queue_validation_run,
    resume_job,
    wake_dispatcher,
)

# list_jobs returns the user's jobs on this agent only, so the cap holds per user and per agent.
MAX_CRON_JOBS_PER_USER_PER_AGENT = 10


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
    if len(existing) >= MAX_CRON_JOBS_PER_USER_PER_AGENT:
        raise ValueError(f"Maximum of {MAX_CRON_JOBS_PER_USER_PER_AGENT} cron jobs per user on this agent reached.")
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


def list_cron_jobs(user_id: int) -> list[dict[str, Any]]:
    """Return the user's shell command jobs that are not archived."""
    return [
        row
        for row in list_jobs(user_id)
        if str(row.get("job_type") or "") == "shell_command" and str(row.get("status") or "") != JOB_STATUS_ARCHIVED
    ]


def delete_cron_job(user_id: int, job_id: int) -> bool:
    """Archive a cron job."""
    job = _get_job(job_id, user_id)
    if (
        not job
        or str(job.get("job_type") or "") != "shell_command"
        or str(job.get("status") or "") == JOB_STATUS_ARCHIVED
    ):
        return False
    ok, _ = delete_job(job_id, user_id)
    return ok


def toggle_cron_job(user_id: int, job_id: int, enabled: bool) -> bool:
    """Enable or disable a cron job."""
    existing = _get_job(job_id, user_id)
    if (
        not existing
        or str(existing.get("job_type") or "") != "shell_command"
        or str(existing.get("status") or "") == JOB_STATUS_ARCHIVED
    ):
        return False
    if enabled:
        ok, _ = resume_job(job_id, user_id)
        return ok
    ok, _ = pause_job(job_id, user_id)
    return ok
