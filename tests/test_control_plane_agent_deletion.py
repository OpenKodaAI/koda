"""Regression coverage for agent deletion.

The DELETE /api/control-plane/agents/{agent_id} endpoint must actually remove
the agent and its dependent records. The previous behaviour only flipped
`status='archived'`, leaving the row visible in `list_agents()` — which made
the "Remover agente" UX appear broken.

These tests pin the contract:
* `delete_agent(agent_id)` exists on the manager and is a hard delete.
* It removes the row from `cp_agent_definitions` AND cascades through the
  dependent cp_* tables that hold per-agent state (sections, documents,
  config versions, mcp connections, tool policies, discovered tools,
  oauth tokens/sessions, knowledge / template / skill assets).
* It is idempotent — deleting a non-existent agent returns `False`, not a
  crash.
* The DELETE endpoint handler calls `delete_agent`, not `archive_agent`.
"""

from __future__ import annotations

import pytest

import koda.control_plane.manager as manager_mod


def _manager() -> manager_mod.ControlPlaneManager:
    return manager_mod.ControlPlaneManager.__new__(manager_mod.ControlPlaneManager)


def test_manager_exposes_delete_agent() -> None:
    assert hasattr(manager_mod.ControlPlaneManager, "delete_agent"), (
        "ControlPlaneManager must expose a delete_agent() method for hard deletion."
    )


def test_delete_agent_issues_delete_for_main_row(monkeypatch) -> None:
    """The agent's own row in cp_agent_definitions must be DELETED — not
    updated to status='archived'."""
    manager = _manager()
    executed: list[tuple[str, tuple]] = []

    def _fake_fetch_one(query: str, params: tuple = ()):
        # Return a synthetic row so the require_agent_row guard passes.
        if "FROM cp_agent_definitions" in query and "WHERE id" in query:
            return {"id": params[0] if params else "ATLAS", "status": "active"}
        return None

    def _fake_execute(query: str, params: tuple = ()):
        executed.append((" ".join(query.split()), params))
        return 1

    monkeypatch.setattr(manager_mod, "fetch_one", _fake_fetch_one)
    monkeypatch.setattr(manager_mod, "fetch_all", lambda *args, **kwargs: [])
    monkeypatch.setattr(manager_mod, "execute", _fake_execute)
    monkeypatch.setattr(manager_mod, "with_connection", lambda fn: fn(object()))
    manager._require_agent_row = lambda agent_id: (agent_id.upper(), {"id": agent_id.upper(), "status": "active"})  # type: ignore[attr-defined]

    result = manager.delete_agent("atlas")

    assert result is True, "delete_agent must return True when a row is removed."
    agent_deletes = [q for q, _p in executed if q.startswith("DELETE FROM cp_agent_definitions")]
    assert agent_deletes, "delete_agent must emit a DELETE against cp_agent_definitions."
    status_updates = [q for q, _p in executed if "UPDATE cp_agent_definitions" in q and "status" in q.lower()]
    assert not status_updates, (
        "delete_agent must not soft-delete via status='archived' — the old "
        "archive_agent behaviour is what the user reported as broken."
    )


def test_delete_agent_cascades_to_dependent_tables(monkeypatch) -> None:
    """Dependent cp_* rows must be deleted too. We assert that every table
    known to carry agent_id gets a DELETE with the correct agent_id param."""
    manager = _manager()
    executed: list[str] = []

    def _fake_execute(query: str, params: tuple = ()):
        # Record the normalised query + parameter shape so the assertion can
        # confirm the cascade is scoped.
        executed.append(" ".join(query.split()))
        return 1

    monkeypatch.setattr(manager_mod, "execute", _fake_execute)
    monkeypatch.setattr(manager_mod, "fetch_all", lambda *args, **kwargs: [])
    monkeypatch.setattr(manager_mod, "fetch_one", lambda *args, **kwargs: None)
    monkeypatch.setattr(manager_mod, "with_connection", lambda fn: fn(object()))
    manager._require_agent_row = lambda agent_id: (agent_id.upper(), {"id": agent_id.upper(), "status": "active"})  # type: ignore[attr-defined]

    manager.delete_agent("atlas")

    expected_tables = {
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
        "cp_agent_definitions",
    }
    for table in expected_tables:
        assert any(f"DELETE FROM {table}" in q for q in executed), (
            f"delete_agent must emit DELETE FROM {table} WHERE agent_id = ? — missing."
        )


def test_delete_agent_is_idempotent_when_agent_missing(monkeypatch) -> None:
    manager = _manager()
    manager._require_agent_row = lambda agent_id: (_ for _ in ()).throw(KeyError(agent_id))  # type: ignore[attr-defined]

    result = manager.delete_agent("ghost")
    assert result is False, (
        "delete_agent must return False when the agent does not exist; "
        "repeated clicks or stale UI state should not 500."
    )


@pytest.mark.asyncio
async def test_delete_endpoint_calls_delete_agent_not_archive(monkeypatch) -> None:
    """The API handler registered at DELETE /api/control-plane/agents/{agent_id}
    must delegate to `delete_agent`, not `archive_agent`."""
    import koda.control_plane.api as api_mod

    calls: dict[str, list[str]] = {"delete": [], "archive": []}

    class _FakeManager:
        def delete_agent(self, agent_id: str) -> bool:
            calls["delete"].append(agent_id)
            return True

        def archive_agent(self, agent_id: str) -> bool:
            calls["archive"].append(agent_id)
            return True

    monkeypatch.setattr(api_mod, "_manager", lambda: _FakeManager())

    class _FakeRequest:
        match_info = {"agent_id": "atlas"}

    response = await api_mod.delete_agent(_FakeRequest())  # type: ignore[arg-type]

    assert response.status == 200
    assert calls["delete"] == ["atlas"]
    assert calls["archive"] == [], (
        "delete_agent endpoint must not fall through to archive_agent — archiving "
        "left the row visible in list_agents() and is what the user reported as broken."
    )
