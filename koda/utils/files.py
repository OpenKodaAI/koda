"""File operations with path traversal protection."""

import os
import re
from dataclasses import dataclass
from pathlib import Path

from koda.config import FILEOPS_BLOCKED_EXTENSIONS
from koda.logging_config import get_logger
from koda.utils.workdir import sensitive_dir_for

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PathResolution:
    """Decision of :func:`resolve_work_path`: the resolved path, or why it was refused."""

    path: Path | None
    reason: str | None = None
    error: str | None = None


TEMPLATE_FILE_SUFFIXES: frozenset[str] = frozenset({".example", ".sample", ".template", ".dist"})
"""Final extensions that mark a committed, secret-free template of a secret file."""


def blocked_file_suffix(name: str) -> str | None:
    """Return the blocked extension a file name carries, or None.

    A name is blocked when its extension is in ``FILEOPS_BLOCKED_EXTENSIONS``
    (``prod.env``, ``server.pem``), or when it is a dotfile whose first segment is one
    (``.env``, ``.env.local``, ``.env.production``), which ``os.path.splitext`` does not
    report as an extension. A dotfile whose final extension is a template suffix
    (``.env.example``, ``.env.sample``, ``.env.template``, ``.env.dist``) is the
    committed template, not the secret, so it stays readable and editable, as
    ``prod.env.example`` already was.
    """
    lowered = name.lower()
    _, ext = os.path.splitext(lowered)
    if ext in FILEOPS_BLOCKED_EXTENSIONS:
        return ext
    if lowered.startswith(".") and ext not in TEMPLATE_FILE_SUFFIXES:
        stem = "." + lowered[1:].split(".", 1)[0]
        if stem in FILEOPS_BLOCKED_EXTENSIONS:
            return stem
    return None


def resolve_work_path(path_str: str, work_dir: str, *, deny_sensitive_dirs: bool = True) -> PathResolution:
    """Resolve a path for the file commands and the agent file tools.

    This is the single path policy behind ``/cat``, ``/write``, ``/edit``, ``/rm``,
    ``/mkdir``, ``/file``, ``/ls`` and the ``file_*`` agent tools, so the same path gets
    the same decision everywhere:

    - ``~`` is expanded, a relative path is joined with ``work_dir`` (never the process
      CWD), and symlinks are resolved;
    - the result must be ``work_dir`` or inside it (``path_outside_workdir``);
    - it must not be inside a sensitive system directory (``path_sensitive_dir``);
    - neither the requested name nor the name it resolves to may be a blocked secret
      file (``path_blocked_file``, see :func:`blocked_file_suffix`).

    ``deny_sensitive_dirs=False`` skips only the sensitive-directory check, and only the
    file commands pass it: they have never applied that check, and the Docker default
    work directory (``HOME``) sits under ``/var/lib``. The flag changes a decision only
    when the work directory is inside or contains a sensitive directory.
    """
    if not path_str or not path_str.strip():
        return PathResolution(None, "path_missing", "Missing path.")
    try:
        root = os.path.realpath(work_dir)
        requested = os.path.expanduser(path_str)
        resolved = os.path.realpath(os.path.join(root, requested))
    except (OSError, ValueError):
        return _refuse(path_str, work_dir, "path_invalid", f"Access denied: '{path_str}' is not a valid path.")
    if resolved != root and not resolved.startswith(root.rstrip(os.sep) + os.sep):
        return _refuse(
            path_str, work_dir, "path_outside_workdir", f"Access denied: '{path_str}' is outside the working directory."
        )
    sensitive = sensitive_dir_for(resolved) if deny_sensitive_dirs else None
    if sensitive is not None:
        return _refuse(
            path_str, work_dir, "path_sensitive_dir", f"Access denied: '{sensitive}' is a sensitive system directory."
        )
    if resolved != root:
        suffix = blocked_file_suffix(os.path.basename(requested.rstrip(os.sep))) or blocked_file_suffix(
            os.path.basename(resolved)
        )
        if suffix is not None:
            return _refuse(
                path_str,
                work_dir,
                "path_blocked_file",
                f"Access denied: files with extension '{suffix}' are blocked for safety.",
            )
    return PathResolution(Path(resolved))


def _refuse(path_str: str, work_dir: str, reason: str, error: str) -> PathResolution:
    log.warning("path_access_blocked", reason=reason, path=path_str, work_dir=work_dir)
    return PathResolution(None, reason, error)


def list_directory(path_str: str | None, work_dir: str) -> tuple[str, bool]:
    """List contents of a directory within work_dir.

    Returns (listing_text, success).
    """
    if path_str:
        resolution = resolve_work_path(path_str, work_dir, deny_sensitive_dirs=False)
        if resolution.path is None:
            return resolution.error or "Access denied.", False
        target = resolution.path
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
    resolution = resolve_work_path(path_str, work_dir, deny_sensitive_dirs=False)
    if resolution.path is None:
        return resolution.error or "Access denied."
    target = resolution.path

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return f"Written to: {path_str} ({len(content)} bytes)"
    except Exception as e:
        return f"Error writing file: {e}"


def safe_delete(path_str: str, work_dir: str) -> str:
    """Delete a file within work_dir. Returns status message."""
    resolution = resolve_work_path(path_str, work_dir, deny_sensitive_dirs=False)
    if resolution.path is None:
        return resolution.error or "Access denied."
    target = resolution.path

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
    resolution = resolve_work_path(path_str, work_dir, deny_sensitive_dirs=False)
    if resolution.path is None:
        return resolution.error or "Access denied."
    target = resolution.path

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
