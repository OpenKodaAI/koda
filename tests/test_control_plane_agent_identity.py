"""Agent ids: collisions answer 409, and the server picks ids (M2-E3-T1).

``create_agent`` used ``INSERT ... ON CONFLICT (id) DO NOTHING`` and returned
the existing agent with 201, and ``clone_agent`` then wrote the source's
sections and documents into it. Ids are normalised (``My Agent`` and
``my-agent`` are both ``MY_AGENT``), so a different spelling collided too
(D-055, F-AGT-02, F-AGT-03). The dashboard allocated ids and health ports
itself (TD-149); the server now generates both when the request has no id.

These tests run against the real control-plane tables on Postgres.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import koda.control_plane.manager as manager_mod
from koda.control_plane import api as control_plane_api
from koda.control_plane import database as control_plane_db
from koda.control_plane.agent_tables import PER_AGENT_TABLES


@pytest.fixture()
def manager(migrated_postgres: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[manager_mod.ControlPlaneManager]:
    tables = ("cp_agent_definitions", *PER_AGENT_TABLES)
    control_plane_db.execute(f"TRUNCATE TABLE {', '.join(tables)}")
    instance = manager_mod.ControlPlaneManager()
    # Skip legacy-state seeding: these tests own every agent row.
    instance._seeding_legacy_state = True
    # get_agent asks a local Ollama for its models; there is none here.
    monkeypatch.setattr(instance, "_fetch_ollama_model_catalog", lambda **kwargs: {"items": []})
    yield instance
    control_plane_db.execute(f"TRUNCATE TABLE {', '.join(tables)}")


def _definition(agent_id: str) -> dict[str, object]:
    row = control_plane_db.fetch_one("SELECT * FROM cp_agent_definitions WHERE id = ?", (agent_id,))
    assert row is not None, f"agent {agent_id} not persisted"
    return dict(row)


def _identity(agent_id: str) -> str:
    row = control_plane_db.fetch_one(
        "SELECT content_md FROM cp_agent_documents WHERE agent_id = ? AND kind = ?", (agent_id, "identity_md")
    )
    return str(row["content_md"]) if row else ""


def _health_port(agent: dict[str, object]) -> int:
    endpoint = agent["runtime_endpoint"]
    assert isinstance(endpoint, dict)
    return int(endpoint["health_port"])


@pytest.mark.postgres
def test_create_conflicts_when_the_id_collides_after_normalisation(manager: manager_mod.ControlPlaneManager) -> None:
    manager.create_agent({"id": "My Agent", "display_name": "First"})

    with pytest.raises(manager_mod.AgentIdConflictError):
        manager.create_agent({"id": "my-agent", "display_name": "Second"})

    assert _definition("MY_AGENT")["display_name"] == "First"


@pytest.mark.postgres
def test_create_without_an_id_generates_a_free_id_and_health_port(manager: manager_mod.ControlPlaneManager) -> None:
    first = manager.create_agent({"display_name": "Novo agente"})
    second = manager.create_agent({"display_name": "Novo agente"})

    assert first["id"] == "NOVO_AGENTE"
    assert second["id"] == "NOVO_AGENTE_2"
    assert second["display_name"] == "Novo agente"
    assert _health_port(first) != _health_port(second)


@pytest.mark.postgres
def test_clone_onto_an_existing_id_conflicts_and_leaves_the_target_alone(
    manager: manager_mod.ControlPlaneManager,
) -> None:
    manager.create_agent({"id": "SOURCE", "display_name": "Source"})
    manager.upsert_document("SOURCE", "identity_md", {"content_md": "source identity"})
    manager.create_agent({"id": "TARGET", "display_name": "Target"})
    manager.upsert_document("TARGET", "identity_md", {"content_md": "target identity"})

    with pytest.raises(manager_mod.AgentIdConflictError):
        manager.clone_agent("SOURCE", {"id": "target", "display_name": "Copy"})

    assert _definition("TARGET")["display_name"] == "Target"
    assert _identity("TARGET") == "target identity"


@pytest.mark.postgres
def test_clone_without_an_id_generates_one_and_copies_the_source(manager: manager_mod.ControlPlaneManager) -> None:
    manager.create_agent({"id": "ATLAS", "display_name": "Atlas"})
    manager.upsert_document("ATLAS", "identity_md", {"content_md": "atlas identity"})

    clone = manager.clone_agent("ATLAS", {"display_name": "Atlas (Cópia)"})

    assert clone["id"] == "ATLAS_COPIA"
    assert clone["display_name"] == "Atlas (Cópia)"
    assert _identity("ATLAS_COPIA") == "atlas identity"


@pytest.mark.postgres
async def test_create_and_clone_routes_answer_409_on_collision(
    manager: manager_mod.ControlPlaneManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(control_plane_api, "_manager", lambda: manager)
    app = web.Application(middlewares=[control_plane_api.control_plane_error_middleware])
    app.router.add_post("/api/control-plane/agents", control_plane_api.create_agent)
    app.router.add_post("/api/control-plane/agents/{agent_id}/clone", control_plane_api.clone_agent)

    async with TestClient(TestServer(app)) as client:
        created = await client.post("/api/control-plane/agents", json={"id": "My Agent"})
        assert created.status == 201

        duplicate = await client.post("/api/control-plane/agents", json={"id": "my-agent"})
        assert duplicate.status == 409
        assert "MY_AGENT" in (await duplicate.json())["error"]

        clone = await client.post("/api/control-plane/agents/MY_AGENT/clone", json={"id": "my agent"})
        assert clone.status == 409


@pytest.mark.postgres
def test_legacy_import_that_loses_the_create_race_skips_the_agent(
    manager: manager_mod.ControlPlaneManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Two processes seed a fresh database: both see KODA missing, the other one inserts it first.
    real_create = manager.create_agent

    def create_after_the_other_process(payload: dict[str, Any]) -> dict[str, Any]:
        real_create({**payload, "display_name": "Other process"})
        return real_create(payload)

    published: list[str] = []
    monkeypatch.setattr(manager, "create_agent", create_after_the_other_process)
    monkeypatch.setattr(manager, "_load_legacy_env", lambda: {})
    monkeypatch.setattr(manager, "_discover_legacy_agent_ids", lambda env_values: ["KODA"])
    monkeypatch.setattr(manager, "patch_global_defaults", lambda payload: {})
    monkeypatch.setattr(manager, "publish_agent", lambda agent_id: published.append(agent_id) or {"version": 1})
    manager._seeding_legacy_state = False

    manager.import_legacy_state()

    assert _definition("KODA")["display_name"] == "Other process"
    assert published == []


@pytest.mark.postgres
def test_create_without_an_id_tries_one_candidate_when_the_name_is_taken(
    manager: manager_mod.ControlPlaneManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    for agent_id in ("NOVO_AGENTE", *(f"NOVO_AGENTE_{suffix}" for suffix in range(2, 6))):
        manager.create_agent({"id": agent_id, "display_name": "Novo agente"})
    endpoint_calls: list[str] = []
    inserts: list[str] = []
    real_endpoint = manager._normalize_runtime_endpoint_for_agent
    real_fetch_one = manager_mod.fetch_one

    def spy_endpoint(agent_id: str, runtime_endpoint: dict[str, Any]) -> dict[str, Any]:
        endpoint_calls.append(agent_id)
        return real_endpoint(agent_id, runtime_endpoint)

    def spy_fetch_one(query: str, params: tuple[Any, ...] = ()) -> Any:
        if "INSERT INTO cp_agent_definitions" in query:
            inserts.append(str(params[0]))
        return real_fetch_one(query, params)

    monkeypatch.setattr(manager, "_normalize_runtime_endpoint_for_agent", spy_endpoint)
    monkeypatch.setattr(manager_mod, "fetch_one", spy_fetch_one)

    created = manager.create_agent({"display_name": "Novo agente"})

    assert created["id"] == "NOVO_AGENTE_6"
    # No health-port scan or INSERT for the five taken ids (get_agent may resolve the endpoint again).
    assert set(endpoint_calls) == {"NOVO_AGENTE_6"}
    assert inserts == ["NOVO_AGENTE_6"]
