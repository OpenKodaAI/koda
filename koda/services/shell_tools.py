"""Background shell process manager for agent tools."""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass, field

from koda.config import SHELL_BG_MAX_PROCESSES, SHELL_BG_OUTPUT_MAX, SHELL_TIMEOUT
from koda.logging_config import get_logger
from koda.services.provider_env import build_tool_subprocess_env, validate_runtime_path, validate_shell_command

log = get_logger(__name__)


@dataclass
class BackgroundProcess:
    handle_id: str
    command: str
    work_dir: str
    started_at: float
    process: asyncio.subprocess.Process | None = None
    stdout_buf: str = ""
    stderr_buf: str = ""
    exit_code: int | None = None
    finished: bool = False
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
        if self.active_count(user_id) >= SHELL_BG_MAX_PROCESSES:
            return "", f"Too many background processes (max {SHELL_BG_MAX_PROCESSES}). Kill some first."

        try:
            command = validate_shell_command(command)
            validated_dir = validate_runtime_path(work_dir, allow_empty=True)
        except ValueError as e:
            return "", f"Blocked: {e}"

        handle_id = self._make_handle(user_id)
        proc_env = build_tool_subprocess_env()

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=validated_dir,
                env=proc_env,
                start_new_session=True,
            )
        except Exception as e:
            return "", f"Failed to start: {e}"

        bg = BackgroundProcess(
            handle_id=handle_id,
            command=command,
            work_dir=validated_dir,
            started_at=time.monotonic(),
            process=process,
        )
        self._processes[handle_id] = bg

        async def _collect() -> None:
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=max(1, timeout))
                bg.stdout_buf = (stdout_bytes or b"").decode(errors="replace")[:SHELL_BG_OUTPUT_MAX]
                bg.stderr_buf = (stderr_bytes or b"").decode(errors="replace")[:SHELL_BG_OUTPUT_MAX]
                bg.exit_code = process.returncode
            except TimeoutError:
                bg.timed_out = True
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
                bg.exit_code = -1
            finally:
                bg.finished = True

        bg._collection_task = asyncio.create_task(_collect())
        return handle_id, None

    def get(self, handle_id: str) -> BackgroundProcess | None:
        return self._processes.get(handle_id)

    async def kill(self, handle_id: str) -> str | None:
        bg = self._processes.get(handle_id)
        if not bg:
            return f"No process with handle '{handle_id}'."
        if bg.finished:
            return "Process already finished."
        if bg.process:
            try:
                bg.process.kill()
                bg.killed = True
            except ProcessLookupError:
                pass
        return None

    def cleanup_finished(self, max_age: float = 600) -> int:
        """Remove finished processes older than max_age seconds."""
        now = time.monotonic()
        to_remove = [h for h, p in self._processes.items() if p.finished and (now - p.started_at) > max_age]
        for h in to_remove:
            del self._processes[h]
        return len(to_remove)


# Singleton
bg_process_manager = BackgroundProcessManager()
