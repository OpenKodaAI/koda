"""``cargo_build_release`` always rebuilds and never lets a broken build pass silently in CI (D-174).

These tests drive the real session fixture with a fake ``cargo`` first on ``PATH`` and a fake
``RUST_DIR``. Each test builds a crate name of its own, so the session's build cache never
holds an outcome for a real crate.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.integration import conftest as integration_conftest

Build = Callable[[str], Path]
InstallCargo = Callable[[str], None]

COMPILE_ERROR = "error[E0425]: cannot find value `gateway` in this scope"
FAIL_BUILD = f"echo '{COMPILE_ERROR}' >&2\nexit 101"


@pytest.fixture
def crate() -> str:
    return f"koda-fixture-test-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def rust_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    rust_dir = tmp_path / "rust"
    (rust_dir / "target" / "release").mkdir(parents=True)
    monkeypatch.setattr(integration_conftest, "RUST_DIR", rust_dir)
    return rust_dir


@pytest.fixture
def cargo_log(tmp_path: Path) -> Path:
    return tmp_path / "cargo-invocations.log"


@pytest.fixture
def fake_cargo(tmp_path: Path, cargo_log: Path, monkeypatch: pytest.MonkeyPatch) -> InstallCargo:
    """Return ``install(script)``: put a ``cargo`` that logs its call and runs ``script`` first on PATH."""

    def install(script: str) -> None:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        cargo = bin_dir / "cargo"
        cargo.write_text(f'#!/bin/sh\necho "$PWD $*" >> "{cargo_log}"\n{script}\n', encoding="utf-8")
        cargo.chmod(0o755)
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    return install


def _set_ci(monkeypatch: pytest.MonkeyPatch, ci: str | None) -> None:
    if ci is None:
        monkeypatch.delenv("CI", raising=False)
    else:
        monkeypatch.setenv("CI", ci)


def _stale_binary(rust_dir: Path, crate: str) -> Path:
    binary = rust_dir / "target" / "release" / crate
    binary.write_text("stale", encoding="utf-8")
    return binary


def _report_artifact(crate: str, executable: Path, *, write: str | None = None) -> str:
    """Shell that optionally writes ``executable`` and prints cargo's JSON artifact messages for ``crate``."""
    messages = [
        {
            "reason": "compiler-artifact",
            "target": {"name": crate.replace("-", "_"), "kind": ["lib"]},
            "executable": None,
        },
        {"reason": "compiler-artifact", "target": {"name": crate, "kind": ["bin"]}, "executable": str(executable)},
        {"reason": "build-finished", "success": True},
    ]
    lines = [f"printf '%s\\n' '{json.dumps(message)}'" for message in messages]
    if write is not None:
        lines.insert(0, f"echo {write} > '{executable}'")
    return "\n".join(lines)


def _outcome(build: Build, crate: str) -> Path | BaseException:
    try:
        return build(crate)
    except (pytest.fail.Exception, pytest.skip.Exception) as exc:
        return exc


def _calls(cargo_log: Path) -> list[str]:
    return cargo_log.read_text(encoding="utf-8").splitlines() if cargo_log.exists() else []


def test_failed_build_fails_the_test_under_ci(
    cargo_build_release: Build, rust_dir: Path, fake_cargo: InstallCargo, crate: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_ci(monkeypatch, "1")
    fake_cargo(FAIL_BUILD)

    outcome = _outcome(cargo_build_release, crate)

    assert isinstance(outcome, pytest.fail.Exception), f"a failed build must turn CI red, got {outcome!r}"
    assert f"cargo build --release -p {crate} failed" in str(outcome)
    assert COMPILE_ERROR in str(outcome)


def test_failed_build_skips_without_ci(
    cargo_build_release: Build, rust_dir: Path, fake_cargo: InstallCargo, crate: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_ci(monkeypatch, None)
    fake_cargo(FAIL_BUILD)

    outcome = _outcome(cargo_build_release, crate)

    assert isinstance(outcome, pytest.skip.Exception), f"local runs keep skipping, got {outcome!r}"
    assert COMPILE_ERROR in str(outcome)


@pytest.mark.parametrize("ci", ["1", None], ids=["ci", "local"])
def test_existing_binary_is_rebuilt_before_use(
    cargo_build_release: Build,
    rust_dir: Path,
    fake_cargo: InstallCargo,
    cargo_log: Path,
    crate: str,
    ci: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_ci(monkeypatch, ci)
    binary = _stale_binary(rust_dir, crate)
    fake_cargo(_report_artifact(crate, binary, write="fresh"))

    built = cargo_build_release(crate)

    assert built == binary
    assert built.read_text(encoding="utf-8").strip() == "fresh", "the stale binary was run without a rebuild"
    [call] = _calls(cargo_log)
    assert call.startswith(f"{rust_dir} build --release -p {crate}")


@pytest.mark.parametrize(
    ("ci", "expected"),
    [("1", pytest.fail.Exception), (None, pytest.skip.Exception)],
    ids=["ci", "local"],
)
def test_stale_binary_is_not_used_when_the_build_fails(
    cargo_build_release: Build,
    rust_dir: Path,
    fake_cargo: InstallCargo,
    crate: str,
    ci: str | None,
    expected: type[BaseException],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_ci(monkeypatch, ci)
    _stale_binary(rust_dir, crate)
    fake_cargo(FAIL_BUILD)

    outcome = _outcome(cargo_build_release, crate)

    assert isinstance(outcome, expected), f"expected {expected.__name__}, got {outcome!r}"


def test_binary_comes_from_the_build_not_from_a_guessed_path(
    cargo_build_release: Build, rust_dir: Path, fake_cargo: InstallCargo, crate: str, tmp_path: Path
) -> None:
    """With CARGO_TARGET_DIR (or a target-dir config) the fresh binary is not under rust/target."""
    _stale_binary(rust_dir, crate)
    elsewhere = tmp_path / "shared-target" / "release" / crate
    elsewhere.parent.mkdir(parents=True)
    fake_cargo(_report_artifact(crate, elsewhere, write="fresh"))

    assert cargo_build_release(crate) == elsewhere


def test_cargo_target_dir_reaches_the_build(
    cargo_build_release: Build,
    rust_dir: Path,
    fake_cargo: InstallCargo,
    crate: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CONTRIBUTING.md says a CARGO_TARGET_DIR in the environment is honoured."""
    _set_ci(monkeypatch, "1")
    target_dir = tmp_path / "shared-target"
    (target_dir / "release").mkdir(parents=True)
    monkeypatch.setenv("CARGO_TARGET_DIR", str(target_dir))
    binary = target_dir / "release" / crate
    fake_cargo(f'[ "$CARGO_TARGET_DIR" = "{target_dir}" ] || exit 3\n' + _report_artifact(crate, binary, write="fresh"))

    assert cargo_build_release(crate) == binary


def test_successful_build_without_the_binary_fails_under_ci(
    cargo_build_release: Build, rust_dir: Path, fake_cargo: InstallCargo, crate: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_ci(monkeypatch, "1")
    fake_cargo("exit 0")

    outcome = _outcome(cargo_build_release, crate)

    assert isinstance(outcome, pytest.fail.Exception), f"got {outcome!r}"
    assert f"no {crate} executable" in str(outcome)


@pytest.mark.parametrize("ci", ["1", None], ids=["ci", "local"])
def test_missing_cargo_fails_under_ci_and_skips_locally(
    cargo_build_release: Build,
    rust_dir: Path,
    crate: str,
    ci: str | None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_ci(monkeypatch, ci)
    empty = tmp_path / "empty-path"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))

    outcome = _outcome(cargo_build_release, crate)

    expected = pytest.skip.Exception if ci is None else pytest.fail.Exception
    assert isinstance(outcome, expected), f"expected {expected.__name__}, got {outcome!r}"
    assert "cargo not on PATH" in str(outcome)


def test_each_crate_is_built_once_per_session(
    cargo_build_release: Build,
    rust_dir: Path,
    fake_cargo: InstallCargo,
    cargo_log: Path,
    crate: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_ci(monkeypatch, None)
    binary = rust_dir / "target" / "release" / crate
    fake_cargo(_report_artifact(crate, binary, write="fresh"))

    assert cargo_build_release(crate) == cargo_build_release(crate) == binary
    assert len(_calls(cargo_log)) == 1


def test_a_failed_build_is_not_retried_for_every_test(
    cargo_build_release: Build,
    rust_dir: Path,
    fake_cargo: InstallCargo,
    cargo_log: Path,
    crate: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_ci(monkeypatch, None)
    fake_cargo(FAIL_BUILD)

    first = _outcome(cargo_build_release, crate)
    second = _outcome(cargo_build_release, crate)

    assert isinstance(first, pytest.skip.Exception)
    assert isinstance(second, pytest.skip.Exception)
    assert str(second) == str(first)
    assert len(_calls(cargo_log)) == 1
