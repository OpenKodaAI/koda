"""Squad follow-up turns are queued after the per-user worker lock is released (D-019, F-SQD-16).

A squad turn's post-processing (``_post_process``) runs under the per-user
worker lock. Queueing a follow-up turn, such as the coordinator synthesis after
a handoff, goes through ``enqueue_squad_agent_task`` and
``_ensure_queue_worker``, which take that lock again, so the follow-up must be
queued once the lock is released.

Each scenario posts a user message to a squad room through the real Telegram
room handler or the real web route, and the planner hands off to FE and QA.
Every turn then runs in the real per-user queue worker (``_process_queue`` ->
``_execute_single_task``): the last destination's post-processing holds the
real ``_get_worker_lock``, and the coordinator synthesis goes through the real
``dispatch_squad_turn`` and ``enqueue_squad_agent_task`` into the same queue.
The thread, task and runtime stores are real, on Postgres. Only the edges are
replaced: the ``claude`` provider adapter answers from a script, the bot
records what it is sent, and the routing inputs that need a control plane or
an embedding model are fixed. The web route gets the runtime application, as in
a single-process deployment; under the supervisor each destination runtime
queues the synthesis with its own application, through the same post-turn code.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import json
import os
from collections import defaultdict
from collections.abc import AsyncIterator, Iterator
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import asyncpg  # type: ignore[import-not-found]
import pytest

from koda.services import llm_runner
from koda.services.provider_runtime import ProviderCapabilities, TurnMode
from koda.squads.capabilities import CapabilitySummary
from koda.squads.coordinator_engine import (
    CoordinationDecision,
    CoordinationPlannerInput,
    CoordinationTask,
    SquadCoordinatorEngine,
)
from koda.squads.dispatch import _SilentSquadDispatchBot
from koda.squads.semantic_router import SemanticAgentScore, SemanticRoutingResult
from tests.postgres_fixtures import reset_squad_runtime_tables

pytestmark = [pytest.mark.postgres]

USER_ID = 920001
GROUP_CHAT_ID = -1009200010
USER_TEXT = "Ship the launch page"
SYNTHESIS_MARKER = "Todos os task_result abertos deste ciclo"
FINAL_ANSWER = "PM: the launch page is built and reviewed."
_TURN_TIMEOUT_S = 30.0
_RUNTIME_TABLES = (
    "tasks",
    "runtime_queue_items",
    "runtime_events",
    "dead_letter_queue",
    "query_history",
    "user_cost_totals",
    "audit_events",
)


def _schema() -> str:
    return (os.environ.get("KNOWLEDGE_V2_POSTGRES_SCHEMA") or "knowledge_v2").strip() or "knowledge_v2"


@dataclass
class _Turn:
    text: str = ""
    error: str | None = None
    error_kind: str = "provider_runtime"
    retryable: bool = False


class _ScriptedClaude:
    """The ``claude`` entry of ``llm_runner._HTTP_PROVIDER_RUNNERS``, answering each query from a script."""

    def __init__(self, script: Any) -> None:
        self._script = script
        self.queries: list[str] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> _ScriptedClaude:
        monkeypatch.setitem(
            llm_runner._HTTP_PROVIDER_RUNNERS,
            "claude",
            {"run": self.run, "stream": self.stream, "capabilities": self.capabilities, "first_chunk_timeout": 5.0},
        )
        return self

    def _turn(self, query: str) -> _Turn:
        self.queries.append(query)
        return cast(_Turn, self._script(query))

    async def capabilities(self, turn_mode: TurnMode) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider="claude",
            turn_mode=turn_mode,
            status="ready",
            can_execute=True,
            supports_native_resume=True,
            checked_via="stub",
        )

    async def stream(
        self, *, query: str, metadata_collector: dict[str, Any] | None = None, **_kwargs: Any
    ) -> AsyncIterator[str]:
        turn = self._turn(query)
        collector = metadata_collector if metadata_collector is not None else {}
        if turn.text:
            yield turn.text
        if turn.error is not None:
            collector.update(error=True, error_message=turn.error, error_kind=turn.error_kind, retryable=turn.retryable)
            return
        collector.update(usage={"input_tokens": 10, "output_tokens": 5}, cost_usd=0.0, stop_reason="end_turn")

    async def run(self, *, query: str, session_id: str | None = None, **_kwargs: Any) -> dict[str, Any]:
        turn = self._turn(query)
        if turn.error is not None:
            return {
                "result": turn.error,
                "session_id": session_id,
                "cost_usd": 0.0,
                "usage": {},
                "error": True,
                "_error_kind": turn.error_kind,
                "_retryable": turn.retryable,
            }
        return {
            "result": turn.text,
            "session_id": None,
            "cost_usd": 0.0,
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "error": False,
            "_stop_reason": "end_turn",
        }


def _answers(query: str) -> _Turn:
    if SYNTHESIS_MARKER in query:
        return _Turn(text=FINAL_ANSWER)
    if "Task request [frontend]" in query:
        return _Turn(text="FE: launch page built.")
    if "Task request [review]" in query:
        return _Turn(text="QA: launch page reviewed.")
    if "Task request [specialist]" in query:
        return _Turn(text="FE: launch page drafted.")
    return _Turn(text="Noted.")


class _RecordingBot(_SilentSquadDispatchBot):
    """A bot that keeps every message the runtime sends."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, *args: object, text: str = "", **kwargs: object) -> Any:
        chat_id = kwargs.get("chat_id", args[0] if args else 0)
        self.sent.append((int(cast(int, chat_id)), text))
        return await super().send_message(text=text)

    async def edit_message_text(self, *_args: object, **_kwargs: object) -> bool:
        return True

    def texts(self, chat_id: int) -> list[str]:
        return [text for sent_chat_id, text in self.sent if sent_chat_id == chat_id]


@pytest.fixture
async def agent_db(migrated_postgres: str, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[str]:
    """The migrated test database with the runtime tables emptied, and the runtime controller rebuilt on it."""
    from koda.services.runtime import controller as controller_mod

    monkeypatch.setattr(controller_mod, "_runtime_controller", None)
    conn = await asyncpg.connect(migrated_postgres)
    try:
        tables = ", ".join(f'"{_schema()}"."{name}"' for name in _RUNTIME_TABLES)
        await conn.execute(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE")
        await reset_squad_runtime_tables(conn, _schema())
    finally:
        await conn.close()
    try:
        yield migrated_postgres
    finally:
        await _drain_background_work()


async def _drain_background_work() -> None:
    """Let the turns' fire-and-forget work finish while the database is still configured."""
    current = asyncio.current_task()
    pending = [task for task in asyncio.all_tasks() if task is not current and not task.done()]
    if pending:
        _, still_pending = await asyncio.wait(pending, timeout=_TURN_TIMEOUT_S)
        for task in still_pending:
            task.cancel()
        if still_pending:
            await asyncio.wait(still_pending, timeout=5)
    await asyncio.get_running_loop().shutdown_default_executor()


@pytest.fixture
async def squad_stores(agent_db: str, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[Any, Any]]:
    """The process-wide squad stores, built on the test database for this test only."""
    import koda.config as config_mod
    from koda.squads import access, artifacts, capabilities, coordinator, tasks, threads

    singletons = (
        (threads, "_store"),
        (tasks, "_store"),
        (access, "_service"),
        (artifacts, "_store"),
        (capabilities, "_cache"),
        (coordinator, "_service"),
    )
    monkeypatch.setattr(config_mod, "POSTGRES_URL", agent_db)
    for module, attr in singletons:
        monkeypatch.setattr(module, attr, None)
    try:
        yield threads.get_squad_thread_store(), tasks.get_squad_task_store()
    finally:
        for module, attr in singletons:
            built = getattr(module, attr)
            if built is not None and hasattr(built, "close"):
                with contextlib.suppress(Exception):
                    await built.close()


@pytest.fixture
def queue_state() -> Iterator[None]:
    """Stop the test user's queue worker and drop the per-user queue state it leaves behind."""
    from koda.services import queue_manager as qm

    yield
    worker = qm._queue_workers.get(USER_ID)
    if worker is not None and not worker.done():
        worker.cancel()
    for registry in (
        qm._user_queues,
        qm._queue_workers,
        qm._user_tasks,
        qm._worker_locks,
        qm._user_semaphores,
        qm._user_queue_task_ids,
        qm._active_chat_ids,
    ):
        registry.pop(USER_ID, None)


@pytest.fixture
def application(tmp_path: Path) -> Any:
    """The runtime application surface ``build_runtime_context`` reads; users work in an empty directory."""
    return SimpleNamespace(
        bot=_RecordingBot(),
        user_data=defaultdict(lambda: {"work_dir": str(tmp_path)}),
        bot_data={},
        job_queue=None,
    )


class _HandoffPlanner:
    def __init__(self, tasks: list[CoordinationTask], selected_agents: list[str]) -> None:
        self._tasks = tasks
        self._selected_agents = selected_agents

    async def plan(self, planner_input: CoordinationPlannerInput) -> CoordinationDecision:
        return CoordinationDecision(
            mode="handoff",
            confidence=0.86,
            reasoning_summary="Consult the specialists before the final answer.",
            tasks=list(self._tasks),
            selected_agents=list(self._selected_agents),
            final_response_strategy="coordinator_synthesis_after_all_task_results",
        )


HANDOFF_TO_FE_AND_QA = _HandoffPlanner(
    [
        CoordinationTask(key="build", title="Build", agent_id="FE", kind="frontend", objective="Build the page"),
        CoordinationTask(key="review", title="Review", agent_id="QA", kind="review", objective="Review the page"),
    ],
    ["FE", "QA"],
)
# The planner names a destination but gives it no task; the engine gives it one (D-015).
TASK_LESS_HANDOFF_TO_FE = _HandoffPlanner([], ["FE"])


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


@pytest.fixture
def routing_inputs(application: Any) -> Iterator[ExitStack]:
    """Fixed routing inputs: capability summaries, semantic scores, no mentions, no triage proposals."""
    summaries = [
        CapabilitySummary(agent_id="PM", display_name="PM", role="Coordinator", is_coordinator=True),
        CapabilitySummary(agent_id="FE", display_name="Frontend", role="Interface"),
        CapabilitySummary(agent_id="QA", display_name="QA", role="Quality"),
    ]
    no_mentions = SimpleNamespace(
        has_resolved_mentions=False, has_mentions=False, resolved_agent_ids=[], unresolved=[], ambiguous={}
    )
    triage = SimpleNamespace(awareness_agent_ids=[], proposal_candidates=[], to_dict=lambda: {})
    with ExitStack() as stack:
        stack.enter_context(patch("koda.config.SQUAD_COORDINATOR_MODE", "supervisor"))
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
        # Per-agent Telegram bots need agent tokens from the control plane; every agent uses the runtime bot.
        stack.enter_context(
            patch(
                "koda.squads.dispatch._telegram_bot_for_agent",
                AsyncMock(side_effect=lambda *, fallback_bot, **_: fallback_bot),
            )
        )
        yield stack


def _use_planner(stack: ExitStack, planner: Any) -> None:
    stack.enter_context(
        patch("koda.squads.SquadCoordinatorEngine", functools.partial(SquadCoordinatorEngine, planner=planner))
    )


async def _post_telegram_message(thread_store: Any, application: Any) -> Any:
    from koda.handlers.squad_handlers import _notify_squad_targets

    thread = await thread_store.create_thread(
        workspace_id="acme",
        squad_id="launch",
        title="Launch",
        owner_user_id=USER_ID,
        coordinator_agent_id="PM",
        telegram_chat_id=GROUP_CHAT_ID,
        participants=[("PM", "coordinator"), ("FE", "worker"), ("QA", "worker")],
    )
    user_msg_id = await thread_store.post_thread_message(
        thread_id=thread.id, from_agent="user:alice", content=USER_TEXT, message_type="user_input"
    )
    await _notify_squad_targets(
        text=USER_TEXT,
        thread=thread,
        thread_store=thread_store,
        participants=await thread_store.list_participants(thread_id=thread.id),
        sender_handle="alice",
        telegram_chat_id=GROUP_CHAT_ID,
        telegram_message_thread_id=None,
        user_id=USER_ID,
        parent_message_id=f"msg-{user_msg_id}",
        channel="telegram",
        bot_context=cast(Any, SimpleNamespace(application=application, bot=application.bot)),
    )
    return thread


class _JsonRequest:
    def __init__(self, *, thread_id: str, payload: dict[str, object], application: Any) -> None:
        self.match_info = {"thread_id": thread_id}
        self.query: dict[str, str] = {}
        self.headers: dict[str, str] = {}
        self.can_read_body = True
        self.app: dict[str, object] = {"telegram_application": application}
        self._payload = payload

    async def json(self) -> dict[str, object]:
        return dict(self._payload)


async def _post_web_message(thread_store: Any, application: Any, stack: ExitStack) -> Any:
    from koda.control_plane import api as control_plane_api

    thread = await thread_store.create_thread(
        workspace_id="acme",
        squad_id="launch",
        title="Launch",
        owner_user_id=USER_ID,
        coordinator_agent_id="PM",
        participants=[("PM", "coordinator"), ("FE", "worker"), ("QA", "worker")],
    )
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
    request = _JsonRequest(thread_id=thread.id, payload={"content": USER_TEXT}, application=application)
    response = await control_plane_api.post_dashboard_squad_thread_message_route(cast(Any, request))
    assert response.status == 200, cast(Any, response).text
    assert json.loads(cast(Any, response).text)["coordination"]["mode"] == "handoff"
    return thread


def _awaited_coroutines(task: asyncio.Task[Any]) -> list[str]:
    names: list[str] = []
    awaitable: Any = task.get_coro()
    while awaitable is not None:
        code = getattr(awaitable, "cr_code", None)
        if code is not None:
            names.append(code.co_name)
        awaitable = getattr(awaitable, "cr_await", None)
    return names


def _assert_no_turn_waits_on_its_own_lock() -> None:
    for task in asyncio.all_tasks():
        chain = _awaited_coroutines(task)
        assert not ("_post_process" in chain and "_ensure_queue_worker" in chain), (
            "a squad turn waits for the worker lock its own post-processing holds (D-019): " + " -> ".join(chain)
        )


async def _wait_for_coordinator_answer(thread_store: Any, thread_id: str) -> dict[str, Any]:
    """The coordinator's final answer in the thread, once its synthesis turn has run to the end.

    The answer is posted during the turn's post-processing, before it is delivered and its
    runtime task is completed, so this also waits for the queue worker to finish and exit.
    """
    from koda.services import queue_manager as qm

    deadline = asyncio.get_running_loop().time() + _TURN_TIMEOUT_S
    answer: dict[str, Any] | None = None
    while True:
        if answer is None:
            history = await thread_store.thread_history(thread_id=thread_id, limit=200)
            answer = next(
                (
                    row
                    for row in history
                    if row.get("from") == "PM"
                    and row.get("type") == "agent_text"
                    and FINAL_ANSWER in str(row.get("content"))
                ),
                None,
            )
        worker = qm._queue_workers.get(USER_ID)
        if answer is not None and (worker is None or worker.done()):
            return answer
        if asyncio.get_running_loop().time() > deadline:
            _assert_no_turn_waits_on_its_own_lock()
            if answer is not None:
                raise AssertionError("the queue worker did not finish after the coordinator answered")
            raise AssertionError("the coordinator never answered: " + json.dumps(_summary(history), default=str))
        await asyncio.sleep(0.05)


def _summary(history: list[dict[str, Any]]) -> list[tuple[Any, Any, str]]:
    return [(row.get("from"), row.get("type"), str(row.get("content"))[:80]) for row in reversed(history)]


def _handoff_statuses(history: list[dict[str, Any]]) -> list[str]:
    return [
        str(((row.get("metadata") or {}).get("payload") or {}).get("status"))
        for row in reversed(history)
        if ((row.get("metadata") or {}).get("payload") or {}).get("schema_version") == "handoff_event.v1"
    ]


async def _runtime_task_statuses(dsn: str) -> list[tuple[str, str]]:
    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(
            f'SELECT status, query_text FROM "{_schema()}"."tasks" WHERE user_id = $1 ORDER BY id', USER_ID
        )
    finally:
        await conn.close()
    return [(str(row["status"]), str(row["query_text"])) for row in rows]


@pytest.mark.parametrize("channel", ["telegram", "web"])
async def test_handoff_synthesis_is_queued_after_the_last_destination_releases_the_worker_lock(
    agent_db: str,
    squad_stores: tuple[Any, Any],
    queue_state: None,
    application: Any,
    routing_inputs: ExitStack,
    monkeypatch: pytest.MonkeyPatch,
    channel: str,
) -> None:
    thread_store, task_store = squad_stores
    provider = _ScriptedClaude(_answers).install(monkeypatch)
    _use_planner(routing_inputs, HANDOFF_TO_FE_AND_QA)

    if channel == "telegram":
        thread = await _post_telegram_message(thread_store, application)
    else:
        thread = await _post_web_message(thread_store, application, routing_inputs)
    answer = await _wait_for_coordinator_answer(thread_store, thread.id)

    # FE and QA ran their tasks, then the coordinator synthesised both results once.
    [synthesis_query] = [query for query in provider.queries if SYNTHESIS_MARKER in query]
    assert "FE / " in synthesis_query and "QA / " in synthesis_query
    assert "Timeouts/bloqueios declarados" not in synthesis_query
    assert answer["content"].startswith(FINAL_ANSWER)
    history = await thread_store.thread_history(thread_id=thread.id, limit=200)
    assert _handoff_statuses(history) == ["requested", "returned"]
    assert {task.assigned_agent_id: task.status for task in await task_store.list_tasks(thread_id=thread.id)} == {
        "FE": "done",
        "QA": "done",
    }
    statuses = await _runtime_task_statuses(agent_db)
    assert [status for status, _query in statuses] == ["completed", "completed", "completed"]
    assert SYNTHESIS_MARKER in statuses[-1][1]
    if channel == "telegram":
        delivered = application.bot.texts(GROUP_CHAT_ID)
        for text in ("FE: launch page built.", "QA: launch page reviewed.", FINAL_ANSWER):
            assert any(message.startswith(text) for message in delivered), delivered


FAILURES = [
    pytest.param(_Turn(error="QA could not open the page: request rejected"), id="provider_error"),
    pytest.param(
        _Turn(error="claude API overloaded (529), try again later", error_kind="transient", retryable=True),
        id="retries_exhausted",
    ),
    pytest.param(_Turn(error="QA hit a runtime guardrail", error_kind="runtime_guardrail"), id="runtime_guardrail"),
]


@pytest.mark.parametrize("failure", FAILURES)
async def test_a_destination_whose_run_fails_fails_the_handoff_and_the_coordinator_discloses_it(
    agent_db: str,
    squad_stores: tuple[Any, Any],
    queue_state: None,
    application: Any,
    routing_inputs: ExitStack,
    monkeypatch: pytest.MonkeyPatch,
    failure: _Turn,
) -> None:
    from koda.services import queue_manager as qm

    thread_store, task_store = squad_stores
    monkeypatch.setattr(qm, "TASK_RETRY_BASE_DELAY", 1.0)
    monkeypatch.setattr(qm, "TASK_RETRY_MAX_DELAY", 1.0)
    provider = _ScriptedClaude(lambda query: failure if "Task request [review]" in query else _answers(query))
    provider.install(monkeypatch)
    _use_planner(routing_inputs, HANDOFF_TO_FE_AND_QA)

    thread = await _post_telegram_message(thread_store, application)
    answer = await _wait_for_coordinator_answer(thread_store, thread.id)

    # QA's run failed in the queue, so its task failed, its failure is in the room, and the
    # coordinator synthesis names it.
    [synthesis_query] = [query for query in provider.queries if SYNTHESIS_MARKER in query]
    assert "Timeouts/bloqueios declarados:\n- QA: failed" in synthesis_query
    assert answer["content"].startswith(FINAL_ANSWER)
    history = await thread_store.thread_history(thread_id=thread.id, limit=200)
    assert _handoff_statuses(history) == ["requested", "failed"]
    [qa_result] = [row for row in history if row.get("from") == "QA" and row.get("type") == "task_result"]
    assert qa_result["metadata"]["payload"]["status"] == "failed"
    assert failure.error is not None and failure.error in qa_result["content"]
    assert {task.assigned_agent_id: task.status for task in await task_store.list_tasks(thread_id=thread.id)} == {
        "FE": "done",
        "QA": "failed",
    }
    delivered = application.bot.texts(GROUP_CHAT_ID)
    assert any("falhou" in message for message in delivered), delivered
    assert any(message.startswith(FINAL_ANSWER) for message in delivered), delivered


@pytest.mark.parametrize("channel", ["telegram", "web"])
async def test_a_task_less_handoff_is_answered_by_the_destination_and_then_the_coordinator(
    agent_db: str,
    squad_stores: tuple[Any, Any],
    queue_state: None,
    application: Any,
    routing_inputs: ExitStack,
    monkeypatch: pytest.MonkeyPatch,
    channel: str,
) -> None:
    thread_store, task_store = squad_stores
    provider = _ScriptedClaude(_answers).install(monkeypatch)
    _use_planner(routing_inputs, TASK_LESS_HANDOFF_TO_FE)

    if channel == "telegram":
        thread = await _post_telegram_message(thread_store, application)
    else:
        thread = await _post_web_message(thread_store, application, routing_inputs)
    answer = await _wait_for_coordinator_answer(thread_store, thread.id)

    [synthesis_query] = [query for query in provider.queries if SYNTHESIS_MARKER in query]
    assert "FE / " in synthesis_query and "FE: launch page drafted." in synthesis_query
    assert answer["content"].startswith(FINAL_ANSWER)
    history = await thread_store.thread_history(thread_id=thread.id, limit=200)
    assert _handoff_statuses(history) == ["requested", "returned"]
    assert {task.assigned_agent_id: task.status for task in await task_store.list_tasks(thread_id=thread.id)} == {
        "FE": "done"
    }
    assert [status for status, _query in await _runtime_task_statuses(agent_db)] == ["completed", "completed"]
    if channel == "telegram":
        delivered = application.bot.texts(GROUP_CHAT_ID)
        for text in ("FE: launch page drafted.", FINAL_ANSWER):
            assert any(message.startswith(text) for message in delivered), delivered
