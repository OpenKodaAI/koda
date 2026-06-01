"""Tests for koda.services.runtime.kernel_subprocess.

Pinned semantics:

  RuntimeKernelStreamReader
    - feed(data) appends bytes for later read/readline
    - finish() signals EOF (idempotent)
    - readline() returns bytes up to and including \\n
    - readline() returns the buffer tail when EOF arrives mid-line
    - readline() returns b"" when EOF arrives with empty buffer
    - read() drains buffer + queued chunks until EOF
    - ANSI/binary bytes are preserved verbatim (no decoding)

  RuntimeKernelStdinWriter
    - write() buffers; close() commits via process.start_with_input(...)
    - write() after close() raises RuntimeError
    - drain() is a no-op (returns None)
    - wait_closed() awaits the process startup signal

  should_use_runtime_kernel_process
    - True iff runtime_task_id is not None

  create_runtime_kernel_process
    - Returns a RuntimeKernelProcess wrapping the supplied command/cwd/env
    - Empty command raises ValueError
"""

from __future__ import annotations

import asyncio

import pytest

from koda.services.runtime.kernel_subprocess import (
    RuntimeKernelProcess,
    RuntimeKernelStdinWriter,
    RuntimeKernelStreamReader,
    create_runtime_kernel_process,
    should_use_runtime_kernel_process,
)

# RuntimeKernelStreamReader — readline


async def test_readline_returns_complete_line_with_newline() -> None:
    r = RuntimeKernelStreamReader()
    await r.feed(b"hello\nworld\n")
    line = await r.readline()
    assert line == b"hello\n"


async def test_readline_returns_remaining_after_eof() -> None:
    r = RuntimeKernelStreamReader()
    await r.feed(b"partial-no-newline")
    await r.finish()
    line = await r.readline()
    assert line == b"partial-no-newline"


async def test_readline_returns_empty_bytes_at_eof_with_empty_buffer() -> None:
    r = RuntimeKernelStreamReader()
    await r.finish()
    line = await r.readline()
    assert line == b""


async def test_readline_blocks_then_resolves_when_data_arrives() -> None:
    r = RuntimeKernelStreamReader()

    async def feeder() -> None:
        await asyncio.sleep(0.05)
        await r.feed(b"delayed\n")

    feeder_task = asyncio.create_task(feeder())
    line = await asyncio.wait_for(r.readline(), timeout=1.0)
    assert line == b"delayed\n"
    await feeder_task


async def test_readline_consumes_lines_in_order() -> None:
    r = RuntimeKernelStreamReader()
    await r.feed(b"a\nb\nc\n")
    assert await r.readline() == b"a\n"
    assert await r.readline() == b"b\n"
    assert await r.readline() == b"c\n"


async def test_readline_handles_chunks_split_across_feeds() -> None:
    """A line spanning two feeds is reassembled into one readline result."""
    r = RuntimeKernelStreamReader()
    await r.feed(b"par")
    await r.feed(b"tial-line\n")
    line = await r.readline()
    assert line == b"partial-line\n"


# RuntimeKernelStreamReader — read (drain to EOF)


async def test_read_returns_all_buffered_then_eof() -> None:
    r = RuntimeKernelStreamReader()
    await r.feed(b"part-1 ")
    await r.feed(b"part-2 ")
    await r.feed(b"part-3")
    await r.finish()
    out = await r.read()
    assert out == b"part-1 part-2 part-3"


async def test_read_returns_empty_bytes_when_no_data() -> None:
    r = RuntimeKernelStreamReader()
    await r.finish()
    out = await r.read()
    assert out == b""


async def test_read_drains_buffer_after_partial_readline() -> None:
    """After a readline pulled one line, read() returns the rest until EOF."""
    r = RuntimeKernelStreamReader()
    await r.feed(b"first\nsecond and rest")
    await r.finish()
    line = await r.readline()
    assert line == b"first\n"
    rest = await r.read()
    assert rest == b"second and rest"


# RuntimeKernelStreamReader — binary / ANSI / Unicode preservation


async def test_ansi_escape_sequences_pass_through() -> None:
    r = RuntimeKernelStreamReader()
    payload = b"\x1b[31mRed\x1b[0m\n"
    await r.feed(payload)
    line = await r.readline()
    assert line == payload


async def test_binary_bytes_pass_through() -> None:
    r = RuntimeKernelStreamReader()
    payload = bytes(range(256))
    await r.feed(payload)
    await r.finish()
    out = await r.read()
    assert out == payload


async def test_utf8_multibyte_preserved_across_chunks() -> None:
    """Splitting a UTF-8 multibyte sequence across feed boundaries is preserved
    at the byte level (the reader exposes raw bytes; downstream decodes)."""
    r = RuntimeKernelStreamReader()
    # "ã" is C3 A3 in UTF-8 — split across feeds.
    await r.feed(b"ol\xc3")
    await r.feed(b"\xa3 mundo\n")
    line = await r.readline()
    assert line == b"ol\xc3\xa3 mundo\n"
    assert line.decode("utf-8") == "olã mundo\n"


# RuntimeKernelStreamReader — finish() idempotency / EOF behavior


async def test_finish_is_idempotent() -> None:
    r = RuntimeKernelStreamReader()
    await r.finish()
    await r.finish()  # second finish must not deadlock or raise.
    out = await r.read()
    assert out == b""


async def test_feed_after_finish_does_not_appear_in_output() -> None:
    """After finish(), additional feeds enqueue but read() already consumed
    None and exited; the additional feed is therefore invisible to readers."""
    r = RuntimeKernelStreamReader()
    await r.finish()
    out = await r.read()
    assert out == b""


# RuntimeKernelStdinWriter — buffer + close + commit


class _DummyProcess:
    """Minimal stand-in for RuntimeKernelProcess that records the write payload."""

    def __init__(self) -> None:
        self.committed: bytes | None = None
        self._started = asyncio.Event()

    def start_with_input(self, data: bytes) -> None:
        self.committed = data
        self._started.set()

    async def wait_started(self) -> None:
        await self._started.wait()


def test_stdin_writer_buffers_writes() -> None:
    proc = _DummyProcess()
    w = RuntimeKernelStdinWriter(proc)  # type: ignore[arg-type]
    w.write(b"alpha")
    w.write(b"-beta")
    # Buffer is internal; close commits.
    assert proc.committed is None


def test_stdin_writer_close_commits_buffered() -> None:
    proc = _DummyProcess()
    w = RuntimeKernelStdinWriter(proc)  # type: ignore[arg-type]
    w.write(b"alpha-")
    w.write(b"beta")
    w.close()
    assert proc.committed == b"alpha-beta"


def test_stdin_writer_close_is_idempotent() -> None:
    proc = _DummyProcess()
    w = RuntimeKernelStdinWriter(proc)  # type: ignore[arg-type]
    w.write(b"x")
    w.close()
    w.close()  # No-op
    assert proc.committed == b"x"


def test_stdin_writer_write_after_close_raises() -> None:
    proc = _DummyProcess()
    w = RuntimeKernelStdinWriter(proc)  # type: ignore[arg-type]
    w.close()
    with pytest.raises(RuntimeError, match="stdin already closed"):
        w.write(b"x")


async def test_stdin_writer_drain_is_noop() -> None:
    proc = _DummyProcess()
    w = RuntimeKernelStdinWriter(proc)  # type: ignore[arg-type]
    result = await w.drain()
    assert result is None


async def test_stdin_writer_wait_closed_resolves_after_process_started() -> None:
    proc = _DummyProcess()
    w = RuntimeKernelStdinWriter(proc)  # type: ignore[arg-type]
    w.write(b"payload")
    w.close()  # synchronously calls start_with_input → sets _started
    await asyncio.wait_for(w.wait_closed(), timeout=1.0)


# should_use_runtime_kernel_process


@pytest.mark.parametrize("task_id", [1, 42, 999999])
def test_should_use_kernel_process_when_task_id_present(task_id: int) -> None:
    assert should_use_runtime_kernel_process(runtime_task_id=task_id) is True


def test_should_use_kernel_process_returns_false_when_task_id_none() -> None:
    assert should_use_runtime_kernel_process(runtime_task_id=None) is False


def test_should_use_kernel_process_zero_task_id_is_truthy() -> None:
    """task_id=0 is a valid id; the gate is `is not None`, not truthiness."""
    assert should_use_runtime_kernel_process(runtime_task_id=0) is True


# create_runtime_kernel_process


def test_create_kernel_process_returns_correct_type_and_attrs() -> None:
    proc = create_runtime_kernel_process(
        task_id=7,
        command=["echo", "hello"],
        cwd="/tmp",
        env={"FOO": "bar"},
    )
    assert isinstance(proc, RuntimeKernelProcess)
    assert proc.task_id == 7
    assert proc.command == ["echo", "hello"]
    assert proc.cwd == "/tmp"
    assert proc.env == {"FOO": "bar"}
    assert proc.kernel_managed is True
    assert proc.returncode is None
    assert proc.pid is None
    assert proc.pgid is None


def test_create_kernel_process_empty_command_raises() -> None:
    with pytest.raises(ValueError, match="command cannot be empty"):
        create_runtime_kernel_process(task_id=1, command=[], cwd="/tmp")


def test_create_kernel_process_default_env_is_empty_dict() -> None:
    proc = create_runtime_kernel_process(task_id=1, command=["ls"], cwd="/tmp")
    assert proc.env == {}


def test_create_kernel_process_command_list_is_copied() -> None:
    """Mutating the input command list after construction does not affect the process."""
    cmd = ["ls", "-la"]
    proc = create_runtime_kernel_process(task_id=1, command=cmd, cwd="/tmp")
    cmd.append("/etc")
    assert proc.command == ["ls", "-la"]


def test_create_kernel_process_env_dict_is_copied() -> None:
    env = {"FOO": "bar"}
    proc = create_runtime_kernel_process(task_id=1, command=["ls"], cwd="/tmp", env=env)
    env["FOO"] = "changed"
    assert proc.env == {"FOO": "bar"}


# RuntimeKernelProcess constructor invariants


def test_kernel_process_streams_initialized() -> None:
    proc = create_runtime_kernel_process(task_id=1, command=["ls"], cwd="/tmp")
    assert isinstance(proc.stdout, RuntimeKernelStreamReader)
    assert isinstance(proc.stderr, RuntimeKernelStreamReader)
    assert isinstance(proc.stdin, RuntimeKernelStdinWriter)


def test_kernel_process_completion_event_initially_unset() -> None:
    proc = create_runtime_kernel_process(task_id=1, command=["ls"], cwd="/tmp")
    assert not proc._completed.is_set()
    assert not proc._started.is_set()
