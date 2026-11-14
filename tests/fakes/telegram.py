"""Fake Telegram bot, application and update for end-to-end agent-turn tests.

``FakeBot`` records what the runtime sends instead of calling Telegram, and
the messages it returns support the follow-up calls the delivery path makes
(``edit_text``, ``delete``). ``FakeApplication`` has the attributes
``koda.services.queue_manager.build_runtime_context`` reads, and
``fake_text_update`` builds the incoming-message update a Telegram handler
passes to ``enqueue``; its replies go through the same fake bot, as PTB's
``Message.reply_*`` helpers do.
"""

from __future__ import annotations

import itertools
from collections import defaultdict
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any


@dataclass
class FakeMessage:
    """A message sent by the bot or received from a user."""

    bot: FakeBot
    chat_id: int
    message_id: int
    text: str | None = None
    kind: str = "text"
    kwargs: dict[str, Any] = field(default_factory=dict)
    edits: list[str] = field(default_factory=list)
    deleted: bool = False

    async def edit_text(self, text: str, **kwargs: Any) -> FakeMessage:
        self.edits.append(text)
        self.text = text
        return self

    async def delete(self) -> bool:
        return await self.bot.delete_message(chat_id=self.chat_id, message_id=self.message_id)

    async def reply_text(self, text: str, **kwargs: Any) -> FakeMessage:
        return await self.bot.send_message(
            chat_id=self.chat_id, text=text, reply_to_message_id=self.message_id, **kwargs
        )

    async def reply_document(self, document: Any = None, **kwargs: Any) -> FakeMessage:
        return await self.bot.send_document(
            chat_id=self.chat_id, document=document, reply_to_message_id=self.message_id, **kwargs
        )

    async def reply_voice(self, voice: Any = None, **kwargs: Any) -> FakeMessage:
        return await self.bot.send_voice(
            chat_id=self.chat_id, voice=voice, reply_to_message_id=self.message_id, **kwargs
        )


class FakeBot:
    """Records outgoing Telegram calls; every message keeps its later edits and deletion."""

    def __init__(self) -> None:
        self._ids = itertools.count(1000)
        self.messages: list[FakeMessage] = []
        self.chat_actions: list[tuple[int, str]] = []

    def _record(self, chat_id: int, text: str | None, kind: str, kwargs: dict[str, Any]) -> FakeMessage:
        message = FakeMessage(
            bot=self, chat_id=int(chat_id), message_id=next(self._ids), text=text, kind=kind, kwargs=kwargs
        )
        self.messages.append(message)
        return message

    async def send_message(self, chat_id: int, text: str, **kwargs: Any) -> FakeMessage:
        return self._record(chat_id, text, "text", kwargs)

    async def edit_message_text(
        self, text: str, chat_id: int | None = None, message_id: int | None = None, **kwargs: Any
    ) -> FakeMessage | bool:
        for message in self.messages:
            if message.message_id == message_id:
                return await message.edit_text(text, **kwargs)
        return False

    async def delete_message(self, chat_id: int, message_id: int, **_kwargs: Any) -> bool:
        for message in self.messages:
            if message.message_id == message_id:
                message.deleted = True
                return True
        return False

    async def send_chat_action(self, chat_id: int, action: str, **_kwargs: Any) -> bool:
        self.chat_actions.append((int(chat_id), str(action)))
        return True

    async def send_document(self, chat_id: int, document: Any = None, **kwargs: Any) -> FakeMessage:
        return self._record(chat_id, kwargs.get("caption"), "document", kwargs)

    async def send_photo(self, chat_id: int, photo: Any = None, **kwargs: Any) -> FakeMessage:
        return self._record(chat_id, kwargs.get("caption"), "photo", kwargs)

    async def send_voice(self, chat_id: int, voice: Any = None, **kwargs: Any) -> FakeMessage:
        return self._record(chat_id, kwargs.get("caption"), "voice", kwargs)

    def visible(self, chat_id: int | None = None) -> list[FakeMessage]:
        """Messages the user can still see: sent by the bot and not deleted."""
        return [
            message
            for message in self.messages
            if not message.deleted and (chat_id is None or message.chat_id == chat_id)
        ]

    def visible_texts(self, chat_id: int | None = None) -> list[str]:
        return [message.text or "" for message in self.visible(chat_id)]


class FakeApplication:
    """The application surface ``build_runtime_context`` and squad dispatch use.

    ``user_defaults`` seeds each user's ``user_data`` on first access, the way
    earlier commands (``/setdir``, ``/model``) would have left it.
    """

    def __init__(self, bot: FakeBot | None = None, *, user_defaults: dict[str, Any] | None = None) -> None:
        self.bot = bot or FakeBot()
        defaults = dict(user_defaults or {})
        self.user_data: defaultdict[int, dict[str, Any]] = defaultdict(lambda: dict(defaults))
        self.bot_data: dict[str, Any] = {}
        self.job_queue = None


def fake_text_update(bot: FakeBot, *, user_id: int, chat_id: int, text: str, message_id: int = 1) -> Any:
    """An incoming private text message, shaped like the update ``enqueue`` receives."""
    message = FakeMessage(bot=bot, chat_id=chat_id, message_id=message_id, text=text)
    return SimpleNamespace(
        update_id=message_id,
        message=message,
        effective_message=message,
        effective_chat=SimpleNamespace(id=chat_id, type="private"),
        effective_user=SimpleNamespace(id=user_id, first_name="Test", username="test_user"),
        callback_query=None,
    )
