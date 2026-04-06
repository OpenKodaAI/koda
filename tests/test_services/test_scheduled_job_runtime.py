"""Focused tests for scheduled run policy-drift revalidation."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, patch

import pytest

from koda.services import scheduled_job_runtime, scheduled_jobs


def _job_fixture() -> dict[str, object]:
    payload = {
        "query": "Check deploy health",
        "provider": "claude",
        "model": "claude-sonnet-4-6",
        "work_dir": "/tmp",
    }
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
        "payload_json": "{}",
        "status": scheduled_jobs.JOB_STATUS_ACTIVE,
        "provider_preference": "claude",
        "model_preference": "claude-sonnet-4-6",
        "work_dir": "/tmp",
    }
    job["payload_json"] = scheduled_jobs._dumps_json(payload)
    snapshot, snapshot_json, snapshot_hash = scheduled_jobs._policy_snapshot_payload(job)
    job["policy_snapshot"] = snapshot
    job["policy_snapshot_json"] = snapshot_json
    job["policy_snapshot_hash"] = snapshot_hash
    return job


@pytest.mark.asyncio
async def test_dispatch_run_blocks_when_policy_snapshot_changed() -> None:
    job = _job_fixture()
    stale_snapshot = dict(job["policy_snapshot"])  # type: ignore[arg-type]
    stale_snapshot["work_dir"] = "/tmp/elsewhere"
    run = {
        "id": 11,
        "trace_id": "schedrun_trace_11",
        "trigger_reason": scheduled_jobs.RUN_TRIGGER_NORMAL,
        "metadata": {
            "policy_snapshot": stale_snapshot,
            "policy_snapshot_json": scheduled_jobs._stable_dumps_json(stale_snapshot),
            "policy_snapshot_hash": "stale_hash",
        },
        "job": job,
    }
    application = SimpleNamespace(bot=AsyncMock())

    with (
        patch("koda.services.scheduled_job_runtime._dispatch_agent_query", new=AsyncMock()) as dispatch_agent_query,
        patch("koda.services.scheduled_job_runtime._dispatch_reminder", new=AsyncMock()) as dispatch_reminder,
        patch("koda.services.scheduled_job_runtime._dispatch_shell_command", new=AsyncMock()) as dispatch_shell_command,
        patch("koda.services.scheduled_job_runtime._notify_run", new=AsyncMock()) as notify_run,
        patch("koda.services.scheduled_jobs._transition_run", return_value=True) as transition_run,
        patch("koda.services.scheduled_jobs._touch_job") as touch_job,
        patch("koda.services.scheduled_jobs._suppress_pending_runs") as suppress_runs,
        patch("koda.services.scheduled_jobs._record_scheduler_event") as record_event,
    ):
        await scheduled_job_runtime._dispatch_run(application, run)

    dispatch_agent_query.assert_not_called()
    dispatch_reminder.assert_not_called()
    dispatch_shell_command.assert_not_called()
    transition_run.assert_called_once()
    assert transition_run.call_args.kwargs["status"] == scheduled_jobs.RUN_STATUS_BLOCKED
    assert transition_run.call_args.kwargs["verification_status"] == "blocked_by_policy"
    touch_job.assert_called_once_with(
        7,
        status=scheduled_jobs.JOB_STATUS_VALIDATION_PENDING,
        next_run_at=None,
        last_failure_at=ANY,
    )
    suppress_runs.assert_called_once_with(
        7,
        status=scheduled_jobs.RUN_STATUS_BLOCKED,
        error_message="Scheduled run blocked because the job policy changed after validation.",
    )
    assert record_event.call_args.kwargs["event_type"] == "run.blocked_by_policy"
    notify_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_shell_command_uses_central_execution_policy() -> None:
    payload = {"command": "ls -la", "work_dir": "/tmp"}
    job: dict[str, object] = {
        "id": 13,
        "user_id": 111,
        "chat_id": 222,
        "agent_id": "AGENT_A",
        "job_type": "shell_command",
        "trigger_type": "interval",
        "schedule_expr": "3600",
        "timezone": "UTC",
        "payload": payload,
        "payload_json": scheduled_jobs._dumps_json(payload),
        "status": scheduled_jobs.JOB_STATUS_ACTIVE,
        "provider_preference": "claude",
        "model_preference": "claude-sonnet-4-6",
        "work_dir": "/tmp",
    }

    with (
        patch("koda.services.scheduled_jobs.AGENT_TOOL_POLICY", {"allowed_tool_ids": ["shell"]}),
        patch(
            "koda.services.scheduled_jobs.AGENT_RESOURCE_ACCESS_POLICY",
            {"integration_grants": {"shell": {"allow_actions": ["shell.*"]}}},
        ),
        patch(
            "koda.services.scheduled_jobs.AGENT_EXECUTION_POLICY",
            {
                "version": 1,
                "rules": [
                    {
                        "id": "deny-shell",
                        "decision": "deny",
                        "selectors": {"tool_id": ["shell"]},
                    }
                ],
            },
        ),
    ):
        snapshot, snapshot_json, snapshot_hash = scheduled_jobs._policy_snapshot_payload(job)

    job["policy_snapshot"] = snapshot
    job["policy_snapshot_json"] = snapshot_json
    job["policy_snapshot_hash"] = snapshot_hash
    run = {
        "id": 21,
        "trace_id": "schedrun_trace_21",
        "trigger_reason": scheduled_jobs.RUN_TRIGGER_NORMAL,
        "metadata": {
            "policy_snapshot": snapshot,
            "policy_snapshot_json": snapshot_json,
            "policy_snapshot_hash": snapshot_hash,
        },
        "job": job,
    }
    application = SimpleNamespace(bot=AsyncMock())

    with (
        patch("koda.services.scheduled_job_runtime.handle_run_failure", new=AsyncMock()) as handle_failure,
        patch("koda.services.scheduled_job_runtime.handle_run_success", new=AsyncMock()) as handle_success,
        patch("koda.services.scheduled_job_runtime._notify_run", new=AsyncMock()),
        patch("koda.services.shell_runner.run_shell_command", new=AsyncMock()) as run_shell_command,
    ):
        await scheduled_job_runtime._dispatch_shell_command(application, run)

    handle_failure.assert_awaited_once()
    handle_success.assert_not_awaited()
    run_shell_command.assert_not_awaited()
    assert "execution policy" in handle_failure.await_args.kwargs["notification_summary"].lower()
