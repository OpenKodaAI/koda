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


def validate_work_dir(
    path: str | None,
    *,
    fallback_to_default: bool = False,
) -> WorkDirValidation:
    """Validate a work directory against existence and sensitive-path rules."""
    candidate = normalize_work_dir(path)
    for sensitive in SENSITIVE_DIRS:
        sensitive_path = normalize_work_dir(sensitive)
        if candidate == sensitive_path or candidate.startswith(sensitive_path + os.sep):
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
