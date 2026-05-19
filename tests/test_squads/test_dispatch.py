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
