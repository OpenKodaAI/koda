"""Runtime-kernel client selection for the Rust migration seam."""

from __future__ import annotations

import inspect
import json
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from koda import config
from koda.internal_rpc.common import (
    create_grpc_channel,
    ensure_generated_proto_path,
    normalize_internal_service_probe,
    parse_boolish,
    resolve_grpc_target,
    select_engine_backend,
)
from koda.internal_rpc.metadata import build_rpc_metadata

if TYPE_CHECKING:
    from koda.services.runtime.store import RuntimeStore


def _stringify_metadata(metadata: Mapping[str, object] | None) -> dict[str, str]:
    return {str(key): str(value) for key, value in dict(metadata or {}).items()}


_RUNTIME_KERNEL_CAPABILITY_DEFAULTS: tuple[str, ...] = (
    "workspace-provisioning",
    "workspace-cleanup",
    "environment-tracking",
    "process-spawn",
    "command-execution",
    "terminal-streaming",
    "interactive-terminal-sessions",
    "terminal-input-write",
    "terminal-resize",
    "terminal-close",
    "signal-termination",
    "browser-session-registry",
    "checkpoint-persistence",
    "checkpoint-retrieval",
    "checkpoint-restore",
    "snapshot-collection",
    "reconcile",
)
_RUNTIME_KERNEL_AUTHORITATIVE_OPERATION_DEFAULTS: tuple[str, ...] = (
    "create_environment",
    "start_task",
    "execute_command",
    "stream_terminal",
    "open_terminal",
    "write_terminal",
    "resize_terminal",
    "close_terminal",
    "stream_terminal_session",
    "terminate_task",
    "cleanup_environment",
    "start_browser_session",
    "stop_browser_session",
    "get_browser_session",
    "save_checkpoint",
    "get_checkpoint",
    "restore_checkpoint",
)


class RuntimeKernelClient(Protocol):
    """Behavior expected from the runtime-kernel adapter."""

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def create_environment(
        self,
        *,
        task_id: int,
        agent_id: str | None,
        workspace_path: str,
        worktree_ref: str | None = None,
        base_work_dir: str = "",
        slug: str = "",
        create_worktree: bool | None = None,
    ) -> dict[str, object]: ...

    async def start_task(
        self,
        *,
        task_id: int,
        command: str,
        args: list[str] | None = None,
        working_directory: str = "",
        environment_overrides: Mapping[str, str] | None = None,
        stdin_payload: bytes | None = None,
        start_new_session: bool = True,
    ) -> dict[str, object]: ...

    async def execute_command(
        self,
        *,
        agent_id: str | None,
        command: str,
        working_directory: str = "",
        environment_overrides: Mapping[str, str] | None = None,
        stdin_payload: bytes | None = None,
        timeout_seconds: int = 0,
        allow_network: bool = False,
        purpose: str = "",
        env_labels: Mapping[str, str] | None = None,
        argv: list[str] | None = None,
        runtime_env_id: str = "",
        start_new_session: bool = True,
    ) -> dict[str, object]: ...

    async def terminate_task(self, *, task_id: int, force: bool = False) -> dict[str, object]: ...

    async def attach_terminal(self, *, task_id: int, session_id: str) -> dict[str, object]: ...

    def stream_terminal(self, *, task_id: int, stream: str) -> AsyncIterator[bytes]: ...

    async def open_terminal(
        self,
        *,
        task_id: int,
        session_id: str,
        command: str,
        args: list[str] | None = None,
        working_directory: str = "",
        environment_overrides: Mapping[str, str] | None = None,
        cols: int = 120,
        rows: int = 40,
        stdin_payload: bytes | None = None,
    ) -> dict[str, object]: ...

    async def write_terminal(
        self,
        *,
        task_id: int,
        session_id: str,
        data: bytes,
        eof: bool = False,
    ) -> dict[str, object]: ...

    async def resize_terminal(
        self,
        *,
        task_id: int,
        session_id: str,
        cols: int,
        rows: int,
    ) -> dict[str, object]: ...

    async def close_terminal(
        self,
        *,
        task_id: int,
        session_id: str,
        force: bool = False,
    ) -> dict[str, object]: ...

    def stream_terminal_session(self, *, task_id: int, session_id: str) -> AsyncIterator[bytes]: ...

    async def pause_task(self, *, task_id: int, reason: str, actor: str) -> dict[str, object]: ...

    async def resume_task(self, *, task_id: int, actor: str) -> dict[str, object]: ...

    async def finalize_task(
        self,
        *,
        task_id: int,
        success: bool,
        final_phase: str,
        error_message: str | None,
    ) -> dict[str, object]: ...

    async def reconcile(self) -> dict[str, object]: ...

    async def collect_snapshot(self, *, task_id: int) -> dict[str, object] | None: ...

    async def cleanup_environment(self, *, task_id: int, force: bool = False) -> dict[str, object]: ...

    async def start_browser_session(
        self,
        *,
        task_id: int,
        scope_id: int,
        runtime_dir: str,
        transport: str,
        display_id: int | None = None,
        vnc_port: int | None = None,
        novnc_port: int | None = None,
        missing_binaries: list[str] | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> dict[str, object]: ...

    async def stop_browser_session(
        self,
        *,
        task_id: int,
        scope_id: int,
        force: bool = False,
    ) -> dict[str, object]: ...

    async def get_browser_session(
        self,
        *,
        task_id: int,
        scope_id: int,
    ) -> dict[str, object] | None: ...

    async def save_checkpoint(
        self,
        *,
        task_id: int,
        environment_id: str,
        success: bool,
        final_phase: str,
        retention_hours: int = 0,
    ) -> dict[str, object]: ...

    async def get_checkpoint(
        self,
        *,
        task_id: int,
        checkpoint_id: str = "",
    ) -> dict[str, object] | None: ...

    async def restore_checkpoint(
        self,
        *,
        task_id: int,
        checkpoint_id: str = "",
        workspace_path: str = "",
    ) -> dict[str, object]: ...

    def health(self) -> dict[str, object]: ...


class GrpcRuntimeKernelClient:
    """Rust runtime-kernel client over internal gRPC."""

    def __init__(
        self,
        *,
        runtime_root: Path,
        store: RuntimeStore,
        mode: str,
        selection_reason: str | None = None,
        agent_id: str | None = None,
    ) -> None:
        self.runtime_root = runtime_root
        self.store = store
        self.mode = mode
        self.selection_reason = selection_reason or "rust-default"
        self.agent_id = (agent_id or config.AGENT_ID or "").strip().lower() or None
        self._target, self._transport = resolve_grpc_target(config.RUNTIME_KERNEL_SOCKET)
        self._channel: Any | None = None
        self._stub: Any | None = None
        self._metadata_pb2: Any | None = None
        self._runtime_pb2: Any | None = None
        self._startup_error: str | None = None
        self._started = False
        self._last_health: dict[str, object] = {
            "service": "runtime-kernel",
            "mode": self.mode,
            "implementation": "grpc-runtime-kernel-client",
            "transport": self._transport,
            "configured_target": self._target,
            "deadline_ms": config.INTERNAL_RPC_DEADLINE_MS,
            "connected": False,
            "verified": False,
            "ready": False,
            "startup_error": None,
            "selection_reason": self.selection_reason,
            "agent_id": self.agent_id,
        }

    async def start(self) -> None:
        if self._started and self._stub is not None and self._channel is not None:
            return
        try:
            ensure_generated_proto_path()
            from common.v1 import metadata_pb2
            from runtime.v1 import runtime_pb2, runtime_pb2_grpc
        except Exception as exc:  # pragma: no cover - import failure depends on environment
            self._startup_error = f"{type(exc).__name__}: {exc}"
            self._last_health = {
                **self._last_health,
                "startup_error": self._startup_error,
                "ready": False,
            }
            raise RuntimeError("grpc_runtime_kernel_client_requires_runtime_stubs") from exc

        self._channel = create_grpc_channel(self._target, async_channel=True)
        self._metadata_pb2 = metadata_pb2
        self._runtime_pb2 = runtime_pb2
        self._stub = runtime_pb2_grpc.RuntimeKernelServiceStub(self._channel)
        try:
            await self._probe_health()
        except Exception:
            channel = self._channel
            self._channel = None
            self._stub = None
            self._metadata_pb2 = None
            self._runtime_pb2 = None
            self._started = False
            if channel is not None:
                close_result = channel.close()
                if inspect.isawaitable(close_result):
                    await close_result
            raise
        self._started = True

    async def stop(self) -> None:
        if self._channel is None:
            return
        channel = self._channel
        self._channel = None
        self._stub = None
        self._started = False
        close_result = channel.close()
        if inspect.isawaitable(close_result):
            await close_result

    def _rpc_metadata(self, *, task_id: int | None = None) -> tuple[tuple[str, str], ...]:
        return build_rpc_metadata(
            agent_id=config.AGENT_ID,
            task_id=task_id,
            extra={"x-internal-rpc-mode": self.mode},
        )

    def _request_metadata(self, *, task_id: int | None = None, agent_id: str | None = None) -> Any | None:
        if self._metadata_pb2 is None:
            return None
        request_metadata_type = getattr(self._metadata_pb2, "RequestMetadata", None)
        if request_metadata_type is None:
            return None
        return request_metadata_type(
            agent_id=(agent_id or config.AGENT_ID or "").strip(),
            task_id=str(task_id) if task_id is not None else "",
            labels={"internal_rpc_mode": self.mode},
        )

    def _build_request(
        self,
        factory: Any,
        /,
        *,
        _rpc_task_id: int | None = None,
        _rpc_agent_id: str | None = None,
        **kwargs: object,
    ) -> Any:
        request_metadata = self._request_metadata(task_id=_rpc_task_id, agent_id=_rpc_agent_id)
        if request_metadata is not None:
            try:
                return factory(metadata=request_metadata, **kwargs)
            except TypeError:
                kwargs = self._filter_request_kwargs(factory, metadata=request_metadata, **kwargs)
                if "metadata" in kwargs:
                    return factory(**kwargs)
        try:
            return factory(**kwargs)
        except TypeError:
            filtered_kwargs = self._filter_request_kwargs(factory, **kwargs)
            if filtered_kwargs != kwargs:
                return factory(**filtered_kwargs)
            raise

    def _filter_request_kwargs(self, factory: Any, /, **kwargs: object) -> dict[str, object]:
        try:
            parameters = inspect.signature(factory).parameters
        except (TypeError, ValueError):
            return dict(kwargs)
        accepted_names = {
            name
            for name, parameter in parameters.items()
            if parameter.kind
            in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            )
        }
        if not accepted_names:
            return {}
        return {key: value for key, value in kwargs.items() if key in accepted_names}

    async def _probe_health(self) -> None:
        if self._stub is None or self._metadata_pb2 is None:
            return
        response = await self._stub.Health(
            self._metadata_pb2.HealthRequest(),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(),
        )
        self._last_health = normalize_internal_service_probe(
            base_health=self._last_health,
            service=response.service,
            ready=bool(response.ready),
            status=response.status,
            details=dict(response.details),
        )

    async def create_environment(
        self,
        *,
        task_id: int,
        agent_id: str | None,
        workspace_path: str,
        worktree_ref: str | None = None,
        base_work_dir: str = "",
        slug: str = "",
        create_worktree: bool | None = None,
    ) -> dict[str, object]:
        if self._stub is None or self._runtime_pb2 is None:
            return {"forwarded": False, "task_id": task_id, "reason": "runtime-kernel unavailable"}
        response = await self._stub.CreateEnvironment(
            self._build_request(
                self._runtime_pb2.CreateEnvironmentRequest,
                _rpc_task_id=task_id,
                _rpc_agent_id=agent_id,
                agent_id=(agent_id or config.AGENT_ID or "").strip(),
                task_id=str(task_id),
                workspace_path=workspace_path,
                worktree_ref=worktree_ref or "",
                base_work_dir=base_work_dir,
                slug=slug,
                create_worktree=bool(create_worktree),
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(task_id=task_id),
        )
        environment = response.environment
        return {
            "forwarded": True,
            "task_id": task_id,
            "environment_id": getattr(environment, "environment_id", ""),
            "agent_id": getattr(environment, "agent_id", agent_id or config.AGENT_ID or ""),
            "runtime_root": getattr(response, "runtime_root", ""),
            "workspace_path": getattr(response, "workspace_path", workspace_path),
            "branch_name": getattr(response, "branch_name", ""),
            "created_worktree": bool(getattr(response, "created_worktree", False)),
            "worktree_mode": getattr(response, "worktree_mode", ""),
            "metadata_path": getattr(response, "metadata_path", ""),
        }

    async def start_task(
        self,
        *,
        task_id: int,
        command: str,
        args: list[str] | None = None,
        working_directory: str = "",
        environment_overrides: Mapping[str, str] | None = None,
        stdin_payload: bytes | None = None,
        start_new_session: bool = True,
    ) -> dict[str, object]:
        if self._stub is None or self._runtime_pb2 is None:
            return {"forwarded": False, "task_id": task_id, "reason": "runtime-kernel unavailable"}
        response = await self._stub.StartTask(
            self._build_request(
                self._runtime_pb2.StartTaskRequest,
                _rpc_task_id=task_id,
                task_id=str(task_id),
                command=command,
                args=list(args or []),
                working_directory=working_directory,
                environment_overrides=dict(environment_overrides or {}),
                stdin_payload=bytes(stdin_payload or b""),
                start_new_session=start_new_session,
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(task_id=task_id),
        )
        environment = getattr(response, "environment", None)
        process = getattr(response, "process", None)
        stdout_terminal = getattr(response, "stdout_terminal", None)
        stderr_terminal = getattr(response, "stderr_terminal", None)
        return {
            "forwarded": True,
            "task_id": task_id,
            "phase": getattr(response, "phase", ""),
            "process_id": getattr(response, "process_id", ""),
            "environment_id": getattr(environment, "environment_id", ""),
            "pid": int(getattr(process, "pid", 0) or 0),
            "pgid": int(getattr(process, "pgid", 0) or 0),
            "status": getattr(process, "status", ""),
            "stdout_terminal_id": getattr(stdout_terminal, "session_id", ""),
            "stderr_terminal_id": getattr(stderr_terminal, "session_id", ""),
            "running": getattr(process, "status", "") == "running",
        }

    async def execute_command(
        self,
        *,
        agent_id: str | None,
        command: str,
        working_directory: str = "",
        environment_overrides: Mapping[str, str] | None = None,
        stdin_payload: bytes | None = None,
        timeout_seconds: int = 0,
        allow_network: bool = False,
        purpose: str = "",
        env_labels: Mapping[str, str] | None = None,
        argv: list[str] | None = None,
        runtime_env_id: str = "",
        start_new_session: bool = True,
    ) -> dict[str, object]:
        if self._stub is None or self._runtime_pb2 is None or self._metadata_pb2 is None:
            await self.start()
        if self._stub is None or self._runtime_pb2 is None:
            return {"forwarded": False, "reason": "runtime-kernel unavailable"}
        health = self.health()
        if not bool(health.get("cutover_allowed", False)):
            return {
                "forwarded": False,
                "reason": "runtime-kernel not cutover-ready",
                "cutover_allowed": bool(health.get("cutover_allowed", False)),
                "ready": bool(health.get("ready", False)),
                "authoritative": bool(health.get("authoritative", False)),
            }
        response = await self._stub.ExecuteCommand(
            self._build_request(
                self._runtime_pb2.ExecuteCommandRequest,
                _rpc_task_id=None,
                _rpc_agent_id=agent_id,
                agent_id=(agent_id or config.AGENT_ID or "").strip(),
                runtime_env_id=runtime_env_id,
                command=command,
                argv=list(argv or []),
                working_directory=working_directory,
                environment_overrides=dict(environment_overrides or {}),
                stdin_payload=bytes(stdin_payload or b""),
                timeout_seconds=max(0, int(timeout_seconds)),
                allow_network=allow_network,
                purpose=purpose,
                env_labels=_stringify_metadata(env_labels),
                start_new_session=start_new_session,
            ),
            timeout=max(1, int(timeout_seconds or config.INTERNAL_RPC_DEADLINE_MS / 1000)),
            metadata=self._rpc_metadata(),
        )
        return {
            "forwarded": True,
            "command": getattr(response, "command", command),
            "argv": list(getattr(response, "argv", argv or []) or []),
            "working_directory": getattr(response, "working_directory", working_directory),
            "stdout": getattr(response, "stdout", ""),
            "stderr": getattr(response, "stderr", ""),
            "exit_code": int(getattr(response, "exit_code", 0) or 0),
            "timed_out": bool(getattr(response, "timed_out", False)),
            "killed": bool(getattr(response, "killed", False)),
            "started_at_ms": int(getattr(response, "started_at_ms", 0) or 0),
            "finished_at_ms": int(getattr(response, "finished_at_ms", 0) or 0),
            "allow_network": allow_network,
            "purpose": purpose,
            "runtime_env_id": runtime_env_id,
        }

    async def terminate_task(self, *, task_id: int, force: bool = False) -> dict[str, object]:
        if self._stub is None or self._runtime_pb2 is None:
            return {"forwarded": False, "task_id": task_id, "reason": "runtime-kernel unavailable"}
        response = await self._stub.TerminateTask(
            self._build_request(
                self._runtime_pb2.TerminateTaskRequest,
                _rpc_task_id=task_id,
                task_id=str(task_id),
                force=force,
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(task_id=task_id),
        )
        process = getattr(response, "process", None)
        return {
            "forwarded": True,
            "task_id": int(getattr(response, "task_id", "") or task_id),
            "phase": getattr(response, "phase", ""),
            "terminated": bool(getattr(response, "terminated", False)),
            "process_id": getattr(process, "process_id", ""),
            "pid": int(getattr(process, "pid", 0) or 0),
            "pgid": int(getattr(process, "pgid", 0) or 0),
            "status": getattr(process, "status", ""),
            "force": force,
        }

    async def attach_terminal(self, *, task_id: int, session_id: str) -> dict[str, object]:
        if self._stub is None or self._runtime_pb2 is None:
            return {"forwarded": False, "task_id": task_id, "reason": "runtime-kernel unavailable"}
        response = await self._stub.AttachTerminal(
            self._build_request(
                self._runtime_pb2.AttachTerminalRequest,
                _rpc_task_id=task_id,
                task_id=str(task_id),
                session_id=session_id,
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(task_id=task_id),
        )
        return {
            "forwarded": True,
            "task_id": int(getattr(response, "task_id", "") or task_id),
            "session_id": getattr(response, "session_id", session_id),
            "attached": bool(getattr(response, "attached", False)),
        }

    async def stream_terminal(self, *, task_id: int, stream: str) -> AsyncIterator[bytes]:
        if self._stub is None or self._runtime_pb2 is None:
            if False:
                yield b""
            return
        response_stream = self._stub.StreamTerminal(
            self._build_request(
                self._runtime_pb2.StreamTerminalRequest,
                _rpc_task_id=task_id,
                task_id=str(task_id),
                stream=stream,
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(task_id=task_id),
        )
        async for chunk in response_stream:
            data = bytes(getattr(chunk, "data", b""))
            if data:
                yield data

    async def open_terminal(
        self,
        *,
        task_id: int,
        session_id: str,
        command: str,
        args: list[str] | None = None,
        working_directory: str = "",
        environment_overrides: Mapping[str, str] | None = None,
        cols: int = 120,
        rows: int = 40,
        stdin_payload: bytes | None = None,
    ) -> dict[str, object]:
        if self._stub is None or self._runtime_pb2 is None:
            return {"forwarded": False, "task_id": task_id, "reason": "runtime-kernel unavailable"}
        response = await self._stub.OpenTerminal(
            self._build_request(
                self._runtime_pb2.OpenTerminalRequest,
                _rpc_task_id=task_id,
                task_id=str(task_id),
                session_id=session_id,
                command=command,
                args=list(args or []),
                working_directory=working_directory,
                environment_overrides=dict(environment_overrides or {}),
                cols=max(1, int(cols)),
                rows=max(1, int(rows)),
                stdin_payload=bytes(stdin_payload or b""),
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(task_id=task_id),
        )
        terminal = getattr(response, "terminal", None)
        process = getattr(response, "process", None)
        return {
            "forwarded": True,
            "task_id": task_id,
            "opened": bool(getattr(response, "opened", False)),
            "session_id": getattr(terminal, "session_id", session_id),
            "environment_id": getattr(process, "environment_id", ""),
            "status": getattr(terminal, "status", ""),
            "eof": bool(getattr(terminal, "eof", False)),
            "opened_at_ms": int(getattr(terminal, "opened_at_ms", 0) or 0),
            "closed_at_ms": int(getattr(terminal, "closed_at_ms", 0) or 0),
            "pid": int(getattr(process, "pid", 0) or 0),
            "pgid": int(getattr(process, "pgid", 0) or 0),
            "process_id": getattr(process, "process_id", ""),
            "command": getattr(process, "command", command),
            "args": list(getattr(process, "args", []) or []),
        }

    async def write_terminal(
        self,
        *,
        task_id: int,
        session_id: str,
        data: bytes,
        eof: bool = False,
    ) -> dict[str, object]:
        if self._stub is None or self._runtime_pb2 is None:
            return {"forwarded": False, "task_id": task_id, "reason": "runtime-kernel unavailable"}
        response = await self._stub.WriteTerminal(
            self._build_request(
                self._runtime_pb2.WriteTerminalRequest,
                _rpc_task_id=task_id,
                task_id=str(task_id),
                session_id=session_id,
                data=bytes(data),
                eof=eof,
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(task_id=task_id),
        )
        return {
            "forwarded": True,
            "task_id": int(getattr(response, "task_id", "") or task_id),
            "session_id": getattr(response, "session_id", session_id),
            "accepted": bool(getattr(response, "accepted", False)),
            "bytes_written": int(getattr(response, "bytes_written", 0) or 0),
            "eof": bool(getattr(response, "eof", eof)),
            "status": getattr(response, "status", ""),
        }

    async def resize_terminal(
        self,
        *,
        task_id: int,
        session_id: str,
        cols: int,
        rows: int,
    ) -> dict[str, object]:
        if self._stub is None or self._runtime_pb2 is None:
            return {"forwarded": False, "task_id": task_id, "reason": "runtime-kernel unavailable"}
        response = await self._stub.ResizeTerminal(
            self._build_request(
                self._runtime_pb2.ResizeTerminalRequest,
                _rpc_task_id=task_id,
                task_id=str(task_id),
                session_id=session_id,
                cols=max(1, int(cols)),
                rows=max(1, int(rows)),
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(task_id=task_id),
        )
        return {
            "forwarded": True,
            "task_id": int(getattr(response, "task_id", "") or task_id),
            "session_id": getattr(response, "session_id", session_id),
            "resized": bool(getattr(response, "resized", False)),
            "cols": int(getattr(response, "cols", cols) or cols),
            "rows": int(getattr(response, "rows", rows) or rows),
            "status": getattr(response, "status", ""),
        }

    async def close_terminal(
        self,
        *,
        task_id: int,
        session_id: str,
        force: bool = False,
    ) -> dict[str, object]:
        if self._stub is None or self._runtime_pb2 is None:
            return {"forwarded": False, "task_id": task_id, "reason": "runtime-kernel unavailable"}
        response = await self._stub.CloseTerminal(
            self._build_request(
                self._runtime_pb2.CloseTerminalRequest,
                _rpc_task_id=task_id,
                task_id=str(task_id),
                session_id=session_id,
                force=force,
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(task_id=task_id),
        )
        return {
            "forwarded": True,
            "task_id": int(getattr(response, "task_id", "") or task_id),
            "session_id": getattr(response, "session_id", session_id),
            "closed": bool(getattr(response, "closed", False)),
            "status": getattr(response, "status", ""),
            "closed_at_ms": int(getattr(response, "closed_at_ms", 0) or 0),
            "force": force,
        }

    async def stream_terminal_session(self, *, task_id: int, session_id: str) -> AsyncIterator[bytes]:
        if self._stub is None or self._runtime_pb2 is None:
            if False:
                yield b""
            return
        response_stream = self._stub.StreamTerminalSession(
            self._build_request(
                self._runtime_pb2.StreamTerminalSessionRequest,
                _rpc_task_id=task_id,
                task_id=str(task_id),
                session_id=session_id,
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(task_id=task_id),
        )
        async for chunk in response_stream:
            data = bytes(getattr(chunk, "data", b""))
            if data:
                yield data

    async def pause_task(self, *, task_id: int, reason: str, actor: str) -> dict[str, object]:
        if self._stub is None or self._runtime_pb2 is None:
            return {"forwarded": False, "task_id": task_id, "reason": "runtime-kernel unavailable"}
        response = await self._stub.PauseTask(
            self._build_request(
                self._runtime_pb2.PauseTaskRequest,
                _rpc_task_id=task_id,
                task_id=str(task_id),
                reason=reason,
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(task_id=task_id),
        )
        return {
            "forwarded": True,
            "task_id": int(getattr(response, "task_id", "") or task_id),
            "phase": getattr(response, "phase", ""),
            "reason": reason,
            "actor": actor,
        }

    async def resume_task(self, *, task_id: int, actor: str) -> dict[str, object]:
        if self._stub is None or self._runtime_pb2 is None:
            return {"forwarded": False, "task_id": task_id, "reason": "runtime-kernel unavailable"}
        response = await self._stub.ResumeTask(
            self._build_request(
                self._runtime_pb2.ResumeTaskRequest,
                _rpc_task_id=task_id,
                task_id=str(task_id),
                phase="executing",
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(task_id=task_id),
        )
        return {
            "forwarded": True,
            "task_id": int(getattr(response, "task_id", "") or task_id),
            "phase": getattr(response, "phase", ""),
            "actor": actor,
        }

    async def finalize_task(
        self,
        *,
        task_id: int,
        success: bool,
        final_phase: str,
        error_message: str | None,
    ) -> dict[str, object]:
        if self._stub is None or self._runtime_pb2 is None:
            return {"forwarded": False, "task_id": task_id, "reason": "runtime-kernel unavailable"}
        response = await self._stub.FinalizeTask(
            self._build_request(
                self._runtime_pb2.FinalizeTaskRequest,
                _rpc_task_id=task_id,
                task_id=str(task_id),
                success=success,
                error_message=error_message or "",
                final_phase=final_phase,
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(task_id=task_id),
        )
        return {
            "forwarded": True,
            "task_id": int(getattr(response, "task_id", "") or task_id),
            "final_phase": getattr(response, "final_phase", final_phase),
            "environment_id": getattr(response, "environment_id", ""),
            "success": success,
        }

    async def reconcile(self) -> dict[str, object]:
        if self._stub is None or self._runtime_pb2 is None:
            return {"forwarded": False, "reason": "runtime-kernel unavailable"}
        response = await self._stub.Reconcile(
            self._build_request(self._runtime_pb2.ReconcileRequest),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(),
        )
        return {
            "forwarded": True,
            "active_environments": int(getattr(response, "active_environments", 0)),
            "reconciled_environments": int(getattr(response, "reconciled_environments", 0)),
        }

    async def collect_snapshot(self, *, task_id: int) -> dict[str, object] | None:
        if self._stub is None or self._runtime_pb2 is None:
            return None
        response = await self._stub.CollectSnapshot(
            self._build_request(
                self._runtime_pb2.CollectSnapshotRequest,
                _rpc_task_id=task_id,
                task_id=str(task_id),
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(task_id=task_id),
        )
        try:
            payload = json.loads(bytes(getattr(response, "payload_json", b"")).decode("utf-8"))
        except Exception:
            payload = {
                "raw_payload_json": bytes(getattr(response, "payload_json", b"")).decode(
                    "utf-8",
                    errors="replace",
                )
            }
        if not isinstance(payload, dict):
            payload = {"payload": payload}

        payload.setdefault("task_id", getattr(response, "task_id", str(task_id)) or str(task_id))
        payload.setdefault("environment_id", getattr(response, "environment_id", ""))
        payload.setdefault("task_phase", getattr(response, "task_phase", ""))
        payload.setdefault("final_phase", getattr(response, "final_phase", ""))
        payload.setdefault("runtime_root", getattr(response, "runtime_root", ""))
        payload.setdefault("browser_session_count", int(getattr(response, "browser_session_count", 0) or 0))
        payload.setdefault("checkpoint_count", int(getattr(response, "checkpoint_count", 0) or 0))

        task_payload = payload.setdefault("task", {})
        if isinstance(task_payload, dict):
            task_payload.setdefault("task_id", getattr(response, "task_id", str(task_id)) or str(task_id))
            task_payload.setdefault("phase", getattr(response, "task_phase", ""))
            task_payload.setdefault("final_phase", getattr(response, "final_phase", ""))

        environment_payload = payload.setdefault("environment", {})
        if isinstance(environment_payload, dict):
            environment_payload.setdefault("environment_id", getattr(response, "environment_id", ""))
            environment_payload.setdefault("runtime_root", getattr(response, "runtime_root", ""))

        kernel_payload = payload.setdefault("kernel", {})
        if isinstance(kernel_payload, dict):
            kernel_payload.setdefault("runtime_root", getattr(response, "runtime_root", ""))
            kernel_payload.setdefault(
                "browser_session_count",
                int(getattr(response, "browser_session_count", 0) or 0),
            )
            kernel_payload.setdefault(
                "checkpoint_count",
                int(getattr(response, "checkpoint_count", 0) or 0),
            )
            if str(self.mode or "").strip().lower() == "rust":
                kernel_payload.setdefault("capabilities", list(_RUNTIME_KERNEL_CAPABILITY_DEFAULTS))
                kernel_payload.setdefault(
                    "authoritative_operations",
                    list(_RUNTIME_KERNEL_AUTHORITATIVE_OPERATION_DEFAULTS),
                )
                kernel_payload.setdefault("full_authority", True)
                kernel_payload.setdefault("partial_authority", False)
                kernel_payload.setdefault(
                    "authority_scope",
                    "workspace_lifecycle_plus_process_streaming_plus_interactive_terminal_sessions_plus_browser_sidecars_plus_checkpoint_registry",
                )
        return payload

    async def cleanup_environment(self, *, task_id: int, force: bool = False) -> dict[str, object]:
        if self._stub is None or self._runtime_pb2 is None:
            return {"forwarded": False, "task_id": task_id, "reason": "runtime-kernel unavailable"}
        response = await self._stub.CleanupEnvironment(
            self._build_request(
                self._runtime_pb2.CleanupEnvironmentRequest,
                _rpc_task_id=task_id,
                task_id=str(task_id),
                force=force,
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(task_id=task_id),
        )
        return {
            "forwarded": True,
            "task_id": task_id,
            "environment_id": getattr(response, "environment_id", ""),
            "cleaned": bool(getattr(response, "cleaned", False)),
            "workspace_removed": bool(getattr(response, "workspace_removed", False)),
            "runtime_root_removed": bool(getattr(response, "runtime_root_removed", False)),
            "worktree_mode": getattr(response, "worktree_mode", ""),
        }

    async def start_browser_session(
        self,
        *,
        task_id: int,
        scope_id: int,
        runtime_dir: str,
        transport: str,
        display_id: int | None = None,
        vnc_port: int | None = None,
        novnc_port: int | None = None,
        missing_binaries: list[str] | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        if self._stub is None or self._runtime_pb2 is None:
            return {
                "forwarded": False,
                "task_id": task_id,
                "scope_id": str(scope_id),
                "reason": "runtime-kernel unavailable",
            }
        response = await self._stub.StartBrowserSession(
            self._build_request(
                self._runtime_pb2.StartBrowserSessionRequest,
                _rpc_task_id=task_id,
                task_id=str(task_id),
                scope_id=str(scope_id),
                runtime_dir=runtime_dir,
                transport=transport,
                display_id=int(display_id or 0),
                vnc_port=int(vnc_port or 0),
                novnc_port=int(novnc_port or 0),
                missing_binaries=list(missing_binaries or []),
                metadata_labels=_stringify_metadata(metadata),
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(task_id=task_id),
        )
        session = getattr(response, "session", None)
        return {
            "forwarded": True,
            "task_id": task_id,
            "started": bool(getattr(response, "started", False)),
            "session_id": getattr(session, "session_id", ""),
            "environment_id": getattr(session, "environment_id", ""),
            "scope_id": getattr(session, "scope_id", str(scope_id)),
            "transport": getattr(session, "transport", transport),
            "status": getattr(session, "status", ""),
            "runtime_dir": getattr(session, "runtime_dir", runtime_dir),
            "display_id": int(getattr(session, "display_id", 0) or 0),
            "vnc_port": int(getattr(session, "vnc_port", 0) or 0),
            "novnc_port": int(getattr(session, "novnc_port", 0) or 0),
            "missing_binaries": list(getattr(session, "missing_binaries", []) or []),
            "created_at_ms": int(getattr(session, "created_at_ms", 0) or 0),
            "ended_at_ms": int(getattr(session, "ended_at_ms", 0) or 0),
            "metadata": dict(getattr(session, "metadata", {}) or {}),
        }

    async def stop_browser_session(
        self,
        *,
        task_id: int,
        scope_id: int,
        force: bool = False,
    ) -> dict[str, object]:
        if self._stub is None or self._runtime_pb2 is None:
            return {
                "forwarded": False,
                "task_id": task_id,
                "scope_id": str(scope_id),
                "reason": "runtime-kernel unavailable",
            }
        response = await self._stub.StopBrowserSession(
            self._build_request(
                self._runtime_pb2.StopBrowserSessionRequest,
                _rpc_task_id=task_id,
                task_id=str(task_id),
                scope_id=str(scope_id),
                force=force,
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(task_id=task_id),
        )
        return {
            "forwarded": True,
            "task_id": int(getattr(response, "task_id", "") or task_id),
            "scope_id": getattr(response, "scope_id", str(scope_id)),
            "stopped": bool(getattr(response, "stopped", False)),
            "status": getattr(response, "status", ""),
            "force": force,
        }

    async def get_browser_session(
        self,
        *,
        task_id: int,
        scope_id: int,
    ) -> dict[str, object] | None:
        if self._stub is None or self._runtime_pb2 is None:
            return None
        response = await self._stub.GetBrowserSession(
            self._build_request(
                self._runtime_pb2.GetBrowserSessionRequest,
                _rpc_task_id=task_id,
                task_id=str(task_id),
                scope_id=str(scope_id),
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(task_id=task_id),
        )
        if not bool(getattr(response, "found", False)):
            return None
        session = getattr(response, "session", None)
        return {
            "forwarded": True,
            "task_id": task_id,
            "session_id": getattr(session, "session_id", ""),
            "environment_id": getattr(session, "environment_id", ""),
            "scope_id": getattr(session, "scope_id", str(scope_id)),
            "transport": getattr(session, "transport", ""),
            "status": getattr(session, "status", ""),
            "runtime_dir": getattr(session, "runtime_dir", ""),
            "display_id": int(getattr(session, "display_id", 0) or 0),
            "vnc_port": int(getattr(session, "vnc_port", 0) or 0),
            "novnc_port": int(getattr(session, "novnc_port", 0) or 0),
            "missing_binaries": list(getattr(session, "missing_binaries", []) or []),
            "created_at_ms": int(getattr(session, "created_at_ms", 0) or 0),
            "ended_at_ms": int(getattr(session, "ended_at_ms", 0) or 0),
            "metadata": dict(getattr(session, "metadata", {}) or {}),
        }

    async def save_checkpoint(
        self,
        *,
        task_id: int,
        environment_id: str,
        success: bool,
        final_phase: str,
        retention_hours: int = 0,
    ) -> dict[str, object]:
        if self._stub is None or self._runtime_pb2 is None:
            return {"forwarded": False, "task_id": task_id, "reason": "runtime-kernel unavailable"}
        response = await self._stub.SaveCheckpoint(
            self._build_request(
                self._runtime_pb2.SaveCheckpointRequest,
                _rpc_task_id=task_id,
                task_id=str(task_id),
                environment_id=environment_id,
                success=success,
                final_phase=final_phase,
                retention_hours=max(0, int(retention_hours)),
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(task_id=task_id),
        )
        checkpoint = getattr(response, "checkpoint", None)
        return {
            "forwarded": True,
            "task_id": task_id,
            "checkpoint_id": getattr(checkpoint, "checkpoint_id", ""),
            "environment_id": getattr(checkpoint, "environment_id", environment_id),
            "success": bool(getattr(checkpoint, "success", success)),
            "final_phase": getattr(checkpoint, "final_phase", final_phase),
            "checkpoint_dir": getattr(checkpoint, "checkpoint_dir", ""),
            "manifest_path": getattr(checkpoint, "manifest_path", ""),
            "snapshot_path": getattr(checkpoint, "snapshot_path", ""),
            "patch_path": getattr(checkpoint, "patch_path", ""),
            "git_status_path": getattr(checkpoint, "git_status_path", ""),
            "untracked_bundle_path": getattr(checkpoint, "untracked_bundle_path", ""),
            "created_at_ms": int(getattr(checkpoint, "created_at_ms", 0) or 0),
            "expires_at_ms": int(getattr(checkpoint, "expires_at_ms", 0) or 0),
            "commit_sha": getattr(checkpoint, "commit_sha", ""),
            "has_untracked_bundle": bool(getattr(checkpoint, "has_untracked_bundle", False)),
            "saved": bool(getattr(response, "saved", False)),
        }

    async def get_checkpoint(
        self,
        *,
        task_id: int,
        checkpoint_id: str = "",
    ) -> dict[str, object] | None:
        if self._stub is None or self._runtime_pb2 is None:
            return None
        response = await self._stub.GetCheckpoint(
            self._build_request(
                self._runtime_pb2.GetCheckpointRequest,
                _rpc_task_id=task_id,
                task_id=str(task_id),
                checkpoint_id=checkpoint_id,
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(task_id=task_id),
        )
        if not bool(getattr(response, "found", False)):
            return None
        checkpoint = getattr(response, "checkpoint", None)
        return {
            "forwarded": True,
            "task_id": task_id,
            "checkpoint_id": getattr(checkpoint, "checkpoint_id", checkpoint_id),
            "environment_id": getattr(checkpoint, "environment_id", ""),
            "success": bool(getattr(checkpoint, "success", False)),
            "final_phase": getattr(checkpoint, "final_phase", ""),
            "checkpoint_dir": getattr(checkpoint, "checkpoint_dir", ""),
            "manifest_path": getattr(checkpoint, "manifest_path", ""),
            "snapshot_path": getattr(checkpoint, "snapshot_path", ""),
            "patch_path": getattr(checkpoint, "patch_path", ""),
            "git_status_path": getattr(checkpoint, "git_status_path", ""),
            "untracked_bundle_path": getattr(checkpoint, "untracked_bundle_path", ""),
            "created_at_ms": int(getattr(checkpoint, "created_at_ms", 0) or 0),
            "expires_at_ms": int(getattr(checkpoint, "expires_at_ms", 0) or 0),
            "commit_sha": getattr(checkpoint, "commit_sha", ""),
            "has_untracked_bundle": bool(getattr(checkpoint, "has_untracked_bundle", False)),
        }

    async def restore_checkpoint(
        self,
        *,
        task_id: int,
        checkpoint_id: str = "",
        workspace_path: str = "",
    ) -> dict[str, object]:
        request_type = getattr(self._runtime_pb2, "RestoreCheckpointRequest", None) if self._runtime_pb2 else None
        rpc = getattr(self._stub, "RestoreCheckpoint", None) if self._stub is not None else None
        if request_type is None or rpc is None:
            raise RuntimeError("grpc_runtime_kernel_restore_checkpoint_unavailable")
        response = await rpc(
            self._build_request(
                request_type,
                _rpc_task_id=task_id,
                task_id=str(task_id),
                checkpoint_id=checkpoint_id,
                workspace_path=workspace_path,
            ),
            timeout=config.INTERNAL_RPC_DEADLINE_MS / 1000,
            metadata=self._rpc_metadata(task_id=task_id),
        )
        checkpoint = getattr(response, "checkpoint", None)
        return {
            "forwarded": True,
            "task_id": task_id,
            "checkpoint_id": getattr(checkpoint, "checkpoint_id", checkpoint_id),
            "found": bool(getattr(response, "found", False)),
            "restored": bool(getattr(response, "restored", False)),
            "workspace_path": getattr(response, "workspace_path", workspace_path),
            "restored_commit_sha": getattr(response, "restored_commit_sha", ""),
            "restored_paths": list(getattr(response, "restored_paths", []) or []),
            "error_message": getattr(response, "error_message", ""),
            "environment_id": getattr(checkpoint, "environment_id", ""),
            "checkpoint_dir": getattr(checkpoint, "checkpoint_dir", ""),
            "manifest_path": getattr(checkpoint, "manifest_path", ""),
            "snapshot_path": getattr(checkpoint, "snapshot_path", ""),
            "patch_path": getattr(checkpoint, "patch_path", ""),
            "git_status_path": getattr(checkpoint, "git_status_path", ""),
            "untracked_bundle_path": getattr(checkpoint, "untracked_bundle_path", ""),
            "commit_sha": getattr(checkpoint, "commit_sha", ""),
            "has_untracked_bundle": bool(getattr(checkpoint, "has_untracked_bundle", False)),
        }

    def health(self) -> dict[str, object]:
        connected = self._channel is not None
        raw_details = self._last_health.get("details")
        details = dict(raw_details) if isinstance(raw_details, Mapping) else {}
        remote = self._transport not in {"in-process", "python", "unknown"}
        ready = bool(self._last_health.get("ready")) and connected and self._startup_error is None
        rust_mode = str(self.mode or "").strip().lower() == "rust"
        authoritative = parse_boolish(
            self._last_health.get("authoritative", details.get("authoritative")),
            default=ready and rust_mode,
        )
        production_ready = parse_boolish(
            self._last_health.get("production_ready", details.get("production_ready")),
            default=ready and authoritative,
        )
        authority_scope = str(
            self._last_health.get("authority_scope")
            or details.get("authority_scope")
            or ("full_runtime" if authoritative else "unavailable")
        )
        authoritative_ops_value = self._last_health.get(
            "authoritative_operations",
            details.get("authoritative_operations"),
        )
        if isinstance(authoritative_ops_value, str):
            authoritative_operations = [item.strip() for item in authoritative_ops_value.split(",") if item.strip()]
        elif isinstance(authoritative_ops_value, (list, tuple, set)):
            authoritative_operations = [str(item).strip() for item in authoritative_ops_value if str(item).strip()]
        else:
            authoritative_operations = []
        if rust_mode and not authoritative_operations:
            authoritative_operations = list(_RUNTIME_KERNEL_AUTHORITATIVE_OPERATION_DEFAULTS)
        full_authority = parse_boolish(
            self._last_health.get("full_authority", details.get("full_authority")),
            default=authoritative and rust_mode,
        )
        partial_authority = parse_boolish(
            self._last_health.get("partial_authority", details.get("partial_authority")),
            default=False,
        )
        blockers_value = self._last_health.get("cutover_blockers", details.get("cutover_blockers"))
        if isinstance(blockers_value, str):
            cutover_blockers = [item.strip() for item in blockers_value.split(",") if item.strip()]
        elif isinstance(blockers_value, (list, tuple, set)):
            cutover_blockers = [str(item).strip() for item in blockers_value if str(item).strip()]
        else:
            cutover_blockers = []
        return {
            **self._last_health,
            "details": details,
            "remote": remote,
            "connected": connected,
            "ready": ready,
            "authoritative": authoritative,
            "production_ready": production_ready and connected and self._startup_error is None,
            "cutover_allowed": ready and authoritative and production_ready,
            "authority_scope": authority_scope,
            "authoritative_operations": authoritative_operations,
            "full_authority": full_authority,
            "partial_authority": partial_authority,
            "cutover_blockers": cutover_blockers,
            "startup_error": self._startup_error,
        }


def build_runtime_kernel_client(*, runtime_root: Path, store: RuntimeStore) -> RuntimeKernelClient:
    """Build the Rust runtime-kernel client."""

    selection = select_engine_backend(
        mode=config.INTERNAL_RPC_MODE,
        agent_id=config.AGENT_ID,
    )
    return GrpcRuntimeKernelClient(
        runtime_root=runtime_root,
        store=store,
        mode=selection.mode,
        selection_reason=selection.reason,
        agent_id=selection.agent_id,
    )
