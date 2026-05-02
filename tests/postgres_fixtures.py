"""Phase B.1 — real-Postgres fixtures for tests marked ``@pytest.mark.postgres``.

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
        return explicit

    if not _testcontainers_available():
        pytest.skip("postgres fixture requires POSTGRES_TEST_DSN env or testcontainers + Docker")

    from testcontainers.postgres import PostgresContainer  # type: ignore[import-not-found]

    container = PostgresContainer("pgvector/pgvector:pg16", driver=None)
    container.start()
    try:
        # testcontainers' default DSN uses ``postgresql+psycopg2``;
        # asyncpg expects ``postgresql://``. Normalize.
        url = container.get_connection_url().replace("postgresql+psycopg2", "postgresql")
        os.environ["KNOWLEDGE_V2_POSTGRES_DSN"] = url
        yield url
    finally:
        container.stop()


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
        if "postgres" in item.keywords:
            item.add_marker(skip_marker)
