"""Reconcile backoff and kernel socket-path validation (M7-E1-T2, D-177, D-178).

While the runtime kernel is unreachable the reconcile loop backs off
exponentially and logs one traceback per state change, then one-line
summaries. An over-long ``unix://`` kernel target fails at startup instead
of leaving a channel whose close hangs SIGTERM.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda import config as config_module
from koda.control_plane import runtime_kernel_link as link_mod
from koda.control_plane import supervisor as supervisor_mod
from koda.control_plane.runtime_kernel_link import RuntimeKernelLink
from koda.control_plane.supervisor import ControlPlaneSupervisor


def _make_supervisor() -> ControlPlaneSupervisor:
    link = SimpleNamespace(start=AsyncMock(), stop=AsyncMock(), ensure_agent_workers=AsyncMock(), target="k:1")
    with patch("koda.control_plane.supervisor.get_control_plane_manager", return_value=object()):
        return ControlPlaneSupervisor(link=link)  # type: ignore[arg-type]


async def _run_loop(supervisor: ControlPlaneSupervisor, outcomes: list[Exception | None]) -> list[float]:
    """Drive the loop through ``outcomes`` (an exception or None per tick); return the waits."""
    pending = list(outcomes)
    waits: list[float] = []

    async def _reconcile_once() -> None:
        outcome = pending.pop(0)
        if outcome is not None:
            raise outcome

    async def _wait(delay: float) -> None:
        waits.append(delay)
        if not pending:
            supervisor._closing = True

    with (
        patch.object(supervisor, "_reconcile_once", _reconcile_once),
        patch.object(supervisor, "_wait_for_next_reconcile", _wait),
    ):
        await supervisor._reconcile_loop()
    return waits


@pytest.mark.asyncio
async def test_reconcile_backs_off_exponentially_while_the_kernel_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(supervisor_mod, "CONTROL_PLANE_POLL_INTERVAL_SECONDS", 5.0)
    monkeypatch.setattr(supervisor_mod, "_RECONCILE_BACKOFF_MAX_SECONDS", 60.0)
    supervisor = _make_supervisor()
    down = ConnectionError("kernel unreachable")

    waits = await _run_loop(supervisor, [None, down, down, down, down, down, down, None, None])

    assert waits == [5.0, 10.0, 20.0, 40.0, 60.0, 60.0, 60.0, 5.0, 5.0]


@pytest.mark.asyncio
async def test_a_very_long_outage_keeps_waiting_at_the_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Past 1024 failures ``float * 2**failures`` would overflow and end the loop."""
    monkeypatch.setattr(supervisor_mod, "CONTROL_PLANE_POLL_INTERVAL_SECONDS", 5.0)
    monkeypatch.setattr(supervisor_mod, "_RECONCILE_BACKOFF_MAX_SECONDS", 60.0)
    monkeypatch.setattr(supervisor_mod, "log", MagicMock())
    supervisor = _make_supervisor()

    waits = await _run_loop(supervisor, [ConnectionError("down")] * 1100 + [None])

    assert len(waits) == 1101
    assert waits[1099] == 60.0
    assert waits[-1] == 5.0


@pytest.mark.asyncio
async def test_reconcile_logs_one_traceback_per_state_change(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(supervisor_mod, "CONTROL_PLANE_POLL_INTERVAL_SECONDS", 5.0)
    supervisor = _make_supervisor()
    log = MagicMock()
    monkeypatch.setattr(supervisor_mod, "log", log)
    down = ConnectionError("kernel unreachable")

    await _run_loop(supervisor, [down] * 20 + [None] + [down] * 3)

    # Down, recovered, down again: two tracebacks, one recovery line.
    assert [c.args[0] for c in log.exception.call_args_list] == ["control_plane_reconcile_error"] * 2
    assert [c.args[0] for c in log.info.call_args_list] == ["control_plane_reconcile_recovered"]
    summaries = log.warning.call_args_list
    assert len(summaries) == 19 + 2
    assert all(c.args[0] == "control_plane_reconcile_still_failing" for c in summaries)
    assert summaries[-1].kwargs["consecutive_failures"] == 3


@pytest.mark.asyncio
async def test_a_different_error_is_a_new_state_and_gets_its_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    supervisor = _make_supervisor()
    log = MagicMock()
    monkeypatch.setattr(supervisor_mod, "log", log)

    await _run_loop(supervisor, [ConnectionError("down"), ConnectionError("down"), KeyError("agent")])

    assert log.exception.call_count == 2


@pytest.mark.asyncio
async def test_ten_minutes_with_the_kernel_down_stay_far_below_the_log_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-177 measured 2.2 MB in 9 minutes; the budget is 50 KB in 10 minutes."""
    monkeypatch.setattr(supervisor_mod, "CONTROL_PLANE_POLL_INTERVAL_SECONDS", 5.0)
    supervisor = _make_supervisor()
    log = MagicMock()
    monkeypatch.setattr(supervisor_mod, "log", log)
    elapsed = 0.0
    ticks = 0

    async def _reconcile_once() -> None:
        raise ConnectionError("kernel unreachable")

    async def _wait(delay: float) -> None:
        nonlocal elapsed, ticks
        elapsed += delay
        ticks += 1
        if elapsed >= 600:
            supervisor._closing = True

    with (
        patch.object(supervisor, "_reconcile_once", _reconcile_once),
        patch.object(supervisor, "_wait_for_next_reconcile", _wait),
    ):
        await supervisor._reconcile_loop()

    assert log.exception.call_count == 1
    assert ticks <= 15  # was 120 ticks, each with two tracebacks


@pytest.mark.asyncio
async def test_link_leaves_failure_logging_to_the_reconcile_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    from koda.internal_rpc.common import ensure_generated_proto_path

    ensure_generated_proto_path()
    from runtime.v1 import runtime_pb2

    log = MagicMock()
    monkeypatch.setattr(link_mod, "log", log)
    link = RuntimeKernelLink(target="unix:///tmp/fake.sock")
    link._runtime_pb2 = runtime_pb2

    async def _fail(request: Any, metadata: Any) -> Any:
        raise ConnectionError("kernel unreachable")

    link._stub = SimpleNamespace(EnsureAgentWorkers=_fail)
    with pytest.raises(ConnectionError):
        await link.ensure_agent_workers([])
    log.exception.assert_not_called()


def _unix_target(path_bytes: int) -> str:
    stem = "/tmp/"
    return "unix://" + stem + "x" * (path_bytes - len(stem))


def test_over_long_unix_socket_path_is_rejected_at_construction() -> None:
    with pytest.raises(link_mod.RuntimeKernelTargetError, match="RUNTIME_KERNEL_SOCKET"):
        RuntimeKernelLink(target=_unix_target(link_mod.UNIX_SOCKET_PATH_MAX_BYTES + 1))


def test_unix_socket_path_at_the_limit_and_tcp_targets_are_accepted() -> None:
    RuntimeKernelLink(target=_unix_target(link_mod.UNIX_SOCKET_PATH_MAX_BYTES))
    RuntimeKernelLink(target="runtime-kernel:50061")
    RuntimeKernelLink(target="/tmp/short.sock")


def test_control_plane_refuses_to_start_on_an_over_long_socket_path(monkeypatch: pytest.MonkeyPatch) -> None:
    from koda.control_plane import __main__ as cp_main

    monkeypatch.setattr(config_module, "RUNTIME_KERNEL_SOCKET", _unix_target(link_mod.UNIX_SOCKET_PATH_MAX_BYTES + 40))
    monkeypatch.setattr(cp_main, "ensure_browser_installed_in_background", lambda: None)
    monkeypatch.setattr(supervisor_mod, "get_control_plane_manager", lambda: object())
    monkeypatch.setattr(supervisor_mod, "_warn_about_placeholder_secrets", lambda: None)

    with pytest.raises(SystemExit) as excinfo:
        cp_main.main()

    message = str(excinfo.value.code)
    assert message.startswith("koda control plane refused to start:")
    assert "RUNTIME_KERNEL_SOCKET" in message
