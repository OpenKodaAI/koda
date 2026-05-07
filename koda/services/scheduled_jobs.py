"""Unified scheduled job service with persistent jobs/runs and safe validation."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import importlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4
from zoneinfo import ZoneInfo

from koda import config as _config
from koda.agent_contract import normalize_integration_grants, resolve_allowed_tool_ids, resolve_integration_action
from koda.logging_config import get_logger
from koda.services import scheduled_job_dispatcher as _dispatcher_impl
from koda.services import scheduled_job_runtime as _runtime_impl
from koda.services.llm_runner import get_provider_runtime_eligibility
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
AGENT_ALLOWED_TOOLS = _config.AGENT_ALLOWED_TOOLS
AGENT_EXECUTION_POLICY = _config.AGENT_EXECUTION_POLICY
AGENT_RESOURCE_ACCESS_POLICY = _config.AGENT_RESOURCE_ACCESS_POLICY
AGENT_TOOL_POLICY = _config.AGENT_TOOL_POLICY

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
_VALID_NOTIFICATION_POLICY_MODES = {"summary_complete", "failures_only", "none", "silent"}
_VALID_VERIFICATION_POLICY_MODES = {"post_write_if_any", "task_success"}
_RUN_LIVE_STATUSES = {RUN_STATUS_QUEUED, RUN_STATUS_RUNNING, RUN_STATUS_RETRYING}
_RUN_TERMINAL_STATUSES = {
    RUN_STATUS_SUCCEEDED,
    RUN_STATUS_FAILED,
    RUN_STATUS_BLOCKED,
    RUN_STATUS_CANCELLED,
    RUN_STATUS_SKIPPED,
}
_JOB_VALIDATION_REQUIRED_FIELDS = {
    "trigger_type",
    "schedule_expr",
    "timezone",
    "payload_json",
    "safety_mode",
    "dry_run_required",
    "verification_policy_json",
    "provider_preference",
    "model_preference",
    "work_dir",
}
_PUBLISHED_SNAPSHOT_VERSION_ENV_KEYS = (
    "AGENT_SNAPSHOT_VERSION",
    "AGENT_PUBLISHED_SNAPSHOT_VERSION",
    "AGENT_RUNTIME_SNAPSHOT_VERSION",
)


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


def _new_scheduler_trace_id(prefix: str = "sched") -> str:
    return f"{prefix}_{uuid4().hex}"


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


def _stable_dumps_json(value: Any) -> str:
    if value is None:
        value = {}
    return json.dumps(value, default=str, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _normalize_timezone_name(name: str | None) -> str:
    effective = (name or SCHEDULER_DEFAULT_TIMEZONE).strip() or SCHEDULER_DEFAULT_TIMEZONE
    try:
        ZoneInfo(effective)
    except Exception as exc:
        raise ValueError(f"Invalid timezone: {effective}") from exc
    return effective


def _normalize_notification_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    normalized = dict(policy or _default_notification_policy())
    mode = str(normalized.get("mode") or SCHEDULER_NOTIFICATION_MODE).strip().lower()
    if mode not in _VALID_NOTIFICATION_POLICY_MODES:
        raise ValueError(
            "Invalid notification policy mode. Use one of: " + ", ".join(sorted(_VALID_NOTIFICATION_POLICY_MODES)) + "."
        )
    normalized["mode"] = mode
    return normalized


def _normalize_verification_policy(policy: dict[str, Any] | None, *, job_type: str) -> dict[str, Any]:
    normalized = dict(policy or _default_verification_policy(job_type))
    mode = str(normalized.get("mode") or _default_verification_policy(job_type).get("mode") or "").strip().lower()
    if mode not in _VALID_VERIFICATION_POLICY_MODES:
        raise ValueError(
            "Invalid verification policy mode. Use one of: " + ", ".join(sorted(_VALID_VERIFICATION_POLICY_MODES)) + "."
        )
    normalized["mode"] = mode
    return normalized


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
    job["policy_snapshot"] = _loads_json(job.get("policy_snapshot_json"), {})
    job["policy_snapshot_hash"] = str(job.get("policy_snapshot_hash") or "")
    job["dry_run_required"] = bool(job.get("dry_run_required"))
    return job


def _normalize_run(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    run = dict(row)
    run["metadata"] = _loads_json(run.get("metadata_json"), {})
    return run


def _job_audit_snapshot(job: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": int(job["id"]),
        "user_id": int(job["user_id"]),
        "chat_id": int(job["chat_id"]),
        "job_type": str(job["job_type"]),
        "trigger_type": str(job["trigger_type"]),
        "schedule_expr": str(job["schedule_expr"]),
        "timezone": str(job["timezone"]),
        "status": str(job["status"]),
        "safety_mode": str(job.get("safety_mode") or ""),
        "dry_run_required": bool(job.get("dry_run_required")),
        "provider_preference": job.get("provider_preference"),
        "model_preference": job.get("model_preference"),
        "work_dir": job.get("work_dir"),
        "next_run_at": job.get("next_run_at"),
        "last_run_at": job.get("last_run_at"),
        "last_success_at": job.get("last_success_at"),
        "last_failure_at": job.get("last_failure_at"),
        "config_version": int(job.get("config_version") or 1),
        "payload": dict(job.get("payload") or {}),
        "verification_policy": dict(job.get("verification_policy") or {}),
        "notification_policy": dict(job.get("notification_policy") or {}),
        "policy_snapshot": dict(job.get("policy_snapshot") or {}),
        "policy_snapshot_hash": str(job.get("policy_snapshot_hash") or ""),
    }


def _run_audit_snapshot(run: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": int(run["id"]),
        "scheduled_job_id": int(run["scheduled_job_id"]),
        "status": str(run["status"]),
        "trigger_reason": str(run["trigger_reason"]),
        "attempt": int(run.get("attempt") or 0),
        "max_attempts": int(run.get("max_attempts") or 0),
        "task_id": run.get("task_id"),
        "trace_id": run.get("trace_id"),
        "scheduled_for": run.get("scheduled_for"),
        "started_at": run.get("started_at"),
        "completed_at": run.get("completed_at"),
        "verification_status": run.get("verification_status"),
        "notification_status": run.get("notification_status"),
        "error_message": run.get("error_message"),
        "summary_text": run.get("summary_text"),
        "metadata": dict(run.get("metadata") or {}),
    }


def _record_scheduler_event(
    *,
    scheduled_job_id: int,
    event_type: str,
    scheduled_run_id: int | None = None,
    trace_id: str | None = None,
    actor_type: str = "system",
    actor_id: str | None = None,
    source: str | None = None,
    status_from: str | None = None,
    status_to: str | None = None,
    reason: str | None = None,
    details: dict[str, Any] | None = None,
) -> int:
    now = _utcnow()
    event_id = _insert_returning_id(
        """
        INSERT INTO scheduled_job_events (
            scheduled_job_id, scheduled_run_id, trace_id, event_type, actor_type, actor_id,
            source, status_from, status_to, reason, details_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            scheduled_job_id,
            scheduled_run_id,
            trace_id,
            event_type,
            actor_type,
            actor_id,
            source,
            status_from,
            status_to,
            reason,
            _dumps_json(details),
            _iso(now),
        ),
    )
    with contextlib.suppress(Exception):
        from koda.services import audit

        audit.emit(
            audit.AuditEvent(
                event_type=f"scheduler.{event_type}",
                user_id=(details or {}).get("user_id"),
                task_id=(details or {}).get("task_id"),
                trace_id=trace_id,
                details={
                    "scheduled_job_id": scheduled_job_id,
                    "scheduled_run_id": scheduled_run_id,
                    "actor_type": actor_type,
                    "actor_id": actor_id,
                    "source": source,
                    "status_from": status_from,
                    "status_to": status_to,
                    "reason": reason,
                    "event_id": event_id,
                    **dict(details or {}),
                },
            )
        )
    return event_id


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
               j.last_failure_at, j.migration_source, j.policy_snapshot_json,
               j.policy_snapshot_hash
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
            "policy_snapshot_json": row["policy_snapshot_json"],
            "policy_snapshot_hash": row["policy_snapshot_hash"],
        }
    )
    return normalized


def _as_timezone(name: str | None) -> ZoneInfo:
    return ZoneInfo(_normalize_timezone_name(name))


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
    """Shared resolver used to keep legacy shell jobs in the read-only subset."""
    return resolve_integration_action("shell", {"args": command}).access_level == "read"


def _published_snapshot_version() -> int:
    for key in _PUBLISHED_SNAPSHOT_VERSION_ENV_KEYS:
        raw = os.environ.get(key)
        if not raw:
            continue
        with contextlib.suppress(TypeError, ValueError):
            return max(0, int(raw))
    return 0


def _effective_tool_policy() -> dict[str, Any]:
    policy = dict(AGENT_TOOL_POLICY or {})
    resolved_allowed = resolve_allowed_tool_ids(policy)
    if AGENT_ALLOWED_TOOLS:
        allowed_tool_ids = [tool_id for tool_id in resolved_allowed if tool_id in AGENT_ALLOWED_TOOLS]
    else:
        allowed_tool_ids = resolved_allowed
    if allowed_tool_ids:
        policy["allowed_tool_ids"] = allowed_tool_ids
    else:
        policy.pop("allowed_tool_ids", None)
    return policy


def _effective_resource_access_policy() -> dict[str, Any]:
    policy = dict(AGENT_RESOURCE_ACCESS_POLICY or {}) if isinstance(AGENT_RESOURCE_ACCESS_POLICY, dict) else {}
    grants = normalize_integration_grants(policy.get("integration_grants"))
    if grants:
        policy["integration_grants"] = grants
    else:
        policy.pop("integration_grants", None)
    return policy


def _build_policy_snapshot(job: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(job.get("payload") or {})
    provider_preference = str(job.get("provider_preference") or payload.get("provider") or DEFAULT_PROVIDER).strip()
    provider_preference = normalize_provider(provider_preference or DEFAULT_PROVIDER)
    model_preference = str(job.get("model_preference") or payload.get("model") or "").strip() or None
    if model_preference is None:
        model_preference = PROVIDER_DEFAULT_MODELS.get(provider_preference)
    work_dir = str(job.get("work_dir") or payload.get("work_dir") or DEFAULT_WORK_DIR).strip() or DEFAULT_WORK_DIR
    tool_policy = _effective_tool_policy()
    resource_policy = _effective_resource_access_policy()
    provider_runtime_eligibility = get_provider_runtime_eligibility()
    return {
        "agent_snapshot_version": _published_snapshot_version(),
        "allowed_tool_ids": resolve_allowed_tool_ids(tool_policy),
        "integration_grants": resource_policy.get("integration_grants", {}),
        "execution_policy": dict(AGENT_EXECUTION_POLICY or {}),
        "provider_preference": provider_preference,
        "model_preference": model_preference,
        "work_dir": work_dir,
        "provider_runtime_eligibility": provider_runtime_eligibility,
    }


def _policy_snapshot_payload(job: Mapping[str, Any]) -> tuple[dict[str, Any], str, str]:
    snapshot = _build_policy_snapshot(job)
    snapshot_json = _stable_dumps_json(snapshot)
    snapshot_hash = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
    return snapshot, snapshot_json, snapshot_hash


def _persist_job_policy_snapshot(job_id: int, job: Mapping[str, Any]) -> tuple[dict[str, Any], str, str]:
    snapshot, snapshot_json, snapshot_hash = _policy_snapshot_payload(job)
    _touch_job(job_id, policy_snapshot_json=snapshot_json, policy_snapshot_hash=snapshot_hash)
    return snapshot, snapshot_json, snapshot_hash


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


def _suppress_pending_runs(
    job_id: int,
    *,
    status: str,
    error_message: str,
    trigger_reasons: set[str] | None = None,
) -> int:
    now = _utcnow()
    clauses = ["scheduled_job_id = ?", "status IN (?, ?)"]
    params: list[Any] = [job_id, RUN_STATUS_QUEUED, RUN_STATUS_RETRYING]
    if trigger_reasons:
        clauses.append(f"trigger_reason IN ({', '.join('?' for _ in trigger_reasons)})")
        params.extend(sorted(trigger_reasons))
    return _execute(
        """
        UPDATE scheduled_job_runs
        SET status = ?, lease_owner = NULL, lease_expires_at = NULL, next_attempt_at = NULL,
            completed_at = COALESCE(completed_at, ?), error_message = ?, updated_at = ?
        WHERE """
        + " AND ".join(clauses),
        (
            status,
            _iso(now),
            error_message,
            _iso(now),
            *params,
        ),
    )


def _suppress_automatic_runs(job_id: int, *, status: str, error_message: str) -> int:
    return _suppress_pending_runs(
        job_id,
        status=status,
        error_message=error_message,
        trigger_reasons={RUN_TRIGGER_NORMAL, RUN_TRIGGER_CATCHUP},
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


def _transition_run(
    run_id: int,
    *,
    from_statuses: set[str] | None = None,
    expected_dispatch_token: str | None = None,
    **updates: Any,
) -> bool:
    if not updates:
        return False
    sets = []
    values: list[Any] = []
    for key, value in updates.items():
        sets.append(f"{key} = ?")
        values.append(value)
    sets.append("updated_at = ?")
    values.append(_iso(_utcnow()))
    query = f"UPDATE scheduled_job_runs SET {', '.join(sets)} WHERE id = ?"
    values.append(run_id)
    if from_statuses:
        query += f" AND status IN ({', '.join('?' for _ in from_statuses)})"
        values.extend(sorted(from_statuses))
    if expected_dispatch_token is not None:
        query += " AND dispatch_token = ?"
        values.append(expected_dispatch_token)
    return _execute(query, tuple(values)) > 0


def _mark_running_runs(
    job_id: int,
    *,
    disposition: str,
    reason: str,
    trigger_reasons: set[str] | None = None,
) -> list[int]:
    query = """
        SELECT id, task_id, metadata_json, trace_id
        FROM scheduled_job_runs
        WHERE scheduled_job_id = ?
          AND status = ?
    """
    params: list[Any] = [job_id, RUN_STATUS_RUNNING]
    if trigger_reasons:
        query += f" AND trigger_reason IN ({', '.join('?' for _ in trigger_reasons)})"
        params.extend(sorted(trigger_reasons))
    rows = _fetchall(query, tuple(params))
    task_ids: list[int] = []
    requested_at = _iso(_utcnow())
    for row in rows:
        task_id = row.get("task_id")
        if task_id is not None:
            task_ids.append(cast(int, task_id))
        metadata = _loads_json(row.get("metadata_json"), {})
        metadata[_CANCELLATION_METADATA_KEY] = {
            "requested": True,
            "disposition": disposition,
            "reason": reason,
            "requested_at": requested_at,
        }
        _touch_run(int(row["id"]), metadata_json=_dumps_json(metadata))
        with contextlib.suppress(Exception):
            _record_scheduler_event(
                scheduled_job_id=job_id,
                scheduled_run_id=int(row["id"]),
                trace_id=str(row.get("trace_id") or "") or None,
                event_type="run.cancel_requested",
                status_from=RUN_STATUS_RUNNING,
                status_to=disposition,
                reason=reason,
                details={"task_id": task_id, "requested_at": requested_at},
            )
    return task_ids


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
    timezone_name = _normalize_timezone_name(timezone_name)
    normalized_provider = normalize_provider(provider_preference or payload.get("provider") or DEFAULT_PROVIDER)
    model_preference = model_preference or payload.get("model") or PROVIDER_DEFAULT_MODELS.get(normalized_provider)
    verification_policy = _normalize_verification_policy(verification_policy, job_type=job_type)
    notification_policy = _normalize_notification_policy(notification_policy)
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
    snapshot_source = {
        "id": 0,
        "payload": dict(payload),
        "provider_preference": normalized_provider,
        "model_preference": model_preference,
        "work_dir": work_dir_validation.path,
    }
    _, policy_snapshot_json, policy_snapshot_hash = _policy_snapshot_payload(snapshot_source)
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
        policy_snapshot_json,
        policy_snapshot_hash,
        1,
        _iso(now),
        _iso(now),
    )
    sql = """
        INSERT INTO scheduled_jobs (
            user_id, chat_id, agent_id, job_type, trigger_type, schedule_expr, timezone,
            payload_json, status, safety_mode, dry_run_required, verification_policy_json,
            notification_policy_json, provider_preference, model_preference, work_dir,
            next_run_at, migration_source, policy_snapshot_json, policy_snapshot_hash,
            config_version, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    job_id = _insert_returning_id(sql, params)
    _record_scheduler_event(
        scheduled_job_id=job_id,
        event_type="job.created",
        actor_type="system",
        source="scheduler",
        status_to=status,
        details={
            "user_id": user_id,
            "chat_id": chat_id,
            "job_type": job_type,
            "trigger_type": trigger_type,
            "schedule_expr": schedule_expr,
            "timezone": timezone_name,
            "config_version": 1,
        },
    )
    return job_id


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


def list_all_jobs(*, include_archived: bool = False, limit: int = 500) -> list[dict[str, Any]]:
    query = "SELECT * FROM scheduled_jobs"
    params: list[Any] = []
    if not include_archived:
        query += " WHERE status != ?"
        params.append(JOB_STATUS_ARCHIVED)
    query += " ORDER BY COALESCE(next_run_at, updated_at) ASC, id ASC LIMIT ?"
    params.append(limit)
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


def list_job_events(
    job_id: int,
    user_id: int | None = None,
    *,
    run_id: int | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    params: list[Any] = [job_id]
    query = (
        "SELECT e.* FROM scheduled_job_events e "
        "JOIN scheduled_jobs j ON j.id = e.scheduled_job_id "
        "WHERE e.scheduled_job_id = ?"
    )
    if user_id is not None:
        query += " AND j.user_id = ?"
        params.append(user_id)
    if run_id is not None:
        query += " AND e.scheduled_run_id = ?"
        params.append(run_id)
    query += " ORDER BY e.id DESC LIMIT ?"
    params.append(limit)
    events: list[dict[str, Any]] = []
    for row in _fetchall(query, tuple(params)):
        event = dict(row)
        event["details"] = _loads_json(row.get("details_json"), {})
        events.append(event)
    return events


def get_job_detail(
    job_id: int,
    user_id: int | None = None,
    *,
    run_limit: int = 20,
    event_limit: int = 50,
) -> dict[str, Any] | None:
    job = get_job(job_id, user_id)
    if not job:
        return None
    return {
        "job": job,
        "runs": list_job_runs(job_id, user_id, limit=run_limit),
        "events": list_job_events(job_id, user_id, limit=event_limit),
    }


def summarize_job_payload(job: Mapping[str, Any]) -> str:
    payload = job.get("payload") or {}
    for key in ("query", "text", "command"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return ""


def serialize_job(job: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(job.get("payload") or {})
    return {
        "id": int(job["id"]),
        "bot_id": str(job.get("agent_id") or AGENT_ID or "") or None,
        "user_id": int(job.get("user_id") or 0),
        "chat_id": int(job.get("chat_id") or 0),
        "job_type": str(job.get("job_type") or ""),
        "trigger_type": str(job.get("trigger_type") or ""),
        "schedule_expr": str(job.get("schedule_expr") or ""),
        "cron_expression": str(job.get("schedule_expr") or ""),
        "timezone": str(job.get("timezone") or ""),
        "payload": payload,
        "summary": summarize_job_payload(job),
        "description": str(payload.get("description") or ""),
        "status": str(job.get("status") or ""),
        "enabled": 1 if str(job.get("status") or "") == JOB_STATUS_ACTIVE else 0,
        "work_dir": job.get("work_dir"),
        "provider_preference": job.get("provider_preference"),
        "model_preference": job.get("model_preference"),
        "next_run_at": job.get("next_run_at"),
        "last_run_at": job.get("last_run_at"),
        "last_success_at": job.get("last_success_at"),
        "last_failure_at": job.get("last_failure_at"),
        "policy_snapshot": dict(job.get("policy_snapshot") or {}),
        "policy_snapshot_hash": str(job.get("policy_snapshot_hash") or ""),
        "config_version": int(job.get("config_version") or 1),
        "dry_run_required": bool(job.get("dry_run_required")),
        "verification_policy": dict(job.get("verification_policy") or {}),
        "notification_policy": dict(job.get("notification_policy") or {}),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
    }


def serialize_run(run: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": int(run["id"]),
        "scheduled_job_id": int(run["scheduled_job_id"]),
        "scheduled_for": run.get("scheduled_for"),
        "trigger_reason": run.get("trigger_reason"),
        "status": run.get("status"),
        "attempt": int(run.get("attempt") or 0),
        "max_attempts": int(run.get("max_attempts") or 0),
        "task_id": run.get("task_id"),
        "dlq_id": run.get("dlq_id"),
        "trace_id": run.get("trace_id"),
        "provider_effective": run.get("provider_effective"),
        "model_effective": run.get("model_effective"),
        "verification_status": run.get("verification_status"),
        "notification_status": run.get("notification_status"),
        "summary_text": run.get("summary_text"),
        "error_message": run.get("error_message"),
        "started_at": run.get("started_at"),
        "completed_at": run.get("completed_at"),
        "duration_ms": run.get("duration_ms"),
        "next_attempt_at": run.get("next_attempt_at"),
        "lease_owner": run.get("lease_owner"),
        "lease_expires_at": run.get("lease_expires_at"),
        "dispatch_token": run.get("dispatch_token"),
        "lease_recovery_count": int(run.get("lease_recovery_count") or 0),
        "last_recovered_at": run.get("last_recovered_at"),
        "metadata": dict(run.get("metadata") or {}),
    }


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
    return _mark_running_runs(
        job_id,
        disposition=disposition,
        reason=reason,
        trigger_reasons={RUN_TRIGGER_NORMAL, RUN_TRIGGER_CATCHUP},
    )


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
    job = _get_job(scheduled_job_id)
    policy_snapshot = None
    policy_snapshot_json = "{}"
    policy_snapshot_hash = ""
    if job is not None:
        policy_snapshot, policy_snapshot_json, policy_snapshot_hash = _policy_snapshot_payload(job)
    trace_id = _new_scheduler_trace_id("schedrun")
    metadata_payload = dict(metadata or {})
    metadata_payload.setdefault("policy_snapshot_json", policy_snapshot_json)
    metadata_payload.setdefault("policy_snapshot_hash", policy_snapshot_hash)
    if policy_snapshot is not None:
        metadata_payload.setdefault("policy_snapshot", policy_snapshot)
    run_id = _insert_returning_id(
        """
        INSERT INTO scheduled_job_runs (
            scheduled_job_id, scheduled_for, trigger_reason, status, attempt, max_attempts,
            next_attempt_at, verification_status, notification_status, metadata_json, trace_id,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, 0, ?, ?, 'pending', 'pending', ?, ?, ?, ?)
        """,
        (
            scheduled_job_id,
            _iso(scheduled_for),
            trigger_reason,
            RUN_STATUS_QUEUED,
            max_attempts or SCHEDULER_RUN_MAX_ATTEMPTS,
            _iso(scheduled_for),
            _stable_dumps_json(metadata_payload),
            trace_id,
            _iso(now),
            _iso(now),
        ),
    )
    _record_scheduler_event(
        scheduled_job_id=scheduled_job_id,
        scheduled_run_id=run_id,
        trace_id=trace_id,
        event_type="run.created",
        source="scheduler",
        status_to=RUN_STATUS_QUEUED,
        details={
            "scheduled_for": _iso(scheduled_for),
            "trigger_reason": trigger_reason,
            "max_attempts": max_attempts or SCHEDULER_RUN_MAX_ATTEMPTS,
        },
    )
    return run_id


def queue_validation_run(
    job_id: int,
    *,
    user_id: int | None = None,
    activate_on_success: bool | None = None,
    status_before_validation: str | None = None,
    allow_existing_active_run: bool = False,
) -> tuple[int | None, str]:
    """Queue a manual dry-run validation for a job."""
    job = _get_job(job_id, user_id)
    if not job:
        return None, "Job not found."
    if job["status"] == JOB_STATUS_ARCHIVED:
        return None, "Archived jobs cannot be validated."
    if _has_open_validation_run(job_id):
        return None, "Validation already pending."
    if not allow_existing_active_run and _has_open_run(job_id, include_validation=False):
        return None, "Job already has an active run."
    if activate_on_success is None:
        activate_on_success = job["status"] in {JOB_STATUS_DRAFT, JOB_STATUS_VALIDATION_PENDING}
    if job["status"] == JOB_STATUS_DRAFT:
        _touch_job(job_id, status=JOB_STATUS_VALIDATION_PENDING)
    effective_previous_status = status_before_validation or str(job["status"])
    _persist_job_policy_snapshot(job_id, job)
    run_id = create_run(
        scheduled_job_id=job_id,
        trigger_reason=RUN_TRIGGER_MANUAL_TEST,
        metadata={
            _VALIDATION_STATUS_BEFORE_METADATA_KEY: effective_previous_status,
            _VALIDATION_AUTO_ACTIVATE_METADATA_KEY: activate_on_success,
        },
    )
    _touch_job(job_id, last_validation_run_id=run_id)
    run = _get_run(run_id) or {}
    _record_scheduler_event(
        scheduled_job_id=job_id,
        scheduled_run_id=run_id,
        trace_id=str(run.get("trace_id") or "") or None,
        event_type="job.validation_queued",
        actor_type="user" if user_id is not None else "system",
        actor_id=str(user_id) if user_id is not None else None,
        source="scheduler",
        status_from=effective_previous_status,
        status_to=str(job["status"] if job["status"] != JOB_STATUS_DRAFT else JOB_STATUS_VALIDATION_PENDING),
        details={"activate_on_success": activate_on_success, "validation_run_id": run_id},
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
    if job["status"] not in {JOB_STATUS_VALIDATED, JOB_STATUS_PAUSED, JOB_STATUS_ACTIVE, JOB_STATUS_FAILED_OPEN}:
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
    _record_scheduler_event(
        scheduled_job_id=job_id,
        event_type="job.activated",
        actor_type="user",
        actor_id=str(user_id),
        source="scheduler",
        status_from=str(job["status"]),
        status_to=JOB_STATUS_ACTIVE,
        details={"next_run_at": _iso(next_run), "user_id": user_id},
    )
    wake_dispatcher()
    return True, "Job activated."


def pause_job(job_id: int, user_id: int) -> tuple[bool, str]:
    job = _get_job(job_id, user_id)
    if not job:
        return False, "Job not found."
    if job["status"] == JOB_STATUS_ARCHIVED:
        return False, "Archived jobs cannot be paused."
    _touch_job(job_id, status=JOB_STATUS_PAUSED, next_run_at=None)
    _suppress_pending_runs(job_id, status=RUN_STATUS_SKIPPED, error_message="Job paused before execution.")
    running_task_ids = _mark_running_runs(
        job_id,
        disposition=RUN_STATUS_CANCELLED,
        reason="Job paused during execution.",
    )
    _request_task_cancellations(running_task_ids, reason="Job paused during execution.")
    _record_scheduler_event(
        scheduled_job_id=job_id,
        event_type="job.paused",
        actor_type="user",
        actor_id=str(user_id),
        source="scheduler",
        status_from=str(job["status"]),
        status_to=JOB_STATUS_PAUSED,
        reason="Job paused by operator.",
        details={"user_id": user_id},
    )
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
    _suppress_pending_runs(job_id, status=RUN_STATUS_CANCELLED, error_message="Job archived before execution.")
    running_task_ids = _mark_running_runs(
        job_id,
        disposition=RUN_STATUS_CANCELLED,
        reason="Job archived during execution.",
    )
    _request_task_cancellations(running_task_ids, reason="Job archived during execution.")
    _record_scheduler_event(
        scheduled_job_id=job_id,
        event_type="job.archived",
        actor_type="user",
        actor_id=str(user_id),
        source="scheduler",
        status_from=str(job["status"]),
        status_to=JOB_STATUS_ARCHIVED,
        reason="Job archived by operator.",
        details={"user_id": user_id},
    )
    wake_dispatcher()
    return True, "Job archived."


def run_job_now(job_id: int, user_id: int) -> tuple[int | None, str]:
    job = _get_job(job_id, user_id)
    if not job:
        return None, "Job not found."
    if job["status"] == JOB_STATUS_ARCHIVED:
        return None, "Archived jobs cannot be executed."
    if job["status"] not in {JOB_STATUS_ACTIVE, JOB_STATUS_VALIDATED, JOB_STATUS_PAUSED}:
        return None, "Job must be validated before manual execution."
    if _has_open_run(job_id):
        return None, "Job already has an active run."
    run_id = create_run(scheduled_job_id=job_id, trigger_reason=RUN_TRIGGER_MANUAL_RUN)
    run = _get_run(run_id) or {}
    _record_scheduler_event(
        scheduled_job_id=job_id,
        scheduled_run_id=run_id,
        trace_id=str(run.get("trace_id") or "") or None,
        event_type="job.manual_run_queued",
        actor_type="user",
        actor_id=str(user_id),
        source="scheduler",
        details={"user_id": user_id, "run_id": run_id},
    )
    wake_dispatcher()
    return run_id, "Manual execution queued."


def update_job(
    job_id: int,
    *,
    user_id: int,
    patch: Mapping[str, Any],
    expected_config_version: int | None = None,
    actor_type: str = "user",
    actor_id: str | None = None,
    source: str = "scheduler",
    reason: str | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    job = _get_job(job_id, user_id)
    if not job:
        return {"ok": False, "message": "Job not found."}
    if str(job["status"]) == JOB_STATUS_ARCHIVED:
        return {"ok": False, "message": "Archived jobs cannot be edited."}
    current_config_version = int(job.get("config_version") or 1)
    if expected_config_version is not None and expected_config_version != current_config_version:
        return {
            "ok": False,
            "message": (
                "Job was updated by another actor. "
                f"Expected version {expected_config_version}, found {current_config_version}."
            ),
            "config_version": current_config_version,
        }

    before = _job_audit_snapshot(job)
    normalized_patch = dict(patch)
    auto_activate_after_validation = normalized_patch.get("auto_activate_after_validation")
    previous_status = str(job["status"])
    job_type = str(job["job_type"])
    trigger_type = str(normalized_patch.get("trigger_type") or job["trigger_type"]).strip()
    schedule_expr = str(normalized_patch.get("schedule_expr") or job["schedule_expr"]).strip()
    timezone_name = _normalize_timezone_name(
        cast(str | None, normalized_patch.get("timezone") or normalized_patch.get("timezone_name") or job["timezone"])
    )
    payload = dict(job.get("payload") or {})
    provider_preference = normalize_provider(
        cast(
            str | None,
            normalized_patch.get("provider")
            or normalized_patch.get("provider_preference")
            or job.get("provider_preference")
            or DEFAULT_PROVIDER,
        )
    )
    model_preference = cast(
        str | None,
        normalized_patch.get("model") or normalized_patch.get("model_preference") or job.get("model_preference"),
    ) or PROVIDER_DEFAULT_MODELS.get(provider_preference)
    work_dir_candidate = cast(str | None, normalized_patch.get("work_dir") or job.get("work_dir") or DEFAULT_WORK_DIR)
    work_dir_validation = validate_work_dir(work_dir_candidate)
    if not work_dir_validation.ok:
        return {"ok": False, "message": work_dir_validation.reason or "Blocked: invalid work directory."}
    work_dir = work_dir_validation.path
    safety_mode = str(normalized_patch.get("safety_mode") or job.get("safety_mode") or "dry_run_required").strip()
    dry_run_required = bool(normalized_patch.get("dry_run_required", bool(job.get("dry_run_required"))))
    try:
        verification_policy = _normalize_verification_policy(
            cast(dict[str, Any] | None, normalized_patch.get("verification_policy") or job.get("verification_policy")),
            job_type=job_type,
        )
        notification_policy = _normalize_notification_policy(
            cast(dict[str, Any] | None, normalized_patch.get("notification_policy") or job.get("notification_policy"))
        )
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}

    if job_type == "agent_query":
        if "query" in normalized_patch:
            payload["query"] = str(normalized_patch.get("query") or "").strip()
        if "session_id" in normalized_patch:
            payload["session_id"] = normalized_patch.get("session_id")
        if not str(payload.get("query") or "").strip():
            return {"ok": False, "message": "Agent jobs require a non-empty query."}
    elif job_type == "reminder":
        if "text" in normalized_patch:
            payload["text"] = str(normalized_patch.get("text") or "").strip()
        if trigger_type not in {"one_shot", "interval", "cron"}:
            return {"ok": False, "message": "Reminder jobs support trigger_type one_shot, interval or cron."}
        if not str(payload.get("text") or "").strip():
            return {"ok": False, "message": "Reminder jobs require non-empty reminder text."}
    elif job_type == "shell_command":
        if "command" in normalized_patch:
            payload["command"] = str(normalized_patch.get("command") or "").strip()
        if "description" in normalized_patch:
            payload["description"] = str(normalized_patch.get("description") or "").strip()
        if trigger_type != "cron":
            return {"ok": False, "message": "Shell command jobs currently support cron trigger_type only."}
        command = str(payload.get("command") or "").strip()
        if not command:
            return {"ok": False, "message": "Shell command jobs require a command."}
        if not is_read_only_shell_command(command):
            return {"ok": False, "message": "Shell command jobs require a read-only command for safe activation."}
    else:
        return {"ok": False, "message": f"Unsupported job type: {job_type}"}

    payload["provider"] = provider_preference
    payload["model"] = model_preference
    payload["work_dir"] = work_dir

    try:
        _validated_next_run(
            job_type=job_type,
            trigger_type=trigger_type,
            schedule_expr=schedule_expr,
            timezone_name=timezone_name,
            after=_utcnow(),
        )
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}

    base_updates = {
        "trigger_type": trigger_type,
        "schedule_expr": schedule_expr,
        "timezone": timezone_name,
        "payload_json": _dumps_json(payload),
        "safety_mode": safety_mode,
        "dry_run_required": 1 if dry_run_required else 0,
        "verification_policy_json": _dumps_json(verification_policy),
        "notification_policy_json": _dumps_json(notification_policy),
        "provider_preference": provider_preference,
        "model_preference": model_preference,
        "work_dir": work_dir,
    }
    snapshot_source = dict(job)
    snapshot_source.update(
        {
            "payload": payload,
            "provider_preference": provider_preference,
            "model_preference": model_preference,
            "work_dir": work_dir,
        }
    )
    _, policy_snapshot_json, policy_snapshot_hash = _policy_snapshot_payload(snapshot_source)
    base_updates["policy_snapshot_json"] = policy_snapshot_json
    base_updates["policy_snapshot_hash"] = policy_snapshot_hash
    changed_fields = sorted(key for key, value in base_updates.items() if job.get(key) != value)
    if not changed_fields:
        return {
            "ok": True,
            "message": "No changes detected.",
            "job": job,
            "changed_fields": [],
            "config_version": current_config_version,
        }
    updates = {**base_updates, "config_version": current_config_version + 1}

    validation_required = any(field in _JOB_VALIDATION_REQUIRED_FIELDS for field in changed_fields)
    validation_run_id: int | None = None
    if validation_required:
        updates["status"] = JOB_STATUS_VALIDATION_PENDING
        updates["next_run_at"] = None
        updates["last_validation_run_id"] = None
        running_reason = "Job configuration updated during execution."
        pending_reason = "Job configuration updated before execution."
        _touch_job(job_id, **updates)
        _suppress_pending_runs(job_id, status=RUN_STATUS_CANCELLED, error_message=pending_reason)
        running_task_ids = _mark_running_runs(job_id, disposition=RUN_STATUS_CANCELLED, reason=running_reason)
        _request_task_cancellations(running_task_ids, reason=running_reason)
        activate_on_success = (
            bool(auto_activate_after_validation)
            if auto_activate_after_validation is not None
            else previous_status == JOB_STATUS_ACTIVE
        )
        validation_run_id, validation_message = queue_validation_run(
            job_id,
            user_id=user_id,
            activate_on_success=activate_on_success,
            status_before_validation=previous_status,
            allow_existing_active_run=True,
        )
        if validation_run_id is None:
            message = f"Job updated, but follow-up validation was not queued: {validation_message}"
        else:
            message = "Job updated. A new validation run was queued and the job will " + (
                "reactivate automatically if it passes."
                if activate_on_success
                else "stay pending activation after validation."
            )
    else:
        _touch_job(job_id, **updates)
        message = "Job updated."

    refreshed = _get_job(job_id, user_id)
    details = {
        "user_id": user_id,
        "before": before,
        "after": _job_audit_snapshot(refreshed or job),
        "changed_fields": changed_fields,
        "validation_required": validation_required,
        "validation_run_id": validation_run_id,
        "evidence": dict(evidence or {}),
    }
    _record_scheduler_event(
        scheduled_job_id=job_id,
        scheduled_run_id=validation_run_id,
        trace_id=(
            str((_get_run(validation_run_id) or {}).get("trace_id") or "") if validation_run_id is not None else ""
        )
        or None,
        event_type="job.updated",
        actor_type=actor_type,
        actor_id=actor_id or str(user_id),
        source=source,
        status_from=previous_status,
        status_to=str((refreshed or job).get("status") or previous_status),
        reason=reason,
        details=details,
    )
    return {
        "ok": True,
        "message": message,
        "job": refreshed,
        "changed_fields": changed_fields,
        "validation_required": validation_required,
        "validation_run_id": validation_run_id,
        "config_version": int((refreshed or job).get("config_version") or current_config_version),
    }


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
    trigger_type: str = "one_shot",
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
        trigger_type=trigger_type,
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


def _backfill_materialized_run_policy_snapshots(now: datetime | None = None) -> None:
    marker = _iso(now or _utcnow())
    rows = _fetchall(
        """
        SELECT id, scheduled_job_id, metadata_json
        FROM scheduled_job_runs
        WHERE created_at = ? AND metadata_json = ?
        """,
        (marker, "{}"),
    )
    for row in rows:
        job_id = int(row["scheduled_job_id"])
        job = _get_job(job_id)
        if job is None:
            continue
        snapshot, snapshot_json, snapshot_hash = _policy_snapshot_payload(job)
        if (
            str(job.get("policy_snapshot_hash") or "") != snapshot_hash
            or str(job.get("policy_snapshot_json") or "") != snapshot_json
        ):
            _touch_job(job_id, policy_snapshot_json=snapshot_json, policy_snapshot_hash=snapshot_hash)
        metadata = _loads_json(row.get("metadata_json"), {})
        metadata.setdefault("policy_snapshot", snapshot)
        metadata.setdefault("policy_snapshot_json", snapshot_json)
        metadata.setdefault("policy_snapshot_hash", snapshot_hash)
        _touch_run(int(row["id"]), metadata_json=_stable_dumps_json(metadata))


_ORIGINAL_MATERIALIZE_DUE_RUNS = _dispatcher_impl._materialize_due_runs


def _materialize_due_runs(now: datetime | None = None) -> int:
    materialized = _ORIGINAL_MATERIALIZE_DUE_RUNS(now)
    with contextlib.suppress(Exception):
        _backfill_materialized_run_policy_snapshots(now)
    return materialized


_dispatcher_impl._materialize_due_runs = _materialize_due_runs


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
