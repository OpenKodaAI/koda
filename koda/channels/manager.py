"""Channel manager — lifecycle orchestration for multi-channel agents.

Each agent process creates one :class:`ChannelManager` that discovers which
channels have credentials stored, instantiates the matching adapters, and
manages their start/stop lifecycle.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from koda.channels.base import ChannelAdapter
from koda.channels.types import IncomingMessage
from koda.logging_config import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Adapter registry — maps channel_type keys to adapter classes
# ---------------------------------------------------------------------------

_ADAPTER_REGISTRY: dict[str, type[ChannelAdapter]] = {}


def register_adapter(channel_type: str, adapter_cls: type[ChannelAdapter]) -> None:
    """Register an adapter class for a channel type."""
    _ADAPTER_REGISTRY[channel_type] = adapter_cls


def _populate_registry() -> None:
    """Lazy-import and register all built-in adapters."""
    if _ADAPTER_REGISTRY:
        return

    # Each import is guarded so missing optional deps don't break startup.
    _safe_register("telegram", "koda.channels.telegram_adapter", "TelegramAdapter")
    _safe_register("whatsapp", "koda.channels.whatsapp_adapter", "WhatsAppAdapter")
    _safe_register("discord", "koda.channels.discord_adapter", "DiscordAdapter")
    _safe_register("slack", "koda.channels.slack_adapter", "SlackAdapter")
    _safe_register("teams", "koda.channels.teams_adapter", "TeamsAdapter")
    _safe_register("line", "koda.channels.line_adapter", "LineAdapter")
    _safe_register("messenger", "koda.channels.messenger_adapter", "MessengerAdapter")
    _safe_register("signal", "koda.channels.signal_adapter", "SignalAdapter")
    _safe_register("instagram", "koda.channels.instagram_adapter", "InstagramAdapter")


def _safe_register(channel_type: str, module_path: str, class_name: str) -> None:
    try:
        import importlib

        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        _ADAPTER_REGISTRY[channel_type] = cls
    except Exception:
        log.debug("channel_adapter.%s: not available (missing dependency or import error)", channel_type)


# ---------------------------------------------------------------------------
# Secret-key mapping — which secrets indicate a channel is configured
# ---------------------------------------------------------------------------

CHANNEL_SECRET_KEYS: dict[str, list[str]] = {
    "telegram": ["AGENT_TOKEN"],
    "whatsapp": ["WHATSAPP_ACCESS_TOKEN", "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_VERIFY_TOKEN", "WHATSAPP_APP_SECRET"],
    "discord": ["DISCORD_BOT_TOKEN"],
    "slack": ["SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "SLACK_SIGNING_SECRET"],
    "teams": ["TEAMS_APP_ID", "TEAMS_APP_PASSWORD"],
    "line": ["LINE_CHANNEL_SECRET", "LINE_CHANNEL_ACCESS_TOKEN"],
    "messenger": ["MESSENGER_PAGE_ACCESS_TOKEN", "MESSENGER_VERIFY_TOKEN", "MESSENGER_APP_SECRET"],
    "signal": ["SIGNAL_PHONE_NUMBER", "SIGNAL_CLI_URL"],
    "instagram": ["INSTAGRAM_PAGE_ACCESS_TOKEN", "INSTAGRAM_APP_SECRET"],
}


def detect_configured_channels(secrets: dict[str, str]) -> list[str]:
    """Return channel types whose required secrets are all present."""
    configured: list[str] = []
    for channel_type, keys in CHANNEL_SECRET_KEYS.items():
        if all(secrets.get(k) for k in keys):
            configured.append(channel_type)
    return configured


# ---------------------------------------------------------------------------
# ChannelManager
# ---------------------------------------------------------------------------


class ChannelManager:
    """Manages all active channel adapters for a single agent process."""

    def __init__(self, agent_id: str) -> None:
        self._agent_id = agent_id
        self._adapters: dict[str, ChannelAdapter] = {}
        self._message_callback: Callable[[IncomingMessage], Awaitable[None]] | None = None
        self._running = False

    @property
    def adapters(self) -> dict[str, ChannelAdapter]:
        return dict(self._adapters)

    def set_message_callback(self, callback: Callable[[IncomingMessage], Awaitable[None]]) -> None:
        """Set the function that routes inbound messages into enqueue()."""
        self._message_callback = callback
        for adapter in self._adapters.values():
            adapter.set_message_callback(callback)

    async def initialize(self, secrets: dict[str, str]) -> None:
        """Discover configured channels and initialize their adapters."""
        _populate_registry()
        configured = detect_configured_channels(secrets)
        log.info(
            "channel_manager.init: agent=%s configured_channels=%s",
            self._agent_id,
            configured,
        )

        for channel_type in configured:
            adapter_cls = _ADAPTER_REGISTRY.get(channel_type)
            if adapter_cls is None:
                log.warning(
                    "channel_manager: no adapter for %s (dependency not installed?)",
                    channel_type,
                )
                continue

            adapter = adapter_cls()
            try:
                await adapter.initialize(self._agent_id, secrets)
                if self._message_callback:
                    adapter.set_message_callback(self._message_callback)
                self._adapters[channel_type] = adapter
                log.info("channel_manager.adapter_ready: %s", channel_type)
            except Exception:
                log.exception("channel_manager.init_failed: %s", channel_type)

    async def start_all(self) -> None:
        """Start all initialized adapters concurrently."""
        if not self._adapters:
            return
        self._running = True
        start_tasks = []
        for channel_type, adapter in self._adapters.items():
            start_tasks.append(self._start_one(channel_type, adapter))
        await asyncio.gather(*start_tasks, return_exceptions=True)

    async def _start_one(self, channel_type: str, adapter: ChannelAdapter) -> None:
        try:
            await adapter.start()
            log.info("channel_manager.started: %s", channel_type)
        except Exception:
            log.exception("channel_manager.start_failed: %s", channel_type)

    async def stop_all(self) -> None:
        """Gracefully stop all running adapters."""
        self._running = False
        stop_tasks = []
        for channel_type, adapter in self._adapters.items():
            stop_tasks.append(self._stop_one(channel_type, adapter))
        await asyncio.gather(*stop_tasks, return_exceptions=True)
        self._adapters.clear()

    async def _stop_one(self, channel_type: str, adapter: ChannelAdapter) -> None:
        try:
            await adapter.stop()
            log.info("channel_manager.stopped: %s", channel_type)
        except Exception:
            log.exception("channel_manager.stop_failed: %s", channel_type)

    def get_adapter(self, channel_type: str) -> ChannelAdapter | None:
        return self._adapters.get(channel_type)

    def health(self) -> dict[str, Any]:
        return {
            "agent_id": self._agent_id,
            "running": self._running,
            "channels": {k: v.health() for k, v in self._adapters.items()},
        }
