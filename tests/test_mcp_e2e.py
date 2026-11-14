"""End-to-end tests for MCP Bridge flow: bootstrap -> register -> execute."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.services.mcp_bridge import _agent_mcp_tools
from koda.services.mcp_client import McpToolAnnotations, McpToolCallResult, McpToolDefinition


def _make_mock_instance(server_key: str, agent_id: str, tools: list[McpToolDefinition] | None = None) -> MagicMock:
    """Create a mock McpServerInstance with the given tools."""
    instance = MagicMock()
    instance.server_key = server_key
    instance.agent_id = agent_id
    instance.started = True
    instance.cached_tools = tools or []
    instance.session = AsyncMock()
    return instance


def _make_tool_def(name: str, *, read_only: bool = False, destructive: bool = False) -> McpToolDefinition:
    """Create an McpToolDefinition with optional annotations."""
    annotations = McpToolAnnotations(
        read_only_hint=read_only if read_only else None,
        destructive_hint=destructive if destructive else None,
    )
    return McpToolDefinition(
        name=name,
        description=f"Tool: {name}",
        input_schema={"type": "object"},
        annotations=annotations,
    )


class TestMcpBootstrap:
    """Test the bootstrap flow that starts MCP servers at agent startup."""

    @pytest.mark.asyncio
    async def test_bootstrap_starts_servers_and_registers_tools(self):
        tools = [_make_tool_def("create_issue", destructive=True), _make_tool_def("list_repos", read_only=True)]
        mock_instance = _make_mock_instance("github", "agent-1", tools)

        fake_connections = [{"server_key": "github", "enabled": True}]
        fake_catalog = {
            "server_key": "github",
            "transport_type": "stdio",
            "command": ["npx", "mcp-github"],
            "url": None,
        }

        with (
            patch("koda.config.MCP_ENABLED", True),
            patch(
                "koda.services.mcp_bootstrap._load_agent_mcp_connections",
                return_value=fake_connections,
            ),
            patch(
                "koda.services.mcp_bootstrap._load_catalog_entry",
                return_value=fake_catalog,
            ),
            patch(
                "koda.services.mcp_bootstrap._decrypt_connection_env",
                return_value={},
            ),
            patch("koda.services.mcp_manager.mcp_server_manager") as mock_mgr,
            patch("koda.services.mcp_bridge.register_mcp_tools_for_agent") as mock_register,
        ):
            mock_mgr.ensure_started = AsyncMock(return_value=mock_instance)
            mock_register.return_value = ["mcp_github__create_issue", "mcp_github__list_repos"]

            from koda.services.mcp_bootstrap import bootstrap_mcp_for_agent

            result = await bootstrap_mcp_for_agent("agent-1")

        assert result["started_servers"] == 1
        assert result["total_tools"] == 2
        assert result["errors"] == []
        mock_mgr.ensure_started.assert_awaited_once()
        mock_register.assert_called_once()

    @pytest.mark.asyncio
    async def test_bootstrap_skips_disabled_connections(self):
        fake_connections = [
            {"server_key": "github", "enabled": False},
            {"server_key": "slack", "enabled": True},
        ]
        fake_catalog = {
            "server_key": "slack",
            "transport_type": "stdio",
            "command": ["npx", "mcp-slack"],
            "url": None,
        }
        mock_instance = _make_mock_instance("slack", "agent-1", [_make_tool_def("post_message")])

        with (
            patch("koda.config.MCP_ENABLED", True),
            patch(
                "koda.services.mcp_bootstrap._load_agent_mcp_connections",
                return_value=fake_connections,
            ),
            patch(
                "koda.services.mcp_bootstrap._load_catalog_entry",
                return_value=fake_catalog,
            ),
            patch(
                "koda.services.mcp_bootstrap._decrypt_connection_env",
                return_value={},
            ),
            patch("koda.services.mcp_manager.mcp_server_manager") as mock_mgr,
            patch("koda.services.mcp_bridge.register_mcp_tools_for_agent") as mock_register,
        ):
            mock_mgr.ensure_started = AsyncMock(return_value=mock_instance)
            mock_register.return_value = ["mcp_slack__post_message"]

            from koda.services.mcp_bootstrap import bootstrap_mcp_for_agent

            result = await bootstrap_mcp_for_agent("agent-1")

        # Only slack should start, github was disabled
        assert result["started_servers"] == 1
        # ensure_started should be called once (only for slack)
        mock_mgr.ensure_started.assert_awaited_once()
        call_kwargs = mock_mgr.ensure_started.call_args
        assert call_kwargs.kwargs.get("server_key") or call_kwargs[1].get("server_key", "") != "github"

    @pytest.mark.asyncio
    async def test_bootstrap_handles_server_failure_gracefully(self):
        fake_connections = [
            {"server_key": "github", "enabled": True},
            {"server_key": "slack", "enabled": True},
        ]
        fake_catalog_github = {
            "server_key": "github",
            "transport_type": "stdio",
            "command": ["npx", "mcp-github"],
            "url": None,
        }
        fake_catalog_slack = {
            "server_key": "slack",
            "transport_type": "stdio",
            "command": ["npx", "mcp-slack"],
            "url": None,
        }
        mock_slack_instance = _make_mock_instance("slack", "agent-1", [_make_tool_def("post_message")])

        call_count = 0

        async def ensure_started_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if kwargs.get("server_key") == "github":
                raise ConnectionError("github server failed")
            return mock_slack_instance

        with (
            patch("koda.config.MCP_ENABLED", True),
            patch(
                "koda.services.mcp_bootstrap._load_agent_mcp_connections",
                return_value=fake_connections,
            ),
            patch(
                "koda.services.mcp_bootstrap._load_catalog_entry",
                side_effect=lambda key: fake_catalog_github if key == "github" else fake_catalog_slack,
            ),
            patch(
                "koda.services.mcp_bootstrap._decrypt_connection_env",
                return_value={},
            ),
            patch("koda.services.mcp_manager.mcp_server_manager") as mock_mgr,
            patch("koda.services.mcp_bridge.register_mcp_tools_for_agent") as mock_register,
        ):
            mock_mgr.ensure_started = AsyncMock(side_effect=ensure_started_side_effect)
            mock_register.return_value = ["mcp_slack__post_message"]

            from koda.services.mcp_bootstrap import bootstrap_mcp_for_agent

            result = await bootstrap_mcp_for_agent("agent-1")

        assert result["started_servers"] == 1
        assert len(result["errors"]) == 1
        assert "github" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_bootstrap_skips_when_mcp_disabled(self):
        with patch("koda.config.MCP_ENABLED", False):
            from koda.services.mcp_bootstrap import bootstrap_mcp_for_agent

            result = await bootstrap_mcp_for_agent("agent-1")

        assert result.get("skipped") is True
        assert "MCP_ENABLED" in result.get("reason", "")


class TestMcpLazyStart:
    """Test the lazy start fallback in handle_mcp_tool_call."""

    @pytest.mark.asyncio
    async def test_lazy_start_when_server_not_running(self):
        mock_session = AsyncMock()
        mock_session.call_tool.return_value = McpToolCallResult(
            content=[{"type": "text", "text": "Issue #42 created"}],
            is_error=False,
        )

        mock_instance = MagicMock()
        mock_instance.started = True
        mock_instance.session = mock_session

        with (
            patch("koda.services.mcp_bridge.mcp_server_manager") as mock_manager,
            patch("koda.services.mcp_bridge._lazy_start_mcp_server", new_callable=AsyncMock) as mock_lazy,
        ):
            mock_manager.get_instance.return_value = None
            mock_lazy.return_value = mock_instance

            from koda.services.mcp_bridge import handle_mcp_tool_call

            result = await handle_mcp_tool_call(
                "mcp_github__create_issue",
                {"title": "Bug report"},
                "agent-1",
            )

        assert result["success"] is True
        assert result["output"] == "Issue #42 created"
        mock_lazy.assert_awaited_once_with("github", "agent-1")

    @pytest.mark.asyncio
    async def test_lazy_start_failure_returns_error(self):
        with (
            patch("koda.services.mcp_bridge.mcp_server_manager") as mock_manager,
            patch("koda.services.mcp_bridge._lazy_start_mcp_server", new_callable=AsyncMock) as mock_lazy,
        ):
            mock_manager.get_instance.return_value = None
            mock_lazy.side_effect = RuntimeError("catalog not found")

            from koda.services.mcp_bridge import handle_mcp_tool_call

            result = await handle_mcp_tool_call(
                "mcp_github__create_issue",
                {},
                "agent-1",
            )

        assert result["success"] is False
        assert "failed to start" in result["output"]
        assert "catalog not found" in result["metadata"]["error"]


class TestMcpEndToEnd:
    """Test the full flow: register -> discover -> call."""

    @pytest.mark.asyncio
    async def test_full_flow_register_discover_call(self):
        # Clean state
        _agent_mcp_tools.pop("e2e-agent", None)

        # 1. Register tools using the bridge
        from koda.services.mcp_bridge import get_registered_mcp_tools, register_mcp_tools_for_agent

        handlers: dict[str, object] = {}
        write: set[str] = set()
        read: set[str] = set()

        connections = [
            {
                "server_key": "github",
                "cached_tools": [
                    {"name": "create_issue", "annotations": {"destructive_hint": True}},
                    {"name": "list_repos", "annotations": {"read_only_hint": True}},
                ],
            }
        ]

        registered = register_mcp_tools_for_agent("e2e-agent", connections, handlers, write, read)

        # 2. Verify tools are discoverable
        assert len(registered) == 2
        assert "mcp_github__create_issue" in get_registered_mcp_tools("e2e-agent")
        assert "mcp_github__list_repos" in get_registered_mcp_tools("e2e-agent")
        assert "mcp_github__create_issue" in write
        assert "mcp_github__list_repos" in read

        # 3. Call a tool through handle_mcp_tool_call
        mock_session = AsyncMock()
        mock_session.call_tool.return_value = McpToolCallResult(
            content=[{"type": "text", "text": "Issue #99 created"}],
            is_error=False,
        )

        mock_instance = MagicMock()
        mock_instance.started = True
        mock_instance.session = mock_session

        with patch("koda.services.mcp_bridge.mcp_server_manager") as mock_manager:
            mock_manager.get_instance.return_value = mock_instance

            from koda.services.mcp_bridge import handle_mcp_tool_call

            result = await handle_mcp_tool_call(
                "mcp_github__create_issue",
                {"title": "E2E Bug"},
                "e2e-agent",
            )

        # 4. Verify result
        assert result["success"] is True
        assert result["output"] == "Issue #99 created"
        assert result["metadata"]["server_key"] == "github"
        assert result["metadata"]["tool_name"] == "create_issue"

        # Cleanup
        _agent_mcp_tools.pop("e2e-agent", None)

    @pytest.mark.asyncio
    async def test_mcp_write_tool_classification_via_dispatcher(self):
        """Verify that MCP tools registered in _MCP_WRITE_TOOLS / _MCP_READ_TOOLS
        are correctly classified by _is_write_tool."""
        from koda.services.tool_dispatcher import _MCP_READ_TOOLS, _MCP_WRITE_TOOLS, _is_write_tool

        # Temporarily add MCP tools
        _MCP_WRITE_TOOLS.add("mcp_test__write_op")
        _MCP_READ_TOOLS.add("mcp_test__read_op")

        try:
            assert _is_write_tool("mcp_test__write_op", {}) is True
            assert _is_write_tool("mcp_test__read_op", {}) is False
        finally:
            _MCP_WRITE_TOOLS.discard("mcp_test__write_op")
            _MCP_READ_TOOLS.discard("mcp_test__read_op")
