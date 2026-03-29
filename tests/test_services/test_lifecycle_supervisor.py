"""Tests for application background loop supervision."""

from __future__ import annotations

import asyncio

import pytest

from koda.services.lifecycle_supervisor import BackgroundLoopSupervisor


@pytest.mark.asyncio
async def test_background_loop_supervisor_restarts_failed_loop():
    supervisor = BackgroundLoopSupervisor()
    stop_event = asyncio.Event()
    attempts = 0

    async def _runner() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("boom")
        await stop_event.wait()

    await supervisor.start_loop("memory_maintenance", _runner, restart_delay_seconds=0.01)
    for _ in range(100):
        snapshot = supervisor.snapshot()
        loop_state = snapshot["loops"].get("memory_maintenance", {})
        if loop_state.get("restart_count", 0) >= 1 and loop_state.get("running"):
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError("background loop did not restart")

    snapshot = supervisor.snapshot()
    loop_state = snapshot["loops"]["memory_maintenance"]
    assert loop_state["restart_count"] >= 1
    assert loop_state["running"] is True
    assert loop_state["last_error"] == "boom"

    stop_event.set()
    await supervisor.stop()


@pytest.mark.asyncio
async def test_background_loop_supervisor_marks_failed_critical_loop_unready():
    supervisor = BackgroundLoopSupervisor()

    async def _runner() -> None:
        raise RuntimeError("critical failure")

    await supervisor.start_loop(
        "critical_loop",
        _runner,
        critical=True,
        restart_on_failure=False,
    )
    await asyncio.sleep(0)
    snapshot = supervisor.snapshot()

    assert snapshot["critical_ready"] is False
    assert snapshot["degraded_loops"] == ["critical_loop"]
    assert snapshot["loops"]["critical_loop"]["last_error"] == "critical failure"

    await supervisor.stop()
