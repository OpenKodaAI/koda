"""Document persistence for knowledge v2 cutover."""

from __future__ import annotations

from koda.knowledge.types import KnowledgeEntry
from koda.knowledge.v2.common import V2StoreSupport


class KnowledgeDocumentStore(V2StoreSupport):
    """Persist document/chunk manifests for dual-write and future primary reads."""

    def persist_entries(self, entries: list[KnowledgeEntry]) -> None:
        if not entries:
            return
        object_key = self.build_object_key("knowledge_documents", scope="latest")
        payload = {
            "items": [
                {
                    "entry_id": entry.id,
                    "document_key": self._document_key(entry),
                    "source_label": entry.source_label,
                    "source_path": entry.source_path,
                    "layer": entry.layer.value,
                    "scope": entry.scope.value,
                    "title": entry.title,
                    "content": entry.content,
                    "updated_at": entry.updated_at.isoformat(),
                    "owner": entry.owner,
                    "project_key": entry.project_key,
                    "environment": entry.environment,
                    "team": entry.team,
                    "source_type": entry.source_type,
                    "operable": entry.operable,
                }
                for entry in entries
            ]
        }
        if self.local_write_enabled() or (self.external_write_enabled() and self._postgres.enabled):
            object_key = self.write_local_payload("knowledge_documents", scope="latest", payload=payload)
        if self.external_write_enabled() and self._postgres.enabled:
            self.schedule(
                self._postgres.upsert_documents(
                    entries,
                    object_key=object_key,
                )
            )

    def _document_key(self, entry: KnowledgeEntry) -> str:
        return f"{entry.layer.value}:{entry.source_label}:{entry.source_path}"
