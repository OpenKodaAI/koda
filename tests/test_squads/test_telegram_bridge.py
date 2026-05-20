"""Tests for the squad ↔ telegram binding service."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import suppress

import pytest

from koda.squads.telegram_bridge import (
    SquadTelegramBindingService,
    TelegramBindingConflictError,
)


def _schema() -> str:
    return (os.environ.get("KNOWLEDGE_V2_POSTGRES_SCHEMA") or "knowledge_v2").strip() or "knowledge_v2"


def test_rejects_invalid_schema() -> None:
    with pytest.raises(ValueError):
        SquadTelegramBindingService(dsn="postgresql://x/y", schema="bad-schema!")


@pytest.fixture
async def clean_state(migrated_postgres: str) -> AsyncIterator[str]:
    import asyncpg  # type: ignore[import-not-found]

    schema = _schema()
    conn = await asyncpg.connect(migrated_postgres)
    try:
        await conn.execute(f'TRUNCATE TABLE "{schema}"."squad_telegram_bindings"')
    finally:
        await conn.close()
    yield migrated_postgres


@pytest.fixture
async def service(clean_state: str) -> AsyncIterator[SquadTelegramBindingService]:
    s = SquadTelegramBindingService(dsn=clean_state, schema=_schema())
    try:
        yield s
    finally:
        with suppress(Exception):
            await s.close()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_bind_creates_binding(service: SquadTelegramBindingService) -> None:
    binding = await service.bind(
        squad_id="build",
        telegram_chat_id=-100_123,
        chat_title="Build Squad",
        is_forum=True,
        bound_by_user_id=42,
    )
    assert binding.squad_id == "build"
    assert binding.telegram_chat_id == -100_123
    assert binding.chat_title == "Build Squad"
    assert binding.is_forum is True
    assert binding.bound_by_user_id == 42


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_bind_idempotent_for_same_pair(service: SquadTelegramBindingService) -> None:
    a = await service.bind(squad_id="build", telegram_chat_id=-100_123, chat_title="v1")
    b = await service.bind(squad_id="build", telegram_chat_id=-100_123, chat_title="v2")
    assert a.squad_id == b.squad_id == "build"
    assert b.chat_title == "v2"  # upsert refreshes the title


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_bind_replaces_chat_for_same_squad(service: SquadTelegramBindingService) -> None:
    await service.bind(squad_id="build", telegram_chat_id=-100_123)
    second = await service.bind(squad_id="build", telegram_chat_id=-100_999)
    assert second.telegram_chat_id == -100_999
    # Old chat no longer maps anywhere.
    by_old = await service.get_for_chat(-100_123)
    assert by_old is None


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_bind_conflicts_on_different_squad_same_chat(service: SquadTelegramBindingService) -> None:
    await service.bind(squad_id="build", telegram_chat_id=-100_123)
    with pytest.raises(TelegramBindingConflictError):
        await service.bind(squad_id="ops", telegram_chat_id=-100_123)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_bind_force_replaces_other_squad(service: SquadTelegramBindingService) -> None:
    await service.bind(squad_id="build", telegram_chat_id=-100_123)
    new_binding = await service.bind(squad_id="ops", telegram_chat_id=-100_123, force=True)
    assert new_binding.squad_id == "ops"
    # The previous squad's binding row is gone (UNIQUE on chat_id was honored).
    old = await service.get_for_squad("build")
    assert old is None


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_unbind_removes_binding(service: SquadTelegramBindingService) -> None:
    await service.bind(squad_id="build", telegram_chat_id=-100_123)
    removed = await service.unbind(squad_id="build")
    assert removed is True
    assert await service.get_for_squad("build") is None


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_unbind_when_missing_returns_false(service: SquadTelegramBindingService) -> None:
    removed = await service.unbind(squad_id="nope")
    assert removed is False


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_get_for_chat_returns_binding(service: SquadTelegramBindingService) -> None:
    await service.bind(squad_id="build", telegram_chat_id=-100_123, is_forum=True)
    found = await service.get_for_chat(-100_123)
    assert found is not None
    assert found.squad_id == "build"
    assert found.is_forum is True


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_thread_lookup_by_telegram_topic(clean_state: str) -> None:
    from koda.squads.threads import SquadThreadStore

    threads = SquadThreadStore(dsn=clean_state, schema=_schema())
    try:
        thread = await threads.create_thread(
            workspace_id="acme",
            squad_id="build",
            title="Landing",
            telegram_chat_id=-100_123,
            telegram_message_thread_id=7,
        )
        found = await threads.find_by_telegram_topic(
            telegram_chat_id=-100_123,
            telegram_message_thread_id=7,
        )
        assert found is not None
        assert found.id == thread.id
        miss = await threads.find_by_telegram_topic(
            telegram_chat_id=-100_123,
            telegram_message_thread_id=99,
        )
        assert miss is None
    finally:
        with suppress(Exception):
            await threads.close()
