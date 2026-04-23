"""Canonical napkin_log CRUD with Postgres-primary support."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any, cast

from koda.config import AGENT_ID
from koda.memory.quality import record_status_transition
from koda.memory.types import (
    DEFAULT_EMBEDDING_STATUS,
    DEFAULT_MEMORY_STATUS,
    DEFAULT_ORIGIN_KIND,
    Memory,
    MemoryStatus,
    MemoryType,
)
from koda.state.agent_scope import normalize_agent_scope
from koda.state.primary import (
    primary_execute,
    primary_fetch_all,
    primary_fetch_one,
    primary_fetch_val,
    require_primary_state_backend,
    run_coro_sync,
)


def _current_agent_scope(agent_id: str | None = None) -> str:
    return normalize_agent_scope(agent_id, fallback=AGENT_ID)


def _primary_enabled() -> bool:
    require_primary_state_backend(agent_id=AGENT_ID, error="memory napkin requires the primary state backend")
    return True


def _fetch_rows(query: str, params: Sequence[object]) -> list[Any]:
    _primary_enabled()
    return cast(list[Any], run_coro_sync(primary_fetch_all(query, tuple(params))))


def _fetch_row(query: str, params: Sequence[object]) -> Any | None:
    _primary_enabled()
    return run_coro_sync(primary_fetch_one(query, tuple(params)))


def _fetch_value(query: str, params: Sequence[object]) -> Any:
    _primary_enabled()
    return run_coro_sync(primary_fetch_val(query, tuple(params)))


def _insert(query: str, params: Sequence[object]) -> int:
    _primary_enabled()
    inserted = run_coro_sync(primary_fetch_val(f"{query.rstrip(';')} RETURNING id", tuple(params)))
    return int(inserted or 0)


def _write(query: str, params: Sequence[object]) -> int:
    _primary_enabled()
    return int(run_coro_sync(primary_execute(query, tuple(params))) or 0)


_SELECT_COLS = (
    "id, user_id, memory_type, content, source_query_id, session_id, agent_id, origin_kind, "
    "source_task_id, source_episode_id, project_key, environment, team, importance, quality_score, "
    "extraction_confidence, embedding_status, content_hash, claim_kind, subject, decision_source, "
    "evidence_refs_json, applicability_scope_json, valid_until, conflict_key, supersedes_memory_id, "
    "memory_status, retention_reason, embedding_attempts, embedding_last_error, embedding_retry_at, "
    "access_count, last_accessed, last_recalled_at, created_at, expires_at, is_active, metadata_json, vector_ref_id"
)


def _row_to_memory(row: tuple | dict[str, Any]) -> Memory:
    """Convert a database row to a Memory object."""
    if isinstance(row, dict):
        return Memory(
            id=cast(int | None, row.get("id")),
            user_id=int(cast(int | str, row.get("user_id") or 0)),
            memory_type=MemoryType(str(row.get("memory_type") or MemoryType.FACT.value)),
            content=str(row.get("content") or ""),
            source_query_id=cast(int | None, row.get("source_query_id")),
            session_id=cast(str | None, row.get("session_id")),
            agent_id=cast(str | None, row.get("agent_id")),
            origin_kind=str(row.get("origin_kind") or DEFAULT_ORIGIN_KIND),
            source_task_id=cast(int | None, row.get("source_task_id")),
            source_episode_id=cast(int | None, row.get("source_episode_id")),
            project_key=str(row.get("project_key") or ""),
            environment=str(row.get("environment") or ""),
            team=str(row.get("team") or ""),
            importance=float(row.get("importance") or 0.5),
            quality_score=float(row.get("quality_score") or 0.5),
            extraction_confidence=float(row.get("extraction_confidence") or 0.5),
            embedding_status=str(row.get("embedding_status") or DEFAULT_EMBEDDING_STATUS),
            content_hash=str(row.get("content_hash") or ""),
            claim_kind=str(row.get("claim_kind") or ""),
            subject=str(row.get("subject") or ""),
            decision_source=str(row.get("decision_source") or ""),
            evidence_refs=json.loads(str(row.get("evidence_refs_json") or "[]")),
            applicability_scope=json.loads(str(row.get("applicability_scope_json") or "{}")),
            valid_until=datetime.fromisoformat(str(row["valid_until"])) if row.get("valid_until") else None,
            conflict_key=str(row.get("conflict_key") or ""),
            supersedes_memory_id=cast(int | None, row.get("supersedes_memory_id")),
            memory_status=str(row.get("memory_status") or DEFAULT_MEMORY_STATUS),
            retention_reason=str(row.get("retention_reason") or ""),
            embedding_attempts=int(cast(int | str, row.get("embedding_attempts") or 0)),
            embedding_last_error=str(row.get("embedding_last_error") or ""),
            embedding_retry_at=datetime.fromisoformat(str(row["embedding_retry_at"]))
            if row.get("embedding_retry_at")
            else None,
            access_count=int(cast(int | str, row.get("access_count") or 0)),
            last_accessed=datetime.fromisoformat(str(row["last_accessed"])) if row.get("last_accessed") else None,
            last_recalled_at=datetime.fromisoformat(str(row["last_recalled_at"]))
            if row.get("last_recalled_at")
            else None,
            created_at=datetime.fromisoformat(str(row.get("created_at"))),
            expires_at=datetime.fromisoformat(str(row["expires_at"])) if row.get("expires_at") else None,
            is_active=bool(row.get("is_active")),
            metadata=json.loads(str(row.get("metadata_json") or "{}")),
            vector_ref_id=cast(str | None, row.get("vector_ref_id")),
        )
    return Memory(
        id=row[0],
        user_id=row[1],
        memory_type=MemoryType(row[2]),
        content=row[3],
        source_query_id=row[4],
        session_id=row[5],
        agent_id=row[6],
        origin_kind=row[7] or DEFAULT_ORIGIN_KIND,
        source_task_id=row[8],
        source_episode_id=row[9],
        project_key=row[10] or "",
        environment=row[11] or "",
        team=row[12] or "",
        importance=row[13],
        quality_score=row[14] if row[14] is not None else 0.5,
        extraction_confidence=row[15] if row[15] is not None else 0.5,
        embedding_status=row[16] or DEFAULT_EMBEDDING_STATUS,
        content_hash=row[17] or "",
        claim_kind=row[18] or "",
        subject=row[19] or "",
        decision_source=row[20] or "",
        evidence_refs=json.loads(row[21]) if row[21] else [],
        applicability_scope=json.loads(row[22]) if row[22] else {},
        valid_until=datetime.fromisoformat(row[23]) if row[23] else None,
        conflict_key=row[24] or "",
        supersedes_memory_id=row[25],
        memory_status=row[26] or DEFAULT_MEMORY_STATUS,
        retention_reason=row[27] or "",
        embedding_attempts=row[28] or 0,
        embedding_last_error=row[29] or "",
        embedding_retry_at=datetime.fromisoformat(row[30]) if row[30] else None,
        access_count=row[31],
        last_accessed=datetime.fromisoformat(row[32]) if row[32] else None,
        last_recalled_at=datetime.fromisoformat(row[33]) if row[33] else None,
        created_at=datetime.fromisoformat(row[34]),
        expires_at=datetime.fromisoformat(row[35]) if row[35] else None,
        is_active=bool(row[36]),
        metadata=json.loads(row[37]) if row[37] else {},
        vector_ref_id=row[38],
    )


def add_entry(memory: Memory) -> int:
    """Insert a memory into the napkin_log. Returns the row ID."""
    memory.agent_id = _current_agent_scope(memory.agent_id)
    return _insert(
        """INSERT INTO napkin_log
           (user_id, memory_type, content, source_query_id, session_id, agent_id, origin_kind,
            source_task_id, source_episode_id, project_key, environment, team, importance,
            quality_score, extraction_confidence, embedding_status, content_hash, claim_kind, subject,
            decision_source, evidence_refs_json, applicability_scope_json, valid_until, conflict_key,
            supersedes_memory_id, memory_status, retention_reason, embedding_attempts,
            embedding_last_error, embedding_retry_at, access_count, last_accessed, last_recalled_at,
            created_at, expires_at, is_active, metadata_json, vector_ref_id)
           VALUES (
               ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
               ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
           )""",
        (
            memory.user_id,
            memory.memory_type.value,
            memory.content,
            memory.source_query_id,
            memory.session_id,
            memory.agent_id,
            memory.origin_kind,
            memory.source_task_id,
            memory.source_episode_id,
            memory.project_key,
            memory.environment,
            memory.team,
            memory.importance,
            memory.quality_score,
            memory.extraction_confidence,
            memory.embedding_status,
            memory.content_hash,
            memory.claim_kind,
            memory.subject,
            memory.decision_source,
            json.dumps(memory.evidence_refs, default=str),
            json.dumps(memory.applicability_scope, default=str),
            memory.valid_until.isoformat() if memory.valid_until else None,
            memory.conflict_key,
            memory.supersedes_memory_id,
            memory.memory_status,
            memory.retention_reason,
            memory.embedding_attempts,
            memory.embedding_last_error,
            memory.embedding_retry_at.isoformat() if memory.embedding_retry_at else None,
            memory.access_count,
            memory.last_accessed.isoformat() if memory.last_accessed else None,
            memory.last_recalled_at.isoformat() if memory.last_recalled_at else None,
            memory.created_at.isoformat(),
            memory.expires_at.isoformat() if memory.expires_at else None,
            1 if memory.is_active else 0,
            json.dumps(memory.metadata, default=str),
            memory.vector_ref_id,
        ),
    )


def get_entries(
    user_id: int,
    limit: int = 20,
    memory_type: MemoryType | None = None,
    active_only: bool = True,
    *,
    agent_id: str | None = None,
    origin_kind: str | None = None,
    project_key: str | None = None,
    environment: str | None = None,
    team: str | None = None,
    memory_status: str | None = None,
) -> list[Memory]:
    """Get napkin_log entries for a user."""
    scope = _current_agent_scope(agent_id)
    query = f"SELECT {_SELECT_COLS} FROM napkin_log WHERE user_id = ?"
    params: list[object] = [user_id]

    if active_only:
        query += " AND is_active = 1"
    query += " AND agent_id = ?"
    params.append(scope)
    if memory_type:
        query += " AND memory_type = ?"
        params.append(memory_type.value)
    if origin_kind:
        query += " AND origin_kind = ?"
        params.append(origin_kind)
    if project_key:
        query += " AND project_key = ?"
        params.append(project_key)
    if environment:
        query += " AND environment = ?"
        params.append(environment)
    if team:
        query += " AND team = ?"
        params.append(team)
    if memory_status:
        query += " AND COALESCE(memory_status, ?) = ?"
        params.extend([DEFAULT_MEMORY_STATUS, memory_status])

    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    rows = _fetch_rows(query, params)
    return [_row_to_memory(r) for r in rows]


def get_entry(entry_id: int) -> Memory | None:
    """Get a single entry by ID."""
    row = _fetch_row(
        f"SELECT {_SELECT_COLS} FROM napkin_log WHERE id = ?",
        (entry_id,),
    )
    return _row_to_memory(row) if row else None


def find_active_duplicate(memory: Memory) -> Memory | None:
    """Find an active duplicate in the canonical memory scope using hash + scope."""
    scope = _current_agent_scope(memory.agent_id)
    row = _fetch_row(
        f"""SELECT {_SELECT_COLS} FROM napkin_log
            WHERE user_id = ?
              AND is_active = 1
              AND content_hash = ?
              AND memory_type = ?
              AND agent_id = ?
              AND COALESCE(project_key, '') = COALESCE(?, '')
              AND COALESCE(environment, '') = COALESCE(?, '')
              AND COALESCE(team, '') = COALESCE(?, '')
              AND COALESCE(origin_kind, '') = COALESCE(?, '')
              AND COALESCE(memory_status, ?) = ?
            ORDER BY id DESC LIMIT 1""",
        (
            memory.user_id,
            memory.content_hash,
            memory.memory_type.value,
            scope,
            memory.project_key,
            memory.environment,
            memory.team,
            memory.origin_kind,
            DEFAULT_MEMORY_STATUS,
            MemoryStatus.ACTIVE.value,
        ),
    )
    return _row_to_memory(row) if row else None


def update_access(entry_id: int) -> None:
    """Increment access_count and update access metadata."""
    now_iso = datetime.now().isoformat()
    _write(
        "UPDATE napkin_log SET access_count = access_count + 1, last_accessed = ?, last_recalled_at = ? WHERE id = ?",
        (now_iso, now_iso, entry_id),
    )


def deactivate_entry(entry_id: int) -> bool:
    """Deactivate a memory entry. Returns True if updated."""
    return (
        _write(
            "UPDATE napkin_log SET is_active = 0 WHERE id = ? AND is_active = 1",
            (entry_id,),
        )
        > 0
    )


def deactivate_all(user_id: int, *, agent_id: str | None = None) -> int:
    """Deactivate all memories for a user. Returns count affected."""
    scope = _current_agent_scope(agent_id)
    return _write(
        "UPDATE napkin_log SET is_active = 0 WHERE user_id = ? AND is_active = 1 AND agent_id = ?",
        (user_id, scope),
    )


def get_stats(user_id: int, *, agent_id: str | None = None) -> dict:
    """Get memory stats for a user: total, active, and counts by type/origin."""
    scope = _current_agent_scope(agent_id)
    total = int(
        _fetch_value(
            "SELECT COUNT(*) FROM napkin_log WHERE user_id = ? AND agent_id = ?",
            (user_id, scope),
        )
        or 0
    )
    active = int(
        _fetch_value(
            "SELECT COUNT(*) FROM napkin_log WHERE user_id = ? AND is_active = 1 AND agent_id = ?",
            (user_id, scope),
        )
        or 0
    )
    by_type = _fetch_rows(
        "SELECT memory_type, COUNT(*) AS total FROM napkin_log "
        "WHERE user_id = ? AND is_active = 1 AND agent_id = ? GROUP BY memory_type",
        (user_id, scope),
    )
    by_origin = _fetch_rows(
        "SELECT COALESCE(origin_kind, ?) AS origin_kind, COUNT(*) AS total FROM napkin_log "
        "WHERE user_id = ? AND is_active = 1 AND agent_id = ? "
        "GROUP BY COALESCE(origin_kind, ?)",
        (DEFAULT_ORIGIN_KIND, user_id, scope, DEFAULT_ORIGIN_KIND),
    )
    by_status = _fetch_rows(
        "SELECT COALESCE(embedding_status, ?) AS embedding_status, COUNT(*) AS total FROM napkin_log "
        "WHERE user_id = ? AND is_active = 1 AND agent_id = ? "
        "GROUP BY COALESCE(embedding_status, ?)",
        (DEFAULT_EMBEDDING_STATUS, user_id, scope, DEFAULT_EMBEDDING_STATUS),
    )
    by_memory_status = _fetch_rows(
        "SELECT COALESCE(memory_status, ?) AS memory_status, COUNT(*) AS total FROM napkin_log "
        "WHERE user_id = ? AND is_active = 1 AND agent_id = ? "
        "GROUP BY COALESCE(memory_status, ?)",
        (DEFAULT_MEMORY_STATUS, user_id, scope, DEFAULT_MEMORY_STATUS),
    )

    def _pair(row: Any, key: str) -> tuple[str, int]:
        if isinstance(row, dict):
            return str(row.get(key) or ""), int(cast(int | str, row.get("total") or 0))
        return str(row[0] or ""), int(cast(int | str, row[1] or 0))

    return {
        "total": total,
        "active": active,
        "by_type": {k: v for k, v in (_pair(row, "memory_type") for row in by_type)},
        "by_origin": {k: v for k, v in (_pair(row, "origin_kind") for row in by_origin)},
        "embedding_status": {k: v for k, v in (_pair(row, "embedding_status") for row in by_status)},
        "memory_status": {k: v for k, v in (_pair(row, "memory_status") for row in by_memory_status)},
    }


def get_expired_active(now_iso: str, *, agent_id: str | None = None) -> list[tuple[int, str]]:
    """Return (id, vector_ref_id) of active memories with expires_at < now."""
    scope = _current_agent_scope(agent_id)
    rows = _fetch_rows(
        "SELECT id, vector_ref_id FROM napkin_log WHERE is_active = 1 "
        "AND agent_id = ? AND expires_at IS NOT NULL AND expires_at < ?",
        (scope, now_iso),
    )
    return [
        (
            int(cast(int | str, row["id"] if isinstance(row, dict) else row[0])),
            str((row["vector_ref_id"] if isinstance(row, dict) else row[1]) or ""),
        )
        for row in rows
    ]


def batch_deactivate(entry_ids: list[int]) -> int:
    """Deactivate multiple memories at once. Returns count."""
    if not entry_ids:
        return 0
    placeholders = ",".join("?" for _ in entry_ids)
    return _write(
        f"UPDATE napkin_log SET is_active = 0 WHERE id IN ({placeholders}) AND is_active = 1",
        entry_ids,
    )


def get_stale_memories(
    min_age_days: int = 30,
    min_importance: float = 0.1,
    *,
    agent_id: str | None = None,
) -> list[Memory]:
    """Active memories not accessed in min_age_days with importance > min_importance."""
    cutoff = (datetime.now() - timedelta(days=min_age_days)).isoformat()
    scope = _current_agent_scope(agent_id)
    rows = _fetch_rows(
        f"SELECT {_SELECT_COLS} FROM napkin_log "
        "WHERE is_active = 1 AND agent_id = ? AND importance > ? "
        "AND (last_accessed IS NULL OR last_accessed < ?) "
        "AND COALESCE(memory_status, ?) = ? "
        "AND created_at < ?",
        (scope, min_importance, cutoff, DEFAULT_MEMORY_STATUS, MemoryStatus.ACTIVE.value, cutoff),
    )
    return [_row_to_memory(r) for r in rows]


def update_importance(entry_id: int, new_importance: float) -> None:
    """Update importance of a memory."""
    _write(
        "UPDATE napkin_log SET importance = ? WHERE id = ?",
        (new_importance, entry_id),
    )


def update_embedding_state(
    entry_id: int,
    *,
    vector_ref_id: str | None = None,
    embedding_status: str | None = None,
    clear_vector_ref_id: bool = False,
    attempts: int | None = None,
    last_error: str | None = None,
    retry_at: datetime | None = None,
) -> None:
    """Update vector-sync state for a stored memory."""
    fields: list[str] = []
    params: list[object] = []
    if clear_vector_ref_id:
        fields.append("vector_ref_id = NULL")
    elif vector_ref_id is not None:
        fields.append("vector_ref_id = ?")
        params.append(vector_ref_id)
    if embedding_status is not None:
        fields.append("embedding_status = ?")
        params.append(embedding_status)
        if embedding_status == "ready":
            fields.append("embedding_retry_at = NULL")
    if attempts is not None:
        fields.append("embedding_attempts = ?")
        params.append(attempts)
    if last_error is not None:
        fields.append("embedding_last_error = ?")
        params.append(last_error)
    if retry_at is not None:
        fields.append("embedding_retry_at = ?")
        params.append(retry_at.isoformat())
    if not fields:
        return
    params.append(entry_id)
    _write(f"UPDATE napkin_log SET {', '.join(fields)} WHERE id = ?", params)


def get_pending_embeddings(agent_id: str | None, limit: int = 32) -> list[Memory]:
    """Fetch memories that still need vector indexing."""
    scope = _current_agent_scope(agent_id)
    query = (
        f"SELECT {_SELECT_COLS} FROM napkin_log WHERE is_active = 1 "
        "AND COALESCE(embedding_status, ?) IN ('pending', 'failed', 'stale')"
    )
    params: list[object] = [DEFAULT_EMBEDDING_STATUS]
    query += " AND (embedding_retry_at IS NULL OR embedding_retry_at <= ?)"
    params.append(datetime.now().isoformat())
    query += " AND agent_id = ?"
    params.append(scope)
    query += " ORDER BY created_at ASC LIMIT ?"
    params.append(limit)
    rows = _fetch_rows(query, params)
    return [_row_to_memory(r) for r in rows]


def search_entries_lexical(
    *,
    user_id: int,
    query: str,
    limit: int = 24,
    memory_types: list[MemoryType] | None = None,
    agent_id: str | None = None,
    project_key: str = "",
    environment: str = "",
    team: str = "",
    origin_kinds: list[str] | None = None,
    memory_statuses: list[str] | None = None,
    session_id: str | None = None,
    source_query_id: int | None = None,
    source_task_id: int | None = None,
    source_episode_id: int | None = None,
) -> list[Memory]:
    """Return candidate memories for lexical retrieval and scope-aware filtering."""
    scope = _current_agent_scope(agent_id)
    sql = [f"SELECT {_SELECT_COLS} FROM napkin_log WHERE user_id = ? AND is_active = 1"]
    params: list[object] = [user_id]

    if memory_types:
        placeholders = ",".join("?" for _ in memory_types)
        sql.append(f"AND memory_type IN ({placeholders})")
        params.extend(t.value for t in memory_types)
    sql.append("AND agent_id = ?")
    params.append(scope)
    if project_key:
        sql.append("AND COALESCE(project_key, '') IN (?, '')")
        params.append(project_key)
    if environment:
        sql.append("AND COALESCE(environment, '') IN (?, '')")
        params.append(environment)
    if team:
        sql.append("AND COALESCE(team, '') IN (?, '')")
        params.append(team)
    if origin_kinds:
        placeholders = ",".join("?" for _ in origin_kinds)
        sql.append(f"AND COALESCE(origin_kind, '{DEFAULT_ORIGIN_KIND}') IN ({placeholders})")
        params.extend(origin_kinds)
    if memory_statuses:
        placeholders = ",".join("?" for _ in memory_statuses)
        sql.append(f"AND COALESCE(memory_status, '{DEFAULT_MEMORY_STATUS}') IN ({placeholders})")
        params.extend(memory_statuses)
    else:
        sql.append("AND COALESCE(memory_status, ?) = ?")
        params.extend([DEFAULT_MEMORY_STATUS, MemoryStatus.ACTIVE.value])
    if session_id:
        sql.append("AND COALESCE(session_id, '') IN (?, '')")
        params.append(session_id)
    if source_query_id is not None:
        sql.append("AND source_query_id = ?")
        params.append(source_query_id)
    if source_task_id is not None:
        sql.append("AND source_task_id = ?")
        params.append(source_task_id)
    if source_episode_id is not None:
        sql.append("AND source_episode_id = ?")
        params.append(source_episode_id)

    query_terms = [term for term in query.lower().split() if len(term) > 2][:8]
    if query_terms:
        like_clauses = ["LOWER(content) LIKE ?" for _ in query_terms]
        sql.append(f"AND ({' OR '.join(like_clauses)})")
        params.extend(f"%{term}%" for term in query_terms)

    sql.append("ORDER BY importance DESC, quality_score DESC, created_at DESC LIMIT ?")
    params.append(limit)

    rows = _fetch_rows(" ".join(sql), params)
    return [_row_to_memory(r) for r in rows]


def get_exact_linked_memories(
    *,
    user_id: int,
    agent_id: str | None = None,
    project_key: str = "",
    environment: str = "",
    team: str = "",
    session_id: str | None = None,
    source_query_id: int | None = None,
    source_task_id: int | None = None,
    limit: int = 12,
) -> list[Memory]:
    """Return exact link matches for query/task/session-aware recall."""
    scope = _current_agent_scope(agent_id)
    sql = [
        f"SELECT {_SELECT_COLS} FROM napkin_log WHERE user_id = ? AND is_active = 1",
        "AND COALESCE(memory_status, ?) = ?",
    ]
    params: list[object] = [user_id, DEFAULT_MEMORY_STATUS, MemoryStatus.ACTIVE.value]
    sql.append("AND agent_id = ?")
    params.append(scope)
    if project_key:
        sql.append("AND COALESCE(project_key, '') IN (?, '')")
        params.append(project_key)
    if environment:
        sql.append("AND COALESCE(environment, '') IN (?, '')")
        params.append(environment)
    if team:
        sql.append("AND COALESCE(team, '') IN (?, '')")
        params.append(team)
    if source_query_id is not None:
        sql.append("AND source_query_id = ?")
        params.append(source_query_id)
    elif source_task_id is not None:
        sql.append("AND source_task_id = ?")
        params.append(source_task_id)
    elif session_id:
        sql.append("AND COALESCE(session_id, '') = ?")
        params.append(session_id)
    else:
        return []
    sql.append("ORDER BY quality_score DESC, importance DESC, created_at DESC LIMIT ?")
    params.append(limit)
    rows = _fetch_rows(" ".join(sql), params)
    return [_row_to_memory(r) for r in rows]


def get_last_maintenance() -> str | None:
    """Return executed_at of the last maintenance, or None."""
    row = _fetch_row("SELECT executed_at FROM memory_maintenance_log ORDER BY id DESC LIMIT 1", ())
    if row is None:
        return None
    return str(row["executed_at"] if isinstance(row, dict) else row[0])


def log_maintenance(operation: str, affected: int, details: str) -> None:
    """Insert a record into memory_maintenance_log."""
    _insert(
        "INSERT INTO memory_maintenance_log (operation, memories_affected, details, executed_at) VALUES (?, ?, ?, ?)",
        (operation, affected, details, datetime.now().isoformat()),
    )


def count_active(user_id: int, *, agent_id: str | None = None) -> int:
    """Count active memories for a user."""
    scope = _current_agent_scope(agent_id)
    return int(
        _fetch_value(
            "SELECT COUNT(*) FROM napkin_log WHERE user_id = ? AND is_active = 1 AND agent_id = ?",
            (user_id, scope),
        )
        or 0
    )


def get_lowest_importance_entries(
    user_id: int,
    limit: int,
    *,
    agent_id: str | None = None,
) -> list[tuple[int, str | None]]:
    """Return (id, vector_ref_id) of lowest-importance active memories, oldest first."""
    scope = _current_agent_scope(agent_id)
    rows = _fetch_rows(
        "SELECT id, vector_ref_id FROM napkin_log "
        "WHERE user_id = ? AND is_active = 1 AND agent_id = ? "
        "ORDER BY importance ASC, quality_score ASC, created_at ASC LIMIT ?",
        (user_id, scope, limit),
    )
    return [
        (
            int(cast(int | str, row["id"] if isinstance(row, dict) else row[0])),
            cast(str | None, row["vector_ref_id"] if isinstance(row, dict) else row[1]),
        )
        for row in rows
    ]


def batch_update_access(entry_ids: list[int]) -> None:
    """Increment access_count and update access metadata for multiple entries at once."""
    if not entry_ids:
        return
    now_iso = datetime.now().isoformat()
    placeholders = ",".join("?" for _ in entry_ids)
    _write(
        f"UPDATE napkin_log SET access_count = access_count + 1, last_accessed = ?, last_recalled_at = ? "
        f"WHERE id IN ({placeholders})",
        [now_iso, now_iso, *entry_ids],
    )


def batch_get_entries(entry_ids: list[int]) -> dict[int, Memory]:
    """Get multiple entries by ID in a single query. Returns {id: Memory}."""
    if not entry_ids:
        return {}
    placeholders = ",".join("?" for _ in entry_ids)
    rows = _fetch_rows(
        f"SELECT {_SELECT_COLS} FROM napkin_log WHERE id IN ({placeholders})",
        entry_ids,
    )
    result: dict[int, Memory] = {}
    for row in rows:
        memory = _row_to_memory(row)
        if memory.id is not None:
            result[memory.id] = memory
    return result


def batch_update_importance(updates: list[tuple[float, int]]) -> int:
    """Update importance for multiple entries. Takes list of (new_importance, entry_id)."""
    if not updates:
        return 0
    for update in updates:
        _write("UPDATE napkin_log SET importance = ? WHERE id = ?", update)
    return len(updates)


def get_recent_memories(
    user_id: int,
    since_iso: str,
    limit: int = 50,
    *,
    agent_id: str | None = None,
) -> list[Memory]:
    """Active memories created since since_iso."""
    scope = _current_agent_scope(agent_id)
    rows = _fetch_rows(
        f"SELECT {_SELECT_COLS} FROM napkin_log "
        "WHERE user_id = ? AND is_active = 1 AND agent_id = ? AND created_at >= ? "
        "AND COALESCE(memory_status, ?) = ? "
        "ORDER BY created_at DESC LIMIT ?",
        (user_id, scope, since_iso, DEFAULT_MEMORY_STATUS, MemoryStatus.ACTIVE.value, limit),
    )
    return [_row_to_memory(r) for r in rows]


def get_memories_by_types(
    user_id: int,
    types: list[str],
    limit: int = 20,
    *,
    agent_id: str | None = None,
) -> list[Memory]:
    """Active memories of specified types, ordered by importance DESC."""
    if not types:
        return []
    placeholders = ",".join("?" for _ in types)
    scope = _current_agent_scope(agent_id)
    rows = _fetch_rows(
        f"SELECT {_SELECT_COLS} FROM napkin_log "
        f"WHERE user_id = ? AND is_active = 1 AND agent_id = ? "
        f"AND memory_type IN ({placeholders}) "
        "AND COALESCE(memory_status, ?) = ? "
        "ORDER BY importance DESC, created_at DESC LIMIT ?",
        [user_id, scope, *types, DEFAULT_MEMORY_STATUS, MemoryStatus.ACTIVE.value, limit],
    )
    return [_row_to_memory(r) for r in rows]


def get_expiring_soon(user_id: int, within_days: int = 7, *, agent_id: str | None = None) -> list[Memory]:
    """Active memories expiring within the next within_days days."""
    now_iso = datetime.now().isoformat()
    deadline = (datetime.now() + timedelta(days=within_days)).isoformat()
    scope = _current_agent_scope(agent_id)
    rows = _fetch_rows(
        f"SELECT {_SELECT_COLS} FROM napkin_log "
        "WHERE user_id = ? AND is_active = 1 AND agent_id = ? AND expires_at IS NOT NULL "
        "AND COALESCE(memory_status, ?) = ? "
        "AND expires_at >= ? AND expires_at <= ? "
        "ORDER BY expires_at ASC",
        (user_id, scope, DEFAULT_MEMORY_STATUS, MemoryStatus.ACTIVE.value, now_iso, deadline),
    )
    return [_row_to_memory(r) for r in rows]


def get_recent_high_importance(
    user_id: int,
    types: list[str],
    min_importance: float = 0.6,
    max_age_days: int = 7,
    *,
    agent_id: str | None = None,
) -> list[Memory]:
    """Active high-importance memories created in the last max_age_days days."""
    if not types:
        return []
    cutoff = (datetime.now() - timedelta(days=max_age_days)).isoformat()
    placeholders = ",".join("?" for _ in types)
    scope = _current_agent_scope(agent_id)
    rows = _fetch_rows(
        f"SELECT {_SELECT_COLS} FROM napkin_log "
        f"WHERE user_id = ? AND is_active = 1 AND agent_id = ? "
        f"AND memory_type IN ({placeholders}) "
        "AND importance >= ? AND created_at >= ? "
        "AND COALESCE(memory_status, ?) = ? "
        "ORDER BY importance DESC, created_at DESC LIMIT 5",
        [user_id, scope, *types, min_importance, cutoff, DEFAULT_MEMORY_STATUS, MemoryStatus.ACTIVE.value],
    )
    return [_row_to_memory(r) for r in rows]


def set_memory_status(
    entry_id: int,
    *,
    memory_status: str,
    supersedes_memory_id: int | None = None,
) -> bool:
    """Update canonical lifecycle state for one memory."""
    previous = _fetch_row(
        "SELECT COALESCE(memory_status, ?) AS memory_status, agent_id FROM napkin_log WHERE id = ?",
        (DEFAULT_MEMORY_STATUS, entry_id),
    )
    updated = _write(
        "UPDATE napkin_log SET memory_status = ?, supersedes_memory_id = COALESCE(?, supersedes_memory_id) "
        "WHERE id = ?",
        (memory_status, supersedes_memory_id, entry_id),
    )
    if updated > 0 and previous:
        previous_status = str(
            previous["memory_status"] if isinstance(previous, dict) else previous[0] or DEFAULT_MEMORY_STATUS
        )
        previous_agent = str(
            previous["agent_id"] if isinstance(previous, dict) else previous[1] or _current_agent_scope()
        )
        if previous_status != memory_status:
            record_status_transition(previous_agent, previous_status, memory_status)
    return updated > 0


def find_conflicting_active_memories(memory: Memory) -> list[Memory]:
    """Find active same-scope memories that share a conflict key."""
    if not memory.conflict_key:
        return []
    scope = _current_agent_scope(memory.agent_id)
    rows = _fetch_rows(
        f"SELECT {_SELECT_COLS} FROM napkin_log "
        "WHERE user_id = ? AND is_active = 1 AND agent_id = ? "
        "AND COALESCE(conflict_key, '') = ? AND id != COALESCE(?, -1) "
        "AND COALESCE(memory_status, ?) = ? "
        "ORDER BY importance DESC, quality_score DESC, created_at DESC",
        (
            memory.user_id,
            scope,
            memory.conflict_key,
            memory.id,
            DEFAULT_MEMORY_STATUS,
            MemoryStatus.ACTIVE.value,
        ),
    )
    return [_row_to_memory(r) for r in rows]


def get_episode_bundle_candidates(
    *,
    user_id: int,
    query: str,
    limit: int = 24,
    agent_id: str | None = None,
    project_key: str = "",
    environment: str = "",
    team: str = "",
    session_id: str | None = None,
    source_episode_id: int | None = None,
) -> list[Memory]:
    """Return candidate memories that belong to prior execution/query episodes."""
    sql = [
        f"SELECT {_SELECT_COLS} FROM napkin_log WHERE user_id = ? AND is_active = 1",
        "AND source_episode_id IS NOT NULL",
        "AND COALESCE(memory_status, ?) = ?",
    ]
    params: list[object] = [user_id, DEFAULT_MEMORY_STATUS, MemoryStatus.ACTIVE.value]
    scope = _current_agent_scope(agent_id)
    sql.append("AND agent_id = ?")
    params.append(scope)
    if project_key:
        sql.append("AND COALESCE(project_key, '') IN (?, '')")
        params.append(project_key)
    if environment:
        sql.append("AND COALESCE(environment, '') IN (?, '')")
        params.append(environment)
    if team:
        sql.append("AND COALESCE(team, '') IN (?, '')")
        params.append(team)
    if session_id:
        sql.append("AND COALESCE(session_id, '') IN (?, '')")
        params.append(session_id)
    if source_episode_id is not None:
        sql.append("AND source_episode_id = ?")
        params.append(source_episode_id)
    else:
        query_terms = [term for term in query.lower().split() if len(term) > 2][:8]
        if query_terms:
            like_clauses = ["LOWER(content) LIKE ?" for _ in query_terms]
            sql.append(f"AND ({' OR '.join(like_clauses)})")
            params.extend(f"%{term}%" for term in query_terms)
    sql.append("ORDER BY quality_score DESC, importance DESC, created_at DESC LIMIT ?")
    params.append(limit)
    rows = _fetch_rows(" ".join(sql), params)
    return [_row_to_memory(r) for r in rows]


def log_memory_recall_audit(
    *,
    user_id: int,
    query_hash: str,
    query_preview: str,
    session_id: str | None,
    project_key: str,
    environment: str,
    team: str,
    considered: list[dict[str, object]],
    selected: list[dict[str, object]],
    discarded: list[dict[str, object]],
    conflicts: list[dict[str, object]],
    explanations: list[dict[str, object]],
    trust_score: float,
    selected_layers: list[str],
    retrieval_sources: list[str],
    total_considered: int | None = None,
    total_selected: int | None = None,
    total_discarded: int | None = None,
    conflict_group_count: int | None = None,
    agent_id: str | None = None,
    task_id: int | None = None,
) -> int:
    """Persist one recall audit envelope for inspection and postmortem review."""
    scope = _current_agent_scope(agent_id)
    return _insert(
        """INSERT INTO memory_recall_audit
           (agent_id, user_id, task_id, query_hash, query_preview, session_id, project_key, environment, team,
            trust_score, total_considered, total_selected, total_discarded, conflict_group_count,
            considered_json, selected_json, discarded_json, conflicts_json, explanations_json,
            selected_layers_csv, retrieval_sources_csv, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            scope,
            user_id,
            task_id,
            query_hash,
            query_preview,
            session_id,
            project_key,
            environment,
            team,
            trust_score,
            total_considered if total_considered is not None else len(considered),
            total_selected if total_selected is not None else len(selected),
            total_discarded if total_discarded is not None else len(discarded),
            conflict_group_count if conflict_group_count is not None else len(conflicts),
            json.dumps(considered, default=str),
            json.dumps(selected, default=str),
            json.dumps(discarded, default=str),
            json.dumps(conflicts, default=str),
            json.dumps(explanations, default=str),
            ",".join(selected_layers),
            ",".join(retrieval_sources),
            datetime.now().isoformat(),
        ),
    )


def get_memory_recall_audits(
    user_id: int,
    *,
    agent_id: str | None = None,
    limit: int = 10,
    task_id: int | None = None,
    query_contains: str = "",
    episode: str = "",
    layer: str = "",
    retrieval: str = "",
) -> list[dict[str, object]]:
    """Fetch recent recall audit envelopes for `/memory` inspection."""
    if limit <= 0:
        return []
    scope = _current_agent_scope(agent_id)
    sql = [
        "SELECT id, task_id, query_hash, query_preview, session_id, project_key, environment, team, trust_score, ",
        "total_considered, total_selected, total_discarded, conflict_group_count, ",
        "considered_json, selected_json, discarded_json, conflicts_json, explanations_json, ",
        "selected_layers_csv, retrieval_sources_csv, created_at ",
        "FROM memory_recall_audit WHERE user_id = ? AND agent_id = ?",
    ]
    params: list[object] = [user_id, scope]
    if task_id is not None:
        sql.append("AND task_id = ?")
        params.append(task_id)
    if query_contains:
        sql.append("AND LOWER(COALESCE(query_preview, '')) LIKE ?")
        params.append(f"%{query_contains.lower()}%")
    audits: list[dict[str, object]] = []
    batch_size = max(limit * 4, 50)
    offset = 0

    while len(audits) < limit:
        rows = _fetch_rows(
            " ".join([*sql, "ORDER BY created_at DESC LIMIT ? OFFSET ?"]),
            [*params, batch_size, offset],
        )
        if not rows:
            break
        for row in rows:
            if isinstance(row, dict):
                audit = {
                    "id": row.get("id"),
                    "task_id": row.get("task_id"),
                    "query_hash": str(row.get("query_hash") or ""),
                    "query_preview": str(row.get("query_preview") or ""),
                    "session_id": str(row.get("session_id") or ""),
                    "project_key": str(row.get("project_key") or ""),
                    "environment": str(row.get("environment") or ""),
                    "team": str(row.get("team") or ""),
                    "trust_score": float(row.get("trust_score") or 0.0),
                    "total_considered": int(cast(int | str, row.get("total_considered") or 0)),
                    "total_selected": int(cast(int | str, row.get("total_selected") or 0)),
                    "total_discarded": int(cast(int | str, row.get("total_discarded") or 0)),
                    "conflict_group_count": int(cast(int | str, row.get("conflict_group_count") or 0)),
                    "considered": json.loads(str(row.get("considered_json") or "[]")),
                    "selected": json.loads(str(row.get("selected_json") or "[]")),
                    "discarded": json.loads(str(row.get("discarded_json") or "[]")),
                    "conflicts": json.loads(str(row.get("conflicts_json") or "[]")),
                    "explanations": json.loads(str(row.get("explanations_json") or "[]")),
                    "selected_layers": [part for part in str(row.get("selected_layers_csv") or "").split(",") if part],
                    "retrieval_sources": [
                        part for part in str(row.get("retrieval_sources_csv") or "").split(",") if part
                    ],
                    "created_at": row.get("created_at"),
                }
            else:
                audit = {
                    "id": row[0],
                    "task_id": row[1],
                    "query_hash": row[2] or "",
                    "query_preview": row[3] or "",
                    "session_id": row[4] or "",
                    "project_key": row[5] or "",
                    "environment": row[6] or "",
                    "team": row[7] or "",
                    "trust_score": float(row[8] or 0.0),
                    "total_considered": int(row[9] or 0),
                    "total_selected": int(row[10] or 0),
                    "total_discarded": int(row[11] or 0),
                    "conflict_group_count": int(row[12] or 0),
                    "considered": json.loads(row[13]) if row[13] else [],
                    "selected": json.loads(row[14]) if row[14] else [],
                    "discarded": json.loads(row[15]) if row[15] else [],
                    "conflicts": json.loads(row[16]) if row[16] else [],
                    "explanations": json.loads(row[17]) if row[17] else [],
                    "selected_layers": [part for part in str(row[18] or "").split(",") if part],
                    "retrieval_sources": [part for part in str(row[19] or "").split(",") if part],
                    "created_at": row[20],
                }
            if episode:
                explanations = audit["explanations"]
                if not any(
                    str(item.get("source_episode_id") or "") == episode
                    for item in explanations
                    if isinstance(item, dict)
                ):
                    continue
            if layer:
                layers = {str(item.get("layer") or "") for item in audit["selected"] if isinstance(item, dict)}
                layers.update(audit["selected_layers"])
                if layer not in layers:
                    continue
            if retrieval:
                retrievals = {
                    str(item.get("retrieval_source") or "") for item in audit["selected"] if isinstance(item, dict)
                }
                retrievals.update(audit["retrieval_sources"])
                if retrieval not in retrievals:
                    continue
            audits.append(audit)
            if len(audits) >= limit:
                break
        if len(rows) < batch_size:
            break
        offset += batch_size
    return audits
