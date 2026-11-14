"""Idempotent Playwright/Chromium provisioning.

Koda's runtime browser tools (navigate, screenshot, click, etc.) rely on
Playwright-managed Chromium. The Dockerfile installs it at build time, but
if the image pre-dates that change or the container's HOME points at a
fresh volume (``/var/lib/koda/runtime/home`` in the default compose), the
binary can be missing at runtime — every browser tool then fails with
``Browser is not running. It may not be installed or failed to start.``

The supervisor calls ``ensure_browser_installed()`` at startup so the app
boots ready-to-use instead of asking the operator to run ``playwright
install`` manually. Presence is decided by the executable the pinned
Playwright itself launches, asked from its own driver (one short Node run):
that file must exist, and its build must carry the completion marker
Playwright's installer writes once the build is fully extracted. A build cut
off mid-extract is therefore reinstalled, not trusted. A build marked complete
whose executable is gone is reinstalled with ``--force``, because the
installer skips any build it marked complete. It emits a clear log when it has
to install.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from koda.logging_config import get_logger

log = get_logger(__name__)

_DEFAULT_BROWSERS_PATH = "/var/lib/koda/playwright-browsers"
_LOOKUP_TIMEOUT_SECONDS = 30.0
_INSTALL_TIMEOUT_SECONDS = 600
# Installs Chromium, its headless shell and ffmpeg, skipping any build the
# installer already marked complete.
_INSTALL_ARGS = ("install", "chromium")
# Registry names (``chromium-headless-shell``) are passed to the installer as
# an argument, so only plain names are accepted from the driver.
_REGISTRY_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")

# Run by the pinned Playwright driver's Node with its package directory as
# argument. Its own launch code picks the executable for
# ``chromium.launch(headless=True)``, the launch ``BrowserManager`` performs,
# and its registry maps that to a path for this host, revision and
# PLAYWRIGHT_BROWSERS_PATH, and to the browser directory whose completion
# marker its installer checks. Prints {"executablePath": <path or null>,
# "installationMarker": <path or null>, "name": <registry name or null>}; a
# null executablePath means Playwright has no build for this host.
_LAUNCH_EXECUTABLE_LOOKUP = """
const path = require("path");
const serverDir = path.join(process.argv[1], "lib", "server");
const server = require(path.join(serverDir, "index.js"));
const { browserDirectoryToMarkerFilePath } = require(path.join(serverDir, "registry", "index.js"));
const chromium = server.createPlaywright({ sdkLanguage: "python" }).chromium;
const executable = server.registry.findExecutable(chromium.getExecutableName({ headless: true }));
const executablePath = (executable && executable.executablePath()) || null;
const installationMarker =
  executablePath && executable.directory ? browserDirectoryToMarkerFilePath(executable.directory) : null;
const name = (executablePath && executable.name) || null;
process.stdout.write(JSON.stringify({ executablePath, installationMarker, name }));
"""


class _LookupUnavailableError(Exception):
    """The pinned Playwright driver could not say which executable it launches."""


@dataclass(frozen=True)
class _LaunchExecutable:
    """The executable the pinned Playwright launches, its build's completion marker and registry name.

    Playwright's installer writes ``installation_marker`` only after the
    build is fully extracted, and downloads again any build without it.
    ``name`` is what ``playwright install`` takes to install that build alone
    (``chromium-headless-shell``).
    """

    path: Path
    installation_marker: Path
    name: str


class _ChromiumState(Enum):
    """What the bootstrap found for the executable the pinned Playwright launches."""

    PRESENT = "present"
    # No usable build: not installed, another revision, or an extract cut off
    # before the installer marked it complete. ``playwright install`` repairs it.
    MISSING = "missing"
    # The installer marked the build complete but its executable is gone. The
    # installer skips a marked build, so only ``--force`` downloads it again.
    MARKED_WITHOUT_EXECUTABLE = "marked_without_executable"
    # The driver could not be asked; the installer decides.
    UNKNOWN = "unknown"


def _browsers_path() -> Path:
    return Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or _DEFAULT_BROWSERS_PATH)


def _launch_executable(browsers_path: Path) -> _LaunchExecutable | None:
    """Return the executable the pinned Playwright launches for headless Chromium.

    ``None`` means the pinned Playwright has no Chromium build for this host.
    Raises ``_LookupUnavailableError`` when its driver cannot be asked.
    """
    try:
        from playwright._impl._driver import compute_driver_executable, get_driver_env

        node, cli = compute_driver_executable()
        env = get_driver_env()
    except Exception as exc:
        raise _LookupUnavailableError(f"playwright driver not found: {exc!r}") from exc
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_path)
    try:
        result = subprocess.run(
            [node, "-e", _LAUNCH_EXECUTABLE_LOOKUP, str(Path(cli).parent)],
            env=env,
            capture_output=True,
            text=True,
            timeout=_LOOKUP_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise _LookupUnavailableError(f"playwright driver did not run: {exc!r}") from exc
    if result.returncode != 0:
        raise _LookupUnavailableError(f"playwright driver exited {result.returncode}: {result.stderr.strip()[-500:]}")
    try:
        payload = json.loads(result.stdout)
    except ValueError as exc:
        raise _LookupUnavailableError(f"unreadable driver answer: {result.stdout[:200]!r}") from exc
    if not isinstance(payload, dict):
        raise _LookupUnavailableError(f"unexpected driver answer: {result.stdout[:200]!r}")
    executable = payload.get("executablePath", "")
    if executable is None:
        return None
    marker = payload.get("installationMarker")
    name = payload.get("name")
    if not (
        isinstance(executable, str)
        and executable
        and isinstance(marker, str)
        and marker
        and isinstance(name, str)
        and _REGISTRY_NAME.fullmatch(name)
    ):
        raise _LookupUnavailableError(f"unexpected driver answer: {result.stdout[:200]!r}")
    return _LaunchExecutable(path=Path(executable), installation_marker=Path(marker), name=name)


def _chromium_state(browsers_path: Path) -> tuple[_ChromiumState, _LaunchExecutable | None]:
    """Classify the executable the pinned Playwright launches, with the lookup's answer.

    Installed means the executable exists and Playwright's installer marked
    its build complete. An executable without the marker is left by an
    extract cut off mid-way (say, the container stopped during the first-boot
    install); ``playwright install`` downloads that build again, so it counts
    as missing. A marker without the executable (the file was deleted after
    the install) counts as missing too, but the installer skips a marked
    build, so it needs ``--force``.
    """
    try:
        executable = _launch_executable(browsers_path)
    except _LookupUnavailableError as exc:
        log.warning("browser_bootstrap_lookup_unavailable", path=str(browsers_path), reason=str(exc))
        return _ChromiumState.UNKNOWN, None
    if executable is None:
        return _ChromiumState.MISSING, None
    # The installer tests the marker for existence only; so does this check.
    marked = os.path.exists(executable.installation_marker)
    if not marked:
        return _ChromiumState.MISSING, executable
    if not os.path.isfile(executable.path):
        return _ChromiumState.MARKED_WITHOUT_EXECUTABLE, executable
    return _ChromiumState.PRESENT, executable


def _chromium_present(browsers_path: Path) -> bool | None:
    """Return whether the executable the pinned Playwright launches is installed.

    ``None`` when its driver cannot be asked: the caller then falls back to
    ``playwright install``, which skips builds that already finished
    installing, so a complete install is not downloaded again.
    """
    state, _ = _chromium_state(browsers_path)
    if state is _ChromiumState.UNKNOWN:
        return None
    return state is _ChromiumState.PRESENT


def _install_command(state: _ChromiumState, executable: _LaunchExecutable | None) -> list[str]:
    """The ``playwright install`` run that repairs ``state``.

    A build the installer marked complete is skipped unless forced, so only
    that build is reinstalled with ``--force``. Everything else is the plain
    install, which downloads only the builds not marked complete.
    """
    if state is _ChromiumState.MARKED_WITHOUT_EXECUTABLE and executable is not None:
        return [sys.executable, "-m", "playwright", "install", "--force", executable.name]
    return [sys.executable, "-m", "playwright", *_INSTALL_ARGS]


def ensure_browser_installed_in_background() -> None:
    """Run browser provisioning without blocking process readiness."""
    thread = threading.Thread(
        target=ensure_browser_installed,
        name="koda-browser-bootstrap",
        daemon=True,
    )
    thread.start()


def ensure_browser_installed() -> None:
    """Install Playwright Chromium into ``PLAYWRIGHT_BROWSERS_PATH`` if missing.

    Failures are logged but never propagated — the browser is optional, and
    the rest of the runtime (LLM, memory, knowledge) must start even when
    the install step can't run (no network, no disk space, etc.). Browser
    tools will still surface a clear error to the operator at call time.
    """
    browsers_path = _browsers_path()
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(browsers_path))

    state, executable = _chromium_state(browsers_path)
    if state is _ChromiumState.PRESENT:
        log.debug("browser_bootstrap_skipped_already_present", path=str(browsers_path))
        return

    try:
        browsers_path.mkdir(parents=True, exist_ok=True)
    except Exception:
        log.warning("browser_bootstrap_mkdir_failed", path=str(browsers_path), exc_info=True)
        return

    command = _install_command(state, executable)
    log.info("browser_bootstrap_installing", path=str(browsers_path), state=state.value, command=command[2:])
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_path)
    try:
        subprocess.run(
            command,
            env=env,
            check=True,
            timeout=_INSTALL_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        log.warning("browser_bootstrap_playwright_cli_missing")
        return
    except subprocess.CalledProcessError as exc:
        log.warning("browser_bootstrap_install_failed", returncode=exc.returncode)
        return
    except subprocess.TimeoutExpired:
        log.warning("browser_bootstrap_install_timeout")
        return
    except Exception:
        log.exception("browser_bootstrap_install_error")
        return

    present = _chromium_present(browsers_path)
    if present:
        log.info("browser_bootstrap_installed", path=str(browsers_path))
    elif present is None:
        log.info("browser_bootstrap_install_finished_unverified", path=str(browsers_path))
    else:
        log.warning("browser_bootstrap_install_completed_but_binary_missing", path=str(browsers_path))
