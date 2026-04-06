"""Focused scheduler domain tests for updates, validation, and execution gating."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

from koda.services import scheduled_jobs


def _job_fixture(**overrides: object) -> dict[str, object]:
    payload = {
        "query": "Check deploy health",
        "provider": "claude",
        "model": "claude-sonnet-4-6",
        "work_dir": "/tmp",
    }
    verification_policy = {"mode": "post_write_if_any"}
    notification_policy = {"mode": "summary_complete"}
    job: dict[str, object] = {
        "id": 7,
        "user_id": 111,
        "chat_id": 222,
        "agent_id": "AGENT_A",
        "job_type": "agent_query",
        "trigger_type": "interval",
        "schedule_expr": "3600",
        "timezone": "UTC",
        "payload": payload,
        "payload_json": json.dumps(payload, ensure_ascii=True),
        "status": scheduled_jobs.JOB_STATUS_ACTIVE,
        "safety_mode": "dry_run_required",
        "dry_run_required": True,
        "verification_policy": verification_policy,
        "verification_policy_json": json.dumps(verification_policy, ensure_ascii=True),
        "notification_policy": notification_policy,
        "notification_policy_json": json.dumps(notification_policy, ensure_ascii=True),
        "provider_preference": "claude",
        "model_preference": "claude-sonnet-4-6",
        "work_dir": "/tmp",
        "next_run_at": "2026-03-30T14:00:00+00:00",
        "last_run_at": None,
        "last_success_at": None,
        "last_failure_at": None,
        "config_version": 1,
    }
    job.update(overrides)
    snapshot, snapshot_json, snapshot_hash = scheduled_jobs._policy_snapshot_payload(job)
    job["policy_snapshot"] = snapshot
    job["policy_snapshot_json"] = snapshot_json
    job["policy_snapshot_hash"] = snapshot_hash
    return job


def test_update_job_returns_no_changes_without_revalidation() -> None:
    job = _job_fixture()

    with (
        patch("koda.services.scheduled_jobs._get_job", return_value=job),
        patch(
            "koda.services.scheduled_jobs.validate_work_dir",
            return_value=SimpleNamespace(ok=True, path="/tmp"),
        ),
        patch("koda.services.scheduled_jobs._touch_job") as touch_job,
        patch("koda.services.scheduled_jobs._record_scheduler_event") as record_event,
        patch("koda.services.scheduled_jobs.queue_validation_run") as queue_validation,
        patch("koda.services.scheduled_jobs._suppress_pending_runs") as suppress_runs,
        patch("koda.services.scheduled_jobs._mark_running_runs", return_value=[]) as mark_running,
        patch("koda.services.scheduled_jobs._request_task_cancellations") as request_cancellations,
    ):
        result = scheduled_jobs.update_job(
            7,
            user_id=111,
            patch={
                "trigger_type": "interval",
                "schedule_expr": "3600",
                "timezone": "UTC",
                "query": "Check deploy health",
                "work_dir": "/tmp",
                "provider": "claude",
                "model": "claude-sonnet-4-6",
                "notification_policy": {"mode": "summary_complete"},
                "verification_policy": {"mode": "post_write_if_any"},
            },
            expected_config_version=1,
        )

    assert result["ok"] is True
    assert result["message"] == "No changes detected."
    assert result["changed_fields"] == []
    assert result["config_version"] == 1
    touch_job.assert_not_called()
    record_event.assert_not_called()
    queue_validation.assert_not_called()
    suppress_runs.assert_not_called()
    mark_running.assert_not_called()
    request_cancellations.assert_not_called()


def test_update_job_queues_validation_for_execution_changes() -> None:
    original = _job_fixture()
    refreshed = _job_fixture(
        payload={
            "query": "Check deploy health in more detail",
            "provider": "claude",
            "model": "claude-sonnet-4-6",
            "work_dir": "/tmp",
        },
        payload_json=json.dumps(
            {
                "query": "Check deploy health in more detail",
                "provider": "claude",
                "model": "claude-sonnet-4-6",
                "work_dir": "/tmp",
            },
            ensure_ascii=True,
        ),
        status=scheduled_jobs.JOB_STATUS_VALIDATION_PENDING,
        config_version=2,
        next_run_at=None,
    )

    with (
        patch("koda.services.scheduled_jobs._get_job", side_effect=[original, refreshed]),
        patch("koda.services.scheduled_jobs._get_run", return_value={"trace_id": "schedrun_trace_1"}),
        patch(
            "koda.services.scheduled_jobs.validate_work_dir",
            return_value=SimpleNamespace(ok=True, path="/tmp"),
        ),
        patch("koda.services.scheduled_jobs._touch_job") as touch_job,
        patch("koda.services.scheduled_jobs._suppress_pending_runs") as suppress_runs,
        patch("koda.services.scheduled_jobs._mark_running_runs", return_value=[444]) as mark_running,
        patch("koda.services.scheduled_jobs._request_task_cancellations") as request_cancellations,
        patch("koda.services.scheduled_jobs._persist_job_policy_snapshot") as persist_snapshot,
        patch(
            "koda.services.scheduled_jobs.queue_validation_run",
            return_value=(88, "Validation queued."),
        ) as queue_validation,
        patch("koda.services.scheduled_jobs._record_scheduler_event") as record_event,
    ):
        result = scheduled_jobs.update_job(
            7,
            user_id=111,
            patch={"query": "Check deploy health in more detail"},
            expected_config_version=1,
            reason="Requested by operator",
            evidence={"channel": "dashboard"},
        )

    assert result["ok"] is True
    assert result["validation_required"] is True
    assert result["validation_run_id"] == 88
    assert result["config_version"] == 2
    queue_validation.assert_called_once_with(
        7,
        user_id=111,
        activate_on_success=True,
        status_before_validation=scheduled_jobs.JOB_STATUS_ACTIVE,
        allow_existing_active_run=True,
    )
    assert touch_job.call_args.kwargs["status"] == scheduled_jobs.JOB_STATUS_VALIDATION_PENDING
    assert touch_job.call_args.kwargs["next_run_at"] is None
    assert touch_job.call_args.kwargs["config_version"] == 2
    suppress_runs.assert_called_once_with(
        7,
        status=scheduled_jobs.RUN_STATUS_CANCELLED,
        error_message="Job configuration updated before execution.",
    )
    mark_running.assert_called_once_with(
        7,
        disposition=scheduled_jobs.RUN_STATUS_CANCELLED,
        reason="Job configuration updated during execution.",
    )
    request_cancellations.assert_called_once_with([444], reason="Job configuration updated during execution.")
    assert record_event.call_args.kwargs["event_type"] == "job.updated"
    assert record_event.call_args.kwargs["scheduled_run_id"] == 88
    assert record_event.call_args.kwargs["details"]["changed_fields"] == [
        "payload_json",
    ]
    persist_snapshot.assert_not_called()


def test_run_job_now_rejects_job_that_is_not_validated() -> None:
    with patch(
        "koda.services.scheduled_jobs._get_job",
        return_value=_job_fixture(status=scheduled_jobs.JOB_STATUS_VALIDATION_PENDING),
    ):
        run_id, message = scheduled_jobs.run_job_now(7, user_id=111)

    assert run_id is None
    assert message == "Job must be validated before manual execution."


def test_queue_validation_run_can_be_staged_while_previous_run_is_cancelling() -> None:
    job = _job_fixture(status=scheduled_jobs.JOB_STATUS_VALIDATION_PENDING)

    with (
        patch("koda.services.scheduled_jobs._get_job", return_value=job),
        patch("koda.services.scheduled_jobs._has_open_validation_run", return_value=False),
        patch("koda.services.scheduled_jobs._has_open_run", return_value=True),
        patch("koda.services.scheduled_jobs.create_run", return_value=91) as create_run,
        patch("koda.services.scheduled_jobs._touch_job") as touch_job,
        patch("koda.services.scheduled_jobs._get_run", return_value={"trace_id": "schedrun_trace_91"}),
        patch("koda.services.scheduled_jobs._record_scheduler_event") as record_event,
        patch("koda.services.scheduled_jobs.wake_dispatcher") as wake_dispatcher,
        patch("koda.services.scheduled_jobs._persist_job_policy_snapshot") as persist_snapshot,
    ):
        run_id, message = scheduled_jobs.queue_validation_run(
            7,
            user_id=111,
            activate_on_success=True,
            status_before_validation=scheduled_jobs.JOB_STATUS_ACTIVE,
            allow_existing_active_run=True,
        )

    assert run_id == 91
    assert "Validation queued" in message
    touch_job.assert_called_once_with(7, last_validation_run_id=91)
    persist_snapshot.assert_called_once()
    create_run.assert_called_once()
    record_event.assert_called_once()
    wake_dispatcher.assert_called_once()


def test_resume_job_allows_failed_open_jobs() -> None:
    failed_open_job = _job_fixture(status=scheduled_jobs.JOB_STATUS_FAILED_OPEN)

    with (
        patch("koda.services.scheduled_jobs._get_job", return_value=failed_open_job),
        patch("koda.services.scheduled_jobs._validate_schedule_policy"),
        patch(
            "koda.services.scheduled_jobs.compute_next_run",
            return_value=scheduled_jobs._parse_dt("2026-03-30T15:00:00+00:00"),
        ),
        patch("koda.services.scheduled_jobs._touch_job") as touch_job,
        patch("koda.services.scheduled_jobs._record_scheduler_event") as record_event,
        patch("koda.services.scheduled_jobs.wake_dispatcher") as wake_dispatcher,
    ):
        ok, message = scheduled_jobs.resume_job(7, user_id=111)

    assert ok is True
    assert message == "Job activated."
    assert touch_job.call_args.kwargs["status"] == scheduled_jobs.JOB_STATUS_ACTIVE
    assert record_event.call_args.kwargs["event_type"] == "job.activated"
    wake_dispatcher.assert_called_once()


def test_create_run_embeds_policy_snapshot_metadata() -> None:
    job = _job_fixture()

    with (
        patch("koda.services.scheduled_jobs._get_job", return_value=job),
        patch("koda.services.scheduled_jobs._insert_returning_id", return_value=123) as insert_run,
        patch("koda.services.scheduled_jobs._record_scheduler_event") as record_event,
    ):
        run_id = scheduled_jobs.create_run(scheduled_job_id=7, trigger_reason=scheduled_jobs.RUN_TRIGGER_MANUAL_RUN)

    assert run_id == 123
    metadata_json = insert_run.call_args.args[1][6]
    metadata = json.loads(metadata_json)
    assert metadata["policy_snapshot_hash"] == job["policy_snapshot_hash"]
    assert metadata["policy_snapshot"]["allowed_tool_ids"] == job["policy_snapshot"]["allowed_tool_ids"]
    record_event.assert_called_once()


def test_backfill_materialized_run_policy_snapshots_attaches_snapshot_metadata() -> None:
    now = scheduled_jobs._parse_dt("2026-03-30T12:00:00+00:00")
    job = _job_fixture()

    with (
        patch(
            "koda.services.scheduled_jobs._fetchall",
            return_value=[{"id": 501, "scheduled_job_id": 7, "metadata_json": "{}"}],
        ),
        patch("koda.services.scheduled_jobs._get_job", return_value=job),
        patch("koda.services.scheduled_jobs._touch_job") as touch_job,
        patch("koda.services.scheduled_jobs._touch_run") as touch_run,
    ):
        scheduled_jobs._backfill_materialized_run_policy_snapshots(now)

    touch_job.assert_not_called()
    touch_run.assert_called_once()
    metadata = json.loads(touch_run.call_args.kwargs["metadata_json"])
    assert metadata["policy_snapshot_hash"] == job["policy_snapshot_hash"]
    assert metadata["policy_snapshot"]["allowed_tool_ids"] == job["policy_snapshot"]["allowed_tool_ids"]
