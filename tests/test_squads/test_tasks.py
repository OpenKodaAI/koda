"""Tests for the squad task store (Postgres-backed)."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import suppress

import pytest

from koda.squads.tasks import (
    IllegalTransitionError,
    SquadTaskStore,
    StaleVersionError,
    TaskClaimConflictError,
    TaskDescriptor,
    TaskNotFoundError,
    TaskOwnershipError,
)
from koda.squads.threads import SquadThreadStore


def _schema() -> str:
    return (os.environ.get("KNOWLEDGE_V2_POSTGRES_SCHEMA") or "knowledge_v2").strip() or "knowledge_v2"


def test_rejects_invalid_schema() -> None:
    with pytest.raises(ValueError):
        SquadTaskStore(dsn="postgresql://x/y", schema="bad-schema!")


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


async def _seed_thread(threads: SquadThreadStore) -> str:
    thread = await threads.create_thread(workspace_id="acme", squad_id="build", title="t")
    return thread.id


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_create_task_minimal(stores: tuple[SquadThreadStore, SquadTaskStore]) -> None:
    threads, tasks = stores
    tid = await _seed_thread(threads)
    task = await tasks.create_task(thread_id=tid, title="research fintechs", assigner_agent_id="PM")
    assert task.thread_id == tid
    assert task.title == "research fintechs"
    assert task.status == "pending"
    assert task.assigner_agent_id == "PM"
    assert task.assigned_agent_id is None
    assert task.version == 1


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_idempotent_create(stores: tuple[SquadThreadStore, SquadTaskStore]) -> None:
    threads, tasks = stores
    tid = await _seed_thread(threads)
    key = "build-landing-1"
    a = await tasks.create_task(thread_id=tid, title="A", assigner_agent_id="PM", idempotency_key=key)
    b = await tasks.create_task(thread_id=tid, title="A again", assigner_agent_id="PM", idempotency_key=key)
    assert a.id == b.id
    assert b.title == "A"  # original wins, not the duplicate


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_state_machine_happy_path(stores: tuple[SquadThreadStore, SquadTaskStore]) -> None:
    threads, tasks = stores
    tid = await _seed_thread(threads)
    task = await tasks.create_task(thread_id=tid, title="t", assigner_agent_id="PM")
    claimed = await tasks.claim_task(task_id=task.id, agent_id="FE")
    assert claimed.status == "claimed"
    assert claimed.assigned_agent_id == "FE"
    started = await tasks.update_task_status(task_id=task.id, new_status="in_progress", agent_id="FE")
    assert started.status == "in_progress"
    assert started.started_at is not None
    done = await tasks.complete_task(task_id=task.id, agent_id="FE", result_summary="shipped", deliverables=["a-1"])
    assert done.status == "done"
    assert done.completed_at is not None
    assert done.result_summary == "shipped"
    assert done.delivered_artifact_ids == ["a-1"]


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_illegal_transition_raises(stores: tuple[SquadThreadStore, SquadTaskStore]) -> None:
    threads, tasks = stores
    tid = await _seed_thread(threads)
    task = await tasks.create_task(thread_id=tid, title="t", assigner_agent_id="PM")
    with pytest.raises(IllegalTransitionError):
        await tasks.update_task_status(task_id=task.id, new_status="in_progress", agent_id="X")


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_terminal_immutable(stores: tuple[SquadThreadStore, SquadTaskStore]) -> None:
    threads, tasks = stores
    tid = await _seed_thread(threads)
    task = await tasks.create_task(thread_id=tid, title="t", assigner_agent_id="PM")
    await tasks.claim_task(task_id=task.id, agent_id="A")
    await tasks.update_task_status(task_id=task.id, new_status="in_progress", agent_id="A")
    await tasks.complete_task(task_id=task.id, agent_id="A")
    with pytest.raises(IllegalTransitionError):
        await tasks.update_task_status(task_id=task.id, new_status="in_progress", agent_id="A")


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_ownership_enforced(stores: tuple[SquadThreadStore, SquadTaskStore]) -> None:
    threads, tasks = stores
    tid = await _seed_thread(threads)
    task = await tasks.create_task(thread_id=tid, title="t", assigner_agent_id="PM")
    await tasks.claim_task(task_id=task.id, agent_id="A")
    with pytest.raises(TaskOwnershipError):
        await tasks.update_task_status(task_id=task.id, new_status="in_progress", agent_id="B")


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_concurrent_claim_one_wins(stores: tuple[SquadThreadStore, SquadTaskStore]) -> None:
    threads, tasks = stores
    tid = await _seed_thread(threads)
    task = await tasks.create_task(thread_id=tid, title="t", assigner_agent_id="PM")

    async def attempt(agent: str) -> TaskDescriptor | TaskClaimConflictError:
        try:
            return await tasks.claim_task(task_id=task.id, agent_id=agent)
        except TaskClaimConflictError as exc:
            return exc

    a, b = await asyncio.gather(attempt("A"), attempt("B"))
    successes = [r for r in (a, b) if isinstance(r, TaskDescriptor)]
    failures = [r for r in (a, b) if isinstance(r, TaskClaimConflictError)]
    assert len(successes) == 1
    assert len(failures) == 1


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_cross_instance_claim_race(clean_state: str) -> None:
    threads = SquadThreadStore(dsn=clean_state, schema=_schema())
    s1 = SquadTaskStore(dsn=clean_state, schema=_schema())
    s2 = SquadTaskStore(dsn=clean_state, schema=_schema())
    try:
        thread = await threads.create_thread(workspace_id="acme", squad_id="build", title="t")
        task = await s1.create_task(thread_id=thread.id, title="t", assigner_agent_id="PM")

        async def attempt(store: SquadTaskStore, agent: str) -> TaskDescriptor | TaskClaimConflictError:
            try:
                return await store.claim_task(task_id=task.id, agent_id=agent)
            except TaskClaimConflictError as exc:
                return exc

        a, b = await asyncio.gather(attempt(s1, "P1"), attempt(s2, "P2"))
        winners = [r for r in (a, b) if isinstance(r, TaskDescriptor)]
        losers = [r for r in (a, b) if isinstance(r, TaskClaimConflictError)]
        assert len(winners) == 1
        assert len(losers) == 1
    finally:
        with suppress(Exception):
            await threads.close()
        with suppress(Exception):
            await s1.close()
        with suppress(Exception):
            await s2.close()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_stale_version_detection(stores: tuple[SquadThreadStore, SquadTaskStore]) -> None:
    threads, tasks = stores
    tid = await _seed_thread(threads)
    task = await tasks.create_task(thread_id=tid, title="t", assigner_agent_id="PM")
    claimed = await tasks.claim_task(task_id=task.id, agent_id="A")
    # Successive update advances version. Reusing the original `task.version` (1)
    # against the now-bumped version (2) must raise StaleVersionError.
    with pytest.raises(StaleVersionError):
        await tasks.update_task_status(
            task_id=task.id,
            new_status="in_progress",
            agent_id="A",
            expected_version=task.version,
        )
    # Same call with the right version succeeds.
    await tasks.update_task_status(
        task_id=task.id,
        new_status="in_progress",
        agent_id="A",
        expected_version=claimed.version,
    )


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_claim_unknown_task_raises(stores: tuple[SquadThreadStore, SquadTaskStore]) -> None:
    _, tasks = stores
    with pytest.raises(TaskNotFoundError):
        await tasks.claim_task(task_id=str(uuid.uuid4()), agent_id="X")


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_list_tasks_filters(stores: tuple[SquadThreadStore, SquadTaskStore]) -> None:
    threads, tasks = stores
    tid = await _seed_thread(threads)
    a = await tasks.create_task(thread_id=tid, title="A", assigner_agent_id="PM")
    b = await tasks.create_task(thread_id=tid, title="B", assigner_agent_id="PM")
    await tasks.claim_task(task_id=a.id, agent_id="W")
    pending = await tasks.list_tasks(thread_id=tid, status="pending")
    assert {t.id for t in pending} == {b.id}
    claimed = await tasks.list_tasks(thread_id=tid, status="claimed")
    assert {t.id for t in claimed} == {a.id}
    by_agent = await tasks.list_tasks(assigned_agent_id="W")
    assert {t.id for t in by_agent} == {a.id}


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_escalate_records_reason(stores: tuple[SquadThreadStore, SquadTaskStore]) -> None:
    threads, tasks = stores
    tid = await _seed_thread(threads)
    task = await tasks.create_task(thread_id=tid, title="t", assigner_agent_id="PM")
    await tasks.claim_task(task_id=task.id, agent_id="A")
    await tasks.update_task_status(task_id=task.id, new_status="in_progress", agent_id="A")
    escalated = await tasks.escalate_task(task_id=task.id, agent_id="A", reason="provider down")
    assert escalated.status == "escalated"
    assert escalated.error_message == "provider down"
    assert escalated.completed_at is not None


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_escalate_emits_audit_event(stores: tuple[SquadThreadStore, SquadTaskStore]) -> None:
    """Escalation surfaces in audit_events with task_id + reason for governance."""
    from unittest.mock import patch

    threads, tasks = stores
    tid = await _seed_thread(threads)
    task = await tasks.create_task(thread_id=tid, title="t", assigner_agent_id="PM")
    await tasks.claim_task(task_id=task.id, agent_id="A")
    await tasks.update_task_status(task_id=task.id, new_status="in_progress", agent_id="A")
    with patch("koda.control_plane.audit.record_audit_event") as mock_record:
        await tasks.escalate_task(task_id=task.id, agent_id="A", reason="provider down")
    assert mock_record.called
    args, kwargs = mock_record.call_args
    assert args[0] == "A"
    assert kwargs["event_type"] == "squad.task.escalated"
    assert kwargs["details"]["task_id"] == task.id
    assert kwargs["details"]["reason"] == "provider down"
    assert kwargs["details"]["thread_id"] == tid
