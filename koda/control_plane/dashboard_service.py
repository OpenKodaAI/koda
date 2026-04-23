"""Canonical dashboard queries over the Postgres-first control-plane state."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Any, cast

from koda.control_plane.manager import _normalize_agent_id, get_control_plane_manager
from koda.state.primary import primary_fetch_all, primary_fetch_one, run_coro_sync


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _primary_scope(agent_ids: list[str] | None = None) -> str | None:
    return agent_ids[0] if agent_ids else None


def _compact_agent_ids(agent_ids: list[str] | None = None) -> list[str]:
    return [str(agent_id).strip() for agent_id in agent_ids or [] if str(agent_id or "").strip()]


def _fetch_all(query: str, params: tuple[Any, ...] = (), *, agent_ids: list[str] | None = None) -> list[dict[str, Any]]:
    return run_coro_sync(primary_fetch_all(query, params, agent_id=_primary_scope(agent_ids))) or []


def _fetch_one(
    query: str, params: tuple[Any, ...] = (), *, agent_ids: list[str] | None = None
) -> dict[str, Any] | None:
    return cast(
        dict[str, Any] | None,
        run_coro_sync(primary_fetch_one(query, params, agent_id=_primary_scope(agent_ids))),
    )


def _placeholders(count: int) -> str:
    return ", ".join("?" for _ in range(count))


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    # Mixing aware + naive datetimes raises ``TypeError`` when subtracting.
    # Historical rows have both shapes (TEXT ISO with or without tz suffix),
    # so normalize to UTC-aware for arithmetic safety.
    if parsed.tzinfo is None:
        from datetime import UTC

        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _iso(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    return str(value)


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _duration_ms(*, started_at: Any, completed_at: Any, fallback: float | None = None) -> float | None:
    if started_at and completed_at:
        started = _parse_iso(started_at)
        completed = _parse_iso(completed_at)
        if started and completed:
            delta = (completed - started).total_seconds() * 1000
            return max(delta, 0.0)
    return fallback


def _clip_preview(value: Any, max_length: int = 140) -> str | None:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return None
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "…"


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip().lower()


def _serialize_task(row: dict[str, Any]) -> dict[str, Any]:
    agent_id = str(row.get("agent_id") or "") or None
    return {
        "id": int(row["id"]),
        # Both keys: legacy web code reads ``bot_id``, newer paths read
        # ``agent_id``. Emit both until the rename is finished in the web.
        "agent_id": agent_id,
        "bot_id": agent_id,
        "user_id": int(row.get("user_id") or 0),
        "chat_id": int(row.get("chat_id") or 0),
        "status": str(row.get("status") or "queued"),
        "query_text": str(row.get("query_text") or "") or None,
        "model": str(row.get("model") or "") or None,
        "work_dir": str(row.get("work_dir") or "") or None,
        "attempt": int(row.get("attempt") or 1),
        "max_attempts": int(row.get("max_attempts") or 3),
        "cost_usd": float(row.get("cost_usd") or 0.0),
        "error_message": str(row.get("error_message") or "") or None,
        "created_at": _iso(row.get("created_at")),
        "started_at": _iso(row.get("started_at")),
        "completed_at": _iso(row.get("completed_at")),
        "session_id": str(row.get("session_id") or "") or None,
    }


def _trace_runtime(trace: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(trace, dict):
        return {}
    runtime = trace.get("runtime")
    return runtime if isinstance(runtime, dict) else {}


def _trace_assistant(trace: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(trace, dict):
        return {}
    assistant = trace.get("assistant")
    return assistant if isinstance(assistant, dict) else {}


def _trace_tools(trace: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(trace, dict):
        return []
    tools = trace.get("tools")
    return [item for item in tools if isinstance(item, dict)] if isinstance(tools, list) else []


def _trace_timeline(trace: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(trace, dict):
        return []
    timeline = trace.get("timeline")
    return [item for item in timeline if isinstance(item, dict)] if isinstance(timeline, list) else []


def _trace_redactions(trace: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(trace, dict):
        return None
    redactions = trace.get("redactions")
    return redactions if isinstance(redactions, dict) else None


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _task_ids(rows: list[dict[str, Any]]) -> list[int]:
    return [int(row["id"]) for row in rows if row.get("id") is not None]


def _agent_catalog() -> list[dict[str, Any]]:
    return list(get_control_plane_manager().list_agents())


def _catalog_by_id() -> dict[str, dict[str, Any]]:
    return {str(item["id"]): item for item in _agent_catalog()}


def _resolve_agent_ids(agent_ids: list[str] | None = None) -> list[str]:
    catalog = _catalog_by_id()
    if agent_ids:
        normalized = [_normalize_agent_id(agent_id) for agent_id in agent_ids]
        return [agent_id for agent_id in normalized if agent_id in catalog]
    return list(catalog.keys())


def _fetch_task_rows(
    *,
    agent_ids: list[str],
    status: str | None = None,
    search: str | None = None,
    session_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    resolved_agent_ids = _compact_agent_ids(agent_ids)
    if not resolved_agent_ids:
        return []
    params: list[Any] = list(resolved_agent_ids)
    clauses = [f"agent_id IN ({_placeholders(len(resolved_agent_ids))})"]
    if status:
        clauses.append("status = ?")
        params.append(status)
    if search:
        clauses.append("LOWER(query_text) LIKE ?")
        params.append(f"%{_normalize_text(search)}%")
    if session_id:
        clauses.append("session_id = ?")
        params.append(session_id)
    params.extend([max(1, int(limit)), max(0, int(offset))])
    return _fetch_all(
        f"""
        SELECT id, agent_id, user_id, chat_id, status, query_text, model, work_dir, attempt, max_attempts,
               cost_usd, error_message, created_at, started_at, completed_at, session_id
          FROM tasks
         WHERE {" AND ".join(clauses)}
      ORDER BY id DESC
         LIMIT ? OFFSET ?
        """,
        tuple(params),
        agent_ids=resolved_agent_ids,
    )


def _fetch_latest_traces(agent_ids: list[str], task_ids: list[int]) -> dict[int, dict[str, Any]]:
    resolved_agent_ids = _compact_agent_ids(agent_ids)
    if not resolved_agent_ids or not task_ids:
        return {}
    params: list[Any] = list(resolved_agent_ids) + task_ids
    rows = _fetch_all(
        f"""
        SELECT DISTINCT ON (task_id)
               task_id, details_json, cost_usd, duration_ms
          FROM audit_events
         WHERE agent_id IN ({_placeholders(len(resolved_agent_ids))})
           AND event_type = 'task.execution_trace'
           AND task_id IN ({_placeholders(len(task_ids))})
      ORDER BY task_id, id DESC
        """,
        tuple(params),
        agent_ids=resolved_agent_ids,
    )
    return {
        int(row["task_id"]): dict(row.get("details_json") or {})
        | {
            "_duration_ms": float(row.get("duration_ms") or 0.0),
            "_cost_usd": float(row.get("cost_usd") or 0.0),
        }
        for row in rows
        if row.get("task_id") is not None
    }


def _fetch_latest_episodes(agent_ids: list[str], task_ids: list[int]) -> dict[int, dict[str, Any]]:
    resolved_agent_ids = _compact_agent_ids(agent_ids)
    if not resolved_agent_ids or not task_ids:
        return {}
    params: list[Any] = list(resolved_agent_ids) + task_ids
    rows = _fetch_all(
        f"""
        SELECT DISTINCT ON (task_id)
               task_id, tool_trace_json, source_refs_json, winning_sources_json, feedback_status,
               retrieval_trace_id, retrieval_strategy, grounding_score, citation_coverage,
               answer_citation_coverage, answer_gate_status, answer_gate_reasons_json,
               stale_sources_present, ungrounded_operationally, post_write_review_required, created_at
          FROM execution_episodes
         WHERE agent_id IN ({_placeholders(len(resolved_agent_ids))})
           AND task_id IN ({_placeholders(len(task_ids))})
      ORDER BY task_id, id DESC
        """,
        tuple(params),
        agent_ids=resolved_agent_ids,
    )
    return {int(row["task_id"]): row for row in rows if row.get("task_id") is not None}


def _pending_approval_id_for_task(*, agent_id: str, session_id: str | None, task_id: int) -> str | None:
    try:
        from koda.services.approval_broker import find_pending
    except Exception:
        return None
    return find_pending(agent_id=agent_id, session_id=session_id, task_id=task_id)


def _serialize_execution_summary(
    row: dict[str, Any],
    trace: dict[str, Any] | None,
    episode: dict[str, Any] | None,
) -> dict[str, Any]:
    runtime = _trace_runtime(trace)
    tools = _trace_tools(trace) or _safe_list((episode or {}).get("tool_trace_json"))
    warnings = [str(item) for item in _safe_list(runtime.get("warnings"))]
    source_refs = _safe_list((episode or {}).get("source_refs_json"))
    winning_sources = [str(item) for item in _safe_list((episode or {}).get("winning_sources_json"))]
    answer_gate_reasons = [str(item) for item in _safe_list((episode or {}).get("answer_gate_reasons_json"))]
    pending_approval_id = _pending_approval_id_for_task(
        agent_id=str(row.get("agent_id") or ""),
        session_id=str(row.get("session_id") or "") or None,
        task_id=int(row.get("id") or 0),
    )
    agent_id = str(row.get("agent_id") or "")
    return {
        "task_id": int(row["id"]),
        # Both keys intentionally. The frontend type ``ExecutionSummary`` uses
        # ``bot_id`` from the legacy naming (migration-in-progress from "bot"
        # to "agent"). Dropping ``bot_id`` from the response broke the
        # executions table and detail panes silently — React rendered the
        # rows but every ``getAgentColor(execution.bot_id)`` / key lookup
        # fell through with ``undefined``. Emit both until the rename
        # lands across the web tree.
        "agent_id": agent_id,
        "bot_id": agent_id,
        "status": str(row.get("status") or "queued"),
        "query_text": str(row.get("query_text") or "") or None,
        "model": str(row.get("model") or "") or None,
        "session_id": str(row.get("session_id") or "") or None,
        "user_id": int(row.get("user_id") or 0),
        "chat_id": int(row.get("chat_id") or 0),
        "created_at": _iso(row.get("created_at")),
        "started_at": _iso(row.get("started_at")),
        "completed_at": _iso(row.get("completed_at")),
        "cost_usd": float(row.get("cost_usd") or 0.0),
        "duration_ms": _duration_ms(
            started_at=row.get("started_at"),
            completed_at=row.get("completed_at"),
            fallback=float((trace or {}).get("_duration_ms") or 0.0) or None,
        ),
        "attempt": int(row.get("attempt") or 1),
        "max_attempts": int(row.get("max_attempts") or 3),
        "has_rich_trace": bool(trace or episode),
        "trace_source": "trace" if trace else ("legacy" if episode else "missing"),
        "tool_count": len(tools),
        "warning_count": len(warnings),
        "stop_reason": str(runtime.get("stop_reason") or "") or None,
        "error_message": str(row.get("error_message") or "") or None,
        "feedback_status": str((episode or {}).get("feedback_status") or "pending"),
        "retrieval_trace_id": (episode or {}).get("retrieval_trace_id"),
        "retrieval_strategy": str((episode or {}).get("retrieval_strategy") or "") or None,
        "grounding_score": float((episode or {}).get("grounding_score") or 0.0),
        "citation_coverage": float((episode or {}).get("citation_coverage") or 0.0),
        "answer_citation_coverage": float((episode or {}).get("answer_citation_coverage") or 0.0),
        "answer_gate_status": str((episode or {}).get("answer_gate_status") or "") or None,
        "answer_gate_reasons": answer_gate_reasons,
        "pending_approval_id": pending_approval_id,
        "post_write_review_required": bool((episode or {}).get("post_write_review_required")),
        "stale_sources_present": bool((episode or {}).get("stale_sources_present")),
        "ungrounded_operationally": bool((episode or {}).get("ungrounded_operationally")),
        "source_ref_count": len(source_refs),
        "winning_source_count": len(winning_sources),
        "provenance_source": "episode" if episode else ("trace" if trace else "missing"),
    }


def list_dashboard_execution_summaries(
    *,
    agent_ids: list[str],
    status: str | None = None,
    search: str | None = None,
    session_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    rows = _fetch_task_rows(
        agent_ids=agent_ids,
        status=status,
        search=search,
        session_id=session_id,
        limit=limit,
        offset=offset,
    )
    task_ids = _task_ids(rows)
    traces = _fetch_latest_traces(agent_ids, task_ids)
    episodes = _fetch_latest_episodes(agent_ids, task_ids)
    return [_serialize_execution_summary(row, traces.get(int(row["id"])), episodes.get(int(row["id"]))) for row in rows]


def get_dashboard_execution_detail(agent_id: str, task_id: int) -> dict[str, Any] | None:
    normalized = _normalize_agent_id(agent_id)
    row = _fetch_one(
        """
        SELECT id, agent_id, user_id, chat_id, status, query_text, model, work_dir, attempt, max_attempts,
               cost_usd, error_message, created_at, started_at, completed_at, session_id
          FROM tasks
         WHERE agent_id = ? AND id = ?
        """,
        (normalized, task_id),
        agent_ids=[normalized],
    )
    if row is None:
        return None
    trace = _fetch_latest_traces([normalized], [task_id]).get(task_id)
    episode = _fetch_latest_episodes([normalized], [task_id]).get(task_id)
    runtime = _trace_runtime(trace)
    assistant = _trace_assistant(trace)
    tools = _trace_tools(trace) or _safe_list((episode or {}).get("tool_trace_json"))
    timeline = _trace_timeline(trace)
    warnings = [str(item) for item in _safe_list(runtime.get("warnings"))]
    redactions = _trace_redactions(trace)
    reasoning_summary = [str(item) for item in _safe_list(runtime.get("reasoning_summary")) if str(item or "").strip()]
    return {
        **_serialize_execution_summary(row, trace, episode),
        "response_text": str(assistant.get("response_text") or "") or None,
        "work_dir": str(row.get("work_dir") or "") or None,
        "warnings": warnings,
        "response_source": "trace" if assistant.get("response_text") else "missing",
        "tools_source": "trace" if trace else ("audit" if episode else "missing"),
        "timeline": [
            {
                "id": f"timeline-{index}",
                "type": str(item.get("type") or "event"),
                "title": str(item.get("title") or "Event"),
                "summary": str(item.get("summary") or "") or None,
                "status": str(item.get("status") or "info"),
                "timestamp": _iso(item.get("timestamp")),
                "details": item.get("details") if isinstance(item.get("details"), dict) else {},
            }
            for index, item in enumerate(timeline)
        ],
        "tools": [
            {
                "id": f"tool-{index}",
                "tool": str(item.get("tool") or item.get("name") or f"tool_{index + 1}"),
                "category": str(item.get("category") or "tool"),
                "success": item.get("success") if isinstance(item.get("success"), bool) else None,
                "duration_ms": float(item.get("duration_ms") or 0.0) or None,
                "started_at": _iso(item.get("started_at")),
                "completed_at": _iso(item.get("completed_at")),
                "params": item.get("params") if isinstance(item.get("params"), dict) else {},
                "output": str(item.get("output") or "") or None,
                "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
                "summary": str(item.get("summary") or item.get("tool") or f"Tool {index + 1}"),
                "redactions": item.get("redactions") if isinstance(item.get("redactions"), dict) else None,
            }
            for index, item in enumerate(tools)
            if isinstance(item, dict)
        ],
        "artifacts": [],
        "reasoning_summary": reasoning_summary,
        "redactions": redactions,
    }


def _build_stats(agent_id: str) -> dict[str, Any]:
    agent_rows = _fetch_all(
        """
        SELECT status, COUNT(*) AS count
          FROM tasks
         WHERE agent_id = ?
      GROUP BY status
        """,
        (agent_id,),
        agent_ids=[agent_id],
    )
    task_counts = {str(row["status"]): int(row["count"] or 0) for row in agent_rows}
    query_totals = (
        _fetch_one(
            """
        SELECT COUNT(*) AS total_queries, COALESCE(SUM(cost_usd), 0) AS total_cost
          FROM query_history
         WHERE agent_id = ?
        """,
            (agent_id,),
            agent_ids=[agent_id],
        )
        or {}
    )
    today = _now_utc().date()
    today_cost = (
        _fetch_one(
            """
        SELECT COALESCE(SUM(cost_usd), 0) AS total_cost
          FROM query_history
         WHERE agent_id = ? AND timestamp >= ?
        """,
            (agent_id, today),
            agent_ids=[agent_id],
        )
        or {}
    )
    daily_rows = _fetch_all(
        """
        SELECT DATE(timestamp) AS date, COALESCE(SUM(cost_usd), 0) AS cost
          FROM query_history
         WHERE agent_id = ? AND timestamp >= ?
      GROUP BY DATE(timestamp)
      ORDER BY DATE(timestamp) ASC
        """,
        (agent_id, (_now_utc() - timedelta(days=30)).date()),
        agent_ids=[agent_id],
    )
    recent_tasks = [_serialize_task(task) for task in _fetch_task_rows(agent_ids=[agent_id], limit=5, offset=0)]
    return {
        "agentId": agent_id,
        "totalTasks": sum(task_counts.values()),
        "activeTasks": int(task_counts.get("running", 0)) + int(task_counts.get("retrying", 0)),
        "completedTasks": int(task_counts.get("completed", 0)),
        "failedTasks": int(task_counts.get("failed", 0)),
        "queuedTasks": int(task_counts.get("queued", 0)),
        "totalQueries": int(query_totals.get("total_queries") or 0),
        "totalCost": float(query_totals.get("total_cost") or 0.0),
        "todayCost": float(today_cost.get("total_cost") or 0.0),
        "dbExists": True,
        "recentTasks": recent_tasks,
        "dailyCosts": [
            {
                "date": str(row.get("date") or ""),
                "cost": float(row.get("cost") or 0.0),
            }
            for row in daily_rows
        ],
    }


def list_dashboard_agent_summaries(agent_ids: list[str] | None = None) -> list[dict[str, Any]]:
    return [_build_stats(agent_id) for agent_id in _resolve_agent_ids(agent_ids)]


def get_dashboard_agent_stats(agent_id: str) -> dict[str, Any]:
    normalized = _normalize_agent_id(agent_id)
    return _build_stats(normalized)


def _session_rows(agent_id: str) -> list[dict[str, Any]]:
    return _fetch_all(
        """
        SELECT session_id,
               NULL AS name,
               MAX(user_id) AS user_id,
               MIN(timestamp) AS created_at,
               MAX(timestamp) AS last_used
          FROM query_history
         WHERE agent_id = ? AND session_id IS NOT NULL
      GROUP BY session_id
      ORDER BY MAX(timestamp) DESC
        """,
        (agent_id,),
        agent_ids=[agent_id],
    )


def _query_aggregate_rows(agent_id: str) -> list[dict[str, Any]]:
    return _fetch_all(
        """
        SELECT session_id,
               COUNT(*) AS query_count,
               COALESCE(SUM(cost_usd), 0) AS total_cost_usd,
               MAX(timestamp) AS last_query_at
          FROM query_history
         WHERE agent_id = ? AND session_id IS NOT NULL
      GROUP BY session_id
        """,
        (agent_id,),
        agent_ids=[agent_id],
    )


def _latest_query_rows(agent_id: str) -> list[dict[str, Any]]:
    return _fetch_all(
        """
        SELECT session_id, user_id, timestamp, query_text, response_text, model, error
          FROM (
                SELECT session_id, user_id, timestamp, query_text, response_text, model, error, id,
                       ROW_NUMBER() OVER (PARTITION BY session_id ORDER BY timestamp DESC, id DESC) AS rn
                  FROM query_history
                 WHERE agent_id = ? AND session_id IS NOT NULL
               ) ranked
         WHERE rn = 1
        """,
        (agent_id,),
        agent_ids=[agent_id],
    )


def _task_aggregate_rows(agent_id: str) -> list[dict[str, Any]]:
    return _fetch_all(
        """
        SELECT session_id,
               COUNT(*) AS execution_count,
               COALESCE(SUM(cost_usd), 0) AS total_cost_usd,
               SUM(CASE WHEN status IN ('running', 'retrying') THEN 1 ELSE 0 END) AS running_count,
               SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count,
               MAX(COALESCE(completed_at, started_at, created_at)) AS last_execution_at
          FROM tasks
         WHERE agent_id = ? AND session_id IS NOT NULL
      GROUP BY session_id
        """,
        (agent_id,),
        agent_ids=[agent_id],
    )


def _latest_task_rows(agent_id: str) -> list[dict[str, Any]]:
    return _fetch_all(
        """
        SELECT session_id, status, activity_at
          FROM (
                SELECT session_id, status, COALESCE(completed_at, started_at, created_at) AS activity_at, id,
                       ROW_NUMBER() OVER (
                           PARTITION BY session_id
                           ORDER BY COALESCE(completed_at, started_at, created_at) DESC, id DESC
                       ) AS rn
                  FROM tasks
                 WHERE agent_id = ? AND session_id IS NOT NULL
               ) ranked
         WHERE rn = 1
        """,
        (agent_id,),
        agent_ids=[agent_id],
    )


def list_dashboard_session_summaries(
    *,
    agent_ids: list[str],
    limit: int = 50,
    offset: int = 0,
    search: str | None = None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for agent_id in agent_ids:
        sessions = {str(row["session_id"]): row for row in _session_rows(agent_id)}
        query_aggs = {str(row["session_id"]): row for row in _query_aggregate_rows(agent_id)}
        latest_queries = {str(row["session_id"]): row for row in _latest_query_rows(agent_id)}
        task_aggs = {str(row["session_id"]): row for row in _task_aggregate_rows(agent_id)}
        latest_tasks = {str(row["session_id"]): row for row in _latest_task_rows(agent_id)}
        all_ids = set(sessions) | set(query_aggs) | set(latest_queries) | set(task_aggs) | set(latest_tasks)
        for session_id in all_ids:
            session = sessions.get(session_id, {})
            query_agg = query_aggs.get(session_id, {})
            latest_query = latest_queries.get(session_id, {})
            task_agg = task_aggs.get(session_id, {})
            latest_task = latest_tasks.get(session_id, {})
            total_cost = float(task_agg.get("total_cost_usd") or query_agg.get("total_cost_usd") or 0.0)
            item = {
                "agent_id": agent_id,
                "bot_id": agent_id,
                "session_id": session_id,
                "name": str(session.get("name") or "") or None,
                "user_id": session.get("user_id") or latest_query.get("user_id"),
                "created_at": _iso(
                    session.get("created_at") or latest_query.get("timestamp") or task_agg.get("last_execution_at")
                ),
                "last_used": _iso(
                    session.get("last_used") or query_agg.get("last_query_at") or task_agg.get("last_execution_at")
                ),
                "last_activity_at": _iso(
                    session.get("last_used") or query_agg.get("last_query_at") or task_agg.get("last_execution_at")
                ),
                "query_count": int(query_agg.get("query_count") or 0),
                "execution_count": int(task_agg.get("execution_count") or 0),
                "total_cost_usd": total_cost,
                "running_count": int(task_agg.get("running_count") or 0),
                "failed_count": int(task_agg.get("failed_count") or 0),
                "latest_status": str(latest_task.get("status") or "") or None,
                "latest_query_preview": _clip_preview(latest_query.get("query_text"), 120),
                "latest_response_preview": _clip_preview(latest_query.get("response_text"), 120),
                "latest_message_preview": _clip_preview(
                    latest_query.get("response_text") or latest_query.get("query_text"), 132
                ),
            }
            if search:
                haystack = " ".join(
                    filter(
                        None,
                        [
                            session_id,
                            cast(str | None, item["name"]),
                            cast(str | None, item["latest_query_preview"]),
                            cast(str | None, item["latest_response_preview"]),
                            cast(str | None, item["latest_message_preview"]),
                        ],
                    )
                ).lower()
                if _normalize_text(search) not in haystack:
                    continue
            items.append(item)
    items.sort(
        key=lambda item: _parse_iso(item.get("last_activity_at")) or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    return items[offset : offset + limit]


def _find_best_execution_match(executions: list[dict[str, Any]], query: dict[str, Any]) -> int:
    query_text = _normalize_text(query.get("query_text"))
    query_time = _parse_iso(query.get("timestamp")) or datetime.min.replace(tzinfo=UTC)
    best_index = -1
    best_diff = None
    best_task_id = None
    for index, execution in enumerate(executions):
        execution_text = _normalize_text(execution.get("query_text"))
        if query_text and execution_text != query_text:
            continue
        activity = _parse_iso(
            execution.get("completed_at") or execution.get("started_at") or execution.get("created_at")
        )
        if activity is None:
            continue
        diff = abs((activity - query_time).total_seconds())
        task_id = int(execution.get("task_id") or 0)
        if (
            best_diff is None
            or diff < best_diff
            or (diff == best_diff and (best_task_id is None or task_id < best_task_id))
        ):
            best_index = index
            best_diff = diff
            best_task_id = task_id
    if best_index >= 0:
        return best_index
    return 0 if executions else -1


def get_dashboard_session_detail(agent_id: str, session_id: str) -> dict[str, Any] | None:
    normalized = _normalize_agent_id(agent_id)
    summaries = list_dashboard_session_summaries(agent_ids=[normalized], limit=5000)
    summary = next((item for item in summaries if item["session_id"] == session_id), None)
    if summary is None:
        return None
    queries = _fetch_all(
        """
        SELECT id, user_id, timestamp, query_text, response_text, cost_usd, model, session_id, work_dir, error
          FROM query_history
         WHERE agent_id = ? AND session_id = ?
      ORDER BY timestamp ASC, id ASC
        """,
        (normalized, session_id),
        agent_ids=[normalized],
    )
    executions = list_dashboard_execution_summaries(agent_ids=[normalized], session_id=session_id, limit=500, offset=0)
    unmatched = list(executions)
    messages: list[dict[str, Any]] = []
    for query in queries:
        link_index = _find_best_execution_match(unmatched, query)
        linked_execution = unmatched.pop(link_index) if link_index >= 0 else None
        query_text = _clip_preview(query.get("query_text"), 20_000)
        response_text = _clip_preview(query.get("response_text"), 20_000)
        if query_text:
            messages.append(
                {
                    "id": f"query-{query['id']}-user",
                    "role": "user",
                    "text": query_text,
                    "timestamp": _iso(query.get("timestamp")),
                    "model": None,
                    "cost_usd": None,
                    "query_id": int(query["id"]),
                    "session_id": session_id,
                    "error": False,
                    "linked_execution": linked_execution,
                }
            )
        if response_text:
            messages.append(
                {
                    "id": f"query-{query['id']}-assistant",
                    "role": "assistant",
                    "text": response_text,
                    "timestamp": _iso(query.get("timestamp")),
                    "model": str(query.get("model") or "") or None,
                    "cost_usd": float(query.get("cost_usd") or 0.0),
                    "query_id": int(query["id"]),
                    "session_id": session_id,
                    "error": bool(query.get("error")),
                    "linked_execution": linked_execution,
                }
            )
    return {
        "summary": summary,
        "messages": messages,
        "orphan_executions": unmatched,
        "totals": {
            "messages": len(messages),
            "executions": len(executions),
            "tools": sum(int(item.get("tool_count") or 0) for item in executions),
            "cost_usd": float(summary.get("total_cost_usd") or 0.0),
        },
    }


def list_dashboard_dlq(
    *,
    agent_ids: list[str],
    limit: int = 50,
    retry_eligible: bool | None = None,
) -> list[dict[str, Any]]:
    resolved_agent_ids = _compact_agent_ids(agent_ids)
    if not resolved_agent_ids:
        return []
    params: list[Any] = list(resolved_agent_ids)
    clauses = [f"agent_id IN ({_placeholders(len(resolved_agent_ids))})"]
    if retry_eligible is not None:
        clauses.append("retry_eligible = ?")
        params.append(1 if retry_eligible else 0)
    params.append(max(1, int(limit)))
    rows = _fetch_all(
        f"""
        SELECT id, task_id, user_id, chat_id, agent_id, pod_name, query_text, model, error_message, error_class,
               attempt_count, original_created_at, failed_at, retry_eligible, retried_at, metadata_json
          FROM dead_letter_queue
         WHERE {" AND ".join(clauses)}
      ORDER BY failed_at DESC, id DESC
         LIMIT ?
        """,
        tuple(params),
        agent_ids=resolved_agent_ids,
    )
    return [
        {
            "id": int(row["id"]),
            "task_id": int(row.get("task_id") or 0),
            "user_id": int(row.get("user_id") or 0),
            "chat_id": int(row.get("chat_id") or 0),
            "agent_id": str(row.get("agent_id") or "") or None,
            "bot_id": str(row.get("agent_id") or "") or None,
            "pod_name": str(row.get("pod_name") or "") or None,
            "query_text": str(row.get("query_text") or ""),
            "model": str(row.get("model") or "") or None,
            "error_message": str(row.get("error_message") or "") or None,
            "error_class": str(row.get("error_class") or "") or None,
            "attempt_count": int(row.get("attempt_count") or 0),
            "original_created_at": _iso(row.get("original_created_at")),
            "failed_at": _iso(row.get("failed_at")),
            "retry_eligible": int(row.get("retry_eligible") or 0),
            "retried_at": _iso(row.get("retried_at")),
            "metadata_json": row.get("metadata_json") if isinstance(row.get("metadata_json"), str) else "{}",
        }
        for row in rows
    ]


def list_dashboard_schedules(agent_ids: list[str] | None = None) -> list[dict[str, Any]]:
    resolved = _resolve_agent_ids(agent_ids)
    if not resolved:
        return []
    rows = _fetch_all(
        f"""
        SELECT id, user_id, chat_id, agent_id, job_type, trigger_type, schedule_expr, timezone,
               payload_json, status, work_dir, provider_preference, model_preference,
               next_run_at, last_run_at, last_success_at, last_failure_at, config_version,
               verification_policy_json, notification_policy_json, dry_run_required,
               created_at, updated_at
          FROM scheduled_jobs
         WHERE agent_id IN ({_placeholders(len(resolved))})
      ORDER BY COALESCE(next_run_at, updated_at) ASC, id DESC
        """,
        tuple(resolved),
        agent_ids=resolved,
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        payload = _json_object(row.get("payload_json"))
        items.append(
            {
                "id": int(row["id"]),
                "bot_id": str(row.get("agent_id") or "") or None,
                "user_id": int(row.get("user_id") or 0),
                "chat_id": int(row.get("chat_id") or 0),
                "job_type": str(row.get("job_type") or ""),
                "trigger_type": str(row.get("trigger_type") or ""),
                "schedule_expr": str(row.get("schedule_expr") or ""),
                "cron_expression": str(row.get("schedule_expr") or ""),
                "timezone": str(row.get("timezone") or ""),
                "payload": payload,
                "command": str(payload.get("query") or payload.get("text") or payload.get("command") or ""),
                "description": str(payload.get("description") or payload.get("title") or ""),
                "created_at": _iso(row.get("created_at")),
                "updated_at": _iso(row.get("updated_at")),
                "enabled": 1 if str(row.get("status") or "").lower() == "active" else 0,
                "work_dir": str(row.get("work_dir") or "") or None,
                "status": str(row.get("status") or ""),
                "provider_preference": str(row.get("provider_preference") or "") or None,
                "model_preference": str(row.get("model_preference") or "") or None,
                "next_run_at": _iso(row.get("next_run_at")),
                "last_run_at": _iso(row.get("last_run_at")),
                "last_success_at": _iso(row.get("last_success_at")),
                "last_failure_at": _iso(row.get("last_failure_at")),
                "config_version": int(row.get("config_version") or 1),
                "verification_policy": _json_object(row.get("verification_policy_json")),
                "notification_policy": _json_object(row.get("notification_policy_json")),
                "dry_run_required": bool(row.get("dry_run_required")),
            }
        )
    return items


def list_dashboard_audit(
    *,
    agent_id: str,
    limit: int = 50,
    event_type: str | None = None,
    user_id: int | None = None,
) -> list[dict[str, Any]]:
    normalized = _normalize_agent_id(agent_id)
    params: list[Any] = [normalized]
    clauses = ["agent_id = ?"]
    if user_id is not None:
        clauses.append("user_id = ?")
        params.append(user_id)
    if event_type:
        clauses.append("event_type = ?")
        params.append(event_type)
    params.append(max(1, int(limit)))
    rows = _fetch_all(
        f"""
        SELECT id, timestamp, event_type, agent_id, pod_name, user_id, task_id,
               trace_id, details_json, cost_usd, duration_ms
          FROM audit_events
         WHERE {" AND ".join(clauses)}
      ORDER BY id DESC
         LIMIT ?
        """,
        tuple(params),
        agent_ids=[normalized],
    )
    return [
        {
            "id": int(row["id"]),
            "timestamp": _iso(row.get("timestamp")),
            "event_type": str(row.get("event_type") or ""),
            "agent_id": str(row.get("agent_id") or "") or None,
            "bot_id": str(row.get("agent_id") or "") or None,
            "pod_name": str(row.get("pod_name") or "") or None,
            "user_id": row.get("user_id"),
            "task_id": row.get("task_id"),
            "trace_id": str(row.get("trace_id") or "") or None,
            "details_json": "{}",
            "details": row.get("details_json") if isinstance(row.get("details_json"), dict) else {},
            "cost_usd": float(row.get("cost_usd") or 0.0) if row.get("cost_usd") is not None else None,
            "duration_ms": float(row.get("duration_ms") or 0.0) if row.get("duration_ms") is not None else None,
        }
        for row in rows
    ]


def _task_type_label(task_type: str) -> str:
    mapping = {
        "reply": "Reply",
        "research": "Research",
        "summarization": "Summary",
        "jira_update": "Jira",
        "triage": "Triage",
        "memory_lookup": "Memory",
        "content_generation": "Generation",
        "other": "Other",
    }
    return mapping.get(task_type, task_type)


def _classify_task_type(query_text: Any, response_text: Any, model: Any) -> str:
    text = " ".join(filter(None, [str(query_text or ""), str(response_text or ""), str(model or "")])).lower()
    if not text:
        return "other"
    if any(token in text for token in ("jira", "ticket", "issue", "backlog", "sprint", "kanban")):
        return "jira_update"
    if any(token in text for token in ("resumo", "summar", "recap", "tl;dr", "bullet", "sinteti")):
        return "summarization"
    if any(token in text for token in ("pesquis", "research", "buscar", "search", "fonte", "mercado", "compar")):
        return "research"
    if any(token in text for token in ("triage", "triagem", "classif", "prioriz", "categor")):
        return "triage"
    if any(token in text for token in ("memória", "memoria", "contexto", "recall", "remember", "lembr")):
        return "memory_lookup"
    if any(token in text for token in ("escrev", "gerar", "draft", "email", "post", "conteúdo", "conteudo", "copy")):
        return "content_generation"
    if any(token in text for token in ("respond", "resposta", "reply", "chat", "mensagem", "coment")):
        return "reply"
    return "other"


def get_dashboard_cost_insights(
    *,
    agent_ids: list[str],
    period: str = "30d",
    group_by: str = "auto",
    model: str | None = None,
    task_type: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict[str, Any]:
    resolved_agent_ids = _compact_agent_ids(agent_ids)
    now = _now_utc()
    if from_date or to_date:
        start = _parse_iso(f"{from_date}T00:00:00+00:00" if from_date else now.isoformat()) or now
        end_base = _parse_iso(f"{to_date}T00:00:00+00:00" if to_date else now.isoformat()) or now
        end = end_base + timedelta(days=1 if to_date else 0)
        applied_period = "custom"
    else:
        days = 7 if period == "7d" else 90 if period == "90d" else 30
        start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
        applied_period = period
    effective_group_by = group_by
    if effective_group_by == "auto":
        diff_days = max((end - start).total_seconds() / 86400, 1)
        effective_group_by = "hour" if diff_days <= 2 else "day" if diff_days <= 45 else "week"
    if not resolved_agent_ids:
        return {
            "overview": {
                "total_cost_usd": 0.0,
                "today_cost_usd": 0.0,
                "resolved_conversations": 0,
                "unresolved_conversations": 0,
                "avg_cost_per_resolved_conversation": 0.0,
                "median_cost_per_resolved_conversation": 0.0,
                "unresolved_cost_usd": 0.0,
                "total_queries": 0,
                "total_executions": 0,
                "top_model": None,
                "top_agent": None,
                "top_task_type": None,
            },
            "comparison": {
                "previous_total_cost_usd": 0.0,
                "total_delta_pct": None,
                "previous_avg_cost_per_resolved_conversation": 0.0,
                "avg_cost_per_resolved_delta_pct": None,
                "previous_today_cost_usd": None,
                "today_delta_pct": None,
                "previous_resolved_conversations": 0,
            },
            "peak_bucket": None,
            "time_series": [],
            "by_agent": [],
            "by_model": [],
            "by_task_type": [],
            "resolved_conversations": [],
            "conversation_rows": [],
            "available_models": [],
            "available_task_types": [],
            "applied_filters": {
                "agent_id": "all",
                "agent_ids": [],
                "period": applied_period,
                "from": from_date,
                "to": to_date,
                "model": model,
                "task_type": task_type,
                "group_by": effective_group_by,
            },
        }
    params: list[Any] = list(resolved_agent_ids) + [start, end]
    try:
        rows = _fetch_all(
            f"""
            SELECT id, agent_id, user_id, timestamp, query_text, response_text, cost_usd, model, session_id, error
              FROM query_history
             WHERE agent_id IN ({_placeholders(len(resolved_agent_ids))})
               AND timestamp >= ?
               AND timestamp < ?
          ORDER BY timestamp ASC, id ASC
            """,
            tuple(params),
            agent_ids=resolved_agent_ids,
        )
    except Exception:
        rows = []
    events: list[dict[str, Any]] = []
    for row in rows:
        item_task_type = _classify_task_type(row.get("query_text"), row.get("response_text"), row.get("model"))
        if model and str(row.get("model") or "") != model:
            continue
        if task_type and item_task_type != task_type:
            continue
        cost = float(row.get("cost_usd") or 0.0)
        if cost <= 0:
            continue
        events.append(
            {
                "id": f"query-{row['agent_id']}-{row['id']}",
                "agent_id": str(row["agent_id"]),
                "session_id": str(row.get("session_id") or "") or None,
                "timestamp": _iso(row.get("timestamp")),
                "cost_usd": cost,
                "model": str(row.get("model") or "") or None,
                "task_type": item_task_type,
                "latest_message_preview": _clip_preview(row.get("response_text") or row.get("query_text")),
            }
        )
    total_cost = sum(float(item["cost_usd"]) for item in events)
    by_agent: dict[str, float] = defaultdict(float)
    by_model: dict[str, float] = defaultdict(float)
    by_task: dict[str, float] = defaultdict(float)
    time_buckets: dict[str, dict[str, Any]] = {}
    session_totals: dict[tuple[str, str], dict[str, Any]] = {}
    for event in events:
        by_agent[str(event["agent_id"])] += float(event["cost_usd"])
        by_model[str(event.get("model") or "desconhecido")] += float(event["cost_usd"])
        by_task[str(event["task_type"])] += float(event["cost_usd"])
        timestamp = _parse_iso(event["timestamp"]) or now
        if effective_group_by == "hour":
            bucket = timestamp.strftime("%Y-%m-%dT%H:00:00")
            label = timestamp.strftime("%d/%m %Hh")
        elif effective_group_by == "week":
            week_start = (timestamp - timedelta(days=timestamp.weekday())).date().isoformat()
            bucket = week_start
            label = week_start
        else:
            bucket = timestamp.date().isoformat()
            label = bucket
        point = time_buckets.setdefault(
            bucket,
            {
                "bucket": bucket,
                "label": label,
                "total_cost_usd": 0.0,
                "by_agent": defaultdict(float),
                "by_model": defaultdict(float),
            },
        )
        point["total_cost_usd"] += float(event["cost_usd"])
        point["by_agent"][str(event["agent_id"])] += float(event["cost_usd"])
        point["by_model"][str(event.get("model") or "desconhecido")] += float(event["cost_usd"])
        if event.get("session_id"):
            key = (str(event["agent_id"]), str(event["session_id"]))
            session_entry = session_totals.setdefault(
                key,
                {
                    "agent_id": str(event["agent_id"]),
                    "session_id": str(event["session_id"]),
                    "name": None,
                    "cost_usd": 0.0,
                    "query_count": 0,
                    "execution_count": 0,
                    "resolved_at": event["timestamp"],
                    "dominant_model": event.get("model"),
                    "latest_message_preview": event.get("latest_message_preview"),
                    "last_activity_at": event["timestamp"],
                    "created_at": event["timestamp"],
                },
            )
            session_entry["cost_usd"] += float(event["cost_usd"])
            session_entry["query_count"] += 1
            session_entry["last_activity_at"] = event["timestamp"]
            session_entry["resolved_at"] = event["timestamp"]
            session_entry["latest_message_preview"] = (
                event.get("latest_message_preview") or session_entry["latest_message_preview"]
            )
    resolved_costs = [float(item["cost_usd"]) for item in session_totals.values()]
    resolved_conversations = [
        {
            "agent_id": item["agent_id"],
            "session_id": item["session_id"],
            "name": item["name"],
            "cost_usd": item["cost_usd"],
            "query_count": item["query_count"],
            "execution_count": item["execution_count"],
            "resolved_at": item["resolved_at"],
            "dominant_model": item["dominant_model"],
            "latest_message_preview": item["latest_message_preview"],
        }
        for item in sorted(
            session_totals.values(),
            key=lambda current: float(current["cost_usd"]),
            reverse=True,
        )
    ]
    conversation_rows = [
        {
            "agent_id": item["agent_id"],
            "session_id": item["session_id"],
            "name": item["name"],
            "status": "resolved",
            "cost_usd": item["cost_usd"],
            "query_count": item["query_count"],
            "execution_count": item["execution_count"],
            "resolved": True,
            "dominant_model": item["dominant_model"],
            "task_type_mix": [],
            "latest_message_preview": item["latest_message_preview"],
            "last_activity_at": item["last_activity_at"],
            "created_at": item["created_at"],
            "resolved_at": item["resolved_at"],
        }
        for item in resolved_conversations
    ]
    overview = {
        "total_cost_usd": total_cost,
        "today_cost_usd": sum(
            float(item["cost_usd"]) for item in events if (_parse_iso(item["timestamp"]) or now).date() == now.date()
        ),
        "resolved_conversations": len(resolved_conversations),
        "unresolved_conversations": 0,
        "avg_cost_per_resolved_conversation": (
            total_cost / len(resolved_conversations) if resolved_conversations else 0.0
        ),
        "median_cost_per_resolved_conversation": median(resolved_costs) if resolved_costs else 0.0,
        "unresolved_cost_usd": 0.0,
        "total_queries": len(events),
        "total_executions": 0,
        "top_model": max(by_model.items(), key=lambda item: item[1])[0] if by_model else None,
        "top_agent": max(by_agent.items(), key=lambda item: item[1])[0] if by_agent else None,
        "top_task_type": max(by_task.items(), key=lambda item: item[1])[0] if by_task else None,
    }
    peak = None
    if time_buckets:
        peak_bucket = max(time_buckets.values(), key=lambda item: float(item["total_cost_usd"]))
        peak = {
            "bucket": peak_bucket["bucket"],
            "label": peak_bucket["label"],
            "cost_usd": peak_bucket["total_cost_usd"],
            "top_agent": (
                max(peak_bucket["by_agent"].items(), key=lambda item: item[1])[0] if peak_bucket["by_agent"] else None
            ),
            "top_model": (
                max(peak_bucket["by_model"].items(), key=lambda item: item[1])[0] if peak_bucket["by_model"] else None
            ),
            "top_task_type": overview["top_task_type"],
        }
    return {
        "overview": overview,
        "comparison": {
            "previous_total_cost_usd": 0.0,
            "total_delta_pct": None,
            "previous_avg_cost_per_resolved_conversation": 0.0,
            "avg_cost_per_resolved_delta_pct": None,
            "previous_today_cost_usd": None,
            "today_delta_pct": None,
            "previous_resolved_conversations": 0,
        },
        "peak_bucket": peak,
        "time_series": [
            {
                "bucket": key,
                "label": value["label"],
                "total_cost_usd": value["total_cost_usd"],
                "by_agent": dict(value["by_agent"]),
                "by_model": dict(value["by_model"]),
            }
            for key, value in sorted(time_buckets.items())
        ],
        "by_agent": [
            {
                "agent_id": key,
                "cost_usd": value,
                "share_pct": (value / total_cost * 100) if total_cost else 0.0,
                "resolved_conversations": sum(1 for item in resolved_conversations if item["agent_id"] == key),
                "avg_cost_per_resolved_conversation": (
                    sum(float(item["cost_usd"]) for item in resolved_conversations if item["agent_id"] == key)
                    / max(sum(1 for item in resolved_conversations if item["agent_id"] == key), 1)
                )
                if resolved_conversations
                else 0.0,
                "query_count": sum(1 for item in events if item["agent_id"] == key),
                "execution_count": 0,
            }
            for key, value in sorted(by_agent.items(), key=lambda item: item[1], reverse=True)
        ],
        "by_model": [
            {
                "model": key,
                "cost_usd": value,
                "share_pct": (value / total_cost * 100) if total_cost else 0.0,
                "query_count": sum(1 for item in events if (item.get("model") or "desconhecido") == key),
                "execution_count": 0,
                "resolved_conversations": sum(1 for item in resolved_conversations if item["dominant_model"] == key),
            }
            for key, value in sorted(by_model.items(), key=lambda item: item[1], reverse=True)
        ],
        "by_task_type": [
            {
                "task_type": key,
                "label": _task_type_label(key),
                "cost_usd": value,
                "share_pct": (value / total_cost * 100) if total_cost else 0.0,
                "avg_cost_usd": value / max(sum(1 for item in events if item["task_type"] == key), 1),
                "count": sum(1 for item in events if item["task_type"] == key),
            }
            for key, value in sorted(by_task.items(), key=lambda item: item[1], reverse=True)
        ],
        "resolved_conversations": resolved_conversations,
        "conversation_rows": conversation_rows,
        "available_models": sorted(by_model.keys()),
        "available_task_types": [{"value": key, "label": _task_type_label(key)} for key in sorted(by_task.keys())],
        "applied_filters": {
            "agent_id": resolved_agent_ids[0] if len(resolved_agent_ids) == 1 else "all",
            "agent_ids": resolved_agent_ids,
            "period": applied_period,
            "from": from_date,
            "to": to_date,
            "model": model,
            "task_type": task_type,
            "group_by": effective_group_by,
        },
    }
