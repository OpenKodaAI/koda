"""Effective runtime capabilities — auto-activates quality bolt-ons when conditions are met.

Without this layer, every quality feature would default off and the operator
would have to set 5+ env vars to get the experience the implementation is
capable of. Instead, when ``LOCAL_AUTO_OPTIMIZE=true`` (default) and the
operator picks a local provider, we light up the practices that make sense
*for the actual environment*: deps that are installed, binaries that are
on the PATH, hardware that supports the codepath.

Explicit env vars **always win**: ``RERANK_ENABLED=false`` stays off even
when conditions are perfect. ``LOCAL_AUTO_OPTIMIZE=false`` reverts the
whole module to "do nothing implicit".

The functions here are imported by the consumers (reranker, cache manager,
routing policy, runners) so a single source of truth answers "should this
feature run on this install?".
"""

from __future__ import annotations

import importlib.util
import os
import shutil
from functools import cache

from koda.config import (
    LLAMACPP_BIN,
    LLAMACPP_ENABLED,
    LOCAL_AUTO_OPTIMIZE,
    LOCAL_PREFER_BELOW_COMPLEXITY,
    LOCAL_RUNTIME_AUTO_SPAWN,
    METAL_ENABLED,
    MLX_ENABLED,
    MLX_SERVER_BIN,
    OLLAMA_ENABLED,
    RERANK_ENABLED,
    SEMANTIC_CACHE_BACKEND,
)
from koda.logging_config import get_logger
from koda.services.apple_silicon import is_apple_silicon

log = get_logger(__name__)

# Sentinel signaling "operator did not set this env var explicitly".
_DEFAULT_LOCAL_PREFER = 0.4


def _is_env_explicit(name: str) -> bool:
    """Operator explicitly set this env var (any value)."""
    return name in os.environ


@cache
def _has_dep(module_name: str) -> bool:
    """Module is importable in this Python environment.

    Cached per process — deps don't appear/disappear at runtime.
    """
    try:
        spec = importlib.util.find_spec(module_name)
        return spec is not None
    except (ImportError, ValueError):
        return False


@cache
def _has_binary(name: str) -> bool:
    """Binary is resolvable on PATH (or absolute path exists)."""
    if not name:
        return False
    if os.path.isabs(name):
        return os.path.isfile(name) and os.access(name, os.X_OK)
    return shutil.which(name) is not None


def is_local_inference_active() -> bool:
    """Operator opted into at least one local-inference provider."""
    return LLAMACPP_ENABLED or MLX_ENABLED or OLLAMA_ENABLED


def is_metal_path_active() -> bool:
    """The Metal path is the active expectation.

    Three conditions must all hold:

    1. The host is Apple Silicon (no Metal anywhere else).
    2. The operator hasn't disabled Metal in System Settings (``METAL_ENABLED``).
    3. At least one Metal-capable runtime is enabled (llama.cpp or MLX).
    """
    if not is_apple_silicon():
        return False
    if not METAL_ENABLED:
        return False
    return LLAMACPP_ENABLED or MLX_ENABLED


# ---------------------------------------------------------------------------
# Feature-level effective state
# ---------------------------------------------------------------------------


def effective_rerank_enabled() -> bool:
    """Reranker should run on this install.

    Resolution order:
      1. ``RERANK_ENABLED`` set explicitly → respect operator.
      2. ``LOCAL_AUTO_OPTIMIZE`` off → off.
      3. Local inference active + ``sentence-transformers`` importable → on.
      4. Otherwise → off.
    """
    if _is_env_explicit("RERANK_ENABLED"):
        return RERANK_ENABLED
    if not LOCAL_AUTO_OPTIMIZE:
        return False
    if not is_local_inference_active():
        return False
    return _has_dep("sentence_transformers")


def effective_semantic_cache_backend() -> str:
    """Cache backend (``lexical`` or ``vector``) for this install."""
    if _is_env_explicit("SEMANTIC_CACHE_BACKEND"):
        return SEMANTIC_CACHE_BACKEND
    if not LOCAL_AUTO_OPTIMIZE:
        return "lexical"
    if not is_local_inference_active():
        return "lexical"
    if not _has_dep("faiss"):
        return "lexical"
    return "vector"


def effective_local_prefer_threshold() -> float:
    """Cascade-routing threshold: prepend local for queries below this complexity."""
    if _is_env_explicit("LOCAL_PREFER_BELOW_COMPLEXITY"):
        return LOCAL_PREFER_BELOW_COMPLEXITY
    if not LOCAL_AUTO_OPTIMIZE:
        return 0.0
    if not is_local_inference_active():
        return 0.0
    return _DEFAULT_LOCAL_PREFER


def effective_auto_spawn(runtime: str = "llamacpp") -> bool:
    """Whether the supervisor should auto-spawn the local runtime binary.

    Metal-dependent runtimes (llama.cpp, MLX) additionally require the
    ``METAL_ENABLED`` operator switch to be on — flipping the System
    Settings switch off must stop new auto-spawns.
    """
    if _is_env_explicit("LOCAL_RUNTIME_AUTO_SPAWN"):
        return LOCAL_RUNTIME_AUTO_SPAWN
    if not LOCAL_AUTO_OPTIMIZE:
        return False
    if runtime == "llamacpp":
        if not METAL_ENABLED:
            return False
        return LLAMACPP_ENABLED and _has_binary(LLAMACPP_BIN)
    if runtime == "mlx":
        if not METAL_ENABLED:
            return False
        return MLX_ENABLED and (_has_binary(MLX_SERVER_BIN) or _has_dep("mlx_lm"))
    return False


def reset_for_tests() -> None:
    """Clear caches so per-test env mutations take effect.

    Tolerates monkey-patched stand-ins (where ``cache_clear`` is missing)
    so tests can patch ``_has_dep`` / ``_has_binary`` directly without
    needing to also stub the reset.
    """
    for fn in (_has_dep, _has_binary):
        clearer = getattr(fn, "cache_clear", None)
        if callable(clearer):
            clearer()


def runtime_capabilities_snapshot() -> dict[str, object]:
    """Single payload describing what auto-activation decided for this process.

    Surfaced via the web /api/system/local-runtime/profile endpoint and
    logged at startup so operators can verify their environment matches
    their expectations.
    """
    return {
        "local_auto_optimize": LOCAL_AUTO_OPTIMIZE,
        "local_inference_active": is_local_inference_active(),
        "metal_path_active": is_metal_path_active(),
        "rerank": {
            "effective": effective_rerank_enabled(),
            "explicit": _is_env_explicit("RERANK_ENABLED"),
            "dep_present": _has_dep("sentence_transformers"),
        },
        "semantic_cache_backend": {
            "effective": effective_semantic_cache_backend(),
            "explicit": _is_env_explicit("SEMANTIC_CACHE_BACKEND"),
            "dep_present": _has_dep("faiss"),
        },
        "cascade_routing": {
            "threshold": effective_local_prefer_threshold(),
            "explicit": _is_env_explicit("LOCAL_PREFER_BELOW_COMPLEXITY"),
        },
        "auto_spawn": {
            "llamacpp": effective_auto_spawn("llamacpp"),
            "mlx": effective_auto_spawn("mlx"),
            "explicit": _is_env_explicit("LOCAL_RUNTIME_AUTO_SPAWN"),
            "llamacpp_binary_present": _has_binary(LLAMACPP_BIN),
            "mlx_binary_present": _has_binary(MLX_SERVER_BIN) or _has_dep("mlx_lm"),
        },
    }


def log_capabilities_at_startup() -> None:
    """Emit a single structured log line at startup so operators see what auto-activation chose."""
    snap = runtime_capabilities_snapshot()
    log.info("runtime_capabilities_resolved", **snap)
