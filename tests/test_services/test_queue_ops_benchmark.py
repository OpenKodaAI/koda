from __future__ import annotations

import pytest

import scripts.ops_benchmark as ops_benchmark


@pytest.mark.asyncio
async def test_ops_benchmark_quick_proves_queue_runtime_channel_fault_contract() -> None:
    result = await ops_benchmark.run_ops_benchmark(full=False)
    failures = ops_benchmark.evaluate_ops_benchmark(result)

    assert failures == []
    assert result["schema_version"] == "ops_benchmark.v1"
    assert result["mode"] == "quick"


@pytest.mark.asyncio
async def test_ops_benchmark_full_mode_is_opt_in_and_deterministic() -> None:
    result = await ops_benchmark.run_ops_benchmark(full=True)
    failures = ops_benchmark.evaluate_ops_benchmark(result)
    queue_step = next(item for item in result["results"] if item["step"] == "queue_runtime")

    assert failures == []
    assert result["mode"] == "full"
    assert queue_step["task_count"] > 3
    assert all(count == 1 for count in queue_step["run_counts"].values())


def test_ops_benchmark_evaluator_fails_on_missing_terminal_state() -> None:
    result = {
        "schema_version": "ops_benchmark.v1",
        "results": [
            {
                "step": "queue_runtime",
                "no_double_run": True,
                "terminal_state_for_all_tasks": False,
                "timeout_observed": True,
                "dlq_observed": True,
                "no_infinite_loading": True,
                "cleanup_ok": True,
            },
            {
                "step": "queue_recovery",
                "dlq_observed": True,
                "terminal_state": True,
                "finalized": True,
                "status_update_called": True,
            },
            {
                "step": "channel_backpressure",
                "publisher_returned": True,
                "healthy_subscriber_received": True,
                "full_subscriber_dropped": True,
            },
        ],
    }

    failures = ops_benchmark.evaluate_ops_benchmark(result)

    assert "queue_runtime.terminal_state_for_all_tasks expected True; got False" in failures


def test_ops_benchmark_script_passes_quick_mode(capsys: pytest.CaptureFixture[str]) -> None:
    from koda.services.metrics import OPS_BENCHMARK_RUNS

    child = OPS_BENCHMARK_RUNS.labels(mode="quick", status="passed")
    before = float(child._value.get()) if hasattr(child, "_value") else 0.0
    result = ops_benchmark.main([])
    after = float(child._value.get()) if hasattr(child, "_value") else 0.0

    assert result == 0
    assert "ops benchmark passed (quick)" in capsys.readouterr().out
    if after > before:
        assert after == before + 1
