"""Phase A.5 — heartbeat runs as an independent asyncio task.

Before this change ``cluster.heartbeat()`` was called inside
``_reconcile_once``. A reconcile cycle that took longer than
``KODA_CLUSTER_HEARTBEAT_STALE_SECONDS`` (e.g. because spawning a new
worker took 30s for a heavy provider auth probe) would let a sibling
supervisor steal the claims of an otherwise-healthy process. The test
asserts that:

1. The supervisor builds a separate ``_heartbeat_task`` field.
2. The heartbeat-loop interval is bounded (≥ 2s, ≤ stale_seconds/3
   ≈ 10s with the default 30s) so the heartbeat fires at least 3x
   per stale window.
3. The reconcile path no longer refreshes claims itself — ownership
   refresh is exclusively the heartbeat-loop's responsibility.
4. Heartbeat task is cancelled cleanly on supervisor stop.
"""

from __future__ import annotations

from pathlib import Path

from koda.control_plane import supervisor as supervisor_mod


def _read_source() -> str:
    return Path("koda/control_plane/supervisor.py").read_text(encoding="utf-8")


def test_supervisor_has_heartbeat_task_field() -> None:
    src = _read_source()
    assert "self._heartbeat_task" in src, (
        "Supervisor must hold a separate _heartbeat_task field; without it heartbeat is coupled to reconcile cadence."
    )


def test_heartbeat_loop_method_exists() -> None:
    assert hasattr(supervisor_mod.ControlPlaneSupervisor, "_heartbeat_loop"), (
        "ControlPlaneSupervisor._heartbeat_loop must be defined as the target of the heartbeat task."
    )


def test_heartbeat_loop_uses_bounded_interval() -> None:
    src = _read_source()
    # The interval is computed as max(2.0, stale_seconds / 3) so a
    # custom stale-seconds (≥ 6) still gives 3x the heartbeat
    # frequency relative to the staleness window.
    assert "max(2.0, float(self._cluster.config.heartbeat_stale_seconds) / 3.0)" in src or (
        "max(2.0," in src and "heartbeat_stale_seconds" in src
    )


def test_reconcile_does_not_refresh_claims() -> None:
    """Phase A.5 contract — heartbeat is the ONLY place that calls
    ``self._cluster.heartbeat()``. The reconcile path may call
    ``claim_agents`` (to take ownership of new agents) but must NOT
    refresh existing claims."""
    src = _read_source()
    # Find the _reconcile_once body and assert no heartbeat call.
    reconcile_start = src.index("async def _reconcile_once(")
    next_def = src.index("async def ", reconcile_start + 1)
    reconcile_body = src[reconcile_start:next_def]
    assert "self._cluster.heartbeat(" not in reconcile_body, (
        "_reconcile_once must NOT call cluster.heartbeat — that's the heartbeat task's job (Phase A.5)."
    )


def test_supervisor_start_spawns_heartbeat_task_when_clustered() -> None:
    src = _read_source()
    start_idx = src.index("async def start(")
    next_def = src.index("async def ", start_idx + 1)
    start_body = src[start_idx:next_def]
    assert "self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())" in start_body
    # Must be guarded by cluster mode so single-host deploys don't
    # spawn a no-op task.
    assert "if self._cluster.config.enabled:" in start_body


def test_supervisor_stop_cancels_heartbeat_task() -> None:
    src = _read_source()
    stop_idx = src.index("async def stop(")
    next_def = src.index("async def ", stop_idx + 1)
    stop_body = src[stop_idx:next_def]
    assert "self._heartbeat_task" in stop_body
    assert "self._heartbeat_task.cancel()" in stop_body
