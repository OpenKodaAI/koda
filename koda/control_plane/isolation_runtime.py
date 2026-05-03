"""Wire cgroup v2 limits into the supervisor's spawn path.

The Linux body of ``WorkspaceLimits`` / ``apply_workspace_limits`` /
``place_pid`` lives in the Rust runtime-kernel crate. This module is
the Python wrapper that the supervisor calls before and after
``asyncio.create_subprocess_exec`` to:

1. Build a per-workspace ``WorkspaceLimits`` from operator-tunable
   defaults (``KODA_AGENT_DEFAULT_*`` env vars).
2. Materialize the cgroup root + the workspace cgroup directory.
3. Move the freshly-spawned worker PID into the cgroup so OOM /
   CPU-throttle events fire at the right granularity.

The implementation re-creates the small Linux file-write surface the
Rust crate has so the supervisor doesn't need a second gRPC seam to
the runtime-kernel for what is a few writes to ``/sys/fs/cgroup``.

On macOS / non-Linux hosts every helper is a no-op so the supervisor
boots unchanged. On Linux without ``CAP_SYS_ADMIN`` the helpers also
soft-fail with a single warn line — production deploys mount the
cgroup root before the supervisor starts; dev hosts simply run
without per-workspace caps.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from koda.logging_config import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class WorkspaceIsolationLimits:
    """Mirrors the Rust ``WorkspaceLimits`` struct. Each ``None`` knob
    leaves the corresponding cgroup file untouched (system default)."""

    workspace_id: str
    memory_max_bytes: int | None = None
    cpu_max_quota_period: tuple[int, int] | None = None
    pids_max: int | None = None


def _is_linux() -> bool:
    import sys

    return sys.platform == "linux"


def _cgroup_root() -> str:
    return os.environ.get("KODA_CGROUP_ROOT") or "/sys/fs/cgroup/koda"


def _sanitize_workspace_segment(workspace_id: str) -> str:
    """Mirror of the Rust crate's sanitizer: keep ASCII alphanumerics
    + ``-`` ``_``; replace anything else (including ``..``, ``/``,
    ``.``) with ``_`` so a malicious workspace_id cannot escape the
    cgroup root."""
    out: list[str] = []
    for ch in workspace_id or "":
        if ch.isascii() and (ch.isalnum() or ch in "-_"):
            out.append(ch)
        else:
            out.append("_")
    safe = "".join(out)
    return safe or "default"


def _workspace_dir(workspace_id: str) -> str:
    return os.path.join(_cgroup_root(), f"ws_{_sanitize_workspace_segment(workspace_id)}")


def ensure_cgroup_v2_root() -> None:
    """Create the cgroup root if missing. Soft-fails on permission
    errors so dev hosts without root privileges still boot."""
    if not _is_linux():
        return
    root = _cgroup_root()
    try:
        if os.path.isdir(root):
            return
        os.makedirs(root, exist_ok=True)
        log.info("isolation_cgroup_root_created", root=root)
    except OSError as exc:
        log.warning(
            "isolation_cgroup_root_unavailable",
            root=root,
            error=str(exc),
            hint="workers will run without per-workspace OS-level limits",
        )


def apply_workspace_limits(limits: WorkspaceIsolationLimits) -> None:
    """Materialize the workspace's cgroup directory and write the
    configured knobs. Idempotent — re-applying the same limits is a
    no-op (cgroup files accept the same value without error)."""
    if not _is_linux():
        return
    target = _workspace_dir(limits.workspace_id)
    try:
        os.makedirs(target, exist_ok=True)
    except OSError as exc:
        log.warning(
            "isolation_workspace_dir_unavailable",
            workspace_id=limits.workspace_id,
            target=target,
            error=str(exc),
        )
        return

    if limits.memory_max_bytes is not None:
        _write_cgroup_file(target, "memory.max", str(int(limits.memory_max_bytes)))
    if limits.cpu_max_quota_period is not None:
        quota, period = limits.cpu_max_quota_period
        _write_cgroup_file(target, "cpu.max", f"{int(quota)} {int(period)}")
    if limits.pids_max is not None:
        _write_cgroup_file(target, "pids.max", str(int(limits.pids_max)))


def place_pid(workspace_id: str, pid: int) -> None:
    """Move ``pid`` into the workspace's cgroup. Called right after
    ``asyncio.create_subprocess_exec`` returns so OOM events fire on
    the worker, not the supervisor."""
    if not _is_linux():
        return
    if not pid or pid < 1:
        return
    target = _workspace_dir(workspace_id)
    if not os.path.isdir(target):
        return
    _write_cgroup_file(target, "cgroup.procs", str(int(pid)))


def _write_cgroup_file(target: str, name: str, value: str) -> None:
    path = os.path.join(target, name)
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(value)
    except OSError as exc:
        log.warning(
            "isolation_cgroup_write_failed",
            path=path,
            value=value,
            error=str(exc),
        )


def default_limits_from_env(workspace_id: str) -> WorkspaceIsolationLimits:
    """Build a default ``WorkspaceIsolationLimits`` from
    ``KODA_AGENT_DEFAULT_*`` env vars. Returns a record with all knobs
    unset when nothing is configured — the supervisor still calls the
    apply path so the cgroup directory exists for future operator
    tuning at runtime."""
    memory_mb = _env_int("KODA_AGENT_DEFAULT_MEMORY_MB")
    cpu_fraction = _env_float("KODA_AGENT_DEFAULT_CPU_FRACTION")
    pids_max = _env_int("KODA_AGENT_DEFAULT_PIDS_MAX")
    cpu_quota: tuple[int, int] | None = None
    if cpu_fraction is not None and cpu_fraction > 0.0:
        # Default cgroup v2 period is 100_000 microseconds (100 ms).
        period = 100_000
        cpu_quota = (max(1, int(cpu_fraction * period)), period)
    return WorkspaceIsolationLimits(
        workspace_id=workspace_id,
        memory_max_bytes=(memory_mb * 1024 * 1024) if memory_mb else None,
        cpu_max_quota_period=cpu_quota,
        pids_max=pids_max,
    )


def _env_int(key: str) -> int | None:
    raw = os.environ.get(key)
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def _env_float(key: str) -> float | None:
    raw = os.environ.get(key)
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None
