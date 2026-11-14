"""End-to-end scheduler tests against a real PostgreSQL database.

Pinned guarantees:

  * A job validates, activates, and then fires automatically through the real
    dispatcher (materialize -> claim -> dispatch). Automatic runs carry the
    policy snapshot the dispatch gate requires, so they are not blocked as
    "policy snapshot is missing".
  * Automatic runs follow the agent's current policy: a job whose stored
    snapshot went stale since validation is refreshed (and the refresh is
    recorded as ``job.policy_snapshot_refreshed``) only through a
    compare-and-swap, so a concurrent edit is never overwritten.
  * ``POST /api/runtime/schedules`` queues a validation run for the new job
    instead of attempting an activation that the scheduler always rejects, and
    the queued validation activates the job when it passes (or leaves it
    ``validated`` when ``auto_activate`` is false).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

pytestmark = [pytest.mark.postgres]

_SCHEDULER_TABLES = ("scheduled_job_events", "scheduled_job_runs", "scheduled_jobs")


def _stop_primary_bridge() -> None:
    """Stop the sync->async bridge thread these tests start, so later tests run without it."""
    from koda.knowledge.v2 import common as common_mod
    from koda.state import primary as primary_mod

    loop = primary_mod._active_bridge_loop()
    if loop is not None:
        for backend in list(common_mod._SHARED_POSTGRES_BACKENDS.values()):
            future = asyncio.run_coroutine_threadsafe(backend.close(), loop)
            try:
                future.result(timeout=10)
            except Exception:
                future.cancel()
        loop.call_soon_threadsafe(loop.stop)
        thread = primary_mod._BRIDGE_THREAD
        if thread is not None:
            thread.join(timeout=10)
        with primary_mod._BRIDGE_LOCK:
            primary_mod._BRIDGE_LOOP = None
            primary_mod._BRIDGE_THREAD = None
            primary_mod._BRIDGE_OWNER_PID = None
    common_mod._SHARED_POSTGRES_BACKENDS.clear()


@pytest.fixture
async def scheduler_db(migrated_postgres: str) -> AsyncIterator[str]:
    from koda.knowledge.v2 import common as common_mod

    common_mod._SHARED_POSTGRES_BACKENDS.clear()
    conn = await asyncpg.connect(migrated_postgres)
    try:
        tables = ", ".join(f'knowledge_v2."{name}"' for name in _SCHEDULER_TABLES)
        await conn.execute(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE")
    finally:
        await conn.close()
    try:
        yield migrated_postgres
    finally:
        _stop_primary_bridge()


async def _run_dispatch_cycle(application: Any) -> dict[str, int]:
    from koda.services import scheduled_job_dispatcher, scheduled_jobs

    result = await scheduled_jobs.run_dispatch_cycle(application)
    await asyncio.gather(*list(scheduled_job_dispatcher._inflight_dispatch_tasks))
    return result


def _runs(job_id: int, trigger_reason: str) -> list[dict[str, Any]]:
    from koda.services import scheduled_jobs

    rows = scheduled_jobs._fetchall(
        "SELECT * FROM scheduled_job_runs WHERE scheduled_job_id = ? AND trigger_reason = ? ORDER BY id ASC",
        (job_id, trigger_reason),
    )
    return [scheduled_jobs._normalize_run(row) or {} for row in rows]


def _fake_application() -> SimpleNamespace:
    return SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))


def _events(job_id: int, event_type: str) -> list[dict[str, Any]]:
    from koda.services import scheduled_jobs

    return [event for event in scheduled_jobs.list_job_events(job_id, limit=200) if event["event_type"] == event_type]


async def _active_reminder_job(application: Any) -> int:
    """Create a reminder job and let its dry-run validation activate it."""
    from koda.services import scheduled_jobs

    job_id = scheduled_jobs.create_reminder_job(
        user_id=111,
        chat_id=222,
        trigger_type="interval",
        schedule_expr="3600",
        text="Stretch break",
    )
    await _run_dispatch_cycle(application)
    job = scheduled_jobs._get_job(job_id)
    assert job is not None and job["status"] == scheduled_jobs.JOB_STATUS_ACTIVE
    return job_id


async def test_reminder_validates_activates_and_fires_automatically(scheduler_db: str) -> None:
    from koda.services import scheduled_jobs

    application = _fake_application()
    job_id = scheduled_jobs.create_reminder_job(
        user_id=111,
        chat_id=222,
        trigger_type="interval",
        schedule_expr="3600",
        text="Stretch break",
    )

    # Cycle 1 dispatches the queued dry-run validation, which activates the job.
    await _run_dispatch_cycle(application)
    job = scheduled_jobs._get_job(job_id)
    assert job is not None
    assert job["status"] == scheduled_jobs.JOB_STATUS_ACTIVE
    [validation_run] = _runs(job_id, scheduled_jobs.RUN_TRIGGER_MANUAL_TEST)
    assert validation_run["status"] == scheduled_jobs.RUN_STATUS_SUCCEEDED

    # Make the active job due, then let the dispatcher materialize and run it.
    due_at = scheduled_jobs._utcnow() - timedelta(seconds=5)
    scheduled_jobs._touch_job(job_id, next_run_at=scheduled_jobs._iso(due_at))
    cycle = await _run_dispatch_cycle(application)
    assert cycle["materialized"] == 1
    assert cycle["claimed"] == 1

    [automatic_run] = _runs(job_id, scheduled_jobs.RUN_TRIGGER_NORMAL)
    assert automatic_run["status"] == scheduled_jobs.RUN_STATUS_SUCCEEDED, automatic_run.get("error_message")
    assert automatic_run["verification_status"] == "verified"
    _, _, expected_hash = scheduled_jobs._policy_snapshot_payload(job)
    assert automatic_run["metadata"]["policy_snapshot_hash"] == expected_hash
    assert isinstance(automatic_run["metadata"]["policy_snapshot"], dict)
    application.bot.send_message.assert_any_await(chat_id=222, text="⏰ Reminder: Stretch break")

    job_after = scheduled_jobs._get_job(job_id)
    assert job_after is not None
    assert job_after["status"] == scheduled_jobs.JOB_STATUS_ACTIVE
    assert job_after["policy_snapshot_hash"] == expected_hash
    next_run_at = scheduled_jobs._parse_dt(job_after["next_run_at"])
    assert next_run_at is not None and next_run_at > scheduled_jobs._utcnow()


async def test_automatic_run_follows_current_agent_policy_and_records_snapshot_refresh(scheduler_db: str) -> None:
    from koda.services import scheduled_jobs

    application = _fake_application()
    job_id = await _active_reminder_job(application)
    validated_job = scheduled_jobs._get_job(job_id)
    assert validated_job is not None
    validated_hash = validated_job["policy_snapshot_hash"]

    # The agent's execution policy changes after the job was validated.
    due_at = scheduled_jobs._utcnow() - timedelta(seconds=5)
    scheduled_jobs._touch_job(job_id, next_run_at=scheduled_jobs._iso(due_at))
    with patch.object(scheduled_jobs, "AGENT_EXECUTION_POLICY", {"approval_mode": "changed-after-validation"}):
        _, _, current_hash = scheduled_jobs._policy_snapshot_payload(validated_job)
        assert current_hash != validated_hash
        cycle = await _run_dispatch_cycle(application)

    assert cycle["materialized"] == 1
    [automatic_run] = _runs(job_id, scheduled_jobs.RUN_TRIGGER_NORMAL)
    assert automatic_run["status"] == scheduled_jobs.RUN_STATUS_SUCCEEDED, automatic_run.get("error_message")
    assert automatic_run["metadata"]["policy_snapshot_hash"] == current_hash

    job_after = scheduled_jobs._get_job(job_id)
    assert job_after is not None
    assert job_after["policy_snapshot_hash"] == current_hash
    [refresh_event] = _events(job_id, "job.policy_snapshot_refreshed")
    assert refresh_event["source"] == "scheduler_dispatcher"
    assert refresh_event["details"] == {
        "previous_policy_snapshot_hash": validated_hash,
        "policy_snapshot_hash": current_hash,
    }


async def test_snapshot_refresh_does_not_overwrite_a_concurrent_job_update(scheduler_db: str) -> None:
    from koda.services import scheduled_job_dispatcher, scheduled_jobs

    job_id = await _active_reminder_job(_fake_application())
    due_at = scheduled_jobs._iso(scheduled_jobs._utcnow() - timedelta(seconds=5))
    scheduled_jobs._touch_job(
        job_id,
        next_run_at=due_at,
        policy_snapshot_json='{"stale":true}',
        policy_snapshot_hash="stale-hash",
    )
    real_store = scheduled_job_dispatcher._store()

    class _ConcurrentEditStore:
        """Lands a job edit right after the dispatcher reads the due jobs."""

        def __getattr__(self, name: str) -> Any:
            return getattr(real_store, name)

        def fetch_all(self, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
            rows = real_store.fetch_all(query, params)
            if "FROM scheduled_jobs" in query and "next_run_at <= ?" in query:
                real_store.execute(
                    "UPDATE scheduled_jobs SET config_version = config_version + 1, "
                    "policy_snapshot_hash = ? WHERE id = ?",
                    ("concurrent-hash", job_id),
                )
            return rows

    with patch.object(scheduled_job_dispatcher, "_store", return_value=_ConcurrentEditStore()):
        assert scheduled_job_dispatcher._materialize_due_runs() == 0

    job = scheduled_jobs._get_job(job_id)
    assert job is not None
    assert job["policy_snapshot_hash"] == "concurrent-hash"
    assert job["next_run_at"] == due_at
    assert _runs(job_id, scheduled_jobs.RUN_TRIGGER_NORMAL) == []
    assert _events(job_id, "job.policy_snapshot_refreshed") == []

    # The next cycle reads the fresh row and materializes the run.
    assert scheduled_job_dispatcher._materialize_due_runs() == 1
    [refresh_event] = _events(job_id, "job.policy_snapshot_refreshed")
    assert refresh_event["details"]["previous_policy_snapshot_hash"] == "concurrent-hash"


class _AllowRuntimeAccess:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def authorize(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"capability": "mutate"}


async def _post_schedule(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    from koda.services.runtime.api import _runtime_schedule_create

    app = web.Application()
    app.router.add_post("/api/runtime/schedules", _runtime_schedule_create)
    with (
        patch("koda.services.runtime.api.RuntimeAccessService", _AllowRuntimeAccess),
        patch("koda.services.runtime.api.RUNTIME_LOCAL_UI_TOKEN", "test-token"),
    ):
        async with TestClient(TestServer(app)) as client:
            response = await client.post(
                "/api/runtime/schedules",
                data=json.dumps(body),
                headers={"X-Runtime-Token": "any", "Content-Type": "application/json"},
            )
            return response.status, await response.json()


async def test_runtime_api_create_queues_validation_that_activates_the_job(scheduler_db: str) -> None:
    from koda.services import scheduled_jobs

    status, payload = await _post_schedule(
        {
            "job_type": "reminder",
            "trigger_type": "interval",
            "schedule_expr": "3600",
            "timezone": "UTC",
            "payload": {"text": "Weekly review", "name": "Weekly review"},
            "auto_activate": True,
            "session_id": "dashboard:AGENT_A",
        }
    )

    assert status == 201, payload
    assert payload["ok"] is True
    job_id = int(payload["job"]["id"])
    assert payload["job"]["status"] == scheduled_jobs.JOB_STATUS_VALIDATION_PENDING
    [validation_run] = _runs(job_id, scheduled_jobs.RUN_TRIGGER_MANUAL_TEST)
    assert payload["validation_run_id"] == validation_run["id"]
    assert validation_run["status"] == scheduled_jobs.RUN_STATUS_QUEUED
    assert validation_run["metadata"]["activate_on_success"] is True

    await _run_dispatch_cycle(_fake_application())

    job = scheduled_jobs._get_job(job_id)
    assert job is not None
    assert job["status"] == scheduled_jobs.JOB_STATUS_ACTIVE
    assert job["next_run_at"]


async def test_runtime_api_create_without_auto_activate_stops_at_validated(scheduler_db: str) -> None:
    from koda.services import scheduled_jobs

    status, payload = await _post_schedule(
        {
            "job_type": "reminder",
            "trigger_type": "interval",
            "schedule_expr": "3600",
            "timezone": "UTC",
            "payload": {"text": "Incident digest", "name": "Incident digest"},
            "auto_activate": False,
        }
    )

    assert status == 201, payload
    job_id = int(payload["job"]["id"])
    assert payload["job"]["status"] == scheduled_jobs.JOB_STATUS_VALIDATION_PENDING
    [validation_run] = _runs(job_id, scheduled_jobs.RUN_TRIGGER_MANUAL_TEST)
    assert payload["validation_run_id"] == validation_run["id"]
    assert validation_run["metadata"]["activate_on_success"] is False

    await _run_dispatch_cycle(_fake_application())

    [validation_run] = _runs(job_id, scheduled_jobs.RUN_TRIGGER_MANUAL_TEST)
    assert validation_run["status"] == scheduled_jobs.RUN_STATUS_SUCCEEDED, validation_run.get("error_message")
    job = scheduled_jobs._get_job(job_id)
    assert job is not None
    assert job["status"] == scheduled_jobs.JOB_STATUS_VALIDATED
    assert job["next_run_at"] is None
