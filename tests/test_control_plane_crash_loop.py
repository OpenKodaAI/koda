"""Crash-loop detection emits a structured audit row exactly once per episode.

Before: when a worker crash-looped (e.g., the missing migration that broke
pause/activate), the supervisor silently spawned a fresh process every
reconcile. The operator only noticed because messages stopped flowing.

After: the supervisor counts crashes in a sliding window; when it crosses
the threshold it appends a single ``control_plane.worker_crash_loop`` row
to ``audit_events`` with the crash count, window length, and last exit
code. Subsequent crashes inside the same episode do not re-alert. Once
the window cools off without new crashes, the next loop alerts again.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from koda.control_plane import supervisor as supervisor_mod
from koda.control_plane.supervisor import ControlPlaneSupervisor


def _make_supervisor() -> ControlPlaneSupervisor:
    with patch("koda.control_plane.supervisor.get_control_plane_manager", return_value=object()):
        return ControlPlaneSupervisor()


def _capture_audit_calls() -> tuple[list[dict[str, Any]], Any]:
    captured: list[dict[str, Any]] = []

    def _record(agent_id: str, *, event_type: str, details: dict[str, Any] | None = None, **_kw: Any) -> None:
        captured.append({"agent_id": agent_id, "event_type": event_type, "details": details or {}})

    return captured, _record


def test_under_threshold_no_audit_emit() -> None:
    supervisor = _make_supervisor()
    captured, fake_record = _capture_audit_calls()
    with patch("koda.control_plane.audit.record_audit_event", fake_record):
        for _ in range(supervisor_mod._CRASH_LOOP_THRESHOLD - 1):
            supervisor._record_worker_crash("AGENT_FLAKY", exit_code=1)
    assert captured == []
    assert "AGENT_FLAKY" not in supervisor._crash_loop_alerted


def test_threshold_emits_single_audit_event() -> None:
    supervisor = _make_supervisor()
    captured, fake_record = _capture_audit_calls()
    with patch("koda.control_plane.audit.record_audit_event", fake_record):
        for _ in range(supervisor_mod._CRASH_LOOP_THRESHOLD):
            supervisor._record_worker_crash("AGENT_BROKEN", exit_code=137)

    assert len(captured) == 1
    event = captured[0]
    assert event["agent_id"] == "AGENT_BROKEN"
    assert event["event_type"] == "control_plane.worker_crash_loop"
    assert event["details"]["crashes"] == supervisor_mod._CRASH_LOOP_THRESHOLD
    assert event["details"]["threshold"] == supervisor_mod._CRASH_LOOP_THRESHOLD
    assert event["details"]["last_exit_code"] == 137
    assert event["details"]["window_seconds"] == supervisor_mod._CRASH_LOOP_WINDOW_SECONDS
    assert "AGENT_BROKEN" in supervisor._crash_loop_alerted


def test_repeated_crashes_inside_window_emit_only_once() -> None:
    """The audit row should not repeat for every reconcile while the loop
    persists — one row per episode is the contract."""
    supervisor = _make_supervisor()
    captured, fake_record = _capture_audit_calls()
    with patch("koda.control_plane.audit.record_audit_event", fake_record):
        for _ in range(supervisor_mod._CRASH_LOOP_THRESHOLD + 8):
            supervisor._record_worker_crash("AGENT_STORM", exit_code=1)

    assert len(captured) == 1


def test_window_lapse_re_arms_alerting() -> None:
    """When the window slides past the previous crashes, the alerted flag
    clears and a fresh crash-loop episode emits a fresh audit row."""
    supervisor = _make_supervisor()
    captured, fake_record = _capture_audit_calls()
    with (
        patch("koda.control_plane.audit.record_audit_event", fake_record),
        patch.object(supervisor_mod, "_CRASH_LOOP_WINDOW_SECONDS", 0.05),
        patch.object(supervisor_mod, "_CRASH_LOOP_THRESHOLD", 3),
    ):
        # First episode: cross the threshold -> one alert.
        for _ in range(3):
            supervisor._record_worker_crash("AGENT_REARM", exit_code=1)
        assert len(captured) == 1

        # Sleep past the window so the prior crashes are pruned. monotonic()
        # only moves forward, so a real wall-clock sleep is the cleanest way
        # to advance it without monkey-patching time.
        import time as _time

        _time.sleep(0.1)

        # Second episode: cross again -> second alert.
        for _ in range(3):
            supervisor._record_worker_crash("AGENT_REARM", exit_code=1)

    assert len(captured) == 2


def test_stop_worker_clears_crash_state() -> None:
    """When the operator pauses or stops an agent, supervisor must wipe the
    crash bookkeeping so a future activate starts fresh."""
    supervisor = _make_supervisor()
    captured, fake_record = _capture_audit_calls()
    with patch("koda.control_plane.audit.record_audit_event", fake_record):
        for _ in range(supervisor_mod._CRASH_LOOP_THRESHOLD):
            supervisor._record_worker_crash("AGENT_PAUSED", exit_code=2)
        assert "AGENT_PAUSED" in supervisor._crash_loop_alerted

    # _stop_worker normally interacts with the runtime; we just want the
    # bookkeeping reset, so call it with no live state in the dict.
    import asyncio

    asyncio.run(supervisor._stop_worker("AGENT_PAUSED"))

    assert "AGENT_PAUSED" not in supervisor._crash_loop_alerted
    assert "AGENT_PAUSED" not in supervisor._crash_history
