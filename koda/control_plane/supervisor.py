"""Supervisor process for dynamic agent orchestration."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys
import time
from dataclasses import dataclass
from typing import Any

from aiohttp import ClientSession, ClientTimeout, web

from koda import config
from koda.logging_config import get_logger

from .api import control_plane_auth_middleware, control_plane_error_middleware, setup_control_plane_routes
from .cluster import ClusterClient, ClusterConfig
from .lifecycle_events import consume_lifecycle_signal, get_lifecycle_event
from .manager import RuntimeSnapshot, get_control_plane_manager
from .rate_limit import control_plane_rate_limit_middleware
from .settings import (
    CONTROL_PLANE_BIND,
    CONTROL_PLANE_POLL_INTERVAL_SECONDS,
    CONTROL_PLANE_PORT,
    CONTROL_PLANE_RESTART_GRACE_SECONDS,
    CONTROL_PLANE_STARTUP_GRACE_SECONDS,
    ROOT_DIR,
)

log = get_logger(__name__)

# Probe timeouts for the granular health endpoint. Kept tight so /health stays
# fast under monitoring poll. The endpoint runs probes in parallel via gather.
_HEALTH_PROBE_TIMEOUT_SECONDS: float = 1.0

# Crash-loop detection. A worker that exits N times within a sliding window
# raises a single ``control_plane.worker_crash_loop`` audit event so the
# operator stops finding out from end-user complaints. Constants live at
# module scope so tests can monkey-patch them without env plumbing.
_CRASH_LOOP_WINDOW_SECONDS: float = 300.0
_CRASH_LOOP_THRESHOLD: int = 5

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
        # User-identity vars: required by provider CLIs (claude, codex, gemini)
        # to locate per-user credential stores under $HOME / XDG paths and to
        # speak with macOS/Linux keychains. Stripping these makes the CLI
        # report `loggedIn: false` even when the operator authenticated
        # interactively before launching koda.
        "HOME",
        "USER",
        "LOGNAME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_STATE_HOME",
        "XDG_CACHE_HOME",
    }
)


@dataclass(slots=True)
class _WorkerState:
    agent_id: str
    version: int
    process: asyncio.subprocess.Process
    runtime: RuntimeSnapshot


def _sidecar_targets() -> list[tuple[str, str]]:
    """Return (name, gRPC target) pairs the supervisor should health-probe.

    runtime-kernel speaks over a UDS path; the rest are TCP host:port. The
    target list is read at probe time so env overrides apply without restart.
    """
    return [
        ("security", config.SECURITY_GRPC_TARGET),
        ("memory", config.MEMORY_GRPC_TARGET),
        ("artifact", config.ARTIFACT_GRPC_TARGET),
        ("retrieval", config.RETRIEVAL_GRPC_TARGET),
        ("runtime_kernel", config.RUNTIME_KERNEL_SOCKET),
    ]


async def _probe_sidecar(name: str, target: str) -> dict[str, Any]:
    """Open a gRPC channel to a sidecar and wait for it to become ready.

    Returns latency_ms when the channel becomes ready within the budget;
    otherwise ok=False with the truncated error string. Channel is closed
    even on success to avoid leaking sockets across /health calls.
    """
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
    """Start and reconcile agent workers against desired control-plane state."""

    def __init__(self) -> None:
        self._manager = get_control_plane_manager()
        self._workers: dict[str, _WorkerState] = {}
        self._runner: web.AppRunner | None = None
        self._reconcile_task: asyncio.Task[None] | None = None
        self._closing = False
        # Sliding-window per-agent crash timestamps + a one-shot "already
        # alerted" set so we don't spam the audit log every reconcile while
        # a crash-loop persists.
        self._crash_history: dict[str, list[float]] = {}
        self._crash_loop_alerted: set[str] = set()
        # Phase 2A — cluster mode. ``ClusterConfig.from_env`` defaults to
        # disabled so the legacy "I own everything" behavior is preserved
        # when KODA_CLUSTER_MODE != "cluster".
        self._cluster = ClusterClient(config=ClusterConfig.from_env())
        # Phase A.5 — heartbeat runs in its own task at a tighter
        # cadence than reconcile so a slow reconcile cycle cannot
        # delay heartbeat past ``KODA_CLUSTER_HEARTBEAT_STALE_SECONDS``
        # and let a sibling supervisor steal claims from a healthy
        # process.
        self._heartbeat_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        # Phase 2D — supervisor traces. Same opt-in semantics as the
        # worker (``OTEL_EXPORTER_OTLP_ENDPOINT`` env-driven). Calling
        # init_tracing in ``start`` so the supervisor's spans are
        # routed to the same OTLP collector the workers use.
        from koda.observability import init_tracing

        init_tracing("koda-supervisor")
        self._manager.ensure_seeded()
        app = web.Application(
            middlewares=[
                control_plane_rate_limit_middleware,
                control_plane_error_middleware,
                control_plane_auth_middleware,
            ]
        )
        setup_control_plane_routes(app)
        app.router.add_get("/health", self._health)
        # Phase 2E — blue/green drain hooks. The deploy pipeline POSTs
        # to ``/cluster/drain`` on the OLD supervisor pod when the NEW
        # version becomes healthy; the OLD pod releases its claims on
        # the next heartbeat instead of refreshing them, so the NEW
        # pod immediately picks up ownership without dropping work.
        # ``/cluster/status`` is a read-only diagnostic that surfaces
        # supervisor_id, version, draining flag and the count of agents
        # currently owned.
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
            # A.5 — independent heartbeat task. Decoupled from
            # reconcile so a stuck reconcile cycle does not cost us
            # claim ownership.
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._reconcile_task = asyncio.create_task(self._reconcile_loop())
        log.info("control_plane_supervisor_started", bind=CONTROL_PLANE_BIND, port=CONTROL_PLANE_PORT)

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
        for agent_id in list(self._workers):
            await self._stop_worker(agent_id)
        # Release every claim this supervisor still holds so a sibling
        # picks the work up immediately instead of waiting for the
        # heartbeat to go stale (Phase 2A).
        if self._cluster.config.enabled:
            self._cluster.release_all_for_supervisor()
        if self._runner:
            await self._runner.cleanup()
            self._runner = None

    async def _health(self, request: web.Request) -> web.Response:
        worker_states = list(self._workers.values())
        sidecar_targets = _sidecar_targets()

        worker_probes_task = asyncio.gather(
            *[self._probe_worker(state) for state in worker_states],
            return_exceptions=False,
        )
        sidecar_probes_task = asyncio.gather(
            *[_probe_sidecar(name, target) for name, target in sidecar_targets],
            return_exceptions=False,
        )
        worker_results, sidecar_results = await asyncio.gather(worker_probes_task, sidecar_probes_task)

        workers_payload: list[dict[str, Any]] = []
        for state, probe in zip(worker_states, worker_results, strict=True):
            workers_payload.append(
                {
                    "agent_id": state.agent_id,
                    "version": state.version,
                    "pid": state.process.pid,
                    "health_url": state.runtime.health_url,
                    "alive": probe["alive"],
                    "exit_code": probe["exit_code"],
                    "probe": probe["probe"],
                }
            )

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

    async def _probe_worker(self, state: _WorkerState) -> dict[str, Any]:
        """Probe a worker's health endpoint with a short timeout."""
        if state.process.returncode is not None:
            return {
                "alive": False,
                "exit_code": int(state.process.returncode),
                "probe": None,
            }
        started = time.perf_counter()
        try:
            timeout = ClientTimeout(total=_HEALTH_PROBE_TIMEOUT_SECONDS)
            async with (
                ClientSession(timeout=timeout) as session,
                session.get(state.runtime.health_url) as response,
            ):
                latency_ms = int((time.perf_counter() - started) * 1000)
                payload: Any = None
                with contextlib.suppress(Exception):
                    payload = await response.json()
                active_tasks: int | None = None
                if isinstance(payload, dict):
                    raw = payload.get("active_tasks")
                    if isinstance(raw, (int, float)):
                        active_tasks = int(raw)
                return {
                    "alive": True,
                    "exit_code": None,
                    "probe": {
                        "ok": response.status == 200,
                        "status_code": response.status,
                        "latency_ms": latency_ms,
                        "active_tasks": active_tasks,
                        "error": None,
                    },
                }
        except TimeoutError:
            return {
                "alive": True,
                "exit_code": None,
                "probe": {
                    "ok": False,
                    "status_code": None,
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                    "active_tasks": None,
                    "error": "timeout",
                },
            }
        except Exception as exc:
            return {
                "alive": True,
                "exit_code": None,
                "probe": {
                    "ok": False,
                    "status_code": None,
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                    "active_tasks": None,
                    "error": str(exc)[:200] or exc.__class__.__name__,
                },
            }

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
        """Phase A.5 — independent heartbeat task.

        Refreshes ``cp_agent_assignments.heartbeat_at`` and the
        ``cp_supervisor_runtimes`` row at a tighter cadence than
        reconcile (default: stale_seconds / 3) so a slow reconcile
        cannot push heartbeat past the staleness threshold and let a
        sibling steal claims from a healthy supervisor.
        """
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
            # Sleep up to POLL_INTERVAL but wake up immediately whenever the
            # manager fires a lifecycle signal (pause/activate). Without this
            # the operator would observe a multi-second lag between clicking
            # the button and the runtime actually starting/stopping.
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
        active_ids = {str(agent["id"]) for agent in agents if str(agent["status"]) == "active"}

        # Phase 2A — when the cluster mode flag is on, narrow ``agents``
        # down to the subset this supervisor has claimed in the database.
        # ``claim_agents`` runs the SELECT FOR UPDATE SKIP LOCKED batch
        # before returning so sibling supervisors race for the same
        # candidate set without spawning duplicates.
        if self._cluster.config.enabled:
            # A.5 — heartbeat now runs in its own task; reconcile only
            # claims new agents and does not refresh existing claims
            # so a slow reconcile cannot starve the heartbeat path.
            claimed = self._cluster.claim_agents(sorted(active_ids))
            # Stop any worker we used to own that another supervisor
            # has now claimed (or that we deliberately released).
            for owned_id in list(self._workers):
                if owned_id not in claimed:
                    await self._stop_worker(owned_id)
            agents = [agent for agent in agents if str(agent["id"]) in claimed or str(agent["status"]) != "active"]
            active_ids = {agent_id for agent_id in active_ids if agent_id in claimed}

        for agent in agents:
            agent_id = str(agent["id"])
            state = self._workers.get(agent_id)
            desired_version = int(agent.get("desired_version") or agent.get("applied_version") or 0)
            if str(agent["status"]) != "active":
                # Force-stop without waiting for idle. The pause contract
                # promises immediate interruption of any in-flight action;
                # ``manager.pause_agent`` already rolled back running queue
                # items to 'queued' so the kill is safe.
                if state is not None:
                    await self._stop_worker(agent_id)
                continue
            if desired_version <= 0:
                publish = self._manager.publish_agent(agent_id)
                desired_version = int(publish["version"])
            if state is None:
                await self._start_worker(agent_id, desired_version)
                continue
            if state.process.returncode is not None:
                self._record_worker_crash(agent_id, exit_code=int(state.process.returncode))
                await self._start_worker(agent_id, desired_version)
                continue
            if state.version != desired_version and await self._is_agent_idle(state.runtime.health_url):
                await self._restart_worker(agent_id, desired_version)
        # Sweep stragglers: any worker whose agent is no longer in the
        # active set is force-stopped on this pass too. Idle wait is gone
        # for the same contract reason — the operator already paused.
        for agent_id in list(self._workers):
            if agent_id not in active_ids:
                await self._stop_worker(agent_id)

    async def _start_worker(self, agent_id: str, version: int) -> None:
        runtime = self._manager.build_runtime_snapshot(agent_id, version=version)
        # Build worker env: parent env → snapshot env → system overrides.
        # Snapshot may contain stale values for infrastructure flags that must
        # come from the host environment, so we re-apply critical system vars.
        _SYSTEM_ENV_KEYS = {
            "STATE_BACKEND",
            "POSTGRES_ENABLED",
            "POSTGRES_URL",
            "POSTGRES_DB",
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "KNOWLEDGE_V2_POSTGRES_DSN",
            "KNOWLEDGE_V2_POSTGRES_SCHEMA",
            "KNOWLEDGE_V2_STORAGE_MODE",
            "KNOWLEDGE_V2_S3_BUCKET",
            "KNOWLEDGE_V2_S3_ENDPOINT_URL",
            "KNOWLEDGE_V2_S3_REGION",
            "KNOWLEDGE_V2_S3_ACCESS_KEY_ID",
            "KNOWLEDGE_V2_S3_SECRET_ACCESS_KEY",
            "KNOWLEDGE_V2_S3_PREFIX",
            # gRPC sidecar targets set by the compose orchestrator. Workers must inherit
            # these from the parent env; otherwise the child's koda.config defaults
            # to 127.0.0.1:<port> which only resolves inside the supervisor container,
            # and every RPC fails with "Connection refused".
            "SECURITY_GRPC_TARGET",
            "MEMORY_GRPC_TARGET",
            "ARTIFACT_GRPC_TARGET",
            "RETRIEVAL_GRPC_TARGET",
            "RUNTIME_KERNEL_GRPC_TARGET",
            # Playwright's runtime resolver keys off this env; without it the
            # child defaults to $HOME/.cache/ms-playwright, which is a fresh
            # empty volume in the standard compose. Every browser tool then
            # fails with "Browser is not running. It may not be installed or
            # failed to start." even though the Dockerfile installed
            # Chromium into /var/lib/koda/playwright-browsers.
            "PLAYWRIGHT_BROWSERS_PATH",
        }
        env = {key: value for key, value in os.environ.items() if key in _SAFE_RUNTIME_PARENT_ENV_KEYS}
        env.update(runtime.process_env)
        # Restore system infrastructure vars that the snapshot should not override
        for key in _SYSTEM_ENV_KEYS:
            parent_val = os.environ.get(key)
            if parent_val is not None:
                env[key] = parent_val
        # Override available models based on provider auth mode
        try:
            from koda.provider_models import resolve_api_key_extra_model_ids, resolve_known_general_model_ids

            for provider_id, env_key in [("codex", "CODEX_AVAILABLE_MODELS"), ("claude", "CLAUDE_AVAILABLE_MODELS")]:
                connection = self._manager.get_provider_connection(provider_id)
                auth_mode = str(connection.get("auth_mode") or "").strip().lower()
                base_models = resolve_known_general_model_ids(provider_id)
                if auth_mode == "api_key":
                    extra = resolve_api_key_extra_model_ids(provider_id)
                    base_models = list(dict.fromkeys(base_models + extra))
                if base_models:
                    env[env_key] = ",".join(base_models)
        except Exception:
            pass

        env["AGENT_ID"] = agent_id
        env["_KODA_RUNTIME_BOOTSTRAPPED"] = "1"

        # Phase A.3 — materialize the workspace cgroup BEFORE spawn so
        # the limits are in place when the worker starts allocating;
        # ``place_pid`` moves the freshly-spawned PID into the cgroup
        # so OOM kills the offending workspace, not the supervisor.
        # No-op on macOS / on hosts without cgroup root (soft-fail).
        from koda.control_plane.isolation_runtime import (
            apply_workspace_limits,
            default_limits_from_env,
            ensure_cgroup_v2_root,
            place_pid,
        )

        ensure_cgroup_v2_root()
        workspace_id = self._workspace_id_for_agent(agent_id)
        apply_workspace_limits(default_limits_from_env(workspace_id))

        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "koda",
            "--agent-id",
            agent_id,
            cwd=str(ROOT_DIR),
            env=env,
        )
        if proc.pid:
            place_pid(workspace_id, int(proc.pid))
        await asyncio.sleep(CONTROL_PLANE_STARTUP_GRACE_SECONDS)
        self._workers[agent_id] = _WorkerState(agent_id=agent_id, version=version, process=proc, runtime=runtime)
        self._manager.mark_apply_finished(
            agent_id, version, success=True, details={"event": "worker_started", "pid": proc.pid}
        )
        log.info("control_plane_worker_started", agent_id=agent_id, version=version, pid=proc.pid)

    def _workspace_id_for_agent(self, agent_id: str) -> str:
        """Resolve the workspace_id used for cgroup isolation.

        Today the manager exposes ``workspace_id`` on the agent row
        (Phase 0/1 added the column even though enforcement is
        deferred to Phase 3). When the column is unset / NULL, fall
        back to ``"default"`` so the cgroup directory still exists
        and an operator can attach limits at runtime via
        ``KODA_AGENT_DEFAULT_*`` env vars.
        """
        try:
            row = self._manager.get_agent(agent_id) if hasattr(self._manager, "get_agent") else None
        except Exception:
            row = None
        if isinstance(row, dict):
            ws = row.get("workspace_id")
            if isinstance(ws, str) and ws.strip():
                return ws.strip()
        return "default"

    def _record_worker_crash(self, agent_id: str, *, exit_code: int) -> None:
        """Track this crash in a sliding window; alert once if it loops.

        On every observed crash we append ``time.monotonic()`` to the
        agent's history list, drop entries older than the window, and emit
        a structured ``control_plane.worker_crash_loop`` audit row the
        first time the count crosses the threshold. The "alerted" flag
        clears automatically once enough time passes without a new crash,
        so subsequent loop episodes still produce one alert each.
        """
        from koda.control_plane.audit import record_audit_event

        now = time.monotonic()
        history = self._crash_history.setdefault(agent_id, [])
        history.append(now)
        cutoff = now - _CRASH_LOOP_WINDOW_SECONDS
        # Trim left in place. List is small (capped by threshold + a few),
        # so a slice rebuild is fine.
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
            # Below threshold — re-arm so a future loop within the window
            # will alert again instead of staying silent.
            self._crash_loop_alerted.discard(agent_id)

    async def _stop_worker(self, agent_id: str) -> None:
        state = self._workers.pop(agent_id, None)
        # Operator-driven stop clears crash-loop bookkeeping so a future
        # restart starts fresh; otherwise paused-then-resumed agents would
        # inherit stale crash history that no longer reflects reality.
        self._crash_history.pop(agent_id, None)
        self._crash_loop_alerted.discard(agent_id)
        if state is None:
            return
        # Clean up MCP servers for this agent
        try:
            from koda.services.mcp_manager import mcp_server_manager

            await mcp_server_manager.stop_all_for_agent(agent_id)
        except Exception:
            pass
        process = state.process
        if process.returncode is None:
            process.send_signal(signal.SIGINT)
            try:
                await asyncio.wait_for(process.wait(), timeout=CONTROL_PLANE_RESTART_GRACE_SECONDS)
            except TimeoutError:
                process.kill()
                await process.wait()
        log.info("control_plane_worker_stopped", agent_id=agent_id, version=state.version, pid=process.pid)

    async def _restart_worker(self, agent_id: str, version: int) -> None:
        self._manager.mark_apply_started(agent_id, version)
        await self._stop_worker(agent_id)
        await self._start_worker(agent_id, version)

    async def _is_agent_idle(self, health_url: str) -> bool:
        try:
            timeout = ClientTimeout(total=5)
            async with ClientSession(timeout=timeout) as session, session.get(health_url) as response:
                if response.status != 200:
                    return False
                payload = await response.json()
                return int(payload.get("active_tasks") or 0) == 0
        except Exception:
            return False


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
