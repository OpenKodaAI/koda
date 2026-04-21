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


async def start_embedding_repair_loop(store: MemoryStore) -> None:
    """Continuously drain persisted embedding repair jobs."""
    log.info(
        "embedding_repair_loop_started",
        interval_seconds=MEMORY_EMBEDDING_REPAIR_INTERVAL_SECONDS,
        batch_size=MEMORY_EMBEDDING_REPAIR_BATCH_SIZE,
    )
    try:
        _publish_queue_metrics(store.agent_id)
        await store.repair_pending_embeddings(limit=MEMORY_EMBEDDING_REPAIR_BATCH_SIZE)
        _publish_queue_metrics(store.agent_id)
        while True:
            await asyncio.sleep(MEMORY_EMBEDDING_REPAIR_INTERVAL_SECONDS)
            try:
                await store.repair_pending_embeddings(limit=MEMORY_EMBEDDING_REPAIR_BATCH_SIZE)
                _publish_queue_metrics(store.agent_id)
            except Exception:
                log.exception("embedding_repair_loop_error")
    except asyncio.CancelledError:
        log.info("embedding_repair_loop_cancelled")
    except Exception:
        log.exception("embedding_repair_loop_fatal")
