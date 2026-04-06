"""Tests for koda.skills._index — embedding-based skill search."""

from __future__ import annotations

import math
from unittest.mock import patch

import pytest

from koda.skills._index import (
    _SIMILARITY_THRESHOLD,
    SkillEmbeddingIndex,
    _tfidf_vector,
    get_shared_index,
)
from koda.skills._registry import SkillDefinition

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_skill(
    skill_id: str,
    *,
    name: str = "",
    category: str = "general",
    tags: tuple[str, ...] = (),
    version: str = "1.0.0",
    embedding_text: str = "",
) -> SkillDefinition:
    return SkillDefinition(
        id=skill_id,
        name=name or skill_id.replace("-", " ").title(),
        category=category,
        tags=tags,
        version=version,
        embedding_text=embedding_text or f"{skill_id} skill description",
    )


def _deterministic_embed(text: str) -> list[float]:
    """Return a deterministic TF-IDF vector for testing."""
    return _tfidf_vector(text)


def _deterministic_embed_batch(texts: list[str]) -> list[list[float]]:
    return [_deterministic_embed(t) for t in texts]


@pytest.fixture(autouse=True)
def _force_tfidf_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent SentenceTransformer from loading — always use TF-IDF fallback."""
    monkeypatch.setattr("koda.skills._index._embed_model", None)
    monkeypatch.setattr("koda.skills._index._embed_model_available", False)


@pytest.fixture()
def _reset_shared_index(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.skills._index._shared_index", None)


# ---------------------------------------------------------------------------
# TF-IDF fallback
# ---------------------------------------------------------------------------


class TestTfidfVector:
    def test_produces_normalised_vector(self) -> None:
        vec = _tfidf_vector("hello world")
        norm = math.sqrt(sum(v * v for v in vec))
        assert abs(norm - 1.0) < 1e-6

    def test_empty_text_returns_zero_vector(self) -> None:
        vec = _tfidf_vector("")
        assert all(v == 0.0 for v in vec)

    def test_same_text_same_vector(self) -> None:
        a = _tfidf_vector("write unit tests")
        b = _tfidf_vector("write unit tests")
        assert a == b


# ---------------------------------------------------------------------------
# Index unit tests
# ---------------------------------------------------------------------------


class TestRebuild:
    def test_rebuild_indexes_all_skills(self) -> None:
        idx = SkillEmbeddingIndex()
        skills = {
            "tdd": _make_skill("tdd", tags=("testing",)),
            "security": _make_skill("security", tags=("owasp",)),
            "docs": _make_skill("docs"),
        }
        idx.rebuild(skills)

        assert set(idx._indexed_versions.keys()) == {"tdd", "security", "docs"}

    def test_rebuild_clears_previous(self) -> None:
        idx = SkillEmbeddingIndex()
        idx.rebuild({"a": _make_skill("a")})
        assert "a" in idx._indexed_versions

        idx.rebuild({"b": _make_skill("b")})
        assert "a" not in idx._indexed_versions
        assert "b" in idx._indexed_versions

    def test_rebuild_empty(self) -> None:
        idx = SkillEmbeddingIndex()
        idx.rebuild({})
        assert idx._indexed_versions == {}


class TestQuery:
    def test_query_returns_ranked_results(self) -> None:
        idx = SkillEmbeddingIndex()
        skills = {
            "tdd": _make_skill("tdd", embedding_text="test driven development write unit tests"),
            "docs": _make_skill("docs", embedding_text="documentation writing technical docs"),
            "security": _make_skill("security", embedding_text="security vulnerabilities owasp"),
        }
        idx.rebuild(skills)

        results = idx.query("write unit tests")
        # "tdd" should rank higher because its embedding text shares more
        # terms with the query.
        assert len(results) > 0
        skill_ids = [r[0] for r in results]
        assert "tdd" in skill_ids

    def test_query_empty_returns_empty(self) -> None:
        idx = SkillEmbeddingIndex()
        idx.rebuild({"tdd": _make_skill("tdd")})
        assert idx.query("") == []
        assert idx.query("   ") == []

    def test_query_with_category_filter(self) -> None:
        idx = SkillEmbeddingIndex()
        skills = {
            "tdd": _make_skill("tdd", category="engineering", embedding_text="write tests for modules"),
            "docs": _make_skill("docs", category="writing", embedding_text="write documentation for modules"),
        }
        idx.rebuild(skills)

        results_eng = idx.query("write tests for modules", category_filter="engineering")
        ids_eng = [r[0] for r in results_eng]
        assert "docs" not in ids_eng

    def test_query_with_tag_filter(self) -> None:
        idx = SkillEmbeddingIndex()
        skills = {
            "tdd": _make_skill("tdd", tags=("testing", "quality"), embedding_text="test driven development"),
            "security": _make_skill("security", tags=("owasp", "quality"), embedding_text="test driven security"),
        }
        idx.rebuild(skills)

        results = idx.query("test driven", tag_filter=["testing"])
        ids = [r[0] for r in results]
        # Only "tdd" has the "testing" tag.
        assert "security" not in ids

    def test_similarity_threshold_filters_noise(self) -> None:
        idx = SkillEmbeddingIndex()
        skills = {
            "alpha": _make_skill("alpha", embedding_text="completely unrelated banana orange mango"),
        }
        idx.rebuild(skills)

        # A query sharing zero terms should produce very low similarity.
        results = idx.query("kubernetes deployment helm chart")
        for _skill_id, score in results:
            assert score >= _SIMILARITY_THRESHOLD


class TestUpdateSkill:
    def test_update_skill_incremental(self) -> None:
        idx = SkillEmbeddingIndex()
        skills = {
            "tdd": _make_skill("tdd", version="1.0.0"),
            "docs": _make_skill("docs", version="1.0.0"),
        }
        idx.rebuild(skills)

        # Update only tdd to a new version.
        updated_tdd = _make_skill("tdd", version="2.0.0", embedding_text="updated tdd content")
        idx.update_skill(updated_tdd)

        assert idx._indexed_versions["tdd"] == "2.0.0"
        assert idx._indexed_versions["docs"] == "1.0.0"

    def test_update_skill_skips_same_version(self) -> None:
        idx = SkillEmbeddingIndex()
        skills = {"tdd": _make_skill("tdd", version="1.0.0")}
        idx.rebuild(skills)

        # Calling update with the same version should be a no-op.
        with patch.object(idx._collection, "upsert") as mock_upsert:
            idx.update_skill(_make_skill("tdd", version="1.0.0"))
            mock_upsert.assert_not_called()

    def test_update_skill_upserts_new_version(self) -> None:
        idx = SkillEmbeddingIndex()
        skills = {"tdd": _make_skill("tdd", version="1.0.0")}
        idx.rebuild(skills)

        with patch.object(idx._collection, "upsert") as mock_upsert:
            idx.update_skill(_make_skill("tdd", version="2.0.0"))
            mock_upsert.assert_called_once()


class TestSharedIndex:
    @pytest.mark.usefixtures("_reset_shared_index")
    def test_get_shared_index_returns_singleton(self) -> None:
        a = get_shared_index()
        b = get_shared_index()
        assert a is b


# ---------------------------------------------------------------------------
# Integration tests — skipped when SentenceTransformer is unavailable
# ---------------------------------------------------------------------------

_st_available = False
try:
    from sentence_transformers import SentenceTransformer  # noqa: F401

    _st_available = True
except ImportError:
    pass


@pytest.mark.skipif(not _st_available, reason="sentence-transformers not installed")
class TestIntegrationWithTransformer:
    """These tests use the real embedding model and are skipped in CI."""

    @pytest.fixture(autouse=True)
    def _enable_transformer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Re-enable SentenceTransformer for this test class."""
        monkeypatch.setattr("koda.skills._index._embed_model", None)
        monkeypatch.setattr("koda.skills._index._embed_model_available", None)

    def test_tdd_matches_write_tests(self) -> None:
        idx = SkillEmbeddingIndex()
        skills = {
            "tdd": _make_skill(
                "tdd",
                embedding_text="test driven development write unit tests testing quality assurance",
                tags=("testing",),
            ),
            "docs": _make_skill(
                "docs",
                embedding_text="documentation writing technical reference guides",
            ),
            "security": _make_skill(
                "security",
                embedding_text="security audit vulnerability scanning OWASP",
            ),
        }
        idx.rebuild(skills)

        results = idx.query("write unit tests for this module")
        top_ids = [r[0] for r in results[:3]]
        assert "tdd" in top_ids

    def test_security_matches_owasp(self) -> None:
        idx = SkillEmbeddingIndex()
        skills = {
            "tdd": _make_skill(
                "tdd",
                embedding_text="test driven development write unit tests",
            ),
            "security": _make_skill(
                "security",
                embedding_text="security audit vulnerability scanning OWASP penetration testing",
                tags=("owasp", "security"),
            ),
            "docs": _make_skill(
                "docs",
                embedding_text="documentation writing technical reference guides",
            ),
        }
        idx.rebuild(skills)

        results = idx.query("check for OWASP vulnerabilities")
        top_ids = [r[0] for r in results[:3]]
        assert "security" in top_ids
