"""MCP server lifecycle manager – start, stop, health-check, restart, idle TTL."""

from __future__ import annotations

import asyncio
import os
import time

from koda.logging_config import get_logger
from koda.services.mcp_client import (
    HttpSseTransport,
    McpSession,
    McpToolDefinition,
    McpTransport,
    StdioTransport,
)
from koda.services.mcp_isolation import (
    IsolationConstraints,
    IsolationStrategy,
    select_isolation_strategy,
)

logger = get_logger(__name__)

# Background-loop tunables (configurable via env for ops).
_HEALTH_CHECK_INTERVAL_SECONDS = float(os.environ.get("KODA_MCP_HEALTH_INTERVAL", "60"))
_IDLE_TIMEOUT_SECONDS = float(os.environ.get("KODA_MCP_IDLE_TIMEOUT", "900"))
_RESTART_BACKOFF_SCHEDULE: tuple[float, ...] = (1.0, 2.0, 4.0, 8.0, 16.0)
_MAX_RESTART_ATTEMPTS = len(_RESTART_BACKOFF_SCHEDULE)


# Single server instance


class McpServerInstance:
    """One running MCP server, scoped to a specific agent connection."""

    def __init__(
        self,
        server_key: str,
        agent_id: str,
        transport_type: str,
        *,
        command: list[str] | None = None,
        url: str | None = None,
        env: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        isolation_profile: str | None = None,
        isolation_constraints: IsolationConstraints | None = None,
    ) -> None:
        self._server_key = server_key
        self._agent_id = agent_id
        self._transport_type = transport_type
        self._command = command or []
        self._url = url
        self._env = env
        self._headers = headers
        self._isolation_profile = isolation_profile
        self._isolation_constraints = isolation_constraints or IsolationConstraints()
        self._isolation_strategy: IsolationStrategy | None = None

        self._session: McpSession | None = None
        self._transport: McpTransport | None = None
        self._cached_tools: list[McpToolDefinition] = []
        self._cached_tools_at: float = 0.0
        self._started: bool = False
        self._last_used_at: float = time.time()
        self._restart_attempts: int = 0
        self._unhealthy_since: float | None = None

    # -- properties ----------------------------------------------------------

    @property
    def server_key(self) -> str:
        return self._server_key

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def session(self) -> McpSession | None:
        return self._session

    @property
    def cached_tools(self) -> list[McpToolDefinition]:
        return list(self._cached_tools)

    @property
    def cached_tools_at(self) -> float:
        return self._cached_tools_at

    @property
    def started(self) -> bool:
        return self._started

    @property
    def last_used_at(self) -> float:
        return self._last_used_at

    @property
    def restart_attempts(self) -> int:
        return self._restart_attempts

    @property
    def is_unhealthy(self) -> bool:
        return self._unhealthy_since is not None

    def bump_restart_attempt(self) -> None:
        self._restart_attempts += 1

    def mark_unhealthy(self) -> None:
        self._unhealthy_since = time.time()

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        """Create transport, start session, initialize, and cache tools.

        For stdio transports, wraps the argv in the OS-level sandbox returned
        by :func:`select_isolation_strategy`. HTTP-SSE is unaffected (no
        subprocess).
        """
        if self._transport_type == "stdio":
            if not self._command:
                raise ValueError("stdio transport requires a command")
            command, env = self._isolated_command(self._command, self._env or {})
            transport = StdioTransport(command[0], args=command[1:], env=env or None)
            await transport.start()
            self._transport = transport
        elif self._transport_type == "http_sse":
            if not self._url:
                raise ValueError("http_sse transport requires a url")
            self._transport = HttpSseTransport(self._url, headers=self._headers)
        else:
            raise ValueError(f"unknown transport type: {self._transport_type}")

        self._session = McpSession(self._transport)
        await self._session.initialize()
        self._cached_tools = await self._session.list_tools()
        self._cached_tools_at = time.time()
        self._started = True
        self._restart_attempts = 0
        self._unhealthy_since = None
        self._last_used_at = time.time()
        logger.info(
            "mcp_server_started",
            server_key=self._server_key,
            agent_id=self._agent_id,
            transport=self._transport_type,
            tools=len(self._cached_tools),
            isolation=self._isolation_strategy.kind if self._isolation_strategy else "none",
        )

    def _isolated_command(self, command: list[str], env: dict[str, str]) -> tuple[list[str], dict[str, str]]:
        """Apply the OS-native sandbox wrapper (when available)."""
        strategy = select_isolation_strategy(
            catalog_profile=self._isolation_profile,
            env_override=os.environ.get("KODA_MCP_ISOLATION"),
        )
        self._isolation_strategy = strategy
        return strategy.wrap(command, env, self._isolation_constraints)

    def touch(self) -> None:
        """Mark this instance as recently active (resets idle timer)."""
        self._last_used_at = time.time()

    async def stop(self) -> None:
        """Graceful shutdown of the transport."""
        if self._transport is not None:
            try:
                await self._transport.close()
            except Exception:
                logger.warning(
                    "mcp_server_stop_error",
                    server_key=self._server_key,
                    agent_id=self._agent_id,
                )
        self._session = None
        self._transport = None
        self._started = False
        self._cached_tools = []
        self._cached_tools_at = 0.0
        logger.info(
            "mcp_server_stopped",
            server_key=self._server_key,
            agent_id=self._agent_id,
        )

    async def restart(self) -> None:
        """Stop then start the server instance."""
        await self.stop()
        await self.start()

    async def health_check(self) -> bool:
        """Ping the server with a 5-second timeout.  Returns False if not started."""
        if not self._started or self._session is None:
            return False
        return await self._session.ping()

    async def refresh_tools(self) -> list[McpToolDefinition]:
        """Re-query tools/list and update the cache."""
        if self._session is None:
            raise RuntimeError("session not started")
        self._cached_tools = await self._session.list_tools()
        self._cached_tools_at = time.time()
        return list(self._cached_tools)


# Global registry


class McpServerManager:
    """Global registry of MCP server instances, keyed by agent_id:server_key.

    Adds lifecycle management on top of :class:`McpServerInstance`:

    - **Health checks** every ``KODA_MCP_HEALTH_INTERVAL`` seconds (default 60).
    - **Restart on crash** with exponential backoff (1s/2s/4s/8s/16s, max 5
      attempts). After exhaustion, the instance is quarantined and surfaces
      ``unhealthy=True`` so the UI can mark it ``needs_attention``.
    - **Idle timeout**: instances inactive for ``KODA_MCP_IDLE_TIMEOUT``
      seconds (default 900 = 15 min) are stopped automatically; the next
      tool call lazily re-spawns them via ``ensure_started``.
    """

    def __init__(self) -> None:
        self._instances: dict[str, McpServerInstance] = {}
        self._lock = asyncio.Lock()
        self._loops_started: bool = False
        self._health_task: asyncio.Task[None] | None = None
        self._idle_task: asyncio.Task[None] | None = None

    @property
    def active_instances(self) -> dict[str, McpServerInstance]:
        """Return a snapshot of all registered instances (keyed ``agent_id:server_key``)."""
        return dict(self._instances)

    @staticmethod
    def _key(server_key: str, agent_id: str) -> str:
        return f"{agent_id}:{server_key}"

    def get_instance(self, server_key: str, agent_id: str) -> McpServerInstance | None:
        """Return an existing instance or ``None``."""
        return self._instances.get(self._key(server_key, agent_id))

    async def ensure_started(
        self,
        server_key: str,
        agent_id: str,
        *,
        transport_type: str,
        command: list[str] | None = None,
        url: str | None = None,
        env: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        isolation_profile: str | None = None,
        isolation_constraints: IsolationConstraints | None = None,
    ) -> McpServerInstance:
        """Return an existing started instance or create and start a new one."""
        self.ensure_loops_started()
        key = self._key(server_key, agent_id)
        async with self._lock:
            existing = self._instances.get(key)
            if existing is not None and existing.started:
                existing.touch()
                return existing
            instance = McpServerInstance(
                server_key,
                agent_id,
                transport_type,
                command=command,
                url=url,
                env=env,
                headers=headers,
                isolation_profile=isolation_profile,
                isolation_constraints=isolation_constraints,
            )
            await instance.start()
            self._instances[key] = instance
            return instance

    async def stop(self, server_key: str, agent_id: str) -> None:
        """Stop and remove a single instance."""
        key = self._key(server_key, agent_id)
        async with self._lock:
            instance = self._instances.pop(key, None)
        if instance is not None:
            await instance.stop()

    async def stop_all_for_agent(self, agent_id: str) -> None:
        """Stop every instance belonging to *agent_id*."""
        async with self._lock:
            keys = [k for k in self._instances if k.startswith(f"{agent_id}:")]
            instances = [self._instances.pop(k) for k in keys]
        for inst in instances:
            await inst.stop()

    async def stop_all(self) -> None:
        """Shutdown all managed instances."""
        async with self._lock:
            instances = list(self._instances.values())
            self._instances.clear()
        for inst in instances:
            await inst.stop()

    async def health_check_all(self) -> dict[str, bool]:
        """Check health of every registered instance."""
        results: dict[str, bool] = {}
        # Snapshot under lock, then check without holding it.
        async with self._lock:
            snapshot: dict[str, McpServerInstance] = dict(self._instances)
        for key, inst in snapshot.items():
            results[key] = await inst.health_check()
        return results

    # -- Background lifecycle loops -----------------------------------------

    def ensure_loops_started(self) -> None:
        """Start the health and idle-timeout background tasks (idempotent).

        Called on the first ``ensure_started``; safe to call repeatedly.
        Loops only run when an event loop is active.
        """
        if self._loops_started:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._loops_started = True
        self._health_task = loop.create_task(self._health_loop(), name="koda-mcp-health-loop")
        self._idle_task = loop.create_task(self._idle_loop(), name="koda-mcp-idle-loop")

    async def _health_loop(self) -> None:
        """Periodically ping every started instance; restart on failure."""
        while True:
            try:
                await asyncio.sleep(_HEALTH_CHECK_INTERVAL_SECONDS)
                async with self._lock:
                    snapshot = list(self._instances.values())
                for inst in snapshot:
                    if not inst.started:
                        continue
                    healthy = await inst.health_check()
                    if not healthy:
                        await self._restart_with_backoff(inst)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("mcp_health_loop_error")

    async def _idle_loop(self) -> None:
        """Periodically tear down instances idle past the TTL."""
        while True:
            try:
                await asyncio.sleep(min(_IDLE_TIMEOUT_SECONDS, 60.0))
                now = time.time()
                async with self._lock:
                    snapshot = list(self._instances.items())
                for key, inst in snapshot:
                    if not inst.started:
                        continue
                    idle_age = now - inst.last_used_at
                    if idle_age >= _IDLE_TIMEOUT_SECONDS:
                        logger.info(
                            "mcp_server_idle_stop",
                            key=key,
                            idle_seconds=int(idle_age),
                        )
                        await inst.stop()
                        async with self._lock:
                            self._instances.pop(key, None)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("mcp_idle_loop_error")

    async def _restart_with_backoff(self, instance: McpServerInstance) -> None:
        """Try to restart an unhealthy instance with capped exponential backoff."""
        if instance.restart_attempts >= _MAX_RESTART_ATTEMPTS:
            instance.mark_unhealthy()
            logger.warning(
                "mcp_server_quarantined",
                server_key=instance.server_key,
                agent_id=instance.agent_id,
                attempts=instance.restart_attempts,
            )
            return
        delay = _RESTART_BACKOFF_SCHEDULE[instance.restart_attempts]
        instance.bump_restart_attempt()
        logger.warning(
            "mcp_server_restart_scheduled",
            server_key=instance.server_key,
            agent_id=instance.agent_id,
            attempt=instance.restart_attempts,
            delay_seconds=delay,
        )
        await asyncio.sleep(delay)
        try:
            await instance.restart()
        except Exception as exc:
            logger.warning(
                "mcp_server_restart_failed",
                server_key=instance.server_key,
                agent_id=instance.agent_id,
                error=str(exc),
            )


# Module-level singleton

mcp_server_manager = McpServerManager()
