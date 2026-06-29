"""Sandbox doctor payloads for Phase 2 KG-06."""

from __future__ import annotations

import os
import platform
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from koda.config import AGENT_ID, BROWSER_ALLOW_PRIVATE_NETWORK
from koda.services.mcp_isolation import isolation_runtime_summary
from koda.services.sandbox_policy import (
    SandboxEffectivePolicy,
    SandboxPolicyCheck,
    SandboxPolicyEvaluation,
    evaluate_sandbox_effective_policy,
    normalize_isolation_kind,
    normalize_network_mode,
)

SANDBOX_DOCTOR_SCHEMA_VERSION = "sandbox_doctor.v1"
SANDBOX_POLICY_SCHEMA_VERSION = "sandbox_policy.v1"

SandboxDoctorStatus = Literal["passed", "warning", "failed", "degraded", "unavailable"]
SandboxDoctorSeverity = Literal["info", "warning", "danger"]


def build_sandbox_doctor_payload(
    *,
    agent_id: str | None = None,
    task_id: int | None = None,
    task: Mapping[str, Any] | None = None,
    environment: Mapping[str, Any] | None = None,
    runtime_kernel: Mapping[str, Any] | None = None,
    env: Mapping[str, Any] | None = None,
    mcp_risk_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the machine-readable `sandbox_doctor.v1` checklist."""

    resolved_agent_id = _string(agent_id or (task or {}).get("agent_id") or AGENT_ID).upper()
    resolved_task_id = _optional_int(task_id if task_id is not None else (task or {}).get("id"))
    env_values = env or os.environ
    policy = _effective_policy(
        agent_id=resolved_agent_id,
        task_id=resolved_task_id,
        task=task,
        environment=environment,
        env=env_values,
    )
    evaluation = evaluate_sandbox_effective_policy(policy)
    checks: list[dict[str, Any]] = [_policy_check_to_doctor(check) for check in evaluation.checks]
    checks.append(_runtime_kernel_check(runtime_kernel))
    checks.append(_mcp_isolation_check(env_values))
    checks.append(_browser_private_network_check(env_values))
    checks.append(_cgroup_check(env_values))
    checks.append(_mcp_risk_summary_check(mcp_risk_summary))

    status = _overall_status(checks)
    degraded_components = sorted(
        {
            str(check.get("scope") or "sandbox")
            for check in checks
            if str(check.get("status") or "") in {"warning", "failed", "degraded", "unavailable"}
        }
    )
    return {
        "doctor_version": SANDBOX_DOCTOR_SCHEMA_VERSION,
        "schema_version": SANDBOX_DOCTOR_SCHEMA_VERSION,
        "status": status,
        "generated_at": datetime.now(UTC).isoformat(),
        "agent_id": resolved_agent_id or None,
        "task_id": resolved_task_id,
        "effective_policy": _policy_payload(policy, evaluation),
        "checks": checks,
        "degraded_components": degraded_components,
        "warnings": [
            str(check.get("message") or check.get("title") or "")
            for check in checks
            if str(check.get("severity") or "") in {"warning", "danger"} and str(check.get("message") or "").strip()
        ],
    }


def build_cli_sandbox_doctor_payload(env: Mapping[str, Any]) -> dict[str, Any]:
    return build_sandbox_doctor_payload(env=env, runtime_kernel=None, mcp_risk_summary=None)


def _effective_policy(
    *,
    agent_id: str,
    task_id: int | None,
    task: Mapping[str, Any] | None,
    environment: Mapping[str, Any] | None,
    env: Mapping[str, Any],
) -> SandboxEffectivePolicy:
    isolation = (environment or {}).get("isolation")
    if not str(isolation or "").strip():
        isolation = env.get("KODA_MCP_ISOLATION")
    if not str(isolation or "").strip():
        isolation = env.get("SANDBOX_ISOLATION")
    if not str(isolation or "").strip():
        isolation = "auto"
    active_default = _active_default_isolation()
    if str(isolation).strip().lower() in {"", "auto"}:
        isolation = active_default
    network_mode = (
        env.get("KODA_MCP_NETWORK_MODE")
        or env.get("SANDBOX_NETWORK_MODE")
        or (environment or {}).get("network_mode")
        or "egress_allowlist"
    )
    egress_domains = _csv_tuple(env.get("KODA_MCP_EGRESS_DOMAINS") or env.get("SANDBOX_EGRESS_DOMAINS"))
    mounts = _mounts_from_env(env)
    allow_private_egress = _boolish(
        env.get("KODA_MCP_ALLOW_PRIVATE_EGRESS", env.get("BROWSER_ALLOW_PRIVATE_NETWORK", False))
    )
    channel_context = _channel_context(task=task, environment=environment, env=env)
    return SandboxEffectivePolicy.from_runtime(
        isolation_kind=normalize_isolation_kind(isolation),
        risk_class=(task or {}).get("risk_class") or env.get("KODA_MCP_RISK_CLASS") or "read_context",
        constraints={
            "network_mode": normalize_network_mode(network_mode),
            "egress_domains": egress_domains,
            "mounts": mounts,
        },
        env=_csv_tuple(env.get("KODA_MCP_ENV_KEYS") or env.get("SANDBOX_ENV_KEYS")),
        allow_private_egress=allow_private_egress,
        source="runtime" if task_id is not None else "doctor",
        channel_context=channel_context,
    )


def _policy_payload(policy: SandboxEffectivePolicy, evaluation: SandboxPolicyEvaluation) -> dict[str, Any]:
    payload = policy.to_payload()
    payload.update(
        {
            "policy_version": SANDBOX_POLICY_SCHEMA_VERSION,
            "schema_version": SANDBOX_POLICY_SCHEMA_VERSION,
            "decision": evaluation.decision,
            "allowed": evaluation.allowed,
            "scopes": ["filesystem", "network", "shell", "browser", "environment", "mount", "approval", "channel"],
            "read_only": policy.risk_class == "read_context",
            "shell_mode": "guarded" if policy.isolation_kind != "native" else "native",
            "browser_mode": "private_network_allowed" if policy.allow_private_egress else "restricted",
            "policy_ref": "docs/operations/sandbox-doctor-runbook.md",
        }
    )
    return payload


def _policy_check_to_doctor(check: SandboxPolicyCheck) -> dict[str, Any]:
    scope = "filesystem"
    if "remote" in check.check_id:
        scope = "channel"
    elif "env" in check.check_id:
        scope = "environment"
    elif "egress" in check.check_id:
        scope = "network"
    elif "mount" in check.check_id:
        scope = "mount"
    elif "native" in check.check_id or "policy" in check.check_id:
        scope = "shell"
    return {
        "id": check.check_id,
        "scope": scope,
        "title": _title(check.check_id),
        "severity": "info" if check.ok else "danger",
        "status": "passed" if check.ok else "failed",
        "message": check.reason,
        "user_action": "No action required." if check.ok else _policy_user_action(check.check_id),
        "evidence": check.details,
    }


def _runtime_kernel_check(runtime_kernel: Mapping[str, Any] | None) -> dict[str, Any]:
    if not runtime_kernel:
        return {
            "id": "runtime_kernel_unavailable",
            "scope": "shell",
            "title": "Runtime kernel",
            "severity": "warning",
            "status": "degraded",
            "message": "Runtime kernel health was not available to doctor.",
            "user_action": "Start the runtime kernel or run doctor from a live runtime.",
        }
    ready = bool(runtime_kernel.get("ready") or runtime_kernel.get("verified") or runtime_kernel.get("authoritative"))
    return {
        "id": "runtime_kernel_ready",
        "scope": "shell",
        "title": "Runtime kernel",
        "severity": "info" if ready else "warning",
        "status": "passed" if ready else "degraded",
        "message": "Runtime kernel is ready." if ready else "Runtime kernel is not ready or not authoritative.",
        "user_action": "No action required." if ready else "Inspect /api/runtime/readiness and runtime kernel logs.",
        "evidence": {
            "mode": runtime_kernel.get("mode"),
            "transport": runtime_kernel.get("transport"),
            "ready": runtime_kernel.get("ready"),
            "authoritative": runtime_kernel.get("authoritative"),
        },
    }


def _mcp_isolation_check(env: Mapping[str, Any]) -> dict[str, Any]:
    summary = isolation_runtime_summary()
    active_default = str(summary.get("active_default") or "native")
    requested = str(env.get("KODA_MCP_ISOLATION") or "auto")
    ok = active_default != "native" or requested.strip().lower() == "native-readonly"
    return {
        "id": "mcp_isolation_strategy",
        "scope": "shell",
        "title": "MCP isolation strategy",
        "severity": "info" if ok else "warning",
        "status": "passed" if ok else "degraded",
        "message": (
            f"MCP isolation default is {active_default}." if ok else "MCP isolation falls back to native execution."
        ),
        "user_action": (
            "No action required."
            if ok
            else "Install bubblewrap, enable sandbox-exec, or configure KODA_MCP_ISOLATION=docker for risky servers."
        ),
        "evidence": {"requested": requested, **summary},
    }


def _browser_private_network_check(env: Mapping[str, Any]) -> dict[str, Any]:
    allowed = _boolish(env.get("BROWSER_ALLOW_PRIVATE_NETWORK", BROWSER_ALLOW_PRIVATE_NETWORK))
    return {
        "id": "browser_private_network",
        "scope": "browser",
        "title": "Browser private network",
        "severity": "danger" if allowed else "info",
        "status": "failed" if allowed else "passed",
        "message": (
            "Browser private network access is enabled."
            if allowed
            else "Browser private network access is disabled by default."
        ),
        "user_action": (
            "Disable BROWSER_ALLOW_PRIVATE_NETWORK or document an explicit operator grant."
            if allowed
            else "No action required."
        ),
    }


def _cgroup_check(env: Mapping[str, Any]) -> dict[str, Any]:
    if platform.system() != "Linux":
        return {
            "id": "cgroup_platform",
            "scope": "ttl",
            "title": "Cgroup resource isolation",
            "severity": "info",
            "status": "passed",
            "message": "Cgroup enforcement is not required on this platform.",
            "user_action": "No action required.",
        }
    cgroup_root = Path(str(env.get("KODA_CGROUP_ROOT") or "/sys/fs/cgroup/koda"))
    ok = cgroup_root.exists() and os.access(str(cgroup_root), os.W_OK)
    return {
        "id": "cgroup_root_writable",
        "scope": "ttl",
        "title": "Cgroup resource isolation",
        "severity": "info" if ok else "warning",
        "status": "passed" if ok else "degraded",
        "message": "Cgroup root is writable." if ok else "Cgroup root is not writable for runtime limits.",
        "user_action": "No action required." if ok else "Create the cgroup root or disable hard resource limits.",
        "evidence": {"path": str(cgroup_root)},
    }


def _channel_context(
    *,
    task: Mapping[str, Any] | None,
    environment: Mapping[str, Any] | None,
    env: Mapping[str, Any],
) -> dict[str, Any]:
    task_payload = task or {}
    environment_payload = environment or {}
    return {
        "channel_type": (
            task_payload.get("channel_type")
            or environment_payload.get("channel_type")
            or env.get("KODA_CHANNEL_TYPE")
            or "local"
        ),
        "is_group": (
            task_payload.get("is_group")
            if "is_group" in task_payload
            else environment_payload.get("is_group", env.get("KODA_CHANNEL_IS_GROUP", False))
        ),
        "remote_session": (
            task_payload.get("remote_session")
            if "remote_session" in task_payload
            else environment_payload.get("remote_session", env.get("KODA_REMOTE_SESSION", False))
        ),
        "identity_status": (
            task_payload.get("identity_status")
            or environment_payload.get("identity_status")
            or env.get("KODA_CHANNEL_IDENTITY_STATUS")
            or "local"
        ),
        "explicit_remote_policy": (
            task_payload.get("explicit_remote_policy")
            if "explicit_remote_policy" in task_payload
            else environment_payload.get("explicit_remote_policy", env.get("KODA_EXPLICIT_REMOTE_POLICY", False))
        ),
    }


def _mcp_risk_summary_check(summary: Mapping[str, Any] | None) -> dict[str, Any]:
    unknown = int((summary or {}).get("unknown") or (summary or {}).get("unknown_risk") or 0)
    high = int((summary or {}).get("high_risk") or 0)
    ok = unknown == 0 and high == 0
    return {
        "id": "mcp_risk_summary",
        "scope": "approval",
        "title": "MCP risk taxonomy",
        "severity": "info" if ok else "warning",
        "status": "passed" if ok else "degraded",
        "message": (
            "No unknown or high-risk MCP tools were reported."
            if ok
            else "Unknown or high-risk MCP capabilities require approval-first execution."
        ),
        "user_action": (
            "No action required."
            if ok
            else "Review MCP tool risk metadata and grants before enabling unattended execution."
        ),
        "evidence": {"unknown": unknown, "high_risk": high},
    }


def _overall_status(checks: list[dict[str, Any]]) -> SandboxDoctorStatus:
    statuses = {str(check.get("status") or "") for check in checks}
    if "failed" in statuses:
        return "failed"
    if statuses & {"degraded", "warning", "unavailable"}:
        return "degraded"
    return "passed"


def _policy_user_action(check_id: str) -> str:
    if "remote_identity" in check_id:
        return "Approve the channel identity in the channel gateway before allowing remote execution."
    if "remote_unsafe" in check_id:
        return "Add an explicit remote policy for this channel context or retry from a local/dashboard session."
    if "mount" in check_id:
        return "Remove forbidden host mounts or make the mount read-only inside the runtime root."
    if "env" in check_id:
        return "Remove secret-bearing or process-hook environment keys from the sandbox policy."
    if "egress" in check_id:
        return "Use an allowlist and remove private-network targets unless an explicit grant exists."
    if "native" in check_id:
        return "Use bwrap, sandbox-exec, or Docker for high-risk MCP actions."
    return "Resolve the sandbox policy before starting the task."


def _active_default_isolation() -> str:
    try:
        return str(isolation_runtime_summary().get("active_default") or "unknown")
    except Exception:
        return "unknown"


def _mounts_from_env(env: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    raw = str(env.get("KODA_MCP_MOUNTS") or env.get("SANDBOX_MOUNTS") or "").strip()
    if not raw:
        return ()
    mounts: list[dict[str, Any]] = []
    for entry in raw.split(","):
        host, sep, container = entry.partition(":")
        if sep and host.strip() and container.strip():
            mounts.append({"host": host.strip(), "container": container.strip(), "read_only": True})
    return tuple(mounts)


def _csv_tuple(value: Any) -> tuple[str, ...]:
    raw = str(value or "").strip()
    if not raw:
        return ()
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _string(value: Any) -> str:
    return str(value or "").strip()


def _title(value: str) -> str:
    return " ".join(part.capitalize() for part in value.split("_") if part)
