"""Tests for the squad coordinator service."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import suppress
from unittest.mock import AsyncMock

import pytest

from koda.squads.coordinator import (
    REQUIRED_COORDINATOR_TOOL_IDS,
    CoordinatorConflictError,
    CoordinatorEligibilityError,
    CoordinatorNotFoundError,
    CoordinatorService,
    validate_eligibility,
)


def _schema() -> str:
    return (os.environ.get("KNOWLEDGE_V2_POSTGRES_SCHEMA") or "knowledge_v2").strip() or "knowledge_v2"


# --- pure unit tests (no PG) ---


def test_validate_eligibility_skips_when_spec_none() -> None:
    ok, missing = validate_eligibility(None)
    assert ok is True
    assert missing == []


def test_validate_eligibility_passes_with_all_tools() -> None:
    spec = {"tool_policy": {"allowed_tool_ids": list(REQUIRED_COORDINATOR_TOOL_IDS)}}
    ok, missing = validate_eligibility(spec)
    assert ok is True
    assert missing == []


def test_validate_eligibility_lists_missing_tools() -> None:
    spec = {"tool_policy": {"allowed_tool_ids": ["agent_delegate", "squad_post"]}}
    ok, missing = validate_eligibility(spec)
    assert ok is False
    assert "squad_task_create" in missing
    assert "squad_thread_create" in missing


def test_validate_eligibility_rejects_non_dict_policy() -> None:
    ok, missing = validate_eligibility({"tool_policy": "not-a-dict"})
    assert ok is False
    assert set(missing) == set(REQUIRED_COORDINATOR_TOOL_IDS)


def test_service_rejects_invalid_schema() -> None:
    with pytest.raises(ValueError):
        CoordinatorService(dsn="postgresql://x/y", schema="bad-schema!")


# --- PG-marked tests ---


@pytest.fixture
async def clean_state(migrated_postgres: str) -> AsyncIterator[str]:
    import asyncpg  # type: ignore[import-not-found]

    schema = _schema()
    conn = await asyncpg.connect(migrated_postgres)
    try:
        await conn.execute(f'TRUNCATE TABLE "{schema}"."squad_coordinator_history" RESTART IDENTITY')
        await conn.execute(f'TRUNCATE TABLE "{schema}"."squad_coordinator_state"')
    finally:
        await conn.close()
    yield migrated_postgres


@pytest.fixture
async def service(clean_state: str) -> AsyncIterator[CoordinatorService]:
    s = CoordinatorService(dsn=clean_state, schema=_schema())
    try:
        yield s
    finally:
        with suppress(Exception):
            await s.close()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_elect_first_coordinator(service: CoordinatorService) -> None:
    state = await service.elect(squad_id="build", agent_id="PM", triggered_by="admin")
    assert state.coordinator_agent_id == "PM"
    assert state.election_policy == "manual"
    assert state.elected_by_agent_id == "admin"


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_elect_eligibility_blocks_promotion(service: CoordinatorService) -> None:
    spec = {"tool_policy": {"allowed_tool_ids": ["squad_post"]}}
    with pytest.raises(CoordinatorEligibilityError):
        await service.elect(squad_id="build", agent_id="X", agent_spec=spec)
    state = await service.current_coordinator("build")
    assert state is None


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_elect_conflict_without_force(service: CoordinatorService) -> None:
    await service.elect(squad_id="build", agent_id="PM")
    with pytest.raises(CoordinatorConflictError):
        await service.elect(squad_id="build", agent_id="OPS")


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_elect_force_replace(service: CoordinatorService) -> None:
    await service.elect(squad_id="build", agent_id="PM")
    state = await service.elect(squad_id="build", agent_id="OPS", force_replace=True, reason="rotation")
    assert state.coordinator_agent_id == "OPS"
    history = await service.list_history(squad_id="build")
    events = [h.event_type for h in history]
    assert "elected" in events
    assert "replaced" in events


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_demote_clears_state(service: CoordinatorService) -> None:
    await service.elect(squad_id="build", agent_id="PM")
    state = await service.demote(squad_id="build", reason="paused")
    assert state.coordinator_agent_id is None
    fresh = await service.current_coordinator("build")
    assert fresh is not None
    assert fresh.coordinator_agent_id is None


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_demote_when_no_coordinator_raises(service: CoordinatorService) -> None:
    with pytest.raises(CoordinatorNotFoundError):
        await service.demote(squad_id="build")


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_set_election_policy_updates_state(service: CoordinatorService) -> None:
    state = await service.set_election_policy(
        squad_id="build",
        policy="auto_first_active",
        triggered_by="admin",
        auto_demote_after_inactive_days=7,
    )
    assert state.election_policy == "auto_first_active"
    assert state.auto_demote_after_inactive_days == 7
    history = await service.list_history(squad_id="build", limit=1)
    assert history and history[0].event_type == "policy_changed"


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_emits_thread_system_event_on_elect(service: CoordinatorService) -> None:
    fake_thread = type("FakeThread", (), {"id": "00000000-0000-0000-0000-000000000001"})()
    thread_store = AsyncMock()
    thread_store.list_threads = AsyncMock(return_value=[fake_thread])
    thread_store.post_thread_message = AsyncMock(return_value=42)
    await service.elect(
        squad_id="build",
        agent_id="PM",
        triggered_by="admin",
        thread_store=thread_store,
    )
    thread_store.list_threads.assert_awaited_once_with(squad_id="build", status="open")
    thread_store.post_thread_message.assert_awaited_once()
    call_kwargs = thread_store.post_thread_message.await_args.kwargs
    assert call_kwargs["thread_id"] == "00000000-0000-0000-0000-000000000001"
    assert call_kwargs["message_type"] == "system_event"
    assert call_kwargs["metadata"]["event_type"] == "coordinator_changed"
    assert call_kwargs["metadata"]["new_coordinator"] == "PM"


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_thread_event_emission_failure_does_not_raise(service: CoordinatorService) -> None:
    thread_store = AsyncMock()
    thread_store.list_threads = AsyncMock(side_effect=RuntimeError("db down"))
    state = await service.elect(squad_id="build", agent_id="PM", thread_store=thread_store)
    assert state.coordinator_agent_id == "PM"


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_history_listing_orders_recent_first(service: CoordinatorService) -> None:
    await service.elect(squad_id="build", agent_id="A")
    await service.elect(squad_id="build", agent_id="B", force_replace=True)
    await service.demote(squad_id="build")
    history = await service.list_history(squad_id="build", limit=10)
    events = [h.event_type for h in history]
    assert events[0] == "demoted"
    assert "replaced" in events
    assert "elected" in events


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_elect_emits_audit_event(service: CoordinatorService) -> None:
    """Coordinator elect/demote must surface in ``audit_events`` for governance."""
    from unittest.mock import patch

    with patch("koda.control_plane.audit.record_audit_event") as mock_record:
        await service.elect(squad_id="build", agent_id="PM", triggered_by="admin", reason="kickoff")
        await service.demote(squad_id="build", triggered_by="admin", reason="rotation")

    elect_calls = [c for c in mock_record.call_args_list if "elected" in str(c.kwargs.get("event_type"))]
    demote_calls = [c for c in mock_record.call_args_list if "demoted" in str(c.kwargs.get("event_type"))]
    assert elect_calls, "expected at least one elected audit event"
    assert demote_calls, "expected at least one demoted audit event"
    elect_kwargs = elect_calls[0].kwargs
    assert elect_kwargs["event_type"] == "squad.coordinator.elected"
    assert elect_kwargs["details"]["squad_id"] == "build"
    assert elect_kwargs["details"]["new_coordinator"] == "PM"
    demote_kwargs = demote_calls[0].kwargs
    assert demote_kwargs["event_type"] == "squad.coordinator.demoted"
    assert demote_kwargs["details"]["previous_coordinator"] == "PM"


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_elect_swallows_audit_failure(service: CoordinatorService) -> None:
    from unittest.mock import patch

    with patch(
        "koda.control_plane.audit.record_audit_event",
        side_effect=RuntimeError("audit DB down"),
    ):
        # Must not raise — coordinator op already succeeded; missing audit
        # is governance debt, not a correctness issue.
        state = await service.elect(squad_id="build", agent_id="PM", triggered_by="admin")
    assert state.coordinator_agent_id == "PM"
