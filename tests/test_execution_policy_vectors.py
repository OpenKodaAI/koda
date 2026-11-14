"""Execution-policy parity vectors (ADR-002 AG-06; ADR-008 step 1).

Every vector in ``tests/fixtures/execution_policy_vectors.json`` is evaluated twice:

* by the runtime engine, called the way an agent worker calls it (policy inputs
  passed explicitly, the autonomy policy and ``AGENT_ID`` taken from the worker's
  environment, ``known_tool`` from the dispatcher), in a worker whose environment
  is the vector's ``agent.env``, so its feature flags are those koda.config
  computes from it (``test_feature_flags_from_env_matches_koda_config`` proves
  the derivation);
* by the control-plane simulate route, through the aiohttp handler and the real
  ``ControlPlaneManager.evaluate_execution_policy`` with the agent's draft spec
  and snapshot env stubbed, in a process whose own ``AGENT_ID`` and autonomy env
  are unset.

Both must return the vector's expected decision, reason code and rule id, and
the same approval scope, preview and matched selector.
"""

from __future__ import annotations

import json
from functools import partial
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from koda.agent_contract import DISPATCHER_TOOL_IDS
from koda.control_plane import api as control_plane_api
from koda.control_plane.execution_policy import build_policy_catalog
from koda.control_plane.manager import ControlPlaneManager, _worker_feature_flags
from koda.knowledge.task_policy_defaults import default_execution_policy
from koda.services import execution_policy as runtime_policy
from koda.services.tool_dispatcher import _TOOL_HANDLERS, is_known_tool

_VECTORS_PATH = Path(__file__).parent / "fixtures" / "execution_policy_vectors.json"
_DOCUMENT: dict[str, Any] = json.loads(_VECTORS_PATH.read_text(encoding="utf-8"))
_AGENT_ID: str = _DOCUMENT["agent_id"]
_VECTORS: list[dict[str, Any]] = _DOCUMENT["vectors"]


class _Request:
    def __init__(self, *, agent_id: str, payload: dict[str, Any]) -> None:
        self.match_info = {"agent_id": agent_id}
        self.headers: dict[str, str] = {}
        self.can_read_body = True
        self._payload = payload

    async def json(self) -> dict[str, Any]:
        return json.loads(json.dumps(self._payload))


def _agent(vector: dict[str, Any]) -> dict[str, Any]:
    return {**_DOCUMENT["agent_defaults"], **vector.get("agent", {})}


def _control_plane_store(agent: dict[str, Any]) -> MagicMock:
    """The control-plane rows the runtime's legacy MCP lookups read, for the vectors' agent only."""
    store = MagicMock()

    def list_mcp_tool_policies(agent_id: str, server_key: str) -> list[dict[str, str]]:
        if agent_id != _AGENT_ID:
            return []
        policies = agent["mcp_tool_policies"].get(server_key, {})
        return [{"tool_name": name, "policy": policy} for name, policy in policies.items()]

    store.list_mcp_tool_policies.side_effect = list_mcp_tool_policies
    store.get_mcp_connection_tools.return_value = {"tools": []}
    return store


def _runtime_evaluation(vector: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> runtime_policy.PolicyEvaluation:
    agent = _agent(vector)
    action = vector["action"]
    task_kind = action.get("task_kind", "general")
    monkeypatch.setenv("AGENT_AUTONOMY_POLICY_JSON", json.dumps(agent["autonomy_policy"]))
    worker_flags = _worker_feature_flags({"env": agent["env"]})
    try:
        with (
            patch.object(runtime_policy, "AGENT_ID", _AGENT_ID),
            patch.object(runtime_policy, "_configured_feature_flags", return_value=worker_flags),
            patch("koda.control_plane.manager.get_control_plane_manager", return_value=_control_plane_store(agent)),
        ):
            return runtime_policy.evaluate_execution_policy(
                action["tool_id"],
                action.get("params") or {},
                task_kind=task_kind,
                effective_policy=default_execution_policy(task_kind),
                tool_policy=agent["tool_policy"],
                resource_access_policy=agent["resource_access_policy"],
                execution_policy=vector["policy"],
                known_tool=is_known_tool(action["tool_id"]),
            )
    finally:
        monkeypatch.delenv("AGENT_AUTONOMY_POLICY_JSON", raising=False)


async def _simulate_route_payload(
    vector: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    *,
    policy_in_request: bool = False,
) -> dict[str, Any]:
    agent = _agent(vector)
    monkeypatch.delenv("AGENT_AUTONOMY_POLICY_JSON", raising=False)
    agent_spec = {
        "tool_policy": agent["tool_policy"],
        "resource_access_policy": agent["resource_access_policy"],
        "autonomy_policy": agent["autonomy_policy"],
        "execution_policy": {} if policy_in_request else vector["policy"],
    }
    manager = MagicMock()
    manager.build_draft_snapshot.return_value = {"env": dict(agent["env"])}
    manager._validation_inputs.return_value = ({}, {}, [])
    manager.get_agent_spec.return_value = agent_spec
    manager._execution_policy_catalog.return_value = build_policy_catalog()
    manager.evaluate_execution_policy = partial(ControlPlaneManager.evaluate_execution_policy, manager)
    payload: dict[str, Any] = {"action": vector["action"]}
    if policy_in_request:
        payload["policy"] = vector["policy"]
    with (
        patch.object(runtime_policy, "AGENT_ID", ""),
        patch("koda.control_plane.manager.get_control_plane_manager", return_value=_control_plane_store(agent)),
        patch("koda.control_plane.api._manager", return_value=manager),
    ):
        response = await control_plane_api.evaluate_execution_policy(_Request(agent_id=_AGENT_ID, payload=payload))
    return json.loads(response.text)


def _runtime_summary(evaluation: runtime_policy.PolicyEvaluation) -> dict[str, Any]:
    scope = evaluation.approval_scope
    return {
        "decision": evaluation.decision,
        "reason_code": evaluation.reason_code,
        "rule_id": evaluation.rule_id,
        "approval_scope": (
            None
            if scope is None
            else {"kind": scope.kind, "ttl_seconds": scope.ttl_seconds, "max_uses": scope.max_uses}
        ),
        "preview_text": evaluation.preview_text,
        "matched_selector": json.loads(json.dumps(evaluation.matched_selector)),
    }


def _route_summary(evaluation: dict[str, Any]) -> dict[str, Any]:
    scope = evaluation.get("approval_scope")
    return {
        "decision": evaluation.get("decision"),
        "reason_code": evaluation.get("reason_code"),
        "rule_id": evaluation.get("rule_id"),
        "approval_scope": (
            None if scope is None else {key: scope.get(key) for key in ("kind", "ttl_seconds", "max_uses")}
        ),
        "preview_text": evaluation.get("preview_text"),
        "matched_selector": evaluation.get("matched_selector"),
    }


def _expected(summary: dict[str, Any]) -> dict[str, Any]:
    return {key: summary[key] for key in ("decision", "reason_code", "rule_id")}


def test_vectors_file_is_well_formed() -> None:
    ids = [vector["id"] for vector in _VECTORS]
    assert len(ids) == len(set(ids)), "vector ids must be unique"
    for vector in _VECTORS:
        assert {"id", "description", "policy", "action", "expected"} <= set(vector), vector["id"]
        assert set(vector["expected"]) == {"decision", "reason_code", "rule_id"}, vector["id"]
        assert vector["expected"]["decision"] in {"allow", "allow_with_preview", "require_approval", "deny"}
        assert set(vector.get("agent", {})) <= set(_DOCUMENT["agent_defaults"]), vector["id"]


@pytest.mark.parametrize("vector", _VECTORS, ids=[vector["id"] for vector in _VECTORS])
def test_runtime_engine_returns_the_vector_decision(vector: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    summary = _runtime_summary(_runtime_evaluation(vector, monkeypatch))

    assert _expected(summary) == vector["expected"]


@pytest.mark.asyncio
@pytest.mark.parametrize("vector", _VECTORS, ids=[vector["id"] for vector in _VECTORS])
async def test_simulate_route_equals_the_runtime_engine(
    vector: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime_summary(_runtime_evaluation(vector, monkeypatch))
    route = _route_summary((await _simulate_route_payload(vector, monkeypatch))["evaluation"])

    assert _expected(route) == vector["expected"]
    assert route == runtime


@pytest.mark.asyncio
async def test_simulate_route_evaluates_a_draft_policy_sent_with_the_request(monkeypatch: pytest.MonkeyPatch) -> None:
    vector = next(item for item in _VECTORS if item["id"] == "deny-wins-over-higher-priority-allow")

    payload = await _simulate_route_payload(vector, monkeypatch, policy_in_request=True)

    assert _expected(_route_summary(payload["evaluation"])) == vector["expected"]
    assert [rule["name"] for rule in payload["policy"]["rules"]] == ["allow-github", "deny-mcp-deletes"]
    assert payload["agent_id"] == _AGENT_ID
    assert payload["action"] == vector["action"]
    assert payload["evaluation"]["envelope"]["tool_id"] == "mcp_github__delete_repo"
    assert payload["evaluation"]["envelope"]["access_level"] == "destructive"


def test_known_dispatcher_tools_are_the_dispatchers_handlers() -> None:
    """The simulator's known-tool set is the worker's handler set (plugin tools aside)."""
    assert frozenset(_TOOL_HANDLERS) == DISPATCHER_TOOL_IDS


@pytest.mark.asyncio
async def test_simulate_route_equals_the_runtime_engine_for_every_dispatcher_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policies = {
        "no-rules": {},
        "allow-everything": {
            "version": 1,
            "rules": [{"name": "allow-all", "match": {"tool_id": "*"}, "decision": "allow"}],
        },
    }
    mismatches: list[tuple[str, str, dict[str, Any], dict[str, Any]]] = []
    for tool_id in sorted(DISPATCHER_TOOL_IDS):
        for policy_name, policy in policies.items():
            vector = {"policy": policy, "action": {"tool_id": tool_id, "params": {}}}
            runtime = _runtime_summary(_runtime_evaluation(vector, monkeypatch))
            route = _route_summary((await _simulate_route_payload(vector, monkeypatch))["evaluation"])
            if route != runtime or route["reason_code"] == "unknown_action":
                mismatches.append((tool_id, policy_name, runtime, route))

    assert mismatches == []


def _vector(vector_id: str) -> dict[str, Any]:
    return next(item for item in _VECTORS if item["id"] == vector_id)


@pytest.mark.asyncio
async def test_simulate_route_uses_the_agents_worker_flags_not_its_own_process_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control-plane process has the browser off; the agent's worker environment turns it on."""
    vector = _vector("legacy-branch-with-the-browser-on-in-the-workers-environment")

    with patch.object(runtime_policy, "BROWSER_FEATURES_ENABLED", False):
        assert runtime_policy._configured_feature_flags()["browser"] is False
        route = _route_summary((await _simulate_route_payload(vector, monkeypatch))["evaluation"])

    assert _expected(route) == vector["expected"]
    assert _expected(route) == {"decision": "require_approval", "reason_code": "legacy_human_factor", "rule_id": None}


def test_worker_feature_flags_take_the_settings_the_supervisor_forces(monkeypatch: pytest.MonkeyPatch) -> None:
    from koda.control_plane import supervisor
    from koda.control_plane.manager import _SUPERVISOR_FORCED_FEATURE_FLAG_KEYS

    # The supervisor copies these from its own environment onto every worker, over the snapshot's
    # value, and copies no other flag setting from its environment.
    assert (
        set(_SUPERVISOR_FORCED_FEATURE_FLAG_KEYS) == runtime_policy.FEATURE_FLAG_ENV_KEYS & supervisor._SYSTEM_ENV_KEYS
    )
    assert runtime_policy.FEATURE_FLAG_ENV_KEYS.isdisjoint(supervisor._SAFE_RUNTIME_PARENT_ENV_KEYS)

    snapshot = {"env": {"INTER_AGENT_ENABLED": "false", "SHELL_ENABLED": False}}
    monkeypatch.setenv("INTER_AGENT_ENABLED", "true")
    monkeypatch.setenv("SHELL_ENABLED", "true")
    forced = _worker_feature_flags(snapshot)
    monkeypatch.delenv("INTER_AGENT_ENABLED")
    from_snapshot = _worker_feature_flags(snapshot)

    assert (forced["inter_agent"], forced["shell"]) == (True, False)
    assert (from_snapshot["inter_agent"], from_snapshot["shell"]) == (False, False)
