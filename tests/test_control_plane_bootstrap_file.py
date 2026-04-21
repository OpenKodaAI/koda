"""Tests for the first-boot bootstrap-file workflow."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from koda.control_plane import bootstrap_file as bootstrap_file_mod


@pytest.fixture()
def isolated_bootstrap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the bootstrap-file path into a per-test directory."""
    file_path = tmp_path / "control_plane" / "bootstrap.txt"
    monkeypatch.setattr(bootstrap_file_mod, "_BOOTSTRAP_FILE_PATH", file_path)
    monkeypatch.setattr(bootstrap_file_mod, "CONTROL_PLANE_BOOTSTRAP_CODE_SEED", "")
    return file_path


def test_ensure_writes_file_with_restricted_perms(isolated_bootstrap: Path) -> None:
    code = bootstrap_file_mod.ensure_bootstrap_file(has_owner=False)
    assert code is not None
    assert isolated_bootstrap.exists()
    mode = os.stat(isolated_bootstrap).st_mode & 0o777
    assert mode == 0o600
    assert isolated_bootstrap.read_text(encoding="utf-8").strip() == code


def test_ensure_is_noop_when_owner_exists(isolated_bootstrap: Path) -> None:
    # Pre-create the file to ensure ensure() cleans it up when has_owner=True.
    isolated_bootstrap.parent.mkdir(parents=True, exist_ok=True)
    isolated_bootstrap.write_text("OLD-CODE\n", encoding="utf-8")
    bootstrap_file_mod.ensure_bootstrap_file(has_owner=True)
    assert not isolated_bootstrap.exists()


def test_ensure_respects_env_seed(isolated_bootstrap: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bootstrap_file_mod, "CONTROL_PLANE_BOOTSTRAP_CODE_SEED", "CUST-OMSE-EDCD")
    code = bootstrap_file_mod.ensure_bootstrap_file(has_owner=False)
    assert code == "CUST-OMSE-EDCD"
    assert isolated_bootstrap.read_text(encoding="utf-8").strip() == "CUST-OMSE-EDCD"


def test_ensure_does_not_overwrite_existing(isolated_bootstrap: Path) -> None:
    isolated_bootstrap.parent.mkdir(parents=True, exist_ok=True)
    isolated_bootstrap.write_text("EXISTING-CODE-HERE\n", encoding="utf-8")
    code = bootstrap_file_mod.ensure_bootstrap_file(has_owner=False)
    assert code is None
    assert isolated_bootstrap.read_text(encoding="utf-8").strip() == "EXISTING-CODE-HERE"


def test_read_bootstrap_file_returns_content(isolated_bootstrap: Path) -> None:
    bootstrap_file_mod.ensure_bootstrap_file(has_owner=False)
    assert bootstrap_file_mod.read_bootstrap_file() is not None


def test_consume_removes_file(isolated_bootstrap: Path) -> None:
    bootstrap_file_mod.ensure_bootstrap_file(has_owner=False)
    assert isolated_bootstrap.exists()
    bootstrap_file_mod.consume_bootstrap_file()
    assert not isolated_bootstrap.exists()


def test_is_loopback_request_rejects_forwarded() -> None:
    assert bootstrap_file_mod.is_loopback_request("127.0.0.1", None) is True
    assert bootstrap_file_mod.is_loopback_request("::1", None) is True
    assert bootstrap_file_mod.is_loopback_request("127.0.0.1", "203.0.113.10") is False
    assert bootstrap_file_mod.is_loopback_request("10.0.0.5", None) is False
    assert bootstrap_file_mod.is_loopback_request(None, None) is False
