"""MCP server lifecycle manager – start, stop, health-check, and tool caching."""

from __future__ import annotations

import asyncio
import time

from koda.logging_config import get_logger
from koda.services.mcp_client import (
    HttpSseTransport,
    McpSession,
    McpToolDefinition,
    McpTransport,
    StdioTransport,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Single server instance
# ---------------------------------------------------------------------------


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
    ) -> None:
        self._server_key = server_key
        self._agent_id = agent_id
        self._transport_type = transport_type
        self._command = command or []
        self._url = url
        self._env = env
        self._headers = headers

        self._session: McpSession | None = None
        self._transport: McpTransport | None = None
        self._cached_tools: list[McpToolDefinition] = []
        self._cached_tools_at: float = 0.0
        self._started: bool = False

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

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        """Create transport, start session, initialize, and cache tools."""
        if self._transport_type == "stdio":
            if not self._command:
                raise ValueError("stdio transport requires a command")
            transport = StdioTransport(self._command[0], args=self._command[1:], env=self._env)
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
        logger.info(
            "mcp_server_started",
            server_key=self._server_key,
            agent_id=self._agent_id,
            transport=self._transport_type,
            tools=len(self._cached_tools),
        )

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


# ---------------------------------------------------------------------------
# Global registry
# ---------------------------------------------------------------------------


class McpServerManager:
    """Global registry of MCP server instances, keyed by agent_id:server_key."""

    def __init__(self) -> None:
        self._instances: dict[str, McpServerInstance] = {}
        self._lock = asyncio.Lock()

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
    ) -> McpServerInstance:
        """Return an existing started instance or create and start a new one."""
        key = self._key(server_key, agent_id)
        async with self._lock:
            existing = self._instances.get(key)
            if existing is not None and existing.started:
                return existing
            instance = McpServerInstance(
                server_key,
                agent_id,
                transport_type,
                command=command,
                url=url,
                env=env,
                headers=headers,
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


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

mcp_server_manager = McpServerManager()
