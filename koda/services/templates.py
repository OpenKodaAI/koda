"""Prompt template management with JSON storage."""

import json
import os
import re
import unicodedata
from pathlib import Path

from koda.config import AGENT_ID, SCRIPT_DIR
from koda.logging_config import get_logger

log = get_logger(__name__)

_bid = AGENT_ID.lower() if AGENT_ID else None


def _load_inline_mapping(env_key: str) -> dict[str, str]:
    raw = os.environ.get(env_key, "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("templates_inline_json_invalid", env_key=env_key)
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value).strip() for key, value in data.items() if str(key).strip() and str(value).strip()}


_templates_override = os.environ.get("TEMPLATES_PATH")
if _templates_override:
    TEMPLATES_PATH = Path(_templates_override)
    if not TEMPLATES_PATH.is_absolute():
        TEMPLATES_PATH = SCRIPT_DIR / TEMPLATES_PATH
else:
    TEMPLATES_PATH = (SCRIPT_DIR / f"templates_{_bid}.json") if _bid else (SCRIPT_DIR / "templates.json")

_skills_override = os.environ.get("SKILLS_DIR")
if _skills_override:
    SKILLS_DIR = Path(_skills_override)
    if not SKILLS_DIR.is_absolute():
        SKILLS_DIR = SCRIPT_DIR / SKILLS_DIR
else:
    SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"

# Built-in templates
_BUILTIN_TEMPLATES: dict[str, str] = {
    "debug": (
        "Debug this issue systematically:\n"
        "1. Read the relevant code and understand the expected behavior.\n"
        "2. Identify the root cause — trace the data flow and find where it diverges from expected.\n"
        "3. Check for common pitfalls: off-by-one errors, null or undefined values, "
        "race conditions, and wrong assumptions about input.\n"
        "4. Propose a fix with the minimal change needed. "
        "Explain why this is the root cause, not just a symptom.\n"
        "5. If the project has tests, write a test that reproduces the bug before fixing it."
    ),
    "write-tests": (
        "Write comprehensive tests for this code:\n"
        "1. Identify the public interface and core behaviors to test.\n"
        "2. Cover the happy path, edge cases (empty input, boundaries, large data), and error scenarios.\n"
        "3. Follow the project's existing test patterns, naming conventions, and test framework.\n"
        "4. Each test should test one behavior with a descriptive name that reads as a specification.\n"
        "5. Use arrange-act-assert structure. Mock external dependencies, not internal logic.\n"
        "6. Run the tests to verify they pass."
    ),
    "explain": (
        "Explain this code clearly and concisely:\n"
        "1. Start with a one-sentence summary of what this code does and why it exists.\n"
        "2. Walk through the key logic, explaining non-obvious decisions.\n"
        "3. Identify patterns used (design patterns, architectural patterns, idioms).\n"
        "4. Note any trade-offs, limitations, or potential improvements.\n"
        "5. Adjust the depth of explanation to the complexity — simple code needs a brief explanation."
    ),
    "refactor": (
        "Refactor this code to improve quality:\n"
        "1. Read and understand the current behavior fully before changing anything.\n"
        "2. Identify the specific problems: duplication, excessive complexity, "
        "poor naming, and violation of SOLID principles.\n"
        "3. Make changes incrementally — each step should keep tests passing.\n"
        "4. Explain each change and the principle behind it (DRY, SRP, extract method, etc.).\n"
        "5. Preserve the external behavior exactly — refactoring changes structure, not functionality.\n"
        "6. Run tests after refactoring to confirm nothing broke."
    ),
}


def _load_skills() -> dict[str, str]:
    """Load skill templates from .md files in the skills directory."""
    inline_skills = _load_inline_mapping("SKILLS_JSON")
    if inline_skills:
        return inline_skills
    skills: dict[str, str] = {}
    if not SKILLS_DIR.is_dir():
        return skills
    for md_file in sorted(SKILLS_DIR.glob("*.md")):
        name = md_file.stem
        try:
            content = md_file.read_text(encoding="utf-8").strip()
            if content:
                skills[name] = content
        except OSError:
            log.warning("skill_load_failed", name=name, path=str(md_file))
    return skills


_SKILL_TEMPLATES: dict[str, str] = _load_skills()
_CURATED_TEMPLATE_NAMES = frozenset({*_BUILTIN_TEMPLATES.keys(), *_SKILL_TEMPLATES.keys()})

_WHEN_TO_USE_RE = re.compile(r"<when_to_use>\s*(.*?)\s*</when_to_use>", re.DOTALL)
_WORD_RE = re.compile(r"[a-z0-9_+-]+", re.IGNORECASE)
_MATCH_SYNONYMS: dict[str, str] = {
    "seguranca": "security",
    "seguro": "security",
    "arquitetura": "architecture",
    "arquitetural": "architecture",
    "revisao": "review",
    "codigo": "code",
    "teste": "test",
    "testes": "test",
    "banco": "database",
}


def _normalize_skill_match_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    tokens = [token for token in _WORD_RE.findall(ascii_text) if token]
    mapped = [_MATCH_SYNONYMS.get(token, token) for token in tokens]
    return " ".join(mapped)


def build_skills_awareness_prompt() -> str:
    """Build a compact <expert_skills> section listing available skills and when to use them."""
    if not _SKILL_TEMPLATES:
        return ""

    lines: list[str] = []
    for name in sorted(_SKILL_TEMPLATES):
        match = _WHEN_TO_USE_RE.search(_SKILL_TEMPLATES[name])
        desc = match.group(1).strip().split(". ")[0] + "." if match else ""
        if desc:
            lines.append(f"- **{name}**: {desc}")

    if not lines:
        return ""

    return (
        "<expert_skills>\n"
        "You have access to expert skill templates — specialized methodologies for specific domains.\n"
        "When a user's request clearly matches a skill, proactively apply its methodology or suggest "
        "the skill to the user. The user can also invoke directly with `/skill <name> [question]`.\n\n"
        "Available skills:\n" + "\n".join(lines) + "\n</expert_skills>"
    )


def select_relevant_skills(query: str, *, max_skills: int = 4) -> list[dict[str, str | float]]:
    """Return scored curated skills for a query without formatting them into a prompt."""
    normalized_query = _normalize_skill_match_text(query)
    if not normalized_query or not _SKILL_TEMPLATES:
        return []

    query_tokens = {token for token in _WORD_RE.findall(normalized_query) if len(token) >= 3}
    scored: list[tuple[float, str, str]] = []
    for name, content in sorted(_SKILL_TEMPLATES.items()):
        when_to_use = _WHEN_TO_USE_RE.search(content)
        description = when_to_use.group(1).strip() if when_to_use else ""
        haystack = _normalize_skill_match_text(" ".join([name.replace("-", " "), description]))
        haystack_tokens = {token for token in _WORD_RE.findall(haystack) if len(token) >= 3}
        if not haystack_tokens:
            continue
        overlap = len(query_tokens & haystack_tokens)
        name_match = name in normalized_query or name.replace("-", " ") in normalized_query
        if not overlap and not name_match:
            continue
        score = float(overlap) + (2.0 if name_match else 0.0)
        summary = description.split(". ")[0].strip() if description else ""
        if summary and not summary.endswith("."):
            summary += "."
        scored.append((score, name, summary))

    return [
        {"score": score, "name": name, "summary": summary or "Specialized methodology available for this kind of task."}
        for score, name, summary in sorted(scored, key=lambda item: (-item[0], item[1]))[: max(1, max_skills)]
    ]


def build_relevant_skills_awareness_prompt(query: str, *, max_skills: int = 4) -> str:
    """Build a compact skills hint only when the query clearly matches curated skills."""
    relevant_skills = select_relevant_skills(query, max_skills=max_skills)
    if not relevant_skills:
        return ""

    lines = []
    for skill in relevant_skills:
        lines.append(f"- **{skill['name']}**: {skill['summary']}")
    return (
        "<expert_skills>\n"
        "Relevant curated expert skills are available for this request.\n"
        "Apply them when they materially improve quality or specificity.\n\n"
        "Relevant skills:\n" + "\n".join(lines) + "\n</expert_skills>"
    )


_SKILLS_AWARENESS_PROMPT: str = build_skills_awareness_prompt()


def _load_templates() -> dict[str, str]:
    """Load user templates from JSON file."""
    inline_templates = _load_inline_mapping("TEMPLATES_JSON")
    if inline_templates:
        return inline_templates
    if not TEMPLATES_PATH.exists():
        return {}
    try:
        data = json.loads(TEMPLATES_PATH.read_text())
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        log.warning("templates_load_failed", path=str(TEMPLATES_PATH))
        return {}


def _save_templates(templates: dict[str, str]) -> None:
    """Save user templates to JSON file."""
    TEMPLATES_PATH.write_text(json.dumps(templates, indent=2))


def _normalize_template_name(name: str) -> str:
    return str(name or "").strip()


def _user_template_storage_key(name: str) -> str:
    normalized = _normalize_template_name(name)
    if not normalized:
        return ""
    return normalized if normalized.startswith("user/") else f"user/{normalized}"


def _template_key_candidates(name: str) -> list[str]:
    normalized = _normalize_template_name(name)
    if not normalized:
        return []
    candidates = [normalized]
    user_key = _user_template_storage_key(normalized)
    if user_key and user_key not in candidates:
        candidates.append(user_key)
    return candidates


def _user_template_display_name(key: str) -> str:
    return key.split("/", 1)[1] if key.startswith("user/") else key


def _display_user_templates(user_templates: dict[str, str]) -> dict[str, str]:
    displayed: dict[str, str] = {}
    for key, content in user_templates.items():
        display = _user_template_display_name(key)
        if display in _CURATED_TEMPLATE_NAMES:
            displayed[key] = content
        else:
            displayed[display] = content
    return displayed


def _is_curated_name(name: str) -> bool:
    normalized = _normalize_template_name(name)
    if not normalized:
        return False
    basename = normalized.split("/", 1)[1] if normalized.startswith("user/") else normalized
    return basename in _CURATED_TEMPLATE_NAMES or normalized in _CURATED_TEMPLATE_NAMES


def get_all_templates() -> dict[str, str]:
    """Get all templates (skills + built-in + user)."""
    result = dict(_SKILL_TEMPLATES)
    result.update(_BUILTIN_TEMPLATES)
    result.update(_display_user_templates(_load_templates()))
    return result


def get_template(name: str) -> str | None:
    """Get a template by name. Returns None if not found."""
    normalized = _normalize_template_name(name)
    if not normalized:
        return None
    if normalized in _BUILTIN_TEMPLATES:
        return _BUILTIN_TEMPLATES[normalized]
    if normalized in _SKILL_TEMPLATES:
        return _SKILL_TEMPLATES[normalized]
    user = _load_templates()
    for candidate in _template_key_candidates(normalized):
        if candidate in user:
            return user[candidate]
    return None


def get_skill_template(name: str) -> str | None:
    """Get a curated runtime skill by name."""
    normalized = _normalize_template_name(name)
    return _SKILL_TEMPLATES.get(normalized) if normalized else None


def add_template(name: str, content: str) -> None:
    """Add or update a user template."""
    normalized = _normalize_template_name(name)
    if not normalized:
        raise ValueError("template name is required")
    if _is_curated_name(normalized):
        raise ValueError(f"'{normalized}' is reserved for curated skills or built-in templates")
    storage_key = _user_template_storage_key(normalized)
    if not storage_key:
        raise ValueError("template name is required")
    templates = _load_templates()
    templates[storage_key] = content
    _save_templates(templates)
    log.info("template_added", name=storage_key)


def delete_template(name: str) -> bool:
    """Delete a user template. Returns False if it's a built-in, skill, or not found."""
    normalized = _normalize_template_name(name)
    if not normalized or _is_curated_name(normalized):
        return False
    templates = _load_templates()
    target_key = next((candidate for candidate in _template_key_candidates(normalized) if candidate in templates), None)
    if target_key is None:
        return False
    del templates[target_key]
    _save_templates(templates)
    log.info("template_deleted", name=target_key)
    return True


def list_template_names() -> tuple[list[str], list[str], list[str]]:
    """Return (skill_names, builtin_names, user_names)."""
    user = _load_templates()
    displayed_user = sorted(_display_user_templates(user).keys())
    return sorted(_SKILL_TEMPLATES.keys()), sorted(_BUILTIN_TEMPLATES.keys()), displayed_user
