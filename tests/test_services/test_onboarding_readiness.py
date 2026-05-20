from __future__ import annotations

from koda.services.onboarding_readiness import build_onboarding_readiness


def test_onboarding_readiness_passes_core_checks_when_ready():
    payload = build_onboarding_readiness(
        status={
            "providers": [{"verified": True}],
            "agents": [{"id": "ATLAS", "status": "active", "telegram_token_configured": True}],
            "storage": {"database": {"ready": True}, "object_storage": {"ready": True}},
            "steps": {"agent_ready": True},
        },
        channel_gateway={"summary": {"allowed": 1, "pending": 0}},
        release_quality={"status": "passed", "latest_eval_run": {"run_id": "eval-1"}},
    )

    by_key = {item["key"]: item for item in payload["checks"]}
    assert payload["schema_version"] == "onboarding_readiness.v1"
    assert by_key["provider"]["status"] == "passed"
    assert by_key["channel"]["status"] == "passed"
    assert by_key["first_task"]["status"] == "passed"
    assert by_key["first_trace"]["status"] == "passed"


def test_onboarding_readiness_reports_actionable_pending_state():
    payload = build_onboarding_readiness(
        status={
            "providers": [],
            "agents": [{"id": "ATLAS", "status": "paused", "telegram_token_configured": True}],
            "storage": {"database": {"ready": True}, "object_storage": {"ready": False}},
            "steps": {"agent_ready": True},
        },
        channel_gateway={"summary": {"allowed": 0, "pending": 2}},
        release_quality=None,
    )

    by_key = {item["key"]: item for item in payload["checks"]}
    assert payload["status"] == "failed"
    assert by_key["provider"]["status"] == "pending"
    assert by_key["storage"]["error"]["code"] == "onboarding.storage_not_ready"
    assert by_key["channel"]["status"] == "warning"
    assert any(action["check"] == "provider" for action in payload["actions"])
