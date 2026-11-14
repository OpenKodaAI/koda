"""Shared fixtures for the multi-language integration tests."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RUST_DIR = REPO_ROOT / "rust"


def _unavailable(reason: str) -> NoReturn:
    """Skip locally; fail under CI, where a skipped cross-language test would leave the job green."""
    if os.environ.get("CI"):
        pytest.fail(reason, pytrace=False)
    pytest.skip(reason)


def _build_release_binary(crate: str) -> Path | str:
    """Run the incremental release build of ``crate``; return its binary, or why there is none.

    The binary is the one cargo reports for this build, so a binary left by an earlier build
    (or in another target directory) is never run in its place.
    """
    if not shutil.which("cargo"):
        return "cargo not on PATH — cannot build the Rust binaries for the integration tests"
    command = ["cargo", "build", "--release", "-p", crate, "--message-format=json-render-diagnostics"]
    result = subprocess.run(command, cwd=RUST_DIR, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        return f"cargo build --release -p {crate} failed (exit {result.returncode}):\n{result.stderr[-2000:]}"
    for line in result.stdout.splitlines():
        message = json.loads(line) if line.startswith("{") else {}
        if (
            message.get("reason") == "compiler-artifact"
            and message["target"]["name"] == crate
            and message.get("executable")
        ):
            return Path(message["executable"])
    return f"cargo build --release -p {crate} succeeded but reported no {crate} executable"


@pytest.fixture(scope="session")
def cargo_build_release() -> Callable[[str], Path]:
    """Return a callable ``build(crate_name) -> Path`` that runs the
    release build of the given crate and returns the resulting binary.

    The build runs once per session per crate, even when a binary
    already exists (cargo is incremental, so an up-to-date crate costs
    seconds); later calls reuse that outcome. When cargo is missing or
    the build fails, the calling test is skipped, or fails under CI."""
    outcomes: dict[str, Path | str] = {}

    def build(crate: str) -> Path:
        if crate not in outcomes:
            outcomes[crate] = _build_release_binary(crate)
        outcome = outcomes[crate]
        if isinstance(outcome, str):
            _unavailable(outcome)
        return outcome

    return build


@pytest.fixture
def free_port() -> int:
    """Allocate a free TCP port for binding a Rust binary."""
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def wait_for_grpc_ready(target: str, *, timeout_s: float = 15.0) -> None:
    """Block synchronously until a gRPC channel to ``target`` is
    ready. Uses the sync grpc package so this helper can be invoked
    from either sync or async contexts (the async test functions
    spawn the binary inside a fixture that already runs in an
    event loop)."""
    import time

    import grpc

    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        channel = grpc.insecure_channel(target)
        try:
            future = grpc.channel_ready_future(channel)
            future.result(timeout=2.0)
            channel.close()
            return
        except Exception as exc:
            last_error = exc
            channel.close()
            time.sleep(0.2)
    raise RuntimeError(f"gRPC target {target} never became ready") from last_error


@pytest.fixture
def spawn_rust_binary(cargo_build_release):
    """Yield a callable ``spawn(crate, env) -> Popen`` that launches
    a Rust binary with the given env vars and waits for the gRPC
    server to be ready. The process is killed at fixture teardown."""
    procs: list[subprocess.Popen] = []

    def spawn(crate: str, *, env: dict[str, str], grpc_target: str) -> subprocess.Popen:
        binary = cargo_build_release(crate)
        full_env = {**os.environ, **env}
        proc = subprocess.Popen(  # noqa: S603 — local test helper
            [str(binary)],
            env=full_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        procs.append(proc)
        wait_for_grpc_ready(grpc_target)
        return proc

    yield spawn

    for proc in procs:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
