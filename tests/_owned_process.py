"""Start a long-lived test helper process that cannot outlive the process that started it.

``subprocess.Popen`` ties nothing to its caller. When pytest dies before its teardown
runs (SIGKILL, a harness timeout's SIGTERM, an agent stopped mid-run), a server it
started keeps running with no owner: D-254 found session guards still running after
nine hours, holding the deleted binaries of a removed worktree open.

:func:`spawn_owned` runs the command under a watchdog, which is this file run as a
script (standard library only, under ``python -I``). The watchdog:

* runs in its own session, so a signal sent to the owner's process group (a harness
  killing the group, Ctrl-C) cannot take the watchdog down before it has acted;
* starts the command as the leader of a new process group, so stopping the command
  also stops what it started (``cargo run`` runs rustc and build scripts before it
  execs the guard);
* stops that group, SIGTERM and then SIGKILL after a grace period, once its parent is
  no longer the owner pid it was given (the owner died, whatever the signal) or when
  it receives SIGTERM, SIGINT or SIGHUP itself (:func:`stop_owned`);
* otherwise exits with the command's status, and dies by the same signal when the
  command did, so the owner sees the returncode it would see without the watchdog.

The parent check cannot be fooled by pid reuse: while the owner lives it is the
watchdog's parent, and once it dies the watchdog is reparented to init or a subreaper,
which cannot hold the owner's pid at that moment. Nothing here reads a pid file or
signals a pid it did not start.

Why a watchdog rather than ``PR_SET_PDEATHSIG`` from pytest: it is Linux-only (macOS
has no equivalent, so a second mechanism would be needed there anyway); it fires when
the parent *thread* exits, so a server started from a worker thread would die early;
it is cleared by credential changes; and it reaches only the direct child, not the
processes cargo starts. The watchdog is one mechanism for both systems, and every
normal teardown runs the same stop path that an owner's death does.

The watchdog itself can still be killed together with its owner (``pkill -9 python``,
say). On Linux the kernel then kills the command: the watchdog sets ``PR_SET_PDEATHSIG``
for it, and the watchdog is single-threaded, so the thread caveat does not apply. On
macOS that one case leaves the command running.
"""

from __future__ import annotations

import contextlib
import ctypes
import os
import resource
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, NoReturn

_WATCHDOG = Path(__file__).resolve()
_POLL_SECONDS = 0.1
# How long the command gets to exit on SIGTERM before the watchdog sends SIGKILL.
_GRACE_SECONDS = 5.0
_PR_SET_PDEATHSIG = 1  # <linux/prctl.h>


def spawn_owned(command: Sequence[str], **popen_kwargs: Any) -> subprocess.Popen[Any]:
    """Start ``command`` so that it exits soon after this process dies; stop it with :func:`stop_owned`.

    The keyword arguments go to :class:`subprocess.Popen` for the watchdog, and the
    command inherits its working directory, environment and standard streams. The
    returned process is the watchdog: it exits when the command does, with its status.
    """
    watchdog = [sys.executable, "-I", str(_WATCHDOG), str(os.getpid()), *command]
    return subprocess.Popen(watchdog, start_new_session=True, **popen_kwargs)


def stop_owned(proc: subprocess.Popen[Any]) -> None:
    """Stop a command started with :func:`spawn_owned` and wait until it and its watchdog are gone."""
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=_GRACE_SECONDS + 5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def _signal_group(child: subprocess.Popen[bytes], signum: int) -> None:
    # The child is not reaped until wait() returns, so its pid still names its group.
    try:
        os.killpg(child.pid, signum)
    except ProcessLookupError:  # the command left its group; it can still be reached directly
        child.send_signal(signum)


def _stop(child: subprocess.Popen[bytes]) -> int:
    _signal_group(child, signal.SIGTERM)
    try:
        return child.wait(timeout=_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        _signal_group(child, signal.SIGKILL)
        return child.wait()


def _exit_with(status: int) -> NoReturn:
    if status < 0:
        signum = -status
        # The command has already dumped core if it was going to; the watchdog must not.
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        with contextlib.suppress(OSError, ValueError):
            signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)
    sys.exit(status if status >= 0 else 128 - status)


def _killed_with_watchdog() -> Callable[[], None] | None:
    """On Linux, a ``preexec_fn`` that makes the kernel SIGKILL the command if the watchdog dies first."""
    if not sys.platform.startswith("linux"):
        return None
    prctl = ctypes.CDLL(None, use_errno=True).prctl
    watchdog = os.getpid()

    def preexec() -> None:
        if prctl(_PR_SET_PDEATHSIG, ctypes.c_ulong(signal.SIGKILL)) != 0:
            raise OSError(ctypes.get_errno(), "prctl(PR_SET_PDEATHSIG)")
        if os.getppid() != watchdog:  # the watchdog died before the setting took effect
            os._exit(1)

    return preexec


def _watch(owner: int, command: list[str]) -> NoReturn:
    stop_requested = False

    def request_stop(signum: int, frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True

    # Handlers, not SIG_IGN: the command must start with the default dispositions.
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, request_stop)
    child = subprocess.Popen(command, process_group=0, preexec_fn=_killed_with_watchdog())
    while (status := child.poll()) is None:
        if stop_requested or os.getppid() != owner:
            status = _stop(child)
            break
        time.sleep(_POLL_SECONDS)
    _exit_with(status)


if __name__ == "__main__":
    _watch(int(sys.argv[1]), sys.argv[2:])
