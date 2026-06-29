"""Skill definition dataclass and agent-scoped in-memory registry."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from koda.skills._runtime import is_skill_allowed_by_policy

# Regex helpers

_WHEN_TO_USE_RE = re.compile(r"<when_to_use>\s*(.*?)\s*</when_to_use>", re.DOTALL)
_FIRST_SENTENCE_RE = re.compile(r"^(.*?[.!?])(?:\s|$)")


# SkillDefinition


@dataclass(frozen=True)
class SkillDefinition:
    """Immutable representation of a parsed skill file."""

    id: str
    name: str
    aliases: tuple[str, ...] = ()
    version: str = "1.0.0"
    category: str = "general"
    tags: tuple[str, ...] = ()
    when_to_use: str = ""
    awareness_summary: str = ""
    triggers: tuple[re.Pattern[str], ...] = ()
    embedding_text: str = ""
    full_content: str = ""
    requires: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    base_priority: int = 50
    max_token_budget: int = 2000
    model_hints: dict[str, Any] = field(default_factory=dict)
    source_path: Path | None = None
    source_package_id: str = ""
    last_modified: float = 0.0
    frontmatter_present: bool = False
    instruction: str = ""
    output_format_enforcement: str = ""


# Builders


def _first_sentence(text: str) -> str:
    """Return the first sentence of *text*, or the whole string if short."""
    text = text.strip()
    m = _FIRST_SENTENCE_RE.search(text)
    if m:
        return m.group(1).strip()
    # No sentence-ending punctuation — return the whole thing (capped).
    return text[:200]


def _compile_triggers(raw: list[str] | None) -> tuple[re.Pattern[str], ...]:
    if not raw:
        return ()
    patterns: list[re.Pattern[str]] = []
    for pat in raw:
        try:
            patterns.append(re.compile(pat, re.IGNORECASE))
        except re.error:
            continue
    return tuple(patterns)


def _normalize_string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _label_keys(value: str) -> tuple[str, ...]:
    normalized = value.lower().strip()
    if not normalized:
        return ()
    slug = re.sub(r"[\s_]+", "-", normalized)
    if slug == normalized:
        return (normalized,)
    return (normalized, slug)


def _is_skill_enabled(raw: dict[str, Any]) -> bool:
    value = raw.get("enabled", True)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def _build_skill_from_dict(raw: dict[str, Any]) -> SkillDefinition:
    """Build a SkillDefinition from a control-plane custom skill dict."""
    skill_id = str(raw.get("id", "")).strip()
    name = str(raw.get("name", skill_id)).strip() or skill_id
    aliases = _normalize_string_tuple(raw.get("aliases", []))
    tags = _normalize_string_tuple(raw.get("tags", []))
    category = str(raw.get("category", "general")).strip() or "general"
    instruction = str(raw.get("instruction", "")).strip()
    content = str(raw.get("content", "")).strip()
    output_format_enforcement = str(raw.get("output_format_enforcement", "")).strip()
    requires = _normalize_string_tuple(raw.get("requires", []))
    conflicts = _normalize_string_tuple(raw.get("conflicts", []))
    triggers = _compile_triggers(list(_normalize_string_tuple(raw.get("triggers", []))))

    when_to_use = ""
    wtu_match = _WHEN_TO_USE_RE.search(content)
    if wtu_match:
        when_to_use = wtu_match.group(1).strip()

    awareness_summary = _first_sentence(when_to_use) if when_to_use else instruction or name

    parts = [name]
    parts.extend(aliases)
    if when_to_use:
        parts.append(when_to_use)
    elif instruction:
        parts.append(instruction)
    parts.extend(tags)
    embedding_text = ". ".join(parts)

    return SkillDefinition(
        id=skill_id,
        name=name,
        aliases=aliases,
        version=str(raw.get("version", "1.0.0")),
        category=category,
        tags=tags,
        when_to_use=when_to_use,
        awareness_summary=awareness_summary,
        triggers=triggers,
        embedding_text=embedding_text,
        full_content=content,
        requires=requires,
        conflicts=conflicts,
        base_priority=_coerce_int(raw.get("base_priority", 50), 50),
        max_token_budget=_coerce_int(raw.get("max_token_budget", 2500), 2500),
        model_hints=raw.get("model_hints", {}) if isinstance(raw.get("model_hints"), dict) else {},
        source_path=None,
        source_package_id=str(raw.get("source_package_id") or "").strip(),
        last_modified=0.0,
        frontmatter_present=False,
        instruction=instruction,
        output_format_enforcement=output_format_enforcement,
    )


# Registry


class SkillRegistry:
    """In-memory registry scoped to one agent's configured skills."""

    def __init__(self, skills: dict[str, SkillDefinition] | list[SkillDefinition] | None = None) -> None:
        if isinstance(skills, dict):
            self._skills = dict(skills)
        else:
            self._skills = {skill.id: skill for skill in skills or [] if skill.id}
        self._alias_index: dict[str, str] = {}
        self._rebuild_alias_index()

    # -- public API --

    def get_all(self) -> dict[str, SkillDefinition]:
        """Return a snapshot of all registered skills keyed by ID."""
        return dict(self._skills)

    def get(self, skill_id: str) -> SkillDefinition | None:
        """Return a single skill by canonical ID, or ``None``."""
        return self._skills.get(skill_id)

    def resolve_alias(self, name: str) -> str | None:
        """Resolve an alias (case-insensitive) to a canonical skill ID."""
        normalized = name.lower().strip()
        return self._alias_index.get(normalized) or (normalized if normalized in self._skills else None)

    def reload_if_stale(self) -> bool:
        """Compatibility no-op for the old file-backed registry API."""
        return False

    def _rebuild_alias_index(self) -> None:
        index: dict[str, str] = {}
        for defn in self._skills.values():
            index[defn.id.lower()] = defn.id
            for key in _label_keys(defn.name):
                index.setdefault(key, defn.id)
            for alias in defn.aliases:
                for key in _label_keys(alias):
                    index.setdefault(key, defn.id)
        self._alias_index = index


def build_skill_registry_from_custom_skills(
    custom_skills: list[dict[str, Any]] | None,
    skill_policy: dict[str, Any] | None = None,
) -> SkillRegistry:
    """Build an agent-scoped registry from ``agent_spec.custom_skills``."""
    skills: dict[str, SkillDefinition] = {}
    for raw in custom_skills or []:
        if not isinstance(raw, dict) or not _is_skill_enabled(raw):
            continue
        skill = _build_skill_from_dict(raw)
        if skill.id and skill.full_content.strip() and is_skill_allowed_by_policy(raw, skill_policy):
            skills[skill.id] = skill
    return SkillRegistry(skills)


# Compatibility singleton: intentionally empty, never file-backed.

_shared_registry: SkillRegistry | None = None


def get_shared_registry() -> SkillRegistry:
    """Return an empty process-wide registry for legacy callers."""
    global _shared_registry  # noqa: PLW0603
    if _shared_registry is None:
        _shared_registry = SkillRegistry()
    return _shared_registry
