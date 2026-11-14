"""The suite's security guard is owned by the session unless sharing is explicit."""

from __future__ import annotations

import os
import subprocess
import sys
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
    real_popen = subprocess.Popen

    def popen(*args, **kwargs):
        proc = real_popen([sys.executable, "-c", "import time; time.sleep(60)"], text=True)
        started.append(proc)
        return proc

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(_security_guard, "guard_command", lambda root: ["unused"])
    monkeypatch.setattr(_security_guard.subprocess, "Popen", popen)
    monkeypatch.setattr(_security_guard, "wait_until_ready", interrupt)

    with pytest.raises(KeyboardInterrupt), _security_guard.run_own_guard(tmp_path, "unix:///x", 1):
        pass

    assert started and started[0].poll() is not None
