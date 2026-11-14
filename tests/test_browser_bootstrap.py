"""Tests for the idempotent Playwright browser provisioning.

The bootstrap runs at supervisor startup so the runtime's browser tools are
always ready — no operator action required. These tests pin the key
properties:

* Presence is decided by the executable the pinned Playwright itself launches
  for ``chromium.launch(headless=True)``, on every host layout its registry
  knows, so a boot with that executable installed starts no install (D-231).
* A build Playwright would not launch (another revision, or the full browser
  without the headless shell) counts as missing.
* A build Playwright's installer has not marked complete (an interrupted
  extract), or one whose executable is gone, counts as missing, so the
  installer runs and repairs it.
* When the binary is missing, it invokes ``playwright install`` with the
  correct ``PLAYWRIGHT_BROWSERS_PATH`` and doesn't crash on subprocess
  failure (browser is optional; LLM / memory / knowledge must still boot).
* When the driver cannot be asked, the bootstrap defers to Playwright's own
  installer, which skips builds that are already complete.
* The check respects the explicit ``PLAYWRIGHT_BROWSERS_PATH`` env.

The lookups run the real pinned Playwright driver; only the installer
subprocess is faked, except where the real pinned installer is run against a
closed download host to cross-check which builds it counts as installed.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# Executable layouts of the pinned Playwright's registry (EXECUTABLE_PATHS in
# playwright-core's ``lib/server/registry/index.js``), keyed by its short host
# platform: (host platform override, chromium executable, headless shell
# executable), each relative to its browser directory.
_LAYOUTS = {
    "linux-x64": (
        "ubuntu24.04-x64",
        "chrome-linux64/chrome",
        "chrome-headless-shell-linux64/chrome-headless-shell",
    ),
    "linux-arm64": (
        "ubuntu24.04-arm64",
        "chrome-linux/chrome",
        "chrome-linux/headless_shell",
    ),
    "mac-x64": (
        "mac15",
        "chrome-mac-x64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
        "chrome-headless-shell-mac-x64/chrome-headless-shell",
    ),
    "mac-arm64": (
        "mac15-arm64",
        "chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
        "chrome-headless-shell-mac-arm64/chrome-headless-shell",
    ),
    "win-x64": (
        "win64",
        "chrome-win64/chrome.exe",
        "chrome-headless-shell-win64/chrome-headless-shell.exe",
    ),
}
_INSTALL_COMMAND_TAIL = ["-m", "playwright", "install", "chromium"]
# A revision the pinned Playwright does not use, as left by another version.
_STALE_REVISION = "1208"
# Written by Playwright's installer into a browser directory once the build is
# fully extracted; a build without it is downloaded again.
_INSTALLATION_MARKER = "INSTALLATION_COMPLETE"


def _pinned_revision(name: str) -> str:
    from playwright._impl._driver import compute_driver_executable

    browsers_json = Path(compute_driver_executable()[1]).parent / "browsers.json"
    browsers = json.loads(browsers_json.read_text(encoding="utf-8"))["browsers"]
    return str(next(browser["revision"] for browser in browsers if browser["name"] == name))


def _write_executable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("fake binary")


def _install_build(browser_directory: Path, executable: str, *, complete: bool, with_executable: bool) -> None:
    """Lay out one browser build: files beside its executable, the executable, its marker."""
    executable_path = browser_directory / executable
    executable_path.parent.mkdir(parents=True, exist_ok=True)
    (executable_path.parent / "resources.pak").write_text("fake resources")
    if with_executable:
        _write_executable(executable_path)
    if complete:
        (browser_directory / _INSTALLATION_MARKER).write_text("")


def _install_layout(
    root: Path,
    layout: str,
    *,
    chromium: bool = True,
    headless_shell: bool = True,
    revision: str | None = None,
    complete: bool = True,
    with_executables: bool = True,
) -> None:
    """Lay out a ``playwright install chromium`` result the way the registry names it.

    ``complete=False`` leaves out the installer's completion marker, as an
    extract cut off mid-way does; ``with_executables=False`` leaves out the
    executables but keeps the files beside them.
    """
    _, chromium_executable, shell_executable = _LAYOUTS[layout]
    build = {"complete": complete, "with_executable": with_executables}
    if chromium:
        chromium_revision = revision or _pinned_revision("chromium")
        _install_build(root / f"chromium-{chromium_revision}", chromium_executable, **build)
    if headless_shell:
        shell_revision = revision or _pinned_revision("chromium-headless-shell")
        _install_build(root / f"chromium_headless_shell-{shell_revision}", shell_executable, **build)


def _use_layout(monkeypatch: pytest.MonkeyPatch, layout: str) -> None:
    monkeypatch.setenv("PLAYWRIGHT_HOST_PLATFORM_OVERRIDE", _LAYOUTS[layout][0])


def _fake_node(tmp_path: Path, body: str) -> Path:
    node = tmp_path / "fake-node"
    node.write_text(f"#!/bin/sh\n{body}\n")
    node.chmod(0o755)
    return node


@dataclass
class _FakeInstaller:
    """Stands in for the ``playwright install chromium`` subprocess only."""

    calls: list[tuple[list[str], dict[str, Any]]] = field(default_factory=list)
    effect: Callable[[], None] | None = None
    error: BaseException | None = None


@pytest.fixture
def browsers_root(tmp_path: Path) -> Path:
    return tmp_path / "pw"


@pytest.fixture
def installer(monkeypatch: pytest.MonkeyPatch) -> _FakeInstaller:
    from koda.services import browser_bootstrap

    real_run = subprocess.run
    fake = _FakeInstaller()

    def _run(args, **kwargs):  # type: ignore[no-untyped-def]
        if list(args[1:]) != _INSTALL_COMMAND_TAIL:
            return real_run(args, **kwargs)
        fake.calls.append((list(args), kwargs))
        if fake.error is not None:
            raise fake.error
        if fake.effect is not None:
            fake.effect()
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(browser_bootstrap.subprocess, "run", _run)
    return fake


@pytest.mark.parametrize("layout", sorted(_LAYOUTS))
def test_lookup_matches_the_executable_playwright_launch_resolves(
    layout: str, browsers_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bootstrap asks for exactly the path the pinned ``chromium.launch(headless=True)`` needs."""
    from koda.services import browser_bootstrap

    _use_layout(monkeypatch, layout)
    browsers_root.mkdir()
    launch = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from playwright.sync_api import sync_playwright\n"
                "with sync_playwright() as playwright:\n"
                "    try:\n"
                "        playwright.chromium.launch(headless=True)\n"
                "    except Exception as exc:\n"
                "        print(exc)\n"
            ),
        ],
        env={**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(browsers_root)},
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    missing = re.search(r"Executable doesn't exist at (.+)$", launch.stdout, re.MULTILINE)
    assert missing is not None, launch.stdout + launch.stderr

    executable = browser_bootstrap._launch_executable(browsers_root)
    assert executable is not None
    assert executable.path == Path(missing.group(1))


@pytest.mark.parametrize("layout", sorted(_LAYOUTS))
def test_presence_follows_the_executable_pinned_playwright_launches(
    layout: str, browsers_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each registry layout counts at the pinned revision, and only there."""
    from koda.services import browser_bootstrap

    _use_layout(monkeypatch, layout)
    _install_layout(browsers_root, layout, revision=_STALE_REVISION)
    assert browser_bootstrap._chromium_present(browsers_root) is False

    _install_layout(browsers_root, layout)
    assert browser_bootstrap._chromium_present(browsers_root) is True


@pytest.mark.parametrize("layout", sorted(_LAYOUTS))
def test_build_without_the_installation_marker_is_missing(
    layout: str, browsers_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An extract cut off before Playwright marked it complete is not installed yet.

    Playwright's installer downloads such a build again, so the bootstrap must
    start it instead of trusting the executable left on disk.
    """
    from koda.services import browser_bootstrap

    _use_layout(monkeypatch, layout)
    _install_layout(browsers_root, layout, complete=False)
    assert browser_bootstrap._chromium_present(browsers_root) is False

    _install_layout(browsers_root, layout)
    assert browser_bootstrap._chromium_present(browsers_root) is True


@pytest.mark.parametrize("complete", [True, False], ids=["marked-complete", "extract-interrupted"])
def test_presence_agrees_with_the_pinned_installer(
    complete: bool, browsers_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bootstrap reports missing exactly the headless shell the real pinned installer would download.

    The installer runs against a port that refuses connections, so it can
    download nothing: it keeps a build it counts as installed and discards,
    then tries to download, one it does not.
    """
    from koda.services import browser_bootstrap

    _use_layout(monkeypatch, "linux-x64")
    _install_layout(browsers_root, "linux-x64", chromium=False, complete=complete)
    shell = browsers_root / f"chromium_headless_shell-{_pinned_revision('chromium-headless-shell')}"
    present = browser_bootstrap._chromium_present(browsers_root)

    with socket.socket() as refusing:
        refusing.bind(("127.0.0.1", 0))
        install = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium-headless-shell"],
            env={
                **os.environ,
                "PLAYWRIGHT_BROWSERS_PATH": str(browsers_root),
                "PLAYWRIGHT_DOWNLOAD_HOST": f"http://127.0.0.1:{refusing.getsockname()[1]}",
            },
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    output = install.stdout + install.stderr

    assert present is complete
    assert (shell / _LAYOUTS["linux-x64"][2]).is_file() is present, output
    assert ("Downloading Chrome Headless Shell" in output) is not present, output


@pytest.mark.parametrize("complete", [False, True], ids=["extract-interrupted", "executable-removed"])
def test_build_directory_without_its_executable_is_missing(
    complete: bool, browsers_root: Path, installer: _FakeInstaller, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the executable launch resolves counts, not the build directory around it.

    A partial install keeps the pinned revision's directories and the files
    beside the executables; every browser tool would still fail with
    "Executable doesn't exist", so the bootstrap must start the installer.
    """
    from koda.services import browser_bootstrap

    _use_layout(monkeypatch, "linux-x64")
    _install_layout(browsers_root, "linux-x64", complete=complete, with_executables=False)
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(browsers_root))

    assert browser_bootstrap._chromium_present(browsers_root) is False
    browser_bootstrap.ensure_browser_installed()

    assert len(installer.calls) == 1


def test_ensure_browser_installed_repairs_an_interrupted_extract(
    browsers_root: Path, installer: _FakeInstaller, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A first-boot install cut off mid-extract is repaired on the next boot.

    The headless shell executable is on disk but Playwright never marked the
    build complete, so the bootstrap runs the installer, which downloads it again.
    """
    from koda.services import browser_bootstrap

    _use_layout(monkeypatch, "linux-x64")
    _install_layout(browsers_root, "linux-x64", chromium=False, complete=False)
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(browsers_root))
    installer.effect = lambda: _install_layout(browsers_root, "linux-x64")

    browser_bootstrap.ensure_browser_installed()

    assert len(installer.calls) == 1
    assert browser_bootstrap._chromium_present(browsers_root) is True


def test_headless_shell_alone_is_present(browsers_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``playwright install --only-shell chromium`` is enough for the headless launch."""
    from koda.services import browser_bootstrap

    _use_layout(monkeypatch, "linux-x64")
    _install_layout(browsers_root, "linux-x64", chromium=False)

    assert browser_bootstrap._chromium_present(browsers_root) is True


def test_full_chromium_without_headless_shell_is_missing(browsers_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``--no-shell`` leaves no executable for the headless launch.

    On linux-arm64 both builds use the ``chrome-linux`` directory, so only the
    executable Playwright resolves tells them apart.
    """
    from koda.services import browser_bootstrap

    _use_layout(monkeypatch, "linux-arm64")
    _install_layout(browsers_root, "linux-arm64", headless_shell=False)

    assert browser_bootstrap._chromium_present(browsers_root) is False


def test_chromium_present_returns_false_when_missing(browsers_root: Path) -> None:
    from koda.services import browser_bootstrap

    browsers_root.mkdir()
    assert browser_bootstrap._chromium_present(browsers_root) is False


def test_host_without_a_playwright_build_counts_as_missing(
    browsers_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Whatever is on disk, a host the pinned Playwright has no build for has no browser."""
    from koda.services import browser_bootstrap

    _install_layout(browsers_root, "linux-arm64")
    monkeypatch.setenv("PLAYWRIGHT_HOST_PLATFORM_OVERRIDE", "<unknown>")

    assert browser_bootstrap._launch_executable(browsers_root) is None
    assert browser_bootstrap._chromium_present(browsers_root) is False


# Driver answers the bootstrap cannot use, as a fake driver Node's shell body.
_UNUSABLE_DRIVER_NODES = {
    "driver-fails": "exit 3",
    "output-not-json": "echo 'not json'",
    "output-not-an-object": "echo '[]'",
    "output-wrong-shape": "echo '{\"executablePath\": 3}'",
    "output-without-marker": 'echo \'{"executablePath": "/pw/chrome-headless-shell"}\'',
    "driver-hangs": "exec sleep 30",
}


@pytest.mark.parametrize("breakage", ["driver-module-missing", "node-missing", *_UNUSABLE_DRIVER_NODES])
def test_chromium_present_is_unknown_when_the_lookup_is_unavailable(
    breakage: str, browsers_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from koda.services import browser_bootstrap

    _use_layout(monkeypatch, "linux-x64")
    _install_layout(browsers_root, "linux-x64")
    if breakage == "driver-module-missing":
        # A Playwright release within the pinned range that renames the private driver module.
        monkeypatch.setitem(sys.modules, "playwright._impl._driver", None)
    elif breakage == "node-missing":
        monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", str(tmp_path / "no-such-node"))
    else:
        monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", str(_fake_node(tmp_path, _UNUSABLE_DRIVER_NODES[breakage])))
    if breakage == "driver-hangs":
        monkeypatch.setattr(browser_bootstrap, "_LOOKUP_TIMEOUT_SECONDS", 0.5)

    assert browser_bootstrap._chromium_present(browsers_root) is None


@pytest.mark.parametrize("layout", sorted(_LAYOUTS))
def test_ensure_browser_installed_skips_when_present(
    layout: str, browsers_root: Path, installer: _FakeInstaller, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A boot with the browser Playwright launches already installed starts no install."""
    from koda.services import browser_bootstrap

    _use_layout(monkeypatch, layout)
    _install_layout(browsers_root, layout)

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(browsers_root))
    browser_bootstrap.ensure_browser_installed()
    assert installer.calls == []


def test_ensure_browser_installed_invokes_playwright_when_missing(
    browsers_root: Path, installer: _FakeInstaller, monkeypatch: pytest.MonkeyPatch
) -> None:
    from koda.services import browser_bootstrap

    _use_layout(monkeypatch, "linux-x64")
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(browsers_root))
    # Simulate a successful install by creating the expected layout.
    installer.effect = lambda: _install_layout(browsers_root, "linux-x64")

    browser_bootstrap.ensure_browser_installed()

    assert len(installer.calls) == 1
    cmd, called_kwargs = installer.calls[0]
    assert cmd == [sys.executable, *_INSTALL_COMMAND_TAIL]
    assert called_kwargs["env"]["PLAYWRIGHT_BROWSERS_PATH"] == str(browsers_root)
    assert browser_bootstrap._chromium_present(browsers_root) is True


def test_ensure_browser_installed_installs_over_a_stale_revision(
    browsers_root: Path, installer: _FakeInstaller, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A build left by another Playwright version does not stop the pinned one being installed."""
    from koda.services import browser_bootstrap

    _use_layout(monkeypatch, "linux-arm64")
    _install_layout(browsers_root, "linux-arm64", revision=_STALE_REVISION)
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(browsers_root))

    browser_bootstrap.ensure_browser_installed()

    assert len(installer.calls) == 1


def test_ensure_browser_installed_defers_to_playwright_when_lookup_unavailable(
    browsers_root: Path, installer: _FakeInstaller, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without an answer from the driver, Playwright's own installer decides.

    ``playwright install`` skips builds whose installation already completed,
    so this fallback never downloads a browser that is present.
    """
    from koda.services import browser_bootstrap

    _use_layout(monkeypatch, "linux-x64")
    _install_layout(browsers_root, "linux-x64")
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(browsers_root))
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", str(_fake_node(tmp_path, "exit 3")))

    assert browser_bootstrap._chromium_present(browsers_root) is None
    browser_bootstrap.ensure_browser_installed()

    assert len(installer.calls) == 1


def test_ensure_browser_installed_swallows_subprocess_failure(
    browsers_root: Path, installer: _FakeInstaller, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed install must not abort the supervisor — browser is optional."""
    from koda.services import browser_bootstrap

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(browsers_root))
    installer.error = subprocess.CalledProcessError(returncode=1, cmd=["playwright", "install"])

    # Must not raise.
    browser_bootstrap.ensure_browser_installed()
    assert len(installer.calls) == 1


def test_ensure_browser_installed_handles_missing_playwright_cli(
    browsers_root: Path, installer: _FakeInstaller, monkeypatch: pytest.MonkeyPatch
) -> None:
    from koda.services import browser_bootstrap

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(browsers_root))
    installer.error = FileNotFoundError()

    browser_bootstrap.ensure_browser_installed()
    assert len(installer.calls) == 1


def test_ensure_browser_installed_respects_env_path(
    tmp_path: Path, installer: _FakeInstaller, monkeypatch: pytest.MonkeyPatch
) -> None:
    from koda.services import browser_bootstrap

    _use_layout(monkeypatch, "linux-x64")
    custom_path = tmp_path / "custom-browsers"
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(custom_path))
    # Simulate install into the custom path to mark success.
    installer.effect = lambda: _install_layout(custom_path, "linux-x64")

    browser_bootstrap.ensure_browser_installed()

    assert [Path(kwargs["env"]["PLAYWRIGHT_BROWSERS_PATH"]) for _, kwargs in installer.calls] == [custom_path]
    assert browser_bootstrap._chromium_present(custom_path) is True


def test_ensure_browser_installed_in_background_does_not_block() -> None:
    from koda.services import browser_bootstrap

    with patch.object(browser_bootstrap.threading.Thread, "start") as start_mock:
        browser_bootstrap.ensure_browser_installed_in_background()

    assert start_mock.call_count == 1
