"""Shared embedding helpers with auto-device selection + per-text LRU cache.

Behavior contract:

- ``embed_text(text, *, model_name)`` and ``embed_batch(texts, *, model_name)``
  keep their existing signatures (graceful fallback to a hash vector if
  ``sentence-transformers`` is missing).
- Device is resolved automatically: MPS on Apple Silicon, CUDA on Linux
  GPU, CPU otherwise. Override via ``EMBEDDING_DEVICE`` (cpu|mps|cuda|auto).
- A bounded per-(model, text) LRU eliminates redundant encode() calls when
  the same query is touched multiple times in one turn (memory recall +
  cache lookup + skills index regularly share queries).
- ``resolve_active_embedding_repo()`` reports the operator's selected
  embedding model from the control-plane settings DB, falling back to the
  ``MEMORY_EMBEDDING_MODEL`` env var, falling back to the catalog default.
  Callers that want runtime-aware behavior call this; the fixed
  ``MEMORY_EMBEDDING_MODEL`` constant remains for legacy code that needs
  a value at import time.

Why this lives here:
- Auto device: SentenceTransformer was previously instantiated with no
  device argument, defaulting to CPU. Bench-confirmed: MPS gives 1.8-2.2x
  on Apple Silicon for batch=100 (65.7ms → 29.5ms for paraphrase-MiniLM-L12-v2).
- LRU cache: callers in cache_manager._lookup_primary_semantic, recall.py,
  knowledge_manager, skills/_index, script_manager often see the same text
  multiple times in one turn — caching is free quality.
"""

from __future__ import annotations

import logging
import math
import os
import threading
from collections import OrderedDict
from typing import Any, cast

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Device resolution
# ---------------------------------------------------------------------------


def _resolve_device(requested: str | None = None) -> str:
    """Pick the best available device.

    ``EMBEDDING_DEVICE`` env var overrides; ``auto`` (default) probes:
    MPS on Apple Silicon → CUDA on Linux GPU → CPU.
    """
    raw = (requested or os.environ.get("EMBEDDING_DEVICE") or "auto").strip().lower()
    if raw in ("cpu", "mps", "cuda"):
        return raw
    try:
        import torch  # noqa: PLC0415
    except ImportError:
        return "cpu"
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


# ---------------------------------------------------------------------------
# Model cache (per (model_name, device))
# ---------------------------------------------------------------------------


_embed_models: dict[tuple[str, str], Any] = {}
_missing_models: set[str] = set()
_model_lock = threading.Lock()


def load_sentence_transformer(model_name: str, device: str | None = None) -> Any | None:
    """Return a cached SentenceTransformer instance when available locally.

    Always loads with ``local_files_only=True`` — Koda never auto-downloads
    embedding weights from this code path. Operators must explicitly download
    a model through the system settings UI (which uses
    ``huggingface_hub.snapshot_download`` directly). This keeps a fresh
    install lightweight and gives operators full control over what lands on
    disk. When weights are missing the runtime falls back to
    :func:`fallback_text_vector` so retrieval keeps working with a
    bag-of-words approximation.
    """
    resolved_device = _resolve_device(device)
    cache_key = (model_name, resolved_device)
    if cache_key in _embed_models:
        return _embed_models[cache_key]
    if model_name in _missing_models:
        return None
    with _model_lock:
        if cache_key in _embed_models:
            return _embed_models[cache_key]
        if model_name in _missing_models:
            return None
        try:
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415

            kwargs: dict[str, Any] = {
                "device": resolved_device,
                "local_files_only": True,
            }
            # Some modern multilingual models require remote code (e.g. gte-*).
            if "gte" in model_name.lower():
                kwargs["trust_remote_code"] = True
            model = SentenceTransformer(model_name, **kwargs)
            _embed_models[cache_key] = model
            logger.info(
                "sentence_transformer_loaded",
                extra={"model": model_name, "device": resolved_device},
            )
            return model
        except Exception as exc:  # noqa: BLE001
            _missing_models.add(model_name)
            logger.info(
                "sentence_transformer_unavailable_falling_back",
                extra={"model_name": model_name, "reason": type(exc).__name__},
            )
            return None


def reset_embedding_load_cache(model_name: str | None = None) -> None:
    """Drop cached load failures so a freshly-downloaded model is picked up.

    Called from the control-plane manager after a successful UI download.
    Without this, an earlier load attempt that failed (because the model
    wasn't on disk) would have stuck the model in ``_missing_models`` and
    every subsequent ``load_sentence_transformer`` call would short-circuit
    to ``None`` even though the weights are now present.
    """
    with _model_lock:
        if model_name is None:
            _embed_models.clear()
            _missing_models.clear()
            return
        _missing_models.discard(model_name)
        for key in list(_embed_models.keys()):
            if key[0] == model_name:
                _embed_models.pop(key, None)


# ---------------------------------------------------------------------------
# Per-(model, text) LRU cache
# ---------------------------------------------------------------------------

_EMBED_CACHE_MAX_ENTRIES = int(os.environ.get("EMBEDDING_TEXT_CACHE_SIZE", "1024"))
_embed_cache: OrderedDict[tuple[str, str], list[float]] = OrderedDict()
_cache_lock = threading.Lock()
_cache_hits = 0
_cache_misses = 0


def _cache_get(model_name: str, text: str) -> list[float] | None:
    global _cache_hits, _cache_misses
    key = (model_name, text)
    with _cache_lock:
        existing = _embed_cache.get(key)
        if existing is None:
            _cache_misses += 1
            return None
        _embed_cache.move_to_end(key)
        _cache_hits += 1
        return existing


def _cache_put(model_name: str, text: str, vector: list[float]) -> None:
    key = (model_name, text)
    with _cache_lock:
        _embed_cache[key] = vector
        _embed_cache.move_to_end(key)
        while len(_embed_cache) > _EMBED_CACHE_MAX_ENTRIES:
            _embed_cache.popitem(last=False)


def embed_cache_stats() -> dict[str, int]:
    with _cache_lock:
        return {
            "hits": _cache_hits,
            "misses": _cache_misses,
            "size": len(_embed_cache),
            "max_entries": _EMBED_CACHE_MAX_ENTRIES,
        }


def reset_embed_cache_for_tests() -> None:
    global _cache_hits, _cache_misses
    with _cache_lock:
        _embed_cache.clear()
        _cache_hits = 0
        _cache_misses = 0


# ---------------------------------------------------------------------------
# Fallback hash-based vector
# ---------------------------------------------------------------------------


def fallback_text_vector(text: str, *, dim: int = 128) -> list[float]:
    """Produce a deterministic hashed term-frequency vector."""
    terms = text.lower().split()
    freq: dict[int, float] = {}
    for term in terms:
        bucket = hash(term) % dim
        freq[bucket] = freq.get(bucket, 0.0) + 1.0
    vector = [freq.get(i, 0.0) for i in range(dim)]
    norm = math.sqrt(sum(value * value for value in vector))
    if norm > 0:
        vector = [value / norm for value in vector]
    return vector


# ---------------------------------------------------------------------------
# Public API (signature-compatible with the previous version)
# ---------------------------------------------------------------------------


def embed_text_with_model(text: str, model: Any | None) -> list[float]:
    if model is not None:
        encoded = model.encode(text, normalize_embeddings=True)
        return cast(list[float], encoded.tolist())
    return fallback_text_vector(text)


def embed_batch_with_model(texts: list[str], model: Any | None) -> list[list[float]]:
    if not texts:
        return []
    if model is not None:
        result = model.encode(texts, normalize_embeddings=True)
        return cast(list[list[float]], result.tolist())
    return [fallback_text_vector(text) for text in texts]


def embed_text(text: str, *, model_name: str) -> list[float]:
    """Embed *text*, hitting the LRU cache before invoking the model."""
    cached = _cache_get(model_name, text)
    if cached is not None:
        return cached
    model = load_sentence_transformer(model_name)
    vector = embed_text_with_model(text, model)
    if model is not None:
        _cache_put(model_name, text, vector)
    return vector


def embed_batch(texts: list[str], *, model_name: str) -> list[list[float]]:
    """Embed a batch, mixing cache hits with a single batch call for misses.

    Order is preserved so the caller can zip the result back to the input.
    """
    if not texts:
        return []
    results: list[list[float] | None] = []
    misses_idx: list[int] = []
    misses_text: list[str] = []
    for i, text in enumerate(texts):
        cached = _cache_get(model_name, text)
        if cached is not None:
            results.append(cached)
        else:
            results.append(None)
            misses_idx.append(i)
            misses_text.append(text)
    if not misses_text:
        return cast(list[list[float]], results)
    model = load_sentence_transformer(model_name)
    new_vectors = embed_batch_with_model(misses_text, model)
    for idx, text, vector in zip(misses_idx, misses_text, new_vectors, strict=True):
        results[idx] = vector
        if model is not None:
            _cache_put(model_name, text, vector)
    return cast(list[list[float]], results)


# ---------------------------------------------------------------------------
# Active embedding model resolution (DB → env → catalog default)
# ---------------------------------------------------------------------------


def resolve_active_embedding_repo() -> str:
    """Return the Hugging Face repo id the runtime should embed with.

    Lookup order:
      1. ``cp_global_sections.memory.embedding_model`` (operator pick via UI),
         resolved through the curated catalog to the underlying repo id.
      2. ``MEMORY_EMBEDDING_MODEL`` env var (legacy override or container
         deployments without a Postgres-backed control plane).
      3. ``embedding_catalog.DEFAULT_MODEL_ID`` repo id — the model Koda
         ships pre-installed.

    Best-effort: if any step raises (DB unavailable, missing dep, etc.),
    we fall through to the next layer. Returning a string always.
    """
    try:
        from koda.services.embedding_catalog import (  # noqa: PLC0415
            CATALOG,
            DEFAULT_MODEL_ID,
        )
    except ImportError:
        # Catalog unavailable; trust the env var or a hard-coded fallback.
        return os.environ.get("MEMORY_EMBEDDING_MODEL") or "paraphrase-multilingual-MiniLM-L12-v2"

    try:
        from koda.state.control_plane_store import fetch_one  # noqa: PLC0415

        row = fetch_one(
            "SELECT data_json FROM cp_global_sections WHERE section = ?",
            ("memory",),
        )
        if row is not None:
            import json  # noqa: PLC0415

            data = json.loads(row.get("data_json") or "{}")
            chosen_id = str(data.get("embedding_model") or "").strip()
            if chosen_id and chosen_id in CATALOG:
                return CATALOG[chosen_id].repo_id
    except Exception:  # noqa: BLE001 — DB lookup is best-effort
        pass

    env_repo = (os.environ.get("MEMORY_EMBEDDING_MODEL") or "").strip()
    if env_repo:
        return env_repo

    return CATALOG[DEFAULT_MODEL_ID].repo_id
