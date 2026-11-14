"""Evaluation helpers for grounded retrieval and answer quality."""

from __future__ import annotations

from typing import Any

from koda.knowledge.types import (
    EvaluationCaseStatus,
    GoldSourceKind,
    GroundingGateDecision,
    KnowledgeAnswerEvaluation,
)


def build_grounding_gate_decision(
    *,
    response: str,
    evaluation: KnowledgeAnswerEvaluation,
    had_write: bool,
) -> GroundingGateDecision:
    """Build the runtime decision envelope used before finalization."""
    if not had_write or not evaluation.blocking:
        return GroundingGateDecision(status="passed", reasons=list(evaluation.gate_reasons), requires_review=False)
    reason_text = (
        "; ".join(evaluation.gate_reasons) if evaluation.gate_reasons else "grounding policy blocked completion"
    )
    safe_response = (
        f"Nao posso confirmar a conclusao operacional com seguranca. Encaminhei para revisao porque: {reason_text}."
    )
    return GroundingGateDecision(
        status="needs_review",
        reasons=list(evaluation.gate_reasons),
        requires_review=True,
        safe_response=safe_response,
    )


def seed_cases_from_sources(
    *,
    approved_runbooks: list[dict[str, Any]],
    human_corrected_episodes: list[dict[str, Any]],
    negative_control_episodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Create draft evaluation cases from curated sources only."""
    seeded: list[dict[str, Any]] = []
    for runbook in approved_runbooks:
        runbook_id = str(runbook.get("id") or "").strip()
        if not runbook_id:
            continue
        title = str(runbook.get("title") or "").strip() or f"runbook-{runbook_id}"
        summary = str(runbook.get("summary") or "").strip()
        query_text = summary or title
        seeded.append(
            {
                "case_key": f"runbook:{runbook_id}",
                "query_text": query_text,
                "source_task_id": None,
                "task_kind": str(runbook.get("task_kind") or "general"),
                "project_key": str(runbook.get("project_key") or ""),
                "environment": str(runbook.get("environment") or ""),
                "team": str(runbook.get("team") or ""),
                "modality": "text",
                "expected_sources": [f"runbook:{runbook_id}"],
                "expected_layers": ["approved_runbook"],
                "reference_answer": summary,
                "status": EvaluationCaseStatus.DRAFT.value,
                "gold_source_kind": GoldSourceKind.APPROVED_RUNBOOK.value,
                "metadata": {"seed_source": "approved_runbook"},
            }
        )

    for episode in human_corrected_episodes:
        seeded.append(
            {
                "case_key": f"episode:{episode['id']}",
                "query_text": str(((episode.get("plan") or {}).get("query")) or f"Replayed task #{episode['task_id']}"),
                "source_task_id": episode.get("task_id"),
                "task_kind": str(episode.get("task_kind") or "general"),
                "project_key": str(episode.get("project_key") or ""),
                "environment": str(episode.get("environment") or ""),
                "team": str(episode.get("team") or ""),
                "modality": (
                    "multimodal"
                    if any(
                        str(ref.get("source_type") or "").startswith("artifact_")
                        for ref in episode.get("source_refs") or []
                    )
                    else "text"
                ),
                "expected_sources": [],
                "expected_layers": [],
                "reference_answer": "",
                "status": EvaluationCaseStatus.DRAFT.value,
                "gold_source_kind": GoldSourceKind.HUMAN_CORRECTED_TASK.value,
                "metadata": {
                    "feedback_status": str(episode.get("feedback_status") or "corrected"),
                    "seed_source": "human_corrected_task",
                },
            }
        )

    for episode in negative_control_episodes:
        seeded.append(
            {
                "case_key": f"negative:{episode['id']}",
                "query_text": str(
                    ((episode.get("plan") or {}).get("query")) or f"Negative control #{episode['task_id']}"
                ),
                "source_task_id": episode.get("task_id"),
                "task_kind": str(episode.get("task_kind") or "general"),
                "project_key": str(episode.get("project_key") or ""),
                "environment": str(episode.get("environment") or ""),
                "team": str(episode.get("team") or ""),
                "modality": "text",
                "expected_sources": [],
                "expected_layers": [],
                "reference_answer": "",
                "status": EvaluationCaseStatus.DRAFT.value,
                "gold_source_kind": GoldSourceKind.NEGATIVE_CONTROL.value,
                "metadata": {
                    "feedback_status": str(episode.get("feedback_status") or "failed"),
                    "seed_source": "negative_control",
                },
            }
        )
    return seeded
