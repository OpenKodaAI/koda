"""Webhook dispatcher — registers per-channel webhook routes on the health server.

Channels that require inbound webhooks (WhatsApp, Teams, LINE, Messenger,
Instagram) register their routes here.  The routes are mounted on the
existing aiohttp ``web.Application`` that already runs for health checks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from koda.logging_config import get_logger

if TYPE_CHECKING:
    from aiohttp import web

    from koda.channels.base import ChannelAdapter

log = get_logger(__name__)

_registered_routes: list[str] = []


async def register_channel_webhook(
    app: web.Application,
    adapter: ChannelAdapter,
    agent_id: str,
) -> str | None:
    """Register webhook POST (and optional GET for verification) routes.

    Returns the webhook path that should be configured on the platform side,
    or ``None`` if the adapter does not support webhooks.
    """
    if not hasattr(adapter, "handle_webhook"):
        return None

    path = f"/webhooks/{adapter.channel_type}/{agent_id}"

    # POST — inbound messages / events
    app.router.add_post(path, adapter.handle_webhook)  # type: ignore[arg-type]
    _registered_routes.append(f"POST {path}")

    # GET — webhook verification (WhatsApp, Messenger, LINE, etc.)
    if hasattr(adapter, "handle_webhook_verification"):
        app.router.add_get(path, adapter.handle_webhook_verification)  # type: ignore[arg-type]
        _registered_routes.append(f"GET {path}")

    log.info("webhook_dispatcher.registered: %s -> %s", adapter.channel_type, path)
    return path


def registered_routes() -> list[str]:
    """Return a snapshot of all registered webhook routes (for observability)."""
    return list(_registered_routes)
