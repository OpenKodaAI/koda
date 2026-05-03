"""Tests for the effort cascade resolver in agent_settings."""

from __future__ import annotations

from koda.services.agent_settings import _effort_defaults_from_general_settings, resolve_effort


def test_effort_defaults_reads_from_values_models_block() -> None:
    """Ensures we read the modern API shape, not the legacy DB section shape."""
    settings = {
        "values": {
            "models": {"effort_defaults": {"codex:gpt-5": "high"}},
            "providers": {"effort_defaults": {"WRONG": "should-not-leak"}},
        }
    }
    assert _effort_defaults_from_general_settings(settings) == {"codex:gpt-5": "high"}


def test_effort_defaults_returns_empty_when_missing() -> None:
    assert _effort_defaults_from_general_settings({}) == {}
    assert _effort_defaults_from_general_settings({"values": {"models": {}}}) == {}


def test_resolve_effort_returns_agent_override_when_present() -> None:
    settings = {
        "effort_overrides": {"codex:gpt-5": "high"},
        "effort_defaults_global": {"codex:gpt-5": "low"},
    }
    assert resolve_effort(settings, "codex", "gpt-5") == "high"


def test_resolve_effort_falls_back_to_global_default() -> None:
    settings = {
        "effort_overrides": {},
        "effort_defaults_global": {"codex:gpt-5": "low"},
    }
    assert resolve_effort(settings, "codex", "gpt-5") == "low"


def test_resolve_effort_falls_back_to_catalog_default() -> None:
    settings = {"effort_overrides": {}, "effort_defaults_global": {}}
    assert resolve_effort(settings, "codex", "gpt-5") == "medium"


def test_resolve_effort_returns_none_when_model_has_no_capability() -> None:
    settings = {"effort_overrides": {}, "effort_defaults_global": {}}
    assert resolve_effort(settings, "mistral", "mistral-large-latest") is None


def test_resolve_effort_handles_none_settings_with_catalog_default() -> None:
    assert resolve_effort(None, "claude", "claude-opus-4-7") == "medium"


def test_resolve_effort_skips_invalid_enum_values() -> None:
    settings = {
        "effort_overrides": {"codex:gpt-5": "WRONG"},
        "effort_defaults_global": {"codex:gpt-5": "low"},
    }
    assert resolve_effort(settings, "codex", "gpt-5") == "low"


def test_resolve_effort_skips_out_of_range_token_values() -> None:
    settings = {
        "effort_overrides": {"deepseek:deepseek-v4-pro": 999_999},
        "effort_defaults_global": {"deepseek:deepseek-v4-pro": 1500},
    }
    assert resolve_effort(settings, "deepseek", "deepseek-v4-pro") == 1500


def test_resolve_effort_coerces_string_token_overrides() -> None:
    settings = {
        "effort_overrides": {"deepseek:deepseek-v4-pro": "3000"},
        "effort_defaults_global": {},
    }
    assert resolve_effort(settings, "deepseek", "deepseek-v4-pro") == 3000


def test_resolve_effort_skips_string_for_token_kind_when_not_numeric() -> None:
    settings = {
        "effort_overrides": {"deepseek:deepseek-v4-pro": "high"},
        "effort_defaults_global": {},
    }
    assert resolve_effort(settings, "deepseek", "deepseek-v4-pro") == 2000  # catalog default
