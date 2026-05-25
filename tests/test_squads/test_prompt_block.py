"""Tests for the squad runtime context block builder."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from koda.squads.capabilities import CapabilitySummary
from koda.squads.prompt_block import build_squad_context_block
from koda.squads.tasks import TaskDescriptor
from koda.squads.threads import ThreadDescriptor


def _thread(**overrides: object) -> ThreadDescriptor:
    base: dict[str, object] = {
        "id": "00000000-0000-0000-0000-000000000001",
        "workspace_id": "acme",
        "squad_id": "build",
        "owner_user_id": 1,
        "title": "Landing page",
        "status": "open",
        "coordinator_agent_id": "PM",
        "current_owner_agent_id": None,
        "parent_thread_id": None,
        "visibility": "squad",
        "telegram_chat_id": None,
        "telegram_message_thread_id": None,
        "budget_usd_cap": None,
        "cost_usd_accum": Decimal(0),
    }
    base.update(overrides)
    return ThreadDescriptor(**base)  # type: ignore[arg-type]


def _task(**overrides: object) -> TaskDescriptor:
    base: dict[str, object] = {
        "id": "00000000-0000-0000-0000-0000000000ab",
        "thread_id": "00000000-0000-0000-0000-000000000001",
        "parent_task_id": None,
        "depends_on": [],
        "assigned_agent_id": None,
        "assigner_agent_id": "PM",
        "kind": "",
        "title": "API spec",
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


def _make_stores(
    *,
    thread: ThreadDescriptor | None,
    summaries: list[CapabilitySummary] | None = None,
    history: list[dict[str, object]] | None = None,
    tasks: list[TaskDescriptor] | None = None,
) -> tuple[AsyncMock, AsyncMock, AsyncMock]:
    thread_store = AsyncMock()
    thread_store.get_thread = AsyncMock(return_value=thread)
    thread_store.thread_history = AsyncMock(return_value=history or [])
    cache = AsyncMock()
    cache.list_for_squad = AsyncMock(return_value=summaries or [])
    task_store = AsyncMock()
    task_store.list_tasks = AsyncMock(return_value=tasks or [])
    return thread_store, cache, task_store


@pytest.mark.asyncio
async def test_returns_none_when_thread_missing() -> None:
    thread_store, cache, task_store = _make_stores(thread=None)
    block = await build_squad_context_block(
        thread_id="missing",
        thread_store=thread_store,
        capability_cache=cache,
        task_store=task_store,
    )
    assert block is None


@pytest.mark.asyncio
async def test_renders_full_block_with_all_sections() -> None:
    summaries = [
        CapabilitySummary(agent_id="PM", display_name="PM", role="Product", is_coordinator=True),
        CapabilitySummary(agent_id="FE", display_name="Frontend", role="FE Eng"),
    ]
    history = [
        {"id": 5, "from": "PM", "type": "agent_text", "content": "Let's split work."},
        {"id": 4, "from": "FE", "type": "agent_text", "content": "I'll take UI."},
    ]
    tasks = [_task(status="claimed", assigned_agent_id="FE", title="Hero copy")]
    thread_store, cache, task_store = _make_stores(
        thread=_thread(),
        summaries=summaries,
        history=history,
        tasks=tasks,
    )
    block = await build_squad_context_block(
        thread_id="00000000-0000-0000-0000-000000000001",
        executing_agent_id="FE",
        thread_store=thread_store,
        capability_cache=cache,
        task_store=task_store,
        delegation_chain=["PM", "FE"],
    )
    assert block is not None
    assert "<squad_context>" in block
    assert "</squad_context>" in block
    assert "Thread: Landing page (status=open)" in block
    assert "Coordinator: PM" in block
    assert "You are: FE" in block
    # Members block — self is excluded.
    assert "PM [PM] (coordinator)" in block
    assert "Frontend [FE]" not in block
    # Transcript section
    assert "Recent thread" in block
    assert "[5] [agent_text] PM: Let's split work." in block
    # Active tasks
    assert "Active tasks" in block
    assert "Hero copy" in block
    # Delegation chain
    assert "Delegation chain (do not loop): PM -> FE" in block


@pytest.mark.asyncio
async def test_omits_transcript_when_empty() -> None:
    thread_store, cache, task_store = _make_stores(thread=_thread(), history=[])
    block = await build_squad_context_block(
        thread_id="x",
        thread_store=thread_store,
        capability_cache=cache,
        task_store=task_store,
    )
    assert block is not None
    assert "Recent thread" not in block


@pytest.mark.asyncio
async def test_omits_active_tasks_when_no_task_store() -> None:
    thread_store, cache, _ = _make_stores(thread=_thread())
    block = await build_squad_context_block(
        thread_id="x",
        thread_store=thread_store,
        capability_cache=cache,
        task_store=None,
    )
    assert block is not None
    assert "Active tasks" not in block


@pytest.mark.asyncio
async def test_truncates_long_messages() -> None:
    long_content = "x" * 1000
    history = [{"id": 1, "from": "A", "type": "agent_text", "content": long_content}]
    thread_store, cache, task_store = _make_stores(thread=_thread(), history=history)
    block = await build_squad_context_block(
        thread_id="x",
        thread_store=thread_store,
        capability_cache=cache,
        task_store=task_store,
    )
    assert block is not None
    # The truncated snippet ends with ellipsis when it overflows the cap.
    assert "…" in block
    # The full 1000-char content must not appear verbatim.
    assert long_content not in block


@pytest.mark.asyncio
async def test_no_coordinator_falls_back_label() -> None:
    thread = _thread(coordinator_agent_id=None)
    thread_store, cache, task_store = _make_stores(thread=thread)
    block = await build_squad_context_block(
        thread_id="x",
        thread_store=thread_store,
        capability_cache=cache,
        task_store=task_store,
    )
    assert block is not None
    assert "Coordinator: (none — capability-based routing)" in block


@pytest.mark.asyncio
async def test_no_delegation_chain_omits_section() -> None:
    thread_store, cache, task_store = _make_stores(thread=_thread())
    block = await build_squad_context_block(
        thread_id="x",
        thread_store=thread_store,
        capability_cache=cache,
        task_store=task_store,
    )
    assert block is not None
    assert "Delegation chain" not in block


@pytest.mark.asyncio
async def test_smoke_dataclass_extensions() -> None:
    """Smoke check that QueueItem and ToolContext accept the new squad fields."""
    from koda.services.queue_manager import QueueItem
    from koda.services.tool_dispatcher import ToolContext

    qi = QueueItem(
        chat_id=1,
        query_text="hi",
        executing_agent_id="FE",
        squad_thread_id="00000000-0000-0000-0000-000000000001",
        squad_task_id="00000000-0000-0000-0000-0000000000ab",
        delegation_chain=["PM", "FE"],
    )
    assert qi.executing_agent_id == "FE"
    assert qi.delegation_chain == ["PM", "FE"]

    ctx = ToolContext(
        user_id=1,
        chat_id=1,
        work_dir="/tmp",
        user_data={},
        agent=None,
        agent_mode="normal",
        executing_agent_id="FE",
        squad_thread_id="00000000-0000-0000-0000-000000000001",
        delegation_chain=["PM"],
    )
    assert ctx.squad_thread_id == "00000000-0000-0000-0000-000000000001"
    assert ctx.delegation_chain == ["PM"]
    # Default-construct still works (no breaking change).
    bare = ToolContext(user_id=1, chat_id=1, work_dir="/tmp", user_data={}, agent=None, agent_mode="normal")
    assert bare.squad_thread_id is None
    assert bare.delegation_chain == []


# Datetime is unused but kept available for future timestamp-formatting tests.
_PLACEHOLDER_TS = datetime.now(UTC)
