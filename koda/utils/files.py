"""File operations with path traversal protection."""

import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from koda.agent_contract import FILE_COMMAND_ACCESS_LEVELS
from koda.config import FILEOPS_BLOCKED_CREDENTIAL_PATHS, FILEOPS_BLOCKED_EXTENSIONS
from koda.logging_config import get_logger
from koda.utils.workdir import control_plane_state_dir_for, sensitive_dir_for

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


def blocked_credential_path(path: str) -> str | None:
    """Return the ``FILEOPS_BLOCKED_CREDENTIAL_PATHS`` entry that ``path`` is, or is inside.

    ``path`` is absolute and normalised. A directory entry (``.ssh/``, ``.aws/``) matches
    that directory and every path below it, wherever it appears in ``path``; a file entry
    (``.codex/auth.json``, ``.netrc``) matches the last components of ``path``. Components
    are compared case-insensitively, as a case-insensitive filesystem would open them.
    These are the credential stores that the CLIs sharing the runtime HOME keep there, and
    in the Docker layout HOME is the work dir. Returns None for any other path.
    """
    parts = [part.lower() for part in path.split(os.sep) if part]
    for entry in FILEOPS_BLOCKED_CREDENTIAL_PATHS:
        entry_parts = [part.lower() for part in entry.split("/") if part]
        size = len(entry_parts)
        if entry.endswith("/"):
            if any(parts[start : start + size] == entry_parts for start in range(len(parts) - size + 1)):
                return entry
        elif parts[-size:] == entry_parts:
            return entry
    return None


def secret_file_refusal(path: str) -> str | None:
    """Return why ``path`` (absolute, normalised) is a secret file the file layer refuses, or None.

    It is the one secret-file policy: a blocked extension or ``.env`` dotfile
    (:func:`blocked_file_suffix`), or a CLI credential store (:func:`blocked_credential_path`).
    """
    suffix = blocked_file_suffix(os.path.basename(path))
    if suffix is not None:
        return f"files with extension '{suffix}' are blocked for safety"
    credential = blocked_credential_path(path)
    if credential is not None:
        return f"'{credential}' is a credential store, blocked for safety"
    return None


def _children_named(directory: str, name: str) -> list[str]:
    """Return the entries of ``directory`` named ``name``, ignoring case as the policy compares names."""
    try:
        with os.scandir(directory) as entries:
            return [entry.path for entry in entries if entry.name.lower() == name]
    except OSError:
        return []


def secret_move_refusal(source: str, destination: str) -> str | None:
    """Return why moving ``source`` to ``destination`` would unblock a secret below it, or None.

    Both paths are absolute and resolved, and each passed :func:`resolve_work_path`, so
    neither is a secret file itself. ``destination`` is where ``source`` ends up (for
    ``shutil.move`` into an existing directory, the path inside it). A blocked extension or
    ``.env`` name goes with the file wherever it moves, and so does a credential entry that
    lies wholly below ``source``. But a credential entry with several components is also
    matched on the names of the directories above the file (``.codex/auth.json``,
    ``.config/gh/hosts.yml``, ``.config/gcloud/``). When ``source`` ends with the first
    components of such an entry and holds the rest, moving or renaming ``source`` could
    leave that store under a name the policy does not recognise, and the read tools would
    return it. So each such path below ``source`` must still be refused
    (:func:`secret_file_refusal`) at its new place.
    """
    source = source.rstrip(os.sep) or os.sep
    source_parts = [part.lower() for part in source.split(os.sep) if part]
    for entry in FILEOPS_BLOCKED_CREDENTIAL_PATHS:
        entry_parts = [part.lower() for part in entry.split("/") if part]
        for split in range(1, len(entry_parts)):
            if source_parts[-split:] != entry_parts[:split]:
                continue
            below = [source]
            for name in entry_parts[split:]:
                below = [child for directory in below for child in _children_named(directory, name)]
            for path in below:
                refusal = secret_file_refusal(path)
                moved = destination.rstrip(os.sep) + path[len(source) :]
                if refusal is not None and secret_file_refusal(moved) is None:
                    inner = os.path.relpath(path, os.path.dirname(source))
                    return f"the move would take '{inner}' out of the name that blocks it ({refusal})"
    return None


def work_path_location(path_str: str, work_dir: str) -> str:
    """Return the absolute, symlink-resolved path that ``path_str`` names under ``work_dir``.

    This is the path :func:`resolve_work_path` checks: ``~`` is expanded, a relative path
    is joined with ``work_dir`` (never the process CWD), and symlinks are resolved. It
    makes no access decision. Raises ``OSError`` or ``ValueError`` for a path that cannot
    be resolved.
    """
    return os.path.realpath(os.path.join(os.path.realpath(work_dir), os.path.expanduser(path_str)))


FILE_COMMANDS: frozenset[str] = frozenset(FILE_COMMAND_ACCESS_LEVELS)
"""Telegram commands that act on one path in the work dir, grant-gated by the approval layer.

They are the commands of ``koda.agent_contract.FILE_COMMAND_ACCESS_LEVELS``, which gives
each its ``fileops`` access level.
"""

_FILE_COMMANDS_WITH_CONTENT: frozenset[str] = frozenset({"write", "edit"})


def file_command_path(command: str, args: Sequence[str] | None) -> str:
    """Return the path a Telegram file command acts on, parsed from its arguments.

    ``/write`` and ``/edit`` take ``<path> <content>``, so the path is the first argument.
    ``/cat``, ``/file``, ``/rm``, ``/mkdir`` and ``/ls`` take one path, which may contain
    spaces, so it is every argument joined by a space; ``/ls`` without one lists the work
    dir, ``"."``. Arguments are never shell-split or unquoted. The handlers and the
    approval gate (:func:`koda.utils.approval.with_approval`) both take the path from
    here, so the integration grant decides on the path that the handler then resolves and
    acts on. Returns ``""`` when the command names no path.
    """
    items = [str(item) for item in args or []]
    if command in _FILE_COMMANDS_WITH_CONTENT:
        return items[0] if items else ""
    joined = " ".join(items)
    if command == "ls" and not joined.strip():
        return "."
    return joined


NO_WORK_DIR_MESSAGE = "No working directory is set. Use /setdir first."
"""What a file command replies when :func:`file_command_work_dir` finds no work dir."""


def file_command_work_dir(user_data: Mapping[str, Any]) -> str | None:
    """Return the work dir the file commands resolve their path in, exactly as stored, or None.

    The handlers, the approval gate (:func:`koda.utils.approval.with_approval`) and the
    re-check when a confirmation is approved all read it here, so the grant checks the
    path the handler acts on. The value is not stripped: ``/setdir`` and
    ``agent_set_workdir`` store the validated directory as it is, and a directory whose
    name ends in a space is not the one without it. None when no work dir is set (missing,
    not a string, or blank); the handlers then refuse to run.
    """
    work_dir = user_data.get("work_dir")
    if not isinstance(work_dir, str) or not work_dir.strip():
        return None
    return work_dir


def resolve_work_path(
    path_str: str,
    work_dir: str,
    *,
    deny_sensitive_dirs: bool = True,
    deny_sensitive_work_dir: bool = False,
) -> PathResolution:
    """Resolve a path for the file commands and the agent file tools.

    This is the single path policy behind ``/cat``, ``/write``, ``/edit``, ``/rm``,
    ``/mkdir``, ``/file``, ``/ls``, the ``file_*`` agent tools and ``browser_upload``, so
    the same path gets the same decision everywhere:

    - ``~`` is expanded, a relative path is joined with ``work_dir`` (never the process
      CWD), and symlinks are resolved (:func:`work_path_location`);
    - the result must be ``work_dir`` or inside it (``path_outside_workdir``);
    - it must not be inside a sensitive system directory or the control-plane state
      directory (``path_sensitive_dir``, see :func:`koda.utils.workdir.sensitive_dir_for`),
      except the sensitive directories one of Koda's runtime roots is configured under,
      when ``work_dir`` is that runtime root or below it: the Docker default ``HOME`` under
      ``/var/lib`` and the paths inside it stay usable;
    - neither the requested path nor the path it resolves to may be a secret file
      (``path_blocked_file``, see :func:`secret_file_refusal`): a blocked extension, a
      ``.env`` dotfile, or a CLI credential store such as ``.ssh/`` or ``.netrc``.

    ``work_dir`` is the work dir the runtime chose for the caller: every entry point
    validates it (:func:`koda.utils.workdir.validate_work_dir`), or it is the operator's
    ``DEFAULT_WORK_DIR``.

    ``deny_sensitive_dirs=False`` skips only the ``SENSITIVE_DIRS`` check, never the
    control-plane state directory, which is refused for every caller
    (:func:`koda.utils.workdir.control_plane_state_dir_for`). The file commands and
    ``browser_upload`` pass it: they have never applied that check, and anything else
    inside the work dir stays uploadable. It changes a decision only for a path inside a
    sensitive directory that is not waived: one inside the work dir (a work dir of ``/``
    contains ``/etc``), or one a validated work dir resolves into later, through a
    symlink. ``deny_sensitive_work_dir=True``, which ``browser_upload`` passes with it,
    keeps the check for the work dir itself: a work dir that resolves into a sensitive
    directory it is not waived for, such as a validated work dir later replaced with a
    symlink into ``/etc``, refuses every path, while a sensitive directory inside the work
    dir stays reachable.
    """
    if not path_str or not path_str.strip():
        return PathResolution(None, "path_missing", "Missing path.")
    try:
        root = os.path.realpath(work_dir)
        requested = os.path.expanduser(path_str)
        resolved = work_path_location(path_str, root)
    except (OSError, ValueError):
        return _refuse(path_str, work_dir, "path_invalid", f"Access denied: '{path_str}' is not a valid path.")
    if resolved != root and not resolved.startswith(root.rstrip(os.sep) + os.sep):
        return _refuse(
            path_str, work_dir, "path_outside_workdir", f"Access denied: '{path_str}' is outside the working directory."
        )
    if deny_sensitive_dirs:
        sensitive = sensitive_dir_for(resolved, work_dir=root)
    else:
        # The control-plane state directory is never waived, whatever the caller skips.
        sensitive = control_plane_state_dir_for(resolved)
        if sensitive is None and deny_sensitive_work_dir:
            sensitive = sensitive_dir_for(root, work_dir=root)
    if sensitive is not None:
        return _refuse(
            path_str, work_dir, "path_sensitive_dir", f"Access denied: '{sensitive}' is a sensitive system directory."
        )
    if resolved != root:
        refusal = secret_file_refusal(os.path.normpath(os.path.join(root, requested))) or secret_file_refusal(resolved)
        if refusal is not None:
            return _refuse(path_str, work_dir, "path_blocked_file", f"Access denied: {refusal}.")
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
