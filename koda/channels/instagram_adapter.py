"""Instagram Messaging adapter using direct HTTP to the Meta Graph API.

Transport: Webhook — the adapter exposes ``handle_webhook`` and
``handle_webhook_verification`` for aiohttp route registration.
``is_official = False`` because the Instagram Messaging API is in limited
availability and requires additional approval.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any

from koda.channels.base import ChannelAdapter
from koda.channels.types import ChannelIdentity, IncomingMessage, OutgoingMessage
from koda.logging_config import get_logger

log = get_logger(__name__)

_GRAPH_API_BASE = "https://graph.facebook.com/v19.0"


class InstagramAdapter(ChannelAdapter):
    """Bridges Instagram Messaging via the Graph API into the Koda channel layer."""

    channel_type: str = "instagram"
    is_official: bool = False

    def __init__(self) -> None:
        self._agent_id: str = ""
        self._page_access_token: str = ""
        self._app_secret: str = ""
        self._running: bool = False
        self._session: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self, agent_id: str, secrets: dict[str, str]) -> None:
        self._agent_id = agent_id
        self._page_access_token = secrets["INSTAGRAM_PAGE_ACCESS_TOKEN"]
        self._app_secret = secrets["INSTAGRAM_APP_SECRET"]
        log.info("instagram.initialized: agent=%s", agent_id)

    async def start(self) -> None:
        import aiohttp as aio

        self._session = aio.ClientSession()
        self._running = True
        log.info("instagram.started: agent=%s", self._agent_id)

    async def stop(self) -> None:
        self._running = False
        if self._session:
            await self._session.close()
            self._session = None
        log.info("instagram.stopped: agent=%s", self._agent_id)

    # ------------------------------------------------------------------
    # Webhook handling
    # ------------------------------------------------------------------

    async def handle_webhook_verification(self, request: Any) -> Any:
        """Handle Meta's GET verification challenge for Instagram."""
        from aiohttp import web

        mode = request.query.get("hub.mode")
        token = request.query.get("hub.verify_token")
        challenge = request.query.get("hub.challenge")

        # Instagram uses the same verification flow as Messenger.
        # The verify token is derived from the app secret for simplicity.
        expected_token = self._app_secret[:32]
        if mode == "subscribe" and token == expected_token:
            log.info("instagram.webhook_verified: agent=%s", self._agent_id)
            return web.Response(text=challenge, content_type="text/plain")

        log.warning("instagram.webhook_verify_failed: agent=%s", self._agent_id)
        return web.Response(status=403, text="Verification failed")

    async def handle_webhook(self, request: Any) -> Any:
        """Process inbound Instagram webhook POST."""
        from aiohttp import web

        body_bytes = await request.read()

        # Verify HMAC signature.
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not self._verify_signature(body_bytes, signature):
            log.warning("instagram.invalid_signature: agent=%s", self._agent_id)
            return web.Response(status=403, text="Invalid signature")

        try:
            import json

            payload: dict[str, Any] = json.loads(body_bytes)
        except Exception:
            return web.Response(status=400, text="Invalid JSON")

        if payload.get("object") != "instagram":
            return web.Response(status=200, text="OK")

        for entry in payload.get("entry", []):
            for messaging in entry.get("messaging", []):
                await self._process_messaging(messaging)

        return web.Response(status=200, text="OK")

    def _verify_signature(self, body: bytes, signature: str) -> bool:
        if not signature:
            return False
        expected = "sha256=" + hmac.new(self._app_secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def _process_messaging(self, messaging: dict[str, Any]) -> None:
        message = messaging.get("message")
        if message is None:
            return

        sender_id = messaging.get("sender", {}).get("id", "")
        msg_id = message.get("mid", "")
        text = message.get("text", "")

        channel = ChannelIdentity(
            channel_type="instagram",
            channel_id=sender_id,
            user_id=sender_id,
            user_display_name=sender_id,  # Requires Graph API call to resolve name.
            is_group=False,
        )

        incoming = IncomingMessage(
            id=msg_id,
            channel=channel,
            text=text,
            timestamp=time.time(),
            reply_to_id=message.get("reply_to", {}).get("mid") if message.get("reply_to") else None,
            raw_platform_data=messaging,
        )
        await self._dispatch_inbound(incoming)

    # ------------------------------------------------------------------
    # Outbound
    # ------------------------------------------------------------------

    async def send_text(self, channel: ChannelIdentity, msg: OutgoingMessage) -> str:
        url = f"{_GRAPH_API_BASE}/me/messages"
        payload = {
            "recipient": {"id": channel.channel_id},
            "message": {"text": msg.text},
        }
        params = {"access_token": self._page_access_token}

        async with self._session.post(url, json=payload, params=params) as resp:
            data = await resp.json()
            return str(data.get("message_id", ""))

    async def send_typing(self, channel: ChannelIdentity) -> None:
        url = f"{_GRAPH_API_BASE}/me/messages"
        payload = {
            "recipient": {"id": channel.channel_id},
            "sender_action": "typing_on",
        }
        params = {"access_token": self._page_access_token}

        await self._session.post(url, json=payload, params=params)

    async def send_voice(self, channel: ChannelIdentity, path: str, caption: str = "") -> None:
        await self._send_attachment(channel, path, "audio")
        if caption:
            await self.send_text(channel, OutgoingMessage(text=caption))

    async def send_document(self, channel: ChannelIdentity, path: str, filename: str, caption: str = "") -> None:
        # Instagram DMs have limited file support; send as generic attachment.
        await self._send_attachment(channel, path, "file")
        if caption:
            await self.send_text(channel, OutgoingMessage(text=caption))

    async def send_image(self, channel: ChannelIdentity, path: str, caption: str = "") -> None:
        await self._send_attachment(channel, path, "image")
        if caption:
            await self.send_text(channel, OutgoingMessage(text=caption))

    async def _send_attachment(self, channel: ChannelIdentity, path: str, att_type: str) -> None:
        import aiohttp as aio

        url = f"{_GRAPH_API_BASE}/me/messages"
        params = {"access_token": self._page_access_token}

        data = aio.FormData()
        data.add_field("recipient", f'{{"id":"{channel.channel_id}"}}')
        data.add_field(
            "message",
            f'{{"attachment":{{"type":"{att_type}","payload":{{"is_reusable":true}}}}}}',
        )
        with open(path, "rb") as f:
            data.add_field("filedata", f, filename=path.rsplit("/", 1)[-1])
            await self._session.post(url, data=data, params=params)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        return {
            "channel_type": self.channel_type,
            "is_official": self.is_official,
            "status": "running" if self._running else "stopped",
        }
