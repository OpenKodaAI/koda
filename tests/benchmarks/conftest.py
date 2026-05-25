"""Shared bench helpers: load JSON baselines, perf_counter wrappers."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from time import perf_counter_ns
from typing import Any

import pytest

BASELINES_DIR = Path(__file__).resolve().parent / "baselines"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("KODA_RUN_BENCHMARKS") == "1":
        return

    skip = pytest.mark.skip(reason="benchmarks run in the dedicated benchmarks workflow")
    benchmarks_dir = Path(__file__).resolve().parent
    for item in items:
        raw_path = getattr(item, "path", None)
        if raw_path is None:
            raw_path = item.fspath
        item_path = Path(str(raw_path)).resolve()
        if item_path == benchmarks_dir or benchmarks_dir in item_path.parents:
            item.add_marker(skip)


def load_baseline(name: str) -> dict[str, Any]:
    path = BASELINES_DIR / f"{name}.json"
    with path.open(encoding="utf-8") as handle:
        return dict(json.load(handle))


def measure_ns_per_op(fn: Callable[[], Any], *, iters: int = 10_000, warmup: int = 100) -> float:
    """Median ns/op across 5 batches of ``iters`` calls. Median (not
    mean) makes the result stable under GC pauses and scheduler
    noise. Returns float — fractional ns is meaningful when iters is
    large."""
    for _ in range(warmup):
        fn()
    samples: list[float] = []
    for _ in range(5):
        start = perf_counter_ns()
        for _ in range(iters):
            fn()
        elapsed = perf_counter_ns() - start
        samples.append(elapsed / iters)
    samples.sort()
    return samples[len(samples) // 2]


async def measure_async_ns_per_op(
    fn: Callable[[], Any],
    *,
    iters: int = 5_000,
    warmup: int = 50,
) -> float:
    """Async variant — fn must return an awaitable each call."""
    for _ in range(warmup):
        await fn()
    samples: list[float] = []
    for _ in range(5):
        start = perf_counter_ns()
        for _ in range(iters):
            await fn()
        elapsed = perf_counter_ns() - start
        samples.append(elapsed / iters)
    samples.sort()
    return samples[len(samples) // 2]
