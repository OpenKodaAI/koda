"""Fake Telegram bot, application and update for end-to-end agent-turn tests.

``FakeBot`` records what the runtime sends instead of calling Telegram, and
the messages it returns support the follow-up calls the delivery path makes
(``edit_text``, ``delete``). ``FakeApplication`` has the attributes
``koda.services.queue_manager.build_runtime_context`` reads, and
``fake_text_update`` builds the incoming-message update a Telegram handler
passes to ``enqueue``; its replies go through the same fake bot, as PTB's
``Message.reply_*`` helpers do, and quote the user's message only when PTB
would (``tests/test_fakes_telegram.py`` checks this against PTB itself).
"""

from __future__ import annotations

import itertools
from collections import defaultdict
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from telegram import ReplyParameters


def chat_type_for(chat_id: int) -> str:
    """The chat type Telegram uses for ``chat_id``.

    Private chats have the user's (positive) id, supergroups and channels a
    ``-100`` prefix, and basic groups any other negative id.
    """
    if chat_id > 0:
        return "private"
    return "supergroup" if str(chat_id).startswith("-100") else "group"


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
    chat_type: str = ""

    def __post_init__(self) -> None:
        if not self.chat_type:
            self.chat_type = chat_type_for(self.chat_id)

    @property
    def reply_to(self) -> int | None:
        """The message this one was sent as a reply to, or ``None`` for a plain message."""
        reply_parameters = self.kwargs.get("reply_parameters")
        if reply_parameters is not None:
            return int(reply_parameters.message_id)
        reply_to_message_id = self.kwargs.get("reply_to_message_id")
        return None if reply_to_message_id is None else int(reply_to_message_id)

    async def edit_text(self, text: str, **kwargs: Any) -> FakeMessage:
        self.edits.append(text)
        self.text = text
        return self

    async def delete(self) -> bool:
        return await self.bot.delete_message(chat_id=self.chat_id, message_id=self.message_id)

    def _reply_parameters(
        self,
        do_quote: bool | None,
        reply_to_message_id: int | None,
        reply_parameters: ReplyParameters | None,
    ) -> ReplyParameters | None:
        """PTB 22's ``Message._parse_quote_arguments`` with no ``Defaults(do_quote=...)`` set.

        An explicit target wins; otherwise ``do_quote`` decides; otherwise the
        message is quoted only outside private chats.
        """
        if reply_parameters is not None:
            return reply_parameters
        if reply_to_message_id is not None:
            return ReplyParameters(message_id=reply_to_message_id)
        quote = do_quote if do_quote is not None else self.chat_type != "private"
        return ReplyParameters(message_id=self.message_id) if quote else None

    async def reply_text(
        self,
        text: str,
        *,
        do_quote: bool | None = None,
        reply_to_message_id: int | None = None,
        reply_parameters: ReplyParameters | None = None,
        **kwargs: Any,
    ) -> FakeMessage:
        return await self.bot.send_message(
            chat_id=self.chat_id,
            text=text,
            reply_parameters=self._reply_parameters(do_quote, reply_to_message_id, reply_parameters),
            **kwargs,
        )

    async def reply_document(
        self,
        document: Any = None,
        *,
        do_quote: bool | None = None,
        reply_to_message_id: int | None = None,
        reply_parameters: ReplyParameters | None = None,
        **kwargs: Any,
    ) -> FakeMessage:
        return await self.bot.send_document(
            chat_id=self.chat_id,
            document=document,
            reply_parameters=self._reply_parameters(do_quote, reply_to_message_id, reply_parameters),
            **kwargs,
        )

    async def reply_voice(
        self,
        voice: Any = None,
        *,
        do_quote: bool | None = None,
        reply_to_message_id: int | None = None,
        reply_parameters: ReplyParameters | None = None,
        **kwargs: Any,
    ) -> FakeMessage:
        return await self.bot.send_voice(
            chat_id=self.chat_id,
            voice=voice,
            reply_parameters=self._reply_parameters(do_quote, reply_to_message_id, reply_parameters),
            **kwargs,
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


def fake_text_update(
    bot: FakeBot,
    *,
    user_id: int,
    chat_id: int,
    text: str,
    message_id: int = 1,
    chat_type: str | None = None,
) -> Any:
    """An incoming text message, shaped like the update ``enqueue`` receives.

    The chat type defaults to the one Telegram uses for ``chat_id``
    (``chat_type_for``): a positive id is a private chat.
    """
    resolved_chat_type = chat_type or chat_type_for(chat_id)
    message = FakeMessage(bot=bot, chat_id=chat_id, message_id=message_id, text=text, chat_type=resolved_chat_type)
    return SimpleNamespace(
        update_id=message_id,
        message=message,
        effective_message=message,
        effective_chat=SimpleNamespace(id=chat_id, type=resolved_chat_type),
        effective_user=SimpleNamespace(id=user_id, first_name="Test", username="test_user"),
        callback_query=None,
    )
