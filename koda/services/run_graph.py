"""RunGraph v1 contract and offline replay helpers.

The graph is deliberately additive. It can be persisted from fresh execution
traces, or reconstructed from legacy flat traces when no graph rows exist yet.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from koda.services.runtime.redaction import redact_value

RUN_GRAPH_SCHEMA_VERSION = "run_graph.v1"
RUN_REPLAY_SCHEMA_VERSION = "run_replay.v1"

RUN_GRAPH_NODE_TYPES = frozenset(
    {
        "queue_wait",
        "lease_acquire",
        "lease_renew",
        "lease_lost",
        "lease_reaped",
        "model_call",
        "context_block",
        "tool_request",
        "tool_result",
        "policy_gate",
        "approval_request",
        "approval_decision",
        "dependency_call",
        "breaker_open",
        "retry_scheduled",
        "dlq_inserted",
        "cancellation",
        "resource_cleanup",
        "user_facing_error",
        "child_run",
        "squad_reply",
        "agent_request",
        "agent_followup",
        "reply_obligation",
        "coordinator_synthesis",
        "artifact",
        "cost",
        "runtime_event",
    }
)

RUN_GRAPH_STATUSES = frozenset(
    {
        "queued",
        "running",
        "retrying",
        "stalled",
        "degraded",
        "failed",
        "cancelled",
        "completed",
        "blocked",
        "info",
    }
)

RUN_GRAPH_EDGE_TYPES = frozenset(
    {
        "contains",
        "caused_by",
        "emits",
        "uses",
        "approves",
        "produces",
        "retries",
        "fails_to",
        "child_run",
    }
)

_TEXT_PREVIEW_CHARS = 240
_HASH_PREVIEW_CHARS = 12
_SENSITIVE_KEY_PARTS = (
    "api_key",
    "auth",
    "credential",
    "password",
    "private_key",
    "secret",
    "token",
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)


def stable_digest(value: Any, *, length: int = 16) -> str:
    """Return a deterministic short digest for graph ids and replay hashes."""

    digest = hashlib.sha256(_canonical_json(value).encode("utf-8"), usedforsecurity=False).hexdigest()
    return digest[: max(8, int(length))]


def _string(value: Any) -> str:
    return str(value or "").strip()


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


def _dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _clip_text(value: Any, *, limit: int = _TEXT_PREVIEW_CHARS) -> str | None:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def _redacted_payload(value: Any) -> dict[str, Any]:
    try:
        redacted = redact_value(value)
    except Exception:
        redacted = _fallback_redact_value(value)
    return _dict(redacted)


def _fallback_redact_value(value: Any, *, key_hint: str | None = None) -> Any:
    """Conservative local redaction used when the security sidecar is down."""

    key = str(key_hint or "").lower()
    if any(part in key for part in _SENSITIVE_KEY_PARTS):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(item_key): _fallback_redact_value(item, key_hint=str(item_key)) for item_key, item in value.items()}
    if isinstance(value, list):
        return [_fallback_redact_value(item, key_hint=key_hint) for item in value]
    if isinstance(value, tuple):
        return [_fallback_redact_value(item, key_hint=key_hint) for item in value]
    if isinstance(value, str):
        stripped = value.strip()
        lowered = stripped.lower()
        if any(part in lowered for part in _SENSITIVE_KEY_PARTS) and len(stripped) > 12:
            return "[REDACTED]"
    return value


def make_graph_id(agent_id: str, task_id: int, attempt: int = 1) -> str:
    return f"run:{_string(agent_id).upper()}:{int(task_id)}:attempt:{max(1, int(attempt or 1))}"


def make_node_id(graph_id: str, node_type: str, ordinal: int, source_ref: Any = "") -> str:
    seed = {
        "graph_id": graph_id,
        "node_type": node_type,
        "ordinal": int(ordinal),
        "source_ref": source_ref,
    }
    return f"{node_type}:{ordinal}:{stable_digest(seed, length=12)}"


def make_edge_id(graph_id: str, from_node_id: str, to_node_id: str, edge_type: str, ordinal: int) -> str:
    seed = {
        "graph_id": graph_id,
        "from": from_node_id,
        "to": to_node_id,
        "type": edge_type,
        "ordinal": int(ordinal),
    }
    return f"edge:{ordinal}:{stable_digest(seed, length=12)}"


@dataclass(frozen=True, slots=True)
class RunGraphNode:
    """A causal execution node in `run_graph.v1`."""

    node_id: str
    graph_id: str
    agent_id: str
    task_id: int
    attempt: int
    node_type: str
    status: str
    ordinal: int
    summary: str
    parent_node_id: str | None = None
    session_id: str | None = None
    env_id: int | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: float | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    redactions: dict[str, Any] = field(default_factory=dict)
    refs: dict[str, Any] = field(default_factory=dict)
    trace_id: str | None = None
    audit_event_id: int | None = None
    runtime_event_seq: int | None = None
    source: str = "reconstructed"
    schema_version: str = RUN_GRAPH_SCHEMA_VERSION

    def __post_init__(self) -> None:
        node_type = _string(self.node_type) or "runtime_event"
        if node_type not in RUN_GRAPH_NODE_TYPES:
            node_type = "runtime_event"
        status = _string(self.status).lower() or "info"
        if status not in RUN_GRAPH_STATUSES:
            status = "info"
        object.__setattr__(self, "node_type", node_type)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "agent_id", _string(self.agent_id).upper())
        object.__setattr__(self, "task_id", int(self.task_id))
        object.__setattr__(self, "attempt", max(1, int(self.attempt or 1)))
        object.__setattr__(self, "ordinal", max(0, int(self.ordinal)))
        object.__setattr__(self, "payload", _redacted_payload(self.payload))
        object.__setattr__(self, "redactions", _dict(self.redactions))
        object.__setattr__(self, "refs", _dict(self.refs))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "node_id": self.node_id,
            "graph_id": self.graph_id,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "attempt": self.attempt,
            "parent_node_id": self.parent_node_id,
            "session_id": self.session_id,
            "env_id": self.env_id,
            "ordinal": self.ordinal,
            "node_type": self.node_type,
            "status": self.status,
            "summary": self.summary,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "payload": self.payload,
            "redactions": self.redactions,
            "refs": self.refs,
            "trace_id": self.trace_id,
            "audit_event_id": self.audit_event_id,
            "runtime_event_seq": self.runtime_event_seq,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RunGraphNode:
        return cls(
            node_id=_string(payload.get("node_id")),
            graph_id=_string(payload.get("graph_id")),
            agent_id=_string(payload.get("agent_id")),
            task_id=_int(payload.get("task_id")),
            attempt=max(1, _int(payload.get("attempt"), 1)),
            parent_node_id=_string(payload.get("parent_node_id")) or None,
            session_id=_string(payload.get("session_id")) or None,
            env_id=_int(payload.get("env_id")) if payload.get("env_id") is not None else None,
            ordinal=_int(payload.get("ordinal")),
            node_type=_string(payload.get("node_type")),
            status=_string(payload.get("status")),
            summary=_string(payload.get("summary")),
            started_at=_string(payload.get("started_at")) or None,
            completed_at=_string(payload.get("completed_at")) or None,
            duration_ms=_float_or_none(payload.get("duration_ms")),
            payload=_dict(payload.get("payload")),
            redactions=_dict(payload.get("redactions")),
            refs=_dict(payload.get("refs")),
            trace_id=_string(payload.get("trace_id")) or None,
            audit_event_id=_int(payload.get("audit_event_id")) if payload.get("audit_event_id") is not None else None,
            runtime_event_seq=_int(payload.get("runtime_event_seq"))
            if payload.get("runtime_event_seq") is not None
            else None,
            source=_string(payload.get("source")) or "reconstructed",
        )


@dataclass(frozen=True, slots=True)
class RunGraphEdge:
    """A causal edge in `run_graph.v1`."""

    edge_id: str
    graph_id: str
    from_node_id: str
    to_node_id: str
    edge_type: str
    ordinal: int
    payload: dict[str, Any] = field(default_factory=dict)
    schema_version: str = RUN_GRAPH_SCHEMA_VERSION

    def __post_init__(self) -> None:
        edge_type = _string(self.edge_type) or "caused_by"
        if edge_type not in RUN_GRAPH_EDGE_TYPES:
            edge_type = "caused_by"
        object.__setattr__(self, "edge_type", edge_type)
        object.__setattr__(self, "ordinal", max(0, int(self.ordinal)))
        object.__setattr__(self, "payload", _redacted_payload(self.payload))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "edge_id": self.edge_id,
            "graph_id": self.graph_id,
            "from_node_id": self.from_node_id,
            "to_node_id": self.to_node_id,
            "edge_type": self.edge_type,
            "ordinal": self.ordinal,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RunGraphEdge:
        return cls(
            edge_id=_string(payload.get("edge_id")),
            graph_id=_string(payload.get("graph_id")),
            from_node_id=_string(payload.get("from_node_id")),
            to_node_id=_string(payload.get("to_node_id")),
            edge_type=_string(payload.get("edge_type")),
            ordinal=_int(payload.get("ordinal")),
            payload=_dict(payload.get("payload")),
        )


@dataclass(frozen=True, slots=True)
class RunGraph:
    """A serialized RunGraph response payload."""

    graph_id: str
    agent_id: str
    task_id: int
    attempt: int
    nodes: tuple[RunGraphNode, ...]
    edges: tuple[RunGraphEdge, ...]
    summary: dict[str, Any] = field(default_factory=dict)
    source_refs: dict[str, Any] = field(default_factory=dict)
    replay_available: bool = True
    schema_version: str = RUN_GRAPH_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "graph_id": self.graph_id,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "attempt": self.attempt,
            "summary": self.summary,
            "source_refs": self.source_refs,
            "replay_available": self.replay_available,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RunGraph:
        return cls(
            graph_id=_string(payload.get("graph_id")),
            agent_id=_string(payload.get("agent_id")),
            task_id=_int(payload.get("task_id")),
            attempt=max(1, _int(payload.get("attempt"), 1)),
            summary=_dict(payload.get("summary")),
            source_refs=_dict(payload.get("source_refs")),
            replay_available=bool(payload.get("replay_available", True)),
            nodes=tuple(
                RunGraphNode.from_dict(item) for item in _list(payload.get("nodes")) if isinstance(item, Mapping)
            ),
            edges=tuple(
                RunGraphEdge.from_dict(item) for item in _list(payload.get("edges")) if isinstance(item, Mapping)
            ),
        )


@dataclass(frozen=True, slots=True)
class RunReplayBundle:
    """Offline replay bundle for a graph trajectory."""

    graph_id: str
    agent_id: str
    task_id: int
    attempt: int
    inputs: dict[str, Any]
    model_outputs: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    approval_decisions: list[dict[str, Any]]
    artifacts: list[dict[str, Any]]
    costs: dict[str, Any]
    divergences: list[dict[str, Any]]
    replay_mode: str = "offline"
    schema_version: str = RUN_REPLAY_SCHEMA_VERSION
    generated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "graph_id": self.graph_id,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "attempt": self.attempt,
            "replay_mode": self.replay_mode,
            "generated_at": self.generated_at,
            "inputs": self.inputs,
            "model_outputs": self.model_outputs,
            "tool_results": self.tool_results,
            "approval_decisions": self.approval_decisions,
            "artifacts": self.artifacts,
            "costs": self.costs,
            "divergences": self.divergences,
        }


def _timeline_node_type(event_type: str) -> str:
    event = event_type.lower()
    if "lease_reap" in event or "lease.reap" in event:
        return "lease_reaped"
    if "lease_lost" in event or "lease.lost" in event:
        return "lease_lost"
    if "lease_renew" in event or "lease.renew" in event:
        return "lease_renew"
    if "lease_acquire" in event or "lease.acquire" in event:
        return "lease_acquire"
    if "retry" in event or "retried" in event:
        return "retry_scheduled"
    if "dead_letter" in event or "dlq" in event:
        return "dlq_inserted"
    if "breaker" in event:
        return "breaker_open"
    if any(token in event for token in ("dependency", "provider", "mcp", "browser", "postgres", "timeout")):
        return "dependency_call"
    if "cancel" in event:
        return "cancellation"
    if "tool" in event:
        return "tool_result"
    if "approval" in event:
        return "approval_decision"
    if "policy" in event or "confidence" in event:
        return "policy_gate"
    if "artifact" in event:
        return "artifact"
    if "cleanup" in event:
        return "resource_cleanup"
    if "fail" in event or "error" in event:
        return "user_facing_error"
    return "runtime_event"


def _status_from_bool(success: Any) -> str:
    if isinstance(success, bool):
        return "completed" if success else "failed"
    return "info"


def _node(
    *,
    graph_id: str,
    agent_id: str,
    task_id: int,
    attempt: int,
    node_type: str,
    ordinal: int,
    summary: str,
    status: str = "info",
    parent_node_id: str | None = None,
    session_id: str | None = None,
    env_id: int | None = None,
    payload: dict[str, Any] | None = None,
    refs: dict[str, Any] | None = None,
    source: str = "reconstructed",
    source_ref: Any = "",
    started_at: str | None = None,
    completed_at: str | None = None,
    duration_ms: float | None = None,
    trace_id: str | None = None,
    runtime_event_seq: int | None = None,
) -> RunGraphNode:
    return RunGraphNode(
        node_id=make_node_id(graph_id, node_type, ordinal, source_ref),
        graph_id=graph_id,
        agent_id=agent_id,
        task_id=task_id,
        attempt=attempt,
        parent_node_id=parent_node_id,
        session_id=session_id,
        env_id=env_id,
        node_type=node_type,
        status=status,
        ordinal=ordinal,
        summary=summary,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=duration_ms,
        payload=payload or {},
        refs=refs or {},
        trace_id=trace_id,
        runtime_event_seq=runtime_event_seq,
        source=source,
    )


def _edge(
    *,
    graph_id: str,
    from_node_id: str,
    to_node_id: str,
    edge_type: str,
    ordinal: int,
    payload: dict[str, Any] | None = None,
) -> RunGraphEdge:
    return RunGraphEdge(
        edge_id=make_edge_id(graph_id, from_node_id, to_node_id, edge_type, ordinal),
        graph_id=graph_id,
        from_node_id=from_node_id,
        to_node_id=to_node_id,
        edge_type=edge_type,
        ordinal=ordinal,
        payload=payload or {},
    )


def build_run_graph_from_trace(
    *,
    agent_id: str,
    task_id: int,
    trace: Mapping[str, Any] | None,
    runtime_events: Iterable[Mapping[str, Any]] | None = None,
) -> RunGraph:
    """Build a graph from the current flat execution trace shape."""

    trace_payload = _dict(trace)
    runtime = _dict(trace_payload.get("runtime"))
    request = _dict(trace_payload.get("request"))
    assistant = _dict(trace_payload.get("assistant"))
    grounding = _dict(trace_payload.get("grounding"))
    raw_artifacts = _dict(trace_payload.get("raw_artifacts"))
    tools = [item for item in _list(trace_payload.get("tools")) if isinstance(item, Mapping)]
    timeline = [item for item in _list(trace_payload.get("timeline")) if isinstance(item, Mapping)]
    attempt = max(1, _int(runtime.get("attempt"), 1))
    session_id = _string(request.get("session_id")) or None
    graph_id = make_graph_id(agent_id, task_id, attempt)
    status = _string(runtime.get("status")).lower() or "info"
    if status == "needs_review":
        status = "degraded"
    elif status not in RUN_GRAPH_STATUSES:
        status = "info"

    nodes: list[RunGraphNode] = []
    edges: list[RunGraphEdge] = []
    ordinal = 1
    edge_ordinal = 1

    root = _node(
        graph_id=graph_id,
        agent_id=agent_id,
        task_id=task_id,
        attempt=attempt,
        node_type="model_call",
        ordinal=ordinal,
        summary="Model turn",
        status=status,
        session_id=session_id,
        payload={
            "query_preview": _clip_text(request.get("query_text")),
            "query_hash": stable_digest(request.get("query_text") or ""),
            "model": request.get("model"),
            "work_dir": request.get("work_dir"),
            "stop_reason": runtime.get("stop_reason"),
            "response_preview": _clip_text(assistant.get("response_text")),
            "response_hash": stable_digest(assistant.get("response_text") or ""),
        },
        refs={"trace_schema": trace_payload.get("schema"), "trace_version": trace_payload.get("trace_version")},
        source="execution_trace",
        source_ref={"node": "model_call", "task_id": task_id, "attempt": attempt},
    )
    nodes.append(root)
    ordinal += 1

    policy_payload = _dict(grounding.get("effective_policy"))
    if policy_payload:
        policy_node = _node(
            graph_id=graph_id,
            agent_id=agent_id,
            task_id=task_id,
            attempt=attempt,
            node_type="policy_gate",
            ordinal=ordinal,
            summary="Effective execution policy",
            status="info",
            parent_node_id=root.node_id,
            session_id=session_id,
            payload=policy_payload,
            source="execution_trace.grounding",
            source_ref={"node": "policy_gate", "ordinal": ordinal},
        )
        nodes.append(policy_node)
        edges.append(
            _edge(
                graph_id=graph_id,
                from_node_id=root.node_id,
                to_node_id=policy_node.node_id,
                edge_type="uses",
                ordinal=edge_ordinal,
            )
        )
        ordinal += 1
        edge_ordinal += 1

    context_governance = _dict(grounding.get("context_governance"))
    governed_blocks = [item for item in _list(context_governance.get("blocks")) if isinstance(item, Mapping)]
    for index, block in enumerate(governed_blocks[:50], start=1):
        block_dict = _dict(block)
        context_node = _node(
            graph_id=graph_id,
            agent_id=agent_id,
            task_id=task_id,
            attempt=attempt,
            node_type="context_block",
            ordinal=ordinal,
            summary=f"Context block: {_string(block_dict.get('block_id') or index)}",
            status=_string(block_dict.get("status")) or "info",
            parent_node_id=root.node_id,
            session_id=session_id,
            payload={
                "schema_version": block_dict.get("schema_version"),
                "block_id": block_dict.get("block_id"),
                "category": block_dict.get("category"),
                "source": block_dict.get("source"),
                "token_estimate": block_dict.get("token_estimate"),
                "include_reason": block_dict.get("include_reason"),
                "drop_reason": block_dict.get("drop_reason"),
                "redaction": block_dict.get("redaction"),
                "risk": block_dict.get("risk"),
                "provenance": _dict(block_dict.get("provenance")),
            },
            source="execution_trace.grounding.context_governance",
            source_ref={"context_block_index": index, "block_id": block_dict.get("block_id")},
        )
        nodes.append(context_node)
        edges.append(
            _edge(
                graph_id=graph_id,
                from_node_id=root.node_id,
                to_node_id=context_node.node_id,
                edge_type="uses",
                ordinal=edge_ordinal,
            )
        )
        ordinal += 1
        edge_ordinal += 1

    context_count = _int(grounding.get("knowledge_hit_count")) + _int(grounding.get("artifact_dossier_count"))
    memory_sources = _list(grounding.get("memory_retrieval_sources"))
    if context_count or memory_sources:
        context_node = _node(
            graph_id=graph_id,
            agent_id=agent_id,
            task_id=task_id,
            attempt=attempt,
            node_type="context_block",
            ordinal=ordinal,
            summary="Compiled context provenance",
            status="info",
            parent_node_id=root.node_id,
            session_id=session_id,
            payload={
                "knowledge_hit_count": grounding.get("knowledge_hit_count"),
                "memory_layers": grounding.get("memory_layers"),
                "memory_sources": memory_sources,
                "artifact_dossier_count": grounding.get("artifact_dossier_count"),
                "stale_sources_present": grounding.get("stale_sources_present"),
                "ungrounded_operationally": grounding.get("ungrounded_operationally"),
            },
            source="execution_trace.grounding",
            source_ref={"node": "context_block", "ordinal": ordinal},
        )
        nodes.append(context_node)
        edges.append(
            _edge(
                graph_id=graph_id,
                from_node_id=root.node_id,
                to_node_id=context_node.node_id,
                edge_type="uses",
                ordinal=edge_ordinal,
            )
        )
        ordinal += 1
        edge_ordinal += 1

    for index, step in enumerate(tools, start=1):
        step_dict = _dict(step)
        tool_name = _string(step_dict.get("tool") or step_dict.get("name") or f"tool_{index}")
        request_node = _node(
            graph_id=graph_id,
            agent_id=agent_id,
            task_id=task_id,
            attempt=attempt,
            node_type="tool_request",
            ordinal=ordinal,
            summary=f"Tool requested: {tool_name}",
            status="running",
            parent_node_id=root.node_id,
            session_id=session_id,
            started_at=_string(step_dict.get("started_at")) or None,
            payload={
                "tool": tool_name,
                "params": _dict(step_dict.get("params")),
                "iteration": step_dict.get("iteration"),
                "metadata": _dict(step_dict.get("metadata")),
            },
            source="execution_trace.tools",
            source_ref={"tool": tool_name, "index": index, "kind": "request"},
        )
        nodes.append(request_node)
        edges.append(
            _edge(
                graph_id=graph_id,
                from_node_id=root.node_id,
                to_node_id=request_node.node_id,
                edge_type="uses",
                ordinal=edge_ordinal,
            )
        )
        ordinal += 1
        edge_ordinal += 1

        result_node_type = "approval_decision" if _dict(step_dict.get("metadata")).get("approval") else "tool_result"
        result_node = _node(
            graph_id=graph_id,
            agent_id=agent_id,
            task_id=task_id,
            attempt=attempt,
            node_type=result_node_type,
            ordinal=ordinal,
            summary=f"Tool result: {tool_name}",
            status=_status_from_bool(step_dict.get("success")),
            parent_node_id=request_node.node_id,
            session_id=session_id,
            completed_at=_string(step_dict.get("completed_at")) or None,
            duration_ms=_float_or_none(step_dict.get("duration_ms")),
            payload={
                "tool": tool_name,
                "success": step_dict.get("success"),
                "output_preview": _clip_text(step_dict.get("output")),
                "output_hash": stable_digest(step_dict.get("output") or ""),
                "metadata": _dict(step_dict.get("metadata")),
            },
            source="execution_trace.tools",
            source_ref={"tool": tool_name, "index": index, "kind": "result"},
        )
        nodes.append(result_node)
        edges.append(
            _edge(
                graph_id=graph_id,
                from_node_id=request_node.node_id,
                to_node_id=result_node.node_id,
                edge_type="produces",
                ordinal=edge_ordinal,
            )
        )
        ordinal += 1
        edge_ordinal += 1

        child_payload = _dict(step_dict.get("data"))
        child_runs = _list(child_payload.get("child_runs") or _dict(step_dict.get("metadata")).get("child_runs"))
        if tool_name == "task" and child_runs:
            for child_index, child in enumerate(child_runs, start=1):
                child_dict = _dict(child)
                child_node = _node(
                    graph_id=graph_id,
                    agent_id=agent_id,
                    task_id=task_id,
                    attempt=attempt,
                    node_type="child_run",
                    ordinal=ordinal,
                    summary=f"Child run: {_string(child_dict.get('child_run_id') or child_index)}",
                    status=_string(child_dict.get("status")) or "info",
                    parent_node_id=result_node.node_id,
                    session_id=session_id,
                    payload={
                        "schema_version": child_dict.get("schema_version"),
                        "child_run_id": child_dict.get("child_run_id"),
                        "child_task_id": child_dict.get("child_task_id"),
                        "summary": child_dict.get("summary"),
                        "cost_usd": child_dict.get("cost_usd"),
                        "warnings": _list(child_dict.get("warnings")),
                        "error": _dict(child_dict.get("error")),
                    },
                    refs={"child_task_id": child_dict.get("child_task_id")},
                    source="execution_trace.tools.task",
                    source_ref={"tool": "task", "index": index, "child_index": child_index},
                )
                nodes.append(child_node)
                edges.append(
                    _edge(
                        graph_id=graph_id,
                        from_node_id=result_node.node_id,
                        to_node_id=child_node.node_id,
                        edge_type="child_run",
                        ordinal=edge_ordinal,
                    )
                )
                ordinal += 1
                edge_ordinal += 1

    for index, item in enumerate(timeline, start=1):
        item_dict = _dict(item)
        event_type = _string(item_dict.get("type") or "event")
        timeline_node = _node(
            graph_id=graph_id,
            agent_id=agent_id,
            task_id=task_id,
            attempt=attempt,
            node_type=_timeline_node_type(event_type),
            ordinal=ordinal,
            summary=_string(item_dict.get("title") or event_type) or "Timeline event",
            status=_string(item_dict.get("status")) or "info",
            parent_node_id=root.node_id,
            session_id=session_id,
            completed_at=_string(item_dict.get("timestamp")) or None,
            payload={
                "event_type": event_type,
                "summary": item_dict.get("summary"),
                "details": _dict(item_dict.get("details")),
            },
            source="execution_trace.timeline",
            source_ref={"timeline_index": index, "event_type": event_type},
        )
        nodes.append(timeline_node)
        edges.append(
            _edge(
                graph_id=graph_id,
                from_node_id=root.node_id,
                to_node_id=timeline_node.node_id,
                edge_type="emits",
                ordinal=edge_ordinal,
            )
        )
        ordinal += 1
        edge_ordinal += 1

    for raw_event in runtime_events or ():
        event = _dict(raw_event)
        seq = _int(event.get("id") or event.get("seq")) if event.get("id") or event.get("seq") else None
        runtime_node = _node(
            graph_id=graph_id,
            agent_id=agent_id,
            task_id=task_id,
            attempt=max(1, _int(event.get("attempt"), attempt)),
            node_type=_timeline_node_type(_string(event.get("event_type"))),
            ordinal=ordinal,
            summary=_string(event.get("event_type") or "runtime event"),
            status=_string(event.get("severity") or "info"),
            parent_node_id=root.node_id,
            session_id=session_id,
            completed_at=_string(event.get("created_at")) or None,
            payload=_dict(event.get("payload") or event.get("payload_json")),
            source="runtime_events",
            source_ref={"runtime_event_seq": seq, "event_type": event.get("event_type")},
            runtime_event_seq=seq,
        )
        nodes.append(runtime_node)
        edges.append(
            _edge(
                graph_id=graph_id,
                from_node_id=root.node_id,
                to_node_id=runtime_node.node_id,
                edge_type="emits",
                ordinal=edge_ordinal,
            )
        )
        ordinal += 1
        edge_ordinal += 1

    cost_usd = _float_or_none(trace_payload.get("_cost_usd"))
    if cost_usd is None:
        cost_usd = _float_or_none(runtime.get("cost_usd"))
    if cost_usd and cost_usd > 0:
        cost_node = _node(
            graph_id=graph_id,
            agent_id=agent_id,
            task_id=task_id,
            attempt=attempt,
            node_type="cost",
            ordinal=ordinal,
            summary="Cost recorded",
            status="info",
            parent_node_id=root.node_id,
            session_id=session_id,
            payload={"cost_usd": cost_usd, "model": request.get("model")},
            source="audit_events",
            source_ref={"node": "cost", "task_id": task_id},
        )
        nodes.append(cost_node)
        edges.append(
            _edge(
                graph_id=graph_id,
                from_node_id=root.node_id,
                to_node_id=cost_node.node_id,
                edge_type="produces",
                ordinal=edge_ordinal,
            )
        )
        ordinal += 1
        edge_ordinal += 1

    artifacts = _list(raw_artifacts.get("artifact_dossiers")) + _list(raw_artifacts.get("native_items"))
    for index, artifact in enumerate(artifacts, start=1):
        artifact_node = _node(
            graph_id=graph_id,
            agent_id=agent_id,
            task_id=task_id,
            attempt=attempt,
            node_type="artifact",
            ordinal=ordinal,
            summary=f"Artifact {index}",
            status="info",
            parent_node_id=root.node_id,
            session_id=session_id,
            payload={"artifact": artifact},
            source="execution_trace.raw_artifacts",
            source_ref={"artifact_index": index},
        )
        nodes.append(artifact_node)
        edges.append(
            _edge(
                graph_id=graph_id,
                from_node_id=root.node_id,
                to_node_id=artifact_node.node_id,
                edge_type="produces",
                ordinal=edge_ordinal,
            )
        )
        ordinal += 1
        edge_ordinal += 1

    error_message = _string(runtime.get("error_message") or trace_payload.get("error_message"))
    if error_message:
        error_node = _node(
            graph_id=graph_id,
            agent_id=agent_id,
            task_id=task_id,
            attempt=attempt,
            node_type="user_facing_error",
            ordinal=ordinal,
            summary="User-facing error",
            status="failed",
            parent_node_id=root.node_id,
            session_id=session_id,
            payload={
                "code": "runtime.execution_failed",
                "category": "internal",
                "message": error_message,
                "retryable": status in {"retrying", "stalled", "degraded"},
                "user_action": "Inspect the trace, retry if safe, or run doctor.",
            },
            source="execution_trace.runtime",
            source_ref={"node": "user_facing_error", "task_id": task_id},
        )
        nodes.append(error_node)
        edges.append(
            _edge(
                graph_id=graph_id,
                from_node_id=root.node_id,
                to_node_id=error_node.node_id,
                edge_type="fails_to",
                ordinal=edge_ordinal,
            )
        )

    counts: dict[str, int] = {}
    for node in nodes:
        counts[node.node_type] = counts.get(node.node_type, 0) + 1
    return RunGraph(
        graph_id=graph_id,
        agent_id=_string(agent_id).upper(),
        task_id=int(task_id),
        attempt=attempt,
        nodes=tuple(nodes),
        edges=tuple(edges),
        summary={
            "node_count": len(nodes),
            "edge_count": len(edges),
            "node_types": counts,
            "status": status,
            "tool_count": len(tools),
            "has_error": bool(error_message),
        },
        source_refs={
            "trace_schema": trace_payload.get("schema"),
            "trace_version": trace_payload.get("trace_version"),
            "reconstructed": True,
        },
        replay_available=True,
    )


def build_replay_bundle_from_trace(
    *,
    graph: RunGraph,
    trace: Mapping[str, Any] | None,
) -> RunReplayBundle:
    """Build an offline replay bundle from the graph and flat trace."""

    trace_payload = _dict(trace)
    request = _dict(trace_payload.get("request"))
    assistant = _dict(trace_payload.get("assistant"))
    runtime = _dict(trace_payload.get("runtime"))
    raw_artifacts = _dict(trace_payload.get("raw_artifacts"))
    divergences: list[dict[str, Any]] = []
    if not request.get("query_text"):
        divergences.append({"code": "missing_query", "message": "Original query text is unavailable."})
    if not assistant.get("response_text") and runtime.get("status") == "completed":
        divergences.append({"code": "missing_response", "message": "Completed trace has no response text."})

    tool_results = [
        {
            "tool": node.payload.get("tool"),
            "success": node.payload.get("success"),
            "output_preview": node.payload.get("output_preview"),
            "output_hash": node.payload.get("output_hash"),
            "duration_ms": node.duration_ms,
            "node_id": node.node_id,
        }
        for node in graph.nodes
        if node.node_type == "tool_result"
    ]
    approvals = [
        {
            "decision": node.payload.get("metadata", {}).get("approval") or node.status,
            "summary": node.summary,
            "node_id": node.node_id,
            "payload": node.payload,
        }
        for node in graph.nodes
        if node.node_type in {"approval_request", "approval_decision"}
    ]
    artifacts = [
        {
            "node_id": node.node_id,
            "summary": node.summary,
            "refs": node.refs,
            "payload": node.payload,
        }
        for node in graph.nodes
        if node.node_type == "artifact"
    ]
    return RunReplayBundle(
        graph_id=graph.graph_id,
        agent_id=graph.agent_id,
        task_id=graph.task_id,
        attempt=graph.attempt,
        inputs={
            "query_preview": _clip_text(request.get("query_text")),
            "query_hash": stable_digest(request.get("query_text") or ""),
            "model": request.get("model"),
            "session_id": request.get("session_id"),
            "context_nodes": [node.to_dict() for node in graph.nodes if node.node_type == "context_block"],
        },
        model_outputs=[
            {
                "response_preview": _clip_text(assistant.get("response_text")),
                "response_hash": stable_digest(assistant.get("response_text") or ""),
                "stop_reason": runtime.get("stop_reason"),
                "status": runtime.get("status"),
                "node_id": graph.nodes[0].node_id if graph.nodes else None,
            }
        ],
        tool_results=tool_results,
        approval_decisions=approvals,
        artifacts=artifacts,
        costs={
            "cost_usd": trace_payload.get("_cost_usd") or runtime.get("cost_usd"),
            "duration_ms": trace_payload.get("_duration_ms") or runtime.get("duration_ms"),
            "model": request.get("model"),
            "raw_usage_available": bool(raw_artifacts.get("native_items")),
        },
        divergences=divergences,
    )
