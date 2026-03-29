"""Supervision for long-lived application background loops."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from koda.logging_config import get_logger

log = get_logger(__name__)


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class _LoopSpec:
    name: str
    runner: Callable[[], Awaitable[None]]
    critical: bool
    restart_on_failure: bool
    restart_delay_seconds: float


@dataclass(slots=True)
class _LoopState:
    name: str
    critical: bool
    restart_on_failure: bool
    running: bool = False
    stop_requested: bool = False
    run_count: int = 0
    restart_count: int = 0
    last_started_at: str | None = None
    last_stopped_at: str | None = None
    last_error: str | None = None
    last_completion: str | None = None


class BackgroundLoopSupervisor:
    """Own long-lived maintenance loops with restart and visibility semantics."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._specs: dict[str, _LoopSpec] = {}
        self._states: dict[str, _LoopState] = {}
        self._closing = False

    async def start_loop(
        self,
        name: str,
        runner: Callable[[], Awaitable[None]],
        *,
        critical: bool = False,
        restart_on_failure: bool = True,
        restart_delay_seconds: float = 1.0,
    ) -> None:
        existing = self._tasks.get(name)
        if existing is not None and not existing.done():
            return
        spec = _LoopSpec(
            name=name,
            runner=runner,
            critical=critical,
            restart_on_failure=restart_on_failure,
            restart_delay_seconds=max(0.0, restart_delay_seconds),
        )
        self._specs[name] = spec
        self._states[name] = _LoopState(
            name=name,
            critical=critical,
            restart_on_failure=restart_on_failure,
        )
        self._tasks[name] = asyncio.create_task(self._run_loop(spec), name=f"background-loop:{name}")

    async def stop(self) -> None:
        self._closing = True
        tasks = list(self._tasks.items())
        for name, task in tasks:
            state = self._states.get(name)
            if state is not None:
                state.stop_requested = True
            task.cancel()
        for name, task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                log.exception("background_loop_stop_join_failed", loop=name)
        self._tasks.clear()
        self._closing = False

    def snapshot(self) -> dict[str, Any]:
        loops: dict[str, dict[str, Any]] = {}
        degraded_loops: list[str] = []
        critical_degraded: list[str] = []
        for name, state in self._states.items():
            task = self._tasks.get(name)
            running = bool(task is not None and not task.done() and state.running)
            healthy = running or state.stop_requested
            payload = {
                "critical": state.critical,
                "restart_on_failure": state.restart_on_failure,
                "running": running,
                "healthy": healthy,
                "stop_requested": state.stop_requested,
                "run_count": state.run_count,
                "restart_count": state.restart_count,
                "last_started_at": state.last_started_at,
                "last_stopped_at": state.last_stopped_at,
                "last_error": state.last_error,
                "last_completion": state.last_completion,
            }
            loops[name] = payload
            if not healthy:
                degraded_loops.append(name)
                if state.critical:
                    critical_degraded.append(name)
        return {
            "started": bool(self._states),
            "ready": not critical_degraded,
            "critical_ready": not critical_degraded,
            "running_loops": sum(1 for item in loops.values() if item["running"]),
            "degraded_loops": degraded_loops,
            "critical_degraded_loops": critical_degraded,
            "loops": loops,
        }

    async def _run_loop(self, spec: _LoopSpec) -> None:
        state = self._states[spec.name]
        while True:
            state.running = True
            state.stop_requested = False
            state.last_started_at = _utcnow()
            state.run_count += 1
            state.last_completion = None
            try:
                await spec.runner()
                state.last_completion = "returned"
                state.last_stopped_at = _utcnow()
                state.running = False
                if self._closing or not spec.restart_on_failure:
                    return
                state.restart_count += 1
                log.warning("background_loop_returned", loop=spec.name)
                await asyncio.sleep(spec.restart_delay_seconds)
                continue
            except asyncio.CancelledError:
                state.running = False
                state.stop_requested = True
                state.last_completion = "cancelled"
                state.last_stopped_at = _utcnow()
                raise
            except Exception as exc:
                state.running = False
                state.last_error = str(exc)
                state.last_completion = "failed"
                state.last_stopped_at = _utcnow()
                log.exception("background_loop_failed", loop=spec.name)
                if self._closing or not spec.restart_on_failure:
                    return
                state.restart_count += 1
                await asyncio.sleep(spec.restart_delay_seconds)


_SUPERVISOR = BackgroundLoopSupervisor()


def get_background_loop_supervisor() -> BackgroundLoopSupervisor:
    return _SUPERVISOR


async def reset_background_loop_supervisor() -> None:
    await _SUPERVISOR.stop()
    _SUPERVISOR._specs.clear()  # noqa: SLF001 - testing helper
    _SUPERVISOR._states.clear()  # noqa: SLF001 - testing helper
