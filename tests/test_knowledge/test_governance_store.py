from unittest.mock import patch

from koda.state.knowledge_governance_store import approve_knowledge_candidate, record_correction_event


def test_approve_knowledge_candidate_blocks_minimum_gate_failures():
    candidate = {
        "id": 11,
        "agent_id": "agent_a",
        "task_kind": "deploy",
        "candidate_type": "success_pattern",
        "summary": "Deploy safely",
        "proposed_runbook": {
            "title": "Deploy safely",
            "summary": "Deploy safely",
            "steps": ["Apply manifests"],
        },
        "source_refs": [],
        "review_status": "pending",
        "project_key": "workspace",
        "environment": "prod",
        "team": "agent_a",
        "diff_summary": "operator request",
    }

    with (
        patch("koda.state.knowledge_governance_store.get_knowledge_candidate", return_value=candidate),
        patch("koda.state.knowledge_governance_store.set_knowledge_candidate_status") as mock_status,
        patch("koda.state.knowledge_governance_store.list_approved_runbooks") as mock_runbooks,
        patch("koda.state.knowledge_governance_store.create_approved_runbook") as mock_create,
    ):
        result = approve_knowledge_candidate(11, reviewer="reviewer:1")

    assert result is None
    mock_runbooks.assert_not_called()
    mock_create.assert_not_called()
    mock_status.assert_called_once()
    assert "promote_blocked_missing_fields" in mock_status.call_args.kwargs["review_note"]


def test_record_correction_event_is_idempotent_for_existing_feedback():
    episode = {
        "id": 21,
        "task_kind": "deploy",
        "project_key": "workspace",
        "environment": "prod",
    }

    with (
        patch("koda.state.knowledge_governance_store.get_latest_execution_episode", return_value=episode),
        patch(
            "koda.state.knowledge_governance_store.get_correction_event",
            return_value={"id": 55},
        ),
        patch("koda.state.knowledge_governance_store.primary_fetch_val") as mock_insert,
    ):
        result = record_correction_event(
            agent_id="agent_a",
            task_id=77,
            feedback_type="approved",
            user_id=101,
        )

    assert result == 55
    mock_insert.assert_not_called()
