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


def test_runtime_prompt_preview_respects_agent_tool_policy():
    import koda.control_plane.manager as manager_mod

    payload = manager_mod._build_runtime_prompt_preview_payload(
        agent_id="ATLAS",
        agent_spec={
            "tool_policy": {
                "allowed_tool_ids": ["web_search", "fetch_url"],
            },
            "memory_policy": {},
            "knowledge_policy": {},
            "model_policy": {},
        },
        compiled_prompt="<agent_configuration_contract>\ncontract\n</agent_configuration_contract>",
    )

    compiled_prompt = str(payload.get("compiled_prompt") or "")
    assert "`web_search`" in compiled_prompt
    assert "`fetch_url`" in compiled_prompt
    assert "cron_list" not in compiled_prompt
    assert "browser_navigate" not in compiled_prompt


def test_runtime_access_ignores_legacy_runtime_token_secret():
    import koda.control_plane.manager as manager_mod
    import koda.control_plane.runtime_access as runtime_access_mod

    manager = object.__new__(manager_mod.ControlPlaneManager)
    manager._require_agent_row = lambda agent_id: (  # type: ignore[attr-defined]
        "ATLAS",
        {
            "id": "ATLAS",
            "applied_version": 0,
            "desired_version": 0,
            "workspace_id": "",
        },
    )
    manager.build_draft_snapshot = lambda agent_id: {  # type: ignore[attr-defined]
        "agent": {"runtime_endpoint": {}},
        "secrets": {
            "RUNTIME_TOKEN": {
                "encrypted_value": "legacy-token",
            }
        },
        "sections": {},
    }

    original_decrypt = runtime_access_mod.decrypt_secret
    original_fetch_one = runtime_access_mod.fetch_one
    try:
        runtime_access_mod.decrypt_secret = lambda value: f"decrypted:{value}"  # type: ignore[assignment]
        runtime_access_mod.fetch_one = lambda *_args, **_kwargs: None  # type: ignore[assignment]
        payload = manager.get_runtime_access("atlas")
    finally:
        runtime_access_mod.decrypt_secret = original_decrypt  # type: ignore[assignment]
        runtime_access_mod.fetch_one = original_fetch_one  # type: ignore[assignment]

    assert payload["runtime_token"] is None
    assert payload["runtime_token_present"] is False
    assert payload["runtime_request_token"] is None
    assert payload["access_scope_token"] is None


def test_runtime_access_issues_scoped_request_tokens_without_exposing_secret():
    import koda.control_plane.manager as manager_mod
    import koda.control_plane.runtime_access as runtime_access_mod

    manager = object.__new__(manager_mod.ControlPlaneManager)
    manager._require_agent_row = lambda agent_id: (  # type: ignore[attr-defined]
        "ATLAS",
        {
            "id": "ATLAS",
            "applied_version": 0,
            "desired_version": 0,
            "workspace_id": "workspace-a",
        },
    )
    manager.build_draft_snapshot = lambda agent_id: {  # type: ignore[attr-defined]
        "agent": {"runtime_endpoint": {}},
        "secrets": {
            "RUNTIME_LOCAL_UI_TOKEN": {
                "encrypted_value": "encrypted-runtime-token",
            }
        },
        "sections": {
            "knowledge": {
                "policy": {
                    "allowed_source_labels": ["policy:*"],
                }
            }
        },
    }

    original_decrypt = runtime_access_mod.decrypt_secret
    original_fetch_one = runtime_access_mod.fetch_one
    try:
        runtime_access_mod.decrypt_secret = lambda value: "decrypted-runtime-secret"  # type: ignore[assignment]
        runtime_access_mod.fetch_one = lambda *_args, **_kwargs: None  # type: ignore[assignment]
        payload = manager.get_runtime_access("atlas", capability="attach", include_sensitive=True)
    finally:
        runtime_access_mod.decrypt_secret = original_decrypt  # type: ignore[assignment]
        runtime_access_mod.fetch_one = original_fetch_one  # type: ignore[assignment]

    assert payload["runtime_token"] is None
    assert payload["runtime_token_present"] is True
    assert payload["runtime_request_capability"] == "attach"
    assert isinstance(payload["runtime_request_token"], str) and payload["runtime_request_token"]
    assert isinstance(payload["access_scope_token"], str) and payload["access_scope_token"]
