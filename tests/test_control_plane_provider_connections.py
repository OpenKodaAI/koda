"""Focused tests for provider connection lifecycle and catalog contracts."""

from __future__ import annotations

import contextlib
import json
import time
from types import SimpleNamespace
from typing import Any, cast

from koda.agent_contract import resolve_core_provider_catalog
from koda.provider_models import build_function_model_catalog
from koda.services.provider_auth import (
    MANAGED_PROVIDER_IDS,
    PROVIDER_API_KEY_ENV_KEYS,
    ProviderLoginSessionState,
    ProviderVerificationResult,
    provider_login_command,
)


def _build_provider_catalog() -> dict[str, dict[str, object]]:
    catalog = {}
    for item in resolve_core_provider_catalog():
        catalog[str(item["id"])] = {
            **item,
            "enabled": True,
            "command_present": True,
            "available_models": [],
            "default_model": "",
        }
    return catalog


def _make_manager(monkeypatch):
    import koda.control_plane.manager as manager_mod

    manager = object.__new__(manager_mod.ControlPlaneManager)
    catalog = _build_provider_catalog()
    rows = {
        provider_id: {
            "auth_mode": "api_key"
            if provider_id == "elevenlabs"
            else "local"
            if provider_id == "ollama"
            else "subscription_login",
            "configured": 0,
            "verified": 0,
            "account_label": "",
            "plan_label": "",
            "project_id": "",
            "last_verified_at": "",
            "last_error": "",
        }
        for provider_id in MANAGED_PROVIDER_IDS
    }
    meta: dict[str, dict[str, str]] = {"ollama": {"base_url": ""}}
    secrets: dict[str, str] = {}
    login_sessions: dict[str, ProviderLoginSessionState] = {}

    manager._provider_login_processes = {}
    manager.ensure_seeded = lambda: None  # type: ignore[attr-defined]
    manager._merged_global_env = lambda: {}  # type: ignore[attr-defined]
    manager._merged_global_env_base = lambda: {}  # type: ignore[attr-defined]
    manager._provider_auth_work_dir = lambda provider_id: "/tmp"  # type: ignore[attr-defined]
    manager._provider_catalog_from_env = lambda env: {"providers": catalog}  # type: ignore[attr-defined]
    manager.list_mcp_catalog = lambda: []  # type: ignore[attr-defined]
    manager._provider_connection_row = lambda provider_id: rows[provider_id]  # type: ignore[attr-defined]
    manager._persist_provider_connection_row = (  # type: ignore[attr-defined]
        lambda provider_id, **payload: rows[provider_id].update(payload)
    )
    manager._persist_provider_connection_meta = (  # type: ignore[attr-defined]
        lambda provider_id, **payload: meta.setdefault(provider_id, {}).update(
            {key: str(value) for key, value in payload.items() if value is not None}
        )
    )
    manager._provider_api_key_secret_value = lambda provider_id: secrets.get(provider_id, "")  # type: ignore[attr-defined]
    manager._global_secret_preview_state = (  # type: ignore[attr-defined]
        lambda env_key: (
            any(
                PROVIDER_API_KEY_ENV_KEYS[provider_id] == env_key and bool(secrets.get(provider_id))
                for provider_id in secrets
            ),
            "sk-***"
            if any(
                PROVIDER_API_KEY_ENV_KEYS[provider_id] == env_key and bool(secrets.get(provider_id))
                for provider_id in secrets
            )
            else "",
        )
    )
    manager.upsert_global_secret_asset = (  # type: ignore[attr-defined]
        lambda env_key, payload, persist_sections=True: secrets.__setitem__(
            next(provider_id for provider_id, key in PROVIDER_API_KEY_ENV_KEYS.items() if key == env_key),
            str(payload["value"]),
        )
    )
    manager.delete_global_secret_asset = (  # type: ignore[attr-defined]
        lambda env_key, persist_sections=True: secrets.pop(
            next(provider_id for provider_id, key in PROVIDER_API_KEY_ENV_KEYS.items() if key == env_key),
            None,
        )
    )
    manager._resolve_ollama_base_url = (  # type: ignore[attr-defined]
        lambda auth_mode, env=None: str(
            (env or {}).get("OLLAMA_BASE_URL") or meta.get("ollama", {}).get("base_url") or "http://localhost:11434"
        )
    )
    manager._persist_provider_login_session = (  # type: ignore[attr-defined]
        lambda state: login_sessions.__setitem__(state.session_id, state)
    )
    manager.get_provider_login_session = (  # type: ignore[attr-defined]
        lambda provider_id, session_id: manager_mod.ControlPlaneManager._provider_login_session_dict(
            manager, login_sessions[session_id]
        )
    )
    # Required by _mark_provider_enabled after successful verification:
    # tests that don't care about the enabled-flag still need these stubs
    # so verify_provider_connection doesn't crash.
    manager._system_settings_sections = lambda: {"providers": {}}  # type: ignore[attr-defined]
    manager._persist_global_sections = lambda sections: 1  # type: ignore[attr-defined]

    monkeypatch.setattr(
        manager_mod, "provider_command_present", lambda provider_id, base_env=None: provider_id != "gemini"
    )
    monkeypatch.setattr(manager_mod, "fetch_one", lambda *args, **kwargs: None)
    monkeypatch.setattr(manager_mod, "execute", lambda *args, **kwargs: None)

    return manager, rows, meta, secrets, login_sessions


def test_core_provider_catalog_exposes_connection_flags_and_hides_sora():
    catalog = {item["id"]: item for item in resolve_core_provider_catalog()}

    assert catalog["ollama"]["supports_local_connection"] is True
    assert catalog["ollama"]["connection_managed"] is True
    assert catalog["claude"]["connection_managed"] is True
    assert catalog["kokoro"]["connection_managed"] is False
    assert catalog["sora"]["show_in_settings"] is False


def test_function_model_catalog_skips_hidden_standalone_providers():
    catalog = _build_provider_catalog()

    functional_catalog = build_function_model_catalog(catalog)

    assert all(item["provider_id"] != "sora" for item in functional_catalog["video"])


def test_verify_provider_connection_flips_enabled_flag(monkeypatch):
    """Successful verification must mark ``{provider}_enabled=true`` so
    subsequent ``put_general_system_settings`` saves don't reject the
    provider with ``must_be_enabled`` even though the UI shows the check."""
    import koda.control_plane.manager as manager_mod

    manager, _rows, _meta, _secrets, _sessions = _make_manager(monkeypatch)
    sections_store: dict[str, dict[str, object]] = {"providers": {}}
    manager._system_settings_sections = lambda: sections_store  # type: ignore[attr-defined]

    persisted: list[dict[str, dict[str, object]]] = []

    def _fake_persist(sections):
        persisted.append(sections)
        for section, payload in sections.items():
            sections_store.setdefault(section, {}).update(payload)
        return 1

    manager._persist_global_sections = _fake_persist  # type: ignore[attr-defined]
    monkeypatch.setattr(
        manager_mod,
        "verify_provider_api_key",
        lambda provider_id, api_key, project_id="", base_url="": ProviderVerificationResult(
            provider_id=provider_id,
            auth_mode="api_key",
            verified=True,
            account_label="Workspace",
            checked_via="api_key",
        ),
    )
    # Seed credential so verify has something to check
    manager_mod.ControlPlaneManager.put_provider_api_key_connection(manager, "claude", {"api_key": "sk-claude"})
    sections_store["providers"] = {}  # reset after put to isolate verify effect

    manager_mod.ControlPlaneManager.verify_provider_connection(manager, "claude")

    assert sections_store["providers"].get("claude_enabled") is True
    assert any("providers" in payload for payload in persisted)


def test_api_key_provider_round_trip_resets_to_local(monkeypatch):
    import koda.control_plane.manager as manager_mod

    manager, _rows, _meta, secrets, _sessions = _make_manager(monkeypatch)
    manager._system_settings_sections = lambda: {"providers": {}}  # type: ignore[attr-defined]
    manager._persist_global_sections = lambda sections: 1  # type: ignore[attr-defined]
    monkeypatch.setattr(
        manager_mod,
        "verify_provider_api_key",
        lambda provider_id, api_key, project_id="", base_url="": ProviderVerificationResult(
            provider_id=provider_id,
            auth_mode="api_key",
            verified=bool(api_key),
            account_label="Workspace",
            checked_via="api_key",
            details={"provider": provider_id},
        ),
    )
    monkeypatch.setattr(manager_mod, "run_provider_logout", lambda provider_id, base_env=None, work_dir="": (True, ""))

    connection = manager_mod.ControlPlaneManager.put_provider_api_key_connection(
        manager,
        "claude",
        {"api_key": "sk-claude"},
    )
    assert connection["auth_mode"] == "api_key"
    assert connection["configured"] is True
    assert connection["connection_managed"] is True
    assert secrets["claude"] == "sk-claude"

    verification = manager_mod.ControlPlaneManager.verify_provider_connection(manager, "claude")
    assert verification["connection"]["verified"] is True
    assert verification["verification"]["checked_via"] == "api_key"
    assert verification["verification"]["auth_expired"] is False
    assert verification["verification"]["details"] == {"provider": "claude"}

    disconnected = manager_mod.ControlPlaneManager.disconnect_provider_connection(manager, "claude")
    # After disconnect Claude falls back to ``local`` — a neutral baseline
    # that doesn't assume the operator wants to start a new subscription
    # flow. From there the wizard offers API key, subscription (``claude
    # setup-token``) or pure local detection.
    assert disconnected["connection"]["auth_mode"] == "local"
    assert disconnected["connection"]["configured"] is False
    assert disconnected["connection"]["verified"] is False
    assert "claude" not in secrets


def test_ollama_local_connection_round_trip_preserves_local_mode(monkeypatch):
    import koda.control_plane.manager as manager_mod

    manager, _rows, meta, _secrets, _sessions = _make_manager(monkeypatch)
    monkeypatch.setattr(
        manager_mod,
        "verify_provider_local_connection",
        lambda provider_id, base_url="", base_env=None, work_dir=None: ProviderVerificationResult(
            provider_id=provider_id,
            auth_mode="local",
            verified=base_url == "http://127.0.0.1:11434",
            account_label="Local daemon",
            checked_via="tcp_probe",
            last_error="" if base_url == "http://127.0.0.1:11434" else "unreachable",
        ),
    )
    monkeypatch.setattr(
        manager_mod,
        "run_provider_logout",
        lambda provider_id, base_env=None, work_dir="": (False, "logout not supported"),
    )

    connection = manager_mod.ControlPlaneManager.put_provider_local_connection(
        manager,
        "ollama",
        {"base_url": "http://127.0.0.1:11434"},
    )
    assert connection["auth_mode"] == "local"
    assert connection["supports_local_connection"] is True
    assert connection["connection_status"] == "configured"
    assert meta["ollama"]["base_url"] == "http://127.0.0.1:11434"

    verification = manager_mod.ControlPlaneManager.verify_provider_connection(manager, "ollama")
    assert verification["connection"]["verified"] is True
    assert verification["connection"]["base_url"] == "http://127.0.0.1:11434"
    assert verification["verification"]["checked_via"] == "tcp_probe"

    disconnected = manager_mod.ControlPlaneManager.disconnect_provider_connection(manager, "ollama")
    assert disconnected["connection"]["auth_mode"] == "local"
    assert disconnected["connection"]["verified"] is False
    assert disconnected["connection"]["base_url"] == "http://127.0.0.1:11434"


def test_postgres_is_not_exposed_as_native_core_integration(monkeypatch):
    import koda.control_plane.manager as manager_mod

    manager, _rows, _meta, _secrets, _sessions = _make_manager(monkeypatch)
    payload = manager_mod.ControlPlaneManager.list_connection_catalog(manager)

    assert all(item["integration_key"] != "postgres" for item in payload["items"] if item.get("kind") == "core")


def test_browser_connection_default_round_trip_and_system_toggle_do_not_depend_on_provider_validation(monkeypatch):
    import koda.control_plane.manager as manager_mod

    manager, _rows, _meta, _secrets, _sessions = _make_manager(monkeypatch)
    integration_rows: dict[str, dict[str, object]] = {}
    persisted_sections: dict[str, dict[str, object]] = {}

    def persist_integration_row(integration_id: str, **payload):
        integration_rows[integration_id] = {
            "auth_mode": payload.get("auth_mode", "none"),
            "configured": bool(payload.get("configured")),
            "verified": bool(payload.get("verified")),
            "account_label": payload.get("account_label", ""),
            "last_verified_at": payload.get("last_verified_at", ""),
            "last_error": payload.get("last_error", ""),
            "auth_expired": bool(payload.get("auth_expired")),
            "checked_via": payload.get("checked_via", ""),
            "metadata": dict(payload.get("metadata") or {}),
        }

    def fake_fetch_one(query, params=()):
        if "FROM cp_connection_defaults" not in query:
            return None
        connection_key = str(params[0]) if params else ""
        integration_id = connection_key.removeprefix("core:")
        row = integration_rows.get(integration_id)
        if row is None:
            return None
        return {
            "connection_key": connection_key,
            "kind": "core",
            "integration_key": integration_id,
            "auth_method": str(row.get("auth_mode") or "none"),
            "configured": 1 if row.get("configured") else 0,
            "verified": 1 if row.get("verified") else 0,
            "account_label": str(row.get("account_label") or ""),
            "provider_account_id": str(row.get("provider_account_id") or ""),
            "expires_at": str(row.get("expires_at") or ""),
            "source_origin": "system_default",
            "last_verified_at": str(row.get("last_verified_at") or ""),
            "last_error": str(row.get("last_error") or ""),
            "auth_expired": 1 if row.get("auth_expired") else 0,
            "checked_via": str(row.get("checked_via") or ""),
            "metadata_json": json.dumps(row.get("metadata") or {}),
        }

    manager.get_system_settings = lambda: {  # type: ignore[attr-defined]
        "integrations": {"browser_enabled": False},
        "general": {},
        "scheduler": {},
        "providers": {},
        "tools": {},
        "memory": {},
        "knowledge": {},
        "shared_variables": [],
        "additional_env_vars": [],
    }
    manager._integration_fields_payload = lambda integration_id: []  # type: ignore[attr-defined]
    manager._persist_integration_connection_row = persist_integration_row  # type: ignore[attr-defined]
    manager._record_integration_health_check = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    manager._apply_system_settings_to_sections = lambda payload: {  # type: ignore[attr-defined]
        "runtime": {
            "env": {
                "BROWSER_ENABLED": "true" if payload["integrations"]["browser_enabled"] else "false",
            }
        }
    }
    manager._persist_global_sections = lambda sections: persisted_sections.update(sections) or 1  # type: ignore[attr-defined]

    monkeypatch.setattr(manager_mod, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(manager_mod, "execute", lambda *args, **kwargs: None)

    connected = manager_mod.ControlPlaneManager.put_connection_default(manager, "core:browser", {})
    assert connected["connected"] is True
    assert connected["status"] == "configured"

    system_state = manager_mod.ControlPlaneManager.set_integration_system_enabled(manager, "browser", True)
    assert system_state["enabled"] is True
    assert persisted_sections["runtime"]["env"]["BROWSER_ENABLED"] == "true"

    disconnected = manager_mod.ControlPlaneManager.delete_connection_default(manager, "core:browser")
    assert disconnected["connection"]["connected"] is False
    assert disconnected["connection"]["status"] == "not_configured"


def test_jira_connection_default_persists_credentials_and_connection_default(monkeypatch):
    import koda.control_plane.manager as manager_mod

    manager, _rows, _meta, _secrets, _sessions = _make_manager(monkeypatch)
    integration_rows: dict[str, dict[str, object]] = {}
    persisted_sections: dict[str, dict[str, object]] = {section: {} for section in manager_mod.AGENT_SECTIONS}
    persisted_secrets: dict[str, str] = {}

    def fake_fetch_one(query, params=()):
        if "FROM cp_connection_defaults" not in query:
            return None
        connection_key = str(params[0]) if params else ""
        integration_id = connection_key.removeprefix("core:")
        row = integration_rows.get(integration_id)
        if row is None:
            return None
        return {
            "connection_key": connection_key,
            "kind": "core",
            "integration_key": integration_id,
            "auth_method": str(row.get("auth_mode") or "none"),
            "configured": 1 if row.get("configured") else 0,
            "verified": 1 if row.get("verified") else 0,
            "account_label": str(row.get("account_label") or ""),
            "provider_account_id": str(row.get("provider_account_id") or ""),
            "expires_at": str(row.get("expires_at") or ""),
            "source_origin": "system_default",
            "last_verified_at": str(row.get("last_verified_at") or ""),
            "last_error": str(row.get("last_error") or ""),
            "auth_expired": 1 if row.get("auth_expired") else 0,
            "checked_via": str(row.get("checked_via") or ""),
            "metadata_json": json.dumps(row.get("metadata") or {}),
        }

    def fake_execute(query, params=()):
        if "INSERT INTO cp_connection_defaults" not in query:
            return None
        integration_rows[str(params[2])] = {
            "auth_mode": str(params[3]),
            "configured": bool(params[4]),
            "verified": bool(params[5]),
            "account_label": str(params[6]),
            "provider_account_id": str(params[7]),
            "expires_at": str(params[8]),
            "last_verified_at": str(params[10]),
            "last_error": str(params[11]),
            "auth_expired": bool(params[12]),
            "checked_via": str(params[13]),
            "metadata": json.loads(str(params[14]) or "{}"),
        }
        return None

    manager._provider_connection_env = lambda: {}  # type: ignore[attr-defined]
    manager._merged_global_env_base = (  # type: ignore[attr-defined]
        lambda: manager_mod.ControlPlaneManager._merged_global_env_base(manager)
    )
    manager._merged_global_env = lambda: manager_mod.ControlPlaneManager._merged_global_env(manager)  # type: ignore[attr-defined]
    manager._load_global_sections = lambda: json.loads(json.dumps(persisted_sections))  # type: ignore[attr-defined]
    manager._persist_global_sections = (  # type: ignore[attr-defined]
        lambda sections: persisted_sections.clear() or persisted_sections.update(json.loads(json.dumps(sections))) or 1
    )
    manager.upsert_global_secret_asset = (  # type: ignore[attr-defined]
        lambda secret_key, payload, persist_sections=False: (
            persisted_secrets.__setitem__(
                secret_key,
                str(payload["value"]),
            )
            or {"secret_key": secret_key, "preview": "tok-***"}
        )
    )
    manager.delete_global_secret_asset = (  # type: ignore[attr-defined]
        lambda secret_key, persist_sections=False: persisted_secrets.pop(secret_key, None) is not None
    )
    manager._record_integration_health_check = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    manager.get_system_settings = lambda: {  # type: ignore[attr-defined]
        "integrations": {"jira_enabled": True},
        "general": {},
        "scheduler": {},
        "providers": {},
        "tools": {},
        "memory": {},
        "knowledge": {},
        "shared_variables": [],
        "additional_env_vars": [],
    }
    manager._integration_configured = (  # type: ignore[attr-defined]
        lambda integration_id: (
            (
                integration_id == "jira"
                and bool(persisted_sections["integrations"].get("env", {}).get("JIRA_URL"))
                and bool(persisted_sections["integrations"].get("env", {}).get("JIRA_USERNAME"))
                and bool(persisted_secrets.get("JIRA_API_TOKEN"))
            )
            or integration_id == "browser"
        )
    )

    monkeypatch.setattr(manager_mod, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(manager_mod, "execute", fake_execute)
    monkeypatch.setattr(
        manager_mod.ControlPlaneManager,
        "_global_secret_value",
        lambda self, secret_key: persisted_secrets.get(secret_key, ""),
    )
    monkeypatch.setattr(
        manager_mod.ControlPlaneManager,
        "_global_secret_preview_state",
        lambda self, secret_key: (
            bool(persisted_secrets.get(secret_key)),
            "tok-***" if persisted_secrets.get(secret_key) else "",
        ),
    )
    monkeypatch.setattr(
        manager_mod.ControlPlaneManager,
        "_verify_integration_configuration",
        lambda self, integration_id: {
            "verified": True,
            "account_label": "Ada Lovelace",
            "last_error": "",
            "checked_via": "jira_myself",
            "auth_expired": False,
            "details": {"account": "ada@example.com"},
        },
    )

    connected = manager_mod.ControlPlaneManager.put_connection_default(
        manager,
        "core:jira",
        {
            "fields": [
                {"key": "JIRA_URL", "value": "https://example.atlassian.net"},
                {"key": "JIRA_USERNAME", "value": "ada@example.com"},
                {"key": "JIRA_API_TOKEN", "value": "jira-token"},
            ]
        },
    )
    assert connected["connected"] is True
    assert connected["auth_method"] == "api_token"
    assert connected["status"] == "configured"
    assert persisted_sections["integrations"]["env"]["JIRA_URL"] == "https://example.atlassian.net"
    assert persisted_sections["integrations"]["env"]["JIRA_USERNAME"] == "ada@example.com"
    assert persisted_secrets["JIRA_API_TOKEN"] == "jira-token"

    verified = manager_mod.ControlPlaneManager.verify_connection_default(manager, "core:jira")
    assert verified["connection"]["metadata"]["verified"] is True
    assert verified["connection"]["auth_method"] == "api_token"
    assert verified["verification"]["checked_via"] == "jira_myself"

    default_connection = manager_mod.ControlPlaneManager.get_connection_default(manager, "core:jira")
    assert default_connection["connected"] is True
    assert default_connection["account_label"] == "Ada Lovelace"
    assert default_connection["status"] == "verified"

    disconnected = manager_mod.ControlPlaneManager.delete_connection_default(manager, "core:jira")
    assert disconnected["connection"]["connected"] is False
    assert disconnected["connection"]["status"] == "not_configured"
    assert "JIRA_API_TOKEN" not in persisted_secrets
    assert "JIRA_URL" not in persisted_sections["integrations"].get("env", {})
    assert "JIRA_USERNAME" not in persisted_sections["integrations"].get("env", {})


def test_import_agent_connection_default_copies_system_credentials_into_agent_binding(monkeypatch):
    import koda.control_plane.manager as manager_mod

    manager, _rows, _meta, _secrets, _sessions = _make_manager(monkeypatch)
    captured_fields: list[dict[str, object]] = []
    persisted_row: dict[str, object] = {}

    manager._require_agent_row = lambda agent_id: ("ATLAS", {"id": "ATLAS"})  # type: ignore[attr-defined]
    manager._integration_connection_row = lambda integration_id: (
        {  # type: ignore[attr-defined]
            "configured": 1,
            "auth_method": "api_token",
            "metadata_json": "{}",
        }
        if integration_id == "jira"
        else None
    )
    manager._system_settings_sections = lambda: {  # type: ignore[attr-defined]
        "integrations": {
            "env": {
                "JIRA_URL": "https://example.atlassian.net",
                "JIRA_USERNAME": "ada@example.com",
            }
        }
    }

    def persist_fields(agent_id: str, integration_id: str, payload_fields: list[dict[str, object]]):
        del agent_id, integration_id
        captured_fields.extend(payload_fields)
        return {
            "JIRA_URL": "https://example.atlassian.net",
            "JIRA_USERNAME": "ada@example.com",
        }

    manager._persist_agent_core_connection_fields = persist_fields  # type: ignore[attr-defined]
    manager._resolve_agent_core_auth_method = (  # type: ignore[attr-defined]
        lambda agent_id, integration_id, requested_auth_method=None: "api_token"
    )
    manager._agent_core_connection_configured = lambda agent_id, integration_id: True  # type: ignore[attr-defined]
    manager._persist_core_agent_connection_row = (  # type: ignore[attr-defined]
        lambda agent_id, integration_id, **payload: persisted_row.update(
            {"agent_id": agent_id, "integration_id": integration_id, **payload}
        )
    )
    manager._serialize_agent_core_connection_payload = lambda agent_id, integration_id: {  # type: ignore[attr-defined]
        "connection_key": "core:jira",
        "kind": "core",
        "integration_key": integration_id,
        "auth_method": "api_token",
        "source_origin": "imported_default",
        "status": "configured",
        "connected": True,
    }

    monkeypatch.setattr(
        manager_mod,
        "fetch_one",
        lambda query, params=(): {"encrypted_value": "enc-jira-token"} if "cp_secret_values" in query else None,
    )
    monkeypatch.setattr(
        manager_mod,
        "decrypt_secret",
        lambda value: "jira-token" if value == "enc-jira-token" else str(value),
    )

    result = manager_mod.ControlPlaneManager.import_agent_connection_default(
        manager,
        "atlas",
        "core:jira",
    )

    assert captured_fields == [
        {"key": "JIRA_URL", "value": "https://example.atlassian.net"},
        {"key": "JIRA_USERNAME", "value": "ada@example.com"},
        {"key": "JIRA_API_TOKEN", "value": "jira-token"},
    ]
    assert persisted_row["agent_id"] == "ATLAS"
    assert persisted_row["integration_id"] == "jira"
    assert persisted_row["auth_method"] == "api_token"
    assert persisted_row["source_origin"] == "imported_default"
    assert persisted_row["enabled"] is True
    assert persisted_row["configured"] is True
    assert result["connection"]["connection_key"] == "core:jira"
    assert result["connection"]["source_origin"] == "imported_default"


def test_verify_agent_connection_persists_verified_state_for_core_binding(monkeypatch):
    import koda.control_plane.manager as manager_mod

    manager, _rows, _meta, _secrets, _sessions = _make_manager(monkeypatch)
    persisted_row: dict[str, object] = {}

    manager._require_agent_row = lambda agent_id: ("ATLAS", {"id": "ATLAS"})  # type: ignore[attr-defined]
    manager._core_agent_connection_row = lambda agent_id, integration_id: {  # type: ignore[attr-defined]
        "enabled": 1,
        "source_origin": "imported_default",
        "metadata_json": json.dumps({"seed": "default"}),
    }
    manager._verify_agent_core_connection_configuration = (  # type: ignore[attr-defined]
        lambda agent_id, integration_id: {
            "verified": True,
            "account_label": "Ada Lovelace",
            "last_error": "",
            "checked_via": "jira_myself",
            "auth_expired": False,
            "details": {
                "account": "ada@example.com",
                "provider_account_id": "ada@example.com",
            },
        }
    )
    manager._resolve_agent_core_auth_method = lambda agent_id, integration_id: "api_token"  # type: ignore[attr-defined]
    manager._agent_core_connection_configured = lambda agent_id, integration_id: True  # type: ignore[attr-defined]
    manager._agent_core_connection_config = lambda agent_id, integration_id: {  # type: ignore[attr-defined]
        "JIRA_URL": "https://example.atlassian.net",
        "JIRA_USERNAME": "ada@example.com",
    }
    manager._persist_core_agent_connection_row = (  # type: ignore[attr-defined]
        lambda agent_id, integration_id, **payload: persisted_row.update(
            {"agent_id": agent_id, "integration_id": integration_id, **payload}
        )
    )
    manager._serialize_agent_core_connection_payload = lambda agent_id, integration_id: {  # type: ignore[attr-defined]
        "connection_key": "core:jira",
        "kind": "core",
        "integration_key": integration_id,
        "auth_method": "api_token",
        "source_origin": "imported_default",
        "status": "verified",
        "connected": True,
    }

    result = manager_mod.ControlPlaneManager.verify_agent_connection(manager, "atlas", "core:jira")

    assert result["connection"]["connection_key"] == "core:jira"
    assert result["connection"]["status"] == "verified"
    assert result["verification"]["checked_via"] == "jira_myself"
    assert persisted_row["agent_id"] == "ATLAS"
    assert persisted_row["integration_id"] == "jira"
    assert persisted_row["source_origin"] == "imported_default"
    assert persisted_row["account_label"] == "Ada Lovelace"
    assert persisted_row["provider_account_id"] == "ada@example.com"
    assert persisted_row["verified"] is True
    assert persisted_row["enabled"] is True
    assert persisted_row["metadata"]["seed"] == "default"
    assert persisted_row["metadata"]["account"] == "ada@example.com"


def test_start_provider_login_tracks_session_and_disconnect_cancels_it(monkeypatch):
    import koda.control_plane.manager as manager_mod

    manager, _rows, _meta, _secrets, login_sessions = _make_manager(monkeypatch)
    process = SimpleNamespace(
        provider_id="codex", command=("codex", "login"), normalized_output=lambda: "", terminate=lambda: None
    )
    session = ProviderLoginSessionState(
        session_id="sess-1",
        provider_id="codex",
        auth_mode="subscription_login",
        status="awaiting_browser",
        command="codex login --device-auth",
        auth_url="https://example.com/auth",
        user_code="ABCD-EFGH",
        message="Open browser",
    )
    monkeypatch.setattr(
        manager_mod,
        "start_login_process",
        lambda provider_id, project_id="", base_env=None, work_dir="": (process, session),
    )

    def fake_sync_provider_login_session(provider_id, session_id):
        return manager_mod.ControlPlaneManager._provider_login_session_dict(
            manager,
            login_sessions[session_id],
        )

    manager._sync_provider_login_session = fake_sync_provider_login_session  # type: ignore[attr-defined]
    monkeypatch.setattr(manager_mod, "run_provider_logout", lambda provider_id, base_env=None, work_dir="": (True, ""))

    started = manager_mod.ControlPlaneManager.start_provider_login(manager, "codex", {})
    assert started["connection"]["auth_mode"] == "subscription_login"
    assert started["login_session"]["status"] == "awaiting_browser"
    assert manager._provider_login_processes["sess-1"] is process

    reauthed = manager_mod.ControlPlaneManager.reauth_provider_connection(manager, "codex", {})
    assert reauthed["connection"]["auth_mode"] == "subscription_login"
    assert reauthed["login_session"]["status"] == "awaiting_browser"

    disconnected = manager_mod.ControlPlaneManager.disconnect_provider_connection(manager, "codex")
    assert disconnected["connection"]["auth_mode"] == "subscription_login"
    assert login_sessions["sess-1"].status == "cancelled"


def test_submit_provider_login_code_rejects_oversized_payload(monkeypatch):
    """Authorization codes fit in under 200 chars; anything significantly
    longer is a paste mishap or an abuse attempt against the subprocess
    stdin buffer. The manager must reject oversized payloads before any
    bytes touch the live CLI process.
    """
    import koda.control_plane.manager as manager_mod

    manager, _rows, _meta, _secrets, login_sessions = _make_manager(monkeypatch)

    written_chunks: list[str] = []
    handle = SimpleNamespace(
        provider_id="claude",
        command=("claude", "setup-token"),
        write=lambda text: written_chunks.append(text),
        process=SimpleNamespace(poll=lambda: None),
    )
    manager._provider_login_processes["sess-claude"] = handle
    manager._sync_provider_login_session = lambda provider_id, session_id: {  # type: ignore[attr-defined]
        "session_id": session_id,
        "status": "completed",
    }

    oversized = "A" * 1024
    try:
        manager_mod.ControlPlaneManager.submit_provider_login_code(
            manager,
            "claude",
            "sess-claude",
            {"code": oversized},
        )
    except ValueError as exc:
        assert "too long" in str(exc)
    else:  # pragma: no cover - failure path
        raise AssertionError("submit_provider_login_code should have rejected the oversized payload")

    # The payload must never have been written to the subprocess stdin.
    assert written_chunks == []


def test_submit_provider_login_code_short_circuits_on_oauth_error_line(monkeypatch):
    """When the CLI prints an ``OAuth error:`` line (Anthropic rejected the
    code), the submit loop must return immediately — continuing to sleep
    until the deadline blocks the HTTP response and leaves the spinner on
    screen for several extra seconds, even though the outcome is already
    known.
    """
    import koda.control_plane.manager as manager_mod

    manager, _rows, _meta, _secrets, _login_sessions = _make_manager(monkeypatch)
    # Keep the deadline high so we can prove the short-circuit is what ends
    # the loop, not the deadline timeout.
    manager_mod.ControlPlaneManager._PROVIDER_LOGIN_SUBMIT_DEADLINE_SECONDS = 30.0

    # Simulate the CLI printing the error line only on the third output read.
    outputs = iter(
        [
            "Paste code here if prompted>\n",
            "Paste code here if prompted>\n*****TEST*****\n",
            (
                "Paste code here if prompted>\n*****TEST*****\n"
                "OAuth error: Request failed with status code 400\n"
                "Press Enter to retry.\n"
            ),
        ]
    )
    current_output = [""]

    def fake_output():
        with contextlib.suppress(StopIteration):
            current_output[0] = next(outputs)
        return current_output[0]

    handle = SimpleNamespace(
        provider_id="claude",
        command=("claude", "setup-token"),
        write=lambda text: None,
        normalized_output=fake_output,
        process=SimpleNamespace(poll=lambda: None, returncode=None),
        terminate=lambda: None,
    )
    manager._provider_login_processes["sess-claude"] = handle
    manager._sync_provider_login_session = lambda provider_id, session_id: {  # type: ignore[attr-defined]
        "session_id": session_id,
        "status": "error",
        "last_error": "Claude Code rejected the authentication code. Start over.",
    }

    start = time.monotonic()
    result = manager_mod.ControlPlaneManager.submit_provider_login_code(
        manager,
        "claude",
        "sess-claude",
        {"code": "fakecode#statepart"},
    )
    elapsed = time.monotonic() - start

    assert result["status"] == "error"
    assert "rejected" in result["last_error"].lower()
    assert elapsed < 2.0, (
        f"submit must short-circuit on OAuth error line but took {elapsed:.2f}s "
        "(deadline is 30s — if we'd hit it this test would take much longer)"
    )


def test_submit_provider_login_code_returns_when_cli_exits_on_its_own(monkeypatch):
    """The submit loop must break as soon as the CLI exits on its own.
    Otherwise we'd keep polling the handle past the process's lifetime and
    block the HTTP response longer than necessary.
    """
    import koda.control_plane.manager as manager_mod

    manager, _rows, _meta, _secrets, _login_sessions = _make_manager(monkeypatch)
    manager_mod.ControlPlaneManager._PROVIDER_LOGIN_SUBMIT_DEADLINE_SECONDS = 5.0

    poll_results = iter([None, None, 0])  # exits on the third poll
    handle = SimpleNamespace(
        provider_id="claude",
        command=("claude", "setup-token"),
        write=lambda text: None,
        normalized_output=lambda: "Paste code here if prompted>\n",
        process=SimpleNamespace(poll=lambda: next(poll_results, 0), returncode=0),
        terminate=lambda: None,
    )
    manager._provider_login_processes["sess-claude"] = handle
    manager._sync_provider_login_session = lambda provider_id, session_id: {  # type: ignore[attr-defined]
        "session_id": session_id,
        "status": "completed",
    }

    # If we fall through to verify we'd block the test on a real subprocess —
    # fail loudly instead so a regression surfaces.
    def _fail_verify(*_args, **_kwargs):
        raise AssertionError("verification should not run once the CLI exits on its own")

    monkeypatch.setattr(manager_mod, "verify_provider_subscription_login", _fail_verify)

    start = time.monotonic()
    manager_mod.ControlPlaneManager.submit_provider_login_code(
        manager,
        "claude",
        "sess-claude",
        {"code": "abcd"},
    )
    elapsed = time.monotonic() - start
    assert elapsed < 4.0, f"submit must return promptly after CLI exits; took {elapsed:.2f}s"


def test_provider_login_pty_reader_swallows_eio_from_closed_slave():
    """When the child process closes the PTY slave side, ``read`` on the master
    returns ``OSError: [Errno 5] Input/output error``. The reader thread must
    treat that as end-of-stream and exit silently instead of crashing with a
    stack trace that pollutes the container logs.
    """
    import os
    import threading

    from koda.services.provider_auth import _ProviderLoginProcess

    calls = {"read": 0, "select": 0}

    def fake_poll():
        # Keep the reader inside the ``select`` branch (not the post-exit
        # drain branch) so we exercise the OSError path inside ``os.read``.
        return None

    def fake_select(_fds, _w, _x, _timeout):
        calls["select"] += 1
        # Return fd as ready so the reader calls os.read; on the second call
        # signal "not ready" to slow down the loop without the reader having
        # exited yet.
        return ([_fds[0]], [], []) if calls["select"] == 1 else ([], [], [])

    def fake_read(_fd, _size):
        calls["read"] += 1
        raise OSError(5, "Input/output error")

    process = SimpleNamespace(poll=fake_poll)
    handle = _ProviderLoginProcess(
        provider_id="claude",
        auth_mode="subscription_login",
        command=("claude", "setup-token"),
        process=cast(Any, process),
        interactive_fd=-1,  # not used because os.read is patched
    )

    original_read = os.read
    original_select_select = __import__("select").select
    original_set_blocking = os.set_blocking
    original_close = os.close

    def noop_set_blocking(_fd, _blocking):
        return None

    def noop_close(_fd):
        return None

    os.read = fake_read  # type: ignore[assignment]
    os.set_blocking = noop_set_blocking  # type: ignore[assignment]
    os.close = noop_close  # type: ignore[assignment]
    import select as select_module

    select_module.select = fake_select  # type: ignore[assignment]

    try:
        thread = threading.Thread(target=handle._read_from_pty, daemon=True)
        thread.start()
        thread.join(timeout=2.0)
        assert not thread.is_alive(), "reader thread must exit when the PTY returns EIO"
    finally:
        os.read = original_read  # type: ignore[assignment]
        os.set_blocking = original_set_blocking  # type: ignore[assignment]
        os.close = original_close  # type: ignore[assignment]
        select_module.select = original_select_select  # type: ignore[assignment]

    assert calls["read"] >= 1, "reader must have attempted to read before breaking"


def test_start_provider_login_terminates_stale_session_before_spawning_new(monkeypatch):
    """If the operator restarts the wizard mid-flow, the manager must tear
    down any existing subprocess for that provider so we never leak PTYs.
    """
    import koda.control_plane.manager as manager_mod

    manager, _rows, _meta, _secrets, login_sessions = _make_manager(monkeypatch)

    terminated = {"called": False}
    stale_handle = SimpleNamespace(
        provider_id="claude",
        command=("claude", "setup-token"),
        normalized_output=lambda: "",
        terminate=lambda: terminated.__setitem__("called", True),
    )
    manager._provider_login_processes["stale-session"] = stale_handle

    fresh_process = SimpleNamespace(
        provider_id="claude",
        command=("claude", "setup-token"),
        normalized_output=lambda: "",
        terminate=lambda: None,
    )
    fresh_state = ProviderLoginSessionState(
        session_id="fresh-session",
        provider_id="claude",
        auth_mode="subscription_login",
        status="awaiting_browser",
        command="claude setup-token",
        auth_url="https://claude.com/cai/oauth/authorize?code=true&state=test",
    )
    monkeypatch.setattr(
        manager_mod,
        "start_login_process",
        lambda provider_id, project_id="", base_env=None, work_dir="": (fresh_process, fresh_state),
    )
    manager._sync_provider_login_session = (  # type: ignore[attr-defined]
        lambda provider_id, session_id: manager_mod.ControlPlaneManager._provider_login_session_dict(
            manager,
            login_sessions[session_id],
        )
    )

    started = manager_mod.ControlPlaneManager.start_provider_login(manager, "claude", {})

    assert started["login_session"]["session_id"] == "fresh-session"
    assert "stale-session" not in manager._provider_login_processes
    assert manager._provider_login_processes["fresh-session"] is fresh_process
    assert terminated["called"] is True


def test_provider_fallback_chain_skips_unverified_managed_providers(monkeypatch):
    import koda.config as config_mod
    import koda.services.llm_runner as llm_runner_mod

    # ``PROVIDER_FALLBACK_ORDER`` is read at import time; patch the resolved
    # attributes so the test is independent of env load order.
    monkeypatch.setattr(config_mod, "PROVIDER_FALLBACK_ORDER", ["claude", "codex", "gemini"])
    monkeypatch.setattr(llm_runner_mod, "PROVIDER_FALLBACK_ORDER", ["claude", "codex", "gemini"])
    monkeypatch.setenv(
        "AGENT_PROVIDER_RUNTIME_ELIGIBILITY_JSON",
        json.dumps(
            {
                "claude": {"eligible": False, "reason": "not_verified"},
                "codex": {"eligible": True, "reason": "verified"},
                "gemini": {"eligible": False, "reason": "not_verified"},
            }
        ),
    )

    chain = llm_runner_mod.get_provider_fallback_chain("claude")

    assert chain == ["codex"]


def test_claude_login_parser_extracts_browser_url_from_auth_login_output():
    import koda.services.provider_auth as auth_mod

    handle = SimpleNamespace(
        provider_id="claude",
        auth_mode="subscription_login",
        command=("claude", "setup-token"),
        process=SimpleNamespace(poll=lambda: None),
        normalized_output=lambda: (
            "Opening browser to sign in…\n"
            "If the browser didn't open, visit: https://claude.com/cai/oauth/authorize?code=true&state=test"
        ),
    )

    state = auth_mod.parse_login_session_state("sess-1", handle)

    assert state.status == "awaiting_browser"
    assert state.auth_url == "https://claude.com/cai/oauth/authorize?code=true&state=test"
    assert state.user_code == ""
    assert "login no navegador" in state.instructions.lower()


def test_claude_subscription_login_uses_setup_token_command(monkeypatch):
    """Claude subscription login must spawn ``claude setup-token`` — the
    headless-friendly variant that accepts the authorization code on stdin
    and writes a long-lived OAuth token to CLAUDE_CONFIG_DIR. Regressing to
    ``claude auth login --claudeai`` breaks the pasted-code flow because the
    non-headless login mutates CLI config in a way that isn't portable across
    worker spawns.
    """
    import koda.services.provider_auth as auth_mod

    monkeypatch.setattr(auth_mod, "resolve_provider_command", lambda provider_id, base_env=None: ("claude",))

    assert provider_login_command("claude") == ("claude", "setup-token")


def test_claude_browser_login_parser_detects_browser_prompt():
    import koda.services.provider_auth as auth_mod

    expected_url = (
        "https://claude.com/cai/oauth/authorize?code=true&client_id=9d1c250a-e61b-44d9-88"
        "ed-5944d1962f5e&response_type=code&redirect_uri=https%3A%2F%2Fplatform.claude.com"
        "%2Foauth%2Fcode%2Fcallback&scope=user%3Ainference&code_challenge=wvDwgqzGPIFcbo"
        "9MC9y2oDPWw-xLEaTIWNlXD7JwMuY&code_challenge_method=S256&state=IWISQ5VtCsd9wBDEX"
        "GKv0pgD-y2tsSYjSmFmVOLEQb0"
    )
    handle = SimpleNamespace(
        provider_id="claude",
        auth_mode="subscription_login",
        command=("claude", "setup-token"),
        process=SimpleNamespace(poll=lambda: None),
        normalized_output=lambda: (
            "Opening browser to sign in...\n"
            "If the browser didn't open, visit: https://claude.com/cai/oauth/authorize?code=true&client_id=9d1c250a-e61b-44d9-88\n"
            "https://claude.com/cai/oauth/authorize?code=true&client_id=9d1c250a-e61b-44d9-88\n"
            "\n"
            "ed-5944d1962f5e&response_type=code&redirect_uri=https%3A%2F%2Fplatform.claude.co\n"
            "m%2Foauth%2Fcode%2Fcallback&scope=user%3Ainference&code_challenge=wvDwgqzGPIFcbo\n"
            "9MC9y2oDPWw-xLEaTIWNlXD7JwMuY&code_challenge_method=S256&state=IWISQ5VtCsd9wBDEX\n"
            "GKv0pgD-y2tsSYjSmFmVOLEQb0\n\n"
            "Use the browser to sign in."
        ),
    )

    state = auth_mod.parse_login_session_state("sess-claude", handle)

    assert state.status == "awaiting_browser"
    assert state.auth_url == expected_url
    assert "login no navegador" in state.instructions.lower()


def test_claude_browser_login_parser_keeps_awaiting_browser_after_successful_exit():
    import koda.services.provider_auth as auth_mod

    handle = SimpleNamespace(
        provider_id="claude",
        auth_mode="subscription_login",
        command=("claude", "setup-token"),
        process=SimpleNamespace(poll=lambda: 0),
        normalized_output=lambda: (
            "Opening browser to sign in…\n"
            "If the browser didn't open, visit: https://claude.com/cai/oauth/authorize?code=true&state=test"
        ),
    )

    state = auth_mod.parse_login_session_state("sess-claude", handle)

    assert state.status == "awaiting_browser"
    assert state.auth_url == "https://claude.com/cai/oauth/authorize?code=true&state=test"
    assert "browser" in state.message.lower()


def test_claude_setup_token_parser_surfaces_invalid_code_retry():
    import koda.services.provider_auth as auth_mod

    handle = SimpleNamespace(
        provider_id="claude",
        auth_mode="subscription_login",
        command=("claude", "setup-token"),
        process=SimpleNamespace(poll=lambda: None),
        normalized_output=lambda: (
            "Browser didn't open? Use the url below to sign in\n"
            "https://claude.com/cai/oauth/authorize?code=true&state=test\n\n"
            "OAuth error: Invalid code. Please make sure the full code was copied\n"
            "Press Enter to retry.\n"
        ),
    )

    state = auth_mod.parse_login_session_state("sess-claude", handle)

    assert state.status == "awaiting_browser"
    assert state.last_error.startswith("Claude Code rejected the authentication code.")
    assert state.message == state.last_error


def test_claude_parser_marks_session_error_when_cli_exits_after_oauth_failure():
    """When ``claude setup-token`` exchanges the pasted code with Anthropic and
    the provider rejects it, the CLI prints an ``OAuth error`` line and then
    exits cleanly (returncode 0). The parser must translate that to
    ``status=error`` so the UI surfaces the rejection — keeping the session
    in ``awaiting_browser`` with a dead CLI leaves the wizard stuck on the
    authorize step forever because no retry is possible.
    """
    import koda.services.provider_auth as auth_mod

    handle = SimpleNamespace(
        provider_id="claude",
        auth_mode="subscription_login",
        command=("claude", "setup-token"),
        process=SimpleNamespace(poll=lambda: 0),  # CLI exited cleanly
        normalized_output=lambda: (
            "Welcome to Claude Code\n"
            "Browser didn't open? Use the url below to sign in\n"
            "https://claude.com/cai/oauth/authorize?code=true&state=test\n"
            "Paste code here if prompted>\n"
            "****************TE_XYZ\n"
            "OAuth error: Request failed with status code 400\n"
            "Press Enter to retry.\n"
        ),
    )

    state = auth_mod.parse_login_session_state("sess-exit-with-error", handle)

    assert state.status == "error"
    assert state.last_error, "parser must populate last_error when CLI exits after OAuth failure"
    assert state.message == state.last_error


def test_claude_setup_token_parser_reads_real_cli_output():
    """Regression test pinned against the real output produced by
    ``claude setup-token`` v2.1.92 when spawned under a PTY. The URL is wrapped
    across multiple lines because the CLI renders in a 80-col terminal; the
    parser must reassemble it via line-continuation detection before we hand
    it to the UI.
    """
    import koda.services.provider_auth as auth_mod

    handle = SimpleNamespace(
        provider_id="claude",
        auth_mode="subscription_login",
        command=("claude", "setup-token"),
        process=SimpleNamespace(poll=lambda: None),
        normalized_output=lambda: (
            "Welcome to Claude Code v2.1.92\n"
            "·Opening browser to sign in…\n"
            "Browser didn't open? Use the url below to sign in (c to copy)\n\n"
            "https://claude.com/cai/oauth/authorize?code=true&client_id=9d1c250a-e61b-44d9-88\n"
            "ed-5944d1962f5e&response_type=code&redirect_uri=https%3A%2F%2Fplatform.claude.co\n"
            "m%2Foauth%2Fcode%2Fcallback&scope=user%3Ainference&code_challenge=AbczIByBkoutvv\n"
            "HBgfxqi60-3VPNE62T1QXpx4s0b10&code_challenge_method=S256&state=6W3kLsogFAln8_3Uq\n"
            "cE4kqjUEeIbr_M6-9TGlT2WX9s\n\n"
            "Paste code here if prompted >\n"
        ),
    )

    state = auth_mod.parse_login_session_state("sess-setup-token", handle)

    assert state.status == "awaiting_browser"
    # The parser must stitch the 5-line wrapped URL into a single query string
    # — otherwise Anthropic's OAuth server rejects the code exchange.
    assert state.auth_url.startswith("https://claude.com/cai/oauth/authorize?code=true&client_id=")
    assert state.auth_url.endswith("_M6-9TGlT2WX9s")
    assert "code_challenge=" in state.auth_url
    assert state.auth_url.count("\n") == 0  # no stray newlines in the URL


def test_pending_login_session_auto_completes_when_subscription_is_already_authenticated(monkeypatch):
    import koda.control_plane.manager as manager_mod

    manager, _rows, _meta, _secrets, login_sessions = _make_manager(monkeypatch)
    manager._cleanup_provider_login_sessions = lambda: None  # type: ignore[attr-defined]

    terminated = {"called": False}
    handle = SimpleNamespace(
        provider_id="claude",
        auth_mode="subscription_login",
        command=("claude", "setup-token"),
        process=SimpleNamespace(poll=lambda: None),
        normalized_output=lambda: (
            "Opening browser to sign in…\n"
            "If the browser didn't open, visit: https://claude.com/cai/oauth/authorize?code=true&state=test"
        ),
        terminate=lambda: terminated.__setitem__("called", True),
    )
    manager._provider_login_processes["sess-1"] = handle
    login_sessions["sess-1"] = ProviderLoginSessionState(
        session_id="sess-1",
        provider_id="claude",
        auth_mode="subscription_login",
        status="awaiting_browser",
        command="claude setup-token",
        auth_url="https://claude.com/cai/oauth/authorize?code=true&state=test",
        user_code="",
        message="Abra o navegador",
        instructions="Abra o link do Claude Code e conclua o login no navegador.",
    )

    monkeypatch.setattr(
        manager_mod,
        "verify_provider_subscription_login",
        lambda provider_id, project_id="", base_env=None, work_dir="": ProviderVerificationResult(
            provider_id=provider_id,
            auth_mode="subscription_login",
            verified=True,
            account_label="Claude",
            checked_via="auth_status",
        ),
    )

    def fake_fetch_one(query, params=()):
        if "FROM cp_provider_login_sessions" not in query:
            return None
        session_id = str(params[0]) if params else ""
        state = login_sessions.get(session_id)
        if state is None:
            return None
        provider_id = str(params[1]) if len(params) > 1 else state.provider_id
        if provider_id != state.provider_id:
            return None
        return {
            "id": state.session_id,
            "provider_id": state.provider_id,
            "status": state.status,
            "details_json": manager_mod.json_dump(
                {
                    **manager_mod.ControlPlaneManager._provider_login_session_dict(manager, state),
                    "encrypted_details": "",
                }
            ),
            "created_at": "2026-03-30T00:00:00+00:00",
            "updated_at": "2026-03-30T00:00:01+00:00",
            "completed_at": "2026-03-30T00:00:02+00:00" if state.status == "completed" else None,
        }

    monkeypatch.setattr(manager_mod, "fetch_one", fake_fetch_one)

    details = manager_mod.ControlPlaneManager._sync_provider_login_session(manager, "claude", "sess-1")
    time.sleep(0.01)

    assert details["status"] == "completed"
    assert details["user_code"] == ""
    assert login_sessions["sess-1"].status == "completed"
    assert "sess-1" not in manager._provider_login_processes
    assert terminated["called"] is True


def test_claude_supports_subscription_login_and_local_modes():
    """Claude exposes three connection paths: API key, subscription login
    (``claude setup-token`` spawned in a PTY, code forwarded via stdin),
    and local (operator already authenticated the CLI on a mounted
    CLAUDE_CONFIG_DIR). All three must be advertised so the UI can render
    every branch of the connection wizard.
    """
    import koda.services.provider_auth as auth_mod

    assert auth_mod.provider_supports_api_key("claude")
    assert auth_mod.provider_supports_subscription_login("claude")
    assert auth_mod.provider_supports_local_connection("claude")


def test_claude_core_definition_advertises_all_three_auth_modes():
    """The core provider catalog must list every mode Claude supports so the
    UI catalog endpoint renders the full wizard."""
    from koda.agent_contract import resolve_core_provider_catalog

    catalog = {item["id"]: item for item in resolve_core_provider_catalog()}
    claude = catalog["claude"]
    assert set(claude["supported_auth_modes"]) == {"api_key", "subscription_login", "local"}
    assert claude["supports_api_key"] is True
    assert claude["supports_subscription_login"] is True
    assert claude["supports_local_connection"] is True
    assert claude["login_flow_kind"] == "browser"


def test_claude_subscription_verification_returns_friendly_message_when_not_logged_in(monkeypatch):
    import koda.services.provider_auth as auth_mod

    monkeypatch.setattr(auth_mod, "resolve_provider_command", lambda provider_id, base_env=None: ("claude",))
    monkeypatch.setattr(auth_mod, "build_provider_process_env", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        auth_mod.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout='{\n  "loggedIn": false,\n  "authMethod": "none",\n  "apiProvider": "firstParty"\n}\n',
            stderr="",
        ),
    )

    result = auth_mod.verify_provider_subscription_login("claude")

    assert result.verified is False
    assert result.last_error.startswith("Claude CLI not authenticated yet.")


def test_completed_claude_login_session_waits_for_backend_verification(monkeypatch):
    import koda.control_plane.manager as manager_mod

    manager, _rows, _meta, _secrets, login_sessions = _make_manager(monkeypatch)
    manager._cleanup_provider_login_sessions = lambda: None  # type: ignore[attr-defined]

    handle = SimpleNamespace(
        provider_id="claude",
        auth_mode="subscription_login",
        command=("claude", "setup-token"),
        process=SimpleNamespace(poll=lambda: 0),
        terminate=lambda: None,
    )
    manager._provider_login_processes["sess-claude"] = handle
    login_sessions["sess-claude"] = ProviderLoginSessionState(
        session_id="sess-claude",
        provider_id="claude",
        auth_mode="subscription_login",
        status="pending",
        command="claude setup-token",
        auth_url="https://claude.com/cai/oauth/authorize?code=true&state=test",
        user_code="",
        message="Aguardando navegador",
        instructions="Abra o link do Claude Code e conclua o login no navegador.",
        output_preview="Opening browser to sign in…",
    )

    monkeypatch.setattr(
        manager_mod,
        "parse_login_session_state",
        lambda session_id, live_handle: ProviderLoginSessionState(
            session_id=session_id,
            provider_id="claude",
            auth_mode="subscription_login",
            status="completed",
            command="claude setup-token",
            auth_url="https://claude.com/cai/oauth/authorize?code=true&state=test",
            user_code="",
            message="Fluxo oficial de login concluido.",
            instructions="Abra o link do Claude Code e conclua o login no navegador.",
            output_preview="Authentication complete",
        ),
    )
    monkeypatch.setattr(
        manager_mod,
        "verify_provider_subscription_login",
        lambda provider_id, project_id="", base_env=None, work_dir="": ProviderVerificationResult(
            provider_id=provider_id,
            auth_mode="subscription_login",
            verified=False,
            last_error="Claude CLI not authenticated yet.",
            checked_via="auth_status",
        ),
    )

    def fake_fetch_one(query, params=()):
        if "FROM cp_provider_login_sessions" not in query:
            return None
        session_id = str(params[0]) if params else ""
        state = login_sessions.get(session_id)
        if state is None:
            return None
        provider_id = str(params[1]) if len(params) > 1 else state.provider_id
        if provider_id != state.provider_id:
            return None
        return {
            "id": state.session_id,
            "provider_id": state.provider_id,
            "status": state.status,
            "details_json": manager_mod.json_dump(
                {
                    **manager_mod.ControlPlaneManager._provider_login_session_dict(manager, state),
                    "encrypted_details": "",
                }
            ),
            "created_at": "2026-03-30T00:00:00+00:00",
            "updated_at": "2026-03-30T00:00:01+00:00",
            "completed_at": None,
        }

    monkeypatch.setattr(manager_mod, "fetch_one", fake_fetch_one)

    details = manager_mod.ControlPlaneManager._sync_provider_login_session(manager, "claude", "sess-claude")

    assert details["status"] == "pending"
    assert "validando" in details["message"].lower()
    assert manager._provider_login_processes["sess-claude"] is handle


def test_stale_pending_login_session_is_cancelled_when_runtime_process_is_missing(monkeypatch):
    import koda.control_plane.manager as manager_mod

    manager, _rows, _meta, _secrets, login_sessions = _make_manager(monkeypatch)
    manager._cleanup_provider_login_sessions = lambda: None  # type: ignore[attr-defined]
    login_sessions["sess-stale"] = ProviderLoginSessionState(
        session_id="sess-stale",
        provider_id="claude",
        auth_mode="subscription_login",
        status="awaiting_browser",
        command="claude setup-token",
        auth_url="https://claude.com/cai/oauth/authorize?code=true&client_id=stale",
        user_code="",
        message="Abra o navegador",
    )

    monkeypatch.setattr(
        manager_mod,
        "verify_provider_subscription_login",
        lambda provider_id, project_id="", base_env=None, work_dir="": ProviderVerificationResult(
            provider_id=provider_id,
            auth_mode="subscription_login",
            verified=False,
            last_error="not authenticated",
            checked_via="auth_status",
        ),
    )

    def fake_fetch_one(query, params=()):
        if "FROM cp_provider_login_sessions" not in query:
            return None
        session_id = str(params[0]) if params else ""
        state = login_sessions.get(session_id)
        if state is None:
            return None
        provider_id = str(params[1]) if len(params) > 1 else state.provider_id
        if provider_id != state.provider_id:
            return None
        return {
            "id": state.session_id,
            "provider_id": state.provider_id,
            "status": state.status,
            "details_json": manager_mod.json_dump(
                {
                    **manager_mod.ControlPlaneManager._provider_login_session_dict(manager, state),
                    "encrypted_details": "",
                }
            ),
            "created_at": "2026-03-30T00:00:00+00:00",
            "updated_at": "2026-03-30T00:00:01+00:00",
            "completed_at": "2026-03-30T00:00:02+00:00" if state.status in {"completed", "cancelled"} else None,
        }

    monkeypatch.setattr(manager_mod, "fetch_one", fake_fetch_one)

    details = manager_mod.ControlPlaneManager._sync_provider_login_session(manager, "claude", "sess-stale")

    assert details["status"] == "cancelled"
    assert details["auth_url"] == ""
    assert "expirou" in details["message"]
    assert login_sessions["sess-stale"].status == "cancelled"


def test_general_review_warns_when_default_or_fallback_uses_unverified_provider(monkeypatch):
    import koda.control_plane.manager as manager_mod

    manager, _rows, _meta, _secrets, _sessions = _make_manager(monkeypatch)
    manager.get_core_providers = lambda: {  # type: ignore[attr-defined]
        "providers": _build_provider_catalog(),
    }
    manager.list_connection_defaults = lambda: {"items": []}  # type: ignore[attr-defined]

    warnings = manager_mod.ControlPlaneManager._general_review_warnings(
        manager,
        {
            "models": {
                "providers_enabled": ["claude", "codex"],
                "default_provider": "claude",
                "fallback_order": ["claude", "codex"],
                "functional_defaults": {},
                "elevenlabs_default_voice": "",
            },
            "provider_connections": {
                "claude": {"verified": False},
                "codex": {"verified": True, "auth_mode": "api_key", "api_key_present": True},
            },
        },
    )

    assert "The default provider must be connected and verified." in warnings
    assert "The fallback order includes providers that have not yet been verified." in warnings


def test_purge_provider_global_secrets_wipes_every_scoped_env_key(monkeypatch):
    """Disconnect must remove API key + auth token + base URL + project +
    verified flag — not only the API key as the old implementation did.
    Otherwise a re-connection inherits stale ``ANTHROPIC_AUTH_TOKEN`` /
    ``CLAUDE_AUTH_MODE`` state and the operator gets unexpected behavior
    (still logged in even though the UI says "disconnected").
    """
    import koda.control_plane.manager as manager_mod

    manager = object.__new__(manager_mod.ControlPlaneManager)
    deleted: list[str] = []

    def _capture_delete(env_key, *, persist_sections=True):
        deleted.append(env_key)

    manager.delete_global_secret_asset = _capture_delete  # type: ignore[method-assign]
    manager._persist_global_sections = lambda sections: None  # type: ignore[method-assign]

    manager._purge_provider_global_secrets("claude")

    assert "ANTHROPIC_API_KEY" in deleted
    assert "ANTHROPIC_AUTH_TOKEN" in deleted
    assert "CLAUDE_AUTH_MODE" in deleted
    assert "CLAUDE_CONNECTION_VERIFIED" in deleted


def test_wipe_provider_credential_files_clears_known_dirs(monkeypatch, tmp_path):
    """Claude Code CLI persists OAuth tokens under ``CLAUDE_CONFIG_DIR``.
    A CLI ``logout`` normally clears them, but older versions (or a
    mid-logout crash) leave tokens on disk. The disconnect path must wipe
    the known credential directories so the next login starts fresh.
    """
    import koda.control_plane.manager as manager_mod

    config_dir = tmp_path / "claude-config"
    config_dir.mkdir()
    leftover = config_dir / ".claude.json"
    leftover.write_text('{"oauth": "stale-token"}')
    (config_dir / "backups").mkdir()
    (config_dir / "backups" / "old.json").write_text("{}")

    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_dir))
    monkeypatch.delenv("HOME", raising=False)

    manager = object.__new__(manager_mod.ControlPlaneManager)
    manager._wipe_provider_credential_files("claude")

    assert not leftover.exists()
    # The config_dir itself is kept (CLI will recreate children); only
    # children are removed so we don't stomp on a path owned by volume
    # mounts.
    assert config_dir.is_dir()
    assert list(config_dir.iterdir()) == []
