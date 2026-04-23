"""Focused tests for queue recovery, DLQ reprocessing, and worker resilience."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class _RuntimeStoreStub:
    def __init__(
        self,
        *,
        queue_rows: list[dict[str, object]] | None = None,
        environments: dict[int, dict[str, object]] | None = None,
    ) -> None:
        self._queue_rows = list(queue_rows or [])
        self._environments = dict(environments or {})
        self.updated: list[tuple[int, dict[str, object]]] = []

    def list_runtime_queues(self) -> list[dict[str, object]]:
        return list(self._queue_rows)

    def get_environment_by_task(self, task_id: int) -> dict[str, object] | None:
        return self._environments.get(task_id)

    def update_runtime_queue_item(self, task_id: int, **fields: object) -> None:
        self.updated.append((task_id, dict(fields)))

    def bulk_update_runtime_queue_items(self, updates: list[dict[str, object]]) -> None:
        self.updated.extend((int(item["task_id"]), dict(item)) for item in updates)


class _RuntimeStub:
    def __init__(self, store: _RuntimeStoreStub) -> None:
        self.store = store
        self.events = SimpleNamespace(publish=AsyncMock())
        self.record_warning = AsyncMock()
        self.finalize_task = AsyncMock()


@pytest.mark.asyncio
async def test_recover_pending_tasks_requeues_persisted_fifo_item():
    from koda.services.queue_manager import (
        _queue_workers,
        _user_queue_task_ids,
        _user_queues,
        _user_tasks,
        get_queue,
        recover_pending_tasks,
    )

    user_id = 321
    task_id = 42
    task_row = {
        "id": task_id,
        "user_id": user_id,
        "chat_id": 555,
        "status": "running",
        "query_text": "mensagem recuperada",
        "provider": "codex",
        "model": "gpt-5.4",
        "work_dir": "/tmp/work",
        "attempt": 1,
        "created_at": "2026-03-30T10:00:00+00:00",
        "session_id": "sess-1",
    }
    payload = {
        "_user_message": True,
        "_task_id": task_id,
        "chat_id": 555,
        "query_text": "mensagem recuperada",
        "provider": "codex",
        "model": "gpt-5.4",
        "work_dir": "/tmp/work",
        "session_id": "sess-1",
        "image_paths": ["img-1.png"],
    }
    application = MagicMock()
    application.user_data = defaultdict(dict)
    application.bot = AsyncMock()
    runtime = _RuntimeStub(
        _RuntimeStoreStub(
            queue_rows=[
                {
                    "task_id": task_id,
                    "payload_json": json.dumps(payload),
                    "recovery_count": 0,
                }
            ]
        )
    )

    try:
        with (
            patch("koda.services.queue_manager.list_pending_tasks_for_recovery", return_value=[task_row]),
            patch("koda.services.runtime.get_runtime_controller", return_value=runtime),
            patch("koda.services.queue_manager._persist_runtime_queue_item", new_callable=AsyncMock) as persist,
            patch("koda.services.queue_manager._sync_user_queue_observability"),
            patch("koda.services.queue_manager._ensure_queue_worker", new_callable=AsyncMock) as ensure_worker,
            patch("koda.services.queue_manager.update_task_status"),
            patch("koda.services.queue_manager.RUNTIME_ENVIRONMENTS_ENABLED", False),
        ):
            summary = await recover_pending_tasks(application)

        assert summary == {"recovered": 1, "exhausted": 0, "skipped": 0}
        raw_item = get_queue(user_id).get_nowait()
        assert raw_item["_task_id"] == task_id
        assert raw_item["_user_message"] is True
        assert raw_item["_queue_recovered"] is True
        assert raw_item["_recovery_count"] == 1
        assert raw_item["image_paths"] == ["img-1.png"]
        persist.assert_awaited_once()
        assert persist.await_args.kwargs["recovery_count"] == 1
        assert persist.await_args.kwargs["last_recovered_at"]
        ensure_worker.assert_awaited_once()
    finally:
        _queue_workers.pop(user_id, None)
        _user_tasks.pop(user_id, None)
        _user_queue_task_ids.pop(user_id, None)
        _user_queues.pop(user_id, None)


@pytest.mark.asyncio
async def test_recover_pending_tasks_moves_task_to_dlq_after_recovery_limit():
    from koda.config import QUEUE_MAX_RECOVERY_ATTEMPTS
    from koda.services.queue_manager import (
        _queue_workers,
        _user_queue_task_ids,
        _user_queues,
        _user_tasks,
        recover_pending_tasks,
    )

    user_id = 777
    task_id = 90
    task_row = {
        "id": task_id,
        "user_id": user_id,
        "chat_id": 777,
        "status": "queued",
        "query_text": "nao repetir para sempre",
        "provider": "codex",
        "model": "gpt-5.4",
        "attempt": 2,
        "created_at": "2026-03-30T10:00:00+00:00",
    }
    runtime = _RuntimeStub(
        _RuntimeStoreStub(
            queue_rows=[
                {
                    "task_id": task_id,
                    "payload_json": json.dumps(
                        {"_user_message": True, "chat_id": 777, "query_text": task_row["query_text"]}
                    ),
                    "recovery_count": QUEUE_MAX_RECOVERY_ATTEMPTS,
                }
            ]
        )
    )
    application = MagicMock()
    application.user_data = defaultdict(dict)
    application.bot = AsyncMock()

    try:
        with (
            patch("koda.services.queue_manager.list_pending_tasks_for_recovery", return_value=[task_row]),
            patch("koda.services.runtime.get_runtime_controller", return_value=runtime),
            patch("koda.services.queue_manager.dlq_insert", return_value=11) as dlq_insert,
            patch("koda.services.queue_manager._persist_runtime_queue_item", new_callable=AsyncMock) as persist,
            patch("koda.services.queue_manager._sync_user_queue_observability"),
            patch("koda.services.queue_manager._ensure_queue_worker", new_callable=AsyncMock) as ensure_worker,
            patch("koda.services.queue_manager.update_task_status"),
            patch("koda.services.queue_manager.RUNTIME_ENVIRONMENTS_ENABLED", False),
        ):
            summary = await recover_pending_tasks(application)

        assert summary == {"recovered": 0, "exhausted": 1, "skipped": 0}
        dlq_insert.assert_called_once()
        persist.assert_not_awaited()
        ensure_worker.assert_not_awaited()
        assert not _user_queues.get(user_id)
    finally:
        _queue_workers.pop(user_id, None)
        _user_tasks.pop(user_id, None)
        _user_queue_task_ids.pop(user_id, None)
        _user_queues.pop(user_id, None)


@pytest.mark.asyncio
async def test_requeue_dlq_entry_creates_fresh_task_and_appends_history():
    from koda.services.queue_manager import (
        _queue_workers,
        _user_queue_task_ids,
        _user_queues,
        _user_tasks,
        get_queue,
        requeue_dlq_entry,
    )

    user_id = 808
    entry = {
        "id": 5,
        "task_id": 44,
        "user_id": user_id,
        "chat_id": 909,
        "query_text": "executar novamente",
        "model": "gpt-5.4",
        "metadata_json": json.dumps(
            {
                "queue_payload": {
                    "_dashboard_chat": True,
                    "chat_id": 909,
                    "query_text": "executar novamente",
                    "provider": "codex",
                    "model": "gpt-5.4",
                    "work_dir": "/tmp/work",
                    "session_id": "sess-9",
                },
                "history": [{"event": "dlq_inserted", "at": "2026-03-30T10:00:00+00:00"}],
            }
        ),
    }
    application = MagicMock()
    application.user_data = defaultdict(dict)
    application.bot = AsyncMock()

    try:
        with (
            patch("koda.services.queue_manager.create_task", return_value=77),
            patch("koda.services.queue_manager.dlq_mark_retried", return_value=True) as mark_retried,
            patch("koda.services.queue_manager._persist_runtime_queue_item", new_callable=AsyncMock) as persist,
            patch("koda.services.queue_manager._sync_user_queue_observability"),
            patch("koda.services.queue_manager._ensure_queue_worker", new_callable=AsyncMock) as ensure_worker,
        ):
            new_task_id = await requeue_dlq_entry(
                entry, application=application, actor=111, bot_override=application.bot
            )

        assert new_task_id == 77
        raw_item = get_queue(user_id).get_nowait()
        assert raw_item["_user_message"] is True
        assert raw_item["_task_id"] == 77
        assert raw_item["query_text"] == "executar novamente"
        assert raw_item["provider"] == "codex"
        persist.assert_awaited_once()
        ensure_worker.assert_awaited_once()
        metadata_json = mark_retried.call_args.kwargs["metadata_json"]
        metadata = json.loads(metadata_json)
        assert metadata["last_reprocessed_task_id"] == 77
        assert metadata["history"][-1]["event"] == "dlq_requeued"
        assert metadata["history"][-1]["new_task_id"] == 77
    finally:
        _queue_workers.pop(user_id, None)
        _user_tasks.pop(user_id, None)
        _user_queue_task_ids.pop(user_id, None)
        _user_queues.pop(user_id, None)


@pytest.mark.asyncio
async def test_process_queue_survives_dispatch_failure_and_continues_fifo():
    from koda.services.queue_manager import (
        _process_queue,
        _queue_workers,
        _unregister_task,
        _user_queues,
        _user_tasks,
    )

    user_id = 999
    queue = asyncio.Queue()
    _user_queues[user_id] = queue
    context = MagicMock()
    context.user_data = {}

    broken_item = {"_task_id": 1, "chat_id": 123}
    second_update = MagicMock()
    second_update.effective_chat.id = 123
    await queue.put(broken_item)
    await queue.put((second_update, "segunda", None, None, 2))

    executed: list[int] = []

    async def fake_execute(raw_item, _user_id, _context, task_id, task_info):
        if task_id == 1:
            raise ValueError("falha de despacho")
        executed.append(task_id)
        _unregister_task(task_info)

    try:
        with (
            patch("koda.services.queue_manager._execute_single_task", side_effect=fake_execute),
            patch(
                "koda.services.queue_manager._handle_queue_dispatch_failure", new_callable=AsyncMock
            ) as dispatch_failure,
            patch("koda.services.queue_manager._sync_user_queue_observability"),
        ):
            await _process_queue(user_id, context)

        assert executed == [2]
        dispatch_failure.assert_awaited_once()
        assert queue.qsize() == 0
    finally:
        _queue_workers.pop(user_id, None)
        _user_tasks.pop(user_id, None)
        _user_queues.pop(user_id, None)
