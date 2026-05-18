"""Tests for supervisor-style squad coordination."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from koda.squads.capabilities import CapabilitySummary
from koda.squads.coordinator_engine import (
    CoordinationDecision,
    CoordinationPlannerInput,
    CoordinationPolicyError,
    CoordinationPolicyValidator,
    CoordinationTask,
    LLMCoordinationPlanner,
    SquadCoordinatorEngine,
    request_needs_coordination,
    should_use_coordinator_engine,
)
from koda.squads.semantic_router import SemanticAgentScore, SemanticRoutingResult
from koda.squads.tasks import TaskDescriptor
from koda.squads.threads import ParticipantInfo, ThreadDescriptor


def _thread(**overrides: object) -> ThreadDescriptor:
    base: dict[str, object] = {
        "id": "00000000-0000-0000-0000-000000000001",
        "workspace_id": "acme",
        "squad_id": "build",
        "owner_user_id": 42,
        "title": "Landing",
        "status": "open",
        "coordinator_agent_id": "PM",
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


def _participant(agent_id: str, role: str = "worker") -> ParticipantInfo:
    return ParticipantInfo(
        thread_id="00000000-0000-0000-0000-000000000001",
        agent_id=agent_id,
        role=role,
        joined_at=datetime.now(UTC),
        left_at=None,
        last_read_message_id=None,
        inbox_cursor=None,
        paused=False,
    )


def _task_descriptor(task_id: str, *, agent_id: str = "FE", kind: str = "frontend") -> TaskDescriptor:
    return TaskDescriptor(
        id=task_id,
        thread_id="00000000-0000-0000-0000-000000000001",
        parent_task_id=None,
        depends_on=[],
        assigned_agent_id=agent_id,
        assigner_agent_id="PM",
        kind=kind,
        title="Task",
        description="Do work",
        status="pending",
        acceptance_criteria=[],
        deliverables_spec=[],
        delivered_artifact_ids=[],
        claim_token=None,
        claim_expires_at=None,
        delegation_depth=0,
        idempotency_key=None,
        cost_usd_so_far=Decimal(0),
        runtime_task_id=None,
        version=1,
    )


def _semantic_result(*agent_ids: str) -> SemanticRoutingResult:
    return SemanticRoutingResult(
        available=True,
        model_name="test-model",
        scores=[
            SemanticAgentScore(
                agent_id=agent_id,
                score=0.9 - (idx * 0.05),
                positive_score=0.9 - (idx * 0.05),
                negative_score=0.0,
                summary_text=f"{agent_id} capability summary",
                is_coordinator=agent_id == "PM",
            )
            for idx, agent_id in enumerate(agent_ids)
        ],
    )


class _StaticPlanner:
    async def plan(self, planner_input: CoordinationPlannerInput) -> CoordinationDecision:
        return CoordinationDecision(
            mode="sequential_plan",
            confidence=0.91,
            reasoning_summary="planner json",
            tasks=[
                CoordinationTask(
                    key="brief",
                    title="Brief",
                    agent_id="COPY",
                    kind="brief_copy",
                    objective="Brief the work",
                ),
                CoordinationTask(
                    key="build",
                    title="Build",
                    agent_id="FE",
                    kind="frontend",
                    objective="Build the artifact",
                    depends_on=["brief"],
                ),
                CoordinationTask(
                    key="review",
                    title="Review",
                    agent_id="QA",
                    kind="review",
                    objective="Review the artifact",
                    depends_on=["build"],
                ),
            ],
            selected_agents=["COPY", "FE", "QA"],
            final_response_strategy="coordinator_synthesis_after_all_task_results",
        )


def _planner_input() -> CoordinationPlannerInput:
    return CoordinationPlannerInput(
        text="Build the launch page",
        thread_id="00000000-0000-0000-0000-000000000001",
        squad_id="build",
        coordinator_agent_id="PM",
        participant_agent_ids=["PM", "COPY", "FE"],
        capability_summaries=[
            CapabilitySummary(agent_id="PM", display_name="PM", role="Coordinator", is_coordinator=True),
            CapabilitySummary(agent_id="COPY", display_name="Copy", role="Content"),
            CapabilitySummary(agent_id="FE", display_name="Frontend", role="Interface"),
        ],
        semantic_result=_semantic_result("COPY", "FE"),
    )


def test_coordination_decision_validates_schema() -> None:
    decision = CoordinationDecision.from_dict(
        {
            "mode": "delegate",
            "confidence": 0.8,
            "reasoning_summary": "needs specialist",
            "tasks": [
                {
                    "key": "frontend",
                    "title": "Build UI",
                    "agent_id": "FE",
                    "kind": "frontend",
                    "objective": "Build the interface",
                }
            ],
            "selected_agents": ["FE"],
        }
    )
    decision.validate(["PM", "FE"])
    assert decision.tasks[0].agent_id == "FE"


def test_coordination_decision_rejects_invalid_kind() -> None:
    with pytest.raises(ValueError):
        CoordinationDecision.from_dict({"mode": "magic", "confidence": 0.4, "tasks": []})


def test_complex_deliverable_uses_supervisor_without_mentions() -> None:
    assert request_needs_coordination(
        "Entregue uma landing page de fintech com copy, design e formulário",
        has_coordinator=True,
        participant_count=4,
        semantic_result=_semantic_result("FE", "COPY", "QA"),
    )
    assert should_use_coordinator_engine(
        "Entregue uma landing page de fintech com copy, design e formulário",
        participant_agent_ids=["PM", "COPY", "FE", "QA"],
        coordinator_agent_id="PM",
        semantic_result=_semantic_result("FE", "COPY", "QA"),
    )


def test_explicit_mention_stays_fast_path() -> None:
    assert not should_use_coordinator_engine(
        "@FE ajuste o CSS do hero",
        participant_agent_ids=["PM", "FE"],
        coordinator_agent_id="PM",
    )


def test_landing_page_decision_creates_specialist_tasks() -> None:
    engine = SquadCoordinatorEngine(thread_store=AsyncMock(), task_store=AsyncMock())
    decision = engine.decide(
        "Entregue uma landing page de fintech com copy forte, design polido e formulário",
        participants=["PM", "COPY", "FE", "QA"],
        coordinator_agent_id="PM",
        semantic_result=_semantic_result("COPY", "FE", "QA"),
    )
    assert decision.mode == "parallel_delegation"
    assert [task.agent_id for task in decision.tasks] == ["COPY", "FE", "QA"]
    assert {task.kind for task in decision.tasks} == {"specialist"}


def test_fallback_planner_uses_contribution_proposals() -> None:
    decision = SquadCoordinatorEngine(thread_store=AsyncMock(), task_store=AsyncMock()).decide(
        "Preciso de uma entrega integrada",
        participants=["PM", "COPY", "FE"],
        coordinator_agent_id="PM",
        semantic_result=_semantic_result("COPY", "FE"),
        capability_summaries=[
            CapabilitySummary(agent_id="PM", display_name="PM", role="Coordinator", is_coordinator=True),
            CapabilitySummary(agent_id="COPY", display_name="Copy", role="Content"),
            CapabilitySummary(agent_id="FE", display_name="Frontend", role="Interface"),
        ],
    )
    assert decision.selected_agents == ["COPY", "FE"]


@pytest.mark.asyncio
async def test_llm_planner_parses_strict_json(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run_llm(**_: object) -> dict[str, object]:
        return {
            "result": json.dumps(
                {
                    "mode": "sequential_plan",
                    "confidence": 0.93,
                    "reasoning_summary": "structured plan",
                    "tasks": [
                        {
                            "key": "copy",
                            "title": "Copy",
                            "agent_id": "COPY",
                            "kind": "content",
                            "objective": "Produce copy",
                        },
                        {
                            "key": "build",
                            "title": "Build",
                            "agent_id": "FE",
                            "kind": "implementation",
                            "objective": "Build artifact",
                            "depends_on": ["copy"],
                        },
                    ],
                    "selected_agents": ["COPY", "FE"],
                    "final_response_strategy": "coordinator_synthesis_after_all_task_results",
                }
            )
        }

    monkeypatch.setattr("koda.services.llm_runner.run_llm", fake_run_llm)
    decision = await LLMCoordinationPlanner().plan(_planner_input())

    assert decision.mode == "sequential_plan"
    assert [task.agent_id for task in decision.tasks] == ["COPY", "FE"]
    assert decision.tasks[1].depends_on == ["copy"]


@pytest.mark.asyncio
async def test_llm_planner_falls_back_to_semantic_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run_llm(**_: object) -> dict[str, object]:
        return {"error": True, "result": "offline"}

    monkeypatch.setattr("koda.services.llm_runner.run_llm", fake_run_llm)
    decision = await LLMCoordinationPlanner().plan(_planner_input())

    assert decision.mode == "parallel_delegation"
    assert [task.agent_id for task in decision.tasks] == ["COPY", "FE"]


def test_coordinator_engine_has_no_keyword_intent_tables() -> None:
    source = Path("koda/squads/coordinator_engine.py").read_text(encoding="utf-8")
    assert "_DELIVERABLE_RE" not in source
    assert "_COMPLEX_OBJECT_RE" not in source
    assert "_ROLE_TERMS" not in source


def test_policy_blocks_non_participant_task() -> None:
    decision = CoordinationDecision(
        mode="delegate",
        confidence=0.8,
        reasoning_summary="x",
        tasks=[CoordinationTask(title="x", agent_id="GHOST", kind="x", objective="x")],
        selected_agents=["GHOST"],
    )
    with pytest.raises(ValueError):
        decision.validate(["PM", "FE"])


def test_policy_blocks_paused_thread() -> None:
    validator = CoordinationPolicyValidator()
    decision = CoordinationDecision(
        mode="delegate",
        confidence=0.8,
        reasoning_summary="x",
        tasks=[CoordinationTask(title="x", agent_id="FE", kind="x", objective="x")],
        selected_agents=["FE"],
    )
    with pytest.raises(CoordinationPolicyError):
        validator.validate(
            decision,
            thread=_thread(status="paused"),
            participants=["PM", "FE"],
            coordinator_agent_id="PM",
        )


@pytest.mark.asyncio
async def test_engine_persists_task_request_and_dispatches() -> None:
    thread_store = AsyncMock()
    thread_store.post_thread_message = AsyncMock(side_effect=[10, 11, 12, 13])
    thread_store.notify_event = AsyncMock()
    task_store = AsyncMock()
    task_store.create_task = AsyncMock(
        side_effect=[
            _task_descriptor("00000000-0000-0000-0000-000000000101", agent_id="COPY", kind="brief_copy"),
            _task_descriptor("00000000-0000-0000-0000-000000000102", agent_id="FE", kind="frontend"),
            _task_descriptor("00000000-0000-0000-0000-000000000103", agent_id="QA", kind="review"),
        ]
    )
    engine = SquadCoordinatorEngine(thread_store=thread_store, task_store=task_store, planner=_StaticPlanner())
    dispatched: list[str] = []

    async def dispatch(request: object) -> str:
        dispatched.append(cast(Any, request).agent_id)
        return f"sent-{len(dispatched)}"

    execution = await engine.coordinate_user_input(
        text="Entregue uma landing page de fintech com copy forte, design polido e formulário",
        thread=_thread(),
        participants=[_participant("PM", "coordinator"), _participant("COPY"), _participant("FE"), _participant("QA")],
        coordinator_agent_id="PM",
        capability_hints={
            "PM": "coordinator supervisor",
            "COPY": "copy marketing headline cta planejamento",
            "FE": "frontend react html css landing page ui",
            "QA": "review qa quality testes",
        },
        semantic_result=_semantic_result("COPY", "FE", "QA"),
        dispatch=dispatch,
        parent_message_id="msg-99",
    )

    assert execution.coordinated is True
    assert dispatched == ["COPY"]
    assert task_store.create_task.await_count == 3
    assert task_store.create_task.await_args_list[1].kwargs["depends_on"] == ["00000000-0000-0000-0000-000000000101"]
    assert task_store.create_task.await_args_list[2].kwargs["depends_on"] == ["00000000-0000-0000-0000-000000000102"]
    assert thread_store.post_thread_message.await_args_list[0].kwargs["message_type"] == "system_event"
    assert all(
        call.kwargs["message_type"] == "task_request" for call in thread_store.post_thread_message.await_args_list[1:]
    )
