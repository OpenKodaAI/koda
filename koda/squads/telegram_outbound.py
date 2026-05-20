"""Squad outbound — posting agent replies into bound Telegram forum topics.

Wraps ``bot.send_message`` with the squad-specific ``message_thread_id``
override and an optional ``[Agent Name]`` prefix so a thread transcript stays
legible when multiple agents reply. Designed to be called from a tool handler
(``squad_telegram_post``) and, later, from the queue manager's response
delivery path when a turn is squad-scoped.
"""

from __future__ import annotations

import asyncio
import html
from typing import Any

from telegram.error import RetryAfter

from koda.config import SQUAD_DEBOUNCE_MS
from koda.logging_config import get_logger
from koda.squads.threads import ThreadDescriptor

log = get_logger(__name__)

_TELEGRAM_MAX_TEXT = 4096
_BOT_CACHE: dict[str, Any] = {}
_BUFFERS: dict[tuple[int, int, int | None], _OutboundBuffer] = {}


class _OutboundBuffer:
    def __init__(self, bot: Any, chat_id: int, message_thread_id: int | None) -> None:
        self.bot = bot
        self.chat_id = chat_id
        self.message_thread_id = message_thread_id
        self.items: list[tuple[str | None, str, str | None, Any | None]] = []
        self.task: asyncio.Task[None] | None = None
        self.lock = asyncio.Lock()

    async def add(
        self,
        *,
        agent_label: str | None,
        text: str,
        parse_mode: str | None,
        reply_markup: Any | None,
    ) -> None:
        async with self.lock:
            self.items.append((agent_label, text, parse_mode, reply_markup))
            if self.task is None or self.task.done():
                self.task = asyncio.create_task(self._flush_later())

    async def _flush_later(self) -> None:
        await asyncio.sleep(max(0, SQUAD_DEBOUNCE_MS) / 1000)
        async with self.lock:
            items = list(self.items)
            self.items.clear()
        if not items:
            return
        parse_mode = next((item[2] for item in reversed(items) if item[2]), None)
        reply_markup = next((item[3] for item in reversed(items) if item[3] is not None), None)
        combined = _combine_items(items, parse_mode=parse_mode)
        for index, chunk in enumerate(_split_telegram_text(combined)):
            kwargs: dict[str, Any] = {
                "chat_id": self.chat_id,
                "text": chunk,
            }
            if self.message_thread_id is not None:
                kwargs["message_thread_id"] = self.message_thread_id
            if parse_mode:
                kwargs["parse_mode"] = parse_mode
            if index == 0 and reply_markup is not None:
                kwargs["reply_markup"] = reply_markup
            await _send_with_retry(self.bot, kwargs)


def _split_telegram_text(text: str) -> list[str]:
    try:
        from koda.utils.messaging import split_message

        return split_message(text)
    except Exception:
        if len(text) <= _TELEGRAM_MAX_TEXT:
            return [text]
        chunks: list[str] = []
        start = 0
        while start < len(text):
            chunks.append(text[start : start + _TELEGRAM_MAX_TEXT])
            start += _TELEGRAM_MAX_TEXT
        return chunks


def _combine_items(items: list[tuple[str | None, str, str | None, Any | None]], *, parse_mode: str | None) -> str:
    if len(items) == 1:
        label, text, _mode, _markup = items[0]
        return _prefix_text(text, agent_label=label)
    sections: list[str] = []
    html_mode = str(parse_mode or "").upper() == "HTML"
    for label, text, _mode, _markup in items:
        if label:
            header = html.escape(label) if html_mode else label
            sections.append(f"<b>{header}</b>\n{text}" if html_mode else f"[{header}]\n{text}")
        else:
            sections.append(text)
    return "\n\n".join(section.strip() for section in sections if section.strip())


async def _send_with_retry(bot: Any, kwargs: dict[str, Any]) -> Any:
    try:
        return await bot.send_message(**kwargs)
    except RetryAfter as exc:
        delay = float(getattr(exc, "retry_after", 1.0) or 1.0)
        await asyncio.sleep(max(0.1, delay))
        return await bot.send_message(**kwargs)


def get_outbound_bot(token: str) -> Any:
    """Return a process-cached ``telegram.Bot`` for ``token``.

    Tools call this when a ``ToolContext.bot`` is not available (the runtime
    that owns the queue passes its bot through context; out-of-band callers
    such as scheduled jobs reuse this cached instance instead of paying the
    httpx client construction cost on every call.
    """
    cached = _BOT_CACHE.get(token)
    if cached is not None:
        return cached
    from telegram import Bot

    bot = Bot(token=token)
    _BOT_CACHE[token] = bot
    return bot


def _prefix_text(text: str, *, agent_label: str | None) -> str:
    if not agent_label:
        return text
    label = agent_label.strip()
    if not label:
        return text
    return f"[{label}] {text}"


async def post_to_thread(
    bot: Any,
    thread: ThreadDescriptor,
    text: str,
    *,
    agent_label: str | None = None,
    parse_mode: str | None = None,
) -> Any:
    """Send ``text`` into the Telegram topic linked to ``thread``.

    The thread must already carry ``telegram_chat_id``; ``message_thread_id``
    is forwarded only when present (chats without forum topics fall back to
    the General topic). Returns the resulting Telegram ``Message`` object.
    Raises ``ValueError`` when the thread has no telegram binding.
    """
    if thread.telegram_chat_id is None:
        raise ValueError(f"thread {thread.id!r} is not bound to a telegram chat")
    body = _prefix_text(text, agent_label=agent_label)
    if len(body) > _TELEGRAM_MAX_TEXT:
        body = body[: _TELEGRAM_MAX_TEXT - 1] + "…"
    kwargs: dict[str, Any] = {
        "chat_id": thread.telegram_chat_id,
        "text": body,
    }
    if thread.telegram_message_thread_id is not None:
        kwargs["message_thread_id"] = thread.telegram_message_thread_id
    if parse_mode is not None:
        kwargs["parse_mode"] = parse_mode
    return await bot.send_message(**kwargs)


async def post_to_topic_buffered(
    bot: Any,
    *,
    chat_id: int,
    message_thread_id: int | None,
    text: str,
    agent_label: str | None = None,
    parse_mode: str | None = None,
    reply_markup: Any | None = None,
) -> None:
    key = (id(bot), int(chat_id), int(message_thread_id) if message_thread_id is not None else None)
    buffer = _BUFFERS.get(key)
    if buffer is None:
        buffer = _OutboundBuffer(bot, int(chat_id), int(message_thread_id) if message_thread_id is not None else None)
        _BUFFERS[key] = buffer
    await buffer.add(
        agent_label=agent_label,
        text=text,
        parse_mode=parse_mode,
        reply_markup=reply_markup,
    )
