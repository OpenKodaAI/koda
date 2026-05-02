"""Tests for the MCP bridge — registration of tools + resources + prompts."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from koda.services.mcp_bridge import (
    MCP_PROMPT_INFIX,
    MCP_RESOURCE_INFIX,
    _agent_mcp_tools,
    _agent_prompt_lookup,
    _agent_resource_lookup,
    is_mcp_tool,
    mcp_prompt_tool_id,
    mcp_resource_tool_id,
    mcp_tool_id,
    parse_mcp_tool_id,
    register_mcp_capabilities_for_agent,
    register_mcp_prompts_for_agent,
    register_mcp_resources_for_agent,
    register_mcp_tools_for_agent,
    unregister_mcp_tools_for_agent,
)


def _reset_agent(agent_id: str) -> None:
    _agent_mcp_tools.pop(agent_id, None)
    keys_to_drop = [(a, t) for (a, t) in _agent_resource_lookup if a == agent_id]
    for k in keys_to_drop:
        _agent_resource_lookup.pop(k, None)
    keys_to_drop_p = [(a, t) for (a, t) in _agent_prompt_lookup if a == agent_id]
    for k in keys_to_drop_p:
        _agent_prompt_lookup.pop(k, None)


def test_mcp_tool_id_round_trip():
    tid = mcp_tool_id("supabase", "execute_sql")
    assert parse_mcp_tool_id(tid) == ("supabase", "execute_sql")
    assert is_mcp_tool(tid)


def test_mcp_resource_tool_id_uses_distinct_infix():
    rid = mcp_resource_tool_id("postgres_mcp", "postgres://server/db")
    assert MCP_RESOURCE_INFIX in rid
    assert MCP_PROMPT_INFIX not in rid


def test_mcp_prompt_tool_id_sanitizes_name():
    pid = mcp_prompt_tool_id("notion", "summarize page!")
    assert pid.endswith("summarize_page_")
    assert MCP_PROMPT_INFIX in pid


def test_register_resources_uses_synthetic_ids_and_classifies_read_only():
    agent = "AGENT_RES"
    _reset_agent(agent)
    handlers: dict[str, Any] = {}
    read_tools: set[str] = set()
    resources = [
        {"uri": "postgres://srv/db", "name": "Production DB"},
        {"uri": "file:///etc/config", "name": "Config", "mime_type": "text/plain"},
    ]
    with patch("koda.services.mcp_bridge._blocked_mcp_capability_names", return_value=set()):
        registered = register_mcp_resources_for_agent(agent, "postgres_mcp", resources, handlers, read_tools)
    assert len(registered) == 2
    for tid in registered:
        assert MCP_RESOURCE_INFIX in tid
        assert tid in read_tools
        assert tid in handlers
        assert (agent, tid) in _agent_resource_lookup
    _reset_agent(agent)


def test_register_resources_skips_blocked_uris():
    agent = "AGENT_BLOCK"
    _reset_agent(agent)
    handlers: dict[str, Any] = {}
    read_tools: set[str] = set()
    resources = [
        {"uri": "postgres://srv/db", "name": "Allowed"},
        {"uri": "secret://tokens", "name": "Blocked"},
    ]
    with patch(
        "koda.services.mcp_bridge._blocked_mcp_capability_names",
        return_value={"secret://tokens"},
    ):
        registered = register_mcp_resources_for_agent(agent, "any", resources, handlers, read_tools)
    assert len(registered) == 1
    assert all("secret://tokens" not in str(_agent_resource_lookup.get((agent, t))) for t in registered)
    _reset_agent(agent)


def test_register_prompts_classifies_as_write():
    agent = "AGENT_PROMPT"
    _reset_agent(agent)
    handlers: dict[str, Any] = {}
    write_tools: set[str] = set()
    prompts = [{"name": "summarize"}, {"name": "translate"}]
    with patch("koda.services.mcp_bridge._blocked_mcp_capability_names", return_value=set()):
        registered = register_mcp_prompts_for_agent(agent, "notion", prompts, handlers, write_tools)
    assert len(registered) == 2
    for tid in registered:
        assert MCP_PROMPT_INFIX in tid
        assert tid in write_tools
        assert tid in handlers
    _reset_agent(agent)


def test_register_capabilities_unifies_tools_resources_prompts():
    agent = "AGENT_ALL"
    _reset_agent(agent)
    handlers: dict[str, Any] = {}
    read_tools: set[str] = set()
    write_tools: set[str] = set()
    tools = [
        {
            "name": "list_items",
            "annotations": {"read_only_hint": True},
        },
        {"name": "create_item"},
    ]
    resources = [{"uri": "items://catalog"}]
    prompts = [{"name": "draft_email"}]
    with (
        patch("koda.services.mcp_bridge._blocked_mcp_capability_names", return_value=set()),
        patch("koda.services.mcp_bridge._blocked_mcp_tool_names", return_value=set()),
    ):
        result = register_mcp_capabilities_for_agent(
            agent,
            "demo",
            tools,
            resources,
            prompts,
            handlers,
            write_tools,
            read_tools,
        )
    assert len(result["tools"]) == 2
    assert len(result["resources"]) == 1
    assert len(result["prompts"]) == 1
    # All registered IDs were added to the agent's set
    expected = set(result["tools"]) | set(result["resources"]) | set(result["prompts"])
    assert expected <= _agent_mcp_tools[agent]
    _reset_agent(agent)


def test_unregister_clears_lookup_indices():
    agent = "AGENT_UNREG"
    _reset_agent(agent)
    handlers: dict[str, Any] = {}
    read_tools: set[str] = set()
    write_tools: set[str] = set()
    tools = [{"name": "tool1", "annotations": {"read_only_hint": True}}]
    with (
        patch("koda.services.mcp_bridge._blocked_mcp_capability_names", return_value=set()),
        patch("koda.services.mcp_bridge._blocked_mcp_tool_names", return_value=set()),
    ):
        register_mcp_capabilities_for_agent(
            agent,
            "demo",
            tools,
            [{"uri": "test://r"}],
            [{"name": "p"}],
            handlers,
            write_tools,
            read_tools,
        )
    assert len(_agent_mcp_tools[agent]) == 3
    unregister_mcp_tools_for_agent(agent, handlers, write_tools, read_tools)
    assert agent not in _agent_mcp_tools
    assert all((agent, t) not in _agent_resource_lookup for t in handlers)
    assert all((agent, t) not in _agent_prompt_lookup for t in handlers)


def test_register_tools_with_blocked_skips_those():
    agent = "AGENT_TOOL_BLOCK"
    _reset_agent(agent)
    handlers: dict[str, Any] = {}
    read_tools: set[str] = set()
    write_tools: set[str] = set()
    tools = [{"name": "ok"}, {"name": "blocked_one"}]
    with patch(
        "koda.services.mcp_bridge._blocked_mcp_tool_names",
        return_value={"blocked_one"},
    ):
        registered = register_mcp_tools_for_agent(
            agent,
            [{"server_key": "srv", "cached_tools": tools}],
            handlers,
            write_tools,
            read_tools,
        )
    assert any(t.endswith("ok") for t in registered)
    assert all(not t.endswith("blocked_one") for t in registered)
    _reset_agent(agent)
