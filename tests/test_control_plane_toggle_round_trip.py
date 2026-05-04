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


def test_memory_enabled_overrides_stale_policy_enabled_from_dashboard(monkeypatch):
    """Regression: the dashboard echoes back the previous `memory_policy.enabled`
    from a fresh GET when the operator only flips `memory_enabled`. The PUT
    handler used to deep-merge that stale `memory_policy` on top of the
    overlay derived from `current_memory`, so toggling `memory_enabled=True`
    silently kept `enabled=False` in the persisted policy/env. The dashboard
    then re-rendered the switch as off."""
    manager = _mk_manager()
    _mock_storage(manager, monkeypatch)

    # Seed: memory_enabled=False (matches default install)
    manager_mod.ControlPlaneManager.put_general_system_settings(
        manager,
        {"memory_and_knowledge": {"memory_enabled": False, "knowledge_enabled": False}},
    )

    # User toggles memory_enabled+knowledge_enabled to True. The dashboard sends
    # the previous policy block alongside the new flags (real-world payload shape).
    manager_mod.ControlPlaneManager.put_general_system_settings(
        manager,
        {
            "memory_and_knowledge": {
                "memory_enabled": True,
                "memory_policy": {"enabled": False},
                "knowledge_enabled": True,
                "knowledge_policy": {"enabled": False},
            }
        },
    )
    got = manager_mod.ControlPlaneManager.get_general_system_settings(manager)
    mk = got["values"]["memory_and_knowledge"]
    assert mk["memory_enabled"] is True, f"memory_enabled regressed: got {mk['memory_enabled']!r}"
    assert mk["knowledge_enabled"] is True, f"knowledge_enabled regressed: got {mk['knowledge_enabled']!r}"


def test_policy_env_keys_never_surface_as_user_variables(monkeypatch):
    """Regression: env keys produced by `_apply_*_policy_to_section` (e.g.
    `AGENT_AUTONOMY_POLICY_JSON`, `MEMORY_RECENCY_HALF_LIFE_DAYS`,
    `KNOWLEDGE_GRAPH_ENABLED`) used to escape the
    `_SYSTEM_SETTINGS_KNOWN_ENV_KEYS` filter and show up as if the operator
    had typed them in the Variables panel. They are system-managed and must
    stay out of the user variables list — both on read and on write."""
    import koda.control_plane.manager as M

    # Read path: every policy-env key must be in the known set so it gets
    # filtered out of `additional_env_vars`.
    for k in M._AUTONOMY_POLICY_ENV_KEYS:
        assert k in M._SYSTEM_SETTINGS_KNOWN_ENV_KEYS, f"{k} leaks into user variables"
    for k in M._MEMORY_POLICY_ENV_KEYS:
        assert k in M._SYSTEM_SETTINGS_KNOWN_ENV_KEYS, f"{k} leaks into user variables"
    for k in M._KNOWLEDGE_POLICY_ENV_KEYS:
        assert k in M._SYSTEM_SETTINGS_KNOWN_ENV_KEYS, f"{k} leaks into user variables"
    for k in M._TOOL_POLICY_ENV_KEYS:
        assert k in M._SYSTEM_SETTINGS_KNOWN_ENV_KEYS, f"{k} leaks into user variables"
    for k in M._MODEL_POLICY_ENV_KEYS:
        assert k in M._SYSTEM_SETTINGS_KNOWN_ENV_KEYS, f"{k} leaks into user variables"

    # Write path: a malicious or careless dashboard payload that lists a
    # system-managed key under `variables` must be silently dropped instead
    # of getting persisted as a free-form env override.
    manager = _mk_manager()
    store = _mock_storage(manager, monkeypatch)
    manager_mod.ControlPlaneManager.put_general_system_settings(
        manager,
        {
            "variables": [
                {
                    "key": "AGENT_AUTONOMY_POLICY_JSON",
                    "value": '{"hacked": true}',
                    "type": "text",
                    "scope": "system_only",
                },
                {"key": "MEMORY_ENABLED", "value": "false", "type": "text", "scope": "system_only"},
                {"key": "MY_LEGIT_VAR", "value": "ok", "type": "text", "scope": "system_only"},
            ]
        },
    )
    # Inspect the store directly — every section's `env` map combined.
    persisted_envs: dict[str, str] = {}
    for section_data in store.values():
        env_map = (section_data or {}).get("env") or {}
        persisted_envs.update({str(k): str(v) for k, v in env_map.items()})
    assert "AGENT_AUTONOMY_POLICY_JSON" not in persisted_envs, (
        f"policy key persisted as user-defined env: {persisted_envs}"
    )
    # MEMORY_ENABLED is a system field-spec key — the user-vars list is the
    # wrong place for it. The actual MEMORY_ENABLED env, when set, comes from
    # the memory section's policy/toggle path, not from this loop.
    # The general section, where free-form vars land, must not carry it.
    general_env = (store.get("general") or {}).get("env") or {}
    assert "MEMORY_ENABLED" not in general_env, f"field-spec key leaked into general.env via variables: {general_env}"
    # The legitimate user var lands in general.env (or wherever the section
    # router sends it) and must survive.
    assert persisted_envs.get("MY_LEGIT_VAR") == "ok", f"legitimate user var got dropped on write: {persisted_envs}"


def test_memory_section_keeps_canonical_shape_across_round_trips(monkeypatch):
    """Regression: top-level shadow fields like `enabled`,
    `proactive_enabled`, `procedural_enabled`, `promotion_mode`,
    `require_freshness_provenance` used to live at the section root
    alongside the canonical `policy.*` and `env.*` maps. They were a
    side-effect of older persisted defaults, leaving the section data
    inconsistent with itself. `_apply_*_policy_to_section` now strips
    them, so the only keys allowed at the section root are `env` and
    `policy` — anything else means a leak crept back in."""
    manager = _mk_manager()
    store = _mock_storage(manager, monkeypatch)

    # Drive a couple of toggles through the policy-application paths.
    for state in (True, False, True):
        manager_mod.ControlPlaneManager.put_general_system_settings(
            manager,
            {"memory_and_knowledge": {"memory_enabled": state, "knowledge_enabled": state}},
        )

    for section_name in ("memory", "knowledge"):
        section = store.get(section_name) or {}
        assert sorted(section.keys()) == ["env", "policy"], (
            f"{section_name} section has stray top-level fields: {sorted(section.keys())}"
        )


def test_provenance_policy_overrides_stale_knowledge_policy(monkeypatch):
    """Regression: switching `provenance_policy` from 'standard' to 'strict'
    used to leave the `access.general_ui.provenance_policy` cached at
    'standard' because the dashboard echoes back the old `knowledge_policy`
    (with `require_freshness_provenance=False`) and that block was
    deep-merged on top of the user's intent. After the fix, the operator's
    `provenance_policy=strict` choice always wins over a stale knowledge
    policy block."""
    manager = _mk_manager()
    _mock_storage(manager, monkeypatch)

    # Bring the system to a 'standard' baseline.
    manager_mod.ControlPlaneManager.put_general_system_settings(
        manager,
        {"memory_and_knowledge": {"provenance_policy": "standard"}},
    )

    # Simulate the dashboard switching the radio to 'strict' while still
    # echoing back the previous knowledge_policy (with stale fields).
    manager_mod.ControlPlaneManager.put_general_system_settings(
        manager,
        {
            "memory_and_knowledge": {
                "provenance_policy": "strict",
                "knowledge_policy": {
                    "enabled": False,
                    "require_owner_provenance": False,
                    "require_freshness_provenance": False,
                },
            }
        },
    )
    got = manager_mod.ControlPlaneManager.get_general_system_settings(manager)
    assert got["values"]["memory_and_knowledge"]["provenance_policy"] == "strict"


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
    assert integrations.get("gh_enabled") is not True
    assert integrations.get("jira_enabled") is not True


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


def test_metal_enabled_false_round_trips(monkeypatch):
    """Regression: ``models.metal_enabled`` was being silently dropped by
    ``put_general_system_settings`` because the handler had no branch for it.
    The Apple Silicon switch in the UI would flip but the next GET would
    snap back to the default of ``True``. This locks down the round trip."""
    manager = _mk_manager()
    _mock_storage(manager, monkeypatch)

    manager_mod.ControlPlaneManager.put_general_system_settings(
        manager,
        {"models": {"metal_enabled": False}},
    )
    got = manager_mod.ControlPlaneManager.get_general_system_settings(manager)
    assert got["values"]["models"]["metal_enabled"] is False


def test_metal_enabled_true_round_trips_after_being_off(monkeypatch):
    """Flip off then back on — both writes must stick."""
    manager = _mk_manager()
    _mock_storage(manager, monkeypatch)

    manager_mod.ControlPlaneManager.put_general_system_settings(
        manager,
        {"models": {"metal_enabled": False}},
    )
    manager_mod.ControlPlaneManager.put_general_system_settings(
        manager,
        {"models": {"metal_enabled": True}},
    )
    got = manager_mod.ControlPlaneManager.get_general_system_settings(manager)
    assert got["values"]["models"]["metal_enabled"] is True
