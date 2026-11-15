"""Bootstrap migrations are not cut off by the query timeout (D-285).

An index build on a large table can take longer than any query should, so a
migration step longer than ``KNOWLEDGE_V2_POSTGRES_QUERY_TIMEOUT_MS`` must
still complete instead of being cancelled at every boot. The control plane
applies them at boot from its running event loop, so through the sync bridge:
its ``PRIMARY_STATE_BRIDGE_TIMEOUT_SECONDS`` must not cut them off either.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import asyncpg  # type: ignore[import-not-found]
import pytest

from tests.postgres_fixtures import stop_primary_bridge

pytestmark = pytest.mark.postgres

_SCHEMA = "migration_timeout_probe"
_SLOW_VERSION = "001_slow_index_build"


def _slow_backend(dsn: str, monkeypatch: pytest.MonkeyPatch, *, seconds: float) -> Any:
    """A backend whose only migration takes ``seconds``, with a 200 ms query timeout."""
    from koda.knowledge.v2 import postgres_backend as backend_mod

    backend = backend_mod.KnowledgeV2PostgresBackend(agent_id=None, dsn=dsn, schema=_SCHEMA, query_timeout_ms=200)
    slow = backend_mod._Migration(_SLOW_VERSION, (f"SELECT pg_sleep({seconds})",))
    monkeypatch.setattr(backend, "_migrations", lambda: (slow,))
    monkeypatch.setattr(backend, "_unversioned_vector_statements", lambda: ())
    return backend


async def _applied(admin: Any) -> list[str]:
    if await admin.fetchval("SELECT to_regclass($1)", f'"{_SCHEMA}"."schema_migrations"') is None:
        return []
    return [str(row["version"]) for row in await admin.fetch(f'SELECT version FROM "{_SCHEMA}"."schema_migrations"')]


async def test_a_migration_step_longer_than_the_query_timeout_completes(
    migrated_postgres: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = _slow_backend(migrated_postgres, monkeypatch, seconds=1)
    admin: Any = await asyncpg.connect(migrated_postgres)
    try:
        await admin.execute(f'DROP SCHEMA IF EXISTS "{_SCHEMA}" CASCADE')

        assert await backend.bootstrap() is True

        assert await _applied(admin) == [_SLOW_VERSION]
        # Queries still run under the query timeout.
        async with backend._connection() as conn:
            with pytest.raises(TimeoutError):
                await conn.execute("SELECT pg_sleep(1)")
    finally:
        await backend.close()
        await admin.execute(f'DROP SCHEMA IF EXISTS "{_SCHEMA}" CASCADE')
        await admin.close()


async def test_the_control_plane_boot_waits_for_a_migration_longer_than_the_bridge_timeout(
    migrated_postgres: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``init_control_plane_db`` from a running loop, as ``ControlPlaneSupervisor()`` in ``run_supervisor()``."""
    from koda.state import control_plane_store
    from koda.state import primary as primary_state

    backend = _slow_backend(migrated_postgres, monkeypatch, seconds=2)
    monkeypatch.setattr(primary_state, "_BRIDGE_TIMEOUT_SECONDS", 0.5)
    monkeypatch.setattr(control_plane_store, "STATE_BACKEND", "postgres")
    monkeypatch.setattr(control_plane_store, "get_primary_state_backend", lambda: backend)
    admin: Any = await asyncpg.connect(migrated_postgres)
    try:
        await admin.execute(f'DROP SCHEMA IF EXISTS "{_SCHEMA}" CASCADE')

        control_plane_store.init_control_plane_db()

        assert await _applied(admin) == [_SLOW_VERSION]
    finally:
        primary_state.run_coro_sync(backend.close())
        stop_primary_bridge()
        await admin.execute(f'DROP SCHEMA IF EXISTS "{_SCHEMA}" CASCADE')
        await admin.close()


async def test_a_health_check_that_stops_waiting_leaves_the_migrations_running(
    migrated_postgres: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control plane's database health check answers after the bridge timeout; the migration still completes."""
    from koda.control_plane import manager as manager_mod
    from koda.state import primary as primary_state

    backend = _slow_backend(migrated_postgres, monkeypatch, seconds=2)
    monkeypatch.setattr(primary_state, "_BRIDGE_TIMEOUT_SECONDS", 0.5)
    monkeypatch.setattr(manager_mod, "KNOWLEDGE_V2_POSTGRES_DSN", migrated_postgres)
    monkeypatch.setattr(manager_mod, "get_shared_postgres_backend", lambda **_kwargs: backend)
    admin: Any = await asyncpg.connect(migrated_postgres)
    try:
        await admin.execute(f'DROP SCHEMA IF EXISTS "{_SCHEMA}" CASCADE')

        payload = manager_mod.ControlPlaneManager._database_health_payload(SimpleNamespace())  # type: ignore[arg-type]

        assert payload["ready"] is False
        assert "primary_state_bridge_timeout" in str(payload["reason"])
        for _ in range(100):
            if await _applied(admin):
                break
            await asyncio.sleep(0.1)
        assert await _applied(admin) == [_SLOW_VERSION]
    finally:
        primary_state.run_coro_sync(backend.close())
        stop_primary_bridge()
        await admin.execute(f'DROP SCHEMA IF EXISTS "{_SCHEMA}" CASCADE')
        await admin.close()
