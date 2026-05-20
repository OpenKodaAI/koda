from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from koda.control_plane import api as control_plane_api
from koda.control_plane.manager import ControlPlaneManager
from koda.knowledge.repository import KnowledgeRepository

ROOT = Path(__file__).resolve().parents[1]

CANONICAL_PHASE5_ROUTES = (
    ("POST", "/api/control-plane/agents/{agent_id}/evals/cases/from-run"),
    ("GET", "/api/control-plane/agents/{agent_id}/evals/cases"),
    ("PATCH", "/api/control-plane/agents/{agent_id}/evals/cases/{case_key}"),
    ("POST", "/api/control-plane/agents/{agent_id}/evals/runs"),
    ("GET", "/api/control-plane/agents/{agent_id}/evals/runs/{run_id}"),
    ("POST", "/api/control-plane/agents/{agent_id}/evals/trajectory-exports"),
    ("GET", "/api/control-plane/agents/{agent_id}/evals/release-quality/latest"),
    ("GET", "/api/control-plane/dashboard/quality/overview"),
    ("GET", "/api/control-plane/dashboard/quality/agents/{agent_id}"),
    ("POST", "/api/control-plane/dashboard/quality/failures/{failure_id}/proposal"),
)

EXPECTED_MANAGER_METHODS = (
    "create_eval_case_from_run",
    "list_eval_cases",
    "update_eval_case",
    "run_eval_suite",
    "list_eval_runs",
    "get_eval_run",
    "create_trajectory_export",
    "get_release_quality_latest",
    "get_quality_cockpit_overview",
    "get_quality_cockpit_agent",
    "create_quality_failure_proposal",
)


class _JsonRequest:
    def __init__(
        self,
        payload: dict[str, Any] | None = None,
        *,
        match_info: dict[str, str] | None = None,
        query: dict[str, str] | None = None,
    ) -> None:
        self.match_info = match_info or {"agent_id": "KODA"}
        self.query = query or {}
        self._payload = payload or {}
        self.headers: dict[str, str] = {}
        self.can_read_body = True

    async def json(self) -> dict[str, Any]:
        return self._payload


def test_phase5_control_plane_routes_are_registered_and_legacy_aliases_remain() -> None:
    api_source = (ROOT / "koda" / "control_plane" / "api.py").read_text(encoding="utf-8")

    for _method, path in CANONICAL_PHASE5_ROUTES:
        assert path in api_source
    for legacy_path in (
        "/api/control-plane/agents/{agent_id}/evaluation-cases",
        "/api/control-plane/agents/{agent_id}/knowledge-evals/runs",
    ):
        assert legacy_path in api_source


def test_phase5_manager_methods_are_exposed_for_api_handlers() -> None:
    manager_source = (ROOT / "koda" / "control_plane" / "manager.py").read_text(encoding="utf-8")

    for method_name in EXPECTED_MANAGER_METHODS:
        assert f"def {method_name}(" in manager_source


@pytest.mark.asyncio
async def test_create_eval_case_from_run_route_delegates_to_manager() -> None:
    handler = getattr(control_plane_api, "create_eval_case_from_run_route", None)
    if handler is None:
        pytest.fail(
            "Expected Phase 5 API handler missing: from koda.control_plane.api import create_eval_case_from_run_route",
            pytrace=False,
        )
    manager = MagicMock()
    manager.create_eval_case_from_run.return_value = {
        "schema_version": "eval_case.v1",
        "case_id": "case_run_7101",
        "agent_id": "KODA",
        "source_task_id": 7101,
    }
    request = _JsonRequest({"task_id": 7101}, match_info={"agent_id": "KODA"})

    with (
        patch("koda.control_plane.api._manager", return_value=manager),
        patch("koda.control_plane.api._authorize_request", return_value=None),
    ):
        response = await handler(request)

    assert response.status == 201
    assert json.loads(response.text)["schema_version"] == "eval_case.v1"
    manager.create_eval_case_from_run.assert_called_once_with("KODA", 7101, {"task_id": 7101})


@pytest.mark.asyncio
async def test_create_trajectory_export_route_returns_jsonl_metadata() -> None:
    handler = getattr(control_plane_api, "create_trajectory_export_route", None)
    if handler is None:
        pytest.fail(
            "Expected Phase 5 API handler missing: from koda.control_plane.api import create_trajectory_export_route",
            pytrace=False,
        )
    manager = MagicMock()
    manager.create_trajectory_export.return_value = {
        "schema_version": "trajectory_export.v1",
        "export_id": "traj_phase5_7101",
        "replay_mode": "offline",
        "raw_prompt_included": False,
        "line_count": 3,
    }
    request = _JsonRequest({"task_id": 7101}, match_info={"agent_id": "KODA"})

    with patch("koda.control_plane.api._manager", return_value=manager):
        response = await handler(request)

    payload = json.loads(response.text)
    assert response.status == 201
    assert payload["schema_version"] == "trajectory_export.v1"
    assert payload["raw_prompt_included"] is False
    manager.create_trajectory_export.assert_called_once_with("KODA", {"task_id": 7101})


def test_create_trajectory_export_accepts_eval_run_id() -> None:
    manager = object.__new__(ControlPlaneManager)
    repository = SimpleNamespace(
        get_evaluation_case=lambda case_key: {"case_key": case_key, "source_task_id": 7101},
        get_eval_run_batch=lambda run_id: {
            "run_id": run_id,
            "case_results": [{"case_key": "run:KODA:7101", "status": "passed"}],
        },
        create_trajectory_export=MagicMock(),
    )
    manager._require_dashboard_agent = lambda agent_id: ("KODA", {})  # type: ignore[method-assign]
    manager._knowledge_repository = lambda agent_id: repository  # type: ignore[method-assign]
    manager.get_dashboard_execution = lambda agent_id, task_id: {  # type: ignore[method-assign]
        "task_id": task_id,
        "status": "completed",
        "query_text": "E2E export",
        "response_text": "Redacted response",
        "run_graph": {"nodes": [{"node_id": "model", "node_type": "model_call", "status": "completed"}]},
        "run_replay": {"replay_mode": "offline", "steps": [{"node_id": "model", "status": "completed"}]},
    }
    manager._emit_eval_audit_event = MagicMock()  # type: ignore[method-assign]

    export = ControlPlaneManager.create_trajectory_export(manager, "KODA", {"run_id": "eval-run:latest"})

    assert export["schema_version"] == "trajectory_export.v1"
    assert export["task_id"] == 7101
    assert export["provider_calls_disabled"] is True
    repository.create_trajectory_export.assert_called_once()


def test_evaluation_case_upsert_serializes_json_fields_for_primary_backend() -> None:
    repository = KnowledgeRepository("KODA")
    repository._run_coro_sync = lambda _operation: 42  # type: ignore[method-assign]

    with patch("koda.knowledge.repository.primary_fetch_val", new=MagicMock(return_value=object())) as fetch_val:
        row_id = repository.upsert_evaluation_case(
            case_key="run:KODA:7101",
            source_task_id=7101,
            query_text="Redacted query",
            expected_sources=["doc:1"],
            expected_layers=["run_graph"],
            reference_answer="Redacted answer",
            metadata={"source": "execution_run", "expected_tool_ids": ["read_file"]},
        )

    assert row_id == 42
    values = fetch_val.call_args.args[1]
    assert values[9] == '["doc:1"]'
    assert values[10] == '["run_graph"]'
    assert json.loads(values[16])["expected_tool_ids"] == ["read_file"]


def test_eval_run_batch_serializes_json_fields_for_primary_backend() -> None:
    repository = KnowledgeRepository("KODA")
    repository._run_coro_sync = lambda _operation: None  # type: ignore[method-assign]

    with patch("koda.knowledge.repository.primary_execute", new=MagicMock(return_value=object())) as execute:
        run_id = repository.upsert_eval_run_batch(
            {
                "run_id": "eval-run:1",
                "suite_id": "default",
                "status": "passed",
                "score": 1.0,
                "summary": {"case_count": 1, "passed": 1},
                "case_results": [{"case_key": "run:KODA:7101", "status": "passed"}],
            }
        )

    assert run_id == "eval-run:1"
    values = execute.call_args.args[1]
    assert json.loads(values[6]) == {"case_count": 1, "passed": 1}
    assert json.loads(values[7])[0]["case_key"] == "run:KODA:7101"


def test_trajectory_and_release_quality_serializes_json_fields_for_primary_backend() -> None:
    repository = KnowledgeRepository("KODA")
    repository._run_coro_sync = lambda _operation: None  # type: ignore[method-assign]

    with patch("koda.knowledge.repository.primary_execute", new=MagicMock(return_value=object())) as execute:
        repository.create_trajectory_export(
            {
                "export_id": "trajectory:1",
                "task_id": 7101,
                "status": "created",
                "package_hash": "sha256:abc",
                "jsonl": "{}\n",
                "metadata": {"redacted": True},
            }
        )
        repository.create_release_quality_report(
            {
                "schema_version": "release_quality.v1",
                "status": "passed",
                "summary": {"suite_score": 1.0},
            }
        )

    trajectory_values = execute.call_args_list[0].args[1]
    release_values = execute.call_args_list[1].args[1]
    assert json.loads(trajectory_values[5])["metadata"] == {"redacted": True}
    assert json.loads(release_values[2])["summary"] == {"suite_score": 1.0}


def test_release_quality_latest_fails_when_eval_source_run_graph_is_missing() -> None:
    manager = MagicMock()
    manager._require_dashboard_agent.return_value = ("KODA", None)
    repository = MagicMock()
    repository.list_eval_run_batches.return_value = [
        {
            "schema_version": "eval_run.v1",
            "run_id": "eval-run:1",
            "status": "passed",
            "score": 0.93,
            "case_results": [{"case_key": "run:KODA:7101", "source_task_id": 7101}],
        }
    ]
    repository.list_trajectory_exports.return_value = []
    repository.list_evaluation_cases.return_value = [{"case_key": "run:KODA:7101", "source_task_id": 7101}]
    manager._knowledge_repository.return_value = repository
    manager._release_quality_run_graphs = ControlPlaneManager._release_quality_run_graphs.__get__(manager)
    manager.get_dashboard_execution_run_graph.return_value = None
    manager._emit_eval_audit_event = MagicMock()

    report = ControlPlaneManager.get_release_quality_latest(manager, "KODA")

    assert report["status"] == "failed"
    assert report["gates"]["run_graph_completeness"]["status"] == "failed"
    assert report["gates"]["run_graph_completeness"]["failures"][0]["category"] in {
        "missing_node_type",
        "missing_run_graph",
    }
    manager.get_dashboard_execution_run_graph.assert_called_with("KODA", 7101)


@pytest.mark.asyncio
async def test_release_quality_latest_route_returns_backend_report() -> None:
    handler = getattr(control_plane_api, "get_release_quality_latest_route", None)
    if handler is None:
        pytest.fail(
            "Expected Phase 5 API handler missing: from koda.control_plane.api import get_release_quality_latest_route",
            pytrace=False,
        )
    manager = MagicMock()
    manager.get_release_quality_latest.return_value = {
        "schema_version": "release_quality.v1",
        "status": "passed",
        "suite_score": 0.93,
    }
    request = _JsonRequest(match_info={"agent_id": "KODA"})

    with patch("koda.control_plane.api._manager", return_value=manager):
        response = await handler(request)

    payload = json.loads(response.text)
    assert payload["schema_version"] == "release_quality.v1"
    assert payload["status"] == "passed"
    manager.get_release_quality_latest.assert_called_once_with("KODA")


@pytest.mark.asyncio
async def test_quality_cockpit_routes_delegate_to_manager() -> None:
    manager = MagicMock()
    manager.get_quality_cockpit_overview.return_value = {
        "schema_version": "quality_cockpit.v1",
        "summary": {},
    }
    manager.get_quality_cockpit_agent.return_value = {
        "schema_version": "quality_cockpit.v1",
        "agent_id": "KODA",
    }
    manager.create_quality_failure_proposal.return_value = {
        "schema_version": "improvement_proposal.v1",
        "proposal_id": "imp_quality",
    }

    with (
        patch("koda.control_plane.api._manager", return_value=manager),
        patch("koda.control_plane.api._authorize_request", return_value=None),
    ):
        overview = await control_plane_api.get_quality_cockpit_overview_route(_JsonRequest())
        agent = await control_plane_api.get_quality_cockpit_agent_route(_JsonRequest(match_info={"agent_id": "KODA"}))
        proposal = await control_plane_api.create_quality_failure_proposal_route(
            _JsonRequest(
                {"agent_id": "KODA", "requested_by": "operator"},
                match_info={"failure_id": "quality-failure:abc"},
            )
        )

    assert json.loads(overview.text)["schema_version"] == "quality_cockpit.v1"
    assert json.loads(agent.text)["agent_id"] == "KODA"
    assert proposal.status == 201
    manager.get_quality_cockpit_overview.assert_called_once_with()
    manager.get_quality_cockpit_agent.assert_called_once_with("KODA")
    manager.create_quality_failure_proposal.assert_called_once_with(
        agent_id="KODA",
        failure_id="quality-failure:abc",
        requested_by="operator",
    )
