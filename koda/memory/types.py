"""Memory system data types."""

from __future__ import annotations

import enum
import hashlib
from dataclasses import dataclass, field
from datetime import datetime


class MemoryType(enum.StrEnum):
    """Types of extractable memories."""

    FACT = "fact"
    EVENT = "event"
    PREFERENCE = "preference"
    DECISION = "decision"
    PROBLEM = "problem"
    COMMIT = "commit"
    RELATIONSHIP = "relationship"
    TASK = "task"
    PROCEDURE = "procedure"


class MemoryStatus(enum.StrEnum):
    """Lifecycle states for canonical memories."""

    ACTIVE = "active"
    STALE = "stale"
    SUPERSEDED = "superseded"
    INVALIDATED = "invalidated"
    REJECTED = "rejected"


class MemoryLayer(enum.StrEnum):
    """Prompt/runtime layers used when composing recall context."""

    EPISODIC = "episodic"
    PROCEDURAL = "procedural"
    CONVERSATIONAL = "conversational"
    PROACTIVE = "proactive"


# Default TTL in days per memory type
DEFAULT_TTL_DAYS: dict[MemoryType, int] = {
    MemoryType.FACT: 730,
    MemoryType.EVENT: 365,
    MemoryType.PREFERENCE: 730,
    MemoryType.DECISION: 730,
    MemoryType.PROBLEM: 365,
    MemoryType.COMMIT: 365,
    MemoryType.RELATIONSHIP: 730,
    MemoryType.TASK: 90,
    MemoryType.PROCEDURE: 365,
}


DEFAULT_ORIGIN_KIND = "conversation"
DEFAULT_EMBEDDING_STATUS = "pending"
DEFAULT_MEMORY_STATUS = MemoryStatus.ACTIVE.value


def build_content_hash(content: str, memory_type: MemoryType | None = None) -> str:
    """Build a stable hash for deduplication and audit provenance."""
    normalized = " ".join(content.split()).strip().lower()
    if memory_type is not None:
        normalized = f"{memory_type.value}|{normalized}"
    return hashlib.sha256(normalized.encode("utf-8"), usedforsecurity=False).hexdigest()


def build_conflict_key(
    memory_type: MemoryType,
    *,
    subject: str = "",
    project_key: str = "",
    environment: str = "",
    team: str = "",
) -> str:
    """Build a stable conflict key so newer memories can supersede stale ones."""
    normalized_subject = " ".join(subject.split()).strip().lower()
    normalized_scope = "|".join(
        [
            memory_type.value,
            normalized_subject,
            project_key.strip().lower(),
            environment.strip().lower(),
            team.strip().lower(),
        ]
    )
    return hashlib.sha256(normalized_scope.encode("utf-8"), usedforsecurity=False).hexdigest()[:24]


@dataclass
class Memory:
    """A single memory entry."""

    user_id: int
    memory_type: MemoryType
    content: str
    importance: float = 0.5
    source_query_id: int | None = None
    session_id: str | None = None
    agent_id: str | None = None
    origin_kind: str = DEFAULT_ORIGIN_KIND
    source_task_id: int | None = None
    source_episode_id: int | None = None
    project_key: str = ""
    environment: str = ""
    team: str = ""
    quality_score: float = 0.5
    extraction_confidence: float = 0.5
    embedding_status: str = DEFAULT_EMBEDDING_STATUS
    content_hash: str = ""
    claim_kind: str = ""
    subject: str = ""
    decision_source: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    applicability_scope: dict[str, str] = field(default_factory=dict)
    valid_until: datetime | None = None
    conflict_key: str = ""
    supersedes_memory_id: int | None = None
    memory_status: str = DEFAULT_MEMORY_STATUS
    retention_reason: str = ""
    embedding_attempts: int = 0
    embedding_last_error: str = ""
    embedding_retry_at: datetime | None = None
    access_count: int = 0
    last_accessed: datetime | None = None
    last_recalled_at: datetime | None = None
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime | None = None
    is_active: bool = True
    metadata: dict[str, object] = field(default_factory=dict)
    vector_ref_id: str | None = None
    id: int | None = None

    def __post_init__(self) -> None:
        if not self.content_hash:
            self.content_hash = build_content_hash(self.content, self.memory_type)
        if not self.subject:
            self.subject = " ".join(self.content.split()[:8]).strip()
        if not self.conflict_key and self.subject:
            self.conflict_key = build_conflict_key(
                self.memory_type,
                subject=self.subject,
                project_key=self.project_key,
                environment=self.environment,
                team=self.team,
            )
        if not self.applicability_scope:
            self.applicability_scope = {
                "project_key": self.project_key,
                "environment": self.environment,
                "team": self.team,
            }


@dataclass
class RecallResult:
    """A memory with relevance scoring."""

    memory: Memory
    relevance_score: float  # Vector distance (lower = more similar)
    combined_score: float = 0.0  # weighted: 0.60*relevance + 0.25*importance + 0.15*recency + access_boost
    retrieval_source: str = "vector"
    layer: str = MemoryLayer.CONVERSATIONAL.value
    scope_score: float = 0.0
    score_breakdown: dict[str, float] = field(default_factory=dict)
    selection_reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RecallDiscard:
    """A candidate that was considered but not injected into prompt context."""

    memory_id: int | None
    content_preview: str
    layer: str
    retrieval_source: str
    reason: str
    score: float


@dataclass(slots=True)
class RecallExplanation:
    """Explain why one memory was selected for the current turn."""

    memory_id: int | None
    layer: str
    retrieval_source: str
    score: float
    scope_score: float
    reasons: list[str] = field(default_factory=list)
    source_query_id: int | None = None
    source_task_id: int | None = None
    source_episode_id: int | None = None


@dataclass(slots=True)
class RecallConflict:
    """Summarize how one conflict group was resolved during recall."""

    conflict_key: str
    winner_memory_id: int | None
    loser_memory_ids: list[int | None] = field(default_factory=list)
    winner_layer: str = MemoryLayer.CONVERSATIONAL.value
    winner_retrieval_source: str = "vector"
    winner_score: float = 0.0


@dataclass(slots=True)
class MemoryResolution:
    """Prompt-ready recall envelope with audit and trust metadata."""

    context: str
    considered: list[RecallResult] = field(default_factory=list)
    selected: list[RecallResult] = field(default_factory=list)
    discarded: list[RecallDiscard] = field(default_factory=list)
    conflicts: list[RecallConflict] = field(default_factory=list)
    explanations: list[RecallExplanation] = field(default_factory=list)
    trust_score: float = 0.0
    selected_layers: list[str] = field(default_factory=list)
    retrieval_sources: list[str] = field(default_factory=list)
