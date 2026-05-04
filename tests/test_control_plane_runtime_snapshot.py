"""Focused tests for canonical runtime snapshot prompt injection."""

from __future__ import annotations

from pathlib import Path

import pytest


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
        "provider_runtime_eligibility": {
            "claude": {"eligible": True, "reason": "verified"},
        },
    }
    manager.publish_agent = lambda agent_id: {"version": 7}  # type: ignore[attr-defined]
    manager._snapshot_version = lambda agent_id, snapshot: 7  # type: ignore[attr-defined]
    manager._merged_global_env = lambda: {}  # type: ignore[attr-defined]
    manager._provider_connection_env = lambda: {}  # type: ignore[attr-defined]
    manager.get_agent_spec = lambda agent_id, snapshot=None: {  # type: ignore[attr-defined]
        "documents": docs,
        "resource_access_policy": {
            "integration_grants": {
                "gws": {"allow_actions": ["gmail.list"]},
            }
        },
    }
    manager._general_ui_meta = lambda sections=None: {}  # type: ignore[attr-defined]
    manager._system_settings_sections = lambda: {}  # type: ignore[attr-defined]
    manager._bool_from_env = lambda env, key, default=False: default  # type: ignore[attr-defined]
    manager._scoped_env = lambda agent_id, env: dict(env)  # type: ignore[attr-defined]
    monkeypatch.setattr(
        manager_mod,
        "kokoro_managed_voices_storage_path",
        lambda: Path("/tmp/kokoro-managed.bin"),
    )

    snapshot = manager._resolve_runtime_snapshot("agent_a")

    assert snapshot.agent_id == "AGENT_A"
    assert snapshot.version == 7
    assert snapshot.persisted_to_disk is False
    assert snapshot.env["KOKORO_VOICES_PATH"] == "/tmp/kokoro-managed.bin"
    assert snapshot.env["AGENT_COMPILED_PROMPT_TEXT"] == expected_prompt
    assert "AGENT_RESOURCE_ACCESS_POLICY_JSON" not in snapshot.env
    assert "AGENT_PROVIDER_RUNTIME_ELIGIBILITY_JSON" in snapshot.env
    assert '"claude"' in snapshot.env["AGENT_PROVIDER_RUNTIME_ELIGIBILITY_JSON"]
    assert "SKILLS_JSON" not in snapshot.env


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


def test_runtime_snapshot_propagates_health_port_to_process_env(monkeypatch):
    """The worker reads HEALTH_PORT from env; the supervisor polls the URL
    from runtime.health_url. If the two disagree the supervisor's idle-check
    never succeeds and graceful version-bump restarts don't fire.

    Regression: _resolve_runtime_snapshot used runtime_endpoint.health_port
    when composing the health_url but never wrote it back to ``env``, so the
    spawned worker fell back to config.HEALTH_PORT default (8080) while the
    supervisor polled 8223 (or whatever per-agent value the snapshot stored).
    """
    import koda.control_plane.manager as manager_mod

    manager = object.__new__(manager_mod.ControlPlaneManager)

    monkeypatch.delenv("AGENT_ID", raising=False)

    manager.get_published_snapshot = lambda agent_id, version=None: {  # type: ignore[attr-defined]
        "env": {},
        "agent": {"runtime_endpoint": {"health_port": 8223}},
        "sections": {},
        "skills": [],
        "templates": [],
        "secrets": {},
    }
    manager.publish_agent = lambda agent_id: {"version": 1}  # type: ignore[attr-defined]
    manager._snapshot_version = lambda agent_id, snapshot: 1  # type: ignore[attr-defined]
    manager._merged_global_env = lambda: {}  # type: ignore[attr-defined]
    manager._provider_connection_env = lambda: {}  # type: ignore[attr-defined]
    manager.get_agent_spec = lambda agent_id, snapshot=None: {"documents": {}}  # type: ignore[attr-defined]
    manager._general_ui_meta = lambda sections=None: {}  # type: ignore[attr-defined]
    manager._system_settings_sections = lambda: {}  # type: ignore[attr-defined]
    manager._bool_from_env = lambda env, key, default=False: default  # type: ignore[attr-defined]
    manager._scoped_env = lambda agent_id, env: dict(env)  # type: ignore[attr-defined]
    monkeypatch.setattr(
        manager_mod,
        "kokoro_managed_voices_storage_path",
        lambda: Path("/tmp/kokoro-managed.bin"),
    )

    snapshot = manager._resolve_runtime_snapshot("agent_h")

    assert snapshot.health_url == "http://127.0.0.1:8223/health"
    assert snapshot.process_env.get("HEALTH_PORT") == "8223", (
        "HEALTH_PORT must be in process_env so the spawned worker binds the port the supervisor is polling."
    )


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


def test_runtime_prompt_preview_respects_execution_policy_allowlist():
    import koda.control_plane.manager as manager_mod

    payload = manager_mod._build_runtime_prompt_preview_payload(
        agent_id="ATLAS",
        agent_spec={
            "execution_policy": {
                "version": 1,
                "rules": [
                    {
                        "id": "allow-job-create",
                        "decision": "require_approval",
                        "selectors": {"tool_id": ["job_create"]},
                    }
                ],
            },
            "resource_access_policy": {
                "integration_grants": {
                    "mcp:atlassian": {"allow_actions": ["search_issues"]},
                }
            },
            "memory_policy": {},
            "knowledge_policy": {},
            "model_policy": {},
        },
        compiled_prompt="<agent_configuration_contract>\ncontract\n</agent_configuration_contract>",
    )

    compiled_prompt = str(payload.get("compiled_prompt") or "")
    assert "`job_create`" in compiled_prompt
    assert "## Integration Grants" in compiled_prompt
    assert "`mcp:atlassian`" in compiled_prompt


def test_runtime_access_uses_only_current_runtime_secret_key(monkeypatch):
    import koda.control_plane.manager as manager_mod
    import koda.control_plane.runtime_access as runtime_access_mod

    monkeypatch.delenv("RUNTIME_LOCAL_UI_TOKEN", raising=False)
    monkeypatch.delenv("ATLAS_RUNTIME_LOCAL_UI_TOKEN", raising=False)

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


def test_runtime_access_issues_request_token_from_bootstrap_env(monkeypatch):
    import koda.control_plane.manager as manager_mod
    import koda.control_plane.runtime_access as runtime_access_mod
    from koda.services.runtime_access_service import RuntimeAccessService

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
        "secrets": {},
        "sections": {},
    }

    monkeypatch.setattr(runtime_access_mod, "fetch_one", lambda *_args, **_kwargs: None)
    monkeypatch.delenv("ATLAS_RUNTIME_LOCAL_UI_TOKEN", raising=False)
    monkeypatch.setenv("RUNTIME_LOCAL_UI_TOKEN", "env-runtime-secret")

    payload = manager.get_runtime_access("atlas", capability="mutate")

    token = str(payload["runtime_request_token"])
    envelope = RuntimeAccessService("env-runtime-secret").authorize(
        token,
        agent_scope="ATLAS",
        capability="mutate",
    )
    assert payload["runtime_token"] is None
    assert payload["runtime_token_present"] is True
    assert envelope is not None


def test_runtime_access_prefers_agent_scoped_bootstrap_env(monkeypatch):
    import koda.control_plane.manager as manager_mod
    import koda.control_plane.runtime_access as runtime_access_mod
    from koda.services.runtime_access_service import RuntimeAccessService

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
        "secrets": {},
        "sections": {},
    }

    monkeypatch.setattr(runtime_access_mod, "fetch_one", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("RUNTIME_LOCAL_UI_TOKEN", "global-runtime-secret")
    monkeypatch.setenv("ATLAS_RUNTIME_LOCAL_UI_TOKEN", "scoped-runtime-secret")

    payload = manager.get_runtime_access("atlas")

    token = str(payload["runtime_request_token"])
    assert (
        RuntimeAccessService("scoped-runtime-secret").authorize(
            token,
            agent_scope="ATLAS",
            capability="read",
        )
        is not None
    )
    assert (
        RuntimeAccessService("global-runtime-secret").authorize(
            token,
            agent_scope="ATLAS",
            capability="read",
        )
        is None
    )


def test_removed_runtime_token_secret_is_not_visible_or_recreated():
    import koda.control_plane.manager as manager_mod

    manager = object.__new__(manager_mod.ControlPlaneManager)

    assert manager.get_global_secret_asset("RUNTIME_TOKEN") is None
    with pytest.raises(ValueError, match="RUNTIME_TOKEN is no longer supported"):
        manager.upsert_global_secret_asset("RUNTIME_TOKEN", {"value": "old-token"})


def test_reconcile_global_secret_classification_deletes_removed_runtime_token(monkeypatch):
    import koda.control_plane.manager as manager_mod

    manager = object.__new__(manager_mod.ControlPlaneManager)
    sections = {
        "access": {
            "global_secret_meta": {
                "RUNTIME_TOKEN": {"description": "old", "usage_scope": "system_only"},
                "OTHER_SECRET": {"description": "kept", "usage_scope": "agent_grant"},
            }
        }
    }
    deleted_ids: list[int] = []

    def fake_execute(query: str, params: tuple[object, ...] = ()) -> int:
        if "DELETE FROM cp_secret_values WHERE id = ?" in query:
            deleted_ids.append(int(params[0]))
        return 1

    monkeypatch.setattr(
        manager_mod,
        "fetch_all",
        lambda *_args, **_kwargs: [
            {"id": 7, "secret_key": "RUNTIME_TOKEN", "encrypted_value": "old-encrypted-token"},
            {"id": 8, "secret_key": "OTHER_SECRET", "encrypted_value": "kept-encrypted-token"},
        ],
    )
    monkeypatch.setattr(manager_mod, "execute", fake_execute)
    monkeypatch.setattr(manager, "_system_settings_sections", lambda: sections)
    monkeypatch.setattr(manager, "_persist_global_default_version", lambda _sections: 1)

    manager._reconcile_global_secret_classification()

    assert deleted_ids == [7]
    assert "RUNTIME_TOKEN" not in sections["access"]["global_secret_meta"]
    assert "OTHER_SECRET" in sections["access"]["global_secret_meta"]


def test_runtime_access_scope_includes_integration_grants():
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
        "secrets": {},
        "sections": {
            "knowledge": {"policy": {}},
            "access": {
                "resource_access_policy": {
                    "integration_grants": {
                        "browser": {
                            "allow_actions": ["navigate"],
                            "allowed_domains": ["example.com"],
                        }
                    }
                }
            },
        },
    }

    original_fetch_one = runtime_access_mod.fetch_one
    try:
        runtime_access_mod.fetch_one = lambda *_args, **_kwargs: None  # type: ignore[assignment]
        payload = manager.get_runtime_access("atlas")
    finally:
        runtime_access_mod.fetch_one = original_fetch_one  # type: ignore[assignment]

    assert payload["access_scope"]["integration_grants"] == {
        "browser": {
            "allow_actions": ["navigate"],
            "allowed_domains": ["example.com"],
        }
    }
