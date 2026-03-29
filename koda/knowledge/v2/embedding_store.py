"""Embedding persistence for knowledge v2 cutover."""

from __future__ import annotations

from koda.knowledge.config import KNOWLEDGE_EMBEDDING_MODEL
from koda.knowledge.types import KnowledgeEntry
from koda.knowledge.v2.common import V2StoreSupport


class KnowledgeEmbeddingStore(V2StoreSupport):
    """Persist embeddings for dual-write and future vector-index cutover."""

    def persist_embeddings(self, entries: list[KnowledgeEntry], embeddings: list[list[float]]) -> None:
        if not entries or not embeddings:
            return
        object_key = self.build_object_key("knowledge_embeddings", scope="latest")
        payload = {
            "model": KNOWLEDGE_EMBEDDING_MODEL,
            "items": [
                {
                    "embedding_key": entry.id,
                    "document_key": f"{entry.layer.value}:{entry.source_label}:{entry.source_path}",
                    "source_label": entry.source_label,
                    "vector": embedding,
                }
                for entry, embedding in zip(entries, embeddings, strict=True)
            ],
        }
        if self.local_write_enabled() or (self.external_write_enabled() and self._postgres.enabled):
            object_key = self.write_local_payload("knowledge_embeddings", scope="latest", payload=payload)
        if self.external_write_enabled() and self._postgres.enabled:
            self.schedule(
                self._postgres.upsert_embeddings(
                    entries=entries,
                    embeddings=embeddings,
                    object_key=object_key,
                    model=str(payload.get("model") or KNOWLEDGE_EMBEDDING_MODEL),
                )
            )
