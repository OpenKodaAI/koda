"""Agent tool dispatcher: parses <agent_cmd> tags, executes tools, and formats results."""

import asyncio
import contextlib
import json
import re
import time as _time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

from koda.agent_contract import (
    evaluate_integration_grant,
    resolve_integration_action,
)
from koda.config import (
    AGENT_RESOURCE_ACCESS_POLICY,
    AGENT_TOOL_TIMEOUT,
    ALLOWED_GIT_CMDS,
    BROWSER_FEATURES_ENABLED,
    BROWSER_TOOL_TIMEOUT,
    FILEOPS_BLOCKED_EXTENSIONS,
    FILEOPS_ENABLED,
    FILEOPS_MAX_READ_SIZE,
    GIT_ENABLED,
    GIT_META_CHARS,
    INTER_AGENT_ENABLED,
    PLUGIN_SYSTEM_ENABLED,
    SHELL_ENABLED,
    SHELL_TIMEOUT,
    SNAPSHOT_ENABLED,
    STRUCTURED_DATA_OUTPUT_ENABLED,
    WEBHOOK_ENABLED,
    WORKFLOW_ENABLED,
)
from koda.knowledge.types import EffectiveExecutionPolicy
from koda.logging_config import get_logger
from koda.services import blocked_patterns as _blocked_patterns_module
from koda.services.execution_policy import PolicyEvaluation, evaluate_execution_policy
from koda.utils.workdir import validate_work_dir

log = get_logger(__name__)


def _audit_blocked(tool: str, reason: str, user_id: int | None = None) -> None:
    from koda.services.audit import emit_security

    emit_security("security.command_blocked", user_id=user_id, tool=tool, reason=reason)


def _browser_scope_id(ctx: "ToolContext") -> int:
    """Prefer task-scoped browser sessions when available."""
    return ctx.task_id if ctx.task_id is not None else ctx.user_id


def _coerce_bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def _coerce_int(value: object) -> int:
    if value is None:
        raise ValueError("value is required")
    return int(str(value))


_AGENT_CMD_RE = re.compile(r'<agent_cmd\s+tool="([^"]+)">(.*?)</agent_cmd>', re.DOTALL)
_ACTION_PLAN_RE = re.compile(r"<action_plan>.*?</action_plan>", re.DOTALL | re.IGNORECASE)

# Native-fast block-pattern matchers. Sourced
# from the central :mod:`koda.services.blocked_patterns` registry so
# every site of the runtime — handlers, cli_runner, dispatcher — uses
# the same compiled guard. Building once at module load: when the
# ``koda_command_guard`` wheel is installed the matcher is a Rust DFA
# (linear time, no GIL); otherwise it falls back to Python re.compile.
# A grep gate in ``tests/test_open_source_hygiene.py`` enforces that
# no caller bypasses the registry by using ``BLOCKED_*_PATTERN.search``
# directly. The ``noqa: E402`` here keeps the comment block above the
# import so the rationale is co-located with the wire-up site.
_BLOCKED_SHELL = _blocked_patterns_module.SHELL_GUARD

# Tools that modify state (require approval in supervised mode)
_WRITE_TOOLS = frozenset(
    {
        "job_create",
        "job_update",
        "job_validate",
        "job_activate",
        "job_pause",
        "job_resume",
        "job_delete",
        "job_run_now",
        "agent_set_workdir",
        "browser_click",
        "browser_type",
        "browser_submit",
        "browser_select",
        "browser_hover",
        "browser_press_key",
        "browser_network_capture_start",
        "browser_network_capture_stop",
        "browser_network_mock",
        "browser_session_save",
        "browser_session_restore",
        "browser_tab_open",
        "browser_tab_close",
        "browser_tab_switch",
        "browser_execute_js",
        "browser_download",
        "browser_upload",
        "browser_set_viewport",
        "script_save",
        "script_delete",
        "cache_clear",
        "snapshot_save",
        "snapshot_delete",
        "webhook_register",
        "webhook_unregister",
        "file_write",
        "file_edit",
        "file_delete",
        "file_move",
        "image_generate",
        "shell_execute",
        "shell_bg",
        "shell_kill",
        "git_commit",
        "git_branch",
        "git_checkout",
        "git_push",
        "git_pull",
        "plugin_install",
        "plugin_uninstall",
        "plugin_reload",
        "workflow_create",
        "workflow_run",
        "workflow_delete",
        "agent_send",
        "task",
        "agent_delegate",
        "agent_broadcast",
        "squad_reply",
        "squad_request_input",
        "squad_follow_up",
        "squad_synthesize",
    }
)

# Tools that are always read-only
_READ_TOOLS = frozenset(
    {
        "job_list",
        "job_get",
        "job_runs",
        "web_search",
        "fetch_url",
        "agent_get_status",
        "browser_navigate",
        "browser_screenshot",
        "browser_get_text",
        "browser_get_elements",
        "browser_scroll",
        "browser_wait",
        "browser_back",
        "browser_forward",
        "browser_network_requests",
        "browser_session_list",
        "browser_tab_list",
        "browser_tab_compare",
        "browser_pdf",
        "script_search",
        "script_list",
        "cache_stats",
        "snapshot_restore",
        "snapshot_list",
        "snapshot_diff",
        "webhook_list",
        "event_wait",
        "request_skill",
        "file_read",
        "file_list",
        "file_search",
        "file_grep",
        "file_info",
        "shell_status",
        "shell_output",
        "git_status",
        "git_diff",
        "git_log",
        "plugin_list",
        "plugin_info",
        "workflow_list",
        "workflow_get",
        "agent_receive",
        "agent_list_agents",
    }
)

# Mutable sets for dynamically registered MCP tools (populated by mcp_bootstrap / mcp_bridge)
_MCP_WRITE_TOOLS: set[str] = set()
_MCP_READ_TOOLS: set[str] = set()

# Per-user tool execution rate limiter (sliding window).
# Uses deque for O(1) popleft. Safe in single-event-loop asyncio (no preemptive
# interleaving between await points within this synchronous function).
_tool_rate_windows: dict[str, deque[float]] = defaultdict(deque)
_TOOL_RATE_WINDOW_SECONDS = 60.0


def _check_tool_rate_limit(user_id: int | None, agent_id: str) -> str | None:
    """Return an error message if rate limit exceeded, else None."""
    from koda.config import TOOL_RATE_LIMIT_PER_MINUTE

    if TOOL_RATE_LIMIT_PER_MINUTE <= 0:
        return None
    key = f"{user_id or 0}:{agent_id}"
    now = _time.monotonic()
    window = _tool_rate_windows[key]
    # Evict entries older than the window (O(1) per pop with deque)
    cutoff = now - _TOOL_RATE_WINDOW_SECONDS
    while window and window[0] < cutoff:
        window.popleft()
    if len(window) >= TOOL_RATE_LIMIT_PER_MINUTE:
        return (
            f"Tool execution rate limit exceeded ({TOOL_RATE_LIMIT_PER_MINUTE}/min). "
            "Please wait before executing more tools."
        )
    window.append(now)
    return None


def _configured_resource_access_policy() -> dict[str, object]:
    return dict(AGENT_RESOURCE_ACCESS_POLICY) if AGENT_RESOURCE_ACCESS_POLICY else {}


def is_known_tool(tool_id: str) -> bool:
    if tool_id in _TOOL_HANDLERS:
        return True
    if tool_id.startswith("mcp_"):
        return True
    if PLUGIN_SYSTEM_ENABLED:
        try:
            from koda.plugins import get_registry

            return get_registry().get_handler(tool_id) is not None
        except Exception:
            return False
    return False


@dataclass
class AgentToolCall:
    tool: str
    params: dict
    raw_match: str


@dataclass
class AgentToolResult:
    tool: str
    success: bool
    output: str
    metadata: dict = field(default_factory=dict)
    data: dict | list | None = None
    data_format: str | None = None
    duration_ms: float | None = None
    started_at: str | None = None
    completed_at: str | None = None


@dataclass
class ToolContext:
    user_id: int
    chat_id: int
    work_dir: str
    user_data: dict
    agent: object
    agent_mode: str
    task_id: int | None = None
    dry_run: bool = False
    scheduled_job_id: int | None = None
    scheduled_run_id: int | None = None
    task_kind: str = "general"
    effective_policy: EffectiveExecutionPolicy | None = None
    executing_agent_id: str | None = None
    squad_thread_id: str | None = None
    squad_task_id: str | None = None
    parent_message_id: str | None = None
    delegation_chain: list[str] = field(default_factory=list)
    delegation_request_id: str | None = None
    delegation_origin_agent_id: str | None = None
    bot: Any | None = None
    application: Any | None = None
    context_governance: dict[str, Any] | None = None
    source_root_path: str | None = None
    runtime_workspace_path: str | None = None


def parse_agent_commands(text: str) -> tuple[list[AgentToolCall], str]:
    """Parse <agent_cmd> tags from text. Returns (calls, clean_text)."""
    calls: list[AgentToolCall] = []
    clean = text

    for match in _AGENT_CMD_RE.finditer(text):
        tool = match.group(1).strip()
        body = match.group(2).strip()
        try:
            params = json.loads(body) if body else {}
        except (json.JSONDecodeError, ValueError):
            log.warning("agent_cmd_invalid_json", tool=tool, body=body[:200])
            continue
        calls.append(AgentToolCall(tool=tool, params=params, raw_match=match.group(0)))

    for call in calls:
        clean = clean.replace(call.raw_match, "")

    clean = _ACTION_PLAN_RE.sub("", clean)

    # Collapse excessive whitespace from removed tags
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    return calls, clean


def _infer_tool_category(tool: str) -> str:
    if tool.startswith("mcp_"):
        return "mcp"
    if tool.startswith("file_"):
        return "fileops"
    if tool.startswith("db_"):
        return "db"
    if tool.startswith("browser_"):
        return "browser"
    if tool.startswith("image_"):
        return "image"
    if tool.startswith("job_"):
        return "ops"
    if tool.startswith("shell_"):
        return "shell"
    if tool.startswith("git_"):
        return "git"
    if tool.startswith("plugin_"):
        return "plugin"
    if tool.startswith("workflow_"):
        return "workflow"
    if tool.startswith("snapshot_"):
        return "snapshots"
    if tool == "task":
        return "agent_comm"
    if tool in {"agent_send", "agent_receive", "agent_delegate", "agent_list_agents", "agent_broadcast"}:
        return "agent_comm"
    if tool.startswith("squad_"):
        return "agent_comm"
    return "tool"


def _integration_policy_error(decision_reason: str) -> str:
    mapping = {
        "integration_disabled": "Blocked by integration policy: this integration is disabled for the agent.",
        "action_denied": "Blocked by integration policy: this action is explicitly denied.",
        "action_not_granted": "Blocked by integration policy: this action is outside the granted scope.",
        "read_only_policy": "Blocked by integration policy: only read actions are allowed.",
        "domain_unknown": "Blocked by integration policy: the active browser domain could not be resolved.",
        "domain_not_granted": "Blocked by integration policy: the target domain is outside the granted scope.",
        "private_network_not_granted": (
            "Blocked by integration policy: private network access requires an explicit grant."
        ),
        "db_env_not_granted": "Blocked by integration policy: this database environment is outside the granted scope.",
        "path_not_granted": "Blocked by integration policy: this filesystem path is outside the granted scope.",
    }
    return mapping.get(decision_reason, "Blocked by integration policy.")


def _record_integration_grant_audit(
    *,
    agent_id: str,
    decision: object,
    params: dict[str, object],
) -> None:
    try:
        from koda.control_plane.database import execute, json_dump, now_iso
    except Exception:
        return
    payload = {
        "integration_id": getattr(decision, "integration_id", ""),
        "action_id": getattr(decision, "action_id", ""),
        "allowed": bool(getattr(decision, "allowed", False)),
        "access_level": getattr(decision, "access_level", ""),
        "transport": getattr(decision, "transport", ""),
        "risk_class": getattr(decision, "risk_class", ""),
        "default_approval_mode": getattr(decision, "default_approval_mode", ""),
        "auth_mode": getattr(decision, "auth_mode", ""),
        "reason": getattr(decision, "reason", ""),
        "sensitive_access_used": bool(getattr(decision, "sensitive_access_used", False)),
    }
    try:
        execute(
            """
            INSERT INTO cp_integration_grant_audit (
                agent_id, integration_id, action_id, grant_decision, details_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                agent_id,
                str(payload.get("integration_id") or ""),
                str(payload.get("action_id") or ""),
                "allowed" if bool(payload.get("allowed")) else "denied",
                json_dump(
                    {
                        "params": params,
                        "decision": payload,
                    }
                ),
                now_iso(),
            ),
        )
    except Exception:
        return


def _looks_like_runtime_auth_or_config_error(text: str) -> bool:
    normalized = text.lower()
    return any(
        token in normalized
        for token in (
            "missing",
            "credential",
            "credentials",
            "auth",
            "authentication",
            "unauthorized",
            "forbidden",
            "permission denied",
            "not enabled",
            "not authenticated",
            "service account",
            "api token",
            "login required",
        )
    )


def _record_runtime_integration_health(
    *,
    integration_id: str,
    status: str,
    details: dict[str, object],
) -> None:
    if integration_id != "browser":
        return
    try:
        from koda.control_plane.database import execute, json_dump, now_iso
    except Exception:
        return
    try:
        execute(
            """
            INSERT INTO cp_integration_health_checks (integration_id, status, details_json, checked_at)
            VALUES (?, ?, ?, ?)
            """,
            (integration_id, status, json_dump(details), now_iso()),
        )
    except Exception:
        return


def _policy_params_for_call(call: AgentToolCall, ctx: ToolContext) -> dict[str, object]:
    policy_params: dict[str, object] = dict(call.params)
    if call.tool.startswith("browser_"):
        try:
            from koda.services.browser_manager import browser_manager

            snapshot = browser_manager.get_session_snapshot(_browser_scope_id(ctx)) or {}
        except Exception:
            snapshot = {}
        if snapshot.get("url") and "current_url" not in policy_params:
            policy_params["current_url"] = snapshot["url"]
        if snapshot.get("domain") and "current_domain" not in policy_params:
            policy_params["current_domain"] = snapshot["domain"]
    return policy_params


def _effective_private_network_access(grant_decision: object) -> bool:
    grant = getattr(grant_decision, "grant", None)
    if not isinstance(grant, dict):
        return False
    return bool(grant.get("allow_private_network"))


async def execute_tool(
    call: AgentToolCall,
    ctx: ToolContext,
    *,
    policy_evaluation: PolicyEvaluation | None = None,
) -> AgentToolResult:
    """Execute a single agent tool call with timeout and security checks.

    Wraps the body in an OTel span so collectors see the full hierarchy
    (queue_manager → tool_dispatcher → internal_rpc → sidecar).
    ``start_span`` is a no-op when tracing is disabled
    (``OTEL_EXPORTER_OTLP_ENDPOINT`` unset), so the overhead on quiet
    hosts is a single attribute-dict construction per call.
    """
    from koda.config import AGENT_ID
    from koda.observability import start_span

    with start_span(
        "tool_dispatcher.execute_tool",
        tool=call.tool,
        agent_id=AGENT_ID or "default",
        task_id=ctx.task_id,
        user_id=ctx.user_id,
    ):
        return await _execute_tool_traced(call, ctx, policy_evaluation=policy_evaluation)


async def _execute_tool_traced(
    call: AgentToolCall,
    ctx: ToolContext,
    *,
    policy_evaluation: PolicyEvaluation | None = None,
) -> AgentToolResult:
    """Original execute_tool body — see ``execute_tool`` for the OTel
    span wrapper that calls into here."""
    import time

    from koda.config import AGENT_ID
    from koda.services import audit
    from koda.services.metrics import (
        INTEGRATION_EXECUTION_LATENCY,
        INTEGRATION_GRANT_DECISIONS,
        TOOL_EXECUTIONS,
    )
    from koda.services.runtime import get_runtime_controller

    _agent_id_label = AGENT_ID or "default"
    started_at = datetime.now(UTC).isoformat()
    try:
        runtime = get_runtime_controller()
    except Exception:
        runtime = None

    async def _publish_runtime_event(event_type: str, *, severity: str = "info", payload: dict | None = None) -> None:
        if ctx.task_id is None or runtime is None:
            return
        try:
            env = runtime.store.get_environment_by_task(ctx.task_id)
            task = runtime.store.get_task_runtime(ctx.task_id)
            await runtime.events.publish(
                task_id=ctx.task_id,
                env_id=int(env["id"]) if env else None,
                attempt=task.get("attempt") if task else None,
                phase=task.get("current_phase") if task else None,
                event_type=event_type,
                severity=severity,
                payload=payload or {},
            )
        except Exception:
            return

    handler = _TOOL_HANDLERS.get(call.tool)
    if not handler:
        if PLUGIN_SYSTEM_ENABLED:
            with contextlib.suppress(Exception):
                from koda.skills._package import ensure_installed_package_tools_registered

                ensure_installed_package_tools_registered(AGENT_ID or "default")
            from koda.plugins import get_registry

            handler = get_registry().get_handler(call.tool)
        if not handler:
            TOOL_EXECUTIONS.labels(agent_id=_agent_id_label, tool_name=call.tool, status="unknown").inc()
            return AgentToolResult(
                tool=call.tool,
                success=False,
                output=f"Unknown tool: {call.tool}",
                metadata={"category": _infer_tool_category(call.tool)},
                started_at=started_at,
                completed_at=datetime.now(UTC).isoformat(),
            )

    access_policy = _configured_resource_access_policy()
    policy_params = _policy_params_for_call(call, ctx)
    policy_evaluation = policy_evaluation or evaluate_execution_policy(
        call.tool,
        policy_params,
        task_kind=ctx.task_kind,
        effective_policy=ctx.effective_policy,
        resource_access_policy=access_policy,
        known_tool=True,
    )
    resolution = resolve_integration_action(call.tool, policy_params)
    grant_decision = evaluate_integration_grant(call.tool, policy_params, access_policy)
    handler_params = dict(call.params)
    if call.tool in {"fetch_url", "http_request"}:
        handler_params["allow_private"] = _effective_private_network_access(grant_decision)
    if call.tool.startswith("browser_"):
        handler_params["allow_private"] = _effective_private_network_access(grant_decision)
    integration_metadata = {
        "integration_id": grant_decision.integration_id,
        "action_id": grant_decision.action_id,
        "access_level": grant_decision.access_level,
        "grant_decision": "allowed" if grant_decision.allowed else "denied",
        "grant_reason": grant_decision.reason,
        "approval_mode": grant_decision.default_approval_mode,
        "auth_mode": grant_decision.auth_mode,
        "sensitive_access_used": grant_decision.sensitive_access_used,
    }
    audit_params = dict(policy_params)
    if resolution.resource_method:
        integration_metadata["resource_method"] = resolution.resource_method
        audit_params["resource_method"] = resolution.resource_method
    INTEGRATION_GRANT_DECISIONS.labels(
        agent_id=_agent_id_label,
        integration_id=grant_decision.integration_id,
        action_id=grant_decision.action_id,
        grant_decision="allowed" if grant_decision.allowed else "denied",
        auth_mode=grant_decision.auth_mode,
        sensitive_access_used=str(grant_decision.sensitive_access_used).lower(),
    ).inc()
    _record_integration_grant_audit(
        agent_id=_agent_id_label,
        decision=grant_decision,
        params=audit_params,
    )
    if policy_evaluation.decision == "deny":
        _audit_blocked(call.tool, f"execution_policy:{policy_evaluation.reason_code}", user_id=ctx.user_id)
        return AgentToolResult(
            tool=call.tool,
            success=False,
            output=policy_evaluation.reason or _integration_policy_error(str(grant_decision.reason)),
            metadata={
                "category": _infer_tool_category(call.tool),
                "policy_blocked": True,
                "policy_reason_code": policy_evaluation.reason_code,
                "policy_rule_id": policy_evaluation.rule_id,
                **integration_metadata,
            },
            started_at=started_at,
            completed_at=datetime.now(UTC).isoformat(),
        )
    if policy_evaluation.requires_confirmation:
        _audit_blocked(call.tool, f"approval_required:{policy_evaluation.reason_code}", user_id=ctx.user_id)
        preview_suffix = f"\n\nPreview:\n{policy_evaluation.preview_text}" if policy_evaluation.preview_text else ""
        return AgentToolResult(
            tool=call.tool,
            success=False,
            output=f"Human approval required before '{call.tool}' can execute.{preview_suffix}",
            metadata={
                "category": _infer_tool_category(call.tool),
                "approval_required": True,
                "policy_reason_code": policy_evaluation.reason_code,
                "policy_rule_id": policy_evaluation.rule_id,
                **integration_metadata,
            },
            started_at=started_at,
            completed_at=datetime.now(UTC).isoformat(),
        )

    _start = time.monotonic()
    try:
        await _publish_runtime_event("command.started", payload={"tool": call.tool, "params": call.params})
        rate_err = _check_tool_rate_limit(ctx.user_id, _agent_id_label)
        if rate_err:
            return AgentToolResult(
                tool=call.tool,
                success=False,
                output=rate_err,
                metadata={"category": _infer_tool_category(call.tool), "rate_limited": True},
                started_at=started_at,
                completed_at=datetime.now(UTC).isoformat(),
            )
        if _is_write_tool(call.tool, call.params) and ctx.agent_mode == "supervised":
            from koda.utils.approval import check_execution_approved

            if not check_execution_approved():
                return AgentToolResult(
                    tool=call.tool,
                    success=False,
                    output=f"Write operation '{call.tool}' requires approval in supervised mode.",
                    metadata={"category": _infer_tool_category(call.tool), "requires_approval": True},
                    started_at=started_at,
                    completed_at=datetime.now(UTC).isoformat(),
                )
        if ctx.dry_run and _is_write_tool(call.tool, call.params):
            return AgentToolResult(
                tool=call.tool,
                success=False,
                output=f"Dry-run blocked write tool '{call.tool}': no safe simulation is available.",
                metadata={"category": _infer_tool_category(call.tool), "dry_run_blocked": True},
                started_at=started_at,
                completed_at=datetime.now(UTC).isoformat(),
            )
        if call.tool.startswith("browser_"):
            timeout = BROWSER_TOOL_TIMEOUT
        else:
            timeout = AGENT_TOOL_TIMEOUT
        result = cast(
            AgentToolResult,
            await asyncio.wait_for(
                handler(handler_params, ctx),
                timeout=timeout,
            ),
        )
        _elapsed_ms = (time.monotonic() - _start) * 1000
        completed_at = datetime.now(UTC).isoformat()
        _status = "success" if result.success else "failed"
        TOOL_EXECUTIONS.labels(agent_id=_agent_id_label, tool_name=call.tool, status=_status).inc()
        result.duration_ms = _elapsed_ms
        result.started_at = started_at
        result.completed_at = completed_at
        result.metadata = {
            "category": _infer_tool_category(call.tool),
            **integration_metadata,
            **result.metadata,
        }
        if not result.success and _looks_like_runtime_auth_or_config_error(result.output):
            _record_runtime_integration_health(
                integration_id=grant_decision.integration_id,
                status="degraded",
                details={
                    "action_id": grant_decision.action_id,
                    "resource_method": resolution.resource_method,
                    "output": result.output[:1000],
                },
            )
        audit.emit_task_lifecycle(
            "task.tool_executed",
            user_id=ctx.user_id,
            task_id=ctx.task_id,
            duration_ms=_elapsed_ms,
            tool=call.tool,
            success=result.success,
            params=call.params,
            effective_params=handler_params,
            output=result.output,
            metadata=result.metadata,
            started_at=started_at,
            completed_at=completed_at,
        )
        INTEGRATION_EXECUTION_LATENCY.labels(
            agent_id=_agent_id_label,
            integration_id=grant_decision.integration_id,
            action_id=grant_decision.action_id,
            result_class=_status,
        ).observe(_elapsed_ms / 1000)
        await _publish_runtime_event(
            "command.finished",
            severity="info" if result.success else "warning",
            payload={"tool": call.tool, "success": result.success, "output": result.output},
        )
        try:
            from koda.config import DASHBOARD_ENABLED as _DASHBOARD_ON

            if _DASHBOARD_ON:
                from koda.dashboard import get_aggregator

                get_aggregator().record_tool_execution(
                    tool=call.tool,
                    success=result.success,
                    duration_ms=_elapsed_ms,
                    agent_id=_agent_id_label,
                )
        except Exception:
            pass
        return result
    except TimeoutError:
        _elapsed_ms = (time.monotonic() - _start) * 1000
        completed_at = datetime.now(UTC).isoformat()
        timeout_message = f"Tool '{call.tool}' timed out after {timeout}s."
        TOOL_EXECUTIONS.labels(agent_id=_agent_id_label, tool_name=call.tool, status="timeout").inc()
        audit.emit_task_lifecycle(
            "task.tool_executed",
            user_id=ctx.user_id,
            task_id=ctx.task_id,
            duration_ms=_elapsed_ms,
            tool=call.tool,
            success=False,
            error="timeout",
            params=call.params,
            effective_params=handler_params,
            metadata={"category": _infer_tool_category(call.tool), **integration_metadata},
            started_at=started_at,
            completed_at=completed_at,
        )
        if _looks_like_runtime_auth_or_config_error(timeout_message):
            _record_runtime_integration_health(
                integration_id=grant_decision.integration_id,
                status="degraded",
                details={
                    "action_id": grant_decision.action_id,
                    "resource_method": resolution.resource_method,
                    "error": timeout_message,
                },
            )
        INTEGRATION_EXECUTION_LATENCY.labels(
            agent_id=_agent_id_label,
            integration_id=grant_decision.integration_id,
            action_id=grant_decision.action_id,
            result_class="timeout",
        ).observe(_elapsed_ms / 1000)
        await _publish_runtime_event(
            "command.finished",
            severity="warning",
            payload={"tool": call.tool, "success": False, "error": timeout_message},
        )
        return AgentToolResult(
            tool=call.tool,
            success=False,
            output=timeout_message,
            metadata={"category": _infer_tool_category(call.tool), **integration_metadata},
            duration_ms=_elapsed_ms,
            started_at=started_at,
            completed_at=completed_at,
        )
    except Exception as e:
        _elapsed_ms = (time.monotonic() - _start) * 1000
        completed_at = datetime.now(UTC).isoformat()
        log.exception("agent_tool_error", tool=call.tool)
        TOOL_EXECUTIONS.labels(agent_id=_agent_id_label, tool_name=call.tool, status="error").inc()
        audit.emit_task_lifecycle(
            "task.tool_executed",
            user_id=ctx.user_id,
            task_id=ctx.task_id,
            duration_ms=_elapsed_ms,
            tool=call.tool,
            success=False,
            error=str(e),
            params=call.params,
            effective_params=handler_params,
            metadata={"category": _infer_tool_category(call.tool), **integration_metadata},
            started_at=started_at,
            completed_at=completed_at,
        )
        INTEGRATION_EXECUTION_LATENCY.labels(
            agent_id=_agent_id_label,
            integration_id=grant_decision.integration_id,
            action_id=grant_decision.action_id,
            result_class="error",
        ).observe(_elapsed_ms / 1000)
        await _publish_runtime_event(
            "command.finished",
            severity="error",
            payload={"tool": call.tool, "success": False, "error": str(e)},
        )
        return AgentToolResult(
            tool=call.tool,
            success=False,
            output=f"Error executing '{call.tool}': {e}",
            metadata={"category": _infer_tool_category(call.tool), **integration_metadata},
            duration_ms=_elapsed_ms,
            started_at=started_at,
            completed_at=completed_at,
        )


def format_tool_results(results: list[AgentToolResult]) -> str:
    """Format results as <tool_result> tags for provider resume."""
    parts = ["Here are the results of the agent tool calls you requested:\n"]
    for r in results:
        success = "true" if r.success else "false"
        body = r.output
        if STRUCTURED_DATA_OUTPUT_ENABLED and r.data is not None:
            try:
                data_json = json.dumps(r.data, ensure_ascii=False, default=str)
                fmt = r.data_format or "json"
                body += f'\n<structured_data format="{fmt}">{data_json}</structured_data>'
            except (TypeError, ValueError):
                pass  # silently skip if data is not serializable
        parts.append(f'<tool_result tool="{r.tool}" success="{success}">{body}</tool_result>')
    return "\n".join(parts)


def _is_write_tool(tool: str, params: dict) -> bool:
    """Determine if a tool call is a write operation."""
    if tool in _WRITE_TOOLS:
        return True
    if tool in _READ_TOOLS:
        return False
    # Check dynamically registered MCP tool sets
    if tool in _MCP_WRITE_TOOLS:
        return True
    if tool in _MCP_READ_TOOLS:
        return False
    if tool == "browser_cookies" and str(params.get("action", "get")).strip().lower() == "get":
        return False
    with contextlib.suppress(Exception):
        from koda.services.tool_registry import get_tool_definition

        definition = get_tool_definition(tool)
        if definition is not None and definition.source == "skill_package":
            return definition.access_level != "read"
    if tool not in _TOOL_HANDLERS:
        return False
    resolution = resolve_integration_action(tool, params)
    return resolution.access_level != "read"


# Tool handlers


async def _handle_job_list(params: dict, ctx: ToolContext) -> AgentToolResult:
    from koda.services.scheduler import list_user_jobs

    jobs = list_user_jobs(None, ctx.user_id)
    if not jobs:
        return AgentToolResult(tool="job_list", success=True, output="No scheduled jobs found.")
    return AgentToolResult(tool="job_list", success=True, output="\n".join(jobs))


async def _handle_job_get(params: dict, ctx: ToolContext) -> AgentToolResult:
    from koda.services.scheduled_jobs import get_job_detail

    job_id = params.get("job_id")
    if job_id is None:
        return AgentToolResult(tool="job_get", success=False, output="Missing required param: 'job_id'.")
    try:
        job_id = int(job_id)
    except (TypeError, ValueError):
        return AgentToolResult(tool="job_get", success=False, output="'job_id' must be an integer.")
    detail = get_job_detail(job_id, ctx.user_id, run_limit=int(params.get("run_limit", 10)), event_limit=20)
    if not detail:
        return AgentToolResult(tool="job_get", success=False, output=f"Job #{job_id} not found.")
    job = detail["job"]
    payload = job["payload"]
    return AgentToolResult(
        tool="job_get",
        success=True,
        output=(
            f"Job #{job['id']}\n"
            f"type={job['job_type']} trigger={job['trigger_type']} status={job['status']}\n"
            f"schedule={job['schedule_expr']} tz={job['timezone']}\n"
            f"provider/model={job.get('provider_preference') or 'n/a'} / {job.get('model_preference') or 'n/a'}\n"
            f"next={job.get('next_run_at') or 'pending validation'}\n"
            f"config_version={job.get('config_version') or 1}\n"
            f"notification_policy={json.dumps(job.get('notification_policy') or {}, ensure_ascii=True)}\n"
            f"verification_policy={json.dumps(job.get('verification_policy') or {}, ensure_ascii=True)}\n"
            f"payload={json.dumps(payload, ensure_ascii=True)}"
        ),
        metadata={"job": job, "runs": detail["runs"], "events": detail["events"]},
    )


async def _handle_job_runs(params: dict, ctx: ToolContext) -> AgentToolResult:
    from koda.services.scheduled_jobs import list_job_runs

    job_id = params.get("job_id")
    if job_id is None:
        return AgentToolResult(tool="job_runs", success=False, output="Missing required param: 'job_id'.")
    try:
        job_id = int(job_id)
    except (TypeError, ValueError):
        return AgentToolResult(tool="job_runs", success=False, output="'job_id' must be an integer.")
    runs = list_job_runs(job_id, ctx.user_id, limit=int(params.get("limit", 10)))
    if not runs:
        return AgentToolResult(tool="job_runs", success=True, output=f"No runs found for job #{job_id}.")
    lines = []
    for run in runs:
        lines.append(
            f"#{run['id']}: {run['trigger_reason']} [{run['status']}] scheduled={run['scheduled_for']} "
            f"task={run.get('task_id') or 'n/a'} verify={run.get('verification_status') or 'pending'} "
            f"attempt={run.get('attempt') or 0}/{run.get('max_attempts') or 0} trace={run.get('trace_id') or 'n/a'}"
        )
    return AgentToolResult(tool="job_runs", success=True, output="\n".join(lines), metadata={"runs": runs})


async def _handle_job_update(params: dict, ctx: ToolContext) -> AgentToolResult:
    from koda.services.scheduled_jobs import update_job

    try:
        job_id = _coerce_int(params.get("job_id"))
    except (TypeError, ValueError):
        return AgentToolResult(tool="job_update", success=False, output="'job_id' must be an integer.")
    patch = params.get("patch")
    if not isinstance(patch, dict) or not patch:
        return AgentToolResult(tool="job_update", success=False, output="Missing required param: 'patch'.")
    result = update_job(
        job_id,
        user_id=ctx.user_id,
        patch=patch,
        expected_config_version=_coerce_int(params["expected_config_version"])
        if params.get("expected_config_version") is not None
        else None,
        actor_type=str(params.get("actor_type") or "agent"),
        actor_id=str(params.get("actor_id") or ctx.user_id),
        source="agent_tool",
        reason=str(params.get("reason") or "Updated by agent request."),
        evidence=params.get("evidence") if isinstance(params.get("evidence"), dict) else None,
    )
    return AgentToolResult(
        tool="job_update",
        success=bool(result.get("ok")),
        output=str(result.get("message") or ("Job updated." if result.get("ok") else "Unable to update job.")),
        metadata=result,
    )


async def _handle_job_create(params: dict, ctx: ToolContext) -> AgentToolResult:
    from koda.services.scheduled_jobs import (
        create_agent_query_job,
        create_reminder_job,
        create_shell_command_job,
        queue_validation_run,
    )

    job_type = str(params.get("job_type") or "agent_query")
    trigger_type = str(params.get("trigger_type") or "")
    schedule_expr = str(params.get("schedule_expr") or "")
    timezone_name = params.get("timezone")
    work_dir_validation = validate_work_dir(str(params.get("work_dir") or ctx.work_dir))
    if not work_dir_validation.ok:
        _audit_blocked("job_create", "invalid_work_dir", user_id=ctx.user_id)
        return AgentToolResult(tool="job_create", success=False, output=work_dir_validation.reason or "Blocked.")
    verification_policy = params.get("verification_policy")
    notification_policy = params.get("notification_policy")
    safety_mode = str(params.get("safety_mode") or "dry_run_required")
    dry_run_required = bool(params.get("dry_run_required", True))
    auto_activate_after_validation = _coerce_bool(
        params.get("auto_activate_after_validation"),
        default=True,
    )
    if job_type == "agent_query":
        query = str(params.get("query") or "")
        if not trigger_type or not schedule_expr or not query:
            return AgentToolResult(
                tool="job_create",
                success=False,
                output="agent_query requires 'trigger_type', 'schedule_expr', and 'query'.",
            )
        job_id = create_agent_query_job(
            user_id=ctx.user_id,
            chat_id=ctx.chat_id,
            trigger_type=trigger_type,
            schedule_expr=schedule_expr,
            query=query,
            timezone_name=timezone_name,
            provider_preference=params.get("provider") or ctx.user_data.get("provider"),
            model_preference=params.get("model") or ctx.user_data.get("model"),
            work_dir=work_dir_validation.path,
            session_id=params.get("session_id") or ctx.user_data.get("session_id"),
            safety_mode=safety_mode,
            dry_run_required=dry_run_required,
            verification_policy=verification_policy if isinstance(verification_policy, dict) else None,
            notification_policy=notification_policy if isinstance(notification_policy, dict) else None,
            auto_activate_after_validation=auto_activate_after_validation,
        )
        return AgentToolResult(
            tool="job_create",
            success=True,
            output=(
                f"Scheduled agent job #{job_id} created in validation mode. "
                + (
                    "A safe dry-run is running now and the job will activate automatically if it passes."
                    if auto_activate_after_validation
                    else f"Run /jobs activate {job_id} after validation."
                )
            ),
        )
    if job_type == "reminder":
        text = str(params.get("text") or "")
        reminder_trigger_type = trigger_type or "one_shot"
        if not schedule_expr or not text:
            return AgentToolResult(
                tool="job_create",
                success=False,
                output="reminder requires 'schedule_expr' and 'text'.",
            )
        job_id = create_reminder_job(
            user_id=ctx.user_id,
            chat_id=ctx.chat_id,
            trigger_type=reminder_trigger_type,
            schedule_expr=schedule_expr,
            text=text,
            timezone_name=timezone_name,
            safety_mode=safety_mode,
            dry_run_required=dry_run_required,
            verification_policy=verification_policy if isinstance(verification_policy, dict) else None,
            notification_policy=notification_policy if isinstance(notification_policy, dict) else None,
            auto_activate_after_validation=auto_activate_after_validation,
        )
        return AgentToolResult(
            tool="job_create",
            success=True,
            output=(
                f"Reminder job #{job_id} created in validation mode. "
                + (
                    "A safe dry-run is running now and the job will activate automatically if it passes."
                    if auto_activate_after_validation
                    else f"Run /jobs activate {job_id} after validation."
                )
            ),
        )
    if job_type == "shell_command":
        command = str(params.get("command") or "")
        if trigger_type != "cron" or not schedule_expr or not command:
            return AgentToolResult(
                tool="job_create",
                success=False,
                output="shell_command requires trigger_type='cron', 'schedule_expr', and 'command'.",
            )
        if (_BLOCKED_SHELL is not None and _BLOCKED_SHELL.is_blocked(command)) or GIT_META_CHARS.search(command):
            _audit_blocked("job_create", "dangerous_shell_pattern", user_id=ctx.user_id)
            return AgentToolResult(tool="job_create", success=False, output="Blocked: unsafe shell command.")
        try:
            job_id = create_shell_command_job(
                user_id=ctx.user_id,
                chat_id=ctx.chat_id,
                expression=schedule_expr,
                command=command,
                description=str(params.get("description") or ""),
                work_dir=work_dir_validation.path,
                auto_activate=False,
                safety_mode=safety_mode,
                verification_policy=verification_policy if isinstance(verification_policy, dict) else None,
                notification_policy=notification_policy if isinstance(notification_policy, dict) else None,
            )
        except ValueError as exc:
            return AgentToolResult(tool="job_create", success=False, output=str(exc))
        queue_validation_run(job_id, user_id=ctx.user_id, activate_on_success=auto_activate_after_validation)
        return AgentToolResult(
            tool="job_create",
            success=True,
            output=(
                f"Scheduled shell command job #{job_id} created in validation mode. "
                + (
                    "A safe dry-run is running now and the job will activate automatically if it passes."
                    if auto_activate_after_validation
                    else f"Run /jobs activate {job_id} after validation."
                )
            ),
        )
    return AgentToolResult(tool="job_create", success=False, output=f"Unsupported job_type: {job_type}")


async def _handle_job_validate(params: dict, ctx: ToolContext) -> AgentToolResult:
    from koda.services.scheduled_jobs import queue_validation_run

    job_id = params.get("job_id")
    if job_id is None:
        return AgentToolResult(tool="job_validate", success=False, output="Missing required param: 'job_id'.")
    try:
        job_id = int(job_id)
    except (TypeError, ValueError):
        return AgentToolResult(tool="job_validate", success=False, output="'job_id' must be an integer.")
    run_id, msg = queue_validation_run(job_id, user_id=ctx.user_id, activate_on_success=False)
    return AgentToolResult(
        tool="job_validate",
        success=run_id is not None,
        output=msg if run_id is None else f"{msg} validation_run_id={run_id}",
    )


async def _handle_job_activate(params: dict, ctx: ToolContext) -> AgentToolResult:
    from koda.services.scheduled_jobs import activate_job

    try:
        job_id = _coerce_int(params.get("job_id"))
    except (TypeError, ValueError):
        return AgentToolResult(tool="job_activate", success=False, output="'job_id' must be an integer.")
    ok, msg = activate_job(job_id, ctx.user_id)
    return AgentToolResult(tool="job_activate", success=ok, output=msg)


async def _handle_job_pause(params: dict, ctx: ToolContext) -> AgentToolResult:
    from koda.services.scheduled_jobs import pause_job
    from koda.services.scheduler import cancel_user_jobs

    if str(params.get("job_id") or "").lower() == "all":
        paused = cancel_user_jobs(None, ctx.user_id)
        return AgentToolResult(
            tool="job_pause",
            success=True,
            output=f"Paused {paused} active jobs." if paused else "No active jobs were eligible for pause.",
        )
    try:
        job_id = _coerce_int(params.get("job_id"))
    except (TypeError, ValueError):
        return AgentToolResult(tool="job_pause", success=False, output="'job_id' must be an integer.")
    ok, msg = pause_job(job_id, ctx.user_id)
    return AgentToolResult(tool="job_pause", success=ok, output=msg)


async def _handle_job_resume(params: dict, ctx: ToolContext) -> AgentToolResult:
    from koda.services.scheduled_jobs import resume_job

    try:
        job_id = _coerce_int(params.get("job_id"))
    except (TypeError, ValueError):
        return AgentToolResult(tool="job_resume", success=False, output="'job_id' must be an integer.")
    ok, msg = resume_job(job_id, ctx.user_id)
    return AgentToolResult(tool="job_resume", success=ok, output=msg)


async def _handle_job_delete(params: dict, ctx: ToolContext) -> AgentToolResult:
    from koda.services.scheduled_jobs import delete_job

    try:
        job_id = _coerce_int(params.get("job_id"))
    except (TypeError, ValueError):
        return AgentToolResult(tool="job_delete", success=False, output="'job_id' must be an integer.")
    ok, msg = delete_job(job_id, ctx.user_id)
    return AgentToolResult(tool="job_delete", success=ok, output=msg)


async def _handle_job_run_now(params: dict, ctx: ToolContext) -> AgentToolResult:
    from koda.services.scheduled_jobs import run_job_now

    try:
        job_id = _coerce_int(params.get("job_id"))
    except (TypeError, ValueError):
        return AgentToolResult(tool="job_run_now", success=False, output="'job_id' must be an integer.")
    run_id, msg = run_job_now(job_id, ctx.user_id)
    return AgentToolResult(
        tool="job_run_now",
        success=run_id is not None,
        output=msg if run_id is None else f"{msg} run_id={run_id}",
    )


async def _handle_web_search(params: dict, ctx: ToolContext) -> AgentToolResult:
    query = params.get("query", "")
    if not query:
        return AgentToolResult(
            tool="web_search",
            success=False,
            output="Missing required param: 'query'.",
        )

    from koda.services.resilience import check_breaker, http_external_breaker, record_failure, record_success

    err = check_breaker(http_external_breaker)
    if err:
        return AgentToolResult(tool="web_search", success=False, output=err)

    from koda.services.http_client import search_web

    result = await search_web(query)
    success = not result.startswith("Error:")
    if success:
        record_success(http_external_breaker)
    else:
        record_failure(http_external_breaker)
    return AgentToolResult(tool="web_search", success=success, output=result)


async def _handle_fetch_url(params: dict, ctx: ToolContext) -> AgentToolResult:
    url = params.get("url", "")
    if not url:
        return AgentToolResult(
            tool="fetch_url",
            success=False,
            output="Missing required param: 'url'.",
        )

    from koda.services.resilience import check_breaker, http_external_breaker, record_failure, record_success

    err = check_breaker(http_external_breaker)
    if err:
        return AgentToolResult(tool="fetch_url", success=False, output=err)

    from koda.services.http_client import fetch_url

    result = await fetch_url(url, allow_private=bool(params.get("allow_private")))
    success = not result.startswith("Error:")
    if success:
        record_success(http_external_breaker)
    else:
        record_failure(http_external_breaker)
    return AgentToolResult(tool="fetch_url", success=success, output=result)


async def _handle_http_request(params: dict, ctx: ToolContext) -> AgentToolResult:
    method = params.get("method", "GET")
    url = params.get("url", "")
    body = params.get("body")
    headers = params.get("headers")

    if not url:
        return AgentToolResult(
            tool="http_request",
            success=False,
            output="Missing required param: 'url'.",
        )

    from koda.services.http_client import make_http_request

    result = await make_http_request(
        method,
        url,
        headers=headers,
        body=body,
        allow_private=bool(params.get("allow_private")),
    )
    success = not result.startswith("Error:")
    return AgentToolResult(tool="http_request", success=success, output=result)


async def _handle_set_workdir(params: dict, ctx: ToolContext) -> AgentToolResult:
    path = params.get("path", "")
    if not path:
        return AgentToolResult(
            tool="agent_set_workdir",
            success=False,
            output="Missing required param: 'path'.",
        )

    validation = validate_work_dir(path)
    if validation.blocked:
        _audit_blocked("agent_set_workdir", "sensitive_directory", user_id=ctx.user_id)
        return AgentToolResult(
            tool="agent_set_workdir",
            success=False,
            output=validation.reason or "Blocked.",
        )
    if not validation.ok:
        return AgentToolResult(
            tool="agent_set_workdir",
            success=False,
            output=validation.reason or "Directory does not exist.",
        )

    allowed_roots = [
        str(root)
        for root in (ctx.runtime_workspace_path, ctx.source_root_path)
        if str(root or "").strip()
    ]
    if allowed_roots and not _path_is_within_any_root(validation.path, allowed_roots):
        _audit_blocked("agent_set_workdir", "outside_workspace_roots", user_id=ctx.user_id)
        return AgentToolResult(
            tool="agent_set_workdir",
            success=False,
            output="Working directory must stay inside the active runtime workspace or workspace root.",
        )

    ctx.user_data["work_dir"] = validation.path
    return AgentToolResult(
        tool="agent_set_workdir",
        success=True,
        output=f"Working directory changed to: {validation.path}",
    )


def _path_is_within_any_root(path: str, roots: list[str]) -> bool:
    import os

    resolved = os.path.realpath(os.path.expanduser(path))
    for root in roots:
        root_resolved = os.path.realpath(os.path.expanduser(root))
        if resolved == root_resolved or resolved.startswith(root_resolved + os.sep):
            return True
    return False


async def _handle_get_status(params: dict, ctx: ToolContext) -> AgentToolResult:
    status_lines = [
        f"work_dir: {ctx.user_data.get('work_dir', ctx.work_dir)}",
        f"model: {ctx.user_data.get('model', 'unknown')}",
        f"session_id: {ctx.user_data.get('session_id', 'none')}",
        f"mode: {ctx.agent_mode}",
        f"total_cost: ${ctx.user_data.get('total_cost', 0.0):.4f}",
        f"query_count: {ctx.user_data.get('query_count', 0)}",
    ]
    return AgentToolResult(tool="agent_get_status", success=True, output="\n".join(status_lines))


async def _handle_image_generate(params: dict, ctx: ToolContext) -> AgentToolResult:
    prompt = str(params.get("prompt") or params.get("description") or "").strip()
    if not prompt:
        return AgentToolResult(tool="image_generate", success=False, output="Missing required param: 'prompt'.")

    from koda.services.generation_stubs import (
        GenerationServiceNotImplemented,
        ImageGenerationError,
        generate_image,
    )

    provider_id = str(params.get("provider_id") or params.get("provider") or "").strip() or None
    model_id = str(params.get("model_id") or params.get("model") or "").strip() or None
    output_format = params.get("output_format", params.get("format"))

    try:
        result = await asyncio.to_thread(
            generate_image,
            prompt,
            provider_id=provider_id,
            model_id=model_id,
            output_dir=ctx.work_dir,
            filename=str(params.get("filename") or "").strip() or None,
            size=str(params.get("size") or "").strip() or None,
            quality=str(params.get("quality") or "").strip() or None,
            background=str(params.get("background") or "").strip() or None,
            output_format=str(output_format or "").strip() or None,
            n=params.get("n"),
            user=str(ctx.user_id) if ctx.user_id else None,
        )
    except GenerationServiceNotImplemented as exc:
        return AgentToolResult(
            tool="image_generate",
            success=False,
            output=str(exc),
            metadata={"category": "image"},
        )
    except ImageGenerationError as exc:
        return AgentToolResult(
            tool="image_generate",
            success=False,
            output=f"Image generation failed: {exc}",
            metadata={"category": "image"},
        )

    created_files = [artifact.path for artifact in result.artifacts]
    output_lines = [
        f"Generated {len(created_files)} image(s) with {result.provider_id}/{result.model_id}:",
        *created_files,
    ]
    revised_prompts = [artifact.revised_prompt for artifact in result.artifacts if artifact.revised_prompt]
    if revised_prompts:
        output_lines.append("Revised prompt:")
        output_lines.append(revised_prompts[0])
    return AgentToolResult(
        tool="image_generate",
        success=True,
        output="\n".join(output_lines),
        metadata={
            "category": "image",
            "write": True,
            "created_files": created_files,
            "provider_id": result.provider_id,
            "model_id": result.model_id,
        },
        data={
            "provider_id": result.provider_id,
            "model_id": result.model_id,
            "artifacts": [
                {
                    "path": artifact.path,
                    "size": artifact.size,
                    "output_format": artifact.output_format,
                    "revised_prompt": artifact.revised_prompt,
                }
                for artifact in result.artifacts
            ],
        },
        data_format="json",
    )


async def _check_browser_available(tool_name: str) -> AgentToolResult | None:
    """Return error result if browser is not available, else None."""
    if not BROWSER_FEATURES_ENABLED:
        return AgentToolResult(
            tool=tool_name,
            success=False,
            output="Browser is disabled. Enable BROWSER_ENABLED=true or keep runtime browser live enabled.",
        )

    from koda.services.resilience import browser_breaker, check_breaker

    err = check_breaker(browser_breaker)
    if err:
        return AgentToolResult(tool=tool_name, success=False, output=err)

    from koda.services.browser_manager import browser_manager

    if not await browser_manager.ensure_started():
        return AgentToolResult(tool=tool_name, success=False, output="Browser is not running.")
    return None


async def _handle_browser_navigate(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_navigate")
    if err:
        return err
    url = params.get("url", "")
    if not url:
        return AgentToolResult(tool="browser_navigate", success=False, output="Missing required param: 'url'.")
    from koda.services.browser_manager import browser_manager

    result = await browser_manager.navigate(
        _browser_scope_id(ctx),
        url,
        allow_private=bool(params.get("allow_private")),
    )
    success = not result.startswith("Error")
    return AgentToolResult(tool="browser_navigate", success=success, output=result)


async def _handle_browser_click(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_click")
    if err:
        return err
    selector = params.get("selector", "")
    if not selector:
        return AgentToolResult(tool="browser_click", success=False, output="Missing required param: 'selector'.")
    from koda.services.browser_manager import browser_manager

    result = await browser_manager.smart_click(_browser_scope_id(ctx), selector)
    success = not result.startswith("Error") and "not found" not in result.lower()
    return AgentToolResult(tool="browser_click", success=success, output=result)


async def _handle_browser_type(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_type")
    if err:
        return err
    selector = params.get("selector", "")
    text = params.get("text", "")
    if not selector or not text:
        return AgentToolResult(
            tool="browser_type", success=False, output="Missing required params: 'selector' and 'text'."
        )
    clear_first = params.get("clear_first", True)
    if isinstance(clear_first, str):
        clear_first = clear_first.lower() in ("true", "1", "yes")
    from koda.services.browser_manager import browser_manager

    result = await browser_manager.smart_type(_browser_scope_id(ctx), selector, text, clear_first=clear_first)
    success = not result.startswith("Error") and "not found" not in result.lower()
    return AgentToolResult(tool="browser_type", success=success, output=result)


async def _handle_browser_submit(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_submit")
    if err:
        return err
    selector = params.get("selector")
    from koda.services.browser_manager import browser_manager

    result = await browser_manager.submit_form(_browser_scope_id(ctx), selector)
    success = not result.startswith("Error")
    return AgentToolResult(tool="browser_submit", success=success, output=result)


async def _handle_browser_screenshot(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_screenshot")
    if err:
        return err
    full_page = params.get("full_page", False)
    if isinstance(full_page, str):
        full_page = full_page.lower() in ("true", "1", "yes")
    selector = params.get("selector")
    from koda.services.browser_manager import browser_manager

    result = await browser_manager.screenshot_to_file(_browser_scope_id(ctx), full_page=full_page, selector=selector)
    success = not result.startswith("Error")
    return AgentToolResult(tool="browser_screenshot", success=success, output=result)


async def _handle_browser_get_text(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_get_text")
    if err:
        return err
    selector = params.get("selector")
    from koda.services.browser_manager import browser_manager

    result = await browser_manager.get_page_text(_browser_scope_id(ctx), selector=selector)
    success = not result.startswith("Error")
    return AgentToolResult(tool="browser_get_text", success=success, output=result)


async def _handle_browser_get_elements(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_get_elements")
    if err:
        return err
    element_type = params.get("element_type", "all")
    from koda.services.browser_manager import browser_manager

    result = await browser_manager.get_elements(_browser_scope_id(ctx), element_type=element_type)
    success = not result.startswith("Error")
    return AgentToolResult(tool="browser_get_elements", success=success, output=result)


async def _handle_browser_select(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_select")
    if err:
        return err
    selector = params.get("selector", "")
    if not selector:
        return AgentToolResult(tool="browser_select", success=False, output="Missing required param: 'selector'.")
    value = params.get("value")
    label = params.get("label")
    index = params.get("index")
    if index is not None:
        try:
            index = int(index)
        except (TypeError, ValueError):
            return AgentToolResult(tool="browser_select", success=False, output="'index' must be an integer.")
    from koda.services.browser_manager import browser_manager

    result = await browser_manager.select_option(
        _browser_scope_id(ctx),
        selector,
        value=value,
        label=label,
        index=index,
    )
    success = not result.startswith("Error")
    return AgentToolResult(tool="browser_select", success=success, output=result)


async def _handle_browser_scroll(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_scroll")
    if err:
        return err
    direction = params.get("direction", "down")
    amount = params.get("amount", 500)
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        amount = 500
    from koda.services.browser_manager import browser_manager

    result = await browser_manager.scroll(_browser_scope_id(ctx), direction=direction, amount=amount)
    success = not result.startswith("Error")
    return AgentToolResult(tool="browser_scroll", success=success, output=result)


async def _handle_browser_wait(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_wait")
    if err:
        return err
    selector = params.get("selector", "")
    if not selector:
        return AgentToolResult(tool="browser_wait", success=False, output="Missing required param: 'selector'.")
    state = params.get("state", "visible")
    timeout = params.get("timeout", 30000)
    try:
        timeout = int(timeout)
    except (TypeError, ValueError):
        timeout = 30000
    from koda.services.browser_manager import browser_manager

    result = await browser_manager.wait_for(_browser_scope_id(ctx), selector, state=state, timeout=timeout)
    success = not result.startswith("Error")
    return AgentToolResult(tool="browser_wait", success=success, output=result)


async def _handle_browser_back(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_back")
    if err:
        return err
    from koda.services.browser_manager import browser_manager

    result = await browser_manager.go_back(_browser_scope_id(ctx))
    success = not result.startswith("Error")
    return AgentToolResult(tool="browser_back", success=success, output=result)


async def _handle_browser_forward(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_forward")
    if err:
        return err
    from koda.services.browser_manager import browser_manager

    result = await browser_manager.go_forward(_browser_scope_id(ctx))
    success = not result.startswith("Error")
    return AgentToolResult(tool="browser_forward", success=success, output=result)


async def _handle_browser_hover(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_hover")
    if err:
        return err
    selector = params.get("selector", "")
    if not selector:
        return AgentToolResult(tool="browser_hover", success=False, output="Missing required param: 'selector'.")
    from koda.services.browser_manager import browser_manager

    result = await browser_manager.hover(_browser_scope_id(ctx), selector)
    success = not result.startswith("Error") and "not found" not in result.lower()
    return AgentToolResult(tool="browser_hover", success=success, output=result)


async def _handle_browser_press_key(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_press_key")
    if err:
        return err
    key = params.get("key", "")
    if not key:
        return AgentToolResult(tool="browser_press_key", success=False, output="Missing required param: 'key'.")
    selector = params.get("selector")
    from koda.services.browser_manager import browser_manager

    result = await browser_manager.press_key(_browser_scope_id(ctx), key, selector=selector)
    success = not result.startswith("Error") and "not found" not in result.lower()
    return AgentToolResult(tool="browser_press_key", success=success, output=result)


async def _handle_browser_cookies(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_cookies")
    if err:
        return err
    action = params.get("action", "get")
    from koda.services.browser_manager import browser_manager

    if action == "set":
        name = params.get("name", "")
        value = params.get("value", "")
        if not name:
            return AgentToolResult(
                tool="browser_cookies", success=False, output="Missing required param: 'name' for set action."
            )
        domain = params.get("domain")
        result = await browser_manager.set_cookie(
            _browser_scope_id(ctx),
            name,
            value,
            domain=domain,
            allow_private=bool(params.get("allow_private")),
        )
    else:
        url = params.get("url")
        result = await browser_manager.get_cookies(_browser_scope_id(ctx), url=url)
    success = not result.startswith("Error")
    return AgentToolResult(tool="browser_cookies", success=success, output=result)


# Browser tab handlers


async def _handle_browser_tab_open(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_tab_open")
    if err:
        return err
    url = params.get("url")
    from koda.services.browser_manager import browser_manager

    result = await browser_manager.open_tab(_browser_scope_id(ctx), url)
    success = not result.startswith("Error")
    return AgentToolResult(tool="browser_tab_open", success=success, output=result)


async def _handle_browser_tab_close(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_tab_close")
    if err:
        return err
    tab_id = params.get("tab_id")
    if tab_id is not None:
        try:
            tab_id = int(tab_id)
        except (TypeError, ValueError):
            return AgentToolResult(tool="browser_tab_close", success=False, output="tab_id must be an integer.")
    from koda.services.browser_manager import browser_manager

    result = await browser_manager.close_tab(_browser_scope_id(ctx), tab_id)
    success = not result.startswith("Error")
    return AgentToolResult(tool="browser_tab_close", success=success, output=result)


async def _handle_browser_tab_switch(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_tab_switch")
    if err:
        return err
    tab_id = params.get("tab_id")
    if tab_id is None:
        return AgentToolResult(tool="browser_tab_switch", success=False, output="Missing required param: 'tab_id'.")
    try:
        tab_id = int(tab_id)
    except (TypeError, ValueError):
        return AgentToolResult(tool="browser_tab_switch", success=False, output="tab_id must be an integer.")
    from koda.services.browser_manager import browser_manager

    result = await browser_manager.switch_tab(_browser_scope_id(ctx), tab_id)
    success = not result.startswith("Error")
    return AgentToolResult(tool="browser_tab_switch", success=success, output=result)


async def _handle_browser_tab_list(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_tab_list")
    if err:
        return err
    from koda.services.browser_manager import browser_manager

    text, data = await browser_manager.list_tabs(_browser_scope_id(ctx))
    success = not text.startswith("Error")
    return AgentToolResult(tool="browser_tab_list", success=success, output=text, metadata={"tabs": data})


async def _handle_browser_tab_compare(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_tab_compare")
    if err:
        return err
    tab_ids = params.get("tab_ids", [])
    if not isinstance(tab_ids, list) or len(tab_ids) < 2:
        return AgentToolResult(
            tool="browser_tab_compare",
            success=False,
            output="Provide 'tab_ids' as a list of at least 2 integers.",
        )
    try:
        tab_ids = [int(t) for t in tab_ids]
    except (TypeError, ValueError):
        return AgentToolResult(tool="browser_tab_compare", success=False, output="tab_ids must be integers.")
    selector = params.get("selector")
    from koda.services.browser_manager import browser_manager

    result = await browser_manager.compare_tabs(_browser_scope_id(ctx), tab_ids, selector)
    success = not result.startswith("Error")
    return AgentToolResult(tool="browser_tab_compare", success=success, output=result)


async def _handle_browser_execute_js(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_execute_js")
    if err:
        return err
    script = params.get("script", "")
    if not script:
        return AgentToolResult(tool="browser_execute_js", success=False, output="Missing required param: 'script'.")
    from koda.services.browser_manager import browser_manager

    result = await browser_manager.execute_js(_browser_scope_id(ctx), script)
    success = not result.startswith("Error")
    return AgentToolResult(tool="browser_execute_js", success=success, output=result)


async def _handle_browser_download(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_download")
    if err:
        return err
    url = params.get("url", "")
    if not url:
        return AgentToolResult(tool="browser_download", success=False, output="Missing required param: 'url'.")
    filename = params.get("filename")
    from koda.services.browser_manager import browser_manager

    result = await browser_manager.download_file(
        _browser_scope_id(ctx),
        url,
        filename,
        allow_private=bool(params.get("allow_private")),
    )
    success = not result.startswith("Error")
    return AgentToolResult(tool="browser_download", success=success, output=result)


async def _handle_browser_upload(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_upload")
    if err:
        return err
    selector = params.get("selector", "")
    file_path = params.get("file_path", "")
    if not file_path:
        return AgentToolResult(tool="browser_upload", success=False, output="Missing required param: 'file_path'.")
    if not selector:
        selector = 'input[type="file"]'
    from koda.services.browser_manager import browser_manager

    result = await browser_manager.upload_file(_browser_scope_id(ctx), selector, file_path, allowed_root=ctx.work_dir)
    success = not result.startswith("Error")
    return AgentToolResult(tool="browser_upload", success=success, output=result)


async def _handle_browser_set_viewport(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_set_viewport")
    if err:
        return err
    try:
        width = int(params.get("width", 1280))
        height = int(params.get("height", 720))
    except (TypeError, ValueError):
        return AgentToolResult(tool="browser_set_viewport", success=False, output="width and height must be integers.")
    from koda.services.browser_manager import browser_manager

    result = await browser_manager.set_viewport(_browser_scope_id(ctx), width, height)
    success = not result.startswith("Error")
    return AgentToolResult(tool="browser_set_viewport", success=success, output=result)


async def _handle_browser_pdf(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_pdf")
    if err:
        return err
    from koda.services.browser_manager import browser_manager

    result = await browser_manager.page_to_pdf(_browser_scope_id(ctx))
    success = not result.startswith("Error")
    return AgentToolResult(tool="browser_pdf", success=success, output=result)


# Script Library handlers


async def _handle_script_save(params: dict, ctx: ToolContext) -> AgentToolResult:
    from koda.services.cache_config import SCRIPT_LIBRARY_ENABLED

    if not SCRIPT_LIBRARY_ENABLED:
        return AgentToolResult(tool="script_save", success=False, output="Script library is disabled.")

    title = params.get("title", "")
    content = params.get("content", "")
    if not title or not content:
        return AgentToolResult(
            tool="script_save", success=False, output="Missing required params: 'title' and 'content'."
        )

    from koda.services.script_manager import get_script_manager

    sm = get_script_manager()
    description = params.get("description")
    language = params.get("language")
    tags = params.get("tags", [])
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except (json.JSONDecodeError, ValueError):
            tags = [t.strip() for t in tags.split(",") if t.strip()]

    row_id = await sm.save(
        user_id=ctx.user_id,
        title=title,
        description=description,
        content=content,
        language=language,
        tags=tags,
    )
    if row_id:
        return AgentToolResult(tool="script_save", success=True, output=f"Script #{row_id} saved: {title}")
    return AgentToolResult(tool="script_save", success=False, output="Failed to save script (limit reached or error).")


async def _handle_script_search(params: dict, ctx: ToolContext) -> AgentToolResult:
    from koda.services.cache_config import SCRIPT_LIBRARY_ENABLED

    if not SCRIPT_LIBRARY_ENABLED:
        return AgentToolResult(tool="script_search", success=False, output="Script library is disabled.")

    query = params.get("query", "")
    if not query:
        return AgentToolResult(tool="script_search", success=False, output="Missing required param: 'query'.")

    from koda.services.script_manager import get_script_manager

    sm = get_script_manager()
    language = params.get("language")
    results = await sm.search(query, ctx.user_id, language=language)

    if not results:
        return AgentToolResult(tool="script_search", success=True, output="No matching scripts found.")

    lines = []
    data = []
    for r in results:
        lang = f" [{r.language}]" if r.language else ""
        lines.append(f"#{r.script_id}: {r.title}{lang} (score: {r.similarity:.2f}, uses: {r.use_count})")
        if r.description:
            lines.append(f"  {r.description[:100]}")
        preview = r.content[:200].replace("\n", "\n  ")
        lines.append(f"  ```\n  {preview}\n  ```")
        data.append(
            {
                "id": r.script_id,
                "title": r.title,
                "language": r.language,
                "similarity": r.similarity,
                "use_count": r.use_count,
                "description": r.description,
            }
        )
    return AgentToolResult(tool="script_search", success=True, output="\n".join(lines), data=data, data_format="json")


async def _handle_script_list(params: dict, ctx: ToolContext) -> AgentToolResult:
    from koda.services.cache_config import SCRIPT_LIBRARY_ENABLED

    if not SCRIPT_LIBRARY_ENABLED:
        return AgentToolResult(tool="script_list", success=False, output="Script library is disabled.")

    from koda.services.script_manager import get_script_manager

    sm = get_script_manager()
    language = params.get("language")
    limit = params.get("limit", 20)
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 20

    scripts = await sm.list_scripts(ctx.user_id, language=language, limit=limit)
    if not scripts:
        return AgentToolResult(tool="script_list", success=True, output="No scripts saved yet.")

    lines = []
    data = []
    for row in scripts:
        sid, title, desc, lang, use_count, quality, created = row
        lang_str = f" [{lang}]" if lang else ""
        lines.append(f"#{sid}: {title}{lang_str} — uses: {use_count}, quality: {quality:.1f}")
        data.append(
            {
                "id": sid,
                "title": title,
                "description": desc,
                "language": lang,
                "use_count": use_count,
                "quality": quality,
                "created": created,
            }
        )
    return AgentToolResult(tool="script_list", success=True, output="\n".join(lines), data=data, data_format="json")


async def _handle_script_delete(params: dict, ctx: ToolContext) -> AgentToolResult:
    from koda.services.cache_config import SCRIPT_LIBRARY_ENABLED

    if not SCRIPT_LIBRARY_ENABLED:
        return AgentToolResult(tool="script_delete", success=False, output="Script library is disabled.")

    script_id = params.get("script_id")
    if script_id is None:
        return AgentToolResult(tool="script_delete", success=False, output="Missing required param: 'script_id'.")

    try:
        script_id = int(script_id)
    except (TypeError, ValueError):
        return AgentToolResult(tool="script_delete", success=False, output="'script_id' must be an integer.")

    from koda.services.script_manager import get_script_manager

    sm = get_script_manager()
    if await sm.deactivate(script_id, ctx.user_id):
        return AgentToolResult(tool="script_delete", success=True, output=f"Script #{script_id} deleted.")
    return AgentToolResult(
        tool="script_delete", success=False, output=f"Script #{script_id} not found or not owned by you."
    )


# Cache management handlers


async def _handle_cache_stats(params: dict, ctx: ToolContext) -> AgentToolResult:
    from koda.services.cache_config import CACHE_ENABLED

    if not CACHE_ENABLED:
        return AgentToolResult(tool="cache_stats", success=False, output="Cache is disabled.")

    from koda.services.cache_manager import get_cache_manager

    cm = get_cache_manager()
    stats = await cm.get_stats(ctx.user_id)

    from koda.services.script_manager import get_script_manager

    sm = get_script_manager()
    script_stats = await sm.get_stats(ctx.user_id)

    lines = [
        "Cache Statistics:",
        f"  Entries: {stats['entries']}",
        f"  Total hits: {stats['total_hits']}",
        f"  Estimated savings: ${stats['estimated_savings_usd']:.4f}",
        "",
        "Script Library:",
        f"  Scripts: {script_stats['scripts']}",
        f"  Total uses: {script_stats['total_uses']}",
    ]
    data = {
        "cache": {
            "entries": stats["entries"],
            "total_hits": stats["total_hits"],
            "estimated_savings_usd": stats["estimated_savings_usd"],
        },
        "script_library": {
            "scripts": script_stats["scripts"],
            "total_uses": script_stats["total_uses"],
        },
    }
    return AgentToolResult(tool="cache_stats", success=True, output="\n".join(lines), data=data, data_format="json")


async def _handle_cache_clear(params: dict, ctx: ToolContext) -> AgentToolResult:
    from koda.services.cache_config import CACHE_ENABLED

    if not CACHE_ENABLED:
        return AgentToolResult(tool="cache_clear", success=False, output="Cache is disabled.")

    from koda.services.cache_manager import get_cache_manager

    cm = get_cache_manager()
    count = await cm.invalidate_user(ctx.user_id)
    return AgentToolResult(tool="cache_clear", success=True, output=f"Cleared {count} cached entries.")


# Snapshot handlers


async def _handle_snapshot_save(params: dict, ctx: ToolContext) -> AgentToolResult:
    if not SNAPSHOT_ENABLED:
        return AgentToolResult(tool="snapshot_save", success=False, output="Snapshots not enabled.")
    name = params.get("name", "")
    if not name:
        return AgentToolResult(tool="snapshot_save", success=False, output="Missing 'name'.")
    from koda.snapshots.capture import capture_snapshot
    from koda.snapshots.store import get_snapshot_store

    scope_id = ctx.task_id if ctx.task_id else ctx.user_id
    data = await capture_snapshot(scope_id, ctx.work_dir)
    err = await get_snapshot_store().save(scope_id, name, data)
    if err:
        return AgentToolResult(tool="snapshot_save", success=False, output=err)
    subs = list(data.get("subsystems", {}).keys())
    return AgentToolResult(
        tool="snapshot_save", success=True, output=f"Snapshot '{name}' saved. Subsystems: {', '.join(subs)}"
    )


async def _handle_snapshot_restore(params: dict, ctx: ToolContext) -> AgentToolResult:
    if not SNAPSHOT_ENABLED:
        return AgentToolResult(tool="snapshot_restore", success=False, output="Snapshots not enabled.")
    name = params.get("name", "")
    if not name:
        return AgentToolResult(tool="snapshot_restore", success=False, output="Missing 'name'.")
    from koda.snapshots.store import get_snapshot_store

    scope_id = ctx.task_id if ctx.task_id else ctx.user_id
    data = get_snapshot_store().load(scope_id, name)
    if isinstance(data, str):
        return AgentToolResult(tool="snapshot_restore", success=False, output=data)
    subs = list(data.get("subsystems", {}).keys())
    return AgentToolResult(
        tool="snapshot_restore",
        success=True,
        output=(
            f"Snapshot '{name}' loaded. Contains: {', '.join(subs)}\n"
            "Note: state inspection only. Use individual tools to restore specific subsystem state."
        ),
        metadata={"snapshot_data": data},
    )


async def _handle_snapshot_list(params: dict, ctx: ToolContext) -> AgentToolResult:
    if not SNAPSHOT_ENABLED:
        return AgentToolResult(tool="snapshot_list", success=False, output="Snapshots not enabled.")
    from koda.snapshots.store import get_snapshot_store

    scope_id = ctx.task_id if ctx.task_id else ctx.user_id
    snapshots = get_snapshot_store().list_snapshots(scope_id)
    if not snapshots:
        return AgentToolResult(tool="snapshot_list", success=True, output="No snapshots.")
    lines = [f"Snapshots ({len(snapshots)}):"]
    for s in snapshots:
        lines.append(f"  {s['name']} \u2014 {s['size']} bytes, {s['age_hours']}h ago")
    return AgentToolResult(tool="snapshot_list", success=True, output="\n".join(lines))


async def _handle_snapshot_diff(params: dict, ctx: ToolContext) -> AgentToolResult:
    if not SNAPSHOT_ENABLED:
        return AgentToolResult(tool="snapshot_diff", success=False, output="Snapshots not enabled.")
    name_from = params.get("from", "")
    name_to = params.get("to", "")
    if not name_from or not name_to:
        return AgentToolResult(tool="snapshot_diff", success=False, output="Missing 'from' and 'to'.")
    from koda.snapshots.store import get_snapshot_store

    scope_id = ctx.task_id if ctx.task_id else ctx.user_id
    result = get_snapshot_store().diff(scope_id, name_from, name_to)
    if isinstance(result, str):
        return AgentToolResult(tool="snapshot_diff", success=False, output=result)
    changes = result.get("changes", {})
    if not changes:
        return AgentToolResult(tool="snapshot_diff", success=True, output="No differences found.")
    lines = [f"Diff: {name_from} \u2192 {name_to}"]
    for sub, info in changes.items():
        lines.append(f"  {sub}: {info['status']}")
    return AgentToolResult(tool="snapshot_diff", success=True, output="\n".join(lines))


async def _handle_snapshot_delete(params: dict, ctx: ToolContext) -> AgentToolResult:
    if not SNAPSHOT_ENABLED:
        return AgentToolResult(tool="snapshot_delete", success=False, output="Snapshots not enabled.")
    name = params.get("name", "")
    if not name:
        return AgentToolResult(tool="snapshot_delete", success=False, output="Missing 'name'.")
    from koda.snapshots.store import get_snapshot_store

    scope_id = ctx.task_id if ctx.task_id else ctx.user_id
    err = get_snapshot_store().delete(scope_id, name)
    if err:
        return AgentToolResult(tool="snapshot_delete", success=False, output=err)
    return AgentToolResult(tool="snapshot_delete", success=True, output=f"Snapshot '{name}' deleted.")


async def _handle_request_skill(params: dict, ctx: ToolContext) -> AgentToolResult:
    """Resolve a skill by name/alias/query and return its full content with instruction."""
    from koda.skills._index import SkillEmbeddingIndex
    from koda.skills._registry import build_skill_registry_from_custom_skills
    from koda.skills._runtime import get_runtime_agent_spec, get_runtime_custom_skills, get_runtime_skill_policy
    from koda.skills._selector import SkillSelector
    from koda.skills._telemetry import emit_skill_invocation

    query = str(params.get("query", "")).strip()
    if not query:
        return AgentToolResult(
            tool="request_skill",
            success=False,
            output="Please specify a skill name or description. Use /skill to list available skills.",
        )

    agent_spec = get_runtime_agent_spec()
    skill_policy = get_runtime_skill_policy(agent_spec) or None
    custom_skills = get_runtime_custom_skills(agent_spec)
    unfiltered_registry = build_skill_registry_from_custom_skills(custom_skills)
    registry = build_skill_registry_from_custom_skills(custom_skills, skill_policy)
    skills = registry.get_all()
    if not skills:
        return AgentToolResult(
            tool="request_skill",
            success=False,
            output="No expert skills configured for this agent.",
        )

    def _resolve_exact(registry_to_search: Any) -> Any:
        # Try exact match or alias before the semantic fallback.
        for key in (query.lower().replace(" ", "-"), query.lower()):
            skill_id = registry_to_search.resolve_alias(key)
            if skill_id:
                skill_match = registry_to_search.get(skill_id)
                if skill_match is not None:
                    return skill_match
            skill_match = registry_to_search.get(key)
            if skill_match is not None:
                return skill_match
        return None

    skill = _resolve_exact(registry)

    if skill is None and _resolve_exact(unfiltered_registry) is not None:
        available = ", ".join(sorted(skills.keys()))
        return AgentToolResult(
            tool="request_skill",
            success=False,
            output=f"No matching skill found for '{query}'. Skills configured for this agent: {available}",
        )

    if skill is None:
        # Fall back to semantic search
        try:
            skill_index = SkillEmbeddingIndex()
            skill_index.rebuild(skills)
            selector = SkillSelector(registry, skill_index)
            matches = selector.select(query, max_skills=1, agent_skill_policy=skill_policy)
            if matches and matches[0].composite_score >= 0.4:
                skill = matches[0].skill
        except Exception:
            pass

    if skill is None:
        available = ", ".join(sorted(skills.keys()))
        return AgentToolResult(
            tool="request_skill",
            success=False,
            output=f"No matching skill found for '{query}'. Skills configured for this agent: {available}",
        )

    # Build response with instruction
    parts: list[str] = []
    if skill.instruction:
        parts.append(f"<instruction>{skill.instruction}</instruction>")
    parts.append(skill.full_content)
    if skill.output_format_enforcement:
        parts.append(f"\n<output_format>{skill.output_format_enforcement}</output_format>")

    # Emit telemetry
    emit_skill_invocation(
        skill_id=skill.id,
        explicit=False,
        user_id=ctx.user_id,
        task_id=ctx.task_id,
    )

    return AgentToolResult(tool="request_skill", success=True, output="\n\n".join(parts))


# File operations handlers


async def _check_fileops_available(tool: str) -> AgentToolResult | None:
    if not FILEOPS_ENABLED:
        return AgentToolResult(
            tool=tool, success=False, output="File operations are not enabled. Set FILEOPS_ENABLED=true."
        )
    return None


def _validate_file_path(path: str, work_dir: str) -> str | None:
    """Validate file path is within work_dir and not a sensitive file. Returns error string or None."""
    import os

    if not path:
        return "Missing required param: 'path'."
    resolved = os.path.realpath(os.path.expanduser(path))
    work_resolved = os.path.realpath(work_dir)
    if not resolved.startswith(work_resolved + os.sep) and resolved != work_resolved:
        return f"Path '{path}' is outside the working directory."
    from koda.config import SENSITIVE_DIRS

    for sensitive in SENSITIVE_DIRS:
        if resolved.startswith(sensitive):
            return f"Access to '{sensitive}' is not allowed."
    _, ext = os.path.splitext(resolved)
    if ext.lower() in FILEOPS_BLOCKED_EXTENSIONS:
        return f"Files with extension '{ext}' are blocked for safety."
    return None


async def _handle_file_read(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_fileops_available("file_read")
    if err:
        return err
    path = params.get("path", "")
    path_err = _validate_file_path(path, ctx.work_dir)
    if path_err:
        return AgentToolResult(tool="file_read", success=False, output=path_err)
    import os

    resolved = os.path.realpath(os.path.expanduser(path))
    if not os.path.isfile(resolved):
        return AgentToolResult(tool="file_read", success=False, output=f"File not found: {path}")
    try:
        size = os.path.getsize(resolved)
        if size > FILEOPS_MAX_READ_SIZE:
            return AgentToolResult(
                tool="file_read",
                success=False,
                output=f"File too large ({size} bytes). Max: {FILEOPS_MAX_READ_SIZE}.",
            )
        offset = int(params.get("offset", 0))
        limit = int(params.get("limit", 0)) or None
        with open(resolved, errors="replace") as f:
            lines = f.readlines()
        if offset > 0:
            lines = lines[offset:]
        if limit:
            lines = lines[:limit]
        content = "".join(f"{offset + i + 1}\t{line}" for i, line in enumerate(lines))
        if len(content) > 50000:
            content = content[:50000] + "\n… (truncated)"
        return AgentToolResult(tool="file_read", success=True, output=content or "(empty file)")
    except Exception as e:
        return AgentToolResult(tool="file_read", success=False, output=f"Error reading file: {e}")


async def _handle_file_write(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_fileops_available("file_write")
    if err:
        return err
    path = params.get("path", "")
    content = params.get("content")
    if content is None:
        return AgentToolResult(tool="file_write", success=False, output="Missing required param: 'content'.")
    path_err = _validate_file_path(path, ctx.work_dir)
    if path_err:
        return AgentToolResult(tool="file_write", success=False, output=path_err)
    import os

    resolved = os.path.realpath(os.path.expanduser(path))
    try:
        os.makedirs(os.path.dirname(resolved), exist_ok=True)
        with open(resolved, "w") as f:
            f.write(str(content))
        size = os.path.getsize(resolved)
        return AgentToolResult(tool="file_write", success=True, output=f"Written {size} bytes to {path}")
    except Exception as e:
        return AgentToolResult(tool="file_write", success=False, output=f"Error writing file: {e}")


async def _handle_file_edit(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_fileops_available("file_edit")
    if err:
        return err
    path = params.get("path", "")
    old_string = params.get("old_string", "")
    new_string = params.get("new_string", "")
    if not old_string:
        return AgentToolResult(tool="file_edit", success=False, output="Missing required param: 'old_string'.")
    path_err = _validate_file_path(path, ctx.work_dir)
    if path_err:
        return AgentToolResult(tool="file_edit", success=False, output=path_err)
    import os

    resolved = os.path.realpath(os.path.expanduser(path))
    if not os.path.isfile(resolved):
        return AgentToolResult(tool="file_edit", success=False, output=f"File not found: {path}")
    try:
        with open(resolved, errors="replace") as f:
            content = f.read()
        count = content.count(old_string)
        if count == 0:
            return AgentToolResult(tool="file_edit", success=False, output="old_string not found in file.")
        replace_all = bool(params.get("replace_all", False))
        if not replace_all and count > 1:
            return AgentToolResult(
                tool="file_edit",
                success=False,
                output=f"old_string found {count} times. Set replace_all=true or provide a more specific string.",
            )
        if replace_all:
            new_content = content.replace(old_string, new_string)
        else:
            new_content = content.replace(old_string, new_string, 1)
        with open(resolved, "w") as f:
            f.write(new_content)
        replaced = count if replace_all else 1
        return AgentToolResult(tool="file_edit", success=True, output=f"Replaced {replaced} occurrence(s) in {path}")
    except Exception as e:
        return AgentToolResult(tool="file_edit", success=False, output=f"Error editing file: {e}")


async def _handle_file_list(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_fileops_available("file_list")
    if err:
        return err
    import os

    path = params.get("path", ctx.work_dir)
    path_err = _validate_file_path(path, ctx.work_dir)
    if path_err:
        return AgentToolResult(tool="file_list", success=False, output=path_err)
    resolved = os.path.realpath(os.path.expanduser(path))
    if not os.path.isdir(resolved):
        return AgentToolResult(tool="file_list", success=False, output=f"Not a directory: {path}")
    try:
        entries = sorted(os.listdir(resolved))
        lines: list[str] = []
        for entry in entries[:500]:
            full = os.path.join(resolved, entry)
            kind = "d" if os.path.isdir(full) else "f"
            try:
                size = os.path.getsize(full) if kind == "f" else 0
                lines.append(f"[{kind}] {entry}" + (f"  ({size} bytes)" if kind == "f" else ""))
            except OSError:
                lines.append(f"[{kind}] {entry}")
        result = "\n".join(lines) or "(empty directory)"
        if len(entries) > 500:
            result += f"\n… ({len(entries) - 500} more entries)"
        return AgentToolResult(tool="file_list", success=True, output=result)
    except Exception as e:
        return AgentToolResult(tool="file_list", success=False, output=f"Error listing directory: {e}")


async def _handle_file_search(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_fileops_available("file_search")
    if err:
        return err
    import fnmatch
    import os

    pattern = params.get("pattern", "")
    if not pattern:
        return AgentToolResult(tool="file_search", success=False, output="Missing required param: 'pattern'.")
    search_path = params.get("path", ctx.work_dir)
    path_err = _validate_file_path(search_path, ctx.work_dir)
    if path_err:
        return AgentToolResult(tool="file_search", success=False, output=path_err)
    resolved = os.path.realpath(os.path.expanduser(search_path))
    try:
        matches: list[str] = []
        for root, dirs, files in os.walk(resolved):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for name in files:
                if fnmatch.fnmatch(name, pattern):
                    rel = os.path.relpath(os.path.join(root, name), resolved)
                    matches.append(rel)
                    if len(matches) >= 200:
                        break
            if len(matches) >= 200:
                break
        result = "\n".join(matches) if matches else f"No files matching '{pattern}' found."
        if len(matches) >= 200:
            result += "\n… (results capped at 200)"
        return AgentToolResult(tool="file_search", success=True, output=result)
    except Exception as e:
        return AgentToolResult(tool="file_search", success=False, output=f"Error searching: {e}")


async def _handle_file_grep(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_fileops_available("file_grep")
    if err:
        return err
    import fnmatch
    import os
    import re as re_mod

    pattern = params.get("pattern", "")
    if not pattern:
        return AgentToolResult(tool="file_grep", success=False, output="Missing required param: 'pattern'.")
    search_path = params.get("path", ctx.work_dir)
    path_err = _validate_file_path(search_path, ctx.work_dir)
    if path_err:
        return AgentToolResult(tool="file_grep", success=False, output=path_err)
    resolved = os.path.realpath(os.path.expanduser(search_path))
    try:
        regex = re_mod.compile(pattern, re_mod.IGNORECASE if params.get("ignore_case") else 0)
    except re_mod.error as e:
        return AgentToolResult(tool="file_grep", success=False, output=f"Invalid regex: {e}")
    try:
        glob_filter = params.get("glob", "*")
        results: list[str] = []
        total_matches = 0
        for root, dirs, files in os.walk(resolved):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for name in files:
                if not fnmatch.fnmatch(name, glob_filter):
                    continue
                fpath = os.path.join(root, name)
                rel = os.path.relpath(fpath, resolved)
                try:
                    with open(fpath, errors="replace") as f:
                        for lineno, line in enumerate(f, 1):
                            if regex.search(line):
                                results.append(f"{rel}:{lineno}: {line.rstrip()}")
                                total_matches += 1
                                if total_matches >= 200:
                                    break
                except (OSError, UnicodeDecodeError):
                    continue
                if total_matches >= 200:
                    break
            if total_matches >= 200:
                break
        output = "\n".join(results) if results else f"No matches for '{pattern}'."
        if total_matches >= 200:
            output += "\n… (results capped at 200)"
        return AgentToolResult(tool="file_grep", success=True, output=output)
    except Exception as e:
        return AgentToolResult(tool="file_grep", success=False, output=f"Error grepping: {e}")


async def _handle_file_delete(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_fileops_available("file_delete")
    if err:
        return err
    import os

    path = params.get("path", "")
    path_err = _validate_file_path(path, ctx.work_dir)
    if path_err:
        return AgentToolResult(tool="file_delete", success=False, output=path_err)
    resolved = os.path.realpath(os.path.expanduser(path))
    if not os.path.exists(resolved):
        return AgentToolResult(tool="file_delete", success=False, output=f"File not found: {path}")
    if os.path.isdir(resolved):
        return AgentToolResult(tool="file_delete", success=False, output="Cannot delete directories. Only files.")
    try:
        os.remove(resolved)
        return AgentToolResult(tool="file_delete", success=True, output=f"Deleted: {path}")
    except Exception as e:
        return AgentToolResult(tool="file_delete", success=False, output=f"Error deleting file: {e}")


async def _handle_file_move(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_fileops_available("file_move")
    if err:
        return err
    import os
    import shutil

    source = params.get("source", "")
    destination = params.get("destination", "")
    if not source or not destination:
        return AgentToolResult(
            tool="file_move", success=False, output="Missing required params: 'source' and 'destination'."
        )
    src_err = _validate_file_path(source, ctx.work_dir)
    if src_err:
        return AgentToolResult(tool="file_move", success=False, output=src_err)
    dst_err = _validate_file_path(destination, ctx.work_dir)
    if dst_err:
        return AgentToolResult(tool="file_move", success=False, output=dst_err)
    resolved_src = os.path.realpath(os.path.expanduser(source))
    resolved_dst = os.path.realpath(os.path.expanduser(destination))
    if not os.path.exists(resolved_src):
        return AgentToolResult(tool="file_move", success=False, output=f"Source not found: {source}")
    try:
        os.makedirs(os.path.dirname(resolved_dst), exist_ok=True)
        shutil.move(resolved_src, resolved_dst)
        return AgentToolResult(tool="file_move", success=True, output=f"Moved: {source} → {destination}")
    except Exception as e:
        return AgentToolResult(tool="file_move", success=False, output=f"Error moving file: {e}")


async def _handle_file_info(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_fileops_available("file_info")
    if err:
        return err
    import os
    from datetime import UTC as _UTC
    from datetime import datetime as _datetime

    path = params.get("path", "")
    path_err = _validate_file_path(path, ctx.work_dir)
    if path_err:
        return AgentToolResult(tool="file_info", success=False, output=path_err)
    resolved = os.path.realpath(os.path.expanduser(path))
    if not os.path.exists(resolved):
        return AgentToolResult(tool="file_info", success=False, output=f"Not found: {path}")
    try:
        stat = os.stat(resolved)
        kind = "directory" if os.path.isdir(resolved) else "file"
        modified = _datetime.fromtimestamp(stat.st_mtime, tz=_UTC).isoformat()
        created = _datetime.fromtimestamp(stat.st_ctime, tz=_UTC).isoformat()
        info = (
            f"Type: {kind}\n"
            f"Size: {stat.st_size} bytes\n"
            f"Permissions: {oct(stat.st_mode)}\n"
            f"Modified: {modified}\n"
            f"Created: {created}\n"
            f"Path: {resolved}"
        )
        return AgentToolResult(tool="file_info", success=True, output=info)
    except Exception as e:
        return AgentToolResult(tool="file_info", success=False, output=f"Error: {e}")


# Shell tool handlers


async def _check_shell_available(tool: str) -> AgentToolResult | None:
    if not SHELL_ENABLED:
        return AgentToolResult(
            tool=tool, success=False, output="Shell execution is not enabled. Set SHELL_ENABLED=true."
        )
    return None


async def _handle_shell_execute(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_shell_available("shell_execute")
    if err:
        return err
    command = params.get("command", "")
    if not command:
        return AgentToolResult(tool="shell_execute", success=False, output="Missing required param: 'command'.")

    # Token-level command blocking (defense-in-depth)
    from koda.config import BLOCKED_COMMAND_TOKENS

    try:
        import shlex

        tokens = shlex.split(command)
        for token in tokens:
            base = token.rsplit("/", 1)[-1]  # handle absolute paths like /usr/bin/sudo
            if base.lower() in BLOCKED_COMMAND_TOKENS:
                _audit_blocked("shell_execute", f"blocked_command_token:{base}", user_id=ctx.user_id)
                return AgentToolResult(
                    tool="shell_execute",
                    success=False,
                    output=f"Command blocked: '{base}' is not allowed.",
                    metadata={"category": "shell", "blocked": True},
                )
    except ValueError:
        # shlex parse error on malformed input — regex check still applies.
        # Log for operator visibility so potential evasion attempts are detectable.
        log.warning("shell_token_check_shlex_error", command=command[:200], user_id=ctx.user_id)

    timeout = int(params.get("timeout", SHELL_TIMEOUT))
    timeout = min(max(1, timeout), 300)  # cap at 5 minutes
    from koda.services.shell_runner import run_shell_command

    result = await run_shell_command(command, ctx.work_dir, timeout=timeout)
    success = not result.startswith("Error") and not result.startswith("Blocked")
    return AgentToolResult(tool="shell_execute", success=success, output=result)


async def _handle_shell_bg(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_shell_available("shell_bg")
    if err:
        return err
    command = params.get("command", "")
    if not command:
        return AgentToolResult(tool="shell_bg", success=False, output="Missing required param: 'command'.")
    timeout = int(params.get("timeout", SHELL_TIMEOUT))
    timeout = min(max(1, timeout), 600)
    from koda.services.shell_tools import bg_process_manager

    handle_id, error = await bg_process_manager.start(command, ctx.work_dir, ctx.user_id, timeout=timeout)
    if error:
        return AgentToolResult(tool="shell_bg", success=False, output=error)
    return AgentToolResult(
        tool="shell_bg",
        success=True,
        output=f"Started background process: {handle_id}\nUse shell_status or shell_output to check progress.",
    )


async def _handle_shell_status(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_shell_available("shell_status")
    if err:
        return err
    handle_id = params.get("handle_id", "")
    if not handle_id:
        return AgentToolResult(tool="shell_status", success=False, output="Missing required param: 'handle_id'.")
    from koda.services.shell_tools import bg_process_manager

    bg = bg_process_manager.get(handle_id, user_id=ctx.user_id)
    if not bg:
        return AgentToolResult(tool="shell_status", success=False, output=f"No process with handle '{handle_id}'.")
    import time

    elapsed = time.monotonic() - bg.started_at
    status = "finished" if bg.finished else "running"
    if bg.killed:
        status = "killed"
    if bg.timed_out:
        status = "timed_out"
    info = f"Handle: {bg.handle_id}\nStatus: {status}\nCommand: {bg.command}\nElapsed: {elapsed:.1f}s"
    if bg.finished:
        info += f"\nExit code: {bg.exit_code}"
    return AgentToolResult(tool="shell_status", success=True, output=info)


async def _handle_shell_kill(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_shell_available("shell_kill")
    if err:
        return err
    handle_id = params.get("handle_id", "")
    if not handle_id:
        return AgentToolResult(tool="shell_kill", success=False, output="Missing required param: 'handle_id'.")
    from koda.services.shell_tools import bg_process_manager

    error = await bg_process_manager.kill(handle_id, user_id=ctx.user_id)
    if error:
        return AgentToolResult(tool="shell_kill", success=False, output=error)
    return AgentToolResult(tool="shell_kill", success=True, output=f"Killed process: {handle_id}")


async def _handle_shell_output(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_shell_available("shell_output")
    if err:
        return err
    handle_id = params.get("handle_id", "")
    if not handle_id:
        return AgentToolResult(tool="shell_output", success=False, output="Missing required param: 'handle_id'.")
    from koda.services.shell_tools import bg_process_manager

    bg = bg_process_manager.get(handle_id, user_id=ctx.user_id)
    if not bg:
        return AgentToolResult(tool="shell_output", success=False, output=f"No process with handle '{handle_id}'.")
    if not bg.finished:
        return AgentToolResult(
            tool="shell_output", success=True, output="Process still running. No output available yet."
        )
    output = (bg.stdout_buf + bg.stderr_buf).strip()
    if not output:
        output = "(no output)"
    return AgentToolResult(tool="shell_output", success=True, output=f"Exit {bg.exit_code}:\n{output}")


# Git tool handlers


async def _check_git_available(tool: str) -> AgentToolResult | None:
    if not GIT_ENABLED:
        return AgentToolResult(tool=tool, success=False, output="Git tools are not enabled. Set GIT_ENABLED=true.")
    return None


def _validate_git_args(args: list[str]) -> str | None:
    """Validate git arguments for injection. Returns error or None."""
    for arg in args:
        if GIT_META_CHARS.search(arg):
            return "Blocked: argument contains disallowed characters."
    return None


async def _run_git(subcommand: str, args: list[str], ctx: ToolContext, timeout: int = 30) -> AgentToolResult:
    """Run a git subcommand via cli_runner."""
    tool_name = f"git_{subcommand}"
    if subcommand not in ALLOWED_GIT_CMDS:
        return AgentToolResult(tool=tool_name, success=False, output=f"Git subcommand '{subcommand}' is not allowed.")
    arg_err = _validate_git_args(args)
    if arg_err:
        return AgentToolResult(tool=tool_name, success=False, output=arg_err)
    import shlex

    from koda.services.cli_runner import run_cli_command_detailed

    args_str = " ".join([subcommand, *(shlex.quote(a) for a in args)])
    result = await run_cli_command_detailed(
        "git",
        args_str,
        ctx.work_dir,
        allowed_cmds=ALLOWED_GIT_CMDS,
        timeout=timeout,
    )
    if result.blocked:
        return AgentToolResult(tool=tool_name, success=False, output="Blocked: this git command is not allowed.")
    if result.timed_out:
        return AgentToolResult(tool=tool_name, success=False, output=f"Timeout after {timeout}s.")
    if result.error:
        return AgentToolResult(tool=tool_name, success=False, output="Error: command execution failed.")
    success = result.exit_code == 0
    output = result.text or "(no output)"
    if not success:
        output = f"Exit {result.exit_code}:\n{output}"
    return AgentToolResult(tool=tool_name, success=success, output=output)


async def _handle_git_status(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_git_available("git_status")
    if err:
        return err
    args: list[str] = []
    if params.get("short"):
        args.append("--short")
    return await _run_git("status", args, ctx)


async def _handle_git_diff(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_git_available("git_diff")
    if err:
        return err
    args: list[str] = []
    if params.get("staged"):
        args.append("--cached")
    if params.get("ref"):
        args.append(str(params["ref"]))
    if params.get("path"):
        args.extend(["--", str(params["path"])])
    if params.get("stat"):
        args.append("--stat")
    return await _run_git("diff", args, ctx)


async def _handle_git_log(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_git_available("git_log")
    if err:
        return err
    limit = int(params.get("limit", 10))
    limit = min(max(1, limit), 100)
    args = [f"-{limit}", "--oneline"]
    if params.get("all"):
        args.append("--all")
    if params.get("graph"):
        args.append("--graph")
    if params.get("path"):
        args.extend(["--", str(params["path"])])
    return await _run_git("log", args, ctx)


async def _handle_git_commit(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_git_available("git_commit")
    if err:
        return err
    message = params.get("message", "")
    if not message:
        return AgentToolResult(tool="git_commit", success=False, output="Missing required param: 'message'.")
    args = ["-m", message]
    if params.get("all"):
        args.insert(0, "-a")
    return await _run_git("commit", args, ctx)


async def _handle_git_branch(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_git_available("git_branch")
    if err:
        return err
    name = params.get("name")
    if name:
        # Create branch
        args = [str(name)]
        if params.get("start_point"):
            args.append(str(params["start_point"]))
        return await _run_git("branch", args, ctx)
    else:
        # List branches
        list_args: list[str] = ["-a"] if params.get("all") else []
        list_args.append("-v")
        return await _run_git("branch", list_args, ctx)


async def _handle_git_checkout(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_git_available("git_checkout")
    if err:
        return err
    target = params.get("target", "")
    if not target:
        return AgentToolResult(
            tool="git_checkout",
            success=False,
            output="Missing required param: 'target' (branch name, commit, or file path).",
        )
    args = [str(target)]
    if params.get("create"):
        args = ["-b", str(target)]
        if params.get("start_point"):
            args.append(str(params["start_point"]))
    return await _run_git("checkout", args, ctx)


async def _handle_git_push(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_git_available("git_push")
    if err:
        return err
    args: list[str] = []
    remote = params.get("remote", "origin")
    branch = params.get("branch")
    args.append(str(remote))
    if branch:
        args.append(str(branch))
    if params.get("set_upstream"):
        args.insert(0, "-u")
    return await _run_git("push", args, ctx, timeout=60)


async def _handle_git_pull(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_git_available("git_pull")
    if err:
        return err
    args: list[str] = []
    remote = params.get("remote")
    branch = params.get("branch")
    if remote:
        args.append(str(remote))
        if branch:
            args.append(str(branch))
    if params.get("rebase"):
        args.insert(0, "--rebase")
    return await _run_git("pull", args, ctx, timeout=60)


# Plugin handlers


async def _check_plugin_available(tool: str) -> AgentToolResult | None:
    if not PLUGIN_SYSTEM_ENABLED:
        return AgentToolResult(
            tool=tool,
            success=False,
            output="Plugin system not enabled. Set PLUGIN_SYSTEM_ENABLED=true.",
        )
    return None


async def _handle_plugin_list(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_plugin_available("plugin_list")
    if err:
        return err
    from koda.config import AGENT_ID
    from koda.skills._package import ensure_installed_package_tools_registered

    ensure_installed_package_tools_registered(AGENT_ID or "default")
    from koda.plugins import get_registry

    plugins = get_registry().list_plugins()
    if not plugins:
        return AgentToolResult(
            tool="plugin_list",
            success=True,
            output="No plugins installed.",
            metadata={"data": [], "data_format": "json"},
        )
    lines = [f"Installed plugins ({len(plugins)}):"]
    for p in plugins:
        lines.append(f"  {p['name']} v{p['version']} — {p['description']} ({p['tool_count']} tools)")
    return AgentToolResult(
        tool="plugin_list",
        success=True,
        output="\n".join(lines),
        metadata={"data": plugins, "data_format": "json"},
    )


async def _handle_plugin_info(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_plugin_available("plugin_info")
    if err:
        return err
    name = params.get("name", "")
    if not name:
        return AgentToolResult(tool="plugin_info", success=False, output="Missing required param: 'name'.")
    from koda.config import AGENT_ID
    from koda.skills._package import ensure_installed_package_tools_registered

    ensure_installed_package_tools_registered(AGENT_ID or "default")
    from koda.plugins import get_registry

    plugins = get_registry().list_plugins()
    info = next((p for p in plugins if p["name"] == name), None)
    if not info:
        return AgentToolResult(tool="plugin_info", success=False, output=f"Plugin '{name}' not found.")
    tools = get_registry().list_tools(name)
    lines = [
        f"Plugin: {info['name']} v{info['version']}",
        f"Author: {info['author']}",
        f"Description: {info['description']}",
        f"Tools ({len(tools)}):",
    ]
    for t in tools:
        rw = "READ" if t["read_only"] else "WRITE"
        lines.append(f"  {t['id']} [{rw}] — {t['description']}")
    return AgentToolResult(
        tool="plugin_info",
        success=True,
        output="\n".join(lines),
        metadata={"data": {"plugin": info, "tools": tools}, "data_format": "json"},
    )


async def _handle_plugin_install(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_plugin_available("plugin_install")
    if err:
        return err
    path = params.get("path", "")
    if not path:
        return AgentToolResult(tool="plugin_install", success=False, output="Missing required param: 'path'.")
    from koda.config import AGENT_ID
    from koda.skills._package import SkillPackageError, install_skill_package

    try:
        result = install_skill_package(
            path,
            agent_id=AGENT_ID or "default",
            review_accepted=bool(params.get("review_accepted") or params.get("approved")),
        )
    except SkillPackageError as exc:
        error = dict(exc.error)
        scan = error.get("scan") if isinstance(error.get("scan"), dict) else {}
        raw_findings = scan.get("findings") if isinstance(scan, dict) else []
        findings = raw_findings if isinstance(raw_findings, list) else []
        finding_lines = "\n".join(
            f"  - {item.get('id')}: {item.get('message')}" for item in findings if isinstance(item, dict)
        )
        output = error.get("message", "Skill package install failed.")
        if finding_lines:
            output = f"{output}\n{finding_lines}"
        return AgentToolResult(
            tool="plugin_install",
            success=False,
            output=output,
            metadata={"data": {"error": error}, "data_format": "json"},
        )
    lock = result["lock"]
    return AgentToolResult(
        tool="plugin_install",
        success=True,
        output=(
            f"Plugin package '{lock.get('package_id')}' installed with "
            f"{len(lock.get('installed_tools') or [])} tools and {len(lock.get('installed_skills') or [])} skills."
        ),
        metadata={"data": result, "data_format": "json"},
    )


async def _handle_plugin_uninstall(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_plugin_available("plugin_uninstall")
    if err:
        return err
    name = params.get("name", "")
    if not name:
        return AgentToolResult(tool="plugin_uninstall", success=False, output="Missing required param: 'name'.")
    from koda.config import AGENT_ID
    from koda.skills._package import SkillPackageError, get_skill_package_lock, uninstall_skill_package

    if get_skill_package_lock(AGENT_ID or "default", name):
        try:
            result = uninstall_skill_package(AGENT_ID or "default", name)
        except SkillPackageError as exc:
            error = dict(exc.error)
            return AgentToolResult(
                tool="plugin_uninstall",
                success=False,
                output=str(error.get("message") or "Skill package uninstall failed."),
                metadata={"data": {"error": error}, "data_format": "json"},
            )
        return AgentToolResult(
            tool="plugin_uninstall",
            success=True,
            output=f"Plugin package '{name}' uninstalled.",
            metadata={"data": result, "data_format": "json"},
        )
    from koda.plugins import get_registry

    unreg_err = get_registry().unregister(name)
    if unreg_err:
        return AgentToolResult(tool="plugin_uninstall", success=False, output=unreg_err)
    return AgentToolResult(tool="plugin_uninstall", success=True, output=f"Plugin '{name}' uninstalled.")


async def _handle_plugin_reload(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_plugin_available("plugin_reload")
    if err:
        return err
    name = params.get("name", "")
    if not name:
        return AgentToolResult(tool="plugin_reload", success=False, output="Missing required param: 'name'.")
    from koda.config import AGENT_ID
    from koda.skills._package import ensure_installed_package_tools_registered, get_skill_package_lock

    if get_skill_package_lock(AGENT_ID or "default", name):
        ensure_installed_package_tools_registered(AGENT_ID or "default", force=True)
        return AgentToolResult(tool="plugin_reload", success=True, output=f"Plugin package '{name}' reloaded.")
    from koda.plugins import get_registry

    reload_err = get_registry().reload(name)
    if reload_err:
        return AgentToolResult(tool="plugin_reload", success=False, output=reload_err)
    return AgentToolResult(tool="plugin_reload", success=True, output=f"Plugin '{name}' reloaded.")


# Workflow handlers


async def _check_workflow_available(tool: str) -> AgentToolResult | None:
    if not WORKFLOW_ENABLED:
        return AgentToolResult(
            tool=tool,
            success=False,
            output="Workflows not enabled. Set WORKFLOW_ENABLED=true.",
        )
    return None


async def _handle_workflow_create(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_workflow_available("workflow_create")
    if err:
        return err
    name = params.get("name", "")
    steps = params.get("steps", [])
    if not name:
        return AgentToolResult(tool="workflow_create", success=False, output="Missing 'name'.")
    if not steps:
        return AgentToolResult(tool="workflow_create", success=False, output="Missing 'steps'.")
    from koda.workflows.store import get_workflow_store

    store = get_workflow_store()
    workflow = store.parse_workflow(name, steps, description=params.get("description", ""), user_id=ctx.user_id)
    if isinstance(workflow, str):
        return AgentToolResult(tool="workflow_create", success=False, output=workflow)
    store.save(workflow)
    return AgentToolResult(
        tool="workflow_create",
        success=True,
        output=f"Workflow '{name}' created with {len(workflow.steps)} steps.",
    )


async def _handle_workflow_run(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_workflow_available("workflow_run")
    if err:
        return err
    name = params.get("name", "")
    if not name:
        return AgentToolResult(tool="workflow_run", success=False, output="Missing 'name'.")
    from koda.workflows.engine import WorkflowEngine
    from koda.workflows.store import get_workflow_store

    store = get_workflow_store()
    workflow = store.get(name)
    if not workflow:
        return AgentToolResult(tool="workflow_run", success=False, output=f"Workflow '{name}' not found.")
    engine = WorkflowEngine()
    run = await engine.run(workflow, ctx)
    lines = [f"Workflow '{name}': {run.status}"]
    for sid, sr in run.step_results.items():
        status = "OK" if sr["success"] else "FAIL"
        if sr.get("skipped"):
            status = "SKIP"
        lines.append(f"  [{status}] {sid}: {sr['output'][:100]}")
    if run.error:
        lines.append(f"Error: {run.error}")
    return AgentToolResult(
        tool="workflow_run",
        success=run.status == "completed",
        output="\n".join(lines),
    )


async def _handle_workflow_list(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_workflow_available("workflow_list")
    if err:
        return err
    from koda.workflows.store import get_workflow_store

    workflows = get_workflow_store().list_all()
    if not workflows:
        return AgentToolResult(tool="workflow_list", success=True, output="No workflows.")
    lines = [f"Workflows ({len(workflows)}):"]
    for w in workflows:
        lines.append(f"  {w['name']} \u2014 {w['step_count']} steps \u2014 {w.get('description', '')}")
    return AgentToolResult(tool="workflow_list", success=True, output="\n".join(lines))


async def _handle_workflow_get(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_workflow_available("workflow_get")
    if err:
        return err
    name = params.get("name", "")
    if not name:
        return AgentToolResult(tool="workflow_get", success=False, output="Missing 'name'.")
    from koda.workflows.store import get_workflow_store

    workflow = get_workflow_store().get(name)
    if not workflow:
        return AgentToolResult(tool="workflow_get", success=False, output=f"Workflow '{name}' not found.")
    lines = [
        f"Workflow: {workflow.name}",
        f"Description: {workflow.description}",
        f"Steps ({len(workflow.steps)}):",
    ]
    for s in workflow.steps:
        cond = f" [if {s.condition}]" if s.condition else ""
        lines.append(f"  {s.id}: {s.tool}{cond} \u2192 {s.params}")
    return AgentToolResult(tool="workflow_get", success=True, output="\n".join(lines))


async def _handle_workflow_delete(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_workflow_available("workflow_delete")
    if err:
        return err
    name = params.get("name", "")
    if not name:
        return AgentToolResult(tool="workflow_delete", success=False, output="Missing 'name'.")
    from koda.workflows.store import get_workflow_store

    delete_err = get_workflow_store().delete(name)
    if delete_err:
        return AgentToolResult(tool="workflow_delete", success=False, output=delete_err)
    return AgentToolResult(tool="workflow_delete", success=True, output=f"Workflow '{name}' deleted.")


# Inter-agent communication handlers


async def _check_inter_agent_available(tool: str) -> AgentToolResult | None:
    if not INTER_AGENT_ENABLED:
        return AgentToolResult(
            tool=tool,
            success=False,
            output="Inter-agent communication not enabled. Set INTER_AGENT_ENABLED=true.",
        )
    return None


def _ctx_agent_id(ctx: ToolContext) -> str:
    from koda.config import AGENT_ID

    return ctx.executing_agent_id or AGENT_ID or "default"


async def _require_squad_thread_access(
    *,
    tool: str,
    ctx: ToolContext,
    thread_id: str,
    require_write: bool = False,
) -> AgentToolResult | None:
    from koda.squads import SquadAccessError, SquadResourceNotFoundError, get_squad_access_service

    service = get_squad_access_service()
    if service is None:
        return AgentToolResult(tool=tool, success=False, output="Squad access service unavailable.")
    try:
        await service.require_thread_access(
            thread_id=thread_id,
            agent_id=_ctx_agent_id(ctx),
            require_write=require_write,
        )
    except SquadResourceNotFoundError as exc:
        return AgentToolResult(tool=tool, success=False, output=str(exc))
    except SquadAccessError as exc:
        return AgentToolResult(tool=tool, success=False, output=f"Forbidden: {exc}")
    return None


async def _require_squad_task_access(
    *,
    tool: str,
    ctx: ToolContext,
    task_id: str,
    require_write: bool = False,
    coordinator_override: bool = False,
) -> AgentToolResult | None:
    from koda.squads import SquadAccessError, SquadResourceNotFoundError, get_squad_access_service

    service = get_squad_access_service()
    if service is None:
        return AgentToolResult(tool=tool, success=False, output="Squad access service unavailable.")
    try:
        await service.require_task_access(
            task_id=task_id,
            agent_id=_ctx_agent_id(ctx),
            require_write=require_write,
            coordinator_override=coordinator_override,
        )
    except SquadResourceNotFoundError as exc:
        return AgentToolResult(tool=tool, success=False, output=str(exc))
    except SquadAccessError as exc:
        return AgentToolResult(tool=tool, success=False, output=f"Forbidden: {exc}")
    return None


async def _handle_agent_send(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_inter_agent_available("agent_send")
    if err:
        return err
    to = params.get("to", "")
    message = params.get("message", "")
    if not to or not message:
        return AgentToolResult(tool="agent_send", success=False, output="Missing 'to' and 'message'.")
    if ctx.squad_thread_id:
        access_err = await _require_squad_thread_access(
            tool="agent_send",
            ctx=ctx,
            thread_id=ctx.squad_thread_id,
            require_write=True,
        )
        if access_err:
            return access_err
        from koda.squads import SquadAccessError, SquadResourceNotFoundError, get_squad_access_service

        service = get_squad_access_service()
        if service is None:
            return AgentToolResult(tool="agent_send", success=False, output="Squad access service unavailable.")
        try:
            await service.require_thread_access(thread_id=ctx.squad_thread_id, agent_id=to)
        except (SquadAccessError, SquadResourceNotFoundError) as exc:
            return AgentToolResult(tool="agent_send", success=False, output=f"Forbidden target: {exc}")

    from koda.agents import get_message_bus

    from_agent = _ctx_agent_id(ctx)
    log.info("inter_agent_communication", tool="agent_send", from_agent=from_agent, to_agent=to, user_id=ctx.user_id)
    _audit_blocked("agent_send", f"inter_agent:{from_agent}->{to}", user_id=ctx.user_id)
    msg_id = await get_message_bus().send(
        from_agent,
        to,
        message,
        {
            "thread_id": ctx.squad_thread_id,
            "squad_task_id": ctx.squad_task_id,
            "parent_message_id": ctx.parent_message_id,
            "delegation_chain": ctx.delegation_chain,
            "kind": "agent_text",
        },
    )
    if msg_id.startswith("Error"):
        return AgentToolResult(tool="agent_send", success=False, output=msg_id)
    return AgentToolResult(tool="agent_send", success=True, output=f"Message sent to '{to}'. ID: {msg_id}")


async def _handle_agent_receive(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_inter_agent_available("agent_receive")
    if err:
        return err
    timeout = min(int(params.get("timeout", 30)), 300)

    from koda.agents import get_message_bus
    from koda.config import AGENT_ID

    agent_id = ctx.executing_agent_id or AGENT_ID or "default"
    msg = await get_message_bus().receive(agent_id, timeout=timeout)
    if not msg:
        return AgentToolResult(
            tool="agent_receive",
            success=False,
            output=f"No message received (timeout: {timeout}s).",
        )
    await get_message_bus().ack(agent_id, msg.message_id)
    return AgentToolResult(
        tool="agent_receive",
        success=True,
        output=f"From: {msg.from_agent}\nType: {msg.message_type}\n\n{msg.content}",
    )


async def _handle_agent_delegate(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_inter_agent_available("agent_delegate")
    if err:
        return err
    to = params.get("to", "")
    task = params.get("task", "")
    if not to or not task:
        return AgentToolResult(tool="agent_delegate", success=False, output="Missing 'to' and 'task'.")
    if to in set(ctx.delegation_chain or []):
        return AgentToolResult(tool="agent_delegate", success=False, output=f"Delegation cycle detected for '{to}'.")
    if ctx.squad_thread_id:
        access_err = await _require_squad_thread_access(
            tool="agent_delegate",
            ctx=ctx,
            thread_id=ctx.squad_thread_id,
            require_write=True,
        )
        if access_err:
            return access_err
        from koda.squads import SquadAccessError, get_squad_access_service

        service = get_squad_access_service()
        if service is None:
            return AgentToolResult(tool="agent_delegate", success=False, output="Squad access service unavailable.")
        try:
            await service.require_thread_access(thread_id=ctx.squad_thread_id, agent_id=to)
        except SquadAccessError as exc:
            return AgentToolResult(tool="agent_delegate", success=False, output=f"Forbidden target: {exc}")
    timeout = min(int(params.get("timeout", 60)), 300)
    context = params.get("context", {})

    from koda.agents import get_message_bus
    from koda.agents.models import DelegationRequest

    from_agent = _ctx_agent_id(ctx)
    log.info(
        "inter_agent_communication",
        tool="agent_delegate",
        from_agent=from_agent,
        to_agent=to,
        user_id=ctx.user_id,
    )
    _audit_blocked("agent_delegate", f"inter_agent:{from_agent}->{to}", user_id=ctx.user_id)
    request = DelegationRequest(
        from_agent=from_agent,
        to_agent=to,
        task=task,
        context=context if isinstance(context, dict) else {},
        timeout=timeout,
        delegation_depth=len(ctx.delegation_chain or []),
        thread_id=ctx.squad_thread_id,
        parent_message_id=ctx.parent_message_id,
        squad_task_id=ctx.squad_task_id,
        correlation_id=ctx.squad_task_id or ctx.parent_message_id,
    )
    result = await get_message_bus().delegate(request)
    if not result.success:
        return AgentToolResult(tool="agent_delegate", success=False, output=f"Delegation failed: {result.error}")
    return AgentToolResult(
        tool="agent_delegate",
        success=True,
        output=f"Delegation to '{to}' completed:\n{result.result}",
    )


async def _handle_task(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_inter_agent_available("task")
    if err:
        return err
    from koda.services.child_runs import delegate_child_task_tool

    return cast(AgentToolResult, await delegate_child_task_tool(params, ctx))


async def _handle_agent_list_agents(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_inter_agent_available("agent_list_agents")
    if err:
        return err

    from koda.agents import get_message_bus

    agents = get_message_bus().list_agents()
    if not agents:
        return AgentToolResult(tool="agent_list_agents", success=True, output="No agents registered.")
    lines = [f"Known agents ({len(agents)}):"]
    for a in agents:
        lines.append(f"  {a['agent_id']} \u2014 inbox: {a['inbox_size']}/{a['inbox_max']}")
    return AgentToolResult(tool="agent_list_agents", success=True, output="\n".join(lines))


async def _handle_agent_broadcast(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_inter_agent_available("agent_broadcast")
    if err:
        return err
    message = params.get("message", "")
    if not message:
        return AgentToolResult(tool="agent_broadcast", success=False, output="Missing 'message'.")

    from koda.agents import get_message_bus
    from koda.config import AGENT_ID

    count = await get_message_bus().broadcast(AGENT_ID or "default", message)
    return AgentToolResult(tool="agent_broadcast", success=True, output=f"Broadcast sent to {count} agents.")


# Squad thread handlers


async def _handle_squad_thread_create(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_inter_agent_available("squad_thread_create")
    if err:
        return err
    workspace_id = params.get("workspace_id", "")
    squad_id = params.get("squad_id", "")
    title = params.get("title", "")
    if not workspace_id or not squad_id:
        return AgentToolResult(
            tool="squad_thread_create",
            success=False,
            output="Missing 'workspace_id' or 'squad_id'.",
        )

    from koda.squads import get_squad_thread_store

    store = get_squad_thread_store()
    if store is None:
        return AgentToolResult(
            tool="squad_thread_create",
            success=False,
            output="Squad thread store unavailable: POSTGRES_URL is not configured.",
        )

    raw_participants = params.get("participants", [])
    participants: list[tuple[str, str]] = []
    if isinstance(raw_participants, list):
        for entry in raw_participants:
            if isinstance(entry, dict):
                aid = entry.get("agent_id")
                role = entry.get("role", "worker")
                if isinstance(aid, str) and aid:
                    participants.append((aid, str(role)))

    coordinator = params.get("coordinator_agent_id")
    coord_id = coordinator if isinstance(coordinator, str) and coordinator else None

    try:
        thread = await store.create_thread(
            workspace_id=workspace_id,
            squad_id=squad_id,
            title=title or "",
            owner_user_id=ctx.user_id,
            coordinator_agent_id=coord_id,
            participants=participants,
        )
    except (ValueError, KeyError) as exc:
        return AgentToolResult(tool="squad_thread_create", success=False, output=f"Create failed: {exc}")

    member_count = len(participants) + (1 if coord_id else 0)
    return AgentToolResult(
        tool="squad_thread_create",
        success=True,
        output=f"Thread '{thread.id}' created (status={thread.status}, members={member_count}).",
        data={"thread_id": thread.id, "title": thread.title, "status": thread.status},
    )


async def _handle_squad_post(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_inter_agent_available("squad_post")
    if err:
        return err
    thread_id = params.get("thread_id", "")
    content = params.get("content", "")
    if not thread_id or not content:
        return AgentToolResult(tool="squad_post", success=False, output="Missing 'thread_id' or 'content'.")
    access_err = await _require_squad_thread_access(
        tool="squad_post",
        ctx=ctx,
        thread_id=thread_id,
        require_write=True,
    )
    if access_err:
        return access_err

    from koda.squads import get_squad_thread_store

    store = get_squad_thread_store()
    if store is None:
        return AgentToolResult(tool="squad_post", success=False, output="Squad thread store unavailable.")

    metadata = params.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    try:
        msg_id = await store.post_thread_message(
            thread_id=thread_id,
            from_agent=_ctx_agent_id(ctx),
            content=content,
            message_type="agent_text",
            metadata=metadata,
        )
    except (KeyError, ValueError) as exc:
        return AgentToolResult(tool="squad_post", success=False, output=f"Post failed: {exc}")

    return AgentToolResult(
        tool="squad_post",
        success=True,
        output=f"Posted to thread '{thread_id}' (msg-{msg_id}).",
        data={"thread_id": thread_id, "message_id": msg_id},
    )


def _parse_tool_deadline(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    raw = str(value or "").strip()
    if not raw:
        return None
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _normalize_tool_targets(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        agent_id = str(item or "").strip()
        key = agent_id.lower()
        if not agent_id or key in seen:
            continue
        seen.add(key)
        out.append(agent_id)
    return out[:8]


async def _handle_squad_reply(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_inter_agent_available("squad_reply")
    if err:
        return err
    thread_id = params.get("thread_id") or ctx.squad_thread_id
    content = str(params.get("content") or "").strip()
    if not thread_id or not content:
        return AgentToolResult(
            tool="squad_reply",
            success=False,
            output="Missing 'thread_id' (or current squad thread) and 'content'.",
        )
    access_err = await _require_squad_thread_access(
        tool="squad_reply",
        ctx=ctx,
        thread_id=str(thread_id),
        require_write=True,
    )
    if access_err:
        return access_err

    from koda.squads import (
        ThreadReplyError,
        dispatch_squad_turn,
        get_squad_thread_store,
        get_thread_reply_service,
        message_ref,
    )

    store = get_squad_thread_store()
    if store is None:
        return AgentToolResult(tool="squad_reply", success=False, output="Squad thread store unavailable.")
    reply_service = get_thread_reply_service(store)
    if reply_service is None:
        return AgentToolResult(tool="squad_reply", success=False, output="Thread reply service unavailable.")

    raw_metadata = params.get("metadata")
    metadata: dict[str, Any] = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
    reply_to = message_ref(params.get("reply_to_message_id") or ctx.parent_message_id)
    reply_kind = str(params.get("reply_kind") or "agent_reply").strip() or "agent_reply"
    target_agent_ids = _normalize_tool_targets(params.get("target_agent_ids"))
    deadline = None
    try:
        deadline = _parse_tool_deadline(params.get("requires_response_by"))
    except ValueError:
        return AgentToolResult(
            tool="squad_reply",
            success=False,
            output="reply.policy_denied: requires_response_by must be an ISO timestamp.",
        )
    from_agent = _ctx_agent_id(ctx)
    metadata.update(
        {
            "reply_contract_version": "thread_reply.v1",
            "reply_kind": reply_kind,
            "reply_to_message_id": reply_to,
            "source": "squad_reply",
        }
    )
    correlation_id = str(params.get("correlation_id") or ctx.delegation_request_id or "")
    if correlation_id:
        metadata["correlation_id"] = correlation_id
    idempotency_key = str(params.get("idempotency_key") or "").strip() or None
    message_type = "coordinator_synthesis" if reply_kind == "synthesis" else reply_kind
    try:
        msg_id = await store.post_thread_message(
            thread_id=str(thread_id),
            from_agent=from_agent,
            content=content,
            message_type=message_type,
            metadata=metadata,
            to_agent_ids=target_agent_ids,
            in_reply_to=reply_to,
            requires_response_by=deadline,
            idempotency_key=idempotency_key,
            payload={
                "markdown": content,
                "reply_kind": reply_kind,
                "target_agent_ids": target_agent_ids,
                "reply_to_message_id": reply_to,
            },
        )
        resolved = await reply_service.resolve_for_reply(
            thread_id=str(thread_id),
            reply_message_id=msg_id,
            from_agent=from_agent,
            in_reply_to=reply_to,
            correlation_id=correlation_id or None,
        )
        obligations = []
        if target_agent_ids:
            obligations = await reply_service.create_obligations(
                thread_id=str(thread_id),
                source_message_id=msg_id,
                target_agent_ids=target_agent_ids,
                source_agent_id=from_agent,
                requires_response_by=deadline,
                metadata={
                    "origin": "tool",
                    "reply_kind": reply_kind,
                    "reply_to_message_id": reply_to,
                    "correlation_id": f"reply:{thread_id}:{msg_id}",
                },
            )
            thread = await store.get_thread(str(thread_id))
            if thread is not None:
                for obligation in obligations:
                    await dispatch_squad_turn(
                        target_agent_id=obligation.target_agent_id,
                        thread=thread,
                        thread_store=store,
                        query_text=content,
                        parent_message_id=f"msg-{msg_id}",
                        metadata={
                            "from_agent": from_agent,
                            "source": "squad_reply",
                            "delivery_intent": "reply_required",
                            "reply_contract_version": "thread_reply.v1",
                            "reply_kind": reply_kind,
                            "reply_to_message_id": reply_to,
                            "correlation_id": obligation.obligation_key,
                        },
                        application=ctx.application,
                        user_id=ctx.user_id,
                        chat_id=ctx.chat_id,
                        delegation_chain=[*(ctx.delegation_chain or []), from_agent],
                        delegation_request_id=obligation.obligation_key,
                        delegation_origin_agent_id=from_agent,
                    )
        await store.notify_event(
            thread_id=str(thread_id),
            event_type="synthesis_created" if reply_kind == "synthesis" else "reply_added",
            data={
                "message_id": msg_id,
                "from_agent": from_agent,
                "in_reply_to": reply_to,
                "target_agent_ids": target_agent_ids,
            },
        )
    except ThreadReplyError as exc:
        return AgentToolResult(tool="squad_reply", success=False, output=f"{exc.code}: {exc.message}")
    except (KeyError, ValueError) as exc:
        return AgentToolResult(tool="squad_reply", success=False, output=f"Reply failed: {exc}")
    return AgentToolResult(
        tool="squad_reply",
        success=True,
        output=f"Reply posted to thread '{thread_id}' (msg-{msg_id}).",
        data={
            "thread_id": str(thread_id),
            "message_id": msg_id,
            "resolved_obligations": [item.to_dict() for item in resolved],
            "created_obligations": [item.to_dict() for item in obligations],
        },
        data_format="json",
    )


async def _handle_squad_request_input(params: dict, ctx: ToolContext) -> AgentToolResult:
    targets = _normalize_tool_targets(params.get("target_agent_ids"))
    question = str(params.get("question") or "").strip()
    if not targets or not question:
        return AgentToolResult(
            tool="squad_request_input",
            success=False,
            output="Missing 'target_agent_ids' or 'question'.",
        )
    reason = str(params.get("reason") or "").strip()
    urgency = str(params.get("urgency") or "").strip()
    content_parts = [question]
    if reason:
        content_parts.append(f"\nReason: {reason}")
    if urgency:
        content_parts.append(f"\nUrgency: {urgency}")
    result = await _handle_squad_reply(
        {
            "thread_id": params.get("thread_id"),
            "content": "\n".join(content_parts),
            "reply_to_message_id": params.get("parent_message_id") or ctx.parent_message_id,
            "target_agent_ids": targets,
            "reply_kind": "agent_request",
            "requires_response_by": params.get("requires_response_by"),
            "metadata": {"reason": reason, "urgency": urgency, "source": "squad_request_input"},
        },
        ctx,
    )
    result.tool = "squad_request_input"
    return result


async def _handle_squad_follow_up(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_inter_agent_available("squad_follow_up")
    if err:
        return err
    thread_id = params.get("thread_id") or ctx.squad_thread_id
    obligation_id = params.get("obligation_id")
    if not thread_id or obligation_id is None:
        return AgentToolResult(tool="squad_follow_up", success=False, output="Missing 'thread_id' or 'obligation_id'.")
    access_err = await _require_squad_thread_access(
        tool="squad_follow_up",
        ctx=ctx,
        thread_id=str(thread_id),
        require_write=True,
    )
    if access_err:
        return access_err
    from koda.squads import ThreadReplyError, get_squad_thread_store, get_thread_reply_service

    store = get_squad_thread_store()
    reply_service = get_thread_reply_service(store)
    if store is None or reply_service is None:
        return AgentToolResult(tool="squad_follow_up", success=False, output="Thread reply service unavailable.")
    note = str(params.get("note") or "").strip()
    actor_id = _ctx_agent_id(ctx)
    try:
        obligation = await reply_service.follow_up(
            thread_id=str(thread_id),
            obligation_id=int(obligation_id),
            actor_id=actor_id,
            note=note,
        )
        msg_id = await store.post_thread_message(
            thread_id=str(thread_id),
            from_agent=actor_id,
            content=note or f"Follow-up requested from {obligation.target_agent_id}.",
            message_type="agent_followup",
            metadata={
                "reply_contract_version": "thread_reply.v1",
                "reply_kind": "agent_followup",
                "obligation_id": obligation.id,
                "target_agent_id": obligation.target_agent_id,
                "source": "squad_follow_up",
            },
            to_agent_ids=[obligation.target_agent_id],
            in_reply_to=obligation.source_message_id,
            correlation_id=obligation.obligation_key,
        )
        await store.notify_event(
            thread_id=str(thread_id),
            event_type="reply_obligation_updated",
            data={"message_id": msg_id, "obligations": [obligation.to_dict()]},
        )
    except ThreadReplyError as exc:
        return AgentToolResult(tool="squad_follow_up", success=False, output=f"{exc.code}: {exc.message}")
    return AgentToolResult(
        tool="squad_follow_up",
        success=True,
        output=f"Follow-up sent for obligation {obligation.id}.",
        data=obligation.to_dict(),
        data_format="json",
    )


async def _handle_squad_synthesize(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_inter_agent_available("squad_synthesize")
    if err:
        return err
    thread_id = params.get("thread_id") or ctx.squad_thread_id
    content = str(params.get("content") or "").strip()
    if not thread_id or not content:
        return AgentToolResult(tool="squad_synthesize", success=False, output="Missing 'thread_id' or 'content'.")
    access_err = await _require_squad_thread_access(
        tool="squad_synthesize",
        ctx=ctx,
        thread_id=str(thread_id),
        require_write=True,
    )
    if access_err:
        return access_err
    from koda.squads import get_squad_thread_store

    store = get_squad_thread_store()
    if store is None:
        return AgentToolResult(tool="squad_synthesize", success=False, output="Squad thread store unavailable.")
    thread = await store.get_thread(str(thread_id))
    actor_id = _ctx_agent_id(ctx)
    if thread is None:
        return AgentToolResult(
            tool="squad_synthesize",
            success=False,
            output="reply.parent_not_found: thread not found.",
        )
    if thread.coordinator_agent_id and actor_id != thread.coordinator_agent_id:
        return AgentToolResult(
            tool="squad_synthesize",
            success=False,
            output="reply.synthesis_blocked: only the coordinator can finalize synthesis.",
        )
    if not thread.coordinator_agent_id:
        await store.post_thread_message(
            thread_id=str(thread_id),
            from_agent="system",
            content="[synthesis_blocked] thread has no coordinator",
            message_type="system_event",
            metadata={"event_type": "synthesis_blocked", "actor_id": actor_id},
        )
        return AgentToolResult(
            tool="squad_synthesize",
            success=False,
            output="reply.synthesis_blocked: thread has no coordinator.",
        )
    result = await _handle_squad_reply(
        {
            "thread_id": str(thread_id),
            "content": content,
            "reply_to_message_id": params.get("reply_to_message_id") or ctx.parent_message_id,
            "reply_kind": "synthesis",
            "metadata": {"synthesis_state": "final", **dict(params.get("metadata") or {})},
        },
        ctx,
    )
    result.tool = "squad_synthesize"
    return result


async def _handle_squad_thread_history(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_inter_agent_available("squad_thread_history")
    if err:
        return err
    thread_id = params.get("thread_id", "")
    if not thread_id:
        return AgentToolResult(tool="squad_thread_history", success=False, output="Missing 'thread_id'.")
    from koda.squads import SquadAccessError, SquadResourceNotFoundError, get_squad_access_service

    access_service = get_squad_access_service()
    if access_service is None:
        return AgentToolResult(tool="squad_thread_history", success=False, output="Squad access service unavailable.")
    try:
        access = await access_service.require_thread_access(thread_id=thread_id, agent_id=_ctx_agent_id(ctx))
    except SquadResourceNotFoundError as exc:
        return AgentToolResult(tool="squad_thread_history", success=False, output=str(exc))
    except SquadAccessError as exc:
        return AgentToolResult(tool="squad_thread_history", success=False, output=f"Forbidden: {exc}")
    limit = min(int(params.get("limit", 30)), 200)
    before_id = params.get("before_id")

    from koda.squads import get_squad_thread_store

    store = get_squad_thread_store()
    if store is None:
        return AgentToolResult(tool="squad_thread_history", success=False, output="Squad thread store unavailable.")

    try:
        messages = await store.thread_history(
            thread_id=thread_id,
            limit=limit,
            before_id=int(before_id) if before_id is not None else None,
            visible_after=None if access.is_coordinator else access.joined_at,
        )
    except (ValueError, KeyError) as exc:
        return AgentToolResult(tool="squad_thread_history", success=False, output=f"Read failed: {exc}")

    if not messages:
        return AgentToolResult(
            tool="squad_thread_history",
            success=True,
            output="(empty thread)",
            data={"messages": [], "thread_id": thread_id},
        )
    lines = [f"Thread '{thread_id}' — {len(messages)} message(s):"]
    for msg in messages:
        sender = msg["from"] or "?"
        snippet = (msg["content"] or "")[:200]
        lines.append(f"  [{msg['type']}] {sender}: {snippet}")
    return AgentToolResult(
        tool="squad_thread_history",
        success=True,
        output="\n".join(lines),
        data={"messages": messages, "thread_id": thread_id},
    )


# Squad task handlers


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


async def _handle_squad_task_create(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_inter_agent_available("squad_task_create")
    if err:
        return err
    thread_id = params.get("thread_id", "")
    title = params.get("title", "")
    if not thread_id or not title:
        return AgentToolResult(
            tool="squad_task_create",
            success=False,
            output="Missing 'thread_id' or 'title'.",
        )
    access_err = await _require_squad_thread_access(
        tool="squad_task_create",
        ctx=ctx,
        thread_id=thread_id,
        require_write=True,
    )
    if access_err:
        return access_err

    from koda.squads import get_squad_task_store

    store = get_squad_task_store()
    if store is None:
        return AgentToolResult(tool="squad_task_create", success=False, output="Squad task store unavailable.")

    try:
        task = await store.create_task(
            thread_id=thread_id,
            title=title,
            assigner_agent_id=_ctx_agent_id(ctx),
            description=str(params.get("description", "")),
            kind=str(params.get("kind", "")),
            parent_task_id=params.get("parent_task_id") or None,
            depends_on=_string_list(params.get("depends_on")),
            assigned_agent_id=params.get("assigned_agent_id") or None,
            acceptance_criteria=_string_list(params.get("acceptance_criteria")),
            deliverables_spec=list(params.get("deliverables_spec") or []),
            delegation_depth=int(params.get("delegation_depth", 0)),
            idempotency_key=params.get("idempotency_key") or None,
            metadata=params.get("metadata") if isinstance(params.get("metadata"), dict) else None,
        )
    except (ValueError, KeyError) as exc:
        return AgentToolResult(tool="squad_task_create", success=False, output=f"Create failed: {exc}")

    return AgentToolResult(
        tool="squad_task_create",
        success=True,
        output=f"Task '{task.id}' created (status={task.status}, assignee={task.assigned_agent_id or 'unassigned'}).",
        data={"task_id": task.id, "status": task.status, "version": task.version},
    )


async def _handle_squad_task_claim(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_inter_agent_available("squad_task_claim")
    if err:
        return err
    task_id = params.get("task_id", "")
    if not task_id:
        return AgentToolResult(tool="squad_task_claim", success=False, output="Missing 'task_id'.")
    ttl = min(int(params.get("ttl_seconds", 300)), 3600)
    coordinator_override = bool(params.get("coordinator_override", False))
    access_err = await _require_squad_task_access(
        tool="squad_task_claim",
        ctx=ctx,
        task_id=task_id,
        require_write=True,
        coordinator_override=coordinator_override,
    )
    if access_err:
        return access_err

    from koda.squads import TaskClaimConflictError, TaskNotFoundError, get_squad_task_store

    store = get_squad_task_store()
    if store is None:
        return AgentToolResult(tool="squad_task_claim", success=False, output="Squad task store unavailable.")

    try:
        task = await store.claim_task(
            task_id=task_id,
            agent_id=_ctx_agent_id(ctx),
            ttl_seconds=ttl,
            coordinator_override=coordinator_override,
        )
    except TaskNotFoundError:
        return AgentToolResult(tool="squad_task_claim", success=False, output=f"Task '{task_id}' not found.")
    except TaskClaimConflictError as exc:
        return AgentToolResult(tool="squad_task_claim", success=False, output=str(exc))
    except ValueError as exc:
        return AgentToolResult(tool="squad_task_claim", success=False, output=str(exc))

    return AgentToolResult(
        tool="squad_task_claim",
        success=True,
        output=f"Claimed '{task.id}' (token={task.claim_token}, expires={task.claim_expires_at}).",
        data={"task_id": task.id, "version": task.version, "claim_token": task.claim_token},
    )


async def _run_status_update(
    *,
    tool_name: str,
    params: dict,
    ctx: ToolContext,
    new_status: str | None = None,
    extra: dict[str, Any] | None = None,
) -> AgentToolResult:
    err = await _check_inter_agent_available(tool_name)
    if err:
        return err
    task_id = params.get("task_id", "")
    target_status = new_status or params.get("new_status", "")
    if not task_id or not target_status:
        return AgentToolResult(tool=tool_name, success=False, output="Missing 'task_id' or 'new_status'.")
    coordinator_override = bool(params.get("coordinator_override", False))
    access_err = await _require_squad_task_access(
        tool=tool_name,
        ctx=ctx,
        task_id=task_id,
        require_write=True,
        coordinator_override=coordinator_override,
    )
    if access_err:
        return access_err

    from koda.squads import (
        IllegalTransitionError,
        StaleVersionError,
        TaskDependencyError,
        TaskNotFoundError,
        TaskOwnershipError,
        get_squad_task_store,
    )

    store = get_squad_task_store()
    if store is None:
        return AgentToolResult(tool=tool_name, success=False, output="Squad task store unavailable.")

    extra = extra or {}
    expected_version = params.get("expected_version")
    metadata_patch = params.get("metadata_patch")
    try:
        task = await store.update_task_status(
            task_id=task_id,
            new_status=target_status,
            agent_id=_ctx_agent_id(ctx),
            expected_version=int(expected_version) if expected_version is not None else None,
            error_message=extra.get("error_message") or params.get("error_message"),
            result_summary=extra.get("result_summary") or params.get("result_summary"),
            deliverables=extra.get("deliverables") or _string_list(params.get("deliverables")) or None,
            metadata_patch=metadata_patch if isinstance(metadata_patch, dict) else None,
            coordinator_override=coordinator_override,
        )
    except TaskNotFoundError:
        return AgentToolResult(tool=tool_name, success=False, output=f"Task '{task_id}' not found.")
    except (IllegalTransitionError, ValueError) as exc:
        return AgentToolResult(tool=tool_name, success=False, output=f"Illegal transition: {exc}")
    except TaskDependencyError as exc:
        return AgentToolResult(tool=tool_name, success=False, output=f"Dependency blocked: {exc}")
    except StaleVersionError as exc:
        return AgentToolResult(tool=tool_name, success=False, output=f"Stale version: {exc}")
    except TaskOwnershipError as exc:
        return AgentToolResult(tool=tool_name, success=False, output=str(exc))

    return AgentToolResult(
        tool=tool_name,
        success=True,
        output=f"Task '{task.id}' -> {task.status} (version={task.version}).",
        data={"task_id": task.id, "status": task.status, "version": task.version},
    )


async def _handle_squad_task_update(params: dict, ctx: ToolContext) -> AgentToolResult:
    return await _run_status_update(tool_name="squad_task_update", params=params, ctx=ctx)


async def _handle_squad_task_complete(params: dict, ctx: ToolContext) -> AgentToolResult:
    deliverables = _string_list(params.get("deliverables"))
    return await _run_status_update(
        tool_name="squad_task_complete",
        params=params,
        ctx=ctx,
        new_status="done",
        extra={
            "result_summary": params.get("result_summary"),
            "deliverables": deliverables or None,
        },
    )


async def _handle_squad_task_escalate(params: dict, ctx: ToolContext) -> AgentToolResult:
    reason = params.get("reason", "")
    if not reason:
        return AgentToolResult(tool="squad_task_escalate", success=False, output="Missing 'reason'.")
    return await _run_status_update(
        tool_name="squad_task_escalate",
        params=params,
        ctx=ctx,
        new_status="escalated",
        extra={"error_message": reason},
    )


async def _handle_squad_context(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_inter_agent_available("squad_context")
    if err:
        return err
    thread_id = params.get("thread_id") or ctx.squad_thread_id
    if not thread_id:
        return AgentToolResult(
            tool="squad_context",
            success=False,
            output="Missing 'thread_id' (and ToolContext has no squad_thread_id).",
        )
    access_err = await _require_squad_thread_access(tool="squad_context", ctx=ctx, thread_id=thread_id)
    if access_err:
        return access_err
    transcript_limit = min(int(params.get("transcript_limit", 8)), 50)

    from koda.config import AGENT_ID
    from koda.squads import build_squad_context_block_default

    executing_agent = ctx.executing_agent_id or AGENT_ID or "default"
    delegation_chain = ctx.delegation_chain or None
    block = await build_squad_context_block_default(
        thread_id=thread_id,
        executing_agent_id=executing_agent,
        transcript_limit=transcript_limit,
        delegation_chain=delegation_chain,
    )
    if block is None:
        return AgentToolResult(
            tool="squad_context",
            success=False,
            output=f"Squad context unavailable for thread '{thread_id}' (thread missing or store not configured).",
        )
    return AgentToolResult(
        tool="squad_context",
        success=True,
        output=block,
        data={"thread_id": thread_id, "executing_agent_id": executing_agent},
    )


async def _handle_squad_dashboard_overview(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_inter_agent_available("squad_dashboard_overview")
    if err:
        return err

    from koda.squads import list_squad_overviews_default

    workspace_id = params.get("workspace_id") or None
    overviews = await list_squad_overviews_default(workspace_id=workspace_id)
    if overviews is None:
        return AgentToolResult(
            tool="squad_dashboard_overview",
            success=False,
            output="Squad dashboard unavailable: POSTGRES_URL is not configured.",
        )
    if not overviews:
        return AgentToolResult(
            tool="squad_dashboard_overview",
            success=True,
            output="(no active squads)",
            data={"overviews": [], "count": 0},
        )
    lines = [f"{len(overviews)} squad(s):"]
    payload: list[dict[str, Any]] = []
    for ov in overviews:
        threads = ov.thread_counts
        tasks = ov.task_counts
        coord = ov.coordinator_agent_id or "(none)"
        lines.append(
            f"  {ov.squad_id} (workspace={ov.workspace_id or '?'}, coord={coord}, "
            f"members={ov.member_count}, threads=open:{threads['open']}/paused:{threads['paused']}/"
            f"completed:{threads['completed']}, tasks=pending:{tasks['pending']}/"
            f"in_progress:{tasks['in_progress']}/done:{tasks['done']}, cost=${ov.total_cost_usd})"
        )
        payload.append(
            {
                "squad_id": ov.squad_id,
                "workspace_id": ov.workspace_id,
                "coordinator_agent_id": ov.coordinator_agent_id,
                "thread_counts": ov.thread_counts,
                "task_counts": ov.task_counts,
                "member_count": ov.member_count,
                "last_active_at": ov.last_active_at,
                "total_cost_usd": str(ov.total_cost_usd),
            }
        )
    return AgentToolResult(
        tool="squad_dashboard_overview",
        success=True,
        output="\n".join(lines),
        data={"overviews": payload, "count": len(payload)},
    )


async def _handle_squad_thread_overview(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_inter_agent_available("squad_thread_overview")
    if err:
        return err
    thread_id = params.get("thread_id") or ctx.squad_thread_id
    if not thread_id:
        return AgentToolResult(
            tool="squad_thread_overview",
            success=False,
            output="Missing 'thread_id' (and ToolContext has no squad_thread_id).",
        )
    access_err = await _require_squad_thread_access(tool="squad_thread_overview", ctx=ctx, thread_id=thread_id)
    if access_err:
        return access_err
    message_limit = min(max(int(params.get("message_limit", 30)), 1), 200)
    task_limit = min(max(int(params.get("task_limit", 30)), 1), 200)

    from koda.squads import get_thread_overview_default

    overview = await get_thread_overview_default(
        thread_id,
        message_limit=message_limit,
        task_limit=task_limit,
    )
    if overview is None:
        return AgentToolResult(
            tool="squad_thread_overview",
            success=False,
            output=f"Thread '{thread_id}' not found (or POSTGRES_URL is not configured).",
        )
    thread = overview.thread
    lines = [
        f"Thread: {thread.title or '(untitled)'} (status={thread.status})",
        f"Squad: {thread.squad_id} (workspace={thread.workspace_id})",
        f"Coordinator: {overview.coordinator_agent_id or '(none)'}",
        f"Members ({len(overview.participants)}): "
        + ", ".join(f"{p.agent_id}[{p.role}]" for p in overview.participants),
        f"Tasks: open={overview.open_task_count}, done={overview.done_task_count}, "
        f"active_listed={len(overview.active_tasks)}",
    ]
    if overview.recent_messages:
        lines.append(f"Recent messages ({len(overview.recent_messages)}):")
        for msg in overview.recent_messages[:8]:
            sender = msg.get("from") or "?"
            snippet = (msg.get("content") or "")[:160]
            lines.append(f"  [{msg.get('type')}] {sender}: {snippet}")
    if overview.active_tasks:
        lines.append("Active tasks:")
        for task in overview.active_tasks[:8]:
            owner = task.assigned_agent_id or "unassigned"
            lines.append(f"  [{task.status}] {task.id[:8]}… '{task.title}' — {owner}")
    return AgentToolResult(
        tool="squad_thread_overview",
        success=True,
        output="\n".join(lines),
        data={
            "thread_id": thread.id,
            "squad_id": thread.squad_id,
            "workspace_id": thread.workspace_id,
            "status": thread.status,
            "coordinator_agent_id": overview.coordinator_agent_id,
            "participants": [
                {"agent_id": p.agent_id, "role": p.role, "joined_at": p.joined_at} for p in overview.participants
            ],
            "recent_messages": overview.recent_messages,
            "active_tasks": [
                {
                    "id": t.id,
                    "title": t.title,
                    "status": t.status,
                    "assigned_agent_id": t.assigned_agent_id,
                    "version": t.version,
                }
                for t in overview.active_tasks
            ],
            "open_task_count": overview.open_task_count,
            "done_task_count": overview.done_task_count,
        },
    )


async def _handle_squad_artifact_list(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_inter_agent_available("squad_artifact_list")
    if err:
        return err
    thread_id = params.get("thread_id") or ctx.squad_thread_id
    if not thread_id:
        return AgentToolResult(
            tool="squad_artifact_list",
            success=False,
            output="Missing 'thread_id' (and ToolContext has no squad_thread_id).",
        )
    access_err = await _require_squad_thread_access(tool="squad_artifact_list", ctx=ctx, thread_id=thread_id)
    if access_err:
        return access_err
    from koda.squads import get_squad_artifact_store

    store = get_squad_artifact_store()
    if store is None:
        return AgentToolResult(tool="squad_artifact_list", success=False, output="Squad artifact store unavailable.")
    artifacts = await store.list_for_thread(thread_id=thread_id)
    if not artifacts:
        return AgentToolResult(
            tool="squad_artifact_list",
            success=True,
            output="(no artifacts)",
            data={"thread_id": thread_id, "artifacts": []},
        )
    lines = [f"Artifacts for thread '{thread_id}' ({len(artifacts)}):"]
    payload = []
    for artifact in artifacts:
        lines.append(
            f"  {artifact.artifact_id} v{artifact.version} [{artifact.kind or 'artifact'}] "
            f"owner={artifact.owner_agent_id} path={artifact.path_or_uri}"
        )
        payload.append(
            {
                "artifact_id": artifact.artifact_id,
                "thread_id": artifact.thread_id,
                "task_id": artifact.task_id,
                "owner_agent_id": artifact.owner_agent_id,
                "version": artifact.version,
                "kind": artifact.kind,
                "path_or_uri": artifact.path_or_uri,
                "visible_to_squad": artifact.visible_to_squad,
                "metadata": artifact.metadata,
            }
        )
    return AgentToolResult(
        tool="squad_artifact_list",
        success=True,
        output="\n".join(lines),
        data={"thread_id": thread_id, "artifacts": payload},
    )


async def _handle_squad_inbox_drain(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_inter_agent_available("squad_inbox_drain")
    if err:
        return err
    limit = min(max(int(params.get("limit", 20)), 1), 100)
    poll_timeout = max(float(params.get("poll_timeout", 0.05)), 0.0)

    from koda.agents import get_message_bus
    from koda.config import AGENT_ID

    bus = get_message_bus()
    agent_id = ctx.executing_agent_id or AGENT_ID or "default"
    drained: list[dict[str, Any]] = []
    while len(drained) < limit:
        msg = await bus.receive(agent_id, timeout=poll_timeout)
        if msg is None:
            break
        metadata = msg.metadata or {}
        drained.append(
            {
                "message_id": msg.message_id,
                "from_agent": msg.from_agent,
                "to_agent": msg.to_agent,
                "kind": metadata.get("kind") or msg.message_type,
                "content": msg.content,
                "thread_id": metadata.get("thread_id"),
                "squad_id": metadata.get("squad_id"),
                "telegram_chat_id": metadata.get("telegram_chat_id"),
                "telegram_message_thread_id": metadata.get("telegram_message_thread_id"),
                "from_user": metadata.get("from_user"),
                "metadata": metadata,
                "timestamp": msg.timestamp,
            }
        )
        await bus.ack(agent_id, msg.message_id)
    if not drained:
        return AgentToolResult(
            tool="squad_inbox_drain",
            success=True,
            output="(inbox empty)",
            data={"drained": [], "count": 0},
        )
    squad_inputs = [m for m in drained if m["kind"] == "squad_thread_input"]
    other = [m for m in drained if m["kind"] != "squad_thread_input"]
    lines = [f"Drained {len(drained)} message(s) ({len(squad_inputs)} squad_thread_input):"]
    for entry in drained:
        thread_hint = (entry["thread_id"] or "")[:8]
        sender = entry["from_user"] or entry["from_agent"] or "?"
        snippet = (entry["content"] or "")[:200]
        lines.append(f"  [{entry['kind']}] thread={thread_hint}… from={sender}: {snippet}")
    return AgentToolResult(
        tool="squad_inbox_drain",
        success=True,
        output="\n".join(lines),
        data={
            "drained": drained,
            "count": len(drained),
            "squad_inputs": squad_inputs,
            "other": other,
        },
    )


async def _handle_squad_telegram_post(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_inter_agent_available("squad_telegram_post")
    if err:
        return err
    thread_id = params.get("thread_id") or ctx.squad_thread_id
    content = params.get("content", "")
    if not thread_id or not content:
        return AgentToolResult(
            tool="squad_telegram_post",
            success=False,
            output="Missing 'thread_id' or 'content'.",
        )
    access_err = await _require_squad_thread_access(
        tool="squad_telegram_post",
        ctx=ctx,
        thread_id=thread_id,
        require_write=True,
    )
    if access_err:
        return access_err

    from koda.config import AGENT_NAME, AGENT_TOKEN
    from koda.squads import (
        TaskNotFoundError,  # noqa: F401  - imported for type-check parity
        get_outbound_bot,
        get_squad_thread_store,
        post_to_telegram_thread,
    )

    store = get_squad_thread_store()
    if store is None:
        return AgentToolResult(
            tool="squad_telegram_post",
            success=False,
            output="Squad thread store unavailable: POSTGRES_URL is not configured.",
        )
    thread = await store.get_thread(thread_id)
    if thread is None:
        return AgentToolResult(
            tool="squad_telegram_post",
            success=False,
            output=f"Thread '{thread_id}' not found.",
        )
    if thread.telegram_chat_id is None:
        return AgentToolResult(
            tool="squad_telegram_post",
            success=False,
            output="Thread has no telegram binding — use 'squad_post' for audit-only delivery.",
        )

    bot = ctx.bot
    if bot is None:
        if not AGENT_TOKEN:
            return AgentToolResult(
                tool="squad_telegram_post",
                success=False,
                output="No bot available and AGENT_TOKEN is not configured.",
            )
        bot = get_outbound_bot(AGENT_TOKEN)

    raw_label = params.get("agent_label")
    if isinstance(raw_label, str) and raw_label.strip():
        agent_label: str | None = raw_label.strip()
    else:
        agent_label = AGENT_NAME or _ctx_agent_id(ctx) or None

    metadata = {
        "agent_id": _ctx_agent_id(ctx),
        "agent_label": agent_label,
    }
    msg_id = await store.post_thread_message(
        thread_id=thread_id,
        from_agent=_ctx_agent_id(ctx),
        content=content,
        message_type="agent_text",
        metadata=metadata,
    )
    try:
        sent = await post_to_telegram_thread(bot, thread, content, agent_label=agent_label)
    except Exception as exc:
        log.exception("squad_telegram_post_send_failed", thread_id=thread_id)
        return AgentToolResult(
            tool="squad_telegram_post",
            success=False,
            output=(f"Persisted to thread audit (msg-{msg_id}) but Telegram send failed: {exc}"),
            data={"thread_id": thread_id, "message_id": msg_id, "telegram_sent": False},
        )
    telegram_message_id = getattr(sent, "message_id", None)
    return AgentToolResult(
        tool="squad_telegram_post",
        success=True,
        output=(f"Posted to thread '{thread_id}' (msg-{msg_id}; telegram_message_id={telegram_message_id})."),
        data={
            "thread_id": thread_id,
            "message_id": msg_id,
            "telegram_message_id": telegram_message_id,
            "telegram_sent": True,
        },
    )


async def _handle_squad_telegram_bind(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_inter_agent_available("squad_telegram_bind")
    if err:
        return err
    squad_id = params.get("squad_id", "")
    workspace_id = params.get("workspace_id", "")
    raw_chat = params.get("telegram_chat_id")
    if not squad_id or not workspace_id or raw_chat is None:
        return AgentToolResult(
            tool="squad_telegram_bind",
            success=False,
            output="Missing 'workspace_id', 'squad_id', or 'telegram_chat_id'.",
        )
    if not bool(params.get("is_forum", False)):
        return AgentToolResult(
            tool="squad_telegram_bind",
            success=False,
            output="Telegram squad binding requires a forum-enabled supergroup.",
        )
    try:
        chat_id = int(raw_chat)
    except (TypeError, ValueError):
        return AgentToolResult(
            tool="squad_telegram_bind",
            success=False,
            output="'telegram_chat_id' must be an integer.",
        )

    from koda.squads import TelegramBindingConflictError, get_telegram_binding_service

    service = get_telegram_binding_service()
    if service is None:
        return AgentToolResult(
            tool="squad_telegram_bind",
            success=False,
            output="Telegram binding service unavailable: POSTGRES_URL is not configured.",
        )
    raw_user = params.get("bound_by_user_id")
    bound_by = None
    if raw_user is not None:
        try:
            bound_by = int(raw_user)
        except (TypeError, ValueError):
            bound_by = None
    raw_metadata = params.get("metadata")
    metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
    metadata["workspace_id"] = str(workspace_id)
    try:
        binding = await service.bind(
            squad_id=squad_id,
            telegram_chat_id=chat_id,
            chat_title=str(params.get("chat_title", "")),
            is_forum=bool(params.get("is_forum", False)),
            bound_by_user_id=bound_by if bound_by is not None else ctx.user_id,
            force=bool(params.get("force", False)),
            metadata=metadata,
        )
    except TelegramBindingConflictError as exc:
        return AgentToolResult(tool="squad_telegram_bind", success=False, output=str(exc))
    except (ValueError, KeyError) as exc:
        return AgentToolResult(tool="squad_telegram_bind", success=False, output=f"Bind failed: {exc}")
    return AgentToolResult(
        tool="squad_telegram_bind",
        success=True,
        output=(f"Squad '{binding.squad_id}' bound to chat {binding.telegram_chat_id} (forum={binding.is_forum})."),
        data={
            "squad_id": binding.squad_id,
            "telegram_chat_id": binding.telegram_chat_id,
            "is_forum": binding.is_forum,
        },
    )


async def _handle_squad_telegram_unbind(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_inter_agent_available("squad_telegram_unbind")
    if err:
        return err
    squad_id = params.get("squad_id", "")
    if not squad_id:
        return AgentToolResult(tool="squad_telegram_unbind", success=False, output="Missing 'squad_id'.")

    from koda.squads import get_telegram_binding_service

    service = get_telegram_binding_service()
    if service is None:
        return AgentToolResult(
            tool="squad_telegram_unbind",
            success=False,
            output="Telegram binding service unavailable.",
        )
    removed = await service.unbind(squad_id=squad_id)
    if not removed:
        return AgentToolResult(
            tool="squad_telegram_unbind",
            success=True,
            output=f"Squad '{squad_id}' had no telegram binding.",
            data={"removed": False},
        )
    return AgentToolResult(
        tool="squad_telegram_unbind",
        success=True,
        output=f"Squad '{squad_id}' unbound from telegram.",
        data={"removed": True},
    )


async def _handle_squad_telegram_binding_get(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_inter_agent_available("squad_telegram_binding_get")
    if err:
        return err
    squad_id = params.get("squad_id") or None
    raw_chat = params.get("telegram_chat_id")
    if not squad_id and raw_chat is None:
        return AgentToolResult(
            tool="squad_telegram_binding_get",
            success=False,
            output="Provide 'squad_id' or 'telegram_chat_id'.",
        )

    from koda.squads import get_telegram_binding_service

    service = get_telegram_binding_service()
    if service is None:
        return AgentToolResult(
            tool="squad_telegram_binding_get",
            success=False,
            output="Telegram binding service unavailable.",
        )
    binding = None
    if squad_id:
        binding = await service.get_for_squad(squad_id)
    elif raw_chat is not None:
        try:
            chat_id = int(raw_chat)
        except (TypeError, ValueError):
            return AgentToolResult(
                tool="squad_telegram_binding_get",
                success=False,
                output="'telegram_chat_id' must be an integer.",
            )
        binding = await service.get_for_chat(chat_id)
    if binding is None:
        return AgentToolResult(
            tool="squad_telegram_binding_get",
            success=True,
            output="(no binding)",
            data={"binding": None},
        )
    return AgentToolResult(
        tool="squad_telegram_binding_get",
        success=True,
        output=(
            f"Squad '{binding.squad_id}' ↔ chat {binding.telegram_chat_id} "
            f"(forum={binding.is_forum}, title={binding.chat_title!r})."
        ),
        data={
            "squad_id": binding.squad_id,
            "telegram_chat_id": binding.telegram_chat_id,
            "chat_title": binding.chat_title,
            "is_forum": binding.is_forum,
            "bound_by_user_id": binding.bound_by_user_id,
            "bound_at": binding.bound_at,
        },
    )


async def _handle_squad_router_tick(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_inter_agent_available("squad_router_tick")
    if err:
        return err

    from koda.squads import get_squad_router

    router = get_squad_router()
    if router is None:
        return AgentToolResult(
            tool="squad_router_tick",
            success=False,
            output="Squad router unavailable: POSTGRES_URL is not configured.",
        )
    report = await router.sweep_once()
    if report.reverted_count == 0:
        return AgentToolResult(
            tool="squad_router_tick",
            success=True,
            output="Squad router tick: nothing expired.",
            data={"reverted_count": 0, "reverted": []},
        )
    lines = [f"Squad router tick: reverted {report.reverted_count} expired claim(s)."]
    for claim in report.expired_claims:
        prior = claim.previously_assigned_agent_id or "(unknown)"
        lines.append(f"  task {claim.task_id[:8]}… (prior: {prior}) -> pending [v{claim.version_after}]")
    return AgentToolResult(
        tool="squad_router_tick",
        success=True,
        output="\n".join(lines),
        data={
            "reverted_count": report.reverted_count,
            "reverted": [
                {
                    "task_id": c.task_id,
                    "thread_id": c.thread_id,
                    "previously_assigned_agent_id": c.previously_assigned_agent_id,
                    "version_after": c.version_after,
                }
                for c in report.expired_claims
            ],
        },
    )


async def _handle_squad_coordinator_elect(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_inter_agent_available("squad_coordinator_elect")
    if err:
        return err
    squad_id = params.get("squad_id", "")
    agent_id = params.get("agent_id", "")
    if not squad_id or not agent_id:
        return AgentToolResult(
            tool="squad_coordinator_elect",
            success=False,
            output="Missing 'squad_id' or 'agent_id'.",
        )

    from koda.config import AGENT_ID
    from koda.squads import (
        CoordinatorConflictError,
        CoordinatorEligibilityError,
        get_coordinator_service,
        get_squad_thread_store,
    )

    service = get_coordinator_service()
    if service is None:
        return AgentToolResult(
            tool="squad_coordinator_elect",
            success=False,
            output="Coordinator service unavailable: POSTGRES_URL is not configured.",
        )
    triggered_by = (
        (ctx.executing_agent_id if isinstance(ctx.executing_agent_id, str) else None) or AGENT_ID or "operator"
    )
    force_replace = bool(params.get("force_replace", False))
    reason = params.get("reason") if isinstance(params.get("reason"), str) else None
    try:
        from koda.control_plane.manager import get_control_plane_manager

        agent_spec = get_control_plane_manager().get_agent_spec(agent_id)
    except Exception as exc:
        return AgentToolResult(
            tool="squad_coordinator_elect",
            success=False,
            output=f"Election failed: unable to load real AgentSpec for {agent_id!r}: {exc}",
        )

    try:
        state = await service.elect(
            squad_id=squad_id,
            agent_id=agent_id,
            triggered_by=triggered_by,
            reason=reason,
            force_replace=force_replace,
            agent_spec=agent_spec,
            thread_store=get_squad_thread_store(),
        )
    except CoordinatorConflictError as exc:
        return AgentToolResult(tool="squad_coordinator_elect", success=False, output=str(exc))
    except CoordinatorEligibilityError as exc:
        return AgentToolResult(tool="squad_coordinator_elect", success=False, output=str(exc))
    except (ValueError, KeyError) as exc:
        return AgentToolResult(tool="squad_coordinator_elect", success=False, output=f"Election failed: {exc}")

    return AgentToolResult(
        tool="squad_coordinator_elect",
        success=True,
        output=f"Squad '{squad_id}' coordinator -> {state.coordinator_agent_id} (policy={state.election_policy}).",
        data={
            "squad_id": squad_id,
            "coordinator_agent_id": state.coordinator_agent_id,
            "election_policy": state.election_policy,
        },
    )


async def _handle_squad_coordinator_demote(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_inter_agent_available("squad_coordinator_demote")
    if err:
        return err
    squad_id = params.get("squad_id", "")
    if not squad_id:
        return AgentToolResult(tool="squad_coordinator_demote", success=False, output="Missing 'squad_id'.")

    from koda.config import AGENT_ID
    from koda.squads import CoordinatorNotFoundError, get_coordinator_service, get_squad_thread_store

    service = get_coordinator_service()
    if service is None:
        return AgentToolResult(
            tool="squad_coordinator_demote",
            success=False,
            output="Coordinator service unavailable.",
        )
    triggered_by = (
        (ctx.executing_agent_id if isinstance(ctx.executing_agent_id, str) else None) or AGENT_ID or "operator"
    )
    reason = params.get("reason") if isinstance(params.get("reason"), str) else None
    try:
        state = await service.demote(
            squad_id=squad_id,
            triggered_by=triggered_by,
            reason=reason,
            thread_store=get_squad_thread_store(),
        )
    except CoordinatorNotFoundError:
        return AgentToolResult(
            tool="squad_coordinator_demote",
            success=False,
            output=f"Squad '{squad_id}' has no active coordinator.",
        )
    return AgentToolResult(
        tool="squad_coordinator_demote",
        success=True,
        output=f"Squad '{squad_id}' coordinator demoted (now: none).",
        data={"squad_id": squad_id, "coordinator_agent_id": state.coordinator_agent_id},
    )


async def _handle_squad_coordinator_get(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_inter_agent_available("squad_coordinator_get")
    if err:
        return err
    squad_id = params.get("squad_id", "")
    if not squad_id:
        return AgentToolResult(tool="squad_coordinator_get", success=False, output="Missing 'squad_id'.")

    from koda.squads import get_coordinator_service

    service = get_coordinator_service()
    if service is None:
        return AgentToolResult(
            tool="squad_coordinator_get",
            success=False,
            output="Coordinator service unavailable.",
        )
    state = await service.current_coordinator(squad_id)
    history = await service.list_history(squad_id=squad_id, limit=int(params.get("history_limit", 5)))
    if state is None:
        head = f"Squad '{squad_id}': no coordinator state."
    else:
        head = (
            f"Squad '{squad_id}': coordinator={state.coordinator_agent_id or '(none)'} "
            f"policy={state.election_policy} elected_at={state.elected_at}"
        )
    lines = [head]
    if history:
        lines.append("History:")
        for h in history:
            lines.append(
                f"  [{h.created_at}] {h.event_type} {h.previous_coordinator_agent_id or '(none)'} "
                f"-> {h.coordinator_agent_id or '(none)'} (by {h.triggered_by_agent_id or 'system'})"
            )
    return AgentToolResult(
        tool="squad_coordinator_get",
        success=True,
        output="\n".join(lines),
        data={
            "squad_id": squad_id,
            "state": (
                {
                    "coordinator_agent_id": state.coordinator_agent_id,
                    "election_policy": state.election_policy,
                    "elected_at": state.elected_at,
                    "elected_by_agent_id": state.elected_by_agent_id,
                }
                if state is not None
                else None
            ),
            "history": [
                {
                    "id": h.id,
                    "event_type": h.event_type,
                    "coordinator_agent_id": h.coordinator_agent_id,
                    "previous_coordinator_agent_id": h.previous_coordinator_agent_id,
                    "triggered_by_agent_id": h.triggered_by_agent_id,
                    "reason": h.reason,
                    "created_at": h.created_at,
                }
                for h in history
            ],
        },
    )


async def _handle_squad_capabilities(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_inter_agent_available("squad_capabilities")
    if err:
        return err
    squad_id = params.get("squad_id", "")
    if not squad_id:
        return AgentToolResult(tool="squad_capabilities", success=False, output="Missing 'squad_id'.")
    if ctx.squad_thread_id:
        from koda.squads import SquadAccessError, get_squad_access_service

        access = get_squad_access_service()
        if access is None:
            return AgentToolResult(tool="squad_capabilities", success=False, output="Squad access service unavailable.")
        try:
            grant = await access.require_thread_access(thread_id=ctx.squad_thread_id, agent_id=_ctx_agent_id(ctx))
        except SquadAccessError as exc:
            return AgentToolResult(tool="squad_capabilities", success=False, output=f"Forbidden: {exc}")
        if grant.thread.squad_id != squad_id:
            return AgentToolResult(tool="squad_capabilities", success=False, output="Forbidden: squad mismatch.")

    from koda.squads import format_capability_block, get_capability_cache

    cache = get_capability_cache()
    if cache is None:
        return AgentToolResult(
            tool="squad_capabilities",
            success=False,
            output="Capability cache unavailable: POSTGRES_URL is not configured.",
        )
    summaries = await cache.list_for_squad(squad_id=squad_id)
    if not summaries:
        return AgentToolResult(
            tool="squad_capabilities",
            success=True,
            output=f"(no cached capabilities for squad '{squad_id}')",
            data={"summaries": [], "squad_id": squad_id},
        )
    exclude = params.get("exclude_agent_id") or None
    block = format_capability_block(summaries, exclude_agent_id=exclude if isinstance(exclude, str) else None)
    return AgentToolResult(
        tool="squad_capabilities",
        success=True,
        output=block,
        data={"summaries": [s.to_dict() for s in summaries], "squad_id": squad_id},
    )


async def _handle_squad_task_list(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_inter_agent_available("squad_task_list")
    if err:
        return err
    thread_id = params.get("thread_id") or None
    assigned_agent_id = params.get("assigned_agent_id") or None
    if not thread_id and not assigned_agent_id:
        return AgentToolResult(
            tool="squad_task_list",
            success=False,
            output="Provide 'thread_id' or 'assigned_agent_id'.",
        )
    if thread_id:
        access_err = await _require_squad_thread_access(tool="squad_task_list", ctx=ctx, thread_id=thread_id)
        if access_err:
            return access_err
    elif assigned_agent_id != _ctx_agent_id(ctx):
        return AgentToolResult(
            tool="squad_task_list",
            success=False,
            output="Forbidden: assigned_agent_id listing is limited to the current agent unless thread_id is provided.",
        )
    raw_status = params.get("status")
    status_filter: str | list[str] | None
    if isinstance(raw_status, list):
        status_filter = [str(s) for s in raw_status if s]
    elif isinstance(raw_status, str) and raw_status:
        status_filter = raw_status
    else:
        status_filter = None
    limit = min(int(params.get("limit", 50)), 500)

    from koda.squads import get_squad_task_store

    store = get_squad_task_store()
    if store is None:
        return AgentToolResult(tool="squad_task_list", success=False, output="Squad task store unavailable.")

    tasks = await store.list_tasks(
        thread_id=thread_id,
        assigned_agent_id=assigned_agent_id,
        status=status_filter,
        limit=limit,
    )
    if not tasks:
        return AgentToolResult(tool="squad_task_list", success=True, output="(no tasks)", data={"tasks": []})
    lines = [f"{len(tasks)} task(s):"]
    summary_data: list[dict[str, Any]] = []
    for task in tasks:
        owner = task.assigned_agent_id or "unassigned"
        lines.append(f"  [{task.status}] {task.id[:8]}… '{task.title}' — {owner}")
        summary_data.append(
            {
                "id": task.id,
                "title": task.title,
                "status": task.status,
                "assigned_agent_id": task.assigned_agent_id,
                "version": task.version,
            }
        )
    return AgentToolResult(
        tool="squad_task_list",
        success=True,
        output="\n".join(lines),
        data={"tasks": summary_data},
    )


# Webhook handlers


async def _check_webhook_available(tool: str) -> AgentToolResult | None:
    if not WEBHOOK_ENABLED:
        return AgentToolResult(tool=tool, success=False, output="Webhooks not enabled. Set WEBHOOK_ENABLED=true.")
    return None


async def _handle_webhook_register(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_webhook_available("webhook_register")
    if err:
        return err
    name = params.get("name", "")
    path = params.get("path", "")
    if not name or not path:
        return AgentToolResult(tool="webhook_register", success=False, output="Missing 'name' and 'path'.")
    secret = params.get("secret")
    from koda.services.webhook_manager import webhook_manager

    error = webhook_manager.register(name, path, secret)
    if error:
        return AgentToolResult(tool="webhook_register", success=False, output=error)
    return AgentToolResult(tool="webhook_register", success=True, output=f"Webhook '{name}' registered at {path}")


async def _handle_webhook_unregister(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_webhook_available("webhook_unregister")
    if err:
        return err
    name = params.get("name", "")
    if not name:
        return AgentToolResult(tool="webhook_unregister", success=False, output="Missing 'name'.")
    from koda.services.webhook_manager import webhook_manager

    error = webhook_manager.unregister(name)
    if error:
        return AgentToolResult(tool="webhook_unregister", success=False, output=error)
    return AgentToolResult(tool="webhook_unregister", success=True, output=f"Webhook '{name}' removed.")


async def _handle_webhook_list(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_webhook_available("webhook_list")
    if err:
        return err
    from koda.services.webhook_manager import webhook_manager

    hooks = webhook_manager.list_webhooks()
    if not hooks:
        return AgentToolResult(tool="webhook_list", success=True, output="No webhooks registered.")
    lines = [f"Registered webhooks ({len(hooks)}):"]
    for h in hooks:
        secret_info = " (secured)" if h["has_secret"] else ""
        lines.append(f"  {h['name']}: {h['path']}{secret_info} — {h['call_count']} calls")
    return AgentToolResult(tool="webhook_list", success=True, output="\n".join(lines), data=hooks, data_format="json")


async def _handle_event_wait(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_webhook_available("event_wait")
    if err:
        return err
    event_type = params.get("event_type", "")
    if not event_type:
        return AgentToolResult(tool="event_wait", success=False, output="Missing 'event_type'.")
    timeout = min(int(params.get("timeout", 60)), 300)
    from koda.services.webhook_manager import webhook_manager

    event = await webhook_manager.wait_for_event(event_type, timeout=timeout)
    if event is None:
        return AgentToolResult(tool="event_wait", success=False, output=f"Timeout ({timeout}s): no event received.")
    payload_str = json.dumps(event.payload, default=str)[:4000]
    return AgentToolResult(
        tool="event_wait",
        success=True,
        output=f"Event received: {event_type}\nPayload: {payload_str}",
        data={"event_type": event_type, "payload": event.payload},
        data_format="json",
    )


# Browser network interception handlers


async def _handle_browser_network_capture_start(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_network_capture_start")
    if err:
        return err
    url_pattern = params.get("url_pattern")
    from koda.services.browser_manager import browser_manager

    result = await browser_manager.start_network_capture(_browser_scope_id(ctx), url_pattern)
    success = not result.startswith("Error")
    return AgentToolResult(tool="browser_network_capture_start", success=success, output=result)


async def _handle_browser_network_capture_stop(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_network_capture_stop")
    if err:
        return err
    from koda.services.browser_manager import browser_manager

    result = await browser_manager.stop_network_capture(_browser_scope_id(ctx))
    success = not result.startswith("Error") and "No capture" not in result
    return AgentToolResult(tool="browser_network_capture_stop", success=success, output=result)


async def _handle_browser_network_requests(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_network_requests")
    if err:
        return err
    limit = int(params.get("limit", 50))
    filter_str = params.get("filter")
    from koda.services.browser_manager import browser_manager

    text, data = browser_manager.get_captured_requests(_browser_scope_id(ctx), limit=limit, filter_str=filter_str)
    success = not text.startswith("Error")
    return AgentToolResult(
        tool="browser_network_requests",
        success=success,
        output=text,
        metadata={"data": data},
        data=data,
        data_format="json",
    )


async def _handle_browser_network_mock(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_network_mock")
    if err:
        return err
    url_pattern = params.get("url_pattern", "")
    if not url_pattern:
        return AgentToolResult(tool="browser_network_mock", success=False, output="Missing 'url_pattern'.")
    response = params.get("response", {})
    status = int(response.get("status", 200)) if isinstance(response, dict) else 200
    body = str(response.get("body", "")) if isinstance(response, dict) else ""
    headers = response.get("headers") if isinstance(response, dict) else None
    from koda.services.browser_manager import browser_manager

    result = await browser_manager.mock_route(_browser_scope_id(ctx), url_pattern, status, body, headers)
    success = not result.startswith("Error")
    return AgentToolResult(tool="browser_network_mock", success=success, output=result)


# Browser session persistence handlers


async def _handle_browser_session_save(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_session_save")
    if err:
        return err
    name = params.get("name", "")
    if not name:
        return AgentToolResult(tool="browser_session_save", success=False, output="Missing 'name'.")
    from koda.services.browser_manager import browser_manager

    result = await browser_manager.save_session(_browser_scope_id(ctx), name)
    success = not result.startswith("Error")
    return AgentToolResult(tool="browser_session_save", success=success, output=result)


async def _handle_browser_session_restore(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_session_restore")
    if err:
        return err
    name = params.get("name", "")
    if not name:
        return AgentToolResult(tool="browser_session_restore", success=False, output="Missing 'name'.")
    from koda.services.browser_manager import browser_manager

    result = await browser_manager.restore_session(_browser_scope_id(ctx), name)
    success = not result.startswith("Error")
    return AgentToolResult(tool="browser_session_restore", success=success, output=result)


async def _handle_browser_session_list(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_browser_available("browser_session_list")
    if err:
        return err
    from koda.services.browser_manager import browser_manager

    text, data = browser_manager.list_sessions(_browser_scope_id(ctx))
    success = not text.startswith("Error")
    return AgentToolResult(tool="browser_session_list", success=success, output=text, data=data, data_format="json")


# Handler registry

_ToolHandler = Callable[[dict, ToolContext], Awaitable[AgentToolResult]]

_TOOL_HANDLERS: dict[str, _ToolHandler] = {
    "job_list": _handle_job_list,
    "job_get": _handle_job_get,
    "job_create": _handle_job_create,
    "job_update": _handle_job_update,
    "job_validate": _handle_job_validate,
    "job_activate": _handle_job_activate,
    "job_pause": _handle_job_pause,
    "job_resume": _handle_job_resume,
    "job_delete": _handle_job_delete,
    "job_run_now": _handle_job_run_now,
    "job_runs": _handle_job_runs,
    "web_search": _handle_web_search,
    "fetch_url": _handle_fetch_url,
    "http_request": _handle_http_request,
    "agent_set_workdir": _handle_set_workdir,
    "agent_get_status": _handle_get_status,
    "browser_navigate": _handle_browser_navigate,
    "browser_click": _handle_browser_click,
    "browser_type": _handle_browser_type,
    "browser_submit": _handle_browser_submit,
    "browser_screenshot": _handle_browser_screenshot,
    "browser_get_text": _handle_browser_get_text,
    "browser_get_elements": _handle_browser_get_elements,
    "browser_select": _handle_browser_select,
    "browser_scroll": _handle_browser_scroll,
    "browser_wait": _handle_browser_wait,
    "browser_back": _handle_browser_back,
    "browser_forward": _handle_browser_forward,
    "browser_hover": _handle_browser_hover,
    "browser_press_key": _handle_browser_press_key,
    "browser_cookies": _handle_browser_cookies,
    "browser_tab_open": _handle_browser_tab_open,
    "browser_tab_close": _handle_browser_tab_close,
    "browser_tab_switch": _handle_browser_tab_switch,
    "browser_tab_list": _handle_browser_tab_list,
    "browser_tab_compare": _handle_browser_tab_compare,
    "browser_execute_js": _handle_browser_execute_js,
    "browser_download": _handle_browser_download,
    "browser_upload": _handle_browser_upload,
    "browser_set_viewport": _handle_browser_set_viewport,
    "browser_pdf": _handle_browser_pdf,
    "script_save": _handle_script_save,
    "script_search": _handle_script_search,
    "script_list": _handle_script_list,
    "script_delete": _handle_script_delete,
    "cache_stats": _handle_cache_stats,
    "cache_clear": _handle_cache_clear,
    "snapshot_save": _handle_snapshot_save,
    "snapshot_restore": _handle_snapshot_restore,
    "snapshot_list": _handle_snapshot_list,
    "snapshot_diff": _handle_snapshot_diff,
    "snapshot_delete": _handle_snapshot_delete,
    "request_skill": _handle_request_skill,
    "image_generate": _handle_image_generate,
    "file_read": _handle_file_read,
    "file_write": _handle_file_write,
    "file_edit": _handle_file_edit,
    "file_list": _handle_file_list,
    "file_search": _handle_file_search,
    "file_grep": _handle_file_grep,
    "file_delete": _handle_file_delete,
    "file_move": _handle_file_move,
    "file_info": _handle_file_info,
    "shell_execute": _handle_shell_execute,
    "shell_bg": _handle_shell_bg,
    "shell_status": _handle_shell_status,
    "shell_kill": _handle_shell_kill,
    "shell_output": _handle_shell_output,
    "git_status": _handle_git_status,
    "git_diff": _handle_git_diff,
    "git_log": _handle_git_log,
    "git_commit": _handle_git_commit,
    "git_branch": _handle_git_branch,
    "git_checkout": _handle_git_checkout,
    "git_push": _handle_git_push,
    "git_pull": _handle_git_pull,
    "plugin_list": _handle_plugin_list,
    "plugin_info": _handle_plugin_info,
    "plugin_install": _handle_plugin_install,
    "plugin_uninstall": _handle_plugin_uninstall,
    "plugin_reload": _handle_plugin_reload,
    "workflow_create": _handle_workflow_create,
    "workflow_run": _handle_workflow_run,
    "workflow_list": _handle_workflow_list,
    "workflow_get": _handle_workflow_get,
    "workflow_delete": _handle_workflow_delete,
    "agent_send": _handle_agent_send,
    "agent_receive": _handle_agent_receive,
    "task": _handle_task,
    "agent_delegate": _handle_agent_delegate,
    "agent_list_agents": _handle_agent_list_agents,
    "agent_broadcast": _handle_agent_broadcast,
    "squad_thread_create": _handle_squad_thread_create,
    "squad_post": _handle_squad_post,
    "squad_reply": _handle_squad_reply,
    "squad_request_input": _handle_squad_request_input,
    "squad_follow_up": _handle_squad_follow_up,
    "squad_synthesize": _handle_squad_synthesize,
    "squad_thread_history": _handle_squad_thread_history,
    "squad_task_create": _handle_squad_task_create,
    "squad_task_claim": _handle_squad_task_claim,
    "squad_task_update": _handle_squad_task_update,
    "squad_task_complete": _handle_squad_task_complete,
    "squad_task_escalate": _handle_squad_task_escalate,
    "squad_task_list": _handle_squad_task_list,
    "squad_capabilities": _handle_squad_capabilities,
    "squad_context": _handle_squad_context,
    "squad_coordinator_elect": _handle_squad_coordinator_elect,
    "squad_coordinator_demote": _handle_squad_coordinator_demote,
    "squad_coordinator_get": _handle_squad_coordinator_get,
    "squad_router_tick": _handle_squad_router_tick,
    "squad_telegram_bind": _handle_squad_telegram_bind,
    "squad_telegram_unbind": _handle_squad_telegram_unbind,
    "squad_telegram_binding_get": _handle_squad_telegram_binding_get,
    "squad_telegram_post": _handle_squad_telegram_post,
    "squad_inbox_drain": _handle_squad_inbox_drain,
    "squad_dashboard_overview": _handle_squad_dashboard_overview,
    "squad_thread_overview": _handle_squad_thread_overview,
    "squad_artifact_list": _handle_squad_artifact_list,
    "webhook_register": _handle_webhook_register,
    "webhook_unregister": _handle_webhook_unregister,
    "webhook_list": _handle_webhook_list,
    "event_wait": _handle_event_wait,
    "browser_network_capture_start": _handle_browser_network_capture_start,
    "browser_network_capture_stop": _handle_browser_network_capture_stop,
    "browser_network_requests": _handle_browser_network_requests,
    "browser_network_mock": _handle_browser_network_mock,
    "browser_session_save": _handle_browser_session_save,
    "browser_session_restore": _handle_browser_session_restore,
    "browser_session_list": _handle_browser_session_list,
}
