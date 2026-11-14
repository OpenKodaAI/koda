"""Execution-policy parity vectors (ADR-002 AG-06; ADR-008 step 1).

Every vector in ``tests/fixtures/execution_policy_vectors.json`` is evaluated twice:

* by the runtime engine, called the way an agent worker calls it (policy inputs
  passed explicitly, the autonomy policy and ``AGENT_ID`` taken from the worker's
  environment, ``known_tool`` from the dispatcher), in a worker started from a
  snapshot whose env is the vector's ``agent.env``, so its feature flags are
  those koda.config computes there
  (``test_simulator_feature_flags_equal_those_of_the_worker_the_supervisor_starts``
  and ``test_feature_flags_from_env_matches_koda_config`` prove the derivation);
* by the control-plane simulate route, through the aiohttp handler and the real
  ``ControlPlaneManager.evaluate_execution_policy`` with the agent's draft spec
  and snapshot env stubbed, in a process whose own ``AGENT_ID`` and autonomy env
  are unset.

Both must return the vector's expected decision, reason code and rule id, and
the same approval scope, preview and matched selector.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from koda.agent_contract import DISPATCHER_TOOL_IDS
from koda.control_plane import api as control_plane_api
from koda.control_plane import supervisor as supervisor_module
from koda.control_plane.execution_policy import build_policy_catalog
from koda.control_plane.manager import ControlPlaneManager, RuntimeSnapshot, _stringify_env_value
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


# The supervisor's own state that ``ControlPlaneSupervisor._build_spec`` reads besides the snapshot.
_SUPERVISOR = SimpleNamespace(
    _manager=MagicMock(**{"get_provider_connection.return_value": {}}),
    _link=SimpleNamespace(target="unix:///tmp/koda-test.sock"),
    _workspace_id_for_agent=lambda _agent_id: "default",
)


def _worker_env(agent_id: str, snapshot_env: dict[str, Any]) -> dict[str, str]:
    """The environment of the worker the supervisor starts from a snapshot whose env is ``snapshot_env``.

    Built by the real steps: the manager's runtime snapshot (``_stringify_env_value`` and
    ``_scoped_env``) and ``ControlPlaneSupervisor._build_spec`` in this process's environment.
    """
    runtime = RuntimeSnapshot(
        agent_id=agent_id,
        version=1,
        runtime_dir=Path("/tmp/koda-test"),
        process_env=ControlPlaneManager._scoped_env(
            MagicMock(), agent_id, {key: _stringify_env_value(value) for key, value in snapshot_env.items()}
        ),
        connection_refs=[],
        health_url="http://127.0.0.1:9001/health",
        runtime_base_url="http://127.0.0.1:9001",
        state_backend="postgres",
        db_file_name="",
    )
    return dict(supervisor_module.ControlPlaneSupervisor._build_spec(_SUPERVISOR, agent_id, 1, runtime).environment)


def _runtime_evaluation(vector: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> runtime_policy.PolicyEvaluation:
    agent = _agent(vector)
    action = vector["action"]
    task_kind = action.get("task_kind", "general")
    monkeypatch.setenv("AGENT_AUTONOMY_POLICY_JSON", json.dumps(agent["autonomy_policy"]))
    worker_flags = runtime_policy.feature_flags_from_env(_worker_env(_AGENT_ID, agent["env"]))
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
        # The vectors' workers have no .env file (os.devnull is not one), and a developer's must not leak in.
        patch("koda.control_plane.manager.DOTENV_PATH", Path(os.devnull), create=True),
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


_WORKER_FLAGS_SCRIPT = """
import importlib, json, os, sys
import dotenv
real_load_dotenv = dotenv.load_dotenv
case = {"dotenv_file": None}
loaded_paths = []


def load_dotenv(dotenv_path=None, *args, **kwargs):
    # Record the file koda.config loads, and load the case's file in its place, with koda.config's own
    # arguments: a developer's .env must not leak into the comparison.
    loaded_paths.append(str(dotenv_path))
    return real_load_dotenv(case["dotenv_file"], *args, **kwargs) if case["dotenv_file"] else False


dotenv.load_dotenv = load_dotenv
import koda.config
import koda.services.execution_policy as runtime_policy
results = []
for worker_env, dotenv_file in json.loads(sys.argv[1]):
    case["dotenv_file"] = dotenv_file
    del loaded_paths[:]
    os.environ.clear()
    os.environ.update(worker_env)
    importlib.reload(koda.config)
    importlib.reload(runtime_policy)
    results.append({"flags": runtime_policy._configured_feature_flags(), "loaded_paths": list(loaded_paths)})
print(json.dumps(results))
"""


def _workers_started_with(workers: list[tuple[dict[str, str], str]]) -> list[dict[str, Any]]:
    """What koda.config does in a fresh process for each (worker environment, .env file) pair.

    Each result holds the feature flags it computes and the paths it passes to ``load_dotenv``.
    """
    completed = subprocess.run(
        [sys.executable, "-c", _WORKER_FLAGS_SCRIPT, json.dumps(workers)],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).resolve().parents[1],
        env={key: value for key, value in os.environ.items() if key in {"PATH", "HOME", "LANG"}},
        timeout=120,
    )
    return cast(list[dict[str, Any]], json.loads(completed.stdout.strip().splitlines()[-1]))


def test_simulator_feature_flags_equal_those_of_the_worker_the_supervisor_starts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The simulator's flags equal koda.config's in the worker built by the real snapshot and supervisor steps.

    The worker env is the snapshot env scoped by the manager (``KEY`` and ``<AGENT_ID>_KEY``), with
    the supervisor's own infrastructure keys forced over both, and koda.config reads
    ``<AGENT_ID>_KEY`` first. So the supervisor's INTER_AGENT_ENABLED wins over the snapshot's and
    the ``.env`` file's, and the snapshot's applies only where the supervisor sets none.
    koda.config then loads the install's ``.env`` without override, so the file fills only the keys
    the worker env lacks (unless the worker env sets ``PYTHON_DOTENV_DISABLED``).
    """
    from koda.control_plane import manager as manager_module
    from koda.control_plane.manager import _SUPERVISOR_FORCED_FEATURE_FLAG_KEYS

    # The supervisor forces these flag settings from its own environment, and copies no other one.
    assert set(_SUPERVISOR_FORCED_FEATURE_FLAG_KEYS) == (
        runtime_policy.FEATURE_FLAG_ENV_KEYS & supervisor_module._SYSTEM_ENV_KEYS
    )
    assert runtime_policy.FEATURE_FLAG_ENV_KEYS.isdisjoint(supervisor_module._SAFE_RUNTIME_PARENT_ENV_KEYS)
    install_dotenv_path = str(getattr(manager_module, "DOTENV_PATH", None))
    agent_id = "AGENT_A"
    # (snapshot env, supervisor env, the install's .env file)
    cases: list[tuple[dict[str, Any], dict[str, str], str]] = [
        ({"INTER_AGENT_ENABLED": "true"}, {"INTER_AGENT_ENABLED": "false"}, ""),
        ({"INTER_AGENT_ENABLED": "false"}, {"INTER_AGENT_ENABLED": "true"}, ""),
        ({"inter_agent_enabled": "true"}, {"INTER_AGENT_ENABLED": "false"}, ""),
        ({}, {"INTER_AGENT_ENABLED": "true"}, ""),
        ({}, {}, ""),
        (
            {"SHELL_ENABLED": False, "BROWSER_ENABLED": True},
            {"SHELL_ENABLED": "true", "BROWSER_ENABLED": "false"},
            "",
        ),
        ({"SHELL_ENABLED": "true", "AGENT_A_SHELL_ENABLED": "false"}, {}, ""),
        ({"AGENT_A_SHELL_ENABLED": "false", "SHELL_ENABLED": "true"}, {}, ""),
        ({"AGENT_A_INTER_AGENT_ENABLED": "true"}, {"INTER_AGENT_ENABLED": "false"}, ""),
        # A setting the snapshot leaves unset comes from the install's .env.
        ({}, {}, "SHELL_ENABLED=false\n"),
        ({}, {}, "export BROWSER_ENABLED=true\n# a comment\nGIT_ENABLED='false'\nFILEOPS_ENABLED=\"false\"\n"),
        ({}, {}, "AGENT_A_SHELL_ENABLED=false\nSHELL_ENABLED=true\n"),
        ({}, {}, "INTER_AGENT_ENABLED=true\n"),
        ({}, {"INTER_AGENT_ENABLED": "false"}, "AGENT_A_INTER_AGENT_ENABLED=true\n"),
        # A setting the worker env has wins over the .env, and a key without a value sets nothing.
        ({"SHELL_ENABLED": "true"}, {}, "SHELL_ENABLED=false\nAGENT_A_SHELL_ENABLED=false\n"),
        ({}, {"INTER_AGENT_ENABLED": "false"}, "INTER_AGENT_ENABLED=true\n"),
        ({}, {}, "SHELL_ENABLED\n"),
        # A worker env that disables python-dotenv ignores the file.
        ({"PYTHON_DOTENV_DISABLED": "true"}, {}, "SHELL_ENABLED=false\n"),
    ]
    workers: list[tuple[dict[str, str], str]] = []
    simulated: list[dict[str, bool]] = []
    for index, (snapshot_env, supervisor_env, dotenv_text) in enumerate(cases):
        dotenv_file = tmp_path / f"case-{index}.env"
        dotenv_file.write_text(dotenv_text, encoding="utf-8")
        manager = MagicMock()
        manager.build_draft_snapshot.return_value = {"agent": {"id": agent_id}, "env": snapshot_env}
        manager.get_agent_spec.return_value = {}
        manager._validation_inputs.return_value = ({}, {}, [])
        manager._execution_policy_catalog.return_value = {}
        for key in runtime_policy.FEATURE_FLAG_ENV_KEYS:
            monkeypatch.delenv(key, raising=False)
        with (
            patch.dict(os.environ, supervisor_env),
            patch("koda.control_plane.manager.DOTENV_PATH", dotenv_file, create=True),
            patch("koda.control_plane.manager.simulate_execution_policy", return_value={}) as simulate,
        ):
            workers.append((_worker_env(agent_id, snapshot_env), str(dotenv_file)))
            ControlPlaneManager.evaluate_execution_policy(manager, agent_id, {"action": {"tool_id": "agent_send"}})
        simulated.append(simulate.call_args.kwargs["feature_flags"])

    started = _workers_started_with(workers)

    assert simulated == [worker["flags"] for worker in started]
    assert [flags["inter_agent"] for flags in simulated[:5]] == [False, True, False, True, False]
    assert [flags["shell"] for flags in simulated[9:]] == [False, True, False, True, True, True, True, True, True]
    assert [flags["inter_agent"] for flags in simulated[12:16]] == [True, False, False, False]
    # The simulator reads the file koda.config loads in the worker.
    assert {path for worker in started for path in worker["loaded_paths"]} == {install_dotenv_path}
