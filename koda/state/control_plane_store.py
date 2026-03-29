"""Control-plane persistence store over the primary backend."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any, cast

from koda.config import STATE_BACKEND
from koda.state_primary import (
    get_primary_state_backend,
    primary_execute,
    primary_fetch_all,
    primary_fetch_one,
    primary_fetch_val,
    run_coro_sync,
)

_INSERT_OR_IGNORE_RE = re.compile(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\s+", re.IGNORECASE)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _primary_requested() -> bool:
    return STATE_BACKEND == "postgres"


def _primary_enabled() -> bool:
    return _primary_requested() and get_primary_state_backend() is not None


def _require_primary_backend() -> Any:
    if not _primary_requested():
        raise RuntimeError("control_plane_primary_mode_required")
    backend = get_primary_state_backend()
    if backend is None:
        raise RuntimeError("control_plane_primary_backend_unavailable")
    return backend


def _connect() -> Any:
    raise RuntimeError("control_plane_legacy_backend_removed")


def _normalize_primary_query(query: str) -> str:
    normalized = query.strip().rstrip(";")
    if _INSERT_OR_IGNORE_RE.match(normalized):
        normalized = _INSERT_OR_IGNORE_RE.sub("INSERT INTO ", normalized, count=1)
        if "ON CONFLICT" not in normalized.upper():
            normalized = f"{normalized} ON CONFLICT DO NOTHING"
    return normalized


def init_control_plane_db() -> None:
    backend = _require_primary_backend()
    run_coro_sync(backend.start())


def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[Any]:
    _require_primary_backend()
    return cast(list[Any], run_coro_sync(primary_fetch_all(_normalize_primary_query(query), params)))


def fetch_one(query: str, params: tuple[Any, ...] = ()) -> Any | None:
    _require_primary_backend()
    return run_coro_sync(primary_fetch_one(_normalize_primary_query(query), params))


def execute(query: str, params: tuple[Any, ...] = ()) -> int:
    _require_primary_backend()
    normalized = _normalize_primary_query(query)
    if normalized[:6].upper() == "INSERT" and "RETURNING " not in normalized.upper():
        try:
            inserted = run_coro_sync(primary_fetch_val(f"{normalized} RETURNING id", params))
            return int(inserted or 0)
        except Exception:
            return int(run_coro_sync(primary_execute(normalized, params)) or 0)
    return int(run_coro_sync(primary_execute(normalized, params)) or 0)


def execute_many(query: str, items: list[tuple[Any, ...]]) -> None:
    _require_primary_backend()
    normalized = _normalize_primary_query(query)
    for item in items:
        run_coro_sync(primary_execute(normalized, item))


def with_connection(fn: Any) -> Any:
    _require_primary_backend()

    class _PrimaryConnectionRecorder:
        def __init__(self) -> None:
            self.operations: list[tuple[str, tuple[Any, ...]]] = []

        def execute(self, query: str, params: tuple[Any, ...] = ()) -> None:
            self.operations.append((_normalize_primary_query(query), tuple(params)))

    recorder = _PrimaryConnectionRecorder()
    result = fn(recorder)
    for query, params in recorder.operations:
        run_coro_sync(primary_execute(query, params))
    return result


def json_load(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def now_iso() -> str:
    return _utc_now()
