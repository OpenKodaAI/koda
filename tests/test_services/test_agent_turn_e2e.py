"""End-to-end agent turns on real Postgres (M0-E3-T2; characterises D-021 / F-QA-21).

Each scenario enters the runtime the way production does (the Telegram
``enqueue`` entrypoint, or ``enqueue_squad_agent_task`` for squad turns) and
lets the real per-user queue worker run ``_execute_single_task``. Only the
edges are replaced:

* the provider adapter: ``tests.fakes.provider.StubProvider`` is the
  ``claude`` entry of ``llm_runner._HTTP_PROVIDER_RUNNERS``, so capability
  checks, ``run_llm_streaming``, provider fallback, the agent tool loop and
  the retry loop above it are production code;
* Telegram: ``tests.fakes.telegram.FakeBot`` records what is delivered.

No function on the orchestration path is patched; tests only set
configuration (the retry back-off, the squad stores' database URL) and reset
process-wide singletons so they are built against the test database. Task rows
and their leases, the runtime queue mirror, the query log, the dead-letter
queue, scheduled jobs and squad state are written to, and read back from, that
database.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import asyncpg
import pytest

from tests.fakes.provider import ProviderCall, ProviderTurn, StubProvider
from tests.fakes.telegram import FakeApplication, FakeBot, fake_text_update
from tests.postgres_fixtures import reset_squad_runtime_tables

pytestmark = [pytest.mark.postgres]

_SCHEMA = "knowledge_v2"
_TABLES = (
    "tasks",
    "runtime_queue_items",
    "runtime_events",
    "dead_letter_queue",
    "query_history",
    "user_cost_totals",
    "audit_events",
    "scheduled_job_events",
    "scheduled_job_runs",
    "scheduled_jobs",
)
_TURN_TIMEOUT_S = 30.0
_USER_IDS = frozenset({910001, 910002, 910003, 910004, 910005, 910006})


def _stop_primary_bridge() -> None:
    """Stop the sync->async bridge thread the runtime starts, so later tests run without it."""
    from koda.knowledge.v2 import common as common_mod
    from koda.state import primary as primary_mod

    loop = primary_mod._active_bridge_loop()
    if loop is not None:
        for backend in list(common_mod._SHARED_POSTGRES_BACKENDS.values()):
            future = asyncio.run_coroutine_threadsafe(backend.close(), loop)
            try:
                future.result(timeout=10)
            except Exception:
                future.cancel()
        loop.call_soon_threadsafe(loop.stop)
        thread = primary_mod._BRIDGE_THREAD
        if thread is not None:
            thread.join(timeout=10)
        with primary_mod._BRIDGE_LOCK:
            primary_mod._BRIDGE_LOOP = None
            primary_mod._BRIDGE_THREAD = None
            primary_mod._BRIDGE_OWNER_PID = None
    common_mod._SHARED_POSTGRES_BACKENDS.clear()


async def _drain_background_work() -> None:
    """Let a turn's fire-and-forget work finish before the bridge stops.

    A turn leaves asyncio tasks (procedural memory, memory extraction) and
    executor jobs (audit inserts, run-graph writes) behind. They write through
    the primary-state bridge, so they must finish while it still runs.
    """
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
async def agent_db(migrated_postgres: str, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[str]:
    """The migrated test database, with the tables these scenarios read emptied."""
    from koda.knowledge.v2 import common as common_mod
    from koda.services.runtime import controller as controller_mod

    common_mod._SHARED_POSTGRES_BACKENDS.clear()
    # The process-wide runtime controller is built on first use against the
    # test database, and dropped afterwards so later tests do not inherit it.
    monkeypatch.setattr(controller_mod, "_runtime_controller", None)
    conn = await asyncpg.connect(migrated_postgres)
    try:
        tables = ", ".join(f'{_SCHEMA}."{name}"' for name in _TABLES)
        await conn.execute(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE")
    finally:
        await conn.close()
    try:
        yield migrated_postgres
    finally:
        await _drain_background_work()
        _stop_primary_bridge()


@pytest.fixture
def queue_state() -> Iterator[None]:
    """Remove the per-user queue state the scenarios leave in ``queue_manager``."""
    from koda.services import queue_manager as qm

    yield
    for registry in (
        qm._user_queues,
        qm._queue_workers,
        qm._user_tasks,
        qm._worker_locks,
        qm._user_semaphores,
        qm._user_queue_task_ids,
        qm._active_chat_ids,
    ):
        for user_id in [key for key in registry if key in _USER_IDS]:
            registry.pop(user_id, None)


@pytest.fixture
def application(tmp_path: Path) -> FakeApplication:
    """A fake Telegram application whose users work in an empty directory.

    Without this the work dir is the system temp dir, and the artifact discovery
    that runs after every turn would attach any file another process modifies
    there during the run (D-023).
    """
    return FakeApplication(user_defaults={"work_dir": str(tmp_path)})


@pytest.fixture
def fast_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the retry back-off to its one-second floor (the defaults wait 1-10 s)."""
    from koda.services import queue_manager as qm

    monkeypatch.setattr(qm, "TASK_RETRY_BASE_DELAY", 1.0)
    monkeypatch.setattr(qm, "TASK_RETRY_MAX_DELAY", 1.0)


async def _fetch_all(dsn: str, query: str, *args: Any) -> list[dict[str, Any]]:
    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(query, *args)
    finally:
        await conn.close()
    return [dict(row) for row in rows]


async def _task_row(dsn: str, task_id: int) -> dict[str, Any]:
    rows = await _fetch_all(dsn, f'SELECT * FROM {_SCHEMA}."tasks" WHERE id = $1', task_id)
    assert rows, f"task {task_id} has no row"
    return rows[0]


async def _queue_item_row(dsn: str, task_id: int) -> dict[str, Any]:
    rows = await _fetch_all(dsn, f'SELECT * FROM {_SCHEMA}."runtime_queue_items" WHERE task_id = $1', task_id)
    assert rows, f"task {task_id} has no runtime queue item"
    return rows[0]


async def _audit_event_types(dsn: str, task_id: int, *, until_present: str) -> list[str]:
    """Event types recorded for a task, once ``until_present`` has been written.

    Audit inserts run on executor threads after the turn returns, so poll briefly.
    """
    deadline = asyncio.get_running_loop().time() + 10
    while True:
        rows = await _fetch_all(
            dsn, f'SELECT event_type FROM {_SCHEMA}."audit_events" WHERE task_id = $1 ORDER BY id', task_id
        )
        types = [str(row["event_type"]) for row in rows]
        if until_present in types or asyncio.get_running_loop().time() > deadline:
            return types
        await asyncio.sleep(0.05)


async def _execution_trace(dsn: str, task_id: int) -> dict[str, Any]:
    """The persisted ``task.execution_trace`` audit details for a task."""
    await _audit_event_types(dsn, task_id, until_present="task.execution_trace")
    rows = await _fetch_all(
        dsn,
        f"""SELECT details_json::text AS details FROM {_SCHEMA}."audit_events"
             WHERE task_id = $1 AND event_type = 'task.execution_trace'""",
        task_id,
    )
    assert len(rows) == 1, f"task {task_id} has {len(rows)} execution traces"
    details: dict[str, Any] = json.loads(rows[0]["details"])
    return details


async def _wait_for_worker(user_id: int) -> None:
    """Wait until the user's queue worker has drained the queue and exited."""
    from koda.services import queue_manager as qm

    worker = qm._queue_workers.get(user_id)
    if worker is not None:
        await asyncio.wait_for(asyncio.shield(worker), timeout=_TURN_TIMEOUT_S)


async def _wait_for_task_status(dsn: str, task_id: int, statuses: set[str], *, timeout: float) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        rows = await _fetch_all(dsn, f'SELECT * FROM {_SCHEMA}."tasks" WHERE id = $1', task_id)
        if rows and rows[0]["status"] in statuses:
            return rows[0]
        if asyncio.get_running_loop().time() > deadline:
            raise TimeoutError(f"task {task_id} did not reach {sorted(statuses)}; row: {rows[0] if rows else None}")
        await asyncio.sleep(0.05)


async def _stop_worker(user_id: int) -> None:
    from koda.services import queue_manager as qm

    worker = qm._queue_workers.get(user_id)
    if worker is not None and not worker.done():
        worker.cancel()
        with contextlib.suppress(BaseException):
            await worker


def _context(application: FakeApplication, user_id: int) -> Any:
    from koda.services.queue_manager import build_runtime_context

    return build_runtime_context(application, user_id)


async def _send(application: FakeApplication, *, user_id: int, chat_id: int, text: str, message_id: int = 1) -> int:
    """Deliver an incoming Telegram text message to the runtime, as the message handler does."""
    from koda.services.queue_manager import enqueue

    update = fake_text_update(application.bot, user_id=user_id, chat_id=chat_id, text=text, message_id=message_id)
    task_id = await enqueue(user_id, update, _context(application, user_id), text)
    assert task_id is not None
    return int(task_id)


def _assert_lease_released(row: dict[str, Any]) -> None:
    assert row["lease_owner"] is None
    assert row["lease_expires_at"] is None


async def test_success_delivers_the_answer_and_persists_the_completed_task(
    agent_db: str, queue_state: None, application: FakeApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = chat_id = 910001
    provider = StubProvider(
        [ProviderTurn(text="Paris is the capital of France.", cost_usd=0.0125, session_id="prov-sess-1")]
    ).install(monkeypatch)

    task_id = await _send(application, user_id=user_id, chat_id=chat_id, text="What is the capital of France?")
    await _wait_for_worker(user_id)

    [call] = provider.calls
    assert call.query == "What is the capital of France?"
    assert call.turn_mode == "new_turn"
    assert call.streaming is True
    assert call.system_prompt

    bot: FakeBot = application.bot
    progress, answer = bot.messages
    # The streaming progress message showed the partial output, then was removed.
    assert progress.edits and "Paris is the capital of France." in progress.edits[-1]
    assert progress.deleted is True
    # The answer is the only visible message: a reply to the user's message, with the cost footer.
    assert bot.visible(chat_id) == [answer]
    assert answer.text is not None
    assert answer.text.startswith("Paris is the capital of France.\n\n———\n<i>Cost: $0.0125 | Total: $0.0125 | claude")
    assert answer.kwargs["reply_to_message_id"] == 1
    assert str(answer.kwargs["parse_mode"]) == "HTML"

    row = await _task_row(agent_db, task_id)
    assert row["status"] == "completed"
    assert (row["user_id"], row["chat_id"]) == (user_id, chat_id)
    assert row["query_text"] == "What is the capital of France?"
    assert (row["provider"], row["model"]) == ("claude", "claude-sonnet-4-6")
    assert row["attempt"] == 1
    assert row["cost_usd"] == pytest.approx(0.0125)
    assert row["provider_session_id"] == "prov-sess-1"
    assert row["session_id"]
    assert row["error_message"] is None
    assert row["started_at"] and row["completed_at"]
    _assert_lease_released(row)
    assert (await _queue_item_row(agent_db, task_id))["status"] == "completed"

    [logged] = await _fetch_all(agent_db, f'SELECT * FROM {_SCHEMA}."query_history" WHERE user_id = $1', user_id)
    assert logged["query_text"] == "What is the capital of France?"
    assert logged["response_text"] == "Paris is the capital of France."
    assert logged["cost_usd"] == pytest.approx(0.0125)
    assert logged["session_id"] == row["session_id"]
    assert logged["error"] is False
    assert await _fetch_all(agent_db, f'SELECT * FROM {_SCHEMA}."dead_letter_queue"') == []

    events = await _audit_event_types(agent_db, task_id, until_present="task.completed")
    for expected in ("task.created", "task.queued", "task.started", "task.execution_trace", "task.completed"):
        assert expected in events
    trace = await _execution_trace(agent_db, task_id)
    assert trace["runtime"]["status"] == "completed"
    assert trace["request"]["query_text"] == "What is the capital of France?"
    assert trace["assistant"]["response_text"] == "Paris is the capital of France."


async def test_retryable_provider_error_is_retried_then_dead_lettered(
    agent_db: str,
    queue_state: None,
    application: FakeApplication,
    fast_retries: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = chat_id = 910002
    error = "claude API overloaded (529), try again later"
    provider = StubProvider([ProviderTurn(error=error, error_kind="transient", retryable=True)]).install(monkeypatch)

    task_id = await _send(application, user_id=user_id, chat_id=chat_id, text="Summarise the release notes")
    await _wait_for_worker(user_id)

    # One provider call per attempt: TASK_MAX_RETRY_ATTEMPTS (3) attempts, no other provider in the chain.
    assert [call.query for call in provider.calls] == ["Summarise the release notes"] * 3

    row = await _task_row(agent_db, task_id)
    assert row["status"] == "failed"
    assert row["attempt"] == 3
    assert row["error_message"] == error
    assert row["completed_at"]
    _assert_lease_released(row)
    queue_item = await _queue_item_row(agent_db, task_id)
    assert (queue_item["status"], queue_item["last_error"]) == ("failed", error)

    [dead_letter] = await _fetch_all(
        agent_db, f'SELECT * FROM {_SCHEMA}."dead_letter_queue" WHERE task_id = $1', task_id
    )
    assert (dead_letter["user_id"], dead_letter["chat_id"]) == (user_id, chat_id)
    assert dead_letter["query_text"] == "Summarise the release notes"
    assert dead_letter["error_message"] == error
    assert dead_letter["error_class"] == "RetryableError"
    assert dead_letter["attempt_count"] == 3
    assert dead_letter["retry_eligible"] == 1
    metadata = json.loads(dead_letter["metadata_json"])
    assert metadata["history"][0]["reason"] == "retry_exhausted"
    assert metadata["queue_payload"]["query_text"] == "Summarise the release notes"
    assert await _fetch_all(agent_db, f'SELECT * FROM {_SCHEMA}."query_history" WHERE user_id = $1', user_id) == []

    # Each attempt's progress message is removed; the user is left with one failure notice.
    bot: FakeBot = application.bot
    assert [message.text for message in bot.messages if message.deleted] == ["Processing…"] * 3
    [notice] = bot.visible(chat_id)
    assert notice.text is not None
    assert notice.text.startswith(f"Task #{task_id} falhou:\n")
    assert "<b>Overloaded</b>" in notice.text
    assert notice.kwargs["reply_to_message_id"] == 1

    events = await _audit_event_types(agent_db, task_id, until_present="task.dead_letter")
    assert events.count("task.retried") == 2
    assert events.count("task.failed") == 1
    assert events.count("task.dead_letter") == 1


async def test_read_tool_called_through_agent_cmd_feeds_its_result_back_to_the_provider(
    agent_db: str, queue_state: None, application: FakeApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    from koda.services import scheduled_jobs

    user_id = chat_id = 910003
    job_id = scheduled_jobs.create_reminder_job(
        user_id=user_id,
        chat_id=chat_id,
        trigger_type="interval",
        schedule_expr="3600",
        text="Stretch break",
    )
    provider = StubProvider(
        [
            ProviderTurn(
                text='Let me check your schedule. <agent_cmd tool="job_list">{}</agent_cmd>',
                cost_usd=0.01,
                session_id="prov-sess-tools",
            ),
            ProviderTurn(text="You have one reminder: Stretch break, every hour.", cost_usd=0.02),
        ]
    ).install(monkeypatch)

    task_id = await _send(application, user_id=user_id, chat_id=chat_id, text="Which reminders do I have?")
    await _wait_for_worker(user_id)

    first, resume = provider.calls
    assert first.query == "Which reminders do I have?"
    assert first.turn_mode == "new_turn"
    # The loop ran job_list against the scheduled_jobs table and resumed the provider session with its output.
    assert resume.turn_mode == "resume_turn"
    assert resume.session_id == "prov-sess-tools"
    assert resume.query.startswith("Here are the results of the agent tool calls you requested:")
    assert '<tool_result tool="job_list" success="true">' in resume.query
    assert f"#{job_id} | reminder |" in resume.query
    assert "Stretch break" in resume.query

    bot: FakeBot = application.bot
    tool_status = [message for message in bot.messages if (message.text or "").endswith("job_list...")]
    assert len(tool_status) == 1 and tool_status[0].deleted is True
    [answer] = bot.visible(chat_id)
    assert answer.text is not None
    assert answer.text.startswith("You have one reminder: Stretch break, every hour.")
    assert "<agent_cmd" not in answer.text

    row = await _task_row(agent_db, task_id)
    assert row["status"] == "completed"
    assert row["cost_usd"] == pytest.approx(0.03)
    _assert_lease_released(row)
    [logged] = await _fetch_all(agent_db, f'SELECT * FROM {_SCHEMA}."query_history" WHERE user_id = $1', user_id)
    assert logged["response_text"] == "You have one reminder: Stretch break, every hour."
    [step] = (await _execution_trace(agent_db, task_id))["tools"]
    assert (step["tool"], step["success"], step["metadata"]["write"]) == ("job_list", True, False)
    assert "Stretch break" in step["output"]


_CANCEL_REASON = "Cancelled by /cancel command."


class _CancelScenario:
    """Two messages from one user; the first turn is cancelled while its provider is streaming."""

    def __init__(self, application: FakeApplication, monkeypatch: pytest.MonkeyPatch, *, user_id: int) -> None:
        self.user_id = self.chat_id = user_id
        hold = asyncio.Event()  # never set: only the cancel ends the first turn

        def _script(call: ProviderCall) -> ProviderTurn:
            if call.query == "Write a long report":
                return ProviderTurn(text="Partial report…", hold=hold)
            return ProviderTurn(text="Here is the short answer.", cost_usd=0.001)

        self.provider = StubProvider(_script).install(monkeypatch)
        self.application = application
        self.first_id = 0
        self.second_id = 0

    async def start(self) -> None:
        """Send both messages; return once the first turn's provider is streaming."""
        app = self.application
        self.first_id = await _send(app, user_id=self.user_id, chat_id=self.chat_id, text="Write a long report")
        await asyncio.wait_for(self.provider.holding.wait(), timeout=_TURN_TIMEOUT_S)
        self.second_id = await _send(
            app, user_id=self.user_id, chat_id=self.chat_id, text="Quick question", message_id=2
        )

    async def assert_first_cancelled_and_second_answered(self, dsn: str) -> dict[str, Any]:
        await _wait_for_worker(self.user_id)
        assert self.provider.cancelled_turns == 1
        assert [call.query for call in self.provider.calls] == ["Write a long report", "Quick question"]

        cancelled = await _task_row(dsn, self.first_id)
        assert cancelled["status"] == "cancelled"
        assert cancelled["error_message"] == _CANCEL_REASON
        assert cancelled["completed_at"]
        _assert_lease_released(cancelled)
        assert (await _queue_item_row(dsn, self.first_id))["status"] == "cancelled"
        assert (await _task_row(dsn, self.second_id))["status"] == "completed"

        # Nothing of the cancelled turn stays visible: no partial output, answer or failure notice.
        bot: FakeBot = self.application.bot
        feedback, answer = bot.visible(self.chat_id)
        assert feedback.text == (
            "Received your message and queued it. I'll process it once the current task finishes. "
            f"Reference: #{self.second_id}."
        )
        assert answer.text is not None and answer.text.startswith("Here is the short answer.")
        assert answer.kwargs["reply_to_message_id"] == 2
        [logged] = await _fetch_all(dsn, f'SELECT * FROM {_SCHEMA}."query_history" WHERE user_id = $1', self.user_id)
        assert logged["query_text"] == "Quick question"
        return cancelled


async def test_cancel_stops_the_running_light_task_and_the_worker_runs_the_next_one(
    agent_db: str, queue_state: None, application: FakeApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cancelling a running light task through the queue's cancel primitive (D-009, fixed in DEFECT-BATCH-1).

    ``cancel_active_task_execution`` is what ``RuntimeController.cancel_task``,
    scheduler control and child-run timeouts call for a task that is already
    running. The turn's provider stream is cancelled, no response is
    delivered, the row is finalised as cancelled and the worker survives to
    run the next message.
    """
    from koda.services.queue_manager import cancel_active_task_execution

    scenario = _CancelScenario(application, monkeypatch, user_id=910004)
    try:
        await scenario.start()
        assert await cancel_active_task_execution(scenario.first_id, reason=_CANCEL_REASON) is True
        await scenario.assert_first_cancelled_and_second_answered(agent_db)
    finally:
        await _stop_worker(scenario.user_id)


class RuntimeStoreCannotSeeTask(AssertionError):
    """The runtime store reads ``tasks`` with a different ``agent_id`` casing than the task writer uses."""


@pytest.mark.xfail(
    strict=True,
    raises=RuntimeStoreCannotSeeTask,
    reason=(
        "New finding (agent_id casing, see D-061/TD-009 and M2-E3-T5): history_store writes tasks.agent_id "
        "upper-cased ('AGENT_A') while PostgresRuntimeStore reads it lower-cased ('agent_a'), so "
        "RuntimeController.cancel_task finds no task and /cancel <id> answers 'not found'."
    ),
)
async def test_cancel_command_stops_the_running_light_task_on_postgres(
    agent_db: str, queue_state: None, application: FakeApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``/cancel <id>``: the Telegram command cancels through ``RuntimeController.cancel_task``."""
    from koda.services.runtime import get_runtime_controller

    scenario = _CancelScenario(application, monkeypatch, user_id=910006)
    try:
        await scenario.start()
        controller = get_runtime_controller()
        result = await controller.cancel_task(
            task_id=scenario.first_id, actor="telegram_command", reason=_CANCEL_REASON
        )
        if result is None and controller.store.get_task_runtime(scenario.first_id) is None:
            row = await _task_row(agent_db, scenario.first_id)
            raise RuntimeStoreCannotSeeTask(
                f"task {scenario.first_id} exists with agent_id={row['agent_id']!r} and status={row['status']!r}, "
                f"but the runtime store looks it up with agent_id={controller.store._agent_scope!r}"
            )
        assert result == {
            "ok": True,
            "action": "cancelled",
            "task_id": scenario.first_id,
            "env_id": None,
            "final_phase": "cancelled_retained",
        }
        cancelled = await scenario.assert_first_cancelled_and_second_answered(agent_db)
        assert cancelled["current_phase"] == "cancelled_retained"
    finally:
        await _stop_worker(scenario.user_id)


class SquadFollowUpDeadlock(AssertionError):
    """The squad follow-up waits for the per-user worker lock its own post-processing holds (D-019)."""


@pytest.fixture
async def squad_stores(agent_db: str, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[Any, Any]]:
    """Squad thread and task stores on the test database.

    The squad stores read ``POSTGRES_URL``, which is empty in the test
    environment, and cache module-level singletons; both are pointed at the
    test database for this test only.
    """
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
    conn = await asyncpg.connect(agent_db)
    try:
        await reset_squad_runtime_tables(conn, _SCHEMA)
    finally:
        await conn.close()
    try:
        yield threads.get_squad_thread_store(), tasks.get_squad_task_store()
    finally:
        for module, attr in singletons:
            built = getattr(module, attr)
            if built is not None and hasattr(built, "close"):
                with contextlib.suppress(Exception):
                    await built.close()


def _awaited_coroutines(task: asyncio.Task[Any]) -> list[str]:
    """Names of the coroutines a suspended task is awaiting, outermost first."""
    names: list[str] = []
    awaitable: Any = task.get_coro()
    while awaitable is not None:
        code = getattr(awaitable, "cr_code", None)
        if code is not None:
            names.append(code.co_name)
        awaitable = getattr(awaitable, "cr_await", None)
    return names


@pytest.mark.xfail(
    strict=True,
    raises=SquadFollowUpDeadlock,
    reason=(
        "D-019: _post_process holds the per-user worker lock while enqueue_squad_agent_task "
        "reaches _ensure_queue_worker, which takes the same lock."
    ),
)
async def test_squad_follow_up_is_enqueued_and_runs_under_the_real_worker_lock(
    agent_db: str,
    queue_state: None,
    squad_stores: tuple[Any, Any],
    application: FakeApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A squad task whose dependency the turn completes is dispatched to its assignee and runs."""
    from koda.config import AGENT_ID
    from koda.services import queue_manager as qm

    thread_store, task_store = squad_stores
    user_id = 910005
    group_chat_id = -1009100050
    agent = str(AGENT_ID)
    thread = await thread_store.create_thread(
        workspace_id="acme",
        squad_id="launch",
        title="Launch page",
        owner_user_id=user_id,
        coordinator_agent_id="PM",
        telegram_chat_id=group_chat_id,
        participants=[(agent, "worker")],
    )
    copy_task = await task_store.create_task(
        thread_id=thread.id,
        title="Write the launch copy",
        assigner_agent_id="PM",
        kind="brief_copy",
        description="Write the launch copy.",
        assigned_agent_id=agent,
    )
    page_task = await task_store.create_task(
        thread_id=thread.id,
        title="Build the launch page",
        assigner_agent_id="PM",
        kind="frontend",
        description="Build the launch page from the approved copy.",
        assigned_agent_id=agent,
        depends_on=[copy_task.id],
    )

    def _script(call: ProviderCall) -> ProviderTurn:
        if f"Task request [frontend] {page_task.id}" in call.query:
            return ProviderTurn(text="Launch page built from the approved copy.", cost_usd=0.002)
        if "Write the launch copy" in call.query:
            return ProviderTurn(text="Launch copy: Ship faster with Koda.", cost_usd=0.001)
        return ProviderTurn(text="Noted.")

    provider = StubProvider(_script).install(monkeypatch)

    copy_turn_id = await qm.enqueue_squad_agent_task(
        application=application,
        user_id=user_id,
        chat_id=group_chat_id,
        query_text="Write the launch copy",
        executing_agent_id=agent,
        squad_thread_id=thread.id,
        squad_task_id=copy_task.id,
        parent_message_id="msg-1",
        delegation_chain=["PM"],
    )
    try:
        try:
            copy_row = await _wait_for_task_status(agent_db, copy_turn_id, {"completed", "failed"}, timeout=10)
        except TimeoutError:
            task_info = qm.get_task_info(copy_turn_id)
            chain = _awaited_coroutines(task_info.asyncio_task) if task_info and task_info.asyncio_task else []
            if "_post_process" in chain and "_ensure_queue_worker" in chain:
                raise SquadFollowUpDeadlock("the copy turn is stuck in " + " -> ".join(chain)) from None
            raise
        assert copy_row["status"] == "completed"
        assert (await task_store.get_task(copy_task.id)).status == "done"

        deadline = asyncio.get_running_loop().time() + 10
        while True:
            follow_ups = await _fetch_all(
                agent_db,
                f'SELECT * FROM {_SCHEMA}."tasks" WHERE user_id = $1 AND id <> $2 ORDER BY id',
                user_id,
                copy_turn_id,
            )
            if follow_ups or asyncio.get_running_loop().time() > deadline:
                break
            await asyncio.sleep(0.05)
        assert follow_ups, "the unblocked squad task was not enqueued"
        page_turn_id = int(follow_ups[0]["id"])
        assert follow_ups[0]["source_action"] == "squad_thread_input"
        page_row = await _wait_for_task_status(agent_db, page_turn_id, {"completed", "failed"}, timeout=10)
        assert page_row["status"] == "completed"
        assert (await task_store.get_task(page_task.id)).status == "done"
        assert any(f"Task request [frontend] {page_task.id}" in call.query for call in provider.calls)
        delivered = application.bot.visible_texts(group_chat_id)
        assert any(text.startswith("Launch copy: Ship faster with Koda.") for text in delivered)
        assert any(text.startswith("Launch page built from the approved copy.") for text in delivered)
    finally:
        await _stop_worker(user_id)
