"""Dashboard-facing approval broker.

Adapts the Telegram-native approval queue (``koda.utils.approval``) into a
read / resolve / stream surface that the dashboard can drive. Pending
approvals are still owned by ``koda.utils.approval`` (in-memory +
``state.pending_approvals`` JSON). This module provides three capabilities on
top of that store:

* ``list_pending_for_session`` — enumerate pending agent-cmd approvals
  scoped to an agent + session.
* ``resolve_approval`` — submit a decision (``approved``/``denied``/
  ``approved_scope``) from outside Telegram.
* ``publish_approval_required`` / ``publish_approval_resolved`` — emit
  runtime SSE events so connected dashboard clients can react in real
  time.

The broker does not store state itself. Keeping state in one place avoids
divergence between the Telegram flow and the dashboard flow.
"""

from __future__ import annotations

import asyncio
from typing import Any

from koda.logging_config import get_logger

log = get_logger(__name__)


_APPROVAL_REQUIRED_EVENT = "approval_required"
_APPROVAL_RESOLVED_EVENT = "approval_resolved"


def _runtime_broker() -> Any | None:
    """Return the running runtime event broker or None if unavailable."""
    try:
        from koda.services.runtime.controller import get_runtime_controller
    except Exception:
        log.debug("approval_broker_runtime_controller_import_failed", exc_info=True)
        return None
    try:
        controller = get_runtime_controller()
    except Exception:
        log.debug("approval_broker_runtime_controller_unavailable", exc_info=True)
        return None
    events = getattr(controller, "events", None)
    return events


def _approval_summary(op_id: str, op: dict[str, Any]) -> dict[str, Any]:
    requests = [_serialize_request(item) for item in (op.get("requests") or []) if isinstance(item, dict)]
    task_id_raw = op.get("task_id")
    try:
        task_id = int(task_id_raw) if task_id_raw is not None else None
    except (TypeError, ValueError):
        task_id = None
    return {
        "approval_id": op_id,
        "op_type": "agent_cmd",
        "agent_id": str(op.get("agent_id") or "").strip() or None,
        "session_id": str(op.get("session_id") or "").strip() or None,
        "chat_id": op.get("chat_id"),
        "user_id": op.get("user_id"),
        "task_id": task_id,
        "description": str(op.get("description") or ""),
        "preview_text": str(op.get("preview_text") or "") or None,
        "requests": requests,
        "created_at": op.get("timestamp"),
        "decision": op.get("decision"),
    }


def _serialize_request(request: dict[str, Any]) -> dict[str, Any]:
    envelope = request.get("envelope")
    envelope_payload: dict[str, Any] | None = None
    if envelope is not None:
        if hasattr(envelope, "__dataclass_fields__"):
            from dataclasses import asdict

            envelope_payload = asdict(envelope)
        elif isinstance(envelope, dict):
            envelope_payload = dict(envelope)

    approval_scope = request.get("approval_scope")
    scope_payload: dict[str, Any] | None = None
    if approval_scope is not None:
        if hasattr(approval_scope, "__dataclass_fields__"):
            from dataclasses import asdict

            scope_payload = asdict(approval_scope)
        elif isinstance(approval_scope, dict):
            scope_payload = dict(approval_scope)

    payload: dict[str, Any] = {}
    if envelope_payload:
        payload["envelope"] = envelope_payload
    if scope_payload:
        payload["approval_scope"] = scope_payload
    return payload


def list_pending_for_session(
    *,
    agent_id: str,
    session_id: str | None,
) -> list[dict[str, Any]]:
    """Return pending agent-cmd approvals scoped to ``agent_id``/``session_id``."""
    from koda.utils.approval import _PENDING_AGENT_CMD_OPS

    normalized_agent = str(agent_id or "").strip()
    normalized_session = str(session_id or "").strip() or None
    items: list[dict[str, Any]] = []
    for op_id, op in _PENDING_AGENT_CMD_OPS.items():
        if op.get("decision") is not None:
            continue
        if normalized_agent and str(op.get("agent_id") or "") != normalized_agent:
            continue
        if normalized_session is not None and str(op.get("session_id") or "") != normalized_session:
            continue
        items.append(_approval_summary(op_id, op))
    items.sort(key=lambda item: float(item.get("created_at") or 0.0))
    return items


def find_pending(
    *,
    agent_id: str,
    session_id: str | None,
    task_id: int | None = None,
) -> str | None:
    """Return the ``op_id`` of the first pending approval matching the scope.

    When ``task_id`` is provided, only approvals bound to that task are
    considered; otherwise the oldest pending approval for the session is
    returned. This avoids attributing an unrelated task's pending approval
    to the wrong execution summary.
    """
    pending = list_pending_for_session(agent_id=agent_id, session_id=session_id)
    if task_id is not None:
        for item in pending:
            if int(item.get("task_id") or 0) == task_id:
                return str(item["approval_id"])
        return None
    return str(pending[0]["approval_id"]) if pending else None


async def resolve_approval(
    *,
    approval_id: str,
    decision: str,
    rationale: str | None = None,
) -> dict[str, Any]:
    """Resolve a pending approval from the dashboard.

    Valid decisions mirror the Telegram callback: ``approved``,
    ``approved_scope``, ``denied``. Returns the updated summary or raises
    ``KeyError`` when the approval id is unknown.
    """
    from koda.utils.approval import (
        _PENDING_AGENT_CMD_OPS,
        _issue_agent_approval_grants,
        resolve_agent_cmd_approval,
    )

    normalized = (decision or "").strip().lower()
    mapping = {
        "approve": "approved",
        "approved": "approved",
        "scope": "approved_scope",
        "approve_scope": "approved_scope",
        "approved_scope": "approved_scope",
        "deny": "denied",
        "denied": "denied",
        "reject": "denied",
    }
    resolved_decision = mapping.get(normalized)
    if resolved_decision is None:
        raise ValueError(f"invalid approval decision: {decision!r}")

    op = _PENDING_AGENT_CMD_OPS.get(approval_id)
    if op is None:
        raise KeyError(approval_id)

    grants: list[dict[str, Any]] = []
    if resolved_decision in {"approved", "approved_scope"}:
        grants = _issue_agent_approval_grants(
            user_id=int(op.get("user_id") or 0),
            agent_id=str(op.get("agent_id") or "default"),
            session_id=str(op.get("session_id") or "").strip() or None,
            chat_id=op.get("chat_id"),
            requests=list(op.get("requests") or []),
            decision=resolved_decision,
            issued_by_op_id=approval_id,
        )

    resolve_agent_cmd_approval(approval_id, resolved_decision, grants=grants)

    summary = _approval_summary(approval_id, op)
    summary["decision"] = resolved_decision
    summary["rationale"] = rationale or None
    summary["grants_issued"] = len(grants)
    await publish_approval_resolved(
        approval_id=approval_id,
        decision=resolved_decision,
        session_id=summary.get("session_id"),
        rationale=rationale,
    )
    return summary


async def publish_approval_required(
    *,
    approval_id: str,
    session_id: str | None,
    task_id: int | None = None,
    description: str = "",
    preview_text: str | None = None,
    reasons: list[str] | None = None,
) -> None:
    """Emit a runtime event when a new approval is created."""
    broker = _runtime_broker()
    if broker is None:
        return
    try:
        await broker.publish(
            task_id=task_id,
            env_id=None,
            attempt=None,
            phase=None,
            event_type=_APPROVAL_REQUIRED_EVENT,
            severity="warning",
            payload={
                "approval_id": approval_id,
                "session_id": session_id,
                "description": description,
                "preview_text": preview_text,
                "reasons": list(reasons or []),
            },
        )
    except Exception:
        log.warning("approval_broker_publish_required_failed", exc_info=True)


async def publish_approval_resolved(
    *,
    approval_id: str,
    decision: str,
    session_id: str | None,
    task_id: int | None = None,
    rationale: str | None = None,
) -> None:
    """Emit a runtime event when an approval is resolved."""
    broker = _runtime_broker()
    if broker is None:
        return
    try:
        await broker.publish(
            task_id=task_id,
            env_id=None,
            attempt=None,
            phase=None,
            event_type=_APPROVAL_RESOLVED_EVENT,
            severity="info",
            payload={
                "approval_id": approval_id,
                "decision": decision,
                "session_id": session_id,
                "rationale": rationale,
            },
        )
    except Exception:
        log.warning("approval_broker_publish_resolved_failed", exc_info=True)


def spawn_publish_required(
    *,
    approval_id: str,
    session_id: str | None,
    task_id: int | None = None,
    description: str = "",
    preview_text: str | None = None,
    reasons: list[str] | None = None,
) -> None:
    """Fire-and-forget helper for call sites that are already async-aware."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(
        publish_approval_required(
            approval_id=approval_id,
            session_id=session_id,
            task_id=task_id,
            description=description,
            preview_text=preview_text,
            reasons=reasons,
        )
    )


def spawn_publish_resolved(
    *,
    approval_id: str,
    decision: str,
    session_id: str | None,
    task_id: int | None = None,
    rationale: str | None = None,
) -> None:
    """Fire-and-forget helper for sync call sites."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(
        publish_approval_resolved(
            approval_id=approval_id,
            decision=decision,
            session_id=session_id,
            task_id=task_id,
            rationale=rationale,
        )
    )
