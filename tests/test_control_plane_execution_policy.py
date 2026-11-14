"""Focused tests for execution-policy control-plane contracts."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from aiohttp import web

from koda.control_plane import api as control_plane_api
from koda.control_plane.execution_policy import (
    build_mcp_action_catalog,
    build_policy_catalog,
    evaluate_execution_policy,
    resolve_execution_policy,
    validate_execution_policy,
)


class _Request:
    def __init__(self, *, payload: dict[str, object] | None = None) -> None:
        self.match_info: dict[str, str] = {}
        self.headers: dict[str, str] = {}
        self.can_read_body = payload is not None
        self._payload = payload or {}

    async def json(self) -> dict[str, object]:
        return dict(self._payload)


def test_resolve_execution_policy_returns_explicit_policy_only() -> None:
    catalog = build_policy_catalog()
    tool_id = catalog["tool_ids"][0]

    explicit = {
        "version": 1,
        "rules": [
            {
                "name": f"allow_{tool_id}",
                "priority": 100,
                "match": {"tool_id": tool_id},
                "decision": "allow",
            }
        ],
        "defaults": {"default_approval_mode": "guarded"},
    }

    policy = resolve_execution_policy({"execution_policy": explicit})

    assert policy["rules"][0]["match"]["tool_id"] == tool_id
    assert policy["defaults"]["default_approval_mode"] == "guarded"


def test_resolve_execution_policy_returns_empty_when_no_explicit_policy() -> None:
    policy = resolve_execution_policy(
        {
            "tool_policy": {"allowed_tool_ids": ["http_request"]},
            "autonomy_policy": {"default_approval_mode": "guarded"},
        }
    )

    assert policy == {}


def test_build_policy_catalog_exposes_action_entries_and_groupings() -> None:
    catalog = build_policy_catalog()
    actions = catalog["actions"]

    assert actions
    assert catalog["approval_scope_templates"]
    assert catalog["action_groups"]["by_integration"]
    assert any(action["tool_id"] == "http_request" and action["action_id"] == "http.get" for action in actions)
    legacy_external_ids = {"gws", "jira", "confluence", "gh", "glab", "aws"}
    assert not any(action["tool_id"] in legacy_external_ids for action in actions)
    core_integration_ids = {str(item.get("id") or "") for item in catalog.get("core_integrations", [])}
    assert not (core_integration_ids & legacy_external_ids)


def test_build_mcp_action_catalog_maps_tool_policies_to_defaults() -> None:
    actions = build_mcp_action_catalog(
        server_key="github",
        tools=[
            {
                "name": "create_issue",
                "description": "Create an issue.",
                "annotations": {"title": "Create issue"},
            }
        ],
        tool_policies={"create_issue": "always_ask"},
        connection_title="GitHub MCP",
    )

    assert actions[0]["tool_id"] == "mcp_github__create_issue"
    assert actions[0]["integration_id"] == "mcp:github"
    assert actions[0]["default_decision"] == "require_approval"
    assert actions[0]["approval_scope_default"] == "tool_call"


def test_evaluate_execution_policy_applies_safe_defaults_and_overlays() -> None:
    catalog = build_policy_catalog()
    tool_id = catalog["tool_ids"][0]
    policy = {"version": 1, "rules": []}

    safe = evaluate_execution_policy(policy, {"tool_id": tool_id, "access_level": "read"}, policy_catalog=catalog)
    write = evaluate_execution_policy(policy, {"tool_id": tool_id, "access_level": "write"}, policy_catalog=catalog)
    destructive = evaluate_execution_policy(
        policy,
        {"tool_id": tool_id, "access_level": "admin", "effect_tags": ["credential_access"]},
        policy_catalog=catalog,
    )
    private_network = evaluate_execution_policy(
        policy,
        {"tool_id": tool_id, "private_network": True},
        policy_catalog=catalog,
    )

    assert safe["decision"] == "allow"
    assert write["decision"] == "allow_with_preview"
    assert destructive["decision"] == "require_approval"
    assert private_network["decision"] == "deny"


def test_evaluate_execution_policy_resolves_action_id_from_catalog() -> None:
    catalog = build_policy_catalog()
    action = next(
        item for item in catalog["actions"] if item["tool_id"] == "http_request" and item["action_id"] == "http.get"
    )

    evaluation = evaluate_execution_policy(
        {"version": 1, "rules": []},
        {"action_id": action["action_id"], "integration_id": action["integration_id"]},
        policy_catalog=catalog,
    )

    assert evaluation["decision"] == "allow_with_preview"
    assert evaluation["audit_payload"]["envelope"]["tool_id"] == "http_request"
    assert evaluation["audit_payload"]["envelope"]["action_id"] == "http.get"
    assert isinstance(evaluation["preview_text"], str)
    assert "Action Id: http.get" in evaluation["preview_text"]


def test_evaluate_execution_policy_degrades_explicit_allow_for_human_factor_actions() -> None:
    catalog = build_policy_catalog()
    policy = {
        "version": 1,
        "rules": [
            {
                "name": "allow-browser-cookie-set",
                "match": {"tool_id": "browser_cookies"},
                "decision": "allow",
            }
        ],
    }

    evaluation = evaluate_execution_policy(
        policy,
        {
            "tool_id": "browser_cookies",
            "access_level": "admin",
            "effect_tags": ["browser_state_mutation", "identity_admin"],
        },
        policy_catalog=catalog,
    )

    assert evaluation["decision"] == "require_approval"
    assert evaluation["reason_code"] == "human_factor_required"


def test_validate_execution_policy_rejects_invalid_decisions() -> None:
    errors, warnings = validate_execution_policy(
        {
            "version": 1,
            "rules": [
                {
                    "name": "bad-rule",
                    "match": {"tool_id": "web_search"},
                    "decision": "maybe",
                }
            ],
        }
    )

    assert errors
    assert not warnings


@pytest.mark.asyncio
async def test_execution_policy_handlers_proxy_manager_payloads() -> None:
    manager = MagicMock()
    manager.get_execution_policy.return_value = {"agent_id": "AGENT_A", "policy": {"version": 1}}
    manager.put_execution_policy.return_value = {"agent_id": "AGENT_A", "policy": {"version": 1}}
    manager.get_execution_policy_catalog.return_value = {"agent_id": "AGENT_A", "catalog": {"version": 1}}
    manager.evaluate_execution_policy.return_value = {
        "agent_id": "AGENT_A",
        "action": {"tool_id": "web_search"},
        "evaluation": {"decision": "allow", "preview_text": None},
    }

    with patch("koda.control_plane.api._manager", return_value=manager):
        get_request = _Request()
        get_request.match_info = {"agent_id": "AGENT_A"}
        get_response = await control_plane_api.get_execution_policy(get_request)

        put_request = _Request(payload={"policy": {"version": 1}})
        put_request.match_info = {"agent_id": "AGENT_A"}
        put_response = await control_plane_api.put_execution_policy(put_request)

        catalog_request = _Request()
        catalog_request.match_info = {"agent_id": "AGENT_A"}
        catalog_response = await control_plane_api.get_execution_policy_catalog(catalog_request)

        evaluate_request = _Request(payload={"action": {"tool_id": "web_search"}})
        evaluate_request.match_info = {"agent_id": "AGENT_A"}
        evaluate_response = await control_plane_api.evaluate_execution_policy(evaluate_request)

    manager.get_execution_policy.assert_called_once_with("AGENT_A")
    manager.put_execution_policy.assert_called_once_with("AGENT_A", {"policy": {"version": 1}})
    manager.get_execution_policy_catalog.assert_called_once_with("AGENT_A")
    manager.evaluate_execution_policy.assert_called_once_with(
        "AGENT_A",
        {"action": {"tool_id": "web_search"}},
    )

    assert json.loads(get_response.text)["agent_id"] == "AGENT_A"
    assert json.loads(put_response.text)["agent_id"] == "AGENT_A"
    assert json.loads(catalog_response.text)["agent_id"] == "AGENT_A"
    assert json.loads(evaluate_response.text)["evaluation"] == {"decision": "allow", "preview_text": None}


def test_setup_control_plane_routes_registers_execution_policy_surfaces() -> None:
    app = web.Application()
    control_plane_api.setup_control_plane_routes(app)
    canonicals = {route.resource.canonical for route in app.router.routes()}

    assert "/api/control-plane/agents/{agent_id}/execution-policy" in canonicals
    assert "/api/control-plane/agents/{agent_id}/policy-catalog" in canonicals
    assert "/api/control-plane/agents/{agent_id}/execution-policy/evaluate" in canonicals


def test_agent_spec_validation_rejects_regex_execution_policy_patterns() -> None:
    from koda.control_plane.agent_spec import validate_agent_spec

    report = validate_agent_spec(
        {
            "execution_policy": {
                "version": 1,
                "rules": [{"name": "deny-deletes", "match": {"tool_id": "^mcp_.*__delete_.*"}, "decision": "deny"}],
            }
        }
    )

    assert any(error.startswith("execution_policy.rules[0].match.tool_id") for error in report["errors"])


def _put_agent_spec_manager(current_policy: dict[str, object]) -> MagicMock:
    manager = MagicMock()
    manager._require_agent_row.return_value = ("AGENT_A", {})
    manager.get_agent_spec.return_value = {"execution_policy": current_policy}
    manager.get_section.return_value = {"data": {}}
    manager.get_document.return_value = None
    return manager


def test_put_agent_spec_rejects_a_written_policy_whose_rules_the_normalizer_would_drop() -> None:
    from koda.control_plane.manager import ControlPlaneManager

    for written in (
        {"version": 1, "rules": [{"name": "deny-shell", "match": {"tool_id": "shell"}, "decision": "dney"}]},
        {"version": 1, "rules": [{"name": "deny-shell", "selectors": {"tool_id": "shell"}, "action": "dney"}]},
        {"version": 1, "rules": [{"name": "deny-all", "match": {}, "decision": "deny"}]},
        {"version": 1, "rules": [{"name": "d", "match": {"tool_id": "web_search", "private_network": "ture"}}]},
    ):
        manager = _put_agent_spec_manager({})

        with pytest.raises(ValueError, match=r"execution_policy\.rules\[0\]"):
            ControlPlaneManager.put_agent_spec(manager, "agent_a", {"execution_policy": written})

        manager.put_section.assert_not_called()


def test_put_execution_policy_rejects_an_invalid_policy_before_storing_it() -> None:
    from koda.control_plane.manager import ControlPlaneManager

    manager = _put_agent_spec_manager({})
    manager.put_agent_spec.side_effect = lambda agent_id, payload: ControlPlaneManager.put_agent_spec(
        manager, agent_id, payload
    )
    policy = {"version": 1, "rules": [{"name": "deny-shell", "match": {"tool_id": "shell"}, "decision": "dney"}]}

    with pytest.raises(ValueError, match=r"execution_policy\.rules\[0\]\.decision is invalid: dney"):
        ControlPlaneManager.put_execution_policy(manager, "agent_a", {"policy": policy})

    manager.put_section.assert_not_called()


def test_put_agent_spec_stores_a_valid_policy_and_saves_other_edits_beside_an_unchanged_one() -> None:
    from koda.control_plane.manager import ControlPlaneManager

    valid = {"version": 1, "rules": [{"name": "deny-shell", "match": {"tool_id": "shell_execute"}, "decision": "deny"}]}
    manager = _put_agent_spec_manager({})
    ControlPlaneManager.put_agent_spec(manager, "agent_a", {"execution_policy": valid})
    runtime_writes = [call for call in manager.put_section.call_args_list if call.args[1] == "runtime"]
    assert runtime_writes[0].args[2]["data"]["execution_policy"]["rules"][0]["name"] == "deny-shell"

    # A stored policy with an error the normalizer keeps (an unknown selector) is reported at publish;
    # sending it back unchanged must not block an unrelated edit.
    stored = {
        "version": 1,
        "rules": [{"name": "typo", "priority": 0, "match": {"tool_ids": "shell_execute"}, "decision": "deny"}],
    }
    manager = _put_agent_spec_manager(stored)
    ControlPlaneManager.put_agent_spec(
        manager,
        "agent_a",
        {"execution_policy": json.loads(json.dumps(stored)), "mission_profile": {"goal": "ship"}},
    )
    assert any(call.args[1] == "identity" for call in manager.put_section.call_args_list)


def test_publish_validation_reports_a_stored_rule_that_the_normalizer_drops() -> None:
    from koda.control_plane.agent_spec import build_agent_spec_from_snapshot
    from koda.control_plane.manager import ControlPlaneManager

    # Stored through the runtime section route, which keeps the policy as written.
    stored = {
        "version": 1,
        "rules": [
            {"name": "allow-search", "match": {"tool_id": "web_search"}, "decision": "allow"},
            {"name": "deny-shell", "match": {"tool_id": "shell_execute"}, "decision": "dney"},
        ],
    }
    snapshot = {"agent": {"id": "AGENT_A"}, "sections": {"runtime": {"execution_policy": stored}}, "env": {}}
    manager = MagicMock()
    manager.get_agent_spec.return_value = build_agent_spec_from_snapshot(snapshot)
    manager._validation_inputs.return_value = ({}, {}, [])
    manager._provider_catalog_from_env.return_value = {}
    assert [rule["name"] for rule in manager.get_agent_spec.return_value["execution_policy"]["rules"]] == [
        "allow-search"
    ]

    with patch("koda.control_plane.manager.fetch_one", return_value=None):
        report = ControlPlaneManager._build_validation_report(manager, snapshot)

    assert (
        "execution_policy.rules[1].decision is invalid: dney. "
        "Expected one of: allow, allow_with_preview, deny, require_approval"
    ) in report["errors"]
