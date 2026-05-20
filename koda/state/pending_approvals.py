"""Pending approval persistence with Postgres-primary support.

Stores pending approvals in the primary state backend when Koda is running in
Postgres mode, falling back to ``{STATE_ROOT_DIR}/pending_approvals.json`` so
approvals survive process restarts in local/dev mode.  asyncio.Event objects
cannot be serialized, so callers must recreate them after loading.

Note: functions are declared ``async`` for interface consistency with the rest
of the state layer, but file I/O is synchronous.  This is acceptable because
the JSON payload is small (< 10 KB) and the writes are infrequent.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import koda.config as config_module
from koda.logging_config import get_logger
from koda.state.primary import get_primary_state_backend, primary_execute, primary_fetch_all, run_coro_sync

log = get_logger(__name__)

_PRIMARY_SCHEMA_READY = False


def _file_path() -> Path:
    return config_module.STATE_ROOT_DIR / "pending_approvals.json"


def _primary_enabled() -> bool:
    return (
        config_module.STATE_BACKEND == "postgres"
        and get_primary_state_backend(agent_id=config_module.AGENT_ID) is not None
    )


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _json_loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _optional_chat_id(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _ensure_primary_schema() -> None:
    global _PRIMARY_SCHEMA_READY
    if _PRIMARY_SCHEMA_READY or not _primary_enabled():
        return
    run_coro_sync(
        primary_execute(
            """
            CREATE TABLE IF NOT EXISTS pending_approvals (
                op_id TEXT PRIMARY KEY,
                op_type TEXT NOT NULL,
                user_id INTEGER,
                agent_id TEXT,
                session_id TEXT,
                chat_id INTEGER,
                description TEXT,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                payload_json TEXT NOT NULL
            )
            """,
            agent_id=config_module.AGENT_ID,
        )
    )
    _PRIMARY_SCHEMA_READY = True


def _entry_for_save(op_id: str, data: dict[str, Any], ttl_seconds: int) -> dict[str, Any]:
    now = time.time()
    entry = dict(data)
    entry.update(
        {
            "op_id": op_id,
            "created_at": now,
            "expires_at": now + ttl_seconds,
            "op_type": data.get("op_type", "user"),
            "user_id": data.get("user_id"),
            "chat_id": data.get("chat_id"),
            "session_id": data.get("session_id"),
            "agent_id": data.get("agent_id"),
            "description": data.get("description", ""),
        }
    )
    return entry


def _pending_filter_matches(
    entry: dict[str, Any],
    *,
    user_id: int | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
    chat_id: int | None = None,
) -> bool:
    if user_id is not None and int(entry.get("user_id") or 0) != user_id:
        return False
    if agent_id is not None and str(entry.get("agent_id") or "") != agent_id:
        return False
    if session_id is not None and str(entry.get("session_id") or "") != session_id:
        return False
    return chat_id is None or int(entry.get("chat_id") or 0) == chat_id


def _read_raw() -> dict[str, Any]:
    """Read the JSON file, returning an empty dict on any error."""
    fp = _file_path()
    if not fp.exists():
        return {}
    try:
        text = fp.read_text(encoding="utf-8")
        data = json.loads(text)
        if not isinstance(data, dict):
            return {}
        return data
    except Exception:
        log.warning("pending_approvals: failed to read %s, starting fresh", fp, exc_info=True)
        return {}


def _write_raw(data: dict[str, Any]) -> None:
    """Persist *data* to the JSON file, creating parent dirs as needed."""
    fp = _file_path()
    try:
        fp.parent.mkdir(parents=True, exist_ok=True)
        tmp = fp.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, default=str), encoding="utf-8")
        tmp.replace(fp)
    except Exception:
        log.warning("pending_approvals: failed to write %s", fp, exc_info=True)


# Public API


async def save_pending_op(
    op_id: str,
    data: dict[str, Any],
    ttl_seconds: int,
) -> None:
    """Persist a single pending operation with a TTL."""
    entry = _entry_for_save(op_id, data, ttl_seconds)
    if _primary_enabled():
        try:
            _ensure_primary_schema()
            run_coro_sync(
                primary_execute(
                    """
                    INSERT INTO pending_approvals (
                        op_id, op_type, user_id, agent_id, session_id, chat_id,
                        description, created_at, expires_at, payload_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(op_id) DO UPDATE SET
                        op_type = excluded.op_type,
                        user_id = excluded.user_id,
                        agent_id = excluded.agent_id,
                        session_id = excluded.session_id,
                        chat_id = excluded.chat_id,
                        description = excluded.description,
                        created_at = excluded.created_at,
                        expires_at = excluded.expires_at,
                        payload_json = excluded.payload_json
                    """,
                    (
                        op_id,
                        str(entry.get("op_type") or "user"),
                        int(entry.get("user_id") or 0) if entry.get("user_id") is not None else None,
                        str(entry.get("agent_id") or "") or None,
                        str(entry.get("session_id") or "") or None,
                        _optional_chat_id(entry.get("chat_id")),
                        str(entry.get("description") or ""),
                        float(entry["created_at"]),
                        float(entry["expires_at"]),
                        _json_dumps(entry),
                    ),
                    agent_id=config_module.AGENT_ID,
                )
            )
            return
        except Exception:
            log.warning("pending_approvals: failed to persist in primary backend", exc_info=True)

    store = _read_raw()
    store[op_id] = entry
    _write_raw(store)


async def load_pending_ops() -> dict[str, dict[str, Any]]:
    """Load all non-expired pending ops from disk."""
    now = time.time()
    if _primary_enabled():
        try:
            _ensure_primary_schema()
            rows = (
                run_coro_sync(
                    primary_fetch_all(
                        """
                        SELECT op_id, payload_json, expires_at
                          FROM pending_approvals
                         WHERE expires_at > ?
                        """,
                        (now,),
                        agent_id=config_module.AGENT_ID,
                    )
                )
                or []
            )
            primary_result: dict[str, dict[str, Any]] = {}
            for row in rows:
                if not isinstance(row, dict):
                    continue
                op_id = str(row.get("op_id") or "")
                payload = _json_loads(str(row.get("payload_json") or ""))
                if op_id and payload:
                    primary_result[op_id] = payload
            return primary_result
        except Exception:
            log.warning("pending_approvals: failed to load from primary backend", exc_info=True)

    raw = _read_raw()
    result: dict[str, dict[str, Any]] = {}
    for op_id, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        expires_at = entry.get("expires_at", 0)
        if isinstance(expires_at, (int, float)) and expires_at > now:
            result[op_id] = entry
    return result


async def remove_pending_op(op_id: str) -> None:
    """Remove a single pending op from the persisted store."""
    if _primary_enabled():
        try:
            _ensure_primary_schema()
            run_coro_sync(
                primary_execute(
                    "DELETE FROM pending_approvals WHERE op_id = ?",
                    (op_id,),
                    agent_id=config_module.AGENT_ID,
                )
            )
            return
        except Exception:
            log.warning("pending_approvals: failed to remove from primary backend", exc_info=True)

    store = _read_raw()
    if op_id in store:
        del store[op_id]
        _write_raw(store)


async def remove_pending_ops(
    *,
    user_id: int | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
    chat_id: int | None = None,
) -> int:
    if _primary_enabled():
        try:
            _ensure_primary_schema()
            clauses = []
            params: list[Any] = []
            if user_id is not None:
                clauses.append("user_id = ?")
                params.append(user_id)
            if agent_id is not None:
                clauses.append("agent_id = ?")
                params.append(agent_id)
            if session_id is not None:
                clauses.append("session_id = ?")
                params.append(session_id)
            if chat_id is not None:
                clauses.append("chat_id = ?")
                params.append(chat_id)
            if not clauses:
                return 0
            query = "DELETE FROM pending_approvals WHERE " + " AND ".join(clauses)
            return int(run_coro_sync(primary_execute(query, tuple(params), agent_id=config_module.AGENT_ID)) or 0)
        except Exception:
            log.warning("pending_approvals: failed to bulk-remove from primary backend", exc_info=True)

    store = _read_raw()
    kept: dict[str, Any] = {}
    removed = 0
    for op_id, entry in store.items():
        if not isinstance(entry, dict):
            kept[op_id] = entry
            continue
        if not _pending_filter_matches(
            entry,
            user_id=user_id,
            agent_id=agent_id,
            session_id=session_id,
            chat_id=chat_id,
        ):
            kept[op_id] = entry
            continue
        removed += 1
    if removed:
        _write_raw(kept)
    return removed


async def cleanup_expired_ops() -> None:
    """Remove all expired entries from the persisted store."""
    if _primary_enabled():
        try:
            _ensure_primary_schema()
            run_coro_sync(
                primary_execute(
                    "DELETE FROM pending_approvals WHERE expires_at <= ?",
                    (time.time(),),
                    agent_id=config_module.AGENT_ID,
                )
            )
            return
        except Exception:
            log.warning("pending_approvals: failed to cleanup primary backend", exc_info=True)

    raw = _read_raw()
    now = time.time()
    cleaned: dict[str, Any] = {}
    for op_id, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        expires_at = entry.get("expires_at", 0)
        if isinstance(expires_at, (int, float)) and expires_at > now:
            cleaned[op_id] = entry
    if len(cleaned) != len(raw):
        _write_raw(cleaned)
