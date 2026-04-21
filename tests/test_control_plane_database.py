"""Focused tests for control-plane database primary mode."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


def test_control_plane_database_prefers_primary_backend():
    import koda.control_plane.database as database

    backend = SimpleNamespace(start=AsyncMock(return_value=True))

    with (
        patch("koda.control_plane.database.STATE_BACKEND", "postgres"),
        patch("koda.control_plane.database.get_primary_state_backend", return_value=backend),
        patch("koda.control_plane.database.primary_fetch_one", new=AsyncMock(return_value={"id": "agent_a"})),
        patch("koda.control_plane.database.primary_fetch_all", new=AsyncMock(return_value=[{"id": "agent_a"}])),
        patch("koda.control_plane.database.primary_fetch_val", new=AsyncMock(return_value=17)),
    ):
        database.init_control_plane_db()
        row = database.fetch_one("SELECT * FROM cp_agent_definitions WHERE id = ?", ("agent_a",))
        rows = database.fetch_all("SELECT * FROM cp_agent_definitions ORDER BY id ASC")
        inserted = database.execute(
            "INSERT INTO cp_global_default_versions (snapshot_json, created_at) VALUES (?, ?)",
            ("{}", "2026-03-26T00:00:00+00:00"),
        )

    backend.start.assert_awaited_once()
    assert row == {"id": "agent_a"}
    assert rows == [{"id": "agent_a"}]
    assert inserted == 17


def test_control_plane_execute_falls_back_to_primary_execute_when_table_has_no_id():
    import koda.control_plane.database as database

    with (
        patch("koda.control_plane.database.STATE_BACKEND", "postgres"),
        patch("koda.control_plane.database.get_primary_state_backend", return_value=object()),
        patch("koda.control_plane.database.primary_fetch_val", new=AsyncMock(side_effect=RuntimeError("no id"))),
        patch("koda.control_plane.database.primary_execute", new=AsyncMock(return_value=1)) as primary_execute,
    ):
        affected = database.execute(
            """
            INSERT INTO cp_global_sections (section, data_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(section) DO UPDATE SET data_json = excluded.data_json, updated_at = excluded.updated_at
            """,
            ("general", "{}", "2026-03-26T00:00:00+00:00"),
        )

    primary_execute.assert_awaited_once()
    assert affected == 1


def test_control_plane_with_connection_replays_operations_in_primary_mode():
    import koda.control_plane.database as database

    with (
        patch("koda.control_plane.database.STATE_BACKEND", "postgres"),
        patch("koda.control_plane.database.get_primary_state_backend", return_value=object()),
        patch("koda.control_plane.database.primary_execute", new=AsyncMock(return_value=1)) as primary_execute,
    ):

        def _delete(conn: object) -> str:
            recorder = conn
            recorder.execute("DELETE FROM cp_workspace_squads WHERE workspace_id = ?", ("ws-1",))
            recorder.execute("DELETE FROM cp_workspaces WHERE id = ?", ("ws-1",))
            return "ok"

        result = database.with_connection(_delete)

    assert result == "ok"
    assert primary_execute.await_count == 2
