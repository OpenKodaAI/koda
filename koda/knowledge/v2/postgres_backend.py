"""Postgres-backed persistence and retrieval for knowledge v2."""

# ruff: noqa: E501

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from koda.knowledge.config import (
    KNOWLEDGE_EMBEDDING_MODEL,
    KNOWLEDGE_V2_INGEST_MAX_POISONED_JOBS,
    KNOWLEDGE_V2_INGEST_MAX_QUEUE_DEPTH,
    KNOWLEDGE_V2_POSTGRES_ACQUIRE_TIMEOUT_MS,
    KNOWLEDGE_V2_POSTGRES_DSN,
    KNOWLEDGE_V2_POSTGRES_IDLE_TIMEOUT_SECONDS,
    KNOWLEDGE_V2_POSTGRES_POOL_MAX_SIZE,
    KNOWLEDGE_V2_POSTGRES_POOL_MIN_SIZE,
    KNOWLEDGE_V2_POSTGRES_QUERY_TIMEOUT_MS,
    KNOWLEDGE_V2_POSTGRES_RETRY_BASE_SECONDS,
    KNOWLEDGE_V2_POSTGRES_SCHEMA,
    KNOWLEDGE_V2_POSTGRES_START_RETRIES,
)
from koda.knowledge.types import (
    ArtifactDerivative,
    GraphEntity,
    GraphRelation,
    KnowledgeEntry,
    RetrievalTrace,
)
from koda.logging_config import get_logger

log = get_logger(__name__)

_LOW_SIGNAL_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}
_RRF_K = 60
_ISSUE_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")
_PATH_RE = re.compile(r"(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+")
_ERROR_RE = re.compile(r"\b([A-Z][A-Za-z]+(?:Error|Exception))\b")
_SYMBOL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*)\b")
_RELATION_WEIGHTS: dict[str, float] = {
    "governs": 1.0,
    "supersedes": 0.95,
    "verifies": 0.9,
    "requires": 0.9,
    "corroborates": 0.7,
    "supports": 0.7,
    "observed_in": 0.6,
    "derived_from": 0.55,
    "attached_to": 0.5,
    "impacts": 0.5,
    "mentions": 0.35,
    "contradicts": 0.0,
}


class _PostgresAcquireTimeout(RuntimeError):
    """Raised when the asyncpg pool or guarded direct lane cannot provide a connection."""


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, default=str)


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _iso_or_empty(value: Any) -> str:
    if isinstance(value, datetime):
        return _safe_datetime(value).isoformat()
    return str(value or "")


def _tokenize_query(query: str) -> list[str]:
    tokens = []
    for token in "".join(char if char.isalnum() else " " for char in query.lower()).split():
        if token and token not in _LOW_SIGNAL_WORDS:
            tokens.append(token)
    return tokens


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.9f}" for value in vector) + "]"


def _safe_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC)


def _coerce_datetime(value: datetime | str | None) -> datetime:
    if isinstance(value, datetime):
        return _safe_datetime(value)
    if isinstance(value, str) and value.strip():
        try:
            return _safe_datetime(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            pass
    return datetime.now(UTC)


def _rescaled_rrf_score(raw_rrf: float) -> float:
    if raw_rrf <= 0:
        return 0.0
    pivot = 1.0 / max(1, _RRF_K)
    return min(1.0, raw_rrf / (raw_rrf + pivot))


def _workspace_root_for(path_value: str) -> str:
    if not path_value:
        return ""
    try:
        return str(Path(path_value).expanduser().resolve().parent)
    except Exception:
        return str(Path(path_value).parent)


@dataclass(slots=True, frozen=True)
class _Migration:
    version: str
    statements: tuple[str, ...]


class KnowledgeV2PostgresBackend:
    """Single place for Postgres schema management, persistence, and primary reads."""

    def __init__(
        self,
        *,
        agent_id: str | None,
        dsn: str | None = None,
        schema: str | None = None,
        embedding_dimension: int = 1024,
        pool_min_size: int = KNOWLEDGE_V2_POSTGRES_POOL_MIN_SIZE,
        pool_max_size: int = KNOWLEDGE_V2_POSTGRES_POOL_MAX_SIZE,
        acquire_timeout_ms: int = KNOWLEDGE_V2_POSTGRES_ACQUIRE_TIMEOUT_MS,
        query_timeout_ms: int = KNOWLEDGE_V2_POSTGRES_QUERY_TIMEOUT_MS,
        start_retries: int = KNOWLEDGE_V2_POSTGRES_START_RETRIES,
        retry_base_seconds: float = KNOWLEDGE_V2_POSTGRES_RETRY_BASE_SECONDS,
    ) -> None:
        self._agent_id = (agent_id or "default").upper()
        self._dsn = (dsn or KNOWLEDGE_V2_POSTGRES_DSN).strip()
        self._schema = (schema or KNOWLEDGE_V2_POSTGRES_SCHEMA).strip() or "knowledge_v2"
        self._embedding_dimension = max(1, int(embedding_dimension))
        self._pool_min_size = max(1, int(pool_min_size))
        self._pool_max_size = max(self._pool_min_size, int(pool_max_size))
        self._acquire_timeout_seconds = max(0.05, int(acquire_timeout_ms) / 1000)
        self._query_timeout_seconds = max(0.1, int(query_timeout_ms) / 1000)
        self._start_retries = max(0, int(start_retries))
        self._retry_base_seconds = max(0.05, float(retry_base_seconds))
        self._ready = False
        self._vector_enabled = False
        self._ensure_lock = asyncio.Lock()
        self._pool: Any | None = None
        self._asyncpg: Any | None = None
        self._direct_connection_gate = asyncio.Semaphore(self._pool_max_size)
        self._direct_connections_in_flight = 0
        self._pool_wait_timeout_total = 0
        self._direct_wait_timeout_total = 0
        self._query_timeout_total = 0
        self._last_postgres_error = ""

    @property
    def enabled(self) -> bool:
        return bool(self._dsn)

    @property
    def schema(self) -> str:
        return self._schema

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def bootstrapped(self) -> bool:
        return self._ready

    async def start(self) -> bool:
        if not self.enabled:
            return False
        last_error: Exception | None = None
        for attempt in range(self._start_retries + 1):
            try:
                if not await self.bootstrap():
                    raise RuntimeError("knowledge postgres backend not ready")
                await self._ensure_pool()
                return True
            except Exception as exc:
                last_error = exc
                if attempt >= self._start_retries:
                    break
                await asyncio.sleep(self._retry_base_seconds * (2**attempt))
        if last_error is not None:
            log.exception("knowledge_v2_postgres_start_failed")
        return False

    async def close(self) -> None:
        pool = self._pool
        self._pool = None
        if pool is not None:
            with suppress(Exception):
                await pool.close()

    async def health(self) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "ready": False, "pool_active": False}
        pool_active = bool(self._pool)
        check_ok, error, probe_mode = await self._probe_connectivity()
        ready = bool(self._ready and check_ok)
        ingest_queue = await self.ingest_queue_health()
        bootstrap_state = "ready" if self._ready else "not_bootstrapped"
        if not ready and not error and bootstrap_state != "ready":
            error = bootstrap_state
        return {
            "enabled": True,
            "ready": ready,
            "bootstrap_state": bootstrap_state,
            "vector_enabled": self._vector_enabled,
            "pool_active": pool_active,
            "pool_min_size": self._pool_min_size,
            "pool_max_size": self._pool_max_size,
            "pool_size": self._pool_size(),
            "pool_idle": self._pool_idle_size(),
            "pool_in_use": max(0, self._pool_size() - self._pool_idle_size()),
            "acquire_timeout_ms": int(self._acquire_timeout_seconds * 1000),
            "query_timeout_ms": int(self._query_timeout_seconds * 1000),
            "idle_timeout_seconds": KNOWLEDGE_V2_POSTGRES_IDLE_TIMEOUT_SECONDS,
            "pool_wait_timeout_total": self._pool_wait_timeout_total,
            "direct_wait_timeout_total": self._direct_wait_timeout_total,
            "query_timeout_total": self._query_timeout_total,
            "direct_connections_in_flight": self._direct_connections_in_flight,
            "postgres_pool_max_size": self._pool_max_size,
            "postgres_pool_idle": self._pool_idle_size(),
            "postgres_pool_in_use": max(0, self._pool_size() - self._pool_idle_size()),
            "postgres_acquire_timeout_ms": int(self._acquire_timeout_seconds * 1000),
            "postgres_query_timeout_ms": int(self._query_timeout_seconds * 1000),
            "postgres_wait_timeout_total": self._pool_wait_timeout_total,
            "postgres_query_timeout_total": self._query_timeout_total,
            "postgres_last_error": error or self._last_postgres_error,
            "probe_mode": probe_mode,
            "check_ok": check_ok,
            "error": error or self._last_postgres_error,
            "cache": {},
            "ingest_queue": ingest_queue,
        }

    async def _probe_connectivity(self) -> tuple[bool, str, str]:
        try:
            async with self._probe_connection() as (conn, probe_mode):
                async with asyncio.timeout(self._query_timeout_seconds):
                    await conn.fetchval("SELECT 1")
            return True, "", probe_mode
        except TimeoutError:
            self._query_timeout_total += 1
            self._last_postgres_error = "postgres health query timed out"
            return False, self._last_postgres_error, "unavailable"
        except _PostgresAcquireTimeout as exc:
            self._last_postgres_error = str(exc)
            return False, str(exc), "unavailable"
        except Exception as exc:
            self._last_postgres_error = str(exc)
            return False, str(exc), "unavailable"

    async def ensure_ready(self) -> bool:
        if not self.enabled:
            return False
        return self._ready

    async def bootstrap(self) -> bool:
        if not self.enabled:
            return False
        if self._ready:
            return True
        async with self._ensure_lock:
            if self._ready:
                return True
            try:
                conn = await self._open_direct_connection()
                try:
                    await conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{self._schema}"')
                    await conn.execute(
                        f"""CREATE TABLE IF NOT EXISTS "{self._schema}"."schema_migrations" (
                                version TEXT PRIMARY KEY,
                                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                            )"""
                    )
                    try:
                        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                        self._vector_enabled = True
                    except Exception:
                        self._vector_enabled = False
                    applied = {
                        str(row["version"])
                        for row in await conn.fetch(f'SELECT version FROM "{self._schema}"."schema_migrations"')
                    }
                    for migration in self._migrations():
                        if migration.version in applied:
                            continue
                        for statement in migration.statements:
                            await conn.execute(statement)
                        await conn.execute(
                            f"""INSERT INTO "{self._schema}"."schema_migrations" (version) VALUES ($1)
                                ON CONFLICT (version) DO NOTHING""",
                            migration.version,
                        )
                    if self._vector_enabled:
                        await conn.execute(
                            f"""ALTER TABLE "{self._schema}"."knowledge_embeddings"
                                   ADD COLUMN IF NOT EXISTS embedding_vector VECTOR({self._embedding_dimension})"""
                        )
                        await conn.execute(
                            f"""ALTER TABLE "{self._schema}"."artifact_derivatives"
                                   ADD COLUMN IF NOT EXISTS embedding_vector VECTOR({self._embedding_dimension})"""
                        )
                        await conn.execute(
                            f"""CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_vector_hnsw
                                   ON "{self._schema}"."knowledge_embeddings"
                                USING hnsw (embedding_vector vector_cosine_ops)"""
                        )
                        await conn.execute(
                            f"""CREATE INDEX IF NOT EXISTS idx_artifact_derivatives_vector_hnsw
                                   ON "{self._schema}"."artifact_derivatives"
                                USING hnsw (embedding_vector vector_cosine_ops)"""
                        )
                finally:
                    await self._close_direct_connection(conn)
            except Exception:
                log.exception("knowledge_v2_postgres_init_failed")
                return False
            self._ready = True
            return True

    async def _load_asyncpg(self) -> Any:
        if self._asyncpg is None:
            import asyncpg

            self._asyncpg = asyncpg
        return self._asyncpg

    async def _ensure_pool(self) -> None:
        if self._pool is not None:
            # Keep the existing pool. If it belongs to a different event loop,
            # ``_connection()`` / ``_probe_connection()`` will skip it via
            # ``_pool_loop_matches_current()`` and fall back to a direct
            # connection for this loop. Closing the cross-loop pool from the
            # current loop triggers ``InterfaceError: pool is closing`` for
            # any in-flight acquire on the original loop.
            return
        asyncpg = await self._load_asyncpg()
        create_pool = getattr(asyncpg, "create_pool", None)
        if create_pool is None:
            return
        self._pool = await create_pool(
            self._dsn,
            min_size=self._pool_min_size,
            max_size=self._pool_max_size,
            timeout=self._acquire_timeout_seconds,
            command_timeout=self._query_timeout_seconds,
            max_inactive_connection_lifetime=max(1, KNOWLEDGE_V2_POSTGRES_IDLE_TIMEOUT_SECONDS),
        )

    @asynccontextmanager
    async def _probe_connection(self) -> AsyncIterator[tuple[Any, str]]:
        if self._pool is not None and self._pool_loop_matches_current():
            async with self._pooled_connection() as conn:
                yield conn, "pool"
            return
        conn = await self._open_direct_connection()
        try:
            yield conn, "direct"
        finally:
            await self._close_direct_connection(conn)

    def _pool_loop_matches_current(self) -> bool:
        """Return True when the cached pool is usable from the current loop.

        asyncpg pools bind to one event loop at creation. Accessing a pool
        from a different loop raises ``Future attached to a different loop``.
        Test fakes typically omit the ``_loop`` attribute — we treat a
        missing attribute as "usable" so unit tests needn't mirror asyncpg
        internals.
        """
        if self._pool is None:
            return False
        existing_loop = getattr(self._pool, "_loop", None)
        if existing_loop is None:
            return True
        try:
            return existing_loop is asyncio.get_running_loop()
        except RuntimeError:
            return False

    @asynccontextmanager
    async def _connection(self) -> AsyncIterator[Any]:
        if not self.bootstrapped and not await self.start():
            raise RuntimeError("knowledge_v2_postgres_backend_unavailable")
        await self._ensure_pool()
        if self._pool is not None and self._pool_loop_matches_current():
            async with self._pooled_connection() as conn:
                yield conn
            return
        # No pool for the current loop — fall back to a throwaway direct
        # connection rather than poisoning the cached pool. This happens
        # when a caller on a second event loop in the same process needs
        # DB access (worker main loop while bridge loop owns the pool).
        conn = await self._open_direct_connection()
        try:
            yield conn
        finally:
            await self._close_direct_connection(conn)

    @asynccontextmanager
    async def _pooled_connection(self) -> AsyncIterator[Any]:
        context = self._pool_acquire_context()
        try:
            conn = await context.__aenter__()
        except TimeoutError:
            self._pool_wait_timeout_total += 1
            self._last_postgres_error = "postgres pool acquire timed out"
            raise _PostgresAcquireTimeout(self._last_postgres_error) from None
        except Exception as exc:
            self._last_postgres_error = str(exc)
            raise
        try:
            yield conn
        except BaseException as exc:
            handled = await context.__aexit__(type(exc), exc, exc.__traceback__)
            if not handled:
                raise
        else:
            await context.__aexit__(None, None, None)

    def _pool_acquire_context(self) -> Any:
        """Acquire asyncpg pools with timeout while keeping lightweight test fakes usable."""
        if self._pool is None:
            raise RuntimeError("knowledge_v2_postgres_pool_unavailable")
        try:
            return self._pool.acquire(timeout=self._acquire_timeout_seconds)
        except TypeError:
            return self._pool.acquire()

    async def _open_direct_connection(self) -> Any:
        try:
            await asyncio.wait_for(
                self._direct_connection_gate.acquire(),
                timeout=self._acquire_timeout_seconds,
            )
        except TimeoutError:
            self._direct_wait_timeout_total += 1
            self._last_postgres_error = "direct postgres connection lane saturated"
            raise _PostgresAcquireTimeout(self._last_postgres_error) from None
        self._direct_connections_in_flight += 1
        try:
            asyncpg = await self._load_asyncpg()
            try:
                return await asyncpg.connect(
                    self._dsn,
                    timeout=self._acquire_timeout_seconds,
                    command_timeout=self._query_timeout_seconds,
                )
            except TypeError:
                return await asyncpg.connect(self._dsn)
        except Exception as exc:
            self._last_postgres_error = str(exc)
            self._direct_connections_in_flight = max(0, self._direct_connections_in_flight - 1)
            self._direct_connection_gate.release()
            raise

    async def _close_direct_connection(self, conn: Any) -> None:
        try:
            await conn.close()
        finally:
            self._direct_connections_in_flight = max(0, self._direct_connections_in_flight - 1)
            self._direct_connection_gate.release()

    def _pool_size(self) -> int:
        if self._pool is None:
            return 0
        getter = getattr(self._pool, "get_size", None)
        if callable(getter):
            with suppress(Exception):
                return max(0, int(getter()))
        holders = getattr(self._pool, "_holders", None)
        if holders is not None:
            with suppress(Exception):
                return max(0, len(holders))
        return 0

    def _pool_idle_size(self) -> int:
        if self._pool is None:
            return 0
        getter = getattr(self._pool, "get_idle_size", None)
        if callable(getter):
            with suppress(Exception):
                return max(0, int(getter()))
        return 0

    def _invalidate_query_caches(self) -> None:
        return None

    def _migrations(self) -> tuple[_Migration, ...]:
        schema = self._schema
        return (
            _Migration(
                "001_base_tables",
                (
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."knowledge_documents" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            document_key TEXT NOT NULL,
                            source_label TEXT NOT NULL,
                            source_path TEXT NOT NULL,
                            workspace_root TEXT NOT NULL DEFAULT '',
                            layer TEXT NOT NULL,
                            scope TEXT NOT NULL,
                            title TEXT NOT NULL,
                            content TEXT NOT NULL,
                            owner TEXT NOT NULL DEFAULT '',
                            project_key TEXT NOT NULL DEFAULT '',
                            environment TEXT NOT NULL DEFAULT '',
                            team TEXT NOT NULL DEFAULT '',
                            source_type TEXT NOT NULL DEFAULT 'document',
                            operable BOOLEAN NOT NULL DEFAULT TRUE,
                            freshness_days INTEGER NOT NULL DEFAULT 90,
                            tags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                            metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            content_hash TEXT NOT NULL,
                            object_key TEXT NOT NULL,
                            updated_at TIMESTAMPTZ NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE (agent_id, document_key)
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."knowledge_chunks" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            chunk_key TEXT NOT NULL,
                            document_key TEXT NOT NULL,
                            source_label TEXT NOT NULL,
                            source_path TEXT NOT NULL,
                            workspace_root TEXT NOT NULL DEFAULT '',
                            layer TEXT NOT NULL,
                            scope TEXT NOT NULL,
                            title TEXT NOT NULL,
                            content TEXT NOT NULL,
                            owner TEXT NOT NULL DEFAULT '',
                            project_key TEXT NOT NULL DEFAULT '',
                            environment TEXT NOT NULL DEFAULT '',
                            team TEXT NOT NULL DEFAULT '',
                            source_type TEXT NOT NULL DEFAULT 'document',
                            operable BOOLEAN NOT NULL DEFAULT TRUE,
                            freshness_days INTEGER NOT NULL DEFAULT 90,
                            tags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                            metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            updated_at TIMESTAMPTZ NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            search_vector TSVECTOR GENERATED ALWAYS AS (
                                to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(content, ''))
                            ) STORED,
                            UNIQUE (agent_id, chunk_key)
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."knowledge_embeddings" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            embedding_key TEXT NOT NULL,
                            chunk_key TEXT NOT NULL,
                            document_key TEXT NOT NULL,
                            model TEXT NOT NULL,
                            vector_json JSONB NOT NULL,
                            payload_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            object_key TEXT NOT NULL,
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE (agent_id, embedding_key)
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."knowledge_entities" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            entity_key TEXT NOT NULL,
                            entity_type TEXT NOT NULL,
                            label TEXT NOT NULL,
                            source_kind TEXT NOT NULL DEFAULT 'knowledge',
                            metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE (agent_id, entity_key)
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."knowledge_relations" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            relation_key TEXT NOT NULL,
                            relation_type TEXT NOT NULL,
                            source_entity_key TEXT NOT NULL,
                            target_entity_key TEXT NOT NULL,
                            weight DOUBLE PRECISION NOT NULL DEFAULT 1.0,
                            metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE (agent_id, relation_key)
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."retrieval_traces" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            task_id BIGINT,
                            query_text TEXT NOT NULL,
                            strategy TEXT NOT NULL,
                            route TEXT NOT NULL,
                            project_key TEXT NOT NULL DEFAULT '',
                            environment TEXT NOT NULL DEFAULT '',
                            team TEXT NOT NULL DEFAULT '',
                            graph_hops INTEGER NOT NULL DEFAULT 0,
                            grounding_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            required_citation_count INTEGER NOT NULL DEFAULT 0,
                            conflict_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                            evidence_modalities_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                            winning_sources_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                            explanation TEXT NOT NULL DEFAULT '',
                            experiment_key TEXT NOT NULL DEFAULT '',
                            trace_role TEXT NOT NULL DEFAULT 'primary',
                            paired_trace_id BIGINT,
                            payload_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."retrieval_trace_hits" (
                            id BIGSERIAL PRIMARY KEY,
                            trace_id BIGINT NOT NULL REFERENCES "{schema}"."retrieval_traces"(id) ON DELETE CASCADE,
                            hit_id TEXT NOT NULL,
                            title TEXT NOT NULL,
                            layer TEXT NOT NULL,
                            source_label TEXT NOT NULL,
                            similarity DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            freshness TEXT NOT NULL DEFAULT '',
                            selected BOOLEAN NOT NULL DEFAULT FALSE,
                            rank_before INTEGER NOT NULL DEFAULT 0,
                            rank_after INTEGER NOT NULL DEFAULT 0,
                            graph_hops INTEGER NOT NULL DEFAULT 0,
                            graph_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                            exclusion_reason TEXT NOT NULL DEFAULT '',
                            evidence_modalities_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                            supporting_evidence_keys_json JSONB NOT NULL DEFAULT '[]'::jsonb
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."retrieval_bundles" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            task_id BIGINT,
                            payload_json JSONB NOT NULL,
                            object_key TEXT NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."answer_traces" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            task_id BIGINT,
                            operational_status TEXT NOT NULL DEFAULT '',
                            answer_text TEXT NOT NULL DEFAULT '',
                            citations_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                            supporting_evidence_refs_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                            uncertainty_notes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                            answer_plan_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            judge_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            authoritative_sources_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                            supporting_sources_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                            uncertainty_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            payload_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            object_key TEXT NOT NULL DEFAULT '',
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."answer_judgements" (
                            id BIGSERIAL PRIMARY KEY,
                            answer_trace_id BIGINT NOT NULL REFERENCES "{schema}"."answer_traces"(id) ON DELETE CASCADE,
                            agent_id TEXT NOT NULL,
                            task_id BIGINT,
                            status TEXT NOT NULL DEFAULT '',
                            reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                            warnings_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                            citation_coverage DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            citation_span_precision DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            contradiction_escape_rate DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            policy_compliance DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            requires_review BOOLEAN NOT NULL DEFAULT FALSE,
                            safe_response TEXT NOT NULL DEFAULT '',
                            payload_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."evaluation_cases" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            case_key TEXT NOT NULL,
                            query TEXT NOT NULL,
                            source_task_id BIGINT,
                            task_kind TEXT NOT NULL DEFAULT 'general',
                            project_key TEXT NOT NULL DEFAULT '',
                            environment TEXT NOT NULL DEFAULT '',
                            team TEXT NOT NULL DEFAULT '',
                            modality TEXT NOT NULL DEFAULT 'text',
                            expected_sources_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                            expected_layers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                            reference_answer TEXT NOT NULL DEFAULT '',
                            status TEXT NOT NULL DEFAULT 'draft',
                            gold_source_kind TEXT NOT NULL DEFAULT 'manual_gold',
                            validated_by TEXT NOT NULL DEFAULT '',
                            validated_at TEXT NOT NULL DEFAULT '',
                            metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE (agent_id, case_key)
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."evaluation_runs" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            case_key TEXT NOT NULL,
                            strategy TEXT NOT NULL,
                            retrieval_trace_id BIGINT,
                            recall_at_k DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            ndcg_at_k DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            citation_accuracy DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            groundedness_precision DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            conflict_detection_rate DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            verification_before_finalize_rate DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            human_correction_rate DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            task_success_proxy DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."artifact_manifests" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            task_id BIGINT,
                            artifact_id TEXT NOT NULL,
                            source_path TEXT NOT NULL DEFAULT '',
                            source_url TEXT NOT NULL DEFAULT '',
                            object_key TEXT NOT NULL DEFAULT '',
                            metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE (agent_id, artifact_id)
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."artifact_derivatives" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            task_id BIGINT,
                            derivative_key TEXT NOT NULL,
                            artifact_id TEXT NOT NULL DEFAULT '',
                            project_key TEXT NOT NULL DEFAULT '',
                            workspace_fingerprint TEXT NOT NULL DEFAULT '',
                            modality TEXT NOT NULL,
                            label TEXT NOT NULL,
                            extracted_text TEXT NOT NULL DEFAULT '',
                            confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            trust_level TEXT NOT NULL DEFAULT 'untrusted',
                            source_path TEXT NOT NULL DEFAULT '',
                            source_url TEXT NOT NULL DEFAULT '',
                            source_object_key TEXT NOT NULL DEFAULT '',
                            time_span TEXT NOT NULL DEFAULT '',
                            frame_ref TEXT NOT NULL DEFAULT '',
                            provenance_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            embedding_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                            search_vector TSVECTOR GENERATED ALWAYS AS (
                                to_tsvector('simple', coalesce(label, '') || ' ' || coalesce(extracted_text, ''))
                            ) STORED,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE (agent_id, derivative_key)
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."knowledge_ingest_jobs" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            job_key TEXT NOT NULL,
                            task_id BIGINT,
                            artifact_id TEXT NOT NULL DEFAULT '',
                            job_type TEXT NOT NULL DEFAULT 'artifact_derivative',
                            status TEXT NOT NULL DEFAULT 'ready',
                            priority INTEGER NOT NULL DEFAULT 50,
                            source_path TEXT NOT NULL DEFAULT '',
                            source_url TEXT NOT NULL DEFAULT '',
                            payload_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            attempts INTEGER NOT NULL DEFAULT 0,
                            available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            leased_at TIMESTAMPTZ,
                            lease_owner TEXT NOT NULL DEFAULT '',
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE (agent_id, job_key)
                        )""",
                ),
            ),
            _Migration(
                "002_indexes",
                (
                    f"""CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_lookup
                           ON "{schema}"."knowledge_chunks"
                           (agent_id, project_key, environment, team, updated_at DESC)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_search
                           ON "{schema}"."knowledge_chunks" USING GIN (search_vector)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_lookup
                           ON "{schema}"."knowledge_embeddings"
                           (agent_id, model, updated_at DESC)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_knowledge_entities_lookup
                           ON "{schema}"."knowledge_entities"
                           (agent_id, entity_type, updated_at DESC)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_knowledge_relations_lookup
                           ON "{schema}"."knowledge_relations"
                           (agent_id, relation_type, source_entity_key, target_entity_key)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_retrieval_traces_lookup
                           ON "{schema}"."retrieval_traces"
                           (agent_id, task_id, strategy, created_at DESC)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_answer_traces_lookup
                           ON "{schema}"."answer_traces"
                           (agent_id, task_id, created_at DESC)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_evaluation_cases_lookup
                           ON "{schema}"."evaluation_cases"
                           (agent_id, task_kind, project_key, environment, updated_at DESC)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_artifact_derivatives_lookup
                           ON "{schema}"."artifact_derivatives"
                           (agent_id, task_id, project_key, workspace_fingerprint, created_at DESC)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_artifact_derivatives_search
                           ON "{schema}"."artifact_derivatives" USING GIN (search_vector)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_knowledge_ingest_jobs_lookup
                           ON "{schema}"."knowledge_ingest_jobs"
                           (agent_id, status, priority, available_at)""",
                ),
            ),
            _Migration(
                "003_audit_events",
                (
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."audit_events" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            timestamp TIMESTAMPTZ NOT NULL,
                            event_type TEXT NOT NULL,
                            pod_name TEXT NOT NULL DEFAULT '',
                            user_id BIGINT,
                            task_id BIGINT,
                            trace_id TEXT NOT NULL DEFAULT '',
                            details_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            cost_usd DOUBLE PRECISION,
                            duration_ms DOUBLE PRECISION,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_audit_events_lookup
                           ON "{schema}"."audit_events"
                           (agent_id, timestamp DESC, event_type)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_audit_events_user
                           ON "{schema}"."audit_events"
                           (agent_id, user_id, timestamp DESC)""",
                ),
            ),
            _Migration(
                "004_primary_state_tables",
                (
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."query_history" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            user_id BIGINT NOT NULL,
                            timestamp TIMESTAMPTZ NOT NULL,
                            query_text TEXT NOT NULL,
                            response_text TEXT NOT NULL,
                            cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            provider TEXT NOT NULL DEFAULT 'claude',
                            model TEXT NOT NULL DEFAULT '',
                            session_id TEXT,
                            provider_session_id TEXT,
                            usage_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            work_dir TEXT NOT NULL DEFAULT '',
                            error BOOLEAN NOT NULL DEFAULT FALSE,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_query_history_lookup
                           ON "{schema}"."query_history"
                           (agent_id, user_id, timestamp DESC)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."user_cost_totals" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            user_id BIGINT NOT NULL,
                            total_cost DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            query_count BIGINT NOT NULL DEFAULT 0,
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE (agent_id, user_id)
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."digest_preferences" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            user_id BIGINT NOT NULL,
                            chat_id BIGINT NOT NULL,
                            enabled BOOLEAN NOT NULL DEFAULT TRUE,
                            send_hour INTEGER NOT NULL DEFAULT 9,
                            send_minute INTEGER NOT NULL DEFAULT 0,
                            timezone TEXT NOT NULL DEFAULT 'UTC',
                            last_sent_date TEXT,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE (agent_id, user_id)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_digest_preferences_enabled
                           ON "{schema}"."digest_preferences"
                           (agent_id, enabled, send_hour, send_minute)""",
                ),
            ),
            _Migration(
                "005_runtime_state_tables",
                (
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."tasks" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            user_id BIGINT NOT NULL,
                            chat_id BIGINT NOT NULL,
                            status TEXT NOT NULL DEFAULT 'queued',
                            query_text TEXT NOT NULL DEFAULT '',
                            provider TEXT,
                            model TEXT,
                            work_dir TEXT,
                            attempt INTEGER NOT NULL DEFAULT 1,
                            max_attempts INTEGER NOT NULL DEFAULT 3,
                            cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            error_message TEXT,
                            created_at TEXT NOT NULL,
                            started_at TEXT,
                            completed_at TEXT,
                            session_id TEXT,
                            provider_session_id TEXT,
                            source_task_id BIGINT,
                            source_action TEXT,
                            env_id BIGINT,
                            classification TEXT,
                            environment_kind TEXT,
                            current_phase TEXT,
                            last_heartbeat_at TEXT,
                            retention_expires_at TEXT
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_tasks_user_status
                           ON "{schema}"."tasks"
                           (agent_id, user_id, status, id DESC)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."runtime_environments" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            task_id BIGINT NOT NULL,
                            user_id BIGINT NOT NULL,
                            chat_id BIGINT NOT NULL,
                            classification TEXT NOT NULL,
                            environment_kind TEXT NOT NULL,
                            isolation TEXT NOT NULL,
                            duration TEXT NOT NULL,
                            status TEXT NOT NULL DEFAULT 'active',
                            current_phase TEXT NOT NULL DEFAULT 'queued',
                            workspace_path TEXT NOT NULL,
                            runtime_dir TEXT NOT NULL,
                            base_work_dir TEXT NOT NULL,
                            branch_name TEXT,
                            created_worktree BOOLEAN NOT NULL DEFAULT FALSE,
                            worktree_mode TEXT NOT NULL DEFAULT 'shared',
                            is_pinned BOOLEAN NOT NULL DEFAULT FALSE,
                            checkpoint_status TEXT NOT NULL DEFAULT 'pending',
                            checkpoint_path TEXT,
                            parent_env_id BIGINT,
                            lineage_root_env_id BIGINT,
                            source_checkpoint_id BIGINT,
                            recovery_state TEXT NOT NULL DEFAULT '',
                            revision INTEGER NOT NULL DEFAULT 1,
                            browser_transport TEXT NOT NULL DEFAULT '',
                            display_id INTEGER,
                            vnc_port INTEGER,
                            novnc_port INTEGER,
                            pause_state TEXT NOT NULL DEFAULT 'none',
                            pause_reason TEXT NOT NULL DEFAULT '',
                            save_verified_at TEXT,
                            process_pid INTEGER,
                            process_pgid INTEGER,
                            browser_scope_id BIGINT,
                            retention_expires_at TEXT,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            last_heartbeat_at TEXT,
                            UNIQUE (agent_id, task_id)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_runtime_environments_status
                           ON "{schema}"."runtime_environments"
                           (agent_id, status, current_phase, last_heartbeat_at)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."runtime_queue_items" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            task_id BIGINT NOT NULL,
                            user_id BIGINT NOT NULL,
                            chat_id BIGINT NOT NULL,
                            queue_name TEXT NOT NULL DEFAULT 'user',
                            status TEXT NOT NULL DEFAULT 'queued',
                            queue_position INTEGER,
                            query_text TEXT NOT NULL DEFAULT '',
                            queued_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            UNIQUE (agent_id, task_id)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_runtime_queue_items_status
                           ON "{schema}"."runtime_queue_items"
                           (agent_id, status, queued_at)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."runtime_processes" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            task_id BIGINT NOT NULL,
                            env_id BIGINT,
                            pid INTEGER NOT NULL,
                            pgid INTEGER,
                            parent_pid INTEGER,
                            role TEXT NOT NULL,
                            process_kind TEXT NOT NULL DEFAULT 'service',
                            command TEXT NOT NULL DEFAULT '',
                            status TEXT NOT NULL DEFAULT 'running',
                            exit_code INTEGER,
                            started_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            exited_at TEXT
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."runtime_events" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            task_id BIGINT,
                            env_id BIGINT,
                            attempt INTEGER,
                            phase TEXT,
                            event_type TEXT NOT NULL,
                            severity TEXT NOT NULL,
                            payload_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            artifact_refs_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                            resource_snapshot_ref TEXT,
                            created_at TEXT NOT NULL
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_runtime_events_task
                           ON "{schema}"."runtime_events"
                           (agent_id, task_id, env_id, id)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."runtime_terminals" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            task_id BIGINT NOT NULL,
                            env_id BIGINT,
                            terminal_kind TEXT NOT NULL,
                            label TEXT NOT NULL,
                            path TEXT NOT NULL,
                            stream_path TEXT,
                            interactive BOOLEAN NOT NULL DEFAULT FALSE,
                            cursor_offset BIGINT NOT NULL DEFAULT 0,
                            last_offset BIGINT NOT NULL DEFAULT 0,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."runtime_browser_sessions" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            task_id BIGINT NOT NULL,
                            env_id BIGINT,
                            scope_id BIGINT NOT NULL,
                            transport TEXT NOT NULL,
                            status TEXT NOT NULL,
                            display_id INTEGER,
                            vnc_port INTEGER,
                            novnc_port INTEGER,
                            metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            ended_at TEXT
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."runtime_service_endpoints" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            task_id BIGINT NOT NULL,
                            env_id BIGINT,
                            process_id BIGINT,
                            service_kind TEXT NOT NULL,
                            label TEXT NOT NULL,
                            host TEXT NOT NULL,
                            port INTEGER NOT NULL,
                            protocol TEXT NOT NULL DEFAULT 'tcp',
                            status TEXT NOT NULL DEFAULT 'active',
                            url TEXT NOT NULL DEFAULT '',
                            metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            ended_at TEXT
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."runtime_loop_cycles" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            task_id BIGINT NOT NULL,
                            env_id BIGINT,
                            cycle_index INTEGER NOT NULL,
                            phase TEXT NOT NULL,
                            goal TEXT NOT NULL DEFAULT '',
                            plan_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            hypothesis TEXT NOT NULL DEFAULT '',
                            command_fingerprint TEXT NOT NULL DEFAULT '',
                            diff_hash TEXT NOT NULL DEFAULT '',
                            failure_fingerprint TEXT NOT NULL DEFAULT '',
                            validations_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                            outcome_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TEXT NOT NULL
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."runtime_guardrail_hits" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            task_id BIGINT NOT NULL,
                            env_id BIGINT,
                            cycle_id BIGINT,
                            guardrail_type TEXT NOT NULL,
                            details_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TEXT NOT NULL
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."runtime_attach_sessions" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            task_id BIGINT NOT NULL,
                            env_id BIGINT,
                            attach_kind TEXT NOT NULL,
                            terminal_id BIGINT,
                            token TEXT NOT NULL,
                            can_write BOOLEAN NOT NULL DEFAULT FALSE,
                            actor TEXT NOT NULL,
                            status TEXT NOT NULL DEFAULT 'active',
                            expires_at TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            last_seen_at TEXT NOT NULL,
                            ended_at TEXT,
                            UNIQUE (agent_id, token)
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."runtime_artifacts" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            task_id BIGINT NOT NULL,
                            env_id BIGINT,
                            artifact_kind TEXT NOT NULL,
                            label TEXT NOT NULL,
                            path TEXT NOT NULL,
                            metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TEXT NOT NULL,
                            expires_at TEXT
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."runtime_checkpoints" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            task_id BIGINT NOT NULL,
                            env_id BIGINT NOT NULL,
                            status TEXT NOT NULL,
                            checkpoint_dir TEXT NOT NULL,
                            manifest_path TEXT NOT NULL,
                            patch_path TEXT NOT NULL,
                            commit_sha TEXT,
                            metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TEXT NOT NULL,
                            expires_at TEXT
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."runtime_resource_samples" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            task_id BIGINT NOT NULL,
                            env_id BIGINT,
                            cpu_percent DOUBLE PRECISION,
                            rss_kb DOUBLE PRECISION,
                            process_count INTEGER,
                            workspace_disk_bytes BIGINT,
                            metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TEXT NOT NULL
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."runtime_warnings" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            task_id BIGINT NOT NULL,
                            env_id BIGINT,
                            warning_type TEXT NOT NULL,
                            message TEXT NOT NULL,
                            details_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TEXT NOT NULL
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."runtime_recovery_actions" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            task_id BIGINT NOT NULL,
                            env_id BIGINT,
                            action TEXT NOT NULL,
                            status TEXT NOT NULL,
                            checkpoint_id BIGINT,
                            new_task_id BIGINT,
                            new_env_id BIGINT,
                            details_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TEXT NOT NULL
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."runtime_port_allocations" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            task_id BIGINT NOT NULL,
                            env_id BIGINT,
                            purpose TEXT NOT NULL,
                            host TEXT NOT NULL,
                            port INTEGER NOT NULL,
                            status TEXT NOT NULL DEFAULT 'allocated',
                            metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            released_at TEXT
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."correction_events" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            task_id BIGINT,
                            episode_id BIGINT,
                            runbook_id BIGINT,
                            candidate_id BIGINT,
                            task_kind TEXT NOT NULL,
                            feedback_type TEXT NOT NULL,
                            note TEXT,
                            user_id BIGINT,
                            project_key TEXT,
                            environment TEXT,
                            created_at TEXT NOT NULL
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_correction_events_lookup
                           ON "{schema}"."correction_events"
                           (agent_id, task_kind, project_key, environment, created_at DESC)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."execution_reliability_stats" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            task_kind TEXT NOT NULL,
                            project_key TEXT NOT NULL DEFAULT '',
                            environment TEXT NOT NULL DEFAULT '',
                            total_runs INTEGER NOT NULL DEFAULT 0,
                            successful_runs INTEGER NOT NULL DEFAULT 0,
                            verified_runs INTEGER NOT NULL DEFAULT 0,
                            human_override_count INTEGER NOT NULL DEFAULT 0,
                            correction_count INTEGER NOT NULL DEFAULT 0,
                            rollback_count INTEGER NOT NULL DEFAULT 0,
                            updated_at TEXT NOT NULL,
                            UNIQUE (agent_id, task_kind, project_key, environment)
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."execution_episodes" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            task_id BIGINT,
                            user_id BIGINT,
                            task_kind TEXT NOT NULL,
                            project_key TEXT NOT NULL DEFAULT '',
                            environment TEXT NOT NULL DEFAULT '',
                            team TEXT NOT NULL DEFAULT '',
                            autonomy_tier TEXT NOT NULL DEFAULT '',
                            approval_mode TEXT NOT NULL DEFAULT '',
                            status TEXT NOT NULL,
                            confidence_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            verified_before_finalize BOOLEAN NOT NULL DEFAULT FALSE,
                            stale_sources_present BOOLEAN NOT NULL DEFAULT FALSE,
                            ungrounded_operationally BOOLEAN NOT NULL DEFAULT FALSE,
                            plan_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            source_refs_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                            tool_trace_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                            feedback_status TEXT NOT NULL DEFAULT 'pending',
                            retrieval_trace_id BIGINT,
                            retrieval_strategy TEXT NOT NULL DEFAULT '',
                            grounding_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            citation_coverage DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            winning_sources_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                            answer_citation_coverage DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            answer_gate_status TEXT NOT NULL DEFAULT '',
                            answer_gate_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                            post_write_review_required BOOLEAN NOT NULL DEFAULT FALSE,
                            created_at TEXT NOT NULL
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_execution_episodes_task
                           ON "{schema}"."execution_episodes"
                           (agent_id, task_id, task_kind, project_key, environment)""",
                ),
            ),
            _Migration(
                "006_control_plane_state_tables",
                (
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_agent_definitions" (
                            id TEXT PRIMARY KEY,
                            display_name TEXT NOT NULL,
                            status TEXT NOT NULL DEFAULT 'paused',
                            appearance_json TEXT NOT NULL DEFAULT '{{}}',
                            storage_namespace TEXT NOT NULL,
                            runtime_endpoint_json TEXT NOT NULL DEFAULT '{{}}',
                            applied_version INTEGER,
                            desired_version INTEGER,
                            metadata_json TEXT NOT NULL DEFAULT '{{}}',
                            workspace_id TEXT,
                            squad_id TEXT,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_workspaces" (
                            id TEXT PRIMARY KEY,
                            name TEXT NOT NULL,
                            description TEXT NOT NULL DEFAULT '',
                            spec_json TEXT NOT NULL DEFAULT '{{}}'  ,
                            documents_json TEXT NOT NULL DEFAULT '{{}}',
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_workspace_squads" (
                            id TEXT PRIMARY KEY,
                            workspace_id TEXT NOT NULL,
                            name TEXT NOT NULL,
                            description TEXT NOT NULL DEFAULT '',
                            spec_json TEXT NOT NULL DEFAULT '{{}}'  ,
                            documents_json TEXT NOT NULL DEFAULT '{{}}',
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            UNIQUE (workspace_id, name)
                        )""",
                    # Drop the legacy color column if it exists from older deployments.
                    f"""ALTER TABLE "{schema}"."cp_workspaces" DROP COLUMN IF EXISTS color""",
                    f"""ALTER TABLE "{schema}"."cp_workspace_squads" DROP COLUMN IF EXISTS color""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_agent_sections" (
                            agent_id TEXT NOT NULL,
                            section TEXT NOT NULL,
                            data_json TEXT NOT NULL DEFAULT '{{}}',
                            updated_at TEXT NOT NULL,
                            PRIMARY KEY (agent_id, section)
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_global_sections" (
                            section TEXT PRIMARY KEY,
                            data_json TEXT NOT NULL DEFAULT '{{}}',
                            updated_at TEXT NOT NULL
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_agent_documents" (
                            agent_id TEXT NOT NULL,
                            kind TEXT NOT NULL,
                            content_md TEXT NOT NULL DEFAULT '',
                            updated_at TEXT NOT NULL,
                            PRIMARY KEY (agent_id, kind)
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_global_default_versions" (
                            id BIGSERIAL PRIMARY KEY,
                            snapshot_json TEXT NOT NULL,
                            created_at TEXT NOT NULL
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_agent_config_versions" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            version INTEGER NOT NULL,
                            snapshot_json TEXT NOT NULL,
                            status TEXT NOT NULL DEFAULT 'published',
                            summary TEXT NOT NULL DEFAULT '',
                            created_at TEXT NOT NULL,
                            published_at TEXT NOT NULL,
                            UNIQUE (agent_id, version)
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_template_assets" (
                            id BIGSERIAL PRIMARY KEY,
                            scope_id TEXT NOT NULL,
                            agent_id TEXT,
                            name TEXT NOT NULL,
                            content TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            UNIQUE (scope_id, name)
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_skill_assets" (
                            id BIGSERIAL PRIMARY KEY,
                            scope_id TEXT NOT NULL,
                            agent_id TEXT,
                            name TEXT NOT NULL,
                            content TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            UNIQUE (scope_id, name)
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_knowledge_assets" (
                            id BIGSERIAL PRIMARY KEY,
                            scope_id TEXT NOT NULL,
                            agent_id TEXT,
                            asset_key TEXT NOT NULL,
                            title TEXT NOT NULL DEFAULT '',
                            kind TEXT NOT NULL DEFAULT 'entry',
                            content_text TEXT NOT NULL DEFAULT '',
                            body_json TEXT NOT NULL DEFAULT '{{}}',
                            enabled INTEGER NOT NULL DEFAULT 1,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            UNIQUE (scope_id, asset_key)
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_secret_values" (
                            id BIGSERIAL PRIMARY KEY,
                            scope_id TEXT NOT NULL,
                            agent_id TEXT,
                            secret_key TEXT NOT NULL,
                            encrypted_value TEXT NOT NULL,
                            preview TEXT NOT NULL DEFAULT '',
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            UNIQUE (scope_id, secret_key)
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_apply_operations" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            target_version INTEGER NOT NULL,
                            status TEXT NOT NULL DEFAULT 'pending',
                            requested_at TEXT NOT NULL,
                            started_at TEXT,
                            applied_at TEXT,
                            details_json TEXT NOT NULL DEFAULT '{{}}'
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_cp_apply_ops_lookup
                           ON "{schema}"."cp_apply_operations"
                           (agent_id, status, target_version DESC)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_provider_connections" (
                            provider_id TEXT PRIMARY KEY,
                            auth_mode TEXT NOT NULL DEFAULT 'subscription_login',
                            configured INTEGER NOT NULL DEFAULT 0,
                            verified INTEGER NOT NULL DEFAULT 0,
                            account_label TEXT NOT NULL DEFAULT '',
                            plan_label TEXT NOT NULL DEFAULT '',
                            project_id TEXT NOT NULL DEFAULT '',
                            last_verified_at TEXT,
                            last_error TEXT NOT NULL DEFAULT '',
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_provider_login_sessions" (
                            id TEXT PRIMARY KEY,
                            provider_id TEXT NOT NULL,
                            auth_mode TEXT NOT NULL DEFAULT 'subscription_login',
                            status TEXT NOT NULL DEFAULT 'pending',
                            details_json TEXT NOT NULL DEFAULT '{{}}',
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            completed_at TEXT
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_cp_provider_login_sessions_lookup
                           ON "{schema}"."cp_provider_login_sessions"
                           (provider_id, status, created_at DESC)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_provider_download_jobs" (
                            id TEXT PRIMARY KEY,
                            provider_id TEXT NOT NULL,
                            asset_id TEXT NOT NULL,
                            status TEXT NOT NULL DEFAULT 'pending',
                            downloaded_bytes BIGINT NOT NULL DEFAULT 0,
                            total_bytes BIGINT NOT NULL DEFAULT 0,
                            progress_percent DOUBLE PRECISION NOT NULL DEFAULT 0,
                            details_json TEXT NOT NULL DEFAULT '{{}}',
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            completed_at TEXT
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_cp_provider_download_jobs_lookup
                           ON "{schema}"."cp_provider_download_jobs"
                           (provider_id, asset_id, status, created_at DESC)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_cp_workspace_squads_workspace
                           ON "{schema}"."cp_workspace_squads"
                           (workspace_id)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_cp_agent_definitions_workspace
                           ON "{schema}"."cp_agent_definitions"
                           (workspace_id)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_cp_agent_definitions_squad
                           ON "{schema}"."cp_agent_definitions"
                           (squad_id)""",
                    f"""ALTER TABLE "{schema}"."cp_workspaces"
                           ADD COLUMN IF NOT EXISTS spec_json TEXT NOT NULL DEFAULT '{{}}'""",
                    f"""ALTER TABLE "{schema}"."cp_workspaces"
                           ADD COLUMN IF NOT EXISTS documents_json TEXT NOT NULL DEFAULT '{{}}'""",
                    f"""ALTER TABLE "{schema}"."cp_workspace_squads"
                           ADD COLUMN IF NOT EXISTS spec_json TEXT NOT NULL DEFAULT '{{}}'""",
                    f"""ALTER TABLE "{schema}"."cp_workspace_squads"
                           ADD COLUMN IF NOT EXISTS documents_json TEXT NOT NULL DEFAULT '{{}}'""",
                ),
            ),
            _Migration(
                "007_memory_state_tables",
                (
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."napkin_log" (
                            id BIGSERIAL PRIMARY KEY,
                            user_id BIGINT NOT NULL,
                            memory_type TEXT NOT NULL,
                            content TEXT NOT NULL,
                            source_query_id BIGINT,
                            session_id TEXT,
                            agent_id TEXT,
                            origin_kind TEXT DEFAULT 'conversation',
                            source_task_id BIGINT,
                            source_episode_id BIGINT,
                            project_key TEXT DEFAULT '',
                            environment TEXT DEFAULT '',
                            team TEXT DEFAULT '',
                            importance DOUBLE PRECISION DEFAULT 0.5,
                            quality_score DOUBLE PRECISION DEFAULT 0.5,
                            extraction_confidence DOUBLE PRECISION DEFAULT 0.5,
                            embedding_status TEXT DEFAULT 'pending',
                            content_hash TEXT,
                            claim_kind TEXT DEFAULT '',
                            subject TEXT DEFAULT '',
                            decision_source TEXT DEFAULT '',
                            evidence_refs_json TEXT DEFAULT '[]',
                            applicability_scope_json TEXT DEFAULT '{{}}',
                            valid_until TEXT,
                            conflict_key TEXT,
                            supersedes_memory_id BIGINT,
                            memory_status TEXT DEFAULT 'active',
                            retention_reason TEXT DEFAULT '',
                            embedding_attempts INTEGER DEFAULT 0,
                            embedding_last_error TEXT DEFAULT '',
                            embedding_retry_at TEXT,
                            access_count INTEGER DEFAULT 0,
                            last_accessed TEXT,
                            last_recalled_at TEXT,
                            created_at TEXT NOT NULL,
                            expires_at TEXT,
                            is_active INTEGER DEFAULT 1,
                            metadata_json TEXT DEFAULT '{{}}',
                            vector_ref_id TEXT
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_napkin_user_active
                           ON "{schema}"."napkin_log"
                           (user_id, is_active, importance DESC)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_napkin_expires
                           ON "{schema}"."napkin_log"
                           (expires_at)
                           WHERE is_active = 1""",
                    f"""CREATE INDEX IF NOT EXISTS idx_napkin_user_created
                           ON "{schema}"."napkin_log"
                           (user_id, created_at)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_napkin_agent_scope
                           ON "{schema}"."napkin_log"
                           (user_id, agent_id, project_key, environment, team, is_active)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_napkin_content_hash
                           ON "{schema}"."napkin_log"
                           (user_id, content_hash, is_active)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_napkin_conflict_key
                           ON "{schema}"."napkin_log"
                           (user_id, agent_id, conflict_key, memory_status, created_at DESC)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."memory_maintenance_log" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT DEFAULT 'default',
                            operation TEXT NOT NULL,
                            memories_affected INTEGER DEFAULT 0,
                            details TEXT,
                            executed_at TEXT NOT NULL
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_memory_maintenance_log_agent
                           ON "{schema}"."memory_maintenance_log"
                           (agent_id, executed_at DESC)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."memory_recall_audit" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT,
                            user_id BIGINT NOT NULL,
                            task_id BIGINT,
                            query_hash TEXT NOT NULL,
                            query_preview TEXT,
                            session_id TEXT,
                            project_key TEXT DEFAULT '',
                            environment TEXT DEFAULT '',
                            team TEXT DEFAULT '',
                            trust_score DOUBLE PRECISION DEFAULT 0.0,
                            total_considered INTEGER DEFAULT 0,
                            total_selected INTEGER DEFAULT 0,
                            total_discarded INTEGER DEFAULT 0,
                            conflict_group_count INTEGER DEFAULT 0,
                            considered_json TEXT DEFAULT '[]',
                            selected_json TEXT DEFAULT '[]',
                            discarded_json TEXT DEFAULT '[]',
                            conflicts_json TEXT DEFAULT '[]',
                            explanations_json TEXT DEFAULT '[]',
                            selected_layers_csv TEXT DEFAULT '',
                            retrieval_sources_csv TEXT DEFAULT '',
                            created_at TEXT NOT NULL
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_memory_recall_audit_lookup
                           ON "{schema}"."memory_recall_audit"
                           (user_id, agent_id, created_at DESC)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."memory_embedding_jobs" (
                            id BIGSERIAL PRIMARY KEY,
                            memory_id BIGINT NOT NULL,
                            agent_id TEXT,
                            status TEXT NOT NULL DEFAULT 'pending',
                            attempt_count INTEGER DEFAULT 0,
                            last_error TEXT DEFAULT '',
                            next_retry_at TEXT,
                            last_attempt_at TEXT,
                            claimed_at TEXT,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            UNIQUE (memory_id, agent_id)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_memory_embedding_jobs_status
                           ON "{schema}"."memory_embedding_jobs"
                           (status, next_retry_at, agent_id)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."memory_quality_counters" (
                            agent_id TEXT NOT NULL,
                            counter_key TEXT NOT NULL,
                            counter_value INTEGER DEFAULT 0,
                            updated_at TEXT NOT NULL,
                            PRIMARY KEY (agent_id, counter_key)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_memory_quality_counters_updated
                           ON "{schema}"."memory_quality_counters"
                           (agent_id, updated_at DESC)""",
                ),
            ),
            _Migration(
                "008_scheduler_state_tables",
                (
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."scheduled_jobs" (
                            id BIGSERIAL PRIMARY KEY,
                            user_id BIGINT NOT NULL,
                            chat_id BIGINT NOT NULL,
                            agent_id TEXT,
                            job_type TEXT NOT NULL,
                            trigger_type TEXT NOT NULL,
                            schedule_expr TEXT NOT NULL,
                            timezone TEXT NOT NULL DEFAULT 'UTC',
                            payload_json TEXT NOT NULL DEFAULT '{{}}',
                            status TEXT NOT NULL DEFAULT 'draft',
                            safety_mode TEXT NOT NULL DEFAULT 'dry_run_required',
                            dry_run_required INTEGER NOT NULL DEFAULT 1,
                            verification_policy_json TEXT NOT NULL DEFAULT '{{}}',
                            notification_policy_json TEXT NOT NULL DEFAULT '{{}}',
                            provider_preference TEXT,
                            model_preference TEXT,
                            work_dir TEXT,
                            next_run_at TEXT,
                            last_run_at TEXT,
                            last_success_at TEXT,
                            last_failure_at TEXT,
                            migration_source TEXT,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            UNIQUE (migration_source)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_user_status
                           ON "{schema}"."scheduled_jobs"
                           (user_id, status, next_run_at)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."scheduled_job_runs" (
                            id BIGSERIAL PRIMARY KEY,
                            scheduled_job_id BIGINT NOT NULL REFERENCES "{schema}"."scheduled_jobs"(id) ON DELETE CASCADE,
                            scheduled_for TEXT NOT NULL,
                            trigger_reason TEXT NOT NULL,
                            status TEXT NOT NULL DEFAULT 'queued',
                            attempt INTEGER NOT NULL DEFAULT 0,
                            max_attempts INTEGER NOT NULL DEFAULT 3,
                            lease_owner TEXT,
                            lease_expires_at TEXT,
                            next_attempt_at TEXT,
                            task_id BIGINT,
                            dlq_id BIGINT,
                            provider_effective TEXT,
                            model_effective TEXT,
                            verification_status TEXT NOT NULL DEFAULT 'pending',
                            notification_status TEXT NOT NULL DEFAULT 'pending',
                            summary_text TEXT,
                            metadata_json TEXT NOT NULL DEFAULT '{{}}',
                            started_at TEXT,
                            completed_at TEXT,
                            duration_ms DOUBLE PRECISION,
                            error_message TEXT,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            UNIQUE (scheduled_job_id, scheduled_for, trigger_reason)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_scheduled_job_runs_due
                           ON "{schema}"."scheduled_job_runs"
                           (status, next_attempt_at, lease_expires_at)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_scheduled_job_runs_job
                           ON "{schema}"."scheduled_job_runs"
                           (scheduled_job_id, scheduled_for DESC)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."dead_letter_queue" (
                            id BIGSERIAL PRIMARY KEY,
                            task_id BIGINT NOT NULL,
                            user_id BIGINT NOT NULL,
                            chat_id BIGINT NOT NULL,
                            agent_id TEXT,
                            pod_name TEXT,
                            query_text TEXT NOT NULL,
                            model TEXT,
                            error_message TEXT,
                            error_class TEXT,
                            attempt_count INTEGER NOT NULL DEFAULT 0,
                            original_created_at TEXT,
                            failed_at TEXT NOT NULL,
                            retry_eligible INTEGER NOT NULL DEFAULT 1,
                            retried_at TEXT,
                            metadata_json TEXT NOT NULL DEFAULT '{{}}'
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_dead_letter_queue_failed
                           ON "{schema}"."dead_letter_queue"
                           (agent_id, failed_at DESC)""",
                ),
            ),
            _Migration(
                "009_script_library_tables",
                (
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."script_library" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            user_id BIGINT NOT NULL,
                            title TEXT NOT NULL,
                            description TEXT,
                            language TEXT,
                            content TEXT NOT NULL,
                            source_query TEXT,
                            tags TEXT NOT NULL DEFAULT '[]',
                            use_count INTEGER NOT NULL DEFAULT 0,
                            last_used_at TEXT,
                            quality_score DOUBLE PRECISION NOT NULL DEFAULT 0.5,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            expires_at TEXT,
                            is_active BOOLEAN NOT NULL DEFAULT TRUE
                        )""",
                    f"""ALTER TABLE "{schema}"."script_library"
                           ADD COLUMN IF NOT EXISTS agent_id TEXT""",
                    f"""ALTER TABLE "{schema}"."script_library"
                           ADD COLUMN IF NOT EXISTS user_id BIGINT""",
                    f"""ALTER TABLE "{schema}"."script_library"
                           ADD COLUMN IF NOT EXISTS title TEXT""",
                    f"""ALTER TABLE "{schema}"."script_library"
                           ADD COLUMN IF NOT EXISTS description TEXT""",
                    f"""ALTER TABLE "{schema}"."script_library"
                           ADD COLUMN IF NOT EXISTS language TEXT""",
                    f"""ALTER TABLE "{schema}"."script_library"
                           ADD COLUMN IF NOT EXISTS content TEXT""",
                    f"""ALTER TABLE "{schema}"."script_library"
                           ADD COLUMN IF NOT EXISTS source_query TEXT""",
                    f"""ALTER TABLE "{schema}"."script_library"
                           ADD COLUMN IF NOT EXISTS tags TEXT DEFAULT '[]'""",
                    f"""ALTER TABLE "{schema}"."script_library"
                           ADD COLUMN IF NOT EXISTS use_count INTEGER DEFAULT 0""",
                    f"""ALTER TABLE "{schema}"."script_library"
                           ADD COLUMN IF NOT EXISTS last_used_at TEXT""",
                    f"""ALTER TABLE "{schema}"."script_library"
                           ADD COLUMN IF NOT EXISTS quality_score DOUBLE PRECISION DEFAULT 0.5""",
                    f"""ALTER TABLE "{schema}"."script_library"
                           ADD COLUMN IF NOT EXISTS created_at TEXT""",
                    f"""ALTER TABLE "{schema}"."script_library"
                           ADD COLUMN IF NOT EXISTS updated_at TEXT""",
                    f"""ALTER TABLE "{schema}"."script_library"
                           ADD COLUMN IF NOT EXISTS expires_at TEXT""",
                    f"""ALTER TABLE "{schema}"."script_library"
                           ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE""",
                    f"""CREATE INDEX IF NOT EXISTS idx_script_library_agent_user_active
                           ON "{schema}"."script_library"
                           (agent_id, user_id, is_active)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_script_library_agent_user_lang
                           ON "{schema}"."script_library"
                           (agent_id, user_id, language, is_active)""",
                ),
            ),
            _Migration(
                "010_response_cache_tables",
                (
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."response_cache" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT,
                            user_id BIGINT NOT NULL,
                            query_hash TEXT NOT NULL,
                            query_text TEXT NOT NULL,
                            response_text TEXT NOT NULL,
                            model TEXT,
                            cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            work_dir TEXT,
                            hit_count INTEGER NOT NULL DEFAULT 0,
                            last_hit_at TEXT,
                            created_at TEXT NOT NULL,
                            expires_at TEXT NOT NULL,
                            is_active BOOLEAN NOT NULL DEFAULT TRUE,
                            UNIQUE (user_id, query_hash)
                        )""",
                    f"""ALTER TABLE "{schema}"."response_cache"
                           ADD COLUMN IF NOT EXISTS agent_id TEXT""",
                    f"""CREATE INDEX IF NOT EXISTS idx_response_cache_hash_user
                           ON "{schema}"."response_cache"
                           (query_hash, user_id, agent_id, is_active)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_response_cache_expires
                           ON "{schema}"."response_cache"
                           (agent_id, expires_at, is_active)""",
                ),
            ),
            _Migration(
                "011_mcp_bridge_tables",
                (
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_mcp_server_catalog" (
                            server_key TEXT PRIMARY KEY,
                            display_name TEXT NOT NULL,
                            description TEXT NOT NULL DEFAULT '',
                            transport_type TEXT NOT NULL DEFAULT 'stdio',
                            command_json TEXT NOT NULL DEFAULT '[]',
                            url TEXT,
                            env_schema_json TEXT NOT NULL DEFAULT '[]',
                            documentation_url TEXT,
                            logo_key TEXT,
                            category TEXT NOT NULL DEFAULT 'general',
                            enabled INTEGER NOT NULL DEFAULT 1,
                            metadata_json TEXT NOT NULL DEFAULT '{{}}',
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_mcp_agent_connections" (
                            agent_id TEXT NOT NULL,
                            server_key TEXT NOT NULL,
                            enabled INTEGER NOT NULL DEFAULT 1,
                            transport_override TEXT,
                            command_override_json TEXT,
                            url_override TEXT,
                            env_values_json TEXT NOT NULL DEFAULT '{{}}',
                            last_connected_at TEXT,
                            last_error TEXT,
                            cached_tools_json TEXT,
                            cached_tools_at TEXT,
                            metadata_json TEXT NOT NULL DEFAULT '{{}}',
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            PRIMARY KEY (agent_id, server_key)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_cp_mcp_agent_connections_agent
                           ON "{schema}"."cp_mcp_agent_connections" (agent_id)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_mcp_discovered_tools" (
                            agent_id TEXT NOT NULL,
                            server_key TEXT NOT NULL,
                            tool_name TEXT NOT NULL,
                            description TEXT NOT NULL DEFAULT '',
                            input_schema_json TEXT NOT NULL DEFAULT '{{}}',
                            annotations_json TEXT NOT NULL DEFAULT '{{}}',
                            risk_level TEXT NOT NULL DEFAULT 'read',
                            schema_hash TEXT NOT NULL DEFAULT '',
                            discovered_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            PRIMARY KEY (agent_id, server_key, tool_name)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_cp_mcp_discovered_tools_lookup
                           ON "{schema}"."cp_mcp_discovered_tools" (agent_id, server_key)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_mcp_tool_policies" (
                            agent_id TEXT NOT NULL,
                            server_key TEXT NOT NULL,
                            tool_name TEXT NOT NULL,
                            policy TEXT NOT NULL DEFAULT 'auto',
                            updated_at TEXT NOT NULL,
                            PRIMARY KEY (agent_id, server_key, tool_name)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_cp_mcp_tool_policies_lookup
                           ON "{schema}"."cp_mcp_tool_policies" (agent_id, server_key)""",
                ),
            ),
            _Migration(
                "012_mcp_oauth_support",
                (
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_mcp_oauth_provider_configs" (
                            server_key TEXT PRIMARY KEY,
                            oauth_enabled INTEGER NOT NULL DEFAULT 0,
                            authorization_url TEXT NOT NULL,
                            token_url TEXT NOT NULL,
                            client_id TEXT NOT NULL,
                            client_secret_encrypted TEXT NOT NULL,
                            scopes TEXT NOT NULL DEFAULT '',
                            pkce_required INTEGER NOT NULL DEFAULT 0,
                            token_env_mapping_json TEXT NOT NULL DEFAULT '{{}}',
                            extra_auth_params_json TEXT NOT NULL DEFAULT '{{}}',
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_mcp_oauth_tokens" (
                            agent_id TEXT NOT NULL,
                            server_key TEXT NOT NULL,
                            access_token_encrypted TEXT,
                            refresh_token_encrypted TEXT,
                            token_type TEXT DEFAULT 'Bearer',
                            expires_at TIMESTAMPTZ,
                            scopes_granted TEXT DEFAULT '',
                            provider_account_id TEXT,
                            provider_account_label TEXT,
                            last_refreshed_at TIMESTAMPTZ,
                            last_error TEXT,
                            oauth_context_json TEXT NOT NULL DEFAULT '{{}}',
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            PRIMARY KEY (agent_id, server_key)
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_mcp_oauth_sessions" (
                            session_id TEXT PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            server_key TEXT NOT NULL,
                            state_param TEXT NOT NULL,
                            code_verifier TEXT,
                            redirect_uri TEXT NOT NULL,
                            frontend_callback_uri TEXT NOT NULL DEFAULT '',
                            oauth_context_json TEXT NOT NULL DEFAULT '{{}}',
                            status TEXT NOT NULL DEFAULT 'pending',
                            error_message TEXT,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            expires_at TIMESTAMPTZ NOT NULL
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_cp_mcp_oauth_sessions_state
                           ON "{schema}"."cp_mcp_oauth_sessions" (state_param)""",
                    f"""ALTER TABLE "{schema}"."cp_mcp_agent_connections"
                           ADD COLUMN IF NOT EXISTS auth_method TEXT NOT NULL DEFAULT 'manual'""",
                    f"""ALTER TABLE "{schema}"."cp_mcp_server_catalog"
                           ADD COLUMN IF NOT EXISTS oauth_enabled INTEGER NOT NULL DEFAULT 0""",
                    f"""ALTER TABLE "{schema}"."cp_mcp_server_catalog"
                           ADD COLUMN IF NOT EXISTS transport_kind TEXT NOT NULL DEFAULT 'local'""",
                    f"""ALTER TABLE "{schema}"."cp_mcp_server_catalog"
                           ADD COLUMN IF NOT EXISTS auth_strategy TEXT NOT NULL DEFAULT 'no_auth'""",
                    f"""ALTER TABLE "{schema}"."cp_mcp_server_catalog"
                           ADD COLUMN IF NOT EXISTS official_support_level TEXT NOT NULL DEFAULT 'community_manual'""",
                    f"""ALTER TABLE "{schema}"."cp_mcp_server_catalog"
                           ADD COLUMN IF NOT EXISTS oauth_mode TEXT NOT NULL DEFAULT 'none'""",
                    f"""ALTER TABLE "{schema}"."cp_mcp_server_catalog"
                           ADD COLUMN IF NOT EXISTS oauth_metadata_url TEXT""",
                    f"""ALTER TABLE "{schema}"."cp_mcp_server_catalog"
                           ADD COLUMN IF NOT EXISTS remote_url TEXT""",
                    f"""ALTER TABLE "{schema}"."cp_mcp_server_catalog"
                           ADD COLUMN IF NOT EXISTS headers_schema_json TEXT NOT NULL DEFAULT '[]'""",
                    f"""ALTER TABLE "{schema}"."cp_mcp_server_catalog"
                           ADD COLUMN IF NOT EXISTS tool_discovery_mode TEXT NOT NULL DEFAULT 'runtime'""",
                    f"""ALTER TABLE "{schema}"."cp_mcp_server_catalog"
                           ADD COLUMN IF NOT EXISTS vendor_notes TEXT NOT NULL DEFAULT ''""",
                    f"""ALTER TABLE "{schema}"."cp_mcp_server_catalog"
                           ADD COLUMN IF NOT EXISTS default_policy TEXT NOT NULL DEFAULT 'always_ask'""",
                    f"""ALTER TABLE "{schema}"."cp_mcp_oauth_sessions"
                           ADD COLUMN IF NOT EXISTS frontend_callback_uri TEXT NOT NULL DEFAULT ''""",
                    f"""ALTER TABLE "{schema}"."cp_mcp_oauth_sessions"
                           ADD COLUMN IF NOT EXISTS oauth_context_json TEXT NOT NULL DEFAULT '{{}}'""",
                    f"""ALTER TABLE "{schema}"."cp_mcp_oauth_sessions"
                           ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()""",
                    f"""ALTER TABLE "{schema}"."cp_mcp_oauth_tokens"
                           ADD COLUMN IF NOT EXISTS oauth_context_json TEXT NOT NULL DEFAULT '{{}}'""",
                ),
            ),
            _Migration(
                "013_connection_discovery_history",
                (
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_connection_discovery_runs" (
                            run_id TEXT PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            connection_key TEXT NOT NULL,
                            status TEXT NOT NULL DEFAULT 'succeeded',
                            tool_count INTEGER NOT NULL DEFAULT 0,
                            diff_json TEXT NOT NULL DEFAULT '{{}}',
                            error TEXT NOT NULL DEFAULT '',
                            discovered_at TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_cp_connection_discovery_runs_lookup
                           ON "{schema}"."cp_connection_discovery_runs" (agent_id, connection_key, discovered_at DESC)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_connection_discovery_run_tools" (
                            run_id TEXT NOT NULL,
                            tool_name TEXT NOT NULL,
                            description TEXT NOT NULL DEFAULT '',
                            input_schema_json TEXT NOT NULL DEFAULT '{{}}',
                            annotations_json TEXT NOT NULL DEFAULT '{{}}',
                            risk_level TEXT NOT NULL DEFAULT 'read',
                            signature_hash TEXT NOT NULL DEFAULT '',
                            created_at TEXT NOT NULL,
                            PRIMARY KEY (run_id, tool_name)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_cp_connection_discovery_run_tools_lookup
                           ON "{schema}"."cp_connection_discovery_run_tools" (run_id)""",
                ),
            ),
            _Migration(
                "015_operator_auth",
                (
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_operator_users" (
                            id TEXT PRIMARY KEY,
                            username TEXT NOT NULL UNIQUE,
                            email TEXT NOT NULL UNIQUE,
                            display_name TEXT NOT NULL DEFAULT '',
                            password_hash TEXT NOT NULL,
                            role TEXT NOT NULL DEFAULT 'owner',
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            last_login_at TEXT NOT NULL DEFAULT '',
                            failed_login_attempts INTEGER NOT NULL DEFAULT 0,
                            locked_until TEXT NOT NULL DEFAULT '',
                            disabled INTEGER NOT NULL DEFAULT 0
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_cp_operator_users_lookup
                           ON "{schema}"."cp_operator_users" (lower(username), lower(email))""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_operator_sessions" (
                            session_id TEXT PRIMARY KEY,
                            user_id TEXT,
                            token_hash TEXT NOT NULL UNIQUE,
                            subject_type TEXT NOT NULL DEFAULT 'operator',
                            label TEXT NOT NULL DEFAULT '',
                            created_at TEXT NOT NULL,
                            last_used_at TEXT NOT NULL,
                            expires_at TEXT NOT NULL,
                            revoked_at TEXT NOT NULL DEFAULT '',
                            metadata_json TEXT NOT NULL DEFAULT '{{}}'
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_cp_operator_sessions_lookup
                           ON "{schema}"."cp_operator_sessions" (user_id, revoked_at, expires_at)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_operator_tokens" (
                            id TEXT PRIMARY KEY,
                            user_id TEXT NOT NULL,
                            token_name TEXT NOT NULL DEFAULT '',
                            token_hash TEXT NOT NULL UNIQUE,
                            token_prefix TEXT NOT NULL DEFAULT '',
                            scopes_json TEXT NOT NULL DEFAULT '[]',
                            created_at TEXT NOT NULL,
                            last_used_at TEXT NOT NULL DEFAULT '',
                            expires_at TEXT NOT NULL DEFAULT '',
                            revoked_at TEXT NOT NULL DEFAULT '',
                            metadata_json TEXT NOT NULL DEFAULT '{{}}'
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_cp_operator_tokens_lookup
                           ON "{schema}"."cp_operator_tokens" (user_id, revoked_at, expires_at)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_bootstrap_codes" (
                            id TEXT PRIMARY KEY,
                            code_hash TEXT NOT NULL UNIQUE,
                            code_hint TEXT NOT NULL DEFAULT '',
                            purpose TEXT NOT NULL DEFAULT 'owner_setup',
                            created_at TEXT NOT NULL,
                            expires_at TEXT NOT NULL,
                            consumed_at TEXT NOT NULL DEFAULT '',
                            exchange_token_hash TEXT NOT NULL DEFAULT '',
                            exchange_issued_at TEXT NOT NULL DEFAULT '',
                            exchange_expires_at TEXT NOT NULL DEFAULT '',
                            exchange_consumed_at TEXT NOT NULL DEFAULT '',
                            issued_by TEXT NOT NULL DEFAULT '',
                            metadata_json TEXT NOT NULL DEFAULT '{{}}'
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_cp_bootstrap_codes_expiry
                           ON "{schema}"."cp_bootstrap_codes" (expires_at, exchange_expires_at)""",
                ),
            ),
            _Migration(
                "016_agent_core_connections",
                (
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_connection_defaults" (
                            connection_key TEXT PRIMARY KEY,
                            kind TEXT NOT NULL DEFAULT 'core',
                            integration_key TEXT NOT NULL,
                            auth_method TEXT NOT NULL DEFAULT 'none',
                            configured INTEGER NOT NULL DEFAULT 0,
                            verified INTEGER NOT NULL DEFAULT 0,
                            account_label TEXT NOT NULL DEFAULT '',
                            provider_account_id TEXT NOT NULL DEFAULT '',
                            expires_at TEXT NOT NULL DEFAULT '',
                            source_origin TEXT NOT NULL DEFAULT 'system_default',
                            last_verified_at TEXT NOT NULL DEFAULT '',
                            last_error TEXT NOT NULL DEFAULT '',
                            auth_expired INTEGER NOT NULL DEFAULT 0,
                            checked_via TEXT NOT NULL DEFAULT '',
                            metadata_json TEXT NOT NULL DEFAULT '{{}}',
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_cp_connection_defaults_lookup
                           ON "{schema}"."cp_connection_defaults" (kind, integration_key, updated_at DESC)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_agent_connections" (
                            agent_id TEXT NOT NULL,
                            connection_key TEXT NOT NULL,
                            kind TEXT NOT NULL,
                            integration_key TEXT NOT NULL,
                            auth_method TEXT NOT NULL DEFAULT 'none',
                            source_origin TEXT NOT NULL DEFAULT 'agent_binding',
                            enabled INTEGER NOT NULL DEFAULT 1,
                            configured INTEGER NOT NULL DEFAULT 0,
                            verified INTEGER NOT NULL DEFAULT 0,
                            account_label TEXT NOT NULL DEFAULT '',
                            provider_account_id TEXT NOT NULL DEFAULT '',
                            expires_at TEXT NOT NULL DEFAULT '',
                            last_verified_at TEXT NOT NULL DEFAULT '',
                            last_error TEXT NOT NULL DEFAULT '',
                            auth_expired INTEGER NOT NULL DEFAULT 0,
                            checked_via TEXT NOT NULL DEFAULT '',
                            config_json TEXT NOT NULL DEFAULT '{{}}',
                            metadata_json TEXT NOT NULL DEFAULT '{{}}',
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            PRIMARY KEY (agent_id, connection_key)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_cp_agent_connections_lookup
                           ON "{schema}"."cp_agent_connections" (agent_id, kind, integration_key, updated_at DESC)""",
                ),
            ),
            _Migration(
                "017_drop_legacy_integration_connections",
                (
                    f"""
                    DO $$
                    BEGIN
                        IF EXISTS (
                            SELECT 1
                            FROM information_schema.tables
                            WHERE table_schema = '{schema}'
                              AND table_name = 'cp_integration_connections'
                        ) THEN
                            INSERT INTO "{schema}"."cp_connection_defaults" (
                                connection_key,
                                kind,
                                integration_key,
                                auth_method,
                                configured,
                                verified,
                                account_label,
                                provider_account_id,
                                expires_at,
                                source_origin,
                                last_verified_at,
                                last_error,
                                auth_expired,
                                checked_via,
                                metadata_json,
                                created_at,
                                updated_at
                            )
                            SELECT
                                'core:' || integration_id,
                                'core',
                                integration_id,
                                auth_mode,
                                configured,
                                verified,
                                account_label,
                                COALESCE(metadata_json::jsonb ->> 'provider_account_id', ''),
                                COALESCE(metadata_json::jsonb ->> 'expires_at', ''),
                                'system_default',
                                last_verified_at,
                                last_error,
                                auth_expired,
                                checked_via,
                                metadata_json,
                                created_at,
                                updated_at
                            FROM "{schema}"."cp_integration_connections"
                            ON CONFLICT (connection_key) DO UPDATE SET
                                auth_method = EXCLUDED.auth_method,
                                configured = EXCLUDED.configured,
                                verified = EXCLUDED.verified,
                                account_label = EXCLUDED.account_label,
                                provider_account_id = EXCLUDED.provider_account_id,
                                expires_at = EXCLUDED.expires_at,
                                source_origin = EXCLUDED.source_origin,
                                last_verified_at = EXCLUDED.last_verified_at,
                                last_error = EXCLUDED.last_error,
                                auth_expired = EXCLUDED.auth_expired,
                                checked_via = EXCLUDED.checked_via,
                                metadata_json = EXCLUDED.metadata_json,
                                updated_at = EXCLUDED.updated_at;

                            DROP TABLE "{schema}"."cp_integration_connections";
                        END IF;
                    END
                    $$;
                    """,
                ),
            ),
            _Migration(
                "018_operator_recovery_codes",
                (
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_operator_recovery_codes" (
                            id TEXT PRIMARY KEY,
                            user_id TEXT NOT NULL,
                            code_hash TEXT NOT NULL,
                            code_hint TEXT NOT NULL DEFAULT '',
                            created_at TEXT NOT NULL,
                            consumed_at TEXT NOT NULL DEFAULT '',
                            consumed_reason TEXT NOT NULL DEFAULT '',
                            generation TEXT NOT NULL DEFAULT ''
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_cp_operator_recovery_codes_user
                           ON "{schema}"."cp_operator_recovery_codes" (user_id, consumed_at)""",
                    f"""CREATE UNIQUE INDEX IF NOT EXISTS idx_cp_operator_recovery_codes_hash
                           ON "{schema}"."cp_operator_recovery_codes" (code_hash)""",
                    f"""ALTER TABLE "{schema}"."cp_operator_users"
                           ADD COLUMN IF NOT EXISTS totp_secret TEXT NOT NULL DEFAULT ''""",
                    f"""ALTER TABLE "{schema}"."cp_operator_users"
                           ADD COLUMN IF NOT EXISTS recovery_generation TEXT NOT NULL DEFAULT ''""",
                ),
            ),
            _Migration(
                "019a_runtime_queue_items_payload_columns",
                (
                    f"""ALTER TABLE "{schema}"."runtime_queue_items"
                           ADD COLUMN IF NOT EXISTS payload_json TEXT NOT NULL DEFAULT '{{}}'""",
                    f"""ALTER TABLE "{schema}"."runtime_queue_items"
                           ADD COLUMN IF NOT EXISTS recovery_count INTEGER NOT NULL DEFAULT 0""",
                    f"""ALTER TABLE "{schema}"."runtime_queue_items"
                           ADD COLUMN IF NOT EXISTS last_recovered_at TEXT""",
                    f"""ALTER TABLE "{schema}"."runtime_queue_items"
                           ADD COLUMN IF NOT EXISTS source_kind TEXT NOT NULL DEFAULT 'user'""",
                    f"""ALTER TABLE "{schema}"."runtime_queue_items"
                           ADD COLUMN IF NOT EXISTS last_error TEXT""",
                ),
            ),
            _Migration(
                "019b_scheduled_job_runs_lease_recovery_columns",
                (
                    # Added when scheduled_job_dispatcher started recovering
                    # expired leases. Without these columns the recovery query
                    # crashes the runtime on boot and the supervisor enters a
                    # restart loop, never delivering user messages.
                    f"""ALTER TABLE "{schema}"."scheduled_job_runs"
                           ADD COLUMN IF NOT EXISTS lease_recovery_count INTEGER NOT NULL DEFAULT 0""",
                    f"""ALTER TABLE "{schema}"."scheduled_job_runs"
                           ADD COLUMN IF NOT EXISTS last_recovered_at TEXT""",
                    f"""ALTER TABLE "{schema}"."scheduled_job_runs"
                           ADD COLUMN IF NOT EXISTS trace_id TEXT""",
                ),
            ),
            _Migration(
                "019c_provider_session_map",
                (
                    # Maps koda's canonical session id ↔ provider-native session
                    # id (Claude/Codex/Gemini resume tokens). Used by the
                    # llm_runner fallback chain and by history_store when the
                    # operator switches providers mid-conversation. Missing
                    # this table causes "relation does not exist" the moment
                    # the agent tries to persist its first turn.
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."provider_session_map" (
                            canonical_session_id TEXT NOT NULL,
                            provider TEXT NOT NULL,
                            provider_session_id TEXT NOT NULL,
                            last_model TEXT,
                            last_used TEXT NOT NULL,
                            PRIMARY KEY (canonical_session_id, provider)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_provider_session_map_last_used
                           ON "{schema}"."provider_session_map" (last_used DESC)""",
                ),
            ),
            _Migration(
                "019d_sessions_table",
                (
                    # Per-user conversation sessions tracked by history_store.
                    # The worker logs every user-initiated turn as a row here so
                    # /sessions can list past conversations and the LLM runner
                    # can resume the right provider-native session id. Missing
                    # this table makes the first message of every user fail
                    # with "relation 'sessions' does not exist".
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."sessions" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL DEFAULT 'KODA',
                            user_id BIGINT NOT NULL,
                            session_id TEXT NOT NULL,
                            name TEXT,
                            provider TEXT NOT NULL,
                            provider_session_id TEXT,
                            last_model TEXT,
                            created_at TEXT NOT NULL,
                            last_used TEXT NOT NULL,
                            UNIQUE (user_id, session_id)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_sessions_user_last_used
                           ON "{schema}"."sessions" (user_id, last_used DESC)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_sessions_agent_last_used
                           ON "{schema}"."sessions" (agent_id, last_used DESC)""",
                ),
            ),
            _Migration(
                "019e_scheduled_jobs_policy_snapshot_columns",
                (
                    # Added when the scheduler began capturing a policy
                    # snapshot for every job (model_policy + tool_policy at
                    # creation time, hashed for change detection) and a
                    # `config_version` for idempotent updates. Without these
                    # columns the INSERT in scheduled_jobs.create_job fails
                    # silently inside the LLM turn pipeline and the agent
                    # stops responding to user messages.
                    f"""ALTER TABLE "{schema}"."scheduled_jobs"
                           ADD COLUMN IF NOT EXISTS policy_snapshot_json TEXT NOT NULL DEFAULT '{{}}'""",
                    f"""ALTER TABLE "{schema}"."scheduled_jobs"
                           ADD COLUMN IF NOT EXISTS policy_snapshot_hash TEXT NOT NULL DEFAULT ''""",
                    f"""ALTER TABLE "{schema}"."scheduled_jobs"
                           ADD COLUMN IF NOT EXISTS config_version INTEGER NOT NULL DEFAULT 1""",
                ),
            ),
            _Migration(
                "019_knowledge_governance_tables",
                (
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."knowledge_candidates" (
                            id BIGSERIAL PRIMARY KEY,
                            candidate_key TEXT NOT NULL UNIQUE,
                            merge_key TEXT,
                            agent_id TEXT,
                            task_id BIGINT,
                            task_kind TEXT NOT NULL DEFAULT '',
                            candidate_type TEXT NOT NULL DEFAULT '',
                            summary TEXT NOT NULL DEFAULT '',
                            evidence_json TEXT NOT NULL DEFAULT '[]',
                            source_refs_json TEXT NOT NULL DEFAULT '[]',
                            proposed_runbook_json TEXT NOT NULL DEFAULT '{{}}',
                            confidence_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            review_status TEXT NOT NULL DEFAULT 'learning',
                            reviewer TEXT NOT NULL DEFAULT '',
                            reviewed_at TEXT,
                            diff_summary TEXT NOT NULL DEFAULT '',
                            review_note TEXT NOT NULL DEFAULT '',
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            project_key TEXT NOT NULL DEFAULT '',
                            environment TEXT NOT NULL DEFAULT '',
                            team TEXT NOT NULL DEFAULT '',
                            support_count INTEGER NOT NULL DEFAULT 0,
                            success_count INTEGER NOT NULL DEFAULT 0,
                            failure_count INTEGER NOT NULL DEFAULT 0,
                            verification_count INTEGER NOT NULL DEFAULT 0,
                            promoted_runbook_id BIGINT,
                            last_human_feedback_at TEXT,
                            last_promoted_version TEXT
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_knowledge_candidates_review
                           ON "{schema}"."knowledge_candidates"
                           (review_status, agent_id, updated_at DESC)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_knowledge_candidates_merge
                           ON "{schema}"."knowledge_candidates"
                           (merge_key)
                           WHERE merge_key IS NOT NULL""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."approved_runbooks" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT,
                            runbook_key TEXT NOT NULL,
                            version TEXT NOT NULL DEFAULT '',
                            title TEXT NOT NULL DEFAULT '',
                            task_kind TEXT NOT NULL DEFAULT '',
                            summary TEXT NOT NULL DEFAULT '',
                            prerequisites_json TEXT NOT NULL DEFAULT '[]',
                            steps_json TEXT NOT NULL DEFAULT '[]',
                            verification_json TEXT NOT NULL DEFAULT '[]',
                            rollback TEXT NOT NULL DEFAULT '',
                            source_refs_json TEXT NOT NULL DEFAULT '[]',
                            project_key TEXT NOT NULL DEFAULT '',
                            environment TEXT NOT NULL DEFAULT '',
                            team TEXT NOT NULL DEFAULT '',
                            owner TEXT NOT NULL DEFAULT '',
                            approved_by TEXT NOT NULL DEFAULT '',
                            approved_at TEXT NOT NULL,
                            last_validated_by TEXT NOT NULL DEFAULT '',
                            last_validated_at TEXT,
                            status TEXT NOT NULL DEFAULT 'approved',
                            lifecycle_status TEXT NOT NULL DEFAULT 'approved',
                            valid_from TEXT,
                            valid_until TEXT,
                            rollout_scope_json TEXT NOT NULL DEFAULT '{{}}',
                            policy_overrides_json TEXT NOT NULL DEFAULT '{{}}',
                            supersedes_runbook_id BIGINT,
                            source_candidate_id BIGINT
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_approved_runbooks_lookup
                           ON "{schema}"."approved_runbooks"
                           (agent_id, status, lifecycle_status, task_kind, approved_at DESC)""",
                    f"""CREATE UNIQUE INDEX IF NOT EXISTS idx_approved_runbooks_key
                           ON "{schema}"."approved_runbooks"
                           (agent_id, runbook_key, version)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."approved_guardrails" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT,
                            task_kind TEXT NOT NULL DEFAULT '',
                            title TEXT NOT NULL DEFAULT '',
                            severity TEXT NOT NULL DEFAULT '',
                            reason TEXT NOT NULL DEFAULT '',
                            source_label TEXT NOT NULL DEFAULT '',
                            source_path TEXT NOT NULL DEFAULT '',
                            project_key TEXT NOT NULL DEFAULT '',
                            environment TEXT NOT NULL DEFAULT '',
                            team TEXT NOT NULL DEFAULT '',
                            owner TEXT NOT NULL DEFAULT '',
                            status TEXT NOT NULL DEFAULT 'active',
                            source_candidate_id BIGINT,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_approved_guardrails_lookup
                           ON "{schema}"."approved_guardrails"
                           (agent_id, status, task_kind, updated_at DESC)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."knowledge_source_registry" (
                            id BIGSERIAL PRIMARY KEY,
                            source_key TEXT NOT NULL UNIQUE,
                            agent_id TEXT,
                            project_key TEXT NOT NULL DEFAULT '',
                            source_type TEXT NOT NULL DEFAULT '',
                            layer TEXT NOT NULL DEFAULT '',
                            source_label TEXT NOT NULL DEFAULT '',
                            source_path TEXT NOT NULL DEFAULT '',
                            owner TEXT NOT NULL DEFAULT '',
                            freshness_days INTEGER NOT NULL DEFAULT 0,
                            content_hash TEXT NOT NULL DEFAULT '',
                            status TEXT NOT NULL DEFAULT '',
                            is_canonical BOOLEAN NOT NULL DEFAULT FALSE,
                            updated_at TEXT NOT NULL,
                            last_synced_at TEXT,
                            stale_after TEXT,
                            invalid_after TEXT,
                            sla_hours INTEGER NOT NULL DEFAULT 0,
                            sync_mode TEXT NOT NULL DEFAULT '',
                            last_success_at TEXT,
                            last_error TEXT NOT NULL DEFAULT '',
                            workspace_fingerprint TEXT NOT NULL DEFAULT ''
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_knowledge_source_registry_lookup
                           ON "{schema}"."knowledge_source_registry"
                           (agent_id, status, is_canonical, updated_at DESC)""",
                ),
            ),
            _Migration(
                "020_telegram_offsets",
                (
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_telegram_offsets" (
                            agent_id TEXT PRIMARY KEY,
                            last_update_id BIGINT NOT NULL DEFAULT 0,
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )""",
                ),
            ),
            _Migration(
                "021_bot_gateway",
                (
                    # Token registry — one row per agent. The bot-gateway
                    # service polls Telegram on behalf of every registered
                    # bot. ``bot_token`` is treated as a secret; gateway
                    # logs redact it via the koda-security-core helpers.
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_bot_gateway_tokens" (
                            agent_id TEXT PRIMARY KEY,
                            bot_token TEXT NOT NULL,
                            registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )""",
                    # Durable per-agent queue. Gateway INSERTs each Update
                    # before advancing Telegram's polling offset, so a
                    # restart never loses messages. Subscribers consume
                    # rows in order and DELETE them via AcknowledgeUpdate
                    # to confirm processing (at-least-once delivery).
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_telegram_pending_updates" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            update_id BIGINT NOT NULL,
                            payload_json JSONB NOT NULL,
                            queued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE (agent_id, update_id)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_telegram_pending_updates_lookup
                           ON "{schema}"."cp_telegram_pending_updates"
                           (agent_id, queued_at, id)""",
                ),
            ),
            _Migration(
                "022_policy_engine",
                (
                    # Per-workspace policy: rate, concurrency and spend caps.
                    # ``enabled=false`` makes the policy-engine a no-op for that
                    # workspace (used by single-tenant deployments that don't
                    # care about isolation yet).
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_policy" (
                            workspace_id TEXT PRIMARY KEY,
                            max_concurrent_agents INTEGER NOT NULL DEFAULT 0,
                            max_messages_per_minute INTEGER NOT NULL DEFAULT 0,
                            monthly_llm_spend_usd_cap DOUBLE PRECISION NOT NULL DEFAULT 0,
                            spend_warning_fraction DOUBLE PRECISION NOT NULL DEFAULT 0.8,
                            enabled BOOLEAN NOT NULL DEFAULT TRUE,
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )""",
                    # Append-only ledger of LLM spend. Aggregated lazily into
                    # ``cp_policy_spend_window`` for fast cap decisions.
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_policy_spend_ledger" (
                            id BIGSERIAL PRIMARY KEY,
                            workspace_id TEXT NOT NULL,
                            agent_id TEXT NOT NULL,
                            cost_usd DOUBLE PRECISION NOT NULL,
                            provider TEXT NOT NULL DEFAULT '',
                            model TEXT NOT NULL DEFAULT '',
                            recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_policy_spend_lookup
                           ON "{schema}"."cp_policy_spend_ledger"
                           (workspace_id, recorded_at DESC)""",
                    # Running monthly spend per workspace. Updated atomically
                    # by RecordSpend so the hard-stop decision is sub-ms.
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_policy_spend_window" (
                            workspace_id TEXT PRIMARY KEY,
                            window_start TIMESTAMPTZ NOT NULL,
                            spent_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )""",
                ),
            ),
            _Migration(
                "023_mcp_resources_prompts_custom",
                (
                    # Per-agent user-defined MCP servers (custom JSON paste / form).
                    # System-wide custom rows live in cp_mcp_server_catalog with
                    # is_custom=1; per-agent variants live here.
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_mcp_user_servers" (
                            server_key TEXT NOT NULL,
                            agent_id TEXT NOT NULL,
                            owner_user_id TEXT,
                            display_name TEXT NOT NULL,
                            description TEXT NOT NULL DEFAULT '',
                            transport_type TEXT NOT NULL DEFAULT 'stdio',
                            command_json TEXT NOT NULL DEFAULT '[]',
                            args_json TEXT NOT NULL DEFAULT '[]',
                            url TEXT,
                            headers_schema_json TEXT NOT NULL DEFAULT '[]',
                            env_schema_json TEXT NOT NULL DEFAULT '[]',
                            auth_strategy TEXT NOT NULL DEFAULT 'no_auth',
                            oauth_config_json TEXT NOT NULL DEFAULT '{{}}',
                            isolation_profile TEXT NOT NULL DEFAULT 'auto',
                            isolation_constraints_json TEXT NOT NULL DEFAULT '{{}}',
                            runtime_constraints_json TEXT NOT NULL DEFAULT '[]',
                            source TEXT NOT NULL DEFAULT 'manual',
                            metadata_json TEXT NOT NULL DEFAULT '{{}}',
                            validation_signature TEXT,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            PRIMARY KEY (server_key, agent_id)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_cp_mcp_user_servers_agent
                           ON "{schema}"."cp_mcp_user_servers" (agent_id)""",
                    # Capability snapshot cache (initialize + tools/list +
                    # resources/list + prompts/list). One row per
                    # (agent_id, server_key); refreshed on demand.
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_mcp_capability_snapshots" (
                            agent_id TEXT NOT NULL,
                            server_key TEXT NOT NULL,
                            server_info_json TEXT NOT NULL DEFAULT '{{}}',
                            server_capabilities_json TEXT NOT NULL DEFAULT '{{}}',
                            tools_json TEXT NOT NULL DEFAULT '[]',
                            resources_json TEXT NOT NULL DEFAULT '[]',
                            resource_templates_json TEXT NOT NULL DEFAULT '[]',
                            prompts_json TEXT NOT NULL DEFAULT '[]',
                            captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            ttl_seconds INTEGER NOT NULL DEFAULT 3600,
                            error TEXT,
                            PRIMARY KEY (agent_id, server_key)
                        )""",
                    # Discovered resources (data sources exposed by MCP server).
                    # uri_hash is sha256(uri) — used as PK component to keep
                    # the key short for long URIs.
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_mcp_discovered_resources" (
                            agent_id TEXT NOT NULL,
                            server_key TEXT NOT NULL,
                            uri_hash TEXT NOT NULL,
                            uri TEXT NOT NULL,
                            name TEXT,
                            description TEXT,
                            mime_type TEXT,
                            is_template INTEGER NOT NULL DEFAULT 0,
                            annotations_json TEXT NOT NULL DEFAULT '{{}}',
                            schema_hash TEXT NOT NULL DEFAULT '',
                            discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            PRIMARY KEY (agent_id, server_key, uri_hash)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_cp_mcp_discovered_resources_lookup
                           ON "{schema}"."cp_mcp_discovered_resources" (agent_id, server_key)""",
                    # Discovered prompts (reusable prompt templates exposed by MCP).
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_mcp_discovered_prompts" (
                            agent_id TEXT NOT NULL,
                            server_key TEXT NOT NULL,
                            prompt_name TEXT NOT NULL,
                            description TEXT,
                            arguments_json TEXT NOT NULL DEFAULT '[]',
                            schema_hash TEXT NOT NULL DEFAULT '',
                            discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            PRIMARY KEY (agent_id, server_key, prompt_name)
                        )""",
                    # Unified per-capability policy table. Replaces the
                    # tools-only cp_mcp_tool_policies; capability_kind
                    # discriminates between tool / resource / prompt rows.
                    # The legacy table stays untouched until a future cleanup.
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_mcp_capability_policies" (
                            agent_id TEXT NOT NULL,
                            server_key TEXT NOT NULL,
                            capability_kind TEXT NOT NULL,
                            capability_name TEXT NOT NULL,
                            policy TEXT NOT NULL DEFAULT 'auto',
                            exposure_mode TEXT,
                            metadata_json TEXT NOT NULL DEFAULT '{{}}',
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            PRIMARY KEY (agent_id, server_key, capability_kind, capability_name)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_cp_mcp_capability_policies_lookup
                           ON "{schema}"."cp_mcp_capability_policies"
                           (agent_id, server_key, capability_kind)""",
                    # Backfill: copy existing tool policies into the new table
                    # so reads can transition without losing state. Idempotent
                    # via ON CONFLICT DO NOTHING.
                    f"""INSERT INTO "{schema}"."cp_mcp_capability_policies"
                           (agent_id, server_key, capability_kind, capability_name, policy, updated_at)
                           SELECT agent_id, server_key, 'tool', tool_name, policy, updated_at::timestamptz
                           FROM "{schema}"."cp_mcp_tool_policies"
                           ON CONFLICT DO NOTHING""",
                    # ALTERs on cp_mcp_server_catalog for custom servers + isolation +
                    # runtime token placement (where the OAuth/api_key token goes
                    # at runtime: env var, auth header, or url param).
                    f"""ALTER TABLE "{schema}"."cp_mcp_server_catalog"
                           ADD COLUMN IF NOT EXISTS is_custom INTEGER NOT NULL DEFAULT 0""",
                    f"""ALTER TABLE "{schema}"."cp_mcp_server_catalog"
                           ADD COLUMN IF NOT EXISTS isolation_profile TEXT NOT NULL DEFAULT 'auto'""",
                    f"""ALTER TABLE "{schema}"."cp_mcp_server_catalog"
                           ADD COLUMN IF NOT EXISTS isolation_constraints_json TEXT NOT NULL DEFAULT '{{}}'""",
                    f"""ALTER TABLE "{schema}"."cp_mcp_server_catalog"
                           ADD COLUMN IF NOT EXISTS runtime_token_placement TEXT NOT NULL DEFAULT 'env_var'""",
                    f"""ALTER TABLE "{schema}"."cp_mcp_server_catalog"
                           ADD COLUMN IF NOT EXISTS token_env_key TEXT""",
                    f"""ALTER TABLE "{schema}"."cp_mcp_server_catalog"
                           ADD COLUMN IF NOT EXISTS token_header_name TEXT""",
                    f"""ALTER TABLE "{schema}"."cp_mcp_server_catalog"
                           ADD COLUMN IF NOT EXISTS token_header_template TEXT""",
                    f"""ALTER TABLE "{schema}"."cp_mcp_server_catalog"
                           ADD COLUMN IF NOT EXISTS owner_user_id TEXT""",
                    f"""ALTER TABLE "{schema}"."cp_mcp_server_catalog"
                           ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'curated'""",
                    f"""ALTER TABLE "{schema}"."cp_mcp_server_catalog"
                           ADD COLUMN IF NOT EXISTS validation_signature TEXT""",
                    # ALTER on oauth_sessions to add HMAC binding (defense in
                    # depth against state replay across sessions).
                    f"""ALTER TABLE "{schema}"."cp_mcp_oauth_sessions"
                           ADD COLUMN IF NOT EXISTS state_hmac TEXT""",
                ),
            ),
            _Migration(
                "024_supervisor_cluster",
                (
                    # leader-elected agent placement so a fleet of
                    # supervisor instances can host the same active set without
                    # two of them spawning duplicate workers for the same
                    # agent. ``supervisor_id`` identifies the claiming process
                    # (uuid generated at boot); ``heartbeat_at`` is refreshed
                    # on every reconcile and other supervisors reap claims
                    # whose heartbeat is older than
                    # ``KODA_CLUSTER_HEARTBEAT_STALE_SECONDS``.
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_agent_assignments" (
                            agent_id TEXT PRIMARY KEY,
                            supervisor_id TEXT NOT NULL,
                            claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            version INTEGER NOT NULL DEFAULT 0,
                            draining BOOLEAN NOT NULL DEFAULT FALSE
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_agent_assignments_supervisor
                           ON "{schema}"."cp_agent_assignments"
                           (supervisor_id, heartbeat_at DESC)""",
                    # supervisor runtime registry. Used by the
                    # blue/green drain protocol: setting ``draining=TRUE``
                    # for a supervisor causes the cluster module to release
                    # its claims on next heartbeat instead of refreshing
                    # them, so a rolling deploy hands work to the new
                    # version without dropping in-flight requests.
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."cp_supervisor_runtimes" (
                            supervisor_id TEXT PRIMARY KEY,
                            version TEXT NOT NULL DEFAULT '',
                            host TEXT NOT NULL DEFAULT '',
                            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            draining BOOLEAN NOT NULL DEFAULT FALSE,
                            capacity INTEGER NOT NULL DEFAULT 0
                        )""",
                ),
            ),
            _Migration(
                "025_task_leases",
                (
                    # Per-task lease ownership for crash-safe orchestration.
                    # ``lease_owner`` is the worker process UUID generated at
                    # boot; ``lease_expires_at`` is the point past which any
                    # other worker (or the janitor) is free to reclaim the
                    # row. Acquisition, renewal, completion and reaping all
                    # run as single atomic UPDATEs scoped to ``lease_owner``,
                    # so two workers cannot execute the same task and a
                    # crashed worker cannot resurrect a task that the janitor
                    # already requeued.
                    f"""ALTER TABLE "{schema}"."tasks"
                           ADD COLUMN IF NOT EXISTS lease_owner TEXT""",
                    f"""ALTER TABLE "{schema}"."tasks"
                           ADD COLUMN IF NOT EXISTS lease_expires_at TEXT""",
                    # Janitor sweep filter: scans active rows whose lease has
                    # expired (or was never set, for legacy stuck rows). The
                    # partial index keeps this O(stale rows) instead of
                    # O(all tasks) on agents with long history.
                    f"""CREATE INDEX IF NOT EXISTS idx_tasks_lease_sweep
                           ON "{schema}"."tasks"
                           (agent_id, lease_expires_at)
                           WHERE status IN ('running', 'retrying')""",
                ),
            ),
            _Migration(
                "026_memory_truthful_status_and_agent_maintenance",
                (
                    f"""ALTER TABLE "{schema}"."memory_maintenance_log"
                           ADD COLUMN IF NOT EXISTS agent_id TEXT DEFAULT 'default'""",
                    f"""UPDATE "{schema}"."memory_maintenance_log"
                           SET agent_id = 'default'
                           WHERE agent_id IS NULL OR agent_id = ''""",
                    f"""CREATE INDEX IF NOT EXISTS idx_memory_maintenance_log_agent
                           ON "{schema}"."memory_maintenance_log"
                           (agent_id, executed_at DESC)""",
                    f"""UPDATE "{schema}"."napkin_log"
                           SET embedding_status = 'lexical_ready'
                           WHERE COALESCE(embedding_status, '') = 'ready'
                             AND COALESCE(vector_ref_id, '') = ''""",
                ),
            ),
            _Migration(
                "027_sessions_agent_scope",
                (
                    f"""ALTER TABLE "{schema}"."sessions"
                           ADD COLUMN IF NOT EXISTS agent_id TEXT NOT NULL DEFAULT 'KODA'""",
                    f"""UPDATE "{schema}"."sessions"
                           SET agent_id = 'KODA'
                           WHERE agent_id IS NULL OR agent_id = ''""",
                    f"""CREATE INDEX IF NOT EXISTS idx_sessions_agent_last_used
                           ON "{schema}"."sessions" (agent_id, last_used DESC)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_sessions_agent_session
                           ON "{schema}"."sessions" (agent_id, session_id)""",
                ),
            ),
            _Migration(
                "028_squad_messages_v0",
                (
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."squad_messages" (
                            id BIGSERIAL PRIMARY KEY,
                            thread_id UUID NULL,
                            from_agent TEXT NOT NULL,
                            to_agent TEXT NOT NULL,
                            content TEXT NOT NULL DEFAULT '',
                            message_type TEXT NOT NULL DEFAULT 'text',
                            metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            delivered_at TIMESTAMPTZ NULL
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_squad_messages_to_agent_id
                           ON "{schema}"."squad_messages" (to_agent, id)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_squad_messages_thread_created
                           ON "{schema}"."squad_messages" (thread_id, created_at)
                           WHERE thread_id IS NOT NULL""",
                    f"""CREATE INDEX IF NOT EXISTS idx_squad_messages_created_at
                           ON "{schema}"."squad_messages" (created_at DESC)""",
                ),
            ),
            _Migration(
                "029_squad_threads_v0",
                (
                    f"""ALTER TABLE "{schema}"."squad_messages"
                           ALTER COLUMN to_agent DROP NOT NULL""",
                    f"""ALTER TABLE "{schema}"."squad_messages"
                           DROP CONSTRAINT IF EXISTS squad_messages_recipient_required""",
                    f"""ALTER TABLE "{schema}"."squad_messages"
                           ADD CONSTRAINT squad_messages_recipient_required
                           CHECK (to_agent IS NOT NULL OR thread_id IS NOT NULL)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."squad_threads" (
                            id UUID PRIMARY KEY,
                            workspace_id TEXT NOT NULL,
                            squad_id TEXT NOT NULL,
                            owner_user_id BIGINT NULL,
                            title TEXT NOT NULL DEFAULT '',
                            status TEXT NOT NULL DEFAULT 'open',
                            coordinator_agent_id TEXT NULL,
                            current_owner_agent_id TEXT NULL,
                            parent_thread_id UUID NULL,
                            visibility TEXT NOT NULL DEFAULT 'squad',
                            telegram_chat_id BIGINT NULL,
                            telegram_message_thread_id BIGINT NULL,
                            budget_usd_cap NUMERIC NULL,
                            cost_usd_accum NUMERIC NOT NULL DEFAULT 0,
                            metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            completed_at TIMESTAMPTZ NULL,
                            archived_at TIMESTAMPTZ NULL
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_squad_threads_workspace_squad_status
                           ON "{schema}"."squad_threads" (workspace_id, squad_id, status, updated_at DESC)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_squad_threads_owner_status
                           ON "{schema}"."squad_threads" (owner_user_id, status, updated_at DESC)
                           WHERE owner_user_id IS NOT NULL""",
                    f"""CREATE INDEX IF NOT EXISTS idx_squad_threads_telegram_topic
                           ON "{schema}"."squad_threads" (telegram_chat_id, telegram_message_thread_id)
                           WHERE telegram_chat_id IS NOT NULL""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."squad_thread_participants" (
                            thread_id UUID NOT NULL,
                            agent_id TEXT NOT NULL,
                            role TEXT NOT NULL DEFAULT 'worker',
                            joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            left_at TIMESTAMPTZ NULL,
                            last_read_message_id BIGINT NULL,
                            inbox_cursor BIGINT NULL,
                            paused BOOLEAN NOT NULL DEFAULT FALSE,
                            PRIMARY KEY (thread_id, agent_id)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_squad_thread_participants_agent_active
                           ON "{schema}"."squad_thread_participants" (agent_id, thread_id)
                           WHERE left_at IS NULL""",
                ),
            ),
            _Migration(
                "030_squad_tasks_v0",
                (
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."squad_tasks" (
                            id UUID PRIMARY KEY,
                            thread_id UUID NOT NULL,
                            parent_task_id UUID NULL,
                            depends_on JSONB NOT NULL DEFAULT '[]'::jsonb,
                            assigned_agent_id TEXT NULL,
                            assigner_agent_id TEXT NOT NULL,
                            kind TEXT NOT NULL DEFAULT '',
                            title TEXT NOT NULL,
                            description TEXT NOT NULL DEFAULT '',
                            status TEXT NOT NULL DEFAULT 'pending',
                            acceptance_criteria JSONB NOT NULL DEFAULT '[]'::jsonb,
                            deliverables_spec JSONB NOT NULL DEFAULT '[]'::jsonb,
                            delivered_artifact_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                            claim_token UUID NULL,
                            claim_expires_at TIMESTAMPTZ NULL,
                            delegation_depth INTEGER NOT NULL DEFAULT 0,
                            idempotency_key TEXT NULL,
                            cost_usd_so_far NUMERIC NOT NULL DEFAULT 0,
                            runtime_task_id BIGINT NULL,
                            version INTEGER NOT NULL DEFAULT 1,
                            metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            started_at TIMESTAMPTZ NULL,
                            completed_at TIMESTAMPTZ NULL,
                            error_message TEXT NULL,
                            result_summary TEXT NULL,
                            CONSTRAINT squad_tasks_status_check
                                CHECK (status IN (
                                    'pending', 'claimed', 'in_progress', 'blocked',
                                    'done', 'failed', 'cancelled', 'escalated'
                                ))
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_squad_tasks_thread_status
                           ON "{schema}"."squad_tasks" (thread_id, status, created_at)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_squad_tasks_assignee_active
                           ON "{schema}"."squad_tasks" (assigned_agent_id, status)
                           WHERE status IN ('claimed', 'in_progress', 'blocked')""",
                    f"""CREATE INDEX IF NOT EXISTS idx_squad_tasks_parent
                           ON "{schema}"."squad_tasks" (parent_task_id)
                           WHERE parent_task_id IS NOT NULL""",
                    f"""CREATE UNIQUE INDEX IF NOT EXISTS idx_squad_tasks_idempotency_key
                           ON "{schema}"."squad_tasks" (idempotency_key)
                           WHERE idempotency_key IS NOT NULL""",
                ),
            ),
            _Migration(
                "031_squad_member_capabilities_v0",
                (
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."squad_member_capabilities" (
                            squad_id TEXT NOT NULL,
                            agent_id TEXT NOT NULL,
                            display_name TEXT NOT NULL DEFAULT '',
                            role_label TEXT NOT NULL DEFAULT '',
                            domains JSONB NOT NULL DEFAULT '[]'::jsonb,
                            primary_outcomes JSONB NOT NULL DEFAULT '[]'::jsonb,
                            tool_categories JSONB NOT NULL DEFAULT '[]'::jsonb,
                            delegate_when TEXT NOT NULL DEFAULT '',
                            do_not_delegate TEXT NOT NULL DEFAULT '',
                            is_coordinator BOOLEAN NOT NULL DEFAULT FALSE,
                            summary_text TEXT NOT NULL DEFAULT '',
                            spec_version INTEGER NOT NULL DEFAULT 0,
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            expires_at TIMESTAMPTZ NULL,
                            PRIMARY KEY (squad_id, agent_id)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_squad_member_capabilities_agent
                           ON "{schema}"."squad_member_capabilities" (agent_id)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_squad_member_capabilities_expires
                           ON "{schema}"."squad_member_capabilities" (expires_at)
                           WHERE expires_at IS NOT NULL""",
                ),
            ),
            _Migration(
                "032_squad_coordinator_v0",
                (
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."squad_coordinator_state" (
                            squad_id TEXT PRIMARY KEY,
                            coordinator_agent_id TEXT NULL,
                            election_policy TEXT NOT NULL DEFAULT 'manual',
                            auto_demote_after_inactive_days INTEGER NULL,
                            elected_at TIMESTAMPTZ NULL,
                            elected_by_agent_id TEXT NULL,
                            last_active_at TIMESTAMPTZ NULL,
                            metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            CONSTRAINT squad_coordinator_election_policy_check
                                CHECK (election_policy IN ('manual', 'auto_first_active', 'weighted'))
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."squad_coordinator_history" (
                            id BIGSERIAL PRIMARY KEY,
                            squad_id TEXT NOT NULL,
                            event_type TEXT NOT NULL,
                            coordinator_agent_id TEXT NULL,
                            previous_coordinator_agent_id TEXT NULL,
                            triggered_by_agent_id TEXT NULL,
                            reason TEXT NULL,
                            metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            CONSTRAINT squad_coordinator_history_event_check
                                CHECK (event_type IN (
                                    'elected', 'demoted', 'auto_elected', 'auto_demoted',
                                    'replaced', 'policy_changed'
                                ))
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_squad_coordinator_history_squad_time
                           ON "{schema}"."squad_coordinator_history" (squad_id, created_at DESC)""",
                ),
            ),
            _Migration(
                "033_squad_telegram_bindings_v0",
                (
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."squad_telegram_bindings" (
                            squad_id TEXT PRIMARY KEY,
                            telegram_chat_id BIGINT NOT NULL,
                            chat_title TEXT NOT NULL DEFAULT '',
                            is_forum BOOLEAN NOT NULL DEFAULT FALSE,
                            bound_by_user_id BIGINT NULL,
                            bound_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb
                        )""",
                    f"""CREATE UNIQUE INDEX IF NOT EXISTS idx_squad_telegram_bindings_chat
                           ON "{schema}"."squad_telegram_bindings" (telegram_chat_id)""",
                ),
            ),
            _Migration(
                "034_squad_thread_cost_rollup",
                (
                    f"""ALTER TABLE "{schema}"."query_history"
                           ADD COLUMN IF NOT EXISTS squad_thread_id UUID NULL""",
                    f"""CREATE INDEX IF NOT EXISTS idx_query_history_squad_thread
                           ON "{schema}"."query_history" (squad_thread_id)
                           WHERE squad_thread_id IS NOT NULL""",
                    f"""CREATE OR REPLACE FUNCTION "{schema}".squad_thread_cost_rollup()
                        RETURNS TRIGGER AS $$
                        DECLARE
                            v_delta NUMERIC := 0;
                        BEGIN
                            IF (TG_OP = 'INSERT') THEN
                                IF NEW.squad_thread_id IS NULL THEN
                                    RETURN NEW;
                                END IF;
                                v_delta := COALESCE(NEW.cost_usd, 0);
                            ELSIF (TG_OP = 'UPDATE') THEN
                                -- Apply delta only if cost changed; if the
                                -- thread linkage moved, refund the old thread
                                -- and charge the new one.
                                IF NEW.squad_thread_id IS DISTINCT FROM OLD.squad_thread_id THEN
                                    IF OLD.squad_thread_id IS NOT NULL AND COALESCE(OLD.cost_usd, 0) <> 0 THEN
                                        UPDATE "{schema}"."squad_threads"
                                           SET cost_usd_accum = GREATEST(cost_usd_accum - COALESCE(OLD.cost_usd, 0), 0),
                                               updated_at = NOW()
                                         WHERE id = OLD.squad_thread_id;
                                    END IF;
                                    IF NEW.squad_thread_id IS NULL THEN
                                        RETURN NEW;
                                    END IF;
                                    v_delta := COALESCE(NEW.cost_usd, 0);
                                ELSE
                                    IF NEW.squad_thread_id IS NULL THEN
                                        RETURN NEW;
                                    END IF;
                                    v_delta := COALESCE(NEW.cost_usd, 0) - COALESCE(OLD.cost_usd, 0);
                                END IF;
                            END IF;
                            IF v_delta = 0 THEN
                                RETURN NEW;
                            END IF;
                            UPDATE "{schema}"."squad_threads"
                               SET cost_usd_accum = GREATEST(cost_usd_accum + v_delta, 0),
                                   updated_at = NOW()
                             WHERE id = NEW.squad_thread_id;
                            RETURN NEW;
                        END;
                        $$ LANGUAGE plpgsql""",
                    f"""DROP TRIGGER IF EXISTS query_history_squad_cost_rollup
                        ON "{schema}"."query_history" """,
                    f"""CREATE TRIGGER query_history_squad_cost_rollup
                        AFTER INSERT OR UPDATE OF cost_usd, squad_thread_id
                        ON "{schema}"."query_history"
                        FOR EACH ROW
                        EXECUTE FUNCTION "{schema}".squad_thread_cost_rollup()""",
                ),
            ),
            _Migration(
                "035_squad_runtime_envelope_and_artifacts",
                (
                    f"""ALTER TABLE "{schema}"."squad_messages"
                           ADD COLUMN IF NOT EXISTS message_uuid TEXT NULL""",
                    f"""ALTER TABLE "{schema}"."squad_messages"
                           ADD COLUMN IF NOT EXISTS to_agent_ids JSONB NOT NULL DEFAULT '[]'::jsonb""",
                    f"""ALTER TABLE "{schema}"."squad_messages"
                           ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'agent_text'""",
                    f"""ALTER TABLE "{schema}"."squad_messages"
                           ADD COLUMN IF NOT EXISTS payload_json JSONB NOT NULL DEFAULT '{{}}'::jsonb""",
                    f"""ALTER TABLE "{schema}"."squad_messages"
                           ADD COLUMN IF NOT EXISTS causation_id TEXT NULL""",
                    f"""ALTER TABLE "{schema}"."squad_messages"
                           ADD COLUMN IF NOT EXISTS correlation_id TEXT NULL""",
                    f"""ALTER TABLE "{schema}"."squad_messages"
                           ADD COLUMN IF NOT EXISTS in_reply_to TEXT NULL""",
                    f"""ALTER TABLE "{schema}"."squad_messages"
                           ADD COLUMN IF NOT EXISTS requires_response_by TIMESTAMPTZ NULL""",
                    f"""ALTER TABLE "{schema}"."squad_messages"
                           ADD COLUMN IF NOT EXISTS idempotency_key TEXT NULL""",
                    f"""UPDATE "{schema}"."squad_messages"
                           SET message_uuid = COALESCE(message_uuid, id::text),
                               to_agent_ids = CASE
                                   WHEN jsonb_array_length(to_agent_ids) = 0 AND to_agent IS NOT NULL
                                   THEN jsonb_build_array(to_agent)
                                   ELSE to_agent_ids
                               END,
                               kind = CASE
                                   WHEN COALESCE(message_type, 'text') = 'text' THEN 'agent_text'
                                   ELSE COALESCE(message_type, 'agent_text')
                               END,
                               payload_json = CASE
                                   WHEN payload_json = '{{}}'::jsonb AND COALESCE(content, '') <> ''
                                   THEN jsonb_build_object('text', content)
                                   ELSE payload_json
                               END
                         WHERE message_uuid IS NULL
                            OR jsonb_array_length(to_agent_ids) = 0
                            OR payload_json = '{{}}'::jsonb""",
                    f"""CREATE UNIQUE INDEX IF NOT EXISTS idx_squad_messages_message_uuid
                           ON "{schema}"."squad_messages" (message_uuid)
                           WHERE message_uuid IS NOT NULL""",
                    f"""CREATE INDEX IF NOT EXISTS idx_squad_messages_idempotency
                           ON "{schema}"."squad_messages" (idempotency_key, created_at DESC)
                           WHERE idempotency_key IS NOT NULL""",
                    f"""CREATE INDEX IF NOT EXISTS idx_squad_messages_correlation
                           ON "{schema}"."squad_messages" (correlation_id)
                           WHERE correlation_id IS NOT NULL""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."squad_message_recipients" (
                            message_id BIGINT NOT NULL REFERENCES "{schema}"."squad_messages"(id) ON DELETE CASCADE,
                            to_agent_id TEXT NOT NULL,
                            delivered_at TIMESTAMPTZ NULL,
                            acked_at TIMESTAMPTZ NULL,
                            delivery_status TEXT NOT NULL DEFAULT 'pending',
                            delivery_attempts INTEGER NOT NULL DEFAULT 0,
                            lease_expires_at TIMESTAMPTZ NULL,
                            last_error TEXT NULL,
                            enqueued_task_id BIGINT NULL,
                            dead_reported_at TIMESTAMPTZ NULL,
                            PRIMARY KEY (message_id, to_agent_id)
                        )""",
                    f"""ALTER TABLE "{schema}"."squad_message_recipients"
                           ADD COLUMN IF NOT EXISTS delivery_status TEXT NOT NULL DEFAULT 'pending'""",
                    f"""ALTER TABLE "{schema}"."squad_message_recipients"
                           ADD COLUMN IF NOT EXISTS delivery_attempts INTEGER NOT NULL DEFAULT 0""",
                    f"""ALTER TABLE "{schema}"."squad_message_recipients"
                           ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ NULL""",
                    f"""ALTER TABLE "{schema}"."squad_message_recipients"
                           ADD COLUMN IF NOT EXISTS last_error TEXT NULL""",
                    f"""ALTER TABLE "{schema}"."squad_message_recipients"
                           ADD COLUMN IF NOT EXISTS enqueued_task_id BIGINT NULL""",
                    f"""ALTER TABLE "{schema}"."squad_message_recipients"
                           ADD COLUMN IF NOT EXISTS dead_reported_at TIMESTAMPTZ NULL""",
                    f"""UPDATE "{schema}"."squad_message_recipients"
                           SET delivery_status = CASE
                               WHEN acked_at IS NOT NULL THEN 'acked'
                               WHEN delivery_status IS NULL THEN 'pending'
                               ELSE delivery_status
                           END""",
                    f"""CREATE INDEX IF NOT EXISTS idx_squad_message_recipients_agent_message
                           ON "{schema}"."squad_message_recipients" (to_agent_id, message_id)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_squad_message_recipients_delivery
                           ON "{schema}"."squad_message_recipients" (to_agent_id, delivery_status, message_id)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_squad_message_recipients_lease
                           ON "{schema}"."squad_message_recipients" (delivery_status, lease_expires_at)
                           WHERE delivery_status = 'leased'""",
                    f"""INSERT INTO "{schema}"."squad_message_recipients" (message_id, to_agent_id)
                           SELECT id, to_agent
                             FROM "{schema}"."squad_messages"
                            WHERE to_agent IS NOT NULL
                              ON CONFLICT DO NOTHING""",
                    f"""ALTER TABLE "{schema}"."query_history"
                           ADD COLUMN IF NOT EXISTS squad_message_id TEXT NULL""",
                    f"""ALTER TABLE "{schema}"."query_history"
                           ADD COLUMN IF NOT EXISTS squad_task_id UUID NULL""",
                    f"""CREATE INDEX IF NOT EXISTS idx_query_history_squad_task
                           ON "{schema}"."query_history" (squad_task_id)
                           WHERE squad_task_id IS NOT NULL""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."squad_artifacts" (
                            artifact_id TEXT PRIMARY KEY,
                            thread_id UUID NOT NULL,
                            task_id UUID NULL,
                            owner_agent_id TEXT NOT NULL,
                            version INTEGER NOT NULL DEFAULT 1,
                            kind TEXT NOT NULL DEFAULT '',
                            path_or_uri TEXT NOT NULL DEFAULT '',
                            visible_to_squad BOOLEAN NOT NULL DEFAULT TRUE,
                            metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_squad_artifacts_thread_created
                           ON "{schema}"."squad_artifacts" (thread_id, created_at DESC)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_squad_artifacts_task
                           ON "{schema}"."squad_artifacts" (task_id)
                           WHERE task_id IS NOT NULL""",
                ),
            ),
            _Migration(
                "036_run_graph_v1",
                (
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."run_graph_nodes" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            task_id BIGINT NOT NULL,
                            graph_id TEXT NOT NULL,
                            node_id TEXT NOT NULL,
                            attempt INTEGER NOT NULL DEFAULT 1,
                            parent_node_id TEXT NULL,
                            ordinal INTEGER NOT NULL DEFAULT 0,
                            node_type TEXT NOT NULL,
                            status TEXT NOT NULL,
                            summary TEXT NOT NULL DEFAULT '',
                            payload_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            redactions_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            refs_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            trace_id TEXT NULL,
                            audit_event_id BIGINT NULL,
                            runtime_event_seq BIGINT NULL,
                            source TEXT NOT NULL DEFAULT '',
                            started_at TIMESTAMPTZ NULL,
                            completed_at TIMESTAMPTZ NULL,
                            duration_ms DOUBLE PRECISION NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE (agent_id, task_id, node_id)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_run_graph_nodes_task
                           ON "{schema}"."run_graph_nodes" (agent_id, task_id, ordinal)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_run_graph_nodes_parent
                           ON "{schema}"."run_graph_nodes" (agent_id, task_id, parent_node_id)
                           WHERE parent_node_id IS NOT NULL""",
                    f"""CREATE INDEX IF NOT EXISTS idx_run_graph_nodes_type
                           ON "{schema}"."run_graph_nodes" (agent_id, node_type, created_at DESC)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."run_graph_edges" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            task_id BIGINT NOT NULL,
                            graph_id TEXT NOT NULL,
                            edge_id TEXT NOT NULL,
                            from_node_id TEXT NOT NULL,
                            to_node_id TEXT NOT NULL,
                            edge_type TEXT NOT NULL,
                            ordinal INTEGER NOT NULL DEFAULT 0,
                            payload_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE (agent_id, task_id, edge_id)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_run_graph_edges_task
                           ON "{schema}"."run_graph_edges" (agent_id, task_id, ordinal)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_run_graph_edges_nodes
                           ON "{schema}"."run_graph_edges" (agent_id, task_id, from_node_id, to_node_id)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."run_replay_snapshots" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            task_id BIGINT NOT NULL,
                            graph_id TEXT NOT NULL,
                            attempt INTEGER NOT NULL DEFAULT 1,
                            replay_mode TEXT NOT NULL DEFAULT 'offline',
                            payload_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE (agent_id, task_id, graph_id, attempt)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_run_replay_snapshots_task
                           ON "{schema}"."run_replay_snapshots" (agent_id, task_id, created_at DESC)""",
                    f"""ALTER TABLE "{schema}"."cp_mcp_discovered_tools"
                           ADD COLUMN IF NOT EXISTS risk_class TEXT NOT NULL DEFAULT 'unknown'""",
                    f"""ALTER TABLE "{schema}"."cp_mcp_discovered_tools"
                           ADD COLUMN IF NOT EXISTS approval_default TEXT NOT NULL DEFAULT 'require_approval'""",
                    f"""ALTER TABLE "{schema}"."cp_mcp_discovered_tools"
                           ADD COLUMN IF NOT EXISTS risk_metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb""",
                ),
            ),
            _Migration(
                "037_child_runs_v1",
                (
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."child_runs" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            child_run_id TEXT NOT NULL,
                            parent_task_id BIGINT NOT NULL,
                            child_task_id BIGINT NULL,
                            status TEXT NOT NULL DEFAULT 'queued',
                            idempotency_key TEXT NOT NULL,
                            target_agent_id TEXT NULL,
                            toolset TEXT NOT NULL DEFAULT 'read_only',
                            request_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            context_policy_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            context_summary_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            result_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            error_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            deadline_at TIMESTAMPTZ NULL,
                            started_at TIMESTAMPTZ NULL,
                            completed_at TIMESTAMPTZ NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE (agent_id, child_run_id)
                        )""",
                    f"""CREATE UNIQUE INDEX IF NOT EXISTS idx_child_runs_idempotency
                           ON "{schema}"."child_runs" (agent_id, parent_task_id, idempotency_key)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_child_runs_parent
                           ON "{schema}"."child_runs" (agent_id, parent_task_id, created_at ASC)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_child_runs_child_task
                           ON "{schema}"."child_runs" (agent_id, child_task_id)
                           WHERE child_task_id IS NOT NULL""",
                    f"""CREATE INDEX IF NOT EXISTS idx_child_runs_status
                           ON "{schema}"."child_runs" (agent_id, status, updated_at DESC)""",
                ),
            ),
            _Migration(
                "038_skill_packages_v1",
                (
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."skill_packages" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            package_id TEXT NOT NULL,
                            status TEXT NOT NULL DEFAULT 'installed',
                            package_hash TEXT NOT NULL DEFAULT '',
                            manifest_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            scan_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            lock_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            installed_skills_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                            installed_tools_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                            previous_lock_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            installed_at TIMESTAMPTZ NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE (agent_id, package_id)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_skill_packages_agent_status
                           ON "{schema}"."skill_packages" (agent_id, status, updated_at DESC)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_skill_packages_hash
                           ON "{schema}"."skill_packages" (agent_id, package_hash)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."skill_package_events" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            package_id TEXT NOT NULL,
                            event_type TEXT NOT NULL,
                            event_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_skill_package_events_agent_package
                           ON "{schema}"."skill_package_events" (agent_id, package_id, created_at DESC)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_skill_package_events_type
                           ON "{schema}"."skill_package_events" (event_type, created_at DESC)""",
                ),
            ),
            _Migration(
                "039_evals_release_quality_v1",
                (
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."eval_suites" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            suite_id TEXT NOT NULL,
                            title TEXT NOT NULL DEFAULT '',
                            description TEXT NOT NULL DEFAULT '',
                            status TEXT NOT NULL DEFAULT 'active',
                            metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE (agent_id, suite_id)
                        )""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."eval_suite_cases" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            suite_id TEXT NOT NULL,
                            case_key TEXT NOT NULL,
                            position INTEGER NOT NULL DEFAULT 0,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE (agent_id, suite_id, case_key)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_eval_suite_cases_suite
                           ON "{schema}"."eval_suite_cases" (agent_id, suite_id, position)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."eval_run_batches" (
                            id BIGSERIAL PRIMARY KEY,
                            run_id TEXT NOT NULL,
                            agent_id TEXT NOT NULL,
                            suite_id TEXT NOT NULL DEFAULT 'default',
                            strategy TEXT NOT NULL DEFAULT 'offline_replay',
                            status TEXT NOT NULL DEFAULT 'failed',
                            score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            summary_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            case_results_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                            requested_by TEXT NOT NULL DEFAULT '',
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE (agent_id, run_id)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_eval_run_batches_agent_created
                           ON "{schema}"."eval_run_batches" (agent_id, created_at DESC)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_eval_run_batches_status
                           ON "{schema}"."eval_run_batches" (agent_id, status, created_at DESC)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."trajectory_exports" (
                            id BIGSERIAL PRIMARY KEY,
                            export_id TEXT NOT NULL,
                            agent_id TEXT NOT NULL,
                            task_id BIGINT NULL,
                            status TEXT NOT NULL DEFAULT 'created',
                            package_hash TEXT NOT NULL DEFAULT '',
                            payload_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            jsonl_text TEXT NOT NULL DEFAULT '',
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE (agent_id, export_id)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_trajectory_exports_agent_created
                           ON "{schema}"."trajectory_exports" (agent_id, created_at DESC)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_trajectory_exports_task
                           ON "{schema}"."trajectory_exports" (agent_id, task_id, created_at DESC)
                           WHERE task_id IS NOT NULL""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."release_quality_runs" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            status TEXT NOT NULL DEFAULT 'failed',
                            payload_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_release_quality_runs_agent_created
                           ON "{schema}"."release_quality_runs" (agent_id, created_at DESC)""",
                ),
            ),
            _Migration(
                "040_channel_gateway_onboarding_v1",
                (
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."channel_gateway_identities" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            identity_id TEXT NOT NULL,
                            channel_type TEXT NOT NULL,
                            channel_id TEXT NOT NULL DEFAULT '',
                            user_id TEXT NOT NULL DEFAULT '',
                            display_name TEXT NOT NULL DEFAULT '',
                            status TEXT NOT NULL DEFAULT 'pending',
                            is_group BOOLEAN NOT NULL DEFAULT FALSE,
                            record_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            last_seen_at TIMESTAMPTZ NULL,
                            UNIQUE (agent_id, identity_id)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_channel_gateway_identities_agent_status
                           ON "{schema}"."channel_gateway_identities" (agent_id, status, updated_at DESC)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_channel_gateway_identities_sender
                           ON "{schema}"."channel_gateway_identities" (agent_id, channel_type, channel_id, user_id)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."channel_unknown_senders" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            identity_id TEXT NOT NULL,
                            channel_type TEXT NOT NULL,
                            channel_id TEXT NOT NULL DEFAULT '',
                            user_id TEXT NOT NULL DEFAULT '',
                            display_name TEXT NOT NULL DEFAULT '',
                            status TEXT NOT NULL DEFAULT 'pending',
                            payload_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE (agent_id, identity_id)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_channel_unknown_senders_agent_status
                           ON "{schema}"."channel_unknown_senders" (agent_id, status, last_seen_at DESC)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."channel_pairing_codes" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            pairing_code_id TEXT NOT NULL,
                            channel_type TEXT NOT NULL,
                            code TEXT NOT NULL,
                            payload_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            expires_at TIMESTAMPTZ NOT NULL,
                            used_at TIMESTAMPTZ NULL,
                            UNIQUE (agent_id, pairing_code_id)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_channel_pairing_codes_active
                           ON "{schema}"."channel_pairing_codes" (agent_id, channel_type, expires_at DESC)
                           WHERE used_at IS NULL""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."channel_gateway_events" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            event_type TEXT NOT NULL,
                            event_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_channel_gateway_events_agent_created
                           ON "{schema}"."channel_gateway_events" (agent_id, created_at DESC)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_channel_gateway_events_type
                           ON "{schema}"."channel_gateway_events" (event_type, created_at DESC)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."onboarding_readiness_runs" (
                            id BIGSERIAL PRIMARY KEY,
                            agent_id TEXT NOT NULL,
                            status TEXT NOT NULL DEFAULT 'pending',
                            payload_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_onboarding_readiness_runs_agent_created
                           ON "{schema}"."onboarding_readiness_runs" (agent_id, created_at DESC)""",
                ),
            ),
            _Migration(
                "041_evaluation_cases_created_at",
                (
                    f"""ALTER TABLE "{schema}"."evaluation_cases"
                           ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()""",
                ),
            ),
            _Migration(
                "042_thread_replies_v1",
                (
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."squad_reply_obligations" (
                            id BIGSERIAL PRIMARY KEY,
                            obligation_key TEXT NOT NULL,
                            thread_id UUID NOT NULL REFERENCES "{schema}"."squad_threads"(id) ON DELETE CASCADE,
                            source_message_id BIGINT NOT NULL REFERENCES "{schema}"."squad_messages"(id) ON DELETE CASCADE,
                            target_agent_id TEXT NOT NULL,
                            status TEXT NOT NULL DEFAULT 'open',
                            requires_response_by TIMESTAMPTZ NULL,
                            resolved_by_message_id BIGINT NULL REFERENCES "{schema}"."squad_messages"(id) ON DELETE SET NULL,
                            followup_count INTEGER NOT NULL DEFAULT 0,
                            last_followup_at TIMESTAMPTZ NULL,
                            metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE (obligation_key)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_squad_reply_obligations_thread_status
                           ON "{schema}"."squad_reply_obligations" (thread_id, status, updated_at DESC)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_squad_reply_obligations_source
                           ON "{schema}"."squad_reply_obligations" (thread_id, source_message_id, target_agent_id)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_squad_reply_obligations_target_open
                           ON "{schema}"."squad_reply_obligations" (target_agent_id, requires_response_by, created_at)
                           WHERE status = 'open'""",
                    f"""CREATE INDEX IF NOT EXISTS idx_squad_reply_obligations_resolved
                           ON "{schema}"."squad_reply_obligations" (resolved_by_message_id)
                           WHERE resolved_by_message_id IS NOT NULL""",
                    f"""CREATE INDEX IF NOT EXISTS idx_squad_messages_thread_reply_parent
                           ON "{schema}"."squad_messages" (thread_id, in_reply_to, id)
                           WHERE in_reply_to IS NOT NULL""",
                    f"""CREATE INDEX IF NOT EXISTS idx_squad_messages_thread_correlation
                           ON "{schema}"."squad_messages" (thread_id, correlation_id, id)
                           WHERE correlation_id IS NOT NULL""",
                    f"""CREATE INDEX IF NOT EXISTS idx_squad_messages_thread_response_deadline
                           ON "{schema}"."squad_messages" (thread_id, requires_response_by)
                           WHERE requires_response_by IS NOT NULL""",
                ),
            ),
            _Migration(
                "043_operator_profile",
                (
                    f"""ALTER TABLE "{schema}"."cp_operator_users"
                           ADD COLUMN IF NOT EXISTS profile_photo_hash TEXT NOT NULL DEFAULT ''""",
                    f"""ALTER TABLE "{schema}"."cp_operator_users"
                           ADD COLUMN IF NOT EXISTS profile_photo_updated_at TEXT NOT NULL DEFAULT ''""",
                ),
            ),
            _Migration(
                "044_workspace_directory_import",
                (
                    f"""ALTER TABLE "{schema}"."cp_workspaces"
                           ADD COLUMN IF NOT EXISTS root_path TEXT""",
                    f"""ALTER TABLE "{schema}"."cp_workspaces"
                           ADD COLUMN IF NOT EXISTS root_kind TEXT NOT NULL DEFAULT ''""",
                    f"""ALTER TABLE "{schema}"."cp_workspaces"
                           ADD COLUMN IF NOT EXISTS scan_status TEXT NOT NULL DEFAULT 'not_scanned'""",
                    f"""ALTER TABLE "{schema}"."cp_workspaces"
                           ADD COLUMN IF NOT EXISTS last_scanned_at TEXT""",
                    f"""ALTER TABLE "{schema}"."cp_workspaces"
                           ADD COLUMN IF NOT EXISTS scan_hash TEXT NOT NULL DEFAULT ''""",
                    f"""ALTER TABLE "{schema}"."cp_workspaces"
                           ADD COLUMN IF NOT EXISTS config_sources_json TEXT NOT NULL DEFAULT '{{}}'""",
                    f"""ALTER TABLE "{schema}"."cp_workspaces"
                           ADD COLUMN IF NOT EXISTS import_history_json TEXT NOT NULL DEFAULT '[]'""",
                ),
            ),
            _Migration(
                "045_improvement_proposals_v1",
                (
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."improvement_proposals" (
                            proposal_id TEXT PRIMARY KEY,
                            schema_version TEXT NOT NULL DEFAULT 'improvement_proposal.v1',
                            agent_id TEXT NOT NULL,
                            source_kind TEXT NOT NULL CHECK (
                                source_kind IN (
                                    'run', 'eval', 'user_correction', 'timeout',
                                    'dead_letter', 'tool_failure', 'manual'
                                )
                            ),
                            source_ref TEXT NOT NULL,
                            proposal_type TEXT NOT NULL CHECK (
                                proposal_type IN (
                                    'memory', 'skill', 'prompt', 'routing_profile',
                                    'tool_policy', 'eval_case', 'docs'
                                )
                            ),
                            summary TEXT NOT NULL,
                            evidence_refs_json TEXT NOT NULL DEFAULT '[]',
                            diff_preview_json TEXT NOT NULL DEFAULT '{{}}',
                            risk_class TEXT NOT NULL DEFAULT 'medium' CHECK (
                                risk_class IN ('low', 'medium', 'high', 'critical')
                            ),
                            validation_plan_json TEXT NOT NULL DEFAULT '{{}}',
                            validation_result_json TEXT NOT NULL DEFAULT '{{}}',
                            rollback_plan_json TEXT NOT NULL DEFAULT '{{}}',
                            status TEXT NOT NULL DEFAULT 'pending_review' CHECK (
                                status IN (
                                    'draft', 'pending_review', 'approved', 'rejected',
                                    'validating', 'applied', 'rolled_back', 'failed'
                                )
                            ),
                            reviewer TEXT NOT NULL DEFAULT '',
                            idempotency_hash TEXT NOT NULL,
                            run_graph_node_ids_json TEXT NOT NULL DEFAULT '[]',
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            reviewed_at TEXT NOT NULL DEFAULT '',
                            validated_at TEXT NOT NULL DEFAULT '',
                            applied_at TEXT NOT NULL DEFAULT '',
                            rolled_back_at TEXT NOT NULL DEFAULT '',
                            status_history_json TEXT NOT NULL DEFAULT '[]',
                            UNIQUE (agent_id, idempotency_hash)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_improvement_proposals_agent_status
                           ON "{schema}"."improvement_proposals" (agent_id, status, updated_at DESC)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_improvement_proposals_agent_type
                           ON "{schema}"."improvement_proposals" (agent_id, proposal_type, updated_at DESC)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_improvement_proposals_source
                           ON "{schema}"."improvement_proposals" (source_kind, source_ref)""",
                    f"""CREATE TABLE IF NOT EXISTS "{schema}"."improvement_proposal_effects" (
                            effect_id TEXT PRIMARY KEY,
                            proposal_id TEXT NOT NULL,
                            agent_id TEXT NOT NULL,
                            effect_kind TEXT NOT NULL,
                            target_ref TEXT NOT NULL,
                            before_ref_json TEXT NOT NULL DEFAULT '{{}}',
                            after_ref_json TEXT NOT NULL DEFAULT '{{}}',
                            status TEXT NOT NULL DEFAULT 'pending' CHECK (
                                status IN ('pending', 'applied', 'rolled_back', 'failed')
                            ),
                            apply_idempotency_key TEXT NOT NULL,
                            rollback_idempotency_key TEXT NOT NULL,
                            error_json TEXT NOT NULL DEFAULT '{{}}',
                            metadata_json TEXT NOT NULL DEFAULT '{{}}',
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            applied_at TEXT NOT NULL DEFAULT '',
                            rolled_back_at TEXT NOT NULL DEFAULT '',
                            UNIQUE (agent_id, proposal_id, apply_idempotency_key),
                            UNIQUE (agent_id, proposal_id, rollback_idempotency_key)
                        )""",
                    f"""CREATE INDEX IF NOT EXISTS idx_improvement_proposal_effects_proposal
                           ON "{schema}"."improvement_proposal_effects" (agent_id, proposal_id, status)""",
                ),
            ),
            _Migration(
                "046_memory_governance_namespaces",
                (
                    f"""ALTER TABLE "{schema}"."napkin_log"
                           ADD COLUMN IF NOT EXISTS namespace_kind TEXT NOT NULL DEFAULT 'agent'""",
                    f"""ALTER TABLE "{schema}"."napkin_log"
                           ADD COLUMN IF NOT EXISTS namespace_key TEXT NOT NULL DEFAULT ''""",
                    f"""ALTER TABLE "{schema}"."napkin_log"
                           ADD COLUMN IF NOT EXISTS namespace_scope_json TEXT NOT NULL DEFAULT '{{}}'""",
                    f"""ALTER TABLE "{schema}"."napkin_log"
                           ADD COLUMN IF NOT EXISTS sensitivity TEXT NOT NULL DEFAULT 'normal'""",
                    f"""UPDATE "{schema}"."napkin_log"
                           SET namespace_kind = COALESCE(NULLIF(namespace_kind, ''), 'agent'),
                               namespace_key = COALESCE(NULLIF(namespace_key, ''), COALESCE(agent_id, 'default')),
                               sensitivity = CASE
                                   WHEN COALESCE(sensitivity, '') IN ('normal', 'sensitive') THEN sensitivity
                                   ELSE 'normal'
                               END
                         WHERE namespace_key = '' OR namespace_kind = '' OR sensitivity = ''""",
                    f"""CREATE INDEX IF NOT EXISTS idx_napkin_namespace_lookup
                           ON "{schema}"."napkin_log"
                           (user_id, agent_id, namespace_kind, namespace_key, is_active)""",
                    f"""CREATE INDEX IF NOT EXISTS idx_napkin_sensitivity
                           ON "{schema}"."napkin_log"
                           (agent_id, sensitivity, memory_status, is_active)""",
                ),
            ),
        )

    async def upsert_skill_package_lock(self, agent_id: str, lock: dict[str, Any]) -> None:
        if not self.enabled:
            return
        package_id = str(lock.get("package_id") or "").strip()
        if not package_id:
            return
        normalized_agent = (agent_id or self._agent_id or "default").upper()
        async with self._connection() as conn:
            await conn.execute(
                f"""
                INSERT INTO "{self._schema}"."skill_packages" (
                    agent_id, package_id, status, package_hash, manifest_json, scan_json,
                    lock_json, installed_skills_json, installed_tools_json, previous_lock_json,
                    installed_at, updated_at
                )
                VALUES ($1, $2, 'installed', $3, $4::jsonb, $5::jsonb, $6::jsonb, $7::jsonb,
                        $8::jsonb, $9::jsonb, NOW(), NOW())
                ON CONFLICT (agent_id, package_id) DO UPDATE SET
                    status = 'installed',
                    package_hash = EXCLUDED.package_hash,
                    manifest_json = EXCLUDED.manifest_json,
                    scan_json = EXCLUDED.scan_json,
                    lock_json = EXCLUDED.lock_json,
                    installed_skills_json = EXCLUDED.installed_skills_json,
                    installed_tools_json = EXCLUDED.installed_tools_json,
                    previous_lock_json = EXCLUDED.previous_lock_json,
                    installed_at = EXCLUDED.installed_at,
                    updated_at = NOW()
                """,
                normalized_agent,
                package_id,
                str(lock.get("package_hash") or ""),
                _json_dumps(lock.get("manifest") or {}),
                _json_dumps(lock.get("scan_summary") or {}),
                _json_dumps(lock),
                _json_dumps(lock.get("installed_skills") or []),
                _json_dumps(lock.get("installed_tools") or []),
                _json_dumps(lock.get("previous_revision") or {}),
            )

    async def list_skill_package_locks(self, agent_id: str) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        normalized_agent = (agent_id or self._agent_id or "default").upper()
        async with self._connection() as conn:
            rows = await conn.fetch(
                f"""
                SELECT lock_json
                FROM "{self._schema}"."skill_packages"
                WHERE agent_id = $1 AND status = 'installed'
                ORDER BY updated_at DESC, package_id ASC
                """,
                normalized_agent,
            )
        return [_json_object(row["lock_json"]) for row in rows]

    async def get_skill_package_lock(self, agent_id: str, package_id: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        normalized_agent = (agent_id or self._agent_id or "default").upper()
        async with self._connection() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT lock_json
                FROM "{self._schema}"."skill_packages"
                WHERE agent_id = $1 AND package_id = $2 AND status = 'installed'
                """,
                normalized_agent,
                str(package_id),
            )
        return _json_object(row["lock_json"]) if row else None

    async def delete_skill_package_lock(self, agent_id: str, package_id: str) -> None:
        if not self.enabled:
            return
        normalized_agent = (agent_id or self._agent_id or "default").upper()
        async with self._connection() as conn:
            await conn.execute(
                f"""
                UPDATE "{self._schema}"."skill_packages"
                SET status = 'uninstalled', updated_at = NOW()
                WHERE agent_id = $1 AND package_id = $2
                """,
                normalized_agent,
                str(package_id),
            )

    async def append_skill_package_event(
        self,
        agent_id: str,
        package_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        if not self.enabled:
            return
        normalized_agent = (agent_id or self._agent_id or "default").upper()
        async with self._connection() as conn:
            await conn.execute(
                f"""
                INSERT INTO "{self._schema}"."skill_package_events" (
                    agent_id, package_id, event_type, event_json
                ) VALUES ($1, $2, $3, $4::jsonb)
                """,
                normalized_agent,
                str(package_id or ""),
                str(event_type or "skill_package.event"),
                _json_dumps(payload or {}),
            )

    async def upsert_channel_gateway_identity(self, agent_id: str, record: dict[str, Any]) -> None:
        if not self.enabled:
            return
        normalized_agent = (agent_id or self._agent_id or "default").upper()
        identity_id = str(record.get("identity_id") or "").strip()
        if not identity_id:
            return
        async with self._connection() as conn:
            await conn.execute(
                f"""
                INSERT INTO "{self._schema}"."channel_gateway_identities" (
                    agent_id, identity_id, channel_type, channel_id, user_id,
                    display_name, status, is_group, record_json, last_seen_at, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, NOW(), NOW())
                ON CONFLICT (agent_id, identity_id) DO UPDATE SET
                    channel_type = EXCLUDED.channel_type,
                    channel_id = EXCLUDED.channel_id,
                    user_id = EXCLUDED.user_id,
                    display_name = EXCLUDED.display_name,
                    status = EXCLUDED.status,
                    is_group = EXCLUDED.is_group,
                    record_json = EXCLUDED.record_json,
                    last_seen_at = NOW(),
                    updated_at = NOW()
                """,
                normalized_agent,
                identity_id,
                str(record.get("channel_type") or ""),
                str(record.get("channel_id") or ""),
                str(record.get("user_id") or ""),
                str(record.get("display_name") or ""),
                str(record.get("status") or "pending"),
                bool(record.get("is_group")),
                _json_dumps(record),
            )

    async def list_channel_gateway_identities(self, agent_id: str) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        normalized_agent = (agent_id or self._agent_id or "default").upper()
        async with self._connection() as conn:
            rows = await conn.fetch(
                f"""
                SELECT agent_id, identity_id, channel_type, channel_id, user_id,
                       display_name, status, is_group, record_json,
                       created_at, updated_at, last_seen_at
                FROM "{self._schema}"."channel_gateway_identities"
                WHERE agent_id = $1
                ORDER BY updated_at DESC, identity_id ASC
                """,
                normalized_agent,
            )
        items: list[dict[str, Any]] = []
        for row in rows:
            base = {
                "schema_version": "channel_gateway.v1",
                "agent_id": str(row["agent_id"] or normalized_agent),
                "identity_id": str(row["identity_id"] or ""),
                "channel_type": str(row["channel_type"] or ""),
                "channel_id": str(row["channel_id"] or ""),
                "user_id": str(row["user_id"] or ""),
                "display_name": str(row["display_name"] or row["user_id"] or ""),
                "status": str(row["status"] or "pending"),
                "is_group": bool(row["is_group"]),
                "scopes": ["message"],
                "source": "channel_gateway",
                "created_at": _iso_or_empty(row["created_at"]),
                "updated_at": _iso_or_empty(row["updated_at"]),
                "last_seen_at": _iso_or_empty(row["last_seen_at"]),
            }
            payload = _json_object(row["record_json"])
            base.update(payload)
            for key in (
                "agent_id",
                "identity_id",
                "channel_type",
                "channel_id",
                "user_id",
                "display_name",
                "status",
            ):
                if not str(base.get(key) or ""):
                    base[key] = str(row[key] or "")
            base["is_group"] = bool(base.get("is_group"))
            items.append(base)
        return items

    async def upsert_channel_unknown_sender(self, agent_id: str, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return
        normalized_agent = (agent_id or self._agent_id or "default").upper()
        identity_id = str(payload.get("identity_id") or "").strip()
        if not identity_id:
            return
        async with self._connection() as conn:
            await conn.execute(
                f"""
                INSERT INTO "{self._schema}"."channel_unknown_senders" (
                    agent_id, identity_id, channel_type, channel_id, user_id,
                    display_name, status, payload_json, last_seen_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, NOW())
                ON CONFLICT (agent_id, identity_id) DO UPDATE SET
                    channel_type = EXCLUDED.channel_type,
                    channel_id = EXCLUDED.channel_id,
                    user_id = EXCLUDED.user_id,
                    display_name = EXCLUDED.display_name,
                    status = EXCLUDED.status,
                    payload_json = EXCLUDED.payload_json,
                    last_seen_at = NOW()
                """,
                normalized_agent,
                identity_id,
                str(payload.get("channel_type") or ""),
                str(payload.get("channel_id") or ""),
                str(payload.get("user_id") or ""),
                str(payload.get("display_name") or ""),
                str(payload.get("status") or "pending"),
                _json_dumps(payload),
            )

    async def list_channel_unknown_senders(self, agent_id: str) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        normalized_agent = (agent_id or self._agent_id or "default").upper()
        async with self._connection() as conn:
            rows = await conn.fetch(
                f"""
                SELECT agent_id, identity_id, channel_type, channel_id, user_id,
                       display_name, status, payload_json, first_seen_at, last_seen_at
                FROM "{self._schema}"."channel_unknown_senders"
                WHERE agent_id = $1 AND status = 'pending'
                ORDER BY last_seen_at DESC, identity_id ASC
                """,
                normalized_agent,
            )
        items: list[dict[str, Any]] = []
        for row in rows:
            base = {
                "schema_version": "channel_gateway.v1",
                "agent_id": str(row["agent_id"] or normalized_agent),
                "identity_id": str(row["identity_id"] or ""),
                "channel_type": str(row["channel_type"] or ""),
                "channel_id": str(row["channel_id"] or ""),
                "user_id": str(row["user_id"] or ""),
                "display_name": str(row["display_name"] or row["user_id"] or ""),
                "is_group": False,
                "message_id": "",
                "message_preview": "",
                "status": str(row["status"] or "pending"),
                "first_seen_at": _iso_or_empty(row["first_seen_at"]),
                "last_seen_at": _iso_or_empty(row["last_seen_at"]),
            }
            payload = _json_object(row["payload_json"])
            base.update(payload)
            for key in (
                "agent_id",
                "identity_id",
                "channel_type",
                "channel_id",
                "user_id",
                "display_name",
                "status",
            ):
                if not str(base.get(key) or ""):
                    base[key] = str(row[key] or "")
            base["is_group"] = bool(base.get("is_group"))
            items.append(base)
        return items

    async def delete_channel_unknown_sender(self, agent_id: str, identity_id: str) -> None:
        if not self.enabled:
            return
        normalized_agent = (agent_id or self._agent_id or "default").upper()
        async with self._connection() as conn:
            await conn.execute(
                f"""
                UPDATE "{self._schema}"."channel_unknown_senders"
                SET status = 'resolved', last_seen_at = NOW()
                WHERE agent_id = $1 AND identity_id = $2
                """,
                normalized_agent,
                str(identity_id),
            )

    async def upsert_channel_pairing_code(self, agent_id: str, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return
        normalized_agent = (agent_id or self._agent_id or "default").upper()
        pairing_code_id = str(payload.get("pairing_code_id") or "").strip()
        if not pairing_code_id:
            return
        async with self._connection() as conn:
            await conn.execute(
                f"""
                INSERT INTO "{self._schema}"."channel_pairing_codes" (
                    agent_id, pairing_code_id, channel_type, code, payload_json, expires_at
                )
                VALUES ($1, $2, $3, $4, $5::jsonb, $6::timestamptz)
                ON CONFLICT (agent_id, pairing_code_id) DO UPDATE SET
                    channel_type = EXCLUDED.channel_type,
                    code = EXCLUDED.code,
                    payload_json = EXCLUDED.payload_json,
                    expires_at = EXCLUDED.expires_at
                """,
                normalized_agent,
                pairing_code_id,
                str(payload.get("channel_type") or "telegram"),
                str(payload.get("code") or ""),
                _json_dumps(payload),
                str(payload.get("expires_at") or ""),
            )

    async def list_channel_pairing_codes(self, agent_id: str) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        normalized_agent = (agent_id or self._agent_id or "default").upper()
        async with self._connection() as conn:
            rows = await conn.fetch(
                f"""
                SELECT agent_id, pairing_code_id, channel_type, code,
                       payload_json, created_at, expires_at, used_at
                FROM "{self._schema}"."channel_pairing_codes"
                WHERE agent_id = $1 AND used_at IS NULL AND expires_at > NOW()
                ORDER BY expires_at DESC, pairing_code_id ASC
                """,
                normalized_agent,
            )
        payloads: list[dict[str, Any]] = []
        for row in rows:
            payload = {
                "schema_version": "channel_gateway.v1",
                "agent_id": str(row["agent_id"] or normalized_agent),
                "pairing_code_id": str(row["pairing_code_id"] or ""),
                "channel_type": str(row["channel_type"] or "telegram"),
                "code": str(row["code"] or ""),
                "status": "active",
                "created_at": _iso_or_empty(row["created_at"]),
                "expires_at": _iso_or_empty(row["expires_at"]),
                **_json_object(row["payload_json"]),
            }
            if row["used_at"] is not None:
                payload["used_at"] = _iso_or_empty(row["used_at"])
            payloads.append(payload)
        return payloads

    async def consume_channel_pairing_code(self, agent_id: str, pairing_code_id: str) -> None:
        if not self.enabled:
            return
        normalized_agent = (agent_id or self._agent_id or "default").upper()
        async with self._connection() as conn:
            await conn.execute(
                f"""
                UPDATE "{self._schema}"."channel_pairing_codes"
                SET used_at = NOW()
                WHERE agent_id = $1 AND pairing_code_id = $2 AND used_at IS NULL
                """,
                normalized_agent,
                str(pairing_code_id),
            )

    async def append_channel_gateway_event(self, agent_id: str, event_type: str, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return
        normalized_agent = (agent_id or self._agent_id or "default").upper()
        async with self._connection() as conn:
            await conn.execute(
                f"""
                INSERT INTO "{self._schema}"."channel_gateway_events" (
                    agent_id, event_type, event_json
                ) VALUES ($1, $2, $3::jsonb)
                """,
                normalized_agent,
                str(event_type or "channel_gateway.event"),
                _json_dumps(payload or {}),
            )

    async def persist_onboarding_readiness_run(self, agent_id: str, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return
        normalized_agent = (agent_id or self._agent_id or "default").upper()
        async with self._connection() as conn:
            await conn.execute(
                f"""
                INSERT INTO "{self._schema}"."onboarding_readiness_runs" (
                    agent_id, status, payload_json
                ) VALUES ($1, $2, $3::jsonb)
                """,
                normalized_agent,
                str(payload.get("status") or "pending"),
                _json_dumps(payload or {}),
            )

    async def upsert_documents(self, entries: list[KnowledgeEntry], *, object_key: str) -> None:
        if not entries or not self.bootstrapped:
            return
        async with self._connection() as conn:
            rows = []
            chunk_rows = []
            for entry in entries:
                document_key = f"{entry.layer.value}:{entry.source_label}:{entry.source_path}"
                tags = list(entry.tags)
                metadata = {
                    "entry_id": entry.id,
                    "pack_id": entry.pack_id,
                    "criticality": entry.criticality,
                }
                rows.append(
                    (
                        self._agent_id,
                        document_key,
                        entry.source_label,
                        entry.source_path,
                        _workspace_root_for(entry.source_path),
                        entry.layer.value,
                        entry.scope.value,
                        entry.title,
                        entry.content,
                        entry.owner,
                        entry.project_key,
                        entry.environment,
                        entry.team,
                        entry.source_type,
                        entry.operable,
                        entry.freshness_days,
                        _json_dumps(tags),
                        _json_dumps(metadata),
                        hashlib.sha256(entry.content.encode("utf-8")).hexdigest(),
                        object_key,
                        _safe_datetime(entry.updated_at),
                    )
                )
                chunk_rows.append(
                    (
                        self._agent_id,
                        entry.id,
                        document_key,
                        entry.source_label,
                        entry.source_path,
                        _workspace_root_for(entry.source_path),
                        entry.layer.value,
                        entry.scope.value,
                        entry.title,
                        entry.content,
                        entry.owner,
                        entry.project_key,
                        entry.environment,
                        entry.team,
                        entry.source_type,
                        entry.operable,
                        entry.freshness_days,
                        _json_dumps(tags),
                        _json_dumps(metadata),
                        _safe_datetime(entry.updated_at),
                    )
                )
            await conn.executemany(
                f"""INSERT INTO "{self._schema}"."knowledge_documents"
                       (agent_id, document_key, source_label, source_path, workspace_root, layer, scope, title, content,
                        owner, project_key, environment, team, source_type, operable, freshness_days, tags_json,
                        metadata_json, content_hash, object_key, updated_at)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16,
                               $17::jsonb, $18::jsonb, $19, $20, $21)
                       ON CONFLICT (agent_id, document_key) DO UPDATE SET
                           source_label = EXCLUDED.source_label,
                           source_path = EXCLUDED.source_path,
                           workspace_root = EXCLUDED.workspace_root,
                           layer = EXCLUDED.layer,
                           scope = EXCLUDED.scope,
                           title = EXCLUDED.title,
                           content = EXCLUDED.content,
                           owner = EXCLUDED.owner,
                           project_key = EXCLUDED.project_key,
                           environment = EXCLUDED.environment,
                           team = EXCLUDED.team,
                           source_type = EXCLUDED.source_type,
                           operable = EXCLUDED.operable,
                           freshness_days = EXCLUDED.freshness_days,
                           tags_json = EXCLUDED.tags_json,
                           metadata_json = EXCLUDED.metadata_json,
                           content_hash = EXCLUDED.content_hash,
                           object_key = EXCLUDED.object_key,
                           updated_at = EXCLUDED.updated_at""",
                rows,
            )
            await conn.executemany(
                f"""INSERT INTO "{self._schema}"."knowledge_chunks"
                       (agent_id, chunk_key, document_key, source_label, source_path, workspace_root, layer, scope,
                        title, content, owner, project_key, environment, team, source_type, operable, freshness_days,
                        tags_json, metadata_json, updated_at)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17,
                               $18::jsonb, $19::jsonb, $20)
                       ON CONFLICT (agent_id, chunk_key) DO UPDATE SET
                           document_key = EXCLUDED.document_key,
                           source_label = EXCLUDED.source_label,
                           source_path = EXCLUDED.source_path,
                           workspace_root = EXCLUDED.workspace_root,
                           layer = EXCLUDED.layer,
                           scope = EXCLUDED.scope,
                           title = EXCLUDED.title,
                           content = EXCLUDED.content,
                           owner = EXCLUDED.owner,
                           project_key = EXCLUDED.project_key,
                           environment = EXCLUDED.environment,
                           team = EXCLUDED.team,
                           source_type = EXCLUDED.source_type,
                           operable = EXCLUDED.operable,
                           freshness_days = EXCLUDED.freshness_days,
                           tags_json = EXCLUDED.tags_json,
                           metadata_json = EXCLUDED.metadata_json,
                           updated_at = EXCLUDED.updated_at""",
                chunk_rows,
            )
        self._invalidate_query_caches()

    async def upsert_embeddings(
        self,
        *,
        entries: list[KnowledgeEntry],
        embeddings: list[list[float]],
        object_key: str,
        model: str = KNOWLEDGE_EMBEDDING_MODEL,
    ) -> None:
        if not entries or not embeddings or not self.bootstrapped:
            return
        async with self._connection() as conn:
            for entry, embedding in zip(entries, embeddings, strict=True):
                document_key = f"{entry.layer.value}:{entry.source_label}:{entry.source_path}"
                vector_literal = _vector_literal(embedding)
                if self._vector_enabled:
                    await conn.execute(
                        f"""INSERT INTO "{self._schema}"."knowledge_embeddings"
                               (agent_id, embedding_key, chunk_key, document_key, model, vector_json, payload_json,
                                object_key, embedding_vector)
                               VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, $9::vector)
                               ON CONFLICT (agent_id, embedding_key) DO UPDATE SET
                                   chunk_key = EXCLUDED.chunk_key,
                                   document_key = EXCLUDED.document_key,
                                   model = EXCLUDED.model,
                                   vector_json = EXCLUDED.vector_json,
                                   payload_json = EXCLUDED.payload_json,
                                   object_key = EXCLUDED.object_key,
                                   embedding_vector = EXCLUDED.embedding_vector,
                                   updated_at = NOW()""",
                        self._agent_id,
                        entry.id,
                        entry.id,
                        document_key,
                        model,
                        _json_dumps(embedding),
                        _json_dumps({"source_label": entry.source_label, "source_path": entry.source_path}),
                        object_key,
                        vector_literal,
                    )
                else:
                    await conn.execute(
                        f"""INSERT INTO "{self._schema}"."knowledge_embeddings"
                               (agent_id, embedding_key, chunk_key, document_key, model, vector_json, payload_json, object_key)
                               VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8)
                               ON CONFLICT (agent_id, embedding_key) DO UPDATE SET
                                   chunk_key = EXCLUDED.chunk_key,
                                   document_key = EXCLUDED.document_key,
                                   model = EXCLUDED.model,
                                   vector_json = EXCLUDED.vector_json,
                                   payload_json = EXCLUDED.payload_json,
                                   object_key = EXCLUDED.object_key,
                                   updated_at = NOW()""",
                        self._agent_id,
                        entry.id,
                        entry.id,
                        document_key,
                        model,
                        _json_dumps(embedding),
                        _json_dumps({"source_label": entry.source_label, "source_path": entry.source_path}),
                        object_key,
                    )
        self._invalidate_query_caches()

    async def persist_retrieval_bundle(self, *, task_id: int | None, payload: dict[str, Any], object_key: str) -> None:
        if not self.bootstrapped:
            return
        async with self._connection() as conn:
            await conn.execute(
                f"""INSERT INTO "{self._schema}"."retrieval_bundles"
                       (agent_id, task_id, payload_json, object_key)
                       VALUES ($1, $2, $3::jsonb, $4)""",
                self._agent_id,
                task_id,
                _json_dumps(payload),
                object_key,
            )

    async def persist_retrieval_trace(self, *, trace: RetrievalTrace) -> int | None:
        if not trace.hits or not self.bootstrapped:
            return None
        async with self._connection() as conn:
            trace_id = await conn.fetchval(
                f"""INSERT INTO "{self._schema}"."retrieval_traces"
                       (agent_id, task_id, query_text, strategy, route, project_key, environment, team, graph_hops,
                        grounding_score, required_citation_count, conflict_reasons_json, evidence_modalities_json,
                        winning_sources_json, explanation, experiment_key, trace_role, paired_trace_id, payload_json)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb, $13::jsonb, $14::jsonb,
                               $15, $16, $17, $18, $19::jsonb)
                       RETURNING id""",
                trace.agent_id or self._agent_id,
                trace.task_id,
                trace.query,
                trace.strategy.value,
                trace.route,
                trace.project_key,
                trace.environment,
                trace.team,
                trace.graph_hops,
                trace.grounding_score,
                trace.required_citation_count,
                _json_dumps(list(trace.conflict_reasons)),
                _json_dumps([item.value for item in trace.evidence_modalities]),
                _json_dumps(list(trace.winning_sources)),
                trace.explanation,
                trace.experiment_key,
                trace.trace_role.value,
                trace.paired_trace_id,
                _json_dumps(trace.to_dict()),
            )
            if trace_id is None:
                return None
            await conn.executemany(
                f"""INSERT INTO "{self._schema}"."retrieval_trace_hits"
                       (trace_id, hit_id, title, layer, source_label, similarity, freshness, selected,
                        rank_before, rank_after, graph_hops, graph_score, reasons_json, exclusion_reason,
                        evidence_modalities_json, supporting_evidence_keys_json)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::jsonb, $14, $15::jsonb, $16::jsonb)""",
                [
                    (
                        trace_id,
                        hit.hit_id,
                        hit.title,
                        hit.layer,
                        hit.source_label,
                        hit.similarity,
                        hit.freshness,
                        hit.selected,
                        hit.rank_before,
                        hit.rank_after,
                        hit.graph_hops,
                        hit.graph_score,
                        _json_dumps(list(hit.reasons)),
                        hit.exclusion_reason,
                        _json_dumps([item.value for item in hit.evidence_modalities]),
                        _json_dumps(list(hit.supporting_evidence_keys)),
                    )
                    for hit in trace.hits
                ],
            )
            return int(trace_id)

    async def persist_answer_trace(
        self, *, task_id: int | None, payload: dict[str, Any], object_key: str
    ) -> int | None:
        if not self.bootstrapped:
            return None

        grounded_answer = dict(payload.get("grounded_answer") or {})
        judgement = dict(payload.get("judge_result") or {})
        async with self._connection() as conn:
            answer_trace_id = await conn.fetchval(
                f"""INSERT INTO "{self._schema}"."answer_traces"
                       (agent_id, task_id, operational_status, answer_text, citations_json,
                        supporting_evidence_refs_json, uncertainty_notes_json, answer_plan_json, metadata_json,
                        judge_json, authoritative_sources_json, supporting_sources_json, uncertainty_json,
                        payload_json, object_key)
                       VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7::jsonb, $8::jsonb, $9::jsonb,
                               $10::jsonb, $11::jsonb, $12::jsonb, $13::jsonb, $14::jsonb, $15)
                       RETURNING id""",
                self._agent_id,
                task_id,
                str(grounded_answer.get("operational_status") or ""),
                str(grounded_answer.get("answer_text") or ""),
                _json_dumps(list(grounded_answer.get("citations") or [])),
                _json_dumps(list(grounded_answer.get("supporting_evidence_refs") or [])),
                _json_dumps(list(grounded_answer.get("uncertainty_notes") or [])),
                _json_dumps(dict(grounded_answer.get("answer_plan") or {})),
                _json_dumps(dict(grounded_answer.get("metadata") or {})),
                _json_dumps(judgement),
                _json_dumps(list(payload.get("authoritative_sources") or [])),
                _json_dumps(list(payload.get("supporting_sources") or [])),
                _json_dumps(dict(payload.get("uncertainty") or {})),
                _json_dumps(payload),
                object_key,
            )
            if answer_trace_id is None:
                return None
            await conn.execute(
                f"""INSERT INTO "{self._schema}"."answer_judgements"
                       (answer_trace_id, agent_id, task_id, status, reasons_json, warnings_json, citation_coverage,
                        citation_span_precision, contradiction_escape_rate, policy_compliance, requires_review,
                        safe_response, payload_json)
                       VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8, $9, $10, $11, $12, $13::jsonb)""",
                answer_trace_id,
                self._agent_id,
                task_id,
                str(judgement.get("status") or ""),
                _json_dumps(list(judgement.get("reasons") or [])),
                _json_dumps(list(judgement.get("warnings") or [])),
                float(judgement.get("citation_coverage") or 0.0),
                float(judgement.get("citation_span_precision") or 0.0),
                float(judgement.get("contradiction_escape_rate") or 0.0),
                float(judgement.get("policy_compliance") or 0.0),
                bool(judgement.get("requires_review") or False),
                str(judgement.get("safe_response") or ""),
                _json_dumps(judgement),
            )
            return int(answer_trace_id)

    async def persist_audit_event(
        self,
        *,
        event_type: str,
        timestamp: datetime | str | None,
        pod_name: str,
        user_id: int | None,
        task_id: int | None,
        trace_id: str | None,
        details: dict[str, Any],
        cost_usd: float | None,
        duration_ms: float | None,
    ) -> int | None:
        if not event_type or not self.bootstrapped:
            return None
        async with self._connection() as conn:
            event_id = await conn.fetchval(
                f"""INSERT INTO "{self._schema}"."audit_events"
                       (agent_id, timestamp, event_type, pod_name, user_id, task_id, trace_id, details_json, cost_usd, duration_ms)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10)
                       RETURNING id""",
                self._agent_id,
                _coerce_datetime(timestamp),
                str(event_type).strip(),
                str(pod_name or "").strip(),
                user_id,
                task_id,
                str(trace_id or "").strip(),
                _json_dumps(details),
                cost_usd,
                duration_ms,
            )
            return int(event_id) if event_id is not None else None

    async def list_audit_events(
        self,
        *,
        limit: int = 50,
        user_id: int | None = None,
        event_type: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self.bootstrapped:
            return []
        clauses = ["agent_id = $1"]
        params: list[Any] = [self._agent_id]
        if user_id is not None:
            params.append(user_id)
            clauses.append(f"user_id = ${len(params)}")
        if event_type is not None:
            params.append(str(event_type).strip())
            clauses.append(f"event_type = ${len(params)}")
        params.append(max(1, int(limit)))
        async with self._connection() as conn:
            rows = await conn.fetch(
                f"""SELECT id, timestamp, event_type, agent_id, pod_name, user_id, task_id, trace_id,
                           details_json, cost_usd, duration_ms
                      FROM "{self._schema}"."audit_events"
                     WHERE {" AND ".join(clauses)}
                  ORDER BY id DESC
                     LIMIT ${len(params)}""",
                *params,
            )
        return [
            {
                "id": int(row["id"]),
                "timestamp": str(row["timestamp"]),
                "event_type": str(row["event_type"]),
                "agent_id": str(row["agent_id"]),
                "pod_name": str(row["pod_name"] or ""),
                "user_id": row["user_id"],
                "task_id": row["task_id"],
                "trace_id": str(row["trace_id"] or ""),
                "details": dict(row["details_json"] or {}),
                "cost_usd": row["cost_usd"],
                "duration_ms": row["duration_ms"],
            }
            for row in rows
        ]

    async def persist_query_log(
        self,
        *,
        user_id: int,
        timestamp: datetime | str | None,
        query_text: str,
        response_text: str,
        cost_usd: float,
        provider: str,
        model: str,
        session_id: str | None,
        provider_session_id: str | None,
        usage: dict[str, Any] | None,
        work_dir: str,
        error: bool,
        squad_thread_id: str | None = None,
        squad_message_id: str | None = None,
        squad_task_id: str | None = None,
    ) -> int | None:
        if not self.bootstrapped:
            return None
        async with self._connection() as conn:
            row_id = await conn.fetchval(
                f"""INSERT INTO "{self._schema}"."query_history"
                       (agent_id, user_id, timestamp, query_text, response_text, cost_usd, provider, model,
                        session_id, provider_session_id, usage_json, work_dir, error,
                        squad_thread_id, squad_message_id, squad_task_id)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12, $13,
                               $14::uuid, $15, $16::uuid)
                       RETURNING id""",
                self._agent_id,
                user_id,
                _coerce_datetime(timestamp),
                query_text,
                response_text,
                float(cost_usd or 0.0),
                str(provider or "claude"),
                str(model or ""),
                session_id,
                provider_session_id,
                _json_dumps(usage or {}),
                str(work_dir or ""),
                bool(error),
                str(squad_thread_id) if squad_thread_id else None,
                str(squad_message_id) if squad_message_id else None,
                str(squad_task_id) if squad_task_id else None,
            )
            return int(row_id) if row_id is not None else None

    async def list_query_history(self, *, user_id: int, limit: int = 10) -> list[dict[str, Any]]:
        if not self.bootstrapped:
            return []
        async with self._connection() as conn:
            rows = await conn.fetch(
                f"""SELECT timestamp, provider, model, cost_usd, query_text, error
                      FROM "{self._schema}"."query_history"
                     WHERE agent_id = $1 AND user_id = $2
                  ORDER BY id DESC
                     LIMIT $3""",
                self._agent_id,
                user_id,
                max(1, int(limit)),
            )
        return [
            {
                "timestamp": str(row["timestamp"]),
                "provider": str(row["provider"] or "claude"),
                "model": str(row["model"] or ""),
                "cost_usd": float(row["cost_usd"] or 0.0),
                "query_text": str(row["query_text"] or ""),
                "error": bool(row["error"]),
            }
            for row in rows
        ]

    async def list_full_query_history(self, *, user_id: int) -> list[dict[str, Any]]:
        if not self.bootstrapped:
            return []
        async with self._connection() as conn:
            rows = await conn.fetch(
                f"""SELECT timestamp, provider, model, cost_usd, query_text, response_text, work_dir, error
                      FROM "{self._schema}"."query_history"
                     WHERE agent_id = $1 AND user_id = $2
                  ORDER BY id ASC""",
                self._agent_id,
                user_id,
            )
        return [
            {
                "timestamp": str(row["timestamp"]),
                "provider": str(row["provider"] or "claude"),
                "model": str(row["model"] or ""),
                "cost_usd": float(row["cost_usd"] or 0.0),
                "query_text": str(row["query_text"] or ""),
                "response_text": str(row["response_text"] or ""),
                "work_dir": str(row["work_dir"] or ""),
                "error": bool(row["error"]),
            }
            for row in rows
        ]

    async def count_recent_queries(self, *, user_id: int, since: datetime | str) -> int:
        if not self.bootstrapped:
            return 0
        async with self._connection() as conn:
            value = await conn.fetchval(
                f"""SELECT COUNT(*)
                      FROM "{self._schema}"."query_history"
                     WHERE agent_id = $1 AND user_id = $2 AND timestamp >= $3""",
                self._agent_id,
                user_id,
                _coerce_datetime(since),
            )
        return int(value or 0)

    async def get_user_cost_total(self, *, user_id: int) -> dict[str, Any] | None:
        if not self.bootstrapped:
            return None
        async with self._connection() as conn:
            row = await conn.fetchrow(
                f"""SELECT total_cost, query_count
                      FROM "{self._schema}"."user_cost_totals"
                     WHERE agent_id = $1 AND user_id = $2""",
                self._agent_id,
                user_id,
            )
        if row is None:
            return None
        return {
            "total_cost": float(row["total_cost"] or 0.0),
            "query_count": int(row["query_count"] or 0),
        }

    async def upsert_user_cost_total(
        self,
        *,
        user_id: int,
        total_cost: float,
        query_count: int,
        updated_at: datetime | str | None = None,
    ) -> None:
        if not self.bootstrapped:
            return
        async with self._connection() as conn:
            await conn.execute(
                f"""INSERT INTO "{self._schema}"."user_cost_totals"
                       (agent_id, user_id, total_cost, query_count, updated_at)
                       VALUES ($1, $2, $3, $4, $5)
                       ON CONFLICT (agent_id, user_id) DO UPDATE SET
                           total_cost = EXCLUDED.total_cost,
                           query_count = EXCLUDED.query_count,
                           updated_at = EXCLUDED.updated_at""",
                self._agent_id,
                user_id,
                float(total_cost),
                int(query_count),
                _coerce_datetime(updated_at),
            )

    async def delete_user_cost_total(self, *, user_id: int) -> None:
        if not self.bootstrapped:
            return
        async with self._connection() as conn:
            await conn.execute(
                f"""DELETE FROM "{self._schema}"."user_cost_totals"
                     WHERE agent_id = $1 AND user_id = $2""",
                self._agent_id,
                user_id,
            )

    async def upsert_digest_preference(
        self,
        *,
        user_id: int,
        chat_id: int,
        enabled: bool,
        send_hour: int,
        send_minute: int,
        timezone: str,
    ) -> None:
        if not self.bootstrapped:
            return
        async with self._connection() as conn:
            await conn.execute(
                f"""INSERT INTO "{self._schema}"."digest_preferences"
                       (agent_id, user_id, chat_id, enabled, send_hour, send_minute, timezone)
                       VALUES ($1, $2, $3, $4, $5, $6, $7)
                       ON CONFLICT (agent_id, user_id) DO UPDATE SET
                           chat_id = EXCLUDED.chat_id,
                           enabled = EXCLUDED.enabled,
                           send_hour = EXCLUDED.send_hour,
                           send_minute = EXCLUDED.send_minute,
                           timezone = EXCLUDED.timezone,
                           updated_at = NOW()""",
                self._agent_id,
                user_id,
                chat_id,
                bool(enabled),
                int(send_hour),
                int(send_minute),
                str(timezone or "UTC"),
            )

    async def get_digest_preference(self, *, user_id: int) -> dict[str, Any] | None:
        if not self.bootstrapped:
            return None
        async with self._connection() as conn:
            row = await conn.fetchrow(
                f"""SELECT user_id, chat_id, enabled, send_hour, send_minute, timezone, last_sent_date
                      FROM "{self._schema}"."digest_preferences"
                     WHERE agent_id = $1 AND user_id = $2""",
                self._agent_id,
                user_id,
            )
        if row is None:
            return None
        return {
            "user_id": int(row["user_id"]),
            "chat_id": int(row["chat_id"]),
            "enabled": bool(row["enabled"]),
            "send_hour": int(row["send_hour"]),
            "send_minute": int(row["send_minute"]),
            "timezone": str(row["timezone"] or "UTC"),
            "last_sent_date": row["last_sent_date"],
        }

    async def list_enabled_digest_preferences(self) -> list[dict[str, Any]]:
        if not self.bootstrapped:
            return []
        async with self._connection() as conn:
            rows = await conn.fetch(
                f"""SELECT user_id, chat_id, enabled, send_hour, send_minute, timezone, last_sent_date
                      FROM "{self._schema}"."digest_preferences"
                     WHERE agent_id = $1 AND enabled = TRUE
                  ORDER BY user_id ASC""",
                self._agent_id,
            )
        return [
            {
                "user_id": int(row["user_id"]),
                "chat_id": int(row["chat_id"]),
                "enabled": bool(row["enabled"]),
                "send_hour": int(row["send_hour"]),
                "send_minute": int(row["send_minute"]),
                "timezone": str(row["timezone"] or "UTC"),
                "last_sent_date": row["last_sent_date"],
            }
            for row in rows
        ]

    async def mark_digest_sent(self, *, user_id: int, date_str: str) -> None:
        if not self.bootstrapped:
            return
        async with self._connection() as conn:
            await conn.execute(
                f"""UPDATE "{self._schema}"."digest_preferences"
                       SET last_sent_date = $3, updated_at = NOW()
                     WHERE agent_id = $1 AND user_id = $2""",
                self._agent_id,
                user_id,
                str(date_str or ""),
            )

    async def delete_digest_preference(self, *, user_id: int) -> bool:
        if not self.bootstrapped:
            return False
        async with self._connection() as conn:
            result = await conn.execute(
                f"""DELETE FROM "{self._schema}"."digest_preferences"
                     WHERE agent_id = $1 AND user_id = $2""",
                self._agent_id,
                user_id,
            )
        return str(result).endswith("1")

    async def upsert_graph(self, *, entities: list[GraphEntity], relations: list[GraphRelation]) -> None:
        if (not entities and not relations) or not self.bootstrapped:
            return
        async with self._connection() as conn:
            if entities:
                await conn.executemany(
                    f"""INSERT INTO "{self._schema}"."knowledge_entities"
                           (agent_id, entity_key, entity_type, label, source_kind, metadata_json)
                           VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                           ON CONFLICT (agent_id, entity_key) DO UPDATE SET
                               entity_type = EXCLUDED.entity_type,
                               label = EXCLUDED.label,
                               source_kind = EXCLUDED.source_kind,
                               metadata_json = EXCLUDED.metadata_json,
                               updated_at = NOW()""",
                    [
                        (
                            entity.agent_id or self._agent_id,
                            entity.entity_key,
                            entity.entity_type,
                            entity.label,
                            entity.source_kind,
                            _json_dumps(entity.metadata or {}),
                        )
                        for entity in entities
                    ],
                )
            if relations:
                await conn.executemany(
                    f"""INSERT INTO "{self._schema}"."knowledge_relations"
                           (agent_id, relation_key, relation_type, source_entity_key, target_entity_key, weight, metadata_json)
                           VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                           ON CONFLICT (agent_id, relation_key) DO UPDATE SET
                               relation_type = EXCLUDED.relation_type,
                               source_entity_key = EXCLUDED.source_entity_key,
                               target_entity_key = EXCLUDED.target_entity_key,
                               weight = EXCLUDED.weight,
                               metadata_json = EXCLUDED.metadata_json,
                               updated_at = NOW()""",
                    [
                        (
                            relation.agent_id or self._agent_id,
                            relation.relation_key,
                            relation.relation_type,
                            relation.source_entity_key,
                            relation.target_entity_key,
                            relation.weight,
                            _json_dumps(relation.metadata or {}),
                        )
                        for relation in relations
                    ],
                )
        self._invalidate_query_caches()

    async def upsert_artifact_derivatives(
        self,
        *,
        task_id: int | None,
        derivatives: list[ArtifactDerivative],
        object_key: str,
        enqueue_jobs: bool = True,
    ) -> None:
        if not derivatives or not self.bootstrapped:
            return
        async with self._connection() as conn:
            for item in derivatives:
                provenance = dict(item.provenance)
                embedding_value = provenance.get("embedding")
                embedding = [float(value) for value in embedding_value] if isinstance(embedding_value, list) else []
                project_key = str(provenance.get("project_key") or "")
                workspace_fingerprint = str(provenance.get("workspace_fingerprint") or "")
                await conn.execute(
                    f"""INSERT INTO "{self._schema}"."artifact_manifests"
                           (agent_id, task_id, artifact_id, source_path, source_url, object_key, metadata_json)
                           VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                           ON CONFLICT (agent_id, artifact_id) DO UPDATE SET
                               task_id = EXCLUDED.task_id,
                               source_path = EXCLUDED.source_path,
                               source_url = EXCLUDED.source_url,
                               object_key = EXCLUDED.object_key,
                               metadata_json = EXCLUDED.metadata_json""",
                    self._agent_id,
                    task_id,
                    item.artifact_id,
                    item.source_path,
                    item.source_url,
                    object_key,
                    _json_dumps(provenance),
                )
                if self._vector_enabled and embedding:
                    await conn.execute(
                        f"""INSERT INTO "{self._schema}"."artifact_derivatives"
                               (agent_id, task_id, derivative_key, artifact_id, project_key, workspace_fingerprint,
                                modality, label, extracted_text, confidence, trust_level, source_path, source_url,
                                source_object_key, time_span, frame_ref, provenance_json, embedding_json, embedding_vector)
                               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16,
                                       $17::jsonb, $18::jsonb, $19::vector)
                               ON CONFLICT (agent_id, derivative_key) DO UPDATE SET
                                   task_id = EXCLUDED.task_id,
                                   artifact_id = EXCLUDED.artifact_id,
                                   project_key = EXCLUDED.project_key,
                                   workspace_fingerprint = EXCLUDED.workspace_fingerprint,
                                   modality = EXCLUDED.modality,
                                   label = EXCLUDED.label,
                                   extracted_text = EXCLUDED.extracted_text,
                                   confidence = EXCLUDED.confidence,
                                   trust_level = EXCLUDED.trust_level,
                                   source_path = EXCLUDED.source_path,
                                   source_url = EXCLUDED.source_url,
                                   source_object_key = EXCLUDED.source_object_key,
                                   time_span = EXCLUDED.time_span,
                                   frame_ref = EXCLUDED.frame_ref,
                                   provenance_json = EXCLUDED.provenance_json,
                                   embedding_json = EXCLUDED.embedding_json,
                                   embedding_vector = EXCLUDED.embedding_vector""",
                        self._agent_id,
                        task_id,
                        item.derivative_key,
                        item.artifact_id,
                        project_key,
                        workspace_fingerprint,
                        item.modality.value,
                        item.label,
                        item.extracted_text,
                        item.confidence,
                        item.trust_level,
                        item.source_path,
                        item.source_url,
                        object_key,
                        item.time_span,
                        item.frame_ref,
                        _json_dumps(provenance),
                        _json_dumps(embedding),
                        _vector_literal(embedding),
                    )
                else:
                    await conn.execute(
                        f"""INSERT INTO "{self._schema}"."artifact_derivatives"
                               (agent_id, task_id, derivative_key, artifact_id, project_key, workspace_fingerprint,
                                modality, label, extracted_text, confidence, trust_level, source_path, source_url,
                                source_object_key, time_span, frame_ref, provenance_json, embedding_json)
                               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16,
                                       $17::jsonb, $18::jsonb)
                               ON CONFLICT (agent_id, derivative_key) DO UPDATE SET
                                   task_id = EXCLUDED.task_id,
                                   artifact_id = EXCLUDED.artifact_id,
                                   project_key = EXCLUDED.project_key,
                                   workspace_fingerprint = EXCLUDED.workspace_fingerprint,
                                   modality = EXCLUDED.modality,
                                   label = EXCLUDED.label,
                                   extracted_text = EXCLUDED.extracted_text,
                                   confidence = EXCLUDED.confidence,
                                   trust_level = EXCLUDED.trust_level,
                                   source_path = EXCLUDED.source_path,
                                   source_url = EXCLUDED.source_url,
                                   source_object_key = EXCLUDED.source_object_key,
                                   time_span = EXCLUDED.time_span,
                                   frame_ref = EXCLUDED.frame_ref,
                                   provenance_json = EXCLUDED.provenance_json,
                                   embedding_json = EXCLUDED.embedding_json""",
                        self._agent_id,
                        task_id,
                        item.derivative_key,
                        item.artifact_id,
                        project_key,
                        workspace_fingerprint,
                        item.modality.value,
                        item.label,
                        item.extracted_text,
                        item.confidence,
                        item.trust_level,
                        item.source_path,
                        item.source_url,
                        object_key,
                        item.time_span,
                        item.frame_ref,
                        _json_dumps(provenance),
                        _json_dumps(embedding),
                    )
                if enqueue_jobs:
                    await conn.execute(
                        f"""INSERT INTO "{self._schema}"."knowledge_ingest_jobs"
                               (agent_id, job_key, task_id, artifact_id, job_type, status, source_path, source_url, payload_json)
                               VALUES ($1, $2, $3, $4, $5, 'ready', $6, $7, $8::jsonb)
                               ON CONFLICT (agent_id, job_key) DO UPDATE SET
                                   task_id = EXCLUDED.task_id,
                                   artifact_id = EXCLUDED.artifact_id,
                                   source_path = EXCLUDED.source_path,
                                   source_url = EXCLUDED.source_url,
                                   payload_json = EXCLUDED.payload_json,
                                   updated_at = NOW()""",
                        self._agent_id,
                        f"derivative:{item.derivative_key}",
                        task_id,
                        item.artifact_id,
                        "artifact_derivative",
                        item.source_path,
                        item.source_url,
                        _json_dumps(
                            {
                                "derivative_key": item.derivative_key,
                                "modality": item.modality.value,
                                "label": item.label,
                            }
                        ),
                    )

    async def list_artifact_derivative_rows(
        self,
        *,
        task_id: int | None,
        project_key: str,
        workspace_fingerprint: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if not self.bootstrapped:
            return []
        async with self._connection() as conn:
            rows = await conn.fetch(
                f"""SELECT derivative_key AS evidence_key, modality, label, extracted_text, confidence, trust_level,
                              source_path, source_url, provenance_json, embedding_json, project_key, workspace_fingerprint,
                              artifact_id, time_span, frame_ref, created_at
                       FROM "{self._schema}"."artifact_derivatives"
                      WHERE agent_id = $1
                        AND ($2::BIGINT IS NULL OR task_id = $2)
                        AND ($3 = '' OR project_key = '' OR project_key = $3)
                        AND ($4 = '' OR workspace_fingerprint = '' OR workspace_fingerprint = $4)
                      ORDER BY created_at DESC
                      LIMIT $5""",
                self._agent_id,
                task_id,
                project_key or "",
                workspace_fingerprint or "",
                limit,
            )
        items = []
        for row in rows:
            item = dict(row)
            item["metadata"] = dict(item.pop("provenance_json") or {})
            item["embedding"] = list(item.pop("embedding_json") or [])
            items.append(item)
        return items

    async def list_answer_traces(self, *, task_id: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if not self.bootstrapped:
            return []
        async with self._connection() as conn:
            rows = await conn.fetch(
                f"""SELECT id, agent_id, task_id, operational_status, answer_text, citations_json,
                              supporting_evidence_refs_json, uncertainty_notes_json, answer_plan_json, metadata_json,
                              judge_json, authoritative_sources_json, supporting_sources_json, uncertainty_json, created_at
                       FROM "{self._schema}"."answer_traces"
                      WHERE agent_id = $1 AND ($2::BIGINT IS NULL OR task_id = $2)
                      ORDER BY id DESC LIMIT $3""",
                self._agent_id,
                task_id,
                limit,
            )
        return [self._answer_trace_record(dict(row)) for row in rows]

    async def get_answer_trace(self, answer_trace_id: int) -> dict[str, Any] | None:
        traces = await self._fetch_answer_trace_rows(answer_trace_id=answer_trace_id)
        return traces[0] if traces else None

    async def get_latest_answer_trace(self, task_id: int) -> dict[str, Any] | None:
        items = await self.list_answer_traces(task_id=task_id, limit=1)
        return items[0] if items else None

    async def list_retrieval_traces(
        self,
        *,
        task_id: int | None = None,
        strategy: str | None = None,
        experiment_key: str | None = None,
        trace_role: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if not self.bootstrapped:
            return []
        async with self._connection() as conn:
            rows = await conn.fetch(
                f"""SELECT id, agent_id, task_id, query_text, strategy, route, project_key, environment, team,
                              graph_hops, grounding_score, required_citation_count, conflict_reasons_json,
                              evidence_modalities_json, winning_sources_json, explanation, experiment_key,
                              trace_role, paired_trace_id, created_at
                       FROM "{self._schema}"."retrieval_traces"
                      WHERE agent_id = $1
                        AND ($2::BIGINT IS NULL OR task_id = $2)
                        AND ($3 = '' OR strategy = $3)
                        AND ($4 = '' OR experiment_key = $4)
                        AND ($5 = '' OR trace_role = $5)
                      ORDER BY id DESC LIMIT $6""",
                self._agent_id,
                task_id,
                strategy or "",
                experiment_key or "",
                trace_role or "",
                limit,
            )
            trace_ids = [int(row["id"]) for row in rows]
            hits_by_trace = await self._list_trace_hits_many(conn, trace_ids)
        items = []
        for row in rows:
            payload = dict(row)
            payload["hits"] = hits_by_trace.get(int(row["id"]), [])
            items.append(self._retrieval_trace_record(payload))
        return items

    async def get_retrieval_trace(self, trace_id: int) -> dict[str, Any] | None:
        if not self.bootstrapped:
            return None
        async with self._connection() as conn:
            row = await conn.fetchrow(
                f"""SELECT id, agent_id, task_id, query_text, strategy, route, project_key, environment, team,
                              graph_hops, grounding_score, required_citation_count, conflict_reasons_json,
                              evidence_modalities_json, winning_sources_json, explanation, experiment_key,
                              trace_role, paired_trace_id, created_at
                       FROM "{self._schema}"."retrieval_traces"
                      WHERE agent_id = $1 AND id = $2""",
                self._agent_id,
                trace_id,
            )
            if row is None:
                return None
            hits_by_trace = await self._list_trace_hits_many(conn, [trace_id])
        payload = dict(row)
        payload["hits"] = hits_by_trace.get(trace_id, [])
        return self._retrieval_trace_record(payload)

    async def enqueue_ingest_job(
        self,
        *,
        job_key: str,
        task_id: int | None,
        artifact_id: str,
        job_type: str = "artifact_derivative",
        payload: dict[str, Any],
        source_path: str = "",
        source_url: str = "",
        priority: int = 50,
    ) -> None:
        if not self.bootstrapped:
            return
        async with self._connection() as conn:
            await conn.execute(
                f"""INSERT INTO "{self._schema}"."knowledge_ingest_jobs"
                       (agent_id, job_key, task_id, artifact_id, job_type, priority, source_path, source_url, payload_json)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
                       ON CONFLICT (agent_id, job_key) DO UPDATE SET
                           task_id = EXCLUDED.task_id,
                           artifact_id = EXCLUDED.artifact_id,
                           job_type = EXCLUDED.job_type,
                           priority = EXCLUDED.priority,
                           source_path = EXCLUDED.source_path,
                           source_url = EXCLUDED.source_url,
                           payload_json = EXCLUDED.payload_json,
                           updated_at = NOW()""",
                self._agent_id,
                job_key,
                task_id,
                artifact_id,
                job_type,
                priority,
                source_path,
                source_url,
                _json_dumps(payload),
            )

    async def list_ingest_jobs(self, *, status: str = "ready", limit: int = 100) -> list[dict[str, Any]]:
        if not self.bootstrapped:
            return []
        async with self._connection() as conn:
            rows = await conn.fetch(
                f"""SELECT id, job_key, task_id, artifact_id, job_type, status, priority, source_path, source_url,
                              payload_json, attempts, available_at, leased_at, lease_owner, created_at, updated_at
                       FROM "{self._schema}"."knowledge_ingest_jobs"
                      WHERE agent_id = $1 AND status = $2
                      ORDER BY priority ASC, available_at ASC
                      LIMIT $3""",
                self._agent_id,
                status,
                limit,
            )
        return [dict(row) for row in rows]

    async def lease_ingest_jobs(
        self,
        *,
        worker_id: str,
        limit: int = 10,
        lease_seconds: int = 60,
    ) -> list[dict[str, Any]]:
        if not self.bootstrapped:
            return []
        async with self._connection() as conn:
            rows = await conn.fetch(
                f"""WITH candidate AS (
                           SELECT id
                             FROM "{self._schema}"."knowledge_ingest_jobs"
                            WHERE agent_id = $1
                              AND available_at <= NOW()
                              AND (
                                    status = 'ready'
                                 OR (status = 'leased' AND leased_at < NOW() - make_interval(secs => $4))
                              )
                            ORDER BY priority ASC, available_at ASC, id ASC
                            LIMIT $2
                            FOR UPDATE SKIP LOCKED
                       )
                       UPDATE "{self._schema}"."knowledge_ingest_jobs" job
                          SET status = 'leased',
                              lease_owner = $3,
                              leased_at = NOW(),
                              attempts = job.attempts + 1,
                              updated_at = NOW()
                         FROM candidate
                        WHERE job.id = candidate.id
                    RETURNING job.id, job.job_key, job.task_id, job.artifact_id, job.job_type, job.status,
                              job.priority, job.source_path, job.source_url, job.payload_json, job.attempts,
                              job.available_at, job.leased_at, job.lease_owner, job.created_at, job.updated_at""",
                self._agent_id,
                max(1, limit),
                worker_id,
                max(1, lease_seconds),
            )
        return [dict(row) for row in rows]

    async def complete_ingest_job(self, *, job_id: int, result: dict[str, Any] | None = None) -> None:
        if not self.bootstrapped:
            return
        result_payload = dict(result or {})
        async with self._connection() as conn:
            await conn.execute(
                f"""UPDATE "{self._schema}"."knowledge_ingest_jobs"
                       SET status = 'completed',
                           lease_owner = '',
                           leased_at = NULL,
                           payload_json = payload_json || $2::jsonb,
                           updated_at = NOW()
                     WHERE agent_id = $1 AND id = $3""",
                self._agent_id,
                _json_dumps({"_result": result_payload}),
                job_id,
            )

    async def fail_ingest_job(
        self,
        *,
        job_id: int,
        error_message: str,
        retry_delay_seconds: int = 60,
        max_attempts: int = 5,
    ) -> None:
        if not self.bootstrapped:
            return
        async with self._connection() as conn:
            await conn.execute(
                f"""UPDATE "{self._schema}"."knowledge_ingest_jobs"
                       SET status = CASE WHEN attempts >= $2 THEN 'failed' ELSE 'ready' END,
                           lease_owner = '',
                           leased_at = NULL,
                           available_at = CASE
                               WHEN attempts >= $2 THEN available_at
                               ELSE NOW() + make_interval(secs => $3)
                           END,
                           payload_json = payload_json || $4::jsonb,
                           updated_at = NOW()
                     WHERE agent_id = $1 AND id = $5""",
                self._agent_id,
                max(1, max_attempts),
                max(1, retry_delay_seconds),
                _json_dumps({"_last_error": error_message}),
                job_id,
            )

    async def ingest_queue_health(self) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "ready": False}
        if not self._ready:
            return {"enabled": True, "ready": False, "reason": "backend_not_bootstrapped"}
        try:
            async with self._probe_connection() as (conn, _probe_mode):
                rows = await conn.fetch(
                    f"""SELECT status, COUNT(*) AS count, MAX(updated_at) AS updated_at
                           FROM "{self._schema}"."knowledge_ingest_jobs"
                          WHERE agent_id = $1
                          GROUP BY status""",
                    self._agent_id,
                )
                poisoned = await conn.fetchval(
                    f"""SELECT COUNT(*) FROM "{self._schema}"."knowledge_ingest_jobs"
                          WHERE agent_id = $1 AND status = 'failed' AND attempts >= 3""",
                    self._agent_id,
                )
        except Exception as exc:
            return {"enabled": True, "ready": False, "error": str(exc)}
        by_status = {
            str(row["status"]): {
                "count": int(row["count"] or 0),
                "updated_at": str(row["updated_at"] or ""),
            }
            for row in rows
        }
        queue_depth = 0
        for status in ("ready", "leased", "failed"):
            raw_count = by_status.get(status, {}).get("count", 0)
            queue_depth += raw_count if isinstance(raw_count, int) else 0
        poisoned_jobs = int(poisoned or 0)
        degraded_reasons: list[str] = []
        if queue_depth > KNOWLEDGE_V2_INGEST_MAX_QUEUE_DEPTH:
            degraded_reasons.append("queue_depth")
        if poisoned_jobs > KNOWLEDGE_V2_INGEST_MAX_POISONED_JOBS:
            degraded_reasons.append("poisoned_jobs")
        return {
            "enabled": True,
            "ready": not degraded_reasons,
            "queue_depth": queue_depth,
            "ready_jobs": by_status.get("ready", {}).get("count", 0),
            "leased_jobs": by_status.get("leased", {}).get("count", 0),
            "failed_jobs": by_status.get("failed", {}).get("count", 0),
            "completed_jobs": by_status.get("completed", {}).get("count", 0),
            "poisoned_jobs": poisoned_jobs,
            "degraded_reasons": degraded_reasons,
            "by_status": by_status,
        }

    async def _fetch_answer_trace_rows(self, *, answer_trace_id: int) -> list[dict[str, Any]]:
        if not self.bootstrapped:
            return []
        async with self._connection() as conn:
            rows = await conn.fetch(
                f"""SELECT id, agent_id, task_id, operational_status, answer_text, citations_json,
                              supporting_evidence_refs_json, uncertainty_notes_json, answer_plan_json, metadata_json,
                              judge_json, authoritative_sources_json, supporting_sources_json, uncertainty_json, created_at
                       FROM "{self._schema}"."answer_traces"
                      WHERE agent_id = $1 AND id = $2""",
                self._agent_id,
                answer_trace_id,
            )
        return [self._answer_trace_record(dict(row)) for row in rows]

    async def _list_trace_hits(self, trace_id: int) -> list[dict[str, Any]]:
        if not self.bootstrapped:
            return []
        async with self._connection() as conn:
            hits_by_trace = await self._list_trace_hits_many(conn, [trace_id])
        return hits_by_trace.get(trace_id, [])

    async def _list_trace_hits_many(
        self,
        conn: Any,
        trace_ids: list[int],
    ) -> dict[int, list[dict[str, Any]]]:
        if not trace_ids:
            return {}
        rows = await conn.fetch(
            f"""SELECT trace_id, hit_id, title, layer, source_label, similarity, freshness, selected, rank_before,
                          rank_after, graph_hops, graph_score, reasons_json, exclusion_reason,
                          evidence_modalities_json, supporting_evidence_keys_json
                   FROM "{self._schema}"."retrieval_trace_hits"
                  WHERE trace_id = ANY($1::BIGINT[])
                  ORDER BY trace_id DESC, rank_after ASC, id ASC""",
            trace_ids,
        )
        grouped: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            item = dict(row)
            trace_id = int(item.pop("trace_id"))
            item["reasons"] = list(item.pop("reasons_json") or [])
            item["evidence_modalities"] = list(item.pop("evidence_modalities_json") or [])
            item["supporting_evidence_keys"] = list(item.pop("supporting_evidence_keys_json") or [])
            grouped.setdefault(trace_id, []).append(item)
        return grouped

    def _answer_trace_record(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row.get("id"),
            "agent_id": row.get("agent_id"),
            "task_id": row.get("task_id"),
            "operational_status": str(row.get("operational_status") or ""),
            "answer_text": str(row.get("answer_text") or ""),
            "citations": list(row.get("citations_json") or []),
            "supporting_evidence_refs": list(row.get("supporting_evidence_refs_json") or []),
            "uncertainty_notes": list(row.get("uncertainty_notes_json") or []),
            "answer_plan": dict(row.get("answer_plan_json") or {}),
            "metadata": dict(row.get("metadata_json") or {}),
            "judge_result": dict(row.get("judge_json") or {}),
            "authoritative_sources": list(row.get("authoritative_sources_json") or []),
            "supporting_sources": list(row.get("supporting_sources_json") or []),
            "uncertainty": dict(row.get("uncertainty_json") or {}),
            "created_at": row.get("created_at"),
        }

    def _retrieval_trace_record(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row.get("id"),
            "agent_id": row.get("agent_id"),
            "task_id": row.get("task_id"),
            "query": str(row.get("query_text") or ""),
            "strategy": str(row.get("strategy") or ""),
            "route": str(row.get("route") or ""),
            "project_key": str(row.get("project_key") or ""),
            "environment": str(row.get("environment") or ""),
            "team": str(row.get("team") or ""),
            "graph_hops": int(row.get("graph_hops") or 0),
            "grounding_score": float(row.get("grounding_score") or 0.0),
            "required_citation_count": int(row.get("required_citation_count") or 0),
            "conflict_reasons": list(row.get("conflict_reasons_json") or []),
            "evidence_modalities": list(row.get("evidence_modalities_json") or []),
            "winning_sources": list(row.get("winning_sources_json") or []),
            "explanation": str(row.get("explanation") or ""),
            "experiment_key": str(row.get("experiment_key") or ""),
            "trace_role": str(row.get("trace_role") or "primary"),
            "paired_trace_id": row.get("paired_trace_id"),
            "hits": list(row.get("hits") or []),
            "created_at": row.get("created_at"),
        }
