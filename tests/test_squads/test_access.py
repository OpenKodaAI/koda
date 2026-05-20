from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import suppress

import pytest

from koda.squads.access import SquadAccessError, SquadAccessService, SquadPrincipal
from koda.squads.threads import SquadThreadStore


def _schema() -> str:
    return (os.environ.get("KNOWLEDGE_V2_POSTGRES_SCHEMA") or "knowledge_v2").strip() or "knowledge_v2"


@pytest.fixture
async def stores(migrated_postgres: str) -> AsyncIterator[tuple[SquadThreadStore, SquadAccessService]]:
    import asyncpg  # type: ignore[import-not-found]

    schema = _schema()
    conn = await asyncpg.connect(migrated_postgres)
    try:
        await conn.execute(f'TRUNCATE TABLE "{schema}"."squad_message_recipients"')
        await conn.execute(f'TRUNCATE TABLE "{schema}"."squad_coordinator_state"')
        await conn.execute(f'TRUNCATE TABLE "{schema}"."squad_thread_participants"')
        await conn.execute(f'TRUNCATE TABLE "{schema}"."squad_threads"')
        await conn.execute(f'TRUNCATE TABLE "{schema}"."squad_messages" RESTART IDENTITY CASCADE')
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
async def test_private_thread_allows_elected_coordinator(
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
    import asyncpg  # type: ignore[import-not-found]

    conn = await asyncpg.connect(migrated_postgres)
    try:
        await conn.execute(
            f"""INSERT INTO "{_schema()}"."squad_coordinator_state" (squad_id, coordinator_agent_id)
                  VALUES ('build', 'PM')""",
        )
    finally:
        await conn.close()
    grant = await access.require_thread_access(thread_id=thread.id, agent_id="PM")
    assert grant.is_coordinator is True
    assert grant.redacted is False


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
