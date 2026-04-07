"""Multi-channel messaging abstraction layer.

This package provides a unified interface for connecting Koda agents
to multiple messaging platforms (Telegram, WhatsApp, Discord, Slack, etc.).
"""

from koda.channels.base import ChannelAdapter
from koda.channels.bridge import MessageBridge, TelegramMessageBridge
from koda.channels.types import ChannelIdentity, IncomingMessage, OutgoingMessage

__all__ = [
    "ChannelAdapter",
    "ChannelIdentity",
    "IncomingMessage",
    "MessageBridge",
    "OutgoingMessage",
    "TelegramMessageBridge",
]
