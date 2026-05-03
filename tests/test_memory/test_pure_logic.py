"""Pure-logic tests for memory recall scoring, hashing, and conflict resolution.

No DB, no asyncio, no Rust. Pins the formulas in:

  koda/memory/recall.py    _recency_factor, _compute_combined_score, _is_redundant, _scope_reason
  koda/memory/types.py     build_content_hash, build_conflict_key, Memory.__post_init__

Memory is a best-effort layer (per memory/CLAUDE.md) — these formulas are
the only thing standing between "useful recall" and "noise" so we pin them
hard. Any drift requires a deliberate test update.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from koda.memory.recall import (
    _compute_combined_score,
    _is_redundant,
    _recency_factor,
    _scope_reason,
)
from koda.memory.types import (
    Memory,
    MemoryType,
    RecallResult,
    build_conflict_key,
    build_content_hash,
)

# ---------------------------------------------------------------------------
# build_content_hash
# ---------------------------------------------------------------------------


def test_content_hash_is_deterministic() -> None:
    a = build_content_hash("Hello world")
    b = build_content_hash("Hello world")
    assert a == b
    assert len(a) == 64  # SHA-256 hex


def test_content_hash_normalizes_whitespace_and_case() -> None:
    a = build_content_hash("  Hello   World  ")
    b = build_content_hash("hello world")
    assert a == b


def test_content_hash_collapses_internal_whitespace() -> None:
    a = build_content_hash("hello\n\n\tworld")
    b = build_content_hash("hello world")
    assert a == b


def test_content_hash_changes_with_memory_type() -> None:
    a = build_content_hash("hello", MemoryType.FACT)
    b = build_content_hash("hello", MemoryType.PREFERENCE)
    c = build_content_hash("hello", None)
    assert a != b
    # Without a type, the hash differs from any typed variant.
    assert c != a
    assert c != b


def test_content_hash_distinguishes_distinct_content() -> None:
    a = build_content_hash("hello world")
    b = build_content_hash("hello world.")  # trailing punctuation matters
    c = build_content_hash("hola mundo")
    assert a != b
    assert a != c


# ---------------------------------------------------------------------------
# build_conflict_key
# ---------------------------------------------------------------------------


def test_conflict_key_is_24_hex_chars() -> None:
    key = build_conflict_key(MemoryType.FACT, subject="user prefers dark mode")
    assert len(key) == 24
    int(key, 16)  # parses as hex without raising


def test_conflict_key_normalizes_subject() -> None:
    a = build_conflict_key(MemoryType.FACT, subject="User Prefers Dark Mode")
    b = build_conflict_key(MemoryType.FACT, subject="  user   prefers   dark   mode  ")
    assert a == b


def test_conflict_key_distinguishes_scope_dimensions() -> None:
    base = build_conflict_key(MemoryType.FACT, subject="x")
    by_proj = build_conflict_key(MemoryType.FACT, subject="x", project_key="alpha")
    by_env = build_conflict_key(MemoryType.FACT, subject="x", environment="prod")
    by_team = build_conflict_key(MemoryType.FACT, subject="x", team="security")
    seen = {base, by_proj, by_env, by_team}
    assert len(seen) == 4, "scope dimensions must affect the key"


def test_conflict_key_changes_with_memory_type() -> None:
    a = build_conflict_key(MemoryType.FACT, subject="x")
    b = build_conflict_key(MemoryType.PREFERENCE, subject="x")
    assert a != b


# ---------------------------------------------------------------------------
# Memory.__post_init__ derives content_hash, subject, conflict_key, scope
# ---------------------------------------------------------------------------


def test_memory_post_init_derives_content_hash() -> None:
    m = Memory(user_id=1, memory_type=MemoryType.FACT, content="Use asyncio for concurrency")
    assert m.content_hash == build_content_hash("Use asyncio for concurrency", MemoryType.FACT)


def test_memory_post_init_derives_subject_from_first_8_words() -> None:
    m = Memory(
        user_id=1,
        memory_type=MemoryType.FACT,
        content="A B C D E F G H I J K",  # 11 words
    )
    assert m.subject == "A B C D E F G H"


def test_memory_post_init_short_content_uses_full_subject() -> None:
    m = Memory(user_id=1, memory_type=MemoryType.FACT, content="Just three words")
    assert m.subject == "Just three words"


def test_memory_post_init_derives_conflict_key() -> None:
    m = Memory(user_id=1, memory_type=MemoryType.FACT, content="some content here")
    expected = build_conflict_key(MemoryType.FACT, subject=m.subject)
    assert m.conflict_key == expected


def test_memory_post_init_derives_applicability_scope() -> None:
    m = Memory(
        user_id=1,
        memory_type=MemoryType.FACT,
        content="x",
        project_key="alpha",
        environment="prod",
        team="security",
    )
    assert m.applicability_scope == {"project_key": "alpha", "environment": "prod", "team": "security"}


def test_memory_post_init_does_not_overwrite_explicit_values() -> None:
    m = Memory(
        user_id=1,
        memory_type=MemoryType.FACT,
        content="x",
        content_hash="explicit-hash",
        subject="explicit subject",
        conflict_key="explicit-key",
    )
    assert m.content_hash == "explicit-hash"
    assert m.subject == "explicit subject"
    assert m.conflict_key == "explicit-key"


# ---------------------------------------------------------------------------
# _recency_factor — exponential half-life decay
# ---------------------------------------------------------------------------


def test_recency_factor_now_is_one() -> None:
    f = _recency_factor(datetime.now(), half_life_days=120)
    assert f == pytest.approx(1.0, rel=1e-3)


def test_recency_factor_at_half_life_is_half() -> None:
    f = _recency_factor(datetime.now() - timedelta(days=120), half_life_days=120)
    assert f == pytest.approx(0.5, rel=0.01)


def test_recency_factor_at_two_half_lives_is_quarter() -> None:
    f = _recency_factor(datetime.now() - timedelta(days=240), half_life_days=120)
    assert f == pytest.approx(0.25, rel=0.01)


def test_recency_factor_monotonically_decreases() -> None:
    fs = [_recency_factor(datetime.now() - timedelta(days=d), half_life_days=120) for d in (0, 30, 60, 120, 240, 480)]
    for a, b in zip(fs, fs[1:], strict=False):
        assert a > b
    assert all(0.0 < f <= 1.0 for f in fs)


def test_recency_factor_custom_half_life_overrides_default() -> None:
    long = _recency_factor(datetime.now() - timedelta(days=120), half_life_days=240)
    short = _recency_factor(datetime.now() - timedelta(days=120), half_life_days=60)
    assert long > short  # longer half-life → memory still fresher


# ---------------------------------------------------------------------------
# _scope_reason — additive boosts when context matches
# ---------------------------------------------------------------------------


def _scope_test_memory(**overrides: object) -> Memory:
    base: dict[str, object] = {
        "user_id": 1,
        "memory_type": MemoryType.FACT,
        "content": "x",
        "session_id": None,
        "source_episode_id": None,
        "project_key": "",
        "environment": "",
        "team": "",
    }
    base.update(overrides)
    return Memory(**base)  # type: ignore[arg-type]


def test_scope_reason_no_matches_returns_zero() -> None:
    m = _scope_test_memory()
    boost, reasons = _scope_reason(m, session_id=None, project_key="", environment="", team="")
    assert boost == 0.0
    assert reasons == []


def test_scope_reason_session_match_only() -> None:
    m = _scope_test_memory(session_id="s1")
    boost, reasons = _scope_reason(m, session_id="s1", project_key="", environment="", team="")
    assert boost == pytest.approx(0.08)
    assert reasons == ["same_session"]


def test_scope_reason_full_stack_combines() -> None:
    m = _scope_test_memory(
        session_id="s1",
        project_key="alpha",
        environment="prod",
        team="security",
        source_episode_id=42,
    )
    boost, reasons = _scope_reason(
        m, session_id="s1", project_key="alpha", environment="prod", team="security"
    )
    # 0.08 + 0.07 + 0.04 + 0.03 + 0.05 = 0.27
    assert boost == pytest.approx(0.27)
    expected = ["same_session", "same_project", "same_environment", "same_team", "episodic_bundle"]
    assert sorted(reasons) == sorted(expected)


def test_scope_reason_session_mismatch_no_boost() -> None:
    m = _scope_test_memory(session_id="s2")
    boost, reasons = _scope_reason(m, session_id="s1", project_key="", environment="", team="")
    assert boost == 0.0
    assert "same_session" not in reasons


# ---------------------------------------------------------------------------
# _compute_combined_score — formula and clamping
# ---------------------------------------------------------------------------


def _result(
    *,
    relevance: float = 0.2,
    importance: float = 0.5,
    quality: float = 0.5,
    age_days: float = 0,
    access_count: int = 0,
) -> RecallResult:
    """Build a RecallResult with controlled inputs for scoring tests."""
    mem = Memory(
        user_id=1,
        memory_type=MemoryType.FACT,
        content="content",
        importance=importance,
        quality_score=quality,
        access_count=access_count,
        created_at=datetime.now() - timedelta(days=age_days),
    )
    return RecallResult(memory=mem, relevance_score=relevance)


def test_combined_score_zero_inputs_floor() -> None:
    """All inputs at minimum: relevance=1 (worst), importance=0, quality=0, very old."""
    res = _result(relevance=1.0, importance=0.0, quality=0.0, age_days=10000)
    score = _compute_combined_score(res)
    assert score == pytest.approx(0.0, abs=1e-3)


def test_combined_score_perfect_relevance_recent() -> None:
    """Best case: relevance=0 (full match), importance=1, quality=1, fresh."""
    res = _result(relevance=0.0, importance=1.0, quality=1.0, age_days=0)
    score = _compute_combined_score(res)
    # base = 0.55*1 + 0.20*1 + 0.15*~1 + 0.10*1 = ~1.0
    assert 0.95 < score < 1.10


def test_combined_score_clamped_at_1_5() -> None:
    """Even with type_weight inflated externally, score never exceeds 1.5."""
    res = _result(relevance=0.0, importance=1.0, quality=1.0, access_count=100, age_days=0)
    # access_count contributes max +0.05 (capped). Score should still be < 1.5.
    score = _compute_combined_score(res)
    assert score <= 1.5


def test_combined_score_relevance_dominates() -> None:
    """relevance has weight 0.55 — it should drive the ranking."""
    high_rel = _result(relevance=0.0, importance=0.0, quality=0.0)
    low_rel = _result(relevance=1.0, importance=1.0, quality=1.0)
    assert _compute_combined_score(high_rel) > _compute_combined_score(low_rel)


def test_combined_score_access_boost_caps_at_5pct() -> None:
    """access_boost = min(0.05, count * 0.01) — caps at 5 visits."""
    no_access = _result(access_count=0)
    five = _result(access_count=5)
    fifty = _result(access_count=50)
    s5 = _compute_combined_score(five)
    s50 = _compute_combined_score(fifty)
    s_none = _compute_combined_score(no_access)
    assert s5 > s_none
    # At 5+, additional access provides no further boost.
    assert s50 == pytest.approx(s5, rel=1e-6)


def test_combined_score_breakdown_is_attached() -> None:
    res = _result()
    _compute_combined_score(res)
    assert res.score_breakdown is not None
    keys = set(res.score_breakdown.keys())
    expected = {
        "relevance",
        "importance",
        "quality",
        "recency",
        "access_boost",
        "scope_boost",
        "retrieval_boost",
        "preferred_layer_boost",
        "type_weight",
    }
    assert expected.issubset(keys)


# ---------------------------------------------------------------------------
# _is_redundant — Jaccard-style word-set redundancy check
# ---------------------------------------------------------------------------


def test_is_redundant_empty_candidate_returns_false() -> None:
    assert _is_redundant("", [{"hello", "world"}]) is False


def test_is_redundant_no_existing_returns_false() -> None:
    assert _is_redundant("hello world", []) is False


def test_is_redundant_high_overlap_returns_true() -> None:
    """A candidate that shares ≥75% of words with any existing set is redundant."""
    existing = [{"the", "cat", "sat", "on", "mat"}]
    # Candidate shares 5/6 words.
    candidate = "cat sat on the mat hat"
    assert _is_redundant(candidate, existing) is True


def test_is_redundant_low_overlap_returns_false() -> None:
    existing = [{"alpha", "beta", "gamma"}]
    candidate = "delta epsilon zeta eta theta"
    assert _is_redundant(candidate, existing) is False


def test_is_redundant_case_insensitive() -> None:
    existing = [{"hello", "world"}]
    # Lowercased candidate {hello, world} == existing → 1.0 ≥ 0.75 → True
    assert _is_redundant("HELLO WORLD", existing) is True


def test_is_redundant_partial_below_threshold() -> None:
    """{HELLO, WORLD, foo} vs {hello, world}: Jaccard = 2/3 ≈ 0.67 < 0.75."""
    existing = [{"hello", "world"}]
    assert _is_redundant("HELLO WORLD foo", existing) is False


def test_is_redundant_threshold_override() -> None:
    existing = [{"alpha", "beta", "gamma", "delta"}]
    # 2/4 = 50% overlap — below default 0.75, above 0.4
    candidate = "alpha beta something"
    assert _is_redundant(candidate, existing, threshold=0.75) is False
    assert _is_redundant(candidate, existing, threshold=0.4) is True
