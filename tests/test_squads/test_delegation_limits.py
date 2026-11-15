"""Delegation and ``agent_send`` in a squad thread are bounded (D-095, D-096, F-SQD-06, F-SQD-07, R-27).

Each delegation request and ``agent_send`` message carries the whole chain of agents that led to
it, ending with its sender. The sender's tool refuses a delegation to an agent already in the
chain (a cycle), one deeper than ``INTER_AGENT_MAX_DELEGATION_DEPTH``, and an ``agent_send``
longer than ``MAX_REPLY_DEPTH`` hops; the inbox dispatcher refuses the same before it enqueues a
turn. Each refusal in a squad thread posts one ``delegation_limit_reached`` system event whose
``limit`` names it (P25).
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import suppress
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from koda.agents.models import DelegationRequest
from koda.agents.postgres_message_bus import PostgresMessageBus
from koda.services.tool_dispatcher import ToolContext, _handle_agent_delegate, _handle_agent_send
from koda.squads.threads import SquadThreadStore
from tests.postgres_fixtures import reset_squad_runtime_tables


def _schema() -> str:
    return (os.environ.get("KNOWLEDGE_V2_POSTGRES_SCHEMA") or "knowledge_v2").strip() or "knowledge_v2"


@pytest.fixture
async def room(migrated_postgres: str, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[SimpleNamespace]:
    """A squad thread, its store and a real Postgres bus, wired in as this runtime's."""
    import asyncpg  # type: ignore[import-not-found]

    conn = await asyncpg.connect(migrated_postgres)
    try:
        await reset_squad_runtime_tables(conn, _schema())
    finally:
        await conn.close()
    threads = SquadThreadStore(dsn=migrated_postgres, schema=_schema())
    bus = PostgresMessageBus(dsn=migrated_postgres, schema=_schema(), lease_seconds=1, listen_enabled=False)
    thread = await threads.create_thread(
        workspace_id="acme",
        squad_id="build",
        title="room",
        owner_user_id=42,
        coordinator_agent_id="PM",
    )
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    monkeypatch.setattr("koda.config.SQUADS_ENABLED", True)
    monkeypatch.setattr("koda.config.SQUAD_POLL_INTERVAL_S", 0.5)
    access = Mock(require_thread_access=AsyncMock())
    with (
        patch("koda.agents.get_message_bus", return_value=bus),
        patch("koda.squads.get_squad_thread_store", return_value=threads),
        patch("koda.squads.get_squad_access_service", return_value=access),
    ):
        try:
            yield SimpleNamespace(threads=threads, bus=bus, thread=thread)
        finally:
            with suppress(Exception):
                await bus.close()
            with suppress(Exception):
                await threads.close()


def _ctx(agent_id: str, thread_id: str, chain: list[str]) -> ToolContext:
    return ToolContext(
        user_id=42,
        chat_id=-42,
        work_dir="/tmp",
        user_data={},
        agent=None,
        agent_mode="normal",
        executing_agent_id=agent_id,
        squad_thread_id=thread_id,
        delegation_chain=list(chain),
    )


def _turn_ctx(turn: dict[str, Any]) -> ToolContext:
    """The tool context of an enqueued squad turn, as the queue worker builds it."""
    return _ctx(turn["executing_agent_id"], turn["squad_thread_id"], turn["delegation_chain"])


async def _deliver(room: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, agent_id: str) -> list[dict[str, Any]]:
    """Run ``agent_id``'s inbox dispatcher over its waiting messages once; returns the turns it enqueued."""
    from koda.services import queue_manager as qm

    enqueued: list[dict[str, Any]] = []

    async def enqueue(**kwargs: Any) -> int:
        enqueued.append(kwargs)
        return len(enqueued)

    receive_batch = room.bus.receive_batch
    batches = 0

    async def one_batch(agent: str, *, limit: int, timeout: float) -> list[Any]:
        nonlocal batches
        batches += 1
        if batches > 1:
            monkeypatch.setattr(qm, "_shutting_down", True)
            return []
        return list(await receive_batch(agent, limit=limit, timeout=timeout))

    monkeypatch.setattr(qm, "AGENT_ID", agent_id)
    monkeypatch.setattr(room.bus, "receive_batch", one_batch)
    try:
        with patch.object(qm, "enqueue_squad_agent_task", enqueue):
            await asyncio.wait_for(qm.start_squad_inbox_dispatcher(SimpleNamespace(bot=None)), timeout=20)
    finally:
        monkeypatch.setattr(qm, "_shutting_down", False)
        monkeypatch.setattr(room.bus, "receive_batch", receive_batch)
    # The limit event and the failed delegation result are written by tasks the dispatcher starts.
    await asyncio.sleep(0.2)
    return enqueued


async def _limit_events(room: SimpleNamespace) -> list[dict[str, Any]]:
    history = await room.threads.thread_history(thread_id=room.thread.id, limit=100)
    return [m for m in history if (m.get("metadata") or {}).get("event_type") == "delegation_limit_reached"]


async def _stop(*tasks: asyncio.Task[Any]) -> None:
    for task in tasks:
        task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await task


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_an_a_b_c_a_delegation_cycle_is_rejected_with_one_event(
    room: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Depth is not what stops this chain: only the cycle limit applies.
    monkeypatch.setattr("koda.config.INTER_AGENT_MAX_DELEGATION_DEPTH", 10)
    thread_id = room.thread.id

    a = asyncio.create_task(
        _handle_agent_delegate({"to": "B", "task": "plan", "timeout": 30}, _ctx("A", thread_id, ["squad_router"]))
    )
    [b_turn] = await _deliver(room, monkeypatch, "B")
    # The chain survives the hop: B's turn knows A delegated to it.
    assert b_turn["delegation_chain"] == ["squad_router", "A"]

    b = asyncio.create_task(_handle_agent_delegate({"to": "C", "task": "build", "timeout": 30}, _turn_ctx(b_turn)))
    [c_turn] = await _deliver(room, monkeypatch, "C")
    assert c_turn["delegation_chain"] == ["squad_router", "A", "B"]

    try:
        result = await _handle_agent_delegate({"to": "A", "task": "review", "timeout": 30}, _turn_ctx(c_turn))
        assert not result.success
        assert "cycle" in result.output.lower()
        # Nothing reached A.
        assert await _deliver(room, monkeypatch, "A") == []
        [event] = await _limit_events(room)
        assert event["metadata"]["limit"] == "cycle"
        assert event["metadata"]["from_agent"] == "C"
        assert event["metadata"]["to_agent"] == "A"
        assert event["metadata"]["delegation_chain"] == ["squad_router", "A", "B", "C"]
        assert event["type"] == "system_event"
    finally:
        await _stop(a, b)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_delegation_depth_is_capped_across_hops_with_one_event(
    room: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("koda.config.INTER_AGENT_MAX_DELEGATION_DEPTH", 3)
    thread_id = room.thread.id

    a = asyncio.create_task(
        _handle_agent_delegate({"to": "B", "task": "plan", "timeout": 30}, _ctx("A", thread_id, ["squad_router"]))
    )
    [b_turn] = await _deliver(room, monkeypatch, "B")
    b = asyncio.create_task(_handle_agent_delegate({"to": "C", "task": "build", "timeout": 30}, _turn_ctx(b_turn)))
    [c_turn] = await _deliver(room, monkeypatch, "C")

    try:
        # C's delegation would be the fourth link of the chain: past the cap of 3.
        result = await _handle_agent_delegate({"to": "D", "task": "test", "timeout": 30}, _turn_ctx(c_turn))
        assert not result.success
        assert "depth" in result.output.lower()
        assert await _deliver(room, monkeypatch, "D") == []
        [event] = await _limit_events(room)
        assert event["metadata"]["limit"] == "depth"
        assert event["metadata"]["max"] == 3
    finally:
        await _stop(a, b)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_agent_send_ping_pong_stops_at_the_hop_limit_with_one_event(
    room: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    from koda.squads import MAX_REPLY_DEPTH

    ctx = _ctx("A", room.thread.id, ["squad_router"])
    delivered = 0
    refused = None
    for _ in range(4 * MAX_REPLY_DEPTH):
        to = "B" if ctx.executing_agent_id == "A" else "A"
        sent = await _handle_agent_send({"to": to, "message": "ping"}, ctx)
        if not sent.success:
            refused = sent
            break
        [turn] = await _deliver(room, monkeypatch, to)
        delivered += 1
        ctx = _turn_ctx(turn)

    assert refused is not None, "A and B kept answering each other"
    assert "hop" in refused.output.lower()
    # The chain starts at the router, so the hops up to the limit are the router's and the agents'.
    assert delivered == MAX_REPLY_DEPTH - 1
    [event] = await _limit_events(room)
    assert event["metadata"]["limit"] == "hop_count"
    assert event["metadata"]["max"] == MAX_REPLY_DEPTH


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_the_inbox_counts_agent_send_hops_when_the_sender_does_not_add_itself(
    room: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sender that passes its turn's chain on as is (an older runtime) still stops at the hop limit."""
    from koda.squads import MAX_REPLY_DEPTH

    sender, chain = "A", ["squad_router"]
    delivered = 0
    for _ in range(2 * MAX_REPLY_DEPTH):
        to = "B" if sender == "A" else "A"
        await room.bus.send(
            sender, to, "ping", {"thread_id": room.thread.id, "delegation_chain": chain, "kind": "agent_text"}
        )
        turns = await _deliver(room, monkeypatch, to)
        if not turns:
            break
        delivered += 1
        sender, chain = to, turns[0]["delegation_chain"]

    assert delivered == MAX_REPLY_DEPTH - 1, "A and B kept answering each other"
    [event] = await _limit_events(room)
    assert event["metadata"]["limit"] == "hop_count"


@pytest.mark.postgres
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("chain", "limit"),
    [
        (["squad_router", "A", "B", "C"], "cycle"),
        (["squad_router", "X", "B", "C"], "depth"),
    ],
)
async def test_the_inbox_dispatcher_refuses_a_delegation_past_a_limit(
    room: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, chain: list[str], limit: str
) -> None:
    """A request the sender did not check (another runtime) is refused before a turn is enqueued."""
    monkeypatch.setattr("koda.config.INTER_AGENT_MAX_DELEGATION_DEPTH", 10 if limit == "cycle" else 3)
    # The sender's own check is bypassed: the request goes straight to the bus, with the depth of
    # a runtime whose chain reset at every hop (D-095), so only its chain shows the limit.
    request = DelegationRequest(
        from_agent="C",
        to_agent="A",
        task="review",
        timeout=15,
        thread_id=room.thread.id,
        delegation_chain=chain,
        delegation_depth=0,
    )
    delegation = asyncio.create_task(room.bus.delegate(request))
    try:
        assert await _deliver(room, monkeypatch, "A") == []
        # The delegator is told at once, rather than waiting for its timeout.
        result = await asyncio.wait_for(delegation, timeout=10)
        assert not result.success
        assert limit in (result.error or "").lower()
        [event] = await _limit_events(room)
        assert event["metadata"]["limit"] == limit
        assert event["metadata"]["to_agent"] == "A"
    finally:
        await _stop(delegation)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_the_inbox_dispatcher_refuses_an_agent_send_past_the_hop_limit(
    room: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    from koda.squads import MAX_REPLY_DEPTH

    chain = ["squad_router", *(["A", "B"] * MAX_REPLY_DEPTH)][: MAX_REPLY_DEPTH + 1]
    await room.bus.send(
        chain[-1],
        "A" if chain[-1] == "B" else "B",
        "ping",
        {"thread_id": room.thread.id, "delegation_chain": chain, "kind": "agent_text"},
    )
    assert await _deliver(room, monkeypatch, "A" if chain[-1] == "B" else "B") == []
    [event] = await _limit_events(room)
    assert event["metadata"]["limit"] == "hop_count"


def _no_local_runtime() -> Any:
    """No runtime application in this process, so a squad turn goes to the runtime API, then the bus."""
    return patch("koda.squads.dispatch._runtime_application_or_none", return_value=None)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_a_squad_turn_carries_its_whole_chain_on_every_dispatch_path(
    room: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The local queue, the runtime API and the bus fallback deliver the same chain (D-352)."""
    from koda.services import queue_manager as qm
    from koda.squads import dispatch_squad_turn

    chain = ["squad_router", "A", "B"]

    async def dispatch(application: Any = None) -> Any:
        return await dispatch_squad_turn(
            target_agent_id="C",
            thread=room.thread,
            thread_store=room.threads,
            query_text="answer",
            parent_message_id=None,
            metadata={"from_agent": "B", "source": "squad_reply"},
            application=application,
            delegation_chain=list(chain),
        )

    local = AsyncMock(return_value=11)
    with patch.object(qm, "enqueue_squad_agent_task", local):
        assert (await dispatch(application=SimpleNamespace(bot=None))).transport == "local_queue"
    assert local.await_args.kwargs["delegation_chain"] == chain

    manager = Mock()
    manager.send_dashboard_squad_message.return_value = {"task_id": 12, "session_id": "s-1"}
    with _no_local_runtime(), patch("koda.control_plane.manager.get_control_plane_manager", return_value=manager):
        assert (await dispatch()).transport == "runtime_http"
        assert manager.send_dashboard_squad_message.call_args.kwargs["delegation_chain"] == chain

        manager.send_dashboard_squad_message.side_effect = RuntimeError("runtime API down")
        assert (await dispatch()).transport == "bus"
    [turn] = await _deliver(room, monkeypatch, "C")
    assert turn["delegation_chain"] == chain


@pytest.mark.postgres
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("metadata", "request_id"),
    [
        # A squad_reply turn is correlated by its reply obligation's key.
        ({"from_agent": "B", "source": "squad_reply", "correlation_id": "obligation-1"}, "obligation-1"),
        # A coordinator synthesis is correlated by its idempotency key.
        (
            {"from_agent": "B", "kind": "task_result", "delivery_intent": "final_synthesis"},
            "squad_synthesis:thread:msg-1:C",
        ),
    ],
    ids=["squad_reply", "synthesis"],
)
async def test_a_squad_reply_or_synthesis_turn_carries_its_correlation_on_every_dispatch_path(
    room: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, metadata: dict[str, Any], request_id: str
) -> None:
    """The local queue, the runtime API and the bus fallback deliver the same request id and origin (D-363)."""
    from koda.services import queue_manager as qm
    from koda.squads import dispatch_squad_turn

    async def dispatch(application: Any = None) -> Any:
        return await dispatch_squad_turn(
            target_agent_id="C",
            thread=room.thread,
            thread_store=room.threads,
            query_text="answer",
            parent_message_id="msg-1",
            metadata=dict(metadata),
            application=application,
            delegation_chain=["B"],
            delegation_request_id=request_id,
            delegation_origin_agent_id="B",
        )

    local = AsyncMock(return_value=11)
    with patch.object(qm, "enqueue_squad_agent_task", local):
        assert (await dispatch(application=SimpleNamespace(bot=None))).transport == "local_queue"
    assert local.await_args.kwargs["delegation_request_id"] == request_id
    assert local.await_args.kwargs["delegation_origin_agent_id"] == "B"

    manager = Mock()
    manager.send_dashboard_squad_message.return_value = {"task_id": 12, "session_id": "s-1"}
    with _no_local_runtime(), patch("koda.control_plane.manager.get_control_plane_manager", return_value=manager):
        assert (await dispatch()).transport == "runtime_http"
        assert manager.send_dashboard_squad_message.call_args.kwargs["delegation_request_id"] == request_id
        assert manager.send_dashboard_squad_message.call_args.kwargs["delegation_origin_agent_id"] == "B"

        manager.send_dashboard_squad_message.side_effect = RuntimeError("runtime API down")
        assert (await dispatch()).transport == "bus"
    [turn] = await _deliver(room, monkeypatch, "C")
    assert turn["delegation_request_id"] == request_id
    assert turn["delegation_origin_agent_id"] == "B"


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_a_ping_pong_through_the_bus_fallback_stops_at_the_hop_limit_with_one_event(
    room: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A answers B with squad_reply, delivered through the bus, and B answers A with agent_send (D-352).

    The reply turn keeps the chain it came with, so B's agent_send counts every hop and the two
    stop at the hop limit, instead of starting again from ``[A]`` at each reply.
    """
    from koda.services.tool_dispatcher import _handle_squad_reply
    from koda.squads import MAX_REPLY_DEPTH

    for agent_id in ("A", "B"):
        await room.threads.add_participant(thread_id=room.thread.id, agent_id=agent_id)
    manager = Mock()
    manager.send_dashboard_squad_message.side_effect = RuntimeError("runtime API down")
    ctx = _ctx("A", room.thread.id, ["squad_router"])
    refused = None
    with _no_local_runtime(), patch("koda.control_plane.manager.get_control_plane_manager", return_value=manager):
        for _ in range(2 * MAX_REPLY_DEPTH):
            replied = await _handle_squad_reply({"content": "pong", "target_agent_ids": ["B"]}, ctx)
            assert replied.success, replied.output
            [b_turn] = await _deliver(room, monkeypatch, "B")
            sent = await _handle_agent_send({"to": "A", "message": "ping"}, _turn_ctx(b_turn))
            if not sent.success:
                refused = sent
                break
            [a_turn] = await _deliver(room, monkeypatch, "A")
            ctx = _turn_ctx(a_turn)

    assert refused is not None, "A and B kept answering each other"
    assert "hop" in refused.output.lower()
    [event] = await _limit_events(room)
    assert event["metadata"]["limit"] == "hop_count"
    # Every hop counts: the router's, then A and B in turn, up to the one past the limit.
    hops = ["squad_router", *(["A", "B"] * MAX_REPLY_DEPTH)]
    assert event["metadata"]["delegation_chain"] == hops[: MAX_REPLY_DEPTH + 1]


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_a_delegation_outside_a_squad_thread_fails_at_once_over_the_postgres_bus(
    room: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Postgres bus runs squad turns only: a thread-less delegator is told so, not left to time out (D-353)."""
    request = DelegationRequest(from_agent="A", to_agent="B", task="review", timeout=60, delegation_chain=["A"])
    delegation = asyncio.create_task(room.bus.delegate(request))
    try:
        assert await _deliver(room, monkeypatch, "B") == []
        result = await asyncio.wait_for(delegation, timeout=10)
        assert not result.success
        assert "squad thread" in (result.error or "")
    finally:
        await _stop(delegation)
