from __future__ import annotations

from koda.services.sandbox_doctor import (
    SANDBOX_DOCTOR_SCHEMA_VERSION,
    build_cli_sandbox_doctor_payload,
    build_sandbox_doctor_payload,
)


def test_sandbox_doctor_reports_versioned_policy_and_passed_checks() -> None:
    payload = build_sandbox_doctor_payload(
        agent_id="koda",
        task_id=12,
        runtime_kernel={"ready": True, "authoritative": True, "mode": "rust"},
        env={
            "KODA_MCP_ISOLATION": "docker",
            "KODA_MCP_NETWORK_MODE": "egress_allowlist",
            "BROWSER_ALLOW_PRIVATE_NETWORK": "false",
        },
        mcp_risk_summary={"unknown": 0, "high_risk": 0},
    )

    assert payload["doctor_version"] == SANDBOX_DOCTOR_SCHEMA_VERSION
    assert payload["agent_id"] == "KODA"
    assert payload["task_id"] == 12
    assert payload["effective_policy"]["policy_version"] == "sandbox_policy.v1"
    assert any(check["id"] == "runtime_kernel_ready" for check in payload["checks"])


def test_sandbox_doctor_fails_for_private_egress_and_forbidden_mount() -> None:
    payload = build_sandbox_doctor_payload(
        env={
            "KODA_MCP_ISOLATION": "docker",
            "KODA_MCP_NETWORK_MODE": "any",
            "KODA_MCP_MOUNTS": "/var/run/docker.sock:/docker.sock",
            "BROWSER_ALLOW_PRIVATE_NETWORK": "true",
        }
    )
    failed_ids = {check["id"] for check in payload["checks"] if check["status"] == "failed"}

    assert payload["status"] == "failed"
    assert "sandbox_forbidden_mount" in failed_ids
    assert "sandbox_private_egress" in failed_ids
    assert "browser_private_network" in failed_ids


def test_sandbox_doctor_degrades_when_runtime_kernel_missing() -> None:
    payload = build_sandbox_doctor_payload(
        env={
            "KODA_MCP_ISOLATION": "docker",
            "KODA_MCP_NETWORK_MODE": "egress_allowlist",
            "BROWSER_ALLOW_PRIVATE_NETWORK": "false",
        },
        runtime_kernel=None,
    )

    assert any(check["id"] == "runtime_kernel_unavailable" for check in payload["checks"])
    assert payload["status"] in {"degraded", "failed"}


def test_cli_sandbox_doctor_uses_auto_detect_when_isolation_is_absent() -> None:
    payload = build_cli_sandbox_doctor_payload(
        {
            "KODA_MCP_NETWORK_MODE": "egress_allowlist",
            "BROWSER_ALLOW_PRIVATE_NETWORK": "false",
        }
    )

    failed_ids = {check["id"] for check in payload["checks"] if check["status"] == "failed"}

    assert "sandbox_policy_unknown" not in failed_ids
    assert payload["status"] in {"passed", "degraded"}
