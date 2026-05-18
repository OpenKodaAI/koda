"""Focused tests for sandbox effective policy evaluation."""

from __future__ import annotations

import pytest

from koda.services.mcp_isolation import IsolationConstraints, Mount
from koda.services.sandbox_policy import (
    SANDBOX_POLICY_SCHEMA_VERSION,
    SandboxEffectivePolicy,
    SandboxMount,
    SandboxPolicyDenied,
    ensure_sandbox_policy_allows_execution,
    evaluate_sandbox_effective_policy,
)


def test_safe_read_policy_allows_execution() -> None:
    policy = SandboxEffectivePolicy(
        isolation_kind="bwrap",
        risk_class="read_context",
        network_mode="egress_allowlist",
        egress_domains=("api.github.com",),
        mounts=(SandboxMount(host="/tmp/koda-work", container="/workspace"),),
        env_keys=("GITHUB_TOKEN",),
    )

    evaluation = evaluate_sandbox_effective_policy(policy)

    assert evaluation.allowed is True
    assert evaluation.reason_codes == ()
    assert policy.to_payload()["policy_version"] == SANDBOX_POLICY_SCHEMA_VERSION


def test_forbidden_mount_denies_execution() -> None:
    policy = SandboxEffectivePolicy(
        isolation_kind="docker",
        risk_class="read_context",
        network_mode="none",
        mounts=(SandboxMount(host="/var/run/docker.sock", container="/docker.sock"),),
    )

    evaluation = evaluate_sandbox_effective_policy(policy)

    assert evaluation.allowed is False
    assert "sandbox_forbidden_mount" in evaluation.reason_codes


def test_forbidden_env_denies_execution_without_storing_values() -> None:
    policy = SandboxEffectivePolicy.from_runtime(
        isolation_kind="bwrap",
        risk_class="read_context",
        constraints={"network_mode": "none"},
        env={"LD_PRELOAD": "/tmp/hook.so", "OK_TOKEN": "redacted"},
    )

    evaluation = evaluate_sandbox_effective_policy(policy)

    assert evaluation.allowed is False
    assert "sandbox_forbidden_env" in evaluation.reason_codes
    assert policy.to_payload()["env_keys"] == ["LD_PRELOAD", "OK_TOKEN"]


def test_private_egress_domain_denies_execution() -> None:
    policy = SandboxEffectivePolicy(
        isolation_kind="docker",
        risk_class="network_write",
        network_mode="egress_allowlist",
        egress_domains=("127.0.0.1:5432", "api.example.com"),
    )

    evaluation = evaluate_sandbox_effective_policy(policy)

    assert evaluation.allowed is False
    assert "sandbox_private_egress" in evaluation.reason_codes


def test_network_any_denies_as_private_egress_possible() -> None:
    policy = SandboxEffectivePolicy(
        isolation_kind="docker",
        risk_class="read_context",
        network_mode="any",
    )

    evaluation = evaluate_sandbox_effective_policy(policy)

    assert evaluation.allowed is False
    assert "sandbox_private_egress" in evaluation.reason_codes


def test_native_isolation_denies_high_risk_mcp_action() -> None:
    policy = SandboxEffectivePolicy(
        isolation_kind="native",
        risk_class="code_execution",
        network_mode="none",
    )

    evaluation = evaluate_sandbox_effective_policy(policy)

    assert evaluation.allowed is False
    assert "sandbox_native_high_risk" in evaluation.reason_codes


def test_unknown_policy_fields_fail_closed() -> None:
    policy = SandboxEffectivePolicy.from_runtime(
        isolation_kind="unexpected-runtime",
        risk_class="read_context",
        constraints={"network_mode": "mystery"},
    )

    evaluation = evaluate_sandbox_effective_policy(policy)

    assert evaluation.allowed is False
    assert "sandbox_policy_unknown" in evaluation.reason_codes


def test_from_runtime_accepts_existing_isolation_constraints() -> None:
    constraints = IsolationConstraints(
        network_mode="egress_allowlist",
        egress_domains=("api.example.com",),
        mounts=(Mount(host="/tmp/project", container="/workspace"),),
    )

    policy = SandboxEffectivePolicy.from_runtime(
        isolation_kind="sandbox-exec",
        risk_class="low_risk_write",
        constraints=constraints,
        env=["SAFE_TOKEN"],
    )

    assert policy.isolation_kind == "sandbox-exec"
    assert policy.network_mode == "egress_allowlist"
    assert policy.mounts == (SandboxMount(host="/tmp/project", container="/workspace"),)
    assert evaluate_sandbox_effective_policy(policy).allowed is True


def test_ensure_sandbox_policy_allows_execution_raises_on_denied() -> None:
    policy = SandboxEffectivePolicy(
        isolation_kind="native",
        risk_class="secret_access",
        network_mode="none",
    )

    with pytest.raises(SandboxPolicyDenied, match="sandbox_native_high_risk"):
        ensure_sandbox_policy_allows_execution(policy)
