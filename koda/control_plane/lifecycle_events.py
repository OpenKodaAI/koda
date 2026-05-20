"""Cross-coroutine wake-up signal for agent lifecycle changes.

The control-plane reconciliation loop (``ControlPlaneSupervisor._reconcile_loop``)
normally waits ``CONTROL_PLANE_POLL_INTERVAL_SECONDS`` between iterations.
That latency is acceptable for organic drift but unacceptable when the
operator clicks Pause / Activate and expects the runtime to flip "no exato
momento". This module exposes a singleton :class:`asyncio.Event` that the
manager fires from ``pause_agent`` / ``activate_agent``; the supervisor
waits on it (with a timeout that preserves the periodic poll cadence)
and reconciles immediately when set.

Why a module-level singleton instead of an attribute on the supervisor?
Manager and supervisor live in the same process / event loop but are not
mutually aware (supervisor owns the manager, never the other way around).
A single module-level event keeps both sides loosely coupled — the
manager can fire-and-forget without holding a reference to the supervisor,
and tests / scripts that spin up only a manager (no supervisor) never
allocate the event because it is created lazily on first ``set()``.
"""

from __future__ import annotations

import asyncio
import contextlib

from koda.logging_config import get_logger

log = get_logger(__name__)

_lifecycle_event: asyncio.Event | None = None


def _ensure_event() -> asyncio.Event | None:
    """Lazily allocate the event when an event loop is available."""
    global _lifecycle_event
    if _lifecycle_event is not None:
        return _lifecycle_event
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return None
    _lifecycle_event = asyncio.Event()
    return _lifecycle_event


def get_lifecycle_event() -> asyncio.Event | None:
    """Return the wake-up event used by the supervisor reconcile loop."""
    return _ensure_event()


def notify_lifecycle_change(reason: str = "") -> None:
    """Fire-and-forget wake-up for the supervisor reconcile loop.

    Safe to call from synchronous code paths inside an aiohttp request
    handler — the manager itself runs synchronously inside async handlers.
    Silently no-ops when there is no event loop or no supervisor listening
    (e.g. in unit tests that exercise the manager in isolation).
    """
    event = _ensure_event()
    if event is None:
        return
    try:
        event.set()
    except RuntimeError as exc:
        # Event loop closed while we were trying to wake it — never raise
        # back into the operator's request, the next reconcile poll will
        # observe the change anyway.
        log.debug("lifecycle_event_set_failed", reason=reason, error=str(exc))


def consume_lifecycle_signal() -> None:
    """Clear the event after the supervisor processes a reconcile cycle."""
    event = _ensure_event()
    if event is None:
        return
    with contextlib.suppress(RuntimeError):
        event.clear()
