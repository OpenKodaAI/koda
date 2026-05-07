"""Contract for the supervisor → runtime-kernel gRPC link.

The link is the single boundary where the supervisor turns its declarative
``AgentWorkerSpec`` dataclass into the proto wire format and back. Bugs in
this conversion would silently drop env vars, swap agent_ids, or render
the kernel unable to identify a worker. These tests pin:

  * Spec → proto: every dataclass field reaches the proto request, env
    map preserved verbatim, args turned into a list, defaults respected.
  * Proto status → dataclass: enum int round-trips to the canonical
    string constant, every numeric field is coerced from int.
  * Lifecycle: ``start()`` is idempotent, ``stop()`` releases the channel,
    methods called before ``start()`` raise a clear RuntimeError.

The tests use a hand-rolled fake stub so they run with no kernel and no
running gRPC server — pure dataclass / proto conversion checks.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from koda.control_plane.runtime_kernel_link import (
    AgentWorkerSpec,
    AgentWorkerState,
    AgentWorkerStatus,
    EnsureOutcome,
    RuntimeKernelLink,
    _state_int_to_name,
    _status_from_proto,
)


def test_state_int_to_name_round_trips_known_values() -> None:
    """Each proto enum int must map to the matching string constant.

    A drift here (e.g. an enum reordering) would cause the dashboard to
    render every worker as STATE_UNSPECIFIED."""
    from koda.internal_rpc.common import ensure_generated_proto_path

    ensure_generated_proto_path()
    from runtime.v1 import runtime_pb2

    descriptor = runtime_pb2.AgentWorkerStatus.State.DESCRIPTOR
    for value in descriptor.values:
        assert _state_int_to_name(value.number) == value.name


def test_state_int_to_name_returns_unspecified_for_unknown() -> None:
    """Out-of-range enum int collapses to UNSPECIFIED instead of raising
    so a future kernel adding a state cannot crash a current supervisor."""
    assert _state_int_to_name(99_999) == AgentWorkerState.UNSPECIFIED


def test_status_from_proto_extracts_every_field() -> None:
    from koda.internal_rpc.common import ensure_generated_proto_path

    ensure_generated_proto_path()
    from runtime.v1 import runtime_pb2

    proto = runtime_pb2.AgentWorkerStatus(
        agent_id="AGENT_ALPHA",
        version=42,
        state=runtime_pb2.AgentWorkerStatus.State.STATE_RUNNING,
        pid=12345,
        pgid=12340,
        exit_code=0,
        started_at_ms=1_700_000_000_000,
        last_health_at_ms=1_700_000_000_500,
        restart_count=3,
        spawn_blocked_reason="",
    )

    status = _status_from_proto(proto)
    assert status == AgentWorkerStatus(
        agent_id="AGENT_ALPHA",
        version=42,
        state=AgentWorkerState.RUNNING,
        pid=12345,
        pgid=12340,
        exit_code=0,
        started_at_ms=1_700_000_000_000,
        last_health_at_ms=1_700_000_000_500,
        restart_count=3,
        spawn_blocked_reason="",
    )
    assert status.is_running is True
    assert status.is_starting_or_running is True
    assert status.is_terminal is False


def test_status_predicates_for_each_state() -> None:
    def make(state: str) -> AgentWorkerStatus:
        return AgentWorkerStatus(
            agent_id="A",
            version=1,
            state=state,
            pid=0,
            pgid=0,
            exit_code=0,
            started_at_ms=0,
            last_health_at_ms=0,
            restart_count=0,
            spawn_blocked_reason="",
        )

    starting = make(AgentWorkerState.STARTING)
    running = make(AgentWorkerState.RUNNING)
    unhealthy = make(AgentWorkerState.UNHEALTHY)
    exited = make(AgentWorkerState.EXITED)
    terminated = make(AgentWorkerState.TERMINATED)
    blocked = make(AgentWorkerState.SPAWN_BLOCKED)

    assert running.is_running and running.is_starting_or_running
    assert not running.is_terminal
    assert starting.is_starting_or_running and not starting.is_running
    assert unhealthy.is_starting_or_running is False
    for terminal in (exited, terminated, blocked):
        assert terminal.is_terminal is True
        assert terminal.is_running is False


@pytest.mark.asyncio
async def test_ensure_agent_workers_before_start_raises() -> None:
    link = RuntimeKernelLink(target="unix:///tmp/fake.sock")
    with pytest.raises(RuntimeError, match="start"):
        await link.ensure_agent_workers([])


@pytest.mark.asyncio
async def test_get_agent_worker_before_start_raises() -> None:
    link = RuntimeKernelLink(target="unix:///tmp/fake.sock")
    with pytest.raises(RuntimeError, match="start"):
        await link.get_agent_worker("AGENT_X")


@pytest.mark.asyncio
async def test_get_agent_worker_rejects_empty_id_after_start() -> None:
    link = RuntimeKernelLink(target="unix:///tmp/fake.sock")
    # Forge minimal "started" state without opening a real channel.
    link._stub = MagicMock()
    link._runtime_pb2 = SimpleNamespace(
        GetAgentWorkerRequest=lambda **kwargs: kwargs,
    )
    with pytest.raises(ValueError):
        await link.get_agent_worker("")


@pytest.mark.asyncio
async def test_terminate_agent_worker_rejects_empty_id_after_start() -> None:
    link = RuntimeKernelLink(target="unix:///tmp/fake.sock")
    link._stub = MagicMock()
    link._runtime_pb2 = SimpleNamespace(
        TerminateAgentWorkerRequest=lambda **kwargs: kwargs,
    )
    with pytest.raises(ValueError):
        await link.terminate_agent_worker("")


@pytest.mark.asyncio
async def test_ensure_agent_workers_serializes_full_spec_into_request() -> None:
    """The link is the only place where the dataclass spec is converted to
    proto. A bug here drops env vars or args silently."""
    from koda.internal_rpc.common import ensure_generated_proto_path

    ensure_generated_proto_path()
    from runtime.v1 import runtime_pb2

    link = RuntimeKernelLink(target="unix:///tmp/fake.sock")
    link._runtime_pb2 = runtime_pb2

    captured: dict[str, object] = {}

    async def fake_ensure(request, metadata):
        captured["request"] = request
        captured["metadata"] = metadata
        # Build a real response so _status_from_proto works against it.
        return runtime_pb2.EnsureAgentWorkersResponse(
            current=[
                runtime_pb2.AgentWorkerStatus(
                    agent_id="AGENT_ALPHA",
                    version=7,
                    state=runtime_pb2.AgentWorkerStatus.State.STATE_RUNNING,
                    pid=4242,
                    pgid=4242,
                    exit_code=0,
                    started_at_ms=1,
                    last_health_at_ms=2,
                    restart_count=0,
                    spawn_blocked_reason="",
                )
            ],
            spawned=1,
            terminated=0,
            restarted=0,
            unchanged=0,
        )

    link._stub = SimpleNamespace(EnsureAgentWorkers=fake_ensure)

    spec = AgentWorkerSpec(
        agent_id="AGENT_ALPHA",
        version=7,
        command="/usr/bin/python3",
        args=("-m", "koda", "--agent-id", "AGENT_ALPHA"),
        working_directory="/srv/koda",
        environment={"AGENT_ID": "AGENT_ALPHA", "PATH": "/usr/bin"},
        health_port=9001,
        health_path="/health",
        workspace_id="alpha-ws",
    )

    outcome = await link.ensure_agent_workers([spec])

    request = captured["request"]
    assert isinstance(request, runtime_pb2.EnsureAgentWorkersRequest)
    assert len(request.desired) == 1
    proto_spec = request.desired[0]
    assert proto_spec.agent_id == "AGENT_ALPHA"
    assert proto_spec.version == 7
    assert proto_spec.command == "/usr/bin/python3"
    assert list(proto_spec.args) == [
        "-m",
        "koda",
        "--agent-id",
        "AGENT_ALPHA",
    ]
    assert proto_spec.working_directory == "/srv/koda"
    assert dict(proto_spec.environment) == {
        "AGENT_ID": "AGENT_ALPHA",
        "PATH": "/usr/bin",
    }
    assert proto_spec.health_port == 9001
    assert proto_spec.health_path == "/health"
    assert proto_spec.workspace_id == "alpha-ws"

    assert isinstance(outcome, EnsureOutcome)
    assert outcome.spawned == 1
    assert outcome.terminated == 0
    assert outcome.restarted == 0
    assert outcome.unchanged == 0
    assert len(outcome.current) == 1
    assert outcome.current[0].agent_id == "AGENT_ALPHA"
    assert outcome.current[0].is_running is True


@pytest.mark.asyncio
async def test_ensure_agent_workers_propagates_rpc_failure() -> None:
    """A gRPC failure must propagate so the supervisor can log it and the
    next reconcile cycle retries — never silently swallowed."""
    from koda.internal_rpc.common import ensure_generated_proto_path

    ensure_generated_proto_path()
    from runtime.v1 import runtime_pb2

    link = RuntimeKernelLink(target="unix:///tmp/fake.sock")
    link._runtime_pb2 = runtime_pb2

    boom = RuntimeError("kernel unreachable")

    async def fake_ensure(request, metadata):
        raise boom

    link._stub = SimpleNamespace(EnsureAgentWorkers=fake_ensure)

    with pytest.raises(RuntimeError, match="kernel unreachable"):
        await link.ensure_agent_workers([])


@pytest.mark.asyncio
async def test_get_agent_worker_returns_none_when_not_found() -> None:
    from koda.internal_rpc.common import ensure_generated_proto_path

    ensure_generated_proto_path()
    from runtime.v1 import runtime_pb2

    link = RuntimeKernelLink(target="unix:///tmp/fake.sock")
    link._runtime_pb2 = runtime_pb2

    async def fake_get(request, metadata):
        return runtime_pb2.GetAgentWorkerResponse(found=False)

    link._stub = SimpleNamespace(GetAgentWorker=fake_get)
    assert await link.get_agent_worker("AGENT_GHOST") is None


@pytest.mark.asyncio
async def test_terminate_agent_worker_returns_none_when_not_terminated() -> None:
    from koda.internal_rpc.common import ensure_generated_proto_path

    ensure_generated_proto_path()
    from runtime.v1 import runtime_pb2

    link = RuntimeKernelLink(target="unix:///tmp/fake.sock")
    link._runtime_pb2 = runtime_pb2

    async def fake_terminate(request, metadata):
        return runtime_pb2.TerminateAgentWorkerResponse(terminated=False)

    link._stub = SimpleNamespace(TerminateAgentWorker=fake_terminate)
    assert await link.terminate_agent_worker("AGENT_GHOST") is None


@pytest.mark.asyncio
async def test_lifecycle_start_is_idempotent_and_stop_releases_channel() -> None:
    link = RuntimeKernelLink(target="unix:///tmp/fake.sock")

    fake_channel = MagicMock(name="channel")
    fake_channel.close = MagicMock(return_value=None)
    fake_metadata_pb2 = SimpleNamespace()
    fake_runtime_pb2 = SimpleNamespace()

    class _StubFactory:
        def __init__(self, channel):
            self._channel = channel

    fake_runtime_pb2_grpc = SimpleNamespace(
        RuntimeKernelServiceStub=lambda channel: _StubFactory(channel),
    )

    with (
        patch(
            "koda.control_plane.runtime_kernel_link.create_grpc_channel",
            return_value=fake_channel,
        ),
        patch.dict(
            "sys.modules",
            {
                "common.v1.metadata_pb2": fake_metadata_pb2,
                "runtime.v1.runtime_pb2": fake_runtime_pb2,
                "runtime.v1.runtime_pb2_grpc": fake_runtime_pb2_grpc,
            },
        ),
    ):
        await link.start()
        # Idempotent — second call must not re-open the channel.
        await link.start()
        assert link._channel is fake_channel
        await link.stop()
        assert link._channel is None
        assert link._stub is None
        # close() called exactly once across the lifecycle.
        fake_channel.close.assert_called_once()
