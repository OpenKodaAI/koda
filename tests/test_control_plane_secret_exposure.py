"""Tests enforcing the "no secret preview ever reaches the browser" contract.

Every API surface that serializes a secret (provider connection, custom global
variable, integration credential template, per-agent secret) is expected to
emit ``preview`` / ``api_key_preview`` as ``""``. The UI shows only presence
flags (`value_present`, `api_key_present`) and action buttons; the operator
who wants to see a stored value must replace it.
"""

from __future__ import annotations

from koda.services.provider_auth import (
    PROVIDER_API_KEY_ENV_KEYS,
    ProviderLoginSessionState,
)


def _make_manager(monkeypatch):
    import koda.control_plane.manager as manager_mod

    manager = object.__new__(manager_mod.ControlPlaneManager)
    manager._elevenlabs_voice_cache = {}
    manager._ollama_model_cache = {}
    manager._provider_login_processes = {}
    manager._claude_oauth_verifiers = {}
    manager._provider_download_threads = {}
    rows = {
        provider_id: {
            "auth_mode": "api_key",
            "configured": 1,
            "verified": 1,
            "account_label": "",
            "plan_label": "",
            "project_id": "",
            "last_verified_at": "",
            "last_error": "",
        }
        for provider_id in PROVIDER_API_KEY_ENV_KEYS
    }
    secrets: dict[str, str] = {
        "OPENAI_API_KEY": "sk-openai-123456789abc",
        "ANTHROPIC_API_KEY": "sk-ant-abcdef",
    }
    login_sessions: dict[str, ProviderLoginSessionState] = {}

    manager.ensure_seeded = lambda: None  # type: ignore[attr-defined]
    manager._merged_global_env = lambda: {}  # type: ignore[attr-defined]
    manager._merged_global_env_base = lambda: {}  # type: ignore[attr-defined]
    manager._provider_auth_work_dir = lambda provider_id: "/tmp"  # type: ignore[attr-defined]
    manager._provider_catalog_from_env = lambda env: {  # type: ignore[attr-defined]
        "providers": {
            "claude": {"title": "Anthropic", "connection_managed": True, "supports_api_key": True},
            "codex": {"title": "OpenAI", "connection_managed": True, "supports_api_key": True},
            "gemini": {"title": "Google", "connection_managed": True, "supports_api_key": True},
            "elevenlabs": {"title": "ElevenLabs", "connection_managed": True, "supports_api_key": True},
            "ollama": {
                "title": "Ollama",
                "connection_managed": True,
                "supports_api_key": False,
                "supported_auth_modes": ["local"],
            },
        }
    }
    manager._provider_connection_row = lambda provider_id: rows[provider_id]  # type: ignore[attr-defined]
    manager._provider_api_key_secret_value = lambda provider_id: secrets.get(  # type: ignore[attr-defined]
        PROVIDER_API_KEY_ENV_KEYS.get(provider_id, ""),
        "",
    )
    manager._global_secret_preview_state = lambda env_key: (  # type: ignore[attr-defined]
        bool(secrets.get(env_key)),
        # Intentionally returns a populated preview — the point of the test
        # is that the SERIALIZER discards it regardless of what was computed.
        "sk**************************xx" if secrets.get(env_key) else "",
    )
    manager._resolve_ollama_base_url = lambda auth_mode, env=None: ""  # type: ignore[attr-defined]
    manager._persist_provider_login_session = lambda state: login_sessions.__setitem__(  # type: ignore[attr-defined]
        state.session_id,
        state,
    )

    monkeypatch.setattr(manager_mod, "fetch_one", lambda *args, **kwargs: None)
    monkeypatch.setattr(manager_mod, "fetch_all", lambda *args, **kwargs: [])
    monkeypatch.setattr(manager_mod, "execute", lambda *args, **kwargs: 1)
    monkeypatch.setattr(manager_mod, "provider_command_present", lambda provider_id, base_env=None: True)

    return manager


def test_provider_connection_serialize_strips_api_key_preview(monkeypatch):
    import koda.control_plane.manager as manager_mod

    manager = _make_manager(monkeypatch)
    conn = manager_mod.ControlPlaneManager._serialize_provider_connection(manager, "claude")
    assert conn["api_key_present"] is True
    assert conn["api_key_preview"] == "", f"expected empty preview, got {conn['api_key_preview']!r}"


def test_custom_global_variables_payload_strips_secret_preview(monkeypatch):
    import koda.control_plane.manager as manager_mod

    manager = _make_manager(monkeypatch)
    manager._access_meta_map = lambda meta_key, sections=None: {}  # type: ignore[attr-defined]
    manager._current_global_secrets = lambda sections=None: [  # type: ignore[attr-defined]
        {
            "secret_key": "MY_CUSTOM_SECRET",
            "usage_scope": "agent_grant",
            "description": "",
            "preview": "ab***yz",
        }
    ]

    variables = manager_mod.ControlPlaneManager._custom_global_variables_payload(
        manager,
        {"shared_variables": [], "additional_env_vars": []},
        sections={},
    )
    secrets = [v for v in variables if v["type"] == "secret"]
    assert secrets, "expected at least one secret-type variable in the payload"
    for entry in secrets:
        assert entry["preview"] == "", f"secret {entry['key']} leaked preview {entry['preview']!r}"
        assert entry["value_present"] is True


def test_stored_secret_assets_never_leak_preview(monkeypatch):
    import koda.control_plane.manager as manager_mod

    manager = _make_manager(monkeypatch)
    monkeypatch.setattr(
        manager_mod,
        "fetch_one",
        lambda *args, **kwargs: {
            "id": 7,
            "scope_id": "agent_one",
            "secret_key": "MY_AGENT_SECRET",
            "preview": "xy***yz",
            "updated_at": "2026-04-20T00:00:00+00:00",
        },
    )
    manager._require_agent_row = lambda agent_id: (agent_id, None)  # type: ignore[attr-defined]
    result = manager_mod.ControlPlaneManager.get_secret_asset(manager, "agent_one", "MY_AGENT_SECRET")
    assert result is not None
    assert result["preview"] == ""


def test_credential_template_field_strips_preview(monkeypatch):
    import koda.control_plane.manager as manager_mod

    manager = _make_manager(monkeypatch)
    manager._system_default_connection_config = lambda integration_id: {}  # type: ignore[attr-defined]
    manager._stored_global_secret_preview_state = lambda key: (True, "ab*******yz")  # type: ignore[attr-defined]

    payload = manager_mod.ControlPlaneManager._integration_fields_payload(manager, "jira")
    secret_fields = [field for field in payload if field.get("storage") == "secret"]
    assert secret_fields, "expected at least one secret field from the Jira credential template"
    for field in secret_fields:
        assert field["preview"] == "", f"template field {field.get('key')!r} leaked preview {field['preview']!r}"
        assert field["value_present"] is True
