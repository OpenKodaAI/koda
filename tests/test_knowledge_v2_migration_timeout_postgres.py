"""Bootstrap migrations are not cut off by the query timeout (D-285).

An index build on a large table can take longer than any query should, so a
migration step longer than ``KNOWLEDGE_V2_POSTGRES_QUERY_TIMEOUT_MS`` must
still complete instead of being cancelled at every boot.
"""

from __future__ import annotations

from typing import Any

import asyncpg  # type: ignore[import-not-found]
import pytest

pytestmark = pytest.mark.postgres

_SCHEMA = "migration_timeout_probe"


async def test_a_migration_step_longer_than_the_query_timeout_completes(
    migrated_postgres: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from koda.knowledge.v2 import postgres_backend as backend_mod

    backend = backend_mod.KnowledgeV2PostgresBackend(
        agent_id=None, dsn=migrated_postgres, schema=_SCHEMA, query_timeout_ms=200
    )
    slow = backend_mod._Migration("001_slow_index_build", ("SELECT pg_sleep(1)",))
    monkeypatch.setattr(backend, "_migrations", lambda: (slow,))
    monkeypatch.setattr(backend, "_unversioned_vector_statements", lambda: ())
    admin: Any = await asyncpg.connect(migrated_postgres)
    try:
        await admin.execute(f'DROP SCHEMA IF EXISTS "{_SCHEMA}" CASCADE')

        assert await backend.bootstrap() is True

        applied = await admin.fetch(f'SELECT version FROM "{_SCHEMA}"."schema_migrations"')
        assert [row["version"] for row in applied] == ["001_slow_index_build"]
        # Queries still run under the query timeout.
        async with backend._connection() as conn:
            with pytest.raises(TimeoutError):
                await conn.execute("SELECT pg_sleep(1)")
    finally:
        await backend.close()
        await admin.execute(f'DROP SCHEMA IF EXISTS "{_SCHEMA}" CASCADE')
        await admin.close()
