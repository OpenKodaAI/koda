"""Circuit breakers for external dependencies.

Uses pybreaker with a Prometheus listener to track state changes
and emit audit events on circuit open/close.

Integration pattern for services that return error strings (no exceptions):
    Use `check_breaker()` before calls and `record_outcome()` after.

Integration pattern for services that raise exceptions:
    Use the breaker directly via `breaker.call_async(func, *args)`.
"""

import contextlib
from collections.abc import Callable
from typing import Any

try:
    import pybreaker
except ModuleNotFoundError:  # pragma: no cover - exercised in lean test envs

    class _FallbackState:
        def __init__(self, name: str):
            self.name = name

    class _FallbackListener:
        def state_change(self, cb: Any, old_state: Any, new_state: Any) -> None:
            return

    class _FallbackCircuitBreaker:
        def __init__(self, fail_max: int, reset_timeout: int, name: str, listeners: list[Any] | None = None):
            self.fail_max = fail_max
            self.reset_timeout = reset_timeout
            self.name = name
            self.listeners = listeners or []
            self.current_state = _FallbackState("closed")

        def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

    class _PyBreakerModule:
        CircuitBreaker = _FallbackCircuitBreaker
        CircuitBreakerListener = _FallbackListener

    pybreaker = _PyBreakerModule()  # type: ignore[assignment]

from koda.config import AGENT_ID
from koda.logging_config import get_logger

log = get_logger(__name__)
_agent_id_label = AGENT_ID or "default"


class _MetricsListener(pybreaker.CircuitBreakerListener):
    """Update Prometheus gauge and emit audit on circuit state changes."""

    def state_change(self, cb: pybreaker.CircuitBreaker, old_state: Any, new_state: Any) -> None:
        from koda.services.metrics import CIRCUIT_BREAKER_STATE

        state_map = {"closed": 0, "half-open": 1, "open": 2}
        val = state_map.get(str(new_state.name).lower(), -1)
        CIRCUIT_BREAKER_STATE.labels(agent_id=_agent_id_label, dependency=cb.name).set(val)

        log.warning(
            "circuit_breaker_state_change",
            dependency=cb.name,
            old_state=str(old_state.name) if old_state else "unknown",
            new_state=str(new_state.name) if new_state else "unknown",
        )

        from koda.services.audit import emit_task_lifecycle

        event_type = "system.circuit_opened" if val == 2 else "system.circuit_closed"
        emit_task_lifecycle(
            event_type,
            dependency=cb.name,
            old_state=str(old_state.name) if old_state else "unknown",
            new_state=str(new_state.name) if new_state else "unknown",
        )


_listener = _MetricsListener()

# --- Circuit breaker instances per dependency ---

claude_cli_breaker = pybreaker.CircuitBreaker(
    fail_max=5,
    reset_timeout=60,
    name="claude_cli",
    listeners=[_listener],
)

codex_cli_breaker = pybreaker.CircuitBreaker(
    fail_max=5,
    reset_timeout=60,
    name="codex_cli",
    listeners=[_listener],
)

telegram_api_breaker = pybreaker.CircuitBreaker(
    fail_max=10,
    reset_timeout=30,
    name="telegram_api",
    listeners=[_listener],
)

jira_breaker = pybreaker.CircuitBreaker(
    fail_max=3,
    reset_timeout=120,
    name="jira",
    listeners=[_listener],
)

confluence_breaker = pybreaker.CircuitBreaker(
    fail_max=3,
    reset_timeout=120,
    name="confluence",
    listeners=[_listener],
)

postgres_breaker = pybreaker.CircuitBreaker(
    fail_max=5,
    reset_timeout=60,
    name="postgres",
    listeners=[_listener],
)

browser_breaker = pybreaker.CircuitBreaker(
    fail_max=3,
    reset_timeout=180,
    name="browser",
    listeners=[_listener],
)

http_external_breaker = pybreaker.CircuitBreaker(
    fail_max=5,
    reset_timeout=60,
    name="http_external",
    listeners=[_listener],
)

memory_vector_breaker = pybreaker.CircuitBreaker(
    fail_max=5,
    reset_timeout=120,
    name="memory_vector",
    listeners=[_listener],
)

elevenlabs_breaker = pybreaker.CircuitBreaker(
    fail_max=3,
    reset_timeout=120,
    name="elevenlabs",
    listeners=[_listener],
)

scheduler_dispatcher_breaker = pybreaker.CircuitBreaker(
    fail_max=5,
    reset_timeout=60,
    name="scheduler_dispatcher",
    listeners=[_listener],
)

# Convenient registry for status reporting
ALL_BREAKERS: dict[str, pybreaker.CircuitBreaker] = {
    "claude_cli": claude_cli_breaker,
    "codex_cli": codex_cli_breaker,
    "telegram_api": telegram_api_breaker,
    "jira": jira_breaker,
    "confluence": confluence_breaker,
    "postgres": postgres_breaker,
    "browser": browser_breaker,
    "http_external": http_external_breaker,
    "memory_vector": memory_vector_breaker,
    "elevenlabs": elevenlabs_breaker,
    "scheduler_dispatcher": scheduler_dispatcher_breaker,
}


def get_breaker_states() -> dict[str, str]:
    """Get current state of all circuit breakers."""
    return {name: str(cb.current_state) for name, cb in ALL_BREAKERS.items()}


def init_breaker_metrics() -> None:
    """Initialize circuit breaker state gauges to 0 (closed) for all breakers.

    Call at startup so Prometheus dashboards show all breakers from the start.
    """
    from koda.services.metrics import CIRCUIT_BREAKER_STATE

    for name in ALL_BREAKERS:
        CIRCUIT_BREAKER_STATE.labels(agent_id=_agent_id_label, dependency=name).set(0)


class CircuitOpenError(Exception):
    """Raised when a circuit breaker is open and the call is rejected."""

    def __init__(self, dependency: str):
        self.dependency = dependency
        super().__init__(f"{dependency} circuit breaker is open")


def check_breaker(breaker: pybreaker.CircuitBreaker) -> str | None:
    """Check if a breaker is open. Returns error message or None if OK."""
    if str(breaker.current_state) == "open":
        return f"{breaker.name} temporarily unavailable (circuit breaker open)."
    return None


def record_success(breaker: pybreaker.CircuitBreaker) -> None:
    """Record a successful call for the breaker (dummy no-op call).

    Note: Has no effect when the breaker is open — open state rejects all calls
    until reset_timeout expires, regardless of success signals.
    """
    with contextlib.suppress(Exception):
        breaker.call(lambda: None)


def record_failure(breaker: pybreaker.CircuitBreaker) -> None:
    """Record a failed call for the breaker."""
    with contextlib.suppress(Exception):
        breaker.call(_always_fail)


def _always_fail() -> None:
    raise RuntimeError("recorded failure")
