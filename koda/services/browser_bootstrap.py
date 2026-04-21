"""Idempotent Playwright/Chromium provisioning.

Koda's runtime browser tools (navigate, screenshot, click, etc.) rely on
Playwright-managed Chromium. The Dockerfile installs it at build time, but
if the image pre-dates that change or the container's HOME points at a
fresh volume (``/var/lib/koda/runtime/home`` in the default compose), the
binary can be missing at runtime — every browser tool then fails with
``Browser is not running. It may not be installed or failed to start.``

The supervisor calls ``ensure_browser_installed()`` at startup so the app
boots ready-to-use instead of asking the operator to run ``playwright
install`` manually. The check is cheap when browsers are already present
(a single exists() probe) and emits a clear log when it has to install.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from koda.logging_config import get_logger

log = get_logger(__name__)

_DEFAULT_BROWSERS_PATH = "/var/lib/koda/playwright-browsers"


def _browsers_path() -> Path:
    return Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or _DEFAULT_BROWSERS_PATH)


def _chromium_present(browsers_path: Path) -> bool:
    """Return True when a usable chromium build is under ``browsers_path``."""
    if not browsers_path.is_dir():
        return False
    return any(
        candidate.is_file()
        for candidate in browsers_path.glob("chromium-*/chrome-linux/chrome")
    )


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

    if _chromium_present(browsers_path):
        log.info("browser_bootstrap_installed", path=str(browsers_path))
    else:
        log.warning("browser_bootstrap_install_completed_but_binary_missing", path=str(browsers_path))
