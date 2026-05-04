"""Tests for the auto-activation layer that decides which quality bolt-ons run."""

from __future__ import annotations

from unittest.mock import patch

import pytest

import koda.services.runtime_capabilities as caps


@pytest.fixture(autouse=True)
def _reset():
    caps.reset_for_tests()
    yield
    caps.reset_for_tests()


@pytest.fixture
def _clean_env(monkeypatch):
    """Strip the explicit env vars so default-resolution path is exercised."""
    for key in (
        "RERANK_ENABLED",
        "SEMANTIC_CACHE_BACKEND",
        "LOCAL_PREFER_BELOW_COMPLEXITY",
        "LOCAL_RUNTIME_AUTO_SPAWN",
        "LOCAL_AUTO_OPTIMIZE",
    ):
        monkeypatch.delenv(key, raising=False)
    yield monkeypatch


# Env-explicit override always wins


class TestExplicitOverrideWins:
    def test_rerank_explicit_true_respected(self, monkeypatch):
        monkeypatch.setenv("RERANK_ENABLED", "true")
        with patch.object(caps, "RERANK_ENABLED", True):
            assert caps.effective_rerank_enabled() is True

    def test_rerank_explicit_false_respected_even_when_conditions_perfect(self, monkeypatch):
        monkeypatch.setenv("RERANK_ENABLED", "false")
        with (
            patch.object(caps, "RERANK_ENABLED", False),
            patch.object(caps, "LOCAL_AUTO_OPTIMIZE", True),
            patch.object(caps, "LLAMACPP_ENABLED", True),
        ):
            assert caps.effective_rerank_enabled() is False

    def test_semantic_cache_explicit_lexical_wins(self, monkeypatch):
        monkeypatch.setenv("SEMANTIC_CACHE_BACKEND", "lexical")
        with (
            patch.object(caps, "SEMANTIC_CACHE_BACKEND", "lexical"),
            patch.object(caps, "LOCAL_AUTO_OPTIMIZE", True),
            patch.object(caps, "LLAMACPP_ENABLED", True),
        ):
            assert caps.effective_semantic_cache_backend() == "lexical"

    def test_local_prefer_explicit_zero_respected(self, monkeypatch):
        monkeypatch.setenv("LOCAL_PREFER_BELOW_COMPLEXITY", "0.0")
        with (
            patch.object(caps, "LOCAL_PREFER_BELOW_COMPLEXITY", 0.0),
            patch.object(caps, "LOCAL_AUTO_OPTIMIZE", True),
            patch.object(caps, "LLAMACPP_ENABLED", True),
        ):
            assert caps.effective_local_prefer_threshold() == 0.0


# Auto-optimize off → everything stays at "off" defaults


class TestAutoOptimizeDisabled:
    def test_rerank_off(self, _clean_env):
        with patch.object(caps, "LOCAL_AUTO_OPTIMIZE", False):
            assert caps.effective_rerank_enabled() is False

    def test_semantic_cache_lexical(self, _clean_env):
        with patch.object(caps, "LOCAL_AUTO_OPTIMIZE", False):
            assert caps.effective_semantic_cache_backend() == "lexical"

    def test_cascade_off(self, _clean_env):
        with patch.object(caps, "LOCAL_AUTO_OPTIMIZE", False):
            assert caps.effective_local_prefer_threshold() == 0.0

    def test_auto_spawn_off(self, _clean_env):
        with patch.object(caps, "LOCAL_AUTO_OPTIMIZE", False):
            assert caps.effective_auto_spawn("llamacpp") is False
            assert caps.effective_auto_spawn("mlx") is False


# ---------------------------------------------------------------------------
# Auto-optimize on but no local provider → still off (don't activate things
# the operator hasn't opted into via picking a local provider)
# ---------------------------------------------------------------------------


class TestNoLocalProvider:
    def test_rerank_off_when_no_local(self, _clean_env):
        with (
            patch.object(caps, "LOCAL_AUTO_OPTIMIZE", True),
            patch.object(caps, "LLAMACPP_ENABLED", False),
            patch.object(caps, "MLX_ENABLED", False),
            patch.object(caps, "OLLAMA_ENABLED", False),
        ):
            assert caps.effective_rerank_enabled() is False

    def test_cascade_off_when_no_local(self, _clean_env):
        with (
            patch.object(caps, "LOCAL_AUTO_OPTIMIZE", True),
            patch.object(caps, "LLAMACPP_ENABLED", False),
            patch.object(caps, "MLX_ENABLED", False),
            patch.object(caps, "OLLAMA_ENABLED", False),
        ):
            assert caps.effective_local_prefer_threshold() == 0.0


# ---------------------------------------------------------------------------
# The happy path: operator picks llamacpp → bolt-ons light up automatically
# based on what's actually available in the environment
# ---------------------------------------------------------------------------


class TestAutoActivationHappyPath:
    def test_rerank_lights_up_when_dep_installed(self, _clean_env):
        with (
            patch.object(caps, "LOCAL_AUTO_OPTIMIZE", True),
            patch.object(caps, "LLAMACPP_ENABLED", True),
            patch.object(caps, "_has_dep", lambda name: name == "sentence_transformers"),
        ):
            caps.reset_for_tests()
            assert caps.effective_rerank_enabled() is True

    def test_rerank_stays_off_without_dep(self, _clean_env):
        with (
            patch.object(caps, "LOCAL_AUTO_OPTIMIZE", True),
            patch.object(caps, "LLAMACPP_ENABLED", True),
            patch.object(caps, "_has_dep", lambda name: False),
        ):
            caps.reset_for_tests()
            assert caps.effective_rerank_enabled() is False

    def test_semantic_cache_vector_when_faiss_installed(self, _clean_env):
        with (
            patch.object(caps, "LOCAL_AUTO_OPTIMIZE", True),
            patch.object(caps, "LLAMACPP_ENABLED", True),
            patch.object(caps, "_has_dep", lambda name: name == "faiss"),
        ):
            caps.reset_for_tests()
            assert caps.effective_semantic_cache_backend() == "vector"

    def test_semantic_cache_stays_lexical_without_faiss(self, _clean_env):
        with (
            patch.object(caps, "LOCAL_AUTO_OPTIMIZE", True),
            patch.object(caps, "LLAMACPP_ENABLED", True),
            patch.object(caps, "_has_dep", lambda name: False),
        ):
            caps.reset_for_tests()
            assert caps.effective_semantic_cache_backend() == "lexical"

    def test_cascade_threshold_default_04(self, _clean_env):
        with (
            patch.object(caps, "LOCAL_AUTO_OPTIMIZE", True),
            patch.object(caps, "LLAMACPP_ENABLED", True),
        ):
            assert caps.effective_local_prefer_threshold() == pytest.approx(0.4)

    def test_auto_spawn_when_binary_present(self, _clean_env):
        with (
            patch.object(caps, "LOCAL_AUTO_OPTIMIZE", True),
            patch.object(caps, "LLAMACPP_ENABLED", True),
            patch.object(caps, "_has_binary", lambda name: True),
        ):
            caps.reset_for_tests()
            assert caps.effective_auto_spawn("llamacpp") is True

    def test_auto_spawn_off_when_binary_missing(self, _clean_env):
        with (
            patch.object(caps, "LOCAL_AUTO_OPTIMIZE", True),
            patch.object(caps, "LLAMACPP_ENABLED", True),
            patch.object(caps, "_has_binary", lambda name: False),
        ):
            caps.reset_for_tests()
            assert caps.effective_auto_spawn("llamacpp") is False


# Apple Silicon detection → metal_path_active flag


class TestMetalPath:
    def test_metal_active_when_apple_silicon_and_local(self, _clean_env):
        with (
            patch("koda.services.runtime_capabilities.is_apple_silicon", return_value=True),
            patch.object(caps, "METAL_ENABLED", True),
            patch.object(caps, "LLAMACPP_ENABLED", True),
        ):
            assert caps.is_metal_path_active() is True

    def test_metal_inactive_on_intel(self, _clean_env):
        with (
            patch("koda.services.runtime_capabilities.is_apple_silicon", return_value=False),
            patch.object(caps, "METAL_ENABLED", True),
            patch.object(caps, "LLAMACPP_ENABLED", True),
        ):
            assert caps.is_metal_path_active() is False

    def test_metal_inactive_when_no_local_provider(self, _clean_env):
        with (
            patch("koda.services.runtime_capabilities.is_apple_silicon", return_value=True),
            patch.object(caps, "METAL_ENABLED", True),
            patch.object(caps, "LLAMACPP_ENABLED", False),
            patch.object(caps, "MLX_ENABLED", False),
        ):
            assert caps.is_metal_path_active() is False

    def test_metal_inactive_when_operator_disabled_switch(self, _clean_env):
        """The operator's System Settings switch (METAL_ENABLED=False) must
        take precedence over any provider being enabled. Flipping the toggle
        off is the documented kill-switch for Metal-accelerated runtimes."""
        with (
            patch("koda.services.runtime_capabilities.is_apple_silicon", return_value=True),
            patch.object(caps, "METAL_ENABLED", False),
            patch.object(caps, "LLAMACPP_ENABLED", True),
            patch.object(caps, "MLX_ENABLED", True),
        ):
            assert caps.is_metal_path_active() is False

    def test_auto_spawn_blocked_when_metal_disabled(self, _clean_env):
        """The auto-spawn supervisor must respect the Metal kill-switch too —
        otherwise the operator could disable Metal in the UI but llama.cpp
        would still get spawned in the background."""
        with (
            patch.object(caps, "LOCAL_AUTO_OPTIMIZE", True),
            patch.object(caps, "METAL_ENABLED", False),
            patch.object(caps, "LLAMACPP_ENABLED", True),
            patch.object(caps, "MLX_ENABLED", True),
            patch.object(caps, "_has_binary", return_value=True),
            patch.object(caps, "_has_dep", return_value=True),
        ):
            assert caps.effective_auto_spawn("llamacpp") is False
            assert caps.effective_auto_spawn("mlx") is False


# Snapshot endpoint — single payload the web UI consumes


class TestSnapshot:
    def test_snapshot_keys_present(self, _clean_env):
        snap = caps.runtime_capabilities_snapshot()
        for key in (
            "local_auto_optimize",
            "local_inference_active",
            "metal_path_active",
            "rerank",
            "semantic_cache_backend",
            "cascade_routing",
            "auto_spawn",
        ):
            assert key in snap, f"missing key {key!r} in snapshot"

    def test_snapshot_reports_explicit_flag(self, monkeypatch):
        monkeypatch.setenv("RERANK_ENABLED", "true")
        snap = caps.runtime_capabilities_snapshot()
        assert snap["rerank"]["explicit"] is True

    def test_snapshot_reports_implicit_when_unset(self, _clean_env):
        snap = caps.runtime_capabilities_snapshot()
        assert snap["rerank"]["explicit"] is False
