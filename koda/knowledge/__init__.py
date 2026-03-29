"""Sourced knowledge retrieval for grounded responses."""

from __future__ import annotations

from koda.knowledge.manager import KnowledgeManager
from koda.knowledge.policy import (
    ExecutionPolicy,
    classify_task_kind,
    default_execution_policy,
    sanitize_policy_overrides,
)
from koda.knowledge.types import (
    AnswerJudgement,
    AnswerPlan,
    ArtifactDerivative,
    ArtifactEvidenceMatch,
    ArtifactEvidenceNode,
    AuthoritativeEvidence,
    AutonomyTier,
    CanonicalEntity,
    CanonicalRelation,
    CitationRequirement,
    EffectiveExecutionPolicy,
    EvaluationBenchmark,
    EvaluationCase,
    EvaluationCaseStatus,
    EvaluationRun,
    EvidenceModality,
    GoldSourceKind,
    GraphEntity,
    GraphRelation,
    GroundedAnswer,
    GroundingGateDecision,
    KnowledgeAnswerEvaluation,
    KnowledgeConflict,
    KnowledgeGuardrail,
    KnowledgeQueryContext,
    KnowledgeResolution,
    KnowledgeV2StorageMode,
    QueryEnvelope,
    RetrievalBundle,
    RetrievalStrategy,
    RetrievalTrace,
    RetrievalTraceHit,
    SupportingEvidence,
    TraceRole,
)

_manager: KnowledgeManager | None = None


def get_knowledge_manager() -> KnowledgeManager:
    """Get or create the singleton KnowledgeManager."""
    global _manager
    if _manager is None:
        from koda.config import AGENT_ID

        _manager = KnowledgeManager(AGENT_ID)
    return _manager


__all__ = [
    "AutonomyTier",
    "AnswerPlan",
    "AnswerJudgement",
    "ArtifactDerivative",
    "ArtifactEvidenceNode",
    "ArtifactEvidenceMatch",
    "AuthoritativeEvidence",
    "CanonicalEntity",
    "CanonicalRelation",
    "CitationRequirement",
    "EffectiveExecutionPolicy",
    "EvaluationBenchmark",
    "ExecutionPolicy",
    "EvaluationCase",
    "EvaluationCaseStatus",
    "EvaluationRun",
    "EvidenceModality",
    "GoldSourceKind",
    "GroundedAnswer",
    "GraphEntity",
    "GraphRelation",
    "GroundingGateDecision",
    "KnowledgeAnswerEvaluation",
    "KnowledgeConflict",
    "KnowledgeGuardrail",
    "KnowledgeManager",
    "KnowledgeQueryContext",
    "KnowledgeResolution",
    "KnowledgeV2StorageMode",
    "QueryEnvelope",
    "RetrievalBundle",
    "RetrievalStrategy",
    "RetrievalTrace",
    "RetrievalTraceHit",
    "SupportingEvidence",
    "TraceRole",
    "classify_task_kind",
    "default_execution_policy",
    "get_knowledge_manager",
    "sanitize_policy_overrides",
]
