"""Deterministic quality cockpit aggregation helpers.

This module is deliberately offline and side-effect free. It normalizes quality
rows that already exist in Koda (eval runs, metrics snapshots, skill/tool/model
summaries) and builds a compact ``quality_cockpit.v1`` payload plus
``improvement_proposal.v1`` creation payloads for operator review.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

QUALITY_COCKPIT_SCHEMA_VERSION = "quality_cockpit.v1"
QUALITY_COCKPIT_PROPOSAL_SOURCE = "quality_cockpit.v1"
RELEASE_BLOCKER_SCHEMA_VERSION = "release_blocker.v1"

_DIMENSION_BUCKETS = {
    "agent_quality": "agent",
    "agents": "agent",
    "squad_quality": "squad",
    "squads": "squad",
    "tool_quality": "tool",
    "tools": "tool",
    "skill_quality": "skill",
    "skills": "skill",
    "model_quality": "model",
    "models": "model",
    "route_quality": "route_source",
    "route_outcomes": "route_source",
    "routes": "route_source",
    "quality_rows": "",
    "rows": "",
    "metrics": "",
}
_EVAL_RUN_KEYS = ("latest_eval_run", "eval_runs", "recent_eval_runs")
_FAILURE_PROPOSAL_TYPES = {
    "tool_regression": "tool_policy",
    "policy_regression": "tool_policy",
    "replay_unavailable": "eval_case",
    "missing_run_graph": "eval_case",
    "squad_golden_quality": "routing_profile",
    "skill_eval": "skill",
    "skill_regression": "skill",
    "model_quality": "routing_profile",
}


def as_record(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


def as_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return [value]


def compact_strings(values: Iterable[Any]) -> list[str]:
    return [text for item in values if (text := str(item or "").strip())]


def stable_digest(value: Any, *, length: int = 16) -> str:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8"), usedforsecurity=False).hexdigest()[: max(8, int(length))]


def build_quality_cockpit(
    payload: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    agent_id: str = "",
    proposal_limit: int = 3,
    failure_limit: int = 10,
) -> dict[str, Any]:
    """Aggregate quality rows from dict/list payloads into ``quality_cockpit.v1``."""

    rows, eval_runs = _normalize_inputs(payload)
    entity_summaries = _summarize_entities(rows)
    top_failures = _top_failures(rows=rows, limit=failure_limit)
    cost_vs_quality = _cost_vs_quality(entity_summaries)
    eval_trends = _eval_trends(eval_runs)
    summary = _summary(entity_summaries, eval_runs)
    cockpit_agent_id = (agent_id or _first_text(rows, "agent_id") or _first_text(eval_runs, "agent_id")).upper()
    cockpit_id = f"quality-cockpit:{cockpit_agent_id or 'ALL'}:{stable_digest({'rows': rows, 'eval_runs': eval_runs})}"
    groups = _groups(entity_summaries, top_failures)
    status = _cockpit_status(summary, top_failures)
    release_quality_payload = as_record(payload).get("release_quality") if isinstance(payload, Mapping) else {}
    release_quality_payload = as_record(release_quality_payload)
    if release_quality_payload and not release_quality_payload.get("agent_id"):
        release_quality_payload = {**release_quality_payload, "agent_id": cockpit_agent_id or "ALL"}
    release_blockers = build_release_blockers(as_record(release_quality_payload))
    route_quality_history = _route_quality_history(rows, entity_summaries)
    proposals = [
        build_quality_proposal_payload(
            failure,
            agent_id=cockpit_agent_id,
            cockpit_id=cockpit_id,
        )
        for failure in top_failures[: max(0, int(proposal_limit))]
    ]
    return {
        "schema_version": QUALITY_COCKPIT_SCHEMA_VERSION,
        "cockpit_id": cockpit_id,
        "agent_id": cockpit_agent_id,
        "generated_at": "",
        "status": status,
        "summary": summary,
        "groups": groups,
        "entities": entity_summaries,
        "top_failures": top_failures,
        "cost_vs_quality": cost_vs_quality,
        "eval_trends": eval_trends,
        "route_quality_history": route_quality_history,
        "release_blockers": release_blockers,
        "proposal_payloads": proposals,
    }


def build_release_blockers(release_quality: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Derive a blocker view from canonical ``release_quality.v1`` gates."""

    payload = as_record(release_quality)
    if not payload:
        return []
    raw_gates = payload.get("gate_items") or payload.get("gates") or []
    if isinstance(raw_gates, Mapping):
        gates = [{"id": key, **as_record(value)} for key, value in raw_gates.items()]
    else:
        gates = [as_record(item) for item in as_list(raw_gates)]
    blockers: list[dict[str, Any]] = []
    for gate in gates:
        gate_id = str(gate.get("id") or gate.get("gate_id") or "release_gate").strip()
        gate_status = str(gate.get("status") or "unknown").strip().lower()
        if gate_status in {"passed", "passing"}:
            continue
        failures = [as_record(item) for item in as_list(gate.get("failures")) if as_record(item)]
        evidence_refs = _release_blocker_evidence_refs(gate, payload, failures)
        public_status = "failing" if gate_status == "failed" else gate_status
        blockers.append(
            {
                "schema_version": RELEASE_BLOCKER_SCHEMA_VERSION,
                "blocker_id": "release-blocker:"
                + stable_digest(
                    {"release": payload.get("release_quality_id"), "gate": gate_id, "status": gate_status},
                    length=20,
                ),
                "gate_id": gate_id,
                "severity": _release_blocker_severity(gate_status, failures),
                "status": public_status or "unknown",
                "title": str(gate.get("title") or gate_id.replace("_", " ").title()),
                "summary": str(gate.get("summary") or gate.get("message") or _release_blocker_summary(gate_id)),
                "evidence_refs": evidence_refs,
                "next_action": str(gate.get("next_action") or _release_blocker_next_action(gate_id)),
                "proposal_action_available": gate_status not in {"blocked"} or bool(failures),
                "metadata": {
                    "release_quality_id": payload.get("release_quality_id") or "",
                    "required": bool(gate.get("required", True)),
                    "failure_count": len(failures),
                },
            }
        )
    sorted_blockers = sorted(blockers, key=lambda item: (item["severity"], item["gate_id"]))
    _release_blocker_metrics(payload, sorted_blockers)
    return sorted_blockers


def build_quality_proposal_payload(
    failure: Mapping[str, Any],
    *,
    agent_id: str = "",
    cockpit_id: str = "",
    status: str = "pending_review",
) -> dict[str, Any]:
    """Build a create-ready improvement proposal payload without applying it."""

    item = as_record(failure)
    category = str(item.get("category") or "quality_regression").strip() or "quality_regression"
    dimension = str(item.get("dimension") or "eval").strip() or "eval"
    entity_id = str(item.get("entity_id") or item.get("case_key") or category).strip()
    source_ref = f"quality:{dimension}:{entity_id}:{category}"
    proposal_type = _FAILURE_PROPOSAL_TYPES.get(category, _proposal_type_for_dimension(dimension))
    evidence_refs = _evidence_refs(item, cockpit_id=cockpit_id)
    run_graph_node_ids = compact_strings(item.get("run_graph_node_ids") or [])
    return {
        "agent_id": agent_id.upper(),
        "source_kind": "eval",
        "source_ref": source_ref,
        "proposal_type": proposal_type,
        "summary": _proposal_summary(category, dimension, entity_id, item),
        "evidence_refs": evidence_refs,
        "diff_preview": {
            "schema_version": QUALITY_COCKPIT_PROPOSAL_SOURCE,
            "category": category,
            "dimension": dimension,
            "entity_id": entity_id,
            "observed_count": int(item.get("count") or 1),
            "affected_cases": compact_strings(item.get("case_keys") or [])[:10],
            "suggested_action": _suggested_action(category, dimension),
        },
        "risk_class": _risk_class(item),
        "validation_plan": {
            "strategy": "offline_replay",
            "required": ["eval_run.v1", QUALITY_COCKPIT_SCHEMA_VERSION],
            "target_failure_category": category,
        },
        "rollback_plan": {
            "strategy": "ledger_only",
            "effects": [
                {
                    "effect_kind": "ledger_only",
                    "target_ref": source_ref,
                    "before_ref": {"status": "observed_failure"},
                    "after_ref": {"status": "proposal_created", "auto_apply": False},
                }
            ],
        },
        "status": status,
        "run_graph_node_ids": run_graph_node_ids,
    }


def _normalize_inputs(
    payload: Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if isinstance(payload, Mapping):
        rows: list[dict[str, Any]] = []
        eval_runs: list[dict[str, Any]] = []
        for key, dimension in _DIMENSION_BUCKETS.items():
            for item in _iter_payload_items(payload.get(key)):
                row = _normalize_quality_row(item, dimension=dimension)
                if row:
                    rows.append(row)
        for key in _EVAL_RUN_KEYS:
            for item in _iter_payload_items(payload.get(key)):
                run = as_record(item)
                if run and run not in eval_runs:
                    eval_runs.append(run)
                    rows.extend(_rows_from_eval_run(run))
        return _dedupe_rows(rows), eval_runs
    rows = [_normalize_quality_row(item, dimension="") for item in payload]
    return _dedupe_rows([row for row in rows if row]), []


def _iter_payload_items(value: Any) -> list[Any]:
    if isinstance(value, Mapping):
        if "schema_version" in value or "entity_id" in value or "score" in value or "quality_score" in value:
            return [value]
        return list(value.values())
    return as_list(value)


def _normalize_quality_row(value: Any, *, dimension: str) -> dict[str, Any]:
    raw = as_record(value)
    if not raw:
        return {}
    metrics = as_record(raw.get("metrics"))
    schema_version = str(raw.get("schema_version") or "").strip()
    row_dimension = str(
        raw.get("dimension") or raw.get("kind") or raw.get("entity_type") or dimension or "unknown"
    ).strip()
    if schema_version == "route_outcome.v1":
        row_dimension = "route_source"
    entity_id = str(
        raw.get("entity_id")
        or raw.get(f"{row_dimension}_id")
        or raw.get("route_source")
        or raw.get("id")
        or raw.get("name")
        or raw.get("case_key")
        or raw.get("suite_id")
        or raw.get("agent_id")
        or "unknown"
    ).strip()
    score = _score(raw, metrics)
    if schema_version == "route_outcome.v1":
        score = _route_outcome_score(raw)
    cost = _number(
        raw.get("cost_usd")
        or raw.get("total_cost_usd")
        or raw.get("total_cost")
        or metrics.get("cost_usd")
        or metrics.get("total_cost_usd")
    )
    return {
        "dimension": row_dimension or "unknown",
        "entity_id": entity_id or "unknown",
        "agent_id": str(raw.get("agent_id") or "").upper(),
        "squad_id": str(raw.get("squad_id") or ""),
        "model": str(raw.get("model") or raw.get("model_id") or ""),
        "score": score,
        "status": str(raw.get("status") or raw.get("result") or _status_for_score(score)),
        "cost_usd": cost,
        "latency_ms": _number(raw.get("latency_ms") or metrics.get("latency_ms")),
        "timeout": bool(raw.get("timeout")) or str(raw.get("status") or "").lower() == "timeout",
        "outcome_id": str(raw.get("outcome_id") or ""),
        "sample_count": int(_number(raw.get("sample_count") or raw.get("count") or 1) or 1),
        "failures": _failures_from(raw),
        "case_key": str(raw.get("case_key") or ""),
        "run_id": str(raw.get("run_id") or ""),
        "suite_id": str(raw.get("suite_id") or ""),
        "created_at": str(raw.get("created_at") or raw.get("completed_at") or ""),
        "run_graph_node_ids": compact_strings(raw.get("run_graph_node_ids") or metrics.get("run_graph_node_ids") or []),
    }


def _rows_from_eval_run(run: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = as_record(run)
    rows = [
        _normalize_quality_row(
            {**raw, "dimension": "eval", "entity_id": raw.get("suite_id") or raw.get("run_id")}, dimension="eval"
        )
    ]
    for result in as_list(raw.get("case_results")):
        case = as_record(result)
        rows.append(
            _normalize_quality_row(
                {
                    **case,
                    "dimension": "eval_case",
                    "entity_id": case.get("case_key"),
                    "agent_id": raw.get("agent_id"),
                    "suite_id": raw.get("suite_id"),
                    "run_id": raw.get("run_id"),
                    "created_at": raw.get("created_at"),
                },
                dimension="eval_case",
            )
        )
    return [row for row in rows if row]


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for row in rows:
        key = stable_digest(row, length=24)
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def _summarize_entities(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row["dimension"]), str(row["entity_id"]))
        current = grouped.setdefault(
            key,
            {
                "dimension": key[0],
                "entity_id": key[1],
                "scores": [],
                "cost_usd": 0.0,
                "sample_count": 0,
                "failure_count": 0,
                "statuses": {},
            },
        )
        current["scores"].append(float(row.get("score") or 0.0))
        current["cost_usd"] += float(row.get("cost_usd") or 0.0)
        current["sample_count"] += int(row.get("sample_count") or 1)
        current["failure_count"] += len(as_list(row.get("failures")))
        status = str(row.get("status") or "unknown")
        current["statuses"][status] = int(current["statuses"].get(status, 0)) + 1
    summaries: list[dict[str, Any]] = []
    for item in grouped.values():
        scores = [float(score) for score in item.pop("scores")]
        avg_score = sum(scores) / len(scores) if scores else 0.0
        summaries.append(
            {
                **item,
                "quality_score": _metric(avg_score),
                "cost_usd": round(float(item["cost_usd"]), 6),
                "cost_per_quality_point": _cost_per_quality_point(float(item["cost_usd"]), avg_score),
                "status": "failed" if int(item["failure_count"]) > 0 or _metric(avg_score) < 0.8 else "passed",
            }
        )
    return sorted(summaries, key=lambda item: (str(item["dimension"]), str(item["entity_id"])))


def _top_failures(*, rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        failures = as_list(row.get("failures"))
        if not failures and str(row.get("status") or "") == "failed":
            failures = [{"category": "quality_regression", "message": "Quality row reported failed status."}]
        for failure in failures:
            raw = as_record(failure)
            category = str(raw.get("category") or raw.get("type") or "unknown").strip() or "unknown"
            key = (str(row.get("dimension") or "unknown"), str(row.get("entity_id") or "unknown"), category)
            item = grouped.setdefault(
                key,
                {
                    "dimension": key[0],
                    "entity_id": key[1],
                    "category": category,
                    "count": 0,
                    "case_keys": [],
                    "run_ids": [],
                    "messages": [],
                    "run_graph_node_ids": [],
                },
            )
            item["count"] += 1
            _append_unique(item["case_keys"], raw.get("case_key") or row.get("case_key"))
            _append_unique(item["run_ids"], raw.get("run_id") or row.get("run_id"))
            _append_unique(item["messages"], raw.get("message"))
            for node_id in compact_strings(raw.get("run_graph_node_ids") or row.get("run_graph_node_ids") or []):
                _append_unique(item["run_graph_node_ids"], node_id)
    failures = sorted(
        grouped.values(),
        key=lambda item: (-int(item["count"]), str(item["dimension"]), str(item["entity_id"]), str(item["category"])),
    )
    for item in failures:
        item["failure_id"] = "quality-failure:" + stable_digest(
            {
                "dimension": item.get("dimension"),
                "entity_id": item.get("entity_id"),
                "category": item.get("category"),
            },
            length=20,
        )
        item["status"] = _status_from_failure_count(int(item.get("count") or 1))
        item["risk_class"] = _risk_class(item)
        item["title"] = f"{item['category']} on {item['dimension']} {item['entity_id']}"
        item["summary"] = "; ".join(compact_strings(item.get("messages") or [])[:3])
        item["proposal_action_available"] = True
        _failure_metric(item)
    return failures[: max(0, int(limit))]


def _groups(entities: list[dict[str, Any]], failures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    allowed_dimensions = {"agent", "squad", "tool", "skill", "model", "route_source"}
    by_dimension: dict[str, list[dict[str, Any]]] = {}
    failures_by_entity: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for failure in failures:
        failures_by_entity.setdefault(
            (str(failure.get("dimension") or ""), str(failure.get("entity_id") or "")),
            [],
        ).append(failure)
    for entity in entities:
        dimension = str(entity.get("dimension") or "unknown")
        if dimension not in allowed_dimensions:
            continue
        failure_items = failures_by_entity.get((dimension, str(entity.get("entity_id") or "")), [])
        quality_score = float(entity.get("quality_score") or 0.0)
        item = {
            "entity_type": dimension,
            "entity_id": str(entity.get("entity_id") or "unknown"),
            "label": str(entity.get("entity_id") or "unknown"),
            "status": _status_from_quality(quality_score, int(entity.get("failure_count") or 0)),
            "risk_class": _risk_class({"count": int(entity.get("failure_count") or 0)}),
            "metrics": {
                "success_rate": quality_score,
                "failure_count": int(entity.get("failure_count") or 0),
                "run_count": int(entity.get("sample_count") or 0),
                "cost_usd": float(entity.get("cost_usd") or 0.0),
                "timeout_rate": None,
                "eval_trend": "unknown",
                "eval_score": quality_score,
            },
            "failures": failure_items,
            "release_gate_ids": [],
            "improvement_proposal_ids": [],
        }
        by_dimension.setdefault(dimension, []).append(item)
    groups: list[dict[str, Any]] = []
    for dimension, items in sorted(by_dimension.items()):
        failure_count = sum(int(item["metrics"]["failure_count"] or 0) for item in items)
        run_count = sum(int(item["metrics"]["run_count"] or 0) for item in items)
        avg_success = sum(float(item["metrics"]["success_rate"] or 0.0) for item in items) / max(1, len(items))
        groups.append(
            {
                "entity_type": dimension,
                "label": dimension.title() + "s",
                "status": _status_from_quality(avg_success, failure_count),
                "items": items,
                "metrics": {
                    "success_rate": _metric(avg_success),
                    "failure_count": failure_count,
                    "run_count": run_count,
                    "cost_usd": round(sum(float(item["metrics"]["cost_usd"] or 0.0) for item in items), 6),
                    "timeout_rate": None,
                    "eval_trend": "unknown",
                    "eval_score": _metric(avg_success),
                },
            }
        )
    return groups


def _cost_vs_quality(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [
        {
            "dimension": item["dimension"],
            "entity_id": item["entity_id"],
            "quality_score": item["quality_score"],
            "cost_usd": item["cost_usd"],
            "cost_per_quality_point": item["cost_per_quality_point"],
            "sample_count": item["sample_count"],
        }
        for item in entities
        if float(item.get("cost_usd") or 0.0) > 0.0 or int(item.get("sample_count") or 0) > 0
    ]
    return sorted(
        rows, key=lambda item: (-float(item["cost_usd"]), float(item["quality_score"]), str(item["entity_id"]))
    )


def _eval_trends(eval_runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trends: list[dict[str, Any]] = []
    for run in eval_runs:
        summary = as_record(run.get("summary"))
        score = _score(run, as_record(run.get("metrics")))
        trends.append(
            {
                "run_id": str(run.get("run_id") or ""),
                "suite_id": str(run.get("suite_id") or "default"),
                "status": str(run.get("status") or _status_for_score(score)),
                "score": score,
                "passed": int(summary.get("passed") or 0),
                "failed": int(summary.get("failed") or 0),
                "case_count": int(summary.get("case_count") or len(as_list(run.get("case_results")))),
                "created_at": str(run.get("created_at") or ""),
            }
        )
    return sorted(trends, key=lambda item: (str(item["suite_id"]), str(item["created_at"]), str(item["run_id"])))


def _summary(entities: list[dict[str, Any]], eval_runs: list[dict[str, Any]]) -> dict[str, Any]:
    score_values = [float(item.get("quality_score") or 0.0) for item in entities]
    failure_count = sum(1 for item in entities if str(item.get("status") or "") == "failed")
    run_count = sum(int(item.get("sample_count") or 1) for item in entities)
    average = _metric(sum(score_values) / len(score_values) if score_values else 0.0)
    return {
        "entity_count": len(entities),
        "eval_run_count": len(eval_runs),
        "average_quality_score": average,
        "total_cost_usd": round(sum(float(item.get("cost_usd") or 0.0) for item in entities), 6),
        "failed_entity_count": failure_count,
        "success_rate": average,
        "failure_count": failure_count,
        "run_count": run_count,
        "cost_usd": round(sum(float(item.get("cost_usd") or 0.0) for item in entities), 6),
        "timeout_rate": None,
        "eval_trend": _eval_trend_label(eval_runs),
        "eval_score": average,
    }


def _route_quality_history(rows: list[dict[str, Any]], entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_source: dict[str, dict[str, Any]] = {}
    for row in rows:
        if str(row.get("dimension") or "") != "route_source":
            continue
        source = str(row.get("entity_id") or "unknown")
        item = by_source.setdefault(
            source,
            {
                "schema_version": "route_outcome.v1",
                "route_source": source,
                "outcome_count": 0,
                "success_count": 0,
                "timeout_count": 0,
                "failure_count": 0,
                "cost_usd": 0.0,
                "latency_values": [],
                "run_graph_node_ids": [],
            },
        )
        item["outcome_count"] += int(row.get("sample_count") or 1)
        status = str(row.get("status") or "").lower()
        if status in {"passed", "success", "completed"}:
            item["success_count"] += 1
        if bool(row.get("timeout")):
            item["timeout_count"] += 1
        if status in {"failed", "failure", "timeout"}:
            item["failure_count"] += 1
        item["cost_usd"] += float(row.get("cost_usd") or 0.0)
        if row.get("latency_ms") is not None:
            item["latency_values"].append(float(row.get("latency_ms") or 0.0))
        for node_id in compact_strings(row.get("run_graph_node_ids") or []):
            _append_unique(item["run_graph_node_ids"], node_id)
    quality_by_source = {
        str(entity.get("entity_id") or ""): float(entity.get("quality_score") or 0.0)
        for entity in entities
        if str(entity.get("dimension") or "") == "route_source"
    }
    history = []
    for source, item in sorted(by_source.items()):
        count = max(1, int(item["outcome_count"]))
        latencies = list(item.pop("latency_values"))
        history.append(
            {
                **item,
                "success_rate": round(float(item["success_count"]) / count, 6),
                "timeout_rate": round(float(item["timeout_count"]) / count, 6),
                "failure_rate": round(float(item["failure_count"]) / count, 6),
                "quality_score": round(float(quality_by_source.get(source, 0.0)), 6),
                "avg_latency_ms": round(sum(latencies) / len(latencies), 6) if latencies else None,
                "cost_usd": round(float(item["cost_usd"]), 6),
            }
        )
    return history


def _failures_from(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
    metrics = as_record(raw.get("metrics"))
    failures = as_list(raw.get("failures")) or as_list(raw.get("top_failures")) or as_list(metrics.get("failures"))
    summary_failures = as_list(as_record(raw.get("summary")).get("top_failures"))
    output = [as_record(item) for item in [*failures, *summary_failures] if as_record(item)]
    if str(raw.get("schema_version") or "") == "route_outcome.v1":
        status = str(raw.get("status") or "").lower()
        if status in {"timeout", "failure", "failed"} or bool(raw.get("timeout")):
            output.append(
                {
                    "category": "route_timeout" if status == "timeout" or bool(raw.get("timeout")) else "route_failure",
                    "message": f"Route outcome reported {status or 'failure'}.",
                    "run_graph_node_ids": compact_strings([raw.get("run_graph_node_id")]),
                }
            )
    return output


def _score(raw: Mapping[str, Any], metrics: Mapping[str, Any]) -> float:
    for key in ("quality_score", "score", "success_rate", "pass_rate"):
        if (value := _number(raw.get(key))) is not None:
            return _metric(value)
    for key in ("quality_score", "task_success_proxy", "success_rate", "pass_rate"):
        if (value := _number(metrics.get(key))) is not None:
            return _metric(value)
    status = str(raw.get("status") or raw.get("result") or "").lower()
    if status == "passed":
        return 1.0
    if status == "failed":
        return 0.0
    return 0.0


def _route_outcome_score(raw: Mapping[str, Any]) -> float:
    status = str(raw.get("status") or "").lower()
    if status in {"success", "completed", "passed"}:
        return 1.0
    if status in {"timeout", "failure", "failed"} or bool(raw.get("timeout")):
        return 0.0
    return 0.5


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _metric(value: float) -> float:
    return round(max(0.0, min(1.0, float(value or 0.0))), 6)


def _status_for_score(score: float) -> str:
    return "passed" if score >= 0.8 else "failed"


def _cost_per_quality_point(cost: float, quality: float) -> float | None:
    if quality <= 0:
        return None
    return round(float(cost) / float(quality), 6)


def _append_unique(values: list[Any], value: Any) -> None:
    text = str(value or "").strip()
    if text and text not in values:
        values.append(text)


def _first_text(rows: list[dict[str, Any]], field: str) -> str:
    for row in rows:
        text = str(row.get(field) or "").strip()
        if text:
            return text
    return ""


def _proposal_type_for_dimension(dimension: str) -> str:
    if dimension == "skill":
        return "skill"
    if dimension == "tool":
        return "tool_policy"
    if dimension == "model":
        return "routing_profile"
    if dimension == "eval_case":
        return "eval_case"
    return "prompt"


def _proposal_summary(category: str, dimension: str, entity_id: str, failure: Mapping[str, Any]) -> str:
    count = int(failure.get("count") or 1)
    return f"Review {category} affecting {dimension} {entity_id} ({count} observed failure{'s' if count != 1 else ''})."


def _suggested_action(category: str, dimension: str) -> str:
    if category in {"tool_regression", "policy_regression"} or dimension == "tool":
        return "Review tool policy, expected tool coverage, and offline eval fixture evidence."
    if dimension == "skill" or category.startswith("skill"):
        return "Review skill package instructions and run skill_eval.v1 before approval."
    if dimension == "model":
        return "Compare routing profile quality against cost and promote only after offline eval pass."
    return "Inspect failing eval evidence and create a targeted prompt, routing, or eval-case adjustment."


def _risk_class(failure: Mapping[str, Any]) -> str:
    count = int(failure.get("count") or 1)
    if count >= 5:
        return "high"
    if count >= 2:
        return "medium"
    return "low"


def _cockpit_status(summary: Mapping[str, Any], failures: list[dict[str, Any]]) -> str:
    if any(str(item.get("risk_class") or "") in {"critical", "high"} for item in failures):
        return "degraded"
    if int(summary.get("failure_count") or 0) > 0:
        return "warning"
    success_rate = float(summary.get("success_rate") or 0.0)
    if success_rate >= 0.9:
        return "healthy"
    if success_rate >= 0.75:
        return "warning"
    return "degraded"


def _status_from_failure_count(count: int) -> str:
    if count >= 5:
        return "failing"
    if count >= 2:
        return "degraded"
    return "warning"


def _status_from_quality(quality_score: float, failure_count: int) -> str:
    if failure_count >= 5:
        return "failing"
    if failure_count > 0 or quality_score < 0.8:
        return "degraded"
    if quality_score < 0.9:
        return "warning"
    return "healthy"


def _eval_trend_label(eval_runs: list[dict[str, Any]]) -> str:
    if len(eval_runs) < 2:
        return "unknown"
    trends = _eval_trends(eval_runs)
    if len(trends) < 2:
        return "unknown"
    delta = float(trends[-1].get("score") or 0.0) - float(trends[0].get("score") or 0.0)
    if delta >= 0.05:
        return "improving"
    if delta <= -0.05:
        return "regressing"
    return "flat"


def _evidence_refs(failure: Mapping[str, Any], *, cockpit_id: str) -> list[dict[str, Any]]:
    refs = [{"kind": "quality_cockpit", "id": cockpit_id}] if cockpit_id else []
    for run_id in compact_strings(failure.get("run_ids") or []):
        refs.append({"kind": "eval_run", "id": run_id})
    for case_key in compact_strings(failure.get("case_keys") or []):
        refs.append({"kind": "eval_case", "id": case_key})
    return refs


def _release_blocker_severity(status: str, failures: list[dict[str, Any]]) -> str:
    if status in {"failed", "failing"}:
        return "critical" if len(failures) >= 2 else "high"
    if status == "blocked":
        return "medium"
    return "low"


def _release_blocker_summary(gate_id: str) -> str:
    return f"Release gate {gate_id} is not passing."


def _release_blocker_next_action(gate_id: str) -> str:
    if "run_graph" in gate_id:
        return "Inspect RunGraph completeness failures and add causal nodes/edges before release."
    if "trajectory" in gate_id or "redaction" in gate_id:
        return "Create a redacted trajectory_export.v1 and rerun release quality."
    if "golden" in gate_id:
        return "Rerun the squad golden eval and inspect evidence refs."
    return "Inspect gate evidence and create a reviewed improvement proposal if the failure persists."


def _release_blocker_evidence_refs(
    gate: Mapping[str, Any],
    release_quality: Mapping[str, Any],
    failures: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    refs = []
    release_id = str(release_quality.get("release_quality_id") or "").strip()
    if release_id:
        refs.append({"kind": "release_quality", "id": release_id})
    gate_id = str(gate.get("id") or gate.get("gate_id") or "").strip()
    if gate_id:
        refs.append({"kind": "release_gate", "id": gate_id})
    for failure in failures[:10]:
        for node_id in compact_strings(failure.get("run_graph_node_ids") or []):
            refs.append({"kind": "run_graph_node", "id": node_id})
        if failure.get("case_key"):
            refs.append({"kind": "eval_case", "id": str(failure.get("case_key"))})
    return refs


def _failure_metric(failure: Mapping[str, Any]) -> None:
    try:
        from koda.services.metrics import QUALITY_COCKPIT_FAILURES

        QUALITY_COCKPIT_FAILURES.labels(
            dimension=str(failure.get("dimension") or "unknown"),
            category=str(failure.get("category") or "unknown"),
            status="observed",
        ).inc(int(failure.get("count") or 1))
    except Exception:
        return


def _release_blocker_metrics(release_quality: Mapping[str, Any], blockers: list[dict[str, Any]]) -> None:
    try:
        from koda.services.metrics import RELEASE_BLOCKERS

        agent_id = str(release_quality.get("agent_id") or "unknown").upper()
        for blocker in blockers:
            RELEASE_BLOCKERS.labels(
                agent_id=agent_id,
                gate_id=str(blocker.get("gate_id") or "unknown"),
                severity=str(blocker.get("severity") or "unknown"),
                status=str(blocker.get("status") or "unknown"),
            ).set(1)
    except Exception:
        return
