"""Shared work directory validation helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass

from koda.config import DEFAULT_WORK_DIR, SENSITIVE_DIRS


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


def _waived_sensitive_roots(work_dir: str | None) -> frozenset[str]:
    """Return the sensitive roots that do not deny the paths resolved in ``work_dir``.

    Every work dir a user or the agent picks (``/setdir``, its buttons, ``agent_set_workdir``,
    workspace roots, queued and scheduled tasks) goes through :func:`validate_work_dir`,
    which refuses one under a sensitive directory. The one exception is the operator's
    ``DEFAULT_WORK_DIR``, used as configured, such as the Docker default
    ``HOME=/var/lib/koda/runtime/home`` under ``/var/lib``. So only a ``work_dir`` that
    resolves to the resolved ``DEFAULT_WORK_DIR`` gets a waiver, and it covers only the
    sensitive directories ``DEFAULT_WORK_DIR`` is under as configured (as written, before
    symlinks are resolved), in their written and resolved forms. A sensitive directory that
    a work dir reaches only through a symlink is never waived: neither a validated work dir
    that was later replaced with a symlink into ``/etc``, nor a ``DEFAULT_WORK_DIR`` that
    now resolves there.
    """
    if work_dir is None or normalize_work_dir(work_dir) != normalize_work_dir(DEFAULT_WORK_DIR):
        return frozenset()
    configured = os.path.abspath(os.path.expanduser(DEFAULT_WORK_DIR))
    waived: set[str] = set()
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
        """Resolve the sensitive roots now, without the ones waived for ``work_dir``."""
        waived = _waived_sensitive_roots(work_dir)
        deny = tuple(
            (sensitive, root)
            for sensitive in sorted(SENSITIVE_DIRS)
            for root in _sensitive_roots(sensitive)
            if root not in waived
        )
        return cls(deny)

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

    ``work_dir`` is the work directory that ``path`` was resolved in. When it is the
    operator's ``DEFAULT_WORK_DIR``, the sensitive directories that ``DEFAULT_WORK_DIR`` is
    configured under do not count (see :func:`_waived_sensitive_roots`), so the Docker
    default ``HOME=/var/lib/koda/runtime/home`` and the paths inside it stay usable. Every
    other sensitive directory still matches, including one inside the work dir (a work dir
    of ``/`` contains ``/etc``).
    """
    return SensitiveDirs.for_work_dir(work_dir).containing(path)


def validate_work_dir(
    path: str | None,
    *,
    fallback_to_default: bool = False,
) -> WorkDirValidation:
    """Validate a work directory against existence and sensitive-path rules."""
    candidate = normalize_work_dir(path)
    if sensitive_dir_for(candidate) is not None:
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
