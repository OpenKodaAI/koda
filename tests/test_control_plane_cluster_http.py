"""Phase 2E — blue/green drain HTTP contract.

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

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

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
