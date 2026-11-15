from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any

import pytest

from koda.squads.access import SquadAccessError, SquadAccessService, SquadPrincipal
from koda.squads.threads import SquadThreadStore
from tests.postgres_fixtures import reset_squad_runtime_tables


def _schema() -> str:
    return (os.environ.get("KNOWLEDGE_V2_POSTGRES_SCHEMA") or "knowledge_v2").strip() or "knowledge_v2"


@pytest.fixture
async def stores(migrated_postgres: str) -> AsyncIterator[tuple[SquadThreadStore, SquadAccessService]]:
    import asyncpg  # type: ignore[import-not-found]

    schema = _schema()
    conn = await asyncpg.connect(migrated_postgres)
    try:
        await reset_squad_runtime_tables(conn, schema)
    finally:
        await conn.close()
    threads = SquadThreadStore(dsn=migrated_postgres, schema=schema)
    access = SquadAccessService(dsn=migrated_postgres, schema=schema)
    try:
        yield threads, access
    finally:
        with suppress(Exception):
            await threads.close()
        with suppress(Exception):
            await access.close()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_membership_required(stores: tuple[SquadThreadStore, SquadAccessService]) -> None:
    threads, access = stores
    thread = await threads.create_thread(
        workspace_id="acme",
        squad_id="build",
        title="t",
        participants=[("PM", "coordinator")],
    )
    grant = await access.require_thread_access(thread_id=thread.id, agent_id="PM")
    assert grant.thread.id == thread.id
    with pytest.raises(SquadAccessError):
        await access.require_thread_access(thread_id=thread.id, agent_id="STRANGER")


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_private_thread_rejects_an_elected_coordinator_who_is_not_a_participant(
    stores: tuple[SquadThreadStore, SquadAccessService],
    migrated_postgres: str,
) -> None:
    threads, access = stores
    thread = await threads.create_thread(
        workspace_id="acme",
        squad_id="build",
        title="private",
        visibility="private",
        participants=[("A", "worker")],
    )
    await _set_coordinator(migrated_postgres, "build", "PM")
    with pytest.raises(SquadAccessError):
        await access.require_thread_access(thread_id=thread.id, agent_id="PM")
    with pytest.raises(SquadAccessError):
        await access.require_thread_access(thread_id=thread.id, agent_id="PM", require_write=True)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_joined_at_blocks_retroactive_message_read(
    stores: tuple[SquadThreadStore, SquadAccessService],
) -> None:
    threads, access = stores
    thread = await threads.create_thread(workspace_id="acme", squad_id="build", title="t")
    msg_id = await threads.post_thread_message(thread_id=thread.id, from_agent="PM", content="old")
    await threads.add_participant(thread_id=thread.id, agent_id="LATE", role="worker")
    with pytest.raises(SquadAccessError):
        await access.require_thread_access(thread_id=thread.id, agent_id="LATE", message_id=msg_id)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_operator_private_thread_is_redacted(
    stores: tuple[SquadThreadStore, SquadAccessService],
) -> None:
    threads, access = stores
    thread = await threads.create_thread(
        workspace_id="acme",
        squad_id="build",
        title="private",
        visibility="private",
        participants=[("A", "worker")],
    )
    await threads.post_thread_message(thread_id=thread.id, from_agent="A", content="secret")
    grant = await access.require_thread_access_for_principal(
        thread_id=thread.id,
        principal=SquadPrincipal.workspace_operator("ops", workspace_id="acme"),
    )
    assert grant.redacted is True
    history = await threads.thread_history(thread_id=thread.id)
    redacted = access.redact_messages(grant, history)
    assert redacted[0]["content"] == "[redacted]"


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_operator_cross_workspace_rejected(
    stores: tuple[SquadThreadStore, SquadAccessService],
) -> None:
    threads, access = stores
    thread = await threads.create_thread(workspace_id="acme", squad_id="build", title="t")
    with pytest.raises(SquadAccessError):
        await access.require_thread_access_for_principal(
            thread_id=thread.id,
            principal=SquadPrincipal.workspace_operator("ops", workspace_id="other"),
        )


async def _set_coordinator(dsn: str, squad_id: str, agent_id: str) -> None:
    import asyncpg  # type: ignore[import-not-found]

    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(
            f"""INSERT INTO "{_schema()}"."squad_coordinator_state" (squad_id, coordinator_agent_id)
                  VALUES ($1, $2)""",
            squad_id,
            agent_id,
        )
    finally:
        await conn.close()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_squad_admin_requires_the_current_coordinator_or_a_workspace_operator(
    stores: tuple[SquadThreadStore, SquadAccessService],
    migrated_postgres: str,
) -> None:
    _, access = stores
    # No coordinator yet: no agent may administer the squad, itself included.
    with pytest.raises(SquadAccessError):
        await access.require_squad_admin(
            squad_id="build",
            squad_workspace_id="acme",
            principal=SquadPrincipal.agent("WORKER"),
        )
    await _set_coordinator(migrated_postgres, "build", "PM")
    with pytest.raises(SquadAccessError):
        await access.require_squad_admin(
            squad_id="build",
            squad_workspace_id="acme",
            principal=SquadPrincipal.agent("WORKER"),
        )
    await access.require_squad_admin(
        squad_id="build",
        squad_workspace_id="acme",
        principal=SquadPrincipal.agent("PM"),
    )
    # A coordinator of one squad does not administer another.
    with pytest.raises(SquadAccessError):
        await access.require_squad_admin(
            squad_id="ops",
            squad_workspace_id="acme",
            principal=SquadPrincipal.agent("PM"),
        )
    await access.require_squad_admin(
        squad_id="build",
        squad_workspace_id="acme",
        principal=SquadPrincipal.workspace_operator("owner", workspace_id="acme"),
    )
    with pytest.raises(SquadAccessError):
        await access.require_squad_admin(
            squad_id="build",
            squad_workspace_id="acme",
            principal=SquadPrincipal.workspace_operator("owner", workspace_id="other"),
        )
    with pytest.raises(SquadAccessError):
        await access.require_squad_admin(
            squad_id="build",
            squad_workspace_id="acme",
            principal=SquadPrincipal.thread_owner(42, workspace_id="acme"),
        )


class _AuditFailingConnection:
    """Delegates to a real connection but fails every write to ``audit_events``."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    async def execute(self, query: str, *args: Any) -> Any:
        if "audit_events" in query:
            raise RuntimeError("audit store unavailable")
        return await self._conn.execute(query, *args)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


class _AuditFailingPool:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[_AuditFailingConnection]:
        async with self._pool.acquire() as conn:
            yield _AuditFailingConnection(conn)

    async def close(self) -> None:
        await self._pool.close()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_coordinator_outside_a_squad_thread_gets_no_access(
    stores: tuple[SquadThreadStore, SquadAccessService],
    migrated_postgres: str,
) -> None:
    threads, access = stores
    thread = await threads.create_thread(
        workspace_id="acme",
        squad_id="build",
        title="open",
        participants=[("A", "worker")],
    )
    await _set_coordinator(migrated_postgres, "build", "PM")
    with pytest.raises(SquadAccessError):
        await access.require_thread_access(thread_id=thread.id, agent_id="PM")


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_participant_coordinator_keeps_coordination_actions(
    stores: tuple[SquadThreadStore, SquadAccessService],
    migrated_postgres: str,
) -> None:
    threads, access = stores
    thread = await threads.create_thread(workspace_id="acme", squad_id="build", title="t")
    msg_id = await threads.post_thread_message(thread_id=thread.id, from_agent="A", content="before PM joined")
    await threads.add_participant(thread_id=thread.id, agent_id="PM", role="coordinator")
    await _set_coordinator(migrated_postgres, "build", "PM")
    grant = await access.require_thread_access(thread_id=thread.id, agent_id="PM", message_id=msg_id)
    assert grant.is_coordinator is True
    assert access.visible_after_for(grant) is None


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_break_glass_writes_its_audit_event(
    stores: tuple[SquadThreadStore, SquadAccessService],
    migrated_postgres: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("koda.config.SQUAD_OPERATOR_BREAK_GLASS_ENABLED", True)
    threads, access = stores
    thread = await threads.create_thread(
        workspace_id="acme",
        squad_id="build",
        title="private",
        visibility="private",
        participants=[("A", "worker")],
    )
    grant = await access.require_thread_access_for_principal(
        thread_id=thread.id,
        principal=SquadPrincipal.workspace_operator("ops", workspace_id="acme", break_glass_reason="incident 42"),
    )
    assert grant.break_glass is True
    import asyncpg  # type: ignore[import-not-found]

    conn = await asyncpg.connect(migrated_postgres)
    try:
        count = await conn.fetchval(
            f"""SELECT COUNT(*) FROM "{_schema()}"."audit_events"
                 WHERE event_type = 'squad.operator.break_glass' AND trace_id = $1""",
            thread.id,
        )
    finally:
        await conn.close()
    assert count == 1


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_break_glass_is_refused_when_its_audit_write_fails(
    stores: tuple[SquadThreadStore, SquadAccessService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("koda.config.SQUAD_OPERATOR_BREAK_GLASS_ENABLED", True)
    threads, access = stores
    thread = await threads.create_thread(
        workspace_id="acme",
        squad_id="build",
        title="private",
        visibility="private",
        participants=[("A", "worker")],
    )
    access._pool = _AuditFailingPool(await access._ensure_pool())
    with pytest.raises(SquadAccessError, match="audit"):
        await access.require_thread_access_for_principal(
            thread_id=thread.id,
            principal=SquadPrincipal.workspace_operator("ops", workspace_id="acme", break_glass_reason="incident 42"),
        )
