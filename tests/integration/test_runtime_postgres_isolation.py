"""Integration tests for koda.services.runtime.postgres_store against a real
PostgreSQL container.

Pinned guarantees:

  * agent_id scoping: rows inserted by one agent are NOT visible to another.
  * create_environment writes a runtime_environments row AND updates tasks.env_id.
  * add_event assigns monotonic per-task seq numbers visible via list_events.
  * Port allocations are scoped per agent (`agent_id, host, port` uniqueness).
  * Listing endpoints return only rows from the configured agent scope.

The test patches ``AGENT_ID`` to switch between two agents in the same Postgres
schema, then verifies queries do NOT cross the boundary. This is the highest
risk gap in the runtime explore report.
"""

from __future__ import annotations

import importlib
from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import pytest

from koda.knowledge.v2.common import get_shared_postgres_backend

pytestmark = [pytest.mark.postgres]


@pytest.fixture
async def runtime_db(migrated_postgres: str, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[str]:
    """Yield the migrated DSN with runtime tables truncated and config reloaded.

    The migrated_postgres fixture sets KNOWLEDGE_V2_POSTGRES_DSN in os.environ,
    but the constant inside koda.knowledge.config was captured at import time
    against an empty string. We reload the relevant modules so subsequent
    backend lookups see the test DSN.

    We also extend the asyncpg codec installer to register a JSONB codec
    that round-trips Python dict/list — required because runtime_events
    and runtime_port_allocations use JSONB columns and the default codec
    rejects Python objects.
    """
    # Reload configs that captured env at import time.
    import koda.knowledge.config as kn_config

    importlib.reload(kn_config)

    # Clear shared backend cache so reload takes effect.
    from koda.knowledge.v2 import common as common_mod

    if hasattr(common_mod, "_SHARED_BACKENDS"):
        common_mod._SHARED_BACKENDS.clear()  # type: ignore[attr-defined]

    # Install a JSONB codec for the test session. The runtime store passes
    # already-redacted JSON *strings* into JSONB columns — asyncpg's default
    # codec rejects this. We register a codec that accepts strings (passed
    # through verbatim) AND Python dict/list (json.dumps'd).
    import contextlib
    import json as _json

    from koda.state import primary as primary_mod

    original_install = primary_mod._install_timestamptz_str_codec

    async def _install_codecs(conn: Any) -> None:
        await original_install(conn)
        with contextlib.suppress(Exception):
            await conn.set_type_codec(
                "jsonb",
                encoder=lambda v: v if isinstance(v, str) else _json.dumps(v, default=str),
                decoder=lambda v: _json.loads(v) if v else None,
                schema="pg_catalog",
                format="text",
            )

    monkeypatch.setattr(primary_mod, "_install_timestamptz_str_codec", _install_codecs)

    # Reset runtime tables to a clean slate (session-scoped schema is shared).
    conn = await asyncpg.connect(migrated_postgres)
    try:
        for table in (
            "runtime_port_allocations",
            "runtime_events",
            "runtime_environments",
            "runtime_queue_items",
            "tasks",
        ):
            await conn.execute(f'TRUNCATE TABLE knowledge_v2."{table}" RESTART IDENTITY CASCADE')
    finally:
        await conn.close()
    try:
        yield migrated_postgres
    finally:
        if hasattr(common_mod, "_SHARED_BACKENDS"):
            common_mod._SHARED_BACKENDS.clear()  # type: ignore[attr-defined]


def _build_store(agent_id: str):
    """Build a fresh PostgresRuntimeStore bound to the given agent_id."""
    import koda.config as config_mod
    config_mod.AGENT_ID = agent_id  # patches the imported constant
    # Reload the postgres_store module so its agent_scope helper re-reads AGENT_ID.
    import koda.services.runtime.postgres_store as ps_mod
    importlib.reload(ps_mod)
    return ps_mod.PostgresRuntimeStore()


async def _seed_task(dsn: str, *, agent_id: str, task_id: int, user_id: int = 100, chat_id: int = 100) -> None:
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(
            """
            INSERT INTO knowledge_v2.tasks
                (id, agent_id, user_id, chat_id, status, query_text, attempt, max_attempts, cost_usd, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            task_id,
            agent_id,
            user_id,
            chat_id,
            "queued",
            f"task {task_id} for {agent_id}",
            1,
            3,
            0.0,
            "2026-05-01T00:00:00+00:00",
        )
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# add_event monotonic seq + cross-agent isolation
# ---------------------------------------------------------------------------


async def test_add_event_assigns_monotonic_seq_within_task(runtime_db: str) -> None:
    backend = get_shared_postgres_backend(
        agent_id="agent_a",
        dsn=runtime_db,
        schema="knowledge_v2",
        embedding_dimension=1024,
    )
    assert backend.enabled

    await _seed_task(runtime_db, agent_id="agent_a", task_id=1)

    store_a = _build_store("agent_a")
    e1 = store_a.add_event(task_id=1, env_id=None, attempt=1, phase="x", severity="info", event_type="t1")
    e2 = store_a.add_event(task_id=1, env_id=None, attempt=1, phase="x", severity="info", event_type="t2")
    e3 = store_a.add_event(task_id=1, env_id=None, attempt=1, phase="x", severity="info", event_type="t3")

    assert int(e1["seq"]) == 1
    assert int(e2["seq"]) == 2
    assert int(e3["seq"]) == 3


async def test_list_events_returns_only_agents_rows(runtime_db: str) -> None:
    """Same task_id literal in two agents → list_events only sees own rows.

    The tasks table has `id BIGSERIAL PRIMARY KEY`, so two agents cannot share
    the same task id at the row level. But runtime_events.task_id is just
    BIGINT (no FK), so each agent_scope can write events tagged with the same
    task_id literal — and list_events must still partition them by agent_id.
    """
    await _seed_task(runtime_db, agent_id="agent_a", task_id=1)
    await _seed_task(runtime_db, agent_id="agent_b", task_id=2)

    # Make sure backends for both agents exist.
    get_shared_postgres_backend(agent_id="agent_a", dsn=runtime_db, schema="knowledge_v2", embedding_dimension=1024)
    get_shared_postgres_backend(agent_id="agent_b", dsn=runtime_db, schema="knowledge_v2", embedding_dimension=1024)

    store_a = _build_store("agent_a")
    store_a.add_event(task_id=1, env_id=None, attempt=1, phase="x", severity="info", event_type="A1")
    store_a.add_event(task_id=1, env_id=None, attempt=1, phase="x", severity="info", event_type="A2")

    store_b = _build_store("agent_b")
    store_b.add_event(task_id=1, env_id=None, attempt=1, phase="x", severity="info", event_type="B1")

    # agent_a sees only A* events.
    a_events = store_a.list_events(task_id=1)
    a_types = sorted(e["type"] for e in a_events)
    assert a_types == ["A1", "A2"], f"agent_a leaked agent_b events: {a_types}"

    # agent_b sees only B* events.
    b_events = store_b.list_events(task_id=1)
    b_types = sorted(e["type"] for e in b_events)
    assert b_types == ["B1"], f"agent_b leaked agent_a events: {b_types}"


async def test_list_events_after_seq_pagination(runtime_db: str) -> None:
    await _seed_task(runtime_db, agent_id="agent_a", task_id=10)
    store = _build_store("agent_a")
    for i in range(5):
        store.add_event(task_id=10, env_id=None, attempt=1, phase="x", severity="info", event_type=f"e{i}")

    all_events = store.list_events(task_id=10)
    assert [e["type"] for e in all_events] == ["e0", "e1", "e2", "e3", "e4"]

    after_2 = store.list_events(task_id=10, after_seq=2)
    assert [e["type"] for e in after_2] == ["e2", "e3", "e4"]


async def test_list_events_empty_when_no_events(runtime_db: str) -> None:
    await _seed_task(runtime_db, agent_id="agent_a", task_id=99)
    store = _build_store("agent_a")
    assert store.list_events(task_id=99) == []


# ---------------------------------------------------------------------------
# create_environment + cross-agent isolation
# ---------------------------------------------------------------------------


async def test_create_environment_writes_row_and_updates_task(runtime_db: str) -> None:
    await _seed_task(runtime_db, agent_id="agent_a", task_id=1)
    store = _build_store("agent_a")
    env_id = store.create_environment(
        task_id=1,
        user_id=100,
        chat_id=100,
        classification="standard",
        environment_kind="dev_worktree",
        isolation="worktree",
        duration="medium",
        workspace_path="/tmp/koda/work/1",
        runtime_dir="/tmp/koda/runtime/1",
        base_work_dir="/tmp/koda/base",
        branch_name="koda/agent_a/1",
        created_worktree=True,
        worktree_mode="auto",
        current_phase="provisioning",
    )
    assert env_id > 0

    # The environment row was written.
    env = store.get_environment(env_id)
    assert env is not None
    assert env["task_id"] == 1
    assert env["classification"] == "standard"
    assert env["status"] == "active"

    # The task's env_id pointer was updated.
    conn = await asyncpg.connect(runtime_db)
    try:
        row = await conn.fetchrow(
            'SELECT env_id, current_phase, classification FROM knowledge_v2.tasks WHERE agent_id = $1 AND id = $2',
            "agent_a", 1,
        )
    finally:
        await conn.close()
    assert row is not None
    assert row["env_id"] == env_id
    assert row["classification"] == "standard"
    assert row["current_phase"] == "provisioning"


async def test_get_environment_returns_none_for_other_agent(runtime_db: str) -> None:
    await _seed_task(runtime_db, agent_id="agent_a", task_id=1)
    store_a = _build_store("agent_a")
    env_id = store_a.create_environment(
        task_id=1,
        user_id=1,
        chat_id=1,
        classification="light",
        environment_kind="dev_worktree",
        isolation="shared",
        duration="short",
        workspace_path="/tmp/work/1",
        runtime_dir="/tmp/rt/1",
        base_work_dir="/tmp/base",
        branch_name=None,
        created_worktree=False,
        worktree_mode="none",
        current_phase="executing",
    )
    # agent_b cannot fetch env_id from agent_a.
    store_b = _build_store("agent_b")
    assert store_b.get_environment(env_id) is None


async def test_list_environments_scoped_per_agent(runtime_db: str) -> None:
    await _seed_task(runtime_db, agent_id="agent_a", task_id=1)
    await _seed_task(runtime_db, agent_id="agent_b", task_id=2)

    store_a = _build_store("agent_a")
    store_a.create_environment(
        task_id=1,
        user_id=1,
        chat_id=1,
        classification="light",
        environment_kind="dev_worktree",
        isolation="shared",
        duration="short",
        workspace_path="/tmp/work/1",
        runtime_dir="/tmp/rt/1",
        base_work_dir="/tmp/base",
        branch_name=None,
        created_worktree=False,
        worktree_mode="none",
        current_phase="executing",
    )

    store_b = _build_store("agent_b")
    store_b.create_environment(
        task_id=2,
        user_id=1,
        chat_id=1,
        classification="light",
        environment_kind="dev_worktree",
        isolation="shared",
        duration="short",
        workspace_path="/tmp/work/2",
        runtime_dir="/tmp/rt/2",
        base_work_dir="/tmp/base",
        branch_name=None,
        created_worktree=False,
        worktree_mode="none",
        current_phase="executing",
    )

    a_envs = store_a.list_environments()
    b_envs = store_b.list_environments()
    assert {e["task_id"] for e in a_envs} == {1}
    assert {e["task_id"] for e in b_envs} == {2}


# ---------------------------------------------------------------------------
# Port allocation persistence + cross-agent uniqueness
# ---------------------------------------------------------------------------


async def test_port_allocation_round_trip(runtime_db: str) -> None:
    await _seed_task(runtime_db, agent_id="agent_a", task_id=1)
    store = _build_store("agent_a")

    aid = store.add_port_allocation(
        task_id=1, env_id=None, purpose="vnc", host="127.0.0.1", port=5900
    )
    assert aid > 0
    rows = store.list_port_allocations(task_id=1)
    assert len(rows) == 1
    assert rows[0]["host"] == "127.0.0.1"
    assert rows[0]["port"] == 5900
    assert rows[0]["status"] == "allocated"

    assert store.is_port_allocated("127.0.0.1", 5900) is True
    assert store.is_port_allocated("127.0.0.1", 5901) is False


async def test_port_allocation_release_persists(runtime_db: str) -> None:
    await _seed_task(runtime_db, agent_id="agent_a", task_id=1)
    store = _build_store("agent_a")
    aid = store.add_port_allocation(
        task_id=1, env_id=None, purpose="vnc", host="127.0.0.1", port=5910
    )
    store.update_port_allocation(aid, status="released", released=True)
    rows = store.list_port_allocations(task_id=1)
    assert rows[0]["status"] == "released"
    # Released port no longer counts as allocated.
    assert store.is_port_allocated("127.0.0.1", 5910) is False


async def test_port_allocation_isolated_per_agent(runtime_db: str) -> None:
    """agent_a and agent_b can each register port 5920 — they are scoped per agent.

    `is_port_allocated` is also agent-scoped, so each agent only "sees" its
    own active reservations. Cross-agent collision must be prevented at a
    higher layer (e.g. cluster resource manager), not here.
    """
    await _seed_task(runtime_db, agent_id="agent_a", task_id=1)
    await _seed_task(runtime_db, agent_id="agent_b", task_id=2)

    store_a = _build_store("agent_a")
    store_a.add_port_allocation(
        task_id=1, env_id=None, purpose="vnc", host="127.0.0.1", port=5920
    )
    assert store_a.is_port_allocated("127.0.0.1", 5920) is True

    store_b = _build_store("agent_b")
    # From agent_b's scope, the port appears free even though agent_a has it.
    assert store_b.is_port_allocated("127.0.0.1", 5920) is False
    store_b.add_port_allocation(
        task_id=2, env_id=None, purpose="vnc", host="127.0.0.1", port=5920
    )
    # agent_b list shows only its own allocation.
    a_rows = store_a.list_port_allocations(task_id=1)
    b_rows = store_b.list_port_allocations(task_id=2)
    assert len(a_rows) == 1
    assert len(b_rows) == 1


# ---------------------------------------------------------------------------
# Index sanity (EXPLAIN) — list_events hot path uses idx_runtime_events_task
# ---------------------------------------------------------------------------


async def test_runtime_events_query_uses_index(runtime_db: str) -> None:
    """When list_events scans by (agent_id, task_id, seq), the planner should
    use idx_runtime_events_task and not seq scan."""
    await _seed_task(runtime_db, agent_id="agent_a", task_id=1)
    store = _build_store("agent_a")
    for i in range(50):
        store.add_event(task_id=1, env_id=None, attempt=1, phase="x", severity="info", event_type=f"e{i}")

    # Direct EXPLAIN against the same query shape.
    conn = await asyncpg.connect(runtime_db)
    try:
        plan_rows: list[Any] = await conn.fetch(
            """
            EXPLAIN
            SELECT * FROM knowledge_v2.runtime_events
            WHERE agent_id = $1 AND task_id = $2 AND id > $3
            ORDER BY id ASC
            """,
            "agent_a", 1, 0,
        )
    finally:
        await conn.close()
    plan_text = "\n".join(str(r[0]) for r in plan_rows).lower()
    # Either Index Scan or Bitmap Index Scan — never bare Seq Scan with no qualifier.
    assert "index" in plan_text or "bitmap" in plan_text, f"unexpected plan: {plan_text}"
