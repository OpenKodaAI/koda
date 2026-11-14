"""``tests.fakes.telegram`` quotes the user's message exactly when PTB would.

``Message.reply_*`` in python-telegram-bot only sends ``reply_parameters``
when the caller asks for it (``do_quote``, ``reply_to_message_id``,
``reply_parameters``) or the chat is not private; Koda sets no
``Defaults(do_quote=...)``. Each case below runs the same reply through a
real PTB ``Message`` and through the fake, and compares the reply target the
bot receives, so an end-to-end test cannot pin a quote that production never
sends.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from telegram import Chat, Message, ReplyParameters

from tests.fakes.telegram import FakeBot, FakeMessage, fake_text_update

_MESSAGE_ID = 7
_CHATS = {
    "private": 4242,
    "group": -4242,
    "supergroup": -1004242,
}
_QUOTE_ARGUMENTS: list[dict[str, Any]] = [
    {},
    {"do_quote": True},
    {"do_quote": False},
    {"reply_to_message_id": 3},
    {"reply_parameters": ReplyParameters(message_id=4)},
]
_QUOTE_IDS = ["default", "do_quote=True", "do_quote=False", "reply_to_message_id", "reply_parameters"]
# Each reply shortcut and the payload it sends.
_REPLIES: dict[str, dict[str, Any]] = {
    "reply_text": {"text": "answer"},
    "reply_document": {"document": b"report", "filename": "report.txt"},
    "reply_voice": {"voice": b"audio"},
}
_SEND_METHOD_BY_KIND = {"text": "send_message", "document": "send_document", "voice": "send_voice"}


class _CapturingBot:
    """Stands in for ``telegram.Bot``: records the send call PTB's shortcut makes."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __getattr__(self, name: str) -> Any:
        if not name.startswith("send_"):
            raise AttributeError(name)

        async def _send(**kwargs: Any) -> None:
            self.calls.append((name, kwargs))

        return _send


async def _ptb_reply_target(chat_type: str, method: str, arguments: dict[str, Any]) -> tuple[str, int | None]:
    bot = _CapturingBot()
    message = Message(
        message_id=_MESSAGE_ID,
        date=dt.datetime.now(dt.UTC),
        chat=Chat(id=_CHATS[chat_type], type=chat_type),
    )
    message.set_bot(bot)  # type: ignore[arg-type]
    await getattr(message, method)(**_REPLIES[method], **arguments)
    [(sent_with, kwargs)] = bot.calls
    reply_parameters = kwargs["reply_parameters"]
    return sent_with, (reply_parameters.message_id if reply_parameters is not None else None)


async def _fake_reply_target(chat_type: str, method: str, arguments: dict[str, Any]) -> tuple[str, int | None]:
    bot = FakeBot()
    update = fake_text_update(bot, user_id=4242, chat_id=_CHATS[chat_type], text="hi", message_id=_MESSAGE_ID)
    sent = await getattr(update.message, method)(**_REPLIES[method], **arguments)
    assert isinstance(sent, FakeMessage)
    assert bot.messages == [sent]
    # Read the target from what the fake bot received, as the PTB side does.
    reply_parameters = sent.kwargs.get("reply_parameters")
    target = reply_parameters.message_id if reply_parameters is not None else sent.kwargs.get("reply_to_message_id")
    return _SEND_METHOD_BY_KIND[sent.kind], target


@pytest.mark.parametrize("arguments", _QUOTE_ARGUMENTS, ids=_QUOTE_IDS)
@pytest.mark.parametrize("method", sorted(_REPLIES))
@pytest.mark.parametrize("chat_type", sorted(_CHATS))
async def test_fake_reply_quotes_the_message_exactly_when_ptb_does(
    chat_type: str, method: str, arguments: dict[str, Any]
) -> None:
    expected = await _ptb_reply_target(chat_type, method, arguments)
    assert await _fake_reply_target(chat_type, method, arguments) == expected


async def test_private_chat_replies_are_plain_messages_by_default() -> None:
    bot = FakeBot()
    update = fake_text_update(bot, user_id=4242, chat_id=4242, text="hi")
    sent = await update.message.reply_text("answer", parse_mode="HTML")
    assert sent.reply_to is None
    assert sent.kwargs["parse_mode"] == "HTML"


@pytest.mark.parametrize(
    ("chat_id", "chat_type"),
    [(4242, "private"), (-4242, "group"), (-1004242, "supergroup")],
)
def test_fake_update_takes_the_chat_type_telegram_uses_for_the_chat_id(chat_id: int, chat_type: str) -> None:
    bot = FakeBot()
    update = fake_text_update(bot, user_id=4242, chat_id=chat_id, text="hi")
    assert update.effective_chat.type == chat_type
    assert update.message.chat_type == chat_type


def test_fake_update_chat_type_can_be_given_explicitly() -> None:
    update = fake_text_update(FakeBot(), user_id=4242, chat_id=-1004242, text="hi", chat_type="channel")
    assert update.effective_chat.type == "channel"
    assert update.message.chat_type == "channel"
