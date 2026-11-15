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

    used = await approval.consume_agent_approval_grant(
        user_id=_USER, agent_id="AGENT_A", envelope=_ENVELOPE, approval_scope=_SCOPE, chat_id=_CHAT
    )

    assert used is not None and used["grant_id"] == "grant-a"
    rows = await _grant_rows(conn, schema)
    assert rows["grant-a"]["remaining_uses"] == 2
    assert rows["grant-b"]["agent_id"] == "AGENT_B"
    assert rows["grant-b"]["remaining_uses"] == 3

    # The last use removes only agent A's grant.
    for _ in range(2):
        await approval.consume_agent_approval_grant(
            user_id=_USER, agent_id="AGENT_A", envelope=_ENVELOPE, approval_scope=_SCOPE, chat_id=_CHAT
        )
    assert set(await _grant_rows(conn, schema)) == {"grant-b"}


async def test_a_failure_mid_write_leaves_the_grants_unchanged(
    approval_db: tuple[Any, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import koda.config as config_module
    from koda.state import approval_grants
    from koda.utils import approval

    conn, schema = approval_db
    # A failed write falls back to nothing: no file appears in the state root.
    monkeypatch.setattr(config_module, "STATE_ROOT_DIR", tmp_path)
    for grant_id, agent_id in (("grant-a1", "AGENT_A"), ("grant-a2", "AGENT_A"), ("grant-b", "AGENT_B")):
        await approval_grants.save_approval_grant(grant_id, _scope_grant(agent_id), ttl_seconds=600)
    approval._APPROVAL_GRANTS.update(await approval_grants.load_approval_grants())
    unchanged = await _grant_rows(conn, schema)

    with injected_fault("approval_grants", "UPDATE", rows_before=1), pytest.raises(asyncpg.PostgresError):
        await approval.consume_agent_approval_grant(
            user_id=_USER, agent_id="AGENT_A", envelope=_ENVELOPE, approval_scope=_SCOPE, chat_id=_CHAT
        )

    assert await _grant_rows(conn, schema) == unchanged
    assert list(tmp_path.iterdir()) == []


def _use(approval: Any) -> Any:
    return approval.consume_agent_approval_grant(
        user_id=_USER, agent_id="AGENT_A", envelope=_ENVELOPE, approval_scope=_SCOPE, chat_id=_CHAT
    )


async def test_a_revoked_grant_stays_revoked_when_a_use_of_it_follows(approval_db: tuple[Any, str]) -> None:
    """D-343: a use of a grant another worker revoked meanwhile neither re-inserts it nor counts."""
    from koda.state import approval_grants
    from koda.utils import approval

    conn, schema = approval_db
    await approval_grants.save_approval_grant("grant-a", _scope_grant("AGENT_A"), ttl_seconds=600)
    approval._APPROVAL_GRANTS.update(await approval_grants.load_approval_grants())

    # Another worker revokes it (a new session, say); this worker still holds it in memory.
    assert await approval_grants.remove_approval_grants(agent_id="AGENT_A", user_id=_USER) == 1
    assert await _use(approval) is None

    assert await _grant_rows(conn, schema) == {}
    assert "grant-a" not in approval._APPROVAL_GRANTS
    assert await _use(approval) is None


async def test_a_use_postgres_does_not_record_is_refused_and_memory_matches_the_database(
    approval_db: tuple[Any, str],
) -> None:
    """D-344: with a write failing, a grant is never used more often than it allows."""
    from koda.state import approval_grants
    from koda.utils import approval

    conn, schema = approval_db
    await approval_grants.save_approval_grant("grant-a", _scope_grant("AGENT_A", uses=2), ttl_seconds=600)
    approval._APPROVAL_GRANTS.update(await approval_grants.load_approval_grants())

    async def remaining() -> tuple[int | None, int | None]:
        row = (await _grant_rows(conn, schema)).get("grant-a")
        held = approval._APPROVAL_GRANTS.get("grant-a")
        return (row or {}).get("remaining_uses"), (held or {}).get("remaining_uses")

    uses = 0
    # A partial use is an UPDATE, the last use a DELETE: each fails once, and neither counts.
    for event, left in (("UPDATE", 2), ("DELETE", 1)):
        with injected_fault("approval_grants", event), pytest.raises(asyncpg.PostgresError):
            await _use(approval)
        assert await remaining() == (left, left)
        assert await _use(approval) is not None
        uses += 1
    assert await _use(approval) is None
    assert uses == 2
    assert await remaining() == (None, None)


async def _audited_grant_count(conn: Any, schema: str, grant_id: str) -> int:
    return int(
        await conn.fetchval(
            f"""SELECT count(*) FROM "{schema}"."audit_events"
                 WHERE event_type = 'approval.grant_expired' AND details_json ->> 'grant_id' = $1""",
            grant_id,
        )
    )


async def test_the_json_files_are_imported_once_at_startup(
    approval_db: tuple[Any, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M2-E1-T2: a grant an earlier release wrote to JSON is in Postgres after one boot, and only once."""
    import koda.config as config_module
    from koda.state import approval_grants, approval_import, pending_approvals

    conn, schema = approval_db
    monkeypatch.setattr(config_module, "STATE_ROOT_DIR", tmp_path)
    now = time.time()
    times = {"created_at": now, "expires_at": now + 600}
    pending = {"json-op": {"op_id": "json-op", "op_type": "agent_cmd", "user_id": 9101, "agent_id": "AGENT_B"} | times}
    grants = {
        "json-a": _scope_grant("AGENT_A") | {"grant_id": "json-a"} | times,
        # No agent: the approval request that issued it names agent B.
        "json-request": _scope_grant("")
        | {"grant_id": "json-request", "user_id": 9101, "chat_id": None, "issued_by_op_id": "json-op"}
        | times,
        # No agent, and nothing names one: it expires, with an audit row.
        "json-orphan-m2e1t2": _scope_grant("")
        | {"grant_id": "json-orphan-m2e1t2", "user_id": 9102, "chat_id": 9102000}
        | times,
    }
    seeded = {"pending_approvals.json": json.dumps(pending), "approval_grants.json": json.dumps(grants)}
    for name, content in seeded.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    audited_before = await _audited_grant_count(conn, schema, "json-orphan-m2e1t2")

    assert await approval_import.import_approval_json_files() == {
        "pending_approvals.json": 1,
        "approval_grants.json": 3,
    }

    rows = await _grant_rows(conn, schema)
    assert {grant_id: row["agent_id"] for grant_id, row in rows.items()} == {
        "json-a": "AGENT_A",
        "json-request": "AGENT_B",
        "json-orphan-m2e1t2": "",
    }
    assert rows["json-a"]["remaining_uses"] == 3
    assert set(await approval_grants.load_approval_grants()) == {"json-a", "json-request"}
    assert set(await pending_approvals.load_pending_ops()) == {"json-op"}
    assert await _audited_grant_count(conn, schema, "json-orphan-m2e1t2") == audited_before + 1
    # Each file is kept, renamed.
    for name, content in seeded.items():
        assert not (tmp_path / name).exists()
        assert (tmp_path / f"{name}.migrated").read_text(encoding="utf-8") == content

    # The next boot finds no file and imports nothing.
    imported = await _grant_rows(conn, schema)
    assert await approval_import.import_approval_json_files() == {}

    # A file seen again (an import that stopped before its rename) adds no row, changes none,
    # audits no grant twice, and is renamed beside the first copy.
    for name, content in seeded.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    assert await approval_import.import_approval_json_files() == {
        "pending_approvals.json": 0,
        "approval_grants.json": 0,
    }
    assert await _grant_rows(conn, schema) == imported
    assert await _audited_grant_count(conn, schema, "json-orphan-m2e1t2") == audited_before + 1
    for name in seeded:
        assert len(list(tmp_path.glob(f"{name}*.migrated"))) == 2


# 1.8e9 is a multiple of 128, the step of REAL (float4) there, so 10 seconds either side of this
# instant round to the same float4 value as the instant itself.
_ON_A_FLOAT4_STEP = 1_800_000_050.0


async def test_the_sql_expiry_filter_is_exact_to_the_second(postgres_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """D-347: a grant 10 seconds from expiry is valid, and one expired 10 seconds ago is filtered out."""
    import koda.knowledge.config as knowledge_config
    from koda.knowledge.v2.postgres_backend import KnowledgeV2PostgresBackend
    from koda.state import approval_grants, pending_approvals

    # A fresh schema, so 050 creates the tables as it stands now.
    schema = f"m2e1t2_expiry_{uuid.uuid4().hex[:10]}"
    conn = await asyncpg.connect(postgres_url)
    try:
        assert await KnowledgeV2PostgresBackend(agent_id=None, dsn=postgres_url, schema=schema).bootstrap()
        monkeypatch.setattr(knowledge_config, "KNOWLEDGE_V2_POSTGRES_SCHEMA", schema)
        clock = SimpleNamespace(time=lambda: _ON_A_FLOAT4_STEP)
        monkeypatch.setattr(approval_grants, "time", clock)
        monkeypatch.setattr(pending_approvals, "time", clock)

        for name, ttl in (("in-10s", 10), ("10s-ago", -10)):
            await approval_grants.save_approval_grant(f"grant-{name}", _scope_grant("AGENT_A"), ttl_seconds=ttl)
            await pending_approvals.save_pending_op(f"op-{name}", {"op_type": "agent_cmd", "user_id": _USER}, ttl)

        assert set(await approval_grants.load_approval_grants()) == {"grant-in-10s"}
        assert set(await pending_approvals.load_pending_ops()) == {"op-in-10s"}
        await approval_grants.cleanup_expired_approval_grants()
        await pending_approvals.cleanup_expired_ops()
        assert [row["grant_id"] for row in await conn.fetch(f'SELECT grant_id FROM "{schema}"."approval_grants"')] == [
            "grant-in-10s"
        ]
        assert [row["op_id"] for row in await conn.fetch(f'SELECT op_id FROM "{schema}"."pending_approvals"')] == [
            "op-in-10s"
        ]
    finally:
        close_shared_postgres_backends()
        stop_primary_bridge()
        await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await conn.close()


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
        for agent_id, user_id, session_id in (("AGENT_B", 7, "sess-b"), ("KODA", 13, "sess-before-027")):
            await conn.execute(
                f"""INSERT INTO "{schema}"."sessions" (agent_id, user_id, session_id, provider, created_at, last_used)
                    VALUES ($1, $2, $3, 'claude', '2026-11-15', '2026-11-15')""",
                agent_id,
                user_id,
                session_id,
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
            # Its session names KODA, which 027 wrote into every older session, whoever owned it.
            "g-backfilled-session": ("", 13, "sess-before-027", None, {}),
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
                    WHERE table_schema = $1 AND column_name IN ('user_id', 'chat_id', 'created_at', 'expires_at')
                      AND table_name IN ('approval_grants', 'pending_approvals')""",
                schema,
            )
        }
        for table in ("approval_grants", "pending_approvals"):
            assert (types[(table, "user_id")], types[(table, "chat_id")]) == ("bigint", "bigint")
            # The runtime created REAL (float4) epoch columns; 050 widens them (D-347).
            assert (types[(table, "created_at")], types[(table, "expires_at")]) == (
                "double precision",
                "double precision",
            )

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
