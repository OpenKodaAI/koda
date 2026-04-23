"""Tests for memory/recall.py."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.memory.profile import MemoryProfile
from koda.memory.recall import (
    _cache_key,
    _compute_combined_score,
    _is_redundant,
    _recall_cache,
    _recency_factor,
    build_memory_context,
    build_memory_resolution,
    clear_recall_cache,
)
from koda.memory.types import Memory, MemoryType, RecallResult


def test_recency_factor_recent():
    """Recent memories have high recency factor."""
    factor = _recency_factor(datetime.now())
    assert factor > 0.99


def test_recency_factor_old():
    """90-day-old memories with half_life=120 have moderate recency factor."""
    old_date = datetime.now() - timedelta(days=90)
    factor = _recency_factor(old_date)
    # With half_life=120, 90 days → factor ~0.63
    assert 0.5 < factor < 0.75


def test_recency_factor_half_life():
    """At half_life, factor should be ~0.5."""
    half_life = 30.0
    date = datetime.now() - timedelta(days=half_life)
    factor = _recency_factor(date, half_life)
    assert 0.45 < factor < 0.55


def test_combined_score():
    """Combined score uses weighted formula: high relevance+importance+recency → high score."""
    m = Memory(
        user_id=111,
        memory_type=MemoryType.FACT,
        content="test",
        importance=1.0,
        created_at=datetime.now(),
    )
    # Low distance = high relevance
    r = RecallResult(memory=m, relevance_score=0.1)
    score = _compute_combined_score(r)
    # 0.60*0.9 + 0.25*1.0 + 0.15*~1.0 = 0.54 + 0.25 + 0.15 = 0.94
    assert score > 0.85

    # High distance = low relevance
    r2 = RecallResult(memory=m, relevance_score=0.9)
    score2 = _compute_combined_score(r2)
    assert score2 < score


def test_combined_score_low_importance():
    """Low importance with weighted formula doesn't zero the score."""
    m = Memory(
        user_id=111,
        memory_type=MemoryType.FACT,
        content="test",
        importance=0.1,
        created_at=datetime.now(),
    )
    r = RecallResult(memory=m, relevance_score=0.1)
    score = _compute_combined_score(r)
    # 0.60*0.9 + 0.25*0.1 + 0.15*~1.0 = 0.54 + 0.025 + 0.15 = 0.715
    assert 0.6 < score < 0.8


def test_combined_score_old_memory_surfaces():
    """120-day-old memory with high relevance still surfaces with weighted formula."""
    m = Memory(
        user_id=111,
        memory_type=MemoryType.FACT,
        content="old but relevant",
        importance=0.9,
        created_at=datetime.now() - timedelta(days=120),
    )
    r = RecallResult(memory=m, relevance_score=0.1)
    score = _compute_combined_score(r)
    # 0.60*0.9 + 0.25*0.9 + 0.15*~0.5 = 0.54 + 0.225 + 0.075 = 0.84
    assert score > 0.7


def test_access_boost():
    """Memories with access history get a small score boost."""
    m_no_access = Memory(
        user_id=111,
        memory_type=MemoryType.FACT,
        content="test",
        importance=0.8,
        created_at=datetime.now(),
        access_count=0,
    )
    m_with_access = Memory(
        user_id=111,
        memory_type=MemoryType.FACT,
        content="test",
        importance=0.8,
        created_at=datetime.now(),
        access_count=5,
    )
    r1 = RecallResult(memory=m_no_access, relevance_score=0.2)
    r2 = RecallResult(memory=m_with_access, relevance_score=0.2)
    score1 = _compute_combined_score(r1)
    score2 = _compute_combined_score(r2)
    assert score2 > score1
    assert score2 - score1 == pytest.approx(0.05, abs=0.001)


@pytest.mark.asyncio
async def test_build_memory_context_empty():
    """Returns empty string when no results."""
    mock_store = MagicMock()
    mock_store.search = AsyncMock(return_value=[])

    context = await build_memory_context(mock_store, "query", user_id=111)
    assert context == ""


@pytest.mark.asyncio
async def test_build_memory_context_formats():
    """Builds formatted context with grouped types."""
    m1 = Memory(
        user_id=111,
        memory_type=MemoryType.FACT,
        content="API uses REST",
        importance=0.8,
        created_at=datetime.now(),
        id=1,
    )
    m2 = Memory(
        user_id=111,
        memory_type=MemoryType.EVENT,
        content="Deploy on Monday",
        importance=0.9,
        created_at=datetime.now(),
        id=2,
    )
    results = [
        RecallResult(memory=m1, relevance_score=0.2),
        RecallResult(memory=m2, relevance_score=0.15),
    ]

    mock_store = MagicMock()
    mock_store.search = AsyncMock(return_value=results)
    mock_store.batch_update_access = MagicMock()

    context = await build_memory_context(mock_store, "tell me about the API", user_id=111)

    assert "Long-term Memory" in context
    assert "API uses REST" in context
    assert "Deploy on Monday" in context
    assert "### Recent Events" in context
    assert "### Relevant Facts" in context


@pytest.mark.asyncio
async def test_build_memory_context_respects_threshold():
    """Low relevance memories are filtered out."""
    m = Memory(
        user_id=111,
        memory_type=MemoryType.FACT,
        content="Irrelevant fact",
        importance=0.5,
        created_at=datetime.now(),
        id=1,
    )
    # High distance = low similarity = below threshold
    results = [RecallResult(memory=m, relevance_score=0.95)]

    mock_store = MagicMock()
    mock_store.search = AsyncMock(return_value=results)

    context = await build_memory_context(mock_store, "query", user_id=111)
    assert context == ""


@pytest.mark.asyncio
async def test_build_memory_context_updates_access():
    """Updates access count for recalled memories using batch call."""
    m = Memory(
        user_id=111,
        memory_type=MemoryType.FACT,
        content="Important fact",
        importance=0.8,
        created_at=datetime.now(),
        id=42,
    )
    results = [RecallResult(memory=m, relevance_score=0.1)]

    mock_store = MagicMock()
    mock_store.search = AsyncMock(return_value=results)
    mock_store.batch_update_access = MagicMock()

    await build_memory_context(mock_store, "query", user_id=111)
    mock_store.batch_update_access.assert_called_once_with([42])


@pytest.mark.asyncio
async def test_build_memory_resolution_discards_conflict_loser():
    winner = Memory(
        user_id=111,
        memory_type=MemoryType.DECISION,
        content="Use provider A for deploys",
        importance=0.9,
        quality_score=0.9,
        created_at=datetime.now(),
        id=10,
        conflict_key="same-decision",
    )
    loser = Memory(
        user_id=111,
        memory_type=MemoryType.DECISION,
        content="Use provider B for deploys",
        importance=0.6,
        quality_score=0.6,
        created_at=datetime.now(),
        id=11,
        conflict_key="same-decision",
    )
    mock_store = MagicMock()
    mock_store.agent_id = "test"
    mock_store.search = AsyncMock(
        return_value=[
            RecallResult(memory=winner, relevance_score=0.05),
            RecallResult(memory=loser, relevance_score=0.05),
        ]
    )
    mock_store.batch_update_access = MagicMock()

    with patch("koda.memory.recall.log_memory_recall_audit"):
        resolution = await build_memory_resolution(mock_store, "deploy provider", user_id=111)

    assert [item.memory.id for item in resolution.selected] == [10]
    assert any(item.reason == "conflict_loser" and item.memory_id == 11 for item in resolution.discarded)
    assert resolution.conflicts
    assert resolution.conflicts[0].winner_memory_id == 10


@pytest.mark.asyncio
async def test_build_memory_resolution_applies_profile_density_limits():
    results = []
    for idx in range(6):
        results.append(
            RecallResult(
                memory=Memory(
                    user_id=111,
                    memory_type=MemoryType.FACT,
                    content=f"fact {idx}",
                    importance=0.9,
                    created_at=datetime.now(),
                    id=idx + 1,
                ),
                relevance_score=0.05,
            )
        )
    mock_store = MagicMock()
    mock_store.agent_id = "test"
    mock_store.search = AsyncMock(return_value=results)
    mock_store.batch_update_access = MagicMock()
    profile = MemoryProfile(agent_id="test", memory_density_target="sparse")

    with patch("koda.memory.recall.log_memory_recall_audit"):
        resolution = await build_memory_resolution(mock_store, "fact", user_id=111, profile=profile)

    assert len(resolution.selected) <= 5
    assert sum(1 for item in resolution.discarded if item.reason == "layer_budget") >= 1


@pytest.mark.asyncio
async def test_build_memory_resolution_boosts_preferred_layers():
    conversational = RecallResult(
        memory=Memory(
            user_id=111,
            memory_type=MemoryType.FACT,
            content="conversation memory",
            importance=0.8,
            created_at=datetime.now(),
            id=1,
        ),
        relevance_score=0.05,
        layer="conversational",
    )
    procedural = RecallResult(
        memory=Memory(
            user_id=111,
            memory_type=MemoryType.PROCEDURE,
            content="procedural memory",
            importance=0.8,
            created_at=datetime.now(),
            id=2,
            origin_kind="procedural_memory",
        ),
        relevance_score=0.05,
        layer="procedural",
    )
    mock_store = MagicMock()
    mock_store.agent_id = "test"
    mock_store.search = AsyncMock(return_value=[conversational, procedural])
    mock_store.batch_update_access = MagicMock()
    profile = MemoryProfile(agent_id="test", preferred_layers=("procedural",))

    with patch("koda.memory.recall.log_memory_recall_audit"):
        resolution = await build_memory_resolution(mock_store, "memory", user_id=111, profile=profile)

    assert resolution.selected[0].memory.id == 2


@pytest.mark.asyncio
async def test_build_memory_resolution_audits_full_considered_and_discarded_sets():
    clear_recall_cache()
    results = [
        RecallResult(
            memory=Memory(
                user_id=111,
                memory_type=MemoryType.FACT,
                content=f"fact {idx}",
                importance=0.9,
                created_at=datetime.now(),
                id=idx + 1,
            ),
            relevance_score=0.05,
        )
        for idx in range(50)
    ]
    mock_store = MagicMock()
    mock_store.agent_id = "test"
    mock_store.search = AsyncMock(return_value=results)
    mock_store.batch_update_access = MagicMock()
    profile = MemoryProfile(agent_id="test", memory_density_target="sparse")

    with (
        patch("koda.memory.recall.log_memory_recall_audit") as mock_audit,
        patch("koda.memory.recall.record_memory_quality_counter"),
        patch("koda.memory.recall.record_conflict_resolution"),
    ):
        await build_memory_resolution(mock_store, "fact", user_id=111, profile=profile)

    audit_kwargs = mock_audit.call_args.kwargs
    assert len(audit_kwargs["considered"]) == 50
    assert len(audit_kwargs["discarded"]) == 48
    assert audit_kwargs["total_considered"] == 50
    assert audit_kwargs["total_discarded"] == 48


# ---------------------------------------------------------------------------
# Recall cache tests
# ---------------------------------------------------------------------------


class TestRecallCache:
    def setup_method(self):
        _recall_cache.clear()

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        """Second identical query returns cached result without searching."""
        _recall_cache.clear()  # ensure clean state

        m = Memory(
            user_id=111,
            memory_type=MemoryType.FACT,
            content="cached fact",
            importance=0.8,
            created_at=datetime.now(),
            id=1,
        )
        results = [RecallResult(memory=m, relevance_score=0.1)]
        mock_store = MagicMock()
        mock_store.search = AsyncMock(return_value=results)
        mock_store.batch_update_access = MagicMock()

        # First call populates cache
        ctx1 = await build_memory_context(mock_store, "unique_cache_test_query", user_id=999)
        assert ctx1 != ""
        assert mock_store.search.call_count == 1

        # Verify cache was populated
        key = _cache_key("unique_cache_test_query", 999)
        assert key in _recall_cache

        # Second call uses cache
        ctx2 = await build_memory_context(mock_store, "unique_cache_test_query", user_id=999)
        assert ctx2 == ctx1
        assert mock_store.search.call_count == 1  # no second search

    @pytest.mark.asyncio
    async def test_cache_miss_different_query(self):
        """Different queries are not cached together."""
        mock_store = MagicMock()
        mock_store.search = AsyncMock(return_value=[])

        await build_memory_context(mock_store, "query one", user_id=111)
        await build_memory_context(mock_store, "query two", user_id=111)
        assert mock_store.search.call_count == 2

    def test_cache_expiration(self):
        """Expired cache entries are not returned."""
        import time as _time

        key = _cache_key("old query", 111)
        _recall_cache[key] = (_time.time() - 400, "stale context")
        # The entry is stale (>300s TTL), so build_memory_context will search again
        cached = _recall_cache.get(key)
        assert cached is not None
        assert (_time.time() - cached[0]) > 300  # confirms it's expired

    def test_clear_cache_per_user(self):
        """clear_recall_cache(user_id) only removes that user's entries."""
        import time as _time

        _recall_cache.clear()

        key_111 = _cache_key("query for user 111", 111)
        key_222 = _cache_key("query for user 222", 222)
        _recall_cache[key_111] = (_time.time(), "context for 111")
        _recall_cache[key_222] = (_time.time(), "context for 222")

        assert len(_recall_cache) == 2

        # Clear only user 111
        clear_recall_cache(user_id=111)

        # User 222's cache should remain
        assert key_222 in _recall_cache
        assert key_111 not in _recall_cache
        assert len(_recall_cache) == 1

    def test_clear_cache_global(self):
        """clear_recall_cache() without user_id clears everything."""
        import time as _time

        _recall_cache.clear()

        _recall_cache[_cache_key("q1", 111)] = (_time.time(), "c1")
        _recall_cache[_cache_key("q2", 222)] = (_time.time(), "c2")

        clear_recall_cache()
        assert len(_recall_cache) == 0


# ---------------------------------------------------------------------------
# Diversity filter tests
# ---------------------------------------------------------------------------


class TestIsRedundant:
    @staticmethod
    def _word_sets(texts: list[str]) -> list[set[str]]:
        return [set(t.lower().split()) for t in texts]

    def test_identical_strings(self):
        assert _is_redundant("the quick brown fox", self._word_sets(["the quick brown fox"])) is True

    def test_completely_different(self):
        assert _is_redundant("the quick brown fox", self._word_sets(["alpha beta gamma delta"])) is False

    def test_threshold_boundary(self):
        # words_a = {a,b,c,d}, words_b = {a,b,c,e}
        # intersection = {a,b,c} = 3, union = {a,b,c,d,e} = 5
        # 3/5 = 0.6 < 0.75 → NOT redundant
        assert _is_redundant("a b c d", self._word_sets(["a b c e"])) is False

        # words_a = {a,b,c}, words_b = {a,b,c,d}
        # intersection = {a,b,c} = 3, union = {a,b,c,d} = 4
        # 3/4 = 0.75 → exactly at threshold → redundant
        assert _is_redundant("a b c", self._word_sets(["a b c d"])) is True

    def test_empty_candidate(self):
        assert _is_redundant("", self._word_sets(["some text"])) is False

    def test_high_overlap(self):
        # 4/5 words shared
        assert _is_redundant("a b c d e", self._word_sets(["a b c d f"])) is False  # 4/6 = 0.67
        assert _is_redundant("a b c d", self._word_sets(["a b c d"])) is True  # identical
