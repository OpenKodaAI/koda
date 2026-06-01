"""Tests for the Postgres-backed inter-agent message bus."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import suppress

import pytest

from koda.agents.message_bus_iface import MessageBus
from koda.agents.models import DelegationRequest, DelegationResult
from koda.agents.postgres_message_bus import PostgresMessageBus


def test_postgres_satisfies_messagebus_protocol() -> None:
    bus = PostgresMessageBus(dsn="postgresql://disabled/skip")
    assert isinstance(bus, MessageBus)


def test_postgres_rejects_invalid_schema() -> None:
    with pytest.raises(ValueError):
        PostgresMessageBus(dsn="postgresql://x/y", schema="bad schema!")


def _schema() -> str:
    return (os.environ.get("KNOWLEDGE_V2_POSTGRES_SCHEMA") or "knowledge_v2").strip() or "knowledge_v2"


@pytest.fixture
async def clean_squad_messages(migrated_postgres: str) -> AsyncIterator[str]:
    import asyncpg  # type: ignore[import-not-found]

    schema = _schema()
    conn = await asyncpg.connect(migrated_postgres)
    try:
        await conn.execute(f'TRUNCATE TABLE "{schema}"."squad_message_recipients"')
        await conn.execute(f'TRUNCATE TABLE "{schema}"."squad_messages" RESTART IDENTITY CASCADE')
    finally:
        await conn.close()
    yield migrated_postgres


@pytest.fixture
async def bus_factory(clean_squad_messages: str) -> AsyncIterator[list[PostgresMessageBus]]:
    schema = _schema()
    instances: list[PostgresMessageBus] = []

    def _make() -> PostgresMessageBus:
        b = PostgresMessageBus(dsn=clean_squad_messages, schema=schema, lease_seconds=1)
        instances.append(b)
        return b

    try:
        yield _make  # type: ignore[misc]
    finally:
        for b in instances:
            with suppress(Exception):
                await b.close()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_send_and_receive_roundtrip(bus_factory) -> None:  # type: ignore[no-untyped-def]
    sender = bus_factory()
    receiver = bus_factory()
    msg_id = await sender.send("agent-a", "agent-b", "hello squad")
    assert msg_id.startswith("msg-")
    msg = await receiver.receive("agent-b", timeout=3)
    assert msg is not None
    assert msg.from_agent == "agent-a"
    assert msg.to_agent == "agent-b"
    assert msg.content == "hello squad"
    assert msg.message_type == "text"
    await receiver.ack("agent-b", msg.message_id)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_durable_across_instances(bus_factory) -> None:  # type: ignore[no-untyped-def]
    sender = bus_factory()
    await sender.send("agent-a", "agent-b", "msg-1")
    await sender.send("agent-a", "agent-b", "msg-2")
    later_receiver = bus_factory()
    first = await later_receiver.receive("agent-b", timeout=3)
    assert first is not None and first.content == "msg-1"
    await later_receiver.ack("agent-b", first.message_id)
    second = await later_receiver.receive("agent-b", timeout=3)
    assert second is not None and second.content == "msg-2"
    await later_receiver.ack("agent-b", second.message_id)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_receive_replays_until_ack_then_skips(bus_factory) -> None:  # type: ignore[no-untyped-def]
    sender = bus_factory()
    await sender.send("agent-a", "agent-b", "replay")
    receiver = bus_factory()
    first = await receiver.receive("agent-b", timeout=3)
    assert first is not None and first.content == "replay"
    assert await receiver.receive("agent-b", timeout=0.2) is None
    await asyncio.sleep(1.1)
    replayed = await receiver.receive("agent-b", timeout=3)
    assert replayed is not None and replayed.message_id == first.message_id
    await receiver.ack("agent-b", first.message_id)
    assert await receiver.receive("agent-b", timeout=0.5) is None


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_nack_retries_then_dead(clean_squad_messages: str) -> None:
    import asyncpg  # type: ignore[import-not-found]

    bus = PostgresMessageBus(
        dsn=clean_squad_messages,
        schema=_schema(),
        lease_seconds=1,
        max_delivery_attempts=2,
    )
    try:
        await bus.send("agent-a", "agent-b", "flaky")
        first = await bus.receive("agent-b", timeout=3)
        assert first is not None
        await bus.nack("agent-b", first.message_id, error="boom", retry_after=0.1)
        await asyncio.sleep(0.2)
        second = await bus.receive("agent-b", timeout=3)
        assert second is not None and second.message_id == first.message_id
        await bus.nack("agent-b", second.message_id, error="boom again")
        assert await bus.receive("agent-b", timeout=0.5) is None
        conn = await asyncpg.connect(clean_squad_messages)
        try:
            status = await conn.fetchval(
                f"""SELECT delivery_status
                      FROM "{_schema()}"."squad_message_recipients"
                     WHERE to_agent_id = 'agent-b'"""
            )
        finally:
            await conn.close()
        assert status == "dead"
    finally:
        await bus.close()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_receive_timeout(bus_factory) -> None:  # type: ignore[no-untyped-def]
    bus = bus_factory()
    msg = await bus.receive("nobody-home", timeout=0.5)
    assert msg is None


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_inbox_full_backpressure(clean_squad_messages: str) -> None:
    bus = PostgresMessageBus(dsn=clean_squad_messages, schema=_schema(), max_inbox_size=2)
    try:
        await bus.send("a", "victim", "m1")
        await bus.send("a", "victim", "m2")
        result = await bus.send("a", "victim", "m3")
        assert result.startswith("Error")
    finally:
        await bus.close()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_delegate_timeout(bus_factory) -> None:  # type: ignore[no-untyped-def]
    bus = bus_factory()
    request = DelegationRequest(from_agent="a", to_agent="b", task="ignored", timeout=0.5)
    result = await bus.delegate(request)
    assert not result.success
    assert "timeout" in (result.error or "").lower()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_delegate_depth_limit(bus_factory, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("koda.config.INTER_AGENT_MAX_DELEGATION_DEPTH", 2)
    bus = bus_factory()
    request = DelegationRequest(from_agent="a", to_agent="b", task="chain", delegation_depth=2)
    result = await bus.delegate(request)
    assert not result.success
    assert "depth" in (result.error or "").lower()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_resolve_delegation_in_process(bus_factory) -> None:  # type: ignore[no-untyped-def]
    bus = bus_factory()

    async def resolver() -> None:
        msg = await bus.receive("b", timeout=3)
        assert msg is not None
        rid = msg.metadata["request_id"]
        await bus.ack("b", msg.message_id)
        bus.resolve_delegation(
            rid,
            DelegationResult(request_id=rid, from_agent="b", to_agent="a", success=True, result="local-ok"),
        )

    task = asyncio.create_task(resolver())
    result = await bus.delegate(DelegationRequest(from_agent="a", to_agent="b", task="x", timeout=5))
    await task
    assert result.success
    assert result.result == "local-ok"


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_resolve_delegation_across_processes(bus_factory) -> None:  # type: ignore[no-untyped-def]
    caller = bus_factory()
    worker = bus_factory()

    async def resolver() -> None:
        msg = await worker.receive("b", timeout=3)
        assert msg is not None
        rid = msg.metadata["request_id"]
        await worker.ack("b", msg.message_id)
        worker.resolve_delegation(
            rid,
            DelegationResult(request_id=rid, from_agent="b", to_agent="a", success=True, result="remote-ok"),
        )

    task = asyncio.create_task(resolver())
    result = await caller.delegate(DelegationRequest(from_agent="a", to_agent="b", task="x", timeout=5))
    await task
    assert result.success
    assert result.result == "remote-ok"


@pytest.mark.asyncio
async def test_persist_delegation_result_addresses_original_caller(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import AsyncMock

    from koda.agents.postgres_message_bus import PostgresMessageBus

    bus = PostgresMessageBus(dsn="postgresql://example.invalid/koda")
    insert = AsyncMock(return_value="msg-1")
    monkeypatch.setattr(bus, "_ensure_started", AsyncMock())
    monkeypatch.setattr(bus, "_insert", insert)

    await bus._persist_delegation_result(
        "req-1",
        DelegationResult(request_id="req-1", from_agent="worker", to_agent="caller", success=True, result="done"),
    )

    args = insert.await_args.args
    assert args[:4] == ("worker", "caller", "done", "delegation_result")


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_broadcast_skips_sender_and_excluded(bus_factory) -> None:  # type: ignore[no-untyped-def]
    seed = bus_factory()
    # Make three agents observable by inserting any message touching them.
    await seed.send("a", "b", "seed-1")
    await seed.send("c", "d", "seed-2")
    await seed.send("a", "c", "seed-3")
    bus = bus_factory()
    count = await bus.broadcast("a", "ping", exclude={"d"})
    # Known agents: a, b, c, d. Exclude {a (sender), d}. Should reach b and c.
    assert count == 2
