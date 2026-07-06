"""Runtime helpers for resolving agent-scoped skills."""

from __future__ import annotations

import json
import os
from typing import Any

from koda.config import AGENT_ID


def _normalize_string_set(value: Any) -> frozenset[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list | tuple | set):
        values = list(value)
    else:
        return frozenset()
    return frozenset(str(item).strip() for item in values if str(item).strip())


def get_runtime_agent_spec() -> dict[str, Any]:
    """Return the current agent spec from runtime env or control-plane state."""
    raw = os.environ.get("AGENT_SPEC_JSON", "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            return parsed

    if not AGENT_ID:
        return {}

    try:
        from koda.control_plane.manager import get_control_plane_manager

        spec = get_control_plane_manager().get_agent_spec(AGENT_ID)
    except Exception:
        return {}
    return spec if isinstance(spec, dict) else {}


def get_runtime_custom_skills(agent_spec: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    spec = agent_spec if agent_spec is not None else get_runtime_agent_spec()
    policy = get_runtime_skill_policy(spec)
    skills = spec.get("custom_skills") if isinstance(spec, dict) else []
    custom = [skill for skill in skills if isinstance(skill, dict)] if isinstance(skills, list) else []
    try:
        from koda.skills._package import get_installed_package_skills

        installed = get_installed_package_skills(AGENT_ID or str(spec.get("id") or "default"))
    except Exception:
        installed = []
    allowed_packages = _normalize_string_set(policy.get("enabled_skill_packages"))
    installed = [
        skill
        for skill in installed
        if isinstance(skill, dict) and str(skill.get("source_package_id") or "").strip() in allowed_packages
    ]
    return [*custom, *installed]


def get_runtime_skill_policy(agent_spec: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = agent_spec if agent_spec is not None else get_runtime_agent_spec()
    policy = spec.get("skill_policy") if isinstance(spec, dict) else {}
    return dict(policy) if isinstance(policy, dict) else {}


def is_skill_allowed_by_policy(skill: dict[str, Any] | str, policy: dict[str, Any] | None) -> bool:
    if not policy or not policy.get("enabled", True):
        return False

    skill_id = str(skill.get("id") if isinstance(skill, dict) else skill).strip()
    if not skill_id:
        return False

    enabled_skills = _normalize_string_set(policy.get("enabled_skills"))
    if not enabled_skills or skill_id not in enabled_skills:
        return False

    disabled_skills = _normalize_string_set(policy.get("disabled_skills"))
    if skill_id in disabled_skills:
        return False

    if isinstance(skill, dict):
        package_id = str(skill.get("source_package_id") or "").strip()
        if package_id:
            enabled_packages = _normalize_string_set(policy.get("enabled_skill_packages"))
            return package_id in enabled_packages

    return True


def is_skill_package_allowed(package_id: str, policy: dict[str, Any] | None) -> bool:
    if not policy or not policy.get("enabled", True):
        return False
    normalized = str(package_id).strip()
    if not normalized:
        return False
    return normalized in _normalize_string_set(policy.get("enabled_skill_packages"))
