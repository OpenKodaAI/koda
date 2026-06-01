"""Password strength policy for operator accounts.

Goal: reject weak or guessable passwords without adding a heavy dependency.
Checks:
1. Minimum length (default 12).
2. At least 3 of 4 character classes (lower, upper, digit, symbol).
3. Reject passwords that contain (case-insensitive) the username or email local-part.
4. Reject passwords on a small embedded list of most-common leaked passwords.
5. Reject passwords with Shannon entropy below a low threshold (catches repeats).

Errors are raised as `PasswordPolicyError` with a stable `code` attribute so the
web layer can map them to i18n keys.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

_DATA_PATH = Path(__file__).resolve().parent / "data" / "common_passwords.txt"

_MIN_ENTROPY_BITS_PER_CHAR = 2.0


class PasswordPolicyError(ValueError):
    """Raised when a password fails the policy."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


@lru_cache(maxsize=1)
def _common_passwords() -> frozenset[str]:
    if not _DATA_PATH.exists():
        return frozenset()
    lines = _DATA_PATH.read_text(encoding="utf-8", errors="ignore").splitlines()
    return frozenset(line.strip().lower() for line in lines if line.strip() and not line.startswith("#"))


def _shannon_bits_per_char(password: str) -> float:
    if not password:
        return 0.0
    total = len(password)
    counts: dict[str, int] = {}
    for ch in password:
        counts[ch] = counts.get(ch, 0) + 1
    entropy = 0.0
    for freq in counts.values():
        p = freq / total
        entropy -= p * math.log2(p)
    return entropy


def _identifier_fragments(values: Iterable[str | None]) -> list[str]:
    fragments: list[str] = []
    for value in values:
        if not value:
            continue
        normalized = str(value).strip().lower()
        if not normalized:
            continue
        if "@" in normalized:
            local_part = normalized.split("@", 1)[0]
            if len(local_part) >= 3:
                fragments.append(local_part)
        else:
            if len(normalized) >= 3:
                fragments.append(normalized)
    return fragments


def validate_password(
    password: str,
    *,
    min_length: int,
    username: str | None = None,
    email: str | None = None,
) -> None:
    """Raise PasswordPolicyError when password fails policy.

    Keep order stable — tests and i18n rely on the specific error code returned
    for each failure mode.
    """
    if password is None:
        raise PasswordPolicyError("password is required", code="password_required")
    if len(password) < min_length:
        raise PasswordPolicyError(
            f"password must be at least {min_length} characters",
            code="password_too_short",
        )
    if len(password) > 256:
        raise PasswordPolicyError("password is too long", code="password_too_long")

    classes = {
        "lower": any(ch.islower() for ch in password),
        "upper": any(ch.isupper() for ch in password),
        "digit": any(ch.isdigit() for ch in password),
        "symbol": any(not ch.isalnum() for ch in password),
    }
    if sum(1 for active in classes.values() if active) < 3:
        raise PasswordPolicyError(
            "password must contain at least 3 of: lowercase, uppercase, digit, symbol",
            code="password_weak_composition",
        )

    lowered = password.lower()
    for fragment in _identifier_fragments((username, email)):
        if fragment in lowered:
            raise PasswordPolicyError(
                "password must not contain your username or email",
                code="password_contains_identifier",
            )

    if lowered in _common_passwords():
        raise PasswordPolicyError(
            "password is too common; pick something unique",
            code="password_too_common",
        )

    if _shannon_bits_per_char(password) < _MIN_ENTROPY_BITS_PER_CHAR:
        raise PasswordPolicyError(
            "password is too repetitive; pick something more varied",
            code="password_low_entropy",
        )
