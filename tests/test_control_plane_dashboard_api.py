"""Focused tests for control-plane dashboard route contracts."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web

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


class _JsonRequest(_Request):
    def __init__(
        self,
        *,
        match_info: dict[str, str] | None = None,
        payload: dict[str, object] | None = None,
    ) -> None:
        super().__init__(match_info=match_info)
        self.can_read_body = True
        self._payload = payload or {}
        self.app: dict[str, object] = {}

    async def json(self) -> dict[str, object]:
        return dict(self._payload)


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
async def test_list_agents_supports_search_and_pagination() -> None:
    manager = MagicMock()
    manager.list_agents.return_value = [
        {
            "id": f"AGENT_{index:02d}",
            "display_name": f"Agent {index:02d}",
            "appearance": {
                "label": f"Agent {index:02d}",
                "color": "#fff",
            },
            "organization": {
                "workspace_id": "alpha" if index < 6 else "beta",
                "workspace_name": "Alpha Workspace" if index < 6 else "Beta Workspace",
            },
        }
        for index in range(12)
    ]
    request = _Request(query={"q": "beta", "limit": "5", "offset": "0"})

    with patch("koda.control_plane.api._manager", return_value=manager):
        response = await control_plane_api.list_agents(request)

    payload = json.loads(response.text)
    assert [item["id"] for item in payload["items"]] == [
        "AGENT_06",
        "AGENT_07",
        "AGENT_08",
        "AGENT_09",
        "AGENT_10",
    ]
    assert payload["total"] == 6
    assert payload["limit"] == 5
    assert payload["offset"] == 0
    assert payload["has_more"] is True


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


@pytest.mark.asyncio
async def test_dashboard_executions_route_supports_deep_paginated_offsets() -> None:
    request = _Request(query={"paged": "1", "limit": "2", "offset": "1200"})
    manager = MagicMock()
    manager.list_agents.return_value = [{"id": "AGENT_A"}]
    rows = [
        {"bot_id": "AGENT_A", "task_id": 1201},
        {"bot_id": "AGENT_A", "task_id": 1202},
        {"bot_id": "AGENT_A", "task_id": 1203},
    ]

    with (
        patch("koda.control_plane.api._manager", return_value=manager),
        patch(
            "koda.control_plane.api.list_dashboard_execution_summaries",
            return_value=rows,
        ) as list_executions,
    ):
        response = await control_plane_api.list_dashboard_executions_route(request)

    payload = json.loads(response.text)
    list_executions.assert_called_once_with(
        agent_ids=["AGENT_A"],
        status=None,
        search=None,
        session_id=None,
        limit=3,
        offset=1200,
    )
    assert payload["items"] == rows[:2]
    assert payload["page"] == {
        "limit": 2,
        "offset": 1200,
        "returned": 2,
        "next_offset": 1202,
        "has_more": True,
        "total": None,
    }


@pytest.mark.asyncio
async def test_dashboard_squad_message_supervisor_dispatch_uses_http_request_app() -> None:
    thread = SimpleNamespace(
        id="thread-1",
        workspace_id="workspace-1",
        squad_id="squad-1",
        status="open",
        coordinator_agent_id="PM",
        owner_user_id=42,
        telegram_chat_id=None,
        telegram_message_thread_id=None,
    )
    request = _JsonRequest(
        match_info={"thread_id": "thread-1"},
        payload={"content": "Coordinate specialists", "from_agent": "operator"},
    )
    store = AsyncMock()
    store.post_thread_message = AsyncMock(return_value=101)
    store.notify_event = AsyncMock()
    store.get_thread = AsyncMock(return_value=thread)
    participants = [
        SimpleNamespace(agent_id="PM", left_at=None, paused=False),
        SimpleNamespace(agent_id="FE", left_at=None, paused=False),
    ]

    class _FakeEngine:
        def __init__(self, **_: object) -> None:
            pass

        async def coordinate_user_input(self, **kwargs: object) -> object:
            dispatch = kwargs["dispatch"]
            dispatched = await dispatch(
                SimpleNamespace(
                    agent_id="FE",
                    content="Task request",
                    metadata={},
                    task_descriptor=SimpleNamespace(id="task-1"),
                    request_id="coord-task-1",
                )
            )
            assert dispatched == 123
            return SimpleNamespace(
                coordinated=True,
                decision=SimpleNamespace(mode="parallel_delegation"),
                task_ids=["task-1"],
                dispatched_agents=["FE"],
            )

    dispatch_result = SimpleNamespace(enqueued_task_id=123, message_id=None)

    with (
        patch("koda.control_plane.api._authorize_request", return_value=None),
        patch(
            "koda.control_plane.api._request_auth_context",
            return_value=control_plane_api.OperatorAuthContext(
                auth_kind="session",
                subject_type="operator",
                user_id="usr_1",
                username="owner",
                email="owner@example.com",
                display_name="Owner",
            ),
        ),
        patch(
            "koda.control_plane.api._dashboard_squad_thread_access",
            AsyncMock(return_value=(SimpleNamespace(thread=thread), None)),
        ),
        patch("koda.squads.get_squad_thread_store", return_value=store),
        patch("koda.squads.sync_thread_participants_from_squad", AsyncMock(return_value=participants)),
        patch("koda.squads.build_squad_capability_summaries", AsyncMock(return_value=[])),
        patch(
            "koda.squads.get_squad_semantic_router",
            return_value=SimpleNamespace(
                rank_agents=AsyncMock(
                    return_value=SimpleNamespace(available=False, to_dict=lambda: {"available": False})
                )
            ),
        ),
        patch(
            "koda.squads.get_squad_mention_resolver",
            return_value=SimpleNamespace(
                resolve=AsyncMock(
                    return_value=SimpleNamespace(
                        has_resolved_mentions=False,
                        has_mentions=False,
                        resolved_agent_ids=[],
                        unresolved=[],
                        ambiguous={},
                    )
                )
            ),
        ),
        patch(
            "koda.squads.get_squad_triage_service",
            return_value=SimpleNamespace(
                triage_user_input=AsyncMock(
                    return_value=SimpleNamespace(
                        awareness_agent_ids=[],
                        proposal_candidates=[],
                        to_dict=lambda: {},
                    )
                )
            ),
        ),
        patch("koda.squads.should_use_coordinator_engine", return_value=True),
        patch("koda.squads.get_squad_task_store", return_value=MagicMock()),
        patch("koda.squads.SquadCoordinatorEngine", _FakeEngine),
        patch("koda.squads.dispatch_squad_turn", AsyncMock(return_value=dispatch_result)) as dispatch_turn,
        patch("koda.squads.record_squad_routing_decision", AsyncMock()),
    ):
        response = await control_plane_api.post_dashboard_squad_thread_message_route(request)

    payload = json.loads(response.text)
    assert payload["coordination"] == {
        "mode": "parallel_delegation",
        "tasks": ["task-1"],
        "agents": ["FE"],
    }
    dispatch_turn.assert_awaited_once()


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


def _room_store(*, status: str) -> AsyncMock:
    """A room store whose status change reports the status it found under the row lock.

    ``get_thread`` keeps answering the status the room had first, as a read taken before a
    concurrent change does.
    """
    store = AsyncMock()
    current = {"status": status}

    async def _transition(thread_id: str, new_status: str) -> tuple[SimpleNamespace, str]:
        previous = current["status"]
        current["status"] = new_status
        return SimpleNamespace(id=thread_id, status=new_status), previous

    store.get_thread = AsyncMock(return_value=SimpleNamespace(id="thread-1", status=status))
    store.transition_thread_status = AsyncMock(side_effect=_transition)
    store.post_thread_message = AsyncMock(return_value=7)
    store.notify_event = AsyncMock()
    return store


async def _patch_room_status(store: AsyncMock, status: str) -> web.Response:
    request = _JsonRequest(match_info={"thread_id": "thread-1"}, payload={"status": status})
    with (
        patch("koda.control_plane.api._authorize_request", return_value=None),
        patch(
            "koda.control_plane.api._request_auth_context",
            return_value=control_plane_api.OperatorAuthContext(
                auth_kind="session",
                subject_type="operator",
                user_id="usr_1",
                username="owner",
                email="owner@example.com",
                display_name="Owner",
            ),
        ),
        patch("koda.squads.threads.get_squad_thread_store", return_value=store),
    ):
        return await control_plane_api.patch_dashboard_room_route(request)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_an_operator_pause_posts_a_system_event_with_reason_operator() -> None:
    store = _room_store(status="open")

    response = await _patch_room_status(store, "paused")

    assert response.status == 200
    store.transition_thread_status.assert_awaited_once_with("thread-1", "paused")
    kwargs = store.post_thread_message.await_args.kwargs
    assert kwargs["thread_id"] == "thread-1"
    assert kwargs["from_agent"] == "system"
    assert kwargs["message_type"] == "system_event"
    assert kwargs["metadata"]["event_type"] == "thread_paused"
    assert kwargs["metadata"]["reason"] == "operator"
    assert kwargs["metadata"]["paused_by"] == "operator:owner"
    store.notify_event.assert_awaited_once()
    assert store.notify_event.await_args.kwargs["event_type"] == "thread_paused"


@pytest.mark.asyncio
@pytest.mark.parametrize(("current", "requested"), [("paused", "paused"), ("paused", "open"), ("open", "completed")])
async def test_a_room_status_change_that_is_not_a_pause_posts_no_pause_event(current: str, requested: str) -> None:
    store = _room_store(status=current)

    response = await _patch_room_status(store, requested)

    assert response.status == 200
    store.transition_thread_status.assert_awaited_once_with("thread-1", requested)
    store.post_thread_message.assert_not_awaited()
    store.notify_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_concurrent_operator_pauses_post_one_pause_event() -> None:
    # Both requests read the room open before either paused it; only the real open -> paused
    # transition posts the event.
    store = _room_store(status="open")

    first = await _patch_room_status(store, "paused")
    second = await _patch_room_status(store, "paused")

    assert (first.status, second.status) == (200, 200)
    assert store.transition_thread_status.await_count == 2
    store.post_thread_message.assert_awaited_once()
    store.notify_event.assert_awaited_once()


async def _patch_room(store: AsyncMock, payload: dict[str, object]) -> web.Response:
    request = _JsonRequest(match_info={"thread_id": "thread-1"}, payload=payload)
    with (
        patch("koda.control_plane.api._authorize_request", return_value=None),
        patch("koda.squads.threads.get_squad_thread_store", return_value=store),
    ):
        return await control_plane_api.patch_dashboard_room_route(request)  # type: ignore[arg-type]


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["budget_auto_paused", "budget_alert_80_sent", "photo_hash", "telegram_title_key"])
async def test_a_room_patch_refuses_metadata_the_server_owns(key: str) -> None:
    store = _room_store(status="paused")

    response = await _patch_room(store, {"title": "Room", "metadata": {key: False}})

    # A client cannot clear the budget sweep's flags, or any other key the server keeps, so the
    # whole patch is refused and nothing changes.
    assert response.status == 400
    assert key in json.loads(response.text)["error"]
    store.update_thread.assert_not_awaited()
    store.transition_thread_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_room_patch_sets_the_metadata_a_client_may_set() -> None:
    store = _room_store(status="open")

    response = await _patch_room(store, {"metadata": {"photo_url": "https://example.com/room.png"}})

    assert response.status == 200
    assert store.update_thread.await_args.kwargs["metadata_patch"] == {"photo_url": "https://example.com/room.png"}


@pytest.mark.asyncio
async def test_a_post_to_an_open_room_at_its_budget_cap_is_refused_with_the_reason() -> None:
    from decimal import Decimal

    thread = SimpleNamespace(
        id="thread-1",
        status="open",
        budget_usd_cap=Decimal("1.00"),
        cost_usd_accum=Decimal("1.00"),
    )
    store = AsyncMock()
    request = _JsonRequest(match_info={"thread_id": "thread-1"}, payload={"content": "Ship the page"})
    with (
        patch("koda.control_plane.api._authorize_request", return_value=None),
        patch(
            "koda.control_plane.api._dashboard_squad_thread_access",
            AsyncMock(return_value=(SimpleNamespace(thread=thread), None)),
        ),
        patch("koda.squads.get_squad_thread_store", return_value=store),
    ):
        response = await control_plane_api.post_dashboard_squad_thread_message_route(request)  # type: ignore[arg-type]

    # The room is open, but its spend reached the cap, so no turn would run: the operator is told
    # why instead of the message being stored for a dispatch that is refused.
    assert response.status == 409
    assert "budget cap" in json.loads(response.text)["error"]
    store.post_thread_message.assert_not_awaited()
