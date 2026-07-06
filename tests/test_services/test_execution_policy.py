"""Focused runtime tests for the central execution-policy gate."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from koda.services.execution_policy import (
    evaluate_execution_policy,
    resolve_execution_policy_allowed_tool_ids,
)


def test_unknown_action_fails_closed() -> None:
    evaluation = evaluate_execution_policy(
        "totally_unknown_tool",
        {},
        execution_policy={"version": 1, "rules": []},
        known_tool=False,
    )

    assert evaluation.decision == "deny"
    assert evaluation.reason_code == "unknown_action"


def test_explicit_allow_is_degraded_to_preview_for_preview_class_actions() -> None:
    evaluation = evaluate_execution_policy(
        "file_delete",
        {"path": "tmp.txt"},
        resource_access_policy={"integration_grants": {"fileops": {"allow_actions": ["fileops.*"]}}},
        execution_policy={
            "version": 1,
            "rules": [
                {
                    "id": "allow-file-delete",
                    "decision": "allow",
                    "selectors": {"tool_id": ["file_delete"]},
                }
            ],
        },
        known_tool=True,
    )

    assert evaluation.decision == "allow_with_preview"
    assert evaluation.reason_code == "preview_required"
    assert evaluation.approval_scope is not None
    assert evaluation.approval_scope.kind == "once"


def test_explicit_allow_is_degraded_to_human_approval_for_human_factor_actions() -> None:
    evaluation = evaluate_execution_policy(
        "browser_cookies",
        {"action": "set", "name": "session", "value": "secret"},
        resource_access_policy={"integration_grants": {"browser": {"allow_actions": ["*"]}}},
        execution_policy={
            "version": 1,
            "rules": [
                {
                    "id": "allow-browser-cookies",
                    "decision": "allow",
                    "selectors": {"tool_id": ["browser_cookies"]},
                }
            ],
        },
        known_tool=True,
    )

    assert evaluation.decision == "require_approval"
    assert evaluation.reason_code == "human_factor_required"
    assert evaluation.approval_scope is not None
    assert evaluation.approval_scope.kind == "once"


def test_approval_grant_replays_authorized_tool_call() -> None:
    blocked = evaluate_execution_policy(
        "file_delete",
        {"path": "tmp.txt"},
        resource_access_policy={"integration_grants": {"fileops": {"allow_actions": ["fileops.*"]}}},
        execution_policy={
            "version": 1,
            "rules": [
                {
                    "id": "approve-file-delete",
                    "decision": "allow_with_preview",
                    "selectors": {"tool_id": ["file_delete"]},
                }
            ],
        },
        known_tool=True,
    )
    allowed = evaluate_execution_policy(
        "file_delete",
        {"path": "tmp.txt"},
        resource_access_policy={"integration_grants": {"fileops": {"allow_actions": ["fileops.*"]}}},
        execution_policy={
            "version": 1,
            "rules": [
                {
                    "id": "approve-file-delete",
                    "decision": "allow_with_preview",
                    "selectors": {"tool_id": ["file_delete"]},
                }
            ],
        },
        approval_grant={"grant_id": "grant-1"},
        known_tool=True,
    )

    assert blocked.requires_confirmation is True
    assert allowed.decision == "allow"
    assert allowed.reason_code == "approval_grant"


def test_legacy_mcp_policy_is_compiled_inside_central_gate() -> None:
    evaluation = evaluate_execution_policy(
        "mcp_github__create_issue",
        {"title": "Security issue"},
        resource_access_policy={"integration_grants": {"github": {"allow_actions": ["*"]}}},
        legacy_mcp_policy="blocked",
        known_tool=True,
    )

    assert evaluation.decision == "deny"
    assert evaluation.reason_code == "mcp_blocked"
    assert evaluation.legacy_compiled is True


def test_legacy_mcp_policy_is_resolved_inside_central_gate_when_not_injected() -> None:
    manager = MagicMock()
    manager.list_mcp_tool_policies.return_value = [{"tool_name": "create_issue", "policy": "blocked"}]

    with patch("koda.control_plane.manager.get_control_plane_manager", return_value=manager):
        evaluation = evaluate_execution_policy(
            "mcp_github__create_issue",
            {"title": "Security issue"},
            known_tool=True,
        )

    assert evaluation.decision == "deny"
    assert evaluation.reason_code == "mcp_blocked"
    assert evaluation.legacy_compiled is True


def test_effective_allowed_tool_ids_include_secure_default_plus_execution_policy_rules() -> None:
    allowed_tool_ids = resolve_execution_policy_allowed_tool_ids(
        execution_policy={
            "version": 1,
            "rules": [
                {
                    "id": "allow-job-create",
                    "decision": "require_approval",
                    "selectors": {"tool_id": ["job_create"]},
                }
            ],
        }
    )

    assert "web_search" in allowed_tool_ids
    assert "agent_get_status" in allowed_tool_ids
    assert "job_create" in allowed_tool_ids
    assert "agent_set_workdir" not in allowed_tool_ids


def test_runtime_rule_match_supports_extended_selector_fields() -> None:
    evaluation = evaluate_execution_policy(
        "shell",
        {"args": "ls -la"},
        tool_policy={"allowed_tool_ids": ["shell"]},
        resource_access_policy={"integration_grants": {"shell": {"allow_actions": ["shell.*"]}}},
        execution_policy={
            "version": 1,
            "rules": [
                {
                    "id": "allow-local-cli-read",
                    "decision": "allow",
                    "selectors": {
                        "tool_id": ["shell"],
                        "transport": ["cli"],
                        "private_network": False,
                        "uses_secrets": False,
                        "bulk_operation": False,
                        "external_side_effect": False,
                    },
                }
            ],
        },
        known_tool=True,
    )

    assert evaluation.decision == "allow"
    assert evaluation.rule_id == "allow-local-cli-read"
