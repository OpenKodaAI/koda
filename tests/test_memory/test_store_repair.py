"""Tests for parallel embedding repair in MemoryStore."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from koda.memory.store import MemoryStore


@dataclass(slots=True)
class _FakeJob:
    id: int
    memory_id: int
    agent_id: str = "agent_a"
    status: str = "pending"
    attempt_count: int = 0
    last_error: str = ""
    next_retry_at: datetime | None = None
    last_attempt_at: datetime | None = None
    claimed_at: datetime | None = None
    created_at: datetime = datetime(2025, 1, 1)
    updated_at: datetime = datetime(2025, 1, 1)


def _make_memory(memory_id: int, agent_id: str = "agent_a") -> MagicMock:
    mem = MagicMock()
    mem.id = memory_id
    mem.memory_id = memory_id
    mem.is_active = True
    mem.agent_id = agent_id
    return mem


@pytest.mark.asyncio
async def test_repair_processes_jobs_concurrently(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that multiple jobs overlap in time (run concurrently)."""
    store = MemoryStore("AGENT_A")

    jobs = [_FakeJob(id=i, memory_id=100 + i) for i in range(4)]
    timestamps: list[tuple[int, str]] = []

    def _slow_repair(self_ref: object, job: object) -> bool:
        job_id = getattr(job, "id", -1)
        timestamps.append((job_id, "start"))
        time.sleep(0.05)
        timestamps.append((job_id, "end"))
        return True

    with (
        patch("koda.memory.store.claim_embedding_jobs", return_value=jobs),
        patch("koda.memory.store.record_memory_quality_counter"),
        patch("koda.memory.store.get_embedding_job_stats", return_value={}),
    ):
        monkeypatch.setattr(MemoryStore, "_repair_single_job", _slow_repair)
        resolved = await store.repair_pending_embeddings()

    assert resolved == 4

    # If sequential, starts would strictly alternate with ends.
    # With concurrency, at least two jobs should have started before the first ends.
    first_end_idx = next(i for i, ts in enumerate(timestamps) if ts[1] == "end")
    starts_before_first_end = sum(1 for ts in timestamps[:first_end_idx] if ts[1] == "start")
    assert starts_before_first_end >= 2, (
        f"Expected concurrent starts before first end, got {starts_before_first_end}. Timestamps: {timestamps}"
    )


@pytest.mark.asyncio
async def test_repair_one_failure_does_not_abort_others(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failing job should not prevent other jobs from completing."""
    store = MemoryStore("AGENT_A")

    jobs = [_FakeJob(id=i, memory_id=200 + i) for i in range(3)]

    call_log: list[int] = []

    def _sometimes_failing_repair(self_ref: object, job: object) -> bool:
        jid = getattr(job, "id", -1)
        call_log.append(jid)
        if jid == 1:
            raise RuntimeError("simulated failure")
        return True

    with (
        patch("koda.memory.store.claim_embedding_jobs", return_value=jobs),
        patch("koda.memory.store.record_memory_quality_counter"),
        patch("koda.memory.store.get_embedding_job_stats", return_value={}),
    ):
        monkeypatch.setattr(MemoryStore, "_repair_single_job", _sometimes_failing_repair)
        resolved = await store.repair_pending_embeddings()

    # Job 1 failed, jobs 0 and 2 should succeed.
    assert resolved == 2
    # All three jobs were attempted.
    assert sorted(call_log) == [0, 1, 2]


@pytest.mark.asyncio
async def test_repair_no_jobs_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """When no jobs are claimed, return 0 without errors."""
    store = MemoryStore("AGENT_A")

    with patch("koda.memory.store.claim_embedding_jobs", return_value=[]):
        resolved = await store.repair_pending_embeddings()

    assert resolved == 0


@pytest.mark.asyncio
async def test_repair_single_job_skips_inactive_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    """_repair_single_job cancels job when memory is inactive."""
    store = MemoryStore("AGENT_A")

    job = _FakeJob(id=1, memory_id=300)
    inactive_mem = _make_memory(300)
    inactive_mem.is_active = False

    with (
        patch("koda.memory.store.get_entry", return_value=inactive_mem),
        patch("koda.memory.store.cancel_embedding_job") as mock_cancel,
    ):
        result = store._repair_single_job(job)

    assert result is False
    mock_cancel.assert_called_once_with(300, agent_id="agent_a")


@pytest.mark.asyncio
async def test_repair_single_job_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """_repair_single_job returns True for a valid active memory."""
    store = MemoryStore("AGENT_A")

    job = _FakeJob(id=1, memory_id=400)
    mem = _make_memory(400, agent_id="agent_a")

    with (
        patch("koda.memory.store.get_entry", return_value=mem),
        patch("koda.memory.store.update_embedding_state") as mock_update,
        patch("koda.memory.store.mark_embedding_job_completed") as mock_complete,
    ):
        result = store._repair_single_job(job)

    assert result is True
    mock_update.assert_called_once_with(400, vector_ref_id="", embedding_status="ready", attempts=0, last_error="")
    mock_complete.assert_called_once_with(400, agent_id="agent_a")
