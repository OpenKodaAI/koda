"""Tests for koda.services.runtime.recovery_manager.RecoveryManager.

The recovery sweep has one action: the controller recovers every stale environment the
manager lists. The manager only marks an environment as an orphan when none of its
recorded processes is alive (status != "exited") and it has no checkpoint; the
controller counts orphans in ``koda_runtime_orphan_envs`` and the others in
``koda_runtime_recoveries_total``.
"""

from __future__ import annotations

from typing import Any

from koda.services.runtime.recovery_manager import RecoveryManager


class _FakeStore:
    """Minimal PostgresRuntimeStore stand-in for recovery-manager tests."""

    def __init__(
        self,
        *,
        stale_envs: list[dict[str, Any]] | None = None,
        checkpoints: dict[int, dict[str, Any]] | None = None,
        processes: dict[tuple[int, int], list[dict[str, Any]]] | None = None,
    ) -> None:
        self._stale = list(stale_envs or [])
        self._checkpoints = dict(checkpoints or {})
        self._processes = dict(processes or {})
        self.list_stale_calls: list[str] = []

    def list_stale_environments(self, *, stale_before: str) -> list[dict[str, Any]]:
        self.list_stale_calls.append(stale_before)
        return list(self._stale)

    def get_latest_checkpoint(self, task_id: int) -> dict[str, Any] | None:
        return self._checkpoints.get(task_id)

    def list_processes(self, task_id: int, *, env_id: int | None = None) -> list[dict[str, Any]]:
        return list(self._processes.get((task_id, env_id or 0), []))


# No stale envs → no-op


def test_no_stale_environments_returns_empty_list() -> None:
    rm = RecoveryManager(_FakeStore())  # type: ignore[arg-type]
    assert rm.recover_stale() == []


def test_recover_calls_list_stale_with_iso_timestamp() -> None:
    """Sweep computes stale_before = now - RUNTIME_STALE_AFTER_SECONDS."""
    store = _FakeStore()
    rm = RecoveryManager(store)  # type: ignore[arg-type]
    rm.recover_stale()
    assert len(store.list_stale_calls) == 1
    cutoff = store.list_stale_calls[0]
    # ISO 8601 with timezone — must end with +00:00 or Z.
    assert cutoff.endswith("+00:00") or cutoff.endswith("Z")


# Not an orphan: a recorded process is still alive


def test_not_orphan_when_at_least_one_process_alive() -> None:
    store = _FakeStore(
        stale_envs=[{"id": 100, "task_id": 1}],
        processes={
            (1, 100): [
                {"pid": 1234, "status": "running"},
                {"pid": 5678, "status": "exited"},  # one dead, one alive → not an orphan
            ],
        },
    )
    rm = RecoveryManager(store)  # type: ignore[arg-type]
    out = rm.recover_stale()
    assert out == [{"env_id": 100, "task_id": 1, "orphan": False}]


def test_not_orphan_with_several_alive_processes() -> None:
    store = _FakeStore(
        stale_envs=[{"id": 200, "task_id": 2}],
        processes={
            (2, 200): [
                {"pid": 1, "status": "running"},
                {"pid": 2, "status": "running"},
                {"pid": 3, "status": "running"},
                {"pid": 4, "status": "exited"},
            ],
        },
    )
    rm = RecoveryManager(store)  # type: ignore[arg-type]
    out = rm.recover_stale()
    assert out[0]["orphan"] is False


def test_status_other_than_exited_counts_as_alive() -> None:
    """Only literal status == 'exited' is treated as dead. Anything else
    (running, suspended, '', None, 'paused') counts as alive."""
    for status in ("running", "suspended", "paused", "", None, "wedged"):
        store = _FakeStore(
            stale_envs=[{"id": 1, "task_id": 1}],
            processes={(1, 1): [{"pid": 99, "status": status}]},
        )
        rm = RecoveryManager(store)  # type: ignore[arg-type]
        out = rm.recover_stale()
        assert out[0]["orphan"] is False, f"status={status!r} should count as alive"


def test_not_orphan_with_alive_processes_and_a_checkpoint() -> None:
    store = _FakeStore(
        stale_envs=[{"id": 1, "task_id": 1}],
        checkpoints={1: {"id": 99}},  # has a checkpoint
        processes={(1, 1): [{"pid": 1, "status": "running"}]},
    )
    rm = RecoveryManager(store)  # type: ignore[arg-type]
    out = rm.recover_stale()
    assert out[0]["orphan"] is False


# Not an orphan: no live process, but a checkpoint exists


def test_not_orphan_when_only_a_checkpoint_is_present() -> None:
    store = _FakeStore(
        stale_envs=[{"id": 50, "task_id": 5}],
        checkpoints={5: {"id": 9999}},
        processes={(5, 50): [{"pid": 1, "status": "exited"}]},
    )
    rm = RecoveryManager(store)  # type: ignore[arg-type]
    out = rm.recover_stale()
    assert out == [{"env_id": 50, "task_id": 5, "orphan": False}]


def test_not_orphan_with_a_checkpoint_and_no_recorded_process() -> None:
    """Empty process list with a checkpoint → not an orphan."""
    store = _FakeStore(
        stale_envs=[{"id": 7, "task_id": 7}],
        checkpoints={7: {"id": 1234}},
        processes={(7, 7): []},
    )
    rm = RecoveryManager(store)  # type: ignore[arg-type]
    out = rm.recover_stale()
    assert out[0]["orphan"] is False


# Orphan: neither a live process nor a checkpoint


def test_orphan_when_nothing_to_recover() -> None:
    store = _FakeStore(
        stale_envs=[{"id": 11, "task_id": 1}],
        checkpoints={},
        processes={},
    )
    rm = RecoveryManager(store)  # type: ignore[arg-type]
    out = rm.recover_stale()
    assert out == [{"env_id": 11, "task_id": 1, "orphan": True}]


def test_orphan_when_only_dead_processes() -> None:
    store = _FakeStore(
        stale_envs=[{"id": 11, "task_id": 1}],
        processes={(1, 11): [{"pid": 1, "status": "exited"}, {"pid": 2, "status": "exited"}]},
    )
    rm = RecoveryManager(store)  # type: ignore[arg-type]
    out = rm.recover_stale()
    assert out[0]["orphan"] is True


# Multiple stale envs in one sweep


def test_recover_handles_a_mix_in_one_sweep() -> None:
    store = _FakeStore(
        stale_envs=[
            {"id": 1, "task_id": 10},
            {"id": 2, "task_id": 20},
            {"id": 3, "task_id": 30},
        ],
        checkpoints={20: {"id": 200}},
        processes={
            (10, 1): [{"pid": 1, "status": "running"}],  # alive process
            (20, 2): [{"pid": 2, "status": "exited"}],  # checkpoint
            (30, 3): [],  # nothing → orphan
        },
    )
    rm = RecoveryManager(store)  # type: ignore[arg-type]
    out = rm.recover_stale()
    assert len(out) == 3
    orphans = {item["env_id"]: item["orphan"] for item in out}
    assert orphans == {1: False, 2: False, 3: True}


def test_recover_preserves_order_from_list_stale_environments() -> None:
    """Output ordering matches the input ordering of list_stale_environments."""
    store = _FakeStore(
        stale_envs=[
            {"id": 99, "task_id": 9},
            {"id": 50, "task_id": 5},
            {"id": 1, "task_id": 1},
        ],
        checkpoints={9: {"id": 1}, 5: {"id": 2}, 1: {"id": 3}},
        processes={},
    )
    rm = RecoveryManager(store)  # type: ignore[arg-type]
    out = rm.recover_stale()
    assert [item["env_id"] for item in out] == [99, 50, 1]


# Edge: env id / task_id coercion


def test_recover_coerces_str_env_and_task_ids_to_int() -> None:
    """The store may return string-typed ids; the manager must coerce."""
    store = _FakeStore(
        stale_envs=[{"id": "42", "task_id": "7"}],
        checkpoints={7: {"id": 1}},
    )
    rm = RecoveryManager(store)  # type: ignore[arg-type]
    out = rm.recover_stale()
    assert out[0]["env_id"] == 42
    assert out[0]["task_id"] == 7
    assert isinstance(out[0]["env_id"], int)
    assert isinstance(out[0]["task_id"], int)
