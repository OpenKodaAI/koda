"""Shared helpers for canonical agent scoping and agent-local collection names."""

from __future__ import annotations

import re

from koda.config import AGENT_ID

_COLLECTION_SCOPE_RE = re.compile(r"[^a-z0-9_]+")


def normalize_agent_scope(
    agent_id: str | None = None,
    *,
    fallback: str | None = None,
    user_id: int | str | None = None,
) -> str:
    """Return the canonical lowercase agent scope, optionally scoped to a user."""
    normalized = str(agent_id or fallback or AGENT_ID or "default").strip().lower()
    scope = normalized or "default"
    if user_id is not None:
        scope = f"{scope}:{user_id}"
    return scope


def task_agent_scope(agent_id: str | None = None) -> str:
    """Return the ``agent_id`` value of this agent's ``tasks`` and ``sessions`` rows.

    These rows carry the upper-case id, as ``cp_agent_definitions.id`` and
    ``audit_events`` do. ``koda.state.history_store`` writes them with this
    value and the runtime store reads and updates ``tasks`` with it, so both
    sides match (D-293). The runtime-owned ``runtime_*`` tables keep the
    lower-case :func:`normalize_agent_scope`.
    """
    normalized = str(agent_id or AGENT_ID or "default").strip().upper()
    return normalized or "DEFAULT"


def collection_agent_scope(
    agent_id: str | None = None,
    *,
    fallback: str | None = None,
    user_id: int | str | None = None,
) -> str:
    """Return a collection-safe scope token derived from the canonical agent scope."""
    normalized = _COLLECTION_SCOPE_RE.sub(
        "_", normalize_agent_scope(agent_id, fallback=fallback, user_id=user_id)
    ).strip("_")
    return normalized or "default"
