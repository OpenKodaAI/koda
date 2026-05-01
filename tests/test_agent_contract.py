"""Sentinel tests for CoreProviderDefinition catalog (especially the 7 HTTP providers)."""

import pytest

from koda.agent_contract import CORE_PROVIDER_CATALOG

_HTTP_OPENAI_COMPATIBLE_PROVIDERS = (
    "perplexity",
    "mistral",
    "qwen",
    "kimi",
    "groq",
    "deepseek",
    "xai",
)


@pytest.mark.parametrize("provider_id", _HTTP_OPENAI_COMPATIBLE_PROVIDERS)
def test_provider_in_catalog(provider_id):
    assert provider_id in CORE_PROVIDER_CATALOG


@pytest.mark.parametrize("provider_id", _HTTP_OPENAI_COMPATIBLE_PROVIDERS)
def test_provider_uses_openai_compatible_runtime_adapter(provider_id):
    assert CORE_PROVIDER_CATALOG[provider_id].runtime_adapter == "openai_compatible"


@pytest.mark.parametrize("provider_id", _HTTP_OPENAI_COMPATIBLE_PROVIDERS)
def test_provider_supports_only_api_key(provider_id):
    """None of the 7 new providers expose OAuth/subscription auth for API access."""
    assert CORE_PROVIDER_CATALOG[provider_id].supported_auth_modes == ("api_key",)


@pytest.mark.parametrize("provider_id", _HTTP_OPENAI_COMPATIBLE_PROVIDERS)
def test_provider_is_connection_managed(provider_id):
    """connection_managed=True is required so the frontend treats them as managed (no commandPresent check)."""
    assert CORE_PROVIDER_CATALOG[provider_id].connection_managed is True


@pytest.mark.parametrize("provider_id", _HTTP_OPENAI_COMPATIBLE_PROVIDERS)
def test_provider_has_no_login_flow(provider_id):
    assert CORE_PROVIDER_CATALOG[provider_id].login_flow_kind is None


@pytest.mark.parametrize("provider_id", _HTTP_OPENAI_COMPATIBLE_PROVIDERS)
def test_provider_does_not_require_project_id(provider_id):
    assert CORE_PROVIDER_CATALOG[provider_id].requires_project_id is False


@pytest.mark.parametrize("provider_id", _HTTP_OPENAI_COMPATIBLE_PROVIDERS)
def test_provider_supports_streaming(provider_id):
    assert CORE_PROVIDER_CATALOG[provider_id].supports_streaming is True


@pytest.mark.parametrize("provider_id", _HTTP_OPENAI_COMPATIBLE_PROVIDERS)
def test_provider_visible_in_settings(provider_id):
    assert CORE_PROVIDER_CATALOG[provider_id].show_in_settings is True


def test_perplexity_marked_as_no_long_context():
    """Sonar context is moderate; mark accordingly."""
    assert CORE_PROVIDER_CATALOG["perplexity"].supports_long_context is False


def test_mistral_supports_vision():
    """Mistral pixtral models support vision; declared at catalog level."""
    assert CORE_PROVIDER_CATALOG["mistral"].supports_images is True


def test_groq_supports_vision():
    """Groq llama-3.2-*-vision models support vision."""
    assert CORE_PROVIDER_CATALOG["groq"].supports_images is True


def test_deepseek_no_vision_support():
    """DeepSeek V3/R1 are text-only as of Q1 2026."""
    assert CORE_PROVIDER_CATALOG["deepseek"].supports_images is False


def test_existing_providers_still_present():
    """Regression sentinel: pre-existing providers untouched."""
    for legacy in ("claude", "codex", "gemini", "ollama", "elevenlabs", "kokoro", "whispercpp", "sora"):
        assert legacy in CORE_PROVIDER_CATALOG
