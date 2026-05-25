"""Trace persistence for retrieval and answer pipelines."""

from __future__ import annotations

from typing import Any, cast

from koda.knowledge.repository import KnowledgeRepository
from koda.knowledge.types import RetrievalTrace
from koda.knowledge.v2.common import V2StoreSupport
from koda.state.primary import run_coro_sync


class KnowledgeTraceStore(V2StoreSupport):
    """Persist retrieval bundles and answer traces with local and external mirrors."""

    def __init__(self, repository: KnowledgeRepository, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._repository = repository

    def persist_retrieval_bundle(self, *, task_id: int | None, payload: dict[str, Any]) -> None:
        self.require_primary_backend()
        scope = str(task_id if task_id is not None else "global")
        object_key = self.build_object_key("retrieval_bundles", scope=scope)
        if self.local_write_enabled() or (self.external_write_enabled() and self._postgres.enabled):
            object_key = self.write_local_payload("retrieval_bundles", scope=scope, payload=payload)
        if self.external_write_enabled() and self._postgres.enabled:
            self.schedule(
                self._postgres.persist_retrieval_bundle(
                    task_id=task_id,
                    payload=payload,
                    object_key=object_key,
                )
            )

    def persist_retrieval_trace(self, *, trace: RetrievalTrace, sampled: bool) -> int | None:
        if not sampled:
            return None
        self.require_primary_backend()
        trace_id: int | None = None
        if self.local_write_enabled():
            trace_id = self._repository.persist_retrieval_trace(trace, sampled=sampled)
        if self.external_write_enabled() and self._postgres.enabled:
            if self.primary_read_enabled():
                primary_trace_id = run_coro_sync(self._postgres.persist_retrieval_trace(trace=trace))
                return int(primary_trace_id) if primary_trace_id is not None else trace_id
            self.schedule(self._postgres.persist_retrieval_trace(trace=trace))
        return trace_id

    def persist_answer_trace(self, *, task_id: int | None, payload: dict[str, Any]) -> int | None:
        self.require_primary_backend()
        scope = str(task_id if task_id is not None else "global")
        object_key = self.build_object_key("answer_traces", scope=scope)
        trace_id: int | None = None
        if self.local_write_enabled() or (self.external_write_enabled() and self._postgres.enabled):
            object_key = self.write_local_payload("answer_traces", scope=scope, payload=payload)
        if self.local_write_enabled():
            trace_id = self._repository.persist_answer_trace(
                task_id=task_id,
                grounded_answer=dict(payload.get("grounded_answer") or {}),
                judgement=dict(payload.get("judge_result") or {}),
                authoritative_sources=list(payload.get("authoritative_sources") or []),
                supporting_sources=list(payload.get("supporting_sources") or []),
                uncertainty=dict(payload.get("uncertainty") or {}),
            )
        if self.external_write_enabled() and self._postgres.enabled:
            if self.primary_read_enabled():
                primary_trace_id = run_coro_sync(
                    self._postgres.persist_answer_trace(
                        task_id=task_id,
                        payload=payload,
                        object_key=object_key,
                    )
                )
                return int(primary_trace_id) if primary_trace_id is not None else trace_id
            self.schedule(
                self._postgres.persist_answer_trace(
                    task_id=task_id,
                    payload=payload,
                    object_key=object_key,
                )
            )
        return trace_id

    def list_answer_traces(self, *, task_id: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
        self.require_primary_backend()
        if self.primary_read_enabled():
            return cast(
                list[dict[str, Any]],
                run_coro_sync(self._postgres.list_answer_traces(task_id=task_id, limit=limit)),
            )
        return self._repository.list_answer_traces(task_id=task_id, limit=limit)

    def get_answer_trace(self, answer_trace_id: int) -> dict[str, Any] | None:
        self.require_primary_backend()
        if self.primary_read_enabled():
            return cast(dict[str, Any] | None, run_coro_sync(self._postgres.get_answer_trace(answer_trace_id)))
        return self._repository.get_answer_trace(answer_trace_id)

    def get_latest_answer_trace(self, task_id: int) -> dict[str, Any] | None:
        self.require_primary_backend()
        if self.primary_read_enabled():
            return cast(dict[str, Any] | None, run_coro_sync(self._postgres.get_latest_answer_trace(task_id)))
        return self._repository.get_latest_answer_trace(task_id)

    async def list_answer_traces_async(self, *, task_id: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
        self.require_primary_backend()
        if self.primary_read_enabled():
            return await self._postgres.list_answer_traces(task_id=task_id, limit=limit)
        return self.list_answer_traces(task_id=task_id, limit=limit)

    async def get_answer_trace_async(self, answer_trace_id: int) -> dict[str, Any] | None:
        self.require_primary_backend()
        if self.primary_read_enabled():
            return await self._postgres.get_answer_trace(answer_trace_id)
        return self.get_answer_trace(answer_trace_id)

    async def get_latest_answer_trace_async(self, task_id: int) -> dict[str, Any] | None:
        self.require_primary_backend()
        if self.primary_read_enabled():
            return await self._postgres.get_latest_answer_trace(task_id)
        return self.get_latest_answer_trace(task_id)

    async def list_retrieval_traces_async(
        self,
        *,
        task_id: int | None = None,
        strategy: str | None = None,
        experiment_key: str | None = None,
        trace_role: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        self.require_primary_backend()
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
        self.require_primary_backend()
        if self.primary_read_enabled():
            return await self._postgres.get_retrieval_trace(trace_id)
        return self._repository.get_retrieval_trace(trace_id)
