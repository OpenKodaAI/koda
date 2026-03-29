"""Post-answer grounded judgement for citation, contradiction, and policy compliance."""

from __future__ import annotations

from koda.knowledge.telemetry import knowledge_span
from koda.knowledge.types import AnswerJudgement, GroundedAnswer, KnowledgeResolution


class KnowledgeJudgeService:
    """Evaluate grounded answers and decide whether completion is safe."""

    def evaluate(
        self,
        *,
        grounded_answer: GroundedAnswer,
        resolution: KnowledgeResolution | None,
        had_write: bool,
        verified_before_finalize: bool = False,
        required_verifications: tuple[str, ...] = (),
    ) -> AnswerJudgement:
        with knowledge_span(
            "judge",
            has_resolution=resolution is not None,
            had_write=had_write,
        ):
            if resolution is None:
                safe_response = (
                    "Nao posso confirmar a conclusao operacional com seguranca porque "
                    "a resolucao grounded nao estava disponivel."
                )
                return AnswerJudgement(
                    status="needs_review" if had_write else "passed",
                    reasons=["knowledge resolution unavailable"] if had_write else [],
                    warnings=["knowledge resolution unavailable"],
                    citation_coverage=0.0,
                    citation_span_precision=0.0,
                    contradiction_escape_rate=0.0,
                    policy_compliance=0.0,
                    uncertainty_marked=bool(grounded_answer.uncertainty_notes),
                    requires_review=had_write,
                    safe_response=safe_response if had_write else "",
                    metrics={
                        "citation_coverage": 0.0,
                        "citation_span_precision": 0.0,
                        "contradiction_escape_rate": 0.0,
                        "policy_compliance": 0.0,
                    },
                )

            required_sources = [item.source_label for item in resolution.citation_requirements if item.required]
            all_resolution_sources = {
                hit.entry.source_label
                for hit in getattr(resolution, "hits", []) or []
                if getattr(hit.entry, "source_label", "")
            }
            cited_sources = {
                str(item.get("source_label") or "") for item in grounded_answer.citations if item.get("source_label")
            }
            coverage = len(cited_sources & set(required_sources)) / len(required_sources) if required_sources else 1.0
            valid_cited_sources = {source for source in cited_sources if source in all_resolution_sources}
            span_precision = (
                len(valid_cited_sources & set(required_sources)) / len(cited_sources) if cited_sources else 0.0
            )
            uncertainty_marked = bool(grounded_answer.uncertainty_notes)
            authoritative_sources = list(getattr(resolution, "authoritative_sources", []) or [])
            authoritative_operable = [item for item in authoritative_sources if bool(getattr(item, "operable", False))]
            stale_only_authority = bool(authoritative_operable) and all(
                str(getattr(item, "freshness", "") or "").lower() == "stale" for item in authoritative_operable
            )

            reasons: list[str] = []
            warnings: list[str] = []
            if coverage < 1.0:
                warnings.append("missing required source citations")
                if had_write:
                    reasons.append("missing required source citations")
            if cited_sources - all_resolution_sources:
                warnings.append("citations reference sources outside the grounded pack")
                if had_write:
                    reasons.append("citations reference sources outside the grounded pack")
            if resolution.conflicts and not uncertainty_marked:
                warnings.append("open grounded conflict is not disclosed")
                if had_write:
                    reasons.append("open grounded conflict is not disclosed")
            if resolution.ungrounded_operationally:
                warnings.append("no authoritative grounded source for operational action")
                if had_write:
                    reasons.append("no authoritative grounded source for operational action")
            if had_write and stale_only_authority:
                warnings.append("stale-only authoritative evidence cannot justify a write")
                reasons.append("stale-only authoritative evidence cannot justify a write")
            if resolution.stale_sources_present and not uncertainty_marked:
                warnings.append("stale evidence is not disclosed")
            if required_verifications and not verified_before_finalize:
                warnings.append("required verification missing")
                if had_write:
                    reasons.append("required verification missing")

            contradiction_escape_rate = 1.0 if resolution.conflicts and not uncertainty_marked else 0.0
            policy_compliance = 1.0
            if reasons:
                policy_compliance = 0.0
            elif warnings:
                policy_compliance = 0.5 if had_write else 0.7
            status = "needs_review" if had_write and reasons else "passed"
            safe_response = (
                "Nao posso confirmar a conclusao operacional com seguranca. Encaminhei para revisao porque: "
                + "; ".join(reasons)
                + "."
                if status != "passed"
                else ""
            )
            return AnswerJudgement(
                status=status,
                reasons=reasons,
                warnings=warnings,
                citation_coverage=coverage,
                citation_span_precision=span_precision,
                contradiction_escape_rate=contradiction_escape_rate,
                policy_compliance=policy_compliance,
                uncertainty_marked=uncertainty_marked,
                requires_review=status != "passed",
                safe_response=safe_response,
                metrics={
                    "citation_coverage": coverage,
                    "citation_span_precision": span_precision,
                    "contradiction_escape_rate": contradiction_escape_rate,
                    "policy_compliance": policy_compliance,
                },
            )
