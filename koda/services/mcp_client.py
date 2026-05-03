"""MCP (Model Context Protocol) client – JSON-RPC 2.0 over stdio and HTTP."""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import json
import socket
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol, cast
from urllib.parse import urlparse

from koda.logging_config import get_logger

logger = get_logger(__name__)


# Data classes


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


@dataclass(frozen=True, slots=True)
class McpResource:
    """One resource (data source) advertised by the server via resources/list."""

    uri: str
    name: str | None = None
    description: str | None = None
    mime_type: str | None = None
    annotations: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class McpResourceTemplate:
    """A URI template for resources (e.g. ``file:///{path}``)."""

    uri_template: str
    name: str | None = None
    description: str | None = None
    mime_type: str | None = None


@dataclass(frozen=True, slots=True)
class McpPromptArgument:
    """One argument schema for an MCP prompt."""

    name: str
    description: str | None = None
    required: bool = False


@dataclass(frozen=True, slots=True)
class McpPrompt:
    """One prompt template advertised by the server via prompts/list."""

    name: str
    description: str | None = None
    arguments: tuple[McpPromptArgument, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class McpPromptResult:
    """Result from prompts/get — rendered prompt messages."""

    description: str | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class McpResourceContent:
    """Result from resources/read — list of content items (text or blob)."""

    contents: list[dict[str, Any]] = field(default_factory=list)


# Errors


class McpError(Exception):
    """JSON-RPC error returned by an MCP server."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


# Transport protocol


class McpTransport(Protocol):
    """Abstract transport interface."""

    async def send_request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]: ...

    async def send_notification(self, method: str, params: dict[str, Any] | None = None) -> None: ...

    async def close(self) -> None: ...

    @property
    def is_alive(self) -> bool: ...


# Stdio transport


class StdioTransport:
    """Speaks JSON-RPC 2.0 over a subprocess's stdin/stdout."""

    def __init__(self, command: str, args: list[str] | None = None, env: dict[str, str] | None = None) -> None:
        self._command = command
        self._args = args or []
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


# HTTP transport


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


# Session


class McpSession:
    """Protocol-level MCP session."""

    def __init__(self, transport: McpTransport) -> None:
        self._transport = transport
        self._initialized = False
        self._server_info: dict[str, Any] = {}
        self._server_capabilities: dict[str, Any] = {}
        self._protocol_version: str | None = None

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
        info = result.get("serverInfo")
        if isinstance(info, dict):
            self._server_info = info
        caps = result.get("capabilities")
        if isinstance(caps, dict):
            self._server_capabilities = caps
        proto = result.get("protocolVersion")
        if isinstance(proto, str):
            self._protocol_version = proto
        return result

    async def list_tools(self) -> list[McpToolDefinition]:
        """Discover tools from the server. Walks pagination via cursor."""
        tools: list[McpToolDefinition] = []
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"cursor": cursor} if cursor else {}
            result = await self._transport.send_request("tools/list", params or None)
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
            cursor = result.get("nextCursor") or None
            if not cursor:
                break
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

    async def list_resources(self) -> list[McpResource]:
        """Discover concrete resources from the server (resources/list)."""
        if not self._server_capabilities.get("resources"):
            return []
        items: list[McpResource] = []
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"cursor": cursor} if cursor else {}
            try:
                result = await self._transport.send_request("resources/list", params or None)
            except McpError as exc:
                if exc.code == -32601:  # Method not found
                    return []
                raise
            for item in result.get("resources", []):
                raw_annotations = item.get("annotations") if isinstance(item.get("annotations"), dict) else {}
                items.append(
                    McpResource(
                        uri=str(item.get("uri") or ""),
                        name=item.get("name"),
                        description=item.get("description"),
                        mime_type=item.get("mimeType"),
                        annotations=raw_annotations or {},
                    )
                )
            cursor = result.get("nextCursor") or None
            if not cursor:
                break
        return items

    async def list_resource_templates(self) -> list[McpResourceTemplate]:
        """Discover resource URI templates from the server (resources/templates/list)."""
        if not self._server_capabilities.get("resources"):
            return []
        items: list[McpResourceTemplate] = []
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"cursor": cursor} if cursor else {}
            try:
                result = await self._transport.send_request("resources/templates/list", params or None)
            except McpError as exc:
                if exc.code == -32601:
                    return []
                raise
            for item in result.get("resourceTemplates", []):
                items.append(
                    McpResourceTemplate(
                        uri_template=str(item.get("uriTemplate") or ""),
                        name=item.get("name"),
                        description=item.get("description"),
                        mime_type=item.get("mimeType"),
                    )
                )
            cursor = result.get("nextCursor") or None
            if not cursor:
                break
        return items

    async def read_resource(self, uri: str) -> McpResourceContent:
        """Read a resource by URI (resources/read)."""
        result = await self._transport.send_request("resources/read", {"uri": uri})
        return McpResourceContent(contents=list(result.get("contents") or []))

    async def list_prompts(self) -> list[McpPrompt]:
        """Discover prompt templates from the server (prompts/list)."""
        if not self._server_capabilities.get("prompts"):
            return []
        items: list[McpPrompt] = []
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"cursor": cursor} if cursor else {}
            try:
                result = await self._transport.send_request("prompts/list", params or None)
            except McpError as exc:
                if exc.code == -32601:
                    return []
                raise
            for item in result.get("prompts", []):
                args_raw = item.get("arguments") or []
                args: list[McpPromptArgument] = []
                if isinstance(args_raw, list):
                    for arg in args_raw:
                        if not isinstance(arg, dict):
                            continue
                        args.append(
                            McpPromptArgument(
                                name=str(arg.get("name") or ""),
                                description=arg.get("description"),
                                required=bool(arg.get("required", False)),
                            )
                        )
                items.append(
                    McpPrompt(
                        name=str(item.get("name") or ""),
                        description=item.get("description"),
                        arguments=tuple(args),
                    )
                )
            cursor = result.get("nextCursor") or None
            if not cursor:
                break
        return items

    async def get_prompt(self, name: str, arguments: dict[str, Any] | None = None) -> McpPromptResult:
        """Render a prompt template (prompts/get)."""
        params: dict[str, Any] = {"name": name}
        if arguments:
            params["arguments"] = arguments
        result = await self._transport.send_request("prompts/get", params)
        return McpPromptResult(
            description=result.get("description"),
            messages=list(result.get("messages") or []),
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

    @property
    def server_info(self) -> dict[str, Any]:
        """Server identity returned from initialize (name/version/...)."""
        return dict(self._server_info)

    @property
    def server_capabilities(self) -> dict[str, Any]:
        """Capabilities reported by the server during initialize."""
        return dict(self._server_capabilities)

    @property
    def protocol_version(self) -> str | None:
        return self._protocol_version
