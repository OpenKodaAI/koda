"""Circuit-breaker contract for internal_rpc.

A hung sidecar must not freeze every worker.
The breaker:

1. Stays closed under success and below the failure threshold.
2. Trips open after ``failure_threshold`` failures inside
   ``window_seconds``.
3. While open, ``run`` raises :class:`CircuitOpenError` immediately
   (no waiting on the hung upstream).
4. After ``open_seconds``, transitions to half_open. One probe call
   is allowed: success → closed; failure → re-open.
5. Failures older than the window are pruned so a transient blip does
   not poison the breaker forever.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from koda.internal_rpc.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    State,
    get_breaker,
    reset_registry_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    reset_registry_for_tests()


async def _ok() -> str:
    return "ok"


async def _boom() -> Any:
    raise RuntimeError("upstream down")


@pytest.mark.asyncio
async def test_closed_breaker_passes_through_calls() -> None:
    breaker = CircuitBreaker("svc", failure_threshold=3)
    assert await breaker.run(_ok) == "ok"
    assert breaker.state is State.CLOSED


@pytest.mark.asyncio
async def test_threshold_failures_open_the_breaker() -> None:
    breaker = CircuitBreaker("svc", failure_threshold=3, window_seconds=10)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            await breaker.run(_boom)
    assert breaker.state is State.CLOSED
    with pytest.raises(RuntimeError):
        await breaker.run(_boom)
    # 3 failures inside the window → breaker opens.
    assert breaker.state is State.OPEN


@pytest.mark.asyncio
async def test_open_breaker_short_circuits_without_invoking_callable() -> None:
    breaker = CircuitBreaker("svc", failure_threshold=1, open_seconds=60)
    with pytest.raises(RuntimeError):
        await breaker.run(_boom)
    assert breaker.state is State.OPEN

    invocations = 0

    async def _spy() -> str:
        nonlocal invocations
        invocations += 1
        return "should-not-be-called"

    with pytest.raises(CircuitOpenError):
        await breaker.run(_spy)
    assert invocations == 0


@pytest.mark.asyncio
async def test_cooldown_transitions_to_half_open_then_closes_on_success() -> None:
    breaker = CircuitBreaker("svc", failure_threshold=1, open_seconds=0.05)
    with pytest.raises(RuntimeError):
        await breaker.run(_boom)
    assert breaker.state is State.OPEN
    await asyncio.sleep(0.07)
    # Next call transitions to half_open and probes.
    assert await breaker.run(_ok) == "ok"
    assert breaker.state is State.CLOSED


@pytest.mark.asyncio
async def test_half_open_probe_failure_reopens_immediately() -> None:
    breaker = CircuitBreaker("svc", failure_threshold=1, open_seconds=0.05)
    with pytest.raises(RuntimeError):
        await breaker.run(_boom)
    await asyncio.sleep(0.07)
    with pytest.raises(RuntimeError):
        await breaker.run(_boom)
    assert breaker.state is State.OPEN


@pytest.mark.asyncio
async def test_failures_outside_window_do_not_count() -> None:
    breaker = CircuitBreaker("svc", failure_threshold=3, window_seconds=0.05)
    with pytest.raises(RuntimeError):
        await breaker.run(_boom)
    with pytest.raises(RuntimeError):
        await breaker.run(_boom)
    # Wait long enough that earlier failures fall out of the window.
    await asyncio.sleep(0.07)
    with pytest.raises(RuntimeError):
        await breaker.run(_boom)
    # Should still be closed because the window now holds only 1 failure.
    assert breaker.state is State.CLOSED


async def _own_timeout() -> Any:
    raise TimeoutError("the command ran out its own budget")


def _is_own_timeout(exc: Exception) -> bool:
    return isinstance(exc, TimeoutError)


@pytest.mark.asyncio
async def test_expected_errors_neither_open_nor_close_the_breaker() -> None:
    breaker = CircuitBreaker("svc", failure_threshold=2, window_seconds=10)
    for _ in range(5):
        with pytest.raises(TimeoutError):
            await breaker.run_allowing(_is_own_timeout, _own_timeout)
    assert breaker.state is State.CLOSED

    # One upstream failure, then expected errors: they do not clear that failure either.
    with pytest.raises(RuntimeError):
        await breaker.run_allowing(_is_own_timeout, _boom)
    with pytest.raises(TimeoutError):
        await breaker.run_allowing(_is_own_timeout, _own_timeout)
    assert breaker.state is State.CLOSED
    with pytest.raises(RuntimeError):
        await breaker.run_allowing(_is_own_timeout, _boom)
    assert breaker.state is State.OPEN

    # While open, run_allowing short-circuits like run.
    with pytest.raises(CircuitOpenError):
        await breaker.run_allowing(_is_own_timeout, _own_timeout)


@pytest.mark.asyncio
async def test_run_allowing_passes_arguments_and_records_success() -> None:
    breaker = CircuitBreaker("svc", failure_threshold=2, window_seconds=10)
    with pytest.raises(RuntimeError):
        await breaker.run(_boom)

    async def _echo(value: str, *, suffix: str) -> str:
        return value + suffix

    assert await breaker.run_allowing(_is_own_timeout, _echo, "o", suffix="k") == "ok"
    # The success cleared the earlier failure, so one more failure does not open the breaker.
    with pytest.raises(RuntimeError):
        await breaker.run(_boom)
    assert breaker.state is State.CLOSED


def test_get_breaker_returns_same_instance_per_name() -> None:
    a = get_breaker("svc")
    b = get_breaker("svc")
    c = get_breaker("other")
    assert a is b
    assert a is not c


def test_failure_threshold_must_be_positive() -> None:
    with pytest.raises(ValueError):
        CircuitBreaker("svc", failure_threshold=0)
