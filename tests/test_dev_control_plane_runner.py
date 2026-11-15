"""The dev stack's hot-reload runner, ``scripts/dev/run_control_plane_dev.py`` (docker-compose.dev.yml)."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "dev" / "run_control_plane_dev.py"


def _load_runner() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("koda_dev_control_plane_runner", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _NoSubprocess:
    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"the dev runner must not spawn a process here (subprocess.{name})")


def test_missing_watchfiles_stops_the_runner_instead_of_installing_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """watchfiles comes from uv.lock's dev group; the runner never fetches an unpinned, unhashed copy."""
    runner = _load_runner()
    monkeypatch.setattr(runner, "subprocess", _NoSubprocess())
    monkeypatch.setitem(sys.modules, "watchfiles", None)  # `import watchfiles` raises ImportError

    with pytest.raises(SystemExit) as excinfo:
        runner.ensure_watchfiles()

    message = str(excinfo.value.code)
    assert "pnpm dev:stack:build" in message
    assert "uv sync" in message


def test_installed_watchfiles_lets_the_runner_start(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _load_runner()
    monkeypatch.setattr(runner, "subprocess", _NoSubprocess())
    monkeypatch.setitem(sys.modules, "watchfiles", types.ModuleType("watchfiles"))

    runner.ensure_watchfiles()
