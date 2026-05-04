"""``koda.services.command_guard`` is the native-fast block-pattern shim.

The
the per-tool ``BLOCKED_*_PATTERN.search(args)`` calls in
``koda/services/tool_dispatcher.py`` for a Rust DFA via PyO3. The shim
keeps the Python regex as a transparent fallback so dev environments
without the wheel still work — these tests pin both behaviors.
"""

from __future__ import annotations

import re

from koda.services import command_guard


def test_build_guard_returns_none_for_none_pattern() -> None:
    """Optional (env-disabled) BLOCKED_* slots must short-circuit."""
    assert command_guard.build_guard(None) is None


def test_build_guard_matches_compiled_pattern_semantics() -> None:
    pattern = re.compile(r"rm\s+-rf|sudo\b", re.IGNORECASE)
    guard = command_guard.build_guard(pattern)
    assert guard is not None
    assert guard.is_blocked("rm -rf /")
    assert guard.is_blocked("RM -RF /")
    assert guard.is_blocked("please sudo apt") is True
    assert guard.is_blocked("git status") is False


def test_build_guard_accepts_string_pattern() -> None:
    guard = command_guard.build_guard(r"mkfs\b")
    assert guard is not None
    assert guard.is_blocked("mkfs.ext4 /dev/sda")
    assert not guard.is_blocked("ls -la")


def test_first_match_span_returns_byte_offsets() -> None:
    pattern = re.compile(r"sudo\b", re.IGNORECASE)
    guard = command_guard.build_guard(pattern)
    assert guard is not None
    span = guard.first_match_span("please sudo apt-get install")
    assert span is not None
    start, end = span
    text = "please sudo apt-get install"
    assert text[start:end].lower() == "sudo"
    assert guard.first_match_span("git status") is None


def test_python_fallback_matches_native_semantics() -> None:
    """Force the Python fallback path and confirm equivalent behavior so
    a dev environment without the wheel doesn't drift from prod."""
    pattern = re.compile(r"rm\s+-rf|sudo\b", re.IGNORECASE)
    fallback = command_guard._PythonGuard(pattern)
    assert fallback.is_blocked("rm -rf /")
    assert fallback.is_blocked("RM -RF /")
    assert fallback.is_blocked("git status") is False
    span = fallback.first_match_span("please sudo apt-get install")
    assert span is not None and span[0] == 7


def test_dispatcher_module_uses_guard_constants() -> None:
    """The dispatcher must hold the matchers as module-level constants
    so they're compiled once, not on every tool invocation."""
    from koda.services import tool_dispatcher

    assert tool_dispatcher._BLOCKED_SHELL is not None
    assert tool_dispatcher._BLOCKED_SHELL.is_blocked("rm -rf /")
    assert not tool_dispatcher._BLOCKED_SHELL.is_blocked("git status")
