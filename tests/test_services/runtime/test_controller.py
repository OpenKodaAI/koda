"""Focused tests for the runtime controller gRPC seam."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import koda.services.runtime.controller as controller_module


class _StoreStub:
    def __init__(self, *, env: dict[str, Any] | None = None, task: dict[str, Any] | None = None) -> None:
        self.env = env
        self.task = task or {"id": 1, "task_id": 1, "current_phase": "executing", "status": "running"}
        self.events: list[dict[str, Any]] = []
        self.warnings: list[dict[str, Any]] = []
        self.artifacts: list[dict[str, Any]] = []
        self.processes: list[dict[str, Any]] = []
        self.browser_sessions: list[dict[str, Any]] = []
        self.terminals: list[dict[str, Any]] = []
        self.attach_sessions: list[dict[str, Any]] = []
        self.service_endpoints: list[dict[str, Any]] = []

    def add_event(
        self,
        *,
        task_id: int | None,
        env_id: int | None,
        attempt: int | None,
        phase: str | None,
        event_type: str,
        severity: str = "info",
        payload: dict[str, Any] | None = None,
        artifact_refs: list[str] | None = None,
        resource_snapshot_ref: str | None = None,
    ) -> dict[str, Any]:
        event = {
            "seq": len(self.events) + 1,
            "task_id": task_id,
            "env_id": env_id,
            "attempt": attempt,
            "phase": phase,
            "event_type": event_type,
            "severity": severity,
            "payload": dict(payload or {}),
            "artifact_refs": list(artifact_refs or []),
            "resource_snapshot_ref": resource_snapshot_ref,
        }
        self.events.append(event)
        return event

    def list_events(
        self,
        *,
        task_id: int | None = None,
        env_id: int | None = None,
        after_seq: int = 0,
    ) -> list[dict[str, Any]]:
        rows = [item for item in self.events if int(item["seq"]) > after_seq]
        if task_id is not None:
            rows = [item for item in rows if item.get("task_id") == task_id]
        if env_id is not None:
            rows = [item for item in rows if item.get("env_id") == env_id]
        return rows

    def list_environments(self) -> list[dict[str, Any]]:
        return [self.env] if self.env else []

    def get_environment_by_task(self, task_id: int) -> dict[str, Any] | None:
        if self.env and int(self.env["task_id"]) == task_id:
            return self.env
        return None

    def get_environment(self, env_id: int) -> dict[str, Any] | None:
        if self.env and int(self.env["id"]) == env_id:
            return self.env
        return None

    def update_environment(self, env_id: int, **fields: Any) -> None:
        if self.env and int(self.env["id"]) == env_id:
            self.env.update(fields)

    def update_task_runtime(self, task_id: int, **fields: Any) -> None:
        if int(self.task["task_id"]) != task_id and int(self.task["id"]) != task_id:
            return
        mapped = dict(fields)
        if "phase" in mapped:
            mapped["current_phase"] = mapped.pop("phase")
        self.task.update(mapped)

    def get_task_runtime(self, task_id: int) -> dict[str, Any] | None:
        if int(self.task["task_id"]) == task_id or int(self.task["id"]) == task_id:
            return self.task
        return None

    def update_runtime_queue_item(self, task_id: int, *, status: str, queue_position: int | None = None) -> None:
        self.task["queue_status"] = status
        if queue_position is not None:
            self.task["queue_position"] = queue_position

    def list_runtime_queues(self) -> list[dict[str, Any]]:
        return []

    def count_envs_by_phase(self) -> dict[str, int]:
        if not self.env:
            return {}
        return {str(self.env.get("current_phase") or "unknown"): 1}

    def list_processes(self, task_id: int, *, env_id: int | None = None) -> list[dict[str, Any]]:
        rows = [item for item in self.processes if int(item["task_id"]) == task_id]
        if env_id is not None:
            rows = [item for item in rows if int(item.get("env_id") or 0) == env_id]
        return [dict(item) for item in rows]

    def get_process(self, process_id: int) -> dict[str, Any] | None:
        for row in self.processes:
            if int(row["id"]) == process_id:
                return dict(row)
        return None

    def update_process(self, process_id: int, **fields: Any) -> None:
        for row in self.processes:
            if int(row["id"]) != process_id:
                continue
            row.update(fields)
            return

    def create_attach_session(self, **kwargs: Any) -> int:
        row = {"id": len(self.attach_sessions) + 1, "status": "active", **kwargs}
        self.attach_sessions.append(row)
        return int(row["id"])

    def touch_attach_session(self, token: str) -> dict[str, Any] | None:
        for row in self.attach_sessions:
            if str(row.get("token") or "") == token:
                return dict(row)
        return None

    def touch_attach_session_by_id(self, session_id: int) -> dict[str, Any] | None:
        for row in self.attach_sessions:
            if int(row.get("id") or 0) == session_id:
                return dict(row)
        return None

    def close_attach_session(self, token: str) -> None:
        for row in self.attach_sessions:
            if str(row.get("token") or "") == token:
                row["status"] = "closed"

    def close_attach_session_by_id(self, session_id: int) -> None:
        for row in self.attach_sessions:
            if int(row.get("id") or 0) == session_id:
                row["status"] = "closed"

    def list_attach_sessions(self, task_id: int) -> list[dict[str, Any]]:
        return [dict(item) for item in self.attach_sessions if int(item["task_id"]) == task_id]

    def upsert_terminal(self, **kwargs: Any) -> int:
        row: dict[str, Any] = {
            "id": len(self.terminals) + 1,
            "cursor_offset": 0,
            "last_offset": 0,
            **kwargs,
        }
        self.terminals.append(row)
        return int(row["id"])

    def update_terminal(self, terminal_id: int, **fields: Any) -> None:
        for row in self.terminals:
            if int(row["id"]) == terminal_id:
                row.update(fields)
                return

    def list_terminals(self, task_id: int) -> list[dict[str, Any]]:
        return [dict(item) for item in self.terminals if int(item["task_id"]) == task_id]

    def list_browser_sessions(self, task_id: int) -> list[dict[str, Any]]:
        return [dict(item) for item in self.browser_sessions if int(item["task_id"]) == task_id]

    def list_service_endpoints(self, task_id: int) -> list[dict[str, Any]]:
        return [dict(item) for item in self.service_endpoints if int(item["task_id"]) == task_id]

    def list_loop_cycles(self, task_id: int) -> list[dict[str, Any]]:
        return []

    def list_resource_samples(self, task_id: int, limit: int | None = None) -> list[dict[str, Any]]:
        return []

    def heartbeat(self, task_id: int, env_id: int | None, *, phase: str | None = None) -> None:
        if phase:
            self.task["current_phase"] = phase
            if self.env:
                self.env["current_phase"] = phase

    def add_checkpoint(self, **kwargs: Any) -> int:
        return 41

    def add_artifact(
        self,
        *,
        task_id: int,
        env_id: int | None,
        artifact_kind: str,
        label: str,
        path: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        artifact = {
            "task_id": task_id,
            "env_id": env_id,
            "artifact_kind": artifact_kind,
            "label": label,
            "path": path,
            "metadata": dict(metadata or {}),
        }
        self.artifacts.append(artifact)
        return artifact

    def add_browser_session(
        self,
        *,
        task_id: int,
        env_id: int | None,
        scope_id: int,
        transport: str,
        status: str,
        display_id: int | None,
        vnc_port: int | None,
        novnc_port: int | None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        row: dict[str, Any] = {
            "id": len(self.browser_sessions) + 1,
            "task_id": task_id,
            "env_id": env_id,
            "scope_id": scope_id,
            "transport": transport,
            "status": status,
            "display_id": display_id,
            "vnc_port": vnc_port,
            "novnc_port": novnc_port,
            "metadata": dict(metadata or {}),
        }
        self.browser_sessions.append(row)
        return int(row["id"])

    def update_browser_session(self, session_id: int, **fields: Any) -> None:
        for row in self.browser_sessions:
            if int(row["id"]) != session_id:
                continue
            row.update(fields)
            return

    def add_service_endpoint(
        self,
        *,
        task_id: int,
        env_id: int | None,
        process_id: int | None,
        service_kind: str,
        label: str,
        host: str,
        port: int,
        protocol: str,
        status: str,
        url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        row: dict[str, Any] = {
            "id": len(self.service_endpoints) + 1,
            "task_id": task_id,
            "env_id": env_id,
            "process_id": process_id,
            "service_kind": service_kind,
            "label": label,
            "host": host,
            "port": port,
            "protocol": protocol,
            "status": status,
            "url": url,
            "metadata": dict(metadata or {}),
        }
        self.service_endpoints.append(row)
        return int(row["id"])

    def update_service_endpoint(self, endpoint_id: int, **fields: Any) -> None:
        for row in self.service_endpoints:
            if int(row["id"]) != endpoint_id:
                continue
            row.update(fields)
            return

    def update_port_allocation(self, allocation_id: int, **fields: Any) -> None:
        return None

    def list_port_allocations(self, task_id: int) -> list[dict[str, Any]]:
        return []

    def list_artifacts(self, task_id: int) -> list[dict[str, Any]]:
        return list(self.artifacts)

    def add_warning(
        self,
        *,
        task_id: int,
        env_id: int | None,
        warning_type: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        warning = {
            "task_id": task_id,
            "env_id": env_id,
            "warning_type": warning_type,
            "message": message,
            "details": dict(details or {}),
        }
        self.warnings.append(warning)
        return warning


class _KernelStub:
    def __init__(
        self,
        *,
        health_payload: dict[str, Any] | None = None,
        create_environment_result: dict[str, Any] | None = None,
        start_task_result: dict[str, Any] | None = None,
        attach_terminal_result: dict[str, Any] | None = None,
        open_terminal_result: dict[str, Any] | None = None,
        write_terminal_result: dict[str, Any] | None = None,
        resize_terminal_result: dict[str, Any] | None = None,
        close_terminal_result: dict[str, Any] | None = None,
        pause_result: dict[str, Any] | None = None,
        resume_result: dict[str, Any] | None = None,
        finalize_result: dict[str, Any] | None = None,
        reconcile_result: dict[str, Any] | None = None,
        terminate_result: dict[str, Any] | None = None,
        health_sequence: list[dict[str, Any]] | None = None,
        cleanup_environment_result: dict[str, Any] | None = None,
        start_browser_session_result: dict[str, Any] | None = None,
        stop_browser_session_result: dict[str, Any] | None = None,
        get_browser_session_result: dict[str, Any] | None = None,
        save_checkpoint_result: dict[str, Any] | None = None,
        get_checkpoint_result: dict[str, Any] | None = None,
        restore_checkpoint_result: dict[str, Any] | None = None,
        collect_snapshot_result: dict[str, Any] | None = None,
    ) -> None:
        self._health_payload = dict(health_payload or {})
        self._health_sequence = [dict(item) for item in (health_sequence or [])]
        self.create_environment_result = dict(create_environment_result or {})
        self.start_task_result = dict(start_task_result or {})
        self.attach_terminal_result = dict(attach_terminal_result or {})
        self.open_terminal_result = dict(open_terminal_result or {})
        self.write_terminal_result = dict(write_terminal_result or {})
        self.resize_terminal_result = dict(resize_terminal_result or {})
        self.close_terminal_result = dict(close_terminal_result or {})
        self.pause_result = dict(pause_result or {})
        self.resume_result = dict(resume_result or {})
        self.finalize_result = dict(finalize_result or {})
        self.reconcile_result = dict(reconcile_result or {})
        self.terminate_result = dict(terminate_result or {})
        self.cleanup_environment_result = dict(cleanup_environment_result or {})
        self.start_browser_session_result = dict(start_browser_session_result or {})
        self.stop_browser_session_result = dict(stop_browser_session_result or {})
        self.get_browser_session_result = dict(get_browser_session_result or {})
        self.save_checkpoint_result = dict(save_checkpoint_result or {})
        self.get_checkpoint_result = dict(get_checkpoint_result or {})
        self.restore_checkpoint_result = dict(restore_checkpoint_result or {})
        self.collect_snapshot_result = dict(collect_snapshot_result or {})
        self.health_calls = 0

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

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
    ) -> dict[str, Any]:
        return dict(self.create_environment_result)

    async def start_task(self, *, task_id: int, command: str, args: list[str] | None = None) -> dict[str, Any]:
        return dict(self.start_task_result)

    async def attach_terminal(self, *, task_id: int, session_id: str) -> dict[str, Any]:
        return dict(self.attach_terminal_result)

    async def open_terminal(
        self,
        *,
        task_id: int,
        session_id: str,
        command: str,
        args: list[str] | None = None,
        working_directory: str = "",
        environment_overrides: dict[str, str] | None = None,
        cols: int = 120,
        rows: int = 40,
        stdin_payload: bytes | None = None,
    ) -> dict[str, Any]:
        return dict(self.open_terminal_result)

    async def write_terminal(self, *, task_id: int, session_id: str, data: bytes, eof: bool = False) -> dict[str, Any]:
        return dict(self.write_terminal_result)

    async def resize_terminal(self, *, task_id: int, session_id: str, cols: int, rows: int) -> dict[str, Any]:
        return dict(self.resize_terminal_result)

    async def close_terminal(self, *, task_id: int, session_id: str, force: bool = False) -> dict[str, Any]:
        return dict(self.close_terminal_result)

    async def stream_terminal_session(self, *, task_id: int, session_id: str) -> Any:
        if False:
            yield b""
        return

    async def stream_terminal(self, *, task_id: int, stream: str) -> Any:
        if False:
            yield b""
        return

    def health(self) -> dict[str, Any]:
        self.health_calls += 1
        if self._health_sequence:
            index = min(self.health_calls - 1, len(self._health_sequence) - 1)
            return dict(self._health_sequence[index])
        return dict(self._health_payload)

    async def pause_task(self, *, task_id: int, reason: str, actor: str) -> dict[str, Any]:
        return dict(self.pause_result)

    async def resume_task(self, *, task_id: int, actor: str) -> dict[str, Any]:
        return dict(self.resume_result)

    async def terminate_task(self, *, task_id: int, force: bool = False) -> dict[str, Any]:
        return dict(self.terminate_result)

    async def finalize_task(
        self,
        *,
        task_id: int,
        success: bool,
        final_phase: str,
        error_message: str | None,
    ) -> dict[str, Any]:
        return dict(self.finalize_result)

    async def reconcile(self) -> dict[str, Any]:
        return dict(self.reconcile_result)

    async def cleanup_environment(self, *, task_id: int, force: bool = False) -> dict[str, Any]:
        return dict(self.cleanup_environment_result)

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
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return dict(self.start_browser_session_result)

    async def stop_browser_session(self, *, task_id: int, scope_id: int, force: bool = False) -> dict[str, Any]:
        return dict(self.stop_browser_session_result)

    async def get_browser_session(self, *, task_id: int, scope_id: int) -> dict[str, Any] | None:
        return dict(self.get_browser_session_result) if self.get_browser_session_result else None

    async def save_checkpoint(
        self,
        *,
        task_id: int,
        environment_id: str,
        success: bool,
        final_phase: str,
        retention_hours: int = 0,
    ) -> dict[str, Any]:
        return dict(self.save_checkpoint_result)

    async def get_checkpoint(self, *, task_id: int, checkpoint_id: str = "") -> dict[str, Any] | None:
        return dict(self.get_checkpoint_result) if self.get_checkpoint_result else None

    async def restore_checkpoint(
        self,
        *,
        task_id: int,
        checkpoint_id: str = "",
        workspace_path: str = "",
    ) -> dict[str, Any]:
        return dict(self.restore_checkpoint_result)

    async def collect_snapshot(self, *, task_id: int) -> dict[str, Any] | None:
        del task_id
        return dict(self.collect_snapshot_result) if self.collect_snapshot_result else None


class _PortAllocatorStub:
    def __init__(self, store: _StoreStub) -> None:
        self.store = store
        self.next_id = 1
        self.allocations: list[dict[str, Any]] = []
        self.released: list[dict[str, Any]] = []

    def allocate(
        self,
        *,
        task_id: int,
        env_id: int,
        purpose: str,
        start_port: int,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        row = {
            "id": self.next_id,
            "task_id": task_id,
            "env_id": env_id,
            "purpose": purpose,
            "port": start_port + self.next_id,
            "metadata": dict(metadata or {}),
        }
        self.next_id += 1
        self.allocations.append(dict(row))
        return row

    def release_ports(self, *, task_id: int, env_id: int, purposes: tuple[str, ...]) -> None:
        self.released.append({"task_id": task_id, "env_id": env_id, "purposes": purposes})

    def release_task_ports(self, task_id: int) -> None:
        self.released.append({"task_id": task_id, "env_id": None, "purposes": ("*",)})


def _build_controller(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    store: _StoreStub,
    kernel: _KernelStub,
) -> controller_module.RuntimeController:
    monkeypatch.setattr(controller_module, "RuntimeStore", lambda: store)
    monkeypatch.setattr(controller_module, "build_runtime_kernel_client", lambda runtime_root, store: kernel)
    monkeypatch.setattr(controller_module, "RecoveryManager", lambda store: SimpleNamespace())
    monkeypatch.setattr(controller_module, "PortAllocator", _PortAllocatorStub)
    monkeypatch.setattr(controller_module, "RUNTIME_BROWSER_LIVE_ENABLED", False)
    monkeypatch.setattr(controller_module, "RUNTIME_ENVIRONMENTS_ENABLED", True)
    monkeypatch.setattr(controller_module, "RUNTIME_RECOVERY_ENABLED", False)
    monkeypatch.setattr(controller_module.shutil, "which", lambda name: f"/usr/bin/{name}")
    return controller_module.RuntimeController(runtime_root=tmp_path / "runtime")


def test_runtime_health_snapshot_keeps_kernel_payload_consistent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = _StoreStub()
    kernel = _KernelStub(
        health_sequence=[
            {
                "mode": "rust",
                "transport": "grpc-uds",
                "connected": True,
                "ready": True,
                "configured_target": "unix:///tmp/runtime-kernel.sock",
                "selection_reason": "rust-default",
            },
            {
                "mode": "rust",
                "transport": "grpc-uds",
                "connected": False,
                "ready": False,
            },
        ]
    )
    controller = _build_controller(monkeypatch, tmp_path, store=store, kernel=kernel)

    payload = controller.get_runtime_health_snapshot()

    assert kernel.health_calls == 1
    assert payload["runtime_kernel"]["ready"] is True
    assert payload["runtime_kernel"]["authoritative"] is True
    assert payload["readiness"]["runtime_kernel"]["ready"] is True
    assert payload["runtime_kernel_cutover"]["state"] == "remote_authoritative"
    assert payload["runtime_kernel_cutover"]["forwarding_expected"] is True
    assert payload["runtime_kernel_cutover"]["cutover_allowed"] is True


@pytest.mark.asyncio
async def test_add_artifact_merges_engine_metadata_and_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "artifact.txt"
    file_path.write_text("artifact payload", encoding="utf-8")

    class _ArtifactEngineStub:
        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        async def put_artifact(
            self,
            *,
            path: str,
            logical_filename: str,
            mime_type: str,
            source_metadata_json: str,
            purpose: str,
        ) -> dict[str, Any]:
            assert path == str(file_path)
            assert logical_filename == file_path.name
            assert purpose == "document"
            return {
                "artifact_id": "artifact-123",
                "object_key": "agent_a/artifact.txt",
                "content_hash": "ingest-hash",
                "mime_type": "text/plain",
                "metadata_json": '{"phase":"ingest"}',
            }

        async def get_artifact_metadata_by_artifact_id(self, *, artifact_id: str) -> dict[str, Any]:
            assert artifact_id == "artifact-123"
            return {
                "artifact_id": artifact_id,
                "object_key": "agent_a/artifact.txt",
                "content_hash": "metadata-hash",
                "mime_type": "text/plain",
                "metadata_json": '{"phase":"metadata","size_bytes":16}',
            }

        async def generate_evidence_by_artifact_id(self, *, artifact_id: str) -> dict[str, Any]:
            assert artifact_id == "artifact-123"
            return {"evidence_json": '{"excerpt":"artifact payload"}'}

        def health(self) -> dict[str, Any]:
            return {"ready": True}

    store = _StoreStub(
        env={
            "id": 7,
            "task_id": 1,
            "status": "active",
            "current_phase": "executing",
            "workspace_path": str(tmp_path),
            "runtime_dir": str(tmp_path / "runtime"),
        }
    )
    kernel = _KernelStub()
    monkeypatch.setattr(controller_module, "build_artifact_engine_client", lambda agent_id=None: _ArtifactEngineStub())
    controller = _build_controller(monkeypatch, tmp_path, store=store, kernel=kernel)

    await controller.add_artifact(
        task_id=1,
        artifact_kind="document",
        label="artifact.txt",
        path=str(file_path),
    )

    metadata = store.artifacts[0]["metadata"]
    assert metadata["object_key"] == "agent_a/artifact.txt"
    assert metadata["content_hash"] == "metadata-hash"
    assert metadata["metadata_json"] == '{"phase":"metadata","size_bytes":16}'
    assert metadata["evidence_json"] == '{"excerpt":"artifact payload"}'


@pytest.mark.asyncio
async def test_pause_environment_records_runtime_kernel_forwarding_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    store = _StoreStub(
        env={
            "id": 7,
            "task_id": 1,
            "status": "active",
            "current_phase": "executing",
            "workspace_path": str(workspace_path),
            "runtime_dir": str(tmp_path / "runtime" / "tasks" / "1"),
            "pause_state": "none",
        }
    )
    kernel = _KernelStub(
        health_payload={
            "mode": "rust",
            "transport": "grpc-uds",
            "connected": True,
            "ready": True,
            "authoritative": True,
            "production_ready": True,
        },
        pause_result={"forwarded": False, "reason": "runtime-kernel unavailable"},
    )
    controller = _build_controller(monkeypatch, tmp_path, store=store, kernel=kernel)

    ok = await controller.pause_environment(task_id=1, reason="operator requested pause")

    readiness = controller.get_runtime_readiness()
    assert ok is False
    assert readiness["runtime_kernel_operations"]["pause"]["ok"] is False
    assert store.warnings[-1]["warning_type"] == "runtime_kernel_pause_failed"
    assert any(event["event_type"] == "runtime_kernel.pause" for event in store.events)


@pytest.mark.asyncio
async def test_finalize_task_records_kernel_failure_but_keeps_local_retention(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    runtime_dir = tmp_path / "runtime" / "tasks" / "1"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_dir = runtime_dir / "checkpoints" / "kernel-1"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = checkpoint_dir / "manifest.json"
    snapshot_path = checkpoint_dir / "snapshot.json"
    patch_path = checkpoint_dir / "git.patch"
    git_status_path = checkpoint_dir / "git_status.txt"
    manifest_path.write_text('{"ok":true}', encoding="utf-8")
    snapshot_path.write_text('{"task_id":1}', encoding="utf-8")
    patch_path.write_text("", encoding="utf-8")
    git_status_path.write_text("", encoding="utf-8")
    store = _StoreStub(
        env={
            "id": 9,
            "task_id": 1,
            "status": "active",
            "current_phase": "executing",
            "workspace_path": str(workspace_path),
            "runtime_dir": str(runtime_dir),
            "branch_name": "main",
            "pause_state": "none",
        }
    )
    kernel = _KernelStub(
        health_payload={
            "mode": "rust",
            "transport": "grpc-uds",
            "connected": True,
            "ready": True,
            "authoritative": True,
            "production_ready": True,
        },
        save_checkpoint_result={
            "forwarded": True,
            "saved": True,
            "checkpoint_id": "kernel-1",
            "checkpoint_dir": str(checkpoint_dir),
            "manifest_path": str(manifest_path),
            "snapshot_path": str(snapshot_path),
            "patch_path": str(patch_path),
            "git_status_path": str(git_status_path),
            "untracked_bundle_path": "",
            "has_untracked_bundle": False,
            "commit_sha": "abc123",
        },
        finalize_result={"forwarded": False, "reason": "runtime-kernel unavailable"},
    )
    controller = _build_controller(monkeypatch, tmp_path, store=store, kernel=kernel)

    env = await controller.finalize_task(task_id=1, success=True, summary={"result": "ok"})

    snapshot = controller.get_runtime_health_snapshot()
    assert env is not None
    assert env["current_phase"] == "completed_retained"
    assert env["status"] == "retained"
    assert bool(env.get("save_verified_at"))
    assert snapshot["runtime_kernel_operations"]["finalize"]["ok"] is False
    assert store.warnings[-1]["warning_type"] == "runtime_kernel_finalize_failed"


@pytest.mark.asyncio
async def test_finalize_task_fails_closed_when_rust_requires_kernel_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    runtime_dir = tmp_path / "runtime" / "tasks" / "1"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    store = _StoreStub(
        env={
            "id": 91,
            "task_id": 1,
            "status": "active",
            "current_phase": "executing",
            "workspace_path": str(workspace_path),
            "runtime_dir": str(runtime_dir),
            "branch_name": "main",
            "pause_state": "none",
        }
    )
    kernel = _KernelStub(
        health_payload={
            "mode": "rust",
            "transport": "grpc-uds",
            "connected": True,
            "ready": True,
            "authoritative": False,
            "production_ready": False,
            "authoritative_operations": ["create_environment", "cleanup_environment", "save_checkpoint"],
        },
        save_checkpoint_result={"forwarded": False, "reason": "runtime-kernel unavailable"},
    )
    controller = _build_controller(monkeypatch, tmp_path, store=store, kernel=kernel)

    env = await controller.finalize_task(task_id=1, success=True, summary={"result": "ok"})

    assert env is not None
    assert env["current_phase"] == "recoverable_failed_retained"
    assert env["checkpoint_status"] == "failed"
    readiness = controller.get_runtime_readiness()
    assert readiness["runtime_kernel_operations"]["save_checkpoint"]["ok"] is False


@pytest.mark.asyncio
async def test_reconcile_runtime_state_persists_kernel_reconcile_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = _StoreStub()
    kernel = _KernelStub(
        health_payload={
            "mode": "rust",
            "transport": "grpc-uds",
            "connected": True,
            "ready": True,
            "authoritative": True,
            "production_ready": True,
        },
        reconcile_result={"forwarded": True, "active_environments": 1, "reconciled_environments": 3},
    )
    controller = _build_controller(monkeypatch, tmp_path, store=store, kernel=kernel)

    await controller.reconcile_runtime_state()

    readiness = controller.get_runtime_readiness()
    assert readiness["runtime_kernel_operations"]["reconcile"]["ok"] is True
    assert readiness["runtime_kernel_operations"]["reconcile"]["reconciled_environments"] == 3


@pytest.mark.asyncio
async def test_pause_environment_keeps_mirror_forwarding_best_effort(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    store = _StoreStub(
        env={
            "id": 11,
            "task_id": 1,
            "status": "active",
            "current_phase": "executing",
            "workspace_path": str(workspace_path),
            "runtime_dir": str(tmp_path / "runtime" / "tasks" / "1"),
            "pause_state": "none",
        }
    )
    kernel = _KernelStub(
        health_payload={
            "mode": "rust",
            "transport": "grpc-uds",
            "connected": True,
            "ready": True,
            "authoritative": False,
            "production_ready": False,
        },
        pause_result={"forwarded": False, "reason": "runtime-kernel unavailable"},
    )
    controller = _build_controller(monkeypatch, tmp_path, store=store, kernel=kernel)

    ok = await controller.pause_environment(task_id=1, reason="operator requested pause")

    readiness = controller.get_runtime_readiness()
    assert ok is True
    assert readiness["runtime_kernel_operations"]["pause"]["required"] is False
    assert readiness["runtime_kernel_operations"]["pause"]["ok"] is True
    assert not store.warnings


@pytest.mark.asyncio
async def test_pause_environment_prefers_kernel_signal_when_forwarded(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    store = _StoreStub(
        env={
            "id": 17,
            "task_id": 1,
            "status": "active",
            "current_phase": "executing",
            "workspace_path": str(workspace_path),
            "runtime_dir": str(tmp_path / "runtime" / "tasks" / "1"),
            "pause_state": "none",
            "process_pgid": 4242,
        }
    )
    kernel = _KernelStub(
        health_payload={
            "mode": "rust",
            "transport": "grpc-uds",
            "connected": True,
            "ready": True,
            "authoritative": True,
            "production_ready": True,
        },
        pause_result={"forwarded": True, "phase": "paused_for_operator"},
    )
    controller = _build_controller(monkeypatch, tmp_path, store=store, kernel=kernel)
    killpg_calls: list[tuple[int, int]] = []
    monkeypatch.setattr(controller_module.os, "killpg", lambda pgid, sig: killpg_calls.append((pgid, sig)))

    ok = await controller.pause_environment(task_id=1, reason="operator requested pause")

    assert ok is True
    assert killpg_calls == []


@pytest.mark.asyncio
async def test_provision_environment_uses_kernel_workspace_result_when_available(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = _StoreStub()
    kernel_workspace = tmp_path / "kernel-workspace"
    kernel_workspace.mkdir()
    kernel = _KernelStub(
        health_payload={
            "mode": "rust",
            "transport": "grpc-uds",
            "connected": True,
            "ready": True,
            "authoritative": True,
            "production_ready": True,
        },
        create_environment_result={
            "forwarded": True,
            "workspace_path": str(kernel_workspace),
            "branch_name": "task/1-ship-it",
            "created_worktree": True,
            "worktree_mode": "worktree",
            "metadata_path": str(tmp_path / "worktree.json"),
        },
    )
    controller = _build_controller(monkeypatch, tmp_path, store=store, kernel=kernel)
    created_envs: list[dict[str, Any]] = []

    def _create_environment(**kwargs: Any) -> int:
        env = {
            "id": 17,
            "task_id": kwargs["task_id"],
            "status": "active",
            "current_phase": kwargs["current_phase"],
            "workspace_path": kwargs["workspace_path"],
            "runtime_dir": kwargs["runtime_dir"],
            "branch_name": kwargs["branch_name"],
            "created_worktree": kwargs["created_worktree"],
            "worktree_mode": kwargs["worktree_mode"],
        }
        store.env = env
        created_envs.append(env)
        return 17

    store.create_environment = _create_environment  # type: ignore[attr-defined]
    store.update_runtime_queue_item = lambda task_id, *, status, queue_position=None: None  # type: ignore[assignment]
    classification = controller_module.RuntimeClassification(
        classification="standard",
        environment_kind="dev_worktree",
        isolation="worktree",
        duration="ephemeral",
        reasons=["test"],
    )

    env = await controller.provision_environment(
        task_id=1,
        user_id=1,
        chat_id=1,
        query_text="ship it",
        base_work_dir=str(tmp_path),
        classification=classification,
    )

    readiness = controller.get_runtime_readiness()
    assert env is not None
    assert created_envs[0]["workspace_path"] == str(kernel_workspace)
    assert created_envs[0]["branch_name"] == "task/1-ship-it"
    assert created_envs[0]["created_worktree"] is True
    assert readiness["runtime_kernel_operations"]["create_environment"]["ok"] is True


@pytest.mark.asyncio
async def test_provision_environment_records_create_environment_forwarding_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    store = _StoreStub()
    kernel = _KernelStub(
        health_payload={
            "mode": "rust",
            "transport": "grpc-uds",
            "connected": True,
            "ready": True,
            "authoritative": False,
            "production_ready": False,
        },
        create_environment_result={"forwarded": False, "reason": "runtime-kernel unavailable"},
    )
    controller = _build_controller(monkeypatch, tmp_path, store=store, kernel=kernel)
    created_envs: list[dict[str, Any]] = []

    def _create_environment(**kwargs: Any) -> int:
        env = {
            "id": 17,
            "task_id": kwargs["task_id"],
            "status": "active",
            "current_phase": kwargs["current_phase"],
            "workspace_path": kwargs["workspace_path"],
            "runtime_dir": kwargs["runtime_dir"],
        }
        store.env = env
        created_envs.append(env)
        return 17

    store.create_environment = _create_environment  # type: ignore[attr-defined]
    store.update_runtime_queue_item = lambda task_id, *, status, queue_position=None: None  # type: ignore[assignment]
    classification = controller_module.RuntimeClassification(
        classification="standard",
        environment_kind="dev_worktree",
        isolation="worktree",
        duration="ephemeral",
        reasons=["test"],
    )

    with pytest.raises(RuntimeError, match="runtime kernel create_environment required"):
        await controller.provision_environment(
            task_id=1,
            user_id=1,
            chat_id=1,
            query_text="ship it",
            base_work_dir=str(tmp_path),
            classification=classification,
        )

    readiness = controller.get_runtime_readiness()
    assert created_envs == []
    assert readiness["runtime_kernel_operations"]["create_environment"]["required"] is True
    assert readiness["runtime_kernel_operations"]["create_environment"]["ok"] is False
    assert store.warnings[-1]["warning_type"] == "runtime_kernel_create_environment_failed"


@pytest.mark.asyncio
async def test_request_cleanup_prefers_kernel_cleanup_when_available(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    runtime_dir = tmp_path / "runtime" / "tasks" / "1"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    store = _StoreStub(
        env={
            "id": 41,
            "task_id": 1,
            "status": "retained",
            "current_phase": "completed_retained",
            "workspace_path": str(workspace_path),
            "runtime_dir": str(runtime_dir),
            "created_worktree": True,
            "worktree_mode": "worktree",
            "save_verified_at": datetime.now(UTC).isoformat(),
            "browser_scope_id": 1,
        }
    )
    kernel = _KernelStub(
        health_payload={
            "mode": "rust",
            "transport": "grpc-uds",
            "connected": True,
            "ready": True,
            "authoritative": True,
            "production_ready": True,
        },
        cleanup_environment_result={
            "forwarded": True,
            "cleaned": True,
            "workspace_removed": True,
            "runtime_root_removed": True,
            "worktree_mode": "worktree",
        },
    )
    controller = _build_controller(monkeypatch, tmp_path, store=store, kernel=kernel)
    ok = await controller.request_cleanup(task_id=1, force=False)

    readiness = controller.get_runtime_readiness()
    assert ok is True
    assert readiness["runtime_kernel_operations"]["cleanup_environment"]["ok"] is True
    assert store.env is not None
    assert store.env["current_phase"] == "cleaned"


@pytest.mark.asyncio
async def test_request_cleanup_fails_closed_when_rust_requires_kernel_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    runtime_dir = tmp_path / "runtime" / "tasks" / "1"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    store = _StoreStub(
        env={
            "id": 42,
            "task_id": 1,
            "status": "retained",
            "current_phase": "completed_retained",
            "workspace_path": str(workspace_path),
            "runtime_dir": str(runtime_dir),
            "created_worktree": True,
            "worktree_mode": "worktree",
            "save_verified_at": datetime.now(UTC).isoformat(),
            "browser_scope_id": 1,
        }
    )
    kernel = _KernelStub(
        health_payload={
            "mode": "rust",
            "transport": "grpc-uds",
            "connected": True,
            "ready": True,
            "authoritative": False,
            "production_ready": False,
            "authoritative_operations": ["create_environment", "cleanup_environment", "save_checkpoint"],
        },
        cleanup_environment_result={"forwarded": False, "reason": "runtime-kernel unavailable"},
    )
    controller = _build_controller(monkeypatch, tmp_path, store=store, kernel=kernel)

    ok = await controller.request_cleanup(task_id=1, force=False)

    assert ok is False
    assert store.env is not None
    assert store.env["current_phase"] == "completed_retained"
    assert store.env["status"] == "retained"
    assert store.warnings[-1]["warning_type"] == "runtime_kernel_cleanup_environment_failed"


@pytest.mark.asyncio
async def test_request_cleanup_prefers_kernel_terminate_for_primary_process(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    runtime_dir = tmp_path / "runtime" / "tasks" / "1"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    store = _StoreStub(
        env={
            "id": 52,
            "task_id": 1,
            "status": "retained",
            "current_phase": "completed_retained",
            "workspace_path": str(workspace_path),
            "runtime_dir": str(runtime_dir),
            "created_worktree": True,
            "worktree_mode": "worktree",
            "save_verified_at": datetime.now(UTC).isoformat(),
            "browser_scope_id": 1,
            "process_pid": 9001,
            "process_pgid": 9001,
        }
    )
    store.processes.append(
        {
            "id": 77,
            "task_id": 1,
            "env_id": 52,
            "pid": 9001,
            "pgid": 9001,
            "role": "provider",
            "status": "running",
        }
    )
    kernel = _KernelStub(
        health_payload={
            "mode": "rust",
            "transport": "grpc-uds",
            "connected": True,
            "ready": True,
            "authoritative": True,
            "production_ready": True,
        },
        terminate_result={"forwarded": True, "terminated": True, "phase": "cleanup_pending"},
        cleanup_environment_result={
            "forwarded": True,
            "cleaned": True,
            "workspace_removed": True,
            "runtime_root_removed": True,
            "worktree_mode": "worktree",
        },
    )
    controller = _build_controller(monkeypatch, tmp_path, store=store, kernel=kernel)

    ok = await controller.request_cleanup(task_id=1, force=False)

    assert ok is True
    assert store.processes[0]["status"] == "exited"


@pytest.mark.asyncio
async def test_start_browser_runtime_state_prefers_kernel_authority_in_rust_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime_dir = tmp_path / "runtime" / "tasks" / "1"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    store = _StoreStub(
        env={
            "id": 61,
            "task_id": 1,
            "status": "active",
            "current_phase": "executing",
            "workspace_path": str(tmp_path / "workspace"),
            "runtime_dir": str(runtime_dir),
        }
    )
    kernel = _KernelStub(
        health_payload={
            "mode": "rust",
            "transport": "grpc-uds",
            "connected": True,
            "ready": True,
        },
        start_browser_session_result={
            "forwarded": True,
            "started": True,
            "session_id": "browser-session-1",
            "environment_id": "env-61",
            "scope_id": 7,
            "transport": "local_headful",
            "status": "running",
            "runtime_dir": str(runtime_dir / "browser"),
            "display_id": None,
            "vnc_port": None,
            "novnc_port": None,
            "missing_binaries": [],
            "metadata": {},
        },
    )
    controller = _build_controller(monkeypatch, tmp_path, store=store, kernel=kernel)

    session = await controller._start_browser_runtime_state(
        task_id=1,
        env_id=61,
        runtime_dir=str(runtime_dir),
        scope_id=7,
    )

    assert session is not None
    assert session["kernel_session_id"] == "browser-session-1"
    assert store.env is not None
    assert store.env["browser_scope_id"] == 7
    assert store.browser_sessions[-1]["metadata"]["kernel_session_id"] == "browser-session-1"


@pytest.mark.asyncio
async def test_start_browser_runtime_state_does_not_fallback_to_local_browser_live_in_rust_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime_dir = tmp_path / "runtime" / "tasks" / "1"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    store = _StoreStub(
        env={
            "id": 62,
            "task_id": 1,
            "status": "active",
            "current_phase": "executing",
            "workspace_path": str(tmp_path / "workspace"),
            "runtime_dir": str(runtime_dir),
        }
    )
    kernel = _KernelStub(
        health_payload={
            "mode": "rust",
            "transport": "grpc-uds",
            "connected": True,
            "ready": True,
        },
        start_browser_session_result={"forwarded": False, "reason": "runtime-kernel unavailable"},
    )
    controller = _build_controller(monkeypatch, tmp_path, store=store, kernel=kernel)

    session = await controller._start_browser_runtime_state(
        task_id=1,
        env_id=62,
        runtime_dir=str(runtime_dir),
        scope_id=8,
    )

    assert session is not None
    assert session["status"] == "unavailable"
    assert "kernel_error" in session
    assert store.browser_sessions[-1]["status"] == "unavailable"


@pytest.mark.asyncio
async def test_retire_browser_runtime_state_does_not_use_local_stop_in_rust_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime_dir = tmp_path / "runtime" / "tasks" / "1"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    store = _StoreStub(
        env={
            "id": 63,
            "task_id": 1,
            "status": "active",
            "current_phase": "executing",
            "workspace_path": str(tmp_path / "workspace"),
            "runtime_dir": str(runtime_dir),
            "browser_scope_id": 9,
            "browser_transport": "local_headful",
        }
    )
    store.browser_sessions.append(
        {
            "id": 1,
            "task_id": 1,
            "env_id": 63,
            "scope_id": 9,
            "transport": "local_headful",
            "status": "running",
            "display_id": None,
            "vnc_port": None,
            "novnc_port": None,
            "metadata": {},
        }
    )
    kernel = _KernelStub(
        health_payload={
            "mode": "rust",
            "transport": "grpc-uds",
            "connected": True,
            "ready": True,
        },
        stop_browser_session_result={"forwarded": False, "reason": "runtime-kernel unavailable"},
    )
    controller = _build_controller(monkeypatch, tmp_path, store=store, kernel=kernel)

    await controller._retire_browser_runtime_state(task_id=1, env_id=63, scope_id=9)

    assert store.browser_sessions[0]["status"] == "closed"


@pytest.mark.asyncio
async def test_retire_browser_runtime_state_keeps_local_fallback_outside_rust_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime_dir = tmp_path / "runtime" / "tasks" / "1"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    store = _StoreStub(
        env={
            "id": 64,
            "task_id": 1,
            "status": "active",
            "current_phase": "executing",
            "workspace_path": str(tmp_path / "workspace"),
            "runtime_dir": str(runtime_dir),
            "browser_scope_id": 10,
            "browser_transport": "local_headful",
        }
    )
    store.browser_sessions.append(
        {
            "id": 1,
            "task_id": 1,
            "env_id": 64,
            "scope_id": 10,
            "transport": "local_headful",
            "status": "running",
            "display_id": None,
            "vnc_port": None,
            "novnc_port": None,
            "metadata": {},
        }
    )
    kernel = _KernelStub(
        health_payload={
            "mode": "rust",
            "transport": "grpc-uds",
            "connected": True,
            "ready": True,
        },
        stop_browser_session_result={"forwarded": False, "reason": "runtime-kernel unavailable"},
    )
    controller = _build_controller(monkeypatch, tmp_path, store=store, kernel=kernel)

    await controller._retire_browser_runtime_state(task_id=1, env_id=64, scope_id=10)

    readiness = controller.get_runtime_readiness()
    assert store.browser_sessions[0]["status"] == "closed"
    assert readiness["runtime_kernel_operations"]["stop_browser_session"]["required"] is True


@pytest.mark.asyncio
async def test_record_process_records_start_task_forwarding_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    store = _StoreStub(
        env={
            "id": 21,
            "task_id": 1,
            "status": "active",
            "current_phase": "executing",
            "workspace_path": str(workspace_path),
            "runtime_dir": str(tmp_path / "runtime" / "tasks" / "1"),
        }
    )
    kernel = _KernelStub(
        health_payload={
            "mode": "rust",
            "transport": "grpc-uds",
            "connected": True,
            "ready": True,
            "authoritative": True,
            "production_ready": True,
        },
        start_task_result={"forwarded": False, "reason": "runtime-kernel unavailable"},
    )
    controller = _build_controller(monkeypatch, tmp_path, store=store, kernel=kernel)
    store.upsert_process = lambda **kwargs: 31  # type: ignore[attr-defined]
    proc = SimpleNamespace(pid=4242, pgid=4242)

    await controller.record_process(task_id=1, command="python worker.py", proc=proc)

    readiness = controller.get_runtime_readiness()
    assert readiness["runtime_kernel_operations"]["start_task"]["ok"] is False
    assert store.warnings[-1]["warning_type"] == "runtime_kernel_start_task_failed"


@pytest.mark.asyncio
async def test_record_process_surfaces_kernel_process_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    store = _StoreStub(
        env={
            "id": 22,
            "task_id": 1,
            "status": "active",
            "current_phase": "planning",
            "workspace_path": str(workspace_path),
            "runtime_dir": str(tmp_path / "runtime" / "tasks" / "1"),
        }
    )
    kernel = _KernelStub(
        health_payload={
            "mode": "rust",
            "transport": "grpc-uds",
            "connected": True,
            "ready": True,
            "authoritative": True,
            "production_ready": True,
        },
        start_task_result={
            "forwarded": True,
            "process_id": "proc-9",
            "environment_id": "env-1",
            "phase": "kernel_executing",
        },
    )
    controller = _build_controller(monkeypatch, tmp_path, store=store, kernel=kernel)
    store.upsert_process = lambda **kwargs: 32  # type: ignore[attr-defined]
    proc = SimpleNamespace(pid=4343, pgid=4343)

    await controller.record_process(task_id=1, command="python worker.py", proc=proc)

    assert store.task["current_phase"] == "kernel_executing"
    assert store.env is not None
    assert store.env["current_phase"] == "kernel_executing"
    assert store.events[-1]["payload"]["kernel_process_id"] == "proc-9"
    assert store.events[-1]["payload"]["kernel_environment_id"] == "env-1"


@pytest.mark.asyncio
async def test_create_attach_session_records_attach_terminal_forwarding_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    store = _StoreStub(
        env={
            "id": 29,
            "task_id": 1,
            "status": "active",
            "current_phase": "paused_for_operator",
            "workspace_path": str(workspace_path),
            "runtime_dir": str(tmp_path / "runtime" / "tasks" / "1"),
            "pause_state": "paused_for_operator",
        }
    )
    kernel = _KernelStub(
        health_payload={
            "mode": "rust",
            "transport": "grpc-uds",
            "connected": True,
            "ready": True,
            "authoritative": True,
            "production_ready": True,
        },
        attach_terminal_result={"forwarded": False, "reason": "runtime-kernel unavailable"},
    )
    controller = _build_controller(monkeypatch, tmp_path, store=store, kernel=kernel)
    monkeypatch.setattr(store, "create_attach_session", lambda **kwargs: None)
    monkeypatch.setattr(controller_module.secrets, "token_urlsafe", lambda size: "fixed-token")

    session = await controller.create_attach_session(task_id=1, attach_kind="terminal", terminal_id=7, can_write=True)

    readiness = controller.get_runtime_readiness()
    assert session is not None
    assert readiness["runtime_kernel_operations"]["attach_terminal"]["ok"] is False
    assert store.warnings[-1]["warning_type"] == "runtime_kernel_attach_terminal_failed"


@pytest.mark.asyncio
async def test_create_attach_session_surfaces_kernel_session_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    store = _StoreStub(
        env={
            "id": 30,
            "task_id": 1,
            "status": "active",
            "current_phase": "paused_for_operator",
            "workspace_path": str(workspace_path),
            "runtime_dir": str(tmp_path / "runtime" / "tasks" / "1"),
            "pause_state": "paused_for_operator",
        }
    )
    kernel = _KernelStub(
        health_payload={
            "mode": "rust",
            "transport": "grpc-uds",
            "connected": True,
            "ready": True,
            "authoritative": True,
            "production_ready": True,
        },
        attach_terminal_result={"forwarded": True, "session_id": "kernel-session-7", "attached": True},
    )
    controller = _build_controller(monkeypatch, tmp_path, store=store, kernel=kernel)
    monkeypatch.setattr(store, "create_attach_session", lambda **kwargs: 55)
    monkeypatch.setattr(controller_module.secrets, "token_urlsafe", lambda size: "fixed-token")

    session = await controller.create_attach_session(task_id=1, attach_kind="terminal", terminal_id=7, can_write=True)

    assert session is not None
    assert session["attach_session_id"] == 55
    assert session["kernel_session_id"] == "kernel-session-7"
    assert store.events[-1]["payload"]["attach_session_id"] == 55
    assert store.events[-1]["payload"]["kernel_session_id"] == "kernel-session-7"


@pytest.mark.asyncio
async def test_start_operator_terminal_prefers_kernel_authority_in_rust_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    store = _StoreStub(
        env={
            "id": 33,
            "task_id": 1,
            "status": "active",
            "current_phase": "paused_for_operator",
            "workspace_path": str(workspace_path),
            "runtime_dir": str(tmp_path / "runtime" / "tasks" / "1"),
            "pause_state": "paused_for_operator",
        }
    )
    kernel = _KernelStub(
        health_payload={
            "mode": "rust",
            "transport": "grpc-uds",
            "connected": True,
            "ready": True,
            "authoritative_operations": [
                "open_terminal",
                "write_terminal",
                "resize_terminal",
                "close_terminal",
                "stream_terminal_session",
            ],
        },
        open_terminal_result={
            "forwarded": True,
            "opened": True,
            "session_id": "tty-session-1",
            "process_id": "tty-proc-1",
            "pid": 4242,
            "pgid": 4242,
        },
    )
    controller = _build_controller(monkeypatch, tmp_path, store=store, kernel=kernel)

    terminal = await controller.start_operator_terminal(task_id=1, actor="test")

    assert terminal is not None
    assert terminal["kernel_session_id"] == "tty-session-1"
    assert store.terminals[0]["path"] == "kernel://tty-session-1"
    assert store.terminals[0]["stream_path"] == "kernel://tty-session-1"


@pytest.mark.asyncio
async def test_iter_terminal_stream_supports_kernel_primary_streams(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = _StoreStub(
        env={
            "id": 11,
            "task_id": 1,
            "status": "active",
            "current_phase": "executing",
            "workspace_path": str(tmp_path / "workspace"),
            "runtime_dir": str(tmp_path / "runtime" / "tasks" / "1"),
        }
    )
    store.upsert_terminal(
        task_id=1,
        env_id=11,
        terminal_kind="provider_stream",
        label="stdout",
        path=str(tmp_path / "runtime" / "tasks" / "1" / "stdout" / "provider.log"),
        stream_path="kernel-stream://stdout",
    )
    kernel = _KernelStub(
        health_payload={
            "mode": "rust",
            "transport": "grpc-uds",
            "connected": True,
            "ready": True,
            "authoritative": True,
            "production_ready": True,
            "authoritative_operations": ["stream_terminal"],
        }
    )

    async def _stream_terminal(*, task_id: int, stream: str) -> Any:
        assert task_id == 1
        assert stream == "stdout"
        yield b"hello "
        yield b"world"

    kernel.stream_terminal = _stream_terminal  # type: ignore[method-assign]
    controller = _build_controller(monkeypatch, tmp_path, store=store, kernel=kernel)

    payloads = [item async for item in controller.iter_terminal_stream(task_id=1, terminal_id=1)]

    assert payloads == [
        {
            "type": "chunk",
            "terminal_id": 1,
            "offset": len(b"hello "),
            "data": "hello ",
            "stream": "stdout",
        },
        {
            "type": "chunk",
            "terminal_id": 1,
            "offset": len(b"hello world"),
            "data": "world",
            "stream": "stdout",
        },
        {
            "type": "closed",
            "terminal_id": 1,
            "offset": len(b"hello world"),
            "data": "",
            "stream": "stdout",
        },
    ]


@pytest.mark.asyncio
async def test_runtime_controller_rejects_file_backed_terminal_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    terminal_path = tmp_path / "runtime" / "tasks" / "1" / "stdout" / "legacy.log"
    terminal_path.parent.mkdir(parents=True, exist_ok=True)
    terminal_path.write_text("legacy terminal", encoding="utf-8")
    store = _StoreStub(
        env={
            "id": 11,
            "task_id": 1,
            "status": "active",
            "current_phase": "executing",
            "workspace_path": str(workspace_path),
            "runtime_dir": str(tmp_path / "runtime" / "tasks" / "1"),
        }
    )
    store.upsert_terminal(
        task_id=1,
        env_id=11,
        terminal_kind="provider_stream",
        label="legacy",
        path=str(terminal_path),
    )
    kernel = _KernelStub(
        health_payload={
            "mode": "rust",
            "transport": "grpc-uds",
            "connected": True,
            "ready": True,
            "authoritative": True,
            "production_ready": True,
            "authoritative_operations": ["open_terminal", "write_terminal", "stream_terminal_session"],
        }
    )
    controller = _build_controller(monkeypatch, tmp_path, store=store, kernel=kernel)

    with pytest.raises(RuntimeError, match="kernel-backed"):
        await controller.append_terminal_output(task_id=1, terminal_id=1, text="hello")

    with pytest.raises(RuntimeError, match="kernel-backed"):
        stream = controller.iter_terminal_stream(task_id=1, terminal_id=1)
        await anext(stream)


@pytest.mark.asyncio
async def test_record_resource_sample_uses_kernel_snapshot_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    (workspace_path / "payload.txt").write_text("payload", encoding="utf-8")
    store = _StoreStub(
        env={
            "id": 21,
            "task_id": 1,
            "status": "active",
            "current_phase": "executing",
            "workspace_path": str(workspace_path),
            "runtime_dir": str(tmp_path / "runtime" / "tasks" / "1"),
        }
    )
    captured: dict[str, Any] = {}

    def _add_resource_sample(**kwargs: Any) -> int:
        captured.update(kwargs)
        return 99

    store.add_resource_sample = _add_resource_sample  # type: ignore[attr-defined]
    kernel = _KernelStub(
        health_payload={
            "mode": "rust",
            "transport": "grpc-uds",
            "connected": True,
            "ready": True,
            "authoritative": True,
            "production_ready": True,
        },
        collect_snapshot_result={
            "task_id": "1",
            "environment_id": "env-21",
            "task": {"pid": 4242, "process_running": True},
            "interactive_terminals": [{"status": "running", "pid": 4242}],
            "browser_sessions": [],
        },
    )
    controller = _build_controller(monkeypatch, tmp_path, store=store, kernel=kernel)

    sample_id = await controller.record_resource_sample(task_id=1, env_id=21)

    assert sample_id == 99
    assert captured["workspace_disk_bytes"] is None
    assert captured["metadata"]["tracked_pids"] == [4242]
    assert "workspace_disk_bytes" not in captured["metadata"]


@pytest.mark.asyncio
async def test_recover_task_prefers_kernel_cleanup_for_old_workspace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    old_workspace = tmp_path / "workspace-old"
    old_workspace.mkdir()
    new_workspace = tmp_path / "workspace-new"
    new_workspace.mkdir()
    checkpoint_dir = tmp_path / "checkpoints" / "1"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    store = _StoreStub(
        env={
            "id": 41,
            "task_id": 1,
            "status": "retained",
            "current_phase": "recoverable_failed_retained",
            "environment_kind": "dev_worktree",
            "workspace_path": str(old_workspace),
            "runtime_dir": str(tmp_path / "runtime" / "tasks" / "1"),
            "base_work_dir": str(tmp_path),
            "created_worktree": True,
            "worktree_mode": "worktree",
            "revision": 1,
        },
        task={
            "id": 1,
            "task_id": 1,
            "status": "failed",
            "current_phase": "recoverable_failed_retained",
            "query_text": "recover me",
            "work_dir": str(tmp_path),
            "agent_id": "AGENT_A",
        },
    )
    kernel = _KernelStub(
        health_payload={
            "mode": "rust",
            "transport": "grpc-uds",
            "connected": True,
            "ready": True,
            "authoritative": True,
            "production_ready": True,
        },
        cleanup_environment_result={
            "forwarded": True,
            "cleaned": True,
            "workspace_removed": True,
            "runtime_root_removed": True,
            "worktree_mode": "worktree",
        },
        create_environment_result={
            "forwarded": True,
            "workspace_path": str(new_workspace),
            "branch_name": "task/1-recover-r2",
            "created_worktree": True,
            "worktree_mode": "worktree",
            "metadata_path": str(tmp_path / "worktree.json"),
        },
        get_checkpoint_result={"forwarded": True, "checkpoint_id": "kernel-91"},
        restore_checkpoint_result={
            "forwarded": True,
            "found": True,
            "restored": True,
            "workspace_path": str(new_workspace),
            "restored_commit_sha": "abc123",
            "restored_paths": ["git_reset", "git_patch"],
        },
    )
    controller = _build_controller(monkeypatch, tmp_path, store=store, kernel=kernel)

    async def _rehydrate_environment_state(task_id: int, env: dict[str, Any]) -> None:
        return None

    controller._rehydrate_environment_state = _rehydrate_environment_state  # type: ignore[method-assign]
    store.get_latest_checkpoint = lambda task_id: {"id": 91, "checkpoint_dir": str(checkpoint_dir)}  # type: ignore[attr-defined]
    store.add_recovery_action = lambda **kwargs: 1  # type: ignore[attr-defined]
    monkeypatch.setattr(controller, "_has_alive_recorded_processes", lambda **kwargs: False)

    result = await controller.recover_task(task_id=1, actor="test")

    readiness = controller.get_runtime_readiness()
    assert result is not None
    assert result["action"] == "reconstructed"
    assert store.env is not None
    assert store.env["workspace_path"] == str(new_workspace)
    assert readiness["runtime_kernel_operations"]["cleanup_environment"]["ok"] is True


@pytest.mark.asyncio
async def test_recover_task_prefers_kernel_restore_when_rust_requires_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    old_workspace = tmp_path / "workspace-old"
    old_workspace.mkdir()
    new_workspace = tmp_path / "workspace-new"
    new_workspace.mkdir()
    store = _StoreStub(
        env={
            "id": 49,
            "task_id": 1,
            "status": "retained",
            "current_phase": "recoverable_failed_retained",
            "environment_kind": "dev_worktree",
            "workspace_path": str(old_workspace),
            "runtime_dir": str(tmp_path / "runtime" / "tasks" / "1"),
            "base_work_dir": str(tmp_path),
            "created_worktree": True,
            "worktree_mode": "worktree",
            "revision": 1,
        },
        task={
            "id": 1,
            "task_id": 1,
            "status": "failed",
            "current_phase": "recoverable_failed_retained",
            "query_text": "recover me",
            "work_dir": str(tmp_path),
            "agent_id": "AGENT_A",
        },
    )
    kernel = _KernelStub(
        health_payload={
            "mode": "rust",
            "transport": "grpc-uds",
            "connected": True,
            "ready": True,
            "authoritative_operations": [
                "create_environment",
                "cleanup_environment",
                "get_checkpoint",
                "restore_checkpoint",
            ],
        },
        cleanup_environment_result={
            "forwarded": True,
            "cleaned": True,
            "workspace_removed": True,
            "runtime_root_removed": True,
            "worktree_mode": "worktree",
        },
        create_environment_result={
            "forwarded": True,
            "workspace_path": str(new_workspace),
            "branch_name": "task/1-recover-r2",
            "created_worktree": True,
            "worktree_mode": "worktree",
            "metadata_path": str(tmp_path / "worktree.json"),
        },
        get_checkpoint_result={"forwarded": True, "checkpoint_id": "kernel-91"},
        restore_checkpoint_result={
            "forwarded": True,
            "found": True,
            "restored": True,
            "workspace_path": str(new_workspace),
            "restored_commit_sha": "abc123",
            "restored_paths": ["git_reset", "git_patch"],
        },
    )
    controller = _build_controller(monkeypatch, tmp_path, store=store, kernel=kernel)
    store.get_latest_checkpoint = lambda task_id: {"id": 91, "checkpoint_dir": str(tmp_path / "checkpoint")}  # type: ignore[attr-defined]
    store.add_recovery_action = lambda **kwargs: 1  # type: ignore[attr-defined]
    monkeypatch.setattr(controller, "_has_alive_recorded_processes", lambda **kwargs: False)

    result = await controller.recover_task(task_id=1, actor="test")

    assert result is not None
    assert result["action"] == "reconstructed"
    assert store.env is not None
    assert store.env["workspace_path"] == str(new_workspace)


@pytest.mark.asyncio
async def test_recover_task_fails_closed_when_rust_requires_kernel_recreate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    old_workspace = tmp_path / "workspace-old"
    old_workspace.mkdir()
    checkpoint_dir = tmp_path / "checkpoints" / "1"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    store = _StoreStub(
        env={
            "id": 51,
            "task_id": 1,
            "status": "retained",
            "current_phase": "recoverable_failed_retained",
            "environment_kind": "dev_worktree",
            "workspace_path": str(old_workspace),
            "runtime_dir": str(tmp_path / "runtime" / "tasks" / "1"),
            "base_work_dir": str(tmp_path),
            "created_worktree": True,
            "worktree_mode": "worktree",
            "revision": 1,
        },
        task={
            "id": 1,
            "task_id": 1,
            "status": "failed",
            "current_phase": "recoverable_failed_retained",
            "query_text": "recover me",
            "work_dir": str(tmp_path),
            "agent_id": "AGENT_A",
        },
    )
    kernel = _KernelStub(
        health_payload={
            "mode": "rust",
            "transport": "grpc-uds",
            "connected": True,
            "ready": True,
            "authoritative": False,
            "production_ready": False,
            "authoritative_operations": ["create_environment", "cleanup_environment", "save_checkpoint"],
        },
        cleanup_environment_result={
            "forwarded": True,
            "cleaned": True,
            "workspace_removed": True,
            "runtime_root_removed": True,
            "worktree_mode": "worktree",
        },
        create_environment_result={"forwarded": False, "reason": "runtime-kernel unavailable"},
    )
    controller = _build_controller(monkeypatch, tmp_path, store=store, kernel=kernel)
    store.get_latest_checkpoint = lambda task_id: {"id": 91, "checkpoint_dir": str(checkpoint_dir)}  # type: ignore[attr-defined]
    monkeypatch.setattr(controller, "_has_alive_recorded_processes", lambda **kwargs: False)

    with pytest.raises(RuntimeError, match="runtime kernel create_environment required during recovery"):
        await controller.recover_task(task_id=1, actor="test")


@pytest.mark.asyncio
async def test_finalize_task_prefers_kernel_checkpoint_authority_in_rust_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    checkpoint_dir = tmp_path / "runtime" / "tasks" / "1" / "checkpoints" / "kernel-1"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = checkpoint_dir / "manifest.json"
    snapshot_path = checkpoint_dir / "snapshot.json"
    patch_path = checkpoint_dir / "git.patch"
    git_status_path = checkpoint_dir / "git_status.txt"
    manifest_path.write_text('{"ok":true}', encoding="utf-8")
    snapshot_path.write_text('{"task_id":1}', encoding="utf-8")
    patch_path.write_text("", encoding="utf-8")
    git_status_path.write_text("", encoding="utf-8")
    store = _StoreStub(
        env={
            "id": 71,
            "task_id": 1,
            "status": "active",
            "current_phase": "executing",
            "workspace_path": str(workspace_path),
            "runtime_dir": str(tmp_path / "runtime" / "tasks" / "1"),
            "branch_name": "task/1",
        }
    )
    kernel = _KernelStub(
        health_payload={
            "mode": "rust",
            "transport": "grpc-uds",
            "connected": True,
            "ready": True,
            "authoritative_operations": ["save_checkpoint", "get_checkpoint", "restore_checkpoint"],
        },
        save_checkpoint_result={
            "forwarded": True,
            "saved": True,
            "checkpoint_id": "kernel-1",
            "checkpoint_dir": str(checkpoint_dir),
            "manifest_path": str(manifest_path),
            "snapshot_path": str(snapshot_path),
            "patch_path": str(patch_path),
            "git_status_path": str(git_status_path),
            "untracked_bundle_path": "",
            "has_untracked_bundle": False,
            "commit_sha": "abc123",
        },
    )
    controller = _build_controller(monkeypatch, tmp_path, store=store, kernel=kernel)
    result = await controller.finalize_task(task_id=1, success=False, summary={"save_only": True})

    assert result is not None
    assert store.artifacts
    assert {item["artifact_kind"] for item in store.artifacts} >= {"manifest", "patch", "snapshot", "git_status"}
