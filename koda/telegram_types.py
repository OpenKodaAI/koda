"""Shared Telegram typing aliases for strict mypy checks."""

from __future__ import annotations

from typing import Any, Protocol, TypeAlias

from telegram import CallbackQuery, Chat, Message, User
from telegram import Update as TelegramUpdate
from telegram.ext import ExtBot

UserData: TypeAlias = dict[str, Any]
ChatData: TypeAlias = dict[Any, Any]


class BotContext(Protocol):
    """Minimal PTB context surface used across the runtime."""

    @property
    def bot(self) -> ExtBot[None]: ...

    @property
    def user_data(self) -> UserData: ...

    @property
    def args(self) -> list[str]: ...


class MessageUpdate(TelegramUpdate):
    """Telegram update shape for command and message handlers with message access."""

    message: Message
    effective_message: Message
    effective_user: User
    effective_chat: Chat


class CallbackUpdate(TelegramUpdate):
    """Telegram update shape for callback handlers with callback access."""

    callback_query: CallbackQuery
    effective_message: Message
    effective_user: User
    effective_chat: Chat
