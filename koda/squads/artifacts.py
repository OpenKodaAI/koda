"""Squad artifact visibility and version checks."""

from __future__ import annotations

import json
import re
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ArtifactVersionConflictError(RuntimeError):
    """The caller's If-Match version does not match the current artifact."""


class ArtifactOwnershipError(PermissionError):
    """Only the owner can mutate an artifact unless the caller is coordinator."""


@dataclass
class SquadArtifact:
    artifact_id: str
    thread_id: str
    task_id: str | None
    owner_agent_id: str
    version: int
    kind: str
    path_or_uri: str
    visible_to_squad: bool
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


def _decode_metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            data = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}
    return value if isinstance(value, dict) else {}


def _row_to_artifact(row: Any) -> SquadArtifact:
    return SquadArtifact(
        artifact_id=str(row["artifact_id"]),
        thread_id=str(row["thread_id"]),
        task_id=str(row["task_id"]) if row["task_id"] is not None else None,
        owner_agent_id=str(row["owner_agent_id"]),
        version=int(row["version"]),
        kind=str(row["kind"] or ""),
        path_or_uri=str(row["path_or_uri"] or ""),
        visible_to_squad=bool(row["visible_to_squad"]),
        metadata=_decode_metadata(row["metadata_json"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class SquadArtifactStore:
    def __init__(
        self,
        *,
        dsn: str,
        schema: str = "knowledge_v2",
        pool_min_size: int = 1,
        pool_max_size: int = 4,
    ) -> None:
        if not _SCHEMA_RE.match(schema):
            raise ValueError(f"invalid postgres schema name: {schema!r}")
        self._dsn = dsn
        self._schema = schema
        self._pool_min_size = max(1, int(pool_min_size))
        self._pool_max_size = max(self._pool_min_size, int(pool_max_size))
        self._pool: Any | None = None

    async def _ensure_pool(self) -> Any:
        if self._pool is None:
            import asyncpg  # type: ignore[import-not-found]

            self._pool = await asyncpg.create_pool(
                self._dsn,
                min_size=self._pool_min_size,
                max_size=self._pool_max_size,
            )
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            with suppress(Exception):
                await self._pool.close()
            self._pool = None

    async def upsert_artifact(
        self,
        *,
        artifact_id: str,
        thread_id: str,
        owner_agent_id: str,
        task_id: str | None = None,
        kind: str = "",
        path_or_uri: str = "",
        visible_to_squad: bool = True,
        metadata: dict[str, Any] | None = None,
        if_match_version: int | None = None,
        coordinator_override: bool = False,
    ) -> SquadArtifact:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn, conn.transaction():
            current = await conn.fetchrow(
                f'SELECT * FROM "{self._schema}"."squad_artifacts" WHERE artifact_id = $1 FOR UPDATE',
                artifact_id,
            )
            if current is not None:
                if if_match_version is None and current["owner_agent_id"] == owner_agent_id:
                    same_task = (str(current["task_id"]) if current["task_id"] is not None else None) == task_id
                    if same_task and str(current["path_or_uri"] or "") == str(path_or_uri or ""):
                        return _row_to_artifact(current)
                if int(current["version"]) != int(if_match_version or -1):
                    raise ArtifactVersionConflictError(
                        f"artifact {artifact_id!r} version mismatch: expected {if_match_version}, "
                        f"got {current['version']}"
                    )
                if current["owner_agent_id"] != owner_agent_id and not coordinator_override:
                    raise ArtifactOwnershipError(f"artifact {artifact_id!r} is owned by {current['owner_agent_id']!r}")
                row = await conn.fetchrow(
                    f"""UPDATE "{self._schema}"."squad_artifacts"
                           SET task_id = $2::uuid,
                               kind = $3,
                               path_or_uri = $4,
                               visible_to_squad = $5,
                               metadata_json = $6::jsonb,
                               version = version + 1,
                               updated_at = NOW()
                         WHERE artifact_id = $1
                         RETURNING *""",
                    artifact_id,
                    task_id,
                    kind,
                    path_or_uri,
                    bool(visible_to_squad),
                    json.dumps(metadata or {}),
                )
                return _row_to_artifact(row)
            row = await conn.fetchrow(
                f"""INSERT INTO "{self._schema}"."squad_artifacts"
                        (artifact_id, thread_id, task_id, owner_agent_id, kind,
                         path_or_uri, visible_to_squad, metadata_json)
                      VALUES ($1, $2::uuid, $3::uuid, $4, $5, $6, $7, $8::jsonb)
                      RETURNING *""",
                artifact_id,
                thread_id,
                task_id,
                owner_agent_id,
                kind,
                path_or_uri,
                bool(visible_to_squad),
                json.dumps(metadata or {}),
            )
            return _row_to_artifact(row)

    async def list_for_thread(self, *, thread_id: str, include_private: bool = False) -> list[SquadArtifact]:
        pool = await self._ensure_pool()
        sql = f'SELECT * FROM "{self._schema}"."squad_artifacts" WHERE thread_id = $1'
        if not include_private:
            sql += " AND visible_to_squad IS TRUE"
        sql += " ORDER BY created_at DESC"
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, thread_id)
        return [_row_to_artifact(row) for row in rows]

    async def get_artifact(self, artifact_id: str) -> SquadArtifact | None:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f'SELECT * FROM "{self._schema}"."squad_artifacts" WHERE artifact_id = $1',
                artifact_id,
            )
        return _row_to_artifact(row) if row is not None else None


_store: SquadArtifactStore | None = None


def _build_store() -> SquadArtifactStore | None:
    from koda.config import POSTGRES_URL
    from koda.knowledge.config import KNOWLEDGE_V2_POSTGRES_SCHEMA

    if not POSTGRES_URL:
        return None
    schema = (KNOWLEDGE_V2_POSTGRES_SCHEMA or "knowledge_v2").strip() or "knowledge_v2"
    return SquadArtifactStore(dsn=POSTGRES_URL, schema=schema)


def get_squad_artifact_store() -> SquadArtifactStore | None:
    global _store  # noqa: PLW0603
    if _store is None:
        _store = _build_store()
    return _store
