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


def sensitive_dir_for(path: str) -> str | None:
    """Return the sensitive system directory that contains ``path``, or None.

    ``path`` must be absolute and already resolved. Each entry of ``SENSITIVE_DIRS`` is
    compared as written and in its resolved form (``/var/run`` is ``/run`` on most Linux
    hosts, ``/etc`` is ``/private/etc`` on macOS), by whole path component, so ``/etc``
    matches ``/etc/ssh`` but not ``/etcetera``. Work directories and the paths that the
    file commands and file tools resolve inside them share this one deny-root check.
    """
    for sensitive in sorted(SENSITIVE_DIRS):
        for root in {sensitive, normalize_work_dir(sensitive)}:
            if path == root or path.startswith(root.rstrip(os.sep) + os.sep):
                return sensitive
    return None


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
