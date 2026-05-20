"""Pause/activate agent lifecycle emits a structured audit row.

Before: ``pause_agent`` rolled back in-flight queue items by appending
``paused_by_operator`` to ``last_error`` on each row. Activate left no
trace at all. Replay tools and operators had no correlation log to
explain why an agent went paused or when it came back, so support cases
ended at "the queue rolled back, somehow."

After: every pause/activate appends a structured row to ``audit_events``
with the event type, the rolled-back count (pause), and the agent_id in
details_json. Without these tests, a future refactor could quietly drop
the emit and we would lose visibility again.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

from koda.control_plane import manager as manager_mod


class _Recorder:
    """Capture (sql, params) tuples passed to ``execute``."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def __call__(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        self.calls.append((sql, params))
        # The rollback UPDATE returns the number of in-flight items rolled back.
        # Stub it as 3 so the audit details_json carries a non-zero count.
        if "UPDATE runtime_queue_items" in sql:
            return 3
        return 1

    def audit_calls(self) -> list[tuple[str, tuple[Any, ...]]]:
        return [call for call in self.calls if "INSERT INTO audit_events" in call[0]]


def _emit(event_type: str, agent_id: str = "AGENT_ALPHA", **details: Any) -> _Recorder:
    """Drive ``_emit_lifecycle_audit_event`` with a recorder execute()."""
    recorder = _Recorder()
    instance = manager_mod.ControlPlaneManager.__new__(manager_mod.ControlPlaneManager)
    with patch("koda.control_plane.audit.execute", recorder):
        instance._emit_lifecycle_audit_event(agent_id, event_type=event_type, details={"agent_id": agent_id, **details})
    return recorder


def test_emit_writes_paused_event_with_details() -> None:
    recorder = _emit("control_plane.agent_paused", to_status="paused", rolled_back_queue_items=4)
    audit_calls = recorder.audit_calls()
    assert len(audit_calls) == 1
    sql, params = audit_calls[0]
    # agent_id, timestamp, event_type, details_json
    assert params[0] == "AGENT_ALPHA"
    assert params[2] == "control_plane.agent_paused"
    payload = json.loads(params[6])
    assert payload == {
        "agent_id": "AGENT_ALPHA",
        "to_status": "paused",
        "rolled_back_queue_items": 4,
    }


def test_emit_writes_activated_event() -> None:
    recorder = _emit("control_plane.agent_activated", to_status="active")
    audit_calls = recorder.audit_calls()
    assert len(audit_calls) == 1
    _, params = audit_calls[0]
    assert params[2] == "control_plane.agent_activated"
    assert json.loads(params[6]) == {"agent_id": "AGENT_ALPHA", "to_status": "active"}


def test_emit_swallows_failures_so_lifecycle_is_never_blocked() -> None:
    """Audit emit failure must not propagate; the operator's pause/activate
    must succeed even if the audit table is briefly unavailable."""

    def _boom(sql: str, params: tuple[Any, ...] = ()) -> int:
        raise RuntimeError("audit table unavailable")

    instance = manager_mod.ControlPlaneManager.__new__(manager_mod.ControlPlaneManager)
    with patch("koda.control_plane.audit.execute", _boom):
        # Must NOT raise.
        instance._emit_lifecycle_audit_event(
            "AGENT_BETA",
            event_type="control_plane.agent_paused",
            details={"agent_id": "AGENT_BETA"},
        )


def test_emit_skips_blank_agent_id() -> None:
    recorder = _Recorder()
    instance = manager_mod.ControlPlaneManager.__new__(manager_mod.ControlPlaneManager)
    with patch("koda.control_plane.audit.execute", recorder):
        instance._emit_lifecycle_audit_event("", event_type="control_plane.agent_paused", details={})
        instance._emit_lifecycle_audit_event("   ", event_type="control_plane.agent_paused", details={})
    assert recorder.calls == []


def test_pause_agent_emits_audit_with_rolled_back_count() -> None:
    recorder = _Recorder()
    instance = manager_mod.ControlPlaneManager.__new__(manager_mod.ControlPlaneManager)
    with (
        patch.object(manager_mod, "execute", recorder),
        patch("koda.control_plane.audit.execute", recorder),
        patch.object(instance, "update_agent", lambda agent_id, fields: {"id": agent_id, **fields}),
        patch("koda.control_plane.lifecycle_events.notify_lifecycle_change"),
    ):
        result = instance.pause_agent("AGENT_GAMMA")

    assert result["status"] == "paused"
    audit_calls = recorder.audit_calls()
    assert len(audit_calls) == 1
    _, params = audit_calls[0]
    assert params[2] == "control_plane.agent_paused"
    payload = json.loads(params[6])
    assert payload["rolled_back_queue_items"] == 3  # _Recorder stubs this
    assert payload["to_status"] == "paused"
    assert payload["agent_id"] == "AGENT_GAMMA"


def test_activate_agent_emits_audit() -> None:
    recorder = _Recorder()
    instance = manager_mod.ControlPlaneManager.__new__(manager_mod.ControlPlaneManager)
    with (
        patch.object(manager_mod, "execute", recorder),
        patch("koda.control_plane.audit.execute", recorder),
        patch.object(instance, "update_agent", lambda agent_id, fields: {"id": agent_id, **fields}),
        patch("koda.control_plane.lifecycle_events.notify_lifecycle_change"),
    ):
        result = instance.activate_agent("AGENT_DELTA")

    assert result["status"] == "active"
    audit_calls = recorder.audit_calls()
    assert len(audit_calls) == 1
    _, params = audit_calls[0]
    assert params[2] == "control_plane.agent_activated"
    assert json.loads(params[6]) == {"agent_id": "AGENT_DELTA", "to_status": "active"}
