"""Memory maintenance over the canonical primary backend."""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta
from functools import partial
from typing import Any

from koda.logging_config import get_logger
from koda.memory.napkin import (
    batch_update_importance,
    get_expired_active,
    get_stale_memories,
    log_maintenance,
)
from koda.memory.store import MemoryStore
from koda.memory.types import DEFAULT_TTL_DAYS, MemoryType
from koda.state.agent_scope import normalize_agent_scope
from koda.state_primary import (
    primary_execute,
    primary_fetch_all,
    require_primary_state_backend,
    run_coro_sync,
)

log = get_logger(__name__)

_LN2 = 0.6931471805599453


def _require_primary(agent_id: str) -> str:
    scope = normalize_agent_scope(agent_id, fallback="default")
    require_primary_state_backend(agent_id=scope, error="memory maintenance requires the primary state backend")
    return scope


def _fetch_rows(query: str, params: tuple[Any, ...], *, agent_id: str) -> list[dict[str, Any]] | list[tuple[Any, ...]]:
    scope = _require_primary(agent_id)
    return run_coro_sync(primary_fetch_all(query, params, agent_id=scope)) or []


def _execute_many(query: str, values: list[tuple[Any, ...]], *, agent_id: str) -> int:
    if not values:
        return 0
    scope = _require_primary(agent_id)
    count = 0
    for params in values:
        count += int(run_coro_sync(primary_execute(query, params, agent_id=scope)) or 0)
    return count


def _store_agent_scope(store: MemoryStore) -> str:
    agent_id = getattr(store, "agent_id", "default")
    return normalize_agent_scope(agent_id if isinstance(agent_id, str) else None, fallback="default")


def cleanup_expired(store: MemoryStore) -> int:
    now_iso = datetime.now().isoformat()
    agent_id = _store_agent_scope(store)
    expired = get_expired_active(now_iso, agent_id=agent_id)
    if not expired:
        return 0
    entry_ids = [row[0] for row in expired]
    vector_ref_ids = [row[1] for row in expired if row[1]]
    count = store.batch_deactivate(entry_ids, vector_ref_ids)
    log_maintenance("cleanup_expired", count, f"Deactivated {count} expired memories")
    log.info("maintenance_cleanup_expired", count=count)
    return count


def decay_importance(store: MemoryStore, half_life_days: float = 180.0, min_importance: float = 0.05) -> int:
    stale = get_stale_memories(min_age_days=60, min_importance=min_importance, agent_id=_store_agent_scope(store))
    if not stale:
        return 0
    now = datetime.now()
    updates: list[tuple[float, int]] = []
    for memory in stale:
        ref_date = memory.last_accessed or memory.created_at
        days_since = (now - ref_date).total_seconds() / 86400
        new_imp = max(memory.importance * math.exp(-_LN2 * days_since / half_life_days), min_importance)
        if memory.id is not None and abs(new_imp - memory.importance) > 0.001:
            updates.append((new_imp, memory.id))
    if updates:
        batch_update_importance(updates)
    log_maintenance("decay_importance", len(updates), f"Decayed importance of {len(updates)} stale memories")
    log.info("maintenance_decay_importance", updated=len(updates), total_stale=len(stale))
    return len(updates)


def extend_existing_ttls(store: MemoryStore) -> int:
    updated = 0
    agent_id = _store_agent_scope(store)
    try:
        rows = _fetch_rows(
            """
            SELECT id, memory_type, created_at, expires_at
            FROM napkin_log
            WHERE is_active = 1 AND expires_at IS NOT NULL AND agent_id = ?
            """,
            (agent_id,),
            agent_id=agent_id,
        )
        updates: list[tuple[str, int]] = []
        for row in rows:
            if isinstance(row, dict):
                entry_id = int(row.get("id") or 0)
                type_str = str(row.get("memory_type") or "")
                created_at_str = str(row.get("created_at") or "")
                expires_at_str = str(row.get("expires_at") or "")
            else:
                entry_id, type_str, created_at_str, expires_at_str = row
                entry_id = int(entry_id or 0)
                type_str = str(type_str or "")
                created_at_str = str(created_at_str or "")
                expires_at_str = str(expires_at_str or "")
            try:
                memory_type = MemoryType(type_str)
            except ValueError:
                continue
            new_ttl_days = DEFAULT_TTL_DAYS.get(memory_type)
            if new_ttl_days is None:
                continue
            created_at = datetime.fromisoformat(created_at_str)
            current_expires = datetime.fromisoformat(expires_at_str)
            new_expires = created_at + timedelta(days=new_ttl_days)
            if new_expires > current_expires:
                updates.append((new_expires.isoformat(), entry_id))
        updated = _execute_many("UPDATE napkin_log SET expires_at = ? WHERE id = ?", updates, agent_id=agent_id)
    except Exception:
        log.exception("extend_existing_ttls_failed")
    if updated:
        log_maintenance("extend_ttls", updated, f"Extended TTLs for {updated} memories")
        log.info("maintenance_extend_ttls", updated=updated)
    return updated


def cleanup_orphans(store: MemoryStore) -> int:
    cleaned = 0
    agent_id = _store_agent_scope(store)
    collection = getattr(store, "_collection", None)
    if collection is None:
        return 0
    try:
        rows = _fetch_rows(
            """
            SELECT id, vector_ref_id
            FROM napkin_log
            WHERE is_active = 1 AND agent_id = ? AND vector_ref_id IS NOT NULL
            """,
            (agent_id,),
            agent_id=agent_id,
        )
        napkin_vector_ref_ids: set[str] = set()
        for row in rows:
            if isinstance(row, dict):
                vector_ref_id = str(row.get("vector_ref_id") or "")
            else:
                vector_ref_id = str(row[1] or "")
            if vector_ref_id:
                napkin_vector_ref_ids.add(vector_ref_id)
        index_data = collection.get(include=[])
        index_ids = set(index_data["ids"]) if index_data["ids"] else set()
        orphan_index_ids = list(index_ids - napkin_vector_ref_ids)
        if orphan_index_ids:
            collection.delete(ids=orphan_index_ids)
            cleaned += len(orphan_index_ids)
            log.info("orphan_vector_index_cleaned", count=len(orphan_index_ids))
        orphan_vector_refs = napkin_vector_ref_ids - index_ids
        if orphan_vector_refs:
            log.info(
                "orphan_napkin_sidecar_skipped",
                count=len(orphan_vector_refs),
                reason="local_vector_helper_rebuildable",
            )
        if cleaned:
            log_maintenance("cleanup_orphans", cleaned, f"Cleaned {cleaned} orphan entries")
    except Exception:
        log.exception("cleanup_orphans_failed")
    return cleaned


async def run_maintenance(store: MemoryStore) -> dict:
    loop = asyncio.get_running_loop()
    repaired = await store.repair_pending_embeddings(limit=64)
    expired = await loop.run_in_executor(None, partial(cleanup_expired, store))
    decayed, extended = await asyncio.gather(
        loop.run_in_executor(None, partial(decay_importance, store)),
        loop.run_in_executor(None, partial(extend_existing_ttls, store)),
    )
    orphans = await loop.run_in_executor(None, partial(cleanup_orphans, store))
    summary = {
        "expired_cleaned": expired,
        "importance_decayed": decayed,
        "ttls_extended": extended,
        "orphans_cleaned": orphans,
        "embeddings_repaired": repaired,
    }
    log.info("maintenance_complete", **summary)
    return summary
