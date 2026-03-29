"""Helpers for the Postgres-first primary state path."""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime
from typing import Any, cast

import koda.config as config_module

_BRIDGE_LOOP: asyncio.AbstractEventLoop | None = None
_BRIDGE_THREAD: threading.Thread | None = None
_BRIDGE_LOCK = threading.Lock()


def _ensure_bridge_loop() -> asyncio.AbstractEventLoop:
    global _BRIDGE_LOOP, _BRIDGE_THREAD

    with _BRIDGE_LOCK:
        if _BRIDGE_LOOP is not None and _BRIDGE_THREAD is not None and _BRIDGE_THREAD.is_alive():
            return _BRIDGE_LOOP

        ready = threading.Event()

        def _runner() -> None:
            global _BRIDGE_LOOP

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            with _BRIDGE_LOCK:
                _BRIDGE_LOOP = loop
            ready.set()
            loop.run_forever()

        thread = threading.Thread(target=_runner, daemon=True, name="primary-state-bridge")
        _BRIDGE_THREAD = thread
        thread.start()

    ready.wait()
    if _BRIDGE_LOOP is None:  # pragma: no cover - defensive initialization guard
        raise RuntimeError("primary_state_bridge_unavailable")
    return _BRIDGE_LOOP


def postgres_primary_mode() -> bool:
    """Return whether the runtime should avoid legacy local SQLite state."""
    return config_module.STATE_BACKEND == "postgres"


def get_primary_state_backend(*, agent_id: str | None = None) -> Any | None:
    """Return the shared Postgres backend when primary state mode is active."""
    if not postgres_primary_mode():
        return None
    from koda.knowledge.config import (
        KNOWLEDGE_V2_EMBEDDING_DIMENSION,
        KNOWLEDGE_V2_POSTGRES_DSN,
        KNOWLEDGE_V2_POSTGRES_SCHEMA,
    )
    from koda.knowledge.v2.common import get_shared_postgres_backend

    backend = get_shared_postgres_backend(
        agent_id=agent_id or config_module.AGENT_ID,
        dsn=KNOWLEDGE_V2_POSTGRES_DSN,
        schema=KNOWLEDGE_V2_POSTGRES_SCHEMA,
        embedding_dimension=KNOWLEDGE_V2_EMBEDDING_DIMENSION,
    )
    return backend if backend.enabled else None


def require_primary_state_backend(*, agent_id: str | None = None, error: str) -> Any:
    """Return the primary backend or raise when postgres-primary mode is required."""
    backend = get_primary_state_backend(agent_id=agent_id)
    if backend is None and postgres_primary_mode():
        raise RuntimeError(error)
    return backend


def run_coro_sync(coro: Any) -> Any:
    """Run an async primary-backend operation from sync callers."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    bridge_loop = _ensure_bridge_loop()
    future = asyncio.run_coroutine_threadsafe(coro, bridge_loop)
    return future.result()


def _normalize_qmark_placeholders(query: str) -> str:
    index = 0
    chunks: list[str] = []
    for char in query:
        if char == "?":
            index += 1
            chunks.append(f"${index}")
        else:
            chunks.append(char)
    return "".join(chunks)


def _normalize_primary_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_normalize_primary_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_normalize_primary_value(item) for item in value)
    if isinstance(value, dict):
        return {str(key): _normalize_primary_value(item) for key, item in value.items()}
    return value


async def primary_fetch_all(
    query: str,
    params: tuple[Any, ...] | list[Any] = (),
    *,
    agent_id: str | None = None,
) -> list[dict[str, Any]]:
    backend = get_primary_state_backend(agent_id=agent_id)
    if backend is None:
        return []
    async with backend._connection() as conn:  # noqa: SLF001 - controlled shared backend bridge
        await conn.execute(f'SET search_path TO "{backend.schema}"')
        rows = await conn.fetch(_normalize_qmark_placeholders(query), *tuple(params))
    return [_normalize_primary_value(dict(row)) for row in rows]


async def primary_fetch_one(
    query: str,
    params: tuple[Any, ...] | list[Any] = (),
    *,
    agent_id: str | None = None,
) -> dict[str, Any] | None:
    backend = get_primary_state_backend(agent_id=agent_id)
    if backend is None:
        return None
    async with backend._connection() as conn:  # noqa: SLF001 - controlled shared backend bridge
        await conn.execute(f'SET search_path TO "{backend.schema}"')
        row = await conn.fetchrow(_normalize_qmark_placeholders(query), *tuple(params))
    if row is None:
        return None
    return cast(dict[str, Any], _normalize_primary_value(dict(row)))


async def primary_fetch_val(
    query: str,
    params: tuple[Any, ...] | list[Any] = (),
    *,
    agent_id: str | None = None,
) -> Any:
    backend = get_primary_state_backend(agent_id=agent_id)
    if backend is None:
        return None
    async with backend._connection() as conn:  # noqa: SLF001 - controlled shared backend bridge
        await conn.execute(f'SET search_path TO "{backend.schema}"')
        value = await conn.fetchval(_normalize_qmark_placeholders(query), *tuple(params))
    return _normalize_primary_value(value)


async def primary_execute(
    query: str,
    params: tuple[Any, ...] | list[Any] = (),
    *,
    agent_id: str | None = None,
) -> int:
    backend = get_primary_state_backend(agent_id=agent_id)
    if backend is None:
        return 0
    async with backend._connection() as conn:  # noqa: SLF001 - controlled shared backend bridge
        await conn.execute(f'SET search_path TO "{backend.schema}"')
        status = await conn.execute(_normalize_qmark_placeholders(query), *tuple(params))
    try:
        return int(str(status).rsplit(" ", 1)[-1])
    except (TypeError, ValueError):
        return 0
