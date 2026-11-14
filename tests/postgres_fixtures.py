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

Per-test isolation: ``db_transaction`` opens a transaction at test
start and rolls back at end so successive tests see a clean state
without paying the full migration cost.
"""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator
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


def _clear_shared_postgres_backends() -> None:
    from koda.knowledge.v2 import common as knowledge_common

    knowledge_common._SHARED_POSTGRES_BACKENDS.clear()


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
    _clear_shared_postgres_backends()
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
        _clear_shared_postgres_backends()


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


# Squad runtime tables, truncated together so foreign keys between them
# (e.g. squad_reply_obligations -> squad_threads / squad_messages) never
# block cleanup when a new referencing table is added.
SQUAD_RUNTIME_TABLES = (
    "squad_reply_obligations",
    "squad_message_recipients",
    "squad_messages",
    "squad_tasks",
    "squad_thread_participants",
    "squad_threads",
    "squad_coordinator_state",
    "squad_coordinator_history",
)


async def reset_squad_runtime_tables(conn: Any, schema: str) -> None:
    """Empty every squad runtime table in one statement."""
    tables = ", ".join(f'"{schema}"."{name}"' for name in SQUAD_RUNTIME_TABLES)
    await conn.execute(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE")


@pytest.fixture
async def db_connection(migrated_postgres: str) -> AsyncIterator[Any]:
    """Per-test asyncpg connection wrapped in a transaction that
    rolls back at end. Successive tests see a clean state without
    re-running migrations."""
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
