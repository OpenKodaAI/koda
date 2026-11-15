"""Storage facade over the knowledge v2 primary backend."""

from __future__ import annotations

import asyncio
from typing import Any

from koda.knowledge.config import (
    KNOWLEDGE_V2_EMBEDDING_DIMENSION,
    KNOWLEDGE_V2_INGEST_WORKER_ENABLED,
    KNOWLEDGE_V2_POSTGRES_DSN,
    KNOWLEDGE_V2_POSTGRES_SCHEMA,
    KNOWLEDGE_V2_S3_PREFIX,
    KNOWLEDGE_V2_STORAGE_MODE,
)
from koda.knowledge.repository import KnowledgeRepository
from koda.knowledge.types import (
    AnswerJudgement,
    GroundedAnswer,
    KnowledgeV2StorageMode,
    RetrievalTrace,
)
from koda.knowledge.v2.common import coerce_storage_mode, get_shared_postgres_backend, object_store_health


class KnowledgeStorageV2:
    """High-level storage facade used by knowledge and runtime services.

    In PRIMARY mode reads and writes go to the shared Postgres backend. In
    OFF mode writes are skipped, artifact-evidence reads return no rows, and
    trace reads fall back to the repository.
    """

    def __init__(
        self,
        repository: KnowledgeRepository,
        agent_id: str | None = None,
        *,
        storage_mode: str | None = None,
    ) -> None:
        self._repository = repository
        self._agent_id = agent_id or "default"
        self._storage_mode = coerce_storage_mode(storage_mode or KNOWLEDGE_V2_STORAGE_MODE)
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._postgres = get_shared_postgres_backend(
            agent_id=self._agent_id,
            dsn=KNOWLEDGE_V2_POSTGRES_DSN,
            schema=KNOWLEDGE_V2_POSTGRES_SCHEMA,
            embedding_dimension=KNOWLEDGE_V2_EMBEDDING_DIMENSION,
        )

    def primary_read_enabled(self) -> bool:
        return self._storage_mode is KnowledgeV2StorageMode.PRIMARY

    def external_read_enabled(self) -> bool:
        return self._postgres.enabled and self.primary_read_enabled()

    def _require_primary_backend(self) -> None:
        """Writes and artifact reads need a configured backend in PRIMARY mode."""
        if self.primary_read_enabled() and not self._postgres.enabled:
            raise RuntimeError("knowledge_primary_backend_unavailable")

    def _require_bootstrapped_primary_backend(self) -> None:
        """Trace reads need a configured and bootstrapped backend in PRIMARY mode."""
        available = bool(getattr(self._postgres, "enabled", False)) and bool(
            getattr(self._postgres, "bootstrapped", False)
        )
        if self.primary_read_enabled() and not available:
            raise RuntimeError("knowledge_primary_backend_unavailable")

    def _schedule(self, task_coro: Any) -> None:
        """Run a backend write as a detached task; nothing awaits its result."""
        try:
            task = asyncio.create_task(task_coro)
        except RuntimeError:
            close = getattr(task_coro, "close", None)
            if callable(close):
                close()
            return
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _require_async_context(self) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            raise RuntimeError("knowledge_primary_async_context_required") from None

    def _object_key(self, namespace: str, *, scope: str) -> str:
        prefix = KNOWLEDGE_V2_S3_PREFIX.strip().strip("/")
        key = f"{self._agent_id}/{namespace}/{scope}.json"
        return f"{prefix}/{key}" if prefix else key

    def persist_retrieval_trace_deferred(self, *, trace: RetrievalTrace, sampled: bool) -> int | None:
        if not sampled or not self.primary_read_enabled():
            return None
        self._require_primary_backend()
        self._require_async_context()
        self._schedule(self._postgres.persist_retrieval_trace(trace=trace))
        return None

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
            return None
        self._require_primary_backend()
        self._require_async_context()
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
        self._schedule(
            self._postgres.persist_answer_trace(
                task_id=task_id,
                payload=payload,
                object_key=self._object_key("answer_traces", scope=scope),
            )
        )
        return None

    async def start_primary_backend(self) -> bool:
        return await self._postgres.start()

    async def close_primary_backend(self) -> None:
        await self._postgres.close()

    async def primary_health_summary(self) -> dict[str, Any]:
        external_read = self.external_read_enabled()
        primary_backend = (
            await self._postgres.health() if external_read else {"enabled": False, "ready": False, "pool_active": False}
        )
        object_store = object_store_health(self._storage_mode)
        ingest_queue = (
            await self._postgres.ingest_queue_health() if external_read else {"enabled": False, "ready": False}
        )
        object_store_ready = not object_store.get("enabled") or bool(object_store.get("ready"))
        return {
            "storage_mode": self._storage_mode.value,
            "primary_read_enabled": self.primary_read_enabled(),
            "external_read_enabled": external_read,
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
        if not self.primary_read_enabled():
            # OFF mode keeps no artifact evidence. Before M4-E1-T6 this read
            # selected from a table no schema creates.
            return []
        return await self._postgres.list_artifact_derivative_rows(
            task_id=task_id,
            project_key=project_key,
            workspace_fingerprint=workspace_fingerprint,
            limit=limit,
        )

    async def get_latest_answer_trace_async(self, task_id: int) -> dict[str, Any] | None:
        self._require_bootstrapped_primary_backend()
        if self.primary_read_enabled():
            return await self._postgres.get_latest_answer_trace(task_id)
        return self._repository.get_latest_answer_trace(task_id)

    async def list_answer_traces_async(self, *, task_id: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
        self._require_bootstrapped_primary_backend()
        if self.primary_read_enabled():
            return await self._postgres.list_answer_traces(task_id=task_id, limit=limit)
        return self._repository.list_answer_traces(task_id=task_id, limit=limit)

    async def get_answer_trace_async(self, answer_trace_id: int) -> dict[str, Any] | None:
        self._require_bootstrapped_primary_backend()
        if self.primary_read_enabled():
            return await self._postgres.get_answer_trace(answer_trace_id)
        return self._repository.get_answer_trace(answer_trace_id)

    async def list_retrieval_traces_async(
        self,
        *,
        task_id: int | None = None,
        strategy: str | None = None,
        experiment_key: str | None = None,
        trace_role: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        self._require_bootstrapped_primary_backend()
        if self.primary_read_enabled():
            return await self._postgres.list_retrieval_traces(
                task_id=task_id,
                strategy=strategy,
                experiment_key=experiment_key,
                trace_role=trace_role,
                limit=limit,
            )
        return self._repository.list_retrieval_traces(
            task_id=task_id,
            strategy=strategy,
            experiment_key=experiment_key,
            trace_role=trace_role,
            limit=limit,
        )

    async def get_retrieval_trace_async(self, trace_id: int) -> dict[str, Any] | None:
        self._require_bootstrapped_primary_backend()
        if self.primary_read_enabled():
            return await self._postgres.get_retrieval_trace(trace_id)
        return self._repository.get_retrieval_trace(trace_id)
