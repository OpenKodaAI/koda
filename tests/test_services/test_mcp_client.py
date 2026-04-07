"""Tests for MCP client protocol implementation."""

from __future__ import annotations

import asyncio
import json
import socket
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.services.mcp_client import (
    HttpSseTransport,
    McpError,
    McpSession,
    McpToolCallResult,
    McpToolDefinition,
    StdioTransport,
    _normalize_stdio_args,
    _resolve_stdio_command,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_process() -> SimpleNamespace:
    """Build a bare mock subprocess; tests wire stdout behavior themselves."""

    async def _drain() -> None:
        return None

    async def _stderr_readline() -> bytes:
        return b""

    async def _wait() -> int:
        return 0

    proc = SimpleNamespace()
    proc.returncode = None
    proc.stdin = SimpleNamespace(write=MagicMock(), drain=_drain)
    proc.stdout = SimpleNamespace()
    proc.stderr = SimpleNamespace(readline=_stderr_readline)
    proc.terminate = MagicMock()
    proc.kill = MagicMock()
    proc.wait = _wait
    return proc


def _wire_stdout_responses(proc: SimpleNamespace, responses: list[dict]) -> None:
    """Make stdout.readline yield responses only *after* stdin.write is called.

    Each time stdin.write is called, it enqueues the next response for readline.
    The reader loop blocks until a write happens, then gets the corresponding
    response, then blocks again.  A final b"" (EOF) unblocks after all responses
    are consumed.
    """
    queue: asyncio.Queue[bytes] = asyncio.Queue()
    idx = 0

    original_write = proc.stdin.write

    def _on_write(data: bytes) -> None:
        nonlocal idx
        original_write(data)
        if idx < len(responses):
            queue.put_nowait(json.dumps(responses[idx]).encode() + b"\n")
            idx += 1

    proc.stdin.write = MagicMock(side_effect=_on_write)

    async def _readline() -> bytes:
        try:
            return await asyncio.wait_for(queue.get(), timeout=2.0)
        except TimeoutError:
            return b""

    proc.stdout.readline = _readline


# ---------------------------------------------------------------------------
# StdioTransport tests
# ---------------------------------------------------------------------------


class TestStdioTransport:
    def test_resolve_stdio_command_rejects_control_characters(self) -> None:
        with pytest.raises(ValueError, match="invalid control characters"):
            _resolve_stdio_command("python\n-m")

    def test_resolve_stdio_command_accepts_existing_explicit_path(self, tmp_path: Path) -> None:
        command = tmp_path / "koda-mcp"
        command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        command.chmod(0o755)

        resolved = _resolve_stdio_command(str(command))

        assert resolved == str(command.resolve())

    def test_resolve_stdio_command_rejects_missing_path_command(self, tmp_path) -> None:
        missing = tmp_path / "missing-mcp-server"

        with pytest.raises(ValueError, match="does not exist"):
            _resolve_stdio_command(str(missing))

    def test_resolve_stdio_command_uses_path_lookup_for_bare_commands(self) -> None:
        with patch("shutil.which", return_value="/usr/local/bin/koda-mcp") as mock_which:
            resolved = _resolve_stdio_command("koda-mcp")

        assert resolved == "/usr/local/bin/koda-mcp"
        mock_which.assert_called_once_with("koda-mcp")

    def test_normalize_stdio_args_rejects_null_bytes(self) -> None:
        with pytest.raises(ValueError, match="invalid control characters"):
            _normalize_stdio_args(["--config", "bad\x00arg"])

    def test_normalize_stdio_args_rejects_newlines(self) -> None:
        with pytest.raises(ValueError, match="invalid control characters"):
            _normalize_stdio_args(["--config", "bad\narg"])

    @pytest.mark.asyncio
    async def test_sends_jsonrpc_request(self) -> None:
        response = {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
        proc = _mock_process()
        _wire_stdout_responses(proc, [response])

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            transport = StdioTransport("echo")
            await transport.start()

            result = await transport.send_request("test/method", {"key": "value"})
            assert result == {"ok": True}

            written = proc.stdin.write.call_args[0][0]
            envelope = json.loads(written)
            assert envelope["jsonrpc"] == "2.0"
            assert envelope["id"] == 1
            assert envelope["method"] == "test/method"
            assert envelope["params"] == {"key": "value"}

            await transport.close()

    @pytest.mark.asyncio
    async def test_handles_error_response(self) -> None:
        response = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32601, "message": "Method not found"},
        }
        proc = _mock_process()
        _wire_stdout_responses(proc, [response])

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            transport = StdioTransport("echo")
            await transport.start()

            with pytest.raises(McpError) as exc_info:
                await transport.send_request("bad/method")

            assert exc_info.value.code == -32601
            assert "Method not found" in str(exc_info.value)
            await transport.close()

    @pytest.mark.asyncio
    async def test_close_graceful(self) -> None:
        proc = _mock_process()
        _wire_stdout_responses(proc, [])

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            transport = StdioTransport("echo")
            await transport.start()
            await transport.close()
            proc.terminate.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_force_kill(self) -> None:
        proc = _mock_process()
        _wire_stdout_responses(proc, [])

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            transport = StdioTransport("echo")
            await transport.start()

            async def _timeout_wait_for(awaitable, timeout):
                if hasattr(awaitable, "close"):
                    awaitable.close()
                raise TimeoutError

            # Patch wait_for so terminate-wait times out, triggering kill path.
            with patch("asyncio.wait_for", side_effect=_timeout_wait_for):
                await transport.close()

            proc.terminate.assert_called_once()
            proc.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_is_alive(self) -> None:
        proc = _mock_process()
        _wire_stdout_responses(proc, [])

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            transport = StdioTransport("echo")
            assert not transport.is_alive  # not started
            await transport.start()
            assert transport.is_alive
            proc.returncode = 1
            assert not transport.is_alive
            await transport.close()

    @pytest.mark.asyncio
    async def test_send_notification(self) -> None:
        proc = _mock_process()
        _wire_stdout_responses(proc, [])

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            transport = StdioTransport("echo")
            await transport.start()

            await transport.send_notification("notifications/test", {"x": 1})

            written = proc.stdin.write.call_args[0][0]
            envelope = json.loads(written)
            assert "id" not in envelope
            assert envelope["method"] == "notifications/test"
            assert envelope["params"] == {"x": 1}

            await transport.close()


# ---------------------------------------------------------------------------
# HttpSseTransport tests
# ---------------------------------------------------------------------------


class TestHttpSseTransport:
    @pytest.fixture(autouse=True)
    def _public_dns_resolution(self):
        with patch(
            "socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
        ):
            yield

    @pytest.mark.asyncio
    async def test_sends_request(self) -> None:
        response_body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"status": "ok"}}).encode()

        mock_resp = MagicMock()
        mock_resp.read.return_value = response_body

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
            transport = HttpSseTransport("https://mcp.example.com/rpc")
            result = await transport.send_request("ping")

            assert result == {"status": "ok"}
            req_obj = mock_open.call_args[0][0]
            assert req_obj.get_header("Content-type") == "application/json"
            body = json.loads(req_obj.data)
            assert body["method"] == "ping"

    @pytest.mark.asyncio
    async def test_handles_error_response(self) -> None:
        response_body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32600, "message": "Invalid request"},
            }
        ).encode()

        mock_resp = MagicMock()
        mock_resp.read.return_value = response_body

        with patch("urllib.request.urlopen", return_value=mock_resp):
            transport = HttpSseTransport("https://mcp.example.com/rpc")
            with pytest.raises(McpError) as exc_info:
                await transport.send_request("bad")
            assert exc_info.value.code == -32600

    @pytest.mark.asyncio
    async def test_is_alive_always_true(self) -> None:
        transport = HttpSseTransport("https://mcp.example.com/rpc")
        assert transport.is_alive

    @pytest.mark.asyncio
    async def test_close_is_noop(self) -> None:
        transport = HttpSseTransport("https://mcp.example.com/rpc")
        await transport.close()  # should not raise

    @pytest.mark.asyncio
    async def test_rejects_localhost_url(self) -> None:
        with pytest.raises(ValueError, match="localhost"):
            HttpSseTransport("http://localhost:8080/mcp")

    @pytest.mark.asyncio
    async def test_rejects_private_ip(self) -> None:
        with pytest.raises(ValueError, match="Private"):
            HttpSseTransport("http://192.168.1.1:8080/mcp")

    @pytest.mark.asyncio
    async def test_rejects_hostname_resolving_to_private_ip(self) -> None:
        with (
            patch(
                "socket.getaddrinfo",
                return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 443))],
            ),
            pytest.raises(ValueError, match="Private/internal destination"),
        ):
            HttpSseTransport("https://mcp.example.com/rpc")

    @pytest.mark.asyncio
    async def test_rejects_unsupported_scheme(self) -> None:
        with pytest.raises(ValueError, match="Unsupported URL scheme"):
            HttpSseTransport("ftp://example.com/mcp")


# ---------------------------------------------------------------------------
# McpSession tests
# ---------------------------------------------------------------------------


class TestMcpSession:
    @pytest.mark.asyncio
    async def test_initialize(self) -> None:
        transport = MagicMock()
        transport.send_request = AsyncMock(return_value={"protocolVersion": "2025-03-26", "capabilities": {}})
        transport.send_notification = AsyncMock()

        session = McpSession(transport)
        assert not session.initialized

        result = await session.initialize()

        assert session.initialized
        assert result["protocolVersion"] == "2025-03-26"

        transport.send_request.assert_awaited_once()
        call_args = transport.send_request.call_args
        assert call_args[0][0] == "initialize"
        assert call_args[0][1]["clientInfo"]["name"] == "koda"

        transport.send_notification.assert_awaited_once_with("notifications/initialized")

    @pytest.mark.asyncio
    async def test_list_tools_parses_annotations(self) -> None:
        transport = MagicMock()
        transport.send_request = AsyncMock(
            return_value={
                "tools": [
                    {
                        "name": "read_file",
                        "description": "Read a file",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"path": {"type": "string"}},
                        },
                        "annotations": {
                            "title": "File Reader",
                            "readOnlyHint": True,
                            "destructiveHint": False,
                            "idempotentHint": True,
                            "openWorldHint": False,
                        },
                    }
                ]
            }
        )

        session = McpSession(transport)
        tools = await session.list_tools()

        assert len(tools) == 1
        tool = tools[0]
        assert tool.name == "read_file"
        assert tool.description == "Read a file"
        assert tool.input_schema["type"] == "object"
        assert tool.annotations is not None
        assert tool.annotations.title == "File Reader"
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.destructive_hint is False
        assert tool.annotations.idempotent_hint is True
        assert tool.annotations.open_world_hint is False

    @pytest.mark.asyncio
    async def test_list_tools_no_annotations(self) -> None:
        transport = MagicMock()
        transport.send_request = AsyncMock(return_value={"tools": [{"name": "simple_tool"}]})

        session = McpSession(transport)
        tools = await session.list_tools()

        assert len(tools) == 1
        assert tools[0].name == "simple_tool"
        assert tools[0].description is None
        assert tools[0].annotations is None

    @pytest.mark.asyncio
    async def test_call_tool_success(self) -> None:
        transport = MagicMock()
        transport.send_request = AsyncMock(
            return_value={
                "content": [{"type": "text", "text": "hello"}],
                "isError": False,
            }
        )

        session = McpSession(transport)
        result = await session.call_tool("greet", {"name": "world"})

        assert not result.is_error
        assert len(result.content) == 1
        assert result.content[0]["text"] == "hello"

        call_args = transport.send_request.call_args
        assert call_args[0][1]["name"] == "greet"
        assert call_args[0][1]["arguments"] == {"name": "world"}

    @pytest.mark.asyncio
    async def test_call_tool_error(self) -> None:
        transport = MagicMock()
        transport.send_request = AsyncMock(
            return_value={
                "content": [{"type": "text", "text": "not found"}],
                "isError": True,
            }
        )

        session = McpSession(transport)
        result = await session.call_tool("missing_tool")

        assert result.is_error
        assert result.content[0]["text"] == "not found"

    @pytest.mark.asyncio
    async def test_ping_success(self) -> None:
        transport = MagicMock()
        transport.send_request = AsyncMock(return_value={})

        session = McpSession(transport)
        assert await session.ping() is True

    @pytest.mark.asyncio
    async def test_ping_timeout(self) -> None:
        async def _hang(*_a: object, **_kw: object) -> dict:
            await asyncio.sleep(999)
            return {}

        transport = MagicMock()
        transport.send_request = _hang

        session = McpSession(transport)
        assert await session.ping() is False


# ---------------------------------------------------------------------------
# Data class sanity checks
# ---------------------------------------------------------------------------


class TestDataClasses:
    def test_tool_definition_defaults(self) -> None:
        td = McpToolDefinition(name="t")
        assert td.description is None
        assert td.input_schema == {}
        assert td.annotations is None

    def test_tool_call_result_defaults(self) -> None:
        r = McpToolCallResult()
        assert r.content == []
        assert r.is_error is False

    def test_mcp_error_fields(self) -> None:
        err = McpError(42, "boom", {"extra": 1})
        assert err.code == 42
        assert err.message == "boom"
        assert err.data == {"extra": 1}
        assert "boom" in str(err)
