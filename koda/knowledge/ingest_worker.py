"""Asynchronous worker for Postgres-backed knowledge ingest jobs."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from typing import Any

from koda.knowledge.config import (
    KNOWLEDGE_V2_INGEST_BATCH_LIMIT,
    KNOWLEDGE_V2_INGEST_LEASE_SECONDS,
    KNOWLEDGE_V2_INGEST_POLL_SECONDS,
    KNOWLEDGE_V2_INGEST_WORKER_ENABLED,
)
from koda.knowledge.telemetry import knowledge_span
from koda.knowledge.types import ArtifactDerivative, EvidenceModality
from koda.knowledge.v2.postgres_backend import KnowledgeV2PostgresBackend
from koda.logging_config import get_logger

log = get_logger(__name__)

_BACKGROUND_RUNS: dict[str, asyncio.Task[None]] = {}


def _worker_key(backend: KnowledgeV2PostgresBackend) -> str:
    return f"{backend.agent_id}:{backend.schema}"


@dataclass(slots=True)
class KnowledgeIngestWorker:
    """Consume ready ingest jobs and persist retrieval-ready derivatives."""

    backend: KnowledgeV2PostgresBackend
    worker_id: str = "inline"
    poll_seconds: float = KNOWLEDGE_V2_INGEST_POLL_SECONDS
    lease_seconds: int = KNOWLEDGE_V2_INGEST_LEASE_SECONDS

    async def run_once(self, *, limit: int = KNOWLEDGE_V2_INGEST_BATCH_LIMIT) -> dict[str, int]:
        if not KNOWLEDGE_V2_INGEST_WORKER_ENABLED:
            return {"leased": 0, "completed": 0, "failed": 0}
        leased = await self.backend.lease_ingest_jobs(
            worker_id=self.worker_id,
            limit=max(1, limit),
            lease_seconds=max(1, self.lease_seconds),
        )
        completed = 0
        failed = 0
        for job in leased:
            try:
                result = await self._process_job(job)
                await self.backend.complete_ingest_job(job_id=int(job["id"]), result=result)
                completed += 1
            except Exception as exc:
                failed += 1
                log.exception("knowledge_ingest_job_failed", job_id=job.get("id"), job_key=job.get("job_key"))
                await self.backend.fail_ingest_job(
                    job_id=int(job["id"]),
                    error_message=str(exc),
                    retry_delay_seconds=max(5, self.lease_seconds // 2),
                )
        return {"leased": len(leased), "completed": completed, "failed": failed}

    async def run_forever(
        self,
        *,
        stop_event: asyncio.Event | None = None,
        limit: int = KNOWLEDGE_V2_INGEST_BATCH_LIMIT,
    ) -> None:
        while True:
            if stop_event is not None and stop_event.is_set():
                return
            result = await self.run_once(limit=limit)
            sleep_for = 0.0 if result["leased"] else max(0.25, self.poll_seconds)
            if stop_event is not None:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=sleep_for)
                    return
                except TimeoutError:
                    continue
            await asyncio.sleep(sleep_for)

    async def _process_job(self, job: dict[str, Any]) -> dict[str, Any]:
        payload = dict(job.get("payload_json") or {})
        job_type = str(job.get("job_type") or payload.get("job_type") or "artifact_derivative")
        with knowledge_span(
            "ingest_job",
            job_type=job_type,
            task_id=job.get("task_id"),
            artifact_id=job.get("artifact_id"),
        ):
            if job_type in {"artifact_derivative", "artifact_derivative_batch"}:
                derivatives = self._derivatives_from_payload(payload)
                if derivatives:
                    await self.backend.upsert_artifact_derivatives(
                        task_id=int(job["task_id"]) if job.get("task_id") is not None else None,
                        derivatives=derivatives,
                        object_key=str(payload.get("object_key") or self._default_object_key(job)),
                        enqueue_jobs=False,
                    )
                return {
                    "job_type": job_type,
                    "processed_derivatives": len(derivatives),
                }
            return {"job_type": job_type, "skipped": 1}

    def _derivatives_from_payload(self, payload: dict[str, Any]) -> list[ArtifactDerivative]:
        items = list(payload.get("items") or [])
        derivatives: list[ArtifactDerivative] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            modality_value = str(item.get("modality") or EvidenceModality.TEXT.value)
            try:
                modality = EvidenceModality(modality_value)
            except ValueError:
                modality = EvidenceModality.TEXT
            derivatives.append(
                ArtifactDerivative(
                    derivative_key=str(item.get("derivative_key") or ""),
                    artifact_id=str(item.get("artifact_id") or ""),
                    modality=modality,
                    label=str(item.get("label") or ""),
                    extracted_text=str(item.get("extracted_text") or ""),
                    confidence=float(item.get("confidence") or 0.0),
                    trust_level=str(item.get("trust_level") or "untrusted"),
                    source_path=str(item.get("source_path") or ""),
                    source_url=str(item.get("source_url") or ""),
                    time_span=str(item.get("time_span") or ""),
                    frame_ref=str(item.get("frame_ref") or ""),
                    provenance=dict(item.get("provenance") or {}),
                )
            )
        return [item for item in derivatives if item.derivative_key]

    def _default_object_key(self, job: dict[str, Any]) -> str:
        artifact_id = str(job.get("artifact_id") or "artifact")
        task_id = str(job.get("task_id") or "global")
        suffix = hashlib.sha256(f"{self.backend.agent_id}:{artifact_id}:{task_id}".encode(), usedforsecurity=False)
        return f"{self.backend.agent_id}/artifact_derivatives/{task_id}-{suffix.hexdigest()[:12]}.json"


def schedule_ingest_worker_drain(backend: KnowledgeV2PostgresBackend) -> None:
    """Best-effort in-process drain for queued ingest jobs."""
    if not KNOWLEDGE_V2_INGEST_WORKER_ENABLED:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    key = _worker_key(backend)
    current = _BACKGROUND_RUNS.get(key)
    if current is not None and not current.done():
        return

    async def _drain() -> None:
        worker = KnowledgeIngestWorker(backend=backend, worker_id="inline-drain")
        try:
            await worker.run_once()
        finally:
            _BACKGROUND_RUNS.pop(key, None)

    task = loop.create_task(_drain())
    _BACKGROUND_RUNS[key] = task
