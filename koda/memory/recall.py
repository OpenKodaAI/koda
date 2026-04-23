"""Memory recall: hybrid retrieval, episodic replay, ranking, and audit envelope."""

from __future__ import annotations

import collections
import hashlib
import math
import time as _time
from datetime import datetime

from koda.logging_config import get_logger
from koda.memory.config import (
    MEMORY_MAX_CONTEXT_TOKENS,
    MEMORY_MAX_RECALL,
    MEMORY_RECALL_THRESHOLD,
    MEMORY_RECENCY_HALF_LIFE_DAYS,
)
from koda.memory.napkin import get_recent_high_importance, log_memory_recall_audit
from koda.memory.procedural import build_procedural_context as _build_procedural_context
from koda.memory.profile import MemoryProfile
from koda.memory.prompts import PROACTIVE_HEADER, RECALL_HEADER, RECALL_TYPE_HEADERS
from koda.memory.quality import record_conflict_resolution, record_memory_quality_counter
from koda.memory.store import MemoryStore
from koda.memory.types import (
    Memory,
    MemoryLayer,
    MemoryResolution,
    RecallConflict,
    RecallDiscard,
    RecallExplanation,
    RecallResult,
)

log = get_logger(__name__)

_CHARS_PER_TOKEN = 4
_recall_cache: collections.OrderedDict[str, tuple[float, MemoryResolution]] = collections.OrderedDict()
_CACHE_TTL = 300
_CACHE_MAX = 100
_TYPE_ORDER = ["event", "fact", "task", "procedure", "decision", "problem", "preference", "commit", "relationship"]


def _cache_key(
    query: str,
    user_id: int,
    *,
    agent_id: str = "default",
    session_id: str | None = None,
    project_key: str = "",
    environment: str = "",
    team: str = "",
    source_query_id: int | None = None,
    source_task_id: int | None = None,
    source_episode_id: int | None = None,
) -> str:
    h = hashlib.sha256(query[:500].encode(), usedforsecurity=False).hexdigest()[:16]
    scope = "|".join(
        [
            agent_id,
            session_id or "",
            project_key,
            environment,
            team,
            str(source_query_id or ""),
            str(source_task_id or ""),
            str(source_episode_id or ""),
        ]
    )
    return f"{user_id}:{scope}:{h}"


def _retrieval_bonus(result: RecallResult) -> float:
    return {
        "query_link": 0.35,
        "task_link": 0.22,
        "episode": 0.14,
        "session": 0.08,
        "vector": 0.0,
        "exact": 0.0,
    }.get(result.retrieval_source, 0.0)


def clear_recall_cache(user_id: int | None = None) -> None:
    """Invalidate cached recall results. If user_id given, only that user's entries."""
    if user_id is None:
        _recall_cache.clear()
        return
    to_remove = [k for k in _recall_cache if k.startswith(f"{user_id}:")]
    for k in to_remove:
        del _recall_cache[k]


def _recency_factor(created_at: datetime, half_life_days: float | None = None) -> float:
    if half_life_days is None:
        half_life_days = MEMORY_RECENCY_HALF_LIFE_DAYS
    age_days = (datetime.now() - created_at).total_seconds() / 86400
    return math.exp(-0.693 * age_days / half_life_days)


def _scope_reason(
    memory: Memory,
    *,
    session_id: str | None,
    project_key: str,
    environment: str,
    team: str,
) -> tuple[float, list[str]]:
    boost = 0.0
    reasons: list[str] = []
    if session_id and memory.session_id and memory.session_id == session_id:
        boost += 0.08
        reasons.append("same_session")
    if project_key and memory.project_key == project_key:
        boost += 0.07
        reasons.append("same_project")
    if environment and memory.environment == environment:
        boost += 0.04
        reasons.append("same_environment")
    if team and memory.team == team:
        boost += 0.03
        reasons.append("same_team")
    if memory.source_episode_id is not None:
        boost += 0.05
        reasons.append("episodic_bundle")
    return boost, reasons


def _compute_combined_score(
    result: RecallResult,
    profile: MemoryProfile | None = None,
    *,
    session_id: str | None = None,
    project_key: str = "",
    environment: str = "",
    team: str = "",
) -> float:
    relevance = max(0.0, 1.0 - result.relevance_score)
    importance = result.memory.importance
    quality = result.memory.quality_score
    recency = _recency_factor(result.memory.created_at)
    access_boost = min(0.05, result.memory.access_count * 0.01)
    type_weight = profile.recall_weight_for(result.memory.memory_type) if profile else 1.0
    scope_boost, scope_reasons = _scope_reason(
        result.memory,
        session_id=session_id,
        project_key=project_key,
        environment=environment,
        team=team,
    )
    result.scope_score = scope_boost
    inferred_layer = _infer_layer(result)
    preferred_layer_boost = min(0.10, profile.preferred_layer_weight(inferred_layer) if profile else 0.0)
    retrieval_boost = _retrieval_bonus(result)
    result.score_breakdown = {
        "relevance": round(relevance, 4),
        "importance": round(importance, 4),
        "quality": round(quality, 4),
        "recency": round(recency, 4),
        "access_boost": round(access_boost, 4),
        "scope_boost": round(scope_boost, 4),
        "retrieval_boost": round(retrieval_boost, 4),
        "preferred_layer_boost": round(preferred_layer_boost, 4),
        "type_weight": round(type_weight, 4),
    }
    result.selection_reasons = [
        *scope_reasons,
        *(["preferred_layer"] if preferred_layer_boost else []),
        *(["linked_recall"] if retrieval_boost else []),
    ]
    base = (0.55 * relevance) + (0.20 * importance) + (0.15 * recency) + (0.10 * quality) + access_boost + scope_boost
    return min(1.5, (base * type_weight) + retrieval_boost + preferred_layer_boost)


def _is_redundant(candidate: str, selected_word_sets: list[set[str]], threshold: float = 0.75) -> bool:
    words = set(candidate.lower().split())
    if not words:
        return False
    for existing_words in selected_word_sets:
        if not existing_words:
            continue
        intersection = words & existing_words
        union = words | existing_words
        if len(intersection) / len(union) >= threshold:
            return True
    return False


def _infer_layer(result: RecallResult) -> str:
    if result.layer:
        return result.layer
    if result.memory.source_episode_id is not None:
        return MemoryLayer.EPISODIC.value
    if result.memory.origin_kind == "procedural_memory":
        return MemoryLayer.PROCEDURAL.value
    return MemoryLayer.CONVERSATIONAL.value


def _build_explanation(result: RecallResult) -> RecallExplanation:
    return RecallExplanation(
        memory_id=result.memory.id,
        layer=_infer_layer(result),
        retrieval_source=result.retrieval_source,
        score=round(result.combined_score, 4),
        scope_score=round(result.scope_score, 4),
        reasons=list(result.selection_reasons),
        source_query_id=result.memory.source_query_id,
        source_task_id=result.memory.source_task_id,
        source_episode_id=result.memory.source_episode_id,
    )


def _build_discard(result: RecallResult, reason: str) -> RecallDiscard:
    return RecallDiscard(
        memory_id=result.memory.id,
        content_preview=result.memory.content[:120],
        layer=_infer_layer(result),
        retrieval_source=result.retrieval_source,
        reason=reason,
        score=round(result.combined_score, 4),
    )


def _resolve_conflicts(
    results: list[RecallResult],
) -> tuple[list[RecallResult], list[RecallDiscard], list[RecallConflict]]:
    """Choose one winner per conflict key and discard weaker siblings."""
    winners: list[RecallResult] = []
    discards: list[RecallDiscard] = []
    conflicts: list[RecallConflict] = []
    groups: dict[str, list[RecallResult]] = collections.defaultdict(list)
    passthrough: list[RecallResult] = []
    for result in results:
        conflict_key = (result.memory.conflict_key or "").strip()
        if conflict_key:
            groups[conflict_key].append(result)
        else:
            passthrough.append(result)
    for conflict_key, items in groups.items():
        if len(items) == 1:
            passthrough.append(items[0])
            continue
        ranked = sorted(items, key=lambda item: item.combined_score, reverse=True)
        winner = ranked[0]
        winners.append(winner)
        losers = ranked[1:]
        conflicts.append(
            RecallConflict(
                conflict_key=conflict_key,
                winner_memory_id=winner.memory.id,
                loser_memory_ids=[item.memory.id for item in losers],
                winner_layer=_infer_layer(winner),
                winner_retrieval_source=winner.retrieval_source,
                winner_score=round(winner.combined_score, 4),
            )
        )
        for loser in losers:
            discards.append(_build_discard(loser, "conflict_loser"))
    return [*passthrough, *winners], discards, conflicts


def _apply_density_limits(results: list[RecallResult], profile: MemoryProfile | None) -> list[RecallResult]:
    if not profile:
        return results
    total_limit, per_layer_limit = profile.density_limits()
    if total_limit <= 0:
        return []
    per_layer_counts: collections.Counter[str] = collections.Counter()
    selected: list[RecallResult] = []
    for result in results:
        if len(selected) >= total_limit:
            break
        layer = _infer_layer(result)
        if per_layer_counts[layer] >= per_layer_limit:
            continue
        per_layer_counts[layer] += 1
        selected.append(result)
    return selected


def _render_sections(selected: list[RecallResult], max_chars: int) -> str:
    if not selected:
        return ""

    grouped: dict[str, list[RecallResult]] = {}
    for result in selected:
        grouped.setdefault(result.memory.memory_type.value, []).append(result)

    sections: list[str] = []
    used_chars = len(RECALL_HEADER)
    for type_key in _TYPE_ORDER:
        memories = grouped.get(type_key)
        if not memories:
            continue
        header = RECALL_TYPE_HEADERS.get(type_key, f"### {type_key.title()}")
        lines = [header]
        for result in memories:
            memory = result.memory
            date_str = memory.created_at.strftime("%Y-%m-%d")
            provenance: list[str] = [date_str, _infer_layer(result)]
            if memory.origin_kind and memory.origin_kind != "conversation":
                provenance.append(memory.origin_kind)
            if memory.project_key:
                provenance.append(memory.project_key)
            if memory.environment:
                provenance.append(memory.environment)
            if memory.source_task_id is not None:
                provenance.append(f"task {memory.source_task_id}")
            if memory.source_episode_id is not None:
                provenance.append(f"episode {memory.source_episode_id}")
            line = f"- [{' | '.join(provenance)}] {memory.content}"
            if used_chars + len(line) > max_chars:
                break
            used_chars += len(line)
            lines.append(line)
        if len(lines) > 1:
            sections.append("\n".join(lines))
    return RECALL_HEADER + "\n" + "\n\n".join(sections) if sections else ""


def _compute_trust_score(selected: list[RecallResult]) -> float:
    if not selected:
        return 0.0
    layer_weights = {
        MemoryLayer.EPISODIC.value: 0.80,
        MemoryLayer.PROCEDURAL.value: 0.70,
        MemoryLayer.CONVERSATIONAL.value: 0.55,
        MemoryLayer.PROACTIVE.value: 0.45,
    }
    weighted = 0.0
    total = 0.0
    for result in selected:
        layer = _infer_layer(result)
        layer_weight = layer_weights.get(layer, 0.50)
        weighted += min(1.0, result.combined_score) * layer_weight
        total += layer_weight
    return round(weighted / total, 4) if total else 0.0


async def build_memory_resolution(
    store: MemoryStore,
    query: str,
    user_id: int,
    max_tokens: int | None = None,
    *,
    profile: MemoryProfile | None = None,
    session_id: str | None = None,
    project_key: str = "",
    environment: str = "",
    team: str = "",
    task_id: int | None = None,
    source_query_id: int | None = None,
    source_task_id: int | None = None,
    source_episode_id: int | None = None,
) -> MemoryResolution:
    """Build a recall envelope with context, explanations, and audit metadata."""
    if max_tokens is None:
        max_tokens = MEMORY_MAX_CONTEXT_TOKENS

    agent_scope = getattr(store, "agent_id", "default")
    if not isinstance(agent_scope, str) or not agent_scope:
        agent_scope = "default"
    key = _cache_key(
        query,
        user_id,
        agent_id=agent_scope,
        session_id=session_id,
        project_key=project_key,
        environment=environment,
        team=team,
        source_query_id=source_query_id,
        source_task_id=source_task_id,
        source_episode_id=source_episode_id,
    )
    cached = _recall_cache.get(key)
    if cached and (_time.time() - cached[0]) < _CACHE_TTL:
        resolution = cached[1]
        if resolution.selected:
            access_ids = [result.memory.id for result in resolution.selected if result.memory.id]
            if access_ids:
                store.batch_update_access(access_ids)
            return resolution

    max_chars = max_tokens * _CHARS_PER_TOKEN
    results = await store.search(
        query=query,
        user_id=user_id,
        n_results=MEMORY_MAX_RECALL,
        project_key=project_key,
        environment=environment,
        team=team,
        session_id=session_id,
        source_query_id=source_query_id,
        source_task_id=source_task_id,
        source_episode_id=source_episode_id,
    )
    if not results:
        resolution = MemoryResolution(context="")
        _recall_cache[key] = (_time.time(), resolution)
        return resolution

    filtered: list[RecallResult] = []
    considered: list[RecallResult] = []
    discarded: list[RecallDiscard] = []
    for result in results:
        similarity = 1.0 - result.relevance_score
        if similarity < MEMORY_RECALL_THRESHOLD and result.retrieval_source not in {
            "query_link",
            "task_link",
            "episode",
            "session",
        }:
            result.combined_score = 0.0
            discarded.append(_build_discard(result, "below_threshold"))
            continue
        result.combined_score = _compute_combined_score(
            result,
            profile=profile,
            session_id=session_id,
            project_key=project_key,
            environment=environment,
            team=team,
        )
        filtered.append(result)
        considered.append(result)

    filtered.sort(key=lambda item: item.combined_score, reverse=True)
    filtered, conflict_discards, conflicts = _resolve_conflicts(filtered)
    discarded.extend(conflict_discards)
    filtered = sorted(filtered, key=lambda item: item.combined_score, reverse=True)

    selected: list[RecallResult] = []
    selected_word_sets: list[set[str]] = []
    layer_counts: collections.Counter[str] = collections.Counter()
    total_limit, per_layer_limit = profile.density_limits() if profile else (MEMORY_MAX_RECALL, MEMORY_MAX_RECALL)
    used_chars = len(RECALL_HEADER) + 50
    for result in filtered:
        if len(selected) >= total_limit:
            discarded.append(_build_discard(result, "density_budget"))
            continue
        layer = _infer_layer(result)
        if layer_counts[layer] >= per_layer_limit:
            discarded.append(_build_discard(result, "layer_budget"))
            continue
        if _is_redundant(result.memory.content, selected_word_sets):
            discarded.append(_build_discard(result, "redundant"))
            continue
        entry_chars = len(result.memory.content) + 20
        if used_chars + entry_chars > max_chars:
            discarded.append(_build_discard(result, "token_budget"))
            continue
        selected.append(result)
        layer_counts[layer] += 1
        selected_word_sets.append(set(result.memory.content.lower().split()))
        used_chars += entry_chars

    if not selected:
        resolution = MemoryResolution(context="", considered=considered, discarded=discarded, conflicts=conflicts)
        _recall_cache[key] = (_time.time(), resolution)
        return resolution

    access_ids = [result.memory.id for result in selected if result.memory.id]
    if access_ids:
        store.batch_update_access(access_ids)

    explanations = [_build_explanation(result) for result in selected]
    context = _render_sections(selected, max_chars)
    resolution = MemoryResolution(
        context=context,
        considered=considered,
        selected=selected,
        discarded=discarded,
        conflicts=conflicts,
        explanations=explanations,
        trust_score=_compute_trust_score(selected),
        selected_layers=sorted({_infer_layer(result) for result in selected}),
        retrieval_sources=sorted({result.retrieval_source for result in selected}),
    )

    try:
        from koda.services import metrics

        for item in selected:
            metrics.MEMORY_RECALL_SELECTIONS.labels(
                agent_id=agent_scope,
                layer=_infer_layer(item),
                retrieval_source=item.retrieval_source,
            ).inc()
            record_memory_quality_counter(agent_scope, "recall", "selected")
        for discard in discarded:
            metrics.MEMORY_RECALL_DISCARDS.labels(agent_id=agent_scope, reason=discard.reason).inc()
            record_memory_quality_counter(agent_scope, "recall", "discarded")
        for conflict in conflicts:
            record_conflict_resolution(agent_scope, "winner")
            record_conflict_resolution(agent_scope, "loser", delta=len(conflict.loser_memory_ids))
        log_memory_recall_audit(
            user_id=user_id,
            task_id=task_id,
            query_hash=key,
            query_preview=query[:200],
            session_id=session_id,
            project_key=project_key,
            environment=environment,
            team=team,
            trust_score=resolution.trust_score,
            considered=[
                {
                    "memory_id": item.memory.id,
                    "content": item.memory.content[:180],
                    "score": round(item.combined_score, 4),
                    "layer": _infer_layer(item),
                    "retrieval_source": item.retrieval_source,
                }
                for item in considered
            ],
            selected=[
                {
                    "memory_id": item.memory.id,
                    "content": item.memory.content[:180],
                    "score": round(item.combined_score, 4),
                    "layer": _infer_layer(item),
                    "retrieval_source": item.retrieval_source,
                }
                for item in selected
            ],
            discarded=[
                {
                    "memory_id": item.memory_id,
                    "reason": item.reason,
                    "layer": item.layer,
                    "retrieval_source": item.retrieval_source,
                    "score": item.score,
                }
                for item in discarded
            ],
            conflicts=[
                {
                    "conflict_key": item.conflict_key,
                    "winner_memory_id": item.winner_memory_id,
                    "loser_memory_ids": item.loser_memory_ids,
                    "winner_layer": item.winner_layer,
                    "winner_retrieval_source": item.winner_retrieval_source,
                    "winner_score": item.winner_score,
                }
                for item in conflicts
            ],
            explanations=[
                {
                    "memory_id": item.memory_id,
                    "layer": item.layer,
                    "retrieval_source": item.retrieval_source,
                    "score": item.score,
                    "scope_score": item.scope_score,
                    "reasons": item.reasons,
                    "source_query_id": item.source_query_id,
                    "source_task_id": item.source_task_id,
                    "source_episode_id": item.source_episode_id,
                }
                for item in explanations
            ],
            selected_layers=resolution.selected_layers,
            retrieval_sources=resolution.retrieval_sources,
            total_considered=len(considered),
            total_selected=len(selected),
            total_discarded=len(discarded),
            conflict_group_count=len(conflicts),
            agent_id=agent_scope,
        )
    except Exception:
        log.exception("memory_recall_audit_error")

    log.info("memory_recall", count=len(selected), discarded=len(discarded), trust_score=resolution.trust_score)
    if len(_recall_cache) >= _CACHE_MAX:
        _recall_cache.popitem(last=False)
    _recall_cache[key] = (_time.time(), resolution)
    return resolution


async def build_memory_context(
    store: MemoryStore,
    query: str,
    user_id: int,
    max_tokens: int | None = None,
    *,
    profile: MemoryProfile | None = None,
    session_id: str | None = None,
    project_key: str = "",
    environment: str = "",
    team: str = "",
    task_id: int | None = None,
    source_query_id: int | None = None,
    source_task_id: int | None = None,
    source_episode_id: int | None = None,
) -> str:
    resolution = await build_memory_resolution(
        store,
        query,
        user_id,
        max_tokens=max_tokens,
        profile=profile,
        session_id=session_id,
        project_key=project_key,
        environment=environment,
        team=team,
        task_id=task_id,
        source_query_id=source_query_id,
        source_task_id=source_task_id,
        source_episode_id=source_episode_id,
    )
    return resolution.context


def build_proactive_context(user_id: int, *, agent_id: str | None = None) -> str:
    memories = get_recent_high_importance(
        user_id=user_id,
        types=["event", "task"],
        min_importance=0.6,
        max_age_days=7,
        agent_id=agent_id,
    )
    if not memories:
        return ""

    lines = []
    for memory in memories:
        date_str = memory.created_at.strftime("%Y-%m-%d")
        type_label = memory.memory_type.value
        lines.append(f"- [{date_str}, {type_label}, proactive] {memory.content}")
    return PROACTIVE_HEADER + "\n".join(lines)


async def build_procedural_context(
    store: MemoryStore,
    query: str,
    user_id: int,
    *,
    project_key: str = "",
    environment: str = "",
    team: str = "",
    session_id: str | None = None,
) -> str:
    return await _build_procedural_context(
        store,
        query,
        user_id,
        project_key=project_key,
        environment=environment,
        team=team,
        session_id=session_id,
    )
