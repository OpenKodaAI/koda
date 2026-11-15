"""The daily retention job runs in report-only mode (D-053, F-PLT-06).

``run_maintenance`` used to delete from ``queries`` and ``audit_log``, tables
that do not exist in Postgres, so it failed every day with a warning. It now
counts the ``query_history`` and ``audit_events`` rows past retention, under
every agent scope, with TIMESTAMPTZ comparisons, and deletes nothing: deletes
wait for the approved retention defaults (M2-E5-T2).

The lifecycle supervisor runs it through ``run_maintenance_loop``, which
records each report as a ``retention.report`` audit event. The schedule is
deployment-wide: a worker reports only when no report was recorded in the last
day by any worker, under an advisory lock, so a restart does not push the next
report back and the workers of a deployment record one report a day.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import asyncpg
import pytest

pytestmark = [pytest.mark.postgres]

_AGENT = "RETENTION_REPORT"
# Rows of this worker's agent, of control-plane and squad scopes, and of an
# agent that has been deleted (no worker is left to report its rows).
_SCOPES = (_AGENT, "admin", "squad_router", "system", "RETENTION_DELETED_AGENT")
_USER_ID = 70531  # marks this test's query_history rows
_EVENT = "retention.test"  # marks this test's audit_events rows
_REPORT_EVENT = "retention.report"
_DAY = 86400


async def _seeded_counts(conn: Any, schema: str) -> tuple[int, int]:
    history = await conn.fetchval(f'SELECT count(*) FROM "{schema}"."query_history" WHERE user_id = $1', _USER_ID)
    audit = await conn.fetchval(f'SELECT count(*) FROM "{schema}"."audit_events" WHERE event_type = $1', _EVENT)
    return int(history), int(audit)


async def _insert_report(conn: Any, schema: str, timestamp: datetime, agent_id: str = _AGENT) -> None:
    await conn.execute(
        f"""INSERT INTO "{schema}"."audit_events" (agent_id, timestamp, event_type)
               VALUES ($1, $2, $3)""",
        agent_id,
        timestamp,
        _REPORT_EVENT,
    )


async def _recorded_reports(conn: Any, schema: str) -> list[Any]:
    return list(
        await conn.fetch(
            f'SELECT agent_id, details_json FROM "{schema}"."audit_events" WHERE event_type = $1', _REPORT_EVENT
        )
    )


@pytest.fixture
async def seeded(
    migrated_postgres: str, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[Any, str, dict[str, Any]]]:
    """Rows on both sides of each retention window, under several agent scopes.

    Yields the connection, the schema and the report taken before seeding, so
    tests compare counts against rows other tests left in the shared tables.
    """
    import koda.config as config_module
    from koda.knowledge.config import KNOWLEDGE_V2_POSTGRES_SCHEMA
    from koda.state import history_store

    schema = KNOWLEDGE_V2_POSTGRES_SCHEMA
    monkeypatch.setattr(history_store, "AGENT_ID", _AGENT)
    # Audit events are written under the worker's agent id.
    monkeypatch.setattr(config_module, "AGENT_ID", _AGENT)
    monkeypatch.setattr(config_module, "AUDIT_RETENTION_DAYS", 30)
    conn = await asyncpg.connect(migrated_postgres)

    async def _clear() -> None:
        await conn.execute(f'DELETE FROM "{schema}"."query_history" WHERE user_id = $1', _USER_ID)
        await conn.execute(f'DELETE FROM "{schema}"."audit_events" WHERE event_type = $1', _EVENT)
        # The schedule reads every worker's reports.
        await conn.execute(f'DELETE FROM "{schema}"."audit_events" WHERE event_type = $1', _REPORT_EVENT)

    await _clear()
    baseline = history_store.run_maintenance()
    assert "error" not in baseline, baseline
    now = datetime.now(UTC)
    history_rows = [(scope, now - timedelta(days=120)) for scope in _SCOPES] + [
        (_AGENT, now - timedelta(days=91)),  # past the 90-day window
        (_AGENT, now - timedelta(days=89)),  # inside the window
    ]
    for agent_id, timestamp in history_rows:
        await conn.execute(
            f"""INSERT INTO "{schema}"."query_history"
                   (agent_id, user_id, timestamp, query_text, response_text)
                   VALUES ($1, $2, $3, 'q', 'r')""",
            agent_id,
            _USER_ID,
            timestamp,
        )
    audit_rows = [(scope, now - timedelta(days=31)) for scope in _SCOPES] + [
        (_AGENT, now - timedelta(days=29)),  # inside AUDIT_RETENTION_DAYS=30
    ]
    for agent_id, timestamp in audit_rows:
        await conn.execute(
            f"""INSERT INTO "{schema}"."audit_events" (agent_id, timestamp, event_type)
                   VALUES ($1, $2, $3)""",
            agent_id,
            timestamp,
            _EVENT,
        )
    try:
        yield conn, schema, baseline
    finally:
        await _clear()
        await conn.close()


async def test_run_maintenance_counts_every_agent_scope_without_deleting(
    seeded: tuple[Any, str, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Retention applies to the whole table, so the report counts rows of
    every scope: this worker's agent, admin, squad_router and system rows, and
    rows of a deleted agent that no worker reports for."""
    from koda.state import history_store

    conn, schema, baseline = seeded
    log = MagicMock()
    monkeypatch.setattr(history_store, "log", log)
    before = await _seeded_counts(conn, schema)

    result = history_store.run_maintenance()

    assert "error" not in result, result
    log.warning.assert_not_called()
    assert result["mode"] == "report_only"
    assert result["query_history_expired"] - baseline["query_history_expired"] == len(_SCOPES) + 1
    assert result["audit_events_expired"] - baseline["audit_events_expired"] == len(_SCOPES)
    assert result["query_history_retention_days"] == 90
    assert result["audit_events_retention_days"] == 30
    # Report-only: every seeded row is still there.
    assert await _seeded_counts(conn, schema) == before == (len(_SCOPES) + 2, len(_SCOPES) + 1)


async def test_run_maintenance_cutoffs_are_utc_timestamps(seeded: tuple[Any, str, dict[str, Any]]) -> None:
    from koda.state import history_store

    started = datetime.now(UTC)
    result = history_store.run_maintenance()

    for table, days in (("query_history", 90), ("audit_events", 30)):
        cutoff = datetime.fromisoformat(result[f"{table}_cutoff"])
        assert cutoff.tzinfo is not None
        assert abs(cutoff - (started - timedelta(days=days))) < timedelta(minutes=1)


class _StopLoop(Exception):
    pass


@pytest.fixture
def report_loop(
    seeded: tuple[Any, str, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> tuple[Callable[[], Awaitable[None]], list[float], MagicMock]:
    """Start ``run_maintenance_loop`` the way the lifecycle supervisor does,
    with a sleep that records its delay and then stops the loop."""
    from koda.state import history_store

    log = MagicMock()
    monkeypatch.setattr(history_store, "log", log)
    sleeps: list[float] = []

    async def _sleep(seconds: float) -> None:
        sleeps.append(seconds)
        raise _StopLoop

    async def _start() -> None:
        with pytest.raises(_StopLoop):
            await history_store.run_maintenance_loop(sleep=_sleep)

    return _start, sleeps, log


def _completed_reports(log: MagicMock) -> list[dict[str, Any]]:
    return [call.kwargs for call in log.info.call_args_list if call.args == ("db_maintenance_complete",)]


async def test_maintenance_loop_reports_at_start_and_records_the_report(
    seeded: tuple[Any, str, dict[str, Any]],
    report_loop: tuple[Callable[[], Awaitable[None]], list[float], MagicMock],
) -> None:
    """With no report recorded, the first report runs when the worker starts,
    not a day later, and is recorded for the next start."""
    conn, schema, _ = seeded
    start, sleeps, log = report_loop

    await start()

    reports = _completed_reports(log)
    assert len(reports) == 1
    assert reports[0]["mode"] == "report_only"
    assert reports[0]["query_history_expired"] >= len(_SCOPES) + 1
    recorded = await _recorded_reports(conn, schema)
    assert len(recorded) == 1
    assert recorded[0]["agent_id"] == _AGENT
    details = json.loads(recorded[0]["details_json"])
    assert details["query_history_expired"] == reports[0]["query_history_expired"]
    assert details["audit_events_expired"] == reports[0]["audit_events_expired"]
    log.warning.assert_not_called()
    assert sleeps == [pytest.approx(_DAY, abs=60)]


async def test_maintenance_loop_after_a_restart_waits_for_the_rest_of_the_day(
    report_loop: tuple[Callable[[], Awaitable[None]], list[float], MagicMock],
) -> None:
    """A worker restarted soon after a report does not report again at start;
    it waits until a day after the recorded report."""
    start, sleeps, log = report_loop

    await start()
    await start()  # the restart

    assert len(_completed_reports(log)) == 1
    assert sleeps == [pytest.approx(_DAY, abs=60), pytest.approx(_DAY, abs=60)]


@pytest.mark.parametrize(
    ("hours_ago", "reports_at_start", "first_sleep"),
    [
        (30, 1, _DAY),  # more than a day old: catch up at once
        (2, 0, _DAY - 2 * 3600),  # recent: wait for the rest of the day
    ],
)
@pytest.mark.parametrize("reported_by", [_AGENT, "RETENTION_OTHER_WORKER"])
async def test_maintenance_loop_schedules_from_the_deployments_last_report(
    seeded: tuple[Any, str, dict[str, Any]],
    report_loop: tuple[Callable[[], Awaitable[None]], list[float], MagicMock],
    hours_ago: int,
    reports_at_start: int,
    first_sleep: int,
    reported_by: str,
) -> None:
    """The last report of any worker of the deployment counts, not only this
    worker's own: retention covers whole tables, so one report a day is enough."""
    conn, schema, _ = seeded
    start, sleeps, log = report_loop
    await _insert_report(conn, schema, datetime.now(UTC) - timedelta(hours=hours_ago), agent_id=reported_by)

    await start()

    assert len(_completed_reports(log)) == reports_at_start
    assert len(await _recorded_reports(conn, schema)) == 1 + reports_at_start
    assert sleeps == [pytest.approx(first_sleep, abs=60)]


async def test_workers_starting_together_record_one_report(
    seeded: tuple[Any, str, dict[str, Any]],
    report_loop: tuple[Callable[[], Awaitable[None]], list[float], MagicMock],
) -> None:
    """Every worker of a deployment starts the loop. Started together, with no
    report recorded, only one of them reports: the others wait for it."""
    conn, schema, _ = seeded
    start, sleeps, log = report_loop

    await asyncio.gather(start(), start(), start())

    assert len(_completed_reports(log)) == 1
    assert len(await _recorded_reports(conn, schema)) == 1
    assert len(sleeps) == 3
    log.warning.assert_not_called()


async def test_a_failed_report_is_retried_within_the_hour(
    seeded: tuple[Any, str, dict[str, Any]],
    report_loop: tuple[Callable[[], Awaitable[None]], list[float], MagicMock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A report that ends in error is not the day's run: nothing is recorded
    and the loop tries again in an hour, not a day later."""
    from koda.state import history_store

    conn, schema, _ = seeded
    start, sleeps, log = report_loop
    monkeypatch.setitem(history_store._EXPIRED_ROWS_SQL, "audit_events", "SELECT COUNT(*) FROM no_such_table_70531")

    await start()

    assert _completed_reports(log) == []
    assert await _recorded_reports(conn, schema) == []
    assert log.warning.call_args.args == ("db_maintenance_error",)
    assert sleeps == [pytest.approx(3600, abs=60)]


async def test_maintenance_loop_records_the_report_without_the_bridge_loop(
    seeded: tuple[Any, str, dict[str, Any]],
    report_loop: tuple[Callable[[], Awaitable[None]], list[float], MagicMock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no bridge loop running, the loop's Postgres work runs on transient
    ``asyncio.run`` loops, each with a fresh backend. The report must still be
    recorded (the ``seeded`` fixture starts the bridge loop, so it is hidden here)."""
    from koda.state import primary

    conn, schema, _ = seeded
    start, sleeps, log = report_loop
    monkeypatch.setattr(primary, "_active_bridge_loop", lambda: None)

    await start()

    assert len(_completed_reports(log)) == 1
    assert len(await _recorded_reports(conn, schema)) == 1
    assert sleeps == [pytest.approx(_DAY, abs=60)]


async def test_an_audit_event_is_written_without_the_bridge_loop(
    migrated_postgres: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sync caller with no bridge loop running inserts on a transient loop,
    whose shared backend is fresh and not bootstrapped yet. The event must be
    written, not dropped without a log line."""
    import koda.config as config_module
    from koda.knowledge.config import KNOWLEDGE_V2_POSTGRES_SCHEMA
    from koda.services import audit
    from koda.state import primary

    monkeypatch.setattr(config_module, "AGENT_ID", _AGENT)
    monkeypatch.setattr(primary, "_active_bridge_loop", lambda: None)
    log = MagicMock()
    monkeypatch.setattr(audit, "log", log)
    event = audit.AuditEvent(event_type=_EVENT, details={"path": "transient"})

    await asyncio.get_running_loop().run_in_executor(None, audit.emit, event)

    conn = await asyncpg.connect(migrated_postgres)
    try:
        written = await conn.fetchval(
            f"""SELECT count(*) FROM "{KNOWLEDGE_V2_POSTGRES_SCHEMA}"."audit_events"
                 WHERE event_type = $1 AND agent_id = $2 AND details_json->>'path' = 'transient'""",
            _EVENT,
            _AGENT,
        )
        await conn.execute(f'DELETE FROM "{KNOWLEDGE_V2_POSTGRES_SCHEMA}"."audit_events" WHERE event_type = $1', _EVENT)
    finally:
        await conn.close()
    log.warning.assert_not_called()
    assert written == 1


async def test_the_report_lock_ends_with_the_report_and_is_keyed_by_the_schema(
    seeded: tuple[Any, str, dict[str, Any]],
    report_loop: tuple[Callable[[], Awaitable[None]], list[float], MagicMock],
    migrated_postgres: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Behind a transaction-pooling PgBouncer, closing the client connection
    does not end the server session, so a session lock would stay held for
    whichever client lands on it next. The report's lock is a transaction lock,
    released before the connection is closed. It is keyed by the deployment's
    schema, so a deployment that shares the database under another schema
    takes another lock and still reports when the two overlap."""
    from koda.knowledge.v2.postgres_backend import KnowledgeV2PostgresBackend
    from koda.state import history_store

    _, schema, _ = seeded
    start, sleeps, log = report_loop
    ours_during: list[int] = []
    held_at_close: list[int] = []
    take_report = history_store._expired_rows_report
    close = KnowledgeV2PostgresBackend._close_direct_connection

    async def _observed_report() -> dict[str, Any]:
        observer = await asyncpg.connect(migrated_postgres)
        try:
            ours_during.append(
                await observer.fetchval(
                    """SELECT count(*) FROM pg_locks
                        WHERE locktype = 'advisory' AND granted AND objsubid = 2
                          AND objid::int4 = hashtext($1)""",
                    schema,
                )
            )
        finally:
            await observer.close()
        return await take_report()

    async def _observed_close(self: Any, conn: Any) -> None:
        if not conn.is_closed():
            held_at_close.append(
                await conn.fetchval(
                    "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND pid = pg_backend_pid()"
                )
            )
        await close(self, conn)

    monkeypatch.setattr(history_store, "_expired_rows_report", _observed_report)
    monkeypatch.setattr(KnowledgeV2PostgresBackend, "_close_direct_connection", _observed_close)

    await start()

    assert len(_completed_reports(log)) == 1
    assert ours_during == [1]
    assert held_at_close == [0]
    log.warning.assert_not_called()


async def test_a_slow_report_gets_a_bridge_budget_for_each_step(
    seeded: tuple[Any, str, dict[str, Any]],
    report_loop: tuple[Callable[[], Awaitable[None]], list[float], MagicMock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The report runs in one bridge call: the lock, the last-report lookup,
    two whole-table counts and the insert. Each count finishes inside one
    bridge timeout, but not both together, and the report must still be
    recorded instead of being cancelled every hour."""
    from koda.state import history_store, primary

    conn, schema, _ = seeded
    start, sleeps, log = report_loop
    monkeypatch.setattr(primary, "_BRIDGE_TIMEOUT_SECONDS", 1.0)
    for table in ("query_history", "audit_events"):
        monkeypatch.setitem(
            history_store._EXPIRED_ROWS_SQL,
            table,
            f"SELECT (SELECT COUNT(*) FROM {table} WHERE timestamp < ?) FROM pg_sleep(0.6)",
        )

    await start()

    assert len(_completed_reports(log)) == 1
    assert len(await _recorded_reports(conn, schema)) == 1
    log.warning.assert_not_called()
    assert sleeps == [pytest.approx(_DAY, abs=60)]


async def test_the_last_report_lookup_reads_an_event_type_index(seeded: tuple[Any, str, dict[str, Any]]) -> None:
    """The deployment-wide lookup filters on ``event_type`` alone, so it needs
    an index that leads with it instead of scanning all of ``audit_events``."""
    from koda.state import history_store

    conn, schema, _ = seeded
    async with conn.transaction():
        await conn.execute(f'SET LOCAL search_path = "{schema}"')
        await conn.execute("SET LOCAL enable_seqscan = off")
        plan = "\n".join(
            row[0]
            for row in await conn.fetch("EXPLAIN " + history_store._LAST_REPORT_SQL.replace("?", "$1"), _REPORT_EVENT)
        )

    assert "idx_audit_events_type_time" in plan, plan
