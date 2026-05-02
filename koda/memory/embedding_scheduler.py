"""Background worker that drains the embedding repair queue."""

from __future__ import annotations

import asyncio

from koda.logging_config import get_logger
from koda.memory.config import (
    MEMORY_EMBEDDING_REPAIR_BATCH_SIZE,
    MEMORY_EMBEDDING_REPAIR_INTERVAL_SECONDS,
)
from koda.memory.embedding_queue import get_embedding_job_stats
from koda.memory.store import MemoryStore

log = get_logger(__name__)


def _publish_queue_metrics(agent_id: str) -> None:
    try:
        from koda.services import metrics

        for status, count in get_embedding_job_stats(agent_id).items():
            metrics.MEMORY_EMBEDDING_QUEUE.labels(agent_id=agent_id, status=status).set(count)
    except Exception:
        log.debug("embedding_repair_metrics_publish_error", exc_info=True)


async def _publish_queue_metrics_async(agent_id: str) -> None:
    """Publish queue metrics without blocking the running event loop.

    ``_publish_queue_metrics`` is sync and reaches Postgres through
    ``run_coro_sync``, which dispatches to the cross-thread bridge loop and
    then waits on ``future.result()`` — that wait happens on the *calling*
    thread. When the caller is itself an asyncio task on the main event
    loop, the wait deadlocks the loop: the bridge thread can run, but every
    other asyncio task (including the bot's ``run_polling``) is frozen
    until the future resolves. Pushing the sync call to the default
    ``ThreadPoolExecutor`` lets the loop keep ticking.
    """
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _publish_queue_metrics, agent_id)


async def start_embedding_repair_loop(store: MemoryStore) -> None:
    """Continuously drain persisted embedding repair jobs."""
    log.info(
        "embedding_repair_loop_started",
        interval_seconds=MEMORY_EMBEDDING_REPAIR_INTERVAL_SECONDS,
        batch_size=MEMORY_EMBEDDING_REPAIR_BATCH_SIZE,
    )
    try:
        await _publish_queue_metrics_async(store.agent_id)
        await store.repair_pending_embeddings(limit=MEMORY_EMBEDDING_REPAIR_BATCH_SIZE)
        await _publish_queue_metrics_async(store.agent_id)
        while True:
            await asyncio.sleep(MEMORY_EMBEDDING_REPAIR_INTERVAL_SECONDS)
            try:
                await store.repair_pending_embeddings(limit=MEMORY_EMBEDDING_REPAIR_BATCH_SIZE)
                await _publish_queue_metrics_async(store.agent_id)
            except Exception:
                log.exception("embedding_repair_loop_error")
    except asyncio.CancelledError:
        log.info("embedding_repair_loop_cancelled")
    except Exception:
        log.exception("embedding_repair_loop_fatal")
