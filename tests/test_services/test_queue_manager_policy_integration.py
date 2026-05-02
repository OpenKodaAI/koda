"""Phase A.1 — verify policy_engine wired into queue_manager hot path.

Without these tests the policy_engine wrappers from Phase 1C could
land but never actually be called, leaving multi-team fairness
unenforced even when a workspace policy exists. The tests are a
mixture of grep gates (cheap, regression-proof) plus runtime checks
of the helper-singleton lifecycle.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from koda.services import policy_engine_runtime


def _read_queue_manager() -> str:
    return Path("koda/services/queue_manager.py").read_text(encoding="utf-8")


def test_enqueue_calls_check_ingest_or_allow() -> None:
    """The ingest hot path must consult the policy engine BEFORE
    creating the task row — otherwise a denied message would still
    consume a task_id and pollute the queue table."""
    src = _read_queue_manager()
    enqueue_idx = src.index("\nasync def enqueue(\n")
    next_def = src.index("\nasync def ", enqueue_idx + 1)
    enqueue_body = src[enqueue_idx:next_def]
    assert "check_ingest_or_allow(" in enqueue_body, "enqueue() must call check_ingest_or_allow before create_task"
    create_task_idx = enqueue_body.index("create_task(")
    check_idx = enqueue_body.index("check_ingest_or_allow(")
    assert check_idx < create_task_idx, "policy check must run BEFORE create_task to avoid wasting task IDs"


def test_enqueue_returns_early_on_deny() -> None:
    src = _read_queue_manager()
    enqueue_idx = src.index("\nasync def enqueue(\n")
    next_def = src.index("\nasync def ", enqueue_idx + 1)
    enqueue_body = src[enqueue_idx:next_def]
    assert "if not decision.allowed:" in enqueue_body
    assert "Workspace policy blocked" in enqueue_body
    # The deny path must surface retry_after_ms when present so users
    # can back off rather than retry immediately and burn tokens.
    assert "retry_after_ms" in enqueue_body


def test_post_llm_records_spend() -> None:
    """After a successful LLM call (cost > 0), record_spend_safe must
    fire so the workspace's monthly cap reflects real consumption."""
    src = _read_queue_manager()
    assert "record_spend_safe(" in src
    assert "if cost > 0:" in src or "if cost > 0 :" in src


@pytest.mark.asyncio
async def test_singleton_returns_none_when_disabled() -> None:
    """When POLICY_ENGINE_ENABLED is False the helper must return
    None and never construct a client — zero overhead in single-tenant
    deployments without a configured workspace policy."""
    policy_engine_runtime._reset_for_tests()
    with patch("koda.config.POLICY_ENGINE_ENABLED", False):
        client = await policy_engine_runtime.get_policy_engine_client()
    assert client is None


@pytest.mark.asyncio
async def test_singleton_caches_started_client() -> None:
    """Repeated calls return the same instance — start() is called
    exactly once per process."""
    policy_engine_runtime._reset_for_tests()
    fake_client = AsyncMock()
    fake_client.start = AsyncMock()
    fake_client.stop = AsyncMock()

    with (
        patch("koda.config.POLICY_ENGINE_ENABLED", True),
        patch("koda.services.policy_engine_runtime.PolicyEngineClient", return_value=fake_client),
    ):
        a = await policy_engine_runtime.get_policy_engine_client()
        b = await policy_engine_runtime.get_policy_engine_client()
        c = await policy_engine_runtime.get_policy_engine_client()
    assert a is b is c is fake_client
    assert fake_client.start.await_count == 1


@pytest.mark.asyncio
async def test_singleton_marks_failed_after_start_error() -> None:
    """If the engine is unreachable at boot, start() raises and the
    helper records the failure — subsequent calls return None without
    retrying so a misconfigured deploy doesn't hammer a dead service."""
    policy_engine_runtime._reset_for_tests()
    fake_client = AsyncMock()
    fake_client.start = AsyncMock(side_effect=RuntimeError("connection refused"))

    with (
        patch("koda.config.POLICY_ENGINE_ENABLED", True),
        patch("koda.services.policy_engine_runtime.PolicyEngineClient", return_value=fake_client),
    ):
        first = await policy_engine_runtime.get_policy_engine_client()
        second = await policy_engine_runtime.get_policy_engine_client()
    assert first is None
    assert second is None
    # Only one start attempt — the failure short-circuits future calls.
    assert fake_client.start.await_count == 1


@pytest.mark.asyncio
async def test_shutdown_closes_client() -> None:
    """Worker shutdown must close the channel cleanly so the next
    boot starts with a fresh state."""
    policy_engine_runtime._reset_for_tests()
    fake_client = AsyncMock()
    fake_client.start = AsyncMock()
    fake_client.stop = AsyncMock()

    with (
        patch("koda.config.POLICY_ENGINE_ENABLED", True),
        patch("koda.services.policy_engine_runtime.PolicyEngineClient", return_value=fake_client),
    ):
        await policy_engine_runtime.get_policy_engine_client()
        await policy_engine_runtime.shutdown_policy_engine_client()
    fake_client.stop.assert_awaited_once()
