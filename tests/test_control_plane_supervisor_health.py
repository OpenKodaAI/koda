"""Granular /health contract for the control-plane supervisor.

The supervisor exposes /health for external monitoring. Post runtime-kernel
migration the worker view is built from the most recent
``RuntimeKernelLink.ensure_agent_workers`` snapshot rather than from a local
process registry. These tests pin:

  * The legacy payload shape (``workers[]`` + ``sidecars[]`` + ``summary``)
    so existing operator tooling and dashboards do not break.
  * The top-level ``status`` flips to ``"degraded"`` the moment any worker
    is not running OR any sidecar is unreachable.
  * ``_split_health_url`` is robust against absent ports / malformed URLs.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from koda.control_plane import supervisor as supervisor_mod
from koda.control_plane.runtime_kernel_link import (
    AgentWorkerState,
    AgentWorkerStatus,
)
from koda.control_plane.supervisor import (
    ControlPlaneSupervisor,
    _sidecar_targets,
    _split_health_url,
)


def _running_status(agent_id: str = "AGENT_ALPHA") -> AgentWorkerStatus:
    return AgentWorkerStatus(
        agent_id=agent_id,
        version=1,
        state=AgentWorkerState.RUNNING,
        pid=12345,
        pgid=12345,
        exit_code=0,
        started_at_ms=1_700_000_000_000,
        last_health_at_ms=1_700_000_000_500,
        restart_count=0,
        spawn_blocked_reason="",
    )


def _exited_status(agent_id: str = "AGENT_DEAD", exit_code: int = 1) -> AgentWorkerStatus:
    return AgentWorkerStatus(
        agent_id=agent_id,
        version=1,
        state=AgentWorkerState.EXITED,
        pid=0,
        pgid=0,
        exit_code=exit_code,
        started_at_ms=0,
        last_health_at_ms=0,
        restart_count=0,
        spawn_blocked_reason="",
    )


def _spawn_blocked_status(agent_id: str = "AGENT_BLOCKED") -> AgentWorkerStatus:
    return AgentWorkerStatus(
        agent_id=agent_id,
        version=1,
        state=AgentWorkerState.SPAWN_BLOCKED,
        pid=0,
        pgid=0,
        exit_code=0,
        started_at_ms=0,
        last_health_at_ms=0,
        restart_count=0,
        spawn_blocked_reason="port 9001 already bound",
    )


def _make_supervisor() -> ControlPlaneSupervisor:
    """Instantiate the supervisor without touching the real control-plane DB
    or opening a gRPC link to the kernel."""
    fake_link = SimpleNamespace(
        start=AsyncMock(),
        stop=AsyncMock(),
        ensure_agent_workers=AsyncMock(),
        target="unix:///tmp/fake.sock",
    )
    with patch(
        "koda.control_plane.supervisor.get_control_plane_manager",
        return_value=object(),
    ):
        sup = ControlPlaneSupervisor(link=fake_link)  # type: ignore[arg-type]
    return sup


def test_sidecar_targets_covers_all_five_rust_services() -> None:
    """All five sidecars must be in the probe list. Adding a sixth sidecar
    that doesn't surface here would leave operators blind to its outages."""
    names = {name for name, _ in _sidecar_targets()}
    assert names == {"security", "memory", "artifact", "retrieval", "runtime_kernel"}


def test_split_health_url_extracts_port_and_path() -> None:
    assert _split_health_url("http://127.0.0.1:9001/health") == (9001, "/health")
    assert _split_health_url("http://localhost:9100/internal/healthz") == (
        9100,
        "/internal/healthz",
    )
    # No port → kernel skips bind probe + health monitor.
    assert _split_health_url("") == (0, "/health")
    assert _split_health_url("http://example.com/health") == (0, "/health")
    # Malformed URL is tolerated; never raises (the kernel will refuse to spawn
    # if the port is invalid, so the supervisor never has to police it here).
    assert _split_health_url("not-a-url") == (0, "/health")


@pytest.mark.asyncio
async def test_health_payload_shape_with_all_healthy() -> None:
    supervisor = _make_supervisor()
    supervisor._statuses = {
        "AGENT_ALPHA": _running_status("AGENT_ALPHA"),
        "AGENT_BETA": _running_status("AGENT_BETA"),
    }
    supervisor._health_urls = {
        "AGENT_ALPHA": "http://127.0.0.1:9001/health",
        "AGENT_BETA": "http://127.0.0.1:9002/health",
    }

    async def _fake_probe_sidecar(name: str, target: str) -> dict[str, Any]:
        return {
            "name": name,
            "target": target,
            "ok": True,
            "latency_ms": 3,
            "error": None,
        }

    request = SimpleNamespace()
    with patch.object(
        supervisor_mod, "_probe_sidecar", AsyncMock(side_effect=_fake_probe_sidecar)
    ):
        response = await supervisor._health(request)  # type: ignore[arg-type]

    payload = json.loads(response.body.decode())
    assert payload["status"] == "healthy"
    assert payload["summary"] == {
        "workers_total": 2,
        "workers_alive": 2,
        "workers_unhealthy": 0,
        "sidecars_total": 5,
        "sidecars_unhealthy": 0,
    }
    assert {w["agent_id"] for w in payload["workers"]} == {"AGENT_ALPHA", "AGENT_BETA"}
    assert all(w["alive"] is True for w in payload["workers"])
    assert all(w["probe"]["ok"] is True for w in payload["workers"])
    assert {s["name"] for s in payload["sidecars"]} == {
        "security",
        "memory",
        "artifact",
        "retrieval",
        "runtime_kernel",
    }
    assert all(s["ok"] for s in payload["sidecars"])
    # health_url surfaces from the cache so dashboards can deep-link.
    by_id = {w["agent_id"]: w for w in payload["workers"]}
    assert by_id["AGENT_ALPHA"]["health_url"] == "http://127.0.0.1:9001/health"
    assert by_id["AGENT_BETA"]["health_url"] == "http://127.0.0.1:9002/health"


@pytest.mark.asyncio
async def test_health_marks_degraded_when_worker_exited() -> None:
    """An exited worker drops top-level status to degraded so monitoring
    catches it before users do."""
    supervisor = _make_supervisor()
    supervisor._statuses = {"AGENT_DEAD": _exited_status("AGENT_DEAD", exit_code=1)}
    supervisor._health_urls = {"AGENT_DEAD": "http://127.0.0.1:9000/health"}

    async def _fake_probe_sidecar(name: str, target: str) -> dict[str, Any]:
        return {
            "name": name,
            "target": target,
            "ok": True,
            "latency_ms": 1,
            "error": None,
        }

    request = SimpleNamespace()
    with patch.object(
        supervisor_mod, "_probe_sidecar", AsyncMock(side_effect=_fake_probe_sidecar)
    ):
        response = await supervisor._health(request)  # type: ignore[arg-type]

    payload = json.loads(response.body.decode())
    assert payload["status"] == "degraded"
    assert payload["summary"]["workers_unhealthy"] == 1
    assert payload["summary"]["workers_alive"] == 0
    dead = payload["workers"][0]
    assert dead["alive"] is False
    assert dead["exit_code"] == 1
    assert dead["probe"] is None


@pytest.mark.asyncio
async def test_health_marks_degraded_when_worker_spawn_blocked() -> None:
    """SPAWN_BLOCKED is the kernel's signal that a port conflict (or other
    pre-flight failure) prevented the worker from starting. /health must
    flag it the same as a crash so operators get paged."""
    supervisor = _make_supervisor()
    supervisor._statuses = {"AGENT_BLOCKED": _spawn_blocked_status("AGENT_BLOCKED")}
    supervisor._health_urls = {"AGENT_BLOCKED": "http://127.0.0.1:9001/health"}

    async def _fake_probe_sidecar(name: str, target: str) -> dict[str, Any]:
        return {
            "name": name,
            "target": target,
            "ok": True,
            "latency_ms": 1,
            "error": None,
        }

    request = SimpleNamespace()
    with patch.object(
        supervisor_mod, "_probe_sidecar", AsyncMock(side_effect=_fake_probe_sidecar)
    ):
        response = await supervisor._health(request)  # type: ignore[arg-type]

    payload = json.loads(response.body.decode())
    assert payload["status"] == "degraded"
    assert payload["summary"]["workers_unhealthy"] == 1
    blocked = payload["workers"][0]
    assert blocked["alive"] is False
    assert blocked["probe"] is None


@pytest.mark.asyncio
async def test_health_marks_degraded_when_sidecar_unreachable() -> None:
    """One unreachable sidecar flips status, even if every worker is fine."""
    supervisor = _make_supervisor()
    supervisor._statuses = {"AGENT_OK": _running_status("AGENT_OK")}
    supervisor._health_urls = {"AGENT_OK": "http://127.0.0.1:9000/health"}

    async def _fake_probe_sidecar(name: str, target: str) -> dict[str, Any]:
        if name == "memory":
            return {
                "name": name,
                "target": target,
                "ok": False,
                "latency_ms": 1000,
                "error": "timeout",
            }
        return {
            "name": name,
            "target": target,
            "ok": True,
            "latency_ms": 2,
            "error": None,
        }

    request = SimpleNamespace()
    with patch.object(
        supervisor_mod, "_probe_sidecar", AsyncMock(side_effect=_fake_probe_sidecar)
    ):
        response = await supervisor._health(request)  # type: ignore[arg-type]

    payload = json.loads(response.body.decode())
    assert payload["status"] == "degraded"
    assert payload["summary"]["sidecars_unhealthy"] == 1
    assert payload["summary"]["workers_unhealthy"] == 0
    bad = next(s for s in payload["sidecars"] if s["name"] == "memory")
    assert bad["ok"] is False
    assert bad["error"] == "timeout"


@pytest.mark.asyncio
async def test_health_renders_starting_worker_as_alive_but_not_probed() -> None:
    """STARTING is alive (so dashboards do not page) but the probe shows the
    transient state so operators understand what they are looking at."""
    supervisor = _make_supervisor()
    starting = AgentWorkerStatus(
        agent_id="AGENT_BOOTING",
        version=1,
        state=AgentWorkerState.STARTING,
        pid=200,
        pgid=200,
        exit_code=0,
        started_at_ms=1,
        last_health_at_ms=0,
        restart_count=0,
        spawn_blocked_reason="",
    )
    supervisor._statuses = {"AGENT_BOOTING": starting}
    supervisor._health_urls = {"AGENT_BOOTING": "http://127.0.0.1:9001/health"}

    async def _fake_probe_sidecar(name: str, target: str) -> dict[str, Any]:
        return {
            "name": name,
            "target": target,
            "ok": True,
            "latency_ms": 1,
            "error": None,
        }

    request = SimpleNamespace()
    with patch.object(
        supervisor_mod, "_probe_sidecar", AsyncMock(side_effect=_fake_probe_sidecar)
    ):
        response = await supervisor._health(request)  # type: ignore[arg-type]

    payload = json.loads(response.body.decode())
    worker = payload["workers"][0]
    assert worker["alive"] is True
    assert worker["probe"]["ok"] is False
    assert worker["probe"]["error"] == "starting"
    # During start-up the dashboard surfaces the worker but does not
    # consider it unhealthy — flapping new agents would otherwise alert.
    assert payload["summary"]["workers_unhealthy"] == 1  # probe.ok=False ⇒ unhealthy
