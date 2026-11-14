"""Focused runtime tests for the central execution-policy gate."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from koda.services.execution_policy import (
    evaluate_execution_policy,
    normalize_execution_policy,
    resolve_execution_policy_allowed_tool_ids,
    validate_execution_policy,
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


def test_normalizer_migrates_legacy_rule_keys_to_the_canonical_keys() -> None:
    normalized = normalize_execution_policy(
        {
            "version": 1,
            "rules": [
                {
                    "id": "legacy-deny-shell",
                    "selectors": {"tool_id": ["shell_execute"]},
                    "action": "deny",
                    "reason_code": "no_shell",
                    "priority": "5",
                },
                {
                    "rule_id": "legacy-approve-jobs",
                    "selectors": {"tool_id": "job_create"},
                    "decision": "require_approval",
                },
            ],
        }
    )

    assert normalized["rules"] == [
        {
            "name": "legacy-deny-shell",
            "priority": 5,
            "match": {"tool_id": ["shell_execute"]},
            "decision": "deny",
            "reason": "no_shell",
        },
        {
            "name": "legacy-approve-jobs",
            "priority": 0,
            "match": {"tool_id": "job_create"},
            "decision": "require_approval",
        },
    ]
    for rule in normalized["rules"]:
        assert not {"id", "rule_id", "selectors", "action", "reason_code"} & set(rule)


def test_normalizer_prefers_canonical_keys_over_legacy_aliases() -> None:
    normalized = normalize_execution_policy(
        {
            "rules": [
                {
                    "name": "canonical-name",
                    "id": "legacy-id",
                    "match": {"tool_id": "web_search"},
                    "selectors": {"tool_id": "shell_execute"},
                    "decision": "deny",
                    "action": "allow",
                }
            ]
        }
    )

    assert normalized["rules"] == [
        {"name": "canonical-name", "priority": 0, "match": {"tool_id": "web_search"}, "decision": "deny"}
    ]


def test_normalizer_names_rules_by_index_defaults_decision_and_orders_by_priority_then_name() -> None:
    normalized = normalize_execution_policy(
        {
            "rules": [
                {"match": {"tool_id": "web_search"}},
                {"name": "b", "priority": 10, "match": {"tool_id": "file_read"}, "decision": "allow"},
                {"name": "a", "priority": 10, "match": {"tool_id": "file_list"}, "decision": "allow"},
            ]
        }
    )

    assert [(rule["name"], rule["decision"]) for rule in normalized["rules"]] == [
        ("a", "allow"),
        ("b", "allow"),
        ("rule_0", "require_approval"),
    ]


def test_normalizer_drops_rules_without_selectors_or_with_unknown_decisions() -> None:
    normalized = normalize_execution_policy(
        {
            "version": 1,
            "rules": [
                {"name": "catch-all", "match": {}, "decision": "deny"},
                {"name": "no-match", "decision": "allow"},
                {"name": "maybe", "match": {"tool_id": "web_search"}, "decision": "maybe"},
                "not-a-rule",
            ],
        }
    )

    assert normalized == {"version": 1}


def test_normalizer_is_idempotent_on_its_own_output() -> None:
    once = normalize_execution_policy(
        {
            "version": 1,
            "defaults": {"default_approval_mode": "guarded"},
            "rules": [
                {
                    "id": "legacy",
                    "selectors": {"tool_id": ["shell_execute"], "private_network": "false"},
                    "action": "deny",
                },
                {"name": "preview", "match": {"tool_id": "file_write"}, "decision": "allow_with_preview"},
            ],
        }
    )

    assert normalize_execution_policy(once) == once
    assert once["rules"][0]["match"] == {"tool_id": ["shell_execute"], "private_network": False}


def test_control_plane_normalizer_and_validator_delegate_to_the_runtime_engine() -> None:
    from koda.control_plane import execution_policy as control_plane_policy

    assert control_plane_policy.normalize_execution_policy is normalize_execution_policy
    assert control_plane_policy.validate_execution_policy is validate_execution_policy


def test_validation_rejects_regex_patterns_with_their_path() -> None:
    errors, _warnings = validate_execution_policy(
        {
            "version": 1,
            "rules": [
                {"name": "ok", "match": {"tool_id": "mcp_*__delete_*"}, "decision": "deny"},
                {"name": "regex", "match": {"tool_id": ["web_search", " ^mcp_.*__delete_.*$"]}, "decision": "deny"},
            ],
        }
    )

    assert len(errors) == 1
    assert errors[0].startswith("execution_policy.rules[1].match.tool_id")
    assert "^mcp_.*__delete_.*$" in errors[0]
    assert "fnmatch" in errors[0]


def test_validation_accepts_fnmatch_patterns_and_legacy_selectors() -> None:
    errors, warnings = validate_execution_policy(
        {
            "version": 1,
            "rules": [
                {"name": "a", "match": {"tool_id": "mcp_*__delete_*"}, "decision": "deny"},
                {"name": "b", "match": {"action_id": "http.[pd]*", "path": "/srv/*/secrets"}, "decision": "deny"},
                {"id": "c", "selectors": {"tool_id": ["file_?ead"]}, "decision": "allow"},
            ],
        }
    )

    assert errors == []
    assert warnings == []


def test_explicit_rule_approval_scope_defaults_to_once_with_rule_ttl() -> None:
    evaluation = evaluate_execution_policy(
        "file_write",
        {"path": "notes.txt", "content": "x"},
        resource_access_policy={"integration_grants": {"fileops": {"allow_actions": ["fileops.*"]}}},
        execution_policy={
            "rules": [
                {"name": "approve-writes", "match": {"tool_id": "file_write"}, "decision": "require_approval"},
                {
                    "name": "approve-writes-scoped",
                    "priority": -1,
                    "match": {"tool_id": "file_write"},
                    "decision": "require_approval",
                    "approval_scope_kind": "scope",
                    "approval_ttl_seconds": 5,
                },
            ]
        },
        known_tool=True,
    )

    assert evaluation.rule_id == "approve-writes"
    assert evaluation.approval_scope is not None
    assert (evaluation.approval_scope.kind, evaluation.approval_scope.ttl_seconds) == ("once", 600)
    assert evaluation.approval_scope.max_uses == 1
