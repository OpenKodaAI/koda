"""Pure feedback and runbook policy helpers."""

from __future__ import annotations

import contextlib
import hashlib
from typing import Any, TypedDict


class KnowledgeCandidatePayload(TypedDict, total=False):
    candidate_key: str
    merge_key: str | None
    task_kind: str
    candidate_type: str
    summary: str
    evidence: list[dict[str, Any]]
    source_refs: list[dict[str, Any]]
    proposed_runbook: dict[str, Any]
    confidence_score: float
    agent_id: str | None
    task_id: int | None
    project_key: str
    environment: str
    team: str
    success_delta: int
    failure_delta: int
    verification_delta: int
    force_pending: bool
    diff_summary: str


def normalize_feedback_runbook_steps(value: object, *, fallback: str) -> list[str]:
    if isinstance(value, list):
        steps = [str(item).strip() for item in value if str(item).strip()]
        if steps:
            return steps
    if isinstance(value, str):
        text = value.strip()
        if text:
            return [text]
    return [fallback]


def episode_source_refs(episode: dict[str, object]) -> list[dict[str, Any]]:
    payload = episode.get("source_refs")
    if not isinstance(payload, list):
        return []
    return [dict(item) for item in payload if isinstance(item, dict)]


def episode_confidence_score(episode: dict[str, object]) -> float:
    raw = episode.get("confidence_score")
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        with contextlib.suppress(ValueError):
            return float(raw)
    return 0.0


def episode_feedback_gate_reasons(episode: dict[str, object]) -> list[str]:
    reasons: list[str] = []
    if str(episode.get("status") or "") != "completed":
        reasons.append("task_not_completed")
    if bool(episode.get("stale_sources_present")):
        reasons.append("stale_sources_present")
    if bool(episode.get("ungrounded_operationally")):
        reasons.append("ungrounded_operationally")
    if bool(episode.get("post_write_review_required")):
        reasons.append("post_write_review_required")
    if not bool(episode.get("verified_before_finalize")):
        reasons.append("not_verified_before_finalize")
    answer_gate_status = str(episode.get("answer_gate_status") or "").strip().lower()
    if answer_gate_status not in {"approved", "accepted", "ok", "pass", "passed"}:
        reasons.append(f"answer_gate_status:{answer_gate_status or 'missing'}")
    if not episode_source_refs(episode):
        reasons.append("missing_source_refs")
    plan = episode.get("plan") if isinstance(episode.get("plan"), dict) else {}
    if not isinstance(plan, dict) or not str(plan.get("summary") or "").strip():
        reasons.append("missing_plan_summary")
    return reasons


def build_success_pattern_candidate(
    *,
    episode: dict[str, object],
    feedback_type: str,
    task_id: int,
    agent_id: str | None,
) -> KnowledgeCandidatePayload:
    plan = episode.get("plan") if isinstance(episode.get("plan"), dict) else {}
    plan = plan if isinstance(plan, dict) else {}
    summary = str(plan.get("summary") or episode.get("task_kind") or "Promoted routine").strip()
    verification = normalize_feedback_runbook_steps(
        plan.get("verification"),
        fallback="Confirm the completed state matches the expected outcome.",
    )
    steps = normalize_feedback_runbook_steps(
        plan.get("steps"),
        fallback="Repeat the structured workflow that produced the approved result.",
    )
    rollback = str(plan.get("rollback") or "Revert the last change and restore the previous known-good state.").strip()
    return {
        "candidate_key": hashlib.sha256(
            f"{feedback_type}:{task_id}:{episode['task_kind']}:{episode['project_key']}".encode(),
            usedforsecurity=False,
        ).hexdigest()[:24],
        "merge_key": hashlib.sha256(
            f"{feedback_type}:{episode['task_kind']}:{episode['project_key']}:{episode['environment']}".encode(),
            usedforsecurity=False,
        ).hexdigest()[:24],
        "agent_id": agent_id,
        "task_id": task_id,
        "task_kind": str(episode["task_kind"]),
        "candidate_type": "success_pattern",
        "summary": f"Human {feedback_type} feedback for task #{task_id} promoted into reusable routine.",
        "evidence": [
            {"kind": "human_feedback", "value": feedback_type},
            {"kind": "verified_before_finalize", "value": bool(episode.get("verified_before_finalize"))},
            {"kind": "answer_gate_status", "value": str(episode.get("answer_gate_status") or "")},
        ],
        "source_refs": episode_source_refs(episode),
        "proposed_runbook": {
            "title": f"{str(episode['task_kind']).replace('_', ' ').title()} reusable routine",
            "summary": summary,
            "prerequisites": [str(item) for item in (plan.get("prerequisites") or []) if str(item).strip()],
            "steps": steps,
            "verification": verification,
            "rollback": rollback,
            "owner": str(plan.get("owner") or ""),
        },
        "confidence_score": max(0.8, episode_confidence_score(episode)),
        "project_key": str(episode.get("project_key") or ""),
        "environment": str(episode.get("environment") or ""),
        "team": str(episode.get("team") or ""),
        "success_delta": 1,
        "verification_delta": 1 if bool(episode.get("verified_before_finalize")) else 0,
        "force_pending": True,
        "diff_summary": f"Requested by operator from task #{task_id} with {feedback_type} feedback.",
    }
