"""Child-run contract, store helpers, and Delegate Task tool implementation."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from koda.config import AGENT_ID, DEFAULT_PROVIDER
from koda.logging_config import get_logger
from koda.services.context_governance import build_child_context_prompt, normalize_context_policy
from koda.state.primary import primary_execute, primary_fetch_all, primary_fetch_one

log = get_logger(__name__)

CHILD_RUN_SCHEMA_VERSION = "child_run.v1"
DEFAULT_CHILD_RUN_TIMEOUT_SECONDS = 180
MAX_CHILD_RUN_TIMEOUT_SECONDS = 600
MAX_CHILD_RUNS_PER_CALL = 4
MAX_CONCURRENT_CHILD_RUNS_PER_PARENT = 2

TERMINAL_CHILD_RUN_STATUSES = frozenset({"completed", "failed", "cancelled"})
ALLOWED_CHILD_TOOLSETS = frozenset({"read_only", "analysis", "research"})
BLOCKED_CHILD_TOOLSETS = frozenset({"write", "network_write", "destructive", "unknown", "standard"})

_IN_PROCESS_CHILD_TASKS: dict[tuple[int, str], int] = {}
_IDEMPOTENCY_LOCK = asyncio.Lock()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_load(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return fallback


def _normalize_agent_id(agent_id: str | None = None) -> str:
    return str(agent_id or AGENT_ID or "default").strip().upper()


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_status(value: Any) -> str:
    status = str(value or "queued").strip().lower()
    if status == "needs_review":
        return "degraded"
    if status in {"queued", "running", "retrying", "stalled", "degraded", "failed", "cancelled", "completed"}:
        return status
    return "degraded"


def _clip(value: Any, limit: int = 600) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _signature(value: Any) -> str:
    text = _json_dumps(value)
    return hashlib.sha256(text.encode("utf-8"), usedforsecurity=False).hexdigest()


def make_child_run_id(parent_task_id: int, attempt: int, tool_call_signature: str, child_index: int) -> str:
    seed = f"{int(parent_task_id)}:{int(attempt)}:{tool_call_signature}:{int(child_index)}"
    digest = hashlib.sha256(seed.encode("utf-8"), usedforsecurity=False).hexdigest()[:20]
    return f"childrun_{digest}"


def make_idempotency_key(parent_task_id: int, attempt: int, tool_call_signature: str, child_index: int) -> str:
    return f"{int(parent_task_id)}:{int(attempt)}:{tool_call_signature[:24]}:{int(child_index)}"


def error_envelope(code: str, message: str, *, retryable: bool = False, category: str = "policy") -> dict[str, Any]:
    return {
        "code": code,
        "category": category,
        "message": message,
        "retryable": retryable,
        "user_action": "Adjust the Delegate Task request or inspect the child run in the execution detail.",
    }


def normalize_child_run_requests(params: Mapping[str, Any]) -> list[dict[str, Any]]:
    base = {str(key): item for key, item in params.items() if key != "tasks"}
    tasks = params.get("tasks")
    if isinstance(tasks, list) and tasks:
        normalized = []
        for item in tasks:
            if isinstance(item, Mapping):
                merged = dict(base)
                merged.update({str(key): value for key, value in item.items()})
                normalized.append(merged)
        return normalized
    return [base]


async def _fetch_child_run_by_idempotency(
    *,
    agent_id: str,
    parent_task_id: int,
    idempotency_key: str,
) -> dict[str, Any] | None:
    try:
        return await primary_fetch_one(
            """
            SELECT child_run_id, agent_id, parent_task_id, child_task_id, status,
                   target_agent_id, toolset, request_json, context_policy_json,
                   context_summary_json, result_json, error_json, deadline_at,
                   started_at, completed_at, created_at, updated_at, idempotency_key
              FROM child_runs
             WHERE agent_id = ? AND parent_task_id = ? AND idempotency_key = ?
             LIMIT 1
            """,
            (agent_id, parent_task_id, idempotency_key),
            agent_id=agent_id,
        )
    except Exception:
        log.debug("child_run_idempotency_lookup_skipped", exc_info=True)
        return None


async def list_child_runs_for_parent(agent_id: str | None, parent_task_id: int) -> list[dict[str, Any]]:
    """Return child-run rows for API/detail surfaces, falling back to task lineage."""

    normalized_agent_id = _normalize_agent_id(agent_id)
    rows: list[dict[str, Any]] = []
    try:
        rows = await primary_fetch_all(
            """
            SELECT child_run_id, agent_id, parent_task_id, child_task_id, status,
                   target_agent_id, toolset, request_json, context_policy_json,
                   context_summary_json, result_json, error_json, deadline_at,
                   started_at, completed_at, created_at, updated_at, idempotency_key
              FROM child_runs
             WHERE agent_id = ? AND parent_task_id = ?
          ORDER BY created_at ASC, child_run_id ASC
            """,
            (normalized_agent_id, parent_task_id),
            agent_id=normalized_agent_id,
        )
    except Exception:
        log.debug("child_run_list_table_unavailable", parent_task_id=parent_task_id, exc_info=True)

    if rows:
        return [_normalize_child_run_row(row) for row in rows]

    try:
        task_rows = await primary_fetch_all(
            """
            SELECT id, agent_id, source_task_id, source_action, status, query_text,
                   cost_usd, error_message, created_at, started_at, completed_at
              FROM tasks
             WHERE agent_id = ? AND source_task_id = ? AND source_action = 'child_run'
          ORDER BY created_at ASC, id ASC
            """,
            (normalized_agent_id, parent_task_id),
            agent_id=normalized_agent_id,
        )
    except Exception:
        return []
    return [
        {
            "schema_version": CHILD_RUN_SCHEMA_VERSION,
            "child_run_id": f"task:{row.get('id')}",
            "agent_id": normalized_agent_id,
            "parent_task_id": parent_task_id,
            "child_task_id": _int(row.get("id")),
            "status": _normalize_status(row.get("status")),
            "target_agent_id": normalized_agent_id,
            "toolset": "unknown",
            "summary": _clip(row.get("query_text")),
            "structured_output": None,
            "artifacts": [],
            "cost_usd": _float_or_none(row.get("cost_usd")),
            "run_graph_node_id": None,
            "warnings": ["reconstructed_from_task_lineage"],
            "error": error_envelope("subagent.reconstructed", str(row.get("error_message") or ""), category="runtime")
            if row.get("error_message")
            else None,
            "created_at": row.get("created_at"),
            "started_at": row.get("started_at"),
            "completed_at": row.get("completed_at"),
            "context_policy": {},
            "context_summary": {},
            "request": {},
            "available_actions": _available_actions_for_status(str(row.get("status") or "")),
        }
        for row in task_rows
    ]


def list_child_runs_for_parent_sync(agent_id: str | None, parent_task_id: int) -> list[dict[str, Any]]:
    from koda.state.primary import run_coro_sync

    try:
        return list(run_coro_sync(list_child_runs_for_parent(agent_id, parent_task_id)) or [])
    except Exception:
        log.debug("child_run_list_sync_failed", parent_task_id=parent_task_id, exc_info=True)
        return []


async def upsert_child_run(
    *,
    agent_id: str,
    child_run_id: str,
    parent_task_id: int,
    child_task_id: int | None,
    status: str,
    idempotency_key: str,
    target_agent_id: str | None,
    toolset: str,
    request: Mapping[str, Any],
    context_policy: Mapping[str, Any],
    context_summary: Mapping[str, Any] | None = None,
    result: Mapping[str, Any] | None = None,
    error: Mapping[str, Any] | None = None,
    deadline_at: str | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
) -> None:
    try:
        await primary_execute(
            """
            INSERT INTO child_runs (
                agent_id, child_run_id, parent_task_id, child_task_id, status, idempotency_key,
                target_agent_id, toolset, request_json, context_policy_json, context_summary_json,
                result_json, error_json, deadline_at, started_at, completed_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?::jsonb, ?::jsonb, ?::jsonb, ?::jsonb, ?::jsonb, ?, ?, ?, ?)
            ON CONFLICT (agent_id, child_run_id) DO UPDATE SET
                child_task_id = COALESCE(EXCLUDED.child_task_id, child_runs.child_task_id),
                status = EXCLUDED.status,
                target_agent_id = EXCLUDED.target_agent_id,
                toolset = EXCLUDED.toolset,
                request_json = EXCLUDED.request_json,
                context_policy_json = EXCLUDED.context_policy_json,
                context_summary_json = EXCLUDED.context_summary_json,
                result_json = EXCLUDED.result_json,
                error_json = EXCLUDED.error_json,
                deadline_at = EXCLUDED.deadline_at,
                started_at = COALESCE(EXCLUDED.started_at, child_runs.started_at),
                completed_at = EXCLUDED.completed_at,
                updated_at = EXCLUDED.updated_at
            """,
            (
                agent_id,
                child_run_id,
                parent_task_id,
                child_task_id,
                status,
                idempotency_key,
                target_agent_id,
                toolset,
                _json_dumps(dict(request)),
                _json_dumps(dict(context_policy)),
                _json_dumps(dict(context_summary or {})),
                _json_dumps(dict(result or {})),
                _json_dumps(dict(error or {})),
                deadline_at,
                started_at,
                completed_at,
                _now_iso(),
            ),
            agent_id=agent_id,
        )
    except Exception:
        log.debug("child_run_upsert_skipped", child_run_id=child_run_id, exc_info=True)


async def update_child_run_result(
    *,
    agent_id: str,
    child_run_id: str,
    status: str,
    result: Mapping[str, Any] | None = None,
    error: Mapping[str, Any] | None = None,
) -> None:
    try:
        await primary_execute(
            """
            UPDATE child_runs
               SET status = ?,
                   result_json = ?::jsonb,
                   error_json = ?::jsonb,
                   completed_at = ?,
                   updated_at = ?
             WHERE agent_id = ? AND child_run_id = ?
            """,
            (
                status,
                _json_dumps(dict(result or {})),
                _json_dumps(dict(error or {})),
                _now_iso() if status in TERMINAL_CHILD_RUN_STATUSES else None,
                _now_iso(),
                agent_id,
                child_run_id,
            ),
            agent_id=agent_id,
        )
    except Exception:
        log.debug("child_run_result_update_skipped", child_run_id=child_run_id, exc_info=True)


def _normalize_child_run_row(row: Mapping[str, Any]) -> dict[str, Any]:
    result = _json_load(row.get("result_json"), {})
    error = _json_load(row.get("error_json"), {})
    return {
        "schema_version": CHILD_RUN_SCHEMA_VERSION,
        "child_run_id": str(row.get("child_run_id") or ""),
        "agent_id": str(row.get("agent_id") or ""),
        "parent_task_id": _int(row.get("parent_task_id")),
        "child_task_id": _int(row.get("child_task_id")) if row.get("child_task_id") is not None else None,
        "status": _normalize_status(row.get("status")),
        "target_agent_id": str(row.get("target_agent_id") or "") or None,
        "toolset": str(row.get("toolset") or "read_only"),
        "summary": result.get("summary") if isinstance(result, Mapping) else None,
        "structured_output": result.get("structured_output") if isinstance(result, Mapping) else None,
        "artifacts": result.get("artifacts") if isinstance(result, Mapping) else [],
        "cost_usd": _float_or_none(result.get("cost_usd")) if isinstance(result, Mapping) else None,
        "run_graph_node_id": result.get("run_graph_node_id") if isinstance(result, Mapping) else None,
        "warnings": result.get("warnings")
        if isinstance(result, Mapping) and isinstance(result.get("warnings"), list)
        else [],
        "error": error if isinstance(error, Mapping) and error else None,
        "request": _json_load(row.get("request_json"), {}),
        "context_policy": _json_load(row.get("context_policy_json"), {}),
        "context_summary": _json_load(row.get("context_summary_json"), {}),
        "created_at": row.get("created_at"),
        "started_at": row.get("started_at"),
        "completed_at": row.get("completed_at"),
        "deadline_at": row.get("deadline_at"),
        "idempotency_key": row.get("idempotency_key"),
        "available_actions": _available_actions_for_status(str(row.get("status") or "")),
    }


def _available_actions_for_status(status: str) -> list[str]:
    normalized = status.lower()
    if normalized in {"queued", "running", "retrying", "stalled", "degraded"}:
        return ["cancel", "interrupt", "open_execution"]
    return ["open_execution"]


def _summarize_child_task(agent_id: str, child_run_id: str, child_task_id: int, warnings: list[str]) -> dict[str, Any]:
    from koda.state.history_store import get_task

    task = get_task(child_task_id)
    status = "failed"
    cost_usd = None
    error_message = None
    if task is not None:
        status = _normalize_status(task[3])
        cost_usd = _float_or_none(task[10])
        error_message = str(task[11] or "") or None

    response_text = ""
    structured_output: Any = None
    try:
        from koda.control_plane.dashboard_service import get_dashboard_execution_detail

        detail = get_dashboard_execution_detail(agent_id, child_task_id) or {}
        response_text = str(detail.get("response_text") or "")
        structured_output = detail.get("structured_output")
    except Exception:
        log.debug("child_run_detail_summary_unavailable", child_task_id=child_task_id, exc_info=True)

    summary = _clip(response_text or error_message or f"Child task {child_task_id} ended with status {status}.")
    error = (
        error_envelope(
            "subagent.child_failed" if status == "failed" else f"subagent.{status}",
            error_message or f"Child task ended with status {status}.",
            retryable=status in {"stalled", "degraded", "retrying"},
            category="runtime",
        )
        if status not in {"completed", "degraded"} or error_message
        else None
    )
    return {
        "schema_version": CHILD_RUN_SCHEMA_VERSION,
        "child_run_id": child_run_id,
        "child_task_id": child_task_id,
        "status": status,
        "summary": summary,
        "structured_output": structured_output,
        "artifacts": [],
        "cost_usd": cost_usd,
        "run_graph_node_id": None,
        "warnings": warnings,
        "error": error,
    }


async def _await_existing_child_task(child_task_id: int, timeout_seconds: int) -> None:
    from koda.services.queue_manager import get_task_info

    task_info = get_task_info(child_task_id)
    if task_info is not None and task_info.asyncio_task is not None and not task_info.asyncio_task.done():
        await asyncio.wait_for(task_info.asyncio_task, timeout=timeout_seconds)


async def _execute_one_child_request(
    *,
    request: Mapping[str, Any],
    ctx: Any,
    index: int,
    tool_call_signature: str,
) -> dict[str, Any]:
    from koda.services.queue_manager import cancel_active_task_execution, start_child_run_task

    parent_task_id = int(ctx.task_id or 0)
    attempt = _int(getattr(ctx, "attempt", None) or getattr(ctx, "parent_attempt", None), 1)
    idempotency_key = make_idempotency_key(parent_task_id, attempt, tool_call_signature, index)
    child_run_id = make_child_run_id(parent_task_id, attempt, tool_call_signature, index)
    agent_id = _normalize_agent_id()
    goal = str(request.get("goal") or request.get("prompt") or "").strip()
    prompt = str(request.get("prompt") or goal).strip()
    target_agent_id = str(
        request.get("target_agent_id") or getattr(ctx, "executing_agent_id", None) or AGENT_ID or "default"
    ).strip()
    toolset = str(request.get("toolset") or "read_only").strip().lower()
    timeout_seconds = max(
        1,
        min(
            MAX_CHILD_RUN_TIMEOUT_SECONDS,
            _int(request.get("timeout_seconds"), DEFAULT_CHILD_RUN_TIMEOUT_SECONDS),
        ),
    )
    max_context_tokens = _int(request.get("max_context_tokens"), 0)
    context_policy = normalize_context_policy(request.get("context_policy"))
    if max_context_tokens > 0:
        context_policy["max_tokens"] = max(128, min(16_000, max_context_tokens))
    context_summary = getattr(ctx, "context_governance", None) or {}
    warnings: list[str] = []
    if request.get("max_cost_usd") is not None:
        warnings.append("max_cost_usd is recorded and checked after completion in this Phase 3 runtime.")

    existing = await _fetch_child_run_by_idempotency(
        agent_id=agent_id,
        parent_task_id=parent_task_id,
        idempotency_key=idempotency_key,
    )
    if existing and existing.get("child_task_id"):
        child_task_id = int(existing["child_task_id"])
        try:
            await _await_existing_child_task(child_task_id, timeout_seconds)
        except TimeoutError:
            await cancel_active_task_execution(child_task_id, reason="subagent.timeout")
        result = _summarize_child_task(
            agent_id, str(existing.get("child_run_id") or child_run_id), child_task_id, warnings
        )
        await update_child_run_result(
            agent_id=agent_id,
            child_run_id=str(existing.get("child_run_id") or child_run_id),
            status=str(result.get("status") or "failed"),
            result=result,
            error=result.get("error") if isinstance(result.get("error"), Mapping) else None,
        )
        return result

    async with _IDEMPOTENCY_LOCK:
        cached_task_id = _IN_PROCESS_CHILD_TASKS.get((parent_task_id, idempotency_key))
        if cached_task_id is not None:
            await _await_existing_child_task(cached_task_id, timeout_seconds)
            return _summarize_child_task(agent_id, child_run_id, cached_task_id, warnings)
        await upsert_child_run(
            agent_id=agent_id,
            child_run_id=child_run_id,
            parent_task_id=parent_task_id,
            child_task_id=None,
            status="queued",
            idempotency_key=idempotency_key,
            target_agent_id=target_agent_id,
            toolset=toolset,
            request=request,
            context_policy=context_policy,
            context_summary=context_summary if isinstance(context_summary, Mapping) else {},
            deadline_at=(datetime.now(UTC) + timedelta(seconds=timeout_seconds)).isoformat(),
        )

    child_context_prompt = build_child_context_prompt(
        parent_task_id=parent_task_id,
        goal=goal,
        context_policy=context_policy,
        context_summary=context_summary if isinstance(context_summary, Mapping) else {},
    )
    child_query = f"{child_context_prompt}\n\n<child_run_brief>\n{prompt}\n</child_run_brief>"
    child_task_id, task = await start_child_run_task(
        application=getattr(ctx, "application", None),
        user_id=int(ctx.user_id),
        chat_id=int(ctx.chat_id),
        query_text=child_query,
        parent_task_id=parent_task_id,
        child_run_id=child_run_id,
        provider=str(ctx.user_data.get("provider") or DEFAULT_PROVIDER),
        model=ctx.user_data.get("model"),
        work_dir=str(ctx.work_dir or ctx.user_data.get("work_dir") or ""),
        session_id=str(ctx.user_data.get("session_id") or ""),
        child_context_prompt=child_context_prompt,
        context_policy=context_policy,
        toolset=toolset,
        target_agent_id=target_agent_id,
        bot_override=getattr(ctx, "bot", None),
        user_data_overlay={
            "child_run_depth": _int(ctx.user_data.get("child_run_depth"), 0) + 1,
            "child_run_parent_task_id": parent_task_id,
            "child_run_id": child_run_id,
        },
    )
    _IN_PROCESS_CHILD_TASKS[(parent_task_id, idempotency_key)] = child_task_id
    await upsert_child_run(
        agent_id=agent_id,
        child_run_id=child_run_id,
        parent_task_id=parent_task_id,
        child_task_id=child_task_id,
        status="running",
        idempotency_key=idempotency_key,
        target_agent_id=target_agent_id,
        toolset=toolset,
        request=request,
        context_policy=context_policy,
        context_summary=context_summary if isinstance(context_summary, Mapping) else {},
        deadline_at=(datetime.now(UTC) + timedelta(seconds=timeout_seconds)).isoformat(),
        started_at=_now_iso(),
    )

    try:
        await asyncio.wait_for(task, timeout=timeout_seconds)
    except TimeoutError:
        await cancel_active_task_execution(child_task_id, reason="subagent.timeout")
        with contextlib.suppress(BaseException):
            await task
        timeout_error = error_envelope("subagent.timeout", f"Child run exceeded {timeout_seconds}s.", retryable=True)
        result = {
            "schema_version": CHILD_RUN_SCHEMA_VERSION,
            "child_run_id": child_run_id,
            "child_task_id": child_task_id,
            "status": "failed",
            "summary": timeout_error["message"],
            "structured_output": None,
            "artifacts": [],
            "cost_usd": None,
            "run_graph_node_id": None,
            "warnings": warnings,
            "error": timeout_error,
        }
        await update_child_run_result(
            agent_id=agent_id, child_run_id=child_run_id, status="failed", result=result, error=timeout_error
        )
        return result
    except asyncio.CancelledError:
        await cancel_active_task_execution(child_task_id, reason="subagent.cancelled")
        await update_child_run_result(
            agent_id=agent_id,
            child_run_id=child_run_id,
            status="cancelled",
            error=error_envelope("subagent.cancelled", "Parent run cancelled the child run.", category="runtime"),
        )
        raise

    result = _summarize_child_task(agent_id, child_run_id, child_task_id, warnings)
    max_cost_usd = _float_or_none(request.get("max_cost_usd"))
    if max_cost_usd is not None and result.get("cost_usd") is not None and float(result["cost_usd"]) > max_cost_usd:
        result.setdefault("warnings", []).append("max_cost_usd_exceeded")
    await update_child_run_result(
        agent_id=agent_id,
        child_run_id=child_run_id,
        status=str(result.get("status") or "failed"),
        result=result,
        error=result.get("error") if isinstance(result.get("error"), Mapping) else None,
    )
    return result


async def delegate_child_task_tool(params: Mapping[str, Any], ctx: Any) -> Any:
    """Execute the schema-driven `task` tool and return an AgentToolResult."""

    from koda.services.tool_dispatcher import AgentToolResult

    if not getattr(ctx, "task_id", None):
        error = error_envelope("subagent.parent_task_required", "Delegate Task requires a persisted parent task.")
        return AgentToolResult(tool="task", success=False, output=error["message"], data={"error": error})
    if getattr(ctx, "application", None) is None:
        error = error_envelope("subagent.runtime_unavailable", "Runtime application context is unavailable.")
        return AgentToolResult(tool="task", success=False, output=error["message"], data={"error": error})
    if _int(getattr(ctx, "user_data", {}).get("child_run_depth"), 0) > 0:
        error = error_envelope("subagent.policy_denied", "Nested child-runs are disabled.")
        return AgentToolResult(tool="task", success=False, output=error["message"], data={"error": error})

    requests = normalize_child_run_requests(params)
    if not requests:
        error = error_envelope("subagent.validation", "Delegate Task requires `prompt` or `tasks[]`.")
        return AgentToolResult(tool="task", success=False, output=error["message"], data={"error": error})
    if len(requests) > MAX_CHILD_RUNS_PER_CALL:
        error = error_envelope(
            "subagent.fanout_limit_exceeded",
            f"Delegate Task accepts at most {MAX_CHILD_RUNS_PER_CALL} child runs per call.",
            retryable=False,
        )
        return AgentToolResult(tool="task", success=False, output=error["message"], data={"error": error})

    existing = await list_child_runs_for_parent(AGENT_ID, int(ctx.task_id))
    if len(existing) + len(requests) > MAX_CHILD_RUNS_PER_CALL:
        error = error_envelope(
            "subagent.fanout_limit_exceeded",
            f"Parent task already has {len(existing)} child run(s); total cap is {MAX_CHILD_RUNS_PER_CALL}.",
            retryable=False,
        )
        return AgentToolResult(tool="task", success=False, output=error["message"], data={"error": error})

    for request in requests:
        prompt = str(request.get("prompt") or request.get("goal") or "").strip()
        if not prompt:
            error = error_envelope("subagent.validation", "Each child run requires a `prompt` or `goal`.")
            return AgentToolResult(tool="task", success=False, output=error["message"], data={"error": error})
        toolset = str(request.get("toolset") or "read_only").strip().lower()
        if toolset in BLOCKED_CHILD_TOOLSETS or toolset not in ALLOWED_CHILD_TOOLSETS:
            error = error_envelope(
                "subagent.policy_denied",
                f"Toolset `{toolset}` is not available for child runs without a stricter approval path.",
            )
            return AgentToolResult(tool="task", success=False, output=error["message"], data={"error": error})

    tool_call_signature = _signature({"params": params, "parent_task_id": ctx.task_id})
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHILD_RUNS_PER_PARENT)

    async def _bounded(index: int, request: Mapping[str, Any]) -> dict[str, Any]:
        async with semaphore:
            return await _execute_one_child_request(
                request=request,
                ctx=ctx,
                index=index,
                tool_call_signature=tool_call_signature,
            )

    results = await asyncio.gather(*[_bounded(index, request) for index, request in enumerate(requests)])
    success = all(
        str(item.get("status")) in {"completed", "needs_review", "degraded"} and not item.get("error")
        for item in results
    )
    lines = [
        (
            f"{item.get('child_run_id')} task={item.get('child_task_id')} "
            f"status={item.get('status')}: {item.get('summary')}"
        )
        for item in results
    ]
    payload: dict[str, Any] = {
        "schema_version": CHILD_RUN_SCHEMA_VERSION,
        "child_runs": results,
        "results": results,
        "fanout": len(results),
    }
    if len(results) == 1:
        payload.update(results[0])
    return AgentToolResult(
        tool="task",
        success=success,
        output="\n".join(lines) if lines else "No child runs executed.",
        metadata={
            "category": "agent_comm",
            "contract": CHILD_RUN_SCHEMA_VERSION,
            "child_runs": results,
        },
        data=payload,
        data_format="json",
    )
