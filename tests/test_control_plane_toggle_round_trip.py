"""Integration tests that reproduce the "toggle unchecks after save" bug.

These tests drive the full put/get round-trip for toggle fields in the
Intelligence, Integrations, and Scheduler sections, asserting that values
written by the UI survive the backend pipeline and are returned intact.
"""

from __future__ import annotations

import koda.control_plane.manager as manager_mod


def _mk_manager():
    manager = object.__new__(manager_mod.ControlPlaneManager)
    manager._seeding_legacy_state = False
    manager._ollama_model_cache = {}
    manager._elevenlabs_voice_cache = {}
    manager._provider_login_processes = {}
    manager._claude_oauth_verifiers = {}
    manager._provider_download_threads = {}
    return manager


def _mock_storage(manager, monkeypatch) -> dict[str, dict[str, object]]:
    """Install an in-memory sections store on `manager` so put/get round-trip."""
    store: dict[str, dict[str, object]] = {}

    def load():
        return {section: dict(data) for section, data in store.items()}

    def load_section_attr():
        return load()

    def persist(sections):
        for section, data in sections.items():
            store[section] = dict(data)
        return 1

    manager._load_global_sections = load_section_attr  # type: ignore[attr-defined]
    manager._system_settings_sections = load_section_attr  # type: ignore[attr-defined]
    manager._persist_global_sections = persist  # type: ignore[attr-defined]
    manager._persist_global_default_version = lambda sections: 1  # type: ignore[attr-defined]
    manager.ensure_seeded = lambda: None  # type: ignore[attr-defined]
    manager._current_global_secrets = lambda **kwargs: []  # type: ignore[attr-defined]
    manager._access_meta_map = lambda key, sections=None: {}  # type: ignore[attr-defined]
    manager._general_ui_meta = lambda sections=None: {}  # type: ignore[attr-defined]
    manager._access_section = lambda sections=None: {}  # type: ignore[attr-defined]
    manager._global_secret_usage_scope = lambda secret_key, sections=None: "system_only"  # type: ignore[attr-defined]
    manager.delete_global_secret_asset = lambda env_key, persist_sections=True: None  # type: ignore[attr-defined]
    manager.upsert_global_secret_asset = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    # Real _merged_global_env/base walks the store to build env dict. Let it
    # run so GET reads what PUT wrote.
    manager._provider_connection_env = lambda: {}  # type: ignore[attr-defined]
    manager._validate_system_settings_payload = lambda payload: None  # type: ignore[attr-defined]
    manager._infer_profile_from_presets = lambda section, presets, meta_key=None, sections=None, default="": default  # type: ignore[attr-defined]
    # Stub provider catalog to avoid touching Ollama/HTTP calls during round-trip.
    manager.get_core_providers = lambda: {  # type: ignore[attr-defined]
        "providers": {},
        "default_provider": "claude",
        "fallback_order": [],
    }
    manager._provider_catalog_from_env = lambda env: {  # type: ignore[attr-defined]
        "providers": {},
        "default_provider": "claude",
        "fallback_order": [],
    }
    manager._infer_usage_profile = lambda *args, **kwargs: "balanced"  # type: ignore[attr-defined]
    manager._functional_model_catalog = lambda catalog: {}  # type: ignore[attr-defined]
    manager._resolve_general_functional_defaults = lambda **kwargs: {}  # type: ignore[attr-defined]
    manager._custom_global_variables_payload = lambda *args, **kwargs: []  # type: ignore[attr-defined]
    manager.get_provider_connection = lambda provider_id: {  # type: ignore[attr-defined]
        "provider_id": provider_id,
        "verified": False,
        "configured": False,
    }

    monkeypatch.setattr(manager_mod, "fetch_one", lambda *args, **kwargs: None)
    monkeypatch.setattr(manager_mod, "fetch_all", lambda *args, **kwargs: [])
    monkeypatch.setattr(manager_mod, "execute", lambda *args, **kwargs: 1)

    return store


def test_memory_enabled_toggle_round_trips_true(monkeypatch):
    manager = _mk_manager()
    _mock_storage(manager, monkeypatch)

    manager_mod.ControlPlaneManager.put_general_system_settings(
        manager,
        {
            "memory_and_knowledge": {
                "memory_enabled": True,
                "memory_profile": "balanced",
                "procedural_enabled": True,
                "proactive_enabled": True,
                "knowledge_enabled": True,
                "knowledge_profile": "curated_workspace",
                "provenance_policy": "standard",
            }
        },
    )
    got = manager_mod.ControlPlaneManager.get_general_system_settings(manager)
    mk = got["values"]["memory_and_knowledge"]
    assert mk["memory_enabled"] is True, f"memory_enabled regressed: got {mk['memory_enabled']!r}"
    assert mk["procedural_enabled"] is True, f"procedural_enabled regressed: got {mk['procedural_enabled']!r}"
    assert mk["proactive_enabled"] is True, f"proactive_enabled regressed: got {mk['proactive_enabled']!r}"
    assert mk["knowledge_enabled"] is True, f"knowledge_enabled regressed: got {mk['knowledge_enabled']!r}"


def test_memory_enabled_toggle_round_trips_false(monkeypatch):
    manager = _mk_manager()
    _mock_storage(manager, monkeypatch)

    # First enable, then disable to prove the switch flips both ways
    manager_mod.ControlPlaneManager.put_general_system_settings(
        manager,
        {"memory_and_knowledge": {"memory_enabled": True}},
    )
    manager_mod.ControlPlaneManager.put_general_system_settings(
        manager,
        {"memory_and_knowledge": {"memory_enabled": False}},
    )
    got = manager_mod.ControlPlaneManager.get_general_system_settings(manager)
    assert got["values"]["memory_and_knowledge"]["memory_enabled"] is False


def test_integration_toggle_round_trips(monkeypatch):
    manager = _mk_manager()
    _mock_storage(manager, monkeypatch)

    manager_mod.ControlPlaneManager.put_general_system_settings(
        manager,
        {
            "resources": {
                "integrations": {
                    "browser_enabled": True,
                    "gh_enabled": True,
                    "jira_enabled": True,
                }
            }
        },
    )
    got = manager_mod.ControlPlaneManager.get_general_system_settings(manager)
    integrations = got["values"]["resources"]["integrations"]
    assert integrations["browser_enabled"] is True
    assert integrations["gh_enabled"] is True
    assert integrations["jira_enabled"] is True


def test_scheduler_toggle_round_trips(monkeypatch):
    manager = _mk_manager()
    _mock_storage(manager, monkeypatch)

    manager_mod.ControlPlaneManager.put_general_system_settings(
        manager,
        {
            "scheduler": {
                "scheduler_enabled": True,
                "runbook_governance_enabled": True,
                "runbook_governance_hour": 4,
            }
        },
    )
    got = manager_mod.ControlPlaneManager.get_general_system_settings(manager)
    scheduler = got["values"]["scheduler"]
    assert scheduler["scheduler_enabled"] is True
    assert scheduler["runbook_governance_enabled"] is True
    assert scheduler["runbook_governance_hour"] == 4


def test_time_format_round_trips(monkeypatch):
    manager = _mk_manager()
    _mock_storage(manager, monkeypatch)

    manager_mod.ControlPlaneManager.put_general_system_settings(
        manager,
        {"account": {"time_format": "12h"}},
    )
    got = manager_mod.ControlPlaneManager.get_general_system_settings(manager)
    assert got["values"]["account"]["time_format"] == "12h"


def test_promotion_mode_round_trips(monkeypatch):
    manager = _mk_manager()
    _mock_storage(manager, monkeypatch)

    manager_mod.ControlPlaneManager.put_general_system_settings(
        manager,
        {"memory_and_knowledge": {"promotion_mode": "review_queue"}},
    )
    got = manager_mod.ControlPlaneManager.get_general_system_settings(manager)
    assert got["values"]["memory_and_knowledge"]["promotion_mode"] == "review_queue"


def test_promotion_mode_invalid_coerces_to_review_queue(monkeypatch):
    """Legacy 'supervised' value must be coerced to the only valid promotion mode."""
    manager = _mk_manager()
    _mock_storage(manager, monkeypatch)

    manager_mod.ControlPlaneManager.put_general_system_settings(
        manager,
        {"memory_and_knowledge": {"promotion_mode": "supervised"}},
    )
    got = manager_mod.ControlPlaneManager.get_general_system_settings(manager)
    assert got["values"]["memory_and_knowledge"]["promotion_mode"] == "review_queue"
