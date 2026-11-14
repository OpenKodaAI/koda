"""Blue/green drain HTTP contract.

The deploy pipeline POSTs to ``/cluster/drain`` on each old supervisor
when the new version becomes healthy. The supervisor flips its
``draining`` flag in ``cp_supervisor_runtimes`` so that on the next
heartbeat the cluster module RELEASES every claim instead of
refreshing them. The new version then immediately picks up ownership
and the rolling deploy completes without losing in-flight work.

These tests pin the HTTP contract by driving the handlers directly —
no aiohttp test server needed since the handlers are pure functions
of ``request`` plus the supervisor's ``_cluster`` instance.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from aiohttp.test_utils import TestClient, TestServer

from koda.control_plane import api as control_plane_api
from koda.control_plane import rate_limit
from koda.control_plane.operator_auth import OperatorAuthContext
from koda.control_plane.supervisor import ControlPlaneSupervisor


class _FakeCluster:
    def __init__(self, *, enabled: bool, draining: bool = False) -> None:
        self.config = SimpleNamespace(
            enabled=enabled,
            supervisor_id="sup_test",
            version="v1",
            host="localhost",
            capacity=10,
        )
        self._draining = draining
        self.set_draining_calls: list[bool] = []

    def is_draining(self) -> bool:
        return self._draining

    def list_owned_agents(self) -> set[str]:
        return {"AGENT_A", "AGENT_B"}

    def set_draining(self, value: bool) -> bool:
        self.set_draining_calls.append(value)
        self._draining = value
        return True


def _make_supervisor(*, enabled: bool, draining: bool = False) -> ControlPlaneSupervisor:
    with patch("koda.control_plane.supervisor.get_control_plane_manager", return_value=object()):
        sup = ControlPlaneSupervisor()
    sup._cluster = _FakeCluster(enabled=enabled, draining=draining)  # type: ignore[assignment]
    return sup


@pytest.mark.asyncio
async def test_status_reports_disabled_when_cluster_off() -> None:
    supervisor = _make_supervisor(enabled=False)
    response = await supervisor._cluster_status(SimpleNamespace())  # type: ignore[arg-type]
    body = await _decode(response)
    assert body == {"enabled": False, "reason": "KODA_CLUSTER_MODE != 'cluster'"}


@pytest.mark.asyncio
async def test_status_reports_owned_count_when_enabled() -> None:
    supervisor = _make_supervisor(enabled=True)
    response = await supervisor._cluster_status(SimpleNamespace())  # type: ignore[arg-type]
    body = await _decode(response)
    assert body["enabled"] is True
    assert body["supervisor_id"] == "sup_test"
    assert body["owned_count"] == 2
    assert body["owned_agents"] == ["AGENT_A", "AGENT_B"]
    assert body["draining"] is False


@pytest.mark.asyncio
async def test_drain_flips_draining_flag_to_true() -> None:
    supervisor = _make_supervisor(enabled=True)
    response = await supervisor._cluster_drain(SimpleNamespace())  # type: ignore[arg-type]
    body = await _decode(response)
    assert body == {"applied": True, "draining": True}
    cluster: Any = supervisor._cluster  # type: ignore[assignment]
    assert cluster.set_draining_calls == [True]


@pytest.mark.asyncio
async def test_undrain_flips_draining_flag_back() -> None:
    supervisor = _make_supervisor(enabled=True, draining=True)
    response = await supervisor._cluster_undrain(SimpleNamespace())  # type: ignore[arg-type]
    body = await _decode(response)
    assert body == {"applied": True, "draining": False}
    cluster: Any = supervisor._cluster  # type: ignore[assignment]
    assert cluster.set_draining_calls == [False]


@pytest.mark.asyncio
async def test_drain_returns_409_when_cluster_disabled() -> None:
    supervisor = _make_supervisor(enabled=False)
    response = await supervisor._cluster_drain(SimpleNamespace())  # type: ignore[arg-type]
    assert response.status == 409


@pytest.mark.asyncio
async def test_undrain_returns_409_when_cluster_disabled() -> None:
    supervisor = _make_supervisor(enabled=False)
    response = await supervisor._cluster_undrain(SimpleNamespace())  # type: ignore[arg-type]
    assert response.status == 409


async def _decode(response: Any) -> dict[str, Any]:
    import json

    return json.loads(response.body.decode())


_OPERATOR_TOKEN = "cluster-operator-token"


class _StubAuthService:
    """Knows one operator bearer token and nothing else."""

    def resolve_bearer_token(self, token: str) -> OperatorAuthContext | None:
        if token != _OPERATOR_TOKEN:
            return None
        return OperatorAuthContext(
            auth_kind="session",
            subject_type="operator",
            user_id="cluster-operator",
            username="cluster-operator",
            email=None,
            display_name=None,
        )


@pytest.fixture
async def cluster_client() -> AsyncIterator[tuple[TestClient, _FakeCluster]]:
    """The supervisor's own app, with its middleware stack, in front of a fake cluster."""
    supervisor = _make_supervisor(enabled=True)
    cluster: Any = supervisor._cluster
    rate_limit.clear_limiters()
    with patch.object(control_plane_api, "_auth_service", _StubAuthService):
        async with TestClient(TestServer(supervisor.build_app())) as client:
            yield client, cluster
    rate_limit.clear_limiters()


@pytest.mark.parametrize("path", ["/cluster/drain", "/cluster/undrain"])
@pytest.mark.parametrize("authorization", [None, "Bearer ", "Bearer wrong-token", f"Basic {_OPERATOR_TOKEN}"])
async def test_drain_endpoints_refuse_a_request_without_an_operator_token(
    cluster_client: tuple[TestClient, _FakeCluster], path: str, authorization: str | None
) -> None:
    """D-033: without a valid bearer the flag never changes."""
    client, cluster = cluster_client
    headers = {"Authorization": authorization} if authorization is not None else {}

    response = await client.post(path, headers=headers)

    assert response.status == 401
    assert await response.json() == {"error": "operator session is required"}
    assert cluster.set_draining_calls == []


@pytest.mark.parametrize(("path", "draining"), [("/cluster/drain", True), ("/cluster/undrain", False)])
async def test_drain_endpoints_accept_an_operator_token(
    cluster_client: tuple[TestClient, _FakeCluster], path: str, draining: bool
) -> None:
    client, cluster = cluster_client

    response = await client.post(path, headers={"Authorization": f"Bearer {_OPERATOR_TOKEN}"})

    assert response.status == 200
    assert await response.json() == {"applied": True, "draining": draining}
    assert cluster.set_draining_calls == [draining]


async def test_cluster_status_still_answers_without_a_token(cluster_client: tuple[TestClient, _FakeCluster]) -> None:
    client, _cluster = cluster_client

    response = await client.get("/cluster/status")

    assert response.status == 200
    assert (await response.json())["supervisor_id"] == "sup_test"


def test_the_drain_docs_and_the_cluster_smoke_send_a_token() -> None:
    root = Path(__file__).resolve().parents[1]
    cluster_mode = (root / "docs" / "operations" / "cluster-mode.md").read_text(encoding="utf-8")
    upgrade = (root / "docs" / "operations" / "upgrade.md").read_text(encoding="utf-8")
    smoke = (root / "scripts" / "cluster_smoke.sh").read_text(encoding="utf-8")

    assert "unauthenticated by design" not in cluster_mode
    assert (
        "| `POST /cluster/drain` | Sets `draining=true`. Next heartbeat releases all claims. | operator bearer token |"
        in (cluster_mode)
    )
    bearer = 'curl -fs -X POST -H "Authorization: Bearer ${CONTROL_PLANE_API_TOKEN%%,*}"'
    assert bearer in cluster_mode
    assert bearer in upgrade
    assert '| curl -fs -X POST -H @- "$0"' in smoke
    posts = [line for line in smoke.splitlines() if "/cluster/drain" in line or "/cluster/undrain" in line]
    assert [line for line in posts if not line.lstrip().startswith("#")] == [
        'cluster_post "${target_cid}" /cluster/drain >/dev/null',
        'cluster_post "${target_cid}" /cluster/undrain >/dev/null',
    ]
