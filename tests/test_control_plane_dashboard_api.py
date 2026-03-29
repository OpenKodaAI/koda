"""Focused tests for control-plane dashboard route contracts."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from koda.control_plane import api as control_plane_api


class _Request:
    def __init__(
        self,
        *,
        match_info: dict[str, str] | None = None,
        query: dict[str, str] | None = None,
    ) -> None:
        self.match_info = match_info or {}
        self.query = _Query(query or {})
        self.headers: dict[str, str] = {}
        self.can_read_body = False


class _Query(dict[str, str]):
    def getall(self, key: str, default: list[str] | None = None) -> list[str]:
        value = self.get(key)
        if value is None:
            return list(default or [])
        return [value]


@pytest.mark.asyncio
async def test_dashboard_agent_summaries_include_agent_metadata() -> None:
    request = _Request()
    manager = MagicMock()
    manager.list_agents.return_value = [
        {
            "id": "AGENT_A",
            "display_name": "AGENT_A",
            "appearance": {"label": "AGENT_A", "color": "#fff"},
        }
    ]
    with (
        patch(
            "koda.control_plane.api.list_dashboard_agent_summaries",
            return_value=[{"agentId": "AGENT_A", "totalTasks": 12, "dbExists": True}],
        ),
        patch("koda.control_plane.api._manager", return_value=manager),
    ):
        response = await control_plane_api.list_dashboard_agent_summaries_route(request)

    payload = json.loads(response.text)
    assert payload[0]["agent"]["id"] == "AGENT_A"
    assert payload[0]["totalTasks"] == 12


@pytest.mark.asyncio
async def test_dashboard_agent_stats_route_strips_nested_agent_summary() -> None:
    request = _Request(match_info={"agent_id": "AGENT_A"})
    manager = MagicMock()
    manager.get_dashboard_agent_summary.return_value = {
        "agentId": "AGENT_A",
        "totalTasks": 3,
        "dbExists": True,
        "agent": {"id": "AGENT_A", "display_name": "AGENT_A"},
    }
    with patch("koda.control_plane.api._manager", return_value=manager):
        response = await control_plane_api.get_dashboard_agent_stats_route(request)

    payload = json.loads(response.text)
    assert payload["agentId"] == "AGENT_A"
    assert "agent" not in payload
