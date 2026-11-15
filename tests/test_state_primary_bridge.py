"""Tests for the primary-state bridge loop and shared asyncpg pool isolation.

Covers two related hardening fixes:

1. ``run_coro_sync`` must always route through the persistent bridge loop.
   The previous implementation used ``asyncio.run(coro)`` when no loop was
   running — that creates and closes a transient loop every call, leaving
   asyncpg pools pinned to a dead loop in the shared backend cache. The
   next operation raised ``InterfaceError: cannot perform operation: another
   operation is in progress`` or ``ConnectionDoesNotExistError``.

2. Both the bridge loop and the shared-backend cache must detect process
   hops (a parent cache must not be reused in a child PID). ``subprocess_exec``
   already re-imports modules, but any future fork-based spawn would silently
   reuse the parent's event-loop-bound pool.
"""

from __future__ import annotations

import asyncio
import os
import threading


def test_run_coro_sync_works_without_running_loop() -> None:
    """Sync-only callers can invoke run_coro_sync; the coroutine runs and
    returns its value without requiring a pre-existing event loop.
    """
    import koda.state.primary as sp

    async def _probe() -> str:
        return "ok"

    # Ensure no ambient running loop.
    try:
        asyncio.get_running_loop()
        has_loop = True
    except RuntimeError:
        has_loop = False
    assert not has_loop, "test precondition: caller must not be inside a running loop"

    assert sp.run_coro_sync(_probe()) == "ok"


def test_redacted_json_returns_string_for_text_column_storage() -> None:
    """``*_json`` columns in the runtime schema are TEXT. asyncpg would
    reject a dict with ``DataError: expected str, got dict``. The
    ``_redacted_json`` helper must therefore return the serialized string,
    not the parsed object.
    """
    from koda.services.runtime import postgres_store

    assert isinstance(postgres_store._redacted_json({"a": 1, "b": [1, 2]}), str)
    assert isinstance(postgres_store._redacted_json([1, 2, 3]), str)
    assert isinstance(postgres_store._redacted_json(None), str)


def test_bulk_update_runtime_queue_items_casts_task_id_bigint() -> None:
    """The VALUES clause of ``bulk_update_runtime_queue_items`` must
    declare ``task_id`` as ``bigint`` so the ``WHERE target.task_id =
    source.task_id`` join doesn't fail with ``operator does not exist:
    bigint = text``. Postgres treats un-annotated VALUES columns as TEXT.
    """
    import inspect

    from koda.services.runtime import postgres_store

    src = inspect.getsource(postgres_store.PostgresRuntimeStore.bulk_update_runtime_queue_items)
    assert "::bigint" in src, "task_id VALUES column must be cast to bigint"


def test_audit_run_coro_sync_delegates_to_primary() -> None:
    """Audit inserts must reuse the canonical ``state.primary.run_coro_sync``
    so the shared asyncpg pool cache reset happens around each transient
    ``asyncio.run`` boundary. A separate bridge would leave the pool pinned
    to a closed loop → ``InterfaceError`` on the next insert.
    """
    import inspect

    from koda.services import audit

    src = inspect.getsource(audit._run_coro_sync)
    assert "run_coro_sync" in src
    # The old implementation spun its own Thread. That approach bypassed the
    # pool reset — guard against regressing.
    assert "threading.Thread" not in src


def test_history_store_scope_matches_cp_agent_definitions_case(monkeypatch) -> None:
    """``tasks.agent_id`` must match ``cp_agent_definitions.id`` (uppercase)
    so the dashboard joins don't silently return zero rows. A prior lowercase
    convention caused the executions screen to show "no data" even though
    the runtime was persisting tasks — the SQL just never matched.
    """
    monkeypatch.setattr("koda.state.history_store.AGENT_ID", "PIXIE_COPY")
    from koda.state.history_store import _current_agent_scope

    assert _current_agent_scope() == "PIXIE_COPY"


def test_dashboard_parse_iso_returns_tz_aware_for_naive_input() -> None:
    """``_parse_iso`` must coerce naive ISO strings to UTC-aware datetimes
    so arithmetic (e.g. duration = completed - started) doesn't raise
    ``TypeError: can't subtract offset-naive and offset-aware datetimes``
    when mixing rows persisted in different tz formats.
    """
    from datetime import UTC

    from koda.control_plane.dashboard_service import _parse_iso

    naive = _parse_iso("2026-04-21T01:36:55.665619")
    aware = _parse_iso("2026-04-21T01:41:20.834457+00:00")
    assert naive is not None and naive.tzinfo is UTC
    assert aware is not None and aware.tzinfo is not None
    # Subtraction must work — this was raising before the fix.
    delta = aware - naive
    assert delta.total_seconds() > 0


def test_build_recovered_raw_item_preserves_marker_for_empty_payload() -> None:
    """Persisted ``payload_json`` defaults to ``"{}"`` (empty dict) when the
    original enqueue hit the asyncpg error we fixed. On recovery the old
    code path popped ``_recovered_task`` for ``payload is not None`` — which
    matches ``{}`` — so the resulting dict had no ``_user_message`` /
    ``_recovered_task`` marker. ``_parse_queue_item`` then fell through to
    ``update, query_text = item`` and raised ``ValueError: too many values
    to unpack (expected 2)``.

    Guard the rebuild so empty payloads still route through the recovered
    branch with the marker intact.
    """
    from koda.services.queue_manager import _build_recovered_raw_item

    task_row = {
        "id": 42,
        "user_id": 8509575891,
        "chat_id": 8509575891,
        "query_text": "Olá",
        "provider": "ollama",
        "model": "qwen3.5:9b",
        "work_dir": None,
        "session_id": None,
    }

    # Empty persisted payload ({}) — previously triggered the bug.
    raw = _build_recovered_raw_item(task_row, payload={})
    assert raw.get("_recovered_task") is True, (
        "empty persisted payload must still carry the _recovered_task marker so "
        "_parse_queue_item recognizes the dict shape"
    )
    assert raw["query_text"] == "Olá"

    # None payload — unchanged behavior.
    raw_none = _build_recovered_raw_item(task_row, payload=None)
    assert raw_none.get("_recovered_task") is True

    # Non-empty persisted payload — marker intentionally stripped; the payload
    # already carries its own (_user_message) marker.
    raw_persisted = _build_recovered_raw_item(
        task_row,
        payload={
            "_user_message": True,
            "chat_id": 8509575891,
            "query_text": "Olá",
        },
    )
    assert raw_persisted.get("_user_message") is True
    assert "_recovered_task" not in raw_persisted


def test_run_coro_sync_dispatches_to_bridge_from_running_loop() -> None:
    """When invoked from within a running loop (sync wrapper called from
    async code), dispatch to the persistent bridge thread so we don't
    deadlock the caller's loop and the asyncpg pool stays on a loop that
    outlives transient asyncio.run boundaries.
    """
    import koda.state.primary as sp

    captured: list[str] = []

    async def _probe() -> str:
        captured.append(threading.current_thread().name)
        return "bridge-ok"

    async def _outer() -> str:
        return sp.run_coro_sync(_probe())

    result = asyncio.run(_outer())
    assert result == "bridge-ok"
    assert captured and captured[0] == "primary-state-bridge"


def test_bridge_loop_rebuilds_on_pid_change() -> None:
    """When the module observes a new PID (fork / subprocess state handoff),
    the bridge must be torn down and rebuilt. ``subprocess_exec`` already
    re-imports modules in a fresh interpreter, so this is defensive against
    any future ``os.fork`` path.
    """
    import koda.state.primary as sp

    # Ensure bridge is up under the current (real) PID.
    sp._ensure_bridge_loop()
    assert os.getpid() == sp._BRIDGE_OWNER_PID

    # Simulate a child process observing inherited module state from a parent.
    fake_parent_pid = os.getpid() + 1234567
    sp._BRIDGE_OWNER_PID = fake_parent_pid

    new_loop = sp._ensure_bridge_loop()
    assert os.getpid() == sp._BRIDGE_OWNER_PID
    assert new_loop is sp._BRIDGE_LOOP


def test_timestamp_text_parser_reads_iso_8601_only() -> None:
    """Legacy callers pass ISO-8601 text for TIMESTAMPTZ/TIMESTAMP parameters.
    The codec parses it in Python; free-form text is refused, never guessed."""
    from datetime import UTC, datetime

    import pytest

    from koda.state.primary import _parse_timestamp_text

    assert _parse_timestamp_text("2026-04-20T23:38:39.997821") == datetime(2026, 4, 20, 23, 38, 39, 997821)
    assert _parse_timestamp_text("2026-04-20T23:38:39Z") == datetime(2026, 4, 20, 23, 38, 39, tzinfo=UTC)
    # Shapes Postgres's own parser accepted when the value was sent as text.
    assert _parse_timestamp_text("2026-04-20 12:00:00+00") == datetime(2026, 4, 20, 12, tzinfo=UTC)
    assert _parse_timestamp_text("2026-04-20") == datetime(2026, 4, 20)
    assert _parse_timestamp_text(" infinity ") == datetime.max
    assert _parse_timestamp_text("-infinity") == datetime.min

    for raw in (
        "sess-abc-123",
        "PIXIE_COPY",
        '{"created_at": "2026-04-20T12:00:00"}',
        "",
        "not a timestamp",
        "now",
    ):
        with pytest.raises(TypeError):
            _parse_timestamp_text(raw)


class _FakeCodecConn:
    def __init__(self, time_zone: str = "UTC") -> None:
        self.codecs: dict[str, dict[str, object]] = {}
        self._time_zone = time_zone

    def get_settings(self) -> object:
        return type("_Settings", (), {"TimeZone": self._time_zone})()

    async def set_type_codec(
        self,
        type_name: str,
        *,
        encoder: object,
        decoder: object,
        schema: str,
        format: str,
    ) -> None:
        self.codecs[type_name] = {
            "encoder": encoder,
            "decoder": decoder,
            "schema": schema,
            "format": format,
        }


def test_timestamptz_codec_accepts_strings_and_datetimes() -> None:
    """The connection-scoped type codec accepts ``datetime``, ``date`` and
    ISO-8601 strings for TIMESTAMPTZ/TIMESTAMP columns so legacy callers
    (``_now_iso()`` returns ``str``) don't hit ``DataError`` on every insert.
    TEXT columns remain unaffected — the codec is registered against
    ``timestamptz``/``timestamp`` only.

    It uses asyncpg's ``tuple`` format: values travel in the binary wire
    format (microseconds since 2000-01-01), so composites, ranges and arrays
    that contain timestamps still decode (D-076).
    """
    import asyncio
    from datetime import UTC, date, datetime, timedelta, timezone

    from koda.state.primary import _install_timestamptz_str_codec

    conn = _FakeCodecConn(time_zone="America/Sao_Paulo")
    asyncio.run(_install_timestamptz_str_codec(conn))

    assert {name: codec["format"] for name, codec in conn.codecs.items()} == {
        "timestamptz": "tuple",
        "timestamp": "tuple",
    }
    encode = conn.codecs["timestamptz"]["encoder"]
    decode = conn.codecs["timestamptz"]["decoder"]
    epoch = datetime(2000, 1, 1, tzinfo=UTC)

    def micros(value: datetime) -> tuple[int]:
        return ((value - epoch) // timedelta(microseconds=1),)

    noon_utc = datetime(2026, 4, 20, 12, 0, tzinfo=UTC)
    assert encode(noon_utc) == micros(noon_utc)
    assert encode(datetime(2026, 4, 20, 9, 0, tzinfo=timezone(timedelta(hours=-3)))) == micros(noon_utc)
    assert encode("2026-04-20T12:00:00+00:00") == micros(noon_utc)
    # Naive text is read in the session TimeZone, as Postgres read it before.
    assert encode("2026-04-20T09:00:00") == micros(noon_utc)
    assert encode(datetime.max) == (2**63 - 1,)
    assert encode(datetime.min) == (-(2**63),)
    assert encode(date(2026, 4, 20)) == micros(datetime(2026, 4, 20).astimezone(UTC))

    assert decode(micros(noon_utc)) == noon_utc
    assert decode(micros(noon_utc)).tzinfo is UTC
    assert decode((2**63 - 1,)) == datetime.max
    assert decode((-(2**63),)) == datetime.min

    encode_naive = conn.codecs["timestamp"]["encoder"]
    decode_naive = conn.codecs["timestamp"]["decoder"]
    naive_epoch = datetime(2000, 1, 1)
    noon = datetime(2026, 4, 20, 12)
    assert encode_naive(noon) == ((noon - naive_epoch) // timedelta(microseconds=1),)
    # Postgres drops the offset of TIMESTAMP text; an aware datetime is refused.
    assert encode_naive("2026-04-20T12:00:00+02:00") == encode_naive(datetime(2026, 4, 20, 12))
    assert decode_naive(encode_naive(datetime(2026, 4, 20, 12))) == datetime(2026, 4, 20, 12)

    import pytest

    with pytest.raises(TypeError):
        encode_naive(noon_utc)
    with pytest.raises(TypeError):
        encode(12345)


def test_timestamptz_codec_install_raises_driver_errors() -> None:
    """The codec is installed once, in the pool ``init`` hook. A failure must
    reach asyncpg, which then discards the connection instead of pooling one
    without the codec (where ISO-string parameters fail with ``DataError``
    for the rest of its life)."""
    import asyncio

    import pytest

    from koda.state.primary import _install_timestamptz_str_codec

    class _BoomConn:
        async def set_type_codec(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("canceling statement due to statement timeout")

    with pytest.raises(RuntimeError, match="statement timeout"):
        asyncio.run(_install_timestamptz_str_codec(_BoomConn()))


def test_primary_sql_qualifies_known_tables_with_the_schema() -> None:
    """The ``primary_*`` helpers schema-qualify table names instead of relying
    on ``search_path``, which a connection pooler may refuse or drop (D-076).
    Only names of tables in the schema change; literals, quoted identifiers,
    comments, columns, functions and already-qualified names stay as written."""
    from koda.state.primary import _schema_qualified

    tables = {"tasks", "sessions", "query_history", "audit_events"}

    def q(sql: str) -> str:
        return _schema_qualified(sql, "knowledge_v2", tables)

    assert q("SELECT * FROM tasks WHERE id = ?") == 'SELECT * FROM "knowledge_v2".tasks WHERE id = ?'
    assert (
        q("SELECT t.id FROM tasks t JOIN sessions s ON s.id = t.session_id")
        == 'SELECT t.id FROM "knowledge_v2".tasks t JOIN "knowledge_v2".sessions s ON s.id = t.session_id'
    )
    assert (
        q("SELECT tasks.id FROM Tasks LEFT JOIN sessions USING (session_id)")
        == 'SELECT tasks.id FROM "knowledge_v2".Tasks LEFT JOIN "knowledge_v2".sessions USING (session_id)'
    )
    assert (
        q("SELECT 1 WHERE EXISTS (SELECT 1 FROM audit_events WHERE event_type = 'from tasks')")
        == "SELECT 1 WHERE EXISTS (SELECT 1 FROM \"knowledge_v2\".audit_events WHERE event_type = 'from tasks')"
    )
    assert (
        q("INSERT INTO tasks (id) VALUES (?) ON CONFLICT (id) DO UPDATE SET id = excluded.id")
        == 'INSERT INTO "knowledge_v2".tasks (id) VALUES (?) ON CONFLICT (id) DO UPDATE SET id = excluded.id'
    )
    assert (
        q("UPDATE tasks SET status = s.status FROM sessions s WHERE s.id = tasks.session_id")
        == 'UPDATE "knowledge_v2".tasks SET status = s.status FROM "knowledge_v2".sessions s'
        " WHERE s.id = tasks.session_id"
    )
    assert (
        q("DELETE FROM tasks USING sessions WHERE sessions.id = tasks.session_id")
        == 'DELETE FROM "knowledge_v2".tasks USING "knowledge_v2".sessions WHERE sessions.id = tasks.session_id'
    )
    assert (
        q("SELECT id FROM tasks WHERE status = 'queued' FOR UPDATE SKIP LOCKED")
        == "SELECT id FROM \"knowledge_v2\".tasks WHERE status = 'queued' FOR UPDATE SKIP LOCKED"
    )
    assert (
        q("TRUNCATE TABLE tasks; ALTER TABLE IF EXISTS sessions ADD COLUMN x TEXT")
        == 'TRUNCATE TABLE "knowledge_v2".tasks; ALTER TABLE IF EXISTS "knowledge_v2".sessions ADD COLUMN x TEXT'
    )
    # Table lists: every listed table, and aliases stay unqualified.
    assert (
        q("TRUNCATE TABLE tasks, sessions RESTART IDENTITY CASCADE")
        == 'TRUNCATE TABLE "knowledge_v2".tasks, "knowledge_v2".sessions RESTART IDENTITY CASCADE'
    )
    assert (
        q("SELECT count(*) FROM tasks t, sessions s, other.audit_events WHERE s.id = t.session_id")
        == 'SELECT count(*) FROM "knowledge_v2".tasks t, "knowledge_v2".sessions s, other.audit_events'
        " WHERE s.id = t.session_id"
    )
    assert (
        q("ALTER TABLE tasks ADD COLUMN s INT REFERENCES sessions(id) ON DELETE CASCADE, ADD COLUMN tasks INT")
        == 'ALTER TABLE "knowledge_v2".tasks ADD COLUMN s INT REFERENCES "knowledge_v2".sessions(id)'
        " ON DELETE CASCADE, ADD COLUMN tasks INT"
    )
    unchanged = [
        'SELECT * FROM "tasks"',
        "SELECT * FROM other.tasks",
        "SELECT * FROM knowledge_v2.tasks",
        "SELECT EXTRACT(EPOCH FROM created_at) FROM recent",
        "SELECT value FROM jsonb_array_elements(?::jsonb)",
        "SELECT 1 -- FROM tasks\n",
        "SELECT 1 /* JOIN sessions */",
        "SELECT $$ FROM tasks $$",
        "SELECT E'it\\'s FROM tasks'",
        "CREATE TEMP TABLE scratch (id INT)",
    ]
    for sql in unchanged:
        assert q(sql) == sql, sql


def test_primary_sql_qualifies_tables_the_helpers_create() -> None:
    """Some stores create their table lazily through the helpers. The new table
    goes into the backend schema, and later statements qualify it too."""
    from koda.state.primary import _schema_qualified

    tables = {"tasks"}
    ddl = _schema_qualified(
        "CREATE TABLE IF NOT EXISTS pending_approvals (op_id TEXT PRIMARY KEY, task_id INT REFERENCES tasks(id))",
        'odd"schema',
        tables,
    )

    assert ddl == (
        'CREATE TABLE IF NOT EXISTS "odd""schema".pending_approvals '
        '(op_id TEXT PRIMARY KEY, task_id INT REFERENCES "odd""schema".tasks(id))'
    )
    assert "pending_approvals" in tables
    assert (
        _schema_qualified("CREATE INDEX IF NOT EXISTS idx_op ON pending_approvals (op_id)", "s", tables)
        == 'CREATE INDEX IF NOT EXISTS idx_op ON "s".pending_approvals (op_id)'
    )
    assert _schema_qualified("SELECT * FROM pending_approvals", "s", tables) == 'SELECT * FROM "s".pending_approvals'


def test_get_shared_postgres_backend_clears_cache_on_pid_change() -> None:
    """The v2 shared backend cache must also drop inherited entries on PID
    change — otherwise the child reuses a backend whose asyncpg pool is
    bound to the parent's event loop.
    """
    from koda.knowledge.v2 import common as common_mod

    # Seed the cache with a sentinel entry and mark it as owned by a fake parent PID.
    class _Sentinel:
        enabled = True
        bootstrapped = False

    common_mod._SHARED_POSTGRES_BACKENDS[("PARENT", "dsn", "knowledge_v2", 1536)] = _Sentinel()  # type: ignore[assignment]
    common_mod._SHARED_BACKENDS_OWNER_PID = os.getpid() + 7654321

    # First call after PID change should clear and install a fresh backend.
    # We accept any backend instance, but the sentinel must be gone.
    common_mod.get_shared_postgres_backend(
        agent_id="CHILD",
        dsn="postgresql://localhost/empty",
        schema="knowledge_v2",
        embedding_dimension=1536,
    )

    cached_keys = set(common_mod._SHARED_POSTGRES_BACKENDS.keys())
    assert ("PARENT", "dsn", "knowledge_v2", 1536) not in cached_keys, (
        "parent-owned cache entry must be evicted when the current PID differs"
    )
    assert os.getpid() == common_mod._SHARED_BACKENDS_OWNER_PID
