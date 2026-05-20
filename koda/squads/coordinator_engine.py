"""Coordinator engine for squad supervisor-style orchestration.

The engine implements Koda's internal version of the LangChain/LangGraph
``supervisor + subagents`` pattern: the elected coordinator decides whether a
turn needs specialists, creates real SquadTasks, emits visible task_request
messages, and dispatches the work to the selected agents.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from koda.config import (
    DEFAULT_WORK_DIR,
    INTER_AGENT_MAX_DELEGATION_DEPTH,
    SQUAD_CLAIM_TTL_S,
    SQUAD_COORDINATOR_LLM_TIMEOUT_S,
    SQUAD_COORDINATOR_PLANNER,
    SQUAD_FANOUT_MAX_PER_TURN,
)
from koda.logging_config import get_logger
from koda.squads.capabilities import CapabilitySummary
from koda.squads.delivery import SQUAD_DELIVERY_SCHEMA_VERSION, delivery_metric
from koda.squads.dispatch import record_squad_handoff_event
from koda.squads.routing import extract_mentions
from koda.squads.semantic_router import (
    CoordinationPlannerInput,
    SemanticAgentScore,
    SemanticRoutingResult,
    SquadSemanticRouter,
    get_squad_semantic_router,
)
from koda.squads.tasks import SquadTaskStore, TaskDescriptor
from koda.squads.threads import ParticipantInfo, SquadThreadStore, ThreadDescriptor

log = get_logger(__name__)

CoordinationMode = Literal[
    "answer_self",
    "delegate",
    "parallel_delegation",
    "sequential_plan",
    "ask_clarification",
    "handoff",
    "decline",
]

_VALID_MODES: set[str] = {
    "answer_self",
    "delegate",
    "parallel_delegation",
    "sequential_plan",
    "ask_clarification",
    "handoff",
    "decline",
}


@dataclass(frozen=True)
class CoordinationTask:
    title: str
    agent_id: str
    kind: str
    objective: str
    acceptance_criteria: list[str] = field(default_factory=list)
    deliverables: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    context_refs: list[str] = field(default_factory=list)
    report_via: str = "thread"
    key: str = ""
    deadline: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "agent_id": self.agent_id,
            "kind": self.kind,
            "objective": self.objective,
            "acceptance_criteria": list(self.acceptance_criteria),
            "deliverables": list(self.deliverables),
            "depends_on": list(self.depends_on),
            "context_refs": list(self.context_refs),
            "report_via": self.report_via,
            "deadline": self.deadline,
        }


@dataclass(frozen=True)
class CoordinationDecision:
    mode: CoordinationMode
    confidence: float
    reasoning_summary: str
    tasks: list[CoordinationTask] = field(default_factory=list)
    dependencies: list[dict[str, str]] = field(default_factory=list)
    selected_agents: list[str] = field(default_factory=list)
    needs_user_clarification: bool = False
    budget_estimate_usd: float = 0.0
    visibility: str = "thread"
    final_response_strategy: str = "direct"

    def validate(self, participant_agent_ids: Iterable[str] | None = None) -> None:
        if self.mode not in _VALID_MODES:
            raise ValueError(f"invalid coordination mode: {self.mode!r}")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        participants = {str(value) for value in participant_agent_ids or [] if str(value or "")}
        seen_keys: set[str] = set()
        for task in self.tasks:
            if not task.title.strip() or not task.agent_id.strip() or not task.objective.strip():
                raise ValueError("coordination tasks require title, agent_id, and objective")
            if participants and task.agent_id not in participants:
                raise ValueError(f"task targets non-participant agent: {task.agent_id}")
            if task.key:
                if task.key in seen_keys:
                    raise ValueError(f"duplicate coordination task key: {task.key}")
                for dep in task.depends_on:
                    if dep == task.key:
                        raise ValueError(f"coordination task {task.key!r} cannot depend on itself")
                    if dep not in seen_keys:
                        raise ValueError(
                            f"coordination task {task.key!r} depends on unknown or later task key: {dep!r}"
                        )
                seen_keys.add(task.key)
        if self.mode in {"delegate", "parallel_delegation", "sequential_plan"} and not self.tasks:
            raise ValueError(f"mode {self.mode!r} requires at least one task")

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "confidence": self.confidence,
            "reasoning_summary": self.reasoning_summary,
            "tasks": [task.to_dict() for task in self.tasks],
            "dependencies": list(self.dependencies),
            "selected_agents": list(self.selected_agents),
            "needs_user_clarification": self.needs_user_clarification,
            "budget_estimate_usd": self.budget_estimate_usd,
            "visibility": self.visibility,
            "final_response_strategy": self.final_response_strategy,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CoordinationDecision:
        mode = str(payload.get("mode") or "answer_self")
        tasks_payload = payload.get("tasks") or []
        if not isinstance(tasks_payload, list):
            raise ValueError("tasks must be a list")
        tasks = [
            CoordinationTask(
                key=str(item.get("key") or f"task-{idx + 1}"),
                title=str(item.get("title") or ""),
                agent_id=str(item.get("agent_id") or ""),
                kind=str(item.get("kind") or "general"),
                objective=str(item.get("objective") or ""),
                acceptance_criteria=[str(value) for value in item.get("acceptance_criteria") or []],
                deliverables=[str(value) for value in item.get("deliverables") or []],
                depends_on=[str(value) for value in item.get("depends_on") or []],
                context_refs=[str(value) for value in item.get("context_refs") or []],
                report_via=str(item.get("report_via") or "thread"),
                deadline=str(item.get("deadline")) if item.get("deadline") else None,
            )
            for idx, item in enumerate(tasks_payload)
            if isinstance(item, dict)
        ]
        decision = cls(
            mode=mode,  # type: ignore[arg-type]
            confidence=float(payload.get("confidence") or 0.0),
            reasoning_summary=str(payload.get("reasoning_summary") or ""),
            tasks=tasks,
            dependencies=[dict(item) for item in payload.get("dependencies") or [] if isinstance(item, dict)],
            selected_agents=[str(value) for value in payload.get("selected_agents") or []],
            needs_user_clarification=bool(payload.get("needs_user_clarification")),
            budget_estimate_usd=float(payload.get("budget_estimate_usd") or 0.0),
            visibility=str(payload.get("visibility") or "thread"),
            final_response_strategy=str(payload.get("final_response_strategy") or "direct"),
        )
        decision.validate()
        return decision


@dataclass(frozen=True)
class TaskDispatchRequest:
    agent_id: str
    task: CoordinationTask
    task_descriptor: TaskDescriptor
    request_id: str
    content: str
    metadata: dict[str, Any]


TaskDispatch = Callable[[TaskDispatchRequest], Awaitable[str | int | None]]


@dataclass(frozen=True)
class CoordinationExecution:
    coordinated: bool
    decision: CoordinationDecision
    task_ids: list[str] = field(default_factory=list)
    dispatched_agents: list[str] = field(default_factory=list)
    message_ids: list[str] = field(default_factory=list)
    delivery_status: str = "coordinating"
    schema_version: str = SQUAD_DELIVERY_SCHEMA_VERSION

    @property
    def dispatched_count(self) -> int:
        return len(self.dispatched_agents)


def _coerce_capability_summaries(
    *,
    participants: list[str],
    coordinator_agent_id: str | None,
    capability_hints: dict[str, str] | None = None,
) -> list[CapabilitySummary]:
    hints = capability_hints or {}
    return [
        CapabilitySummary(
            agent_id=agent_id,
            display_name=agent_id,
            role=hints.get(agent_id, ""),
            is_coordinator=bool(coordinator_agent_id and agent_id == coordinator_agent_id),
        )
        for agent_id in participants
    ]


def request_needs_coordination(
    text: str,
    *,
    has_coordinator: bool,
    participant_count: int,
    semantic_result: SemanticRoutingResult | None = None,
) -> bool:
    """Return true when a turn should go through the supervisor planner."""
    if not has_coordinator or participant_count <= 1 or not str(text or "").strip():
        return False
    if semantic_result is None:
        return True
    return get_squad_semantic_router().should_coordinate(
        text,
        semantic_result,
        has_coordinator=has_coordinator,
    )


def should_use_coordinator_engine(
    text: str,
    *,
    participant_agent_ids: Iterable[str],
    coordinator_agent_id: str | None,
    reply_to_agent_id: str | None = None,
    semantic_result: SemanticRoutingResult | None = None,
) -> bool:
    participants = [p for p in participant_agent_ids if isinstance(p, str) and p]
    if extract_mentions(text, participants):
        return False
    return request_needs_coordination(
        text,
        has_coordinator=bool(coordinator_agent_id and coordinator_agent_id in participants),
        participant_count=len(participants),
        semantic_result=semantic_result,
    )


class CoordinationPlanner(Protocol):
    async def plan(self, planner_input: CoordinationPlannerInput) -> CoordinationDecision: ...


class SemanticFallbackPlanner:
    """Conservative planner used when the LLM is unavailable or returns invalid JSON."""

    async def plan(self, planner_input: CoordinationPlannerInput) -> CoordinationDecision:
        return self.plan_sync(planner_input)

    def plan_sync(self, planner_input: CoordinationPlannerInput) -> CoordinationDecision:
        semantic = planner_input.semantic_result
        proposal_by_agent = {
            str(item.get("agent_id")): item
            for item in planner_input.contribution_proposals
            if isinstance(item, dict) and item.get("agent_id")
        }
        targets = [agent_id for agent_id in proposal_by_agent if agent_id in planner_input.participant_agent_ids] or (
            semantic.top_agents(include_coordinator=False, limit=SQUAD_FANOUT_MAX_PER_TURN)
            if semantic.available
            else []
        )
        targets = targets[:SQUAD_FANOUT_MAX_PER_TURN]
        if not targets:
            return CoordinationDecision(
                mode="answer_self",
                confidence=0.55,
                reasoning_summary=(
                    "Sem embedding/candidato semântico suficiente; o coordenador deve responder diretamente."
                ),
                selected_agents=[planner_input.coordinator_agent_id],
                final_response_strategy="direct",
            )
        summaries = {summary.agent_id: summary for summary in planner_input.capability_summaries}
        tasks = [
            _fallback_task_for_agent(
                agent_id=agent_id,
                summary=summaries.get(agent_id),
                proposal=proposal_by_agent.get(agent_id),
                index=idx + 1,
            )
            for idx, agent_id in enumerate(targets)
        ]
        return CoordinationDecision(
            mode="delegate" if len(tasks) == 1 else "parallel_delegation",
            confidence=max(0.6, min(0.9, semantic.top_score)),
            reasoning_summary=(
                "Ranking semântico e propostas de contribuição indicaram especialistas relevantes; "
                "o plano conservador acionará tarefas reais."
            ),
            tasks=tasks,
            selected_agents=targets,
            budget_estimate_usd=0.2 * len(tasks),
            visibility="thread",
            final_response_strategy="coordinator_synthesis_after_all_task_results",
        )


def _fallback_task_for_agent(
    *,
    agent_id: str,
    summary: CapabilitySummary | None,
    proposal: dict[str, Any] | None,
    index: int,
) -> CoordinationTask:
    objective = str((proposal or {}).get("suggested_contribution") or "").strip()
    if not objective:
        objective = (
            "Contribua com sua especialidade para cumprir o pedido do usuário. "
            "Use apenas o contexto visível do squad e entregue resultado verificável."
        )
    return CoordinationTask(
        key=f"task_{index}",
        title=_fallback_task_title(summary, index),
        agent_id=agent_id,
        kind="specialist",
        objective=objective,
        acceptance_criteria=[
            "Responder ao pedido original dentro da sua especialidade declarada.",
            "Entregar conclusão concreta, evidências ou artefato quando aplicável.",
            "Não afirmar participação de outros agentes sem task_result persistido.",
        ],
        deliverables=["Resultado especializado em markdown e artefatos produzidos, se houver."],
        context_refs=["user_input", "squad_context", "semantic_ranking", "contribution_proposals"],
        report_via="thread",
    )


class LLMCoordinationPlanner:
    def __init__(
        self,
        *,
        fallback: SemanticFallbackPlanner | None = None,
        timeout_s: float = SQUAD_COORDINATOR_LLM_TIMEOUT_S,
    ) -> None:
        self._fallback = fallback or SemanticFallbackPlanner()
        self._timeout_s = max(1.0, float(timeout_s))

    async def plan(self, planner_input: CoordinationPlannerInput) -> CoordinationDecision:
        try:
            provider, model = _resolve_coordinator_provider_model(planner_input.coordinator_agent_id)
            prompt = _planner_prompt(planner_input)
            from koda.services.llm_runner import run_llm

            result = await asyncio.wait_for(
                run_llm(
                    provider=provider,
                    model=model,
                    query=prompt,
                    work_dir=DEFAULT_WORK_DIR,
                    dry_run=False,
                    max_turns=1,
                    system_prompt=_planner_system_prompt(),
                ),
                timeout=self._timeout_s,
            )
            if result.get("error"):
                raise RuntimeError(str(result.get("result") or "planner LLM failed"))
            payload = _extract_json_object(str(result.get("result") or ""))
            payload.setdefault(
                "selected_agents",
                [
                    str(item.get("agent_id"))
                    for item in payload.get("tasks", [])
                    if isinstance(item, dict) and item.get("agent_id")
                ],
            )
            decision = CoordinationDecision.from_dict(payload)
            decision.validate(planner_input.participant_agent_ids)
            return decision
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "squad_coordination_llm_planner_fallback",
                thread_id=planner_input.thread_id,
                coordinator=planner_input.coordinator_agent_id,
                error=str(exc),
            )
            return await self._fallback.plan(planner_input)


def _fallback_task_title(summary: CapabilitySummary | None, index: int) -> str:
    if summary is None:
        return f"Contribuição especializada {index}"
    label = summary.display_name or summary.agent_id
    role = f" ({summary.role})" if summary.role else ""
    return f"Contribuição especializada de {label}{role}"


def _resolve_coordinator_provider_model(agent_id: str) -> tuple[str, str]:
    try:
        from koda.control_plane.manager import get_control_plane_manager

        spec = get_control_plane_manager().get_agent_spec(agent_id)
        model_policy = spec.get("model_policy") if isinstance(spec, dict) else {}
        if not isinstance(model_policy, dict):
            model_policy = {}
        provider = str(model_policy.get("default_provider") or "").strip().lower()
        allowed = [str(value).strip().lower() for value in model_policy.get("allowed_providers") or [] if value]
        provider = provider or (allowed[0] if allowed else "claude")
        default_models = model_policy.get("default_models") or {}
        model = str(default_models.get(provider) or "").strip() if isinstance(default_models, dict) else ""
        functional_defaults = model_policy.get("functional_defaults") or {}
        if not model and isinstance(functional_defaults, dict):
            general = functional_defaults.get("general") or {}
            if isinstance(general, dict) and str(general.get("provider_id") or "").strip().lower() == provider:
                model = str(general.get("model_id") or "").strip()
        return provider or "claude", model or provider or "claude"
    except Exception:
        return "claude", "claude"


def _planner_system_prompt() -> str:
    return (
        "Você é o planejador interno do coordenador de um squad multi-agente. "
        "Responda somente com um objeto JSON válido no schema pedido. "
        "Nunca selecione agentes fora da lista recebida. Nunca invente tarefas já executadas."
    )


def _planner_prompt(planner_input: CoordinationPlannerInput) -> str:
    payload = planner_input.to_prompt_payload()
    schema = {
        "mode": "answer_self|delegate|parallel_delegation|sequential_plan|ask_clarification|handoff|decline",
        "confidence": 0.0,
        "reasoning_summary": "short operational rationale",
        "tasks": [
            {
                "key": "stable_task_key",
                "title": "task title",
                "agent_id": "one participant id",
                "kind": "task kind",
                "objective": "objective",
                "acceptance_criteria": ["criterion"],
                "deliverables": ["deliverable"],
                "depends_on": ["earlier_task_key"],
                "context_refs": ["user_input", "squad_context"],
                "report_via": "thread",
            }
        ],
        "selected_agents": ["agent_id"],
        "needs_user_clarification": False,
        "budget_estimate_usd": 0.0,
        "visibility": "thread",
        "final_response_strategy": "direct|coordinator_synthesis_after_all_task_results",
    }
    return (
        "Planeje a próxima ação do squad a partir do payload abaixo.\n"
        "Use o ranking semântico como fonte de candidatos, mas aplique julgamento profissional.\n"
        "Para trabalho que exige múltiplas contribuições, crie task_requests reais. "
        "Use contribution_proposals como evidência de especialistas que podem ajudar, mas valide dependências e custo. "
        "Para dúvida simples ou score semântico fraco, use answer_self ou ask_clarification.\n\n"
        f"Schema JSON esperado:\n{json.dumps(schema, ensure_ascii=False)}\n\n"
        f"Payload:\n{json.dumps(payload, ensure_ascii=False, default=str)}"
    )


def _extract_json_object(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        payload = json.loads(text[start : end + 1])
        if isinstance(payload, dict):
            return payload
    raise ValueError("planner did not return a JSON object")


class CoordinationPolicyError(ValueError):
    """A coordination decision violates hard squad policy."""


class CoordinationPolicyValidator:
    def __init__(
        self,
        *,
        fanout_max: int = SQUAD_FANOUT_MAX_PER_TURN,
        max_delegation_depth: int = INTER_AGENT_MAX_DELEGATION_DEPTH,
    ) -> None:
        self._fanout_max = max(1, int(fanout_max))
        self._max_delegation_depth = max(0, int(max_delegation_depth))

    def validate(
        self,
        decision: CoordinationDecision,
        *,
        thread: ThreadDescriptor,
        participants: list[str],
        coordinator_agent_id: str,
        delegation_depth: int = 0,
    ) -> None:
        if thread.status != "open":
            raise CoordinationPolicyError(f"thread is {thread.status}")
        if coordinator_agent_id not in participants:
            raise CoordinationPolicyError("coordinator must be an active participant")
        if delegation_depth >= self._max_delegation_depth:
            raise CoordinationPolicyError("delegation depth cap exceeded")
        decision.validate(participants)
        delegated_agents = [agent for agent in decision.selected_agents if agent != coordinator_agent_id]
        if len(delegated_agents) > self._fanout_max:
            raise CoordinationPolicyError(f"fan-out exceeds cap ({self._fanout_max})")
        for task in decision.tasks:
            if task.agent_id == coordinator_agent_id:
                raise CoordinationPolicyError("coordinator cannot create a delegated task for itself")


class SquadCoordinatorEngine:
    def __init__(
        self,
        *,
        thread_store: SquadThreadStore,
        task_store: SquadTaskStore,
        policy: CoordinationPolicyValidator | None = None,
        planner: CoordinationPlanner | None = None,
        semantic_router: SquadSemanticRouter | None = None,
    ) -> None:
        self._thread_store = thread_store
        self._task_store = task_store
        self._policy = policy or CoordinationPolicyValidator()
        self._semantic_router = semantic_router or get_squad_semantic_router()
        if planner is not None:
            self._planner = planner
        elif SQUAD_COORDINATOR_PLANNER == "semantic_llm":
            self._planner = LLMCoordinationPlanner()
        else:
            self._planner = SemanticFallbackPlanner()

    def decide(
        self,
        text: str,
        *,
        participants: list[str],
        coordinator_agent_id: str,
        capability_hints: dict[str, str] | None = None,
        semantic_result: SemanticRoutingResult | None = None,
        capability_summaries: list[CapabilitySummary] | None = None,
    ) -> CoordinationDecision:
        summaries = capability_summaries or _coerce_capability_summaries(
            participants=participants,
            coordinator_agent_id=coordinator_agent_id,
            capability_hints=capability_hints,
        )
        fallback_input = CoordinationPlannerInput(
            text=text,
            thread_id="",
            squad_id="",
            coordinator_agent_id=coordinator_agent_id,
            participant_agent_ids=participants,
            capability_summaries=summaries,
            semantic_result=semantic_result
            or SemanticRoutingResult(
                available=True,
                model_name="precomputed",
                scores=[],
            ),
        )
        return SemanticFallbackPlanner().plan_sync(fallback_input)

    async def coordinate_user_input(
        self,
        *,
        text: str,
        thread: ThreadDescriptor,
        participants: list[ParticipantInfo],
        coordinator_agent_id: str,
        capability_hints: dict[str, str] | None,
        dispatch: TaskDispatch,
        capability_summaries: list[CapabilitySummary] | None = None,
        semantic_result: SemanticRoutingResult | None = None,
        parent_message_id: str | None = None,
        user_id: int | None = None,
        chat_id: int | None = None,
        telegram_message_thread_id: int | None = None,
        delegation_chain: list[str] | None = None,
        awareness_agent_ids: list[str] | None = None,
        contribution_proposals: list[dict[str, Any]] | None = None,
    ) -> CoordinationExecution:
        participant_ids = [p.agent_id for p in participants if p.left_at is None]
        summaries = capability_summaries or _coerce_capability_summaries(
            participants=participant_ids,
            coordinator_agent_id=coordinator_agent_id,
            capability_hints=capability_hints,
        )
        if semantic_result is None:
            semantic_result = await self._semantic_router.rank_agents(
                text,
                summaries,
                squad_id=thread.squad_id,
                coordinator_agent_id=coordinator_agent_id,
            )
        if not semantic_result.available:
            await self._thread_store.post_thread_message(
                thread_id=thread.id,
                from_agent=coordinator_agent_id,
                content=f"[semantic_router_unavailable] {semantic_result.reason or 'semantic routing unavailable'}",
                message_type="system_event",
                metadata={
                    "event_type": "semantic_router_unavailable",
                    "parent_message_id": parent_message_id,
                    "payload": {
                        "event_type": "semantic_router_unavailable",
                        "data": semantic_result.to_dict(),
                    },
                },
            )
            semantic_result = _capability_fallback_semantic_result(
                summaries=summaries,
                coordinator_agent_id=coordinator_agent_id,
                reason=semantic_result.reason or "semantic routing unavailable",
            )
            if not semantic_result.scores:
                return CoordinationExecution(
                    coordinated=False,
                    decision=CoordinationDecision(
                        mode="answer_self",
                        confidence=0.5,
                        reasoning_summary="Roteamento semântico indisponível e nenhum especialista ativo encontrado.",
                        selected_agents=[coordinator_agent_id],
                        final_response_strategy="direct",
                    ),
                )
        planner_input = self._semantic_router.build_planner_input(
            text=text,
            thread=thread,
            coordinator_agent_id=coordinator_agent_id,
            participant_agent_ids=participant_ids,
            capability_summaries=summaries,
            semantic_result=semantic_result,
            parent_message_id=parent_message_id,
            awareness_agent_ids=awareness_agent_ids,
            contribution_proposals=contribution_proposals,
        )
        decision = await self._planner.plan(planner_input)
        if decision.mode == "answer_self":
            return CoordinationExecution(coordinated=False, decision=decision)
        self._policy.validate(
            decision,
            thread=thread,
            participants=participant_ids,
            coordinator_agent_id=coordinator_agent_id,
            delegation_depth=len(delegation_chain or []),
        )
        decision_message_id = await self._post_coordination_decision(
            thread_id=thread.id,
            coordinator_agent_id=coordinator_agent_id,
            decision=decision,
            parent_message_id=parent_message_id,
        )
        task_ids: list[str] = []
        pending_task_ids: list[str] = []
        dispatched_agents: list[str] = []
        dispatch_message_ids: list[str] = [f"msg-{decision_message_id}"]
        handoff_message_ids: list[str] = []
        handoff_correlation_id: str | None = None
        if decision.mode == "handoff":
            handoff_destinations = _handoff_destinations(decision, coordinator_agent_id=coordinator_agent_id)
            handoff_correlation_id = f"handoff:{thread.id}:msg-{decision_message_id}"
            handoff_message_id = await record_squad_handoff_event(
                self._thread_store,
                thread_id=thread.id,
                source_agent_id=coordinator_agent_id,
                destination_agent_ids=handoff_destinations,
                reason=decision.reasoning_summary,
                handoff_kind="parallel_consult" if len(handoff_destinations) > 1 else "consult",
                context_policy={
                    "source": "coordinator_engine",
                    "visibility": decision.visibility,
                    "context_refs": _handoff_context_refs(decision),
                    "final_response_strategy": decision.final_response_strategy,
                },
                deadline=_handoff_deadline(decision),
                return_criteria=_handoff_return_criteria(decision),
                status="requested",
                parent_message_id=parent_message_id,
                correlation_id=handoff_correlation_id,
            )
            if handoff_message_id is not None:
                handoff_message_ids.append(f"msg-{handoff_message_id}")
                dispatch_message_ids.append(f"msg-{handoff_message_id}")
        created_by_key: dict[str, str] = {}
        for index, task in enumerate(decision.tasks):
            depends_on = [created_by_key[key] for key in task.depends_on if key in created_by_key]
            idempotency_key = _idempotency_key(thread.id, parent_message_id, task.agent_id, task.kind, task.objective)
            task_row = await self._task_store.create_task(
                thread_id=thread.id,
                title=task.title,
                assigner_agent_id=coordinator_agent_id,
                description=task.objective,
                kind=task.kind,
                depends_on=depends_on,
                assigned_agent_id=task.agent_id,
                acceptance_criteria=task.acceptance_criteria,
                deliverables_spec=list(task.deliverables),
                delegation_depth=len(delegation_chain or []),
                idempotency_key=idempotency_key,
                metadata={
                    "coordination_parent_message_id": parent_message_id,
                    "coordination_task_key": task.key or task.kind,
                    "coordination_mode": decision.mode,
                    "handoff_correlation_id": handoff_correlation_id,
                    "report_via": task.report_via,
                    "schema_version": SQUAD_DELIVERY_SCHEMA_VERSION,
                    "delivery_status": "waiting_for_replies" if depends_on else "delegated",
                    "delivery_intent": "execution",
                },
            )
            if task.key:
                created_by_key[task.key] = task_row.id
            request_id = f"coord-{task_row.id}"
            request_content = _render_task_request(task=task, source_request=text, task_id=task_row.id)
            metadata = {
                "kind": "task_request",
                "thread_id": thread.id,
                "squad_id": thread.squad_id,
                "squad_task_id": task_row.id,
                "task_id": task_row.id,
                "request_id": request_id,
                "correlation_id": request_id,
                "parent_message_id": parent_message_id,
                "delegation_chain": [*(delegation_chain or []), coordinator_agent_id],
                "telegram_chat_id": thread.telegram_chat_id or chat_id,
                "telegram_message_thread_id": telegram_message_thread_id or thread.telegram_message_thread_id,
                "user_id": user_id or thread.owner_user_id,
                "chat_id": chat_id or thread.telegram_chat_id or 0,
                "payload": {
                    "task_id": task_row.id,
                    "description": task.objective,
                    "deliverables": list(task.deliverables),
                    "deadline": task.deadline,
                    "acceptance_criteria": list(task.acceptance_criteria),
                    "context_refs": list(task.context_refs),
                },
                "delivery_intent": "execution",
                "schema_version": SQUAD_DELIVERY_SCHEMA_VERSION,
                "delivery_status": "waiting_for_replies" if depends_on else "delegated",
                "squad_delivery": {
                    "schema_version": SQUAD_DELIVERY_SCHEMA_VERSION,
                    "status": "waiting_for_replies" if depends_on else "delegated",
                    "source": "coordinator_engine",
                    "target_agent_id": task.agent_id,
                    "task_id": task_row.id,
                    "parent_message_id": parent_message_id,
                    "final_response_strategy": decision.final_response_strategy,
                },
                "idempotency_key": idempotency_key,
                "delivery_queue_status": "waiting_dependencies" if depends_on else "ready",
            }
            visible_msg = await self._thread_store.post_thread_message(
                thread_id=thread.id,
                from_agent=coordinator_agent_id,
                content=request_content,
                message_type="task_request",
                metadata=metadata,
            )
            dispatch_message_ids.append(f"msg-{visible_msg}")
            if depends_on:
                log.info(
                    "squad_coordination_task_waiting_dependencies",
                    thread_id=thread.id,
                    task_id=task_row.id,
                    agent_id=task.agent_id,
                    depends_on=depends_on,
                )
                task_ids.append(task_row.id)
                pending_task_ids.append(task_row.id)
                continue
            try:
                await self._task_store.claim_task(
                    task_id=task_row.id,
                    agent_id=task.agent_id,
                    ttl_seconds=SQUAD_CLAIM_TTL_S,
                )
            except Exception:
                log.exception(
                    "squad_coordination_task_initial_claim_failed",
                    thread_id=thread.id,
                    task_id=task_row.id,
                    agent_id=task.agent_id,
                )
                task_ids.append(task_row.id)
                pending_task_ids.append(task_row.id)
                continue
            dispatched = await dispatch(
                TaskDispatchRequest(
                    agent_id=task.agent_id,
                    task=task,
                    task_descriptor=task_row,
                    request_id=request_id,
                    content=request_content,
                    metadata=metadata,
                )
            )
            if dispatched is not None:
                dispatch_message_ids.append(str(dispatched))
            task_ids.append(task_row.id)
            dispatched_agents.append(task.agent_id)
            log.info(
                "squad_coordination_task_dispatched",
                thread_id=thread.id,
                task_id=task_row.id,
                agent_id=task.agent_id,
                index=index,
            )
        await self._thread_store.notify_event(
            thread_id=thread.id,
            event_type="coordination_dispatched",
            data={
                "schema_version": SQUAD_DELIVERY_SCHEMA_VERSION,
                "delivery_status": "delegated",
                "task_ids": task_ids,
                "agents": dispatched_agents,
                "mode": decision.mode,
                "handoff_message_ids": handoff_message_ids,
                "handoff_correlation_id": handoff_correlation_id,
                "pending_task_ids": pending_task_ids,
            },
        )
        delivery_metric(event_type="coordination_dispatched", status="delegated", source="coordinator_engine")
        return CoordinationExecution(
            coordinated=True,
            decision=decision,
            task_ids=task_ids,
            dispatched_agents=dispatched_agents,
            message_ids=dispatch_message_ids,
            delivery_status="delegated",
        )

    async def _post_coordination_decision(
        self,
        *,
        thread_id: str,
        coordinator_agent_id: str,
        decision: CoordinationDecision,
        parent_message_id: str | None,
    ) -> int:
        selected = ", ".join(decision.selected_agents) or "(none)"
        content = (
            f"[coordination_decision] {decision.mode}: {decision.reasoning_summary} Agentes selecionados: {selected}."
        )
        message_id = await self._thread_store.post_thread_message(
            thread_id=thread_id,
            from_agent=coordinator_agent_id,
            content=content,
            message_type="system_event",
            metadata={
                "event_type": "coordination_decision",
                "schema_version": SQUAD_DELIVERY_SCHEMA_VERSION,
                "delivery_status": "coordinating",
                "delivery_intent": "execution",
                "parent_message_id": parent_message_id,
                "payload": {
                    "schema_version": SQUAD_DELIVERY_SCHEMA_VERSION,
                    "event_type": "coordination_decision",
                    "delivery_status": "coordinating",
                    "delivery_intent": "execution",
                    "data": decision.to_dict(),
                },
                "coordination_decision": decision.to_dict(),
            },
        )
        await self._thread_store.notify_event(
            thread_id=thread_id,
            event_type="coordination_decision",
            data={
                "schema_version": SQUAD_DELIVERY_SCHEMA_VERSION,
                "delivery_status": "coordinating",
                "message_id": message_id,
                "decision": decision.to_dict(),
            },
        )
        delivery_metric(event_type="coordination_decision", status="coordinating", source="coordinator_engine")
        return message_id


def _handoff_destinations(decision: CoordinationDecision, *, coordinator_agent_id: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for agent_id in [*(task.agent_id for task in decision.tasks), *decision.selected_agents]:
        normalized = str(agent_id or "").strip()
        if not normalized or normalized == coordinator_agent_id or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _handoff_context_refs(decision: CoordinationDecision) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for task in decision.tasks:
        for ref in task.context_refs:
            normalized = str(ref or "").strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                refs.append(normalized)
    if not refs:
        refs.append("squad_thread_visible_context")
    return refs


def _handoff_deadline(decision: CoordinationDecision) -> str | None:
    for task in decision.tasks:
        if task.deadline:
            return task.deadline
    return None


def _handoff_return_criteria(decision: CoordinationDecision) -> list[str]:
    criteria: list[str] = []
    seen: set[str] = set()
    for task in decision.tasks:
        for item in [*task.acceptance_criteria, *task.deliverables]:
            normalized = str(item or "").strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                criteria.append(normalized)
    if not criteria:
        criteria.append("Return with a visible reply or task_result before coordinator synthesis.")
    return criteria


def _idempotency_key(
    thread_id: str,
    parent_message_id: str | None,
    agent_id: str,
    kind: str,
    objective: str,
) -> str:
    raw = f"{thread_id}:{parent_message_id or ''}:{agent_id}:{kind}:{objective}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:48]


def _capability_fallback_semantic_result(
    *,
    summaries: list[CapabilitySummary],
    coordinator_agent_id: str,
    reason: str,
) -> SemanticRoutingResult:
    """Build a non-semantic specialist ordering when embeddings are offline."""

    scores: list[SemanticAgentScore] = []
    for index, summary in enumerate(summaries):
        is_coordinator = summary.agent_id == coordinator_agent_id or summary.is_coordinator
        if is_coordinator:
            continue
        summary_text = " ".join(
            part
            for part in [
                summary.role,
                *summary.domains[:3],
                *summary.primary_outcomes[:3],
                summary.delegate_when,
            ]
            if str(part or "").strip()
        )
        scores.append(
            SemanticAgentScore(
                agent_id=summary.agent_id,
                score=max(0.35, 0.75 - (index * 0.03)),
                positive_score=max(0.35, 0.75 - (index * 0.03)),
                negative_score=0.0,
                summary_text=summary_text or summary.display_name or summary.agent_id,
                is_coordinator=False,
            )
        )
    return SemanticRoutingResult(
        available=True,
        model_name="capability-fallback",
        scores=scores,
        reason=reason,
        min_score=0.0,
        top_k=max(1, len(scores)),
    )


def _render_task_request(*, task: CoordinationTask, source_request: str, task_id: str) -> str:
    lines = [
        f"Task request [{task.kind}] {task_id}",
        f"Assigned to: {task.agent_id}",
        "",
        "Execution role:",
        "- You are the assigned worker for this task, not the squad coordinator.",
        "- The coordinator has already delegated the work. Do not spawn, delegate, or ask others to do this task.",
        "- Treat the source user request as context; your responsibility is the Objective below.",
        "- Return only your own concrete task_result for this assigned objective.",
        "",
        "Source user request:",
        source_request.strip(),
        "",
        "Objective:",
        task.objective.strip(),
    ]
    if task.acceptance_criteria:
        lines.extend(["", "Acceptance criteria:"])
        lines.extend(f"- {item}" for item in task.acceptance_criteria)
    if task.deliverables:
        lines.extend(["", "Deliverables:"])
        lines.extend(f"- {item}" for item in task.deliverables)
    if task.context_refs:
        lines.extend(["", "Context refs: " + ", ".join(task.context_refs)])
    lines.extend(
        [
            "",
            "Return a concrete task_result in this thread without progress narration. Do not claim other agents "
            "contributed unless their task_result is visible.",
        ]
    )
    return "\n".join(lines)


def make_request_id() -> str:
    return f"coord-{uuid.uuid4()}"
