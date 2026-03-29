"""Telegram response action markup helpers."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_response_markup(task_id: int | None) -> InlineKeyboardMarkup:
    """Build the standard response action keyboard for task outputs."""
    rows = [[InlineKeyboardButton("📌 Bookmark", callback_data="bookmark:save")]]
    if task_id is not None:
        rows.append(
            [
                InlineKeyboardButton("✅ Aprovado", callback_data=f"feedback:approved:{task_id}"),
                InlineKeyboardButton("🛠 Corrigir", callback_data=f"feedback:corrected:{task_id}"),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton("❌ Falhou", callback_data=f"feedback:failed:{task_id}"),
                InlineKeyboardButton("⚠️ Risco", callback_data=f"feedback:risky:{task_id}"),
            ]
        )
        rows.append([InlineKeyboardButton("📈 Promover", callback_data=f"feedback:promote:{task_id}")])
    return InlineKeyboardMarkup(rows)
