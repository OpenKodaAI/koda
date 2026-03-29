from koda.services.feedback_policy import (
    build_success_pattern_candidate,
    episode_feedback_gate_reasons,
)


def test_episode_feedback_gate_reasons_requires_completed_grounded_verified_episode():
    reasons = episode_feedback_gate_reasons(
        {
            "status": "failed",
            "verified_before_finalize": False,
            "stale_sources_present": True,
            "ungrounded_operationally": True,
            "post_write_review_required": True,
            "answer_gate_status": "needs_review",
            "source_refs": [],
            "plan": {},
        }
    )

    assert "task_not_completed" in reasons
    assert "stale_sources_present" in reasons
    assert "ungrounded_operationally" in reasons
    assert "post_write_review_required" in reasons
    assert "not_verified_before_finalize" in reasons
    assert "answer_gate_status:needs_review" in reasons
    assert "missing_source_refs" in reasons
    assert "missing_plan_summary" in reasons


def test_build_success_pattern_candidate_produces_pending_runbook_review_payload():
    payload = build_success_pattern_candidate(
        episode={
            "task_kind": "deploy",
            "project_key": "workspace",
            "environment": "prod",
            "team": "ops",
            "verified_before_finalize": True,
            "answer_gate_status": "approved",
            "confidence_score": 0.91,
            "source_refs": [{"source_label": "policy", "layer": "canonical_policy"}],
            "plan": {
                "summary": "Deploy safely",
                "verification": ["Run smoke tests"],
                "steps": ["Apply manifests", "Verify rollout"],
                "rollback": "Rollback deployment on failure.",
            },
        },
        feedback_type="promote",
        task_id=77,
        agent_id="ATLAS",
    )

    assert payload["candidate_type"] == "success_pattern"
    assert payload["force_pending"] is True
    assert payload["agent_id"] == "ATLAS"
    assert payload["proposed_runbook"]["verification"] == ["Run smoke tests"]
    assert payload["proposed_runbook"]["steps"] == ["Apply manifests", "Verify rollout"]
