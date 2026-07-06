"""Graph persistence helpers for knowledge v2."""

from __future__ import annotations

from typing import Any

from koda.knowledge.repository import KnowledgeRepository
from koda.knowledge.types import GraphEntity, GraphRelation
from koda.knowledge.v2.common import V2StoreSupport


class KnowledgeGraphStore(V2StoreSupport):
    """Persist graph projections and expose repository snapshots."""

    def __init__(self, repository: KnowledgeRepository, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._repository = repository

    def persist_projection(self, payload: dict[str, Any]) -> None:
        if not self.external_write_enabled() or not self._postgres.enabled:
            return
        entities = [
            GraphEntity(
                entity_key=str(item.get("entity_key") or ""),
                entity_type=str(item.get("entity_type") or ""),
                label=str(item.get("label") or ""),
                agent_id=self._agent_id,
                source_kind=str(item.get("source_kind") or "knowledge"),
                metadata=dict(item.get("metadata") or {}),
            )
            for item in payload.get("linked_entities") or []
            if item.get("entity_key")
        ]
        relations = [
            GraphRelation(
                relation_key=str(item.get("relation_key") or ""),
                relation_type=str(item.get("relation_type") or ""),
                source_entity_key=str(item.get("source_entity_key") or ""),
                target_entity_key=str(item.get("target_entity_key") or ""),
                agent_id=self._agent_id,
                weight=float(item.get("weight") or 0.0),
                metadata=dict(item.get("metadata") or {}),
            )
            for item in payload.get("graph_relations") or []
            if item.get("relation_key")
        ]
        if entities or relations:
            self.schedule(self._postgres.upsert_graph(entities=entities, relations=relations))
