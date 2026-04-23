"""Helpers for the Postgres-first primary state path."""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import threading
from datetime import datetime
from typing import Any, cast

import koda.config as config_module

# Strict ISO-8601 datetime detector. We deliberately require at least
# ``YYYY-MM-DDTHH:MM:SS`` (with optional fractional seconds and timezone)
# so free-form text never gets coerced into a datetime. Legacy callers used
# ``datetime.isoformat()`` which produces exactly this shape.
_ISO_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?"
    r"(?:[Zz]|[+-]\d{2}:?\d{2})?$"
)

_BRIDGE_LOOP: asyncio.AbstractEventLoop | None = None
_BRIDGE_THREAD: threading.Thread | None = None
_BRIDGE_LOCK = threading.Lock()
_BRIDGE_OWNER_PID: int | None = None


def _ensure_bridge_loop() -> asyncio.AbstractEventLoop:
    """Return the process-local bridge event loop, spawning it on first use.

    The bridge loop is a persistent daemon thread that owns all asyncpg pool
    lifecycles for sync-to-async bridging. Every Postgres operation routes
    through this loop so the pool's event-loop binding stays stable across
    ``asyncio.run()`` boundaries and subprocess spawns.

    PID-awareness: when the current PID differs from the bridge's owner PID
    (i.e. we are running inside a worker subprocess that inherited module
    state), the singleton is torn down and rebuilt so the child process owns
    its own pool. ``subprocess_exec`` re-imports the module in a fresh
    interpreter so this path is largely defensive, but it also guards any
    future caller that forks the supervisor.
    """
    global _BRIDGE_LOOP, _BRIDGE_THREAD, _BRIDGE_OWNER_PID

    current_pid = os.getpid()
    with _BRIDGE_LOCK:
        if (
            _BRIDGE_LOOP is not None
            and _BRIDGE_THREAD is not None
            and _BRIDGE_THREAD.is_alive()
            and current_pid == _BRIDGE_OWNER_PID
        ):
            return _BRIDGE_LOOP
        if _BRIDGE_OWNER_PID is not None and current_pid != _BRIDGE_OWNER_PID:
            # Inherited state from a parent process: the cached pool is bound
            # to the parent's event loop and cannot be used safely here.
            _BRIDGE_LOOP = None
            _BRIDGE_THREAD = None

        ready = threading.Event()

        def _runner() -> None:
            global _BRIDGE_LOOP

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            # Clear any shared Postgres backends whose pools were created on
            # transient asyncio.run() loops during bootstrap.  The bridge loop
            # will lazily create fresh pools bound to THIS persistent loop.
            try:
                from koda.knowledge.v2 import common as _k2c

                _k2c._SHARED_POSTGRES_BACKENDS.clear()
            except Exception:
                pass
            with _BRIDGE_LOCK:
                _BRIDGE_LOOP = loop
            ready.set()
            loop.run_forever()

        thread = threading.Thread(target=_runner, daemon=True, name="primary-state-bridge")
        _BRIDGE_THREAD = thread
        _BRIDGE_OWNER_PID = current_pid
        thread.start()

    ready.wait()
    if _BRIDGE_LOOP is None:  # pragma: no cover - defensive initialization guard
        raise RuntimeError("primary_state_bridge_unavailable")
    return _BRIDGE_LOOP


def postgres_primary_mode() -> bool:
    """Return whether the runtime should avoid legacy local SQLite state."""
    return config_module.STATE_BACKEND == "postgres"


def get_primary_state_backend(*, agent_id: str | None = None) -> Any | None:
    """Return the shared Postgres backend when primary state mode is active."""
    if not postgres_primary_mode():
        return None
    from koda.knowledge.config import (
        KNOWLEDGE_V2_EMBEDDING_DIMENSION,
        KNOWLEDGE_V2_POSTGRES_DSN,
        KNOWLEDGE_V2_POSTGRES_SCHEMA,
    )
    from koda.knowledge.v2.common import get_shared_postgres_backend

    backend = get_shared_postgres_backend(
        agent_id=agent_id or config_module.AGENT_ID,
        dsn=KNOWLEDGE_V2_POSTGRES_DSN,
        schema=KNOWLEDGE_V2_POSTGRES_SCHEMA,
        embedding_dimension=KNOWLEDGE_V2_EMBEDDING_DIMENSION,
    )
    return backend if backend.enabled else None


def require_primary_state_backend(*, agent_id: str | None = None, error: str) -> Any:
    """Return the primary backend or raise when postgres-primary mode is required."""
    backend = get_primary_state_backend(agent_id=agent_id)
    if backend is None and postgres_primary_mode():
        raise RuntimeError(error)
    return backend


def run_coro_sync(coro: Any) -> Any:
    """Run an async primary-backend operation from sync callers.

    Two dispatch modes:

    1. **No running loop** — sync-only callers (CLI tools, control-plane
       bootstrap) run the coroutine in a fresh ``asyncio.run`` loop. The
       shared asyncpg backend cache is cleared before and after so each
       invocation starts with a pool bound to the fresh loop. Skipping the
       clear would leave the pool pinned to the previous transient loop
       (closed by the time the next call runs) → ``InterfaceError: cannot
       perform operation: another operation is in progress``.
    2. **Running loop** — sync wrapper called from async code. Dispatch to
       the persistent bridge thread so the calling loop keeps making
       progress while Postgres work lands on a stable event loop.

    Historical note: a previous attempt always used the bridge loop. That
    cascaded cross-loop errors into downstream consumers that use
    ``backend._connection()`` directly on a different loop (the worker's
    main loop ≠ the bridge loop). The fresh-loop path below is the
    pragmatic baseline.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        _reset_shared_backends_for_transient_loop()
        try:
            return asyncio.run(coro)
        finally:
            _reset_shared_backends_for_transient_loop()
    bridge_loop = _ensure_bridge_loop()
    future = asyncio.run_coroutine_threadsafe(coro, bridge_loop)
    return future.result()


def _reset_shared_backends_for_transient_loop() -> None:
    """Evict the shared asyncpg backend cache before/after each transient
    ``asyncio.run`` loop.

    Pools are bound to the loop they were created on. A pool cached in
    module state from a previous ``asyncio.run`` invocation is pinned to a
    loop that has since been closed, so acquiring from it on the next run
    raises ``InterfaceError`` / ``ConnectionDoesNotExistError``. We drop the
    cache so the next caller rebuilds a fresh pool on the fresh loop, and
    again after completion so the just-used pool doesn't leak into
    subsequent bridge-loop callers.
    """
    with contextlib.suppress(Exception):
        from koda.knowledge.v2 import common as _k2c

        _k2c._SHARED_POSTGRES_BACKENDS.clear()


def _normalize_qmark_placeholders(query: str) -> str:
    index = 0
    chunks: list[str] = []
    for char in query:
        if char == "?":
            index += 1
            chunks.append(f"${index}")
        else:
            chunks.append(char)
    return "".join(chunks)


def _normalize_primary_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_normalize_primary_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_normalize_primary_value(item) for item in value)
    if isinstance(value, dict):
        return {str(key): _normalize_primary_value(item) for key, item in value.items()}
    return value


def _iso_string_to_datetime(value: str) -> datetime | None:
    """Parse a strict ISO-8601 datetime string, returning ``None`` on mismatch."""
    if not _ISO_TIMESTAMP_RE.match(value):
        return None
    candidate = value
    # Python's ``fromisoformat`` accepts ``+00:00`` but not the trailing ``Z``
    # form used by many JSON encoders; normalize before parsing.
    if candidate.endswith(("Z", "z")):
        candidate = candidate[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        return None


async def _install_timestamptz_str_codec(conn: Any) -> None:
    """Accept ISO-8601 strings for TIMESTAMPTZ/TIMESTAMP columns.

    Every legacy caller uses ``_now_iso()`` (returns ``str``) when inserting
    into ``created_at`` / ``last_used`` / ``updated_at`` columns. asyncpg's
    default codec refuses strings with
    ``DataError: invalid input for query argument $N: '...' (expected a
    datetime.date or datetime.datetime instance, got 'str')``.

    Rather than rewrite every INSERT across the codebase, install a
    connection-scoped type codec that accepts either ``datetime`` or a
    strict ISO-8601 string (coerced in-place) and always decodes to
    ``datetime`` on read. TEXT columns are unaffected — they keep storing
    the original string — because this codec is registered only for the
    ``timestamptz`` / ``timestamp`` Postgres types.
    """

    def _encode(value: Any) -> str:
        # Return the canonical Postgres textual representation so asyncpg's
        # text-format wire protocol accepts it without additional conversion.
        # Accept datetime, date, and ISO-8601 strings — asyncpg's default
        # codec handles both datetime/date for TIMESTAMPTZ, so we must too
        # to avoid breaking callers that pass ``datetime.date`` (e.g. cost
        # dashboard period filters).
        from datetime import date

        if isinstance(value, datetime):
            return value.isoformat(sep=" ")
        if isinstance(value, date):
            # date.isoformat() → "YYYY-MM-DD"; Postgres accepts that for
            # TIMESTAMPTZ (implicit 00:00:00 UTC).
            return value.isoformat()
        if isinstance(value, str):
            parsed = _iso_string_to_datetime(value)
            if parsed is not None:
                return parsed.isoformat(sep=" ")
            # Fall through: the string is not a recognized ISO-8601 timestamp.
            # Let Postgres's own parser attempt to interpret it (e.g. "now",
            # relative specs) and raise the usual error if it can't.
            return value
        raise TypeError(f"timestamptz column expects datetime, date, or ISO-8601 string, got {type(value).__name__}")

    def _decode(value: str) -> str:
        # Return the textual value as-is; upstream normalizers already convert
        # ISO strings when needed. We keep text format end-to-end so the
        # codec does the smallest amount of work.
        return value

    for type_name in ("timestamptz", "timestamp"):
        # Codec registration is best-effort: if the driver can't install
        # for a given type (e.g. connection already in use), fall back to
        # default behavior. Callers that still pass ISO strings will hit
        # the classic DataError — surfaced to the operator, not silent.
        with contextlib.suppress(Exception):
            await conn.set_type_codec(
                type_name,
                encoder=_encode,
                decoder=_decode,
                schema="pg_catalog",
                format="text",
            )


def _fail_missing_backend(operation: str) -> None:
    """Raise when postgres-primary mode is required but the backend is absent.

    The primitives used to return empty sentinels silently, which made write
    failures invisible — operators saw a 200 OK while nothing was persisted.
    Fail loud here so the layer above surfaces a real error.
    """
    if not postgres_primary_mode():
        return
    raise RuntimeError(
        f"primary_backend_unavailable: {operation} attempted while STATE_BACKEND=postgres "
        "but KNOWLEDGE_V2_POSTGRES_DSN is empty or the shared backend failed to initialize."
    )


async def primary_fetch_all(
    query: str,
    params: tuple[Any, ...] | list[Any] = (),
    *,
    agent_id: str | None = None,
) -> list[dict[str, Any]]:
    backend = get_primary_state_backend(agent_id=agent_id)
    if backend is None:
        _fail_missing_backend("fetch_all")
        return []
    async with backend._connection() as conn:  # noqa: SLF001 - controlled shared backend bridge
        await _install_timestamptz_str_codec(conn)
        await conn.execute(f'SET search_path TO "{backend.schema}"')
        rows = await conn.fetch(_normalize_qmark_placeholders(query), *tuple(params))
    return [_normalize_primary_value(dict(row)) for row in rows]


async def primary_fetch_one(
    query: str,
    params: tuple[Any, ...] | list[Any] = (),
    *,
    agent_id: str | None = None,
) -> dict[str, Any] | None:
    backend = get_primary_state_backend(agent_id=agent_id)
    if backend is None:
        _fail_missing_backend("fetch_one")
        return None
    async with backend._connection() as conn:  # noqa: SLF001 - controlled shared backend bridge
        await _install_timestamptz_str_codec(conn)
        await conn.execute(f'SET search_path TO "{backend.schema}"')
        row = await conn.fetchrow(_normalize_qmark_placeholders(query), *tuple(params))
    if row is None:
        return None
    return cast(dict[str, Any], _normalize_primary_value(dict(row)))


async def primary_fetch_val(
    query: str,
    params: tuple[Any, ...] | list[Any] = (),
    *,
    agent_id: str | None = None,
) -> Any:
    backend = get_primary_state_backend(agent_id=agent_id)
    if backend is None:
        _fail_missing_backend("fetch_val")
        return None
    async with backend._connection() as conn:  # noqa: SLF001 - controlled shared backend bridge
        await _install_timestamptz_str_codec(conn)
        await conn.execute(f'SET search_path TO "{backend.schema}"')
        value = await conn.fetchval(_normalize_qmark_placeholders(query), *tuple(params))
    return _normalize_primary_value(value)


async def primary_execute(
    query: str,
    params: tuple[Any, ...] | list[Any] = (),
    *,
    agent_id: str | None = None,
) -> int:
    backend = get_primary_state_backend(agent_id=agent_id)
    if backend is None:
        _fail_missing_backend("execute")
        return 0
    async with backend._connection() as conn:  # noqa: SLF001 - controlled shared backend bridge
        await _install_timestamptz_str_codec(conn)
        await conn.execute(f'SET search_path TO "{backend.schema}"')
        status = await conn.execute(_normalize_qmark_placeholders(query), *tuple(params))
    try:
        return int(str(status).rsplit(" ", 1)[-1])
    except (TypeError, ValueError):
        return 0
