"""Agent tool dispatcher: parses <agent_cmd> tags, executes tools, and formats results."""

import asyncio
import importlib
import json
import re
import time as _time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import cast

from koda.agent_contract import (
    evaluate_integration_grant,
    resolve_gws_action,
    resolve_integration_action,
)
from koda.config import (
    AGENT_RESOURCE_ACCESS_POLICY,
    AGENT_TOOL_TIMEOUT,
    ALLOWED_GIT_CMDS,
    BLOCKED_CONFLUENCE_PATTERN,
    BLOCKED_GWS_PATTERN,
    BLOCKED_JIRA_PATTERN,
    BLOCKED_SHELL_PATTERN,
    BROWSER_FEATURES_ENABLED,
    BROWSER_TOOL_TIMEOUT,
    CONFLUENCE_ENABLED,
    FILEOPS_BLOCKED_EXTENSIONS,
    FILEOPS_ENABLED,
    FILEOPS_MAX_READ_SIZE,
    GIT_ENABLED,
    GIT_META_CHARS,
    GWS_CREDENTIALS_FILE,
    GWS_ENABLED,
    INTER_AGENT_ENABLED,
    JIRA_ENABLED,
    MONGO_ENABLED,
    MYSQL_ENABLED,
    PLUGIN_SYSTEM_ENABLED,
    POSTGRES_ENABLED,
    POSTGRES_MAX_ROWS_CAP,
    POSTGRES_WRITE_ENABLED,
    REDIS_ENABLED,
    SHELL_ENABLED,
    SHELL_TIMEOUT,
    SNAPSHOT_ENABLED,
    SQLITE_ENABLED,
    STRUCTURED_DATA_OUTPUT_ENABLED,
    WEBHOOK_ENABLED,
    WORKFLOW_ENABLED,
)
from koda.knowledge.types import EffectiveExecutionPolicy
from koda.logging_config import get_logger
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
_REMOVED_NATIVE_DB_TOOLS = frozenset(
    {
        "sqlite_query",
        "sqlite_schema",
        "mongo_query",
        "db_query",
        "db_schema",
        "db_explain",
        "db_switch_env",
        "db_execute",
        "db_execute_plan",
        "db_transaction",
        "mysql_query",
        "mysql_schema",
        "redis_query",
    }
)

# Tools that modify state (require approval in supervised mode)
_WRITE_TOOLS = frozenset(
    {
        "cron_add",
        "cron_delete",
        "cron_toggle",
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
        "agent_delegate",
        "agent_broadcast",
    }
)

# Tools that are always read-only
_READ_TOOLS = frozenset(
    {
        "cron_list",
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


def _gws_env_overrides() -> dict[str, str]:
    if not GWS_CREDENTIALS_FILE:
        return {}
    return {
        "GWS_CREDENTIALS_FILE": GWS_CREDENTIALS_FILE,
        "GOOGLE_APPLICATION_CREDENTIALS": GWS_CREDENTIALS_FILE,
    }


@contextmanager
def _gws_env_context() -> Iterator[dict[str, str]]:
    from koda.config import AGENT_ID

    current_agent = str(AGENT_ID or "").strip().upper()
    if not current_agent:
        with nullcontext(_gws_env_overrides()) as env:
            yield env
        return

    from koda.services.core_connection_broker import get_core_connection_broker

    with get_core_connection_broker().materialize_cli_environment("gws", agent_id=current_agent) as (_resolved, env):
        yield env


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
    if tool.startswith("mysql_"):
        return "mysql"
    if tool.startswith("mongo_"):
        return "db"
    if tool.startswith("sqlite_"):
        return "db"
    if tool.startswith("redis_"):
        return "db"
    if tool.startswith("db_"):
        return "db"
    if tool in {"gws", "jira", "confluence"}:
        return "cli"
    if tool.startswith("browser_"):
        return "browser"
    if tool.startswith("cron_") or tool.startswith("job_"):
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
    if tool in {"agent_send", "agent_receive", "agent_delegate", "agent_list_agents", "agent_broadcast"}:
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
    if integration_id not in {"browser", "gws", "jira", "confluence"}:
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
    """Execute a single agent tool call with timeout and security checks."""
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
    if call.tool in _REMOVED_NATIVE_DB_TOOLS:
        return AgentToolResult(
            tool=call.tool,
            success=False,
            output=("Native database tools were removed from Koda. Configure and use a database MCP server instead."),
            metadata={"category": _infer_tool_category(call.tool), "mcp_only": True},
            started_at=started_at,
            completed_at=datetime.now(UTC).isoformat(),
        )

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
    if tool not in _TOOL_HANDLERS:
        return False
    resolution = resolve_integration_action(tool, params)
    return resolution.access_level != "read"


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


async def _handle_cron_list(params: dict, ctx: ToolContext) -> AgentToolResult:
    from koda.services.cron_store import list_cron_jobs

    jobs = list_cron_jobs(ctx.user_id)
    if not jobs:
        return AgentToolResult(tool="cron_list", success=True, output="No cron jobs found.")

    lines = []
    for job_id, expr, cmd, desc, enabled in jobs:
        status = "enabled" if enabled else "disabled"
        line = f"#{job_id}: {expr} → {cmd}"
        if desc:
            line += f" ({desc})"
        line += f" [{status}]"
        lines.append(line)
    data = [
        {"id": job_id, "expression": expr, "command": cmd, "description": desc, "enabled": enabled}
        for job_id, expr, cmd, desc, enabled in jobs
    ]
    return AgentToolResult(tool="cron_list", success=True, output="\n".join(lines), data=data, data_format="json")


async def _handle_cron_add(params: dict, ctx: ToolContext) -> AgentToolResult:
    expression = params.get("expression", "")
    command = params.get("command", "")
    description = params.get("description", "")

    if not expression or not command:
        return AgentToolResult(
            tool="cron_add",
            success=False,
            output="Missing required params: 'expression' and 'command'.",
        )

    # Validate cron expression
    try:
        croniter = importlib.import_module("croniter").croniter

        if not croniter.is_valid(expression):
            return AgentToolResult(
                tool="cron_add",
                success=False,
                output=f"Invalid cron expression: {expression}",
            )
    except ImportError:
        return AgentToolResult(
            tool="cron_add",
            success=False,
            output="croniter not installed — cannot validate cron expression.",
        )

    # Security: block dangerous commands
    if BLOCKED_SHELL_PATTERN.search(command):
        _audit_blocked("cron_add", "dangerous_shell_pattern", user_id=ctx.user_id)
        return AgentToolResult(
            tool="cron_add",
            success=False,
            output="Blocked: command contains a dangerous pattern.",
        )
    if GIT_META_CHARS.search(command):
        _audit_blocked("cron_add", "shell_meta_characters", user_id=ctx.user_id)
        return AgentToolResult(
            tool="cron_add",
            success=False,
            output="Blocked: command contains shell meta-characters.",
        )

    work_dir_validation = validate_work_dir(str(params.get("work_dir") or ctx.work_dir))
    if not work_dir_validation.ok:
        _audit_blocked("cron_add", "invalid_work_dir", user_id=ctx.user_id)
        return AgentToolResult(tool="cron_add", success=False, output=work_dir_validation.reason or "Blocked.")

    try:
        from koda.services.cron_store import create_cron_job

        auto_activate_after_validation = _coerce_bool(
            params.get("auto_activate_after_validation"),
            default=True,
        )
        job_id = create_cron_job(
            ctx.user_id,
            ctx.chat_id,
            expression,
            command,
            description,
            work_dir_validation.path,
            auto_activate_after_validation=auto_activate_after_validation,
        )
        return AgentToolResult(
            tool="cron_add",
            success=True,
            output=(
                f'Legacy cron job #{job_id} created in validation mode: "{expression}" → {command}. '
                + (
                    "A safe dry-run is running now and the job will activate automatically if it passes."
                    if auto_activate_after_validation
                    else f"Run /jobs activate {job_id} after the dry-run passes."
                )
            ),
        )
    except ValueError as e:
        return AgentToolResult(tool="cron_add", success=False, output=str(e))


async def _handle_cron_delete(params: dict, ctx: ToolContext) -> AgentToolResult:
    job_id = params.get("job_id")
    if job_id is None:
        return AgentToolResult(
            tool="cron_delete",
            success=False,
            output="Missing required param: 'job_id'.",
        )

    from koda.services.cron_store import cancel_cron_task, delete_cron_job

    try:
        job_id = int(job_id)
    except (TypeError, ValueError):
        return AgentToolResult(tool="cron_delete", success=False, output="'job_id' must be an integer.")
    if delete_cron_job(ctx.user_id, job_id):
        cancel_cron_task(job_id)
        return AgentToolResult(
            tool="cron_delete",
            success=True,
            output=f"Cron job #{job_id} deleted.",
        )
    return AgentToolResult(
        tool="cron_delete",
        success=False,
        output=f"Cron job #{job_id} not found or not owned by you.",
    )


async def _handle_cron_toggle(params: dict, ctx: ToolContext) -> AgentToolResult:
    job_id = params.get("job_id")
    enabled = params.get("enabled")
    if job_id is None or enabled is None:
        return AgentToolResult(
            tool="cron_toggle",
            success=False,
            output="Missing required params: 'job_id' and 'enabled'.",
        )

    from koda.services.cron_store import (
        cancel_cron_task,
        get_cron_job,
        schedule_cron_task,
        toggle_cron_job,
    )

    try:
        job_id = int(job_id)
    except (TypeError, ValueError):
        return AgentToolResult(tool="cron_toggle", success=False, output="'job_id' must be an integer.")
    if isinstance(enabled, str):
        enabled = enabled.lower() in ("true", "1", "yes")
    else:
        enabled = bool(enabled)

    if not toggle_cron_job(ctx.user_id, job_id, enabled):
        return AgentToolResult(
            tool="cron_toggle",
            success=False,
            output=f"Cron job #{job_id} not found or not owned by you.",
        )

    if enabled:
        job = get_cron_job(job_id)
        if job:
            schedule_cron_task(job_id, ctx.agent, ctx.chat_id, job[3], job[4], job[7] or ctx.work_dir)
    else:
        cancel_cron_task(job_id)

    state = "enabled" if enabled else "disabled"
    return AgentToolResult(
        tool="cron_toggle",
        success=True,
        output=f"Cron job #{job_id} {state}.",
    )


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
        if BLOCKED_SHELL_PATTERN.search(command) or GIT_META_CHARS.search(command):
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


async def _handle_gws(params: dict, ctx: ToolContext) -> AgentToolResult:
    if not GWS_ENABLED:
        return AgentToolResult(
            tool="gws",
            success=False,
            output="Google Workspace is not enabled.",
        )

    args = params.get("args", "")
    if not args:
        return AgentToolResult(
            tool="gws",
            success=False,
            output="Missing required param: 'args'.",
        )

    if BLOCKED_GWS_PATTERN and BLOCKED_GWS_PATTERN.search(args):
        _audit_blocked("gws", "blocked_gws_pattern", user_id=ctx.user_id)
        return AgentToolResult(
            tool="gws",
            success=False,
            output="Blocked: this GWS command is not allowed for safety reasons.",
        )
    resolution = resolve_gws_action(args)

    from koda.services.cli_runner import run_cli_command_detailed
    from koda.utils.approval import _execution_approved

    token = _execution_approved.set(True)
    try:
        with _gws_env_context() as env:
            command_result = await run_cli_command_detailed(
                "gws",
                args,
                ctx.work_dir,
                blocked_pattern=BLOCKED_GWS_PATTERN,
                timeout=AGENT_TOOL_TIMEOUT,
                env=env,
            )
    except RuntimeError as exc:
        return AgentToolResult(
            tool="gws",
            success=False,
            output=str(exc),
        )
    finally:
        _execution_approved.reset(token)

    success = not command_result.text.startswith(("Exit 1:", "Blocked:", "Error:", "Timeout"))
    return AgentToolResult(
        tool="gws",
        success=success,
        output=command_result.text,
        metadata={
            "category": "cli",
            "binary": command_result.binary,
            "args": command_result.args,
            "exit_code": command_result.exit_code,
            "timed_out": command_result.timed_out,
            "truncated": command_result.truncated,
            "action_id": resolution.action_id,
            "resource_method": resolution.resource_method,
        },
    )


async def _handle_jira(params: dict, ctx: ToolContext) -> AgentToolResult:
    if not JIRA_ENABLED:
        return AgentToolResult(
            tool="jira",
            success=False,
            output="Jira is not enabled.",
        )

    args = params.get("args", "")
    if not args:
        return AgentToolResult(
            tool="jira",
            success=False,
            output="Missing required param: 'args' (e.g. 'issues search --jql ...').",
        )

    if BLOCKED_JIRA_PATTERN and BLOCKED_JIRA_PATTERN.search(args):
        _audit_blocked("jira", "blocked_jira_pattern", user_id=ctx.user_id)
        return AgentToolResult(
            tool="jira",
            success=False,
            output="Blocked: this Jira command is not allowed for safety reasons.",
        )

    from koda.services.resilience import check_breaker, jira_breaker, record_failure, record_success

    err = check_breaker(jira_breaker)
    if err:
        return AgentToolResult(tool="jira", success=False, output=err)

    from koda.services.atlassian_client import get_jira_service, parse_atlassian_args
    from koda.utils.approval import _execution_approved

    try:
        resource, action, parsed_params = parse_atlassian_args(args)
    except ValueError as e:
        return AgentToolResult(tool="jira", success=False, output=str(e))

    token = _execution_approved.set(True)
    try:
        service = get_jira_service()
        result = await service.execute(resource, action, parsed_params)
    finally:
        _execution_approved.reset(token)

    success = not result.startswith("Exit 1:")
    if success:
        record_success(jira_breaker)
    else:
        record_failure(jira_breaker)
    return AgentToolResult(
        tool="jira",
        success=success,
        output=result,
        metadata={
            "category": "cli",
            "binary": "jira",
            "args": args,
            "resource": resource,
            "action": action,
            "params": parsed_params,
        },
    )


async def _handle_confluence(params: dict, ctx: ToolContext) -> AgentToolResult:
    if not CONFLUENCE_ENABLED:
        return AgentToolResult(
            tool="confluence",
            success=False,
            output="Confluence is not enabled.",
        )

    args = params.get("args", "")
    if not args:
        return AgentToolResult(
            tool="confluence",
            success=False,
            output="Missing required param: 'args' (e.g. 'pages search --cql ...').",
        )

    if BLOCKED_CONFLUENCE_PATTERN and BLOCKED_CONFLUENCE_PATTERN.search(args):
        _audit_blocked("confluence", "blocked_confluence_pattern", user_id=ctx.user_id)
        return AgentToolResult(
            tool="confluence",
            success=False,
            output="Blocked: this Confluence command is not allowed for safety reasons.",
        )

    from koda.services.resilience import check_breaker, confluence_breaker, record_failure, record_success

    err = check_breaker(confluence_breaker)
    if err:
        return AgentToolResult(tool="confluence", success=False, output=err)

    from koda.services.atlassian_client import get_confluence_service, parse_atlassian_args
    from koda.utils.approval import _execution_approved

    try:
        resource, action, parsed_params = parse_atlassian_args(args)
    except ValueError as e:
        return AgentToolResult(tool="confluence", success=False, output=str(e))

    token = _execution_approved.set(True)
    try:
        service = get_confluence_service()
        result = await service.execute(resource, action, parsed_params)
    finally:
        _execution_approved.reset(token)

    success = not result.startswith("Exit 1:")
    if success:
        record_success(confluence_breaker)
    else:
        record_failure(confluence_breaker)
    return AgentToolResult(
        tool="confluence",
        success=success,
        output=result,
        metadata={
            "category": "cli",
            "binary": "confluence",
            "args": args,
            "resource": resource,
            "action": action,
            "params": parsed_params,
        },
    )


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

    ctx.user_data["work_dir"] = validation.path
    return AgentToolResult(
        tool="agent_set_workdir",
        success=True,
        output=f"Working directory changed to: {validation.path}",
    )


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


# ---------------------------------------------------------------------------
# Browser tab handlers
# ---------------------------------------------------------------------------


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

    result = await browser_manager.upload_file(_browser_scope_id(ctx), selector, file_path)
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


# ---------------------------------------------------------------------------
# SQLite handlers
# ---------------------------------------------------------------------------


async def _handle_sqlite_query(params: dict, ctx: ToolContext) -> AgentToolResult:
    if not SQLITE_ENABLED:
        return AgentToolResult(
            tool="sqlite_query", success=False, output="SQLite not enabled. Set SQLITE_ENABLED=true."
        )
    sql = params.get("sql", "")
    db_path = params.get("db_path", "")
    if not sql or not db_path:
        return AgentToolResult(
            tool="sqlite_query", success=False, output="Missing required params: 'sql' and 'db_path'."
        )
    max_rows = params.get("max_rows", 100)
    try:
        max_rows = int(max_rows)
    except (TypeError, ValueError):
        return AgentToolResult(tool="sqlite_query", success=False, output="'max_rows' must be an integer.")
    if max_rows < 1:
        return AgentToolResult(tool="sqlite_query", success=False, output="'max_rows' must be at least 1.")

    from koda.services.sqlite_manager import get_sqlite_manager

    mgr = get_sqlite_manager()
    if not mgr.is_available:
        return AgentToolResult(
            tool="sqlite_query", success=False, output="SQLite not available (aiosqlite not installed)."
        )
    result = await mgr.query(sql, db_path, max_rows=max_rows)
    return AgentToolResult(
        tool="sqlite_query",
        success=not result.startswith("Error"),
        output=result,
        metadata={"category": "sqlite", "sql": sql, "db_path": db_path},
    )


async def _handle_sqlite_schema(params: dict, ctx: ToolContext) -> AgentToolResult:
    if not SQLITE_ENABLED:
        return AgentToolResult(
            tool="sqlite_schema", success=False, output="SQLite not enabled. Set SQLITE_ENABLED=true."
        )
    db_path = params.get("db_path", "")
    if not db_path:
        return AgentToolResult(tool="sqlite_schema", success=False, output="Missing required param: 'db_path'.")

    from koda.services.sqlite_manager import get_sqlite_manager

    mgr = get_sqlite_manager()
    if not mgr.is_available:
        return AgentToolResult(
            tool="sqlite_schema", success=False, output="SQLite not available (aiosqlite not installed)."
        )
    result = await mgr.get_schema(db_path, table=params.get("table"))
    return AgentToolResult(
        tool="sqlite_schema",
        success=not result.startswith("Error"),
        output=result,
        metadata={"category": "sqlite", "db_path": db_path, "table": params.get("table")},
    )


# ---------------------------------------------------------------------------
# MongoDB handlers
# ---------------------------------------------------------------------------


async def _handle_mongo_query(params: dict, ctx: ToolContext) -> AgentToolResult:
    if not MONGO_ENABLED:
        return AgentToolResult(
            tool="mongo_query",
            success=False,
            output="MongoDB not enabled. Set MONGO_ENABLED=true.",
        )
    database = params.get("database", "")
    collection = params.get("collection", "")
    if not database or not collection:
        return AgentToolResult(
            tool="mongo_query",
            success=False,
            output="Missing required params: 'database' and 'collection'.",
        )
    filter_doc = params.get("filter", {})
    limit = int(params.get("limit", 100))
    env = params.get("env")
    from koda.services.mongo_manager import get_mongo_manager

    mgr = get_mongo_manager()
    if not mgr.is_available:
        return AgentToolResult(
            tool="mongo_query",
            success=False,
            output="MongoDB not available (motor not installed).",
        )
    result = await mgr.query(database, collection, filter_doc, limit, env)
    return AgentToolResult(
        tool="mongo_query",
        success=not result.startswith("Error"),
        output=result,
        metadata={"category": "db", "database": database, "collection": collection, "env": env},
    )


# ---------------------------------------------------------------------------
# Database handlers
# ---------------------------------------------------------------------------


def _check_db_available(tool_name: str, env: str | None = None) -> AgentToolResult | None:
    """Return error result if PostgreSQL is not available, else None."""
    if not POSTGRES_ENABLED:
        return AgentToolResult(
            tool=tool_name, success=False, output="PostgreSQL is disabled. Set POSTGRES_ENABLED=true."
        )

    from koda.services.resilience import check_breaker, postgres_breaker

    err = check_breaker(postgres_breaker)
    if err:
        return AgentToolResult(tool=tool_name, success=False, output=err)

    from koda.services.db_manager import db_manager

    if not db_manager.is_available:
        return AgentToolResult(tool=tool_name, success=False, output="PostgreSQL is not connected.")
    if env and not db_manager.is_env_available(env):
        return AgentToolResult(
            tool=tool_name,
            success=False,
            output=f"Database env '{env}' is not available. Available: {', '.join(db_manager.available_envs)}",
        )
    return None


async def _handle_db_query(params: dict, ctx: ToolContext) -> AgentToolResult:
    env = str(params.get("env") or ctx.user_data.get("postgres_env") or "").strip().lower() or None
    err = _check_db_available("db_query", env)
    if err:
        return err
    sql = params.get("sql", "")
    if not sql:
        return AgentToolResult(tool="db_query", success=False, output="Missing required param: 'sql'.")

    max_rows = params.get("max_rows")
    if max_rows is not None:
        try:
            max_rows = int(max_rows)
        except (TypeError, ValueError):
            return AgentToolResult(
                tool="db_query",
                success=False,
                output="'max_rows' must be an integer.",
            )
        if max_rows < 1:
            return AgentToolResult(
                tool="db_query",
                success=False,
                output="'max_rows' must be at least 1.",
            )
        if max_rows > POSTGRES_MAX_ROWS_CAP:
            return AgentToolResult(
                tool="db_query",
                success=False,
                output=f"'max_rows' cannot exceed {POSTGRES_MAX_ROWS_CAP}.",
            )
    timeout = params.get("timeout")
    if timeout is not None:
        try:
            timeout = int(timeout)
        except (TypeError, ValueError):
            return AgentToolResult(tool="db_query", success=False, output="'timeout' must be an integer.")
        if timeout < 1:
            return AgentToolResult(tool="db_query", success=False, output="'timeout' must be at least 1.")

    from koda.services.db_manager import db_manager

    result = await db_manager.query(sql, timeout=timeout, max_rows=max_rows, env=env)
    success = not result.startswith("Error")
    return AgentToolResult(
        tool="db_query",
        success=success,
        output=result,
        metadata={
            "category": "db",
            "sql": sql,
            "env": env,
            "max_rows": max_rows,
            "timeout": timeout,
        },
    )


async def _handle_db_schema(params: dict, ctx: ToolContext) -> AgentToolResult:
    env = str(params.get("env") or ctx.user_data.get("postgres_env") or "").strip().lower() or None
    err = _check_db_available("db_schema", env)
    if err:
        return err
    table = params.get("table")
    timeout = params.get("timeout")
    if timeout is not None:
        try:
            timeout = int(timeout)
        except (TypeError, ValueError):
            return AgentToolResult(tool="db_schema", success=False, output="'timeout' must be an integer.")
        if timeout < 1:
            return AgentToolResult(tool="db_schema", success=False, output="'timeout' must be at least 1.")
    from koda.services.db_manager import db_manager

    result = await db_manager.get_schema(table, env=env, timeout=timeout)
    success = not result.startswith("Error")
    return AgentToolResult(
        tool="db_schema",
        success=success,
        output=result,
        metadata={
            "category": "db",
            "table": table,
            "env": env,
            "timeout": timeout,
        },
    )


async def _handle_db_explain(params: dict, ctx: ToolContext) -> AgentToolResult:
    env = str(params.get("env") or ctx.user_data.get("postgres_env") or "").strip().lower() or None
    err = _check_db_available("db_explain", env)
    if err:
        return err
    sql = params.get("sql", "")
    if not sql:
        return AgentToolResult(tool="db_explain", success=False, output="Missing required param: 'sql'.")
    analyze = params.get("analyze", False)
    if isinstance(analyze, str):
        analyze = analyze.lower() in ("true", "1", "yes")
    timeout = params.get("timeout")
    if timeout is not None:
        try:
            timeout = int(timeout)
        except (TypeError, ValueError):
            return AgentToolResult(tool="db_explain", success=False, output="'timeout' must be an integer.")
        if timeout < 1:
            return AgentToolResult(tool="db_explain", success=False, output="'timeout' must be at least 1.")
    from koda.services.db_manager import db_manager

    result = await db_manager.explain(sql, analyze=analyze, env=env, timeout=timeout)
    success = not result.startswith("Error")
    return AgentToolResult(
        tool="db_explain",
        success=success,
        output=result,
        metadata={
            "category": "db",
            "sql": sql,
            "env": env,
            "analyze": analyze,
            "timeout": timeout,
        },
    )


async def _handle_db_switch_env(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = _check_db_available("db_switch_env")
    if err:
        return err
    env = str(params.get("env") or "").lower()
    from koda.services.db_manager import db_manager

    if env not in db_manager.available_envs:
        return AgentToolResult(
            tool="db_switch_env",
            success=False,
            output=f"Unknown env '{env}'. Available: {', '.join(db_manager.available_envs)}",
        )
    ctx.user_data["postgres_env"] = env
    return AgentToolResult(tool="db_switch_env", success=True, output=f"Switched to {env}.")


# ---------------------------------------------------------------------------
# MySQL handlers
# ---------------------------------------------------------------------------


async def _handle_mysql_query(params: dict, ctx: ToolContext) -> AgentToolResult:
    if not MYSQL_ENABLED:
        return AgentToolResult(
            tool="mysql_query", success=False, output="MySQL is not enabled. Set MYSQL_ENABLED=true."
        )
    sql = params.get("sql", "")
    if not sql:
        return AgentToolResult(tool="mysql_query", success=False, output="Missing required param: 'sql'.")
    env = params.get("env")
    max_rows = int(params.get("max_rows", 100))
    from koda.services.mysql_manager import get_mysql_manager

    manager = get_mysql_manager()
    if not manager.is_available:
        return AgentToolResult(
            tool="mysql_query", success=False, output="MySQL is not available (aiomysql not installed)."
        )
    result = await manager.query(sql, env=env, max_rows=max_rows)
    success = not result.startswith("Error")
    return AgentToolResult(
        tool="mysql_query",
        success=success,
        output=result,
        metadata={"category": "mysql", "sql": sql, "env": env, "max_rows": max_rows},
    )


async def _handle_mysql_schema(params: dict, ctx: ToolContext) -> AgentToolResult:
    if not MYSQL_ENABLED:
        return AgentToolResult(tool="mysql_schema", success=False, output="MySQL is not enabled.")
    table = params.get("table")
    env = params.get("env")
    from koda.services.mysql_manager import get_mysql_manager

    manager = get_mysql_manager()
    if not manager.is_available:
        return AgentToolResult(tool="mysql_schema", success=False, output="MySQL is not available.")
    result = await manager.get_schema(table=table, env=env)
    success = not result.startswith("Error")
    return AgentToolResult(
        tool="mysql_schema",
        success=success,
        output=result,
        metadata={"category": "mysql", "table": table, "env": env},
    )


# ---------------------------------------------------------------------------
# Script Library handlers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Cache management handlers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Snapshot handlers
# ---------------------------------------------------------------------------


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


async def _handle_redis_query(params: dict, ctx: ToolContext) -> AgentToolResult:
    if not REDIS_ENABLED:
        return AgentToolResult(tool="redis_query", success=False, output="Redis not enabled. Set REDIS_ENABLED=true.")
    command = params.get("command", "")
    if not command:
        return AgentToolResult(tool="redis_query", success=False, output="Missing required param: 'command'.")
    args = params.get("args", [])
    env = params.get("env")
    from koda.services.redis_manager import get_redis_manager

    mgr = get_redis_manager()
    if not mgr.is_available:
        return AgentToolResult(
            tool="redis_query", success=False, output="Redis not available (redis package not installed)."
        )
    result = await mgr.execute(command, args, env)
    return AgentToolResult(tool="redis_query", success=not result.startswith("Error"), output=result)


async def _handle_request_skill(params: dict, ctx: ToolContext) -> AgentToolResult:
    """Resolve a skill by name/alias/query and return its full content with instruction."""
    from koda.skills._registry import get_shared_registry
    from koda.skills._selector import get_shared_selector
    from koda.skills._telemetry import emit_skill_invocation

    query = str(params.get("query", "")).strip()
    if not query:
        return AgentToolResult(
            tool="request_skill",
            success=False,
            output="Please specify a skill name or description. Use /skill to list available skills.",
        )

    registry = get_shared_registry()

    # Try exact match or alias first
    skill_id = registry.resolve_alias(query.lower().replace(" ", "-"))
    if not skill_id:
        skill_id = registry.resolve_alias(query.lower())

    skill = None
    if skill_id:
        skill = registry.get(skill_id)

    if skill is None:
        # Also try matching by canonical skill ID directly
        skill = registry.get(query.lower().replace(" ", "-"))
        if skill is None:
            skill = registry.get(query.lower())

    if skill is None:
        # Fall back to semantic search
        try:
            selector = get_shared_selector()
            matches = selector.select(query, max_skills=1)
            if matches and matches[0].composite_score >= 0.4:
                skill = matches[0].skill
        except Exception:
            pass

    if skill is None:
        available = ", ".join(sorted(registry.get_all().keys()))
        return AgentToolResult(
            tool="request_skill",
            success=False,
            output=f"No matching skill found for '{query}'. Available skills: {available}",
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


# ---------------------------------------------------------------------------
# File operations handlers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Shell tool handlers
# ---------------------------------------------------------------------------


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

    bg = bg_process_manager.get(handle_id)
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

    error = await bg_process_manager.kill(handle_id)
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

    bg = bg_process_manager.get(handle_id)
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


# ---------------------------------------------------------------------------
# Git tool handlers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Plugin handlers
# ---------------------------------------------------------------------------


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
    from pathlib import Path as P

    plugin_dir = P(path)
    manifest_path = plugin_dir / "plugin.yaml"
    from koda.plugins.manifest import parse_manifest
    from koda.plugins.validator import validate_manifest

    manifest = parse_manifest(manifest_path)
    if isinstance(manifest, str):
        return AgentToolResult(tool="plugin_install", success=False, output=manifest)
    errors = validate_manifest(manifest)
    if errors:
        return AgentToolResult(
            tool="plugin_install",
            success=False,
            output="Validation errors:\n" + "\n".join(f"  - {e}" for e in errors),
        )
    from koda.plugins import get_registry

    reg_err = get_registry().register(manifest)
    if reg_err:
        return AgentToolResult(tool="plugin_install", success=False, output=reg_err)
    return AgentToolResult(
        tool="plugin_install",
        success=True,
        output=f"Plugin '{manifest.name}' installed with {len(manifest.tools)} tools.",
    )


async def _handle_plugin_uninstall(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_plugin_available("plugin_uninstall")
    if err:
        return err
    name = params.get("name", "")
    if not name:
        return AgentToolResult(tool="plugin_uninstall", success=False, output="Missing required param: 'name'.")
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
    from koda.plugins import get_registry

    reload_err = get_registry().reload(name)
    if reload_err:
        return AgentToolResult(tool="plugin_reload", success=False, output=reload_err)
    return AgentToolResult(tool="plugin_reload", success=True, output=f"Plugin '{name}' reloaded.")


# ---------------------------------------------------------------------------
# Workflow handlers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Inter-agent communication handlers
# ---------------------------------------------------------------------------


async def _check_inter_agent_available(tool: str) -> AgentToolResult | None:
    if not INTER_AGENT_ENABLED:
        return AgentToolResult(
            tool=tool,
            success=False,
            output="Inter-agent communication not enabled. Set INTER_AGENT_ENABLED=true.",
        )
    return None


async def _handle_agent_send(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = await _check_inter_agent_available("agent_send")
    if err:
        return err
    to = params.get("to", "")
    message = params.get("message", "")
    if not to or not message:
        return AgentToolResult(tool="agent_send", success=False, output="Missing 'to' and 'message'.")

    from koda.agents import get_message_bus
    from koda.config import AGENT_ID

    log.info("inter_agent_communication", tool="agent_send", from_agent=AGENT_ID, to_agent=to, user_id=ctx.user_id)
    _audit_blocked("agent_send", f"inter_agent:{AGENT_ID or 'default'}->{to}", user_id=ctx.user_id)
    msg_id = await get_message_bus().send(AGENT_ID or "default", to, message)
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

    msg = await get_message_bus().receive(AGENT_ID or "default", timeout=timeout)
    if not msg:
        return AgentToolResult(
            tool="agent_receive",
            success=False,
            output=f"No message received (timeout: {timeout}s).",
        )
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
    timeout = min(int(params.get("timeout", 60)), 300)
    context = params.get("context", {})

    from koda.agents import get_message_bus
    from koda.agents.models import DelegationRequest
    from koda.config import AGENT_ID

    log.info("inter_agent_communication", tool="agent_delegate", from_agent=AGENT_ID, to_agent=to, user_id=ctx.user_id)
    _audit_blocked("agent_delegate", f"inter_agent:{AGENT_ID or 'default'}->{to}", user_id=ctx.user_id)
    request = DelegationRequest(
        from_agent=AGENT_ID or "default",
        to_agent=to,
        task=task,
        context=context if isinstance(context, dict) else {},
        timeout=timeout,
    )
    result = await get_message_bus().delegate(request)
    if not result.success:
        return AgentToolResult(tool="agent_delegate", success=False, output=f"Delegation failed: {result.error}")
    return AgentToolResult(
        tool="agent_delegate",
        success=True,
        output=f"Delegation to '{to}' completed:\n{result.result}",
    )


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


# ---------------------------------------------------------------------------
# Webhook handlers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Database write handlers
# ---------------------------------------------------------------------------


async def _handle_db_execute(params: dict, ctx: ToolContext) -> AgentToolResult:
    if not POSTGRES_WRITE_ENABLED:
        return AgentToolResult(
            tool="db_execute",
            success=False,
            output="Database write not enabled. Set POSTGRES_WRITE_ENABLED=true.",
        )
    if not POSTGRES_ENABLED:
        return AgentToolResult(tool="db_execute", success=False, output="Database not enabled.")
    sql = params.get("sql", "")
    if not sql:
        return AgentToolResult(tool="db_execute", success=False, output="Missing 'sql'.")
    env = params.get("env") or ctx.user_data.get("postgres_env")
    sql_params = params.get("params")
    from koda.services.db_manager import db_manager

    result = await db_manager.execute_write(sql, params=sql_params, env=env)
    if result.get("error"):
        return AgentToolResult(tool="db_execute", success=False, output=result["error"])
    output = f"Executed on {result['env']}:\n{result['command']}\nAffected rows: {result['affected_rows']}"
    return AgentToolResult(tool="db_execute", success=True, output=output, data=result, data_format="json")


async def _handle_db_execute_plan(params: dict, ctx: ToolContext) -> AgentToolResult:
    if not POSTGRES_WRITE_ENABLED:
        return AgentToolResult(tool="db_execute_plan", success=False, output="Database write not enabled.")
    if not POSTGRES_ENABLED:
        return AgentToolResult(tool="db_execute_plan", success=False, output="Database not enabled.")
    sql = params.get("sql", "")
    if not sql:
        return AgentToolResult(tool="db_execute_plan", success=False, output="Missing 'sql'.")
    env = params.get("env") or ctx.user_data.get("postgres_env")
    from koda.services.db_manager import db_manager

    result = await db_manager.explain_write(sql, env=env)
    if result.get("error"):
        return AgentToolResult(tool="db_execute_plan", success=False, output=result["error"])
    return AgentToolResult(tool="db_execute_plan", success=True, output=f"EXPLAIN:\n{result['plan']}")


async def _handle_db_transaction(params: dict, ctx: ToolContext) -> AgentToolResult:
    if not POSTGRES_WRITE_ENABLED:
        return AgentToolResult(tool="db_transaction", success=False, output="Database write not enabled.")
    if not POSTGRES_ENABLED:
        return AgentToolResult(tool="db_transaction", success=False, output="Database not enabled.")
    statements = params.get("statements", [])
    if not statements or not isinstance(statements, list):
        return AgentToolResult(tool="db_transaction", success=False, output="Missing 'statements' (list).")
    env = params.get("env") or ctx.user_data.get("postgres_env")
    from koda.services.db_manager import db_manager

    result = await db_manager.execute_transaction(statements, env=env)
    if result.get("error"):
        return AgentToolResult(tool="db_transaction", success=False, output=result["error"])
    lines = [f"Transaction on {result['env']}: {len(result['results'])} statements"]
    for r in result["results"]:
        lines.append(f"  {r['command']} ({r['affected_rows']} rows)")
    return AgentToolResult(
        tool="db_transaction", success=True, output="\n".join(lines), data=result, data_format="json"
    )


# ---------------------------------------------------------------------------
# Browser network interception handlers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Browser session persistence handlers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

_ToolHandler = Callable[[dict, ToolContext], Awaitable[AgentToolResult]]

_TOOL_HANDLERS: dict[str, _ToolHandler] = {
    "cron_list": _handle_cron_list,
    "cron_add": _handle_cron_add,
    "cron_delete": _handle_cron_delete,
    "cron_toggle": _handle_cron_toggle,
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
    "gws": _handle_gws,
    "jira": _handle_jira,
    "confluence": _handle_confluence,
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
    "sqlite_query": _handle_sqlite_query,
    "sqlite_schema": _handle_sqlite_schema,
    "mongo_query": _handle_mongo_query,
    "db_query": _handle_db_query,
    "db_schema": _handle_db_schema,
    "db_explain": _handle_db_explain,
    "db_switch_env": _handle_db_switch_env,
    "mysql_query": _handle_mysql_query,
    "mysql_schema": _handle_mysql_schema,
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
    "redis_query": _handle_redis_query,
    "request_skill": _handle_request_skill,
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
    "agent_delegate": _handle_agent_delegate,
    "agent_list_agents": _handle_agent_list_agents,
    "agent_broadcast": _handle_agent_broadcast,
    "webhook_register": _handle_webhook_register,
    "webhook_unregister": _handle_webhook_unregister,
    "webhook_list": _handle_webhook_list,
    "event_wait": _handle_event_wait,
    "db_execute": _handle_db_execute,
    "db_execute_plan": _handle_db_execute_plan,
    "db_transaction": _handle_db_transaction,
    "browser_network_capture_start": _handle_browser_network_capture_start,
    "browser_network_capture_stop": _handle_browser_network_capture_stop,
    "browser_network_requests": _handle_browser_network_requests,
    "browser_network_mock": _handle_browser_network_mock,
    "browser_session_save": _handle_browser_session_save,
    "browser_session_restore": _handle_browser_session_restore,
    "browser_session_list": _handle_browser_session_list,
}
