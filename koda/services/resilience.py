"""Circuit breakers for external dependencies.

Uses pybreaker with a Prometheus listener to track state changes
and emit audit events when a circuit opens, half-opens or closes.

Integration pattern (every call site in this codebase):
    Call `check_breaker()` before the guarded call and return early when it
    reports an error. A caller it admits must then report the outcome with
    `record_success()` or `record_failure()`. The one exception today is
    `browser_breaker`: the browser tools only check it and never record an
    outcome, so it never opens.

Recovery contract: once a breaker opens, `check_breaker()` rejects calls until
`reset_timeout` seconds have passed, then moves the breaker to half-open and
admits one caller as the recovery probe. The probe holds the slot for
`reset_timeout` seconds. The probe's `record_success()` closes the breaker;
its `record_failure()` re-opens it for another `reset_timeout`. A probe that
has not reported within `reset_timeout`, whether lost or still running, frees
the slot and the next caller becomes another probe. One lost caller therefore
cannot latch the breaker half-open, but a dependency whose calls outlast
`reset_timeout` (the CLI runners) admits one extra probe per `reset_timeout`
while the first is still running.
"""

import contextlib
import threading
import time
import weakref
from collections.abc import Callable
from dataclasses import dataclass
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

# Audit event per koda_circuit_breaker_state gauge value.
_AUDIT_EVENT_BY_STATE = {
    0: "system.circuit_closed",
    1: "system.circuit_half_open",
    2: "system.circuit_opened",
}


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

        emit_task_lifecycle(
            _AUDIT_EVENT_BY_STATE.get(val, "system.circuit_state_changed"),
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


_STATE_OPEN = "open"
_STATE_HALF_OPEN = "half-open"

# Monotonic clock for open/probe timing. pybreaker only re-evaluates its own
# timeout inside ``breaker.call``, which call sites never reach while
# ``check_breaker`` rejects them, so the timing lives here. Tests replace it.
_clock: Callable[[], float] = time.monotonic


@dataclass
class _RecoveryGate:
    """Timing for one open or half-open episode of a breaker.

    pybreaker creates a new state object on every transition, so ``episode``
    (a weak reference to that object) tells whether this timing still belongs
    to the breaker's current state. ``started_at`` is when the breaker opened
    (open episode) or when the current probe was admitted (half-open episode).
    """

    episode: weakref.ReferenceType[Any]
    started_at: float


_gates: weakref.WeakKeyDictionary[Any, _RecoveryGate] = weakref.WeakKeyDictionary()
_gates_lock = threading.RLock()


def _unavailable(breaker: pybreaker.CircuitBreaker) -> str:
    return f"{breaker.name} temporarily unavailable (circuit breaker open)."


def _current_gate(breaker: pybreaker.CircuitBreaker) -> _RecoveryGate | None:
    gate = _gates.get(breaker)
    if gate is None or gate.episode() is not breaker.state:
        return None  # no timing yet, or left over from an earlier episode
    return gate


def _start_episode(breaker: pybreaker.CircuitBreaker, now: float) -> None:
    _gates[breaker] = _RecoveryGate(episode=weakref.ref(breaker.state), started_at=now)


def check_breaker(breaker: pybreaker.CircuitBreaker) -> str | None:
    """Admit or reject a guarded call. Returns error message or None if OK.

    See the module docstring for the recovery contract. A caller admitted
    here must report the outcome with ``record_success``/``record_failure``.
    """
    with _gates_lock:
        state = str(breaker.current_state)
        if state not in (_STATE_OPEN, _STATE_HALF_OPEN):
            return None
        now = _clock()
        gate = _current_gate(breaker)
        if state == _STATE_OPEN:
            if gate is None:
                # Opened outside record_failure (e.g. breaker.open()): start timing now.
                _start_episode(breaker, now)
                return _unavailable(breaker)
            if now - gate.started_at < breaker.reset_timeout:
                return _unavailable(breaker)
            breaker.half_open()
        elif gate is not None and now - gate.started_at < breaker.reset_timeout:
            return _unavailable(breaker)  # a probe holds the slot
        _start_episode(breaker, now)  # this caller is the probe
        return None


def record_success(breaker: pybreaker.CircuitBreaker) -> None:
    """Record a successful guarded call.

    Closes a half-open breaker. Ignored while the breaker is open: a call
    admitted before the breaker tripped is not a recovery probe.
    """
    with _gates_lock:
        if str(breaker.current_state) == _STATE_OPEN:
            return
        with contextlib.suppress(Exception):
            breaker.call(lambda: None)
        _gates.pop(breaker, None)


def record_failure(breaker: pybreaker.CircuitBreaker) -> None:
    """Record a failed guarded call.

    Counts toward ``fail_max`` when closed and re-opens a half-open breaker.
    Ignored while the breaker is open so stragglers do not extend the window.
    """
    with _gates_lock:
        if str(breaker.current_state) == _STATE_OPEN:
            return
        with contextlib.suppress(Exception):
            breaker.call(_always_fail)
        if str(breaker.current_state) == _STATE_OPEN:
            _start_episode(breaker, _clock())


def _always_fail() -> None:
    raise RuntimeError("recorded failure")
