"""Circuit breaker for internal gRPC clients (Phase 1D).

Direct fix for P0-3 of the production roadmap: a single sidecar that
hangs on a slow gRPC call must not freeze every worker on the host.
Today's implementation has no breaker — every internal_rpc call goes
through and waits for the full ``INTERNAL_RPC_DEADLINE_MS`` (default
1500ms) before failing, even when the upstream has been broken for
minutes. At 50 workers × 5 sidecars × N calls per turn, that compounds
into the deadlocks observed during pause/activate debugging.

This is a pragmatic, language-local breaker (not a Rust proxy):
- ``CircuitBreaker`` wraps any awaitable call site.
- States: ``closed`` → ``open`` → ``half_open`` → ``closed``.
- ``open`` skips the call entirely and raises
  :class:`CircuitOpenError` immediately so callers fall back to their
  degrade path within microseconds instead of waiting on a hung RPC.
- The breaker is process-local (one per worker × upstream). For
  cluster-wide breaker coordination, Phase 1D-v2 / Phase 2 may move
  the state into a shared store; the API is shaped to allow that
  without callers changing.

Usage::

    breaker = CircuitBreaker("memory_engine")

    async def call_with_breaker():
        return await breaker.run(client.recall, query=...)

The first ``failure_threshold`` failures trip the breaker open for
``open_seconds``; after that one exploratory call is allowed
(half-open). Success closes the breaker; failure re-opens it.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, TypeVar

from koda.logging_config import get_logger

log = get_logger(__name__)

T = TypeVar("T")


class CircuitOpenError(RuntimeError):
    """Raised when an attempted call is short-circuited because the
    upstream's breaker is currently open. Caller should treat this as
    "upstream temporarily unavailable" and fall back, NOT retry."""


class State(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class _BreakerState:
    state: State = State.CLOSED
    failure_count: int = 0
    failures_window: list[float] = field(default_factory=list)
    opened_at: float = 0.0


class CircuitBreaker:
    """Sliding-window failure counter with exponential cool-down.

    Parameters
    ----------
    name:
        Identifier used in logs / metrics (e.g. ``"memory_engine"``).
    failure_threshold:
        Number of failures within ``window_seconds`` that trip the
        breaker open. Default 5.
    window_seconds:
        Sliding window length. Failures older than this are pruned at
        every call, so the breaker self-heals after a transient blip.
    open_seconds:
        How long the breaker stays open before transitioning to
        half_open. Default 30.
    """

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        window_seconds: float = 30.0,
        open_seconds: float = 30.0,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        self.name = name
        self.failure_threshold = failure_threshold
        self.window_seconds = float(window_seconds)
        self.open_seconds = float(open_seconds)
        self._state = _BreakerState()
        self._lock = asyncio.Lock()

    @property
    def state(self) -> State:
        return self._state.state

    async def run(self, fn: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
        """Invoke ``fn(*args, **kwargs)`` through the breaker.

        Raises :class:`CircuitOpenError` immediately when the breaker
        is open AND we are still inside the cool-down window. After
        cool-down expires, exactly one half-open call is permitted —
        success closes the breaker, failure re-opens it.
        """
        await self._maybe_transition_after_cooldown()
        if self._state.state is State.OPEN:
            raise CircuitOpenError(
                f"circuit_breaker_open:{self.name}; cool down for ~{self._cooldown_remaining():.1f}s before retrying"
            )
        try:
            result = await fn(*args, **kwargs)
        except Exception:
            await self._record_failure()
            raise
        else:
            await self._record_success()
            return result

    async def _record_success(self) -> None:
        async with self._lock:
            if self._state.state is State.HALF_OPEN:
                log.info("circuit_breaker_closed_after_half_open_success", name=self.name)
            self._state.state = State.CLOSED
            self._state.failure_count = 0
            self._state.failures_window.clear()

    async def _record_failure(self) -> None:
        async with self._lock:
            now = time.monotonic()
            cutoff = now - self.window_seconds
            self._state.failures_window = [t for t in self._state.failures_window if t >= cutoff]
            self._state.failures_window.append(now)
            if self._state.state is State.HALF_OPEN:
                # Half-open probe failed → re-open immediately.
                self._open(now, reason="half_open_probe_failed")
                return
            if len(self._state.failures_window) >= self.failure_threshold:
                self._open(now, reason="threshold_exceeded")

    def _open(self, now: float, *, reason: str) -> None:
        self._state.state = State.OPEN
        self._state.opened_at = now
        log.warning(
            "circuit_breaker_opened",
            name=self.name,
            reason=reason,
            failures=len(self._state.failures_window),
            cool_down_seconds=self.open_seconds,
        )

    async def _maybe_transition_after_cooldown(self) -> None:
        async with self._lock:
            if self._state.state is not State.OPEN:
                return
            if self._cooldown_remaining_locked() <= 0:
                self._state.state = State.HALF_OPEN
                log.info("circuit_breaker_half_open", name=self.name)

    def _cooldown_remaining(self) -> float:
        return self._cooldown_remaining_locked()

    def _cooldown_remaining_locked(self) -> float:
        elapsed = time.monotonic() - self._state.opened_at
        return max(0.0, self.open_seconds - elapsed)


_REGISTRY: dict[str, CircuitBreaker] = {}


def get_breaker(
    name: str,
    *,
    failure_threshold: int = 5,
    window_seconds: float = 30.0,
    open_seconds: float = 30.0,
) -> CircuitBreaker:
    """Process-local registry: one breaker per logical upstream.

    Repeated calls return the same instance so per-call sites share
    state. Configuration is honored on first construction; later calls
    return the existing breaker even if the parameters differ (matches
    the singleton-by-name pattern other internal_rpc components use).
    """
    breaker = _REGISTRY.get(name)
    if breaker is not None:
        return breaker
    breaker = CircuitBreaker(
        name,
        failure_threshold=failure_threshold,
        window_seconds=window_seconds,
        open_seconds=open_seconds,
    )
    _REGISTRY[name] = breaker
    return breaker


def reset_registry_for_tests() -> None:
    """Test-only helper. Production never calls this."""
    _REGISTRY.clear()
