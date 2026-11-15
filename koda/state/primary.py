"""Helpers for the Postgres-first primary state path."""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import functools
import os
import re
import threading
from datetime import UTC, date, datetime, timedelta, tzinfo
from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import koda.config as config_module

# Parts of a statement whose text is not SQL to rewrite: string literals
# (escape strings first, so a backslash-escaped quote does not end them),
# quoted identifiers, dollar-quoted bodies and comments.
_SQL_OPAQUE_RE = re.compile(
    r"(?<!\w)[Ee]'(?:[^'\\]|\\.|'')*'"
    r"|'(?:[^']|'')*'"
    r'|"(?:[^"]|"")*"'
    r"|\$(?P<tag>[A-Za-z_]\w*|)\$.*?\$(?P=tag)\$"
    r"|--[^\n]*"
    r"|/\*.*?\*/",
    re.DOTALL,
)
# Bare names where a statement names tables: after FROM, USING, TRUNCATE and
# TABLE a comma-separated list ("TRUNCATE a, b"; "FROM a x, b y", where an
# alias counts only when a comma follows it, so "FROM a JOIN b" still sees
# JOIN), after the other keywords one name. A name followed by "." is
# already qualified, or is a column reference such as ``tasks.id``.
_SQL_TABLE_ITEM = r"[A-Za-z_]\w*(?:\s+(?:AS\s+)?[A-Za-z_]\w*(?=\s*,))?"
_SQL_TABLE_POSITION_RE = re.compile(
    r"(?P<lead>\b(?P<keyword>FROM|USING|TRUNCATE(?:\s+TABLE)?|TABLE|JOIN|INTO|UPDATE|REFERENCES|ON)\s+"
    r"(?:(?:ONLY|IF\s+NOT\s+EXISTS|IF\s+EXISTS)\s+)?)"
    rf"(?P<names>{_SQL_TABLE_ITEM}(?:\s*,\s*{_SQL_TABLE_ITEM})*)\b(?!\s*\.)",
    re.IGNORECASE,
)
_SQL_TABLE_LIST_KEYWORDS = ("FROM", "USING", "TRUNCATE", "TABLE")
_SQL_ITEM_NAME_RE = re.compile(r"(?P<space>\s*)(?P<name>[A-Za-z_]\w*)(?P<rest>.*)", re.DOTALL)
_SQL_CREATE_TABLE_RE = re.compile(
    r"\bCREATE\s+(?:UNLOGGED\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<name>[A-Za-z_]\w*)\b(?!\s*\.)",
    re.IGNORECASE,
)

# asyncpg's ``tuple`` format for timestamps: microseconds since 2000-01-01,
# with the int64 extremes for +/-infinity, as in its default codec.
_PG_EPOCH = datetime(2000, 1, 1)
_PG_EPOCH_UTC = datetime(2000, 1, 1, tzinfo=UTC)
_PG_INFINITY = 2**63 - 1
_PG_NEGATIVE_INFINITY = -(2**63)

_BRIDGE_LOOP: asyncio.AbstractEventLoop | None = None
_BRIDGE_THREAD: threading.Thread | None = None
_BRIDGE_LOCK = threading.Lock()
_BRIDGE_OWNER_PID: int | None = None
_BRIDGE_TIMEOUT_SECONDS = float(os.environ.get("PRIMARY_STATE_BRIDGE_TIMEOUT_SECONDS", "30"))


def _active_bridge_loop() -> asyncio.AbstractEventLoop | None:
    current_pid = os.getpid()
    with _BRIDGE_LOCK:
        if (
            _BRIDGE_LOOP is not None
            and _BRIDGE_THREAD is not None
            and _BRIDGE_THREAD.is_alive()
            and current_pid == _BRIDGE_OWNER_PID
        ):
            return _BRIDGE_LOOP
    return None


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

    def _run_on_bridge(loop: asyncio.AbstractEventLoop) -> Any:
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        try:
            return future.result(timeout=_BRIDGE_TIMEOUT_SECONDS)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise TimeoutError(f"primary_state_bridge_timeout_after_{_BRIDGE_TIMEOUT_SECONDS:g}s") from exc

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        if bridge_loop := _active_bridge_loop():
            return _run_on_bridge(bridge_loop)
        _reset_shared_backends_for_transient_loop()
        try:
            return asyncio.run(coro)
        finally:
            _reset_shared_backends_for_transient_loop()
    bridge_loop = _ensure_bridge_loop()
    return _run_on_bridge(bridge_loop)


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


def _schema_qualified(query: str, schema: str, tables: set[str]) -> str:
    """Return ``query`` with each table of the backend schema schema-qualified.

    The ``primary_*`` helpers run SQL that names tables without a schema. They
    qualify it here instead of setting ``search_path`` on the connection,
    which a pooler such as PgBouncer refuses as a startup parameter (D-076).
    Only names in ``tables`` change, so columns, functions and CTEs stay as
    written. A ``CREATE TABLE`` puts its table in the schema and adds the name
    to ``tables``, for the stores that create their table on first use.
    """
    prefix = '"' + schema.replace('"', '""') + '".'

    def _qualify_item(item: str) -> str:
        parts = _SQL_ITEM_NAME_RE.match(item)
        if parts is None or parts.group("name").lower() not in tables:
            return item
        return parts.group("space") + prefix + parts.group("name") + parts.group("rest")

    def _qualify(match: re.Match[str]) -> str:
        items = match.group("names").split(",")
        if match.group("keyword").split()[0].upper() in _SQL_TABLE_LIST_KEYWORDS:
            items = [_qualify_item(item) for item in items]
        else:
            items[0] = _qualify_item(items[0])
        return match.group("lead") + ",".join(items)

    chunks: list[str] = []
    position = 0
    for opaque in _SQL_OPAQUE_RE.finditer(query):
        chunks.append(query[position : opaque.start()])
        chunks.append(opaque.group(0))
        position = opaque.end()
    chunks.append(query[position:])
    for index in range(0, len(chunks), 2):
        for created in _SQL_CREATE_TABLE_RE.finditer(chunks[index]):
            tables.add(created.group("name").lower())
        chunks[index] = _SQL_TABLE_POSITION_RE.sub(_qualify, chunks[index])
    return "".join(chunks)


def _primary_sql(backend: Any, query: str) -> str:
    """The statement a ``primary_*`` helper sends: schema-qualified, ``$n`` placeholders."""
    schema = getattr(backend, "schema", None)
    tables = getattr(backend, "table_names", None)
    if isinstance(schema, str) and isinstance(tables, set):
        query = _schema_qualified(query, schema, tables)
    return _normalize_qmark_placeholders(query)


def _parse_timestamp_text(value: str) -> datetime:
    """Parse the ISO-8601 text legacy callers pass for timestamp parameters.

    Accepts the shapes Postgres read when the value was sent as text
    (``T`` or space separator, ``Z`` or numeric offsets, date only) and
    ``infinity`` / ``-infinity``. Free-form text raises ``TypeError``, which
    asyncpg reports as ``DataError``.
    """
    text = value.strip()
    if text.lower() == "infinity":
        return datetime.max
    if text.lower() == "-infinity":
        return datetime.min
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        raise TypeError(f"timestamp parameter expects ISO-8601 text, got {value!r}") from None


@functools.lru_cache(maxsize=32)
def _time_zone(name: str) -> tzinfo:
    try:
        return ZoneInfo(name)
    except (ValueError, ZoneInfoNotFoundError):
        # A POSIX-style zone such as "<-03>+03" has no IANA entry.
        return UTC


def _session_time_zone(conn: Any) -> tzinfo:
    get_settings = getattr(conn, "get_settings", None)
    name = getattr(get_settings(), "TimeZone", None) if callable(get_settings) else None
    return _time_zone(str(name or "UTC"))


def _pg_microseconds(delta: timedelta) -> int:
    return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds


async def _install_timestamptz_str_codec(conn: Any) -> None:
    """Accept ISO-8601 strings for TIMESTAMPTZ/TIMESTAMP columns.

    Every legacy caller uses ``_now_iso()`` (returns ``str``) when inserting
    into ``created_at`` / ``last_used`` / ``updated_at`` columns. asyncpg's
    default codec refuses strings with
    ``DataError: invalid input for query argument $N: '...' (expected a
    datetime.date or datetime.datetime instance, got 'str')``.

    Rather than rewrite every INSERT across the codebase, install a
    connection-scoped type codec that also accepts ISO-8601 strings and
    always decodes to ``datetime`` on read. TEXT columns are unaffected —
    they keep storing the original string — because this codec is
    registered only for the ``timestamptz`` / ``timestamp`` Postgres types.

    ``datetime`` and ``date`` values are encoded, and every value decoded,
    exactly as asyncpg's default codec does: a naive value is the process's
    local time, the max/min datetimes are +/-infinity, and a TIMESTAMP
    refuses an aware value. Strings are read the way Postgres reads
    timestamp text: with their offset, or else in the session TimeZone.
    The ``tuple`` format keeps the binary wire format, so composites, ranges
    and arrays that contain timestamps still decode.

    The shared backend installs it once per connection, when the connection
    opens (``KnowledgeV2PostgresBackend._init_connection``): the pool is
    shared with knowledge-backend queries, which need ``datetime`` values,
    and asyncpg drops the statement cache whenever a codec is set (D-076).
    A failure is raised, so asyncpg discards the connection rather than
    pooling one without the codec.
    """

    def _encode_timestamptz(value: Any) -> tuple[int]:
        if isinstance(value, str):
            value = _parse_timestamp_text(value)
            if value.tzinfo is None and value not in (datetime.max, datetime.min):
                value = value.replace(tzinfo=_session_time_zone(conn))
        elif not isinstance(value, datetime):
            if not isinstance(value, date):
                raise TypeError(f"timestamptz expects datetime, date or ISO-8601 text, got {type(value).__name__}")
            value = datetime(value.year, value.month, value.day)
        # A naive value never equals an aware one, so only naive max/min match.
        if value == datetime.max:
            return (_PG_INFINITY,)
        if value == datetime.min:
            return (_PG_NEGATIVE_INFINITY,)
        return (_pg_microseconds(value.astimezone(UTC) - _PG_EPOCH_UTC),)

    def _encode_timestamp(value: Any) -> tuple[int]:
        if isinstance(value, str):
            # Postgres ignores the offset in TIMESTAMP text.
            value = _parse_timestamp_text(value).replace(tzinfo=None)
        elif not isinstance(value, datetime):
            if not isinstance(value, date):
                raise TypeError(f"timestamp expects datetime, date or ISO-8601 text, got {type(value).__name__}")
            value = datetime(value.year, value.month, value.day)
        elif value.tzinfo is not None:
            raise TypeError("timestamp without time zone expects a naive datetime, got an aware one")
        if value == datetime.max:
            return (_PG_INFINITY,)
        if value == datetime.min:
            return (_PG_NEGATIVE_INFINITY,)
        return (_pg_microseconds(value - _PG_EPOCH),)

    def _decoder(epoch: datetime) -> Any:
        def _decode(value: tuple[int]) -> datetime:
            microseconds = value[0]
            if microseconds == _PG_INFINITY:
                return datetime.max
            if microseconds == _PG_NEGATIVE_INFINITY:
                return datetime.min
            return epoch + timedelta(microseconds=microseconds)

        return _decode

    await conn.set_type_codec(
        "timestamptz",
        encoder=_encode_timestamptz,
        decoder=_decoder(_PG_EPOCH_UTC),
        schema="pg_catalog",
        format="tuple",
    )
    await conn.set_type_codec(
        "timestamp",
        encoder=_encode_timestamp,
        decoder=_decoder(_PG_EPOCH),
        schema="pg_catalog",
        format="tuple",
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
        rows = await conn.fetch(_primary_sql(backend, query), *tuple(params))
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
        row = await conn.fetchrow(_primary_sql(backend, query), *tuple(params))
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
        value = await conn.fetchval(_primary_sql(backend, query), *tuple(params))
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
        status = await conn.execute(_primary_sql(backend, query), *tuple(params))
    try:
        return int(str(status).rsplit(" ", 1)[-1])
    except (TypeError, ValueError):
        return 0
