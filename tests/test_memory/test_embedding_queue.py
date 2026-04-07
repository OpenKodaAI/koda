"""Tests for the atomic embedding job claim in embedding_queue.py."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

from koda.memory.embedding_queue import (
    EmbeddingJob,
    claim_embedding_jobs,
)

_MODULE = "koda.memory.embedding_queue"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 1, 15, 12, 0, 0)


def _make_row(
    *,
    job_id: int = 1,
    memory_id: int = 100,
    agent_id: str = "AGENT_A",
    status: str = "processing",
    attempt_count: int = 0,
    last_error: str = "",
    next_retry_at: str | None = None,
    last_attempt_at: str | None = None,
    claimed_at: str | None = None,
    created_at: str = "2026-01-15T11:00:00",
    updated_at: str = "2026-01-15T12:00:00",
) -> dict[str, object]:
    return {
        "id": job_id,
        "memory_id": memory_id,
        "agent_id": agent_id,
        "status": status,
        "attempt_count": attempt_count,
        "last_error": last_error,
        "next_retry_at": next_retry_at,
        "last_attempt_at": last_attempt_at,
        "claimed_at": claimed_at,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def _run_coro(coro):
    """Resolve an awaitable synchronously for test purposes."""
    import asyncio

    return asyncio.run(coro)


def _patch_primary():
    """Return context-manager stack that stubs out the primary state backend."""
    return (
        patch(f"{_MODULE}.require_primary_state_backend", return_value=object()),
        patch(f"{_MODULE}.primary_fetch_all", new_callable=AsyncMock),
        patch(f"{_MODULE}.run_coro_sync", side_effect=_run_coro),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestClaimEmbeddingJobs:
    """Verify the atomic UPDATE...RETURNING claim path."""

    def test_returns_correct_number_of_jobs(self) -> None:
        rows = [
            _make_row(job_id=1, memory_id=100, claimed_at=_NOW.isoformat()),
            _make_row(job_id=2, memory_id=101, claimed_at=_NOW.isoformat()),
            _make_row(job_id=3, memory_id=102, claimed_at=_NOW.isoformat()),
        ]
        p_req, p_fetch, p_sync = _patch_primary()
        with p_req, p_fetch as mock_fetch, p_sync:
            mock_fetch.return_value = rows
            jobs = claim_embedding_jobs("AGENT_A", limit=5)

        assert len(jobs) == 3
        assert all(isinstance(j, EmbeddingJob) for j in jobs)

    def test_claimed_jobs_have_processing_status(self) -> None:
        rows = [_make_row(job_id=1, status="processing")]
        p_req, p_fetch, p_sync = _patch_primary()
        with p_req, p_fetch as mock_fetch, p_sync:
            mock_fetch.return_value = rows
            jobs = claim_embedding_jobs("AGENT_A")

        assert jobs[0].status == "processing"

    def test_only_eligible_jobs_claimed_via_query(self) -> None:
        """The SQL must filter by status IN ('pending', 'failed') -- verify the
        query text passed to primary_fetch_all contains the right predicates."""
        p_req, p_fetch, p_sync = _patch_primary()
        with p_req, p_fetch as mock_fetch, p_sync:
            mock_fetch.return_value = []
            claim_embedding_jobs("AGENT_A", limit=10)

        # primary_fetch_all receives (query, params, agent_id=...)
        call_args = mock_fetch.call_args
        query: str = call_args[0][0]
        assert "status IN ('pending', 'failed')" in query
        assert "UPDATE memory_embedding_jobs" in query
        assert "RETURNING" in query

    def test_limit_is_respected(self) -> None:
        p_req, p_fetch, p_sync = _patch_primary()
        with p_req, p_fetch as mock_fetch, p_sync:
            mock_fetch.return_value = []
            claim_embedding_jobs("AGENT_A", limit=7)

        call_args = mock_fetch.call_args
        params = call_args[0][1]
        # The limit value should appear as the last positional param
        assert params[-1] == 7

    def test_empty_result_when_no_eligible_jobs(self) -> None:
        p_req, p_fetch, p_sync = _patch_primary()
        with p_req, p_fetch as mock_fetch, p_sync:
            mock_fetch.return_value = []
            jobs = claim_embedding_jobs("AGENT_A")

        assert jobs == []

    def test_future_next_retry_at_skipped_via_query(self) -> None:
        """The query must include a predicate filtering out future next_retry_at."""
        p_req, p_fetch, p_sync = _patch_primary()
        with p_req, p_fetch as mock_fetch, p_sync:
            mock_fetch.return_value = []
            claim_embedding_jobs("AGENT_A")

        query: str = mock_fetch.call_args[0][0]
        assert "next_retry_at IS NULL OR next_retry_at <=" in query

    def test_single_db_round_trip(self) -> None:
        """The optimized path must issue exactly one call to primary_fetch_all,
        not three sequential operations."""
        rows = [_make_row(job_id=1)]
        p_req, p_fetch, p_sync = _patch_primary()
        with p_req, p_fetch as mock_fetch, p_sync:
            mock_fetch.return_value = rows
            claim_embedding_jobs("AGENT_A")

        assert mock_fetch.call_count == 1

    def test_agent_id_scoping(self) -> None:
        """The query must scope to the given agent_id."""
        p_req, p_fetch, p_sync = _patch_primary()
        with p_req, p_fetch as mock_fetch, p_sync:
            mock_fetch.return_value = []
            claim_embedding_jobs("MY_BOT", limit=4)

        params = mock_fetch.call_args[0][1]
        # normalize_agent_scope lowercases the agent_id
        assert "my_bot" in params
