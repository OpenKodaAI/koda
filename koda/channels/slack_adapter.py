"""Slack adapter using the slack-bolt[async] library with Socket Mode.

Transport: Socket Mode (WebSocket) — no public URL required.  The adapter
connects to Slack's Socket Mode gateway and receives events in real time.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any

from koda.channels.base import ChannelAdapter
from koda.channels.types import ChannelIdentity, IncomingMessage, OutgoingMessage
from koda.logging_config import get_logger

try:
    from slack_bolt.adapter.socket_mode.async_handler import (  # type: ignore[import-untyped]
        AsyncSocketModeHandler,
    )
    from slack_bolt.async_app import AsyncApp  # type: ignore[import-untyped]
except ImportError:
    AsyncApp = None  # type: ignore[assignment,misc]
    AsyncSocketModeHandler = None  # type: ignore[assignment,misc]

log = get_logger(__name__)


class SlackAdapter(ChannelAdapter):
    """Bridges Slack via Socket Mode into the Koda channel layer."""

    channel_type: str = "slack"
    is_official: bool = True

    def __init__(self) -> None:
        self._agent_id: str = ""
        self._bot_token: str = ""
        self._app_token: str = ""
        self._signing_secret: str = ""
        self._app: Any = None
        self._handler: Any = None
        self._task: asyncio.Task[None] | None = None
        self._running: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self, agent_id: str, secrets: dict[str, str]) -> None:
        if AsyncApp is None:
            raise RuntimeError("slack-bolt is not installed. Install it with: pip install slack-bolt[async]")
        self._agent_id = agent_id
        self._bot_token = secrets["SLACK_BOT_TOKEN"]
        self._app_token = secrets["SLACK_APP_TOKEN"]
        self._signing_secret = secrets["SLACK_SIGNING_SECRET"]

        self._app = AsyncApp(
            token=self._bot_token,
            signing_secret=self._signing_secret,
        )
        self._register_handlers()
        log.info("slack.initialized: agent=%s", agent_id)

    def _register_handlers(self) -> None:
        @self._app.message("")
        async def handle_message(message: dict[str, Any], say: Any) -> None:  # noqa: ARG001
            await self._handle_message(message)

    async def start(self) -> None:
        self._handler = AsyncSocketModeHandler(self._app, self._app_token)
        self._running = True
        self._task = asyncio.create_task(self._run_handler())
        log.info("slack.started: agent=%s", self._agent_id)

    async def _run_handler(self) -> None:
        try:
            await self._handler.start_async()
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("slack.handler_error: agent=%s", self._agent_id)
            self._running = False

    async def stop(self) -> None:
        self._running = False
        if self._handler is not None:
            await self._handler.close_async()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        log.info("slack.stopped: agent=%s", self._agent_id)

    # ------------------------------------------------------------------
    # Inbound
    # ------------------------------------------------------------------

    async def _handle_message(self, message: dict[str, Any]) -> None:
        # Ignore bot messages.
        if message.get("bot_id") or message.get("subtype") == "bot_message":
            return

        user_id = message.get("user", "")
        channel_id = message.get("channel", "")
        text = message.get("text", "")
        ts = message.get("ts", "")

        # Determine if this is a group channel.
        channel_type_raw = message.get("channel_type", "")
        is_group = channel_type_raw in ("channel", "group")

        channel = ChannelIdentity(
            channel_type="slack",
            channel_id=channel_id,
            user_id=user_id,
            user_display_name=user_id,  # Resolved later if needed.
            is_group=is_group,
        )

        reply_to_id: str | None = message.get("thread_ts") if message.get("thread_ts") != ts else None

        incoming = IncomingMessage(
            id=ts,
            channel=channel,
            text=text,
            timestamp=time.time(),
            reply_to_id=reply_to_id,
            raw_platform_data=message,
        )
        await self._dispatch_inbound(incoming)

    # ------------------------------------------------------------------
    # Outbound
    # ------------------------------------------------------------------

    async def send_text(self, channel: ChannelIdentity, msg: OutgoingMessage) -> str:
        if self._app is None:
            raise RuntimeError("Slack adapter not initialized")
        result = await self._app.client.chat_postMessage(channel=channel.channel_id, text=msg.text)
        return str(result.get("ts", ""))

    async def send_typing(self, channel: ChannelIdentity) -> None:
        # Slack does not have a direct typing indicator API for bots.
        pass

    async def send_voice(self, channel: ChannelIdentity, path: str, caption: str = "") -> None:
        if self._app is None:
            raise RuntimeError("Slack adapter not initialized")
        await self._app.client.files_upload_v2(
            channel=channel.channel_id,
            file=path,
            initial_comment=caption,
        )

    async def send_document(self, channel: ChannelIdentity, path: str, filename: str, caption: str = "") -> None:
        if self._app is None:
            raise RuntimeError("Slack adapter not initialized")
        await self._app.client.files_upload_v2(
            channel=channel.channel_id,
            file=path,
            filename=filename,
            initial_comment=caption,
        )

    async def send_image(self, channel: ChannelIdentity, path: str, caption: str = "") -> None:
        if self._app is None:
            raise RuntimeError("Slack adapter not initialized")
        await self._app.client.files_upload_v2(
            channel=channel.channel_id,
            file=path,
            initial_comment=caption,
        )

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        return {
            "channel_type": self.channel_type,
            "is_official": self.is_official,
            "status": "running" if self._running else "stopped",
        }
