"""Scheduler runtime execution, transitions, and notifications."""

from __future__ import annotations

import contextlib
from collections.abc import Mapping
from datetime import timedelta
from typing import Any, cast

from koda.logging_config import get_logger

log = get_logger(__name__)


def _jobs() -> Any:
    from koda.services import scheduled_jobs

    return scheduled_jobs


async def _dispatch_run(application: Any, run: dict[str, Any]) -> None:
    job = run["job"]
    try:
        blocked_reason = _policy_snapshot_drift_reason(run)
        if blocked_reason:
            await _block_run_due_to_policy_drift(
                application=application,
                run=run,
                reason=blocked_reason,
            )
            return
        if job["job_type"] == "agent_query":
            await _dispatch_agent_query(application, run)
        elif job["job_type"] == "reminder":
            await _dispatch_reminder(application, run)
        else:
            await _dispatch_shell_command(application, run)
    except Exception as exc:
        log.exception("scheduled_run_dispatch_error", run_id=run["id"], job_id=job["id"])
        await handle_run_failure(
            run_id=run["id"],
            task_id=None,
            error_message=str(exc),
            provider_effective=None,
            model_effective=None,
            duration_ms=None,
            verification_status="failed",
            notification_summary=None,
            notification_chat_id=job["chat_id"],
            telegram_bot=getattr(application, "bot", None),
        )


def _policy_snapshot_drift_reason(run: dict[str, Any]) -> str | None:
    jobs = _jobs()
    job = run["job"]
    metadata = run.get("metadata") or {}
    stored_hash = str(metadata.get("policy_snapshot_hash") or "").strip()
    stored_snapshot = metadata.get("policy_snapshot")
    if not stored_hash or not isinstance(stored_snapshot, dict):
        return "Scheduled run blocked because its policy snapshot is missing."
    _, _, snapshot_hash = jobs._policy_snapshot_payload(job)
    if not snapshot_hash:
        return "Scheduled run blocked because policy snapshot could not be resolved."
    if stored_hash != snapshot_hash:
        return "Scheduled run blocked because the job policy changed after validation."
    return None


async def _block_run_due_to_policy_drift(*, application: Any, run: dict[str, Any], reason: str) -> None:
    jobs = _jobs()
    job = run["job"]
    now = jobs._utcnow()
    transitioned = jobs._transition_run(
        int(run["id"]),
        from_statuses={jobs.RUN_STATUS_RUNNING},
        status=jobs.RUN_STATUS_BLOCKED,
        completed_at=jobs._iso(now),
        verification_status="blocked_by_policy",
        summary_text=reason,
        error_message=reason,
        lease_owner=None,
        lease_expires_at=None,
        next_attempt_at=None,
    )
    if not transitioned:
        return
    jobs._touch_job(
        int(job["id"]),
        status=jobs.JOB_STATUS_VALIDATION_PENDING,
        next_run_at=None,
        last_failure_at=jobs._iso(now),
    )
    jobs._suppress_pending_runs(
        int(job["id"]),
        status=jobs.RUN_STATUS_BLOCKED,
        error_message=reason,
    )
    jobs._record_scheduler_event(
        scheduled_job_id=int(job["id"]),
        scheduled_run_id=int(run["id"]),
        trace_id=str(run.get("trace_id") or "") or None,
        event_type="run.blocked_by_policy",
        source="scheduler_runtime",
        status_from=jobs.RUN_STATUS_RUNNING,
        status_to=jobs.RUN_STATUS_BLOCKED,
        reason=reason,
        details={"trigger_reason": run.get("trigger_reason")},
    )
    await _notify_run(
        telegram_bot=application.bot,
        chat_id=int(job["chat_id"]),
        job=job,
        run={
            **run,
            "status": jobs.RUN_STATUS_BLOCKED,
            "verification_status": "blocked_by_policy",
            "completed_at": jobs._iso(now),
            "error_message": reason,
            "summary_text": reason,
        },
        summary_text=reason,
        notification_status_on_success="sent",
    )


async def _dispatch_agent_query(application: Any, run: dict[str, Any]) -> None:
    jobs = _jobs()
    from koda.services.queue_manager import build_runtime_context, enqueue_scheduled_run

    job = run["job"]
    payload = job["payload"]
    context = build_runtime_context(application, int(job["user_id"]))
    task_id = await enqueue_scheduled_run(
        user_id=int(job["user_id"]),
        chat_id=int(job["chat_id"]),
        context=context,
        query_text=str(payload.get("query") or ""),
        scheduled_job_id=int(job["id"]),
        scheduled_run_id=int(run["id"]),
        dry_run=str(run["trigger_reason"]) == jobs.RUN_TRIGGER_MANUAL_TEST,
        provider=str(job.get("provider_preference") or payload.get("provider") or jobs.DEFAULT_PROVIDER),
        model=str(job.get("model_preference") or payload.get("model") or ""),
        work_dir=str(job.get("work_dir") or payload.get("work_dir") or jobs.DEFAULT_WORK_DIR),
        session_id=payload.get("session_id"),
        trigger_reason=str(run["trigger_reason"]),
    )
    jobs._touch_run(
        int(run["id"]),
        task_id=task_id,
        provider_effective=job.get("provider_preference"),
        model_effective=job.get("model_preference"),
        lease_heartbeat_at=jobs._iso(jobs._utcnow()),
    )
    jobs._record_scheduler_event(
        scheduled_job_id=int(job["id"]),
        scheduled_run_id=int(run["id"]),
        trace_id=str(run.get("trace_id") or "") or None,
        event_type="run.dispatched",
        source="scheduler_runtime",
        details={"task_id": task_id, "provider": job.get("provider_preference"), "model": job.get("model_preference")},
    )


async def _dispatch_reminder(application: Any, run: dict[str, Any]) -> None:
    jobs = _jobs()
    job = run["job"]
    payload = job["payload"]
    text = str(payload.get("text") or "").strip()
    summary = (
        "Reminder validation passed."
        if run["trigger_reason"] == jobs.RUN_TRIGGER_MANUAL_TEST
        else f"Reminder sent: {text}"
    )
    if run["trigger_reason"] != jobs.RUN_TRIGGER_MANUAL_TEST:
        await application.bot.send_message(chat_id=job["chat_id"], text=f"⏰ Reminder: {text}")
    await handle_run_success(
        run_id=int(run["id"]),
        task_id=None,
        provider_effective=None,
        model_effective=None,
        duration_ms=0.0,
        verification_status="verified",
        summary_text=summary,
        fallback_chain=[],
        artifacts=[],
        telegram_bot=application.bot,
        notification_chat_id=int(job["chat_id"]),
    )


async def _dispatch_shell_command(application: Any, run: dict[str, Any]) -> None:
    jobs = _jobs()
    from koda.agent_contract import evaluate_integration_grant
    from koda.knowledge.task_policy_defaults import default_execution_policy
    from koda.services.execution_policy import evaluate_execution_policy
    from koda.services.shell_runner import run_shell_command
    from koda.utils.approval import _execution_approved
    from koda.utils.formatting import escape_html

    job = run["job"]
    payload = job["payload"]
    command = str(payload.get("command") or "")
    if jobs.GIT_META_CHARS.search(command) or jobs.BLOCKED_SHELL_PATTERN.search(command):
        await handle_run_failure(
            run_id=int(run["id"]),
            task_id=None,
            error_message="Blocked by shell security policy.",
            provider_effective=None,
            model_effective=None,
            duration_ms=0.0,
            verification_status="blocked",
            notification_summary="Scheduled shell command blocked by security policy.",
            notification_chat_id=int(job["chat_id"]),
            telegram_bot=application.bot,
        )
        return
    if not job.get("migration_source") and not jobs.is_read_only_shell_command(command):
        await handle_run_failure(
            run_id=int(run["id"]),
            task_id=None,
            error_message="Scheduled shell command requires a read-only command for safe execution.",
            provider_effective=None,
            model_effective=None,
            duration_ms=0.0,
            verification_status="blocked",
            notification_summary="Scheduled shell command blocked because it is not read-only.",
            notification_chat_id=int(job["chat_id"]),
            telegram_bot=application.bot,
        )
        return
    policy_snapshot = job.get("policy_snapshot") if isinstance(job.get("policy_snapshot"), dict) else {}
    grant_decision = evaluate_integration_grant(
        "shell",
        {"args": command},
        {"integration_grants": policy_snapshot.get("integration_grants") if policy_snapshot else {}},
    )
    if not grant_decision.allowed:
        await handle_run_failure(
            run_id=int(run["id"]),
            task_id=None,
            error_message=f"Scheduled shell command blocked by integration policy ({grant_decision.reason}).",
            provider_effective=None,
            model_effective=None,
            duration_ms=0.0,
            verification_status="blocked_by_policy",
            notification_summary="Scheduled shell command blocked by integration policy.",
            notification_chat_id=int(job["chat_id"]),
            telegram_bot=application.bot,
        )
        return
    policy_evaluation = evaluate_execution_policy(
        "shell",
        {"args": command},
        task_kind="general",
        effective_policy=default_execution_policy("general"),
        tool_policy={"allowed_tool_ids": list(policy_snapshot.get("allowed_tool_ids") or [])},
        resource_access_policy={
            "integration_grants": policy_snapshot.get("integration_grants") if policy_snapshot else {}
        },
        execution_policy=(
            policy_snapshot.get("execution_policy")
            if isinstance(policy_snapshot.get("execution_policy"), dict)
            else None
        ),
        known_tool=True,
    )
    if policy_evaluation.decision != "allow":
        await handle_run_failure(
            run_id=int(run["id"]),
            task_id=None,
            error_message=f"Scheduled shell command blocked by execution policy ({policy_evaluation.reason_code}).",
            provider_effective=None,
            model_effective=None,
            duration_ms=0.0,
            verification_status="blocked_by_policy",
            notification_summary="Scheduled shell command blocked by execution policy.",
            notification_chat_id=int(job["chat_id"]),
            telegram_bot=application.bot,
        )
        return
    if run["trigger_reason"] == jobs.RUN_TRIGGER_MANUAL_TEST:
        await handle_run_success(
            run_id=int(run["id"]),
            task_id=None,
            provider_effective=None,
            model_effective=None,
            duration_ms=0.0,
            verification_status="verified",
            summary_text="Scheduled shell command validation passed.",
            fallback_chain=[],
            artifacts=[],
            telegram_bot=application.bot,
            notification_chat_id=int(job["chat_id"]),
        )
        return
    token = _execution_approved.set(True)
    started = jobs._utcnow()
    try:
        result = await run_shell_command(command, str(job.get("work_dir") or jobs.DEFAULT_WORK_DIR), timeout=60)
    finally:
        _execution_approved.reset(token)
    preview = result if len(result) <= 3000 else result[:3000] + "\n... (truncated)"
    await application.bot.send_message(
        chat_id=job["chat_id"],
        text=f"⏰ Scheduled command #{job['id']}:\n<pre>{escape_html(preview)}</pre>",
        parse_mode="HTML",
    )
    await handle_run_success(
        run_id=int(run["id"]),
        task_id=None,
        provider_effective=None,
        model_effective=None,
        duration_ms=(jobs._utcnow() - started).total_seconds() * 1000,
        verification_status="verified",
        summary_text="Scheduled shell command executed successfully.",
        fallback_chain=[],
        artifacts=[],
        telegram_bot=application.bot,
        notification_chat_id=int(job["chat_id"]),
    )


def _validated_job_status_after_manual_test(
    *,
    previous_status: str,
    success: bool,
    activate_on_success: bool,
) -> str:
    jobs = _jobs()
    if not success:
        return str(jobs.JOB_STATUS_FAILED_OPEN)
    if previous_status == jobs.JOB_STATUS_ACTIVE:
        return str(jobs.JOB_STATUS_ACTIVE)
    if previous_status == jobs.JOB_STATUS_PAUSED:
        return str(jobs.JOB_STATUS_PAUSED)
    if activate_on_success:
        return str(jobs.JOB_STATUS_ACTIVE)
    return str(jobs.JOB_STATUS_VALIDATED)


async def handle_run_cancellation(
    *,
    run_id: int,
    task_id: int | None,
    status: str,
    reason: str,
    telegram_bot: Any,
    notification_chat_id: int,
) -> None:
    """Finalize a scheduled run that was cancelled/skipped by scheduler control."""
    jobs = _jobs()
    run = jobs._get_run_with_job(run_id)
    if not run:
        return
    job = run["job"]
    now = jobs._utcnow()
    metadata = dict(run.get("metadata") or {})
    metadata[jobs._CANCELLATION_METADATA_KEY] = {
        **(metadata.get(jobs._CANCELLATION_METADATA_KEY) or {}),
        "requested": True,
        "reason": reason,
        "disposition": status,
        "finalized_at": jobs._iso(now),
    }
    transitioned = jobs._transition_run(
        run_id,
        from_statuses={jobs.RUN_STATUS_RUNNING},
        status=status,
        completed_at=jobs._iso(now),
        task_id=task_id,
        verification_status="cancelled",
        summary_text=reason,
        metadata_json=jobs._dumps_json(metadata),
        lease_owner=None,
        lease_expires_at=None,
        next_attempt_at=None,
        error_message=reason,
    )
    if not transitioned:
        return
    if run["trigger_reason"] == jobs.RUN_TRIGGER_MANUAL_TEST:
        new_status = jobs.JOB_STATUS_ARCHIVED if job["status"] == jobs.JOB_STATUS_ARCHIVED else job["status"]
        jobs._touch_job(
            int(job["id"]),
            status=new_status,
            last_run_at=jobs._iso(now),
        )
    elif job["trigger_type"] == "one_shot" and status == jobs.RUN_STATUS_CANCELLED:
        jobs._touch_job(int(job["id"]), status=jobs.JOB_STATUS_ARCHIVED, next_run_at=None, last_run_at=jobs._iso(now))
    else:
        jobs._touch_job(int(job["id"]), last_run_at=jobs._iso(now))
    jobs._record_scheduler_event(
        scheduled_job_id=int(job["id"]),
        scheduled_run_id=run_id,
        trace_id=str(run.get("trace_id") or "") or None,
        event_type="run.cancelled",
        source="scheduler_runtime",
        status_from=jobs.RUN_STATUS_RUNNING,
        status_to=status,
        reason=reason,
        details={"task_id": task_id, "notification_chat_id": notification_chat_id},
    )
    await _notify_run(
        telegram_bot=telegram_bot,
        chat_id=notification_chat_id,
        job=job,
        run={
            **run,
            "status": status,
            "verification_status": "cancelled",
            "completed_at": jobs._iso(now),
            "task_id": task_id,
            "metadata": metadata,
        },
        summary_text=reason,
        notification_status_on_success="sent",
    )


async def handle_run_success(
    *,
    run_id: int,
    task_id: int | None,
    provider_effective: str | None,
    model_effective: str | None,
    duration_ms: float | None,
    verification_status: str,
    summary_text: str | None,
    fallback_chain: list[str],
    artifacts: list[str],
    telegram_bot: Any,
    notification_chat_id: int,
) -> None:
    """Finalize a scheduled run after successful execution."""
    jobs = _jobs()
    run = jobs._get_run_with_job(run_id)
    if not run:
        return
    job = run["job"]
    override = jobs._cancellation_override(run)
    if override:
        disposition, reason = override
        await handle_run_cancellation(
            run_id=run_id,
            task_id=task_id,
            status=disposition,
            reason=reason,
            telegram_bot=telegram_bot,
            notification_chat_id=notification_chat_id,
        )
        return
    now = jobs._utcnow()
    run_status = (
        jobs.RUN_STATUS_SUCCEEDED if verification_status in {"verified", "simulated"} else jobs.RUN_STATUS_BLOCKED
    )
    notification_metadata = {
        **run.get("metadata", {}),
        "fallback_chain": fallback_chain,
        "artifacts": artifacts,
    }
    job_status = str(job["status"])
    next_run_at = job.get("next_run_at")
    transitioned = jobs._transition_run(
        run_id,
        from_statuses={jobs.RUN_STATUS_RUNNING},
        status=run_status,
        completed_at=jobs._iso(now),
        duration_ms=duration_ms,
        task_id=task_id,
        provider_effective=provider_effective,
        model_effective=model_effective,
        verification_status=verification_status,
        summary_text=summary_text,
        metadata_json=jobs._dumps_json(notification_metadata),
        lease_owner=None,
        lease_expires_at=None,
        next_attempt_at=None,
        error_message=None,
    )
    if not transitioned:
        return
    with contextlib.suppress(Exception):
        from koda.services.metrics import SCHEDULED_RUN_TRANSITIONS

        SCHEDULED_RUN_TRANSITIONS.labels(agent_id=jobs.AGENT_ID or "default", status=run_status).inc()
    if run["trigger_reason"] == jobs.RUN_TRIGGER_MANUAL_TEST:
        previous_status = str(run.get("metadata", {}).get(jobs._VALIDATION_STATUS_BEFORE_METADATA_KEY) or job["status"])
        activate_on_success = bool(run.get("metadata", {}).get(jobs._VALIDATION_AUTO_ACTIVATE_METADATA_KEY))
        job_status = _validated_job_status_after_manual_test(
            previous_status=previous_status,
            success=run_status == jobs.RUN_STATUS_SUCCEEDED,
            activate_on_success=activate_on_success,
        )
        if job_status == jobs.JOB_STATUS_ACTIVE and not next_run_at:
            with contextlib.suppress(ValueError):
                next_run_at = jobs._iso(
                    jobs._validated_next_run(
                        job_type=str(job["job_type"]),
                        trigger_type=str(job["trigger_type"]),
                        schedule_expr=str(job["schedule_expr"]),
                        timezone_name=str(job["timezone"]),
                        after=now,
                    )
                )
            if next_run_at is None and str(job["trigger_type"]) == "one_shot":
                next_run_at = jobs._iso(now)
        notification_metadata[jobs._VALIDATION_STATUS_BEFORE_METADATA_KEY] = previous_status
        notification_metadata[jobs._VALIDATION_AUTO_ACTIVATE_METADATA_KEY] = activate_on_success
        notification_metadata[jobs._VALIDATION_STATUS_AFTER_METADATA_KEY] = job_status
        notification_metadata[jobs._VALIDATION_AUTO_ACTIVATED_METADATA_KEY] = (
            job_status == jobs.JOB_STATUS_ACTIVE and previous_status != jobs.JOB_STATUS_ACTIVE
        )
        jobs._touch_run(run_id, metadata_json=jobs._dumps_json(notification_metadata))
        jobs._touch_job(
            int(job["id"]),
            status=job_status,
            last_run_at=jobs._iso(now),
            next_run_at=next_run_at if job_status == jobs.JOB_STATUS_ACTIVE else job.get("next_run_at"),
            last_validated_at=jobs._iso(now),
            last_validation_run_id=run_id,
            last_success_at=jobs._iso(now) if run_status == jobs.RUN_STATUS_SUCCEEDED else job.get("last_success_at"),
            last_failure_at=jobs._iso(now) if run_status != jobs.RUN_STATUS_SUCCEEDED else job.get("last_failure_at"),
        )
        if job_status == jobs.JOB_STATUS_FAILED_OPEN:
            jobs._suppress_automatic_runs(
                int(job["id"]),
                status=jobs.RUN_STATUS_BLOCKED,
                error_message="Job failed validation and was opened in failed state.",
            )
    else:
        updates = {
            "last_run_at": jobs._iso(now),
            "last_success_at": (
                jobs._iso(now) if run_status == jobs.RUN_STATUS_SUCCEEDED else job.get("last_success_at")
            ),
            "last_failure_at": (
                jobs._iso(now) if run_status != jobs.RUN_STATUS_SUCCEEDED else job.get("last_failure_at")
            ),
        }
        if job["trigger_type"] == "one_shot" and run_status == jobs.RUN_STATUS_SUCCEEDED:
            updates["status"] = jobs.JOB_STATUS_ARCHIVED
            updates["next_run_at"] = None
            job_status = jobs.JOB_STATUS_ARCHIVED
        jobs._touch_job(int(job["id"]), **updates)
    jobs._record_scheduler_event(
        scheduled_job_id=int(job["id"]),
        scheduled_run_id=run_id,
        trace_id=str(run.get("trace_id") or "") or None,
        event_type="run.completed" if run_status == jobs.RUN_STATUS_SUCCEEDED else "run.blocked",
        source="scheduler_runtime",
        status_from=jobs.RUN_STATUS_RUNNING,
        status_to=run_status,
        details={
            "task_id": task_id,
            "verification_status": verification_status,
            "provider_effective": provider_effective,
            "model_effective": model_effective,
            "duration_ms": duration_ms,
            "job_status": job_status,
        },
    )
    await _notify_run(
        telegram_bot=telegram_bot,
        chat_id=notification_chat_id,
        job=job,
        run={
            **run,
            "status": run_status,
            "metadata": notification_metadata,
            "verification_status": verification_status,
            "duration_ms": duration_ms,
            "task_id": task_id,
            "provider_effective": provider_effective,
            "model_effective": model_effective,
            "completed_at": jobs._iso(now),
        },
        summary_text=summary_text,
        notification_status_on_success="sent",
    )


async def handle_run_failure(
    *,
    run_id: int,
    task_id: int | None,
    error_message: str,
    provider_effective: str | None,
    model_effective: str | None,
    duration_ms: float | None,
    verification_status: str,
    notification_summary: str | None,
    notification_chat_id: int,
    telegram_bot: Any,
    dlq_id: int | None = None,
) -> None:
    """Finalize or retry a scheduled run after failure."""
    jobs = _jobs()
    run = jobs._get_run_with_job(run_id)
    if not run:
        return
    job = run["job"]
    override = jobs._cancellation_override(run)
    if override:
        disposition, reason = override
        await handle_run_cancellation(
            run_id=run_id,
            task_id=task_id,
            status=disposition,
            reason=reason,
            telegram_bot=telegram_bot,
            notification_chat_id=notification_chat_id,
        )
        return
    now = jobs._utcnow()
    attempt = int(run.get("attempt") or 0) + 1
    max_attempts = int(run.get("max_attempts") or jobs.SCHEDULER_RUN_MAX_ATTEMPTS)
    should_retry = verification_status != "blocked" and attempt < max_attempts
    terminal_status = jobs.RUN_STATUS_BLOCKED if verification_status == "blocked" else jobs.RUN_STATUS_FAILED
    if should_retry:
        next_retry = now + timedelta(seconds=_scheduler_retry_delay(attempt))
        transitioned = jobs._transition_run(
            run_id,
            from_statuses={jobs.RUN_STATUS_RUNNING},
            status=jobs.RUN_STATUS_RETRYING,
            attempt=attempt,
            next_attempt_at=jobs._iso(next_retry),
            completed_at=jobs._iso(now),
            duration_ms=duration_ms,
            task_id=task_id,
            dlq_id=dlq_id,
            provider_effective=provider_effective,
            model_effective=model_effective,
            verification_status=verification_status,
            summary_text=notification_summary,
            error_message=error_message,
            lease_owner=None,
            lease_expires_at=None,
        )
        if not transitioned:
            return
        with contextlib.suppress(Exception):
            from koda.services.metrics import SCHEDULED_RUN_TRANSITIONS

            SCHEDULED_RUN_TRANSITIONS.labels(agent_id=jobs.AGENT_ID or "default", status=jobs.RUN_STATUS_RETRYING).inc()
        jobs._touch_job(int(job["id"]), last_run_at=jobs._iso(now), last_failure_at=jobs._iso(now))
        jobs._record_scheduler_event(
            scheduled_job_id=int(job["id"]),
            scheduled_run_id=run_id,
            trace_id=str(run.get("trace_id") or "") or None,
            event_type="run.retried",
            source="scheduler_runtime",
            status_from=jobs.RUN_STATUS_RUNNING,
            status_to=jobs.RUN_STATUS_RETRYING,
            reason=error_message,
            details={"task_id": task_id, "attempt": attempt, "next_retry_at": jobs._iso(next_retry), "dlq_id": dlq_id},
        )
    else:
        transitioned = jobs._transition_run(
            run_id,
            from_statuses={jobs.RUN_STATUS_RUNNING},
            status=terminal_status,
            attempt=attempt,
            completed_at=jobs._iso(now),
            duration_ms=duration_ms,
            task_id=task_id,
            dlq_id=dlq_id,
            provider_effective=provider_effective,
            model_effective=model_effective,
            verification_status=verification_status,
            summary_text=notification_summary,
            error_message=error_message,
            lease_owner=None,
            lease_expires_at=None,
            next_attempt_at=None,
        )
        if not transitioned:
            return
        with contextlib.suppress(Exception):
            from koda.services.metrics import SCHEDULED_RUN_TRANSITIONS

            SCHEDULED_RUN_TRANSITIONS.labels(agent_id=jobs.AGENT_ID or "default", status=terminal_status).inc()
        new_job_status = jobs.JOB_STATUS_FAILED_OPEN if verification_status in {"blocked", "failed"} else job["status"]
        if run["trigger_reason"] == jobs.RUN_TRIGGER_MANUAL_TEST:
            previous_status = str(
                run.get("metadata", {}).get(jobs._VALIDATION_STATUS_BEFORE_METADATA_KEY) or job["status"]
            )
            activate_on_success = bool(run.get("metadata", {}).get(jobs._VALIDATION_AUTO_ACTIVATE_METADATA_KEY))
            new_job_status = _validated_job_status_after_manual_test(
                previous_status=previous_status,
                success=False,
                activate_on_success=activate_on_success,
            )
        jobs._touch_job(
            int(job["id"]),
            status=new_job_status,
            last_run_at=jobs._iso(now),
            last_failure_at=jobs._iso(now),
        )
        if new_job_status == jobs.JOB_STATUS_FAILED_OPEN:
            jobs._suppress_automatic_runs(
                int(job["id"]),
                status=jobs.RUN_STATUS_BLOCKED,
                error_message="Job moved to failed_open after terminal failure.",
            )
        jobs._record_scheduler_event(
            scheduled_job_id=int(job["id"]),
            scheduled_run_id=run_id,
            trace_id=str(run.get("trace_id") or "") or None,
            event_type="run.failed" if terminal_status == jobs.RUN_STATUS_FAILED else "run.blocked",
            source="scheduler_runtime",
            status_from=jobs.RUN_STATUS_RUNNING,
            status_to=terminal_status,
            reason=error_message,
            details={
                "task_id": task_id,
                "attempt": attempt,
                "verification_status": verification_status,
                "job_status": new_job_status,
                "dlq_id": dlq_id,
            },
        )
    await _notify_run(
        telegram_bot=telegram_bot,
        chat_id=notification_chat_id,
        job=job,
        run={
            **run,
            "attempt": attempt,
            "status": jobs.RUN_STATUS_RETRYING if should_retry else terminal_status,
            "verification_status": verification_status,
            "duration_ms": duration_ms,
            "task_id": task_id,
            "provider_effective": provider_effective,
            "model_effective": model_effective,
            "completed_at": jobs._iso(now),
        },
        summary_text=notification_summary or error_message,
        notification_status_on_success="sent",
        error_message=error_message,
        next_retry_at=jobs._iso(now + timedelta(seconds=_scheduler_retry_delay(attempt))) if should_retry else None,
    )


def _notification_text(
    *,
    job: Mapping[str, Any],
    run: Mapping[str, Any],
    summary_text: str | None,
    error_message: str | None = None,
    next_retry_at: str | None = None,
) -> str:
    jobs = _jobs()
    scheduled_for = jobs._parse_dt(run.get("scheduled_for"))
    started_at = jobs._parse_dt(run.get("started_at"))
    completed_at = jobs._parse_dt(run.get("completed_at"))
    planned = scheduled_for.isoformat(timespec="seconds") if scheduled_for else "unknown"
    actual = (
        completed_at.isoformat(timespec="seconds")
        if completed_at
        else (started_at.isoformat(timespec="seconds") if started_at else "unknown")
    )
    duration_ms = run.get("duration_ms")
    duration_label = f"{round(float(duration_ms) / 1000, 1)}s" if duration_ms is not None else "n/a"
    provider = run.get("provider_effective") or "n/a"
    model = run.get("model_effective") or "n/a"
    lines = [
        f"⏱ Job #{job['id']} • run #{run['id']}",
        f"Status: {run.get('status')}",
        f"Trace: {run.get('trace_id') or 'n/a'}",
        f"Planned: {planned}",
        f"Executed: {actual}",
        f"Duration: {duration_label}",
        f"Provider/model: {provider} / {model}",
        f"Verification: {run.get('verification_status')}",
        f"Task: {run.get('task_id') or 'n/a'}",
    ]
    if summary_text:
        lines.append(f"Summary: {summary_text}")
    if error_message:
        lines.append(f"Error: {error_message}")
    if next_retry_at:
        lines.append(f"Next retry: {next_retry_at}")
    metadata = run.get("metadata") or {}
    artifacts = metadata.get("artifacts") or []
    if artifacts:
        lines.append(f"Artifacts: {', '.join(str(path) for path in artifacts[:5])}")
    fallback_chain = metadata.get("fallback_chain") or []
    if fallback_chain:
        lines.append(f"Fallback: {' -> '.join(str(step) for step in fallback_chain)}")
    if run.get("trigger_reason") == jobs.RUN_TRIGGER_MANUAL_TEST and run.get("status") == jobs.RUN_STATUS_SUCCEEDED:
        if metadata.get(jobs._VALIDATION_AUTO_ACTIVATED_METADATA_KEY):
            lines.append("Ativado automaticamente apos a validacao.")
        else:
            lines.append(f"Ative com: /jobs activate {job['id']}")
    return "\n".join(lines)


def _should_notify(job: Mapping[str, Any], run: Mapping[str, Any]) -> bool:
    jobs = _jobs()
    policy = job.get("notification_policy") or jobs._loads_json(job.get("notification_policy_json"), {})
    mode = str(policy.get("mode") or jobs.SCHEDULER_NOTIFICATION_MODE)
    if mode in {"none", "silent"}:
        return False
    if mode == "failures_only":
        return str(run.get("status")) not in {jobs.RUN_STATUS_SUCCEEDED, jobs.RUN_STATUS_SKIPPED}
    return True


async def _notify_run(
    *,
    telegram_bot: Any,
    chat_id: int,
    job: Mapping[str, Any],
    run: Mapping[str, Any],
    summary_text: str | None,
    notification_status_on_success: str,
    error_message: str | None = None,
    next_retry_at: str | None = None,
) -> None:
    jobs = _jobs()
    if not _should_notify(job, run):
        jobs._touch_run(int(run["id"]), notification_status="skipped")
        return
    if telegram_bot is None:
        jobs._touch_run(int(run["id"]), notification_status="skipped")
        return
    text = _notification_text(
        job=job,
        run=run,
        summary_text=summary_text,
        error_message=error_message,
        next_retry_at=next_retry_at,
    )
    try:
        await telegram_bot.send_message(chat_id=chat_id, text=text)
        jobs._touch_run(int(run["id"]), notification_status=notification_status_on_success)
    except Exception as exc:
        log.warning("scheduled_run_notification_failed", run_id=run["id"], error=str(exc))
        with contextlib.suppress(Exception):
            from koda.services.metrics import SCHEDULED_NOTIFICATION_FAILURES

            SCHEDULED_NOTIFICATION_FAILURES.labels(agent_id=jobs.AGENT_ID or "default").inc()
        jobs._touch_run(int(run["id"]), notification_status="failed")


def derive_verification_status(
    *,
    trigger_reason: str,
    dry_run: bool,
    had_writes: bool,
    verified_before_finalize: bool,
    tool_execution_trace: list[dict[str, Any]],
    error: bool,
    error_message: str | None = None,
    verification_policy: Mapping[str, Any] | None = None,
) -> str:
    """Derive verification status for scheduler decisions."""
    jobs = _jobs()
    policy_mode = str((verification_policy or {}).get("mode") or "post_write_if_any")
    if error_message and error_message.startswith("Blocked:"):
        return "blocked"
    if error_message and "cancelled" in error_message.lower():
        return "cancelled"
    if error:
        return "failed"
    if any(step.get("metadata", {}).get("dry_run_blocked") for step in tool_execution_trace):
        return "blocked"
    if trigger_reason == jobs.RUN_TRIGGER_MANUAL_TEST or dry_run:
        return "verified"
    if policy_mode == "task_success":
        return "verified"
    if had_writes and not verified_before_finalize:
        return "failed"
    return "verified"


def _scheduler_retry_delay(attempt: int) -> int:
    jobs = _jobs()
    delay = jobs.SCHEDULER_RETRY_BASE_DELAY * (2 ** max(0, attempt - 1))
    return cast(int, min(delay, jobs.SCHEDULER_RETRY_MAX_DELAY))
