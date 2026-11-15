"""Operator squad-coordinator routes (M1-E5-T1).

Coordinator election and demotion are squad administration: agents reach them only as the
squad's current coordinator, and operators reach them through these control-plane routes,
scoped to the workspace that owns the squad.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.control_plane import api as control_plane_api
from koda.squads.access import SquadAccessService


class _Request:
    def __init__(
        self,
        *,
        match_info: dict[str, str],
        payload: dict[str, object] | None = None,
        query: dict[str, str] | None = None,
    ) -> None:
        self.match_info = match_info
        self.query = dict(query or {})
        self.headers: dict[str, str] = {}
        self.can_read_body = payload is not None
        self._payload = payload or {}
        self.app: dict[str, object] = {}

    async def json(self) -> dict[str, object]:
        return dict(self._payload)


def _operator() -> control_plane_api.OperatorAuthContext:
    return control_plane_api.OperatorAuthContext(
        auth_kind="session",
        subject_type="operator",
        user_id="usr_1",
        username="owner",
        email="owner@example.com",
        display_name="Owner",
    )


def _manager(*, squad_workspace_id: str = "acme") -> MagicMock:
    manager = MagicMock()
    manager._workspace_row.side_effect = lambda workspace_id: {"id": workspace_id}
    manager._squad_row.side_effect = lambda squad_id: {"id": squad_id, "workspace_id": squad_workspace_id}
    manager.get_agent_spec.return_value = {"tool_policy": {"allowed_tool_ids": []}}
    return manager


def _state(coordinator_agent_id: str | None) -> SimpleNamespace:
    return SimpleNamespace(coordinator_agent_id=coordinator_agent_id, election_policy="manual")


def _access() -> SquadAccessService:
    # The operator branch never opens the pool, so no database is needed here.
    return SquadAccessService(dsn="postgresql://unused/unused")


@pytest.mark.asyncio
async def test_operator_elects_a_squad_coordinator() -> None:
    service = AsyncMock()
    service.elect = AsyncMock(return_value=_state("PM"))
    manager = _manager()
    request = _Request(
        match_info={"workspace_id": "acme", "squad_id": "build"},
        payload={"agentId": "PM", "reason": "kickoff", "forceReplace": True},
    )
    with (
        patch("koda.control_plane.api._manager", return_value=manager),
        patch("koda.control_plane.api._require_auth_context", return_value=_operator()),
        patch("koda.squads.get_squad_access_service", return_value=_access()),
        patch("koda.squads.get_coordinator_service", return_value=service),
        patch("koda.squads.get_squad_thread_store", return_value=None),
    ):
        response = await control_plane_api.put_squad_coordinator_route(request)  # type: ignore[arg-type]
    assert response.status == 200
    assert json.loads(response.text)["coordinator_agent_id"] == "PM"
    kwargs = service.elect.await_args.kwargs
    assert kwargs["squad_id"] == "build"
    assert kwargs["agent_id"] == "PM"
    assert kwargs["triggered_by"] == "operator:owner"
    assert kwargs["reason"] == "kickoff"
    assert kwargs["force_replace"] is True
    assert kwargs["agent_spec"] == manager.get_agent_spec.return_value
    manager.get_agent_spec.assert_called_once_with("PM")


@pytest.mark.asyncio
async def test_operator_demotes_a_squad_coordinator() -> None:
    service = AsyncMock()
    service.demote = AsyncMock(return_value=_state(None))
    request = _Request(match_info={"workspace_id": "acme", "squad_id": "build"}, query={"reason": "rotation"})
    with (
        patch("koda.control_plane.api._manager", return_value=_manager()),
        patch("koda.control_plane.api._require_auth_context", return_value=_operator()),
        patch("koda.squads.get_squad_access_service", return_value=_access()),
        patch("koda.squads.get_coordinator_service", return_value=service),
        patch("koda.squads.get_squad_thread_store", return_value=None),
    ):
        response = await control_plane_api.delete_squad_coordinator_route(request)  # type: ignore[arg-type]
    assert response.status == 200
    assert json.loads(response.text)["coordinator_agent_id"] is None
    kwargs = service.demote.await_args.kwargs
    assert kwargs["squad_id"] == "build"
    assert kwargs["triggered_by"] == "operator:owner"
    assert kwargs["reason"] == "rotation"


@pytest.mark.asyncio
async def test_operator_cannot_administer_a_squad_of_another_workspace() -> None:
    service = AsyncMock()
    request = _Request(match_info={"workspace_id": "acme", "squad_id": "build"}, payload={"agentId": "PM"})
    with (
        patch("koda.control_plane.api._manager", return_value=_manager(squad_workspace_id="other")),
        patch("koda.control_plane.api._require_auth_context", return_value=_operator()),
        patch("koda.squads.get_squad_access_service", return_value=_access()),
        patch("koda.squads.get_coordinator_service", return_value=service),
    ):
        elect = await control_plane_api.put_squad_coordinator_route(request)  # type: ignore[arg-type]
        demote = await control_plane_api.delete_squad_coordinator_route(request)  # type: ignore[arg-type]
    assert elect.status == 403
    assert demote.status == 403
    assert service.mock_calls == []


@pytest.mark.asyncio
async def test_operator_election_reports_a_conflict() -> None:
    from koda.squads.coordinator import CoordinatorConflictError

    service = AsyncMock()
    service.elect = AsyncMock(side_effect=CoordinatorConflictError("squad 'build' already has coordinator 'PM'"))
    request = _Request(match_info={"workspace_id": "acme", "squad_id": "build"}, payload={"agentId": "OPS"})
    with (
        patch("koda.control_plane.api._manager", return_value=_manager()),
        patch("koda.control_plane.api._require_auth_context", return_value=_operator()),
        patch("koda.squads.get_squad_access_service", return_value=_access()),
        patch("koda.squads.get_coordinator_service", return_value=service),
        patch("koda.squads.get_squad_thread_store", return_value=None),
    ):
        response = await control_plane_api.put_squad_coordinator_route(request)  # type: ignore[arg-type]
    assert response.status == 409
    assert service.elect.await_args.kwargs["force_replace"] is False


def test_squad_coordinator_routes_are_registered() -> None:
    from aiohttp import web

    app = web.Application()
    control_plane_api.setup_control_plane_routes(app)
    path = "/api/control-plane/workspaces/{workspace_id}/squads/{squad_id}/coordinator"
    methods = {route.method for route in app.router.routes() if getattr(route.resource, "canonical", None) == path}
    assert {"PUT", "DELETE"} <= methods


@pytest.mark.asyncio
async def test_operator_cannot_elect_an_agent_outside_the_squad() -> None:
    service = AsyncMock()
    manager = _manager()
    manager.is_squad_member_agent.return_value = False
    request = _Request(match_info={"workspace_id": "acme", "squad_id": "build"}, payload={"agentId": "BETA_PM"})
    with (
        patch("koda.control_plane.api._manager", return_value=manager),
        patch("koda.control_plane.api._require_auth_context", return_value=_operator()),
        patch("koda.squads.get_squad_access_service", return_value=_access()),
        patch("koda.squads.get_coordinator_service", return_value=service),
        patch("koda.squads.get_squad_thread_store", return_value=None),
    ):
        response = await control_plane_api.put_squad_coordinator_route(request)  # type: ignore[arg-type]
    assert response.status == 400
    assert "BETA_PM" in json.loads(response.text)["error"]
    manager.is_squad_member_agent.assert_called_once_with("BETA_PM", "build")
    assert service.mock_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["false", "true", 0, 1, None])
async def test_operator_election_rejects_a_force_replace_that_is_not_a_boolean(value: object) -> None:
    service = AsyncMock()
    service.elect = AsyncMock(return_value=_state("OPS"))
    request = _Request(
        match_info={"workspace_id": "acme", "squad_id": "build"},
        payload={"agentId": "OPS", "forceReplace": value},
    )
    with (
        patch("koda.control_plane.api._manager", return_value=_manager()),
        patch("koda.control_plane.api._require_auth_context", return_value=_operator()),
        patch("koda.squads.get_squad_access_service", return_value=_access()),
        patch("koda.squads.get_coordinator_service", return_value=service),
        patch("koda.squads.get_squad_thread_store", return_value=None),
    ):
        response = await control_plane_api.put_squad_coordinator_route(request)  # type: ignore[arg-type]
    assert response.status == 400
    assert "forceReplace" in json.loads(response.text)["error"]
    service.elect.assert_not_awaited()


def test_squad_membership_of_an_elected_agent() -> None:
    import koda.control_plane.manager as manager_mod

    squads = {"build": {"id": "build", "workspace_id": "acme"}, "web": {"id": "web", "workspace_id": "acme"}}
    agents = {
        "PM": {"id": "PM", "workspace_id": "acme", "squad_id": "build"},
        "LEAD": {"id": "LEAD", "workspace_id": "acme", "squad_id": None},
        "WEB": {"id": "WEB", "workspace_id": "acme", "squad_id": "web"},
        "BETA_PM": {"id": "BETA_PM", "workspace_id": "beta", "squad_id": "ops"},
        "LONER": {"id": "LONER", "workspace_id": None, "squad_id": None},
    }

    def fetch_one(sql: str, params: tuple[object, ...]) -> object:
        table = squads if "cp_workspace_squads" in sql else agents
        return table.get(str(params[0]))

    manager = object.__new__(manager_mod.ControlPlaneManager)
    with patch.object(manager_mod, "fetch_one", fetch_one):
        # A member of the squad, or an agent of its workspace that is in no squad.
        assert manager.is_squad_member_agent("PM", "build") is True
        assert manager.is_squad_member_agent("LEAD", "build") is True
        # Another squad of the workspace, another workspace, no workspace, unknown agent or squad.
        assert manager.is_squad_member_agent("WEB", "build") is False
        assert manager.is_squad_member_agent("BETA_PM", "build") is False
        assert manager.is_squad_member_agent("LONER", "build") is False
        assert manager.is_squad_member_agent("GHOST", "build") is False
        assert manager.is_squad_member_agent("PM", "missing") is False
