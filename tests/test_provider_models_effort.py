"""Tests for the per-model effort capability metadata."""

from __future__ import annotations

from koda.provider_models import get_model_effort_capability, resolve_provider_function_model_catalog


def test_claude_opus_47_declares_enum_effort() -> None:
    cap = get_model_effort_capability("claude", "claude-opus-4-7")
    assert cap is not None
    assert cap["kind"] == "enum"
    assert "xhigh" in cap["values"] and "max" in cap["values"]
    assert cap["default"] == "xhigh"


def test_codex_gpt5_declares_enum_with_minimal_level() -> None:
    cap = get_model_effort_capability("codex", "gpt-5")
    assert cap is not None
    assert cap["kind"] == "enum"
    assert "minimal" in cap["values"]
    assert cap["default"] == "medium"


def test_deepseek_v4_pro_declares_enum_effort() -> None:
    cap = get_model_effort_capability("deepseek", "deepseek-v4-pro")
    assert cap is not None
    assert cap["kind"] == "enum"
    assert cap["values"] == ("high", "max")
    assert cap["default"] == "high"


def test_perplexity_sonar_reasoning_declares_enum_effort() -> None:
    cap = get_model_effort_capability("perplexity", "sonar-reasoning")
    assert cap is not None
    assert cap["kind"] == "enum"


def test_xai_multi_agent_declares_reasoning_effort() -> None:
    cap = get_model_effort_capability("xai", "grok-4.20-multi-agent")
    assert cap is not None
    assert cap["kind"] == "enum"
    assert cap["values"] == ("low", "medium", "high", "xhigh")
    assert cap["default"] == "medium"


def test_provider_capability_is_case_insensitive() -> None:
    cap = get_model_effort_capability("  CODEX  ", "gpt-5")
    assert cap is not None


def test_models_without_effort_return_none() -> None:
    assert get_model_effort_capability("mistral", "mistral-large-latest") is None
    assert get_model_effort_capability("xai", "grok-3") is None
    assert get_model_effort_capability("claude", "claude-haiku-4-5-20251001") is None
    assert get_model_effort_capability("gemini", "gemini-2.5-pro") is None


def test_unknown_models_return_none() -> None:
    assert get_model_effort_capability("codex", "totally-fake-model") is None
    assert get_model_effort_capability("notaprovider", "gpt-5") is None


def test_catalog_dto_carries_effort_for_supported_models() -> None:
    catalog = resolve_provider_function_model_catalog("claude")
    opus = next(item for item in catalog if item["model_id"] == "claude-opus-4-7")
    assert opus["effort_kind"] == "enum"
    assert opus["effort_enum_values"]
    assert opus["effort_default"] == "xhigh"

    catalog = resolve_provider_function_model_catalog("deepseek")
    pro = next(item for item in catalog if item["model_id"] == "deepseek-v4-pro")
    assert pro["effort_kind"] == "enum"
    assert pro["effort_enum_values"] == ["high", "max"]

    catalog = resolve_provider_function_model_catalog("xai")
    grok = next(item for item in catalog if item["model_id"] == "grok-4.20-multi-agent")
    assert grok["effort_kind"] == "enum"
    assert grok["effort_enum_values"] == ["low", "medium", "high", "xhigh"]


def test_catalog_dto_omits_effort_for_unsupported_models() -> None:
    catalog = resolve_provider_function_model_catalog("mistral")
    large = next(item for item in catalog if item["model_id"] == "mistral-large-latest")
    assert "effort_kind" not in large
    assert "effort_enum_values" not in large
    assert "effort_token_min" not in large
