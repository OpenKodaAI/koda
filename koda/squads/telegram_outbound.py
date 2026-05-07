"""Squad outbound — posting agent replies into bound Telegram forum topics.

Wraps ``bot.send_message`` with the squad-specific ``message_thread_id``
override and an optional ``[Agent Name]`` prefix so a thread transcript stays
legible when multiple agents reply. Designed to be called from a tool handler
(``squad_telegram_post``) and, later, from the queue manager's response
delivery path when a turn is squad-scoped.
"""

from __future__ import annotations

from typing import Any

from koda.logging_config import get_logger
from koda.squads.threads import ThreadDescriptor

log = get_logger(__name__)

_TELEGRAM_MAX_TEXT = 4096
_BOT_CACHE: dict[str, Any] = {}


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
