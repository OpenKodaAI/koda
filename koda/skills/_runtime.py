"""Runtime helpers for resolving agent-scoped skills."""

from __future__ import annotations

import json
import os
from typing import Any

from koda.config import AGENT_ID


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
    skills = spec.get("custom_skills") if isinstance(spec, dict) else []
    return [skill for skill in skills if isinstance(skill, dict)] if isinstance(skills, list) else []


def get_runtime_skill_policy(agent_spec: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = agent_spec if agent_spec is not None else get_runtime_agent_spec()
    policy = spec.get("skill_policy") if isinstance(spec, dict) else {}
    return dict(policy) if isinstance(policy, dict) else {}
