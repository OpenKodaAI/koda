"""Effective sandbox policy checks for MCP and tool execution gates."""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import urlparse

from koda.services.mcp_risk import HIGH_RISK_MCP_CLASSES, McpRiskClass, normalize_mcp_risk_class

SandboxIsolationKind = Literal["native", "bwrap", "sandbox-exec", "docker", "unknown"]
SandboxNetworkMode = Literal["none", "egress_allowlist", "any", "unknown"]
SandboxDecisionKind = Literal["allow", "deny"]
SandboxCheckSeverity = Literal["info", "warning", "error"]

SANDBOX_POLICY_SCHEMA_VERSION = "sandbox_policy.v1"

_ISOLATION_ALIASES: dict[str, SandboxIsolationKind] = {
    "native": "native",
    "none": "native",
    "passthrough": "native",
    "bwrap": "bwrap",
    "bubblewrap": "bwrap",
    "sandbox_exec": "sandbox-exec",
    "sandbox-exec": "sandbox-exec",
    "macos": "sandbox-exec",
    "docker": "docker",
}
_NETWORK_ALIASES: dict[str, SandboxNetworkMode] = {
    "none": "none",
    "off": "none",
    "disabled": "none",
    "egress_allowlist": "egress_allowlist",
    "allowlist": "egress_allowlist",
    "allow_list": "egress_allowlist",
    "restricted": "egress_allowlist",
    "any": "any",
    "all": "any",
    "bridge": "any",
}
_LOCAL_CHANNEL_TYPES: frozenset[str] = frozenset({"", "local", "dashboard", "runtime", "doctor", "cli"})
_ALLOWED_IDENTITY_STATUSES: frozenset[str] = frozenset({"local", "allowed"})
_REMOTE_UNSAFE_RISK_CLASSES: frozenset[McpRiskClass] = frozenset(
    {
        "low_risk_write",
        *HIGH_RISK_MCP_CLASSES,
    }
)
_FORBIDDEN_ENV_NAMES: frozenset[str] = frozenset(
    {
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "LD_AUDIT",
        "DYLD_INSERT_LIBRARIES",
        "DYLD_LIBRARY_PATH",
        "DYLD_FRAMEWORK_PATH",
        "PATH",
        "NODE_OPTIONS",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "BASH_ENV",
        "ENV",
        "GOPATH",
        "RUBYLIB",
        "RUBYOPT",
    }
)
_FORBIDDEN_MOUNT_ROOTS: tuple[str, ...] = (
    "/",
    "/dev",
    "/etc",
    "/proc",
    "/root",
    "/sys",
)
_FORBIDDEN_MOUNT_EXACT: tuple[str, ...] = (
    "/var/run/docker.sock",
    "/run/docker.sock",
)
_FORBIDDEN_MOUNT_PARTS: frozenset[str] = frozenset(
    {
        ".aws",
        ".azure",
        ".config/gcloud",
        ".docker",
        ".gnupg",
        ".kube",
        ".ssh",
    }
)


class SandboxPolicyDenied(ValueError):
    """Raised when an effective sandbox policy is not safe to execute."""


@dataclass(frozen=True, slots=True)
class SandboxMount:
    """One normalized sandbox mount."""

    host: str
    container: str
    read_only: bool = True

    def to_payload(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "container": self.container,
            "read_only": self.read_only,
        }


@dataclass(frozen=True, slots=True)
class SandboxEffectivePolicy:
    """Normalized effective policy evaluated immediately before execution."""

    isolation_kind: SandboxIsolationKind = "unknown"
    risk_class: McpRiskClass = "unknown"
    network_mode: SandboxNetworkMode = "unknown"
    egress_domains: tuple[str, ...] = ()
    mounts: tuple[SandboxMount, ...] = ()
    env_keys: tuple[str, ...] = ()
    allow_private_egress: bool = False
    source: str = "runtime"
    channel_type: str = "local"
    is_group: bool = False
    remote_session: bool = False
    identity_status: str = "local"
    explicit_remote_policy: bool = False

    def __post_init__(self) -> None:
        channel_type = normalize_channel_type(self.channel_type)
        object.__setattr__(self, "channel_type", channel_type)
        object.__setattr__(self, "identity_status", normalize_identity_status(self.identity_status))
        object.__setattr__(self, "remote_session", _is_remote_session(channel_type, self.is_group, self.remote_session))

    @classmethod
    def from_runtime(
        cls,
        *,
        isolation_kind: Any,
        risk_class: Any,
        constraints: Any | None = None,
        env: Mapping[str, Any] | Iterable[str] | None = None,
        allow_private_egress: bool = False,
        source: str = "runtime",
        channel_type: Any = "local",
        is_group: Any = False,
        remote_session: Any = False,
        identity_status: Any = "local",
        explicit_remote_policy: Any = False,
        channel_context: Mapping[str, Any] | None = None,
    ) -> SandboxEffectivePolicy:
        """Build a policy from runtime isolation constraints without storing env values."""

        channel_context = channel_context or {}
        return cls(
            isolation_kind=normalize_isolation_kind(isolation_kind),
            risk_class=normalize_mcp_risk_class(risk_class),
            network_mode=normalize_network_mode(_constraint_value(constraints, "network_mode", "unknown")),
            egress_domains=_string_tuple(_constraint_value(constraints, "egress_domains", ())),
            mounts=_mount_tuple(_constraint_value(constraints, "mounts", ())),
            env_keys=_env_key_tuple(env),
            allow_private_egress=bool(allow_private_egress),
            source=str(source or "runtime"),
            channel_type=channel_context.get("channel_type", channel_type),
            is_group=_boolish(channel_context.get("is_group", is_group)),
            remote_session=_boolish(channel_context.get("remote_session", remote_session)),
            identity_status=channel_context.get("identity_status", identity_status),
            explicit_remote_policy=_boolish(channel_context.get("explicit_remote_policy", explicit_remote_policy)),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "policy_version": SANDBOX_POLICY_SCHEMA_VERSION,
            "isolation_kind": self.isolation_kind,
            "risk_class": self.risk_class,
            "network_mode": self.network_mode,
            "egress_domains": list(self.egress_domains),
            "mounts": [mount.to_payload() for mount in self.mounts],
            "env_keys": list(self.env_keys),
            "allow_private_egress": self.allow_private_egress,
            "source": self.source,
            "channel_type": self.channel_type,
            "is_group": self.is_group,
            "remote_session": self.remote_session,
            "identity_status": self.identity_status,
            "explicit_remote_policy": self.explicit_remote_policy,
        }


@dataclass(frozen=True, slots=True)
class SandboxPolicyCheck:
    """One effective-policy check result."""

    check_id: str
    ok: bool
    reason: str
    severity: SandboxCheckSeverity = "error"
    details: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "ok": self.ok,
            "reason": self.reason,
            "severity": self.severity,
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class SandboxPolicyEvaluation:
    """Deny-before-execute result for a sandbox effective policy."""

    decision: SandboxDecisionKind
    policy: SandboxEffectivePolicy
    checks: tuple[SandboxPolicyCheck, ...]

    @property
    def allowed(self) -> bool:
        return self.decision == "allow"

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return tuple(check.check_id for check in self.checks if not check.ok)

    def to_payload(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "allowed": self.allowed,
            "reason_codes": list(self.reason_codes),
            "policy": self.policy.to_payload(),
            "checks": [check.to_payload() for check in self.checks],
        }


def normalize_isolation_kind(value: Any) -> SandboxIsolationKind:
    normalized = str(value or "").strip().lower().replace("_", "-")
    return _ISOLATION_ALIASES.get(normalized, "unknown")


def normalize_network_mode(value: Any) -> SandboxNetworkMode:
    normalized = str(value or "").strip().lower().replace("-", "_")
    return _NETWORK_ALIASES.get(normalized, "unknown")


def normalize_channel_type(value: Any) -> str:
    return str(value or "local").strip().lower().replace(" ", "_") or "local"


def normalize_identity_status(value: Any) -> str:
    return str(value or "unknown").strip().lower().replace(" ", "_") or "unknown"


def evaluate_sandbox_effective_policy(policy: SandboxEffectivePolicy) -> SandboxPolicyEvaluation:
    """Evaluate effective sandbox posture and deny unsafe execution."""

    checks = (
        _check_known_policy(policy),
        _check_remote_channel_identity(policy),
        _check_remote_unsafe_default(policy),
        _check_forbidden_mounts(policy),
        _check_forbidden_env(policy),
        _check_private_egress(policy),
        _check_native_high_risk(policy),
    )
    decision: SandboxDecisionKind = "allow" if all(check.ok for check in checks) else "deny"
    return SandboxPolicyEvaluation(decision=decision, policy=policy, checks=checks)


def sandbox_policy_allows_execution(policy: SandboxEffectivePolicy) -> bool:
    return evaluate_sandbox_effective_policy(policy).allowed


def ensure_sandbox_policy_allows_execution(policy: SandboxEffectivePolicy) -> SandboxPolicyEvaluation:
    evaluation = evaluate_sandbox_effective_policy(policy)
    if not evaluation.allowed:
        raise SandboxPolicyDenied(", ".join(evaluation.reason_codes))
    return evaluation


def _check_known_policy(policy: SandboxEffectivePolicy) -> SandboxPolicyCheck:
    failures: list[str] = []
    if policy.isolation_kind == "unknown":
        failures.append("isolation_kind")
    if policy.network_mode == "unknown":
        failures.append("network_mode")
    if failures:
        return SandboxPolicyCheck(
            check_id="sandbox_policy_unknown",
            ok=False,
            reason="Sandbox policy contains unknown normalized fields.",
            details={"fields": failures},
        )
    return SandboxPolicyCheck(
        check_id="sandbox_policy_known",
        ok=True,
        reason="Sandbox isolation and network mode are known.",
        severity="info",
    )


def _check_remote_channel_identity(policy: SandboxEffectivePolicy) -> SandboxPolicyCheck:
    if policy.remote_session and policy.identity_status not in _ALLOWED_IDENTITY_STATUSES:
        return SandboxPolicyCheck(
            check_id="sandbox_remote_identity_untrusted",
            ok=False,
            reason="Remote channel identity is not explicitly allowed.",
            details={
                "channel_type": policy.channel_type,
                "is_group": policy.is_group,
                "remote_session": policy.remote_session,
                "identity_status": policy.identity_status,
            },
        )
    return SandboxPolicyCheck(
        check_id="sandbox_remote_identity_trusted",
        ok=True,
        reason="Channel identity is trusted for this sandbox context.",
        severity="info",
        details={
            "channel_type": policy.channel_type,
            "is_group": policy.is_group,
            "remote_session": policy.remote_session,
            "identity_status": policy.identity_status,
        },
    )


def _check_remote_unsafe_default(policy: SandboxEffectivePolicy) -> SandboxPolicyCheck:
    unsafe_remote_action = policy.remote_session and policy.risk_class in _REMOTE_UNSAFE_RISK_CLASSES
    if unsafe_remote_action and not policy.explicit_remote_policy:
        return SandboxPolicyCheck(
            check_id="sandbox_remote_unsafe_default",
            ok=False,
            reason="Remote or group sessions require explicit policy before unsafe tool execution.",
            details={
                "channel_type": policy.channel_type,
                "is_group": policy.is_group,
                "remote_session": policy.remote_session,
                "risk_class": policy.risk_class,
                "explicit_remote_policy": policy.explicit_remote_policy,
            },
        )
    return SandboxPolicyCheck(
        check_id="sandbox_remote_unsafe_default",
        ok=True,
        reason="Remote session default is compatible with this risk class.",
        severity="info",
        details={
            "channel_type": policy.channel_type,
            "is_group": policy.is_group,
            "remote_session": policy.remote_session,
            "risk_class": policy.risk_class,
            "explicit_remote_policy": policy.explicit_remote_policy,
        },
    )


def _check_forbidden_mounts(policy: SandboxEffectivePolicy) -> SandboxPolicyCheck:
    forbidden = [mount.to_payload() for mount in policy.mounts if _is_forbidden_mount(mount.host)]
    if forbidden:
        return SandboxPolicyCheck(
            check_id="sandbox_forbidden_mount",
            ok=False,
            reason="Sandbox policy includes a forbidden host mount.",
            details={"mounts": forbidden},
        )
    return SandboxPolicyCheck(
        check_id="sandbox_forbidden_mount",
        ok=True,
        reason="No forbidden host mounts requested.",
        severity="info",
    )


def _check_forbidden_env(policy: SandboxEffectivePolicy) -> SandboxPolicyCheck:
    forbidden = sorted(key for key in policy.env_keys if _is_forbidden_env_key(key))
    if forbidden:
        return SandboxPolicyCheck(
            check_id="sandbox_forbidden_env",
            ok=False,
            reason="Sandbox policy includes forbidden environment variables.",
            details={"env_keys": forbidden},
        )
    return SandboxPolicyCheck(
        check_id="sandbox_forbidden_env",
        ok=True,
        reason="No forbidden environment variables requested.",
        severity="info",
    )


def _check_private_egress(policy: SandboxEffectivePolicy) -> SandboxPolicyCheck:
    private_domains = [domain for domain in policy.egress_domains if _is_private_egress_target(domain)]
    private_egress_possible = policy.network_mode == "any" or policy.allow_private_egress or bool(private_domains)
    if private_egress_possible:
        return SandboxPolicyCheck(
            check_id="sandbox_private_egress",
            ok=False,
            reason="Sandbox policy permits private-network egress.",
            details={
                "network_mode": policy.network_mode,
                "allow_private_egress": policy.allow_private_egress,
                "private_targets": private_domains,
            },
        )
    return SandboxPolicyCheck(
        check_id="sandbox_private_egress",
        ok=True,
        reason="Private-network egress is not permitted.",
        severity="info",
    )


def _check_native_high_risk(policy: SandboxEffectivePolicy) -> SandboxPolicyCheck:
    if policy.isolation_kind == "native" and policy.risk_class in HIGH_RISK_MCP_CLASSES:
        return SandboxPolicyCheck(
            check_id="sandbox_native_high_risk",
            ok=False,
            reason="Native isolation is not allowed for high-risk or unknown MCP actions.",
            details={"isolation_kind": policy.isolation_kind, "risk_class": policy.risk_class},
        )
    return SandboxPolicyCheck(
        check_id="sandbox_native_high_risk",
        ok=True,
        reason="Isolation kind is acceptable for this risk class.",
        severity="info",
    )


def _constraint_value(constraints: Any | None, key: str, default: Any) -> Any:
    if constraints is None:
        return default
    if isinstance(constraints, Mapping):
        return constraints.get(key, default)
    return getattr(constraints, key, default)


def _is_remote_session(channel_type: str, is_group: bool, remote_session: Any) -> bool:
    return _boolish(remote_session) or bool(is_group) or channel_type not in _LOCAL_CHANNEL_TYPES


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on", "allowed", "enabled"}


def _mount_tuple(value: Any) -> tuple[SandboxMount, ...]:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes, Mapping)):
        return ()
    mounts: list[SandboxMount] = []
    for item in value:
        if isinstance(item, SandboxMount):
            mounts.append(item)
        elif isinstance(item, Mapping):
            host = str(item.get("host") or "")
            container = str(item.get("container") or item.get("target") or "")
            if host and container:
                mounts.append(SandboxMount(host=host, container=container, read_only=bool(item.get("read_only", True))))
        else:
            host = str(getattr(item, "host", "") or "")
            container = str(getattr(item, "container", "") or "")
            if host and container:
                mounts.append(
                    SandboxMount(
                        host=host,
                        container=container,
                        read_only=bool(getattr(item, "read_only", True)),
                    )
                )
    return tuple(mounts)


def _env_key_tuple(env: Mapping[str, Any] | Iterable[str] | None) -> tuple[str, ...]:
    if env is None:
        return ()
    values: Iterable[Any]
    if isinstance(env, Mapping):
        values = env.keys()
    else:
        values = env
    return tuple(sorted({str(value).strip() for value in values if str(value).strip()}))


def _string_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if not isinstance(value, Iterable):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _is_forbidden_env_key(key: str) -> bool:
    normalized = str(key or "").strip().upper()
    return normalized in _FORBIDDEN_ENV_NAMES or normalized.startswith("KODA_")


def _is_forbidden_mount(host: str) -> bool:
    normalized = _normalize_path(host)
    if not normalized:
        return True
    if normalized in _FORBIDDEN_MOUNT_EXACT:
        return True
    for root in _FORBIDDEN_MOUNT_ROOTS:
        if root == "/":
            if normalized == root:
                return True
            continue
        if normalized == root or normalized.startswith(root.rstrip("/") + "/"):
            return True
    parts = set(Path(normalized).parts)
    if parts & _FORBIDDEN_MOUNT_PARTS:
        return True
    return any(part in normalized for part in _FORBIDDEN_MOUNT_PARTS if "/" in part)


def _normalize_path(path: str) -> str:
    value = str(path or "").strip()
    if not value:
        return ""
    expanded = os.path.expanduser(value)
    normalized = os.path.normpath(expanded)
    if not normalized.startswith("/"):
        normalized = os.path.normpath(str(Path.cwd() / normalized))
    return normalized


def _is_private_egress_target(value: str) -> bool:
    host = _host_from_target(value)
    if not host:
        return True
    lowered = host.lower().strip("[]")
    if lowered in {"localhost", "ip6-localhost"}:
        return True
    if lowered.endswith((".local", ".localhost", ".internal")):
        return True
    try:
        ip = ipaddress.ip_address(lowered)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified


def _host_from_target(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"//{raw}")
    host = parsed.hostname or raw.split("/", 1)[0].split(":", 1)[0]
    return cast(str, host or "")
