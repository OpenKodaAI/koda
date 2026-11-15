"""One canonical list of per-agent tables, checked against the live schema.

``koda.control_plane.agent_tables`` lists the control-plane tables that hold
per-agent rows. The legacy default-agent id repair and agent hard delete both
read that list (M2-E3-T2, D-054, TD-079). The schema test enumerates every
table with an ``agent_id`` column in the migrated database and fails when one
is neither listed nor explicitly exempt, so a new per-agent table cannot be
forgotten.
"""

from __future__ import annotations

from typing import Any

import pytest

import koda.control_plane.manager as manager_mod
from koda.control_plane import database as control_plane_db
from koda.control_plane.agent_tables import (
    AGENT_DELETE_RETAINED_TABLES,
    AGENT_DELETE_TABLES,
    AGENT_ID_TABLE_EXEMPTIONS,
    PER_AGENT_TABLES,
)

# What hard delete purged before the canonical list existed. Delete behaviour
# does not change in M2-E3-T2; M2-E3-T3 changes it.
_DELETE_TABLES_BEFORE_CANONICAL_LIST = {
    "cp_agent_sections",
    "cp_agent_documents",
    "cp_agent_config_versions",
    "cp_apply_operations",
    "cp_knowledge_assets",
    "cp_template_assets",
    "cp_skill_assets",
    "cp_mcp_agent_connections",
    "cp_mcp_tool_policies",
    "cp_mcp_discovered_tools",
    "cp_mcp_oauth_tokens",
    "cp_mcp_oauth_sessions",
    "cp_agent_connections",
}


@pytest.mark.postgres
def test_every_agent_id_table_in_the_schema_is_listed_or_exempt(migrated_postgres: str) -> None:
    rows = control_plane_db.fetch_all(
        """
        SELECT DISTINCT table_name
        FROM information_schema.columns
        WHERE table_schema = current_schema() AND column_name = 'agent_id'
        """
    )
    live = {str(row["table_name"]) for row in rows}
    assert "cp_secret_values" in live, "the schema enumeration found no control-plane tables"

    classified = set(PER_AGENT_TABLES) | AGENT_ID_TABLE_EXEMPTIONS
    unclassified = sorted(live - classified)
    assert not unclassified, (
        "These tables have an agent_id column but are neither in PER_AGENT_TABLES nor in "
        f"AGENT_ID_TABLE_EXEMPTIONS (koda/control_plane/agent_tables.py): {unclassified}"
    )
    stale = sorted(classified - live)
    assert not stale, f"agent_tables.py names tables that have no agent_id column in the schema: {stale}"


def test_listed_and_exempt_tables_do_not_overlap() -> None:
    assert len(PER_AGENT_TABLES) == len(set(PER_AGENT_TABLES))
    assert not set(PER_AGENT_TABLES) & AGENT_ID_TABLE_EXEMPTIONS
    assert AGENT_DELETE_RETAINED_TABLES.issubset(PER_AGENT_TABLES)
    assert set(AGENT_DELETE_TABLES) == set(PER_AGENT_TABLES) - AGENT_DELETE_RETAINED_TABLES


def _recording_execute(executed: list[str]) -> Any:
    def _execute(query: str, params: tuple[Any, ...] = ()) -> int:
        executed.append(" ".join(query.split()))
        return 1

    return _execute


def test_legacy_id_repair_rewrites_every_listed_table(monkeypatch: pytest.MonkeyPatch) -> None:
    executed: list[str] = []

    def _fetch_one(query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        # The legacy lowercase row exists; the canonical one does not.
        return {"id": "koda"} if params == ("koda",) else None

    monkeypatch.setattr(manager_mod, "fetch_one", _fetch_one)
    monkeypatch.setattr(manager_mod, "execute", _recording_execute(executed))
    manager = manager_mod.ControlPlaneManager.__new__(manager_mod.ControlPlaneManager)

    manager._repair_legacy_default_agent_id()

    rewritten = {query.split()[1] for query in executed if query.startswith("UPDATE ") and "SET agent_id = ?" in query}
    assert rewritten == set(PER_AGENT_TABLES)


def test_delete_purges_the_listed_delete_tables_and_nothing_else(monkeypatch: pytest.MonkeyPatch) -> None:
    executed: list[str] = []
    monkeypatch.setattr(manager_mod, "execute", _recording_execute(executed))
    manager = manager_mod.ControlPlaneManager.__new__(manager_mod.ControlPlaneManager)
    manager._require_agent_row = lambda agent_id: ("ATLAS", {"id": "ATLAS"})  # type: ignore[method-assign]

    assert manager.delete_agent("atlas") is True

    purged = {query.split()[2] for query in executed if query.startswith("DELETE FROM ") and "agent_id = ?" in query}
    assert purged == set(AGENT_DELETE_TABLES)
    assert purged == _DELETE_TABLES_BEFORE_CANONICAL_LIST
    assert executed[-1] == "DELETE FROM cp_agent_definitions WHERE id = ?"
