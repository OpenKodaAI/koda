"""LINE Messaging API adapter using the line-bot-sdk library.

Transport: Webhook — the adapter exposes ``handle_webhook`` for aiohttp
route registration.
"""

from __future__ import annotations

import time
from typing import Any

from koda.channels.base import ChannelAdapter
from koda.channels.types import ChannelIdentity, IncomingMessage, OutgoingMessage
from koda.logging_config import get_logger

try:
    from linebot.v3.messaging import (  # type: ignore[import-untyped]
        ApiClient,
        Configuration,
        MessagingApi,
        PushMessageRequest,
        TextMessage,
    )
    from linebot.v3.webhook import WebhookParser  # type: ignore[import-untyped]
    from linebot.v3.webhooks import MessageEvent, TextMessageContent  # type: ignore[import-untyped]
except ImportError:
    ApiClient = None  # type: ignore[assignment,misc]
    Configuration = None  # type: ignore[assignment,misc]
    MessagingApi = None  # type: ignore[assignment,misc]
    PushMessageRequest = None  # type: ignore[assignment,misc]
    TextMessage = None  # type: ignore[assignment,misc]
    WebhookParser = None  # type: ignore[assignment,misc]
    MessageEvent = None  # type: ignore[assignment,misc]
    TextMessageContent = None  # type: ignore[assignment,misc]

log = get_logger(__name__)


class LineAdapter(ChannelAdapter):
    """Bridges the LINE Messaging API into the Koda channel layer."""

    channel_type: str = "line"
    is_official: bool = True

    def __init__(self) -> None:
        self._agent_id: str = ""
        self._channel_secret: str = ""
        self._channel_access_token: str = ""
        self._api: Any = None
        self._parser: Any = None
        self._running: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self, agent_id: str, secrets: dict[str, str]) -> None:
        if MessagingApi is None:
            raise RuntimeError("line-bot-sdk is not installed. Install it with: pip install line-bot-sdk")
        self._agent_id = agent_id
        self._channel_secret = secrets["LINE_CHANNEL_SECRET"]
        self._channel_access_token = secrets["LINE_CHANNEL_ACCESS_TOKEN"]

        configuration = Configuration(access_token=self._channel_access_token)
        api_client = ApiClient(configuration)
        self._api = MessagingApi(api_client)
        self._parser = WebhookParser(self._channel_secret)
        log.info("line.initialized: agent=%s", agent_id)

    async def start(self) -> None:
        # Webhook-based — listening is passive; nothing to start.
        self._running = True
        log.info("line.started: agent=%s", self._agent_id)

    async def stop(self) -> None:
        self._running = False
        self._api = None
        self._parser = None
        log.info("line.stopped: agent=%s", self._agent_id)

    # ------------------------------------------------------------------
    # Webhook handling
    # ------------------------------------------------------------------

    async def handle_webhook(self, request: Any) -> Any:
        """Process inbound LINE webhook POST."""
        from aiohttp import web

        signature = request.headers.get("X-Line-Signature", "")
        body = await request.text()

        try:
            events = self._parser.parse(body, signature)
        except Exception:
            log.exception("line.webhook_parse_error: agent=%s", self._agent_id)
            return web.Response(status=400, text="Invalid signature")

        for event in events:
            if isinstance(event, MessageEvent) and isinstance(event.message, TextMessageContent):
                await self._handle_message_event(event)

        return web.Response(status=200, text="OK")

    async def _handle_message_event(self, event: Any) -> None:
        source = event.source
        source_type = getattr(source, "type", "user")

        user_id = getattr(source, "user_id", "")
        # Group / room context.
        if source_type == "group":
            channel_id = getattr(source, "group_id", user_id)
        elif source_type == "room":
            channel_id = getattr(source, "room_id", user_id)
        else:
            channel_id = user_id

        channel = ChannelIdentity(
            channel_type="line",
            channel_id=channel_id,
            user_id=user_id,
            user_display_name=user_id,  # LINE requires a profile API call to resolve names.
            is_group=source_type in ("group", "room"),
        )

        incoming = IncomingMessage(
            id=event.message.id,
            channel=channel,
            text=event.message.text,
            timestamp=time.time(),
            reply_to_id=None,  # LINE doesn't support threaded replies; reply_token is in raw_platform_data
            raw_platform_data=event,
        )
        await self._dispatch_inbound(incoming)

    # ------------------------------------------------------------------
    # Outbound
    # ------------------------------------------------------------------

    async def send_text(self, channel: ChannelIdentity, msg: OutgoingMessage) -> str:
        if self._api is None:
            raise RuntimeError("LINE adapter not initialized")
        request = PushMessageRequest(
            to=channel.channel_id,
            messages=[TextMessage(text=msg.text)],
        )
        self._api.push_message(request)
        return ""

    async def send_typing(self, channel: ChannelIdentity) -> None:
        # LINE does not support a typing indicator via the Messaging API.
        pass

    async def send_voice(self, channel: ChannelIdentity, path: str, caption: str = "") -> None:
        # LINE voice messages require uploaded media URLs.
        # Fall back to sending as a document.
        await self.send_document(channel, path, "voice.ogg", caption)

    async def send_document(self, channel: ChannelIdentity, path: str, filename: str, caption: str = "") -> None:
        # LINE does not support direct file uploads via the Messaging API;
        # files must be hosted at a public URL. Send a text fallback.
        log.warning("line.send_document: file uploads require a public URL; sending caption only")
        if caption:
            await self.send_text(channel, OutgoingMessage(text=f"[{filename}] {caption}"))

    async def send_image(self, channel: ChannelIdentity, path: str, caption: str = "") -> None:
        # LINE image messages require a public URL for the image.
        log.warning("line.send_image: image uploads require a public URL; sending caption only")
        if caption:
            await self.send_text(channel, OutgoingMessage(text=caption))

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        return {
            "channel_type": self.channel_type,
            "is_official": self.is_official,
            "status": "running" if self._running else "stopped",
        }
