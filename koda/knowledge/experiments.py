"""Execution-plan coordination for the Rust-authoritative retrieval path."""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass

from koda.knowledge.config import KNOWLEDGE_TRACE_SAMPLING_RATE
from koda.knowledge.types import KnowledgeQueryContext, RetrievalStrategy


def _coerce_strategy(value: object | None) -> RetrievalStrategy | None:
    if value in (None, ""):
        return None
    try:
        return RetrievalStrategy(str(value))
    except ValueError:
        return None


@dataclass(slots=True, frozen=True)
class KnowledgeExperimentPlan:
    """Execution plan for one authoritative retrieval query."""

    experiment_key: str
    primary_strategy: RetrievalStrategy
    persist_primary_trace: bool


class KnowledgeExperimentService:
    """Encapsulate primary-strategy selection and trace sampling."""

    def __init__(self, *, trace_sampling_rate: float = KNOWLEDGE_TRACE_SAMPLING_RATE) -> None:
        self._trace_sampling_rate = max(0.0, min(1.0, float(trace_sampling_rate)))

    def plan(self, query_context: KnowledgeQueryContext) -> KnowledgeExperimentPlan:
        primary_strategy = _coerce_strategy(query_context.retrieval_strategy) or RetrievalStrategy.LANGGRAPH_CURRENT
        trace_sampled = self._sample(self._trace_sampling_rate)
        experiment_key = f"kgx_{uuid.uuid4().hex[:12]}" if trace_sampled else ""
        return KnowledgeExperimentPlan(
            experiment_key=experiment_key,
            primary_strategy=primary_strategy,
            persist_primary_trace=trace_sampled,
        )

    def _sample(self, rate: float) -> bool:
        if rate <= 0.0:
            return False
        if rate >= 1.0:
            return True
        return random.random() < rate
