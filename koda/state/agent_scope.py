"""Shared helpers for canonical agent scoping and agent-local collection names."""

from __future__ import annotations

import re

from koda.config import AGENT_ID

_COLLECTION_SCOPE_RE = re.compile(r"[^a-z0-9_]+")


def normalize_agent_scope(agent_id: str | None = None, *, fallback: str | None = None) -> str:
    """Return the canonical lowercase agent scope."""
    normalized = str(agent_id or fallback or AGENT_ID or "default").strip().lower()
    return normalized or "default"


def collection_agent_scope(agent_id: str | None = None, *, fallback: str | None = None) -> str:
    """Return a collection-safe scope token derived from the canonical agent scope."""
    normalized = _COLLECTION_SCOPE_RE.sub("_", normalize_agent_scope(agent_id, fallback=fallback)).strip("_")
    return normalized or "default"
