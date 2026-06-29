"""Contract tests for the per-task lease primitives in ``koda.state.history_store``.

Together with the runtime tests in ``test_services/test_queue_manager_lease.py``
these guarantee the orchestration invariants the lease design depends on:

- Acquisition is a single atomic UPDATE — two workers never both succeed.
- Renewal requires the caller to still own the lease; if the row was reaped
  the renewal MUST return False so the worker can bail.
- Terminal-state transitions clear the lease atomically; mid-execution ones
  preserve it so the renewal loop keeps extending.
- The reaper splits expired rows into requeued (attempt < max_attempts) and
  failed (exhausted) buckets and labels them via the ``outcome`` field.

The tests run without a Postgres backend by stubbing ``primary_execute`` and
``primary_fetch_all`` to capture every issued statement.
"""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def stub_primary(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace the primary backend bridge with deterministic captures.

    ``executes`` is a list of (sql, params) tuples for every UPDATE issued.
    ``execute_returns`` is a queue of integer return values consumed in
    order — the next ``primary_execute`` call returns the head element
    (default 1, simulating "row updated"). ``fetch_all_returns`` works the
    same way for the reaper's RETURNING queries.
    """
    from koda.state import history_store as hs
    from koda.state import primary as primary_module

    state: dict[str, Any] = {
        "executes": [],
        "execute_returns": [],
        "fetch_all_returns": [],
    }

    async def fake_execute(query: str, params: tuple[Any, ...] | list[Any] = (), *, agent_id: str | None = None) -> int:
        state["executes"].append((query, tuple(params)))
        if state["execute_returns"]:
            return int(state["execute_returns"].pop(0))
        return 1

    async def fake_fetch_all(
        query: str, params: tuple[Any, ...] | list[Any] = (), *, agent_id: str | None = None
    ) -> list[dict[str, Any]]:
        state["executes"].append((query, tuple(params)))
        if state["fetch_all_returns"]:
            return list(state["fetch_all_returns"].pop(0))
        return []

    def fake_run_coro_sync(coro: Any) -> Any:
        # Drive the awaitable to completion synchronously; primary_execute
        # is a coroutine in the production code, but the bridge loop is
        # not exercised here.
        try:
            coro.send(None)
        except StopIteration as exc:
            return exc.value

    monkeypatch.setattr(hs, "primary_execute", fake_execute)
    monkeypatch.setattr(hs, "primary_fetch_all", fake_fetch_all)
    monkeypatch.setattr(hs, "run_coro_sync", fake_run_coro_sync)
    monkeypatch.setattr(hs, "_primary_backend", lambda: object())
    monkeypatch.setattr(primary_module, "postgres_primary_mode", lambda: True)
    return state


def _last_sql(state: dict[str, Any]) -> str:
    assert state["executes"], "expected at least one statement"
    return state["executes"][-1][0]


def test_acquire_task_lease_uses_compare_and_swap(stub_primary: dict[str, Any]) -> None:
    from koda.state.history_store import acquire_task_lease

    ok = acquire_task_lease(task_id=42, owner="worker-A", lease_seconds=60)
    assert ok is True

    sql, params = stub_primary["executes"][-1]
    # Atomic UPDATE — sets running + lease, gated by status not-yet-terminal
    # AND lease either missing, owned by us, or expired.
    assert "UPDATE tasks" in sql
    assert "SET status = 'running'" in sql
    assert "lease_owner = ?" in sql
    assert "lease_expires_at = ?" in sql
    assert "status IN ('queued', 'running', 'retrying')" in sql
    assert "lease_owner IS NULL" in sql
    assert "lease_owner = ?" in sql.split("WHERE", 1)[1]
    assert "lease_expires_at IS NULL" in sql
    assert "lease_expires_at < ?" in sql
    # owner appears in SET and WHERE; task_id and agent_scope appear once.
    assert "worker-A" in params


def test_acquire_task_lease_returns_false_on_zero_rows(stub_primary: dict[str, Any]) -> None:
    from koda.state.history_store import acquire_task_lease

    stub_primary["execute_returns"].append(0)
    ok = acquire_task_lease(task_id=42, owner="worker-A", lease_seconds=60)
    assert ok is False


def test_extend_task_lease_scoped_to_owner(stub_primary: dict[str, Any]) -> None:
    from koda.state.history_store import extend_task_lease

    ok = extend_task_lease(task_id=7, owner="worker-A", lease_seconds=60)
    assert ok is True

    sql = _last_sql(stub_primary)
    assert "UPDATE tasks" in sql
    assert "SET lease_expires_at = ?, last_heartbeat_at = ?" in sql
    # WHERE clause MUST scope by owner — otherwise a reaped row could be
    # silently revived by an unaware worker.
    assert "lease_owner = ?" in sql
    assert "status IN ('running', 'retrying')" in sql


def test_extend_task_lease_returns_false_when_owner_lost(stub_primary: dict[str, Any]) -> None:
    from koda.state.history_store import extend_task_lease

    stub_primary["execute_returns"].append(0)
    ok = extend_task_lease(task_id=7, owner="worker-A", lease_seconds=60)
    assert ok is False, "extend MUST signal lease loss so the worker can abort"


def test_release_task_lease_only_clears_when_owner_matches(stub_primary: dict[str, Any]) -> None:
    from koda.state.history_store import release_task_lease

    release_task_lease(task_id=7, owner="worker-A")
    sql = _last_sql(stub_primary)
    assert "SET lease_owner = NULL, lease_expires_at = NULL" in sql
    assert "lease_owner = ?" in sql, "release must be a no-op for non-owners"


def test_update_task_with_lease_keeps_lease_for_running(stub_primary: dict[str, Any]) -> None:
    """Mid-execution status updates (running/retrying) MUST NOT clear the
    lease — the renewal loop is still extending it and clearing here would
    let the janitor reap a row that is actively being processed."""
    from koda.state.history_store import update_task_with_lease

    ok = update_task_with_lease(task_id=7, owner="worker-A", status="retrying", attempt=2)
    assert ok is True
    sql = _last_sql(stub_primary)
    assert "SET status = ?" in sql
    assert "lease_owner = NULL" not in sql
    assert "lease_expires_at = NULL" not in sql


def test_update_task_with_lease_clears_lease_for_terminal(stub_primary: dict[str, Any]) -> None:
    """Terminal transitions (completed/failed/cancelled) clear the lease in
    the same atomic UPDATE so a follow-up worker can immediately reacquire."""
    from koda.state.history_store import update_task_with_lease

    for terminal in ("completed", "failed", "cancelled"):
        stub_primary["executes"].clear()
        ok = update_task_with_lease(task_id=9, owner="worker-A", status=terminal)
        assert ok is True
        sql = _last_sql(stub_primary)
        assert "SET status = ?, lease_owner = NULL, lease_expires_at = NULL" in sql


def test_update_task_with_lease_returns_false_on_lost_lease(stub_primary: dict[str, Any]) -> None:
    """If the janitor already requeued the row, the worker's terminal
    update MUST be a no-op so it cannot resurrect a row the janitor
    decided was orphaned."""
    from koda.state.history_store import update_task_with_lease

    stub_primary["execute_returns"].append(0)
    ok = update_task_with_lease(task_id=9, owner="worker-A", status="completed")
    assert ok is False


def test_reap_expired_returns_split_outcomes(stub_primary: dict[str, Any]) -> None:
    """The reaper splits expired rows into ``requeued`` (still inside the
    retry budget) and ``failed`` (exhausted) buckets via two atomic UPDATEs
    with RETURNING. Each entry is annotated with its outcome so callers
    can audit the distinction."""
    from koda.state.history_store import reap_expired_task_leases

    stub_primary["fetch_all_returns"].append(
        [
            {"id": 11, "user_id": 100, "chat_id": 200, "attempt": 1, "max_attempts": 3},
        ]
    )
    stub_primary["fetch_all_returns"].append(
        [
            {"id": 22, "user_id": 101, "chat_id": 201, "attempt": 3, "max_attempts": 3},
        ]
    )

    out = reap_expired_task_leases()
    assert len(out) == 2
    by_id = {row["id"]: row for row in out}
    assert by_id[11]["outcome"] == "requeued"
    assert by_id[22]["outcome"] == "failed"

    # Two separate atomic UPDATEs were issued — one per outcome.
    assert len(stub_primary["executes"]) == 2
    requeue_sql = stub_primary["executes"][0][0]
    fail_sql = stub_primary["executes"][1][0]
    assert "SET status = 'queued'" in requeue_sql
    assert "attempt = attempt + 1" in requeue_sql
    assert "attempt < max_attempts" in requeue_sql
    assert "SET status = 'failed'" in fail_sql
    assert "attempt >= max_attempts" in fail_sql
    # Both branches must catch legacy rows where lease was never set.
    for sql in (requeue_sql, fail_sql):
        assert "lease_expires_at IS NULL OR lease_expires_at < ?" in sql


def test_reap_expired_returns_empty_when_nothing_expired(stub_primary: dict[str, Any]) -> None:
    from koda.state.history_store import reap_expired_task_leases

    stub_primary["fetch_all_returns"].extend([[], []])
    assert reap_expired_task_leases() == []
