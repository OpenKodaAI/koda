"""Smoke checks for the default PT-BR squad agent templates.

The repository ships five seed AgentSpec JSON files under
``koda/control_plane/data/squad_agent_templates/``. They are not auto-loaded
into the runtime — operators copy them into their control-plane spec via the
existing onboarding flow. These tests guarantee the seeds stay valid as the
AgentSpec normalizer evolves.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from koda.control_plane.agent_spec import normalize_agent_spec
from koda.squads.coordinator import REQUIRED_COORDINATOR_TOOL_IDS, validate_eligibility

TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "koda" / "control_plane" / "data" / "squad_agent_templates"

EXPECTED_AGENTS = {
    "COORDENADOR_PM",
    "PESQUISADOR",
    "FRONTEND_DEV",
    "BACKEND_DEV",
    "MARKETING",
}


def _load_template(filename: str) -> dict:
    with (TEMPLATE_DIR / filename).open() as fh:
        return json.load(fh)


def test_template_dir_has_five_files() -> None:
    files = sorted(p.name for p in TEMPLATE_DIR.glob("*.json"))
    assert len(files) == 5, f"expected 5 templates, found {len(files)}: {files}"


@pytest.mark.parametrize(
    "filename",
    sorted(p.name for p in TEMPLATE_DIR.glob("*.json")),
)
def test_template_parses_and_normalizes(filename: str) -> None:
    spec = _load_template(filename)
    assert spec.get("agent_id") in EXPECTED_AGENTS
    norm = normalize_agent_spec(spec)
    assert norm["agent_id"]
    mission = norm.get("mission_profile") or {}
    assert mission.get("role"), f"{filename} missing mission_profile.role"
    assert mission.get("domains"), f"{filename} missing mission_profile.domains"
    assert mission.get("delegate_when"), f"{filename} missing mission_profile.delegate_when"
    assert mission.get("do_not_delegate"), f"{filename} missing mission_profile.do_not_delegate"
    tool_policy = norm.get("tool_policy") or {}
    assert tool_policy.get("allowed_tool_ids"), f"{filename} missing tool_policy.allowed_tool_ids"


def test_coordenador_template_is_eligible_to_coordinate() -> None:
    """The Coordenador / PM template must allow every required coordinator tool."""
    spec = normalize_agent_spec(_load_template("coordenador_pm.json"))
    ok, missing = validate_eligibility(spec)
    assert ok, f"COORDENADOR_PM missing tools: {missing}"
    allowed = set(spec.get("tool_policy", {}).get("allowed_tool_ids") or [])
    for tool in REQUIRED_COORDINATOR_TOOL_IDS:
        assert tool in allowed, f"COORDENADOR_PM should declare {tool}"


@pytest.mark.parametrize(
    "filename",
    sorted(p.name for p in TEMPLATE_DIR.glob("*.json") if p.name != "coordenador_pm.json"),
)
def test_specialist_templates_have_squad_messaging_tools(filename: str) -> None:
    """Every specialist must at least be able to read their inbox and post results."""
    spec = normalize_agent_spec(_load_template(filename))
    allowed = set(spec.get("tool_policy", {}).get("allowed_tool_ids") or [])
    for tool in (
        "squad_post",
        "squad_thread_history",
        "squad_task_claim",
        "squad_task_complete",
        "squad_inbox_drain",
        "squad_telegram_post",
    ):
        assert tool in allowed, f"{filename} should declare {tool}"


def test_each_template_has_a_delegation_policy() -> None:
    for path in TEMPLATE_DIR.glob("*.json"):
        spec = normalize_agent_spec(_load_template(path.name))
        policy = spec.get("delegation_policy") or {}
        assert policy.get("mode") in {"auto", "always_self", "always_delegate"}, path.name
