"""Service wrapper that keeps knowledge answer synthesis and judging out of queue_manager."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from koda.knowledge.answer_service import KnowledgeAnswerService
from koda.knowledge.config import KNOWLEDGE_SEMANTIC_JUDGE_ENABLED
from koda.knowledge.evaluation import build_grounding_gate_decision
from koda.knowledge.judge_service import KnowledgeJudgeService
from koda.knowledge.semantic_judge import KnowledgeSemanticJudgeService
from koda.knowledge.storage_v2 import KnowledgeStorageV2
from koda.knowledge.types import GroundedAnswer, GroundingGateDecision, KnowledgeAnswerEvaluation


class KnowledgeOrchestrationService:
    """Compose answer traces, run judgement, and persist v2 artifacts."""

    def __init__(self, storage: KnowledgeStorageV2) -> None:
        self._answer_service = KnowledgeAnswerService()
        self._judge_service = KnowledgeJudgeService()
        self._semantic_judge = KnowledgeSemanticJudgeService()
        self._storage = storage

    @staticmethod
    def _resolution_plan_dict(resolution: Any) -> dict[str, Any]:
        plan = getattr(resolution, "answer_plan", {}) or {}
        if hasattr(plan, "to_dict"):
            plan = plan.to_dict()
        return dict(plan) if isinstance(plan, dict) else {}

    def evaluate_response(
        self,
        *,
        response: str,
        resolution: Any,
        had_write: bool,
        verified_before_finalize: bool = False,
        required_verifications: tuple[str, ...] = (),
        task_id: int | None = None,
    ) -> tuple[GroundedAnswer, Any, KnowledgeAnswerEvaluation, GroundingGateDecision]:
        grounded_answer = self._answer_service.build_grounded_answer(response=response, resolution=resolution)
        judgement = self._judge_service.evaluate(
            grounded_answer=grounded_answer,
            resolution=resolution,
            had_write=had_write,
            verified_before_finalize=verified_before_finalize,
            required_verifications=required_verifications,
        )
        semantic_report = None
        if KNOWLEDGE_SEMANTIC_JUDGE_ENABLED:
            semantic_report = self._semantic_judge.evaluate(
                grounded_answer=grounded_answer,
                resolution=resolution,
                had_write=had_write,
            )
            grounded_answer.metadata["semantic_judge"] = semantic_report.to_dict()
            judgement.metrics.update(
                {
                    "semantic_claim_support": semantic_report.support_ratio,
                    "semantic_contradiction_risk": semantic_report.contradiction_risk,
                    "semantic_uncertainty_behavior": semantic_report.uncertainty_behavior_score,
                }
            )
            if semantic_report.unsupported_claims:
                warning = "semantic judge found unsupported operational claims"
                if warning not in judgement.warnings:
                    judgement.warnings.append(warning)
            if semantic_report.requires_review:
                reason = "semantic judge found unsupported operational claims"
                if reason not in judgement.reasons:
                    judgement.reasons.append(reason)
                judgement.status = "needs_review"
                judgement.requires_review = True
                judgement.policy_compliance = min(float(judgement.policy_compliance or 1.0), 0.5)
                if not judgement.safe_response:
                    judgement.safe_response = (
                        "Nao posso confirmar a conclusao operacional com seguranca. "
                        "Encaminhei para revisao porque a resposta ficou insuficientemente suportada pelas fontes."
                    )
        evaluation = KnowledgeAnswerEvaluation(
            citation_coverage=judgement.citation_coverage,
            grounding_score=float(getattr(resolution, "grounding_score", 0.0) or 0.0),
            missing_citations=[
                item.source_label
                for item in getattr(resolution, "citation_requirements", [])
                if item.required
                and item.source_label
                not in {str(citation.get("source_label") or "") for citation in grounded_answer.citations}
            ]
            if resolution is not None
            else [],
            warnings=list(judgement.warnings),
            gate_status=judgement.status,
            gate_reasons=list(judgement.reasons),
            requires_review=judgement.requires_review,
            blocking=judgement.requires_review,
        )
        gate = build_grounding_gate_decision(response=response, evaluation=evaluation, had_write=had_write)
        gate.safe_response = judgement.safe_response or gate.safe_response
        if resolution is not None and getattr(resolution, "backend_unavailable", False):
            failure_reason = str(getattr(resolution, "backend_failure_reason", "") or "")
            if not failure_reason:
                failure_reason = "knowledge primary backend unavailable"
            grounded_answer.metadata["backend_unavailable"] = True
            grounded_answer.metadata["backend_failure_reason"] = failure_reason
            if failure_reason not in grounded_answer.uncertainty_notes:
                grounded_answer.uncertainty_notes.append(failure_reason)
            if "grounded knowledge unavailable" not in grounded_answer.uncertainty_notes:
                grounded_answer.uncertainty_notes.append("grounded knowledge unavailable")
            if failure_reason not in judgement.reasons:
                judgement.reasons.append(failure_reason)
            if "knowledge backend unavailable during answer evaluation" not in judgement.warnings:
                judgement.warnings.append("knowledge backend unavailable during answer evaluation")
            judgement.status = "needs_review"
            judgement.requires_review = True
            judgement.policy_compliance = min(float(judgement.policy_compliance or 1.0), 0.0)
            if not judgement.safe_response:
                judgement.safe_response = (
                    "Nao posso validar a resposta com seguranca "
                    "porque a base de conhecimento primaria esta indisponivel."
                )
            evaluation.gate_status = judgement.status
            evaluation.gate_reasons = list(judgement.reasons)
            evaluation.requires_review = True
            evaluation.blocking = bool(had_write) or evaluation.blocking
            gate.status = judgement.status
            gate.reasons = list(judgement.reasons)
            gate.requires_review = True
            gate.safe_response = judgement.safe_response

        def _serialize_source(item: Any) -> dict[str, Any]:
            if hasattr(item, "to_dict"):
                serialized = item.to_dict()
                if isinstance(serialized, dict):
                    return dict(serialized)
                return {"value": str(serialized)}
            if isinstance(item, dict):
                return dict(item)
            return {"value": str(item)}

        if hasattr(self._storage, "persist_answer_trace_deferred"):
            persist_answer_trace = self._storage.persist_answer_trace_deferred
        else:
            persist_answer_trace = self._storage.persist_answer_trace
        try:
            answer_trace_id = persist_answer_trace(
                task_id=task_id,
                grounded_answer=grounded_answer,
                judgement=judgement,
                authoritative_sources=[
                    _serialize_source(item) for item in list(getattr(resolution, "authoritative_sources", []) or [])
                ],
                supporting_sources=[
                    _serialize_source(item) for item in list(getattr(resolution, "supporting_sources", []) or [])
                ],
                uncertainty={
                    "level": str(self._resolution_plan_dict(resolution).get("uncertainty_level", "") or ""),
                    "notes": list(getattr(grounded_answer, "uncertainty_notes", []) or []),
                },
            )
        except RuntimeError as exc:
            answer_trace_id = None
            grounded_answer.metadata["answer_trace_error"] = str(exc)
        if answer_trace_id is not None:
            grounded_answer.metadata["answer_trace_id"] = answer_trace_id
        elif getattr(self._storage, "primary_read_enabled", lambda: False)():
            grounded_answer.metadata["answer_trace_pending"] = True
        return grounded_answer, judgement, evaluation, gate

    def build_plan_payload(
        self,
        *,
        existing_plan: dict[str, Any] | None,
        resolution: Any,
        grounded_answer: GroundedAnswer | None,
        judgement: Any,
    ) -> dict[str, Any]:
        payload = dict(existing_plan or {})
        if resolution is not None and getattr(resolution, "retrieval_bundle", None) is not None:
            payload["retrieval_bundle"] = resolution.retrieval_bundle.to_dict()
        if grounded_answer is not None:
            payload["answer_trace"] = grounded_answer.to_dict()
        if judgement is not None:
            payload["judge_result"] = judgement.to_dict() if hasattr(judgement, "to_dict") else asdict(judgement)
        if resolution is not None:
            resolution_plan = self._resolution_plan_dict(resolution)
            payload["authoritative_sources"] = [
                item.to_dict() if hasattr(item, "to_dict") else {"value": str(item)}
                for item in list(getattr(resolution, "authoritative_sources", []) or [])
            ]
            payload["supporting_sources"] = [
                item.to_dict() if hasattr(item, "to_dict") else {"value": str(item)}
                for item in list(getattr(resolution, "supporting_sources", []) or [])
            ]
            payload["uncertainty"] = {
                "level": str(dict(resolution_plan).get("uncertainty_level", "") or ""),
                "notes": list(getattr(getattr(resolution, "retrieval_bundle", None), "uncertainty_notes", []) or []),
            }
        return payload
