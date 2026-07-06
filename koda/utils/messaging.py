"""Message splitting and sending utilities.

Split logic tracks <pre> tag state (instead of code fences) since
all output is now Telegram HTML.
"""

import re
import tempfile
from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode

from koda.utils.command_helpers import require_message
from koda.utils.formatting import (
    extract_and_replace_large_blocks,
    safe_markdown_to_telegram_html,
)


def split_message(text: str, max_len: int = 4090) -> list[str]:
    """Split HTML text into chunks respecting ``<pre>`` blocks.

    Closes and reopens ``</pre>``…``<pre>`` at cut points so that
    each chunk is valid Telegram HTML.
    """
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    current = ""
    in_pre = False

    for line in text.split("\n"):
        # Track <pre> open/close (may appear mid-line)
        candidate = current + line + "\n" if current else line + "\n"

        if len(candidate) > max_len:
            if current:
                if in_pre:
                    current += "</pre>\n"
                chunks.append(current)
                if in_pre:
                    current = "<pre>" + line + "\n"
                else:
                    current = line + "\n"
            else:
                # Single line too long — force split
                remaining = line
                while len(remaining) > max_len:
                    if in_pre:
                        split_at = max_len - 7  # room for "</pre>\n"
                        chunk_text = "<pre>" + remaining[:split_at] + "</pre>\n"
                        chunks.append(chunk_text)
                    else:
                        split_at = max_len
                        chunks.append(remaining[:split_at])
                    remaining = remaining[split_at:]

                if in_pre:
                    current = "<pre>" + remaining + "\n"
                else:
                    current = remaining + "\n"
        else:
            current = candidate

        # Update pre state after processing the line
        opens = line.count("<pre>") + line.count("<pre ")
        closes = line.count("</pre>")
        net = opens - closes
        if net > 0:
            in_pre = True
        elif net < 0:
            in_pre = False

    if current.strip():
        chunks.append(current)

    return chunks


def _strip_html_tags(text: str) -> str:
    """Remove all HTML tags for plain-text fallback."""
    return re.sub(r"<[^>]+>", "", text)


async def send_long_message(update: Update, text: str, parse_mode: str = ParseMode.HTML) -> None:
    """Send a message as Telegram HTML, splitting if needed.

    Large code blocks (>50 lines) are extracted and sent as file attachments.
    Falls back to plain text (tags stripped) if HTML send fails.
    """
    message = require_message(update)

    # Extract large code blocks and send as files
    modified_text, code_files = extract_and_replace_large_blocks(text)

    # Send code files first
    for filename, content in code_files:
        with tempfile.NamedTemporaryFile(mode="w", suffix=f"_{filename}", prefix="code_", delete=False) as f:
            f.write(content)
            tmp_path = f.name
        try:
            with open(tmp_path, "rb") as fh:
                await message.reply_document(
                    document=fh,
                    filename=filename,
                    caption=f"Code block: {filename}",
                )
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    # Convert Markdown → Telegram HTML
    html_text = safe_markdown_to_telegram_html(modified_text)

    # Send text chunks
    chunks = split_message(html_text)
    for chunk in chunks:
        try:
            await message.reply_text(chunk, parse_mode=parse_mode)
        except Exception:
            # Fallback: strip tags → plain text
            await message.reply_text(_strip_html_tags(chunk))
