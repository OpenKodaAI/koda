"""Centralized block-pattern guards (Phase A.6 of the consolidation plan).

The runtime has multiple sites that historically called
``BLOCKED_*_PATTERN.search(...)`` directly against the raw Python regex
exposed by ``koda/config.py``. Two problems with that:

1. Python ``re.search`` carries catastrophic-backtracking risk on
   user-controlled inputs. The Phase 1A ``koda-command-guard`` PyO3
   crate compiles each pattern to a linear-time DFA via the Rust
   ``regex`` crate; we want every block-pattern site to go through
   that DFA so a malicious or malformed shell argument cannot blow up
   matching.
2. Repeated ``re.compile`` lookups are paid per call. Compiling each
   pattern *once* at module load and reusing the resulting guard is
   the right shape — but doing so inline at every call site (as
   ``tool_dispatcher.py`` did) leads to drift, with handlers / cli
   runners reaching back to the raw pattern.

This module is the single source of truth: every block-pattern
matcher used anywhere in the runtime lives here, built once via
:func:`koda.services.command_guard.build_guard` (native DFA when
``koda_command_guard`` wheel is installed; Python fallback otherwise).
Call sites import the helper functions (``is_blocked_shell`` etc.) and
never touch the raw patterns. ``tests/test_open_source_hygiene.py``
enforces this with a grep gate.
"""

from __future__ import annotations

from typing import Protocol

from koda.config import (
    BLOCKED_CONFLUENCE_PATTERN,
    BLOCKED_DOCKER_PATTERN,
    BLOCKED_GH_PATTERN,
    BLOCKED_GLAB_PATTERN,
    BLOCKED_GWS_PATTERN,
    BLOCKED_JIRA_PATTERN,
    BLOCKED_NPM_PATTERN,
    BLOCKED_PIP_PATTERN,
    BLOCKED_SHELL_PATTERN,
)
from koda.services.command_guard import build_guard


class _GuardProto(Protocol):
    def is_blocked(self, text: str) -> bool: ...

    def first_match_span(self, text: str) -> tuple[int, int] | None: ...


# Module-level guards. ``None`` when the source pattern was env-
# disabled (e.g. ``BLOCKED_GH_PATTERN`` defaults to ``None``).
SHELL_GUARD: _GuardProto | None = build_guard(BLOCKED_SHELL_PATTERN)
GWS_GUARD: _GuardProto | None = build_guard(BLOCKED_GWS_PATTERN)
JIRA_GUARD: _GuardProto | None = build_guard(BLOCKED_JIRA_PATTERN)
CONFLUENCE_GUARD: _GuardProto | None = build_guard(BLOCKED_CONFLUENCE_PATTERN)
GH_GUARD: _GuardProto | None = build_guard(BLOCKED_GH_PATTERN)
GLAB_GUARD: _GuardProto | None = build_guard(BLOCKED_GLAB_PATTERN)
DOCKER_GUARD: _GuardProto | None = build_guard(BLOCKED_DOCKER_PATTERN)
PIP_GUARD: _GuardProto | None = build_guard(BLOCKED_PIP_PATTERN)
NPM_GUARD: _GuardProto | None = build_guard(BLOCKED_NPM_PATTERN)


def is_blocked_shell(text: str) -> bool:
    return SHELL_GUARD is not None and SHELL_GUARD.is_blocked(text)


def is_blocked_gws(text: str) -> bool:
    return GWS_GUARD is not None and GWS_GUARD.is_blocked(text)


def is_blocked_jira(text: str) -> bool:
    return JIRA_GUARD is not None and JIRA_GUARD.is_blocked(text)


def is_blocked_confluence(text: str) -> bool:
    return CONFLUENCE_GUARD is not None and CONFLUENCE_GUARD.is_blocked(text)


def is_blocked_gh(text: str) -> bool:
    return GH_GUARD is not None and GH_GUARD.is_blocked(text)


def is_blocked_glab(text: str) -> bool:
    return GLAB_GUARD is not None and GLAB_GUARD.is_blocked(text)


def is_blocked_docker(text: str) -> bool:
    return DOCKER_GUARD is not None and DOCKER_GUARD.is_blocked(text)


def is_blocked_pip(text: str) -> bool:
    return PIP_GUARD is not None and PIP_GUARD.is_blocked(text)


def is_blocked_npm(text: str) -> bool:
    return NPM_GUARD is not None and NPM_GUARD.is_blocked(text)


def is_blocked_against(guard: _GuardProto | None, text: str) -> bool:
    """Generic helper for callers that hold a guard reference (e.g.
    ``cli_runner`` accepting an injected guard from a handler)."""
    return guard is not None and guard.is_blocked(text)
