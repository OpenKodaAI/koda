"""Provider detection plugin for the test suite.

Detects which real-provider API keys are configured in the environment and
exposes the result via the ``provider_keys`` fixture. Tests that exercise
real providers can ``pytest.skip`` when their target provider is missing,
or call into a mock when convenient. The session header advertises which
providers are exercised against the real API and which are mocked, so a
green run with everything mocked can never silently masquerade as full
coverage.

Local providers (Whisper.cpp, Kokoro, Ollama, MLX, LlamaCpp) are detected
by binary/file presence, not env vars.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterable
from dataclasses import dataclass

import pytest

# Cloud providers — detected via env var presence + non-empty value.
_CLOUD_PROVIDERS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "perplexity": "PERPLEXITY_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "kimi": "KIMI_API_KEY",
    "qwen": "QWEN_API_KEY",
    "xai": "XAI_API_KEY",
    "elevenlabs": "ELEVENLABS_API_KEY",
}


@dataclass(frozen=True)
class ProviderAvailability:
    cloud_real: frozenset[str]
    cloud_missing: frozenset[str]
    local_real: frozenset[str]
    local_missing: frozenset[str]

    def has_cloud(self, provider: str) -> bool:
        return provider in self.cloud_real

    def has_local(self, provider: str) -> bool:
        return provider in self.local_real


def _detect_local() -> tuple[frozenset[str], frozenset[str]]:
    """Detect locally-runnable providers."""
    real: set[str] = set()
    missing: set[str] = set()

    # Whisper.cpp on macOS via Homebrew installs `whisper-cli`; on Linux it is
    # often `whisper-cpp` or `whisper.cpp`. The repo accepts whichever resolves.
    whisper_candidates = ("whisper-cli", "whisper-cpp", "whisper.cpp")
    if any(shutil.which(name) for name in whisper_candidates):
        real.add("whisper_cpp")
    else:
        missing.add("whisper_cpp")

    # ffmpeg is required for STT/TTS preprocessing.
    if shutil.which("ffmpeg"):
        real.add("ffmpeg")
    else:
        missing.add("ffmpeg")

    # Kokoro models are managed by koda.services.kokoro_manager. The model file
    # is downloaded on demand into a managed storage path. We consider it real
    # if either the package can resolve a path (whether or not the file exists
    # yet — synthesize_speech() will lazy-download), or the env override points
    # at an existing dir.
    env_dir = os.environ.get("KOKORO_MODEL_DIR")
    if env_dir and os.path.isdir(env_dir):
        real.add("kokoro")
    else:
        try:
            from koda.services.kokoro_manager import kokoro_managed_voices_storage_path

            kokoro_managed_voices_storage_path()
            real.add("kokoro")
        except Exception:
            missing.add("kokoro")

    # Local LLM runtimes are detected by binary or env var.
    if shutil.which("ollama") or os.environ.get("OLLAMA_HOST"):
        real.add("ollama")
    else:
        missing.add("ollama")

    if os.environ.get("MLX_MODEL_PATH"):
        real.add("mlx")
    else:
        missing.add("mlx")

    if os.environ.get("LLAMACPP_BIN"):
        real.add("llamacpp")
    else:
        missing.add("llamacpp")

    return frozenset(real), frozenset(missing)


def _detect_cloud() -> tuple[frozenset[str], frozenset[str]]:
    """Detect cloud providers with non-empty API keys configured."""
    real: set[str] = set()
    missing: set[str] = set()
    for provider, env_name in _CLOUD_PROVIDERS.items():
        value = os.environ.get(env_name, "").strip()
        (real if value else missing).add(provider)
    return frozenset(real), frozenset(missing)


def _availability() -> ProviderAvailability:
    cloud_real, cloud_missing = _detect_cloud()
    local_real, local_missing = _detect_local()
    return ProviderAvailability(
        cloud_real=cloud_real,
        cloud_missing=cloud_missing,
        local_real=local_real,
        local_missing=local_missing,
    )


@pytest.fixture(scope="session")
def provider_keys() -> ProviderAvailability:
    """Snapshot of provider availability at session start.

    Tests that need a real provider should call ``provider_keys.has_cloud(name)``
    or ``provider_keys.has_local(name)`` and ``pytest.skip`` if it returns False.
    """
    return _availability()


def _format_set(items: Iterable[str]) -> str:
    return ", ".join(sorted(items)) or "(none)"


def pytest_report_header(config: pytest.Config) -> list[str]:
    """Print which providers are real vs missing in the pytest header."""
    avail = _availability()
    return [
        f"providers (cloud, real): {_format_set(avail.cloud_real)}",
        f"providers (cloud, missing): {_format_set(avail.cloud_missing)}",
        f"providers (local, real): {_format_set(avail.local_real)}",
        f"providers (local, missing): {_format_set(avail.local_missing)}",
    ]
