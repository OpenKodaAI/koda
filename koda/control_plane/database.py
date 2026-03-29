"""Compatibility adapter that re-exports control-plane store helpers."""

from __future__ import annotations

from typing import Any

from koda.state import control_plane_store as _store

STATE_BACKEND = _store.STATE_BACKEND
get_primary_state_backend = _store.get_primary_state_backend
primary_execute = _store.primary_execute
primary_fetch_all = _store.primary_fetch_all
primary_fetch_one = _store.primary_fetch_one
primary_fetch_val = _store.primary_fetch_val
run_coro_sync = _store.run_coro_sync
_connect = _store._connect


def _sync_store_overrides() -> None:
    _store.STATE_BACKEND = STATE_BACKEND
    _store.get_primary_state_backend = get_primary_state_backend
    _store.primary_execute = primary_execute
    _store.primary_fetch_all = primary_fetch_all
    _store.primary_fetch_one = primary_fetch_one
    _store.primary_fetch_val = primary_fetch_val
    _store.run_coro_sync = run_coro_sync
    _store._connect = _connect


def init_control_plane_db() -> None:
    _sync_store_overrides()
    _store.init_control_plane_db()


def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[Any]:
    _sync_store_overrides()
    return _store.fetch_all(query, params)


def fetch_one(query: str, params: tuple[Any, ...] = ()) -> Any | None:
    _sync_store_overrides()
    return _store.fetch_one(query, params)


def execute(query: str, params: tuple[Any, ...] = ()) -> int:
    _sync_store_overrides()
    return _store.execute(query, params)


def execute_many(query: str, items: list[tuple[Any, ...]]) -> None:
    _sync_store_overrides()
    _store.execute_many(query, items)


def with_connection(fn: Any) -> Any:
    _sync_store_overrides()
    return _store.with_connection(fn)


def json_load(value: str | None, default: Any) -> Any:
    return _store.json_load(value, default)


def json_dump(value: Any) -> str:
    return _store.json_dump(value)


def now_iso() -> str:
    return _store.now_iso()


__all__ = [
    "STATE_BACKEND",
    "get_primary_state_backend",
    "primary_execute",
    "primary_fetch_all",
    "primary_fetch_one",
    "primary_fetch_val",
    "run_coro_sync",
    "_connect",
    "execute",
    "execute_many",
    "fetch_all",
    "fetch_one",
    "init_control_plane_db",
    "json_dump",
    "json_load",
    "now_iso",
    "with_connection",
]
