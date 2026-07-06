"""Tests for the squad thread store (Postgres-backed)."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import suppress

import pytest

from koda.squads import threads as thread_module
from koda.squads.replies import ThreadReplyError, ThreadReplyService
from koda.squads.threads import SquadThreadStore


def _schema() -> str:
    return (os.environ.get("KNOWLEDGE_V2_POSTGRES_SCHEMA") or "knowledge_v2").strip() or "knowledge_v2"


def test_rejects_invalid_schema() -> None:
    with pytest.raises(ValueError):
        SquadThreadStore(dsn="postgresql://x/y", schema="bad-schema!")


def test_archive_transition_policy_allows_open_and_paused_threads() -> None:
    assert "archived" in thread_module._ALLOWED_TRANSITIONS["open"]
    assert "archived" in thread_module._ALLOWED_TRANSITIONS["paused"]
    assert "archived" in thread_module._ALLOWED_TRANSITIONS["completed"]


@pytest.fixture
async def clean_squad_state(migrated_postgres: str) -> AsyncIterator[str]:
    import asyncpg  # type: ignore[import-not-found]

    schema = _schema()
    conn = await asyncpg.connect(migrated_postgres)
    try:
        await conn.execute(f'TRUNCATE TABLE "{schema}"."squad_reply_obligations" RESTART IDENTITY CASCADE')
        await conn.execute(f'TRUNCATE TABLE "{schema}"."squad_message_recipients"')
        await conn.execute(f'TRUNCATE TABLE "{schema}"."squad_thread_participants"')
        await conn.execute(f'TRUNCATE TABLE "{schema}"."squad_threads"')
        await conn.execute(f'TRUNCATE TABLE "{schema}"."squad_messages" RESTART IDENTITY CASCADE')
    finally:
        await conn.close()
    yield migrated_postgres


@pytest.fixture
async def store(clean_squad_state: str) -> AsyncIterator[SquadThreadStore]:
    s = SquadThreadStore(dsn=clean_squad_state, schema=_schema())
    try:
        yield s
    finally:
        with suppress(Exception):
            await s.close()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_create_thread_minimal(store: SquadThreadStore) -> None:
    thread = await store.create_thread(workspace_id="acme", squad_id="build", title="kickoff")
    assert thread.id
    assert thread.workspace_id == "acme"
    assert thread.squad_id == "build"
    assert thread.status == "open"
    assert thread.title == "kickoff"
    assert thread.visibility == "squad"


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_create_thread_with_participants_and_coordinator(store: SquadThreadStore) -> None:
    thread = await store.create_thread(
        workspace_id="acme",
        squad_id="build",
        title="landing page",
        coordinator_agent_id="PM",
        participants=[("FE", "worker"), ("BE", "worker")],
    )
    members = await store.list_participants(thread_id=thread.id)
    by_id = {m.agent_id: m for m in members}
    assert set(by_id) == {"PM", "FE", "BE"}
    assert by_id["PM"].role == "coordinator"
    assert by_id["FE"].role == "worker"


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_get_and_list_threads(store: SquadThreadStore) -> None:
    a = await store.create_thread(workspace_id="acme", squad_id="build", title="a")
    b = await store.create_thread(workspace_id="acme", squad_id="build", title="b")
    fetched = await store.get_thread(a.id)
    assert fetched is not None and fetched.id == a.id
    listed = await store.list_threads(workspace_id="acme", squad_id="build")
    ids = {t.id for t in listed}
    assert {a.id, b.id} <= ids


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_status_state_machine(store: SquadThreadStore) -> None:
    thread = await store.create_thread(workspace_id="acme", squad_id="build", title="t")
    paused = await store.update_thread_status(thread.id, "paused")
    assert paused.status == "paused"
    reopened = await store.update_thread_status(thread.id, "open")
    assert reopened.status == "open"
    completed = await store.update_thread_status(thread.id, "completed")
    assert completed.status == "completed"
    assert completed.completed_at is not None
    archived = await store.update_thread_status(thread.id, "archived")
    assert archived.status == "archived"
    assert archived.archived_at is not None


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_open_thread_can_be_archived_directly(store: SquadThreadStore) -> None:
    thread = await store.create_thread(workspace_id="acme", squad_id="build", title="t")
    archived = await store.update_thread_status(thread.id, "archived")
    assert archived.status == "archived"
    assert archived.archived_at is not None
    assert archived.completed_at is None


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_paused_thread_can_be_archived_directly(store: SquadThreadStore) -> None:
    thread = await store.create_thread(workspace_id="acme", squad_id="build", title="t")
    paused = await store.update_thread_status(thread.id, "paused")
    assert paused.status == "paused"
    archived = await store.update_thread_status(thread.id, "archived")
    assert archived.status == "archived"
    assert archived.archived_at is not None


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_status_illegal_transition(store: SquadThreadStore) -> None:
    thread = await store.create_thread(workspace_id="acme", squad_id="build", title="t")
    await store.update_thread_status(thread.id, "completed")
    with pytest.raises(ValueError):
        await store.update_thread_status(thread.id, "open")


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_add_remove_participant(store: SquadThreadStore) -> None:
    thread = await store.create_thread(workspace_id="acme", squad_id="build", title="t")
    info = await store.add_participant(thread_id=thread.id, agent_id="QA", role="observer")
    assert info.role == "observer"
    members = await store.list_participants(thread_id=thread.id)
    assert any(m.agent_id == "QA" for m in members)
    removed = await store.remove_participant(thread_id=thread.id, agent_id="QA")
    assert removed is True
    active = await store.list_participants(thread_id=thread.id)
    assert all(m.agent_id != "QA" for m in active)
    all_members = await store.list_participants(thread_id=thread.id, active_only=False)
    qa = next(m for m in all_members if m.agent_id == "QA")
    assert qa.left_at is not None


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_post_and_history_roundtrip(store: SquadThreadStore) -> None:
    thread = await store.create_thread(workspace_id="acme", squad_id="build", title="t")
    msg1 = await store.post_thread_message(thread_id=thread.id, from_agent="PM", content="hello")
    msg2 = await store.post_thread_message(thread_id=thread.id, from_agent="FE", content="on it")
    assert msg2 > msg1
    history = await store.thread_history(thread_id=thread.id, limit=10)
    contents = [h["content"] for h in history]
    assert contents == ["on it", "hello"]


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_thread_reply_obligation_roundtrip(store: SquadThreadStore) -> None:
    thread = await store.create_thread(
        workspace_id="acme",
        squad_id="build",
        title="t",
        coordinator_agent_id="PM",
        participants=[("FE", "worker"), ("BE", "worker")],
    )
    root_id = await store.post_thread_message(
        thread_id=thread.id,
        from_agent="operator",
        content="Need backend review",
        message_type="user_input",
        to_agent_ids=["BE"],
        metadata={"reply_contract_version": "thread_reply.v1"},
    )
    service = ThreadReplyService(store)
    obligations = await service.create_obligations(
        thread_id=thread.id,
        source_message_id=root_id,
        target_agent_ids=["BE"],
        source_agent_id="operator",
    )
    assert len(obligations) == 1
    assert obligations[0].status == "open"

    reply_id = await store.post_thread_message(
        thread_id=thread.id,
        from_agent="BE",
        content="Reviewed.",
        message_type="agent_reply",
        in_reply_to=f"msg-{root_id}",
        correlation_id=obligations[0].obligation_key,
    )
    resolved = await service.resolve_for_reply(
        thread_id=thread.id,
        reply_message_id=reply_id,
        from_agent="BE",
        in_reply_to=f"msg-{root_id}",
        correlation_id=obligations[0].obligation_key,
    )
    assert [item.status for item in resolved] == ["answered"]
    history = await store.thread_history(thread_id=thread.id, limit=10)
    by_id = {item["id"]: item for item in history}
    assert by_id[root_id]["reply_summary"]["answered"] == 1
    assert by_id[reply_id]["resolved_reply_obligations"][0]["targetAgentId"] == "BE"


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_thread_reply_rejects_non_participant_target(store: SquadThreadStore) -> None:
    thread = await store.create_thread(
        workspace_id="acme",
        squad_id="build",
        title="t",
        participants=[("FE", "worker")],
    )
    root_id = await store.post_thread_message(
        thread_id=thread.id,
        from_agent="operator",
        content="Need backend review",
        message_type="user_input",
    )
    service = ThreadReplyService(store)
    with pytest.raises(ThreadReplyError) as err:
        await service.create_obligations(
            thread_id=thread.id,
            source_message_id=root_id,
            target_agent_ids=["BE"],
            source_agent_id="operator",
        )
    assert err.value.code == "reply.target_not_participant"


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_history_pagination(store: SquadThreadStore) -> None:
    thread = await store.create_thread(workspace_id="acme", squad_id="build", title="t")
    ids = []
    for i in range(5):
        ids.append(await store.post_thread_message(thread_id=thread.id, from_agent="A", content=f"m{i}"))
    head = await store.thread_history(thread_id=thread.id, limit=2)
    assert [h["id"] for h in head] == [ids[4], ids[3]]
    rest = await store.thread_history(thread_id=thread.id, limit=10, before_id=ids[3])
    assert [h["id"] for h in rest] == [ids[2], ids[1], ids[0]]


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_post_to_unknown_thread_raises(store: SquadThreadStore) -> None:
    with pytest.raises(KeyError):
        await store.post_thread_message(
            thread_id="00000000-0000-0000-0000-000000000099",
            from_agent="X",
            content="orphan",
        )
