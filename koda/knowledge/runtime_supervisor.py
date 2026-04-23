"""Long-lived supervisor for the knowledge v2 primary backend and ingest worker."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from koda.config import AGENT_ID
from koda.knowledge.config import KNOWLEDGE_V2_INGEST_BATCH_LIMIT, KNOWLEDGE_V2_INGEST_WORKER_ENABLED
from koda.knowledge.ingest_worker import KnowledgeIngestWorker
from koda.knowledge.repository import KnowledgeRepository
from koda.knowledge.storage_v2 import KnowledgeStorageV2
from koda.logging_config import get_logger

log = get_logger(__name__)

_SUPERVISORS: dict[str, KnowledgeRuntimeSupervisor] = {}


@dataclass(slots=True)
class KnowledgeRuntimeSupervisor:
    """Supervise the primary knowledge backend and the ingest worker."""

    agent_id: str | None = None
    storage: KnowledgeStorageV2 | None = None
    _stop_event: asyncio.Event | None = field(default=None, init=False)
    _worker_task: asyncio.Task[None] | None = field(default=None, init=False)
    _started: bool = field(default=False, init=False)
    _last_worker_result: dict[str, Any] | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if self.storage is None:
            self.storage = KnowledgeStorageV2(KnowledgeRepository(self.agent_id), self.agent_id)

    async def start(self) -> bool:
        if self._started:
            return True
        if self.storage is None:
            return False
        try:
            if self.storage.external_read_enabled():
                primary_started = await self.storage.start_primary_backend()
                if not primary_started:
                    log.error("knowledge_runtime_supervisor_primary_backend_unavailable")
                    return False
            self._started = True
            if (
                KNOWLEDGE_V2_INGEST_WORKER_ENABLED
                and self.storage.external_read_enabled()
                and self._worker_task is None
                and getattr(self.storage, "_postgres", None) is not None
            ):
                self._stop_event = asyncio.Event()
                self._worker_task = asyncio.create_task(self._run_worker_loop())
            return True
        except Exception:
            log.exception("knowledge_runtime_supervisor_start_failed")
            return False

    async def close(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        worker_task = self._worker_task
        self._worker_task = None
        if worker_task is not None:
            worker_task.cancel()
            with suppress(asyncio.CancelledError):
                await worker_task
        if self.storage is not None:
            await self.storage.close_primary_backend()
        self._started = False

    async def health(self) -> dict[str, Any]:
        if self.storage is None:
            return {"enabled": False, "ready": False, "started": False}
        payload = await self.storage.primary_health_summary()
        payload["started"] = self._started
        payload["worker"] = {
            "enabled": KNOWLEDGE_V2_INGEST_WORKER_ENABLED,
            "running": bool(self._worker_task and not self._worker_task.done()),
            "last_result": dict(self._last_worker_result or {}),
        }
        object_store_ready = not payload.get("object_store", {}).get("enabled") or bool(
            payload.get("object_store", {}).get("ready")
        )
        queue_ready = not payload.get("ingest_worker", {}).get("enabled") or bool(
            payload.get("ingest_worker", {}).get("queue", {}).get("ready")
        )
        worker_result = payload["worker"]["last_result"]
        worker_healthy = int(worker_result.get("failed", 0) or 0) == 0
        payload["ready"] = (
            bool(payload.get("primary_backend", {}).get("ready"))
            and object_store_ready
            and queue_ready
            and (
                not KNOWLEDGE_V2_INGEST_WORKER_ENABLED
                or not self.storage.external_read_enabled()
                or (payload["worker"]["running"] and worker_healthy)
            )
        )
        return payload

    async def _run_worker_loop(self) -> None:
        assert self.storage is not None
        stop_event = self._stop_event or asyncio.Event()
        worker = KnowledgeIngestWorker(
            backend=self.storage._postgres,  # type: ignore[attr-defined]
            worker_id=f"supervisor:{(self.agent_id or AGENT_ID or 'default').upper()}",
        )
        while not stop_event.is_set():
            try:
                self._last_worker_result = await worker.run_once(limit=KNOWLEDGE_V2_INGEST_BATCH_LIMIT)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("knowledge_runtime_supervisor_worker_loop_failed")
                self._last_worker_result = {"leased": 0, "completed": 0, "failed": 1}
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=max(0.5, worker.poll_seconds))
            except TimeoutError:
                continue


def get_knowledge_runtime_supervisor(agent_id: str | None = None) -> KnowledgeRuntimeSupervisor:
    normalized = (agent_id or AGENT_ID or "default").upper()
    supervisor = _SUPERVISORS.get(normalized)
    if supervisor is None:
        supervisor = KnowledgeRuntimeSupervisor(agent_id=normalized)
        _SUPERVISORS[normalized] = supervisor
    return supervisor
