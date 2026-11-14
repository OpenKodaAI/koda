"""Shared work directory validation helpers."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from koda.config import (
    BROWSER_SESSION_DIR,
    DEFAULT_WORK_DIR,
    IMAGE_TEMP_DIR,
    PROVIDER_CLI_CONFIG_DIR_ENV_KEYS,
    RUNTIME_EPHEMERAL_ROOT,
    RUNTIME_ROOT_DIR,
    SENSITIVE_DIRS,
    STATE_ROOT_DIR,
)


@dataclass(slots=True)
class WorkDirValidation:
    """Normalized validation result for a work directory candidate."""

    ok: bool
    path: str
    reason: str | None = None
    blocked: bool = False


def normalize_work_dir(path: str | None) -> str:
    """Resolve a work directory to an absolute real path."""
    raw_path = path or DEFAULT_WORK_DIR
    return os.path.realpath(os.path.expanduser(raw_path))


def _is_within(path: str, root: str) -> bool:
    """Return whether ``path`` is ``root`` or below it, by whole path component."""
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _sensitive_roots(sensitive: str) -> tuple[str, ...]:
    """Return a ``SENSITIVE_DIRS`` entry as written and resolved (``/var/run`` and ``/run``)."""
    return tuple(dict.fromkeys((sensitive, normalize_work_dir(sensitive))))


def _configured_path(path: str | os.PathLike[str]) -> str:
    """Return a configured path absolute, with ``~`` expanded and symlinks left as they are."""
    return os.path.abspath(os.path.expanduser(os.fspath(path)))


def runtime_roots() -> tuple[str, ...]:
    """Return Koda's own runtime roots, as configured: where Koda itself runs agent work.

    They are ``RUNTIME_ROOT_DIR``, ``RUNTIME_EPHEMERAL_ROOT`` and the operator's
    ``DEFAULT_WORK_DIR``, absolute and ``~``-expanded but not symlink-resolved. The Docker
    layout puts all three under the sensitive ``/var/lib``: ``/var/lib/koda/runtime`` and
    its ``home`` (``HOME``, the default ``DEFAULT_WORK_DIR``).
    """
    configured = (RUNTIME_ROOT_DIR, RUNTIME_EPHEMERAL_ROOT, DEFAULT_WORK_DIR)
    return tuple(dict.fromkeys(_configured_path(root) for root in configured if str(root).strip()))


def control_plane_state_dir() -> str:
    """Return the control-plane state directory as configured (``STATE_ROOT_DIR/control_plane``).

    It holds the master key and the bootstrap code, so it is one of the
    :func:`protected_dirs`.
    """
    return _configured_path(os.path.join(os.fspath(STATE_ROOT_DIR), "control_plane"))


def browser_sessions_dir() -> str:
    """Return the directory where the browser saves each chat scope's sessions, as configured.

    It is ``browser_sessions`` in ``BROWSER_SESSION_DIR`` or, when that is unset, in
    ``IMAGE_TEMP_DIR`` (``RUNTIME_EPHEMERAL_ROOT/image-scratch`` by default), and holds one
    directory per chat scope with the cookies and localStorage of each saved session
    (:meth:`koda.services.browser_manager.BrowserManager.save_session`). So it is one of the
    :func:`protected_dirs`.
    """
    return _configured_path(os.path.join(BROWSER_SESSION_DIR or os.fspath(IMAGE_TEMP_DIR), "browser_sessions"))


def provider_cli_config_dirs(environ: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Return the provider CLI config dirs that the environment moves out of HOME, as configured.

    They are the directories named by ``CLAUDE_CONFIG_DIR`` and ``CODEX_HOME``
    (``koda.config.PROVIDER_CLI_CONFIG_DIR_ENV_KEYS``) in ``environ``, by default this
    process's environment, which is the one the CLIs it starts inherit
    (:func:`koda.services.provider_env.build_llm_subprocess_env`). Each holds that CLI's
    login, settings and session transcripts, under any name, so they are among the
    :func:`protected_dirs`. A variable that is unset or blank names none.
    """
    env = os.environ if environ is None else environ
    configured = (env.get(key, "") for key in PROVIDER_CLI_CONFIG_DIR_ENV_KEYS.values())
    return tuple(dict.fromkeys(_configured_path(value) for value in configured if value.strip()))


def protected_dirs() -> tuple[str, ...]:
    """Return the directories that hold Koda's or a provider CLI's credentials, as configured now.

    They are the control-plane state directory (:func:`control_plane_state_dir`: the master
    key and the bootstrap code), the browser's saved sessions of every chat scope
    (:func:`browser_sessions_dir`), and the provider CLI config dirs the environment moves
    out of HOME (:func:`provider_cli_config_dirs`). In the Docker layout the last two sit
    below ``RUNTIME_EPHEMERAL_ROOT`` (``image-scratch/browser_sessions``, and
    ``claude-config`` where ``CLAUDE_CONFIG_DIR`` is set as the app container sets it),
    which is a valid work dir, and outside Docker the state directory sits in the default
    work dir ``~``. None of them is Koda's work area: none is ever a work dir, and the file
    tools, the file commands and ``browser_upload`` refuse every path inside them, whatever
    the work dir and its waiver (:class:`SensitiveDirs`, :func:`protected_dir_for`).
    """
    return tuple(dict.fromkeys((control_plane_state_dir(), browser_sessions_dir(), *provider_cli_config_dirs())))


def protected_dir_for(path: str) -> str | None:
    """Return the one of :func:`protected_dirs` that contains ``path``, or None.

    ``path`` is absolute and resolved; each directory is compared as configured and
    resolved, by whole path component. They are never waived, so every caller of the shared
    path policy applies this check, also those that skip ``SENSITIVE_DIRS``
    (:func:`koda.utils.files.resolve_work_path` with ``deny_sensitive_dirs=False``).
    """
    for protected in protected_dirs():
        if any(_is_within(path, root) for root in _sensitive_roots(protected)):
            return protected
    return None


def protected_dir_within(path: str) -> str | None:
    """Return the one of :func:`protected_dirs` that is ``path`` or lies below it, or None.

    ``path`` is absolute and resolved; each directory is compared as configured and
    resolved, by whole path component, as :func:`protected_dir_for` compares them. A
    protected directory is recognised by its location alone, so moving ``path`` would take
    that directory to a path no check recognises, and putting something at ``path`` would
    put it where Koda or a CLI reads that directory from
    (:func:`koda.utils.files.protected_move_refusal`).
    """
    for protected in protected_dirs():
        if any(_is_within(root, path) for root in _sensitive_roots(protected)):
            return protected
    return None


def _waived_sensitive_roots(work_dir: str | None) -> frozenset[str]:
    """Return the sensitive roots that do not deny the paths resolved in ``work_dir``.

    Every work dir a user or the agent picks (``/setdir``, its buttons, ``agent_set_workdir``,
    workspace roots, queued and scheduled tasks) goes through :func:`validate_work_dir`.
    Koda's own runtime roots (:func:`runtime_roots`) may sit under a sensitive directory,
    such as the Docker ``/var/lib/koda/runtime`` and ``HOME=/var/lib/koda/runtime/home``
    under ``/var/lib``. So a ``work_dir`` that resolves to a runtime root, or below one,
    gets a waiver, and it covers only the sensitive directories that runtime root is under
    as configured (as written, before symlinks are resolved), in their written and resolved
    forms. A sensitive directory that a work dir reaches only through a symlink is never
    waived: neither a validated work dir that was later replaced with a symlink into
    ``/etc``, nor a runtime root that now resolves there, nor a link inside a runtime root
    that points to another directory under ``/var/lib``.
    """
    if work_dir is None:
        return frozenset()
    resolved = normalize_work_dir(work_dir)
    waived: set[str] = set()
    for configured in runtime_roots():
        if not _is_within(resolved, os.path.realpath(configured)):
            continue
        for sensitive in SENSITIVE_DIRS:
            roots = _sensitive_roots(sensitive)
            if any(_is_within(configured, root) for root in roots):
                waived.update(roots)
    return frozenset(waived)


@dataclass(frozen=True, slots=True)
class SensitiveDirs:
    """The ``SENSITIVE_DIRS`` roots that deny access below them, resolved when it is built.

    Build it with :meth:`for_work_dir` for one check (:func:`sensitive_dir_for` does), or
    once for a batch of checks in the same work dir, as ``file_grep`` does for the
    directories it walks.
    """

    deny: tuple[tuple[str, str], ...]
    """``(entry as configured, root)`` pairs, the root being the entry as written or resolved."""

    @classmethod
    def for_work_dir(cls, work_dir: str | None = None) -> SensitiveDirs:
        """Resolve the sensitive roots now, without the ones waived for ``work_dir``.

        The :func:`protected_dirs` (the control-plane state directory, the browser's saved
        sessions and the provider CLI config dirs moved out of HOME) are deny roots too, and
        are never waived.
        """
        waived = _waived_sensitive_roots(work_dir)
        deny = tuple(
            (sensitive, root)
            for sensitive in sorted(SENSITIVE_DIRS)
            for root in _sensitive_roots(sensitive)
            if root not in waived
        )
        protected = tuple((directory, root) for directory in protected_dirs() for root in _sensitive_roots(directory))
        return cls(deny + protected)

    def containing(self, path: str) -> str | None:
        """Return the ``SENSITIVE_DIRS`` entry whose directory contains ``path``, or None."""
        for sensitive, root in self.deny:
            if _is_within(path, root):
                return sensitive
        return None


def sensitive_dir_for(path: str, *, work_dir: str | None = None) -> str | None:
    """Return the sensitive system directory that contains ``path``, or None.

    ``path`` must be absolute and already resolved. Each entry of ``SENSITIVE_DIRS`` is
    compared as written and in its resolved form (``/var/run`` is ``/run`` on most Linux
    hosts, ``/etc`` is ``/private/etc`` on macOS), by whole path component, so ``/etc``
    matches ``/etc/ssh`` but not ``/etcetera``. The entries are resolved on every call, so
    the check follows the filesystem as it is now. Work directories (``/setdir``, the
    setdir buttons, ``agent_set_workdir``, workspace roots), the paths that the file tools
    resolve inside them, and the directories that ``file_grep`` walks share this one
    deny-root check.

    ``work_dir`` is the work directory that ``path`` was resolved in. When it is one of
    Koda's runtime roots (:func:`runtime_roots`) or below one, the sensitive directories
    that runtime root is configured under do not count (see
    :func:`_waived_sensitive_roots`), so the Docker default
    ``HOME=/var/lib/koda/runtime/home`` and the paths inside it stay usable. Every other
    sensitive directory still matches, including one inside the work dir (a work dir of
    ``/`` contains ``/etc``), and so do the :func:`protected_dirs` (the control-plane state
    directory, the browser's saved sessions and the provider CLI config dirs moved out of
    HOME), wherever they are.
    """
    return SensitiveDirs.for_work_dir(work_dir).containing(path)


def validate_work_dir(
    path: str | None,
    *,
    fallback_to_default: bool = False,
) -> WorkDirValidation:
    """Validate a work directory against existence and sensitive-path rules.

    The candidate is resolved (``~`` expanded, symlinks resolved) and refused when it is
    inside a sensitive directory (:func:`sensitive_dir_for`) or one of the
    :func:`protected_dirs`. Koda's own runtime roots (:func:`runtime_roots`) and the
    directories below them are valid work dirs, also when a runtime root is configured
    under a sensitive directory, as the Docker layout puts ``/var/lib/koda/runtime`` under
    ``/var/lib``, except the protected dirs below them.
    """
    candidate = normalize_work_dir(path)
    if sensitive_dir_for(candidate, work_dir=candidate) is not None:
        return WorkDirValidation(
            ok=False,
            path=candidate,
            reason=f"Blocked: '{candidate}' is a sensitive system directory.",
            blocked=True,
        )

    if os.path.isdir(candidate):
        return WorkDirValidation(ok=True, path=candidate)

    if fallback_to_default:
        fallback = normalize_work_dir(DEFAULT_WORK_DIR)
        if os.path.isdir(fallback):
            return WorkDirValidation(
                ok=True,
                path=fallback,
                reason=f"Directory does not exist: {candidate}. Falling back to {fallback}.",
            )

    return WorkDirValidation(
        ok=False,
        path=candidate,
        reason=f"Directory does not exist: {candidate}",
    )
