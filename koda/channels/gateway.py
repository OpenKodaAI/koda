"""Phase 6 channel gateway contracts and fail-closed helpers."""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast

from koda.channels.types import ChannelIdentity, IncomingMessage
from koda.config import AGENT_ID
from koda.logging_config import get_logger

log = get_logger(__name__)

CHANNEL_GATEWAY_SCHEMA_VERSION = "channel_gateway.v1"
PAIRING_CODE_TTL_SECONDS = 15 * 60
# A sender gets this many failed pairing attempts per lockout window; the last
# one locks the sender out of pairing for the window.
PAIRING_MAX_FAILURES = 5
PAIRING_LOCKOUT_SECONDS = 15 * 60
_MAX_TEXT_PREVIEW = 240

GatewayStatus = Literal["pending", "paired", "allowed", "blocked", "revoked"]
GatewayDecision = Literal["allow", "queue_for_pairing", "deny", "paired"]
GatewaySeverity = Literal["info", "warning", "error"]

_LAST_DECISIONS: dict[str, dict[str, Any]] = {}
# Per-sender pairing limits, keyed by "<agent_id>:<identity_id>" (monotonic seconds).
_PAIRING_FAILURES: dict[str, list[float]] = {}
_PAIRING_LOCKED_UNTIL: dict[str, float] = {}


@dataclass(frozen=True, slots=True)
class ChannelGatewayError:
    """User-facing error envelope for channel gateway decisions."""

    code: str
    category: str
    message: str
    retryable: bool
    user_action: str
    trace_id: str | None = None
    run_graph_node_id: str | None = None
    detail_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ChannelGatewayDecision:
    """Authorization result for an inbound channel message."""

    schema_version: str
    decision: GatewayDecision
    allowed: bool
    identity_id: str
    channel_type: str
    channel_id: str
    user_id: str
    status: GatewayStatus
    reason_code: str
    error: ChannelGatewayError | None = None
    event_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.error is not None:
            payload["error"] = self.error.to_dict()
        return payload


@dataclass(frozen=True, slots=True)
class ChannelGatewayIdentityRecord:
    """Persisted identity for one sender/conversation pair."""

    schema_version: str
    identity_id: str
    agent_id: str
    channel_type: str
    channel_id: str
    user_id: str
    display_name: str
    is_group: bool = False
    status: GatewayStatus = "pending"
    scopes: list[str] = field(default_factory=lambda: ["message"])
    source: str = "channel_gateway"
    allowed_by: str = ""
    blocked_by: str = ""
    revoked_by: str = ""
    created_at: str = ""
    updated_at: str = ""
    last_seen_at: str = ""
    paired_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_agent_id(agent_id: str | None) -> str:
    return (agent_id or AGENT_ID or "default").strip().upper() or "DEFAULT"


def _stable_id(prefix: str, *parts: object) -> str:
    raw = "\x1f".join(str(part or "") for part in parts)
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]}"


def identity_id_for(agent_id: str | None, identity: ChannelIdentity) -> str:
    normalized = _normalize_agent_id(agent_id)
    return _stable_id(
        "chgid",
        normalized,
        identity.channel_type.lower(),
        identity.channel_id,
        identity.user_id,
    )


def _event_id(agent_id: str, event_type: str, identity_id: str) -> str:
    return _stable_id("chgev", agent_id, event_type, identity_id, time.time_ns())


def _safe_text(value: object, *, limit: int = _MAX_TEXT_PREVIEW) -> str:
    text = str(value or "").replace("\n", " ").strip()
    return text[:limit] + ("..." if len(text) > limit else "")


def _primary_backend(agent_id: str) -> Any | None:
    try:
        from koda.state.primary import get_primary_state_backend

        return get_primary_state_backend(agent_id=agent_id)
    except Exception:
        return None


def _run_primary(coro: Any) -> Any | None:
    try:
        from koda.state.primary import run_coro_sync

        return run_coro_sync(coro)
    except Exception:
        log.debug("channel_gateway_primary_operation_skipped", exc_info=True)
        return None


def _list_primary_identities(agent_id: str) -> list[dict[str, Any]] | None:
    backend = _primary_backend(agent_id)
    if backend is None or not hasattr(backend, "list_channel_gateway_identities"):
        return None
    result = _run_primary(backend.list_channel_gateway_identities(agent_id))
    return list(result) if isinstance(result, list) else None


def _list_primary_unknown_senders(agent_id: str) -> list[dict[str, Any]] | None:
    backend = _primary_backend(agent_id)
    if backend is None or not hasattr(backend, "list_channel_unknown_senders"):
        return None
    result = _run_primary(backend.list_channel_unknown_senders(agent_id))
    return list(result) if isinstance(result, list) else None


def _list_primary_pairing_codes(agent_id: str) -> list[dict[str, Any]] | None:
    backend = _primary_backend(agent_id)
    if backend is None or not hasattr(backend, "list_channel_pairing_codes"):
        return None
    result = _run_primary(backend.list_channel_pairing_codes(agent_id))
    return list(result) if isinstance(result, list) else None


# Gateway state lives only in the primary backend, one row per identity, sender or
# code. Without a primary backend nothing is stored: unknown senders stay denied.


def _persist_identity(agent_id: str, record: dict[str, Any]) -> None:
    backend = _primary_backend(agent_id)
    if backend is not None and hasattr(backend, "upsert_channel_gateway_identity"):
        _run_primary(backend.upsert_channel_gateway_identity(agent_id, record))


def _persist_unknown_sender(agent_id: str, payload: dict[str, Any]) -> None:
    backend = _primary_backend(agent_id)
    if backend is not None and hasattr(backend, "upsert_channel_unknown_sender"):
        _run_primary(backend.upsert_channel_unknown_sender(agent_id, payload))


def _delete_unknown_sender(agent_id: str, identity_id: str) -> None:
    backend = _primary_backend(agent_id)
    if backend is not None and hasattr(backend, "delete_channel_unknown_sender"):
        _run_primary(backend.delete_channel_unknown_sender(agent_id, identity_id))


def _persist_pairing_code(agent_id: str, payload: dict[str, Any]) -> None:
    backend = _primary_backend(agent_id)
    if backend is not None and hasattr(backend, "upsert_channel_pairing_code"):
        _run_primary(backend.upsert_channel_pairing_code(agent_id, payload))


def _consume_pairing_code(agent_id: str, pairing_code_id: str) -> None:
    backend = _primary_backend(agent_id)
    if backend is not None and hasattr(backend, "consume_channel_pairing_code"):
        _run_primary(backend.consume_channel_pairing_code(agent_id, pairing_code_id))


def _append_event(
    agent_id: str, event_type: str, payload: dict[str, Any], *, severity: GatewaySeverity = "info"
) -> str:
    identity_id = str(payload.get("identity_id") or "")
    event = {
        "schema_version": CHANNEL_GATEWAY_SCHEMA_VERSION,
        "event_id": _event_id(agent_id, event_type, identity_id),
        "agent_id": agent_id,
        "event_type": event_type,
        "severity": severity,
        "payload": payload,
        "created_at": _now_iso(),
    }
    backend = _primary_backend(agent_id)
    if backend is not None and hasattr(backend, "append_channel_gateway_event"):
        _run_primary(backend.append_channel_gateway_event(agent_id, event_type, event))
    _emit_observability(agent_id, event_type, payload, severity=severity)
    return str(event["event_id"])


def _emit_observability(agent_id: str, event_type: str, payload: dict[str, Any], *, severity: str) -> None:
    try:
        from koda.services.metrics import CHANNEL_GATEWAY_EVENTS

        CHANNEL_GATEWAY_EVENTS.labels(
            agent_id=agent_id, event=event_type, status=str(payload.get("status") or severity)
        ).inc()
    except Exception:
        log.debug("channel_gateway_metric_skipped", exc_info=True)
    try:
        from koda.services.audit import AuditEvent, emit

        emit(
            AuditEvent(
                event_type=f"channel_gateway.{event_type}",
                agent_id=agent_id,
                details={
                    "schema_version": CHANNEL_GATEWAY_SCHEMA_VERSION,
                    **payload,
                },
            )
        )
    except Exception:
        log.debug("channel_gateway_audit_skipped", exc_info=True)


def _record_from_identity(
    agent_id: str,
    identity: ChannelIdentity,
    *,
    status: GatewayStatus,
    source: str,
    allowed_by: str = "",
    blocked_by: str = "",
    revoked_by: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = _now_iso()
    identity_id = identity_id_for(agent_id, identity)
    existing = _identity_by_id(agent_id, identity_id) or {}
    created_at = str(existing.get("created_at") or now)
    paired_at = str(
        existing.get("paired_at") or (now if status in {"paired", "allowed"} and source == "pairing_code" else "")
    )
    record = ChannelGatewayIdentityRecord(
        schema_version=CHANNEL_GATEWAY_SCHEMA_VERSION,
        identity_id=identity_id,
        agent_id=agent_id,
        channel_type=identity.channel_type.lower(),
        channel_id=str(identity.channel_id),
        user_id=str(identity.user_id),
        display_name=str(identity.user_display_name or identity.user_id),
        is_group=bool(identity.is_group),
        status=status,
        source=source,
        allowed_by=allowed_by or str(existing.get("allowed_by") or ""),
        blocked_by=blocked_by,
        revoked_by=revoked_by,
        created_at=created_at,
        updated_at=now,
        last_seen_at=now,
        paired_at=paired_at,
        metadata={**dict(existing.get("metadata") or {}), **dict(metadata or {})},
    )
    return record.to_dict()


def _identity_by_id(agent_id: str, identity_id: str) -> dict[str, Any] | None:
    for item in list_gateway_identities(agent_id):
        if str(item.get("identity_id") or "") == identity_id:
            return dict(item)
    return None


def _identity_from_unknown(agent_id: str, identity_id: str) -> ChannelIdentity | None:
    for item in list_unknown_senders(agent_id):
        if str(item.get("identity_id") or "") == identity_id:
            return ChannelIdentity(
                channel_type=str(item.get("channel_type") or "telegram"),
                channel_id=str(item.get("channel_id") or ""),
                user_id=str(item.get("user_id") or ""),
                user_display_name=str(item.get("display_name") or item.get("user_id") or ""),
                is_group=bool(item.get("is_group")),
            )
    existing = _identity_by_id(agent_id, identity_id)
    if existing:
        return ChannelIdentity(
            channel_type=str(existing.get("channel_type") or "telegram"),
            channel_id=str(existing.get("channel_id") or ""),
            user_id=str(existing.get("user_id") or ""),
            user_display_name=str(existing.get("display_name") or existing.get("user_id") or ""),
            is_group=bool(existing.get("is_group")),
        )
    return None


def list_gateway_identities(agent_id: str | None) -> list[dict[str, Any]]:
    normalized = _normalize_agent_id(agent_id)
    return [dict(item) for item in _list_primary_identities(normalized) or [] if isinstance(item, dict)]


def list_unknown_senders(agent_id: str | None) -> list[dict[str, Any]]:
    normalized = _normalize_agent_id(agent_id)
    return [dict(item) for item in _list_primary_unknown_senders(normalized) or [] if isinstance(item, dict)]


def list_pairing_codes(agent_id: str | None, *, include_used: bool = False) -> list[dict[str, Any]]:
    normalized = _normalize_agent_id(agent_id)
    items = [dict(item) for item in _list_primary_pairing_codes(normalized) or [] if isinstance(item, dict)]
    now = datetime.now(UTC)
    filtered: list[dict[str, Any]] = []
    for item in items:
        if item.get("used_at") and not include_used:
            continue
        expires_at = _parse_dt(item.get("expires_at"))
        if expires_at is not None and expires_at < now and not include_used:
            continue
        filtered.append(item)
    return filtered


def create_pairing_code(
    agent_id: str | None,
    *,
    channel_type: str = "telegram",
    created_by: str = "",
    ttl_seconds: int = PAIRING_CODE_TTL_SECONDS,
) -> dict[str, Any]:
    normalized = _normalize_agent_id(agent_id)
    code = secrets.token_urlsafe(5).replace("-", "").replace("_", "")[:8].upper()
    now = datetime.now(UTC)
    payload = {
        "schema_version": CHANNEL_GATEWAY_SCHEMA_VERSION,
        "pairing_code_id": _stable_id("chgpair", normalized, channel_type, code, now.timestamp()),
        "agent_id": normalized,
        "channel_type": channel_type.lower(),
        "code": code,
        "status": "active",
        "created_by": created_by,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=max(60, ttl_seconds))).isoformat(),
        "used_at": "",
    }
    _persist_pairing_code(normalized, payload)
    _append_event(
        normalized,
        "pairing_created",
        {"channel_type": channel_type, "pairing_code_id": payload["pairing_code_id"], "status": "active"},
    )
    return payload


def approve_identity(
    agent_id: str | None, identity_id: str, *, approved_by: str = "", rationale: str = ""
) -> dict[str, Any]:
    normalized = _normalize_agent_id(agent_id)
    identity = _identity_from_unknown(normalized, identity_id)
    if identity is None:
        raise KeyError(identity_id)
    record = _record_from_identity(
        normalized,
        identity,
        status="allowed",
        source="operator_approval",
        allowed_by=approved_by,
        metadata={"rationale": rationale} if rationale else {},
    )
    _persist_identity(normalized, record)
    _delete_unknown_sender(normalized, identity_id)
    _append_event(
        normalized, "identity_allowed", {"identity_id": identity_id, "status": "allowed", "approved_by": approved_by}
    )
    return record


def block_identity(
    agent_id: str | None, identity_id: str, *, blocked_by: str = "", rationale: str = ""
) -> dict[str, Any]:
    normalized = _normalize_agent_id(agent_id)
    identity = _identity_from_unknown(normalized, identity_id)
    if identity is None:
        raise KeyError(identity_id)
    record = _record_from_identity(
        normalized,
        identity,
        status="blocked",
        source="operator_block",
        blocked_by=blocked_by,
        metadata={"rationale": rationale} if rationale else {},
    )
    _persist_identity(normalized, record)
    _delete_unknown_sender(normalized, identity_id)
    _append_event(
        normalized,
        "identity_blocked",
        {"identity_id": identity_id, "status": "blocked", "blocked_by": blocked_by},
        severity="warning",
    )
    return record


def revoke_identity(
    agent_id: str | None, identity_id: str, *, revoked_by: str = "", rationale: str = ""
) -> dict[str, Any]:
    normalized = _normalize_agent_id(agent_id)
    current = _identity_by_id(normalized, identity_id)
    if not current:
        raise KeyError(identity_id)
    identity = ChannelIdentity(
        channel_type=str(current.get("channel_type") or "telegram"),
        channel_id=str(current.get("channel_id") or ""),
        user_id=str(current.get("user_id") or ""),
        user_display_name=str(current.get("display_name") or current.get("user_id") or ""),
        is_group=bool(current.get("is_group")),
    )
    record = _record_from_identity(
        normalized,
        identity,
        status="revoked",
        source="operator_revoke",
        revoked_by=revoked_by,
        metadata={"rationale": rationale} if rationale else {},
    )
    _persist_identity(normalized, record)
    _append_event(
        normalized,
        "identity_revoked",
        {"identity_id": identity_id, "status": "revoked", "revoked_by": revoked_by},
        severity="warning",
    )
    return record


def gateway_state(agent_id: str | None, *, legacy_allowed_user_ids: list[str] | None = None) -> dict[str, Any]:
    normalized = _normalize_agent_id(agent_id)
    identities = list_gateway_identities(normalized)
    unknown = list_unknown_senders(normalized)
    active_codes = list_pairing_codes(normalized)
    return {
        "schema_version": CHANNEL_GATEWAY_SCHEMA_VERSION,
        "agent_id": normalized,
        "pilot_channel": "telegram",
        "status": "ready" if identities or legacy_allowed_user_ids else "pairing_required",
        "legacy_allowed_user_ids": list(legacy_allowed_user_ids or []),
        "identities": identities,
        "unknown_senders": unknown,
        "pairing_codes": active_codes,
        "summary": {
            "allowed": sum(1 for item in identities if item.get("status") == "allowed"),
            "blocked": sum(1 for item in identities if item.get("status") in {"blocked", "revoked"}),
            "pending": len(unknown),
            "active_pairing_codes": len(active_codes),
        },
    }


def evaluate_incoming_message(
    agent_id: str | None,
    message: IncomingMessage,
    *,
    legacy_allowed_user_ids: set[int] | None = None,
) -> ChannelGatewayDecision:
    normalized = _normalize_agent_id(agent_id)
    identity = message.channel
    identity_id = identity_id_for(normalized, identity)
    _append_event(
        normalized,
        "message_received",
        {
            "identity_id": identity_id,
            "channel_type": identity.channel_type,
            "channel_id": identity.channel_id,
            "user_id": identity.user_id,
            "status": "received",
        },
    )

    legacy_allowed = _coerce_int(identity.user_id) in set(legacy_allowed_user_ids or set())
    existing = _identity_by_id(normalized, identity_id)
    raw_status = str((existing or {}).get("status") or "pending")
    status = cast(
        GatewayStatus,
        raw_status if raw_status in {"pending", "paired", "allowed", "blocked", "revoked"} else "pending",
    )
    existing_source = str((existing or {}).get("source") or "")
    if status == "allowed" and existing_source == "legacy_allowed_user_ids" and not legacy_allowed:
        status = "pending"

    if status in {"blocked", "revoked"}:
        event_id = _append_event(
            normalized,
            "policy_denied",
            {"identity_id": identity_id, "status": status, "reason_code": "channel.policy_denied"},
            severity="warning",
        )
        return ChannelGatewayDecision(
            schema_version=CHANNEL_GATEWAY_SCHEMA_VERSION,
            decision="deny",
            allowed=False,
            identity_id=identity_id,
            channel_type=identity.channel_type,
            channel_id=identity.channel_id,
            user_id=identity.user_id,
            status=status,
            reason_code="channel.policy_denied",
            event_id=event_id,
            error=ChannelGatewayError(
                code="channel.policy_denied",
                category="permission",
                message="This channel identity is blocked for the agent.",
                retryable=False,
                user_action="Ask an operator to review the channel gateway allowlist.",
            ),
        )

    if legacy_allowed or status == "allowed":
        # The identity is written only when its status changes, never on every message.
        if status != "allowed":
            record = _record_from_identity(
                normalized,
                identity,
                status="allowed",
                source="legacy_allowed_user_ids",
                allowed_by="legacy_allowed_user_ids",
            )
            _persist_identity(normalized, record)
        return ChannelGatewayDecision(
            schema_version=CHANNEL_GATEWAY_SCHEMA_VERSION,
            decision="allow",
            allowed=True,
            identity_id=identity_id,
            channel_type=identity.channel_type,
            channel_id=identity.channel_id,
            user_id=identity.user_id,
            status="allowed",
            reason_code="channel.identity_allowed",
        )

    attempt = _pairing_attempt(message.text)
    limiter_key = f"{normalized}:{identity_id}"
    pairing: dict[str, Any] | None = None
    locked_out = False
    if attempt:
        now = _clock()
        locked_out = _pairing_locked(limiter_key, now)
        if not locked_out:
            pairing = _matching_pairing_code(normalized, identity.channel_type, attempt)
            if pairing is None and _record_pairing_failure(limiter_key, now):
                locked_out = True
                _append_event(
                    normalized,
                    "pairing_locked_out",
                    {"identity_id": identity_id, "status": "pending", "reason_code": "channel.pairing_locked"},
                    severity="warning",
                )
    if pairing is not None:
        _PAIRING_FAILURES.pop(limiter_key, None)
        record = _record_from_identity(
            normalized,
            identity,
            status="allowed",
            source="pairing_code",
            allowed_by=str(pairing.get("created_by") or "pairing_code"),
            metadata={"pairing_code_id": pairing.get("pairing_code_id")},
        )
        _persist_identity(normalized, record)
        _delete_unknown_sender(normalized, identity_id)
        _consume_pairing_code(normalized, str(pairing.get("pairing_code_id") or ""))
        event_id = _append_event(
            normalized,
            "identity_paired",
            {"identity_id": identity_id, "status": "allowed", "pairing_code_id": pairing.get("pairing_code_id")},
        )
        return ChannelGatewayDecision(
            schema_version=CHANNEL_GATEWAY_SCHEMA_VERSION,
            decision="paired",
            allowed=False,
            identity_id=identity_id,
            channel_type=identity.channel_type,
            channel_id=identity.channel_id,
            user_id=identity.user_id,
            status="paired",
            reason_code="channel.pairing_complete",
            event_id=event_id,
            error=ChannelGatewayError(
                code="channel.pairing_complete",
                category="permission",
                message="Channel pairing is complete.",
                retryable=True,
                user_action="Send the task again now that the channel identity is paired.",
            ),
        )

    unknown_payload = {
        "schema_version": CHANNEL_GATEWAY_SCHEMA_VERSION,
        "identity_id": identity_id,
        "agent_id": normalized,
        "channel_type": identity.channel_type.lower(),
        "channel_id": str(identity.channel_id),
        "user_id": str(identity.user_id),
        "display_name": str(identity.user_display_name or identity.user_id),
        "is_group": bool(identity.is_group),
        "message_id": str(message.id),
        "message_preview": _safe_text(message.text),
        "status": "pending",
        "first_seen_at": str((existing or {}).get("created_at") or _now_iso()),
        "last_seen_at": _now_iso(),
    }
    if str((existing or {}).get("status") or "") != "pending":
        pending_record = _record_from_identity(normalized, identity, status="pending", source="unknown_sender")
        _persist_identity(normalized, pending_record)
    _persist_unknown_sender(normalized, unknown_payload)
    event_id = _append_event(
        normalized,
        "unknown_sender_queued",
        {"identity_id": identity_id, "status": "pending", "channel_type": identity.channel_type},
        severity="warning",
    )
    if locked_out:
        reason_code = "channel.pairing_locked"
        error = ChannelGatewayError(
            code=reason_code,
            category="rate_limit",
            message="Too many pairing attempts from this sender.",
            retryable=True,
            user_action="Wait before sending a pairing code again, or ask an operator to approve the sender.",
            detail_ref="docs/operations/channel-gateway-runbook.md",
        )
    else:
        reason_code = "channel.identity_unknown"
        error = ChannelGatewayError(
            code=reason_code,
            category="permission",
            message="This channel identity has not been approved for the agent.",
            retryable=True,
            user_action="Open the dashboard channel gateway and approve or block the sender.",
            detail_ref="docs/operations/channel-gateway-runbook.md",
        )
    return ChannelGatewayDecision(
        schema_version=CHANNEL_GATEWAY_SCHEMA_VERSION,
        decision="queue_for_pairing",
        allowed=False,
        identity_id=identity_id,
        channel_type=identity.channel_type,
        channel_id=identity.channel_id,
        user_id=identity.user_id,
        status="pending",
        reason_code=reason_code,
        event_id=event_id,
        error=error,
    )


def evaluate_telegram_update(
    update: Any,
    *,
    agent_id: str | None = None,
    legacy_allowed_user_ids: set[int] | None = None,
) -> ChannelGatewayDecision | None:
    try:
        from koda.channels.telegram_adapter import TelegramAdapter

        message = TelegramAdapter.normalize_update(update)
    except Exception:
        log.debug("channel_gateway_telegram_normalize_failed", exc_info=True)
        return None
    if message is None:
        return None
    decision = evaluate_incoming_message(agent_id, message, legacy_allowed_user_ids=legacy_allowed_user_ids)
    update_key = _update_key(update)
    if update_key:
        _LAST_DECISIONS[update_key] = decision.to_dict()
        if len(_LAST_DECISIONS) > 1000:
            for key in list(_LAST_DECISIONS)[:200]:
                _LAST_DECISIONS.pop(key, None)
    return decision


def last_decision_for_update(update: Any) -> dict[str, Any] | None:
    update_key = _update_key(update)
    if not update_key:
        return None
    decision = _LAST_DECISIONS.get(update_key)
    return dict(decision) if isinstance(decision, dict) else None


def denial_message_for_decision(decision: dict[str, Any] | None) -> str:
    code = str((decision or {}).get("reason_code") or "")
    if code == "channel.pairing_complete":
        return "Channel pairing complete. Send your request again."
    if code == "channel.identity_unknown":
        return "Access denied. This sender is pending operator approval in the Koda channel gateway."
    if code == "channel.pairing_locked":
        minutes = PAIRING_LOCKOUT_SECONDS // 60
        return f"Access denied. Too many pairing attempts; wait {minutes} minutes before sending a pairing code again."
    if code == "channel.policy_denied":
        return "Access denied. This sender is blocked in the Koda channel gateway."
    return "Access denied."


def _pairing_attempt(text: str) -> str:
    """The one code a message offers: the whole message, or the argument of a
    leading command such as ``/start CODE``. Any other message tries no code, so
    one message is at most one guess.
    """
    tokens = str(text or "").strip().upper().split()
    if tokens and tokens[0].startswith("/"):
        tokens = tokens[1:]
    if len(tokens) != 1 or not (tokens[0].isascii() and tokens[0].isalnum()):
        return ""
    return tokens[0]


def _clock() -> float:
    return time.monotonic()


def _pairing_locked(key: str, now: float) -> bool:
    if _PAIRING_LOCKED_UNTIL.get(key, 0.0) > now:
        return True
    _PAIRING_LOCKED_UNTIL.pop(key, None)
    return False


def _record_pairing_failure(key: str, now: float) -> bool:
    """Count a failed attempt; return True when it locks the sender out."""
    failures = [at for at in _PAIRING_FAILURES.get(key, []) if now - at < PAIRING_LOCKOUT_SECONDS]
    failures.append(now)
    if len(failures) >= PAIRING_MAX_FAILURES:
        _PAIRING_FAILURES.pop(key, None)
        _PAIRING_LOCKED_UNTIL[key] = now + PAIRING_LOCKOUT_SECONDS
        return True
    _PAIRING_FAILURES[key] = failures
    if len(_PAIRING_FAILURES) > 10_000:
        for stale in [k for k, times in _PAIRING_FAILURES.items() if now - times[-1] >= PAIRING_LOCKOUT_SECONDS]:
            _PAIRING_FAILURES.pop(stale, None)
    return False


def _matching_pairing_code(agent_id: str, channel_type: str, attempt: str) -> dict[str, Any] | None:
    for item in list_pairing_codes(agent_id):
        if str(item.get("channel_type") or "").lower() != channel_type.lower():
            continue
        code = str(item.get("code") or "").upper()
        if code and secrets.compare_digest(code.encode(), attempt.encode()):
            return item
    return None


def _parse_dt(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _coerce_int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _update_key(update: Any) -> str:
    update_id = getattr(update, "update_id", None)
    if update_id is not None:
        return str(update_id)
    msg = getattr(update, "effective_message", None) or getattr(update, "message", None)
    if msg is not None:
        return str(getattr(msg, "message_id", "") or "")
    return ""
