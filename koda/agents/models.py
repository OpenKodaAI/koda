"""Inter-agent communication data models."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

MessageKind = Literal[
    "user_input",
    "agent_text",
    "task_request",
    "task_result",
    "delegation_request",
    "delegation_result",
    "clarification_request",
    "clarification_response",
    "status_update",
    "escalation",
    "handoff",
    "system_event",
    "text",
]


def _kind_from_legacy(message_type: str) -> str:
    if message_type == "text":
        return "agent_text"
    return message_type or "agent_text"


def _payload_from_legacy(kind: str, content: str, metadata: dict[str, Any]) -> dict[str, Any]:
    payload = metadata.get("payload")
    if isinstance(payload, dict):
        return dict(payload)
    if kind == "agent_text":
        return {"markdown": content}
    if kind == "user_input":
        return {"text": content, "attachments": metadata.get("attachments", [])}
    if kind == "task_result" or kind == "delegation_result":
        return {
            "status": "ok" if metadata.get("success", True) else "failed",
            "output_md": content,
            **{k: v for k, v in metadata.items() if k not in {"payload", "success"}},
        }
    return {"text": content, **{k: v for k, v in metadata.items() if k != "payload"}}


@dataclass
class AgentMessage:
    """A typed message sent between agents.

    The legacy ``content/message_type/to_agent`` fields are kept so older
    ``agent_*`` handlers can continue to call the bus while squad-aware code
    uses the durable envelope fields.
    """

    from_agent: str
    to_agent: str
    content: str
    message_type: str = "text"  # text, delegation_request, delegation_result
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    message_id: str = ""
    thread_id: str | None = None
    to_agent_ids: list[str] = field(default_factory=list)
    kind: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    causation_id: str | None = None
    correlation_id: str | None = None
    in_reply_to: str | None = None
    requires_response_by: str | None = None
    idempotency_key: str | None = None
    created_at: float | None = None

    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = time.time()
        if not self.to_agent_ids and self.to_agent:
            self.to_agent_ids = [self.to_agent]
        if not self.to_agent and self.to_agent_ids:
            self.to_agent = self.to_agent_ids[0]
        if not self.kind:
            self.kind = _kind_from_legacy(self.message_type)
        if self.kind and self.message_type == "text" and self.kind != "agent_text":
            self.message_type = self.kind
        if not self.payload:
            self.payload = _payload_from_legacy(self.kind, self.content, self.metadata)
        if self.created_at is None:
            self.created_at = self.timestamp
        if not self.thread_id:
            meta_thread = self.metadata.get("thread_id") or self.metadata.get("squad_thread_id")
            self.thread_id = str(meta_thread) if meta_thread else None
        self.causation_id = self.causation_id or self._metadata_str("causation_id")
        self.correlation_id = (
            self.correlation_id or self._metadata_str("correlation_id") or self._metadata_str("request_id")
        )
        self.in_reply_to = self.in_reply_to or self._metadata_str("in_reply_to")
        self.idempotency_key = self.idempotency_key or self._metadata_str("idempotency_key")

    def _metadata_str(self, key: str) -> str | None:
        value = self.metadata.get(key)
        return str(value) if value is not None else None

    @classmethod
    def from_legacy(
        cls,
        *,
        from_agent: str,
        to_agent: str,
        content: str,
        message_type: str = "text",
        metadata: dict[str, Any] | None = None,
        message_id: str = "",
        timestamp: float | None = None,
    ) -> AgentMessage:
        return cls(
            from_agent=from_agent,
            to_agent=to_agent,
            content=content,
            message_type=message_type,
            metadata=metadata or {},
            timestamp=time.time() if timestamp is None else timestamp,
            message_id=message_id,
        )

    @classmethod
    def from_envelope(
        cls,
        *,
        message_id: str,
        thread_id: str | None,
        from_agent: str,
        to_agent_ids: list[str],
        kind: str,
        payload: dict[str, Any] | None = None,
        causation_id: str | None = None,
        correlation_id: str | None = None,
        in_reply_to: str | None = None,
        idempotency_key: str | None = None,
        created_at: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentMessage:
        payload = payload or {}
        content = str(payload.get("markdown") or payload.get("text") or payload.get("output_md") or "")
        to_agent = to_agent_ids[0] if to_agent_ids else ""
        message_type = "text" if kind == "agent_text" else kind
        return cls(
            from_agent=from_agent,
            to_agent=to_agent,
            content=content,
            message_type=message_type,
            metadata=metadata or {},
            timestamp=time.time() if created_at is None else created_at,
            message_id=message_id,
            thread_id=thread_id,
            to_agent_ids=list(to_agent_ids),
            kind=kind,
            payload=payload,
            causation_id=causation_id,
            correlation_id=correlation_id,
            in_reply_to=in_reply_to,
            idempotency_key=idempotency_key,
            created_at=created_at,
        )

    def to_envelope_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "thread_id": self.thread_id,
            "from_agent": self.from_agent,
            "to_agent_ids": list(self.to_agent_ids),
            "kind": self.kind,
            "payload": dict(self.payload),
            "causation_id": self.causation_id,
            "correlation_id": self.correlation_id,
            "in_reply_to": self.in_reply_to,
            "requires_response_by": self.requires_response_by,
            "idempotency_key": self.idempotency_key,
            "created_at": self.created_at,
        }

    def to_legacy_dict(self) -> dict[str, Any]:
        return {
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "content": self.content,
            "message_type": self.message_type,
            "metadata": dict(self.metadata),
            "timestamp": self.timestamp,
            "message_id": self.message_id,
        }


@dataclass
class DelegationRequest:
    """A task delegation request from one agent to another."""

    from_agent: str
    to_agent: str
    task: str
    context: dict[str, Any] = field(default_factory=dict)
    delegation_depth: int = 0
    timeout: float = 60.0
    request_id: str = ""
    thread_id: str | None = None
    parent_message_id: str | None = None
    squad_task_id: str | None = None
    correlation_id: str | None = None
    idempotency_key: str | None = None


@dataclass
class DelegationResult:
    """The result of a delegation request."""

    request_id: str
    from_agent: str
    to_agent: str
    success: bool
    result: str = ""
    error: str | None = None
    duration_ms: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
