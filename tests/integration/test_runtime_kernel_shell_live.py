"""Background shell against the real Rust runtime kernel (M1-E4-T10).

The unit and adversarial tests stand in for the kernel. These tests run
``shell_bg``, ``shell_kill`` and ``shell_execute`` through the real
``koda-runtime-kernel`` binary over gRPC, and check what only the kernel can
show: an allowed command's output comes back through ExecuteCommand, a kill
leaves no process in the command's process group, command timeouts and
commands the kernel refuses come back as the command's own outcome without
opening the runtime-kernel circuit breaker, and a kernel that stops answering
does count against it.

Opt-in. Set ``KODA_TEST_RUNTIME_KERNEL_BIN`` to a built ``koda-runtime-kernel``
binary, or ``KODA_TEST_RUNTIME_KERNEL=1`` to build it with
``cargo build --release -p koda-runtime-kernel``. The build reuses an existing
``rust/target/release`` binary as is, so point at a fresh binary after Rust
changes.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import time
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from koda.internal_rpc.circuit_breaker import State
from koda.services.tool_dispatcher import (
    ToolContext,
    _handle_shell_bg,
    _handle_shell_execute,
    _handle_shell_kill,
    _handle_shell_output,
    _handle_shell_status,
)

pytestmark = [
    pytest.mark.rust_engine,
    pytest.mark.skipif(not Path("/proc/self/stat").exists(), reason="inspects process groups through /proc"),
]


def _live_process_group_members(pgid: int) -> list[int]:
    """Pids of the non-zombie processes in process group ``pgid``."""
    members = []
    for stat_path in Path("/proc").glob("[0-9]*/stat"):
        try:
            stat = stat_path.read_text()
        except OSError:
            continue
        # "pid (comm) state ppid pgrp ..."; comm may itself contain ")".
        fields = stat.rpartition(")")[2].split()
        if len(fields) > 2 and fields[0] not in {"Z", "X"} and fields[2] == str(pgid):
            members.append(int(stat_path.parent.name))
    return members


async def _read_pgid(path: Path) -> int:
    deadline = time.monotonic() + 10
    while True:
        text = path.read_text(encoding="utf-8").strip() if path.exists() else ""
        if text:
            return int(text)
        assert time.monotonic() < deadline, "the command never started"
        await asyncio.sleep(0.02)


async def _wait_for_empty_group(pgid: int, *, within: float) -> list[int]:
    deadline = time.monotonic() + within
    while _live_process_group_members(pgid) and time.monotonic() < deadline:
        await asyncio.sleep(0.05)
    return _live_process_group_members(pgid)


def _kill_group(pgid: int | None) -> None:
    # Never leave sleepers behind on a shared host, even when an assertion failed.
    if pgid is not None and pgid > 1 and pgid != os.getpgrp():
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pgid, signal.SIGKILL)


@pytest.fixture
async def kernel_shell(
    spawn_rust_binary: Any,
    free_port: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[SimpleNamespace]:
    explicit = os.environ.get("KODA_TEST_RUNTIME_KERNEL_BIN", "").strip()
    if not explicit and os.environ.get("KODA_TEST_RUNTIME_KERNEL", "").strip() != "1":
        pytest.skip(
            "opt-in: set KODA_TEST_RUNTIME_KERNEL_BIN=<koda-runtime-kernel binary> "
            "or KODA_TEST_RUNTIME_KERNEL=1 to build it"
        )
    binary = Path(explicit) if explicit else None
    if binary is not None and not binary.is_file():
        pytest.fail(f"KODA_TEST_RUNTIME_KERNEL_BIN={explicit} is not a file")

    bind = f"127.0.0.1:{free_port}"
    runtime_root = tmp_path / "runtime-kernel"
    process = spawn_rust_binary(
        "koda-runtime-kernel",
        env={"RUNTIME_KERNEL_SOCKET": bind, "RUNTIME_KERNEL_ROOT": str(runtime_root), "RUST_LOG": "warn"},
        grpc_target=bind,
        binary=binary,
    )

    from koda import config
    from koda.internal_rpc.runtime_kernel import GrpcRuntimeKernelClient
    from koda.services.shell_tools import BackgroundProcessManager

    monkeypatch.setattr(config, "RUNTIME_KERNEL_SOCKET", bind)
    client = GrpcRuntimeKernelClient(runtime_root=runtime_root, store=None, mode="rust")  # type: ignore[arg-type]
    await client.start()
    assert client.health().get("cutover_allowed") is True, client.health()
    monkeypatch.setattr(
        "koda.services.shell_runner.get_runtime_controller",
        lambda: SimpleNamespace(runtime_kernel=client),
    )
    manager = BackgroundProcessManager()
    monkeypatch.setattr("koda.services.shell_tools.bg_process_manager", manager)
    monkeypatch.setattr("koda.services.tool_dispatcher.SHELL_ENABLED", True)
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    ctx = ToolContext(
        user_id=111,
        chat_id=111,
        work_dir=str(work_dir),
        user_data={},
        agent=None,
        agent_mode="autonomous",
    )
    try:
        yield SimpleNamespace(client=client, manager=manager, work_dir=work_dir, ctx=ctx, process=process)
    finally:
        for bg in manager._processes.values():
            task = bg._collection_task
            if task is not None and not task.done():
                task.cancel()
                await asyncio.wait({task})
        await client.stop()


async def _start(kernel_shell: SimpleNamespace, command: str, *, timeout: int) -> str:
    before = set(kernel_shell.manager._processes)
    started = await _handle_shell_bg({"command": command, "timeout": timeout}, kernel_shell.ctx)
    assert started.success is True, started.output
    (handle_id,) = set(kernel_shell.manager._processes) - before
    return str(handle_id)


async def _wait_finished(kernel_shell: SimpleNamespace, handle_ids: list[str], *, within: float) -> None:
    tasks = {kernel_shell.manager.get(handle_id)._collection_task for handle_id in handle_ids}
    _done, pending = await asyncio.wait(tasks, timeout=within)
    assert not pending, f"{len(pending)} background command(s) never finished"


@pytest.mark.asyncio
async def test_allowed_command_output_comes_back_through_execute_command(kernel_shell: SimpleNamespace) -> None:
    handle_id = await _start(kernel_shell, "echo hello-from-kernel", timeout=30)
    await _wait_finished(kernel_shell, [handle_id], within=30)

    output = await _handle_shell_output({"handle_id": handle_id}, kernel_shell.ctx)
    assert output.output == "Exit 0:\nhello-from-kernel"
    foreground = await _handle_shell_execute({"command": "echo hello-from-kernel"}, kernel_shell.ctx)
    assert foreground.output == "Exit 0:\nhello-from-kernel"

    # A command the guard denies gets the same refusal from both tools and never runs.
    denied_background = await _handle_shell_bg({"command": "env"}, kernel_shell.ctx)
    denied_foreground = await _handle_shell_execute({"command": "env"}, kernel_shell.ctx)
    assert denied_foreground.success is False
    assert (denied_background.success, denied_background.output) == (False, denied_foreground.output)


@pytest.mark.asyncio
async def test_kill_leaves_no_process_in_the_command_group(kernel_shell: SimpleNamespace) -> None:
    pgid: int | None = None
    try:
        # The shell records its process group, then leaves a grandchild behind in it.
        handle_id = await _start(kernel_shell, "echo $$ > pgid; sleep 60 & sleep 60", timeout=120)
        pgid = await _read_pgid(kernel_shell.work_dir / "pgid")
        assert len(_live_process_group_members(pgid)) >= 2

        killed = await _handle_shell_kill({"handle_id": handle_id}, kernel_shell.ctx)
        assert killed.success is True, killed.output

        assert await _wait_for_empty_group(pgid, within=5) == []
        status = await _handle_shell_status({"handle_id": handle_id}, kernel_shell.ctx)
        assert "Status: killed" in status.output
    finally:
        _kill_group(pgid)


@pytest.mark.asyncio
async def test_timeouts_come_back_as_timeouts_and_leave_the_breaker_closed(kernel_shell: SimpleNamespace) -> None:
    from koda import config
    from koda.services.shell_runner import run_shell_command
    from koda.services.shell_tools import SHELL_BG_MAX_PROCESSES

    # Enough timeouts to open the breaker if they counted as kernel failures. The last one
    # ignores SIGTERM, so the kernel answers only after its 2 s grace period and SIGKILL.
    commands = ["sleep 20"] * max(0, config.INTERNAL_RPC_BREAKER_THRESHOLD - 1) + ["trap '' TERM; sleep 20"]
    handle_ids: list[str] = []
    for batch_start in range(0, len(commands), SHELL_BG_MAX_PROCESSES):
        batch = [
            await _start(kernel_shell, command, timeout=1)
            for command in commands[batch_start : batch_start + SHELL_BG_MAX_PROCESSES]
        ]
        await _wait_finished(kernel_shell, batch, within=20)
        handle_ids.extend(batch)

    for handle_id in handle_ids:
        status = await _handle_shell_status({"handle_id": handle_id}, kernel_shell.ctx)
        assert "Status: timed_out" in status.output, status.output
        output = await _handle_shell_output({"handle_id": handle_id}, kernel_shell.ctx)
        assert "AioRpcError" not in output.output
    assert kernel_shell.client._breaker.state is State.CLOSED
    assert await run_shell_command("sleep 20", str(kernel_shell.work_dir), timeout=1) == "Timeout after 1s."
    assert await run_shell_command("echo still-works", str(kernel_shell.work_dir), timeout=5) == "Exit 0:\nstill-works"


@pytest.mark.asyncio
async def test_command_holding_its_output_open_times_out_and_is_cleaned_up(kernel_shell: SimpleNamespace) -> None:
    pgid: int | None = None
    try:
        # The shell exits at once, but the sleep it leaves behind keeps the output pipe open.
        # The kernel stops it at the command's timeout and answers with what it read.
        started = time.monotonic()
        handle_id = await _start(kernel_shell, "echo $$ > pgid; sleep 30 & echo started", timeout=1)
        pgid = await _read_pgid(kernel_shell.work_dir / "pgid")
        await _wait_finished(kernel_shell, [handle_id], within=20)

        assert time.monotonic() - started < 5
        status = await _handle_shell_status({"handle_id": handle_id}, kernel_shell.ctx)
        assert "Status: timed_out" in status.output, status.output
        output = await _handle_shell_output({"handle_id": handle_id}, kernel_shell.ctx)
        assert output.output == "Exit -1:\nstarted"
        assert kernel_shell.client._breaker.state is State.CLOSED
        assert await _wait_for_empty_group(pgid, within=5) == []
    finally:
        _kill_group(pgid)


@pytest.mark.asyncio
async def test_process_that_left_the_group_cannot_hold_the_reply(kernel_shell: SimpleNamespace) -> None:
    from koda.services.shell_runner import run_shell_command

    escaped: int | None = None
    try:
        # setsid takes the sleep out of the command's process group, so no kill reaches it,
        # and it keeps stdout open for 30 s. The kernel still answers within the grace periods.
        started = time.monotonic()
        handle_id = await _start(kernel_shell, "setsid sleep 30 & echo $! > escaped; echo started", timeout=1)
        await _wait_finished(kernel_shell, [handle_id], within=20)
        escaped = int((kernel_shell.work_dir / "escaped").read_text(encoding="utf-8").strip())

        assert time.monotonic() - started < 1 + 2 + 1 + 2
        status = await _handle_shell_status({"handle_id": handle_id}, kernel_shell.ctx)
        assert "Status: timed_out" in status.output, status.output
        output = await _handle_shell_output({"handle_id": handle_id}, kernel_shell.ctx)
        assert output.output == "Exit -1:\nstarted"
        assert kernel_shell.client._breaker.state is State.CLOSED
        assert await run_shell_command("echo still-works", str(kernel_shell.work_dir), timeout=5) == (
            "Exit 0:\nstill-works"
        )
    finally:
        if escaped is not None and escaped > 1:
            with contextlib.suppress(ProcessLookupError):
                os.kill(escaped, signal.SIGKILL)


@pytest.mark.asyncio
async def test_commands_the_kernel_refuses_get_the_guard_answer_and_leave_the_breaker_closed(
    kernel_shell: SimpleNamespace,
) -> None:
    from koda import config
    from koda.services.shell_runner import BLOCKED_MESSAGE, run_shell_command
    from koda.services.shell_tools import SHELL_BG_MAX_PROCESSES

    # The command guard lets curl through; the kernel's network policy refuses it without
    # allow_network, which the shell tools never set.
    command = "curl -s https://example.com -o /dev/null"
    attempts = max(1, config.INTERNAL_RPC_BREAKER_THRESHOLD)
    handle_ids: list[str] = []
    for batch_start in range(0, attempts, SHELL_BG_MAX_PROCESSES):
        batch = [
            await _start(kernel_shell, command, timeout=5)
            for _ in range(batch_start, min(attempts, batch_start + SHELL_BG_MAX_PROCESSES))
        ]
        await _wait_finished(kernel_shell, batch, within=20)
        handle_ids.extend(batch)
    foreground = await _handle_shell_execute({"command": command}, kernel_shell.ctx)

    assert (foreground.success, foreground.output) == (False, BLOCKED_MESSAGE)
    for handle_id in handle_ids:
        output = await _handle_shell_output({"handle_id": handle_id}, kernel_shell.ctx)
        assert output.output == f"Exit -1:\n{BLOCKED_MESSAGE}"
    assert kernel_shell.client._breaker.state is State.CLOSED
    assert await run_shell_command("echo still-works", str(kernel_shell.work_dir), timeout=5) == "Exit 0:\nstill-works"


@pytest.mark.asyncio
async def test_a_kernel_that_stops_answering_is_a_kernel_failure(kernel_shell: SimpleNamespace) -> None:
    from koda.internal_rpc.runtime_kernel import EXECUTE_COMMAND_DEADLINE_GRACE_SECONDS
    from koda.services.shell_runner import run_shell_command

    kernel_shell.process.send_signal(signal.SIGSTOP)
    try:
        started = time.monotonic()
        result = await run_shell_command("echo hi", str(kernel_shell.work_dir), timeout=1)
        elapsed = time.monotonic() - started
    finally:
        kernel_shell.process.send_signal(signal.SIGCONT)

    assert result.startswith("Error: "), result
    assert "DEADLINE_EXCEEDED" in result
    assert elapsed >= 1 + EXECUTE_COMMAND_DEADLINE_GRACE_SECONDS - 0.5
    # It counts on the breaker like any other kernel failure; a command timeout does not.
    assert len(kernel_shell.client._breaker._state.failures_window) == 1
