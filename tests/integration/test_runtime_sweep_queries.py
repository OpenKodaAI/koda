"""Runtime sweeps act on live environments only (M9-E1-T4, D-112).

The resource, reconcile and cleanup sweeps used to load every environment
ever created and issue several queries for each one. These tests seed a
real Postgres with a few live environments plus 10 or 10,000 cleaned
(historical) ones and count the queries each sweep issues.
"""

from __future__ import annotations

import contextlib
import json as _json
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import asyncpg
import pytest

import koda.services.runtime.controller as controller_module
import koda.services.runtime.postgres_store as ps_mod
from tests.postgres_fixtures import close_shared_postgres_backends

pytestmark = [pytest.mark.postgres]

_AGENT = "agent_sweep"
_TABLES = (
    "runtime_attach_sessions",
    "runtime_browser_sessions",
    "runtime_events",
    "runtime_port_allocations",
    "runtime_processes",
    "runtime_resource_samples",
    "runtime_service_endpoints",
    "runtime_terminals",
    "runtime_environments",
)
_ENV_COLUMNS = (
    "agent_id, task_id, user_id, chat_id, classification, environment_kind, isolation, duration, status, "
    "current_phase, workspace_path, runtime_dir, base_work_dir, browser_transport, process_pid, "
    "retention_expires_at, created_at, updated_at"
)
_PAST = "2026-01-01T00:00:00+00:00"
_FUTURE = "2999-01-01T00:00:00+00:00"


@pytest.fixture
async def runtime_db(migrated_postgres: str, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[str]:
    close_shared_postgres_backends()
    from koda.state import primary as primary_mod

    original_install = primary_mod._install_timestamptz_str_codec

    async def _install_codecs(conn: Any) -> None:
        await original_install(conn)
        with contextlib.suppress(Exception):
            await conn.set_type_codec(
                "jsonb",
                encoder=lambda v: v if isinstance(v, str) else _json.dumps(v, default=str),
                decoder=lambda v: _json.loads(v) if v else None,
                schema="pg_catalog",
                format="text",
            )

    monkeypatch.setattr(primary_mod, "_install_timestamptz_str_codec", _install_codecs)
    await _truncate(migrated_postgres)
    try:
        yield migrated_postgres
    finally:
        await _truncate(migrated_postgres)
        close_shared_postgres_backends()


async def _truncate(dsn: str) -> None:
    conn = await asyncpg.connect(dsn)
    try:
        tables = ", ".join(f'knowledge_v2."{name}"' for name in _TABLES)
        await conn.execute(f"TRUNCATE TABLE {tables} RESTART IDENTITY")
    finally:
        await conn.close()


async def _insert_env(
    conn: asyncpg.Connection,
    *,
    task_id: int,
    status: str,
    phase: str,
    browser_transport: str = "",
    process_pid: int | None = None,
    retention_expires_at: str | None = None,
) -> int:
    return int(
        await conn.fetchval(
            f"""
            INSERT INTO knowledge_v2.runtime_environments ({_ENV_COLUMNS})
            VALUES ($1, $2, 1, 1, 'standard', 'dev_worktree_browser', 'worktree', 'long', $3, $4,
                    '/tmp/ws', '/tmp/rt', '/tmp/base', $5, $6, $7, $8, $8)
            RETURNING id
            """,
            _AGENT,
            task_id,
            status,
            phase,
            browser_transport,
            process_pid,
            retention_expires_at,
            _PAST,
        )
    )


async def _insert_process(
    conn: asyncpg.Connection,
    *,
    task_id: int,
    env_id: int,
    pid: int,
    status: str,
    process_kind: str = "service",
) -> None:
    await conn.execute(
        """
        INSERT INTO knowledge_v2.runtime_processes
            (agent_id, task_id, env_id, pid, role, process_kind, status, started_at, updated_at)
        VALUES ($1, $2, $3, $4, 'provider', $5, $6, $7, $7)
        """,
        _AGENT,
        task_id,
        env_id,
        pid,
        process_kind,
        status,
        _PAST,
    )


async def _insert_attach_session(conn: asyncpg.Connection, *, task_id: int, env_id: int, status: str) -> None:
    await conn.execute(
        """
        INSERT INTO knowledge_v2.runtime_attach_sessions
            (agent_id, task_id, env_id, attach_kind, token, actor, status, expires_at, created_at, last_seen_at)
        VALUES ($1, $2, $3, 'terminal', $4, 'operator', $5, $6, $7, $7)
        """,
        _AGENT,
        task_id,
        env_id,
        f"token-{task_id}-{env_id}-{status}",
        status,
        _FUTURE,
        _PAST,
    )


async def _insert_browser_session(conn: asyncpg.Connection, *, task_id: int, env_id: int, status: str) -> None:
    await conn.execute(
        """
        INSERT INTO knowledge_v2.runtime_browser_sessions
            (agent_id, task_id, env_id, scope_id, transport, status, created_at, updated_at)
        VALUES ($1, $2, $3, $2, 'xvfb', $4, $5, $5)
        """,
        _AGENT,
        task_id,
        env_id,
        status,
        _PAST,
    )


async def _seed_live(dsn: str) -> None:
    """One running active environment, one retained environment an operator is
    attached to, and one idle retained environment."""
    conn = await asyncpg.connect(dsn)
    try:
        active = await _insert_env(conn, task_id=1, status="active", phase="executing", process_pid=4242)
        await _insert_process(conn, task_id=1, env_id=active, pid=4242, status="running")
        attached = await _insert_env(
            conn, task_id=2, status="retained", phase="completed_retained", retention_expires_at=_FUTURE
        )
        await _insert_attach_session(conn, task_id=2, env_id=attached, status="active")
        await _insert_env(conn, task_id=3, status="retained", phase="completed_retained", retention_expires_at=_FUTURE)
    finally:
        await conn.close()


async def _seed_historical(dsn: str, count: int) -> None:
    """``count`` cleaned browser environments whose sidecars exited and whose
    browser sessions were closed when they were cleaned."""
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(
            f"""
            INSERT INTO knowledge_v2.runtime_environments ({_ENV_COLUMNS})
            SELECT $1, 1000 + n, 1, 1, 'standard', 'dev_worktree_browser', 'worktree', 'long', 'cleaned',
                   'cleaned', '/tmp/ws', '/tmp/rt', '/tmp/base', 'xvfb', NULL, $2, $2, $2
            FROM generate_series(1, $3::int) AS n
            """,
            _AGENT,
            _PAST,
            count,
        )
        await conn.execute(
            """
            INSERT INTO knowledge_v2.runtime_processes
                (agent_id, task_id, env_id, pid, role, process_kind, status, started_at, updated_at)
            SELECT agent_id, task_id, id, 50000 + id, 'browser', 'browser_sidecar', 'exited', $2, $2
            FROM knowledge_v2.runtime_environments WHERE agent_id = $1 AND status = 'cleaned'
            """,
            _AGENT,
            _PAST,
        )
        await conn.execute(
            """
            INSERT INTO knowledge_v2.runtime_browser_sessions
                (agent_id, task_id, env_id, scope_id, transport, status, created_at, updated_at)
            SELECT agent_id, task_id, id, task_id, 'xvfb', 'closed', $2, $2
            FROM knowledge_v2.runtime_environments WHERE agent_id = $1 AND status = 'cleaned'
            """,
            _AGENT,
            _PAST,
        )
    finally:
        await conn.close()


class _KernelStub:
    def health(self) -> dict[str, Any]:
        return {"mode": "python", "transport": "in-process", "connected": True, "ready": True}

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def collect_snapshot(self, *, task_id: int) -> dict[str, Any]:
        return {"task": {"process_running": task_id == 1}}

    async def reconcile(self) -> dict[str, Any]:
        return {"forwarded": True}

    async def stop_browser_session(self, *, task_id: int, scope_id: int, force: bool = False) -> dict[str, Any]:
        return {"forwarded": True, "stopped": True}


def _store() -> ps_mod.PostgresRuntimeStore:
    store = ps_mod.PostgresRuntimeStore()
    store._agent_scope = _AGENT
    return store


def _controller(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, store: ps_mod.PostgresRuntimeStore
) -> controller_module.RuntimeController:
    monkeypatch.setattr(controller_module, "RuntimeStore", lambda: store)
    monkeypatch.setattr(controller_module, "build_runtime_kernel_client", lambda runtime_root, store: _KernelStub())
    monkeypatch.setattr(controller_module, "RecoveryManager", lambda store: SimpleNamespace())
    monkeypatch.setattr(controller_module, "RUNTIME_BROWSER_LIVE_ENABLED", False)
    return controller_module.RuntimeController(runtime_root=tmp_path / "runtime")


def _count_queries(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    queries: list[str] = []
    for name in ("primary_execute", "primary_fetch_all", "primary_fetch_one", "primary_fetch_val"):
        original = getattr(ps_mod, name)

        def _counted(query: str, *args: Any, _original: Any = original, **kwargs: Any) -> Any:
            queries.append(query)
            return _original(query, *args, **kwargs)

        monkeypatch.setattr(ps_mod, name, _counted)
    return queries


async def _sweep_query_counts(
    dsn: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, historical: int
) -> dict[str, int]:
    await _truncate(dsn)
    await _seed_live(dsn)
    await _seed_historical(dsn, historical)
    controller = _controller(monkeypatch, tmp_path, _store())
    counts: dict[str, int] = {}
    with monkeypatch.context() as patch:
        queries = _count_queries(patch)
        for name, sweep in (
            ("resource", controller.sample_resources),
            ("reconcile", controller.reconcile_runtime_state),
            ("cleanup", controller.cleanup_expired),
        ):
            queries.clear()
            await sweep()
            counts[name] = len(queries)
    return counts


async def test_sweep_query_count_does_not_grow_with_historical_environments(
    runtime_db: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    few = await _sweep_query_counts(runtime_db, monkeypatch, tmp_path, historical=10)
    many = await _sweep_query_counts(runtime_db, monkeypatch, tmp_path, historical=10_000)

    assert many == few
    # The live environments are still swept: the active and the attached
    # retained environment are sampled, and the active one is reconciled.
    assert few["resource"] > 1
    assert few["reconcile"] > 1


async def test_sweeps_leave_cleaned_environments_alone(
    runtime_db: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    await _seed_live(runtime_db)
    await _seed_historical(runtime_db, 3)
    store = _store()
    controller = _controller(monkeypatch, tmp_path, store)

    await controller.sample_resources()
    await controller.reconcile_runtime_state()
    await controller.cleanup_expired()

    sampled = {int(row["task_id"]) for row in store._fetch_all("SELECT task_id FROM runtime_resource_samples")}
    assert sampled == {1, 2}
    event_tasks = {int(row["task_id"]) for row in store._fetch_all("SELECT task_id FROM runtime_events")}
    assert event_tasks <= {1, 2, 3}


async def test_live_environments_keep_cleaned_ones_with_unexited_processes(runtime_db: str) -> None:
    conn = await asyncpg.connect(runtime_db)
    try:
        active = await _insert_env(conn, task_id=1, status="active", phase="executing")
        cancel = await _insert_env(conn, task_id=2, status="cancel_requested", phase="cancel_requested")
        retained = await _insert_env(conn, task_id=3, status="retained", phase="completed_retained")
        cleaned_done = await _insert_env(conn, task_id=4, status="cleaned", phase="cleaned")
        await _insert_process(conn, task_id=4, env_id=cleaned_done, pid=40, status="exited")
        cleaned_running = await _insert_env(conn, task_id=5, status="cleaned", phase="cleaned", process_pid=50)
        await _insert_process(conn, task_id=5, env_id=cleaned_running, pid=50, status="running")
    finally:
        await conn.close()

    live = [int(row["id"]) for row in _store().list_live_environments()]

    assert live == [cleaned_running, retained, cancel, active]


async def test_environments_to_sample_match_the_sampling_rule(runtime_db: str) -> None:
    conn = await asyncpg.connect(runtime_db)
    try:
        active = await _insert_env(conn, task_id=1, status="active", phase="executing")
        cleaning = await _insert_env(conn, task_id=2, status="cleaning", phase="cleaning")
        with_process = await _insert_env(conn, task_id=3, status="retained", phase="completed_retained")
        await _insert_process(conn, task_id=3, env_id=with_process, pid=30, status="running")
        with_attach = await _insert_env(conn, task_id=4, status="retained", phase="completed_retained")
        await _insert_attach_session(conn, task_id=4, env_id=with_attach, status="active")
        with_browser = await _insert_env(conn, task_id=5, status="retained", phase="completed_retained")
        await _insert_browser_session(conn, task_id=5, env_id=with_browser, status="active")
        idle = await _insert_env(conn, task_id=6, status="retained", phase="completed_retained")
        await _insert_process(conn, task_id=6, env_id=idle, pid=60, status="exited")
        await _insert_attach_session(conn, task_id=6, env_id=idle, status="closed")
        await _insert_browser_session(conn, task_id=6, env_id=idle, status="closed")
        other_env_browser = await _insert_env(conn, task_id=7, status="retained", phase="completed_retained")
        await _insert_browser_session(conn, task_id=7, env_id=other_env_browser + 1000, status="active")
        await _insert_env(conn, task_id=8, status="cancel_requested", phase="cancel_requested")
        cleaned = await _insert_env(conn, task_id=9, status="cleaned", phase="cleaned")
        await _insert_process(conn, task_id=9, env_id=cleaned, pid=90, status="running")
    finally:
        await conn.close()

    sampled = [int(row["id"]) for row in _store().list_environments_to_sample()]

    assert sampled == [with_browser, with_attach, with_process, cleaning, active]
