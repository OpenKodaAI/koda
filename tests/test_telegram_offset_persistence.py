"""Telegram polling resumes from a known offset across restarts (P1-2).

Before: ``app.run_polling(drop_pending_updates=True)`` discarded any
queued user messages on every bot restart. Combined with the lazy
migration regression, restarting an agent after a crash silently lost
whatever the user had sent during the outage.

After:
- ``TELEGRAM_DROP_PENDING_UPDATES`` defaults to ``False`` so Telegram's
  server-side offset replays pending updates on reconnect.
- The supervisor records the last seen ``update_id`` per agent in
  ``cp_telegram_offsets`` for observability + Phase 1 bot-pool
  groundwork.

These tests pin both halves so a future refactor can't regress us back
to silent message loss.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from koda.state import telegram_offsets


def test_get_last_offset_returns_zero_for_unknown_agent() -> None:
    with patch.object(telegram_offsets, "fetch_one", return_value=None):
        assert telegram_offsets.get_last_offset("AGENT_NEW") == 0


def test_get_last_offset_returns_stored_value() -> None:
    with patch.object(telegram_offsets, "fetch_one", return_value={"last_update_id": 42}):
        assert telegram_offsets.get_last_offset("AGENT_OLD") == 42


def test_get_last_offset_swallows_db_errors() -> None:
    """Offset plumbing must never block message delivery."""

    def _boom(_sql: str, _params: tuple[Any, ...] = ()) -> Any:
        raise RuntimeError("table missing")

    with patch.object(telegram_offsets, "fetch_one", side_effect=_boom):
        assert telegram_offsets.get_last_offset("AGENT_X") == 0


def test_record_offset_upserts_through_execute() -> None:
    captured: list[tuple[str, tuple[Any, ...]]] = []

    def _spy(sql: str, params: tuple[Any, ...] = ()) -> int:
        captured.append((sql, params))
        return 1

    with patch.object(telegram_offsets, "execute", _spy):
        telegram_offsets.record_offset("AGENT_GAMMA", 1234)

    assert len(captured) == 1
    sql, params = captured[0]
    assert "INSERT INTO cp_telegram_offsets" in sql
    assert "GREATEST" in sql  # never moves the offset backward on out-of-order replay
    assert params[0] == "AGENT_GAMMA"
    assert params[1] == 1234


def test_record_offset_skips_blank_or_negative_values() -> None:
    captured: list[tuple[str, tuple[Any, ...]]] = []

    def _spy(sql: str, params: tuple[Any, ...] = ()) -> int:
        captured.append((sql, params))
        return 1

    with patch.object(telegram_offsets, "execute", _spy):
        telegram_offsets.record_offset("", 1)
        telegram_offsets.record_offset("AGENT_X", 0)
        telegram_offsets.record_offset("AGENT_X", -5)
    assert captured == []


def test_default_dropping_pending_updates_is_false() -> None:
    """The whole point: a fresh boot must not drop the user's queued
    messages. The legacy default was ``True`` and bit operators every
    restart."""
    from koda.config import TELEGRAM_DROP_PENDING_UPDATES

    assert TELEGRAM_DROP_PENDING_UPDATES is False


def test_main_module_uses_config_flag_not_hardcoded_true() -> None:
    """``__main__.py`` must read the env-driven flag, not pass a literal
    ``True`` into ``run_polling``."""
    from pathlib import Path

    src = Path("koda/__main__.py").read_text()
    assert "drop_pending_updates=TELEGRAM_DROP_PENDING_UPDATES" in src
    assert "drop_pending_updates=True" not in src
