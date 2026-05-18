"""Tests for the squad Telegram command handlers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.handlers.squad_handlers import (
    cmd_squad_bind,
    cmd_squad_status,
    cmd_squad_thread_close,
    cmd_squad_thread_new,
    cmd_squad_unbind,
    route_squad_supergroup_message,
)


def _make_update(
    *, chat_type: str = "supergroup", chat_id: int = -100, is_forum: bool = False, message_thread_id: int | None = None
) -> MagicMock:
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 42
    update.effective_chat = MagicMock()
    update.effective_chat.id = chat_id
    update.effective_chat.type = chat_type
    update.effective_chat.title = "Build"
    update.effective_chat.is_forum = is_forum
    update.message = AsyncMock()
    update.message.reply_text = AsyncMock()
    update.message.message_thread_id = message_thread_id
    return update


def _make_context(*, args: list[str] | None = None, user_data: dict | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.args = list(args or [])
    ctx.user_data = dict(user_data or {})
    ctx.application = None
    ctx.bot = AsyncMock()
    ctx.bot.get_me = AsyncMock(return_value=SimpleNamespace(id=99))
    ctx.bot.get_chat_member = AsyncMock(return_value=SimpleNamespace(status="administrator"))
    return ctx


def _binding(**overrides: object) -> object:
    from koda.squads.telegram_bridge import SquadTelegramBinding

    base: dict[str, object] = {
        "squad_id": "build",
        "telegram_chat_id": -100,
        "chat_title": "Build",
        "is_forum": True,
        "bound_by_user_id": 42,
        "bound_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "metadata": {},
    }
    base.update(overrides)
    return SquadTelegramBinding(**base)  # type: ignore[arg-type]


def _thread(**overrides: object) -> object:
    from koda.squads.threads import ThreadDescriptor

    base: dict[str, object] = {
        "id": "00000000-0000-0000-0000-000000000001",
        "workspace_id": "acme",
        "squad_id": "build",
        "owner_user_id": 42,
        "title": "Landing",
        "status": "open",
        "coordinator_agent_id": None,
        "current_owner_agent_id": None,
        "parent_thread_id": None,
        "visibility": "squad",
        "telegram_chat_id": -100,
        "telegram_message_thread_id": 7,
        "budget_usd_cap": None,
        "cost_usd_accum": Decimal(0),
    }
    base.update(overrides)
    return ThreadDescriptor(**base)  # type: ignore[arg-type]


def _task_descriptor(task_id: str, *, agent_id: str, kind: str) -> object:
    from koda.squads.tasks import TaskDescriptor

    return TaskDescriptor(
        id=task_id,
        thread_id="00000000-0000-0000-0000-000000000001",
        parent_task_id=None,
        depends_on=[],
        assigned_agent_id=agent_id,
        assigner_agent_id="PM",
        kind=kind,
        title="Task",
        description="Do work",
        status="pending",
        acceptance_criteria=[],
        deliverables_spec=[],
        delivered_artifact_ids=[],
        claim_token=None,
        claim_expires_at=None,
        delegation_depth=0,
        idempotency_key=None,
        cost_usd_so_far=Decimal(0),
        runtime_task_id=None,
        version=1,
    )


def _capability_summaries(agent_ids: list[str]) -> list[object]:
    from koda.squads.capabilities import CapabilitySummary

    return [CapabilitySummary(agent_id=agent_id, display_name=agent_id, role=agent_id) for agent_id in agent_ids]


def _semantic_router(*agent_ids: str) -> object:
    from koda.squads.semantic_router import SemanticAgentScore, SemanticRoutingResult

    router = MagicMock()
    router.rank_agents = AsyncMock(
        return_value=SemanticRoutingResult(
            available=True,
            model_name="test-model",
            scores=[
                SemanticAgentScore(
                    agent_id=agent_id,
                    score=0.9 - (idx * 0.05),
                    positive_score=0.9 - (idx * 0.05),
                    negative_score=0.0,
                    summary_text=f"{agent_id} summary",
                )
                for idx, agent_id in enumerate(agent_ids)
            ],
        )
    )
    return router


@pytest.fixture(autouse=True)
def _auth_and_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.handlers.squad_handlers.INTER_AGENT_ENABLED", True)
    monkeypatch.setattr("koda.handlers.squad_handlers.auth_check", lambda update: True)
    monkeypatch.setattr("koda.config.SQUAD_TELEGRAM_STRICT_ADMIN_CHECK", False)


@pytest.mark.asyncio
async def test_bind_rejects_non_supergroup() -> None:
    update = _make_update(chat_type="private")
    ctx = _make_context(args=["build"])
    await cmd_squad_bind(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "supergroup" in text


@pytest.mark.asyncio
async def test_bind_requires_squad_id() -> None:
    update = _make_update(is_forum=True)
    ctx = _make_context(args=[])
    await cmd_squad_bind(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "Usage" in text


@pytest.mark.asyncio
async def test_bind_service_unavailable() -> None:
    update = _make_update(is_forum=True)
    ctx = _make_context(args=["acme", "build"])
    with patch("koda.squads.get_telegram_binding_service", return_value=None):
        await cmd_squad_bind(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "unavailable" in text.lower()


@pytest.mark.asyncio
async def test_bind_success_passes_chat_metadata() -> None:
    update = _make_update(is_forum=True)
    ctx = _make_context(args=["acme", "build"])
    mock_service = AsyncMock()
    mock_service.bind = AsyncMock(return_value=_binding(is_forum=True))
    with patch("koda.squads.get_telegram_binding_service", return_value=mock_service):
        await cmd_squad_bind(update, ctx)
    mock_service.bind.assert_awaited_once()
    kwargs = mock_service.bind.await_args.kwargs
    assert kwargs["squad_id"] == "build"
    assert kwargs["metadata"]["workspace_id"] == "acme"
    assert kwargs["telegram_chat_id"] == -100
    assert kwargs["is_forum"] is True
    assert kwargs["bound_by_user_id"] == 42
    assert "bound to this chat" in update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_bind_conflict_surfaces_message() -> None:
    from koda.squads.telegram_bridge import TelegramBindingConflictError

    update = _make_update(is_forum=True)
    ctx = _make_context(args=["acme", "ops"])
    mock_service = AsyncMock()
    mock_service.bind = AsyncMock(side_effect=TelegramBindingConflictError("chat owned by 'build'"))
    with patch("koda.squads.get_telegram_binding_service", return_value=mock_service):
        await cmd_squad_bind(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "Bind failed" in text
    assert "build" in text


@pytest.mark.asyncio
async def test_unbind_no_binding() -> None:
    update = _make_update()
    ctx = _make_context()
    mock_service = AsyncMock()
    mock_service.get_for_chat = AsyncMock(return_value=None)
    with patch("koda.squads.get_telegram_binding_service", return_value=mock_service):
        await cmd_squad_unbind(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "not bound" in text


@pytest.mark.asyncio
async def test_unbind_success() -> None:
    update = _make_update()
    ctx = _make_context()
    mock_service = AsyncMock()
    mock_service.get_for_chat = AsyncMock(return_value=_binding())
    mock_service.unbind = AsyncMock(return_value=True)
    with patch("koda.squads.get_telegram_binding_service", return_value=mock_service):
        await cmd_squad_unbind(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "unbound" in text


@pytest.mark.asyncio
async def test_status_no_binding() -> None:
    update = _make_update()
    ctx = _make_context()
    mock_service = AsyncMock()
    mock_service.get_for_chat = AsyncMock(return_value=None)
    with patch("koda.squads.get_telegram_binding_service", return_value=mock_service):
        await cmd_squad_status(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "not bound" in text


@pytest.mark.asyncio
async def test_status_shows_binding() -> None:
    update = _make_update(is_forum=True)
    ctx = _make_context()
    mock_service = AsyncMock()
    mock_service.get_for_chat = AsyncMock(return_value=_binding(is_forum=True))
    with patch("koda.squads.get_telegram_binding_service", return_value=mock_service):
        await cmd_squad_status(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "build" in text
    assert "forum" in text


@pytest.mark.asyncio
async def test_thread_new_requires_binding() -> None:
    update = _make_update()
    ctx = _make_context(args=["Landing", "page"])
    mock_binding_service = AsyncMock()
    mock_binding_service.get_for_chat = AsyncMock(return_value=None)
    mock_thread_store = AsyncMock()
    with (
        patch("koda.squads.get_telegram_binding_service", return_value=mock_binding_service),
        patch("koda.squads.get_squad_thread_store", return_value=mock_thread_store),
    ):
        await cmd_squad_thread_new(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "not bound" in text


@pytest.mark.asyncio
async def test_thread_new_requires_workspace_id() -> None:
    update = _make_update(is_forum=True)
    ctx = _make_context(args=["Landing"])
    mock_binding_service = AsyncMock()
    mock_binding_service.get_for_chat = AsyncMock(return_value=_binding(is_forum=True))
    mock_thread_store = AsyncMock()
    with (
        patch("koda.squads.get_telegram_binding_service", return_value=mock_binding_service),
        patch("koda.squads.get_squad_thread_store", return_value=mock_thread_store),
    ):
        await cmd_squad_thread_new(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "workspace_id" in text


@pytest.mark.asyncio
async def test_thread_new_creates_forum_topic_and_thread() -> None:
    update = _make_update(is_forum=True)
    ctx = _make_context(
        args=["Landing", "page"],
        user_data={"squad_default_workspace_id": "acme"},
    )
    ctx.bot.create_forum_topic = AsyncMock(return_value=MagicMock(message_thread_id=21))
    mock_binding_service = AsyncMock()
    mock_binding_service.get_for_chat = AsyncMock(return_value=_binding(is_forum=True))
    mock_thread_store = AsyncMock()
    mock_thread_store.create_thread = AsyncMock(return_value=_thread(telegram_message_thread_id=21))
    with (
        patch("koda.squads.get_telegram_binding_service", return_value=mock_binding_service),
        patch("koda.squads.get_squad_thread_store", return_value=mock_thread_store),
    ):
        await cmd_squad_thread_new(update, ctx)
    ctx.bot.create_forum_topic.assert_awaited_once_with(chat_id=-100, name="Landing page")
    create_kwargs = mock_thread_store.create_thread.await_args.kwargs
    assert create_kwargs["telegram_chat_id"] == -100
    assert create_kwargs["telegram_message_thread_id"] == 21
    assert create_kwargs["workspace_id"] == "acme"
    assert "topic 21" in update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_thread_new_non_forum_skips_topic() -> None:
    update = _make_update(is_forum=False)
    ctx = _make_context(
        args=["Hotfix"],
        user_data={"squad_default_workspace_id": "acme"},
    )
    mock_binding_service = AsyncMock()
    mock_binding_service.get_for_chat = AsyncMock(return_value=_binding(is_forum=False))
    mock_thread_store = AsyncMock()
    mock_thread_store.create_thread = AsyncMock(return_value=_thread(telegram_message_thread_id=None))
    with (
        patch("koda.squads.get_telegram_binding_service", return_value=mock_binding_service),
        patch("koda.squads.get_squad_thread_store", return_value=mock_thread_store),
    ):
        await cmd_squad_thread_new(update, ctx)
    ctx.bot.create_forum_topic.assert_not_called()
    create_kwargs = mock_thread_store.create_thread.await_args.kwargs
    assert create_kwargs["telegram_message_thread_id"] is None
    assert "no forum topic" in update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_thread_close_no_thread_for_topic() -> None:
    update = _make_update(is_forum=True, message_thread_id=7)
    ctx = _make_context()
    mock_thread_store = AsyncMock()
    mock_thread_store.find_by_telegram_topic = AsyncMock(return_value=None)
    with patch("koda.squads.get_squad_thread_store", return_value=mock_thread_store):
        await cmd_squad_thread_close(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "No squad thread" in text


@pytest.mark.asyncio
async def test_thread_close_marks_completed() -> None:
    update = _make_update(is_forum=True, message_thread_id=7)
    ctx = _make_context()
    mock_thread_store = AsyncMock()
    mock_thread_store.find_by_telegram_topic = AsyncMock(return_value=_thread())
    mock_thread_store.update_thread_status = AsyncMock(return_value=_thread(status="completed"))
    with patch("koda.squads.get_squad_thread_store", return_value=mock_thread_store):
        await cmd_squad_thread_close(update, ctx)
    mock_thread_store.update_thread_status.assert_awaited_once()
    text = update.message.reply_text.call_args[0][0]
    assert "completed" in text


@pytest.mark.asyncio
async def test_inter_agent_disabled_blocks_all(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.handlers.squad_handlers.INTER_AGENT_ENABLED", False)
    update = _make_update()
    ctx = _make_context(args=["build"])
    await cmd_squad_bind(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "disabled" in text


# --- inbound MessageHandler ---


def _make_inbound_update(
    *,
    chat_type: str = "supergroup",
    chat_id: int = -100,
    is_topic: bool = True,
    message_thread_id: int | None = 7,
    text: str = "Need a hand with this design",
    is_bot: bool = False,
    user_id: int = 42,
    username: str = "operator",
) -> MagicMock:
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.username = username
    update.effective_user.is_bot = is_bot
    update.effective_chat = MagicMock()
    update.effective_chat.id = chat_id
    update.effective_chat.type = chat_type
    update.effective_chat.title = "Build"
    msg = AsyncMock()
    msg.text = text
    msg.caption = None
    msg.is_topic_message = is_topic
    msg.message_thread_id = message_thread_id
    msg.message_id = 555
    update.effective_message = msg
    update.message = msg
    return update


@pytest.mark.asyncio
async def test_inbound_skips_bot_user() -> None:
    update = _make_inbound_update(is_bot=True)
    ctx = _make_context()
    mock_binding = AsyncMock()
    mock_thread = AsyncMock()
    with (
        patch("koda.squads.get_telegram_binding_service", return_value=mock_binding),
        patch("koda.squads.get_squad_thread_store", return_value=mock_thread),
    ):
        await route_squad_supergroup_message(update, ctx)
    mock_binding.get_for_chat.assert_not_called()


@pytest.mark.asyncio
async def test_inbound_skips_non_topic_message() -> None:
    update = _make_inbound_update(is_topic=False, message_thread_id=None)
    ctx = _make_context()
    mock_binding = AsyncMock()
    mock_thread = AsyncMock()
    with (
        patch("koda.squads.get_telegram_binding_service", return_value=mock_binding),
        patch("koda.squads.get_squad_thread_store", return_value=mock_thread),
    ):
        await route_squad_supergroup_message(update, ctx)
    mock_binding.get_for_chat.assert_not_called()


@pytest.mark.asyncio
async def test_inbound_skips_when_no_binding() -> None:
    update = _make_inbound_update()
    ctx = _make_context()
    mock_binding = AsyncMock()
    mock_binding.get_for_chat = AsyncMock(return_value=None)
    mock_thread_store = AsyncMock()
    with (
        patch("koda.squads.get_telegram_binding_service", return_value=mock_binding),
        patch("koda.squads.get_squad_thread_store", return_value=mock_thread_store),
    ):
        await route_squad_supergroup_message(update, ctx)
    mock_thread_store.find_by_telegram_topic.assert_not_called()


@pytest.mark.asyncio
async def test_inbound_skips_when_thread_missing() -> None:
    update = _make_inbound_update()
    ctx = _make_context()
    mock_binding = AsyncMock()
    mock_binding.get_for_chat = AsyncMock(return_value=_binding())
    mock_thread_store = AsyncMock()
    mock_thread_store.find_by_telegram_topic = AsyncMock(return_value=None)
    mock_thread_store.post_thread_message = AsyncMock()
    with (
        patch("koda.squads.get_telegram_binding_service", return_value=mock_binding),
        patch("koda.squads.get_squad_thread_store", return_value=mock_thread_store),
    ):
        await route_squad_supergroup_message(update, ctx)
    mock_thread_store.post_thread_message.assert_not_called()


@pytest.mark.asyncio
async def test_inbound_persists_user_input() -> None:
    update = _make_inbound_update(text="hello squad")
    ctx = _make_context()
    mock_binding = AsyncMock()
    mock_binding.get_for_chat = AsyncMock(return_value=_binding())
    mock_thread_store = AsyncMock()
    mock_thread_store.find_by_telegram_topic = AsyncMock(return_value=_thread())
    mock_thread_store.post_thread_message = AsyncMock(return_value=99)
    mock_thread_store.list_participants = AsyncMock(return_value=[])
    with (
        patch("koda.squads.get_telegram_binding_service", return_value=mock_binding),
        patch("koda.squads.get_squad_thread_store", return_value=mock_thread_store),
    ):
        await route_squad_supergroup_message(update, ctx)
    assert mock_thread_store.post_thread_message.await_count == 2
    kwargs = mock_thread_store.post_thread_message.await_args_list[0].kwargs
    assert kwargs["thread_id"] == "00000000-0000-0000-0000-000000000001"
    assert kwargs["from_agent"] == "user:operator"
    assert kwargs["content"] == "hello squad"
    assert kwargs["message_type"] == "user_input"
    assert kwargs["metadata"]["telegram_user_id"] == 42
    assert kwargs["metadata"]["telegram_message_thread_id"] == 7
    awareness_payload = mock_thread_store.post_thread_message.await_args_list[1].kwargs["metadata"]["payload"]
    assert awareness_payload["event_type"] == "squad_awareness_fanout"


@pytest.mark.asyncio
async def test_inbound_routes_to_mentioned_agent() -> None:
    update = _make_inbound_update(text="@fe please style this")
    ctx = _make_context()
    mock_binding = AsyncMock()
    mock_binding.get_for_chat = AsyncMock(return_value=_binding())
    mock_thread_store = AsyncMock()
    mock_thread_store.find_by_telegram_topic = AsyncMock(return_value=_thread(coordinator_agent_id="PM"))
    mock_thread_store.post_thread_message = AsyncMock(return_value=42)
    fe_part = MagicMock(agent_id="FE", left_at=None)
    pm_part = MagicMock(agent_id="PM", left_at=None)
    mock_thread_store.list_participants = AsyncMock(return_value=[fe_part, pm_part])
    mock_bus = AsyncMock()
    mock_bus.send = AsyncMock(return_value="msg-101")
    with (
        patch("koda.squads.get_telegram_binding_service", return_value=mock_binding),
        patch("koda.squads.get_squad_thread_store", return_value=mock_thread_store),
        patch("koda.agents.get_message_bus", return_value=mock_bus),
    ):
        await route_squad_supergroup_message(update, ctx)
    mock_bus.send.assert_awaited_once()
    kwargs = mock_bus.send.await_args.kwargs
    assert kwargs["from_agent"] == "squad_router"
    assert kwargs["to_agent"] == "FE"
    assert kwargs["content"] == "@fe please style this"
    assert kwargs["metadata"]["kind"] == "squad_thread_input"
    assert kwargs["metadata"]["thread_id"] == "00000000-0000-0000-0000-000000000001"
    assert kwargs["metadata"]["telegram_message_thread_id"] == 7


@pytest.mark.asyncio
async def test_inbound_enqueues_target_locally_when_application_available() -> None:
    update = _make_inbound_update(text="@fe please style this")
    ctx = _make_context()
    ctx.application = MagicMock()
    mock_binding = AsyncMock()
    mock_binding.get_for_chat = AsyncMock(return_value=_binding())
    mock_thread_store = AsyncMock()
    mock_thread_store.find_by_telegram_topic = AsyncMock(return_value=_thread(coordinator_agent_id="PM"))
    mock_thread_store.post_thread_message = AsyncMock(return_value=42)
    fe_part = MagicMock(agent_id="FE", left_at=None)
    pm_part = MagicMock(agent_id="PM", left_at=None)
    mock_thread_store.list_participants = AsyncMock(return_value=[fe_part, pm_part])
    mock_enqueue = AsyncMock(return_value=1001)
    mock_bus = AsyncMock()
    mock_bus.send = AsyncMock()
    with (
        patch("koda.squads.get_telegram_binding_service", return_value=mock_binding),
        patch("koda.squads.get_squad_thread_store", return_value=mock_thread_store),
        patch("koda.services.queue_manager.enqueue_squad_agent_task", mock_enqueue),
        patch("koda.agents.get_message_bus", return_value=mock_bus),
    ):
        await route_squad_supergroup_message(update, ctx)
    mock_enqueue.assert_awaited_once()
    enqueue_kwargs = mock_enqueue.await_args.kwargs
    assert enqueue_kwargs["executing_agent_id"] == "FE"
    assert enqueue_kwargs["squad_thread_id"] == "00000000-0000-0000-0000-000000000001"
    assert enqueue_kwargs["telegram_message_thread_id"] == 7
    mock_bus.send.assert_not_called()


@pytest.mark.asyncio
async def test_inbound_telegram_bot_username_mention_enqueues_specialist() -> None:
    update = _make_inbound_update(text="@frontend_bot please style this")
    ctx = _make_context()
    ctx.application = MagicMock()
    mock_binding = AsyncMock()
    mock_binding.get_for_chat = AsyncMock(return_value=_binding())
    mock_thread_store = AsyncMock()
    mock_thread_store.find_by_telegram_topic = AsyncMock(return_value=_thread(coordinator_agent_id="PM"))
    mock_thread_store.post_thread_message = AsyncMock(return_value=42)
    fe_part = MagicMock(agent_id="FE", left_at=None)
    pm_part = MagicMock(agent_id="PM", left_at=None)
    mock_thread_store.list_participants = AsyncMock(return_value=[fe_part, pm_part])
    mock_enqueue = AsyncMock(return_value=1001)
    manager = MagicMock()
    manager.list_agents.return_value = [{"id": "FE", "metadata": {"telegram_username": "frontend_bot"}}]
    manager.get_decrypted_secret_value.return_value = None

    with (
        patch("koda.squads.get_telegram_binding_service", return_value=mock_binding),
        patch("koda.squads.get_squad_thread_store", return_value=mock_thread_store),
        patch(
            "koda.squads.build_squad_capability_summaries",
            AsyncMock(return_value=_capability_summaries(["PM", "FE"])),
        ),
        patch("koda.squads.get_squad_semantic_router", return_value=_semantic_router("FE")),
        patch("koda.control_plane.manager.get_control_plane_manager", return_value=manager),
        patch("koda.services.queue_manager.enqueue_squad_agent_task", mock_enqueue),
    ):
        await route_squad_supergroup_message(update, ctx)

    enqueue_kwargs = mock_enqueue.await_args.kwargs
    assert enqueue_kwargs["executing_agent_id"] == "FE"
    event_types = [call.kwargs["message_type"] for call in mock_thread_store.post_thread_message.await_args_list]
    assert event_types[:3] == ["user_input", "system_event", "system_event"]
    awareness_payload = mock_thread_store.post_thread_message.await_args_list[1].kwargs["metadata"]["payload"]
    assert awareness_payload["event_type"] == "squad_awareness_fanout"
    assert awareness_payload["delivery_intent"] == "awareness"
    routing_payload = mock_thread_store.post_thread_message.await_args_list[2].kwargs["metadata"]["payload"]
    assert routing_payload["source"] == "telegram_mention"
    assert routing_payload["targets"] == ["FE"]


@pytest.mark.asyncio
async def test_inbound_unresolved_telegram_mention_is_visible_and_not_dispatched() -> None:
    update = _make_inbound_update(text="@ghost please style this")
    ctx = _make_context()
    ctx.application = MagicMock()
    update.message.reply_text = AsyncMock()
    mock_binding = AsyncMock()
    mock_binding.get_for_chat = AsyncMock(return_value=_binding())
    mock_thread_store = AsyncMock()
    mock_thread_store.find_by_telegram_topic = AsyncMock(return_value=_thread(coordinator_agent_id="PM"))
    mock_thread_store.post_thread_message = AsyncMock(return_value=42)
    mock_thread_store.list_participants = AsyncMock(
        return_value=[MagicMock(agent_id="FE", left_at=None), MagicMock(agent_id="PM", left_at=None)]
    )
    mock_enqueue = AsyncMock()
    mock_bus = AsyncMock()
    mock_bus.send = AsyncMock()

    with (
        patch("koda.squads.get_telegram_binding_service", return_value=mock_binding),
        patch("koda.squads.get_squad_thread_store", return_value=mock_thread_store),
        patch(
            "koda.squads.build_squad_capability_summaries",
            AsyncMock(return_value=_capability_summaries(["PM", "FE"])),
        ),
        patch("koda.squads.get_squad_semantic_router", return_value=_semantic_router("FE")),
        patch("koda.services.queue_manager.enqueue_squad_agent_task", mock_enqueue),
        patch("koda.agents.get_message_bus", return_value=mock_bus),
    ):
        await route_squad_supergroup_message(update, ctx)

    mock_enqueue.assert_not_awaited()
    mock_bus.send.assert_not_called()
    update.message.reply_text.assert_awaited_once()
    awareness_payload = mock_thread_store.post_thread_message.await_args_list[1].kwargs["metadata"]["payload"]
    assert awareness_payload["event_type"] == "squad_awareness_fanout"
    event_payload = mock_thread_store.post_thread_message.await_args_list[2].kwargs["metadata"]["payload"]
    assert event_payload["event_type"] == "mention_unresolved"
    assert event_payload["unresolved"] == ["@ghost"]


@pytest.mark.asyncio
async def test_inbound_routes_to_coordinator_when_no_mention() -> None:
    update = _make_inbound_update(text="any progress on the design?")
    ctx = _make_context()
    mock_binding = AsyncMock()
    mock_binding.get_for_chat = AsyncMock(return_value=_binding())
    mock_thread_store = AsyncMock()
    mock_thread_store.find_by_telegram_topic = AsyncMock(return_value=_thread(coordinator_agent_id="PM"))
    mock_thread_store.post_thread_message = AsyncMock(return_value=42)
    fe_part = MagicMock(agent_id="FE", left_at=None)
    pm_part = MagicMock(agent_id="PM", left_at=None)
    mock_thread_store.list_participants = AsyncMock(return_value=[fe_part, pm_part])
    mock_bus = AsyncMock()
    mock_bus.send = AsyncMock(return_value="msg-201")
    with (
        patch("koda.squads.get_telegram_binding_service", return_value=mock_binding),
        patch("koda.squads.get_squad_thread_store", return_value=mock_thread_store),
        patch("koda.agents.get_message_bus", return_value=mock_bus),
    ):
        await route_squad_supergroup_message(update, ctx)
    mock_bus.send.assert_awaited_once()
    assert mock_bus.send.await_args.kwargs["to_agent"] == "PM"


@pytest.mark.asyncio
async def test_inbound_complex_request_uses_supervisor_and_real_task_requests() -> None:
    update = _make_inbound_update(
        text="Entregue uma landing page de fintech com copy forte, design polido e formulário"
    )
    ctx = _make_context()
    ctx.application = MagicMock()
    mock_binding = AsyncMock()
    mock_binding.get_for_chat = AsyncMock(return_value=_binding())
    mock_thread_store = AsyncMock()
    mock_thread_store.find_by_telegram_topic = AsyncMock(return_value=_thread(coordinator_agent_id="PM"))
    mock_thread_store.post_thread_message = AsyncMock(side_effect=[42, 43, 44, 45, 46, 47, 48, 49])
    mock_thread_store.notify_event = AsyncMock()
    parts = [
        MagicMock(agent_id="PM", left_at=None),
        MagicMock(agent_id="COPY", left_at=None),
        MagicMock(agent_id="FE", left_at=None),
        MagicMock(agent_id="QA", left_at=None),
    ]
    mock_thread_store.list_participants = AsyncMock(return_value=parts)
    mock_task_store = AsyncMock()
    mock_task_store.create_task = AsyncMock(
        side_effect=[
            _task_descriptor("00000000-0000-0000-0000-000000000101", agent_id="COPY", kind="brief_copy"),
            _task_descriptor("00000000-0000-0000-0000-000000000102", agent_id="FE", kind="frontend"),
            _task_descriptor("00000000-0000-0000-0000-000000000103", agent_id="QA", kind="review"),
        ]
    )
    mock_enqueue = AsyncMock(return_value=1001)
    mock_bus = AsyncMock()
    mock_bus.send = AsyncMock()

    async def fake_run_llm(**_: object) -> dict[str, object]:
        return {
            "result": json.dumps(
                {
                    "mode": "sequential_plan",
                    "confidence": 0.92,
                    "reasoning_summary": "real team plan",
                    "tasks": [
                        {
                            "key": "brief",
                            "title": "Brief",
                            "agent_id": "COPY",
                            "kind": "brief_copy",
                            "objective": "Brief and copy",
                        },
                        {
                            "key": "build",
                            "title": "Build",
                            "agent_id": "FE",
                            "kind": "frontend",
                            "objective": "Build landing page",
                            "depends_on": ["brief"],
                        },
                        {
                            "key": "review",
                            "title": "Review",
                            "agent_id": "QA",
                            "kind": "review",
                            "objective": "Review delivery",
                            "depends_on": ["build"],
                        },
                    ],
                    "selected_agents": ["COPY", "FE", "QA"],
                    "final_response_strategy": "coordinator_synthesis_after_all_task_results",
                }
            )
        }

    with (
        patch("koda.squads.get_telegram_binding_service", return_value=mock_binding),
        patch("koda.squads.get_squad_thread_store", return_value=mock_thread_store),
        patch("koda.squads.get_squad_task_store", return_value=mock_task_store),
        patch(
            "koda.squads.build_squad_capability_summaries",
            AsyncMock(return_value=_capability_summaries(["PM", "COPY", "FE", "QA"])),
        ),
        patch("koda.squads.get_squad_semantic_router", return_value=_semantic_router("COPY", "FE", "QA")),
        patch("koda.services.llm_runner.run_llm", fake_run_llm),
        patch("koda.services.queue_manager.enqueue_squad_agent_task", mock_enqueue),
        patch("koda.agents.get_message_bus", return_value=mock_bus),
    ):
        await route_squad_supergroup_message(update, ctx)

    assert mock_task_store.create_task.await_count == 3
    assert mock_enqueue.await_count == 1
    assert [call.kwargs["executing_agent_id"] for call in mock_enqueue.await_args_list] == ["COPY"]
    assert all(call.kwargs["squad_task_id"] for call in mock_enqueue.await_args_list)
    assert mock_task_store.create_task.await_args_list[1].kwargs["depends_on"] == [
        "00000000-0000-0000-0000-000000000101"
    ]
    assert mock_task_store.create_task.await_args_list[2].kwargs["depends_on"] == [
        "00000000-0000-0000-0000-000000000102"
    ]
    mock_bus.send.assert_not_called()
    posted_types = [call.kwargs["message_type"] for call in mock_thread_store.post_thread_message.await_args_list]
    assert posted_types == [
        "user_input",
        "system_event",
        "system_event",
        "system_event",
        "task_request",
        "task_request",
        "task_request",
        "system_event",
    ]


@pytest.mark.asyncio
async def test_inbound_routes_by_capability_fallback_when_no_coordinator() -> None:
    update = _make_inbound_update(text="random observation")
    ctx = _make_context()
    mock_binding = AsyncMock()
    mock_binding.get_for_chat = AsyncMock(return_value=_binding())
    mock_thread_store = AsyncMock()
    # Coordinator is None and no mentions -> deterministic capability fallback.
    mock_thread_store.find_by_telegram_topic = AsyncMock(return_value=_thread(coordinator_agent_id=None))
    mock_thread_store.post_thread_message = AsyncMock(return_value=42)
    fe_part = MagicMock(agent_id="FE", left_at=None)
    mock_thread_store.list_participants = AsyncMock(return_value=[fe_part])
    mock_bus = AsyncMock()
    mock_bus.send = AsyncMock()
    with (
        patch("koda.squads.get_telegram_binding_service", return_value=mock_binding),
        patch("koda.squads.get_squad_thread_store", return_value=mock_thread_store),
        patch("koda.agents.get_message_bus", return_value=mock_bus),
    ):
        await route_squad_supergroup_message(update, ctx)
    assert mock_thread_store.post_thread_message.await_args_list[0].kwargs["message_type"] == "user_input"
    mock_bus.send.assert_awaited_once()
    assert mock_bus.send.await_args.kwargs["to_agent"] == "FE"


@pytest.mark.asyncio
async def test_inbound_routes_to_multiple_mentions() -> None:
    update = _make_inbound_update(text="@fe and @be sync up please")
    ctx = _make_context()
    mock_binding = AsyncMock()
    mock_binding.get_for_chat = AsyncMock(return_value=_binding())
    mock_thread_store = AsyncMock()
    mock_thread_store.find_by_telegram_topic = AsyncMock(return_value=_thread())
    mock_thread_store.post_thread_message = AsyncMock(return_value=42)
    parts = [
        MagicMock(agent_id="FE", left_at=None),
        MagicMock(agent_id="BE", left_at=None),
        MagicMock(agent_id="PM", left_at=None),
    ]
    mock_thread_store.list_participants = AsyncMock(return_value=parts)
    mock_bus = AsyncMock()
    mock_bus.send = AsyncMock(return_value="msg-1")
    with (
        patch("koda.squads.get_telegram_binding_service", return_value=mock_binding),
        patch("koda.squads.get_squad_thread_store", return_value=mock_thread_store),
        patch("koda.agents.get_message_bus", return_value=mock_bus),
    ):
        await route_squad_supergroup_message(update, ctx)
    targets = [c.kwargs["to_agent"] for c in mock_bus.send.await_args_list]
    assert targets == ["FE", "BE"]


@pytest.mark.asyncio
async def test_inbound_swallows_bus_failures() -> None:
    update = _make_inbound_update(text="@fe ping")
    ctx = _make_context()
    mock_binding = AsyncMock()
    mock_binding.get_for_chat = AsyncMock(return_value=_binding())
    mock_thread_store = AsyncMock()
    mock_thread_store.find_by_telegram_topic = AsyncMock(return_value=_thread())
    mock_thread_store.post_thread_message = AsyncMock(return_value=42)
    mock_thread_store.list_participants = AsyncMock(return_value=[MagicMock(agent_id="FE", left_at=None)])
    mock_bus = AsyncMock()
    mock_bus.send = AsyncMock(side_effect=RuntimeError("bus down"))
    with (
        patch("koda.squads.get_telegram_binding_service", return_value=mock_binding),
        patch("koda.squads.get_squad_thread_store", return_value=mock_thread_store),
        patch("koda.agents.get_message_bus", return_value=mock_bus),
    ):
        # Must not raise — audit row already in DB; routing failure is logged
        # and silently swallowed so the next user message can recover.
        await route_squad_supergroup_message(update, ctx)
    assert mock_thread_store.post_thread_message.await_args_list[0].kwargs["message_type"] == "user_input"
    mock_bus.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_inbound_skips_when_squad_mismatch() -> None:
    update = _make_inbound_update()
    ctx = _make_context()
    mock_binding = AsyncMock()
    mock_binding.get_for_chat = AsyncMock(return_value=_binding(squad_id="other"))
    mock_thread_store = AsyncMock()
    mock_thread_store.find_by_telegram_topic = AsyncMock(return_value=_thread())
    mock_thread_store.post_thread_message = AsyncMock()
    with (
        patch("koda.squads.get_telegram_binding_service", return_value=mock_binding),
        patch("koda.squads.get_squad_thread_store", return_value=mock_thread_store),
    ):
        await route_squad_supergroup_message(update, ctx)
    mock_thread_store.post_thread_message.assert_not_called()


@pytest.mark.asyncio
async def test_inbound_skips_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.handlers.squad_handlers.INTER_AGENT_ENABLED", False)
    update = _make_inbound_update()
    ctx = _make_context()
    mock_binding = AsyncMock()
    mock_thread_store = AsyncMock()
    with (
        patch("koda.squads.get_telegram_binding_service", return_value=mock_binding),
        patch("koda.squads.get_squad_thread_store", return_value=mock_thread_store),
    ):
        await route_squad_supergroup_message(update, ctx)
    mock_binding.get_for_chat.assert_not_called()
