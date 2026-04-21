"""Per-agent asset registry over the shared primary backend."""

from __future__ import annotations

import json
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

_PRIMARY_SCOPE_PREFIX = "agent_assets"


def _scope(agent_id: str | None = None) -> str:
    return normalize_agent_scope(agent_id, fallback=AGENT_ID)


def _require_primary(agent_id: str | None = None) -> str:
    scope = _scope(agent_id)
    require_primary_state_backend(agent_id=scope, error="asset registry requires the primary state backend")
    return scope


def _primary_scope_id(agent_id: str | None = None) -> str:
    scope = _scope(agent_id)
    return f"{_PRIMARY_SCOPE_PREFIX}:{scope}"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _asset_row_from_primary(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": int(row.get("id") or 0),
        "agent_id": str(row.get("agent_id") or ""),
        "asset_key": str(row.get("asset_key") or ""),
        "title": str(row.get("title") or ""),
        "kind": str(row.get("kind") or "entry"),
        "content_text": str(row.get("content_text") or ""),
        "body": json.loads(str(row.get("body_json") or "{}")),
        "enabled": bool(row.get("enabled")),
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }


def upsert_asset(
    *,
    asset_key: str,
    title: str,
    kind: str,
    content_text: str,
    body: dict[str, Any] | None = None,
    enabled: bool = True,
    agent_id: str | None = None,
) -> int | None:
    scope = _require_primary(agent_id)
    now = _now_iso()
    body_json = json.dumps(body or {}, default=str)
    row_id = run_coro_sync(
        primary_fetch_val(
            """
            INSERT INTO cp_knowledge_assets
                (scope_id, agent_id, asset_key, title, kind, content_text, body_json, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(scope_id, asset_key) DO UPDATE SET
                agent_id = EXCLUDED.agent_id,
                title = EXCLUDED.title,
                kind = EXCLUDED.kind,
                content_text = EXCLUDED.content_text,
                body_json = EXCLUDED.body_json,
                enabled = EXCLUDED.enabled,
                updated_at = EXCLUDED.updated_at
            RETURNING id
            """,
            (
                _primary_scope_id(scope),
                scope,
                asset_key,
                title,
                kind,
                content_text,
                body_json,
                1 if enabled else 0,
                now,
                now,
            ),
            agent_id=scope,
        )
    )
    return int(row_id) if row_id is not None else None


def disable_asset(asset_key: str, *, agent_id: str | None = None) -> bool:
    scope = _require_primary(agent_id)
    updated = run_coro_sync(
        primary_execute(
            """
            UPDATE cp_knowledge_assets
            SET enabled = 0, updated_at = ?
            WHERE scope_id = ? AND agent_id = ? AND asset_key = ? AND enabled = 1
            """,
            (_now_iso(), _primary_scope_id(scope), scope, asset_key),
            agent_id=scope,
        )
    )
    return bool(updated)


def search_assets(
    *,
    query: str,
    limit: int = 12,
    kinds: tuple[str, ...] = (),
    agent_id: str | None = None,
) -> list[dict[str, Any]]:
    scope = _require_primary(agent_id)
    normalized_query = str(query or "").strip().lower()
    query_terms = [term for term in normalized_query.replace("/", " ").replace("_", " ").split() if len(term) >= 3]
    like_terms = [f"%{term}%" for term in query_terms[:5]]
    sql = """
        SELECT id, agent_id, asset_key, title, kind, content_text, body_json, enabled, created_at, updated_at
        FROM cp_knowledge_assets
        WHERE scope_id = ? AND agent_id = ? AND enabled = 1
    """
    params: list[Any] = [_primary_scope_id(scope), scope]
    if kinds:
        placeholders = ",".join("?" for _ in kinds)
        sql += f" AND kind IN ({placeholders})"
        params.extend(kinds)
    if like_terms:
        token_clause = " OR ".join(
            "(LOWER(title) LIKE ? OR LOWER(content_text) LIKE ? OR LOWER(body_json) LIKE ?)" for _ in like_terms
        )
        sql += f" AND ({token_clause})"
        for term in like_terms:
            params.extend([term, term, term])
    sql += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)
    rows = run_coro_sync(primary_fetch_all(sql, tuple(params), agent_id=scope)) or []
    return [row for row in (_asset_row_from_primary(row) for row in rows) if row is not None]


def get_asset(asset_key: str, *, agent_id: str | None = None) -> dict[str, Any] | None:
    scope = _require_primary(agent_id)
    row = run_coro_sync(
        primary_fetch_one(
            """
            SELECT id, agent_id, asset_key, title, kind, content_text, body_json, enabled, created_at, updated_at
            FROM cp_knowledge_assets
            WHERE scope_id = ? AND agent_id = ? AND asset_key = ?
            """,
            (_primary_scope_id(scope), scope, asset_key),
            agent_id=scope,
        )
    )
    return _asset_row_from_primary(row)
