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
  * Expired-lease recovery runs in every dispatch cycle: a run whose completion
    callback was lost leaves ``running`` once its lease expires and is re-run,
    without restarting the dispatcher. A live run keeps its lease instead: one
    whose runtime task is still active, or whose dispatch is still running in
    this process, is never recovered or dispatched a second time. Each cycle
    also extends the lease of every run still dispatching in this process, so
    a second process of the same agent (an overlapping restart, a cluster
    handover) never sees that lease expire.
  * Each agent's process materializes, claims and dispatches only its own
    agent's jobs, through its own bot and under its own policy, so a job's
    policy snapshot never flips between agents. Lease recovery is scoped the
    same way: only the owning agent's process, which knows whether the dispatch
    still runs, recovers its runs. An agent's bot, tools and runtime API never
    list, validate or run another agent's job, so manual and validation runs
    carry their own agent's policy too. Jobs without an agent (created by a
    process started without AGENT_ID) are reported by every agent instead of
    being listed or queued there, and the scheduler snapshot counts only this
    agent's jobs and runs. The upgrade doc's procedure to assign such a job,
    run as written, closes its runs and keeps it running under the agent.
  * ``POST /api/runtime/schedules`` queues a validation run for the new job
    instead of attempting an activation that the scheduler always rejects, and
    the queued validation activates the job when it passes (or leaves it
    ``validated`` when ``auto_activate`` is false).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
from collections.abc import AsyncIterator, Iterator
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from tests.postgres_fixtures import close_shared_postgres_backends, stop_primary_bridge

pytestmark = [pytest.mark.postgres]

_SCHEDULER_TABLES = ("scheduled_job_events", "scheduled_job_runs", "scheduled_jobs")


@pytest.fixture
async def scheduler_db(migrated_postgres: str) -> AsyncIterator[str]:
    close_shared_postgres_backends()
    conn = await asyncpg.connect(migrated_postgres)
    try:
        tables = ", ".join(f'knowledge_v2."{name}"' for name in _SCHEDULER_TABLES)
        await conn.execute(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE")
    finally:
        await conn.close()
    try:
        yield migrated_postgres
    finally:
        stop_primary_bridge()


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


async def test_run_with_lost_callback_is_recovered_by_a_later_cycle_without_restart(scheduler_db: str) -> None:
    from koda.services import scheduled_job_runtime, scheduled_jobs

    application = _fake_application()
    job_id = await _active_reminder_job(application)
    due_at = scheduled_jobs._utcnow() - timedelta(seconds=5)
    scheduled_jobs._touch_job(job_id, next_run_at=scheduled_jobs._iso(due_at))

    # The run is claimed, but its success or failure callback never arrives.
    with patch.object(scheduled_job_runtime, "_dispatch_run", AsyncMock()):
        cycle = await _run_dispatch_cycle(application)
    assert cycle["claimed"] == 1
    [stuck_run] = _runs(job_id, scheduled_jobs.RUN_TRIGGER_NORMAL)
    assert stuck_run["status"] == scheduled_jobs.RUN_STATUS_RUNNING

    # Its lease runs out while the same dispatcher keeps cycling (no restart).
    expired_at = scheduled_jobs._utcnow() - timedelta(seconds=1)
    scheduled_jobs._touch_run(int(stuck_run["id"]), lease_expires_at=scheduled_jobs._iso(expired_at))
    await _run_dispatch_cycle(application)

    [recovered_run] = _runs(job_id, scheduled_jobs.RUN_TRIGGER_NORMAL)
    assert recovered_run["id"] == stuck_run["id"]
    assert recovered_run["lease_recovery_count"] == 1
    assert recovered_run["status"] == scheduled_jobs.RUN_STATUS_SUCCEEDED, recovered_run.get("error_message")
    [recovered_event] = _events(job_id, "run.lease_recovered")
    assert recovered_event["status_to"] == scheduled_jobs.RUN_STATUS_RETRYING


async def _claimed_normal_run(application: Any) -> tuple[int, dict[str, Any]]:
    """Activate a reminder job and claim its first automatic run without dispatching it."""
    from koda.services import scheduled_job_runtime, scheduled_jobs

    job_id = await _active_reminder_job(application)
    scheduled_jobs._touch_job(job_id, next_run_at=scheduled_jobs._iso(scheduled_jobs._utcnow() - timedelta(seconds=5)))
    with patch.object(scheduled_job_runtime, "_dispatch_run", AsyncMock()):
        assert (await _run_dispatch_cycle(application))["claimed"] == 1
    [run] = _runs(job_id, scheduled_jobs.RUN_TRIGGER_NORMAL)
    assert run["status"] == scheduled_jobs.RUN_STATUS_RUNNING
    return job_id, run


def _expire_lease(run_id: int) -> None:
    from koda.services import scheduled_jobs

    expired_at = scheduled_jobs._utcnow() - timedelta(seconds=1)
    scheduled_jobs._touch_run(run_id, lease_expires_at=scheduled_jobs._iso(expired_at))


async def test_run_with_live_runtime_task_keeps_its_lease_across_later_cycles(scheduler_db: str) -> None:
    from koda.services import scheduled_job_runtime, scheduled_jobs

    application = _fake_application()
    job_id, run = await _claimed_normal_run(application)
    run_id = int(run["id"])
    # Explicit id: other suites insert task rows with explicit ids, so the sequence can lag behind.
    task_id = int(scheduled_jobs._store().fetch_val("SELECT COALESCE(MAX(id), 0) + 1 FROM tasks"))
    scheduled_jobs._store().execute(
        "INSERT INTO tasks (id, agent_id, user_id, chat_id, status, query_text, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (task_id, "default", 111, 222, "running", "scheduled query", scheduled_jobs._iso(scheduled_jobs._utcnow())),
    )
    scheduled_jobs._touch_run(run_id, task_id=task_id)

    # The lease runs out while the runtime task is still running: a later cycle extends the lease.
    _expire_lease(run_id)
    redispatch = AsyncMock()
    with patch.object(scheduled_job_runtime, "_dispatch_run", redispatch):
        cycle = await _run_dispatch_cycle(application)

    assert cycle["claimed"] == 0
    redispatch.assert_not_called()
    [live_run] = _runs(job_id, scheduled_jobs.RUN_TRIGGER_NORMAL)
    assert live_run["status"] == scheduled_jobs.RUN_STATUS_RUNNING
    assert live_run["lease_recovery_count"] == 0
    lease_expires_at = scheduled_jobs._parse_dt(live_run["lease_expires_at"])
    assert lease_expires_at is not None and lease_expires_at > scheduled_jobs._utcnow()
    [refreshed_event] = _events(job_id, "run.lease_refreshed")
    assert refreshed_event["details"]["task_id"] == task_id
    assert _events(job_id, "run.lease_recovered") == []

    # Once the task ends without a callback, the next expired lease is recovered.
    scheduled_jobs._store().execute("UPDATE tasks SET status = ? WHERE id = ?", ("completed", task_id))
    _expire_lease(run_id)
    await _run_dispatch_cycle(application)

    [recovered_run] = _runs(job_id, scheduled_jobs.RUN_TRIGGER_NORMAL)
    assert recovered_run["lease_recovery_count"] == 1
    assert len(_events(job_id, "run.lease_recovered")) == 1


async def test_dispatch_still_running_in_this_process_is_not_recovered_and_runs_once(scheduler_db: str) -> None:
    from koda.services import scheduled_job_dispatcher, scheduled_jobs

    application = _fake_application()
    job_id = await _active_reminder_job(application)
    send_started = asyncio.Event()
    release_send = asyncio.Event()

    async def _slow_send(**_kwargs: Any) -> None:
        send_started.set()
        await release_send.wait()

    application.bot.send_message = AsyncMock(side_effect=_slow_send)
    scheduled_jobs._touch_job(job_id, next_run_at=scheduled_jobs._iso(scheduled_jobs._utcnow() - timedelta(seconds=5)))
    assert (await scheduled_jobs.run_dispatch_cycle(application))["claimed"] == 1
    await asyncio.wait_for(send_started.wait(), timeout=10)
    [run] = _runs(job_id, scheduled_jobs.RUN_TRIGGER_NORMAL)

    # The reminder's Telegram send outlives the lease (a short operator lease): the next cycle
    # must not recover the run this process is still executing, nor dispatch it a second time.
    _expire_lease(int(run["id"]))
    cycle = await scheduled_jobs.run_dispatch_cycle(application)

    assert cycle["claimed"] == 0
    [live_run] = _runs(job_id, scheduled_jobs.RUN_TRIGGER_NORMAL)
    assert live_run["status"] == scheduled_jobs.RUN_STATUS_RUNNING
    assert _events(job_id, "run.lease_recovered") == []
    assert len(_events(job_id, "run.lease_refreshed")) == 1

    release_send.set()
    await asyncio.gather(*list(scheduled_job_dispatcher._inflight_dispatch_tasks))
    [finished_run] = _runs(job_id, scheduled_jobs.RUN_TRIGGER_NORMAL)
    assert finished_run["status"] == scheduled_jobs.RUN_STATUS_SUCCEEDED, finished_run.get("error_message")
    assert finished_run["lease_recovery_count"] == 0
    reminders = [
        call for call in application.bot.send_message.await_args_list if "Reminder:" in str(call.kwargs.get("text"))
    ]
    assert len(reminders) == 1


_POLICY_A = {"approval_mode": "agent-a-policy"}
_POLICY_B = {"approval_mode": "agent-b-policy"}


@contextlib.contextmanager
def _as_agent(agent_id: str | None, execution_policy: dict[str, Any]) -> Iterator[None]:
    """Run scheduler code as one agent's process: its agent id and its execution policy."""
    from koda.services import scheduled_jobs

    with (
        patch.object(scheduled_jobs, "AGENT_ID", agent_id),
        patch.object(scheduled_jobs, "AGENT_EXECUTION_POLICY", execution_policy),
    ):
        yield


def _reminders_sent(application: Any) -> list[str]:
    return [
        str(call.kwargs.get("text"))
        for call in application.bot.send_message.await_args_list
        if "Reminder:" in str(call.kwargs.get("text"))
    ]


async def test_an_agent_cycle_never_claims_another_agents_queued_run(scheduler_db: str) -> None:
    from koda.services import scheduled_jobs

    application_a, application_b = _fake_application(), _fake_application()
    with _as_agent("AGENT_B", _POLICY_B):
        job_b = scheduled_jobs.create_reminder_job(
            user_id=111, chat_id=333, trigger_type="interval", schedule_expr="3600", text="Drink water"
        )

    # Agent A's cycle sees agent B's queued validation run and leaves it to agent B.
    with _as_agent("AGENT_A", _POLICY_A):
        cycle = await _run_dispatch_cycle(application_a)
    assert cycle["claimed"] == 0
    [validation_run] = _runs(job_b, scheduled_jobs.RUN_TRIGGER_MANUAL_TEST)
    assert validation_run["status"] == scheduled_jobs.RUN_STATUS_QUEUED
    application_a.bot.send_message.assert_not_called()

    with _as_agent("AGENT_B", _POLICY_B):
        cycle = await _run_dispatch_cycle(application_b)
    assert cycle["claimed"] == 1
    job = scheduled_jobs._get_job(job_b)
    assert job is not None and job["status"] == scheduled_jobs.JOB_STATUS_ACTIVE


async def test_a_process_without_agent_id_runs_the_jobs_created_without_one(scheduler_db: str) -> None:
    # A standalone install runs without AGENT_ID: its jobs carry no agent, and they still run there.
    from koda.services import scheduled_jobs

    with _as_agent(None, _POLICY_A):
        job_id = scheduled_jobs.create_reminder_job(
            user_id=111, chat_id=222, trigger_type="interval", schedule_expr="3600", text="Stretch break"
        )
    job = scheduled_jobs._get_job(job_id)
    assert job is not None and job["agent_id"] is None

    with _as_agent("AGENT_A", _POLICY_A):
        assert (await _run_dispatch_cycle(_fake_application()))["claimed"] == 0
    with _as_agent(None, _POLICY_A):
        assert (await _run_dispatch_cycle(_fake_application()))["claimed"] == 1
    job = scheduled_jobs._get_job(job_id)
    assert job is not None and job["status"] == scheduled_jobs.JOB_STATUS_ACTIVE


async def test_each_agent_materializes_and_dispatches_only_its_own_jobs_under_its_own_policy(
    scheduler_db: str,
) -> None:
    from koda.services import scheduled_jobs

    application_a, application_b = _fake_application(), _fake_application()
    with _as_agent("AGENT_A", _POLICY_A):
        job_a = await _active_reminder_job(application_a)
    with _as_agent("AGENT_B", _POLICY_B):
        job_b = scheduled_jobs.create_reminder_job(
            user_id=111, chat_id=333, trigger_type="interval", schedule_expr="3600", text="Drink water"
        )
        await _run_dispatch_cycle(application_b)
    validated_a, validated_b = scheduled_jobs._get_job(job_a), scheduled_jobs._get_job(job_b)
    assert validated_a is not None and validated_b is not None
    assert validated_b["status"] == scheduled_jobs.JOB_STATUS_ACTIVE
    hash_a, hash_b = validated_a["policy_snapshot_hash"], validated_b["policy_snapshot_hash"]
    assert hash_a != hash_b
    due_at = scheduled_jobs._iso(scheduled_jobs._utcnow() - timedelta(seconds=5))
    scheduled_jobs._touch_job(job_a, next_run_at=due_at)
    scheduled_jobs._touch_job(job_b, next_run_at=due_at)

    # Agent A's cycle runs agent A's job only, through agent A's bot.
    with _as_agent("AGENT_A", _POLICY_A):
        cycle = await _run_dispatch_cycle(application_a)
    assert cycle["materialized"] == 1
    assert cycle["claimed"] == 1
    assert _runs(job_b, scheduled_jobs.RUN_TRIGGER_NORMAL) == []
    untouched_b = scheduled_jobs._get_job(job_b)
    assert untouched_b is not None
    assert untouched_b["next_run_at"] == due_at
    assert untouched_b["policy_snapshot_hash"] == hash_b
    assert _reminders_sent(application_a) == ["⏰ Reminder: Stretch break"]

    # Agent B's cycle runs agent B's job under agent B's policy; agent A's snapshot stays put.
    with _as_agent("AGENT_B", _POLICY_B):
        cycle = await _run_dispatch_cycle(application_b)
    assert cycle["materialized"] == 1
    [run_b] = _runs(job_b, scheduled_jobs.RUN_TRIGGER_NORMAL)
    assert run_b["status"] == scheduled_jobs.RUN_STATUS_SUCCEEDED, run_b.get("error_message")
    assert run_b["metadata"]["policy_snapshot_hash"] == hash_b
    assert run_b["metadata"]["policy_snapshot"]["execution_policy"] == _POLICY_B
    [run_a] = _runs(job_a, scheduled_jobs.RUN_TRIGGER_NORMAL)
    assert run_a["metadata"]["policy_snapshot"]["execution_policy"] == _POLICY_A
    job_a_after = scheduled_jobs._get_job(job_a)
    assert job_a_after is not None and job_a_after["policy_snapshot_hash"] == hash_a
    assert _events(job_a, "job.policy_snapshot_refreshed") == []
    assert _events(job_b, "job.policy_snapshot_refreshed") == []
    assert _reminders_sent(application_b) == ["⏰ Reminder: Drink water"]
    assert _reminders_sent(application_a) == ["⏰ Reminder: Stretch break"]


@contextlib.contextmanager
def _another_process() -> Iterator[None]:
    """Run a dispatch cycle as a separate process: its own dispatcher id and no in-flight runs."""
    from koda.services import scheduled_job_dispatcher

    with (
        patch.object(scheduled_job_dispatcher, "_dispatcher_id", "other-host:4242:feedbeef"),
        patch.object(scheduled_job_dispatcher, "_inflight_run_ids", {}),
        patch.object(scheduled_job_dispatcher, "_inflight_dispatch_tasks", set()),
    ):
        yield


async def test_another_agents_process_never_recovers_a_run_this_agent_still_dispatches(scheduler_db: str) -> None:
    from koda.services import scheduled_job_dispatcher, scheduled_jobs

    application_a, application_b = _fake_application(), _fake_application()
    send_started = asyncio.Event()
    release_send = asyncio.Event()

    async def _slow_send(**_kwargs: Any) -> None:
        send_started.set()
        await release_send.wait()

    with _as_agent("AGENT_A", _POLICY_A):
        job_id = await _active_reminder_job(application_a)
        application_a.bot.send_message = AsyncMock(side_effect=_slow_send)
        due_at = scheduled_jobs._utcnow() - timedelta(seconds=5)
        scheduled_jobs._touch_job(job_id, next_run_at=scheduled_jobs._iso(due_at))
        assert (await scheduled_jobs.run_dispatch_cycle(application_a))["claimed"] == 1
        await asyncio.wait_for(send_started.wait(), timeout=10)
    [run] = _runs(job_id, scheduled_jobs.RUN_TRIGGER_NORMAL)

    # Agent A's send outlives a short lease while agent B's process cycles: agent B cannot see
    # that agent A still dispatches the run, so it must leave the run alone.
    _expire_lease(int(run["id"]))
    with _as_agent("AGENT_B", _POLICY_B), _another_process():
        cycle = await scheduled_jobs.run_dispatch_cycle(application_b)

    assert cycle["claimed"] == 0
    [live_run] = _runs(job_id, scheduled_jobs.RUN_TRIGGER_NORMAL)
    assert live_run["status"] == scheduled_jobs.RUN_STATUS_RUNNING
    assert live_run["lease_recovery_count"] == 0
    assert _events(job_id, "run.lease_recovered") == []

    with _as_agent("AGENT_A", _POLICY_A):
        release_send.set()
        await asyncio.gather(*list(scheduled_job_dispatcher._inflight_dispatch_tasks))
    [finished_run] = _runs(job_id, scheduled_jobs.RUN_TRIGGER_NORMAL)
    assert finished_run["status"] == scheduled_jobs.RUN_STATUS_SUCCEEDED, finished_run.get("error_message")
    assert finished_run["lease_recovery_count"] == 0
    assert _reminders_sent(application_a) == ["⏰ Reminder: Stretch break"]
    application_b.bot.send_message.assert_not_called()


async def test_a_second_process_of_the_same_agent_never_recovers_a_run_the_first_still_dispatches(
    scheduler_db: str,
) -> None:
    # An overlapping restart or a cluster handover runs two processes of one agent. The second cannot
    # see the first's in-flight run, so the first keeps that run's lease alive every cycle.
    from koda.services import scheduled_job_dispatcher, scheduled_jobs

    first, second = _fake_application(), _fake_application()
    send_started = asyncio.Event()
    release_send = asyncio.Event()

    async def _slow_send(**_kwargs: Any) -> None:
        send_started.set()
        await release_send.wait()

    with _as_agent("AGENT_A", _POLICY_A):
        job_id = await _active_reminder_job(first)
        first.bot.send_message = AsyncMock(side_effect=_slow_send)
        scheduled_jobs._touch_job(
            job_id, next_run_at=scheduled_jobs._iso(scheduled_jobs._utcnow() - timedelta(seconds=5))
        )
        assert (await scheduled_jobs.run_dispatch_cycle(first))["claimed"] == 1
        await asyncio.wait_for(send_started.wait(), timeout=10)
        [run] = _runs(job_id, scheduled_jobs.RUN_TRIGGER_NORMAL)
        # The send outlives most of a short lease; the first process's next cycle extends it.
        about_to_expire = scheduled_jobs._utcnow() + timedelta(seconds=1)
        scheduled_jobs._touch_run(int(run["id"]), lease_expires_at=scheduled_jobs._iso(about_to_expire))
        await scheduled_jobs.run_dispatch_cycle(first)

    # The second process cycles after the old lease would have run out.
    later = scheduled_jobs._utcnow() + timedelta(seconds=5)
    with (
        _as_agent("AGENT_A", _POLICY_A),
        _another_process(),
        patch.object(scheduled_jobs, "_utcnow", return_value=later),
    ):
        cycle = await scheduled_jobs.run_dispatch_cycle(second)

    assert cycle["claimed"] == 0
    [live_run] = _runs(job_id, scheduled_jobs.RUN_TRIGGER_NORMAL)
    assert live_run["status"] == scheduled_jobs.RUN_STATUS_RUNNING
    assert live_run["lease_recovery_count"] == 0
    assert _events(job_id, "run.lease_recovered") == []

    with _as_agent("AGENT_A", _POLICY_A):
        release_send.set()
        await asyncio.gather(*list(scheduled_job_dispatcher._inflight_dispatch_tasks))
    [finished_run] = _runs(job_id, scheduled_jobs.RUN_TRIGGER_NORMAL)
    assert finished_run["status"] == scheduled_jobs.RUN_STATUS_SUCCEEDED, finished_run.get("error_message")
    assert _reminders_sent(first) == ["⏰ Reminder: Stretch break"]
    second.bot.send_message.assert_not_called()


async def test_an_agent_never_lists_validates_or_runs_another_agents_job(scheduler_db: str) -> None:
    # One Telegram user talks to agent A's and agent B's bots. Agent A's bot, tools and runtime API
    # must not act on agent B's job: a run or validation queued there would carry agent A's policy,
    # and agent B's drift check would then block the run and deactivate agent B's job.
    from koda.services import scheduled_jobs
    from koda.services.scheduler import cancel_user_jobs, list_user_jobs

    application_b = _fake_application()
    with _as_agent("AGENT_B", _POLICY_B):
        job_b = await _active_reminder_job(application_b)
    validated_b = scheduled_jobs._get_job(job_b)
    assert validated_b is not None
    hash_b = validated_b["policy_snapshot_hash"]

    with _as_agent("AGENT_A", _POLICY_A):
        assert scheduled_jobs.list_jobs(111) == []
        assert list_user_jobs(None, 111) == []
        assert scheduled_jobs.get_job(job_b, 111) is None
        assert scheduled_jobs.list_job_runs(job_b, 111) == []
        assert scheduled_jobs.queue_validation_run(job_b, user_id=111, activate_on_success=False) == (
            None,
            "Job not found.",
        )
        assert scheduled_jobs.run_job_now(job_b, 111) == (None, "Job not found.")
        assert scheduled_jobs.pause_job(job_b, 111) == (False, "Job not found.")
        assert cancel_user_jobs(None, 111) == 0
        # Internal callers without a user cannot queue a run under this agent's policy either.
        assert scheduled_jobs.queue_validation_run(job_b) == (None, "Job not found.")
        with pytest.raises(ValueError):
            scheduled_jobs.create_run(scheduled_job_id=job_b, trigger_reason=scheduled_jobs.RUN_TRIGGER_MANUAL_RUN)
        assert (await _run_dispatch_cycle(_fake_application()))["claimed"] == 0

    job_after = scheduled_jobs._get_job(job_b)
    assert job_after is not None
    assert job_after["status"] == scheduled_jobs.JOB_STATUS_ACTIVE
    assert job_after["policy_snapshot_hash"] == hash_b
    assert _runs(job_b, scheduled_jobs.RUN_TRIGGER_MANUAL_RUN) == []
    assert len(_runs(job_b, scheduled_jobs.RUN_TRIGGER_MANUAL_TEST)) == 1

    # Agent B's own bot runs it now, under agent B's policy, and the job stays active.
    with _as_agent("AGENT_B", _POLICY_B):
        run_id, _ = scheduled_jobs.run_job_now(job_b, 111)
        assert run_id is not None
        await _run_dispatch_cycle(application_b)
    [manual_run] = _runs(job_b, scheduled_jobs.RUN_TRIGGER_MANUAL_RUN)
    assert manual_run["status"] == scheduled_jobs.RUN_STATUS_SUCCEEDED, manual_run.get("error_message")
    assert manual_run["metadata"]["policy_snapshot"]["execution_policy"] == _POLICY_B
    job_final = scheduled_jobs._get_job(job_b)
    assert job_final is not None and job_final["status"] == scheduled_jobs.JOB_STATUS_ACTIVE
    assert _reminders_sent(application_b) == ["⏰ Reminder: Stretch break"]


async def _unowned_and_owned_jobs() -> tuple[int, int]:
    """A job created by a process without AGENT_ID (a standalone worker) and one of agent A."""
    with _as_agent(None, _POLICY_A):
        unowned_job = await _active_reminder_job(_fake_application())
    with _as_agent("AGENT_A", _POLICY_A):
        owned_job = await _active_reminder_job(_fake_application())
    return unowned_job, owned_job


async def test_an_agent_never_lists_or_queues_a_run_for_a_job_without_an_agent(scheduler_db: str) -> None:
    # No supervised agent runs a job without an agent, so none lists it as its own (the bot, the
    # dashboard) or accepts a run for it that nothing would ever claim.
    from koda.services import scheduled_jobs
    from koda.state.dashboard_store import DashboardStore

    unowned_job, owned_job = await _unowned_and_owned_jobs()

    with _as_agent("AGENT_A", _POLICY_A):
        assert scheduled_jobs.run_job_now(unowned_job, 111) == (None, "Job not found.")
        assert [job["id"] for job in scheduled_jobs.list_jobs(111)] == [owned_job]
    assert _runs(unowned_job, scheduled_jobs.RUN_TRIGGER_MANUAL_RUN) == []
    assert [item["id"] for item in DashboardStore().list_schedules("AGENT_A")] == [owned_job]
    assert DashboardStore().list_schedules("AGENT_B") == []


async def test_each_agent_reports_the_jobs_without_an_agent_that_it_skips(scheduler_db: str) -> None:
    from koda.services import scheduled_job_dispatcher, scheduled_jobs

    unowned_job, _owned_job = await _unowned_and_owned_jobs()

    with _as_agent("AGENT_A", _POLICY_A), patch.object(scheduled_job_dispatcher, "log") as log:
        assert scheduled_job_dispatcher.report_unowned_jobs() == [unowned_job]
        assert scheduled_jobs.get_scheduler_snapshot()["unowned_jobs"] == 1
    log.warning.assert_called_once()
    assert log.warning.call_args.args == ("scheduler_unowned_jobs_skipped",)
    assert log.warning.call_args.kwargs["job_ids"] == [unowned_job]

    # A process without an agent id (the standalone worker) owns them: nothing to report there.
    with _as_agent(None, _POLICY_A):
        assert scheduled_job_dispatcher.report_unowned_jobs() == []
        assert scheduled_jobs.get_scheduler_snapshot()["unowned_jobs"] == 0


_POLICY_STANDALONE = {"approval_mode": "standalone-worker-policy"}
_UPGRADE_DOC = Path(__file__).resolve().parents[2] / "docs" / "operations" / "upgrade.md"


def _documented_assignment_sql(job_id: int) -> str:
    """The SQL that docs/operations/upgrade.md gives to assign jobs without an agent, for one job."""
    doc = _UPGRADE_DOC.read_text(encoding="utf-8")
    section = doc.split("### Scheduled jobs without an agent", 1)[1].split("\n## ", 1)[0]
    blocks = re.findall(r"```sql\n(.*?)```", section, flags=re.DOTALL)
    assert blocks, "the section gives no SQL"
    return "\n".join(blocks).replace("(12, 15)", f"({job_id})")


async def _standalone_job_with_leftover_runs() -> int:
    """An active hourly reminder of a standalone worker that died mid-send, with a catch-up run queued."""
    from koda.services import scheduled_jobs

    with _as_agent(None, _POLICY_STANDALONE):
        job_id = await _active_reminder_job(_fake_application())
        now = scheduled_jobs._utcnow()
        running = scheduled_jobs.create_run(
            scheduled_job_id=job_id,
            scheduled_for=now - timedelta(hours=3),
            trigger_reason=scheduled_jobs.RUN_TRIGGER_CATCHUP,
        )
        scheduled_jobs._touch_run(
            running,
            status=scheduled_jobs.RUN_STATUS_RUNNING,
            lease_owner="standalone-host:1:dead",
            lease_expires_at=scheduled_jobs._iso(now - timedelta(minutes=1)),
        )
        scheduled_jobs.create_run(
            scheduled_job_id=job_id,
            scheduled_for=now - timedelta(hours=2),
            trigger_reason=scheduled_jobs.RUN_TRIGGER_CATCHUP,
        )
        scheduled_jobs._touch_job(job_id, next_run_at=scheduled_jobs._iso(now - timedelta(minutes=30)))
    return job_id


async def test_the_documented_assignment_of_a_job_without_an_agent_keeps_it_running(scheduler_db: str) -> None:
    # The upgrade doc's procedure, run as written: the job's leftover runs carry the standalone
    # worker's policy snapshot, so they must be closed before the job moves to the agent.
    from koda.services import scheduled_jobs

    job_id = await _standalone_job_with_leftover_runs()
    open_runs = {int(run["id"]): str(run["status"]) for run in _runs(job_id, scheduled_jobs.RUN_TRIGGER_CATCHUP)}
    before = scheduled_jobs._utcnow()
    conn = await asyncpg.connect(scheduler_db)
    try:
        await conn.execute(_documented_assignment_sql(job_id))
    finally:
        await conn.close()

    # The SQL closes each run as the scheduler's own cancellation does: a completion time, a fresh
    # updated_at, and one run.cancelled event that says what closed it.
    closed = {int(run["id"]): run for run in _runs(job_id, scheduled_jobs.RUN_TRIGGER_CATCHUP)}
    assert set(closed) == set(open_runs)
    for run_id, run in closed.items():
        assert run["status"] == scheduled_jobs.RUN_STATUS_CANCELLED
        assert run["completed_at"] is not None and datetime.fromisoformat(run["completed_at"]) >= before
        assert datetime.fromisoformat(run["updated_at"]) >= before
        [event] = [event for event in _events(job_id, "run.cancelled") if event["scheduled_run_id"] == run_id]
        assert (event["status_from"], event["status_to"]) == (open_runs[run_id], scheduled_jobs.RUN_STATUS_CANCELLED)
        assert event["reason"] == "Closed before assigning the job to an agent."
        assert datetime.fromisoformat(event["created_at"]) >= before

    application_a = _fake_application()
    with _as_agent("AGENT_A", _POLICY_A):
        for _ in range(3):
            await _run_dispatch_cycle(application_a)

    job = scheduled_jobs._get_job(job_id)
    assert job is not None and job["agent_id"] == "AGENT_A"
    assert job["status"] == scheduled_jobs.JOB_STATUS_ACTIVE
    assert job["next_run_at"] is not None
    assert _events(job_id, "run.blocked_by_policy") == []
    # The next occurrence inside the catch-up window runs under the agent's policy.
    assert _reminders_sent(application_a) == ["⏰ Reminder: Stretch break"]
    [catch_up] = [run for run in _runs(job_id, scheduled_jobs.RUN_TRIGGER_CATCHUP) if run["status"] == "succeeded"]
    assert catch_up["metadata"]["policy_snapshot"]["execution_policy"] == _POLICY_A


async def test_a_job_assigned_with_its_runs_open_is_blocked_until_the_agent_revalidates_it(
    scheduler_db: str,
) -> None:
    # What the upgrade doc says happens when the job's runs are left open: the agent blocks the
    # first leftover run it claims, the job waits for validation with no next run, and its other
    # runs end blocked. Validating and activating it from the agent's bot recovers it.
    from koda.services import scheduled_jobs

    job_id = await _standalone_job_with_leftover_runs()
    scheduled_jobs._store().execute("UPDATE scheduled_jobs SET agent_id = ? WHERE id = ?", ("AGENT_A", job_id))

    application_a = _fake_application()
    with _as_agent("AGENT_A", _POLICY_A):
        await _run_dispatch_cycle(application_a)
        job = scheduled_jobs._get_job(job_id)
        assert job is not None
        assert (job["status"], job["next_run_at"]) == (scheduled_jobs.JOB_STATUS_VALIDATION_PENDING, None)
        [blocked] = _events(job_id, "run.blocked_by_policy")
        assert blocked["reason"] == "Scheduled run blocked because the job policy changed after validation."
        statuses = {run["status"] for run in _runs(job_id, scheduled_jobs.RUN_TRIGGER_CATCHUP)}
        assert statuses == {scheduled_jobs.RUN_STATUS_BLOCKED}
        assert _reminders_sent(application_a) == []

        # `/jobs validate <id>`, then `/jobs activate <id>` once the validation passes.
        run_id, _ = scheduled_jobs.queue_validation_run(job_id, user_id=111, activate_on_success=False)
        assert run_id is not None
        await _run_dispatch_cycle(application_a)
        assert scheduled_jobs.activate_job(job_id, 111) == (True, "Job activated.")
    job = scheduled_jobs._get_job(job_id)
    assert job is not None and job["status"] == scheduled_jobs.JOB_STATUS_ACTIVE
    assert job["next_run_at"] is not None


async def test_scheduler_snapshot_counts_only_this_agents_jobs_and_runs(scheduler_db: str) -> None:
    from koda.services import scheduled_job_runtime, scheduled_jobs
    from koda.services.metrics import SCHEDULED_DUE_RUNS, SCHEDULED_LEASED_RUNS

    with _as_agent("AGENT_B", _POLICY_B):
        # Two jobs of agent B wait in validation: one validation run is claimed (a live lease) and the
        # other is due. Agent B is down, so agent A's process must not report either as its own.
        for text in ("Drink water", "Stand up"):
            scheduled_jobs.create_reminder_job(
                user_id=111, chat_id=333, trigger_type="interval", schedule_expr="3600", text=text
            )
        with patch.object(scheduled_job_runtime, "_dispatch_run", AsyncMock()):
            assert len(scheduled_jobs._claim_due_runs(limit=1)) == 1
        snapshot_b = scheduled_jobs.get_scheduler_snapshot()
    with _as_agent("AGENT_A", _POLICY_A):
        snapshot_a = scheduled_jobs.get_scheduler_snapshot()

    assert (snapshot_a["active_jobs"], snapshot_a["due_runs"], snapshot_a["leased_runs"]) == (0, 0, 0)
    assert snapshot_a["validation_pending_jobs"] == 0
    assert (snapshot_b["active_jobs"], snapshot_b["due_runs"], snapshot_b["leased_runs"]) == (2, 1, 1)
    assert snapshot_b["validation_pending_jobs"] == 2
    assert SCHEDULED_DUE_RUNS.labels(agent_id="AGENT_A")._value.get() == 0
    assert SCHEDULED_LEASED_RUNS.labels(agent_id="AGENT_A")._value.get() == 0
    assert SCHEDULED_DUE_RUNS.labels(agent_id="AGENT_B")._value.get() == 1


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
