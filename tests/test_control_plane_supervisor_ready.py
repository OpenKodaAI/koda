"""``/ready`` answers 503 when a critical dependency is down (M7-E1-T1, D-105).

``/health`` stays a liveness probe: it reports ``degraded`` but answers 200.
``/ready`` is what the compose healthcheck uses, so ``depends_on:
service_healthy`` waits for Postgres and the runtime kernel.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from koda import config as config_module
from koda.control_plane import supervisor as supervisor_mod
from koda.control_plane.supervisor import ControlPlaneSupervisor

ROOT = Path(__file__).resolve().parents[1]


def _make_supervisor() -> ControlPlaneSupervisor:
    fake_link = SimpleNamespace(start=AsyncMock(), stop=AsyncMock(), ensure_agent_workers=AsyncMock(), target="x")
    with patch("koda.control_plane.supervisor.get_control_plane_manager", return_value=object()):
        return ControlPlaneSupervisor(link=fake_link)  # type: ignore[arg-type]


def _check(name: str, ok: bool) -> dict[str, Any]:
    return {"name": name, "ok": ok, "latency_ms": 1, "error": None if ok else "down"}


def _sidecar(ok: bool) -> AsyncMock:
    return AsyncMock(side_effect=lambda name, target: {**_check(name, ok), "target": target})


@pytest.mark.asyncio
async def test_ready_is_200_when_postgres_and_kernel_are_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_module, "STATE_BACKEND", "postgres")
    supervisor = _make_supervisor()
    with (
        patch.object(supervisor_mod, "_probe_postgres", AsyncMock(return_value=_check("postgres", True))),
        patch.object(supervisor_mod, "_probe_sidecar", _sidecar(True)),
    ):
        response = await supervisor._ready(SimpleNamespace())  # type: ignore[arg-type]

    assert response.status == 200
    payload = json.loads(response.body.decode())
    assert payload["status"] == "ready"
    assert {c["name"] for c in payload["checks"]} == {"postgres", "runtime_kernel"}
    # /ready is unauthenticated: it carries no internal addresses.
    assert all("target" not in c for c in payload["checks"])


@pytest.mark.asyncio
async def test_ready_is_503_when_the_runtime_kernel_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_module, "STATE_BACKEND", "postgres")
    supervisor = _make_supervisor()
    with (
        patch.object(supervisor_mod, "_probe_postgres", AsyncMock(return_value=_check("postgres", True))),
        patch.object(supervisor_mod, "_probe_sidecar", _sidecar(False)),
    ):
        response = await supervisor._ready(SimpleNamespace())  # type: ignore[arg-type]

    assert response.status == 503
    assert json.loads(response.body.decode())["status"] == "not_ready"


@pytest.mark.asyncio
async def test_ready_is_503_when_postgres_is_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real Postgres probe against a closed port: what a stopped Postgres looks like."""
    import koda.knowledge.config as knowledge_config

    monkeypatch.setattr(config_module, "STATE_BACKEND", "postgres")
    monkeypatch.setattr(knowledge_config, "KNOWLEDGE_V2_POSTGRES_DSN", "postgresql://koda:koda@127.0.0.1:1/koda")
    supervisor = _make_supervisor()
    with patch.object(supervisor_mod, "_probe_sidecar", _sidecar(True)):
        response = await supervisor._ready(SimpleNamespace())  # type: ignore[arg-type]

    assert response.status == 503
    checks = {c["name"]: c for c in json.loads(response.body.decode())["checks"]}
    assert checks["postgres"]["ok"] is False
    assert checks["postgres"]["error"]
    assert checks["runtime_kernel"]["ok"] is True


@pytest.mark.asyncio
async def test_health_stays_a_liveness_probe_while_degraded() -> None:
    supervisor = _make_supervisor()
    with patch.object(supervisor_mod, "_probe_sidecar", _sidecar(False)):
        response = await supervisor._health(SimpleNamespace())  # type: ignore[arg-type]

    assert response.status == 200
    assert json.loads(response.body.decode())["status"] == "degraded"


def test_ready_route_is_registered() -> None:
    supervisor = _make_supervisor()
    app = supervisor.build_app()
    paths = {getattr(resource, "canonical", None) for resource in app.router.resources()}
    assert {"/health", "/ready"} <= paths


def test_compose_orders_startup_on_health() -> None:
    services = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))["services"]
    app = services["app"]

    assert app["environment"]["HEALTHCHECK_URL"].endswith("/ready")
    for dependency, rule in app["depends_on"].items():
        expected = "service_completed_successfully" if dependency == "seaweedfs-init" else "service_healthy"
        assert rule["condition"] == expected, dependency
        if expected == "service_healthy":
            assert "healthcheck" in services[dependency], dependency
    # The runtime kernel (the sidecar ADR-001 keeps) is probed over gRPC.
    assert "grpc" in " ".join(services["runtime-kernel"]["healthcheck"]["test"])
    assert services["web"]["depends_on"]["app"]["condition"] == "service_healthy"
