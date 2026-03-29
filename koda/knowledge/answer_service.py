"""Structured grounded answer planning and synthesis helpers."""

from __future__ import annotations

from koda.knowledge.telemetry import knowledge_span
from koda.knowledge.types import (
    AnswerPlan,
    GroundedAnswer,
    KnowledgeHit,
    KnowledgeQueryContext,
    KnowledgeResolution,
    QueryEnvelope,
    RetrievalBundle,
)


class KnowledgeAnswerService:
    """Build answer plans and grounded internal envelopes from retrieved evidence."""

    def _plan_items(self, plan: dict[str, object], key: str) -> list[object]:
        value = plan.get(key)
        return list(value) if isinstance(value, list) else []

    def plan(
        self,
        *,
        query_envelope: QueryEnvelope | KnowledgeQueryContext,
        retrieval_bundle: RetrievalBundle,
    ) -> AnswerPlan:
        with knowledge_span(
            "answer_plan",
            task_id=getattr(query_envelope, "task_id", None),
            task_kind=getattr(query_envelope, "task_kind", ""),
            strategy=getattr(getattr(query_envelope, "strategy", None), "value", ""),
        ):
            authoritative_sources = [item.source_label for item in retrieval_bundle.authoritative_evidence]
            supporting_sources = [item.ref_key for item in retrieval_bundle.supporting_evidence]
            open_conflicts = list(retrieval_bundle.open_conflicts)
            required_verifications = list(retrieval_bundle.required_verifications)
            uncertainty_level = retrieval_bundle.uncertainty_level
            return AnswerPlan(
                user_intent=retrieval_bundle.query_intent or getattr(query_envelope, "task_kind", "") or "general",
                recommended_action_mode=retrieval_bundle.recommended_action_mode,
                authoritative_sources=authoritative_sources,
                supporting_sources=supporting_sources,
                required_verifications=required_verifications,
                open_conflicts=open_conflicts,
                uncertainty_level=uncertainty_level,
            )

    def build_answer_plan(
        self,
        *,
        query_context: KnowledgeQueryContext,
        retrieval_bundle: RetrievalBundle,
        retrieval_engine: str = "",
    ) -> dict[str, object]:
        plan = self.plan(query_envelope=query_context, retrieval_bundle=retrieval_bundle).to_dict()
        engine_name = retrieval_engine or str(getattr(retrieval_bundle, "engine_name", "") or "")
        if engine_name:
            plan["retrieval_engine"] = engine_name
        return plan

    def render_answer_plan_block(self, plan: dict[str, object]) -> str:
        if not plan:
            return ""
        authoritative = ", ".join(str(item) for item in self._plan_items(plan, "authoritative_sources")[:4]) or "none"
        supporting = ", ".join(str(item) for item in self._plan_items(plan, "supporting_sources")[:4]) or "none"
        verifications = ", ".join(str(item) for item in self._plan_items(plan, "required_verifications")[:4]) or "none"
        conflicts = ", ".join(str(item) for item in self._plan_items(plan, "open_conflicts")[:4]) or "none"
        return (
            "<grounded_answer_plan>\n"
            f"- user_intent: {plan.get('user_intent') or 'general'}\n"
            f"- recommended_action_mode: {plan.get('recommended_action_mode') or 'read_only'}\n"
            f"- authoritative_sources: {authoritative}\n"
            f"- supporting_sources: {supporting}\n"
            f"- required_verifications: {verifications}\n"
            f"- open_conflicts: {conflicts}\n"
            f"- uncertainty_level: {plan.get('uncertainty_level') or 'low'}\n"
            "Use authoritative sources first. Supporting sources are auxiliary only.\n"
            "</grounded_answer_plan>"
        )

    def compose(
        self,
        *,
        response: str,
        resolution: KnowledgeResolution | None,
    ) -> GroundedAnswer:
        with knowledge_span(
            "answer_compose",
            retrieval_strategy=getattr(
                getattr(resolution, "retrieval_strategy", None),
                "value",
                "",
            ),
            has_resolution=resolution is not None,
        ):
            if resolution is None:
                return GroundedAnswer(
                    answer_text=response,
                    operational_status="unknown",
                    citations=[],
                    supporting_evidence_refs=[],
                    uncertainty_notes=["knowledge resolution unavailable"],
                    answer_plan={},
                )

            resolution_plan = getattr(resolution, "answer_plan", {}) or {}
            if hasattr(resolution_plan, "to_dict"):
                resolution_plan = resolution_plan.to_dict()
            retrieval_engine = str(resolution_plan.get("retrieval_engine", "") or "")
            backend_unavailable = bool(getattr(resolution, "backend_unavailable", False))
            if backend_unavailable:
                failure_reason = str(
                    getattr(resolution, "backend_failure_reason", "") or "knowledge primary backend unavailable"
                )
                uncertainty_notes = [failure_reason]
                if "grounded knowledge unavailable" not in uncertainty_notes:
                    uncertainty_notes.append("grounded knowledge unavailable")
                return GroundedAnswer(
                    answer_text=response,
                    operational_status="knowledge_unavailable",
                    citations=[],
                    supporting_evidence_refs=[],
                    uncertainty_notes=uncertainty_notes,
                    answer_plan=dict(resolution_plan),
                    metadata={
                        "backend_unavailable": True,
                        "backend_failure_reason": failure_reason,
                        "winning_sources": [],
                        "retrieval_strategy": getattr(
                            getattr(resolution, "retrieval_strategy", None),
                            "value",
                            str(getattr(resolution, "retrieval_strategy", "")),
                        ),
                        "retrieval_engine": retrieval_engine,
                    },
                )

            citations = self._extract_citations(response, resolution)
            supporting_refs = [
                item.ref_key
                for item in list(getattr(resolution, "supporting_sources", []) or [])
                if getattr(item, "ref_key", "")
            ]
            retrieval_bundle = getattr(resolution, "retrieval_bundle", None)
            uncertainty_notes = list(retrieval_bundle.uncertainty_notes) if retrieval_bundle is not None else []
            if bool(getattr(resolution, "stale_sources_present", False)) and (
                "stale grounded sources present" not in uncertainty_notes
            ):
                uncertainty_notes.append("stale grounded sources present")
            if list(getattr(resolution, "conflicts", []) or []) and (
                "grounded conflicts remain open" not in uncertainty_notes
            ):
                uncertainty_notes.append("grounded conflicts remain open")
            operational_status = (
                "needs_review" if bool(getattr(resolution, "ungrounded_operationally", False)) else "grounded"
            )
            return GroundedAnswer(
                answer_text=response,
                operational_status=operational_status,
                citations=citations,
                supporting_evidence_refs=supporting_refs,
                uncertainty_notes=uncertainty_notes,
                answer_plan=dict(resolution_plan),
                metadata={
                    "winning_sources": list(getattr(resolution, "winning_sources", []) or []),
                    "retrieval_strategy": getattr(
                        getattr(resolution, "retrieval_strategy", None),
                        "value",
                        str(getattr(resolution, "retrieval_strategy", "")),
                    ),
                    "retrieval_engine": retrieval_engine,
                },
            )

    def build_grounded_answer(
        self,
        *,
        response: str,
        resolution: KnowledgeResolution | None,
    ) -> GroundedAnswer:
        return self.compose(response=response, resolution=resolution)

    def _extract_citations(self, response: str, resolution: KnowledgeResolution) -> list[dict[str, object]]:
        lowered = response.lower()
        citations: list[dict[str, object]] = []
        for requirement in resolution.citation_requirements:
            source_label = requirement.source_label
            start = lowered.find(source_label.lower())
            if start < 0:
                continue
            hit = self._find_hit_by_source_label(resolution.hits, source_label)
            citations.append(
                {
                    "source_label": source_label,
                    "layer": requirement.layer,
                    "required": requirement.required,
                    "updated_at": requirement.updated_at,
                    "span_start": start,
                    "span_end": start + len(source_label),
                    "title": hit.entry.title if hit is not None else source_label,
                }
            )
        return citations

    def _find_hit_by_source_label(self, hits: list[KnowledgeHit], source_label: str) -> KnowledgeHit | None:
        for hit in hits:
            if hit.entry.source_label == source_label:
                return hit
        return None
