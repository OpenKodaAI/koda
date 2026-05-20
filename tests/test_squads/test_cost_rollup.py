"""Tests for the squad cost rollup trigger on query_history."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest


def _schema() -> str:
    return (os.environ.get("KNOWLEDGE_V2_POSTGRES_SCHEMA") or "knowledge_v2").strip() or "knowledge_v2"


@pytest.fixture
async def conn(migrated_postgres: str) -> AsyncIterator[object]:
    import asyncpg  # type: ignore[import-not-found]

    schema = _schema()
    raw = await asyncpg.connect(migrated_postgres)
    try:
        await raw.execute(f'TRUNCATE TABLE "{schema}"."squad_threads" CASCADE')
        await raw.execute(f'TRUNCATE TABLE "{schema}"."query_history" RESTART IDENTITY CASCADE')
        yield raw
    finally:
        await raw.close()


async def _insert_thread(conn: object, *, squad_id: str = "build") -> str:
    schema = _schema()
    thread_id = str(uuid.uuid4())
    await conn.execute(  # type: ignore[attr-defined]
        f"""INSERT INTO "{schema}"."squad_threads"
                (id, workspace_id, squad_id, title)
              VALUES ($1, 'acme', $2, 't')""",
        thread_id,
        squad_id,
    )
    return thread_id


async def _insert_query_history(
    conn: object,
    *,
    cost_usd: float,
    squad_thread_id: str | None = None,
    agent_id: str = "AGENT_A",
    user_id: int = 1,
) -> int:
    schema = _schema()
    return int(
        await conn.fetchval(  # type: ignore[attr-defined]
            f"""INSERT INTO "{schema}"."query_history"
                    (agent_id, user_id, timestamp, query_text, response_text,
                     cost_usd, squad_thread_id)
                  VALUES ($1, $2, $3, 'q', 'r', $4, $5)
                  RETURNING id""",
            agent_id,
            user_id,
            datetime.now(UTC),
            cost_usd,
            squad_thread_id,
        )
    )


async def _thread_cost(conn: object, thread_id: str) -> Decimal:
    schema = _schema()
    raw = await conn.fetchval(  # type: ignore[attr-defined]
        f'SELECT cost_usd_accum FROM "{schema}"."squad_threads" WHERE id = $1',
        thread_id,
    )
    return Decimal(raw)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_insert_with_thread_bumps_cost(conn: object) -> None:
    thread_id = await _insert_thread(conn)
    await _insert_query_history(conn, cost_usd=0.25, squad_thread_id=thread_id)
    cost = await _thread_cost(conn, thread_id)
    assert cost == Decimal("0.25")


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_insert_without_thread_does_not_bump(conn: object) -> None:
    thread_id = await _insert_thread(conn)
    await _insert_query_history(conn, cost_usd=1.50, squad_thread_id=None)
    cost = await _thread_cost(conn, thread_id)
    assert cost == Decimal("0")


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_multiple_inserts_accumulate(conn: object) -> None:
    thread_id = await _insert_thread(conn)
    await _insert_query_history(conn, cost_usd=0.10, squad_thread_id=thread_id)
    await _insert_query_history(conn, cost_usd=0.30, squad_thread_id=thread_id)
    await _insert_query_history(conn, cost_usd=0.05, squad_thread_id=thread_id)
    cost = await _thread_cost(conn, thread_id)
    assert cost == Decimal("0.45")


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_update_cost_applies_delta(conn: object) -> None:
    schema = _schema()
    thread_id = await _insert_thread(conn)
    row_id = await _insert_query_history(conn, cost_usd=0.20, squad_thread_id=thread_id)
    assert await _thread_cost(conn, thread_id) == Decimal("0.20")
    await conn.execute(  # type: ignore[attr-defined]
        f'UPDATE "{schema}"."query_history" SET cost_usd = $1 WHERE id = $2',
        0.50,
        row_id,
    )
    cost = await _thread_cost(conn, thread_id)
    assert cost == Decimal("0.50")  # 0.20 + (0.50 - 0.20)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_relink_thread_refunds_old_and_charges_new(conn: object) -> None:
    schema = _schema()
    a = await _insert_thread(conn, squad_id="build")
    b = await _insert_thread(conn, squad_id="ops")
    row_id = await _insert_query_history(conn, cost_usd=0.40, squad_thread_id=a)
    assert await _thread_cost(conn, a) == Decimal("0.40")
    await conn.execute(  # type: ignore[attr-defined]
        f'UPDATE "{schema}"."query_history" SET squad_thread_id = $1 WHERE id = $2',
        b,
        row_id,
    )
    assert await _thread_cost(conn, a) == Decimal("0")
    assert await _thread_cost(conn, b) == Decimal("0.40")


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_unlinking_thread_refunds(conn: object) -> None:
    schema = _schema()
    thread_id = await _insert_thread(conn)
    row_id = await _insert_query_history(conn, cost_usd=0.75, squad_thread_id=thread_id)
    assert await _thread_cost(conn, thread_id) == Decimal("0.75")
    await conn.execute(  # type: ignore[attr-defined]
        f'UPDATE "{schema}"."query_history" SET squad_thread_id = NULL WHERE id = $1',
        row_id,
    )
    assert await _thread_cost(conn, thread_id) == Decimal("0")
