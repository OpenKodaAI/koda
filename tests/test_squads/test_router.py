"""Tests for the squad router daemon."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import suppress
from unittest.mock import AsyncMock

import pytest

from koda.squads.router import SquadRouter, SweepReport
from koda.squads.tasks import ExpiredClaim, SquadTaskStore
from koda.squads.threads import SquadThreadStore


def _schema() -> str:
    return (os.environ.get("KNOWLEDGE_V2_POSTGRES_SCHEMA") or "knowledge_v2").strip() or "knowledge_v2"


# --- non-PG unit tests ---


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
    thread_store = AsyncMock()
    thread_store.post_thread_message = AsyncMock(return_value=99)
    router = SquadRouter(task_store=task_store, thread_store=thread_store)
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
    thread_store = AsyncMock()
    thread_store.post_thread_message = AsyncMock(side_effect=RuntimeError("disk full"))
    router = SquadRouter(task_store=task_store, thread_store=thread_store)
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
        await conn.execute(f'TRUNCATE TABLE "{schema}"."squad_tasks"')
        await conn.execute(f'TRUNCATE TABLE "{schema}"."squad_thread_participants"')
        await conn.execute(f'TRUNCATE TABLE "{schema}"."squad_threads"')
        await conn.execute(f'TRUNCATE TABLE "{schema}"."squad_messages" RESTART IDENTITY')
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
    assert fresh.assigned_agent_id is None
    assert fresh.claim_token is None


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
    coord = CoordinatorService(dsn=clean_state, schema=_schema())
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
