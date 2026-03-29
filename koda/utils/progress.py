"""Progress indicator and shared tool-label utilities for long-running operations."""

import asyncio
import contextlib

from telegram import Message
from telegram.constants import ChatAction

from koda.telegram_types import BotContext


def compact_tool_label(name: str, input_data: dict | None = None) -> str:
    """Build a compact label like 'Read(file.py)', 'Bash(npm test...)'."""
    if not input_data:
        return name
    if name == "Read" and "file_path" in input_data:
        path = input_data["file_path"]
        return f"Read({path.rsplit('/', 1)[-1]})"
    if name == "Bash" and "command" in input_data:
        cmd = input_data["command"]
        if len(cmd) > 30:
            cmd = cmd[:27] + "..."
        return f"Bash({cmd})"
    if name == "Grep" and "pattern" in input_data:
        pat = input_data["pattern"]
        if len(pat) > 20:
            pat = pat[:17] + "..."
        return f"Grep({pat})"
    # Generic: show first string value
    for v in input_data.values():
        if isinstance(v, str) and v:
            short = v if len(v) <= 20 else v[:17] + "..."
            return f"{name}({short})"
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
