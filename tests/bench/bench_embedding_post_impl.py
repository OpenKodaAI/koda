"""Post-implementation benchmark.

Measures the SAME quality + performance corpora as ``bench_embedding_models.py``
but goes through the production code paths in ``koda.utils.embeddings`` and
``koda.services.reranker`` so we can validate:

1. **Auto-MPS device** is now active (latency drop on b=10/100).
2. **Per-text LRU cache** reduces repeat encode cost.
3. **Reranker uplift** is measurable when the model + reranker are loaded.
4. **Production callers** all benefit (cache_manager, knowledge, skills,
   script_manager) — we don't need to test each call site here, the unit
   tests cover that. We just confirm the underlying primitives work.

Output a side-by-side comparison vs the pre-implementation results.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


# Same corpus as the model bench
from tests.bench.bench_embedding_models import (  # noqa: E402
    CROSS_LINGUAL_PAIRS,
    PARAPHRASE_PAIRS_EN,
    PARAPHRASE_PAIRS_PT,
    RANDOM_NEGATIVES_EN,
    RANDOM_NEGATIVES_PT,
    RANKING_CORPUS,
    auc_paraphrase,
    cosine,
    ranking_metrics,
)


def measure_quality_with_production(model_name: str) -> dict[str, float]:
    """Run the full quality suite using koda.utils.embeddings (post-impl path)."""
    from koda.utils.embeddings import embed_batch  # noqa: PLC0415

    def prep(_model: object, texts: list[str], *, role: str = "passage") -> list[list[float]]:
        # The production path doesn't (yet) prefix texts based on model — that's
        # an extra refinement we keep as a future option. Here we test the
        # ACTUAL production path including the LRU cache.
        return embed_batch(texts, model_name=model_name)

    return {
        "auc_paraphrase_pt": round(auc_paraphrase(None, prep, PARAPHRASE_PAIRS_PT, RANDOM_NEGATIVES_PT), 4),
        "auc_paraphrase_en": round(auc_paraphrase(None, prep, PARAPHRASE_PAIRS_EN, RANDOM_NEGATIVES_EN), 4),
        "auc_cross_lingual": round(
            auc_paraphrase(None, prep, CROSS_LINGUAL_PAIRS, RANDOM_NEGATIVES_EN + RANDOM_NEGATIVES_PT), 4
        ),
        **{f"ranking_{k}": v for k, v in ranking_metrics(None, prep, RANKING_CORPUS).items()},
    }


def measure_perf_with_production(model_name: str, sample: str = "como deployar serviço") -> dict[str, float]:
    from koda.utils.embeddings import embed_batch, embed_text, reset_embed_cache_for_tests  # noqa: PLC0415

    me = psutil.Process()
    rss_baseline = me.memory_info().rss / 1e6

    # Cold start — first invocation triggers model load
    t0 = time.perf_counter()
    _ = embed_text(sample, model_name=model_name)
    cold_start_ms = (time.perf_counter() - t0) * 1000
    rss_after_load = me.memory_info().rss / 1e6

    # Warmup
    for _ in range(3):
        _ = embed_text(sample, model_name=model_name)
        _ = embed_batch([sample] * 10, model_name=model_name)

    # b=1 (cache-hit dominant — same text repeated)
    reset_embed_cache_for_tests()
    latencies_b1: list[float] = []
    for i in range(20):
        t0 = time.perf_counter()
        _ = embed_text(f"{sample}-{i}", model_name=model_name)  # unique text → cache miss
        latencies_b1.append((time.perf_counter() - t0) * 1000)

    # b=1 (cache-hit only — repeat the same string)
    reset_embed_cache_for_tests()
    _ = embed_text(sample, model_name=model_name)  # warm cache
    latencies_b1_cached: list[float] = []
    for _ in range(20):
        t0 = time.perf_counter()
        _ = embed_text(sample, model_name=model_name)
        latencies_b1_cached.append((time.perf_counter() - t0) * 1000)

    # b=10
    reset_embed_cache_for_tests()
    latencies_b10: list[float] = []
    for i in range(10):
        t0 = time.perf_counter()
        _ = embed_batch([f"{sample}-{j}-{i}" for j in range(10)], model_name=model_name)
        latencies_b10.append((time.perf_counter() - t0) * 1000)

    # b=100
    reset_embed_cache_for_tests()
    latencies_b100: list[float] = []
    rss_peak = rss_after_load
    for i in range(5):
        t0 = time.perf_counter()
        _ = embed_batch([f"{sample}-{j}-{i}" for j in range(100)], model_name=model_name)
        latencies_b100.append((time.perf_counter() - t0) * 1000)
        rss_peak = max(rss_peak, me.memory_info().rss / 1e6)

    return {
        "cold_start_ms": round(cold_start_ms, 1),
        "latency_p50_b1_ms": round(statistics.median(latencies_b1), 2),
        "latency_p50_b1_cached_ms": round(statistics.median(latencies_b1_cached), 3),
        "latency_p50_b10_ms": round(statistics.median(latencies_b10), 2),
        "latency_p50_b100_ms": round(statistics.median(latencies_b100), 2),
        "rss_baseline_mb": round(rss_baseline, 1),
        "rss_after_load_mb": round(rss_after_load, 1),
        "rss_peak_mb": round(rss_peak, 1),
    }


def device_in_use(model_name: str) -> str:
    """Inspect the loaded SentenceTransformer to see which device it actually picked."""
    from koda.utils.embeddings import load_sentence_transformer  # noqa: PLC0415

    model = load_sentence_transformer(model_name)
    if model is None:
        return "fallback"
    try:
        return str(model.device)
    except Exception:  # noqa: BLE001
        return "unknown"


def measure_reranker_uplift(model_name: str) -> dict[str, float] | None:
    """Compute reranker uplift on the ranking corpus, only if reranker is available."""
    try:
        from koda.services.reranker import is_enabled  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return None
    if not is_enabled():
        return None

    from koda.services.reranker import _load_model  # noqa: PLC0415

    if _load_model() is None:
        return None  # reranker model failed to load (HF rate limit etc.)

    import math  # noqa: PLC0415

    from koda.services.reranker import rerank_top_k_indices  # noqa: PLC0415
    from koda.utils.embeddings import embed_batch  # noqa: PLC0415

    ndcg_baseline: list[float] = []
    ndcg_reranked: list[float] = []
    for case in RANKING_CORPUS:
        candidates = case.relevant + case.distractors
        relevant_set = set(case.relevant)
        embs = embed_batch([case.query, *candidates], model_name=model_name)
        q_emb = embs[0]
        cand_embs = embs[1:]
        scored = sorted(
            ((i, cosine(q_emb, e)) for i, e in enumerate(cand_embs)),
            key=lambda x: x[1],
            reverse=True,
        )
        ranked_docs = [candidates[i] for i, _ in scored]
        # Baseline nDCG@5
        dcg = sum((1.0 / math.log2(i + 2)) for i in range(5) if i < len(ranked_docs) and ranked_docs[i] in relevant_set)
        idcg = sum(1.0 / math.log2(i + 2) for i in range(min(5, len(relevant_set))))
        ndcg_baseline.append(dcg / idcg if idcg > 0 else 0.0)

        # Reranked top-5
        top5 = ranked_docs[:5]
        new_order = rerank_top_k_indices(case.query, top5, top_k=5)
        if new_order is not None:
            reranked_top5 = [top5[i] for i in new_order]
            full = reranked_top5 + ranked_docs[5:]
        else:
            full = ranked_docs
        dcg = sum((1.0 / math.log2(i + 2)) for i in range(5) if i < len(full) and full[i] in relevant_set)
        ndcg_reranked.append(dcg / idcg if idcg > 0 else 0.0)

    return {
        "ndcg5_baseline": round(statistics.mean(ndcg_baseline), 4),
        "ndcg5_with_reranker": round(statistics.mean(ndcg_reranked), 4),
        "uplift_pp": round((statistics.mean(ndcg_reranked) - statistics.mean(ndcg_baseline)) * 100, 2),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="paraphrase-multilingual-MiniLM-L12-v2")
    p.add_argument("--out", default="/tmp/embedding_bench_post.json")
    args = p.parse_args()

    print(f"=== Post-implementation bench: {args.model} ===")
    print(f"Device: {device_in_use(args.model)}")

    print("\nMeasuring performance through production embeddings.py...")
    perf = measure_perf_with_production(args.model)
    for k, v in perf.items():
        print(f"  {k}: {v}")

    print("\nMeasuring quality through production embeddings.py...")
    quality = measure_quality_with_production(args.model)
    for k, v in quality.items():
        print(f"  {k}: {v}")

    print("\nMeasuring reranker uplift (if available)...")
    uplift = measure_reranker_uplift(args.model)
    if uplift is None:
        print("  [reranker unavailable — skipping uplift]")
    else:
        for k, v in uplift.items():
            print(f"  {k}: {v}")

    payload: dict[str, object] = {
        "model": args.model,
        "device": device_in_use(args.model),
        "performance": perf,
        "quality": quality,
        "reranker_uplift": uplift,
    }
    Path(args.out).write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"\nFull payload written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
