"""Bench: circuit breaker closed-passthrough + open-fail-fast.

Two paths matter:
- closed: every internal_rpc call goes through the breaker even when
  the upstream is healthy. Overhead must stay sub-µs.
- open: when a sidecar is hung, the breaker raises immediately
  instead of waiting on INTERNAL_RPC_DEADLINE_MS=1500. The fail-fast
  latency is what makes the cascading-deadlock fix work."""

from __future__ import annotations

import pytest

from koda.internal_rpc.circuit_breaker import (
    CircuitOpenError,
    get_breaker,
    reset_registry_for_tests,
)

from .conftest import load_baseline, measure_async_ns_per_op


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    reset_registry_for_tests()


@pytest.mark.asyncio
async def test_breaker_closed_passthrough_within_baseline() -> None:
    breaker = get_breaker("bench_closed_pass", failure_threshold=100)

    async def _ok() -> int:
        return 1

    async def _call() -> None:
        await breaker.run(_ok)

    measured = await measure_async_ns_per_op(_call, iters=10_000)
    baseline = load_baseline("circuit_breaker_closed")
    assert measured < baseline["max_ns"], (
        f"breaker closed-passthrough regressed: {measured:.0f}ns/op > {baseline['max_ns']}ns/op. "
        f"Common cause: lock contention, or new bookkeeping on every call."
    )


@pytest.mark.asyncio
async def test_breaker_open_fail_fast_within_baseline() -> None:
    breaker = get_breaker("bench_open_ff", failure_threshold=1, open_seconds=300)

    async def _fail() -> None:
        raise RuntimeError("upstream hung")

    # Trip breaker open.
    with pytest.raises(RuntimeError):
        await breaker.run(_fail)

    import contextlib

    async def _call() -> None:
        with contextlib.suppress(CircuitOpenError):
            await breaker.run(_fail)

    measured = await measure_async_ns_per_op(_call, iters=10_000)
    baseline = load_baseline("circuit_breaker_open")
    assert measured < baseline["max_ns"], (
        f"breaker open fail-fast regressed: {measured:.0f}ns/op > {baseline['max_ns']}ns/op. "
        f"This is the headline guarantee against P0-3 cascading deadlocks."
    )
