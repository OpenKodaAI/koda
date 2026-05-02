"""Granular /health contract for the control-plane supervisor.

The supervisor exposes /health for external monitoring. The legacy payload
returned only a static worker list (agent_id, version, pid, health_url),
which gave operators no signal about whether a worker process was actually
running, whether it was responding to its own liveness probe, or whether
the Rust sidecars (security/memory/artifact/retrieval/runtime-kernel) were
reachable.

These tests pin the granular contract: per-worker liveness + probe latency,
per-sidecar reachability + latency, and a top-level status that flips to
"degraded" the moment anything misbehaves. Without these, the only signal
operators got was end users complaining that messages stopped flowing.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from koda.control_plane import supervisor as supervisor_mod
from koda.control_plane.supervisor import (
    ControlPlaneSupervisor,
    _sidecar_targets,
    _WorkerState,
)


def _make_worker_state(*, agent_id: str = "AGENT_ALPHA", returncode: int | None = None) -> _WorkerState:
    process = SimpleNamespace(pid=12345, returncode=returncode)
    runtime = SimpleNamespace(health_url="http://127.0.0.1:9000/health")
    return _WorkerState(
        agent_id=agent_id,
        version=1,
        process=process,  # type: ignore[arg-type]
        runtime=runtime,  # type: ignore[arg-type]
    )


def _make_supervisor() -> ControlPlaneSupervisor:
    """Instantiate the supervisor without touching the real control-plane DB.

    ControlPlaneSupervisor.__init__ resolves the singleton manager which
    requires a live Postgres backend. Tests covering only /health do not
    exercise that path, so we stub the manager lookup.
    """
    with patch("koda.control_plane.supervisor.get_control_plane_manager", return_value=object()):
        return ControlPlaneSupervisor()


def test_sidecar_targets_covers_all_five_rust_services() -> None:
    """All five sidecars must be in the probe list. Adding a sixth sidecar
    that doesn't surface here would leave operators blind to its outages."""
    names = {name for name, _ in _sidecar_targets()}
    assert names == {"security", "memory", "artifact", "retrieval", "runtime_kernel"}


@pytest.mark.asyncio
async def test_health_payload_shape_with_all_healthy() -> None:
    supervisor = _make_supervisor()
    supervisor._workers = {
        "AGENT_ALPHA": _make_worker_state(agent_id="AGENT_ALPHA"),
        "AGENT_BETA": _make_worker_state(agent_id="AGENT_BETA"),
    }

    async def _fake_probe_worker(state: _WorkerState) -> dict[str, Any]:
        return {
            "alive": True,
            "exit_code": None,
            "probe": {
                "ok": True,
                "status_code": 200,
                "latency_ms": 7,
                "active_tasks": 0,
                "error": None,
            },
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
    with (
        patch.object(supervisor, "_probe_worker", AsyncMock(side_effect=_fake_probe_worker)),
        patch.object(supervisor_mod, "_probe_sidecar", AsyncMock(side_effect=_fake_probe_sidecar)),
    ):
        response = await supervisor._health(request)  # type: ignore[arg-type]

    body = response.body.decode()
    import json

    payload = json.loads(body)
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


@pytest.mark.asyncio
async def test_health_marks_degraded_when_worker_dead() -> None:
    """A worker whose process exited drops top-level status to degraded so
    monitoring catches it before users do."""
    supervisor = _make_supervisor()
    supervisor._workers = {
        "AGENT_DEAD": _make_worker_state(agent_id="AGENT_DEAD", returncode=1),
    }

    async def _fake_probe_worker(state: _WorkerState) -> dict[str, Any]:
        return {"alive": False, "exit_code": 1, "probe": None}

    async def _fake_probe_sidecar(name: str, target: str) -> dict[str, Any]:
        return {
            "name": name,
            "target": target,
            "ok": True,
            "latency_ms": 1,
            "error": None,
        }

    request = SimpleNamespace()
    with (
        patch.object(supervisor, "_probe_worker", AsyncMock(side_effect=_fake_probe_worker)),
        patch.object(supervisor_mod, "_probe_sidecar", AsyncMock(side_effect=_fake_probe_sidecar)),
    ):
        response = await supervisor._health(request)  # type: ignore[arg-type]

    import json

    payload = json.loads(response.body.decode())
    assert payload["status"] == "degraded"
    assert payload["summary"]["workers_unhealthy"] == 1
    assert payload["summary"]["workers_alive"] == 0
    dead = payload["workers"][0]
    assert dead["alive"] is False
    assert dead["exit_code"] == 1
    assert dead["probe"] is None


@pytest.mark.asyncio
async def test_health_marks_degraded_when_sidecar_unreachable() -> None:
    """One unreachable sidecar flips status, even if every worker is fine."""
    supervisor = _make_supervisor()
    supervisor._workers = {
        "AGENT_OK": _make_worker_state(agent_id="AGENT_OK"),
    }

    async def _fake_probe_worker(state: _WorkerState) -> dict[str, Any]:
        return {
            "alive": True,
            "exit_code": None,
            "probe": {
                "ok": True,
                "status_code": 200,
                "latency_ms": 4,
                "active_tasks": 0,
                "error": None,
            },
        }

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
    with (
        patch.object(supervisor, "_probe_worker", AsyncMock(side_effect=_fake_probe_worker)),
        patch.object(supervisor_mod, "_probe_sidecar", AsyncMock(side_effect=_fake_probe_sidecar)),
    ):
        response = await supervisor._health(request)  # type: ignore[arg-type]

    import json

    payload = json.loads(response.body.decode())
    assert payload["status"] == "degraded"
    assert payload["summary"]["sidecars_unhealthy"] == 1
    assert payload["summary"]["workers_unhealthy"] == 0
    bad = next(s for s in payload["sidecars"] if s["name"] == "memory")
    assert bad["ok"] is False
    assert bad["error"] == "timeout"


@pytest.mark.asyncio
async def test_probe_worker_handles_dead_process_without_http_call() -> None:
    """A dead worker must not trigger an HTTP probe — the process is gone,
    so opening a session would just hang on connection refused."""
    supervisor = _make_supervisor()
    state = _make_worker_state(returncode=137)

    with patch("koda.control_plane.supervisor.ClientSession") as session_factory:
        result = await supervisor._probe_worker(state)

    assert session_factory.call_count == 0
    assert result == {"alive": False, "exit_code": 137, "probe": None}
