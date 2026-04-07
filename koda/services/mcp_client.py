"""MCP (Model Context Protocol) client – JSON-RPC 2.0 over stdio and HTTP."""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import json
import shutil
import socket
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol, cast
from urllib.parse import urlparse

from koda.logging_config import get_logger

logger = get_logger(__name__)


def _resolve_stdio_command(command: str) -> str:
    value = str(command or "").strip()
    if not value:
        raise ValueError("stdio transport requires a command")
    if any(char in value for char in ("\x00", "\r", "\n")):
        raise ValueError("stdio transport command contains invalid control characters")
    if "/" in value or "\\" in value:
        raise ValueError("stdio transport command must be a bare executable name available on PATH")

    resolved_command = shutil.which(value)
    if not resolved_command:
        raise ValueError(f"stdio transport command was not found on PATH: {value}")
    return resolved_command


def _normalize_stdio_args(args: list[str]) -> list[str]:
    normalized: list[str] = []
    for arg in args:
        value = str(arg)
        if any(char in value for char in ("\x00", "\r", "\n")):
            raise ValueError("stdio transport arguments contain invalid control characters")
        normalized.append(value)
    return normalized


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class McpToolAnnotations:
    """MCP spec tool annotations for governance classification."""

    title: str | None = None
    read_only_hint: bool | None = None
    destructive_hint: bool | None = None
    idempotent_hint: bool | None = None
    open_world_hint: bool | None = None


@dataclass(frozen=True, slots=True)
class McpToolDefinition:
    """One tool discovered from an MCP server."""

    name: str
    description: str | None = None
    input_schema: dict[str, Any] = field(default_factory=dict)
    annotations: McpToolAnnotations | None = None


@dataclass(slots=True)
class McpToolCallResult:
    """Result from tools/call."""

    content: list[dict[str, Any]] = field(default_factory=list)
    is_error: bool = False


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class McpError(Exception):
    """JSON-RPC error returned by an MCP server."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


# ---------------------------------------------------------------------------
# Transport protocol
# ---------------------------------------------------------------------------


class McpTransport(Protocol):
    """Abstract transport interface."""

    async def send_request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]: ...

    async def send_notification(self, method: str, params: dict[str, Any] | None = None) -> None: ...

    async def close(self) -> None: ...

    @property
    def is_alive(self) -> bool: ...


# ---------------------------------------------------------------------------
# Stdio transport
# ---------------------------------------------------------------------------


class StdioTransport:
    """Speaks JSON-RPC 2.0 over a subprocess's stdin/stdout."""

    def __init__(self, command: str, args: list[str] | None = None, env: dict[str, str] | None = None) -> None:
        self._command = _resolve_stdio_command(command)
        self._args = _normalize_stdio_args(args or [])
        self._env = env
        self._process: asyncio.subprocess.Process | None = None
        self._next_id = 1
        self._lock = asyncio.Lock()
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        self._process = await asyncio.create_subprocess_exec(
            self._command,
            *self._args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._env,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        if self._process.stderr:
            self._stderr_task = asyncio.create_task(self._drain_stderr())

    async def _read_loop(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        try:
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("mcp_stdio_bad_json", raw=line.decode(errors="replace"))
                    continue
                msg_id = msg.get("id")
                if msg_id is not None and msg_id in self._pending:
                    self._pending.pop(msg_id).set_result(msg)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("mcp_stdio_reader_error")

    async def _drain_stderr(self) -> None:
        assert self._process is not None and self._process.stderr is not None
        try:
            while True:
                line = await self._process.stderr.readline()
                if not line:
                    break
                logger.debug("mcp_stderr", line=line.decode(errors="replace").rstrip())
        except Exception:
            pass

    # -- transport interface -------------------------------------------------

    async def send_request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert self._process is not None and self._process.stdin is not None

        async with self._lock:
            req_id = self._next_id
            self._next_id += 1

        envelope: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
        }
        if params is not None:
            envelope["params"] = params

        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[req_id] = future

        raw = json.dumps(envelope).encode() + b"\n"
        async with self._lock:
            self._process.stdin.write(raw)
            await self._process.stdin.drain()

        try:
            response = await asyncio.wait_for(future, timeout=30.0)
        except TimeoutError:
            self._pending.pop(req_id, None)
            raise McpError(-1, f"Request timed out after 30s: {method}") from None

        if "error" in response:
            err = response["error"]
            raise McpError(
                code=err.get("code", -1),
                message=err.get("message", "Unknown error"),
                data=err.get("data"),
            )

        return cast(dict[str, Any], response.get("result", {}))

    async def send_notification(self, method: str, params: dict[str, Any] | None = None) -> None:
        assert self._process is not None and self._process.stdin is not None
        envelope: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            envelope["params"] = params
        raw = json.dumps(envelope).encode() + b"\n"
        async with self._lock:
            self._process.stdin.write(raw)
            await self._process.stdin.drain()

    async def close(self) -> None:
        if self._process is None:
            return
        if self._reader_task is not None:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task
        if self._stderr_task is not None:
            self._stderr_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._stderr_task
        try:
            self._process.terminate()
            await asyncio.wait_for(self._process.wait(), timeout=5.0)
        except TimeoutError:
            self._process.kill()
            await self._process.wait()
        # Resolve any dangling futures so callers don't hang.
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(McpError(-1, "transport closed"))
        self._pending.clear()

    @property
    def is_alive(self) -> bool:
        return self._process is not None and self._process.returncode is None


# ---------------------------------------------------------------------------
# HTTP transport
# ---------------------------------------------------------------------------


def _validate_url(url: str) -> None:
    """Validate that a URL is safe for MCP HTTP transport (no SSRF)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")
    hostname = parsed.hostname or ""
    if hostname in ("localhost", ""):
        raise ValueError("localhost URLs not allowed for MCP HTTP transport")

    def _blocked_ip(value: str) -> bool:
        ip = ipaddress.ip_address(value)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )

    try:
        if _blocked_ip(hostname):
            raise ValueError(f"Private/internal IP not allowed: {hostname}")
    except ValueError as exc:
        # Re-raise our own validation errors
        if "not allowed" in str(exc) or "Unsupported" in str(exc):
            raise
        # hostname is a domain name, not an IP - validate all resolved targets.
        try:
            resolved = socket.getaddrinfo(hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        except socket.gaierror as resolve_exc:
            raise ValueError(f"Unable to resolve MCP HTTP host: {hostname}") from resolve_exc
        for _, _, _, _, sockaddr in resolved:
            resolved_host = str(sockaddr[0]).strip()
            if resolved_host and _blocked_ip(resolved_host):
                raise ValueError(f"Private/internal destination not allowed: {hostname}") from None


class HttpSseTransport:
    """Speaks JSON-RPC 2.0 over HTTP POST (stdlib only)."""

    def __init__(self, url: str, headers: dict[str, str] | None = None) -> None:
        _validate_url(url)
        self._url = url
        self._headers = headers or {}
        self._next_id = 1
        self._lock = asyncio.Lock()

    async def send_request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        async with self._lock:
            req_id = self._next_id
            self._next_id += 1

        envelope: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
        }
        if params is not None:
            envelope["params"] = params

        body = json.dumps(envelope).encode()
        req = urllib.request.Request(
            self._url,
            data=body,
            headers={
                "Content-Type": "application/json",
                **self._headers,
            },
            method="POST",
        )

        loop = asyncio.get_running_loop()
        response_data: bytes = await loop.run_in_executor(None, lambda: urllib.request.urlopen(req, timeout=30).read())
        response = json.loads(response_data)

        if "error" in response:
            err = response["error"]
            raise McpError(
                code=err.get("code", -1),
                message=err.get("message", "Unknown error"),
                data=err.get("data"),
            )

        return cast(dict[str, Any], response.get("result", {}))

    async def send_notification(self, method: str, params: dict[str, Any] | None = None) -> None:
        # Notifications are fire-and-forget; send but ignore response.
        envelope: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            envelope["params"] = params
        body = json.dumps(envelope).encode()
        req = urllib.request.Request(
            self._url,
            data=body,
            headers={
                "Content-Type": "application/json",
                **self._headers,
            },
            method="POST",
        )
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: urllib.request.urlopen(req, timeout=30).read())

    async def close(self) -> None:
        pass  # Stateless transport; nothing to close.

    @property
    def is_alive(self) -> bool:
        return True  # Stateless; always considered alive.


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


class McpSession:
    """Protocol-level MCP session."""

    def __init__(self, transport: McpTransport) -> None:
        self._transport = transport
        self._initialized = False

    async def initialize(self) -> dict[str, Any]:
        """Send initialize request and notifications/initialized notification."""
        result = await self._transport.send_request(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "koda", "version": "1.0.0"},
            },
        )
        await self._transport.send_notification("notifications/initialized")
        self._initialized = True
        return result

    async def list_tools(self) -> list[McpToolDefinition]:
        """Discover tools from the server."""
        result = await self._transport.send_request("tools/list")
        tools: list[McpToolDefinition] = []
        for item in result.get("tools", []):
            annotations: McpToolAnnotations | None = None
            raw_annotations = item.get("annotations")
            if raw_annotations and isinstance(raw_annotations, dict):
                annotations = McpToolAnnotations(
                    title=raw_annotations.get("title"),
                    read_only_hint=raw_annotations.get("readOnlyHint"),
                    destructive_hint=raw_annotations.get("destructiveHint"),
                    idempotent_hint=raw_annotations.get("idempotentHint"),
                    open_world_hint=raw_annotations.get("openWorldHint"),
                )
            tools.append(
                McpToolDefinition(
                    name=item["name"],
                    description=item.get("description"),
                    input_schema=item.get("inputSchema", {}),
                    annotations=annotations,
                )
            )
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> McpToolCallResult:
        """Execute a tool on the server."""
        result = await self._transport.send_request(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
        )
        return McpToolCallResult(
            content=result.get("content", []),
            is_error=bool(result.get("isError", False)),
        )

    async def ping(self) -> bool:
        """Health check."""
        try:
            await asyncio.wait_for(
                self._transport.send_request("ping"),
                timeout=5.0,
            )
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """Close the underlying transport."""
        await self._transport.close()

    @property
    def initialized(self) -> bool:
        return self._initialized
