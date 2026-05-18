"""Structural routing helpers for inbound squad-thread messages.

Semantic ranking lives in :mod:`koda.squads.semantic_router`. This module keeps
only language-independent control flow: explicit mentions, reply continuation,
semantic results supplied by the caller, coordinator fallback, and a stable
tie-breaker.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from koda.squads.semantic_router import SemanticRoutingResult

_MENTION_RE = re.compile(r"(?<![A-Za-z0-9_])@([A-Za-z][A-Za-z0-9_-]*)")


def extract_mentions(text: str, candidates: Iterable[str]) -> list[str]:
    """Return participants from ``candidates`` that appear as ``@<name>`` in
    ``text``. Matching is case-insensitive; original casing of the candidate
    is preserved in the output. Order follows first appearance in ``text``;
    duplicates are dropped.
    """
    if not text:
        return []
    found_raw = [m.group(1) for m in _MENTION_RE.finditer(text)]
    if not found_raw:
        return []
    upper_lookup = {c.upper(): c for c in candidates if isinstance(c, str) and c}
    out: list[str] = []
    seen: set[str] = set()
    for raw in found_raw:
        match = upper_lookup.get(raw.upper())
        if match is None or match in seen:
            continue
        out.append(match)
        seen.add(match)
    return out


def select_targets(
    text: str,
    *,
    participant_agent_ids: Iterable[str],
    coordinator_agent_id: str | None = None,
    reply_to_agent_id: str | None = None,
    capability_hints: dict[str, str] | None = None,
    semantic_result: SemanticRoutingResult | None = None,
    explicit_mention_agent_ids: Iterable[str] | None = None,
) -> list[str]:
    """Decide which squad members should be notified about ``text``.

    Returns an ordered, deduplicated list of agent IDs. An empty list means
    no participant qualifies (the message stays in the thread audit log but
    no agent is woken up).
    """
    participants = [p for p in participant_agent_ids if isinstance(p, str) and p]
    if not participants:
        return []
    explicit_mentions = _dedupe([agent_id for agent_id in explicit_mention_agent_ids or [] if agent_id in participants])
    if explicit_mentions:
        return explicit_mentions
    mentioned = extract_mentions(text, participants)
    if mentioned:
        return mentioned
    if reply_to_agent_id and reply_to_agent_id in participants:
        return [reply_to_agent_id]
    if semantic_result is not None and semantic_result.available:
        semantic_targets = [
            agent_id for agent_id in semantic_result.top_agents(include_coordinator=False) if agent_id in participants
        ]
        if semantic_targets:
            return semantic_targets
    _ = capability_hints
    if coordinator_agent_id and coordinator_agent_id in participants:
        return [coordinator_agent_id]
    if participants:
        return [participants[0]]
    return []


def _dedupe(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        out.append(value)
        seen.add(value)
    return out
