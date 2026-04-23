"""Tests for the MCP server lifecycle manager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.services.mcp_client import McpToolDefinition
from koda.services.mcp_manager import McpServerInstance, McpServerManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_TOOLS = [
    McpToolDefinition(name="read_file", description="Read a file"),
    McpToolDefinition(name="write_file", description="Write a file"),
]


def _mock_session() -> MagicMock:
    session = MagicMock()
    session.initialize = AsyncMock(return_value={})
    session.list_tools = AsyncMock(return_value=list(_SAMPLE_TOOLS))
    session.ping = AsyncMock(return_value=True)
    return session


def _mock_stdio_transport() -> MagicMock:
    transport = MagicMock()
    transport.start = AsyncMock()
    transport.close = AsyncMock()
    transport.is_alive = True
    return transport


def _mock_http_transport() -> MagicMock:
    transport = MagicMock()
    transport.close = AsyncMock()
    transport.is_alive = True
    return transport


# ---------------------------------------------------------------------------
# McpServerInstance tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_instance_start_stdio():
    transport = _mock_stdio_transport()
    session = _mock_session()

    with (
        patch("koda.services.mcp_manager.StdioTransport", return_value=transport),
        patch("koda.services.mcp_manager.McpSession", return_value=session),
    ):
        inst = McpServerInstance("my-server", "agent-1", "stdio", command=["node", "server.js"])
        await inst.start()

    transport.start.assert_awaited_once()
    session.initialize.assert_awaited_once()
    session.list_tools.assert_awaited_once()
    assert inst.started is True
    assert len(inst.cached_tools) == 2
    assert inst.cached_tools_at > 0


@pytest.mark.asyncio
async def test_instance_start_http():
    transport = _mock_http_transport()
    session = _mock_session()

    with (
        patch("koda.services.mcp_manager.HttpSseTransport", return_value=transport),
        patch("koda.services.mcp_manager.McpSession", return_value=session),
    ):
        inst = McpServerInstance("my-server", "agent-1", "http_sse", url="http://localhost:8080")
        await inst.start()

    # HttpSseTransport has no start() to call
    transport.start.assert_not_called()
    session.initialize.assert_awaited_once()
    session.list_tools.assert_awaited_once()
    assert inst.started is True
    assert len(inst.cached_tools) == 2


@pytest.mark.asyncio
async def test_instance_start_missing_command():
    inst = McpServerInstance("srv", "a1", "stdio")
    with pytest.raises(ValueError, match="command"):
        await inst.start()


@pytest.mark.asyncio
async def test_instance_start_missing_url():
    inst = McpServerInstance("srv", "a1", "http_sse")
    with pytest.raises(ValueError, match="url"):
        await inst.start()


@pytest.mark.asyncio
async def test_instance_stop():
    transport = _mock_stdio_transport()
    session = _mock_session()

    with (
        patch("koda.services.mcp_manager.StdioTransport", return_value=transport),
        patch("koda.services.mcp_manager.McpSession", return_value=session),
    ):
        inst = McpServerInstance("srv", "a1", "stdio", command=["cmd"])
        await inst.start()
        await inst.stop()

    transport.close.assert_awaited_once()
    assert inst.started is False
    assert inst.session is None
    assert inst.cached_tools == []
    assert inst.cached_tools_at == 0.0


@pytest.mark.asyncio
async def test_instance_restart():
    transport = _mock_stdio_transport()
    session = _mock_session()

    with (
        patch("koda.services.mcp_manager.StdioTransport", return_value=transport),
        patch("koda.services.mcp_manager.McpSession", return_value=session),
    ):
        inst = McpServerInstance("srv", "a1", "stdio", command=["cmd"])
        await inst.start()
        await inst.restart()

    # start called twice (initial + restart), close called once (stop during restart)
    assert transport.start.await_count == 2
    assert transport.close.await_count == 1
    assert session.initialize.await_count == 2
    assert inst.started is True


@pytest.mark.asyncio
async def test_instance_health_check_ok():
    transport = _mock_stdio_transport()
    session = _mock_session()

    with (
        patch("koda.services.mcp_manager.StdioTransport", return_value=transport),
        patch("koda.services.mcp_manager.McpSession", return_value=session),
    ):
        inst = McpServerInstance("srv", "a1", "stdio", command=["cmd"])
        await inst.start()
        result = await inst.health_check()

    assert result is True
    session.ping.assert_awaited_once()


@pytest.mark.asyncio
async def test_instance_health_check_not_started():
    inst = McpServerInstance("srv", "a1", "stdio", command=["cmd"])
    result = await inst.health_check()
    assert result is False


@pytest.mark.asyncio
async def test_instance_refresh_tools():
    transport = _mock_stdio_transport()
    session = _mock_session()
    new_tools = [McpToolDefinition(name="new_tool", description="A new tool")]
    # list_tools returns original tools on first call, new tools on second
    session.list_tools = AsyncMock(side_effect=[list(_SAMPLE_TOOLS), new_tools])

    with (
        patch("koda.services.mcp_manager.StdioTransport", return_value=transport),
        patch("koda.services.mcp_manager.McpSession", return_value=session),
    ):
        inst = McpServerInstance("srv", "a1", "stdio", command=["cmd"])
        await inst.start()
        original_ts = inst.cached_tools_at

        refreshed = await inst.refresh_tools()

    assert len(refreshed) == 1
    assert refreshed[0].name == "new_tool"
    assert inst.cached_tools == refreshed
    assert inst.cached_tools_at >= original_ts


# ---------------------------------------------------------------------------
# McpServerManager tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_manager_ensure_started_creates_new():
    transport = _mock_stdio_transport()
    session = _mock_session()

    mgr = McpServerManager()
    with (
        patch("koda.services.mcp_manager.StdioTransport", return_value=transport),
        patch("koda.services.mcp_manager.McpSession", return_value=session),
    ):
        inst = await mgr.ensure_started("srv", "a1", transport_type="stdio", command=["cmd"])

    assert inst.started is True
    assert inst.server_key == "srv"
    assert inst.agent_id == "a1"
    assert mgr.get_instance("srv", "a1") is inst


@pytest.mark.asyncio
async def test_manager_ensure_started_reuses_existing():
    transport = _mock_stdio_transport()
    session = _mock_session()

    mgr = McpServerManager()
    with (
        patch("koda.services.mcp_manager.StdioTransport", return_value=transport),
        patch("koda.services.mcp_manager.McpSession", return_value=session),
    ):
        first = await mgr.ensure_started("srv", "a1", transport_type="stdio", command=["cmd"])
        second = await mgr.ensure_started("srv", "a1", transport_type="stdio", command=["cmd"])

    assert first is second
    # start should only be called once (reuse path skips creation)
    assert transport.start.await_count == 1


@pytest.mark.asyncio
async def test_manager_stop_removes_instance():
    transport = _mock_stdio_transport()
    session = _mock_session()

    mgr = McpServerManager()
    with (
        patch("koda.services.mcp_manager.StdioTransport", return_value=transport),
        patch("koda.services.mcp_manager.McpSession", return_value=session),
    ):
        await mgr.ensure_started("srv", "a1", transport_type="stdio", command=["cmd"])
        await mgr.stop("srv", "a1")

    assert mgr.get_instance("srv", "a1") is None
    transport.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_manager_stop_all_for_agent():
    transport = _mock_stdio_transport()
    session = _mock_session()

    mgr = McpServerManager()
    with (
        patch("koda.services.mcp_manager.StdioTransport", return_value=transport),
        patch("koda.services.mcp_manager.McpSession", return_value=session),
    ):
        await mgr.ensure_started("srv1", "a1", transport_type="stdio", command=["cmd"])
        await mgr.ensure_started("srv2", "a1", transport_type="stdio", command=["cmd2"])
        await mgr.ensure_started("srv1", "a2", transport_type="stdio", command=["cmd3"])

        await mgr.stop_all_for_agent("a1")

    assert mgr.get_instance("srv1", "a1") is None
    assert mgr.get_instance("srv2", "a1") is None
    # Agent a2 should be untouched
    assert mgr.get_instance("srv1", "a2") is not None
