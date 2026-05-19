from __future__ import annotations

from koda.services.run_graph import (
    RUN_GRAPH_SCHEMA_VERSION,
    RUN_REPLAY_SCHEMA_VERSION,
    RunGraph,
    RunGraphEdge,
    RunGraphNode,
    build_replay_bundle_from_trace,
    build_run_graph_from_trace,
    make_edge_id,
    make_graph_id,
    make_node_id,
)


def test_run_graph_dataclasses_serialize_and_round_trip() -> None:
    graph_id = make_graph_id("KODA", 42, 2)
    root_id = make_node_id(graph_id, "model_call", 1)
    tool_id = make_node_id(graph_id, "tool_result", 2, {"tool": "shell_execute"})
    edge_id = make_edge_id(graph_id, root_id, tool_id, "produces", 1)
    graph = RunGraph(
        graph_id=graph_id,
        agent_id="KODA",
        task_id=42,
        attempt=2,
        nodes=(
            RunGraphNode(
                node_id=root_id,
                graph_id=graph_id,
                agent_id="KODA",
                task_id=42,
                attempt=2,
                node_type="model_call",
                status="completed",
                ordinal=1,
                summary="Model turn",
                payload={"api_key": "sk-live-secret", "query_preview": "deploy"},
            ),
            RunGraphNode(
                node_id=tool_id,
                graph_id=graph_id,
                agent_id="KODA",
                task_id=42,
                attempt=2,
                node_type="tool_result",
                status="completed",
                ordinal=2,
                summary="Tool result",
                parent_node_id=root_id,
                payload={"tool": "shell_execute", "output": "ok"},
            ),
        ),
        edges=(
            RunGraphEdge(
                edge_id=edge_id,
                graph_id=graph_id,
                from_node_id=root_id,
                to_node_id=tool_id,
                edge_type="produces",
                ordinal=1,
            ),
        ),
        summary={"source": "unit-test"},
    )

    payload = graph.to_dict()
    assert payload["schema_version"] == RUN_GRAPH_SCHEMA_VERSION
    assert payload["nodes"][0]["payload"]["api_key"] == "[REDACTED]"
    assert RunGraph.from_dict(payload).to_dict() == payload


def test_deterministic_ids_are_stable_and_source_sensitive() -> None:
    graph_id = make_graph_id("KODA", 7, 1)
    first = make_node_id(graph_id, "tool_result", 3, {"tool": "read_file"})
    second = make_node_id(graph_id, "tool_result", 3, {"tool": "read_file"})
    changed = make_node_id(graph_id, "tool_result", 3, {"tool": "write_file"})

    assert first == second
    assert first != changed
    assert make_edge_id(graph_id, "a", "b", "contains", 1) == make_edge_id(graph_id, "a", "b", "contains", 1)


def test_build_run_graph_from_flat_trace_runtime_events_and_redaction() -> None:
    trace = {
        "trace_version": 1,
        "schema": "execution_trace",
        "request": {
            "query_text": "deploy with token=live-secret",
            "model": "gpt-5-codex",
            "session_id": "sess-1",
            "work_dir": "/tmp/work",
        },
        "assistant": {"response_text": "done"},
        "runtime": {
            "status": "completed",
            "attempt": 2,
            "max_attempts": 3,
            "stop_reason": "completed",
        },
        "grounding": {
            "knowledge_hit_count": 1,
            "memory_layers": ["workspace"],
            "memory_retrieval_sources": ["memory"],
            "effective_policy": {"task_kind": "deploy", "autonomy_tier": "review"},
        },
        "tools": [
            {
                "tool": "shell_execute",
                "params": {"command": "echo ok", "api_key": "sk-live-secret"},
                "success": True,
                "output": "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456",
                "metadata": {"write": True, "category": "shell"},
                "duration_ms": 17,
                "started_at": "2026-05-16T12:00:01+00:00",
                "completed_at": "2026-05-16T12:00:02+00:00",
            }
        ],
        "timeline": [
            {
                "type": "task.retried",
                "title": "Retry scheduled",
                "status": "warning",
                "timestamp": "2026-05-16T12:00:03+00:00",
            }
        ],
        "_cost_usd": 0.12,
    }
    runtime_events = [
        {
            "id": 1,
            "task_id": 42,
            "attempt": 2,
            "event_type": "provider.dependency_timeout",
            "severity": "error",
            "payload": {"provider": "codex", "status": "failed"},
        },
        {
            "id": 2,
            "task_id": 42,
            "attempt": 2,
            "event_type": "routing_decision",
            "severity": "info",
            "payload": {"schema_version": "squad_delivery.v1", "targets": ["FE"]},
        },
    ]

    graph = build_run_graph_from_trace(agent_id="KODA", task_id=42, trace=trace, runtime_events=runtime_events)
    node_types = [node.node_type for node in graph.nodes]
    encoded = str(graph.to_dict())

    assert graph.graph_id == "run:KODA:42:attempt:2"
    assert "model_call" in node_types
    assert "context_block" in node_types
    assert "policy_gate" in node_types
    assert "tool_request" in node_types
    assert "tool_result" in node_types
    assert "retry_scheduled" in node_types
    assert "dependency_call" in node_types
    assert "agent_request" in node_types
    assert "cost" in node_types
    assert "sk-live-secret" not in encoded
    assert "abcdefghijklmnopqrstuvwxyz123456" not in encoded
    assert "[REDACTED]" in encoded


def test_offline_replay_bundle_uses_recorded_payloads_and_disables_provider_calls() -> None:
    trace = {
        "request": {"query_text": "read file", "model": "gpt-5-codex", "session_id": "sess-7"},
        "assistant": {"response_text": "done"},
        "runtime": {"status": "completed", "attempt": 1, "stop_reason": "completed"},
        "tools": [{"tool": "read_file", "success": True, "output": "ok"}],
    }
    graph = build_run_graph_from_trace(agent_id="KODA", task_id=7, trace=trace)

    bundle = build_replay_bundle_from_trace(graph=graph, trace=trace)
    payload = bundle.to_dict()

    assert payload["schema_version"] == RUN_REPLAY_SCHEMA_VERSION
    assert payload["replay_mode"] == "offline"
    assert payload["inputs"]["query_preview"] == "read file"
    assert payload["model_outputs"][0]["response_preview"] == "done"
    assert payload["tool_results"][0]["tool"] == "read_file"
    assert payload["divergences"] == []
