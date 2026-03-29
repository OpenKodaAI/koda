"""Scheduling utilities backed by the unified scheduled jobs domain."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from telegram.ext import ContextTypes

from koda.logging_config import get_logger
from koda.services import scheduled_jobs as scheduled_jobs_service

log = get_logger(__name__)

_TIME_PATTERN = re.compile(r"^(\d+)\s*(s|sec|m|min|h|hr|hour|d|day)s?$", re.IGNORECASE)
_CRON_INTERVAL = re.compile(r"^every\s+(\d+)\s*(m|min|h|hr|hour|d|day)s?$", re.IGNORECASE)


def create_reminder_job(
    *,
    user_id: int,
    chat_id: int,
    schedule_expr: str,
    text: str,
    timezone_name: str | None = None,
    safety_mode: str = "dry_run_required",
    dry_run_required: bool = True,
    verification_policy: dict[str, Any] | None = None,
    notification_policy: dict[str, Any] | None = None,
    auto_activate_after_validation: bool = True,
) -> int:
    """Legacy-compatible wrapper over the unified scheduled jobs service."""
    return int(
        scheduled_jobs_service.create_reminder_job(
            user_id=user_id,
            chat_id=chat_id,
            schedule_expr=schedule_expr,
            text=text,
            timezone_name=timezone_name,
            safety_mode=safety_mode,
            dry_run_required=dry_run_required,
            verification_policy=verification_policy,
            notification_policy=notification_policy,
            auto_activate_after_validation=auto_activate_after_validation,
        )
    )


def create_agent_query_job(
    *,
    user_id: int,
    chat_id: int,
    trigger_type: str,
    schedule_expr: str,
    query: str,
    timezone_name: str | None = None,
    provider_preference: str | None = None,
    model_preference: str | None = None,
    work_dir: str | None = None,
    session_id: str | None = None,
    safety_mode: str = "dry_run_required",
    dry_run_required: bool = True,
    verification_policy: dict[str, Any] | None = None,
    notification_policy: dict[str, Any] | None = None,
    auto_activate_after_validation: bool = True,
) -> int:
    """Legacy-compatible wrapper over the unified scheduled jobs service."""
    return int(
        scheduled_jobs_service.create_agent_query_job(
            user_id=user_id,
            chat_id=chat_id,
            trigger_type=trigger_type,
            schedule_expr=schedule_expr,
            query=query,
            timezone_name=timezone_name,
            provider_preference=provider_preference,
            model_preference=model_preference,
            work_dir=work_dir,
            session_id=session_id,
            safety_mode=safety_mode,
            dry_run_required=dry_run_required,
            verification_policy=verification_policy,
            notification_policy=notification_policy,
            auto_activate_after_validation=auto_activate_after_validation,
        )
    )


def list_jobs(user_id: int) -> list[dict]:
    """Legacy-compatible wrapper over the unified scheduled jobs service."""
    return scheduled_jobs_service.list_jobs(user_id)


def pause_job(job_id: int, user_id: int) -> tuple[bool, str]:
    """Legacy-compatible wrapper over the unified scheduled jobs service."""
    return scheduled_jobs_service.pause_job(job_id, user_id)


def parse_time_delta(time_str: str) -> timedelta | None:
    """Parse human-readable duration like 5m or 2h."""
    match = _TIME_PATTERN.match(time_str.strip())
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2).lower()
    if unit in ("s", "sec"):
        return timedelta(seconds=amount)
    if unit in ("m", "min"):
        return timedelta(minutes=amount)
    if unit in ("h", "hr", "hour"):
        return timedelta(hours=amount)
    if unit in ("d", "day"):
        return timedelta(days=amount)
    return None


def parse_interval(interval_str: str) -> timedelta | None:
    """Parse recurring interval like every 30m."""
    match = _CRON_INTERVAL.match(interval_str.strip())
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2).lower()
    if unit in ("m", "min"):
        return timedelta(minutes=amount)
    if unit in ("h", "hr", "hour"):
        return timedelta(hours=amount)
    if unit in ("d", "day"):
        return timedelta(days=amount)
    return None


async def schedule_reminder(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    delay: timedelta,
    text: str,
) -> str:
    """Create a reminder job and queue its safe validation."""
    target = datetime.now(UTC) + delay
    job_id = create_reminder_job(
        user_id=user_id,
        chat_id=chat_id,
        schedule_expr=target.isoformat(),
        text=text,
    )
    log.info("reminder_job_created", job_id=job_id, delay_seconds=delay.total_seconds())
    return (
        f"Reminder set as job #{job_id} in validation mode.\n"
        "A safe dry-run is being executed now. "
        "If validation passes, the job will be activated automatically."
    )


async def schedule_recurring(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    interval: timedelta,
    query: str,
) -> str:
    """Create a recurring agent job and queue its safe validation."""
    user_data = context.user_data or {}
    job_id = create_agent_query_job(
        user_id=user_id,
        chat_id=chat_id,
        trigger_type="interval",
        schedule_expr=str(int(interval.total_seconds())),
        query=query,
        provider_preference=user_data.get("provider"),
        model_preference=user_data.get("model"),
        work_dir=user_data.get("work_dir"),
        session_id=user_data.get("session_id"),
    )
    log.info("recurring_job_created", job_id=job_id, interval_seconds=interval.total_seconds())
    return (
        f"Recurring job #{job_id} created in validation mode.\n"
        "A dry-run is in progress to confirm the execution plan safely. "
        "If validation passes, the job will be activated automatically."
    )


def list_user_jobs(context: ContextTypes.DEFAULT_TYPE | None, user_id: int) -> list[str]:
    """Return compact scheduler rows for the user."""
    jobs = list_jobs(user_id)
    lines: list[str] = []
    for job in jobs:
        if job["status"] == "archived":
            continue
        next_run = job.get("next_run_at") or "pending validation"
        lines.append(
            f"#{job['id']} | {job['job_type']} | {job['status']} | next: {next_run} | "
            f"{job['payload'].get('query') or job['payload'].get('text') or job['payload'].get('command', '')}"
        )
    return lines


def cancel_user_jobs(context: ContextTypes.DEFAULT_TYPE | None, user_id: int) -> int:
    """Pause all active scheduler jobs for a user."""
    count = 0
    for job in list_jobs(user_id):
        if job["status"] in {"active", "validation_pending", "validated"}:
            ok, _ = pause_job(int(job["id"]), user_id)
            count += 1 if ok else 0
    return count
