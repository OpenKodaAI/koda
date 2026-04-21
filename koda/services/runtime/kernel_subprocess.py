"""Kernel-backed subprocess adapter for runtime-scoped provider execution."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from koda.logging_config import get_logger

log = get_logger(__name__)


class RuntimeKernelStreamReader:
    """Minimal stream-reader facade backed by runtime-kernel chunks."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._buffer = bytearray()
        self._eof = False
        self._closed = False
        self._limit = 64 * 1024

    async def feed(self, data: bytes) -> None:
        if data:
            await self._queue.put(bytes(data))

    async def finish(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._queue.put(None)

    async def readline(self) -> bytes:
        while True:
            newline = self._buffer.find(b"\n")
            if newline >= 0:
                result = bytes(self._buffer[: newline + 1])
                del self._buffer[: newline + 1]
                return result
            if self._eof:
                if not self._buffer:
                    return b""
                result = bytes(self._buffer)
                self._buffer.clear()
                return result
            item = await self._queue.get()
            if item is None:
                self._eof = True
                continue
            self._buffer.extend(item)

    async def read(self) -> bytes:
        chunks: list[bytes] = []
        if self._buffer:
            chunks.append(bytes(self._buffer))
            self._buffer.clear()
        while not self._eof:
            item = await self._queue.get()
            if item is None:
                self._eof = True
                break
            chunks.append(item)
        return b"".join(chunks)


class RuntimeKernelStdinWriter:
    """Buffer stdin until the remote process is started."""

    def __init__(self, process: RuntimeKernelProcess) -> None:
        self._process = process
        self._buffer = bytearray()
        self._closed = False

    def write(self, data: bytes) -> None:
        if self._closed:
            raise RuntimeError("stdin already closed")
        self._buffer.extend(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._process.start_with_input(bytes(self._buffer))

    async def wait_closed(self) -> None:
        await self._process.wait_started()


class RuntimeKernelProcess:
    """Async subprocess-like facade backed by the runtime kernel."""

    kernel_managed = True

    def __init__(
        self,
        *,
        task_id: int,
        command: list[str],
        cwd: str,
        env: Mapping[str, str] | None = None,
    ) -> None:
        if not command:
            raise ValueError("command cannot be empty")
        self.task_id = task_id
        self.command = list(command)
        self.cwd = cwd
        self.env = dict(env or {})
        self.process_id = ""
        self.pid: int | None = None
        self.pgid: int | None = None
        self.returncode: int | None = None
        self.stdout = RuntimeKernelStreamReader()
        self.stderr = RuntimeKernelStreamReader()
        self.stdin = RuntimeKernelStdinWriter(self)
        self._start_lock = asyncio.Lock()
        self._started = asyncio.Event()
        self._completed = asyncio.Event()
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._wait_task: asyncio.Task[None] | None = None
        self._start_error: BaseException | None = None
        self._pending_input: bytes | None = None

    def start_with_input(self, data: bytes) -> None:
        self._pending_input = data
        asyncio.create_task(self._ensure_started())

    async def wait_started(self) -> None:
        await self._ensure_started()
        await self._started.wait()
        if self._start_error is not None:
            raise RuntimeError(str(self._start_error))

    async def _runtime_kernel(self) -> Any:
        from koda.services.runtime import get_runtime_controller

        runtime = get_runtime_controller()
        return runtime.runtime_kernel

    async def _ensure_started(self) -> None:
        if self._started.is_set():
            return
        async with self._start_lock:
            if self._started.is_set():
                return
            try:
                kernel = await self._runtime_kernel()
                result = await kernel.start_task(
                    task_id=self.task_id,
                    command=self.command[0],
                    args=self.command[1:],
                    working_directory=self.cwd,
                    environment_overrides=self.env,
                    stdin_payload=self._pending_input or b"",
                    start_new_session=True,
                )
                if not bool(result.get("forwarded")):
                    raise RuntimeError(str(result.get("reason") or "runtime-kernel start_task unavailable"))
                self.process_id = str(result.get("process_id") or "")
                self.pid = int(result.get("pid") or 0) or None
                self.pgid = int(result.get("pgid") or 0) or None
                self._stdout_task = asyncio.create_task(self._pump_stream("stdout", self.stdout))
                self._stderr_task = asyncio.create_task(self._pump_stream("stderr", self.stderr))
                self._wait_task = asyncio.create_task(self._wait_for_completion())
            except BaseException as exc:  # pragma: no cover - surfaced to callers
                self._start_error = exc
                await self.stdout.finish()
                await self.stderr.finish()
            finally:
                self._started.set()

    async def _pump_stream(self, stream: str, reader: RuntimeKernelStreamReader) -> None:
        try:
            kernel = await self._runtime_kernel()
            async for chunk in kernel.stream_terminal(task_id=self.task_id, stream=stream):
                await reader.feed(chunk)
        except Exception as exc:  # pragma: no cover - depends on kernel transport/runtime
            log.exception("runtime_kernel_stream_failed", task_id=self.task_id, stream=stream)
            await reader.feed(f"\n[runtime kernel {stream} stream failed: {exc}]\n".encode("utf-8", errors="replace"))
        finally:
            await reader.finish()

    async def _wait_for_completion(self) -> None:
        try:
            if self._stdout_task is not None:
                await self._stdout_task
            if self._stderr_task is not None:
                await self._stderr_task
            kernel = await self._runtime_kernel()
            snapshot = await kernel.collect_snapshot(task_id=self.task_id)
            task_payload = snapshot.get("task", {}) if isinstance(snapshot, dict) else {}
            if isinstance(task_payload, dict):
                exit_code = task_payload.get("exit_code")
                if exit_code is not None:
                    self.returncode = int(exit_code)
            if self.returncode is None:
                self.returncode = 0
        finally:
            self._completed.set()

    async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
        if input is not None:
            self._pending_input = bytes(input)
        await self._ensure_started()
        await self.wait()
        stdout = await self.stdout.read()
        stderr = await self.stderr.read()
        return stdout, stderr

    async def wait(self) -> int:
        await self.wait_started()
        await self._completed.wait()
        return int(self.returncode or 0)

    async def terminate(self) -> None:
        kernel = await self._runtime_kernel()
        await kernel.terminate_task(task_id=self.task_id, force=False)

    async def kill(self) -> None:
        kernel = await self._runtime_kernel()
        await kernel.terminate_task(task_id=self.task_id, force=True)


def should_use_runtime_kernel_process(*, runtime_task_id: int | None) -> bool:
    return runtime_task_id is not None


def create_runtime_kernel_process(
    *,
    task_id: int,
    command: list[str],
    cwd: str,
    env: Mapping[str, str] | None = None,
) -> RuntimeKernelProcess:
    return RuntimeKernelProcess(task_id=task_id, command=command, cwd=cwd, env=env)
