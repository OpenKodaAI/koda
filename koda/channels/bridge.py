"""MessageBridge protocol — abstracts response delivery from platform specifics.

The bridge sits between ``queue_manager`` orchestration and the actual
platform SDK calls so that the queue code never touches Telegram (or any
other platform) objects directly.

**Integration status:** The bridge infrastructure is complete and ready.
The next step is to wire it into ``queue_manager.py`` by:

1. Replacing the ~20 direct ``context.bot.send_*`` / ``update.message.reply_*``
   call sites with ``bridge.send_text()`` / ``bridge.reply_text()`` etc.
2. Changing ``enqueue()`` signature to accept ``IncomingMessage`` + ``MessageBridge``
   instead of Telegram's ``Update`` + ``BotContext``.
3. Updating ``QueueItem`` to store ``IncomingMessage`` instead of ``Update``.

This is an incremental refactor that preserves existing Telegram behavior
via ``TelegramMessageBridge`` while enabling non-Telegram channels to route
through the same orchestration pipeline via ``AdapterMessageBridge``.
"""

from __future__ import annotations

from typing import Any, Protocol

from koda.channels.types import ChannelIdentity, OutgoingMessage
from koda.logging_config import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Protocol (structural subtyping — no inheritance required)
# ---------------------------------------------------------------------------


class MessageBridge(Protocol):
    """Minimal I/O surface that queue_manager uses to deliver responses."""

    async def send_text(self, chat_id: int | str, text: str, **kwargs: Any) -> Any:
        """Send a text message to *chat_id*."""
        ...

    async def reply_text(self, text: str, **kwargs: Any) -> Any:
        """Reply to the original inbound message with *text*."""
        ...

    async def send_typing(self, chat_id: int | str) -> None:
        """Show a typing indicator in *chat_id*."""
        ...

    async def send_voice(self, chat_id: int | str, voice: Any, caption: str = "", **kwargs: Any) -> Any:
        """Send a voice note to *chat_id*."""
        ...

    async def send_document(
        self, chat_id: int | str, document: Any, filename: str = "", caption: str = "", **kwargs: Any
    ) -> Any:
        """Send a document attachment to *chat_id*."""
        ...

    async def send_photo(self, chat_id: int | str, photo: Any, caption: str = "", **kwargs: Any) -> Any:
        """Send a photo to *chat_id*."""
        ...


# ---------------------------------------------------------------------------
# Telegram implementation (wraps the existing context.bot / update.message)
# ---------------------------------------------------------------------------


class TelegramMessageBridge:
    """Wraps ``context.bot`` and ``update.message`` behind :class:`MessageBridge`.

    This is the **zero-change** shim — every method delegates to the same
    Telegram SDK calls that were previously made inline in queue_manager.
    """

    def __init__(self, bot: Any, message: Any | None = None) -> None:
        self._bot = bot
        self._message = message

    # -- text --------------------------------------------------------------

    async def send_text(self, chat_id: int | str, text: str, **kwargs: Any) -> Any:
        return await self._bot.send_message(chat_id=chat_id, text=text, **kwargs)

    async def reply_text(self, text: str, **kwargs: Any) -> Any:
        if self._message is not None:
            return await self._message.reply_text(text, **kwargs)
        log.warning("TelegramMessageBridge.reply_text called without a message reference")
        return None

    # -- typing ------------------------------------------------------------

    async def send_typing(self, chat_id: int | str) -> None:
        from telegram.constants import ChatAction

        await self._bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    # -- media -------------------------------------------------------------

    async def send_voice(self, chat_id: int | str, voice: Any, caption: str = "", **kwargs: Any) -> Any:
        return await self._bot.send_voice(chat_id=chat_id, voice=voice, caption=caption, **kwargs)

    async def send_document(
        self, chat_id: int | str, document: Any, filename: str = "", caption: str = "", **kwargs: Any
    ) -> Any:
        return await self._bot.send_document(
            chat_id=chat_id, document=document, filename=filename, caption=caption, **kwargs
        )

    async def send_photo(self, chat_id: int | str, photo: Any, caption: str = "", **kwargs: Any) -> Any:
        return await self._bot.send_photo(chat_id=chat_id, photo=photo, caption=caption, **kwargs)


# ---------------------------------------------------------------------------
# Generic adapter bridge (routes through ChannelAdapter methods)
# ---------------------------------------------------------------------------


class AdapterMessageBridge:
    """Routes :class:`MessageBridge` calls through a :class:`ChannelAdapter`.

    Used by non-Telegram channels so queue_manager can use the same
    ``bridge.send_text(chat_id, text)`` interface.
    """

    def __init__(self, adapter: Any, channel: ChannelIdentity) -> None:
        from koda.channels.base import ChannelAdapter

        self._adapter: ChannelAdapter = adapter
        self._channel = channel

    async def send_text(self, chat_id: int | str, text: str, **kwargs: Any) -> Any:
        msg = OutgoingMessage(text=text, parse_mode=kwargs.get("parse_mode", "html"))
        return await self._adapter.send_text(self._channel, msg)

    async def reply_text(self, text: str, **kwargs: Any) -> Any:
        return await self.send_text(self._channel.channel_id, text, **kwargs)

    async def send_typing(self, chat_id: int | str) -> None:
        await self._adapter.send_typing(self._channel)

    async def send_voice(self, chat_id: int | str, voice: Any, caption: str = "", **kwargs: Any) -> Any:
        path = str(voice) if not isinstance(voice, str) else voice
        await self._adapter.send_voice(self._channel, path, caption)

    async def send_document(
        self, chat_id: int | str, document: Any, filename: str = "", caption: str = "", **kwargs: Any
    ) -> Any:
        path = str(document) if not isinstance(document, str) else document
        await self._adapter.send_document(self._channel, path, filename, caption)

    async def send_photo(self, chat_id: int | str, photo: Any, caption: str = "", **kwargs: Any) -> Any:
        path = str(photo) if not isinstance(photo, str) else photo
        await self._adapter.send_image(self._channel, path, caption)
