"""Unified message types shared across all channel adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ChannelIdentity:
    """Platform-agnostic identification of a conversation endpoint."""

    channel_type: str
    """Adapter key: ``"telegram"``, ``"discord"``, ``"whatsapp"``, etc."""

    channel_id: str
    """Platform-specific chat / conversation / channel ID (stringified)."""

    user_id: str
    """Platform-specific user ID (stringified)."""

    user_display_name: str
    """Human-readable display name for the sender."""

    is_group: bool = False
    """Whether the message came from a group/multi-party context."""


@dataclass(frozen=True, slots=True)
class IncomingMessage:
    """Normalized inbound message produced by every channel adapter."""

    id: str
    """Platform-specific message ID (stringified)."""

    channel: ChannelIdentity
    """Sender and conversation identification."""

    text: str
    """Plaintext body of the message."""

    timestamp: float
    """Unix epoch seconds when the message was sent."""

    reply_to_id: str | None = None
    """ID of the message being replied to, if any."""

    image_paths: list[str] = field(default_factory=list)
    """Local paths to downloaded image files."""

    document_paths: list[str] = field(default_factory=list)
    """Local paths to downloaded document files."""

    audio_path: str | None = None
    """Local path to a downloaded audio/voice file."""

    raw_platform_data: Any = None
    """Escape hatch for platform-specific payload when needed."""


@dataclass(slots=True)
class OutgoingMessage:
    """Normalized outbound message consumed by every channel adapter."""

    text: str
    """Message body to send."""

    parse_mode: str = "html"
    """Formatting hint: ``"html"``, ``"markdown"``, or ``"plain"``."""

    voice_path: str | None = None
    """Path to a voice/audio file to send."""

    document_path: str | None = None
    """Path to a document file to send."""

    document_filename: str | None = None
    """Display filename for the document."""

    image_path: str | None = None
    """Path to an image file to send."""
