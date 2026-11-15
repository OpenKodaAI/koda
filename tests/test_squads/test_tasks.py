"""Tests for the squad task store (Postgres-backed)."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import suppress
from typing import Any

import pytest

from koda.squads.tasks import (
    IllegalTransitionError,
    SquadTaskStore,
    StaleVersionError,
    TaskClaimConflictError,
    TaskDependencyError,
    TaskDescriptor,
    TaskNotFoundError,
    TaskOwnershipError,
)
from koda.squads.threads import SquadThreadStore
from tests.postgres_fixtures import reset_squad_runtime_tables


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
async def test_coordinator_override_can_transition_assigned_task(
    stores: tuple[SquadThreadStore, SquadTaskStore],
) -> None:
    threads, tasks = stores
    tid = await _seed_thread(threads)
    task = await tasks.create_task(thread_id=tid, title="t", assigner_agent_id="PM")
    await tasks.claim_task(task_id=task.id, agent_id="A")

    updated = await tasks.update_task_status(
        task_id=task.id,
        new_status="in_progress",
        agent_id="PM",
        coordinator_override=True,
    )

    assert updated.status == "in_progress"
    assert updated.assigned_agent_id == "A"


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
async def test_preassigned_task_can_only_be_claimed_by_assignee(
    stores: tuple[SquadThreadStore, SquadTaskStore],
) -> None:
    threads, tasks = stores
    tid = await _seed_thread(threads)
    task = await tasks.create_task(
        thread_id=tid,
        title="backend api",
        assigner_agent_id="PM",
        assigned_agent_id="BE",
    )
    with pytest.raises(TaskClaimConflictError):
        await tasks.claim_task(task_id=task.id, agent_id="FE")
    claimed = await tasks.claim_task(task_id=task.id, agent_id="BE")
    assert claimed.assigned_agent_id == "BE"


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_dependency_references_must_exist_in_same_thread(
    stores: tuple[SquadThreadStore, SquadTaskStore],
) -> None:
    threads, tasks = stores
    tid = await _seed_thread(threads)
    with pytest.raises(TaskDependencyError):
        await tasks.create_task(
            thread_id=tid,
            title="bad",
            assigner_agent_id="PM",
            depends_on=[str(uuid.uuid4())],
        )


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_dependencies_must_be_done_before_in_progress(
    stores: tuple[SquadThreadStore, SquadTaskStore],
) -> None:
    threads, tasks = stores
    tid = await _seed_thread(threads)
    upstream = await tasks.create_task(thread_id=tid, title="research", assigner_agent_id="PM")
    dependent = await tasks.create_task(
        thread_id=tid,
        title="build",
        assigner_agent_id="PM",
        depends_on=[upstream.id],
    )
    await tasks.claim_task(task_id=dependent.id, agent_id="FE")
    with pytest.raises(TaskDependencyError):
        await tasks.update_task_status(task_id=dependent.id, new_status="in_progress", agent_id="FE")

    await tasks.claim_task(task_id=upstream.id, agent_id="PM")
    await tasks.update_task_status(task_id=upstream.id, new_status="in_progress", agent_id="PM")
    await tasks.complete_task(task_id=upstream.id, agent_id="PM")
    started = await tasks.update_task_status(task_id=dependent.id, new_status="in_progress", agent_id="FE")
    assert started.status == "in_progress"


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


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_a_new_claim_of_a_task_whose_earlier_claim_was_refused_is_renewed_and_counted(
    stores: tuple[SquadThreadStore, SquadTaskStore],
) -> None:
    """A refused claim the task leaves another way does not mark the next claim refused (D-097)."""
    threads, tasks = stores
    tid = await _seed_thread(threads)
    task = await tasks.create_task(thread_id=tid, title="t", assigner_agent_id="PM", assigned_agent_id="FE")
    await tasks.claim_task(task_id=task.id, agent_id="FE")
    # A worker refused its turn in a paused room; a coordinator then moved it back to pending.
    assert await tasks.release_refused_claim(task_id=task.id, agent_id="FE") is True
    await tasks.update_task_status(task_id=task.id, new_status="pending", agent_id="FE")

    claimed = await tasks.claim_task(task_id=task.id, agent_id="FE", ttl_seconds=60)

    assert "claim_refused" not in claimed.metadata
    # The live turn renews the new claim, and an expiry of it counts as one.
    assert await tasks.renew_claims(claims=[(task.id, "FE")], ttl_seconds=60) == 1
    pool = await tasks._ensure_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f'UPDATE "{_schema()}"."squad_tasks" SET claim_expires_at = NOW() - INTERVAL \'1 second\' WHERE id = $1',
            task.id,
        )
    [expired] = await tasks.sweep_expired_claims()
    assert expired.task_id == task.id
    assert expired.refused is False
    assert expired.expiry_count == 1


@pytest.fixture
def task_tool(
    stores: tuple[SquadThreadStore, SquadTaskStore], monkeypatch: pytest.MonkeyPatch
) -> Iterator[Callable[..., Awaitable[Any]]]:
    """``squad_task_update`` as agent FE calls it, against the real task store."""
    from unittest.mock import AsyncMock, Mock, patch

    from koda.services.tool_dispatcher import ToolContext, _handle_squad_task_update

    _threads, tasks = stores
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    ctx = ToolContext(
        user_id=42,
        chat_id=-42,
        work_dir="/tmp",
        user_data={},
        agent=None,
        agent_mode="normal",
        executing_agent_id="FE",
    )

    async def call(**params: Any) -> Any:
        return await _handle_squad_task_update(params, ctx)

    with (
        patch("koda.squads.get_squad_task_store", return_value=tasks),
        patch("koda.squads.get_squad_access_service", return_value=Mock(require_task_access=AsyncMock())),
    ):
        yield call


async def _claimed_task(stores: tuple[SquadThreadStore, SquadTaskStore]) -> TaskDescriptor:
    threads, tasks = stores
    task = await tasks.create_task(
        thread_id=await _seed_thread(threads), title="t", assigner_agent_id="PM", assigned_agent_id="FE"
    )
    return await tasks.claim_task(task_id=task.id, agent_id="FE")


@pytest.mark.postgres
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key",
    [
        "claim_expiry_count",
        "claim_refused",
        "claim_expires_at",
        "coordination_parent_message_id",
        "handoff_correlation_id",
        "operator_override",
    ],
)
async def test_an_agent_cannot_set_server_owned_task_metadata(
    stores: tuple[SquadThreadStore, SquadTaskStore], task_tool: Callable[..., Awaitable[Any]], key: str
) -> None:
    """An agent's metadata_patch may not touch the claim bookkeeping or the coordination fields (D-339)."""
    _threads, tasks = stores
    task = await _claimed_task(stores)

    result = await task_tool(task_id=task.id, new_status="in_progress", metadata_patch={"notes": "x", key: -5})

    assert not result.success
    assert key in result.output
    assert "cannot be set by an agent" in result.output
    after = await tasks.get_task(task.id)
    assert after is not None
    # Nothing of the call was applied: not the status, not the allowed key.
    assert after.status == "claimed" and after.version == task.version
    assert key not in after.metadata and "notes" not in after.metadata


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_an_agent_may_set_its_task_notes_and_the_server_keeps_full_access(
    stores: tuple[SquadThreadStore, SquadTaskStore], task_tool: Callable[..., Awaitable[Any]]
) -> None:
    _threads, tasks = stores
    task = await _claimed_task(stores)

    result = await task_tool(
        task_id=task.id, new_status="in_progress", metadata_patch={"notes": "halfway", "progress": 50}
    )

    assert result.success, result.output
    after = await tasks.get_task(task.id)
    assert after is not None and after.status == "in_progress"
    assert after.metadata["notes"] == "halfway" and after.metadata["progress"] == 50

    # The operator API writes keys an agent may not.
    overridden = await tasks.update_task_status(
        task_id=task.id,
        new_status="done",
        agent_id="PM",
        metadata_patch={"operator_override": True, "actor_type": "operator"},
        coordinator_override=True,
    )
    assert overridden.metadata["operator_override"] is True
    assert overridden.metadata["notes"] == "halfway"


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_the_router_still_counts_and_clears_claim_bookkeeping(
    stores: tuple[SquadThreadStore, SquadTaskStore],
) -> None:
    _threads, tasks = stores
    task = await _claimed_task(stores)
    assert await tasks.release_refused_claim(task_id=task.id, agent_id="FE") is True
    assert (await tasks.get_task(task.id)).metadata["claim_refused"] is True  # type: ignore[union-attr]
    [refused] = await tasks.sweep_expired_claims()
    assert refused.refused is True

    await tasks.claim_task(task_id=task.id, agent_id="FE")
    pool = await tasks._ensure_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f'UPDATE "{_schema()}"."squad_tasks" SET claim_expires_at = NOW() - INTERVAL \'1 second\' WHERE id = $1',
            task.id,
        )
    [expired] = await tasks.sweep_expired_claims()
    assert expired.expiry_count == 1
    after = await tasks.get_task(task.id)
    assert after is not None
    assert after.metadata["claim_expiry_count"] == 1 and "claim_refused" not in after.metadata


@pytest.mark.postgres
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key",
    ["claim_expiry_count", "claim_refused", "coordination_parent_message_id", "handoff_correlation_id"],
)
async def test_an_agent_cannot_create_a_task_with_server_owned_metadata(
    stores: tuple[SquadThreadStore, SquadTaskStore], monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    """squad_task_create applies the same allowlist to ``metadata`` as the update tools (D-339)."""
    from unittest.mock import AsyncMock, Mock, patch

    from koda.services.tool_dispatcher import ToolContext, _handle_squad_task_create

    threads, tasks = stores
    thread_id = await _seed_thread(threads)
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    ctx = ToolContext(
        user_id=42,
        chat_id=-42,
        work_dir="/tmp",
        user_data={},
        agent=None,
        agent_mode="normal",
        executing_agent_id="FE",
    )

    with (
        patch("koda.squads.get_squad_task_store", return_value=tasks),
        patch("koda.squads.get_squad_access_service", return_value=Mock(require_thread_access=AsyncMock())),
    ):
        refused = await _handle_squad_task_create(
            {"thread_id": thread_id, "title": "t", "assigned_agent_id": "FE", "metadata": {"notes": "x", key: -1000}},
            ctx,
        )
        allowed = await _handle_squad_task_create(
            {"thread_id": thread_id, "title": "u", "metadata": {"notes": "x", "progress": 0}}, ctx
        )

    assert not refused.success
    assert key in refused.output and "cannot be set by an agent" in refused.output
    assert allowed.success, allowed.output
    [created] = await tasks.list_tasks(thread_id=thread_id)
    assert created.title == "u"
    assert created.metadata == {"notes": "x", "progress": 0}
