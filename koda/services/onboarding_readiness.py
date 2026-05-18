"""Phase 6 onboarding readiness contract helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from koda.logging_config import get_logger

log = get_logger(__name__)

ONBOARDING_READINESS_SCHEMA_VERSION = "onboarding_readiness.v1"
ReadinessStatus = Literal["passed", "warning", "failed", "pending"]


@dataclass(frozen=True, slots=True)
class OnboardingReadinessError:
    code: str
    category: str
    message: str
    retryable: bool
    user_action: str
    detail_ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class OnboardingReadinessCheck:
    key: str
    title: str
    status: ReadinessStatus
    summary: str
    action_label: str = ""
    action_href: str = ""
    error: OnboardingReadinessError | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.error is not None:
            payload["error"] = self.error.to_dict()
        return payload


def build_onboarding_readiness(
    *,
    status: dict[str, Any],
    channel_gateway: dict[str, Any] | None = None,
    release_quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a versioned first-use readiness snapshot from existing health contracts."""

    providers = [dict(item) for item in status.get("providers") or [] if isinstance(item, dict)]
    agents = [dict(item) for item in status.get("agents") or [] if isinstance(item, dict)]
    storage = dict(status.get("storage") or {})
    steps = dict(status.get("steps") or {})
    primary_agent_id = str((agents[0] if agents else {}).get("id") or "")
    checks = [
        _provider_check(providers),
        _runtime_check(agents),
        _storage_check(storage),
        _sandbox_check(),
        _mcp_check(),
        _memory_check(),
        _channel_check(channel_gateway, steps),
        _first_task_check(release_quality),
        _first_trace_check(release_quality),
        _docs_check(),
        _release_quality_check(release_quality),
    ]
    status_value = _rollup_status(checks)
    payload = {
        "schema_version": ONBOARDING_READINESS_SCHEMA_VERSION,
        "status": status_value,
        "primary_agent_id": primary_agent_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "checks": [check.to_dict() for check in checks],
        "summary": {
            "passed": sum(1 for check in checks if check.status == "passed"),
            "warning": sum(1 for check in checks if check.status == "warning"),
            "failed": sum(1 for check in checks if check.status == "failed"),
            "pending": sum(1 for check in checks if check.status == "pending"),
        },
        "actions": _actions_for_checks(checks),
    }
    _emit_metrics(primary_agent_id or "default", checks)
    return payload


def _provider_check(providers: list[dict[str, Any]]) -> OnboardingReadinessCheck:
    verified = any(bool(item.get("verified")) for item in providers)
    configured = any(bool(item.get("configured")) for item in providers)
    if verified:
        return OnboardingReadinessCheck("provider", "Provider", "passed", "At least one provider is verified.")
    status: ReadinessStatus = "warning" if configured else "pending"
    return OnboardingReadinessCheck(
        "provider",
        "Provider",
        status,
        "No verified provider is available.",
        "Open model settings",
        "/control-plane/system/models",
        OnboardingReadinessError(
            code="onboarding.provider_not_verified",
            category="configuration",
            message="A provider must be verified before first-use work is reliable.",
            retryable=True,
            user_action="Open model settings and verify a provider connection.",
        ),
    )


def _runtime_check(agents: list[dict[str, Any]]) -> OnboardingReadinessCheck:
    active_agents = [item for item in agents if str(item.get("status") or "").lower() == "active"]
    token_ready = any(bool(item.get("telegram_token_configured")) for item in agents)
    if active_agents:
        return OnboardingReadinessCheck("runtime", "Runtime", "passed", "At least one active agent is available.")
    status: ReadinessStatus = "warning" if agents else "pending"
    return OnboardingReadinessCheck(
        "runtime",
        "Runtime",
        status,
        "No active agent runtime is available.",
        "Open agents",
        "/control-plane",
        metadata={"telegram_token_configured": token_ready},
    )


def _storage_check(storage: dict[str, Any]) -> OnboardingReadinessCheck:
    database = dict(storage.get("database") or {})
    object_storage = dict(storage.get("object_storage") or {})
    if database.get("ready") and object_storage.get("ready"):
        return OnboardingReadinessCheck("storage", "Storage", "passed", "Database and object storage are ready.")
    return OnboardingReadinessCheck(
        "storage",
        "Storage",
        "failed",
        "Storage readiness is incomplete.",
        "Run doctor",
        "/setup",
        OnboardingReadinessError(
            code="onboarding.storage_not_ready",
            category="dependency_unavailable",
            message="Database or object storage is not ready.",
            retryable=True,
            user_action="Run the setup doctor and fix the storage dependency.",
        ),
    )


def _sandbox_check() -> OnboardingReadinessCheck:
    return OnboardingReadinessCheck(
        "sandbox",
        "Sandbox",
        "warning",
        "Sandbox doctor should be reviewed before risky work.",
        "Open runtime doctor",
        "/runtime",
    )


def _mcp_check() -> OnboardingReadinessCheck:
    return OnboardingReadinessCheck(
        "mcp",
        "MCP",
        "warning",
        "MCP risk grants are optional for first use.",
        "Open integrations",
        "/control-plane/system/integrations",
    )


def _memory_check() -> OnboardingReadinessCheck:
    return OnboardingReadinessCheck(
        "memory",
        "Memory",
        "warning",
        "Memory and knowledge can be enabled after the first task.",
        "Open memory settings",
        "/control-plane/system/memory",
    )


def _channel_check(channel_gateway: dict[str, Any] | None, steps: dict[str, Any]) -> OnboardingReadinessCheck:
    if channel_gateway:
        summary = dict(channel_gateway.get("summary") or {})
        if int(summary.get("allowed") or 0) > 0:
            return OnboardingReadinessCheck(
                "channel", "Channel", "passed", "Telegram gateway has an approved identity."
            )
        if int(summary.get("pending") or 0) > 0:
            return OnboardingReadinessCheck(
                "channel",
                "Channel",
                "warning",
                "Telegram has pending unknown senders.",
                "Review senders",
                "/control-plane",
            )
    if steps.get("agent_ready"):
        return OnboardingReadinessCheck(
            "channel",
            "Channel",
            "pending",
            "Telegram is connected, but no gateway identity is approved yet.",
            "Pair Telegram",
            "/control-plane",
        )
    return OnboardingReadinessCheck(
        "channel", "Channel", "pending", "Telegram is not connected yet.", "Connect Telegram", "/control-plane"
    )


def _first_task_check(release_quality: dict[str, Any] | None) -> OnboardingReadinessCheck:
    if release_quality and release_quality.get("latest_eval_run"):
        return OnboardingReadinessCheck(
            "first_task", "First Task", "passed", "Execution evidence exists for this agent."
        )
    return OnboardingReadinessCheck(
        "first_task",
        "First Task",
        "pending",
        "Create a safe first task from the dashboard.",
        "Create first task",
        "/",
    )


def _first_trace_check(release_quality: dict[str, Any] | None) -> OnboardingReadinessCheck:
    if release_quality and str(release_quality.get("status") or "") == "passed":
        return OnboardingReadinessCheck(
            "first_trace", "First Trace", "passed", "Release quality has a passing trace gate."
        )
    return OnboardingReadinessCheck(
        "first_trace",
        "First Trace",
        "pending",
        "Open a task trace after the first execution completes.",
        "Open executions",
        "/executions",
    )


def _docs_check() -> OnboardingReadinessCheck:
    return OnboardingReadinessCheck(
        "docs",
        "Docs",
        "passed",
        "Phase 6 operator docs are versioned in the repository.",
        "Open docs",
        "/docs",
    )


def _release_quality_check(release_quality: dict[str, Any] | None) -> OnboardingReadinessCheck:
    if not release_quality:
        return OnboardingReadinessCheck(
            "release_quality",
            "Release Quality",
            "warning",
            "Release quality has not been checked for the primary agent.",
            "Open Evals",
            "/evaluations",
        )
    status = str(release_quality.get("status") or "failed")
    if status == "passed":
        return OnboardingReadinessCheck(
            "release_quality", "Release Quality", "passed", "Latest release-quality gate passed."
        )
    return OnboardingReadinessCheck(
        "release_quality",
        "Release Quality",
        "warning",
        "Latest release-quality gate is not passing.",
        "Open Evals",
        "/evaluations",
    )


def _rollup_status(checks: list[OnboardingReadinessCheck]) -> ReadinessStatus:
    if any(check.status == "failed" for check in checks):
        return "failed"
    if any(check.status == "pending" for check in checks):
        return "pending"
    if any(check.status == "warning" for check in checks):
        return "warning"
    return "passed"


def _actions_for_checks(checks: list[OnboardingReadinessCheck]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    for check in checks:
        if check.status == "passed" or not check.action_label:
            continue
        actions.append({"check": check.key, "label": check.action_label, "href": check.action_href})
    return actions


def _emit_metrics(agent_id: str, checks: list[OnboardingReadinessCheck]) -> None:
    try:
        from koda.services.metrics import ONBOARDING_READINESS_CHECKS

        for check in checks:
            ONBOARDING_READINESS_CHECKS.labels(agent_id=agent_id, check=check.key, status=check.status).inc()
    except Exception:
        log.debug("onboarding_readiness_metrics_skipped", exc_info=True)
