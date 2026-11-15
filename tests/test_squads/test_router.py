"""Tests for the squad router daemon."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from koda.squads.coordinator import REQUIRED_COORDINATOR_TOOL_IDS
from koda.squads.router import SquadRouter, SweepReport
from koda.squads.tasks import ExpiredClaim, SquadTaskStore
from koda.squads.threads import SquadThreadStore
from tests.postgres_fixtures import reset_squad_runtime_tables

# A store mock whose pool is not async leaves "coroutine ... was never awaited" behind (D-289).
pytestmark = [
    pytest.mark.filterwarnings("error:coroutine .* was never awaited:RuntimeWarning"),
    pytest.mark.filterwarnings("error::pytest.PytestUnraisableExceptionWarning"),
]


def _schema() -> str:
    return (os.environ.get("KNOWLEDGE_V2_POSTGRES_SCHEMA") or "knowledge_v2").strip() or "knowledge_v2"


def _eligible_spec() -> dict[str, object]:
    return {"tool_policy": {"allowed_tool_ids": list(REQUIRED_COORDINATOR_TOOL_IDS)}}


# --- non-PG unit tests ---


class _FakeConnection:
    """An asyncpg connection that answers every ``fetch`` with ``rows``.

    ``fetchval`` answers the open-handoff sweep's advisory lock: it is taken unless the lock's
    key is in ``held_locks``.
    """

    def __init__(self, rows: list[dict[str, Any]] | None = None, held_locks: set[str] | None = None) -> None:
        self.rows = list(rows or [])
        self.held_locks = set(held_locks or ())
        self.fetches: list[tuple[str, tuple[Any, ...]]] = []
        self.lock_keys: list[str] = []

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        self.fetches.append((sql, args))
        return self.rows

    async def fetchval(self, _sql: str, key: str) -> bool:
        self.lock_keys.append(key)
        return key not in self.held_locks

    async def execute(self, *_args: Any) -> str:
        return "UPDATE 0"

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        yield


class _FakePool:
    def __init__(self, conn: _FakeConnection) -> None:
        self._conn = conn

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[_FakeConnection]:
        yield self._conn


class _FakeThreadStore:
    """A thread store whose pool is async like asyncpg's, so the router's SQL sweeps run against it."""

    _schema = "knowledge_v2"

    def __init__(self, conn: _FakeConnection | None = None) -> None:
        self.conn = conn or _FakeConnection()
        self._ensure_pool = AsyncMock(return_value=_FakePool(self.conn))
        self.post_thread_message = AsyncMock(return_value=99)
        self.notify_event = AsyncMock()


def _handoff_row(row_id: int, handoff_id: str | None) -> dict[str, Any]:
    return {"id": row_id, "thread_id": f"thread-{row_id}", "handoff_id": handoff_id, "task_id": f"task-{row_id}"}


@pytest.mark.asyncio
async def test_sweep_open_handoffs_checks_each_handoff_it_locks_and_pages_after_a_full_batch() -> None:
    conn = _FakeConnection(
        rows=[_handoff_row(5, "handoff-a"), _handoff_row(6, None), _handoff_row(7, "handoff-held")],
        held_locks={"squad_handoff_completion:handoff-held"},
    )
    router = SquadRouter(task_store=AsyncMock(), thread_store=_FakeThreadStore(conn), batch_size=3)  # type: ignore[arg-type]
    complete = AsyncMock()

    with patch("koda.services.queue_manager.complete_open_squad_handoff", complete):
        checked = await router._sweep_open_handoffs()

    # A row with no handoff id is skipped, and a handoff another runtime holds is left to it.
    assert checked == 1
    complete.assert_awaited_once_with(thread_id="thread-5", squad_task_id="task-5", handoff_id="handoff-a")
    assert conn.lock_keys == ["squad_handoff_completion:handoff-a", "squad_handoff_completion:handoff-held"]
    [(_sql, first_args)] = conn.fetches
    assert first_args[2:] == (3, 0)

    # A full batch moves the cursor past its last row; a short one starts the next sweep over.
    conn.rows = [_handoff_row(8, "handoff-b")]
    with patch("koda.services.queue_manager.complete_open_squad_handoff", complete):
        assert await router._sweep_open_handoffs() == 1
    assert conn.fetches[1][1][2:] == (3, 7)
    conn.rows = []
    with patch("koda.services.queue_manager.complete_open_squad_handoff", complete):
        assert await router._sweep_open_handoffs() == 0
    assert conn.fetches[2][1][2:] == (3, 0)


@pytest.mark.asyncio
async def test_sweep_open_handoffs_needs_a_thread_store() -> None:
    assert await SquadRouter(task_store=AsyncMock())._sweep_open_handoffs() == 0


@pytest.mark.asyncio
async def test_the_budget_sweep_posts_no_pause_event_when_its_pause_changed_no_row() -> None:
    # The SELECT read the thread open at its cap, but an operator paused it before the UPDATE ran:
    # the UPDATE changes no row (the fake answers "UPDATE 0"), so the operator's event is the only one.
    conn = _FakeConnection(
        rows=[
            {
                "id": "thread-1",
                "status": "open",
                "budget_usd_cap": 1.0,
                "cost_usd_accum": 1.0,
                "metadata_json": {"budget_alert_80_sent": True},
            }
        ]
    )
    thread_store = _FakeThreadStore(conn)
    router = SquadRouter(task_store=AsyncMock(), thread_store=thread_store)  # type: ignore[arg-type]

    assert await router._sweep_budgets() == (0, 0)

    thread_store.post_thread_message.assert_not_awaited()
    thread_store.notify_event.assert_not_awaited()


def test_sweep_report_reverted_count_default() -> None:
    assert SweepReport().reverted_count == 0


@pytest.mark.asyncio
async def test_sweep_once_with_no_expired_returns_empty() -> None:
    task_store = AsyncMock()
    task_store.sweep_expired_claims = AsyncMock(return_value=[])
    router = SquadRouter(task_store=task_store)
    report = await router.sweep_once()
    assert report.reverted_count == 0
    assert report.expired_claims == []


@pytest.mark.asyncio
async def test_sweep_once_emits_thread_event_per_claim() -> None:
    task_store = AsyncMock()
    claims = [
        ExpiredClaim(
            task_id="00000000-0000-0000-0000-000000000aa1",
            thread_id="00000000-0000-0000-0000-000000000bb1",
            previously_assigned_agent_id="FE",
            version_after=4,
        ),
        ExpiredClaim(
            task_id="00000000-0000-0000-0000-000000000aa2",
            thread_id="00000000-0000-0000-0000-000000000bb2",
            previously_assigned_agent_id=None,
            version_after=2,
        ),
    ]
    task_store.sweep_expired_claims = AsyncMock(return_value=claims)
    thread_store = _FakeThreadStore()
    router = SquadRouter(task_store=task_store, thread_store=thread_store)  # type: ignore[arg-type]
    report = await router.sweep_once()
    assert report.reverted_count == 2
    assert thread_store.post_thread_message.await_count == 2
    first_call = thread_store.post_thread_message.await_args_list[0].kwargs
    assert first_call["thread_id"] == claims[0].thread_id
    assert first_call["message_type"] == "system_event"
    assert first_call["metadata"]["event_type"] == "claim_expired"
    assert first_call["metadata"]["task_id"] == claims[0].task_id


@pytest.mark.asyncio
async def test_sweep_once_swallows_thread_event_failure() -> None:
    task_store = AsyncMock()
    claim = ExpiredClaim(
        task_id="00000000-0000-0000-0000-000000000aa1",
        thread_id="00000000-0000-0000-0000-000000000bb1",
        previously_assigned_agent_id="X",
        version_after=2,
    )
    task_store.sweep_expired_claims = AsyncMock(return_value=[claim])
    thread_store = _FakeThreadStore()
    thread_store.post_thread_message = AsyncMock(side_effect=RuntimeError("disk full"))
    router = SquadRouter(task_store=task_store, thread_store=thread_store)  # type: ignore[arg-type]
    # Must not propagate the inner error; the claim was already reverted
    # before this call, so a failed audit event is non-fatal.
    report = await router.sweep_once()
    assert report.reverted_count == 1


@pytest.mark.asyncio
async def test_sweep_once_swallows_sweep_failure() -> None:
    task_store = AsyncMock()
    task_store.sweep_expired_claims = AsyncMock(side_effect=RuntimeError("pool down"))
    router = SquadRouter(task_store=task_store)
    report = await router.sweep_once()
    assert report.reverted_count == 0


@pytest.mark.asyncio
async def test_router_lifecycle_idempotent() -> None:
    task_store = AsyncMock()
    task_store.sweep_expired_claims = AsyncMock(return_value=[])
    router = SquadRouter(task_store=task_store, sweep_interval_s=10.0)
    await router.start()
    assert router.is_running
    # Second start is a no-op.
    await router.start()
    assert router.is_running
    await router.stop()
    assert not router.is_running
    # Second stop is a no-op.
    await router.stop()


@pytest.mark.asyncio
async def test_router_sweeps_periodically() -> None:
    task_store = AsyncMock()
    task_store.sweep_expired_claims = AsyncMock(return_value=[])
    router = SquadRouter(task_store=task_store, sweep_interval_s=0.05)
    await router.start()
    try:
        # Wait long enough for at least 2 sweeps.
        await asyncio.sleep(0.18)
    finally:
        await router.stop()
    assert task_store.sweep_expired_claims.await_count >= 2


# --- PG-marked tests ---


@pytest.fixture
async def clean_state(migrated_postgres: str) -> AsyncIterator[str]:
    import asyncpg  # type: ignore[import-not-found]

    schema = _schema()
    conn = await asyncpg.connect(migrated_postgres)
    try:
        await reset_squad_runtime_tables(conn, schema)
    finally:
        await conn.close()
    yield migrated_postgres


@pytest.fixture
async def stores(clean_state: str) -> AsyncIterator[tuple[SquadThreadStore, SquadTaskStore]]:
    threads = SquadThreadStore(dsn=clean_state, schema=_schema())
    tasks = SquadTaskStore(dsn=clean_state, schema=_schema())
    try:
        yield threads, tasks
    finally:
        with suppress(Exception):
            await threads.close()
        with suppress(Exception):
            await tasks.close()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_sweep_reverts_expired_claim(stores: tuple[SquadThreadStore, SquadTaskStore]) -> None:
    threads, tasks = stores
    thread = await threads.create_thread(workspace_id="acme", squad_id="build", title="t")
    task = await tasks.create_task(thread_id=thread.id, title="t", assigner_agent_id="PM")
    # Use a very short TTL so the claim is already past expiry by the time we sweep.
    await tasks.claim_task(task_id=task.id, agent_id="W", ttl_seconds=1)
    await asyncio.sleep(1.2)
    expired = await tasks.sweep_expired_claims()
    assert len(expired) == 1
    assert expired[0].task_id == task.id
    assert expired[0].previously_assigned_agent_id == "W"
    fresh = await tasks.get_task(task.id)
    assert fresh is not None
    assert fresh.status == "pending"
    # The planned assignee is kept, so the router can dispatch the task to it again (D-097).
    assert fresh.assigned_agent_id == "W"
    assert fresh.claim_token is None
    assert fresh.metadata["claim_expiry_count"] == 1
    assert expired[0].expiry_count == 1


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_sweep_keeps_the_expired_claims_of_a_thread_that_reached_its_budget_cap(
    stores: tuple[SquadThreadStore, SquadTaskStore],
) -> None:
    from decimal import Decimal

    threads, tasks = stores
    thread = await threads.create_thread(
        workspace_id="acme", squad_id="build", title="t", budget_usd_cap=Decimal("1.00")
    )
    task = await tasks.create_task(thread_id=thread.id, title="t", assigner_agent_id="PM")
    await tasks.claim_task(task_id=task.id, agent_id="W", ttl_seconds=1)
    pool = await tasks._ensure_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f"""UPDATE "{_schema()}"."squad_tasks" SET claim_expires_at = NOW() - INTERVAL '1 second' WHERE id = $1""",
            task.id,
        )
        await conn.execute(
            f'UPDATE "{_schema()}"."squad_threads" SET cost_usd_accum = 1.00 WHERE id = $1',
            thread.id,
        )

    # The thread runs no turn, so the claim waits rather than being dispatched again into a refusal.
    assert await tasks.sweep_expired_claims() == []
    fresh = await tasks.get_task(task.id)
    assert fresh is not None and fresh.status == "claimed"


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_sweep_skips_unexpired_claim(stores: tuple[SquadThreadStore, SquadTaskStore]) -> None:
    threads, tasks = stores
    thread = await threads.create_thread(workspace_id="acme", squad_id="build", title="t")
    task = await tasks.create_task(thread_id=thread.id, title="t", assigner_agent_id="PM")
    await tasks.claim_task(task_id=task.id, agent_id="W", ttl_seconds=300)
    expired = await tasks.sweep_expired_claims()
    assert expired == []
    fresh = await tasks.get_task(task.id)
    assert fresh is not None
    assert fresh.status == "claimed"
    assert fresh.assigned_agent_id == "W"


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_router_auto_election_promotes_first_active(
    clean_state: str,
) -> None:
    """When a squad has policy=auto_first_active and no coordinator, the
    router promotes the earliest-joined active participant of any open thread."""
    from koda.squads.coordinator import CoordinatorService

    threads = SquadThreadStore(dsn=clean_state, schema=_schema())
    tasks = SquadTaskStore(dsn=clean_state, schema=_schema())
    coord = CoordinatorService(dsn=clean_state, schema=_schema(), agent_spec_loader=lambda _agent_id: _eligible_spec())
    try:
        # Configure auto policy without electing.
        await coord.set_election_policy(squad_id="build", policy="auto_first_active")
        thread = await threads.create_thread(workspace_id="acme", squad_id="build", title="t")
        await threads.add_participant(thread_id=thread.id, agent_id="FE", role="worker")
        await threads.add_participant(thread_id=thread.id, agent_id="BE", role="worker")
        router = SquadRouter(task_store=tasks, thread_store=threads, coordinator_service=coord)
        report = await router.sweep_once()
        assert report.elected_count == 1
        assert report.auto_elections[0].squad_id == "build"
        assert report.auto_elections[0].coordinator_agent_id == "FE"
        # State table reflects the elected coordinator.
        state = await coord.current_coordinator("build")
        assert state is not None
        assert state.coordinator_agent_id == "FE"
        # A second sweep is a no-op (already elected).
        second = await router.sweep_once()
        assert second.elected_count == 0
    finally:
        with suppress(Exception):
            await threads.close()
        with suppress(Exception):
            await tasks.close()
        with suppress(Exception):
            await coord.close()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_router_skips_auto_election_when_no_open_thread(clean_state: str) -> None:
    from koda.squads.coordinator import CoordinatorService

    threads = SquadThreadStore(dsn=clean_state, schema=_schema())
    tasks = SquadTaskStore(dsn=clean_state, schema=_schema())
    coord = CoordinatorService(dsn=clean_state, schema=_schema())
    try:
        await coord.set_election_policy(squad_id="build", policy="auto_first_active")
        # No threads → no candidates
        router = SquadRouter(task_store=tasks, thread_store=threads, coordinator_service=coord)
        report = await router.sweep_once()
        assert report.elected_count == 0
        state = await coord.current_coordinator("build")
        assert state is not None
        assert state.coordinator_agent_id is None
    finally:
        with suppress(Exception):
            await threads.close()
        with suppress(Exception):
            await tasks.close()
        with suppress(Exception):
            await coord.close()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_router_full_path_emits_thread_message(
    stores: tuple[SquadThreadStore, SquadTaskStore],
) -> None:
    threads, tasks = stores
    thread = await threads.create_thread(workspace_id="acme", squad_id="build", title="t")
    task = await tasks.create_task(thread_id=thread.id, title="t", assigner_agent_id="PM")
    await tasks.claim_task(task_id=task.id, agent_id="W", ttl_seconds=1)
    await asyncio.sleep(1.2)
    router = SquadRouter(task_store=tasks, thread_store=threads)
    report = await router.sweep_once()
    assert report.reverted_count == 1
    history = await threads.thread_history(thread_id=thread.id, limit=10)
    assert any(m["type"] == "system_event" and "claim_expired" in (m["content"] or "") for m in history)


@pytest.mark.asyncio
async def test_sweep_squad_claims_runs_only_that_squads_claim_sweep() -> None:
    claim = ExpiredClaim(
        task_id="00000000-0000-0000-0000-000000000aa1",
        thread_id="00000000-0000-0000-0000-000000000bb1",
        previously_assigned_agent_id="FE",
        version_after=4,
    )
    task_store = AsyncMock()
    task_store.sweep_expired_claims = AsyncMock(return_value=[claim])
    thread_store = _FakeThreadStore()
    coordinator = AsyncMock()
    router = SquadRouter(task_store=task_store, thread_store=thread_store, coordinator_service=coordinator)  # type: ignore[arg-type]
    report = await router.sweep_squad_claims("build")
    assert report.expired_claims == [claim]
    assert task_store.sweep_expired_claims.await_args.kwargs["squad_id"] == "build"
    assert thread_store.post_thread_message.await_args.kwargs["thread_id"] == claim.thread_id
    # The global sweeps (auto-election, timeouts, dead letters, budgets, handoffs) stay with the loop.
    assert coordinator.mock_calls == []
    assert thread_store._ensure_pool.await_count == 0


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_squad_scoped_sweep_leaves_other_squads_alone(clean_state: str) -> None:
    from koda.squads.coordinator import CoordinatorService

    threads = SquadThreadStore(dsn=clean_state, schema=_schema())
    tasks = SquadTaskStore(dsn=clean_state, schema=_schema())
    coord = CoordinatorService(dsn=clean_state, schema=_schema(), agent_spec_loader=lambda _agent_id: _eligible_spec())
    try:
        build = await threads.create_thread(workspace_id="acme", squad_id="build", title="t")
        other = await threads.create_thread(workspace_id="beta", squad_id="ops", title="t")
        await threads.add_participant(thread_id=other.id, agent_id="BETA_W", role="worker")
        await coord.set_election_policy(squad_id="ops", policy="auto_first_active")
        build_task = await tasks.create_task(thread_id=build.id, title="t", assigner_agent_id="PM")
        other_task = await tasks.create_task(thread_id=other.id, title="t", assigner_agent_id="BETA_PM")
        await tasks.claim_task(task_id=build_task.id, agent_id="W", ttl_seconds=1)
        await tasks.claim_task(task_id=other_task.id, agent_id="BETA_W", ttl_seconds=1)
        await asyncio.sleep(1.2)
        router = SquadRouter(task_store=tasks, thread_store=threads, coordinator_service=coord)
        report = await router.sweep_squad_claims("build")
        assert [c.task_id for c in report.expired_claims] == [build_task.id]
        assert report.auto_elections == []
        fresh_other = await tasks.get_task(other_task.id)
        assert fresh_other is not None
        assert fresh_other.status == "claimed"
        assert fresh_other.assigned_agent_id == "BETA_W"
        state = await coord.current_coordinator("ops")
        assert state is not None and state.coordinator_agent_id is None
    finally:
        with suppress(Exception):
            await threads.close()
        with suppress(Exception):
            await tasks.close()
        with suppress(Exception):
            await coord.close()
