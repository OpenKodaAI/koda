"""Scoped approval-grant persistence with primary-backend support."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import koda.config as config_module
from koda.logging_config import get_logger
from koda.state_primary import get_primary_state_backend, primary_execute, primary_fetch_all, run_coro_sync

log = get_logger(__name__)

_PRIMARY_SCHEMA_READY = False


def _file_path() -> Path:
    return config_module.STATE_ROOT_DIR / "approval_grants.json"


def _primary_enabled() -> bool:
    return (
        config_module.STATE_BACKEND == "postgres"
        and get_primary_state_backend(agent_id=config_module.AGENT_ID) is not None
    )


def _read_raw() -> dict[str, Any]:
    fp = _file_path()
    if not fp.exists():
        return {}
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        log.warning("approval_grants: failed to read %s", fp, exc_info=True)
        return {}


def _write_raw(data: dict[str, Any]) -> None:
    fp = _file_path()
    try:
        fp.parent.mkdir(parents=True, exist_ok=True)
        tmp = fp.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
        tmp.replace(fp)
    except Exception:
        log.warning("approval_grants: failed to write %s", fp, exc_info=True)


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


def _grant_filter_matches(
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
    backend = get_primary_state_backend(agent_id=config_module.AGENT_ID)
    if backend is None:
        return
    run_coro_sync(
        primary_execute(
            """
            CREATE TABLE IF NOT EXISTS approval_grants (
                grant_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                agent_id TEXT NOT NULL,
                session_id TEXT,
                chat_id INTEGER,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                payload_json TEXT NOT NULL
            )
            """,
            agent_id=config_module.AGENT_ID,
        )
    )
    _PRIMARY_SCHEMA_READY = True


def _primary_upsert(grant_id: str, payload: dict[str, Any], ttl_seconds: int) -> None:
    _ensure_primary_schema()
    now = time.time()
    entry = dict(payload)
    entry["grant_id"] = grant_id
    entry["created_at"] = now
    entry["expires_at"] = now + ttl_seconds
    run_coro_sync(
        primary_execute(
            """
            INSERT INTO approval_grants (
                grant_id, user_id, agent_id, session_id, chat_id, created_at, expires_at, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(grant_id) DO UPDATE SET
                user_id = excluded.user_id,
                agent_id = excluded.agent_id,
                session_id = excluded.session_id,
                chat_id = excluded.chat_id,
                created_at = excluded.created_at,
                expires_at = excluded.expires_at,
                payload_json = excluded.payload_json
            """,
            (
                grant_id,
                int(entry.get("user_id") or 0),
                str(entry.get("agent_id") or ""),
                str(entry.get("session_id") or "") or None,
                _optional_chat_id(entry.get("chat_id")),
                entry["created_at"],
                entry["expires_at"],
                _json_dumps(entry),
            ),
            agent_id=config_module.AGENT_ID,
        )
    )


async def save_approval_grant(grant_id: str, payload: dict[str, Any], ttl_seconds: int) -> None:
    if _primary_enabled():
        try:
            _primary_upsert(grant_id, payload, ttl_seconds)
            return
        except Exception:
            log.warning("approval_grants: failed to persist in primary backend", exc_info=True)

    now = time.time()
    store = _read_raw()
    entry = dict(payload)
    entry["grant_id"] = grant_id
    entry["created_at"] = now
    entry["expires_at"] = now + ttl_seconds
    store[grant_id] = entry
    _write_raw(store)


async def load_approval_grants() -> dict[str, dict[str, Any]]:
    now = time.time()
    if _primary_enabled():
        try:
            _ensure_primary_schema()
            rows = (
                run_coro_sync(
                    primary_fetch_all(
                        """
                    SELECT grant_id, payload_json, expires_at
                      FROM approval_grants
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
                grant_id = str(row.get("grant_id") or "")
                payload = _json_loads(str(row.get("payload_json") or ""))
                if grant_id and payload:
                    primary_result[grant_id] = payload
            return primary_result
        except Exception:
            log.warning("approval_grants: failed to load from primary backend", exc_info=True)

    store = _read_raw()
    result: dict[str, dict[str, Any]] = {}
    for grant_id, entry in store.items():
        if not isinstance(entry, dict):
            continue
        expires_at = entry.get("expires_at")
        if isinstance(expires_at, (int, float)) and expires_at > now:
            result[grant_id] = entry
    return result


async def remove_approval_grant(grant_id: str) -> None:
    if _primary_enabled():
        try:
            _ensure_primary_schema()
            run_coro_sync(
                primary_execute(
                    "DELETE FROM approval_grants WHERE grant_id = ?",
                    (grant_id,),
                    agent_id=config_module.AGENT_ID,
                )
            )
            return
        except Exception:
            log.warning("approval_grants: failed to remove from primary backend", exc_info=True)

    store = _read_raw()
    if grant_id in store:
        del store[grant_id]
        _write_raw(store)


async def remove_approval_grants(
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
            query = "DELETE FROM approval_grants WHERE " + " AND ".join(clauses)
            return int(
                run_coro_sync(
                    primary_execute(query, tuple(params), agent_id=config_module.AGENT_ID)  # type: ignore[arg-type]
                )
                or 0
            )
        except Exception:
            log.warning("approval_grants: failed to bulk-remove from primary backend", exc_info=True)

    store = _read_raw()
    kept: dict[str, Any] = {}
    removed = 0
    for grant_id, entry in store.items():
        if isinstance(entry, dict) and _grant_filter_matches(
            entry,
            user_id=user_id,
            agent_id=agent_id,
            session_id=session_id,
            chat_id=chat_id,
        ):
            removed += 1
            continue
        kept[grant_id] = entry
    if removed:
        _write_raw(kept)
    return removed


async def replace_approval_grants(grants: dict[str, dict[str, Any]]) -> None:
    if _primary_enabled():
        try:
            _ensure_primary_schema()
            run_coro_sync(primary_execute("DELETE FROM approval_grants", agent_id=config_module.AGENT_ID))
            for grant_id, payload in grants.items():
                if not isinstance(payload, dict):
                    continue
                created_at = float(payload.get("created_at") or time.time())
                expires_at = float(payload.get("expires_at") or (created_at + 600))
                run_coro_sync(
                    primary_execute(
                        """
                        INSERT INTO approval_grants (
                            grant_id, user_id, agent_id, session_id, chat_id, created_at, expires_at, payload_json
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            grant_id,
                            int(payload.get("user_id") or 0),
                            str(payload.get("agent_id") or ""),
                            str(payload.get("session_id") or "") or None,
                            _optional_chat_id(payload.get("chat_id")),
                            created_at,
                            expires_at,
                            _json_dumps(dict(payload, grant_id=grant_id, created_at=created_at, expires_at=expires_at)),
                        ),
                        agent_id=config_module.AGENT_ID,
                    )
                )
            return
        except Exception:
            log.warning("approval_grants: failed to replace primary backend grants", exc_info=True)

    _write_raw(grants)


async def cleanup_expired_approval_grants() -> None:
    if _primary_enabled():
        try:
            _ensure_primary_schema()
            run_coro_sync(
                primary_execute(
                    "DELETE FROM approval_grants WHERE expires_at <= ?",
                    (time.time(),),
                    agent_id=config_module.AGENT_ID,
                )
            )
            return
        except Exception:
            log.warning("approval_grants: failed to cleanup primary backend grants", exc_info=True)

    current = await load_approval_grants()
    _write_raw(current)
