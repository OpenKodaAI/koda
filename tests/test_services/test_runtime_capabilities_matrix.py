"""Full matrix of auto-activation states.

Covers every combination of:
- ``LOCAL_AUTO_OPTIMIZE`` ∈ {true, false}
- Local provider on/off (llamacpp, mlx, ollama)
- Apple Silicon detected / not detected
- Each dependency installed / not installed (sentence-transformers, faiss)
- Each binary present / missing (llama-server, mlx_lm.server)
- Each explicit override set / unset

The matrix has 256+ logical configurations; we collapse to the meaningful
equivalence classes here. The goal is to prove the resolution is
deterministic and doesn't accidentally activate features when conditions
aren't met (a real risk class — silent over-activation is worse than
silent under-activation because it triggers unsolicited model downloads).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from unittest.mock import patch

import pytest

import koda.services.runtime_capabilities as caps


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Strip every env var the resolver inspects so default-resolution path is exercised."""
    for key in (
        "RERANK_ENABLED",
        "SEMANTIC_CACHE_BACKEND",
        "LOCAL_PREFER_BELOW_COMPLEXITY",
        "LOCAL_RUNTIME_AUTO_SPAWN",
        "LOCAL_AUTO_OPTIMIZE",
    ):
        monkeypatch.delenv(key, raising=False)
    caps.reset_for_tests()
    yield
    caps.reset_for_tests()


@dataclass(frozen=True)
class Scenario:
    """One row of the matrix."""

    label: str
    auto_optimize: bool
    llamacpp: bool
    mlx: bool
    ollama: bool
    apple_silicon: bool
    has_st: bool  # sentence-transformers
    has_faiss: bool
    has_llama_bin: bool
    has_mlx_bin: bool
    expected_rerank: bool
    expected_cache: str
    expected_threshold_positive: bool
    expected_spawn_llamacpp: bool
    expected_spawn_mlx: bool


def _apply(scenario: Scenario) -> dict[str, object]:
    """Run ``runtime_capabilities`` under one scenario, return resolved snapshot."""

    def fake_has_dep(name: str) -> bool:
        if name == "sentence_transformers":
            return scenario.has_st
        if name == "faiss":
            return scenario.has_faiss
        if name == "mlx_lm":
            return scenario.has_mlx_bin
        return False

    def fake_has_binary(name: str) -> bool:
        if "llama-server" in name:
            return scenario.has_llama_bin
        if "mlx_lm.server" in name:
            return scenario.has_mlx_bin
        return False

    with (
        patch.object(caps, "LOCAL_AUTO_OPTIMIZE", scenario.auto_optimize),
        patch.object(caps, "LLAMACPP_ENABLED", scenario.llamacpp),
        patch.object(caps, "MLX_ENABLED", scenario.mlx),
        patch.object(caps, "OLLAMA_ENABLED", scenario.ollama),
        patch.object(caps, "_has_dep", fake_has_dep),
        patch.object(caps, "_has_binary", fake_has_binary),
        patch("koda.services.runtime_capabilities.is_apple_silicon", return_value=scenario.apple_silicon),
    ):
        return {
            "rerank": caps.effective_rerank_enabled(),
            "cache": caps.effective_semantic_cache_backend(),
            "threshold": caps.effective_local_prefer_threshold(),
            "spawn_llamacpp": caps.effective_auto_spawn("llamacpp"),
            "spawn_mlx": caps.effective_auto_spawn("mlx"),
            "metal_path": caps.is_metal_path_active(),
        }


_SCENARIOS: list[Scenario] = [
    # --- Conservative defaults ---
    Scenario(
        "no-local no-deps no-binaries",
        auto_optimize=True,
        llamacpp=False,
        mlx=False,
        ollama=False,
        apple_silicon=True,
        has_st=False,
        has_faiss=False,
        has_llama_bin=False,
        has_mlx_bin=False,
        expected_rerank=False,
        expected_cache="lexical",
        expected_threshold_positive=False,
        expected_spawn_llamacpp=False,
        expected_spawn_mlx=False,
    ),
    # --- Auto-optimize OFF kills everything ---
    Scenario(
        "auto-optimize off, perfect environment",
        auto_optimize=False,
        llamacpp=True,
        mlx=True,
        ollama=True,
        apple_silicon=True,
        has_st=True,
        has_faiss=True,
        has_llama_bin=True,
        has_mlx_bin=True,
        expected_rerank=False,
        expected_cache="lexical",
        expected_threshold_positive=False,
        expected_spawn_llamacpp=False,
        expected_spawn_mlx=False,
    ),
    # --- Happy path: llamacpp + everything available ---
    Scenario(
        "llamacpp on, all deps + binary, Apple Silicon",
        auto_optimize=True,
        llamacpp=True,
        mlx=False,
        ollama=False,
        apple_silicon=True,
        has_st=True,
        has_faiss=True,
        has_llama_bin=True,
        has_mlx_bin=False,
        expected_rerank=True,
        expected_cache="vector",
        expected_threshold_positive=True,
        expected_spawn_llamacpp=True,
        expected_spawn_mlx=False,
    ),
    # --- llamacpp on but no deps installed ---
    Scenario(
        "llamacpp on, no python deps, binary present",
        auto_optimize=True,
        llamacpp=True,
        mlx=False,
        ollama=False,
        apple_silicon=True,
        has_st=False,
        has_faiss=False,
        has_llama_bin=True,
        has_mlx_bin=False,
        expected_rerank=False,
        expected_cache="lexical",
        expected_threshold_positive=True,  # cascade only needs flag, not deps
        expected_spawn_llamacpp=True,
        expected_spawn_mlx=False,
    ),
    # --- llamacpp on, binary missing → no auto-spawn but other bolt-ons fine ---
    Scenario(
        "llamacpp on, binary missing",
        auto_optimize=True,
        llamacpp=True,
        mlx=False,
        ollama=False,
        apple_silicon=True,
        has_st=True,
        has_faiss=True,
        has_llama_bin=False,
        has_mlx_bin=False,
        expected_rerank=True,
        expected_cache="vector",
        expected_threshold_positive=True,
        expected_spawn_llamacpp=False,
        expected_spawn_mlx=False,
    ),
    # --- MLX-only setup ---
    Scenario(
        "mlx only, binary present, deps OK",
        auto_optimize=True,
        llamacpp=False,
        mlx=True,
        ollama=False,
        apple_silicon=True,
        has_st=True,
        has_faiss=True,
        has_llama_bin=False,
        has_mlx_bin=True,
        expected_rerank=True,
        expected_cache="vector",
        expected_threshold_positive=True,
        expected_spawn_llamacpp=False,
        expected_spawn_mlx=True,
    ),
    # --- Ollama only — local but no metal-path runtime ---
    Scenario(
        "ollama only, partial deps",
        auto_optimize=True,
        llamacpp=False,
        mlx=False,
        ollama=True,
        apple_silicon=True,
        has_st=True,
        has_faiss=False,
        has_llama_bin=False,
        has_mlx_bin=False,
        expected_rerank=True,
        expected_cache="lexical",
        expected_threshold_positive=True,
        expected_spawn_llamacpp=False,
        expected_spawn_mlx=False,
    ),
    # --- Intel Mac / Linux: local providers still work, just no metal_path ---
    Scenario(
        "llamacpp on Intel host",
        auto_optimize=True,
        llamacpp=True,
        mlx=False,
        ollama=False,
        apple_silicon=False,
        has_st=True,
        has_faiss=True,
        has_llama_bin=True,
        has_mlx_bin=False,
        expected_rerank=True,
        expected_cache="vector",
        expected_threshold_positive=True,
        expected_spawn_llamacpp=True,
        expected_spawn_mlx=False,
    ),
    # --- Mixed setup: all 3 local providers, partial environment ---
    Scenario(
        "all local providers, only sentence-transformers",
        auto_optimize=True,
        llamacpp=True,
        mlx=True,
        ollama=True,
        apple_silicon=True,
        has_st=True,
        has_faiss=False,
        has_llama_bin=False,
        has_mlx_bin=False,
        expected_rerank=True,
        expected_cache="lexical",
        expected_threshold_positive=True,
        expected_spawn_llamacpp=False,
        expected_spawn_mlx=False,
    ),
]


@pytest.mark.parametrize("scenario", _SCENARIOS, ids=lambda s: s.label)
def test_scenario_resolves_as_expected(scenario: Scenario):
    snap = _apply(scenario)
    assert snap["rerank"] is scenario.expected_rerank, f"rerank mismatch in {scenario.label}: {snap}"
    assert snap["cache"] == scenario.expected_cache, f"cache mismatch in {scenario.label}: {snap}"
    assert (snap["threshold"] > 0) is scenario.expected_threshold_positive, (
        f"threshold mismatch in {scenario.label}: {snap}"
    )
    assert snap["spawn_llamacpp"] is scenario.expected_spawn_llamacpp, (
        f"spawn_llamacpp mismatch in {scenario.label}: {snap}"
    )
    assert snap["spawn_mlx"] is scenario.expected_spawn_mlx, f"spawn_mlx mismatch in {scenario.label}: {snap}"


# ---------------------------------------------------------------------------
# Explicit overrides — every feature × every direction
# ---------------------------------------------------------------------------


_OVERRIDE_TABLE: list[tuple[str, str, Callable[[], object], object]] = [
    ("RERANK_ENABLED", "true", lambda: caps.effective_rerank_enabled(), True),
    ("RERANK_ENABLED", "false", lambda: caps.effective_rerank_enabled(), False),
    ("SEMANTIC_CACHE_BACKEND", "vector", lambda: caps.effective_semantic_cache_backend(), "vector"),
    ("SEMANTIC_CACHE_BACKEND", "lexical", lambda: caps.effective_semantic_cache_backend(), "lexical"),
    ("LOCAL_PREFER_BELOW_COMPLEXITY", "0.0", lambda: caps.effective_local_prefer_threshold(), 0.0),
    ("LOCAL_PREFER_BELOW_COMPLEXITY", "0.7", lambda: caps.effective_local_prefer_threshold(), 0.7),
    ("LOCAL_RUNTIME_AUTO_SPAWN", "true", lambda: caps.effective_auto_spawn("llamacpp"), True),
    ("LOCAL_RUNTIME_AUTO_SPAWN", "false", lambda: caps.effective_auto_spawn("llamacpp"), False),
]


@pytest.mark.parametrize(("env_key", "env_val", "getter", "expected"), _OVERRIDE_TABLE)
def test_explicit_override_always_wins_against_auto_activation(
    env_key: str,
    env_val: str,
    getter: Callable[[], object],
    expected: object,
    monkeypatch,
):
    """Operator's explicit env value is honored even when auto-activation would decide otherwise."""
    monkeypatch.setenv(env_key, env_val)
    # Reload config to pick up the env var (config reads at import time).
    import importlib  # noqa: PLC0415

    from koda import config as cfg  # noqa: PLC0415

    importlib.reload(cfg)
    importlib.reload(caps)

    # Configure environment that would auto-activate the *opposite* of what the
    # operator chose, to make this test a real adversary case.
    with (
        patch.object(caps, "LOCAL_AUTO_OPTIMIZE", True),
        patch.object(caps, "LLAMACPP_ENABLED", True),
        patch.object(caps, "_has_dep", lambda name: True),
        patch.object(caps, "_has_binary", lambda name: True),
    ):
        result = getter()
    if isinstance(expected, float):
        assert float(result) == expected, f"{env_key}={env_val} → expected {expected}, got {result}"
    else:
        assert result == expected, f"{env_key}={env_val} → expected {expected}, got {result}"


# ---------------------------------------------------------------------------
# Determinism — same inputs always resolve to same outputs
# ---------------------------------------------------------------------------


def test_resolution_is_deterministic_across_calls():
    """Calling effective_* repeatedly with same inputs returns same outputs."""
    snap1 = caps.runtime_capabilities_snapshot()
    snap2 = caps.runtime_capabilities_snapshot()
    snap3 = caps.runtime_capabilities_snapshot()
    assert snap1 == snap2 == snap3
