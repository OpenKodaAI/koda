"""Host-auth isolation checks for agent-scoped CORE execution."""

from __future__ import annotations


def test_tool_subprocess_env_ignores_host_core_auth_variables(monkeypatch):
    from koda.services.provider_env import build_tool_subprocess_env

    monkeypatch.setenv("GH_TOKEN", "host-gh-token")
    monkeypatch.setenv("AWS_PROFILE", "host-profile")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/host-google.json")
    monkeypatch.setenv("JIRA_API_TOKEN", "host-jira-token")

    env = build_tool_subprocess_env()

    assert "GH_TOKEN" not in env
    assert "AWS_PROFILE" not in env
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in env
    assert "JIRA_API_TOKEN" not in env


def test_agent_core_runtime_connection_does_not_fall_back_to_host_auth(monkeypatch):
    import koda.control_plane.manager as manager_mod

    manager = object.__new__(manager_mod.ControlPlaneManager)
    manager._require_agent_row = lambda agent_id: (  # type: ignore[attr-defined]
        "ATLAS",
        {"id": "ATLAS"},
    )
    manager._core_agent_connection_row = lambda agent_id, integration_id: None  # type: ignore[attr-defined]

    monkeypatch.setenv("GH_TOKEN", "host-gh-token")
    monkeypatch.setenv("AWS_PROFILE", "host-profile")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/host-google.json")
    monkeypatch.setenv("JIRA_API_TOKEN", "host-jira-token")

    assert manager.resolve_agent_core_runtime_connection("atlas", "gh") is None
    assert manager.resolve_agent_core_runtime_connection("atlas", "aws") is None
    assert manager.resolve_agent_core_runtime_connection("atlas", "gws") is None
    assert manager.resolve_agent_core_runtime_connection("atlas", "jira") is None


def test_runtime_snapshot_excludes_core_connection_auth_env(monkeypatch):
    import koda.control_plane.manager as manager_mod

    manager = object.__new__(manager_mod.ControlPlaneManager)
    docs = {
        "identity_md": "# Identity",
        "soul_md": "# Soul",
        "system_prompt_md": "# System",
        "instructions_md": "# Instructions",
        "rules_md": "# Rules",
    }

    manager.get_published_snapshot = lambda agent_id, version=None: {  # type: ignore[attr-defined]
        "process_env": {
            "PATH": "/usr/bin",
            "JIRA_URL": "https://jira.example.com",
            "AWS_DEFAULT_REGION": "us-east-1",
            "GWS_CREDENTIALS_FILE": "/tmp/creds.json",
        },
        "connection_refs": [
            {"connection_key": "core:jira", "kind": "core", "integration_key": "jira"},
        ],
        "agent": {"runtime_endpoint": {}},
        "sections": {},
        "skills": [],
        "templates": [],
        "secrets": {
            "JIRA_API_TOKEN": {"encrypted_value": "enc-jira"},
            "RUNTIME_LOCAL_UI_TOKEN": {"encrypted_value": "enc-runtime"},
        },
    }
    manager.publish_agent = lambda agent_id: {"version": 3}  # type: ignore[attr-defined]
    manager._snapshot_version = lambda agent_id, snapshot: 3  # type: ignore[attr-defined]
    manager.get_agent_spec = lambda agent_id, snapshot=None: {  # type: ignore[attr-defined]
        "documents": docs,
    }
    manager._general_ui_meta = lambda sections=None: {}  # type: ignore[attr-defined]
    manager._system_settings_sections = lambda: {}  # type: ignore[attr-defined]
    manager._bool_from_env = lambda env, key, default=False: default  # type: ignore[attr-defined]
    manager._scoped_env = lambda agent_id, env: dict(env)  # type: ignore[attr-defined]

    monkeypatch.setattr(manager_mod, "decrypt_secret", lambda value: f"decrypted:{value}")

    snapshot = manager._resolve_runtime_snapshot("atlas")

    assert "JIRA_URL" not in snapshot.process_env
    assert "AWS_DEFAULT_REGION" not in snapshot.process_env
    assert "GWS_CREDENTIALS_FILE" not in snapshot.process_env
    assert "JIRA_API_TOKEN" not in snapshot.process_env
    assert snapshot.process_env["RUNTIME_LOCAL_UI_TOKEN"] == "decrypted:enc-runtime"
    assert snapshot.connection_refs == [{"connection_key": "core:jira", "kind": "core", "integration_key": "jira"}]
