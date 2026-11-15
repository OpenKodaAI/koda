"""PATCH ``status`` goes through ``pause_agent`` / ``activate_agent`` (M2-E3-T4).

``update_agent`` used to write ``status`` straight to ``cp_agent_definitions``.
A PATCH pause therefore skipped the queue rollback, the supervisor wake signal
and the audit row that ``pause_agent`` writes, and the killed worker left its
queue items in ``running`` (D-150, F-AGT-08). PATCH now hands a change to
``active`` or ``paused`` to the lifecycle methods and rejects any other status
change.

These tests run against the real control-plane tables on Postgres.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import koda.control_plane.lifecycle_events as lifecycle_events
import koda.control_plane.manager as manager_mod
from koda.control_plane import api as control_plane_api
from koda.control_plane import database as control_plane_db
from koda.control_plane.agent_tables import PER_AGENT_TABLES

_TABLES = ("cp_agent_definitions", "runtime_queue_items", "audit_events", *PER_AGENT_TABLES)


@pytest.fixture()
def wakes(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    reasons: list[str] = []
    monkeypatch.setattr(lifecycle_events, "notify_lifecycle_change", lambda reason="": reasons.append(reason))
    return reasons


@pytest.fixture()
def manager(migrated_postgres: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[manager_mod.ControlPlaneManager]:
    control_plane_db.execute(f"TRUNCATE TABLE {', '.join(_TABLES)}")
    instance = manager_mod.ControlPlaneManager()
    # Skip legacy-state seeding: these tests own every agent row.
    instance._seeding_legacy_state = True
    # get_agent asks a local Ollama for its models; there is none here.
    monkeypatch.setattr(instance, "_fetch_ollama_model_catalog", lambda **kwargs: {"items": []})
    yield instance
    control_plane_db.execute(f"TRUNCATE TABLE {', '.join(_TABLES)}")


def _insert_agent(agent_id: str, status: str) -> None:
    now = control_plane_db.now_iso()
    control_plane_db.execute(
        """
        INSERT INTO cp_agent_definitions (id, display_name, status, storage_namespace, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (agent_id, agent_id, status, agent_id.lower(), now, now),
    )


def _insert_queue_item(agent_id: str, task_id: int, status: str) -> None:
    now = control_plane_db.now_iso()
    control_plane_db.execute(
        """
        INSERT INTO runtime_queue_items (agent_id, task_id, user_id, chat_id, status, queued_at, updated_at)
        VALUES (?, ?, 1, 1, ?, ?, ?)
        """,
        (agent_id, task_id, status, now, now),
    )


def _row(query: str, params: tuple[Any, ...]) -> dict[str, Any]:
    row = control_plane_db.fetch_one(query, params)
    assert row is not None
    return dict(row)


def _queue_statuses(agent_id: str) -> list[str]:
    rows = control_plane_db.fetch_all(
        "SELECT status FROM runtime_queue_items WHERE agent_id = ? ORDER BY task_id", (agent_id,)
    )
    return [str(row["status"]) for row in rows]


def _audit_events(agent_id: str) -> list[str]:
    rows = control_plane_db.fetch_all("SELECT event_type FROM audit_events WHERE agent_id = ? ORDER BY id", (agent_id,))
    return [str(row["event_type"]) for row in rows]


@pytest.mark.postgres
async def test_patch_pause_rolls_back_running_items_and_writes_an_audit_row(
    manager: manager_mod.ControlPlaneManager, wakes: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _insert_agent("ATLAS", "active")
    _insert_queue_item("ATLAS", 1, "running")
    _insert_queue_item("ATLAS", 2, "retrying")
    _insert_queue_item("ATLAS", 3, "queued")
    monkeypatch.setattr(control_plane_api, "_manager", lambda: manager)
    app = web.Application(middlewares=[control_plane_api.control_plane_error_middleware])
    app.router.add_patch("/api/control-plane/agents/{agent_id}", control_plane_api.patch_agent)

    async with TestClient(TestServer(app)) as client:
        response = await client.patch(
            "/api/control-plane/agents/ATLAS", json={"status": "paused", "display_name": "Atlas Renamed"}
        )
        assert response.status == 200
        body = await response.json()

    assert body["status"] == "paused"
    assert body["display_name"] == "Atlas Renamed"
    assert _queue_statuses("ATLAS") == ["queued", "queued", "queued"]
    assert _audit_events("ATLAS") == ["control_plane.agent_paused"]
    assert wakes == ["pause:ATLAS"]


@pytest.mark.postgres
def test_patch_activate_wakes_the_supervisor_and_writes_an_audit_row(
    manager: manager_mod.ControlPlaneManager, wakes: list[str]
) -> None:
    _insert_agent("ATLAS", "paused")

    result = manager.update_agent("atlas", {"status": "active"})

    assert result["status"] == "active"
    assert _row("SELECT status FROM cp_agent_definitions WHERE id = ?", ("ATLAS",))["status"] == "active"
    assert _audit_events("ATLAS") == ["control_plane.agent_activated"]
    assert wakes == ["activate:ATLAS"]


@pytest.mark.postgres
def test_patch_rejects_other_status_changes_and_leaves_the_agent_alone(
    manager: manager_mod.ControlPlaneManager, wakes: list[str]
) -> None:
    _insert_agent("ATLAS", "active")
    _insert_queue_item("ATLAS", 1, "running")

    with pytest.raises(ValueError, match="status"):
        manager.update_agent("ATLAS", {"status": "archived", "display_name": "Ignored"})

    row = _row("SELECT status, display_name FROM cp_agent_definitions WHERE id = ?", ("ATLAS",))
    assert row == {"status": "active", "display_name": "ATLAS"}
    assert _queue_statuses("ATLAS") == ["running"]
    assert _audit_events("ATLAS") == []
    assert wakes == []
