"""Artifact derivative persistence for knowledge v2."""

from __future__ import annotations

from typing import Any

from koda.knowledge.config import KNOWLEDGE_V2_INGEST_WORKER_ENABLED
from koda.knowledge.ingest_worker import schedule_ingest_worker_drain
from koda.knowledge.types import ArtifactDerivative
from koda.knowledge.v2.common import V2StoreSupport
from koda.logging_config import get_logger

log = get_logger(__name__)


class ArtifactStore(V2StoreSupport):
    """Persist derived multimodal artifacts for cutover and audits."""

    def persist_derivatives(self, *, task_id: int | None, derivatives: list[ArtifactDerivative]) -> None:
        if not derivatives:
            return
        scope = str(task_id if task_id is not None else "global")
        object_key = self.build_object_key("artifact_derivatives", scope=scope)
        payload = {
            "task_id": task_id,
            "object_key": object_key,
            "items": [
                {
                    "derivative_key": item.derivative_key,
                    "artifact_id": item.artifact_id,
                    "modality": item.modality.value,
                    "label": item.label,
                    "extracted_text": item.extracted_text,
                    "confidence": item.confidence,
                    "trust_level": item.trust_level,
                    "source_path": item.source_path,
                    "source_url": item.source_url,
                    "time_span": item.time_span,
                    "frame_ref": item.frame_ref,
                    "provenance": dict(item.provenance),
                }
                for item in derivatives
            ],
        }
        if self.local_write_enabled() or (self.external_write_enabled() and self._postgres.enabled):
            object_key = self.write_local_payload("artifact_derivatives", scope=scope, payload=payload)
        if self.external_write_enabled() and self._postgres.enabled:
            if not self._postgres.bootstrapped:
                log.warning(
                    "knowledge_v2_artifact_derivatives_skipped_unbootstrapped_backend",
                    task_id=task_id,
                    scope=scope,
                )
                return
            first = derivatives[0]
            if KNOWLEDGE_V2_INGEST_WORKER_ENABLED:
                self.schedule(
                    self._postgres.enqueue_ingest_job(
                        job_key=f"artifact-batch:{scope}",
                        task_id=task_id,
                        artifact_id=first.artifact_id or scope,
                        job_type="artifact_derivative_batch",
                        payload=payload,
                        source_path=first.source_path,
                        source_url=first.source_url,
                        priority=40,
                    )
                )
                schedule_ingest_worker_drain(self._postgres)
            else:
                self.schedule(
                    self._postgres.upsert_artifact_derivatives(
                        task_id=task_id,
                        derivatives=derivatives,
                        object_key=object_key,
                        enqueue_jobs=False,
                    )
                )

    async def list_derivative_rows_async(
        self,
        *,
        task_id: int | None,
        project_key: str,
        workspace_fingerprint: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if self.primary_read_enabled() and self._postgres.enabled:
            return await self._postgres.list_artifact_derivative_rows(
                task_id=task_id,
                project_key=project_key,
                workspace_fingerprint=workspace_fingerprint,
                limit=limit,
            )
        return []

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
        if not self.external_write_enabled() or not self._postgres.enabled:
            return
        if not self._postgres.bootstrapped:
            log.warning(
                "knowledge_v2_ingest_job_skipped_unbootstrapped_backend",
                task_id=task_id,
                job_key=job_key,
            )
            return
        self.schedule(
            self._postgres.enqueue_ingest_job(
                job_key=job_key,
                task_id=task_id,
                artifact_id=artifact_id,
                payload=payload,
                source_path=source_path,
                source_url=source_url,
                priority=priority,
            )
        )
        schedule_ingest_worker_drain(self._postgres)
