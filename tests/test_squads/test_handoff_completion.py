"""Handoffs complete and unblock coordinator synthesis (D-074).

The coordinator engine records a handoff with status ``requested``. Once every
destination has finished its turn, the post-turn path must dispatch one
coordinator synthesis and record the handoff outcome: ``returned``, or
``failed`` (disclosed to synthesis) when a destination's run failed. Each
destination turn goes through the real ``_post_process``, so the task_result
it posts and the task status it advances are the production ones. Real thread
and task stores on Postgres; only the agent turns (``dispatch_squad_turn``)
and the run's non-squad bookkeeping are stubbed.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import ExitStack, suppress
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.services.queue_manager import (
    QueryContext,
    RunResult,
    _maybe_enqueue_squad_coordinator_synthesis,
    _post_process,
)
from koda.squads.coordinator_engine import (
    CoordinationDecision,
    CoordinationPlannerInput,
    CoordinationTask,
    SquadCoordinatorEngine,
)
from koda.squads.semantic_router import SemanticAgentScore, SemanticRoutingResult
from koda.squads.tasks import SquadTaskStore
from koda.squads.threads import SquadThreadStore
from tests.postgres_fixtures import reset_squad_runtime_tables


def _schema() -> str:
    return (os.environ.get("KNOWLEDGE_V2_POSTGRES_SCHEMA") or "knowledge_v2").strip() or "knowledge_v2"


@pytest.fixture
async def stores(migrated_postgres: str) -> AsyncIterator[tuple[SquadThreadStore, SquadTaskStore]]:
    import asyncpg  # type: ignore[import-not-found]

    conn = await asyncpg.connect(migrated_postgres)
    try:
        await reset_squad_runtime_tables(conn, _schema())
    finally:
        await conn.close()
    threads = SquadThreadStore(dsn=migrated_postgres, schema=_schema())
    tasks = SquadTaskStore(dsn=migrated_postgres, schema=_schema())
    try:
        yield threads, tasks
    finally:
        with suppress(Exception):
            await threads.close()
        with suppress(Exception):
            await tasks.close()


class _HandoffPlanner:
    async def plan(self, planner_input: CoordinationPlannerInput) -> CoordinationDecision:
        return CoordinationDecision(
            mode="handoff",
            confidence=0.86,
            reasoning_summary="Consult FE and QA before the final answer.",
            tasks=[
                CoordinationTask(key="build", title="Build", agent_id="FE", kind="frontend", objective="Build it"),
                CoordinationTask(key="review", title="Review", agent_id="QA", kind="review", objective="Review it"),
            ],
            # UX is selected but gets no task, so it is never contacted and cannot be a destination.
            selected_agents=["FE", "QA", "UX"],
            final_response_strategy="coordinator_synthesis_after_all_task_results",
        )


def _semantic_result() -> SemanticRoutingResult:
    return SemanticRoutingResult(
        available=True,
        model_name="test-model",
        scores=[
            SemanticAgentScore(
                agent_id=agent_id,
                score=0.9,
                positive_score=0.9,
                negative_score=0.0,
                summary_text=agent_id,
                is_coordinator=False,
            )
            for agent_id in ("FE", "QA", "UX")
        ],
        min_score=0.0,
    )


def _handoff_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in reversed(history)
        if ((row.get("metadata") or {}).get("payload") or {}).get("schema_version") == "handoff_event.v1"
    ]


def _ctx(*, thread_id: str, task_id: str, agent_id: str, parent: str) -> QueryContext:
    return QueryContext(
        provider="codex",
        work_dir="/tmp",
        model="stub",
        session_id=None,
        provider_session_id=None,
        system_prompt="system",
        agent_mode="autonomous",
        permission_mode="bypassPermissions",
        max_turns=1,
        executing_agent_id=agent_id,
        squad_thread_id=thread_id,
        squad_task_id=task_id,
        parent_message_id=parent,
    )


@pytest.fixture
def turn_stubs(stores: tuple[SquadThreadStore, SquadTaskStore]) -> Iterator[AsyncMock]:
    threads, tasks = stores
    dispatch = AsyncMock()
    with ExitStack() as stack:
        stack.enter_context(patch("koda.squads.get_squad_thread_store", return_value=threads))
        stack.enter_context(patch("koda.squads.get_squad_task_store", return_value=tasks))
        stack.enter_context(patch("koda.squads.dispatch_squad_turn", dispatch))
        stack.enter_context(patch("koda.services.queue_manager.asyncio.sleep", AsyncMock()))
        stack.enter_context(patch("koda.services.queue_manager.save_user_cost"))
        stack.enter_context(patch("koda.services.queue_manager.log_query", return_value=1))
        stack.enter_context(patch("koda.memory.config.MEMORY_ENABLED", False))
        stack.enter_context(patch("koda.services.cache_config.CACHE_ENABLED", False))
        stack.enter_context(patch("koda.services.cache_config.SCRIPT_LIBRARY_ENABLED", False))
        yield dispatch


async def _start_handoff(threads: SquadThreadStore, tasks: SquadTaskStore) -> tuple[str, str, dict[str, str]]:
    thread = await threads.create_thread(
        workspace_id="acme",
        squad_id="build",
        title="room",
        owner_user_id=42,
        coordinator_agent_id="PM",
        participants=[("PM", "coordinator"), ("FE", "worker"), ("QA", "worker"), ("UX", "worker")],
    )
    user_msg_id = await threads.post_thread_message(
        thread_id=thread.id, from_agent="user:alice", content="Ship the page", message_type="user_input"
    )
    parent = f"msg-{user_msg_id}"
    execution = await SquadCoordinatorEngine(
        thread_store=threads, task_store=tasks, planner=_HandoffPlanner()
    ).coordinate_user_input(
        text="Ship the page",
        thread=thread,
        participants=await threads.list_participants(thread_id=thread.id),
        coordinator_agent_id="PM",
        capability_hints={},
        semantic_result=_semantic_result(),
        dispatch=AsyncMock(return_value=None),
        parent_message_id=parent,
    )
    assert execution.coordinated is True
    fe_task_id, qa_task_id = execution.task_ids
    return thread.id, parent, {"FE": fe_task_id, "QA": qa_task_id}


async def _finish_turn(*, thread_id: str, parent: str, task_id: str, agent_id: str, error: bool = False) -> None:
    context = MagicMock(application=None, bot=None)
    context.user_data = {"total_cost": 0.0, "query_count": 0}
    follow_ups: list[Callable[[], Awaitable[None]]] = []
    await _post_process(
        42,
        context,
        RunResult(
            provider="codex",
            model="stub",
            result=f"{agent_id} provider error" if error else f"{agent_id} done",
            session_id="",
            provider_session_id=None,
            cost_usd=0.0,
            error=error,
            stop_reason="error" if error else "completed",
        ),
        "task request",
        "/tmp",
        "stub",
        ctx=_ctx(thread_id=thread_id, task_id=task_id, agent_id=agent_id, parent=parent),
        squad_follow_ups=follow_ups,
    )
    # The queue worker runs these once it releases the per-user lock (D-019).
    [follow_up] = follow_ups
    await follow_up()


def _final_syntheses(dispatch: AsyncMock) -> list[dict[str, Any]]:
    return [
        call.kwargs
        for call in dispatch.await_args_list
        if (call.kwargs.get("metadata") or {}).get("delivery_intent") == "final_synthesis"
    ]


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_synthesis_runs_once_after_every_handoff_destination_returns(
    stores: tuple[SquadThreadStore, SquadTaskStore], turn_stubs: AsyncMock
) -> None:
    threads, tasks = stores
    thread_id, parent, task_ids = await _start_handoff(threads, tasks)
    [requested] = _handoff_rows(await threads.thread_history(thread_id=thread_id, limit=100))
    assert requested["metadata"]["payload"]["status"] == "requested"
    assert requested["metadata"]["payload"]["destination_agent_ids"] == ["FE", "QA"]

    await _finish_turn(thread_id=thread_id, parent=parent, task_id=task_ids["FE"], agent_id="FE")
    assert _final_syntheses(turn_stubs) == []
    await _finish_turn(thread_id=thread_id, parent=parent, task_id=task_ids["QA"], agent_id="QA")

    [synthesis] = _final_syntheses(turn_stubs)
    assert synthesis["target_agent_id"] == "PM"
    assert "FE / " in synthesis["query_text"] and "QA / " in synthesis["query_text"]
    assert "Timeouts/bloqueios declarados" not in synthesis["query_text"]
    rows = _handoff_rows(await threads.thread_history(thread_id=thread_id, limit=100))
    assert [row["metadata"]["payload"]["status"] for row in rows] == ["requested", "returned"]
    returned = rows[1]
    assert returned["metadata"]["payload"]["handoff_id"] == requested["metadata"]["payload"]["handoff_id"]
    assert returned["metadata"]["payload"]["destination_agent_ids"] == ["FE", "QA"]
    # A status change is not a new request: it is completed, and nobody's inbox gets it.
    assert returned["metadata"]["delivery_status"] == "completed"
    assert returned["to_agent_ids"] == []


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_failed_destination_marks_the_handoff_failed_and_discloses_it(
    stores: tuple[SquadThreadStore, SquadTaskStore], turn_stubs: AsyncMock
) -> None:
    threads, tasks = stores
    thread_id, parent, task_ids = await _start_handoff(threads, tasks)

    await _finish_turn(thread_id=thread_id, parent=parent, task_id=task_ids["FE"], agent_id="FE")
    await _finish_turn(thread_id=thread_id, parent=parent, task_id=task_ids["QA"], agent_id="QA", error=True)

    qa_task = await tasks.get_task(task_ids["QA"])
    assert qa_task is not None and qa_task.status == "failed"
    [synthesis] = _final_syntheses(turn_stubs)
    assert "Timeouts/bloqueios declarados:\n- QA: failed" in synthesis["query_text"]
    rows = _handoff_rows(await threads.thread_history(thread_id=thread_id, limit=100))
    assert [row["metadata"]["payload"]["status"] for row in rows] == ["requested", "failed"]
    assert rows[1]["metadata"]["delivery_status"] == "failed"


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_destinations_finishing_together_record_one_returned_event(
    stores: tuple[SquadThreadStore, SquadTaskStore], turn_stubs: AsyncMock
) -> None:
    threads, tasks = stores
    thread_id, parent, task_ids = await _start_handoff(threads, tasks)
    with patch("koda.services.queue_manager._maybe_enqueue_squad_coordinator_synthesis", AsyncMock()):
        for agent_id in ("FE", "QA"):
            await _finish_turn(thread_id=thread_id, parent=parent, task_id=task_ids[agent_id], agent_id=agent_id)

    # Both post-turn checks read the thread before either records the outcome.
    barrier = asyncio.Barrier(2)
    read_history = threads.thread_history

    async def history_then_wait(**kwargs: Any) -> list[dict[str, Any]]:
        rows = await read_history(**kwargs)
        await barrier.wait()
        return rows

    with patch.object(threads, "thread_history", history_then_wait):
        await asyncio.gather(
            *(
                _maybe_enqueue_squad_coordinator_synthesis(
                    user_id=42,
                    context=MagicMock(application=None, bot=None),
                    ctx=_ctx(thread_id=thread_id, task_id=task_ids[agent_id], agent_id=agent_id, parent=parent),
                    response_text=f"{agent_id} done",
                    squad_message_id=None,
                    artifact_ids=[],
                )
                for agent_id in ("FE", "QA")
            )
        )

    rows = _handoff_rows(await threads.thread_history(thread_id=thread_id, limit=100))
    assert [row["metadata"]["payload"]["status"] for row in rows] == ["requested", "returned"]


@pytest.mark.parametrize(
    ("status", "ending"),
    [("failed", "which failed."), ("cancelled", "which was cancelled."), ("escalated", "which was escalated.")],
)
async def test_a_task_whose_dependency_ended_is_cancelled_by_the_system_with_a_reason_that_reads(
    status: str, ending: str
) -> None:
    from types import SimpleNamespace

    from koda.services import queue_manager as qm

    task = SimpleNamespace(id="task-review", metadata={"coordination_parent_message_id": "msg-1"})
    dependency = SimpleNamespace(id="task-build", title="Build", status=status)
    with patch.object(qm, "_persist_squad_turn_result", AsyncMock(return_value=(None, []))) as persist:
        await qm._cancel_squad_task_after_its_dependency_ended(
            ctx=_ctx(thread_id="thread-1", task_id="task-build", agent_id="FE", parent="msg-1"),
            task=task,
            dependency=dependency,
            assignee="QA",
            coordinator="PM",
        )

    kwargs = persist.await_args.kwargs
    assert kwargs["response_text"] == f"Not run: this task depends on task task-build (Build), {ending}"
    assert kwargs["cancelled"] is True
    # The result is for QA's task, but QA never ran, so the system posts it.
    assert kwargs["ctx"].executing_agent_id == "QA"
    assert kwargs["posted_by"] == "system"


async def _strand_handoff(threads: SquadThreadStore, tasks: SquadTaskStore) -> tuple[str, str, dict[str, str]]:
    """A handoff whose destinations both answered while the check after their turns was lost."""
    thread_id, parent, task_ids = await _start_handoff(threads, tasks)
    with patch("koda.services.queue_manager._maybe_enqueue_squad_coordinator_synthesis", AsyncMock()):
        for agent_id in ("FE", "QA"):
            await _finish_turn(thread_id=thread_id, parent=parent, task_id=task_ids[agent_id], agent_id=agent_id)
    return thread_id, parent, task_ids


def _router(threads: SquadThreadStore, tasks: SquadTaskStore, **kwargs: Any) -> Any:
    from koda.squads.router import SquadRouter

    return SquadRouter(task_store=tasks, thread_store=threads, **kwargs)


async def _sweep(router: Any) -> int:
    """One sweep with no grace period; returns the number of open handoffs it checked."""
    with patch("koda.squads.router._HANDOFF_COMPLETION_GRACE_S", 0.0):
        return int((await router.sweep_once()).open_handoffs_checked)


async def _handoff_statuses(threads: SquadThreadStore, thread_id: str) -> list[str]:
    rows = _handoff_rows(await threads.thread_history(thread_id=thread_id, limit=100))
    return [row["metadata"]["payload"]["status"] for row in rows]


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_the_sweep_queues_nothing_for_a_destination_whose_task_ended_without_a_result(
    stores: tuple[SquadThreadStore, SquadTaskStore], turn_stubs: AsyncMock
) -> None:
    threads, tasks = stores
    thread_id, parent, task_ids = await _start_handoff(threads, tasks)
    with patch("koda.services.queue_manager._maybe_enqueue_squad_coordinator_synthesis", AsyncMock()):
        await _finish_turn(thread_id=thread_id, parent=parent, task_id=task_ids["FE"], agent_id="FE")
    # QA's task ends without a turn, as the squad_task_update tool can end it, so QA posts no result.
    await tasks.update_task_status(
        task_id=task_ids["QA"], new_status="cancelled", agent_id="PM", coordinator_override=True
    )

    assert await _sweep(_router(threads, tasks)) == 1

    # The sweep does not answer for QA, so the gate still waits for QA's result.
    assert _final_syntheses(turn_stubs) == []
    assert await _handoff_statuses(threads, thread_id) == ["requested"]


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_the_sweep_queues_nothing_for_a_handoff_the_check_does_not_read(
    stores: tuple[SquadThreadStore, SquadTaskStore], turn_stubs: AsyncMock
) -> None:
    from koda.services.queue_manager import complete_open_squad_handoff

    threads, tasks = stores
    thread_id, _parent, task_ids = await _strand_handoff(threads, tasks)

    await complete_open_squad_handoff(
        thread_id=thread_id, squad_task_id=task_ids["QA"], handoff_id="handoff-of-another-cycle"
    )

    assert _final_syntheses(turn_stubs) == []
    assert await _handoff_statuses(threads, thread_id) == ["requested"]


@pytest.mark.postgres
@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["paused", "completed", "archived"])
async def test_the_sweep_leaves_the_handoffs_of_a_thread_that_is_not_open(
    stores: tuple[SquadThreadStore, SquadTaskStore], turn_stubs: AsyncMock, status: str
) -> None:
    threads, tasks = stores
    thread_id, _parent, _task_ids = await _strand_handoff(threads, tasks)
    await threads.update_thread_status(thread_id, status)

    assert await _sweep(_router(threads, tasks)) == 0
    assert _final_syntheses(turn_stubs) == []


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_the_sweep_leaves_a_handoff_requested_before_its_cutoff(
    stores: tuple[SquadThreadStore, SquadTaskStore], turn_stubs: AsyncMock
) -> None:
    from koda.squads import router as router_mod

    threads, tasks = stores
    thread_id, _parent, _task_ids = await _strand_handoff(threads, tasks)
    pool = await threads._ensure_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f"""UPDATE "{_schema()}"."squad_messages"
                   SET created_at = NOW() - make_interval(secs => $2)
                 WHERE thread_id = $1 AND metadata_json->>'event_type' = 'handoff_event'""",
            thread_id,
            router_mod._HANDOFF_COMPLETION_MAX_AGE_S + 60.0,
        )

    assert await _sweep(_router(threads, tasks)) == 0
    assert _final_syntheses(turn_stubs) == []


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_a_handoff_the_sweep_cannot_close_does_not_keep_it_from_a_newer_one(
    stores: tuple[SquadThreadStore, SquadTaskStore], turn_stubs: AsyncMock
) -> None:
    from types import SimpleNamespace

    threads, tasks = stores
    older_thread_id, _parent, _task_ids = await _strand_handoff(threads, tasks)
    newer_thread_id, _parent, _task_ids = await _strand_handoff(threads, tasks)
    # The older cycle's synthesis is always refused, so its handoff stays open.
    turn_stubs.side_effect = lambda **kwargs: SimpleNamespace(dispatched=kwargs["thread"].id != older_thread_id)
    router = _router(threads, tasks, batch_size=1)

    for _ in range(2):
        assert await _sweep(router) == 1

    assert [call["thread"].id for call in _final_syntheses(turn_stubs)] == [older_thread_id, newer_thread_id]
    assert await _handoff_statuses(threads, older_thread_id) == ["requested"]
    assert await _handoff_statuses(threads, newer_thread_id) == ["requested", "returned"]


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_two_runtimes_sweeping_the_same_handoff_at_once_queue_one_synthesis(
    stores: tuple[SquadThreadStore, SquadTaskStore], turn_stubs: AsyncMock
) -> None:
    from types import SimpleNamespace

    threads, tasks = stores
    thread_id, _parent, _task_ids = await _strand_handoff(threads, tasks)
    first_dispatch_started = asyncio.Event()
    release_first_dispatch = asyncio.Event()

    async def dispatch(**kwargs: Any) -> Any:
        if (kwargs.get("metadata") or {}).get("delivery_intent") == "final_synthesis" and (
            not first_dispatch_started.is_set()
        ):
            first_dispatch_started.set()
            await release_first_dispatch.wait()
        return SimpleNamespace(dispatched=True)

    turn_stubs.side_effect = dispatch

    # The first runtime's sweep is still queueing the synthesis when the second runtime's sweep runs.
    first_sweep = asyncio.create_task(_sweep(_router(threads, tasks)))
    await asyncio.wait_for(first_dispatch_started.wait(), timeout=30)
    assert await _sweep(_router(threads, tasks)) == 0
    release_first_dispatch.set()
    assert await first_sweep == 1

    assert len(_final_syntheses(turn_stubs)) == 1
    assert await _handoff_statuses(threads, thread_id) == ["requested", "returned"]


async def _expire_claim(tasks: SquadTaskStore, task_id: str) -> None:
    """Move the task's claim deadline into the past, as a worker that went silent leaves it."""
    pool = await tasks._ensure_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f"""UPDATE "{_schema()}"."squad_tasks"
                   SET claim_expires_at = NOW() - INTERVAL '1 second'
                 WHERE id = $1 AND status = 'claimed'""",
            task_id,
        )


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_an_expired_claim_is_dispatched_again_to_its_planned_assignee(
    stores: tuple[SquadThreadStore, SquadTaskStore], turn_stubs: AsyncMock
) -> None:
    threads, tasks = stores
    _thread_id, parent, task_ids = await _start_handoff(threads, tasks)
    await _expire_claim(tasks, task_ids["QA"])

    report = await _router(threads, tasks).sweep_once()

    assert [claim.task_id for claim in report.expired_claims] == [task_ids["QA"]]
    qa_task = await tasks.get_task(task_ids["QA"])
    assert qa_task is not None
    # The planned assignee is kept and holds a fresh claim for the dispatched turn (D-097).
    assert qa_task.status == "claimed"
    assert qa_task.assigned_agent_id == "QA"
    assert qa_task.metadata["claim_expiry_count"] == 1
    [redispatch] = [call.kwargs for call in turn_stubs.await_args_list]
    assert redispatch["target_agent_id"] == "QA"
    assert redispatch["squad_task_id"] == task_ids["QA"]
    assert redispatch["parent_message_id"] == parent
    assert redispatch["delegation_request_id"] == f"coord-{task_ids['QA']}"
    assert f"Task request [review] {task_ids['QA']}" in redispatch["query_text"]


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_a_claim_that_expires_again_is_escalated_and_the_handoff_completes_as_failed(
    stores: tuple[SquadThreadStore, SquadTaskStore], turn_stubs: AsyncMock
) -> None:
    threads, tasks = stores
    thread_id, parent, task_ids = await _start_handoff(threads, tasks)
    await _finish_turn(thread_id=thread_id, parent=parent, task_id=task_ids["FE"], agent_id="FE")
    router = _router(threads, tasks)

    for _ in range(2):
        await _expire_claim(tasks, task_ids["QA"])
        await router.sweep_once()

    qa_task = await tasks.get_task(task_ids["QA"])
    assert qa_task is not None
    assert qa_task.status == "escalated"
    assert qa_task.assigned_agent_id == "QA"
    # The system posts QA's result, which says why, so the coordinator synthesis discloses it.
    history = await threads.thread_history(thread_id=thread_id, limit=100)
    [qa_result] = [
        row
        for row in history
        if row["type"] == "task_result" and (row.get("metadata") or {}).get("squad_task_id") == task_ids["QA"]
    ]
    assert qa_result["from"] == "system"
    assert qa_result["metadata"]["assigned_agent_id"] == "QA"
    assert qa_result["metadata"]["payload"]["status"] == "failed"
    assert "expired 2 times" in qa_result["content"]
    [synthesis] = _final_syntheses(turn_stubs)
    assert synthesis["target_agent_id"] == "PM"
    assert "Timeouts/bloqueios declarados:\n- QA: failed" in synthesis["query_text"]
    assert await _handoff_statuses(threads, thread_id) == ["requested", "failed"]


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_a_paused_thread_keeps_its_expired_claims_until_it_reopens(
    stores: tuple[SquadThreadStore, SquadTaskStore], turn_stubs: AsyncMock
) -> None:
    threads, tasks = stores
    thread_id, _parent, task_ids = await _start_handoff(threads, tasks)
    await threads.update_thread_status(thread_id, "paused")
    await _expire_claim(tasks, task_ids["QA"])
    router = _router(threads, tasks)

    assert (await router.sweep_once()).expired_claims == []
    qa_task = await tasks.get_task(task_ids["QA"])
    assert qa_task is not None and qa_task.status == "claimed"
    assert turn_stubs.await_count == 0

    await threads.update_thread_status(thread_id, "open")
    assert [claim.task_id for claim in (await router.sweep_once()).expired_claims] == [task_ids["QA"]]
    assert [call.kwargs["target_agent_id"] for call in turn_stubs.await_args_list] == ["QA"]


async def _leave_a_stale_task_of_an_earlier_cycle(tasks: SquadTaskStore, thread_id: str) -> str:
    """A task of an earlier cycle of the room that its worker started and never finished.

    It is ``in_progress``, so no claim of it expires and nothing ends it.
    """
    stale = await tasks.create_task(
        thread_id=thread_id,
        title="Old work",
        assigner_agent_id="PM",
        assigned_agent_id="UX",
        metadata={"coordination_parent_message_id": "msg-earlier-cycle"},
    )
    claimed = await tasks.claim_task(task_id=stale.id, agent_id="UX")
    await tasks.update_task_status(task_id=stale.id, new_status="in_progress", agent_id="UX")
    return claimed.id


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_a_stale_open_task_of_an_earlier_cycle_does_not_hold_a_later_handoff(
    stores: tuple[SquadThreadStore, SquadTaskStore], turn_stubs: AsyncMock
) -> None:
    threads, tasks = stores
    thread_id, parent, task_ids = await _start_handoff(threads, tasks)
    stale_id = await _leave_a_stale_task_of_an_earlier_cycle(tasks, thread_id)

    await _finish_turn(thread_id=thread_id, parent=parent, task_id=task_ids["FE"], agent_id="FE")
    assert _final_syntheses(turn_stubs) == []
    await _finish_turn(thread_id=thread_id, parent=parent, task_id=task_ids["QA"], agent_id="QA")

    # The check reads this cycle's tasks only (D-287).
    [synthesis] = _final_syntheses(turn_stubs)
    assert synthesis["target_agent_id"] == "PM"
    assert await _handoff_statuses(threads, thread_id) == ["requested", "returned"]
    stale = await tasks.get_task(stale_id)
    assert stale is not None and stale.status == "in_progress"


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_the_sweep_completes_a_handoff_beside_a_stale_open_task_of_an_earlier_cycle(
    stores: tuple[SquadThreadStore, SquadTaskStore], turn_stubs: AsyncMock
) -> None:
    threads, tasks = stores
    thread_id, _parent, _task_ids = await _strand_handoff(threads, tasks)
    await _leave_a_stale_task_of_an_earlier_cycle(tasks, thread_id)

    assert await _sweep(_router(threads, tasks)) == 1

    assert len(_final_syntheses(turn_stubs)) == 1
    assert await _handoff_statuses(threads, thread_id) == ["requested", "returned"]


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_list_tasks_reads_one_coordination_cycle(stores: tuple[SquadThreadStore, SquadTaskStore]) -> None:
    threads, tasks = stores
    thread_id, parent, task_ids = await _start_handoff(threads, tasks)
    await _leave_a_stale_task_of_an_earlier_cycle(tasks, thread_id)

    cycle = await tasks.list_tasks(thread_id=thread_id, coordination_parent_message_id=parent)

    assert sorted(task.id for task in cycle) == sorted(task_ids.values())


@pytest.fixture
def fresh_queues(monkeypatch: pytest.MonkeyPatch) -> None:
    """Module queue state of the runtime, empty for the test and restored after it."""
    from koda.services import queue_manager as qm

    for name in ("_user_queues", "_queue_workers", "_user_queue_task_ids", "_user_tasks", "_squad_turn_claims"):
        monkeypatch.setattr(qm, name, {}, raising=False)


async def _queue_turn_here(*, thread_id: str, task_id: str, agent_id: str, parent: str) -> None:
    """Queue the task's turn on this runtime's per-user queue, behind turns that keep it waiting."""
    from collections import defaultdict
    from types import SimpleNamespace

    from koda.services import queue_manager as qm

    with (
        patch.object(qm, "create_task", MagicMock(return_value=601)),
        patch.object(qm, "_persist_runtime_queue_item", AsyncMock()),
        patch.object(qm, "_ensure_queue_worker", AsyncMock()),
    ):
        await qm.enqueue_squad_agent_task(
            application=SimpleNamespace(user_data=defaultdict(dict), bot=None),
            user_id=42,
            chat_id=-42,
            query_text="task request",
            executing_agent_id=agent_id,
            squad_thread_id=thread_id,
            squad_task_id=task_id,
            parent_message_id=parent,
        )


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_a_task_whose_turn_waits_or_runs_here_keeps_its_claim_past_its_ttl(
    stores: tuple[SquadThreadStore, SquadTaskStore], turn_stubs: AsyncMock, fresh_queues: None
) -> None:
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from koda.services import queue_manager as qm

    threads, tasks = stores
    thread_id, parent, task_ids = await _start_handoff(threads, tasks)
    await _queue_turn_here(thread_id=thread_id, task_id=task_ids["QA"], agent_id="QA", parent=parent)
    router = _router(threads, tasks)

    # The turn waits behind others in the serial per-user queue for longer than the claim TTL.
    await _expire_claim(tasks, task_ids["QA"])
    assert (await router.sweep_once()).expired_claims == []
    waiting = await tasks.get_task(task_ids["QA"])
    assert waiting is not None and waiting.status == "claimed" and waiting.assigned_agent_id == "QA"
    assert waiting.claim_expires_at is not None and waiting.claim_expires_at > datetime.now(UTC)

    # The turn itself runs for longer than the claim TTL.
    async def _long_turn(*_args: Any, **_kwargs: Any) -> None:
        await _expire_claim(tasks, task_ids["QA"])
        assert (await router.sweep_once()).expired_claims == []

    with patch.object(qm, "_execute_single_task", AsyncMock(side_effect=_long_turn)) as execute:
        await qm._process_queue(42, SimpleNamespace(user_data={}, bot=None, application=None))
    execute.assert_awaited_once()

    # The task was never dispatched a second time, nor escalated, while its turn was alive here.
    assert turn_stubs.await_count == 0
    running = await tasks.get_task(task_ids["QA"])
    assert running is not None and running.status == "claimed"
    assert "claim_expiry_count" not in running.metadata

    # Once no turn of it is queued or running here, its claim expires as a silent worker's does.
    await _expire_claim(tasks, task_ids["QA"])
    assert [claim.task_id for claim in (await router.sweep_once()).expired_claims] == [task_ids["QA"]]
