"""Reconcile-loop contract for the control-plane supervisor.

The supervisor's only job since the runtime-kernel migration is to:

  1. Read the desired set of active agents from the manager.
  2. Build an ``AgentWorkerSpec`` for each.
  3. Hand the full set to the kernel via ``ensure_agent_workers``.
  4. Cache the resulting status snapshot for ``/health``.

These tests pin that pipeline against a fake manager + fake link, so a
regression that drops env vars, leaks state across reconciles, or stops
flagging SPAWN_BLOCKED to the dashboard is caught without booting any
real subprocess.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from koda.control_plane.manager import RuntimeSnapshot
from koda.control_plane.runtime_kernel_link import (
    AgentWorkerSpec,
    AgentWorkerState,
    AgentWorkerStatus,
    EnsureOutcome,
)
from koda.control_plane.supervisor import ControlPlaneSupervisor


def _runtime_snapshot(agent_id: str, *, port: int, version: int = 1) -> RuntimeSnapshot:
    return RuntimeSnapshot(
        agent_id=agent_id,
        version=version,
        runtime_dir=Path(f"/tmp/koda/{agent_id}"),
        process_env={
            "AGENT_ID": agent_id,
            "AGENT_RUNTIME_DIR": f"/tmp/koda/{agent_id}",
        },
        connection_refs=[],
        health_url=f"http://127.0.0.1:{port}/health",
        runtime_base_url=f"http://127.0.0.1:{port}",
        state_backend="postgres",
        db_file_name=f"{agent_id}.db",
        persisted_to_disk=True,
    )


def _running_status(
    agent_id: str = "AGENT_A",
    *,
    pid: int = 1234,
    version: int = 1,
) -> AgentWorkerStatus:
    return AgentWorkerStatus(
        agent_id=agent_id,
        version=version,
        state=AgentWorkerState.RUNNING,
        pid=pid,
        pgid=pid,
        exit_code=0,
        started_at_ms=1,
        last_health_at_ms=2,
        restart_count=0,
        spawn_blocked_reason="",
    )


def _spawn_blocked_status(agent_id: str, reason: str = "port held") -> AgentWorkerStatus:
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
        spawn_blocked_reason=reason,
    )


class _FakeManager:
    """Minimal stand-in for ControlPlaneManager that supervises agents.

    Only the surface the supervisor uses is implemented. Each call records
    its arguments so tests can assert on the dashboard side-effects."""

    def __init__(self, agents: list[dict[str, Any]]):
        self._agents = agents
        self._snapshots: dict[str, RuntimeSnapshot] = {}
        self.publish_calls: list[str] = []
        self.apply_calls: list[tuple[str, int, bool, dict[str, Any]]] = []
        self.workspace_id = "test-ws"
        self.cluster = SimpleNamespace(config=SimpleNamespace(enabled=False))
        self.provider_connections: dict[str, dict[str, Any]] = {}

    def add_snapshot(self, snapshot: RuntimeSnapshot) -> None:
        self._snapshots[snapshot.agent_id] = snapshot

    # ---- manager API ------------------------------------------------- #
    def list_agents(self) -> list[dict[str, Any]]:
        return list(self._agents)

    def publish_agent(self, agent_id: str) -> dict[str, Any]:
        self.publish_calls.append(agent_id)
        return {"version": 1}

    def build_runtime_snapshot(self, agent_id: str, version: int | None = None) -> RuntimeSnapshot:
        snap = self._snapshots[agent_id]
        return snap

    def mark_apply_finished(
        self,
        agent_id: str,
        version: int,
        *,
        success: bool,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.apply_calls.append((agent_id, version, success, dict(details or {})))

    def ensure_seeded(self) -> None:
        pass

    def get_provider_connection(self, provider_id: str) -> dict[str, Any]:
        return self.provider_connections.get(provider_id, {})

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        for a in self._agents:
            if str(a["id"]) == agent_id:
                return {"workspace_id": self.workspace_id, **a}
        return None


def _make_supervisor(manager: _FakeManager, link: SimpleNamespace) -> ControlPlaneSupervisor:
    with patch(
        "koda.control_plane.supervisor.get_control_plane_manager",
        return_value=manager,
    ):
        return ControlPlaneSupervisor(link=link)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_reconcile_skips_paused_agents() -> None:
    """A paused agent must NOT show up in the desired set sent to the kernel.
    The kernel will then terminate any worker it had for that agent."""
    manager = _FakeManager(
        [
            {"id": "AGENT_ALPHA", "status": "active", "applied_version": 1},
            {"id": "AGENT_BETA", "status": "paused", "applied_version": 1},
        ]
    )
    manager.add_snapshot(_runtime_snapshot("AGENT_ALPHA", port=9001))

    captured: dict[str, Any] = {}

    async def fake_ensure(desired: list[AgentWorkerSpec]) -> EnsureOutcome:
        captured["desired"] = desired
        return EnsureOutcome(
            current=(_running_status("AGENT_ALPHA"),),
            spawned=1,
            terminated=0,
            restarted=0,
            unchanged=0,
        )

    fake_link = SimpleNamespace(
        start=AsyncMock(),
        stop=AsyncMock(),
        ensure_agent_workers=AsyncMock(side_effect=fake_ensure),
        target="unix:///tmp/fake.sock",
    )

    supervisor = _make_supervisor(manager, fake_link)
    await supervisor._reconcile_once()

    desired = captured["desired"]
    assert [s.agent_id for s in desired] == ["AGENT_ALPHA"]
    assert "AGENT_ALPHA" in supervisor._statuses
    assert "AGENT_BETA" not in supervisor._statuses


@pytest.mark.asyncio
async def test_reconcile_caches_health_url_for_dashboard() -> None:
    """After a successful reconcile the supervisor must cache the health URL
    keyed by agent_id so /health can render the legacy payload shape."""
    manager = _FakeManager([{"id": "AGENT_A", "status": "active", "applied_version": 1}])
    manager.add_snapshot(_runtime_snapshot("AGENT_A", port=9100))

    fake_link = SimpleNamespace(
        start=AsyncMock(),
        stop=AsyncMock(),
        ensure_agent_workers=AsyncMock(
            return_value=EnsureOutcome(
                current=(_running_status("AGENT_A"),),
                spawned=1,
                terminated=0,
                restarted=0,
                unchanged=0,
            )
        ),
        target="unix:///tmp/fake.sock",
    )

    supervisor = _make_supervisor(manager, fake_link)
    await supervisor._reconcile_once()

    assert supervisor._health_urls == {"AGENT_A": "http://127.0.0.1:9100/health"}


@pytest.mark.asyncio
async def test_reconcile_skips_agent_when_publish_fails() -> None:
    """A bad draft must not poison the whole reconcile cycle."""
    manager = _FakeManager(
        [
            {"id": "BROKEN", "status": "active", "applied_version": None, "desired_version": None},
            {"id": "HEALTHY", "status": "active", "applied_version": 1},
        ]
    )
    manager.add_snapshot(_runtime_snapshot("HEALTHY", port=9100))

    def publish_agent(agent_id: str) -> dict[str, Any]:
        manager.publish_calls.append(agent_id)
        if agent_id == "BROKEN":
            raise ValueError("invalid draft")
        return {"version": 1}

    manager.publish_agent = publish_agent  # type: ignore[method-assign]

    captured: dict[str, Any] = {}

    async def fake_ensure(desired: list[AgentWorkerSpec]) -> EnsureOutcome:
        captured["desired"] = desired
        return EnsureOutcome(
            current=(_running_status("HEALTHY"),),
            spawned=1,
            terminated=0,
            restarted=0,
            unchanged=0,
        )

    fake_link = SimpleNamespace(
        start=AsyncMock(),
        stop=AsyncMock(),
        ensure_agent_workers=AsyncMock(side_effect=fake_ensure),
        target="unix:///tmp/fake.sock",
    )

    supervisor = _make_supervisor(manager, fake_link)
    await supervisor._reconcile_once()

    assert manager.publish_calls == ["BROKEN"]
    assert [s.agent_id for s in captured["desired"]] == ["HEALTHY"]
    assert "HEALTHY" in supervisor._statuses
    assert "BROKEN" not in supervisor._statuses


@pytest.mark.asyncio
async def test_reconcile_binds_worker_health_api_for_remote_kernel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUNTIME_EPHEMERAL_ROOT", "/var/lib/koda/runtime")
    monkeypatch.setenv("STATE_ROOT_DIR", "/var/lib/koda/state")
    monkeypatch.setenv("ARTIFACT_STORE_DIR", "/var/lib/koda/artifacts")
    manager = _FakeManager([{"id": "AGENT_A", "status": "active", "applied_version": 1}])
    manager.add_snapshot(_runtime_snapshot("AGENT_A", port=9100))
    captured: dict[str, Any] = {}

    async def fake_ensure(desired: list[AgentWorkerSpec]) -> EnsureOutcome:
        captured["desired"] = desired
        return EnsureOutcome(
            current=(_running_status("AGENT_A"),),
            spawned=1,
            terminated=0,
            restarted=0,
            unchanged=0,
        )

    fake_link = SimpleNamespace(
        start=AsyncMock(),
        stop=AsyncMock(),
        ensure_agent_workers=AsyncMock(side_effect=fake_ensure),
        target="runtime-kernel:50061",
    )

    supervisor = _make_supervisor(manager, fake_link)
    await supervisor._reconcile_once()

    desired = captured["desired"]
    assert len(desired) == 1
    assert desired[0].environment["HEALTH_BIND"] == "0.0.0.0"
    assert desired[0].environment["RUNTIME_EPHEMERAL_ROOT"] == "/var/lib/koda/runtime"
    assert desired[0].environment["STATE_ROOT_DIR"] == "/var/lib/koda/state"
    assert desired[0].environment["ARTIFACT_STORE_DIR"] == "/var/lib/koda/artifacts"


@pytest.mark.asyncio
async def test_reconcile_drops_stale_status_when_agent_is_removed() -> None:
    """An agent that disappears from the manager must NOT linger in the
    /health output. Otherwise the dashboard ghosts dead agents forever."""
    manager = _FakeManager([{"id": "AGENT_OLD", "status": "active", "applied_version": 1}])
    manager.add_snapshot(_runtime_snapshot("AGENT_OLD", port=9001))

    ensure_mock = AsyncMock(
        return_value=EnsureOutcome(
            current=(_running_status("AGENT_OLD"),),
            spawned=1,
            terminated=0,
            restarted=0,
            unchanged=0,
        )
    )

    fake_link = SimpleNamespace(
        start=AsyncMock(),
        stop=AsyncMock(),
        ensure_agent_workers=ensure_mock,
        target="unix:///tmp/fake.sock",
    )

    supervisor = _make_supervisor(manager, fake_link)
    await supervisor._reconcile_once()
    assert "AGENT_OLD" in supervisor._statuses

    # Agent is removed from the manager. Kernel response is now empty.
    manager._agents = []
    ensure_mock.return_value = EnsureOutcome(
        current=(),
        spawned=0,
        terminated=1,
        restarted=0,
        unchanged=0,
    )

    await supervisor._reconcile_once()
    assert supervisor._statuses == {}
    assert supervisor._health_urls == {}


@pytest.mark.asyncio
async def test_reconcile_marks_apply_finished_on_running_transition() -> None:
    """A worker entering RUNNING is the trigger for marking the apply
    successful in the dashboard. Operators read this to know whether their
    last edit took effect."""
    manager = _FakeManager([{"id": "AGENT_OK", "status": "active", "applied_version": 5}])
    manager.add_snapshot(_runtime_snapshot("AGENT_OK", port=9001, version=5))

    fake_link = SimpleNamespace(
        start=AsyncMock(),
        stop=AsyncMock(),
        ensure_agent_workers=AsyncMock(
            return_value=EnsureOutcome(
                current=(_running_status("AGENT_OK", version=5),),
                spawned=1,
                terminated=0,
                restarted=0,
                unchanged=0,
            )
        ),
        target="unix:///tmp/fake.sock",
    )

    supervisor = _make_supervisor(manager, fake_link)
    await supervisor._reconcile_once()

    assert any(
        agent_id == "AGENT_OK" and version == 5 and success is True
        for agent_id, version, success, _ in manager.apply_calls
    )


@pytest.mark.asyncio
async def test_reconcile_marks_apply_failed_on_spawn_blocked() -> None:
    """SPAWN_BLOCKED is the kernel's pre-flight signal that the worker
    cannot start (port held, executable missing, etc). The dashboard must
    surface that as a failed apply, not as a silent stall."""
    manager = _FakeManager([{"id": "AGENT_X", "status": "active", "applied_version": 1}])
    manager.add_snapshot(_runtime_snapshot("AGENT_X", port=9001))

    fake_link = SimpleNamespace(
        start=AsyncMock(),
        stop=AsyncMock(),
        ensure_agent_workers=AsyncMock(
            return_value=EnsureOutcome(
                current=(_spawn_blocked_status("AGENT_X", reason="port held"),),
                spawned=0,
                terminated=0,
                restarted=0,
                unchanged=0,
            )
        ),
        target="unix:///tmp/fake.sock",
    )

    supervisor = _make_supervisor(manager, fake_link)
    await supervisor._reconcile_once()

    failures = [call for call in manager.apply_calls if call[0] == "AGENT_X" and call[2] is False]
    assert failures, "spawn-blocked must mark apply as failed"
    _agent_id, _version, _success, details = failures[0]
    assert details.get("reason") == "port held"


@pytest.mark.asyncio
async def test_reconcile_does_not_remark_apply_for_unchanged_state() -> None:
    """Once a worker is RUNNING, subsequent reconciles must NOT spam
    mark_apply_finished. That would flood the dashboard's audit log."""
    manager = _FakeManager([{"id": "AGENT_OK", "status": "active", "applied_version": 1}])
    manager.add_snapshot(_runtime_snapshot("AGENT_OK", port=9001))

    fake_link = SimpleNamespace(
        start=AsyncMock(),
        stop=AsyncMock(),
        ensure_agent_workers=AsyncMock(
            return_value=EnsureOutcome(
                current=(_running_status("AGENT_OK"),),
                spawned=1,
                terminated=0,
                restarted=0,
                unchanged=0,
            )
        ),
        target="unix:///tmp/fake.sock",
    )

    supervisor = _make_supervisor(manager, fake_link)
    await supervisor._reconcile_once()
    first_count = len(manager.apply_calls)
    await supervisor._reconcile_once()
    await supervisor._reconcile_once()
    assert len(manager.apply_calls) == first_count, "mark_apply_finished must only fire on state transitions"


@pytest.mark.asyncio
async def test_build_spec_forwards_safe_parent_env_and_overrides_runtime_env() -> None:
    """The spec built for the kernel must:
    * Forward whitelisted parent env (PATH, HOME, …).
    * Apply the manager's runtime env on top.
    * Re-apply system-critical infra env from the parent so a stale
      snapshot can never override the host."""
    manager = _FakeManager([{"id": "AGENT_E", "status": "active", "applied_version": 1}])
    manager.add_snapshot(_runtime_snapshot("AGENT_E", port=9001))

    fake_link = SimpleNamespace(
        start=AsyncMock(),
        stop=AsyncMock(),
        ensure_agent_workers=AsyncMock(),
        target="unix:///tmp/fake.sock",
    )

    supervisor = _make_supervisor(manager, fake_link)

    snapshot = manager._snapshots["AGENT_E"]
    snapshot.process_env["PATH"] = "/snapshot/bin"  # snapshot tries to override
    snapshot.process_env["AGENT_ID"] = "AGENT_E"
    snapshot.process_env["POSTGRES_URL"] = "postgres://stale"
    snapshot.process_env["INTER_AGENT_BUS_BACKEND"] = "memory"

    parent_env = {
        "PATH": "/usr/bin:/usr/local/bin",
        "HOME": "/workspace/koda",
        "POSTGRES_URL": "postgres://live",
        "INTER_AGENT_BUS_BACKEND": "postgres",
        "SQUAD_BUS_LISTEN_ENABLED": "false",
        "DANGEROUS_LEAK": "should-not-forward",
    }
    with patch.dict(os.environ, parent_env, clear=False):
        spec = supervisor._build_spec("AGENT_E", version=1, runtime=snapshot)

    env = dict(spec.environment)
    # Whitelisted parent env reaches the worker.
    assert env["HOME"] == "/workspace/koda"
    # Snapshot env still wins for non-system keys (only SYSTEM_ENV_KEYS get
    # forced from parent).
    assert env["AGENT_ID"] == "AGENT_E"
    # System-critical infra env is forced from parent regardless of snapshot.
    assert env["POSTGRES_URL"] == "postgres://live"
    assert env["INTER_AGENT_BUS_BACKEND"] == "postgres"
    assert env["SQUAD_BUS_LISTEN_ENABLED"] == "false"
    # Non-whitelisted host env never leaks.
    assert "DANGEROUS_LEAK" not in env
    # Boot guard so the worker boots in agent mode.
    assert env["_KODA_RUNTIME_BOOTSTRAPPED"] == "1"
    # Health port + path roundtrip from the snapshot URL.
    assert spec.health_port == 9001
    assert spec.health_path == "/health"
    assert spec.workspace_id == manager.workspace_id


@pytest.mark.asyncio
async def test_reconcile_logs_manager_failures_without_aborting() -> None:
    """A single agent's snapshot build failure must NOT take down the
    whole reconcile cycle. Other agents in the desired set still proceed."""
    manager = _FakeManager(
        [
            {"id": "AGENT_BAD", "status": "active", "applied_version": 1},
            {"id": "AGENT_GOOD", "status": "active", "applied_version": 1},
        ]
    )
    manager.add_snapshot(_runtime_snapshot("AGENT_GOOD", port=9001))

    def boom_or_real(agent_id: str, version: int | None = None) -> RuntimeSnapshot:
        if agent_id == "AGENT_BAD":
            raise RuntimeError("snapshot build failed for AGENT_BAD")
        return manager._snapshots[agent_id]

    manager.build_runtime_snapshot = boom_or_real  # type: ignore[method-assign]

    captured: dict[str, Any] = {}

    async def fake_ensure(desired: list[AgentWorkerSpec]) -> EnsureOutcome:
        captured["desired"] = desired
        return EnsureOutcome(
            current=(_running_status("AGENT_GOOD"),),
            spawned=1,
            terminated=0,
            restarted=0,
            unchanged=0,
        )

    fake_link = SimpleNamespace(
        start=AsyncMock(),
        stop=AsyncMock(),
        ensure_agent_workers=AsyncMock(side_effect=fake_ensure),
        target="unix:///tmp/fake.sock",
    )

    supervisor = _make_supervisor(manager, fake_link)
    await supervisor._reconcile_once()

    desired = captured["desired"]
    assert [s.agent_id for s in desired] == ["AGENT_GOOD"]
    assert "AGENT_GOOD" in supervisor._statuses
