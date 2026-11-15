"""Multi-statement control-plane writes commit together or not at all (D-056).

Each test runs on the migrated Postgres test database and injects a fault
from inside Postgres (``injected_fault``) partway through the operation.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest

from koda.control_plane import database as control_plane_db
from koda.control_plane import manager as manager_mod
from tests.postgres_fixtures import injected_fault

pytestmark = pytest.mark.postgres

_NOW = "2026-11-15T00:00:00+00:00"


@pytest.fixture()
def ids(migrated_postgres: str) -> Iterator[dict[str, str]]:
    """Fresh agent, workspace and squad ids; their rows are deleted afterwards."""
    suffix = uuid.uuid4().hex[:12]
    seeded = {"agent": f"TXTEST_{suffix.upper()}", "workspace": f"txtest_{suffix}", "squad": f"txtest_{suffix}_sq"}
    yield seeded
    for table in ("cp_agent_sections", "cp_agent_documents"):
        control_plane_db.execute(f"DELETE FROM {table} WHERE agent_id = ?", (seeded["agent"],))
    control_plane_db.execute("DELETE FROM cp_agent_definitions WHERE id = ?", (seeded["agent"],))
    control_plane_db.execute("DELETE FROM cp_workspace_squads WHERE id = ?", (seeded["squad"],))
    control_plane_db.execute("DELETE FROM cp_workspaces WHERE id = ?", (seeded["workspace"],))


def _manager() -> manager_mod.ControlPlaneManager:
    # ``__new__`` skips seeding and legacy import, so only the rows seeded here exist for these ids.
    return manager_mod.ControlPlaneManager.__new__(manager_mod.ControlPlaneManager)


def _seed_agent(agent_id: str, *, workspace_id: str | None = None, squad_id: str | None = None) -> None:
    control_plane_db.execute(
        """
        INSERT INTO cp_agent_definitions (
            id, display_name, storage_namespace, workspace_id, squad_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (agent_id, agent_id, agent_id.lower(), workspace_id, squad_id, _NOW, _NOW),
    )
    control_plane_db.execute(
        "INSERT INTO cp_agent_sections (agent_id, section, data_json, updated_at) VALUES (?, ?, ?, ?)",
        (agent_id, "identity", "{}", _NOW),
    )
    control_plane_db.execute(
        "INSERT INTO cp_agent_documents (agent_id, kind, content_md, updated_at) VALUES (?, ?, ?, ?)",
        (agent_id, "system_prompt", "prompt", _NOW),
    )


def _seed_workspace(workspace_id: str, squad_id: str) -> None:
    control_plane_db.execute(
        "INSERT INTO cp_workspaces (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (workspace_id, workspace_id, _NOW, _NOW),
    )
    control_plane_db.execute(
        "INSERT INTO cp_workspace_squads (id, workspace_id, name, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (squad_id, workspace_id, "Squad", _NOW, _NOW),
    )


def _agent_rows(agent_id: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table, column in (
        ("cp_agent_definitions", "id"),
        ("cp_agent_sections", "agent_id"),
        ("cp_agent_documents", "agent_id"),
    ):
        row = control_plane_db.fetch_one(f"SELECT COUNT(*) AS count FROM {table} WHERE {column} = ?", (agent_id,))
        counts[table] = int(row["count"]) if row else 0
    return counts


def test_with_connection_applies_nothing_when_a_statement_fails(ids: dict[str, str]) -> None:
    def _writes(conn: object) -> None:
        conn.execute(  # type: ignore[attr-defined]
            "INSERT INTO cp_workspaces (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (ids["workspace"], "Tx", _NOW, _NOW),
        )
        conn.execute("INSERT INTO cp_txtest_missing_table (id) VALUES (?)", (ids["workspace"],))  # type: ignore[attr-defined]

    with pytest.raises(Exception, match="cp_txtest_missing_table"):
        control_plane_db.with_connection(_writes)

    assert control_plane_db.fetch_one("SELECT id FROM cp_workspaces WHERE id = ?", (ids["workspace"],)) is None


def test_agent_delete_fault_keeps_every_row(ids: dict[str, str]) -> None:
    agent_id = ids["agent"]
    _seed_agent(agent_id)
    manager = _manager()

    with injected_fault("cp_agent_definitions", "DELETE"), pytest.raises(Exception, match="injected fault"):
        manager.delete_agent(agent_id)

    assert _agent_rows(agent_id) == {"cp_agent_definitions": 1, "cp_agent_sections": 1, "cp_agent_documents": 1}
    assert manager.delete_agent(agent_id) is True
    assert _agent_rows(agent_id) == {"cp_agent_definitions": 0, "cp_agent_sections": 0, "cp_agent_documents": 0}


def test_workspace_delete_fault_keeps_squads_and_assignments(ids: dict[str, str]) -> None:
    _seed_workspace(ids["workspace"], ids["squad"])
    _seed_agent(ids["agent"], workspace_id=ids["workspace"], squad_id=ids["squad"])
    manager = _manager()

    with injected_fault("cp_workspaces", "DELETE"), pytest.raises(Exception, match="injected fault"):
        manager.delete_workspace(ids["workspace"])

    agent = control_plane_db.fetch_one(
        "SELECT workspace_id, squad_id FROM cp_agent_definitions WHERE id = ?",
        (ids["agent"],),
    )
    assert agent == {"workspace_id": ids["workspace"], "squad_id": ids["squad"]}
    assert control_plane_db.fetch_one("SELECT id FROM cp_workspace_squads WHERE id = ?", (ids["squad"],)) is not None
    assert manager.delete_workspace(ids["workspace"]) is True
    agent = control_plane_db.fetch_one(
        "SELECT workspace_id, squad_id FROM cp_agent_definitions WHERE id = ?",
        (ids["agent"],),
    )
    assert agent == {"workspace_id": None, "squad_id": None}
    assert control_plane_db.fetch_one("SELECT id FROM cp_workspace_squads WHERE id = ?", (ids["squad"],)) is None
    assert control_plane_db.fetch_one("SELECT id FROM cp_workspaces WHERE id = ?", (ids["workspace"],)) is None
