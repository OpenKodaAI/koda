"""Background loop that sends daily digests to users."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from koda.config import AGENT_ID
from koda.logging_config import get_logger
from koda.memory.digest import build_digest
from koda.memory.digest_store import get_all_enabled, mark_sent

log = get_logger(__name__)

# Check interval: 30 minutes
_CHECK_INTERVAL = 30 * 60


def _current_agent_scope() -> str:
    normalized = (AGENT_ID or "default").strip().lower()
    return normalized or "default"


class _TelegramBotLike(Protocol):
    async def send_message(self, *args: Any, **kwargs: Any) -> Any: ...


async def start_digest_loop(telegram_bot: _TelegramBotLike) -> None:
    """Background loop that checks every 30 minutes which users need a digest.

    Checks immediately on startup (catch-up for missed digests), then
    every _CHECK_INTERVAL seconds. Respects both send_hour and send_minute.
    """
    log.info("digest_loop_started")

    try:
        # Check immediately on startup for missed digests
        await _check_and_send(telegram_bot)

        while True:
            await asyncio.sleep(_CHECK_INTERVAL)
            await _check_and_send(telegram_bot)

    except asyncio.CancelledError:
        log.info("digest_loop_cancelled")
    except Exception:
        log.exception("digest_loop_fatal")


async def _check_and_send(telegram_bot: _TelegramBotLike) -> None:
    """Check all enabled preferences and send digests where due."""
    try:
        preferences = get_all_enabled()
        for user_id, chat_id, _enabled, send_hour, send_minute, timezone_name, last_sent_date in preferences:
            try:
                zone = ZoneInfo(timezone_name or "UTC")
            except ZoneInfoNotFoundError:
                zone = ZoneInfo("UTC")
            now = datetime.now(zone)
            today = now.strftime("%Y-%m-%d")
            current_hour = now.hour
            current_minute = now.minute
            if last_sent_date == today:
                continue
            # Send if we're at or past the configured time
            if current_hour < send_hour:
                continue
            if current_hour == send_hour and current_minute < send_minute:
                continue

            try:
                digest = build_digest(user_id, agent_id=_current_agent_scope())
                if digest:
                    await telegram_bot.send_message(
                        chat_id=chat_id,
                        text=digest,
                        parse_mode="HTML",
                    )
                    log.info("digest_sent", user_id=user_id, chat_id=chat_id)
                mark_sent(user_id, today)
            except Exception:
                log.exception("digest_send_error", user_id=user_id)

    except Exception:
        log.exception("digest_loop_check_error")
