"""WhatsApp Cloud API adapter using the PyWa library.

Transport: Webhook — the adapter exposes ``handle_webhook`` and
``handle_webhook_verification`` for aiohttp route registration.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from typing import Any

from koda.channels.base import ChannelAdapter
from koda.channels.types import ChannelIdentity, IncomingMessage, OutgoingMessage
from koda.logging_config import get_logger

try:
    from pywa import WhatsApp  # type: ignore[import-untyped]
    from pywa.types import Message as WaMessage  # type: ignore[import-untyped]
except ImportError:
    WhatsApp = None  # type: ignore[assignment,misc]
    WaMessage = None  # type: ignore[assignment,misc]

log = get_logger(__name__)


class WhatsAppAdapter(ChannelAdapter):
    """Bridges the WhatsApp Cloud API via *pywa* into the Koda channel layer."""

    channel_type: str = "whatsapp"
    is_official: bool = True

    def __init__(self) -> None:
        self._agent_id: str = ""
        self._access_token: str = ""
        self._phone_number_id: str = ""
        self._verify_token: str = ""
        self._app_secret: str = ""
        self._client: Any = None
        self._running: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self, agent_id: str, secrets: dict[str, str]) -> None:
        if WhatsApp is None:
            raise RuntimeError("pywa is not installed. Install it with: pip install pywa")
        self._agent_id = agent_id
        self._access_token = secrets["WHATSAPP_ACCESS_TOKEN"]
        self._phone_number_id = secrets["WHATSAPP_PHONE_NUMBER_ID"]
        self._verify_token = secrets["WHATSAPP_VERIFY_TOKEN"]
        self._app_secret = secrets.get("WHATSAPP_APP_SECRET", "")
        self._client = WhatsApp(
            phone_id=self._phone_number_id,
            token=self._access_token,
        )
        log.info("whatsapp.initialized: agent=%s phone_id=%s", agent_id, self._phone_number_id)

    async def start(self) -> None:
        # Webhook-based — listening is passive; nothing to start.
        self._running = True
        log.info("whatsapp.started: agent=%s", self._agent_id)

    async def stop(self) -> None:
        self._running = False
        self._client = None
        log.info("whatsapp.stopped: agent=%s", self._agent_id)

    # ------------------------------------------------------------------
    # Webhook signature verification (C1 fix)
    # ------------------------------------------------------------------

    def _verify_signature(self, body: bytes, signature_header: str) -> bool:
        """Verify X-Hub-Signature-256 HMAC from Meta."""
        if not self._app_secret:
            log.error("whatsapp.no_app_secret: rejecting webhook — WHATSAPP_APP_SECRET is required")
            return False
        expected = (
            "sha256="
            + hmac.new(
                self._app_secret.encode(),
                body,
                hashlib.sha256,
            ).hexdigest()
        )
        return hmac.compare_digest(expected, signature_header)

    # ------------------------------------------------------------------
    # Webhook handling
    # ------------------------------------------------------------------

    async def handle_webhook_verification(self, request: Any) -> Any:
        """Handle Meta's GET verification challenge."""
        from aiohttp import web

        mode = request.query.get("hub.mode")
        token = request.query.get("hub.verify_token")
        challenge = request.query.get("hub.challenge")

        if mode == "subscribe" and token == self._verify_token:
            log.info("whatsapp.webhook_verified: agent=%s", self._agent_id)
            return web.Response(text=challenge, content_type="text/plain")

        log.warning("whatsapp.webhook_verify_failed: agent=%s", self._agent_id)
        return web.Response(status=403, text="Verification failed")

    async def handle_webhook(self, request: Any) -> Any:
        """Process inbound WhatsApp webhook POST."""
        from aiohttp import web

        body_bytes = await request.read()

        # Verify HMAC signature from Meta
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not self._verify_signature(body_bytes, signature):
            log.warning("whatsapp.invalid_signature: agent=%s", self._agent_id)
            return web.Response(status=403, text="Invalid signature")

        try:
            import json

            payload: dict[str, Any] = json.loads(body_bytes)
        except Exception:
            return web.Response(status=400, text="Invalid JSON")

        # WhatsApp webhook payload structure:
        # entry[].changes[].value.messages[]
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])
                contacts = value.get("contacts", [])
                contact_map: dict[str, str] = {
                    c["wa_id"]: c.get("profile", {}).get("name", c["wa_id"]) for c in contacts
                }

                for msg in messages:
                    await self._process_message(msg, contact_map)

        return web.Response(status=200, text="OK")

    async def _process_message(self, msg: dict[str, Any], contact_map: dict[str, str]) -> None:
        sender = msg.get("from", "")
        msg_id = msg.get("id", "")
        msg_type = msg.get("type", "")

        text = ""
        if msg_type == "text":
            text = msg.get("text", {}).get("body", "")
        elif msg_type == "image":
            text = msg.get("image", {}).get("caption", "")
        elif msg_type == "document":
            text = msg.get("document", {}).get("caption", "")

        display_name = contact_map.get(sender, sender)

        channel = ChannelIdentity(
            channel_type="whatsapp",
            channel_id=sender,
            user_id=sender,
            user_display_name=display_name,
            is_group=False,
        )

        incoming = IncomingMessage(
            id=msg_id,
            channel=channel,
            text=text,
            timestamp=time.time(),
            reply_to_id=msg.get("context", {}).get("message_id"),
            raw_platform_data=msg,
        )
        await self._dispatch_inbound(incoming)

    # ------------------------------------------------------------------
    # Outbound (C3 fix — wrap sync calls in asyncio.to_thread)
    # ------------------------------------------------------------------

    async def send_text(self, channel: ChannelIdentity, msg: OutgoingMessage) -> str:
        if self._client is None:
            raise RuntimeError("WhatsApp adapter not initialized")
        result = await asyncio.to_thread(self._client.send_message, to=channel.channel_id, text=msg.text)
        return str(getattr(result, "id", ""))

    async def send_typing(self, channel: ChannelIdentity) -> None:
        # WhatsApp Cloud API does not support a native typing indicator.
        pass

    async def send_voice(self, channel: ChannelIdentity, path: str, caption: str = "") -> None:
        if self._client is None:
            raise RuntimeError("WhatsApp adapter not initialized")
        with open(path, "rb") as f:
            await asyncio.to_thread(self._client.send_audio, to=channel.channel_id, audio=f)

    async def send_document(self, channel: ChannelIdentity, path: str, filename: str, caption: str = "") -> None:
        if self._client is None:
            raise RuntimeError("WhatsApp adapter not initialized")
        with open(path, "rb") as f:
            await asyncio.to_thread(
                self._client.send_document, to=channel.channel_id, document=f, filename=filename, caption=caption
            )

    async def send_image(self, channel: ChannelIdentity, path: str, caption: str = "") -> None:
        if self._client is None:
            raise RuntimeError("WhatsApp adapter not initialized")
        with open(path, "rb") as f:
            await asyncio.to_thread(self._client.send_image, to=channel.channel_id, image=f, caption=caption)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        return {
            "channel_type": self.channel_type,
            "is_official": self.is_official,
            "status": "running" if self._running else "stopped",
            "phone_number_id": self._phone_number_id,
        }
