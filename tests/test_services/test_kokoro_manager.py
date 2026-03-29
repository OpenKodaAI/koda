"""Tests for Kokoro asset root defaults."""

from __future__ import annotations

import importlib
import sys


def test_kokoro_assets_default_to_state_root(monkeypatch, tmp_path):
    monkeypatch.delenv("CONTROL_PLANE_RUNTIME_DIR", raising=False)
    monkeypatch.delenv("KOKORO_ASSET_ROOT", raising=False)
    monkeypatch.setenv("STATE_ROOT_DIR", str(tmp_path / "state"))

    sys.modules.pop("koda.services.kokoro_manager", None)
    module = importlib.import_module("koda.services.kokoro_manager")

    assert str(module._KOKORO_ROOT).startswith(str((tmp_path / "state").expanduser()))
