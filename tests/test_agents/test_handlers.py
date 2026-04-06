"""Tests for inter-agent tool handlers in tool_dispatcher."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from koda.services.tool_dispatcher import (
    ToolContext,
    _handle_agent_broadcast,
    _handle_agent_delegate,
    _handle_agent_list_agents,
    _handle_agent_receive,
    _handle_agent_send,
)


@pytest.fixture
def ctx() -> ToolContext:
    return ToolContext(
        user_id=1,
        chat_id=1,
        work_dir="/tmp",
        user_data={},
        agent=None,
        agent_mode="normal",
    )


# --- disabled flag ---


@pytest.mark.asyncio
async def test_send_disabled(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", False)
    result = await _handle_agent_send({"to": "a", "message": "hi"}, ctx)
    assert not result.success
    assert "not enabled" in result.output


@pytest.mark.asyncio
async def test_receive_disabled(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", False)
    result = await _handle_agent_receive({}, ctx)
    assert not result.success


@pytest.mark.asyncio
async def test_delegate_disabled(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", False)
    result = await _handle_agent_delegate({"to": "a", "task": "x"}, ctx)
    assert not result.success


@pytest.mark.asyncio
async def test_list_agents_disabled(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", False)
    result = await _handle_agent_list_agents({}, ctx)
    assert not result.success


@pytest.mark.asyncio
async def test_broadcast_disabled(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", False)
    result = await _handle_agent_broadcast({"message": "hi"}, ctx)
    assert not result.success


# --- missing params ---


@pytest.mark.asyncio
async def test_send_missing_params(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    result = await _handle_agent_send({}, ctx)
    assert not result.success
    assert "Missing" in result.output


@pytest.mark.asyncio
async def test_delegate_missing_params(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    result = await _handle_agent_delegate({"to": "a"}, ctx)
    assert not result.success
    assert "Missing" in result.output


@pytest.mark.asyncio
async def test_broadcast_missing_params(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    result = await _handle_agent_broadcast({}, ctx)
    assert not result.success
    assert "Missing" in result.output


# --- success paths ---


@pytest.mark.asyncio
async def test_send_success(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    mock_bus = AsyncMock()
    mock_bus.send = AsyncMock(return_value="msg-1-abc")
    with patch("koda.agents.get_message_bus", return_value=mock_bus):
        result = await _handle_agent_send({"to": "agent-2", "message": "hello"}, ctx)
    assert result.success
    assert "msg-1-abc" in result.output


@pytest.mark.asyncio
async def test_send_inbox_full(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    mock_bus = AsyncMock()
    mock_bus.send = AsyncMock(return_value="Error: inbox full for agent 'x'.")
    with patch("koda.agents.get_message_bus", return_value=mock_bus):
        result = await _handle_agent_send({"to": "x", "message": "hi"}, ctx)
    assert not result.success


@pytest.mark.asyncio
async def test_receive_success(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)

    from koda.agents.models import AgentMessage

    mock_bus = AsyncMock()
    mock_bus.receive = AsyncMock(return_value=AgentMessage(from_agent="a1", to_agent="default", content="hi there"))
    with patch("koda.agents.get_message_bus", return_value=mock_bus):
        result = await _handle_agent_receive({"timeout": 5}, ctx)
    assert result.success
    assert "a1" in result.output
    assert "hi there" in result.output


@pytest.mark.asyncio
async def test_receive_timeout(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    mock_bus = AsyncMock()
    mock_bus.receive = AsyncMock(return_value=None)
    with patch("koda.agents.get_message_bus", return_value=mock_bus):
        result = await _handle_agent_receive({"timeout": 1}, ctx)
    assert not result.success
    assert "No message" in result.output


@pytest.mark.asyncio
async def test_list_agents_success(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    mock_bus = AsyncMock()
    mock_bus.list_agents = lambda: [
        {"agent_id": "a1", "inbox_size": 0, "inbox_max": 100},
        {"agent_id": "a2", "inbox_size": 3, "inbox_max": 100},
    ]
    with patch("koda.agents.get_message_bus", return_value=mock_bus):
        result = await _handle_agent_list_agents({}, ctx)
    assert result.success
    assert "a1" in result.output
    assert "a2" in result.output


@pytest.mark.asyncio
async def test_list_agents_empty(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    mock_bus = AsyncMock()
    mock_bus.list_agents = lambda: []
    with patch("koda.agents.get_message_bus", return_value=mock_bus):
        result = await _handle_agent_list_agents({}, ctx)
    assert result.success
    assert "No agents" in result.output


@pytest.mark.asyncio
async def test_broadcast_success(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    mock_bus = AsyncMock()
    mock_bus.broadcast = AsyncMock(return_value=3)
    with patch("koda.agents.get_message_bus", return_value=mock_bus):
        result = await _handle_agent_broadcast({"message": "update"}, ctx)
    assert result.success
    assert "3" in result.output


@pytest.mark.asyncio
async def test_delegate_success(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)

    from koda.agents.models import DelegationResult

    mock_bus = AsyncMock()
    mock_bus.delegate = AsyncMock(
        return_value=DelegationResult(
            request_id="r1", from_agent="default", to_agent="a2", success=True, result="analysis done"
        )
    )
    with patch("koda.agents.get_message_bus", return_value=mock_bus):
        result = await _handle_agent_delegate({"to": "a2", "task": "analyze"}, ctx)
    assert result.success
    assert "analysis done" in result.output


@pytest.mark.asyncio
async def test_delegate_failure(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)

    from koda.agents.models import DelegationResult

    mock_bus = AsyncMock()
    mock_bus.delegate = AsyncMock(
        return_value=DelegationResult(
            request_id="r1", from_agent="default", to_agent="a2", success=False, error="timeout"
        )
    )
    with patch("koda.agents.get_message_bus", return_value=mock_bus):
        result = await _handle_agent_delegate({"to": "a2", "task": "x"}, ctx)
    assert not result.success
    assert "timeout" in result.output


# --- prompt section ---


def test_inter_agent_prompt_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_prompt.INTER_AGENT_ENABLED", True)
    monkeypatch.setattr("koda.services.tool_prompt.BROWSER_FEATURES_ENABLED", False)
    monkeypatch.setattr("koda.services.tool_prompt.POSTGRES_ENABLED", False)
    monkeypatch.setattr("koda.services.tool_prompt.GWS_ENABLED", False)
    monkeypatch.setattr("koda.services.tool_prompt.JIRA_ENABLED", False)
    monkeypatch.setattr("koda.services.tool_prompt.CONFLUENCE_ENABLED", False)

    from koda.services.tool_prompt import build_agent_tools_prompt

    prompt = build_agent_tools_prompt()
    assert "Inter-Agent Communication" in prompt
    assert "agent_send" not in prompt
    assert "agent_receive" not in prompt
    assert "agent_delegate" not in prompt
    assert "agent_list_agents" not in prompt
    assert "agent_broadcast" not in prompt


def test_inter_agent_prompt_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_prompt.INTER_AGENT_ENABLED", False)
    monkeypatch.setattr("koda.services.tool_prompt.BROWSER_FEATURES_ENABLED", False)
    monkeypatch.setattr("koda.services.tool_prompt.POSTGRES_ENABLED", False)
    monkeypatch.setattr("koda.services.tool_prompt.GWS_ENABLED", False)
    monkeypatch.setattr("koda.services.tool_prompt.JIRA_ENABLED", False)
    monkeypatch.setattr("koda.services.tool_prompt.CONFLUENCE_ENABLED", False)

    from koda.services.tool_prompt import build_agent_tools_prompt

    prompt = build_agent_tools_prompt()
    assert "Inter-Agent Communication" not in prompt
