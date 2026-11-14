"""Runtime manager for layered grounded knowledge and approved runbooks."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, cast

from koda.config import AGENT_ID
from koda.internal_rpc.retrieval_engine import (
    build_retrieval_engine_client,
)
from koda.knowledge.answer_service import KnowledgeAnswerService
from koda.knowledge.config import (
    KNOWLEDGE_CITATION_POLICY,
    KNOWLEDGE_CONTEXT_MAX_TOKENS,
    KNOWLEDGE_ENABLED,
    KNOWLEDGE_MAX_RESULTS,
    KNOWLEDGE_MULTIMODAL_GRAPH_ENABLED,
    KNOWLEDGE_V2_ENABLED,
)
from koda.knowledge.experiments import KnowledgeExperimentPlan, KnowledgeExperimentService
from koda.knowledge.repository import KnowledgeRepository
from koda.knowledge.retrieval_v2 import KnowledgeRetrievalService, RetrievalEngineClient
from koda.knowledge.storage_v2 import KnowledgeStorageV2
from koda.knowledge.telemetry import knowledge_span
from koda.knowledge.types import (
    ArtifactEvidenceMatch,
    ArtifactEvidenceNode,
    AuthoritativeEvidence,
    CanonicalRelation,
    CitationRequirement,
    KnowledgeConflict,
    KnowledgeGuardrail,
    KnowledgeHit,
    KnowledgeLayer,
    KnowledgeQueryContext,
    KnowledgeResolution,
    QueryEnvelope,
    RetrievalStrategy,
    RetrievalTrace,
    SupportingEvidence,
    TraceRole,
)
from koda.logging_config import get_logger
from koda.state.knowledge_governance_store import list_approved_guardrails

log = get_logger(__name__)

_CHARS_PER_TOKEN = 4
_LAYER_ORDER: tuple[KnowledgeLayer, ...] = (
    KnowledgeLayer.CANONICAL_POLICY,
    KnowledgeLayer.APPROVED_RUNBOOK,
    KnowledgeLayer.WORKSPACE_DOC,
    KnowledgeLayer.OBSERVED_PATTERN,
)


class KnowledgeManager:
    """Retrieves layered operational context through the authoritative retrieval engine."""

    def __init__(
        self,
        agent_id: str | None = None,
        *,
        retrieval_service: KnowledgeRetrievalService | None = None,
        retrieval_engine_client: RetrievalEngineClient | None = None,
    ) -> None:
        self._agent_id = (agent_id or AGENT_ID or "").upper() or None
        self._initialized = False
        self._experiment_service = KnowledgeExperimentService()
        if retrieval_service is not None:
            self._retrieval_engine_client = retrieval_engine_client
            self._retrieval_v2 = retrieval_service
        else:
            self._retrieval_engine_client = retrieval_engine_client or build_retrieval_engine_client(
                agent_id=self._agent_id
            )
            self._retrieval_v2 = KnowledgeRetrievalService(
                engine_client=self._retrieval_engine_client,
            )
        self._answer_service = KnowledgeAnswerService()
        self._storage_v2 = KnowledgeStorageV2(KnowledgeRepository(self._agent_id), self._agent_id)

    @property
    def initialized(self) -> bool:
        return self._initialized

    async def initialize(self) -> None:
        """Start the retrieval engine and, in primary storage mode, the knowledge backend."""
        if not KNOWLEDGE_ENABLED:
            log.info("knowledge_disabled")
            return

        retrieval_start = getattr(self._retrieval_v2, "start", None)
        if callable(retrieval_start):
            try:
                await retrieval_start()
            except Exception:
                log.exception(
                    "knowledge_retrieval_engine_start_failed",
                    engine=getattr(self._retrieval_v2, "engine_name", "unknown"),
                )
        if self._storage_v2.primary_read_enabled():
            try:
                await self._storage_v2.start_primary_backend()
            except Exception:
                log.exception("knowledge_primary_backend_start_failed")
        self._initialized = True
        log.info(
            "knowledge_initialized",
            entry_count=0,
            primary_backend=self._storage_v2.external_read_enabled(),
            local_materialization=False,
            knowledge_pack_loading=False,
        )

    async def search(
        self,
        query_context: KnowledgeQueryContext,
        max_results: int | None = None,
    ) -> list[KnowledgeHit]:
        """Search the layered knowledge base using precedence-aware ordering."""
        resolution = await self.resolve(query_context, max_results=max_results)
        return resolution.hits

    def retrieval_engine_health(self) -> dict[str, Any]:
        health_fn = getattr(self._retrieval_v2, "health", None)
        if not callable(health_fn):
            return {
                "primary": {
                    "service": "retrieval",
                    "implementation": "unknown",
                    "ready": False,
                },
            }
        return cast(dict[str, Any], health_fn())

    async def resolve(
        self,
        query_context: KnowledgeQueryContext,
        max_results: int | None = None,
    ) -> KnowledgeResolution:
        """Build the full knowledge resolution envelope used by runtime grounding.

        Retrieval is authoritative only in primary storage mode; in any other
        mode ``_resolve_with_strategy`` raises.
        """
        if not KNOWLEDGE_ENABLED or not self._initialized:
            return KnowledgeResolution(context="")

        with knowledge_span(
            "resolve",
            task_id=query_context.task_id,
            task_kind=query_context.task_kind,
            project_key=query_context.project_key,
        ):
            experiment_plan = self._experiment_service.plan(query_context)

            if self._storage_v2.primary_read_enabled() and not self._storage_v2.external_read_enabled():
                return self._build_primary_backend_unavailable_resolution(
                    query_context=query_context,
                    strategy=experiment_plan.primary_strategy,
                    reason="knowledge_primary_backend_unavailable",
                )

            primary_resolution = self._resolve_with_strategy(
                query_context=query_context,
                strategy=experiment_plan.primary_strategy,
                experiment_plan=experiment_plan,
                trace_role=TraceRole.PRIMARY,
                max_results=max_results,
                persist_trace=experiment_plan.persist_primary_trace,
            )
            self._finalize_trace_persistence(
                primary_resolution=primary_resolution,
                experiment_plan=experiment_plan,
            )
            return primary_resolution

    async def build_context(
        self,
        query_context: KnowledgeQueryContext,
    ) -> tuple[str, list[KnowledgeHit]]:
        """Return the grounded knowledge context block for the query."""
        resolution = await self.resolve(query_context)
        if not resolution.hits:
            return "", []
        return resolution.context, resolution.hits

    async def ingest_artifact_dossiers(
        self,
        query_context: KnowledgeQueryContext,
        dossiers: list[Any],
    ) -> list[ArtifactEvidenceNode]:
        """Return no evidence nodes: this manager does not ingest artifact dossiers."""
        if not KNOWLEDGE_MULTIMODAL_GRAPH_ENABLED or not dossiers or query_context.task_id is None:
            return []
        if self._storage_v2.primary_read_enabled():
            log.info(
                "knowledge_primary_read_only_skips_artifact_ingest",
                task_id=query_context.task_id,
                dossier_count=len(dossiers),
            )
        return []

    def _resolve_with_strategy(
        self,
        *,
        query_context: KnowledgeQueryContext,
        strategy: RetrievalStrategy,
        experiment_plan: KnowledgeExperimentPlan,
        trace_role: TraceRole,
        max_results: int | None,
        persist_trace: bool,
    ) -> KnowledgeResolution:
        if not KNOWLEDGE_V2_ENABLED or not self._storage_v2.primary_read_enabled():
            raise RuntimeError("knowledge_retrieval_engine_not_authoritative")
        retrieval_bundle = self._retrieval_v2.query(
            envelope=QueryEnvelope(
                query=query_context.query,
                normalized_query=" ".join(query_context.query.split()).strip(),
                agent_id=query_context.agent_id,
                task_id=query_context.task_id,
                user_id=query_context.user_id,
                task_kind=query_context.task_kind,
                project_key=query_context.project_key,
                environment=query_context.environment,
                team=query_context.team,
                workspace_dir=query_context.workspace_dir or "",
                workspace_fingerprint=query_context.workspace_fingerprint,
                requires_write=query_context.requires_write,
                strategy=strategy,
                allowed_source_labels=query_context.allowed_source_labels,
                allowed_workspace_roots=query_context.allowed_workspace_roots,
            ),
            max_results=max_results or KNOWLEDGE_MAX_RESULTS,
        )
        trace_hits = retrieval_bundle.trace_hits
        route = retrieval_bundle.route
        graph_hops = retrieval_bundle.graph_hops
        grounding_score = retrieval_bundle.grounding_score
        conflict_reasons = tuple(retrieval_bundle.open_conflicts)
        explanation = retrieval_bundle.explanation
        evidence_modalities = tuple(
            dict.fromkeys(
                [modality for hit in retrieval_bundle.selected_hits for modality in hit.evidence_modalities]
                + [item.modality for item in retrieval_bundle.supporting_evidence]
            )
        )
        authoritative_remote_bundle = bool(
            retrieval_bundle.effective_engine
            and retrieval_bundle.effective_engine != "in_process"
            and not retrieval_bundle.fallback_used
        )
        if not authoritative_remote_bundle:
            raise RuntimeError("knowledge_retrieval_engine_not_authoritative")
        deduped = list(retrieval_bundle.selected_hits)
        conflicts: list[KnowledgeConflict] = []
        trace_hits = list(retrieval_bundle.trace_hits)
        authoritative_sources: list[AuthoritativeEvidence] = []
        supporting_sources: list[SupportingEvidence] = []
        linked_entities = []
        graph_relations: list[CanonicalRelation] = []
        query_intent = ""
        answer_plan: dict[str, Any] = {}
        authoritative_sources = [
            item
            for item in retrieval_bundle.authoritative_evidence
            if item.source_label in {hit.entry.source_label for hit in deduped}
        ]
        supporting_sources = list(retrieval_bundle.supporting_evidence)
        linked_entities = list(retrieval_bundle.linked_entities)
        graph_relations = list(retrieval_bundle.graph_relations)
        query_intent = retrieval_bundle.query_intent
        answer_plan = self._answer_service.build_answer_plan(
            query_context=query_context,
            retrieval_bundle=retrieval_bundle,
            retrieval_engine=retrieval_bundle.effective_engine or getattr(self._retrieval_v2, "engine_name", ""),
        )
        render_supporting_evidence = None
        context, context_blocks = self._render_context(
            deduped,
            supporting_evidence=render_supporting_evidence,
            answer_plan=answer_plan,
            authoritative_sources=authoritative_sources,
            supporting_sources=supporting_sources,
        )
        citation_requirements = self._build_citation_requirements(deduped)
        winning_sources = [hit.entry.source_label for hit in deduped]
        guardrails = self._load_guardrails(query_context)
        ungrounded_operationally = not any(
            hit.entry.layer in {KnowledgeLayer.CANONICAL_POLICY, KnowledgeLayer.APPROVED_RUNBOOK} for hit in deduped
        )
        stale_sources_present = any(hit.freshness == "stale" for hit in deduped)
        supporting_modalities = list(dict.fromkeys(item.modality for item in supporting_sources))
        trace = RetrievalTrace(
            strategy=strategy,
            route=route,
            query=query_context.query,
            agent_id=query_context.agent_id,
            task_id=query_context.task_id,
            project_key=query_context.project_key,
            environment=query_context.environment,
            team=query_context.team,
            graph_hops=graph_hops,
            grounding_score=grounding_score,
            required_citation_count=len([item for item in citation_requirements if item.required]),
            conflict_reasons=conflict_reasons,
            evidence_modalities=evidence_modalities,
            winning_sources=tuple(winning_sources),
            hits=trace_hits,
            explanation=explanation,
            experiment_key=experiment_plan.experiment_key,
            trace_role=trace_role,
        )
        return KnowledgeResolution(
            context=context,
            context_blocks=context_blocks,
            hits=deduped,
            retrieval_route=route,
            retrieval_strategy=strategy,
            trace_id=None,
            trace=trace,
            experiment_key=experiment_plan.experiment_key,
            trace_role=trace_role,
            paired_trace_id=None,
            guardrails=guardrails,
            conflicts=conflicts,
            conflict_reasons=list(conflict_reasons),
            ungrounded_operationally=ungrounded_operationally,
            stale_sources_present=stale_sources_present,
            graph_hops=graph_hops,
            citation_requirements=citation_requirements,
            grounding_score=grounding_score,
            retrieval_grounding_score=grounding_score,
            evidence_modalities=list(evidence_modalities),
            supporting_evidence_modalities=supporting_modalities,
            supporting_evidence=[],
            authoritative_sources=authoritative_sources,
            supporting_sources=supporting_sources,
            linked_entities=linked_entities,
            graph_relations=graph_relations,
            query_intent=query_intent,
            answer_plan=answer_plan,
            retrieval_bundle=retrieval_bundle,
            winning_sources=winning_sources,
            required_citation_count=trace.required_citation_count,
            citation_coverage=0.0,
        )

    def _finalize_trace_persistence(
        self,
        *,
        primary_resolution: KnowledgeResolution,
        experiment_plan: KnowledgeExperimentPlan,
    ) -> None:
        primary_trace = primary_resolution.trace
        try:
            if primary_trace is None:
                return
            primary_trace_id = self._storage_v2.persist_retrieval_trace_deferred(
                trace=primary_trace,
                sampled=experiment_plan.persist_primary_trace,
            )
            primary_trace.trace_id = primary_trace_id
            primary_resolution.trace_id = primary_trace_id
        except RuntimeError as exc:
            log.warning(
                "knowledge_trace_persistence_deferred_failed",
                task_id=primary_resolution.trace.task_id if primary_resolution.trace is not None else None,
                experiment_key=experiment_plan.experiment_key,
                error=str(exc),
            )
            if primary_resolution.trace is not None:
                primary_resolution.trace.trace_id = None
            primary_resolution.trace_id = None

    def _build_primary_backend_unavailable_resolution(
        self,
        *,
        query_context: KnowledgeQueryContext,
        strategy: RetrievalStrategy,
        reason: str,
    ) -> KnowledgeResolution:
        return KnowledgeResolution(
            context="",
            retrieval_route="primary_backend_unavailable",
            retrieval_strategy=strategy,
            ungrounded_operationally=True,
            answer_plan={
                "user_intent": query_context.task_kind or "general",
                "recommended_action_mode": "needs_review" if query_context.requires_write else "read_only",
                "authoritative_sources": [],
                "supporting_sources": [],
                "required_verifications": [],
                "open_conflicts": [],
                "uncertainty_level": "high",
            },
            backend_unavailable=True,
            backend_failure_reason=reason,
        )

    def _build_citation_requirements(self, hits: list[KnowledgeHit]) -> list[CitationRequirement]:
        if KNOWLEDGE_CITATION_POLICY == "off":
            return []
        requirements: list[CitationRequirement] = []
        for hit in hits:
            if KNOWLEDGE_CITATION_POLICY == "operational_required" and not hit.entry.operable:
                continue
            requirements.append(
                CitationRequirement(
                    source_label=hit.entry.source_label,
                    updated_at=hit.entry.updated_at.date().isoformat(),
                    layer=hit.entry.layer.value,
                    required=hit.entry.operable,
                )
            )
        return requirements

    def _load_guardrails(self, query_context: KnowledgeQueryContext) -> list[KnowledgeGuardrail]:
        guardrails = list_approved_guardrails(
            agent_id=self._agent_id,
            task_kind=query_context.task_kind,
            project_key=query_context.project_key or None,
            environment=query_context.environment or None,
            team=query_context.team or None,
            limit=8,
        )
        return [
            KnowledgeGuardrail(
                id=f"guardrail:{guardrail['id']}",
                title=str(guardrail["title"]),
                task_kind=str(guardrail["task_kind"]),
                severity=str(guardrail["severity"]),
                reason=str(guardrail["reason"]),
                source_label=str(guardrail["source_label"]),
                project_key=str(guardrail.get("project_key") or ""),
                environment=str(guardrail.get("environment") or ""),
                team=str(guardrail.get("team") or ""),
            )
            for guardrail in guardrails
        ]

    def _render_context(
        self,
        hits: list[KnowledgeHit],
        *,
        supporting_evidence: list[ArtifactEvidenceMatch] | None = None,
        answer_plan: dict[str, Any] | None = None,
        authoritative_sources: list[AuthoritativeEvidence] | None = None,
        supporting_sources: list[SupportingEvidence] | None = None,
    ) -> tuple[str, list[str]]:
        if not hits:
            return "", []

        grouped: OrderedDict[KnowledgeLayer, list[KnowledgeHit]] = OrderedDict((layer, []) for layer in _LAYER_ORDER)
        for hit in hits:
            grouped.setdefault(hit.entry.layer, []).append(hit)

        max_chars = KNOWLEDGE_CONTEXT_MAX_TOKENS * _CHARS_PER_TOKEN
        used_chars = 0
        sections: list[str] = []
        headings = {
            KnowledgeLayer.CANONICAL_POLICY: "### Canonical Policy",
            KnowledgeLayer.APPROVED_RUNBOOK: "### Approved Runbooks",
            KnowledgeLayer.WORKSPACE_DOC: "### Workspace Docs",
            KnowledgeLayer.OBSERVED_PATTERN: "### Observed Patterns (Weak Signals, Validate Before Write)",
        }
        for layer in _LAYER_ORDER:
            layer_hits = grouped.get(layer) or []
            if not layer_hits:
                continue
            lines = [headings[layer]]
            for hit in layer_hits:
                entry = hit.entry
                updated = entry.updated_at.date().isoformat()
                owner = entry.owner or "unknown"
                project = f" | project {entry.project_key}" if entry.project_key else ""
                weak_signal_note = " | weak signal" if entry.layer is KnowledgeLayer.OBSERVED_PATTERN else ""
                provenance = f"{entry.source_label} | updated {updated} | owner {owner} | {hit.freshness}"
                line = f"- [{provenance}{project}{weak_signal_note}] {entry.title}: {entry.content}"
                if used_chars + len(line) > max_chars:
                    break
                lines.append(line)
                used_chars += len(line)
            if len(lines) > 1:
                sections.append("\n".join(lines))

        if not sections:
            return "", []

        if supporting_evidence:
            evidence_lines = ["### Supporting Multimodal Evidence (Auxiliary, Not Operational Authority)"]
            for match in supporting_evidence[:4]:
                evidence_lines.append(
                    "- "
                    f"[{match.modality.value} | confidence {match.confidence:.2f} | similarity {match.similarity:.2f}] "
                    f"{match.label}: {match.excerpt}"
                )
            if len(evidence_lines) > 1:
                sections.append("\n".join(evidence_lines))
        elif supporting_sources:
            v2_supporting_sources = list(supporting_sources)
            evidence_lines = ["### Supporting Evidence (Auxiliary, Not Operational Authority)"]
            for supporting_item in v2_supporting_sources[:4]:
                evidence_lines.append(
                    "- "
                    "["
                    f"{supporting_item.modality.value} | confidence {supporting_item.confidence:.2f} "
                    f"| score {supporting_item.score:.2f}"
                    "] "
                    f"{supporting_item.label}: {supporting_item.excerpt}"
                )
            if len(evidence_lines) > 1:
                sections.append("\n".join(evidence_lines))

        if authoritative_sources:
            authority_lines = ["### Authoritative Evidence"]
            for item in authoritative_sources[:4]:
                authority_lines.append(
                    "- "
                    f"[{item.layer} | updated {item.updated_at} | {item.freshness}] "
                    f"{item.source_label}: {item.excerpt}"
                )
            if len(authority_lines) > 1:
                sections.append("\n".join(authority_lines))

        if answer_plan:
            plan_block = self._answer_service.render_answer_plan_block(answer_plan)
            if plan_block:
                sections.append(plan_block)

        context = (
            "<grounded_knowledge>\n"
            "Use these layered sources in precedence order. Higher layers override lower layers on conflict. "
            "Supporting multimodal evidence is auxiliary only and cannot override operational policy. "
            "If you rely on them, mention the source label and updated date briefly in your answer.\n\n"
            + "\n\n".join(sections)
            + "\n</grounded_knowledge>"
        )
        return context, sections
