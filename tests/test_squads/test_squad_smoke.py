from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import scripts.squad_smoke as squad_smoke
from koda.services.run_graph import verify_run_graph_completeness

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "evals"


def _fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def test_kat_001_squad_smoke_fixture_covers_delivery_and_run_graph() -> None:
    payload = _fixture("squad_smoke.v1.json")

    failures = squad_smoke.evaluate_squad_smoke(payload)
    graph_report = verify_run_graph_completeness(
        payload["run_graph"],
        scenario="squad",
        requires_partial_timeout=True,
        require_synthesis_path=True,
    )

    assert failures == []
    assert graph_report["status"] == "passed"
    assert {"agent_request", "reply_obligation", "squad_reply", "child_run", "coordinator_synthesis"} <= set(
        graph_report["present_node_types"]
    )


def test_squad_smoke_fails_when_reply_obligation_is_missing() -> None:
    payload = _fixture("squad_smoke.v1.json")
    payload["delivery"]["events"] = [
        event for event in payload["delivery"]["events"] if event["event_type"] != "reply_obligation"
    ]

    failures = squad_smoke.evaluate_squad_smoke(payload)

    assert any("reply obligation" in failure for failure in failures)


def test_squad_smoke_fails_when_mention_target_and_obligation_diverge() -> None:
    payload = deepcopy(_fixture("squad_smoke.v1.json"))
    payload["delivery"]["route_decision"]["targets"] = ["QA"]
    payload["delivery"]["route_decision"]["explicit_mentions"] = ["QA"]

    failures = squad_smoke.evaluate_squad_smoke(payload)

    assert any("target must match" in failure for failure in failures)


def test_squad_smoke_fails_without_in_reply_to_evidence() -> None:
    payload = deepcopy(_fixture("squad_smoke.v1.json"))
    for event in payload["delivery"]["events"]:
        if event["event_type"] == "squad_reply":
            event["payload"].pop("in_reply_to")

    failures = squad_smoke.evaluate_squad_smoke(payload)

    assert any("in_reply_to" in failure for failure in failures)


def test_squad_smoke_fails_when_synthesis_omits_timeout_disclosure() -> None:
    payload = deepcopy(_fixture("squad_smoke.v1.json"))
    for event in payload["delivery"]["events"]:
        if event["event_type"] == "coordinator_synthesis":
            event["payload"]["timeout_declared"] = False
            event["payload"]["timed_out_agent_ids"] = []

    failures = squad_smoke.evaluate_squad_smoke(payload)

    assert any("declare timed out" in failure for failure in failures)


def test_squad_smoke_fails_without_task_result_strategy() -> None:
    payload = deepcopy(_fixture("squad_smoke.v1.json"))
    payload["delivery"]["route_decision"]["final_response_strategy"] = "direct"

    failures = squad_smoke.evaluate_squad_smoke(payload)

    assert any("final_response_strategy" in failure for failure in failures)


def test_squad_smoke_fails_when_graph_lacks_result_edge_to_synthesis() -> None:
    payload = deepcopy(_fixture("squad_smoke.v1.json"))
    payload["run_graph"]["edges"] = [
        edge for edge in payload["run_graph"]["edges"] if edge["to_node_id"] != "synthesis:7"
    ]

    failures = squad_smoke.evaluate_squad_smoke(payload)

    assert any("coordinator synthesis" in failure or "result/timeout edge" in failure for failure in failures)


def test_squad_smoke_execute_fails_closed_without_dsn(monkeypatch, capsys) -> None:
    monkeypatch.delenv("POSTGRES_TEST_DSN", raising=False)

    result = squad_smoke.main(["--input", str(FIXTURE_ROOT / "squad_smoke.v1.json"), "--execute"])

    captured = capsys.readouterr()
    assert result == 2
    assert "POSTGRES_TEST_DSN" in captured.err


def test_squad_smoke_script_passes_fixture(capsys) -> None:
    result = squad_smoke.main(["--input", str(FIXTURE_ROOT / "squad_smoke.v1.json")])

    assert result == 0
    assert "squad smoke passed" in capsys.readouterr().out
