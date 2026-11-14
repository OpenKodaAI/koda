"""Handoffs complete and unblock coordinator synthesis (D-074).

The coordinator engine records a handoff with status ``requested``. Once every
destination has returned its task_result, the post-turn synthesis must run and
the handoff must be marked ``returned``. Real thread and task stores on
Postgres; only the agent turn (``dispatch_squad_turn``) is stubbed.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.services.queue_manager import QueryContext, _maybe_enqueue_squad_coordinator_synthesis
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
            selected_agents=["FE", "QA"],
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
            for agent_id in ("FE", "QA")
        ],
        min_score=0.0,
    )


def _handoff_payloads(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in history:
        payload = (row.get("metadata") or {}).get("payload") or {}
        if isinstance(payload, dict) and payload.get("schema_version") == "handoff_event.v1":
            out.append(payload)
    return out


async def _finish_task(
    threads: SquadThreadStore, tasks: SquadTaskStore, *, thread_id: str, task_id: str, agent_id: str, parent: str
) -> int:
    await tasks.update_task_status(task_id=task_id, new_status="in_progress", agent_id=agent_id)
    await tasks.complete_task(task_id=task_id, agent_id=agent_id, result_summary=f"{agent_id} done")
    return await threads.post_thread_message(
        thread_id=thread_id,
        from_agent=agent_id,
        content=f"{agent_id} done",
        message_type="task_result",
        metadata={"parent_message_id": parent, "squad_task_id": task_id},
    )


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_synthesis_runs_after_every_handoff_destination_returns(
    stores: tuple[SquadThreadStore, SquadTaskStore],
) -> None:
    threads, tasks = stores
    thread = await threads.create_thread(
        workspace_id="acme",
        squad_id="build",
        title="room",
        owner_user_id=42,
        coordinator_agent_id="PM",
        participants=[("PM", "coordinator"), ("FE", "worker"), ("QA", "worker")],
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
    [requested] = _handoff_payloads(await threads.thread_history(thread_id=thread.id, limit=100))
    assert requested["status"] == "requested"

    await _finish_task(threads, tasks, thread_id=thread.id, task_id=fe_task_id, agent_id="FE", parent=parent)
    qa_msg_id = await _finish_task(
        threads, tasks, thread_id=thread.id, task_id=qa_task_id, agent_id="QA", parent=parent
    )

    dispatch = AsyncMock()
    with (
        patch("koda.squads.get_squad_thread_store", return_value=threads),
        patch("koda.squads.get_squad_task_store", return_value=tasks),
        patch("koda.squads.dispatch_squad_turn", dispatch),
    ):
        await _maybe_enqueue_squad_coordinator_synthesis(
            user_id=42,
            context=MagicMock(application=None, bot=None),
            ctx=QueryContext(
                provider="codex",
                work_dir="/tmp",
                model="stub",
                session_id="s-1",
                provider_session_id=None,
                system_prompt="system",
                agent_mode="autonomous",
                permission_mode="bypassPermissions",
                max_turns=1,
                executing_agent_id="QA",
                squad_thread_id=thread.id,
                squad_task_id=qa_task_id,
                parent_message_id=parent,
            ),
            response_text="QA done",
            squad_message_id=f"msg-{qa_msg_id}",
            artifact_ids=[],
        )

    dispatch.assert_awaited_once()
    call = dispatch.await_args.kwargs
    assert call["target_agent_id"] == "PM"
    assert call["metadata"]["delivery_intent"] == "final_synthesis"
    assert "FE / " in call["query_text"] and "QA / " in call["query_text"]
    payloads = _handoff_payloads(await threads.thread_history(thread_id=thread.id, limit=100))
    returned = [payload for payload in payloads if payload["status"] == "returned"]
    assert [payload["handoff_id"] for payload in returned] == [requested["handoff_id"]]
    assert returned[0]["destination_agent_ids"] == ["FE", "QA"]
