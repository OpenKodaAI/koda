"""Synthesis readiness checks for squad collaboration.

The gate is intentionally metadata-first: it decides whether a coordinator can
produce final synthesis from visible task results, replies, child runs and
handoff outcomes without reading hidden runtime state.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

SYNTHESIS_READINESS_SCHEMA_VERSION = "synthesis_readiness.v1"

_OPEN_TASK_STATUSES = {"pending", "claimed", "in_progress", "blocked"}
_OPEN_OBLIGATION_STATUSES = {"open"}
_OPEN_HANDOFF_STATUSES = {"requested", "accepted"}
_OPEN_CHILD_RUN_STATUSES = {"queued", "running", "retrying"}
_DISCLOSURE_REQUIRED_STATUSES = {"declined", "timed_out", "failed", "cancelled", "escalated"}


@dataclass(frozen=True)
class SynthesisReadiness:
    ready: bool
    status: str
    reason: str
    blockers: list[dict[str, Any]] = field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    timeout_disclosures: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SYNTHESIS_READINESS_SCHEMA_VERSION,
            "ready": self.ready,
            "status": self.status,
            "reason": self.reason,
            "blockers": [dict(item) for item in self.blockers],
            "evidence_refs": [dict(item) for item in self.evidence_refs],
            "timeout_disclosures": [dict(item) for item in self.timeout_disclosures],
        }


def evaluate_synthesis_readiness(
    *,
    tasks: Iterable[Any] | None = None,
    reply_obligations: Iterable[Any] | None = None,
    handoff_events: Iterable[Mapping[str, Any]] | None = None,
    child_runs: Iterable[Mapping[str, Any]] | None = None,
    result_messages: Iterable[Mapping[str, Any]] | None = None,
    declared_timeouts: Iterable[Mapping[str, Any]] | None = None,
) -> SynthesisReadiness:
    blockers: list[dict[str, Any]] = []
    evidence_refs: list[dict[str, Any]] = []
    disclosures = [_dict(item) for item in declared_timeouts or []]

    for task in tasks or []:
        task_id = _field(task, "id", "task_id")
        status = _string(_field(task, "status")).lower()
        if status in _OPEN_TASK_STATUSES:
            blockers.append({"kind": "task", "id": task_id, "status": status, "reason": "open_task"})
        elif status in _DISCLOSURE_REQUIRED_STATUSES and not _has_disclosure(disclosures, "task", task_id):
            blockers.append({"kind": "task", "id": task_id, "status": status, "reason": "missing_terminal_disclosure"})
        elif task_id:
            evidence_refs.append({"kind": "task", "id": task_id, "status": status})

    for obligation in reply_obligations or []:
        obligation_id = _field(obligation, "id", "obligation_id", "obligationId")
        status = _string(_field(obligation, "status")).lower()
        if status in _OPEN_OBLIGATION_STATUSES:
            blockers.append(
                {"kind": "reply_obligation", "id": obligation_id, "status": status, "reason": "open_obligation"}
            )
        elif status in _DISCLOSURE_REQUIRED_STATUSES and not _has_disclosure(
            disclosures, "reply_obligation", obligation_id
        ):
            blockers.append(
                {
                    "kind": "reply_obligation",
                    "id": obligation_id,
                    "status": status,
                    "reason": "missing_terminal_disclosure",
                }
            )
        elif obligation_id:
            evidence_refs.append({"kind": "reply_obligation", "id": obligation_id, "status": status})

    for event in handoff_events or []:
        payload = _dict(_dict(event).get("payload")) or _dict(event)
        handoff_id = _string(payload.get("handoff_id") or payload.get("id"))
        status = _string(payload.get("status")).lower()
        if status in _OPEN_HANDOFF_STATUSES:
            blockers.append({"kind": "handoff_event", "id": handoff_id, "status": status, "reason": "open_handoff"})
        elif status in _DISCLOSURE_REQUIRED_STATUSES and not _has_disclosure(disclosures, "handoff_event", handoff_id):
            blockers.append(
                {
                    "kind": "handoff_event",
                    "id": handoff_id,
                    "status": status,
                    "reason": "missing_terminal_disclosure",
                }
            )
        elif handoff_id:
            evidence_refs.append({"kind": "handoff_event", "id": handoff_id, "status": status})

    for child in child_runs or []:
        child_payload = _dict(child)
        child_id = _string(child_payload.get("child_run_id") or child_payload.get("id"))
        status = _string(child_payload.get("status")).lower()
        if status in _OPEN_CHILD_RUN_STATUSES:
            blockers.append({"kind": "child_run", "id": child_id, "status": status, "reason": "open_child_run"})
        elif status in _DISCLOSURE_REQUIRED_STATUSES and not _has_disclosure(disclosures, "child_run", child_id):
            blockers.append(
                {"kind": "child_run", "id": child_id, "status": status, "reason": "missing_terminal_disclosure"}
            )
        elif child_id:
            evidence_refs.append({"kind": "child_run", "id": child_id, "status": status})

    for message in result_messages or []:
        msg = _dict(message)
        message_type = _string(msg.get("type") or msg.get("message_type"))
        if message_type in {"task_result", "delegation_result", "agent_reply", "coordinator_synthesis"}:
            evidence_refs.append(
                {
                    "kind": message_type,
                    "id": _string(msg.get("id") or msg.get("message_id")),
                    "agent_id": _string(msg.get("from") or msg.get("from_agent")),
                }
            )

    ready = not blockers
    return SynthesisReadiness(
        ready=ready,
        status="ready" if ready else "blocked",
        reason="evidence_terminal_or_declared" if ready else "open_or_undisclosed_work",
        blockers=blockers,
        evidence_refs=evidence_refs,
        timeout_disclosures=disclosures,
    )


def synthesis_gate_metric(*, gate: str, result: SynthesisReadiness) -> None:
    try:
        from koda.services.metrics import SQUAD_SYNTHESIS_GATE

        reason = result.blockers[0]["reason"] if result.blockers else result.reason
        SQUAD_SYNTHESIS_GATE.labels(gate=str(gate or "unknown"), status=result.status, reason=str(reason)).inc()
    except Exception:
        return


def _field(value: Any, *names: str) -> Any:
    if isinstance(value, Mapping):
        for name in names:
            if name in value:
                return value[name]
        return None
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return None


def _dict(value: Any) -> dict[str, Any]:
    return {str(key): item for key, item in value.items()} if isinstance(value, Mapping) else {}


def _string(value: Any) -> str:
    return str(value or "").strip()


def _has_disclosure(disclosures: list[dict[str, Any]], kind: str, item_id: Any) -> bool:
    normalized_id = _string(item_id)
    for item in disclosures:
        if _string(item.get("kind")) != kind:
            continue
        if not normalized_id or _string(item.get("id")) == normalized_id:
            return True
    return False
