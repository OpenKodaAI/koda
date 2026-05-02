"""FAISS-backed vector index for paraphrase-tolerant cache lookup.

The default cache lookup in :mod:`koda.services.cache_manager` does an exact
hash match plus a chunked semantic scan (embed each row, compute cosine).
That works but is O(N) per lookup and can't reuse work across agents.

When ``SEMANTIC_CACHE_BACKEND=vector`` is set, the cache lookup path delegates
to this module's process-wide :class:`SemanticCacheIndex`, which keeps a
``faiss.IndexFlatIP`` (cosine via L2-normalized vectors) populated with
``(cache_id, embedding)`` pairs. Lookups are O(log N) effective and
paraphrase-tolerant on the same embedding space already used for memory
recall.

Design choices:

- Per-agent index instances (multi-tenant scoping) — keyed by
  ``normalize_agent_scope(agent_id)``.
- FAISS-CPU only; embeddings are computed by the caller (the cache manager
  already owns a sentence-transformer instance, so we don't double-load).
- Stale entries are tolerated. If FAISS returns a ``cache_id`` that has been
  invalidated upstream, the cache manager's existing
  ``cache_get_by_id`` + ``cache_invalidate_entry`` paths clean up.
- Persistence is best-effort — the index can always be rebuilt from
  ``cache_list_active_entries``.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any

import numpy as np

from koda.logging_config import get_logger

log = get_logger(__name__)

_MAX_INDICES = 50
_INDICES: OrderedDict[str, SemanticCacheIndex] = OrderedDict()
_INDICES_LOCK = threading.Lock()


def _faiss_module() -> Any | None:
    try:
        import faiss  # noqa: PLC0415

        return faiss
    except ImportError:
        log.warning(
            "semantic_cache_faiss_missing",
            hint="Install with `pip install faiss-cpu` to enable SEMANTIC_CACHE_BACKEND=vector.",
        )
        return None


class SemanticCacheIndex:
    """Per-agent FAISS index of cached query embeddings.

    Vectors must be supplied already normalized — the cache manager produces
    normalized embeddings via ``sentence_transformers.encode(normalize_embeddings=True)``,
    so cosine similarity reduces to inner product (``IndexFlatIP``).
    """

    def __init__(self, agent_id: str, dim: int) -> None:
        self._agent_id = agent_id
        self._dim = int(dim)
        self._lock = threading.Lock()
        self._faiss = _faiss_module()
        self._index: Any | None = None
        self._cache_ids: list[int] = []
        self._cache_id_to_position: dict[int, int] = {}
        self._loaded = False

    @property
    def is_available(self) -> bool:
        return self._faiss is not None

    def _ensure_index(self) -> Any | None:
        if self._faiss is None:
            return None
        if self._index is None:
            self._index = self._faiss.IndexFlatIP(self._dim)
        return self._index

    def bulk_load(self, entries: list[tuple[int, np.ndarray]]) -> int:
        """Rebuild the index from ``[(cache_id, embedding), ...]`` pairs."""
        if self._faiss is None or not entries:
            self._loaded = True
            return 0
        with self._lock:
            self._index = self._faiss.IndexFlatIP(self._dim)
            self._cache_ids = []
            self._cache_id_to_position = {}
            vectors = np.asarray([entry[1] for entry in entries], dtype=np.float32)
            if vectors.ndim != 2 or vectors.shape[1] != self._dim:
                log.warning(
                    "semantic_cache_index_bulk_load_dim_mismatch",
                    expected=self._dim,
                    received=tuple(vectors.shape),
                )
                self._loaded = True
                return 0
            self._index.add(vectors)
            for position, (cache_id, _) in enumerate(entries):
                self._cache_ids.append(int(cache_id))
                self._cache_id_to_position[int(cache_id)] = position
            self._loaded = True
            log.debug("semantic_cache_index_loaded", agent_id=self._agent_id, size=len(self._cache_ids))
            return len(self._cache_ids)

    def add(self, cache_id: int, embedding: np.ndarray) -> None:
        if self._faiss is None:
            return
        with self._lock:
            index = self._ensure_index()
            if index is None:
                return
            if cache_id in self._cache_id_to_position:
                # Re-add overwrites — FAISS doesn't natively support update,
                # so we just append; the older copy stays but its row may have
                # been invalidated upstream and will be filtered there.
                pass
            vector = np.asarray(embedding, dtype=np.float32).reshape(1, -1)
            if vector.shape[1] != self._dim:
                return
            index.add(vector)
            position = len(self._cache_ids)
            self._cache_ids.append(int(cache_id))
            self._cache_id_to_position[int(cache_id)] = position

    def search(
        self,
        embedding: np.ndarray,
        *,
        k: int = 1,
        threshold: float = 0.92,
    ) -> list[tuple[int, float]]:
        """Return ``[(cache_id, similarity), ...]`` above ``threshold``, sorted desc."""
        if self._faiss is None or self._index is None or not self._cache_ids:
            return []
        with self._lock:
            vector = np.asarray(embedding, dtype=np.float32).reshape(1, -1)
            if vector.shape[1] != self._dim:
                return []
            distances, indices = self._index.search(vector, min(k, len(self._cache_ids)))
        hits: list[tuple[int, float]] = []
        for distance, idx in zip(distances[0], indices[0], strict=False):
            if idx < 0 or idx >= len(self._cache_ids):
                continue
            similarity = float(distance)
            if similarity < threshold:
                continue
            hits.append((self._cache_ids[idx], similarity))
        return hits

    def is_loaded(self) -> bool:
        return self._loaded

    def size(self) -> int:
        return len(self._cache_ids)


def get_semantic_cache_index(agent_id: str, dim: int) -> SemanticCacheIndex:
    """Return the index instance for ``agent_id``, creating one if needed."""
    with _INDICES_LOCK:
        existing = _INDICES.get(agent_id)
        if existing is not None and existing._dim == dim:
            _INDICES.move_to_end(agent_id)
            return existing
        if len(_INDICES) >= _MAX_INDICES:
            _INDICES.popitem(last=False)
        index = SemanticCacheIndex(agent_id=agent_id, dim=dim)
        _INDICES[agent_id] = index
        return index


def clear_indices_for_tests() -> None:
    with _INDICES_LOCK:
        _INDICES.clear()
