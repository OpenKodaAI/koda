"""Tests for inter-agent tool handlers in tool_dispatcher."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.services.tool_dispatcher import (
    ToolContext,
    _handle_agent_broadcast,
    _handle_agent_delegate,
    _handle_agent_list_agents,
    _handle_agent_receive,
    _handle_agent_send,
    _handle_squad_capabilities,
    _handle_squad_context,
    _handle_squad_coordinator_demote,
    _handle_squad_coordinator_elect,
    _handle_squad_coordinator_get,
    _handle_squad_dashboard_overview,
    _handle_squad_inbox_drain,
    _handle_squad_post,
    _handle_squad_router_tick,
    _handle_squad_task_claim,
    _handle_squad_task_complete,
    _handle_squad_task_create,
    _handle_squad_task_escalate,
    _handle_squad_task_list,
    _handle_squad_task_update,
    _handle_squad_telegram_bind,
    _handle_squad_telegram_binding_get,
    _handle_squad_telegram_post,
    _handle_squad_telegram_unbind,
    _handle_squad_thread_create,
    _handle_squad_thread_history,
    _handle_squad_thread_overview,
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

    from koda.services.tool_prompt import build_agent_tools_prompt

    prompt = build_agent_tools_prompt()
    assert "Inter-Agent Communication" not in prompt


# --- squad thread handlers ---


@pytest.mark.asyncio
async def test_squad_thread_create_disabled(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", False)
    result = await _handle_squad_thread_create({"workspace_id": "w", "squad_id": "s"}, ctx)
    assert not result.success


@pytest.mark.asyncio
async def test_squad_thread_create_missing_params(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    result = await _handle_squad_thread_create({}, ctx)
    assert not result.success
    assert "Missing" in result.output


@pytest.mark.asyncio
async def test_squad_thread_create_no_store(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    with patch("koda.squads.get_squad_thread_store", return_value=None):
        result = await _handle_squad_thread_create(
            {"workspace_id": "w", "squad_id": "s", "title": "t"},
            ctx,
        )
    assert not result.success
    assert "unavailable" in result.output


@pytest.mark.asyncio
async def test_squad_thread_create_success(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    from decimal import Decimal

    from koda.squads.threads import ThreadDescriptor

    descriptor = ThreadDescriptor(
        id="00000000-0000-0000-0000-000000000001",
        workspace_id="w",
        squad_id="s",
        owner_user_id=1,
        title="t",
        status="open",
        coordinator_agent_id="PM",
        current_owner_agent_id=None,
        parent_thread_id=None,
        visibility="squad",
        telegram_chat_id=None,
        telegram_message_thread_id=None,
        budget_usd_cap=None,
        cost_usd_accum=Decimal(0),
    )
    mock_store = AsyncMock()
    mock_store.create_thread = AsyncMock(return_value=descriptor)
    with patch("koda.squads.get_squad_thread_store", return_value=mock_store):
        result = await _handle_squad_thread_create(
            {
                "workspace_id": "w",
                "squad_id": "s",
                "title": "t",
                "coordinator_agent_id": "PM",
                "participants": [{"agent_id": "FE", "role": "worker"}],
            },
            ctx,
        )
    assert result.success
    assert "created" in result.output
    mock_store.create_thread.assert_awaited_once()


@pytest.mark.asyncio
async def test_squad_post_missing_params(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    result = await _handle_squad_post({}, ctx)
    assert not result.success
    assert "Missing" in result.output


@pytest.mark.asyncio
async def test_squad_post_success(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    mock_store = AsyncMock()
    mock_store.post_thread_message = AsyncMock(return_value=42)
    with patch("koda.squads.get_squad_thread_store", return_value=mock_store):
        result = await _handle_squad_post(
            {"thread_id": "00000000-0000-0000-0000-000000000001", "content": "hi team"},
            ctx,
        )
    assert result.success
    assert "msg-42" in result.output
    mock_store.post_thread_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_squad_thread_history_missing_params(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    result = await _handle_squad_thread_history({}, ctx)
    assert not result.success
    assert "Missing" in result.output


@pytest.mark.asyncio
async def test_squad_thread_history_success(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    mock_store = AsyncMock()
    mock_store.thread_history = AsyncMock(
        return_value=[
            {
                "id": 1,
                "from": "PM",
                "to": None,
                "content": "Kickoff",
                "type": "agent_text",
                "metadata": {},
                "created_at": None,
            }
        ]
    )
    with patch("koda.squads.get_squad_thread_store", return_value=mock_store):
        result = await _handle_squad_thread_history(
            {"thread_id": "00000000-0000-0000-0000-000000000001", "limit": 10},
            ctx,
        )
    assert result.success
    assert "Kickoff" in result.output


# --- squad task handlers ---


def _task_descriptor(**overrides: object) -> object:
    from decimal import Decimal

    from koda.squads.tasks import TaskDescriptor

    base: dict[str, object] = {
        "id": "00000000-0000-0000-0000-000000000010",
        "thread_id": "00000000-0000-0000-0000-000000000001",
        "parent_task_id": None,
        "depends_on": [],
        "assigned_agent_id": None,
        "assigner_agent_id": "PM",
        "kind": "",
        "title": "x",
        "description": "",
        "status": "pending",
        "acceptance_criteria": [],
        "deliverables_spec": [],
        "delivered_artifact_ids": [],
        "claim_token": None,
        "claim_expires_at": None,
        "delegation_depth": 0,
        "idempotency_key": None,
        "cost_usd_so_far": Decimal(0),
        "runtime_task_id": None,
        "version": 1,
    }
    base.update(overrides)
    return TaskDescriptor(**base)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_squad_task_create_disabled(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", False)
    result = await _handle_squad_task_create({"thread_id": "t", "title": "x"}, ctx)
    assert not result.success


@pytest.mark.asyncio
async def test_squad_task_create_missing_params(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    result = await _handle_squad_task_create({"thread_id": "t"}, ctx)
    assert not result.success
    assert "Missing" in result.output


@pytest.mark.asyncio
async def test_squad_task_create_success(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    mock_store = AsyncMock()
    mock_store.create_task = AsyncMock(return_value=_task_descriptor(status="pending"))
    with patch("koda.squads.get_squad_task_store", return_value=mock_store):
        result = await _handle_squad_task_create(
            {"thread_id": "t", "title": "research", "kind": "research"},
            ctx,
        )
    assert result.success
    assert "created" in result.output


@pytest.mark.asyncio
async def test_squad_task_claim_missing_params(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    result = await _handle_squad_task_claim({}, ctx)
    assert not result.success
    assert "Missing" in result.output


@pytest.mark.asyncio
async def test_squad_task_claim_conflict(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    from koda.squads.tasks import TaskClaimConflictError

    mock_store = AsyncMock()
    mock_store.claim_task = AsyncMock(side_effect=TaskClaimConflictError("already claimed by FE"))
    with patch("koda.squads.get_squad_task_store", return_value=mock_store):
        result = await _handle_squad_task_claim({"task_id": "x"}, ctx)
    assert not result.success
    assert "already claimed" in result.output


@pytest.mark.asyncio
async def test_squad_task_update_illegal(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    from koda.squads.tasks import IllegalTransitionError

    mock_store = AsyncMock()
    mock_store.update_task_status = AsyncMock(side_effect=IllegalTransitionError("bad transition"))
    with patch("koda.squads.get_squad_task_store", return_value=mock_store):
        result = await _handle_squad_task_update({"task_id": "x", "new_status": "in_progress"}, ctx)
    assert not result.success
    assert "Illegal transition" in result.output


@pytest.mark.asyncio
async def test_squad_task_complete_success(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    mock_store = AsyncMock()
    mock_store.update_task_status = AsyncMock(return_value=_task_descriptor(status="done", version=4))
    with patch("koda.squads.get_squad_task_store", return_value=mock_store):
        result = await _handle_squad_task_complete(
            {"task_id": "x", "result_summary": "ok", "deliverables": ["a-1"]},
            ctx,
        )
    assert result.success
    assert "done" in result.output


@pytest.mark.asyncio
async def test_squad_task_escalate_missing_reason(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    result = await _handle_squad_task_escalate({"task_id": "x"}, ctx)
    assert not result.success
    assert "Missing" in result.output


@pytest.mark.asyncio
async def test_squad_task_list_no_filter(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    result = await _handle_squad_task_list({}, ctx)
    assert not result.success
    assert "thread_id" in result.output or "assigned_agent_id" in result.output


@pytest.mark.asyncio
async def test_squad_task_list_success(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    mock_store = AsyncMock()
    mock_store.list_tasks = AsyncMock(
        return_value=[_task_descriptor(status="claimed", title="A"), _task_descriptor(status="pending", title="B")]
    )
    with patch("koda.squads.get_squad_task_store", return_value=mock_store):
        result = await _handle_squad_task_list({"thread_id": "t"}, ctx)
    assert result.success
    assert "2 task(s)" in result.output


# --- squad capability handler ---


@pytest.mark.asyncio
async def test_squad_capabilities_disabled(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", False)
    result = await _handle_squad_capabilities({"squad_id": "build"}, ctx)
    assert not result.success


@pytest.mark.asyncio
async def test_squad_capabilities_missing_squad_id(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    result = await _handle_squad_capabilities({}, ctx)
    assert not result.success
    assert "Missing" in result.output


@pytest.mark.asyncio
async def test_squad_capabilities_no_cache(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    with patch("koda.squads.get_capability_cache", return_value=None):
        result = await _handle_squad_capabilities({"squad_id": "build"}, ctx)
    assert not result.success
    assert "unavailable" in result.output


@pytest.mark.asyncio
async def test_squad_capabilities_empty_cache(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    mock_cache = AsyncMock()
    mock_cache.list_for_squad = AsyncMock(return_value=[])
    with patch("koda.squads.get_capability_cache", return_value=mock_cache):
        result = await _handle_squad_capabilities({"squad_id": "build"}, ctx)
    assert result.success
    assert "no cached" in result.output


@pytest.mark.asyncio
async def test_squad_capabilities_with_summaries(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    from koda.squads.capabilities import CapabilitySummary

    mock_cache = AsyncMock()
    mock_cache.list_for_squad = AsyncMock(
        return_value=[
            CapabilitySummary(agent_id="PM", display_name="PM", role="Product", is_coordinator=True),
            CapabilitySummary(agent_id="FE", display_name="Frontend", role="FE Eng"),
        ]
    )
    with patch("koda.squads.get_capability_cache", return_value=mock_cache):
        result = await _handle_squad_capabilities({"squad_id": "build", "exclude_agent_id": "FE"}, ctx)
    assert result.success
    assert "<squad_members>" in result.output
    assert "PM [PM] (coordinator)" in result.output
    assert "FE [FE]" not in result.output


# --- squad_context handler ---


@pytest.mark.asyncio
async def test_squad_context_disabled(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", False)
    result = await _handle_squad_context({"thread_id": "x"}, ctx)
    assert not result.success


@pytest.mark.asyncio
async def test_squad_context_missing_thread(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    result = await _handle_squad_context({}, ctx)
    assert not result.success
    assert "Missing" in result.output


@pytest.mark.asyncio
async def test_squad_context_uses_ctx_thread_id(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    ctx.squad_thread_id = "00000000-0000-0000-0000-000000000001"
    captured: dict[str, object] = {}

    async def fake_builder(**kwargs: object) -> str:
        captured.update(kwargs)
        return "<squad_context>OK</squad_context>"

    with patch("koda.squads.build_squad_context_block_default", side_effect=fake_builder):
        result = await _handle_squad_context({}, ctx)
    assert result.success
    assert captured["thread_id"] == "00000000-0000-0000-0000-000000000001"
    assert "OK" in result.output


@pytest.mark.asyncio
async def test_squad_context_block_unavailable(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    with patch("koda.squads.build_squad_context_block_default", AsyncMock(return_value=None)):
        result = await _handle_squad_context({"thread_id": "missing"}, ctx)
    assert not result.success
    assert "unavailable" in result.output


@pytest.mark.asyncio
async def test_squad_context_propagates_chain(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    ctx.delegation_chain = ["PM", "FE"]
    captured: dict[str, object] = {}

    async def fake_builder(**kwargs: object) -> str:
        captured.update(kwargs)
        return "<squad_context>OK</squad_context>"

    with patch("koda.squads.build_squad_context_block_default", side_effect=fake_builder):
        await _handle_squad_context({"thread_id": "x", "transcript_limit": 5}, ctx)
    assert captured["delegation_chain"] == ["PM", "FE"]
    assert captured["transcript_limit"] == 5


# --- coordinator handlers ---


def _coordinator_state(**overrides: object) -> object:
    from koda.squads.coordinator import CoordinatorState

    base: dict[str, object] = {
        "squad_id": "build",
        "coordinator_agent_id": "PM",
        "election_policy": "manual",
        "auto_demote_after_inactive_days": None,
        "elected_at": None,
        "elected_by_agent_id": "admin",
        "last_active_at": None,
        "metadata": {},
    }
    base.update(overrides)
    return CoordinatorState(**base)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_coordinator_elect_disabled(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", False)
    result = await _handle_squad_coordinator_elect({"squad_id": "build", "agent_id": "PM"}, ctx)
    assert not result.success


@pytest.mark.asyncio
async def test_coordinator_elect_missing_params(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    result = await _handle_squad_coordinator_elect({"squad_id": "build"}, ctx)
    assert not result.success
    assert "Missing" in result.output


@pytest.mark.asyncio
async def test_coordinator_elect_conflict(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    from koda.squads.coordinator import CoordinatorConflictError

    mock_service = AsyncMock()
    mock_service.elect = AsyncMock(side_effect=CoordinatorConflictError("already coord"))
    with patch("koda.squads.get_coordinator_service", return_value=mock_service):
        result = await _handle_squad_coordinator_elect({"squad_id": "build", "agent_id": "PM"}, ctx)
    assert not result.success
    assert "already coord" in result.output


@pytest.mark.asyncio
async def test_coordinator_elect_eligibility_error(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    from koda.squads.coordinator import CoordinatorEligibilityError

    mock_service = AsyncMock()
    mock_service.elect = AsyncMock(side_effect=CoordinatorEligibilityError("missing tools"))
    with patch("koda.squads.get_coordinator_service", return_value=mock_service):
        result = await _handle_squad_coordinator_elect(
            {
                "squad_id": "build",
                "agent_id": "PM",
                "validate_tool_ids": ["agent_delegate"],
            },
            ctx,
        )
    assert not result.success
    assert "missing tools" in result.output


@pytest.mark.asyncio
async def test_coordinator_elect_success(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    state = _coordinator_state(coordinator_agent_id="PM")
    mock_service = AsyncMock()
    mock_service.elect = AsyncMock(return_value=state)
    with (
        patch("koda.squads.get_coordinator_service", return_value=mock_service),
        patch("koda.squads.get_squad_thread_store", return_value=None),
    ):
        result = await _handle_squad_coordinator_elect(
            {"squad_id": "build", "agent_id": "PM", "reason": "kickoff"},
            ctx,
        )
    assert result.success
    assert "PM" in result.output
    mock_service.elect.assert_awaited_once()


@pytest.mark.asyncio
async def test_coordinator_demote_missing_squad(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    result = await _handle_squad_coordinator_demote({}, ctx)
    assert not result.success


@pytest.mark.asyncio
async def test_coordinator_demote_not_found(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    from koda.squads.coordinator import CoordinatorNotFoundError

    mock_service = AsyncMock()
    mock_service.demote = AsyncMock(side_effect=CoordinatorNotFoundError("none"))
    with (
        patch("koda.squads.get_coordinator_service", return_value=mock_service),
        patch("koda.squads.get_squad_thread_store", return_value=None),
    ):
        result = await _handle_squad_coordinator_demote({"squad_id": "build"}, ctx)
    assert not result.success
    assert "no active coordinator" in result.output


@pytest.mark.asyncio
async def test_coordinator_demote_success(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    state = _coordinator_state(coordinator_agent_id=None)
    mock_service = AsyncMock()
    mock_service.demote = AsyncMock(return_value=state)
    with (
        patch("koda.squads.get_coordinator_service", return_value=mock_service),
        patch("koda.squads.get_squad_thread_store", return_value=None),
    ):
        result = await _handle_squad_coordinator_demote({"squad_id": "build"}, ctx)
    assert result.success
    assert "now: none" in result.output


@pytest.mark.asyncio
async def test_coordinator_get_no_state(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    mock_service = AsyncMock()
    mock_service.current_coordinator = AsyncMock(return_value=None)
    mock_service.list_history = AsyncMock(return_value=[])
    with patch("koda.squads.get_coordinator_service", return_value=mock_service):
        result = await _handle_squad_coordinator_get({"squad_id": "build"}, ctx)
    assert result.success
    assert "no coordinator state" in result.output


@pytest.mark.asyncio
async def test_router_tick_disabled(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", False)
    result = await _handle_squad_router_tick({}, ctx)
    assert not result.success


@pytest.mark.asyncio
async def test_router_tick_no_router(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    with patch("koda.squads.get_squad_router", return_value=None):
        result = await _handle_squad_router_tick({}, ctx)
    assert not result.success
    assert "unavailable" in result.output


@pytest.mark.asyncio
async def test_router_tick_empty_sweep(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    from koda.squads.router import SweepReport

    mock_router = AsyncMock()
    mock_router.sweep_once = AsyncMock(return_value=SweepReport())
    with patch("koda.squads.get_squad_router", return_value=mock_router):
        result = await _handle_squad_router_tick({}, ctx)
    assert result.success
    assert "nothing expired" in result.output


@pytest.mark.asyncio
async def test_telegram_bind_disabled(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", False)
    result = await _handle_squad_telegram_bind({"squad_id": "build", "telegram_chat_id": -100}, ctx)
    assert not result.success


@pytest.mark.asyncio
async def test_telegram_bind_missing_params(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    result = await _handle_squad_telegram_bind({"squad_id": "build"}, ctx)
    assert not result.success
    assert "Missing" in result.output


@pytest.mark.asyncio
async def test_telegram_bind_chat_id_not_int(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    result = await _handle_squad_telegram_bind({"squad_id": "x", "telegram_chat_id": "not"}, ctx)
    assert not result.success
    assert "integer" in result.output


@pytest.mark.asyncio
async def test_telegram_bind_conflict(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    from koda.squads.telegram_bridge import TelegramBindingConflictError

    mock_service = AsyncMock()
    mock_service.bind = AsyncMock(side_effect=TelegramBindingConflictError("chat owned by other"))
    with patch("koda.squads.get_telegram_binding_service", return_value=mock_service):
        result = await _handle_squad_telegram_bind(
            {"squad_id": "build", "telegram_chat_id": -100},
            ctx,
        )
    assert not result.success
    assert "chat owned by other" in result.output


@pytest.mark.asyncio
async def test_telegram_bind_success(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    from koda.squads.telegram_bridge import SquadTelegramBinding

    binding = SquadTelegramBinding(
        squad_id="build",
        telegram_chat_id=-100,
        chat_title="Build",
        is_forum=True,
        bound_by_user_id=42,
        bound_at=None,
        updated_at=None,
    )
    mock_service = AsyncMock()
    mock_service.bind = AsyncMock(return_value=binding)
    with patch("koda.squads.get_telegram_binding_service", return_value=mock_service):
        result = await _handle_squad_telegram_bind(
            {"squad_id": "build", "telegram_chat_id": -100, "is_forum": True},
            ctx,
        )
    assert result.success
    assert "build" in result.output and "-100" in result.output


@pytest.mark.asyncio
async def test_telegram_unbind_missing_squad(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    result = await _handle_squad_telegram_unbind({}, ctx)
    assert not result.success


@pytest.mark.asyncio
async def test_telegram_unbind_when_no_binding(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    mock_service = AsyncMock()
    mock_service.unbind = AsyncMock(return_value=False)
    with patch("koda.squads.get_telegram_binding_service", return_value=mock_service):
        result = await _handle_squad_telegram_unbind({"squad_id": "ghost"}, ctx)
    assert result.success
    assert "no telegram binding" in result.output


@pytest.mark.asyncio
async def test_telegram_unbind_success(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    mock_service = AsyncMock()
    mock_service.unbind = AsyncMock(return_value=True)
    with patch("koda.squads.get_telegram_binding_service", return_value=mock_service):
        result = await _handle_squad_telegram_unbind({"squad_id": "build"}, ctx)
    assert result.success
    assert "unbound" in result.output


@pytest.mark.asyncio
async def test_telegram_binding_get_no_args(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    result = await _handle_squad_telegram_binding_get({}, ctx)
    assert not result.success


# --- squad dashboard handlers ---


@pytest.mark.asyncio
async def test_dashboard_overview_disabled(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", False)
    result = await _handle_squad_dashboard_overview({}, ctx)
    assert not result.success


@pytest.mark.asyncio
async def test_dashboard_overview_no_dsn(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    with patch("koda.squads.list_squad_overviews_default", AsyncMock(return_value=None)):
        result = await _handle_squad_dashboard_overview({}, ctx)
    assert not result.success
    assert "unavailable" in result.output


@pytest.mark.asyncio
async def test_dashboard_overview_empty(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    with patch("koda.squads.list_squad_overviews_default", AsyncMock(return_value=[])):
        result = await _handle_squad_dashboard_overview({}, ctx)
    assert result.success
    assert "no active squads" in result.output


@pytest.mark.asyncio
async def test_dashboard_overview_with_data(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    from datetime import UTC, datetime
    from decimal import Decimal

    from koda.squads.projections import SquadOverview

    overview = SquadOverview(
        squad_id="build",
        workspace_id="acme",
        coordinator_agent_id="PM",
        thread_counts={"open": 2, "paused": 0, "completed": 1, "archived": 0},
        task_counts={
            "pending": 1,
            "claimed": 0,
            "in_progress": 1,
            "blocked": 0,
            "done": 3,
            "failed": 0,
            "cancelled": 0,
            "escalated": 0,
        },
        member_count=4,
        last_active_at=datetime.now(UTC),
        total_cost_usd=Decimal("12.34"),
    )
    with patch("koda.squads.list_squad_overviews_default", AsyncMock(return_value=[overview])):
        result = await _handle_squad_dashboard_overview({"workspace_id": "acme"}, ctx)
    assert result.success
    assert "build" in result.output
    assert "PM" in result.output
    assert result.data["count"] == 1
    assert result.data["overviews"][0]["squad_id"] == "build"
    assert result.data["overviews"][0]["total_cost_usd"] == "12.34"


@pytest.mark.asyncio
async def test_thread_overview_missing_thread_id(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    result = await _handle_squad_thread_overview({}, ctx)
    assert not result.success
    assert "Missing" in result.output


@pytest.mark.asyncio
async def test_thread_overview_uses_ctx(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    ctx.squad_thread_id = "00000000-0000-0000-0000-000000000001"

    captured: dict[str, object] = {}

    async def fake(thread_id: str, *, message_limit: int, task_limit: int):
        captured.update({"thread_id": thread_id, "message_limit": message_limit, "task_limit": task_limit})
        return None

    with patch("koda.squads.get_thread_overview_default", side_effect=fake):
        result = await _handle_squad_thread_overview({"message_limit": 5}, ctx)
    assert not result.success
    assert captured["thread_id"] == "00000000-0000-0000-0000-000000000001"
    assert captured["message_limit"] == 5


@pytest.mark.asyncio
async def test_thread_overview_with_data(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    from datetime import UTC, datetime
    from decimal import Decimal

    from koda.squads.projections import ThreadOverview
    from koda.squads.tasks import TaskDescriptor
    from koda.squads.threads import ParticipantInfo, ThreadDescriptor

    thread = ThreadDescriptor(
        id="00000000-0000-0000-0000-000000000001",
        workspace_id="acme",
        squad_id="build",
        owner_user_id=1,
        title="Landing",
        status="open",
        coordinator_agent_id="PM",
        current_owner_agent_id=None,
        parent_thread_id=None,
        visibility="squad",
        telegram_chat_id=None,
        telegram_message_thread_id=None,
        budget_usd_cap=None,
        cost_usd_accum=Decimal(0),
    )
    participant = ParticipantInfo(
        thread_id=thread.id,
        agent_id="FE",
        role="worker",
        joined_at=datetime.now(UTC),
        left_at=None,
        last_read_message_id=None,
        inbox_cursor=None,
        paused=False,
    )
    task = TaskDescriptor(
        id="00000000-0000-0000-0000-0000000000aa",
        thread_id=thread.id,
        parent_task_id=None,
        depends_on=[],
        assigned_agent_id="FE",
        assigner_agent_id="PM",
        kind="design",
        title="hero copy",
        description="",
        status="claimed",
        acceptance_criteria=[],
        deliverables_spec=[],
        delivered_artifact_ids=[],
        claim_token=None,
        claim_expires_at=None,
        delegation_depth=0,
        idempotency_key=None,
        cost_usd_so_far=Decimal(0),
        runtime_task_id=None,
        version=2,
    )
    overview = ThreadOverview(
        thread=thread,
        participants=[participant],
        recent_messages=[
            {"id": 1, "from": "PM", "to": None, "content": "kickoff", "type": "agent_text", "metadata": {}}
        ],
        active_tasks=[task],
        coordinator_agent_id="PM",
        open_task_count=1,
        done_task_count=2,
    )
    with patch("koda.squads.get_thread_overview_default", AsyncMock(return_value=overview)):
        result = await _handle_squad_thread_overview({"thread_id": thread.id}, ctx)
    assert result.success
    assert "Landing" in result.output
    assert "Coordinator: PM" in result.output
    assert "FE[worker]" in result.output
    assert result.data["status"] == "open"
    assert result.data["open_task_count"] == 1
    assert result.data["done_task_count"] == 2


# --- squad_inbox_drain handler ---


@pytest.mark.asyncio
async def test_inbox_drain_disabled(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", False)
    result = await _handle_squad_inbox_drain({}, ctx)
    assert not result.success


@pytest.mark.asyncio
async def test_inbox_drain_empty(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    mock_bus = AsyncMock()
    mock_bus.receive = AsyncMock(return_value=None)
    with patch("koda.agents.get_message_bus", return_value=mock_bus):
        result = await _handle_squad_inbox_drain({}, ctx)
    assert result.success
    assert "(inbox empty)" in result.output
    assert result.data["count"] == 0


@pytest.mark.asyncio
async def test_inbox_drain_returns_squad_inputs(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    from koda.agents.models import AgentMessage

    msg1 = AgentMessage(
        from_agent="squad_router",
        to_agent="FE",
        content="@fe please style this",
        message_type="text",
        metadata={
            "kind": "squad_thread_input",
            "thread_id": "00000000-0000-0000-0000-000000000001",
            "squad_id": "build",
            "telegram_chat_id": -100,
            "telegram_message_thread_id": 7,
            "from_user": "operator",
        },
        message_id="msg-101",
    )
    msg2 = AgentMessage(
        from_agent="other",
        to_agent="FE",
        content="random ping",
        message_type="text",
        metadata={},
        message_id="msg-102",
    )
    mock_bus = AsyncMock()
    mock_bus.receive = AsyncMock(side_effect=[msg1, msg2, None])
    with patch("koda.agents.get_message_bus", return_value=mock_bus):
        result = await _handle_squad_inbox_drain({"limit": 10}, ctx)
    assert result.success
    assert result.data["count"] == 2
    assert len(result.data["squad_inputs"]) == 1
    assert len(result.data["other"]) == 1
    squad_input = result.data["squad_inputs"][0]
    assert squad_input["thread_id"] == "00000000-0000-0000-0000-000000000001"
    assert squad_input["telegram_message_thread_id"] == 7
    assert squad_input["from_user"] == "operator"
    assert "@fe please style this" in squad_input["content"]


@pytest.mark.asyncio
async def test_inbox_drain_respects_limit(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    from koda.agents.models import AgentMessage

    def _msg(i: int) -> AgentMessage:
        return AgentMessage(
            from_agent="squad_router",
            to_agent="FE",
            content=f"input-{i}",
            metadata={"kind": "squad_thread_input", "thread_id": "abc"},
            message_id=f"msg-{i}",
        )

    mock_bus = AsyncMock()
    mock_bus.receive = AsyncMock(side_effect=[_msg(i) for i in range(50)] + [None])
    with patch("koda.agents.get_message_bus", return_value=mock_bus):
        result = await _handle_squad_inbox_drain({"limit": 3}, ctx)
    assert result.success
    assert result.data["count"] == 3
    # Bus.receive was called exactly limit times (no over-pull).
    assert mock_bus.receive.await_count == 3


@pytest.mark.asyncio
async def test_inbox_drain_uses_executing_agent_id(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    ctx.executing_agent_id = "FRONTEND"
    mock_bus = AsyncMock()
    mock_bus.receive = AsyncMock(return_value=None)
    with patch("koda.agents.get_message_bus", return_value=mock_bus):
        await _handle_squad_inbox_drain({}, ctx)
    args = mock_bus.receive.await_args.args
    assert args[0] == "FRONTEND"


def _telegram_thread(**overrides: object) -> object:
    from decimal import Decimal

    from koda.squads.threads import ThreadDescriptor

    base: dict[str, object] = {
        "id": "00000000-0000-0000-0000-000000000099",
        "workspace_id": "acme",
        "squad_id": "build",
        "owner_user_id": 1,
        "title": "t",
        "status": "open",
        "coordinator_agent_id": None,
        "current_owner_agent_id": None,
        "parent_thread_id": None,
        "visibility": "squad",
        "telegram_chat_id": -100,
        "telegram_message_thread_id": 7,
        "budget_usd_cap": None,
        "cost_usd_accum": Decimal(0),
    }
    base.update(overrides)
    return ThreadDescriptor(**base)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_telegram_post_disabled(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", False)
    result = await _handle_squad_telegram_post({"thread_id": "x", "content": "hi"}, ctx)
    assert not result.success


@pytest.mark.asyncio
async def test_telegram_post_missing_params(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    result = await _handle_squad_telegram_post({}, ctx)
    assert not result.success
    assert "Missing" in result.output


@pytest.mark.asyncio
async def test_telegram_post_thread_not_found(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    mock_store = AsyncMock()
    mock_store.get_thread = AsyncMock(return_value=None)
    with patch("koda.squads.get_squad_thread_store", return_value=mock_store):
        result = await _handle_squad_telegram_post(
            {"thread_id": "missing", "content": "hi"},
            ctx,
        )
    assert not result.success
    assert "not found" in result.output


@pytest.mark.asyncio
async def test_telegram_post_thread_without_chat(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    mock_store = AsyncMock()
    mock_store.get_thread = AsyncMock(return_value=_telegram_thread(telegram_chat_id=None))
    with patch("koda.squads.get_squad_thread_store", return_value=mock_store):
        result = await _handle_squad_telegram_post(
            {"thread_id": "abc", "content": "hi"},
            ctx,
        )
    assert not result.success
    assert "no telegram binding" in result.output


@pytest.mark.asyncio
async def test_telegram_post_success_uses_ctx_bot(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    mock_store = AsyncMock()
    mock_store.get_thread = AsyncMock(return_value=_telegram_thread())
    mock_store.post_thread_message = AsyncMock(return_value=51)
    sent_msg = MagicMock()
    sent_msg.message_id = 999
    fake_bot = AsyncMock()
    fake_bot.send_message = AsyncMock(return_value=sent_msg)
    ctx.bot = fake_bot
    with patch("koda.squads.get_squad_thread_store", return_value=mock_store):
        result = await _handle_squad_telegram_post(
            {"thread_id": "abc", "content": "shipping it"},
            ctx,
        )
    assert result.success
    assert result.data["telegram_message_id"] == 999
    assert result.data["message_id"] == 51
    fake_bot.send_message.assert_awaited_once()
    # Persist was called BEFORE send (audit-first ordering).
    mock_store.post_thread_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_telegram_post_send_failure_keeps_audit(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    mock_store = AsyncMock()
    mock_store.get_thread = AsyncMock(return_value=_telegram_thread())
    mock_store.post_thread_message = AsyncMock(return_value=77)
    fake_bot = AsyncMock()
    fake_bot.send_message = AsyncMock(side_effect=RuntimeError("bot rate-limited"))
    ctx.bot = fake_bot
    with patch("koda.squads.get_squad_thread_store", return_value=mock_store):
        result = await _handle_squad_telegram_post(
            {"thread_id": "abc", "content": "shipping it"},
            ctx,
        )
    assert not result.success
    assert "msg-77" in result.output
    assert "Telegram send failed" in result.output
    assert result.data["telegram_sent"] is False
    mock_store.post_thread_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_telegram_binding_get_lookup_by_chat(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    from koda.squads.telegram_bridge import SquadTelegramBinding

    binding = SquadTelegramBinding(
        squad_id="build",
        telegram_chat_id=-100,
        chat_title="Build",
        is_forum=True,
        bound_by_user_id=None,
        bound_at=None,
        updated_at=None,
    )
    mock_service = AsyncMock()
    mock_service.get_for_squad = AsyncMock(return_value=None)
    mock_service.get_for_chat = AsyncMock(return_value=binding)
    with patch("koda.squads.get_telegram_binding_service", return_value=mock_service):
        result = await _handle_squad_telegram_binding_get({"telegram_chat_id": -100}, ctx)
    assert result.success
    assert "build" in result.output
    mock_service.get_for_chat.assert_awaited_once_with(-100)


@pytest.mark.asyncio
async def test_router_tick_reverts_summary(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    from koda.squads.router import SweepReport
    from koda.squads.tasks import ExpiredClaim

    mock_router = AsyncMock()
    mock_router.sweep_once = AsyncMock(
        return_value=SweepReport(
            expired_claims=[
                ExpiredClaim(
                    task_id="00000000-0000-0000-0000-000000000aa1",
                    thread_id="00000000-0000-0000-0000-000000000bb1",
                    previously_assigned_agent_id="FE",
                    version_after=4,
                )
            ]
        )
    )
    with patch("koda.squads.get_squad_router", return_value=mock_router):
        result = await _handle_squad_router_tick({}, ctx)
    assert result.success
    assert "reverted 1" in result.output
    assert "FE" in result.output


@pytest.mark.asyncio
async def test_coordinator_get_with_state_and_history(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("koda.services.tool_dispatcher.INTER_AGENT_ENABLED", True)
    from koda.squads.coordinator import CoordinatorHistoryEntry

    mock_service = AsyncMock()
    mock_service.current_coordinator = AsyncMock(return_value=_coordinator_state())
    mock_service.list_history = AsyncMock(
        return_value=[
            CoordinatorHistoryEntry(
                id=1,
                squad_id="build",
                event_type="elected",
                coordinator_agent_id="PM",
                previous_coordinator_agent_id=None,
                triggered_by_agent_id="admin",
                reason=None,
                metadata={},
                created_at=None,
            )
        ]
    )
    with patch("koda.squads.get_coordinator_service", return_value=mock_service):
        result = await _handle_squad_coordinator_get({"squad_id": "build", "history_limit": 1}, ctx)
    assert result.success
    assert "coordinator=PM" in result.output
    assert "elected" in result.output
