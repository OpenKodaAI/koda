"""Shared shell command guardrails for foreground and background execution."""

from __future__ import annotations

import shlex

from koda.config import BLOCKED_COMMAND_TOKENS
from koda.services.blocked_patterns import is_blocked_shell

_ENV_EXFIL_SUBSTRINGS = (
    "os.environ",
    "os.getenv",
    "process.env",
    "/proc/self/environ",
    "/proc/1/environ",
)


def enforce_shell_guardrails(command: str) -> str:
    """Raise ValueError when a shell command is not safe to execute."""
    normalized = str(command or "").strip()
    if not normalized:
        raise ValueError("command cannot be empty")
    if is_blocked_shell(normalized):
        raise ValueError("command matches a blocked shell pattern")
    lowered = normalized.lower()
    if any(marker in lowered for marker in _ENV_EXFIL_SUBSTRINGS):
        raise ValueError("command attempts to read process environment")
    try:
        tokens = shlex.split(normalized)
    except ValueError as exc:
        raise ValueError(f"command could not be parsed safely: {exc}") from exc
    for token in tokens:
        base = token.rsplit("/", 1)[-1].lower()
        if base in BLOCKED_COMMAND_TOKENS:
            raise ValueError(f"command token {base!r} is blocked")
    return normalized
