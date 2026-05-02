"""Tests for the runtime side of per-task lease orchestration.

Covers the two background coroutines added to ``koda/services/queue_manager.py``:

- ``_task_lease_renewal_loop``: extends the lease at a fixed cadence,
  exits cleanly on the cancel event, and signals lease loss back to the
  worker by setting the cancel event when ``extend_task_lease`` returns
  False (so any subsequent ``update_task_with_lease`` from the worker
  will be a no-op).
- ``_stale_task_lease_janitor``: periodic sweep that calls the reaper and
  emits a ``task.lease_reaped`` audit event for each requeued / failed row.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest


def _patch_lease_intervals(monkeypatch: pytest.MonkeyPatch, *, heartbeat: float = 0.05, janitor: float = 0.05) -> None:
    """Shrink the lease cadence so unit tests don't sleep for production
    intervals (15s / 30s)."""
    from koda.services import queue_manager

    monkeypatch.setattr(queue_manager, "TASK_LEASE_HEARTBEAT_SECONDS", heartbeat)
    monkeypatch.setattr(queue_manager, "TASK_LEASE_DURATION_SECONDS", 5)
    monkeypatch.setattr(queue_manager, "TASK_LEASE_JANITOR_INTERVAL_SECONDS", janitor)


@pytest.mark.asyncio
async def test_renewal_loop_extends_until_cancel(monkeypatch: pytest.MonkeyPatch) -> None:
    """Loop calls extend_task_lease at the heartbeat cadence and exits
    cleanly within one cycle of the cancel event being set."""
    from koda.services import queue_manager

    _patch_lease_intervals(monkeypatch, heartbeat=0.02)
    extends: list[tuple[int, str, int]] = []

    def fake_extend(task_id: int, owner: str, lease_seconds: int) -> bool:
        extends.append((task_id, owner, lease_seconds))
        return True

    monkeypatch.setattr(queue_manager, "extend_task_lease", fake_extend)

    cancel = asyncio.Event()
    loop_task = asyncio.create_task(queue_manager._task_lease_renewal_loop(task_id=1, owner="W", cancel=cancel))
    # Need enough wall time for two heartbeat iterations + to_thread
    # dispatch overhead — the heartbeat sleep alone is 20ms each.
    await asyncio.sleep(0.3)
    assert len(extends) >= 2, "renewal loop must extend repeatedly while running"
    cancel.set()
    await asyncio.wait_for(loop_task, timeout=0.5)


@pytest.mark.asyncio
async def test_renewal_loop_signals_lease_loss(monkeypatch: pytest.MonkeyPatch) -> None:
    """If ``extend_task_lease`` returns False the loop MUST set the cancel
    event so the worker observes the loss at its next checkpoint and any
    subsequent ``update_task_with_lease`` becomes a no-op. Without this
    signal, the worker could happily push a 'completed' update over a
    row the janitor already requeued — that would resurrect orphan tasks
    and break the consistency contract."""
    from koda.services import queue_manager

    _patch_lease_intervals(monkeypatch, heartbeat=0.01)

    def fake_extend(task_id: int, owner: str, lease_seconds: int) -> bool:
        return False

    monkeypatch.setattr(queue_manager, "extend_task_lease", fake_extend)

    cancel = asyncio.Event()
    await asyncio.wait_for(
        queue_manager._task_lease_renewal_loop(task_id=1, owner="W", cancel=cancel),
        timeout=0.5,
    )
    assert cancel.is_set(), "lease loss MUST flip the cancel event"


@pytest.mark.asyncio
async def test_renewal_loop_swallows_transient_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """A transient DB error during extend should NOT take down the loop;
    the next cycle gets another chance. Only an explicit False return
    (lease lost) terminates the loop."""
    from koda.services import queue_manager

    _patch_lease_intervals(monkeypatch, heartbeat=0.01)
    calls: list[int] = []

    def fake_extend(task_id: int, owner: str, lease_seconds: int) -> bool:
        calls.append(task_id)
        if len(calls) == 1:
            raise RuntimeError("transient db error")
        return True

    monkeypatch.setattr(queue_manager, "extend_task_lease", fake_extend)

    cancel = asyncio.Event()
    loop_task = asyncio.create_task(queue_manager._task_lease_renewal_loop(task_id=1, owner="W", cancel=cancel))
    # Two iterations need the heartbeat sleep + the to_thread dispatch
    # latency, so allow enough wall time for both extend calls to land.
    await asyncio.sleep(0.3)
    cancel.set()
    await asyncio.wait_for(loop_task, timeout=0.5)
    assert len(calls) >= 2, "loop must retry after a transient error"


@pytest.mark.asyncio
async def test_janitor_emits_audit_per_reaped_task(monkeypatch: pytest.MonkeyPatch) -> None:
    """The janitor must emit a ``task.lease_reaped`` lifecycle event for
    every reaped row (both buckets) so operators can correlate orb-status
    transitions with the underlying recovery decision."""
    from koda.services import queue_manager

    _patch_lease_intervals(monkeypatch, janitor=5)  # never sleep through a cycle

    reaped_payload = [
        {"id": 11, "user_id": 100, "chat_id": 200, "attempt": 1, "max_attempts": 3, "outcome": "requeued"},
        {"id": 22, "user_id": 101, "chat_id": 201, "attempt": 3, "max_attempts": 3, "outcome": "failed"},
    ]
    call_count = {"n": 0}

    def fake_reap() -> list[dict[str, Any]]:
        call_count["n"] += 1
        # First cycle returns reapings; subsequent cycles return nothing.
        return reaped_payload if call_count["n"] == 1 else []

    monkeypatch.setattr(queue_manager, "reap_expired_task_leases", fake_reap)

    audit_events: list[dict[str, Any]] = []

    def fake_emit(event: str, **fields: Any) -> None:
        audit_events.append({"event": event, **fields})

    # Patch the real audit module's emit so the lazy ``from koda.services
    # import audit`` inside the janitor still resolves to the production
    # module — only the side-effecting call is intercepted.
    from koda.services import audit as audit_module

    monkeypatch.setattr(audit_module, "emit_task_lifecycle", fake_emit)

    # Run a short slice of the janitor — first cycle takes one
    # ``await asyncio.sleep(janitor)``, then reaps.
    monkeypatch.setattr(queue_manager, "TASK_LEASE_JANITOR_INTERVAL_SECONDS", 0.02)
    janitor_task = asyncio.create_task(queue_manager._stale_task_lease_janitor())
    await asyncio.sleep(0.08)
    janitor_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await janitor_task

    events = [e for e in audit_events if e["event"] == "task.lease_reaped"]
    by_id = {e["task_id"]: e for e in events}
    assert by_id[11]["outcome"] == "requeued"
    assert by_id[22]["outcome"] == "failed"
