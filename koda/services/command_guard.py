"""Native-fast block-pattern matcher with a Python fallback.

The tool dispatcher (``koda/services/tool_dispatcher.py``) checks every
``<agent_cmd>`` invocation against ``BLOCKED_*_PATTERN`` regexes from
``koda/config.py``. Those patterns are user-input-adjacent, security-
critical, and run on the asyncio main thread. We compile them once via
the Rust ``koda_command_guard`` PyO3 module (RE2-style DFA, linear
time, no GIL contention) and fall back to the original Python regex if
the native wheel is not installed in this environment.

A regex DFA is required on the security-critical hot path. The fallback
keeps dev environments without the native wheel working unchanged; the
production deploy installs the wheel via maturin and gets the speedup
plus a guarantee against catastrophic backtracking automatically.
"""

from __future__ import annotations

import re
from typing import Protocol

from koda.logging_config import get_logger

log = get_logger(__name__)


class _MatcherProto(Protocol):
    def is_blocked(self, text: str) -> bool: ...

    def first_match_span(self, text: str) -> tuple[int, int] | None: ...


try:  # pragma: no cover - import-time branch
    import koda_command_guard as _native  # type: ignore[import-not-found]

    _NATIVE_AVAILABLE = True
    _NATIVE_VERSION = getattr(_native, "__version__", "unknown")
except Exception:  # pragma: no cover - fallback path
    _native = None
    _NATIVE_AVAILABLE = False
    _NATIVE_VERSION = ""


class _PythonGuard:
    """Pure-Python fallback that mirrors the Rust ``Guard`` API."""

    __slots__ = ("_pattern",)

    def __init__(self, pattern: re.Pattern[str]) -> None:
        self._pattern = pattern

    def is_blocked(self, text: str) -> bool:
        return self._pattern.search(text) is not None

    def first_match_span(self, text: str) -> tuple[int, int] | None:
        match = self._pattern.search(text)
        return match.span() if match is not None else None


def build_guard(pattern: re.Pattern[str] | str | None) -> _MatcherProto | None:
    """Wrap a compiled or string pattern in the fastest available matcher.

    ``None`` patterns short-circuit to ``None`` so callers can use the
    helper for optional (env-disabled) blocked-pattern slots without
    branching on availability themselves.
    """
    if pattern is None:
        return None
    if isinstance(pattern, re.Pattern):
        source = pattern.pattern
    else:
        source = pattern
    if _NATIVE_AVAILABLE:
        try:
            return _native.Guard(source)  # type: ignore[no-any-return]
        except Exception:
            log.exception(
                "command_guard_native_compile_failed_using_python_fallback",
                pattern_prefix=source[:80],
            )
    if isinstance(pattern, re.Pattern):
        return _PythonGuard(pattern)
    return _PythonGuard(re.compile(source, re.IGNORECASE))


def native_available() -> bool:
    """Tests/diagnostics use this to assert the fast path is wired in."""
    return _NATIVE_AVAILABLE


def native_version() -> str:
    return _NATIVE_VERSION
