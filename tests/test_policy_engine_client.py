"""Policy-engine Python contract.

Pins the wrapper semantics queue_manager will rely on:

1. ``check_ingest_or_allow`` falls through to "allow" when the engine
   is disabled or unreachable — the bot-gateway at-least-once delivery
   means a transient outage cannot drop user messages, only skip the
   policy check.
2. ``record_spend_safe`` never raises on the LLM-success path —
   spend-ledger drift is preferable to losing a generated response.
3. The default flag is OFF so single-tenant deployments aren't
   affected by this code landing.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from koda.internal_rpc import policy_engine as pe


class _FakeStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def CheckIngest(self, request: Any) -> Any:
        self.calls.append(("CheckIngest", request))
        return _coro(SimpleNamespace(allowed=True, deny_reason="", retry_after_ms=0))

    def RecordSpend(self, request: Any) -> Any:
        self.calls.append(("RecordSpend", request))
        return _coro(
            SimpleNamespace(
                remaining_budget_usd=42.0,
                warning_threshold_crossed=True,
                hard_stop_threshold_crossed=False,
            )
        )

    def AcquireSlot(self, request: Any) -> Any:
        self.calls.append(("AcquireSlot", request))
        return _coro(SimpleNamespace(acquired=True, slot_token="tok-1", active_holders=1, max_holders=5))

    def ReleaseSlot(self, request: Any) -> Any:
        self.calls.append(("ReleaseSlot", request))
        return _coro(SimpleNamespace(released=True))


async def _coro(value: Any) -> Any:
    return value


def _build_client_with_fake_stub() -> tuple[pe.PolicyEngineClient, _FakeStub]:
    fake_pb2 = SimpleNamespace(
        CheckIngestRequest=lambda **kw: SimpleNamespace(**kw),
        RecordSpendRequest=lambda **kw: SimpleNamespace(**kw),
        AcquireSlotRequest=lambda **kw: SimpleNamespace(**kw),
        ReleaseSlotRequest=lambda **kw: SimpleNamespace(**kw),
    )
    stub = _FakeStub()
    client = pe.PolicyEngineClient(target="127.0.0.1:50067")
    client._channel = object()
    client._pb2 = fake_pb2
    client._stub = stub
    return client, stub


@pytest.mark.asyncio
async def test_check_ingest_returns_typed_decision() -> None:
    client, stub = _build_client_with_fake_stub()
    decision = await client.check_ingest("ws", "AGENT_A", 100)
    assert decision.allowed is True
    assert decision.deny_reason == ""
    assert decision.retry_after_ms == 0
    assert stub.calls[0][0] == "CheckIngest"


@pytest.mark.asyncio
async def test_record_spend_returns_thresholds() -> None:
    client, _ = _build_client_with_fake_stub()
    decision = await client.record_spend("ws", "AGENT_A", 1.5, "openai", "gpt")
    assert decision.warning_threshold_crossed is True
    assert decision.hard_stop_threshold_crossed is False
    assert decision.remaining_budget_usd == 42.0


@pytest.mark.asyncio
async def test_acquire_release_slot_roundtrip() -> None:
    client, _ = _build_client_with_fake_stub()
    lease = await client.acquire_slot("ws", "AGENT_A", 60)
    assert lease.acquired
    assert lease.slot_token == "tok-1"
    released = await client.release_slot("ws", lease.slot_token)
    assert released is True


@pytest.mark.asyncio
async def test_check_ingest_or_allow_short_circuits_when_disabled() -> None:
    """When POLICY_ENGINE_ENABLED is False the helper must NOT touch
    the network — even with a real client, the fallthrough is silent."""
    with patch("koda.config.POLICY_ENGINE_ENABLED", False):
        d = await pe.check_ingest_or_allow(None, agent_id="AGENT_A")
        assert d.allowed is True
        assert d.deny_reason == ""


@pytest.mark.asyncio
async def test_check_ingest_or_allow_falls_through_on_exception() -> None:
    class _ExplodingClient:
        async def check_ingest(self, **_kw: Any) -> Any:
            raise RuntimeError("network blip")

    with patch("koda.config.POLICY_ENGINE_ENABLED", True):
        d = await pe.check_ingest_or_allow(_ExplodingClient(), agent_id="A")
    assert d.allowed is True


@pytest.mark.asyncio
async def test_record_spend_safe_swallows_errors() -> None:
    class _ExplodingClient:
        async def record_spend(self, **_kw: Any) -> Any:
            raise RuntimeError("db down")

    with patch("koda.config.POLICY_ENGINE_ENABLED", True):
        result = await pe.record_spend_safe(_ExplodingClient(), agent_id="A", cost_usd=1.0, provider="p", model="m")
    assert result is None  # no propagation


@pytest.mark.asyncio
async def test_record_spend_safe_skips_zero_cost() -> None:
    class _ShouldNotBeCalled:
        async def record_spend(self, **_kw: Any) -> Any:
            raise AssertionError("must not call gateway for zero cost")

    with patch("koda.config.POLICY_ENGINE_ENABLED", True):
        result = await pe.record_spend_safe(_ShouldNotBeCalled(), agent_id="A", cost_usd=0.0)
    assert result is None


def test_default_flag_is_off() -> None:
    from koda.config import POLICY_ENGINE_ENABLED

    assert POLICY_ENGINE_ENABLED is False
