"""History/session/task state store over the shared primary backend."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from koda.config import AGENT_ID, POD_NAME
from koda.logging_config import get_logger
from koda.state.primary import (
    postgres_primary_mode,
    primary_execute,
    primary_fetch_all,
    primary_fetch_one,
    primary_fetch_val,
    require_primary_state_backend,
    run_coro_sync,
)

log = get_logger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).replace(tzinfo=None).isoformat()


def _current_agent_scope() -> str:
    """Return the canonical agent id used as ``agent_id`` in tasks / sessions.

    Uppercase to match ``cp_agent_definitions.id`` and the writes performed
    by ``audit_events``. The previous lowercase convention caused dashboard
    reads — which derive the scope from the uppercase ``cp_agent_definitions``
    id — to miss every row written from this module, leaving the frontend
    executions/usage panels empty even though the runtime was persisting
    data correctly.
    """
    normalized = str(AGENT_ID or "default").strip().upper()
    return normalized or "DEFAULT"


def _primary_backend() -> Any | None:
    scope = _current_agent_scope()
    if not postgres_primary_mode():
        raise RuntimeError("history_primary_mode_required")
    return require_primary_state_backend(agent_id=scope, error="history_primary_backend_unavailable")


@contextmanager
def _history_backend_removed() -> Iterator[Any]:
    raise RuntimeError("history_compat_backend_removed")
    yield None


def _history_row_from_primary(item: dict[str, Any]) -> tuple[str, str, str, float, str, int]:
    return (
        str(item.get("timestamp") or ""),
        str(item.get("provider") or "claude"),
        str(item.get("model") or ""),
        float(item.get("cost_usd") or 0.0),
        str(item.get("query_text") or ""),
        1 if bool(item.get("error")) else 0,
    )


def _full_history_row_from_primary(item: dict[str, Any]) -> tuple[str, str, str, float, str, str, str, int]:
    return (
        str(item.get("timestamp") or ""),
        str(item.get("provider") or "claude"),
        str(item.get("model") or ""),
        float(item.get("cost_usd") or 0.0),
        str(item.get("query_text") or ""),
        str(item.get("response_text") or ""),
        str(item.get("work_dir") or ""),
        1 if bool(item.get("error")) else 0,
    )


def _task_row_from_primary(item: dict[str, Any] | None) -> tuple[Any, ...] | None:
    if item is None:
        return None
    return (
        item.get("id"),
        item.get("user_id"),
        item.get("chat_id"),
        item.get("status"),
        item.get("query_text"),
        item.get("provider"),
        item.get("model"),
        item.get("work_dir"),
        item.get("attempt"),
        item.get("max_attempts"),
        float(item.get("cost_usd") or 0.0),
        item.get("error_message"),
        item.get("created_at"),
        item.get("started_at"),
        item.get("completed_at"),
        item.get("session_id"),
        item.get("provider_session_id"),
    )


def _user_task_row_from_primary(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item.get("id"),
        item.get("status"),
        item.get("query_text"),
        item.get("provider"),
        item.get("model"),
        float(item.get("cost_usd") or 0.0),
        item.get("error_message"),
        item.get("created_at"),
        item.get("started_at"),
        item.get("completed_at"),
        item.get("attempt"),
        item.get("max_attempts"),
        item.get("work_dir"),
    )


def log_query(
    user_id: int,
    query_text: str,
    response_text: str,
    cost_usd: float,
    model: str,
    session_id: str | None,
    work_dir: str,
    provider: str = "claude",
    provider_session_id: str | None = None,
    usage: dict | None = None,
    error: bool = False,
) -> int:
    """Insert a query record and return its row ID."""
    from koda.services.llm_runner import serialize_usage

    backend = _primary_backend()
    if backend is not None:
        usage_payload: dict[str, Any] = {}
        serialized_usage = serialize_usage(usage)
        try:
            parsed_usage = json.loads(serialized_usage)
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed_usage = {}
        if isinstance(parsed_usage, dict):
            usage_payload = parsed_usage
        row_id = run_coro_sync(
            backend.persist_query_log(
                user_id=user_id,
                timestamp=_now_iso(),
                query_text=query_text,
                response_text=response_text,
                cost_usd=cost_usd,
                provider=provider,
                model=model,
                session_id=session_id,
                provider_session_id=provider_session_id,
                usage=usage_payload,
                work_dir=work_dir,
                error=error,
            )
        )
        if row_id is None:
            raise RuntimeError("primary_query_insert_missing_row_id")
        return int(row_id)

    with _history_backend_removed() as conn:
        cursor = conn.execute(
            """INSERT INTO queries
               (user_id, timestamp, query_text, response_text, cost_usd, provider, model, session_id,
                provider_session_id, usage_json, work_dir, error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                _now_iso(),
                query_text,
                response_text,
                cost_usd,
                provider,
                model,
                session_id,
                provider_session_id,
                serialize_usage(usage),
                work_dir,
                1 if error else 0,
            ),
        )
        row_id = cursor.lastrowid
        if row_id is None:
            raise RuntimeError("compat_query_insert_missing_row_id")
        return int(row_id)


def get_history(user_id: int, limit: int = 10) -> list[tuple[Any, ...]]:
    backend = _primary_backend()
    if backend is not None:
        rows = run_coro_sync(backend.list_query_history(user_id=user_id, limit=limit))
        return [_history_row_from_primary(cast(dict[str, Any], row)) for row in cast(list[dict[str, Any]], rows or [])]
    with _history_backend_removed() as conn:
        return cast(
            list[tuple[Any, ...]],
            conn.execute(
                "SELECT timestamp, provider, model, cost_usd, query_text, error "
                "FROM queries WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall(),
        )


def get_full_history(user_id: int) -> list[tuple[Any, ...]]:
    backend = _primary_backend()
    if backend is not None:
        rows = run_coro_sync(backend.list_full_query_history(user_id=user_id))
        return [
            _full_history_row_from_primary(cast(dict[str, Any], row)) for row in cast(list[dict[str, Any]], rows or [])
        ]
    with _history_backend_removed() as conn:
        return cast(
            list[tuple[Any, ...]],
            conn.execute(
                "SELECT timestamp, provider, model, cost_usd, query_text, response_text, work_dir, error "
                "FROM queries WHERE user_id = ? ORDER BY id ASC",
                (user_id,),
            ).fetchall(),
        )


def add_bookmark(user_id: int, message_text: str) -> int:
    now = _now_iso()
    backend = _primary_backend()
    if backend is not None:
        row_id = run_coro_sync(
            primary_fetch_val(
                "INSERT INTO bookmarks (user_id, message_text, timestamp) VALUES (?, ?, ?) RETURNING id",
                (user_id, message_text, now),
                agent_id=AGENT_ID,
            )
        )
        return int(row_id or 0)
    with _history_backend_removed() as conn:
        cursor = conn.execute(
            "INSERT INTO bookmarks (user_id, message_text, timestamp) VALUES (?, ?, ?)",
            (user_id, message_text, now),
        )
        return int(cursor.lastrowid or 0)


def get_bookmarks(user_id: int, limit: int = 20) -> list[tuple[Any, ...]]:
    backend = _primary_backend()
    if backend is not None:
        rows = run_coro_sync(
            primary_fetch_all(
                "SELECT id, message_text, timestamp FROM bookmarks WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
                agent_id=AGENT_ID,
            )
        )
        return [(row["id"], row["message_text"], row["timestamp"]) for row in rows]
    with _history_backend_removed() as conn:
        return cast(
            list[tuple[Any, ...]],
            conn.execute(
                "SELECT id, message_text, timestamp FROM bookmarks WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall(),
        )


def delete_bookmark(user_id: int, bookmark_id: int) -> bool:
    backend = _primary_backend()
    if backend is not None:
        updated = run_coro_sync(
            primary_execute(
                "DELETE FROM bookmarks WHERE id = ? AND user_id = ?",
                (bookmark_id, user_id),
                agent_id=AGENT_ID,
            )
        )
        return bool(updated)
    with _history_backend_removed() as conn:
        cursor = conn.execute("DELETE FROM bookmarks WHERE id = ? AND user_id = ?", (bookmark_id, user_id))
        return int(getattr(cursor, "rowcount", 0) or 0) > 0


def save_session(
    user_id: int,
    session_id: str,
    name: str | None = None,
    *,
    provider: str = "claude",
    provider_session_id: str | None = None,
    model: str | None = None,
) -> None:
    now = _now_iso()
    backend = _primary_backend()
    if backend is not None:
        existing = run_coro_sync(
            primary_fetch_one(
                "SELECT id FROM sessions WHERE user_id = ? AND session_id = ?",
                (user_id, session_id),
                agent_id=AGENT_ID,
            )
        )
        if existing:
            run_coro_sync(
                primary_execute(
                    "UPDATE sessions SET last_used = ?, provider = ?, "
                    "provider_session_id = COALESCE(?, provider_session_id), "
                    "last_model = COALESCE(?, last_model) WHERE id = ?",
                    (now, provider, provider_session_id, model, existing["id"]),
                    agent_id=AGENT_ID,
                )
            )
        else:
            run_coro_sync(
                primary_execute(
                    "INSERT INTO sessions "
                    "(user_id, session_id, name, provider, provider_session_id, last_model, created_at, last_used) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (user_id, session_id, name, provider, provider_session_id, model, now, now),
                    agent_id=AGENT_ID,
                )
            )
        if provider_session_id:
            run_coro_sync(
                primary_execute(
                    """INSERT INTO provider_session_map
                       (canonical_session_id, provider, provider_session_id, last_model, last_used)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(canonical_session_id, provider) DO UPDATE SET
                           provider_session_id = EXCLUDED.provider_session_id,
                           last_model = EXCLUDED.last_model,
                           last_used = EXCLUDED.last_used""",
                    (session_id, provider, provider_session_id, model, now),
                    agent_id=AGENT_ID,
                )
            )
        return
    with _history_backend_removed() as conn:
        existing = conn.execute(
            "SELECT id FROM sessions WHERE user_id = ? AND session_id = ?",
            (user_id, session_id),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE sessions SET last_used = ?, provider = ?, "
                "provider_session_id = COALESCE(?, provider_session_id), "
                "last_model = COALESCE(?, last_model) WHERE id = ?",
                (now, provider, provider_session_id, model, existing[0]),
            )
        else:
            conn.execute(
                "INSERT INTO sessions "
                "(user_id, session_id, name, provider, provider_session_id, last_model, created_at, last_used) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, session_id, name, provider, provider_session_id, model, now, now),
            )
        if provider_session_id:
            conn.execute(
                """INSERT INTO provider_session_map
                   (canonical_session_id, provider, provider_session_id, last_model, last_used)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(canonical_session_id, provider) DO UPDATE SET
                       provider_session_id = excluded.provider_session_id,
                       last_model = excluded.last_model,
                       last_used = excluded.last_used""",
                (session_id, provider, provider_session_id, model, now),
            )


def get_sessions(user_id: int, limit: int = 20) -> list[tuple[Any, ...]]:
    backend = _primary_backend()
    if backend is not None:
        rows = run_coro_sync(
            primary_fetch_all(
                "SELECT id, session_id, name, provider, last_model, created_at, last_used "
                "FROM sessions WHERE user_id = ? ORDER BY last_used DESC LIMIT ?",
                (user_id, limit),
                agent_id=AGENT_ID,
            )
        )
        return [
            (
                row["id"],
                row["session_id"],
                row.get("name"),
                row.get("provider"),
                row.get("last_model"),
                row.get("created_at"),
                row.get("last_used"),
            )
            for row in rows
        ]
    with _history_backend_removed() as conn:
        return cast(
            list[tuple[Any, ...]],
            conn.execute(
                "SELECT id, session_id, name, provider, last_model, created_at, last_used FROM sessions "
                "WHERE user_id = ? ORDER BY last_used DESC LIMIT ?",
                (user_id, limit),
            ).fetchall(),
        )


def rename_session(user_id: int, session_id: str, name: str) -> bool:
    backend = _primary_backend()
    if backend is not None:
        updated = run_coro_sync(
            primary_execute(
                "UPDATE sessions SET name = ? WHERE user_id = ? AND session_id = ?",
                (name, user_id, session_id),
                agent_id=AGENT_ID,
            )
        )
        return bool(updated)
    with _history_backend_removed() as conn:
        cursor = conn.execute(
            "UPDATE sessions SET name = ? WHERE user_id = ? AND session_id = ?",
            (name, user_id, session_id),
        )
        return int(getattr(cursor, "rowcount", 0) or 0) > 0


def get_session_by_id(user_id: int, row_id: int) -> tuple[Any, ...] | None:
    backend = _primary_backend()
    if backend is not None:
        row = run_coro_sync(
            primary_fetch_one(
                "SELECT session_id, name, provider, last_model FROM sessions WHERE id = ? AND user_id = ?",
                (row_id, user_id),
                agent_id=AGENT_ID,
            )
        )
        if row is None:
            return None
        return (row["session_id"], row.get("name"), row.get("provider"), row.get("last_model"))
    with _history_backend_removed() as conn:
        row = conn.execute(
            "SELECT session_id, name, provider, last_model FROM sessions WHERE id = ? AND user_id = ?",
            (row_id, user_id),
        ).fetchone()
        return cast(tuple[Any, ...] | None, row)


def get_session_runtime_defaults(session_id: str) -> tuple[str | None, str | None] | None:
    """Return the latest provider/model pair observed for a canonical session id."""
    backend = _primary_backend()
    if backend is not None:
        row = run_coro_sync(
            primary_fetch_one(
                """
                SELECT provider, last_model
                  FROM sessions
                 WHERE session_id = ?
              ORDER BY COALESCE(last_used, created_at) DESC, id DESC
                 LIMIT 1
                """,
                (session_id,),
                agent_id=AGENT_ID,
            )
        )
        if row is None:
            return None
        return (cast(str | None, row.get("provider")), cast(str | None, row.get("last_model")))
    with _history_backend_removed() as conn:
        row = conn.execute(
            """
            SELECT provider, last_model
              FROM sessions
             WHERE session_id = ?
          ORDER BY COALESCE(last_used, created_at) DESC, id DESC
             LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        return (cast(str | None, row[0]), cast(str | None, row[1]))


def save_provider_session_mapping(
    canonical_session_id: str,
    provider: str,
    provider_session_id: str,
    last_model: str | None = None,
) -> None:
    now = _now_iso()
    backend = _primary_backend()
    if backend is not None:
        run_coro_sync(
            primary_execute(
                """INSERT INTO provider_session_map
                   (canonical_session_id, provider, provider_session_id, last_model, last_used)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(canonical_session_id, provider) DO UPDATE SET
                       provider_session_id = EXCLUDED.provider_session_id,
                       last_model = EXCLUDED.last_model,
                       last_used = EXCLUDED.last_used""",
                (canonical_session_id, provider, provider_session_id, last_model, now),
                agent_id=AGENT_ID,
            )
        )
        return
    with _history_backend_removed() as conn:
        conn.execute(
            """INSERT INTO provider_session_map
               (canonical_session_id, provider, provider_session_id, last_model, last_used)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(canonical_session_id, provider) DO UPDATE SET
                   provider_session_id = excluded.provider_session_id,
                   last_model = excluded.last_model,
                   last_used = excluded.last_used""",
            (canonical_session_id, provider, provider_session_id, last_model, now),
        )


def delete_provider_session_mapping(canonical_session_id: str, provider: str) -> None:
    backend = _primary_backend()
    if backend is not None:
        run_coro_sync(
            primary_execute(
                "DELETE FROM provider_session_map WHERE canonical_session_id = ? AND provider = ?",
                (canonical_session_id, provider),
                agent_id=AGENT_ID,
            )
        )
        run_coro_sync(
            primary_execute(
                "UPDATE sessions SET provider_session_id = NULL WHERE session_id = ? AND provider = ?",
                (canonical_session_id, provider),
                agent_id=AGENT_ID,
            )
        )
        return
    with _history_backend_removed() as conn:
        conn.execute(
            "DELETE FROM provider_session_map WHERE canonical_session_id = ? AND provider = ?",
            (canonical_session_id, provider),
        )
        conn.execute(
            "UPDATE sessions SET provider_session_id = NULL WHERE session_id = ? AND provider = ?",
            (canonical_session_id, provider),
        )


def get_provider_session_mapping(canonical_session_id: str, provider: str) -> tuple[str, str | None] | None:
    backend = _primary_backend()
    if backend is not None:
        row = run_coro_sync(
            primary_fetch_one(
                "SELECT provider_session_id, last_model FROM provider_session_map "
                "WHERE canonical_session_id = ? AND provider = ?",
                (canonical_session_id, provider),
                agent_id=AGENT_ID,
            )
        )
        if row is not None:
            return (str(row["provider_session_id"]), cast(str | None, row.get("last_model")))
        legacy = run_coro_sync(
            primary_fetch_one(
                "SELECT provider_session_id, last_model FROM sessions WHERE session_id = ? AND provider = ?",
                (canonical_session_id, provider),
                agent_id=AGENT_ID,
            )
        )
        if legacy and legacy.get("provider_session_id"):
            return (str(legacy["provider_session_id"]), cast(str | None, legacy.get("last_model")))
        return None
    try:
        with _history_backend_removed() as conn:
            row = conn.execute(
                "SELECT provider_session_id, last_model "
                "FROM provider_session_map WHERE canonical_session_id = ? AND provider = ?",
                (canonical_session_id, provider),
            ).fetchone()
            if row:
                return cast(tuple[str, str | None], row)
            legacy = conn.execute(
                "SELECT provider_session_id, last_model FROM sessions WHERE session_id = ? AND provider = ?",
                (canonical_session_id, provider),
            ).fetchone()
            if legacy and legacy[0]:
                return cast(tuple[str, str | None], legacy)
            return None
    except Exception:
        return None


def get_recent_session_transcript(user_id: int, session_id: str, limit: int = 10) -> list[tuple[Any, ...]]:
    backend = _primary_backend()
    if backend is not None:
        rows = run_coro_sync(
            primary_fetch_all(
                "SELECT timestamp, provider, model, query_text, response_text FROM queries "
                "WHERE user_id = ? AND session_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, session_id, limit),
                agent_id=AGENT_ID,
            )
        )
        transcript = [
            (
                row.get("timestamp"),
                row.get("provider"),
                row.get("model"),
                row.get("query_text"),
                row.get("response_text"),
            )
            for row in rows
        ]
        return list(reversed(transcript))
    try:
        with _history_backend_removed() as conn:
            rows = conn.execute(
                "SELECT timestamp, provider, model, query_text, response_text FROM queries "
                "WHERE user_id = ? AND session_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, session_id, limit),
            ).fetchall()
        return list(reversed(rows))
    except Exception:
        return []


def get_user_cost(user_id: int) -> tuple[float, int]:
    try:
        backend = _primary_backend()
    except RuntimeError:
        return (0.0, 0)
    if backend is not None:
        row = cast(dict[str, Any] | None, run_coro_sync(backend.get_user_cost_total(user_id=user_id)))
        if row:
            return (float(row.get("total_cost") or 0.0), int(row.get("query_count") or 0))
        return (0.0, 0)
    try:
        with _history_backend_removed() as conn:
            row = conn.execute(
                "SELECT total_cost, query_count FROM user_costs WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if row:
                return (float(row[0] or 0.0), int(row[1] or 0))
    except Exception:
        pass
    return (0.0, 0)


def save_user_cost(user_id: int, total_cost: float, query_count: int) -> None:
    try:
        backend = _primary_backend()
    except RuntimeError:
        return
    if backend is not None:
        run_coro_sync(
            backend.upsert_user_cost_total(
                user_id=user_id,
                total_cost=total_cost,
                query_count=query_count,
                updated_at=_now_iso(),
            )
        )
        return
    try:
        with _history_backend_removed() as conn:
            conn.execute(
                """INSERT INTO user_costs (user_id, total_cost, query_count, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                       total_cost = excluded.total_cost,
                       query_count = excluded.query_count,
                       updated_at = excluded.updated_at""",
                (user_id, total_cost, query_count, _now_iso()),
            )
    except Exception:
        log.warning("save_user_cost_failed", user_id=user_id)


def reset_user_cost(user_id: int) -> None:
    try:
        backend = _primary_backend()
    except RuntimeError:
        return
    if backend is not None:
        run_coro_sync(backend.delete_user_cost_total(user_id=user_id))
        return
    try:
        with _history_backend_removed() as conn:
            conn.execute("DELETE FROM user_costs WHERE user_id = ?", (user_id,))
    except Exception:
        pass


def create_task(
    user_id: int,
    chat_id: int,
    query_text: str,
    provider: str | None = None,
    model: str | None = None,
    session_id: str | None = None,
    provider_session_id: str | None = None,
    work_dir: str | None = None,
    max_attempts: int = 3,
    source_task_id: int | None = None,
    source_action: str | None = None,
) -> int:
    backend = _primary_backend()
    if backend is not None:
        task_id = run_coro_sync(
            primary_fetch_val(
                """INSERT INTO tasks (
                       agent_id, user_id, chat_id, query_text, provider, model, work_dir, max_attempts,
                       created_at, session_id, provider_session_id, source_task_id, source_action
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   RETURNING id""",
                (
                    _current_agent_scope(),
                    user_id,
                    chat_id,
                    query_text,
                    provider,
                    model,
                    work_dir,
                    max_attempts,
                    _now_iso(),
                    session_id,
                    provider_session_id,
                    source_task_id,
                    source_action,
                ),
                agent_id=AGENT_ID,
            )
        )
        return int(task_id or 0)
    with _history_backend_removed() as conn:
        cursor = conn.execute(
            """INSERT INTO tasks
               (user_id, chat_id, query_text, provider, model, work_dir, max_attempts,
                created_at, session_id, provider_session_id, source_task_id, source_action)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                chat_id,
                query_text,
                provider,
                model,
                work_dir,
                max_attempts,
                _now_iso(),
                session_id,
                provider_session_id,
                source_task_id,
                source_action,
            ),
        )
        return int(cursor.lastrowid or 0)


def update_task_status(task_id: int, status: str, **kwargs: object) -> None:
    allowed = {
        "error_message",
        "cost_usd",
        "started_at",
        "completed_at",
        "attempt",
        "session_id",
        "provider_session_id",
        "provider",
        "model",
        "env_id",
        "classification",
        "environment_kind",
        "current_phase",
        "last_heartbeat_at",
        "retention_expires_at",
        "source_task_id",
        "source_action",
    }
    sets = ["status = ?"]
    vals: list[Any] = [status]
    for key, value in kwargs.items():
        if key in allowed:
            sets.append(f"{key} = ?")
            vals.append(value)
    backend = _primary_backend()
    if backend is not None:
        run_coro_sync(
            primary_execute(
                f"UPDATE tasks SET {', '.join(sets)} WHERE agent_id = ? AND id = ?",
                (*vals, _current_agent_scope(), task_id),
                agent_id=AGENT_ID,
            )
        )
        return
    with _history_backend_removed() as conn:
        conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", (*vals, task_id))


def get_user_tasks(user_id: int, limit: int = 10, status: str | None = None) -> list[tuple[Any, ...]]:
    backend = _primary_backend()
    if backend is not None:
        if status:
            rows = run_coro_sync(
                primary_fetch_all(
                    """SELECT id, status, query_text, provider, model, cost_usd, error_message,
                              created_at, started_at, completed_at, attempt, max_attempts, work_dir
                       FROM tasks
                       WHERE agent_id = ? AND user_id = ? AND status = ?
                       ORDER BY id DESC LIMIT ?""",
                    (_current_agent_scope(), user_id, status, limit),
                    agent_id=AGENT_ID,
                )
            )
        else:
            rows = run_coro_sync(
                primary_fetch_all(
                    """SELECT id, status, query_text, provider, model, cost_usd, error_message,
                              created_at, started_at, completed_at, attempt, max_attempts, work_dir
                       FROM tasks
                       WHERE agent_id = ? AND user_id = ?
                       ORDER BY id DESC LIMIT ?""",
                    (_current_agent_scope(), user_id, limit),
                    agent_id=AGENT_ID,
                )
            )
        return [_user_task_row_from_primary(row) for row in rows]
    with _history_backend_removed() as conn:
        if status:
            return cast(
                list[tuple[Any, ...]],
                conn.execute(
                    "SELECT id, status, query_text, provider, model, cost_usd, error_message, "
                    "created_at, started_at, completed_at, attempt, max_attempts, work_dir "
                    "FROM tasks WHERE user_id = ? AND status = ? ORDER BY id DESC LIMIT ?",
                    (user_id, status, limit),
                ).fetchall(),
            )
        return cast(
            list[tuple[Any, ...]],
            conn.execute(
                "SELECT id, status, query_text, provider, model, cost_usd, error_message, "
                "created_at, started_at, completed_at, attempt, max_attempts, work_dir "
                "FROM tasks WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall(),
        )


def get_task(task_id: int) -> tuple[Any, ...] | None:
    backend = _primary_backend()
    if backend is not None:
        row = run_coro_sync(
            primary_fetch_one(
                """SELECT id, user_id, chat_id, status, query_text, provider, model, work_dir, attempt, max_attempts,
                          cost_usd, error_message, created_at, started_at, completed_at, session_id, provider_session_id
                   FROM tasks WHERE agent_id = ? AND id = ?""",
                (_current_agent_scope(), task_id),
                agent_id=AGENT_ID,
            )
        )
        return _task_row_from_primary(row)
    with _history_backend_removed() as conn:
        row = conn.execute(
            "SELECT id, user_id, chat_id, status, query_text, provider, model, work_dir, attempt, max_attempts, "
            "cost_usd, error_message, created_at, started_at, completed_at, session_id, provider_session_id "
            "FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        return cast(tuple[Any, ...] | None, row)


def list_pending_tasks_for_recovery(limit: int | None = None) -> list[dict[str, Any]]:
    """Return queued/running/retrying tasks that should be considered for queue recovery."""
    query = (
        "SELECT id, user_id, chat_id, status, query_text, provider, model, work_dir, attempt, max_attempts, "
        "error_message, created_at, started_at, completed_at, session_id, provider_session_id, "
        "source_task_id, source_action "
        "FROM tasks WHERE agent_id = ? AND status IN ('queued', 'running', 'retrying') ORDER BY created_at ASC"
    )
    params: list[Any] = [_current_agent_scope()]
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    backend = _primary_backend()
    if backend is not None:
        rows = run_coro_sync(primary_fetch_all(query, tuple(params), agent_id=AGENT_ID))
        return [dict(row) for row in rows]
    with _history_backend_removed() as conn:
        legacy_query = (
            "SELECT id, user_id, chat_id, status, query_text, provider, model, work_dir, attempt, max_attempts, "
            "error_message, created_at, started_at, completed_at, session_id, provider_session_id, "
            "source_task_id, source_action "
            "FROM tasks WHERE status IN ('queued', 'running', 'retrying') ORDER BY created_at ASC"
        )
        legacy_params: list[Any] = []
        if limit is not None:
            legacy_query += " LIMIT ?"
            legacy_params.append(limit)
        rows = conn.execute(legacy_query, tuple(legacy_params)).fetchall()
    return [
        {
            "id": row[0],
            "user_id": row[1],
            "chat_id": row[2],
            "status": row[3],
            "query_text": row[4],
            "provider": row[5],
            "model": row[6],
            "work_dir": row[7],
            "attempt": row[8],
            "max_attempts": row[9],
            "error_message": row[10],
            "created_at": row[11],
            "started_at": row[12],
            "completed_at": row[13],
            "session_id": row[14],
            "provider_session_id": row[15],
            "source_task_id": row[16],
            "source_action": row[17],
        }
        for row in rows
    ]


def mark_stale_tasks_failed() -> int:
    backend = _primary_backend()
    if backend is not None:
        updated = run_coro_sync(
            primary_execute(
                """UPDATE tasks
                   SET status = 'failed', error_message = 'agent reiniciado', completed_at = ?
                   WHERE agent_id = ? AND status IN ('queued', 'running', 'retrying')""",
                (_now_iso(), _current_agent_scope()),
                agent_id=AGENT_ID,
            )
        )
        return int(updated or 0)
    with _history_backend_removed() as conn:
        cursor = conn.execute(
            "UPDATE tasks SET status = 'failed', error_message = 'agent reiniciado', completed_at = ? "
            "WHERE status IN ('queued', 'running', 'retrying')",
            (_now_iso(),),
        )
        return int(cursor.rowcount)


def dlq_insert(
    task_id: int,
    user_id: int,
    chat_id: int,
    query_text: str,
    error_message: str | None = None,
    error_class: str | None = None,
    attempt_count: int = 0,
    model: str | None = None,
    original_created_at: str | None = None,
    metadata_json: str = "{}",
) -> int | None:
    try:
        backend = _primary_backend()
        if backend is not None:
            row_id = run_coro_sync(
                primary_fetch_val(
                    """INSERT INTO dead_letter_queue
                       (task_id, user_id, chat_id, agent_id, pod_name, query_text, model,
                        error_message, error_class, attempt_count, original_created_at,
                        failed_at, metadata_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       RETURNING id""",
                    (
                        task_id,
                        user_id,
                        chat_id,
                        AGENT_ID,
                        POD_NAME,
                        query_text,
                        model,
                        error_message,
                        error_class,
                        attempt_count,
                        original_created_at,
                        _now_iso(),
                        metadata_json,
                    ),
                    agent_id=AGENT_ID,
                )
            )
            return int(row_id) if row_id is not None else None
        with _history_backend_removed() as conn:
            cursor = conn.execute(
                """INSERT INTO dead_letter_queue
                   (task_id, user_id, chat_id, agent_id, pod_name, query_text, model,
                    error_message, error_class, attempt_count, original_created_at,
                    failed_at, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_id,
                    user_id,
                    chat_id,
                    AGENT_ID,
                    POD_NAME,
                    query_text,
                    model,
                    error_message,
                    error_class,
                    attempt_count,
                    original_created_at,
                    _now_iso(),
                    metadata_json,
                ),
            )
            return int(cursor.lastrowid) if cursor.lastrowid is not None else None
    except Exception:
        log.warning("dlq_insert_failed", task_id=task_id)
        return None


def dlq_list(limit: int = 20, retry_eligible: bool | None = None) -> list[tuple[Any, ...]]:
    try:
        backend = _primary_backend()
        if backend is not None:
            if retry_eligible is not None:
                rows = run_coro_sync(
                    primary_fetch_all(
                        "SELECT id, task_id, user_id, chat_id, query_text, error_message, "
                        "attempt_count, failed_at, retry_eligible "
                        "FROM dead_letter_queue WHERE retry_eligible = ? ORDER BY id DESC LIMIT ?",
                        (retry_eligible, limit),
                        agent_id=AGENT_ID,
                    )
                )
            else:
                rows = run_coro_sync(
                    primary_fetch_all(
                        "SELECT id, task_id, user_id, chat_id, query_text, error_message, "
                        "attempt_count, failed_at, retry_eligible "
                        "FROM dead_letter_queue ORDER BY id DESC LIMIT ?",
                        (limit,),
                        agent_id=AGENT_ID,
                    )
                )
            return [
                (
                    row["id"],
                    row["task_id"],
                    row["user_id"],
                    row["chat_id"],
                    row["query_text"],
                    row.get("error_message"),
                    row.get("attempt_count"),
                    row.get("failed_at"),
                    row.get("retry_eligible"),
                )
                for row in rows
            ]
        with _history_backend_removed() as conn:
            if retry_eligible is not None:
                return cast(
                    list[tuple[Any, ...]],
                    conn.execute(
                        "SELECT id, task_id, user_id, chat_id, query_text, error_message, "
                        "attempt_count, failed_at, retry_eligible "
                        "FROM dead_letter_queue WHERE retry_eligible = ? ORDER BY id DESC LIMIT ?",
                        (1 if retry_eligible else 0, limit),
                    ).fetchall(),
                )
            return cast(
                list[tuple[Any, ...]],
                conn.execute(
                    "SELECT id, task_id, user_id, chat_id, query_text, error_message, "
                    "attempt_count, failed_at, retry_eligible "
                    "FROM dead_letter_queue ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall(),
            )
    except Exception:
        return []


def dlq_get_dict(dlq_id: int) -> dict[str, Any] | None:
    columns = [
        "id",
        "task_id",
        "user_id",
        "chat_id",
        "agent_id",
        "pod_name",
        "query_text",
        "model",
        "error_message",
        "error_class",
        "attempt_count",
        "original_created_at",
        "failed_at",
        "retry_eligible",
        "retried_at",
        "metadata_json",
    ]
    try:
        backend = _primary_backend()
        if backend is not None:
            row = run_coro_sync(
                primary_fetch_one(
                    "SELECT id, task_id, user_id, chat_id, agent_id, pod_name, query_text, model, "
                    "error_message, error_class, attempt_count, original_created_at, failed_at, "
                    "retry_eligible, retried_at, metadata_json "
                    "FROM dead_letter_queue WHERE id = ?",
                    (dlq_id,),
                    agent_id=AGENT_ID,
                )
            )
            if row is None:
                return None
            return {key: row.get(key) for key in columns}
        with _history_backend_removed() as conn:
            row = conn.execute(
                "SELECT id, task_id, user_id, chat_id, agent_id, pod_name, query_text, model, "
                "error_message, error_class, attempt_count, original_created_at, failed_at, "
                "retry_eligible, retried_at, metadata_json "
                "FROM dead_letter_queue WHERE id = ?",
                (dlq_id,),
            ).fetchone()
        return dict(zip(columns, row, strict=False)) if row else None
    except Exception:
        return None


def dlq_mark_retried(dlq_id: int, *, metadata_json: str | None = None) -> bool:
    try:
        backend = _primary_backend()
        if backend is not None:
            if metadata_json is not None:
                updated = run_coro_sync(
                    primary_execute(
                        "UPDATE dead_letter_queue "
                        "SET retry_eligible = FALSE, retried_at = ?, metadata_json = ? WHERE id = ?",
                        (_now_iso(), metadata_json, dlq_id),
                        agent_id=AGENT_ID,
                    )
                )
                return bool(updated)
            updated = run_coro_sync(
                primary_execute(
                    "UPDATE dead_letter_queue SET retry_eligible = FALSE, retried_at = ? WHERE id = ?",
                    (_now_iso(), dlq_id),
                    agent_id=AGENT_ID,
                )
            )
            return bool(updated)
        with _history_backend_removed() as conn:
            if metadata_json is not None:
                cursor = conn.execute(
                    "UPDATE dead_letter_queue SET retry_eligible = 0, retried_at = ?, metadata_json = ? WHERE id = ?",
                    (_now_iso(), metadata_json, dlq_id),
                )
                return int(getattr(cursor, "rowcount", 0) or 0) > 0
            cursor = conn.execute(
                "UPDATE dead_letter_queue SET retry_eligible = 0, retried_at = ? WHERE id = ?",
                (_now_iso(), dlq_id),
            )
            return int(getattr(cursor, "rowcount", 0) or 0) > 0
    except Exception:
        return False


def run_maintenance() -> dict[str, Any]:
    cutoff = (datetime.now(UTC).replace(tzinfo=None) - timedelta(days=90)).isoformat()
    result: dict[str, Any] = {}
    backend = _primary_backend()
    if backend is not None:
        try:
            result["queries_deleted"] = int(
                run_coro_sync(
                    primary_execute(
                        "DELETE FROM queries WHERE timestamp < ?",
                        (cutoff,),
                        agent_id=AGENT_ID,
                    )
                )
                or 0
            )
            result["audit_log_deleted"] = int(
                run_coro_sync(
                    primary_execute(
                        "DELETE FROM audit_log WHERE timestamp < ?",
                        (cutoff,),
                        agent_id=AGENT_ID,
                    )
                )
                or 0
            )
            result["mode"] = "primary"
        except Exception as exc:  # noqa: BLE001
            log.warning("db_maintenance_error", error=str(exc))
            result["error"] = str(exc)
        return result

    try:
        with _history_backend_removed() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            result["wal_checkpoint"] = "ok"
            row = conn.execute("PRAGMA integrity_check").fetchone()
            result["integrity_check"] = row[0] if row else "unknown"
            result["audit_log_deleted"] = conn.execute("DELETE FROM audit_log WHERE timestamp < ?", (cutoff,)).rowcount
            result["queries_deleted"] = conn.execute("DELETE FROM queries WHERE timestamp < ?", (cutoff,)).rowcount
    except Exception as exc:  # noqa: BLE001
        log.warning("db_maintenance_error", error=str(exc))
        result["error"] = str(exc)
    return result
