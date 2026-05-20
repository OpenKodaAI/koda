#!/usr/bin/env python3
"""Deterministic offline ops benchmark for queue/runtime/channel fault gates."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from koda.services.runtime.events import RuntimeEventBroker

OPS_BENCHMARK_SCHEMA_VERSION = "ops_benchmark.v1"
TERMINAL_STATUSES = {"completed", "failed", "cancelled", "timeout"}
LOADING_STATUSES = {"queued", "running", "retrying"}


class OpsBenchmarkError(RuntimeError):
    """Raised when the ops benchmark cannot prove the contract."""


class _BenchmarkStore:
    def __init__(self) -> None:
        self.runtime_queue: dict[int, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self.bulk_updates: list[dict[str, Any]] = []
        self._next_seq = 1

    async def register_queued_task(self, **fields: Any) -> None:
        task_id = int(fields["task_id"])
        self.runtime_queue[task_id] = {
            "task_id": task_id,
            "status": "queued",
            "queue_position": None,
            "last_error": fields.get("last_error"),
            **fields,
        }

    def list_runtime_queues(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self.runtime_queue.values()]

    def update_runtime_queue_item(self, task_id: int, **fields: Any) -> None:
        row = self.runtime_queue.setdefault(int(task_id), {"task_id": int(task_id)})
        row.update(fields)

    def bulk_update_runtime_queue_items(self, updates: list[dict[str, Any]]) -> None:
        self.bulk_updates.extend(dict(item) for item in updates)
        for item in updates:
            task_id = int(item["task_id"])
            fields = {key: value for key, value in item.items() if key != "task_id"}
            self.update_runtime_queue_item(task_id, **fields)

    def get_environment_by_task(self, task_id: int) -> dict[str, Any] | None:
        return None

    def add_event(
        self,
        *,
        task_id: int | None,
        env_id: int | None,
        attempt: int | None,
        phase: str | None,
        event_type: str,
        severity: str = "info",
        payload: dict[str, Any] | None = None,
        artifact_refs: list[str] | None = None,
        resource_snapshot_ref: str | None = None,
    ) -> dict[str, Any]:
        event = {
            "seq": self._next_seq,
            "task_id": task_id,
            "env_id": env_id,
            "attempt": attempt,
            "phase": phase,
            "event_type": event_type,
            "severity": severity,
            "payload": dict(payload or {}),
            "artifact_refs": list(artifact_refs or []),
            "resource_snapshot_ref": resource_snapshot_ref,
        }
        self._next_seq += 1
        self.events.append(event)
        return dict(event)

    def list_events(
        self,
        *,
        task_id: int | None = None,
        task_ids: list[int] | None = None,
        env_id: int | None = None,
        after_seq: int = 0,
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for event in self.events:
            if event["seq"] <= after_seq:
                continue
            if task_id is not None and event["task_id"] != task_id:
                continue
            if task_ids is not None and event["task_id"] not in task_ids:
                continue
            if env_id is not None and event["env_id"] != env_id:
                continue
            out.append(dict(event))
        return out


class _BenchmarkRuntime:
    def __init__(self, runtime_root: Path) -> None:
        self.store = _BenchmarkStore()
        self.events = RuntimeEventBroker(store=self.store, runtime_root=runtime_root)  # type: ignore[arg-type]
        self.finalized: list[dict[str, Any]] = []
        self.warnings: list[dict[str, Any]] = []

    async def register_queued_task(self, **fields: Any) -> None:
        await self.store.register_queued_task(**fields)

    async def finalize_task(self, *, task_id: int, success: bool, **fields: Any) -> None:
        status = "completed" if success else str(fields.get("final_status") or "failed")
        self.store.update_runtime_queue_item(task_id, status=status, last_error=fields.get("error_message"))
        self.finalized.append({"task_id": task_id, "success": success, **fields})

    async def record_warning(self, *, task_id: int, warning_type: str, message: str, **fields: Any) -> None:
        self.warnings.append({"task_id": task_id, "warning_type": warning_type, "message": message, **fields})


def _reset_queue_state(queue_manager: Any, user_id: int) -> None:
    queue_manager._queue_workers.pop(user_id, None)
    queue_manager._user_tasks.pop(user_id, None)
    queue_manager._user_queue_task_ids.pop(user_id, None)
    queue_manager._user_queues.pop(user_id, None)
    queue_manager._worker_locks.pop(user_id, None)
    queue_manager._active_chat_ids.pop(user_id, None)


async def _run_queue_runtime_scenario(*, full: bool, runtime: _BenchmarkRuntime) -> dict[str, Any]:
    from koda.services import queue_manager

    user_id = 76001
    chat_id = 76002
    repetitions = 10 if full else 1
    base_actions = ("success", "timeout", "dlq")
    task_ids = [1000 + index for index in range(repetitions * len(base_actions))]
    actions = {task_id: base_actions[index % len(base_actions)] for index, task_id in enumerate(task_ids)}
    run_counts: dict[int, int] = defaultdict(int)
    terminal_by_task: dict[int, str] = {}
    dlq_rows: list[dict[str, Any]] = []
    status_updates: list[dict[str, Any]] = []

    context = SimpleNamespace(user_data={"provider": "fake", "provider_sessions": {}}, bot=AsyncMock())
    queue = queue_manager.get_queue(user_id)
    for task_id in task_ids:
        raw_item = {
            "_user_message": True,
            "_task_id": task_id,
            "chat_id": chat_id,
            "query_text": f"ops benchmark {actions[task_id]} #{task_id}",
            "provider": "fake",
            "model": "fake-model",
            "work_dir": tempfile.gettempdir(),
            "session_id": f"ops-benchmark-{task_id}",
        }
        await queue.put(raw_item)
        queue_manager._track_queued_task_id(user_id, task_id)
        await runtime.register_queued_task(
            task_id=task_id,
            user_id=user_id,
            chat_id=chat_id,
            query_text=raw_item["query_text"],
            payload_json=json.dumps(raw_item),
            source_kind="ops_benchmark",
        )

    async def fake_execute(raw_item: Any, _user_id: int, _context: Any, task_id: int, task_info: Any) -> None:
        run_counts[task_id] += 1
        action = actions[task_id]
        if action == "dlq":
            raise RuntimeError("ops benchmark forced dispatch failure")
        if action == "timeout":
            try:
                await asyncio.wait_for(asyncio.sleep(0.02), timeout=0.001)
            except TimeoutError:
                task_info.status = "timeout"
                task_info.error_message = "ops benchmark timeout"
                terminal_by_task[task_id] = "timeout"
                runtime.store.update_runtime_queue_item(task_id, status="timeout", last_error=task_info.error_message)
                await runtime.record_warning(
                    task_id=task_id,
                    warning_type="ops_benchmark_timeout",
                    message=task_info.error_message,
                )
                await runtime.events.publish(
                    task_id=task_id,
                    env_id=None,
                    attempt=1,
                    phase="timeout",
                    event_type="task.timeout",
                    severity="warning",
                    payload={"benchmark": OPS_BENCHMARK_SCHEMA_VERSION},
                )
                await runtime.finalize_task(
                    task_id=task_id,
                    success=False,
                    error_message=task_info.error_message,
                    final_status="timeout",
                )
                queue_manager._unregister_task(task_info)
                return
            raise AssertionError("timeout scenario did not time out")
        task_info.status = "completed"
        terminal_by_task[task_id] = "completed"
        runtime.store.update_runtime_queue_item(task_id, status="completed", last_error=None)
        await runtime.events.publish(
            task_id=task_id,
            env_id=None,
            attempt=1,
            phase="completed",
            event_type="task.completed",
            payload={"benchmark": OPS_BENCHMARK_SCHEMA_VERSION},
        )
        await runtime.finalize_task(task_id=task_id, success=True, summary={"benchmark": OPS_BENCHMARK_SCHEMA_VERSION})
        queue_manager._unregister_task(task_info)

    def fake_update_task_status(task_id: int, status: str, **fields: Any) -> None:
        status_updates.append({"task_id": task_id, "status": status, **fields})
        runtime.store.update_runtime_queue_item(task_id, status=status, last_error=fields.get("error_message"))
        if status in TERMINAL_STATUSES:
            terminal_by_task[task_id] = status

    def fake_dlq_insert(**fields: Any) -> int:
        dlq_id = len(dlq_rows) + 1
        dlq_rows.append({"id": dlq_id, **fields})
        terminal_by_task[int(fields["task_id"])] = "failed"
        return dlq_id

    with (
        patch("koda.services.queue_manager._execute_single_task", side_effect=fake_execute),
        patch("koda.services.queue_manager.update_task_status", side_effect=fake_update_task_status),
        patch("koda.services.queue_manager.dlq_insert", side_effect=fake_dlq_insert),
        patch("koda.services.queue_manager.RUNTIME_ENVIRONMENTS_ENABLED", True),
        patch("koda.services.queue_manager.log.info"),
        patch("koda.services.queue_manager.log.warning"),
        patch("koda.services.queue_manager.log.error"),
        patch("koda.services.queue_manager.log.exception"),
        patch("koda.services.audit.emit_task_lifecycle"),
        patch("koda.services.runtime.get_runtime_controller", return_value=runtime),
    ):
        await asyncio.gather(
            queue_manager._ensure_queue_worker(user_id, context),
            queue_manager._ensure_queue_worker(user_id, context),
        )
        worker = queue_manager._queue_workers.get(user_id)
        if worker is not None:
            await asyncio.wait_for(worker, timeout=5)

    no_double_run = all(run_counts.get(task_id) == 1 for task_id in task_ids)
    terminal_task_ids = {task_id for task_id, status in terminal_by_task.items() if status in TERMINAL_STATUSES}
    loading_rows = [
        row for row in runtime.store.list_runtime_queues() if str(row.get("status") or "") in LOADING_STATUSES
    ]
    cleanup_ok = (
        queue.qsize() == 0
        and not queue_manager._user_tasks.get(user_id)
        and not queue_manager._user_queue_task_ids.get(user_id)
        and user_id not in queue_manager._queue_workers
    )
    _reset_queue_state(queue_manager, user_id)
    return {
        "step": "queue_runtime",
        "task_count": len(task_ids),
        "run_counts": dict(run_counts),
        "no_double_run": no_double_run,
        "terminal_state_for_all_tasks": len(terminal_task_ids) == len(task_ids),
        "terminal_statuses": {str(task_id): terminal_by_task.get(task_id) for task_id in task_ids},
        "timeout_observed": any(status == "timeout" for status in terminal_by_task.values()),
        "dlq_count": len(dlq_rows),
        "dlq_observed": len(dlq_rows) == repetitions,
        "no_infinite_loading": loading_rows == [],
        "cleanup_ok": cleanup_ok,
        "status_update_count": len(status_updates),
    }


async def _run_recovery_scenario(runtime: _BenchmarkRuntime) -> dict[str, Any]:
    from koda.config import QUEUE_MAX_RECOVERY_ATTEMPTS
    from koda.services import queue_manager

    user_id = 77001
    task_id = 77002
    dlq_rows: list[dict[str, Any]] = []
    application = MagicMock()
    application.user_data = defaultdict(dict)
    application.bot = AsyncMock()
    task_row = {
        "id": task_id,
        "user_id": user_id,
        "chat_id": 77003,
        "status": "running",
        "query_text": "ops benchmark recovery exhausted",
        "provider": "fake",
        "model": "fake-model",
        "attempt": 2,
        "created_at": "2026-05-19T00:00:00+00:00",
    }
    runtime.store.runtime_queue[task_id] = {
        "task_id": task_id,
        "payload_json": json.dumps(
            {
                "_user_message": True,
                "_task_id": task_id,
                "chat_id": 77003,
                "query_text": task_row["query_text"],
            }
        ),
        "recovery_count": QUEUE_MAX_RECOVERY_ATTEMPTS,
        "status": "running",
    }

    def fake_dlq_insert(**fields: Any) -> int:
        dlq_id = len(dlq_rows) + 1
        dlq_rows.append({"id": dlq_id, **fields})
        return dlq_id

    with (
        patch("koda.services.queue_manager.list_pending_tasks_for_recovery", return_value=[task_row]),
        patch("koda.services.queue_manager.update_task_status") as update_task_status,
        patch("koda.services.queue_manager.dlq_insert", side_effect=fake_dlq_insert),
        patch("koda.services.queue_manager.RUNTIME_ENVIRONMENTS_ENABLED", True),
        patch("koda.services.queue_manager.log.warning"),
        patch("koda.services.audit.emit_task_lifecycle"),
        patch("koda.services.runtime.get_runtime_controller", return_value=runtime),
    ):
        summary = await queue_manager.recover_pending_tasks(application)

    _reset_queue_state(queue_manager, user_id)
    return {
        "step": "queue_recovery",
        "summary": summary,
        "dlq_observed": len(dlq_rows) == 1,
        "terminal_state": runtime.store.runtime_queue[task_id].get("status") == "failed",
        "finalized": any(item["task_id"] == task_id and item["success"] is False for item in runtime.finalized),
        "status_update_called": update_task_status.called,
    }


async def _run_channel_backpressure_scenario(runtime: _BenchmarkRuntime) -> dict[str, Any]:
    full_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1)
    full_queue.put_nowait({"prefilled": True})
    runtime.events._subscribers.add(full_queue)
    healthy_queue = runtime.events.subscribe()
    started = time.perf_counter()
    await runtime.events.publish(
        task_id=88001,
        env_id=None,
        attempt=1,
        phase="executing",
        event_type="ops.backpressure",
        payload={"benchmark": OPS_BENCHMARK_SCHEMA_VERSION},
    )
    duration_ms = (time.perf_counter() - started) * 1000
    healthy_event = await asyncio.wait_for(healthy_queue.get(), timeout=1)
    runtime.events.unsubscribe(healthy_queue)
    runtime.events.unsubscribe(full_queue)
    return {
        "step": "channel_backpressure",
        "publisher_returned": duration_ms < 100,
        "duration_ms": round(duration_ms, 3),
        "healthy_subscriber_received": healthy_event.get("event_type") == "ops.backpressure",
        "full_subscriber_dropped": full_queue.qsize() == 1 and full_queue.get_nowait() == {"prefilled": True},
    }


async def run_ops_benchmark(*, full: bool = False) -> dict[str, Any]:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="koda-ops-benchmark-") as tmp_dir:
        runtime = _BenchmarkRuntime(Path(tmp_dir))
        queue_result = await _run_queue_runtime_scenario(full=full, runtime=runtime)
        recovery_result = await _run_recovery_scenario(runtime)
        channel_result = await _run_channel_backpressure_scenario(runtime)
        results = [queue_result, recovery_result, channel_result]
    return {
        "schema_version": OPS_BENCHMARK_SCHEMA_VERSION,
        "mode": "full" if full else "quick",
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        "results": results,
    }


def evaluate_ops_benchmark(result: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if result.get("schema_version") != OPS_BENCHMARK_SCHEMA_VERSION:
        failures.append("result.schema_version must be ops_benchmark.v1")
    by_step = {str(item.get("step") or ""): item for item in result.get("results", []) if isinstance(item, dict)}
    required = {
        "queue_runtime": [
            "no_double_run",
            "terminal_state_for_all_tasks",
            "timeout_observed",
            "dlq_observed",
            "no_infinite_loading",
            "cleanup_ok",
        ],
        "queue_recovery": ["dlq_observed", "terminal_state", "finalized", "status_update_called"],
        "channel_backpressure": ["publisher_returned", "healthy_subscriber_received", "full_subscriber_dropped"],
    }
    for step, checks in required.items():
        actual = by_step.get(step)
        if actual is None:
            failures.append(f"missing smoke step: {step}")
            continue
        for check in checks:
            if actual.get(check) is not True:
                failures.append(f"{step}.{check} expected True; got {actual.get(check)!r}")
    return failures


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="Run the larger opt-in benchmark loop.")
    parser.add_argument("--json", action="store_true", help="Print the benchmark result as JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    full = bool(args.full or os.getenv("KODA_OPS_BENCH_FULL") == "1")
    mode = "full" if full else "quick"
    started = time.perf_counter()
    try:
        result = asyncio.run(run_ops_benchmark(full=full))
        failures = evaluate_ops_benchmark(result)
    except OpsBenchmarkError as exc:
        print(f"ops benchmark input error: {exc}", file=sys.stderr)
        _emit_ops_benchmark_metric(mode=mode, status="input_error", duration_seconds=time.perf_counter() - started)
        return 2
    except Exception as exc:
        print(f"ops benchmark failed unexpectedly: {exc}", file=sys.stderr)
        _emit_ops_benchmark_metric(mode=mode, status="error", duration_seconds=time.perf_counter() - started)
        return 2
    if failures:
        print("ops benchmark failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        _emit_ops_benchmark_metric(mode=mode, status="failed", duration_seconds=time.perf_counter() - started)
        return 1
    _emit_ops_benchmark_metric(mode=mode, status="passed", duration_seconds=time.perf_counter() - started)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"ops benchmark passed ({result['mode']})")
    return 0


def _emit_ops_benchmark_metric(*, mode: str, status: str, duration_seconds: float) -> None:
    try:
        from koda.services.metrics import OPS_BENCHMARK_DURATION, OPS_BENCHMARK_RUNS

        OPS_BENCHMARK_RUNS.labels(mode=mode or "unknown", status=status or "unknown").inc()
        OPS_BENCHMARK_DURATION.labels(mode=mode or "unknown").observe(max(0.0, duration_seconds))
    except Exception:
        return


if __name__ == "__main__":
    raise SystemExit(main())
