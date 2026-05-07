"""Discord adapter using the discord.py library.

Transport: WebSocket Gateway — the adapter maintains a persistent connection
to Discord's gateway and receives events in real time.
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
    import discord  # type: ignore[import-untyped]
except ImportError:
    discord = None  # type: ignore[assignment]

log = get_logger(__name__)


class DiscordAdapter(ChannelAdapter):
    """Bridges Discord's gateway WebSocket into the Koda channel layer."""

    channel_type: str = "discord"
    is_official: bool = True

    def __init__(self) -> None:
        self._agent_id: str = ""
        self._token: str = ""
        self._client: Any = None
        self._task: asyncio.Task[None] | None = None
        self._running: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self, agent_id: str, secrets: dict[str, str]) -> None:
        if discord is None:
            raise RuntimeError("discord.py is not installed. Install it with: pip install discord.py")
        self._agent_id = agent_id
        self._token = secrets["DISCORD_BOT_TOKEN"]
        log.info("discord.initialized: agent=%s", agent_id)

    async def start(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        self._client = discord.Client(intents=intents)

        @self._client.event
        async def on_message(message: Any) -> None:
            # Ignore messages from bots (including ourselves).
            if message.author.bot:
                return
            await self._handle_message(message)

        @self._client.event
        async def on_ready() -> None:
            log.info(
                "discord.connected: agent=%s user=%s",
                self._agent_id,
                self._client.user,
            )

        self._running = True
        self._task = asyncio.create_task(self._run_client())
        log.info("discord.started: agent=%s", self._agent_id)

    async def _run_client(self) -> None:
        try:
            await self._client.start(self._token)
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("discord.client_error: agent=%s", self._agent_id)
            self._running = False

    async def stop(self) -> None:
        self._running = False
        if self._client is not None:
            await self._client.close()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        log.info("discord.stopped: agent=%s", self._agent_id)

    # ------------------------------------------------------------------
    # Inbound
    # ------------------------------------------------------------------

    async def _handle_message(self, message: Any) -> None:
        is_group = hasattr(message.channel, "guild") and message.channel.guild is not None

        channel = ChannelIdentity(
            channel_type="discord",
            channel_id=str(message.channel.id),
            user_id=str(message.author.id),
            user_display_name=message.author.display_name,
            is_group=is_group,
        )

        reply_to_id: str | None = None
        if message.reference and message.reference.message_id:
            reply_to_id = str(message.reference.message_id)

        incoming = IncomingMessage(
            id=str(message.id),
            channel=channel,
            text=message.content,
            timestamp=time.time(),
            reply_to_id=reply_to_id,
            raw_platform_data=message,
        )
        await self._dispatch_inbound(incoming)

    # ------------------------------------------------------------------
    # Outbound
    # ------------------------------------------------------------------

    async def send_text(self, channel: ChannelIdentity, msg: OutgoingMessage) -> str:
        if self._client is None:
            raise RuntimeError("Discord adapter not initialized")
        dc_channel = self._client.get_channel(int(channel.channel_id))
        if dc_channel is None:
            dc_channel = await self._client.fetch_channel(int(channel.channel_id))
        sent = await dc_channel.send(msg.text)
        return str(sent.id)

    async def send_typing(self, channel: ChannelIdentity) -> None:
        if self._client is None:
            return
        dc_channel = self._client.get_channel(int(channel.channel_id))
        if dc_channel is None:
            dc_channel = await self._client.fetch_channel(int(channel.channel_id))
        await dc_channel.typing()

    async def send_voice(self, channel: ChannelIdentity, path: str, caption: str = "") -> None:
        if self._client is None:
            raise RuntimeError("Discord adapter not initialized")
        dc_channel = self._client.get_channel(int(channel.channel_id))
        if dc_channel is None:
            dc_channel = await self._client.fetch_channel(int(channel.channel_id))
        await dc_channel.send(content=caption or None, file=discord.File(path))

    async def send_document(self, channel: ChannelIdentity, path: str, filename: str, caption: str = "") -> None:
        if self._client is None:
            raise RuntimeError("Discord adapter not initialized")
        dc_channel = self._client.get_channel(int(channel.channel_id))
        if dc_channel is None:
            dc_channel = await self._client.fetch_channel(int(channel.channel_id))
        await dc_channel.send(content=caption or None, file=discord.File(path, filename=filename))

    async def send_image(self, channel: ChannelIdentity, path: str, caption: str = "") -> None:
        if self._client is None:
            raise RuntimeError("Discord adapter not initialized")
        dc_channel = self._client.get_channel(int(channel.channel_id))
        if dc_channel is None:
            dc_channel = await self._client.fetch_channel(int(channel.channel_id))
        await dc_channel.send(content=caption or None, file=discord.File(path))

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        status = "stopped"
        if self._running and self._client and self._client.is_ready():
            status = "running"
        elif self._running:
            status = "connecting"
        return {
            "channel_type": self.channel_type,
            "is_official": self.is_official,
            "status": status,
        }
