"""Start a long-lived test helper process that cannot outlive the process that started it.

``subprocess.Popen`` ties nothing to its caller. When pytest dies before its teardown
runs (SIGKILL, a harness timeout's SIGTERM, an agent stopped mid-run), a server it
started keeps running with no owner: D-254 found session guards still running after
nine hours, holding the deleted binaries of a removed worktree open.

:func:`spawn_owned` runs the command under a watchdog, which is this file run as a
script (standard library only, under ``python -I``). The watchdog:

* runs in its own session, so a signal sent to the owner's process group (a harness
  killing the group, Ctrl-C) cannot take the watchdog down before it has acted;
* starts the command in a new process group, so stopping the command also stops what it
  started (``cargo run`` runs rustc and build scripts before it execs the guard);
* stops that group once its parent is no longer the owner pid it was given (the owner
  died, whatever the signal) or when it receives SIGTERM, SIGINT or SIGHUP itself
  (:func:`stop_owned`): SIGTERM to the group, up to a grace period for the command to
  exit, then SIGKILL to the group, which also ends members that ignore SIGTERM. A
  command that has left the group (``setsid()``, ``setpgid(0, 0)``) gets that SIGTERM and
  SIGKILL sent to it alone;
* sends the group that SIGKILL as well when the command exits by itself, so nothing it
  started in the group is left behind;
* then removes ``cleanup_dir`` if one was given (a killed owner's atexit handlers never
  run), and exits with the command's status, dying by the same signal when the command
  did, so the owner sees the returncode it would see without the watchdog.

The group's leader is an *anchor*: a ``/bin/sh`` that ignores SIGHUP, SIGINT and SIGTERM
and blocks reading a pipe that only the watchdog holds. It does two things:

* It keeps the group id from being reused. The watchdog reaps the anchor only after its
  last signal to the group, so until then the id is the pid of a process that still
  exists, alive or a zombie, and no other group can have it.
* It ends the group if the watchdog dies first. Its read returns once the watchdog is
  gone, whatever the signal, and it then sends SIGKILL to its whole group, itself
  included. This works the same on Linux and macOS, also for what the command started,
  and it covers ``pkill -9 python``, which kills the watchdog with pytest but leaves the
  shell. It reaches only its group: a process that has left the group, the command
  included, keeps running if the watchdog dies. A process that stays in the group keeps
  running only after a kill that picks out both the watchdog and the anchor, or the
  anchor alone just before the watchdog dies.

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
"""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, NoReturn

_WATCHDOG = Path(__file__).resolve()
_POLL_SECONDS = 0.1
# How long the command gets to exit on SIGTERM before the watchdog sends SIGKILL.
_GRACE_SECONDS = 5.0
# The leader of the command's process group (see the module docstring). Its stdin is a pipe
# whose only writer is the watchdog: the command does not inherit it (close_fds).
_ANCHOR = ("/bin/sh", "-c", "trap '' HUP INT TERM; read -r line; kill -s KILL 0")


def spawn_owned(
    command: Sequence[str], *, cleanup_dir: str | None = None, **popen_kwargs: Any
) -> subprocess.Popen[Any]:
    """Start ``command`` so that it exits soon after this process dies; stop it with :func:`stop_owned`.

    The keyword arguments go to :class:`subprocess.Popen` for the watchdog, and the
    command inherits its working directory, environment and standard streams. The
    returned process is the watchdog: it exits when the command does, with its status.
    ``cleanup_dir`` is removed, with its contents, once the command and every process in
    its group are gone; pass only a directory this process created for the command. A
    relative ``cleanup_dir`` is taken relative to this process's working directory, not to
    ``cwd``.
    """
    cleanup = os.path.abspath(cleanup_dir) if cleanup_dir else ""
    watchdog = [sys.executable, "-I", str(_WATCHDOG), str(os.getpid()), cleanup, *command]
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


def _signal_group(group: int, signum: int) -> None:
    # The anchor is not reaped yet, so ``group`` cannot name another group. These errors
    # mean no member is left that this process may signal: ESRCH, or EPERM on macOS, whose
    # killpg skips zombies and fails with EPERM when the anchor's zombie is all that is left.
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(group, signum)


def _terminate_if_outside(child: subprocess.Popen[bytes], group: int) -> None:
    # The command is not reaped yet, so its pid still names it. A command that has left
    # ``group`` is out of reach of the group's SIGTERM.
    with contextlib.suppress(ProcessLookupError):
        if os.getpgid(child.pid) != group:
            child.terminate()


def _exit_with(status: int) -> NoReturn:
    if status < 0:
        # POSIX-only, so imported here: tests/conftest.py imports this module on every platform.
        import resource

        signum = -status
        # The command has already dumped core if it was going to; the watchdog must not.
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        with contextlib.suppress(OSError, ValueError):
            signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)
    sys.exit(status if status >= 0 else 128 - status)


def _watch(owner: int, cleanup_dir: str, command: list[str]) -> NoReturn:
    stop_requested = False

    def request_stop(signum: int, frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True

    # Handlers, not SIG_IGN: the command must start with the default dispositions.
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, request_stop)
    anchor = subprocess.Popen(_ANCHOR, stdin=subprocess.PIPE, process_group=0)
    try:
        child = subprocess.Popen(command, process_group=anchor.pid)
        while child.poll() is None:
            if stop_requested or os.getppid() != owner:
                _signal_group(anchor.pid, signal.SIGTERM)
                _terminate_if_outside(child, anchor.pid)
                with contextlib.suppress(subprocess.TimeoutExpired):
                    child.wait(timeout=_GRACE_SECONDS)
                break
            time.sleep(_POLL_SECONDS)
    finally:
        _signal_group(anchor.pid, signal.SIGKILL)
        anchor.wait()
    child.kill()  # only if it left the group and outlived the grace period
    status = child.wait()
    if cleanup_dir:
        shutil.rmtree(cleanup_dir, ignore_errors=True)
    _exit_with(status)


if __name__ == "__main__":
    _watch(int(sys.argv[1]), sys.argv[2], sys.argv[3:])
