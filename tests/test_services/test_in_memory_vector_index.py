"""Tests for the in-memory vector index (heap optimisation and size limits)."""

from __future__ import annotations

import logging
import math

import pytest

from koda.services.in_memory_vector_index import (
    _MAX_COLLECTION_SIZE,
    InMemoryVectorCollection,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unit_vector(angle_deg: float, dims: int = 3) -> list[float]:
    """Return a simple unit-ish vector rotated by *angle_deg* in the first two dims."""
    rad = math.radians(angle_deg)
    vec = [math.cos(rad), math.sin(rad)] + [0.0] * (dims - 2)
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec]


def _make_collection(n: int = 5, *, name: str = "test") -> InMemoryVectorCollection:
    """Create a collection with *n* rows whose embeddings fan out from 0-degrees."""
    col = InMemoryVectorCollection(name=name)
    col.upsert(
        ids=[f"id-{i}" for i in range(n)],
        embeddings=[_unit_vector(i * 10) for i in range(n)],
        documents=[f"doc-{i}" for i in range(n)],
        metadatas=[{"group": "a" if i % 2 == 0 else "b", "idx": i} for i in range(n)],
    )
    return col


# ---------------------------------------------------------------------------
# Top-k correctness
# ---------------------------------------------------------------------------


class TestQueryTopK:
    """Ensure heap-based top-k returns the same results as the old sorted approach."""

    def test_top_k_ordering(self) -> None:
        col = _make_collection(10)
        query_vec = _unit_vector(0)
        result = col.query(query_embeddings=[query_vec], n_results=3)

        ids = result["ids"][0]
        distances = result["distances"][0]

        assert len(ids) == 3
        # distances must be ascending (closest first)
        assert distances == sorted(distances)
        # the closest vector to 0-degrees is id-0 (angle 0)
        assert ids[0] == "id-0"

    def test_top_k_with_k_greater_than_n(self) -> None:
        col = _make_collection(3)
        result = col.query(query_embeddings=[_unit_vector(0)], n_results=10)

        assert len(result["ids"][0]) == 3  # only 3 items exist

    def test_top_k_with_k_zero(self) -> None:
        col = _make_collection(5)
        result = col.query(query_embeddings=[_unit_vector(0)], n_results=0)

        assert result["ids"][0] == []
        assert result["distances"][0] == []

    def test_query_empty_collection(self) -> None:
        col = InMemoryVectorCollection(name="empty")
        result = col.query(query_embeddings=[_unit_vector(0)], n_results=5)

        assert result["ids"][0] == []
        assert result["distances"][0] == []

    def test_multiple_query_embeddings(self) -> None:
        col = _make_collection(10)
        result = col.query(
            query_embeddings=[_unit_vector(0), _unit_vector(90)],
            n_results=2,
        )

        assert len(result["ids"]) == 2
        # First query: closest to 0 degrees
        assert result["ids"][0][0] == "id-0"
        # Second query: closest to 90 degrees (id-9 is at 90 degrees)
        assert result["ids"][1][0] == "id-9"


# ---------------------------------------------------------------------------
# Metadata filtering with heap
# ---------------------------------------------------------------------------


class TestMetadataFiltering:
    def test_where_simple(self) -> None:
        col = _make_collection(10)
        result = col.query(
            query_embeddings=[_unit_vector(0)],
            n_results=5,
            where={"group": "a"},
        )
        # Only even indices have group "a"
        for rid in result["ids"][0]:
            idx = int(rid.split("-")[1])
            assert idx % 2 == 0

    def test_where_and_clause(self) -> None:
        col = _make_collection(10)
        result = col.query(
            query_embeddings=[_unit_vector(0)],
            n_results=5,
            where={"$and": [{"group": "a"}, {"idx": 0}]},
        )
        assert result["ids"][0] == ["id-0"]


# ---------------------------------------------------------------------------
# Size limit and eviction
# ---------------------------------------------------------------------------


class TestSizeLimit:
    def test_eviction_triggers_when_exceeded(self) -> None:
        col = InMemoryVectorCollection(name="bounded")
        # Insert exactly at the limit -- no eviction
        n = _MAX_COLLECTION_SIZE
        col.upsert(
            ids=[f"id-{i}" for i in range(n)],
            embeddings=[[1.0, 0.0]] * n,
            documents=[f"doc-{i}" for i in range(n)],
        )
        assert len(col._rows) == _MAX_COLLECTION_SIZE

        # Insert one more to trigger eviction
        col.upsert(
            ids=["overflow-0"],
            embeddings=[[0.0, 1.0]],
            documents=["overflow"],
        )
        assert len(col._rows) == _MAX_COLLECTION_SIZE
        # The very first entry should have been evicted (oldest by insertion order)
        assert "id-0" not in col._rows
        assert "overflow-0" in col._rows

    def test_eviction_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        col = InMemoryVectorCollection(name="warn-test")
        n = _MAX_COLLECTION_SIZE
        col.upsert(
            ids=[f"id-{i}" for i in range(n)],
            embeddings=[[1.0, 0.0]] * n,
        )

        with caplog.at_level(logging.WARNING):
            col.upsert(
                ids=["extra"],
                embeddings=[[0.0, 1.0]],
            )

        assert any("exceeded size limit" in msg for msg in caplog.messages)

    def test_bulk_upsert_eviction(self) -> None:
        col = InMemoryVectorCollection(name="bulk")
        n = _MAX_COLLECTION_SIZE
        overflow = 100
        total = n + overflow
        col.upsert(
            ids=[f"id-{i}" for i in range(total)],
            embeddings=[[1.0, 0.0]] * total,
        )
        assert len(col._rows) == _MAX_COLLECTION_SIZE
        # First `overflow` entries should be gone
        for i in range(overflow):
            assert f"id-{i}" not in col._rows
        # Last entries should remain
        assert f"id-{total - 1}" in col._rows
