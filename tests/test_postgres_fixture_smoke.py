"""Smoke test for the real-Postgres fixture chain.

The ``@pytest.mark.postgres`` tests below auto-skip when no DSN is
configured and testcontainers/Docker is unavailable. CI runners that
ship a Postgres service satisfy ``POSTGRES_TEST_DSN``; dev hosts with
Docker daemon running auto-spin a pgvector container; everyone else
sees a deterministic skip without surprises.

The plain (non-marked) tests below verify the auto-skip mechanism
itself — those run on every host so a future regression to the skip
logic is caught immediately.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from tests import postgres_fixtures


def test_explicit_dsn_helper_returns_env_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_TEST_DSN", "postgresql://u:p@h/db")
    assert postgres_fixtures._explicit_dsn() == "postgresql://u:p@h/db"


def test_explicit_dsn_helper_returns_none_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POSTGRES_TEST_DSN", raising=False)
    assert postgres_fixtures._explicit_dsn() is None


def test_testcontainers_available_returns_false_when_lib_missing() -> None:
    """Force the import to fail and assert the helper degrades to
    False rather than raising."""
    import builtins

    real_import = builtins.__import__

    def _block_testcontainers(name: str, *args, **kwargs):
        if name.startswith("testcontainers"):
            raise ImportError("simulated missing dep")
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", _block_testcontainers):
        assert postgres_fixtures._testcontainers_available() is False


def test_stop_primary_bridge_stops_the_bridge_thread_and_forgets_it() -> None:
    """Postgres tests share one teardown for the sync->async bridge the runtime starts."""
    from koda.state import primary as primary_mod

    loop = primary_mod._ensure_bridge_loop()
    thread = primary_mod._BRIDGE_THREAD
    assert thread is not None and thread.is_alive()
    assert primary_mod._active_bridge_loop() is loop

    postgres_fixtures.stop_primary_bridge()

    assert not thread.is_alive()
    assert primary_mod._active_bridge_loop() is None
    assert (primary_mod._BRIDGE_LOOP, primary_mod._BRIDGE_THREAD, primary_mod._BRIDGE_OWNER_PID) == (None, None, None)
    # Idempotent: a test whose run never started the bridge tears down cleanly too.
    postgres_fixtures.stop_primary_bridge()


@pytest.mark.postgres
def test_postgres_marker_is_registered() -> None:
    """If this test runs, real Postgres is available and the
    fixture chain is wired correctly. If it doesn't, it auto-skips
    via the collection hook in postgres_fixtures.py."""
    # Marker presence alone is enough for this smoke. Real test bodies
    # that exercise SQL belong in tests that actually need it.
    assert True


@pytest.mark.postgres
def test_postgres_url_resolves_to_a_dsn(postgres_url: str) -> None:
    """When the fixture is satisfied (env DSN OR Docker+
    testcontainers), it must yield a non-empty DSN string."""
    assert isinstance(postgres_url, str)
    assert postgres_url.startswith("postgresql://")


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_db_connection_executes_simple_query(db_connection) -> None:
    """End-to-end: open a transaction, run a query, roll back. The
    next test sees a clean slate. Keep the query on pytest-asyncio's
    fixture loop; asyncpg connections cannot safely hop through
    ``asyncio.run``."""

    result = await db_connection.fetchval("SELECT 42")
    assert int(result) == 42


async def _backend_connected(dsn: str, pid: int) -> bool:
    import asyncpg  # type: ignore[import-not-found]

    conn = await asyncpg.connect(dsn)
    try:
        count = await conn.fetchval("SELECT count(*) FROM pg_stat_activity WHERE pid = $1", pid)
    finally:
        await conn.close()
    return bool(count)


async def _wait_for_disconnect(dsn: str, pid: int) -> None:
    # The server process exits shortly after the client closes the socket.
    for _ in range(100):
        if not await _backend_connected(dsn, pid):
            return
        await asyncio.sleep(0.05)


def _open_bridge_pool_connection() -> int:
    """Run a query the way sync code under test does from async code: on the
    primary-state bridge loop, through the cached shared backend's pool.
    Returns the server pid of the pooled connection that ran it."""
    from koda.state.primary import primary_fetch_val, run_coro_sync

    return int(run_coro_sync(primary_fetch_val("SELECT pg_backend_pid()")))


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_close_shared_postgres_backends_closes_bridge_pools(migrated_postgres: str) -> None:
    """Sync code under test (audit events, the control-plane store) opens a
    shared-backend pool on the primary-state bridge loop. Resetting the cache
    between tests must close that pool; dropping it leaked one connection per
    such test for the rest of the session until the server refused new
    clients (D-225)."""
    bridge_backend_pid = _open_bridge_pool_connection()

    assert await _backend_connected(migrated_postgres, bridge_backend_pid)

    postgres_fixtures.close_shared_postgres_backends()

    await _wait_for_disconnect(migrated_postgres, bridge_backend_pid)
    assert not await _backend_connected(migrated_postgres, bridge_backend_pid)


# The next two tests run in file order as a pair: the first leaves a bridge
# pool open when it ends, the second checks that the autouse
# ``_postgres_dsn_scope`` fixture closed it in between. That fixture runs
# around every Postgres test, so it is where the D-225 leak came from.
_BRIDGE_PIDS_LEFT_OPEN: list[int] = []


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_bridge_pool_left_open_when_a_postgres_test_ends(migrated_postgres: str) -> None:
    _BRIDGE_PIDS_LEFT_OPEN.clear()
    bridge_backend_pid = _open_bridge_pool_connection()

    assert await _backend_connected(migrated_postgres, bridge_backend_pid)
    _BRIDGE_PIDS_LEFT_OPEN.append(bridge_backend_pid)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_postgres_fixture_closed_the_previous_tests_bridge_pool(migrated_postgres: str) -> None:
    if not _BRIDGE_PIDS_LEFT_OPEN:
        pytest.skip("needs test_bridge_pool_left_open_when_a_postgres_test_ends to run first")
    bridge_backend_pid = _BRIDGE_PIDS_LEFT_OPEN.pop()

    await _wait_for_disconnect(migrated_postgres, bridge_backend_pid)
    assert not await _backend_connected(migrated_postgres, bridge_backend_pid), (
        "the bridge pool opened by the previous Postgres test is still connected: "
        "_postgres_dsn_scope must close the shared backends, not just drop them"
    )


def test_collection_hook_skips_postgres_when_unavailable(pytestconfig) -> None:
    """The hook in postgres_fixtures.pytest_collection_modifyitems
    must add a skip marker to every postgres-tagged test when the
    fixture cannot be satisfied. This protects contributors without
    Docker from spurious failures."""
    has_dsn = postgres_fixtures._explicit_dsn() is not None
    has_tc = postgres_fixtures._testcontainers_available()
    if has_dsn or has_tc:
        pytest.skip("Postgres fixture is available — collection hook is a no-op here.")

    class _FakeItem:
        def __init__(self, *, marked: bool) -> None:
            # A parametrize id such as ``[postgres]`` also lands in keywords;
            # only the real marker may trigger the skip.
            self.keywords = {"postgres": True}
            self._marked = marked
            self.markers: list[Any] = []

        def get_closest_marker(self, name: str) -> Any:
            return pytest.mark.postgres.mark if self._marked and name == "postgres" else None

        def add_marker(self, marker: Any) -> None:
            self.markers.append(marker)

    marked, keyword_only = _FakeItem(marked=True), _FakeItem(marked=False)
    postgres_fixtures.pytest_collection_modifyitems(pytestconfig, [marked, keyword_only])
    assert marked.markers, "expected an auto-skip marker on a postgres-marked item"
    assert not keyword_only.markers, "a 'postgres' keyword without the marker must not be skipped"


# Quiet the type checker on the loose ``Any`` import above.
from typing import Any  # noqa: E402
