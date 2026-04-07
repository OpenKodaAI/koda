"""Procedural memory helpers for reusable execution patterns."""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from koda.memory.config import MEMORY_PROCEDURAL_MAX_RECALL
from koda.memory.store import MemoryStore
from koda.memory.types import Memory, MemoryStatus, MemoryType, build_conflict_key

_VALIDATION_COMMAND_RE = re.compile(
    r"\b(pytest|ruff check|ruff format --check|mypy|npm test|pnpm test|yarn test|vitest|go test|cargo test)\b",
    re.I,
)


@dataclass(slots=True)
class ObservedPattern:
    """Structured procedural recall used as the lowest knowledge layer."""

    content: str
    updated_at: datetime
    owner: str
    source_label: str
    metadata: dict[str, Any]


def infer_validation_summary(tool_uses: list[dict[str, Any]]) -> str:
    """Summarize validations detected in native provider tool usage."""
    commands: list[str] = []
    for tool in tool_uses:
        if tool.get("name") != "Bash":
            continue
        command = str(tool.get("input", {}).get("command", ""))
        match = _VALIDATION_COMMAND_RE.search(command)
        if match:
            commands.append(match.group(1))
    if not commands:
        return "no explicit validation detected"
    unique_commands = list(OrderedDict.fromkeys(commands))
    return ", ".join(unique_commands)


def build_execution_memories(
    *,
    query: str,
    user_id: int,
    task_id: int | None,
    status: str,
    confidence_score: float | None,
    error_message: str | None,
    tool_uses: list[dict[str, Any]],
    tool_execution_trace: list[dict[str, Any]],
    knowledge_hits: list[dict[str, Any]] | None,
    work_dir: str | None,
    model: str | None,
    task_kind: str | None = None,
    project_key: str = "",
    environment: str = "",
    team: str = "",
    owner: str = "",
    source_episode_id: int | None = None,
) -> list[Memory]:
    """Create procedural memories from an execution outcome."""
    from koda.knowledge.task_policy_defaults import classify_task_kind

    task_kind = task_kind or classify_task_kind(query)
    validation_summary = infer_validation_summary(tool_uses)
    outcome = "success" if status == "completed" else "failure"
    confidence = confidence_score if confidence_score is not None else 0.5
    tools = [step.get("tool") for step in tool_execution_trace if step.get("tool")]
    tool_list = ", ".join(list(OrderedDict.fromkeys(str(tool) for tool in tools))) or "no agent tools"
    source_labels = [str(hit.get("source_label")) for hit in (knowledge_hits or []) if hit.get("source_label")]
    source_summary = ", ".join(list(OrderedDict.fromkeys(source_labels[:3]))) or "runtime inspection"
    preview = query.strip().replace("\n", " ")[:140]

    if outcome == "success":
        content = (
            f"Procedimento validado para {task_kind}: em tarefas como '{preview}', "
            f"comece reunindo evidências e fontes ({source_summary}), execute apenas depois de um mini-plano, "
            f"use ferramentas como {tool_list}, e finalize verificando com {validation_summary}."
        )
        importance = 0.82
    else:
        error_summary = (error_message or "unknown error")[:160]
        content = (
            f"Cautela para {task_kind}: uma execução de '{preview}' falhou. "
            f"Evite agir sem plano e sem fontes atualizadas; o risco observado foi '{error_summary}'. "
            f"Ferramentas tentadas: {tool_list}. Validação detectada: {validation_summary}."
        )
        importance = 0.74

    metadata: dict[str, object] = {
        "origin": "procedural_memory",
        "task_kind": task_kind,
        "outcome": outcome,
        "task_id": task_id,
        "confidence_score": round(confidence, 4),
        "validation_summary": validation_summary,
        "source_labels": list(OrderedDict.fromkeys(source_labels)),
        "tool_names": list(OrderedDict.fromkeys(str(tool) for tool in tools)),
        "work_dir": work_dir,
        "model": model,
        "project_key": project_key,
        "environment": environment,
        "team": team,
        "owner": owner,
    }

    return [
        Memory(
            user_id=user_id,
            memory_type=MemoryType.PROCEDURE,
            content=content,
            importance=importance,
            agent_id=owner or None,
            origin_kind="procedural_memory",
            source_task_id=task_id,
            source_episode_id=source_episode_id,
            project_key=project_key,
            environment=environment,
            team=team,
            quality_score=max(importance, min(1.0, confidence)),
            extraction_confidence=min(1.0, confidence),
            embedding_status="pending",
            claim_kind="procedure" if outcome == "success" else "risk_pattern",
            subject=task_kind,
            decision_source="runtime_observation",
            evidence_refs=list(OrderedDict.fromkeys(source_labels[:5])),
            applicability_scope={
                "project_key": project_key,
                "environment": environment,
                "team": team,
                "task_kind": task_kind,
            },
            conflict_key=build_conflict_key(
                MemoryType.PROCEDURE,
                subject=task_kind,
                project_key=project_key,
                environment=environment,
                team=team,
            ),
            memory_status=MemoryStatus.ACTIVE.value,
            retention_reason="validated execution pattern" if outcome == "success" else "execution caution pattern",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(days=365),
            metadata=metadata,
        )
    ]


async def search_observed_patterns(
    store: MemoryStore,
    query: str,
    user_id: int,
    *,
    max_results: int,
    task_kind: str = "",
    project_key: str = "",
    environment: str = "",
    team: str = "",
    owner: str = "",
) -> list[ObservedPattern]:
    """Return procedural observations as structured entries for grounded retrieval."""
    results = await store.search(
        query=query,
        user_id=user_id,
        n_results=max(max_results * 4, max_results),
        memory_types=[MemoryType.PROCEDURE],
        project_key=project_key,
        environment=environment,
        team=team,
    )
    observed: list[ObservedPattern] = []
    for result in results:
        metadata = result.memory.metadata or {}
        if task_kind and str(metadata.get("task_kind") or "") != task_kind:
            continue
        if project_key and str(metadata.get("project_key") or "") != project_key:
            continue
        if environment and str(metadata.get("environment") or "") != environment:
            continue
        if team and str(metadata.get("team") or "") != team:
            continue
        if owner and str(metadata.get("owner") or "") != owner:
            continue
        owner = str(metadata.get("owner") or "observed_execution")
        task_id = metadata.get("task_id")
        source_label = f"procedure#{task_id}" if task_id is not None else "procedure"
        observed.append(
            ObservedPattern(
                content=result.memory.content,
                updated_at=result.memory.created_at,
                owner=owner,
                source_label=source_label,
                metadata=metadata,
            )
        )
        if len(observed) >= max_results:
            break
    return observed


async def build_procedural_context(
    store: MemoryStore,
    query: str,
    user_id: int,
    *,
    project_key: str = "",
    environment: str = "",
    team: str = "",
    session_id: str | None = None,
) -> str:
    """Retrieve successful and failed procedural memories relevant to the query."""
    results = await store.search(
        query=query,
        user_id=user_id,
        n_results=MEMORY_PROCEDURAL_MAX_RECALL,
        memory_types=[MemoryType.PROCEDURE],
        project_key=project_key,
        environment=environment,
        team=team,
    )
    if not results:
        return ""

    successes: list[str] = []
    cautions: list[str] = []
    for result in results:
        metadata = result.memory.metadata or {}
        if project_key and str(metadata.get("project_key") or result.memory.project_key or "") not in {project_key, ""}:
            continue
        if environment and str(metadata.get("environment") or result.memory.environment or "") not in {environment, ""}:
            continue
        if team and str(metadata.get("team") or result.memory.team or "") not in {team, ""}:
            continue
        if session_id and result.memory.session_id and result.memory.session_id != session_id:
            continue
        task_id = metadata.get("task_id")
        validation = metadata.get("validation_summary")
        confidence = metadata.get("confidence_score")
        prefix = []
        if task_id is not None:
            prefix.append(f"task #{task_id}")
        if confidence is not None:
            prefix.append(f"confidence {confidence:.2f}")
        if validation:
            prefix.append(str(validation))
        label = " | ".join(prefix)
        rendered = f"- [{label}] {result.memory.content}" if label else f"- {result.memory.content}"
        if metadata.get("outcome") == "failure":
            cautions.append(rendered)
        else:
            successes.append(rendered)

    if not successes and not cautions:
        return ""

    sections = ["## Memória Procedural"]
    if successes:
        sections.append("### Procedimentos Validados\n" + "\n".join(successes))
    if cautions:
        sections.append("### Cautelas\n" + "\n".join(cautions))
    return "\n\n".join(sections)
