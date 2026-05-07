"""Best-effort supervision for post-response memory extraction tasks."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import Any

from koda.logging_config import get_logger
from koda.memory.quality import record_memory_quality_counter

log = get_logger(__name__)


class MemoryExtractionSupervisor:
    """Run bounded one-shot extraction jobs without delaying user responses."""

    def __init__(self, *, max_concurrency: int = 2) -> None:
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self._tasks: set[asyncio.Task[None]] = set()

    def submit(
        self,
        job_factory: Callable[[], Awaitable[None]],
        *,
        agent_id: str | None = None,
        user_id: int | None = None,
        task_id: int | None = None,
    ) -> None:
        task = asyncio.create_task(
            self._run(job_factory, agent_id=agent_id, user_id=user_id, task_id=task_id),
            name="memory-extraction",
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def drain(self, *, timeout: float = 2.0) -> None:
        tasks = [task for task in self._tasks if not task.done()]
        if not tasks:
            return
        done, pending = await asyncio.wait(tasks, timeout=max(0.0, timeout))
        for task in done:
            with contextlib.suppress(Exception, asyncio.CancelledError):
                task.result()
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    async def _run(
        self,
        job_factory: Callable[[], Awaitable[None]],
        *,
        agent_id: str | None,
        user_id: int | None,
        task_id: int | None,
    ) -> None:
        async with self._semaphore:
            try:
                await job_factory()
            except asyncio.CancelledError:
                record_memory_quality_counter(agent_id, "extraction_background", "cancelled")
                log.info("memory_extraction_cancelled", agent_id=agent_id, user_id=user_id, task_id=task_id)
                raise
            except Exception:
                record_memory_quality_counter(agent_id, "extraction_background", "failed")
                log.exception("memory_extraction_failed", agent_id=agent_id, user_id=user_id, task_id=task_id)

    def snapshot(self) -> dict[str, Any]:
        pending = sum(1 for task in self._tasks if not task.done())
        return {"pending": pending}


_SUPERVISOR = MemoryExtractionSupervisor()


def get_memory_extraction_supervisor() -> MemoryExtractionSupervisor:
    return _SUPERVISOR
