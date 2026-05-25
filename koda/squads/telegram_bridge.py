"""Squad ↔ Telegram binding service.

Maps a squad to a Telegram supergroup. Each binding is a single
``(squad_id, telegram_chat_id)`` row; both sides are unique so a chat hosts
at most one squad and a squad lives in at most one chat. Phase 5 wiring
(``koda/handlers/`` + ``koda/__main__.py``) reads this table on every
inbound supergroup message to resolve the squad and dispatch.
"""

from __future__ import annotations

import json
import re
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from koda.logging_config import get_logger

log = get_logger(__name__)

_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class TelegramBindingConflictError(RuntimeError):
    """The Telegram chat is already bound to a different squad and ``force`` is False."""


@dataclass
class SquadTelegramBinding:
    squad_id: str
    telegram_chat_id: int
    chat_title: str
    is_forum: bool
    bound_by_user_id: int | None
    bound_at: datetime | None
    updated_at: datetime | None
    metadata: dict[str, Any] = field(default_factory=dict)


def _decode_metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            data = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}
    if isinstance(value, dict):
        return value
    return {}


def _row_to_binding(row: Any) -> SquadTelegramBinding:
    return SquadTelegramBinding(
        squad_id=row["squad_id"],
        telegram_chat_id=int(row["telegram_chat_id"]),
        chat_title=row["chat_title"] or "",
        is_forum=bool(row["is_forum"]),
        bound_by_user_id=row["bound_by_user_id"],
        bound_at=row["bound_at"],
        updated_at=row["updated_at"],
        metadata=_decode_metadata(row["metadata_json"]),
    )


class SquadTelegramBindingService:
    def __init__(
        self,
        *,
        dsn: str,
        schema: str = "knowledge_v2",
        pool_min_size: int = 1,
        pool_max_size: int = 4,
    ) -> None:
        if not _SCHEMA_RE.match(schema):
            raise ValueError(f"invalid postgres schema name: {schema!r}")
        self._dsn = dsn
        self._schema = schema
        self._pool_min_size = max(1, int(pool_min_size))
        self._pool_max_size = max(self._pool_min_size, int(pool_max_size))
        self._pool: Any | None = None

    async def _ensure_pool(self) -> Any:
        if self._pool is None:
            import asyncpg  # type: ignore[import-not-found]

            self._pool = await asyncpg.create_pool(
                self._dsn,
                min_size=self._pool_min_size,
                max_size=self._pool_max_size,
            )
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            with suppress(Exception):
                await self._pool.close()
            self._pool = None

    async def bind(
        self,
        *,
        squad_id: str,
        telegram_chat_id: int,
        chat_title: str = "",
        is_forum: bool = False,
        bound_by_user_id: int | None = None,
        force: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> SquadTelegramBinding:
        if not squad_id:
            raise ValueError("squad_id is required")
        chat_id = int(telegram_chat_id)
        pool = await self._ensure_pool()
        async with pool.acquire() as conn, conn.transaction():
            existing_for_chat = await conn.fetchrow(
                f'SELECT * FROM "{self._schema}"."squad_telegram_bindings" WHERE telegram_chat_id = $1 FOR UPDATE',
                chat_id,
            )
            if existing_for_chat is not None and existing_for_chat["squad_id"] != squad_id and not force:
                raise TelegramBindingConflictError(
                    f"telegram chat {chat_id} is already bound to squad "
                    f"{existing_for_chat['squad_id']!r}; pass force=True to replace"
                )
            # If forcing over a different squad's chat, drop their binding first
            # so the UNIQUE(telegram_chat_id) index does not block the upsert.
            if existing_for_chat is not None and existing_for_chat["squad_id"] != squad_id and force:
                await conn.execute(
                    f'DELETE FROM "{self._schema}"."squad_telegram_bindings" WHERE squad_id = $1',
                    existing_for_chat["squad_id"],
                )
            row = await conn.fetchrow(
                f"""INSERT INTO "{self._schema}"."squad_telegram_bindings"
                        (squad_id, telegram_chat_id, chat_title, is_forum,
                         bound_by_user_id, metadata_json)
                      VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                      ON CONFLICT (squad_id) DO UPDATE SET
                          telegram_chat_id = EXCLUDED.telegram_chat_id,
                          chat_title = EXCLUDED.chat_title,
                          is_forum = EXCLUDED.is_forum,
                          bound_by_user_id = EXCLUDED.bound_by_user_id,
                          metadata_json = EXCLUDED.metadata_json,
                          updated_at = NOW()
                      RETURNING *""",
                squad_id,
                chat_id,
                chat_title or "",
                bool(is_forum),
                bound_by_user_id,
                json.dumps(metadata or {}),
            )
        return _row_to_binding(row)

    async def unbind(self, *, squad_id: str) -> bool:
        if not squad_id:
            raise ValueError("squad_id is required")
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                f'DELETE FROM "{self._schema}"."squad_telegram_bindings" WHERE squad_id = $1',
                squad_id,
            )
        if isinstance(result, str):
            parts = result.split()
            with suppress(ValueError):
                return int(parts[-1]) > 0
        return False

    async def get_for_squad(self, squad_id: str) -> SquadTelegramBinding | None:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f'SELECT * FROM "{self._schema}"."squad_telegram_bindings" WHERE squad_id = $1',
                squad_id,
            )
        return _row_to_binding(row) if row is not None else None

    async def get_for_chat(self, telegram_chat_id: int) -> SquadTelegramBinding | None:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f'SELECT * FROM "{self._schema}"."squad_telegram_bindings" WHERE telegram_chat_id = $1',
                int(telegram_chat_id),
            )
        return _row_to_binding(row) if row is not None else None


_service: SquadTelegramBindingService | None = None


def _build_service() -> SquadTelegramBindingService | None:
    from koda.config import POSTGRES_URL
    from koda.knowledge.config import KNOWLEDGE_V2_POSTGRES_SCHEMA

    if not POSTGRES_URL:
        return None
    schema = (KNOWLEDGE_V2_POSTGRES_SCHEMA or "knowledge_v2").strip() or "knowledge_v2"
    return SquadTelegramBindingService(dsn=POSTGRES_URL, schema=schema)


def get_telegram_binding_service() -> SquadTelegramBindingService | None:
    """Return the singleton binding service, or None if no Postgres DSN is configured."""
    global _service  # noqa: PLW0603
    if _service is None:
        _service = _build_service()
    return _service
