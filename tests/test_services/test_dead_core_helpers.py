"""The dead core helpers removed by M4-E1-T1 stay removed (TD-012 to TD-015).

No producer puts tuples on a user queue, so the legacy tuple shapes are not
parsed; every producer sets ``_task_id``, so the queue worker never creates a
task itself; and the per-user semaphore never limited anything because each
user's worker runs one task at a time.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import koda
import koda.config as config
from koda.services import llm_runner, queue_manager


def _legacy_tuple() -> tuple[object, ...]:
    update = MagicMock()
    update.effective_chat.id = 123
    return (update, "hello", ["/tmp/img.png"], None, 5)


def test_startup_validator_module_is_gone() -> None:
    assert not (Path(koda.__file__).parent / "startup_validator.py").exists()


@pytest.mark.parametrize("name", ["_user_semaphores", "_get_user_semaphore"])
def test_per_user_semaphore_is_gone(name: str) -> None:
    assert not hasattr(queue_manager, name)


def test_per_user_concurrency_setting_is_gone() -> None:
    assert not hasattr(config, "MAX_CONCURRENT_TASKS_PER_USER")


def test_warm_provider_capabilities_is_gone() -> None:
    assert not hasattr(llm_runner, "warm_provider_capabilities")


class TestLegacyTupleQueueItems:
    def test_parse_rejects_a_tuple(self) -> None:
        with pytest.raises(ValueError, match="unsupported queue item"):
            queue_manager._parse_queue_item(_legacy_tuple())

    def test_task_id_is_not_read_from_a_tuple(self) -> None:
        assert queue_manager._extract_task_id_from_raw_item(_legacy_tuple()) is None

    def test_serialize_marks_a_tuple_unsupported(self) -> None:
        payload = json.loads(queue_manager._serialize_queue_payload(_legacy_tuple()))
        assert payload == {"_unsupported_payload": True}


@pytest.mark.asyncio
async def test_worker_does_not_create_a_task_for_an_item_without_task_id() -> None:
    user_id = 70123
    queue: asyncio.Queue[object] = asyncio.Queue()
    await queue.put({"chat_id": 7, "query_text": "no id"})
    queue_manager._user_queues[user_id] = queue
    context = MagicMock()
    context.user_data = {}
    try:
        with (
            patch("koda.services.queue_manager.create_task", return_value=99) as create_task,
            patch("koda.services.queue_manager._persist_runtime_queue_item", new=AsyncMock()),
            patch("koda.services.queue_manager._execute_single_task", new=AsyncMock()) as execute,
            patch("koda.services.queue_manager._handle_queue_dispatch_failure", new=AsyncMock()) as failure,
            patch("koda.services.queue_manager._sync_user_queue_observability"),
        ):
            await queue_manager._process_queue(user_id, context)

        create_task.assert_not_called()
        execute.assert_not_called()
        failure.assert_awaited_once()
        assert failure.await_args.kwargs["task_id"] is None
    finally:
        queue_manager._queue_workers.pop(user_id, None)
        queue_manager._user_queues.pop(user_id, None)
        queue_manager._user_tasks.pop(user_id, None)
