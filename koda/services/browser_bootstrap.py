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
Playwright itself launches, asked from its own driver (one short Node run)
and probed with a single exists() check; it emits a clear log when it has to
install.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

from koda.logging_config import get_logger

log = get_logger(__name__)

_DEFAULT_BROWSERS_PATH = "/var/lib/koda/playwright-browsers"
_LOOKUP_TIMEOUT_SECONDS = 30.0

# Run by the pinned Playwright driver's Node with its package directory as
# argument. Its own launch code picks the executable for
# ``chromium.launch(headless=True)``, the launch ``BrowserManager`` performs,
# and its registry maps that to a path for this host, revision and
# PLAYWRIGHT_BROWSERS_PATH. Prints {"executablePath": <path or null>}; null
# means Playwright has no build for this host.
_LAUNCH_EXECUTABLE_LOOKUP = """
const path = require("path");
const server = require(path.join(process.argv[1], "lib", "server", "index.js"));
const chromium = server.createPlaywright({ sdkLanguage: "python" }).chromium;
const executable = server.registry.findExecutable(chromium.getExecutableName({ headless: true }));
process.stdout.write(JSON.stringify({ executablePath: (executable && executable.executablePath()) || null }));
"""


class _LookupUnavailableError(Exception):
    """The pinned Playwright driver could not say which executable it launches."""


def _browsers_path() -> Path:
    return Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or _DEFAULT_BROWSERS_PATH)


def _launch_executable(browsers_path: Path) -> Path | None:
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
    executable = payload.get("executablePath") if isinstance(payload, dict) else ""
    if executable is None:
        return None
    if not isinstance(executable, str) or not executable:
        raise _LookupUnavailableError(f"unexpected driver answer: {result.stdout[:200]!r}")
    return Path(executable)


def _chromium_present(browsers_path: Path) -> bool | None:
    """Return whether the executable the pinned Playwright launches is installed.

    ``None`` when its driver cannot be asked: the caller then falls back to
    ``playwright install``, which skips builds that already finished
    installing, so a complete install is not downloaded again.
    """
    try:
        executable = _launch_executable(browsers_path)
    except _LookupUnavailableError as exc:
        log.warning("browser_bootstrap_lookup_unavailable", path=str(browsers_path), reason=str(exc))
        return None
    return executable is not None and os.path.isfile(executable)


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

    if _chromium_present(browsers_path):
        log.debug("browser_bootstrap_skipped_already_present", path=str(browsers_path))
        return

    try:
        browsers_path.mkdir(parents=True, exist_ok=True)
    except Exception:
        log.warning("browser_bootstrap_mkdir_failed", path=str(browsers_path), exc_info=True)
        return

    log.info("browser_bootstrap_installing", path=str(browsers_path))
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_path)
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            env=env,
            check=True,
            timeout=600,
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
