"""Control-plane persistence store over the primary backend."""

from __future__ import annotations

import json
import math
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast

from koda.config import STATE_BACKEND
from koda.state.primary import (
    _normalize_qmark_placeholders,
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
    # start() applies the schema migrations. The control plane calls this from
    # its running event loop, so through the bridge, whose time limit would
    # cancel an index build on a large table at every boot (D-285).
    run_coro_sync(backend.start(), timeout=math.inf)


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
        except Exception:
            # RETURNING id isn't supported here (no `id` column, or some other
            # driver error). Fall back to a bare INSERT *only in that case* —
            # never after the RETURNING path already committed the row, which
            # would produce a duplicate-key on retry.
            return int(run_coro_sync(primary_execute(normalized, params)) or 0)
        # Callers historically expect an integer rowcount. Numeric primary
        # keys return as ints (legacy callers relied on this); TEXT primary
        # keys (e.g. "boot_<hex>", "usr_<hex>") return strings. In the TEXT
        # case we still want to report "one row affected" (==1) rather than 0,
        # since the INSERT did succeed — a 0 return would make idempotent
        # UPSERT paths re-fire the INSERT and produce a duplicate-key error.
        if inserted is None:
            return 0
        try:
            return int(inserted)
        except (TypeError, ValueError):
            return 1
    return int(run_coro_sync(primary_execute(normalized, params)) or 0)


def execute_many(query: str, items: list[tuple[Any, ...]]) -> None:
    _require_primary_backend()
    normalized = _normalize_primary_query(query)
    for item in items:
        run_coro_sync(primary_execute(normalized, item))


class WriteConflictError(RuntimeError):
    """A write recorded with ``require_row=True`` matched no row, so its ``with_connection`` applied nothing."""


class Transaction:
    """The statements of one open Postgres transaction, all on one connection."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    async def execute(self, query: str, params: tuple[Any, ...] = ()) -> int:
        """Run one statement and return the number of rows it affected."""
        status = await self._conn.execute(
            _normalize_qmark_placeholders(_normalize_primary_query(query)), *tuple(params)
        )
        try:
            return int(str(status).rsplit(" ", 1)[-1])
        except (TypeError, ValueError):
            return 0


@asynccontextmanager
async def transaction() -> AsyncIterator[Transaction]:
    """Open a transaction: its statements commit together when the block ends, or none do if it raises."""
    backend = _require_primary_backend()
    async with backend._connection() as conn, conn.transaction():  # noqa: SLF001 - controlled shared backend bridge
        yield Transaction(conn)


async def _apply_in_transaction(operations: list[tuple[str, tuple[Any, ...], bool]]) -> None:
    async with transaction() as tx:
        for query, params, require_row in operations:
            if await tx.execute(query, params) == 0 and require_row:
                raise WriteConflictError(query)


def with_connection(fn: Any) -> Any:
    """Call ``fn`` with a recorder, then apply the statements it recorded in one transaction.

    ``fn`` only records writes: they run after it returns, so a read inside
    ``fn`` does not see them. If any statement fails, none of them is applied.
    A statement recorded with ``require_row=True`` fails when it affects no
    row (``WriteConflictError``): a conditional ``UPDATE ... WHERE`` that
    another transaction got to first rolls back the whole set.
    """
    _require_primary_backend()

    class _PrimaryConnectionRecorder:
        def __init__(self) -> None:
            self.operations: list[tuple[str, tuple[Any, ...], bool]] = []

        def execute(self, query: str, params: tuple[Any, ...] = (), *, require_row: bool = False) -> None:
            self.operations.append((_normalize_primary_query(query), tuple(params), require_row))

    recorder = _PrimaryConnectionRecorder()
    result = fn(recorder)
    if recorder.operations:
        run_coro_sync(_apply_in_transaction(recorder.operations))
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
