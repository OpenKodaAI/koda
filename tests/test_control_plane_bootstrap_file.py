"""Tests for the first-boot bootstrap-file workflow."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

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
    content = isolated_bootstrap.read_text(encoding="utf-8")
    assert content.splitlines()[0] == code
    assert "expires_at=" in content
    assert "setup_url=/setup" in content


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
    assert isolated_bootstrap.read_text(encoding="utf-8").splitlines()[0] == "CUST-OMSE-EDCD"


def _weak_seed_warnings(log: MagicMock) -> list[Any]:
    return [call for call in log.warning.call_args_list if call.args == ("bootstrap_code_seed_weak",)]


@pytest.mark.parametrize(
    ("seed", "significant"),
    [("!@#$%^&*()_+1", 1), ("!!!!a!!!!", 1), ("Tr0ub4dor&3!", 10), ("ÄÖÜ-ÄÖÜ", 0)],
)
def test_ensure_warns_about_a_seed_with_few_ascii_letters_or_digits(
    isolated_bootstrap: Path, monkeypatch: pytest.MonkeyPatch, seed: str, significant: int
) -> None:
    """Setup codes match on ASCII letters and digits only, so a symbol-heavy seed is a short secret."""
    monkeypatch.setattr(bootstrap_file_mod, "CONTROL_PLANE_BOOTSTRAP_CODE_SEED", seed)
    log = MagicMock()
    monkeypatch.setattr(bootstrap_file_mod, "log", log)

    assert bootstrap_file_mod.ensure_bootstrap_file(has_owner=False) == seed
    assert isolated_bootstrap.read_text(encoding="utf-8").splitlines()[0] == seed
    # The file already exists now, so a later call writes nothing and warns no more.
    assert bootstrap_file_mod.ensure_bootstrap_file(has_owner=False) is None

    warnings = _weak_seed_warnings(log)
    assert len(warnings) == 1
    kwargs = warnings[0].kwargs
    assert kwargs["significant_characters"] == significant
    assert kwargs["minimum"] == 12
    assert seed not in repr(warnings[0])


@pytest.mark.parametrize("seed", ["", "CUST-OMSE-EDCD", "cust omse edcd", "Tr0ub4dor&3!xy"])
def test_ensure_does_not_warn_about_a_generated_code_or_a_full_seed(
    isolated_bootstrap: Path, monkeypatch: pytest.MonkeyPatch, seed: str
) -> None:
    monkeypatch.setattr(bootstrap_file_mod, "CONTROL_PLANE_BOOTSTRAP_CODE_SEED", seed)
    log = MagicMock()
    monkeypatch.setattr(bootstrap_file_mod, "log", log)

    assert bootstrap_file_mod.ensure_bootstrap_file(has_owner=False)
    assert _weak_seed_warnings(log) == []


def test_ensure_does_not_overwrite_existing(isolated_bootstrap: Path) -> None:
    isolated_bootstrap.parent.mkdir(parents=True, exist_ok=True)
    isolated_bootstrap.write_text("EXISTING-CODE-HERE\n", encoding="utf-8")
    code = bootstrap_file_mod.ensure_bootstrap_file(has_owner=False)
    assert code is None
    assert isolated_bootstrap.read_text(encoding="utf-8").strip() == "EXISTING-CODE-HERE"


def test_read_bootstrap_file_returns_content(isolated_bootstrap: Path) -> None:
    code = bootstrap_file_mod.ensure_bootstrap_file(has_owner=False)
    assert bootstrap_file_mod.read_bootstrap_file() == code


def test_read_bootstrap_file_rejects_expired_content(isolated_bootstrap: Path) -> None:
    isolated_bootstrap.parent.mkdir(parents=True, exist_ok=True)
    isolated_bootstrap.write_text(
        "EXPI-REDC-ODEX\nexpires_at=2000-01-01T00:00:00+00:00\nsetup_url=/setup\n",
        encoding="utf-8",
    )
    assert bootstrap_file_mod.read_bootstrap_file() is None


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
