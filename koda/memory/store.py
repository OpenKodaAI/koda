"""Canonical memory storage backed by the primary state backend."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import datetime

from koda.config import STATE_BACKEND
from koda.internal_rpc.memory_engine import MemoryEngineClient, build_memory_engine_client
from koda.logging_config import get_logger
from koda.memory.config import (
    MEMORY_EMBEDDING_REPAIR_BATCH_SIZE,
    MEMORY_MAX_PER_USER,
)
from koda.memory.embedding_queue import (
    EmbeddingJob,
    cancel_embedding_job,
    cancel_embedding_jobs_for_user,
    claim_embedding_jobs,
    get_embedding_job_stats,
    mark_embedding_job_completed,
)
from koda.memory.napkin import (
    add_entry,
    deactivate_all,
    deactivate_entry,
    find_active_duplicate,
    find_conflicting_active_memories,
    get_entry,
    get_stats,
    set_memory_status,
    update_access,
    update_embedding_state,
)
from koda.memory.napkin import batch_deactivate as napkin_batch_deactivate
from koda.memory.napkin import batch_update_access as napkin_batch_update_access
from koda.memory.quality import record_dedup_decision, record_memory_quality_counter
from koda.memory.types import Memory, MemoryLayer, MemoryStatus, MemoryType, RecallResult
from koda.state.agent_scope import normalize_agent_scope

log = get_logger(__name__)


def _coerce_score(raw: object) -> float:
    if isinstance(raw, bool):
        return float(int(raw))
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        try:
            return float(raw)
        except ValueError:
            return 0.0
    return 0.0


def _parse_datetime(raw: object) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _memory_type_from_value(raw: object) -> MemoryType:
    text = str(raw or "").strip().lower()
    try:
        return MemoryType(text)
    except ValueError:
        return MemoryType.FACT


class MemoryStore:
    """Manages canonical memory state with primary-backend semantic retrieval."""

    def __init__(self, agent_id: str | None, user_id: int | str | None = None) -> None:
        bid = normalize_agent_scope(agent_id, user_id=user_id)
        self._agent_id = bid
        self._vector_index_mode = "canonical"
        self._repair_lock = asyncio.Lock()
        self._memory_engine: MemoryEngineClient = build_memory_engine_client(agent_id=bid)
        self._memory_engine_started = False
        self._memory_engine_lock = asyncio.Lock()
        log.info(
            "memory_store_initialized",
            agent_id=bid,
            vector_index_mode=self._vector_index_mode,
            state_backend=STATE_BACKEND,
        )

    @property
    def agent_id(self) -> str:
        return self._agent_id

    def _hydrate_memory(self, memory: Memory) -> Memory:
        memory.agent_id = normalize_agent_scope(memory.agent_id, fallback=self._agent_id)
        memory.embedding_status = memory.embedding_status or "pending"
        return memory

    def _persist_canonical(self, memory: Memory) -> Memory:
        row_id = add_entry(memory)
        memory.id = row_id
        return memory

    def _matches_filters(
        self,
        memory: Memory,
        *,
        memory_types: list[MemoryType] | None = None,
        project_key: str = "",
        environment: str = "",
        team: str = "",
        origin_kinds: list[str] | None = None,
        memory_statuses: list[str] | None = None,
        session_id: str | None = None,
        source_query_id: int | None = None,
        source_task_id: int | None = None,
        source_episode_id: int | None = None,
    ) -> bool:
        if memory_types and memory.memory_type not in memory_types:
            return False
        if project_key and memory.project_key not in {project_key, ""}:
            return False
        if environment and memory.environment not in {environment, ""}:
            return False
        if team and memory.team not in {team, ""}:
            return False
        if origin_kinds and memory.origin_kind not in set(origin_kinds):
            return False
        if memory_statuses:
            if memory.memory_status not in set(memory_statuses):
                return False
        elif memory.memory_status != MemoryStatus.ACTIVE.value:
            return False
        if session_id and (memory.session_id or "") not in {session_id, ""}:
            return False
        if source_query_id is not None and memory.source_query_id != source_query_id:
            return False
        if source_task_id is not None and memory.source_task_id != source_task_id:
            return False
        return source_episode_id is None or memory.source_episode_id == source_episode_id

    def _apply_conflict_policy(self, memory: Memory) -> None:
        """Supersede weaker same-scope memories that share a conflict key."""
        if memory.id is None or not memory.conflict_key:
            return

        memory_id = memory.id
        conflicts = find_conflicting_active_memories(memory)
        if not conflicts:
            return

        challenger_score = (memory.importance * 0.55) + (memory.quality_score * 0.45)
        for existing in conflicts:
            if existing.id is None:
                continue
            incumbent_score = (existing.importance * 0.55) + (existing.quality_score * 0.45)
            if challenger_score >= incumbent_score:
                set_memory_status(
                    existing.id,
                    memory_status=MemoryStatus.SUPERSEDED.value,
                    supersedes_memory_id=memory_id,
                )
            else:
                set_memory_status(
                    memory_id,
                    memory_status=MemoryStatus.SUPERSEDED.value,
                    supersedes_memory_id=existing.id,
                )
                memory.memory_status = MemoryStatus.SUPERSEDED.value
                break

    async def _index_one(self, memory: Memory) -> bool:
        if memory.id is None:
            return False
        update_embedding_state(
            memory.id,
            vector_ref_id="",
            embedding_status="ready",
            attempts=0,
            last_error="",
        )
        memory.vector_ref_id = ""
        memory.embedding_status = "ready"
        memory.embedding_attempts = 0
        memory.embedding_last_error = ""
        mark_embedding_job_completed(memory.id, agent_id=self._agent_id)
        return True

    def _repair_single_job(self, job: EmbeddingJob) -> bool:
        """Process one embedding repair job. Returns True if the job was resolved."""
        memory = get_entry(job.memory_id)
        if (
            memory is None
            or not memory.is_active
            or normalize_agent_scope(memory.agent_id, fallback=self._agent_id) != self._agent_id
        ):
            cancel_embedding_job(job.memory_id, agent_id=self._agent_id)
            return False
        update_embedding_state(
            memory.id or job.memory_id,
            vector_ref_id="",
            embedding_status="ready",
            attempts=0,
            last_error="",
        )
        mark_embedding_job_completed(job.memory_id, agent_id=self._agent_id)
        return True

    async def repair_pending_embeddings(self, limit: int = 16) -> int:
        """Consume the persisted repair queue and backfill missing embeddings."""
        async with self._repair_lock:
            jobs = claim_embedding_jobs(self._agent_id, limit=max(1, min(limit, MEMORY_EMBEDDING_REPAIR_BATCH_SIZE)))
            if not jobs:
                return 0

            sem = asyncio.Semaphore(4)

            async def _repair_one(job: EmbeddingJob) -> bool:
                async with sem:
                    try:
                        return await asyncio.to_thread(self._repair_single_job, job)
                    except Exception:
                        log.exception("embedding_repair_failed", job_id=getattr(job, "id", None))
                        return False

            results = await asyncio.gather(*[_repair_one(job) for job in jobs])
            resolved = sum(1 for r in results if r)

            if resolved:
                record_memory_quality_counter(self._agent_id, "embedding", "repaired", delta=resolved)
                log.info("memory_embedding_repaired", count=resolved, agent_id=self._agent_id)
            try:
                from koda.services import metrics

                for status, count in get_embedding_job_stats(self._agent_id).items():
                    metrics.MEMORY_EMBEDDING_QUEUE.labels(agent_id=self._agent_id, status=status).set(count)
            except Exception:
                log.debug("memory_embedding_queue_metrics_error", exc_info=True)
            return resolved

    async def add(self, memory: Memory) -> Memory:
        """Add a memory to the canonical store."""
        memory = self._hydrate_memory(memory)
        if find_active_duplicate(memory):
            log.info("memory_duplicate_skipped", reason="canonical_hash", content=memory.content[:80])
            record_dedup_decision(self._agent_id, "canonical_hash")
            return memory

        await self._require_memory_engine("deduplicate")
        dedupe_result = await self._memory_engine.deduplicate(rows=self._dedupe_rows([memory]))
        if self._has_duplicate_group_for_memory(dedupe_result, memory):
            log.info("memory_duplicate_skipped", reason="rust_deduplicate", content=memory.content[:80])
            record_dedup_decision(self._agent_id, "rust_deduplicate")
            return memory

        self._enforce_user_limit(memory.user_id, 1)
        self._persist_canonical(memory)
        self._apply_conflict_policy(memory)
        await self._index_one(memory)
        return memory

    async def add_batch(self, memories: list[Memory]) -> list[Memory]:
        """Add multiple memories while keeping the canonical store as the source of truth."""
        if not memories:
            return []

        normalized = [self._hydrate_memory(memory) for memory in memories]
        user_id = normalized[0].user_id

        unique: list[Memory] = []
        seen_scope_hashes: set[tuple[object, ...]] = set()
        for memory in normalized:
            scope_hash = (
                memory.user_id,
                memory.content_hash,
                memory.memory_type.value,
                memory.agent_id,
                memory.project_key,
                memory.environment,
                memory.team,
                memory.origin_kind,
            )
            if scope_hash in seen_scope_hashes:
                continue
            if find_active_duplicate(memory):
                log.info("memory_duplicate_skipped", reason="canonical_hash", content=memory.content[:80])
                record_dedup_decision(self._agent_id, "canonical_hash")
                continue
            seen_scope_hashes.add(scope_hash)
            unique.append(memory)

        if not unique:
            return memories

        await self._require_memory_engine("deduplicate")
        dedupe_result = await self._memory_engine.deduplicate(rows=self._dedupe_rows(unique))
        to_persist: list[Memory] = []
        for memory in unique:
            if self._has_duplicate_group_for_memory(dedupe_result, memory):
                log.info("memory_duplicate_skipped", reason="rust_deduplicate", content=memory.content[:80])
                record_dedup_decision(self._agent_id, "rust_deduplicate")
                continue
            to_persist.append(memory)
        if not to_persist:
            return memories

        self._enforce_user_limit(user_id, len(to_persist))

        for memory in to_persist:
            self._persist_canonical(memory)
            self._apply_conflict_policy(memory)

        for memory in to_persist:
            if memory.id is None:
                continue
            await self._index_one(memory)

        stored = [memory for memory in memories if memory.id is not None]
        if stored:
            log.info("memory_batch_stored", count=len(stored), user_id=user_id, agent_id=self._agent_id)
        return memories

    def _enforce_user_limit(self, user_id: int, incoming: int) -> None:
        """Deactivate oldest low-importance memories if user is at capacity."""
        from koda.memory.napkin import count_active, get_lowest_importance_entries

        count = count_active(user_id, agent_id=self._agent_id)
        overflow = (count + incoming) - MEMORY_MAX_PER_USER
        if overflow <= 0:
            return

        rows = get_lowest_importance_entries(user_id, overflow, agent_id=self._agent_id)
        if rows:
            entry_ids = [r[0] for r in rows]
            vector_ref_ids = [r[1] for r in rows if r[1]]
            self.batch_deactivate(entry_ids, vector_ref_ids)
            log.info("memory_limit_enforced", user_id=user_id, deactivated=len(entry_ids))

    async def search(
        self,
        query: str,
        user_id: int,
        n_results: int = 10,
        memory_types: list[MemoryType] | None = None,
        *,
        project_key: str = "",
        environment: str = "",
        team: str = "",
        origin_kinds: list[str] | None = None,
        session_id: str | None = None,
        source_query_id: int | None = None,
        source_task_id: int | None = None,
        source_episode_id: int | None = None,
        memory_statuses: list[str] | None = None,
        allowed_layers: list[str] | None = None,
        allowed_retrieval_sources: list[str] | None = None,
    ) -> list[RecallResult]:
        """Search memories via the Rust memory engine."""
        await self._require_memory_engine("recall")
        search_budget = max(1, n_results)
        recalled = await self._memory_engine.recall(
            query=query,
            limit=search_budget,
            user_id=user_id,
            memory_types=[item.value for item in list(memory_types or [])],
            project_key=project_key,
            environment=environment,
            team=team,
            origin_kinds=list(origin_kinds or []),
            session_id=session_id,
            source_query_id=source_query_id,
            source_task_id=source_task_id,
            source_episode_id=source_episode_id,
            memory_statuses=list(memory_statuses or []),
            allowed_layers=list(allowed_layers or []),
            allowed_retrieval_sources=list(allowed_retrieval_sources or []),
        )
        results: list[RecallResult] = []
        for item in recalled:
            row = item.get("memory")
            if not isinstance(row, Mapping):
                continue
            memory = Memory(
                user_id=int(row.get("user_id") or 0),
                memory_type=_memory_type_from_value(row.get("memory_type")),
                content=str(row.get("content") or ""),
                importance=_coerce_score(row.get("importance")),
                source_query_id=int(row.get("source_query_id") or 0) or None,
                session_id=str(row.get("session_id") or "") or None,
                agent_id=str(row.get("agent_id") or self._agent_id),
                origin_kind=str(row.get("origin_kind") or ""),
                source_task_id=int(row.get("source_task_id") or 0) or None,
                source_episode_id=int(row.get("source_episode_id") or 0) or None,
                project_key=str(row.get("project_key") or ""),
                environment=str(row.get("environment") or ""),
                team=str(row.get("team") or ""),
                quality_score=_coerce_score(row.get("quality_score")),
                extraction_confidence=_coerce_score(row.get("extraction_confidence")),
                embedding_status=str(row.get("embedding_status") or ""),
                content_hash=str(row.get("content_hash") or ""),
                claim_kind=str(row.get("claim_kind") or ""),
                subject=str(row.get("subject") or ""),
                decision_source=str(row.get("decision_source") or ""),
                evidence_refs=[str(value) for value in list(row.get("evidence_refs") or []) if str(value)],
                applicability_scope=dict(row.get("applicability_scope") or {})
                if isinstance(row.get("applicability_scope"), Mapping)
                else {},
                valid_until=_parse_datetime(row.get("valid_until")),
                conflict_key=str(row.get("conflict_key") or ""),
                supersedes_memory_id=int(row.get("supersedes_memory_id") or 0) or None,
                memory_status=str(row.get("memory_status") or MemoryStatus.ACTIVE.value),
                retention_reason=str(row.get("retention_reason") or ""),
                embedding_attempts=int(row.get("embedding_attempts") or 0),
                embedding_last_error=str(row.get("embedding_last_error") or ""),
                embedding_retry_at=_parse_datetime(row.get("embedding_retry_at")),
                access_count=int(row.get("access_count") or 0),
                last_accessed=_parse_datetime(row.get("last_accessed")),
                last_recalled_at=_parse_datetime(row.get("last_recalled_at")),
                created_at=_parse_datetime(row.get("created_at")) or datetime.now(),
                expires_at=_parse_datetime(row.get("expires_at")),
                is_active=bool(row.get("is_active", False)),
                metadata=dict(row.get("metadata") or {}) if isinstance(row.get("metadata"), Mapping) else {},
                vector_ref_id=str(row.get("vector_ref_id") or "") or None,
                id=int(row.get("id") or 0) or None,
            )
            results.append(
                RecallResult(
                    memory=memory,
                    relevance_score=max(0.0, 1.0 - _coerce_score(item.get("score"))),
                    retrieval_source=str(item.get("retrieval_source") or "rust"),
                    layer=str(item.get("layer") or MemoryLayer.CONVERSATIONAL.value),
                    selection_reasons=["rust_grpc_recall"],
                )
            )
        return results[:n_results]

    async def _ensure_memory_engine_started(self) -> bool:
        if self._memory_engine_started:
            return True
        async with self._memory_engine_lock:
            if self._memory_engine_started:
                return True
            try:
                await self._memory_engine.start()
            except Exception:
                log.exception("memory_engine_start_error", agent_id=self._agent_id)
                return False
            self._memory_engine_started = True
            return True

    def _memory_engine_supports(self, *capabilities: str) -> bool:
        health = dict(self._memory_engine.health() or {})
        if not bool(health.get("ready", False)):
            return False
        if not bool(health.get("cutover_allowed", False)):
            return False
        details = health.get("details")
        if not isinstance(details, Mapping):
            return False
        raw_capabilities = details.get("capabilities")
        if not isinstance(raw_capabilities, str) or not raw_capabilities.strip():
            return False
        advertised = {item.strip() for item in raw_capabilities.split(",") if item.strip()}
        return all(capability in advertised for capability in capabilities)

    async def _require_memory_engine(self, *capabilities: str) -> None:
        if not await self._ensure_memory_engine_started():
            raise RuntimeError("memory_engine_unavailable")
        if not self._memory_engine_supports(*capabilities):
            raise RuntimeError("memory_engine_unavailable")

    def _dedupe_rows(self, memories: list[Memory]) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for memory in memories:
            rows.append(
                {
                    "id": memory.id or 0,
                    "content_hash": memory.content_hash,
                    "conflict_key": memory.conflict_key,
                    "quality_score": memory.quality_score,
                    "importance": memory.importance,
                    "created_at": str(memory.created_at),
                    "agent_id": memory.agent_id,
                    "memory_type": memory.memory_type.value,
                    "subject": memory.subject,
                    "content": memory.content,
                    "session_id": memory.session_id,
                }
            )
        return rows

    def _has_duplicate_group_for_memory(self, dedupe_result: dict[str, object], memory: Memory) -> bool:
        groups = dedupe_result.get("duplicate_groups")
        if not isinstance(groups, list):
            return False
        for group in groups:
            if not isinstance(group, dict):
                continue
            if str(group.get("content_hash") or "") != memory.content_hash:
                continue
            memory_ids = group.get("memory_ids")
            if isinstance(memory_ids, list) and len(memory_ids) > 1:
                return True
        return False

    async def deactivate(self, memory_id: int, user_id: int | None = None) -> bool:
        """Deactivate a memory in the canonical store."""
        entry = get_entry(memory_id)
        if not entry:
            return False
        if (entry.agent_id or self._agent_id) != self._agent_id:
            return False
        if user_id is not None and entry.user_id != user_id:
            return False

        deactivated = deactivate_entry(memory_id)
        cancel_embedding_job(memory_id, agent_id=self._agent_id)
        return deactivated

    async def deactivate_all_for_user(self, user_id: int) -> int:
        """Deactivate all memories for a user."""
        count = deactivate_all(user_id, agent_id=self._agent_id)
        cancel_embedding_jobs_for_user(user_id, agent_id=self._agent_id)
        return count

    def update_access(self, memory_id: int) -> None:
        update_access(memory_id)

    def batch_update_access(self, memory_ids: list[int]) -> None:
        napkin_batch_update_access(memory_ids)

    def batch_deactivate(self, entry_ids: list[int], vector_ref_ids: list[str]) -> int:
        """Deactivate multiple memories in the canonical store."""
        count = napkin_batch_deactivate(entry_ids)
        for entry_id in entry_ids:
            cancel_embedding_job(entry_id, agent_id=self._agent_id)
        return count

    def get_stats(self, user_id: int) -> dict:
        return get_stats(user_id, agent_id=self._agent_id)
