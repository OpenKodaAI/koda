from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from koda.squads.capabilities import CapabilitySummary
from koda.squads.mentions import SquadMentionResolver
from koda.squads.threads import ParticipantInfo


def _participant(agent_id: str) -> ParticipantInfo:
    return ParticipantInfo(
        thread_id="thread-1",
        agent_id=agent_id,
        role="worker",
        joined_at=None,
        left_at=None,
        last_read_message_id=None,
        inbox_cursor=None,
        paused=False,
    )


@pytest.mark.asyncio
async def test_telegram_bot_username_resolves_to_agent_id() -> None:
    manager = MagicMock()
    manager.list_agents.return_value = [
        {"id": "FE", "metadata": {"telegram_username": "frontend_bot"}},
    ]

    with patch("koda.control_plane.manager.get_control_plane_manager", return_value=manager):
        result = await SquadMentionResolver().resolve(
            "@frontend_bot entregue a LP",
            participants=[_participant("FE"), _participant("PM")],
            channel="telegram",
            channel_context={},
            capability_summaries=[CapabilitySummary(agent_id="FE", display_name="Frontend Dev", role="frontend")],
        )

    assert result.resolved_agent_ids == ["FE"]
    assert result.unresolved == []


@pytest.mark.asyncio
async def test_telegram_display_name_resolves_to_active_participant() -> None:
    result = await SquadMentionResolver().resolve(
        "@frontend-dev revise esta tela",
        participants=[_participant("FE"), _participant("PM")],
        channel="telegram",
        channel_context={},
        capability_summaries=[CapabilitySummary(agent_id="FE", display_name="Frontend Dev", role="frontend")],
    )

    assert result.resolved_agent_ids == ["FE"]


@pytest.mark.asyncio
async def test_telegram_entity_mention_uses_entity_text() -> None:
    entity = SimpleNamespace(type="mention", offset=0, length=13, user=None)
    message = SimpleNamespace(entities=[entity], caption_entities=None, parse_entity=lambda _: "@frontend_bot")
    manager = MagicMock()
    manager.list_agents.return_value = [
        {"id": "FE", "metadata": {"telegram_username": "frontend_bot"}},
    ]

    with patch("koda.control_plane.manager.get_control_plane_manager", return_value=manager):
        result = await SquadMentionResolver().resolve(
            "@frontend_bot faça o frontend",
            participants=[_participant("FE")],
            channel="telegram",
            channel_context={"message": message},
            capability_summaries=[CapabilitySummary(agent_id="FE", display_name="Frontend Dev", role="frontend")],
        )

    assert result.resolved_agent_ids == ["FE"]


@pytest.mark.asyncio
async def test_unknown_telegram_mention_is_unresolved() -> None:
    result = await SquadMentionResolver().resolve(
        "@ghost faça isso",
        participants=[_participant("FE")],
        channel="telegram",
        channel_context={},
        capability_summaries=[CapabilitySummary(agent_id="FE", display_name="Frontend Dev", role="frontend")],
    )

    assert result.resolved_agent_ids == []
    assert result.unresolved == ["@ghost"]


@pytest.mark.asyncio
async def test_web_mention_uses_same_resolver_with_display_alias() -> None:
    result = await SquadMentionResolver().resolve(
        "@frontend-dev please review",
        participants=[_participant("FE")],
        channel="web",
        channel_context={},
        capability_summaries=[CapabilitySummary(agent_id="FE", display_name="Frontend Dev", role="frontend")],
    )

    assert result.resolved_agent_ids == ["FE"]
