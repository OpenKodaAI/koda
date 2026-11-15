"""Real-Postgres fixtures for tests marked ``@pytest.mark.postgres``.

Resolution order (cheapest first):

1. ``POSTGRES_TEST_DSN`` env var — CI workflows provision an
   ephemeral Postgres service and inject the DSN. Tests run
   immediately, no Docker needed in the runner.

2. ``testcontainers`` library + Docker daemon — local dev. The
   fixture spins ``pgvector/pgvector:pg16`` once per session and
   shuts it down at exit.

3. Otherwise — ``pytest.skip`` on every postgres-marked test. A
   contributor without Docker can still run the rest of the suite
   without surprises.

Migrations apply via the production code path
(``KnowledgeV2PostgresBackend.bootstrap``) so the fixture verifies
the same DDL we'd ship to a real deploy.

Per-test isolation: every Postgres test shares one database and one
schema (``KNOWLEDGE_V2_POSTGRES_SCHEMA``, default ``knowledge_v2``).
Most tests reset the tables they use with ``TRUNCATE`` in their own
fixtures; squad tests call ``reset_squad_runtime_tables``. Only the
smoke test uses ``db_connection``, a connection inside a transaction
that rolls back at the end. Because tests truncate shared tables, the
Postgres suite is serial-only: do not run it with parallel workers,
and give each concurrent ``pytest -m postgres`` session its own
database in ``POSTGRES_TEST_DSN``.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest


def _explicit_dsn() -> str | None:
    raw = os.environ.get("POSTGRES_TEST_DSN", "").strip()
    return raw or None


def _testcontainers_available() -> bool:
    try:
        import testcontainers.postgres  # type: ignore[import-not-found]  # noqa: F401
    except Exception:
        return False
    # Docker daemon reachable?
    try:
        import docker  # type: ignore[import-not-found]

        docker.from_env().ping()
    except Exception:
        return False
    return True


@pytest.fixture(scope="session")
def postgres_url() -> str:
    """Session-scoped DSN. Uses the env override when present;
    otherwise spins testcontainers; otherwise skips the test."""
    explicit = _explicit_dsn()
    if explicit:
        yield explicit
        return

    if not _testcontainers_available():
        pytest.skip("postgres fixture requires POSTGRES_TEST_DSN env or testcontainers + Docker")

    from testcontainers.postgres import PostgresContainer  # type: ignore[import-not-found]

    container = PostgresContainer("pgvector/pgvector:pg16", driver=None)
    container.start()
    try:
        # testcontainers' default DSN uses ``postgresql+psycopg2``;
        # asyncpg expects ``postgresql://``. Normalize.
        url = container.get_connection_url().replace("postgresql+psycopg2", "postgresql")
        yield url
    finally:
        container.stop()


_DSN_ATTR = "KNOWLEDGE_V2_POSTGRES_DSN"


def close_shared_postgres_backends() -> None:
    """Close every cached shared Postgres backend, then empty the cache.

    Sync code under test (audit events, the control-plane store) reaches
    Postgres through the persistent bridge loop in ``koda.state.primary``,
    and the shared backend it caches keeps an asyncpg pool open on that
    loop. Emptying the cache without closing the pool leaves those
    connections open for the rest of the session: one ``-m postgres`` run
    used to hold about 65 idle connections by the end, enough for two
    concurrent sessions to exhaust a default ``max_connections=100`` server
    and fail with ``TooManyConnectionsError`` (D-225). Fixtures that reset
    the shared backends call this instead of clearing the cache themselves.
    """
    from koda.knowledge.v2 import common as knowledge_common
    from koda.state import primary as primary_state

    backends = list(knowledge_common._SHARED_POSTGRES_BACKENDS.values())
    knowledge_common._SHARED_POSTGRES_BACKENDS.clear()
    bridge_loop = primary_state._active_bridge_loop()
    if bridge_loop is None:
        return
    for backend in backends:
        future = asyncio.run_coroutine_threadsafe(backend.close(), bridge_loop)
        try:
            future.result(timeout=10)
        except Exception:
            future.cancel()


def stop_primary_bridge() -> None:
    """Stop the sync->async bridge thread the runtime starts, so later tests run without it.

    Runtime code that writes Postgres from synchronous call sites starts
    ``koda.state.primary``'s bridge loop on a daemon thread and caches shared
    backends on it. Postgres tests that drive the runtime call this in their
    teardown: the shared backends are closed on the bridge loop, the loop is
    stopped and its thread joined, and the module forgets both. Safe to call
    when no bridge is running.
    """
    from koda.state import primary as primary_mod

    close_shared_postgres_backends()
    loop = primary_mod._active_bridge_loop()
    if loop is not None:
        loop.call_soon_threadsafe(loop.stop)
        thread = primary_mod._BRIDGE_THREAD
        if thread is not None:
            thread.join(timeout=10)
        with primary_mod._BRIDGE_LOCK:
            primary_mod._BRIDGE_LOOP = None
            primary_mod._BRIDGE_THREAD = None
            primary_mod._BRIDGE_OWNER_PID = None


def _koda_modules_holding_dsn() -> list[Any]:
    """Loaded koda modules that captured ``KNOWLEDGE_V2_POSTGRES_DSN`` at import."""
    return [
        module
        for name, module in list(sys.modules.items())
        if module is not None
        and (name == "koda" or name.startswith("koda."))
        and isinstance(module.__dict__.get(_DSN_ATTR), str)
    ]


def _is_postgres_test(node: Any) -> bool:
    return node.get_closest_marker("postgres") is not None


@pytest.fixture(autouse=True)
def _postgres_dsn_scope(request: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Point Koda's Postgres-backed code at the test database for the duration
    of each ``@pytest.mark.postgres`` test only.

    Koda reads ``KNOWLEDGE_V2_POSTGRES_DSN`` from the environment and from
    module constants that several modules copy at import time (e.g.
    ``koda.knowledge.config``, ``koda.knowledge.v2.common``,
    ``koda.services.audit``, ``koda.control_plane.manager``). During the test
    every loaded copy points at the test database; afterwards each copy,
    including ones first imported or reloaded during the test, gets its
    pre-test value back, so later non-postgres tests keep their file or
    in-memory backends instead of silently sharing the test database.
    """
    if not _is_postgres_test(request.node):
        yield
        return

    dsn = request.getfixturevalue("postgres_url")
    # Import (and empty) the shared backend cache before patching so the
    # cache module itself is patched rather than imported with the test DSN.
    close_shared_postgres_backends()
    import koda.knowledge.config as knowledge_config

    original_dsn = knowledge_config.KNOWLEDGE_V2_POSTGRES_DSN
    snapshot = {
        name: getattr(knowledge_config, name) for name in dir(knowledge_config) if name.startswith("KNOWLEDGE_V2_")
    }
    monkeypatch.setenv(_DSN_ATTR, dsn)
    for module in _koda_modules_holding_dsn():
        monkeypatch.setattr(module, _DSN_ATTR, dsn)
    try:
        yield
    finally:
        for name, value in snapshot.items():
            setattr(knowledge_config, name, value)
        # Modules first imported (or reloaded) during the test captured the
        # test DSN and are not covered by monkeypatch's undo.
        for module in _koda_modules_holding_dsn():
            if module.__dict__.get(_DSN_ATTR) == dsn:
                setattr(module, _DSN_ATTR, original_dsn)
        close_shared_postgres_backends()


@pytest.fixture(scope="session")
async def migrated_postgres(postgres_url: str) -> str:
    """Apply every migration once per session before any DB-touching
    test runs. Returns the same DSN; presence of this fixture in a
    test signature is the gate that triggers migration."""
    from koda.knowledge.v2.postgres_backend import KnowledgeV2PostgresBackend

    schema = os.environ.get("KNOWLEDGE_V2_POSTGRES_SCHEMA") or "knowledge_v2"
    backend = KnowledgeV2PostgresBackend(
        agent_id=None,
        dsn=postgres_url,
        schema=schema,
        embedding_dimension=1024,
    )
    ok = await backend.bootstrap()
    if not ok:
        pytest.fail(f"failed to bootstrap migrations against {postgres_url}")
    return postgres_url


# Every squad table, truncated together so foreign keys between them
# (e.g. squad_reply_obligations -> squad_threads / squad_messages) never
# block cleanup when a new referencing table is added.
# tests/test_suite_hygiene.py fails when a squad table in the migrations is
# missing here, or when a test truncates a squad table directly.
SQUAD_RUNTIME_TABLES = (
    "squad_reply_obligations",
    "squad_message_recipients",
    "squad_messages",
    "squad_tasks",
    "squad_thread_participants",
    "squad_threads",
    "squad_coordinator_state",
    "squad_coordinator_history",
    "squad_member_capabilities",
    "squad_telegram_bindings",
    "squad_artifacts",
)


async def reset_squad_runtime_tables(conn: Any, schema: str) -> None:
    """Empty every squad table in one statement. Postgres tests use this
    instead of truncating squad tables themselves."""
    tables = ", ".join(f'"{schema}"."{name}"' for name in SQUAD_RUNTIME_TABLES)
    await conn.execute(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE")


@pytest.fixture
async def db_connection(migrated_postgres: str) -> AsyncIterator[Any]:
    """Per-test asyncpg connection wrapped in a transaction that rolls
    back at the end. Only writes made through this connection are undone;
    code under test that opens its own pool is not covered."""
    import asyncpg  # type: ignore[import-not-found]

    conn = await asyncpg.connect(migrated_postgres)
    transaction = conn.transaction()
    await transaction.start()
    try:
        yield conn
    finally:
        try:
            await transaction.rollback()
        finally:
            await conn.close()


@contextlib.contextmanager
def injected_fault(table: str, event: str, *, rows_before: int = 0) -> Iterator[None]:
    """Make each ``event`` (INSERT, UPDATE or DELETE) on ``table`` fail once it holds ``rows_before`` rows.

    A row-level BEFORE trigger raises ``injected fault`` from inside
    Postgres, so the write fails however the code under test sends it. The
    trigger and its function are dropped on exit. Use it from tests that
    run on ``migrated_postgres``.
    """
    from koda.control_plane import database

    database.execute(
        f"""
        CREATE OR REPLACE FUNCTION koda_test_injected_fault() RETURNS trigger AS $$
        BEGIN
            IF (SELECT count(*) FROM {table}) >= {int(rows_before)} THEN
                RAISE EXCEPTION 'injected fault';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql
        """
    )
    database.execute(
        f"CREATE TRIGGER koda_test_injected_fault BEFORE {event} ON {table} "
        "FOR EACH ROW EXECUTE FUNCTION koda_test_injected_fault()"
    )
    try:
        yield
    finally:
        database.execute(f"DROP TRIGGER IF EXISTS koda_test_injected_fault ON {table}")
        database.execute("DROP FUNCTION IF EXISTS koda_test_injected_fault()")


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    """Auto-skip ``@pytest.mark.postgres`` tests when no DSN is
    available and testcontainers is missing — the fixture would
    skip anyway, but the marker hook gives a single canonical
    reason in the report."""
    if _explicit_dsn() or _testcontainers_available():
        return
    skip_marker = pytest.mark.skip(reason="postgres fixture unavailable (no DSN, no testcontainers/Docker)")
    for item in items:
        if _is_postgres_test(item):
            item.add_marker(skip_marker)
