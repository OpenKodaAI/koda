"""Supervisor process for dynamic agent orchestration."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys
from dataclasses import dataclass

from aiohttp import ClientSession, ClientTimeout, web

from koda.logging_config import get_logger

from .api import control_plane_auth_middleware, control_plane_error_middleware, setup_control_plane_routes
from .manager import RuntimeSnapshot, get_control_plane_manager
from .settings import (
    CONTROL_PLANE_BIND,
    CONTROL_PLANE_POLL_INTERVAL_SECONDS,
    CONTROL_PLANE_PORT,
    CONTROL_PLANE_RESTART_GRACE_SECONDS,
    CONTROL_PLANE_STARTUP_GRACE_SECONDS,
    ROOT_DIR,
)

log = get_logger(__name__)


@dataclass(slots=True)
class _WorkerState:
    agent_id: str
    version: int
    process: asyncio.subprocess.Process
    runtime: RuntimeSnapshot


class ControlPlaneSupervisor:
    """Start and reconcile agent workers against desired control-plane state."""

    def __init__(self) -> None:
        self._manager = get_control_plane_manager()
        self._workers: dict[str, _WorkerState] = {}
        self._runner: web.AppRunner | None = None
        self._reconcile_task: asyncio.Task[None] | None = None
        self._closing = False

    async def start(self) -> None:
        self._manager.ensure_seeded()
        app = web.Application(middlewares=[control_plane_error_middleware, control_plane_auth_middleware])
        setup_control_plane_routes(app)
        app.router.add_get("/health", self._health)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, CONTROL_PLANE_BIND, CONTROL_PLANE_PORT)
        await site.start()
        self._reconcile_task = asyncio.create_task(self._reconcile_loop())
        log.info("control_plane_supervisor_started", bind=CONTROL_PLANE_BIND, port=CONTROL_PLANE_PORT)

    async def stop(self) -> None:
        self._closing = True
        if self._reconcile_task:
            self._reconcile_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reconcile_task
        for agent_id in list(self._workers):
            await self._stop_worker(agent_id)
        if self._runner:
            await self._runner.cleanup()
            self._runner = None

    async def _health(self, request: web.Request) -> web.Response:
        return web.json_response(
            {
                "status": "healthy",
                "workers": [
                    {
                        "agent_id": state.agent_id,
                        "version": state.version,
                        "pid": state.process.pid,
                        "health_url": state.runtime.health_url,
                    }
                    for state in self._workers.values()
                ],
            }
        )

    async def _reconcile_loop(self) -> None:
        while not self._closing:
            try:
                await self._reconcile_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("control_plane_reconcile_error")
            await asyncio.sleep(CONTROL_PLANE_POLL_INTERVAL_SECONDS)

    async def _reconcile_once(self) -> None:
        agents = self._manager.list_agents()
        active_ids = {str(agent["id"]) for agent in agents if str(agent["status"]) == "active"}
        for agent in agents:
            agent_id = str(agent["id"])
            state = self._workers.get(agent_id)
            desired_version = int(agent.get("desired_version") or agent.get("applied_version") or 0)
            if str(agent["status"]) != "active":
                if state and await self._is_agent_idle(state.runtime.health_url):
                    await self._stop_worker(agent_id)
                continue
            if desired_version <= 0:
                publish = self._manager.publish_agent(agent_id)
                desired_version = int(publish["version"])
            if state is None:
                await self._start_worker(agent_id, desired_version)
                continue
            if state.process.returncode is not None:
                await self._start_worker(agent_id, desired_version)
                continue
            if state.version != desired_version and await self._is_agent_idle(state.runtime.health_url):
                await self._restart_worker(agent_id, desired_version)
        for agent_id in list(self._workers):
            if agent_id not in active_ids and await self._is_agent_idle(self._workers[agent_id].runtime.health_url):
                await self._stop_worker(agent_id)

    async def _start_worker(self, agent_id: str, version: int) -> None:
        runtime = self._manager.build_runtime_snapshot(agent_id, version=version)
        env = dict(os.environ)
        env.update(runtime.env)
        env["AGENT_ID"] = agent_id
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "koda",
            "--agent-id",
            agent_id,
            cwd=str(ROOT_DIR),
            env=env,
        )
        await asyncio.sleep(CONTROL_PLANE_STARTUP_GRACE_SECONDS)
        self._workers[agent_id] = _WorkerState(agent_id=agent_id, version=version, process=proc, runtime=runtime)
        self._manager.mark_apply_finished(
            agent_id, version, success=True, details={"event": "worker_started", "pid": proc.pid}
        )
        log.info("control_plane_worker_started", agent_id=agent_id, version=version, pid=proc.pid)

    async def _stop_worker(self, agent_id: str) -> None:
        state = self._workers.pop(agent_id, None)
        if state is None:
            return
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
