"""Tests for the FAISS-backed semantic cache index."""

from __future__ import annotations

import importlib

import numpy as np
import pytest

faiss = importlib.util.find_spec("faiss")
if faiss is None:
    pytest.skip("faiss-cpu is not installed; vector backend disabled", allow_module_level=True)

from koda.services.semantic_cache_index import (  # noqa: E402
    SemanticCacheIndex,
    clear_indices_for_tests,
    get_semantic_cache_index,
)


@pytest.fixture(autouse=True)
def _clean():
    clear_indices_for_tests()
    yield
    clear_indices_for_tests()


def _normalized(values: list[float]) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float32)
    norm = np.linalg.norm(arr)
    if norm == 0:
        return arr
    return arr / norm


def test_get_semantic_cache_index_returns_singleton_per_agent():
    a = get_semantic_cache_index("agent-a", dim=4)
    b = get_semantic_cache_index("agent-a", dim=4)
    assert a is b


def test_indices_are_isolated_per_agent():
    a = get_semantic_cache_index("agent-a", dim=4)
    b = get_semantic_cache_index("agent-b", dim=4)
    assert a is not b


def test_bulk_load_empty_marks_loaded():
    index = SemanticCacheIndex("agent-test", dim=4)
    count = index.bulk_load([])
    assert count == 0
    assert index.is_loaded() is True
    assert index.size() == 0


def test_bulk_load_populates_and_searches():
    index = SemanticCacheIndex("agent-test", dim=4)
    entries = [
        (1, _normalized([1.0, 0.0, 0.0, 0.0])),
        (2, _normalized([0.0, 1.0, 0.0, 0.0])),
        (3, _normalized([0.0, 0.0, 1.0, 0.0])),
    ]
    count = index.bulk_load(entries)
    assert count == 3
    assert index.size() == 3

    # Query close to entry 1 → top hit returns cache_id=1
    query = _normalized([0.99, 0.01, 0.01, 0.0])
    hits = index.search(query, k=1, threshold=0.5)
    assert len(hits) == 1
    cache_id, similarity = hits[0]
    assert cache_id == 1
    assert similarity > 0.9


def test_search_respects_threshold():
    index = SemanticCacheIndex("agent-test", dim=4)
    index.bulk_load([(1, _normalized([1.0, 0.0, 0.0, 0.0]))])
    # Orthogonal query — similarity is 0.0, below any positive threshold.
    query = _normalized([0.0, 1.0, 0.0, 0.0])
    hits = index.search(query, k=1, threshold=0.5)
    assert hits == []


def test_search_returns_top_k_in_score_order():
    index = SemanticCacheIndex("agent-test", dim=4)
    entries = [
        (10, _normalized([1.0, 0.0, 0.0, 0.0])),
        (20, _normalized([0.95, 0.31, 0.0, 0.0])),
        (30, _normalized([0.5, 0.5, 0.5, 0.5])),
    ]
    index.bulk_load(entries)
    query = _normalized([1.0, 0.0, 0.0, 0.0])
    hits = index.search(query, k=3, threshold=0.0)
    cache_ids = [pair[0] for pair in hits]
    assert cache_ids[0] == 10
    assert cache_ids[1] == 20


def test_add_extends_index():
    index = SemanticCacheIndex("agent-test", dim=4)
    index.bulk_load([(1, _normalized([1.0, 0.0, 0.0, 0.0]))])
    index.add(2, _normalized([0.0, 1.0, 0.0, 0.0]))
    assert index.size() == 2

    query = _normalized([0.0, 1.0, 0.0, 0.0])
    hits = index.search(query, k=1, threshold=0.5)
    assert hits == [(2, pytest.approx(1.0, abs=1e-5))]


def test_dim_mismatch_skips_bulk_load():
    index = SemanticCacheIndex("agent-test", dim=4)
    bad_entry = (1, np.asarray([1.0, 0.0], dtype=np.float32))
    count = index.bulk_load([bad_entry])
    assert count == 0


def test_dim_mismatch_skips_add():
    index = SemanticCacheIndex("agent-test", dim=4)
    index.bulk_load([(1, _normalized([1.0, 0.0, 0.0, 0.0]))])
    # Wrong dim — silently dropped, no exception.
    index.add(99, np.asarray([1.0, 0.0], dtype=np.float32))
    assert index.size() == 1


def test_search_on_empty_index_returns_empty():
    index = SemanticCacheIndex("agent-test", dim=4)
    hits = index.search(_normalized([1.0, 0.0, 0.0, 0.0]), k=1, threshold=0.5)
    assert hits == []
