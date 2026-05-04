"""Prompt template management with JSON storage."""

import json
import os
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


_SKILL_TEMPLATES: dict[str, str] = {}
_CURATED_TEMPLATE_NAMES = frozenset(_BUILTIN_TEMPLATES.keys())


def build_skills_awareness_prompt() -> str:
    """Return no global skills prompt; runtime skills are agent-scoped."""
    return ""


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
    """Get all templates (built-in + user)."""
    result: dict[str, str] = {}
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
    user = _load_templates()
    for candidate in _template_key_candidates(normalized):
        if candidate in user:
            return user[candidate]
    return None


def get_skill_template(name: str) -> str | None:
    """Compatibility shim: runtime skills are resolved from the current agent spec."""
    return None


def add_template(name: str, content: str) -> None:
    """Add or update a user template."""
    normalized = _normalize_template_name(name)
    if not normalized:
        raise ValueError("template name is required")
    if _is_curated_name(normalized):
        raise ValueError(f"'{normalized}' is reserved for built-in templates")
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
    return [], sorted(_BUILTIN_TEMPLATES.keys()), displayed_user
