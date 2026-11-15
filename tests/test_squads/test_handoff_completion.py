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
from collections.abc import AsyncIterator, Iterator
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
    follow_ups = await _post_process(
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
    )
    # The queue worker runs these once it releases the per-user lock (D-019).
    assert follow_ups is not None
    await follow_ups()


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
