"""Background loop that runs memory maintenance daily."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from koda.logging_config import get_logger
from koda.memory.config import MEMORY_MAINTENANCE_HOUR
from koda.memory.maintenance import run_maintenance
from koda.memory.napkin import get_last_maintenance
from koda.memory.store import MemoryStore

log = get_logger(__name__)


def _seconds_until_hour(hour: int) -> float:
    """Calculate seconds until the next occurrence of the given hour."""
    now = datetime.now()
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def start_maintenance_loop(store: MemoryStore) -> None:
    """Background loop that runs maintenance daily at MEMORY_MAINTENANCE_HOUR.

    On startup: if last maintenance was >24h ago, runs immediately.
    Then loops: sleep until next target hour, run maintenance.
    """
    log.info("maintenance_loop_started", hour=MEMORY_MAINTENANCE_HOUR)

    try:
        # Check if we need to run immediately
        last = get_last_maintenance()
        if last:
            last_dt = datetime.fromisoformat(last)
            hours_since = (datetime.now() - last_dt).total_seconds() / 3600
            if hours_since > 24:
                log.info("maintenance_catchup", hours_since=round(hours_since, 1))
                await run_maintenance(store)
        else:
            # Never ran before — run now
            log.info("maintenance_first_run")
            await run_maintenance(store)

        # Ongoing loop
        while True:
            delay = _seconds_until_hour(MEMORY_MAINTENANCE_HOUR)
            log.info("maintenance_next_run", delay_hours=round(delay / 3600, 1))
            await asyncio.sleep(delay)

            try:
                await run_maintenance(store)
            except Exception:
                log.exception("maintenance_loop_error")

    except asyncio.CancelledError:
        log.info("maintenance_loop_cancelled")
    except Exception:
        log.exception("maintenance_loop_fatal")
