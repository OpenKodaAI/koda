"""Runtime manager for layered grounded knowledge and approved runbooks."""

from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import os
import re
import tomllib
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Any, cast

from koda.config import AGENT_ID, RUNTIME_ROOT_DIR
from koda.internal_rpc.retrieval_engine import (
    build_retrieval_engine_client,
)
from koda.knowledge.answer_service import KnowledgeAnswerService
from koda.knowledge.config import (
    KNOWLEDGE_ALLOWED_LAYERS,
    KNOWLEDGE_CITATION_POLICY,
    KNOWLEDGE_CONTEXT_MAX_TOKENS,
    KNOWLEDGE_EMBEDDING_MODEL,
    KNOWLEDGE_ENABLED,
    KNOWLEDGE_GRAPH_ENABLED,
    KNOWLEDGE_MAX_CHARS_PER_CHUNK,
    KNOWLEDGE_MAX_OBSERVED_PATTERNS,
    KNOWLEDGE_MAX_RESULTS,
    KNOWLEDGE_MAX_SOURCE_AGE_DAYS,
    KNOWLEDGE_MULTIMODAL_GRAPH_ENABLED,
    KNOWLEDGE_RECALL_THRESHOLD,
    KNOWLEDGE_REQUIRE_FRESHNESS_PROVENANCE,
    KNOWLEDGE_REQUIRE_OWNER_PROVENANCE,
    KNOWLEDGE_SOURCE_GLOBS,
    KNOWLEDGE_V2_ENABLED,
    KNOWLEDGE_WORKSPACE_MAX_FILES,
    KNOWLEDGE_WORKSPACE_SOURCE_GLOBS,
)
from koda.knowledge.experiments import KnowledgeExperimentPlan, KnowledgeExperimentService
from koda.knowledge.graph_materializer import KnowledgeGraphMaterializer
from koda.knowledge.repository import KnowledgeRepository
from koda.knowledge.retrieval_v2 import KnowledgeRetrievalService, RetrievalEngineClient
from koda.knowledge.storage_v2 import KnowledgeStorageV2
from koda.knowledge.telemetry import knowledge_span
from koda.knowledge.types import (
    ArtifactDerivative,
    ArtifactEvidenceMatch,
    ArtifactEvidenceNode,
    AuthoritativeEvidence,
    CanonicalRelation,
    CitationRequirement,
    EvidenceModality,
    KnowledgeConflict,
    KnowledgeEntry,
    KnowledgeGuardrail,
    KnowledgeHit,
    KnowledgeLayer,
    KnowledgeQueryContext,
    KnowledgeResolution,
    KnowledgeScope,
    QueryEnvelope,
    RetrievalStrategy,
    RetrievalTrace,
    SupportingEvidence,
    TraceRole,
)
from koda.logging_config import get_logger
from koda.memory.procedural import search_observed_patterns
from koda.state.knowledge_governance_store import (
    list_approved_guardrails,
    list_approved_runbooks,
    upsert_knowledge_source,
)

log = get_logger(__name__)

_CHARS_PER_TOKEN = 4
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
_INLINE_SPACE_RE = re.compile(r"\s+")
_NORMALIZE_KEY_RE = re.compile(r"[^a-z0-9]+")
_WORD_RE = re.compile(r"[a-z0-9_]+")
_LAYER_ORDER: tuple[KnowledgeLayer, ...] = (
    KnowledgeLayer.CANONICAL_POLICY,
    KnowledgeLayer.APPROVED_RUNBOOK,
    KnowledgeLayer.WORKSPACE_DOC,
    KnowledgeLayer.OBSERVED_PATTERN,
)
_SKIPPED_WORKSPACE_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "venv",
}


@dataclass(slots=True)
class _Chunk:
    title: str
    text: str


def _normalize_text(text: str) -> str:
    return _INLINE_SPACE_RE.sub(" ", text).strip()


def _normalize_key(value: str) -> str:
    return _NORMALIZE_KEY_RE.sub(" ", value.lower()).strip()


def _tokenize(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _dot_product(left: list[float], right: list[float]) -> float:
    return sum(left_value * right_value for left_value, right_value in zip(left, right, strict=True))


def _parse_datetime(value: str | None, fallback: datetime) -> datetime:
    if not value:
        return fallback
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return fallback
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(UTC).replace(tzinfo=None)


def _freshness_label(updated_at: datetime, freshness_days: int) -> str:
    age_days = max(0, (datetime.now() - updated_at).days)
    if age_days <= freshness_days:
        return "fresh"
    if age_days <= freshness_days * 3:
        return "aging"
    return "stale"


def _freshness_rank(label: str) -> int:
    return {"fresh": 0, "aging": 1, "stale": 2}.get(label, 3)


def _layer_priority(layer: KnowledgeLayer) -> int:
    try:
        return _LAYER_ORDER.index(layer)
    except ValueError:
        return len(_LAYER_ORDER)


def _infer_repo_scope(path: Path, title: str, text: str) -> KnowledgeScope:
    lower_path = str(path).lower()
    lower_title = title.lower()
    lower_text = text.lower()

    if "deploy" in lower_title or "workflow" in lower_text or "regra" in lower_text:
        return KnowledgeScope.OPERATIONAL_POLICY
    if "runbook" in lower_title or "checklist" in lower_title or "playbook" in lower_title:
        return KnowledgeScope.RUNBOOK
    if "decision" in lower_title or "adr" in lower_path:
        return KnowledgeScope.RECENT_DECISION
    return KnowledgeScope.REPO_FACT


def _chunk_text(path: Path, text: str) -> list[_Chunk]:
    if path.suffix.lower() in {".md", ".markdown"}:
        sections: list[_Chunk] = []
        matches = list(_HEADING_RE.finditer(text))
        if not matches:
            normalized = _normalize_text(text)
            if normalized:
                return [_Chunk(title=path.name, text=normalized[:KNOWLEDGE_MAX_CHARS_PER_CHUNK])]
            return []

        for index, match in enumerate(matches):
            start = match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            section_text = text[start:end].strip()
            if not section_text:
                continue
            heading = match.group(1).strip()
            normalized = _normalize_text(section_text)
            if not normalized:
                continue
            while len(normalized) > KNOWLEDGE_MAX_CHARS_PER_CHUNK:
                split_at = normalized.rfind(". ", 0, KNOWLEDGE_MAX_CHARS_PER_CHUNK)
                if split_at <= 0:
                    split_at = KNOWLEDGE_MAX_CHARS_PER_CHUNK
                sections.append(_Chunk(title=heading, text=normalized[:split_at].strip()))
                normalized = normalized[split_at:].strip()
            if normalized:
                sections.append(_Chunk(title=heading, text=normalized))
        return sections

    normalized = _normalize_text(text)
    if not normalized:
        return []
    chunks: list[_Chunk] = []
    while len(normalized) > KNOWLEDGE_MAX_CHARS_PER_CHUNK:
        split_at = normalized.rfind(". ", 0, KNOWLEDGE_MAX_CHARS_PER_CHUNK)
        if split_at <= 0:
            split_at = KNOWLEDGE_MAX_CHARS_PER_CHUNK
        chunks.append(_Chunk(title=path.name, text=normalized[:split_at].strip()))
        normalized = normalized[split_at:].strip()
    if normalized:
        chunks.append(_Chunk(title=path.name, text=normalized))
    return chunks


class KnowledgeManager:
    """Retrieves layered operational context across the configured knowledge stores."""

    def __init__(
        self,
        agent_id: str | None = None,
        *,
        retrieval_service: KnowledgeRetrievalService | None = None,
        retrieval_engine_client: RetrievalEngineClient | None = None,
    ) -> None:
        self._agent_id = (agent_id or AGENT_ID or "").upper() or None
        self._entries: list[KnowledgeEntry] = []
        self._embeddings: list[list[float]] = []
        self._model: Any = None
        self._model_lock = asyncio.Lock()
        self._initialized = False
        self._memory_store: object | None = None
        self._repository = KnowledgeRepository(self._agent_id)
        self._graph_materializer = KnowledgeGraphMaterializer(self._repository, self._agent_id)
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
        self._storage_v2 = KnowledgeStorageV2(self._repository, self._agent_id)

    @property
    def initialized(self) -> bool:
        return self._initialized

    async def initialize(self, memory_store: object | None = None) -> None:
        """Initialize knowledge retrieval state for the active storage mode."""
        if not KNOWLEDGE_ENABLED:
            log.info("knowledge_disabled")
            return

        self._memory_store = memory_store
        if memory_store is not None:
            if hasattr(memory_store, "_get_model_safe"):
                self._model = await memory_store._get_model_safe()  # type: ignore[union-attr]
            elif hasattr(memory_store, "_model"):
                self._model = memory_store._model  # type: ignore[union-attr]
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
            self._entries = []
            self._embeddings = []
            self._initialized = True
            log.info(
                "knowledge_initialized",
                entry_count=0,
                primary_backend=self._storage_v2.external_read_enabled(),
                local_materialization=False,
                knowledge_pack_loading=False,
            )
            return

        if self._storage_v2.external_read_enabled():
            try:
                await self._storage_v2.start_primary_backend()
            except Exception:
                log.exception("knowledge_primary_backend_start_failed")
            self._entries = []
            self._embeddings = []
            self._initialized = True
            log.info(
                "knowledge_initialized",
                entry_count=0,
                primary_backend=True,
                local_materialization=False,
                knowledge_pack_loading=False,
            )
            return

        entries = self._load_pack_entries()
        if not entries:
            self._entries = []
            self._embeddings = []
            self._initialized = True
            log.info("knowledge_initialized", entry_count=0)
            return

        await self._get_model()
        loop = asyncio.get_running_loop()
        texts = [f"{entry.title}\n{entry.content}" for entry in entries]
        embeddings = await loop.run_in_executor(None, partial(self._embed_batch, texts))

        self._entries = entries
        self._embeddings = embeddings
        self._graph_materializer.materialize_entries(entries)
        self._storage_v2.persist_entries(entries=entries, embeddings=embeddings)
        self._initialized = True
        log.info("knowledge_initialized", entry_count=len(entries))

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
        """Build the full knowledge resolution envelope used by runtime grounding."""
        if not KNOWLEDGE_ENABLED or not self._initialized:
            return KnowledgeResolution(context="")

        with knowledge_span(
            "resolve",
            task_id=query_context.task_id,
            task_kind=query_context.task_kind,
            project_key=query_context.project_key,
        ):
            experiment_plan = self._experiment_service.plan(query_context)

            primary_mode = self._storage_v2.primary_read_enabled()
            if primary_mode and not self._storage_v2.external_read_enabled():
                return self._build_primary_backend_unavailable_resolution(
                    query_context=query_context,
                    strategy=experiment_plan.primary_strategy,
                    reason="knowledge_primary_backend_unavailable",
                )
            hits: list[KnowledgeHit] = []
            if not primary_mode:
                await self._get_model()
                loop = asyncio.get_running_loop()
                query_embedding = await loop.run_in_executor(
                    None,
                    partial(self._embed_sync, query_context.query),
                )
                static_pairs = [
                    (entry, embedding)
                    for entry, embedding in zip(self._entries, self._embeddings, strict=True)
                    if self._entry_matches_context(entry, query_context)
                    and self._entry_allowed_by_runtime_policy(entry)
                    and self._entry_allowed_by_access_scope(entry, query_context)
                ]

                dynamic_entries: list[KnowledgeEntry] = []
                dynamic_entries.extend(self._load_approved_runbook_entries(query_context))
                dynamic_entries.extend(self._load_workspace_entries(query_context))
                dynamic_entries.extend(await self._load_observed_pattern_entries(query_context))

                dynamic_pairs: list[tuple[KnowledgeEntry, list[float]]] = []
                if dynamic_entries:
                    dynamic_texts = [f"{entry.title}\n{entry.content}" for entry in dynamic_entries]
                    dynamic_embeddings = await loop.run_in_executor(None, partial(self._embed_batch, dynamic_texts))
                    self._storage_v2.persist_entries(entries=dynamic_entries, embeddings=dynamic_embeddings)
                    dynamic_pairs = list(zip(dynamic_entries, dynamic_embeddings, strict=True))

                for entry, embedding in static_pairs + dynamic_pairs:
                    if not self._entry_allowed_by_runtime_policy(entry):
                        continue
                    if not self._entry_allowed_by_access_scope(entry, query_context):
                        continue
                    similarity = _dot_product(query_embedding, embedding)
                    if similarity < KNOWLEDGE_RECALL_THRESHOLD:
                        continue
                    hits.append(
                        KnowledgeHit(
                            entry=entry,
                            similarity=similarity,
                            freshness=_freshness_label(entry.updated_at, entry.freshness_days),
                        )
                    )

                hits.sort(
                    key=lambda hit: (
                        _layer_priority(hit.entry.layer),
                        _freshness_rank(hit.freshness),
                        -hit.similarity,
                    )
                )

            primary_resolution = self._resolve_with_strategy(
                query_context=query_context,
                strategy=experiment_plan.primary_strategy,
                experiment_plan=experiment_plan,
                trace_role=TraceRole.PRIMARY,
                hits=hits,
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
        """Persist artifact evidence nodes and their graph edges before retrieval."""
        if not KNOWLEDGE_MULTIMODAL_GRAPH_ENABLED or not dossiers or query_context.task_id is None:
            return []
        if self._storage_v2.primary_read_enabled():
            log.info(
                "knowledge_primary_read_only_skips_artifact_ingest",
                task_id=query_context.task_id,
                dossier_count=len(dossiers),
            )
            return []
        await self._get_model()
        loop = asyncio.get_running_loop()

        nodes: list[ArtifactEvidenceNode] = []
        relation_entries = []
        texts_to_embed: list[str] = []
        for dossier in dossiers:
            subject_id = str(getattr(dossier, "subject_id", "unknown") or "unknown")
            subject_key = f"artifact_subject:{query_context.task_id}:{subject_id}"
            relation_entries.append(
                (
                    subject_key,
                    str(getattr(dossier, "subject_label", "") or subject_id),
                    str(getattr(dossier, "summary", "") or ""),
                )
            )
            for artifact in getattr(dossier, "artifacts", [])[:24]:
                kind_value = getattr(getattr(artifact, "ref", None), "kind", "text")
                modality = self._artifact_modality(getattr(kind_value, "value", kind_value))
                chunks = list(getattr(artifact, "evidence_chunks", []) or [])
                if not chunks:
                    evidence_stub = type(
                        "EvidenceStub",
                        (),
                        {
                            "citation": artifact.ref.label,
                            "excerpt": artifact.summary,
                            "score_hint": 0.0,
                        },
                    )
                    chunks = [evidence_stub()]
                for index, evidence in enumerate(chunks[:4]):
                    excerpt = str(getattr(evidence, "excerpt", artifact.summary) or artifact.summary)
                    label = str(getattr(evidence, "citation", artifact.ref.label) or artifact.ref.label)
                    source_path = str(getattr(artifact.ref, "path", "") or "")
                    source_url = str(getattr(artifact.ref, "url", "") or "")
                    source_hash = hashlib.sha256(
                        f"{query_context.task_id}:{source_path}:{source_url}:{excerpt[:120]}".encode(),
                        usedforsecurity=False,
                    ).hexdigest()
                    evidence_key = hashlib.sha256(
                        f"{query_context.task_id}:{artifact.ref.artifact_id}:{index}:{label}:{excerpt[:80]}".encode(),
                        usedforsecurity=False,
                    ).hexdigest()[:16]
                    texts_to_embed.append(f"{label}\n{excerpt}")
                    nodes.append(
                        ArtifactEvidenceNode(
                            evidence_key=evidence_key,
                            modality=modality,
                            label=label,
                            extracted_text=excerpt,
                            agent_id=self._agent_id,
                            task_id=query_context.task_id,
                            source_path=source_path,
                            source_url=source_url,
                            artifact_id=str(getattr(artifact.ref, "artifact_id", "") or ""),
                            confidence=float(getattr(evidence, "score_hint", 0.0) or 0.0),
                            trust_level="untrusted",
                            time_span=str(artifact.metadata.get("time_span", "")),
                            frame_ref=str(artifact.metadata.get("frame_ref", "")),
                            metadata={
                                "artifact_kind": getattr(artifact.ref.kind, "value", str(kind_value)),
                                "status": getattr(artifact.status, "value", ""),
                                "critical_for_action": bool(getattr(artifact, "critical_for_action", False)),
                                "project_key": query_context.project_key,
                                "workspace_fingerprint": query_context.workspace_fingerprint,
                                "source_hash": source_hash,
                            },
                        )
                    )

        embeddings = (
            await loop.run_in_executor(None, partial(self._embed_batch, texts_to_embed)) if texts_to_embed else []
        )
        for node, embedding in zip(nodes, embeddings, strict=True):
            node.metadata["embedding"] = embedding
        if nodes:
            self._storage_v2.persist_artifact_derivatives(
                task_id=query_context.task_id,
                derivatives=[
                    ArtifactDerivative(
                        derivative_key=node.evidence_key,
                        artifact_id=node.artifact_id,
                        modality=node.modality,
                        label=node.label,
                        extracted_text=node.extracted_text,
                        confidence=node.confidence,
                        trust_level=node.trust_level,
                        source_path=node.source_path,
                        source_url=node.source_url,
                        time_span=node.time_span,
                        frame_ref=node.frame_ref,
                        provenance=dict(node.metadata),
                    )
                    for node in nodes
                ],
            )

        relations = []
        for subject_key, subject_label, subject_summary in relation_entries:
            relations.append(
                (
                    subject_key,
                    subject_label,
                    subject_summary,
                )
            )
        graph_relations = self._build_artifact_graph_relations(
            query_context=query_context,
            nodes=nodes,
            relation_entries=relations,
        )
        self._graph_materializer.materialize_artifacts(nodes, graph_relations)
        return nodes

    def _resolve_with_strategy(
        self,
        *,
        query_context: KnowledgeQueryContext,
        strategy: RetrievalStrategy,
        experiment_plan: KnowledgeExperimentPlan,
        trace_role: TraceRole,
        hits: list[KnowledgeHit],
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

    async def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        async with self._model_lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer

                loop = asyncio.get_running_loop()
                self._model = await loop.run_in_executor(
                    None,
                    lambda: SentenceTransformer(KNOWLEDGE_EMBEDDING_MODEL),
                )
        return self._model

    def _embed_sync(self, text: str) -> list[float]:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(KNOWLEDGE_EMBEDDING_MODEL)
        result: list[float] = self._model.encode(text, normalize_embeddings=True).tolist()
        return result

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(KNOWLEDGE_EMBEDDING_MODEL)
        embeddings = self._model.encode(texts, normalize_embeddings=True)
        return [embedding.tolist() for embedding in embeddings]

    def _entry_matches_context(self, entry: KnowledgeEntry, query_context: KnowledgeQueryContext) -> bool:
        if entry.project_key and query_context.project_key and entry.project_key != query_context.project_key:
            return False
        if entry.environment and query_context.environment and entry.environment != query_context.environment:
            return False
        return not (entry.team and query_context.team and entry.team != query_context.team)

    def _allowed_layers(self) -> set[KnowledgeLayer]:
        allowed: set[KnowledgeLayer] = set()
        for layer in KNOWLEDGE_ALLOWED_LAYERS:
            try:
                allowed.add(KnowledgeLayer(str(layer)))
            except ValueError:
                continue
        return allowed or set(_LAYER_ORDER)

    def _requires_provenance_for(self, entry: KnowledgeEntry) -> bool:
        return entry.layer in {KnowledgeLayer.CANONICAL_POLICY, KnowledgeLayer.APPROVED_RUNBOOK}

    def _entry_allowed_by_runtime_policy(self, entry: KnowledgeEntry) -> bool:
        if entry.layer not in self._allowed_layers():
            return False
        age_days = max(0, (datetime.now() - entry.updated_at).days)
        if age_days > KNOWLEDGE_MAX_SOURCE_AGE_DAYS:
            return False
        if self._requires_provenance_for(entry):
            if KNOWLEDGE_REQUIRE_OWNER_PROVENANCE and not entry.owner.strip():
                return False
            if KNOWLEDGE_REQUIRE_FRESHNESS_PROVENANCE and entry.freshness_days <= 0:
                return False
        return True

    def _entry_allowed_by_access_scope(self, entry: KnowledgeEntry, query_context: KnowledgeQueryContext) -> bool:
        allowed_source_labels = tuple(query_context.allowed_source_labels or ())
        if allowed_source_labels and not any(
            fnmatch.fnmatch(entry.source_label, pattern) or entry.source_label == pattern
            for pattern in allowed_source_labels
        ):
            return False
        allowed_workspace_roots = tuple(query_context.allowed_workspace_roots or ())
        if entry.layer is KnowledgeLayer.WORKSPACE_DOC and allowed_workspace_roots:
            entry_path = str(entry.source_path or "")
            if not any(entry_path.startswith(root) for root in allowed_workspace_roots):
                return False
        return True

    def _conflict_key(self, entry: KnowledgeEntry) -> str:
        return f"{entry.scope.value}:{_normalize_key(entry.title)}"

    def _entry_entity_key(self, entry: KnowledgeEntry) -> str:
        return f"entry:{entry.layer.value}:{entry.id}"

    def _artifact_modality(self, kind: str) -> EvidenceModality:
        lowered = str(kind).lower()
        if lowered == "audio":
            return EvidenceModality.AUDIO_TRANSCRIPT
        if lowered == "video":
            return EvidenceModality.VIDEO_FRAME
        if lowered in {"image", "pdf"}:
            return EvidenceModality.OCR
        return EvidenceModality.TEXT

    def _build_artifact_graph_relations(
        self,
        *,
        query_context: KnowledgeQueryContext,
        nodes: list[ArtifactEvidenceNode],
        relation_entries: list[tuple[str, str, str]],
    ) -> list[Any]:
        if not KNOWLEDGE_GRAPH_ENABLED:
            return []
        from koda.knowledge.types import GraphRelation

        relations: list[GraphRelation] = []
        for subject_key, _subject_label, _subject_summary in relation_entries:
            for node in nodes:
                relations.append(
                    GraphRelation(
                        relation_key=f"supports:artifact_evidence:{node.evidence_key}:{subject_key}",
                        relation_type="supports",
                        source_entity_key=f"artifact_evidence:{node.evidence_key}",
                        target_entity_key=subject_key,
                        agent_id=self._agent_id,
                        metadata={"artifact_id": node.artifact_id, "task_id": query_context.task_id},
                    )
                )
        return relations

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

    def _load_pack_entries(self) -> list[KnowledgeEntry]:
        if self._storage_v2.external_read_enabled():
            return []
        if KnowledgeLayer.CANONICAL_POLICY not in self._allowed_layers():
            return []
        entries: list[KnowledgeEntry] = []
        inline_toml = os.environ.get("KNOWLEDGE_PACK_TOML", "").strip()
        if inline_toml:
            try:
                data = tomllib.loads(inline_toml)
            except tomllib.TOMLDecodeError:
                log.warning("knowledge_pack_inline_parse_failed")
                return entries
            return self._pack_entries_from_data(
                data,
                raw_text=inline_toml,
                pack_path=Path("<inline:knowledge_pack>"),
            )
        return entries

    def _pack_entries_from_data(
        self,
        data: dict[str, Any],
        *,
        raw_text: str,
        pack_path: Path,
    ) -> list[KnowledgeEntry]:
        entries: list[KnowledgeEntry] = []
        pack_agent_ids = [str(value).upper() for value in data.get("agent_ids", [])]
        if pack_agent_ids and self._agent_id and self._agent_id not in pack_agent_ids:
            return entries
        if pack_agent_ids and self._agent_id is None:
            return entries

        pack_id = str(data.get("pack_id", pack_path.stem))
        pack_owner = str(data.get("owner", ""))
        fallback_updated_at = datetime.now(UTC).replace(tzinfo=None)
        if pack_path.exists():
            fallback_updated_at = datetime.fromtimestamp(pack_path.stat().st_mtime)
        pack_updated_at = _parse_datetime(
            str(data.get("updated_at", "")),
            fallback=fallback_updated_at,
        )
        freshness_days = int(data.get("freshness_days", 180))
        project_key = str(data.get("project_key", ""))
        environment = str(data.get("environment", ""))
        team = str(data.get("team", ""))

        upsert_knowledge_source(
            source_key=f"pack:{pack_id}",
            agent_id=self._agent_id,
            project_key=project_key or None,
            source_type="knowledge_pack",
            layer=KnowledgeLayer.CANONICAL_POLICY.value,
            source_label=pack_path.name,
            source_path=str(pack_path),
            owner=pack_owner,
            freshness_days=freshness_days,
            content_hash=hashlib.sha256(raw_text.encode("utf-8"), usedforsecurity=False).hexdigest(),
            status="active",
            is_canonical=True,
            updated_at=pack_updated_at.isoformat(),
            stale_after=(pack_updated_at + timedelta(days=freshness_days)).isoformat(),
            invalid_after=(pack_updated_at + timedelta(days=freshness_days * 6)).isoformat(),
            sla_hours=24 * freshness_days,
            sync_mode="knowledge_pack",
            last_success_at=pack_updated_at.isoformat(),
        )

        for index, entry_data in enumerate(data.get("entries", [])):
            content = _normalize_text(str(entry_data.get("content", "")))
            if not content:
                continue
            scope_raw = str(entry_data.get("scope", "operational_policy"))
            try:
                scope = KnowledgeScope(scope_raw)
            except ValueError:
                scope = KnowledgeScope.OPERATIONAL_POLICY
            entry_id = str(entry_data.get("id", f"{pack_id}-{index}"))
            entry_title = str(entry_data.get("title", entry_id))
            entries.append(
                KnowledgeEntry(
                    id=entry_id,
                    title=entry_title,
                    content=content,
                    layer=KnowledgeLayer.CANONICAL_POLICY,
                    scope=scope,
                    source_label=pack_path.name,
                    source_path=str(pack_path),
                    updated_at=_parse_datetime(str(entry_data.get("updated_at", "")), fallback=pack_updated_at),
                    owner=str(entry_data.get("owner", pack_owner)),
                    pack_id=pack_id,
                    tags=[str(tag) for tag in entry_data.get("tags", [])],
                    criticality=str(entry_data.get("criticality", "high")),
                    freshness_days=int(entry_data.get("freshness_days", freshness_days)),
                    project_key=str(entry_data.get("project_key", project_key)),
                    environment=str(entry_data.get("environment", environment)),
                    team=str(entry_data.get("team", team)),
                    source_type="knowledge_pack",
                )
            )
        return entries

    def _resolve_workspace_path(self, workspace_dir: str | None) -> Path | None:
        if not workspace_dir:
            return None
        try:
            path = Path(workspace_dir).expanduser().resolve()
        except OSError:
            return None
        return path if path.exists() else None

    def _is_runtime_workspace(self, workspace_path: Path) -> bool:
        try:
            return workspace_path == RUNTIME_ROOT_DIR.resolve()
        except OSError:
            return False

    def _is_prompt_asset_path(self, file_path: Path) -> bool:
        return any(part.lower() == "prompts" for part in file_path.parts)

    def _iter_source_files(self, root: Path, patterns: list[str], max_files: int) -> list[Path]:
        files: list[Path] = []
        seen: set[Path] = set()
        for pattern in patterns:
            for candidate in sorted(root.glob(pattern)):
                if candidate in seen or not candidate.is_file():
                    continue
                if self._is_prompt_asset_path(candidate):
                    continue
                if any(part in _SKIPPED_WORKSPACE_DIR_NAMES for part in candidate.parts):
                    continue
                if candidate.suffix.lower() not in {".md", ".markdown", ".txt", ".rst"}:
                    continue
                seen.add(candidate)
                files.append(candidate)
                if len(files) >= max_files:
                    return files
        return files

    def _make_workspace_source_label(self, workspace_path: Path, file_path: Path) -> str:
        try:
            relative = str(file_path.relative_to(workspace_path))
        except ValueError:
            relative = file_path.name
        prefix = "runtime" if self._is_runtime_workspace(workspace_path) else "workspace"
        return f"{prefix}:{relative}"

    def _load_workspace_entries(self, query_context: KnowledgeQueryContext) -> list[KnowledgeEntry]:
        if KnowledgeLayer.WORKSPACE_DOC not in self._allowed_layers():
            return []
        workspace_path = self._resolve_workspace_path(query_context.workspace_dir)
        if workspace_path is None:
            return []

        entries: list[KnowledgeEntry] = []
        source_files = self._iter_source_files(
            workspace_path,
            (
                KNOWLEDGE_WORKSPACE_SOURCE_GLOBS
                if not self._is_runtime_workspace(workspace_path)
                else KNOWLEDGE_SOURCE_GLOBS
            ),
            KNOWLEDGE_WORKSPACE_MAX_FILES,
        )
        for path in source_files:
            try:
                raw_text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            updated_at = datetime.fromtimestamp(path.stat().st_mtime)
            source_label = self._make_workspace_source_label(workspace_path, path)
            upsert_knowledge_source(
                source_key=f"workspace:{path}",
                agent_id=self._agent_id,
                project_key=query_context.project_key or None,
                source_type="workspace_doc",
                layer=KnowledgeLayer.WORKSPACE_DOC.value,
                source_label=source_label,
                source_path=str(path),
                owner="workspace",
                freshness_days=90,
                content_hash=hashlib.sha256(raw_text.encode("utf-8"), usedforsecurity=False).hexdigest(),
                status="active",
                is_canonical=False,
                updated_at=updated_at.isoformat(),
                stale_after=(updated_at + timedelta(days=90)).isoformat(),
                invalid_after=(updated_at + timedelta(days=365)).isoformat(),
                sla_hours=24 * 7,
                sync_mode="workspace_scan",
                last_success_at=updated_at.isoformat(),
                workspace_fingerprint=query_context.workspace_fingerprint,
            )
            for index, chunk in enumerate(_chunk_text(path, raw_text)):
                entry_id = hashlib.sha256(
                    f"{path}:{index}:{chunk.title}".encode(),
                    usedforsecurity=False,
                ).hexdigest()[:16]
                entries.append(
                    KnowledgeEntry(
                        id=f"workspace-{entry_id}",
                        title=chunk.title,
                        content=chunk.text,
                        layer=KnowledgeLayer.WORKSPACE_DOC,
                        scope=_infer_repo_scope(path, chunk.title, chunk.text),
                        source_label=source_label,
                        source_path=str(path),
                        updated_at=updated_at,
                        owner="workspace",
                        criticality="medium",
                        freshness_days=90,
                        project_key=query_context.project_key,
                        environment=query_context.environment,
                        team=query_context.team,
                        source_type="workspace_doc",
                    )
                )
        return entries

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

    def _load_approved_runbook_entries(self, query_context: KnowledgeQueryContext) -> list[KnowledgeEntry]:
        if KnowledgeLayer.APPROVED_RUNBOOK not in self._allowed_layers():
            return []
        runbooks = list_approved_runbooks(
            agent_id=self._agent_id,
            task_kind=query_context.task_kind,
            project_key=query_context.project_key or None,
            environment=query_context.environment or None,
            team=query_context.team or None,
            limit=KNOWLEDGE_MAX_RESULTS,
        )
        entries: list[KnowledgeEntry] = []
        for runbook in runbooks:
            updated_at = _parse_datetime(
                str(runbook.get("last_validated_at") or runbook.get("approved_at")),
                fallback=datetime.now(),
            )
            verification = ", ".join(str(item) for item in runbook.get("verification", []))
            steps = "; ".join(str(item) for item in runbook.get("steps", [])[:5])
            prerequisites = ", ".join(str(item) for item in runbook.get("prerequisites", [])[:4])
            rollback = str(runbook.get("rollback") or "")
            content_parts = [str(runbook.get("summary") or "")]
            if prerequisites:
                content_parts.append(f"Prerequisites: {prerequisites}.")
            if steps:
                content_parts.append(f"Recommended steps: {steps}.")
            if verification:
                content_parts.append(f"Verification: {verification}.")
            if rollback:
                content_parts.append(f"Rollback: {rollback}.")
            content = _normalize_text(" ".join(part for part in content_parts if part))
            if not content:
                continue
            entries.append(
                KnowledgeEntry(
                    id=f"runbook-{runbook['id']}",
                    title=str(runbook["title"]),
                    content=content,
                    layer=KnowledgeLayer.APPROVED_RUNBOOK,
                    scope=KnowledgeScope.RUNBOOK,
                    source_label=f"runbook:{runbook['id']}",
                    source_path=f"approved_runbook:{runbook['id']}",
                    updated_at=updated_at,
                    owner=str(runbook.get("last_validated_by") or runbook.get("approved_by") or ""),
                    criticality="high",
                    freshness_days=180,
                    project_key=str(runbook.get("project_key") or ""),
                    environment=str(runbook.get("environment") or ""),
                    team=str(runbook.get("team") or ""),
                    source_type="approved_runbook",
                    operable=True,
                )
            )
        return entries

    async def _load_observed_pattern_entries(self, query_context: KnowledgeQueryContext) -> list[KnowledgeEntry]:
        if KnowledgeLayer.OBSERVED_PATTERN not in self._allowed_layers():
            return []
        if query_context.user_id is None or self._memory_store is None:
            return []
        if not hasattr(self._memory_store, "search"):
            return []

        patterns = await search_observed_patterns(
            self._memory_store,  # type: ignore[arg-type]
            query_context.query,
            query_context.user_id,
            max_results=KNOWLEDGE_MAX_OBSERVED_PATTERNS,
            task_kind=query_context.task_kind,
            project_key=query_context.project_key,
            environment=query_context.environment,
            team=query_context.team,
            owner=self._agent_id or "",
        )
        entries: list[KnowledgeEntry] = []
        for index, pattern in enumerate(patterns):
            metadata = pattern.metadata or {}
            entries.append(
                KnowledgeEntry(
                    id=f"observed-{query_context.user_id}-{index}",
                    title=f"Observed {metadata.get('task_kind') or query_context.task_kind}",
                    content=_normalize_text(pattern.content),
                    layer=KnowledgeLayer.OBSERVED_PATTERN,
                    scope=KnowledgeScope.RECENT_DECISION,
                    source_label=pattern.source_label,
                    source_path=pattern.source_label,
                    updated_at=pattern.updated_at,
                    owner=pattern.owner,
                    criticality="low",
                    freshness_days=60,
                    project_key=str(metadata.get("project_key") or query_context.project_key),
                    environment=str(metadata.get("environment") or query_context.environment),
                    team=str(metadata.get("team") or query_context.team),
                    source_type="observed_pattern",
                    operable=False,
                )
            )
        return entries
