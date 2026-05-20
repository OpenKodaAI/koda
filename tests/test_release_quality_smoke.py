from __future__ import annotations

import json
from pathlib import Path

import scripts.eval_smoke as eval_smoke

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "evals"


def test_eval_smoke_passes_clean_release_quality_fixture(capsys) -> None:
    result = eval_smoke.main(["--input", str(FIXTURE_ROOT / "release_quality.v1.pass.json")])

    captured = capsys.readouterr()
    assert result == 0
    assert "eval smoke passed" in captured.out
    assert captured.err == ""


def test_eval_smoke_fails_on_tool_and_policy_regression(capsys) -> None:
    result = eval_smoke.main(["--input", str(FIXTURE_ROOT / "release_quality.v1.regression.json")])

    captured = capsys.readouterr()
    assert result == 1
    assert "tool regression" in captured.err
    assert "policy regression" in captured.err
    assert "package_install" in captured.err


def test_eval_smoke_fails_on_provider_calls_or_raw_trajectory(tmp_path: Path, capsys) -> None:
    payload = json.loads((FIXTURE_ROOT / "release_quality.v1.pass.json").read_text(encoding="utf-8"))
    payload["trajectory_export"]["raw_prompt_included"] = True
    payload["trajectory_export"]["raw_secret_count"] = 1
    payload["eval_runs"][0]["provider_calls"] = 1
    fixture = tmp_path / "bad-release-quality.json"
    fixture.write_text(json.dumps(payload), encoding="utf-8")

    result = eval_smoke.main(["--input", str(fixture)])

    captured = capsys.readouterr()
    assert result == 1
    assert "raw_prompt_included" in captured.err
    assert "raw_secret_count" in captured.err
    assert "made provider calls" in captured.err


def test_eval_smoke_requires_release_blocking_gate_ids(tmp_path: Path, capsys) -> None:
    payload = json.loads((FIXTURE_ROOT / "release_quality.v1.pass.json").read_text(encoding="utf-8"))
    payload["gates"] = [gate for gate in payload["gates"] if gate["id"] != "tool_policy_regression"]
    fixture = tmp_path / "missing-gate.json"
    fixture.write_text(json.dumps(payload), encoding="utf-8")

    result = eval_smoke.main(["--input", str(fixture)])

    captured = capsys.readouterr()
    assert result == 1
    assert "required gate 'tool_policy_regression' is missing" in captured.err


def test_eval_smoke_reports_malformed_input(tmp_path: Path, capsys) -> None:
    fixture = tmp_path / "bad.json"
    fixture.write_text("{not-json", encoding="utf-8")

    result = eval_smoke.main(["--input", str(fixture)])

    captured = capsys.readouterr()
    assert result == 2
    assert "not valid JSON" in captured.err


def test_evaluate_release_quality_requires_release_quality_schema() -> None:
    failures = eval_smoke.evaluate_release_quality({"schema_version": "eval_run.v1"})

    assert any("release_quality.v1" in failure for failure in failures)
    assert any("eval_runs" in failure for failure in failures)
