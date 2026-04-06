"""Embedding-based semantic index for skill matching."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from koda.services.in_memory_vector_index import InMemoryVectorCollection
    from koda.skills._registry import SkillDefinition

logger = logging.getLogger(__name__)

_SIMILARITY_THRESHOLD = 0.35

# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------

_embed_model: Any = None
_embed_model_available: bool | None = None


def _try_load_sentence_transformer() -> Any:
    """Load SentenceTransformer if the library is installed."""
    global _embed_model, _embed_model_available  # noqa: PLW0603
    if _embed_model_available is False:
        return None
    if _embed_model is not None:
        return _embed_model
    try:
        from sentence_transformers import SentenceTransformer

        from koda.memory.config import MEMORY_EMBEDDING_MODEL

        _embed_model = SentenceTransformer(MEMORY_EMBEDDING_MODEL)
        _embed_model_available = True
        return _embed_model
    except Exception:  # noqa: BLE001
        _embed_model_available = False
        return None


def _tfidf_vector(text: str, *, dim: int = 128) -> list[float]:
    """Produce a simple term-frequency vector as a fallback embedding.

    This is intentionally crude -- it exists only so that the index can
    function in environments where ``sentence-transformers`` is not
    installed (e.g. lightweight CI runners).
    """
    terms = text.lower().split()
    freq: dict[int, float] = {}
    for term in terms:
        bucket = hash(term) % dim
        freq[bucket] = freq.get(bucket, 0.0) + 1.0
    # L2-normalise so cosine distance works correctly.
    vec = [freq.get(i, 0.0) for i in range(dim)]
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def _embed(text: str) -> list[float]:
    """Embed *text* using SentenceTransformer or the TF-IDF fallback."""
    model = _try_load_sentence_transformer()
    if model is not None:
        result: list[float] = model.encode(text, normalize_embeddings=True).tolist()
        return result
    return _tfidf_vector(text)


def _embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts."""
    model = _try_load_sentence_transformer()
    if model is not None:
        results = model.encode(texts, normalize_embeddings=True)
        return [list(v) for v in results.tolist()]
    return [_tfidf_vector(t) for t in texts]


# ---------------------------------------------------------------------------
# SkillEmbeddingIndex
# ---------------------------------------------------------------------------


class SkillEmbeddingIndex:
    """Wraps :class:`InMemoryVectorCollection` for semantic skill search."""

    _collection: InMemoryVectorCollection
    _indexed_versions: dict[str, str]

    def __init__(self) -> None:
        from koda.services.in_memory_vector_index import InMemoryVectorClient

        client = InMemoryVectorClient()
        self._collection = client.get_or_create_collection(name="skill_index")
        self._indexed_versions = {}

    def rebuild(self, skills: dict[str, SkillDefinition]) -> None:
        """Re-index all skills.  Delete old entries, then upsert new ones."""
        self._collection.delete()
        self._indexed_versions.clear()

        if not skills:
            return

        ids: list[str] = []
        texts: list[str] = []
        metadatas: list[dict[str, Any]] = []

        for skill_id, defn in skills.items():
            ids.append(skill_id)
            texts.append(defn.embedding_text or defn.name)
            metadatas.append(
                {
                    "category": defn.category,
                    "tags": " ".join(defn.tags),
                    "skill_id": skill_id,
                }
            )

        embeddings = _embed_batch(texts)

        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

        for skill_id, defn in skills.items():
            self._indexed_versions[skill_id] = defn.version

        logger.debug("skill_embedding_index_rebuilt count=%d", len(skills))

    def update_skill(self, skill: SkillDefinition) -> None:
        """Update a single skill's embedding only if its version changed."""
        cached_version = self._indexed_versions.get(skill.id)
        if cached_version == skill.version:
            return

        text = skill.embedding_text or skill.name
        embedding = _embed(text)

        self._collection.upsert(
            ids=[skill.id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[
                {
                    "category": skill.category,
                    "tags": " ".join(skill.tags),
                    "skill_id": skill.id,
                }
            ],
        )
        self._indexed_versions[skill.id] = skill.version

    def query(
        self,
        query_text: str,
        *,
        n_results: int = 8,
        category_filter: str | None = None,
        tag_filter: list[str] | None = None,
    ) -> list[tuple[str, float]]:
        """Return ``(skill_id, similarity_score)`` pairs ranked by cosine similarity.

        Results below :data:`_SIMILARITY_THRESHOLD` are excluded.
        """
        if not query_text or not query_text.strip():
            return []

        query_embedding = _embed(query_text)

        where: dict[str, Any] | None = None
        clauses: list[dict[str, Any]] = []
        if category_filter:
            clauses.append({"category": category_filter})
        if tag_filter:
            # The tags field is stored as a space-joined string.  For each
            # requested tag we cannot use simple equality, so we filter
            # post-query below instead.
            pass
        if len(clauses) == 1:
            where = clauses[0]
        elif len(clauses) > 1:
            where = {"$and": clauses}

        raw = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
        )

        result_ids: list[str] = raw["ids"][0] if raw["ids"] else []
        distances: list[float] = raw["distances"][0] if raw["distances"] else []
        metadatas: list[dict[str, Any]] = raw["metadatas"][0] if raw["metadatas"] else []

        pairs: list[tuple[str, float]] = []
        for skill_id, distance, meta in zip(result_ids, distances, metadatas, strict=False):
            similarity = 1.0 - distance

            if similarity < _SIMILARITY_THRESHOLD:
                continue

            # Post-query tag filter: every requested tag must appear in the
            # space-joined tags string.
            if tag_filter:
                stored_tags = str(meta.get("tags", "")).lower()
                if not all(t.lower() in stored_tags for t in tag_filter):
                    continue

            pairs.append((skill_id, similarity))

        # Sort descending by similarity.
        pairs.sort(key=lambda item: item[1], reverse=True)
        return pairs


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_shared_index: SkillEmbeddingIndex | None = None


def get_shared_index() -> SkillEmbeddingIndex:
    """Return (and lazily create) the process-wide :class:`SkillEmbeddingIndex`."""
    global _shared_index  # noqa: PLW0603
    if _shared_index is None:
        _shared_index = SkillEmbeddingIndex()
    return _shared_index
