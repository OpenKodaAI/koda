"""Semantic routing primitives for squad coordination.

This module deliberately uses the same local embedding model selected for
memory. It never downloads weights and it never falls back to lexical/hash
vectors for routing decisions: if the real model is unavailable, callers get a
closed, coordinator-only degradation signal.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from koda.config import (
    SQUAD_SEMANTIC_MIN_SCORE,
    SQUAD_SEMANTIC_NEGATIVE_PENALTY,
    SQUAD_SEMANTIC_ROUTING_ENABLED,
    SQUAD_SEMANTIC_TOP_K,
)
from koda.logging_config import get_logger
from koda.squads.capabilities import CapabilitySummary
from koda.squads.threads import ThreadDescriptor
from koda.utils.embeddings import (
    embed_batch_with_model,
    load_sentence_transformer,
    resolve_active_embedding_repo,
)

log = get_logger(__name__)

_VECTOR_CACHE_TTL_S = 300.0
_VECTOR_CACHE_MAX = 2048
_vector_cache: dict[tuple[str, str, str, str], tuple[float, list[float]]] = {}
_vector_cache_lock = threading.Lock()


@dataclass(frozen=True)
class SemanticAgentScore:
    agent_id: str
    score: float
    positive_score: float
    negative_score: float
    summary_text: str
    is_coordinator: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "score": round(self.score, 6),
            "positive_score": round(self.positive_score, 6),
            "negative_score": round(self.negative_score, 6),
            "summary_text": self.summary_text,
            "is_coordinator": self.is_coordinator,
        }


@dataclass(frozen=True)
class SemanticRoutingResult:
    available: bool
    model_name: str
    scores: list[SemanticAgentScore] = field(default_factory=list)
    reason: str = ""
    min_score: float = SQUAD_SEMANTIC_MIN_SCORE
    top_k: int = SQUAD_SEMANTIC_TOP_K

    @property
    def top_score(self) -> float:
        return self.scores[0].score if self.scores else 0.0

    def top_agents(
        self,
        *,
        include_coordinator: bool = False,
        min_score: float | None = None,
        limit: int | None = None,
    ) -> list[str]:
        threshold = self.min_score if min_score is None else float(min_score)
        cap = self.top_k if limit is None else max(1, int(limit))
        out: list[str] = []
        for item in self.scores:
            if item.score < threshold:
                continue
            if item.is_coordinator and not include_coordinator:
                continue
            out.append(item.agent_id)
            if len(out) >= cap:
                break
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "model_name": self.model_name,
            "reason": self.reason,
            "min_score": self.min_score,
            "top_k": self.top_k,
            "scores": [item.to_dict() for item in self.scores],
        }


@dataclass(frozen=True)
class CoordinationPlannerInput:
    text: str
    thread_id: str
    squad_id: str
    coordinator_agent_id: str
    participant_agent_ids: list[str]
    capability_summaries: list[CapabilitySummary]
    semantic_result: SemanticRoutingResult
    budget_usd_cap: float | None = None
    cost_usd_accum: float = 0.0
    parent_message_id: str | None = None
    recent_messages: list[dict[str, Any]] = field(default_factory=list)
    open_tasks: list[dict[str, Any]] = field(default_factory=list)
    awareness_agent_ids: list[str] = field(default_factory=list)
    contribution_proposals: list[dict[str, Any]] = field(default_factory=list)

    def to_prompt_payload(self) -> dict[str, Any]:
        summaries = {summary.agent_id: _summary_to_payload(summary) for summary in self.capability_summaries}
        return {
            "user_input": self.text,
            "thread_id": self.thread_id,
            "squad_id": self.squad_id,
            "coordinator_agent_id": self.coordinator_agent_id,
            "participant_agent_ids": list(self.participant_agent_ids),
            "budget": {
                "cap_usd": self.budget_usd_cap,
                "cost_usd_accum": self.cost_usd_accum,
            },
            "semantic_ranking": self.semantic_result.to_dict(),
            "capability_summaries": summaries,
            "awareness_agent_ids": list(self.awareness_agent_ids),
            "contribution_proposals": list(self.contribution_proposals),
            "recent_messages": list(self.recent_messages),
            "open_tasks": list(self.open_tasks),
        }


def reset_semantic_router_cache_for_tests() -> None:
    with _vector_cache_lock:
        _vector_cache.clear()


def capability_positive_text(summary: CapabilitySummary) -> str:
    return "\n".join(
        part
        for part in [
            f"agent_id: {summary.agent_id}",
            f"display_name: {summary.display_name}",
            f"role: {summary.role}" if summary.role else "",
            f"domains: {', '.join(summary.domains)}" if summary.domains else "",
            f"primary_outcomes: {'; '.join(summary.primary_outcomes)}" if summary.primary_outcomes else "",
            f"delegate_when: {summary.delegate_when}" if summary.delegate_when else "",
            f"tool_categories: {', '.join(summary.tool_categories)}" if summary.tool_categories else "",
        ]
        if part
    )


def capability_negative_text(summary: CapabilitySummary) -> str:
    return summary.do_not_delegate.strip()


def _summary_to_payload(summary: CapabilitySummary) -> dict[str, Any]:
    return {
        "agent_id": summary.agent_id,
        "display_name": summary.display_name,
        "role": summary.role,
        "domains": list(summary.domains),
        "primary_outcomes": list(summary.primary_outcomes),
        "tool_categories": list(summary.tool_categories),
        "delegate_when": summary.delegate_when,
        "do_not_delegate": summary.do_not_delegate,
        "is_coordinator": summary.is_coordinator,
    }


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    size = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(size))
    norm_a = math.sqrt(sum(a[i] * a[i] for i in range(size)))
    norm_b = math.sqrt(sum(b[i] * b[i] for i in range(size)))
    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _cache_get(key: tuple[str, str, str, str]) -> list[float] | None:
    now = time.monotonic()
    with _vector_cache_lock:
        existing = _vector_cache.get(key)
        if existing is None:
            return None
        expires_at, vector = existing
        if expires_at <= now:
            _vector_cache.pop(key, None)
            return None
        return vector


def _cache_put(key: tuple[str, str, str, str], vector: list[float]) -> None:
    now = time.monotonic()
    with _vector_cache_lock:
        _vector_cache[key] = (now + _VECTOR_CACHE_TTL_S, vector)
        if len(_vector_cache) > _VECTOR_CACHE_MAX:
            stale = [item_key for item_key, (expires_at, _) in _vector_cache.items() if expires_at <= now]
            for item_key in stale:
                _vector_cache.pop(item_key, None)
            while len(_vector_cache) > _VECTOR_CACHE_MAX:
                _vector_cache.pop(next(iter(_vector_cache)))


class SquadSemanticRouter:
    def __init__(
        self,
        *,
        top_k: int = SQUAD_SEMANTIC_TOP_K,
        min_score: float = SQUAD_SEMANTIC_MIN_SCORE,
        negative_penalty: float = SQUAD_SEMANTIC_NEGATIVE_PENALTY,
        enabled: bool = SQUAD_SEMANTIC_ROUTING_ENABLED,
        require_real_model: bool = True,
    ) -> None:
        self._top_k = max(1, int(top_k))
        self._min_score = float(min_score)
        self._negative_penalty = max(0.0, float(negative_penalty))
        self._enabled = bool(enabled)
        self._require_real_model = bool(require_real_model)

    async def rank_agents(
        self,
        text: str,
        capability_summaries: list[CapabilitySummary],
        *,
        squad_id: str,
        coordinator_agent_id: str | None = None,
    ) -> SemanticRoutingResult:
        clean_text = str(text or "").strip()
        model_name = resolve_active_embedding_repo()
        if not self._enabled:
            return SemanticRoutingResult(False, model_name, reason="semantic routing disabled")
        if not clean_text or not capability_summaries:
            return SemanticRoutingResult(False, model_name, reason="empty text or no capability summaries")

        model = await asyncio.to_thread(load_sentence_transformer, model_name)
        if model is None and self._require_real_model:
            return SemanticRoutingResult(False, model_name, reason="embedding model unavailable")

        positive_texts = {summary.agent_id: capability_positive_text(summary) for summary in capability_summaries}
        negative_texts = {summary.agent_id: capability_negative_text(summary) for summary in capability_summaries}
        cache_items: list[tuple[tuple[str, str, str, str], str]] = []
        vectors: dict[tuple[str, str], list[float]] = {}
        for summary in capability_summaries:
            text_pairs = (
                ("positive", positive_texts[summary.agent_id]),
                ("negative", negative_texts[summary.agent_id]),
            )
            for kind, text_value in text_pairs:
                if not text_value:
                    continue
                key = (model_name, squad_id, summary.agent_id, f"{kind}:{_hash_text(text_value)}")
                cached = _cache_get(key)
                if cached is not None:
                    vectors[(summary.agent_id, kind)] = cached
                else:
                    cache_items.append((key, text_value))

        batch_texts = [clean_text, *[item[1] for item in cache_items]]
        try:
            encoded = await asyncio.to_thread(embed_batch_with_model, batch_texts, model)
        except Exception as exc:  # noqa: BLE001
            log.warning("squad_semantic_router_embedding_failed", model_name=model_name, error=str(exc))
            return SemanticRoutingResult(False, model_name, reason=f"embedding failed: {type(exc).__name__}")

        query_vector = encoded[0]
        for (key, _), vector in zip(cache_items, encoded[1:], strict=True):
            _cache_put(key, vector)
            vectors[(key[2], key[3].split(":", 1)[0])] = vector

        scores: list[SemanticAgentScore] = []
        for summary in capability_summaries:
            positive_vector = vectors.get((summary.agent_id, "positive"))
            if positive_vector is None:
                continue
            positive_score = _cosine(query_vector, positive_vector)
            negative_vector = vectors.get((summary.agent_id, "negative"))
            negative_score = _cosine(query_vector, negative_vector) if negative_vector is not None else 0.0
            final_score = positive_score - (self._negative_penalty * max(0.0, negative_score))
            scores.append(
                SemanticAgentScore(
                    agent_id=summary.agent_id,
                    score=final_score,
                    positive_score=positive_score,
                    negative_score=negative_score,
                    summary_text=positive_texts[summary.agent_id],
                    is_coordinator=summary.agent_id == coordinator_agent_id or summary.is_coordinator,
                )
            )
        scores.sort(key=lambda item: (-item.score, item.agent_id))
        return SemanticRoutingResult(
            True,
            model_name,
            scores=scores[: self._top_k],
            min_score=self._min_score,
            top_k=self._top_k,
        )

    def should_coordinate(
        self,
        text: str,
        semantic_result: SemanticRoutingResult,
        *,
        has_coordinator: bool,
        reply_to_agent_id: str | None = None,
    ) -> bool:
        if not has_coordinator or not text.strip() or not semantic_result.available:
            return False
        if reply_to_agent_id and not semantic_result.top_agents(include_coordinator=False, limit=1):
            return False
        return bool(semantic_result.top_agents(include_coordinator=False, limit=1))

    def build_planner_input(
        self,
        *,
        text: str,
        thread: ThreadDescriptor,
        coordinator_agent_id: str,
        participant_agent_ids: list[str],
        capability_summaries: list[CapabilitySummary],
        semantic_result: SemanticRoutingResult,
        parent_message_id: str | None = None,
        recent_messages: list[dict[str, Any]] | None = None,
        open_tasks: list[dict[str, Any]] | None = None,
        awareness_agent_ids: list[str] | None = None,
        contribution_proposals: list[dict[str, Any]] | None = None,
    ) -> CoordinationPlannerInput:
        return CoordinationPlannerInput(
            text=text,
            thread_id=thread.id,
            squad_id=thread.squad_id,
            coordinator_agent_id=coordinator_agent_id,
            participant_agent_ids=list(participant_agent_ids),
            capability_summaries=list(capability_summaries),
            semantic_result=semantic_result,
            budget_usd_cap=float(thread.budget_usd_cap) if thread.budget_usd_cap is not None else None,
            cost_usd_accum=float(thread.cost_usd_accum or 0.0),
            parent_message_id=parent_message_id,
            recent_messages=list(recent_messages or []),
            open_tasks=list(open_tasks or []),
            awareness_agent_ids=list(awareness_agent_ids or []),
            contribution_proposals=list(contribution_proposals or []),
        )


_default_router: SquadSemanticRouter | None = None


def get_squad_semantic_router() -> SquadSemanticRouter:
    global _default_router  # noqa: PLW0603
    if _default_router is None:
        _default_router = SquadSemanticRouter()
    return _default_router
