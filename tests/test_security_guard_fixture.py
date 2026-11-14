"""The suite's security guard is owned by the session unless sharing is explicit."""

from __future__ import annotations

import os
import select
import shutil
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from koda import config
from tests import _security_guard, conftest
from tests._security_guard import SHARED_TARGET_ENV


def test_own_target_ignores_ambient_target() -> None:
    environ = {"SECURITY_GRPC_TARGET": "127.0.0.1:50065"}

    selected = _security_guard.select_guard_target(environ)

    assert not selected.shared
    assert selected.target.startswith("unix://")
    assert selected.target.endswith("/guard.sock")
    assert Path(selected.target.removeprefix("unix://")).parent.is_dir()
    assert environ["SECURITY_GRPC_TARGET"] == selected.target


def test_own_targets_are_private_per_session() -> None:
    first = _security_guard.own_target()
    second = _security_guard.own_target()

    assert first != second
    socket_dir = Path(first.removeprefix("unix://")).parent
    assert socket_dir.stat().st_mode & 0o077 == 0, "socket directory must not be accessible to other users"
    assert len(first.removeprefix("unix://")) < 100, "socket path must fit sun_path"


def test_shared_target_is_explicit_opt_in() -> None:
    environ = {SHARED_TARGET_ENV: " 127.0.0.1:50300 ", "SECURITY_GRPC_TARGET": "127.0.0.1:50065"}

    selected = _security_guard.select_guard_target(environ)

    assert selected == _security_guard.GuardTarget("127.0.0.1:50300", shared=True)
    assert environ["SECURITY_GRPC_TARGET"] == "127.0.0.1:50300"


def test_skip_flag_disables_guard() -> None:
    assert _security_guard.guard_disabled({"KODA_SKIP_SECURITY_GUARD_SERVICE": "1"})
    assert not _security_guard.guard_disabled({})


@pytest.mark.skipif(conftest._GUARD is None, reason="guard disabled for this session")
def test_session_targets_the_guard_selected_by_conftest() -> None:
    assert conftest._GUARD is not None
    assert conftest._GUARD.target == config.SECURITY_GRPC_TARGET
    assert os.environ["SECURITY_GRPC_TARGET"] == conftest._GUARD.target
    _security_guard.wait_until_ready(config.SECURITY_GRPC_TARGET, timeout=5)


def test_wait_fails_fast_when_process_exits() -> None:
    proc = subprocess.Popen([sys.executable, "-c", "raise SystemExit(3)"], text=True)
    proc.wait(timeout=10)

    with pytest.raises(_security_guard.GuardUnavailable, match="exited with code 3"):
        _security_guard.wait_until_ready(_security_guard.own_target(), timeout=30, proc=proc)


def test_missing_cargo_is_reported_as_such(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(_security_guard.shutil, "which", lambda name: None)

    with pytest.raises(_security_guard.CargoMissing), _security_guard.run_own_guard(tmp_path, "unix:///x", 1):
        pass


def test_guard_process_is_stopped_when_startup_is_interrupted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    started: list[subprocess.Popen[str]] = []
    real_spawn = _security_guard.spawn_owned

    def spawn(*args, **kwargs):
        proc = real_spawn(*args, **kwargs)
        started.append(proc)
        return proc

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    sleeper = [sys.executable, "-c", "import time; time.sleep(60)"]
    monkeypatch.setattr(_security_guard, "guard_command", lambda root: sleeper)
    monkeypatch.setattr(_security_guard, "spawn_owned", spawn)
    monkeypatch.setattr(_security_guard, "wait_until_ready", interrupt)

    with pytest.raises(KeyboardInterrupt), _security_guard.run_own_guard(tmp_path, "unix:///x", 1):
        pass

    assert started and started[0].poll() is not None
    # The watchdog dies by SIGTERM only after the guard did: stopped and reaped, not left behind.
    assert started[0].returncode == -signal.SIGTERM


# A stand-in for the Rust guard: a gRPC server on SECURITY_GRPC_TARGET, so the real
# readiness wait applies. It exits once argv[1] exists or after argv[2] seconds, so a
# guard that outlives its session (the defect under test) still cleans itself up.
_FAKE_GUARD = r"""
import os, sys, time
from concurrent import futures

import grpc

server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))
server.add_insecure_port(os.environ["SECURITY_GRPC_TARGET"])
server.start()
print("fake guard listening", flush=True)
deadline = time.monotonic() + float(sys.argv[2])
while not os.path.exists(sys.argv[1]) and time.monotonic() < deadline:
    time.sleep(0.1)
server.stop(0)
"""

# A minimal pytest session: starts its guard the way conftest does, reports the guard's
# address once the readiness wait has passed, then waits to be killed before teardown.
_SESSION = r"""
import sys, time
from pathlib import Path

from tests import _security_guard

_security_guard.guard_command = lambda root: sys.argv[1:]
target = _security_guard.own_target()
with _security_guard.run_own_guard(Path.cwd(), target, timeout=60):
    print(target, flush=True)
    time.sleep(120)
"""


def _fake_guard(stop_file: Path) -> list[str]:
    return [sys.executable, "-c", _FAKE_GUARD, str(stop_file), "120"]


def _answers(target: str) -> bool:
    """Whether a process still listens on the guard's socket (a dead guard's socket refuses)."""
    with socket.socket(socket.AF_UNIX) as probe:
        try:
            probe.connect(target.removeprefix("unix://"))
        except (ConnectionRefusedError, FileNotFoundError):
            return False
    return True


@pytest.mark.parametrize(
    ("kill", "signum"),
    [
        pytest.param(os.kill, signal.SIGKILL, id="SIGKILL"),
        pytest.param(os.kill, signal.SIGTERM, id="SIGTERM"),
        pytest.param(os.killpg, signal.SIGKILL, id="SIGKILL-to-process-group"),
    ],
)
def test_guard_does_not_outlive_a_killed_session(
    tmp_path: Path, kill: Callable[[int, int], None], signum: signal.Signals
) -> None:
    """D-254: a session killed before its teardown runs must not leave its guard running."""
    stop_file = tmp_path / "stop"
    session = subprocess.Popen(
        [sys.executable, "-c", _SESSION, *_fake_guard(stop_file)],
        cwd=conftest.ROOT_DIR,
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,  # its own process group, so killpg reaches the session and nothing else
    )
    target = ""
    try:
        assert session.stdout is not None
        ready, _, _ = select.select([session.stdout], [], [], 90)
        target = session.stdout.readline().strip() if ready else ""
        assert target.startswith("unix://"), f"the session did not start its guard (exit {session.poll()})"
        assert _answers(target)

        kill(session.pid, signum)
        session.wait(timeout=10)

        deadline = time.monotonic() + 10
        while _answers(target):
            assert time.monotonic() < deadline, "the guard was still running 10s after its session was killed"
            time.sleep(0.1)
    finally:
        stop_file.touch()
        if session.poll() is None:
            session.kill()
            session.wait(timeout=10)
        if target:
            shutil.rmtree(Path(target.removeprefix("unix://")).parent, ignore_errors=True)


def test_guard_answers_until_teardown_and_stops_with_it(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(_security_guard, "guard_command", lambda root: _fake_guard(tmp_path / "stop"))
    target = _security_guard.own_target()

    with _security_guard.run_own_guard(conftest.ROOT_DIR, target, timeout=60):
        assert _answers(target)

    assert not _answers(target)


def test_readiness_wait_reports_a_guard_that_exits_with_its_code_and_log(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    exits = [sys.executable, "-c", "print('guard config rejected', flush=True); raise SystemExit(3)"]
    monkeypatch.setattr(_security_guard, "guard_command", lambda root: exits)

    with (
        pytest.raises(_security_guard.GuardUnavailable, match=r"exited with code 3[\s\S]*guard config rejected"),
        _security_guard.run_own_guard(tmp_path, _security_guard.own_target(), timeout=60),
    ):
        pass
