"""Per-session Rust security guard for the test suite.

Each pytest session starts its own guard on a Unix socket in a fresh private
directory, so concurrent sessions on one host (worktrees, CI shards, audit
agents) can never reach each other's guard, and an ambient
``SECURITY_GRPC_TARGET`` is ignored like the other environment the suite pins.
``KODA_TEST_SECURITY_GUARD_TARGET`` opts into an already-running guard instead
(for example one guard shared by several worktrees); the session then fails if
that guard is not reachable.

This module must not import ``koda`` at import time: ``conftest.py`` calls
:func:`select_guard_target` before ``koda.config`` reads the environment.
"""

from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

SHARED_TARGET_ENV = "KODA_TEST_SECURITY_GUARD_TARGET"
SKIP_ENV = "KODA_SKIP_SECURITY_GUARD_SERVICE"
STARTUP_TIMEOUT_ENV = "KODA_SECURITY_GUARD_STARTUP_TIMEOUT"
_POLL_SECONDS = 0.5


@dataclass(frozen=True)
class GuardTarget:
    target: str
    shared: bool


class GuardUnavailable(RuntimeError):
    """The guard could not be started or reached."""


class CargoMissing(RuntimeError):
    """``cargo`` is not on PATH, so the suite cannot build its own guard."""


def guard_disabled(environ: MutableMapping[str, str] = os.environ) -> bool:
    return environ.get(SKIP_ENV, "").strip() == "1"


def own_target() -> str:
    """Return a Unix-socket target in a new private directory, removed at exit."""
    # /tmp keeps the socket path short (sun_path is ~104 bytes on macOS).
    socket_dir = tempfile.mkdtemp(prefix="koda-guard-", dir="/tmp" if os.path.isdir("/tmp") else None)
    atexit.register(shutil.rmtree, socket_dir, ignore_errors=True)
    return f"unix://{socket_dir}/guard.sock"


def select_guard_target(environ: MutableMapping[str, str] = os.environ) -> GuardTarget:
    """Pick the guard address for this session and export it as ``SECURITY_GRPC_TARGET``."""
    shared = environ.get(SHARED_TARGET_ENV, "").strip()
    selected = GuardTarget(shared, shared=True) if shared else GuardTarget(own_target(), shared=False)
    environ["SECURITY_GRPC_TARGET"] = selected.target
    return selected


def startup_timeout(environ: MutableMapping[str, str] = os.environ) -> float:
    default = "90" if environ.get("CI") else "20"
    return float(environ.get(STARTUP_TIMEOUT_ENV, default))


def _channel_ready(target: str) -> bool:
    import grpc

    from koda.internal_rpc.common import create_grpc_channel, resolve_grpc_target

    # A fresh channel per poll avoids gRPC's growing reconnect backoff.
    channel = create_grpc_channel(resolve_grpc_target(target)[0])
    try:
        grpc.channel_ready_future(channel).result(timeout=_POLL_SECONDS)
        return True
    except grpc.FutureTimeoutError:
        return False
    finally:
        channel.close()


def wait_until_ready(target: str, timeout: float, proc: subprocess.Popen[str] | None = None) -> None:
    """Block until the guard answers on ``target``; fail fast if ``proc`` exits first."""
    deadline = time.monotonic() + timeout
    while True:
        if _channel_ready(target):
            return
        if proc is not None and proc.poll() is not None:
            raise GuardUnavailable(f"security guard exited with code {proc.returncode} before listening")
        if time.monotonic() >= deadline:
            raise GuardUnavailable(f"security guard did not listen on {target} within {timeout:.0f}s")


def guard_command(root: Path) -> list[str]:
    if shutil.which("cargo") is None:
        raise CargoMissing("cargo")
    return ["cargo", "run", "-p", "koda-security-service", "--manifest-path", str(root / "rust" / "Cargo.toml")]


def _stop(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def _log_tail(log_file: tempfile._TemporaryFileWrapper[str]) -> str:
    log_file.flush()
    log_file.seek(0)
    lines = log_file.read().strip().splitlines()
    return "\n".join(lines[-40:]) or "No service logs were captured."


@contextmanager
def run_own_guard(root: Path, target: str, timeout: float) -> Iterator[None]:
    """Run a guard owned by this session on ``target`` until the context exits."""
    command = guard_command(root)
    env = {**os.environ, "SECURITY_GRPC_TARGET": target}
    with tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8") as log_file:
        proc = subprocess.Popen(command, cwd=root, env=env, stdout=log_file, stderr=log_file, text=True)
        try:
            try:
                wait_until_ready(target, timeout, proc)
            except GuardUnavailable as exc:
                raise GuardUnavailable(f"{exc}\n{_log_tail(log_file)}") from None
            yield
        finally:
            _stop(proc)
