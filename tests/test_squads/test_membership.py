"""Tests for squad membership reconciliation helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.squads.membership import build_squad_capability_hints, sync_thread_participants_from_squad
from koda.squads.threads import ParticipantInfo, ThreadDescriptor


def _thread(**overrides: object) -> ThreadDescriptor:
    base: dict[str, object] = {
        "id": "thread-1",
        "workspace_id": "ws",
        "squad_id": "sq",
        "owner_user_id": 1,
        "title": "Build",
        "status": "open",
        "coordinator_agent_id": "PM",
        "current_owner_agent_id": None,
        "parent_thread_id": None,
        "visibility": "squad",
        "telegram_chat_id": None,
        "telegram_message_thread_id": None,
        "budget_usd_cap": None,
        "cost_usd_accum": 0,
    }
    base.update(overrides)
    return ThreadDescriptor(**base)  # type: ignore[arg-type]


def _participant(agent_id: str, *, role: str = "worker") -> ParticipantInfo:
    return ParticipantInfo(
        thread_id="thread-1",
        agent_id=agent_id,
        role=role,
        joined_at=None,
        left_at=None,
        last_read_message_id=None,
        inbox_cursor=None,
        paused=False,
    )


@pytest.mark.asyncio
async def test_sync_thread_participants_adds_missing_squad_agents() -> None:
    store = AsyncMock()
    store.list_participants = AsyncMock(
        side_effect=[[_participant("PM", role="coordinator")], [_participant("PM"), _participant("FE")]]
    )
    store.add_participant = AsyncMock()
    manager = MagicMock()
    manager.list_agents.return_value = [
        {"id": "PM", "squad_id": "sq"},
        {"id": "FE", "squad_id": "sq"},
        {"id": "OTHER", "squad_id": "elsewhere"},
    ]

    with patch("koda.control_plane.manager.get_control_plane_manager", return_value=manager):
        participants = await sync_thread_participants_from_squad(store, thread=_thread())

    store.add_participant.assert_awaited_once_with(thread_id="thread-1", agent_id="FE", role="worker")
    assert [p.agent_id for p in participants] == ["PM", "FE"]


@pytest.mark.asyncio
async def test_sync_thread_participants_preserves_existing_joined_at_boundary() -> None:
    store = AsyncMock()
    store.list_participants = AsyncMock(return_value=[_participant("PM", role="coordinator"), _participant("FE")])
    store.add_participant = AsyncMock()
    manager = MagicMock()
    manager.list_agents.return_value = [{"id": "PM", "squad_id": "sq"}, {"id": "FE", "squad_id": "sq"}]

    with patch("koda.control_plane.manager.get_control_plane_manager", return_value=manager):
        participants = await sync_thread_participants_from_squad(store, thread=_thread())

    store.add_participant.assert_not_awaited()
    assert [p.agent_id for p in participants] == ["PM", "FE"]


@pytest.mark.asyncio
async def test_build_squad_capability_hints_derives_missing_cache_entries() -> None:
    cache = AsyncMock()
    cache.list_for_squad = AsyncMock(return_value=[])
    cache.upsert = AsyncMock()
    manager = MagicMock()
    manager.list_agents.return_value = [
        {"id": "FE", "display_name": "Sr. Frontend Engineer", "squad_id": "sq"},
    ]
    manager.get_agent_spec.return_value = {
        "mission_profile": {
            "role": "Frontend Engineer",
            "domains": ["React", "UI"],
            "delegate_when": "frontend implementation and design polish",
        },
        "tool_policy": {"allowed_tool_ids": ["file_write", "browser_navigate"]},
    }

    with (
        patch("koda.squads.membership.get_capability_cache", return_value=cache),
        patch("koda.control_plane.manager.get_control_plane_manager", return_value=manager),
    ):
        hints = await build_squad_capability_hints(squad_id="sq", participant_agent_ids=["FE"])

    assert "frontend" in hints["FE"].lower()
    assert "react" in hints["FE"].lower()
    cache.upsert.assert_awaited_once()
