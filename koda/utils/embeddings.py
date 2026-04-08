"""Shared embedding helpers with an optional SentenceTransformer backend."""

from __future__ import annotations

import logging
import math
from typing import Any, cast

logger = logging.getLogger(__name__)

_embed_models: dict[str, Any] = {}
_missing_models: set[str] = set()


def load_sentence_transformer(model_name: str) -> Any | None:
    """Return a cached SentenceTransformer instance when the dependency exists."""
    if model_name in _embed_models:
        return _embed_models[model_name]
    if model_name in _missing_models:
        return None
    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(model_name)
        _embed_models[model_name] = model
        return model
    except Exception as exc:  # noqa: BLE001
        _missing_models.add(model_name)
        logger.info(
            "sentence_transformer_unavailable_falling_back",
            extra={"model_name": model_name, "reason": type(exc).__name__},
        )
        return None


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


def embed_text_with_model(text: str, model: Any | None) -> list[float]:
    """Embed *text* with an explicit model instance when available."""
    if model is not None:
        encoded = model.encode(text, normalize_embeddings=True)
        return cast(list[float], encoded.tolist())
    return fallback_text_vector(text)


def embed_batch_with_model(texts: list[str], model: Any | None) -> list[list[float]]:
    """Embed *texts* with an explicit model instance when available."""
    if not texts:
        return []
    if model is not None:
        result = model.encode(texts, normalize_embeddings=True)
        return cast(list[list[float]], result.tolist())
    return [fallback_text_vector(text) for text in texts]


def embed_text(text: str, *, model_name: str) -> list[float]:
    """Embed *text* with SentenceTransformer when available, else fallback."""
    model = load_sentence_transformer(model_name)
    return embed_text_with_model(text, model)


def embed_batch(texts: list[str], *, model_name: str) -> list[list[float]]:
    """Embed a batch of texts with SentenceTransformer when available, else fallback."""
    model = load_sentence_transformer(model_name)
    return embed_batch_with_model(texts, model)
