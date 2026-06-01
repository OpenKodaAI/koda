"""Tests for the llama.cpp and MLX runner profiles + dispatch wiring."""

from __future__ import annotations

import pytest

from koda.services.llamacpp_runner import LLAMACPP_PROFILE
from koda.services.llamacpp_runner import _build_profile as _build_llamacpp_profile
from koda.services.llm_runner import _HTTP_PROVIDER_RUNNERS, _RETRYABLE_PATTERNS
from koda.services.mlx_runner import MLX_PROFILE
from koda.services.mlx_runner import _build_profile as _build_mlx_profile
from koda.services.openai_compatible_runner import clear_openai_compatible_capability_cache


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_openai_compatible_capability_cache()
    yield
    clear_openai_compatible_capability_cache()


class TestLlamacppProfile:
    def test_provider_id(self):
        assert LLAMACPP_PROFILE.provider_id == "llamacpp"

    def test_default_base_url_is_local(self):
        assert LLAMACPP_PROFILE.base_url.startswith("http://127.0.0.1") or LLAMACPP_PROFILE.base_url.startswith(
            "http://localhost"
        )

    def test_auth_mode_is_local(self):
        assert LLAMACPP_PROFILE.auth_mode == "local"

    def test_allows_private_base_url(self):
        assert LLAMACPP_PROFILE.allow_private_base_url is True

    def test_uses_models_endpoint_probe(self):
        assert LLAMACPP_PROFILE.capability_probe == "models_endpoint"

    def test_local_mode_omits_authorization_when_no_key(self):
        headers = LLAMACPP_PROFILE.headers("")
        assert "Authorization" not in headers
        assert headers["Content-Type"] == "application/json"

    def test_local_mode_includes_authorization_when_proxied(self):
        headers = LLAMACPP_PROFILE.headers("proxy-secret")
        assert headers["Authorization"] == "Bearer proxy-secret"


class TestMlxProfile:
    def test_provider_id(self):
        assert MLX_PROFILE.provider_id == "mlx"

    def test_default_base_url_is_local(self):
        assert MLX_PROFILE.base_url.startswith("http://127.0.0.1") or MLX_PROFILE.base_url.startswith(
            "http://localhost"
        )

    def test_auth_mode_is_local(self):
        assert MLX_PROFILE.auth_mode == "local"

    def test_default_port_differs_from_llamacpp(self):
        # llama-server defaults to 8080, mlx-openai-server to 8000
        assert "8000" in MLX_PROFILE.base_url
        assert "8080" in LLAMACPP_PROFILE.base_url


class TestProviderRegistration:
    def test_llamacpp_in_http_runners(self):
        assert "llamacpp" in _HTTP_PROVIDER_RUNNERS
        runner = _HTTP_PROVIDER_RUNNERS["llamacpp"]
        assert callable(runner["run"])
        assert callable(runner["stream"])
        assert callable(runner["capabilities"])

    def test_mlx_in_http_runners(self):
        assert "mlx" in _HTTP_PROVIDER_RUNNERS
        runner = _HTTP_PROVIDER_RUNNERS["mlx"]
        assert callable(runner["run"])

    def test_local_runtime_retry_pattern_includes_metal_errors(self):
        pattern = _RETRYABLE_PATTERNS["llamacpp"]
        assert pattern.search("CUDA out of memory")  # local retry pattern is generous
        assert pattern.search("model not loaded yet")
        assert pattern.search("connection refused")


class TestProfileGrammarPassthrough:
    def test_llamacpp_profile_carries_grammar_when_enabled(self, monkeypatch):
        # When STRUCTURED_DECODING_ENABLED is on (default), the bundled GBNF
        # is loaded and emitted via extra_payload.
        monkeypatch.setenv("STRUCTURED_DECODING_ENABLED", "true")
        # Re-import to recompute the profile under the patched env.
        import importlib

        import koda.config as config_mod

        importlib.reload(config_mod)
        profile = _build_llamacpp_profile()
        if profile.extra_payload:
            keys = [pair[0] for pair in profile.extra_payload]
            assert "grammar" in keys

    def test_mlx_profile_omits_grammar(self):
        # MLX server doesn't expose grammar via OpenAI-compat HTTP today.
        profile = _build_mlx_profile()
        if profile.extra_payload:
            keys = [pair[0] for pair in profile.extra_payload]
            assert "grammar" not in keys
