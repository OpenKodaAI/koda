"""Persistent runtime event broker."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any, cast

from koda.config import RUNTIME_EVENT_STREAM_ENABLED
from koda.services.runtime.store import RuntimeStore


class RuntimeEventBroker:
    """Persist and fan out runtime events."""

    def __init__(self, store: RuntimeStore, runtime_root: Path) -> None:
        self.store = store
        self.runtime_root = runtime_root
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    def _append_event_log(self, event: dict[str, Any]) -> None:
        task_id = event.get("task_id")
        if not task_id:
            return
        task_dir = self.runtime_root / "tasks" / str(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        events_path = task_dir / "events.ndjson"
        with events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")

    async def publish(
        self,
        *,
        task_id: int | None,
        env_id: int | None,
        attempt: int | None,
        phase: str | None,
        event_type: str,
        severity: str = "info",
        payload: dict[str, Any] | None = None,
        artifact_refs: list[str] | None = None,
        resource_snapshot_ref: str | None = None,
    ) -> dict[str, Any]:
        event = cast(
            dict[str, Any],
            self.store.add_event(
                task_id=task_id,
                env_id=env_id,
                attempt=attempt,
                phase=phase,
                event_type=event_type,
                severity=severity,
                payload=payload,
                artifact_refs=artifact_refs,
                resource_snapshot_ref=resource_snapshot_ref,
            ),
        )
        self._append_event_log(event)
        if RUNTIME_EVENT_STREAM_ENABLED:
            for queue in list(self._subscribers):
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    continue
        return event

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    async def iter_events(
        self,
        *,
        task_id: int | None = None,
        task_ids: set[int] | None = None,
        task_ids_refresh: Callable[[], set[int]] | None = None,
        task_ids_refresh_interval_s: float = 5.0,
        env_id: int | None = None,
        after_seq: int = 0,
    ) -> AsyncIterator[dict[str, Any]]:
        current_task_ids: set[int] | None = task_ids
        loop = asyncio.get_running_loop()
        if task_ids_refresh is not None:
            current_task_ids = task_ids_refresh()
        last_refresh = loop.time()
        for event in cast(
            list[dict[str, Any]],
            self.store.list_events(
                task_id=task_id,
                task_ids=list(current_task_ids) if current_task_ids is not None else None,
                env_id=env_id,
                after_seq=after_seq,
            ),
        ):
            yield event
        queue = self.subscribe()
        try:
            while True:
                event = await queue.get()
                if task_ids_refresh is not None:
                    now = loop.time()
                    if now - last_refresh >= task_ids_refresh_interval_s:
                        current_task_ids = task_ids_refresh()
                        last_refresh = now
                if task_id is not None and event.get("task_id") != task_id:
                    continue
                if current_task_ids is not None and event.get("task_id") not in current_task_ids:
                    continue
                if env_id is not None and event.get("env_id") != env_id:
                    continue
                if event.get("seq", 0) <= after_seq:
                    continue
                yield event
        finally:
            self.unsubscribe(queue)
