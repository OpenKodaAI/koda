"""Shared SSE event hub for squad thread updates.

Dashboard clients should not each open their own Postgres LISTEN connection.
This hub keeps one listener per API process and fans events out to bounded
per-client queues. Clients reconnect with a cursor and fetch deltas through
the normal thread endpoint; the hub is only the low-latency push path.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from typing import Any

from koda.logging_config import get_logger

log = get_logger(__name__)


class SquadEventHub:
    def __init__(self, *, dsn: str, channel: str = "squad_thread_events") -> None:
        self._dsn = dsn
        self._channel = channel
        self._conn: Any | None = None
        self._lock = asyncio.Lock()
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}

    async def start(self) -> None:
        if self._conn is not None:
            return
        async with self._lock:
            if self._conn is not None:
                return
            import asyncpg  # type: ignore[import-not-found]

            conn = await asyncpg.connect(self._dsn)
            await conn.add_listener(self._channel, self._on_notify)
            self._conn = conn

    async def stop(self) -> None:
        conn = self._conn
        self._conn = None
        if conn is not None:
            with suppress(Exception):
                await conn.remove_listener(self._channel, self._on_notify)
            with suppress(Exception):
                await conn.close()

    async def subscribe(self, thread_id: str, *, maxsize: int = 128) -> asyncio.Queue[dict[str, Any]]:
        await self.start()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=max(1, int(maxsize)))
        self._subscribers.setdefault(str(thread_id), set()).add(queue)
        return queue

    def unsubscribe(self, thread_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        subscribers = self._subscribers.get(str(thread_id))
        if not subscribers:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(str(thread_id), None)

    def _on_notify(self, _connection: Any, _pid: int, _channel: str, payload: str) -> None:
        try:
            data = json.loads(payload) if payload else {}
        except (json.JSONDecodeError, ValueError):
            return
        if not isinstance(data, dict):
            return
        thread_id = str(data.get("thread_id") or "")
        if not thread_id:
            return
        subscribers = list(self._subscribers.get(thread_id, set()))
        for queue in subscribers:
            try:
                queue.put_nowait(data)
            except asyncio.QueueFull:
                log.warning("squad_event_hub_queue_full", thread_id=thread_id)


_hub: SquadEventHub | None = None


def get_squad_event_hub() -> SquadEventHub | None:
    from koda.config import POSTGRES_URL

    global _hub  # noqa: PLW0603
    if not POSTGRES_URL:
        return None
    if _hub is None:
        _hub = SquadEventHub(dsn=POSTGRES_URL)
    return _hub
