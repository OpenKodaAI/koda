"""Tests for squad dashboard projections."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import suppress
from decimal import Decimal

import pytest

from koda.squads.coordinator import REQUIRED_COORDINATOR_TOOL_IDS, CoordinatorService
from koda.squads.projections import (
    get_squad_metrics,
    get_thread_overview,
    list_squad_activity,
    list_squad_overviews,
)
from koda.squads.tasks import SquadTaskStore
from koda.squads.threads import SquadThreadStore


def _schema() -> str:
    return (os.environ.get("KNOWLEDGE_V2_POSTGRES_SCHEMA") or "knowledge_v2").strip() or "knowledge_v2"


def _eligible_spec() -> dict[str, object]:
    return {"tool_policy": {"allowed_tool_ids": list(REQUIRED_COORDINATOR_TOOL_IDS)}}


def test_list_overviews_rejects_invalid_schema() -> None:
    import asyncio

    async def go() -> None:
        with pytest.raises(ValueError):
            await list_squad_overviews(dsn="postgresql://x/y", schema="bad-schema!")

    asyncio.run(go())


@pytest.fixture
async def clean_state(migrated_postgres: str) -> AsyncIterator[str]:
    import asyncpg  # type: ignore[import-not-found]

    schema = _schema()
    conn = await asyncpg.connect(migrated_postgres)
    try:
        await conn.execute(f'TRUNCATE TABLE "{schema}"."squad_coordinator_history" RESTART IDENTITY')
        await conn.execute(f'TRUNCATE TABLE "{schema}"."squad_coordinator_state"')
        await conn.execute(
            f'TRUNCATE TABLE "{schema}"."squad_message_recipients", "{schema}"."squad_messages" RESTART IDENTITY'
        )
        await conn.execute(f'TRUNCATE TABLE "{schema}"."squad_tasks"')
        await conn.execute(f'TRUNCATE TABLE "{schema}"."squad_thread_participants"')
        await conn.execute(f'TRUNCATE TABLE "{schema}"."squad_threads"')
    finally:
        await conn.close()
    yield migrated_postgres


@pytest.fixture
async def stores(
    clean_state: str,
) -> AsyncIterator[tuple[SquadThreadStore, SquadTaskStore, CoordinatorService]]:
    threads = SquadThreadStore(dsn=clean_state, schema=_schema())
    tasks = SquadTaskStore(dsn=clean_state, schema=_schema())
    coord = CoordinatorService(dsn=clean_state, schema=_schema())
    try:
        yield threads, tasks, coord
    finally:
        with suppress(Exception):
            await threads.close()
        with suppress(Exception):
            await tasks.close()
        with suppress(Exception):
            await coord.close()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_list_overviews_empty_when_no_threads(clean_state: str) -> None:
    overviews = await list_squad_overviews(dsn=clean_state, schema=_schema())
    assert overviews == []


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_list_overviews_aggregates_threads_and_tasks(
    stores: tuple[SquadThreadStore, SquadTaskStore, CoordinatorService],
    clean_state: str,
) -> None:
    threads, tasks, coord = stores
    # Two squads: "build" with 2 threads + 3 tasks; "ops" with 1 thread + 0 tasks.
    t1 = await threads.create_thread(workspace_id="acme", squad_id="build", title="A")
    t2 = await threads.create_thread(workspace_id="acme", squad_id="build", title="B")
    await threads.update_thread_status(t2.id, "completed")
    t3 = await threads.create_thread(workspace_id="acme", squad_id="ops", title="C")
    # Tasks for build
    a = await tasks.create_task(thread_id=t1.id, title="t-a", assigner_agent_id="PM")
    b = await tasks.create_task(thread_id=t1.id, title="t-b", assigner_agent_id="PM")
    # The third task stays in `pending` to drive the counts assertion below.
    await tasks.create_task(thread_id=t1.id, title="t-c", assigner_agent_id="PM")
    await tasks.claim_task(task_id=a.id, agent_id="W1")
    await tasks.update_task_status(task_id=a.id, new_status="in_progress", agent_id="W1")
    await tasks.claim_task(task_id=b.id, agent_id="W2")
    # Add participants
    await threads.add_participant(thread_id=t1.id, agent_id="FE", role="worker")
    await threads.add_participant(thread_id=t1.id, agent_id="BE", role="worker")
    await threads.add_participant(thread_id=t2.id, agent_id="FE", role="worker")
    await threads.add_participant(thread_id=t3.id, agent_id="OPS", role="worker")
    # Coordinator
    await coord.elect(squad_id="build", agent_id="PM", triggered_by="admin", agent_spec=_eligible_spec())

    overviews = await list_squad_overviews(dsn=clean_state, schema=_schema())
    by_squad = {ov.squad_id: ov for ov in overviews}
    assert set(by_squad) == {"build", "ops"}

    build = by_squad["build"]
    assert build.workspace_id == "acme"
    assert build.coordinator_agent_id == "PM"
    assert build.thread_counts == {"open": 1, "paused": 0, "completed": 1, "archived": 0}
    assert build.task_counts["pending"] == 1
    assert build.task_counts["claimed"] == 1
    assert build.task_counts["in_progress"] == 1
    assert build.task_counts["done"] == 0
    assert build.member_count == 2  # FE + BE (distinct active across threads)

    ops = by_squad["ops"]
    assert ops.workspace_id == "acme"
    assert ops.coordinator_agent_id is None
    assert ops.thread_counts["open"] == 1
    assert ops.task_counts["pending"] == 0
    assert ops.member_count == 1


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_list_overviews_filters_by_workspace(
    stores: tuple[SquadThreadStore, SquadTaskStore, CoordinatorService],
    clean_state: str,
) -> None:
    threads, _, _ = stores
    await threads.create_thread(workspace_id="acme", squad_id="build", title="A")
    await threads.create_thread(workspace_id="initech", squad_id="ops", title="B")
    only_acme = await list_squad_overviews(dsn=clean_state, schema=_schema(), workspace_id="acme")
    assert {ov.squad_id for ov in only_acme} == {"build"}


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_get_thread_overview_returns_none_for_missing(clean_state: str) -> None:
    overview = await get_thread_overview(
        "00000000-0000-0000-0000-0000000000ff",
        dsn=clean_state,
        schema=_schema(),
    )
    assert overview is None


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_get_thread_overview_bundles_data(
    stores: tuple[SquadThreadStore, SquadTaskStore, CoordinatorService],
    clean_state: str,
) -> None:
    threads, tasks, coord = stores
    thread = await threads.create_thread(
        workspace_id="acme",
        squad_id="build",
        title="Landing",
        coordinator_agent_id="PM",
    )
    await threads.add_participant(thread_id=thread.id, agent_id="FE", role="worker")
    await threads.add_participant(thread_id=thread.id, agent_id="BE", role="worker")
    # Coordinator state row (separate from participant role)
    await coord.elect(squad_id="build", agent_id="PM", triggered_by="admin", agent_spec=_eligible_spec())
    # Messages
    await threads.post_thread_message(thread_id=thread.id, from_agent="user:op", content="kickoff")
    await threads.post_thread_message(thread_id=thread.id, from_agent="PM", content="splitting work")
    # Tasks: one open, one done
    open_task = await tasks.create_task(thread_id=thread.id, title="open-t", assigner_agent_id="PM")
    done_task = await tasks.create_task(thread_id=thread.id, title="done-t", assigner_agent_id="PM")
    await tasks.claim_task(task_id=done_task.id, agent_id="FE")
    await tasks.update_task_status(task_id=done_task.id, new_status="in_progress", agent_id="FE")
    await tasks.complete_task(task_id=done_task.id, agent_id="FE")

    overview = await get_thread_overview(thread.id, dsn=clean_state, schema=_schema())
    assert overview is not None
    assert overview.thread.id == thread.id
    assert overview.coordinator_agent_id == "PM"
    member_ids = {p.agent_id for p in overview.participants}
    assert {"FE", "BE", "PM"} <= member_ids
    contents = [m["content"] for m in overview.recent_messages]
    assert "splitting work" in contents
    active_ids = {t.id for t in overview.active_tasks}
    assert open_task.id in active_ids
    assert done_task.id not in active_ids
    assert overview.open_task_count == 1
    assert overview.done_task_count == 1
    assert isinstance(overview.thread.cost_usd_accum, Decimal)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_list_squad_activity_unions_history_and_messages(
    stores: tuple[SquadThreadStore, SquadTaskStore, CoordinatorService],
    clean_state: str,
) -> None:
    threads, _tasks, coord = stores
    thread = await threads.create_thread(workspace_id="acme", squad_id="build", title="t")
    # Coordinator history (no thread_id)
    await coord.elect(
        squad_id="build",
        agent_id="PM",
        triggered_by="admin",
        reason="kickoff",
        agent_spec=_eligible_spec(),
    )
    # System event message (with thread_id) — emit via thread_store directly
    await threads.post_thread_message(
        thread_id=thread.id,
        from_agent="system",
        content="[elected] coordinator changed: (none) -> PM",
        message_type="system_event",
        metadata={"event_type": "coordinator_changed", "kind": "elected"},
    )
    # Non-system_event messages should NOT show up
    await threads.post_thread_message(
        thread_id=thread.id,
        from_agent="user:op",
        content="random user input",
        message_type="user_input",
    )

    entries = await list_squad_activity(squad_id="build", dsn=clean_state, schema=_schema())
    assert len(entries) >= 2
    sources = {e.source for e in entries}
    assert sources == {"system_event", "coordinator"}
    # The system_event row carries a thread_id; the history row does not.
    sys_event = next(e for e in entries if e.source == "system_event")
    coord_event = next(e for e in entries if e.source == "coordinator")
    assert sys_event.thread_id == thread.id
    assert coord_event.thread_id is None
    assert sys_event.event_type == "coordinator_changed"
    assert coord_event.event_type == "elected"
    # Sanity: random user_input message did NOT leak into the activity feed.
    assert all("random user input" not in (e.summary or "") for e in entries)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_get_squad_metrics_aggregates_costs_and_tasks(
    stores: tuple[SquadThreadStore, SquadTaskStore, CoordinatorService],
    clean_state: str,
) -> None:
    threads, tasks, _coord = stores
    schema = _schema()
    t1 = await threads.create_thread(workspace_id="acme", squad_id="build", title="A")
    t2 = await threads.create_thread(workspace_id="acme", squad_id="build", title="B")
    await threads.update_thread_status(t2.id, "completed")
    a = await tasks.create_task(thread_id=t1.id, title="t-a", assigner_agent_id="PM")
    b = await tasks.create_task(thread_id=t1.id, title="t-b", assigner_agent_id="PM")
    await tasks.claim_task(task_id=b.id, agent_id="W")
    await tasks.update_task_status(task_id=b.id, new_status="in_progress", agent_id="W")
    await tasks.complete_task(task_id=b.id, agent_id="W")

    # Insert query_history rows tied to threads (the cost rollup trigger keeps
    # squad_threads.cost_usd_accum in sync; we read via the metrics projection).
    import asyncpg  # type: ignore[import-not-found]

    raw = await asyncpg.connect(clean_state)
    try:
        from datetime import UTC, datetime

        for agent_id, cost in [("PM", 0.10), ("PM", 0.05), ("FE", 0.20)]:
            await raw.execute(
                f"""INSERT INTO "{schema}"."query_history"
                        (agent_id, user_id, timestamp, query_text, response_text,
                         cost_usd, squad_thread_id)
                      VALUES ($1, 1, $2, 'q', 'r', $3, $4)""",
                agent_id,
                datetime.now(UTC),
                cost,
                t1.id,
            )
    finally:
        await raw.close()
    # Sanity: claim a task to leave one open
    _ = a

    metrics = await get_squad_metrics(squad_id="build", dsn=clean_state, schema=_schema())
    assert metrics.squad_id == "build"
    assert "acme" in metrics.workspace_ids
    assert metrics.open_thread_count == 1
    assert metrics.completed_thread_count == 1
    assert metrics.task_count_by_status.get("pending") == 1
    assert metrics.task_count_by_status.get("done") == 1
    by_agent = {row.agent_id: row for row in metrics.cost_by_agent}
    assert by_agent["PM"].query_count == 2
    assert by_agent["PM"].cost_usd == Decimal("0.15")
    assert by_agent["FE"].query_count == 1
    assert by_agent["FE"].cost_usd == Decimal("0.20")
    assert metrics.total_cost_usd == Decimal("0.35")
