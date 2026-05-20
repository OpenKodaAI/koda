"""Postgres-backed RunGraph helpers.

Writes are best effort: RunGraph persistence must never fail a user task.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, cast

from koda.config import AGENT_ID
from koda.logging_config import get_logger
from koda.services.run_graph import (
    RunGraph,
    RunGraphEdge,
    RunGraphNode,
    RunReplayBundle,
    build_replay_bundle_from_trace,
    build_run_graph_from_trace,
)
from koda.state.primary import primary_execute, primary_fetch_all, run_coro_sync

log = get_logger(__name__)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, default=str)


def _json_load(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return fallback


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_agent_id(agent_id: str | None) -> str:
    return str(agent_id or AGENT_ID or "default").strip().upper()


async def _persist_run_graph_async(graph: RunGraph) -> None:
    timestamp = _now_iso()
    for node in graph.nodes:
        await primary_execute(
            """
            INSERT INTO run_graph_nodes (
                agent_id, task_id, graph_id, node_id, attempt, parent_node_id, ordinal,
                node_type, status, summary, payload_json, redactions_json, refs_json,
                trace_id, audit_event_id, runtime_event_seq, source, started_at,
                completed_at, duration_ms, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?::jsonb, ?::jsonb, ?::jsonb,
                    ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (agent_id, task_id, node_id) DO UPDATE SET
                graph_id = EXCLUDED.graph_id,
                attempt = EXCLUDED.attempt,
                parent_node_id = EXCLUDED.parent_node_id,
                ordinal = EXCLUDED.ordinal,
                node_type = EXCLUDED.node_type,
                status = EXCLUDED.status,
                summary = EXCLUDED.summary,
                payload_json = EXCLUDED.payload_json,
                redactions_json = EXCLUDED.redactions_json,
                refs_json = EXCLUDED.refs_json,
                trace_id = EXCLUDED.trace_id,
                audit_event_id = EXCLUDED.audit_event_id,
                runtime_event_seq = EXCLUDED.runtime_event_seq,
                source = EXCLUDED.source,
                started_at = EXCLUDED.started_at,
                completed_at = EXCLUDED.completed_at,
                duration_ms = EXCLUDED.duration_ms,
                updated_at = EXCLUDED.updated_at
            """,
            (
                node.agent_id,
                node.task_id,
                node.graph_id,
                node.node_id,
                node.attempt,
                node.parent_node_id,
                node.ordinal,
                node.node_type,
                node.status,
                node.summary,
                _json_dumps(node.payload),
                _json_dumps(node.redactions),
                _json_dumps(node.refs),
                node.trace_id,
                node.audit_event_id,
                node.runtime_event_seq,
                node.source,
                node.started_at,
                node.completed_at,
                node.duration_ms,
                timestamp,
            ),
            agent_id=node.agent_id,
        )
    for edge in graph.edges:
        await primary_execute(
            """
            INSERT INTO run_graph_edges (
                agent_id, task_id, graph_id, edge_id, from_node_id, to_node_id,
                edge_type, ordinal, payload_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?::jsonb, ?)
            ON CONFLICT (agent_id, task_id, edge_id) DO UPDATE SET
                graph_id = EXCLUDED.graph_id,
                from_node_id = EXCLUDED.from_node_id,
                to_node_id = EXCLUDED.to_node_id,
                edge_type = EXCLUDED.edge_type,
                ordinal = EXCLUDED.ordinal,
                payload_json = EXCLUDED.payload_json,
                updated_at = EXCLUDED.updated_at
            """,
            (
                graph.agent_id,
                graph.task_id,
                edge.graph_id,
                edge.edge_id,
                edge.from_node_id,
                edge.to_node_id,
                edge.edge_type,
                edge.ordinal,
                _json_dumps(edge.payload),
                timestamp,
            ),
            agent_id=graph.agent_id,
        )


def persist_run_graph(graph: RunGraph) -> bool:
    """Best-effort graph persistence."""

    try:
        run_coro_sync(_persist_run_graph_async(graph))
        return True
    except Exception:
        log.warning("run_graph_persist_failed", graph_id=graph.graph_id, exc_info=True)
        return False


def persist_run_graph_from_trace(
    *,
    agent_id: str | None = None,
    task_id: int | None,
    trace: Mapping[str, Any] | None,
) -> RunGraph | None:
    """Build and persist a graph from the execution trace, failing open."""

    if task_id is None or trace is None:
        return None
    graph = build_run_graph_from_trace(agent_id=_normalize_agent_id(agent_id), task_id=int(task_id), trace=trace)
    persist_run_graph(graph)
    return graph


async def _load_persisted_run_graph_async(agent_id: str, task_id: int) -> RunGraph | None:
    nodes = await primary_fetch_all(
        """
        SELECT graph_id, agent_id, task_id, node_id, attempt, parent_node_id, ordinal,
               node_type, status, summary, payload_json, redactions_json, refs_json,
               trace_id, audit_event_id, runtime_event_seq, source, started_at,
               completed_at, duration_ms
          FROM run_graph_nodes
         WHERE agent_id = ? AND task_id = ?
      ORDER BY ordinal ASC, id ASC
        """,
        (agent_id, task_id),
        agent_id=agent_id,
    )
    if not nodes:
        return None
    edges = await primary_fetch_all(
        """
        SELECT graph_id, edge_id, from_node_id, to_node_id, edge_type, ordinal, payload_json
          FROM run_graph_edges
         WHERE agent_id = ? AND task_id = ?
      ORDER BY ordinal ASC, id ASC
        """,
        (agent_id, task_id),
        agent_id=agent_id,
    )
    graph_id = str(nodes[0].get("graph_id") or "")
    attempt = int(nodes[0].get("attempt") or 1)
    graph_nodes = tuple(
        RunGraphNode.from_dict(
            {
                "schema_version": "run_graph.v1",
                "graph_id": row.get("graph_id"),
                "agent_id": row.get("agent_id"),
                "task_id": row.get("task_id"),
                "node_id": row.get("node_id"),
                "attempt": row.get("attempt"),
                "parent_node_id": row.get("parent_node_id"),
                "ordinal": row.get("ordinal"),
                "node_type": row.get("node_type"),
                "status": row.get("status"),
                "summary": row.get("summary"),
                "payload": _json_load(row.get("payload_json"), {}),
                "redactions": _json_load(row.get("redactions_json"), {}),
                "refs": _json_load(row.get("refs_json"), {}),
                "trace_id": row.get("trace_id"),
                "audit_event_id": row.get("audit_event_id"),
                "runtime_event_seq": row.get("runtime_event_seq"),
                "source": row.get("source"),
                "started_at": row.get("started_at"),
                "completed_at": row.get("completed_at"),
                "duration_ms": row.get("duration_ms"),
            }
        )
        for row in nodes
    )
    graph_edges = tuple(
        RunGraphEdge.from_dict(
            {
                "schema_version": "run_graph.v1",
                "graph_id": row.get("graph_id"),
                "edge_id": row.get("edge_id"),
                "from_node_id": row.get("from_node_id"),
                "to_node_id": row.get("to_node_id"),
                "edge_type": row.get("edge_type"),
                "ordinal": row.get("ordinal"),
                "payload": _json_load(row.get("payload_json"), {}),
            }
        )
        for row in edges
    )
    counts: dict[str, int] = {}
    for node in graph_nodes:
        counts[node.node_type] = counts.get(node.node_type, 0) + 1
    return RunGraph(
        graph_id=graph_id,
        agent_id=agent_id,
        task_id=task_id,
        attempt=attempt,
        nodes=graph_nodes,
        edges=graph_edges,
        summary={
            "node_count": len(graph_nodes),
            "edge_count": len(graph_edges),
            "node_types": counts,
            "status": graph_nodes[0].status if graph_nodes else "info",
            "persisted": True,
        },
        source_refs={"persisted": True},
        replay_available=True,
    )


def load_persisted_run_graph(agent_id: str, task_id: int) -> RunGraph | None:
    try:
        return cast(
            RunGraph | None, run_coro_sync(_load_persisted_run_graph_async(_normalize_agent_id(agent_id), int(task_id)))
        )
    except Exception:
        log.warning("run_graph_load_failed", agent_id=agent_id, task_id=task_id, exc_info=True)
        return None


def graph_payload_for_execution(
    *,
    agent_id: str,
    task_id: int,
    trace: Mapping[str, Any] | None,
    runtime_events: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return persisted graph or redacted fallback reconstruction."""

    normalized = _normalize_agent_id(agent_id)
    graph = load_persisted_run_graph(normalized, int(task_id))
    if graph is None:
        graph = build_run_graph_from_trace(
            agent_id=normalized,
            task_id=int(task_id),
            trace=trace or {},
            runtime_events=runtime_events,
        )
    return graph.to_dict()


def replay_payload_for_execution(
    *,
    agent_id: str,
    task_id: int,
    trace: Mapping[str, Any] | None,
    runtime_events: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized = _normalize_agent_id(agent_id)
    graph = load_persisted_run_graph(normalized, int(task_id))
    if graph is None:
        graph = build_run_graph_from_trace(
            agent_id=normalized,
            task_id=int(task_id),
            trace=trace or {},
            runtime_events=runtime_events,
        )
    replay: RunReplayBundle = build_replay_bundle_from_trace(graph=graph, trace=trace or {})
    return replay.to_dict()
