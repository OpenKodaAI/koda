"""Reply context extraction."""

from telegram import Message


def extract_reply_context(message: Message) -> str | None:
    """Extract text from the replied-to message, truncated to 2000 chars."""
    if not message.reply_to_message:
        return None

    reply = message.reply_to_message
    text = reply.text or reply.caption or ""
    if not text:
        return None

    # Strip the footer (--- line and everything after)
    footer_idx = text.rfind("\n\n---\n")
    if footer_idx != -1:
        text = text[:footer_idx]

    text = text.strip()
    if len(text) > 2000:
        text = text[:2000] + "\u2026"

    return text
