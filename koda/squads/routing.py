"""Routing decisions for inbound squad-thread messages.

Pure functions that decide *which* squad agents should be notified about a
message, given the thread's participants and elected coordinator. The actual
delivery mechanism (``AgentMessageBus.send`` to each target) lives in the
inbound handler — this module only ranks the candidates.

Priority (highest first):
  1. Explicit ``@mention`` of a participant agent.
  2. The squad's elected coordinator (if any participant in the thread).
  3. (None — capability-based fallback is the next slice's work.)
"""

from __future__ import annotations

import re
from collections.abc import Iterable

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
) -> list[str]:
    """Decide which squad members should be notified about ``text``.

    Returns an ordered, deduplicated list of agent IDs. An empty list means
    no participant qualifies (the message stays in the thread audit log but
    no agent is woken up).
    """
    participants = [p for p in participant_agent_ids if isinstance(p, str) and p]
    if not participants:
        return []
    mentioned = extract_mentions(text, participants)
    if mentioned:
        return mentioned
    if coordinator_agent_id and coordinator_agent_id in participants:
        return [coordinator_agent_id]
    return []
