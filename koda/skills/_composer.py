"""Skill graph resolution and prompt composition."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from koda.skills._registry import SkillRegistry
    from koda.skills._selector import SkillMatch

# ---------------------------------------------------------------------------
# Approach section extraction
# ---------------------------------------------------------------------------

_APPROACH_RE = re.compile(
    r"^##\s+(?:Approach|Abordagem)\s*\n(.*?)(?=^##\s|\Z)",
    re.MULTILINE | re.DOTALL,
)


def _extract_approach(full_content: str) -> str:
    """Extract the ## Approach / ## Abordagem section from skill content."""
    m = _APPROACH_RE.search(full_content)
    if m:
        return m.group(1).strip()
    return ""


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------


def _estimate_tokens(text: str) -> int:
    return len(text) // 4


# ---------------------------------------------------------------------------
# Graph resolution
# ---------------------------------------------------------------------------


def resolve_skill_graph(
    selected: list[SkillMatch],
    registry: SkillRegistry,
) -> list[SkillMatch]:
    """Expand dependencies, detect conflicts, topological-sort for prompt ordering.

    1. For each selected skill, if it has ``requires``, pull in required skills.
    2. If conflicts detected between selected skills, keep higher score.
    3. Topological sort: dependencies before dependents.
    4. Return the resolved ordered list.
    """
    from koda.skills._selector import SkillMatch as _SM

    if not selected:
        return []

    # Build a lookup by skill id.
    match_by_id: dict[str, SkillMatch] = {m.skill.id: m for m in selected}

    # 1. Expand dependencies --------------------------------------------------
    visited: set[str] = set()
    queue = list(match_by_id.keys())

    while queue:
        sid = queue.pop(0)
        if sid in visited:
            continue
        visited.add(sid)
        match = match_by_id.get(sid)
        skill = match.skill if match else registry.get(sid)
        if skill is None:
            continue
        for req in skill.requires:
            if req not in match_by_id:
                req_skill = registry.get(req)
                if req_skill is not None:
                    # Synthesise a match for the dependency with a baseline score.
                    match_by_id[req] = _SM(
                        skill=req_skill,
                        semantic_score=0.0,
                        trigger_matched=False,
                        alias_matched=False,
                        composite_score=0.0,
                        selection_reason="dependency",
                    )
            if req not in visited:
                queue.append(req)

    # 2. Remove conflicts (keep higher composite_score) -----------------------
    to_remove: set[str] = set()
    ids = list(match_by_id.keys())
    for i, sid_a in enumerate(ids):
        if sid_a in to_remove:
            continue
        skill_a = match_by_id[sid_a].skill
        for sid_b in ids[i + 1 :]:
            if sid_b in to_remove:
                continue
            skill_b = match_by_id[sid_b].skill
            a_conflicts_b = sid_b in skill_a.conflicts
            b_conflicts_a = sid_a in skill_b.conflicts
            if a_conflicts_b or b_conflicts_a:
                # Keep the one with higher composite_score.
                if match_by_id[sid_a].composite_score >= match_by_id[sid_b].composite_score:
                    to_remove.add(sid_b)
                else:
                    to_remove.add(sid_a)

    for sid in to_remove:
        del match_by_id[sid]

    # 3. Topological sort (Kahn's algorithm) ----------------------------------
    in_degree: dict[str, int] = {sid: 0 for sid in match_by_id}
    adj: dict[str, list[str]] = {sid: [] for sid in match_by_id}

    for sid, m in match_by_id.items():
        for req in m.skill.requires:
            if req in match_by_id:
                adj[req].append(sid)
                in_degree[sid] = in_degree.get(sid, 0) + 1

    queue_sorted: list[str] = sorted(
        [sid for sid, deg in in_degree.items() if deg == 0],
        key=lambda s: -match_by_id[s].composite_score,
    )
    ordered: list[str] = []

    while queue_sorted:
        sid = queue_sorted.pop(0)
        ordered.append(sid)
        for dependent in adj.get(sid, []):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue_sorted.append(dependent)
        # Keep stable ordering among same-level nodes.
        queue_sorted.sort(key=lambda s: -match_by_id[s].composite_score)

    return [match_by_id[sid] for sid in ordered if sid in match_by_id]


# ---------------------------------------------------------------------------
# Directive block
# ---------------------------------------------------------------------------

_DIRECTIVE = (
    "<directive>\n"
    "The following expert skills were selected as highly relevant to this query.\n"
    "You MUST follow the methodology described in each skill when formulating your response.\n"
    "Structure your response according to the skill's Output Format section.\n"
    "If multiple skills apply, integrate their approaches coherently.\n"
    "</directive>"
)


# ---------------------------------------------------------------------------
# Prompt composition
# ---------------------------------------------------------------------------


def compose_skill_prompt(
    resolved: list[SkillMatch],
    *,
    token_budget: int = 1600,
    progressive: bool = True,
) -> str:
    """Build the final skill prompt text with 2-tier disclosure.

    If *progressive* is ``True``:
      - ``composite_score >= 0.45``: include ``full_content`` with instruction tag
      - ``composite_score < 0.45``: excluded entirely

    If *progressive* is ``False``, include ``full_content`` for all skills.

    Output is wrapped in ``<expert_skills>`` XML tags with a leading directive.
    Respects *token_budget* by estimating tokens (``len / 4``) and dropping
    lower-scored skills first when the budget is exceeded.
    """
    if not resolved:
        return ""

    # Build per-skill content blocks.
    blocks: list[tuple[SkillMatch, str]] = []
    for m in resolved:
        content = _skill_content(m, progressive=progressive)
        if content is None:
            # Excluded by the 2-tier threshold.
            continue
        blocks.append((m, content))

    if not blocks:
        return ""

    # Enforce token budget: drop lowest-scored skills first.
    # Sort by composite_score ascending so we can pop from the front.
    budget_order = sorted(
        range(len(blocks)),
        key=lambda i: blocks[i][0].composite_score,
    )

    total_tokens = sum(_estimate_tokens(b[1]) for b in blocks)
    removed: set[int] = set()
    while total_tokens > token_budget and budget_order:
        idx = budget_order.pop(0)
        total_tokens -= _estimate_tokens(blocks[idx][1])
        removed.add(idx)

    parts: list[str] = []
    for i, (m, content) in enumerate(blocks):
        if i in removed:
            continue
        score_pct = f"{m.composite_score:.0%}"
        instruction_tag = ""
        if m.skill.instruction:
            instruction_tag = f"\n  <instruction>{m.skill.instruction}</instruction>"
        mode = "active"
        parts.append(
            f'<skill name="{m.skill.name}" category="{m.skill.category}"'
            f' confidence="{score_pct}" mode="{mode}">'
            f"{instruction_tag}\n{content}\n</skill>"
        )

    if not parts:
        return ""

    inner = "\n".join(parts)
    return f"<expert_skills>\n{_DIRECTIVE}\n{inner}\n</expert_skills>"


def _skill_content(m: SkillMatch, *, progressive: bool) -> str | None:
    """Return the content string for a single skill, or ``None`` if excluded."""
    if not progressive:
        return m.skill.full_content

    if m.composite_score >= 0.45:
        return m.skill.full_content

    # Below threshold — exclude entirely.
    return None


# ---------------------------------------------------------------------------
# Output requirements composition
# ---------------------------------------------------------------------------


def compose_output_requirements(resolved: list[SkillMatch]) -> str:
    """Build ``<output_requirements>`` block for high-confidence skills.

    Only skills with ``composite_score >= 0.7`` AND a non-empty
    ``output_format_enforcement`` contribute a requirement entry.
    Returns an empty string when no skills qualify.
    """
    entries: list[str] = []
    for m in resolved:
        if m.composite_score >= 0.7 and m.skill.output_format_enforcement:
            entries.append(
                f'  <requirement source="skill:{m.skill.id}">\n  {m.skill.output_format_enforcement}\n  </requirement>'
            )

    if not entries:
        return ""

    inner = "\n".join(entries)
    return f"<output_requirements>\n{inner}\n</output_requirements>"
