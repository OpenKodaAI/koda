"""Tests for the inter-agent message bus."""

from __future__ import annotations

import asyncio

import pytest

from koda.agents.message_bus import InMemoryMessageBus, get_message_bus
from koda.agents.models import DelegationRequest, DelegationResult


@pytest.fixture
def bus() -> InMemoryMessageBus:
    return InMemoryMessageBus()


@pytest.mark.asyncio
async def test_send_and_receive(bus: InMemoryMessageBus) -> None:
    msg_id = await bus.send("agent-1", "agent-2", "hello")
    assert msg_id.startswith("msg-")
    msg = await bus.receive("agent-2", timeout=1)
    assert msg is not None
    assert msg.from_agent == "agent-1"
    assert msg.content == "hello"
    assert msg.message_type == "text"


@pytest.mark.asyncio
async def test_receive_timeout(bus: InMemoryMessageBus) -> None:
    msg = await bus.receive("agent-1", timeout=0.05)
    assert msg is None


@pytest.mark.asyncio
async def test_inbox_full(bus: InMemoryMessageBus) -> None:
    bus._max_inbox_size = 2
    bus._inboxes["agent-x"] = asyncio.Queue(maxsize=2)
    await bus.send("a", "agent-x", "m1")
    await bus.send("a", "agent-x", "m2")
    result = await bus.send("a", "agent-x", "m3")
    assert result.startswith("Error")


@pytest.mark.asyncio
async def test_broadcast(bus: InMemoryMessageBus) -> None:
    bus._ensure_inbox("agent-1")
    bus._ensure_inbox("agent-2")
    bus._ensure_inbox("agent-3")
    count = await bus.broadcast("agent-1", "update")
    assert count == 2
    m2 = await bus.receive("agent-2", timeout=1)
    m3 = await bus.receive("agent-3", timeout=1)
    assert m2 is not None
    assert m3 is not None
    assert m2.content == "update"


@pytest.mark.asyncio
async def test_broadcast_with_exclude(bus: InMemoryMessageBus) -> None:
    bus._ensure_inbox("agent-1")
    bus._ensure_inbox("agent-2")
    bus._ensure_inbox("agent-3")
    count = await bus.broadcast("agent-1", "update", exclude={"agent-2"})
    assert count == 1


@pytest.mark.asyncio
async def test_list_agents(bus: InMemoryMessageBus) -> None:
    bus._ensure_inbox("a1")
    bus._ensure_inbox("a2")
    agents = bus.list_agents()
    assert len(agents) == 2
    ids = {a["agent_id"] for a in agents}
    assert ids == {"a1", "a2"}


@pytest.mark.asyncio
async def test_message_log(bus: InMemoryMessageBus) -> None:
    await bus.send("a1", "a2", "msg1")
    await bus.send("a2", "a1", "msg2")
    log = bus.get_message_log()
    assert len(log) == 2
    assert log[0]["from"] == "a1"
    assert log[1]["from"] == "a2"

    filtered = bus.get_message_log(agent_id="a1")
    assert len(filtered) == 2  # a1 is sender or receiver in both


@pytest.mark.asyncio
async def test_message_log_limit(bus: InMemoryMessageBus) -> None:
    for i in range(10):
        await bus.send("a", "b", f"msg-{i}")
    log = bus.get_message_log(limit=3)
    assert len(log) == 3


@pytest.mark.asyncio
async def test_message_log_truncation(bus: InMemoryMessageBus) -> None:
    bus._max_log = 5
    for i in range(10):
        await bus.send("a", "b", f"msg-{i}")
    assert len(bus._message_log) == 5


@pytest.mark.asyncio
async def test_delegation_timeout(bus: InMemoryMessageBus) -> None:
    req = DelegationRequest(from_agent="a1", to_agent="a2", task="do stuff", timeout=0.05)
    result = await bus.delegate(req)
    assert not result.success
    assert "timeout" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_delegation_success(bus: InMemoryMessageBus) -> None:
    async def resolver() -> None:
        msg = await bus.receive("a2", timeout=2)
        assert msg is not None
        assert msg.message_type == "delegation_request"
        request_id = msg.metadata["request_id"]
        bus.resolve_delegation(
            request_id,
            DelegationResult(
                request_id=request_id,
                from_agent="a2",
                to_agent="a1",
                success=True,
                result="done!",
            ),
        )

    task = asyncio.create_task(resolver())
    req = DelegationRequest(from_agent="a1", to_agent="a2", task="analyze", timeout=5)
    result = await bus.delegate(req)
    await task
    assert result.success
    assert result.result == "done!"


@pytest.mark.asyncio
async def test_delegation_depth_limit(bus: InMemoryMessageBus, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.config.INTER_AGENT_MAX_DELEGATION_DEPTH", 2)
    req = DelegationRequest(from_agent="a1", to_agent="a2", task="chain", delegation_depth=2)
    result = await bus.delegate(req)
    assert not result.success
    assert "depth" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_delegation_inbox_full(bus: InMemoryMessageBus) -> None:
    bus._max_inbox_size = 1
    bus._inboxes["a2"] = asyncio.Queue(maxsize=1)
    await bus.send("x", "a2", "fill")
    req = DelegationRequest(from_agent="a1", to_agent="a2", task="do", timeout=0.1)
    result = await bus.delegate(req)
    assert not result.success
    assert "inbox full" in (result.error or "").lower()


def test_get_message_bus_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    import koda.agents.message_bus as mb

    monkeypatch.setattr(mb, "_bus", None)
    b1 = get_message_bus()
    b2 = get_message_bus()
    assert b1 is b2
    monkeypatch.setattr(mb, "_bus", None)


def test_inmemory_satisfies_messagebus_protocol() -> None:
    from koda.agents.message_bus_iface import MessageBus

    assert isinstance(InMemoryMessageBus(), MessageBus)


def test_factory_default_returns_inmemory(monkeypatch: pytest.MonkeyPatch) -> None:
    import koda.agents.message_bus as mb

    monkeypatch.setattr(mb, "_bus", None)
    monkeypatch.setattr("koda.config.INTER_AGENT_BUS_BACKEND", "memory")
    assert isinstance(get_message_bus(), InMemoryMessageBus)
    monkeypatch.setattr(mb, "_bus", None)


def test_factory_postgres_without_dsn_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    import koda.agents.message_bus as mb

    monkeypatch.setattr(mb, "_bus", None)
    monkeypatch.setattr("koda.config.INTER_AGENT_BUS_BACKEND", "postgres")
    monkeypatch.setattr("koda.config.POSTGRES_URL", "")
    assert isinstance(get_message_bus(), InMemoryMessageBus)
    monkeypatch.setattr(mb, "_bus", None)


def test_factory_postgres_with_dsn_selects_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    import koda.agents.message_bus as mb
    from koda.agents.postgres_message_bus import PostgresMessageBus

    monkeypatch.setattr(mb, "_bus", None)
    monkeypatch.setattr("koda.config.INTER_AGENT_BUS_BACKEND", "postgres")
    monkeypatch.setattr("koda.config.POSTGRES_URL", "postgresql://stub/db")
    assert isinstance(get_message_bus(), PostgresMessageBus)
    monkeypatch.setattr(mb, "_bus", None)
