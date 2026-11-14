"""A command started with ``spawn_owned`` cannot outlive the process that started it (D-254).

Each check watches a pipe instead of a pid: the command and everything it starts inherit
the pipe's write end, so EOF means every one of them is gone. That needs no pid (which
the system may reuse) and no ``/proc``, and a zombie, which holds no files, counts as gone.
"""

from __future__ import annotations

import os
import select
import signal
import subprocess
import sys
import time
from typing import IO

import pytest

from tests._owned_process import spawn_owned, stop_owned
from tests.conftest import ROOT_DIR

# Starts a grandchild, so a check also sees whether stopping the command reaches what it started.
_FORKER = (
    "import subprocess, sys, time;"
    " subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)']);"
    " print('ready', flush=True);"
    " time.sleep(120)"
)

# Stands in for a pytest session: starts the command it is given, then waits to be killed.
_OWNER = "import sys, time; from tests._owned_process import spawn_owned; spawn_owned(sys.argv[1:]); time.sleep(120)"


def _read_line(stream: IO[bytes], seconds: float) -> bytes:
    ready, _, _ = select.select([stream], [], [], seconds)
    return stream.readline() if ready else b""


def _closed_within(stream: IO[bytes], seconds: float) -> bool:
    """Whether every process holding the write end of ``stream`` exits within ``seconds``."""
    fd = stream.fileno()
    deadline = time.monotonic() + seconds
    while (remaining := deadline - time.monotonic()) > 0:
        ready, _, _ = select.select([fd], [], [], remaining)
        if ready and not os.read(fd, 4096):
            return True
    return False


@pytest.mark.parametrize("signum", [signal.SIGKILL, signal.SIGTERM], ids=["SIGKILL", "SIGTERM"])
def test_command_does_not_outlive_its_owner(signum: signal.Signals) -> None:
    owner = subprocess.Popen(
        [sys.executable, "-c", _OWNER, sys.executable, "-c", _FORKER],
        cwd=ROOT_DIR,
        stdout=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        assert owner.stdout is not None
        assert _read_line(owner.stdout, 30) == b"ready\n", f"the command did not start (owner exit {owner.poll()})"

        os.kill(owner.pid, signum)
        owner.wait(timeout=10)

        assert _closed_within(owner.stdout, 10), "the command was still running 10s after its owner was killed"
    finally:
        if owner.poll() is None:
            owner.kill()
            owner.wait(timeout=10)


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


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="PR_SET_PDEATHSIG is Linux-only")
def test_command_does_not_outlive_a_killed_watchdog_on_linux() -> None:
    proc = spawn_owned(
        [sys.executable, "-c", "import time; print('ready', flush=True); time.sleep(120)"], stdout=subprocess.PIPE
    )
    try:
        assert proc.stdout is not None
        assert _read_line(proc.stdout, 30) == b"ready\n"

        proc.kill()
        proc.wait(timeout=10)

        assert _closed_within(proc.stdout, 10), "the command was still running 10s after its watchdog was killed"
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
