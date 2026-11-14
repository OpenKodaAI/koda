"""End-to-end scheduler tests against a real PostgreSQL database.

Pinned guarantees:

  * A job validates, activates, and then fires automatically through the real
    dispatcher (materialize -> claim -> dispatch). Automatic runs carry the
    policy snapshot the dispatch gate requires, so they are not blocked as
    "policy snapshot is missing".
  * ``POST /api/runtime/schedules`` queues a validation run for the new job
    instead of attempting an activation that the scheduler always rejects, and
    the queued validation activates the job when it passes.
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
            "job_type": "agent_query",
            "trigger_type": "cron",
            "schedule_expr": "0 9 * * *",
            "timezone": "UTC",
            "payload": {"query": "Summarize open incidents", "name": "Incident digest"},
            "auto_activate": False,
        }
    )

    assert status == 201, payload
    job_id = int(payload["job"]["id"])
    assert payload["job"]["status"] == scheduled_jobs.JOB_STATUS_VALIDATION_PENDING
    [validation_run] = _runs(job_id, scheduled_jobs.RUN_TRIGGER_MANUAL_TEST)
    assert payload["validation_run_id"] == validation_run["id"]
    assert validation_run["metadata"]["activate_on_success"] is False
