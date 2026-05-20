"""Phase 5 eval, trajectory export, and release quality contracts.

The helpers in this module are deliberately offline and deterministic. They
consume execution traces, RunGraph/replay payloads, and curated metadata that
already exist in Koda; they never call a provider while building release gates.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from koda.services.run_graph import verify_run_graph_completeness
from koda.services.runtime.redaction import redact_value

EVAL_CASE_SCHEMA_VERSION = "eval_case.v1"
EVAL_RUN_SCHEMA_VERSION = "eval_run.v1"
TRAJECTORY_EXPORT_SCHEMA_VERSION = "trajectory_export.v1"
TRAJECTORY_EXPORT_MANIFEST_SCHEMA_VERSION = "trajectory_export_manifest.v1"
RELEASE_QUALITY_SCHEMA_VERSION = "release_quality.v1"
OFFLINE_REPLAY_STRATEGY = "offline_replay"

_MAX_PREVIEW_CHARS = 1000
_MIN_PASS_SCORE = 0.8


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)


def stable_digest(value: Any, *, length: int = 16) -> str:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8"), usedforsecurity=False).hexdigest()
    return digest[: max(8, int(length))]


def as_record(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


def as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def compact_strings(values: Iterable[Any]) -> list[str]:
    return [text for item in values if (text := str(item or "").strip())]


def safe_preview(value: Any, *, limit: int = _MAX_PREVIEW_CHARS) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def redacted(value: Any) -> Any:
    try:
        return redact_value(value)
    except Exception:
        return _fallback_redact(value)


def _fallback_redact(value: Any, *, key_hint: str = "") -> Any:
    lowered_key = key_hint.lower()
    if any(part in lowered_key for part in ("secret", "token", "password", "credential", "api_key", "auth")):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(key): _fallback_redact(item, key_hint=str(key)) for key, item in value.items()}
    if isinstance(value, list):
        return [_fallback_redact(item, key_hint=key_hint) for item in value]
    if isinstance(value, str):
        lowered = value.lower()
        if any(part in lowered for part in ("bearer ", "api_key=", "token=", "password=", "secret=")):
            return "[REDACTED]"
    return value


def _metric(value: float) -> float:
    return max(0.0, min(1.0, float(value or 0.0)))


def _number_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _node_tool_ids(run_graph: Mapping[str, Any]) -> list[str]:
    tools: list[str] = []
    for node in as_list(run_graph.get("nodes")):
        payload = as_record(as_record(node).get("payload"))
        refs = as_record(as_record(node).get("refs"))
        tool = str(payload.get("tool") or payload.get("tool_id") or refs.get("tool") or refs.get("tool_id") or "")
        if tool:
            tools.append(tool)
    return sorted(set(tools))


def _node_policy_codes(run_graph: Mapping[str, Any]) -> list[str]:
    codes: list[str] = []
    for node in as_list(run_graph.get("nodes")):
        raw = as_record(node)
        if str(raw.get("node_type") or raw.get("type") or "") not in {
            "policy_gate",
            "approval_request",
            "approval_decision",
        }:
            continue
        payload = as_record(raw.get("payload"))
        code = str(payload.get("policy_reason_code") or payload.get("reason_code") or payload.get("decision") or "")
        if code:
            codes.append(code)
    return sorted(set(codes))


def _trace_tools(trace: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [as_record(item) for item in as_list(trace.get("tools")) if isinstance(item, Mapping)]


def _trace_tool_ids(trace: Mapping[str, Any]) -> list[str]:
    return sorted({str(item.get("tool") or item.get("name") or "") for item in _trace_tools(trace) if item})


def _trace_policy_codes(trace: Mapping[str, Any]) -> list[str]:
    codes: set[str] = set()
    for item in _trace_tools(trace):
        metadata = as_record(item.get("metadata"))
        code = str(metadata.get("policy_reason_code") or metadata.get("policy_rule_id") or "")
        if code:
            codes.add(code)
    return sorted(codes)


def _status_from_score(score: float) -> str:
    return "passed" if score >= _MIN_PASS_SCORE else "failed"


def build_eval_case_from_run(
    *,
    agent_id: str,
    task_id: int,
    execution: Mapping[str, Any],
    run_graph: Mapping[str, Any] | None = None,
    replay: Mapping[str, Any] | None = None,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a versioned draft eval case from a real execution detail payload."""

    request = as_record(payload)
    graph_payload = as_record(run_graph or execution.get("run_graph"))
    replay_payload = as_record(replay or execution.get("run_replay"))
    trace_payload = as_record(execution.get("trace"))
    query_text = str(request.get("query_text") or execution.get("query_text") or "").strip()
    response_text = str(request.get("reference_answer") or execution.get("response_text") or "").strip()
    source_tools = _node_tool_ids(graph_payload) or _trace_tool_ids(trace_payload)
    source_policy_codes = _node_policy_codes(graph_payload) or _trace_policy_codes(trace_payload)
    expected_tools = compact_strings(request.get("expected_tool_ids") or source_tools)
    expected_policy = compact_strings(request.get("expected_policy_codes") or source_policy_codes)
    expected_sources = compact_strings(request.get("expected_sources") or [])
    expected_layers = compact_strings(request.get("expected_layers") or [])
    case_key = str(request.get("case_key") or f"run:{agent_id.upper()}:{int(task_id)}").strip()
    metadata = {
        "schema_version": EVAL_CASE_SCHEMA_VERSION,
        "source": "execution_run",
        "source_task_id": int(task_id),
        "source_agent_id": agent_id.upper(),
        "source_status": str(execution.get("status") or ""),
        "source_run_graph_id": graph_payload.get("graph_id") or graph_payload.get("run_id"),
        "source_run_graph_node_ids": compact_strings(
            [
                as_record(node).get("id") or as_record(node).get("node_id")
                for node in as_list(graph_payload.get("nodes"))
            ]
        ),
        "source_replay_mode": replay_payload.get("replay_mode") or replay_payload.get("mode") or "offline",
        "source_tool_ids": source_tools,
        "source_policy_codes": source_policy_codes,
        "expected_tool_ids": expected_tools,
        "expected_policy_codes": expected_policy,
        "response_preview": safe_preview(response_text),
        "query_hash": stable_digest(query_text),
        "response_hash": stable_digest(response_text),
        "trajectory_hash": stable_digest({"graph": graph_payload, "replay": replay_payload}),
        "redaction": {"raw_prompt_stored": False, "raw_secret_stored": False},
    }
    metadata.update(as_record(request.get("metadata")))
    return {
        "schema_version": EVAL_CASE_SCHEMA_VERSION,
        "case_key": case_key,
        "agent_id": agent_id.upper(),
        "source_task_id": int(task_id),
        "query_text": safe_preview(redacted(query_text)),
        "task_kind": str(request.get("task_kind") or execution.get("task_kind") or "general"),
        "project_key": str(request.get("project_key") or ""),
        "environment": str(request.get("environment") or ""),
        "team": str(request.get("team") or ""),
        "modality": str(request.get("modality") or "text"),
        "expected_sources": expected_sources,
        "expected_layers": expected_layers,
        "reference_answer": safe_preview(redacted(response_text)),
        "status": str(request.get("status") or "draft"),
        "gold_source_kind": str(request.get("gold_source_kind") or "human_corrected_task"),
        "metadata": metadata,
    }


@dataclass(slots=True)
class OfflineEvalResult:
    case_key: str
    status: str
    score: float
    metrics: dict[str, float]
    failures: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": EVAL_RUN_SCHEMA_VERSION,
            "case_key": self.case_key,
            "status": self.status,
            "score": self.score,
            "metrics": self.metrics,
            "failures": self.failures,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }


def evaluate_case_offline(case: Mapping[str, Any]) -> OfflineEvalResult:
    """Evaluate a stored case using deterministic metadata only."""

    metadata = as_record(case.get("metadata"))
    expected_tools = set(compact_strings(metadata.get("expected_tool_ids") or []))
    source_tools = set(compact_strings(metadata.get("source_tool_ids") or []))
    expected_policy = set(compact_strings(metadata.get("expected_policy_codes") or []))
    source_policy = set(compact_strings(metadata.get("source_policy_codes") or []))
    source_status = str(metadata.get("source_status") or "").lower()
    replay_mode = str(metadata.get("source_replay_mode") or "offline").lower()
    failures: list[dict[str, Any]] = []
    warnings: list[str] = []

    tool_score = 1.0 if not expected_tools else len(expected_tools & source_tools) / len(expected_tools)
    policy_score = 1.0 if not expected_policy else len(expected_policy & source_policy) / len(expected_policy)
    replay_score = 1.0 if replay_mode == "offline" else 0.0
    terminal_score = 1.0 if source_status in {"completed", "failed", "cancelled"} else 0.0

    if tool_score < 1.0:
        failures.append(
            {
                "category": "tool_regression",
                "message": "Expected tool ids were not present in the source trajectory.",
                "expected": sorted(expected_tools),
                "actual": sorted(source_tools),
            }
        )
    if policy_score < 1.0:
        failures.append(
            {
                "category": "policy_regression",
                "message": "Expected policy decisions were not present in the source trajectory.",
                "expected": sorted(expected_policy),
                "actual": sorted(source_policy),
            }
        )
    if replay_score < 1.0:
        failures.append(
            {
                "category": "replay_unavailable",
                "message": "Case does not carry an offline replay trajectory.",
                "expected": "offline",
                "actual": replay_mode or "missing",
            }
        )
    if terminal_score < 1.0:
        warnings.append("Source run was not terminal when the eval case was created.")

    task_success_proxy = _metric(
        (tool_score * 0.4) + (policy_score * 0.25) + (replay_score * 0.25) + (terminal_score * 0.1)
    )
    metrics = {
        "tool_match_rate": _metric(tool_score),
        "policy_match_rate": _metric(policy_score),
        "offline_replay_rate": _metric(replay_score),
        "terminal_state_rate": _metric(terminal_score),
        "task_success_proxy": task_success_proxy,
    }
    return OfflineEvalResult(
        case_key=str(case.get("case_key") or ""),
        status=_status_from_score(task_success_proxy),
        score=task_success_proxy,
        metrics=metrics,
        failures=failures,
        warnings=warnings,
        metadata={
            "schema_version": EVAL_RUN_SCHEMA_VERSION,
            "strategy": OFFLINE_REPLAY_STRATEGY,
            "source_task_id": case.get("source_task_id"),
            "source_run_graph_id": metadata.get("source_run_graph_id"),
            "source_run_graph_node_ids": compact_strings(metadata.get("source_run_graph_node_ids") or []),
        },
    )


def compare_eval_quality_variants(case: Mapping[str, Any]) -> dict[str, Any]:
    """Compare fixture-backed single-agent and squad variants deterministically."""

    metadata = as_record(case.get("metadata"))
    expected_terms = set(
        compact_strings(as_list(metadata.get("expected_quality_terms") or case.get("expected_quality_terms")))
    )
    thresholds = as_record(metadata.get("thresholds") or case.get("thresholds"))
    squad_min_quality = float(thresholds.get("squad_min_quality_score") or _MIN_PASS_SCORE)
    min_quality_delta = float(thresholds.get("min_quality_delta") or 0.25)
    variants = [as_record(item) for item in as_list(metadata.get("quality_variants") or case.get("quality_variants"))]
    results: list[dict[str, Any]] = []
    for variant in variants:
        variant_id = str(variant.get("id") or variant.get("variant_id") or "")
        kind = str(variant.get("kind") or variant_id)
        observed_terms = set(
            compact_strings(as_list(variant.get("observed_quality_terms") or variant.get("quality_terms")))
        )
        covered_terms = expected_terms & observed_terms
        coverage_score = 1.0 if not expected_terms else len(covered_terms) / len(expected_terms)
        evidence_refs = as_record(variant.get("evidence_refs"))
        run_graph = as_record(variant.get("run_graph"))
        nodes = [as_record(item) for item in as_list(run_graph.get("nodes"))]
        node_ids = {
            str(node.get("node_id") or node.get("id") or "") for node in nodes if node.get("node_id") or node.get("id")
        }
        event_ids = {
            str(event.get("event_id") or f"event:{event.get('event_type')}")
            for event in (as_record(item) for item in as_list(variant.get("delivery_events")))
            if event.get("event_id") or event.get("event_type")
        }
        valid_refs = node_ids | event_ids
        resolved_terms: list[str] = []
        missing_evidence_terms: list[str] = []
        for term in sorted(covered_terms):
            refs = compact_strings(as_list(evidence_refs.get(term)))
            if refs and all(ref in valid_refs for ref in refs):
                resolved_terms.append(term)
            else:
                missing_evidence_terms.append(term)
        evidence_score = 1.0 if not covered_terms else len(resolved_terms) / len(covered_terms)
        requires_partial_timeout = "partial_timeout_disclosed" in observed_terms
        graph_report = verify_run_graph_completeness(
            run_graph,
            scenario="squad" if kind == "squad" else "single_agent",
            requires_partial_timeout=requires_partial_timeout,
            require_synthesis_path=kind == "squad",
        )
        synthesis_score = 1.0 if graph_report.get("status") == "passed" else 0.0
        quality_score = _metric((coverage_score * 0.55) + (evidence_score * 0.30) + (synthesis_score * 0.15))
        provider_calls = int(variant.get("provider_calls") or 0)
        variant_status = (
            "passed"
            if quality_score >= _MIN_PASS_SCORE and provider_calls == 0 and not missing_evidence_terms
            else "failed"
        )
        if graph_report.get("status") != "passed":
            variant_status = "failed"
        results.append(
            {
                "id": variant_id,
                "kind": kind,
                "status": variant_status,
                "coverage_score": _metric(coverage_score),
                "evidence_score": _metric(evidence_score),
                "synthesis_score": _metric(synthesis_score),
                "quality_score": _metric(quality_score),
                "observed_quality_terms": sorted(observed_terms),
                "missing_quality_terms": sorted(expected_terms - observed_terms),
                "missing_evidence_terms": missing_evidence_terms,
                "run_graph_id": variant.get("run_graph_id") or "",
                "run_graph_completeness": graph_report,
                "cost_usd": _number_or_none(variant.get("cost_usd")),
                "duration_ms": _number_or_none(variant.get("duration_ms")),
                "provider_calls": provider_calls,
            }
        )

    winner = max(results, key=lambda item: (float(item["quality_score"]), str(item["id"])), default=None)
    by_id = {str(item["id"]): item for item in results}
    squad = by_id.get("squad")
    single = by_id.get("single_agent")
    quality_delta = (
        _metric(float(squad["quality_score"]) - float(single["quality_score"]))
        if squad is not None and single is not None
        else 0.0
    )
    cost_delta_usd = None
    duration_delta_ms = None
    if squad is not None and single is not None:
        squad_cost = _number_or_none(squad.get("cost_usd"))
        single_cost = _number_or_none(single.get("cost_usd"))
        if squad_cost is not None and single_cost is not None:
            cost_delta_usd = round(squad_cost - single_cost, 6)
        squad_duration = _number_or_none(squad.get("duration_ms"))
        single_duration = _number_or_none(single.get("duration_ms"))
        if squad_duration is not None and single_duration is not None:
            duration_delta_ms = round(squad_duration - single_duration, 3)
    status = (
        "passed"
        if squad is not None
        and single is not None
        and winner is not None
        and winner["id"] == "squad"
        and quality_delta >= min_quality_delta
        and float(squad.get("quality_score") or 0.0) >= squad_min_quality
        and str(squad.get("status") or "") == "passed"
        and int(squad.get("provider_calls") or 0) == 0
        and int(single.get("provider_calls") or 0) == 0
        else "failed"
    )
    return {
        "schema_version": EVAL_RUN_SCHEMA_VERSION,
        "case_key": str(case.get("case_key") or ""),
        "status": status,
        "winner": winner["id"] if winner else "",
        "quality_delta": quality_delta,
        "thresholds": {
            "squad_min_quality_score": _metric(squad_min_quality),
            "min_quality_delta": _metric(min_quality_delta),
        },
        "cost_delta_usd": cost_delta_usd,
        "duration_delta_ms": duration_delta_ms,
        "expected_quality_terms": sorted(expected_terms),
        "variants": results,
        "metadata": {"strategy": "fixture_golden_quality_comparison"},
    }


def build_eval_run_batch(
    *,
    agent_id: str,
    cases: list[Mapping[str, Any]],
    suite_id: str = "default",
    requested_by: str | None = None,
) -> dict[str, Any]:
    results = [evaluate_case_offline(case).to_dict() for case in cases]
    passed = sum(1 for result in results if result["status"] == "passed")
    failed = sum(1 for result in results if result["status"] == "failed")
    total = len(results)
    score = sum(float(result.get("score") or 0.0) for result in results) / total if total else 0.0
    status = "passed" if total > 0 and failed == 0 and score >= _MIN_PASS_SCORE else "failed"
    generated_at = now_iso()
    run_seed = {"suite": suite_id, "cases": [case.get("case_key") for case in cases], "at": generated_at}
    run_id = f"eval-run:{agent_id.upper()}:{stable_digest(run_seed, length=14)}"
    top_failures = [failure for result in results for failure in as_list(result.get("failures"))][:20]
    return {
        "schema_version": EVAL_RUN_SCHEMA_VERSION,
        "run_id": run_id,
        "agent_id": agent_id.upper(),
        "suite_id": suite_id,
        "strategy": OFFLINE_REPLAY_STRATEGY,
        "status": status,
        "score": _metric(score),
        "summary": {
            "case_count": total,
            "passed": passed,
            "failed": failed,
            "threshold": _MIN_PASS_SCORE,
            "top_failures": top_failures,
        },
        "case_results": results,
        "requested_by": requested_by or "",
        "created_at": generated_at,
    }


def build_trajectory_export(
    *,
    agent_id: str,
    task_id: int,
    execution: Mapping[str, Any],
    run_graph: Mapping[str, Any] | None,
    replay: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Build a redacted JSONL trajectory export from one execution."""

    graph_payload = as_record(run_graph or execution.get("run_graph"))
    replay_payload = as_record(replay or execution.get("run_replay"))
    generated_at = now_iso()
    export_seed = {"graph": graph_payload, "replay": replay_payload}
    export_id = f"trajectory:{agent_id.upper()}:{int(task_id)}:{stable_digest(export_seed, length=12)}"
    lines: list[dict[str, Any]] = [
        {
            "schema_version": TRAJECTORY_EXPORT_SCHEMA_VERSION,
            "record_type": "manifest",
            "export_id": export_id,
            "agent_id": agent_id.upper(),
            "task_id": int(task_id),
            "generated_at": generated_at,
            "replay_mode": replay_payload.get("replay_mode") or replay_payload.get("mode") or "offline",
            "provider_calls_disabled": True,
            "redaction_applied": True,
        }
    ]
    for node in as_list(graph_payload.get("nodes")):
        raw = as_record(node)
        lines.append(
            {
                "schema_version": TRAJECTORY_EXPORT_SCHEMA_VERSION,
                "record_type": "run_graph_node",
                "node_id": raw.get("node_id") or raw.get("id"),
                "node_type": raw.get("node_type") or raw.get("type"),
                "status": raw.get("status"),
                "summary": safe_preview(raw.get("summary") or raw.get("label")),
                "payload": redacted(as_record(raw.get("payload") or raw.get("metadata"))),
                "refs": redacted(as_record(raw.get("refs"))),
            }
        )
    for step in as_list(replay_payload.get("steps")):
        raw = as_record(step)
        lines.append(
            {
                "schema_version": TRAJECTORY_EXPORT_SCHEMA_VERSION,
                "record_type": "replay_step",
                "node_id": raw.get("node_id"),
                "type": raw.get("type"),
                "label": raw.get("label"),
                "status": raw.get("status"),
                "deterministic": raw.get("deterministic", True),
                "redacted": raw.get("redacted", True),
                "notes": safe_preview(raw.get("notes")),
            }
        )
    if len(lines) == 1:
        lines.append(
            {
                "schema_version": TRAJECTORY_EXPORT_SCHEMA_VERSION,
                "record_type": "execution_summary",
                "agent_id": agent_id.upper(),
                "task_id": int(task_id),
                "status": execution.get("status"),
                "query_preview": safe_preview(redacted(execution.get("query_text"))),
                "response_preview": safe_preview(redacted(execution.get("response_text"))),
            }
        )
    jsonl = "\n".join(canonical_json(line) for line in lines) + "\n"
    warnings = _trajectory_export_warnings(
        lines=lines,
        graph_payload=graph_payload,
        replay_payload=replay_payload,
    )
    validation_status = "blocked" if _contains_raw_sensitive_marker(jsonl) else ("warning" if warnings else "passed")
    manifest = {
        "schema_version": TRAJECTORY_EXPORT_MANIFEST_SCHEMA_VERSION,
        "export_id": export_id,
        "agent_id": agent_id.upper(),
        "source_refs": {
            "task_id": int(task_id),
            "run_graph_id": graph_payload.get("graph_id") or graph_payload.get("run_id") or "",
            "replay_id": replay_payload.get("replay_id") or replay_payload.get("run_id") or "",
        },
        "run_graph_refs": compact_strings(
            [
                as_record(node).get("node_id") or as_record(node).get("id")
                for node in as_list(graph_payload.get("nodes"))
            ]
        ),
        "redaction_summary": {
            "redaction_applied": True,
            "provider_calls_disabled": True,
            "raw_prompt_included": False,
            "raw_secret_count": 0 if validation_status != "blocked" else 1,
        },
        "validation_status": validation_status,
        "missing_data_warnings": warnings,
        "record_count": len(lines),
        "package_hash": stable_digest(jsonl, length=32),
    }
    return {
        "schema_version": TRAJECTORY_EXPORT_SCHEMA_VERSION,
        "export_id": export_id,
        "agent_id": agent_id.upper(),
        "task_id": int(task_id),
        "generated_at": generated_at,
        "replay_mode": "offline",
        "provider_calls_disabled": True,
        "redaction_applied": True,
        "record_count": len(lines),
        "package_hash": manifest["package_hash"],
        "manifest": manifest,
        "validation_status": validation_status,
        "warnings": warnings,
        "jsonl": jsonl,
        "records": lines,
    }


def _trajectory_export_warnings(
    *,
    lines: list[dict[str, Any]],
    graph_payload: Mapping[str, Any],
    replay_payload: Mapping[str, Any],
) -> list[str]:
    warnings: list[str] = []
    if not as_list(graph_payload.get("nodes")):
        warnings.append("missing_run_graph_nodes")
    if not as_list(replay_payload.get("steps")):
        warnings.append("missing_replay_steps")
    if len(lines) <= 2:
        warnings.append("minimal_export_bundle")
    return warnings


def _contains_raw_sensitive_marker(value: str) -> bool:
    lowered = value.lower()
    markers = ("sk-live-", "bearer ", "api_key=", "password=", "secret=", "token=")
    return any(marker in lowered for marker in markers)


def build_release_quality_report(
    *,
    agent_id: str,
    latest_run: Mapping[str, Any] | None,
    recent_runs: list[Mapping[str, Any]],
    trajectory_exports: list[Mapping[str, Any]] | None = None,
    run_graphs: Iterable[Mapping[str, Any]] | None = None,
    golden_eval_comparisons: Iterable[Mapping[str, Any]] | None = None,
    require_run_graphs: bool = False,
) -> dict[str, Any]:
    latest = as_record(latest_run)
    recent = [as_record(item) for item in recent_runs]
    exports = [as_record(item) for item in trajectory_exports or []]
    failure_counts: dict[str, int] = {}
    for run in recent:
        metrics = as_record(run.get("metrics"))
        failures = as_list(metrics.get("failures")) or as_list(metrics.get("top_failures"))
        for failure in failures:
            category = str(as_record(failure).get("category") or "unknown")
            failure_counts[category] = failure_counts.get(category, 0) + 1
    latest_status = str(latest.get("status") or latest.get("result") or "")
    latest_score = float(latest.get("score") or as_record(latest.get("metrics")).get("task_success_proxy") or 0.0)
    eval_ok = latest_status == "passed" or latest_score >= _MIN_PASS_SCORE
    export_ok = any(bool(item.get("redaction_applied", True)) for item in exports) if exports else True
    graph_reports = []
    for item in run_graphs or []:
        graph = as_record(item)
        scenario = str(graph.get("scenario") or as_record(graph.get("metadata")).get("scenario") or "")
        graph_reports.append(
            verify_run_graph_completeness(
                graph,
                scenario=scenario or None,
                requires_partial_timeout=None,
                require_synthesis_path=True if scenario == "squad" else None,
            )
        )
    graph_missing = require_run_graphs and not graph_reports
    graph_ok = (not graph_missing) and (
        all(report.get("status") == "passed" for report in graph_reports) if graph_reports else True
    )
    golden_comparisons = [as_record(item) for item in golden_eval_comparisons or []]
    golden_ok = all(str(item.get("status") or "") == "passed" for item in golden_comparisons)
    status = "passed" if eval_ok and export_ok and graph_ok and golden_ok else "failed"
    gates: dict[str, dict[str, Any]] = {
        "offline_eval": {"status": "passed" if eval_ok else "failed", "threshold": _MIN_PASS_SCORE},
        "trajectory_export_redaction": {"status": "passed" if export_ok else "failed"},
        "run_graph_completeness": {
            "status": "passed" if graph_ok else "failed",
            "checked_graphs": len(graph_reports),
            "failures": (
                [
                    {
                        "category": "missing_run_graph",
                        "message": "Release quality requires at least one RunGraph for active/golden suites.",
                    }
                ]
                if graph_missing
                else [failure for report in graph_reports for failure in as_list(report.get("failures"))][:20]
            ),
        },
        "squad_golden_quality": {
            "status": "passed" if golden_ok else "failed",
            "checked_cases": len(golden_comparisons),
            "failures": [
                {
                    "category": "squad_golden_quality",
                    "case_key": item.get("case_key"),
                    "winner": item.get("winner"),
                    "quality_delta": item.get("quality_delta"),
                }
                for item in golden_comparisons
                if str(item.get("status") or "") != "passed"
            ][:20],
        },
        "provider_calls_disabled": {"status": "passed"},
        "browser_authenticated_e2e": {
            "status": "blocked",
            "message": "Authenticated browser E2E depends on local Browser/auth infrastructure.",
        },
    }
    generated_at = now_iso()
    release_quality_id = f"release-quality:{agent_id.upper()}:{stable_digest({'latest': latest, 'at': generated_at})}"
    failure_groups = [
        {"category": category, "count": count}
        for category, count in sorted(failure_counts.items(), key=lambda item: (-item[1], item[0]))[:10]
    ]
    gate_items: list[dict[str, Any]] = []
    for key, value in gates.items():
        gate_item = {"id": key}
        gate_item.update(value)
        gate_items.append(gate_item)
    return {
        "schema_version": RELEASE_QUALITY_SCHEMA_VERSION,
        "release_quality_id": release_quality_id,
        "agent_id": agent_id.upper(),
        "status": status,
        "suite_score": _metric(latest_score),
        "generated_at": generated_at,
        "gates": gates,
        "gate_items": gate_items,
        "latest_eval_run": latest or None,
        "failure_groups": failure_groups,
        "top_failures": failure_groups,
        "artifacts": {
            "trajectory_exports": [
                {
                    "export_id": item.get("export_id"),
                    "task_id": item.get("task_id"),
                    "package_hash": item.get("package_hash"),
                    "record_count": item.get("record_count"),
                }
                for item in exports[:10]
            ],
            "run_graph_completeness": graph_reports,
            "squad_golden_quality": golden_comparisons,
        },
        "residual_risks": ["Authenticated dashboard E2E depends on local Browser/auth infrastructure."],
    }
