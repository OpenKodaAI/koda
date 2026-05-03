"""End-to-end DBManager tests against a real PostgreSQL container.

These tests build a DBManager pointing at the testcontainers-managed pgvector/pg16
instance from tests.postgres_fixtures.postgres_url, then exercise the read-only
guarantees, formatting, timeouts, pool behavior, multi-env routing, and
isolation properties against an actual server.

The tests intentionally do not reuse the migrated_postgres fixture — they own
their own asyncpg pool inside DBManager and only need a vanilla connection to
seed/cleanup helper schemas.
"""

from __future__ import annotations

import asyncio
import os
import re
from collections.abc import AsyncIterator

import asyncpg
import pytest

from koda.config import PostgresEnvConfig
from koda.services.db_manager import DBManager, _EnvPool

pytestmark = [pytest.mark.postgres]


# ---------------------------------------------------------------------------
# Test schema lifecycle
# ---------------------------------------------------------------------------

_EVENTS_TABLE = "dbmgr_events"
_EMPTY_TABLE = "dbmgr_empty"


@pytest.fixture(scope="session")
async def seeded_postgres_url(postgres_url: str) -> str:
    """Materialize deterministic test tables in the `public` schema.

    DBManager.get_schema() queries information_schema.tables WHERE table_schema =
    'public', so the integration suite uses prefixed table names in public to
    keep get_schema() tests honest. Existing schema is preserved (other tests
    may share the container).
    """
    conn = await asyncpg.connect(postgres_url)
    try:
        await conn.execute(f"DROP TABLE IF EXISTS public.{_EVENTS_TABLE} CASCADE")
        await conn.execute(f"DROP TABLE IF EXISTS public.{_EMPTY_TABLE} CASCADE")
        await conn.execute(
            f"""
            CREATE TABLE public.{_EVENTS_TABLE} (
                id BIGSERIAL PRIMARY KEY,
                kind TEXT NOT NULL,
                payload JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        # Seed exactly 250 rows so pagination tests are deterministic.
        await conn.executemany(
            f"INSERT INTO public.{_EVENTS_TABLE} (kind, payload) VALUES ($1, $2::jsonb)",
            [(f"kind-{i % 5}", '{"i": ' + str(i) + "}") for i in range(250)],
        )
        await conn.execute(f"CREATE INDEX ON public.{_EVENTS_TABLE} (kind)")
        await conn.execute(
            f"""
            CREATE TABLE public.{_EMPTY_TABLE} (
                id BIGSERIAL PRIMARY KEY,
                note TEXT
            )
            """
        )
    finally:
        await conn.close()
    return postgres_url


@pytest.fixture
async def dbm_real(seeded_postgres_url: str) -> AsyncIterator[DBManager]:
    """A DBManager with a single 'default' env pointing at the test container."""
    dbm = DBManager()
    pool = await asyncpg.create_pool(
        seeded_postgres_url,
        min_size=1,
        max_size=4,
        command_timeout=10,
    )
    dbm._envs["default"] = _EnvPool(pool=pool)
    try:
        yield dbm
    finally:
        await dbm.stop()


def _make_pg_env_config(**overrides: object) -> PostgresEnvConfig:
    """Build a fully-defaulted PostgresEnvConfig for SSL/SSH unit tests."""
    base: dict[str, object] = {
        "url": "postgresql://x@y/z",
        "ssl_mode": "disable",
        "ssl_ca_cert": "",
        "ssl_client_cert": "",
        "ssl_client_key": "",
        "ssh_enabled": False,
        "ssh_host": "",
        "ssh_port": 22,
        "ssh_user": "",
        "ssh_key_file": "",
        "ssh_password": "",
    }
    base.update(overrides)
    return PostgresEnvConfig(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Smoke / availability
# ---------------------------------------------------------------------------


async def test_pool_is_available(dbm_real: DBManager) -> None:
    assert dbm_real.is_available is True
    assert dbm_real.available_envs == ["default"]
    assert dbm_real.is_env_available("default") is True


async def test_simple_select_returns_formatted_table(dbm_real: DBManager) -> None:
    out = await dbm_real.query("SELECT 1 AS n, 'hi' AS s")
    assert "n" in out
    assert "hi" in out
    assert "Rows: 1" in out


async def test_select_real_table_with_count(dbm_real: DBManager) -> None:
    out = await dbm_real.query(f"SELECT count(*)::int AS total FROM public.{_EVENTS_TABLE}")
    assert "250" in out
    assert "Rows: 1" in out


async def test_select_with_where_index(dbm_real: DBManager) -> None:
    out = await dbm_real.query(
        f"SELECT count(*)::int AS c FROM public.{_EVENTS_TABLE} WHERE kind = 'kind-2'"
    )
    # 50 rows per kind (250 / 5)
    assert "50" in out


async def test_explain_returns_plan(dbm_real: DBManager) -> None:
    out = await dbm_real.explain(
        f"SELECT * FROM public.{_EVENTS_TABLE} WHERE kind = 'kind-1' LIMIT 10"
    )
    assert "Index Scan" in out or "Bitmap Index Scan" in out or "Seq Scan" in out
    assert _EVENTS_TABLE in out


async def test_get_schema_lists_tables(dbm_real: DBManager) -> None:
    out = await dbm_real.get_schema()
    assert _EVENTS_TABLE in out
    assert _EMPTY_TABLE in out


async def test_get_schema_columns_for_table(dbm_real: DBManager) -> None:
    out = await dbm_real.get_schema(_EVENTS_TABLE)
    assert "id" in out
    assert "kind" in out
    assert "payload" in out


# ---------------------------------------------------------------------------
# Empty result formatting
# ---------------------------------------------------------------------------


async def test_empty_result_says_no_results(dbm_real: DBManager) -> None:
    out = await dbm_real.query(f"SELECT * FROM public.{_EMPTY_TABLE}")
    assert "No results." in out
    assert "Rows: 0" in out


# ---------------------------------------------------------------------------
# Truncation at max_rows
# ---------------------------------------------------------------------------


async def test_max_rows_truncation(dbm_real: DBManager) -> None:
    out = await dbm_real.query(
        f"SELECT id, kind FROM public.{_EVENTS_TABLE} ORDER BY id",
        max_rows=10,
    )
    # Truncation footer mentions the additional rows.
    m = re.search(r"(\d+)\s+more rows not shown", out)
    assert m is not None, f"expected truncation footer, got: {out[:300]}"
    assert int(m.group(1)) == 240


async def test_exactly_max_rows_no_truncation(dbm_real: DBManager) -> None:
    out = await dbm_real.query(
        f"SELECT id FROM public.{_EVENTS_TABLE} ORDER BY id LIMIT 10",
        max_rows=10,
    )
    assert "more rows not shown" not in out
    assert "Rows: 10" in out


# ---------------------------------------------------------------------------
# Read-only enforcement against a real DB
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        f"INSERT INTO public.{_EVENTS_TABLE} (kind, payload) VALUES ('x', '{{}}'::jsonb)",
        f"UPDATE public.{_EVENTS_TABLE} SET kind = 'x'",
        f"DELETE FROM public.{_EVENTS_TABLE}",
        f"DROP TABLE public.{_EVENTS_TABLE}",
        f"TRUNCATE public.{_EVENTS_TABLE}",
        f"ALTER TABLE public.{_EVENTS_TABLE} ADD COLUMN foo TEXT",
    ],
)
async def test_write_statements_blocked_against_real_db(dbm_real: DBManager, sql: str) -> None:
    out = await dbm_real.query(sql)
    assert out.startswith("Error:"), f"write should be blocked, got: {out[:200]}"

    # Verify the row count is still 250 — the validator must reject before execution.
    verify = await dbm_real.query(f"SELECT count(*)::int AS c FROM public.{_EVENTS_TABLE}")
    assert "250" in verify


async def test_writable_cte_blocked_against_real_db(dbm_real: DBManager) -> None:
    out = await dbm_real.query(
        f"WITH d AS (DELETE FROM public.{_EVENTS_TABLE} RETURNING *) SELECT * FROM d"
    )
    assert out.startswith("Error:")
    verify = await dbm_real.query(f"SELECT count(*)::int AS c FROM public.{_EVENTS_TABLE}")
    assert "250" in verify


# ---------------------------------------------------------------------------
# Statement-level timeout
# ---------------------------------------------------------------------------


async def test_query_timeout_short_circuits(dbm_real: DBManager) -> None:
    # pg_sleep(2); short timeout = 0.5s should produce an error string,
    # not hang forever and not mutate the pool's health.
    out = await dbm_real.query("SELECT pg_sleep(2)", timeout=1)
    assert out.startswith("Error:"), f"expected timeout error, got: {out[:200]}"

    # Pool stays usable after the timeout.
    follow_up = await dbm_real.query("SELECT 1 AS n")
    assert "Rows: 1" in follow_up


# ---------------------------------------------------------------------------
# Concurrency / pool behavior
# ---------------------------------------------------------------------------


async def test_concurrent_queries_share_pool(dbm_real: DBManager) -> None:
    async def one(i: int) -> str:
        return await dbm_real.query(f"SELECT {i} AS n, 'k-{i}' AS s")

    results = await asyncio.gather(*(one(i) for i in range(16)))
    assert all("Rows: 1" in r for r in results)


async def test_pool_recovery_after_error(dbm_real: DBManager) -> None:
    # Force an error via timeout, then verify subsequent queries still work.
    bad = await dbm_real.query("SELECT pg_sleep(5)", timeout=1)
    assert bad.startswith("Error:")
    good = await dbm_real.query("SELECT 1 AS n")
    assert "Rows: 1" in good


# ---------------------------------------------------------------------------
# Multi-env routing — set up a 2nd env on the same physical DB but separate pool
# ---------------------------------------------------------------------------


async def test_multi_env_explicit_routing(seeded_postgres_url: str) -> None:
    dbm = DBManager()
    dev_pool = await asyncpg.create_pool(
        seeded_postgres_url, min_size=1, max_size=2
    )
    prod_pool = await asyncpg.create_pool(
        seeded_postgres_url, min_size=1, max_size=2
    )
    dbm._envs["dev"] = _EnvPool(pool=dev_pool)
    dbm._envs["prod"] = _EnvPool(pool=prod_pool)
    try:
        assert sorted(dbm.available_envs) == ["dev", "prod"]

        # Default routing in multi-env hits "prod".
        out_default = await dbm.query("SELECT current_database() AS db")
        assert "[prod]" in out_default

        # Explicit env="dev" hits dev pool.
        out_dev = await dbm.query("SELECT current_database() AS db", env="dev")
        assert "[dev]" in out_dev

        # Unknown env returns an error string, not an exception.
        out_err = await dbm.query("SELECT 1", env="staging")
        assert out_err.startswith("Error:")
        assert "Unknown env" in out_err
    finally:
        await dbm.stop()


# ---------------------------------------------------------------------------
# Coverage: PostgresEnvConfig SSL + DSN building paths
# ---------------------------------------------------------------------------


def test_ssl_context_disable_returns_none() -> None:
    cfg = _make_pg_env_config(ssl_mode="disable")
    assert DBManager._build_ssl_context(cfg) is None


def test_ssl_context_invalid_mode_raises() -> None:
    cfg = _make_pg_env_config(ssl_mode="oops")
    with pytest.raises(ValueError):
        DBManager._build_ssl_context(cfg)


@pytest.mark.parametrize("mode", ["require", "verify-ca", "verify-full"])
def test_ssl_context_build_modes(mode: str) -> None:
    cfg = _make_pg_env_config(ssl_mode=mode)
    ctx = DBManager._build_ssl_context(cfg)
    assert ctx is not None


# ---------------------------------------------------------------------------
# Smoke: pg_stat_activity baseline returns to <= baseline + 1 after teardown
# ---------------------------------------------------------------------------


async def test_pg_stat_activity_baseline(seeded_postgres_url: str) -> None:
    """Sessions opened by the suite should not leak into pg_stat_activity."""
    if os.environ.get("CI"):
        pytest.skip("pg_stat_activity sampling can be noisy in CI")

    base_conn = await asyncpg.connect(seeded_postgres_url)
    try:
        baseline = await base_conn.fetchval(
            "SELECT count(*) FROM pg_stat_activity WHERE state = 'idle' AND application_name <> ''"
        )
    finally:
        await base_conn.close()

    dbm = DBManager()
    pool = await asyncpg.create_pool(seeded_postgres_url, min_size=1, max_size=2)
    dbm._envs["default"] = _EnvPool(pool=pool)
    try:
        await dbm.query("SELECT 1")
    finally:
        await dbm.stop()

    final_conn = await asyncpg.connect(seeded_postgres_url)
    try:
        after = await final_conn.fetchval(
            "SELECT count(*) FROM pg_stat_activity WHERE state = 'idle' AND application_name <> ''"
        )
    finally:
        await final_conn.close()

    assert after <= (baseline or 0) + 2, f"pg_stat_activity grew by more than 2: {baseline} -> {after}"
