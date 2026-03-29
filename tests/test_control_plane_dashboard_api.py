"""Focused tests for control-plane dashboard route contracts."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from koda.control_plane import api as control_plane_api
from koda.control_plane.dashboard_service import _serialize_execution_summary


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


def test_serialize_execution_summary_exposes_feedback_and_provenance() -> None:
    row = {
        "id": 77,
        "agent_id": "AGENT_A",
        "status": "completed",
        "query_text": "Deploy release",
        "model": "claude-opus-4-6",
        "session_id": "session-1",
        "user_id": 101,
        "chat_id": 202,
        "created_at": "2026-03-28T10:00:00.000Z",
        "started_at": "2026-03-28T10:00:05.000Z",
        "completed_at": "2026-03-28T10:01:05.000Z",
        "cost_usd": 1.25,
        "attempt": 1,
        "max_attempts": 3,
        "error_message": None,
    }
    trace = {
        "runtime": {"stop_reason": "completed"},
        "_duration_ms": 60000,
        "assistant": {"response_text": "Done"},
        "tools": [],
    }
    episode = {
        "feedback_status": "approved",
        "retrieval_trace_id": 9,
        "retrieval_strategy": "hybrid",
        "grounding_score": 0.91,
        "citation_coverage": 0.82,
        "answer_citation_coverage": 0.75,
        "answer_gate_status": "approved",
        "answer_gate_reasons_json": ["approved"],
        "stale_sources_present": False,
        "ungrounded_operationally": False,
        "post_write_review_required": False,
        "source_refs_json": [{"source_label": "policy.toml"}],
        "winning_sources_json": ["source-a"],
    }

    payload = _serialize_execution_summary(row, trace, episode)

    assert payload["feedback_status"] == "approved"
    assert payload["retrieval_strategy"] == "hybrid"
    assert payload["answer_gate_status"] == "approved"
    assert payload["source_ref_count"] == 1
    assert payload["winning_source_count"] == 1
    assert payload["provenance_source"] == "episode"
