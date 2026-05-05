"""Entrypoint for the control-plane supervisor."""

from __future__ import annotations

import asyncio

from koda.control_plane.supervisor import run_supervisor
from koda.services.browser_bootstrap import ensure_browser_installed_in_background


def main() -> None:
    # Auto-provision Playwright browsers when missing, but never block
    # control-plane readiness on an optional browser download.
    ensure_browser_installed_in_background()
    asyncio.run(run_supervisor())


if __name__ == "__main__":
    main()
