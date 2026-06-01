"""Abstract base class for all channel adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from koda.channels.types import ChannelIdentity, IncomingMessage, OutgoingMessage
from koda.logging_config import get_logger

log = get_logger(__name__)


class ChannelAdapter(ABC):
    """Base contract every messaging-platform adapter must implement.

    Lifecycle:
        1. ``initialize(agent_id, secrets)`` — configure credentials
        2. ``set_message_callback(cb)`` — wire inbound messages to enqueue
        3. ``start()`` — begin listening (polling / websocket / webhook)
        4. ``stop()`` — graceful teardown
    """

    channel_type: str = ""
    """Short key matching the frontend catalog: ``"telegram"``, ``"discord"``, etc."""

    is_official: bool = True
    """``False`` for channels that rely on unofficial / reverse-engineered APIs."""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    async def initialize(self, agent_id: str, secrets: dict[str, str]) -> None:
        """Configure the adapter with agent-scoped credentials."""

    @abstractmethod
    async def start(self) -> None:
        """Start listening for inbound messages."""

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully shut down the listener and release resources."""

    # ------------------------------------------------------------------
    # Outbound
    # ------------------------------------------------------------------

    @abstractmethod
    async def send_text(self, channel: ChannelIdentity, msg: OutgoingMessage) -> str:
        """Send a text message. Returns the platform message ID."""

    @abstractmethod
    async def send_typing(self, channel: ChannelIdentity) -> None:
        """Send a typing / chat-action indicator."""

    @abstractmethod
    async def send_voice(self, channel: ChannelIdentity, path: str, caption: str = "") -> None:
        """Send a voice/audio note."""

    @abstractmethod
    async def send_document(self, channel: ChannelIdentity, path: str, filename: str, caption: str = "") -> None:
        """Send a document/file attachment."""

    @abstractmethod
    async def send_image(self, channel: ChannelIdentity, path: str, caption: str = "") -> None:
        """Send an image."""

    # ------------------------------------------------------------------
    # Inbound callback
    # ------------------------------------------------------------------

    _on_message: Callable[[IncomingMessage], Awaitable[None]] | None = None

    def set_message_callback(self, callback: Callable[[IncomingMessage], Awaitable[None]]) -> None:
        """Register the function that routes inbound messages into the core pipeline."""
        self._on_message = callback

    async def _dispatch_inbound(self, message: IncomingMessage) -> None:
        """Normalize and forward an inbound message to the registered callback."""
        if self._on_message is None:
            log.warning("channel.%s: message received but no callback registered", self.channel_type)
            return
        await self._on_message(message)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        """Return adapter health info for observability."""
        return {
            "channel_type": self.channel_type,
            "is_official": self.is_official,
            "status": "unknown",
        }
