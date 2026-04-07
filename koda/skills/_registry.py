"""Skill definition dataclass and file-backed registry."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)
_WHEN_TO_USE_RE = re.compile(r"<when_to_use>\s*(.*?)\s*</when_to_use>", re.DOTALL)
_FIRST_SENTENCE_RE = re.compile(r"^(.*?[.!?])(?:\s|$)")
_H1_RE = re.compile(r"^#\s+(.+)", re.MULTILINE)
_OUTPUT_FORMAT_RE = re.compile(
    r"^##\s+Output\s+Format\s*\n(.*?)(?=^##\s|\Z)",
    re.MULTILINE | re.DOTALL,
)


# ---------------------------------------------------------------------------
# SkillDefinition
# ---------------------------------------------------------------------------


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
    last_modified: float = 0.0
    frontmatter_present: bool = False
    instruction: str = ""
    output_format_enforcement: str = ""


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


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


def _parse_skill_file(path: Path) -> SkillDefinition:
    """Parse a single ``.md`` skill file into a :class:`SkillDefinition`."""
    raw = path.read_text(encoding="utf-8")
    skill_id = path.stem

    # --- frontmatter ---
    frontmatter: dict[str, Any] = {}
    body = raw
    fm_match = _FRONTMATTER_RE.match(raw)
    frontmatter_present = fm_match is not None
    if fm_match:
        try:
            frontmatter = yaml.safe_load(fm_match.group(1)) or {}
        except yaml.YAMLError:
            frontmatter = {}
        body = raw[fm_match.end() :]

    # --- when_to_use ---
    wtu_match = _WHEN_TO_USE_RE.search(body)
    when_to_use = wtu_match.group(1).strip() if wtu_match else ""

    # --- name ---
    name = frontmatter.get("name", "")
    if not name:
        h1 = _H1_RE.search(body)
        name = h1.group(1).strip() if h1 else skill_id.replace("-", " ").title()

    # --- simple fields ---
    aliases = tuple(frontmatter.get("aliases", []))
    version = str(frontmatter.get("version", "1.0.0"))
    category = frontmatter.get("category", "general")
    tags = tuple(frontmatter.get("tags", []))
    requires = tuple(frontmatter.get("requires", []))
    conflicts = tuple(frontmatter.get("conflicts", []))
    base_priority = int(frontmatter.get("base_priority", 50))
    max_token_budget = int(frontmatter.get("max_token_budget", 2000))
    model_hints: dict[str, Any] = frontmatter.get("model_hints", {}) or {}

    # --- instruction & output_format_enforcement ---
    instruction = str(frontmatter.get("instruction", ""))
    output_format_enforcement = str(frontmatter.get("output_format_enforcement", ""))

    # --- derived ---
    awareness_summary = _first_sentence(when_to_use) if when_to_use else ""
    triggers = _compile_triggers(frontmatter.get("triggers"))

    parts = [name]
    if aliases:
        parts.append(" ".join(aliases))
    if when_to_use:
        parts.append(when_to_use)
    if tags:
        parts.append(" ".join(tags))
    embedding_text = "\n".join(parts)

    stat = path.stat()

    return SkillDefinition(
        id=skill_id,
        name=name,
        aliases=aliases,
        version=version,
        category=category,
        tags=tags,
        when_to_use=when_to_use,
        awareness_summary=awareness_summary,
        triggers=triggers,
        embedding_text=embedding_text,
        full_content=body if frontmatter_present else raw,
        requires=requires,
        conflicts=conflicts,
        base_priority=base_priority,
        max_token_budget=max_token_budget,
        model_hints=model_hints,
        source_path=path,
        last_modified=stat.st_mtime,
        frontmatter_present=frontmatter_present,
        instruction=instruction,
        output_format_enforcement=output_format_enforcement,
    )


def _build_skill_from_dict(raw: dict[str, Any]) -> SkillDefinition:
    """Build a SkillDefinition from a control-plane custom skill dict."""
    skill_id = str(raw.get("id", ""))
    name = str(raw.get("name", skill_id))
    aliases = tuple(str(a) for a in raw.get("aliases", []))
    tags = tuple(str(t) for t in raw.get("tags", []))
    category = str(raw.get("category", "general"))
    instruction = str(raw.get("instruction", ""))
    content = str(raw.get("content", ""))
    output_format_enforcement = str(raw.get("output_format_enforcement", ""))

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
        version="1.0.0",
        category=category,
        tags=tags,
        when_to_use=when_to_use,
        awareness_summary=awareness_summary,
        triggers=(),
        embedding_text=embedding_text,
        full_content=content,
        requires=(),
        conflicts=(),
        base_priority=50,
        max_token_budget=2500,
        model_hints={},
        source_path=None,
        last_modified=0.0,
        frontmatter_present=False,
        instruction=instruction,
        output_format_enforcement=output_format_enforcement,
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class SkillRegistry:
    """File-backed registry that lazily scans a directory of ``.md`` skill files."""

    def __init__(self, skills_dir: Path, scan_interval: float = 30.0) -> None:
        self._skills_dir = skills_dir
        self._scan_interval = scan_interval
        self._skills: dict[str, SkillDefinition] = {}
        self._alias_index: dict[str, str] = {}
        self._last_scan: float = 0.0
        # Perform initial scan.
        self._skills = self._scan_directory()
        self._rebuild_alias_index()
        self._last_scan = time.monotonic()

    # -- public API --

    def get_all(self) -> dict[str, SkillDefinition]:
        """Return a snapshot of all registered skills keyed by ID."""
        self.reload_if_stale()
        return dict(self._skills)

    def get(self, skill_id: str) -> SkillDefinition | None:
        """Return a single skill by canonical ID, or ``None``."""
        self.reload_if_stale()
        return self._skills.get(skill_id)

    def resolve_alias(self, name: str) -> str | None:
        """Resolve an alias (case-insensitive) to a canonical skill ID."""
        self.reload_if_stale()
        return self._alias_index.get(name.lower())

    def reload_if_stale(self) -> bool:
        """Re-scan the directory if the scan interval has elapsed.

        Returns ``True`` if a reload was performed.
        """
        now = time.monotonic()
        if now - self._last_scan < self._scan_interval:
            return False

        new_skills = self._scan_directory()

        changed = set(new_skills.keys()) != set(self._skills.keys())
        if not changed:
            for sid, defn in new_skills.items():
                old = self._skills.get(sid)
                if old is None or defn.last_modified != old.last_modified:
                    changed = True
                    break

        if changed:
            self._skills = new_skills
            self._rebuild_alias_index()

        self._last_scan = now
        return changed

    # -- internals --

    def _scan_directory(self) -> dict[str, SkillDefinition]:
        skills: dict[str, SkillDefinition] = {}
        if not self._skills_dir.is_dir():
            return skills
        for path in sorted(self._skills_dir.glob("*.md")):
            try:
                defn = _parse_skill_file(path)
                skills[defn.id] = defn
            except Exception:  # noqa: BLE001
                # Skip unparseable files silently.
                continue
        return skills

    def merge_agent_skills(self, custom_skills: list[dict[str, Any]]) -> dict[str, SkillDefinition]:
        """Merge global skills with agent-specific custom skills.

        Custom skills override global skills with the same ID.
        """
        merged = dict(self.get_all())
        for raw in custom_skills:
            skill = _build_skill_from_dict(raw)
            if skill.id:
                merged[skill.id] = skill
        return merged

    def _rebuild_alias_index(self) -> None:
        index: dict[str, str] = {}
        for defn in self._skills.values():
            for alias in defn.aliases:
                index[alias.lower()] = defn.id
        self._alias_index = index


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_shared_registry: SkillRegistry | None = None


def get_shared_registry() -> SkillRegistry:
    """Return (and lazily create) the process-wide :class:`SkillRegistry`."""
    global _shared_registry  # noqa: PLW0603
    if _shared_registry is None:
        from koda.config import _env

        skills_dir = Path(_env("SKILLS_DIR", str(Path(__file__).parent)))
        _shared_registry = SkillRegistry(Path(skills_dir))
    return _shared_registry
