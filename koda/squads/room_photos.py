"""Room (squad-thread) photo storage.

Persists per-thread profile photos as JPEG files on disk under
``STATE_ROOT_DIR/room_photos`` and runs them through a fixed processing
pipeline so we never store user-supplied bytes verbatim:

1. Auto-orient via EXIF (``ImageOps.exif_transpose``)
2. Convert to RGB
3. Center-crop to a square
4. Resize to ``MAX_DIMENSION`` (512 px) with high-quality Lanczos
5. Re-encode as JPEG at quality 88, with EXIF stripped

The processed JPEG bytes are SHA-256 hashed and the prefix is returned as
``content_hash`` so the HTTP layer can mint cache-busting URLs (the file
itself is content-addressed in the URL, not the path — disk lookup stays
``thread_id``-scoped).
"""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path

from koda.config import STATE_ROOT_DIR
from koda.logging_config import get_logger

log = get_logger(__name__)

MAX_DIMENSION = 512
JPEG_QUALITY = 88
MAX_INPUT_BYTES = 12 * 1024 * 1024  # 12 MiB hard cap to fence off DoS uploads
_THREAD_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_PHOTO_DIR_NAME = "room_photos"


@dataclass
class StoredRoomPhoto:
    thread_id: str
    path: Path
    content_hash: str
    byte_size: int


class InvalidPhotoError(ValueError):
    """The uploaded file could not be decoded as an image."""


class PhotoTooLargeError(ValueError):
    """Input bytes exceed ``MAX_INPUT_BYTES``."""


def _ensure_dir() -> Path:
    base = Path(STATE_ROOT_DIR) / _PHOTO_DIR_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def _safe_thread_id(thread_id: str) -> str:
    if not thread_id or not _THREAD_ID_RE.match(thread_id):
        raise ValueError(f"unsafe thread_id for photo storage: {thread_id!r}")
    return thread_id


def photo_path_for(thread_id: str) -> Path:
    safe = _safe_thread_id(thread_id)
    return _ensure_dir() / f"{safe}.jpg"


def save_room_photo(thread_id: str, raw: bytes) -> StoredRoomPhoto:
    """Process ``raw`` and persist it as the photo for ``thread_id``.

    Raises ``InvalidPhotoError`` if the bytes can't be decoded, or
    ``PhotoTooLargeError`` if they exceed ``MAX_INPUT_BYTES``.
    """
    if not raw:
        raise InvalidPhotoError("empty payload")
    if len(raw) > MAX_INPUT_BYTES:
        raise PhotoTooLargeError(f"photo exceeds maximum upload size of {MAX_INPUT_BYTES} bytes")

    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(raw)) as source:
            source.load()
            oriented = ImageOps.exif_transpose(source) or source
            rgb = oriented.convert("RGB")
            short = min(rgb.width, rgb.height)
            left = (rgb.width - short) // 2
            top = (rgb.height - short) // 2
            cropped = rgb.crop((left, top, left + short, top + short))
            target = min(MAX_DIMENSION, short)
            resized = cropped.resize((target, target), Image.Resampling.LANCZOS)
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidPhotoError(f"could not decode image: {exc}") from exc

    buf = io.BytesIO()
    # ``optimize`` finds a smaller-byte Huffman table; ``progressive`` is
    # also smaller for photos at this resolution. EXIF / metadata are
    # not copied into the new buffer, so the upload is implicitly
    # stripped of identifying tags.
    resized.save(
        buf,
        format="JPEG",
        quality=JPEG_QUALITY,
        optimize=True,
        progressive=True,
    )
    encoded = buf.getvalue()
    content_hash = hashlib.sha256(encoded).hexdigest()[:16]

    target_path = photo_path_for(thread_id)
    tmp_path = target_path.with_suffix(".jpg.tmp")
    tmp_path.write_bytes(encoded)
    tmp_path.replace(target_path)

    log.info(
        "room_photo_saved",
        thread_id=thread_id,
        bytes=len(encoded),
        hash=content_hash,
    )
    return StoredRoomPhoto(
        thread_id=thread_id,
        path=target_path,
        content_hash=content_hash,
        byte_size=len(encoded),
    )


def read_room_photo(thread_id: str) -> bytes | None:
    path = photo_path_for(thread_id)
    if not path.exists():
        return None
    return path.read_bytes()


def delete_room_photo(thread_id: str) -> bool:
    path = photo_path_for(thread_id)
    if not path.exists():
        return False
    path.unlink()
    return True
