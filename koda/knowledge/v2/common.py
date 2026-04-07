"""Shared helpers for knowledge v2 stores."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from koda.config import OBJECT_STORAGE_REQUIRED
from koda.knowledge.config import (
    KNOWLEDGE_V2_EMBEDDING_DIMENSION,
    KNOWLEDGE_V2_OBJECT_STORE_ROOT,
    KNOWLEDGE_V2_POSTGRES_DSN,
    KNOWLEDGE_V2_POSTGRES_SCHEMA,
    KNOWLEDGE_V2_S3_ACCESS_KEY_ID,
    KNOWLEDGE_V2_S3_BUCKET,
    KNOWLEDGE_V2_S3_ENDPOINT_URL,
    KNOWLEDGE_V2_S3_PREFIX,
    KNOWLEDGE_V2_S3_REGION,
    KNOWLEDGE_V2_S3_SECRET_ACCESS_KEY,
)
from koda.knowledge.types import KnowledgeV2StorageMode
from koda.knowledge.v2.postgres_backend import KnowledgeV2PostgresBackend
from koda.logging_config import get_logger

log = get_logger(__name__)
_SHARED_POSTGRES_BACKENDS: dict[tuple[str, str, str, int], KnowledgeV2PostgresBackend] = {}


class KnowledgeBackendLifecycle:
    """Lifecycle wrapper around the primary Postgres backend."""

    def __init__(self, backend: KnowledgeV2PostgresBackend) -> None:
        self._backend = backend

    async def bootstrap(self) -> bool:
        return await self._backend.bootstrap()

    async def start(self) -> bool:
        return await self._backend.start()

    async def close(self) -> None:
        await self._backend.close()

    async def health(self) -> dict[str, Any]:
        return await self._backend.health()


def coerce_storage_mode(value: str | KnowledgeV2StorageMode | None) -> KnowledgeV2StorageMode:
    if isinstance(value, KnowledgeV2StorageMode):
        return value
    normalized = str(value or "primary").strip().lower()
    if normalized in {"", KnowledgeV2StorageMode.PRIMARY.value}:
        return KnowledgeV2StorageMode.PRIMARY
    if normalized == KnowledgeV2StorageMode.OFF.value:
        return KnowledgeV2StorageMode.OFF
    raise ValueError(f"unsupported knowledge_v2_storage_mode={normalized!r}")


def get_shared_postgres_backend(
    *,
    agent_id: str | None,
    dsn: str,
    schema: str,
    embedding_dimension: int,
) -> KnowledgeV2PostgresBackend:
    """Reuse one primary backend per agent/schema tuple inside this process."""
    key = (
        (agent_id or "default").upper(),
        dsn.strip(),
        (schema or "knowledge_v2").strip() or "knowledge_v2",
        int(embedding_dimension),
    )
    backend = _SHARED_POSTGRES_BACKENDS.get(key)
    if backend is None:
        backend = KnowledgeV2PostgresBackend(
            agent_id=agent_id,
            dsn=dsn,
            schema=schema,
            embedding_dimension=embedding_dimension,
        )
        _SHARED_POSTGRES_BACKENDS[key] = backend
    return backend


def clear_shared_postgres_backends() -> None:
    """Testing helper for resetting the process-local backend registry."""
    _SHARED_POSTGRES_BACKENDS.clear()


class V2StoreSupport:
    """Common support for local mirrors and background best-effort writes."""

    def __init__(
        self,
        *,
        agent_id: str | None,
        storage_mode: str | KnowledgeV2StorageMode,
        object_store_root: str = KNOWLEDGE_V2_OBJECT_STORE_ROOT,
    ) -> None:
        self._agent_id = agent_id or "default"
        self._storage_mode = coerce_storage_mode(storage_mode)
        self._root = Path(object_store_root)
        if self.local_write_enabled():
            self._root.mkdir(parents=True, exist_ok=True)
        self._background_tasks: set[asyncio.Task[None]] = set()
        self._postgres = get_shared_postgres_backend(
            agent_id=self._agent_id,
            dsn=KNOWLEDGE_V2_POSTGRES_DSN,
            schema=KNOWLEDGE_V2_POSTGRES_SCHEMA,
            embedding_dimension=KNOWLEDGE_V2_EMBEDDING_DIMENSION,
        )
        self._lifecycle = KnowledgeBackendLifecycle(self._postgres)

    @property
    def storage_mode(self) -> KnowledgeV2StorageMode:
        return self._storage_mode

    def local_write_enabled(self) -> bool:
        if self._storage_mode is KnowledgeV2StorageMode.OFF:
            return False
        return self._storage_mode is not KnowledgeV2StorageMode.PRIMARY

    def external_write_enabled(self) -> bool:
        return self._storage_mode is KnowledgeV2StorageMode.PRIMARY

    def primary_read_enabled(self) -> bool:
        return self._storage_mode is KnowledgeV2StorageMode.PRIMARY

    def external_read_enabled(self) -> bool:
        return self._postgres.enabled and self._storage_mode is KnowledgeV2StorageMode.PRIMARY

    def primary_backend_available(self) -> bool:
        return bool(getattr(self._postgres, "enabled", False)) and bool(getattr(self._postgres, "bootstrapped", False))

    def require_primary_backend(self) -> None:
        if self.primary_read_enabled() and not self.primary_backend_available():
            raise RuntimeError("knowledge_primary_backend_unavailable")

    def build_object_key(self, namespace: str, *, scope: str) -> str:
        prefix = KNOWLEDGE_V2_S3_PREFIX.strip().strip("/")
        key = f"{self._agent_id}/{namespace}/{scope}.json"
        return f"{prefix}/{key}" if prefix else key

    @property
    def backend_lifecycle(self) -> KnowledgeBackendLifecycle:
        return self._lifecycle

    def _build_s3_client(self, *, credentials: dict[str, str] | None = None) -> Any:
        """Build a boto3 S3 client using configured or overridden credentials."""
        import boto3  # type: ignore[import-not-found]

        creds = credentials or {}
        client_kwargs: dict[str, str] = {}
        if KNOWLEDGE_V2_S3_ENDPOINT_URL:
            client_kwargs["endpoint_url"] = KNOWLEDGE_V2_S3_ENDPOINT_URL
        if KNOWLEDGE_V2_S3_REGION:
            client_kwargs["region_name"] = KNOWLEDGE_V2_S3_REGION
        key_id = creds.get("aws_access_key_id") or KNOWLEDGE_V2_S3_ACCESS_KEY_ID
        secret_key = creds.get("aws_secret_access_key") or KNOWLEDGE_V2_S3_SECRET_ACCESS_KEY
        if key_id:
            client_kwargs["aws_access_key_id"] = key_id
        if secret_key:
            client_kwargs["aws_secret_access_key"] = secret_key
        return boto3.client("s3", **client_kwargs)

    def object_store_health(self) -> dict[str, Any]:
        local_ready = self._root.exists() and self._root.is_dir()
        s3_enabled = bool(KNOWLEDGE_V2_S3_BUCKET and self.external_write_enabled())
        primary_requires_remote = self._storage_mode is KnowledgeV2StorageMode.PRIMARY and OBJECT_STORAGE_REQUIRED
        storage_enabled = s3_enabled or self.local_write_enabled()
        payload: dict[str, Any] = {
            "enabled": storage_enabled,
            "mode": "s3" if s3_enabled else ("local" if self.local_write_enabled() else "disabled"),
            "local_root": str(self._root) if self.local_write_enabled() else None,
            "local_ready": local_ready if self.local_write_enabled() else None,
            "bucket": KNOWLEDGE_V2_S3_BUCKET or None,
            "prefix": KNOWLEDGE_V2_S3_PREFIX or "",
            "endpoint_url": KNOWLEDGE_V2_S3_ENDPOINT_URL or None,
            "primary_requires_remote": primary_requires_remote,
            "ready": local_ready if self.local_write_enabled() else False,
        }
        if s3_enabled:
            try:
                client = self._build_s3_client()
                client.head_bucket(Bucket=KNOWLEDGE_V2_S3_BUCKET)
                payload["boto3_available"] = True
                payload["ready"] = True
                payload["s3_ready"] = True
            except Exception as exc:
                payload["boto3_available"] = False
                payload["s3_ready"] = False
                payload["ready"] = False
                payload["error"] = str(exc)
        else:
            payload["boto3_available"] = None
            payload["s3_ready"] = None
            if primary_requires_remote:
                payload["ready"] = False
                payload["error"] = "remote object storage required in primary mode"
            elif not storage_enabled:
                payload["ready"] = False
                payload["error"] = "no object storage sink configured"
        return payload

    def write_local_payload(self, namespace: str, *, scope: str, payload: dict[str, Any]) -> str:
        object_key = self.build_object_key(namespace, scope=scope)
        serialized = json.dumps(payload, ensure_ascii=True, default=str, indent=2)
        if self.local_write_enabled():
            namespace_dir = self._root / self._agent_id / namespace
            namespace_dir.mkdir(parents=True, exist_ok=True)
            path = namespace_dir / f"{scope}.json"
            path.write_text(serialized, encoding="utf-8")
            if KNOWLEDGE_V2_S3_BUCKET and self.external_write_enabled():
                self.schedule(
                    self._persist_s3_copy(
                        path,
                        object_key=object_key,
                    )
                )
        elif KNOWLEDGE_V2_S3_BUCKET and self.external_write_enabled():
            self.schedule(self._persist_s3_payload(serialized.encode("utf-8"), object_key=object_key))
        return object_key

    def schedule(self, task_coro: Any) -> None:
        try:
            task = asyncio.create_task(task_coro)
        except RuntimeError:
            close = getattr(task_coro, "close", None)
            if callable(close):
                close()
            return
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _persist_s3_copy(self, path: Path, *, object_key: str) -> None:
        try:
            client = self._build_s3_client()
            client.upload_file(str(path), KNOWLEDGE_V2_S3_BUCKET, object_key)
        except Exception:
            log.warning("knowledge_v2_s3_copy_unavailable", object_key=object_key)

    async def _persist_s3_payload(self, payload: bytes, *, object_key: str) -> None:
        try:
            client = self._build_s3_client()
            client.put_object(
                Bucket=KNOWLEDGE_V2_S3_BUCKET,
                Key=object_key,
                Body=payload,
                ContentType="application/json",
            )
        except Exception:
            log.warning("knowledge_v2_s3_payload_unavailable", object_key=object_key)
