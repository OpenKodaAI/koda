"""Lightweight JSON-file persistence for pending approval operations.

Stores pending approvals to ``{STATE_ROOT_DIR}/pending_approvals.json`` so they
survive process restarts.  asyncio.Event objects cannot be serialized, so
callers must recreate them after loading.

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

log = get_logger(__name__)


def _file_path() -> Path:
    return config_module.STATE_ROOT_DIR / "pending_approvals.json"


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


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


async def save_pending_op(
    op_id: str,
    data: dict[str, Any],
    ttl_seconds: int,
) -> None:
    """Persist a single pending operation with a TTL."""
    now = time.time()
    store = _read_raw()
    entry = dict(data)
    entry.update(
        {
            "op_id": op_id,
            "created_at": now,
            "expires_at": now + ttl_seconds,
            "op_type": data.get("op_type", "user"),
        }
    )
    store[op_id] = {
        **entry,
        "op_id": op_id,
        "user_id": data.get("user_id"),
        "chat_id": data.get("chat_id"),
        "session_id": data.get("session_id"),
        "agent_id": data.get("agent_id"),
        "description": data.get("description", ""),
    }
    _write_raw(store)


async def load_pending_ops() -> dict[str, dict[str, Any]]:
    """Load all non-expired pending ops from disk."""
    raw = _read_raw()
    now = time.time()
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
    store = _read_raw()
    kept: dict[str, Any] = {}
    removed = 0
    for op_id, entry in store.items():
        if not isinstance(entry, dict):
            kept[op_id] = entry
            continue
        if user_id is not None and int(entry.get("user_id") or 0) != user_id:
            kept[op_id] = entry
            continue
        if agent_id is not None and str(entry.get("agent_id") or "") != agent_id:
            kept[op_id] = entry
            continue
        if session_id is not None and str(entry.get("session_id") or "") != session_id:
            kept[op_id] = entry
            continue
        if chat_id is not None and int(entry.get("chat_id") or 0) != chat_id:
            kept[op_id] = entry
            continue
        removed += 1
    if removed:
        _write_raw(kept)
    return removed


async def cleanup_expired_ops() -> None:
    """Remove all expired entries from the persisted store."""
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
