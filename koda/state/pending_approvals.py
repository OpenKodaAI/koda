"""Pending approval persistence in Postgres, the only approval store.

Stores pending approvals in the ``pending_approvals`` table (migration
``050_approval_tables``). A pending approval cannot outlive its process: its
handler, or the agent loop waiting on it, cannot be restored (D-163). Its row
lets the next start of its agent's worker expire it with an audit row. Every
agent shares the table, so each write names the rows of one agent.

A failed read or write is logged and raised to the caller. Nothing falls back
to a file: earlier releases wrote ``pending_approvals.json`` when a Postgres
write failed, and :mod:`koda.state.approval_import` imports that file once at
startup.
"""

from __future__ import annotations

import json
import time
from typing import Any

import koda.config as config_module
from koda.logging_config import get_logger
from koda.state.primary import get_primary_state_backend, primary_execute, primary_fetch_all, run_coro_sync

log = get_logger(__name__)


def _require_primary() -> None:
    if config_module.STATE_BACKEND != "postgres":
        raise RuntimeError("pending_approvals_primary_mode_required")
    if get_primary_state_backend(agent_id=config_module.AGENT_ID) is None:
        raise RuntimeError("pending_approvals_primary_backend_unavailable")


def _execute(action: str, query: str, params: tuple[Any, ...]) -> int:
    """Run one write and return its row count; a failure is logged and raised."""
    try:
        _require_primary()
        return int(run_coro_sync(primary_execute(query, params, agent_id=config_module.AGENT_ID)) or 0)
    except Exception:
        log.exception("pending_approvals_write_failed", action=action)
        raise


def _fetch_all(action: str, query: str, params: tuple[Any, ...]) -> list[Any]:
    try:
        _require_primary()
        return list(run_coro_sync(primary_fetch_all(query, params, agent_id=config_module.AGENT_ID)) or [])
    except Exception:
        log.exception("pending_approvals_read_failed", action=action)
        raise


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _optional_chat_id(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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


def _row_params(op_id: str, entry: dict[str, Any]) -> tuple[Any, ...]:
    return (
        op_id,
        str(entry.get("op_type") or "user"),
        int(entry.get("user_id") or 0) if entry.get("user_id") is not None else None,
        str(entry.get("agent_id") or "") or None,
        str(entry.get("session_id") or "") or None,
        _optional_chat_id(entry.get("chat_id")),
        str(entry.get("description") or ""),
        float(entry.get("created_at") or 0),
        float(entry.get("expires_at") or 0),
        _json_dumps(entry),
    )


_INSERT = """
    INSERT INTO pending_approvals (
        op_id, op_type, user_id, agent_id, session_id, chat_id,
        description, created_at, expires_at, payload_json
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def import_pending_ops(entries: dict[str, Any]) -> int:
    """Insert pending ops read from the retired JSON file; an op already stored is left as it is.

    Returns how many rows were inserted.
    """
    inserted = 0
    for op_id, entry in entries.items():
        if not isinstance(entry, dict) or not str(op_id):
            continue
        try:
            params = _row_params(str(op_id), dict(entry, op_id=str(op_id)))
        except (TypeError, ValueError):
            log.warning("pending_approvals_import_entry_skipped", op_id=str(op_id))
            continue
        inserted += _execute("import", _INSERT + " ON CONFLICT(op_id) DO NOTHING", params)
    return inserted


# Public API


async def save_pending_op(
    op_id: str,
    data: dict[str, Any],
    ttl_seconds: int,
) -> None:
    """Persist a single pending operation with a TTL."""
    entry = _entry_for_save(op_id, data, ttl_seconds)
    _execute(
        "save",
        _INSERT
        + """
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
        _row_params(op_id, entry),
    )


async def expire_pending_ops(*, agent_id: str) -> int:
    """Delete the live pending ops of ``agent_id``, with one ``approval.pending_expired`` audit row each.

    A worker calls it once at startup, before it asks for any approval: the ops an
    earlier process of its agent left cannot run, as their handlers cannot be restored
    (D-163). Rows of another agent, or with no agent, are left as they are (D-366).
    Returns how many ops expired.
    """
    return _execute(
        "expire",
        """
        WITH expired AS (
            DELETE FROM pending_approvals
             WHERE agent_id = ? AND expires_at > ?
            RETURNING op_id, op_type, user_id, agent_id, session_id, chat_id
        )
        INSERT INTO audit_events (agent_id, timestamp, event_type, user_id, details_json)
        SELECT agent_id, NOW(), 'approval.pending_expired', user_id,
               jsonb_build_object(
                   'op_id', op_id,
                   'op_type', op_type,
                   'session_id', session_id,
                   'chat_id', chat_id,
                   'reason', 'restart'
               )
          FROM expired
        """,
        (agent_id, time.time()),
    )


async def remove_pending_op(op_id: str, *, agent_id: str) -> int:
    """Delete one pending op of ``agent_id``; an op of another agent is left in place. Returns the rows deleted."""
    return _execute("remove", "DELETE FROM pending_approvals WHERE op_id = ? AND agent_id = ?", (op_id, agent_id))


async def remove_pending_ops(
    *,
    user_id: int | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
    chat_id: int | None = None,
) -> int:
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
    return _execute("remove_matching", "DELETE FROM pending_approvals WHERE " + " AND ".join(clauses), tuple(params))


async def cleanup_expired_ops() -> None:
    """Remove all expired entries from the persisted store."""
    _execute("cleanup", "DELETE FROM pending_approvals WHERE expires_at <= ?", (time.time(),))
