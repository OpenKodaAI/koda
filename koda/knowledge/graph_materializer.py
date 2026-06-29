"""Materialize knowledge and artifact evidence into a persisted graph efficiently."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from koda.knowledge.repository import KnowledgeRepository
from koda.knowledge.types import ArtifactEvidenceNode, GraphEntity, GraphRelation, KnowledgeEntry

_ISSUE_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")
_PATH_RE = re.compile(r"(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+")
_ERROR_RE = re.compile(r"\b([A-Z][A-Za-z]+(?:Error|Exception))\b")
_SYMBOL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*)\b")
_PATH_SUFFIX_STRIP = ".,;:)]}>\"'"
_PATH_ANCHORS = ("services", "service", "src", "app", "lib", "packages", "tests", "docs")


def _fingerprint_parts(parts: list[str]) -> str:
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8"), usedforsecurity=False).hexdigest()


@dataclass(slots=True)
class _MaterializedEntry:
    fingerprint: str
    entities: list[GraphEntity]
    relations: list[GraphRelation]


class KnowledgeGraphMaterializer:
    """Batch graph materialization with in-memory dedupe of unchanged sources."""

    def __init__(self, repository: KnowledgeRepository, agent_id: str | None = None) -> None:
        self._repository = repository
        self._agent_id = agent_id
        self._entry_fingerprints: dict[str, str] = {}
        self._artifact_fingerprints: dict[str, str] = {}

    def materialize_entries(self, entries: list[KnowledgeEntry]) -> None:
        entities: list[GraphEntity] = []
        relations: list[GraphRelation] = []
        for entry in entries:
            materialized = self._materialize_entry(entry)
            previous = self._entry_fingerprints.get(entry.id)
            if previous == materialized.fingerprint:
                continue
            self._entry_fingerprints[entry.id] = materialized.fingerprint
            entities.extend(materialized.entities)
            relations.extend(materialized.relations)
        self._repository.batch_upsert_graph(entities=entities, relations=relations)

    def materialize_artifacts(self, nodes: list[ArtifactEvidenceNode], relations: list[GraphRelation]) -> None:
        fresh_nodes = []
        fresh_entities = []
        fresh_relations = list(relations)
        for node in nodes:
            fingerprint = _fingerprint_parts(
                [
                    node.evidence_key,
                    node.modality.value,
                    node.label,
                    node.extracted_text,
                    node.source_path,
                    node.source_url,
                    node.trust_level,
                    str(node.metadata.get("source_hash") or ""),
                ]
            )
            if self._artifact_fingerprints.get(node.evidence_key) == fingerprint:
                continue
            self._artifact_fingerprints[node.evidence_key] = fingerprint
            fresh_nodes.append(node)
            fresh_entities.append(
                GraphEntity(
                    entity_key=f"artifact_evidence:{node.evidence_key}",
                    entity_type="artifact_evidence",
                    label=node.label,
                    agent_id=node.agent_id or self._agent_id,
                    source_kind="artifact",
                    metadata={
                        "modality": node.modality.value,
                        "task_id": node.task_id,
                        "artifact_id": node.artifact_id,
                    },
                )
            )
        self._repository.batch_upsert_artifact_evidence(fresh_nodes)
        self._repository.batch_upsert_graph(entities=fresh_entities, relations=fresh_relations)

    def _materialize_entry(self, entry: KnowledgeEntry) -> _MaterializedEntry:
        fingerprint = _fingerprint_parts(
            [
                entry.id,
                entry.title,
                entry.content,
                entry.layer.value,
                entry.scope.value,
                entry.source_label,
                entry.source_path,
                entry.updated_at.isoformat(),
                entry.project_key,
                entry.environment,
                entry.team,
                ",".join(entry.tags),
                entry.source_type,
                str(entry.operable),
            ]
        )
        entry_key = f"entry:{entry.layer.value}:{entry.id}"
        entities = [
            GraphEntity(
                entity_key=entry_key,
                entity_type=entry.layer.value,
                label=entry.title,
                agent_id=self._agent_id,
                source_kind=entry.source_type,
                metadata={
                    "scope": entry.scope.value,
                    "source_label": entry.source_label,
                    "source_path": entry.source_path,
                    "project_key": entry.project_key,
                    "environment": entry.environment,
                    "team": entry.team,
                    "operable": entry.operable,
                },
            ),
            GraphEntity(
                entity_key=f"source:{entry.source_label}",
                entity_type="source",
                label=entry.source_label,
                agent_id=self._agent_id,
                source_kind="source",
                metadata={"source_path": entry.source_path, "layer": entry.layer.value},
            ),
        ]
        relations = [
            GraphRelation(
                relation_key=f"derived_from:{entry_key}:source:{entry.source_label}",
                relation_type="derived_from",
                source_entity_key=entry_key,
                target_entity_key=f"source:{entry.source_label}",
                agent_id=self._agent_id,
                metadata={"layer": entry.layer.value},
            )
        ]
        if entry.project_key:
            entities.append(
                GraphEntity(
                    entity_key=f"project:{entry.project_key}",
                    entity_type="project",
                    label=entry.project_key,
                    agent_id=self._agent_id,
                )
            )
            relations.append(
                GraphRelation(
                    relation_key=f"observed_in:{entry_key}:project:{entry.project_key}",
                    relation_type="observed_in",
                    source_entity_key=entry_key,
                    target_entity_key=f"project:{entry.project_key}",
                    agent_id=self._agent_id,
                )
            )
        if entry.environment:
            entities.append(
                GraphEntity(
                    entity_key=f"environment:{entry.environment}",
                    entity_type="environment",
                    label=entry.environment,
                    agent_id=self._agent_id,
                )
            )
            relations.append(
                GraphRelation(
                    relation_key=f"requires:{entry_key}:environment:{entry.environment}",
                    relation_type="requires",
                    source_entity_key=entry_key,
                    target_entity_key=f"environment:{entry.environment}",
                    agent_id=self._agent_id,
                )
            )
        if entry.team:
            entities.append(
                GraphEntity(
                    entity_key=f"team:{entry.team}",
                    entity_type="team",
                    label=entry.team,
                    agent_id=self._agent_id,
                )
            )
            relations.append(
                GraphRelation(
                    relation_key=f"supports:{entry_key}:team:{entry.team}",
                    relation_type="supports",
                    source_entity_key=entry_key,
                    target_entity_key=f"team:{entry.team}",
                    agent_id=self._agent_id,
                )
            )
        for tag in entry.tags:
            entities.append(
                GraphEntity(
                    entity_key=f"tag:{tag}",
                    entity_type="tag",
                    label=tag,
                    agent_id=self._agent_id,
                )
            )
            relations.append(
                GraphRelation(
                    relation_key=f"supports:{entry_key}:tag:{tag}",
                    relation_type="supports",
                    source_entity_key=entry_key,
                    target_entity_key=f"tag:{tag}",
                    agent_id=self._agent_id,
                )
            )
        related_entities = self._extract_related_entities(entry)
        for entity in related_entities:
            entities.append(entity)
            relations.append(
                GraphRelation(
                    relation_key=f"mentions:{entry_key}:{entity.entity_key}",
                    relation_type="mentions",
                    source_entity_key=entry_key,
                    target_entity_key=entity.entity_key,
                    agent_id=self._agent_id,
                )
            )
        return _MaterializedEntry(fingerprint=fingerprint, entities=entities, relations=relations)

    def _extract_related_entities(self, entry: KnowledgeEntry) -> list[GraphEntity]:
        entities: dict[str, GraphEntity] = {}
        search_text = "\n".join(
            part for part in [entry.title, entry.content, entry.source_label, entry.source_path] if part
        )
        for issue_key in _ISSUE_KEY_RE.findall(search_text)[:5]:
            entities.setdefault(
                f"issue:{issue_key}",
                GraphEntity(
                    entity_key=f"issue:{issue_key}",
                    entity_type="issue",
                    label=issue_key,
                    agent_id=self._agent_id,
                    source_kind=entry.source_type,
                ),
            )
        for match in _PATH_RE.findall(search_text)[:5]:
            normalized_path = self._normalize_path_candidate(match)
            if not normalized_path:
                continue
            entities.setdefault(
                f"path:{normalized_path}",
                GraphEntity(
                    entity_key=f"path:{normalized_path}",
                    entity_type="file_path",
                    label=normalized_path,
                    agent_id=self._agent_id,
                    source_kind=entry.source_type,
                ),
            )
        for symbol in _SYMBOL_RE.findall(search_text)[:5]:
            entities.setdefault(
                f"symbol:{symbol}",
                GraphEntity(
                    entity_key=f"symbol:{symbol}",
                    entity_type="code_symbol",
                    label=symbol,
                    agent_id=self._agent_id,
                    source_kind=entry.source_type,
                ),
            )
        for error_signature in _ERROR_RE.findall(search_text)[:5]:
            entities.setdefault(
                f"error_signature:{error_signature}",
                GraphEntity(
                    entity_key=f"error_signature:{error_signature}",
                    entity_type="error_signature",
                    label=error_signature,
                    agent_id=self._agent_id,
                    source_kind=entry.source_type,
                ),
            )
        return list(entities.values())

    def _normalize_path_candidate(self, value: str) -> str:
        normalized = str(value or "").strip().strip(_PATH_SUFFIX_STRIP)
        if not normalized:
            return ""
        parts = [part for part in normalized.split("/") if part and part != "."]
        if not parts:
            return ""
        for anchor in _PATH_ANCHORS:
            if anchor in parts:
                return "/".join(parts[parts.index(anchor) :])
        if len(parts) >= 2:
            return "/".join(parts[-2:])
        return parts[0]
