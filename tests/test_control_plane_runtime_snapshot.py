"""Focused tests for canonical runtime snapshot prompt injection."""

from __future__ import annotations


def test_runtime_snapshot_exports_only_compiled_prompt_contract(monkeypatch):
    import koda.control_plane.manager as manager_mod

    manager = object.__new__(manager_mod.ControlPlaneManager)
    docs = {
        "identity_md": "# Identity",
        "soul_md": "# Soul",
        "system_prompt_md": "# System",
        "instructions_md": "# Instructions",
        "rules_md": "# Rules",
    }
    expected_prompt = manager_mod._compose_agent_prompt(docs)

    monkeypatch.delenv("AGENT_ID", raising=False)

    manager.get_published_snapshot = lambda agent_id, version=None: {  # type: ignore[attr-defined]
        "env": {},
        "agent": {"runtime_endpoint": {}},
        "sections": {},
        "skills": [],
        "templates": [],
        "secrets": {},
    }
    manager.publish_agent = lambda agent_id: {"version": 7}  # type: ignore[attr-defined]
    manager._snapshot_version = lambda agent_id, snapshot: 7  # type: ignore[attr-defined]
    manager._merged_global_env = lambda: {}  # type: ignore[attr-defined]
    manager._provider_connection_env = lambda: {}  # type: ignore[attr-defined]
    manager.get_agent_spec = lambda agent_id, snapshot=None: {"documents": docs}  # type: ignore[attr-defined]
    manager._general_ui_meta = lambda sections=None: {}  # type: ignore[attr-defined]
    manager._system_settings_sections = lambda: {}  # type: ignore[attr-defined]
    manager._bool_from_env = lambda env, key, default=False: default  # type: ignore[attr-defined]
    manager._scoped_env = lambda agent_id, env: dict(env)  # type: ignore[attr-defined]

    snapshot = manager._resolve_runtime_snapshot("agent_a")

    assert snapshot.agent_id == "AGENT_A"
    assert snapshot.version == 7
    assert snapshot.persisted_to_disk is False
    assert snapshot.env["AGENT_COMPILED_PROMPT_TEXT"] == expected_prompt


def test_legacy_agent_discovery_uses_env_only(monkeypatch):
    import koda.control_plane.manager as manager_mod

    manager = object.__new__(manager_mod.ControlPlaneManager)

    monkeypatch.setenv("AGENT_ID", "agent_b")

    discovered = manager._discover_legacy_agent_ids(
        {
            "AGENT_A_AGENT_TOKEN": "token-a",
            "AGENT_B_DEFAULT_PROVIDER": "claude",
            "IGNORED_KEY": "value",
        }
    )

    assert discovered == ["AGENT_A"]

    monkeypatch.delenv("AGENT_ID", raising=False)
    assert manager._discover_legacy_agent_ids({}) == []
