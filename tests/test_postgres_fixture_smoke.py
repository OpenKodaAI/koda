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


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_close_shared_postgres_backends_closes_bridge_pools(migrated_postgres: str) -> None:
    """Sync code under test (audit events, the control-plane store) opens a
    shared-backend pool on the primary-state bridge loop. Resetting the cache
    between tests must close that pool; dropping it leaked one connection per
    such test for the rest of the session until the server refused new
    clients (D-225)."""
    import asyncpg  # type: ignore[import-not-found]

    from koda.state.primary import primary_fetch_val, run_coro_sync

    bridge_backend_pid = run_coro_sync(primary_fetch_val("SELECT pg_backend_pid()"))

    async def _bridge_connection_open() -> bool:
        conn = await asyncpg.connect(migrated_postgres)
        try:
            count = await conn.fetchval("SELECT count(*) FROM pg_stat_activity WHERE pid = $1", bridge_backend_pid)
        finally:
            await conn.close()
        return bool(count)

    assert await _bridge_connection_open()

    postgres_fixtures.close_shared_postgres_backends()

    # The server process exits shortly after the client closes the socket.
    for _ in range(100):
        if not await _bridge_connection_open():
            break
        await asyncio.sleep(0.05)
    assert not await _bridge_connection_open()


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
