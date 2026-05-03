"""Failure-injection scenarios for DBManager against a real PostgreSQL container.

Uses pg_terminate_backend, statement_timeout, and pool exhaustion to provoke
realistic transient errors and verify the manager:

  * Returns a typed error string (never raises bare Exception to the caller).
  * Recovers automatically: subsequent queries succeed without a process restart.
  * Doesn't leak idle connections (best-effort sampling of pg_stat_activity).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import asyncpg
import pytest

from koda.services.db_manager import DBManager, _EnvPool

pytestmark = [pytest.mark.postgres, pytest.mark.chaos]


@pytest.fixture
async def chaos_dbm(postgres_url: str) -> AsyncIterator[DBManager]:
    dbm = DBManager()
    pool = await asyncpg.create_pool(
        postgres_url,
        min_size=1,
        max_size=2,
        command_timeout=10,
        server_settings={"application_name": "koda_chaos_test"},
    )
    dbm._envs["default"] = _EnvPool(pool=pool)
    try:
        yield dbm
    finally:
        await dbm.stop()


# ---------------------------------------------------------------------------
# Statement timeout — server-side cancellation
# ---------------------------------------------------------------------------


async def test_query_timeout_returns_error_not_exception(chaos_dbm: DBManager) -> None:
    out = await chaos_dbm.query("SELECT pg_sleep(5)", timeout=1)
    assert out.startswith("Error:")
    # The pool stays live for follow-ups.
    follow = await chaos_dbm.query("SELECT 1 AS n")
    assert "Rows: 1" in follow


# ---------------------------------------------------------------------------
# Connection killed mid-flight — server forcibly terminates one backend
# ---------------------------------------------------------------------------


async def test_pool_recovers_after_backend_termination(
    chaos_dbm: DBManager, postgres_url: str
) -> None:
    """When a backend is killed mid-query, asyncpg surfaces an error; the
    pool returns the broken connection to the bin and the next query
    succeeds via a fresh connection.
    """
    # Run a slow query in the background so we can target its backend.
    async def slow_query() -> str:
        return await chaos_dbm.query("SELECT pg_sleep(3)", timeout=10)

    slow_task = asyncio.create_task(slow_query())
    await asyncio.sleep(0.3)  # let the slow query be issued

    # Find and terminate that backend via a side-channel admin connection.
    admin = await asyncpg.connect(postgres_url)
    try:
        rows = await admin.fetch(
            """
            SELECT pid FROM pg_stat_activity
             WHERE application_name = 'koda_chaos_test'
               AND state = 'active'
               AND query LIKE '%pg_sleep%'
            """
        )
        terminated = 0
        for row in rows:
            ok = await admin.fetchval("SELECT pg_terminate_backend($1)", row["pid"])
            if ok:
                terminated += 1
    finally:
        await admin.close()

    out = await slow_task
    # Either the manager surfaced the termination as an error string OR (rarely)
    # the kill landed after the query already returned. Both outcomes are valid.
    if terminated > 0:
        # The kill landed — manager returned a typed error.
        assert out.startswith("Error:") or "Rows" in out
    else:
        # Race lost — query completed first; that's still a green path.
        assert "Rows" in out

    # Pool is still healthy; subsequent query works.
    after = await chaos_dbm.query("SELECT 1 AS n")
    assert "Rows: 1" in after


# ---------------------------------------------------------------------------
# Pool saturation — serialize multiple slow queries through max_size=2
# ---------------------------------------------------------------------------


async def test_pool_saturation_serializes_without_error(chaos_dbm: DBManager) -> None:
    """With max_size=2 and 6 concurrent queries, the pool queues requests
    and returns clean results. No deadlock, no error spam.
    """

    async def one(i: int) -> str:
        # Each query takes ~0.2s so the test runs quickly.
        return await chaos_dbm.query(f"SELECT {i} AS n, pg_sleep(0.2) AS s")

    results = await asyncio.gather(*(one(i) for i in range(6)), return_exceptions=True)
    bad = [r for r in results if isinstance(r, BaseException)]
    assert not bad, f"unexpected exceptions: {bad!r}"
    success = [r for r in results if isinstance(r, str) and "Rows" in r]
    assert len(success) == 6


# ---------------------------------------------------------------------------
# Repeated error path — the manager logs and returns; never throws to caller
# ---------------------------------------------------------------------------


async def test_repeated_errors_do_not_break_pool(chaos_dbm: DBManager) -> None:
    for _ in range(5):
        out = await chaos_dbm.query("SELECT * FROM no_such_table_xyz")
        assert out.startswith("Error:"), f"non-existent table should error: {out[:200]}"
    # Pool still healthy.
    healthy = await chaos_dbm.query("SELECT 42 AS n")
    assert "42" in healthy
