"""Facade over explicit knowledge v2 stores."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from koda.knowledge.config import (
    KNOWLEDGE_EMBEDDING_MODEL,
    KNOWLEDGE_V2_INGEST_WORKER_ENABLED,
    KNOWLEDGE_V2_STORAGE_MODE,
)
from koda.knowledge.repository import KnowledgeRepository
from koda.knowledge.types import (
    AnswerJudgement,
    ArtifactDerivative,
    GroundedAnswer,
    KnowledgeEntry,
    KnowledgeLayer,
    KnowledgeScope,
    RetrievalTrace,
)
from koda.knowledge.v2.artifact_store import ArtifactStore
from koda.knowledge.v2.document_store import KnowledgeDocumentStore
from koda.knowledge.v2.embedding_store import KnowledgeEmbeddingStore
from koda.knowledge.v2.evaluation_store import KnowledgeEvaluationStore
from koda.knowledge.v2.graph_store import KnowledgeGraphStore
from koda.knowledge.v2.trace_store import KnowledgeTraceStore


class KnowledgeStorageV2:
    """High-level storage facade used by knowledge and runtime services."""

    def __init__(
        self,
        repository: KnowledgeRepository,
        agent_id: str | None = None,
        *,
        storage_mode: str | None = None,
        object_store_root: str | None = None,
    ) -> None:
        self._repository = repository
        resolved_storage_mode = storage_mode or KNOWLEDGE_V2_STORAGE_MODE
        if object_store_root:
            self._documents = KnowledgeDocumentStore(
                agent_id=agent_id,
                storage_mode=resolved_storage_mode,
                object_store_root=object_store_root,
            )
            self._embeddings = KnowledgeEmbeddingStore(
                agent_id=agent_id,
                storage_mode=resolved_storage_mode,
                object_store_root=object_store_root,
            )
            self._traces = KnowledgeTraceStore(
                repository,
                agent_id=agent_id,
                storage_mode=resolved_storage_mode,
                object_store_root=object_store_root,
            )
            self._graph = KnowledgeGraphStore(
                repository,
                agent_id=agent_id,
                storage_mode=resolved_storage_mode,
                object_store_root=object_store_root,
            )
            self._artifacts = ArtifactStore(
                agent_id=agent_id,
                storage_mode=resolved_storage_mode,
                object_store_root=object_store_root,
            )
        else:
            self._documents = KnowledgeDocumentStore(
                agent_id=agent_id,
                storage_mode=resolved_storage_mode,
            )
            self._embeddings = KnowledgeEmbeddingStore(
                agent_id=agent_id,
                storage_mode=resolved_storage_mode,
            )
            self._traces = KnowledgeTraceStore(
                repository,
                agent_id=agent_id,
                storage_mode=resolved_storage_mode,
            )
            self._graph = KnowledgeGraphStore(
                repository,
                agent_id=agent_id,
                storage_mode=resolved_storage_mode,
            )
            self._artifacts = ArtifactStore(
                agent_id=agent_id,
                storage_mode=resolved_storage_mode,
            )
        self._postgres = self._documents._postgres
        self._embeddings._postgres = self._postgres
        self._traces._postgres = self._postgres
        self._graph._postgres = self._postgres
        self._artifacts._postgres = self._postgres
        self._evaluations = KnowledgeEvaluationStore(repository)

    @property
    def storage_mode(self) -> str:
        return self._traces.storage_mode.value

    def primary_read_enabled(self) -> bool:
        return self._traces.primary_read_enabled()

    def external_read_enabled(self) -> bool:
        return self._traces.external_read_enabled()

    def _require_primary_backend(self) -> None:
        if self.primary_read_enabled() and not self._postgres.enabled:
            raise RuntimeError("knowledge_primary_backend_unavailable")

    def persist_entries(self, *, entries: list[KnowledgeEntry], embeddings: list[list[float]]) -> None:
        if not entries:
            return
        self._documents.persist_entries(entries)
        if embeddings:
            self._embeddings.persist_embeddings(entries, embeddings)

    def persist_retrieval_bundle(self, *, task_id: int | None, payload: dict[str, Any]) -> None:
        self._traces.persist_retrieval_bundle(task_id=task_id, payload=payload)
        self._graph.persist_projection(payload)

    def persist_retrieval_trace(self, *, trace: RetrievalTrace, sampled: bool) -> int | None:
        return self._traces.persist_retrieval_trace(trace=trace, sampled=sampled)

    def persist_retrieval_trace_deferred(self, *, trace: RetrievalTrace, sampled: bool) -> int | None:
        if not sampled:
            return None
        if not self.primary_read_enabled():
            return self.persist_retrieval_trace(trace=trace, sampled=sampled)
        self._require_primary_backend()
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            raise RuntimeError("knowledge_primary_async_context_required") from None
        self._traces.schedule(self._postgres.persist_retrieval_trace(trace=trace))
        return None

    def persist_answer_trace(
        self,
        *,
        task_id: int | None,
        grounded_answer: GroundedAnswer,
        judgement: AnswerJudgement,
        authoritative_sources: list[dict[str, Any]] | None = None,
        supporting_sources: list[dict[str, Any]] | None = None,
        uncertainty: dict[str, Any] | None = None,
    ) -> int | None:
        payload = {
            "task_id": task_id,
            "grounded_answer": grounded_answer.to_dict(),
            "judge_result": judgement.to_dict(),
            "authoritative_sources": authoritative_sources or [],
            "supporting_sources": supporting_sources or [],
            "uncertainty": uncertainty
            or {
                "notes": list(grounded_answer.uncertainty_notes),
                "level": str(grounded_answer.answer_plan.get("uncertainty_level") or ""),
            },
        }
        return self._traces.persist_answer_trace(task_id=task_id, payload=payload)

    def persist_answer_trace_deferred(
        self,
        *,
        task_id: int | None,
        grounded_answer: GroundedAnswer,
        judgement: AnswerJudgement,
        authoritative_sources: list[dict[str, Any]] | None = None,
        supporting_sources: list[dict[str, Any]] | None = None,
        uncertainty: dict[str, Any] | None = None,
    ) -> int | None:
        if not self.primary_read_enabled():
            return self.persist_answer_trace(
                task_id=task_id,
                grounded_answer=grounded_answer,
                judgement=judgement,
                authoritative_sources=authoritative_sources,
                supporting_sources=supporting_sources,
                uncertainty=uncertainty,
            )
        self._require_primary_backend()
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            raise RuntimeError("knowledge_primary_async_context_required") from None
        payload = {
            "task_id": task_id,
            "grounded_answer": grounded_answer.to_dict(),
            "judge_result": judgement.to_dict(),
            "authoritative_sources": authoritative_sources or [],
            "supporting_sources": supporting_sources or [],
            "uncertainty": uncertainty
            or {
                "notes": list(grounded_answer.uncertainty_notes),
                "level": str(grounded_answer.answer_plan.get("uncertainty_level") or ""),
            },
        }
        scope = str(task_id if task_id is not None else "global")
        object_key = self._traces.build_object_key("answer_traces", scope=scope)
        self._traces.schedule(
            self._postgres.persist_answer_trace(
                task_id=task_id,
                payload=payload,
                object_key=object_key,
            )
        )
        return None

    def persist_artifact_derivatives(self, *, task_id: int | None, derivatives: list[ArtifactDerivative]) -> None:
        self._artifacts.persist_derivatives(task_id=task_id, derivatives=derivatives)

    def list_answer_traces(self, *, task_id: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
        return self._traces.list_answer_traces(task_id=task_id, limit=limit)

    def get_answer_trace(self, answer_trace_id: int) -> dict[str, Any] | None:
        return self._traces.get_answer_trace(answer_trace_id)

    def get_latest_answer_trace(self, task_id: int) -> dict[str, Any] | None:
        return self._traces.get_latest_answer_trace(task_id)

    def list_evaluation_cases(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return self._evaluations.list_cases(limit=limit)

    def list_evaluation_runs(
        self,
        *,
        case_key: str | None = None,
        strategy: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self._evaluations.list_runs(case_key=case_key, strategy=strategy, limit=limit)

    def embedding_model(self) -> str:
        return KNOWLEDGE_EMBEDDING_MODEL

    async def ensure_primary_ready(self) -> bool:
        return await self._postgres.ensure_ready()

    async def start_primary_backend(self) -> bool:
        return await self._documents.backend_lifecycle.start()

    async def close_primary_backend(self) -> None:
        await self._documents.backend_lifecycle.close()

    async def primary_backend_health(self) -> dict[str, Any]:
        return await self._documents.backend_lifecycle.health()

    async def ingest_queue_health(self) -> dict[str, Any]:
        if not self.external_read_enabled() or not self._postgres.enabled:
            return {"enabled": False, "ready": False}
        return await self._postgres.ingest_queue_health()

    def object_store_health(self) -> dict[str, Any]:
        return self._documents.object_store_health()

    async def primary_health_summary(self) -> dict[str, Any]:
        primary_backend = (
            await self.primary_backend_health()
            if self.external_read_enabled()
            else {"enabled": False, "ready": False, "pool_active": False}
        )
        object_store = self.object_store_health()
        ingest_queue = (
            await self.ingest_queue_health() if self.external_read_enabled() else {"enabled": False, "ready": False}
        )
        object_store_ready = not object_store.get("enabled") or bool(object_store.get("ready"))
        return {
            "storage_mode": self.storage_mode,
            "primary_read_enabled": self.primary_read_enabled(),
            "external_read_enabled": self.external_read_enabled(),
            "primary_backend": primary_backend,
            "object_store": object_store,
            "ingest_worker": {
                "enabled": KNOWLEDGE_V2_INGEST_WORKER_ENABLED,
                "queue": ingest_queue,
                "ready": bool(primary_backend.get("ready"))
                and object_store_ready
                and (not KNOWLEDGE_V2_INGEST_WORKER_ENABLED or bool(ingest_queue.get("ready"))),
            },
        }

    async def list_artifact_evidence_rows_async(
        self,
        *,
        task_id: int | None,
        project_key: str,
        workspace_fingerprint: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self._require_primary_backend()
        if self.primary_read_enabled() and self._postgres.enabled:
            return await self._artifacts.list_derivative_rows_async(
                task_id=task_id,
                project_key=project_key,
                workspace_fingerprint=workspace_fingerprint,
                limit=limit,
            )
        return self._repository.list_artifact_evidence(
            task_id=task_id,
            project_key=project_key,
            workspace_fingerprint=workspace_fingerprint,
            limit=limit,
        )

    async def get_latest_answer_trace_async(self, task_id: int) -> dict[str, Any] | None:
        return await self._traces.get_latest_answer_trace_async(task_id)

    async def list_answer_traces_async(self, *, task_id: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
        return await self._traces.list_answer_traces_async(task_id=task_id, limit=limit)

    async def get_answer_trace_async(self, answer_trace_id: int) -> dict[str, Any] | None:
        return await self._traces.get_answer_trace_async(answer_trace_id)

    async def list_retrieval_traces_async(
        self,
        *,
        task_id: int | None = None,
        strategy: str | None = None,
        experiment_key: str | None = None,
        trace_role: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return await self._traces.list_retrieval_traces_async(
            task_id=task_id,
            strategy=strategy,
            experiment_key=experiment_key,
            trace_role=trace_role,
            limit=limit,
        )

    async def get_retrieval_trace_async(self, trace_id: int) -> dict[str, Any] | None:
        return await self._traces.get_retrieval_trace_async(trace_id)

    def enqueue_ingest_job(
        self,
        *,
        job_key: str,
        task_id: int | None,
        artifact_id: str,
        payload: dict[str, Any],
        source_path: str = "",
        source_url: str = "",
        priority: int = 50,
    ) -> None:
        self._artifacts.enqueue_ingest_job(
            job_key=job_key,
            task_id=task_id,
            artifact_id=artifact_id,
            payload=payload,
            source_path=source_path,
            source_url=source_url,
            priority=priority,
        )

    def _row_to_entry(self, row: dict[str, Any]) -> KnowledgeEntry:
        layer_value = str(row.get("layer") or KnowledgeLayer.WORKSPACE_DOC.value)
        scope_value = str(row.get("scope") or KnowledgeScope.REPO_FACT.value)
        try:
            layer = KnowledgeLayer(layer_value)
        except ValueError:
            layer = KnowledgeLayer.WORKSPACE_DOC
        try:
            scope = KnowledgeScope(scope_value)
        except ValueError:
            scope = KnowledgeScope.REPO_FACT
        updated_at = row.get("updated_at")
        if isinstance(updated_at, datetime):
            timestamp = updated_at.astimezone(UTC).replace(tzinfo=None) if updated_at.tzinfo else updated_at
        else:
            timestamp = datetime.now()
        return KnowledgeEntry(
            id=str(row.get("chunk_key") or row.get("entry_id") or ""),
            title=str(row.get("title") or ""),
            content=str(row.get("content") or ""),
            layer=layer,
            scope=scope,
            source_label=str(row.get("source_label") or ""),
            source_path=str(row.get("source_path") or ""),
            updated_at=timestamp,
            owner=str(row.get("owner") or ""),
            tags=list(row.get("tags_json") or []),
            freshness_days=int(row.get("freshness_days") or 90),
            project_key=str(row.get("project_key") or ""),
            environment=str(row.get("environment") or ""),
            team=str(row.get("team") or ""),
            source_type=str(row.get("source_type") or "document"),
            operable=bool(row.get("operable") if row.get("operable") is not None else True),
        )

    def _freshness_label(self, updated_at: datetime, freshness_days: int) -> str:
        age_days = max(0, (datetime.now() - updated_at).days)
        if age_days <= freshness_days:
            return "fresh"
        if age_days <= freshness_days * 3:
            return "aging"
        return "stale"
