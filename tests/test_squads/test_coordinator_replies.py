"""The squad coordinator always answers (D-015).

When the supervisor planner chooses ``ask_clarification``, ``decline`` or a
task-less ``handoff``, the Telegram and web handlers must still wake an agent
so the user gets a reply. These tests run the real coordinator engine and the
real thread and task stores on Postgres; only the agent turn itself
(``dispatch_squad_turn``) and the routing inputs that need a control plane or
an embedding model are stubbed.
"""

from __future__ import annotations

import functools
import json
import os
from collections.abc import AsyncIterator, Iterator
from contextlib import ExitStack, suppress
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest

from koda.control_plane import api as control_plane_api
from koda.handlers.squad_handlers import _notify_squad_targets
from koda.squads.capabilities import CapabilitySummary
from koda.squads.coordinator_engine import (
    CoordinationDecision,
    CoordinationPlannerInput,
    SquadCoordinatorEngine,
)
from koda.squads.semantic_router import SemanticAgentScore, SemanticRoutingResult
from koda.squads.tasks import SquadTaskStore
from koda.squads.threads import SquadThreadStore, ThreadDescriptor
from tests.postgres_fixtures import reset_squad_runtime_tables

USER_TEXT = "Preciso daquilo para amanhã"


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


class _NoTaskPlanner:
    def __init__(self, mode: str, selected_agents: list[str]) -> None:
        self._mode = mode
        self._selected_agents = selected_agents

    async def plan(self, planner_input: CoordinationPlannerInput) -> CoordinationDecision:
        return CoordinationDecision(
            mode=cast(Any, self._mode),
            confidence=0.7,
            reasoning_summary=f"planner chose {self._mode}",
            selected_agents=list(self._selected_agents),
            needs_user_clarification=self._mode == "ask_clarification",
        )


MODES = [
    pytest.param("ask_clarification", [], id="ask_clarification"),
    pytest.param("decline", [], id="decline"),
    pytest.param("handoff", ["FE"], id="handoff"),
]


async def _seed_thread(threads: SquadThreadStore) -> ThreadDescriptor:
    return await threads.create_thread(
        workspace_id="acme",
        squad_id="build",
        title="room",
        owner_user_id=42,
        coordinator_agent_id="PM",
        participants=[("PM", "coordinator"), ("FE", "worker"), ("QA", "worker")],
    )


def _semantic_result() -> SemanticRoutingResult:
    return SemanticRoutingResult(
        available=True,
        model_name="test-model",
        scores=[
            SemanticAgentScore(
                agent_id=agent_id,
                score=score,
                positive_score=score,
                negative_score=0.0,
                summary_text=f"{agent_id} summary",
                is_coordinator=False,
            )
            for agent_id, score in (("FE", 0.9), ("QA", 0.8))
        ],
        min_score=0.0,
    )


@pytest.fixture
def routing_stubs(stores: tuple[SquadThreadStore, SquadTaskStore]) -> Iterator[Any]:
    threads, tasks = stores
    dispatch = AsyncMock(return_value=SimpleNamespace(enqueued_task_id=1, message_id=None, to_dict=lambda: {}))
    summaries = [
        CapabilitySummary(agent_id="PM", display_name="PM", role="Coordinator", is_coordinator=True),
        CapabilitySummary(agent_id="FE", display_name="Frontend", role="Interface"),
        CapabilitySummary(agent_id="QA", display_name="QA", role="Quality"),
    ]
    no_mentions = SimpleNamespace(
        has_resolved_mentions=False,
        has_mentions=False,
        resolved_agent_ids=[],
        unresolved=[],
        ambiguous={},
    )
    triage = SimpleNamespace(awareness_agent_ids=[], proposal_candidates=[], to_dict=lambda: {})
    with ExitStack() as stack:
        stack.enter_context(patch("koda.config.SQUAD_COORDINATOR_MODE", "supervisor"))
        stack.enter_context(patch("koda.squads.get_squad_thread_store", return_value=threads))
        stack.enter_context(patch("koda.squads.get_squad_task_store", return_value=tasks))
        stack.enter_context(patch("koda.squads.build_squad_capability_summaries", AsyncMock(return_value=summaries)))
        stack.enter_context(
            patch(
                "koda.squads.get_squad_semantic_router",
                return_value=SimpleNamespace(rank_agents=AsyncMock(return_value=_semantic_result())),
            )
        )
        stack.enter_context(
            patch(
                "koda.squads.get_squad_mention_resolver",
                return_value=SimpleNamespace(resolve=AsyncMock(return_value=no_mentions)),
            )
        )
        stack.enter_context(
            patch(
                "koda.squads.get_squad_triage_service",
                return_value=SimpleNamespace(triage_user_input=AsyncMock(return_value=triage)),
            )
        )
        stack.enter_context(patch("koda.squads.dispatch_squad_turn", dispatch))
        yield SimpleNamespace(dispatch=dispatch, stack=stack)


def _use_planner(stubs: Any, mode: str, selected: list[str]) -> None:
    stubs.stack.enter_context(
        patch(
            "koda.squads.SquadCoordinatorEngine",
            functools.partial(SquadCoordinatorEngine, planner=_NoTaskPlanner(mode, selected)),
        )
    )


async def _assert_user_gets_a_reply(threads: SquadThreadStore, thread_id: str, dispatch: AsyncMock, mode: str) -> None:
    calls = [call.kwargs for call in dispatch.await_args_list]
    assert calls, "no agent was woken, so the user gets no reply"
    history = await threads.thread_history(thread_id=thread_id, limit=50)
    event_types = [(row.get("metadata") or {}).get("event_type") for row in history]
    assert "coordination_decision" in event_types
    assert "handoff_event" not in event_types
    if mode == "handoff":
        # A handoff with no task falls back to normal routing, which wakes the ranked specialists.
        assert [call["target_agent_id"] for call in calls] == ["FE", "QA"]
        assert all(call["query_text"] == USER_TEXT for call in calls)
    else:
        assert len(calls) == 1
        assert calls[0]["target_agent_id"] == "PM"
        assert USER_TEXT in calls[0]["query_text"]
        assert f"planner chose {mode}" in calls[0]["query_text"]


@pytest.mark.postgres
@pytest.mark.asyncio
@pytest.mark.parametrize(("mode", "selected"), MODES)
async def test_telegram_room_message_gets_a_reply_when_coordinator_dispatches_no_task(
    stores: tuple[SquadThreadStore, SquadTaskStore], routing_stubs: Any, mode: str, selected: list[str]
) -> None:
    threads, _tasks = stores
    thread = await _seed_thread(threads)
    user_msg_id = await threads.post_thread_message(
        thread_id=thread.id, from_agent="user:alice", content=USER_TEXT, message_type="user_input"
    )
    _use_planner(routing_stubs, mode, selected)

    await _notify_squad_targets(
        text=USER_TEXT,
        thread=thread,
        thread_store=threads,
        participants=await threads.list_participants(thread_id=thread.id),
        sender_handle="alice",
        telegram_chat_id=-100,
        telegram_message_thread_id=None,
        user_id=42,
        parent_message_id=f"msg-{user_msg_id}",
        channel="telegram",
    )

    await _assert_user_gets_a_reply(threads, thread.id, routing_stubs.dispatch, mode)


class _JsonRequest:
    def __init__(self, *, thread_id: str, payload: dict[str, object]) -> None:
        self.match_info = {"thread_id": thread_id}
        self.query: dict[str, str] = {}
        self.headers: dict[str, str] = {}
        self.can_read_body = True
        self.app: dict[str, object] = {}
        self._payload = payload

    async def json(self) -> dict[str, object]:
        return dict(self._payload)


@pytest.mark.postgres
@pytest.mark.asyncio
@pytest.mark.parametrize(("mode", "selected"), MODES)
async def test_web_room_message_gets_a_reply_when_coordinator_dispatches_no_task(
    stores: tuple[SquadThreadStore, SquadTaskStore], routing_stubs: Any, mode: str, selected: list[str]
) -> None:
    threads, _tasks = stores
    thread = await _seed_thread(threads)
    _use_planner(routing_stubs, mode, selected)
    stack = routing_stubs.stack
    stack.enter_context(patch("koda.control_plane.api._authorize_request", return_value=None))
    stack.enter_context(
        patch(
            "koda.control_plane.api._request_auth_context",
            return_value=control_plane_api.OperatorAuthContext(
                auth_kind="session",
                subject_type="operator",
                user_id="usr_1",
                username="owner",
                email="owner@example.com",
                display_name="Owner",
            ),
        )
    )
    stack.enter_context(
        patch(
            "koda.control_plane.api._dashboard_squad_thread_access",
            AsyncMock(return_value=(SimpleNamespace(thread=thread), None)),
        )
    )
    stack.enter_context(patch("koda.squads.sync_thread_participants_from_squad", AsyncMock(return_value=None)))
    stack.enter_context(patch("koda.control_plane.api._watch_dashboard_squad_delivery_synthesis", AsyncMock()))

    response = await control_plane_api.post_dashboard_squad_thread_message_route(
        cast(Any, _JsonRequest(thread_id=thread.id, payload={"content": USER_TEXT}))
    )

    assert response.status == 200
    assert json.loads(cast(Any, response).text)["messageId"]
    await _assert_user_gets_a_reply(threads, thread.id, routing_stubs.dispatch, mode)
