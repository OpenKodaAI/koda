"""A command started with ``spawn_owned`` cannot outlive the process that started it (D-254).

Each check watches a pipe instead of a pid: the command and everything it starts inherit
the pipe's write end, so EOF means every one of them is gone. That needs no pid (which
the system may reuse) and no ``/proc``, and a zombie, which holds no files, counts as gone.
"""

from __future__ import annotations

import errno
import os
import select
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import IO

import pytest

from tests import _owned_process
from tests._owned_process import spawn_owned, stop_owned
from tests.conftest import ROOT_DIR

# Starts a grandchild, so a check also sees whether stopping the command reaches what it started.
_FORKER = (
    "import subprocess, sys, time;"
    " subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)']);"
    " print('ready', flush=True);"
    " time.sleep(120)"
)

# Its own child ignores SIGTERM and reports ready once it does, so only a SIGKILL to the
# command's whole group stops it.
_IGNORES_SIGTERM = (
    "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('ready', flush=True); time.sleep(120)"
)
_STUBBORN_FORKER = (
    f"import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', {_IGNORES_SIGTERM!r}]); time.sleep(120)"
)

# Leaves the process group it was started in, as a daemon or a shell with job control does.
_LEAVES_ITS_GROUP = "import os, time; os.setsid(); print('ready', flush=True); time.sleep(120)"

# Exits at once and leaves its own child running.
_LEAVES_A_CHILD = "import subprocess, sys; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])"

# Stands in for a pytest session: starts the command it is given, reports its watchdog's pid,
# then waits to be killed.
_OWNER = (
    "import sys, time; from tests._owned_process import spawn_owned;"
    " print(spawn_owned(sys.argv[1:]).pid, flush=True); time.sleep(120)"
)


def _read_line(stream: IO[bytes], seconds: float) -> bytes:
    """Read a line from ``stream``'s descriptor, or what arrived of it within ``seconds``.

    One byte at a time, so a following line is left in the pipe, where the next
    ``select()`` sees it, not in a buffer.
    """
    fd = stream.fileno()
    line = b""
    deadline = time.monotonic() + seconds
    while not line.endswith(b"\n") and (remaining := deadline - time.monotonic()) > 0:
        ready, _, _ = select.select([fd], [], [], remaining)
        byte = os.read(fd, 1) if ready else b""
        if not byte:
            break
        line += byte
    return line


def _closed_within(stream: IO[bytes], seconds: float) -> bool:
    """Whether every process holding the write end of ``stream`` exits within ``seconds``."""
    fd = stream.fileno()
    deadline = time.monotonic() + seconds
    while (remaining := deadline - time.monotonic()) > 0:
        ready, _, _ = select.select([fd], [], [], remaining)
        if ready and not os.read(fd, 4096):
            return True
    return False


@pytest.mark.parametrize(
    ("signum", "with_watchdog"),
    [
        pytest.param(signal.SIGKILL, False, id="SIGKILL"),
        pytest.param(signal.SIGTERM, False, id="SIGTERM"),
        # `pkill -9 python` kills the watchdog together with the pytest process that owns it.
        pytest.param(signal.SIGKILL, True, id="SIGKILL-with-its-watchdog"),
    ],
)
def test_command_does_not_outlive_its_owner(signum: signal.Signals, with_watchdog: bool) -> None:
    owner = subprocess.Popen(
        [sys.executable, "-c", _OWNER, sys.executable, "-c", _FORKER],
        cwd=ROOT_DIR,
        stdout=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        assert owner.stdout is not None
        lines = {_read_line(owner.stdout, 30), _read_line(owner.stdout, 30)}
        assert b"ready\n" in lines, f"the command did not start (owner exit {owner.poll()})"
        (watchdog,) = (int(line) for line in lines - {b"ready\n"})

        if with_watchdog:
            # First: until its owner dies, the watchdog stays the owner's child, so its pid cannot be reused.
            os.kill(watchdog, signal.SIGKILL)
        os.kill(owner.pid, signum)
        owner.wait(timeout=10)

        assert _closed_within(owner.stdout, 10), "the command was still running 10s after its owner was killed"
    finally:
        if owner.poll() is None:
            owner.kill()
            owner.wait(timeout=10)


def test_stop_owned_kills_what_ignores_sigterm() -> None:
    proc = spawn_owned([sys.executable, "-c", _STUBBORN_FORKER], stdout=subprocess.PIPE)
    try:
        assert proc.stdout is not None
        assert _read_line(proc.stdout, 30) == b"ready\n"

        stop_owned(proc)

        assert proc.returncode == -signal.SIGTERM
        assert _closed_within(proc.stdout, 10), "a process that ignores SIGTERM outlived stop_owned"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)


def test_what_the_command_started_does_not_outlive_it() -> None:
    proc = spawn_owned([sys.executable, "-c", _LEAVES_A_CHILD], stdout=subprocess.PIPE)
    try:
        assert proc.stdout is not None

        assert proc.wait(timeout=30) == 0

        assert _closed_within(proc.stdout, 10), "a process the command started outlived the command"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)


def test_stop_owned_stops_the_command_and_what_it_started() -> None:
    proc = spawn_owned([sys.executable, "-c", _FORKER], stdout=subprocess.PIPE)
    try:
        assert proc.stdout is not None
        assert _read_line(proc.stdout, 30) == b"ready\n"

        stop_owned(proc)

        assert proc.returncode == -signal.SIGTERM
        assert _closed_within(proc.stdout, 10), "a process the command started outlived stop_owned"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)


def test_stop_owned_asks_a_command_that_left_its_group_to_exit() -> None:
    proc = spawn_owned([sys.executable, "-c", _LEAVES_ITS_GROUP], stdout=subprocess.PIPE)
    try:
        assert proc.stdout is not None
        assert _read_line(proc.stdout, 30) == b"ready\n"

        stop_owned(proc)

        # SIGTERM, not the SIGKILL that follows the grace period.
        assert proc.returncode == -signal.SIGTERM
        assert _closed_within(proc.stdout, 10), "a command that left its group outlived stop_owned"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)


def test_command_and_what_it_started_do_not_outlive_a_killed_watchdog() -> None:
    proc = spawn_owned([sys.executable, "-c", _FORKER], stdout=subprocess.PIPE)
    try:
        assert proc.stdout is not None
        assert _read_line(proc.stdout, 30) == b"ready\n"

        proc.kill()
        proc.wait(timeout=10)

        assert _closed_within(proc.stdout, 10), "the command or its child was still running 10s after its watchdog died"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)


@pytest.mark.parametrize(
    ("code", "status"),
    [
        pytest.param("raise SystemExit(3)", 3, id="exit-code"),
        pytest.param("import os, signal; os.kill(os.getpid(), signal.SIGTERM)", -signal.SIGTERM, id="signal"),
    ],
)
def test_the_watchdog_exits_with_the_command_status(code: str, status: int) -> None:
    proc = spawn_owned([sys.executable, "-c", code])

    assert proc.wait(timeout=30) == status


def test_the_watchdog_reports_a_command_whose_whole_group_was_killed(tmp_path: Path) -> None:
    """A harness may SIGKILL the command's group, anchor included; the watchdog still reports and cleans up."""
    cleanup_dir = tmp_path / "scratch"
    cleanup_dir.mkdir()
    code = "import os, time; print(os.getpgid(0), flush=True); time.sleep(120)"
    proc = spawn_owned([sys.executable, "-c", code], cleanup_dir=str(cleanup_dir), stdout=subprocess.PIPE)
    try:
        assert proc.stdout is not None
        group = int(_read_line(proc.stdout, 30))

        # The watchdog has not reaped the anchor that leads this group, so the id cannot name another group.
        os.killpg(group, signal.SIGKILL)

        assert proc.wait(timeout=10) == -signal.SIGKILL
        assert not cleanup_dir.exists()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)


def test_signalling_a_group_with_no_member_left_to_signal_is_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """macOS's killpg skips zombies and fails with EPERM when only the anchor's zombie is left."""

    def killpg(group: int, signum: int) -> None:
        raise PermissionError(errno.EPERM, os.strerror(errno.EPERM))

    monkeypatch.setattr(os, "killpg", killpg)

    _owned_process._signal_group(os.getpid(), signal.SIGKILL)


def test_a_relative_cleanup_dir_is_resolved_against_the_callers_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    caller, command_cwd = tmp_path / "caller", tmp_path / "command"
    for base in (caller, command_cwd):
        (base / "scratch").mkdir(parents=True)
    monkeypatch.chdir(caller)

    proc = spawn_owned([sys.executable, "-c", "pass"], cleanup_dir="scratch", cwd=command_cwd)

    assert proc.wait(timeout=30) == 0
    assert not (caller / "scratch").exists(), "the caller's directory was kept"
    assert (command_cwd / "scratch").is_dir(), "a directory in the command's working directory was removed"


def test_read_line_leaves_a_line_that_arrived_with_it_for_the_next_call() -> None:
    """Two lines can arrive together: a buffered readline takes both, and the next select then waits in vain."""
    read_fd, write_fd = os.pipe()
    try:
        with os.fdopen(read_fd, "rb") as stream:
            os.write(write_fd, b"first\nsecond\n")

            assert [_read_line(stream, 1), _read_line(stream, 1)] == [b"first\n", b"second\n"]
    finally:
        os.close(write_fd)


def test_imports_where_the_resource_module_is_missing() -> None:
    """tests/conftest.py imports this module, so a platform without ``resource`` must still collect the suite."""
    code = "import sys; sys.modules['resource'] = None; import tests._security_guard"

    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT_DIR, capture_output=True, text=True, timeout=60)

    assert result.returncode == 0, result.stderr
