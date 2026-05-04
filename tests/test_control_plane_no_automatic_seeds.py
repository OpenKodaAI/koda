"""Regression coverage for first-use control planes staying empty."""

from __future__ import annotations

from typing import Any

import koda.control_plane.manager as manager_mod


def _manager() -> manager_mod.ControlPlaneManager:
    manager = object.__new__(manager_mod.ControlPlaneManager)
    manager._seeding_legacy_state = False
    manager._ollama_model_cache = {}
    manager._elevenlabs_voice_cache = {}
    manager._provider_login_processes = {}
    manager._claude_oauth_verifiers = {}
    manager._provider_download_threads = {}
    return manager


def test_control_plane_read_paths_do_not_seed_first_use_records(monkeypatch) -> None:
    writes: list[str] = []

    def fetch_one(query: str, params: tuple[Any, ...] = ()) -> Any | None:
        del query, params
        return None

    def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[Any]:
        del query, params
        return []

    def execute(query: str, params: tuple[Any, ...] = ()) -> int:
        del params
        normalized = " ".join(query.strip().split()).upper()
        writes.append(normalized)
        return 0

    manager = _manager()
    monkeypatch.setattr(manager_mod, "fetch_one", fetch_one)
    monkeypatch.setattr(manager_mod, "fetch_all", fetch_all)
    monkeypatch.setattr(manager_mod, "execute", execute)
    monkeypatch.setattr(
        manager,
        "_database_health_payload",
        lambda: {"enabled": False, "ready": False, "reason": "test"},
    )
    monkeypatch.setattr(
        manager,
        "_object_storage_health_payload",
        lambda: {"enabled": False, "ready": False, "reason": "test"},
    )
    monkeypatch.setattr(manager, "_fetch_ollama_model_catalog", lambda **kwargs: {"items": []})
    monkeypatch.setattr(manager, "_global_secret_preview_state", lambda secret_key: (False, ""))

    assert manager.list_agents() == []
    assert manager.list_workspaces()["items"] == []
    assert manager.list_mcp_catalog() == []
    status = manager.get_onboarding_status()
    assert status["agents"] == []

    seed_writes = [
        query
        for query in writes
        if query.startswith(("INSERT", "UPDATE"))
        and any(
            table in query
            for table in (
                "CP_AGENT_DEFINITIONS",
                "CP_WORKSPACES",
                "CP_WORKSPACE_SQUADS",
                "CP_GLOBAL_SECTIONS",
                "CP_MCP_SERVER_CATALOG",
                "CP_PROVIDER_CONNECTIONS",
            )
        )
    ]
    assert seed_writes == []


def test_provider_connection_reads_are_virtual_until_saved(monkeypatch) -> None:
    writes: list[str] = []

    monkeypatch.setattr(manager_mod, "fetch_one", lambda *args, **kwargs: None)
    monkeypatch.setattr(manager_mod, "fetch_all", lambda *args, **kwargs: [])
    monkeypatch.setattr(manager_mod, "execute", lambda query, params=(): writes.append(query) or 0)

    manager = _manager()
    monkeypatch.setattr(manager, "_fetch_ollama_model_catalog", lambda **kwargs: {"items": []})
    monkeypatch.setattr(manager, "_global_secret_preview_state", lambda secret_key: (False, ""))

    connection = manager.get_provider_connection("claude")

    assert connection["provider_id"] == "claude"
    assert connection["configured"] is False
    assert connection["verified"] is False
    assert writes == []
