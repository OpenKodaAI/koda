#!/usr/bin/env python3
"""Seed deterministic local E2E records for the authenticated Playwright suite.

Run after ``scripts/seed_demo_data.py --apply`` inside the disposable Docker
stack. The seed is additive and only clears rows tagged with the e2e marker.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from seed_demo_data import dumps, execute, iso, load_environment, quote_identifier, table

E2E_MARKER = "koda-e2e"
DEFAULT_AGENT_ID = "DEMO_ATLAS"
E2E_USER_ID = 92_001
E2E_CHAT_ID = 92_001


def now_utc() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


async def table_exists(conn: Any, schema: str, name: str) -> bool:
    return bool(await conn.fetchval("SELECT to_regclass($1)", f"{schema}.{name}"))


async def clear_e2e_data(conn: Any, schema: str, agent_id: str) -> None:
    deletes: list[tuple[str, tuple[Any, ...]]] = [
        (
            f"DELETE FROM {table(schema, 'run_graph_edges')} WHERE agent_id=$1 AND graph_id LIKE 'e2e:%'",
            (agent_id,),
        ),
        (
            f"DELETE FROM {table(schema, 'run_graph_nodes')} WHERE agent_id=$1 AND graph_id LIKE 'e2e:%'",
            (agent_id,),
        ),
        (
            f"DELETE FROM {table(schema, 'run_replay_snapshots')} WHERE agent_id=$1 AND graph_id LIKE 'e2e:%'",
            (agent_id,),
        ),
        (
            f"DELETE FROM {table(schema, 'child_runs')} WHERE agent_id=$1 AND child_run_id LIKE 'e2e:%'",
            (agent_id,),
        ),
        (
            f"DELETE FROM {table(schema, 'skill_package_events')} WHERE agent_id=$1 AND package_id='e2e.safe-readonly'",
            (agent_id,),
        ),
        (
            f"DELETE FROM {table(schema, 'skill_packages')} WHERE agent_id=$1 AND package_id='e2e.safe-readonly'",
            (agent_id,),
        ),
        (
            f"DELETE FROM {table(schema, 'eval_suite_cases')} WHERE agent_id=$1 AND suite_id='e2e-suite'",
            (agent_id,),
        ),
        (
            f"DELETE FROM {table(schema, 'eval_suites')} WHERE agent_id=$1 AND suite_id='e2e-suite'",
            (agent_id,),
        ),
        (
            f"DELETE FROM {table(schema, 'eval_run_batches')} WHERE agent_id=$1 AND run_id LIKE 'e2e:%'",
            (agent_id,),
        ),
        (
            f"DELETE FROM {table(schema, 'trajectory_exports')} WHERE agent_id=$1 AND export_id LIKE 'e2e:%'",
            (agent_id,),
        ),
        (
            f"DELETE FROM {table(schema, 'release_quality_runs')} WHERE agent_id=$1 AND payload_json->>'seed'=$2",
            (agent_id, E2E_MARKER),
        ),
        (
            f"DELETE FROM {table(schema, 'evaluation_runs')} WHERE agent_id=$1 AND metadata_json->>'seed'=$2",
            (agent_id, E2E_MARKER),
        ),
        (
            f"DELETE FROM {table(schema, 'evaluation_cases')} WHERE agent_id=$1 AND case_key LIKE 'e2e:%'",
            (agent_id,),
        ),
        (
            f"DELETE FROM {table(schema, 'channel_gateway_events')} WHERE agent_id=$1 AND event_json->>'seed'=$2",
            (agent_id, E2E_MARKER),
        ),
        (
            f"DELETE FROM {table(schema, 'channel_pairing_codes')} WHERE agent_id=$1 AND pairing_code_id LIKE 'e2e:%'",
            (agent_id,),
        ),
        (
            f"DELETE FROM {table(schema, 'channel_unknown_senders')} WHERE agent_id=$1 AND identity_id LIKE 'e2e:%'",
            (agent_id,),
        ),
        (
            f"DELETE FROM {table(schema, 'channel_gateway_identities')} WHERE agent_id=$1 AND identity_id LIKE 'e2e:%'",
            (agent_id,),
        ),
        (
            f"DELETE FROM {table(schema, 'onboarding_readiness_runs')} WHERE agent_id=$1 AND payload_json->>'seed'=$2",
            (agent_id, E2E_MARKER),
        ),
        (
            (
                f"DELETE FROM {table(schema, 'tasks')} "
                "WHERE agent_id=$1 AND (query_text='E2E seeded parent execution' "
                "OR query_text LIKE 'E2E child-run:%')"
            ),
            (agent_id,),
        ),
    ]
    for sql, params in deletes:
        name = sql.split('"')[-2] if '"' in sql else ""
        if not name or await table_exists(conn, schema, name):
            await execute(conn, sql, *params)


async def ensure_parent_task(conn: Any, schema: str, agent_id: str) -> int:
    task_id = await conn.fetchval(
        f"""
        SELECT id FROM {table(schema, "tasks")}
        WHERE agent_id=$1 AND query_text='E2E seeded parent execution'
        ORDER BY id DESC
        LIMIT 1
        """,
        agent_id,
    )
    if task_id:
        return int(task_id)
    timestamp = iso(now_utc() - timedelta(minutes=12))
    return int(
        await conn.fetchval(
            f"""
            INSERT INTO {table(schema, "tasks")}
                (agent_id, user_id, chat_id, status, query_text, provider, model, work_dir,
                 attempt, max_attempts, cost_usd, created_at, started_at, completed_at,
                 session_id, provider_session_id, classification, environment_kind,
                 current_phase, last_heartbeat_at)
            VALUES ($1, $2, $3, 'completed', 'E2E seeded parent execution', 'fake',
                    'offline-replay', '/tmp/koda-e2e', 1, 3, 0.0, $4, $4, $4,
                    'e2e-session', 'e2e-provider-session', 'operator_task',
                    'ephemeral', 'completed', $4)
            RETURNING id
            """,
            agent_id,
            E2E_USER_ID,
            E2E_CHAT_ID,
            timestamp,
        )
    )


async def seed_child_task(conn: Any, schema: str, agent_id: str, parent_task_id: int) -> int:
    timestamp = iso(now_utc() - timedelta(minutes=8))
    return int(
        await conn.fetchval(
            f"""
            INSERT INTO {table(schema, "tasks")}
                (agent_id, user_id, chat_id, status, query_text, provider, model, work_dir,
                 attempt, max_attempts, cost_usd, created_at, started_at, completed_at,
                 session_id, provider_session_id, source_task_id, source_action,
                 classification, environment_kind, current_phase, last_heartbeat_at)
            VALUES ($1, $2, $3, 'completed', 'E2E child-run: summarize fixture context',
                    'fake', 'offline-replay', '/tmp/koda-e2e-child', 1, 1, 0.0,
                    $4, $4, $4, 'e2e-session-child', 'e2e-provider-child',
                    $5, 'child_run', 'operator_task', 'ephemeral', 'completed', $4)
            RETURNING id
            """,
            agent_id,
            E2E_USER_ID,
            E2E_CHAT_ID,
            timestamp,
            parent_task_id,
        )
    )


async def seed_run_graph(conn: Any, schema: str, agent_id: str, task_id: int) -> None:
    graph_id = f"e2e:{agent_id}:{task_id}"
    created = now_utc() - timedelta(minutes=7)
    nodes = [
        ("e2e-model-call", "model_call", "completed", "Offline model call"),
        ("e2e-policy-gate", "policy_gate", "completed", "ExecutionPolicy allowed read-only tool"),
        ("e2e-tool-request", "tool_request", "completed", "Read-only tool requested"),
        ("e2e-tool-result", "tool_result", "completed", "Tool returned redacted payload"),
        ("e2e-child-run", "child_run", "completed", "Delegate Task child-run completed"),
        ("e2e-user-output", "runtime_event", "completed", "Final answer emitted"),
    ]
    for ordinal, (node_id, node_type, status, summary) in enumerate(nodes, start=1):
        await execute(
            conn,
            f"""
            INSERT INTO {table(schema, "run_graph_nodes")}
                (agent_id, task_id, graph_id, node_id, attempt, parent_node_id, ordinal,
                 node_type, status, summary, payload_json, redactions_json, refs_json,
                 trace_id, source, started_at, completed_at, duration_ms, updated_at)
            VALUES ($1, $2, $3, $4, 1, NULL, $5, $6, $7, $8, $9::jsonb, $10::jsonb,
                    $11::jsonb, $12, 'seed_e2e_data', $13, $13, $14, $13)
            ON CONFLICT (agent_id, task_id, node_id) DO UPDATE SET
                graph_id=EXCLUDED.graph_id,
                ordinal=EXCLUDED.ordinal,
                node_type=EXCLUDED.node_type,
                status=EXCLUDED.status,
                summary=EXCLUDED.summary,
                payload_json=EXCLUDED.payload_json,
                redactions_json=EXCLUDED.redactions_json,
                refs_json=EXCLUDED.refs_json,
                updated_at=EXCLUDED.updated_at
            """,
            agent_id,
            task_id,
            graph_id,
            node_id,
            ordinal,
            node_type,
            status,
            summary,
            dumps({"seed": E2E_MARKER, "schema_version": "run_graph.v1", "offline": True}),
            dumps([{"field": "prompt", "reason": "e2e redaction"}]),
            dumps([{"kind": "task", "id": str(task_id)}]),
            f"trace-e2e-{task_id}",
            created + timedelta(seconds=ordinal),
            ordinal * 17,
        )
    for ordinal, (from_node, to_node) in enumerate(zip(nodes, nodes[1:], strict=False), start=1):
        await execute(
            conn,
            f"""
            INSERT INTO {table(schema, "run_graph_edges")}
                (agent_id, task_id, graph_id, edge_id, from_node_id, to_node_id,
                 edge_type, ordinal, payload_json, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, 'sequence', $7, $8::jsonb, NOW())
            ON CONFLICT (agent_id, task_id, edge_id) DO UPDATE SET
                from_node_id=EXCLUDED.from_node_id,
                to_node_id=EXCLUDED.to_node_id,
                payload_json=EXCLUDED.payload_json,
                updated_at=NOW()
            """,
            agent_id,
            task_id,
            graph_id,
            f"e2e-edge-{ordinal}",
            from_node[0],
            to_node[0],
            ordinal,
            dumps({"seed": E2E_MARKER}),
        )
    await execute(
        conn,
        f"""
        INSERT INTO {table(schema, "run_replay_snapshots")}
            (agent_id, task_id, graph_id, attempt, replay_mode, payload_json)
        VALUES ($1, $2, $3, 1, 'offline', $4::jsonb)
        ON CONFLICT (agent_id, task_id, graph_id, attempt) DO UPDATE SET
            replay_mode=EXCLUDED.replay_mode,
            payload_json=EXCLUDED.payload_json,
            created_at=NOW()
        """,
        agent_id,
        task_id,
        graph_id,
        dumps(
            {
                "schema_version": "run_replay.v1",
                "seed": E2E_MARKER,
                "replay_mode": "offline",
                "provider_calls_disabled": True,
                "missing_data": [],
                "divergences": [],
                "steps": [{"node_id": node[0], "status": node[2]} for node in nodes],
            }
        ),
    )


async def seed_child_runs(conn: Any, schema: str, agent_id: str, parent_task_id: int, child_task_id: int) -> None:
    await execute(
        conn,
        f"""
        INSERT INTO {table(schema, "child_runs")}
            (agent_id, child_run_id, parent_task_id, child_task_id, status, idempotency_key,
             target_agent_id, toolset, request_json, context_policy_json, context_summary_json,
             result_json, error_json, deadline_at, started_at, completed_at, updated_at)
        VALUES ($1, 'e2e:child-run:1', $2, $3, 'completed', 'e2e-idempotency-1',
                $1, 'read_only', $4::jsonb, $5::jsonb, $6::jsonb, $7::jsonb,
                '{{}}'::jsonb, NOW() + interval '10 minutes', NOW() - interval '8 minutes',
                NOW() - interval '7 minutes', NOW())
        ON CONFLICT (agent_id, child_run_id) DO UPDATE SET
            child_task_id=EXCLUDED.child_task_id,
            status=EXCLUDED.status,
            result_json=EXCLUDED.result_json,
            updated_at=NOW()
        """,
        agent_id,
        parent_task_id,
        child_task_id,
        dumps({"schema_version": "child_run.v1", "goal": "Summarize fixture context", "seed": E2E_MARKER}),
        dumps({"schema_version": "context_governance.v1", "max_context_tokens": 1200, "toolset": "read_only"}),
        dumps(
            {
                "included_blocks": 2,
                "dropped_blocks": 1,
                "redactions": [{"category": "secret", "action": "dropped"}],
                "seed": E2E_MARKER,
            }
        ),
        dumps({"summary": "Fixture context summarized.", "structured_output": {"ok": True}, "warnings": []}),
    )


async def seed_skill_package(conn: Any, schema: str, agent_id: str) -> None:
    manifest = {
        "schema_version": "koda_skill.v1",
        "id": "e2e.safe-readonly",
        "name": "E2E Safe Readonly",
        "version": "1.0.0",
        "description": "Deterministic local package for E2E UI checks.",
        "author": "Koda E2E",
        "skills": [{"id": "e2e_brief", "name": "E2E Brief", "instruction": "Summarize seeded context."}],
        "tools": [{"id": "skill.e2e_read", "title": "E2E Read", "risk_class": "read_context"}],
        "permissions": ["read_context"],
    }
    scan = {
        "schema_version": "skill_scan.v1",
        "decision": "allow",
        "severity": "low",
        "findings": [],
        "permissions_requested": ["read_context"],
        "risk_classes": ["read_context"],
        "package_hash": "sha256:e2e-safe",
        "scanner_version": "e2e",
    }
    lock = {
        "schema_version": "skill_lock.v1",
        "package_id": "e2e.safe-readonly",
        "version": "1.0.0",
        "package_hash": "sha256:e2e-safe",
        "seed": E2E_MARKER,
    }
    await execute(
        conn,
        f"""
        INSERT INTO {table(schema, "skill_packages")}
            (agent_id, package_id, status, package_hash, manifest_json, scan_json,
             lock_json, installed_skills_json, installed_tools_json, previous_lock_json,
             installed_at, updated_at)
        VALUES ($1, 'e2e.safe-readonly', 'installed', 'sha256:e2e-safe', $2::jsonb,
                $3::jsonb, $4::jsonb, $5::jsonb, $6::jsonb, '{{}}'::jsonb, NOW(), NOW())
        ON CONFLICT (agent_id, package_id) DO UPDATE SET
            status='installed',
            manifest_json=EXCLUDED.manifest_json,
            scan_json=EXCLUDED.scan_json,
            lock_json=EXCLUDED.lock_json,
            installed_skills_json=EXCLUDED.installed_skills_json,
            installed_tools_json=EXCLUDED.installed_tools_json,
            updated_at=NOW()
        """,
        agent_id,
        dumps(manifest),
        dumps(scan),
        dumps(lock),
        dumps(manifest["skills"]),
        dumps(manifest["tools"]),
    )


async def seed_evals(conn: Any, schema: str, agent_id: str, task_id: int) -> None:
    case_key = "e2e:case:run-graph"
    await execute(
        conn,
        f"""
        INSERT INTO {table(schema, "evaluation_cases")}
            (agent_id, case_key, query, source_task_id, task_kind, project_key,
             environment, team, modality, expected_sources_json, expected_layers_json,
             reference_answer, status, gold_source_kind, validated_by, validated_at,
             metadata_json, updated_at)
        VALUES ($1, $2, 'E2E seeded eval from run', $3, 'release_smoke',
                'e2e', 'local', 'qa', 'text', $4::jsonb, $5::jsonb,
                'The run should replay offline without secrets.', 'active',
                'from_run', 'seed_e2e_data', $6, $7::jsonb, NOW())
        ON CONFLICT (agent_id, case_key) DO UPDATE SET
            source_task_id=EXCLUDED.source_task_id,
            status=EXCLUDED.status,
            metadata_json=EXCLUDED.metadata_json,
            updated_at=NOW()
        """,
        agent_id,
        case_key,
        task_id,
        dumps(["run_graph", "tool_result"]),
        dumps(["runtime", "policy"]),
        iso(now_utc()),
        dumps({"seed": E2E_MARKER, "redacted": True}),
    )
    await execute(
        conn,
        f"""
        INSERT INTO {table(schema, "eval_suites")}
            (agent_id, suite_id, title, description, status, metadata_json, updated_at)
        VALUES ($1, 'e2e-suite', 'E2E release smoke', 'Offline deterministic E2E suite.',
                'active', $2::jsonb, NOW())
        ON CONFLICT (agent_id, suite_id) DO UPDATE SET
            title=EXCLUDED.title,
            description=EXCLUDED.description,
            metadata_json=EXCLUDED.metadata_json,
            updated_at=NOW()
        """,
        agent_id,
        dumps({"seed": E2E_MARKER}),
    )
    await execute(
        conn,
        f"""
        INSERT INTO {table(schema, "eval_suite_cases")}
            (agent_id, suite_id, case_key, position)
        VALUES ($1, 'e2e-suite', $2, 1)
        ON CONFLICT (agent_id, suite_id, case_key) DO UPDATE SET position=EXCLUDED.position
        """,
        agent_id,
        case_key,
    )
    await execute(
        conn,
        f"""
        INSERT INTO {table(schema, "eval_run_batches")}
            (run_id, agent_id, suite_id, strategy, status, score, summary_json,
             case_results_json, requested_by, updated_at)
        VALUES ('e2e:run:latest', $1, 'e2e-suite', 'offline_replay', 'passed', 1.0,
                $2::jsonb, $3::jsonb, 'seed_e2e_data', NOW())
        ON CONFLICT (agent_id, run_id) DO UPDATE SET
            status=EXCLUDED.status,
            score=EXCLUDED.score,
            summary_json=EXCLUDED.summary_json,
            case_results_json=EXCLUDED.case_results_json,
            updated_at=NOW()
        """,
        agent_id,
        dumps({"total": 1, "passed": 1, "failed": 0, "seed": E2E_MARKER}),
        dumps([{"case_key": case_key, "status": "passed", "score": 1.0}]),
    )
    payload = {
        "schema_version": "trajectory_export.v1",
        "seed": E2E_MARKER,
        "format": "jsonl",
        "status": "created",
        "redacted": True,
        "provider_calls_disabled": True,
        "records": 4,
    }
    await execute(
        conn,
        f"""
        INSERT INTO {table(schema, "trajectory_exports")}
            (export_id, agent_id, task_id, status, package_hash, payload_json, jsonl_text)
        VALUES ('e2e:trajectory:latest', $1, $2, 'created', 'sha256:e2e-trajectory',
                $3::jsonb, $4)
        ON CONFLICT (agent_id, export_id) DO UPDATE SET
            task_id=EXCLUDED.task_id,
            status=EXCLUDED.status,
            payload_json=EXCLUDED.payload_json,
            jsonl_text=EXCLUDED.jsonl_text,
            created_at=NOW()
        """,
        agent_id,
        task_id,
        dumps(payload),
        '{"type":"model_call","redacted":true}\n{"type":"tool_result","redacted":true}\n',
    )
    await execute(
        conn,
        f"""
        INSERT INTO {table(schema, "release_quality_runs")}
            (agent_id, status, payload_json, created_at)
        VALUES ($1, 'passed', $2::jsonb, NOW())
        """,
        agent_id,
        dumps(
            {
                "schema_version": "release_quality.v1",
                "seed": E2E_MARKER,
                "status": "passed",
                "smoke": "passed",
                "eval_suite": "passed",
                "export_redaction": "passed",
            }
        ),
    )


async def seed_channel_and_readiness(conn: Any, schema: str, agent_id: str) -> None:
    now = now_utc()
    expires = now + timedelta(hours=1)
    allowed_identity = {
        "schema_version": "channel_gateway.v1",
        "agent_id": agent_id,
        "identity_id": "e2e:telegram:allowed",
        "channel_type": "telegram",
        "channel_id": "-10092001",
        "user_id": "92001",
        "display_name": "E2E Approved Operator",
        "status": "allowed",
        "is_group": False,
        "scopes": ["message"],
        "source": "seed_e2e_data",
        "allowed_by": "seed_e2e_data",
        "created_at": iso(now),
        "updated_at": iso(now),
        "last_seen_at": iso(now),
        "metadata": {"seed": E2E_MARKER},
    }
    await execute(
        conn,
        f"""
        INSERT INTO {table(schema, "channel_gateway_identities")}
            (agent_id, identity_id, channel_type, channel_id, user_id, display_name,
             status, is_group, record_json, last_seen_at, updated_at)
        VALUES ($1, 'e2e:telegram:allowed', 'telegram', '-10092001', '92001',
                'E2E Approved Operator', 'allowed', false, $2::jsonb, NOW(), NOW())
        ON CONFLICT (agent_id, identity_id) DO UPDATE SET
            status=EXCLUDED.status,
            record_json=EXCLUDED.record_json,
            updated_at=NOW()
        """,
        agent_id,
        dumps(allowed_identity),
    )
    unknown_sender = {
        "schema_version": "channel_gateway.v1",
        "agent_id": agent_id,
        "identity_id": "e2e:telegram:unknown",
        "channel_type": "telegram",
        "channel_id": "-10092002",
        "user_id": "92002",
        "display_name": "E2E Unknown Sender",
        "is_group": False,
        "message_id": "e2e-message-1",
        "message_preview": "hello from deterministic e2e",
        "status": "pending",
        "first_seen_at": iso(now),
        "last_seen_at": iso(now),
        "seed": E2E_MARKER,
    }
    await execute(
        conn,
        f"""
        INSERT INTO {table(schema, "channel_unknown_senders")}
            (agent_id, identity_id, channel_type, channel_id, user_id, display_name,
             status, payload_json, first_seen_at, last_seen_at)
        VALUES ($1, 'e2e:telegram:unknown', 'telegram', '-10092002', '92002',
                'E2E Unknown Sender', 'pending', $2::jsonb, NOW(), NOW())
        ON CONFLICT (agent_id, identity_id) DO UPDATE SET
            status='pending',
            payload_json=EXCLUDED.payload_json,
            last_seen_at=NOW()
        """,
        agent_id,
        dumps(unknown_sender),
    )
    block_sender = {
        **unknown_sender,
        "identity_id": "e2e:telegram:block",
        "channel_id": "-10092003",
        "user_id": "92003",
        "display_name": "E2E Block Sender",
        "message_id": "e2e-message-2",
        "message_preview": "please block this deterministic e2e sender",
    }
    await execute(
        conn,
        f"""
        INSERT INTO {table(schema, "channel_unknown_senders")}
            (agent_id, identity_id, channel_type, channel_id, user_id, display_name,
             status, payload_json, first_seen_at, last_seen_at)
        VALUES ($1, 'e2e:telegram:block', 'telegram', '-10092003', '92003',
                'E2E Block Sender', 'pending', $2::jsonb, NOW(), NOW())
        ON CONFLICT (agent_id, identity_id) DO UPDATE SET
            status='pending',
            payload_json=EXCLUDED.payload_json,
            last_seen_at=NOW()
        """,
        agent_id,
        dumps(block_sender),
    )
    pairing_code = {
        "schema_version": "channel_gateway.v1",
        "agent_id": agent_id,
        "pairing_code_id": "e2e:pairing:latest",
        "channel_type": "telegram",
        "code": "E2E-PAIR",
        "status": "active",
        "created_by": "seed_e2e_data",
        "created_at": iso(now),
        "expires_at": iso(expires),
        "used_at": "",
        "seed": E2E_MARKER,
    }
    await execute(
        conn,
        f"""
        INSERT INTO {table(schema, "channel_pairing_codes")}
            (agent_id, pairing_code_id, channel_type, code, payload_json, expires_at)
        VALUES ($1, 'e2e:pairing:latest', 'telegram', 'E2E-PAIR', $2::jsonb, $3)
        ON CONFLICT (agent_id, pairing_code_id) DO UPDATE SET
            code=EXCLUDED.code,
            payload_json=EXCLUDED.payload_json,
            expires_at=EXCLUDED.expires_at,
            used_at=NULL
        """,
        agent_id,
        dumps(pairing_code),
        expires,
    )
    await execute(
        conn,
        f"""
        INSERT INTO {table(schema, "onboarding_readiness_runs")}
            (agent_id, status, payload_json, created_at)
        VALUES ($1, 'warning', $2::jsonb, NOW())
        """,
        agent_id,
        dumps(
            {
                "schema_version": "onboarding_readiness.v1",
                "seed": E2E_MARKER,
                "status": "warning",
                "checks": [
                    {"id": "provider", "status": "passed", "message": "Fake provider configured."},
                    {"id": "runtime", "status": "passed", "message": "Runtime API reachable."},
                    {"id": "channel", "status": "warning", "message": "Telegram gateway has pending senders."},
                    {"id": "first_trace", "status": "passed", "message": "Seeded RunGraph available."},
                ],
            }
        ),
    )


async def apply_seed(dsn: str, schema: str, *, agent_id: str, clear_only: bool) -> None:
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        async with conn.transaction():
            await clear_e2e_data(conn, schema, agent_id)
            if clear_only:
                return
            parent_task_id = await ensure_parent_task(conn, schema, agent_id)
            child_task_id = await seed_child_task(conn, schema, agent_id, parent_task_id)
            await seed_run_graph(conn, schema, agent_id, parent_task_id)
            await seed_child_runs(conn, schema, agent_id, parent_task_id, child_task_id)
            await seed_skill_package(conn, schema, agent_id)
            await seed_evals(conn, schema, agent_id, parent_task_id)
            await seed_channel_and_readiness(conn, schema, agent_id)
    finally:
        await conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed or clear deterministic Koda E2E data.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Apply the E2E data seed.")
    mode.add_argument("--clear", action="store_true", help="Remove only E2E-seeded data.")
    mode.add_argument("--dry-run", action="store_true", help="Print what would happen without touching the database.")
    parser.add_argument("--env-file", type=Path, default=None, help="Path to an environment file.")
    parser.add_argument("--dsn", default="", help="Postgres DSN. Defaults to KNOWLEDGE_V2_POSTGRES_DSN.")
    parser.add_argument("--schema", default="", help="Postgres schema. Defaults to KNOWLEDGE_V2_POSTGRES_SCHEMA.")
    parser.add_argument("--agent-id", default=DEFAULT_AGENT_ID, help="Seed target agent id.")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    load_environment(args.env_file)
    import os

    schema = args.schema or os.environ.get("KNOWLEDGE_V2_POSTGRES_SCHEMA", "knowledge_v2")
    quote_identifier(schema)
    agent_id = str(args.agent_id or DEFAULT_AGENT_ID).upper()
    if args.dry_run or (not args.apply and not args.clear):
        print(f"E2E marker: {E2E_MARKER}")
        print(f"Schema: {schema}")
        print(f"Agent: {agent_id}")
        print("No database changes were made.")
        return 0
    dsn = args.dsn or os.environ.get("KNOWLEDGE_V2_POSTGRES_DSN", "")
    if not dsn:
        raise RuntimeError("KNOWLEDGE_V2_POSTGRES_DSN is required. Run inside the app container or pass --dsn.")
    await apply_seed(dsn, schema, agent_id=agent_id, clear_only=bool(args.clear))
    print(f"Koda E2E data {'cleared' if args.clear else 'seeded'} for {agent_id} in schema {schema}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
