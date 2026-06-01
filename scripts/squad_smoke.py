#!/usr/bin/env python3
"""Deterministic squad/run-graph smoke gate for KAT-001 fixtures."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from koda.services.run_graph import verify_run_graph_completeness

SQUAD_SMOKE_SCHEMA_VERSION = "squad_smoke.v1"
SQUAD_DELIVERY_SCHEMA_VERSION = "squad_delivery.v1"

_SQUAD_REQUIRED_NODE_TYPES = (
    "agent_request",
    "reply_obligation",
    "coordinator_synthesis",
    "dependency_call",
)
_SQUAD_REQUIRED_NODE_GROUPS = {"child_run_or_task_result": ("child_run", "squad_reply")}
_SQUAD_SYNTHESIS_RESULT_TYPES = {"child_run", "squad_reply", "dependency_call"}


class SquadSmokeError(RuntimeError):
    """Raised when the squad smoke input is malformed."""


def read_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SquadSmokeError(f"Smoke input not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SquadSmokeError(f"Smoke input is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SquadSmokeError("Smoke input must be a JSON object")
    return payload


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _event_types(events: list[Any]) -> set[str]:
    return {str(_as_dict(event).get("event_type") or "") for event in events}


def _event_items(events: list[Any], event_type: str) -> list[dict[str, Any]]:
    return [event for event in (_as_dict(item) for item in events) if event.get("event_type") == event_type]


def _node_type_by_id(run_graph: dict[str, Any]) -> dict[str, str]:
    nodes = _as_list(run_graph.get("nodes"))
    by_id: dict[str, str] = {}
    for node in nodes:
        raw = _as_dict(node)
        node_id = str(raw.get("node_id") or "")
        node_type = str(raw.get("node_type") or raw.get("type") or "")
        if node_id and node_type:
            by_id[node_id] = node_type
    return by_id


def _has_result_or_timeout_edge_to_synthesis(run_graph: dict[str, Any]) -> bool:
    by_id = _node_type_by_id(run_graph)
    synthesis_ids = {node_id for node_id, node_type in by_id.items() if node_type == "coordinator_synthesis"}
    if not synthesis_ids:
        return False
    for edge in (_as_dict(item) for item in _as_list(run_graph.get("edges"))):
        from_type = by_id.get(str(edge.get("from_node_id") or ""))
        to_id = str(edge.get("to_node_id") or "")
        if from_type in _SQUAD_SYNTHESIS_RESULT_TYPES and to_id in synthesis_ids:
            return True
    return False


def evaluate_squad_smoke(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if payload.get("schema_version") != SQUAD_SMOKE_SCHEMA_VERSION:
        failures.append(f"schema_version must be {SQUAD_SMOKE_SCHEMA_VERSION!r}; got {payload.get('schema_version')!r}")

    scenario = _as_dict(payload.get("scenario"))
    room = _as_dict(scenario.get("room"))
    if not room.get("squad_id") or not room.get("coordinator_agent_id") or not _as_list(room.get("participants")):
        failures.append("scenario.room must define squad_id, coordinator_agent_id, and participants")
    explicit_mention = _as_dict(scenario.get("explicit_mention"))
    mention_target = str(explicit_mention.get("target_agent_id") or "")
    if not mention_target or f"@{mention_target}" not in str(explicit_mention.get("text") or ""):
        failures.append("scenario.explicit_mention must include a target_agent_id and matching @mention text")

    delivery = _as_dict(payload.get("delivery"))
    if delivery.get("schema_version") != SQUAD_DELIVERY_SCHEMA_VERSION:
        failures.append("delivery.schema_version must be 'squad_delivery.v1'")
    route = _as_dict(delivery.get("route_decision"))
    if route.get("schema_version") != SQUAD_DELIVERY_SCHEMA_VERSION:
        failures.append("delivery.route_decision must use 'squad_delivery.v1'")
    route_targets = {str(item) for item in _as_list(route.get("targets"))}
    explicit_mentions = {str(item) for item in _as_list(route.get("explicit_mentions"))}
    if not route_targets:
        failures.append("mention/route must select at least one target")
    if not explicit_mentions:
        failures.append("mention/route must record the explicit mention that drove routing")
    if mention_target and mention_target not in route_targets:
        failures.append("mention/route target must match scenario.explicit_mention.target_agent_id")
    if mention_target and mention_target not in explicit_mentions:
        failures.append("mention/route explicit_mentions must include the scenario target")
    if route.get("final_response_strategy") != "coordinator_synthesis_after_all_task_results":
        failures.append("route_decision.final_response_strategy must wait for task results before synthesis")

    events = _as_list(delivery.get("events"))
    event_types = _event_types(events)
    obligation_events = _event_items(events, "reply_obligation")
    if not obligation_events:
        failures.append("reply obligation event is missing")
    else:
        target_sets = [{str(item) for item in _as_list(event.get("targets"))} for event in obligation_events]
        if mention_target and not any(mention_target in targets for targets in target_sets):
            failures.append("reply obligation target must include the explicit mention target")
        if not any(str(event.get("status") or "") in {"open", "routed"} for event in obligation_events):
            failures.append("reply obligation lifecycle must include an open/routed state")
    reply_events = _event_items(events, "squad_reply")
    if not any(_as_dict(event.get("payload")).get("in_reply_to") for event in reply_events):
        failures.append("squad reply must record in_reply_to evidence")
    if not any(str(event.get("status") or "") == "answered" for event in reply_events + obligation_events):
        failures.append("reply obligation lifecycle must include a resolved/answered state")
    if not ({"task_result", "child_run_completed"} & event_types):
        failures.append("child run or task result event is missing")
    synthesis_events = _event_items(events, "coordinator_synthesis")
    if not synthesis_events:
        failures.append("coordinator synthesis event is missing")
    timeout_events = _event_items(events, "partial_timeout")
    if not timeout_events:
        failures.append("partial timeout event is missing")
    elif not any(_as_list(_as_dict(event.get("payload")).get("timed_out_agent_ids")) for event in timeout_events):
        failures.append("partial timeout event must name timed_out_agent_ids")
    if synthesis_events and timeout_events:
        synthesis_payloads = [_as_dict(event.get("payload")) for event in synthesis_events]
        declares_timeout = any(
            _as_list(payload.get("timed_out_agent_ids")) or payload.get("timeout_declared")
            for payload in synthesis_payloads
        )
        if not declares_timeout:
            failures.append("coordinator synthesis must declare timed out obligations when timeout evidence exists")

    run_graph = _as_dict(payload.get("run_graph"))
    graph_report = verify_run_graph_completeness(
        run_graph,
        scenario="squad",
        required_node_types=_SQUAD_REQUIRED_NODE_TYPES,
        any_node_type_groups=_SQUAD_REQUIRED_NODE_GROUPS,
        requires_partial_timeout=True,
        require_synthesis_path=True,
    )
    if graph_report["status"] != "passed":
        missing = ", ".join(graph_report.get("missing_node_types") or [])
        failures.append(f"run graph completeness failed: {missing or 'missing required node group'}")
    if not _has_result_or_timeout_edge_to_synthesis(run_graph):
        failures.append("run graph must include a causal result/timeout edge into coordinator synthesis")
    return failures


async def execute_squad_smoke(payload: dict[str, Any], *, dsn: str, schema: str) -> dict[str, Any]:
    """Execute a minimal Postgres-backed squad room scenario for optional smoke evidence."""

    from koda.squads.replies import ThreadReplyService
    from koda.squads.tasks import SquadTaskStore
    from koda.squads.threads import SquadThreadStore

    scenario = _as_dict(payload.get("scenario"))
    room = _as_dict(scenario.get("room"))
    explicit_mention = _as_dict(scenario.get("explicit_mention"))
    coordinator = str(room.get("coordinator_agent_id") or "PM")
    participants = [str(item) for item in _as_list(room.get("participants")) if str(item)]
    mention_target = str(explicit_mention.get("target_agent_id") or "FE")
    timeout_target = str(_as_dict(scenario.get("timeout_obligation")).get("target_agent_id") or "QA")
    if mention_target not in participants:
        participants.append(mention_target)
    if timeout_target not in participants:
        participants.append(timeout_target)

    threads = SquadThreadStore(dsn=dsn, schema=schema)
    tasks = SquadTaskStore(dsn=dsn, schema=schema)
    replies = ThreadReplyService(threads)
    try:
        thread = await threads.create_thread(
            workspace_id=str(room.get("workspace_id") or "p0-smoke"),
            squad_id=str(room.get("squad_id") or "build"),
            title=f"KAT-001 smoke {datetime.now(UTC).isoformat()}",
            coordinator_agent_id=coordinator,
            participants=[(agent_id, "worker") for agent_id in participants if agent_id != coordinator],
        )
        root_id = await threads.post_thread_message(
            thread_id=thread.id,
            from_agent="operator",
            content=str(explicit_mention.get("text") or f"@{mention_target} review this"),
            message_type="user_input",
            to_agent_ids=[mention_target],
            metadata={"schema_version": "squad_delivery.v1", "route_source": "explicit_mention"},
        )
        obligations = await replies.create_obligations(
            thread_id=thread.id,
            source_message_id=root_id,
            target_agent_ids=[mention_target, timeout_target],
            source_agent_id=coordinator,
            requires_response_by=datetime.now(UTC) - timedelta(seconds=1),
        )
        reply_id = await threads.post_thread_message(
            thread_id=thread.id,
            from_agent=mention_target,
            content="Smoke reply completed.",
            message_type="agent_reply",
            in_reply_to=f"msg-{root_id}",
            correlation_id=obligations[0].obligation_key if obligations else None,
        )
        resolved = await replies.resolve_for_reply(
            thread_id=thread.id,
            reply_message_id=reply_id,
            from_agent=mention_target,
            in_reply_to=f"msg-{root_id}",
            correlation_id=obligations[0].obligation_key if obligations else None,
        )
        timed_out = await replies.mark_timeouts(limit=10)
        task = await tasks.create_task(
            thread_id=thread.id,
            title="KAT-001 smoke task",
            assigner_agent_id=coordinator,
            assigned_agent_id=mention_target,
            idempotency_key=f"kat-001:{thread.id}",
        )
        await tasks.claim_task(task_id=task.id, agent_id=mention_target)
        await tasks.update_task_status(task_id=task.id, new_status="in_progress", agent_id=mention_target)
        done = await tasks.complete_task(task_id=task.id, agent_id=mention_target, result_summary="Smoke task done")
        return {
            "thread_id": thread.id,
            "root_message_id": root_id,
            "reply_message_id": reply_id,
            "answered_obligations": [item.to_dict() for item in resolved],
            "timed_out_obligations": [item.to_dict() for item in timed_out if item.thread_id == thread.id],
            "task": done.to_dict(),
        }
    finally:
        await threads.close()
        await tasks.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Path to a squad_smoke.v1 JSON payload.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Optionally execute the smoke against Postgres using --dsn or POSTGRES_TEST_DSN.",
    )
    parser.add_argument("--dsn", default="", help="Postgres DSN for --execute. Defaults to POSTGRES_TEST_DSN.")
    parser.add_argument(
        "--schema",
        default=os.environ.get("KNOWLEDGE_V2_POSTGRES_SCHEMA", "knowledge_v2"),
        help="Postgres schema for --execute.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        payload = read_payload(args.input)
        failures = evaluate_squad_smoke(payload)
    except SquadSmokeError as exc:
        print(f"squad smoke input error: {exc}", file=sys.stderr)
        return 2
    if failures:
        print("squad smoke failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    if args.execute:
        dsn = str(args.dsn or os.environ.get("POSTGRES_TEST_DSN") or "").strip()
        if not dsn:
            print("squad smoke execute requires --dsn or POSTGRES_TEST_DSN", file=sys.stderr)
            return 2
        result = asyncio.run(execute_squad_smoke(payload, dsn=dsn, schema=str(args.schema or "knowledge_v2")))
        print(json.dumps({"status": "executed", **result}, sort_keys=True, default=str))
        return 0
    print("squad smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
