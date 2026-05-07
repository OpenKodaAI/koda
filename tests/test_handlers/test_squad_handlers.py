"""Tests for the squad Telegram command handlers."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
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
    ctx.bot = AsyncMock()
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


@pytest.fixture(autouse=True)
def _auth_and_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.handlers.squad_handlers.INTER_AGENT_ENABLED", True)
    monkeypatch.setattr("koda.handlers.squad_handlers.auth_check", lambda update: True)


@pytest.mark.asyncio
async def test_bind_rejects_non_supergroup() -> None:
    update = _make_update(chat_type="private")
    ctx = _make_context(args=["build"])
    await cmd_squad_bind(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "supergroup" in text


@pytest.mark.asyncio
async def test_bind_requires_squad_id() -> None:
    update = _make_update()
    ctx = _make_context(args=[])
    await cmd_squad_bind(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "Usage" in text


@pytest.mark.asyncio
async def test_bind_service_unavailable() -> None:
    update = _make_update()
    ctx = _make_context(args=["build"])
    with patch("koda.squads.get_telegram_binding_service", return_value=None):
        await cmd_squad_bind(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "unavailable" in text.lower()


@pytest.mark.asyncio
async def test_bind_success_passes_chat_metadata() -> None:
    update = _make_update(is_forum=True)
    ctx = _make_context(args=["build"])
    mock_service = AsyncMock()
    mock_service.bind = AsyncMock(return_value=_binding(is_forum=True))
    with patch("koda.squads.get_telegram_binding_service", return_value=mock_service):
        await cmd_squad_bind(update, ctx)
    mock_service.bind.assert_awaited_once()
    kwargs = mock_service.bind.await_args.kwargs
    assert kwargs["squad_id"] == "build"
    assert kwargs["telegram_chat_id"] == -100
    assert kwargs["is_forum"] is True
    assert kwargs["bound_by_user_id"] == 42
    assert "bound to this chat" in update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_bind_conflict_surfaces_message() -> None:
    from koda.squads.telegram_bridge import TelegramBindingConflictError

    update = _make_update()
    ctx = _make_context(args=["ops"])
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
    mock_thread_store.post_thread_message.assert_awaited_once()
    kwargs = mock_thread_store.post_thread_message.await_args.kwargs
    assert kwargs["thread_id"] == "00000000-0000-0000-0000-000000000001"
    assert kwargs["from_agent"] == "user:operator"
    assert kwargs["content"] == "hello squad"
    assert kwargs["message_type"] == "user_input"
    assert kwargs["metadata"]["telegram_user_id"] == 42
    assert kwargs["metadata"]["telegram_message_thread_id"] == 7


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
async def test_inbound_skips_routing_when_no_target() -> None:
    update = _make_inbound_update(text="random observation")
    ctx = _make_context()
    mock_binding = AsyncMock()
    mock_binding.get_for_chat = AsyncMock(return_value=_binding())
    mock_thread_store = AsyncMock()
    # Coordinator is None and no mentions -> no target.
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
    mock_thread_store.post_thread_message.assert_awaited_once()
    mock_bus.send.assert_not_called()


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
    mock_thread_store.post_thread_message.assert_awaited_once()
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
