"""Generic subprocess termination helpers."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
from typing import Any, cast


def _process_group_id(proc: object) -> int | None:
    explicit_pgid = getattr(proc, "pgid", None)
    if isinstance(explicit_pgid, int) and explicit_pgid > 0:
        return explicit_pgid
    pid = getattr(proc, "pid", None)
    if not isinstance(pid, int) or pid <= 0:
        return None
    with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
        return os.getpgid(pid)
    return None


async def terminate_process_tree(proc: object) -> None:
    """Terminate a process and its process group when possible."""
    terminate_method = getattr(proc, "terminate", None)
    if callable(terminate_method) and getattr(proc, "kernel_managed", False) is True:
        terminate_result = terminate_method()
        if asyncio.iscoroutine(terminate_result):
            await terminate_result
        return
    pgid = _process_group_id(proc)
    if pgid is not None:
        with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
            os.killpg(pgid, signal.SIGTERM)
            return
    with contextlib.suppress(ProcessLookupError):
        kill_result = cast(Any, proc).kill()
        if asyncio.iscoroutine(kill_result):
            await kill_result
