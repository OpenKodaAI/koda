"""Primary-state helpers and the knowledge backend share one asyncpg pool (D-076).

The ``primary_*`` helpers used to call ``set_type_codec`` and ``SET search_path``
on every call. The codec decoded timestamps to text and stayed on the pooled
connection after release, so a later knowledge-backend query on that connection
got a string instead of a ``datetime``. Every ``set_type_codec`` call also
dropped the connection's prepared-statement cache.

The codec is now installed once per connection, when the backend opens it, and
the schema is the connection's startup ``search_path``, so callers can be mixed
on one pool and no call sets anything on the connection.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

import asyncpg
import pytest

from tests.postgres_fixtures import close_shared_postgres_backends

pytestmark = [pytest.mark.postgres]

_AGENT = "AGENT_A"
_USER_ID = 7076


@pytest.fixture
async def one_connection_backend(migrated_postgres: str) -> AsyncIterator[Any]:
    """The shared primary backend, limited to one pooled connection so every
    caller in the test runs on the same connection."""
    from koda.state.primary import get_primary_state_backend, primary_execute

    close_shared_postgres_backends()
    backend = get_primary_state_backend(agent_id=_AGENT)
    assert backend is not None
    backend._pool_min_size = 1
    backend._pool_max_size = 1
    await primary_execute("DELETE FROM query_history WHERE user_id = ?", (_USER_ID,), agent_id=_AGENT)
    try:
        yield backend
    finally:
        await primary_execute("DELETE FROM query_history WHERE user_id = ?", (_USER_ID,), agent_id=_AGENT)
        await backend.close()
        close_shared_postgres_backends()


async def _insert_history_row(timestamp: str) -> None:
    from koda.state.primary import primary_execute

    await primary_execute(
        "INSERT INTO query_history (agent_id, user_id, timestamp, query_text, response_text) VALUES (?, ?, ?, ?, ?)",
        (_AGENT, _USER_ID, timestamp, "q", "r"),
        agent_id=_AGENT,
    )


async def _knowledge_backend_timestamp(backend: Any) -> Any:
    """Read the row the way the knowledge backend does: its own connection,
    schema-qualified SQL, no primary helper in between."""
    async with backend._connection() as conn:
        return await conn.fetchval(
            f'SELECT timestamp FROM "{backend.schema}"."query_history" WHERE user_id = $1',
            _USER_ID,
        )


async def test_knowledge_backend_reads_datetimes_after_primary_calls_on_the_same_pool(
    one_connection_backend: Any,
) -> None:
    from koda.state.primary import primary_fetch_val

    backend = one_connection_backend
    # A primary-helper write (ISO string into TIMESTAMPTZ) and read run first on
    # the pool's only connection.
    await _insert_history_row("2026-04-20T12:00:00+00:00")
    primary_value = await primary_fetch_val(
        "SELECT timestamp FROM query_history WHERE user_id = ?", (_USER_ID,), agent_id=_AGENT
    )

    knowledge_value = await _knowledge_backend_timestamp(backend)

    assert knowledge_value == datetime(2026, 4, 20, 12, 0, tzinfo=UTC)
    assert knowledge_value.tzinfo is not None
    # Primary helpers still return ISO-8601 text for timestamps.
    assert primary_value == "2026-04-20T12:00:00+00:00"
    assert backend._pool.get_size() == 1


async def test_primary_calls_keep_the_prepared_statement_cache(
    one_connection_backend: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from koda.state.primary import primary_fetch_val

    await _insert_history_row("2026-04-20T12:00:00+00:00")
    # The first call opens the pooled connection and sets it up.
    await primary_fetch_val("SELECT count(*) FROM query_history WHERE user_id = ?", (_USER_ID,), agent_id=_AGENT)

    drops: list[int] = []
    original_drop = asyncpg.connection.Connection._drop_local_statement_cache

    def _counting_drop(self: Any) -> None:
        drops.append(1)
        original_drop(self)

    monkeypatch.setattr(asyncpg.connection.Connection, "_drop_local_statement_cache", _counting_drop)

    for _ in range(5):
        count = await primary_fetch_val(
            "SELECT count(*) FROM query_history WHERE user_id = ? AND timestamp >= ?",
            (_USER_ID, "2026-01-01T00:00:00"),
            agent_id=_AGENT,
        )
        assert count == 1

    assert drops == [], "a primary_* call dropped the connection's prepared-statement cache"


async def test_primary_helpers_on_a_direct_connection_get_the_same_setup(one_connection_backend: Any) -> None:
    """When the pool belongs to another event loop, ``_connection()`` hands out
    a direct connection. Unqualified table names and ISO-string timestamps must
    work there too, without a per-call ``SET search_path``."""
    from koda.state.primary import primary_fetch_one, run_coro_sync

    backend = one_connection_backend
    await _insert_history_row("2026-04-20T12:00:00+00:00")
    # Open the pool on this test's loop; the bridge loop below cannot use it.
    assert isinstance(await _knowledge_backend_timestamp(backend), datetime)

    row = run_coro_sync(
        primary_fetch_one(
            "SELECT timestamp FROM query_history WHERE user_id = ? AND timestamp <= ?",
            (_USER_ID, "2026-04-21T00:00:00"),
            agent_id=_AGENT,
        )
    )

    assert row == {"timestamp": "2026-04-20T12:00:00+00:00"}


async def test_primary_sql_resolves_names_through_the_startup_search_path(
    one_connection_backend: Any, migrated_postgres: str
) -> None:
    """Connections start with ``search_path`` set to the backend schema, so the
    primary helpers' SQL resolves names the way Postgres does: a CTE named like
    a schema table reads the CTE, a quoted name reads the schema table (not a
    same-named table in ``public``), and ``current_schema()`` is the backend
    schema. The setting is a startup parameter, so it survives the ``RESET ALL``
    asyncpg runs when the pooled connection is released between calls."""
    from koda.state.primary import primary_fetch_val

    backend = one_connection_backend
    await _insert_history_row("2026-04-20T12:00:00+00:00")
    plain = await asyncpg.connect(migrated_postgres)
    try:
        await plain.execute("CREATE TABLE public.query_history (user_id BIGINT, timestamp TIMESTAMPTZ)")
        await plain.execute(
            "INSERT INTO public.query_history VALUES ($1, now()), ($1, now()), ($1, now())",
            _USER_ID,
        )
        cte = await primary_fetch_val(
            "WITH query_history AS (SELECT ?::bigint AS user_id, 'cte' AS source) "
            "SELECT source FROM query_history WHERE user_id = ?",
            (_USER_ID, _USER_ID),
            agent_id=_AGENT,
        )
        quoted = await primary_fetch_val(
            'SELECT count(*) FROM "query_history" WHERE user_id = ?', (_USER_ID,), agent_id=_AGENT
        )
        schema = await primary_fetch_val("SELECT current_schema()", agent_id=_AGENT)
        joined = await primary_fetch_val(
            """SELECT count(*) FROM query_history h
                 JOIN audit_events a ON a.agent_id = h.agent_id
                WHERE h.user_id = ? AND a.event_type = ?""",
            (_USER_ID, "no.such.event"),
            agent_id=_AGENT,
        )
    finally:
        await plain.execute("DROP TABLE IF EXISTS public.query_history")
        await plain.close()

    assert cte == "cte"
    assert quoted == 1
    assert schema == backend.schema
    assert joined == 0
    assert backend._pool.get_size() == 1


async def test_knowledge_backend_decodes_timestamps_inside_composites_and_ranges(
    one_connection_backend: Any,
) -> None:
    """A text-format codec cannot be combined with composite or range types:
    asyncpg fails to decode them. The pool-wide codec must keep the binary
    wire format so these knowledge-backend queries keep working."""
    backend = one_connection_backend
    await _insert_history_row("2026-04-20T12:00:00+00:00")
    start = datetime(2026, 4, 20, 12, 0, tzinfo=UTC)

    async with backend._connection() as conn:
        row = await conn.fetchval(
            f'SELECT ROW(timestamp, user_id) FROM "{backend.schema}"."query_history" WHERE user_id = $1',
            _USER_ID,
        )
        span = await conn.fetchval("SELECT tstzrange($1::timestamptz, $1::timestamptz + interval '1 day')", start)
        stamps = await conn.fetchval("SELECT ARRAY[$1::timestamptz, $1::timestamptz + interval '1 hour']", start)

    assert row == (start, _USER_ID)
    assert (span.lower, span.upper) == (start, start + timedelta(days=1))
    assert stamps == [start, start + timedelta(hours=1)]


async def _cast_outcome(conn: Any, value: Any, type_name: str) -> tuple[str, Any]:
    try:
        text = await conn.fetchval(f"SELECT $1::{type_name}::text", value)
        decoded = await conn.fetchval(f"SELECT $1::{type_name}", value)
    except asyncpg.exceptions.DataError:
        return ("DataError", None)
    return (text, decoded)


async def test_codec_encodes_and_decodes_datetimes_like_asyncpgs_default_codec(
    one_connection_backend: Any, migrated_postgres: str
) -> None:
    """Knowledge-backend queries pass ``datetime`` values. On every connection
    of the shared pool they must be written and read exactly as asyncpg's
    default codec does: naive values as the process's local time, the max/min
    datetimes as +/-infinity, and an aware value refused for a TIMESTAMP."""
    backend = one_connection_backend
    values = [
        datetime(2026, 4, 20, 12, 0),
        datetime(2026, 4, 20, 12, 0, 0, 250000, tzinfo=UTC),
        datetime(2026, 4, 20, 9, 0, tzinfo=timezone(timedelta(hours=-3))),
        date(2026, 4, 20),
        datetime.max,
        datetime.min,
    ]
    plain = await asyncpg.connect(migrated_postgres)
    try:
        async with backend._connection() as conn:
            for value in values:
                for type_name in ("timestamptz", "timestamp"):
                    expected = await _cast_outcome(plain, value, type_name)
                    actual = await _cast_outcome(conn, value, type_name)
                    assert actual == expected, (value, type_name)
            infinity = await conn.fetchval("SELECT 'infinity'::timestamptz")
    finally:
        await plain.close()

    assert infinity == datetime.max


async def test_iso_strings_are_read_in_the_session_time_zone(migrated_postgres: str) -> None:
    """Legacy callers pass ISO strings to TIMESTAMPTZ parameters. The codec must
    read them the way Postgres reads timestamp text: an offset when given,
    otherwise the session TimeZone."""
    from koda.state.primary import _install_timestamptz_str_codec

    conn = await asyncpg.connect(migrated_postgres)
    try:
        await _install_timestamptz_str_codec(conn)
        await conn.execute("SET TIME ZONE 'America/Sao_Paulo'")
        checks = [
            ("2026-04-20T12:00:00", "2026-04-20 12:00:00-03"),
            ("2026-04-20 12:00:00", "2026-04-20 12:00:00-03"),
            ("2026-04-20", "2026-04-20 00:00:00-03"),
            ("2026-04-20T12:00:00Z", "2026-04-20 12:00:00+00"),
            ("2026-04-20T12:00:00+02:00", "2026-04-20 12:00:00+02"),
        ]
        for given, meant in checks:
            assert await conn.fetchval("SELECT $1::timestamptz = $2::text::timestamptz", given, meant), given
        assert await conn.fetchval("SELECT $1::timestamp::text", "2026-04-20T12:00:00+02:00") == "2026-04-20 12:00:00"
        with pytest.raises(asyncpg.exceptions.DataError):
            await conn.fetchval("SELECT $1::timestamptz", "not a timestamp")
        # Numeric-offset zones are reported in POSIX form, whose sign is
        # inverted: '-03' is reported as '<-03>+03' and '+05:30' means UTC-5:30.
        for zone, meant in (
            ("-03", "2026-04-20 12:00:00-03"),
            ("+05:30", "2026-04-20 12:00:00-05:30"),
            ("UTC+3", "2026-04-20 12:00:00-03"),
        ):
            await conn.execute(f"SET TimeZone = '{zone}'")
            assert await conn.fetchval(
                "SELECT $1::timestamptz = $2::text::timestamptz", "2026-04-20T12:00:00", meant
            ), zone
        await conn.execute("SET TIME ZONE INTERVAL '+05:30' HOUR TO MINUTE")
        assert await conn.fetchval(
            "SELECT $1::timestamptz = $2::text::timestamptz", "2026-04-20T12:00:00", "2026-04-20 12:00:00+05:30"
        )
        # A zone the codec cannot resolve is refused, not read as UTC.
        await conn.execute("SET TimeZone = 'XYZ3ABC'")
        with pytest.raises(asyncpg.exceptions.DataError):
            await conn.fetchval("SELECT $1::timestamptz", "2026-04-20T12:00:00")
        assert await conn.fetchval("SELECT $1::timestamptz", "2026-04-20T12:00:00Z") == datetime(
            2026, 4, 20, 12, tzinfo=UTC
        )
    finally:
        await conn.close()


async def test_a_failed_codec_install_discards_the_connection(
    one_connection_backend: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The codec is installed once, when a connection opens. If that fails (a
    statement timeout or cancel during type introspection), the connection must
    not stay in the pool without the codec: the failure is raised so asyncpg
    discards the connection, and the next call gets a fresh, complete one."""
    from koda.state.primary import primary_fetch_val

    backend = one_connection_backend
    await backend.close()
    original = asyncpg.connection.Connection.set_type_codec
    calls: list[str] = []

    async def _flaky_set_type_codec(self: Any, typename: str, **kwargs: Any) -> None:
        calls.append(typename)
        if len(calls) == 1:
            raise asyncpg.exceptions.QueryCanceledError("canceling statement due to statement timeout")
        await original(self, typename, **kwargs)

    monkeypatch.setattr(asyncpg.connection.Connection, "set_type_codec", _flaky_set_type_codec)

    with pytest.raises(asyncpg.exceptions.QueryCanceledError):
        await _insert_history_row("2026-04-20T12:00:00+00:00")
    await _insert_history_row("2026-04-20T12:00:00+00:00")

    count = await primary_fetch_val(
        "SELECT count(*) FROM query_history WHERE user_id = ?", (_USER_ID,), agent_id=_AGENT
    )
    assert count == 1


async def test_the_startup_search_path_keeps_the_default_search_path_after_the_schema(
    migrated_postgres: str,
) -> None:
    """A startup ``search_path`` overrides the database or role default
    (``ALTER DATABASE/ROLE ... SET search_path``), which can list the schema of
    an extension type such as ``vector`` (Supabase installs pgvector in
    ``extensions``). The backend keeps that default after its schema, so
    unqualified extension types still resolve on its connections."""
    from urllib.parse import urlsplit, urlunsplit

    from koda.knowledge.v2.postgres_backend import KnowledgeV2PostgresBackend

    role, ext = "koda_search_path_probe", "koda_search_path_ext"
    default_path = f'"$user", public, {ext}'
    admin = await asyncpg.connect(migrated_postgres)
    await admin.execute(f"DROP SCHEMA IF EXISTS {ext} CASCADE")
    await admin.execute(f"DROP ROLE IF EXISTS {role}")
    await admin.execute(f"CREATE ROLE {role} LOGIN SUPERUSER PASSWORD 'probe'")
    await admin.execute(f"ALTER ROLE {role} SET search_path = {default_path}")
    await admin.execute(f"CREATE SCHEMA {ext}")
    await admin.execute(f"CREATE DOMAIN {ext}.probe_type AS integer")
    parts = urlsplit(migrated_postgres)
    netloc = f"{role}:probe@{parts.hostname}" + (f":{parts.port}" if parts.port else "")
    schema = os.environ.get("KNOWLEDGE_V2_POSTGRES_SCHEMA") or "knowledge_v2"
    backend = KnowledgeV2PostgresBackend(
        agent_id=_AGENT, dsn=urlunsplit(parts._replace(netloc=netloc)), schema=schema, embedding_dimension=1024
    )
    try:
        async with backend._connection() as conn:
            value = await conn.fetchval("SELECT 7::probe_type")
            path = await conn.fetchval("SHOW search_path")
    finally:
        await backend.close()
        await admin.execute(f"DROP SCHEMA IF EXISTS {ext} CASCADE")
        await admin.execute(f"DROP ROLE IF EXISTS {role}")
        await admin.close()

    assert value == 7
    assert path == f'"{schema}", {default_path}'
