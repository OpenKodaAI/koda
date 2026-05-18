from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "evals"

EXPECTED_PHASE5_IMPORTS = (
    "EVAL_CASE_SCHEMA_VERSION",
    "EVAL_RUN_SCHEMA_VERSION",
    "TRAJECTORY_EXPORT_SCHEMA_VERSION",
    "RELEASE_QUALITY_SCHEMA_VERSION",
    "OfflineEvalResult",
    "build_eval_case_from_run",
    "evaluate_case_offline",
    "build_eval_run_batch",
    "build_trajectory_export",
    "build_release_quality_report",
)


def _json_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def _payload(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "model_dump"):
        return value.model_dump()
    assert isinstance(value, dict)
    return value


def _phase5_evals_module() -> Any:
    try:
        return import_module("koda.services.evals")
    except ModuleNotFoundError as exc:
        if exc.name == "koda.services.evals":
            pytest.fail(
                "Expected Phase 5 backend import is missing: "
                "from koda.services.evals import " + ", ".join(EXPECTED_PHASE5_IMPORTS),
                pytrace=False,
            )
        raise


def test_phase5_fixture_contracts_are_versioned_and_redacted() -> None:
    expected_versions = {
        "eval_case.v1.json": "eval_case.v1",
        "eval_run.v1.pass.json": "eval_run.v1",
        "eval_run.v1.tool_policy_regression.json": "eval_run.v1",
        "release_quality.v1.pass.json": "release_quality.v1",
        "release_quality.v1.regression.json": "release_quality.v1",
    }
    for filename, version in expected_versions.items():
        assert _json_fixture(filename)["schema_version"] == version

    lines = [
        json.loads(line)
        for line in (FIXTURE_ROOT / "trajectory_export.v1.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert lines
    assert all(line["schema_version"] == "trajectory_export.v1" for line in lines)
    assert all(line.get("redaction", {}).get("raw_prompt_included") is not True for line in lines)

    redaction = _json_fixture("redaction.v1.json")
    searchable_payload = json.dumps(redaction["payload"], sort_keys=True)
    for forbidden in redaction["forbidden_strings"]:
        assert forbidden not in searchable_payload
    assert "[REDACTED]" in searchable_payload


def test_expected_phase5_evals_module_imports_are_public() -> None:
    evals = _phase5_evals_module()

    missing = [name for name in EXPECTED_PHASE5_IMPORTS if not hasattr(evals, name)]

    assert missing == []
    assert evals.EVAL_CASE_SCHEMA_VERSION == "eval_case.v1"
    assert evals.EVAL_RUN_SCHEMA_VERSION == "eval_run.v1"
    assert evals.TRAJECTORY_EXPORT_SCHEMA_VERSION == "trajectory_export.v1"
    assert evals.RELEASE_QUALITY_SCHEMA_VERSION == "release_quality.v1"


def test_build_eval_case_from_run_consumes_run_graph_and_replay_contracts() -> None:
    evals = _phase5_evals_module()
    expected_case = _json_fixture("eval_case.v1.json")
    run_graph = {
        "schema_version": "run_graph.v1",
        "graph_id": "run:KODA:7101:attempt:1",
        "agent_id": "KODA",
        "task_id": 7101,
        "attempt": 1,
        "nodes": [
            {
                "node_id": "node:model-call",
                "node_type": "model_call",
                "status": "completed",
                "payload": {"prompt_hash": expected_case["input"]["hash"]},
            }
        ],
        "edges": [],
        "summary": {"status": "completed"},
    }
    replay_bundle = {
        "schema_version": "run_replay.v1",
        "replay_mode": "offline",
        "inputs": {"query_preview": expected_case["input"]["preview"]},
        "provider_calls_allowed": False,
    }
    execution = {
        "id": 91,
        "agent_id": "KODA",
        "task_id": 7101,
        "status": "completed",
        "query_text": expected_case["input"]["preview"],
        "response_text": "Release checks passed.",
        "feedback_status": "promote",
        "trace": {"tools": [{"tool": "read_file", "success": True}]},
        "answer_gate_status": "passed",
    }

    case = _payload(
        evals.build_eval_case_from_run(
            agent_id="KODA",
            task_id=7101,
            execution=execution,
            run_graph=run_graph,
            replay=replay_bundle,
            payload={
                "expected_tool_ids": expected_case["expected_outcome"]["required_tools"],
                "expected_policy_codes": ["package_install:denied"],
                "reference_answer": "Release checks passed.",
            },
        )
    )

    assert case["schema_version"] == "eval_case.v1"
    assert case["agent_id"] == "KODA"
    assert case["source_task_id"] == 7101
    assert case["metadata"]["source_run_graph_id"] == "run:KODA:7101:attempt:1"
    assert case["metadata"]["source_replay_mode"] == "offline"
    assert case["metadata"]["redaction"]["raw_prompt_stored"] is False


def test_deterministic_suite_reports_tool_and_policy_regressions() -> None:
    evals = _phase5_evals_module()
    case = {
        "schema_version": "eval_case.v1",
        "case_key": "run:KODA:7101",
        "agent_id": "KODA",
        "source_task_id": 7101,
        "metadata": {
            "expected_tool_ids": ["read_file"],
            "source_tool_ids": ["shell_execute"],
            "expected_policy_codes": ["package_install:denied"],
            "source_policy_codes": ["package_install:allowed"],
            "source_status": "completed",
            "source_replay_mode": "offline",
        },
    }

    result = _payload(
        evals.build_eval_run_batch(
            agent_id="KODA",
            suite_id="phase5-release-smoke",
            cases=[case],
        )
    )

    encoded = json.dumps(result, sort_keys=True)
    assert result["schema_version"] == "eval_run.v1"
    assert result["status"] == "failed"
    assert result["strategy"] == "offline_replay"
    assert "tool_regression" in encoded
    assert "policy_regression" in encoded


def test_trajectory_export_jsonl_is_offline_and_redacted() -> None:
    evals = _phase5_evals_module()
    replay = {
        "schema_version": "run_replay.v1",
        "replay_mode": "offline",
        "inputs": {"query_preview": "Deploy with token sk-live-secret"},
        "steps": [
            {
                "node_id": "node:model-call",
                "type": "model_call",
                "label": "Model call",
                "status": "completed",
                "notes": "Replay uses recorded output only.",
            }
        ],
    }
    graph = {
        "schema_version": "run_graph.v1",
        "graph_id": "run:KODA:7101:attempt:1",
        "agent_id": "KODA",
        "task_id": 7101,
        "attempt": 1,
        "nodes": [
            {
                "node_id": "node:model-call",
                "node_type": "model_call",
                "status": "completed",
                "summary": "Model call",
                "payload": {
                    "api_key": "sk-live-secret",
                    "authorization": "Bearer abcdef",
                    "prompt_hash": "sha256:abc",
                },
            }
        ],
        "edges": [],
    }

    export = evals.build_trajectory_export(
        agent_id="KODA",
        task_id=7101,
        execution={"status": "completed", "query_text": "Deploy with token sk-live-secret"},
        run_graph=graph,
        replay=replay,
    )
    lines = [json.loads(line) for line in str(export["jsonl"]).splitlines() if line.strip()]
    encoded = json.dumps(lines, sort_keys=True)

    assert lines
    assert all(line["schema_version"] == "trajectory_export.v1" for line in lines)
    assert "sk-live-secret" not in encoded
    assert "Bearer abcdef" not in encoded
    assert "raw_prompt" not in encoded
    assert "[REDACTED]" in encoded or "sha256:" in encoded


def test_release_quality_report_aggregates_eval_export_and_gate_status() -> None:
    evals = _phase5_evals_module()
    pass_run = evals.build_eval_run_batch(
        agent_id="KODA",
        suite_id="phase5-release-smoke",
        cases=[
            {
                "schema_version": "eval_case.v1",
                "case_key": "run:KODA:7101",
                "metadata": {
                    "expected_tool_ids": ["read_file"],
                    "source_tool_ids": ["read_file"],
                    "expected_policy_codes": ["package_install:denied"],
                    "source_policy_codes": ["package_install:denied"],
                    "source_status": "completed",
                    "source_replay_mode": "offline",
                },
            }
        ],
    )

    report = _payload(
        evals.build_release_quality_report(
            agent_id="KODA",
            latest_run=pass_run,
            recent_runs=[pass_run],
            trajectory_exports=[
                {
                    "schema_version": "trajectory_export.v1",
                    "replay_mode": "offline",
                    "redaction_applied": True,
                    "record_count": 3,
                }
            ],
        )
    )

    assert report["schema_version"] == "release_quality.v1"
    assert report["status"] == "passed"
    assert set(report["gates"]) >= {
        "offline_eval",
        "trajectory_export_redaction",
        "provider_calls_disabled",
    }


def test_release_quality_report_fails_when_trajectory_export_is_not_redacted() -> None:
    evals = _phase5_evals_module()
    report = _payload(
        evals.build_release_quality_report(
            agent_id="KODA",
            latest_run={"schema_version": "eval_run.v1", "status": "passed", "score": 0.93},
            recent_runs=[],
            trajectory_exports=[
                {
                    "schema_version": "trajectory_export.v1",
                    "replay_mode": "offline",
                    "redaction_applied": False,
                    "record_count": 3,
                }
            ],
        )
    )

    assert report["schema_version"] == "release_quality.v1"
    assert report["status"] == "failed"
    assert report["gates"]["trajectory_export_redaction"]["status"] == "failed"
