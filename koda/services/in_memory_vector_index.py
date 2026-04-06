"""Small process-local vector index used as a non-authoritative helper."""

from __future__ import annotations

import heapq
import logging
import math
from typing import Any, cast

logger = logging.getLogger(__name__)

_MAX_COLLECTION_SIZE = 50_000


def _coerce_embedding(value: Any) -> list[float]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, tuple):
        value = list(value)
    return [float(item) for item in (value or [])]


def _cosine_distance(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 1.0
    dot = sum(left_value * right_value for left_value, right_value in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(item * item for item in left))
    right_norm = math.sqrt(sum(item * item for item in right))
    if left_norm <= 0.0 or right_norm <= 0.0:
        return 1.0
    similarity = dot / (left_norm * right_norm)
    similarity = max(-1.0, min(1.0, similarity))
    return 1.0 - similarity


def _match_where(metadata: dict[str, Any], where: dict[str, Any] | None) -> bool:
    if not where:
        return True
    clauses = where.get("$and")
    if isinstance(clauses, list):
        return all(_match_where(metadata, clause if isinstance(clause, dict) else {}) for clause in clauses)
    for key, expected in where.items():
        if key == "$and":
            continue
        if metadata.get(key) != expected:
            return False
    return True


class InMemoryVectorCollection:
    """Simple cosine-similarity collection with a minimal vector-store surface."""

    def __init__(self, *, name: str, metadata: dict[str, Any] | None = None) -> None:
        self.name = name
        self.metadata = dict(metadata or {})
        self._rows: dict[str, dict[str, Any]] = {}

    def add(
        self,
        *,
        ids: list[str],
        embeddings: list[Any],
        documents: list[str] | None = None,
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        self.upsert(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)

    def upsert(
        self,
        *,
        ids: list[str],
        embeddings: list[Any],
        documents: list[str] | None = None,
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        docs = documents or [""] * len(ids)
        metas = metadatas or [{} for _ in ids]
        for row_id, embedding, document, metadata in zip(ids, embeddings, docs, metas, strict=False):
            self._rows[str(row_id)] = {
                "embedding": _coerce_embedding(embedding),
                "document": str(document or ""),
                "metadata": dict(metadata or {}),
            }
        if len(self._rows) > _MAX_COLLECTION_SIZE:
            overflow = len(self._rows) - _MAX_COLLECTION_SIZE
            logger.warning(
                "InMemoryVectorCollection '%s' exceeded size limit (%d > %d); evicting %d oldest entries",
                self.name,
                len(self._rows) + overflow,  # size before eviction (already added)
                _MAX_COLLECTION_SIZE,
                overflow,
            )
            keys_to_remove = list(self._rows.keys())[:overflow]
            for key in keys_to_remove:
                del self._rows[key]

    def delete(self, *, ids: list[str] | None = None, where: dict[str, Any] | None = None) -> None:
        if ids:
            for row_id in ids:
                self._rows.pop(str(row_id), None)
            return
        if where:
            for row_id in [candidate for candidate, row in self._rows.items() if _match_where(row["metadata"], where)]:
                self._rows.pop(row_id, None)
            return
        self._rows.clear()

    def query(
        self,
        *,
        query_embeddings: list[Any],
        n_results: int,
        where: dict[str, Any] | None = None,
        include: list[str] | None = None,
    ) -> dict[str, list[list[Any]]]:
        candidates = [
            (row_id, row) for row_id, row in self._rows.items() if _match_where(dict(row.get("metadata") or {}), where)
        ]
        ids_payload: list[list[str]] = []
        distances_payload: list[list[float]] = []
        metadatas_payload: list[list[dict[str, Any]]] = []
        documents_payload: list[list[str]] = []
        for query_embedding in query_embeddings:
            query_vector = _coerce_embedding(query_embedding)
            scored = heapq.nsmallest(
                max(0, n_results),
                (
                    (
                        _cosine_distance(query_vector, cast(list[float], row["embedding"])),
                        row_id,
                        row,
                    )
                    for row_id, row in candidates
                ),
                key=lambda item: (item[0], item[1]),
            )
            ids_payload.append([row_id for _, row_id, _ in scored])
            distances_payload.append([distance for distance, _, _ in scored])
            metadatas_payload.append([dict(row.get("metadata") or {}) for _, _, row in scored])
            documents_payload.append([str(row.get("document") or "") for _, _, row in scored])
        return {
            "ids": ids_payload,
            "distances": distances_payload,
            "metadatas": metadatas_payload,
            "documents": documents_payload,
        }

    def get(
        self,
        *,
        ids: list[str] | None = None,
        where: dict[str, Any] | None = None,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        del include
        rows = [
            (row_id, row)
            for row_id, row in self._rows.items()
            if (not ids or row_id in {str(item) for item in ids})
            and _match_where(dict(row.get("metadata") or {}), where)
        ]
        return {
            "ids": [row_id for row_id, _ in rows],
            "metadatas": [dict(row.get("metadata") or {}) for _, row in rows],
            "documents": [str(row.get("document") or "") for _, row in rows],
        }


class InMemoryVectorClient:
    """Factory/registry for in-memory collections."""

    def __init__(self) -> None:
        self._collections: dict[str, InMemoryVectorCollection] = {}

    def get_or_create_collection(
        self,
        *,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> InMemoryVectorCollection:
        collection = self._collections.get(name)
        if collection is None:
            collection = InMemoryVectorCollection(name=name, metadata=metadata)
            self._collections[name] = collection
        return collection
