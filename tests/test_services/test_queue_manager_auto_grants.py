"""Tests for queue-manager auto cache/script grant gating."""

from __future__ import annotations

from unittest.mock import patch

from koda.services import queue_manager


def test_queue_manager_action_denial_emits_audit() -> None:
    with (
        patch.object(
            queue_manager,
            "AGENT_RESOURCE_ACCESS_POLICY",
            {"integration_grants": {"cache": {"enabled": True, "allow_actions": ["lookup"]}}},
        ),
        patch("koda.services.audit.emit") as audit_emit,
    ):
        allowed = queue_manager._queue_manager_action_allowed(
            integration_id="cache",
            action_id="store",
            user_id=111,
            task_id=22,
            details={"query_text": "hello"},
        )

    assert allowed is False
    audit_emit.assert_called_once()
    assert audit_emit.call_args.args[0].details["reason"] == "action_not_granted"


def test_queue_manager_action_without_grant_is_allowed() -> None:
    with patch.object(queue_manager, "AGENT_RESOURCE_ACCESS_POLICY", {}):
        allowed = queue_manager._queue_manager_action_allowed(
            integration_id="script_library",
            action_id="search",
            user_id=111,
            task_id=22,
        )

    assert allowed is True
