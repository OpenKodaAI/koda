"""Tests for koda.services.runtime.recovery_manager.RecoveryManager.

The recovery manager picks one of three actions for each stale environment:

  * ``reattach`` — at least one of the recorded processes is still alive
    (status != "exited"); the supervisor reconnects.
  * ``reconstruct`` — no live processes but the latest checkpoint exists;
    rebuild the workspace from the checkpoint.
  * ``mark_recoverable_failed`` — neither: the env is unrecoverable but
    not yet finalized; flag for operator triage.

Decision tree is order-sensitive: alive_processes wins, then checkpoint,
then mark_recoverable_failed.
"""

from __future__ import annotations

from typing import Any

from koda.services.runtime.recovery_manager import RecoveryManager


class _FakeStore:
    """Minimal RuntimeStore stand-in for recovery-manager tests."""

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


# ---------------------------------------------------------------------------
# No stale envs → no-op
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# reattach: live processes present
# ---------------------------------------------------------------------------


def test_recover_reattach_when_at_least_one_process_alive() -> None:
    store = _FakeStore(
        stale_envs=[{"id": 100, "task_id": 1}],
        processes={
            (1, 100): [
                {"pid": 1234, "status": "running"},
                {"pid": 5678, "status": "exited"},  # one dead, one alive → reattach
            ],
        },
    )
    rm = RecoveryManager(store)  # type: ignore[arg-type]
    out = rm.recover_stale()
    assert out == [
        {"env_id": 100, "task_id": 1, "action": "reattach", "alive_process_count": 1}
    ]


def test_recover_reattach_counts_all_alive_processes() -> None:
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
    assert out[0]["alive_process_count"] == 3


def test_recover_reattach_status_other_than_exited_counts_as_alive() -> None:
    """Only literal status == 'exited' is treated as dead. Anything else
    (running, suspended, '', None, 'paused') counts as alive."""
    for status in ("running", "suspended", "paused", "", None, "wedged"):
        store = _FakeStore(
            stale_envs=[{"id": 1, "task_id": 1}],
            processes={(1, 1): [{"pid": 99, "status": status}]},
        )
        rm = RecoveryManager(store)  # type: ignore[arg-type]
        out = rm.recover_stale()
        assert out[0]["action"] == "reattach", f"status={status!r} should count as alive"


def test_recover_reattach_takes_precedence_over_checkpoint() -> None:
    """If processes are alive, the checkpoint path is skipped."""
    store = _FakeStore(
        stale_envs=[{"id": 1, "task_id": 1}],
        checkpoints={1: {"id": 99}},  # has a checkpoint
        processes={(1, 1): [{"pid": 1, "status": "running"}]},
    )
    rm = RecoveryManager(store)  # type: ignore[arg-type]
    out = rm.recover_stale()
    assert out[0]["action"] == "reattach"
    assert "checkpoint_id" not in out[0]


# ---------------------------------------------------------------------------
# reconstruct: no live processes but a checkpoint exists
# ---------------------------------------------------------------------------


def test_recover_reconstruct_when_only_checkpoint_present() -> None:
    store = _FakeStore(
        stale_envs=[{"id": 50, "task_id": 5}],
        checkpoints={5: {"id": 9999}},
        processes={(5, 50): [{"pid": 1, "status": "exited"}]},
    )
    rm = RecoveryManager(store)  # type: ignore[arg-type]
    out = rm.recover_stale()
    assert out == [
        {"env_id": 50, "task_id": 5, "action": "reconstruct", "checkpoint_id": 9999}
    ]


def test_recover_reconstruct_when_no_processes_recorded() -> None:
    """Empty process list with a checkpoint → reconstruct."""
    store = _FakeStore(
        stale_envs=[{"id": 7, "task_id": 7}],
        checkpoints={7: {"id": 1234}},
        processes={(7, 7): []},
    )
    rm = RecoveryManager(store)  # type: ignore[arg-type]
    out = rm.recover_stale()
    assert out[0]["action"] == "reconstruct"
    assert out[0]["checkpoint_id"] == 1234


# ---------------------------------------------------------------------------
# mark_recoverable_failed: neither processes nor checkpoint
# ---------------------------------------------------------------------------


def test_recover_marks_recoverable_failed_when_nothing_to_recover() -> None:
    store = _FakeStore(
        stale_envs=[{"id": 11, "task_id": 1}],
        checkpoints={},
        processes={},
    )
    rm = RecoveryManager(store)  # type: ignore[arg-type]
    out = rm.recover_stale()
    assert out == [{"env_id": 11, "task_id": 1, "action": "mark_recoverable_failed"}]


def test_recover_marks_recoverable_failed_when_only_dead_processes() -> None:
    store = _FakeStore(
        stale_envs=[{"id": 11, "task_id": 1}],
        processes={(1, 11): [{"pid": 1, "status": "exited"}, {"pid": 2, "status": "exited"}]},
    )
    rm = RecoveryManager(store)  # type: ignore[arg-type]
    out = rm.recover_stale()
    assert out[0]["action"] == "mark_recoverable_failed"


# ---------------------------------------------------------------------------
# Multiple stale envs in one sweep
# ---------------------------------------------------------------------------


def test_recover_handles_mix_of_actions_in_one_sweep() -> None:
    store = _FakeStore(
        stale_envs=[
            {"id": 1, "task_id": 10},
            {"id": 2, "task_id": 20},
            {"id": 3, "task_id": 30},
        ],
        checkpoints={20: {"id": 200}},
        processes={
            (10, 1): [{"pid": 1, "status": "running"}],   # reattach
            (20, 2): [{"pid": 2, "status": "exited"}],    # checkpoint → reconstruct
            (30, 3): [],                                  # nothing → mark failed
        },
    )
    rm = RecoveryManager(store)  # type: ignore[arg-type]
    out = rm.recover_stale()
    assert len(out) == 3
    actions = {item["env_id"]: item["action"] for item in out}
    assert actions == {1: "reattach", 2: "reconstruct", 3: "mark_recoverable_failed"}


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


# ---------------------------------------------------------------------------
# Edge: env id / task_id coercion
# ---------------------------------------------------------------------------


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
