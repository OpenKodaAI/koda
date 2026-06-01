#!/usr/bin/env python3
"""Offline release-quality smoke gate for Phase 5 eval fixtures.

The script is deliberately deterministic: it reads a recorded
`release_quality.v1` JSON payload and fails if the suite status, redaction gate,
tool-call expectations, or policy decisions regress.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

RELEASE_QUALITY_SCHEMA_VERSION = "release_quality.v1"
EVAL_RUN_SCHEMA_VERSION = "eval_run.v1"
TRAJECTORY_EXPORT_SCHEMA_VERSION = "trajectory_export.v1"
REQUIRED_GATE_IDS = frozenset(
    {
        "deterministic_eval_suite",
        "trajectory_export_redaction",
        "tool_policy_regression",
        "run_graph_completeness",
        "squad_golden_quality",
    }
)


class EvalSmokeError(RuntimeError):
    """Raised when the release-quality smoke input is malformed."""


def read_payload(path: Path) -> dict[str, Any]:
    """Read a release-quality JSON payload."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise EvalSmokeError(f"Smoke input not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise EvalSmokeError(f"Smoke input is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise EvalSmokeError("Smoke input must be a JSON object")
    return payload


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _tool_ids(calls: Iterable[Any]) -> set[str]:
    ids: set[str] = set()
    for call in calls:
        if isinstance(call, dict) and call.get("tool_id"):
            ids.add(str(call["tool_id"]))
    return ids


def _policy_decisions(decisions: Iterable[Any]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for decision in decisions:
        if isinstance(decision, dict) and decision.get("tool_id"):
            normalized[str(decision["tool_id"])] = str(decision.get("decision") or "")
    return normalized


def evaluate_release_quality(payload: dict[str, Any], *, min_suite_score: float = 0.85) -> list[str]:
    """Return smoke failures for a `release_quality.v1` payload."""
    failures: list[str] = []
    if payload.get("schema_version") != RELEASE_QUALITY_SCHEMA_VERSION:
        failures.append(
            f"schema_version must be {RELEASE_QUALITY_SCHEMA_VERSION!r}; got {payload.get('schema_version')!r}"
        )
    if payload.get("status") != "passed":
        failures.append(f"release quality status is {payload.get('status')!r}, expected 'passed'")

    suite_score = float(payload.get("suite_score") or 0.0)
    if suite_score < min_suite_score:
        failures.append(f"suite_score {suite_score:.2f} is below required {min_suite_score:.2f}")

    seen_gate_ids: set[str] = set()
    for gate in _as_list(payload.get("gates")):
        if not isinstance(gate, dict):
            failures.append("gate entries must be objects")
            continue
        gate_id = str(gate.get("id") or "")
        if gate_id:
            seen_gate_ids.add(gate_id)
        if gate.get("status") != "passed":
            failures.append(f"gate {gate.get('id')!r} failed: {gate.get('message') or 'no message'}")
    for missing_gate_id in sorted(REQUIRED_GATE_IDS - seen_gate_ids):
        failures.append(f"required gate {missing_gate_id!r} is missing")

    trajectory = payload.get("trajectory_export")
    if not isinstance(trajectory, dict):
        failures.append("trajectory_export must be present")
    else:
        if trajectory.get("schema_version") != TRAJECTORY_EXPORT_SCHEMA_VERSION:
            failures.append("trajectory_export.schema_version must be 'trajectory_export.v1'")
        if trajectory.get("replay_mode") != "offline":
            failures.append("trajectory_export.replay_mode must be 'offline'")
        if trajectory.get("raw_prompt_included") is not False:
            failures.append("trajectory_export.raw_prompt_included must be false")
        if int(trajectory.get("raw_secret_count") or 0) != 0:
            failures.append("trajectory_export.raw_secret_count must be 0")

    eval_runs = _as_list(payload.get("eval_runs"))
    if not eval_runs:
        failures.append("eval_runs must include at least one deterministic run")
    for run in eval_runs:
        if not isinstance(run, dict):
            failures.append("eval_runs entries must be objects")
            continue
        if run.get("schema_version") != EVAL_RUN_SCHEMA_VERSION:
            failures.append(f"eval run {run.get('run_id')!r} must use schema_version 'eval_run.v1'")
        if run.get("replay_mode") != "offline":
            failures.append(f"eval run {run.get('run_id')!r} must use offline replay")
        if int(run.get("provider_calls") or 0) != 0:
            failures.append(f"eval run {run.get('run_id')!r} made provider calls")
        if run.get("status") != "passed":
            failures.append(f"eval run {run.get('run_id')!r} status is {run.get('status')!r}")
        for case in _as_list(run.get("case_results")):
            failures.extend(_evaluate_case_result(case))
    return failures


def _evaluate_case_result(case: Any) -> list[str]:
    if not isinstance(case, dict):
        return ["case_results entries must be objects"]
    failures: list[str] = []
    case_id = str(case.get("case_id") or "<unknown>")
    expected = case.get("expectations") if isinstance(case.get("expectations"), dict) else {}
    observed = case.get("observed") if isinstance(case.get("observed"), dict) else {}
    expected_tools = _tool_ids(_as_list(expected.get("tool_calls") if isinstance(expected, dict) else None))
    observed_tools = _tool_ids(_as_list(observed.get("tool_calls") if isinstance(observed, dict) else None))
    missing_tools = sorted(expected_tools - observed_tools)
    if missing_tools:
        failures.append(f"case {case_id} tool regression: missing expected tools {', '.join(missing_tools)}")

    expected_policy = _policy_decisions(
        _as_list(expected.get("policy_decisions") if isinstance(expected, dict) else None)
    )
    observed_policy = _policy_decisions(
        _as_list(observed.get("policy_decisions") if isinstance(observed, dict) else None)
    )
    for tool_id, expected_decision in sorted(expected_policy.items()):
        observed_decision = observed_policy.get(tool_id)
        if observed_decision != expected_decision:
            failures.append(
                f"case {case_id} policy regression: {tool_id} expected "
                f"{expected_decision!r}, observed {observed_decision!r}"
            )
    if case.get("status") != "passed":
        failures.append(f"case {case_id} status is {case.get('status')!r}")
    return failures


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Path to a release_quality.v1 JSON payload.")
    parser.add_argument(
        "--min-suite-score",
        type=float,
        default=0.85,
        help="Minimum average suite score required for release quality.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        failures = evaluate_release_quality(read_payload(args.input), min_suite_score=args.min_suite_score)
    except EvalSmokeError as exc:
        print(f"eval smoke input error: {exc}", file=sys.stderr)
        return 2
    if failures:
        print("eval smoke failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("eval smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
