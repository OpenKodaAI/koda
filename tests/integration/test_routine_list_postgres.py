"""Routine list and rename against a real PostgreSQL database (M3-E1-T3).

Pinned guarantees:

  * A deleted (archived) routine disappears from the dashboard schedules list,
    unless the caller asks for ``include_archived`` (D-079).
  * A routine rename is stored in ``payload.name`` and is what the list reads
    back after a reload (D-063).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import patch

import asyncpg
import pytest

from tests.postgres_fixtures import close_shared_postgres_backends, stop_primary_bridge

pytestmark = [pytest.mark.postgres]

_SCHEDULER_TABLES = ("scheduled_job_events", "scheduled_job_runs", "scheduled_jobs")


@pytest.fixture
async def scheduler_db(migrated_postgres: str) -> AsyncIterator[str]:
    close_shared_postgres_backends()
    conn = await asyncpg.connect(migrated_postgres)
    try:
        tables = ", ".join(f'knowledge_v2."{name}"' for name in _SCHEDULER_TABLES)
        await conn.execute(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE")
    finally:
        await conn.close()
    try:
        yield migrated_postgres
    finally:
        stop_primary_bridge()


def _create_routine(name: str) -> int:
    from koda.services import scheduled_jobs

    return scheduled_jobs.create_job(
        user_id=111,
        chat_id=222,
        job_type="agent_query",
        trigger_type="cron",
        schedule_expr="0 9 * * *",
        timezone_name="UTC",
        payload={"name": name, "query": "Check deploy health"},
        work_dir="/tmp",
    )


def _list(**kwargs: Any) -> list[dict[str, Any]]:
    from koda.control_plane import dashboard_service
    from koda.services import scheduled_jobs

    catalog = {scheduled_jobs.AGENT_ID: {"id": scheduled_jobs.AGENT_ID}}
    with patch.object(dashboard_service, "_catalog_by_id", return_value=catalog):
        return dashboard_service.list_dashboard_schedules(**kwargs)


async def test_deleted_routine_disappears_from_the_list(scheduler_db: str) -> None:
    from koda.services import scheduled_jobs

    kept = _create_routine("Kept")
    deleted = _create_routine("Deleted")
    ok, _ = scheduled_jobs.delete_job(deleted, user_id=111)
    assert ok

    assert [item["id"] for item in _list()] == [kept]
    assert sorted(item["id"] for item in _list(include_archived=True)) == sorted([kept, deleted])


async def test_routine_rename_survives_a_reload(scheduler_db: str) -> None:
    from koda.services import scheduled_jobs

    job_id = _create_routine("Original name")
    result = scheduled_jobs.update_job(
        job_id,
        user_id=111,
        patch={"name": "  Renamed routine  "},
        expected_config_version=1,
    )
    assert result["ok"] is True, result

    [item] = _list()
    assert item["payload"]["name"] == "Renamed routine"
    assert item["payload"]["query"] == "Check deploy health"
