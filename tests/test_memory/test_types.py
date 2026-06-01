"""Tests for memory/types.py."""

from datetime import datetime

from koda.memory.types import DEFAULT_TTL_DAYS, Memory, MemoryType, RecallResult


def test_memory_type_enum():
    """All expected types exist."""
    assert MemoryType.FACT.value == "fact"
    assert MemoryType.EVENT.value == "event"
    assert MemoryType.PREFERENCE.value == "preference"
    assert MemoryType.DECISION.value == "decision"
    assert MemoryType.PROBLEM.value == "problem"
    assert MemoryType.COMMIT.value == "commit"
    assert MemoryType.RELATIONSHIP.value == "relationship"
    assert MemoryType.TASK.value == "task"


def test_memory_type_from_string():
    """Can create MemoryType from string value."""
    assert MemoryType("fact") == MemoryType.FACT
    assert MemoryType("event") == MemoryType.EVENT


def test_default_ttl_days():
    """All memory types have a TTL."""
    for mt in MemoryType:
        assert mt in DEFAULT_TTL_DAYS
        assert DEFAULT_TTL_DAYS[mt] > 0


def test_memory_defaults():
    """Memory creates with sensible defaults."""
    m = Memory(user_id=123, memory_type=MemoryType.FACT, content="test fact")
    assert m.user_id == 123
    assert m.importance == 0.5
    assert m.access_count == 0
    assert m.is_active is True
    assert m.id is None
    assert m.vector_ref_id is None
    assert isinstance(m.created_at, datetime)
    assert m.metadata == {}


def test_recall_result():
    """RecallResult stores memory with scores."""
    m = Memory(user_id=123, memory_type=MemoryType.FACT, content="test")
    r = RecallResult(memory=m, relevance_score=0.15, combined_score=0.7)
    assert r.relevance_score == 0.15
    assert r.combined_score == 0.7
    assert r.memory.content == "test"
