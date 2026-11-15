from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from koda.services.child_runs import (
    MAX_CHILD_RUNS_PER_CALL,
    delegate_child_task_tool,
    make_child_run_id,
    make_idempotency_key,
    normalize_child_run_requests,
)


def test_normalize_child_run_requests_supports_single_and_fanout() -> None:
    single = normalize_child_run_requests({"goal": "A", "prompt": "Do A", "toolset": "read_only"})
    assert single == [{"goal": "A", "prompt": "Do A", "toolset": "read_only"}]

    fanout = normalize_child_run_requests(
        {
            "toolset": "read_only",
            "timeout_seconds": 180,
            "tasks": [
                {"goal": "A", "prompt": "Do A"},
                {"goal": "B", "prompt": "Do B", "timeout_seconds": 90},
            ],
        }
    )

    assert len(fanout) == 2
    assert fanout[0]["toolset"] == "read_only"
    assert fanout[0]["timeout_seconds"] == 180
    assert fanout[1]["timeout_seconds"] == 90


def test_child_run_ids_are_stable_by_parent_attempt_signature_and_index() -> None:
    left = make_child_run_id(42, 1, "abc", 0)
    right = make_child_run_id(42, 1, "abc", 0)
    other = make_child_run_id(42, 1, "abc", 1)

    assert left == right
    assert left != other
    assert make_idempotency_key(42, 1, "abc", 0).startswith("42:1:abc")
    assert MAX_CHILD_RUNS_PER_CALL == 4


def _parent_ctx(**overrides: Any) -> SimpleNamespace:
    defaults: dict[str, Any] = {
        "task_id": 42,
        "attempt": 1,
        "application": object(),
        "bot": None,
        "user_id": 7,
        "chat_id": 7,
        "work_dir": "/tmp",
        "user_data": {"provider": "claude", "session_id": "sess-1"},
        "executing_agent_id": "KODA",
        "task_kind": "investigation",
        "context_governance": {},
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
async def test_child_run_cannot_act_as_another_agent() -> None:
    """A child acting as another agent would take that agent's workspace, inbox and memory."""

    start = AsyncMock()
    with (
        patch("koda.services.child_runs.list_child_runs_for_parent", AsyncMock(return_value=[])),
        patch("koda.services.queue_manager.start_child_run_task", start),
    ):
        result = await delegate_child_task_tool({"prompt": "Inspect X", "target_agent_id": "OTHER"}, _parent_ctx())

    assert result.success is False
    assert result.data["error"]["code"] == "subagent.policy_denied"
    start.assert_not_awaited()


@pytest.mark.asyncio
async def test_child_run_starts_with_the_parent_capability_envelope() -> None:
    started: dict[str, Any] = {}

    async def _start(**kwargs: Any) -> tuple[int, asyncio.Task[None]]:
        started.update(kwargs)
        return 501, asyncio.ensure_future(asyncio.sleep(0))

    parent_tools = ["file_list", "task", "web_search"]
    with (
        patch("koda.services.child_runs.list_child_runs_for_parent", AsyncMock(return_value=[])),
        patch("koda.services.child_runs._fetch_child_run_by_idempotency", AsyncMock(return_value=None)),
        patch("koda.services.child_runs.upsert_child_run", AsyncMock()),
        patch("koda.services.child_runs.update_child_run_result", AsyncMock()),
        patch(
            "koda.services.child_runs._summarize_child_task",
            return_value={"child_run_id": "childrun_x", "child_task_id": 501, "status": "completed", "summary": "ok"},
        ),
        patch(
            "koda.services.execution_policy.resolve_execution_policy_allowed_tool_ids",
            return_value=parent_tools,
        ),
        patch("koda.services.queue_manager.start_child_run_task", side_effect=_start),
    ):
        result = await delegate_child_task_tool(
            {
                "prompt": "Inspect X",
                "target_agent_id": "koda",
                "context_policy": {"include_memory": True, "allow_memory_writes": True, "include_sensitive": True},
            },
            _parent_ctx(),
        )

    assert result.success is True
    assert started["target_agent_id"] == "KODA"
    # The child gets the parent's tools, never the Delegate Task tool itself.
    assert started["capabilities"] == {
        "agent_id": "KODA",
        "allowed_tool_ids": ["file_list", "web_search"],
        "task_kind": "investigation",
    }
    # Memory rights: recall only on request, never writes or sensitive recall.
    assert started["context_policy"]["include_memory"] is True
    assert "allow_memory_writes" not in started["context_policy"]
    assert "include_sensitive" not in started["context_policy"]
