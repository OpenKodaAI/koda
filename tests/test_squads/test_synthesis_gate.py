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


def _handoff(status: str = "requested", destinations: tuple[str, ...] = ("FE", "QA")) -> dict[str, object]:
    return {"payload": {"handoff_id": "handoff-1", "status": status, "destination_agent_ids": list(destinations)}}


def test_handoff_completes_once_every_destination_has_a_task_result() -> None:
    partial = evaluate_synthesis_readiness(
        handoff_events=[_handoff()],
        result_messages=[{"type": "task_result", "id": "msg-1", "from": "FE"}],
    )
    assert partial.ready is False
    assert partial.blockers == [
        {"kind": "handoff_event", "id": "handoff-1", "status": "requested", "reason": "open_handoff"}
    ]

    complete = evaluate_synthesis_readiness(
        handoff_events=[_handoff()],
        result_messages=[
            {"type": "task_result", "id": "msg-1", "from": "FE"},
            {"type": "task_result", "id": "msg-2", "from": "QA"},
        ],
    )
    assert complete.ready is True
    assert {"kind": "handoff_event", "id": "handoff-1", "status": "returned"} in complete.evidence_refs


def test_handoff_completes_from_answered_reply_obligations() -> None:
    result = evaluate_synthesis_readiness(
        handoff_events=[_handoff(destinations=("FE",))],
        reply_obligations=[{"id": 7, "status": "answered", "target_agent_id": "FE"}],
    )
    assert result.ready is True
    assert {"kind": "handoff_event", "id": "handoff-1", "status": "returned"} in result.evidence_refs


def test_handoff_marked_returned_supersedes_the_requested_event() -> None:
    result = evaluate_synthesis_readiness(handoff_events=[_handoff("returned"), _handoff("requested")])
    assert result.ready is True


def test_handoff_with_a_failed_destination_is_failed_and_disclosed() -> None:
    result = evaluate_synthesis_readiness(
        handoff_events=[_handoff()],
        result_messages=[
            {"type": "task_result", "id": "msg-1", "from": "FE", "payload": {"status": "ok"}},
            {"type": "task_result", "id": "msg-2", "from": "QA", "metadata": {"payload": {"status": "failed"}}},
        ],
    )

    # The failure is visible, so synthesis may run, but it must be told QA failed.
    assert result.ready is True
    assert {"kind": "handoff_event", "id": "handoff-1", "status": "failed"} in result.evidence_refs
    assert result.timeout_disclosures == [
        {"kind": "handoff_event", "id": "handoff-1", "status": "failed", "agent_ids": ["QA"]}
    ]


def test_an_answered_reply_obligation_does_not_hide_a_failed_task_result() -> None:
    result = evaluate_synthesis_readiness(
        handoff_events=[_handoff(destinations=("QA",))],
        result_messages=[{"type": "task_result", "id": "msg-2", "from": "QA", "payload": {"status": "failed"}}],
        # Post-processing answers QA's obligation with the failed result too.
        reply_obligations=[{"id": 7, "status": "answered", "target_agent_id": "QA"}],
    )

    assert {"kind": "handoff_event", "id": "handoff-1", "status": "failed"} in result.evidence_refs
    assert result.timeout_disclosures == [
        {"kind": "handoff_event", "id": "handoff-1", "status": "failed", "agent_ids": ["QA"]}
    ]


def test_handoff_with_a_cancelled_destination_is_failed_and_disclosed() -> None:
    # A destination whose run was cancelled, or whose task could not run, did not return.
    result = evaluate_synthesis_readiness(
        handoff_events=[_handoff()],
        result_messages=[
            {"type": "task_result", "id": "msg-1", "from": "FE", "payload": {"status": "ok"}},
            {"type": "task_result", "id": "msg-2", "from": "QA", "metadata": {"payload": {"status": "cancelled"}}},
        ],
    )

    assert {"kind": "handoff_event", "id": "handoff-1", "status": "failed"} in result.evidence_refs
    assert result.timeout_disclosures == [
        {"kind": "handoff_event", "id": "handoff-1", "status": "failed", "agent_ids": ["QA"]}
    ]
