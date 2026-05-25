"""Background scheduler for periodic runbook governance."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from koda.config import RUNBOOK_GOVERNANCE_HOUR
from koda.knowledge.governance import run_runbook_governance
from koda.logging_config import get_logger

log = get_logger(__name__)


def _seconds_until_hour(hour: int) -> float:
    """Calculate seconds until the next occurrence of a local wall-clock hour."""
    now = datetime.now()
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def start_runbook_governance_loop(agent_id: str | None = None) -> None:
    """Run governance once on startup and then daily at the configured hour."""
    log.info("runbook_governance_loop_started", hour=RUNBOOK_GOVERNANCE_HOUR, agent_id=agent_id or "default")
    try:
        await run_runbook_governance(agent_id)
        while True:
            await asyncio.sleep(_seconds_until_hour(RUNBOOK_GOVERNANCE_HOUR))
            try:
                await run_runbook_governance(agent_id)
            except Exception:
                log.exception("runbook_governance_loop_error")
    except asyncio.CancelledError:
        log.info("runbook_governance_loop_cancelled", agent_id=agent_id or "default")
    except Exception:
        log.exception("runbook_governance_loop_fatal")
