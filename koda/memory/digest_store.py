"""Digest preference CRUD over the primary backend."""

from __future__ import annotations

from typing import Any, cast

from koda.state.agent_scope import normalize_agent_scope
from koda.state.primary import require_primary_state_backend, run_coro_sync


def _primary_backend(agent_id: str | None = None) -> Any:
    return require_primary_state_backend(
        agent_id=normalize_agent_scope(agent_id),
        error="digest preferences require the primary state backend",
    )


def _tuple_from_row(row: dict[str, Any] | None) -> tuple | None:
    if row is None:
        return None
    return (
        int(row.get("user_id") or 0),
        int(row.get("chat_id") or 0),
        1 if bool(row.get("enabled")) else 0,
        int(row.get("send_hour") or 0),
        int(row.get("send_minute") or 0),
        str(row.get("timezone") or "UTC"),
        row.get("last_sent_date"),
    )


def set_preference(
    user_id: int,
    chat_id: int,
    enabled: bool = True,
    send_hour: int = 9,
    send_minute: int = 0,
    timezone: str = "UTC",
) -> None:
    backend = _primary_backend()
    run_coro_sync(
        backend.upsert_digest_preference(
            user_id=user_id,
            chat_id=chat_id,
            enabled=enabled,
            send_hour=send_hour,
            send_minute=send_minute,
            timezone=timezone,
        )
    )


def get_preference(user_id: int) -> tuple | None:
    backend = _primary_backend()
    row = cast(dict[str, Any] | None, run_coro_sync(backend.get_digest_preference(user_id=user_id)))
    return _tuple_from_row(row)


def get_all_enabled() -> list[tuple]:
    backend = _primary_backend()
    rows = cast(list[dict[str, Any]], run_coro_sync(backend.list_enabled_digest_preferences()) or [])
    return [cast(tuple, _tuple_from_row(row)) for row in rows if _tuple_from_row(row) is not None]


def mark_sent(user_id: int, date_str: str) -> None:
    backend = _primary_backend()
    run_coro_sync(backend.mark_digest_sent(user_id=user_id, date_str=date_str))


def delete_preference(user_id: int) -> bool:
    backend = _primary_backend()
    return bool(run_coro_sync(backend.delete_digest_preference(user_id=user_id)))
