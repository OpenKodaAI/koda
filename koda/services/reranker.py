"""Cross-encoder reranking for memory + knowledge retrieval.

Cross-encoder rerankers score (query, document) pairs jointly, capturing
relevance signals that bi-encoder embeddings miss. ``BAAI/bge-reranker-v2-m3``
is the current sweet spot for multilingual / multi-hop retrieval — small
enough to run on Apple Silicon at single-digit ms per query (MPS device),
large enough to outperform every open lexical baseline by a wide margin on
modern benchmarks.

We deliberately use ``sentence_transformers.CrossEncoder`` rather than
``FlagEmbedding.FlagReranker``: the FlagEmbedding 1.4.0 ``compute_score``
path raises ``XLMRobertaTokenizer has no attribute prepare_for_model``
under transformers ≥5.0 (which is what Koda pins). The CrossEncoder API
is the canonical sentence-transformers interface, has identical model
support (same BGE checkpoints), and stays compatible across the
transformers 4.x → 5.x boundary. Validated end-to-end on M4 Pro / CPU:
94 ms for 6 (query, doc) pairs, scores with meaningful gradient.

Integration is intentionally non-fatal: if the model fails to load or score,
:func:`rerank_sync` returns the original ordering untouched. Callers
(:mod:`koda.memory.recall`, :mod:`koda.services.knowledge_orchestration_service`)
treat the reranker as a quality bolt-on, never as a dependency.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Sequence
from typing import Any

from koda.config import RERANK_DEVICE, RERANK_MODEL, RERANK_TOP_K
from koda.logging_config import get_logger

log = get_logger(__name__)

_MODEL_LOCK = threading.Lock()
_MODEL_INSTANCE: Any | None = None
_MODEL_FAILED: bool = False


def _resolve_device(requested: str) -> str:
    requested = (requested or "auto").strip().lower()
    if requested != "auto":
        return requested
    try:
        import torch  # noqa: PLC0415
    except ImportError:
        return "cpu"
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _load_model() -> Any | None:
    """Lazy-load the cross-encoder. Returns None if loading fails.

    Uses ``sentence_transformers.CrossEncoder`` (canonical, transformers-5
    compatible). First call downloads the model (~280 MB for the small
    bge-reranker; ~570 MB for v2-m3) and pays a one-time load cost
    (~5-10 s on Apple Silicon CPU; faster on MPS). Subsequent calls reuse
    the module-level singleton.
    """
    global _MODEL_INSTANCE, _MODEL_FAILED
    if _MODEL_FAILED:
        return None
    if _MODEL_INSTANCE is not None:
        return _MODEL_INSTANCE
    with _MODEL_LOCK:
        if _MODEL_INSTANCE is not None:
            return _MODEL_INSTANCE
        if _MODEL_FAILED:
            return None
        try:
            from sentence_transformers import CrossEncoder  # noqa: PLC0415

            device = _resolve_device(RERANK_DEVICE)
            log.info("reranker_loading", model=RERANK_MODEL, device=device)
            started = time.monotonic()
            instance = CrossEncoder(RERANK_MODEL, device=device)
            elapsed = time.monotonic() - started
            log.info("reranker_loaded", model=RERANK_MODEL, device=device, elapsed_s=round(elapsed, 2))
            _MODEL_INSTANCE = instance
            return instance
        except Exception as exc:  # noqa: BLE001 — degrade gracefully
            log.warning(
                "reranker_load_failed",
                model=RERANK_MODEL,
                error=str(exc),
                hint="Install with `pip install sentence-transformers`. Reranker disabled for this run.",
            )
            _MODEL_FAILED = True
            return None


def is_enabled() -> bool:
    """Effective state — respects explicit env override, otherwise auto-resolves."""
    # Lazy import: ``runtime_capabilities`` itself imports config flags; keeping
    # this import inside the function keeps module-load order forgiving.
    from koda.services.runtime_capabilities import effective_rerank_enabled  # noqa: PLC0415

    return effective_rerank_enabled()


async def rerank_async(
    query: str,
    documents: Sequence[str],
    *,
    top_k: int | None = None,
) -> list[tuple[int, float]]:
    """Score (query, document) pairs and return ``[(index, score), ...]`` sorted descending.

    Documents that fail to score keep their original order at the tail. The
    return list always has at most ``top_k`` entries (default ``RERANK_TOP_K``).
    On any failure path the function returns identity ordering with score 0.0
    so callers can fall through to the score they already had.
    """
    if not is_enabled() or not documents:
        return [(i, 0.0) for i in range(min(len(documents), top_k or RERANK_TOP_K))]
    limit = top_k or RERANK_TOP_K

    def _score() -> list[tuple[int, float]]:
        model = _load_model()
        if model is None:
            return [(i, 0.0) for i in range(min(len(documents), limit))]
        pairs = [(query, doc) for doc in documents]
        try:
            raw_scores = model.predict(pairs)
        except Exception as exc:  # noqa: BLE001
            log.warning("reranker_score_failed", error=str(exc))
            return [(i, 0.0) for i in range(min(len(documents), limit))]
        scores = _normalize_scores(raw_scores)
        ranked = sorted(enumerate(scores), key=lambda pair: pair[1], reverse=True)
        return ranked[:limit]

    return await asyncio.to_thread(_score)


def rerank_sync(
    query: str,
    documents: Sequence[str],
    *,
    top_k: int | None = None,
) -> list[tuple[int, float]]:
    """Synchronous variant for non-async call sites (e.g. ``recall.py``)."""
    if not is_enabled() or not documents:
        return [(i, 0.0) for i in range(min(len(documents), top_k or RERANK_TOP_K))]
    limit = top_k or RERANK_TOP_K
    model = _load_model()
    if model is None:
        return [(i, 0.0) for i in range(min(len(documents), limit))]
    pairs = [(query, doc) for doc in documents]
    try:
        raw_scores = model.predict(pairs)
    except Exception as exc:  # noqa: BLE001
        log.warning("reranker_score_failed", error=str(exc))
        return [(i, 0.0) for i in range(min(len(documents), limit))]
    scores = _normalize_scores(raw_scores)
    ranked = sorted(enumerate(scores), key=lambda pair: pair[1], reverse=True)
    return ranked[:limit]


def rerank_top_k_indices(
    query: str,
    candidate_texts: list[str],
    *,
    top_k: int = 5,
) -> list[int] | None:
    """Re-order the first ``top_k`` candidates by reranker score.

    Returns the new index ordering for the top-K (full ordering, with the
    untouched tail concatenated). When the reranker is disabled / fails to
    load / scores fail, returns ``None`` so callers can keep their cosine
    ordering untouched. This is the helper meant for cache_manager,
    knowledge_manager, skills/_index and script_manager — each picks the
    top-K by cosine, calls this function, and falls through gracefully.
    """
    if not is_enabled() or not candidate_texts:
        return None
    if top_k <= 0:
        return None
    if len(candidate_texts) == 1:
        return [0]
    limit = min(top_k, len(candidate_texts))
    head_texts = candidate_texts[:limit]
    ranked = rerank_sync(query, head_texts, top_k=limit)
    if not ranked or all(score == 0.0 for _, score in ranked):
        return None
    head_order = [idx for idx, _ in ranked]
    tail = list(range(limit, len(candidate_texts)))
    return head_order + tail


def _normalize_scores(raw: Any) -> list[float]:
    """Coerce CrossEncoder.predict output (numpy array | list | scalar) to ``list[float]``."""
    if isinstance(raw, (int, float)):
        return [float(raw)]
    try:
        return [float(value) for value in raw]
    except TypeError:
        return [float(raw)]


def reset_for_tests() -> None:
    """Test hook: clear the cached model so the next call re-runs loading."""
    global _MODEL_INSTANCE, _MODEL_FAILED
    with _MODEL_LOCK:
        _MODEL_INSTANCE = None
        _MODEL_FAILED = False
