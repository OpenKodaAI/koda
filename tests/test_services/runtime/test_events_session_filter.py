"""Tests for RuntimeEventBroker session_id filtering support."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from koda.services.runtime.events import RuntimeEventBroker


class _FakeStore:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self._next_id = 0
        self._task_sessions: dict[str, list[int]] = {}

    def set_session_tasks(self, session_id: str, task_ids: list[int]) -> None:
        self._task_sessions[session_id] = list(task_ids)

    def add_event(
        self,
        *,
        task_id: int | None,
        env_id: int | None,
        attempt: int | None,
        phase: str | None,
        event_type: str,
        severity: str,
        payload: dict[str, Any] | None = None,
        artifact_refs: list[str] | None = None,
        resource_snapshot_ref: str | None = None,
    ) -> dict[str, Any]:
        self._next_id += 1
        event = {
            "seq": self._next_id,
            "task_id": task_id,
            "env_id": env_id,
            "attempt": attempt,
            "phase": phase,
            "type": event_type,
            "severity": severity,
            "ts": None,
            "payload": dict(payload or {}),
            "artifact_refs": list(artifact_refs or []),
            "resource_snapshot_ref": resource_snapshot_ref,
        }
        self.events.append(event)
        return event

    def list_events(
        self,
        *,
        task_id: int | None = None,
        task_ids: list[int] | None = None,
        env_id: int | None = None,
        after_seq: int = 0,
    ) -> list[dict[str, Any]]:
        if task_ids is not None and not task_ids:
            return []
        rows: list[dict[str, Any]] = []
        for event in self.events:
            if event["seq"] <= after_seq:
                continue
            if task_id is not None and event.get("task_id") != task_id:
                continue
            if task_ids is not None and event.get("task_id") not in set(task_ids):
                continue
            if env_id is not None and event.get("env_id") != env_id:
                continue
            rows.append(event)
        return rows

    def list_task_ids_for_session(self, session_id: str) -> list[int]:
        return list(self._task_sessions.get(session_id, []))


@pytest.mark.asyncio
async def test_iter_events_filters_by_task_ids(tmp_path, monkeypatch):
    monkeypatch.setattr("koda.services.runtime.events.RUNTIME_EVENT_STREAM_ENABLED", True)
    store = _FakeStore()
    broker = RuntimeEventBroker(store=store, runtime_root=tmp_path)

    await broker.publish(task_id=1, env_id=None, attempt=None, phase=None, event_type="t1", severity="info")
    await broker.publish(task_id=2, env_id=None, attempt=None, phase=None, event_type="t2", severity="info")
    await broker.publish(task_id=3, env_id=None, attempt=None, phase=None, event_type="t3", severity="info")

    seen: list[dict[str, Any]] = []
    iterator = broker.iter_events(task_ids={1, 3})

    async def _drain() -> None:
        async for event in iterator:
            seen.append(event)
            if len(seen) >= 2:
                return

    await asyncio.wait_for(_drain(), timeout=1.0)

    types = [event["type"] for event in seen]
    assert types == ["t1", "t3"]


@pytest.mark.asyncio
async def test_iter_events_uses_task_ids_refresh_for_new_tasks(tmp_path, monkeypatch):
    monkeypatch.setattr("koda.services.runtime.events.RUNTIME_EVENT_STREAM_ENABLED", True)
    store = _FakeStore()
    store.set_session_tasks("sess-1", [1])
    broker = RuntimeEventBroker(store=store, runtime_root=tmp_path)

    def refresh() -> set[int]:
        return set(store.list_task_ids_for_session("sess-1"))

    seen: list[dict[str, Any]] = []

    async def _consume() -> None:
        async for event in broker.iter_events(
            task_ids_refresh=refresh,
            task_ids_refresh_interval_s=0.0,
        ):
            seen.append(event)
            if len(seen) >= 2:
                return

    consumer = asyncio.create_task(_consume())
    await asyncio.sleep(0)  # let consumer subscribe

    await broker.publish(
        task_id=1,
        env_id=None,
        attempt=None,
        phase=None,
        event_type="first",
        severity="info",
    )
    await asyncio.sleep(0)

    # New task appears in the same session
    store.set_session_tasks("sess-1", [1, 2])
    await broker.publish(
        task_id=2,
        env_id=None,
        attempt=None,
        phase=None,
        event_type="second",
        severity="info",
    )
    # Unrelated task — must be filtered out
    await broker.publish(
        task_id=99,
        env_id=None,
        attempt=None,
        phase=None,
        event_type="unrelated",
        severity="info",
    )

    await asyncio.wait_for(consumer, timeout=1.0)

    types = [event["type"] for event in seen]
    assert types == ["first", "second"]
