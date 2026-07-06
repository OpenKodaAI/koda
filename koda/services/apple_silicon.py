"""Apple Silicon detection and runtime recommendations.

Detects whether the host is an Apple Silicon Mac and exposes a recommendation
table that local-runtime providers (``llamacpp``, ``mlx``) consume to pick
sensible defaults: quantization format and the largest parameter count that
will fit in unified memory without thrashing.

Runs cheap shell commands once per process (``sysctl``, ``system_profiler``)
and caches the result. On non-Darwin hosts every probe degrades silently to
``is_apple_silicon=False`` so the rest of the runtime stays portable.
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass
from functools import cache
from typing import Literal

from koda.logging_config import get_logger

log = get_logger(__name__)

QuantizationRecommendation = Literal["q4_k_m", "q5_k_m", "q8_0", "mlx-4bit"]


@dataclass(frozen=True, slots=True)
class AppleSiliconProfile:
    """Capability snapshot for the local Apple Silicon environment."""

    is_apple_silicon: bool
    chip: str
    cpu_cores: int
    gpu_cores: int
    unified_memory_gb: int
    metal_supported: bool
    recommended_quantization: QuantizationRecommendation
    recommended_max_param_count_b: int

    def to_payload(self) -> dict[str, object]:
        """Serializable form for the web control plane."""
        return dict(asdict(self))


_DEFAULT_PROFILE = AppleSiliconProfile(
    is_apple_silicon=False,
    chip="",
    cpu_cores=0,
    gpu_cores=0,
    unified_memory_gb=0,
    metal_supported=False,
    recommended_quantization="q4_k_m",
    recommended_max_param_count_b=7,
)


def _run_sysctl(key: str) -> str:
    binary = shutil.which("sysctl")
    if not binary:
        return ""
    try:
        completed = subprocess.run(
            [binary, "-n", key],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.debug("apple_silicon_sysctl_failed", key=key, error=str(exc))
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _gpu_core_count() -> int:
    binary = shutil.which("system_profiler")
    if not binary:
        return 0
    try:
        completed = subprocess.run(
            [binary, "SPDisplaysDataType", "-json"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.debug("apple_silicon_system_profiler_failed", error=str(exc))
        return 0
    if completed.returncode != 0 or not completed.stdout.strip():
        return 0
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return 0
    displays = payload.get("SPDisplaysDataType")
    if not isinstance(displays, list):
        return 0
    for entry in displays:
        if not isinstance(entry, dict):
            continue
        for key in ("sppci_cores", "spdisplays_cores", "spdisplays_corecount"):
            value = entry.get(key)
            if isinstance(value, str) and value.strip().isdigit():
                return int(value.strip())
            if isinstance(value, int):
                return value
    return 0


def _quantization_for(memory_gb: int) -> QuantizationRecommendation:
    # Unified memory headroom: macOS keeps ~5–8GB; the rest is shared with the
    # model + KV cache. Higher-bit quantizations preserve quality on bigger Macs.
    if memory_gb >= 96:
        return "q5_k_m"
    if memory_gb >= 32:
        return "q4_k_m"
    return "mlx-4bit"


def _max_params_for(memory_gb: int) -> int:
    # Conservative ceiling: leave ~10GB headroom for KV cache + macOS + Koda.
    # Numbers are billions of parameters at the recommended quantization.
    if memory_gb >= 128:
        return 70
    if memory_gb >= 64:
        return 70  # 70B Q4_K_M fits with one heavy slot
    if memory_gb >= 36:
        return 30
    if memory_gb >= 24:
        return 13
    if memory_gb >= 16:
        return 8
    return 7


@cache
def detect_apple_silicon_profile() -> AppleSiliconProfile:
    """Return the local Apple Silicon profile, cached for the process lifetime.

    On non-Darwin hosts (or when the probes fail) returns a profile with
    ``is_apple_silicon=False``; callers should treat that as "no Metal path".
    """
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        return _DEFAULT_PROFILE

    chip = _run_sysctl("machdep.cpu.brand_string") or "Apple Silicon"
    cpu_cores_raw = _run_sysctl("hw.ncpu")
    memsize_raw = _run_sysctl("hw.memsize")
    cpu_cores = int(cpu_cores_raw) if cpu_cores_raw.isdigit() else 0
    try:
        unified_memory_gb = max(1, int(int(memsize_raw) / (1024**3)))
    except (TypeError, ValueError):
        unified_memory_gb = 0

    gpu_cores = _gpu_core_count()

    profile = AppleSiliconProfile(
        is_apple_silicon=True,
        chip=chip,
        cpu_cores=cpu_cores,
        gpu_cores=gpu_cores,
        unified_memory_gb=unified_memory_gb,
        metal_supported=True,
        recommended_quantization=_quantization_for(unified_memory_gb),
        recommended_max_param_count_b=_max_params_for(unified_memory_gb),
    )
    log.info(
        "apple_silicon_detected",
        chip=profile.chip,
        unified_memory_gb=profile.unified_memory_gb,
        gpu_cores=profile.gpu_cores,
        recommended_quantization=profile.recommended_quantization,
        recommended_max_param_count_b=profile.recommended_max_param_count_b,
    )
    return profile


def metal_runtime_install_hints() -> dict[str, dict[str, str]]:
    """Copy-paste install snippets shown in the connection modal.

    Keyed by provider id. Each entry has a short ``label`` and a multi-line
    ``snippet`` ready for an operator to paste into Terminal.
    """
    return {
        "llamacpp": {
            "label": "llama.cpp (Metal backend)",
            "snippet": (
                "brew install llama.cpp\n"
                "# Pick a GGUF model from huggingface.co/models?library=gguf\n"
                "llama-server -m ~/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf "
                "-ngl 99 --host 127.0.0.1 --port 8080"
            ),
        },
        "mlx": {
            "label": "MLX (Apple-native)",
            "snippet": (
                "pip install mlx-lm\n"
                "# Models: huggingface.co/mlx-community\n"
                "python -m mlx_lm.server "
                "--model mlx-community/Qwen2.5-7B-Instruct-4bit "
                "--host 127.0.0.1 --port 8000"
            ),
        },
    }


def is_apple_silicon() -> bool:
    """Convenience boolean — equivalent to ``detect_apple_silicon_profile().is_apple_silicon``."""
    return detect_apple_silicon_profile().is_apple_silicon


def reset_cache_for_tests() -> None:
    """Test hook: invalidate the cached profile so a fresh probe runs."""
    detect_apple_silicon_profile.cache_clear()
