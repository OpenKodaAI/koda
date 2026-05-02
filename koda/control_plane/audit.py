"""Structured audit-event emit helpers shared by control-plane components.

Multiple call sites (manager pause/activate, supervisor crash-loop detection,
future quota/policy violations) all need to write a row to ``audit_events``
without coupling to the runtime/dashboard SQL layer. This module exposes the
single best-effort emit so the row shape stays consistent and a future move
to a partitioned per-workspace audit table only changes one file.
"""

from __future__ import annotations

import json
from typing import Any

from koda.logging_config import get_logger

from .database import execute, now_iso

log = get_logger(__name__)


def record_audit_event(
    agent_id: str,
    *,
    event_type: str,
    details: dict[str, Any] | None = None,
    user_id: int | None = None,
    task_id: int | None = None,
    trace_id: str = "",
    cost_usd: float | None = None,
    duration_ms: float | None = None,
) -> None:
    """Append a structured row to ``audit_events``.

    Failure to emit must never block the action that triggered it, so any
    exception is swallowed with a log line. Blank ``agent_id`` is rejected
    because the table has ``NOT NULL`` on that column.
    """
    scope = str(agent_id or "").strip()
    if not scope or not str(event_type or "").strip():
        return
    payload = json.dumps(details or {}, ensure_ascii=False, sort_keys=True)
    try:
        execute(
            """
            INSERT INTO audit_events (
                agent_id, timestamp, event_type, pod_name, user_id, task_id,
                trace_id, details_json, cost_usd, duration_ms
            )
            VALUES (?, ?, ?, '', ?, ?, ?, ?::jsonb, ?, ?)
            """,
            (
                scope,
                now_iso(),
                str(event_type).strip(),
                user_id,
                task_id,
                str(trace_id or "").strip(),
                payload,
                cost_usd,
                duration_ms,
            ),
        )
    except Exception:
        log.exception(
            "control_plane_audit_emit_failed",
            agent_id=scope,
            event_type=event_type,
        )
