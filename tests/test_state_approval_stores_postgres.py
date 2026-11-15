"""The approval tables live in the migration registry, with agent-scoped writes (D-059, D-060).

``pending_approvals`` and ``approval_grants`` used to be created at runtime
with INTEGER user and chat ids, so a Telegram id above 2^31 failed the insert
and fell back to a JSON file that loading never read. Migration
``050_approval_tables`` creates both tables with BIGINT ids. Using a grant
used to delete every agent's grants and re-insert one process's snapshot row by
row; it now writes only that grant, scoped by its agent. Legacy grants without
an agent get the agent their stored scope or chat binding names, or are
expired with one audit row each.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import Counter
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import asyncpg
import pytest

from tests.postgres_fixtures import close_shared_postgres_backends, injected_fault, stop_primary_bridge

pytestmark = [pytest.mark.postgres]

_MIGRATION = "050_approval_tables"
_BIG_USER = 2**31 + 7
_SUPERGROUP_CHAT = -1002147483648  # below -2^31, as Telegram supergroup ids are
_USER = 4242
_CHAT = 4242
_ENVELOPE = SimpleNamespace(resource_scope_fingerprint="scope-fp", params_fingerprint="params-fp")
_SCOPE = SimpleNamespace()


def _scope_grant(agent_id: str, *, uses: int = 3) -> dict[str, Any]:
    return {
        "user_id": _USER,
        "agent_id": agent_id,
        "session_id": None,
        "chat_id": _CHAT,
        "kind": "approve_scope",
        "max_uses": uses,
        "remaining_uses": uses,
        "resource_scope_fingerprint": "scope-fp",
        "params_fingerprint": "params-fp",
        "exact_fingerprint": "scope-fp:params-fp",
        "scope_fingerprint": "scope-fp",
    }


@pytest.fixture
async def approval_db(migrated_postgres: str) -> AsyncIterator[tuple[Any, str]]:
    """A connection to the test database, with both approval tables emptied before and after."""
    from koda.knowledge.config import KNOWLEDGE_V2_POSTGRES_SCHEMA

    schema = KNOWLEDGE_V2_POSTGRES_SCHEMA
    conn = await asyncpg.connect(migrated_postgres)

    async def _empty() -> None:
        for table in ("approval_grants", "pending_approvals"):
            if await conn.fetchval("SELECT to_regclass($1)", f'"{schema}"."{table}"') is not None:
                await conn.execute(f'TRUNCATE TABLE "{schema}"."{table}"')

    await _empty()
    try:
        yield conn, schema
    finally:
        await _empty()
        await conn.close()
        stop_primary_bridge()


async def _grant_rows(conn: Any, schema: str) -> dict[str, dict[str, Any]]:
    rows = await conn.fetch(f'SELECT grant_id, agent_id, payload_json FROM "{schema}"."approval_grants"')
    return {str(row["grant_id"]): {"agent_id": row["agent_id"], **json.loads(row["payload_json"])} for row in rows}


async def _drain_tasks_started_since(before: set[asyncio.Task[Any]]) -> None:
    """Wait for the persistence tasks the approval module started with ``loop.create_task``."""
    started = asyncio.all_tasks() - before - {asyncio.current_task()}
    await asyncio.gather(*started)


async def test_ids_above_int32_persist_and_survive_a_restart(
    approval_db: tuple[Any, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import koda.config as config_module
    from koda.state import approval_grants, pending_approvals

    conn, schema = approval_db
    monkeypatch.setattr(config_module, "STATE_ROOT_DIR", tmp_path)

    # The migrations alone create both tables, with BIGINT ids and an agent column.
    columns = {
        (str(row["table_name"]), str(row["column_name"])): str(row["data_type"])
        for row in await conn.fetch(
            """SELECT table_name, column_name, data_type FROM information_schema.columns
                WHERE table_schema = $1 AND table_name IN ('approval_grants', 'pending_approvals')""",
            schema,
        )
    }
    for table in ("approval_grants", "pending_approvals"):
        assert columns.get((table, "user_id")) == "bigint"
        assert columns.get((table, "chat_id")) == "bigint"
        assert (table, "agent_id") in columns

    grant = _scope_grant("AGENT_A") | {"user_id": _BIG_USER, "chat_id": _SUPERGROUP_CHAT}
    await approval_grants.save_approval_grant("grant-big", grant, ttl_seconds=600)
    await pending_approvals.save_pending_op(
        "op-big",
        {"op_type": "agent_cmd", "user_id": _BIG_USER, "chat_id": _SUPERGROUP_CHAT, "agent_id": "AGENT_A"},
        ttl_seconds=600,
    )

    # A restart: every pool is closed, and the next read opens new connections.
    close_shared_postgres_backends()

    grants = await approval_grants.load_approval_grants()
    ops = await pending_approvals.load_pending_ops()
    assert grants["grant-big"]["user_id"] == _BIG_USER
    assert grants["grant-big"]["chat_id"] == _SUPERGROUP_CHAT
    assert ops["op-big"]["user_id"] == _BIG_USER
    assert ops["op-big"]["chat_id"] == _SUPERGROUP_CHAT
    stored = await conn.fetchrow(
        f'SELECT user_id, chat_id FROM "{schema}"."approval_grants" WHERE grant_id = $1', "grant-big"
    )
    assert (stored["user_id"], stored["chat_id"]) == (_BIG_USER, _SUPERGROUP_CHAT)
    assert not (tmp_path / "approval_grants.json").exists(), "the grant fell back to the JSON file"
    assert not (tmp_path / "pending_approvals.json").exists(), "the pending op fell back to the JSON file"


async def test_using_a_grant_in_one_agent_leaves_another_agents_grants_intact(
    approval_db: tuple[Any, str],
) -> None:
    from koda.state import approval_grants
    from koda.utils import approval

    conn, schema = approval_db
    await approval_grants.save_approval_grant("grant-a", _scope_grant("AGENT_A"), ttl_seconds=600)
    # Agent A's worker loaded its grants at startup; agent B issued its grant afterwards.
    approval._APPROVAL_GRANTS.update(await approval_grants.load_approval_grants())
    await approval_grants.save_approval_grant("grant-b", _scope_grant("AGENT_B"), ttl_seconds=600)

    before = asyncio.all_tasks()
    used = approval.consume_agent_approval_grant(
        user_id=_USER, agent_id="AGENT_A", envelope=_ENVELOPE, approval_scope=_SCOPE, chat_id=_CHAT
    )
    await _drain_tasks_started_since(before)

    assert used is not None and used["grant_id"] == "grant-a"
    rows = await _grant_rows(conn, schema)
    assert rows["grant-a"]["remaining_uses"] == 2
    assert rows["grant-b"]["agent_id"] == "AGENT_B"
    assert rows["grant-b"]["remaining_uses"] == 3

    # The last use removes only agent A's grant.
    for _ in range(2):
        before = asyncio.all_tasks()
        approval.consume_agent_approval_grant(
            user_id=_USER, agent_id="AGENT_A", envelope=_ENVELOPE, approval_scope=_SCOPE, chat_id=_CHAT
        )
        await _drain_tasks_started_since(before)
    assert set(await _grant_rows(conn, schema)) == {"grant-b"}


async def test_a_failure_mid_write_leaves_the_grants_unchanged(approval_db: tuple[Any, str]) -> None:
    from koda.state import approval_grants
    from koda.utils import approval

    conn, schema = approval_db
    for grant_id, agent_id in (("grant-a1", "AGENT_A"), ("grant-a2", "AGENT_A"), ("grant-b", "AGENT_B")):
        await approval_grants.save_approval_grant(grant_id, _scope_grant(agent_id), ttl_seconds=600)
    approval._APPROVAL_GRANTS.update(await approval_grants.load_approval_grants())
    unchanged = await _grant_rows(conn, schema)

    with injected_fault("approval_grants", "INSERT", rows_before=1):
        before = asyncio.all_tasks()
        approval.consume_agent_approval_grant(
            user_id=_USER, agent_id="AGENT_A", envelope=_ENVELOPE, approval_scope=_SCOPE, chat_id=_CHAT
        )
        await _drain_tasks_started_since(before)

    assert await _grant_rows(conn, schema) == unchanged


_LEGACY_GRANTS_DDL = """CREATE TABLE "{schema}"."approval_grants" (
    grant_id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    agent_id TEXT NOT NULL,
    session_id TEXT,
    chat_id INTEGER,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    payload_json TEXT NOT NULL
)"""

_LEGACY_PENDING_DDL = """CREATE TABLE "{schema}"."pending_approvals" (
    op_id TEXT PRIMARY KEY,
    op_type TEXT NOT NULL,
    user_id INTEGER,
    agent_id TEXT,
    session_id TEXT,
    chat_id INTEGER,
    description TEXT,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    payload_json TEXT NOT NULL
)"""


async def test_legacy_grants_get_a_derived_agent_or_expire_with_an_audit_row(postgres_url: str) -> None:
    from koda.knowledge.v2.postgres_backend import KnowledgeV2PostgresBackend

    schema = f"m2e1t1_legacy_{uuid.uuid4().hex[:10]}"
    conn = await asyncpg.connect(postgres_url)
    try:
        assert await KnowledgeV2PostgresBackend(agent_id=None, dsn=postgres_url, schema=schema).bootstrap()
        # The schema as the previous release left it: the runtime created both tables.
        await conn.execute(f'DROP TABLE IF EXISTS "{schema}"."approval_grants", "{schema}"."pending_approvals"')
        await conn.execute(_LEGACY_GRANTS_DDL.format(schema=schema))
        await conn.execute(_LEGACY_PENDING_DDL.format(schema=schema))
        await conn.execute(f'DELETE FROM "{schema}"."schema_migrations" WHERE version = $1', _MIGRATION)

        now = time.time()
        await conn.execute(
            f"""INSERT INTO "{schema}"."pending_approvals"
                   (op_id, op_type, user_id, agent_id, created_at, expires_at, payload_json)
                VALUES ('op-a', 'agent_cmd', 6, 'AGENT_A', $1, $2, '{{}}')""",
            now,
            now + 600,
        )
        await conn.execute(
            f"""INSERT INTO "{schema}"."sessions" (agent_id, user_id, session_id, provider, created_at, last_used)
                VALUES ('AGENT_B', 7, 'sess-b', 'claude', '2026-11-15', '2026-11-15')"""
        )
        for agent_id, user_id, chat_id in (("AGENT_C", 8, 800), ("AGENT_A", 9, 900), ("AGENT_B", 9, 900)):
            await conn.execute(
                f"""INSERT INTO "{schema}"."tasks" (agent_id, user_id, chat_id, created_at)
                    VALUES ($1, $2, $3, '2026-11-15')""",
                agent_id,
                user_id,
                chat_id,
            )

        legacy = {
            # The approval request that issued it names agent A.
            "g-request": ("", 6, None, None, {"issued_by_op_id": "op-a"}),
            # Its session belongs to agent B.
            "g-session": ("", 7, "sess-b", None, {}),
            # Only agent C works in its chat.
            "g-chat": ("", 8, None, 800, {}),
            # Agents A and B both work in its chat.
            "g-two-chat-agents": ("", 9, None, 900, {}),
            # Its request names agent A and its session agent B.
            "g-two-scope-agents": ("", 7, "sess-b", None, {"issued_by_op_id": "op-a"}),
            "g-nothing": ("", 10, None, 1000, {}),
            "g-not-json": ("", 11, None, None, None),
            # Already scoped to an agent: left as it is.
            "g-scoped": ("AGENT_D", 12, None, None, {}),
        }
        for grant_id, (agent_id, user_id, session_id, chat_id, extra) in legacy.items():
            payload = (
                "not json"
                if extra is None
                else json.dumps({"grant_id": grant_id, "agent_id": agent_id, "user_id": user_id, **extra})
            )
            await conn.execute(
                f"""INSERT INTO "{schema}"."approval_grants"
                       (grant_id, user_id, agent_id, session_id, chat_id, created_at, expires_at, payload_json)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
                grant_id,
                user_id,
                agent_id,
                session_id,
                chat_id,
                now,
                now + 600,
                payload,
            )

        assert await KnowledgeV2PostgresBackend(agent_id=None, dsn=postgres_url, schema=schema).bootstrap()

        types = {
            (str(row["table_name"]), str(row["column_name"])): str(row["data_type"])
            for row in await conn.fetch(
                """SELECT table_name, column_name, data_type FROM information_schema.columns
                    WHERE table_schema = $1 AND column_name IN ('user_id', 'chat_id')
                      AND table_name IN ('approval_grants', 'pending_approvals')""",
                schema,
            )
        }
        assert set(types.values()) == {"bigint"} and len(types) == 4

        rows = {
            str(row["grant_id"]): row
            for row in await conn.fetch(
                f'SELECT grant_id, agent_id, expires_at, payload_json FROM "{schema}"."approval_grants"'
            )
        }
        derived = {"g-request": "AGENT_A", "g-session": "AGENT_B", "g-chat": "AGENT_C", "g-scoped": "AGENT_D"}
        for grant_id, agent_id in derived.items():
            row = rows[grant_id]
            assert row["agent_id"] == agent_id
            # The payload is what the worker loads and matches on: it names the same, single agent.
            assert json.loads(row["payload_json"])["agent_id"] == agent_id
            assert row["expires_at"] > now
        expired = set(legacy) - set(derived)
        for grant_id in expired:
            assert rows[grant_id]["agent_id"] == ""
            assert rows[grant_id]["expires_at"] <= now

        audited = Counter(
            str(row["grant_id"])
            for row in await conn.fetch(
                f"""SELECT details_json ->> 'grant_id' AS grant_id FROM "{schema}"."audit_events"
                     WHERE event_type = 'approval.grant_expired'"""
            )
        )
        assert audited == Counter(expired)
    finally:
        await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await conn.close()
