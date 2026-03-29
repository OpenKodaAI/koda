"""Evaluation helpers for grounded retrieval and answer quality."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from koda.knowledge.answer_service import KnowledgeAnswerService
from koda.knowledge.judge_service import KnowledgeJudgeService
from koda.knowledge.types import (
    EvaluationBenchmark,
    EvaluationCaseStatus,
    EvidenceModality,
    GoldSourceKind,
    GroundingGateDecision,
    KnowledgeAnswerEvaluation,
    KnowledgeQueryContext,
    KnowledgeResolution,
    RetrievalStrategy,
)


def citation_coverage_from_response(response: str, required_sources: list[str]) -> float:
    """Return the fraction of required citations mentioned in the response."""
    if not required_sources:
        return 1.0
    lowered = response.lower()
    hits = sum(1 for source in required_sources if source.lower() in lowered)
    return hits / len(required_sources)


def evaluate_runtime_answer(
    *,
    response: str,
    resolution: KnowledgeResolution | None,
    had_write: bool,
    verified_before_finalize: bool = False,
    required_verifications: tuple[str, ...] = (),
) -> KnowledgeAnswerEvaluation:
    """Evaluate the final answer against the grounded resolution."""
    answer_service = KnowledgeAnswerService()
    judge_service = KnowledgeJudgeService()
    grounded_answer = answer_service.build_grounded_answer(response=response, resolution=resolution)
    judgement = judge_service.evaluate(
        grounded_answer=grounded_answer,
        resolution=resolution,
        had_write=had_write,
        verified_before_finalize=verified_before_finalize,
        required_verifications=required_verifications,
    )
    missing = []
    if resolution is not None:
        cited_sources = {str(item.get("source_label") or "") for item in grounded_answer.citations}
        missing = [
            item.source_label
            for item in resolution.citation_requirements
            if item.required and item.source_label not in cited_sources
        ]
    return KnowledgeAnswerEvaluation(
        citation_coverage=judgement.citation_coverage,
        grounding_score=float(getattr(resolution, "retrieval_grounding_score", 0.0) if resolution else 0.0),
        missing_citations=missing,
        warnings=list(judgement.warnings),
        gate_status=judgement.status,
        gate_reasons=list(judgement.reasons),
        requires_review=judgement.requires_review,
        blocking=judgement.requires_review,
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


def _dcg(relevances: list[int]) -> float:
    score = 0.0
    for index, relevance in enumerate(relevances, start=1):
        score += relevance / math.log2(index + 1)
    return score


def _recall_at_k(items: list[str], expected: set[str], k: int) -> float:
    if not expected:
        return 1.0
    return len(set(items[:k]) & expected) / len(expected)


def _ndcg_at_k(items: list[str], expected: set[str], k: int) -> float:
    if not expected:
        return 1.0
    relevances = [1 if item in expected else 0 for item in items[:k]]
    ideal = [1] * min(k, len(expected))
    ideal.extend([0] * max(0, k - len(ideal)))
    denominator = _dcg(ideal)
    if denominator <= 0:
        return 0.0
    return _dcg(relevances) / denominator


def score_resolution_against_case(case: dict[str, Any], resolution: KnowledgeResolution) -> dict[str, float]:
    """Score one grounded resolution against a curated evaluation case."""
    expected_sources = {str(value) for value in case.get("expected_sources") or [] if str(value)}
    expected_layers = {str(value) for value in case.get("expected_layers") or [] if str(value)}
    metadata = dict(case.get("metadata") or {})
    expected_supporting_sources = {
        str(value) for value in metadata.get("expected_supporting_sources") or [] if str(value)
    }
    predicted_sources = [hit.entry.source_label for hit in resolution.hits]
    predicted_layers = [hit.entry.layer.value for hit in resolution.hits]
    recall_at_5 = _recall_at_k(predicted_sources, expected_sources, 5)
    recall_at_10 = _recall_at_k(predicted_sources, expected_sources, 10)
    ndcg_at_10 = _ndcg_at_k(predicted_sources, expected_sources, 10)
    source_precision = (
        len(expected_sources & set(predicted_sources[:5])) / max(1, min(5, len(predicted_sources)))
        if predicted_sources
        else 0.0
    )
    layer_precision = (
        len(expected_layers & set(predicted_layers[:5])) / max(1, min(5, len(predicted_layers)))
        if predicted_layers
        else 0.0
    )
    citation_accuracy = source_precision if expected_sources else 1.0
    groundedness_precision = float(getattr(resolution, "retrieval_grounding_score", resolution.grounding_score) or 0.0)
    supporting_keys = {item.ref_key for item in getattr(resolution, "supporting_sources", []) or []}
    supporting_precision = (
        len(expected_supporting_sources & supporting_keys) / len(expected_supporting_sources)
        if expected_supporting_sources
        else (1.0 if supporting_keys else 0.0)
    )
    conflict_detection_rate = 1.0 if resolution.conflicts else 0.0
    uncertainty_behavior = 1.0 if (not resolution.conflicts or resolution.answer_plan.get("uncertainty_level")) else 0.0
    citation_span_precision = citation_accuracy if expected_sources else max(0.0, supporting_precision)
    contradiction_escape_rate = (
        1.0 if resolution.conflicts and not resolution.answer_plan.get("uncertainty_level") else 0.0
    )
    multimodal_uplift = (
        min(1.0, len(getattr(resolution, "supporting_sources", []) or []) * 0.15)
        if any(
            item.modality is not EvidenceModality.TEXT for item in getattr(resolution, "supporting_sources", []) or []
        )
        else 0.0
    )
    task_success_proxy = (
        (recall_at_5 * 0.25)
        + (recall_at_10 * 0.1)
        + (ndcg_at_10 * 0.2)
        + (citation_accuracy * 0.2)
        + (groundedness_precision * 0.2)
        + (layer_precision * 0.1)
        + ((1.0 if resolution.supporting_evidence else 0.0) * 0.05)
    )
    return {
        "recall_at_k": recall_at_5,
        "recall_at_10": recall_at_10,
        "ndcg_at_k": ndcg_at_10,
        "citation_accuracy": citation_accuracy,
        "citation_span_precision": citation_span_precision,
        "groundedness_precision": groundedness_precision,
        "conflict_detection_rate": conflict_detection_rate,
        "contradiction_escape_rate": contradiction_escape_rate,
        "verification_before_finalize_rate": float(bool(metadata.get("verified_before_finalize"))),
        "human_correction_rate": 1.0
        if str(metadata.get("feedback_status") or "").lower() in {"corrected", "failed", "risky"}
        else 0.0,
        "uncertainty_behavior": uncertainty_behavior,
        "supporting_precision": supporting_precision,
        "multimodal_uplift": multimodal_uplift,
        "task_success_proxy": task_success_proxy,
    }


def compare_replay_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build pairwise comparisons across replay results for dashboards and promotion decisions."""
    grouped: dict[str, dict[str, dict[str, float]]] = {}
    for item in results:
        grouped.setdefault(str(item.get("case_key") or ""), {})[str(item.get("strategy") or "")] = dict(
            item.get("metrics") or {}
        )
    comparisons: list[dict[str, Any]] = []
    for case_key, by_strategy in grouped.items():
        strategies = sorted(by_strategy)
        for left_index, left in enumerate(strategies):
            for right in strategies[left_index + 1 :]:
                left_metrics = by_strategy[left]
                right_metrics = by_strategy[right]
                delta = {
                    key: float(right_metrics.get(key, 0.0) or 0.0) - float(left_metrics.get(key, 0.0) or 0.0)
                    for key in sorted(set(left_metrics) | set(right_metrics))
                }
                comparisons.append(
                    {
                        "case_key": case_key,
                        "left_strategy": left,
                        "right_strategy": right,
                        "metric_delta": delta,
                    }
                )
    return comparisons


def build_benchmark_summary(*, strategy: RetrievalStrategy, runs: list[dict[str, Any]]) -> EvaluationBenchmark:
    """Aggregate a strategy's replay runs into one benchmark summary."""
    if not runs:
        return EvaluationBenchmark(strategy=strategy, case_count=0)
    keys = sorted({key for run in runs for key in (run.get("metrics") or {})})
    metrics = {
        key: sum(float((run.get("metrics") or {}).get(key, 0.0) or 0.0) for run in runs) / len(runs) for key in keys
    }
    return EvaluationBenchmark(strategy=strategy, case_count=len(runs), metrics=metrics)


async def replay_case(
    *,
    manager: Any,
    case: dict[str, Any],
    agent_id: str | None,
    strategies: list[RetrievalStrategy],
) -> list[dict[str, Any]]:
    """Replay one evaluation case across multiple retrieval strategies."""
    results: list[dict[str, Any]] = []
    for strategy in strategies:
        query_context = KnowledgeQueryContext(
            query=str(case.get("query_text") or ""),
            agent_id=agent_id,
            task_id=case.get("source_task_id"),
            user_id=None,
            workspace_dir=None,
            project_key=str(case.get("project_key") or ""),
            task_kind=str(case.get("task_kind") or "general"),
            environment=str(case.get("environment") or ""),
            team=str(case.get("team") or ""),
            retrieval_strategy=strategy,
        )
        resolution = await manager.resolve(query_context)
        metrics = score_resolution_against_case(case, resolution)
        results.append(
            {
                "case_key": str(case.get("case_key") or ""),
                "strategy": strategy.value,
                "trace_id": resolution.trace_id,
                "metrics": metrics,
                "evaluated_at": datetime.now().isoformat(),
            }
        )
    return results
