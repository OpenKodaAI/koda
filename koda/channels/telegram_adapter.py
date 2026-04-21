"""Telegram channel adapter — wraps the existing python-telegram-bot integration.

This adapter keeps the existing Telegram handler/polling model intact while
implementing the :class:`ChannelAdapter` interface for outbound messages.
Inbound messages continue to flow through the registered PTB handlers, which
call ``enqueue()`` directly.  The adapter also exposes ``_dispatch_inbound()``
so that the :class:`ChannelManager` can wire a unified callback if needed.
"""

from __future__ import annotations

import time
from typing import Any

from koda.channels.base import ChannelAdapter
from koda.channels.types import ChannelIdentity, IncomingMessage, OutgoingMessage
from koda.logging_config import get_logger

log = get_logger(__name__)


class TelegramAdapter(ChannelAdapter):
    """Adapter for Telegram Bot API via python-telegram-bot."""

    channel_type = "telegram"
    is_official = True

    def __init__(self) -> None:
        self._bot: Any = None
        self._agent_id: str = ""
        self._running = False

    async def initialize(self, agent_id: str, secrets: dict[str, str]) -> None:
        self._agent_id = agent_id
        token = secrets.get("AGENT_TOKEN", "")
        if not token:
            raise ValueError("AGENT_TOKEN is required for Telegram adapter")
        # Store token for later — the actual Application is built in __main__.py
        self._token = token

    async def start(self) -> None:
        """No-op: Telegram polling is started by __main__.py's app.run_polling()."""
        self._running = True
        log.info("telegram_adapter.started", agent_id=self._agent_id)

    async def stop(self) -> None:
        self._running = False
        log.info("telegram_adapter.stopped", agent_id=self._agent_id)

    def set_bot(self, bot: Any) -> None:
        """Inject the Telegram ExtBot instance after Application is built."""
        self._bot = bot

    # ------------------------------------------------------------------
    # Outbound
    # ------------------------------------------------------------------

    async def send_text(self, channel: ChannelIdentity, msg: OutgoingMessage) -> str:
        if not self._bot:
            raise RuntimeError("Telegram bot not initialized")
        from telegram.constants import ParseMode

        parse_mode = ParseMode.HTML if msg.parse_mode == "html" else None
        result = await self._bot.send_message(
            chat_id=int(channel.channel_id),
            text=msg.text,
            parse_mode=parse_mode,
        )
        return str(result.message_id)

    async def send_typing(self, channel: ChannelIdentity) -> None:
        if not self._bot:
            return
        from telegram.constants import ChatAction

        await self._bot.send_chat_action(
            chat_id=int(channel.channel_id),
            action=ChatAction.TYPING,
        )

    async def send_voice(self, channel: ChannelIdentity, path: str, caption: str = "") -> None:
        if not self._bot:
            return
        with open(path, "rb") as f:
            await self._bot.send_voice(
                chat_id=int(channel.channel_id),
                voice=f,
                caption=caption or None,
            )

    async def send_document(self, channel: ChannelIdentity, path: str, filename: str, caption: str = "") -> None:
        if not self._bot:
            return
        with open(path, "rb") as f:
            await self._bot.send_document(
                chat_id=int(channel.channel_id),
                document=f,
                filename=filename,
                caption=caption or None,
            )

    async def send_image(self, channel: ChannelIdentity, path: str, caption: str = "") -> None:
        if not self._bot:
            return
        with open(path, "rb") as f:
            await self._bot.send_photo(
                chat_id=int(channel.channel_id),
                photo=f,
                caption=caption or None,
            )

    # ------------------------------------------------------------------
    # Inbound normalization helper
    # ------------------------------------------------------------------

    @staticmethod
    def normalize_update(update: Any) -> IncomingMessage | None:
        """Convert a Telegram ``Update`` to an :class:`IncomingMessage`.

        Returns ``None`` if the update doesn't carry a user message.
        """
        msg = getattr(update, "message", None) or getattr(update, "effective_message", None)
        if msg is None:
            return None

        user = getattr(update, "effective_user", None)
        chat = getattr(update, "effective_chat", None)
        if user is None or chat is None:
            return None

        return IncomingMessage(
            id=str(msg.message_id),
            channel=ChannelIdentity(
                channel_type="telegram",
                channel_id=str(chat.id),
                user_id=str(user.id),
                user_display_name=user.first_name or user.username or str(user.id),
                is_group=chat.type in ("group", "supergroup"),
            ),
            text=msg.text or msg.caption or "",
            timestamp=msg.date.timestamp() if msg.date else time.time(),
            reply_to_id=str(msg.reply_to_message.message_id) if msg.reply_to_message else None,
            raw_platform_data=update,
        )

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        return {
            "channel_type": self.channel_type,
            "is_official": self.is_official,
            "status": "running" if self._running else "stopped",
            "agent_id": self._agent_id,
        }
