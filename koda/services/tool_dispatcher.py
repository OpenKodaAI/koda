"""Agent tool dispatcher: parses <agent_cmd> tags, executes tools, and formats results."""

import asyncio
import importlib
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from koda.agent_contract import normalize_string_list, resolve_allowed_tool_ids
from koda.config import (
    AGENT_ALLOWED_TOOLS,
    AGENT_TOOL_POLICY,
    AGENT_TOOL_TIMEOUT,
    BLOCKED_CONFLUENCE_PATTERN,
    BLOCKED_GWS_PATTERN,
    BLOCKED_JIRA_PATTERN,
    BLOCKED_SHELL_PATTERN,
    BROWSER_FEATURES_ENABLED,
    BROWSER_TOOL_TIMEOUT,
    CONFLUENCE_ENABLED,
    GIT_META_CHARS,
    GWS_CREDENTIALS_FILE,
    GWS_ENABLED,
    JIRA_ENABLED,
    POSTGRES_ENABLED,
    POSTGRES_MAX_ROWS_CAP,
    POSTGRES_QUERY_TIMEOUT,
)
from koda.logging_config import get_logger
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

# Tools that modify state (require approval in supervised mode)
_WRITE_TOOLS = frozenset(
    {
        "cron_add",
        "cron_delete",
        "cron_toggle",
        "job_create",
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
        "db_switch_env",
        "script_save",
        "script_delete",
        "cache_clear",
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
        "db_query",
        "db_schema",
        "db_explain",
        "script_search",
        "script_list",
        "cache_stats",
    }
)


def _configured_allowed_tool_ids() -> set[str]:
    feature_flags = {
        "browser": BROWSER_FEATURES_ENABLED,
        "postgres": POSTGRES_ENABLED,
        "jira": JIRA_ENABLED,
        "confluence": CONFLUENCE_ENABLED,
        "gws": GWS_ENABLED,
    }
    if AGENT_TOOL_POLICY:
        policy = AGENT_TOOL_POLICY
    elif AGENT_ALLOWED_TOOLS:
        policy = {"allowed_tool_ids": sorted(AGENT_ALLOWED_TOOLS)}
    else:
        policy = {}
    allowed = resolve_allowed_tool_ids(policy, feature_flags=feature_flags)
    return set(allowed)


def _has_explicit_tool_subset() -> bool:
    if AGENT_TOOL_POLICY and normalize_string_list(AGENT_TOOL_POLICY.get("allowed_tool_ids")):
        return True
    return bool(AGENT_ALLOWED_TOOLS)


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
    if tool.startswith("db_"):
        return "db"
    if tool in {"gws", "jira", "confluence"}:
        return "cli"
    if tool.startswith("browser_"):
        return "browser"
    if tool.startswith("cron_") or tool.startswith("job_"):
        return "ops"
    return "tool"


async def execute_tool(call: AgentToolCall, ctx: ToolContext) -> AgentToolResult:
    """Execute a single agent tool call with timeout and security checks."""
    import time

    from koda.config import AGENT_ID
    from koda.services import audit
    from koda.services.metrics import TOOL_EXECUTIONS
    from koda.services.runtime import get_runtime_controller

    _agent_id_label = AGENT_ID or "default"
    started_at = datetime.now(UTC).isoformat()
    try:
        runtime = get_runtime_controller()
    except RuntimeError:
        runtime = None
    allowed_tool_ids = _configured_allowed_tool_ids()

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
        TOOL_EXECUTIONS.labels(agent_id=_agent_id_label, tool_name=call.tool, status="unknown").inc()
        return AgentToolResult(
            tool=call.tool,
            success=False,
            output=f"Unknown tool: {call.tool}",
            metadata={"category": _infer_tool_category(call.tool)},
            started_at=started_at,
            completed_at=datetime.now(UTC).isoformat(),
        )

    if _has_explicit_tool_subset() and allowed_tool_ids and call.tool not in allowed_tool_ids:
        return AgentToolResult(
            tool=call.tool,
            success=False,
            output=f"Tool '{call.tool}' is not enabled for this agent.",
            metadata={
                "category": _infer_tool_category(call.tool),
                "policy_blocked": True,
                "allowed_tool_ids": sorted(allowed_tool_ids),
            },
            started_at=started_at,
            completed_at=datetime.now(UTC).isoformat(),
        )

    _start = time.monotonic()
    try:
        await _publish_runtime_event("command.started", payload={"tool": call.tool, "params": call.params})
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
        elif call.tool.startswith("db_"):
            timeout = POSTGRES_QUERY_TIMEOUT + 5  # query timeout + margin
        else:
            timeout = AGENT_TOOL_TIMEOUT
        result = await asyncio.wait_for(
            handler(call.params, ctx),
            timeout=timeout,
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
            **result.metadata,
        }
        audit.emit_task_lifecycle(
            "task.tool_executed",
            user_id=ctx.user_id,
            task_id=ctx.task_id,
            duration_ms=_elapsed_ms,
            tool=call.tool,
            success=result.success,
            params=call.params,
            output=result.output,
            metadata=result.metadata,
            started_at=started_at,
            completed_at=completed_at,
        )
        await _publish_runtime_event(
            "command.finished",
            severity="info" if result.success else "warning",
            payload={"tool": call.tool, "success": result.success, "output": result.output},
        )
        return result
    except TimeoutError:
        _elapsed_ms = (time.monotonic() - _start) * 1000
        completed_at = datetime.now(UTC).isoformat()
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
            metadata={"category": _infer_tool_category(call.tool)},
            started_at=started_at,
            completed_at=completed_at,
        )
        await _publish_runtime_event(
            "command.finished",
            severity="warning",
            payload={"tool": call.tool, "success": False, "error": "timeout"},
        )
        return AgentToolResult(
            tool=call.tool,
            success=False,
            output=f"Tool '{call.tool}' timed out after {timeout}s.",
            metadata={"category": _infer_tool_category(call.tool)},
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
            metadata={"category": _infer_tool_category(call.tool)},
            started_at=started_at,
            completed_at=completed_at,
        )
        await _publish_runtime_event(
            "command.finished",
            severity="error",
            payload={"tool": call.tool, "success": False, "error": str(e)},
        )
        return AgentToolResult(
            tool=call.tool,
            success=False,
            output=f"Error executing '{call.tool}': {e}",
            metadata={"category": _infer_tool_category(call.tool)},
            duration_ms=_elapsed_ms,
            started_at=started_at,
            completed_at=completed_at,
        )


def format_tool_results(results: list[AgentToolResult]) -> str:
    """Format results as <tool_result> tags for provider resume."""
    parts = ["Here are the results of the agent tool calls you requested:\n"]
    for r in results:
        success = "true" if r.success else "false"
        parts.append(f'<tool_result tool="{r.tool}" success="{success}">{r.output}</tool_result>')
    return "\n".join(parts)


def _is_write_tool(tool: str, params: dict) -> bool:
    """Determine if a tool call is a write operation."""
    if tool in _WRITE_TOOLS:
        return True
    if tool in _READ_TOOLS:
        return False
    if tool in ("jira", "confluence"):
        from koda.utils.approval import _is_atlassian_write

        return _is_atlassian_write(params.get("args", ""))
    if tool == "gws":
        from koda.utils.approval import _is_gws_write

        return _is_gws_write(params.get("args", ""))
    if tool == "http_request":
        method = params.get("method", "GET").upper()
        return method not in {"GET", "HEAD", "OPTIONS"}
    if tool == "browser_cookies":
        return str(params.get("action", "get")) == "set"
    return False


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
    return AgentToolResult(tool="cron_list", success=True, output="\n".join(lines))


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
    from koda.services.scheduled_jobs import get_job

    job_id = params.get("job_id")
    if job_id is None:
        return AgentToolResult(tool="job_get", success=False, output="Missing required param: 'job_id'.")
    try:
        job_id = int(job_id)
    except (TypeError, ValueError):
        return AgentToolResult(tool="job_get", success=False, output="'job_id' must be an integer.")
    job = get_job(job_id, ctx.user_id)
    if not job:
        return AgentToolResult(tool="job_get", success=False, output=f"Job #{job_id} not found.")
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
            f"payload={json.dumps(payload, ensure_ascii=True)}"
        ),
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
            f"task={run.get('task_id') or 'n/a'} verify={run.get('verification_status') or 'pending'}"
        )
    return AgentToolResult(tool="job_runs", success=True, output="\n".join(lines))


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
        if not schedule_expr or not text:
            return AgentToolResult(
                tool="job_create",
                success=False,
                output="reminder requires 'schedule_expr' and 'text'.",
            )
        job_id = create_reminder_job(
            user_id=ctx.user_id,
            chat_id=ctx.chat_id,
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

    result = await fetch_url(url)
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

    result = await make_http_request(method, url, headers=headers, body=body)
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

    from koda.services.cli_runner import run_cli_command_detailed
    from koda.utils.approval import _execution_approved

    env = {}
    if GWS_CREDENTIALS_FILE:
        env["GWS_CREDENTIALS_FILE"] = GWS_CREDENTIALS_FILE

    token = _execution_approved.set(True)
    try:
        command_result = await run_cli_command_detailed(
            "gws",
            args,
            ctx.work_dir,
            blocked_pattern=BLOCKED_GWS_PATTERN,
            timeout=AGENT_TOOL_TIMEOUT,
            env=env,
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

    result = await browser_manager.navigate(_browser_scope_id(ctx), url)
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
        result = await browser_manager.set_cookie(_browser_scope_id(ctx), name, value, domain=domain)
    else:
        url = params.get("url")
        result = await browser_manager.get_cookies(_browser_scope_id(ctx), url=url)
    success = not result.startswith("Error")
    return AgentToolResult(tool="browser_cookies", success=success, output=result)


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
    env = ctx.user_data.get("postgres_env")
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

    from koda.services.db_manager import db_manager

    result = await db_manager.query(sql, max_rows=max_rows, env=env)
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
        },
    )


async def _handle_db_schema(params: dict, ctx: ToolContext) -> AgentToolResult:
    env = ctx.user_data.get("postgres_env")
    err = _check_db_available("db_schema", env)
    if err:
        return err
    table = params.get("table")
    from koda.services.db_manager import db_manager

    result = await db_manager.get_schema(table, env=env)
    success = not result.startswith("Error")
    return AgentToolResult(
        tool="db_schema",
        success=success,
        output=result,
        metadata={
            "category": "db",
            "table": table,
            "env": env,
        },
    )


async def _handle_db_explain(params: dict, ctx: ToolContext) -> AgentToolResult:
    env = ctx.user_data.get("postgres_env")
    err = _check_db_available("db_explain", env)
    if err:
        return err
    sql = params.get("sql", "")
    if not sql:
        return AgentToolResult(tool="db_explain", success=False, output="Missing required param: 'sql'.")
    analyze = params.get("analyze", False)
    if isinstance(analyze, str):
        analyze = analyze.lower() in ("true", "1", "yes")
    from koda.services.db_manager import db_manager

    result = await db_manager.explain(sql, analyze=analyze, env=env)
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
        },
    )


async def _handle_db_switch_env(params: dict, ctx: ToolContext) -> AgentToolResult:
    err = _check_db_available("db_switch_env")
    if err:
        return err
    env = params.get("env", "").lower()
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
    for r in results:
        lang = f" [{r.language}]" if r.language else ""
        lines.append(f"#{r.script_id}: {r.title}{lang} (score: {r.similarity:.2f}, uses: {r.use_count})")
        if r.description:
            lines.append(f"  {r.description[:100]}")
        preview = r.content[:200].replace("\n", "\n  ")
        lines.append(f"  ```\n  {preview}\n  ```")
    return AgentToolResult(tool="script_search", success=True, output="\n".join(lines))


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
    for row in scripts:
        sid, title, desc, lang, use_count, quality, created = row
        lang_str = f" [{lang}]" if lang else ""
        lines.append(f"#{sid}: {title}{lang_str} — uses: {use_count}, quality: {quality:.1f}")
    return AgentToolResult(tool="script_list", success=True, output="\n".join(lines))


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
    return AgentToolResult(tool="cache_stats", success=True, output="\n".join(lines))


async def _handle_cache_clear(params: dict, ctx: ToolContext) -> AgentToolResult:
    from koda.services.cache_config import CACHE_ENABLED

    if not CACHE_ENABLED:
        return AgentToolResult(tool="cache_clear", success=False, output="Cache is disabled.")

    from koda.services.cache_manager import get_cache_manager

    cm = get_cache_manager()
    count = await cm.invalidate_user(ctx.user_id)
    return AgentToolResult(tool="cache_clear", success=True, output=f"Cleared {count} cached entries.")


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
    "db_query": _handle_db_query,
    "db_schema": _handle_db_schema,
    "db_explain": _handle_db_explain,
    "db_switch_env": _handle_db_switch_env,
    "script_save": _handle_script_save,
    "script_search": _handle_script_search,
    "script_list": _handle_script_list,
    "script_delete": _handle_script_delete,
    "cache_stats": _handle_cache_stats,
    "cache_clear": _handle_cache_clear,
}
