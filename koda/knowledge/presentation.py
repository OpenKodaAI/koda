"""Presentation helpers for grounded runtime knowledge payloads."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

_SENSITIVE_KEYS = frozenset({"extracted_text", "source_path", "source_url"})
_REDACTED_VALUE = "[redacted]"


def _redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        payload: dict[str, Any] = {}
        for key, item in value.items():
            if key in _SENSITIVE_KEYS and item:
                payload[key] = _REDACTED_VALUE
            else:
                payload[key] = _redact_sensitive(item)
        return payload
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    return value


def redact_runtime_knowledge_payload(
    *,
    episode: dict[str, Any] | None,
    retrieval_trace: dict[str, Any] | None,
    answer_trace: dict[str, Any] | None,
    artifact_evidence: list[dict[str, Any]],
    include_sensitive: bool,
) -> dict[str, Any]:
    """Return a runtime-safe knowledge payload with optional redaction."""
    if include_sensitive:
        return {
            "episode": deepcopy(episode),
            "retrieval_trace": deepcopy(retrieval_trace),
            "answer_trace": deepcopy(answer_trace),
            "artifact_evidence": deepcopy(artifact_evidence),
        }

    redacted_episode = _redact_sensitive(deepcopy(episode)) if episode else None

    redacted_trace = _redact_sensitive(deepcopy(retrieval_trace)) if retrieval_trace else None
    redacted_answer_trace = _redact_sensitive(deepcopy(answer_trace)) if answer_trace else None

    redacted_artifacts = [_redact_sensitive(dict(item)) for item in artifact_evidence]

    plan = dict((redacted_episode or {}).get("plan") or {})
    retrieval_bundle = (
        dict(plan.get("retrieval_bundle") or {}) if isinstance(plan.get("retrieval_bundle"), dict) else {}
    )
    plan_answer_trace = dict(plan.get("answer_trace") or {}) if isinstance(plan.get("answer_trace"), dict) else {}
    effective_answer_trace = redacted_answer_trace or plan_answer_trace
    judge_result = dict(effective_answer_trace.get("judge_result") or {}) if effective_answer_trace else {}
    if not judge_result and isinstance(plan.get("judge_result"), dict):
        judge_result = dict(plan.get("judge_result") or {})
    authoritative_sources = list(retrieval_bundle.get("authoritative_evidence") or [])
    if effective_answer_trace and (effective_answer_trace.get("authoritative_sources") or not authoritative_sources):
        authoritative_sources = list(effective_answer_trace.get("authoritative_sources") or [])
    supporting_sources = list(retrieval_bundle.get("supporting_evidence") or [])
    if effective_answer_trace and (effective_answer_trace.get("supporting_sources") or not supporting_sources):
        supporting_sources = list(effective_answer_trace.get("supporting_sources") or [])
    uncertainty = {
        "level": str(retrieval_bundle.get("uncertainty_level") or ""),
        "notes": list(retrieval_bundle.get("uncertainty_notes") or []),
    }
    if effective_answer_trace and (effective_answer_trace.get("uncertainty") or not uncertainty["level"]):
        uncertainty = dict(effective_answer_trace.get("uncertainty") or uncertainty)
    return {
        "episode": redacted_episode,
        "retrieval_trace": redacted_trace,
        "artifact_evidence": redacted_artifacts,
        "retrieval_bundle": retrieval_bundle,
        "answer_trace": effective_answer_trace,
        "judge_result": judge_result,
        "authoritative_sources": authoritative_sources,
        "supporting_sources": supporting_sources,
        "uncertainty": uncertainty,
    }
