"""Fire-and-forget audit event emission."""

import asyncio
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import koda.config as config_module
from koda.knowledge.config import (
    KNOWLEDGE_V2_EMBEDDING_DIMENSION,
    KNOWLEDGE_V2_POSTGRES_DSN,
    KNOWLEDGE_V2_POSTGRES_SCHEMA,
)
from koda.knowledge.v2.common import get_shared_postgres_backend
from koda.logging_config import get_logger

log = get_logger(__name__)

_dropped_events: int = 0

TRACE_SCHEMA_VERSION = 1
_REDACTED = "[REDACTED]"
_MAX_AUDIT_TEXT_LEN = 12000

_SENSITIVE_KEY_RE = re.compile(
    r"(authorization|token|secret|password|passwd|cookie|api[_-]?key|access[_-]?key|credentials?)",
    re.I,
)
_INLINE_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(authorization\s*:\s*)(bearer\s+[a-z0-9._\-]+)"),
    re.compile(r"(?i)\b(bearer\s+)([a-z0-9._\-]+)"),
    re.compile(
        r"(?i)\b((?:api[_-]?key|access[_-]?token|refresh[_-]?token|secret|password|passwd|cookie)\s*[=:]\s*)([^,\s]+)"
    ),
    re.compile(r"(?i)([?&](?:api[_-]?key|access[_-]?token|token|secret|password)=)([^&\s]+)"),
    re.compile(
        r"(?i)\b((?:api[_-]?key|access[_-]?token|refresh[_-]?token|secret|password|passwd|cookie)\s*=\s*)([^,\s]+)"
    ),
)


def _truncate_text(value: str) -> tuple[str, bool]:
    if len(value) <= _MAX_AUDIT_TEXT_LEN:
        return value, False
    return value[:_MAX_AUDIT_TEXT_LEN] + "\n… (truncated)", True


def _redact_string(value: str) -> tuple[str, bool]:
    redacted = value
    changed = False
    for pattern in _INLINE_SECRET_PATTERNS:
        redacted, count = pattern.subn(rf"\1{_REDACTED}", redacted)
        if count:
            changed = True
    truncated, was_truncated = _truncate_text(redacted)
    return truncated, changed or was_truncated


def _sanitize_payload(value: Any, path: str = "") -> tuple[Any, list[str]]:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        redacted_fields: list[str] = []
        for key, inner in value.items():
            current_path = f"{path}.{key}" if path else key
            if _SENSITIVE_KEY_RE.search(key):
                sanitized[key] = _REDACTED
                redacted_fields.append(current_path)
                continue
            clean_value, nested = _sanitize_payload(inner, current_path)
            sanitized[key] = clean_value
            redacted_fields.extend(nested)
        return sanitized, redacted_fields

    if isinstance(value, list):
        sanitized_items: list[Any] = []
        nested_redactions: list[str] = []
        for index, inner in enumerate(value):
            clean_value, nested = _sanitize_payload(inner, f"{path}[{index}]")
            sanitized_items.append(clean_value)
            nested_redactions.extend(nested)
        return sanitized_items, nested_redactions

    if isinstance(value, str):
        clean_value, changed = _redact_string(value)
        return clean_value, [path] if changed and path else []

    return value, []


def _prepare_details(details: dict[str, Any]) -> dict[str, Any]:
    sanitized_value, redacted_fields = _sanitize_payload(details)
    sanitized = cast(dict[str, Any], sanitized_value)
    if redacted_fields and isinstance(sanitized, dict) and "redactions" not in sanitized:
        sanitized = {
            **sanitized,
            "redactions": {
                "count": len(redacted_fields),
                "fields": redacted_fields,
            },
        }
    return sanitized


@dataclass
class AuditEvent:
    """Structured audit event."""

    event_type: str
    agent_id: str | None = None
    pod_name: str | None = None
    user_id: int | None = None
    task_id: int | None = None
    trace_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    cost_usd: float | None = None
    duration_ms: float | None = None
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()
        if not self.agent_id:
            self.agent_id = config_module.AGENT_ID
        if not self.pod_name:
            self.pod_name = config_module.POD_NAME


def _primary_mode_requested() -> bool:
    return config_module.STATE_BACKEND == "postgres"


def _primary_audit_backend() -> Any | None:
    if not _primary_mode_requested():
        return None
    backend = get_shared_postgres_backend(
        agent_id=config_module.AGENT_ID,
        dsn=KNOWLEDGE_V2_POSTGRES_DSN,
        schema=KNOWLEDGE_V2_POSTGRES_SCHEMA,
        embedding_dimension=KNOWLEDGE_V2_EMBEDDING_DIMENSION,
    )
    return backend if backend.enabled else None


async def _insert_audit_primary(event: AuditEvent) -> None:
    backend = _primary_audit_backend()
    if backend is None:
        raise RuntimeError("primary audit backend unavailable")
    await backend.persist_audit_event(
        event_type=event.event_type,
        timestamp=event.timestamp,
        pod_name=str(event.pod_name or ""),
        user_id=event.user_id,
        task_id=event.task_id,
        trace_id=event.trace_id,
        details=_prepare_details(event.details),
        cost_usd=event.cost_usd,
        duration_ms=event.duration_ms,
    )


def _run_coro_sync(coro: Any) -> Any:
    """Delegate to the canonical ``koda.state.primary.run_coro_sync``.

    The primary-state helper clears the shared asyncpg pool cache around
    each transient ``asyncio.run`` boundary. Audit inserts reuse the same
    backend, so keeping them on the same bridge avoids the pool pathology
    where one insert's transient loop leaves a dangling pool that the next
    insert tries to acquire from (``InterfaceError: another operation in
    progress``).
    """
    from koda.state.primary import run_coro_sync as _primary_run_coro_sync

    return _primary_run_coro_sync(coro)


def _insert_audit(event: AuditEvent) -> None:
    """Synchronous insert into the active audit backend."""
    backend = _primary_audit_backend()
    if backend is not None:
        try:
            _run_coro_sync(_insert_audit_primary(event))
            return
        except Exception:
            log.warning("audit_primary_insert_failed", event_type=event.event_type, exc_info=True)
            return
    log.warning("audit_primary_backend_unavailable", event_type=event.event_type)


def emit(event: AuditEvent) -> None:
    """Fire-and-forget audit event emission.

    Runs the DB insert off the request path whenever possible. Failures are
    silently logged — audit must never break the request path itself.

    Note on loop/thread safety: callers frequently run inside a sync handler
    that was itself bridged from aiohttp via `run_coro_sync` on a different
    thread/loop. Scheduling `create_task` against the aiohttp loop from that
    nested context produces "Future attached to a different loop" errors and
    can corrupt concurrent asyncpg operations. We therefore dispatch through
    `run_in_executor` unconditionally so the async insert gets a fresh loop
    in a worker thread, independent of the caller's context.
    """
    global _dropped_events
    try:
        backend = _primary_audit_backend()
        if backend is None:
            _insert_audit(event)
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            loop.run_in_executor(None, _insert_audit, event)
        else:
            _insert_audit(event)
    except Exception:
        _dropped_events += 1
        log.warning("audit_event_dropped", event_type=event.event_type, total_dropped=_dropped_events)


def emit_task_lifecycle(
    event_type: str,
    *,
    user_id: int | None = None,
    task_id: int | None = None,
    cost_usd: float | None = None,
    duration_ms: float | None = None,
    **details: object,
) -> None:
    """Convenience for task lifecycle events."""
    emit(
        AuditEvent(
            event_type=event_type,
            user_id=user_id,
            task_id=task_id,
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            details=dict(details),
        )
    )


def emit_security(
    event_type: str,
    *,
    user_id: int | None = None,
    **details: object,
) -> None:
    """Convenience for security events."""
    emit(
        AuditEvent(
            event_type=event_type,
            user_id=user_id,
            details=dict(details),
        )
    )


def emit_cost(
    *,
    user_id: int | None = None,
    task_id: int | None = None,
    cost_usd: float,
    model: str | None = None,
    **details: object,
) -> None:
    """Convenience for cost events."""
    d = dict(details)
    if model:
        d["model"] = model
    emit(
        AuditEvent(
            event_type="cost.incurred",
            user_id=user_id,
            task_id=task_id,
            cost_usd=cost_usd,
            details=d,
        )
    )


def emit_execution_trace(
    *,
    user_id: int | None = None,
    task_id: int | None = None,
    trace_id: str | None = None,
    query_text: str | None = None,
    response_text: str | None = None,
    model: str | None = None,
    session_id: str | None = None,
    work_dir: str | None = None,
    status: str,
    cost_usd: float | None = None,
    duration_ms: float | None = None,
    stop_reason: str | None = None,
    warnings: list[str] | None = None,
    tool_uses: list[dict[str, Any]] | None = None,
    tools: list[dict[str, Any]] | None = None,
    timeline: list[dict[str, Any]] | None = None,
    reasoning_summary: list[str] | None = None,
    raw_artifacts: dict[str, Any] | None = None,
    grounding: dict[str, Any] | None = None,
    confidence_reports: list[dict[str, Any]] | None = None,
    error_message: str | None = None,
    attempt: int | None = None,
    max_attempts: int | None = None,
    user_context: dict[str, Any] | None = None,
) -> None:
    details = {
        "trace_version": TRACE_SCHEMA_VERSION,
        "schema": "execution_trace",
        "request": {
            "query_text": query_text,
            "model": model,
            "session_id": session_id,
            "work_dir": work_dir,
            "user_context": user_context or {},
        },
        "assistant": {
            "response_text": response_text,
            "tool_uses": tool_uses or [],
        },
        "tools": tools or [],
        "timeline": timeline or [],
        "runtime": {
            "status": status,
            "stop_reason": stop_reason,
            "warnings": warnings or [],
            "attempt": attempt,
            "max_attempts": max_attempts,
            "reasoning_summary": reasoning_summary or [],
            "confidence_reports": confidence_reports or [],
            "error_message": error_message,
        },
        "grounding": grounding or {},
        "raw_artifacts": raw_artifacts or {},
    }
    emit(
        AuditEvent(
            event_type="task.execution_trace",
            user_id=user_id,
            task_id=task_id,
            trace_id=trace_id,
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            details=details,
        )
    )


async def cleanup_expired_audit_events() -> int:
    """Delete audit events older than ``AUDIT_RETENTION_DAYS``.

    Returns the number of deleted rows, or ``0`` when the backend does not
    support retention cleanup.
    """
    backend = _primary_audit_backend()
    if backend is None:
        log.warning("audit_cleanup_skipped: no primary backend available")
        return 0

    retention_days: int = config_module.AUDIT_RETENTION_DAYS
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    cutoff_iso = cutoff.isoformat()

    cleanup_fn = getattr(backend, "delete_audit_events_before", None)
    if cleanup_fn is None:
        log.warning("audit_cleanup_skipped: backend does not implement delete_audit_events_before")
        return 0

    try:
        deleted: int = await cleanup_fn(cutoff_iso)
        log.info(
            "audit_cleanup_completed",
            retention_days=retention_days,
            cutoff=cutoff_iso,
            deleted=deleted,
        )
        return deleted
    except Exception:
        log.warning("audit_cleanup_failed", exc_info=True)
        return 0


def get_audit_log(
    limit: int = 50,
    user_id: int | None = None,
    event_type: str | None = None,
) -> list[dict]:
    """Query audit log entries. Returns list of dicts."""
    backend = _primary_audit_backend()
    if backend is not None:
        try:
            return cast(
                list[dict],
                _run_coro_sync(backend.list_audit_events(limit=limit, user_id=user_id, event_type=event_type)),
            )
        except Exception:
            log.warning("audit_primary_query_failed", exc_info=True)
    return []
