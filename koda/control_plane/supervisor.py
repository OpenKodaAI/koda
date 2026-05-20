"""Supervisor process: declarative agent worker reconciliation.

The supervisor builds the desired set of `AgentWorkerSpec` from the
control-plane database and sends it to the Rust runtime-kernel via
`RuntimeKernelLink.ensure_agent_workers`. The kernel is the sole
OS-level parent of agent workers, so a SIGKILL'd supervisor cannot
leave orphans holding worker health ports.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys
import time
from typing import Any
from urllib.parse import urlparse

from aiohttp import web

from koda import config
from koda.logging_config import get_logger

from .api import (
    control_plane_auth_middleware,
    control_plane_error_middleware,
    setup_control_plane_routes,
)
from .cluster import ClusterClient, ClusterConfig
from .lifecycle_events import consume_lifecycle_signal, get_lifecycle_event
from .manager import RuntimeSnapshot, get_control_plane_manager
from .rate_limit import control_plane_rate_limit_middleware
from .runtime_kernel_link import (
    AgentWorkerSpec,
    AgentWorkerState,
    AgentWorkerStatus,
    RuntimeKernelLink,
)
from .settings import (
    CONTROL_PLANE_BIND,
    CONTROL_PLANE_POLL_INTERVAL_SECONDS,
    CONTROL_PLANE_PORT,
    ROOT_DIR,
)

log = get_logger(__name__)

_HEALTH_PROBE_TIMEOUT_SECONDS: float = 1.0

# Module-scoped so tests can monkey-patch.
_CRASH_LOOP_WINDOW_SECONDS: float = 300.0
_CRASH_LOOP_THRESHOLD: int = 5


# Forced from parent env onto each worker's spec.environment so a stale
# manager snapshot can never override the host's infrastructure addresses.
_SYSTEM_ENV_KEYS = frozenset(
    {
        "STATE_BACKEND",
        "INTER_AGENT_BUS_BACKEND",
        "INTER_AGENT_ENABLED",
        "POSTGRES_ENABLED",
        "POSTGRES_URL",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "SQUAD_BUS_LISTEN_ENABLED",
        "SQUAD_INBOX_MAX_DELIVERY_ATTEMPTS",
        "SQUAD_INBOX_MAX_DEPTH",
        "SQUAD_POLL_INTERVAL_S",
        "SQUADS_ENABLED",
        "KNOWLEDGE_V2_POSTGRES_DSN",
        "KNOWLEDGE_V2_POSTGRES_SCHEMA",
        "KNOWLEDGE_V2_STORAGE_MODE",
        "KNOWLEDGE_V2_S3_BUCKET",
        "KNOWLEDGE_V2_S3_ENDPOINT_URL",
        "KNOWLEDGE_V2_S3_REGION",
        "KNOWLEDGE_V2_S3_ACCESS_KEY_ID",
        "KNOWLEDGE_V2_S3_SECRET_ACCESS_KEY",
        "KNOWLEDGE_V2_S3_PREFIX",
        "SECURITY_GRPC_TARGET",
        "MEMORY_GRPC_TARGET",
        "ARTIFACT_GRPC_TARGET",
        "RETRIEVAL_GRPC_TARGET",
        "RUNTIME_KERNEL_GRPC_TARGET",
        "RUNTIME_KERNEL_SOCKET",
        "RUNTIME_KERNEL_ROOT",
        "RUNTIME_EPHEMERAL_ROOT",
        "STATE_ROOT_DIR",
        "ARTIFACT_STORE_DIR",
        "PLAYWRIGHT_BROWSERS_PATH",
    }
)

# Anything outside this set is dropped from the parent env before spawn.
_SAFE_RUNTIME_PARENT_ENV_KEYS = frozenset(
    {
        "PATH",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TZ",
        "TMPDIR",
        "TMP",
        "TEMP",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "ALL_PROXY",
        # Provider CLIs (claude, codex, gemini) need these to find per-user
        # credential stores under $HOME/XDG and to speak with the keychain.
        "HOME",
        "USER",
        "LOGNAME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_STATE_HOME",
        "XDG_CACHE_HOME",
    }
)

_LOOPBACK_KERNEL_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


def _host_from_grpc_target(raw_target: str) -> str | None:
    raw = str(raw_target or "").strip()
    if not raw or raw.startswith(("unix:", "unix://")):
        return None
    if raw.startswith("dns:///"):
        raw = raw.removeprefix("dns:///")
    if "://" in raw:
        parsed = urlparse(raw)
        return parsed.hostname
    if raw.startswith("[") and "]" in raw:
        return raw[1 : raw.index("]")]
    return raw.rsplit(":", 1)[0].strip() or None


def _kernel_workers_need_network_bind(raw_target: str) -> bool:
    host = _host_from_grpc_target(raw_target)
    return bool(host and host.lower() not in _LOOPBACK_KERNEL_HOSTS)


def _sidecar_targets() -> list[tuple[str, str]]:
    """Return (name, gRPC target) pairs the supervisor health-probes."""
    return [
        ("security", config.SECURITY_GRPC_TARGET),
        ("memory", config.MEMORY_GRPC_TARGET),
        ("artifact", config.ARTIFACT_GRPC_TARGET),
        ("retrieval", config.RETRIEVAL_GRPC_TARGET),
        ("runtime_kernel", config.RUNTIME_KERNEL_SOCKET),
    ]


async def _probe_sidecar(name: str, target: str) -> dict[str, Any]:
    """Open a gRPC channel to a sidecar and wait for it to become ready."""
    from koda.internal_rpc.common import create_grpc_channel, resolve_grpc_target

    resolved_target, _ = resolve_grpc_target(target)
    started = time.perf_counter()
    channel: Any = None
    try:
        channel = create_grpc_channel(resolved_target, async_channel=True)
        await asyncio.wait_for(channel.channel_ready(), timeout=_HEALTH_PROBE_TIMEOUT_SECONDS)
        return {
            "name": name,
            "target": resolved_target,
            "ok": True,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "error": None,
        }
    except TimeoutError:
        return {
            "name": name,
            "target": resolved_target,
            "ok": False,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "error": "timeout",
        }
    except Exception as exc:
        return {
            "name": name,
            "target": resolved_target,
            "ok": False,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "error": str(exc)[:200] or exc.__class__.__name__,
        }
    finally:
        if channel is not None:
            with contextlib.suppress(Exception):
                await channel.close()


class ControlPlaneSupervisor:
    """Reconciles agent workers by delegating spawn/kill to the kernel."""

    def __init__(self, *, link: RuntimeKernelLink | None = None) -> None:
        self._manager = get_control_plane_manager()
        self._runner: web.AppRunner | None = None
        self._reconcile_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._closing = False
        self._cluster = ClusterClient(config=ClusterConfig.from_env())
        self._link = link if link is not None else RuntimeKernelLink()
        self._statuses: dict[str, AgentWorkerStatus] = {}
        self._health_urls: dict[str, str] = {}
        self._crash_history: dict[str, list[float]] = {}
        self._crash_loop_alerted: set[str] = set()
        self._publish_failure_alerted: set[str] = set()

    async def start(self) -> None:
        from koda.observability import init_tracing

        init_tracing("koda-supervisor")
        self._manager.ensure_seeded()
        await self._link.start()

        app = web.Application(
            middlewares=[
                control_plane_rate_limit_middleware,
                control_plane_error_middleware,
                control_plane_auth_middleware,
            ]
        )
        setup_control_plane_routes(app)
        app.router.add_get("/health", self._health)
        app.router.add_get("/cluster/status", self._cluster_status)
        app.router.add_post("/cluster/drain", self._cluster_drain)
        app.router.add_post("/cluster/undrain", self._cluster_undrain)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, CONTROL_PLANE_BIND, CONTROL_PLANE_PORT)
        await site.start()
        if self._cluster.config.enabled:
            registered = self._cluster.register()
            log.info(
                "control_plane_cluster_mode",
                supervisor_id=self._cluster.config.supervisor_id,
                version=self._cluster.config.version,
                capacity=self._cluster.config.capacity,
                registered=registered,
            )
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._reconcile_task = asyncio.create_task(self._reconcile_loop())
        log.info(
            "control_plane_supervisor_started",
            bind=CONTROL_PLANE_BIND,
            port=CONTROL_PLANE_PORT,
            kernel_target=self._link.target,
        )

    async def stop(self) -> None:
        self._closing = True
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task
        if self._reconcile_task:
            self._reconcile_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reconcile_task
        # Empty desired set tells the kernel to drain. Safe whether the
        # kernel survives this stop (rolling upgrade) or not.
        with contextlib.suppress(Exception):
            await self._link.ensure_agent_workers([])
        await self._link.stop()
        if self._cluster.config.enabled:
            self._cluster.release_all_for_supervisor()
        if self._runner:
            await self._runner.cleanup()
            self._runner = None

    async def _health(self, _request: web.Request) -> web.Response:
        statuses = list(self._statuses.values())
        sidecar_targets = _sidecar_targets()
        sidecar_results = await asyncio.gather(
            *[_probe_sidecar(name, target) for name, target in sidecar_targets],
        )

        workers_payload: list[dict[str, Any]] = self._render_worker_payload(statuses)

        workers_alive = sum(1 for w in workers_payload if w["alive"])
        workers_unhealthy = sum(
            1 for w in workers_payload if (not w["alive"]) or (w["probe"] is not None and not w["probe"]["ok"])
        )
        sidecars_unhealthy = sum(1 for s in sidecar_results if not s["ok"])

        overall = "healthy"
        if workers_unhealthy > 0 or sidecars_unhealthy > 0:
            overall = "degraded"

        return web.json_response(
            {
                "status": overall,
                "workers": workers_payload,
                "sidecars": sidecar_results,
                "summary": {
                    "workers_total": len(workers_payload),
                    "workers_alive": workers_alive,
                    "workers_unhealthy": workers_unhealthy,
                    "sidecars_total": len(sidecar_results),
                    "sidecars_unhealthy": sidecars_unhealthy,
                },
            }
        )

    def _render_worker_payload(self, statuses: list[AgentWorkerStatus]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for status in statuses:
            alive = status.state in (
                AgentWorkerState.STARTING,
                AgentWorkerState.RUNNING,
                AgentWorkerState.UNHEALTHY,
            )
            probe: dict[str, Any] | None
            if status.state == AgentWorkerState.RUNNING:
                probe = {
                    "ok": True,
                    "status_code": 200,
                    "latency_ms": None,
                    "active_tasks": None,
                    "error": None,
                }
            elif status.state == AgentWorkerState.UNHEALTHY:
                probe = {
                    "ok": False,
                    "status_code": None,
                    "latency_ms": None,
                    "active_tasks": None,
                    "error": "unhealthy",
                }
            elif status.state == AgentWorkerState.STARTING:
                probe = {
                    "ok": False,
                    "status_code": None,
                    "latency_ms": None,
                    "active_tasks": None,
                    "error": "starting",
                }
            else:
                probe = None
            out.append(
                {
                    "agent_id": status.agent_id,
                    "version": status.version,
                    "pid": status.pid,
                    "health_url": self._health_urls.get(status.agent_id, ""),
                    "alive": alive,
                    "exit_code": status.exit_code if not alive else None,
                    "probe": probe,
                }
            )
        return out

    async def _cluster_status(self, _request: web.Request) -> web.Response:
        if not self._cluster.config.enabled:
            return web.json_response({"enabled": False, "reason": "KODA_CLUSTER_MODE != 'cluster'"})
        owned = sorted(self._cluster.list_owned_agents())
        return web.json_response(
            {
                "enabled": True,
                "supervisor_id": self._cluster.config.supervisor_id,
                "version": self._cluster.config.version,
                "host": self._cluster.config.host,
                "capacity": self._cluster.config.capacity,
                "draining": self._cluster.is_draining(),
                "owned_agents": owned,
                "owned_count": len(owned),
            }
        )

    async def _cluster_drain(self, _request: web.Request) -> web.Response:
        if not self._cluster.config.enabled:
            return web.json_response(
                {"applied": False, "reason": "cluster_mode_disabled"},
                status=409,
            )
        applied = self._cluster.set_draining(True)
        log.info(
            "control_plane_cluster_drain_requested",
            supervisor_id=self._cluster.config.supervisor_id,
            applied=applied,
        )
        return web.json_response({"applied": applied, "draining": True})

    async def _cluster_undrain(self, _request: web.Request) -> web.Response:
        if not self._cluster.config.enabled:
            return web.json_response(
                {"applied": False, "reason": "cluster_mode_disabled"},
                status=409,
            )
        applied = self._cluster.set_draining(False)
        log.info(
            "control_plane_cluster_undrain_requested",
            supervisor_id=self._cluster.config.supervisor_id,
            applied=applied,
        )
        return web.json_response({"applied": applied, "draining": False})

    async def _heartbeat_loop(self) -> None:
        interval = max(2.0, float(self._cluster.config.heartbeat_stale_seconds) / 3.0)
        while not self._closing:
            try:
                self._cluster.heartbeat()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("control_plane_heartbeat_error")
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                raise

    async def _reconcile_loop(self) -> None:
        while not self._closing:
            try:
                await self._reconcile_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("control_plane_reconcile_error")
            event = get_lifecycle_event()
            if event is None:
                await asyncio.sleep(CONTROL_PLANE_POLL_INTERVAL_SECONDS)
                continue
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(
                    event.wait(),
                    timeout=CONTROL_PLANE_POLL_INTERVAL_SECONDS,
                )
            consume_lifecycle_signal()

    async def _reconcile_once(self) -> None:
        agents = self._manager.list_agents()
        active_ids = {str(a["id"]) for a in agents if str(a["status"]) == "active"}

        if self._cluster.config.enabled:
            claimed = self._cluster.claim_agents(sorted(active_ids))
            agents = [a for a in agents if str(a["id"]) in claimed]
            active_ids &= claimed

        # Paused / disabled agents are excluded so the kernel terminates
        # whatever workers it had for them.
        desired_specs: list[AgentWorkerSpec] = []
        for agent in agents:
            agent_id = str(agent["id"])
            if str(agent["status"]) != "active":
                continue
            desired_version = int(agent.get("desired_version") or agent.get("applied_version") or 0)
            if desired_version <= 0:
                try:
                    desired_version = int(self._manager.publish_agent(agent_id)["version"])
                    self._publish_failure_alerted.discard(agent_id)
                except Exception as exc:
                    if agent_id not in self._publish_failure_alerted:
                        log.warning(
                            "control_plane_publish_agent_error",
                            agent_id=agent_id,
                            error=str(exc)[:500],
                        )
                        self._publish_failure_alerted.add(agent_id)
                    continue
            try:
                runtime = self._manager.build_runtime_snapshot(agent_id, version=desired_version)
            except Exception:
                log.exception("control_plane_build_runtime_snapshot_error", agent_id=agent_id)
                continue
            spec = self._build_spec(agent_id, desired_version, runtime)
            desired_specs.append(spec)
            self._health_urls[agent_id] = runtime.health_url

        outcome = await self._link.ensure_agent_workers(desired_specs)
        new_statuses = {status.agent_id: status for status in outcome.current}

        for agent_id, status in new_statuses.items():
            previous = self._statuses.get(agent_id)
            if previous is None or previous.state != status.state:
                self._observe_state_transition(agent_id, status)

        for stale in set(self._statuses) - set(new_statuses):
            self._statuses.pop(stale, None)
            self._health_urls.pop(stale, None)
        self._statuses = new_statuses

        if outcome.spawned or outcome.terminated or outcome.restarted:
            log.info(
                "control_plane_reconcile_outcome",
                spawned=outcome.spawned,
                terminated=outcome.terminated,
                restarted=outcome.restarted,
                unchanged=outcome.unchanged,
                tracked=len(new_statuses),
            )

    def _build_spec(
        self,
        agent_id: str,
        version: int,
        runtime: RuntimeSnapshot,
    ) -> AgentWorkerSpec:
        env: dict[str, str] = {key: value for key, value in os.environ.items() if key in _SAFE_RUNTIME_PARENT_ENV_KEYS}
        env.update(runtime.process_env)
        for key in _SYSTEM_ENV_KEYS:
            parent_val = os.environ.get(key)
            if parent_val is not None:
                env[key] = parent_val
        try:
            from koda.provider_models import (
                resolve_api_key_extra_model_ids,
                resolve_known_general_model_ids,
            )

            for provider_id, env_key in (
                ("codex", "CODEX_AVAILABLE_MODELS"),
                ("claude", "CLAUDE_AVAILABLE_MODELS"),
            ):
                connection = self._manager.get_provider_connection(provider_id)
                auth_mode = str(connection.get("auth_mode") or "").strip().lower()
                base_models = resolve_known_general_model_ids(provider_id)
                if auth_mode == "api_key":
                    extra = resolve_api_key_extra_model_ids(provider_id)
                    base_models = list(dict.fromkeys(base_models + extra))
                if base_models:
                    env[env_key] = ",".join(base_models)
        except Exception:
            log.debug("control_plane_provider_models_resolve_skipped", exc_info=True)
        env["AGENT_ID"] = agent_id
        env["_KODA_RUNTIME_BOOTSTRAPPED"] = "1"
        if _kernel_workers_need_network_bind(self._link.target) and not env.get("HEALTH_BIND"):
            env["HEALTH_BIND"] = "0.0.0.0"

        health_port, health_path = _split_health_url(runtime.health_url)
        workspace_id = self._workspace_id_for_agent(agent_id)
        return AgentWorkerSpec(
            agent_id=agent_id,
            version=version,
            command=os.environ.get("KODA_PYTHON") or sys.executable,
            args=("-m", "koda", "--agent-id", agent_id),
            working_directory=str(ROOT_DIR),
            environment=env,
            health_port=health_port,
            health_path=health_path,
            workspace_id=workspace_id,
        )

    def _workspace_id_for_agent(self, agent_id: str) -> str:
        try:
            row = self._manager.get_agent(agent_id) if hasattr(self._manager, "get_agent") else None
        except Exception:
            row = None
        if isinstance(row, dict):
            ws = row.get("workspace_id")
            if isinstance(ws, str) and ws.strip():
                return ws.strip()
        return "default"

    def _observe_state_transition(self, agent_id: str, status: AgentWorkerStatus) -> None:
        if status.state == AgentWorkerState.RUNNING:
            with contextlib.suppress(Exception):
                self._manager.mark_apply_finished(
                    agent_id,
                    status.version,
                    success=True,
                    details={"event": "worker_running", "pid": status.pid},
                )
            self._crash_loop_alerted.discard(agent_id)
        elif status.state == AgentWorkerState.SPAWN_BLOCKED:
            log.error(
                "control_plane_worker_spawn_blocked",
                agent_id=agent_id,
                reason=status.spawn_blocked_reason,
            )
            with contextlib.suppress(Exception):
                self._manager.mark_apply_finished(
                    agent_id,
                    status.version,
                    success=False,
                    details={
                        "event": "worker_spawn_blocked",
                        "reason": status.spawn_blocked_reason,
                    },
                )
        elif status.state == AgentWorkerState.EXITED:
            self._record_worker_crash(agent_id, exit_code=status.exit_code)
        elif status.state == AgentWorkerState.TERMINATED:
            self._crash_history.pop(agent_id, None)
            self._crash_loop_alerted.discard(agent_id)

    def _record_worker_crash(self, agent_id: str, *, exit_code: int) -> None:
        # Sliding-window crash-loop detector. Emits one audit row the first
        # time a worker crashes _CRASH_LOOP_THRESHOLD times in the window.
        from koda.control_plane.audit import record_audit_event

        now = time.monotonic()
        history = self._crash_history.setdefault(agent_id, [])
        history.append(now)
        cutoff = now - _CRASH_LOOP_WINDOW_SECONDS
        self._crash_history[agent_id] = [t for t in history if t >= cutoff]
        recent = self._crash_history[agent_id]

        if len(recent) >= _CRASH_LOOP_THRESHOLD:
            if agent_id not in self._crash_loop_alerted:
                self._crash_loop_alerted.add(agent_id)
                log.warning(
                    "control_plane_worker_crash_loop",
                    agent_id=agent_id,
                    crashes=len(recent),
                    window_seconds=_CRASH_LOOP_WINDOW_SECONDS,
                    last_exit_code=exit_code,
                )
                with contextlib.suppress(Exception):
                    record_audit_event(
                        agent_id,
                        event_type="control_plane.worker_crash_loop",
                        details={
                            "agent_id": agent_id,
                            "crashes": len(recent),
                            "window_seconds": _CRASH_LOOP_WINDOW_SECONDS,
                            "threshold": _CRASH_LOOP_THRESHOLD,
                            "last_exit_code": exit_code,
                        },
                    )
        else:
            self._crash_loop_alerted.discard(agent_id)


def _split_health_url(url: str) -> tuple[int, str]:
    # Returns (0, "/health") when the URL has no explicit port — the kernel
    # treats that as "skip bind probe + health monitor".
    from urllib.parse import urlparse

    if not url:
        return 0, "/health"
    try:
        parsed = urlparse(url)
    except Exception:
        return 0, "/health"
    if not parsed.scheme:
        return 0, "/health"
    port = parsed.port or 0
    path = parsed.path or "/health"
    return port, path


async def run_supervisor() -> None:
    supervisor = ControlPlaneSupervisor()
    await supervisor.start()
    stop_event = asyncio.Event()

    def _stop() -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for signame in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(signame, _stop)

    await stop_event.wait()
    await supervisor.stop()
