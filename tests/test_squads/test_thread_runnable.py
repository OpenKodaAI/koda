"""A squad thread runs agent turns only while it is open and under its budget cap (D-075, F-SQD-19).

The router's budget sweep pauses a thread at 100% of its cap, and an operator can pause it from
the dashboard. Every path that runs a squad turn goes through ``dispatch_squad_turn`` or
``enqueue_squad_agent_task``, so both refuse a thread that is not open or whose spend reached
its cap, and the inbox dispatcher drops the turn such a thread refuses.
"""

from __future__ import annotations

import asyncio
import os
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import suppress
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from koda.squads.dispatch import SquadTurnDispatchResult, dispatch_squad_turn
from koda.squads.threads import SquadThreadStore
from tests.postgres_fixtures import reset_squad_runtime_tables


def _schema() -> str:
    return (os.environ.get("KNOWLEDGE_V2_POSTGRES_SCHEMA") or "knowledge_v2").strip() or "knowledge_v2"


def _thread(*, status: str = "open", cap: Decimal | None = None, cost: Decimal = Decimal(0)) -> SimpleNamespace:
    return SimpleNamespace(
        id="thread-1",
        squad_id="squad-1",
        status=status,
        budget_usd_cap=cap,
        cost_usd_accum=cost,
        owner_user_id=42,
        telegram_chat_id=None,
        telegram_message_thread_id=None,
    )


async def _dispatch(thread: Any) -> tuple[SquadTurnDispatchResult, AsyncMock, AsyncMock, Mock]:
    application = SimpleNamespace(user_data=defaultdict(dict), bot=object())
    enqueue = AsyncMock(return_value=77)
    runtime_http = AsyncMock()
    bus = Mock(send=AsyncMock(return_value="bus-1"))
    with (
        patch(
            "koda.services.runtime.get_runtime_controller",
            return_value=SimpleNamespace(_application=application),
        ),
        patch("koda.services.queue_manager.enqueue_squad_agent_task", enqueue),
        patch("koda.squads.dispatch._dispatch_via_runtime_http", runtime_http),
        patch("koda.agents.get_message_bus", return_value=bus),
    ):
        result = await dispatch_squad_turn(
            target_agent_id="FE",
            thread=thread,
            thread_store=AsyncMock(),
            query_text="Build the UI",
            parent_message_id="msg-1",
            squad_task_id="task-1",
        )
    return result, enqueue, runtime_http, bus


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("thread", "reason"),
    [
        (_thread(status="paused"), "thread is paused"),
        (_thread(status="completed"), "thread is completed"),
        (_thread(status="archived"), "thread is archived"),
        (_thread(cap=Decimal("1.00"), cost=Decimal("1.00")), "budget cap"),
        (_thread(cap=Decimal("1.00"), cost=Decimal("1.25")), "budget cap"),
    ],
)
async def test_dispatch_squad_turn_refuses_a_thread_that_cannot_run(thread: SimpleNamespace, reason: str) -> None:
    result, enqueue, runtime_http, bus = await _dispatch(thread)

    assert result.dispatched is False
    assert reason in str(result.error)
    # No transport is tried: not the local queue, not runtime HTTP, not the bus.
    enqueue.assert_not_awaited()
    runtime_http.assert_not_awaited()
    bus.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_squad_turn_runs_an_open_thread_under_its_cap() -> None:
    result, enqueue, _runtime_http, _bus = await _dispatch(_thread(cap=Decimal("1.00"), cost=Decimal("0.99")))

    assert result.dispatched is True
    enqueue.assert_awaited_once()


@pytest.mark.asyncio
async def test_the_inbox_dispatcher_drops_a_turn_its_thread_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    from koda.services import queue_manager as qm
    from koda.squads import SquadThreadNotRunnableError

    message = SimpleNamespace(
        message_id="msg-9",
        metadata={"kind": "task_request", "thread_id": "thread-1", "user_id": 42, "chat_id": -42},
        kind="task_request",
        message_type="task_request",
        thread_id="thread-1",
        from_agent="PM",
        content="Build the UI",
        causation_id=None,
    )

    class _Bus:
        def __init__(self) -> None:
            self.batches = 0
            self.ack = AsyncMock()
            self.nack = AsyncMock()

        async def receive_batch(self, _agent_id: str, *, limit: int, timeout: float) -> list[object]:
            self.batches += 1
            if self.batches > 1:
                monkeypatch.setattr(qm, "_shutting_down", True)
                return []
            return [message]

    bus = _Bus()
    monkeypatch.setattr("koda.config.SQUADS_ENABLED", True)
    refused = AsyncMock(side_effect=SquadThreadNotRunnableError("thread is paused"))
    with patch("koda.agents.get_message_bus", return_value=bus), patch.object(qm, "enqueue_squad_agent_task", refused):
        await asyncio.wait_for(qm.start_squad_inbox_dispatcher(SimpleNamespace(bot=None)), timeout=10)

    refused.assert_awaited_once()
    # The turn is dropped, not retried until it dead-letters.
    bus.ack.assert_awaited_once_with(qm.AGENT_ID or "default", "msg-9")
    bus.nack.assert_not_awaited()


# --- Postgres ---


@pytest.fixture
async def threads(migrated_postgres: str) -> AsyncIterator[SquadThreadStore]:
    import asyncpg  # type: ignore[import-not-found]

    conn = await asyncpg.connect(migrated_postgres)
    try:
        await reset_squad_runtime_tables(conn, _schema())
    finally:
        await conn.close()
    store = SquadThreadStore(dsn=migrated_postgres, schema=_schema())
    try:
        yield store
    finally:
        with suppress(Exception):
            await store.close()


async def _spend(threads: SquadThreadStore, thread_id: str, cost: str) -> None:
    """Set the thread's rolled-up spend, as the cost rollup trigger does after a turn."""
    pool = await threads._ensure_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f'UPDATE "{_schema()}"."squad_threads" SET cost_usd_accum = $2::numeric WHERE id = $1',
            thread_id,
            Decimal(cost),
        )


@pytest.mark.postgres
@pytest.mark.asyncio
@pytest.mark.parametrize(("state", "reason"), [("paused", "thread is paused"), ("spent", "budget cap")])
async def test_enqueue_squad_agent_task_refuses_a_thread_that_cannot_run(
    threads: SquadThreadStore, state: str, reason: str
) -> None:
    from koda.services.queue_manager import enqueue_squad_agent_task
    from koda.squads import SquadThreadNotRunnableError

    thread = await threads.create_thread(
        workspace_id="acme",
        squad_id="build",
        title="room",
        owner_user_id=42,
        coordinator_agent_id="PM",
        budget_usd_cap=Decimal("1.00"),
    )
    if state == "paused":
        await threads.update_thread_status(thread.id, "paused")
    else:
        await _spend(threads, thread.id, "1.00")
    create_task = Mock(return_value=1)
    with (
        patch("koda.squads.get_squad_thread_store", return_value=threads),
        patch("koda.services.queue_manager.create_task", create_task),
        pytest.raises(SquadThreadNotRunnableError, match=reason),
    ):
        await enqueue_squad_agent_task(
            application=SimpleNamespace(user_data=defaultdict(dict), bot=None),
            user_id=42,
            chat_id=-42,
            query_text="Build the UI",
            executing_agent_id="FE",
            squad_thread_id=thread.id,
        )
    # Nothing is queued: no runtime task row, no queue item.
    create_task.assert_not_called()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_a_thread_the_budget_sweep_pauses_runs_no_turn(threads: SquadThreadStore) -> None:
    from koda.squads.router import SquadRouter

    thread = await threads.create_thread(
        workspace_id="acme",
        squad_id="build",
        title="room",
        owner_user_id=42,
        coordinator_agent_id="PM",
        budget_usd_cap=Decimal("1.00"),
    )
    await _spend(threads, thread.id, "0.50")
    result, enqueue, _http, _bus = await _dispatch(await threads.get_thread(thread.id))
    assert result.dispatched is True
    enqueue.assert_awaited_once()

    await _spend(threads, thread.id, "1.00")
    task_store = AsyncMock()
    task_store.sweep_expired_claims = AsyncMock(return_value=[])
    report = await SquadRouter(task_store=task_store, thread_store=threads).sweep_once()
    assert report.budget_auto_pauses == 1

    paused = await threads.get_thread(thread.id)
    assert paused is not None and paused.status == "paused"
    result, enqueue, _http, _bus = await _dispatch(paused)
    assert result.dispatched is False
    enqueue.assert_not_awaited()
    history = await threads.thread_history(thread_id=thread.id, limit=20)
    [event] = [m for m in history if (m.get("metadata") or {}).get("event_type") == "budget_exceeded_auto_pause"]
    assert event["metadata"]["reason"] == "budget"


@pytest.mark.asyncio
async def test_a_turn_the_queue_refuses_is_not_recorded_as_a_dispatch_failure() -> None:
    from koda.squads import SquadThreadNotRunnableError

    # The thread read before dispatch is open; the queue's own read finds it paused.
    application = SimpleNamespace(user_data=defaultdict(dict), bot=object())
    enqueue = AsyncMock(side_effect=SquadThreadNotRunnableError("thread is paused"))
    thread_store = AsyncMock()
    with (
        patch(
            "koda.services.runtime.get_runtime_controller",
            return_value=SimpleNamespace(_application=application),
        ),
        patch("koda.services.queue_manager.enqueue_squad_agent_task", enqueue),
    ):
        result = await dispatch_squad_turn(
            target_agent_id="FE",
            thread=_thread(),
            thread_store=thread_store,
            query_text="Build the UI",
            parent_message_id="msg-1",
            squad_task_id="task-1",
        )

    assert result.dispatched is False
    assert result.error == "thread is paused"
    # A deliberate refusal posts no agent_dispatch_unavailable event: the room already says why.
    thread_store.post_thread_message.assert_not_awaited()


@pytest.fixture
def fresh_queues(monkeypatch: pytest.MonkeyPatch) -> None:
    """Module queue state of the runtime, empty for the test and restored after it."""
    from koda.services import queue_manager as qm

    for name in ("_user_queues", "_queue_workers", "_user_queue_task_ids", "_user_tasks", "_squad_turn_claims"):
        monkeypatch.setattr(qm, name, {}, raising=False)


async def _queue_a_squad_turn(thread_id: str) -> int:
    """Queue a squad turn on the owner's per-user queue while no worker runs it yet."""
    from koda.services import queue_manager as qm

    with (
        patch.object(qm, "create_task", Mock(return_value=501)),
        patch.object(qm, "_persist_runtime_queue_item", AsyncMock()),
        patch.object(qm, "_ensure_queue_worker", AsyncMock()),
    ):
        return await qm.enqueue_squad_agent_task(
            application=SimpleNamespace(user_data=defaultdict(dict), bot=None),
            user_id=42,
            chat_id=-42,
            query_text="Build the UI",
            executing_agent_id="FE",
            squad_thread_id=thread_id,
            squad_task_id="00000000-0000-0000-0000-0000000000f1",
        )


@pytest.mark.postgres
@pytest.mark.asyncio
@pytest.mark.parametrize(("state", "reason"), [("paused", "thread is paused"), ("spent", "budget cap"), ("open", None)])
async def test_the_queue_worker_runs_no_turn_of_a_thread_that_stopped_after_the_turn_was_queued(
    threads: SquadThreadStore, fresh_queues: None, state: str, reason: str | None
) -> None:
    from koda.services import queue_manager as qm

    thread = await threads.create_thread(
        workspace_id="acme",
        squad_id="build",
        title="room",
        owner_user_id=42,
        coordinator_agent_id="PM",
        budget_usd_cap=Decimal("1.00"),
    )
    execute = AsyncMock()
    update_status = Mock()
    record_failed = AsyncMock()
    with patch("koda.squads.get_squad_thread_store", return_value=threads):
        assert await _queue_a_squad_turn(thread.id) == 501
        # The operator pauses, or a turn ahead of this one spends the cap, before the worker gets here.
        if state == "paused":
            await threads.update_thread_status(thread.id, "paused")
        elif state == "spent":
            await _spend(threads, thread.id, "1.00")
        with (
            patch.object(qm, "_execute_single_task", execute),
            patch.object(qm, "update_task_status", update_status),
            patch.object(qm, "_update_runtime_queue_status", Mock()),
            patch.object(qm, "_record_failed_squad_task_turn", record_failed),
        ):
            await qm._process_queue(42, SimpleNamespace(user_data={}, bot=None, application=None))

    if reason is None:
        execute.assert_awaited_once()
        return
    execute.assert_not_awaited()
    [call] = update_status.call_args_list
    assert call.args == (501, "cancelled")
    assert reason in str(call.kwargs["error_message"])
    # A deliberate refusal is not a failed turn: no failed task result. The task's claim is released
    # for the router to dispatch it again once the thread runs.
    record_failed.assert_not_awaited()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_concurrent_pauses_report_one_open_to_paused_transition(threads: SquadThreadStore) -> None:
    thread = await threads.create_thread(workspace_id="acme", squad_id="build", title="room")

    results = await asyncio.gather(
        threads.transition_thread_status(thread.id, "paused"),
        threads.transition_thread_status(thread.id, "paused"),
    )

    assert sorted(previous for _thread, previous in results) == ["open", "paused"]
    assert all(updated.status == "paused" for updated, _previous in results)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_the_budget_sweep_pauses_a_room_reopened_at_its_cap_again_and_says_so(threads: SquadThreadStore) -> None:
    from koda.squads.router import SquadRouter

    thread = await threads.create_thread(
        workspace_id="acme",
        squad_id="build",
        title="room",
        owner_user_id=42,
        coordinator_agent_id="PM",
        budget_usd_cap=Decimal("1.00"),
    )
    await _spend(threads, thread.id, "1.00")
    task_store = AsyncMock()
    task_store.sweep_expired_claims = AsyncMock(return_value=[])
    router = SquadRouter(task_store=task_store, thread_store=threads)
    assert (await router.sweep_once()).budget_auto_pauses == 1

    # The operator reopens the room; the cap cannot be raised from the dashboard.
    await threads.update_thread_status(thread.id, "open")
    assert (await router.sweep_once()).budget_auto_pauses == 1

    paused = await threads.get_thread(thread.id)
    assert paused is not None and paused.status == "paused"
    history = await threads.thread_history(thread_id=thread.id, limit=20)
    events = [m for m in history if (m.get("metadata") or {}).get("event_type") == "budget_exceeded_auto_pause"]
    assert len(events) == 2
    # Nothing else changed, so a third sweep posts nothing.
    assert (await router.sweep_once()).budget_auto_pauses == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("read", ["fails", "finds_nothing", "has_no_store"])
async def test_the_queue_worker_runs_no_squad_turn_whose_thread_it_cannot_read(fresh_queues: None, read: str) -> None:
    from koda.services import queue_manager as qm

    thread_store = AsyncMock()
    thread_store.get_thread = (
        AsyncMock(side_effect=ConnectionError("postgres is down")) if read == "fails" else AsyncMock(return_value=None)
    )
    task_store = AsyncMock()
    squad_task_id = "00000000-0000-0000-0000-0000000000f2"
    await qm.get_queue(42).put(
        {
            "_dashboard_chat": True,
            "_task_id": 502,
            "chat_id": -42,
            "query_text": "Build the UI",
            "executing_agent_id": "FE",
            "squad_thread_id": "thread-1",
            "squad_task_id": squad_task_id,
        }
    )
    execute = AsyncMock()
    update_status = Mock()
    with (
        patch("koda.squads.get_squad_thread_store", return_value=None if read == "has_no_store" else thread_store),
        patch("koda.squads.get_squad_task_store", return_value=task_store),
        patch.object(qm, "_execute_single_task", execute),
        patch.object(qm, "update_task_status", update_status),
        patch.object(qm, "_update_runtime_queue_status", Mock()),
    ):
        await qm._process_queue(42, SimpleNamespace(user_data={}, bot=None, application=None))

    # A thread the worker cannot read may be paused or spent, so its turn does not run (D-075).
    execute.assert_not_awaited()
    [call] = update_status.call_args_list
    assert call.args == (502, "cancelled")
    assert "could not be read" in str(call.kwargs["error_message"])
    # Its task's claim is released for the router to dispatch it again once the thread reads runnable.
    task_store.release_refused_claim.assert_awaited_once_with(task_id=squad_task_id, agent_id="FE")


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_enqueue_squad_agent_task_refuses_a_thread_it_cannot_find(threads: SquadThreadStore) -> None:
    from koda.services.queue_manager import enqueue_squad_agent_task
    from koda.squads import SquadThreadNotRunnableError

    create_task = Mock(return_value=1)
    with (
        patch("koda.squads.get_squad_thread_store", return_value=threads),
        patch("koda.services.queue_manager.create_task", create_task),
        pytest.raises(SquadThreadNotRunnableError, match="could not be read"),
    ):
        await enqueue_squad_agent_task(
            application=SimpleNamespace(user_data=defaultdict(dict), bot=None),
            user_id=42,
            chat_id=-42,
            query_text="Build the UI",
            executing_agent_id="FE",
            squad_thread_id="00000000-0000-0000-0000-00000000dead",
        )
    create_task.assert_not_called()


def _budget_events(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [m for m in history if (m.get("metadata") or {}).get("event_type") == "budget_exceeded_auto_pause"]


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_a_room_reopened_under_its_cap_is_no_longer_budget_paused_and_a_later_overrun_pauses_it_again(
    threads: SquadThreadStore,
) -> None:
    from koda.squads.router import SquadRouter

    thread = await threads.create_thread(
        workspace_id="acme",
        squad_id="build",
        title="room",
        owner_user_id=42,
        coordinator_agent_id="PM",
        budget_usd_cap=Decimal("1.00"),
    )
    task_store = AsyncMock()
    task_store.sweep_expired_claims = AsyncMock(return_value=[])
    router = SquadRouter(task_store=task_store, thread_store=threads)
    await _spend(threads, thread.id, "1.00")
    assert (await router.sweep_once()).budget_auto_pauses == 1
    paused = await threads.get_thread(thread.id)
    assert paused is not None and paused.metadata.get("budget_auto_paused") is True

    # The spend is corrected below the cap and the operator reopens the room: it is no longer
    # paused by the budget, and the sweep leaves it open.
    await _spend(threads, thread.id, "0.50")
    await threads.update_thread_status(thread.id, "open")
    reopened = await threads.get_thread(thread.id)
    assert reopened is not None and "budget_auto_paused" not in reopened.metadata
    assert (await router.sweep_once()).budget_auto_pauses == 0

    # A later overrun pauses it again, with one event per pause.
    await _spend(threads, thread.id, "1.10")
    assert (await router.sweep_once()).budget_auto_pauses == 1
    assert (await router.sweep_once()).budget_auto_pauses == 0
    again = await threads.get_thread(thread.id)
    assert again is not None and again.status == "paused" and again.metadata.get("budget_auto_paused") is True
    assert len(_budget_events(await threads.thread_history(thread_id=thread.id, limit=50))) == 2


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_the_budget_sweep_reaches_an_open_room_at_its_cap_behind_a_full_batch_of_paused_rooms(
    threads: SquadThreadStore,
) -> None:
    from koda.squads.router import SquadRouter

    # More paused rooms above 80% of their cap than one batch holds, already alerted, so the sweep
    # has nothing left to do for them; they changed before the open room did.
    for index, cost in enumerate(("0.90", "1.50", "1.00")):
        stale = await threads.create_thread(
            workspace_id="acme",
            squad_id="build",
            title=f"paused room {index}",
            budget_usd_cap=Decimal("1.00"),
            metadata={"budget_alert_80_sent": True},
        )
        await threads.update_thread_status(stale.id, "paused")
        await _spend(threads, stale.id, cost)
    room = await threads.create_thread(
        workspace_id="acme",
        squad_id="build",
        title="open room",
        budget_usd_cap=Decimal("1.00"),
        metadata={"budget_alert_80_sent": True},
    )
    await _spend(threads, room.id, "1.00")
    task_store = AsyncMock()
    task_store.sweep_expired_claims = AsyncMock(return_value=[])

    report = await SquadRouter(task_store=task_store, thread_store=threads, batch_size=2).sweep_once()

    assert report.budget_auto_pauses == 1
    paused = await threads.get_thread(room.id)
    assert paused is not None and paused.status == "paused"
    assert len(_budget_events(await threads.thread_history(thread_id=room.id, limit=50))) == 1
