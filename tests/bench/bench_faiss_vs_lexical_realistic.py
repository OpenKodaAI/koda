"""Realistic FAISS vs lexical cache lookup benchmark — including embed cost.

The earlier ``test_semantic_cache_benchmark.py`` measured pure-vector search
on already-embedded vectors. The honest end-to-end question, which the
production cache_manager faces every lookup, is: "given a fresh query,
which path finds a hit faster — chunked-embed-and-cosine, or
embed-once-then-faiss-search?"

This bench loads the same SentenceTransformer the cache_manager uses
(``MEMORY_EMBEDDING_MODEL``, default ``BAAI/bge-small-en-v1.5``), populates
both a numpy-rows baseline and a FAISS index, then times one cold query
through each path.

Key honest insight: in the FAISS path, candidate rows are embedded ONCE at
``bulk_load`` and reused across lookups. In the lexical path, the cache
manager re-embeds candidate rows on every lookup. So the real-world FAISS
speedup includes the embedding cost the legacy code pays.

Skipped unless ``KODA_RUN_BENCHMARKS=1``.
"""

from __future__ import annotations

import importlib.util
import os
import statistics
import time
from typing import Any

import pytest

if not os.environ.get("KODA_RUN_BENCHMARKS"):
    pytest.skip("set KODA_RUN_BENCHMARKS=1 to run", allow_module_level=True)
if importlib.util.find_spec("faiss") is None:
    pytest.skip("faiss-cpu not installed", allow_module_level=True)
if importlib.util.find_spec("sentence_transformers") is None:
    pytest.skip("sentence-transformers not installed", allow_module_level=True)

import numpy as np  # noqa: E402

from koda.services.semantic_cache_index import (  # noqa: E402
    SemanticCacheIndex,
    clear_indices_for_tests,
)


@pytest.fixture(autouse=True)
def _clean():
    clear_indices_for_tests()
    yield
    clear_indices_for_tests()


def _build_corpus(n: int) -> list[str]:
    """A spread of realistic query-like phrases."""
    bases = [
        "How do I deploy a Python web service",
        "Show me the git log for last week",
        "Explain Postgres MVCC isolation",
        "Refactor the authentication subsystem",
        "What is the time in São Paulo right now",
        "List files in the current directory",
        "Open the README and tell me the title",
        "Find Python files modified yesterday",
        "Run the database migration script",
        "Check disk usage on the server",
    ]
    out: list[str] = []
    for i in range(n):
        suffix = f" (variation {i})"
        out.append(bases[i % len(bases)] + suffix)
    return out


def _legacy_chunked_lookup(model: Any, query: str, corpus: list[str], chunk_size: int = 50) -> tuple[int, float]:
    """Mirror cache_manager._lookup_primary_semantic exactly: re-embed each lookup."""
    query_emb = model.encode(query, normalize_embeddings=True)
    best_idx, best_score = -1, -1.0
    for start in range(0, len(corpus), chunk_size):
        chunk = corpus[start : start + chunk_size]
        chunk_embs = model.encode(chunk, normalize_embeddings=True)
        # cosine similarity = inner product of normalized vectors
        scores = chunk_embs @ query_emb
        local_best = int(np.argmax(scores))
        if float(scores[local_best]) > best_score:
            best_score = float(scores[local_best])
            best_idx = start + local_best
    return best_idx, best_score


def _faiss_lookup(model: Any, query: str, index: SemanticCacheIndex) -> tuple[int, float]:
    query_emb = model.encode(query, normalize_embeddings=True)
    hits = index.search(query_emb, k=1, threshold=0.0)
    if not hits:
        return -1, 0.0
    cache_id, similarity = hits[0]
    return cache_id, similarity


@pytest.mark.parametrize("n_entries", [50, 250, 1000])
def test_e2e_faiss_vs_legacy_chunked(n_entries: int, capsys: pytest.CaptureFixture[str]) -> None:
    from sentence_transformers import SentenceTransformer  # noqa: PLC0415

    print("\n  Loading sentence transformer (BAAI/bge-small-en-v1.5)...")
    model = SentenceTransformer("BAAI/bge-small-en-v1.5", device="cpu")

    corpus = _build_corpus(n_entries)

    # Pre-embed for FAISS index
    print(f"  Pre-embedding {n_entries} corpus entries for FAISS...")
    started = time.perf_counter()
    embeddings = model.encode(corpus, normalize_embeddings=True)
    embed_time = time.perf_counter() - started
    print(f"  Pre-embed time: {embed_time:.2f}s ({n_entries / embed_time:.0f} embeds/s)")

    index = SemanticCacheIndex("bench", dim=int(embeddings.shape[1]))
    entries = [(i + 1, embeddings[i]) for i in range(n_entries)]
    index.bulk_load(entries)

    query = "How do I deploy my Python service to a Linux box?"

    # Warmup
    for _ in range(2):
        _legacy_chunked_lookup(model, query, corpus)
        _faiss_lookup(model, query, index)

    iterations = 20
    legacy_times: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        legacy_idx, _ = _legacy_chunked_lookup(model, query, corpus)
        legacy_times.append(time.perf_counter() - t0)

    faiss_times: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        faiss_idx, _ = _faiss_lookup(model, query, index)
        faiss_times.append(time.perf_counter() - t0)

    legacy_p50 = statistics.median(legacy_times) * 1000
    faiss_p50 = statistics.median(faiss_times) * 1000
    speedup = legacy_p50 / faiss_p50 if faiss_p50 > 0 else float("inf")

    with capsys.disabled():
        print(
            f"\n  n={n_entries:>4d}  legacy={legacy_p50:>7.1f}ms  faiss={faiss_p50:>7.1f}ms  speedup={speedup:>5.1f}x"
        )

    # Both paths must hit the same top result (or close to it).
    # The legacy path returns 0-indexed, FAISS index uses cache_id = i+1.
    assert legacy_idx + 1 == faiss_idx, (
        f"Top result divergence at n={n_entries}: legacy idx {legacy_idx} faiss cache_id {faiss_idx}"
    )

    # Speedup must be > 5x at n=250+ (the one-time embedding savings dominate).
    if n_entries >= 250:
        assert speedup > 5.0, (
            f"FAISS speedup at n={n_entries} only {speedup:.1f}× — expected >5× including embedding cost"
        )
