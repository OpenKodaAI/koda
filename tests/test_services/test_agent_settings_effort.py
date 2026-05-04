"""Tests for the effort cascade resolver in agent_settings."""

from __future__ import annotations

from koda.services.agent_settings import _effort_default_from_general_settings, resolve_effort


def test_effort_default_reads_from_values_models_block() -> None:
    """Ensures we read the modern API shape, not the legacy DB section shape."""
    settings = {
        "values": {
            "models": {"effort_default": {"provider_id": "codex", "model_id": "gpt-5", "value": "high"}},
            "providers": {"effort_defaults": {"WRONG": "should-not-leak"}},
        }
    }
    assert _effort_default_from_general_settings(settings) == {
        "provider_id": "codex",
        "model_id": "gpt-5",
        "value": "high",
    }


def test_effort_default_returns_empty_when_missing() -> None:
    assert _effort_default_from_general_settings({}) == {}
    assert _effort_default_from_general_settings({"values": {"models": {}}}) == {}


def test_resolve_effort_returns_agent_override_when_present() -> None:
    settings = {
        "effort_override": {"provider_id": "codex", "model_id": "gpt-5", "value": "high"},
        "effort_default_global": {"provider_id": "codex", "model_id": "gpt-5", "value": "low"},
    }
    assert resolve_effort(settings, "codex", "gpt-5") == "high"


def test_resolve_effort_falls_back_to_global_default() -> None:
    settings = {
        "effort_override": {},
        "effort_default_global": {"provider_id": "codex", "model_id": "gpt-5", "value": "low"},
    }
    assert resolve_effort(settings, "codex", "gpt-5") == "low"


def test_resolve_effort_falls_back_to_catalog_default() -> None:
    settings = {"effort_override": {}, "effort_default_global": {}}
    assert resolve_effort(settings, "codex", "gpt-5") == "medium"


def test_resolve_effort_returns_none_when_model_has_no_capability() -> None:
    settings = {"effort_override": {}, "effort_default_global": {}}
    assert resolve_effort(settings, "mistral", "mistral-large-latest") is None


def test_resolve_effort_handles_none_settings_with_catalog_default() -> None:
    assert resolve_effort(None, "claude", "claude-opus-4-7") == "xhigh"


def test_resolve_effort_skips_invalid_enum_values() -> None:
    settings = {
        "effort_override": {"provider_id": "codex", "model_id": "gpt-5", "value": "WRONG"},
        "effort_default_global": {"provider_id": "codex", "model_id": "gpt-5", "value": "low"},
    }
    assert resolve_effort(settings, "codex", "gpt-5") == "low"


def test_resolve_effort_skips_invalid_deepseek_values() -> None:
    settings = {
        "effort_override": {"provider_id": "deepseek", "model_id": "deepseek-v4-pro", "value": "medium"},
        "effort_default_global": {"provider_id": "deepseek", "model_id": "deepseek-v4-pro", "value": "max"},
    }
    assert resolve_effort(settings, "deepseek", "deepseek-v4-pro") == "max"


def test_resolve_effort_accepts_legacy_maps() -> None:
    settings = {
        "effort_overrides": {"deepseek:deepseek-v4-pro": "max"},
        "effort_defaults_global": {},
    }
    assert resolve_effort(settings, "deepseek", "deepseek-v4-pro") == "max"


def test_resolve_effort_skips_string_for_token_kind_when_not_numeric() -> None:
    settings = {
        "effort_override": {"provider_id": "deepseek", "model_id": "deepseek-v4-pro", "value": "low"},
        "effort_default_global": {},
    }
    assert resolve_effort(settings, "deepseek", "deepseek-v4-pro") == "high"  # catalog default
