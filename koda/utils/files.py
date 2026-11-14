"""File operations with path traversal protection."""

import os
import re
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from koda.agent_contract import FILE_COMMAND_ACCESS_LEVELS
from koda.config import (
    FILEOPS_BLOCKED_CREDENTIAL_PATHS,
    FILEOPS_BLOCKED_EXTENSIONS,
    FILEOPS_CREDENTIAL_COPY_SUFFIXES,
    FILEOPS_CREDENTIAL_NAME_PREFIXES,
    FILEOPS_CREDENTIAL_TEMP_COPIES,
)
from koda.logging_config import get_logger
from koda.utils.workdir import protected_dir_for, protected_dir_within, sensitive_dir_for

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PathResolution:
    """Decision of :func:`resolve_work_path`: the resolved path, or why it was refused."""

    path: Path | None
    reason: str | None = None
    error: str | None = None


TEMPLATE_FILE_SUFFIXES: frozenset[str] = frozenset({".example", ".sample", ".template", ".dist"})
"""Final extensions that mark a committed, secret-free template of a secret file."""


_COPY_SUFFIX = re.compile("|".join(rf"{re.escape(suffix)}(?=\.|$)" for suffix in FILEOPS_CREDENTIAL_COPY_SUFFIXES))
"""Where a lowered file name carries a copy suffix: ``.tmp`` followed by a dot or the end of the name."""


def _name_pattern(name: str, *, lowered: bool) -> str:
    """Return the regular expression of a credential file name as ``koda.config`` writes it.

    ``*`` stands for one or more characters and ``?`` for one ASCII letter or digit (a Rust
    tempfile's random characters); every other character stands for itself. With
    ``lowered``, the expression is for a lowered name, as the file layer compares names.
    """
    alnum = "[0-9a-z]" if lowered else "[0-9A-Za-z]"
    wildcards = {"*": ".+", "?": alnum}
    return "".join(wildcards.get(char) or re.escape(char) for char in (name.lower() if lowered else name))


_TEMP_COPY_NAMES: dict[str, tuple[re.Pattern[str], ...]] = {
    entry: tuple(re.compile(_name_pattern(name, lowered=True)) for name in names)
    for entry, names in FILEOPS_CREDENTIAL_TEMP_COPIES.items()
}
"""``FILEOPS_CREDENTIAL_TEMP_COPIES`` as patterns of a whole lowered name, which the file layer compares."""

_TEMP_COPY_EXACT_NAMES: dict[str, tuple[re.Pattern[str], ...]] = {
    entry: tuple(re.compile(_name_pattern(name, lowered=False)) for name in names)
    for entry, names in FILEOPS_CREDENTIAL_TEMP_COPIES.items()
}
"""``FILEOPS_CREDENTIAL_TEMP_COPIES`` as patterns of a whole name as the CLI writes it, which the logout deletes."""

_CREDENTIAL_FILE_NAMES: dict[str, re.Pattern[str]] = {
    entry: re.compile(
        _name_pattern(entry.rsplit("/", 1)[-1], lowered=True)
        + "(?:(?:"
        + "|".join(re.escape(suffix) for suffix in FILEOPS_CREDENTIAL_COPY_SUFFIXES)
        + r")(?:\.[\s\S]*)?)?"
    )
    for entry in FILEOPS_BLOCKED_CREDENTIAL_PATHS
    if not entry.endswith("/")
}
"""Each file entry's name, or that name followed by a copy suffix, as a pattern of a whole lowered name."""


def credential_temp_copies(directory: Path, entry: str) -> list[Path]:
    """Return the temp copies of the credential file ``entry`` that sit in ``directory``.

    ``entry`` is a file entry of ``FILEOPS_BLOCKED_CREDENTIAL_PATHS`` and ``directory`` the
    dir that holds that file, in HOME or where the environment moves the CLI's config dir. A
    temp copy is a file (not a directory) whose whole name is one of the names
    ``FILEOPS_CREDENTIAL_TEMP_COPIES`` gives for ``entry``, as the CLI writes it, case
    included: ``.auth-wQZHMQ`` beside ``.codex/auth.json``, ``.tmpafU0fU`` beside
    ``.codex/secrets/gateway_oauth.json``. Disconnecting a provider deletes these with the
    files they copy, and no other file, so a near miss (``.auth-``, ``auth-wQZHMQ``,
    ``.auth-x.example``, ``.tmp-notes.md``) or another file's temp copy in the same dir is
    not returned. An unreadable dir has none.
    """
    patterns = _TEMP_COPY_EXACT_NAMES.get(entry, ())
    if not patterns:
        return []
    try:
        with os.scandir(directory) as children:
            return [
                Path(child.path)
                for child in children
                if any(pattern.fullmatch(child.name) for pattern in patterns)
                and not child.is_dir(follow_symlinks=False)
            ]
    except OSError:
        return []


def _blocked_extension(lowered: str) -> str | None:
    """Return the blocked extension the lowered file name ``lowered`` itself carries, or None."""
    _, ext = os.path.splitext(lowered)
    if ext in FILEOPS_BLOCKED_EXTENSIONS:
        return ext
    if lowered.startswith(".") and ext not in TEMPLATE_FILE_SUFFIXES:
        stem = "." + lowered[1:].split(".", 1)[0]
        if stem in FILEOPS_BLOCKED_EXTENSIONS:
            return stem
    return None


def blocked_file_suffix(name: str) -> str | None:
    """Return the blocked extension a file name carries, or None.

    A name is blocked when its extension is in ``FILEOPS_BLOCKED_EXTENSIONS``
    (``prod.env``, ``server.pem``), or when it is a dotfile whose first segment is one
    (``.env``, ``.env.local``, ``.env.production``), which ``os.path.splitext`` does not
    report as an extension. A dotfile whose final extension is a template suffix
    (``.env.example``, ``.env.sample``, ``.env.template``, ``.env.dist``) is the
    committed template, not the secret, so it stays readable and editable, as
    ``prod.env.example`` already was. A copy a CLI writes of a blocked file holds the same
    secret, and its own extension is the copy's suffix: the blocked name followed by one of
    ``FILEOPS_CREDENTIAL_COPY_SUFFIXES`` and, optionally, a dot and any further suffix
    (``control.key.tmp.a1b2c3d4``, ``key.pem.tmp.4242``, ``prod.env.backup``) is blocked as
    that name is; ``server.key.example.backup`` and ``control.key.tmpx`` are not. Nor is a
    name whose final extension is a template suffix, whatever comes before it
    (``.env.backup.example``, ``prod.env.backup.dist``): that is a committed template, as
    ``.env.example`` is, and no CLI names a copy that way.
    """
    lowered = name.lower()
    found = _blocked_extension(lowered)
    if found is not None:
        return found
    if os.path.splitext(lowered)[1] in TEMPLATE_FILE_SUFFIXES:
        return None
    for copy in _COPY_SUFFIX.finditer(lowered):
        if copy.start() > 0 and (found := _blocked_extension(lowered[: copy.start()])) is not None:
            return found
    return None


def _names_credential_file(name: str, entry: str) -> bool:
    """Return whether the lowered ``name`` is the file of the credential file ``entry`` or a copy of it.

    ``entry`` is a file entry of ``FILEOPS_BLOCKED_CREDENTIAL_PATHS``, whose name may hold
    the wildcards :func:`_name_pattern` reads (``*.config.toml`` of ``.codex/*.config.toml``
    is ``work.config.toml``). A copy is the file name followed by one of
    ``FILEOPS_CREDENTIAL_COPY_SUFFIXES`` and, optionally, a dot and any further suffix
    (``.claude.json.backup``, ``.claude.json.backup.1763100000000``,
    ``.claude.json.tmp.a1b2c3d4``, ``.mcp.json.tmp.4452.b78c150b3d83``), as Claude Code
    writes them; ``.claude.json.example`` and ``.claude.json.backupx`` are not. It is also a
    temp copy that the CLI owning ``entry`` writes the file through, by the name
    ``FILEOPS_CREDENTIAL_TEMP_COPIES`` gives it (``.oauth_creds.json.4242.1763100000000.0.tmp``
    of ``.gemini/oauth_creds.json``, ``.auth-wqzhmq`` of ``.codex/auth.json``, ``.tmpafu0fu``
    of ``.codex/secrets/gateway_oauth.json``), which the caller matches beside that file.
    """
    own = _CREDENTIAL_FILE_NAMES.get(entry)
    if own is not None and own.fullmatch(name):
        return True
    return any(copy.fullmatch(name) for copy in _TEMP_COPY_NAMES.get(entry, ()))


def blocked_credential_path(path: str) -> str | None:
    """Return the ``FILEOPS_BLOCKED_CREDENTIAL_PATHS`` entry that ``path`` is, or is inside.

    ``path`` is absolute and normalised. A directory entry (``.ssh/``, ``.aws/``) matches
    that directory and every path below it, wherever it appears in ``path``; a file entry
    (``.codex/auth.json``, ``.netrc``, ``.codex/*.config.toml``) matches the last components
    of ``path``, the last one being that file's name (a ``*`` in it one or more characters)
    or the name of a copy a CLI writes of it
    (:func:`_names_credential_file`: ``.claude.json.backup.1763100000000`` in any
    ``backups/`` is ``.claude.json``, and ``.gemini/.oauth_creds.json.4242.1763100000000.0.tmp``
    is ``.gemini/oauth_creds.json``). Components are compared case-insensitively, as a
    case-insensitive filesystem would open them. A file whose name is one of
    ``FILEOPS_CREDENTIAL_NAME_PREFIXES``, or one of them followed by a dot and any further
    suffix (``.session_ingress_token.e3``), matches that prefix wherever it sits. These are
    the credential stores that the CLIs sharing the runtime HOME keep there, and in the
    Docker layout HOME is the work dir. Returns None for any other path.
    """
    parts = [part.lower() for part in path.split(os.sep) if part]
    name = parts[-1] if parts else ""
    for prefix in FILEOPS_CREDENTIAL_NAME_PREFIXES:
        lowered_prefix = prefix.lower()
        if name == lowered_prefix or name.startswith(lowered_prefix + "."):
            return prefix
    for entry in FILEOPS_BLOCKED_CREDENTIAL_PATHS:
        entry_parts = [part.lower() for part in entry.split("/") if part]
        size = len(entry_parts)
        if entry.endswith("/"):
            if any(parts[start : start + size] == entry_parts for start in range(len(parts) - size + 1)):
                return entry
        elif (
            len(parts) >= size
            and parts[len(parts) - size : -1] == entry_parts[:-1]
            and _names_credential_file(parts[-1], entry)
        ):
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


def _children_named(directory: str, name: str, *, copies_of: str | None = None) -> list[str]:
    """Return the entries of ``directory`` named ``name``, ignoring case as the policy compares names.

    With ``copies_of``, ``name`` is the name of that credential file entry's file, and the
    copies a CLI writes of it beside it (:func:`_names_credential_file`) are returned too.
    """
    try:
        with os.scandir(directory) as children:
            return [
                child.path
                for child in children
                if child.name.lower() == name
                or (copies_of is not None and _names_credential_file(child.name.lower(), copies_of))
            ]
    except OSError:
        return []


def _entry_completions(location: str, directory: str) -> list[str]:
    """Return the paths below ``directory`` that complete a credential entry ``location`` begins.

    A credential entry with several components is also matched on the names of the
    directories above the file (``.codex/auth.json``, ``.config/gh/hosts.yml``,
    ``.config/gcloud/``). For each such entry whose first components ``location`` (absolute
    and normalised) ends with, this returns the paths below ``directory`` named as the rest
    of it, and the copies a CLI writes beside such a file
    (``.claude/.config.json.tmp.a1b2c3d4``, ``.gemini/.oauth_creds.json.4242.1763100000000.0.tmp``).
    ``directory`` is ``location`` itself, or the directory a move puts at ``location``.
    """
    location_parts = [part.lower() for part in location.split(os.sep) if part]
    found: list[str] = []
    for entry in FILEOPS_BLOCKED_CREDENTIAL_PATHS:
        entry_parts = [part.lower() for part in entry.split("/") if part]
        for split in range(1, len(entry_parts)):
            if location_parts[-split:] != entry_parts[:split]:
                continue
            below = [directory]
            for index, name in enumerate(entry_parts[split:], start=split):
                copies_of = entry if index == len(entry_parts) - 1 and not entry.endswith("/") else None
                below = [child for parent in below for child in _children_named(parent, name, copies_of=copies_of)]
            found.extend(below)
    return found


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
    return it. So each such path below ``source``, and each copy a CLI writes beside such a
    file (``.claude/.config.json.tmp.a1b2c3d4``), must still be refused
    (:func:`secret_file_refusal`) at its new place. The other direction, a move that puts
    data at a store's name, is :func:`planted_secret_refusal`.
    """
    source = source.rstrip(os.sep) or os.sep
    for path in _entry_completions(source, source):
        refusal = secret_file_refusal(path)
        moved = destination.rstrip(os.sep) + path[len(source) :]
        if refusal is not None and secret_file_refusal(moved) is None:
            inner = os.path.relpath(path, os.path.dirname(source))
            return f"the move would take '{inner}' out of the name that blocks it ({refusal})"
    return None


def planted_secret_refusal(source: str, destination: str) -> str | None:
    """Return why moving ``source`` to ``destination`` would put data at a secret file's name, or None.

    Both paths are absolute and resolved, and ``source`` passed :func:`resolve_work_path`.
    ``destination`` is where ``source`` ends up (:func:`move_landing`): into an existing
    directory, the path inside it, which :func:`resolve_work_path` never saw. A secret file
    is unreadable, but the CLI that owns it reads it, so a move must not create one, as
    ``file_write`` must not: ``auth.json`` moved into an existing ``.codex`` would land at
    ``.codex/auth.json`` and replace the Codex login, ``staging/daemon`` moved into
    ``.claude`` would plant ``.claude/daemon/roster.json``, and a kubeconfig exec plugin or
    a docker ``credHelpers`` entry moved into ``.kube`` or ``.docker`` would run a command
    the next time that CLI is used. A directory renamed to ``.codex``, ``.claude`` or
    ``.config`` would do the same with what it holds (:func:`_entry_completions`). So the
    move is refused when ``destination``, or a path below it, is a secret file
    (:func:`secret_file_refusal`) and was not one at its place below ``source``. A secret
    that keeps a refused name where it lands (``.codex`` moved into ``backup/``) still moves,
    and a file's own extension and name go with it, so those cannot change.
    """
    source = source.rstrip(os.sep) or os.sep
    destination = destination.rstrip(os.sep) or os.sep
    moves = [(source, destination)]
    moves += [(path, destination + path[len(source) :]) for path in _entry_completions(destination, source)]
    for path, moved in moves:
        refusal = secret_file_refusal(moved)
        if refusal is not None and secret_file_refusal(path) is None:
            inner = os.path.relpath(moved, os.path.dirname(destination))
            return f"the move would put data at '{inner}' ({refusal})"
    return None


def protected_move_refusal(source: str, destination: str) -> str | None:
    """Return why moving ``source`` to ``destination`` would move a protected directory, or None.

    Both paths are absolute and resolved. ``source`` and the destination the caller named
    passed :func:`resolve_work_path`, so neither lies inside one of the
    :func:`koda.utils.workdir.protected_dirs` (the control-plane state directory, the
    browser's saved sessions, ``CLAUDE_CONFIG_DIR`` and ``CODEX_HOME`` where the environment
    sets them, the Claude Code config dir the compose files configure,
    ``/var/lib/koda/runtime/claude-config``, in every process whatever its environment sets,
    and the Anthropic profile credential dirs the environment names). ``destination`` is where
    ``source`` ends up (for ``shutil.move`` into an existing directory, the path inside it).
    A protected directory is recognised by its location, not its name, compared ignoring
    case, so the move is refused (:func:`koda.utils.workdir.protected_dir_within`):

    - when ``source`` is, or contains, a protected directory (``.koda-state`` holds
      ``control_plane``): the move would take its data to a path no check recognises, and
      the read tools would return it there;
    - when ``destination`` is, contains or lies inside a protected directory: the move would
      put the moved data where Koda or a CLI reads that directory from, such as a planted
      bootstrap code or browser session.

    Every other move is left to :func:`secret_move_refusal`, :func:`planted_secret_refusal`
    and :func:`linked_landing_refusal`.
    """
    moved = protected_dir_within(source)
    if moved is not None:
        return f"'{moved}' is a sensitive system directory, and the move would take it out of its place"
    target = protected_dir_for(destination) or protected_dir_within(destination)
    if target is not None:
        return f"'{target}' is a sensitive system directory, and the move would put data in its place"
    return None


def move_landing(source: str, destination: str) -> str:
    """Return the path where ``shutil.move(source, destination)`` puts ``source``.

    Both paths are absolute and resolved. Into an existing destination directory,
    ``shutil.move`` puts the source at its base name inside it; anywhere else, at
    ``destination`` itself. The move checks (:func:`protected_move_refusal`,
    :func:`secret_move_refusal`, :func:`planted_secret_refusal`,
    :func:`linked_landing_refusal`) are made on that path.
    """
    if os.path.isdir(destination):
        return os.path.join(destination, os.path.basename(source.rstrip(os.sep)))
    return destination


def linked_landing_refusal(landing: str) -> str | None:
    """Return why a move must not land at ``landing``, a link to another file, or None.

    ``landing`` is the path :func:`move_landing` returns, below a resolved destination, so
    only its last component can be a link. A rename replaces a link there. But when the
    source sits on another filesystem, ``shutil.move`` copies it instead, and the copy
    writes through the link, to the file the link names, which neither the path policy nor
    the other move checks saw: inside a protected directory (a planted bootstrap code), at
    a secret file, or outside the work dir. A symbolic link, dangling or not, names that
    file by its path; a hard link is that file's inode under a second name, which
    ``copy2`` truncates and rewrites. So a landing that is a symbolic link, or a file that
    is not a directory and has another hard link, is refused.
    """
    try:
        status = os.lstat(landing)
    except OSError:
        return None
    name = os.path.basename(landing)
    if stat.S_ISLNK(status.st_mode):
        return f"'{name}' in the destination is a symbolic link, and the move could write through it"
    if not stat.S_ISDIR(status.st_mode) and status.st_nlink > 1:
        return f"'{name}' in the destination is a hard link to another file, and the move could write through it"
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
    - it must not be inside a sensitive system directory or a directory that holds Koda's
      or a provider CLI's credentials (``path_sensitive_dir``, see
      :func:`koda.utils.workdir.sensitive_dir_for` and
      :func:`koda.utils.workdir.protected_dirs`: the control-plane state directory, the
      browser's saved sessions, ``CLAUDE_CONFIG_DIR`` and ``CODEX_HOME`` where the
      environment sets them, the Claude Code config dir the compose files configure,
      ``/var/lib/koda/runtime/claude-config``, in every process whatever its environment
      sets, and the Anthropic profile credential dirs the environment names, all
      compared ignoring case), except the sensitive directories one of Koda's runtime roots
      is configured under, when ``work_dir`` is that runtime root or below it: the Docker
      default ``HOME`` under ``/var/lib`` and the paths inside it stay usable;
    - neither the requested path nor the path it resolves to may be a secret file
      (``path_blocked_file``, see :func:`secret_file_refusal`): a blocked extension, a
      ``.env`` dotfile, or a CLI credential store such as ``.ssh/`` or ``.netrc``.

    ``work_dir`` is the work dir the runtime chose for the caller: every entry point
    validates it (:func:`koda.utils.workdir.validate_work_dir`), or it is the operator's
    ``DEFAULT_WORK_DIR``.

    ``deny_sensitive_dirs=False`` skips only the ``SENSITIVE_DIRS`` check, never the
    protected directories, which are refused for every caller
    (:func:`koda.utils.workdir.protected_dir_for`). The file commands and
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
        # The protected directories are never waived, whatever the caller skips.
        sensitive = protected_dir_for(resolved)
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
