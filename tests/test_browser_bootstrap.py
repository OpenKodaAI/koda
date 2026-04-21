"""Tests for the idempotent Playwright browser provisioning.

The bootstrap runs at supervisor startup so the runtime's browser tools are
always ready — no operator action required. These tests pin the key
properties:

* ``ensure_browser_installed`` is a no-op when the binary is already there.
* When the binary is missing, it invokes ``playwright install`` with the
  correct ``PLAYWRIGHT_BROWSERS_PATH`` and doesn't crash on subprocess
  failure (browser is optional; LLM / memory / knowledge must still boot).
* The check respects the explicit ``PLAYWRIGHT_BROWSERS_PATH`` env.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def browsers_root(tmp_path: Path) -> Path:
    return tmp_path / "pw"


def test_chromium_present_detects_installed_binary(browsers_root: Path) -> None:
    from koda.services import browser_bootstrap

    install_dir = browsers_root / "chromium-1208" / "chrome-linux"
    install_dir.mkdir(parents=True)
    (install_dir / "chrome").write_text("fake binary")

    assert browser_bootstrap._chromium_present(browsers_root) is True


def test_chromium_present_returns_false_when_missing(browsers_root: Path) -> None:
    from koda.services import browser_bootstrap

    browsers_root.mkdir()
    assert browser_bootstrap._chromium_present(browsers_root) is False


def test_ensure_browser_installed_skips_when_present(browsers_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from koda.services import browser_bootstrap

    install_dir = browsers_root / "chromium-1208" / "chrome-linux"
    install_dir.mkdir(parents=True)
    (install_dir / "chrome").write_text("fake binary")

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(browsers_root))
    with patch.object(browser_bootstrap.subprocess, "run") as run_mock:
        browser_bootstrap.ensure_browser_installed()
    assert run_mock.call_count == 0


def test_ensure_browser_installed_invokes_playwright_when_missing(
    browsers_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from koda.services import browser_bootstrap

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(browsers_root))

    def _fake_run(args, **kwargs):  # type: ignore[no-untyped-def]
        # Simulate a successful install by creating the expected layout.
        install_dir = browsers_root / "chromium-1208" / "chrome-linux"
        install_dir.mkdir(parents=True)
        (install_dir / "chrome").write_text("fake binary")

        class _Completed:
            returncode = 0

        return _Completed()

    with patch.object(browser_bootstrap.subprocess, "run", side_effect=_fake_run) as run_mock:
        browser_bootstrap.ensure_browser_installed()

    assert run_mock.call_count == 1
    called_args, called_kwargs = run_mock.call_args
    cmd = called_args[0]
    assert "-m" in cmd and "playwright" in cmd and "install" in cmd and "chromium" in cmd
    assert called_kwargs["env"]["PLAYWRIGHT_BROWSERS_PATH"] == str(browsers_root)


def test_ensure_browser_installed_swallows_subprocess_failure(
    browsers_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed install must not abort the supervisor — browser is optional."""
    import subprocess

    from koda.services import browser_bootstrap

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(browsers_root))

    def _raise_called_process_error(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise subprocess.CalledProcessError(returncode=1, cmd=["playwright", "install"])

    with patch.object(browser_bootstrap.subprocess, "run", side_effect=_raise_called_process_error):
        # Must not raise.
        browser_bootstrap.ensure_browser_installed()


def test_ensure_browser_installed_handles_missing_playwright_cli(
    browsers_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from koda.services import browser_bootstrap

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(browsers_root))

    with patch.object(browser_bootstrap.subprocess, "run", side_effect=FileNotFoundError()):
        browser_bootstrap.ensure_browser_installed()


def test_ensure_browser_installed_respects_env_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from koda.services import browser_bootstrap

    custom_path = tmp_path / "custom-browsers"
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(custom_path))

    calls: list[Path] = []

    def _fake_run(args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(Path(kwargs["env"]["PLAYWRIGHT_BROWSERS_PATH"]))

        class _Completed:
            returncode = 0

        # Simulate install into the custom path to mark success.
        install_dir = custom_path / "chromium-1208" / "chrome-linux"
        install_dir.mkdir(parents=True)
        (install_dir / "chrome").write_text("fake binary")
        return _Completed()

    with patch.object(browser_bootstrap.subprocess, "run", side_effect=_fake_run):
        browser_bootstrap.ensure_browser_installed()

    assert calls == [custom_path]
