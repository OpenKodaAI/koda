"""Progress indicator and shared tool-label utilities for long-running operations."""

import asyncio
import contextlib

from telegram import Message
from telegram.constants import ChatAction

from koda.telegram_types import BotContext


def compact_tool_label(name: str, input_data: dict | None = None) -> str:
    """Build a compact, user-safe progress label."""
    if not input_data:
        return name
    if name in {"Read", "Edit", "Write", "read_file", "edit_file", "write_file"}:
        path = input_data.get("file_path") or input_data.get("path")
        if isinstance(path, str) and path:
            return f"{name}({path.rstrip('/').rsplit('/', 1)[-1]})"
    if name.startswith("file_"):
        path = input_data.get("file_path") or input_data.get("path") or input_data.get("destination")
        if isinstance(path, str) and path:
            return f"{name}({path.rstrip('/').rsplit('/', 1)[-1]})"
    if name in {"Bash", "shell_execute", "shell_bg", "shell_status", "shell_output"}:
        return f"{name}(execucao)"
    if name in {"Grep", "file_grep", "file_search"}:
        return f"{name}(busca)"
    if name.startswith("browser_"):
        return f"{name}(navegacao)"
    return name


def _format_elapsed(secs: float) -> str:
    """Format elapsed seconds as human-readable string: '30s', '2m30s', '1h5m'."""
    secs = int(secs)
    if secs < 60:
        return f"{secs}s"
    minutes, s = divmod(secs, 60)
    if minutes < 60:
        return f"{minutes}m{s}s" if s else f"{minutes}m"
    hours, m = divmod(minutes, 60)
    return f"{hours}h{m}m" if m else f"{hours}h"


async def progress_indicator(chat_id: int, context: BotContext) -> Message | None:
    """Send editable progress message and typing action until cancelled.

    Returns the progress message object so the caller can delete it.
    """
    msg = None
    with contextlib.suppress(Exception):
        msg = await context.bot.send_message(chat_id=chat_id, text="Processing\u2026")
    elapsed = 0
    try:
        while True:
            with contextlib.suppress(Exception):
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            await asyncio.sleep(5)
            elapsed += 5
            if msg is not None and elapsed % 15 == 0:
                with contextlib.suppress(Exception):
                    await msg.edit_text(f"Processing\u2026 ({_format_elapsed(elapsed)})")
    except asyncio.CancelledError:
        pass
    return msg
