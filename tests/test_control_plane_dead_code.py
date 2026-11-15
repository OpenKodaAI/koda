"""Dead control-plane code is gone (M4-E1-T8).

TD-070: the legacy state import, off by default, parsed a sibling repository that does not
exist. TD-071: the 410 stub for the old combined onboarding call and the HTML page that only
pointed to the dashboard's /setup. TD-038: the custom MCP HMAC signature was stored and never
verified. TD-037: nothing called the sandbox policy gate functions; only doctor evaluates it.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from koda.control_plane import api as control_plane_api
from koda.control_plane import manager as manager_module
from koda.control_plane import onboarding, settings
from koda.integrations import custom_mcp_registry
from koda.services import sandbox_policy

ROOT = Path(__file__).resolve().parents[1]


def test_legacy_state_import_is_gone() -> None:
    for name in (
        "import_legacy_state",
        "_load_legacy_env",
        "_discover_legacy_agent_ids",
        "_assign_env_value",
        "_import_legacy_templates",
    ):
        assert not hasattr(manager_module.ControlPlaneManager, name), name
    for name in ("_parse_dashboard_appearance", "_TELEGRAM_AGENT_TOKEN_RE", "CONTROL_PLANE_AUTO_IMPORT"):
        assert not hasattr(manager_module, name), name
    for name in ("CONTROL_PLANE_AUTO_IMPORT", "DASHBOARD_PATH", "DASHBOARD_AGENT_CONSTANTS_PATH"):
        assert not hasattr(settings, name), name


def test_removed_handlers_are_gone() -> None:
    for name in ("onboarding_bootstrap", "setup_page", "setup_landing"):
        assert not hasattr(control_plane_api, name), name
    assert not hasattr(onboarding, "render_setup_page")


def test_custom_mcp_servers_carry_no_unverified_signature() -> None:
    assert not hasattr(custom_mcp_registry, "compute_validation_signature")
    for function in (
        custom_mcp_registry.validate_payload,
        custom_mcp_registry.upsert_custom_server,
        custom_mcp_registry.import_claude_desktop_json,
    ):
        assert "secret_key" not in inspect.signature(function).parameters, function.__name__
    payload = custom_mcp_registry.CustomServerPayload(
        server_key="custom_my_server", display_name="My server", command=["npx"], args=["-y", "@org/mcp"]
    )
    custom_mcp_registry.validate_payload(payload)
    assert "validation_signature" not in payload.metadata


def test_sandbox_policy_keeps_only_the_evaluation_doctor_uses() -> None:
    for name in ("sandbox_policy_allows_execution", "ensure_sandbox_policy_allows_execution", "SandboxPolicyDenied"):
        assert not hasattr(sandbox_policy, name), name
    assert callable(sandbox_policy.evaluate_sandbox_effective_policy)


def test_doctor_and_cli_no_longer_point_to_the_removed_page() -> None:
    assert "legacy_setup_url" not in (ROOT / "scripts" / "doctor.py").read_text(encoding="utf-8")
    cli = (ROOT / "packages" / "cli" / "bin" / "koda.mjs").read_text(encoding="utf-8")
    assert "legacy_setup_url" not in cli
    assert "Bridge:" not in cli
