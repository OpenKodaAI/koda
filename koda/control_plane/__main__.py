"""Entrypoint for the control-plane supervisor."""

from __future__ import annotations

import asyncio
import logging

from koda.control_plane.crypto import MasterKeyError
from koda.control_plane.supervisor import run_supervisor
from koda.logging_config import setup_logging
from koda.services.browser_bootstrap import ensure_browser_installed_in_background


def configure_logging() -> None:
    """Configure redacting structured logs (``LOG_FORMAT`` picks console or JSON) before anything logs."""
    setup_logging()
    # aiohttp's access log was silent before logging was configured. Keep it so: its request
    # lines carry query strings, such as the authorization code of an MCP OAuth callback.
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)


def main() -> None:
    configure_logging()
    # Auto-provision Playwright browsers when missing, but never block
    # control-plane readiness on an optional browser download.
    ensure_browser_installed_in_background()
    try:
        asyncio.run(run_supervisor())
    except MasterKeyError as exc:
        # The message carries the operator guidance; a traceback would bury it.
        raise SystemExit(f"koda control plane refused to start: {exc}") from None


if __name__ == "__main__":
    main()
