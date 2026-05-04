"""Shared fixtures for the multi-language integration tests."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RUST_DIR = REPO_ROOT / "rust"


def _cargo_available() -> bool:
    return bool(shutil.which("cargo"))


@pytest.fixture(scope="session")
def cargo_build_release(request: pytest.FixtureRequest):
    """Return a callable ``build(crate_name) -> Path`` that compiles
    the given crate in release mode and yields the resulting binary
    path. Compilation happens once per session per crate; subsequent
    calls reuse the cached binary."""
    if not _cargo_available():
        pytest.skip("cargo not on PATH — skipping Rust binary integration tests")

    cache: dict[str, Path] = {}

    def build(crate: str) -> Path:
        if crate in cache:
            return cache[crate]
        binary = RUST_DIR / "target" / "release" / crate
        if not binary.exists():
            result = subprocess.run(
                ["cargo", "build", "--release", "-p", crate],
                cwd=RUST_DIR,
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.returncode != 0:
                pytest.skip(
                    f"cargo build -p {crate} failed (this is OK on a host without "
                    f"Rust deps; full build is exercised in CI):\n{result.stderr[:1000]}"
                )
        if not binary.exists():
            pytest.skip(f"cargo build succeeded but binary {binary} missing — proto codegen issue?")
        cache[crate] = binary
        return binary

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
