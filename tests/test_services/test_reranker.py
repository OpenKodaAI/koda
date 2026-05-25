"""Tests for the cross-encoder reranker."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import koda.services.reranker as reranker_module
from koda.services.reranker import rerank_sync, reset_for_tests


@pytest.fixture(autouse=True)
def _reset():
    reset_for_tests()
    yield
    reset_for_tests()


def test_disabled_returns_identity(monkeypatch):
    monkeypatch.setattr(reranker_module, "is_enabled", lambda: False)
    result = rerank_sync("query", ["doc a", "doc b", "doc c"])
    assert [pair[0] for pair in result] == [0, 1, 2]
    assert all(score == 0.0 for _, score in result)


def test_empty_documents_returns_empty(monkeypatch):
    monkeypatch.setattr(reranker_module, "is_enabled", lambda: True)
    assert rerank_sync("query", []) == []


def test_top_k_caps_results(monkeypatch):
    monkeypatch.setattr(reranker_module, "is_enabled", lambda: False)
    result = rerank_sync("query", ["a", "b", "c"], top_k=2)
    assert len(result) == 2


def test_load_failure_returns_identity(monkeypatch):
    """If FlagEmbedding isn't installed, reranker degrades gracefully."""
    monkeypatch.setattr(reranker_module, "is_enabled", lambda: True)

    def fake_load() -> None:
        return None

    monkeypatch.setattr(reranker_module, "_load_model", fake_load)
    result = rerank_sync("query", ["doc a", "doc b"])
    assert [pair[0] for pair in result] == [0, 1]


def test_score_failure_returns_identity(monkeypatch):
    """If the model raises during scoring, identity ordering preserved."""
    monkeypatch.setattr(reranker_module, "is_enabled", lambda: True)

    fake_model = MagicMock()
    fake_model.predict.side_effect = RuntimeError("OOM")
    monkeypatch.setattr(reranker_module, "_load_model", lambda: fake_model)

    result = rerank_sync("query", ["a", "b", "c"])
    assert [pair[0] for pair in result] == [0, 1, 2]


def test_successful_reordering(monkeypatch):
    """When scoring works, results sort descending by score."""
    monkeypatch.setattr(reranker_module, "is_enabled", lambda: True)

    fake_model = MagicMock()
    # doc 1 wins, doc 2 second, doc 0 last
    fake_model.predict.return_value = [0.1, 0.9, 0.5]
    monkeypatch.setattr(reranker_module, "_load_model", lambda: fake_model)

    result = rerank_sync("query", ["doc 0", "doc 1", "doc 2"])
    indices = [pair[0] for pair in result]
    assert indices[0] == 1
    assert indices[1] == 2
    assert indices[2] == 0


def test_single_score_result_handled(monkeypatch):
    """compute_score may return a scalar for a single pair."""
    monkeypatch.setattr(reranker_module, "is_enabled", lambda: True)

    fake_model = MagicMock()
    fake_model.predict.return_value = 0.42
    monkeypatch.setattr(reranker_module, "_load_model", lambda: fake_model)

    result = rerank_sync("query", ["only doc"])
    assert result == [(0, pytest.approx(0.42))]


def test_is_enabled_delegates_to_runtime_capabilities(monkeypatch):
    """``is_enabled()`` must round-trip through the runtime_capabilities resolver."""
    import koda.services.runtime_capabilities as caps  # noqa: PLC0415

    monkeypatch.setattr(caps, "effective_rerank_enabled", lambda: False)
    assert reranker_module.is_enabled() is False
    monkeypatch.setattr(caps, "effective_rerank_enabled", lambda: True)
    assert reranker_module.is_enabled() is True


# ---------------------------------------------------------------------------
# Real-model integration test. Skipped unless ``KODA_RUN_RERANKER_E2E=1`` so
# the regular pytest run stays under a second. Catches API-shape regressions
# (this is exactly what surfaced the FlagEmbedding ↔ transformers-5
# incompatibility that mocked tests would have missed).
# ---------------------------------------------------------------------------


import os as _os  # noqa: E402

import pytest as _pytest  # noqa: E402

_E2E_ENABLED = bool(_os.environ.get("KODA_RUN_RERANKER_E2E"))


@_pytest.mark.skipif(not _E2E_ENABLED, reason="set KODA_RUN_RERANKER_E2E=1 to run")
def test_real_cross_encoder_ranking_is_semantically_sensible(monkeypatch):
    """Load the real BGE reranker and verify it discriminates relevant from irrelevant docs."""
    monkeypatch.setattr(reranker_module, "is_enabled", lambda: True)
    monkeypatch.setattr(reranker_module, "RERANK_MODEL", "BAAI/bge-reranker-base")
    monkeypatch.setattr(reranker_module, "RERANK_DEVICE", "cpu")
    reset_for_tests()

    query = "How to deploy a Python web service on Linux"
    docs = [
        "Use systemd to manage the python process. Set up a unit file in /etc/systemd/system/.",
        "Cats are wonderful pets that purr when happy.",
        "gunicorn is a Python WSGI HTTP server for UNIX. Run with: gunicorn app:app",
        "The capital of France is Paris.",
        "Docker containers package your Python app with all its dependencies for portable Linux deployment.",
        "JavaScript is a programming language for web browsers.",
    ]
    relevant = {0, 2, 4}  # systemd, gunicorn, docker
    irrelevant = {1, 3, 5}  # cats, paris, javascript

    results = rerank_sync(query, docs, top_k=6)
    indices = [i for i, _ in results]

    # Top ranked must be a relevant doc.
    assert indices[0] in relevant, f"Top hit {indices[0]} should be relevant. Full ranking: {indices}"

    # Bottom ranked must be an irrelevant doc.
    assert indices[-1] in irrelevant, f"Bottom hit {indices[-1]} should be irrelevant"

    # At least 2 of the 3 relevant docs should be in the top half.
    top_half = set(indices[:3])
    assert len(top_half & relevant) >= 2, f"Relevant in top 3: {top_half & relevant}"

    # Score gradient must be meaningful (not all zeros — that's the failure
    # mode of the original FlagEmbedding API mismatch).
    scores = [score for _, score in results]
    assert max(scores) > 0.1, f"Top score {max(scores)} too low — reranker not producing gradient"
