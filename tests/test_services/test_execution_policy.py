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


def test_validation_rejects_unknown_selector_keys_with_their_path() -> None:
    # A deny rule skips a selector the engine cannot evaluate, so this typo would deny every call.
    policy = {
        "version": 1,
        "rules": [
            {"name": "deny-shell", "match": {"tool_ids": "shell_execute"}, "decision": "deny"},
            {"name": "allow-search", "priority": 100, "match": {"tool_id": "web_search"}, "decision": "allow"},
        ],
    }

    errors, warnings = validate_execution_policy(policy)

    assert len(errors) == 1
    assert errors[0].startswith("execution_policy.rules[0].match.tool_ids is not a supported selector")
    assert "tool_id" in errors[0]
    assert warnings == []


def test_validation_rejects_empty_selector_values_with_their_path() -> None:
    errors, _warnings = validate_execution_policy(
        {
            "version": 1,
            "rules": [
                {"name": "a", "match": {"tool_id": ""}, "decision": "deny"},
                {"name": "b", "match": {"tool_id": []}, "decision": "deny"},
                {"name": "c", "match": {"tool_id": None}, "decision": "deny"},
                {"name": "d", "match": {"tool_id": "web_search", "effect_tags": ["  "]}, "decision": "allow"},
                {"name": "e", "match": {"tool_id": "web_search", "private_network": ""}, "decision": "deny"},
            ],
        }
    )

    assert [error.split(" ", 1)[0] for error in errors] == [
        "execution_policy.rules[0].match.tool_id",
        "execution_policy.rules[1].match.tool_id",
        "execution_policy.rules[2].match.tool_id",
        "execution_policy.rules[3].match.effect_tags",
        "execution_policy.rules[4].match.private_network",
    ]
    assert all("is empty" in error for error in errors)


def test_publish_validation_reports_a_deny_rule_that_would_deny_every_call() -> None:
    from koda.control_plane.agent_spec import validate_agent_spec

    policy = {"version": 1, "rules": [{"name": "d", "match": {"tool_id": []}, "decision": "deny"}]}

    report = validate_agent_spec({"execution_policy": policy})

    assert (
        "execution_policy.rules[0].match.tool_id is empty; a selector needs at least one pattern." in (report["errors"])
    )


def test_validation_rejects_duplicate_rule_names_after_defaulting() -> None:
    errors, _warnings = validate_execution_policy(
        {
            "version": 1,
            "rules": [
                {"name": "r", "match": {"tool_id": "file_read"}, "decision": "allow"},
                {"name": "r", "match": {"tool_id": "file_list"}, "decision": "allow"},
                {"match": {"tool_id": "file_info"}, "decision": "allow"},
                {"name": "rule_2", "match": {"tool_id": "file_grep"}, "decision": "allow"},
                {"id": "legacy", "selectors": {"tool_id": "web_search"}, "decision": "allow"},
                {"rule_id": "legacy", "selectors": {"tool_id": "fetch_url"}, "decision": "allow"},
            ],
        }
    )

    assert errors == [
        "execution_policy.rules[1].name duplicates rules[0]: r. Rule names are audit rule ids and must be unique.",
        "execution_policy.rules[3].name duplicates rules[2]: rule_2. Rule names are audit rule ids and must be unique.",
        "execution_policy.rules[5].name duplicates rules[4]: legacy. Rule names are audit rule ids and must be unique.",
    ]


def test_allowlist_resolver_matches_tool_and_integration_patterns_like_the_evaluator() -> None:
    flags = {"fileops": True}

    def allowlist(*rules: dict[str, object]) -> list[str]:
        return resolve_execution_policy_allowed_tool_ids(
            execution_policy={"version": 1, "rules": list(rules)},
            feature_flags=flags,
        )

    wildcard = allowlist({"name": "allow-files", "match": {"tool_id": "file_*"}, "decision": "allow"})
    by_integration = allowlist({"name": "allow-fileops", "match": {"integration_id": "fileops"}, "decision": "allow"})
    both_selectors = allowlist(
        {"name": "web-files", "match": {"tool_id": "file_*", "integration_id": "web"}, "decision": "allow"}
    )
    unevaluable = allowlist({"name": "typo", "match": {"tool_id": "file_*", "team": "core"}, "decision": "allow"})
    deny_only = allowlist({"name": "deny-files", "match": {"tool_id": "file_*"}, "decision": "deny"})

    for tool_id in ("file_write", "file_edit", "file_move"):
        evaluation = evaluate_execution_policy(
            tool_id,
            {"path": "notes.txt"},
            resource_access_policy={"integration_grants": {"fileops": {"allow_actions": ["fileops.*"]}}},
            execution_policy={
                "version": 1,
                "rules": [{"name": "allow-files", "match": {"tool_id": "file_*"}, "decision": "allow"}],
            },
            known_tool=True,
        )
        assert evaluation.rule_id == "allow-files"
        assert tool_id in wildcard
        assert tool_id in by_integration
        assert tool_id not in both_selectors
        assert tool_id not in unevaluable
        assert tool_id not in deny_only
    assert "file_write" in allowlist({"name": "literal", "match": {"tool_id": "file_write"}, "decision": "allow"})


def test_validation_rejects_rules_the_normalizer_would_drop() -> None:
    # Each of these rules is dropped by the normalizer, so without an error it would vanish from the
    # stored policy and a broader allow would decide the calls it was written to deny.
    policy = {
        "version": 1,
        "rules": [
            {"name": "decision-typo", "match": {"tool_id": "shell_execute"}, "decision": "dney"},
            {"name": "legacy-action-typo", "selectors": {"tool_id": "shell_execute"}, "action": "denyy"},
            {"name": "empty-match", "match": {}, "decision": "deny"},
            {"name": "empty-selectors", "selectors": {}, "decision": "deny"},
            {"name": "legacy-action-ok", "selectors": {"tool_id": "web_search"}, "action": "deny"},
        ],
    }

    errors, warnings = validate_execution_policy(policy)

    assert errors == [
        "execution_policy.rules[0].decision is invalid: dney. "
        "Expected one of: allow, allow_with_preview, deny, require_approval",
        "execution_policy.rules[1].action is invalid: denyy. "
        "Expected one of: allow, allow_with_preview, deny, require_approval",
        "execution_policy.rules[2].match is empty; a rule needs at least one selector.",
        "execution_policy.rules[3].match is empty; a rule needs at least one selector.",
    ]
    assert warnings == []
    assert [rule["name"] for rule in normalize_execution_policy(policy)["rules"]] == ["legacy-action-ok"]


def test_validation_rejects_non_boolean_values_on_boolean_selectors() -> None:
    def errors_for(value: object) -> list[str]:
        rule = {"name": "d", "match": {"tool_id": "web_search", "private_network": value}, "decision": "deny"}
        return validate_execution_policy({"version": 1, "rules": [rule]})[0]

    for invalid in ("ture", "maybe", 0, 1, ["yes"], [True, "nope"]):
        assert errors_for(invalid) == ["execution_policy.rules[0].match.private_network must be true or false."], (
            invalid
        )
    for valid in (True, False, "true", "FALSE", "yes", "off", [True, False]):
        assert errors_for(valid) == [], valid


def test_validation_rejects_mapping_and_nested_selector_values() -> None:
    def errors_for(key: str, value: object) -> list[str]:
        rule = {"name": "d", "match": {key: value}, "decision": "deny"}
        return validate_execution_policy({"version": 1, "rules": [rule]})[0]

    expected = "must be a pattern or a list of patterns, not a mapping or a nested list."
    assert errors_for("tool_id", {"is": "web_search"}) == [f"execution_policy.rules[0].match.tool_id {expected}"]
    assert errors_for("tool_id", ["web_search", {"is": "fetch_url"}]) == [
        f"execution_policy.rules[0].match.tool_id {expected}"
    ]
    assert errors_for("effect_tags", [["destructive_change"]]) == [
        f"execution_policy.rules[0].match.effect_tags {expected}"
    ]
    assert errors_for("tool_id", ["web_search", "fetch_*"]) == []


def test_deny_rule_with_an_unevaluable_selector_value_fails_closed_and_is_not_allowlisted() -> None:
    allow_search = {"name": "allow-search", "priority": 100, "match": {"tool_id": "web_search"}, "decision": "allow"}
    for bad_selector in ({"private_network": "ture"}, {"external_side_effect": 0}, {"tool_id": {"is": "web_search"}}):
        deny_search = {"name": "deny-search", "match": {"tool_id": "web_search", **bad_selector}, "decision": "deny"}
        policy = {"version": 1, "rules": [allow_search, deny_search]}

        evaluation = evaluate_execution_policy("web_search", {"query": "koda"}, execution_policy=policy)

        assert (evaluation.decision, evaluation.rule_id) == ("deny", "deny-search"), bad_selector

    allow_with_typo = {"name": "a", "match": {"tool_id": "file_write", "bulk_operation": "nah"}, "decision": "allow"}
    allowlist = resolve_execution_policy_allowed_tool_ids(
        execution_policy={"version": 1, "rules": [allow_with_typo]},
        feature_flags={"fileops": True},
    )
    assert "file_write" not in allowlist


def test_feature_flags_from_env_matches_koda_config() -> None:
    """The simulator's flag derivation equals what koda.config computes in a fresh process with that env."""
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    from koda.services.execution_policy import FEATURE_FLAG_ENV_KEYS, feature_flags_from_env

    defaults = feature_flags_from_env({})
    cases: list[dict[str, str]] = [{}]
    cases.extend({key: "false"} for key in sorted(FEATURE_FLAG_ENV_KEYS))
    cases.extend({key: "TRUE"} for key in sorted(FEATURE_FLAG_ENV_KEYS))
    cases.append(dict.fromkeys(FEATURE_FLAG_ENV_KEYS, "true"))
    cases.append(dict.fromkeys(FEATURE_FLAG_ENV_KEYS, "no"))
    script = """
import importlib, json, os, sys
import dotenv
dotenv.load_dotenv = lambda *args, **kwargs: False  # a developer's .env must not leak into the comparison
import koda.config
import koda.services.execution_policy as runtime_policy
results = []
for case in json.loads(sys.argv[1]):
    for key in json.loads(sys.argv[2]):
        os.environ.pop(key, None)
    os.environ.update(case)
    importlib.reload(koda.config)
    importlib.reload(runtime_policy)
    results.append(runtime_policy._configured_feature_flags())
print(json.dumps(results))
"""
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in FEATURE_FLAG_ENV_KEYS and key != "AGENT_ID" and not key.endswith(tuple(FEATURE_FLAG_ENV_KEYS))
    }
    completed = subprocess.run(
        [sys.executable, "-c", script, json.dumps(cases), json.dumps(sorted(FEATURE_FLAG_ENV_KEYS))],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        timeout=120,
    )

    computed_by_config = json.loads(completed.stdout.strip().splitlines()[-1])
    assert computed_by_config == [feature_flags_from_env(case) for case in cases]
    assert defaults["shell"] and defaults["fileops"] and defaults["git"] and defaults["browser"]
    assert not defaults["plugins"] and not defaults["inter_agent"]


def test_no_spelling_of_a_path_steps_around_a_restrictive_path_rule_beside_a_broader_allow() -> None:
    spellings = (
        "/srv/prod/config.yml",
        "/srv//prod/config.yml",
        "//srv/prod/config.yml",
        "/srv/prod//config.yml",
        "/srv/./prod/config.yml",
        "/srv/prod/./config.yml",
        "/srv/app/../prod/config.yml",
        "/srv/app/../../srv/prod/config.yml",
        "/srv/Prod/../prod/config.yml",
        "/SRV/PROD/config.yml",
        "/srv/prod",
        "/srv/prod/",
    )
    for restrictive in ("deny", "require_approval", "allow_with_preview"):
        policy = {
            "version": 1,
            "rules": [
                {"name": "allow-file-writes", "priority": 100, "match": {"tool_id": "file_write"}, "decision": "allow"},
                {"name": "gate-prod", "match": {"tool_id": "file_write", "path": "/srv/prod"}, "decision": restrictive},
            ],
        }
        for spelling in spellings:
            evaluation = evaluate_execution_policy(
                "file_write",
                {"path": spelling, "content": "x"},
                resource_access_policy={"integration_grants": {"fileops": {"allow_actions": ["fileops.*"]}}},
                execution_policy=policy,
                known_tool=True,
            )

            assert (evaluation.decision, evaluation.rule_id) == (restrictive, "gate-prod"), (restrictive, spelling)
