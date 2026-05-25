"""File operations with path traversal protection."""

import os
import re
from pathlib import Path

from koda.logging_config import get_logger

log = get_logger(__name__)


def safe_resolve(path_str: str, work_dir: str) -> Path | None:
    """Resolve a path safely within work_dir.

    Returns the resolved Path if it's inside work_dir, or None if path traversal detected.
    """
    work_dir_resolved = Path(work_dir).resolve()

    # Handle relative and absolute paths
    if os.path.isabs(path_str):
        target = Path(path_str).resolve()
    else:
        target = (work_dir_resolved / path_str).resolve()

    # Check that target is inside work_dir
    try:
        target.relative_to(work_dir_resolved)
    except ValueError:
        log.warning("path_traversal_blocked", path=path_str, work_dir=work_dir)
        return None

    return target


def list_directory(path_str: str | None, work_dir: str) -> tuple[str, bool]:
    """List contents of a directory within work_dir.

    Returns (listing_text, success).
    """
    if path_str:
        target = safe_resolve(path_str, work_dir)
        if target is None:
            return "Access denied: path is outside working directory.", False
    else:
        target = Path(work_dir)

    if not target.exists():
        return f"Path not found: {path_str}", False

    if not target.is_dir():
        return f"Not a directory: {path_str}", False

    try:
        entries = sorted(target.iterdir())
    except PermissionError:
        return "Permission denied.", False

    if not entries:
        return "(empty directory)", True

    lines: list[str] = []
    for entry in entries:
        if entry.is_dir():
            lines.append(f"📁 {entry.name}/")
        else:
            size = entry.stat().st_size
            if size < 1024:
                size_str = f"{size}B"
            elif size < 1024 * 1024:
                size_str = f"{size / 1024:.1f}KB"
            else:
                size_str = f"{size / (1024 * 1024):.1f}MB"
            lines.append(f"📄 {entry.name} ({size_str})")

    return "\n".join(lines), True


def safe_write(path_str: str, content: str, work_dir: str) -> str:
    """Write content to a file within work_dir. Returns status message."""
    target = safe_resolve(path_str, work_dir)
    if target is None:
        return "Access denied: path is outside working directory."

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return f"Written to: {path_str} ({len(content)} bytes)"
    except Exception as e:
        return f"Error writing file: {e}"


def safe_delete(path_str: str, work_dir: str) -> str:
    """Delete a file within work_dir. Returns status message."""
    target = safe_resolve(path_str, work_dir)
    if target is None:
        return "Access denied: path is outside working directory."

    if not target.exists():
        return f"File not found: {path_str}"

    if target.is_dir():
        return "Cannot delete directories. Use shell if needed."

    try:
        target.unlink()
        return f"Deleted: {path_str}"
    except Exception as e:
        return f"Error deleting file: {e}"


def safe_read(path_str: str, work_dir: str, max_size: int = 100_000) -> str:
    """Read a file within work_dir. Returns file content or error."""
    target = safe_resolve(path_str, work_dir)
    if target is None:
        return "Access denied: path is outside working directory."

    if not target.exists():
        return f"File not found: {path_str}"

    if target.is_dir():
        return "That's a directory. Use /ls to list contents."

    size = target.stat().st_size
    if size > max_size:
        return f"File too large ({size} bytes). Max readable size is {max_size} bytes."

    try:
        return target.read_text(errors="replace")
    except Exception as e:
        return f"Error reading file: {e}"


_SECRET_PATTERN = re.compile(
    r"^(?:[\w]+_)?(?:secret|password|token|api_key|private_key|access_key)\s*[:=]",
    re.MULTILINE | re.IGNORECASE,
)

_JSON_SECRET_KEYS = frozenset({"private_key", "client_secret", "access_token", "refresh_token", "api_key"})


def validate_file_content_safety(path: str) -> str | None:
    """Return an error message if file content looks like secrets/credentials, else None."""
    try:
        with open(path, "rb") as f:
            head = f.read(512)
    except OSError:
        return None  # Can't read — let the caller handle

    try:
        text = head.decode("utf-8", errors="ignore").lower()
    except Exception:
        return None

    # PEM-format key/certificate detection
    if text.lstrip().startswith("-----begin"):
        return "File appears to contain a PEM-encoded key or certificate."

    # .env-style secret patterns (at least 2 matches = likely credentials file)
    if len(_SECRET_PATTERN.findall(text)) >= 2:
        return "File appears to contain credentials or secrets."

    # JSON credential patterns
    for key in _JSON_SECRET_KEYS:
        if f'"{key}"' in text:
            return "File appears to contain JSON credentials."

    return None
