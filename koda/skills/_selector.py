"""Multi-signal skill selector for the skills v2 system."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from koda.skills._index import SkillEmbeddingIndex
from koda.skills._registry import SkillDefinition, SkillRegistry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SkillMatch
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SkillMatch:
    """Result of the selection algorithm for a single skill."""

    skill: SkillDefinition
    semantic_score: float  # 0.0-1.0 from embedding similarity
    trigger_matched: bool  # Hard regex match
    alias_matched: bool  # Direct alias resolution
    composite_score: float  # Weighted final score
    selection_reason: str  # Human-readable explanation


# ---------------------------------------------------------------------------
# Word-boundary helper
# ---------------------------------------------------------------------------

_WORD_SPLIT_RE = re.compile(r"[\s,;:.!?/\-]+")


def _normalize_words(text: str) -> set[str]:
    """Return a lowered set of word tokens from *text*."""
    return {w for w in _WORD_SPLIT_RE.split(text.lower()) if w}


# ---------------------------------------------------------------------------
# SkillSelector
# ---------------------------------------------------------------------------


class SkillSelector:
    """Combines alias resolution, trigger regexes, and semantic embeddings."""

    _registry: SkillRegistry
    _index: SkillEmbeddingIndex

    def __init__(self, registry: SkillRegistry, index: SkillEmbeddingIndex) -> None:
        self._registry = registry
        self._index = index

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def select(
        self,
        query: str,
        *,
        max_skills: int = 6,
        agent_skill_policy: dict[str, Any] | None = None,
        complexity_tier: str | None = None,
    ) -> list[SkillMatch]:
        """Run the multi-signal selection pipeline and return ranked matches."""
        if not query or not query.strip():
            return []

        all_skills = self._registry.get_all()
        if not all_skills:
            return []

        # Accumulator: skill_id -> partial match data
        candidates: dict[str, _CandidateInfo] = {}

        # 1. Alias resolution (fast path)
        self._alias_pass(query, all_skills, candidates)

        # 2. Trigger regex scan
        self._trigger_pass(query, all_skills, candidates)

        # 3. Semantic embedding query
        self._semantic_pass(query, candidates)

        # 4. Merge & score
        matches = self._merge_candidates(all_skills, candidates)

        # 5. Agent policy filtering
        matches = self._apply_agent_policy(matches, agent_skill_policy, max_skills)

        # 6. Conflict resolution
        matches = self._resolve_conflicts(matches)

        # 7. Dependency expansion
        matches = self._expand_dependencies(matches, all_skills)

        # 8. Sort descending by composite_score, cap to max_skills
        matches.sort(key=lambda m: m.composite_score, reverse=True)
        effective_max = max_skills
        if agent_skill_policy and "max_skills" in agent_skill_policy:
            effective_max = int(agent_skill_policy["max_skills"])
        return matches[:effective_max]

    def select_by_name_or_query(self, input_text: str) -> SkillMatch | None:
        """Resolve a single skill by name, alias, or semantic query."""
        # Try alias resolution first
        skill_id = self._registry.resolve_alias(input_text.lower().strip())
        if skill_id:
            skill = self._registry.get(skill_id)
            if skill:
                return SkillMatch(
                    skill=skill,
                    semantic_score=1.0,
                    trigger_matched=False,
                    alias_matched=True,
                    composite_score=1.0,
                    selection_reason=f"direct match: {input_text}",
                )

        # Try canonical ID
        skill = self._registry.get(input_text.lower().strip().replace(" ", "-"))
        if skill:
            return SkillMatch(
                skill=skill,
                semantic_score=1.0,
                trigger_matched=False,
                alias_matched=False,
                composite_score=1.0,
                selection_reason=f"id match: {skill.id}",
            )

        # Fall back to full selection with max_skills=1
        matches = self.select(input_text, max_skills=1)
        return matches[0] if matches else None

    # ------------------------------------------------------------------
    # Pipeline stages
    # ------------------------------------------------------------------

    def _alias_pass(
        self,
        query: str,
        all_skills: dict[str, SkillDefinition],
        candidates: dict[str, _CandidateInfo],
    ) -> None:
        words = _normalize_words(query)

        for skill_id, defn in all_skills.items():
            # Check if the skill ID itself appears as a word.
            if skill_id.lower() in words:
                info = candidates.setdefault(skill_id, _CandidateInfo())
                info.alias_matched = True
                info.alias_label = skill_id
                continue

            # Check declared aliases.
            for alias in defn.aliases:
                if alias.lower() in words:
                    info = candidates.setdefault(skill_id, _CandidateInfo())
                    info.alias_matched = True
                    info.alias_label = alias
                    break

    def _trigger_pass(
        self,
        query: str,
        all_skills: dict[str, SkillDefinition],
        candidates: dict[str, _CandidateInfo],
    ) -> None:
        for skill_id, defn in all_skills.items():
            if not defn.triggers:
                continue
            for pattern in defn.triggers:
                if pattern.search(query):
                    info = candidates.setdefault(skill_id, _CandidateInfo())
                    info.trigger_matched = True
                    break

    def _semantic_pass(
        self,
        query: str,
        candidates: dict[str, _CandidateInfo],
    ) -> None:
        pairs = self._index.query(query, n_results=8)
        for skill_id, similarity in pairs:
            info = candidates.setdefault(skill_id, _CandidateInfo())
            info.semantic_score = similarity

    @staticmethod
    def _merge_candidates(
        all_skills: dict[str, SkillDefinition],
        candidates: dict[str, _CandidateInfo],
    ) -> list[SkillMatch]:
        results: list[SkillMatch] = []
        for skill_id, info in candidates.items():
            defn = all_skills.get(skill_id)
            if defn is None:
                continue

            raw_score = (
                (info.semantic_score * 0.6)
                + (0.4 if info.trigger_matched else 0.0)
                + (1.0 if info.alias_matched else 0.0)
            )
            composite = min(raw_score, 1.0)

            # Build reason string
            reasons: list[str] = []
            if info.alias_matched:
                reasons.append(f"alias match: {info.alias_label}")
            if info.trigger_matched:
                reasons.append("trigger regex matched")
            if info.semantic_score > 0.0:
                reasons.append(f"semantic similarity={info.semantic_score:.2f}")
            reason = "; ".join(reasons) if reasons else "no signal"

            results.append(
                SkillMatch(
                    skill=defn,
                    semantic_score=info.semantic_score,
                    trigger_matched=info.trigger_matched,
                    alias_matched=info.alias_matched,
                    composite_score=composite,
                    selection_reason=reason,
                )
            )
        return results

    @staticmethod
    def _apply_agent_policy(
        matches: list[SkillMatch],
        policy: dict[str, Any] | None,
        default_max: int,
    ) -> list[SkillMatch]:
        if policy is None:
            return matches

        if not policy.get("enabled", True):
            return []

        enabled_skills: list[str] | None = policy.get("enabled_skills")
        disabled_skills: list[str] | None = policy.get("disabled_skills")

        if enabled_skills is not None:
            allowed = set(enabled_skills)
            matches = [m for m in matches if m.skill.id in allowed]

        if disabled_skills is not None:
            blocked = set(disabled_skills)
            matches = [m for m in matches if m.skill.id not in blocked]

        return matches

    @staticmethod
    def _resolve_conflicts(matches: list[SkillMatch]) -> list[SkillMatch]:
        # Sort descending so the first occurrence wins.
        matches.sort(key=lambda m: m.composite_score, reverse=True)
        selected_ids: set[str] = set()
        blocked_ids: set[str] = set()
        result: list[SkillMatch] = []

        for match in matches:
            sid = match.skill.id
            if sid in blocked_ids:
                continue
            result.append(match)
            selected_ids.add(sid)
            # Block anything this skill conflicts with.
            for conflict_id in match.skill.conflicts:
                if conflict_id not in selected_ids:
                    blocked_ids.add(conflict_id)

        return result

    def _expand_dependencies(
        self,
        matches: list[SkillMatch],
        all_skills: dict[str, SkillDefinition],
    ) -> list[SkillMatch]:
        selected_ids = {m.skill.id for m in matches}
        extra: list[SkillMatch] = []

        for match in matches:
            for req_id in match.skill.requires:
                if req_id in selected_ids:
                    continue
                dep = all_skills.get(req_id)
                if dep is None:
                    dep = self._registry.get(req_id)
                if dep is None:
                    continue
                extra.append(
                    SkillMatch(
                        skill=dep,
                        semantic_score=0.0,
                        trigger_matched=False,
                        alias_matched=False,
                        composite_score=0.0,
                        selection_reason=f"dependency of {match.skill.id}",
                    )
                )
                selected_ids.add(req_id)

        return matches + extra


# ---------------------------------------------------------------------------
# Internal accumulator
# ---------------------------------------------------------------------------


@dataclass
class _CandidateInfo:
    semantic_score: float = 0.0
    trigger_matched: bool = False
    alias_matched: bool = False
    alias_label: str = ""


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_shared_selector: SkillSelector | None = None


def get_shared_selector() -> SkillSelector:
    """Return (and lazily create) the process-wide :class:`SkillSelector`."""
    global _shared_selector  # noqa: PLW0603
    if _shared_selector is None:
        from koda.skills._index import get_shared_index
        from koda.skills._registry import get_shared_registry

        registry = get_shared_registry()
        index = get_shared_index()
        # Ensure index is built
        index.rebuild(registry.get_all())
        _shared_selector = SkillSelector(registry, index)
    return _shared_selector
