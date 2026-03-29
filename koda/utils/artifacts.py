"""Extract and send files created by provider execution via Telegram."""

import os
from typing import BinaryIO

from telegram import Update

from koda.logging_config import get_logger
from koda.telegram_types import BotContext

log = get_logger(__name__)

_FILE_CREATING_TOOLS = {"Write", "write_file", "Edit", "edit_file"}

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
GIF_EXTS = {".gif"}
VIDEO_EXTS = {".mp4", ".mov", ".webm"}
AUDIO_EXTS = {".mp3", ".wav", ".flac", ".aac", ".m4a"}
VOICE_EXTS = {".ogg"}

MAX_PHOTO_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

# Magic bytes for image validation
_IMAGE_SIGNATURES = [
    (b"\x89PNG", 4),  # PNG
    (b"\xff\xd8\xff", 3),  # JPEG
    (b"BM", 2),  # BMP
    (b"RIFF", 4),  # WebP (RIFF....WEBP)
]


def _is_valid_image(path: str) -> bool:
    """Check if file starts with a known image magic byte signature."""
    try:
        with open(path, "rb") as f:
            header = f.read(12)
    except OSError:
        return False
    for sig, length in _IMAGE_SIGNATURES:
        if header[:length] == sig:
            if sig == b"RIFF":
                return header[8:12] == b"WEBP"
            return True
    return False


def _format_size(size_bytes: int) -> str:
    """Format file size as human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    return f"{size_bytes / (1024 * 1024):.1f}MB"


def extract_created_files(tool_uses: list[dict], native_items: list[dict] | None = None) -> list[str]:
    """Extract unique file paths from provider-native file creation signals."""
    seen: set[str] = set()
    paths: list[str] = []
    for block in tool_uses:
        if block.get("name") not in _FILE_CREATING_TOOLS:
            continue
        fp = (block.get("input") or {}).get("file_path")
        if fp and fp not in seen:
            seen.add(fp)
            paths.append(fp)
    for item in native_items or []:
        if item.get("type") != "file_change":
            continue
        kind = str(item.get("kind") or item.get("change_type") or "").lower()
        if kind and kind != "add":
            continue
        fp = item.get("path") or item.get("file_path")
        if fp and fp not in seen:
            seen.add(fp)
            paths.append(fp)
    return paths


async def _send_media(
    method_name: str,
    file_obj: BinaryIO,
    chat_id: int,
    context: BotContext,
    update: Update | None,
    caption: str,
) -> None:
    """Send media via reply or context.bot, eliminating if/else duplication."""
    if update and update.message:
        method = getattr(update.message, f"reply_{method_name}")
        await method(**{method_name: file_obj}, caption=caption)
    else:
        method = getattr(context.bot, f"send_{method_name}")
        await method(chat_id=chat_id, **{method_name: file_obj}, caption=caption)


async def send_created_files(
    paths: list[str],
    chat_id: int,
    context: BotContext,
    update: Update | None,
) -> int:
    """Send created files to Telegram. Returns count of files sent."""
    sent = 0
    for path in paths:
        if not os.path.isfile(path):
            log.debug("artifact_skip_missing", path=path)
            continue
        file_size = os.path.getsize(path)
        if file_size > MAX_FILE_SIZE:
            log.debug("artifact_skip_large", path=path)
            continue

        filename = os.path.basename(path)
        ext = os.path.splitext(filename)[1].lower()
        caption = f"{filename} ({_format_size(file_size)})"

        try:
            with open(path, "rb") as f:
                if ext in IMAGE_EXTS:
                    if file_size > MAX_PHOTO_SIZE or not _is_valid_image(path):
                        await _send_media("document", f, chat_id, context, update, caption)
                    else:
                        try:
                            await _send_media("photo", f, chat_id, context, update, caption)
                        except Exception:
                            log.warning("photo_send_failed_fallback_document", path=path)
                            f.seek(0)
                            await _send_media("document", f, chat_id, context, update, caption)
                elif ext in GIF_EXTS:
                    try:
                        await _send_media("animation", f, chat_id, context, update, caption)
                    except Exception:
                        log.warning("animation_send_failed_fallback_document", path=path)
                        f.seek(0)
                        await _send_media("document", f, chat_id, context, update, caption)
                elif ext in VIDEO_EXTS:
                    await _send_media("video", f, chat_id, context, update, caption)
                elif ext in AUDIO_EXTS:
                    await _send_media("audio", f, chat_id, context, update, caption)
                elif ext in VOICE_EXTS:
                    await _send_media("voice", f, chat_id, context, update, caption)
                else:
                    await _send_media("document", f, chat_id, context, update, caption)
            sent += 1
        except Exception:
            log.exception("artifact_send_error", path=path)

    return sent
