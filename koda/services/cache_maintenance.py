"""Background loop for cache and script library maintenance."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from koda.config import AGENT_ID
from koda.logging_config import get_logger
from koda.services.cache_config import CACHE_CLEANUP_HOUR, CACHE_MAX_ENTRIES_PER_USER
from koda.state.cache_store import (
    cache_cleanup_expired,
    cache_enforce_user_limit,
    cache_get_all_active_user_ids,
)
from koda.state.script_store import script_cleanup_low_quality

log = get_logger(__name__)


def _seconds_until_hour(hour: int) -> float:
    """Calculate seconds until the next occurrence of the given hour."""
    now = datetime.now()
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def _run_cleanup() -> None:
    """Execute all cleanup operations."""
    expired = cache_cleanup_expired(agent_id=AGENT_ID)
    if expired:
        log.info("cache_cleanup_expired", count=expired)

    user_ids = cache_get_all_active_user_ids(agent_id=AGENT_ID)
    total_evicted = 0
    for uid in user_ids:
        evicted = cache_enforce_user_limit(uid, CACHE_MAX_ENTRIES_PER_USER, agent_id=AGENT_ID)
        total_evicted += evicted
    if total_evicted:
        log.info("cache_cleanup_evicted", count=total_evicted)

    low_quality = script_cleanup_low_quality(threshold=0.1, agent_id=AGENT_ID)
    if low_quality:
        log.info("script_cleanup_low_quality", count=low_quality)


async def start_cache_maintenance_loop() -> None:
    """Background loop that runs cache maintenance daily."""
    log.info("cache_maintenance_loop_started", hour=CACHE_CLEANUP_HOUR)

    try:
        # Run once on startup
        await _run_cleanup()

        while True:
            delay = _seconds_until_hour(CACHE_CLEANUP_HOUR)
            log.info("cache_maintenance_next_run", delay_hours=round(delay / 3600, 1))
            await asyncio.sleep(delay)

            try:
                await _run_cleanup()
            except Exception:
                log.exception("cache_maintenance_error")

    except asyncio.CancelledError:
        log.info("cache_maintenance_loop_cancelled")
    except Exception:
        log.exception("cache_maintenance_loop_fatal")
