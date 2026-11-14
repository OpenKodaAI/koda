"""Process hygiene for the agent worker (ADR-002 §2.4 L1, AG-04).

The worker's environment holds the Postgres DSN, the S3 secret, granted secrets
and runtime tokens, and the processes it starts (provider CLIs, MCP stdio
servers, governed shell and git, media tools) run as the same uid. On Linux a
same-uid process may read ``/proc/<pid>/environ`` and ``/proc/<pid>/mem`` of any
*dumpable* process without a capability, and a crash can write the whole address
space to a core file.

:func:`harden_process` closes both. ``koda/__main__.py`` calls it as its first
statement, so ``python -m koda`` and the ``koda-runtime-worker`` script are both
covered:

* ``prctl(PR_SET_DUMPABLE, 0)`` (Linux): ``/proc/<pid>/*`` becomes owned by root
  and ptrace-mode access (environ, mem, fd, ptrace attach) is refused to any
  caller without ``CAP_SYS_PTRACE``. The worker writes no core.
* ``RLIMIT_CORE`` soft and hard limit 0: inherited by every child, which cannot
  raise it again without ``CAP_SYS_RESOURCE``. ``execve`` makes a child dumpable
  again, so this limit is what keeps children's cores off.

It fails closed: when either setting cannot be applied it raises
:class:`ProcessHardeningError` and the worker does not start.

It cannot cover Python's own startup (the interpreter, ``site`` and ``.pth``
processing, ``koda/__init__.py``), which runs before the entrypoint. Until then
the worker is dumpable and a same-uid process can read its environment. The
"startup window" residual in ``docs/operations/hardening.md`` describes it. Only
ADR-002's L2 confinement closes it, once AG-14 (provider CLIs, governed shell and
git that the worker starts), AG-15 (the kernel's ``StartTask`` and
``ExecuteCommand`` children) and AG-16 (MCP stdio servers, media tools and
chromium) have all shipped. It stays open under ``RUNTIME_CONFINEMENT=off``, and
for class U processes (MCP stdio servers, media tools, chromium) on a host
without L2, which still run unconfined with only a health warning.
"""

from __future__ import annotations

import ctypes
import os
import resource
import sys

# <linux/prctl.h>
PR_GET_DUMPABLE = 3
PR_SET_DUMPABLE = 4


class ProcessHardeningError(RuntimeError):
    """The process could not be made non-dumpable or have core dumps disabled."""


def harden_process() -> None:
    """Make this process non-dumpable (Linux) and set ``RLIMIT_CORE`` to zero."""
    if sys.platform.startswith("linux"):
        _disable_dumpable()
    _disable_core_dumps()


def _disable_dumpable() -> None:
    try:
        prctl = ctypes.CDLL(None, use_errno=True).prctl
    except (OSError, AttributeError) as exc:
        raise ProcessHardeningError(f"cannot load prctl from libc: {exc}") from exc
    zero = ctypes.c_ulong(0)
    if prctl(PR_SET_DUMPABLE, zero, zero, zero, zero) != 0:
        errno = ctypes.get_errno()
        raise ProcessHardeningError(f"prctl(PR_SET_DUMPABLE, 0) failed: {os.strerror(errno)} (errno {errno})")
    state = prctl(PR_GET_DUMPABLE, zero, zero, zero, zero)
    if state != 0:
        raise ProcessHardeningError(f"process is still dumpable after PR_SET_DUMPABLE (state {state})")


def _disable_core_dumps() -> None:
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except (OSError, ValueError) as exc:
        raise ProcessHardeningError(f"setrlimit(RLIMIT_CORE, 0) failed: {exc}") from exc
