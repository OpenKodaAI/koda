"""Tests for procedural memory helpers."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from koda.memory.procedural import (
    build_execution_memories,
    build_procedural_context,
    search_observed_patterns,
)
from koda.memory.types import Memory, MemoryType, RecallResult


def test_build_execution_memories_success() -> None:
    memories = build_execution_memories(
        query="Fix the login bug and run pytest",
        user_id=111,
        task_id=42,
        status="completed",
        confidence_score=0.81,
        error_message=None,
        tool_uses=[{"name": "Bash", "input": {"command": "pytest tests/test_auth.py"}}],
        tool_execution_trace=[{"tool": "agent_get_status"}],
        knowledge_hits=[{"source_label": "README.md"}],
        work_dir="/tmp/project",
        model="claude-sonnet-4-6",
        task_kind="bugfix",
        project_key="project",
        environment="prod",
        team="agent_a",
        owner="AGENT_A",
    )

    assert len(memories) == 1
    memory = memories[0]
    assert memory.memory_type is MemoryType.PROCEDURE
    assert memory.metadata["outcome"] == "success"
    assert memory.metadata["task_kind"] == "bugfix"
    assert memory.metadata["project_key"] == "project"
    assert memory.metadata["environment"] == "prod"
    assert memory.metadata["team"] == "agent_a"
    assert memory.metadata["owner"] == "AGENT_A"
    assert "README.md" in memory.content


@pytest.mark.asyncio
async def test_build_procedural_context_groups_success_and_caution() -> None:
    store = MagicMock()
    store.search = AsyncMock(
        return_value=[
            RecallResult(
                memory=Memory(
                    user_id=111,
                    memory_type=MemoryType.PROCEDURE,
                    content="Validate first, then edit.",
                    metadata={"outcome": "success", "task_id": 7, "confidence_score": 0.82},
                ),
                relevance_score=0.1,
            ),
            RecallResult(
                memory=Memory(
                    user_id=111,
                    memory_type=MemoryType.PROCEDURE,
                    content="A previous deploy failed without verification.",
                    metadata={"outcome": "failure", "task_id": 8, "confidence_score": 0.31},
                ),
                relevance_score=0.2,
            ),
        ]
    )

    context = await build_procedural_context(store, "deploy", 111)

    assert "Procedural Memory" in context
    assert "Validated Procedures" in context
    assert "Cautions" in context
    assert "task #7" in context
    assert "task #8" in context


@pytest.mark.asyncio
async def test_search_observed_patterns_filters_by_scope() -> None:
    matching = RecallResult(
        memory=Memory(
            user_id=111,
            memory_type=MemoryType.PROCEDURE,
            content="Match",
            metadata={
                "task_kind": "deploy",
                "project_key": "workspace",
                "environment": "prod",
                "team": "agent_a",
                "owner": "AGENT_A",
                "task_id": 1,
            },
        ),
        relevance_score=0.1,
    )
    wrong_project = RecallResult(
        memory=Memory(
            user_id=111,
            memory_type=MemoryType.PROCEDURE,
            content="Wrong project",
            metadata={
                "task_kind": "deploy",
                "project_key": "other",
                "environment": "prod",
                "team": "agent_a",
                "owner": "AGENT_A",
                "task_id": 2,
            },
        ),
        relevance_score=0.2,
    )
    missing_scope = RecallResult(
        memory=Memory(
            user_id=111,
            memory_type=MemoryType.PROCEDURE,
            content="Missing scope",
            metadata={"task_id": 3},
        ),
        relevance_score=0.3,
    )
    store = MagicMock()
    store.search = AsyncMock(return_value=[matching, wrong_project, missing_scope])

    patterns = await search_observed_patterns(
        store,
        "deploy",
        111,
        max_results=5,
        task_kind="deploy",
        project_key="workspace",
        environment="prod",
        team="agent_a",
        owner="AGENT_A",
    )

    assert [pattern.content for pattern in patterns] == ["Match"]
