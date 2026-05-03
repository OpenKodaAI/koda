"""Pure-logic tests for koda.services.runtime.events.RuntimeEventBroker.

The broker is the streaming spine: every dispatcher tick, terminal byte,
browser screenshot, and tool call traverses publish() → subscribers → web UI.
We test it against an in-memory fake store + a tmp_path filesystem so the
NDJSON append path is exercised end-to-end.

Pinned semantics:

  * publish() returns the persisted event (delegated to store.add_event)
  * NDJSON file appended at {runtime_root}/tasks/{task_id}/events.ndjson
  * Subscribers receive the SAME dict the store returned
  * Dropping happens silently when a subscriber queue is full (asyncio.QueueFull)
  * Slow subscribers do NOT block the publisher
  * iter_events() backfills via store.list_events then attaches a live queue
  * iter_events() filter rules: task_id / task_ids / env_id / after_seq
  * unsubscribe() removes the queue from the broker set
  * If RUNTIME_EVENT_STREAM_ENABLED is False, fan-out is skipped (only persistence)
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from koda.services.runtime.events import RuntimeEventBroker


class _FakeStore:
    """In-memory RuntimeStore stand-in for event-broker tests."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self._next_seq = 1

    def add_event(
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
        event = {
            "seq": self._next_seq,
            "task_id": task_id,
            "env_id": env_id,
            "attempt": attempt,
            "phase": phase,
            "event_type": event_type,
            "severity": severity,
            "payload": dict(payload or {}),
            "artifact_refs": list(artifact_refs or []),
            "resource_snapshot_ref": resource_snapshot_ref,
        }
        self._next_seq += 1
        self.events.append(event)
        return dict(event)

    def list_events(
        self,
        *,
        task_id: int | None = None,
        task_ids: list[int] | None = None,
        env_id: int | None = None,
        after_seq: int = 0,
    ) -> list[dict[str, Any]]:
        out = []
        for e in self.events:
            if e["seq"] <= after_seq:
                continue
            if task_id is not None and e["task_id"] != task_id:
                continue
            if task_ids is not None and e["task_id"] not in task_ids:
                continue
            if env_id is not None and e["env_id"] != env_id:
                continue
            out.append(dict(e))
        return out


@pytest.fixture
def broker_factory(tmp_path: Path):
    """Return a callable that builds (broker, store) sharing tmp_path."""

    def make() -> tuple[RuntimeEventBroker, _FakeStore]:
        store = _FakeStore()
        broker = RuntimeEventBroker(store=store, runtime_root=tmp_path)  # type: ignore[arg-type]
        return broker, store

    return make


# ---------------------------------------------------------------------------
# publish() persistence + NDJSON
# ---------------------------------------------------------------------------


async def test_publish_returns_event_dict(broker_factory) -> None:
    broker, _ = broker_factory()
    event = await broker.publish(
        task_id=42,
        env_id=7,
        attempt=1,
        phase="executing",
        event_type="command.started",
        payload={"cmd": "ls"},
    )
    assert event["task_id"] == 42
    assert event["event_type"] == "command.started"
    assert event["payload"] == {"cmd": "ls"}
    assert event["seq"] == 1


async def test_publish_persists_to_store(broker_factory) -> None:
    broker, store = broker_factory()
    await broker.publish(task_id=1, env_id=1, attempt=1, phase="x", event_type="a")
    await broker.publish(task_id=1, env_id=1, attempt=1, phase="x", event_type="b")
    assert [e["event_type"] for e in store.events] == ["a", "b"]
    assert [e["seq"] for e in store.events] == [1, 2]


async def test_publish_appends_ndjson_file(broker_factory, tmp_path: Path) -> None:
    broker, _ = broker_factory()
    await broker.publish(
        task_id=99,
        env_id=1,
        attempt=1,
        phase="executing",
        event_type="command.started",
        payload={"cmd": "echo hi"},
    )
    ndjson_path = tmp_path / "tasks" / "99" / "events.ndjson"
    assert ndjson_path.exists(), "events.ndjson should be created"
    lines = ndjson_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["event_type"] == "command.started"
    assert parsed["payload"] == {"cmd": "echo hi"}


async def test_publish_appends_multiple_lines(broker_factory, tmp_path: Path) -> None:
    broker, _ = broker_factory()
    for i in range(5):
        await broker.publish(
            task_id=7, env_id=1, attempt=1, phase="x", event_type="t", payload={"i": i}
        )
    ndjson_path = tmp_path / "tasks" / "7" / "events.ndjson"
    lines = ndjson_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 5
    payloads = [json.loads(line)["payload"]["i"] for line in lines]
    assert payloads == [0, 1, 2, 3, 4]


async def test_publish_without_task_id_skips_ndjson(broker_factory, tmp_path: Path) -> None:
    """When task_id is None, no per-task NDJSON file is opened."""
    broker, _ = broker_factory()
    await broker.publish(task_id=None, env_id=None, attempt=None, phase=None, event_type="system")
    # No tasks dir created.
    assert not (tmp_path / "tasks").exists()


async def test_publish_isolates_files_per_task(broker_factory, tmp_path: Path) -> None:
    """Each task_id gets its own events.ndjson — no cross-task append leakage."""
    broker, _ = broker_factory()
    await broker.publish(task_id=1, env_id=1, attempt=1, phase="x", event_type="a")
    await broker.publish(task_id=2, env_id=1, attempt=1, phase="x", event_type="b")
    assert (tmp_path / "tasks" / "1" / "events.ndjson").exists()
    assert (tmp_path / "tasks" / "2" / "events.ndjson").exists()
    a_lines = (tmp_path / "tasks" / "1" / "events.ndjson").read_text().splitlines()
    b_lines = (tmp_path / "tasks" / "2" / "events.ndjson").read_text().splitlines()
    assert len(a_lines) == 1
    assert len(b_lines) == 1
    assert json.loads(a_lines[0])["event_type"] == "a"
    assert json.loads(b_lines[0])["event_type"] == "b"


# ---------------------------------------------------------------------------
# Subscribe / unsubscribe / fan-out
# ---------------------------------------------------------------------------


async def test_subscribe_receives_published_event(broker_factory) -> None:
    broker, _ = broker_factory()
    queue = broker.subscribe()
    await broker.publish(task_id=1, env_id=1, attempt=1, phase="x", event_type="a")
    event = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert event["event_type"] == "a"


async def test_fanout_to_multiple_subscribers(broker_factory) -> None:
    broker, _ = broker_factory()
    qs = [broker.subscribe() for _ in range(5)]
    await broker.publish(task_id=1, env_id=1, attempt=1, phase="x", event_type="a")
    received = await asyncio.gather(*(asyncio.wait_for(q.get(), 1.0) for q in qs))
    assert all(e["event_type"] == "a" for e in received)


async def test_unsubscribe_removes_queue(broker_factory) -> None:
    broker, _ = broker_factory()
    q = broker.subscribe()
    assert q in broker._subscribers
    broker.unsubscribe(q)
    assert q not in broker._subscribers
    # Subsequent publishes do not put into the unsubscribed queue.
    await broker.publish(task_id=1, env_id=1, attempt=1, phase="x", event_type="a")
    assert q.qsize() == 0


async def test_subscriber_added_after_publish_does_not_get_history(broker_factory) -> None:
    broker, _ = broker_factory()
    await broker.publish(task_id=1, env_id=1, attempt=1, phase="x", event_type="a")
    q = broker.subscribe()
    # No event waiting (live-only queue).
    assert q.qsize() == 0


# ---------------------------------------------------------------------------
# Backpressure: full subscriber queue does not block the publisher
# ---------------------------------------------------------------------------


async def test_full_subscriber_queue_does_not_block_publisher(broker_factory) -> None:
    """When subscriber.put_nowait raises QueueFull, publisher continues."""
    broker, _ = broker_factory()
    full_q: asyncio.Queue[dict] = asyncio.Queue(maxsize=1)
    full_q.put_nowait({"prefilled": True})
    broker._subscribers.add(full_q)

    healthy_q = broker.subscribe()

    # Publish while one queue is at capacity.
    await broker.publish(task_id=1, env_id=1, attempt=1, phase="x", event_type="a")

    # Healthy subscriber still got the event.
    e = await asyncio.wait_for(healthy_q.get(), timeout=1.0)
    assert e["event_type"] == "a"
    # The full queue still has only the prefilled item; the new one was dropped.
    assert full_q.qsize() == 1
    assert full_q.get_nowait() == {"prefilled": True}


# ---------------------------------------------------------------------------
# iter_events: backfill + live filtering
# ---------------------------------------------------------------------------


async def test_iter_events_backfills_then_streams_new(broker_factory) -> None:
    broker, _ = broker_factory()
    # Pre-publish two events.
    await broker.publish(task_id=1, env_id=1, attempt=1, phase="x", event_type="a")
    await broker.publish(task_id=1, env_id=1, attempt=1, phase="x", event_type="b")

    received: list[str] = []

    async def consume() -> None:
        async for ev in broker.iter_events(task_id=1, after_seq=0):
            received.append(ev["event_type"])
            if len(received) == 3:
                return

    consumer = asyncio.create_task(consume())
    # Give the consumer a tick to backfill before publishing again.
    await asyncio.sleep(0.05)
    await broker.publish(task_id=1, env_id=1, attempt=1, phase="x", event_type="c")
    await asyncio.wait_for(consumer, timeout=1.0)
    assert received == ["a", "b", "c"]


async def test_iter_events_filters_by_task_id(broker_factory) -> None:
    broker, _ = broker_factory()
    await broker.publish(task_id=1, env_id=1, attempt=1, phase="x", event_type="a")
    await broker.publish(task_id=2, env_id=1, attempt=1, phase="x", event_type="b")

    received: list[str] = []

    async def consume() -> None:
        async for ev in broker.iter_events(task_id=1):
            received.append(ev["event_type"])
            if len(received) == 1:
                return

    consumer = asyncio.create_task(consume())
    await asyncio.wait_for(consumer, timeout=1.0)
    assert received == ["a"]


async def test_iter_events_filters_by_task_ids_set(broker_factory) -> None:
    broker, _ = broker_factory()
    await broker.publish(task_id=1, env_id=1, attempt=1, phase="x", event_type="a")
    await broker.publish(task_id=2, env_id=1, attempt=1, phase="x", event_type="b")
    await broker.publish(task_id=3, env_id=1, attempt=1, phase="x", event_type="c")

    received: list[str] = []

    async def consume() -> None:
        async for ev in broker.iter_events(task_ids={1, 3}):
            received.append(ev["event_type"])
            if len(received) == 2:
                return

    consumer = asyncio.create_task(consume())
    await asyncio.wait_for(consumer, timeout=1.0)
    assert sorted(received) == ["a", "c"]


async def test_iter_events_filters_by_env_id(broker_factory) -> None:
    broker, _ = broker_factory()
    await broker.publish(task_id=1, env_id=10, attempt=1, phase="x", event_type="a")
    await broker.publish(task_id=1, env_id=20, attempt=1, phase="x", event_type="b")

    received: list[str] = []

    async def consume() -> None:
        async for ev in broker.iter_events(env_id=10):
            received.append(ev["event_type"])
            if len(received) == 1:
                return

    consumer = asyncio.create_task(consume())
    await asyncio.wait_for(consumer, timeout=1.0)
    assert received == ["a"]


async def test_iter_events_after_seq_skips_backfill(broker_factory) -> None:
    """Events with seq <= after_seq are skipped in both backfill and live."""
    broker, _ = broker_factory()
    await broker.publish(task_id=1, env_id=1, attempt=1, phase="x", event_type="a")  # seq=1
    await broker.publish(task_id=1, env_id=1, attempt=1, phase="x", event_type="b")  # seq=2
    await broker.publish(task_id=1, env_id=1, attempt=1, phase="x", event_type="c")  # seq=3

    received: list[str] = []

    async def consume() -> None:
        async for ev in broker.iter_events(task_id=1, after_seq=2):
            received.append(ev["event_type"])
            if len(received) == 1:
                return

    consumer = asyncio.create_task(consume())
    await asyncio.wait_for(consumer, timeout=1.0)
    assert received == ["c"]


async def test_iter_events_unsubscribes_on_completion(broker_factory) -> None:
    """When the consumer exits, the broker drops the live queue."""
    broker, _ = broker_factory()
    await broker.publish(task_id=1, env_id=1, attempt=1, phase="x", event_type="a")

    async def consume_once() -> None:
        async for _ in broker.iter_events(task_id=1):
            return

    pre = len(broker._subscribers)
    await asyncio.wait_for(consume_once(), timeout=1.0)
    # Allow the finally clause to run.
    await asyncio.sleep(0)
    post = len(broker._subscribers)
    assert post == pre, f"subscriber leaked: pre={pre} post={post}"


async def test_iter_events_handles_concurrent_publishers(broker_factory) -> None:
    """Two concurrent publishers, one consumer — all events arrive in seq order."""
    broker, _ = broker_factory()

    received: list[int] = []

    async def consume() -> None:
        async for ev in broker.iter_events(task_id=1):
            received.append(int(ev["seq"]))
            if len(received) == 10:
                return

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0.05)
    publishers = [
        broker.publish(task_id=1, env_id=1, attempt=1, phase="x", event_type=f"e{i}") for i in range(10)
    ]
    await asyncio.gather(*publishers)
    await asyncio.wait_for(consumer, timeout=2.0)
    assert sorted(received) == list(range(1, 11))
