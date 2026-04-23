"""Typed models for grounded knowledge retrieval."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class RetrievalStrategy(enum.StrEnum):
    """Available retrieval strategies for knowledge resolution."""

    BASELINE = "baseline"
    LANGGRAPH_CURRENT = "langgraph_current"
    GRAPH_ENRICHED = "graph_enriched"


class KnowledgeV2StorageMode(enum.StrEnum):
    """Operational storage mode for knowledge v2."""

    OFF = "off"
    PRIMARY = "primary"


class TraceRole(enum.StrEnum):
    """Role of one retrieval trace inside an experiment."""

    PRIMARY = "primary"


class EvidenceModality(enum.StrEnum):
    """Normalized evidence modalities tracked by retrieval and evaluation."""

    TEXT = "text"
    OCR = "ocr"
    AUDIO_TRANSCRIPT = "audio_transcript"
    VIDEO_FRAME = "video_frame"
    IMAGE_ANALYSIS = "image_analysis"


class EvaluationCaseStatus(enum.StrEnum):
    """Lifecycle status for curated evaluation cases."""

    DRAFT = "draft"
    VALIDATED = "validated"
    ARCHIVED = "archived"


class GoldSourceKind(enum.StrEnum):
    """How one evaluation case became authoritative."""

    APPROVED_RUNBOOK = "approved_runbook"
    MANUAL_GOLD = "manual_gold"
    HUMAN_CORRECTED_TASK = "human_corrected_task"
    NEGATIVE_CONTROL = "negative_control"


class KnowledgeScope(enum.StrEnum):
    """High-level source buckets shown to the model."""

    REPO_FACT = "repo_fact"
    OPERATIONAL_POLICY = "operational_policy"
    RUNBOOK = "runbook"
    RECENT_DECISION = "recent_decision"


class KnowledgeLayer(enum.StrEnum):
    """Ordered runtime layers for grounded retrieval."""

    CANONICAL_POLICY = "canonical_policy"
    APPROVED_RUNBOOK = "approved_runbook"
    WORKSPACE_DOC = "workspace_doc"
    OBSERVED_PATTERN = "observed_pattern"


class AutonomyTier(enum.StrEnum):
    """Operational autonomy tiers used by policy and reliability gates."""

    T0 = "t0"
    T1 = "t1"
    T2 = "t2"
    T3 = "t3"


@dataclass(slots=True)
class KnowledgeQueryContext:
    """Structured query context used to build layered knowledge."""

    query: str
    task_id: int | None = None
    agent_id: str | None = None
    user_id: int | None = None
    workspace_dir: str | None = None
    project_key: str = ""
    task_kind: str = "general"
    environment: str = ""
    team: str = ""
    autonomy_tier_target: AutonomyTier = AutonomyTier.T0
    workspace_fingerprint: str = ""
    task_risk: str = "medium"
    requires_write: bool = False
    retrieval_strategy: RetrievalStrategy | None = None
    allowed_source_labels: tuple[str, ...] = ()
    allowed_workspace_roots: tuple[str, ...] = ()


@dataclass(slots=True)
class KnowledgeEntry:
    """A single indexed knowledge entry or chunk."""

    id: str
    title: str
    content: str
    layer: KnowledgeLayer
    scope: KnowledgeScope
    source_label: str
    source_path: str
    updated_at: datetime
    owner: str = ""
    pack_id: str | None = None
    tags: list[str] = field(default_factory=list)
    criticality: str = "medium"
    freshness_days: int = 90
    project_key: str = ""
    environment: str = ""
    team: str = ""
    source_type: str = "document"
    operable: bool = True


@dataclass(slots=True)
class KnowledgeHit:
    """A retrieved knowledge entry with similarity metadata."""

    entry: KnowledgeEntry
    similarity: float
    freshness: str
    lexical_rank: int = -1
    dense_rank: int = -1
    graph_rank: int = -1
    lexical_score: float = 0.0
    dense_score: float = 0.0
    graph_hops: int = 0
    graph_score: float = 0.0
    graph_relation_types: tuple[str, ...] = ()
    evidence_modalities: tuple[EvidenceModality, ...] = ()
    reasons: tuple[str, ...] = ()

    def to_trace_dict(self) -> dict[str, object]:
        """Serialize the hit for audit traces."""
        return {
            "id": self.entry.id,
            "title": self.entry.title,
            "layer": self.entry.layer.value,
            "scope": self.entry.scope.value,
            "source_label": self.entry.source_label,
            "source_path": self.entry.source_path,
            "updated_at": self.entry.updated_at.date().isoformat(),
            "owner": self.entry.owner,
            "criticality": self.entry.criticality,
            "freshness": self.freshness,
            "similarity": round(self.similarity, 4),
            "lexical_rank": self.lexical_rank,
            "dense_rank": self.dense_rank,
            "graph_rank": self.graph_rank,
            "lexical_score": round(self.lexical_score, 4),
            "dense_score": round(self.dense_score, 4),
            "tags": self.entry.tags,
            "project_key": self.entry.project_key,
            "environment": self.entry.environment,
            "team": self.entry.team,
            "source_type": self.entry.source_type,
            "operable": self.entry.operable,
            "graph_hops": self.graph_hops,
            "graph_score": round(self.graph_score, 4),
            "graph_relation_types": list(self.graph_relation_types),
            "evidence_modalities": [modality.value for modality in self.evidence_modalities],
            "reasons": list(self.reasons),
        }


@dataclass(slots=True)
class CitationRequirement:
    """Expected citation for one winning source."""

    source_label: str
    updated_at: str
    layer: str
    required: bool = True


@dataclass(slots=True)
class ArtifactEvidenceMatch:
    """Supporting multimodal evidence matched to one grounded hit."""

    evidence_key: str
    modality: EvidenceModality
    label: str
    similarity: float
    confidence: float = 0.0
    trust_level: str = "untrusted"
    excerpt: str = ""


@dataclass(slots=True)
class RetrievalTraceHit:
    """Candidate or winning hit persisted for explainability."""

    hit_id: str
    title: str
    layer: str
    source_label: str
    similarity: float
    freshness: str
    selected: bool
    rank_before: int
    rank_after: int
    lexical_rank: int = -1
    dense_rank: int = -1
    graph_rank: int = -1
    lexical_score: float = 0.0
    dense_score: float = 0.0
    graph_hops: int = 0
    graph_score: float = 0.0
    graph_relation_types: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    exclusion_reason: str = ""
    evidence_modalities: tuple[EvidenceModality, ...] = ()
    supporting_evidence_keys: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "hit_id": self.hit_id,
            "title": self.title,
            "layer": self.layer,
            "source_label": self.source_label,
            "similarity": round(self.similarity, 4),
            "freshness": self.freshness,
            "selected": self.selected,
            "rank_before": self.rank_before,
            "rank_after": self.rank_after,
            "lexical_rank": self.lexical_rank,
            "dense_rank": self.dense_rank,
            "graph_rank": self.graph_rank,
            "lexical_score": round(self.lexical_score, 4),
            "dense_score": round(self.dense_score, 4),
            "graph_hops": self.graph_hops,
            "graph_score": round(self.graph_score, 4),
            "graph_relation_types": list(self.graph_relation_types),
            "reasons": list(self.reasons),
            "exclusion_reason": self.exclusion_reason,
            "evidence_modalities": [modality.value for modality in self.evidence_modalities],
            "supporting_evidence_keys": list(self.supporting_evidence_keys),
        }


@dataclass(slots=True)
class RetrievalTrace:
    """Persistable retrieval trace for one knowledge resolution."""

    strategy: RetrievalStrategy
    route: str
    query: str
    agent_id: str | None = None
    task_id: int | None = None
    project_key: str = ""
    environment: str = ""
    team: str = ""
    graph_hops: int = 0
    grounding_score: float = 0.0
    required_citation_count: int = 0
    conflict_reasons: tuple[str, ...] = ()
    evidence_modalities: tuple[EvidenceModality, ...] = ()
    winning_sources: tuple[str, ...] = ()
    hits: list[RetrievalTraceHit] = field(default_factory=list)
    explanation: str = ""
    experiment_key: str = ""
    trace_role: TraceRole = TraceRole.PRIMARY
    paired_trace_id: int | None = None
    trace_id: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "trace_id": self.trace_id,
            "strategy": self.strategy.value,
            "route": self.route,
            "query": self.query,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "project_key": self.project_key,
            "environment": self.environment,
            "team": self.team,
            "graph_hops": self.graph_hops,
            "grounding_score": round(self.grounding_score, 4),
            "required_citation_count": self.required_citation_count,
            "conflict_reasons": list(self.conflict_reasons),
            "evidence_modalities": [modality.value for modality in self.evidence_modalities],
            "winning_sources": list(self.winning_sources),
            "hits": [hit.to_dict() for hit in self.hits],
            "explanation": self.explanation,
            "experiment_key": self.experiment_key,
            "trace_role": self.trace_role.value,
            "paired_trace_id": self.paired_trace_id,
        }


@dataclass(slots=True)
class GraphEntity:
    """Persisted graph entity materialized from knowledge or artifacts."""

    entity_key: str
    entity_type: str
    label: str
    agent_id: str | None = None
    source_kind: str = "knowledge"
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class GraphRelation:
    """Persisted typed relation between graph entities."""

    relation_key: str
    relation_type: str
    source_entity_key: str
    target_entity_key: str
    agent_id: str | None = None
    weight: float = 1.0
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class ArtifactEvidenceNode:
    """Persisted multimodal evidence extracted from artifact dossiers."""

    evidence_key: str
    modality: EvidenceModality
    label: str
    extracted_text: str
    agent_id: str | None = None
    task_id: int | None = None
    source_path: str = ""
    source_url: str = ""
    artifact_id: str = ""
    confidence: float = 0.0
    trust_level: str = "untrusted"
    time_span: str = ""
    frame_ref: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class ArtifactDerivative:
    """Persistable derivative created from one raw multimodal artifact."""

    derivative_key: str
    artifact_id: str
    modality: EvidenceModality
    label: str
    extracted_text: str
    confidence: float = 0.0
    trust_level: str = "untrusted"
    source_path: str = ""
    source_url: str = ""
    time_span: str = ""
    frame_ref: str = ""
    provenance: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class CanonicalEntity:
    """Canonicalized entity linked from query text or evidence."""

    entity_key: str
    entity_type: str
    label: str
    aliases: tuple[str, ...] = ()
    confidence: float = 0.0
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class CanonicalRelation:
    """Canonical typed relation surfaced to retrieval and graph stores."""

    relation_key: str
    relation_type: str
    source_entity_key: str
    target_entity_key: str
    weight: float = 1.0
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class QueryEnvelope:
    """Normalized envelope used by retrieval v2 services."""

    query: str
    normalized_query: str
    agent_id: str | None = None
    task_id: int | None = None
    user_id: int | None = None
    task_kind: str = "general"
    project_key: str = ""
    environment: str = ""
    team: str = ""
    workspace_dir: str = ""
    workspace_fingerprint: str = ""
    requires_write: bool = False
    strategy: RetrievalStrategy = RetrievalStrategy.LANGGRAPH_CURRENT
    allowed_source_labels: tuple[str, ...] = ()
    allowed_workspace_roots: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class AnswerPlan:
    """Structured plan used to compose a grounded answer."""

    user_intent: str
    recommended_action_mode: str
    authoritative_sources: list[str] = field(default_factory=list)
    supporting_sources: list[str] = field(default_factory=list)
    required_verifications: list[str] = field(default_factory=list)
    open_conflicts: list[str] = field(default_factory=list)
    uncertainty_level: str = "low"

    def to_dict(self) -> dict[str, object]:
        return {
            "user_intent": self.user_intent,
            "recommended_action_mode": self.recommended_action_mode,
            "authoritative_sources": list(self.authoritative_sources),
            "supporting_sources": list(self.supporting_sources),
            "required_verifications": list(self.required_verifications),
            "open_conflicts": list(self.open_conflicts),
            "uncertainty_level": self.uncertainty_level,
        }


@dataclass(slots=True)
class AuthoritativeEvidence:
    """Evidence item allowed to anchor operational answers."""

    source_label: str
    layer: str
    title: str
    excerpt: str
    updated_at: str
    freshness: str
    score: float
    operable: bool = True
    rationale: str = ""
    evidence_modalities: tuple[EvidenceModality, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "source_label": self.source_label,
            "layer": self.layer,
            "title": self.title,
            "excerpt": self.excerpt,
            "updated_at": self.updated_at,
            "freshness": self.freshness,
            "score": round(self.score, 4),
            "operable": self.operable,
            "rationale": self.rationale,
            "evidence_modalities": [modality.value for modality in self.evidence_modalities],
        }


@dataclass(slots=True)
class SupportingEvidence:
    """Auxiliary evidence that can enrich, but not authorize, an answer."""

    ref_key: str
    label: str
    modality: EvidenceModality
    excerpt: str
    score: float
    confidence: float = 0.0
    trust_level: str = "untrusted"
    source_kind: str = "artifact"
    provenance: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "ref_key": self.ref_key,
            "label": self.label,
            "modality": self.modality.value,
            "excerpt": self.excerpt,
            "score": round(self.score, 4),
            "confidence": round(self.confidence, 4),
            "trust_level": self.trust_level,
            "source_kind": self.source_kind,
            "provenance": dict(self.provenance),
        }


@dataclass(slots=True)
class RetrievalBundle:
    """Structured retrieval result for graph-native and multimodal pipelines."""

    normalized_query: str
    query_intent: str
    route: str
    strategy: RetrievalStrategy
    selected_hits: list[KnowledgeHit] = field(default_factory=list)
    candidate_hits: list[KnowledgeHit] = field(default_factory=list)
    trace_hits: list[RetrievalTraceHit] = field(default_factory=list)
    authoritative_evidence: list[AuthoritativeEvidence] = field(default_factory=list)
    supporting_evidence: list[SupportingEvidence] = field(default_factory=list)
    linked_entities: list[CanonicalEntity] = field(default_factory=list)
    graph_relations: list[CanonicalRelation] = field(default_factory=list)
    subqueries: list[str] = field(default_factory=list)
    open_conflicts: list[str] = field(default_factory=list)
    uncertainty_notes: list[str] = field(default_factory=list)
    uncertainty_level: str = "low"
    recommended_action_mode: str = "read_only"
    required_verifications: list[str] = field(default_factory=list)
    graph_hops: int = 0
    grounding_score: float = 0.0
    answer_plan: AnswerPlan | None = None
    judge_result: AnswerJudgement | None = None
    effective_engine: str = ""
    fallback_used: bool = False
    explanation: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "normalized_query": self.normalized_query,
            "query_intent": self.query_intent,
            "route": self.route,
            "strategy": self.strategy.value,
            "selected_hits": [hit.to_trace_dict() for hit in self.selected_hits],
            "candidate_hits": [hit.to_trace_dict() for hit in self.candidate_hits],
            "trace_hits": [hit.to_dict() for hit in self.trace_hits],
            "authoritative_evidence": [item.to_dict() for item in self.authoritative_evidence],
            "supporting_evidence": [item.to_dict() for item in self.supporting_evidence],
            "linked_entities": [
                {
                    "entity_key": item.entity_key,
                    "entity_type": item.entity_type,
                    "label": item.label,
                    "aliases": list(item.aliases),
                    "confidence": round(item.confidence, 4),
                    "metadata": dict(item.metadata),
                }
                for item in self.linked_entities
            ],
            "graph_relations": [
                {
                    "relation_key": item.relation_key,
                    "relation_type": item.relation_type,
                    "source_entity_key": item.source_entity_key,
                    "target_entity_key": item.target_entity_key,
                    "weight": round(item.weight, 4),
                    "metadata": dict(item.metadata),
                }
                for item in self.graph_relations
            ],
            "subqueries": list(self.subqueries),
            "open_conflicts": list(self.open_conflicts),
            "uncertainty_notes": list(self.uncertainty_notes),
            "uncertainty_level": self.uncertainty_level,
            "recommended_action_mode": self.recommended_action_mode,
            "required_verifications": list(self.required_verifications),
            "graph_hops": self.graph_hops,
            "grounding_score": round(self.grounding_score, 4),
            "answer_plan": self.answer_plan.to_dict() if self.answer_plan is not None else {},
            "judge_result": self.judge_result.to_dict() if self.judge_result is not None else {},
            "effective_engine": self.effective_engine,
            "fallback_used": self.fallback_used,
            "explanation": self.explanation,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> RetrievalBundle:
        """Hydrate a retrieval bundle from a JSON-safe payload."""
        return cls(
            normalized_query=str(payload.get("normalized_query") or ""),
            query_intent=str(payload.get("query_intent") or ""),
            route=str(payload.get("route") or ""),
            strategy=_parse_retrieval_strategy(payload.get("strategy")),
            selected_hits=_parse_knowledge_hits(payload.get("selected_hits")),
            candidate_hits=_parse_knowledge_hits(payload.get("candidate_hits")),
            trace_hits=_parse_trace_hits(payload.get("trace_hits")),
            authoritative_evidence=_parse_authoritative_evidence(payload.get("authoritative_evidence")),
            supporting_evidence=_parse_supporting_evidence(payload.get("supporting_evidence")),
            linked_entities=_parse_linked_entities(payload.get("linked_entities")),
            graph_relations=_parse_graph_relations(payload.get("graph_relations")),
            subqueries=[str(item) for item in list(payload.get("subqueries") or [])],
            open_conflicts=[str(item) for item in list(payload.get("open_conflicts") or [])],
            uncertainty_notes=[str(item) for item in list(payload.get("uncertainty_notes") or [])],
            uncertainty_level=str(payload.get("uncertainty_level") or "low"),
            recommended_action_mode=str(payload.get("recommended_action_mode") or "read_only"),
            required_verifications=[str(item) for item in list(payload.get("required_verifications") or [])],
            graph_hops=_safe_int(payload.get("graph_hops")),
            grounding_score=_safe_float(payload.get("grounding_score")),
            answer_plan=_parse_answer_plan(payload.get("answer_plan")),
            judge_result=_parse_judge_result(payload.get("judge_result")),
            effective_engine=str(payload.get("effective_engine") or ""),
            fallback_used=bool(payload.get("fallback_used", False)),
            explanation=str(payload.get("explanation") or ""),
        )


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return datetime.fromtimestamp(0)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return datetime.fromtimestamp(0)


def _parse_retrieval_strategy(value: Any) -> RetrievalStrategy:
    text = str(value or RetrievalStrategy.LANGGRAPH_CURRENT.value).strip()
    try:
        return RetrievalStrategy(text)
    except ValueError:
        return RetrievalStrategy.LANGGRAPH_CURRENT


def _parse_modality(value: Any) -> EvidenceModality:
    text = str(value or EvidenceModality.TEXT.value).strip()
    try:
        return EvidenceModality(text)
    except ValueError:
        return EvidenceModality.TEXT


def _parse_knowledge_hits(raw_items: Any) -> list[KnowledgeHit]:
    items = raw_items if isinstance(raw_items, list) else []
    hits: list[KnowledgeHit] = []
    for raw_item in items:
        if not isinstance(raw_item, dict):
            continue
        layer_value = str(raw_item.get("layer") or KnowledgeLayer.WORKSPACE_DOC.value)
        scope_value = str(raw_item.get("scope") or KnowledgeScope.OPERATIONAL_POLICY.value)
        try:
            layer = KnowledgeLayer(layer_value)
        except ValueError:
            layer = KnowledgeLayer.WORKSPACE_DOC
        try:
            scope = KnowledgeScope(scope_value)
        except ValueError:
            scope = KnowledgeScope.OPERATIONAL_POLICY
        evidence_modalities = tuple(_parse_modality(item) for item in list(raw_item.get("evidence_modalities") or []))
        reasons = tuple(str(item) for item in list(raw_item.get("reasons") or []))
        hits.append(
            KnowledgeHit(
                entry=KnowledgeEntry(
                    id=str(raw_item.get("id") or raw_item.get("hit_id") or ""),
                    title=str(raw_item.get("title") or ""),
                    content=str(raw_item.get("content") or raw_item.get("snippet") or ""),
                    layer=layer,
                    scope=scope,
                    source_label=str(raw_item.get("source_label") or raw_item.get("source_id") or ""),
                    source_path=str(raw_item.get("source_path") or ""),
                    updated_at=_parse_dt(raw_item.get("updated_at")),
                    owner=str(raw_item.get("owner") or ""),
                    tags=[str(item) for item in list(raw_item.get("tags") or [])],
                    criticality=str(raw_item.get("criticality") or "medium"),
                    project_key=str(raw_item.get("project_key") or ""),
                    environment=str(raw_item.get("environment") or ""),
                    team=str(raw_item.get("team") or ""),
                    source_type=str(raw_item.get("source_type") or "document"),
                    operable=bool(raw_item.get("operable", True)),
                ),
                similarity=_safe_float(raw_item.get("similarity", raw_item.get("score"))),
                freshness=str(raw_item.get("freshness") or "fresh"),
                lexical_rank=_safe_int(raw_item.get("lexical_rank", -1)),
                dense_rank=_safe_int(raw_item.get("dense_rank", -1)),
                graph_rank=_safe_int(raw_item.get("graph_rank", -1)),
                lexical_score=_safe_float(raw_item.get("lexical_score")),
                dense_score=_safe_float(raw_item.get("dense_score")),
                graph_hops=_safe_int(raw_item.get("graph_hops")),
                graph_score=_safe_float(raw_item.get("graph_score")),
                graph_relation_types=tuple(str(item) for item in list(raw_item.get("graph_relation_types") or [])),
                evidence_modalities=evidence_modalities,
                reasons=reasons,
            )
        )
    return hits


def _parse_trace_hits(raw_items: Any) -> list[RetrievalTraceHit]:
    items = raw_items if isinstance(raw_items, list) else []
    trace_hits: list[RetrievalTraceHit] = []
    for raw_item in items:
        if not isinstance(raw_item, dict):
            continue
        trace_hits.append(
            RetrievalTraceHit(
                hit_id=str(raw_item.get("hit_id") or raw_item.get("id") or ""),
                title=str(raw_item.get("title") or ""),
                layer=str(raw_item.get("layer") or ""),
                source_label=str(raw_item.get("source_label") or raw_item.get("source_id") or ""),
                similarity=_safe_float(raw_item.get("similarity", raw_item.get("score"))),
                freshness=str(raw_item.get("freshness") or "fresh"),
                selected=bool(raw_item.get("selected", False)),
                rank_before=_safe_int(raw_item.get("rank_before")),
                rank_after=_safe_int(raw_item.get("rank_after")),
                lexical_rank=_safe_int(raw_item.get("lexical_rank", -1)),
                dense_rank=_safe_int(raw_item.get("dense_rank", -1)),
                graph_rank=_safe_int(raw_item.get("graph_rank", -1)),
                lexical_score=_safe_float(raw_item.get("lexical_score")),
                dense_score=_safe_float(raw_item.get("dense_score")),
                graph_hops=_safe_int(raw_item.get("graph_hops")),
                graph_score=_safe_float(raw_item.get("graph_score")),
                graph_relation_types=tuple(str(item) for item in list(raw_item.get("graph_relation_types") or [])),
                reasons=tuple(str(item) for item in list(raw_item.get("reasons") or [])),
                exclusion_reason=str(raw_item.get("exclusion_reason") or ""),
                evidence_modalities=tuple(
                    _parse_modality(item) for item in list(raw_item.get("evidence_modalities") or [])
                ),
                supporting_evidence_keys=tuple(
                    str(item) for item in list(raw_item.get("supporting_evidence_keys") or [])
                ),
            )
        )
    return trace_hits


def _parse_authoritative_evidence(raw_items: Any) -> list[AuthoritativeEvidence]:
    items = raw_items if isinstance(raw_items, list) else []
    return [
        AuthoritativeEvidence(
            source_label=str(item.get("source_label") or ""),
            layer=str(item.get("layer") or ""),
            title=str(item.get("title") or ""),
            excerpt=str(item.get("excerpt") or ""),
            updated_at=str(item.get("updated_at") or ""),
            freshness=str(item.get("freshness") or "fresh"),
            score=_safe_float(item.get("score")),
            operable=bool(item.get("operable", True)),
            rationale=str(item.get("rationale") or ""),
            evidence_modalities=tuple(_parse_modality(value) for value in list(item.get("evidence_modalities") or [])),
        )
        for item in items
        if isinstance(item, dict)
    ]


def _parse_supporting_evidence(raw_items: Any) -> list[SupportingEvidence]:
    items = raw_items if isinstance(raw_items, list) else []
    return [
        SupportingEvidence(
            ref_key=str(item.get("ref_key") or item.get("evidence_key") or ""),
            label=str(item.get("label") or ""),
            modality=_parse_modality(item.get("modality")),
            excerpt=str(item.get("excerpt") or ""),
            score=_safe_float(item.get("score")),
            confidence=_safe_float(item.get("confidence")),
            trust_level=str(item.get("trust_level") or "untrusted"),
            source_kind=str(item.get("source_kind") or "artifact"),
            provenance=dict(item.get("provenance") or {}),
        )
        for item in items
        if isinstance(item, dict)
    ]


def _parse_linked_entities(raw_items: Any) -> list[CanonicalEntity]:
    items = raw_items if isinstance(raw_items, list) else []
    return [
        CanonicalEntity(
            entity_key=str(item.get("entity_key") or ""),
            entity_type=str(item.get("entity_type") or ""),
            label=str(item.get("label") or ""),
            aliases=tuple(str(value) for value in list(item.get("aliases") or [])),
            confidence=_safe_float(item.get("confidence")),
            metadata=dict(item.get("metadata") or {}),
        )
        for item in items
        if isinstance(item, dict)
    ]


def _parse_graph_relations(raw_items: Any) -> list[CanonicalRelation]:
    items = raw_items if isinstance(raw_items, list) else []
    return [
        CanonicalRelation(
            relation_key=str(item.get("relation_key") or ""),
            relation_type=str(item.get("relation_type") or ""),
            source_entity_key=str(item.get("source_entity_key") or ""),
            target_entity_key=str(item.get("target_entity_key") or ""),
            weight=_safe_float(item.get("weight", 1.0)),
            metadata=dict(item.get("metadata") or {}),
        )
        for item in items
        if isinstance(item, dict)
    ]


def _parse_answer_plan(raw_value: Any) -> AnswerPlan | None:
    if not isinstance(raw_value, dict) or not raw_value:
        return None
    return AnswerPlan(
        user_intent=str(raw_value.get("user_intent") or ""),
        recommended_action_mode=str(raw_value.get("recommended_action_mode") or "read_only"),
        authoritative_sources=[str(item) for item in list(raw_value.get("authoritative_sources") or [])],
        supporting_sources=[str(item) for item in list(raw_value.get("supporting_sources") or [])],
        required_verifications=[str(item) for item in list(raw_value.get("required_verifications") or [])],
        open_conflicts=[str(item) for item in list(raw_value.get("open_conflicts") or [])],
        uncertainty_level=str(raw_value.get("uncertainty_level") or "low"),
    )


def _parse_judge_result(raw_value: Any) -> AnswerJudgement | None:
    if not isinstance(raw_value, dict) or not raw_value:
        return None
    metrics = raw_value.get("metrics")
    return AnswerJudgement(
        status=str(raw_value.get("status") or "passed"),
        reasons=[str(item) for item in list(raw_value.get("reasons") or [])],
        warnings=[str(item) for item in list(raw_value.get("warnings") or [])],
        citation_coverage=_safe_float(raw_value.get("citation_coverage")),
        citation_span_precision=_safe_float(raw_value.get("citation_span_precision")),
        contradiction_escape_rate=_safe_float(raw_value.get("contradiction_escape_rate")),
        policy_compliance=_safe_float(raw_value.get("policy_compliance", 1.0)),
        uncertainty_marked=bool(raw_value.get("uncertainty_marked", False)),
        requires_review=bool(raw_value.get("requires_review", False)),
        safe_response=str(raw_value.get("safe_response") or ""),
        metrics=({str(key): _safe_float(value) for key, value in metrics.items()} if isinstance(metrics, dict) else {}),
    )


@dataclass(slots=True)
class EvaluationCase:
    """Curated evaluation case for replay and scoring."""

    case_key: str
    query: str
    agent_id: str | None = None
    source_task_id: int | None = None
    task_kind: str = "general"
    project_key: str = ""
    environment: str = ""
    team: str = ""
    modality: str = "text"
    expected_sources: tuple[str, ...] = ()
    expected_layers: tuple[str, ...] = ()
    reference_answer: str = ""
    status: EvaluationCaseStatus = EvaluationCaseStatus.DRAFT
    gold_source_kind: GoldSourceKind = GoldSourceKind.MANUAL_GOLD
    validated_by: str = ""
    validated_at: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class EvaluationRun:
    """Result of replaying one evaluation case with one strategy."""

    case_key: str
    strategy: RetrievalStrategy
    agent_id: str | None = None
    retrieval_trace_id: int | None = None
    recall_at_k: float = 0.0
    ndcg_at_k: float = 0.0
    citation_accuracy: float = 0.0
    groundedness_precision: float = 0.0
    conflict_detection_rate: float = 0.0
    verification_before_finalize_rate: float = 0.0
    human_correction_rate: float = 0.0
    task_success_proxy: float = 0.0
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class GroundedAnswer:
    """Internal structured answer envelope produced after synthesis."""

    answer_text: str
    operational_status: str
    citations: list[dict[str, object]] = field(default_factory=list)
    supporting_evidence_refs: list[str] = field(default_factory=list)
    uncertainty_notes: list[str] = field(default_factory=list)
    answer_plan: dict[str, object] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "answer_text": self.answer_text,
            "operational_status": self.operational_status,
            "citations": list(self.citations),
            "supporting_evidence_refs": list(self.supporting_evidence_refs),
            "uncertainty_notes": list(self.uncertainty_notes),
            "answer_plan": dict(self.answer_plan),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class AnswerJudgement:
    """Structured post-answer judgement with blocking and quality metrics."""

    status: str = "passed"
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    citation_coverage: float = 0.0
    citation_span_precision: float = 0.0
    contradiction_escape_rate: float = 0.0
    policy_compliance: float = 1.0
    uncertainty_marked: bool = False
    requires_review: bool = False
    safe_response: str = ""
    metrics: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
            "citation_coverage": round(self.citation_coverage, 4),
            "citation_span_precision": round(self.citation_span_precision, 4),
            "contradiction_escape_rate": round(self.contradiction_escape_rate, 4),
            "policy_compliance": round(self.policy_compliance, 4),
            "uncertainty_marked": self.uncertainty_marked,
            "requires_review": self.requires_review,
            "safe_response": self.safe_response,
            "metrics": {key: round(float(value), 4) for key, value in self.metrics.items()},
        }


@dataclass(slots=True)
class EvaluationBenchmark:
    """Aggregated benchmark summary for one evaluation run set."""

    strategy: RetrievalStrategy
    case_count: int
    metrics: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "strategy": self.strategy.value,
            "case_count": self.case_count,
            "metrics": {key: round(float(value), 4) for key, value in self.metrics.items()},
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class KnowledgeAnswerEvaluation:
    """Final grounded answer evaluation after the model has responded."""

    citation_coverage: float = 0.0
    grounding_score: float = 0.0
    missing_citations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    gate_status: str = "passed"
    gate_reasons: list[str] = field(default_factory=list)
    requires_review: bool = False
    blocking: bool = False


@dataclass(slots=True)
class GroundingGateDecision:
    """Decision envelope used by the runtime before finalizing a task."""

    status: str = "passed"
    reasons: list[str] = field(default_factory=list)
    requires_review: bool = False
    safe_response: str = ""


@dataclass(slots=True, frozen=True)
class EffectiveExecutionPolicy:
    """Resolved execution envelope used by the queue manager and write gate."""

    task_kind: str
    autonomy_tier: AutonomyTier = AutonomyTier.T0
    approval_mode: str = "read_only"
    min_read_evidence: int = 1
    required_layers: tuple[KnowledgeLayer, ...] = ()
    required_verifications: tuple[str, ...] = ()
    requires_rollback: bool = False
    requires_probable_cause: bool = False
    max_source_age_days: int = 90

    @property
    def read_only(self) -> bool:
        return self.approval_mode == "read_only"

    @property
    def escalation_required(self) -> bool:
        return self.approval_mode == "escalation_required"


@dataclass(slots=True)
class KnowledgeGuardrail:
    """High-risk caution that should influence the write gate, not normal retrieval ranking."""

    id: str
    title: str
    task_kind: str
    severity: str
    reason: str
    source_label: str
    project_key: str = ""
    environment: str = ""
    team: str = ""
    source_kind: str = "approved_guardrail"


@dataclass(slots=True)
class KnowledgeConflict:
    """Conflict detected between layers after deterministic filtering."""

    title: str
    higher_layer: KnowledgeLayer
    lower_layer: KnowledgeLayer
    higher_source_label: str
    lower_source_label: str


@dataclass(slots=True)
class KnowledgeResolution:
    """Full grounded retrieval result used by orchestration."""

    context: str
    context_blocks: list[str] = field(default_factory=list)
    hits: list[KnowledgeHit] = field(default_factory=list)
    retrieval_route: str = "global"
    retrieval_strategy: RetrievalStrategy = RetrievalStrategy.LANGGRAPH_CURRENT
    trace_id: int | None = None
    trace: RetrievalTrace | None = None
    experiment_key: str = ""
    trace_role: TraceRole = TraceRole.PRIMARY
    paired_trace_id: int | None = None
    guardrails: list[KnowledgeGuardrail] = field(default_factory=list)
    conflicts: list[KnowledgeConflict] = field(default_factory=list)
    conflict_reasons: list[str] = field(default_factory=list)
    ungrounded_operationally: bool = False
    stale_sources_present: bool = False
    graph_hops: int = 0
    citation_requirements: list[CitationRequirement] = field(default_factory=list)
    grounding_score: float = 0.0
    retrieval_grounding_score: float = 0.0
    evidence_modalities: list[EvidenceModality] = field(default_factory=list)
    supporting_evidence_modalities: list[EvidenceModality] = field(default_factory=list)
    supporting_evidence: list[ArtifactEvidenceMatch] = field(default_factory=list)
    authoritative_sources: list[AuthoritativeEvidence] = field(default_factory=list)
    supporting_sources: list[SupportingEvidence] = field(default_factory=list)
    linked_entities: list[CanonicalEntity] = field(default_factory=list)
    graph_relations: list[CanonicalRelation] = field(default_factory=list)
    query_intent: str = ""
    answer_plan: dict[str, Any] = field(default_factory=dict)
    retrieval_bundle: RetrievalBundle | None = None
    winning_sources: list[str] = field(default_factory=list)
    required_citation_count: int = 0
    citation_coverage: float = 0.0
    backend_unavailable: bool = False
    backend_failure_reason: str = ""
    answer_evaluation: KnowledgeAnswerEvaluation | None = None
    grounded_answer: GroundedAnswer | None = None
    answer_judgement: AnswerJudgement | None = None
