"""Extended integration tests for koda.services.runtime.postgres_store.

Cover the runtime persistence surface NOT exercised by
test_runtime_postgres_isolation.py:

  * upsert_terminal / list_terminals
  * upsert_process / update_process / list_processes
  * add_browser_session / update_browser_session / list_browser_sessions
  * add_recovery_action

All against the real testcontainers Postgres + JSONB codec from the
shared fixture pattern.
"""

from __future__ import annotations

import contextlib
import importlib
import json as _json
from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import pytest

pytestmark = [pytest.mark.postgres]


@pytest.fixture
async def runtime_db(migrated_postgres: str, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[str]:
    """Same wiring as test_runtime_postgres_isolation: reload knowledge config,
    install JSONB codec, truncate tables.
    """
    import koda.knowledge.config as kn_config

    importlib.reload(kn_config)

    from koda.knowledge.v2 import common as common_mod

    if hasattr(common_mod, "_SHARED_BACKENDS"):
        common_mod._SHARED_BACKENDS.clear()  # type: ignore[attr-defined]

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

    conn = await asyncpg.connect(migrated_postgres)
    try:
        for table in (
            "runtime_browser_sessions",
            "runtime_terminals",
            "runtime_processes",
            "runtime_recovery_actions",
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
    import koda.config as config_mod

    config_mod.AGENT_ID = agent_id
    import koda.services.runtime.postgres_store as ps_mod

    importlib.reload(ps_mod)
    return ps_mod.PostgresRuntimeStore()


async def _seed_task(dsn: str, *, agent_id: str, task_id: int) -> None:
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
            100,
            100,
            "queued",
            f"task {task_id}",
            1,
            3,
            0.0,
            "2026-05-01T00:00:00+00:00",
        )
    finally:
        await conn.close()


# upsert_terminal / list_terminals


async def test_upsert_terminal_creates_row_with_returning_id(runtime_db: str) -> None:
    await _seed_task(runtime_db, agent_id="agent_a", task_id=1)
    store = _build_store("agent_a")
    tid = store.upsert_terminal(
        task_id=1,
        env_id=None,
        terminal_kind="shell",
        label="bash",
        path="/dev/pts/0",
        interactive=True,
    )
    assert tid > 0
    rows = store.list_terminals(task_id=1)
    assert len(rows) == 1
    assert rows[0]["terminal_kind"] == "shell"
    assert rows[0]["label"] == "bash"
    assert rows[0]["interactive"] is True


async def test_upsert_terminal_with_stream_path(runtime_db: str) -> None:
    await _seed_task(runtime_db, agent_id="agent_a", task_id=1)
    store = _build_store("agent_a")
    store.upsert_terminal(
        task_id=1,
        env_id=None,
        terminal_kind="shell",
        label="t1",
        path="/dev/pts/1",
        stream_path="/tmp/koda/streams/t1.log",
    )
    rows = store.list_terminals(task_id=1)
    assert rows[0]["stream_path"] == "/tmp/koda/streams/t1.log"


async def test_list_terminals_returns_only_own_agent(runtime_db: str) -> None:
    await _seed_task(runtime_db, agent_id="agent_a", task_id=1)
    await _seed_task(runtime_db, agent_id="agent_b", task_id=2)

    store_a = _build_store("agent_a")
    store_a.upsert_terminal(task_id=1, env_id=None, terminal_kind="shell", label="A1", path="/dev/pts/1")
    store_a.upsert_terminal(task_id=1, env_id=None, terminal_kind="repl", label="A2", path="/dev/pts/2")

    store_b = _build_store("agent_b")
    store_b.upsert_terminal(task_id=2, env_id=None, terminal_kind="shell", label="B1", path="/dev/pts/3")

    a_rows = store_a.list_terminals(task_id=1)
    b_rows = store_b.list_terminals(task_id=2)
    assert sorted(r["label"] for r in a_rows) == ["A1", "A2"]
    assert [r["label"] for r in b_rows] == ["B1"]


async def test_update_terminal_persists_offsets(runtime_db: str) -> None:
    await _seed_task(runtime_db, agent_id="agent_a", task_id=1)
    store = _build_store("agent_a")
    tid = store.upsert_terminal(task_id=1, env_id=None, terminal_kind="shell", label="t", path="/dev/pts/1")
    store.update_terminal(tid, cursor_offset=512, last_offset=1024)
    rows = store.list_terminals(task_id=1)
    assert rows[0]["cursor_offset"] == 512
    assert rows[0]["last_offset"] == 1024


# upsert_process / update_process / list_processes


async def test_upsert_process_creates_row(runtime_db: str) -> None:
    await _seed_task(runtime_db, agent_id="agent_a", task_id=1)
    store = _build_store("agent_a")
    pid_db = store.upsert_process(
        task_id=1,
        env_id=None,
        pid=42,
        pgid=42,
        role="primary",
        command="bash -i",
        process_kind="shell",
    )
    assert pid_db > 0
    rows = store.list_processes(task_id=1)
    assert len(rows) == 1
    assert rows[0]["pid"] == 42
    assert rows[0]["role"] == "primary"
    assert rows[0]["process_kind"] == "shell"
    assert rows[0]["status"] == "running"


async def test_upsert_process_idempotent_for_same_pid_role_kind(runtime_db: str) -> None:
    """upsert_process keys on (agent_id, task_id, env_id, pid, role, process_kind).
    Re-calling updates the existing row instead of inserting a duplicate."""
    await _seed_task(runtime_db, agent_id="agent_a", task_id=1)
    store = _build_store("agent_a")
    first = store.upsert_process(task_id=1, env_id=None, pid=99, pgid=99, role="worker", command="bash")
    second = store.upsert_process(task_id=1, env_id=None, pid=99, pgid=99, role="worker", command="bash --new-flag")
    assert first == second
    rows = store.list_processes(task_id=1)
    assert len(rows) == 1
    # The command was updated.
    assert "new-flag" in rows[0]["command"]


async def test_update_process_marks_exited(runtime_db: str) -> None:
    await _seed_task(runtime_db, agent_id="agent_a", task_id=1)
    store = _build_store("agent_a")
    pid_db = store.upsert_process(task_id=1, env_id=None, pid=77, pgid=77, role="worker", command="echo")
    store.update_process(pid_db, status="exited", exit_code=0, exited=True)
    rows = store.list_processes(task_id=1)
    assert rows[0]["status"] == "exited"
    assert rows[0]["exit_code"] == 0
    assert rows[0]["exited_at"] is not None


async def test_list_processes_filtered_by_env_id(runtime_db: str) -> None:
    await _seed_task(runtime_db, agent_id="agent_a", task_id=1)
    store = _build_store("agent_a")
    store.upsert_process(task_id=1, env_id=10, pid=1, pgid=1, role="r1", command="echo")
    store.upsert_process(task_id=1, env_id=20, pid=2, pgid=2, role="r2", command="echo")

    all_rows = store.list_processes(task_id=1)
    assert len(all_rows) == 2

    env10 = store.list_processes(task_id=1, env_id=10)
    assert len(env10) == 1
    assert env10[0]["env_id"] == 10


async def test_list_processes_isolated_per_agent(runtime_db: str) -> None:
    """tasks PK is BIGSERIAL so each agent uses a distinct task_id; the
    isolation we verify is on runtime_processes (filtered by agent_id)."""
    await _seed_task(runtime_db, agent_id="agent_a", task_id=1)
    await _seed_task(runtime_db, agent_id="agent_b", task_id=2)

    store_a = _build_store("agent_a")
    store_a.upsert_process(task_id=1, env_id=None, pid=10, pgid=10, role="r", command="A")

    store_b = _build_store("agent_b")
    store_b.upsert_process(task_id=2, env_id=None, pid=20, pgid=20, role="r", command="B")

    a_rows = store_a.list_processes(task_id=1)
    b_rows = store_b.list_processes(task_id=2)
    assert [r["pid"] for r in a_rows] == [10]
    assert [r["pid"] for r in b_rows] == [20]


# add_browser_session / update / list


async def test_add_browser_session_round_trip(runtime_db: str) -> None:
    await _seed_task(runtime_db, agent_id="agent_a", task_id=1)
    store = _build_store("agent_a")
    sid = store.add_browser_session(
        task_id=1,
        env_id=None,
        scope_id=42,
        transport="vnc",
        status="active",
        display_id=99,
        vnc_port=5900,
        novnc_port=6080,
        metadata={"viewport_width": 1280, "viewport_height": 720},
    )
    assert sid > 0
    sessions = store.list_browser_sessions(task_id=1)
    assert len(sessions) == 1
    s = sessions[0]
    assert s["scope_id"] == 42
    assert s["transport"] == "vnc"
    assert s["vnc_port"] == 5900
    assert s["novnc_port"] == 6080
    assert s["metadata"] == {"viewport_width": 1280, "viewport_height": 720}


async def test_update_browser_session_marks_ended(runtime_db: str) -> None:
    await _seed_task(runtime_db, agent_id="agent_a", task_id=1)
    store = _build_store("agent_a")
    sid = store.add_browser_session(
        task_id=1,
        env_id=None,
        scope_id=1,
        transport="vnc",
        status="active",
        display_id=None,
        vnc_port=None,
        novnc_port=None,
    )
    store.update_browser_session(sid, status="closed", ended=True)
    sessions = store.list_browser_sessions(task_id=1)
    assert sessions[0]["status"] == "closed"
    assert sessions[0]["ended_at"] is not None


async def test_list_browser_sessions_isolated_per_agent(runtime_db: str) -> None:
    await _seed_task(runtime_db, agent_id="agent_a", task_id=1)
    await _seed_task(runtime_db, agent_id="agent_b", task_id=2)

    store_a = _build_store("agent_a")
    store_a.add_browser_session(
        task_id=1,
        env_id=None,
        scope_id=1,
        transport="vnc",
        status="active",
        display_id=None,
        vnc_port=None,
        novnc_port=None,
    )

    store_b = _build_store("agent_b")
    store_b.add_browser_session(
        task_id=2,
        env_id=None,
        scope_id=2,
        transport="cdp",
        status="active",
        display_id=None,
        vnc_port=None,
        novnc_port=None,
    )

    a_rows = store_a.list_browser_sessions(task_id=1)
    b_rows = store_b.list_browser_sessions(task_id=2)
    assert [s["scope_id"] for s in a_rows] == [1]
    assert [s["scope_id"] for s in b_rows] == [2]
    assert a_rows[0]["transport"] == "vnc"
    assert b_rows[0]["transport"] == "cdp"


# add_recovery_action — audit trail for recovery sweeps


async def test_add_recovery_action_persists_with_details(runtime_db: str) -> None:
    await _seed_task(runtime_db, agent_id="agent_a", task_id=1)
    store = _build_store("agent_a")
    aid = store.add_recovery_action(
        task_id=1,
        env_id=10,
        action="reattach",
        status="planned",
        details={"alive_process_count": 2},
    )
    assert aid > 0
    # Verify directly via SQL — there's no list_recovery_actions in the public surface.
    conn = await asyncpg.connect(runtime_db)
    try:
        rows = await conn.fetch(
            "SELECT action, status, details_json FROM knowledge_v2.runtime_recovery_actions "
            "WHERE agent_id = $1 AND id = $2",
            "agent_a",
            aid,
        )
    finally:
        await conn.close()
    assert len(rows) == 1
    assert rows[0]["action"] == "reattach"
    assert rows[0]["status"] == "planned"
    # The direct asyncpg connection here doesn't have the test JSONB codec
    # installed (that's bound to primary_* connection acquisition), so the
    # column comes back as a JSON string.
    raw = rows[0]["details_json"]
    if isinstance(raw, str):
        details = _json.loads(raw)
    else:
        details = raw
    assert details == {"alive_process_count": 2}


async def test_add_recovery_action_with_checkpoint_reference(runtime_db: str) -> None:
    await _seed_task(runtime_db, agent_id="agent_a", task_id=1)
    store = _build_store("agent_a")
    aid = store.add_recovery_action(
        task_id=1,
        env_id=10,
        action="reconstruct",
        status="planned",
        checkpoint_id=999,
    )
    assert aid > 0
    conn = await asyncpg.connect(runtime_db)
    try:
        row = await conn.fetchrow(
            "SELECT action, checkpoint_id FROM knowledge_v2.runtime_recovery_actions WHERE agent_id = $1 AND id = $2",
            "agent_a",
            aid,
        )
    finally:
        await conn.close()
    assert row is not None
    assert row["action"] == "reconstruct"
    assert row["checkpoint_id"] == 999
