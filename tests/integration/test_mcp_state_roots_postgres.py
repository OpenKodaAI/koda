"""D-318 against a real Postgres: the state roots agents' published settings give their workers.

The supervisor gives a worker the ``STATE_ROOT_DIR`` of the snapshot it runs
unless the control plane's environment forces one, so the mount check reads
each agent's applied and desired snapshot from the control-plane store.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import pytest

import koda.control_plane.manager as manager_mod
from koda.integrations.custom_mcp_registry import ValidationError, validate_isolation_constraints
from tests.postgres_fixtures import close_shared_postgres_backends

pytestmark = [pytest.mark.postgres]

_SCHEMA = os.environ.get("KNOWLEDGE_V2_POSTGRES_SCHEMA") or "knowledge_v2"
_AGENTS = ("D318_AGENT_A", "D318_AGENT_B")


async def _execute(dsn: str, sql: str, *params: Any) -> None:
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(sql, *params)
    finally:
        await conn.close()


async def _clear(dsn: str) -> None:
    for table, column in (("cp_agent_config_versions", "agent_id"), ("cp_agent_definitions", "id")):
        await _execute(dsn, f'DELETE FROM "{_SCHEMA}"."{table}" WHERE {column} = ANY($1::text[])', list(_AGENTS))


async def _agent(dsn: str, agent_id: str, *, applied: int | None, desired: int | None) -> None:
    await _execute(
        dsn,
        f"""INSERT INTO "{_SCHEMA}"."cp_agent_definitions"
               (id, display_name, storage_namespace, applied_version, desired_version, created_at, updated_at)
            VALUES ($1, $1, $1, $2, $3, 'now', 'now')""",
        agent_id,
        applied,
        desired,
    )


async def _version(dsn: str, agent_id: str, version: int, env: dict[str, str]) -> None:
    snapshot = json.dumps({"env": env, "process_env": env, "documents": {}})
    await _execute(
        dsn,
        f"""INSERT INTO "{_SCHEMA}"."cp_agent_config_versions"
               (agent_id, version, snapshot_json, created_at, published_at)
            VALUES ($1, $2, $3, 'now', 'now')""",
        agent_id,
        version,
        snapshot,
    )


@pytest.fixture
async def agents_db(migrated_postgres: str) -> AsyncIterator[str]:
    close_shared_postgres_backends()
    await _clear(migrated_postgres)
    try:
        yield migrated_postgres
    finally:
        await _clear(migrated_postgres)
        close_shared_postgres_backends()


async def test_published_state_roots_are_those_of_applied_and_desired_snapshots(agents_db, monkeypatch, tmp_path):
    root = tmp_path / "srv"
    await _agent(agents_db, "D318_AGENT_A", applied=2, desired=3)
    await _version(agents_db, "D318_AGENT_A", 1, {"STATE_ROOT_DIR": f"{root}/a-superseded"})
    await _version(agents_db, "D318_AGENT_A", 2, {"STATE_ROOT_DIR": f"{root}/a-applied", "LOG_LEVEL": "INFO"})
    await _version(agents_db, "D318_AGENT_A", 3, {"STATE_ROOT_DIR": f"{root}/a-desired"})
    await _agent(agents_db, "D318_AGENT_B", applied=1, desired=1)
    await _version(agents_db, "D318_AGENT_B", 1, {"D318_AGENT_B_STATE_ROOT_DIR": f"{root}/b"})
    manager = manager_mod.ControlPlaneManager.__new__(manager_mod.ControlPlaneManager)
    monkeypatch.setattr(manager_mod, "get_control_plane_manager", lambda: manager)
    monkeypatch.delenv("STATE_ROOT_DIR", raising=False)

    roots = manager.published_state_roots()

    assert {path for path in roots if path.startswith(str(root))} == {
        f"{root}/a-applied",
        f"{root}/a-desired",
        f"{root}/b",
    }
    for host in (f"{root}/a-applied", f"{root}/a-desired/control_plane", f"{root}/b"):
        with pytest.raises(ValidationError, match="sensitive host path"):
            validate_isolation_constraints({"mounts": [{"host": host, "container": "/data"}]})
    # A superseded snapshot no worker runs (a rollback makes it the desired one again).
    validate_isolation_constraints({"mounts": [{"host": f"{root}/a-superseded", "container": "/data"}]})
