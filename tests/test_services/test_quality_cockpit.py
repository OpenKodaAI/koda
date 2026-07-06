from __future__ import annotations

from typing import Any

from koda.services.quality_cockpit import (
    QUALITY_COCKPIT_SCHEMA_VERSION,
    RELEASE_BLOCKER_SCHEMA_VERSION,
    build_quality_cockpit,
    build_quality_proposal_payload,
    build_release_blockers,
)


def test_quality_cockpit_aggregates_rows_eval_trends_and_failures() -> None:
    payload: dict[str, Any] = {
        "agent_quality": [
            {
                "agent_id": "koda",
                "entity_id": "KODA",
                "quality_score": 0.91,
                "cost_usd": 0.30,
            }
        ],
        "tool_quality": [
            {
                "entity_id": "read_file",
                "score": 0.45,
                "cost_usd": 0.05,
                "failures": [
                    {
                        "category": "tool_regression",
                        "message": "Expected read_file was missing.",
                        "case_key": "run:KODA:42",
                        "run_graph_node_ids": ["node:tool"],
                    }
                ],
            },
            {
                "entity_id": "read_file",
                "score": 0.55,
                "cost_usd": 0.07,
                "failures": [{"category": "tool_regression", "case_key": "run:KODA:43"}],
            },
        ],
        "model_quality": [
            {"entity_id": "sonnet", "quality_score": 0.88, "cost_usd": 1.20},
            {"entity_id": "haiku", "quality_score": 0.62, "cost_usd": 0.20},
        ],
        "eval_runs": [
            {
                "schema_version": "eval_run.v1",
                "run_id": "eval-run:new",
                "agent_id": "KODA",
                "suite_id": "default",
                "status": "failed",
                "score": 0.73,
                "created_at": "2026-05-19T10:01:00",
                "summary": {
                    "case_count": 2,
                    "passed": 1,
                    "failed": 1,
                    "top_failures": [{"category": "policy_regression", "message": "Policy drift."}],
                },
                "case_results": [
                    {
                        "case_key": "run:KODA:42",
                        "status": "failed",
                        "score": 0.5,
                        "failures": [{"category": "tool_regression"}],
                        "metadata": {"source_run_graph_node_ids": ["node:policy"]},
                    }
                ],
            },
            {
                "schema_version": "eval_run.v1",
                "run_id": "eval-run:old",
                "agent_id": "KODA",
                "suite_id": "default",
                "status": "passed",
                "score": 0.9,
                "created_at": "2026-05-18T10:01:00",
                "summary": {"case_count": 2, "passed": 2, "failed": 0},
            },
        ],
    }

    cockpit = build_quality_cockpit(payload, proposal_limit=2)

    assert cockpit["schema_version"] == QUALITY_COCKPIT_SCHEMA_VERSION
    assert cockpit["agent_id"] == "KODA"
    assert cockpit["summary"]["eval_run_count"] == 2
    assert cockpit["summary"]["failed_entity_count"] >= 2
    assert cockpit["top_failures"][0]["category"] == "tool_regression"
    assert cockpit["top_failures"][0]["failure_id"].startswith("quality-failure:")
    assert cockpit["top_failures"][0]["count"] == 2
    assert cockpit["cost_vs_quality"][0]["entity_id"] == "sonnet"
    assert [trend["run_id"] for trend in cockpit["eval_trends"]] == ["eval-run:old", "eval-run:new"]
    assert len(cockpit["proposal_payloads"]) == 2


def test_quality_cockpit_proposal_payload_is_create_ready_and_offline_only() -> None:
    cockpit = build_quality_cockpit(
        {
            "skill_quality": [
                {
                    "agent_id": "KODA",
                    "skill_id": "release-review",
                    "quality_score": 0.4,
                    "failures": [
                        {
                            "category": "skill_eval",
                            "message": "Skill eval failed.",
                            "case_key": "skill:release-review",
                        }
                    ],
                }
            ]
        },
        proposal_limit=1,
    )

    proposal = cockpit["proposal_payloads"][0]

    assert proposal["source_kind"] == "eval"
    assert proposal["proposal_type"] == "skill"
    assert proposal["status"] == "pending_review"
    assert proposal["validation_plan"]["strategy"] == "offline_replay"
    assert proposal["rollback_plan"]["effects"][0]["effect_kind"] == "ledger_only"
    assert proposal["rollback_plan"]["effects"][0]["after_ref"]["auto_apply"] is False
    assert {"kind": "eval_case", "id": "skill:release-review"} in proposal["evidence_refs"]


def test_quality_cockpit_accepts_flat_list_payloads_deterministically() -> None:
    rows = [
        {"dimension": "model", "entity_id": "haiku", "quality_score": 0.6, "cost_usd": 0.1},
        {"dimension": "model", "entity_id": "sonnet", "quality_score": 0.9, "cost_usd": 0.8},
    ]

    first = build_quality_cockpit(rows, agent_id="KODA")
    second = build_quality_cockpit(rows, agent_id="KODA")

    assert first == second
    assert first["cockpit_id"] == second["cockpit_id"]
    assert [item["entity_id"] for item in first["entities"]] == ["haiku", "sonnet"]


def test_quality_cockpit_aggregates_route_outcomes_and_release_blockers() -> None:
    from koda.services.metrics import RELEASE_BLOCKERS

    blocker_metric = RELEASE_BLOCKERS.labels(
        agent_id="KODA",
        gate_id="run_graph_completeness",
        severity="high",
        status="failing",
    )
    cockpit = build_quality_cockpit(
        {
            "route_outcomes": [
                {
                    "schema_version": "route_outcome.v1",
                    "outcome_id": "route-outcome:1",
                    "agent_id": "FE",
                    "route_source": "semantic",
                    "status": "success",
                    "latency_ms": 1000,
                    "cost_usd": 0.1,
                    "run_graph_node_id": "agent_request:1",
                },
                {
                    "schema_version": "route_outcome.v1",
                    "outcome_id": "route-outcome:2",
                    "agent_id": "FE",
                    "route_source": "semantic",
                    "status": "timeout",
                    "timeout": True,
                    "latency_ms": 90000,
                    "cost_usd": 0.4,
                    "run_graph_node_id": "dependency_call:timeout",
                },
            ],
            "release_quality": {
                "schema_version": "release_quality.v1",
                "release_quality_id": "release-quality:KODA:1",
                "gates": {
                    "run_graph_completeness": {
                        "status": "failed",
                        "summary": "Missing synthesis path.",
                        "failures": [
                            {
                                "category": "missing_synthesis_path",
                                "run_graph_node_ids": ["coordinator_synthesis:1"],
                            }
                        ],
                    }
                },
            },
        },
        agent_id="KODA",
    )

    assert cockpit["route_quality_history"][0]["route_source"] == "semantic"
    assert cockpit["route_quality_history"][0]["timeout_rate"] == 0.5
    assert cockpit["groups"][0]["entity_type"] == "route_source"
    assert cockpit["release_blockers"][0]["schema_version"] == RELEASE_BLOCKER_SCHEMA_VERSION
    assert cockpit["release_blockers"][0]["gate_id"] == "run_graph_completeness"
    assert {"kind": "run_graph_node", "id": "coordinator_synthesis:1"} in cockpit["release_blockers"][0][
        "evidence_refs"
    ]
    if hasattr(blocker_metric, "_value"):
        after = float(blocker_metric._value.get())
        assert after == 1


def test_release_blocker_view_is_derived_from_release_quality_only() -> None:
    blockers = build_release_blockers(
        {
            "schema_version": "release_quality.v1",
            "release_quality_id": "release-quality:ATLAS:1",
            "gate_items": [
                {"id": "offline_eval", "status": "passed", "summary": "green"},
                {
                    "id": "trajectory_export_redaction",
                    "status": "failed",
                    "summary": "Export is not redacted.",
                },
                {
                    "id": "browser_authenticated_e2e",
                    "status": "blocked",
                    "message": "No browser credentials.",
                },
            ],
        }
    )

    assert [item["gate_id"] for item in blockers] == [
        "trajectory_export_redaction",
        "browser_authenticated_e2e",
    ]
    assert blockers[0]["next_action"] == "Create a redacted trajectory_export.v1 and rerun release quality."
    assert blockers[1]["proposal_action_available"] is False


def test_build_quality_proposal_payload_maps_failure_category_to_contract() -> None:
    proposal = build_quality_proposal_payload(
        {
            "dimension": "tool",
            "entity_id": "shell_execute",
            "category": "policy_regression",
            "count": 3,
            "run_ids": ["eval-run:1"],
            "case_keys": ["case:1"],
            "run_graph_node_ids": ["node:gate"],
        },
        agent_id="KODA",
        cockpit_id="quality-cockpit:KODA:test",
    )

    assert proposal["agent_id"] == "KODA"
    assert proposal["source_ref"] == "quality:tool:shell_execute:policy_regression"
    assert proposal["proposal_type"] == "tool_policy"
    assert proposal["risk_class"] == "medium"
    assert proposal["run_graph_node_ids"] == ["node:gate"]
    assert {"kind": "eval_run", "id": "eval-run:1"} in proposal["evidence_refs"]
