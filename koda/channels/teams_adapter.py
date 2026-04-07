"""Microsoft Teams adapter using the Bot Framework SDK.

Transport: Webhook — the adapter exposes ``handle_webhook`` for aiohttp
route registration.  The Bot Framework Adapter processes inbound activities.
"""

from __future__ import annotations

import time
from typing import Any

from koda.channels.base import ChannelAdapter
from koda.channels.types import ChannelIdentity, IncomingMessage, OutgoingMessage
from koda.logging_config import get_logger

try:
    from botbuilder.core import (  # type: ignore[import-untyped]
        BotFrameworkAdapter,
        BotFrameworkAdapterSettings,
        MessageFactory,
        TurnContext,
    )
    from botbuilder.schema import Activity  # type: ignore[import-untyped]
except ImportError:
    BotFrameworkAdapter = None  # type: ignore[assignment,misc]
    BotFrameworkAdapterSettings = None  # type: ignore[assignment,misc]
    MessageFactory = None  # type: ignore[assignment,misc]
    TurnContext = None  # type: ignore[assignment,misc]
    Activity = None  # type: ignore[assignment,misc]

log = get_logger(__name__)


class TeamsAdapter(ChannelAdapter):
    """Bridges Microsoft Teams via the Bot Framework into the Koda channel layer."""

    channel_type: str = "teams"
    is_official: bool = True

    def __init__(self) -> None:
        self._agent_id: str = ""
        self._app_id: str = ""
        self._app_password: str = ""
        self._bf_adapter: Any = None
        self._running: bool = False
        # Store conversation references keyed by conversation ID for
        # concurrency-safe proactive messaging (C2 fix).
        self._conversation_refs: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self, agent_id: str, secrets: dict[str, str]) -> None:
        if BotFrameworkAdapter is None:
            raise RuntimeError(
                "botbuilder-core is not installed. "
                "Install it with: pip install botbuilder-core botbuilder-integration-aiohttp"
            )
        self._agent_id = agent_id
        self._app_id = secrets["TEAMS_APP_ID"]
        self._app_password = secrets["TEAMS_APP_PASSWORD"]

        settings = BotFrameworkAdapterSettings(
            app_id=self._app_id,
            app_password=self._app_password,
        )
        self._bf_adapter = BotFrameworkAdapter(settings)
        log.info("teams.initialized: agent=%s", agent_id)

    async def start(self) -> None:
        # Webhook-based — listening is passive; nothing to start.
        self._running = True
        log.info("teams.started: agent=%s", self._agent_id)

    async def stop(self) -> None:
        self._running = False
        self._bf_adapter = None
        self._conversation_refs.clear()
        log.info("teams.stopped: agent=%s", self._agent_id)

    # ------------------------------------------------------------------
    # Webhook handling
    # ------------------------------------------------------------------

    async def handle_webhook(self, request: Any) -> Any:
        """Process inbound Bot Framework activity from Teams."""
        from aiohttp import web

        try:
            body = await request.json()
        except Exception:
            return web.Response(status=400, text="Invalid JSON")

        activity = Activity().deserialize(body)
        auth_header = request.headers.get("Authorization", "")

        async def _on_turn(turn_context: Any) -> None:
            if turn_context.activity.type == "message":
                await self._handle_message(turn_context)

        try:
            await self._bf_adapter.process_activity(activity, auth_header, _on_turn)
        except Exception:
            log.exception("teams.webhook_error: agent=%s", self._agent_id)
            return web.Response(status=500, text="Processing error")

        return web.Response(status=200)

    async def _handle_message(self, turn_context: Any) -> None:
        activity = turn_context.activity
        sender = activity.from_property
        conversation = activity.conversation

        is_group = getattr(conversation, "is_group", False) or (
            getattr(conversation, "conversation_type", "") == "groupChat"
        )

        channel = ChannelIdentity(
            channel_type="teams",
            channel_id=conversation.id,
            user_id=sender.id if sender else "",
            user_display_name=sender.name if sender else "",
            is_group=bool(is_group),
        )

        incoming = IncomingMessage(
            id=activity.id or "",
            channel=channel,
            text=activity.text or "",
            timestamp=time.time(),
            reply_to_id=getattr(activity, "reply_to_id", None),
            raw_platform_data=activity,
        )

        # Store a conversation reference for concurrency-safe proactive messaging.
        conv_ref = TurnContext.get_conversation_reference(activity)
        self._conversation_refs[conversation.id] = conv_ref

        await self._dispatch_inbound(incoming)

    # ------------------------------------------------------------------
    # Outbound (C2 fix — use conversation references, not shared context)
    # ------------------------------------------------------------------

    async def _send_via_conversation(self, conversation_id: str, callback: Any) -> None:
        """Send a message to a conversation using a stored reference."""
        conv_ref = self._conversation_refs.get(conversation_id)
        if conv_ref is None:
            log.warning("teams.no_conversation_ref: conversation=%s", conversation_id)
            return
        await self._bf_adapter.continue_conversation(conv_ref, callback, self._app_id)

    async def send_text(self, channel: ChannelIdentity, msg: OutgoingMessage) -> str:
        if self._bf_adapter is None:
            raise RuntimeError("Teams adapter not initialized")

        result_id = ""

        async def _callback(turn_context: Any) -> None:
            nonlocal result_id
            reply = MessageFactory.text(msg.text)
            response = await turn_context.send_activity(reply)
            result_id = str(getattr(response, "id", ""))

        await self._send_via_conversation(channel.channel_id, _callback)
        return result_id

    async def send_typing(self, channel: ChannelIdentity) -> None:
        async def _callback(turn_context: Any) -> None:
            typing_activity = Activity(type="typing")
            await turn_context.send_activity(typing_activity)

        await self._send_via_conversation(channel.channel_id, _callback)

    async def send_voice(self, channel: ChannelIdentity, path: str, caption: str = "") -> None:
        # Teams does not support direct voice notes; send as attachment.
        await self.send_document(channel, path, "voice.ogg", caption)

    async def send_document(self, channel: ChannelIdentity, path: str, filename: str, caption: str = "") -> None:
        if self._bf_adapter is None:
            raise RuntimeError("Teams adapter not initialized")

        async def _callback(turn_context: Any) -> None:
            from botbuilder.schema import Attachment

            with open(path, "rb") as f:
                content = f.read()

            import base64

            b64 = base64.b64encode(content).decode()
            attachment = Attachment(
                name=filename,
                content_type="application/octet-stream",
                content_url=f"data:application/octet-stream;base64,{b64}",
            )
            reply = MessageFactory.text(caption)
            reply.attachments = [attachment]
            await turn_context.send_activity(reply)

        await self._send_via_conversation(channel.channel_id, _callback)

    async def send_image(self, channel: ChannelIdentity, path: str, caption: str = "") -> None:
        if self._bf_adapter is None:
            raise RuntimeError("Teams adapter not initialized")

        async def _callback(turn_context: Any) -> None:
            from botbuilder.schema import Attachment

            with open(path, "rb") as f:
                content = f.read()

            import base64

            b64 = base64.b64encode(content).decode()
            attachment = Attachment(
                name="image.png",
                content_type="image/png",
                content_url=f"data:image/png;base64,{b64}",
            )
            reply = MessageFactory.text(caption)
            reply.attachments = [attachment]
            await turn_context.send_activity(reply)

        await self._send_via_conversation(channel.channel_id, _callback)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        return {
            "channel_type": self.channel_type,
            "is_official": self.is_official,
            "status": "running" if self._running else "stopped",
        }
