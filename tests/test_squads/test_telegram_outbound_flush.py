"""Debounced squad flush: parse modes stay apart and send errors are not silent (M7-E1-T4, D-168)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.error import NetworkError, TimedOut

from koda.squads import telegram_outbound as outbound


@pytest.fixture(autouse=True)
def _no_debounce(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(outbound, "SQUAD_DEBOUNCE_MS", 0)
    monkeypatch.setattr(outbound, "_BUFFERS", {})
    monkeypatch.setattr(outbound, "_NETWORK_RETRY_DELAY_SECONDS", 0, raising=False)


async def _flush(bot: Any, items: list[tuple[str, str | None]]) -> None:
    for text, parse_mode in items:
        await outbound.post_to_topic_buffered(
            bot, chat_id=-100, message_thread_id=7, text=text, agent_label="Ana", parse_mode=parse_mode
        )
    (buffer,) = outbound._BUFFERS.values()
    assert buffer.task is not None
    await buffer.task


@pytest.mark.asyncio
async def test_items_with_different_parse_modes_are_sent_separately_in_order() -> None:
    bot = MagicMock()
    bot.send_message = AsyncMock()

    await _flush(bot, [("a < b", None), ("<i>styled</i>", "HTML"), ("c > d", None)])

    calls = [c.kwargs for c in bot.send_message.await_args_list]
    assert [c.get("parse_mode") for c in calls] == [None, "HTML", None]
    assert "a < b" in calls[0]["text"]
    assert "<i>styled</i>" in calls[1]["text"]
    assert "c > d" in calls[2]["text"]
    assert all(c["message_thread_id"] == 7 for c in calls)


@pytest.mark.asyncio
async def test_items_with_the_same_parse_mode_are_still_combined() -> None:
    bot = MagicMock()
    bot.send_message = AsyncMock()

    await _flush(bot, [("one", "HTML"), ("two", "HTML")])

    bot.send_message.assert_awaited_once()
    text = bot.send_message.await_args.kwargs["text"]
    assert "one" in text and "two" in text


@pytest.mark.asyncio
async def test_a_send_error_is_logged_and_the_remaining_replies_are_still_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = MagicMock()
    monkeypatch.setattr(outbound, "log", log)
    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=[NetworkError("connection reset"), NetworkError("again"), None])

    await _flush(bot, [("first", None), ("second", "HTML")])

    # The failed message is retried once, then logged; the next group still goes out.
    assert bot.send_message.await_count == 3
    assert bot.send_message.await_args_list[2].kwargs["parse_mode"] == "HTML"
    assert log.exception.call_count == 1
    event = log.exception.call_args
    assert event.args[0] == "squad_outbound_send_failed"
    assert event.kwargs["chat_id"] == -100
    assert event.kwargs["items"] == 1


@pytest.mark.asyncio
async def test_a_transient_error_is_retried_once() -> None:
    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=[NetworkError("timeout"), None])

    await _flush(bot, [("hello", None)])

    assert bot.send_message.await_count == 2


@pytest.mark.asyncio
async def test_a_timed_out_send_is_not_retried_but_is_logged(monkeypatch: pytest.MonkeyPatch) -> None:
    """Telegram may have delivered a timed-out message; a retry would post it twice."""
    log = MagicMock()
    monkeypatch.setattr(outbound, "log", log)
    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=[TimedOut(), None])

    await _flush(bot, [("hello", None)])

    bot.send_message.assert_awaited_once()
    assert log.exception.call_args.args[0] == "squad_outbound_send_failed"
