"""Entrypoint for the control-plane supervisor."""

from __future__ import annotations

import asyncio

from koda.control_plane.supervisor import run_supervisor
from koda.services.browser_bootstrap import ensure_browser_installed


def main() -> None:
    # Auto-provision Playwright browsers when missing so the app boots
    # "ready to use" — browser tools would otherwise fail with "Browser is
    # not running. It may not be installed or failed to start." whenever
    # the runtime image was built without chromium in the expected path.
    ensure_browser_installed()
    asyncio.run(run_supervisor())


if __name__ == "__main__":
    main()
