"""Tests for squad turn dispatch transports."""

from __future__ import annotations

from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from koda.squads.dispatch import dispatch_squad_turn


@pytest.mark.asyncio
async def test_dashboard_room_dispatch_uses_runtime_queue_when_available() -> None:
    application = SimpleNamespace(user_data=defaultdict(dict), bot=object())
    thread = SimpleNamespace(
        id="thread-web-1",
        squad_id="squad-1",
        owner_user_id=None,
        telegram_chat_id=None,
        telegram_message_thread_id=None,
    )
    thread_store = AsyncMock()
    enqueue = AsyncMock(return_value=77)

    with (
        patch(
            "koda.services.runtime.get_runtime_controller",
            return_value=SimpleNamespace(_application=application),
        ),
        patch("koda.services.queue_manager.enqueue_squad_agent_task", enqueue),
    ):
        result = await dispatch_squad_turn(
            target_agent_id="FE",
            thread=thread,
            thread_store=thread_store,
            query_text="Build the UI",
            parent_message_id="msg-1",
            metadata={"from_agent": "PM"},
            squad_task_id="task-1",
            delegation_chain=["PM"],
            delegation_request_id="coord-task-1",
            delegation_origin_agent_id="PM",
        )

    assert result.dispatched is True
    assert result.transport == "local_queue"
    assert result.enqueued_task_id == 77
    enqueue.assert_awaited_once()
    assert enqueue.await_args.kwargs["application"] is application
    assert enqueue.await_args.kwargs["executing_agent_id"] == "FE"
    assert enqueue.await_args.kwargs["squad_thread_id"] == "thread-web-1"
    assert enqueue.await_args.kwargs["squad_task_id"] == "task-1"
    assert enqueue.await_args.kwargs["user_id"] > 0
    assert enqueue.await_args.kwargs["chat_id"] < 0
    assert enqueue.await_args.kwargs["bot_override"] is not None


@pytest.mark.asyncio
async def test_dashboard_room_dispatch_uses_runtime_http_without_local_application() -> None:
    thread = SimpleNamespace(
        id="thread-runtime-http-1",
        squad_id="squad-1",
        owner_user_id=None,
        telegram_chat_id=None,
        telegram_message_thread_id=None,
    )
    thread_store = AsyncMock()
    manager = SimpleNamespace(
        send_dashboard_squad_message=Mock(return_value={"accepted": True, "session_id": "squad-1", "task_id": 88})
    )

    with (
        patch("koda.services.runtime.get_runtime_controller", return_value=SimpleNamespace(_application=None)),
        patch("koda.control_plane.manager.get_control_plane_manager", return_value=manager),
    ):
        result = await dispatch_squad_turn(
            target_agent_id="FE",
            thread=thread,
            thread_store=thread_store,
            query_text="Build the UI",
            parent_message_id="msg-1",
            metadata={"from_agent": "PM"},
            squad_task_id="task-1",
            delegation_chain=["PM"],
            delegation_request_id="coord-task-1",
            delegation_origin_agent_id="PM",
        )

    assert result.dispatched is True
    assert result.transport == "runtime_http"
    assert result.enqueued_task_id == 88
    manager.send_dashboard_squad_message.assert_called_once()
    assert manager.send_dashboard_squad_message.call_args.args == ("FE",)
    assert manager.send_dashboard_squad_message.call_args.kwargs["text"] == "Build the UI"
    assert manager.send_dashboard_squad_message.call_args.kwargs["squad_thread_id"] == "thread-runtime-http-1"
    assert manager.send_dashboard_squad_message.call_args.kwargs["squad_task_id"] == "task-1"


@pytest.mark.asyncio
async def test_dispatch_falls_back_to_bus_when_runtime_http_is_unavailable() -> None:
    thread = SimpleNamespace(
        id="thread-bus-1",
        squad_id="squad-1",
        owner_user_id=None,
        telegram_chat_id=None,
        telegram_message_thread_id=None,
    )
    thread_store = AsyncMock()
    bus = AsyncMock()
    bus.send = AsyncMock(return_value="msg-1")

    with (
        patch("koda.services.runtime.get_runtime_controller", return_value=SimpleNamespace(_application=None)),
        patch("koda.control_plane.manager.get_control_plane_manager", side_effect=RuntimeError("no runtime")),
        patch("koda.agents.get_message_bus", return_value=bus),
    ):
        result = await dispatch_squad_turn(
            target_agent_id="FE",
            thread=thread,
            thread_store=thread_store,
            query_text="Build the UI",
            parent_message_id="msg-1",
            metadata={"from_agent": "PM"},
        )

    assert result.dispatched is True
    assert result.transport == "bus"
    assert result.message_id == "msg-1"
    bus.send.assert_awaited_once()


def _open_thread(thread_id: str = "thread-refusal-1", status: str = "open") -> SimpleNamespace:
    return SimpleNamespace(
        id=thread_id,
        squad_id="squad-1",
        status=status,
        owner_user_id=None,
        telegram_chat_id=None,
        telegram_message_thread_id=None,
    )


@pytest.mark.asyncio
async def test_every_refusal_path_marks_the_result_refused() -> None:
    """The dispatch's own room read, the queue's re-read and the runtime's 409 all set ``refused`` (D-361)."""
    from koda.control_plane.manager import RuntimeConflictError
    from koda.squads import SquadThreadNotRunnableError

    application = SimpleNamespace(user_data=defaultdict(dict), bot=object())
    kwargs = {"thread_store": AsyncMock(), "query_text": "Build the UI", "parent_message_id": "msg-1"}

    own_read = await dispatch_squad_turn(target_agent_id="FE", thread=_open_thread(status="paused"), **kwargs)
    assert (own_read.transport, own_read.dispatched, own_read.refused) == ("none", False, True)

    with (
        patch(
            "koda.services.runtime.get_runtime_controller",
            return_value=SimpleNamespace(_application=application),
        ),
        patch(
            "koda.services.queue_manager.enqueue_squad_agent_task",
            AsyncMock(side_effect=SquadThreadNotRunnableError("thread is paused")),
        ),
    ):
        queue_read = await dispatch_squad_turn(target_agent_id="FE", thread=_open_thread(), **kwargs)
    assert (queue_read.transport, queue_read.dispatched, queue_read.refused) == ("local_queue", False, True)
    assert queue_read.error == "thread is paused"

    manager = SimpleNamespace(
        send_dashboard_squad_message=Mock(
            side_effect=RuntimeConflictError("runtime rejected dashboard message: thread is paused")
        )
    )
    bus = AsyncMock()
    with (
        patch("koda.services.runtime.get_runtime_controller", return_value=SimpleNamespace(_application=None)),
        patch("koda.control_plane.manager.get_control_plane_manager", return_value=manager),
        patch("koda.agents.get_message_bus", return_value=bus),
    ):
        runtime_read = await dispatch_squad_turn(target_agent_id="FE", thread=_open_thread(), **kwargs)
    assert (runtime_read.transport, runtime_read.dispatched, runtime_read.refused) == ("runtime_http", False, True)
    assert "thread is paused" in str(runtime_read.error)
    # A refused turn is not delivered another way.
    bus.send.assert_not_called()


@pytest.mark.asyncio
async def test_a_failed_delivery_is_not_a_refusal() -> None:
    application = SimpleNamespace(user_data=defaultdict(dict), bot=object())
    with (
        patch(
            "koda.services.runtime.get_runtime_controller",
            return_value=SimpleNamespace(_application=application),
        ),
        patch("koda.services.queue_manager.enqueue_squad_agent_task", AsyncMock(side_effect=RuntimeError("down"))),
    ):
        result = await dispatch_squad_turn(
            target_agent_id="FE",
            thread=_open_thread(),
            thread_store=AsyncMock(),
            query_text="Build the UI",
            parent_message_id="msg-1",
        )
    assert result.dispatched is False and result.refused is False


def test_a_runtime_409_raises_the_conflict_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import io
    import urllib.error

    from koda.control_plane.manager import ControlPlaneManager, RuntimeConflictError

    def conflict(*_args: object, **_kwargs: object) -> None:
        raise urllib.error.HTTPError(
            "http://runtime/api/runtime/sessions/messages",
            409,
            "Conflict",
            {},  # type: ignore[arg-type]
            io.BytesIO(b'{"error": "thread is paused"}'),
        )

    monkeypatch.setattr("koda.control_plane.manager.guarded_urlopen", conflict)
    manager = object.__new__(ControlPlaneManager)
    with pytest.raises(RuntimeConflictError, match="thread is paused"):
        manager._post_runtime_session_message(
            agent_id="FE", runtime_base_url="http://runtime", runtime_token="tok", request_payload={"text": "hi"}
        )
