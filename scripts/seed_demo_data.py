#!/usr/bin/env python3
"""Seed polished local demo data for Koda documentation screenshots.

The script is intentionally explicit: it never runs during app startup and it
only removes records that carry the docs-demo marker or belong to managed demo
agents. Run it from the app container for the default compose stack:

    docker compose exec app python scripts/seed_demo_data.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

SEED_MARKER = "koda-docs-demo"
DEFAULT_PROFILE = "docs"
DEFAULT_AGENT_PREFIX = "DEMO_"
KODA_AGENT_ID = "KODA"
DEMO_USER_ID = 91_001
DEMO_CHAT_ID = 91_001
SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class DemoAgent:
    suffix: str
    label: str
    color: str
    color_rgb: str
    workspace_id: str
    squad_id: str
    role: str
    provider: str
    model: str

    def agent_id(self, prefix: str) -> str:
        return f"{prefix}{self.suffix}"


@dataclass(frozen=True)
class ClearStatement:
    sql: str
    params: tuple[Any, ...]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_env_file_fallback(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_environment(env_file: Path | None = None) -> None:
    path = env_file or repo_root() / ".env"
    try:
        from dotenv import load_dotenv
    except ModuleNotFoundError:
        load_env_file_fallback(path)
        return
    load_dotenv(path)


def quote_identifier(value: str) -> str:
    if not SCHEMA_RE.match(value):
        raise ValueError(f"Unsafe SQL identifier: {value!r}")
    return f'"{value}"'


def table(schema: str, name: str) -> str:
    return f"{quote_identifier(schema)}.{quote_identifier(name)}"


def dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def iso(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def demo_agents(prefix: str = DEFAULT_AGENT_PREFIX) -> list[dict[str, Any]]:
    rows = [
        DemoAgent(
            suffix="ATLAS",
            label="Atlas",
            color="#4F8A8B",
            color_rgb="79, 138, 139",
            workspace_id="docs-demo-revenue",
            squad_id="docs-demo-revenue-ops",
            role="Revenue operations analyst",
            provider="codex",
            model="gpt-5.2",
        ),
        DemoAgent(
            suffix="HARBOR",
            label="Harbor",
            color="#D17A57",
            color_rgb="209, 122, 87",
            workspace_id="docs-demo-support",
            squad_id="docs-demo-customer-care",
            role="Customer experience coordinator",
            provider="claude",
            model="claude-sonnet-4.5",
        ),
        DemoAgent(
            suffix="SAGE",
            label="Sage",
            color="#7C6A9C",
            color_rgb="124, 106, 156",
            workspace_id="docs-demo-research",
            squad_id="docs-demo-market-intel",
            role="Research synthesis lead",
            provider="codex",
            model="gpt-5.2",
        ),
        DemoAgent(
            suffix="FORGE",
            label="Forge",
            color="#C1A24B",
            color_rgb="193, 162, 75",
            workspace_id="docs-demo-engineering",
            squad_id="docs-demo-platform",
            role="Platform delivery assistant",
            provider="gemini",
            model="gemini-2.5-pro",
        ),
    ]
    return [
        {
            "id": item.agent_id(prefix),
            "label": item.label,
            "color": item.color,
            "color_rgb": item.color_rgb,
            "workspace_id": item.workspace_id,
            "squad_id": item.squad_id,
            "role": item.role,
            "provider": item.provider,
            "model": item.model,
        }
        for item in rows
    ]


def managed_demo_agent_ids(prefix: str = DEFAULT_AGENT_PREFIX) -> list[str]:
    return [str(agent["id"]) for agent in demo_agents(prefix)]


def build_clear_statements(schema: str, *, prefix: str = DEFAULT_AGENT_PREFIX) -> list[ClearStatement]:
    demo_ids = managed_demo_agent_ids(prefix)
    session_like = f"{SEED_MARKER}:%"
    task_scope = f"""
        (
            agent_id = ANY($1::text[])
            OR (
                agent_id = $2
                AND task_id IN (
                    SELECT id FROM {table(schema, "tasks")}
                     WHERE agent_id = $2 AND session_id LIKE $3
                )
            )
        )
    """
    agent_or_session_scope = "agent_id = ANY($1::text[]) OR (agent_id = $2 AND session_id LIKE $3)"
    statements: list[ClearStatement] = []

    for name in (
        "runtime_resource_samples",
        "runtime_artifacts",
        "runtime_browser_sessions",
        "runtime_service_endpoints",
        "runtime_terminals",
        "runtime_loop_cycles",
        "runtime_guardrail_hits",
        "runtime_events",
        "runtime_queue_items",
        "runtime_environments",
        "execution_episodes",
        "audit_events",
        "dead_letter_queue",
    ):
        statements.append(
            ClearStatement(
                f"DELETE FROM {table(schema, name)} WHERE {task_scope}",
                (demo_ids, KODA_AGENT_ID, session_like),
            )
        )

    statements.extend(
        [
            ClearStatement(
                f"""
                DELETE FROM {table(schema, "scheduled_job_runs")}
                 WHERE scheduled_job_id IN (
                       SELECT id FROM {table(schema, "scheduled_jobs")}
                        WHERE agent_id = ANY($1::text[]) OR migration_source LIKE $2
                 )
                """,
                (demo_ids, f"{SEED_MARKER}:%"),
            ),
            ClearStatement(
                f"""
                DELETE FROM {table(schema, "scheduled_jobs")}
                 WHERE agent_id = ANY($1::text[]) OR migration_source LIKE $2
                """,
                (demo_ids, f"{SEED_MARKER}:%"),
            ),
            ClearStatement(
                f"DELETE FROM {table(schema, 'query_history')} WHERE {agent_or_session_scope}",
                (demo_ids, KODA_AGENT_ID, session_like),
            ),
            ClearStatement(
                f"DELETE FROM {table(schema, 'tasks')} WHERE {agent_or_session_scope}",
                (demo_ids, KODA_AGENT_ID, session_like),
            ),
            ClearStatement(
                f"DELETE FROM {table(schema, 'sessions')} WHERE session_id LIKE $1",
                (session_like,),
            ),
            ClearStatement(
                f"DELETE FROM {table(schema, 'provider_session_map')} WHERE canonical_session_id LIKE $1",
                (session_like,),
            ),
            ClearStatement(
                f"DELETE FROM {table(schema, 'memory_recall_audit')} WHERE {agent_or_session_scope}",
                (demo_ids, KODA_AGENT_ID, session_like),
            ),
            ClearStatement(
                f"DELETE FROM {table(schema, 'napkin_log')} WHERE {agent_or_session_scope}",
                (demo_ids, KODA_AGENT_ID, session_like),
            ),
            ClearStatement(
                f"""
                DELETE FROM {table(schema, "memory_quality_counters")}
                 WHERE agent_id = ANY($1::text[])
                    OR (agent_id = $2 AND counter_key = 'active_docs_demo_memories')
                """,
                (demo_ids, KODA_AGENT_ID),
            ),
        ]
    )

    for name in (
        "cp_mcp_discovered_tools",
        "cp_mcp_tool_policies",
        "cp_mcp_agent_connections",
        "cp_agent_connections",
        "cp_knowledge_assets",
        "cp_skill_assets",
        "cp_template_assets",
        "cp_agent_documents",
        "cp_agent_sections",
        "cp_agent_config_versions",
        "cp_apply_operations",
    ):
        statements.append(
            ClearStatement(
                f"DELETE FROM {table(schema, name)} WHERE agent_id = ANY($1::text[])",
                (demo_ids,),
            )
        )

    statements.extend(
        [
            ClearStatement(
                f"DELETE FROM {table(schema, 'cp_workspace_squads')} WHERE id LIKE $1 OR workspace_id LIKE $1",
                ("docs-demo-%",),
            ),
            ClearStatement(
                f"DELETE FROM {table(schema, 'cp_agent_definitions')} WHERE id = ANY($1::text[])",
                (demo_ids,),
            ),
            ClearStatement(
                f"DELETE FROM {table(schema, 'cp_workspaces')} WHERE id LIKE $1 OR id LIKE $2",
                ("docs-demo-%", f"{SEED_MARKER}:%"),
            ),
        ]
    )
    return statements


async def execute(conn: Any, sql: str, *args: Any) -> str:
    return await conn.execute(sql, *args)


async def clear_demo_data(conn: Any, schema: str, *, prefix: str = DEFAULT_AGENT_PREFIX) -> None:
    async with conn.transaction():
        for statement in build_clear_statements(schema, prefix=prefix):
            await execute(conn, statement.sql, *statement.params)


async def seed_control_plane(conn: Any, schema: str, *, prefix: str) -> None:
    now = iso(datetime.now(UTC))
    workspaces = [
        ("docs-demo-revenue", "Revenue Operations", "Pipeline, forecast, and expansion workflows."),
        ("docs-demo-support", "Customer Experience", "Escalation, quality, and knowledge workflows."),
        ("docs-demo-research", "Research Desk", "Market monitoring and synthesis workflows."),
        ("docs-demo-engineering", "Platform Delivery", "Release, reliability, and runtime workflows."),
    ]
    squads = [
        ("docs-demo-revenue-ops", "docs-demo-revenue", "Revenue Ops"),
        ("docs-demo-customer-care", "docs-demo-support", "Customer Care"),
        ("docs-demo-market-intel", "docs-demo-research", "Market Intelligence"),
        ("docs-demo-platform", "docs-demo-engineering", "Platform"),
    ]
    for workspace_id, name, description in workspaces:
        await execute(
            conn,
            f"""
            INSERT INTO {table(schema, "cp_workspaces")}
                (id, name, description, spec_json, documents_json, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $6)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                spec_json = EXCLUDED.spec_json,
                documents_json = EXCLUDED.documents_json,
                updated_at = EXCLUDED.updated_at
            """,
            workspace_id,
            name,
            description,
            dumps({"seed": SEED_MARKER, "profile": DEFAULT_PROFILE}),
            dumps({"overview": f"{name} demo workspace for Koda documentation."}),
            now,
        )

    for squad_id, workspace_id, name in squads:
        await execute(
            conn,
            f"""
            INSERT INTO {table(schema, "cp_workspace_squads")}
                (id, workspace_id, name, description, spec_json, documents_json, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $7)
            ON CONFLICT (workspace_id, name) DO UPDATE SET
                description = EXCLUDED.description,
                spec_json = EXCLUDED.spec_json,
                documents_json = EXCLUDED.documents_json,
                updated_at = EXCLUDED.updated_at
            """,
            squad_id,
            workspace_id,
            name,
            "Demo squad seeded for filled documentation screenshots.",
            dumps({"seed": SEED_MARKER}),
            dumps({"charter": f"{name} runs a focused demo operating lane."}),
            now,
        )

    for agent in demo_agents(prefix):
        appearance = {
            "label": agent["label"],
            "color": agent["color"],
            "color_rgb": agent["color_rgb"],
        }
        runtime_endpoint = {
            "health_port": 8080,
            "health_url": "http://127.0.0.1:8080/health",
            "runtime_base_url": "http://127.0.0.1:8080",
        }
        metadata = {
            "seed": SEED_MARKER,
            "profile": DEFAULT_PROFILE,
            "summary": f"{agent['label']} is a polished local demo agent.",
        }
        await execute(
            conn,
            f"""
            INSERT INTO {table(schema, "cp_agent_definitions")}
                (id, display_name, status, appearance_json, storage_namespace, runtime_endpoint_json,
                 applied_version, desired_version, metadata_json, workspace_id, squad_id, created_at, updated_at)
            VALUES ($1, $2, 'paused', $3, $4, $5, 1, 1, $6, $7, $8, $9, $9)
            ON CONFLICT (id) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                status = EXCLUDED.status,
                appearance_json = EXCLUDED.appearance_json,
                storage_namespace = EXCLUDED.storage_namespace,
                runtime_endpoint_json = EXCLUDED.runtime_endpoint_json,
                applied_version = EXCLUDED.applied_version,
                desired_version = EXCLUDED.desired_version,
                metadata_json = EXCLUDED.metadata_json,
                workspace_id = EXCLUDED.workspace_id,
                squad_id = EXCLUDED.squad_id,
                updated_at = EXCLUDED.updated_at
            """,
            agent["id"],
            agent["label"],
            dumps(appearance),
            f"{SEED_MARKER}/{agent['id'].lower()}",
            dumps(runtime_endpoint),
            dumps(metadata),
            agent["workspace_id"],
            agent["squad_id"],
            now,
        )
        await seed_agent_sections(conn, schema, agent, now)


async def seed_agent_sections(conn: Any, schema: str, agent: dict[str, Any], now: str) -> None:
    sections = {
        "general": {
            "description": f"{agent['role']} for the docs demo dataset.",
            "seed": SEED_MARKER,
        },
        "appearance": {
            "label": agent["label"],
            "color": agent["color"],
            "color_rgb": agent["color_rgb"],
        },
        "providers": {
            "provider": agent["provider"],
            "model": agent["model"],
            "fallbacks": ["codex", "claude"],
        },
        "tools": {
            "allowed_tool_ids": ["shell.read", "web.search", "memory.recall", "artifact.inspect"],
            "approval_mode": "ask_for_writes",
        },
        "runtime": {
            "autonomy_tier": "supervised",
            "environment_kind": "ephemeral",
        },
        "memory": {
            "enabled": True,
            "review_required": True,
        },
        "knowledge": {
            "enabled": True,
            "sources": ["workspace notes", "runbooks", "customer summaries"],
        },
        "scheduler": {
            "enabled": True,
            "default_timezone": "America/Sao_Paulo",
        },
    }
    for section, payload in sections.items():
        await execute(
            conn,
            f"""
            INSERT INTO {table(schema, "cp_agent_sections")} (agent_id, section, data_json, updated_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (agent_id, section) DO UPDATE SET
                data_json = EXCLUDED.data_json,
                updated_at = EXCLUDED.updated_at
            """,
            agent["id"],
            section,
            dumps(payload),
            now,
        )

    documents = {
        "identity_md": f"# {agent['label']}\n\nA demo {agent['role'].lower()} used to showcase Koda screens.",
        "instructions_md": "Operate with concise plans, cite the source of operational facts, and ask before writes.",
        "rules_md": "- Never expose secrets.\n- Keep actions reversible.\n- Summarize cost and risk before execution.",
        "system_prompt_md": f"You are {agent['label']}, a Koda demo agent focused on professional operations.",
    }
    for kind, content in documents.items():
        await execute(
            conn,
            f"""
            INSERT INTO {table(schema, "cp_agent_documents")} (agent_id, kind, content_md, updated_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (agent_id, kind) DO UPDATE SET
                content_md = EXCLUDED.content_md,
                updated_at = EXCLUDED.updated_at
            """,
            agent["id"],
            kind,
            content,
            now,
        )

    await execute(
        conn,
        f"""
        INSERT INTO {table(schema, "cp_agent_config_versions")}
            (agent_id, version, snapshot_json, status, summary, created_at, published_at)
        VALUES ($1, 1, $2, 'published', $3, $4, $4)
        ON CONFLICT (agent_id, version) DO UPDATE SET
            snapshot_json = EXCLUDED.snapshot_json,
            status = EXCLUDED.status,
            summary = EXCLUDED.summary,
            published_at = EXCLUDED.published_at
        """,
        agent["id"],
        dumps({"seed": SEED_MARKER, "sections": list(sections)}),
        "Seeded docs-demo configuration.",
        now,
    )
    await execute(
        conn,
        f"""
        INSERT INTO {table(schema, "cp_knowledge_assets")}
            (scope_id, agent_id, asset_key, title, kind, content_text, body_json, enabled, created_at, updated_at)
        VALUES ($1, $2, $3, $4, 'entry', $5, $6, 1, $7, $7)
        ON CONFLICT (scope_id, asset_key) DO UPDATE SET
            title = EXCLUDED.title,
            content_text = EXCLUDED.content_text,
            body_json = EXCLUDED.body_json,
            enabled = EXCLUDED.enabled,
            updated_at = EXCLUDED.updated_at
        """,
        f"agent:{agent['id']}",
        agent["id"],
        f"{SEED_MARKER}-operating-brief",
        "Operating brief",
        f"{agent['label']} tracks current goals, open risks, and weekly business outcomes.",
        dumps({"seed": SEED_MARKER, "type": "brief"}),
        now,
    )


def query_templates(agent_id: str) -> list[str]:
    if agent_id == KODA_AGENT_ID:
        return [
            "Review platform health and summarize runtime readiness for the operator standup",
            "Prepare a concise cost and activity digest for the Koda dashboard",
            "Check the latest execution failures and propose safe recovery actions",
            "Draft documentation notes for the new local demo workflow",
        ]
    if agent_id.endswith("ATLAS"):
        return [
            "Summarize pipeline movement and flag accounts with renewal risk",
            "Prepare the Monday revenue forecast brief with source links",
            "Compare expansion opportunities against customer-health notes",
            "Create a sales leadership digest for open enterprise deals",
        ]
    if agent_id.endswith("HARBOR"):
        return [
            "Group support escalations by root cause and recommend next actions",
            "Draft a customer-facing incident update for the premium queue",
            "Review quality tags and identify coaching opportunities",
            "Summarize customer sentiment from the latest support threads",
        ]
    if agent_id.endswith("SAGE"):
        return [
            "Research competitor launch notes and extract pricing changes",
            "Create a market intelligence memo for the weekly planning review",
            "Summarize analyst coverage and cite the strongest signals",
            "Compare product positioning themes across the research archive",
        ]
    return [
        "Review release checklist progress and highlight deployment blockers",
        "Summarize CI failures and recommend owner-friendly fixes",
        "Prepare an engineering delivery update with risk notes",
        "Check runtime guardrail events for the latest platform tasks",
    ]


def response_for(query: str) -> str:
    return (
        "Prepared a concise operator-ready summary with source notes, next actions, "
        f"and a risk rating for: {query[:96]}."
    )


def session_name_for(agent_id: str) -> str:
    if agent_id == KODA_AGENT_ID:
        return "Koda operations review"
    suffix = agent_id.split("_", maxsplit=1)[-1].replace("-", " ").title()
    return f"{suffix} weekly operating room"


async def seed_task_bundle(
    conn: Any,
    schema: str,
    *,
    agent_id: str,
    query: str,
    session_id: str,
    created_at: datetime,
    status: str,
    provider: str,
    model: str,
    cost_usd: float,
    index: int,
) -> int:
    started_at = created_at + timedelta(minutes=1)
    completed_at = (
        None if status in {"queued", "running", "retrying"} else started_at + timedelta(minutes=4 + index % 5)
    )
    phase = "finalized" if status == "completed" else "investigating" if status == "running" else status
    work_dir = f"/var/lib/koda/runtime/workspaces/{SEED_MARKER}/{agent_id.lower()}/{index}"
    await execute(
        conn,
        f"""
        INSERT INTO {table(schema, "sessions")} AS existing
            (agent_id, user_id, session_id, name, provider, provider_session_id, last_model, created_at, last_used)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        ON CONFLICT (user_id, session_id) DO UPDATE SET
            agent_id = EXCLUDED.agent_id,
            name = EXCLUDED.name,
            provider = EXCLUDED.provider,
            provider_session_id = EXCLUDED.provider_session_id,
            last_model = EXCLUDED.last_model,
            last_used = GREATEST(existing.last_used, EXCLUDED.last_used)
        """,
        agent_id,
        DEMO_USER_ID,
        session_id,
        session_name_for(agent_id),
        provider,
        f"provider-{session_id}",
        model,
        iso(created_at),
        iso(created_at),
    )
    task_id = await conn.fetchval(
        f"""
        INSERT INTO {table(schema, "tasks")}
            (agent_id, user_id, chat_id, status, query_text, provider, model, work_dir, attempt, max_attempts,
             cost_usd, error_message, created_at, started_at, completed_at, session_id, provider_session_id,
             classification, environment_kind, current_phase, last_heartbeat_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 1, 3, $9, $10, $11, $12, $13, $14, $15,
                'operator_task', 'ephemeral', $16, $17)
        RETURNING id
        """,
        agent_id,
        DEMO_USER_ID,
        DEMO_CHAT_ID,
        status,
        query,
        provider,
        model,
        work_dir,
        cost_usd,
        "Connector rate limit recovered by retry policy" if status == "failed" else None,
        iso(created_at),
        iso(started_at) if status != "queued" else None,
        iso(completed_at) if completed_at else None,
        session_id,
        f"provider-{session_id}",
        phase,
        iso(datetime.now(UTC) - timedelta(minutes=index)),
    )
    if task_id is None:
        raise RuntimeError("task insert did not return an id")
    response_text = response_for(query)
    await execute(
        conn,
        f"""
        INSERT INTO {table(schema, "query_history")}
            (agent_id, user_id, timestamp, query_text, response_text, cost_usd, provider, model,
             session_id, provider_session_id, usage_json, work_dir, error)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12, $13)
        """,
        agent_id,
        DEMO_USER_ID,
        created_at,
        query,
        response_text,
        cost_usd,
        provider,
        model,
        session_id,
        f"provider-{session_id}",
        dumps({"input_tokens": 1800 + index * 12, "output_tokens": 420 + index * 7, "seed": SEED_MARKER}),
        work_dir,
        status == "failed",
    )
    await seed_runtime_projection(
        conn,
        schema,
        agent_id=agent_id,
        task_id=int(task_id),
        query=query,
        status=status,
        phase=phase,
        created_at=created_at,
        started_at=started_at,
        completed_at=completed_at,
        work_dir=work_dir,
        index=index,
    )
    await seed_execution_trace(
        conn,
        schema,
        agent_id=agent_id,
        task_id=int(task_id),
        query=query,
        status=status,
        model=model,
        cost_usd=cost_usd,
        created_at=created_at,
        completed_at=completed_at or started_at,
        index=index,
    )
    return int(task_id)


async def seed_runtime_projection(
    conn: Any,
    schema: str,
    *,
    agent_id: str,
    task_id: int,
    query: str,
    status: str,
    phase: str,
    created_at: datetime,
    started_at: datetime,
    completed_at: datetime | None,
    work_dir: str,
    index: int,
) -> None:
    env_status = "active" if status in {"running", "retrying"} else "retained" if status == "completed" else status
    updated_at = completed_at or started_at
    env_id = await conn.fetchval(
        f"""
        INSERT INTO {table(schema, "runtime_environments")}
            (agent_id, task_id, user_id, chat_id, classification, environment_kind, isolation, duration,
             status, current_phase, workspace_path, runtime_dir, base_work_dir, branch_name, created_worktree,
             worktree_mode, is_pinned, checkpoint_status, checkpoint_path, recovery_state, revision,
             browser_transport, display_id, vnc_port, novnc_port, pause_state, pause_reason, process_pid,
             process_pgid, created_at, updated_at, last_heartbeat_at)
        VALUES ($1, $2, $3, $4, 'operator_task', 'ephemeral', 'process', 'short',
                $5, $6, $7, $8, $9, $10, TRUE, 'isolated', $11, $12, $13, '', 1,
                $14, $15, $16, $17, 'none', '', NULL, NULL, $18, $19, $19)
        RETURNING id
        """,
        agent_id,
        task_id,
        DEMO_USER_ID,
        DEMO_CHAT_ID,
        env_status,
        phase,
        work_dir,
        f"/var/lib/koda/runtime/tasks/{task_id}",
        "/workspace",
        f"docs-demo/{agent_id.lower()}-{task_id}",
        index % 7 == 0,
        "completed" if status == "completed" else "pending",
        f"{work_dir}/checkpoint.json" if status == "completed" else None,
        "novnc" if index % 9 == 0 else "",
        90 + index if index % 9 == 0 else None,
        5900 + index if index % 9 == 0 else None,
        6080 + index if index % 9 == 0 else None,
        iso(created_at),
        iso(updated_at),
    )
    await execute(
        conn,
        f"""
        INSERT INTO {table(schema, "runtime_queue_items")}
            (agent_id, task_id, user_id, chat_id, queue_name, status, queue_position, query_text,
             queued_at, updated_at, payload_json, recovery_count, source_kind, last_error)
        VALUES ($1, $2, $3, $4, 'user', $5, $6, $7, $8, $9, $10, $11, 'demo', $12)
        """,
        agent_id,
        task_id,
        DEMO_USER_ID,
        DEMO_CHAT_ID,
        status,
        index % 4 if status == "queued" else None,
        query,
        iso(created_at),
        iso(updated_at),
        dumps({"seed": SEED_MARKER, "source": "docs-demo"}),
        1 if status == "retrying" else 0,
        "Connector rate limit recovered by retry policy" if status == "failed" else None,
    )
    event_payloads = [
        ("task.created", "info", "Task accepted from the operator dashboard."),
        ("context.ready", "info", "Memory and knowledge context were attached."),
        (
            "provider.completed" if status == "completed" else f"task.{status}",
            "error" if status == "failed" else "info",
            query,
        ),
    ]
    for offset, (event_type, severity, message) in enumerate(event_payloads):
        await execute(
            conn,
            f"""
            INSERT INTO {table(schema, "runtime_events")}
                (agent_id, task_id, env_id, attempt, phase, event_type, severity, payload_json,
                 artifact_refs_json, created_at)
            VALUES ($1, $2, $3, 1, $4, $5, $6, $7::jsonb, $8::jsonb, $9)
            """,
            agent_id,
            task_id,
            env_id,
            phase,
            event_type,
            severity,
            dumps({"message": message, "seed": SEED_MARKER}),
            dumps([]),
            iso(created_at + timedelta(minutes=offset)),
        )
    await execute(
        conn,
        f"""
        INSERT INTO {table(schema, "runtime_artifacts")}
            (agent_id, task_id, env_id, artifact_kind, label, path, metadata_json, created_at)
        VALUES ($1, $2, $3, 'report', 'Operator brief', $4, $5::jsonb, $6)
        """,
        agent_id,
        task_id,
        env_id,
        f"{work_dir}/operator-brief.md",
        dumps({"seed": SEED_MARKER, "format": "markdown"}),
        iso(created_at + timedelta(minutes=3)),
    )
    await execute(
        conn,
        f"""
        INSERT INTO {table(schema, "runtime_resource_samples")}
            (agent_id, task_id, env_id, cpu_percent, rss_kb, process_count, workspace_disk_bytes,
             metadata_json, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9)
        """,
        agent_id,
        task_id,
        env_id,
        9.5 + (index % 8) * 2.1,
        120_000 + index * 3200,
        3 + index % 4,
        4_000_000 + index * 17_000,
        dumps({"seed": SEED_MARKER}),
        iso(started_at + timedelta(minutes=2)),
    )


async def seed_execution_trace(
    conn: Any,
    schema: str,
    *,
    agent_id: str,
    task_id: int,
    query: str,
    status: str,
    model: str,
    cost_usd: float,
    created_at: datetime,
    completed_at: datetime,
    index: int,
) -> None:
    details = {
        "runtime": {
            "stop_reason": "completed" if status == "completed" else status,
            "warnings": [] if status != "failed" else ["Upstream connector returned a transient timeout."],
            "reasoning_summary": [
                "Loaded scoped memory and source notes.",
                "Prepared a concise operator response.",
            ],
        },
        "assistant": {"response_text": response_for(query)},
        "tools": [
            {
                "tool": "memory.recall",
                "category": "context",
                "success": True,
                "duration_ms": 340 + index,
                "summary": "Fetched relevant operating notes.",
            },
            {
                "tool": "artifact.write",
                "category": "artifact",
                "success": status == "completed",
                "duration_ms": 820 + index * 2,
                "summary": "Prepared the operator brief artifact.",
            },
        ],
        "timeline": [
            {"type": "queued", "title": "Queued", "status": "info", "timestamp": iso(created_at)},
            {
                "type": "context",
                "title": "Context attached",
                "status": "success",
                "timestamp": iso(created_at + timedelta(minutes=1)),
            },
            {
                "type": status,
                "title": status.title(),
                "status": "success" if status == "completed" else status,
                "timestamp": iso(completed_at),
            },
        ],
    }
    await execute(
        conn,
        f"""
        INSERT INTO {table(schema, "audit_events")}
            (agent_id, timestamp, event_type, pod_name, user_id, task_id, trace_id, details_json,
             cost_usd, duration_ms)
        VALUES ($1, $2, 'task.execution_trace', 'docs-demo', $3, $4, $5, $6::jsonb, $7, $8)
        """,
        agent_id,
        completed_at,
        DEMO_USER_ID,
        task_id,
        f"{SEED_MARKER}-{agent_id}-{task_id}",
        dumps(details),
        cost_usd,
        max((completed_at - created_at).total_seconds() * 1000, 0),
    )
    await execute(
        conn,
        f"""
        INSERT INTO {table(schema, "execution_episodes")}
            (agent_id, task_id, user_id, task_kind, project_key, environment, team, autonomy_tier,
             approval_mode, status, confidence_score, verified_before_finalize, plan_json,
             source_refs_json, tool_trace_json, feedback_status, retrieval_strategy, grounding_score,
             citation_coverage, winning_sources_json, answer_citation_coverage, answer_gate_status,
             answer_gate_reasons_json, created_at)
        VALUES ($1, $2, $3, 'operator_digest', 'docs-demo', 'local', 'operations', 'supervised',
                'ask_for_writes', $4, $5, TRUE, $6::jsonb, $7::jsonb, $8::jsonb, $9,
                'hybrid_dense', $10, $11, $12::jsonb, $13, 'passed', $14::jsonb, $15)
        """,
        agent_id,
        task_id,
        DEMO_USER_ID,
        "succeeded" if status == "completed" else status,
        0.82 + (index % 10) / 100,
        dumps({"steps": ["Read context", "Check recent activity", "Draft response"], "seed": SEED_MARKER}),
        dumps(["operating-brief.md", "weekly-kpis.csv"]),
        dumps(details["tools"]),
        "promote" if status == "completed" and index % 5 == 0 else "pending",
        0.78 + (index % 8) / 100,
        0.74 + (index % 9) / 100,
        dumps(["Operating brief", "Recent dashboard activity"]),
        0.81 + (index % 7) / 100,
        dumps([]),
        iso(completed_at),
    )


async def seed_operational_data(conn: Any, schema: str, *, prefix: str) -> None:
    existing_koda = await conn.fetchval(
        f"SELECT 1 FROM {table(schema, 'cp_agent_definitions')} WHERE id = $1",
        KODA_AGENT_ID,
    )
    operational_agents = ([KODA_AGENT_ID] if existing_koda else []) + managed_demo_agent_ids(prefix)
    agent_meta = {agent["id"]: (agent["provider"], agent["model"]) for agent in demo_agents(prefix)}
    agent_meta[KODA_AGENT_ID] = ("codex", "gpt-5.2")
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    task_index = 0
    first_task_for_agent: dict[str, int] = {}

    for day_offset in range(0, 42):
        for agent_index, agent_id in enumerate(operational_agents):
            if (day_offset + agent_index) % 3 != 0:
                continue
            templates = query_templates(agent_id)
            query = templates[(day_offset + agent_index) % len(templates)]
            created_at = now - timedelta(days=day_offset, hours=agent_index + 1)
            session_id = f"{SEED_MARKER}:{agent_id}:{day_offset // 7}"
            if day_offset == 0 and agent_index == 0:
                status = "running"
            elif (day_offset + agent_index) % 17 == 0:
                status = "queued"
            elif (day_offset + agent_index) % 11 == 0:
                status = "failed"
            else:
                status = "completed"
            provider, model = agent_meta.get(agent_id, ("codex", "gpt-5.2"))
            cost_usd = round(0.035 + ((day_offset + agent_index) % 9) * 0.014, 4)
            task_id = await seed_task_bundle(
                conn,
                schema,
                agent_id=agent_id,
                query=query,
                session_id=session_id,
                created_at=created_at,
                status=status,
                provider=provider,
                model=model,
                cost_usd=cost_usd,
                index=task_index,
            )
            first_task_for_agent.setdefault(agent_id, task_id)
            task_index += 1

    await seed_schedules_and_memory(conn, schema, operational_agents, first_task_for_agent, now)


async def seed_schedules_and_memory(
    conn: Any,
    schema: str,
    agent_ids: list[str],
    first_task_for_agent: dict[str, int],
    now: datetime,
) -> None:
    for index, agent_id in enumerate(agent_ids):
        job_id = await conn.fetchval(
            f"""
            INSERT INTO {table(schema, "scheduled_jobs")}
                (user_id, chat_id, agent_id, job_type, trigger_type, schedule_expr, timezone,
                 payload_json, status, safety_mode, dry_run_required, verification_policy_json,
                 notification_policy_json, provider_preference, model_preference, work_dir,
                 next_run_at, last_run_at, last_success_at, migration_source, created_at, updated_at,
                 policy_snapshot_json, policy_snapshot_hash, config_version)
            VALUES ($1, $2, $3, 'agent_query', 'cron', $4, 'America/Sao_Paulo', $5, 'active',
                    'dry_run_required', 1, $6, $7, 'codex', 'gpt-5.2', $8, $9, $10, $10, $11, $12, $12,
                    $13, $14, 1)
            ON CONFLICT (migration_source) DO UPDATE SET
                payload_json = EXCLUDED.payload_json,
                status = EXCLUDED.status,
                next_run_at = EXCLUDED.next_run_at,
                last_run_at = EXCLUDED.last_run_at,
                last_success_at = EXCLUDED.last_success_at,
                updated_at = EXCLUDED.updated_at
            RETURNING id
            """,
            DEMO_USER_ID,
            DEMO_CHAT_ID,
            agent_id,
            "0 9 * * MON-FRI",
            dumps(
                {
                    "query": "Prepare the morning operating digest.",
                    "description": "Daily operator brief",
                    "seed": SEED_MARKER,
                }
            ),
            dumps({"approval": "manual_review"}),
            dumps({"channels": ["dashboard"]}),
            f"/var/lib/koda/runtime/workspaces/{SEED_MARKER}/{agent_id.lower()}",
            iso(now + timedelta(days=1, hours=9)),
            iso(now - timedelta(days=1, hours=9)),
            f"{SEED_MARKER}:{agent_id}:morning-digest",
            iso(now - timedelta(days=10)),
            dumps({"seed": SEED_MARKER}),
            f"{SEED_MARKER}:{agent_id}",
        )
        if job_id is not None:
            await execute(
                conn,
                f"""
                INSERT INTO {table(schema, "scheduled_job_runs")}
                    (scheduled_job_id, scheduled_for, trigger_reason, status, attempt, max_attempts,
                     task_id, provider_effective, model_effective, verification_status,
                     notification_status, summary_text, metadata_json, started_at, completed_at,
                     duration_ms, created_at, updated_at, trace_id)
                VALUES ($1, $2, 'normal', 'succeeded', 1, 3, $3, 'codex', 'gpt-5.2', 'passed',
                        'sent', $4, $5, $6, $7, 184000, $6, $7, $8)
                ON CONFLICT (scheduled_job_id, scheduled_for, trigger_reason) DO NOTHING
                """,
                int(job_id),
                iso(now - timedelta(days=1, hours=9)),
                first_task_for_agent.get(agent_id),
                "Morning digest completed with no required escalation.",
                dumps({"seed": SEED_MARKER}),
                iso(now - timedelta(days=1, hours=9)),
                iso(now - timedelta(days=1, hours=8, minutes=56)),
                f"{SEED_MARKER}-{agent_id}-schedule",
            )

        if index % 2 == 0 and first_task_for_agent.get(agent_id):
            await execute(
                conn,
                f"""
                INSERT INTO {table(schema, "dead_letter_queue")}
                    (task_id, user_id, chat_id, agent_id, pod_name, query_text, model, error_message,
                     error_class, attempt_count, original_created_at, failed_at, retry_eligible, metadata_json)
                VALUES ($1, $2, $3, $4, 'docs-demo', $5, 'gpt-5.2', $6, 'TransientProviderError',
                        2, $7, $8, 1, $9)
                """,
                first_task_for_agent[agent_id],
                DEMO_USER_ID,
                DEMO_CHAT_ID,
                agent_id,
                "Retry the morning digest after connector throttling",
                "Connector throttled the final artifact upload.",
                iso(now - timedelta(days=2, hours=index)),
                iso(now - timedelta(days=2, hours=index, minutes=-7)),
                dumps({"seed": SEED_MARKER, "retry_hint": "safe"}),
            )

        for memory_index, content in enumerate(
            [
                "The operator prefers short summaries with cost and risk called out first.",
                "Weekly planning reviews need customer impact, owner, and next checkpoint.",
                "Screenshots for public docs must avoid real credentials and private customer names.",
            ]
        ):
            await execute(
                conn,
                f"""
                INSERT INTO {table(schema, "napkin_log")}
                    (user_id, memory_type, content, session_id, agent_id, origin_kind, source_task_id,
                     project_key, environment, team, importance, quality_score, extraction_confidence,
                     embedding_status, content_hash, claim_kind, subject, decision_source,
                     evidence_refs_json, applicability_scope_json, memory_status, retention_reason,
                     access_count, last_accessed, last_recalled_at, created_at, is_active, metadata_json)
                VALUES ($1, 'preference', $2, $3, $4, 'conversation', $5, 'docs-demo', 'local',
                        'operations', $6, 0.88, 0.91, 'ready', $7, 'operator_preference', $8,
                        'demo_seed', $9, $10, 'active', 'docs-demo', $11, $12, $12, $13, 1, $14)
                """,
                DEMO_USER_ID,
                content,
                f"{SEED_MARKER}:{agent_id}:{memory_index}",
                agent_id,
                first_task_for_agent.get(agent_id),
                0.72 + memory_index / 10,
                f"{SEED_MARKER}:{agent_id}:{memory_index}",
                "documentation",
                dumps(["operator-brief.md"]),
                dumps({"workspace": "docs-demo"}),
                3 + memory_index,
                iso(now - timedelta(days=memory_index + 1)),
                iso(now - timedelta(days=memory_index + 4)),
                dumps({"seed": SEED_MARKER}),
            )
        await execute(
            conn,
            f"""
            INSERT INTO {table(schema, "memory_quality_counters")}
                (agent_id, counter_key, counter_value, updated_at)
            VALUES ($1, 'active_docs_demo_memories', 3, $2)
            ON CONFLICT (agent_id, counter_key) DO UPDATE SET
                counter_value = EXCLUDED.counter_value,
                updated_at = EXCLUDED.updated_at
            """,
            agent_id,
            iso(now),
        )


async def apply_seed(dsn: str, schema: str, *, prefix: str, clear_only: bool) -> None:
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        async with conn.transaction():
            await clear_demo_data(conn, schema, prefix=prefix)
            if clear_only:
                return
            await seed_control_plane(conn, schema, prefix=prefix)
            await seed_operational_data(conn, schema, prefix=prefix)
    finally:
        await conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed or clear Koda documentation demo data.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Apply the docs demo data seed.")
    mode.add_argument("--clear", action="store_true", help="Remove only docs demo data.")
    mode.add_argument("--dry-run", action="store_true", help="Print what would happen without touching the database.")
    parser.add_argument("--profile", default=DEFAULT_PROFILE, choices=[DEFAULT_PROFILE], help="Demo profile to seed.")
    parser.add_argument("--agent-prefix", default=DEFAULT_AGENT_PREFIX, help="Prefix used for managed demo agents.")
    parser.add_argument("--env-file", type=Path, default=None, help="Path to the environment file to load.")
    parser.add_argument("--dsn", default="", help="Postgres DSN. Defaults to KNOWLEDGE_V2_POSTGRES_DSN.")
    parser.add_argument("--schema", default="", help="Postgres schema. Defaults to KNOWLEDGE_V2_POSTGRES_SCHEMA.")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    load_environment(args.env_file)
    schema = args.schema or os.environ.get("KNOWLEDGE_V2_POSTGRES_SCHEMA", "knowledge_v2")
    quote_identifier(schema)
    prefix = str(args.agent_prefix or DEFAULT_AGENT_PREFIX)

    if args.dry_run or (not args.apply and not args.clear):
        print(f"Demo marker: {SEED_MARKER}")
        print(f"Schema: {schema}")
        print(f"Managed demo agents: {', '.join(managed_demo_agent_ids(prefix))}")
        print(f"Clear statements: {len(build_clear_statements(schema, prefix=prefix))}")
        print("No database changes were made.")
        return 0

    dsn = args.dsn or os.environ.get("KNOWLEDGE_V2_POSTGRES_DSN", "")
    if not dsn:
        raise RuntimeError("KNOWLEDGE_V2_POSTGRES_DSN is required. Run inside the app container or pass --dsn.")

    await apply_seed(dsn, schema, prefix=prefix, clear_only=bool(args.clear))
    action = "cleared" if args.clear else "seeded"
    print(f"Koda docs demo data {action} in schema {schema}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
