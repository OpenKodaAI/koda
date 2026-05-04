"""Tests for Apple Silicon detection and recommendation table."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from koda.services.apple_silicon import (
    AppleSiliconProfile,
    detect_apple_silicon_profile,
    is_apple_silicon,
    metal_runtime_install_hints,
    reset_cache_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    reset_cache_for_tests()
    yield
    reset_cache_for_tests()


def _completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["mock"], returncode=returncode, stdout=stdout, stderr="")


def test_returns_default_profile_on_non_darwin():
    with (
        patch("koda.services.apple_silicon.platform.system", return_value="Linux"),
        patch("koda.services.apple_silicon.platform.machine", return_value="x86_64"),
    ):
        profile = detect_apple_silicon_profile()
    assert profile.is_apple_silicon is False
    assert profile.metal_supported is False
    assert profile.unified_memory_gb == 0


def test_returns_default_profile_on_intel_mac():
    with (
        patch("koda.services.apple_silicon.platform.system", return_value="Darwin"),
        patch("koda.services.apple_silicon.platform.machine", return_value="x86_64"),
    ):
        profile = detect_apple_silicon_profile()
    assert profile.is_apple_silicon is False


def _patch_apple_silicon(memsize_bytes: int, *, gpu_cores: int = 0) -> dict[str, object]:
    """Build a sysctl-mocking context for an Apple Silicon Mac."""

    def fake_run(args, **kwargs):  # noqa: ANN001 — mock signature
        binary = args[0] if args else ""
        if "sysctl" in binary:
            key = args[2]
            if key == "machdep.cpu.brand_string":
                return _completed("Apple M3 Max\n")
            if key == "hw.ncpu":
                return _completed("16\n")
            if key == "hw.memsize":
                return _completed(f"{memsize_bytes}\n")
            return _completed("")
        if "system_profiler" in binary:
            payload = {"SPDisplaysDataType": [{"sppci_cores": str(gpu_cores)}]}
            return _completed(json.dumps(payload))
        return _completed("")

    return {
        "system": "Darwin",
        "machine": "arm64",
        "subprocess_run": fake_run,
    }


def test_apple_silicon_m3_max_64gb():
    ctx = _patch_apple_silicon(64 * 1024**3, gpu_cores=40)
    with (
        patch("koda.services.apple_silicon.platform.system", return_value=ctx["system"]),
        patch("koda.services.apple_silicon.platform.machine", return_value=ctx["machine"]),
        patch("koda.services.apple_silicon.subprocess.run", side_effect=ctx["subprocess_run"]),
        patch("koda.services.apple_silicon.shutil.which", side_effect=lambda b: f"/usr/bin/{b}"),
    ):
        profile = detect_apple_silicon_profile()
    assert profile.is_apple_silicon is True
    assert profile.metal_supported is True
    assert profile.chip == "Apple M3 Max"
    assert profile.cpu_cores == 16
    assert profile.gpu_cores == 40
    assert profile.unified_memory_gb == 64
    # 64GB tier maps to 70B max + Q4_K_M
    assert profile.recommended_max_param_count_b == 70
    assert profile.recommended_quantization == "q4_k_m"


def test_apple_silicon_low_memory_recommends_smaller_model():
    ctx = _patch_apple_silicon(16 * 1024**3, gpu_cores=8)
    with (
        patch("koda.services.apple_silicon.platform.system", return_value=ctx["system"]),
        patch("koda.services.apple_silicon.platform.machine", return_value=ctx["machine"]),
        patch("koda.services.apple_silicon.subprocess.run", side_effect=ctx["subprocess_run"]),
        patch("koda.services.apple_silicon.shutil.which", side_effect=lambda b: f"/usr/bin/{b}"),
    ):
        profile = detect_apple_silicon_profile()
    assert profile.unified_memory_gb == 16
    assert profile.recommended_max_param_count_b == 8
    assert profile.recommended_quantization == "mlx-4bit"


def test_is_apple_silicon_convenience():
    with (
        patch("koda.services.apple_silicon.platform.system", return_value="Linux"),
        patch("koda.services.apple_silicon.platform.machine", return_value="x86_64"),
    ):
        reset_cache_for_tests()
        assert is_apple_silicon() is False


def test_install_hints_contain_both_runtimes():
    hints = metal_runtime_install_hints()
    assert set(hints.keys()) == {"llamacpp", "mlx"}
    assert "llama-server" in hints["llamacpp"]["snippet"]
    assert "mlx_lm.server" in hints["mlx"]["snippet"]


def test_profile_is_serializable():
    profile = AppleSiliconProfile(
        is_apple_silicon=True,
        chip="Apple M3 Max",
        cpu_cores=16,
        gpu_cores=40,
        unified_memory_gb=64,
        metal_supported=True,
        recommended_quantization="q4_k_m",
        recommended_max_param_count_b=70,
    )
    payload = profile.to_payload()
    assert payload["is_apple_silicon"] is True
    assert payload["recommended_max_param_count_b"] == 70
