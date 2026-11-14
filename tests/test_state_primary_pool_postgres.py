"""Primary-state helpers and the knowledge backend share one asyncpg pool (D-076).

The ``primary_*`` helpers used to call ``set_type_codec`` and ``SET search_path``
on every call. The codec decoded timestamps to text and stayed on the pooled
connection after release, so a later knowledge-backend query on that connection
got a string instead of a ``datetime``. Every ``set_type_codec`` call also
dropped the connection's prepared-statement cache.

The codec and the schema are now set once per connection, when the backend
opens it, so callers can be mixed on one pool.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
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
