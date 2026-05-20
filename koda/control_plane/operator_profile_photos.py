"""Operator profile photo storage.

Stores a single processed JPEG per operator under
``STATE_ROOT_DIR/operator_profile_photos``. Uploaded bytes are never persisted
verbatim: the image is decoded, EXIF-oriented, square-cropped, resized, and
re-encoded without metadata before it touches disk.
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
MAX_INPUT_BYTES = 12 * 1024 * 1024
_PHOTO_DIR_NAME = "operator_profile_photos"
_USER_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True, slots=True)
class StoredOperatorProfilePhoto:
    user_id: str
    path: Path
    content_hash: str
    byte_size: int


class InvalidProfilePhotoError(ValueError):
    """The uploaded file could not be decoded as an image."""


class ProfilePhotoTooLargeError(ValueError):
    """Input bytes exceed ``MAX_INPUT_BYTES``."""


def _ensure_dir() -> Path:
    base = Path(STATE_ROOT_DIR) / _PHOTO_DIR_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def _safe_user_id(user_id: str) -> str:
    if not user_id or not _USER_ID_RE.match(user_id):
        raise ValueError(f"unsafe user_id for profile photo storage: {user_id!r}")
    return user_id


def profile_photo_path_for(user_id: str) -> Path:
    return _ensure_dir() / f"{_safe_user_id(user_id)}.jpg"


def save_operator_profile_photo(user_id: str, raw: bytes) -> StoredOperatorProfilePhoto:
    if not raw:
        raise InvalidProfilePhotoError("empty payload")
    if len(raw) > MAX_INPUT_BYTES:
        raise ProfilePhotoTooLargeError(f"photo exceeds maximum upload size of {MAX_INPUT_BYTES} bytes")

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
        raise InvalidProfilePhotoError(f"could not decode image: {exc}") from exc

    buf = io.BytesIO()
    resized.save(
        buf,
        format="JPEG",
        quality=JPEG_QUALITY,
        optimize=True,
        progressive=True,
    )
    encoded = buf.getvalue()
    content_hash = hashlib.sha256(encoded).hexdigest()[:16]

    target_path = profile_photo_path_for(user_id)
    tmp_path = target_path.with_suffix(".jpg.tmp")
    tmp_path.write_bytes(encoded)
    tmp_path.replace(target_path)

    log.info("operator_profile_photo_saved", user_id=user_id, bytes=len(encoded), hash=content_hash)
    return StoredOperatorProfilePhoto(
        user_id=user_id,
        path=target_path,
        content_hash=content_hash,
        byte_size=len(encoded),
    )


def read_operator_profile_photo(user_id: str) -> bytes | None:
    path = profile_photo_path_for(user_id)
    if not path.exists():
        return None
    return path.read_bytes()


def delete_operator_profile_photo(user_id: str) -> bool:
    path = profile_photo_path_for(user_id)
    if not path.exists():
        return False
    path.unlink()
    return True
