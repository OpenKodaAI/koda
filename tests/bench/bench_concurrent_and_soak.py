"""Concurrency + soak test for the Koda llama.cpp runner.

Exercises three properties that mocked tests can't catch:

1. **Concurrent multi-agent inference**: 10 simultaneous requests through
   ``run_llamacpp`` against a single ``llama-server`` process. Must all
   complete with valid responses, no deadlocks, no exceptions, no corrupted
   token streams.

2. **Sequential soak**: N=200 inferences one after another. Track RSS,
   open file descriptors, and child processes; assert no monotonic growth.
   This is the path that would surface socket leaks, KV cache leaks in the
   client, or zombie subprocesses.

3. **Mixed workload**: 5 concurrent + 100 sequential interleaved, so we
   stress the supervisor's slot lock while also asking the runner to
   accumulate FDs/sockets.

Run after starting llama-server on port 8089 (same as the bench script).
Designed for ad-hoc validation; not part of the regular pytest suite.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import koda.config  # noqa: E402

# Ensure llamacpp is enabled and points at our test server BEFORE importing
# the runner — its module-level profile uses these env vars.
os.environ["LLAMACPP_ENABLED"] = "true"
os.environ["LLAMACPP_API_BASE_URL"] = "http://127.0.0.1:8089"
os.environ["LLAMACPP_DEFAULT_MODEL"] = "qwen"
os.environ["LLAMACPP_FIRST_CHUNK_TIMEOUT"] = "60"
os.environ["LLAMACPP_TIMEOUT"] = "120"
os.environ.setdefault("STRUCTURED_DECODING_ENABLED", "false")  # focus on raw runner reliability

import importlib  # noqa: E402

importlib.reload(koda.config)
import koda.services.llamacpp_runner as llamacpp_runner  # noqa: E402

importlib.reload(llamacpp_runner)
from koda.services.llamacpp_runner import run_llamacpp  # noqa: E402
from koda.services.openai_compatible_runner import (  # noqa: E402
    clear_openai_compatible_capability_cache,
)


def snapshot_process(p: psutil.Process) -> dict[str, int]:
    """Capture RSS bytes, open FD count, and number of child processes."""
    return {
        "rss": p.memory_info().rss,
        "fds": p.num_fds() if hasattr(p, "num_fds") else 0,
        "children": len(p.children(recursive=True)),
    }


async def _one_call(idx: int, prompt: str) -> tuple[bool, str, float]:
    t0 = time.perf_counter()
    result = await run_llamacpp(
        query=prompt,
        work_dir="/tmp",
        model="qwen",
        system_prompt="Be terse.",
    )
    elapsed = time.perf_counter() - t0
    if result.get("error"):
        return False, str(result.get("result", ""))[:120], elapsed
    text = str(result.get("result", "")).strip()
    if not text or text == "Task completed (no text output).":
        return False, "empty response", elapsed
    return True, text[:120], elapsed


async def run_concurrent(n: int) -> dict[str, object]:
    """N coroutines hit run_llamacpp at the same time."""
    clear_openai_compatible_capability_cache()
    prompts = [f"Reply with only the number {i}." for i in range(n)]
    started = time.perf_counter()
    results = await asyncio.gather(
        *(_one_call(i, p) for i, p in enumerate(prompts)),
        return_exceptions=True,
    )
    wallclock = time.perf_counter() - started

    successes = sum(1 for r in results if isinstance(r, tuple) and r[0])
    failures = [r for r in results if not isinstance(r, tuple) or not r[0]]
    latencies = [r[2] for r in results if isinstance(r, tuple)]
    return {
        "n": n,
        "successes": successes,
        "failures": len(failures),
        "wallclock_s": round(wallclock, 2),
        "p50_latency_ms": round(statistics.median(latencies) * 1000, 1) if latencies else 0,
        "p95_latency_ms": round(sorted(latencies)[int(len(latencies) * 0.95)] * 1000, 1) if latencies else 0,
        "max_latency_ms": round(max(latencies) * 1000, 1) if latencies else 0,
        "first_failure_sample": str(failures[0])[:200] if failures else None,
    }


async def run_soak(n: int, sample_every: int = 25) -> dict[str, object]:
    """Sequential inferences, sampling resources every ``sample_every`` calls."""
    clear_openai_compatible_capability_cache()
    me = psutil.Process()
    samples: list[dict[str, int]] = [snapshot_process(me)]

    started = time.perf_counter()
    success_count = 0
    failure_count = 0
    for i in range(n):
        ok, _text, _elapsed = await _one_call(i, f"Reply only with: {i}")
        if ok:
            success_count += 1
        else:
            failure_count += 1
        if (i + 1) % sample_every == 0:
            samples.append(snapshot_process(me))

    wallclock = time.perf_counter() - started
    samples.append(snapshot_process(me))

    rss_growth_mb = (samples[-1]["rss"] - samples[0]["rss"]) / 1e6
    fd_growth = samples[-1]["fds"] - samples[0]["fds"]
    child_growth = samples[-1]["children"] - samples[0]["children"]

    return {
        "n": n,
        "successes": success_count,
        "failures": failure_count,
        "wallclock_s": round(wallclock, 1),
        "throughput_per_s": round(n / wallclock, 2),
        "samples": [
            {
                "rss_mb": round(s["rss"] / 1e6, 1),
                "fds": s["fds"],
                "children": s["children"],
            }
            for s in samples
        ],
        "rss_growth_mb": round(rss_growth_mb, 1),
        "fd_growth": fd_growth,
        "child_growth": child_growth,
    }


async def run_mixed() -> dict[str, object]:
    """5 concurrent batches of 20 sequential calls."""
    clear_openai_compatible_capability_cache()
    me = psutil.Process()
    s0 = snapshot_process(me)

    async def batch(batch_id: int) -> tuple[int, int]:
        ok, fail = 0, 0
        for i in range(20):
            success, _, _ = await _one_call(i, f"Batch {batch_id}, call {i}: respond OK.")
            if success:
                ok += 1
            else:
                fail += 1
        return ok, fail

    started = time.perf_counter()
    results = await asyncio.gather(*(batch(i) for i in range(5)))
    wallclock = time.perf_counter() - started

    s1 = snapshot_process(me)
    return {
        "wallclock_s": round(wallclock, 1),
        "successes": sum(r[0] for r in results),
        "failures": sum(r[1] for r in results),
        "rss_growth_mb": round((s1["rss"] - s0["rss"]) / 1e6, 1),
        "fd_growth": s1["fds"] - s0["fds"],
        "child_growth": s1["children"] - s0["children"],
    }


def check_zombies() -> list[str]:
    """Return cmdlines of any llama-server children of this process."""
    out = subprocess.run(["ps", "-eo", "pid,ppid,command"], check=False, capture_output=True, text=True, timeout=5)
    my_pid = os.getpid()
    leaks: list[str] = []
    for line in out.stdout.splitlines()[1:]:
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        try:
            ppid = int(parts[1])
        except ValueError:
            continue
        if ppid == my_pid and "llama-server" in parts[2]:
            leaks.append(parts[2])
    return leaks


async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--concurrent", type=int, default=10)
    p.add_argument("--soak", type=int, default=200)
    args = p.parse_args()

    print("=" * 70)
    print("CONCURRENT")
    print("=" * 70)
    conc = await run_concurrent(args.concurrent)
    for k, v in conc.items():
        print(f"  {k}: {v}")

    print()
    print("=" * 70)
    print("MIXED (5 concurrent batches of 20 sequential)")
    print("=" * 70)
    mixed = await run_mixed()
    for k, v in mixed.items():
        print(f"  {k}: {v}")

    print()
    print("=" * 70)
    print(f"SOAK ({args.soak} sequential calls)")
    print("=" * 70)
    soak = await run_soak(args.soak)
    for k, v in soak.items():
        if k == "samples":
            print(f"  samples ({len(v)} taken):")
            for i, s in enumerate(v):
                print(f"    [{i}] {s}")
        else:
            print(f"  {k}: {v}")

    print()
    print("=" * 70)
    print("LEAK CHECK")
    print("=" * 70)
    zombies = check_zombies()
    if zombies:
        print(f"  ❌ Found {len(zombies)} llama-server child of this process:")
        for z in zombies:
            print(f"     {z}")
        return 1
    print("  ✅ No llama-server zombies. Clean exit.")

    # Final overall verdict
    all_ok = (
        conc["failures"] == 0
        and mixed["failures"] == 0
        and soak["failures"] == 0
        and not zombies
        and soak["fd_growth"] < 10  # tolerate tiny growth (logging buffers, etc.)
        and soak["child_growth"] == 0
        and soak["rss_growth_mb"] < 50  # tolerate small caching growth
    )

    print()
    print("=" * 70)
    print(f"VERDICT: {'✅ ALL CHECKS PASSED' if all_ok else '❌ FAILURES OBSERVED'}")
    print("=" * 70)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
