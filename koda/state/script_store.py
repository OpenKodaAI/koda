"""Primary reusable script library store."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from koda.config import AGENT_ID
from koda.state.agent_scope import normalize_agent_scope
from koda.state.primary import (
    primary_execute,
    primary_fetch_all,
    primary_fetch_one,
    primary_fetch_val,
    require_primary_state_backend,
    run_coro_sync,
)


def _normalize_agent_scope(agent_id: str | None) -> str:
    return normalize_agent_scope(agent_id, fallback=AGENT_ID)


def _require_primary(agent_id: str | None = None) -> str:
    scope = _normalize_agent_scope(agent_id)
    require_primary_state_backend(agent_id=scope, error="script library requires the primary state backend")
    return scope


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _script_row_from_primary(row: dict[str, Any] | None) -> tuple[Any, ...] | None:
    if row is None:
        return None
    return (
        int(row["id"]),
        int(row["user_id"]),
        str(row["title"] or ""),
        row.get("description"),
        row.get("language"),
        str(row["content"] or ""),
        row.get("source_query"),
        str(row.get("tags") or "[]"),
        int(row.get("use_count") or 0),
        row.get("last_used_at"),
        float(row.get("quality_score") or 0.5),
        str(row.get("created_at") or ""),
        str(row.get("updated_at") or ""),
        bool(row.get("is_active")),
    )


def _script_list_row_from_primary(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        int(row["id"]),
        str(row["title"] or ""),
        row.get("description"),
        row.get("language"),
        int(row.get("use_count") or 0),
        float(row.get("quality_score") or 0.5),
        str(row.get("created_at") or ""),
    )


def script_insert(
    user_id: int,
    title: str,
    description: str | None,
    language: str | None,
    content: str,
    source_query: str | None,
    tags: str = "[]",
    agent_id: str | None = None,
) -> int | None:
    now = _now_iso()
    scope = _require_primary(agent_id)
    row_id = run_coro_sync(
        primary_fetch_val(
            """INSERT INTO script_library
               (agent_id, user_id, title, description, language, content, source_query, tags, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            (scope, user_id, title, description, language, content, source_query, tags, now, now),
            agent_id=scope,
        )
    )
    return int(row_id) if row_id is not None else None


def script_get(script_id: int, agent_id: str | None = None) -> tuple[Any, ...] | None:
    scope = _require_primary(agent_id)
    row = run_coro_sync(
        primary_fetch_one(
            "SELECT id, user_id, title, description, language, content, source_query, tags, "
            "use_count, last_used_at, quality_score, created_at, updated_at, is_active "
            "FROM script_library WHERE id = ? AND agent_id = ?",
            (script_id, scope),
            agent_id=scope,
        )
    )
    return _script_row_from_primary(row)


def script_list_by_user(
    user_id: int,
    language: str | None = None,
    limit: int = 50,
    agent_id: str | None = None,
) -> list[tuple[Any, ...]]:
    scope = _require_primary(agent_id)
    if language:
        rows = run_coro_sync(
            primary_fetch_all(
                "SELECT id, title, description, language, use_count, quality_score, created_at "
                "FROM script_library WHERE user_id = ? AND language = ? AND agent_id = ? "
                "AND is_active = TRUE ORDER BY use_count DESC, quality_score DESC LIMIT ?",
                (user_id, language, scope, limit),
                agent_id=scope,
            )
        )
    else:
        rows = run_coro_sync(
            primary_fetch_all(
                "SELECT id, title, description, language, use_count, quality_score, created_at "
                "FROM script_library WHERE user_id = ? AND agent_id = ? AND is_active = TRUE "
                "ORDER BY use_count DESC, quality_score DESC LIMIT ?",
                (user_id, scope, limit),
                agent_id=scope,
            )
        )
    return [_script_list_row_from_primary(row) for row in rows]


def script_list_for_semantic_index(
    user_id: int,
    *,
    limit: int = 200,
    agent_id: str | None = None,
) -> list[dict[str, Any]]:
    scope = _require_primary(agent_id)
    rows = run_coro_sync(
        primary_fetch_all(
            """
            SELECT id, title, description, language, content, use_count, quality_score, is_active
            FROM script_library
            WHERE user_id = ? AND agent_id = ? AND is_active = TRUE
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            (user_id, scope, limit),
            agent_id=scope,
        )
    )
    return [
        {
            "id": int(row["id"]),
            "title": str(row.get("title") or ""),
            "description": row.get("description"),
            "language": row.get("language"),
            "content": str(row.get("content") or ""),
            "use_count": int(row.get("use_count") or 0),
            "quality_score": float(row.get("quality_score") or 0.5),
            "is_active": bool(row.get("is_active")),
        }
        for row in rows
    ]


def script_record_use(script_id: int, agent_id: str | None = None) -> None:
    scope = _require_primary(agent_id)
    run_coro_sync(
        primary_execute(
            "UPDATE script_library SET use_count = use_count + 1, last_used_at = ? WHERE id = ? AND agent_id = ?",
            (_now_iso(), script_id, scope),
            agent_id=scope,
        )
    )


def script_update_quality(script_id: int, delta: float, agent_id: str | None = None) -> None:
    scope = _require_primary(agent_id)
    run_coro_sync(
        primary_execute(
            "UPDATE script_library SET quality_score = MIN(1.0, MAX(0.0, quality_score + ?)), "
            "updated_at = ? WHERE id = ? AND agent_id = ?",
            (delta, _now_iso(), script_id, scope),
            agent_id=scope,
        )
    )


def script_deactivate(script_id: int, user_id: int, agent_id: str | None = None) -> bool:
    scope = _require_primary(agent_id)
    updated = run_coro_sync(
        primary_execute(
            "UPDATE script_library SET is_active = FALSE, updated_at = ? WHERE id = ? AND user_id = ? AND agent_id = ?",
            (_now_iso(), script_id, user_id, scope),
            agent_id=scope,
        )
    )
    return bool(updated)


def script_cleanup_low_quality(threshold: float = 0.1, agent_id: str | None = None) -> int:
    scope = _require_primary(agent_id)
    deleted = run_coro_sync(
        primary_execute(
            "DELETE FROM script_library WHERE agent_id = ? AND is_active = TRUE AND quality_score < ?",
            (scope, threshold),
            agent_id=scope,
        )
    )
    return int(deleted or 0)


def script_get_stats(user_id: int, agent_id: str | None = None) -> dict[str, Any]:
    scope = _require_primary(agent_id)
    row = run_coro_sync(
        primary_fetch_one(
            "SELECT COUNT(*) AS scripts, COALESCE(SUM(use_count), 0) AS total_uses "
            "FROM script_library WHERE user_id = ? AND agent_id = ? AND is_active = TRUE",
            (user_id, scope),
            agent_id=scope,
        )
    )
    return {
        "scripts": int((row or {}).get("scripts") or 0),
        "total_uses": int((row or {}).get("total_uses") or 0),
    }
