"""The daily retention job runs in report-only mode (D-053, F-PLT-06).

``run_maintenance`` used to delete from ``queries`` and ``audit_log``, tables
that do not exist in Postgres, so it failed every day with a warning. It now
counts this agent's ``query_history`` and ``audit_events`` rows that are past
retention, with TIMESTAMPTZ comparisons, and deletes nothing: deletes wait for
the approved retention defaults (M2-E5-T2).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import asyncpg
import pytest

pytestmark = [pytest.mark.postgres]

_AGENT = "RETENTION_REPORT"
_OTHER_AGENT = "RETENTION_OTHER"
_AGENTS = (_AGENT, _OTHER_AGENT)


async def _row_counts(conn: Any, schema: str) -> tuple[int, int]:
    history = await conn.fetchval(
        f'SELECT count(*) FROM "{schema}"."query_history" WHERE agent_id = ANY($1::text[])', list(_AGENTS)
    )
    audit = await conn.fetchval(
        f'SELECT count(*) FROM "{schema}"."audit_events" WHERE agent_id = ANY($1::text[])', list(_AGENTS)
    )
    return int(history), int(audit)


@pytest.fixture
async def seeded(migrated_postgres: str, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[Any, str]]:
    """Rows on both sides of each retention window, plus an old row of another agent."""
    import koda.config as config_module
    from koda.knowledge.config import KNOWLEDGE_V2_POSTGRES_SCHEMA
    from koda.state import history_store

    schema = KNOWLEDGE_V2_POSTGRES_SCHEMA
    monkeypatch.setattr(history_store, "AGENT_ID", _AGENT)
    monkeypatch.setattr(config_module, "AUDIT_RETENTION_DAYS", 30)
    now = datetime.now(UTC)
    conn = await asyncpg.connect(migrated_postgres)

    async def _clear() -> None:
        for table in ("query_history", "audit_events"):
            await conn.execute(f'DELETE FROM "{schema}"."{table}" WHERE agent_id = ANY($1::text[])', list(_AGENTS))

    await _clear()
    history_rows = [
        (_AGENT, now - timedelta(days=120)),  # past the 90-day window
        (_AGENT, now - timedelta(days=91)),  # past the 90-day window
        (_AGENT, now - timedelta(days=89)),  # inside the window
        (_OTHER_AGENT, now - timedelta(days=120)),  # another agent's row
    ]
    for agent_id, timestamp in history_rows:
        await conn.execute(
            f"""INSERT INTO "{schema}"."query_history"
                   (agent_id, user_id, timestamp, query_text, response_text)
                   VALUES ($1, 1, $2, 'q', 'r')""",
            agent_id,
            timestamp,
        )
    audit_rows = [
        (_AGENT, now - timedelta(days=31)),  # past AUDIT_RETENTION_DAYS=30
        (_AGENT, now - timedelta(days=29)),  # inside the window
        (_OTHER_AGENT, now - timedelta(days=60)),  # another agent's row
    ]
    for agent_id, timestamp in audit_rows:
        await conn.execute(
            f"""INSERT INTO "{schema}"."audit_events" (agent_id, timestamp, event_type)
                   VALUES ($1, $2, 'retention.test')""",
            agent_id,
            timestamp,
        )
    try:
        yield conn, schema
    finally:
        await _clear()
        await conn.close()


async def test_run_maintenance_reports_expired_rows_without_deleting(
    seeded: tuple[Any, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from koda.state import history_store

    conn, schema = seeded
    log = MagicMock()
    monkeypatch.setattr(history_store, "log", log)
    before = await _row_counts(conn, schema)

    result = history_store.run_maintenance()

    assert "error" not in result, result
    log.warning.assert_not_called()
    assert result["mode"] == "report_only"
    assert result["query_history_expired"] == 2
    assert result["audit_events_expired"] == 1
    assert result["query_history_retention_days"] == 90
    assert result["audit_events_retention_days"] == 30
    # Report-only: every seeded row is still there.
    assert await _row_counts(conn, schema) == before == (4, 3)


async def test_run_maintenance_cutoffs_are_utc_timestamps(seeded: tuple[Any, str]) -> None:
    from koda.state import history_store

    started = datetime.now(UTC)
    result = history_store.run_maintenance()

    for table, days in (("query_history", 90), ("audit_events", 30)):
        cutoff = datetime.fromisoformat(result[f"{table}_cutoff"])
        assert cutoff.tzinfo is not None
        assert abs(cutoff - (started - timedelta(days=days))) < timedelta(minutes=1)
