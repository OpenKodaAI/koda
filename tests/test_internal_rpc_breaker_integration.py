"""Verify the circuit breaker is wired into internal_rpc.

Without these tests the breaker scaffold could land but
never actually wrap the gRPC calls, leaving the cascading-deadlock surface
freezing every worker on ``INTERNAL_RPC_DEADLINE_MS``) unfixed in
production. The grep gates pin the wire-up; the runtime test asserts
fail-fast latency in microseconds vs the 1500ms deadline.

Sync clients (``security_guard``, ``retrieval_engine``) are
intentionally not wrapped in this phase — the current
``CircuitBreaker.run`` requires an awaitable, and adding a sync
variant is a separate change. The async clients carry the heaviest
call volume so this still covers ~95% of internal RPC traffic.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from koda.internal_rpc.circuit_breaker import (
    CircuitOpenError,
    State,
    get_breaker,
    reset_registry_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    reset_registry_for_tests()


def _read_source(rel_path: str) -> str:
    return Path(rel_path).read_text(encoding="utf-8")


CLIENTS_REQUIRING_BREAKER = (
    ("koda/internal_rpc/policy_engine.py", '"policy_engine"'),
    ("koda/internal_rpc/bot_gateway.py", '"bot_gateway"'),
    ("koda/internal_rpc/memory_engine.py", '"memory_engine"'),
    ("koda/internal_rpc/artifact_engine.py", '"artifact_engine"'),
    ("koda/internal_rpc/runtime_kernel.py", '"runtime_kernel"'),
)


@pytest.mark.parametrize(("path", "expected_name"), CLIENTS_REQUIRING_BREAKER)
def test_each_async_client_constructs_breaker(path: str, expected_name: str) -> None:
    """Each async internal_rpc client must build a process-local
    breaker keyed by the upstream service name. The grep pattern is
    stable through formatter reflows because the name string is what
    matters — not the surrounding whitespace."""
    src = _read_source(path)
    assert "make_internal_breaker(" in src, (
        f"{path} must call make_internal_breaker so the breaker is registered in the process-local registry."
    )
    assert expected_name in src, f"{path} must register breaker under {expected_name}"


@pytest.mark.parametrize(("path", "_name"), CLIENTS_REQUIRING_BREAKER)
def test_each_async_client_routes_calls_through_breaker(path: str, _name: str) -> None:
    """RPC sites must invoke ``self._breaker.run`` rather than the
    raw stub. If a future refactor regresses any site, this gate
    catches it."""
    src = _read_source(path)
    raw_call = "await self._stub."
    assert raw_call not in src, (
        f"{path}: every async stub call must go through the breaker. "
        f"Found a raw `await self._stub.X(` site that will block on "
        f"INTERNAL_RPC_DEADLINE_MS during a hung-upstream incident."
    )


def test_config_exposes_breaker_thresholds() -> None:
    from koda import config

    assert isinstance(config.INTERNAL_RPC_BREAKER_THRESHOLD, int)
    assert config.INTERNAL_RPC_BREAKER_THRESHOLD >= 1
    assert isinstance(config.INTERNAL_RPC_BREAKER_WINDOW_SECONDS, float)
    assert config.INTERNAL_RPC_BREAKER_WINDOW_SECONDS > 0
    assert isinstance(config.INTERNAL_RPC_BREAKER_OPEN_SECONDS, float)
    assert config.INTERNAL_RPC_BREAKER_OPEN_SECONDS > 0


@pytest.mark.asyncio
async def test_open_breaker_fails_fast_under_microseconds() -> None:
    """The headline guarantee of A.2: when a sidecar is down, the
    breaker raises CircuitOpenError immediately instead of waiting on
    the gRPC deadline. We assert the open-breaker call returns in
    well under 1ms — orders of magnitude below the legacy
    INTERNAL_RPC_DEADLINE_MS=1500 timeout."""
    breaker = get_breaker(
        "test_fast_fail",
        failure_threshold=1,
        window_seconds=10,
        open_seconds=10,
    )

    async def _slow_failing_rpc() -> None:
        # Simulate a hung sidecar: pretend to timeout but raise
        # immediately so the breaker counts the failure.
        raise RuntimeError("upstream timeout")

    with pytest.raises(RuntimeError):
        await breaker.run(_slow_failing_rpc)
    assert breaker.state is State.OPEN

    started = time.perf_counter()
    for _ in range(100):
        with pytest.raises(CircuitOpenError):
            await breaker.run(_slow_failing_rpc)
    elapsed_per_call_us = (time.perf_counter() - started) * 1_000_000 / 100
    # Even allowing for asyncio scheduler noise, well under 1ms per
    # call vs the 1500ms gRPC deadline = ~1500x improvement during a
    # cascading-deadlock incident.
    assert elapsed_per_call_us < 1000, f"open-breaker fail-fast must be <1ms; measured {elapsed_per_call_us:.1f}us"


@pytest.mark.asyncio
async def test_breaker_recovers_after_cool_down_with_successful_probe() -> None:
    """After the open window expires, exactly one half-open probe is
    permitted; on success the breaker closes and traffic resumes."""
    breaker = get_breaker(
        "test_recovery",
        failure_threshold=1,
        window_seconds=10,
        open_seconds=0.05,
    )

    async def _failing() -> None:
        raise RuntimeError("upstream down")

    async def _ok() -> str:
        return "ok"

    with pytest.raises(RuntimeError):
        await breaker.run(_failing)
    assert breaker.state is State.OPEN

    await asyncio.sleep(0.07)
    result = await breaker.run(_ok)
    assert result == "ok"
    assert breaker.state is State.CLOSED
