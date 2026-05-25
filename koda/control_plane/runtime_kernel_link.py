"""Supervisor-side gRPC client for the runtime-kernel agent worker RPCs
(``EnsureAgentWorkers`` / ``GetAgentWorker`` / ``TerminateAgentWorker``).

Kept as the single conversion site between supervisor dataclasses and the
generated proto classes so business code never touches protobuf directly.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from koda import config
from koda.internal_rpc.common import (
    create_grpc_channel,
    ensure_generated_proto_path,
    make_internal_breaker,
    resolve_grpc_target,
)
from koda.internal_rpc.metadata import build_rpc_metadata
from koda.logging_config import get_logger

log = get_logger(__name__)


class AgentWorkerState:
    UNSPECIFIED = "STATE_UNSPECIFIED"
    STARTING = "STATE_STARTING"
    RUNNING = "STATE_RUNNING"
    UNHEALTHY = "STATE_UNHEALTHY"
    EXITED = "STATE_EXITED"
    SPAWN_BLOCKED = "STATE_SPAWN_BLOCKED"
    TERMINATED = "STATE_TERMINATED"


@dataclass(frozen=True, slots=True)
class AgentWorkerSpec:
    agent_id: str
    version: int
    command: str
    args: tuple[str, ...]
    working_directory: str = ""
    environment: Mapping[str, str] = field(default_factory=dict)
    health_port: int = 0
    health_path: str = "/health"
    workspace_id: str = "default"


@dataclass(frozen=True, slots=True)
class AgentWorkerStatus:
    """Snapshot of one worker's state in the kernel's registry."""

    agent_id: str
    version: int
    state: str
    pid: int
    pgid: int
    exit_code: int
    started_at_ms: int
    last_health_at_ms: int
    restart_count: int
    spawn_blocked_reason: str

    @property
    def is_running(self) -> bool:
        return self.state == AgentWorkerState.RUNNING

    @property
    def is_starting_or_running(self) -> bool:
        return self.state in (AgentWorkerState.STARTING, AgentWorkerState.RUNNING)

    @property
    def is_terminal(self) -> bool:
        return self.state in (
            AgentWorkerState.EXITED,
            AgentWorkerState.TERMINATED,
            AgentWorkerState.SPAWN_BLOCKED,
        )


@dataclass(frozen=True, slots=True)
class EnsureOutcome:
    current: tuple[AgentWorkerStatus, ...]
    spawned: int
    terminated: int
    restarted: int
    unchanged: int


# Built lazily so importing this module does not force the generated proto
# stubs onto the path (matters for unit tests that don't touch protobuf).
_STATE_INT_TO_NAME: dict[int, str] | None = None


def _state_int_to_name(value: int) -> str:
    global _STATE_INT_TO_NAME
    if _STATE_INT_TO_NAME is None:
        ensure_generated_proto_path()
        from runtime.v1 import runtime_pb2

        descriptor = runtime_pb2.AgentWorkerStatus.State.DESCRIPTOR
        _STATE_INT_TO_NAME = {v.number: v.name for v in descriptor.values}
    return _STATE_INT_TO_NAME.get(value, AgentWorkerState.UNSPECIFIED)


def _status_from_proto(proto: Any) -> AgentWorkerStatus:
    return AgentWorkerStatus(
        agent_id=proto.agent_id,
        version=int(proto.version),
        state=_state_int_to_name(int(proto.state)),
        pid=int(proto.pid),
        pgid=int(proto.pgid),
        exit_code=int(proto.exit_code),
        started_at_ms=int(proto.started_at_ms),
        last_health_at_ms=int(proto.last_health_at_ms),
        restart_count=int(proto.restart_count),
        spawn_blocked_reason=proto.spawn_blocked_reason,
    )


class RuntimeKernelLink:
    """Async gRPC client used by the control-plane supervisor."""

    def __init__(self, *, target: str | None = None) -> None:
        raw_target = target if target is not None else config.RUNTIME_KERNEL_SOCKET
        self._target, self._transport = resolve_grpc_target(raw_target)
        self._channel: Any | None = None
        self._stub: Any | None = None
        self._runtime_pb2: Any | None = None
        self._metadata_pb2: Any | None = None
        self._breaker = make_internal_breaker("runtime_kernel_link")

    @property
    def target(self) -> str:
        return self._target

    @property
    def transport(self) -> str:
        return self._transport

    async def start(self) -> None:
        if self._channel is not None:
            return
        ensure_generated_proto_path()
        from common.v1 import metadata_pb2
        from runtime.v1 import runtime_pb2, runtime_pb2_grpc

        self._channel = create_grpc_channel(self._target, async_channel=True)
        self._metadata_pb2 = metadata_pb2
        self._runtime_pb2 = runtime_pb2
        self._stub = runtime_pb2_grpc.RuntimeKernelServiceStub(self._channel)

    async def stop(self) -> None:
        if self._channel is None:
            return
        channel = self._channel
        self._channel = None
        self._stub = None
        self._runtime_pb2 = None
        self._metadata_pb2 = None
        close_result = channel.close()
        if inspect.isawaitable(close_result):
            await close_result

    def _rpc_metadata(self) -> tuple[tuple[str, str], ...]:
        return build_rpc_metadata(
            agent_id=config.AGENT_ID,
            extra={"x-internal-rpc-mode": "control-plane-link"},
        )

    def _spec_to_proto(self, spec: AgentWorkerSpec) -> Any:
        runtime_pb2 = self._runtime_pb2
        assert runtime_pb2 is not None, "runtime_kernel_link.start() must be called first"
        return runtime_pb2.AgentWorkerSpec(
            agent_id=spec.agent_id,
            version=spec.version,
            command=spec.command,
            args=list(spec.args),
            working_directory=spec.working_directory,
            environment=dict(spec.environment),
            health_port=spec.health_port,
            health_path=spec.health_path,
            workspace_id=spec.workspace_id,
        )

    async def ensure_agent_workers(self, desired: list[AgentWorkerSpec]) -> EnsureOutcome:
        if self._stub is None or self._runtime_pb2 is None:
            raise RuntimeError("RuntimeKernelLink.start() must be called first")
        request = self._runtime_pb2.EnsureAgentWorkersRequest(
            desired=[self._spec_to_proto(spec) for spec in desired],
        )
        try:
            response = await self._stub.EnsureAgentWorkers(
                request,
                metadata=self._rpc_metadata(),
            )
        except Exception:
            log.exception(
                "ensure_agent_workers_rpc_failed",
                target=self._target,
                desired_count=len(desired),
            )
            raise
        return EnsureOutcome(
            current=tuple(_status_from_proto(s) for s in response.current),
            spawned=int(response.spawned),
            terminated=int(response.terminated),
            restarted=int(response.restarted),
            unchanged=int(response.unchanged),
        )

    async def get_agent_worker(self, agent_id: str) -> AgentWorkerStatus | None:
        if self._stub is None or self._runtime_pb2 is None:
            raise RuntimeError("RuntimeKernelLink.start() must be called first")
        if not agent_id:
            raise ValueError("agent_id is required")
        request = self._runtime_pb2.GetAgentWorkerRequest(agent_id=agent_id)
        response = await self._stub.GetAgentWorker(
            request,
            metadata=self._rpc_metadata(),
        )
        if not response.found:
            return None
        return _status_from_proto(response.status)

    async def terminate_agent_worker(self, agent_id: str, *, force: bool = False) -> AgentWorkerStatus | None:
        if self._stub is None or self._runtime_pb2 is None:
            raise RuntimeError("RuntimeKernelLink.start() must be called first")
        if not agent_id:
            raise ValueError("agent_id is required")
        request = self._runtime_pb2.TerminateAgentWorkerRequest(
            agent_id=agent_id,
            force=force,
        )
        response = await self._stub.TerminateAgentWorker(
            request,
            metadata=self._rpc_metadata(),
        )
        if not response.terminated or not response.HasField("status"):
            return None
        return _status_from_proto(response.status)
