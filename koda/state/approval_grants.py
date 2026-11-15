"""Scoped approval-grant persistence in Postgres, the only approval store.

Migration ``050_approval_tables`` creates the ``approval_grants`` table. Every
agent shares it, so each write names one grant of one agent: saving a grant
upserts its row, using one updates its row only while the row exists, and
removing one deletes it, scoped by its ``agent_id``. Each write is a single
statement, which Postgres runs as one transaction: a failure leaves the row and
every other row as they were.

A failed read or write is logged and raised to the caller. Nothing falls back
to a file: earlier releases wrote ``approval_grants.json`` when a Postgres write
failed, and :mod:`koda.state.approval_import` imports that file once at startup.
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
        raise RuntimeError("approval_grants_primary_mode_required")
    if get_primary_state_backend(agent_id=config_module.AGENT_ID) is None:
        raise RuntimeError("approval_grants_primary_backend_unavailable")


def _execute(action: str, query: str, params: tuple[Any, ...]) -> int:
    """Run one write and return its row count; a failure is logged and raised."""
    try:
        _require_primary()
        return int(run_coro_sync(primary_execute(query, params, agent_id=config_module.AGENT_ID)) or 0)
    except Exception:
        log.exception("approval_grants_write_failed", action=action)
        raise


def _fetch_all(action: str, query: str, params: tuple[Any, ...]) -> list[Any]:
    try:
        _require_primary()
        return list(run_coro_sync(primary_fetch_all(query, params, agent_id=config_module.AGENT_ID)) or [])
    except Exception:
        log.exception("approval_grants_read_failed", action=action)
        raise


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


def _row_params(grant_id: str, entry: dict[str, Any]) -> tuple[Any, ...]:
    return (
        grant_id,
        int(entry.get("user_id") or 0),
        str(entry.get("agent_id") or ""),
        str(entry.get("session_id") or "") or None,
        _optional_chat_id(entry.get("chat_id")),
        float(entry.get("created_at") or 0),
        float(entry.get("expires_at") or 0),
        _json_dumps(entry),
    )


def store_approval_grants(grants: list[dict[str, Any]]) -> None:
    """Insert or update grants, each with its ``grant_id``, ``created_at`` and ``expires_at``.

    It returns once Postgres has stored them: one statement, so either every grant is
    stored or none is, and a failure is raised. An existing row of another agent is
    left unchanged.
    """
    if not grants:
        return
    rows = [_row_params(str(grant["grant_id"]), grant) for grant in grants]
    _execute(
        "upsert",
        """
        INSERT INTO approval_grants (
            grant_id, user_id, agent_id, session_id, chat_id, created_at, expires_at, payload_json
        )
        VALUES """
        + ", ".join("(?, ?, ?, ?, ?, ?, ?, ?)" for _ in rows)
        + """
        ON CONFLICT(grant_id) DO UPDATE SET
            user_id = excluded.user_id,
            session_id = excluded.session_id,
            chat_id = excluded.chat_id,
            created_at = excluded.created_at,
            expires_at = excluded.expires_at,
            payload_json = excluded.payload_json
        WHERE approval_grants.agent_id = excluded.agent_id
        """,
        tuple(value for row in rows for value in row),
    )


def import_approval_grants(entries: dict[str, Any]) -> int:
    """Insert grants read from the retired JSON file, each one expired, with an audit row.

    The file cannot tell a grant the old release used up or revoked from an unused one:
    those writes deleted a Postgres row that was not there and left the file as it was.
    So every imported grant is stored with ``expires_at`` 0, in its row and its payload,
    and authorizes nothing; its user approves again. One ``approval.grant_expired``
    audit row records each grant inserted, with the expiry the file gave it. Each grant
    keeps its ``agent_id``. A grant already stored is left as it is and is not
    audited again; one deleted since an earlier import of the same file comes back, expired
    again. Returns how many grants were inserted.
    """
    inserted = 0
    for grant_id, entry in entries.items():
        if not isinstance(entry, dict) or not str(grant_id):
            continue
        try:
            expires_at = float(entry.get("expires_at") or 0)
            params = _row_params(str(grant_id), dict(entry, grant_id=str(grant_id), expires_at=0))
        except (TypeError, ValueError):
            log.warning("approval_grants_import_entry_skipped", grant_id=str(grant_id))
            continue
        inserted += _execute(
            "import",
            """
            WITH imported AS (
                INSERT INTO approval_grants (
                    grant_id, user_id, agent_id, session_id, chat_id, created_at, expires_at, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(grant_id) DO NOTHING
                RETURNING grant_id, user_id, agent_id, session_id, chat_id
            )
            INSERT INTO audit_events (agent_id, timestamp, event_type, user_id, details_json)
            SELECT COALESCE(NULLIF(btrim(agent_id), ''), 'global'), NOW(), 'approval.grant_expired', user_id,
                   jsonb_build_object(
                       'grant_id', grant_id,
                       'session_id', session_id,
                       'chat_id', chat_id,
                       'expires_at', CAST(? AS DOUBLE PRECISION),
                       'reason', 'imported_from_retired_json'
                   )
              FROM imported
            """,
            (*params, expires_at),
        )
    return inserted


async def save_approval_grant(grant_id: str, payload: dict[str, Any], ttl_seconds: int) -> None:
    now = time.time()
    entry = dict(payload)
    entry["grant_id"] = grant_id
    entry["created_at"] = now
    entry["expires_at"] = now + ttl_seconds
    store_approval_grants([entry])


async def update_approval_grant(grant_id: str, payload: dict[str, Any]) -> int:
    """Store a grant's new state, such as its remaining uses, if its row is still there.

    Returns 1 when the row was updated, and 0 when the grant is gone because it
    was revoked or cleaned up: a use never re-inserts it (D-343).
    """
    return _execute(
        "update",
        "UPDATE approval_grants SET payload_json = ? WHERE grant_id = ? AND agent_id = ?",
        (_json_dumps(dict(payload, grant_id=grant_id)), grant_id, str(payload.get("agent_id") or "")),
    )


async def load_approval_grants(*, agent_id: str) -> dict[str, dict[str, Any]]:
    """Return the live grants of ``agent_id``; grants of another agent, or with no agent, stay out (D-366)."""
    rows = _fetch_all(
        "load",
        """
        SELECT grant_id, payload_json, expires_at
          FROM approval_grants
         WHERE agent_id = ? AND expires_at > ?
        """,
        (agent_id, time.time()),
    )
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        grant_id = str(row.get("grant_id") or "")
        payload = _json_loads(str(row.get("payload_json") or ""))
        if grant_id and payload:
            result[grant_id] = payload
    return result


async def remove_approval_grant(grant_id: str, *, agent_id: str) -> int:
    """Delete one grant of ``agent_id``; a grant of another agent is left in place. Returns the rows deleted."""
    return _execute(
        "remove",
        "DELETE FROM approval_grants WHERE grant_id = ? AND agent_id = ?",
        (grant_id, agent_id),
    )


async def remove_approval_grants(
    *,
    agent_id: str,
    user_id: int | None = None,
    session_id: str | None = None,
    chat_id: int | None = None,
) -> int:
    """Delete the grants of ``agent_id`` that match every given filter."""
    clauses = ["agent_id = ?"]
    params: list[Any] = [agent_id]
    if user_id is not None:
        clauses.append("user_id = ?")
        params.append(user_id)
    if session_id is not None:
        clauses.append("session_id = ?")
        params.append(session_id)
    if chat_id is not None:
        clauses.append("chat_id = ?")
        params.append(chat_id)
    return _execute("remove_matching", "DELETE FROM approval_grants WHERE " + " AND ".join(clauses), tuple(params))


async def cleanup_expired_approval_grants() -> None:
    _execute("cleanup", "DELETE FROM approval_grants WHERE expires_at <= ?", (time.time(),))
