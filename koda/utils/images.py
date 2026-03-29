"""Image download and management utilities.

Bug fix: cleanup uses a tracked set of in-flight image paths
instead of draining the queue (which had a race condition).
"""

import asyncio
import contextlib
import time
from pathlib import Path

from telegram import Update

from koda.config import DEFAULT_IMAGE_PROMPT, IMAGE_TEMP_DIR
from koda.logging_config import get_logger
from koda.utils.command_helpers import require_message, require_user_id

log = get_logger(__name__)

# Track image paths that are currently queued for processing.
# Paths are added when enqueued and removed after processing completes.
_in_flight_images: set[str] = set()


def track_images(paths: list[str]) -> None:
    """Mark image paths as in-flight (queued for processing)."""
    _in_flight_images.update(paths)


def untrack_images(paths: list[str] | None) -> None:
    """Remove image paths from in-flight tracking."""
    if paths:
        _in_flight_images.difference_update(paths)


async def download_photos(update: Update) -> list[str]:
    """Download photo(s) from a message and return local file paths."""
    message = require_message(update)
    paths: list[str] = []
    uid = require_user_id(update)
    msg_id = message.message_id

    if message.photo:
        photo = message.photo[-1]
        file = await photo.get_file()
        dest = IMAGE_TEMP_DIR / f"{uid}_{msg_id}.jpg"
        await file.download_to_drive(str(dest))
        paths.append(str(dest))
    elif message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
        file = await message.document.get_file()
        ext = Path(message.document.file_name or "img.jpg").suffix or ".jpg"
        dest = IMAGE_TEMP_DIR / f"{uid}_{msg_id}{ext}"
        await file.download_to_drive(str(dest))
        paths.append(str(dest))

    return paths


def build_image_prompt(caption: str | None, paths: list[str]) -> str:
    """Build a prompt that asks the provider runtime to analyze the given image files."""
    text = caption or DEFAULT_IMAGE_PROMPT
    file_refs = "\n".join(f"Read and analyze the image at {p}" for p in paths)
    return f"{file_refs}\n\n{text}"


def cleanup_previous_images(user_data: dict) -> None:
    """Delete image files from previous query if not still in-flight.

    Uses module-level _in_flight_images set instead of draining the queue,
    which avoids the race condition with the concurrent queue worker.
    """
    last = user_data.get("last_query")
    if not last or not last.get("image_paths"):
        return

    for p in last["image_paths"]:
        if p not in _in_flight_images:
            with contextlib.suppress(Exception):
                Path(p).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Periodic cleanup of stale temp files
# ---------------------------------------------------------------------------

_CLEANUP_INTERVAL_SEC = 1800  # 30 minutes
_CLEANUP_MAX_AGE_SEC = 3600  # 1 hour


async def start_temp_cleanup_loop() -> None:
    """Periodically delete temp files older than 1 hour from IMAGE_TEMP_DIR.

    Skips files that are currently in-flight. Runs every 30 minutes.
    """
    while True:
        await asyncio.sleep(_CLEANUP_INTERVAL_SEC)
        try:
            _cleanup_stale_files()
        except Exception:
            log.exception("temp_cleanup_error")


def _cleanup_stale_files() -> None:
    """Delete files in IMAGE_TEMP_DIR older than _CLEANUP_MAX_AGE_SEC."""
    if not IMAGE_TEMP_DIR.is_dir():
        return

    now = time.time()
    removed = 0
    for path in IMAGE_TEMP_DIR.iterdir():
        if not path.is_file():
            continue
        if str(path) in _in_flight_images:
            continue
        try:
            age = now - path.stat().st_mtime
            if age > _CLEANUP_MAX_AGE_SEC:
                path.unlink(missing_ok=True)
                removed += 1
        except Exception:
            continue

    if removed > 0:
        log.info("temp_cleanup_complete", removed=removed)
