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
