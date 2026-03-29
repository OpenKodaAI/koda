"""Unified scheduled job service with persistent jobs/runs and safe validation."""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import json
import shlex
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

from koda import config as _config
from koda.logging_config import get_logger
from koda.services import scheduled_job_dispatcher as _dispatcher_impl
from koda.services import scheduled_job_runtime as _runtime_impl
from koda.state.scheduler_store import get_scheduler_store
from koda.utils.command_helpers import normalize_provider
from koda.utils.workdir import validate_work_dir

log = get_logger(__name__)

BLOCKED_SHELL_PATTERN = _config.BLOCKED_SHELL_PATTERN
AGENT_ID = _config.AGENT_ID
DEFAULT_PROVIDER = _config.DEFAULT_PROVIDER
DEFAULT_WORK_DIR = _config.DEFAULT_WORK_DIR
GIT_META_CHARS = _config.GIT_META_CHARS
PROVIDER_DEFAULT_MODELS = _config.PROVIDER_DEFAULT_MODELS
SCHEDULER_CATCHUP_WINDOW_HOURS = _config.SCHEDULER_CATCHUP_WINDOW_HOURS
SCHEDULER_DEFAULT_TIMEZONE = _config.SCHEDULER_DEFAULT_TIMEZONE
SCHEDULER_ENABLED = _config.SCHEDULER_ENABLED
SCHEDULER_LEASE_SECONDS = _config.SCHEDULER_LEASE_SECONDS
SCHEDULER_MAX_CATCHUP_PER_CYCLE = _config.SCHEDULER_MAX_CATCHUP_PER_CYCLE
SCHEDULER_MAX_CONCURRENT_RUNS_PER_JOB = _config.SCHEDULER_MAX_CONCURRENT_RUNS_PER_JOB
SCHEDULER_MAX_DISPATCH_PER_CYCLE = _config.SCHEDULER_MAX_DISPATCH_PER_CYCLE
SCHEDULER_MIN_INTERVAL_SECONDS = _config.SCHEDULER_MIN_INTERVAL_SECONDS
SCHEDULER_NOTIFICATION_MODE = _config.SCHEDULER_NOTIFICATION_MODE
SCHEDULER_POLL_INTERVAL_SECONDS = _config.SCHEDULER_POLL_INTERVAL_SECONDS
SCHEDULER_RETRY_BASE_DELAY = _config.SCHEDULER_RETRY_BASE_DELAY
SCHEDULER_RETRY_MAX_DELAY = _config.SCHEDULER_RETRY_MAX_DELAY
SCHEDULER_RUN_MAX_ATTEMPTS = _config.SCHEDULER_RUN_MAX_ATTEMPTS

JOB_STATUS_DRAFT = "draft"
JOB_STATUS_VALIDATION_PENDING = "validation_pending"
JOB_STATUS_VALIDATED = "validated"
JOB_STATUS_ACTIVE = "active"
JOB_STATUS_PAUSED = "paused"
JOB_STATUS_FAILED_OPEN = "failed_open"
JOB_STATUS_ARCHIVED = "archived"

RUN_STATUS_QUEUED = "queued"
RUN_STATUS_RUNNING = "running"
RUN_STATUS_RETRYING = "retrying"
RUN_STATUS_SUCCEEDED = "succeeded"
RUN_STATUS_FAILED = "failed"
RUN_STATUS_BLOCKED = "blocked"
RUN_STATUS_CANCELLED = "cancelled"
RUN_STATUS_SKIPPED = "skipped"

RUN_TRIGGER_NORMAL = "normal"
RUN_TRIGGER_CATCHUP = "catchup"
RUN_TRIGGER_MANUAL_TEST = "manual_test"
RUN_TRIGGER_MANUAL_RUN = "manual_run"

_ACTIVE_JOB_STATUSES = {
    JOB_STATUS_VALIDATION_PENDING,
    JOB_STATUS_VALIDATED,
    JOB_STATUS_ACTIVE,
    JOB_STATUS_PAUSED,
    JOB_STATUS_FAILED_OPEN,
}
_CLAIMABLE_RUN_STATUSES = {RUN_STATUS_QUEUED, RUN_STATUS_RETRYING}
_AUTOMATIC_RUN_TRIGGERS = {RUN_TRIGGER_NORMAL, RUN_TRIGGER_CATCHUP}
_MANUAL_RUN_TRIGGERS = {RUN_TRIGGER_MANUAL_TEST, RUN_TRIGGER_MANUAL_RUN}
_READ_ONLY_SHELL_COMMANDS = {
    "cat",
    "date",
    "df",
    "du",
    "echo",
    "find",
    "grep",
    "head",
    "ls",
    "pwd",
    "stat",
    "tail",
    "wc",
    "whoami",
}
_READ_ONLY_GIT_SUBCOMMANDS = {"branch", "diff", "log", "rev-parse", "show", "status"}
_CANCELLATION_METADATA_KEY = "cancellation"
_VALIDATION_STATUS_BEFORE_METADATA_KEY = "job_status_before_validation"
_VALIDATION_AUTO_ACTIVATE_METADATA_KEY = "activate_on_success"
_VALIDATION_STATUS_AFTER_METADATA_KEY = "job_status_after_validation"
_VALIDATION_AUTO_ACTIVATED_METADATA_KEY = "validation_auto_activated"


@dataclass(slots=True)
class SchedulerSnapshot:
    active_jobs: int
    due_runs: int
    leased_runs: int
    failed_open_jobs: int
    validation_pending_jobs: int
    dispatcher_running: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_jobs": self.active_jobs,
            "due_runs": self.due_runs,
            "leased_runs": self.leased_runs,
            "failed_open_jobs": self.failed_open_jobs,
            "validation_pending_jobs": self.validation_pending_jobs,
            "dispatcher_running": self.dispatcher_running,
        }


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _loads_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    with contextlib.suppress(TypeError, ValueError, json.JSONDecodeError):
        return json.loads(value)
    return default


def _dumps_json(value: Any) -> str:
    return json.dumps(value or {}, default=str, ensure_ascii=True)


def _store() -> Any:
    return get_scheduler_store()


def _primary_enabled() -> bool:
    return bool(_store().primary_enabled())


def _dict_from_row(cursor: Any, row: Any) -> dict[str, Any]:
    return {cursor.description[idx][0]: row[idx] for idx in range(len(cursor.description))}


def _fetchone(query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    return cast(dict[str, Any] | None, _store().fetch_one(query, params))


def _fetchall(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], _store().fetch_all(query, params))


def _fetchval(query: str, params: tuple[Any, ...] = ()) -> Any:
    return _store().fetch_val(query, params)


def _execute(query: str, params: tuple[Any, ...] = ()) -> int:
    return int(_store().execute(query, params))


def _insert_returning_id(query: str, params: tuple[Any, ...] = ()) -> int:
    return int(_store().insert_returning_id(query, params))


def _normalize_job(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    job = dict(row)
    job["payload"] = _loads_json(job.get("payload_json"), {})
    job["verification_policy"] = _loads_json(job.get("verification_policy_json"), {})
    job["notification_policy"] = _loads_json(job.get("notification_policy_json"), {})
    job["dry_run_required"] = bool(job.get("dry_run_required"))
    return job


def _normalize_run(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    run = dict(row)
    run["metadata"] = _loads_json(run.get("metadata_json"), {})
    return run


def _get_job(job_id: int, user_id: int | None = None) -> dict[str, Any] | None:
    if user_id is None:
        row = _fetchone("SELECT * FROM scheduled_jobs WHERE id = ?", (job_id,))
    else:
        row = _fetchone("SELECT * FROM scheduled_jobs WHERE id = ? AND user_id = ?", (job_id, user_id))
    return _normalize_job(row)


def _get_run(run_id: int) -> dict[str, Any] | None:
    return _normalize_run(_fetchone("SELECT * FROM scheduled_job_runs WHERE id = ?", (run_id,)))


def _get_run_with_job(run_id: int) -> dict[str, Any] | None:
    row = _fetchone(
        """
        SELECT r.*, j.user_id, j.chat_id, j.agent_id, j.job_type, j.trigger_type,
               j.schedule_expr, j.timezone, j.payload_json, j.status AS job_status,
               j.safety_mode, j.dry_run_required, j.verification_policy_json,
               j.notification_policy_json, j.provider_preference, j.model_preference,
               j.work_dir, j.next_run_at, j.last_run_at, j.last_success_at,
               j.last_failure_at, j.migration_source
        FROM scheduled_job_runs r
        JOIN scheduled_jobs j ON j.id = r.scheduled_job_id
        WHERE r.id = ?
        """,
        (run_id,),
    )
    if not row:
        return None
    normalized = _normalize_run(row) or {}
    normalized["job"] = _normalize_job(
        {
            "id": row["scheduled_job_id"],
            "user_id": row["user_id"],
            "chat_id": row["chat_id"],
            "agent_id": row["agent_id"],
            "job_type": row["job_type"],
            "trigger_type": row["trigger_type"],
            "schedule_expr": row["schedule_expr"],
            "timezone": row["timezone"],
            "payload_json": row["payload_json"],
            "status": row["job_status"],
            "safety_mode": row["safety_mode"],
            "dry_run_required": row["dry_run_required"],
            "verification_policy_json": row["verification_policy_json"],
            "notification_policy_json": row["notification_policy_json"],
            "provider_preference": row["provider_preference"],
            "model_preference": row["model_preference"],
            "work_dir": row["work_dir"],
            "next_run_at": row["next_run_at"],
            "last_run_at": row["last_run_at"],
            "last_success_at": row["last_success_at"],
            "last_failure_at": row["last_failure_at"],
            "migration_source": row["migration_source"],
        }
    )
    return normalized


def _as_timezone(name: str | None) -> ZoneInfo:
    with contextlib.suppress(Exception):
        return ZoneInfo(name or SCHEDULER_DEFAULT_TIMEZONE)
    return ZoneInfo("UTC")


def _parse_interval_seconds(expr: str) -> int | None:
    expr = expr.strip().lower()
    if expr.startswith("every "):
        expr = expr[6:]
    if expr.isdigit():
        return int(expr)
    if expr.endswith("s") and expr[:-1].isdigit():
        return int(expr[:-1])
    if expr.endswith("m") and expr[:-1].isdigit():
        return int(expr[:-1]) * 60
    if expr.endswith("h") and expr[:-1].isdigit():
        return int(expr[:-1]) * 3600
    if expr.endswith("d") and expr[:-1].isdigit():
        return int(expr[:-1]) * 86400
    return None


def compute_next_run(
    *,
    trigger_type: str,
    schedule_expr: str,
    timezone_name: str,
    after: datetime | None = None,
) -> datetime | None:
    """Compute the next UTC run time for a job."""
    after_dt = (after or _utcnow()).astimezone(UTC)
    if trigger_type == "interval":
        seconds = _parse_interval_seconds(schedule_expr)
        if not seconds or seconds <= 0:
            return None
        return after_dt + timedelta(seconds=seconds)
    if trigger_type == "one_shot":
        target = _parse_dt(schedule_expr)
        if target and target > after_dt:
            return target
        return None
    if trigger_type == "cron":
        tz = _as_timezone(timezone_name)
        base = after_dt.astimezone(tz)
        croniter = cast(Any, importlib.import_module("croniter").croniter)
        return cast(datetime, croniter(schedule_expr, base).get_next(datetime)).astimezone(UTC)
    return None


def is_read_only_shell_command(command: str) -> bool:
    """Heuristic used to keep legacy shell jobs in a safe subset."""
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    if not parts:
        return False
    root = parts[0].lower()
    if root == "git":
        return len(parts) > 1 and parts[1].lower() in _READ_ONLY_GIT_SUBCOMMANDS
    return root in _READ_ONLY_SHELL_COMMANDS


def _default_verification_policy(job_type: str) -> dict[str, Any]:
    if job_type == "agent_query":
        return {"mode": "post_write_if_any"}
    return {"mode": "task_success"}


def _default_notification_policy() -> dict[str, Any]:
    return {"mode": SCHEDULER_NOTIFICATION_MODE}


def _validate_schedule_policy(
    *,
    job_type: str,
    trigger_type: str,
    schedule_expr: str,
    timezone_name: str,
    after: datetime,
) -> None:
    if trigger_type == "interval":
        seconds = _parse_interval_seconds(schedule_expr)
        if seconds is None or seconds < SCHEDULER_MIN_INTERVAL_SECONDS:
            raise ValueError(
                f"{job_type} jobs require an interval of at least {SCHEDULER_MIN_INTERVAL_SECONDS} seconds."
            )
        return
    if trigger_type != "cron":
        return

    tz = _as_timezone(timezone_name)
    base = after.astimezone(tz)
    try:
        croniter = cast(Any, importlib.import_module("croniter").croniter)
        cron = croniter(schedule_expr, base)
        next_run = cron.get_next(datetime)
        second_run = cron.get_next(datetime)
    except Exception as exc:  # pragma: no cover - validation is handled by _validated_next_run too
        raise ValueError(f"Invalid schedule expression for cron: {exc}") from exc
    interval_seconds = (second_run - next_run).total_seconds()
    if interval_seconds < SCHEDULER_MIN_INTERVAL_SECONDS:
        raise ValueError(
            f"{job_type} cron jobs require an interval of at least {SCHEDULER_MIN_INTERVAL_SECONDS} seconds."
        )


def _validated_next_run(
    *,
    job_type: str,
    trigger_type: str,
    schedule_expr: str,
    timezone_name: str,
    after: datetime | None = None,
) -> datetime | None:
    effective_after = after or _utcnow()
    _validate_schedule_policy(
        job_type=job_type,
        trigger_type=trigger_type,
        schedule_expr=schedule_expr,
        timezone_name=timezone_name,
        after=effective_after,
    )
    try:
        next_run = compute_next_run(
            trigger_type=trigger_type,
            schedule_expr=schedule_expr,
            timezone_name=timezone_name,
            after=effective_after,
        )
    except Exception as exc:
        raise ValueError(f"Invalid schedule expression for {trigger_type}: {exc}") from exc
    if next_run is None:
        raise ValueError(f"Invalid or expired schedule expression for {trigger_type}.")
    return next_run


def _update_run_metadata(run_id: int, updater: Any) -> dict[str, Any] | None:
    run = _get_run(run_id)
    if not run:
        return None
    metadata = dict(run.get("metadata") or {})
    updater(metadata)
    _touch_run(run_id, metadata_json=_dumps_json(metadata))
    return metadata


def _cancellation_override(run: Mapping[str, Any]) -> tuple[str, str] | None:
    metadata = run.get("metadata") or {}
    control = metadata.get(_CANCELLATION_METADATA_KEY)
    if not isinstance(control, dict) or not control.get("requested"):
        return None
    disposition = str(control.get("disposition") or RUN_STATUS_CANCELLED)
    reason = str(control.get("reason") or "Run cancelled by scheduler control.")
    return disposition, reason


def _request_task_cancellations(task_ids: list[int], *, reason: str) -> None:
    if not task_ids:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    from koda.services.queue_manager import cancel_active_task_execution

    for task_id in task_ids:
        loop.create_task(cancel_active_task_execution(task_id, reason=reason))


def _job_status_allows_claim(job_status: str, trigger_reason: str) -> bool:
    if job_status == JOB_STATUS_ACTIVE:
        return True
    if job_status in {JOB_STATUS_VALIDATION_PENDING, JOB_STATUS_VALIDATED, JOB_STATUS_PAUSED, JOB_STATUS_FAILED_OPEN}:
        return trigger_reason in _MANUAL_RUN_TRIGGERS
    return False


def _suppress_automatic_runs(job_id: int, *, status: str, error_message: str) -> int:
    now = _utcnow()
    return _execute(
        """
        UPDATE scheduled_job_runs
        SET status = ?, lease_owner = NULL, lease_expires_at = NULL, next_attempt_at = NULL,
            completed_at = COALESCE(completed_at, ?), error_message = ?, updated_at = ?
        WHERE scheduled_job_id = ?
          AND trigger_reason IN (?, ?)
          AND status IN (?, ?)
        """,
        (
            status,
            _iso(now),
            error_message,
            _iso(now),
            job_id,
            RUN_TRIGGER_NORMAL,
            RUN_TRIGGER_CATCHUP,
            RUN_STATUS_QUEUED,
            RUN_STATUS_RETRYING,
        ),
    )


def _touch_job(job_id: int, **updates: Any) -> None:
    if not updates:
        return
    sets = []
    values: list[Any] = []
    for key, value in updates.items():
        sets.append(f"{key} = ?")
        values.append(value)
    values.append(job_id)
    _execute(
        f"UPDATE scheduled_jobs SET {', '.join(sets)}, updated_at = ? WHERE id = ?",
        tuple([*values[:-1], _iso(_utcnow()), values[-1]]),
    )


def _touch_run(run_id: int, **updates: Any) -> None:
    if not updates:
        return
    sets = []
    values: list[Any] = []
    for key, value in updates.items():
        sets.append(f"{key} = ?")
        values.append(value)
    values.append(run_id)
    _execute(
        f"UPDATE scheduled_job_runs SET {', '.join(sets)}, updated_at = ? WHERE id = ?",
        tuple([*values[:-1], _iso(_utcnow()), values[-1]]),
    )


def create_job(
    *,
    user_id: int,
    chat_id: int,
    job_type: str,
    trigger_type: str,
    schedule_expr: str,
    payload: dict[str, Any],
    timezone_name: str | None = None,
    status: str = JOB_STATUS_VALIDATION_PENDING,
    safety_mode: str = "dry_run_required",
    dry_run_required: bool = True,
    verification_policy: dict[str, Any] | None = None,
    notification_policy: dict[str, Any] | None = None,
    provider_preference: str | None = None,
    model_preference: str | None = None,
    work_dir: str | None = None,
    migration_source: str | None = None,
) -> int:
    """Create a scheduled job and return its ID."""
    now = _utcnow()
    timezone_name = timezone_name or SCHEDULER_DEFAULT_TIMEZONE
    normalized_provider = normalize_provider(provider_preference or payload.get("provider") or DEFAULT_PROVIDER)
    model_preference = model_preference or payload.get("model") or PROVIDER_DEFAULT_MODELS.get(normalized_provider)
    verification_policy = verification_policy or _default_verification_policy(job_type)
    notification_policy = notification_policy or _default_notification_policy()
    work_dir_validation = validate_work_dir(work_dir or payload.get("work_dir") or DEFAULT_WORK_DIR)
    if not work_dir_validation.ok:
        raise ValueError(work_dir_validation.reason or "Blocked: invalid work directory.")
    next_run_at = _validated_next_run(
        job_type=job_type,
        trigger_type=trigger_type,
        schedule_expr=schedule_expr,
        timezone_name=timezone_name,
        after=now,
    )
    params = (
        user_id,
        chat_id,
        AGENT_ID,
        job_type,
        trigger_type,
        schedule_expr,
        timezone_name,
        _dumps_json(payload),
        status,
        safety_mode,
        1 if dry_run_required else 0,
        _dumps_json(verification_policy),
        _dumps_json(notification_policy),
        normalized_provider,
        model_preference,
        work_dir_validation.path,
        _iso(next_run_at) if status == JOB_STATUS_ACTIVE else None,
        migration_source,
        _iso(now),
        _iso(now),
    )
    sql = """
        INSERT INTO scheduled_jobs (
            user_id, chat_id, agent_id, job_type, trigger_type, schedule_expr, timezone,
            payload_json, status, safety_mode, dry_run_required, verification_policy_json,
            notification_policy_json, provider_preference, model_preference, work_dir,
            next_run_at, migration_source, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    return _insert_returning_id(sql, params)


def list_jobs(user_id: int, *, include_archived: bool = False) -> list[dict[str, Any]]:
    query = "SELECT * FROM scheduled_jobs WHERE user_id = ?"
    params: list[Any] = [user_id]
    if not include_archived:
        query += " AND status != ?"
        params.append(JOB_STATUS_ARCHIVED)
    query += " ORDER BY COALESCE(next_run_at, updated_at) ASC, id ASC"
    jobs: list[dict[str, Any]] = []
    for row in _fetchall(query, tuple(params)):
        normalized = _normalize_job(row)
        if normalized is not None:
            jobs.append(normalized)
    return jobs


def get_job(job_id: int, user_id: int | None = None) -> dict[str, Any] | None:
    return _get_job(job_id, user_id)


def get_run_details(run_id: int) -> dict[str, Any] | None:
    """Return a scheduled run joined with its owning job."""
    return _get_run_with_job(run_id)


def list_job_runs(job_id: int, user_id: int | None = None, *, limit: int = 20) -> list[dict[str, Any]]:
    params: list[Any] = [job_id]
    query = (
        "SELECT r.* FROM scheduled_job_runs r "
        "JOIN scheduled_jobs j ON j.id = r.scheduled_job_id "
        "WHERE r.scheduled_job_id = ?"
    )
    if user_id is not None:
        query += " AND j.user_id = ?"
        params.append(user_id)
    query += " ORDER BY r.id DESC LIMIT ?"
    params.append(limit)
    runs: list[dict[str, Any]] = []
    for row in _fetchall(query, tuple(params)):
        normalized = _normalize_run(row)
        if normalized is not None:
            runs.append(normalized)
    return runs


def _has_open_validation_run(job_id: int) -> bool:
    row = _fetchone(
        """
        SELECT id FROM scheduled_job_runs
        WHERE scheduled_job_id = ? AND trigger_reason = ? AND status IN (?, ?, ?)
        ORDER BY id DESC LIMIT 1
        """,
        (job_id, RUN_TRIGGER_MANUAL_TEST, RUN_STATUS_QUEUED, RUN_STATUS_RUNNING, RUN_STATUS_RETRYING),
    )
    return row is not None


def _has_open_run(job_id: int, *, include_validation: bool = True) -> bool:
    statuses = (RUN_STATUS_QUEUED, RUN_STATUS_RUNNING, RUN_STATUS_RETRYING)
    if include_validation:
        row = _fetchone(
            """
            SELECT id FROM scheduled_job_runs
            WHERE scheduled_job_id = ? AND status IN (?, ?, ?)
            ORDER BY id DESC LIMIT 1
            """,
            (job_id, *statuses),
        )
    else:
        row = _fetchone(
            """
            SELECT id FROM scheduled_job_runs
            WHERE scheduled_job_id = ?
              AND trigger_reason != ?
              AND status IN (?, ?, ?)
            ORDER BY id DESC LIMIT 1
            """,
            (job_id, RUN_TRIGGER_MANUAL_TEST, *statuses),
        )
    return row is not None


def _mark_running_automatic_runs(
    job_id: int,
    *,
    disposition: str,
    reason: str,
) -> list[int]:
    rows = _fetchall(
        """
        SELECT id, task_id, metadata_json
        FROM scheduled_job_runs
        WHERE scheduled_job_id = ?
          AND trigger_reason IN (?, ?)
          AND status = ?
        """,
        (job_id, RUN_TRIGGER_NORMAL, RUN_TRIGGER_CATCHUP, RUN_STATUS_RUNNING),
    )
    task_ids: list[int] = []
    now = _iso(_utcnow())
    for row in rows:
        task_id = row.get("task_id")
        if task_id is not None:
            task_ids.append(cast(int, task_id))
        metadata = _loads_json(row.get("metadata_json"), {})
        metadata[_CANCELLATION_METADATA_KEY] = {
            "requested": True,
            "disposition": disposition,
            "reason": reason,
            "requested_at": now,
        }
        _touch_run(int(row["id"]), metadata_json=_dumps_json(metadata))
    return task_ids


def create_run(
    *,
    scheduled_job_id: int,
    scheduled_for: datetime | None = None,
    trigger_reason: str,
    max_attempts: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    """Create a scheduled run occurrence."""
    now = _utcnow()
    scheduled_for = scheduled_for or now
    return _insert_returning_id(
        """
        INSERT INTO scheduled_job_runs (
            scheduled_job_id, scheduled_for, trigger_reason, status, attempt, max_attempts,
            next_attempt_at, verification_status, notification_status, metadata_json,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, 0, ?, ?, 'pending', 'pending', ?, ?, ?)
        """,
        (
            scheduled_job_id,
            _iso(scheduled_for),
            trigger_reason,
            RUN_STATUS_QUEUED,
            max_attempts or SCHEDULER_RUN_MAX_ATTEMPTS,
            _iso(scheduled_for),
            _dumps_json(metadata),
            _iso(now),
            _iso(now),
        ),
    )


def queue_validation_run(
    job_id: int,
    *,
    user_id: int | None = None,
    activate_on_success: bool | None = None,
) -> tuple[int | None, str]:
    """Queue a manual dry-run validation for a job."""
    job = _get_job(job_id, user_id)
    if not job:
        return None, "Job not found."
    if job["status"] == JOB_STATUS_ARCHIVED:
        return None, "Archived jobs cannot be validated."
    if _has_open_validation_run(job_id):
        return None, "Validation already pending."
    if _has_open_run(job_id, include_validation=False):
        return None, "Job already has an active run."
    if activate_on_success is None:
        activate_on_success = job["status"] in {JOB_STATUS_DRAFT, JOB_STATUS_VALIDATION_PENDING}
    if job["status"] == JOB_STATUS_DRAFT:
        _touch_job(job_id, status=JOB_STATUS_VALIDATION_PENDING)
    run_id = create_run(
        scheduled_job_id=job_id,
        trigger_reason=RUN_TRIGGER_MANUAL_TEST,
        metadata={
            _VALIDATION_STATUS_BEFORE_METADATA_KEY: job["status"],
            _VALIDATION_AUTO_ACTIVATE_METADATA_KEY: activate_on_success,
        },
    )
    wake_dispatcher()
    if activate_on_success:
        return run_id, "Validation queued. The job will activate automatically if validation passes."
    return run_id, "Validation queued."


def activate_job(job_id: int, user_id: int) -> tuple[bool, str]:
    """Activate a validated job."""
    job = _get_job(job_id, user_id)
    if not job:
        return False, "Job not found."
    if job["status"] not in {JOB_STATUS_VALIDATED, JOB_STATUS_PAUSED, JOB_STATUS_ACTIVE}:
        return False, "Job must be validated before activation."
    now = _utcnow()
    try:
        _validate_schedule_policy(
            job_type=str(job["job_type"]),
            trigger_type=str(job["trigger_type"]),
            schedule_expr=str(job["schedule_expr"]),
            timezone_name=str(job["timezone"]),
            after=now,
        )
        next_run = compute_next_run(
            trigger_type=str(job["trigger_type"]),
            schedule_expr=str(job["schedule_expr"]),
            timezone_name=str(job["timezone"]),
            after=now,
        )
    except ValueError as exc:
        return False, str(exc)
    if next_run is None and str(job["trigger_type"]) == "one_shot":
        next_run = now
    _touch_job(job_id, status=JOB_STATUS_ACTIVE, next_run_at=_iso(next_run))
    wake_dispatcher()
    return True, "Job activated."


def pause_job(job_id: int, user_id: int) -> tuple[bool, str]:
    job = _get_job(job_id, user_id)
    if not job:
        return False, "Job not found."
    if job["status"] == JOB_STATUS_ARCHIVED:
        return False, "Archived jobs cannot be paused."
    _touch_job(job_id, status=JOB_STATUS_PAUSED, next_run_at=None)
    _suppress_automatic_runs(job_id, status=RUN_STATUS_SKIPPED, error_message="Job paused before execution.")
    running_task_ids = _mark_running_automatic_runs(
        job_id,
        disposition=RUN_STATUS_CANCELLED,
        reason="Job paused during execution.",
    )
    _request_task_cancellations(running_task_ids, reason="Job paused during execution.")
    wake_dispatcher()
    return True, "Job paused."


def resume_job(job_id: int, user_id: int) -> tuple[bool, str]:
    job = _get_job(job_id, user_id)
    if not job:
        return False, "Job not found."
    if job["status"] not in {JOB_STATUS_PAUSED, JOB_STATUS_FAILED_OPEN, JOB_STATUS_VALIDATED}:
        return False, "Job cannot be resumed from its current state."
    return activate_job(job_id, user_id)


def delete_job(job_id: int, user_id: int) -> tuple[bool, str]:
    job = _get_job(job_id, user_id)
    if not job:
        return False, "Job not found."
    if job["status"] == JOB_STATUS_ARCHIVED:
        return False, "Job already archived."
    _touch_job(job_id, status=JOB_STATUS_ARCHIVED, next_run_at=None)
    _suppress_automatic_runs(job_id, status=RUN_STATUS_CANCELLED, error_message="Job archived before execution.")
    running_task_ids = _mark_running_automatic_runs(
        job_id,
        disposition=RUN_STATUS_CANCELLED,
        reason="Job archived during execution.",
    )
    _request_task_cancellations(running_task_ids, reason="Job archived during execution.")
    wake_dispatcher()
    return True, "Job archived."


def run_job_now(job_id: int, user_id: int) -> tuple[int | None, str]:
    job = _get_job(job_id, user_id)
    if not job:
        return None, "Job not found."
    if job["status"] == JOB_STATUS_ARCHIVED:
        return None, "Archived jobs cannot be executed."
    if _has_open_run(job_id):
        return None, "Job already has an active run."
    run_id = create_run(scheduled_job_id=job_id, trigger_reason=RUN_TRIGGER_MANUAL_RUN)
    wake_dispatcher()
    return run_id, "Manual execution queued."


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
    payload = {
        "query": query,
        "session_id": session_id,
        "provider": provider_preference,
        "model": model_preference,
        "work_dir": work_dir,
    }
    job_id = create_job(
        user_id=user_id,
        chat_id=chat_id,
        job_type="agent_query",
        trigger_type=trigger_type,
        schedule_expr=schedule_expr,
        payload=payload,
        timezone_name=timezone_name,
        status=JOB_STATUS_DRAFT,
        safety_mode=safety_mode,
        dry_run_required=dry_run_required,
        verification_policy=verification_policy,
        notification_policy=notification_policy,
        provider_preference=provider_preference,
        model_preference=model_preference,
        work_dir=work_dir,
    )
    queue_validation_run(job_id, user_id=user_id, activate_on_success=auto_activate_after_validation)
    return job_id


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
    payload = {"text": text}
    job_id = create_job(
        user_id=user_id,
        chat_id=chat_id,
        job_type="reminder",
        trigger_type="one_shot",
        schedule_expr=schedule_expr,
        payload=payload,
        timezone_name=timezone_name,
        status=JOB_STATUS_DRAFT,
        safety_mode=safety_mode,
        dry_run_required=dry_run_required,
        verification_policy=verification_policy,
        notification_policy=notification_policy,
        provider_preference=DEFAULT_PROVIDER,
        model_preference=PROVIDER_DEFAULT_MODELS.get(DEFAULT_PROVIDER),
    )
    queue_validation_run(job_id, user_id=user_id, activate_on_success=auto_activate_after_validation)
    return job_id


def create_shell_command_job(
    *,
    user_id: int,
    chat_id: int,
    expression: str,
    command: str,
    description: str = "",
    work_dir: str | None = None,
    auto_activate: bool = True,
    safety_mode: str = "restricted_wrapper",
    verification_policy: dict[str, Any] | None = None,
    notification_policy: dict[str, Any] | None = None,
) -> int:
    if not is_read_only_shell_command(command):
        raise ValueError("Shell command jobs require a read-only command for safe activation.")
    payload = {"command": command, "description": description}
    status = JOB_STATUS_ACTIVE if auto_activate else JOB_STATUS_DRAFT
    return create_job(
        user_id=user_id,
        chat_id=chat_id,
        job_type="shell_command",
        trigger_type="cron",
        schedule_expr=expression,
        payload=payload,
        status=status,
        safety_mode=safety_mode,
        dry_run_required=False,
        verification_policy=verification_policy or {"mode": "task_success"},
        notification_policy=notification_policy,
        work_dir=work_dir,
        provider_preference=DEFAULT_PROVIDER,
        model_preference=PROVIDER_DEFAULT_MODELS.get(DEFAULT_PROVIDER),
    )


_claim_due_runs = _dispatcher_impl._claim_due_runs
_materialize_due_runs = _dispatcher_impl._materialize_due_runs
_release_run = _dispatcher_impl._release_run
get_scheduler_snapshot = _dispatcher_impl.get_scheduler_snapshot
recover_expired_leases = _dispatcher_impl.recover_expired_leases
run_dispatch_cycle = _dispatcher_impl.run_dispatch_cycle
start_scheduler_dispatcher = _dispatcher_impl.start_scheduler_dispatcher
stop_scheduler_dispatcher = _dispatcher_impl.stop_scheduler_dispatcher
wake_dispatcher = _dispatcher_impl.wake_dispatcher

_dispatch_agent_query = _runtime_impl._dispatch_agent_query
_dispatch_reminder = _runtime_impl._dispatch_reminder
_dispatch_run = _runtime_impl._dispatch_run
_dispatch_shell_command = _runtime_impl._dispatch_shell_command
_notification_text = _runtime_impl._notification_text
_notify_run = _runtime_impl._notify_run
_should_notify = _runtime_impl._should_notify
_validated_job_status_after_manual_test = _runtime_impl._validated_job_status_after_manual_test
derive_verification_status = _runtime_impl.derive_verification_status
handle_run_cancellation = _runtime_impl.handle_run_cancellation
handle_run_failure = _runtime_impl.handle_run_failure
handle_run_success = _runtime_impl.handle_run_success
