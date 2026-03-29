"""High-level runtime controller singleton."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import platform
import secrets
import shutil
import subprocess
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from koda.config import (
    AGENT_ID,
    RUNTIME_BROWSER_LIVE_ENABLED,
    RUNTIME_BROWSER_NOVNC_BASE_PORT,
    RUNTIME_BROWSER_TRANSPORT,
    RUNTIME_BROWSER_VNC_BASE_PORT,
    RUNTIME_CLEANUP_SWEEP_INTERVAL_SECONDS,
    RUNTIME_ENVIRONMENTS_ENABLED,
    RUNTIME_HEARTBEAT_INTERVAL_SECONDS,
    RUNTIME_OPERATOR_SESSION_TTL_SECONDS,
    RUNTIME_RECOVERY_ENABLED,
    RUNTIME_RECOVERY_SWEEP_INTERVAL_SECONDS,
    RUNTIME_RESOURCE_SAMPLE_INTERVAL_SECONDS,
    RUNTIME_RETENTION_FAILURE_HOURS,
    RUNTIME_RETENTION_SUCCESS_HOURS,
    RUNTIME_ROOT_DIR,
    RUNTIME_SAVE_VERIFY_TIMEOUT_SECONDS,
    RUNTIME_STALE_AFTER_SECONDS,
    RUNTIME_SUPERVISED_ATTACH_ENABLED,
)
from koda.internal_rpc.artifact_engine import build_artifact_engine_client
from koda.internal_rpc.common import parse_boolish
from koda.internal_rpc.runtime_kernel import build_runtime_kernel_client
from koda.logging_config import get_logger
from koda.services.metrics import (
    RUNTIME_ACTIVE_ENVS,
    RUNTIME_BROWSER_ATTACH_SESSIONS_ACTIVE,
    RUNTIME_BROWSER_SESSIONS_ACTIVE,
    RUNTIME_CHECKPOINT_FAILURES_TOTAL,
    RUNTIME_CLEANUP_BLOCKED_TOTAL,
    RUNTIME_GUARDRAIL_HITS_TOTAL,
    RUNTIME_ORPHAN_ENVS,
    RUNTIME_PAUSE_EVENTS_TOTAL,
    RUNTIME_PHASE_TOTAL,
    RUNTIME_PTYS_ACTIVE,
    RUNTIME_RECOVERIES_TOTAL,
    RUNTIME_RESOURCE_CPU_PERCENT,
    RUNTIME_RESOURCE_RSS_BYTES,
    RUNTIME_RESUME_EVENTS_TOTAL,
    RUNTIME_SAVE_VERIFY_FAILURES_TOTAL,
    RUNTIME_TERMINAL_ATTACH_SESSIONS_ACTIVE,
    RUNTIME_VNC_SESSIONS_ACTIVE,
)
from koda.services.runtime.classifier import RuntimeClassification, classify_task
from koda.services.runtime.events import RuntimeEventBroker
from koda.services.runtime.port_allocator import PortAllocator
from koda.services.runtime.recovery_manager import RecoveryManager
from koda.services.runtime.store import RuntimeStore
from koda.state.history_store import create_task

log = get_logger(__name__)

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


class RuntimeController:
    """Owns runtime state, live events, recovery, and retention."""

    def __init__(self, runtime_root: Path | None = None) -> None:
        self.runtime_root = (runtime_root or RUNTIME_ROOT_DIR).resolve()
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        (self.runtime_root / "tasks").mkdir(parents=True, exist_ok=True)
        self.store = RuntimeStore()
        self.runtime_kernel = build_runtime_kernel_client(runtime_root=self.runtime_root, store=self.store)
        self.artifact_engine = build_artifact_engine_client(agent_id=AGENT_ID)
        self.events = RuntimeEventBroker(self.store, self.runtime_root)
        self.recovery = RecoveryManager(self.store)
        self.port_allocator = PortAllocator(self.store)
        self._recovery_task: asyncio.Task[None] | None = None
        self._cleanup_task: asyncio.Task[None] | None = None
        self._resource_task: asyncio.Task[None] | None = None
        self._attach_reaper_task: asyncio.Task[None] | None = None
        self._reconcile_task: asyncio.Task[None] | None = None
        self._started = False
        self._pause_events: dict[int, asyncio.Event] = {}
        self._resume_phase: dict[int, str] = {}
        self._runtime_kernel_operations: dict[str, dict[str, Any]] = {}
        self._artifact_engine_started = False
        self._artifact_engine_lock = asyncio.Lock()
        self._application: Any | None = None

    async def start(self, app: Any | None = None) -> None:
        """Start background sweeps."""
        if self._started or not RUNTIME_ENVIRONMENTS_ENABLED:
            return
        await self.runtime_kernel.start()
        await self._ensure_artifact_engine_started()
        self._started = True
        self._application = app
        if RUNTIME_RECOVERY_ENABLED:
            await self.run_recovery_sweep()
        await self.rehydrate_live_environments()
        if RUNTIME_RECOVERY_ENABLED:
            self._recovery_task = asyncio.create_task(self._recovery_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self._resource_task = asyncio.create_task(self._resource_loop())
        self._attach_reaper_task = asyncio.create_task(self._attach_reaper_loop())
        self._reconcile_task = asyncio.create_task(self._reconcile_loop())

    async def stop(self) -> None:
        """Stop background sweeps and close live sessions."""
        for task in (
            self._recovery_task,
            self._cleanup_task,
            self._resource_task,
            self._attach_reaper_task,
            self._reconcile_task,
        ):
            if task:
                task.cancel()
        self._recovery_task = None
        self._cleanup_task = None
        self._resource_task = None
        self._attach_reaper_task = None
        self._reconcile_task = None
        for env in self.store.list_environments():
            if str(env.get("status")) == "active" and env.get("workspace_path") and not env.get("save_verified_at"):
                with contextlib.suppress(Exception):
                    await self.finalize_task(
                        task_id=int(env["task_id"]),
                        success=False,
                        error_message="runtime shutdown retention",
                        final_phase="recoverable_failed_retained",
                    )
            for terminal in self.store.list_terminals(int(env["task_id"])):
                if self._terminal_is_kernel_backed(terminal):
                    with contextlib.suppress(Exception):
                        await self.close_terminal_session(
                            task_id=int(env["task_id"]),
                            terminal_id=int(terminal["id"]),
                            force=True,
                        )
            scope_id = int(env.get("browser_scope_id") or env["task_id"])
            with contextlib.suppress(Exception):
                await self.runtime_kernel.stop_browser_session(
                    task_id=int(env["task_id"]),
                    scope_id=scope_id,
                    force=True,
                )
        with contextlib.suppress(Exception):
            await self.artifact_engine.stop()
        self._artifact_engine_started = False
        await self.runtime_kernel.stop()
        self._started = False

    async def _ensure_artifact_engine_started(self) -> bool:
        if self._artifact_engine_started:
            return True
        async with self._artifact_engine_lock:
            if self._artifact_engine_started:
                return True
            try:
                await self.artifact_engine.start()
            except Exception:
                log.exception("runtime_artifact_engine_start_error")
                return False
            self._artifact_engine_started = True
            return True

    async def _recovery_loop(self) -> None:
        while True:
            await asyncio.sleep(RUNTIME_RECOVERY_SWEEP_INTERVAL_SECONDS)
            try:
                await self.run_recovery_sweep()
            except Exception:
                log.exception("recovery_sweep_failed")

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(RUNTIME_CLEANUP_SWEEP_INTERVAL_SECONDS)
            try:
                await self.cleanup_expired()
            except Exception:
                log.exception("cleanup_sweep_failed")

    async def _resource_loop(self) -> None:
        while True:
            await asyncio.sleep(RUNTIME_RESOURCE_SAMPLE_INTERVAL_SECONDS)
            try:
                for env in self.store.list_environments():
                    if not self._should_sample_environment(env):
                        continue
                    sample_id = await self.record_resource_sample(task_id=int(env["task_id"]), env_id=int(env["id"]))
                    await self.events.publish(
                        task_id=int(env["task_id"]),
                        env_id=int(env["id"]),
                        attempt=None,
                        phase=str(env.get("current_phase") or ""),
                        event_type="resource.sampled",
                        payload={"sample_id": sample_id, "source": "resource_loop"},
                        resource_snapshot_ref=str(sample_id),
                    )
            except Exception:
                log.exception("resource_sample_failed")

    async def _attach_reaper_loop(self) -> None:
        while True:
            await asyncio.sleep(max(15, min(RUNTIME_OPERATOR_SESSION_TTL_SECONDS, 60)))
            try:
                for session in self.store.list_expired_attach_sessions():
                    await self.close_attach_session(token=str(session["token"]))
            except Exception:
                log.exception("attach_reaper_failed")

    async def _reconcile_loop(self) -> None:
        while True:
            await asyncio.sleep(max(15, min(RUNTIME_RESOURCE_SAMPLE_INTERVAL_SECONDS, 60)))
            try:
                await self.reconcile_runtime_state()
            except Exception:
                log.exception("reconcile_sweep_failed")

    def _task_runtime_dir(self, task_id: int) -> Path:
        path = self.runtime_root / "tasks" / str(task_id)
        path.mkdir(parents=True, exist_ok=True)
        for child in ("stdout", "stderr", "artifacts", "browser", "checkpoints"):
            (path / child).mkdir(parents=True, exist_ok=True)
        return path

    def _remove_task_runtime_dir(self, task_id: int) -> bool:
        path = self.runtime_root / "tasks" / str(task_id)
        if not path.exists():
            return False
        shutil.rmtree(path, ignore_errors=True)
        return not path.exists()

    def _slugify(self, text: str) -> str:
        cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in text[:60])
        return "-".join(part for part in cleaned.split("-") if part) or "task"

    def _process_group_id_for_proc(self, proc: Any) -> int | None:
        explicit_pgid = getattr(proc, "pgid", None)
        if isinstance(explicit_pgid, int) and explicit_pgid > 0:
            return explicit_pgid
        pid = getattr(proc, "pid", None)
        if not isinstance(pid, int) or pid <= 0:
            return None
        with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
            return os.getpgid(pid)
        return None

    def _snapshot_task_payload(self, snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
        payload = snapshot.get("task") if isinstance(snapshot, Mapping) else None
        return cast(dict[str, Any], payload) if isinstance(payload, dict) else {}

    def _snapshot_running_browser_sessions(self, snapshot: Mapping[str, Any] | None) -> list[dict[str, Any]]:
        payload = snapshot.get("browser_sessions") if isinstance(snapshot, Mapping) else None
        if not isinstance(payload, list):
            return []
        sessions: list[dict[str, Any]] = []
        for item in payload:
            if isinstance(item, dict) and str(item.get("status") or "") in {"running", "pending"}:
                sessions.append(cast(dict[str, Any], item))
        return sessions

    def _snapshot_running_interactive_terminals(self, snapshot: Mapping[str, Any] | None) -> list[dict[str, Any]]:
        payload = snapshot.get("interactive_terminals") if isinstance(snapshot, Mapping) else None
        if not isinstance(payload, list):
            return []
        sessions: list[dict[str, Any]] = []
        for item in payload:
            if isinstance(item, dict) and str(item.get("status") or "") not in {"closed", "exited"}:
                sessions.append(cast(dict[str, Any], item))
        return sessions

    def _snapshot_tracked_pids(self, snapshot: Mapping[str, Any] | None) -> list[int]:
        tracked: set[int] = set()
        task_payload = self._snapshot_task_payload(snapshot)
        pid = task_payload.get("pid")
        if isinstance(pid, int) and pid > 0:
            tracked.add(pid)
        for terminal in self._snapshot_running_interactive_terminals(snapshot):
            terminal_pid = terminal.get("pid")
            if isinstance(terminal_pid, int) and terminal_pid > 0:
                tracked.add(terminal_pid)
        for session in self._snapshot_running_browser_sessions(snapshot):
            metadata = session.get("metadata")
            if not isinstance(metadata, dict):
                continue
            for key in ("xvfb_pid", "openbox_pid", "x11vnc_pid", "websockify_pid"):
                raw_value = metadata.get(key)
                if raw_value is None:
                    continue
                try:
                    candidate = int(raw_value)
                except (TypeError, ValueError):
                    continue
                if candidate > 0:
                    tracked.add(candidate)
        return sorted(tracked)

    async def _kernel_activity_snapshot(self, *, task_id: int) -> dict[str, Any] | None:
        return await self.get_runtime_kernel_snapshot(task_id=task_id)

    async def _kernel_reports_process_running(self, *, task_id: int) -> bool:
        snapshot = await self._kernel_activity_snapshot(task_id=task_id)
        if not snapshot:
            return False
        task_payload = self._snapshot_task_payload(snapshot)
        if bool(task_payload.get("process_running")):
            return True
        if self._snapshot_running_interactive_terminals(snapshot):
            return True
        return bool(self._snapshot_running_browser_sessions(snapshot))

    def _ensure_pause_event(self, task_id: int) -> asyncio.Event:
        event = self._pause_events.get(task_id)
        if event is None:
            event = asyncio.Event()
            event.set()
            self._pause_events[task_id] = event
        return event

    def _sync_pause_event(self, *, task_id: int, pause_state: str) -> None:
        event = self._ensure_pause_event(task_id)
        if pause_state in {"pause_requested", "paused_for_operator", "operator_attached"}:
            event.clear()
        else:
            event.set()

    def _has_alive_recorded_processes(self, *, task_id: int, env_id: int) -> bool:
        return any(
            str(process_row.get("status") or "") != "exited"
            for process_row in self.store.list_processes(task_id, env_id=env_id)
        )

    def get_runtime_kernel_health(self) -> dict[str, Any]:
        """Return a normalized kernel health payload for the gRPC migration seam."""
        raw = cast(dict[str, Any], self.runtime_kernel.health() or {})
        mode = str(raw.get("mode") or "unknown")
        rust_mode = mode == "rust"
        transport = str(raw.get("transport") or "unknown")
        remote = transport not in {"in-process", "python"}
        connected = bool(raw.get("connected", False)) or not remote
        ready = bool(raw.get("ready", False)) and connected
        details = dict(cast(dict[str, Any], raw.get("details") or {}))
        authoritative = parse_boolish(
            raw.get("authoritative", details.get("authoritative")),
            default=ready and (rust_mode or not remote),
        )
        production_ready = parse_boolish(
            raw.get("production_ready", details.get("production_ready")),
            default=ready and authoritative,
        )
        authority_scope = str(
            raw.get("authority_scope")
            or details.get("authority_scope")
            or ("full_runtime" if authoritative else "unavailable")
        )
        blockers_value = raw.get("cutover_blockers", details.get("cutover_blockers"))
        if isinstance(blockers_value, str):
            cutover_blockers = [item.strip() for item in blockers_value.split(",") if item.strip()]
        elif isinstance(blockers_value, (list, tuple, set)):
            cutover_blockers = [str(item).strip() for item in blockers_value if str(item).strip()]
        else:
            cutover_blockers = []
        capabilities_value = raw.get("capabilities", details.get("capabilities"))
        if isinstance(capabilities_value, str):
            capabilities = [item.strip() for item in capabilities_value.split(",") if item.strip()]
        elif isinstance(capabilities_value, (list, tuple, set)):
            capabilities = [str(item).strip() for item in capabilities_value if str(item).strip()]
        else:
            capabilities = []
        if rust_mode and not capabilities:
            capabilities = list(_RUNTIME_KERNEL_CAPABILITY_DEFAULTS)
        authoritative_ops_value = raw.get("authoritative_operations", details.get("authoritative_operations"))
        if isinstance(authoritative_ops_value, str):
            authoritative_operations = [item.strip() for item in authoritative_ops_value.split(",") if item.strip()]
        elif isinstance(authoritative_ops_value, (list, tuple, set)):
            authoritative_operations = [str(item).strip() for item in authoritative_ops_value if str(item).strip()]
        else:
            authoritative_operations = []
        if rust_mode and not authoritative_operations:
            authoritative_operations = list(_RUNTIME_KERNEL_AUTHORITATIVE_OPERATION_DEFAULTS)
        full_authority = parse_boolish(
            raw.get("full_authority", details.get("full_authority")),
            default=authoritative and rust_mode,
        )
        partial_authority = parse_boolish(
            raw.get("partial_authority", details.get("partial_authority")),
            default=False,
        )
        cutover_state = "remote" if remote else "in_process"
        if remote and not connected:
            cutover_state = "remote_disconnected"
        elif remote and not bool(raw.get("ready", False)):
            cutover_state = "remote_unready"
        elif remote and ready and authoritative:
            cutover_state = "remote_authoritative"
        return {
            **raw,
            "mode": mode,
            "transport": transport,
            "remote": remote,
            "connected": connected,
            "ready": ready,
            "details": details,
            "authoritative": authoritative,
            "production_ready": production_ready,
            "cutover_allowed": ready and authoritative and production_ready,
            "authority_scope": authority_scope,
            "cutover_blockers": cutover_blockers,
            "capabilities": capabilities,
            "authoritative_operations": authoritative_operations,
            "full_authority": full_authority,
            "partial_authority": partial_authority,
            "cutover_state": cutover_state,
            "forwarding_expected": remote,
            "forwarding_active": remote and ready,
            "forwarding_authoritative": remote and ready and authoritative,
        }

    def get_artifact_engine_health(self) -> dict[str, Any]:
        """Return the artifact-engine health payload used for runtime artifact ingestion."""
        raw = cast(dict[str, Any], self.artifact_engine.health() or {})
        transport = str(raw.get("transport") or "unknown")
        remote = transport not in {"in-process", "python"}
        connected = bool(raw.get("connected", False)) or not remote
        ready = bool(raw.get("ready", False)) and connected
        return {
            **raw,
            "transport": transport,
            "remote": remote,
            "connected": connected,
            "ready": ready,
        }

    def _runtime_kernel_cutover_payload(self, runtime_kernel: dict[str, Any]) -> dict[str, Any]:
        return {
            "mode": str(runtime_kernel.get("mode") or "unknown"),
            "transport": str(runtime_kernel.get("transport") or "unknown"),
            "state": str(runtime_kernel.get("cutover_state") or "unknown"),
            "remote": bool(runtime_kernel.get("remote", False)),
            "forwarding_expected": bool(runtime_kernel.get("forwarding_expected", False)),
            "forwarding_active": bool(runtime_kernel.get("forwarding_active", False)),
            "forwarding_authoritative": bool(runtime_kernel.get("forwarding_authoritative", False)),
            "connected": bool(runtime_kernel.get("connected", False)),
            "verified": bool(runtime_kernel.get("verified", False)),
            "authoritative": bool(runtime_kernel.get("authoritative", False)),
            "production_ready": bool(runtime_kernel.get("production_ready", False)),
            "cutover_allowed": bool(runtime_kernel.get("cutover_allowed", False)),
            "configured_target": runtime_kernel.get("configured_target"),
            "selection_reason": runtime_kernel.get("selection_reason"),
            "service": runtime_kernel.get("service"),
            "maturity": runtime_kernel.get("maturity"),
            "authority_scope": runtime_kernel.get("authority_scope"),
            "cutover_blockers": list(runtime_kernel.get("cutover_blockers") or []),
            "capabilities": list(runtime_kernel.get("capabilities") or []),
            "authoritative_operations": list(runtime_kernel.get("authoritative_operations") or []),
            "full_authority": bool(runtime_kernel.get("full_authority", False)),
            "partial_authority": bool(runtime_kernel.get("partial_authority", False)),
        }

    def _runtime_kernel_operation_required(self, operation: str, runtime_kernel: Mapping[str, Any]) -> bool:
        if bool(runtime_kernel.get("forwarding_authoritative", False)):
            return True
        if str(runtime_kernel.get("mode") or "").strip().lower() != "rust":
            return False
        authoritative_operations = {
            str(item).strip() for item in runtime_kernel.get("authoritative_operations") or [] if str(item).strip()
        }
        if not authoritative_operations:
            authoritative_operations = set(_RUNTIME_KERNEL_AUTHORITATIVE_OPERATION_DEFAULTS)
        return operation in authoritative_operations

    def _runtime_kernel_browser_authoritative(self, runtime_kernel: Mapping[str, Any] | None = None) -> bool:
        payload = runtime_kernel or self.get_runtime_kernel_health()
        return any(
            self._runtime_kernel_operation_required(operation, payload)
            for operation in ("start_browser_session", "stop_browser_session", "get_browser_session")
        )

    def _runtime_kernel_terminal_authoritative(self, runtime_kernel: Mapping[str, Any] | None = None) -> bool:
        payload = runtime_kernel or self.get_runtime_kernel_health()
        if str(payload.get("mode") or "").strip().lower() != "rust":
            return False
        authoritative_operations = {
            str(item).strip() for item in payload.get("authoritative_operations") or [] if str(item).strip()
        }
        if not authoritative_operations:
            authoritative_operations = set(_RUNTIME_KERNEL_AUTHORITATIVE_OPERATION_DEFAULTS)
        return any(
            operation in authoritative_operations
            for operation in (
                "open_terminal",
                "write_terminal",
                "resize_terminal",
                "close_terminal",
                "stream_terminal_session",
            )
        )

    def _runtime_kernel_checkpoint_restore_authoritative(
        self,
        runtime_kernel: Mapping[str, Any] | None = None,
    ) -> bool:
        payload = runtime_kernel or self.get_runtime_kernel_health()
        if str(payload.get("mode") or "").strip().lower() != "rust":
            return False
        authoritative_operations = {
            str(item).strip() for item in payload.get("authoritative_operations") or [] if str(item).strip()
        }
        if not authoritative_operations:
            authoritative_operations = set(_RUNTIME_KERNEL_AUTHORITATIVE_OPERATION_DEFAULTS)
        checkpoint_ops = {"save_checkpoint", "get_checkpoint", "restore_checkpoint"}
        return any(operation in authoritative_operations for operation in checkpoint_ops)

    def _terminal_kernel_session_id(self, terminal: Mapping[str, Any] | None) -> str:
        if not isinstance(terminal, Mapping):
            return ""
        stream_path = str(terminal.get("stream_path") or "").strip()
        if stream_path.startswith("kernel://"):
            return stream_path.removeprefix("kernel://").strip()
        path = str(terminal.get("path") or "").strip()
        if path.startswith("kernel://"):
            return path.removeprefix("kernel://").strip()
        return ""

    def _terminal_kernel_stream_name(self, terminal: Mapping[str, Any] | None) -> str:
        if not isinstance(terminal, Mapping):
            return ""
        stream_path = str(terminal.get("stream_path") or "").strip()
        if stream_path.startswith("kernel-stream://"):
            return stream_path.removeprefix("kernel-stream://").strip().lower()
        path = str(terminal.get("path") or "").strip()
        if path.startswith("kernel-stream://"):
            return path.removeprefix("kernel-stream://").strip().lower()
        return ""

    def _terminal_is_kernel_backed(self, terminal: Mapping[str, Any] | None) -> bool:
        return bool(self._terminal_kernel_session_id(terminal) or self._terminal_kernel_stream_name(terminal))

    def _resolve_workspace_target(self, workspace_path: str, relative_path: str = "") -> Path:
        root = Path(workspace_path).resolve()
        target = (root / relative_path).resolve()
        if target != root and root not in target.parents:
            raise ValueError("path escapes workspace")
        return target

    def _list_workspace_tree(
        self,
        workspace_path: str,
        *,
        relative_path: str = "",
        max_entries: int = 500,
    ) -> list[dict[str, object]]:
        base = self._resolve_workspace_target(workspace_path, relative_path)
        if not base.exists():
            return []
        entries: list[dict[str, object]] = []
        for child in sorted(base.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))[:max_entries]:
            rel = child.relative_to(Path(workspace_path).resolve())
            entries.append(
                {
                    "name": child.name,
                    "path": str(rel),
                    "is_dir": child.is_dir(),
                    "size": child.stat().st_size if child.is_file() else None,
                }
            )
        return entries

    def _read_workspace_file_payload(
        self,
        workspace_path: str,
        *,
        relative_path: str,
        max_chars: int = 200_000,
    ) -> dict[str, object]:
        path = self._resolve_workspace_target(workspace_path, relative_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(relative_path)
        content = path.read_text(encoding="utf-8", errors="ignore")
        truncated = False
        if len(content) > max_chars:
            content = content[:max_chars]
            truncated = True
        return {"path": relative_path, "content": content, "truncated": truncated}

    def _workspace_git_status(self, workspace_path: str) -> dict[str, object]:
        root = Path(workspace_path).resolve()
        result = subprocess.run(
            ["git", "-C", str(root), "status", "--short", "--branch"],
            capture_output=True,
            text=True,
            check=False,
        )
        return {"ok": result.returncode == 0, "text": result.stdout.strip() or result.stderr.strip()}

    def _workspace_git_diff(
        self,
        workspace_path: str,
        *,
        relative_path: str | None = None,
        max_chars: int = 200_000,
    ) -> dict[str, object]:
        root = Path(workspace_path).resolve()
        cmd = ["git", "-C", str(root), "diff", "--no-ext-diff", "--binary"]
        if relative_path:
            cmd.extend(["--", relative_path])
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        text = result.stdout.strip() or result.stderr.strip()
        truncated = False
        if len(text) > max_chars:
            text = text[:max_chars]
            truncated = True
        return {"ok": result.returncode == 0, "text": text, "truncated": truncated}

    def _get_terminal_row(self, *, task_id: int, terminal_id: int) -> dict[str, Any] | None:
        return next(
            (item for item in self.store.list_terminals(task_id) if int(item["id"]) == terminal_id),
            None,
        )

    def _kernel_checkpoint_id(self, checkpoint: Mapping[str, Any] | None) -> str:
        metadata = cast(dict[str, Any], (checkpoint or {}).get("metadata") or {})
        runtime_kernel_checkpoint = cast(dict[str, Any], metadata.get("runtime_kernel_checkpoint") or {})
        return str(runtime_kernel_checkpoint.get("checkpoint_id") or "").strip()

    def _runtime_kernel_operations_snapshot(self) -> dict[str, dict[str, Any]]:
        return {name: dict(payload) for name, payload in self._runtime_kernel_operations.items()}

    def _runtime_kernel_operation_succeeded(self, operation: str, payload: Mapping[str, Any]) -> bool:
        if "error" in payload:
            return False
        if not bool(payload.get("required", False)):
            return True
        if not bool(payload.get("forwarded", False)):
            return False
        if operation == "create_environment":
            return bool(str(payload.get("workspace_path") or "").strip())
        if operation == "attach_terminal":
            return bool(payload.get("attached", False)) and bool(str(payload.get("session_id") or "").strip())
        if operation == "open_terminal":
            return bool(payload.get("opened", False)) and bool(str(payload.get("session_id") or "").strip())
        if operation == "write_terminal":
            return bool(payload.get("accepted", False))
        if operation == "resize_terminal":
            return bool(payload.get("resized", False))
        if operation == "close_terminal":
            return bool(payload.get("closed", False))
        if operation == "stream_terminal_session":
            return True
        if operation == "cleanup_environment":
            return bool(payload.get("cleaned", False))
        if operation == "start_browser_session":
            return bool(payload.get("started", False)) and bool(str(payload.get("session_id") or "").strip())
        if operation == "stop_browser_session":
            return bool(payload.get("stopped", False))
        if operation == "get_browser_session":
            return bool(str(payload.get("session_id") or "").strip())
        if operation == "save_checkpoint":
            return bool(payload.get("saved", False)) and bool(str(payload.get("checkpoint_id") or "").strip())
        if operation == "get_checkpoint":
            return bool(str(payload.get("checkpoint_id") or "").strip())
        if operation == "restore_checkpoint":
            return bool(payload.get("restored", False))
        return True

    def _record_runtime_kernel_operation(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        entry = {
            "operation": operation,
            "recorded_at": datetime.now(UTC).isoformat(),
            **payload,
        }
        self._runtime_kernel_operations[operation] = entry
        return dict(entry)

    async def _forward_runtime_kernel_operation(
        self,
        *,
        operation: str,
        task_id: int | None,
        env_id: int | None,
        phase: str | None,
        warn_on_failure: bool,
        call: Callable[[], Awaitable[dict[str, object] | None]],
    ) -> dict[str, Any]:
        runtime_kernel = self.get_runtime_kernel_health()
        cutover = self._runtime_kernel_cutover_payload(runtime_kernel)
        required = self._runtime_kernel_operation_required(operation, runtime_kernel)
        payload: dict[str, Any] = {
            "required": required,
            "runtime_kernel": runtime_kernel,
            "cutover": cutover,
            "forwarded": False,
        }
        try:
            result = cast(dict[str, Any], await call() or {})
            payload.update(result)
        except Exception as exc:
            log.exception("runtime_kernel_operation_failed", operation=operation, task_id=task_id)
            payload["error"] = f"{type(exc).__name__}: {exc}"
        ok = self._runtime_kernel_operation_succeeded(operation, payload)
        payload["ok"] = ok
        recorded = self._record_runtime_kernel_operation(operation, payload)
        if task_id is not None:
            severity = "warning" if recorded["required"] and not recorded["ok"] else "info"
            await self.events.publish(
                task_id=task_id,
                env_id=env_id,
                attempt=None,
                phase=phase,
                event_type=f"runtime_kernel.{operation}",
                severity=severity,
                payload=recorded,
            )
            if warn_on_failure and recorded["required"] and not recorded["ok"]:
                message = str(recorded.get("reason") or recorded.get("error") or "runtime kernel forwarding failed")
                await self.record_warning(
                    task_id=task_id,
                    warning_type=f"runtime_kernel_{operation}_failed",
                    message=message,
                    details=recorded,
                )
        return recorded

    def _build_runtime_readiness(self, *, runtime_kernel: dict[str, Any] | None = None) -> dict[str, Any]:
        runtime_kernel = dict(runtime_kernel or self.get_runtime_kernel_health())
        artifact_engine = self.get_artifact_engine_health()
        runtime_kernel_cutover = self._runtime_kernel_cutover_payload(runtime_kernel)
        runtime_kernel_ready = bool(runtime_kernel.get("ready", False))
        browser_authoritative = self._runtime_kernel_browser_authoritative(runtime_kernel)

        runtime_root_exists = self.runtime_root.exists()
        runtime_root_is_dir = self.runtime_root.is_dir() if runtime_root_exists else False
        runtime_root_writable = runtime_root_is_dir and os.access(self.runtime_root, os.W_OK | os.X_OK)
        runtime_root_ready = runtime_root_is_dir and runtime_root_writable
        runtime_root_error: str | None = None
        if not runtime_root_exists:
            runtime_root_error = "runtime_root_missing"
        elif not runtime_root_is_dir:
            runtime_root_error = "runtime_root_not_directory"
        elif not runtime_root_writable:
            runtime_root_error = "runtime_root_not_writable"

        git_available = shutil.which("git") is not None
        browser_transport = str(RUNTIME_BROWSER_TRANSPORT or "").strip().lower()
        browser_live_ready = bool(RUNTIME_BROWSER_LIVE_ENABLED and runtime_kernel_ready and browser_authoritative)
        suggested_actions: list[str] = []
        if not browser_authoritative:
            suggested_actions.append("Runtime kernel browser operations are not authoritative.")

        supervision_loops: dict[str, dict[str, Any]] = {
            "cleanup": {"running": bool(self._cleanup_task and not self._cleanup_task.done()), "critical": True},
            "resource": {"running": bool(self._resource_task and not self._resource_task.done()), "critical": True},
            "attach_reaper": {
                "running": bool(self._attach_reaper_task and not self._attach_reaper_task.done()),
                "critical": True,
            },
            "reconcile": {"running": bool(self._reconcile_task and not self._reconcile_task.done()), "critical": True},
        }
        if RUNTIME_RECOVERY_ENABLED:
            supervision_loops["recovery"] = {
                "running": bool(self._recovery_task and not self._recovery_task.done()),
                "critical": True,
            }
        supervision_degraded = [
            name
            for name, item in supervision_loops.items()
            if self._started and item["critical"] and not item["running"]
        ]
        supervision_ready = not supervision_degraded

        ready = (
            runtime_root_ready
            and git_available
            and (not RUNTIME_BROWSER_LIVE_ENABLED or browser_live_ready)
            and supervision_ready
            and runtime_kernel_ready
        )
        reasons: list[str] = []
        if not runtime_root_ready:
            reasons.append(runtime_root_error or "runtime_root_unavailable")
        if not git_available:
            reasons.append("git_unavailable")
        if RUNTIME_BROWSER_LIVE_ENABLED and not browser_live_ready:
            reasons.append("browser_live_unavailable")
        if not supervision_ready:
            reasons.append("runtime_loop_supervision_unavailable")
        if not runtime_kernel_ready:
            reasons.append("runtime_kernel_unavailable")

        return {
            "ready": ready,
            "reasons": reasons,
            "runtime_kernel": runtime_kernel,
            "artifact_engine": artifact_engine,
            "internal_rpc": runtime_kernel,
            "runtime_kernel_cutover": runtime_kernel_cutover,
            "runtime_kernel_operations": self._runtime_kernel_operations_snapshot(),
            "runtime_root": {
                "path": str(self.runtime_root),
                "exists": runtime_root_exists,
                "is_dir": runtime_root_is_dir,
                "writable": runtime_root_writable,
                "ready": runtime_root_ready,
                "error": runtime_root_error,
            },
            "platform": platform.system().lower(),
            "git": {"available": git_available, "path": shutil.which("git")},
            "browser_live": {
                "enabled": RUNTIME_BROWSER_LIVE_ENABLED,
                "configured_transport": RUNTIME_BROWSER_TRANSPORT,
                "effective_transport": browser_transport,
                "authoritative": browser_authoritative,
                "ready": browser_live_ready,
                "suggested_actions": suggested_actions,
            },
            "supervision": {
                "started": self._started,
                "ready": supervision_ready,
                "degraded_loops": supervision_degraded,
                "loops": supervision_loops,
            },
        }

    def _should_sample_environment(self, env: dict[str, Any]) -> bool:
        status = str(env.get("status") or "")
        if status in {"active", "cleaning"}:
            return True
        if status != "retained":
            return False
        task_id = int(env["task_id"])
        env_id = int(env["id"])
        if self._has_alive_recorded_processes(task_id=task_id, env_id=env_id):
            return True
        if any(str(item.get("status")) == "active" for item in self.store.list_attach_sessions(task_id)):
            return True
        return any(
            str(item.get("status")) == "active" and int(item.get("env_id") or 0) == env_id
            for item in self.store.list_browser_sessions(task_id)
        )

    async def rehydrate_live_environments(self) -> None:
        for env in self.store.list_environments():
            if str(env.get("status")) in {"cleaned", "cleaning"}:
                continue
            await self._rehydrate_environment_state(int(env["task_id"]), env)

    def _resolve_lineage_root_env_id(self, parent_env_id: int | None) -> int | None:
        if parent_env_id is None:
            return None
        parent_env = self.store.get_environment(parent_env_id)
        if parent_env is None:
            return parent_env_id
        lineage_root = parent_env.get("lineage_root_env_id")
        return int(lineage_root) if lineage_root else parent_env_id

    async def register_queued_task(self, *, task_id: int, user_id: int, chat_id: int, query_text: str) -> None:
        if not RUNTIME_ENVIRONMENTS_ENABLED:
            return
        self.store.upsert_runtime_queue_item(task_id=task_id, user_id=user_id, chat_id=chat_id, query_text=query_text)
        self._ensure_pause_event(task_id)
        await self.events.publish(
            task_id=task_id,
            env_id=None,
            attempt=1,
            phase="queued",
            event_type="task.created",
            payload={"query_text": query_text[:400]},
        )

    async def classify_task(
        self,
        *,
        task_id: int,
        query_text: str,
        override: str | None = None,
    ) -> RuntimeClassification:
        classification = classify_task(query_text, override=override)
        self.store.update_task_runtime(task_id, phase="classified")
        await self.events.publish(
            task_id=task_id,
            env_id=None,
            attempt=1,
            phase="classified",
            event_type="task.classified",
            payload=classification.to_dict(),
        )
        return classification

    async def provision_environment(
        self,
        *,
        task_id: int,
        user_id: int,
        chat_id: int,
        query_text: str,
        base_work_dir: str,
        classification: RuntimeClassification,
        parent_env_id: int | None = None,
        source_checkpoint_id: int | None = None,
        recovery_state: str = "",
        revision: int = 1,
        activate_live_resources: bool = True,
    ) -> dict[str, Any] | None:
        if not RUNTIME_ENVIRONMENTS_ENABLED or classification.classification == "light":
            self.store.update_runtime_queue_item(task_id, status="running")
            return None
        runtime_dir = self._task_runtime_dir(task_id)
        await self.events.publish(
            task_id=task_id,
            env_id=None,
            attempt=1,
            phase="provisioning",
            event_type="env.provisioning.started",
            payload={"base_work_dir": base_work_dir, "classification": asdict(classification)},
        )
        runtime_task = cast(dict[str, Any] | None, self.store.get_task_runtime(task_id))
        runtime_agent_id = str((runtime_task or {}).get("agent_id") or AGENT_ID or "").strip()
        create_worktree = classification.classification in {"standard", "heavy"}
        slug = self._slugify(query_text)
        create_result = await self._forward_runtime_kernel_operation(
            operation="create_environment",
            task_id=task_id,
            env_id=None,
            phase="provisioning",
            warn_on_failure=True,
            call=lambda: self.runtime_kernel.create_environment(
                task_id=task_id,
                agent_id=runtime_agent_id or None,
                workspace_path="",
                worktree_ref="",
                base_work_dir=base_work_dir,
                slug=slug,
                create_worktree=create_worktree,
            ),
        )
        if not str(create_result.get("workspace_path") or "").strip():
            reason = str(create_result.get("reason") or create_result.get("error") or "runtime kernel unavailable")
            raise RuntimeError(f"runtime kernel create_environment required: {reason}")
        result = {
            "workspace_path": str(create_result.get("workspace_path") or ""),
            "branch_name": str(create_result.get("branch_name") or ""),
            "created": bool(create_result.get("created_worktree", False)),
            "mode": str(create_result.get("worktree_mode") or ("worktree" if create_worktree else "shared")),
            "metadata_path": str(create_result.get("metadata_path") or ""),
        }
        browser_live_session: dict[str, Any] | None = None
        scope_id = task_id
        lineage_root_env_id = self._resolve_lineage_root_env_id(parent_env_id)
        env_id = self.store.create_environment(
            task_id=task_id,
            user_id=user_id,
            chat_id=chat_id,
            classification=classification.classification,
            environment_kind=classification.environment_kind,
            isolation=classification.isolation,
            duration=classification.duration,
            workspace_path=str(result["workspace_path"]),
            runtime_dir=str(runtime_dir),
            base_work_dir=base_work_dir,
            branch_name=str(result["branch_name"]),
            created_worktree=bool(result["created"]),
            worktree_mode=str(result["mode"]),
            current_phase="provisioning",
            parent_env_id=parent_env_id,
            lineage_root_env_id=lineage_root_env_id,
            source_checkpoint_id=source_checkpoint_id,
            recovery_state=recovery_state,
            revision=revision,
        )
        if (
            activate_live_resources
            and classification.environment_kind == "dev_worktree_browser"
            and RUNTIME_BROWSER_LIVE_ENABLED
        ):
            browser_live_session = await self._start_browser_runtime_state(
                task_id=task_id,
                env_id=env_id,
                runtime_dir=str(runtime_dir),
                scope_id=scope_id,
            )
        self.store.update_runtime_queue_item(task_id, status="running")
        await self.events.publish(
            task_id=task_id,
            env_id=env_id,
            attempt=1,
            phase="provisioning",
            event_type="worktree.created",
            payload=dict(result),
            artifact_refs=[str(result["metadata_path"])] if str(result["metadata_path"]) else [],
        )
        if browser_live_session:
            await self.events.publish(
                task_id=task_id,
                env_id=env_id,
                attempt=1,
                phase="provisioning",
                event_type="browser.started",
                payload=browser_live_session,
            )
        await self.mark_phase(task_id=task_id, env_id=env_id, phase="planning")
        await self.events.publish(
            task_id=task_id,
            env_id=env_id,
            attempt=1,
            phase="planning",
            event_type="env.provisioning.finished",
            payload={"workspace_path": str(result["workspace_path"])},
        )
        return cast(dict[str, Any] | None, self.store.get_environment(env_id))

    async def ensure_environment_live_resources(self, *, task_id: int, env_id: int) -> dict[str, Any] | None:
        env = self.store.get_environment(env_id)
        if env is None:
            return None
        if str(env.get("environment_kind") or "") != "dev_worktree_browser" or not RUNTIME_BROWSER_LIVE_ENABLED:
            return cast(dict[str, Any] | None, env)
        scope_id = int(env.get("browser_scope_id") or task_id)
        active_browser_session = any(
            str(session.get("status") or "") in {"running", "pending"} and int(session.get("env_id") or 0) == env_id
            for session in self.store.list_browser_sessions(task_id)
        )
        if active_browser_session:
            return cast(dict[str, Any] | None, env)
        session = await self._start_browser_runtime_state(
            task_id=task_id,
            env_id=env_id,
            runtime_dir=str(env["runtime_dir"]),
            scope_id=scope_id,
        )
        if session is not None:
            await self.events.publish(
                task_id=task_id,
                env_id=env_id,
                attempt=None,
                phase=str(env.get("current_phase") or ""),
                event_type="browser.started",
                payload=session,
            )
        return cast(dict[str, Any] | None, self.store.get_environment(env_id))

    async def mark_phase(self, *, task_id: int, env_id: int | None, phase: str, attempt: int | None = None) -> None:
        self.store.heartbeat(task_id, env_id, phase=phase)
        if env_id is not None:
            status = "active" if phase not in {"cleaning", "cleaned"} else None
            self.store.update_environment(env_id, current_phase=phase, status=status)
        await self.events.publish(
            task_id=task_id,
            env_id=env_id,
            attempt=attempt,
            phase=phase,
            event_type=f"{phase}.entered",
        )

    async def heartbeat(
        self,
        *,
        task_id: int,
        env_id: int | None,
        phase: str | None = None,
        attempt: int | None = None,
    ) -> None:
        self.store.heartbeat(task_id, env_id, phase=phase)
        env = self.store.get_environment_by_task(task_id) if env_id is None else self.store.get_environment(env_id)
        if env:
            sample_id = await self.record_resource_sample(task_id=task_id, env_id=int(env["id"]))
            await self.events.publish(
                task_id=task_id,
                env_id=int(env["id"]),
                attempt=attempt,
                phase=phase or str(env.get("current_phase") or ""),
                event_type="resource.sampled",
                payload={"sample_id": sample_id},
                resource_snapshot_ref=str(sample_id),
            )

    async def record_resource_sample(self, *, task_id: int, env_id: int) -> int:
        env = self.store.get_environment(env_id)
        if env is None:
            return 0
        snapshot = await self._kernel_activity_snapshot(task_id=task_id)
        tracked_pids = self._snapshot_tracked_pids(snapshot)
        sample = {
            "ts_epoch": time.time(),
            "cpu_percent": None,
            "rss_kb": None,
            "process_count": len(tracked_pids) or None,
            "tracked_pids": tracked_pids,
        }
        cpu_percent = cast(float | None, sample.get("cpu_percent"))
        rss_kb = cast(float | None, sample.get("rss_kb"))
        process_count = cast(int | None, sample.get("process_count"))
        sample_id = self.store.add_resource_sample(
            task_id=task_id,
            env_id=env_id,
            cpu_percent=cpu_percent,
            rss_kb=rss_kb,
            process_count=process_count,
            workspace_disk_bytes=None,
            metadata=sample,
        )
        if cpu_percent is not None:
            RUNTIME_RESOURCE_CPU_PERCENT.set(cpu_percent)
        if rss_kb is not None:
            RUNTIME_RESOURCE_RSS_BYTES.set(rss_kb * 1024)
        return cast(int, sample_id)

    async def record_process(
        self,
        *,
        task_id: int,
        command: str,
        proc: Any,
        role: str = "provider",
        process_kind: str = "service",
        parent_pid: int | None = None,
        track_as_primary: bool = True,
    ) -> None:
        wait_started = getattr(proc, "wait_started", None)
        if callable(wait_started):
            started_result = wait_started()
            if asyncio.iscoroutine(started_result):
                await started_result
        env = self.store.get_environment_by_task(task_id)
        env_id = int(env["id"]) if env else None
        pgid = self._process_group_id_for_proc(proc)
        process_id = self.store.upsert_process(
            task_id=task_id,
            env_id=env_id,
            pid=int(proc.pid),
            pgid=pgid,
            parent_pid=parent_pid,
            role=role,
            process_kind=process_kind,
            command=command,
        )
        if env_id is not None and track_as_primary:
            self.store.update_environment(env_id, process_pid=int(proc.pid), process_pgid=pgid)
            if getattr(proc, "kernel_managed", False):
                kernel_process = {
                    "forwarded": True,
                    "process_id": getattr(proc, "process_id", ""),
                    "phase": "executing",
                    "environment_id": str((env or {}).get("id") or ""),
                }
            else:
                kernel_process = await self._forward_runtime_kernel_operation(
                    operation="start_task",
                    task_id=task_id,
                    env_id=env_id,
                    phase=str((env or {}).get("current_phase") or "executing"),
                    warn_on_failure=True,
                    call=lambda: self.runtime_kernel.start_task(task_id=task_id, command=command, args=[]),
                )
            kernel_phase = str(kernel_process.get("phase") or "").strip()
            if kernel_phase:
                self.store.update_task_runtime(task_id, phase=kernel_phase)
                self.store.update_environment(env_id, current_phase=kernel_phase)
        event_phase = str(kernel_process.get("phase") or "") if env_id is not None and track_as_primary else ""
        await self.events.publish(
            task_id=task_id,
            env_id=env_id,
            attempt=None,
            phase=event_phase or (str(env.get("current_phase") or "") if env else None),
            event_type="process.spawned",
            payload={
                "process_id": process_id,
                "pid": proc.pid,
                "pgid": pgid,
                "command": command,
                "role": role,
                "kernel_process_id": (
                    kernel_process.get("process_id") if env_id is not None and track_as_primary else None
                ),
                "kernel_environment_id": kernel_process.get("environment_id")
                if env_id is not None and track_as_primary
                else None,
            },
        )

    def _is_primary_runtime_process_row(
        self,
        *,
        process_row: Mapping[str, Any],
        env: Mapping[str, Any] | None,
    ) -> bool:
        if env is None:
            return False
        process_pid = cast(int | None, process_row.get("pid"))
        process_pgid = cast(int | None, process_row.get("pgid"))
        environment_pid = cast(int | None, env.get("process_pid"))
        environment_pgid = cast(int | None, env.get("process_pgid"))
        return bool(
            (process_pid and environment_pid and process_pid == environment_pid)
            or (process_pgid and environment_pgid and process_pgid == environment_pgid)
        )

    async def register_pid_process(
        self,
        *,
        task_id: int,
        env_id: int | None,
        pid: int | None,
        role: str,
        process_kind: str = "service",
        command: str = "",
        parent_pid: int | None = None,
    ) -> int | None:
        if pid is None:
            return None
        pgid = None
        with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
            pgid = os.getpgid(pid)
        process_id = self.store.upsert_process(
            task_id=task_id,
            env_id=env_id,
            pid=pid,
            pgid=pgid,
            parent_pid=parent_pid,
            role=role,
            process_kind=process_kind,
            command=command or role,
        )
        current_env = self.store.get_environment_by_task(task_id) if env_id else None
        await self.events.publish(
            task_id=task_id,
            env_id=env_id,
            attempt=None,
            phase=str(current_env.get("current_phase") or "") if current_env else None,
            event_type="process.spawned",
            payload={"process_id": process_id, "pid": pid, "pgid": pgid, "role": role},
        )
        return cast(int | None, process_id)

    async def register_service_endpoint(
        self,
        *,
        task_id: int,
        env_id: int | None,
        process_id: int | None,
        service_kind: str,
        label: str,
        host: str,
        port: int,
        protocol: str = "tcp",
        url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        endpoint_id = self.store.add_service_endpoint(
            task_id=task_id,
            env_id=env_id,
            process_id=process_id,
            service_kind=service_kind,
            label=label,
            host=host,
            port=port,
            protocol=protocol,
            status="active",
            url=url,
            metadata=metadata,
        )
        current_env = self.store.get_environment_by_task(task_id) if env_id else None
        await self.events.publish(
            task_id=task_id,
            env_id=env_id,
            attempt=None,
            phase=str(current_env.get("current_phase") or "") if current_env else None,
            event_type="decision.recorded",
            payload={
                "action": "service_registered",
                "service_kind": service_kind,
                "port": port,
                "endpoint_id": endpoint_id,
            },
        )
        return cast(int, endpoint_id)

    async def _retire_browser_runtime_state(self, *, task_id: int, env_id: int, scope_id: int | None = None) -> None:
        env = self.store.get_environment(env_id)
        for endpoint in self.store.list_service_endpoints(task_id):
            if int(endpoint.get("env_id") or 0) == env_id and str(endpoint.get("status") or "") != "closed":
                self.store.update_service_endpoint(int(endpoint["id"]), status="closed", ended=True)
                metadata = cast(dict[str, Any], endpoint.get("metadata") or {})
                port_allocation_id = metadata.get("port_allocation_id")
                if isinstance(port_allocation_id, int):
                    self.store.update_port_allocation(port_allocation_id, status="released", released=True)
        for session in self.store.list_browser_sessions(task_id):
            if int(session.get("env_id") or 0) == env_id and str(session.get("status") or "") != "closed":
                self.store.update_browser_session(int(session["id"]), status="closed", ended=True)
        self.port_allocator.release_ports(
            task_id=task_id,
            env_id=env_id,
            purposes=("browser_vnc", "browser_novnc"),
        )
        if scope_id is not None:
            kernel_stop = await self._forward_runtime_kernel_operation(
                operation="stop_browser_session",
                task_id=task_id,
                env_id=env_id,
                phase=str((env or {}).get("current_phase") or ""),
                warn_on_failure=True,
                call=lambda: self.runtime_kernel.stop_browser_session(
                    task_id=task_id,
                    scope_id=scope_id,
                    force=True,
                ),
            )
            if bool(kernel_stop.get("required")) and not bool(kernel_stop.get("ok")):
                await self.record_warning(
                    task_id=task_id,
                    warning_type="browser_session_stop_failed",
                    message=str(
                        kernel_stop.get("reason")
                        or kernel_stop.get("error")
                        or "runtime kernel stop_browser_session unavailable"
                    ),
                )
        await self.events.publish(
            task_id=task_id,
            env_id=env_id,
            attempt=None,
            phase=str((env or {}).get("current_phase") or ""),
            event_type="browser.closed",
            payload={"scope_id": scope_id},
        )

    async def _start_browser_runtime_state(
        self,
        *,
        task_id: int,
        env_id: int,
        runtime_dir: str,
        scope_id: int,
    ) -> dict[str, Any] | None:
        browser_transport = str(RUNTIME_BROWSER_TRANSPORT or "").strip().lower()
        runtime_kernel = self.get_runtime_kernel_health()
        kernel_browser_authoritative = self._runtime_kernel_browser_authoritative(runtime_kernel)
        browser_runtime_dir = str(Path(runtime_dir) / "browser")
        vnc_allocation: dict[str, Any] | None = None
        novnc_allocation: dict[str, Any] | None = None
        if browser_transport == "novnc":
            vnc_allocation = self.port_allocator.allocate(
                task_id=task_id,
                env_id=env_id,
                purpose="browser_vnc",
                start_port=RUNTIME_BROWSER_VNC_BASE_PORT,
                metadata={"service_kind": "browser_vnc"},
            )
            novnc_allocation = self.port_allocator.allocate(
                task_id=task_id,
                env_id=env_id,
                purpose="browser_novnc",
                start_port=RUNTIME_BROWSER_NOVNC_BASE_PORT,
                metadata={"service_kind": "browser_novnc"},
            )
        browser_live_session: dict[str, Any] | None = None
        kernel_browser = await self._forward_runtime_kernel_operation(
            operation="start_browser_session",
            task_id=task_id,
            env_id=env_id,
            phase=str((self.store.get_environment(env_id) or {}).get("current_phase") or "provisioning"),
            warn_on_failure=True,
            call=lambda: self.runtime_kernel.start_browser_session(
                task_id=task_id,
                scope_id=scope_id,
                runtime_dir=browser_runtime_dir,
                transport=browser_transport,
                display_id=int(vnc_allocation["port"]) if False else None,
                vnc_port=int(vnc_allocation["port"]) if vnc_allocation else None,
                novnc_port=int(novnc_allocation["port"]) if novnc_allocation else None,
                missing_binaries=None,
                metadata={"requested_transport": browser_transport},
            ),
        )
        if bool(kernel_browser.get("forwarded")):
            browser_live_session = dict(kernel_browser)
            session_metadata = cast(dict[str, Any], browser_live_session.get("metadata") or {})
            for key in ("xvfb_pid", "openbox_pid", "x11vnc_pid", "websockify_pid"):
                raw_value = session_metadata.get(key)
                if raw_value in (None, "", 0):
                    continue
                if isinstance(raw_value, (str, int, float, bool)):
                    with contextlib.suppress(TypeError, ValueError):
                        browser_live_session[key] = int(raw_value)
        elif kernel_browser_authoritative:
            browser_live_session = {
                "scope_id": scope_id,
                "transport": browser_transport,
                "status": "unavailable",
                "display_id": None,
                "vnc_port": None,
                "novnc_port": None,
                "runtime_dir": browser_runtime_dir,
                "missing_binaries": [],
                "kernel_error": str(
                    kernel_browser.get("reason")
                    or kernel_browser.get("error")
                    or "runtime kernel start_browser_session unavailable"
                ),
            }
        else:
            browser_live_session = {
                "scope_id": scope_id,
                "transport": browser_transport,
                "status": "unavailable",
                "display_id": None,
                "vnc_port": int(vnc_allocation["port"]) if vnc_allocation else None,
                "novnc_port": int(novnc_allocation["port"]) if novnc_allocation else None,
                "runtime_dir": browser_runtime_dir,
                "missing_binaries": [],
                "kernel_error": "runtime kernel start_browser_session unavailable",
            }
        assert browser_live_session is not None
        if bool(kernel_browser.get("forwarded")):
            browser_live_session["kernel_session_id"] = str(kernel_browser.get("session_id") or "") or None
            browser_live_session["kernel_environment_id"] = str(kernel_browser.get("environment_id") or "") or None
            browser_live_session["kernel_status"] = str(kernel_browser.get("status") or "") or None
        self.store.update_environment(
            env_id,
            browser_scope_id=scope_id,
            browser_transport=str(browser_live_session.get("transport") or RUNTIME_BROWSER_TRANSPORT),
            display_id=cast(int | None, browser_live_session.get("display_id")),
            vnc_port=cast(int | None, browser_live_session.get("vnc_port")),
            novnc_port=cast(int | None, browser_live_session.get("novnc_port")),
        )
        self.store.add_browser_session(
            task_id=task_id,
            env_id=env_id,
            scope_id=scope_id,
            transport=str(browser_live_session.get("transport") or RUNTIME_BROWSER_TRANSPORT),
            status=str(browser_live_session.get("status") or "pending"),
            display_id=cast(int | None, browser_live_session.get("display_id")),
            vnc_port=cast(int | None, browser_live_session.get("vnc_port")),
            novnc_port=cast(int | None, browser_live_session.get("novnc_port")),
            metadata=browser_live_session,
        )
        if str(browser_live_session.get("status") or "") != "running":
            if browser_transport == "novnc":
                self.port_allocator.release_ports(
                    task_id=task_id,
                    env_id=env_id,
                    purposes=("browser_vnc", "browser_novnc"),
                )
            return browser_live_session
        for allocation in self.store.list_port_allocations(task_id):
            if int(allocation.get("env_id") or 0) == env_id and str(allocation.get("status")) == "allocated":
                self.store.update_port_allocation(int(allocation["id"]), status="active")
        return browser_live_session

    async def record_plan(self, *, task_id: int, plan: dict[str, Any]) -> None:
        env = self.store.get_environment_by_task(task_id)
        env_id = int(env["id"]) if env else None
        task_root = self._task_runtime_dir(task_id)
        trace_path = task_root / "decision_trace.jsonl"
        entry = {"ts": datetime.now(UTC).isoformat(), "kind": "plan", "plan": plan}
        with trace_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        await self.events.publish(
            task_id=task_id,
            env_id=env_id,
            attempt=None,
            phase=str(env.get("current_phase") or "") if env else None,
            event_type="plan.updated",
            payload=plan,
            artifact_refs=[str(trace_path)],
        )

    async def record_decision(self, *, task_id: int, decision: dict[str, Any]) -> None:
        env = self.store.get_environment_by_task(task_id)
        env_id = int(env["id"]) if env else None
        task_root = self._task_runtime_dir(task_id)
        trace_path = task_root / "decision_trace.jsonl"
        entry = {"ts": datetime.now(UTC).isoformat(), "kind": "decision", "decision": decision}
        with trace_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        await self.events.publish(
            task_id=task_id,
            env_id=env_id,
            attempt=None,
            phase=str(env.get("current_phase") or "") if env else None,
            event_type="decision.recorded",
            payload=decision,
            artifact_refs=[str(trace_path)],
        )

    async def record_loop_cycle(
        self,
        *,
        task_id: int,
        cycle_index: int,
        phase: str,
        goal: str = "",
        plan: dict[str, Any] | None = None,
        hypothesis: str = "",
        command_fingerprint: str = "",
        diff_hash: str = "",
        failure_fingerprint: str = "",
        validations: list[dict[str, Any]] | None = None,
        outcome: dict[str, Any] | None = None,
    ) -> int:
        env = self.store.get_environment_by_task(task_id)
        env_id = int(env["id"]) if env else None
        cycle_id = self.store.add_loop_cycle(
            task_id=task_id,
            env_id=env_id,
            cycle_index=cycle_index,
            phase=phase,
            goal=goal,
            plan=plan,
            hypothesis=hypothesis,
            command_fingerprint=command_fingerprint,
            diff_hash=diff_hash,
            failure_fingerprint=failure_fingerprint,
            validations=validations,
            outcome=outcome,
        )
        trace_path = self._task_runtime_dir(task_id) / "loop_cycles.jsonl"
        entry = {
            "ts": datetime.now(UTC).isoformat(),
            "id": cycle_id,
            "cycle_index": cycle_index,
            "phase": phase,
            "goal": goal,
            "plan": plan or {},
            "hypothesis": hypothesis,
            "command_fingerprint": command_fingerprint,
            "diff_hash": diff_hash,
            "failure_fingerprint": failure_fingerprint,
            "validations": validations or [],
            "outcome": outcome or {},
        }
        with trace_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return cast(int, cycle_id)

    async def record_guardrail_hit(
        self,
        *,
        task_id: int,
        guardrail_type: str,
        cycle_id: int | None,
        details: dict[str, Any] | None = None,
    ) -> int:
        env = self.store.get_environment_by_task(task_id)
        env_id = int(env["id"]) if env else None
        RUNTIME_GUARDRAIL_HITS_TOTAL.labels(guardrail_type=guardrail_type).inc()
        return cast(
            int,
            self.store.add_guardrail_hit(
                task_id=task_id,
                env_id=env_id,
                cycle_id=cycle_id,
                guardrail_type=guardrail_type,
                details=details,
            ),
        )

    async def record_warning(
        self,
        *,
        task_id: int,
        warning_type: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        env = self.store.get_environment_by_task(task_id)
        env_id = int(env["id"]) if env else None
        self.store.add_warning(
            task_id=task_id,
            env_id=env_id,
            warning_type=warning_type,
            message=message,
            details=details,
        )
        await self.events.publish(
            task_id=task_id,
            env_id=env_id,
            attempt=None,
            phase=str(env.get("current_phase") or "") if env else None,
            event_type="warning.issued",
            severity="warning",
            payload={"warning_type": warning_type, "message": message, "details": details or {}},
        )

    async def register_terminal(
        self,
        *,
        task_id: int,
        terminal_kind: str,
        label: str,
        path: str,
        interactive: bool = False,
        stream_path: str | None = None,
    ) -> int:
        env = self.store.get_environment_by_task(task_id)
        env_id = int(env["id"]) if env else None
        terminal_id = self.store.upsert_terminal(
            task_id=task_id,
            env_id=env_id,
            terminal_kind=terminal_kind,
            label=label,
            path=path,
            stream_path=stream_path,
            interactive=interactive,
        )
        if interactive:
            RUNTIME_PTYS_ACTIVE.set(len(self.store.list_terminals(task_id)))
        return cast(int, terminal_id)

    async def append_terminal_output(
        self,
        *,
        task_id: int,
        terminal_id: int,
        text: str,
        phase: str = "executing",
        stream_type: str = "stdout",
    ) -> int:
        terminals = self.store.list_terminals(task_id)
        terminal = next((item for item in terminals if int(item["id"]) == terminal_id), None)
        if terminal is None:
            return 0
        if not self._terminal_is_kernel_backed(terminal):
            raise RuntimeError("runtime terminal output requires a kernel-backed terminal")
        if self._terminal_kernel_stream_name(terminal):
            raise RuntimeError("runtime terminal output requires a kernel terminal session")
        env = self.store.get_environment_by_task(task_id)
        env_id = int(env["id"]) if env else None
        result = await self._forward_runtime_kernel_operation(
            operation="write_terminal",
            task_id=task_id,
            env_id=env_id,
            phase=phase,
            warn_on_failure=True,
            call=lambda: self.runtime_kernel.write_terminal(
                task_id=task_id,
                session_id=self._terminal_kernel_session_id(terminal),
                data=text.encode("utf-8"),
                eof=False,
            ),
        )
        if not bool(result.get("ok", False)):
            return 0
        offset = len(text.encode("utf-8"))
        self.store.update_terminal(terminal_id, last_offset=offset)
        await self.events.publish(
            task_id=task_id,
            env_id=int(env["id"]) if env else None,
            attempt=None,
            phase=phase,
            event_type=f"command.{stream_type}",
            payload={"terminal_id": terminal_id, "offset": offset, "chunk": text},
        )
        return offset

    async def start_operator_terminal(
        self,
        *,
        task_id: int,
        actor: str = "local_ui",
        shell: str = "/bin/bash",
    ) -> dict[str, Any] | None:
        env = self.store.get_environment_by_task(task_id)
        if env is None:
            return None
        env_id = int(env["id"])
        runtime_kernel = self.get_runtime_kernel_health()
        if self._runtime_kernel_terminal_authoritative(runtime_kernel):
            session_id = f"task-{task_id}-operator-shell-{secrets.token_hex(6)}"
            opened = await self._forward_runtime_kernel_operation(
                operation="open_terminal",
                task_id=task_id,
                env_id=env_id,
                phase=str(env.get("current_phase") or ""),
                warn_on_failure=True,
                call=lambda: self.runtime_kernel.open_terminal(
                    task_id=task_id,
                    session_id=session_id,
                    command=shell,
                    args=["-lc", f"exec {shell} -li"],
                    working_directory=str(env["workspace_path"]),
                    cols=120,
                    rows=40,
                ),
            )
            if bool(opened.get("required")) and not bool(opened.get("ok")):
                return None
            kernel_session_id = str(opened.get("session_id") or "").strip()
            if not kernel_session_id:
                return None
            terminal_id = await self.register_terminal(
                task_id=task_id,
                terminal_kind="operator",
                label="operator shell",
                path=f"kernel://{kernel_session_id}",
                interactive=True,
                stream_path=f"kernel://{kernel_session_id}",
            )
            await self.record_decision(
                task_id=task_id,
                decision={
                    "action": "operator_terminal_started",
                    "actor": actor,
                    "kernel_session_id": kernel_session_id,
                },
            )
            terminal_row = next(
                (item for item in self.store.list_terminals(task_id) if int(item["id"]) == terminal_id),
                None,
            )
            if terminal_row is None:
                return None
            return {**terminal_row, "kernel_session_id": kernel_session_id}
        return None

    async def iter_terminal_stream(
        self,
        *,
        task_id: int,
        terminal_id: int,
        after_offset: int = 0,
    ) -> AsyncIterator[dict[str, Any]]:
        terminal = self._get_terminal_row(task_id=task_id, terminal_id=terminal_id)
        if terminal is None:
            return
        if self._terminal_is_kernel_backed(terminal):
            offset = max(0, int(after_offset))
            stream_name = self._terminal_kernel_stream_name(terminal)
            if stream_name:
                async for chunk in self.runtime_kernel.stream_terminal(task_id=task_id, stream=stream_name):
                    if not chunk:
                        break
                    text = chunk.decode("utf-8", errors="replace")
                    offset += len(text.encode("utf-8"))
                    self.store.update_terminal(terminal_id, last_offset=offset)
                    yield {
                        "type": "chunk",
                        "terminal_id": terminal_id,
                        "offset": offset,
                        "data": text,
                        "stream": stream_name,
                    }
                yield {
                    "type": "closed",
                    "terminal_id": terminal_id,
                    "offset": offset,
                    "data": "",
                    "stream": stream_name,
                }
                return
            session_id = self._terminal_kernel_session_id(terminal)
            async for chunk in self.runtime_kernel.stream_terminal_session(task_id=task_id, session_id=session_id):
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace")
                offset += len(text.encode("utf-8"))
                self.store.update_terminal(terminal_id, last_offset=offset)
                yield {
                    "type": "chunk",
                    "terminal_id": terminal_id,
                    "offset": offset,
                    "data": text,
                    "session_id": session_id,
                }
            yield {
                "type": "closed",
                "terminal_id": terminal_id,
                "offset": offset,
                "data": "",
                "session_id": session_id,
            }
            return
        raise RuntimeError("runtime terminal stream requires a kernel-backed terminal")

    async def write_terminal_input(self, *, task_id: int, terminal_id: int, text: str) -> bool:
        terminal = self._get_terminal_row(task_id=task_id, terminal_id=terminal_id)
        if terminal is None:
            return False
        if self._terminal_is_kernel_backed(terminal):
            env = self.store.get_environment_by_task(task_id)
            env_id = int(env["id"]) if env else None
            result = await self._forward_runtime_kernel_operation(
                operation="write_terminal",
                task_id=task_id,
                env_id=env_id,
                phase=str((env or {}).get("current_phase") or ""),
                warn_on_failure=True,
                call=lambda: self.runtime_kernel.write_terminal(
                    task_id=task_id,
                    session_id=self._terminal_kernel_session_id(terminal),
                    data=text.encode("utf-8"),
                    eof=False,
                ),
            )
            return bool(result.get("accepted", False))
        return False

    async def resize_terminal_session(self, *, task_id: int, terminal_id: int, cols: int, rows: int) -> bool:
        terminal = self._get_terminal_row(task_id=task_id, terminal_id=terminal_id)
        if terminal is None:
            return False
        if self._terminal_is_kernel_backed(terminal):
            env = self.store.get_environment_by_task(task_id)
            env_id = int(env["id"]) if env else None
            result = await self._forward_runtime_kernel_operation(
                operation="resize_terminal",
                task_id=task_id,
                env_id=env_id,
                phase=str((env or {}).get("current_phase") or ""),
                warn_on_failure=True,
                call=lambda: self.runtime_kernel.resize_terminal(
                    task_id=task_id,
                    session_id=self._terminal_kernel_session_id(terminal),
                    cols=max(1, int(cols)),
                    rows=max(1, int(rows)),
                ),
            )
            return bool(result.get("resized", False))
        return False

    async def close_terminal_session(self, *, task_id: int, terminal_id: int, force: bool = False) -> bool:
        terminal = self._get_terminal_row(task_id=task_id, terminal_id=terminal_id)
        if terminal is None:
            return False
        if self._terminal_is_kernel_backed(terminal):
            env = self.store.get_environment_by_task(task_id)
            env_id = int(env["id"]) if env else None
            result = await self._forward_runtime_kernel_operation(
                operation="close_terminal",
                task_id=task_id,
                env_id=env_id,
                phase=str((env or {}).get("current_phase") or ""),
                warn_on_failure=False,
                call=lambda: self.runtime_kernel.close_terminal(
                    task_id=task_id,
                    session_id=self._terminal_kernel_session_id(terminal),
                    force=force,
                ),
            )
            return bool(result.get("closed", False))
        return False

    async def add_artifact(
        self,
        *,
        task_id: int,
        artifact_kind: str,
        label: str,
        path: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        env = self.store.get_environment_by_task(task_id)
        env_id = int(env["id"]) if env else None
        resolved_metadata = dict(metadata or {})
        artifact_path = Path(path)
        if artifact_path.is_file() and await self._ensure_artifact_engine_started():
            with contextlib.suppress(Exception):
                descriptor = await self.artifact_engine.put_artifact(
                    path=str(artifact_path),
                    logical_filename=artifact_path.name,
                    mime_type=str(resolved_metadata.get("mime_type") or ""),
                    source_metadata_json=json.dumps(resolved_metadata, sort_keys=True, default=str),
                    purpose=artifact_kind,
                )
                artifact_id = str(descriptor.get("artifact_id") or "").strip()
                content_hash = str(descriptor.get("content_hash") or "").strip()
                object_key = str(descriptor.get("object_key") or "").strip()
                metadata_json = str(descriptor.get("metadata_json") or "").strip()
                if artifact_id:
                    resolved_metadata["artifact_id"] = artifact_id
                if content_hash:
                    resolved_metadata["content_hash"] = content_hash
                if artifact_id:
                    metadata_descriptor = await self.artifact_engine.get_artifact_metadata_by_artifact_id(
                        artifact_id=artifact_id
                    )
                    metadata_descriptor_json = str(metadata_descriptor.get("metadata_json") or "").strip()
                    metadata_descriptor_hash = str(metadata_descriptor.get("content_hash") or "").strip()
                    metadata_descriptor_object_key = str(metadata_descriptor.get("object_key") or "").strip()
                    if metadata_descriptor_hash:
                        resolved_metadata["content_hash"] = metadata_descriptor_hash
                    if metadata_descriptor_object_key:
                        object_key = metadata_descriptor_object_key
                    if metadata_descriptor_json:
                        metadata_json = metadata_descriptor_json
                        resolved_metadata["metadata_json"] = metadata_descriptor_json
                    evidence = await self.artifact_engine.generate_evidence_by_artifact_id(artifact_id=artifact_id)
                    evidence_json = str(evidence.get("evidence_json") or "").strip()
                    if evidence_json:
                        resolved_metadata["evidence_json"] = evidence_json
                if object_key:
                    resolved_metadata["object_key"] = object_key
                if metadata_json:
                    resolved_metadata["metadata_json"] = metadata_json
                resolved_metadata["artifact_engine"] = "rust_grpc"
                resolved_metadata["artifact_engine_ready"] = True
        self.store.add_artifact(
            task_id=task_id,
            env_id=env_id,
            artifact_kind=artifact_kind,
            label=label,
            path=path,
            metadata=resolved_metadata,
        )

    async def _record_runtime_task_files(self, *, task_id: int) -> None:
        task_root = self._task_runtime_dir(task_id)
        env = self.store.get_environment_by_task(task_id)
        env_id = int(env["id"]) if env else None
        existing_paths = {str(item.get("path") or "") for item in self.store.list_artifacts(task_id)}
        tracked_files = [
            (task_root / "events.ndjson", "event_log", "runtime events"),
            (task_root / "decision_trace.jsonl", "decision_trace", "decision trace"),
            (task_root / "loop_cycles.jsonl", "loop_cycles", "loop cycles"),
        ]
        runtime_directories = (
            ("stdout", "stdout_log"),
            ("stderr", "stderr_log"),
            ("browser", "browser_artifact"),
        )
        for directory_name, artifact_kind in runtime_directories:
            directory = task_root / directory_name
            if directory.exists():
                for path in sorted(child for child in directory.rglob("*") if child.is_file()):
                    tracked_files.append((path, artifact_kind, path.name))
        for path, artifact_kind, label in tracked_files:
            path_str = str(path)
            if not path.exists() or path_str in existing_paths:
                continue
            await self.add_artifact(
                task_id=task_id,
                artifact_kind=artifact_kind,
                label=label,
                path=path_str,
            )
            existing_paths.add(path_str)
            suffix = path.suffix.lower()
            if artifact_kind != "browser_artifact":
                continue
            if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
                await self.events.publish(
                    task_id=task_id,
                    env_id=env_id,
                    attempt=None,
                    phase=str((env or {}).get("current_phase") or ""),
                    event_type="browser.frame",
                    payload={"path": path_str},
                    artifact_refs=[path_str],
                )
            elif suffix == ".webm":
                await self.events.publish(
                    task_id=task_id,
                    env_id=env_id,
                    attempt=None,
                    phase=str((env or {}).get("current_phase") or ""),
                    event_type="browser.video_ready",
                    payload={"path": path_str},
                    artifact_refs=[path_str],
                )
            elif "trace" in path.name.lower() or suffix == ".zip":
                await self.events.publish(
                    task_id=task_id,
                    env_id=env_id,
                    attempt=None,
                    phase=str((env or {}).get("current_phase") or ""),
                    event_type="browser.trace_ready",
                    payload={"path": path_str},
                    artifact_refs=[path_str],
                )

    async def pause_environment(self, *, task_id: int, reason: str, actor: str = "local_ui") -> bool:
        env = self.store.get_environment_by_task(task_id)
        if env is None:
            return False
        env_id = int(env["id"])
        current_phase = str(env.get("current_phase") or "executing")
        self._resume_phase[task_id] = current_phase if "operator" not in current_phase else "executing"
        pause_event = self._ensure_pause_event(task_id)
        pause_event.clear()
        self.store.update_environment(
            env_id,
            current_phase="operator_pause_requested",
            pause_state="pause_requested",
            pause_reason=reason,
        )
        await self.events.publish(
            task_id=task_id,
            env_id=env_id,
            attempt=None,
            phase="operator_pause_requested",
            event_type="environment.paused",
            payload={"reason": reason, "actor": actor, "state": "pause_requested"},
        )
        kernel_pause = await self._forward_runtime_kernel_operation(
            operation="pause",
            task_id=task_id,
            env_id=env_id,
            phase="paused_for_operator",
            warn_on_failure=True,
            call=lambda: self.runtime_kernel.pause_task(task_id=task_id, reason=reason, actor=actor),
        )
        if bool(kernel_pause.get("required")) and not bool(kernel_pause.get("ok")):
            return False
        self.store.update_environment(
            env_id,
            current_phase="paused_for_operator",
            pause_state="paused_for_operator",
            pause_reason=reason,
        )
        self.store.update_task_runtime(task_id, phase="paused_for_operator")
        self._sync_pause_event(task_id=task_id, pause_state="paused_for_operator")
        RUNTIME_PAUSE_EVENTS_TOTAL.inc()
        return True

    async def resume_environment(self, *, task_id: int, actor: str = "local_ui") -> bool:
        env = self.store.get_environment_by_task(task_id)
        if env is None:
            return False
        env_id = int(env["id"])
        self.store.update_environment(env_id, current_phase="resuming", pause_state="resuming", pause_reason="")
        await self.events.publish(
            task_id=task_id,
            env_id=env_id,
            attempt=None,
            phase="resuming",
            event_type="environment.resumed",
            payload={"actor": actor},
        )
        phase = self._resume_phase.get(task_id, "executing")
        kernel_resume = await self._forward_runtime_kernel_operation(
            operation="resume",
            task_id=task_id,
            env_id=env_id,
            phase=phase,
            warn_on_failure=True,
            call=lambda: self.runtime_kernel.resume_task(task_id=task_id, actor=actor),
        )
        if bool(kernel_resume.get("required")) and not bool(kernel_resume.get("ok")):
            return False
        self.store.update_environment(env_id, current_phase=phase, pause_state="none", pause_reason="")
        self.store.update_task_runtime(task_id, phase=phase)
        self._sync_pause_event(task_id=task_id, pause_state="none")
        RUNTIME_RESUME_EVENTS_TOTAL.inc()
        return True

    async def cooperate_pause(self, *, task_id: int, env_id: int | None, phase: str = "executing") -> None:
        env = self.store.get_environment_by_task(task_id) if env_id is None else self.store.get_environment(env_id)
        if env is None:
            return
        pause_state = str(env.get("pause_state") or "none")
        if pause_state not in {"pause_requested", "paused_for_operator", "operator_attached"}:
            return
        if pause_state == "pause_requested":
            self.store.update_environment(
                int(env["id"]),
                current_phase="paused_for_operator",
                pause_state="paused_for_operator",
            )
            self.store.update_task_runtime(task_id, phase="paused_for_operator")
        await self._ensure_pause_event(task_id).wait()
        if env_id is not None:
            self.store.update_environment(env_id, current_phase=phase)
        self.store.update_task_runtime(task_id, phase=phase)

    async def create_attach_session(
        self,
        *,
        task_id: int,
        attach_kind: str,
        terminal_id: int | None = None,
        actor: str = "local_ui",
        can_write: bool = False,
    ) -> dict[str, Any] | None:
        env = self.store.get_environment_by_task(task_id)
        if env is None:
            return None
        env_id = int(env["id"])
        expires_at = (datetime.now(UTC) + timedelta(seconds=RUNTIME_OPERATOR_SESSION_TTL_SECONDS)).isoformat()
        effective_can_write = bool(
            can_write
            and RUNTIME_SUPERVISED_ATTACH_ENABLED
            and attach_kind == "terminal"
            and str(env.get("pause_state") or "none") in {"paused_for_operator", "operator_attached"}
        )
        token = secrets.token_urlsafe(24)
        attach_session_id = self.store.create_attach_session(
            task_id=task_id,
            env_id=env_id,
            attach_kind=attach_kind,
            terminal_id=terminal_id,
            token=token,
            can_write=effective_can_write,
            actor=actor,
            expires_at=expires_at,
        )
        kernel_terminal = {}
        if attach_kind == "terminal":
            terminal_row = None
            if terminal_id is not None:
                terminal_row = next(
                    (item for item in self.store.list_terminals(task_id) if int(item["id"]) == int(terminal_id)),
                    None,
                )
            kernel_session_id = self._terminal_kernel_session_id(terminal_row) or f"{token}:{terminal_id or 'primary'}"
            kernel_terminal = await self._forward_runtime_kernel_operation(
                operation="attach_terminal",
                task_id=task_id,
                env_id=env_id,
                phase="operator_attached" if effective_can_write else str(env.get("current_phase") or ""),
                warn_on_failure=True,
                call=lambda: self.runtime_kernel.attach_terminal(task_id=task_id, session_id=kernel_session_id),
            )
        if effective_can_write:
            self.store.update_environment(env_id, current_phase="operator_attached", pause_state="operator_attached")
            self._sync_pause_event(task_id=task_id, pause_state="operator_attached")
        await self.events.publish(
            task_id=task_id,
            env_id=env_id,
            attempt=None,
            phase="operator_attached" if effective_can_write else str(env.get("current_phase") or ""),
            event_type=f"{attach_kind}.attached",
            payload={
                "attach_session_id": attach_session_id,
                "terminal_id": terminal_id,
                "actor": actor,
                "can_write": effective_can_write,
                "expires_at": expires_at,
                "kernel_session_id": str(kernel_terminal.get("session_id") or "") or None,
            },
        )
        return {
            "attach_session_id": attach_session_id,
            "token": token,
            "task_id": task_id,
            "env_id": env_id,
            "attach_kind": attach_kind,
            "terminal_id": terminal_id,
            "can_write": effective_can_write,
            "expires_at": expires_at,
            "kernel_session_id": str(kernel_terminal.get("session_id") or "") or None,
        }

    def authorize_attach(self, *, token: str, attach_kind: str) -> dict[str, Any] | None:
        session = self.store.touch_attach_session(token)
        if session is None or str(session.get("attach_kind")) != attach_kind or str(session.get("status")) != "active":
            return None
        expires_at = str(session.get("expires_at") or "")
        if expires_at and expires_at < datetime.now(UTC).isoformat():
            self.store.close_attach_session(token)
            return None
        return cast(dict[str, Any] | None, session)

    async def close_attach_session(self, *, token: str) -> None:
        session = self.store.touch_attach_session(token)
        self.store.close_attach_session(token)
        if session is None:
            return
        task_id = int(session["task_id"])
        env = self.store.get_environment_by_task(task_id)
        if env is None:
            return
        env_id = int(env["id"])
        attach_kind = str(session["attach_kind"])
        await self.events.publish(
            task_id=task_id,
            env_id=env_id,
            attempt=None,
            phase=str(env.get("current_phase") or ""),
            event_type=f"{attach_kind}.detached",
            payload={"terminal_id": session.get("terminal_id")},
        )
        active_sessions = [
            item
            for item in self.store.list_attach_sessions(task_id)
            if str(item.get("status")) == "active" and int(item.get("can_write") or 0) == 1
        ]
        if not active_sessions and str(env.get("pause_state") or "none") == "operator_attached":
            self.store.update_environment(
                env_id,
                current_phase="paused_for_operator",
                pause_state="paused_for_operator",
            )
            self._sync_pause_event(task_id=task_id, pause_state="paused_for_operator")

    def get_workspace_tree(self, task_id: int, *, relative_path: str = "") -> list[dict[str, object]]:
        env = self.store.get_environment_by_task(task_id)
        if env is None:
            return []
        return self._list_workspace_tree(str(env["workspace_path"]), relative_path=relative_path)

    def read_workspace_file(self, task_id: int, *, relative_path: str) -> dict[str, object] | None:
        env = self.store.get_environment_by_task(task_id)
        if env is None:
            return None
        return self._read_workspace_file_payload(str(env["workspace_path"]), relative_path=relative_path)

    def get_workspace_status(self, task_id: int) -> dict[str, object]:
        env = self.store.get_environment_by_task(task_id)
        if env is None:
            return {"ok": False, "text": "environment not found"}
        return self._workspace_git_status(str(env["workspace_path"]))

    def get_workspace_diff(self, task_id: int, *, relative_path: str | None = None) -> dict[str, object]:
        env = self.store.get_environment_by_task(task_id)
        if env is None:
            return {"ok": False, "text": "environment not found", "truncated": False}
        return self._workspace_git_diff(str(env["workspace_path"]), relative_path=relative_path)

    def list_resource_samples(self, task_id: int) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self.store.list_resource_samples(task_id))

    def list_loop_cycles(self, task_id: int) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self.store.list_loop_cycles(task_id))

    def list_guardrail_hits(self, task_id: int) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self.store.list_guardrail_hits(task_id))

    def list_service_endpoints(self, task_id: int) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self.store.list_service_endpoints(task_id))

    def list_sessions(self, task_id: int) -> dict[str, Any]:
        return {
            "attach_sessions": self.store.list_attach_sessions(task_id),
            "browser_sessions": self.store.list_browser_sessions(task_id),
            "terminals": self.store.list_terminals(task_id),
        }

    async def _rehydrate_environment_state(self, task_id: int, env: dict[str, Any]) -> None:
        self._sync_pause_event(task_id=task_id, pause_state=str(env.get("pause_state") or "none"))
        scope_id = int(env.get("browser_scope_id") or env["task_id"] or task_id)
        if env.get("browser_transport"):
            kernel_browser_session: dict[str, Any] | None = None
            with contextlib.suppress(Exception):
                kernel_browser_session = await self.runtime_kernel.get_browser_session(
                    task_id=task_id, scope_id=scope_id
                )
            if (
                isinstance(kernel_browser_session, dict)
                and kernel_browser_session
                and str(kernel_browser_session.get("status") or "") in {"running", "pending", "unavailable"}
            ):
                return
            with contextlib.suppress(Exception):
                await self.ensure_environment_live_resources(task_id=task_id, env_id=int(env["id"]))

    async def cancel_task(
        self,
        *,
        task_id: int,
        actor: str = "runtime_api",
        reason: str = "Cancelled by operator.",
    ) -> dict[str, Any] | None:
        task = self.store.get_task_runtime(task_id)
        if task is None:
            return None
        env = self.store.get_environment_by_task(task_id)
        env_id = int(env["id"]) if env else None
        await self.events.publish(
            task_id=task_id,
            env_id=env_id,
            attempt=None,
            phase="cancel_requested",
            event_type="warning.issued",
            severity="warning",
            payload={"message": reason, "actor": actor, "kind": "cancel_requested"},
        )
        self.store.update_task_runtime(task_id, phase="cancel_requested", error_message=reason)
        if env_id is not None:
            self.store.update_environment(env_id, current_phase="cancel_requested", status="cancel_requested")

        from koda.services.queue_manager import cancel_active_task_execution, cancel_queued_task

        queued_cancelled = await cancel_queued_task(task_id)
        if queued_cancelled and env is None:
            final_phase = "cancelled_retained"
            self.store.update_runtime_queue_item(task_id, status="cancelled")
            self.store.update_task_runtime(task_id, status="cancelled", phase=final_phase, error_message=reason)
            await self.events.publish(
                task_id=task_id,
                env_id=None,
                attempt=None,
                phase=final_phase,
                event_type=f"{final_phase}.entered",
                payload={"actor": actor, "reason": reason},
            )
            return {"ok": True, "action": "cancelled", "task_id": task_id, "env_id": None, "final_phase": final_phase}

        cancelled = await cancel_active_task_execution(task_id, reason=reason)
        if cancelled and env is not None:
            waited_phase = await self._wait_for_task_phase(task_id, {"cancelled_retained"})
            if waited_phase:
                return {
                    "ok": True,
                    "action": "cancelled",
                    "task_id": task_id,
                    "env_id": env_id,
                    "final_phase": waited_phase,
                }
        if env is not None:
            await self._forward_runtime_kernel_operation(
                operation="terminate_task",
                task_id=task_id,
                env_id=env_id,
                phase="cancel_requested",
                warn_on_failure=True,
                call=lambda: self.runtime_kernel.terminate_task(task_id=task_id, force=True),
            )
            await self.finalize_task(
                task_id=task_id,
                success=False,
                error_message=reason,
                summary={"actor": actor, "cancelled": True},
                final_phase="cancelled_retained",
            )
        return {
            "ok": True,
            "action": "cancelled",
            "task_id": task_id,
            "env_id": env_id,
            "final_phase": "cancelled_retained",
        }

    async def _wait_for_task_phase(
        self,
        task_id: int,
        phases: set[str],
        *,
        timeout_seconds: float = 10.0,
        poll_interval: float = 0.1,
    ) -> str | None:
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while asyncio.get_running_loop().time() < deadline:
            task = self.store.get_task_runtime(task_id)
            phase = str((task or {}).get("current_phase") or "")
            if phase in phases:
                return phase
            await asyncio.sleep(poll_interval)
        return None

    async def retry_task(self, *, task_id: int, actor: str = "runtime_api") -> dict[str, Any] | None:
        source_task = self.store.get_task_runtime(task_id)
        if source_task is None or self._application is None:
            return None
        source_env = self.store.get_environment_by_task(task_id)
        checkpoint = self.store.get_latest_checkpoint(task_id)
        if checkpoint is None:
            return None
        user_id = int(source_task["user_id"])
        chat_id = int(source_task["chat_id"])
        query_text = str(source_task.get("query_text") or "")
        provider = cast(str | None, source_task.get("provider"))
        model = cast(str | None, source_task.get("model"))
        work_dir = cast(str | None, source_task.get("work_dir"))
        session_id = cast(str | None, source_task.get("session_id"))
        classification = RuntimeClassification(
            classification=str(
                source_task.get("classification")
                or (source_env.get("classification") if source_env else "")
                or classify_task(query_text).classification
            ),
            environment_kind=str(
                source_task.get("environment_kind")
                or (source_env.get("environment_kind") if source_env else "")
                or "dev_worktree"
            ),
            isolation=str(source_env.get("isolation") if source_env else "worktree"),
            duration=str(source_env.get("duration") if source_env else "medium"),
            reasons=["retry_from_checkpoint"],
        )
        new_task_id = create_task(
            user_id=user_id,
            chat_id=chat_id,
            query_text=query_text,
            provider=provider,
            model=model,
            session_id=session_id,
            work_dir=work_dir,
            source_task_id=task_id,
            source_action="retry",
        )
        await self.register_queued_task(task_id=new_task_id, user_id=user_id, chat_id=chat_id, query_text=query_text)
        new_env = await self.provision_environment(
            task_id=new_task_id,
            user_id=user_id,
            chat_id=chat_id,
            query_text=query_text,
            base_work_dir=str((source_env or {}).get("base_work_dir") or work_dir or os.getcwd()),
            classification=classification,
            parent_env_id=int(source_env["id"]) if source_env else None,
            source_checkpoint_id=int(checkpoint["id"]),
            recovery_state="retry_restored",
            activate_live_resources=False,
        )
        if new_env is None:
            return None
        kernel_checkpoint = await self._forward_runtime_kernel_operation(
            operation="get_checkpoint",
            task_id=task_id,
            env_id=int(source_env["id"]) if source_env else None,
            phase="recovering",
            warn_on_failure=False,
            call=lambda: self.runtime_kernel.get_checkpoint(task_id=task_id),
        )
        restore_payload = await self._forward_runtime_kernel_operation(
            operation="restore_checkpoint",
            task_id=task_id,
            env_id=int(source_env["id"]) if source_env else None,
            phase="recovering",
            warn_on_failure=True,
            call=lambda: self.runtime_kernel.restore_checkpoint(
                task_id=new_task_id if str(kernel_checkpoint.get("checkpoint_id") or "").strip() else task_id,
                checkpoint_id=str(kernel_checkpoint.get("checkpoint_id") or self._kernel_checkpoint_id(checkpoint)),
                workspace_path=str(new_env["workspace_path"]),
            ),
        )
        restore_succeeded = bool(restore_payload.get("restored"))
        restore_error = str(restore_payload.get("error_message") or "").strip() or None
        if not restore_succeeded:
            await self.record_warning(
                task_id=new_task_id,
                warning_type="checkpoint_restore_failed",
                message=str(restore_error or "checkpoint restore failed"),
            )
            await self.finalize_task(
                task_id=new_task_id,
                success=False,
                error_message=str(restore_error or "checkpoint restore failed"),
                summary={"source_task_id": task_id, "restore_failed": True},
            )
            return None
        self.store.update_task_runtime(
            new_task_id,
            status="queued",
            phase="queued",
            source_task_id=task_id,
            source_action="retry",
            env_id=int(new_env["id"]),
            classification=classification.classification,
            environment_kind=classification.environment_kind,
        )
        self.store.update_environment(
            int(new_env["id"]),
            status="queued",
            current_phase="queued",
            checkpoint_status="restored",
            checkpoint_path=str(checkpoint["checkpoint_dir"]),
        )
        self.store.update_runtime_queue_item(new_task_id, status="queued")
        from koda.services.queue_manager import enqueue_runtime_retry_task

        await enqueue_runtime_retry_task(
            application=self._application,
            user_id=user_id,
            task_id=new_task_id,
            chat_id=chat_id,
            query_text=query_text,
            provider=provider,
            model=model,
            work_dir=str(new_env["workspace_path"]),
            session_id=session_id,
            env_id=int(new_env["id"]),
            classification=classification.classification,
            environment_kind=classification.environment_kind,
            checkpoint_id=int(checkpoint["id"]),
        )
        self.store.add_recovery_action(
            task_id=task_id,
            env_id=int(source_env["id"]) if source_env else None,
            action="retry",
            status="queued",
            checkpoint_id=int(checkpoint["id"]),
            new_task_id=new_task_id,
            new_env_id=int(new_env["id"]),
            details={"actor": actor},
        )
        await self.events.publish(
            task_id=task_id,
            env_id=int(source_env["id"]) if source_env else None,
            attempt=None,
            phase=str((source_env or {}).get("current_phase") or ""),
            event_type="retry.scheduled",
            payload={"actor": actor, "new_task_id": new_task_id, "new_env_id": int(new_env["id"])},
        )
        return {
            "ok": True,
            "action": "retried",
            "source_task_id": task_id,
            "new_task_id": new_task_id,
            "new_env_id": int(new_env["id"]),
        }

    async def recover_task(self, *, task_id: int, actor: str = "runtime_api") -> dict[str, Any] | None:
        task = self.store.get_task_runtime(task_id)
        env = self.store.get_environment_by_task(task_id)
        if task is None or env is None:
            return None
        env_id = int(env["id"])
        revision = int(env.get("revision") or 1)
        if await self._kernel_reports_process_running(task_id=task_id):
            await self._rehydrate_environment_state(task_id, env)
            self.store.update_environment(env_id, status="active", recovery_state="reattached")
            self.store.add_recovery_action(
                task_id=task_id,
                env_id=env_id,
                action="reattach",
                status="done",
                details={"actor": actor},
            )
            await self.events.publish(
                task_id=task_id,
                env_id=env_id,
                attempt=None,
                phase=str(env.get("current_phase") or ""),
                event_type="recovery.reattached",
                payload={"actor": actor, "revision": revision},
            )
            return {"ok": True, "action": "reattached", "task_id": task_id, "env_id": env_id, "revision": revision}

        checkpoint = self.store.get_latest_checkpoint(task_id)
        if checkpoint is not None:
            kernel_checkpoint = await self._forward_runtime_kernel_operation(
                operation="get_checkpoint",
                task_id=task_id,
                env_id=env_id,
                phase="recovering",
                warn_on_failure=False,
                call=lambda: self.runtime_kernel.get_checkpoint(task_id=task_id),
            )
            old_workspace = str(env.get("workspace_path") or "")
            if bool(env.get("created_worktree")) and old_workspace and Path(old_workspace).exists():
                cleanup_result = await self._forward_runtime_kernel_operation(
                    operation="cleanup_environment",
                    task_id=task_id,
                    env_id=env_id,
                    phase="recovering",
                    warn_on_failure=False,
                    call=lambda: self.runtime_kernel.cleanup_environment(task_id=task_id, force=True),
                )
                if bool(cleanup_result.get("required")) and not bool(cleanup_result.get("ok")):
                    reason = str(
                        cleanup_result.get("reason")
                        or cleanup_result.get("error")
                        or "runtime kernel cleanup_environment unavailable"
                    )
                    raise RuntimeError(f"runtime kernel cleanup_environment required during recovery: {reason}")
                if not (bool(cleanup_result.get("forwarded")) and bool(cleanup_result.get("cleaned"))):
                    reason = str(
                        cleanup_result.get("reason")
                        or cleanup_result.get("error")
                        or "runtime kernel cleanup_environment unavailable during recovery"
                    )
                    raise RuntimeError(reason)
            next_revision = revision + 1
            base_work_dir = str(env.get("base_work_dir") or task.get("work_dir") or os.getcwd())
            recovery_slug = f"{self._slugify(str(task.get('query_text') or 'task'))}-recover-r{next_revision}"
            create_result = await self._forward_runtime_kernel_operation(
                operation="create_environment",
                task_id=task_id,
                env_id=env_id,
                phase="recovering",
                warn_on_failure=True,
                call=lambda: self.runtime_kernel.create_environment(
                    task_id=task_id,
                    agent_id=str(task.get("agent_id") or AGENT_ID or "").strip() or None,
                    workspace_path="",
                    worktree_ref="",
                    base_work_dir=base_work_dir,
                    slug=recovery_slug,
                    create_worktree=True,
                ),
            )
            if not str(create_result.get("workspace_path") or "").strip():
                reason = str(
                    create_result.get("reason")
                    or create_result.get("error")
                    or "runtime kernel create_environment unavailable"
                )
                raise RuntimeError(f"runtime kernel create_environment required during recovery: {reason}")
            result = {
                "workspace_path": str(create_result.get("workspace_path") or ""),
                "branch_name": str(create_result.get("branch_name") or ""),
                "created_worktree": bool(create_result.get("created_worktree", False)),
                "worktree_mode": str(create_result.get("worktree_mode") or "worktree"),
                "metadata_path": str(create_result.get("metadata_path") or ""),
            }
            restore_payload = await self._forward_runtime_kernel_operation(
                operation="restore_checkpoint",
                task_id=task_id,
                env_id=env_id,
                phase="recovering",
                warn_on_failure=True,
                call=lambda: self.runtime_kernel.restore_checkpoint(
                    task_id=task_id,
                    checkpoint_id=str(kernel_checkpoint.get("checkpoint_id") or self._kernel_checkpoint_id(checkpoint)),
                    workspace_path=str(result["workspace_path"]),
                ),
            )
            if bool(restore_payload.get("required")) and not bool(restore_payload.get("ok")):
                reason = str(
                    restore_payload.get("reason")
                    or restore_payload.get("error_message")
                    or restore_payload.get("error")
                    or "runtime kernel restore_checkpoint unavailable"
                )
                raise RuntimeError(f"runtime kernel restore_checkpoint required during recovery: {reason}")
            restore_succeeded = bool(restore_payload.get("restored"))
            restore_error = str(restore_payload.get("error_message") or "").strip() or None
            if not restore_succeeded:
                await self.record_warning(
                    task_id=task_id,
                    warning_type="checkpoint_restore_failed",
                    message=str(restore_error or "checkpoint restore failed during recovery"),
                )
                self.store.update_environment(
                    env_id,
                    status="retained",
                    current_phase="recoverable_failed_retained",
                    recovery_state="marked_recoverable_failed",
                )
                self.store.update_task_runtime(task_id, phase="recoverable_failed_retained")
                return {
                    "ok": True,
                    "action": "marked_recoverable_failed",
                    "task_id": task_id,
                    "env_id": env_id,
                    "revision": revision,
                }
            if str(env.get("browser_transport") or ""):
                await self._retire_browser_runtime_state(
                    task_id=task_id,
                    env_id=env_id,
                    scope_id=int(env.get("browser_scope_id") or task_id),
                )
            self.store.update_environment(
                env_id,
                status="active",
                current_phase="paused_for_operator",
                workspace_path=str(result["workspace_path"]),
                branch_name=str(result["branch_name"]),
                runtime_dir=str(self._task_runtime_dir(task_id)),
                base_work_dir=base_work_dir,
                created_worktree=bool(result["created_worktree"]),
                worktree_mode=str(result["worktree_mode"]),
                source_checkpoint_id=int(checkpoint["id"]),
                recovery_state="reconstructed",
                revision=next_revision,
                pause_state="paused_for_operator",
                pause_reason="Recovered from checkpoint",
                browser_transport="" if str(env.get("environment_kind") or "") != "dev_worktree_browser" else None,
                display_id=0 if str(env.get("environment_kind") or "") != "dev_worktree_browser" else None,
                vnc_port=0 if str(env.get("environment_kind") or "") != "dev_worktree_browser" else None,
                novnc_port=0 if str(env.get("environment_kind") or "") != "dev_worktree_browser" else None,
                browser_scope_id=0 if str(env.get("environment_kind") or "") != "dev_worktree_browser" else None,
                process_pid=0,
                process_pgid=0,
            )
            self._sync_pause_event(task_id=task_id, pause_state="paused_for_operator")
            if str(env.get("environment_kind") or "") == "dev_worktree_browser" and RUNTIME_BROWSER_LIVE_ENABLED:
                await self._start_browser_runtime_state(
                    task_id=task_id,
                    env_id=env_id,
                    runtime_dir=str(self._task_runtime_dir(task_id)),
                    scope_id=int(env.get("browser_scope_id") or task_id),
                )
            self.store.update_task_runtime(task_id, phase="paused_for_operator")
            await self._rehydrate_environment_state(task_id, self.store.get_environment(env_id) or env)
            self.store.add_recovery_action(
                task_id=task_id,
                env_id=env_id,
                action="reconstruct",
                status="done",
                checkpoint_id=int(checkpoint["id"]),
                details={"actor": actor, "revision": next_revision},
            )
            await self.events.publish(
                task_id=task_id,
                env_id=env_id,
                attempt=None,
                phase="paused_for_operator",
                event_type="recovery.detected",
                payload={
                    "actor": actor,
                    "action": "reconstructed",
                    "revision": next_revision,
                    "kernel_checkpoint_id": kernel_checkpoint.get("checkpoint_id"),
                },
            )
            return {
                "ok": True,
                "action": "reconstructed",
                "task_id": task_id,
                "env_id": env_id,
                "revision": next_revision,
            }

        if env.get("workspace_path") and Path(str(env["workspace_path"])).exists():
            await self.finalize_task(
                task_id=task_id,
                success=False,
                error_message="emergency recovery save",
                summary={"actor": actor, "emergency_save": True},
                final_phase="recoverable_failed_retained",
            )
        self.store.update_environment(
            env_id,
            status="retained",
            current_phase="recoverable_failed_retained",
            recovery_state="marked_recoverable_failed",
        )
        self.store.update_task_runtime(task_id, status="failed", phase="recoverable_failed_retained")
        self.store.update_runtime_queue_item(task_id, status="failed")
        self.store.add_recovery_action(
            task_id=task_id,
            env_id=env_id,
            action="mark_recoverable_failed",
            status="done",
            details={"actor": actor},
        )
        await self.events.publish(
            task_id=task_id,
            env_id=env_id,
            attempt=None,
            phase="recoverable_failed_retained",
            event_type="recovery.failed",
            payload={"actor": actor, "action": "marked_recoverable_failed"},
        )
        return {
            "ok": True,
            "action": "marked_recoverable_failed",
            "task_id": task_id,
            "env_id": env_id,
            "revision": revision,
        }

    async def reconcile_runtime_state(self) -> None:
        for env in self.store.list_environments():
            task_id = int(env["task_id"])
            env_id = int(env["id"])
            snapshot = await self._kernel_activity_snapshot(task_id=task_id)
            primary_process_running = bool(self._snapshot_task_payload(snapshot).get("process_running"))
            active_browser = bool(self._snapshot_running_browser_sessions(snapshot))
            active_terminal_pids = set(self._snapshot_tracked_pids(snapshot))
            processes = self.store.list_processes(task_id, env_id=env_id)
            process_by_id = {int(process_row["id"]): process_row for process_row in processes}
            for process_row in processes:
                pid = cast(int | None, process_row.get("pid"))
                alive = False
                if self._is_primary_runtime_process_row(process_row=process_row, env=env):
                    alive = primary_process_running
                elif isinstance(pid, int) and pid > 0 and pid in active_terminal_pids:
                    alive = True
                elif str(process_row.get("process_kind") or "") == "browser_sidecar":
                    alive = active_browser
                if alive:
                    continue
                if str(process_row.get("status")) != "exited":
                    self.store.update_process(int(process_row["id"]), status="exited", exited=True)
                    await self.events.publish(
                        task_id=task_id,
                        env_id=env_id,
                        attempt=None,
                        phase=str(env.get("current_phase") or ""),
                        event_type="process.exited",
                        payload={"process_id": process_row["id"], "pid": pid},
                    )
            for endpoint in self.store.list_service_endpoints(task_id):
                if int(endpoint.get("env_id") or 0) != env_id:
                    continue
                process_id = cast(int | None, endpoint.get("process_id"))
                linked_process = process_by_id.get(process_id) if process_id is not None else None
                if linked_process is not None and str(linked_process.get("status")) == "exited":
                    self.store.update_service_endpoint(int(endpoint["id"]), status="closed", ended=True)
                    metadata = cast(dict[str, Any], endpoint.get("metadata") or {})
                    port_allocation_id = metadata.get("port_allocation_id")
                    if isinstance(port_allocation_id, int):
                        self.store.update_port_allocation(port_allocation_id, status="released", released=True)
            if str(env.get("browser_transport") or ""):
                sidecars = [proc for proc in processes if str(proc.get("process_kind")) == "browser_sidecar"]
                if sidecars and all(str(proc.get("status")) == "exited" for proc in sidecars):
                    browser_sessions = self.store.list_browser_sessions(task_id)
                    for browser_session in browser_sessions:
                        if int(browser_session.get("env_id") or 0) == env_id:
                            self.store.update_browser_session(
                                int(browser_session["id"]),
                                status="closed",
                                ended=True,
                            )
                    scope_id = int(env.get("browser_scope_id") or env["task_id"])

                    async def _stop_browser_session(
                        *,
                        _task_id: int = task_id,
                        _scope_id: int = scope_id,
                    ) -> dict[str, object] | None:
                        return await self.runtime_kernel.stop_browser_session(
                            task_id=_task_id,
                            scope_id=_scope_id,
                            force=True,
                        )

                    await self._forward_runtime_kernel_operation(
                        operation="stop_browser_session",
                        task_id=task_id,
                        env_id=env_id,
                        phase=str(env.get("current_phase") or ""),
                        warn_on_failure=False,
                        call=_stop_browser_session,
                    )
                    self.port_allocator.release_ports(
                        task_id=task_id,
                        env_id=env_id,
                        purposes=("browser_vnc", "browser_novnc"),
                    )
                    await self.events.publish(
                        task_id=task_id,
                        env_id=env_id,
                        attempt=None,
                        phase=str(env.get("current_phase") or ""),
                        event_type="browser.closed",
                        payload={"scope_id": scope_id, "reason": "sidecars_exited"},
                    )
            if str(env.get("status")) == "active":
                all_processes = self.store.list_processes(task_id, env_id=env_id)
                if all_processes and all(str(p.get("status")) == "exited" for p in all_processes):
                    pause_state = str(env.get("pause_state") or "none")
                    current_phase = str(env.get("current_phase") or "")
                    scope_id = int(env.get("browser_scope_id") or env["task_id"])
                    has_active_attach = any(
                        str(session.get("status") or "") == "active"
                        for session in self.store.list_attach_sessions(task_id)
                    )
                    has_active_browser = any(
                        str(session.get("status") or "") == "running" and int(session.get("env_id") or 0) == env_id
                        for session in self.store.list_browser_sessions(task_id)
                    )
                    if (
                        pause_state in {"pause_requested", "paused_for_operator", "operator_attached", "resuming"}
                        or current_phase in {"paused_for_operator", "operator_attached", "resuming"}
                        or has_active_attach
                        or has_active_browser
                    ):
                        continue
                    await self.events.publish(
                        task_id=task_id,
                        env_id=env_id,
                        attempt=None,
                        phase=str(env.get("current_phase") or ""),
                        event_type="reconcile.orphan_detected",
                        payload={"process_count": len(all_processes)},
                    )
                    with contextlib.suppress(Exception):
                        await self.recover_task(task_id=task_id, actor="reconcile_sweep")
        await self._forward_runtime_kernel_operation(
            operation="reconcile",
            task_id=None,
            env_id=None,
            phase="reconcile",
            warn_on_failure=False,
            call=self.runtime_kernel.reconcile,
        )

    async def get_runtime_kernel_snapshot(self, *, task_id: int) -> dict[str, Any] | None:
        with contextlib.suppress(Exception):
            snapshot = await self.runtime_kernel.collect_snapshot(task_id=task_id)
            if isinstance(snapshot, dict):
                return cast(dict[str, Any], snapshot)
        return None

    async def save_snapshot(self, *, task_id: int, actor: str = "local_ui") -> dict[str, Any] | None:
        await self.record_decision(task_id=task_id, decision={"action": "save_snapshot", "actor": actor})
        return await self.finalize_task(task_id=task_id, success=False, summary={"save_only": True, "actor": actor})

    async def terminate_process(self, *, process_id: int, force: bool = False) -> dict[str, Any] | None:
        process_row = self.store.get_process(process_id)
        if process_row is None:
            return None
        task_id = int(process_row["task_id"])
        env_id = cast(int | None, process_row.get("env_id"))
        env = self.store.get_environment(env_id) if env_id is not None else self.store.get_environment_by_task(task_id)
        terminated = False
        if self._is_primary_runtime_process_row(process_row=process_row, env=env):
            kernel_terminate = await self._forward_runtime_kernel_operation(
                operation="terminate_task",
                task_id=task_id,
                env_id=env_id,
                phase=str((env or {}).get("current_phase") or ""),
                warn_on_failure=True,
                call=lambda: self.runtime_kernel.terminate_task(task_id=task_id, force=force),
            )
            terminated = bool(kernel_terminate.get("forwarded")) and bool(kernel_terminate.get("terminated", True))
        if not terminated:
            return {
                "ok": False,
                "action": "runtime_kernel_required",
                "task_id": task_id,
                "env_id": env_id,
                "process_id": process_id,
            }
        self.store.update_process(process_id, status="exited", exited=True)
        for endpoint in self.store.list_service_endpoints(task_id):
            if int(endpoint.get("process_id") or 0) != process_id:
                continue
            self.store.update_service_endpoint(int(endpoint["id"]), status="closed", ended=True)
            metadata = cast(dict[str, Any], endpoint.get("metadata") or {})
            port_allocation_id = metadata.get("port_allocation_id")
            if isinstance(port_allocation_id, int):
                self.store.update_port_allocation(port_allocation_id, status="released", released=True)
        await self.events.publish(
            task_id=task_id,
            env_id=env_id,
            attempt=None,
            phase=str((self.store.get_environment_by_task(task_id) or {}).get("current_phase") or ""),
            event_type="process.exited",
            payload={"process_id": process_id, "force": force},
        )
        return {
            "ok": True,
            "action": "terminated",
            "task_id": task_id,
            "env_id": env_id,
            "process_id": process_id,
        }

    async def finalize_task(
        self,
        *,
        task_id: int,
        success: bool,
        error_message: str | None = None,
        summary: dict[str, Any] | None = None,
        final_phase: str | None = None,
    ) -> dict[str, Any] | None:
        resolved_final_phase = final_phase or ("completed_retained" if success else "recoverable_failed_retained")
        queue_status = "completed" if resolved_final_phase == "completed_retained" else "failed"
        if resolved_final_phase == "cancelled_retained":
            queue_status = "cancelled"
        if resolved_final_phase == "needs_review_retained":
            queue_status = "needs_review"
        env = self.store.get_environment_by_task(task_id)
        if env is None:
            self.store.update_runtime_queue_item(task_id, status=queue_status)
            self.store.update_task_runtime(
                task_id,
                status=queue_status,
                phase=resolved_final_phase,
                retention_expires_at=(
                    datetime.now(UTC)
                    + timedelta(hours=RUNTIME_RETENTION_SUCCESS_HOURS if success else RUNTIME_RETENTION_FAILURE_HOURS)
                ).isoformat(),
            )
            await self._forward_runtime_kernel_operation(
                operation="finalize",
                task_id=task_id,
                env_id=None,
                phase=resolved_final_phase,
                warn_on_failure=False,
                call=lambda: self.runtime_kernel.finalize_task(
                    task_id=task_id,
                    success=success,
                    final_phase=resolved_final_phase,
                    error_message=error_message,
                ),
            )
            return None
        env_id = int(env["id"])
        retention_hours = RUNTIME_RETENTION_SUCCESS_HOURS if success else RUNTIME_RETENTION_FAILURE_HOURS
        retention_expires_at = (datetime.now(UTC) + timedelta(hours=retention_hours)).isoformat()
        await self.mark_phase(task_id=task_id, env_id=env_id, phase="save_verifying")
        await self.events.publish(
            task_id=task_id,
            env_id=env_id,
            attempt=None,
            phase="checkpointing",
            event_type="checkpoint.started",
            payload={"success": success},
        )
        try:
            kernel_checkpoint = await self._forward_runtime_kernel_operation(
                operation="save_checkpoint",
                task_id=task_id,
                env_id=env_id,
                phase="checkpointing",
                warn_on_failure=True,
                call=lambda: self.runtime_kernel.save_checkpoint(
                    task_id=task_id,
                    environment_id=str(env_id),
                    success=success,
                    final_phase=resolved_final_phase,
                    retention_hours=retention_hours,
                ),
            )
            if bool(kernel_checkpoint.get("required")) and not bool(kernel_checkpoint.get("ok")):
                reason = str(
                    kernel_checkpoint.get("reason")
                    or kernel_checkpoint.get("error_message")
                    or kernel_checkpoint.get("error")
                    or "runtime kernel save_checkpoint unavailable"
                )
                raise RuntimeError(f"runtime kernel save_checkpoint required: {reason}")
            checkpoint_dir = str(kernel_checkpoint.get("checkpoint_dir") or "")
            manifest_path = str(kernel_checkpoint.get("manifest_path") or "")
            snapshot_path = str(kernel_checkpoint.get("snapshot_path") or "")
            patch_path = str(kernel_checkpoint.get("patch_path") or "")
            git_status_path = str(kernel_checkpoint.get("git_status_path") or "")
            untracked_bundle_path = str(kernel_checkpoint.get("untracked_bundle_path") or "")
            commit_sha = str(kernel_checkpoint.get("commit_sha") or "").strip() or None
            has_untracked_bundle = bool(kernel_checkpoint.get("has_untracked_bundle", False))
            verify_deadline = asyncio.get_running_loop().time() + RUNTIME_SAVE_VERIFY_TIMEOUT_SECONDS
            while asyncio.get_running_loop().time() < verify_deadline:
                has_core_bundle = (
                    bool(manifest_path)
                    and Path(manifest_path).exists()
                    and Path(manifest_path).stat().st_size > 0
                    and bool(snapshot_path)
                    and Path(snapshot_path).exists()
                    and Path(snapshot_path).stat().st_size > 0
                    and bool(patch_path)
                    and Path(patch_path).exists()
                    and bool(git_status_path)
                    and Path(git_status_path).exists()
                )
                has_optional_bundle = not has_untracked_bundle or (
                    bool(untracked_bundle_path) and Path(untracked_bundle_path).exists()
                )
                if has_core_bundle and has_optional_bundle:
                    break
                await asyncio.sleep(0.25)
            else:
                RUNTIME_SAVE_VERIFY_FAILURES_TOTAL.inc()
                raise RuntimeError("kernel checkpoint save verification timed out")
            manifest_content = Path(manifest_path).read_text(encoding="utf-8")
            if len(manifest_content) < 2:
                RUNTIME_SAVE_VERIFY_FAILURES_TOTAL.inc()
                raise RuntimeError("kernel checkpoint manifest is empty or trivial")
            try:
                json.loads(manifest_content)
            except json.JSONDecodeError as exc:
                RUNTIME_SAVE_VERIFY_FAILURES_TOTAL.inc()
                raise RuntimeError(f"kernel checkpoint manifest is not valid JSON: {exc}") from exc
            expires_at_ms = int(kernel_checkpoint.get("expires_at_ms") or 0)
            checkpoint_expires_at = (
                datetime.fromtimestamp(expires_at_ms / 1000, UTC).isoformat()
                if expires_at_ms > 0
                else retention_expires_at
            )
            checkpoint_id = self.store.add_checkpoint(
                task_id=task_id,
                env_id=env_id,
                status="saved",
                checkpoint_dir=checkpoint_dir,
                manifest_path=manifest_path,
                patch_path=patch_path,
                commit_sha=commit_sha,
                expires_at=checkpoint_expires_at,
                metadata={
                    "success": success,
                    "summary": summary or {},
                    "snapshot_path": snapshot_path,
                    "git_status_path": git_status_path,
                    "untracked_bundle_path": untracked_bundle_path,
                    "has_untracked_bundle": has_untracked_bundle,
                    "runtime_kernel_checkpoint": {
                        "required": bool(kernel_checkpoint.get("required")),
                        "forwarded": bool(kernel_checkpoint.get("forwarded")),
                        "saved": bool(kernel_checkpoint.get("saved")),
                        "checkpoint_id": str(kernel_checkpoint.get("checkpoint_id") or ""),
                        "environment_id": str(kernel_checkpoint.get("environment_id") or ""),
                        "checkpoint_dir": str(kernel_checkpoint.get("checkpoint_dir") or ""),
                        "manifest_path": str(kernel_checkpoint.get("manifest_path") or ""),
                        "snapshot_path": str(kernel_checkpoint.get("snapshot_path") or ""),
                        "created_at_ms": int(kernel_checkpoint.get("created_at_ms") or 0),
                        "expires_at_ms": int(kernel_checkpoint.get("expires_at_ms") or 0),
                    },
                },
            )
            save_verified_at = datetime.now(UTC).isoformat()
            self.store.update_environment(
                env_id,
                status="retained",
                current_phase=resolved_final_phase,
                checkpoint_status="saved",
                checkpoint_path=checkpoint_dir,
                retention_expires_at=retention_expires_at,
                save_verified_at=save_verified_at,
            )
            self.store.update_task_runtime(
                task_id,
                status=queue_status,
                phase=resolved_final_phase,
                retention_expires_at=retention_expires_at,
            )
            self.store.update_runtime_queue_item(task_id, status=queue_status)
            await self.add_artifact(
                task_id=task_id,
                artifact_kind="manifest",
                label="runtime manifest",
                path=manifest_path,
            )
            await self.add_artifact(
                task_id=task_id,
                artifact_kind="patch",
                label="git patch",
                path=patch_path,
            )
            await self.add_artifact(
                task_id=task_id,
                artifact_kind="snapshot",
                label="workspace snapshot",
                path=snapshot_path,
            )
            await self.add_artifact(
                task_id=task_id,
                artifact_kind="git_status",
                label="git status",
                path=git_status_path,
            )
            if has_untracked_bundle:
                await self.add_artifact(
                    task_id=task_id,
                    artifact_kind="untracked_bundle",
                    label="untracked bundle",
                    path=untracked_bundle_path,
                )
            await self._record_runtime_task_files(task_id=task_id)
            await self.events.publish(
                task_id=task_id,
                env_id=env_id,
                attempt=None,
                phase="checkpointing",
                event_type="checkpoint.saved",
                payload={
                    "checkpoint_id": checkpoint_id,
                    "checkpoint_dir": checkpoint_dir,
                    "kernel_checkpoint_id": kernel_checkpoint.get("checkpoint_id"),
                },
                artifact_refs=[
                    manifest_path,
                    patch_path,
                    snapshot_path,
                    git_status_path,
                ],
            )
            for process_row in self.store.list_processes(task_id, env_id=env_id):
                if str(process_row.get("status")) == "exited":
                    continue
                self.store.update_process(int(process_row["id"]), status="exited", exited=True)
                await self.events.publish(
                    task_id=task_id,
                    env_id=env_id,
                    attempt=None,
                    phase=resolved_final_phase,
                    event_type="process.exited",
                    payload={"process_id": process_row["id"], "pid": process_row.get("pid")},
                )
            await self.events.publish(
                task_id=task_id,
                env_id=env_id,
                attempt=None,
                phase=resolved_final_phase,
                event_type=f"{resolved_final_phase}.entered",
                payload={"error_message": error_message},
            )
            await self._forward_runtime_kernel_operation(
                operation="finalize",
                task_id=task_id,
                env_id=env_id,
                phase=resolved_final_phase,
                warn_on_failure=True,
                call=lambda: self.runtime_kernel.finalize_task(
                    task_id=task_id,
                    success=success,
                    final_phase=resolved_final_phase,
                    error_message=error_message,
                ),
            )
            return cast(dict[str, Any] | None, self.store.get_environment(env_id))
        except Exception as exc:
            error_text = str(exc)
            RUNTIME_CHECKPOINT_FAILURES_TOTAL.inc()
            self.store.update_environment(
                env_id,
                status="retained",
                current_phase="recoverable_failed_retained",
                checkpoint_status="failed",
            )
            self.store.update_task_runtime(
                task_id,
                status="failed",
                phase="recoverable_failed_retained",
                retention_expires_at=retention_expires_at,
            )
            self.store.update_runtime_queue_item(task_id, status="failed")
            await self.events.publish(
                task_id=task_id,
                env_id=env_id,
                attempt=None,
                phase="checkpointing",
                event_type="checkpoint.failed",
                severity="error",
                payload={"error": error_text},
            )
            await self._forward_runtime_kernel_operation(
                operation="finalize",
                task_id=task_id,
                env_id=env_id,
                phase="recoverable_failed_retained",
                warn_on_failure=True,
                call=lambda: self.runtime_kernel.finalize_task(
                    task_id=task_id,
                    success=False,
                    final_phase="recoverable_failed_retained",
                    error_message=error_text,
                ),
            )
            return cast(dict[str, Any] | None, self.store.get_environment(env_id))

    async def request_cleanup(self, *, task_id: int, force: bool = False) -> bool:
        env = self.store.get_environment_by_task(task_id)
        if env is None:
            return False
        env_id = int(env["id"])
        previous_phase = str(env.get("current_phase") or "")
        previous_status = str(env.get("status") or "")
        if env.get("is_pinned") and not force:
            RUNTIME_CLEANUP_BLOCKED_TOTAL.inc()
            await self.events.publish(
                task_id=task_id,
                env_id=env_id,
                attempt=None,
                phase=str(env.get("current_phase") or ""),
                event_type="cleanup.blocked",
                severity="warning",
                payload={"reason": "pinned"},
            )
            return False
        if not env.get("save_verified_at") and not force:
            RUNTIME_CLEANUP_BLOCKED_TOTAL.inc()
            await self.events.publish(
                task_id=task_id,
                env_id=env_id,
                attempt=None,
                phase=str(env.get("current_phase") or ""),
                event_type="cleanup.blocked",
                severity="warning",
                payload={"reason": "save_not_verified"},
            )
            return False
        await self.events.publish(
            task_id=task_id,
            env_id=env_id,
            attempt=None,
            phase="cleaning",
            event_type="cleanup.started",
            payload={"force": force},
        )
        self.store.update_environment(env_id, current_phase="cleaning", status="cleaning")
        kernel_primary_terminated = False
        if cast(int | None, env.get("process_pid")) or cast(int | None, env.get("process_pgid")):
            kernel_terminate = await self._forward_runtime_kernel_operation(
                operation="terminate_task",
                task_id=task_id,
                env_id=env_id,
                phase="cleaning",
                warn_on_failure=True,
                call=lambda: self.runtime_kernel.terminate_task(task_id=task_id, force=force),
            )
            kernel_primary_terminated = bool(kernel_terminate.get("forwarded")) and bool(
                kernel_terminate.get("terminated", True)
            )
            if bool(kernel_terminate.get("required")) and not bool(kernel_terminate.get("ok")):
                self.store.update_environment(env_id, current_phase=previous_phase, status=previous_status)
                return False
        for process_row in self.store.list_processes(task_id, env_id=env_id):
            if not kernel_primary_terminated and self._is_primary_runtime_process_row(process_row=process_row, env=env):
                continue
            self.store.update_process(
                int(process_row["id"]),
                status="exited",
                exited=True,
            )
            await self.events.publish(
                task_id=task_id,
                env_id=env_id,
                attempt=None,
                phase="cleaning",
                event_type="process.exited",
                payload={"process_id": process_row["id"], "pid": process_row.get("pid")},
            )
        for terminal in self.store.list_terminals(task_id):
            if self._terminal_is_kernel_backed(terminal):
                await self.close_terminal_session(task_id=task_id, terminal_id=int(terminal["id"]), force=force)
        scope_id = int(env.get("browser_scope_id") or env["task_id"])
        await self._forward_runtime_kernel_operation(
            operation="stop_browser_session",
            task_id=task_id,
            env_id=env_id,
            phase="cleaning",
            warn_on_failure=False,
            call=lambda: self.runtime_kernel.stop_browser_session(task_id=task_id, scope_id=scope_id, force=force),
        )
        for endpoint in self.store.list_service_endpoints(task_id):
            if int(endpoint.get("env_id") or 0) != env_id:
                continue
            self.store.update_service_endpoint(int(endpoint["id"]), status="closed", ended=True)
        for browser_session in self.store.list_browser_sessions(task_id):
            if int(browser_session.get("env_id") or 0) != env_id:
                continue
            self.store.update_browser_session(int(browser_session["id"]), status="closed", ended=True)
        await self.events.publish(
            task_id=task_id,
            env_id=env_id,
            attempt=None,
            phase="cleaning",
            event_type="browser.closed",
            payload={"scope_id": scope_id, "force": force},
        )
        for session in self.store.list_attach_sessions(task_id):
            if str(session.get("status")) == "active":
                await self.close_attach_session(token=str(session["token"]))
        release_task_ports = getattr(self.port_allocator, "release_task_ports", None)
        if callable(release_task_ports):
            release_task_ports(task_id)
        cleanup_result = await self._forward_runtime_kernel_operation(
            operation="cleanup_environment",
            task_id=task_id,
            env_id=env_id,
            phase="cleaning",
            warn_on_failure=True,
            call=lambda: self.runtime_kernel.cleanup_environment(task_id=task_id, force=force),
        )
        if bool(cleanup_result.get("required")) and not bool(cleanup_result.get("ok")):
            reason = str(
                cleanup_result.get("reason")
                or cleanup_result.get("error")
                or "runtime kernel cleanup_environment unavailable"
            )
            self.store.update_environment(env_id, current_phase=previous_phase, status=previous_status)
            self.store.update_task_runtime(task_id, phase=previous_phase)
            await self.events.publish(
                task_id=task_id,
                env_id=env_id,
                attempt=None,
                phase=previous_phase,
                event_type="cleanup.blocked",
                severity="error",
                payload={"reason": reason, "required": True},
            )
            return False
        removed = bool(cleanup_result.get("workspace_removed"))
        self.store.update_environment(
            env_id,
            current_phase="cleaned",
            status="cleaned",
            process_pid=0,
            process_pgid=0,
            vnc_port=0,
            novnc_port=0,
            browser_scope_id=0,
            pause_state="none",
            pause_reason="",
        )
        self.store.update_task_runtime(task_id, phase="cleaned")
        await self.events.publish(
            task_id=task_id,
            env_id=env_id,
            attempt=None,
            phase="cleaned",
            event_type="cleanup.finished",
            payload={"removed": removed},
        )
        await self.events.publish(
            task_id=task_id,
            env_id=env_id,
            attempt=None,
            phase="cleaned",
            event_type="worktree.removed",
            payload={"removed": removed},
        )
        runtime_artifacts_removed = await asyncio.to_thread(self._remove_task_runtime_dir, task_id)
        if runtime_artifacts_removed:
            log.info("runtime_task_root_removed", task_id=task_id)
        return True

    async def cleanup_expired(self) -> None:
        now = datetime.now(UTC).isoformat()
        for env in self.store.list_environments():
            expires_at = env.get("retention_expires_at")
            if not expires_at or env.get("is_pinned"):
                continue
            if str(expires_at) <= now and str(env.get("status")) not in {"cleaned", "cleaning"}:
                await self.request_cleanup(
                    task_id=int(env["task_id"]),
                    force=not bool(env.get("save_verified_at")),
                )

    async def run_recovery_sweep(self) -> None:
        for action in self.recovery.recover_stale():
            task_id = cast(int, action["task_id"])
            env_id = cast(int, action["env_id"])
            action_name = str(action["action"])
            if action_name == "reattach":
                await self.recover_task(task_id=task_id, actor="recovery_sweep")
                RUNTIME_RECOVERIES_TOTAL.inc()
                continue
            if action_name == "reconstruct":
                await self.recover_task(task_id=task_id, actor="recovery_sweep")
                RUNTIME_RECOVERIES_TOTAL.inc()
                continue
            if action_name == "mark_recoverable_failed":
                RUNTIME_ORPHAN_ENVS.inc()
                await self.recover_task(task_id=task_id, actor="recovery_sweep")
                continue
            await self.events.publish(
                task_id=task_id,
                env_id=env_id,
                attempt=None,
                phase=None,
                event_type="recovery.failed",
                payload=action,
            )

    async def pin_environment(self, *, task_id: int, pinned: bool) -> bool:
        env = self.store.get_environment_by_task(task_id)
        if env is None:
            return False
        env_id = int(env["id"])
        self.store.update_environment(env_id, pinned=pinned)
        await self.events.publish(
            task_id=task_id,
            env_id=env_id,
            attempt=None,
            phase=str(env.get("current_phase") or ""),
            event_type="decision.recorded",
            payload={"action": "pin" if pinned else "unpin"},
        )
        return True

    def get_browser_snapshot(self, task_id: int) -> dict[str, Any]:
        env = self.store.get_environment_by_task(task_id)
        if env is None:
            return {}
        sessions = self.store.list_browser_sessions(task_id)
        live_snapshot = dict(sessions[-1].get("metadata") or {}) if sessions else {}
        merged = dict(live_snapshot)
        if merged:
            return merged

        if sessions:
            persisted = dict(sessions[-1])
            metadata = cast(dict[str, Any], persisted.get("metadata") or {})
            merged = {**metadata, **persisted}
            persisted_status = str(persisted.get("status") or "")
            merged.setdefault("transport", metadata.get("transport"))
            merged.setdefault("runtime_dir", metadata.get("runtime_dir"))
            merged.setdefault("display_id", metadata.get("display_id"))
            merged.setdefault("vnc_port", metadata.get("vnc_port"))
            merged.setdefault("novnc_port", metadata.get("novnc_port"))
            merged["visual_available"] = False
            merged["session_persisted_only"] = True

            if persisted_status not in {"closed", "ended", "stopped", "completed", "unavailable"}:
                merged["last_known_status"] = persisted_status or None
                merged["status"] = "unavailable"
                merged["unavailable_reason"] = (
                    "Browser session metadata was retained, but no live browser is attached "
                    "to the current runtime process."
                )
        return merged

    def get_runtime_readiness(self) -> dict[str, Any]:
        """Return side-effect-free readiness checks for the isolated runtime backend."""
        return self._build_runtime_readiness()

    def _build_runtime_snapshot(self, *, update_metrics: bool) -> dict[str, Any]:
        phase_counts = self.store.count_envs_by_phase()
        if update_metrics:
            for phase, count in phase_counts.items():
                RUNTIME_PHASE_TOTAL.labels(phase=phase).set(count)
        environments = self.store.list_environments()
        active_envs = sum(1 for env in environments if str(env.get("status")) in {"active", "cleaning"})
        retained_envs = sum(1 for env in environments if str(env.get("status")) == "retained")
        stale_before = (datetime.now(UTC) - timedelta(seconds=RUNTIME_STALE_AFTER_SECONDS)).isoformat()
        stale_envs = len(
            [
                env
                for env in environments
                if str(env.get("status")) == "active"
                and env.get("last_heartbeat_at")
                and str(env["last_heartbeat_at"]) < stale_before
            ]
        )
        if update_metrics:
            RUNTIME_ACTIVE_ENVS.set(active_envs)
        browser_sessions = sum(
            1
            for env in environments
            for session in self.store.list_browser_sessions(int(env["task_id"]))
            if str(session.get("status") or "") in {"running", "pending"}
        )
        if update_metrics:
            RUNTIME_PTYS_ACTIVE.set(
                float(
                    sum(
                        1
                        for env in environments
                        for terminal in self.store.list_terminals(int(env["task_id"]))
                        if bool(terminal.get("interactive")) and self._terminal_is_kernel_backed(terminal)
                    )
                )
            )
        attach_sessions_terminal = 0
        attach_sessions_browser = 0
        cleanup_backlog = 0
        recovery_backlog = 0
        total_endpoints = 0
        for env in environments:
            sessions = self.store.list_attach_sessions(int(env["task_id"]))
            attach_sessions_terminal += sum(
                1
                for item in sessions
                if str(item.get("attach_kind")) == "terminal" and str(item.get("status")) == "active"
            )
            attach_sessions_browser += sum(
                1
                for item in sessions
                if str(item.get("attach_kind")) == "browser" and str(item.get("status")) == "active"
            )
            if str(env.get("status")) == "retained" and env.get("retention_expires_at"):
                cleanup_backlog += 1
            if str(env.get("current_phase")) == "recoverable_failed_retained":
                recovery_backlog += 1
            total_endpoints += sum(
                1
                for endpoint in self.store.list_service_endpoints(int(env["task_id"]))
                if str(endpoint.get("status")) == "active"
            )
        if update_metrics:
            RUNTIME_BROWSER_SESSIONS_ACTIVE.set(browser_sessions)
            RUNTIME_VNC_SESSIONS_ACTIVE.set(browser_sessions)
            RUNTIME_TERMINAL_ATTACH_SESSIONS_ACTIVE.set(attach_sessions_terminal)
            RUNTIME_BROWSER_ATTACH_SESSIONS_ACTIVE.set(attach_sessions_browser)
        disk = shutil.disk_usage(self.runtime_root)
        runtime_kernel = self.get_runtime_kernel_health()
        artifact_engine = self.get_artifact_engine_health()
        readiness = self._build_runtime_readiness(runtime_kernel=runtime_kernel)
        return {
            "root_dir": str(self.runtime_root),
            "heartbeat_interval_seconds": RUNTIME_HEARTBEAT_INTERVAL_SECONDS,
            "resource_sample_interval_seconds": RUNTIME_RESOURCE_SAMPLE_INTERVAL_SECONDS,
            "readiness": readiness,
            "active_environments": active_envs,
            "retained_environments": retained_envs,
            "stale_environments": stale_envs,
            "environments_by_phase": phase_counts,
            "queues": self.store.list_runtime_queues(),
            "browser_sessions_active": browser_sessions,
            "attach_sessions_terminal": attach_sessions_terminal,
            "attach_sessions_browser": attach_sessions_browser,
            "cleanup_backlog": cleanup_backlog,
            "recovery_backlog": recovery_backlog,
            "service_endpoints": total_endpoints,
            "runtime_kernel": runtime_kernel,
            "artifact_engine": artifact_engine,
            "runtime_kernel_cutover": readiness.get("runtime_kernel_cutover"),
            "runtime_kernel_operations": readiness.get("runtime_kernel_operations"),
            "internal_rpc": runtime_kernel,
            "disk": {
                "total_bytes": disk.total,
                "used_bytes": disk.used,
                "free_bytes": disk.free,
            },
        }

    def get_runtime_health_snapshot(self) -> dict[str, Any]:
        """Return a pure runtime snapshot for health/readiness handlers."""
        return self._build_runtime_snapshot(update_metrics=False)

    def get_runtime_snapshot(self) -> dict[str, Any]:
        return self._build_runtime_snapshot(update_metrics=True)


_runtime_controller: RuntimeController | None = None


def get_runtime_controller() -> RuntimeController:
    """Return the process-wide runtime controller."""
    global _runtime_controller
    if _runtime_controller is None:
        _runtime_controller = RuntimeController()
    return _runtime_controller
