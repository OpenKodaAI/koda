"""Tests for the squad telegram outbound helper."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from koda.squads.telegram_outbound import post_to_thread
from koda.squads.threads import ThreadDescriptor


def _thread(**overrides: object) -> ThreadDescriptor:
    base: dict[str, object] = {
        "id": "00000000-0000-0000-0000-000000000001",
        "workspace_id": "acme",
        "squad_id": "build",
        "owner_user_id": 1,
        "title": "t",
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


@pytest.mark.asyncio
async def test_post_includes_message_thread_id() -> None:
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=object())
    await post_to_thread(bot, _thread(), "hello")
    bot.send_message.assert_awaited_once()
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == -100
    assert kwargs["message_thread_id"] == 7
    assert kwargs["text"] == "hello"


@pytest.mark.asyncio
async def test_post_omits_message_thread_id_when_absent() -> None:
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=object())
    thread = _thread(telegram_message_thread_id=None)
    await post_to_thread(bot, thread, "hi")
    kwargs = bot.send_message.await_args.kwargs
    assert "message_thread_id" not in kwargs
    assert kwargs["chat_id"] == -100


@pytest.mark.asyncio
async def test_post_applies_agent_label_prefix() -> None:
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=object())
    await post_to_thread(bot, _thread(), "shipping it", agent_label="Frontend Dev")
    text = bot.send_message.await_args.kwargs["text"]
    assert text == "[Frontend Dev] shipping it"


@pytest.mark.asyncio
async def test_post_truncates_to_telegram_limit() -> None:
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=object())
    long_body = "x" * 5000
    await post_to_thread(bot, _thread(), long_body)
    text = bot.send_message.await_args.kwargs["text"]
    assert len(text) == 4096
    assert text.endswith("…")


@pytest.mark.asyncio
async def test_post_raises_when_thread_unbound() -> None:
    bot = AsyncMock()
    thread = _thread(telegram_chat_id=None)
    with pytest.raises(ValueError):
        await post_to_thread(bot, thread, "hi")


@pytest.mark.asyncio
async def test_post_forwards_parse_mode() -> None:
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=object())
    await post_to_thread(bot, _thread(), "*hi*", parse_mode="MarkdownV2")
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["parse_mode"] == "MarkdownV2"


def test_get_outbound_bot_caches_by_token() -> None:
    from unittest.mock import patch

    from koda.squads import telegram_outbound as tob

    tob._BOT_CACHE.clear()
    sentinel_a = object()
    sentinel_b = object()
    constructed: list[str] = []

    def _fake_bot(token: str) -> object:
        constructed.append(token)
        return sentinel_a if token == "A" else sentinel_b

    with patch("telegram.Bot", side_effect=lambda token: _fake_bot(token)):
        first = tob.get_outbound_bot("A")
        again = tob.get_outbound_bot("A")
        other = tob.get_outbound_bot("B")
    assert first is sentinel_a
    assert again is sentinel_a  # cached, not reconstructed
    assert other is sentinel_b
    assert constructed == ["A", "B"]
    tob._BOT_CACHE.clear()
