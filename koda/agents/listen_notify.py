"""Asyncpg LISTEN/NOTIFY helper for the inter-agent message bus.

Owns a dedicated long-lived connection that holds LISTEN on a single channel
and dispatches each NOTIFY payload to a callback. Reconnects with backoff if
the connection drops; safe to start/stop multiple times.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Coroutine
from contextlib import suppress
from typing import Any

from koda.logging_config import get_logger

log = get_logger(__name__)

NotifyCallback = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class AgentInboxListener:
    def __init__(
        self,
        dsn: str,
        channel: str,
        callback: NotifyCallback,
        *,
        reconnect_delay: float = 5.0,
    ) -> None:
        self._dsn = dsn
        self._channel = channel
        self._callback = callback
        self._reconnect_delay = max(0.1, float(reconnect_delay))
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()
        self._conn: Any | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def is_connected(self) -> bool:
        return self._conn is not None and not self._conn.is_closed()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stopping.clear()
        self._loop = asyncio.get_running_loop()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopping.set()
        conn = self._conn
        self._conn = None
        if conn is not None:
            with suppress(Exception):
                await conn.close()
        task = self._task
        self._task = None
        if task is not None:
            try:
                await asyncio.wait_for(task, timeout=2.0)
            except (TimeoutError, asyncio.CancelledError):
                task.cancel()

    async def _run(self) -> None:
        import asyncpg  # type: ignore[import-not-found]

        loop = self._loop or asyncio.get_running_loop()

        def _on_notify(connection: Any, pid: int, channel: str, payload: str) -> None:
            try:
                data = json.loads(payload) if payload else {}
            except (json.JSONDecodeError, ValueError):
                log.warning("listen_notify_invalid_payload", channel=channel, payload=payload[:200])
                return
            loop.create_task(self._callback(data))

        while not self._stopping.is_set():
            try:
                self._conn = await asyncpg.connect(self._dsn)
                await self._conn.add_listener(self._channel, _on_notify)
                while not self._stopping.is_set() and not self._conn.is_closed():
                    await asyncio.sleep(0.5)
            except Exception:
                log.exception("listen_notify_loop_error", channel=self._channel)
            finally:
                conn = self._conn
                self._conn = None
                if conn is not None:
                    with suppress(Exception):
                        await conn.remove_listener(self._channel, _on_notify)
                    with suppress(Exception):
                        await conn.close()
            if not self._stopping.is_set():
                with suppress(TimeoutError):
                    await asyncio.wait_for(self._stopping.wait(), timeout=self._reconnect_delay)
