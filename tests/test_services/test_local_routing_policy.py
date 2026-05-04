"""Tests for the cascade routing policy."""

from __future__ import annotations

from unittest.mock import patch

from koda.services.local_routing_policy import (
    adjust_chain_for_local_preference,
    is_local_provider,
    local_provider_priority,
)
from koda.services.model_router import complexity_score


class TestComplexityScore:
    def test_simple_greeting_low(self):
        assert complexity_score("hello", has_images=False) < 0.3

    def test_long_refactor_high(self):
        long_query = "Refactor the module at " + "x " * 500 + " into smaller files."
        assert complexity_score(long_query) > 0.6

    def test_images_floor_at_half(self):
        score = complexity_score("hi", has_images=True)
        assert score >= 0.5

    def test_score_is_in_unit_interval(self):
        for query in ("hi", "what is x?", "refactor this enormous codebase"):
            score = complexity_score(query)
            assert 0.0 <= score <= 1.0


class TestPolicyDisabled:
    def test_zero_threshold_returns_chain_unchanged(self):
        chain = ["claude", "groq"]
        result = adjust_chain_for_local_preference(
            chain,
            query="hi",
            prefer_below=0.0,
        )
        assert result == chain

    def test_negative_threshold_returns_chain_unchanged(self):
        chain = ["claude"]
        result = adjust_chain_for_local_preference(chain, query="hi", prefer_below=-0.5)
        assert result == chain


class TestPolicyEnabled:
    def test_simple_query_prepends_local_when_available(self):
        chain = ["claude", "groq"]
        with patch("koda.services.local_routing_policy.AVAILABLE_PROVIDERS", ["claude", "groq", "llamacpp"]):
            result = adjust_chain_for_local_preference(
                chain,
                query="hi",
                prefer_below=0.5,
            )
        assert result[0] == "llamacpp"
        assert "claude" in result and "groq" in result

    def test_complex_query_keeps_chain(self):
        chain = ["claude", "groq"]
        with patch("koda.services.local_routing_policy.AVAILABLE_PROVIDERS", ["claude", "groq", "llamacpp"]):
            result = adjust_chain_for_local_preference(
                chain,
                query="Refactor this 500-line file: " + "x " * 300,
                prefer_below=0.5,
            )
        assert result == chain

    def test_image_query_keeps_chain(self):
        chain = ["claude", "groq"]
        with patch("koda.services.local_routing_policy.AVAILABLE_PROVIDERS", ["claude", "groq", "llamacpp"]):
            result = adjust_chain_for_local_preference(
                chain,
                query="hi",
                has_images=True,
                prefer_below=0.5,
            )
        assert result == chain

    def test_no_local_available_keeps_chain(self):
        chain = ["claude", "groq"]
        with patch("koda.services.local_routing_policy.AVAILABLE_PROVIDERS", ["claude", "groq"]):
            result = adjust_chain_for_local_preference(
                chain,
                query="hi",
                prefer_below=0.5,
            )
        assert result == chain

    def test_prefers_mlx_over_llamacpp_when_both_available(self):
        chain = ["claude"]
        with patch("koda.services.local_routing_policy.AVAILABLE_PROVIDERS", ["claude", "llamacpp", "mlx"]):
            result = adjust_chain_for_local_preference(
                chain,
                query="hi",
                prefer_below=0.5,
            )
        assert result[0] == "mlx"

    def test_eligibility_blocks_local_provider(self):
        chain = ["claude"]
        eligibility = {"llamacpp": {"eligible": False}}
        with patch("koda.services.local_routing_policy.AVAILABLE_PROVIDERS", ["claude", "llamacpp"]):
            result = adjust_chain_for_local_preference(
                chain,
                query="hi",
                prefer_below=0.5,
                eligibility=eligibility,
            )
        assert result == chain


class TestHelpers:
    def test_is_local_provider(self):
        assert is_local_provider("llamacpp")
        assert is_local_provider("mlx")
        assert is_local_provider("ollama")
        assert not is_local_provider("claude")
        assert not is_local_provider("groq")

    def test_priority_order(self):
        # MLX first (Apple-native), llamacpp second (Metal via Vulkan-style),
        # Ollama last (already a fallback layer).
        priority = list(local_provider_priority())
        assert priority.index("mlx") < priority.index("llamacpp")
        assert priority.index("llamacpp") < priority.index("ollama")
