"""Shared helpers for the knowledge v2 storage layer."""

from __future__ import annotations

import os
from typing import Any

from koda.config import OBJECT_STORAGE_REQUIRED
from koda.knowledge.config import (
    KNOWLEDGE_V2_S3_ACCESS_KEY_ID,
    KNOWLEDGE_V2_S3_BUCKET,
    KNOWLEDGE_V2_S3_ENDPOINT_URL,
    KNOWLEDGE_V2_S3_PREFIX,
    KNOWLEDGE_V2_S3_REGION,
    KNOWLEDGE_V2_S3_SECRET_ACCESS_KEY,
)
from koda.knowledge.types import KnowledgeV2StorageMode
from koda.knowledge.v2.postgres_backend import KnowledgeV2PostgresBackend

_SHARED_POSTGRES_BACKENDS: dict[tuple[str, str, str, int], KnowledgeV2PostgresBackend] = {}
_SHARED_BACKENDS_OWNER_PID: int | None = None


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
    """Reuse one primary backend per agent/schema tuple inside this process.

    PID-awareness: if the cache was populated in a parent process (e.g. via
    any future ``os.fork``-based spawn), the inherited asyncpg pool points at
    the parent's event loop and its sockets — using it from the child would
    corrupt state. Drop the cache when we detect we've moved processes.
    ``subprocess_exec`` re-imports this module in a fresh interpreter, so
    this branch is primarily defensive for future callers.
    """
    global _SHARED_BACKENDS_OWNER_PID

    current_pid = os.getpid()
    if _SHARED_BACKENDS_OWNER_PID is None:
        _SHARED_BACKENDS_OWNER_PID = current_pid
    elif current_pid != _SHARED_BACKENDS_OWNER_PID:
        _SHARED_POSTGRES_BACKENDS.clear()
        _SHARED_BACKENDS_OWNER_PID = current_pid

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


def build_s3_client(*, credentials: dict[str, str] | None = None) -> Any:
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


def object_store_health(storage_mode: str | KnowledgeV2StorageMode | None) -> dict[str, Any]:
    """Report whether the knowledge object store is configured and reachable.

    Only an S3 bucket counts as a sink: knowledge payloads are never written
    to the local filesystem, so the ``local_*`` fields are always ``None``.
    """
    primary = coerce_storage_mode(storage_mode) is KnowledgeV2StorageMode.PRIMARY
    s3_enabled = bool(KNOWLEDGE_V2_S3_BUCKET and primary)
    primary_requires_remote = primary and OBJECT_STORAGE_REQUIRED
    payload: dict[str, Any] = {
        "enabled": s3_enabled,
        "mode": "s3" if s3_enabled else "disabled",
        "local_root": None,
        "local_ready": None,
        "bucket": KNOWLEDGE_V2_S3_BUCKET or None,
        "prefix": KNOWLEDGE_V2_S3_PREFIX or "",
        "endpoint_url": KNOWLEDGE_V2_S3_ENDPOINT_URL or None,
        "primary_requires_remote": primary_requires_remote,
        "ready": False,
    }
    if s3_enabled:
        try:
            client = build_s3_client()
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
            payload["error"] = "remote object storage required in primary mode"
        else:
            payload["error"] = "no object storage sink configured"
    return payload
