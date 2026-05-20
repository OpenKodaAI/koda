from __future__ import annotations

from types import SimpleNamespace

from koda.squads.synthesis_gate import evaluate_synthesis_readiness


def test_synthesis_gate_blocks_open_tasks_obligations_child_runs_and_handoffs() -> None:
    result = evaluate_synthesis_readiness(
        tasks=[SimpleNamespace(id="task-1", status="in_progress")],
        reply_obligations=[{"id": 7, "status": "open"}],
        child_runs=[{"child_run_id": "child-1", "status": "running"}],
        handoff_events=[{"payload": {"handoff_id": "handoff-1", "status": "requested"}}],
    )

    assert result.ready is False
    assert {item["kind"] for item in result.blockers} == {
        "task",
        "reply_obligation",
        "child_run",
        "handoff_event",
    }


def test_synthesis_gate_requires_disclosure_for_terminal_failures() -> None:
    blocked = evaluate_synthesis_readiness(
        tasks=[{"id": "task-1", "status": "failed"}],
        handoff_events=[{"payload": {"handoff_id": "handoff-1", "status": "timed_out"}}],
    )

    assert blocked.ready is False
    assert {item["reason"] for item in blocked.blockers} == {"missing_terminal_disclosure"}

    ready = evaluate_synthesis_readiness(
        tasks=[{"id": "task-1", "status": "failed"}],
        handoff_events=[{"payload": {"handoff_id": "handoff-1", "status": "timed_out"}}],
        declared_timeouts=[
            {"kind": "task", "id": "task-1"},
            {"kind": "handoff_event", "id": "handoff-1"},
        ],
        result_messages=[{"type": "task_result", "id": "msg-9", "from": "QA"}],
    )

    assert ready.ready is True
    assert ready.evidence_refs[-1] == {"kind": "task_result", "id": "msg-9", "agent_id": "QA"}
