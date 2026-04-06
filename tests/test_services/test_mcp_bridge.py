"""Tests for MCP bridge between MCP servers and tool dispatch."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.services.mcp_bridge import (
    _agent_mcp_tools,
    classify_mcp_tool_rw,
    get_registered_mcp_tools,
    handle_mcp_tool_call,
    is_mcp_tool,
    mcp_tool_id,
    parse_mcp_tool_id,
    register_mcp_tools_for_agent,
    resolve_mcp_tool_policy,
    unregister_mcp_tools_for_agent,
)
from koda.services.mcp_client import McpToolAnnotations, McpToolCallResult

# --- mcp_tool_id ---


def test_mcp_tool_id_format():
    result = mcp_tool_id("github", "create_issue")
    assert result == "mcp_github__create_issue"


# --- parse_mcp_tool_id ---


def test_parse_mcp_tool_id_valid():
    result = parse_mcp_tool_id("mcp_github__create_issue")
    assert result == ("github", "create_issue")


def test_parse_mcp_tool_id_invalid():
    assert parse_mcp_tool_id("native_tool") is None
    assert parse_mcp_tool_id("web_search") is None
    assert parse_mcp_tool_id("") is None


def test_parse_mcp_tool_id_no_separator():
    assert parse_mcp_tool_id("mcp_noseparator") is None


def test_parse_mcp_tool_id_empty_parts():
    assert parse_mcp_tool_id("mcp___tool") is None
    assert parse_mcp_tool_id("mcp_server__") is None


# --- is_mcp_tool ---


def test_is_mcp_tool():
    assert is_mcp_tool("mcp_github__create_issue") is True
    assert is_mcp_tool("mcp_slack__post_message") is True
    assert is_mcp_tool("web_search") is False
    assert is_mcp_tool("file_read") is False


# --- classify_mcp_tool_rw ---


def test_classify_rw_no_annotations():
    assert classify_mcp_tool_rw(None) is True


def test_classify_rw_read_only_hint():
    annotations = McpToolAnnotations(read_only_hint=True)
    assert classify_mcp_tool_rw(annotations) is False


def test_classify_rw_destructive_hint():
    annotations = McpToolAnnotations(destructive_hint=True)
    assert classify_mcp_tool_rw(annotations) is True


def test_classify_rw_no_hints():
    annotations = McpToolAnnotations(title="Some tool")
    assert classify_mcp_tool_rw(annotations) is True


# --- resolve_mcp_tool_policy ---


def test_resolve_policy_explicit_blocked():
    policies = {"my_tool": "blocked"}
    assert resolve_mcp_tool_policy(policies, "my_tool", None) == "blocked"


def test_resolve_policy_explicit_always_ask():
    policies = {"my_tool": "always_ask"}
    assert resolve_mcp_tool_policy(policies, "my_tool", None) == "always_ask"


def test_resolve_policy_explicit_always_allow():
    policies = {"my_tool": "always_allow"}
    assert resolve_mcp_tool_policy(policies, "my_tool", None) == "always_allow"


def test_resolve_policy_auto_default():
    policies: dict[str, str] = {}
    assert resolve_mcp_tool_policy(policies, "my_tool", None) == "auto"


def test_resolve_policy_explicit_auto():
    policies = {"my_tool": "auto"}
    assert resolve_mcp_tool_policy(policies, "my_tool", None) == "auto"


# --- handle_mcp_tool_call ---


@pytest.mark.asyncio
async def test_handle_mcp_tool_call_success():
    mock_session = AsyncMock()
    mock_session.call_tool.return_value = McpToolCallResult(
        content=[{"type": "text", "text": "Issue #42 created"}],
        is_error=False,
    )

    mock_instance = MagicMock()
    mock_instance.started = True
    mock_instance.session = mock_session

    with patch("koda.services.mcp_bridge.mcp_server_manager") as mock_manager:
        mock_manager.get_instance.return_value = mock_instance

        result = await handle_mcp_tool_call(
            "mcp_github__create_issue",
            {"title": "Bug report"},
            "agent-1",
        )

    assert result["success"] is True
    assert result["output"] == "Issue #42 created"
    assert result["metadata"]["server_key"] == "github"
    assert result["metadata"]["tool_name"] == "create_issue"
    assert result["metadata"]["integration_id"] == "mcp"
    mock_session.call_tool.assert_awaited_once_with("create_issue", {"title": "Bug report"})


@pytest.mark.asyncio
async def test_handle_mcp_tool_call_server_not_running():
    with (
        patch("koda.services.mcp_bridge.mcp_server_manager") as mock_manager,
        patch("koda.services.mcp_bridge._lazy_start_mcp_server", new_callable=AsyncMock) as mock_lazy,
    ):
        mock_manager.get_instance.return_value = None
        mock_lazy.return_value = None

        result = await handle_mcp_tool_call(
            "mcp_github__create_issue",
            {},
            "agent-1",
        )

    assert result["success"] is False
    assert "could not be started" in result["output"]


@pytest.mark.asyncio
async def test_handle_mcp_tool_call_server_not_started():
    mock_instance = MagicMock()
    mock_instance.started = False

    with (
        patch("koda.services.mcp_bridge.mcp_server_manager") as mock_manager,
        patch("koda.services.mcp_bridge._lazy_start_mcp_server", new_callable=AsyncMock) as mock_lazy,
    ):
        mock_manager.get_instance.return_value = mock_instance
        mock_lazy.return_value = None

        result = await handle_mcp_tool_call(
            "mcp_github__create_issue",
            {},
            "agent-1",
        )

    assert result["success"] is False
    assert "could not be started" in result["output"]


@pytest.mark.asyncio
async def test_handle_mcp_tool_call_invalid_tool_id():
    result = await handle_mcp_tool_call("web_search", {}, "agent-1")
    assert result["success"] is False
    assert "Invalid MCP tool ID" in result["output"]


@pytest.mark.asyncio
async def test_handle_mcp_tool_call_exception():
    mock_session = AsyncMock()
    mock_session.call_tool.side_effect = RuntimeError("connection lost")

    mock_instance = MagicMock()
    mock_instance.started = True
    mock_instance.session = mock_session

    with patch("koda.services.mcp_bridge.mcp_server_manager") as mock_manager:
        mock_manager.get_instance.return_value = mock_instance

        result = await handle_mcp_tool_call(
            "mcp_github__create_issue",
            {},
            "agent-1",
        )

    assert result["success"] is False
    assert "MCP tool error" in result["output"]
    assert result["metadata"]["error"] == "connection lost"


@pytest.mark.asyncio
async def test_handle_mcp_tool_call_image_content():
    mock_session = AsyncMock()
    mock_session.call_tool.return_value = McpToolCallResult(
        content=[{"type": "image", "mimeType": "image/png", "data": "..."}],
        is_error=False,
    )

    mock_instance = MagicMock()
    mock_instance.started = True
    mock_instance.session = mock_session

    with patch("koda.services.mcp_bridge.mcp_server_manager") as mock_manager:
        mock_manager.get_instance.return_value = mock_instance

        result = await handle_mcp_tool_call(
            "mcp_github__get_avatar",
            {},
            "agent-1",
        )

    assert result["success"] is True
    assert "[Image: image/png]" in result["output"]


@pytest.mark.asyncio
async def test_handle_mcp_tool_call_empty_result():
    mock_session = AsyncMock()
    mock_session.call_tool.return_value = McpToolCallResult(
        content=[],
        is_error=False,
    )

    mock_instance = MagicMock()
    mock_instance.started = True
    mock_instance.session = mock_session

    with patch("koda.services.mcp_bridge.mcp_server_manager") as mock_manager:
        mock_manager.get_instance.return_value = mock_instance

        result = await handle_mcp_tool_call(
            "mcp_github__ping",
            {},
            "agent-1",
        )

    assert result["success"] is True
    assert result["output"] == "(empty result)"


# --- register / unregister ---


def test_register_mcp_tools():
    # Clean state
    _agent_mcp_tools.pop("test-agent", None)

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

    registered = register_mcp_tools_for_agent("test-agent", connections, handlers, write, read)

    assert len(registered) == 2
    assert "mcp_github__create_issue" in registered
    assert "mcp_github__list_repos" in registered
    assert "mcp_github__create_issue" in handlers
    assert "mcp_github__list_repos" in handlers
    assert "mcp_github__create_issue" in write
    assert "mcp_github__list_repos" in read
    assert "mcp_github__list_repos" not in write
    assert "mcp_github__create_issue" not in read

    # Clean up
    _agent_mcp_tools.pop("test-agent", None)


def test_register_mcp_tools_read_only():
    _agent_mcp_tools.pop("test-agent-ro", None)

    handlers: dict[str, object] = {}
    write: set[str] = set()
    read: set[str] = set()

    connections = [
        {
            "server_key": "slack",
            "cached_tools": [
                {"name": "list_channels", "annotations": {"read_only_hint": True}},
            ],
        }
    ]

    registered = register_mcp_tools_for_agent("test-agent-ro", connections, handlers, write, read)

    assert len(registered) == 1
    tid = "mcp_slack__list_channels"
    assert tid in read
    assert tid not in write

    _agent_mcp_tools.pop("test-agent-ro", None)


def test_unregister_mcp_tools():
    handlers: dict[str, object] = {}
    write: set[str] = set()
    read: set[str] = set()

    connections = [
        {
            "server_key": "github",
            "cached_tools": [
                {"name": "create_issue"},
                {"name": "list_repos", "annotations": {"read_only_hint": True}},
            ],
        }
    ]

    register_mcp_tools_for_agent("cleanup-agent", connections, handlers, write, read)
    assert len(handlers) == 2
    assert len(write) + len(read) == 2

    unregister_mcp_tools_for_agent("cleanup-agent", handlers, write, read)
    assert len(handlers) == 0
    assert len(write) == 0
    assert len(read) == 0
    assert get_registered_mcp_tools("cleanup-agent") == set()


def test_get_registered_mcp_tools_empty():
    assert get_registered_mcp_tools("nonexistent-agent") == set()


def test_register_mcp_tools_skip_empty_name():
    _agent_mcp_tools.pop("skip-agent", None)

    handlers: dict[str, object] = {}
    write: set[str] = set()
    read: set[str] = set()

    connections = [
        {
            "server_key": "github",
            "cached_tools": [
                {"name": ""},
                {"name": "valid_tool"},
            ],
        }
    ]

    registered = register_mcp_tools_for_agent("skip-agent", connections, handlers, write, read)

    assert len(registered) == 1
    assert "mcp_github__valid_tool" in registered

    _agent_mcp_tools.pop("skip-agent", None)


# --- handler closure ---


@pytest.mark.asyncio
async def test_handler_closure_delegates_to_handle_mcp_tool_call():
    """Registered handler closure should delegate to handle_mcp_tool_call."""
    _agent_mcp_tools.pop("closure-agent", None)

    handlers: dict[str, object] = {}
    write: set[str] = set()
    read: set[str] = set()

    connections = [
        {
            "server_key": "github",
            "cached_tools": [
                {"name": "create_issue", "annotations": {"destructive_hint": True}},
            ],
        }
    ]

    register_mcp_tools_for_agent("closure-agent", connections, handlers, write, read)

    tid = "mcp_github__create_issue"
    assert tid in handlers
    handler = handlers[tid]
    assert handler is not None
    assert callable(handler)

    # Mock handle_mcp_tool_call so we don't need a real MCP server
    mock_ctx = MagicMock()
    with patch("koda.services.mcp_bridge.handle_mcp_tool_call", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = {
            "success": True,
            "output": "Issue created",
            "metadata": {"server_key": "github"},
        }
        result = await handler({"title": "Bug"}, mock_ctx)

    mock_call.assert_awaited_once_with(tid, {"title": "Bug"}, "closure-agent")
    assert result.success is True
    assert result.output == "Issue created"
    assert result.tool == tid

    _agent_mcp_tools.pop("closure-agent", None)


def test_rw_classification_write_tool_in_correct_sets():
    """Write tools should be in write_tools and not in read_tools."""
    _agent_mcp_tools.pop("rw-agent", None)

    handlers: dict[str, object] = {}
    write: set[str] = set()
    read: set[str] = set()

    connections = [
        {
            "server_key": "srv",
            "cached_tools": [
                {"name": "delete_item", "annotations": {"destructive_hint": True}},
            ],
        }
    ]

    register_mcp_tools_for_agent("rw-agent", connections, handlers, write, read)
    tid = "mcp_srv__delete_item"
    assert tid in write
    assert tid not in read

    _agent_mcp_tools.pop("rw-agent", None)


def test_rw_classification_read_tool_in_correct_sets():
    """Read-only tools should be in read_tools and not in write_tools."""
    _agent_mcp_tools.pop("rw-agent2", None)

    handlers: dict[str, object] = {}
    write: set[str] = set()
    read: set[str] = set()

    connections = [
        {
            "server_key": "srv",
            "cached_tools": [
                {"name": "list_items", "annotations": {"read_only_hint": True}},
            ],
        }
    ]

    register_mcp_tools_for_agent("rw-agent2", connections, handlers, write, read)
    tid = "mcp_srv__list_items"
    assert tid in read
    assert tid not in write

    _agent_mcp_tools.pop("rw-agent2", None)


def test_rw_classification_reclassifies_on_reregister():
    """When re-registering a tool with different annotations, sets should be updated."""
    _agent_mcp_tools.pop("reclass-agent", None)

    handlers: dict[str, object] = {}
    write: set[str] = set()
    read: set[str] = set()

    # First register as write
    connections_write = [
        {
            "server_key": "srv",
            "cached_tools": [
                {"name": "toggle_item", "annotations": {"destructive_hint": True}},
            ],
        }
    ]
    register_mcp_tools_for_agent("reclass-agent", connections_write, handlers, write, read)
    tid = "mcp_srv__toggle_item"
    assert tid in write
    assert tid not in read

    # Re-register as read
    connections_read = [
        {
            "server_key": "srv",
            "cached_tools": [
                {"name": "toggle_item", "annotations": {"read_only_hint": True}},
            ],
        }
    ]
    register_mcp_tools_for_agent("reclass-agent", connections_read, handlers, write, read)
    assert tid in read
    assert tid not in write

    _agent_mcp_tools.pop("reclass-agent", None)


# --- _infer_tool_category in tool_dispatcher ---


def test_tool_dispatcher_infer_category_mcp():
    from koda.services.tool_dispatcher import _infer_tool_category

    assert _infer_tool_category("mcp_github__create_issue") == "mcp"
    assert _infer_tool_category("mcp_slack__post_message") == "mcp"
    assert _infer_tool_category("mcp_anything") == "mcp"
    # Non-MCP tools should not return "mcp"
    assert _infer_tool_category("file_read") != "mcp"
    assert _infer_tool_category("web_search") != "mcp"
