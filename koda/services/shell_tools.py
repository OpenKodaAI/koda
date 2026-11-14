"""Background shell process manager for agent tools.

Background commands take the same path as ``shell_execute``: the approval gate
and command guard in :mod:`koda.services.shell_runner`, then the runtime
kernel's ExecuteCommand. Killing a handle cancels that call, and the kernel
then kills every process still in the command's process group. A process that
leaves the group (``setsid``, a daemonizing fork) is not covered: the command
guard is a guard, not a sandbox.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, cast

from koda.config import SHELL_BG_MAX_PROCESSES, SHELL_BG_OUTPUT_MAX, SHELL_TIMEOUT
from koda.logging_config import get_logger
from koda.services.shell_runner import ShellCommandRejected, execute_in_runtime_kernel, guard_shell_command

log = get_logger(__name__)


@dataclass
class BackgroundProcess:
    handle_id: str
    user_id: int
    command: str
    work_dir: str
    started_at: float
    stdout_buf: str = ""
    stderr_buf: str = ""
    exit_code: int | None = None
    finished: bool = False
    finished_at: float | None = None
    killed: bool = False
    timed_out: bool = False
    _collection_task: asyncio.Task[None] | None = field(default=None, repr=False)


class BackgroundProcessManager:
    """Manages background shell processes per user scope."""

    def __init__(self) -> None:
        self._processes: dict[str, BackgroundProcess] = {}
        self._counter: int = 0

    def _make_handle(self, user_id: int) -> str:
        self._counter += 1
        return f"bg-{user_id}-{self._counter}"

    def active_count(self, user_id: int) -> int:
        prefix = f"bg-{user_id}-"
        return sum(1 for h, p in self._processes.items() if h.startswith(prefix) and not p.finished)

    async def start(
        self,
        command: str,
        work_dir: str,
        user_id: int,
        timeout: int = SHELL_TIMEOUT,
    ) -> tuple[str, str | None]:
        """Start a background process. Returns (handle_id, error_or_none)."""
        self.cleanup_finished()
        try:
            command, validated_dir = guard_shell_command(command, work_dir)
        except ShellCommandRejected as e:
            return "", str(e)

        if self.active_count(user_id) >= SHELL_BG_MAX_PROCESSES:
            return "", f"Too many background processes (max {SHELL_BG_MAX_PROCESSES}). Kill some first."

        handle_id = self._make_handle(user_id)
        bg = BackgroundProcess(
            handle_id=handle_id,
            user_id=user_id,
            command=command,
            work_dir=validated_dir,
            started_at=time.monotonic(),
        )
        self._processes[handle_id] = bg
        bg._collection_task = asyncio.create_task(self._collect(bg, timeout))
        return handle_id, None

    async def _collect(self, bg: BackgroundProcess, timeout: int) -> None:
        try:
            execution = await execute_in_runtime_kernel(
                bg.command, bg.work_dir, timeout=timeout, command_kind="shell_bg"
            )
            if not bool(execution.get("forwarded", False)):
                reason = str(execution.get("reason") or "runtime kernel unavailable")
                log.warning("shell_bg_runtime_kernel_unavailable", handle_id=bg.handle_id, reason=reason)
                bg.stderr_buf = f"Error: {reason}"
                bg.exit_code = -1
                return
            bg.stdout_buf = str(execution.get("stdout") or "")[:SHELL_BG_OUTPUT_MAX]
            bg.stderr_buf = str(execution.get("stderr") or "")[:SHELL_BG_OUTPUT_MAX]
            bg.timed_out = bool(execution.get("timed_out", False))
            bg.exit_code = -1 if bg.timed_out else int(cast(Any, execution.get("exit_code", 0)) or 0)
        except asyncio.CancelledError:
            bg.exit_code = -1
            raise
        except Exception as e:
            log.exception("shell_bg_error", handle_id=bg.handle_id, command=bg.command[:100])
            bg.stderr_buf = f"Error: {e}"
            bg.exit_code = -1
        finally:
            bg.finished = True
            bg.finished_at = time.monotonic()

    def get(self, handle_id: str, *, user_id: int | None = None) -> BackgroundProcess | None:
        bg = self._processes.get(handle_id)
        if bg is None:
            return None
        if user_id is not None and bg.user_id != user_id:
            return None
        return bg

    async def kill(self, handle_id: str, *, user_id: int | None = None) -> str | None:
        bg = self.get(handle_id, user_id=user_id)
        if not bg:
            return f"No process with handle '{handle_id}'."
        if bg.finished:
            return "Process already finished."
        task = bg._collection_task
        if task is not None and not task.done():
            bg.killed = True
            # Cancelling the ExecuteCommand call makes the runtime kernel kill the command's process group.
            task.cancel()
            await asyncio.wait({task})
        return None

    def cleanup_finished(self, max_age: float = 600) -> int:
        """Forget processes that finished more than max_age seconds ago."""
        now = time.monotonic()
        to_remove = [
            h
            for h, p in self._processes.items()
            if p.finished and (now - (p.finished_at if p.finished_at is not None else p.started_at)) > max_age
        ]
        for h in to_remove:
            del self._processes[h]
        return len(to_remove)


# Singleton
bg_process_manager = BackgroundProcessManager()
