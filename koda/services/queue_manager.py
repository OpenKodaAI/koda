"""Per-user async queue management.

Bug fixes:
- Race condition on worker spawn: uses asyncio.Lock per user
- Validates work_dir before use

Features:
- Streaming responses with throttled edits
- Auto-model routing
- Bookmark button on responses
- Session auto-save
- Tool use visibility
"""

import asyncio
import contextlib
import hashlib
import inspect
import json
import os
import subprocess
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from koda.config import (
    AGENT_ID,
    ARTIFACT_EXTRACTION_TIMEOUT,
    DEFAULT_PROVIDER,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_WORK_DIR,
    IMAGE_TEMP_DIR,
    JIRA_DEEP_CONTEXT_ENABLED,
    JIRA_DEEP_CONTEXT_MAX_ISSUES,
    JIRA_ENABLED,
    MAX_AGENT_TOOL_ITERATIONS,
    MAX_BROWSER_TASKS_GLOBAL,
    MAX_CONCURRENT_TASKS_GLOBAL,
    MAX_CONCURRENT_TASKS_PER_USER,
    MAX_HEAVY_TASKS_GLOBAL,
    MAX_STANDARD_TASKS_GLOBAL,
    MAX_TOTAL_BUDGET_USD,
    MAX_TURNS,
    PROVIDER_MODELS,
    RUNTIME_ENVIRONMENTS_ENABLED,
    RUNTIME_HEARTBEAT_INTERVAL_SECONDS,
    TASK_MAX_RETRY_ATTEMPTS,
    TASK_RETRY_BASE_DELAY,
    TASK_RETRY_MAX_DELAY,
    TRANSCRIPT_REPLAY_LIMIT,
    TTS_ENABLED,
    VOICE_ACTIVE_PROMPT,
)
from koda.logging_config import ctx_query_id, ctx_user_id, get_logger
from koda.services.llm_runner import (
    build_bootstrap_prompt,
    get_provider_capabilities,
    get_provider_fallback_chain,
    is_retryable_provider_error,
    resolve_provider_model,
    run_llm,
    run_llm_streaming,
    summarize_native_items,
)
from koda.services.prompt_budget import PromptBudgetPlanner, PromptSegment
from koda.services.provider_runtime import TurnMode, infer_turn_mode
from koda.state.history_store import (
    create_task,
    delete_provider_session_mapping,
    dlq_insert,
    get_provider_session_mapping,
    log_query,
    save_provider_session_mapping,
    save_session,
    save_user_cost,
    update_task_status,
)
from koda.state.knowledge_governance_store import get_execution_reliability_stats, list_approved_runbooks
from koda.telegram_types import BotContext
from koda.telegram_types import MessageUpdate as Update
from koda.utils.artifacts import extract_created_files, send_created_files
from koda.utils.command_helpers import (
    ensure_canonical_session_id,
    get_provider_model,
    normalize_provider,
)
from koda.utils.images import untrack_images
from koda.utils.progress import (
    _format_elapsed,
    compact_tool_label,
    progress_indicator,
)
from koda.utils.tool_parser import (
    format_tool_summary,
    parse_tool_uses,
    summarize_tool_uses,
)
from koda.utils.workdir import validate_work_dir

log = get_logger(__name__)


class CacheHitLike(Protocol):
    match_type: str
    similarity: float
    response: str


class TelegramBotLike(Protocol):
    async def send_message(self, *args: Any, **kwargs: Any) -> Any: ...


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class QueueItem:
    """Parsed queue item with all fields resolved."""

    chat_id: int
    query_text: str
    update: Update | None = None
    image_paths: list[str] | None = None
    artifact_bundle: Any | None = None
    is_continuation: bool = False
    is_link_analysis: bool = False
    continuation_session_id: str | None = None
    continuation_provider: str | None = None
    is_scheduled_run: bool = False
    scheduled_job_id: int | None = None
    scheduled_run_id: int | None = None
    scheduled_dry_run: bool = False
    scheduled_provider: str | None = None
    scheduled_model: str | None = None
    scheduled_work_dir: str | None = None
    scheduled_session_id: str | None = None
    scheduled_trigger_reason: str | None = None
    runtime_work_dir: str | None = None
    is_dashboard_chat: bool = False
    override_session_id: str | None = None


@dataclass
class QueryContext:
    """Resolved context for a single query execution."""

    provider: str
    work_dir: str
    model: str
    session_id: str
    provider_session_id: str | None
    system_prompt: str
    agent_mode: str
    permission_mode: str
    max_turns: int
    task_id: int | None = None
    warnings: list[str] = field(default_factory=list)
    fallback_chain: list[str] = field(default_factory=list)
    cache_hit: CacheHitLike | None = None  # CacheLookupResult from cache_manager
    script_matches: list = field(default_factory=list)  # list[ScriptSearchResult]
    knowledge_hits: list[Any] = field(default_factory=list)
    knowledge_resolution: Any | None = None
    memory_resolution: Any | None = None
    memory_profile: Any | None = None
    memory_trust_score: float = 0.0
    confidence_reports: list[dict[str, Any]] = field(default_factory=list)
    task_kind: str = "general"
    knowledge_query_context: Any | None = None
    effective_policy: Any | None = None
    ungrounded_operationally: bool = False
    stale_sources_present: bool = False
    last_action_plan: dict[str, Any] | None = None
    verified_before_finalize: bool = False
    human_approval_used: bool = False
    execution_episode_id: int | None = None
    answer_evaluation: Any | None = None
    grounding_gate_decision: Any | None = None
    grounded_answer: Any | None = None
    answer_judgement: Any | None = None
    turn_mode: TurnMode = "new_turn"
    resume_requested: bool = False
    supports_native_resume: bool = True
    provider_available: bool = True
    dry_run: bool = False
    scheduled_job_id: int | None = None
    scheduled_run_id: int | None = None
    artifact_dossiers: list[Any] = field(default_factory=list)
    visual_paths: list[str] = field(default_factory=list)
    temp_paths: list[str] = field(default_factory=list)
    runtime_env_id: int | None = None
    runtime_classification: str = "light"
    runtime_environment_kind: str = "dev_worktree"
    prompt_budget: dict[str, Any] | None = None
    asset_refs: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RunResult:
    """Result from provider execution."""

    provider: str
    model: str
    result: str
    session_id: str
    provider_session_id: str | None
    cost_usd: float
    error: bool
    stop_reason: str
    usage: dict[str, Any] = field(default_factory=dict)
    tool_uses: list[dict] = field(default_factory=list)
    native_items: list[dict[str, Any]] = field(default_factory=list)
    tool_execution_trace: list[dict[str, Any]] = field(default_factory=list)
    raw_output: str = ""
    warnings: list[str] = field(default_factory=list)
    fallback_chain: list[str] = field(default_factory=list)
    turn_mode: TurnMode = "new_turn"
    supports_native_resume: bool = True
    error_kind: str = ""
    retryable: bool = False
    runtime_terminal_id: int | None = None
    runtime_terminal_path: str | None = None


class BudgetExceeded(Exception):
    """Raised when the user has exceeded their budget."""


@dataclass
class TaskInfo:
    """In-memory state for an active task."""

    task_id: int
    user_id: int
    chat_id: int
    query_text: str
    status: str = "queued"
    attempt: int = 1
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    cost_usd: float = 0.0
    error_message: str | None = None
    model: str | None = None
    asyncio_task: asyncio.Task | None = None
    runtime_env_id: int | None = None
    runtime_classification: str | None = None
    runtime_environment_kind: str | None = None
    runtime_work_dir: str | None = None


class _RetryableError(Exception):
    """Transient error that allows retry (overloaded, rate limit, connection, timeout)."""


class _RuntimeGuardrailError(Exception):
    """Runtime guardrail triggered and execution must stop safely."""


# ---------------------------------------------------------------------------
# Helper functions (compact tool labels, status line)
# ---------------------------------------------------------------------------


def _compact_tool_label(name: str, input_data: dict | None = None) -> str:
    """Build a compact label like 'Read(file.py)', 'Bash(npm test...)'."""
    return compact_tool_label(name, input_data)


def _get_throttle_interval(elapsed: float) -> float:
    """Adaptive throttle: fast at start, slower for long tasks."""
    if elapsed < 10:
        return 1.5
    if elapsed < 30:
        return 3.0
    if elapsed < 120:
        return 5.0
    return 8.0


def _make_timeline_item(
    item_type: str,
    title: str,
    *,
    timestamp: str | None = None,
    status: str = "info",
    summary: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": item_type,
        "title": title,
        "status": status,
        "timestamp": timestamp or datetime.now(UTC).isoformat(),
    }
    if summary:
        payload["summary"] = summary
    if details:
        payload["details"] = details
    return payload


def _build_operational_reasoning(
    *,
    provider: str | None,
    model: str | None,
    status: str,
    stop_reason: str,
    warning_count: int,
    tool_count: int,
    attempt: int,
    max_attempts: int,
) -> list[str]:
    notes: list[str] = []
    if model:
        if provider:
            notes.append(f"A execução foi conduzida com o provider {provider} e o modelo {model}.")
        else:
            notes.append(f"A execução foi conduzida com o modelo {model}.")
    if tool_count:
        notes.append(f"O agent acionou {tool_count} ferramenta(s) ao longo da resolução.")
    else:
        notes.append("A resposta foi produzida sem uso de ferramentas auxiliares.")
    if stop_reason:
        notes.append(f"O ciclo do runtime foi encerrado com stop reason '{stop_reason}'.")
    if warning_count:
        notes.append(f"Foram registrados {warning_count} warning(s) operacionais durante a execução.")
    if status == "completed":
        notes.append(f"A tarefa terminou com sucesso na tentativa {attempt} de {max_attempts}.")
    else:
        notes.append(f"A tarefa terminou em {status} após {attempt} tentativa(s) de {max_attempts}.")
    return notes


def _build_execution_trace_payload(
    *,
    item: QueueItem,
    task_info: TaskInfo,
    ctx: QueryContext | None,
    run_result: RunResult | None,
    status: str,
    work_dir: str | None,
    timeline: list[dict[str, Any]],
    error_message: str | None = None,
    response_text_override: str | None = None,
) -> dict[str, Any]:
    tool_steps = run_result.tool_execution_trace if run_result else []
    tool_count = len(tool_steps)
    warning_count = len(run_result.warnings) if run_result else 0
    reasoning_summary = _build_operational_reasoning(
        provider=run_result.provider if run_result else None,
        model=task_info.model,
        status=status,
        stop_reason=run_result.stop_reason if run_result else "",
        warning_count=warning_count,
        tool_count=tool_count,
        attempt=task_info.attempt,
        max_attempts=TASK_MAX_RETRY_ATTEMPTS,
    )
    return {
        "query_text": item.query_text,
        "response_text": (
            response_text_override
            if response_text_override is not None
            else (run_result.result if run_result else None)
        ),
        "provider": run_result.provider if run_result else None,
        "model": task_info.model,
        "session_id": run_result.session_id if run_result else None,
        "provider_session_id": run_result.provider_session_id if run_result else None,
        "work_dir": work_dir,
        "status": status,
        "cost_usd": task_info.cost_usd,
        "duration_ms": (
            ((task_info.completed_at or time.time()) - task_info.started_at) * 1000 if task_info.started_at else None
        ),
        "stop_reason": run_result.stop_reason if run_result else None,
        "warnings": run_result.warnings if run_result else [],
        "tool_uses": run_result.tool_uses if run_result else [],
        "tools": tool_steps,
        "timeline": timeline,
        "reasoning_summary": reasoning_summary,
        "grounding": {
            "knowledge_hits": _serialize_knowledge_hits(ctx.knowledge_hits if ctx else []),
            "knowledge_hit_count": len(ctx.knowledge_hits) if ctx else 0,
            "memory_trust_score": float(ctx.memory_trust_score) if ctx else 0.0,
            "memory_layers": list(getattr(ctx.memory_resolution, "selected_layers", []) or []) if ctx else [],
            "memory_retrieval_sources": (
                list(getattr(ctx.memory_resolution, "retrieval_sources", []) or []) if ctx else []
            ),
            "memory_explanations": [
                {
                    "memory_id": explanation.memory_id,
                    "layer": explanation.layer,
                    "retrieval_source": explanation.retrieval_source,
                    "score": explanation.score,
                    "scope_score": explanation.scope_score,
                    "reasons": explanation.reasons,
                    "source_query_id": explanation.source_query_id,
                    "source_task_id": explanation.source_task_id,
                    "source_episode_id": explanation.source_episode_id,
                }
                for explanation in (getattr(ctx.memory_resolution, "explanations", []) if ctx else [])
            ],
            "task_kind": ctx.task_kind if ctx else "general",
            "ungrounded_operationally": bool(ctx.ungrounded_operationally) if ctx else False,
            "stale_sources_present": bool(ctx.stale_sources_present) if ctx else False,
            "artifact_dossier_count": len(ctx.artifact_dossiers) if ctx else 0,
            "artifact_blocking_gaps": any(dossier.has_blocking_gaps for dossier in ctx.artifact_dossiers)
            if ctx
            else False,
            "guardrails": [
                {
                    "id": guardrail.id,
                    "title": guardrail.title,
                    "severity": guardrail.severity,
                    "reason": guardrail.reason,
                    "source_label": guardrail.source_label,
                }
                for guardrail in (getattr(ctx.knowledge_resolution, "guardrails", []) if ctx else [])
            ],
            "conflicts": [
                {
                    "title": conflict.title,
                    "higher_layer": conflict.higher_layer.value,
                    "lower_layer": conflict.lower_layer.value,
                    "higher_source_label": conflict.higher_source_label,
                    "lower_source_label": conflict.lower_source_label,
                }
                for conflict in (getattr(ctx.knowledge_resolution, "conflicts", []) if ctx else [])
            ],
            "effective_policy": _policy_to_dict(ctx.effective_policy if ctx else None),
            "verified_before_finalize": bool(ctx.verified_before_finalize) if ctx else False,
        },
        "confidence_reports": list(ctx.confidence_reports) if ctx else [],
        "raw_artifacts": {
            "assistant_raw_output": run_result.raw_output if run_result and run_result.raw_output else None,
            "native_items": run_result.native_items if run_result else [],
            "fallback_chain": run_result.fallback_chain if run_result else [],
            "artifact_dossiers": [dossier.to_trace_dict() for dossier in ctx.artifact_dossiers] if ctx else [],
        },
        "error_message": error_message,
    }


def _tool_steps_to_timeline(tool_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    timeline: list[dict[str, Any]] = []
    for step in tool_steps:
        tool_name = str(step.get("tool") or "tool")
        success = bool(step.get("success"))
        summary = step.get("metadata", {}).get("category")
        if summary:
            description = f"{tool_name} ({summary})"
        else:
            description = tool_name
        timeline.append(
            _make_timeline_item(
                "task.tool_executed",
                f"Ferramenta {tool_name}",
                timestamp=step.get("completed_at"),
                status="success" if success else "error",
                summary=description,
                details={
                    "tool": tool_name,
                    "duration_ms": step.get("duration_ms"),
                    "success": success,
                },
            )
        )
    return timeline


def _serialize_knowledge_hits(hits: list[Any]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for hit in hits:
        if hasattr(hit, "to_trace_dict"):
            serialized.append(hit.to_trace_dict())
        elif isinstance(hit, dict):
            serialized.append(hit)
    return serialized


async def _persist_artifact_evidence_nodes(
    query_context: Any | None,
    dossiers: list[Any],
) -> None:
    if query_context is None or not dossiers:
        return
    try:
        from koda.knowledge import get_knowledge_manager

        km = get_knowledge_manager()
        if km.initialized:
            await km.ingest_artifact_dossiers(query_context, dossiers)
    except Exception:
        log.exception("artifact_evidence_import_error")


def _policy_to_dict(policy: Any | None) -> dict[str, Any]:
    if policy is None:
        return {}
    required_layers = getattr(policy, "required_layers", ())
    return {
        "task_kind": getattr(policy, "task_kind", ""),
        "autonomy_tier": getattr(getattr(policy, "autonomy_tier", None), "value", ""),
        "min_read_evidence": getattr(policy, "min_read_evidence", 1),
        "required_source_layers": [layer.value if hasattr(layer, "value") else str(layer) for layer in required_layers],
        "required_verifications": list(getattr(policy, "required_verifications", ())),
        "requires_rollback": bool(getattr(policy, "requires_rollback", False)),
        "requires_probable_cause": bool(getattr(policy, "requires_probable_cause", False)),
        "approval_mode": getattr(policy, "approval_mode", "standard"),
        "max_source_age_days": getattr(policy, "max_source_age_days", 90),
    }


def _workspace_fingerprint(work_dir: str) -> str:
    return hashlib.sha256(work_dir.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


def _workspace_diff_hash(work_dir: str | None) -> str:
    if not work_dir:
        return ""
    try:
        status_result = subprocess.run(
            ["git", "-C", work_dir, "status", "--short", "--untracked-files=all"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return ""
    if status_result.returncode != 0:
        return ""
    status_text = status_result.stdout or ""
    if not status_text.strip():
        return "clean"
    try:
        diff_result = subprocess.run(
            ["git", "-C", work_dir, "diff", "--binary", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        diff_text = ""
    else:
        diff_text = diff_result.stdout or ""
    return _hash_text(diff_text or status_text)


def _parse_runbook_id_from_source_path(source_path: str) -> int | None:
    if not source_path.startswith("approved_runbook:"):
        return None
    try:
        return int(source_path.split(":", 1)[1])
    except ValueError:
        return None


def _select_policy_runbook(
    scoped_runbooks: list[dict[str, Any]],
    knowledge_resolution: Any | None,
) -> dict[str, Any] | None:
    if not scoped_runbooks:
        return None
    runbooks_by_id = {
        int(runbook["id"]): runbook for runbook in scoped_runbooks if isinstance(runbook.get("id"), (int, str))
    }
    if knowledge_resolution is not None:
        for hit in getattr(knowledge_resolution, "hits", []) or []:
            layer = getattr(getattr(hit, "entry", None), "layer", None)
            source_path = str(getattr(getattr(hit, "entry", None), "source_path", "") or "")
            if getattr(layer, "value", layer) != "approved_runbook":
                continue
            runbook_id = _parse_runbook_id_from_source_path(source_path)
            if runbook_id is not None and runbook_id in runbooks_by_id:
                return runbooks_by_id[runbook_id]
    if len(scoped_runbooks) == 1:
        return scoped_runbooks[0]
    return None


def _apply_policy_overrides(base_policy: Any, runbook: dict[str, Any] | None) -> Any:
    if base_policy is None or not runbook:
        return base_policy
    from koda.knowledge.policy import sanitize_policy_overrides

    try:
        overrides = sanitize_policy_overrides(dict(runbook.get("policy_overrides") or {}))
    except (TypeError, ValueError):
        log.warning(
            "invalid_policy_overrides_ignored",
            runbook_id=runbook.get("id"),
            overrides=runbook.get("policy_overrides"),
        )
        return base_policy

    if not overrides:
        return base_policy
    patch: dict[str, Any] = {}
    if "min_read_evidence" in overrides:
        patch["min_read_evidence"] = int(overrides["min_read_evidence"])
    if "required_layers" in overrides:
        from koda.knowledge.types import KnowledgeLayer

        patch["required_layers"] = tuple(KnowledgeLayer(str(item)) for item in overrides["required_layers"])
    if "required_verifications" in overrides:
        patch["required_verifications"] = tuple(str(item) for item in overrides["required_verifications"])
    if "requires_rollback" in overrides:
        patch["requires_rollback"] = bool(overrides["requires_rollback"])
    if "requires_probable_cause" in overrides:
        patch["requires_probable_cause"] = bool(overrides["requires_probable_cause"])
    if "approval_mode" in overrides:
        patch["approval_mode"] = str(overrides["approval_mode"])
    if "max_source_age_days" in overrides:
        patch["max_source_age_days"] = int(overrides["max_source_age_days"])
    if "autonomy_tier" in overrides and hasattr(base_policy, "autonomy_tier"):
        from koda.knowledge.types import AutonomyTier

        patch["autonomy_tier"] = AutonomyTier(str(overrides["autonomy_tier"]).lower())
    return replace(base_policy, **patch) if patch else base_policy


def _downgrade_policy_from_reliability(base_policy: Any, stats: dict[str, Any]) -> Any:
    if base_policy is None:
        return None
    total_runs = int(stats.get("total_runs") or 0)
    successful_runs = int(stats.get("successful_runs") or 0)
    correction_count = int(stats.get("correction_count") or 0)
    success_rate = (successful_runs / total_runs) if total_runs else 0.0
    if getattr(getattr(base_policy, "autonomy_tier", None), "value", "") != "t2":
        return base_policy
    if total_runs < 3 or success_rate < 0.75 or correction_count > 0:
        return replace(base_policy, approval_mode="supervised")
    return base_policy


def _has_post_write_verification(tool_steps: list[dict[str, Any]]) -> bool:
    """Whether a successful read-only check happened after the last write."""
    last_write_index: int | None = None
    for index, step in enumerate(tool_steps):
        if step.get("metadata", {}).get("write"):
            last_write_index = index
    if last_write_index is None:
        return False
    for step in tool_steps[last_write_index + 1 :]:
        if step.get("success") and not step.get("metadata", {}).get("write"):
            return True
    return False


def _requires_post_write_verification(ctx: QueryContext) -> bool:
    policy = ctx.effective_policy
    if policy is None:
        return False
    return bool(getattr(policy, "required_verifications", ()))


def _has_grounded_operational_layer(hits: list[Any]) -> bool:
    serialized_hits = _serialize_knowledge_hits(hits)
    return any(hit.get("layer") in {"canonical_policy", "approved_runbook"} for hit in serialized_hits)


def _latest_confidence_score(ctx: QueryContext | None) -> float | None:
    if not ctx or not ctx.confidence_reports:
        return None
    latest = ctx.confidence_reports[-1]
    score = latest.get("score")
    if isinstance(score, (int, float)):
        return float(score)
    return None


def _answer_eval_value(answer_evaluation: Any | None, field: str, default: Any = None) -> Any:
    if answer_evaluation is None:
        return default
    if isinstance(answer_evaluation, dict):
        return answer_evaluation.get(field, default)
    return getattr(answer_evaluation, field, default)


_knowledge_orchestration_service: Any | None = None
_query_context_service: Any | None = None
_execution_episode_service: Any | None = None


def _get_knowledge_orchestration_service() -> Any:
    global _knowledge_orchestration_service
    if _knowledge_orchestration_service is None:
        from koda.knowledge.repository import KnowledgeRepository
        from koda.knowledge.storage_v2 import KnowledgeStorageV2
        from koda.services.knowledge_orchestration_service import KnowledgeOrchestrationService

        repository = KnowledgeRepository(AGENT_ID or None)
        storage = KnowledgeStorageV2(repository, AGENT_ID or None)
        _knowledge_orchestration_service = KnowledgeOrchestrationService(storage)
    return _knowledge_orchestration_service


def _get_query_context_service() -> Any:
    global _query_context_service
    if _query_context_service is None:
        from koda.services.query_context_service import QueryContextService

        _query_context_service = QueryContextService()
    return _query_context_service


def _get_execution_episode_service() -> Any:
    global _execution_episode_service
    if _execution_episode_service is None:
        from koda.services.execution_episode_service import ExecutionEpisodeService

        _execution_episode_service = ExecutionEpisodeService(agent_id=AGENT_ID)
    return _execution_episode_service


def _append_prompt_segment(
    segments: list[PromptSegment],
    *,
    segment_id: str,
    text: str,
    category: str,
    priority: int,
    compression_strategy: str = "truncate_tail",
    drop_policy: str = "drop",
    metadata: dict[str, Any] | None = None,
) -> None:
    if not str(text or "").strip():
        return
    segments.append(
        PromptSegment(
            segment_id=segment_id,
            text=str(text).strip(),
            category=category,
            priority=priority,
            compression_strategy=compression_strategy,
            drop_policy=drop_policy,
            metadata=dict(metadata or {}),
        )
    )


def _compile_runtime_prompt_budget(
    *,
    provider: str,
    model: str,
    segments: list[PromptSegment],
    memory_context_max_tokens: int,
    knowledge_context_max_tokens: int,
) -> dict[str, Any]:
    result = PromptBudgetPlanner().compile(
        provider=provider,
        model=model,
        segments=segments,
        category_token_caps={
            "memory": memory_context_max_tokens,
            "authoritative_knowledge": knowledge_context_max_tokens,
            "supporting_knowledge": max(512, int(knowledge_context_max_tokens * 0.5)),
        },
    )
    payload = result.to_dict()
    payload["compiled_prompt"] = result.compiled_prompt
    return payload


def _prompt_budget_error_message(prompt_budget: dict[str, Any]) -> str:
    overflow_tokens = int(prompt_budget.get("overflow_tokens") or 0)
    gate_reason = str(prompt_budget.get("gate_reason") or "compiled_overflow").strip()
    final_segment_order = list(prompt_budget.get("final_segment_order") or [])
    tail = ", ".join(str(item) for item in final_segment_order[-3:] if str(item).strip())
    suffix = f" Final segments kept: {tail}." if tail else ""
    if gate_reason == "hard_floor_overflow":
        return (
            "System prompt exceeds the configured token budget before any discretionary context can be trimmed. "
            f"Overflow={overflow_tokens} tokens.{suffix}"
        )
    return (
        f"System prompt exceeds the configured token budget for this turn. Overflow={overflow_tokens} tokens.{suffix}"
    )


async def _record_procedural_memory(
    *,
    query_text: str,
    user_id: int,
    task_id: int | None,
    source_episode_id: int | None,
    status: str,
    ctx: QueryContext | None,
    run_result: RunResult | None,
    error_message: str | None,
) -> None:
    """Persist a best-effort procedural memory from the task outcome."""
    if ctx is None or run_result is None or ctx.dry_run:
        return
    try:
        from koda.memory import get_memory_manager

        mm = get_memory_manager()
        await mm.record_execution_pattern(
            query=query_text,
            user_id=user_id,
            task_id=task_id,
            source_episode_id=source_episode_id,
            status=status,
            confidence_score=_latest_confidence_score(ctx),
            error_message=error_message,
            tool_uses=run_result.tool_uses,
            tool_execution_trace=run_result.tool_execution_trace,
            knowledge_hits=_serialize_knowledge_hits(ctx.knowledge_hits),
            work_dir=ctx.work_dir,
            model=run_result.model,
            task_kind=ctx.task_kind,
            verified_before_finalize=ctx.verified_before_finalize,
            ungrounded_operationally=ctx.ungrounded_operationally,
            action_plan=ctx.last_action_plan,
            project_key=getattr(ctx.knowledge_query_context, "project_key", ""),
            environment=getattr(ctx.knowledge_query_context, "environment", ""),
            team=getattr(ctx.knowledge_query_context, "team", ""),
        )
    except Exception:
        log.exception("procedural_memory_record_error")


async def _record_execution_episode(
    *,
    user_id: int,
    task_id: int | None,
    status: str,
    ctx: QueryContext | None,
    run_result: RunResult | None,
    human_override_delta: int = 0,
) -> None:
    """Persist execution episodes and scoped reliability counters."""
    service = _get_execution_episode_service()
    await service.record_execution_episode(
        user_id=user_id,
        task_id=task_id,
        status=status,
        ctx=ctx,
        run_result=run_result,
        confidence_score=float(_latest_confidence_score(ctx) or 0.0) if ctx is not None else 0.0,
        source_refs=_serialize_knowledge_hits(ctx.knowledge_hits) if ctx is not None else [],
        human_override_delta=human_override_delta,
    )


# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

active_processes: dict[int, Any] = {}  # task_id -> local subprocess or runtime-kernel proxy
_user_queues: dict[int, asyncio.Queue] = {}
_queue_workers: dict[int, asyncio.Task] = {}
_worker_locks: dict[int, asyncio.Lock] = {}
_active_chat_ids: dict[int, set[int]] = {}  # user_id -> set of active chat_ids
agent_start_time = time.time()
_shutting_down = False

_user_tasks: dict[int, dict[int, TaskInfo]] = {}  # user_id -> {task_id -> TaskInfo}
_user_semaphores: dict[int, asyncio.Semaphore] = {}
_global_semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS_GLOBAL)
_standard_task_semaphore = asyncio.Semaphore(MAX_STANDARD_TASKS_GLOBAL)
_heavy_task_semaphore = asyncio.Semaphore(MAX_HEAVY_TASKS_GLOBAL)
_browser_task_semaphore = asyncio.Semaphore(MAX_BROWSER_TASKS_GLOBAL)
_agent_id_label = AGENT_ID or "default"
_cancelled_task_ids: set[int] = set()


async def _cancel_pending_task(task: asyncio.Task[Any] | None) -> None:
    """Cancel and drain a best-effort background task if it is still pending."""
    if task is None or task.done():
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await task


def _get_user_semaphore(user_id: int) -> asyncio.Semaphore:
    """Get or create the concurrency semaphore for a user."""
    if user_id not in _user_semaphores:
        _user_semaphores[user_id] = asyncio.Semaphore(MAX_CONCURRENT_TASKS_PER_USER)
    return _user_semaphores[user_id]


def _register_task(task_info: TaskInfo) -> None:
    """Register a task in the active tasks registry."""
    if task_info.user_id not in _user_tasks:
        _user_tasks[task_info.user_id] = {}
    _user_tasks[task_info.user_id][task_info.task_id] = task_info


def _unregister_task(task_info: TaskInfo) -> None:
    """Remove a task from the active registry."""
    user_tasks = _user_tasks.get(task_info.user_id, {})
    user_tasks.pop(task_info.task_id, None)
    if not user_tasks:
        _user_tasks.pop(task_info.user_id, None)


def get_active_tasks(user_id: int) -> list[TaskInfo]:
    """Get all active (in-memory) tasks for a user."""
    return list(_user_tasks.get(user_id, {}).values())


def get_total_active_task_count() -> int:
    """Total number of active tasks across all users."""
    return sum(len(tasks) for tasks in _user_tasks.values())


def get_task_info(task_id: int) -> TaskInfo | None:
    """Look up an active task by ID across all users."""
    for user_tasks in _user_tasks.values():
        if task_id in user_tasks:
            return user_tasks[task_id]
    return None


async def cancel_active_task_execution(task_id: int, *, reason: str = "Cancelled by scheduler control.") -> bool:
    """Cancel an active task and terminate its provider process when possible."""
    from koda.utils.process_control import terminate_process_tree

    task_info = get_task_info(task_id)
    proc = active_processes.get(task_id)
    cancelled = False
    if proc is not None:
        with contextlib.suppress(Exception):
            await terminate_process_tree(proc)
        cancelled = True
    if task_info and task_info.asyncio_task and not task_info.asyncio_task.done():
        task_info.error_message = reason
        task_info.asyncio_task.cancel()
        cancelled = True
    return cancelled


def _get_worker_lock(user_id: int) -> asyncio.Lock:
    """Get or create a lock for worker spawn coordination."""
    if user_id not in _worker_locks:
        _worker_locks[user_id] = asyncio.Lock()
    return _worker_locks[user_id]


def get_queue(user_id: int) -> asyncio.Queue:
    """Get or create the queue for a user."""
    if user_id not in _user_queues:
        _user_queues[user_id] = asyncio.Queue()
    return _user_queues[user_id]


def _extract_task_id_from_raw_item(raw_item: Any) -> int | None:
    if isinstance(raw_item, dict):
        value = raw_item.get("_task_id")
        if isinstance(value, int):
            return value
    if isinstance(raw_item, tuple) and len(raw_item) >= 4:
        candidate = raw_item[-1]
        if isinstance(candidate, int):
            return candidate
    return None


async def _ensure_queue_worker(user_id: int, context: BotContext) -> None:
    lock = _get_worker_lock(user_id)
    async with lock:
        if user_id not in _queue_workers or _queue_workers[user_id].done():
            _queue_workers[user_id] = asyncio.create_task(_process_queue(user_id, context))


async def cancel_queued_task(task_id: int) -> bool:
    """Mark a queued task as cancelled so the worker discards it on dequeue."""
    _cancelled_task_ids.add(task_id)
    from koda.services import metrics

    metrics.QUEUE_DEPTH.labels(agent_id=_agent_id_label).set(sum(queue.qsize() for queue in _user_queues.values()))
    return True


async def enqueue_runtime_retry_task(
    *,
    application: Any,
    user_id: int,
    task_id: int,
    chat_id: int,
    query_text: str,
    provider: str | None,
    model: str | None,
    work_dir: str | None,
    session_id: str | None,
    env_id: int,
    classification: str,
    environment_kind: str,
    checkpoint_id: int,
) -> None:
    """Enqueue a retry task that already has a restored runtime environment."""
    context = build_runtime_context(application, user_id)
    raw_item = {
        "_runtime_retry": True,
        "_runtime_preprovisioned": True,
        "_task_id": task_id,
        "chat_id": chat_id,
        "query_text": query_text,
        "provider": provider,
        "model": model,
        "work_dir": work_dir,
        "session_id": session_id,
        "runtime_env_id": env_id,
        "classification": classification,
        "environment_kind": environment_kind,
        "checkpoint_id": checkpoint_id,
    }
    queue = get_queue(user_id)
    await queue.put(raw_item)
    from koda.services import audit, metrics

    metrics.QUEUE_DEPTH.labels(agent_id=_agent_id_label).set(sum(item.qsize() for item in _user_queues.values()))
    audit.emit_task_lifecycle("task.queued", user_id=user_id, task_id=task_id)
    await _ensure_queue_worker(user_id, context)


async def enqueue_dashboard_chat_task(
    *,
    application: Any,
    user_id: int,
    chat_id: int,
    query_text: str,
    provider: str | None,
    model: str | None,
    work_dir: str | None,
    session_id: str,
    bot_override: Any | None = None,
) -> int:
    """Enqueue a silent dashboard-originated chat turn."""
    if _shutting_down:
        raise RuntimeError("Agent runtime is shutting down.")

    from koda.services import audit, metrics
    from koda.services.runtime import get_runtime_controller

    task_id = create_task(
        user_id=user_id,
        chat_id=chat_id,
        query_text=query_text,
        provider=provider,
        model=model,
        session_id=session_id,
        work_dir=work_dir,
        max_attempts=TASK_MAX_RETRY_ATTEMPTS,
        source_action="dashboard_chat",
    )
    audit.emit_task_lifecycle("task.created", user_id=user_id, task_id=task_id)
    if RUNTIME_ENVIRONMENTS_ENABLED:
        await get_runtime_controller().register_queued_task(
            task_id=task_id,
            user_id=user_id,
            chat_id=chat_id,
            query_text=query_text,
        )
    context = build_runtime_context(application, user_id, bot_override=bot_override)
    raw_item = {
        "_dashboard_chat": True,
        "_task_id": task_id,
        "chat_id": chat_id,
        "query_text": query_text,
        "provider": provider,
        "model": model,
        "work_dir": work_dir,
        "session_id": session_id,
    }
    queue = get_queue(user_id)
    await queue.put(raw_item)
    metrics.QUEUE_DEPTH.labels(agent_id=_agent_id_label).set(sum(item.qsize() for item in _user_queues.values()))
    audit.emit_task_lifecycle("task.queued", user_id=user_id, task_id=task_id)
    await _ensure_queue_worker(user_id, context)
    return task_id


def get_queue_depth(user_id: int) -> int:
    """Get queue depth for a user."""
    queue = _user_queues.get(user_id)
    return queue.qsize() if queue else 0


def is_process_running(user_id: int) -> bool:
    """Check if any process is running for a user (checks active tasks)."""
    user_tasks = _user_tasks.get(user_id, {})
    return any(task_info.status == "running" for task_info in user_tasks.values())


def _validate_work_dir(work_dir: str | None, *, strict: bool = False) -> str:
    """Validate a work_dir, optionally failing closed for scheduled execution."""
    validation = validate_work_dir(work_dir, fallback_to_default=not strict)
    if validation.ok:
        if validation.reason:
            log.warning("work_dir_normalized", work_dir=validation.path, reason=validation.reason)
        return validation.path
    if strict:
        raise ValueError(validation.reason or "Blocked: invalid work directory.")
    log.warning("work_dir_missing", work_dir=work_dir, fallback=DEFAULT_WORK_DIR)
    return DEFAULT_WORK_DIR


# ---------------------------------------------------------------------------
# Queue item parsing and context preparation
# ---------------------------------------------------------------------------


def _parse_queue_item(item: Any) -> QueueItem:
    """Parse a raw queue item into a structured QueueItem."""
    if isinstance(item, dict) and item.get("_dashboard_chat"):
        return QueueItem(
            chat_id=item["chat_id"],
            query_text=item["query_text"],
            scheduled_provider=item.get("provider"),
            scheduled_model=item.get("model"),
            scheduled_work_dir=item.get("work_dir"),
            is_dashboard_chat=True,
            override_session_id=item.get("session_id"),
        )
    if isinstance(item, dict) and item.get("_runtime_retry"):
        return QueueItem(
            chat_id=item["chat_id"],
            query_text=item["query_text"],
            scheduled_provider=item.get("provider"),
            scheduled_model=item.get("model"),
            scheduled_work_dir=item.get("work_dir"),
            scheduled_session_id=item.get("session_id"),
        )
    if isinstance(item, dict) and item.get("_scheduled_run"):
        return QueueItem(
            chat_id=item["chat_id"],
            query_text=item["query_text"],
            is_scheduled_run=True,
            scheduled_job_id=item.get("scheduled_job_id"),
            scheduled_run_id=item.get("scheduled_run_id"),
            scheduled_dry_run=bool(item.get("dry_run")),
            scheduled_provider=item.get("provider"),
            scheduled_model=item.get("model"),
            scheduled_work_dir=item.get("work_dir"),
            scheduled_session_id=item.get("session_id"),
            scheduled_trigger_reason=item.get("trigger_reason"),
        )
    if isinstance(item, dict) and item.get("_continuation"):
        return QueueItem(
            chat_id=item["chat_id"],
            query_text="Continue from where you left off.",
            is_continuation=True,
            continuation_session_id=item["session_id"],
            continuation_provider=item.get("provider"),
        )
    if isinstance(item, dict) and item.get("_link_analysis"):
        return QueueItem(
            chat_id=item["chat_id"],
            query_text=item["query_text"],
            is_link_analysis=True,
        )
    # Handle 5-tuple from enqueue (update, query_text, image_paths, artifact_bundle, task_id)
    if isinstance(item, tuple) and len(item) == 5:
        update, query_text, image_paths, artifact_bundle, _task_id = item
        return QueueItem(
            chat_id=update.effective_chat.id,
            query_text=query_text,
            update=update,
            image_paths=image_paths,
            artifact_bundle=artifact_bundle,
        )
    # Handle 4-tuple legacy enqueue payloads
    if isinstance(item, tuple) and len(item) == 4:
        update, query_text, image_paths, _task_id = item
        return QueueItem(
            chat_id=update.effective_chat.id,
            query_text=query_text,
            update=update,
            image_paths=image_paths,
        )
    if len(item) == 3:
        update, query_text, image_paths = item
        return QueueItem(
            chat_id=update.effective_chat.id,
            query_text=query_text,
            update=update,
            image_paths=image_paths,
        )
    update, query_text = item
    return QueueItem(
        chat_id=update.effective_chat.id,
        query_text=query_text,
        update=update,
    )


def _filter_visual_paths(paths: list[str] | None) -> list[str]:
    """Keep only real image-like paths for provider visual attachments."""
    if not paths:
        return []
    from koda.services.artifact_ingestion import ArtifactKind, detect_artifact_kind

    visual_paths: list[str] = []
    for raw_path in paths:
        if not raw_path:
            continue
        kind = detect_artifact_kind(path=raw_path)
        if kind == ArtifactKind.IMAGE and raw_path not in visual_paths:
            visual_paths.append(raw_path)
    return visual_paths


async def _runtime_heartbeat_loop(task_id: int, env_id: int | None, phase_getter: Callable[[], str]) -> None:
    """Emit periodic heartbeats for long-running runtime environments."""
    if not RUNTIME_ENVIRONMENTS_ENABLED:
        return
    from koda.services.runtime import get_runtime_controller

    controller = get_runtime_controller()
    while True:
        await asyncio.sleep(RUNTIME_HEARTBEAT_INTERVAL_SECONDS)
        await controller.heartbeat(task_id=task_id, env_id=env_id, phase=phase_getter())


async def _prepare_query_context(
    context: BotContext,
    item: QueueItem,
    user_id: int,
    task_id: int | None = None,
) -> QueryContext:
    """Build system prompt, check budget, resolve model and session.

    Raises BudgetExceeded if budget is exceeded.
    """
    from koda.utils.command_helpers import init_user_data

    init_user_data(context.user_data, user_id=user_id)
    from koda.knowledge import classify_task_kind, default_execution_policy

    # Budget check
    if context.user_data["total_cost"] >= MAX_TOTAL_BUDGET_USD:
        raise BudgetExceeded(f"Cumulative budget of ${MAX_TOTAL_BUDGET_USD:.2f} reached. Use /resetcost to reset.")

    work_dir = _validate_work_dir(
        item.runtime_work_dir or item.scheduled_work_dir or context.user_data["work_dir"],
        strict=item.is_scheduled_run,
    )
    context.user_data["work_dir"] = work_dir
    task_kind = classify_task_kind(item.query_text)
    project_key = Path(work_dir).name.lower()
    environment = str(context.user_data.get("postgres_env") or "")
    team = (AGENT_ID or "").lower()
    preferred_provider = normalize_provider(context.user_data.get("provider"))
    provider = item.scheduled_provider or item.continuation_provider or preferred_provider or DEFAULT_PROVIDER
    session_id = ensure_canonical_session_id(context.user_data)
    recall_session_id = (
        item.continuation_session_id or item.scheduled_session_id or item.override_session_id or session_id
    )
    model = get_provider_model(context.user_data, provider)
    provider_session_id = None

    prompt_segments: list[PromptSegment] = []

    # System prompt
    user_system_prompt = context.user_data.get("system_prompt")
    system_prompt = DEFAULT_SYSTEM_PROMPT
    _append_prompt_segment(
        prompt_segments,
        segment_id="immutable_base_policy",
        text=DEFAULT_SYSTEM_PROMPT,
        category="base",
        priority=0,
        compression_strategy="truncate_tail",
        drop_policy="hard_floor",
        metadata={"source": "default_system_prompt"},
    )
    if user_system_prompt:
        _append_prompt_segment(
            prompt_segments,
            segment_id="operator_instructions",
            text="## User Instructions\n" + str(user_system_prompt),
            category="identity",
            priority=5,
            compression_strategy="truncate_tail",
            drop_policy="hard_floor",
        )

    if item.is_scheduled_run and item.scheduled_dry_run:
        _append_prompt_segment(
            prompt_segments,
            segment_id="scheduled_dry_run_rules",
            text=(
                "## Scheduled Dry-Run Mode\n"
                "This execution validates a scheduled job in dry-run mode. "
                "Do not perform irreversible actions. Prefer previews, simulations, and read-only verification. "
                "If a write-capable tool has no safe dry-run path, explain that it was blocked."
            ),
            category="runtime_rules",
            priority=10,
            compression_strategy="truncate_tail",
            drop_policy="hard_floor",
        )

    # Voice instructions
    if context.user_data.get("audio_response") and TTS_ENABLED:
        _append_prompt_segment(
            prompt_segments,
            segment_id="voice_prompt",
            text=VOICE_ACTIVE_PROMPT,
            category="runtime_rules",
            priority=20,
            compression_strategy="head_and_tail",
            drop_policy="drop",
        )

    # Launch memory recall + cache/script lookups concurrently
    memory_task = None
    knowledge_task = None
    cache_task = None
    script_task = None
    artifact_task = None
    jira_dossier_tasks: list[asyncio.Task] = []
    knowledge_waits_for_artifacts = item.artifact_bundle is not None
    knowledge_enabled = False
    base_policy = default_execution_policy(task_kind, environment=environment)
    knowledge_query_context = _get_query_context_service().build_knowledge_query_context(
        query=item.query_text,
        task_id=task_id,
        agent_id=AGENT_ID,
        user_id=user_id,
        workspace_dir=work_dir,
        workspace_fingerprint=_workspace_fingerprint(work_dir),
        project_key=project_key,
        task_kind=task_kind,
        environment=environment,
        team=team,
        autonomy_tier_target=base_policy.autonomy_tier,
        task_risk="high" if task_kind == "deploy" and environment.lower() in {"prod", "production"} else "medium",
        requires_write=task_kind in {"deploy", "code_change", "bugfix"},
        retrieval_strategy=context.user_data.get("knowledge_strategy"),
    )
    effective_policy = base_policy
    try:
        from koda.knowledge.config import KNOWLEDGE_ENABLED as _KNOWLEDGE_ENABLED

        knowledge_enabled = _KNOWLEDGE_ENABLED
    except Exception:
        log.exception("knowledge_config_setup_error")

    try:
        from koda.memory.config import MEMORY_ENABLED

        if MEMORY_ENABLED:
            from koda.memory import get_memory_manager

            mm = get_memory_manager()
            pre_query_callable = getattr(mm, "pre_query_details", None) or getattr(mm, "pre_query", None)
            if pre_query_callable is None:
                raise RuntimeError("memory manager has no pre_query callable")
            pre_query_result = pre_query_callable(
                item.query_text,
                user_id,
                include_procedural=True,
                session_id=recall_session_id,
                project_key=project_key,
                environment=environment,
                team=team,
                task_id=task_id,
                source_query_id=context.user_data.get("last_query_id"),
                source_task_id=task_id,
                source_episode_id=context.user_data.get("last_execution_episode_id"),
            )
            if not inspect.isawaitable(pre_query_result):
                fallback_callable = getattr(mm, "pre_query", None)
                if fallback_callable is None or fallback_callable is pre_query_callable:
                    raise TypeError("memory pre_query callable must be awaitable")
                pre_query_result = fallback_callable(
                    item.query_text,
                    user_id,
                    include_procedural=True,
                    session_id=recall_session_id,
                    project_key=project_key,
                    environment=environment,
                    team=team,
                    task_id=task_id,
                    source_query_id=context.user_data.get("last_query_id"),
                    source_task_id=task_id,
                    source_episode_id=context.user_data.get("last_execution_episode_id"),
                )
            memory_task = asyncio.create_task(pre_query_result)
    except Exception:
        log.exception("memory_recall_setup_error")

    try:
        if knowledge_enabled:
            from koda.knowledge import get_knowledge_manager

            km = get_knowledge_manager()
            if km.initialized and not knowledge_waits_for_artifacts:
                knowledge_task = asyncio.create_task(km.resolve(knowledge_query_context))
    except Exception:
        log.exception("knowledge_recall_setup_error")

    try:
        from koda.services.cache_config import CACHE_ENABLED

        if CACHE_ENABLED:
            from koda.services.cache_manager import get_cache_manager

            cm = get_cache_manager()
            if cm._initialized:
                cache_task = asyncio.create_task(
                    cm.lookup(
                        item.query_text,
                        user_id,
                        work_dir=work_dir,
                        source_scope=tuple(knowledge_query_context.allowed_source_labels or ()),
                        strategy_version=str(
                            getattr(context.user_data.get("knowledge_strategy"), "value", "")
                            or context.user_data.get("knowledge_strategy")
                            or ""
                        ),
                        model_family=provider,
                    )
                )
    except Exception:
        log.exception("cache_lookup_setup_error")

    try:
        from koda.services.cache_config import SCRIPT_LIBRARY_ENABLED

        if SCRIPT_LIBRARY_ENABLED and not item.is_continuation:
            from koda.services.script_manager import get_script_manager

            sm = get_script_manager()
            if sm._initialized:
                script_task = asyncio.create_task(sm.search(item.query_text, user_id))
    except Exception:
        log.exception("script_lookup_setup_error")

    try:
        if item.artifact_bundle is not None:
            from koda.services.artifact_ingestion import extract_bundle

            artifact_task = asyncio.create_task(extract_bundle(item.artifact_bundle))
    except Exception:
        log.exception("artifact_bundle_setup_error")

    try:
        if JIRA_ENABLED and JIRA_DEEP_CONTEXT_ENABLED:
            from koda.services.atlassian_client import get_jira_service
            from koda.services.jira_issue_context import extract_issue_keys

            issue_keys = extract_issue_keys(item.query_text)[:JIRA_DEEP_CONTEXT_MAX_ISSUES]
            if issue_keys:
                knowledge_waits_for_artifacts = True
                jira_service = get_jira_service()
                jira_dossier_tasks = [
                    asyncio.create_task(jira_service.build_issue_dossier(issue_key, query=item.query_text))
                    for issue_key in issue_keys
                ]
    except Exception:
        log.exception("jira_dossier_setup_error")

    # Override session_id for continuations
    if item.is_continuation and item.continuation_session_id:
        session_id = item.continuation_session_id
        context.user_data["session_id"] = session_id
        if item.continuation_provider:
            provider = normalize_provider(item.continuation_provider)
    elif item.is_scheduled_run and item.scheduled_session_id:
        session_id = item.scheduled_session_id
    elif item.override_session_id:
        session_id = item.override_session_id
        context.user_data["session_id"] = session_id

    agent_mode = context.user_data.get("agent_mode", "autonomous")
    permission_mode = "plan" if item.is_scheduled_run and item.scheduled_dry_run else "bypassPermissions"
    max_turns = 1 if agent_mode == "supervised" else MAX_TURNS
    _query_warnings: list[str] = []
    visual_paths = _filter_visual_paths(item.image_paths)
    artifact_dossiers: list[Any] = []
    asset_refs: list[dict[str, Any]] = []
    temp_paths: list[str] = list(dict.fromkeys(item.image_paths or []))

    # Auto-model routing
    if context.user_data.get("auto_model"):
        model = resolve_provider_model(
            provider,
            query=item.query_text,
            auto_model=True,
            has_images=bool(visual_paths),
        )
        log.info("auto_model_selected", provider=provider, model=model)
    else:
        model = resolve_provider_model(
            provider,
            preferred_model=item.scheduled_model or model,
            query=item.query_text,
            has_images=bool(visual_paths),
        )

    if item.is_scheduled_run and item.scheduled_dry_run:
        provider_session_id = None
        _query_warnings.append("dry-run forced fresh provider turn")
    else:
        mapping = get_provider_session_mapping(session_id, provider)
        if mapping:
            provider_session_id, mapped_model = mapping
            context.user_data.setdefault("provider_sessions", {})[provider] = provider_session_id
            if (
                not context.user_data.get("auto_model")
                and mapped_model
                and mapped_model in PROVIDER_MODELS.get(provider, [])
            ):
                model = resolve_provider_model(provider, preferred_model=mapped_model, query=item.query_text)

    # Save last_query for /retry
    context.user_data["last_query"] = {
        "text": item.query_text,
        "image_paths": item.image_paths,
        "artifact_bundle": item.artifact_bundle,
    }
    if not item.scheduled_dry_run and not item.is_dashboard_chat:
        save_session(
            user_id,
            session_id,
            provider=provider,
            provider_session_id=provider_session_id,
            model=model,
        )

    # Collect memory result with timeout (ran concurrently with setup above)
    from koda.services import metrics as _metrics

    memory_context = ""
    memory_resolution = None
    if memory_task:
        _recall_start = time.time()
        try:
            from koda.memory.config import MEMORY_RECALL_TIMEOUT

            memory_result = await asyncio.wait_for(memory_task, timeout=MEMORY_RECALL_TIMEOUT)
            if isinstance(memory_result, tuple) and len(memory_result) == 2:
                memory_context, memory_resolution = memory_result
            elif isinstance(memory_result, str):
                memory_context = memory_result
            if memory_context:
                _append_prompt_segment(
                    prompt_segments,
                    segment_id="memory_context",
                    text=memory_context,
                    category="memory",
                    priority=40,
                    compression_strategy="head_and_tail",
                    drop_policy="drop",
                )
        except TimeoutError:
            log.warning("memory_recall_timeout")
            await _cancel_pending_task(memory_task)
            _query_warnings.append("memory timeout")
        except Exception:
            log.exception("memory_recall_error")
            _query_warnings.append("memory unavailable")
        _metrics.MEMORY_RECALL_DURATION.labels(agent_id=_agent_id_label).observe(time.time() - _recall_start)
        if memory_context and "## Memória Procedural" in memory_context:
            _metrics.PROCEDURAL_HITS.labels(agent_id=_agent_id_label).inc()
        else:
            _metrics.PROCEDURAL_MISSES.labels(agent_id=_agent_id_label).inc()

    knowledge_hits: list[Any] = []
    knowledge_resolution: Any | None = None
    stale_sources_present = False

    scoped_runbooks: list[dict[str, Any]] = []
    try:
        scoped_runbooks = list_approved_runbooks(
            agent_id=AGENT_ID,
            task_kind=task_kind,
            project_key=project_key or None,
            environment=environment or None,
            team=team or None,
            limit=10,
        )
    except Exception:
        log.exception("approved_runbook_lookup_error")
    reliability_stats = {
        "total_runs": 0,
        "successful_runs": 0,
        "verified_runs": 0,
        "human_override_count": 0,
        "correction_count": 0,
        "rollback_count": 0,
        "updated_at": None,
    }
    try:
        reliability_stats = get_execution_reliability_stats(
            agent_id=AGENT_ID,
            task_kind=task_kind,
            project_key=project_key,
            environment=environment,
        )
    except Exception:
        log.exception("execution_reliability_lookup_error")
    # Collect cache/script results
    _cache_hit = None
    _script_matches: list = []

    if cache_task:
        try:
            from koda.services.cache_config import CACHE_LOOKUP_TIMEOUT

            _cache_hit = await asyncio.wait_for(cache_task, timeout=CACHE_LOOKUP_TIMEOUT)
            if _cache_hit:
                _metrics.CACHE_HITS.labels(agent_id=_agent_id_label).inc()
            else:
                _metrics.CACHE_MISSES.labels(agent_id=_agent_id_label).inc()
        except TimeoutError:
            log.warning("cache_lookup_timeout")
            await _cancel_pending_task(cache_task)
            _query_warnings.append("cache timeout")
        except Exception:
            log.exception("cache_lookup_error")

    if script_task:
        try:
            from koda.services.cache_config import SCRIPT_LOOKUP_TIMEOUT

            _script_matches = await asyncio.wait_for(script_task, timeout=SCRIPT_LOOKUP_TIMEOUT)
        except TimeoutError:
            log.warning("script_lookup_timeout")
            await _cancel_pending_task(script_task)
            _query_warnings.append("script timeout")
        except Exception:
            log.exception("script_lookup_error")

    if artifact_task:
        try:
            artifact_dossier = await asyncio.wait_for(artifact_task, timeout=ARTIFACT_EXTRACTION_TIMEOUT)
            artifact_dossiers.append(artifact_dossier)
            _append_prompt_segment(
                prompt_segments,
                segment_id="artifact_context",
                text=artifact_dossier.to_prompt_context(item.query_text),
                category="supporting_knowledge",
                priority=70,
                compression_strategy="head_and_tail",
                drop_policy="drop",
            )
            for path in artifact_dossier.visual_paths:
                if path not in visual_paths:
                    visual_paths.append(path)
            for artifact in artifact_dossier.artifacts:
                if artifact.ref.path and artifact.ref.path not in temp_paths:
                    temp_paths.append(artifact.ref.path)
                for path in artifact.visual_paths:
                    if path not in temp_paths:
                        temp_paths.append(path)
        except TimeoutError:
            log.warning("artifact_bundle_timeout")
            await _cancel_pending_task(artifact_task)
            _query_warnings.append("artifact extraction timeout")
        except Exception:
            log.exception("artifact_bundle_error")
            _query_warnings.append("artifact extraction unavailable")

    if jira_dossier_tasks:
        try:
            jira_results = await asyncio.wait_for(
                asyncio.gather(*jira_dossier_tasks), timeout=ARTIFACT_EXTRACTION_TIMEOUT
            )
            jira_context_blocks: list[str] = []
            for result in jira_results:
                artifact_dossiers.append(result.dossier)
                jira_context_blocks.append(result.dossier.to_prompt_context(item.query_text))
                for path in result.dossier.visual_paths:
                    if path not in visual_paths:
                        visual_paths.append(path)
                for artifact in result.dossier.artifacts:
                    if artifact.ref.path and artifact.ref.path not in temp_paths:
                        temp_paths.append(artifact.ref.path)
                    for path in artifact.visual_paths:
                        if path not in temp_paths:
                            temp_paths.append(path)
            if jira_context_blocks:
                _append_prompt_segment(
                    prompt_segments,
                    segment_id="jira_artifact_context",
                    text="\n\n".join(jira_context_blocks),
                    category="supporting_knowledge",
                    priority=72,
                    compression_strategy="head_and_tail",
                    drop_policy="drop",
                )
        except TimeoutError:
            log.warning("jira_dossier_timeout")
            for task in jira_dossier_tasks:
                await _cancel_pending_task(task)
            _query_warnings.append("jira dossier timeout")
        except Exception:
            log.exception("jira_dossier_error")
            _query_warnings.append("jira dossier unavailable")

    # Inject cache hint or relevant scripts into system prompt
    if _cache_hit and hasattr(_cache_hit, "match_type") and _cache_hit.match_type == "fuzzy_suggest":
        hint = _cache_hit.response[:3000]
        _append_prompt_segment(
            prompt_segments,
            segment_id="cache_hint",
            text=(
                "<cached_response_hint>\n"
                "A similar question was asked before. Here is the previous response as reference — "
                "adapt it if appropriate, but verify accuracy:\n\n"
                f"{hint}\n</cached_response_hint>"
            ),
            category="cache_hints",
            priority=90,
            compression_strategy="truncate_tail",
            drop_policy="drop",
        )

    if _script_matches:
        scripts_text = ""
        total_chars = 0
        for sm_result in _script_matches[:3]:
            snippet = sm_result.content[:1200]
            if total_chars + len(snippet) > 4000:
                break
            lang = sm_result.language or ""
            scripts_text += f"\n### {sm_result.title} ({lang})\n```{lang}\n{snippet}\n```\n"
            total_chars += len(snippet)
        if scripts_text:
            _append_prompt_segment(
                prompt_segments,
                segment_id="relevant_scripts",
                text=(
                    "<relevant_scripts>\n"
                    "The user has saved scripts that may be relevant. "
                    "Reuse or adapt them when appropriate:\n"
                    f"{scripts_text}\n</relevant_scripts>"
                ),
                category="scripts_assets",
                priority=80,
                compression_strategy="head_and_tail",
                drop_policy="drop",
            )

    # Agent tools prompt
    from koda.services.tool_prompt import build_agent_tools_prompt

    postgres_env = context.user_data.get("postgres_env")
    agent_tools_section = build_agent_tools_prompt(postgres_env=postgres_env)
    if agent_tools_section:
        _append_prompt_segment(
            prompt_segments,
            segment_id="tool_contracts",
            text=agent_tools_section,
            category="tool_contracts",
            priority=30,
            compression_strategy="truncate_tail",
            drop_policy="hard_floor",
        )

    # Skills awareness prompt
    from koda.services.templates import build_relevant_skills_awareness_prompt

    relevant_skills_prompt = build_relevant_skills_awareness_prompt(item.query_text)
    if relevant_skills_prompt:
        _append_prompt_segment(
            prompt_segments,
            segment_id="relevant_skills_awareness",
            text=relevant_skills_prompt,
            category="extras",
            priority=35,
            compression_strategy="truncate_tail",
            drop_policy="drop",
        )

    has_blocking_artifact_gap = any(dossier.has_blocking_gaps for dossier in artifact_dossiers)
    if has_blocking_artifact_gap:
        effective_policy = replace(effective_policy, approval_mode="read_only")
        permission_mode = "plan"
        _query_warnings.append("artifact dossier incomplete; writes blocked")
        ungrounded_operationally = True

    await _persist_artifact_evidence_nodes(knowledge_query_context, artifact_dossiers)

    try:
        from koda.services.agent_asset_registry import get_agent_asset_registry
        from koda.services.cache_config import SCRIPT_LOOKUP_TIMEOUT

        asset_refs = await asyncio.wait_for(
            get_agent_asset_registry(AGENT_ID).search(
                query=item.query_text,
                user_id=user_id,
                work_dir=work_dir,
                project_key=project_key,
                workspace_fingerprint=knowledge_query_context.workspace_fingerprint,
                source_scope=tuple(knowledge_query_context.allowed_source_labels or ()),
                task_id=task_id,
                limit=6,
                script_matches=_script_matches,
            ),
            timeout=SCRIPT_LOOKUP_TIMEOUT,
        )
        if asset_refs:
            asset_lines = []
            for ref in asset_refs[:5]:
                score = float(ref.get("score") or 0.0)
                asset_kind = str(ref.get("asset_kind") or "asset")
                title = str(ref.get("title") or ref.get("asset_key") or "asset")
                reason = str(ref.get("reuse_reason") or "contextual_match")
                path_hint = str(ref.get("source_path") or ref.get("source_url") or "").strip()
                suffix = f" [{path_hint}]" if path_hint else ""
                asset_lines.append(f"- [{asset_kind}] {title} (score={score:.2f}, reason={reason}){suffix}")
            _append_prompt_segment(
                prompt_segments,
                segment_id="asset_memory",
                text=(
                    "<asset_memory>\n"
                    "Previously stored agent assets may be reusable for this request.\n"
                    "Reuse them only when they are coherent with the current goal and context.\n\n"
                    + "\n".join(asset_lines)
                    + "\n</asset_memory>"
                ),
                category="scripts_assets",
                priority=75,
                compression_strategy="truncate_tail",
                drop_policy="drop",
            )
    except TimeoutError:
        _query_warnings.append("asset registry timeout")
    except Exception:
        log.exception("asset_registry_lookup_error")
        _query_warnings.append("asset registry unavailable")

    if knowledge_enabled and knowledge_task is None:
        try:
            from koda.knowledge import get_knowledge_manager

            km = get_knowledge_manager()
            if km.initialized:
                knowledge_task = asyncio.create_task(km.resolve(knowledge_query_context))
        except Exception:
            log.exception("knowledge_recall_setup_error")

    if knowledge_task:
        _knowledge_start = time.time()
        try:
            from koda.knowledge.config import KNOWLEDGE_RECALL_TIMEOUT

            knowledge_resolution = await asyncio.wait_for(knowledge_task, timeout=KNOWLEDGE_RECALL_TIMEOUT)
            knowledge_context = knowledge_resolution.context if knowledge_resolution else ""
            knowledge_hits = list(knowledge_resolution.hits) if knowledge_resolution else []
            if knowledge_context:
                _append_prompt_segment(
                    prompt_segments,
                    segment_id="authoritative_knowledge",
                    text=knowledge_context,
                    category="authoritative_knowledge",
                    priority=60,
                    compression_strategy="head_and_tail",
                    drop_policy="drop",
                )
                _metrics.KNOWLEDGE_HITS.labels(agent_id=_agent_id_label).inc()
            else:
                _metrics.KNOWLEDGE_MISSES.labels(agent_id=_agent_id_label).inc()
            if knowledge_resolution:
                strategy_label = getattr(
                    getattr(knowledge_resolution, "retrieval_strategy", None),
                    "value",
                    str(getattr(knowledge_resolution, "retrieval_strategy", "") or "unknown"),
                )
                route_label = str(getattr(knowledge_resolution, "retrieval_route", "") or "unknown")
                _metrics.KNOWLEDGE_STRATEGY_SELECTIONS.labels(
                    agent_id=_agent_id_label,
                    strategy=strategy_label,
                    route=route_label,
                ).inc()
                _metrics.KNOWLEDGE_GROUNDING_SCORE.labels(
                    agent_id=_agent_id_label,
                    strategy=strategy_label,
                ).observe(float(getattr(knowledge_resolution, "grounding_score", 0.0) or 0.0))
                if getattr(knowledge_resolution, "trace_id", None) is not None:
                    _metrics.KNOWLEDGE_TRACE_PERSISTED.labels(
                        agent_id=_agent_id_label,
                        strategy=strategy_label,
                    ).inc()
        except TimeoutError:
            log.warning("knowledge_recall_timeout")
            await _cancel_pending_task(knowledge_task)
            _query_warnings.append("knowledge timeout")
            _metrics.KNOWLEDGE_MISSES.labels(agent_id=_agent_id_label).inc()
        except Exception:
            log.exception("knowledge_recall_error")
            _query_warnings.append("knowledge unavailable")
            _metrics.KNOWLEDGE_MISSES.labels(agent_id=_agent_id_label).inc()
        _metrics.KNOWLEDGE_RECALL_DURATION.labels(agent_id=_agent_id_label).observe(time.time() - _knowledge_start)

    selected_policy_runbook = _select_policy_runbook(scoped_runbooks, knowledge_resolution)
    if selected_policy_runbook:
        effective_policy = _apply_policy_overrides(effective_policy, selected_policy_runbook)
    effective_policy = _downgrade_policy_from_reliability(
        effective_policy,
        reliability_stats,
    )
    ungrounded_operationally = bool(getattr(knowledge_resolution, "ungrounded_operationally", False))
    stale_sources_present = bool(getattr(knowledge_resolution, "stale_sources_present", False))

    from koda.knowledge.config import KNOWLEDGE_CONTEXT_MAX_TOKENS
    from koda.memory.config import MEMORY_MAX_CONTEXT_TOKENS

    prompt_budget = _compile_runtime_prompt_budget(
        provider=provider,
        model=model,
        segments=prompt_segments,
        memory_context_max_tokens=MEMORY_MAX_CONTEXT_TOKENS,
        knowledge_context_max_tokens=KNOWLEDGE_CONTEXT_MAX_TOKENS,
    )
    if not bool(prompt_budget.get("within_budget", False)):
        raise BudgetExceeded(_prompt_budget_error_message(prompt_budget))
    system_prompt = str(prompt_budget.get("compiled_prompt") or DEFAULT_SYSTEM_PROMPT)

    return QueryContext(
        task_id=task_id,
        provider=provider,
        work_dir=work_dir,
        model=model,
        session_id=session_id,
        provider_session_id=provider_session_id,
        system_prompt=system_prompt,
        agent_mode=agent_mode,
        permission_mode=permission_mode,
        max_turns=max_turns,
        warnings=_query_warnings,
        cache_hit=_cache_hit,
        script_matches=_script_matches,
        knowledge_hits=knowledge_hits,
        knowledge_resolution=knowledge_resolution,
        memory_resolution=memory_resolution,
        memory_profile=getattr(mm, "profile", None) if "mm" in locals() else None,
        memory_trust_score=float(getattr(memory_resolution, "trust_score", 0.0) or 0.0),
        task_kind=task_kind,
        knowledge_query_context=knowledge_query_context,
        effective_policy=effective_policy,
        ungrounded_operationally=ungrounded_operationally,
        stale_sources_present=stale_sources_present,
        turn_mode=cast(
            TurnMode,
            "new_turn" if item.is_scheduled_run and item.scheduled_dry_run else infer_turn_mode(provider_session_id),
        ),
        resume_requested=provider_session_id is not None and not (item.is_scheduled_run and item.scheduled_dry_run),
        dry_run=item.scheduled_dry_run,
        scheduled_job_id=item.scheduled_job_id,
        scheduled_run_id=item.scheduled_run_id,
        artifact_dossiers=artifact_dossiers,
        visual_paths=visual_paths,
        temp_paths=temp_paths,
        runtime_env_id=None,
        runtime_classification="light",
        runtime_environment_kind="dev_worktree",
        prompt_budget=prompt_budget,
        asset_refs=asset_refs,
    )


# ---------------------------------------------------------------------------
# Provider execution (streaming + fallback)
# ---------------------------------------------------------------------------


async def _run_streaming(
    ctx: QueryContext,
    item: QueueItem,
    user_id: int,
    chat_id: int,
    context: BotContext,
    task_id: int | None = None,
) -> RunResult | None:
    """Run the selected provider with streaming. Returns RunResult or None if streaming fails."""
    streaming_msg = None
    try:
        streaming_msg = await context.bot.send_message(chat_id=chat_id, text="Processing…")
    except Exception:
        log.warning(
            "streaming_progress_message_failed",
            chat_id=chat_id,
            task_id=task_id,
            exc_info=True,
        )

    process_ready = asyncio.Event()
    process_holder: dict = {"event": process_ready}
    proc_key = task_id if task_id is not None else user_id

    async def _track_process(
        _ev: asyncio.Event = process_ready,
        _ph: dict = process_holder,
    ) -> None:
        await _ev.wait()
        active_processes[proc_key] = _ph["proc"]
        if task_id is not None and RUNTIME_ENVIRONMENTS_ENABLED and ctx.runtime_env_id is not None:
            from koda.services.runtime import get_runtime_controller

            await get_runtime_controller().record_process(
                task_id=task_id,
                command=f"{ctx.provider}:{ctx.model}",
                proc=_ph["proc"],
                role="provider_stream",
            )

    track_task = asyncio.create_task(_track_process())
    typing_task = asyncio.create_task(_send_typing(chat_id, context))
    metadata_collector: dict = {}
    raw_output = ""
    runtime_terminal_id: int | None = None
    runtime_terminal_path: str | None = None

    try:
        from koda.services.runtime import get_runtime_controller
        from koda.utils.progress_tracker import ProgressTracker

        chunks: list[str] = []
        last_edit_time = 0.0
        stream_start = time.time()
        tracker = ProgressTracker(start_time=stream_start)
        if task_id is not None and RUNTIME_ENVIRONMENTS_ENABLED and ctx.runtime_env_id is not None:
            runtime = get_runtime_controller()
            runtime_terminal_path = "kernel-stream://stdout"
            runtime_terminal_id = await runtime.register_terminal(
                task_id=task_id,
                terminal_kind="provider_stream",
                label=f"{ctx.provider} stream",
                path=runtime_terminal_path,
                stream_path="kernel-stream://stdout",
            )
            metadata_collector["runtime_terminal_id"] = runtime_terminal_id
            metadata_collector["runtime_terminal_path"] = runtime_terminal_path

        async for chunk in run_llm_streaming(
            provider=ctx.provider,
            query=item.query_text,
            work_dir=ctx.work_dir,
            model=ctx.model,
            provider_session_id=ctx.provider_session_id,
            process_holder=process_holder,
            system_prompt=ctx.system_prompt,
            image_paths=ctx.visual_paths,
            permission_mode=ctx.permission_mode,
            max_turns=ctx.max_turns,
            metadata_collector=metadata_collector,
            turn_mode=cast(TurnMode, ctx.turn_mode),
            dry_run=ctx.dry_run,
            runtime_task_id=task_id if (RUNTIME_ENVIRONMENTS_ENABLED and ctx.runtime_env_id is not None) else None,
        ):
            chunks.append(chunk)
            raw_output += chunk
            if (
                task_id is not None
                and RUNTIME_ENVIRONMENTS_ENABLED
                and ctx.runtime_env_id is not None
                and runtime_terminal_id is not None
            ):
                await runtime.cooperate_pause(task_id=task_id, env_id=ctx.runtime_env_id, phase="executing")
            now = time.time()
            elapsed = now - stream_start
            # Adaptive throttle based on elapsed time
            if now - last_edit_time >= _get_throttle_interval(elapsed):
                tool_uses = metadata_collector.get("tool_uses", [])
                status_line = tracker.build_status(elapsed, tool_uses)
                full_text = "".join(chunks)
                max_preview = max(4000 - len(status_line) - 4, 0)
                if full_text and max_preview > 0:
                    if len(full_text) > max_preview:
                        preview = "…" + full_text[-max_preview:]
                    else:
                        preview = full_text
                    display = f"{status_line}\n\n{preview}"
                else:
                    display = status_line
                if streaming_msg is not None:
                    with contextlib.suppress(Exception):
                        await streaming_msg.edit_text(display)
                last_edit_time = now

                # Send milestone notifications for long tasks
                milestone = tracker.check_milestone(elapsed, tool_uses)
                if milestone:
                    with contextlib.suppress(Exception):
                        ms_msg = await context.bot.send_message(chat_id=chat_id, text=milestone)
                        tracker.add_milestone_message(ms_msg.message_id)

        typing_task.cancel()
        full_response = "".join(chunks)

        # Clean up milestone messages
        for ms_id in tracker.milestone_message_ids:
            with contextlib.suppress(Exception):
                await context.bot.delete_message(chat_id=chat_id, message_id=ms_id)

        if streaming_msg is not None:
            with contextlib.suppress(Exception):
                await streaming_msg.delete()

        error = bool(metadata_collector.get("error"))
        result_text = full_response or metadata_collector.get("error_message", "")
        if not result_text and not error and metadata_collector.get("stop_reason"):
            result_text = "Task completed (no text output)."
        return RunResult(
            provider=ctx.provider,
            model=ctx.model,
            result=result_text,
            session_id=ctx.session_id,
            provider_session_id=metadata_collector.get("session_id", ctx.provider_session_id),
            cost_usd=metadata_collector.get("cost_usd", 0.0),
            usage=metadata_collector.get("usage", {}),
            error=error,
            stop_reason=metadata_collector.get("stop_reason", ""),
            tool_uses=metadata_collector.get("tool_uses", []),
            native_items=metadata_collector.get("native_items", []),
            raw_output=raw_output,
            warnings=metadata_collector.get("warnings", []),
            turn_mode=cast(TurnMode, str(metadata_collector.get("turn_mode", ctx.turn_mode))),
            supports_native_resume=bool(metadata_collector.get("supports_native_resume", ctx.supports_native_resume)),
            error_kind=str(metadata_collector.get("error_kind", "")),
            retryable=bool(metadata_collector.get("retryable", False)),
            runtime_terminal_id=runtime_terminal_id,
            runtime_terminal_path=runtime_terminal_path,
        )

    except Exception:
        log.exception("streaming_error")
        if streaming_msg is not None:
            with contextlib.suppress(Exception):
                await streaming_msg.delete()
        return None

    finally:
        track_task.cancel()
        typing_task.cancel()
        active_processes.pop(proc_key, None)


async def _run_fallback(
    ctx: QueryContext,
    item: QueueItem,
    user_id: int,
    chat_id: int,
    context: BotContext,
    task_id: int | None = None,
) -> RunResult:
    """Run the selected provider without streaming (fallback with progress indicator)."""
    progress_task = asyncio.create_task(progress_indicator(chat_id, context))

    process_ready = asyncio.Event()
    process_holder: dict = {"event": process_ready}
    proc_key = task_id if task_id is not None else user_id

    async def _track_process(
        _ev: asyncio.Event = process_ready,
        _ph: dict = process_holder,
    ) -> None:
        await _ev.wait()
        active_processes[proc_key] = _ph["proc"]
        if task_id is not None and RUNTIME_ENVIRONMENTS_ENABLED and ctx.runtime_env_id is not None:
            from koda.services.runtime import get_runtime_controller

            await get_runtime_controller().record_process(
                task_id=task_id,
                command=f"{ctx.provider}:{ctx.model}",
                proc=_ph["proc"],
                role="provider",
            )

    track_task = asyncio.create_task(_track_process())
    try:
        result = await run_llm(
            provider=ctx.provider,
            query=item.query_text,
            work_dir=ctx.work_dir,
            model=ctx.model,
            provider_session_id=ctx.provider_session_id,
            process_holder=process_holder,
            system_prompt=ctx.system_prompt,
            image_paths=ctx.visual_paths,
            permission_mode=ctx.permission_mode,
            max_turns=ctx.max_turns,
            turn_mode=cast(TurnMode, ctx.turn_mode),
            dry_run=ctx.dry_run,
            runtime_task_id=task_id if (RUNTIME_ENVIRONMENTS_ENABLED and ctx.runtime_env_id is not None) else None,
        )
        return RunResult(
            provider=ctx.provider,
            model=ctx.model,
            result=result["result"],
            session_id=ctx.session_id,
            provider_session_id=result.get("provider_session_id") or result.get("session_id"),
            cost_usd=result.get("cost_usd", 0.0),
            usage=result.get("usage", {}),
            error=result.get("error", False),
            stop_reason=result.get("_stop_reason", ""),
            tool_uses=result.get("_tool_uses", []),
            native_items=result.get("_native_items", []),
            warnings=result.get("warnings", []),
            turn_mode=cast(TurnMode, str(result.get("turn_mode", ctx.turn_mode))),
            supports_native_resume=bool(result.get("supports_native_resume", ctx.supports_native_resume)),
            error_kind=str(result.get("error_kind", "")),
            retryable=bool(result.get("retryable", False)),
        )
    finally:
        track_task.cancel()
        active_processes.pop(proc_key, None)
        progress_task.cancel()
        try:
            progress_msg = await progress_task
            if progress_msg is not None:
                await progress_msg.delete()
        except Exception:
            pass


def _should_switch_provider(run_result: RunResult | None) -> bool:
    """Decide whether the current provider failed in a way that warrants provider fallback."""
    if run_result is None:
        return True
    if run_result.error:
        if run_result.error_kind in {"adapter_contract", "invalid_session", "provider_auth"}:
            return True
        if run_result.retryable:
            return True
        return is_retryable_provider_error(run_result.provider, run_result.result)
    return not run_result.result and not run_result.stop_reason


def _build_handoff_context(run_result: RunResult | None) -> str | None:
    """Build compact handoff context for bootstrap prompts during provider fallback."""
    if run_result is None:
        return None
    parts: list[str] = []
    if run_result.result:
        parts.append("Latest assistant output:\n" + run_result.result[:4000])
    if run_result.native_items:
        parts.append(
            "Native execution items:\n" + json.dumps(run_result.native_items[:8], ensure_ascii=False, default=str)
        )
    if run_result.tool_execution_trace:
        parts.append(
            "Executed agent tools:\n" + json.dumps(run_result.tool_execution_trace[:8], ensure_ascii=False, default=str)
        )
    return "\n\n".join(parts) if parts else None


def _clear_stale_provider_session(*, session_id: str | None, provider: str, context: BotContext) -> None:
    """Forget an invalid provider-native session from the runtime state."""
    context.user_data.setdefault("provider_sessions", {}).pop(provider, None)
    if session_id:
        delete_provider_session_mapping(session_id, provider)


async def _resolve_provider_context(
    *,
    base_ctx: QueryContext,
    provider: str,
    item: QueueItem,
    context: BotContext,
) -> QueryContext:
    """Resolve model/native session state for one provider attempt."""
    preferred_model = (
        base_ctx.model
        if provider == base_ctx.provider and base_ctx.model in PROVIDER_MODELS.get(provider, [])
        else get_provider_model(context.user_data, provider)
    )
    mapping = get_provider_session_mapping(base_ctx.session_id, provider)
    provider_session_id = None
    mapped_model = None
    if mapping:
        provider_session_id, mapped_model = mapping
    elif provider == base_ctx.provider and base_ctx.provider_session_id:
        provider_session_id = base_ctx.provider_session_id
    elif (
        provider == "claude"
        and base_ctx.session_id
        and provider == normalize_provider(context.user_data.get("provider"))
    ):
        provider_session_id = context.user_data.get("provider_sessions", {}).get(provider)
    if mapped_model:
        preferred_model = mapped_model

    resume_requested = provider_session_id is not None
    desired_turn_mode = infer_turn_mode(provider_session_id)
    capabilities = await get_provider_capabilities(provider, desired_turn_mode)
    effective_turn_mode = desired_turn_mode
    warning_messages = list(base_ctx.warnings)

    if resume_requested and not capabilities.can_execute:
        warning_prefix = capabilities.errors[0] if capabilities.errors else "native resume unavailable"
        warning_messages.append(f"resume degraded: {provider} ({warning_prefix})")
        effective_turn_mode = "new_turn"
        provider_session_id = None
        capabilities = await get_provider_capabilities(provider, effective_turn_mode)

    if not capabilities.can_execute:
        warning_prefix = capabilities.errors[0] if capabilities.errors else "provider unavailable"
        warning_messages.append(f"provider unavailable: {provider} ({warning_prefix})")

    model = resolve_provider_model(
        provider,
        preferred_model=preferred_model,
        query=item.query_text,
        auto_model=bool(context.user_data.get("auto_model")),
        has_images=bool(base_ctx.visual_paths or _filter_visual_paths(item.image_paths)),
    )
    return replace(
        base_ctx,
        provider=provider,
        model=model,
        provider_session_id=provider_session_id,
        warnings=warning_messages,
        turn_mode=effective_turn_mode,
        resume_requested=resume_requested,
        supports_native_resume=capabilities.supports_native_resume,
        provider_available=capabilities.can_execute,
    )


async def _run_with_provider_fallback(
    ctx: QueryContext,
    item: QueueItem,
    user_id: int,
    chat_id: int,
    context: BotContext,
    task_id: int | None = None,
) -> RunResult:
    """Run a task turn with transparent provider fallback."""
    from koda.services import audit, metrics

    attempted: list[str] = []
    handoff_context: str | None = None
    last_result: RunResult | None = None

    async def _execute_attempt(attempt_ctx: QueryContext, attempt_item: QueueItem) -> RunResult:
        run_result = await _run_streaming(attempt_ctx, attempt_item, user_id, chat_id, context, task_id=task_id)
        if run_result is None or (not run_result.result and not run_result.stop_reason):
            attempt_ctx.warnings.append("streaming fallback")
            run_result = await _run_fallback(attempt_ctx, attempt_item, user_id, chat_id, context, task_id=task_id)
            run_result.warnings.append("streaming fallback")

        for warning in attempt_ctx.warnings:
            if warning not in run_result.warnings:
                run_result.warnings.append(warning)
        run_result.turn_mode = attempt_ctx.turn_mode
        run_result.supports_native_resume = attempt_ctx.supports_native_resume
        return run_result

    def _build_bootstrap_item(
        *,
        from_provider: str,
        to_provider: str,
        extra_context: str | None,
    ) -> QueueItem:
        return replace(
            item,
            query_text=build_bootstrap_prompt(
                user_id=user_id,
                canonical_session_id=ctx.session_id,
                current_query=item.query_text,
                from_provider=from_provider,
                to_provider=to_provider,
                transcript_limit=TRANSCRIPT_REPLAY_LIMIT,
                extra_context=extra_context,
            ),
        )

    def _record_resume_degraded(provider: str, reason: str) -> None:
        metrics.PROVIDER_RESUME_DEGRADED_TOTAL.labels(agent_id=_agent_id_label, provider=provider).inc()
        audit.emit_task_lifecycle(
            "task.provider_resume_degraded",
            user_id=user_id,
            task_id=task_id,
            provider=provider,
            reason=reason,
        )

    for provider in get_provider_fallback_chain(ctx.provider):
        attempt_ctx = await _resolve_provider_context(base_ctx=ctx, provider=provider, item=item, context=context)
        if not attempt_ctx.provider_available:
            attempted.append(provider)
            last_result = RunResult(
                provider=provider,
                model=attempt_ctx.model,
                result=attempt_ctx.warnings[-1] if attempt_ctx.warnings else f"{provider} unavailable",
                session_id=ctx.session_id,
                provider_session_id=None,
                cost_usd=0.0,
                error=True,
                stop_reason="error",
                warnings=list(attempt_ctx.warnings),
                fallback_chain=attempted.copy(),
                turn_mode=attempt_ctx.turn_mode,
                supports_native_resume=attempt_ctx.supports_native_resume,
                error_kind="provider_runtime",
                retryable=False,
            )
            handoff_context = _build_handoff_context(last_result)
            continue

        attempt_item = item
        bootstrap_without_resume = attempt_ctx.resume_requested and attempt_ctx.turn_mode != "resume_turn"
        if bootstrap_without_resume:
            reason = attempt_ctx.warnings[-1] if attempt_ctx.warnings else "native resume unavailable"
            _record_resume_degraded(provider, reason)
            attempt_item = _build_bootstrap_item(
                from_provider=provider,
                to_provider=provider,
                extra_context=handoff_context,
            )
        elif provider != ctx.provider and not attempt_ctx.provider_session_id:
            attempt_item = _build_bootstrap_item(
                from_provider=attempted[-1] if attempted else ctx.provider,
                to_provider=provider,
                extra_context=handoff_context,
            )

        run_result = await _execute_attempt(attempt_ctx, attempt_item)

        attempted.append(provider)
        run_result.fallback_chain = attempted.copy()
        if provider != ctx.provider:
            run_result.warnings.append(f"provider fallback: {ctx.provider} -> {provider}")
        if run_result.error_kind == "invalid_session":
            _clear_stale_provider_session(session_id=ctx.session_id, provider=provider, context=context)
            run_result.provider_session_id = None
        if run_result.provider_session_id:
            save_provider_session_mapping(
                ctx.session_id,
                provider,
                run_result.provider_session_id,
                attempt_ctx.model,
            )
            context.user_data.setdefault("provider_sessions", {})[provider] = run_result.provider_session_id

        if run_result.error_kind in {"adapter_contract", "invalid_session"}:
            if run_result.error_kind == "adapter_contract":
                metrics.PROVIDER_ADAPTER_CONTRACT_ERRORS_TOTAL.labels(
                    agent_id=_agent_id_label,
                    provider=provider,
                    turn_mode=run_result.turn_mode,
                ).inc()
                audit_event = "task.provider_adapter_contract_error"
                degrade_reason_fallback = "adapter contract error"
            else:
                audit_event = "task.provider_invalid_session"
                degrade_reason_fallback = "invalid provider session"
            audit.emit_task_lifecycle(
                audit_event,
                user_id=user_id,
                task_id=task_id,
                provider=provider,
                turn_mode=run_result.turn_mode,
                error_message=run_result.result[:500],
            )
            if attempt_ctx.resume_requested and attempt_ctx.turn_mode == "resume_turn":
                degrade_reason = run_result.result.splitlines()[0][:200] or degrade_reason_fallback
                _record_resume_degraded(provider, degrade_reason)
                degraded_ctx = replace(
                    attempt_ctx,
                    provider_session_id=None,
                    turn_mode="new_turn",
                    supports_native_resume=False,
                    warnings=list(
                        dict.fromkeys([*attempt_ctx.warnings, f"resume degraded: {provider} ({degrade_reason})"])
                    ),
                )
                degraded_item = _build_bootstrap_item(
                    from_provider=provider,
                    to_provider=provider,
                    extra_context=_build_handoff_context(run_result) or run_result.result[:1000],
                )
                degraded_result = await _execute_attempt(degraded_ctx, degraded_item)
                degraded_result.fallback_chain = attempted.copy()
                if degraded_result.error_kind == "invalid_session":
                    _clear_stale_provider_session(session_id=ctx.session_id, provider=provider, context=context)
                    degraded_result.provider_session_id = None
                if degraded_result.provider_session_id:
                    save_provider_session_mapping(
                        ctx.session_id,
                        provider,
                        degraded_result.provider_session_id,
                        degraded_ctx.model,
                    )
                    context.user_data.setdefault("provider_sessions", {})[provider] = (
                        degraded_result.provider_session_id
                    )
                if not _should_switch_provider(degraded_result):
                    return degraded_result
                handoff_context = _build_handoff_context(degraded_result)
                last_result = degraded_result
                continue

        if not _should_switch_provider(run_result):
            return run_result

        handoff_context = _build_handoff_context(run_result)
        last_result = run_result

    if last_result is not None:
        return last_result
    return RunResult(
        provider=ctx.provider,
        model=ctx.model,
        result="All providers failed to execute the task.",
        session_id=ctx.session_id,
        provider_session_id=ctx.provider_session_id,
        cost_usd=0.0,
        error=True,
        stop_reason="error",
        warnings=["all providers failed"],
        fallback_chain=attempted,
        turn_mode=cast(TurnMode, ctx.turn_mode),
        supports_native_resume=ctx.supports_native_resume,
        error_kind="provider_runtime",
        retryable=False,
    )


# ---------------------------------------------------------------------------
# Agent tool loop
# ---------------------------------------------------------------------------


async def _run_agent_loop(
    ctx: QueryContext,
    item: QueueItem,
    user_id: int,
    chat_id: int,
    context: BotContext,
    initial_result: RunResult,
    task_id: int | None = None,
) -> RunResult:
    """Execute agent tool calls in a loop, resuming the provider session with results."""
    import json as _json
    from dataclasses import asdict

    from koda.knowledge import default_execution_policy
    from koda.services.execution_confidence import evaluate_write_confidence, parse_action_plan
    from koda.services.runtime import get_runtime_controller
    from koda.services.tool_dispatcher import (
        AgentToolCall,
        AgentToolResult,
        ToolContext,
        _infer_tool_category,
        _is_write_tool,
        execute_tool,
        format_tool_results,
        parse_agent_commands,
    )
    from koda.utils.approval import (
        APPROVAL_TIMEOUT,
        cleanup_agent_cmd_op,
        get_agent_cmd_decision,
        request_agent_cmd_approval,
    )

    current_result = initial_result
    runtime = None
    with contextlib.suppress(RuntimeError):
        runtime = get_runtime_controller()
    if ctx.effective_policy is None:
        ctx.effective_policy = default_execution_policy(
            ctx.task_kind,
            environment=str(getattr(ctx.knowledge_query_context, "environment", "")),
        )
    seen_calls: set[frozenset] = set()
    status_msg_ids: list[int] = []
    all_temp_image_paths: list[str] = []
    verification_follow_up_requested = False
    guardrail_message: str | None = None
    last_diff_hash = ""
    last_failure_fingerprint = ""
    repeated_failure_streak = 0

    loop_exhausted = False
    for _iteration in range(MAX_AGENT_TOOL_ITERATIONS):
        if (
            runtime is not None
            and task_id is not None
            and RUNTIME_ENVIRONMENTS_ENABLED
            and ctx.runtime_env_id is not None
        ):
            await runtime.cooperate_pause(task_id=task_id, env_id=ctx.runtime_env_id, phase="executing")
        tool_calls, clean_text = parse_agent_commands(current_result.result)
        if not tool_calls:
            if (
                _requires_post_write_verification(ctx)
                and current_result.tool_execution_trace
                and any(step.get("metadata", {}).get("write") for step in current_result.tool_execution_trace)
                and not _has_post_write_verification(current_result.tool_execution_trace)
                and not verification_follow_up_requested
            ):
                verification_follow_up_requested = True
                verification_requirements = ", ".join(getattr(ctx.effective_policy, "required_verifications", ()))
                verification_prompt = (
                    "A write operation already happened for this task. "
                    f"Policy for '{ctx.task_kind}' requires post-write verification ({verification_requirements}). "
                    "Before finalizing, emit only read-only <agent_cmd> calls that verify the resulting state."
                )
                resume_ctx = QueryContext(
                    task_id=ctx.task_id,
                    provider=current_result.provider,
                    work_dir=context.user_data.get("work_dir", ctx.work_dir),
                    model=ctx.model,
                    session_id=current_result.session_id,
                    provider_session_id=current_result.provider_session_id,
                    system_prompt=ctx.system_prompt,
                    agent_mode=ctx.agent_mode,
                    permission_mode=ctx.permission_mode,
                    max_turns=1,
                    warnings=ctx.warnings,
                    cache_hit=ctx.cache_hit,
                    script_matches=ctx.script_matches,
                    knowledge_hits=ctx.knowledge_hits,
                    knowledge_resolution=ctx.knowledge_resolution,
                    memory_resolution=ctx.memory_resolution,
                    memory_profile=ctx.memory_profile,
                    memory_trust_score=ctx.memory_trust_score,
                    confidence_reports=ctx.confidence_reports,
                    task_kind=ctx.task_kind,
                    knowledge_query_context=ctx.knowledge_query_context,
                    effective_policy=ctx.effective_policy,
                    ungrounded_operationally=ctx.ungrounded_operationally,
                    last_action_plan=ctx.last_action_plan,
                    artifact_dossiers=ctx.artifact_dossiers,
                    visual_paths=ctx.visual_paths,
                    temp_paths=ctx.temp_paths,
                    runtime_env_id=ctx.runtime_env_id,
                )
                resume_item = QueueItem(chat_id=chat_id, query_text=verification_prompt)
                resume_result = await _run_with_provider_fallback(
                    resume_ctx,
                    resume_item,
                    user_id,
                    chat_id,
                    context,
                    task_id,
                )
                if resume_result is None:
                    current_result.result = clean_text
                    break
                resume_result.cost_usd += current_result.cost_usd
                resume_result.usage = current_result.usage | resume_result.usage
                resume_result.tool_uses = current_result.tool_uses + resume_result.tool_uses
                resume_result.native_items = current_result.native_items + resume_result.native_items
                resume_result.tool_execution_trace = (
                    current_result.tool_execution_trace + resume_result.tool_execution_trace
                )
                current_result = resume_result
                continue
            ctx.verified_before_finalize = _has_post_write_verification(current_result.tool_execution_trace)
            current_result.result = clean_text
            break

        # Cycle detection
        call_signatures = frozenset((c.tool, _json.dumps(c.params, sort_keys=True)) for c in tool_calls)
        if call_signatures in seen_calls:
            log.warning("agent_loop_cycle_detected", iteration=_iteration)
            if (
                runtime is not None
                and task_id is not None
                and RUNTIME_ENVIRONMENTS_ENABLED
                and ctx.runtime_env_id is not None
            ):
                cycle_id = await runtime.record_loop_cycle(
                    task_id=task_id,
                    cycle_index=_iteration + 1,
                    phase="executing",
                    command_fingerprint=_json.dumps(sorted(call_signatures), ensure_ascii=False),
                    outcome={"cycle_detected": True},
                )
                await runtime.record_guardrail_hit(
                    task_id=task_id,
                    guardrail_type="repeated_command",
                    cycle_id=cycle_id,
                    details={"iteration": _iteration},
                )
                await runtime.record_warning(
                    task_id=task_id,
                    warning_type="loop_detected",
                    message="Repeated tool signature detected; stopping agent loop.",
                    details={"iteration": _iteration},
                )
                await runtime.pause_environment(
                    task_id=task_id,
                    reason="Loop detectado pelo runtime: assinatura de tools repetida.",
                )
            guardrail_message = "Loop detectado pelo runtime: assinatura repetida de comandos."
            current_result.warnings.append(guardrail_message)
            break
        seen_calls.add(call_signatures)

        # Visual status for the user
        tool_names = ", ".join(c.tool for c in tool_calls)
        try:
            msg = await context.bot.send_message(chat_id=chat_id, text=f"\U0001f527 {tool_names}...")
            status_msg_ids.append(msg.message_id)
        except Exception:
            pass

        # Preserve tool order while still evaluating approval and confidence before writes.
        tool_ctx = ToolContext(
            user_id=user_id,
            chat_id=chat_id,
            work_dir=context.user_data.get("work_dir", ctx.work_dir),
            user_data=context.user_data,
            agent=context.bot,
            agent_mode=ctx.agent_mode,
            task_id=task_id,
            dry_run=ctx.dry_run,
            scheduled_job_id=ctx.scheduled_job_id,
            scheduled_run_id=ctx.scheduled_run_id,
        )

        leading_read_calls: list[AgentToolCall] = []
        remaining_calls: list[AgentToolCall] = []
        encountered_write = False
        for call in tool_calls:
            is_write = _is_write_tool(call.tool, call.params)
            if not encountered_write and not is_write:
                leading_read_calls.append(call)
                continue
            if is_write:
                encountered_write = True
            remaining_calls.append(call)

        write_calls = [call for call in remaining_calls if _is_write_tool(call.tool, call.params)]
        executed_pairs: list[tuple[AgentToolCall, AgentToolResult]] = []

        for call in leading_read_calls:
            executed_pairs.append((call, await execute_tool(call, tool_ctx)))

        blocked_write_results: list[AgentToolResult] = []
        skip_following_reads = False

        if write_calls:
            from koda.services import audit, metrics

            action_plan = parse_action_plan(current_result.result)
            if action_plan:
                ctx.last_action_plan = asdict(action_plan)
                if (
                    runtime is not None
                    and task_id is not None
                    and RUNTIME_ENVIRONMENTS_ENABLED
                    and ctx.runtime_env_id is not None
                ):
                    await runtime.record_plan(task_id=task_id, plan=ctx.last_action_plan)
            confidence_report = evaluate_write_confidence(
                action_plan=action_plan,
                task_kind=ctx.task_kind,
                policy=ctx.effective_policy,
                read_calls=leading_read_calls,
                prior_tool_steps=current_result.tool_execution_trace,
                native_tool_uses=current_result.tool_uses,
                knowledge_hits=_serialize_knowledge_hits(ctx.knowledge_hits),
                memory_resolution=ctx.memory_resolution,
                memory_profile=ctx.memory_profile,
                warnings=ctx.warnings,
                guardrails=list(getattr(ctx.knowledge_resolution, "guardrails", []) or []),
                stale_sources_present=ctx.stale_sources_present,
                ungrounded_operationally=ctx.ungrounded_operationally,
            )
            ctx.confidence_reports.append(confidence_report.to_dict())
            metrics.EXECUTION_CONFIDENCE_SCORE.labels(agent_id=_agent_id_label, mode=ctx.agent_mode).observe(
                confidence_report.score
            )

            if confidence_report.blocked:
                if confidence_report.write_mode == "read_only":
                    reason_label = "read_only_policy"
                elif "task requires explicit escalation before writes" in confidence_report.reasons:
                    reason_label = "missing_escalation"
                elif not confidence_report.plan_valid:
                    reason_label = "missing_plan"
                elif "required policy/source layer is missing" in confidence_report.reasons:
                    reason_label = "missing_sources"
                elif "rollback note is required for this task kind" in confidence_report.reasons:
                    reason_label = "missing_rollback"
                elif "probable cause is required for this task kind" in confidence_report.reasons:
                    reason_label = "missing_probable_cause"
                elif "verification plan is required for this task kind" in confidence_report.reasons:
                    reason_label = "missing_verification_plan"
                elif confidence_report.read_evidence_count < getattr(ctx.effective_policy, "min_read_evidence", 1):
                    reason_label = "missing_evidence"
                else:
                    reason_label = "low_score"
                metrics.EXECUTION_CONFIDENCE_BLOCKS.labels(agent_id=_agent_id_label, reason=reason_label).inc()
                audit.emit_task_lifecycle(
                    "task.confidence_blocked",
                    user_id=user_id,
                    task_id=task_id,
                    confidence=confidence_report.score,
                    reason=reason_label,
                    missing_fields=confidence_report.missing_fields,
                )
                blocked_write_results = [
                    AgentToolResult(
                        tool=c.tool,
                        success=False,
                        output=confidence_report.to_tool_message(),
                        metadata={"confidence": confidence_report.to_dict()},
                    )
                    for c in write_calls
                ]
                skip_following_reads = True
            elif context.user_data.get("_approve_all_agent_tools"):
                # Writes were already approved earlier in this session; execute them in order below.
                pass
            elif (
                getattr(ctx.effective_policy, "approval_mode", "supervised") == "guarded"
                and not confidence_report.requires_human_approval
            ):
                # Guarded mode allows the write set; execution still happens in original tool order below.
                pass
            else:
                # Build description and request approval
                desc_parts = [f"{c.tool}({_json.dumps(c.params, ensure_ascii=False)[:120]})" for c in write_calls]
                description = "; ".join(desc_parts)
                op_id = await request_agent_cmd_approval(context.bot, chat_id, user_id, description)
                try:
                    from koda.utils.approval import _PENDING_AGENT_CMD_OPS

                    op = _PENDING_AGENT_CMD_OPS.get(op_id)
                    if op:
                        try:
                            await asyncio.wait_for(op["event"].wait(), timeout=APPROVAL_TIMEOUT)
                        except TimeoutError:
                            op["decision"] = "timeout"
                    decision = get_agent_cmd_decision(op_id)
                    if decision == "approved":
                        ctx.human_approval_used = True
                        metrics.HUMAN_OVERRIDE.labels(agent_id=_agent_id_label, decision="approved").inc()
                    elif decision == "approved_all":
                        ctx.human_approval_used = True
                        metrics.HUMAN_OVERRIDE.labels(agent_id=_agent_id_label, decision="approved_all").inc()
                        context.user_data["_approve_all_agent_tools"] = True
                    else:
                        # Denied or timeout
                        decision_label = "denied" if decision == "denied" else "timeout"
                        metrics.HUMAN_OVERRIDE.labels(agent_id=_agent_id_label, decision=decision_label).inc()
                        reason = "Denied by user." if decision == "denied" else "Approval timed out."
                        blocked_write_results = [
                            AgentToolResult(tool=c.tool, success=False, output=reason) for c in write_calls
                        ]
                        skip_following_reads = True
                finally:
                    cleanup_agent_cmd_op(op_id)

        blocked_write_iter = iter(blocked_write_results)
        for call in remaining_calls:
            if _is_write_tool(call.tool, call.params):
                if skip_following_reads:
                    executed_pairs.append((call, next(blocked_write_iter)))
                else:
                    executed_pairs.append((call, await execute_tool(call, tool_ctx)))
                continue
            if skip_following_reads:
                executed_pairs.append(
                    (
                        call,
                        AgentToolResult(
                            tool=call.tool,
                            success=False,
                            output="Skipped because a previous write step was blocked or denied.",
                            metadata={
                                "category": _infer_tool_category(call.tool),
                                "skipped_after_blocked_write": True,
                            },
                        ),
                    )
                )
                continue
            executed_pairs.append((call, await execute_tool(call, tool_ctx)))

        results = [result for _, result in executed_pairs]
        updated_work_dir = context.user_data.get("work_dir", ctx.work_dir)
        diff_hash = _workspace_diff_hash(updated_work_dir if ctx.runtime_env_id is not None else None)
        successful_write_executed = any(
            _is_write_tool(call.tool, call.params) and result.success for call, result in executed_pairs
        )
        failure_outputs = [
            f"{call.tool}:{result.output[:2000]}"
            for call, result in executed_pairs
            if not result.success and result.output
        ]
        failure_fingerprint = _hash_text("\n".join(failure_outputs)) if failure_outputs else ""
        repeated_diff_detected = bool(diff_hash) and diff_hash == last_diff_hash and successful_write_executed
        if failure_fingerprint and failure_fingerprint == last_failure_fingerprint:
            repeated_failure_streak += 1
        elif failure_fingerprint:
            repeated_failure_streak = 1
        else:
            repeated_failure_streak = 0
        last_failure_fingerprint = failure_fingerprint
        recorded_cycle_id: int | None = None
        if (
            runtime is not None
            and task_id is not None
            and RUNTIME_ENVIRONMENTS_ENABLED
            and ctx.runtime_env_id is not None
        ):
            recorded_cycle_id = await runtime.record_loop_cycle(
                task_id=task_id,
                cycle_index=_iteration + 1,
                phase="executing",
                plan=ctx.last_action_plan or {},
                command_fingerprint=_json.dumps(
                    [(call.tool, _json.dumps(call.params, sort_keys=True)) for call, _ in executed_pairs],
                    ensure_ascii=False,
                ),
                diff_hash=diff_hash,
                failure_fingerprint=failure_fingerprint,
                validations=[{"tool": call.tool, "success": result.success} for call, result in executed_pairs],
                outcome={"result_count": len(results)},
            )
        current_result.tool_execution_trace.extend(
            [
                {
                    "iteration": _iteration + 1,
                    "tool": call.tool,
                    "params": call.params,
                    "success": result.success,
                    "output": result.output,
                    "metadata": {
                        "write": _is_write_tool(call.tool, call.params),
                        **result.metadata,
                    },
                    "duration_ms": result.duration_ms,
                    "started_at": result.started_at,
                    "completed_at": result.completed_at,
                }
                for call, result in executed_pairs
            ]
        )

        # Detect image artifacts returned by tools. Runtime browser screenshots may
        # live inside the task directory and must stay available after the turn.
        visual_paths_this_iteration: list[str] = []
        temp_frame_paths_this_iteration: list[str] = []
        for r in results:
            if r.success and "/" in r.output:
                import re as _re

                paths = _re.findall(
                    r"/[^\s'\"<>]+\.(?:jpg|jpeg|png|gif|webp)",
                    r.output,
                )
                for path in paths:
                    if path not in visual_paths_this_iteration:
                        visual_paths_this_iteration.append(path)
                    if path.startswith(f"{IMAGE_TEMP_DIR}/") or path.startswith(str(IMAGE_TEMP_DIR)):
                        temp_frame_paths_this_iteration.append(path)
        all_temp_image_paths.extend(temp_frame_paths_this_iteration)
        no_change_detected = (
            bool(diff_hash)
            and diff_hash == last_diff_hash
            and not successful_write_executed
            and not visual_paths_this_iteration
        )
        if (
            recorded_cycle_id is not None
            and runtime is not None
            and task_id is not None
            and RUNTIME_ENVIRONMENTS_ENABLED
            and ctx.runtime_env_id is not None
        ):
            if repeated_diff_detected:
                await runtime.record_guardrail_hit(
                    task_id=task_id,
                    guardrail_type="repeated_diff",
                    cycle_id=recorded_cycle_id,
                    details={"iteration": _iteration + 1, "diff_hash": diff_hash},
                )
                await runtime.record_warning(
                    task_id=task_id,
                    warning_type="repeated_diff",
                    message="O diff do workspace não mudou por dois ciclos consecutivos de escrita.",
                    details={"iteration": _iteration + 1, "diff_hash": diff_hash},
                )
                await runtime.pause_environment(
                    task_id=task_id,
                    reason="Guardrail do runtime: diff repetido em ciclos consecutivos.",
                )
                guardrail_message = "Guardrail do runtime acionado: diff repetido em ciclos consecutivos."
            elif no_change_detected:
                await runtime.record_guardrail_hit(
                    task_id=task_id,
                    guardrail_type="no_change",
                    cycle_id=recorded_cycle_id,
                    details={"iteration": _iteration + 1, "diff_hash": diff_hash},
                )
                await runtime.record_warning(
                    task_id=task_id,
                    warning_type="no_change",
                    message="Nenhuma mudança observável foi detectada por dois ciclos consecutivos.",
                    details={"iteration": _iteration + 1, "diff_hash": diff_hash},
                )
                await runtime.pause_environment(
                    task_id=task_id,
                    reason="Guardrail do runtime: nenhuma mudança observável em ciclos consecutivos.",
                )
                guardrail_message = "Guardrail do runtime acionado: nenhuma mudança observável em ciclos consecutivos."
            elif repeated_failure_streak >= 3:
                await runtime.record_guardrail_hit(
                    task_id=task_id,
                    guardrail_type="repeated_failure",
                    cycle_id=recorded_cycle_id,
                    details={"iteration": _iteration + 1, "failure_fingerprint": failure_fingerprint},
                )
                await runtime.record_warning(
                    task_id=task_id,
                    warning_type="repeated_failure",
                    message="A mesma falha se repetiu por três ciclos consecutivos.",
                    details={"iteration": _iteration + 1, "failure_fingerprint": failure_fingerprint},
                )
                await runtime.pause_environment(
                    task_id=task_id,
                    reason="Guardrail do runtime: falha repetida por três ciclos.",
                )
                guardrail_message = "Guardrail do runtime acionado: a mesma falha se repetiu por três ciclos."
        if guardrail_message:
            current_result.warnings.append(guardrail_message)
            break
        last_diff_hash = diff_hash or last_diff_hash

        # Resume session with results.
        # Use original model for complex resumes (3+ tools or large output),
        # Haiku for simple resumes (1-2 tools with small output).
        resume_prompt = format_tool_results(results)
        if successful_write_executed:
            verification_requirements = ", ".join(getattr(ctx.effective_policy, "required_verifications", ()))
            verification_suffix = (
                f"\n\nBefore you finalize, verify the resulting state with read-only checks. "
                f"Task policy for '{ctx.task_kind}' requires: {verification_requirements or 'read-back verification'}."
            )
            resume_prompt += verification_suffix
        total_output_len = sum(len(r.output) for r in results)
        use_original_model = len(results) >= 3 or total_output_len > 4000
        resume_model = (
            ctx.model
            if use_original_model
            else resolve_provider_model(
                ctx.provider,
                query=resume_prompt,
                auto_model=True,
                has_images=bool(visual_paths_this_iteration),
            )
        )
        resume_ctx = QueryContext(
            task_id=ctx.task_id,
            provider=current_result.provider,
            work_dir=updated_work_dir,
            model=resume_model,
            session_id=current_result.session_id,
            provider_session_id=current_result.provider_session_id,
            system_prompt=ctx.system_prompt,
            agent_mode=ctx.agent_mode,
            permission_mode=ctx.permission_mode,
            max_turns=2,
            warnings=ctx.warnings,
            cache_hit=ctx.cache_hit,
            script_matches=ctx.script_matches,
            knowledge_hits=ctx.knowledge_hits,
            knowledge_resolution=ctx.knowledge_resolution,
            memory_resolution=ctx.memory_resolution,
            memory_profile=ctx.memory_profile,
            memory_trust_score=ctx.memory_trust_score,
            confidence_reports=ctx.confidence_reports,
            task_kind=ctx.task_kind,
            knowledge_query_context=ctx.knowledge_query_context,
            effective_policy=ctx.effective_policy,
            ungrounded_operationally=ctx.ungrounded_operationally,
            last_action_plan=ctx.last_action_plan,
            artifact_dossiers=ctx.artifact_dossiers,
            visual_paths=visual_paths_this_iteration if visual_paths_this_iteration else ctx.visual_paths,
            temp_paths=list(dict.fromkeys([*ctx.temp_paths, *temp_frame_paths_this_iteration])),
            runtime_env_id=ctx.runtime_env_id,
        )
        resume_item = QueueItem(
            chat_id=chat_id,
            query_text=resume_prompt,
            image_paths=visual_paths_this_iteration if visual_paths_this_iteration else None,
        )

        resume_result = await _run_with_provider_fallback(resume_ctx, resume_item, user_id, chat_id, context, task_id)
        if resume_result is None:
            current_result.result = clean_text
            break

        # Accumulate cost and tool_uses
        resume_result.cost_usd += current_result.cost_usd
        resume_result.usage = current_result.usage | resume_result.usage
        resume_result.tool_uses = current_result.tool_uses + resume_result.tool_uses
        resume_result.native_items = current_result.native_items + resume_result.native_items
        resume_result.tool_execution_trace = current_result.tool_execution_trace + resume_result.tool_execution_trace
        current_result = resume_result

    else:
        # for-loop completed without break — iterations exhausted
        loop_exhausted = True

    if loop_exhausted:
        current_result.warnings.append(
            f"iteration limit ({MAX_AGENT_TOOL_ITERATIONS}) reached — use /retry to continue"
        )
        log.warning("agent_loop_exhausted", iterations=MAX_AGENT_TOOL_ITERATIONS)
        if (
            runtime is not None
            and task_id is not None
            and RUNTIME_ENVIRONMENTS_ENABLED
            and ctx.runtime_env_id is not None
        ):
            loop_exhausted_cycle_id = await runtime.record_loop_cycle(
                task_id=task_id,
                cycle_index=MAX_AGENT_TOOL_ITERATIONS,
                phase="executing",
                outcome={"loop_exhausted": True},
            )
            await runtime.record_guardrail_hit(
                task_id=task_id,
                guardrail_type="retry_exhausted",
                cycle_id=loop_exhausted_cycle_id,
                details={"iterations": MAX_AGENT_TOOL_ITERATIONS},
            )
            await runtime.record_warning(
                task_id=task_id,
                warning_type="retry_exhausted",
                message="Loop do agente atingiu o limite de iterações.",
                details={"iterations": MAX_AGENT_TOOL_ITERATIONS},
            )
            await runtime.pause_environment(
                task_id=task_id,
                reason="Loop do agente atingiu o limite de iterações e foi pausado.",
            )
        guardrail_message = (
            f"Guardrail do runtime acionado: limite de iterações ({MAX_AGENT_TOOL_ITERATIONS}) atingido."
        )

    # Clean up status messages
    for msg_id in status_msg_ids:
        with contextlib.suppress(Exception):
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)

    # Clean up extracted video frames
    if all_temp_image_paths:
        from koda.utils.video import cleanup_video_frames

        cleanup_video_frames(all_temp_image_paths)

    # Strip any residual tags
    ctx.verified_before_finalize = _has_post_write_verification(current_result.tool_execution_trace)
    _, current_result.result = parse_agent_commands(current_result.result)
    if guardrail_message:
        current_result.error = True
        current_result.retryable = False
        current_result.error_kind = "runtime_guardrail"
        current_result.result = guardrail_message
    return current_result


# ---------------------------------------------------------------------------
# Response sending
# ---------------------------------------------------------------------------


def _build_response_markup(task_id: int | None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton("📌 Bookmark", callback_data="bookmark:save")]]
    if task_id is not None:
        rows.append(
            [
                InlineKeyboardButton("✅ Aprovado", callback_data=f"feedback:approved:{task_id}"),
                InlineKeyboardButton("🛠 Corrigir", callback_data=f"feedback:corrected:{task_id}"),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton("❌ Falhou", callback_data=f"feedback:failed:{task_id}"),
                InlineKeyboardButton("⚠️ Risco", callback_data=f"feedback:risky:{task_id}"),
            ]
        )
        rows.append([InlineKeyboardButton("📈 Promover", callback_data=f"feedback:promote:{task_id}")])
    return InlineKeyboardMarkup(rows)


def _build_operational_footer(ctx: QueryContext | None, run_result: RunResult) -> str:
    if ctx is None:
        return ""
    if not any(step.get("metadata", {}).get("write") for step in run_result.tool_execution_trace):
        return ""

    from koda.utils.formatting import escape_html

    source_parts: list[str] = []
    seen_sources: set[str] = set()
    for hit in _serialize_knowledge_hits(ctx.knowledge_hits):
        label = str(hit.get("source_label") or "").strip()
        if not label or label in seen_sources:
            continue
        seen_sources.add(label)
        updated_at = str(hit.get("updated_at") or "").strip()
        source_parts.append(f"{label} ({updated_at})" if updated_at else label)
        if len(source_parts) >= 3:
            break

    tier = getattr(getattr(ctx.effective_policy, "autonomy_tier", None), "value", "unknown")
    approval_mode = str(getattr(ctx.effective_policy, "approval_mode", "standard"))
    verification_status = "verified" if ctx.verified_before_finalize else "missing"
    latest = ctx.confidence_reports[-1] if ctx.confidence_reports else {}
    answer_eval = ctx.answer_evaluation

    flow_bits: list[str] = []
    if ctx.human_approval_used:
        flow_bits.append("human-approved")
    elif ctx.confidence_reports and ctx.confidence_reports[-1].get("requires_human_approval"):
        flow_bits.append("escalated")
    else:
        flow_bits.append(approval_mode)
    if len(run_result.fallback_chain) > 1:
        flow_bits.append("provider-fallback")
    if ctx.stale_sources_present:
        flow_bits.append("stale-sources")

    lines = [
        f"Sources: {', '.join(source_parts) if source_parts else 'runtime inspection'}",
        (
            "Winning sources: "
            + ", ".join((getattr(ctx.knowledge_resolution, "winning_sources", []) or [])[:3] or ["none"])
        ),
        (
            f"Memory trust: {ctx.memory_trust_score:.2f}"
            + (
                f" | layers: {', '.join(getattr(ctx.memory_resolution, 'selected_layers', [])[:3])}"
                if getattr(ctx, "memory_resolution", None)
                else ""
            )
        ),
        (
            "Grounding: "
            + ", ".join(latest.get("operable_source_layers", [])[:3] or ["none-operable"])
            + (
                f" | weak: {', '.join(latest.get('non_operable_source_layers', [])[:3])}"
                if latest.get("non_operable_source_layers")
                else ""
            )
        )
        if ctx.confidence_reports
        else "Grounding: runtime inspection",
        (
            "Retrieval: "
            f"{getattr(getattr(ctx.knowledge_resolution, 'retrieval_strategy', None), 'value', 'unknown')}"
            f" | route: {getattr(ctx.knowledge_resolution, 'retrieval_route', 'unknown')}"
            f" | grounding score: {float(getattr(ctx.knowledge_resolution, 'grounding_score', 0.0) or 0.0):.2f}"
        ),
        f"Citations: {float(_answer_eval_value(answer_eval, 'citation_coverage', 0.0) or 0.0):.0%}",
        f"Verification: {verification_status}",
        f"Tier: {tier} | Mode: {approval_mode}",
        f"Flow: {', '.join(flow_bits)}",
    ]
    return "\n" + "\n".join(f"<i>{escape_html(line)}</i>" for line in lines)


def _compose_response_text(
    run_result: RunResult,
    *,
    response_override: str | None = None,
    elapsed: float = 0.0,
    include_tool_summary: bool = True,
) -> tuple[str, str]:
    """Compose the user-visible response text before Telegram formatting."""
    from koda.services.execution_confidence import strip_internal_blocks

    tool_summary = ""
    if include_tool_summary and run_result.tool_uses:
        from koda.utils.tool_parser import format_completion_summary

        completion = format_completion_summary(run_result.tool_uses, elapsed)
        if completion:
            tool_summary = completion
        else:
            tool_summary = summarize_tool_uses(run_result.tool_uses)
    elif include_tool_summary and run_result.native_items:
        tool_summary = summarize_native_items(run_result.native_items)
    elif include_tool_summary and run_result.raw_output:
        tools = parse_tool_uses(run_result.raw_output)
        tool_summary = format_tool_summary(tools)

    response = response_override if response_override is not None else strip_internal_blocks(run_result.result or "")
    if not response and tool_summary:
        response = tool_summary
    elif tool_summary:
        response = f"{tool_summary}\n\n{response}"
    return response, tool_summary


async def _send_response(
    chat_id: int,
    update: Update | None,
    context: BotContext,
    run_result: RunResult,
    work_dir: str,
    agent_mode: str,
    elapsed: float = 0.0,
    model: str = "",
    task_id: int | None = None,
    ctx: QueryContext | None = None,
    response_override: str | None = None,
    include_tool_summary: bool = True,
) -> None:
    """Send the provider response: TTS, code blocks, HTML text, artifacts, supervised buttons."""
    cost = run_result.cost_usd
    response, tool_summary = _compose_response_text(
        run_result,
        response_override=response_override,
        elapsed=elapsed,
        include_tool_summary=include_tool_summary,
    )

    response_markup = _build_response_markup(task_id)

    # --- TTS voice response branch ---
    audio_sent = False
    if context.user_data.get("audio_response") and TTS_ENABLED:
        from koda.utils.tts import is_mostly_code, strip_for_tts, synthesize_speech

        if not is_mostly_code(response):
            plain = strip_for_tts(response)
            if plain.strip():
                from koda.config import TTS_DEFAULT_VOICE, TTS_SPEED

                tts_voice = context.user_data.get("tts_voice", TTS_DEFAULT_VOICE)
                ogg_path = await synthesize_speech(
                    plain,
                    tts_voice,
                    TTS_SPEED,
                    provider=str(context.user_data.get("audio_provider") or "").strip().lower() or None,
                    model=str(context.user_data.get("audio_model") or "").strip() or None,
                    language=str(context.user_data.get("tts_voice_language") or "").strip().lower() or None,
                )
                if not ogg_path:
                    run_result.warnings.append("audio failed")
                if ogg_path:
                    from pathlib import Path as _P

                    try:
                        caption = (
                            f"Cost: ${cost:.4f} | "
                            f"Total: ${context.user_data['total_cost']:.4f} | "
                            f"Dir: {os.path.basename(work_dir)}"
                        )
                        with open(ogg_path, "rb") as vf:
                            if update and update.message:
                                await update.message.reply_voice(
                                    voice=vf,
                                    caption=caption,
                                    reply_markup=response_markup,
                                )
                            else:
                                await context.bot.send_voice(
                                    chat_id=chat_id,
                                    voice=vf,
                                    caption=caption,
                                    reply_markup=response_markup,
                                )
                        audio_sent = True
                    except Exception:
                        log.exception("tts_send_error")
                    finally:
                        _P(ogg_path).unlink(missing_ok=True)

    # Send text response
    import tempfile
    from pathlib import Path

    from koda.utils.formatting import (
        escape_html,
        extract_and_replace_large_blocks,
        format_error_message,
        safe_markdown_to_telegram_html,
    )

    code_files: list[tuple[str, str]]
    if run_result.error:
        modified_text, code_files = response, []
    elif not audio_sent:
        modified_text, code_files = extract_and_replace_large_blocks(response)
    else:
        modified_text, code_files = response, []

    if not audio_sent:
        # Send code files
        for filename, content in code_files:
            with tempfile.NamedTemporaryFile(mode="w", suffix=f"_{filename}", prefix="code_", delete=False) as f:
                f.write(content)
                tmp_path = f.name
            try:
                with open(tmp_path, "rb") as fh:
                    if update and update.message:
                        await update.message.reply_document(
                            document=fh,
                            filename=filename,
                            caption=f"Code block: {filename}",
                        )
                    else:
                        await context.bot.send_document(
                            chat_id=chat_id,
                            document=fh,
                            filename=filename,
                            caption=f"Code block: {filename}",
                        )
            finally:
                Path(tmp_path).unlink(missing_ok=True)

        from telegram.constants import ParseMode

        from koda.utils.messaging import split_message

        html_text = (
            format_error_message(modified_text) if run_result.error else safe_markdown_to_telegram_html(modified_text)
        )
        # Enriched footer for tasks >5s, minimal for quick tasks
        tool_count = len(run_result.tool_uses) if run_result.tool_uses else len(run_result.native_items)
        extra_parts = []
        extra_parts.append(escape_html(run_result.provider))
        if model:
            extra_parts.append(escape_html(model))
        if elapsed > 5:
            extra_parts.append(_format_elapsed(elapsed))
        if tool_count > 0 and elapsed > 5:
            extra_parts.append(f"{tool_count} tools")
        extra = " | ".join(extra_parts)
        footer_detail = f" | {extra}" if extra else ""
        warning_text = ""
        if run_result.warnings:
            warning_text = "\n⚠️ " + ", ".join(run_result.warnings)
        footer = (
            f"\n\n———\n<i>Cost: ${cost:.4f} | "
            f"Total: ${context.user_data['total_cost']:.4f}{footer_detail} | "
            f"Dir: {escape_html(os.path.basename(work_dir))}</i>"
            f"{warning_text}"
            f"{_build_operational_footer(ctx, run_result)}"
        )
        html_text += footer
        chunks_to_send = split_message(html_text)
        for i, chunk in enumerate(chunks_to_send):
            is_last = i == len(chunks_to_send) - 1
            try:
                if update and update.message:
                    await update.message.reply_text(
                        chunk,
                        parse_mode=ParseMode.HTML,
                        reply_markup=response_markup if is_last else None,
                    )
                else:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=chunk,
                        parse_mode=ParseMode.HTML,
                        reply_markup=response_markup if is_last else None,
                    )
            except Exception:
                import re as _re

                plain_text = _re.sub(r"<[^>]+>", "", chunk)
                try:
                    if update and update.message:
                        await update.message.reply_text(
                            plain_text,
                            reply_markup=response_markup if is_last else None,
                        )
                    else:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=plain_text,
                            reply_markup=response_markup if is_last else None,
                        )
                except Exception:
                    if update and update.message:
                        await update.message.reply_text(plain_text)
                    else:
                        await context.bot.send_message(chat_id=chat_id, text=plain_text)

    # Send created artifacts
    if run_result.tool_uses or run_result.native_items:
        created = extract_created_files(run_result.tool_uses, run_result.native_items)
        if created:
            sent = await send_created_files(created, chat_id, context, update)
            if sent:
                log.info("artifacts_sent", count=sent, total=len(created))

    # Supervised mode: Continue/Stop buttons
    if agent_mode == "supervised" and run_result.stop_reason == "max_turns" and run_result.session_id:
        from telegram.constants import ParseMode

        context.user_data["_supervised_session_id"] = run_result.session_id
        context.user_data["_supervised_provider"] = run_result.provider
        supervised_buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("▶ Continue", callback_data="supervised:continue"),
                    InlineKeyboardButton("⏹ Stop", callback_data="supervised:stop"),
                ]
            ]
        )
        supervised_text = f"🔍 <b>Supervised mode</b> — {escape_html(run_result.provider)} paused after 1 turn."
        if tool_summary:
            supervised_text += f"\n{tool_summary}"
        await context.bot.send_message(
            chat_id=chat_id,
            text=supervised_text,
            reply_markup=supervised_buttons,
            parse_mode=ParseMode.HTML,
        )


# ---------------------------------------------------------------------------
# Post-processing
# ---------------------------------------------------------------------------


async def _post_process(
    user_id: int,
    context: BotContext,
    run_result: RunResult,
    query_text: str,
    work_dir: str,
    model: str,
    *,
    task_id: int | None = None,
    ctx: QueryContext | None = None,
    dry_run: bool = False,
    cacheable: bool = True,
    final_status: str = "completed",
    response_text_override: str | None = None,
) -> None:
    """Update session, stats, log query, extract memories."""
    effective_model = run_result.model or model

    # Update session and stats
    if run_result.session_id and not dry_run:
        context.user_data["session_id"] = run_result.session_id
        if run_result.provider_session_id:
            context.user_data.setdefault("provider_sessions", {})[run_result.provider] = run_result.provider_session_id
            save_provider_session_mapping(
                run_result.session_id,
                run_result.provider,
                run_result.provider_session_id,
                effective_model,
            )
        save_session(
            user_id,
            run_result.session_id,
            provider=run_result.provider,
            provider_session_id=run_result.provider_session_id,
            model=effective_model,
        )

    cost = run_result.cost_usd
    context.user_data["total_cost"] += cost
    context.user_data["query_count"] += 1

    save_user_cost(user_id, context.user_data["total_cost"], context.user_data["query_count"])

    # Log canonically through the history store (use "cache" as model for cache-served responses)
    log_model = "cache" if run_result.stop_reason == "cache_hit" else effective_model
    query_id: int | None = None
    if not dry_run:
        query_id = log_query(
            user_id=user_id,
            query_text=query_text,
            response_text=response_text_override if response_text_override is not None else run_result.result,
            cost_usd=cost,
            provider=run_result.provider,
            model=log_model,
            session_id=run_result.session_id,
            provider_session_id=run_result.provider_session_id,
            usage=run_result.usage,
            work_dir=work_dir,
            error=run_result.error,
        )
        context.user_data["last_query_id"] = query_id
        if ctx and getattr(ctx, "execution_episode_id", None) is not None:
            context.user_data["last_execution_episode_id"] = ctx.execution_episode_id

    # Extract and store memories (fire-and-forget)
    if not run_result.error and not dry_run and final_status == "completed":
        try:
            from koda.memory.config import MEMORY_ENABLED

            if MEMORY_ENABLED:
                from koda.memory import get_memory_manager

                async def _extract_memory() -> None:
                    try:
                        mm = get_memory_manager()
                        knowledge_ctx = getattr(ctx, "knowledge_query_context", None)
                        await mm.post_query(
                            query_text,
                            run_result.result,
                            user_id,
                            run_result.session_id,
                            source_query_id=query_id,
                            source_task_id=task_id,
                            source_episode_id=getattr(ctx, "execution_episode_id", None),
                            project_key=str(getattr(knowledge_ctx, "project_key", "") or ""),
                            environment=str(getattr(knowledge_ctx, "environment", "") or ""),
                            team=str(getattr(knowledge_ctx, "team", "") or ""),
                        )
                    except Exception:
                        log.exception("memory_extraction_error")

                asyncio.create_task(_extract_memory())
        except Exception:
            log.exception("memory_extraction_setup_error")

    # Cache store and script auto-extraction (fire-and-forget)
    if (
        not run_result.error
        and run_result.stop_reason != "cache_hit"
        and not dry_run
        and cacheable
        and final_status == "completed"
    ):
        try:
            from koda.services.cache_config import CACHE_ENABLED
            from koda.services.cache_manager import should_cache

            if CACHE_ENABLED and should_cache(query_text, run_result.result):
                from koda.services.cache_manager import get_cache_manager

                async def _cache_store() -> None:
                    try:
                        cm = get_cache_manager()
                        await cm.store(
                            user_id,
                            query_text,
                            run_result.result,
                            effective_model,
                            cost,
                            work_dir,
                            source_scope=tuple(
                                getattr(getattr(ctx, "knowledge_query_context", None), "allowed_source_labels", ())
                                or ()
                            ),
                            strategy_version=str(
                                getattr(getattr(ctx, "knowledge_query_context", None), "retrieval_strategy", "") or ""
                            ),
                            model_family=run_result.provider,
                        )
                    except Exception:
                        log.exception("cache_store_error")

                asyncio.create_task(_cache_store())
        except Exception:
            log.exception("cache_store_setup_error")

        try:
            from koda.services.cache_config import SCRIPT_AUTO_EXTRACT, SCRIPT_LIBRARY_ENABLED

            if SCRIPT_LIBRARY_ENABLED and SCRIPT_AUTO_EXTRACT:
                from koda.services.script_manager import get_script_manager

                async def _script_extract() -> None:
                    try:
                        sm = get_script_manager()
                        await sm.auto_extract(query_text, run_result.result, user_id)
                    except Exception:
                        log.exception("script_extraction_error")

                asyncio.create_task(_script_extract())
        except Exception:
            log.exception("script_extraction_setup_error")

    log.info(
        "query_complete",
        cost_usd=cost,
        model=log_model,
        error=run_result.error,
        dry_run=dry_run,
        final_status=final_status,
    )


# ---------------------------------------------------------------------------
# Main queue processor (orchestrator) — parallel dispatcher
# ---------------------------------------------------------------------------


async def _process_task_item(
    ctx: QueryContext,
    item: QueueItem,
    user_id: int,
    chat_id: int,
    context: BotContext,
    task_id: int,
) -> RunResult:
    """Core processing logic for a single task (extracted from old _process_queue)."""
    # Short-circuit for high-confidence cache hits
    if not ctx.artifact_dossiers and ctx.cache_hit and ctx.cache_hit.match_type in ("exact", "fuzzy_auto"):
        log.info(
            "cache_short_circuit",
            match_type=ctx.cache_hit.match_type,
            similarity=round(ctx.cache_hit.similarity, 3),
        )
        return RunResult(
            provider=ctx.provider,
            model=ctx.model,
            result=ctx.cache_hit.response,
            session_id=ctx.session_id,
            provider_session_id=ctx.provider_session_id,
            cost_usd=0.0,
            error=False,
            stop_reason="cache_hit",
        )

    run_result = await _run_with_provider_fallback(ctx, item, user_id, chat_id, context, task_id=task_id)

    # Agent loop: execute agent tool calls if present
    if run_result and run_result.result:
        from koda.services.tool_dispatcher import parse_agent_commands as _parse_cmds

        _calls, _ = _parse_cmds(run_result.result)
        if _calls:
            run_result = await _run_agent_loop(
                ctx,
                item,
                user_id,
                chat_id,
                context,
                run_result,
                task_id=task_id,
            )

    run_result.warnings.extend(ctx.warnings)
    return run_result


async def _send_task_error(
    task_info: TaskInfo,
    error_msg: str,
    context: BotContext,
    item: QueueItem | None = None,
) -> None:
    """Notify the user of a task failure via Telegram."""
    from koda.utils.formatting import format_error_message

    text = f"Task #{task_info.task_id} falhou:\n{format_error_message(error_msg)}"
    with contextlib.suppress(Exception):
        from telegram.constants import ParseMode

        if item and item.update and item.update.effective_message:
            await item.update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)
        else:
            await context.bot.send_message(chat_id=task_info.chat_id, text=text, parse_mode=ParseMode.HTML)


def _scheduled_summary(text: str | None, limit: int = 320) -> str | None:
    if not text:
        return None
    compact = " ".join(text.strip().split())
    if not compact:
        return None
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


async def _finalize_scheduled_run(
    *,
    item: QueueItem | None,
    ctx: QueryContext | None,
    run_result: RunResult | None,
    task_id: int,
    task_info: TaskInfo,
    context: BotContext,
    error_message: str | None = None,
    dlq_id: int | None = None,
    duration_ms: float | None = None,
) -> None:
    """Bridge queue outcomes back into the unified scheduled job ledger."""
    if not item or not item.is_scheduled_run or not item.scheduled_run_id:
        return

    from koda.services.scheduled_jobs import (
        derive_verification_status,
        get_run_details,
        handle_run_cancellation,
        handle_run_failure,
        handle_run_success,
    )

    run_details = get_run_details(item.scheduled_run_id)
    verification_policy = None
    if run_details:
        verification_policy = (run_details.get("job") or {}).get("verification_policy")

    tool_trace = run_result.tool_execution_trace if run_result else []
    had_writes = any(step.get("metadata", {}).get("write") for step in tool_trace)
    verification_status = derive_verification_status(
        trigger_reason=item.scheduled_trigger_reason or "",
        dry_run=bool(ctx.dry_run) if ctx else bool(item.scheduled_dry_run),
        had_writes=had_writes,
        verified_before_finalize=bool(ctx.verified_before_finalize) if ctx else False,
        tool_execution_trace=tool_trace,
        error=bool(error_message),
        error_message=error_message,
        verification_policy=verification_policy,
    )

    if verification_status == "cancelled":
        await handle_run_cancellation(
            run_id=item.scheduled_run_id,
            task_id=task_id,
            status="cancelled",
            reason=error_message or "Cancelled by scheduler control.",
            telegram_bot=context.bot,
            notification_chat_id=task_info.chat_id,
        )
        return

    if error_message or verification_status in {"failed", "blocked"}:
        await handle_run_failure(
            run_id=item.scheduled_run_id,
            task_id=task_id,
            error_message=error_message or "verification failed",
            provider_effective=(
                run_result.provider if run_result else (ctx.provider if ctx else item.scheduled_provider)
            ),
            model_effective=run_result.model if run_result else (ctx.model if ctx else item.scheduled_model),
            duration_ms=duration_ms,
            verification_status=verification_status,
            notification_summary=_scheduled_summary(run_result.result if run_result else error_message),
            notification_chat_id=task_info.chat_id,
            telegram_bot=context.bot,
            dlq_id=dlq_id,
        )
        return

    await handle_run_success(
        run_id=item.scheduled_run_id,
        task_id=task_id,
        provider_effective=run_result.provider if run_result else (ctx.provider if ctx else item.scheduled_provider),
        model_effective=run_result.model if run_result else (ctx.model if ctx else item.scheduled_model),
        duration_ms=duration_ms,
        verification_status=verification_status,
        summary_text=_scheduled_summary(run_result.result if run_result else None),
        fallback_chain=run_result.fallback_chain if run_result else [],
        artifacts=extract_created_files(
            run_result.tool_uses if run_result else [],
            run_result.native_items if run_result else [],
        ),
        telegram_bot=context.bot,
        notification_chat_id=task_info.chat_id,
    )


async def _execute_single_task(
    raw_item: Any,
    user_id: int,
    context: BotContext,
    task_id: int,
    task_info: TaskInfo,
) -> None:
    """Execute a single task with semaphore, retry, and error reporting."""
    from koda.services import audit, metrics
    from koda.services.runtime import get_runtime_controller

    semaphore = _get_user_semaphore(user_id)
    item: QueueItem | None = None
    ctx: QueryContext | None = None
    run_result: RunResult | None = None
    execution_timeline: list[dict[str, Any]] = []
    runtime = get_runtime_controller()
    heartbeat_task: asyncio.Task[None] | None = None
    runtime_capacity: contextlib.AsyncExitStack | None = None

    audit.emit_task_lifecycle("task.assigned", user_id=user_id, task_id=task_id)
    execution_timeline.append(
        _make_timeline_item(
            "task.assigned",
            "Tarefa atribuída",
            summary="A execução foi encaminhada para a fila de processamento.",
            details={"task_id": task_id},
        )
    )

    try:
        metrics.ACTIVE_TASKS.labels(agent_id=_agent_id_label).inc()
        async with _global_semaphore, semaphore:
            ctx_user_id.set(user_id)
            query_id = str(uuid.uuid4())[:8]
            ctx_query_id.set(query_id)

            item = _parse_queue_item(raw_item)
            if RUNTIME_ENVIRONMENTS_ENABLED:
                runtime.store.update_runtime_queue_item(task_id, status="running")
            if RUNTIME_ENVIRONMENTS_ENABLED:
                from koda.utils.command_helpers import init_user_data

                init_user_data(context.user_data, user_id=user_id)
                existing_env = (
                    runtime.store.get_environment_by_task(task_id)
                    if isinstance(raw_item, dict) and raw_item.get("_runtime_preprovisioned")
                    else None
                )
                if existing_env is not None:
                    if str(existing_env.get("environment_kind") or "") == "dev_worktree_browser":
                        existing_env = (
                            await runtime.ensure_environment_live_resources(
                                task_id=task_id,
                                env_id=int(existing_env["id"]),
                            )
                            or existing_env
                        )
                    task_info.runtime_env_id = int(existing_env["id"])
                    task_info.runtime_work_dir = str(existing_env["workspace_path"])
                    item.runtime_work_dir = str(existing_env["workspace_path"])
                    task_info.runtime_classification = str(existing_env.get("classification") or "light")
                    task_info.runtime_environment_kind = str(existing_env.get("environment_kind") or "dev_worktree")
                    heartbeat_task = asyncio.create_task(
                        _runtime_heartbeat_loop(
                            task_id,
                            task_info.runtime_env_id,
                            lambda: task_info.status,
                        )
                    )
                else:
                    classification = await runtime.classify_task(task_id=task_id, query_text=item.query_text)
                    task_info.runtime_classification = classification.classification
                    task_info.runtime_environment_kind = classification.environment_kind
                    runtime_capacity = contextlib.AsyncExitStack()
                    await runtime_capacity.__aenter__()
                    if classification.classification == "standard":
                        await runtime_capacity.enter_async_context(_standard_task_semaphore)
                    if classification.classification == "heavy":
                        await runtime_capacity.enter_async_context(_heavy_task_semaphore)
                    if classification.environment_kind == "dev_worktree_browser":
                        await runtime_capacity.enter_async_context(_browser_task_semaphore)
                    base_work_dir = _validate_work_dir(
                        item.scheduled_work_dir or context.user_data.get("work_dir"),
                        strict=item.is_scheduled_run,
                    )
                    env = await runtime.provision_environment(
                        task_id=task_id,
                        user_id=user_id,
                        chat_id=item.chat_id,
                        query_text=item.query_text,
                        base_work_dir=base_work_dir,
                        classification=classification,
                    )
                    if env is not None:
                        task_info.runtime_env_id = int(env["id"])
                        task_info.runtime_work_dir = str(env["workspace_path"])
                        item.runtime_work_dir = str(env["workspace_path"])
                        heartbeat_task = asyncio.create_task(
                            _runtime_heartbeat_loop(
                                task_id,
                                task_info.runtime_env_id,
                                lambda: task_info.status,
                            )
                        )
            task_info.status = "running"
            task_info.started_at = time.time()
            update_task_status(task_id, "running", started_at=datetime.now().isoformat())
            if RUNTIME_ENVIRONMENTS_ENABLED:
                await runtime.mark_phase(
                    task_id=task_id,
                    env_id=task_info.runtime_env_id,
                    phase="planning",
                    attempt=task_info.attempt,
                )
            log.info("task_started", task_id=task_id, attempt=task_info.attempt)
            audit.emit_task_lifecycle("task.started", user_id=user_id, task_id=task_id)
            execution_timeline.append(
                _make_timeline_item(
                    "task.started",
                    "Processamento iniciado",
                    status="info",
                    summary="A tarefa entrou em execução.",
                    details={"attempt": task_info.attempt},
                )
            )

            # Prepare context (budget check, model routing, etc.)
            try:
                lock = _get_worker_lock(user_id)
                async with lock:
                    ctx = await _prepare_query_context(context, item, user_id, task_id=task_id)
            except BudgetExceeded as e:
                task_info.status = "failed"
                task_info.error_message = str(e)
                task_info.completed_at = time.time()
                update_task_status(task_id, "failed", error_message=str(e), completed_at=datetime.now().isoformat())
                if item.update and item.update.message:
                    await item.update.message.reply_text(str(e))
                else:
                    await context.bot.send_message(chat_id=item.chat_id, text=str(e))
                if RUNTIME_ENVIRONMENTS_ENABLED:
                    await runtime.record_warning(
                        task_id=task_id,
                        warning_type="budget_exceeded",
                        message=str(e),
                    )
                    cycle_id = await runtime.record_loop_cycle(
                        task_id=task_id,
                        cycle_index=0,
                        phase="planning",
                        failure_fingerprint=_hash_text(str(e)),
                        outcome={"budget_exceeded": True},
                    )
                    await runtime.record_guardrail_hit(
                        task_id=task_id,
                        guardrail_type="budget_exceeded",
                        cycle_id=cycle_id,
                        details={"message": str(e)},
                    )
                    await runtime.finalize_task(task_id=task_id, success=False, error_message=str(e))
                log.info("task_failed", task_id=task_id, error="budget_exceeded")
                metrics.REQUESTS_TOTAL.labels(agent_id=_agent_id_label, status="failed").inc()
                audit.emit_task_lifecycle("task.failed", user_id=user_id, task_id=task_id, error="budget_exceeded")
                audit.emit(
                    audit.AuditEvent(
                        event_type="cost.budget_exceeded",
                        user_id=user_id,
                        task_id=task_id,
                        cost_usd=context.user_data.get("total_cost", 0.0),
                        details={"budget_limit": MAX_TOTAL_BUDGET_USD},
                    )
                )
                execution_timeline.append(
                    _make_timeline_item(
                        "task.failed",
                        "Orçamento excedido",
                        status="error",
                        summary="A execução foi interrompida antes de rodar o modelo.",
                        details={"error": str(e)},
                    )
                )
                trace_payload = _build_execution_trace_payload(
                    item=item,
                    task_info=task_info,
                    ctx=None,
                    run_result=None,
                    status="failed",
                    work_dir=context.user_data.get("work_dir"),
                    timeline=execution_timeline,
                    error_message=str(e),
                )
                audit.emit_execution_trace(
                    user_id=user_id,
                    task_id=task_id,
                    query_text=trace_payload["query_text"],
                    response_text=trace_payload["response_text"],
                    model=trace_payload["model"],
                    session_id=trace_payload["session_id"],
                    work_dir=trace_payload["work_dir"],
                    status="failed",
                    cost_usd=trace_payload["cost_usd"],
                    duration_ms=trace_payload["duration_ms"],
                    stop_reason=trace_payload["stop_reason"],
                    warnings=trace_payload["warnings"],
                    tool_uses=trace_payload["tool_uses"],
                    tools=trace_payload["tools"],
                    timeline=trace_payload["timeline"],
                    reasoning_summary=trace_payload["reasoning_summary"],
                    raw_artifacts=trace_payload["raw_artifacts"],
                    grounding=trace_payload["grounding"],
                    confidence_reports=trace_payload["confidence_reports"],
                    error_message=str(e),
                    attempt=task_info.attempt,
                    max_attempts=TASK_MAX_RETRY_ATTEMPTS,
                    user_context={"user_id": user_id, "chat_id": item.chat_id},
                )
                await _finalize_scheduled_run(
                    item=item,
                    ctx=ctx,
                    run_result=None,
                    task_id=task_id,
                    task_info=task_info,
                    context=context,
                    error_message=str(e),
                )
                return

            task_info.model = ctx.model
            ctx.runtime_env_id = task_info.runtime_env_id
            ctx.runtime_classification = task_info.runtime_classification or "light"
            ctx.runtime_environment_kind = task_info.runtime_environment_kind or "dev_worktree"
            update_task_status(
                task_id,
                "running",
                provider=ctx.provider,
                model=ctx.model,
                session_id=ctx.session_id,
                provider_session_id=ctx.provider_session_id,
            )
            _active_chat_ids.setdefault(user_id, set()).add(item.chat_id)
            query_start_time = time.time()

            max_attempts = TASK_MAX_RETRY_ATTEMPTS
            last_error: str | None = None
            last_retry_failure_fingerprint = ""
            repeated_retry_failure_count = 0

            for attempt in range(1, max_attempts + 1):
                task_info.attempt = attempt
                task_info.status = "executing"
                try:
                    if RUNTIME_ENVIRONMENTS_ENABLED:
                        await runtime.mark_phase(
                            task_id=task_id,
                            env_id=task_info.runtime_env_id,
                            phase="executing",
                            attempt=attempt,
                        )
                    run_result = await _process_task_item(ctx, item, user_id, item.chat_id, context, task_id)
                    task_info.model = run_result.model
                    if RUNTIME_ENVIRONMENTS_ENABLED:
                        task_root = Path(runtime.runtime_root) / "tasks" / str(task_id)
                        task_root.mkdir(parents=True, exist_ok=True)
                        runtime_terminal_path = str(run_result.runtime_terminal_path or "")
                        if not runtime_terminal_path.startswith(("kernel://", "kernel-stream://")):
                            raise RuntimeError("runtime terminal output requires a kernel-backed terminal path")
                        stdout_path = None
                        if run_result.runtime_terminal_id is None:
                            await runtime.register_terminal(
                                task_id=task_id,
                                terminal_kind="command",
                                label=f"{run_result.provider} attempt {attempt}",
                                path=str(stdout_path) if stdout_path is not None else runtime_terminal_path,
                            )

                    # Check if the result itself indicates a retryable error
                    if run_result.error and (
                        run_result.retryable
                        or (
                            run_result.result
                            and not run_result.error_kind
                            and is_retryable_provider_error(run_result.provider, run_result.result)
                        )
                    ):
                        raise _RetryableError(run_result.result)
                    if run_result.error:
                        if run_result.error_kind == "runtime_guardrail":
                            raise _RuntimeGuardrailError(run_result.result)
                        raise RuntimeError(run_result.result or run_result.error_kind or "provider execution failed")

                    # Success path
                    query_elapsed = time.time() - query_start_time
                    task_info.cost_usd = run_result.cost_usd
                    task_info.status = "validating"
                    if RUNTIME_ENVIRONMENTS_ENABLED:
                        await runtime.mark_phase(
                            task_id=task_id,
                            env_id=task_info.runtime_env_id,
                            phase="validating",
                            attempt=attempt,
                        )

                    had_write = any(step.get("metadata", {}).get("write") for step in run_result.tool_execution_trace)
                    final_response_text, _ = _compose_response_text(run_result, elapsed=query_elapsed)
                    final_status = "completed"
                    runtime_final_phase: str | None = None
                    response_override: str | None = None
                    try:
                        orchestration_service = _get_knowledge_orchestration_service()
                        (
                            ctx.grounded_answer,
                            ctx.answer_judgement,
                            ctx.answer_evaluation,
                            ctx.grounding_gate_decision,
                        ) = orchestration_service.evaluate_response(
                            response=final_response_text,
                            resolution=getattr(ctx, "knowledge_resolution", None),
                            had_write=had_write,
                            verified_before_finalize=ctx.verified_before_finalize,
                            required_verifications=tuple(
                                getattr(getattr(ctx, "effective_policy", None), "required_verifications", ())
                            ),
                            task_id=task_id,
                        )
                        ctx.last_action_plan = orchestration_service.build_plan_payload(
                            existing_plan=ctx.last_action_plan,
                            resolution=getattr(ctx, "knowledge_resolution", None),
                            grounded_answer=ctx.grounded_answer,
                            judgement=ctx.answer_judgement,
                        )
                        resolution = getattr(ctx, "knowledge_resolution", None)
                        if resolution is not None:
                            resolution.grounded_answer = ctx.grounded_answer
                            resolution.answer_judgement = ctx.answer_judgement
                            resolution.answer_evaluation = ctx.answer_evaluation
                        strategy_label = getattr(
                            getattr(getattr(ctx, "knowledge_resolution", None), "retrieval_strategy", None),
                            "value",
                            str(
                                getattr(getattr(ctx, "knowledge_resolution", None), "retrieval_strategy", "")
                                or "unknown"
                            ),
                        )
                        metrics.KNOWLEDGE_CITATION_COVERAGE.labels(
                            agent_id=(AGENT_ID or "default").lower(),
                            strategy=strategy_label,
                        ).observe(float(_answer_eval_value(ctx.answer_evaluation, "citation_coverage", 0.0) or 0.0))
                        if getattr(ctx, "answer_judgement", None) is not None:
                            metrics.KNOWLEDGE_CITATION_SPAN_PRECISION.labels(
                                agent_id=(AGENT_ID or "default").lower(),
                                strategy=strategy_label,
                            ).observe(float(getattr(ctx.answer_judgement, "citation_span_precision", 0.0) or 0.0))
                            metrics.KNOWLEDGE_CONTRADICTION_ESCAPE.labels(
                                agent_id=(AGENT_ID or "default").lower(),
                                strategy=strategy_label,
                                status=(
                                    "escaped"
                                    if float(getattr(ctx.answer_judgement, "contradiction_escape_rate", 0.0) or 0.0) > 0
                                    else "contained"
                                ),
                            ).inc()
                            metrics.KNOWLEDGE_JUDGE_OUTCOMES.labels(
                                agent_id=(AGENT_ID or "default").lower(),
                                status=str(getattr(ctx.answer_judgement, "status", "passed") or "passed"),
                            ).inc()
                        for warning in list(_answer_eval_value(ctx.answer_evaluation, "warnings", []) or []):
                            if warning not in run_result.warnings:
                                run_result.warnings.append(str(warning))
                        if getattr(ctx.grounding_gate_decision, "status", "passed") != "passed":
                            final_status = "needs_review"
                            runtime_final_phase = "needs_review_retained"
                            response_override = str(
                                getattr(ctx.grounding_gate_decision, "safe_response", "") or final_response_text
                            )
                            for reason in list(getattr(ctx.grounding_gate_decision, "reasons", []) or []):
                                warning = f"grounding_gate:{reason}"
                                if warning not in run_result.warnings:
                                    run_result.warnings.append(warning)
                    except Exception:
                        log.exception("knowledge_answer_evaluation_error")

                    delivered_response_text = response_override or final_response_text

                    await _record_execution_episode(
                        user_id=user_id,
                        task_id=task_id,
                        status=final_status,
                        ctx=ctx,
                        run_result=run_result,
                        human_override_delta=1 if ctx.human_approval_used else 0,
                    )

                    # Lock user_data writes to avoid races with concurrent tasks
                    lock = _get_worker_lock(user_id)
                    async with lock:
                        await _post_process(
                            user_id,
                            context,
                            run_result,
                            item.query_text,
                            ctx.work_dir,
                            ctx.model,
                            task_id=task_id,
                            ctx=ctx,
                            dry_run=ctx.dry_run,
                            cacheable=not ctx.artifact_dossiers,
                            final_status=final_status,
                            response_text_override=delivered_response_text,
                        )

                    await _send_response(
                        item.chat_id,
                        item.update,
                        context,
                        run_result,
                        ctx.work_dir,
                        ctx.agent_mode,
                        elapsed=query_elapsed,
                        model=run_result.model,
                        task_id=task_id,
                        ctx=ctx,
                        response_override=response_override,
                        include_tool_summary=response_override is None,
                    )

                    task_info.status = final_status
                    task_info.completed_at = time.time()
                    update_task_status(
                        task_id,
                        final_status,
                        cost_usd=run_result.cost_usd,
                        completed_at=datetime.now().isoformat(),
                        attempt=attempt,
                        session_id=run_result.session_id,
                        provider=run_result.provider,
                        model=run_result.model,
                        provider_session_id=run_result.provider_session_id,
                    )
                    log.info(
                        "task_finalized",
                        task_id=task_id,
                        status=final_status,
                        cost_usd=run_result.cost_usd,
                        elapsed_s=round(query_elapsed, 1),
                    )

                    # Metrics
                    duration_ms = query_elapsed * 1000
                    metrics.REQUESTS_TOTAL.labels(agent_id=_agent_id_label, status=final_status).inc()
                    metrics.REQUEST_DURATION.labels(
                        agent_id=_agent_id_label,
                        provider=run_result.provider,
                        model=run_result.model,
                    ).observe(query_elapsed)
                    if run_result.cost_usd > 0:
                        metrics.COST_PER_QUERY.labels(
                            agent_id=_agent_id_label,
                            provider=run_result.provider,
                            model=run_result.model,
                        ).observe(run_result.cost_usd)
                        metrics.COST_TOTAL.labels(
                            agent_id=_agent_id_label,
                            provider=run_result.provider,
                            model=run_result.model,
                        ).inc(run_result.cost_usd)
                    grounded_status = "grounded" if ctx.knowledge_hits else "ungrounded"
                    metrics.GROUNDED_ANSWERS.labels(agent_id=_agent_id_label, status=grounded_status).inc()
                    runbook_status = (
                        "hit"
                        if any(
                            hit.get("layer") == "approved_runbook"
                            for hit in _serialize_knowledge_hits(ctx.knowledge_hits)
                        )
                        else "miss"
                    )
                    metrics.RUNBOOK_HITS.labels(
                        agent_id=_agent_id_label,
                        task_kind=ctx.task_kind,
                        status=runbook_status,
                    ).inc()
                    metrics.AUTONOMY_TIER_DISTRIBUTION.labels(
                        agent_id=_agent_id_label,
                        task_kind=ctx.task_kind,
                        tier=getattr(getattr(ctx.effective_policy, "autonomy_tier", None), "value", "unknown"),
                    ).inc()
                    if any(hit.get("freshness") == "stale" for hit in _serialize_knowledge_hits(ctx.knowledge_hits)):
                        stale_layers = {
                            str(hit.get("layer") or "unknown")
                            for hit in _serialize_knowledge_hits(ctx.knowledge_hits)
                            if hit.get("freshness") == "stale"
                        }
                        for layer in stale_layers:
                            metrics.STALE_SOURCE_USAGE.labels(agent_id=_agent_id_label, layer=layer).inc()
                    if any(step.get("metadata", {}).get("write") for step in run_result.tool_execution_trace):
                        verification_status = "verified" if ctx.verified_before_finalize else "missing"
                        metrics.VERIFICATION_BEFORE_FINALIZE.labels(
                            agent_id=_agent_id_label,
                            task_kind=ctx.task_kind,
                            status=verification_status,
                        ).inc()
                    # Audit
                    audit.emit_task_lifecycle(
                        "task.completed" if final_status == "completed" else "task.needs_review",
                        user_id=user_id,
                        task_id=task_id,
                        cost_usd=run_result.cost_usd,
                        duration_ms=duration_ms,
                        model=run_result.model,
                        attempt=attempt,
                    )
                    if run_result.cost_usd > 0:
                        audit.emit_cost(
                            user_id=user_id,
                            task_id=task_id,
                            cost_usd=run_result.cost_usd,
                            model=run_result.model,
                        )
                    success_timeline = execution_timeline + _tool_steps_to_timeline(run_result.tool_execution_trace)
                    success_timeline.append(
                        _make_timeline_item(
                            "task.completed" if final_status == "completed" else "task.needs_review",
                            "Execucao concluida" if final_status == "completed" else "Encaminhada para revisao",
                            status="success" if final_status == "completed" else "warning",
                            summary=(
                                "A resposta final foi enviada ao usuario."
                                if final_status == "completed"
                                else "A resposta foi bloqueada pelo grounding gate e encaminhada para revisao."
                            ),
                            details={
                                "attempt": attempt,
                                "stop_reason": run_result.stop_reason,
                                "final_status": final_status,
                            },
                        )
                    )
                    trace_payload = _build_execution_trace_payload(
                        item=item,
                        task_info=task_info,
                        ctx=ctx,
                        run_result=run_result,
                        status=final_status,
                        work_dir=ctx.work_dir,
                        timeline=success_timeline,
                        response_text_override=delivered_response_text,
                    )
                    audit.emit_execution_trace(
                        user_id=user_id,
                        task_id=task_id,
                        query_text=trace_payload["query_text"],
                        response_text=trace_payload["response_text"],
                        model=trace_payload["model"],
                        session_id=trace_payload["session_id"],
                        work_dir=trace_payload["work_dir"],
                        status=final_status,
                        cost_usd=trace_payload["cost_usd"],
                        duration_ms=trace_payload["duration_ms"],
                        stop_reason=trace_payload["stop_reason"],
                        warnings=trace_payload["warnings"],
                        tool_uses=trace_payload["tool_uses"],
                        tools=trace_payload["tools"],
                        timeline=trace_payload["timeline"],
                        reasoning_summary=trace_payload["reasoning_summary"],
                        raw_artifacts=trace_payload["raw_artifacts"],
                        grounding=trace_payload["grounding"],
                        confidence_reports=trace_payload["confidence_reports"],
                        attempt=attempt,
                        max_attempts=TASK_MAX_RETRY_ATTEMPTS,
                        user_context={"user_id": user_id, "chat_id": item.chat_id},
                    )
                    if RUNTIME_ENVIRONMENTS_ENABLED:
                        await runtime.finalize_task(
                            task_id=task_id,
                            success=final_status == "completed",
                            summary={
                                "provider": run_result.provider,
                                "model": run_result.model,
                                "cost_usd": run_result.cost_usd,
                                "stop_reason": run_result.stop_reason,
                                "tool_count": len(run_result.tool_execution_trace),
                                "final_status": final_status,
                            },
                            final_phase=runtime_final_phase,
                        )
                    await _finalize_scheduled_run(
                        item=item,
                        ctx=ctx,
                        run_result=run_result,
                        task_id=task_id,
                        task_info=task_info,
                        context=context,
                        duration_ms=duration_ms,
                    )
                    asyncio.create_task(
                        _record_procedural_memory(
                            query_text=item.query_text,
                            user_id=user_id,
                            task_id=task_id,
                            source_episode_id=getattr(ctx, "execution_episode_id", None),
                            status=final_status,
                            ctx=ctx,
                            run_result=run_result,
                            error_message=(
                                "; ".join(getattr(ctx.grounding_gate_decision, "reasons", []) or [])
                                if final_status != "completed"
                                else None
                            ),
                        )
                    )
                    return

                except _RetryableError as e:
                    last_error = str(e)
                    failure_fingerprint = _hash_text(last_error)
                    repeated_retry_failure_count = (
                        repeated_retry_failure_count + 1 if failure_fingerprint == last_retry_failure_fingerprint else 1
                    )
                    last_retry_failure_fingerprint = failure_fingerprint
                    if RUNTIME_ENVIRONMENTS_ENABLED and task_info.runtime_env_id is not None:
                        cycle_id = await runtime.record_loop_cycle(
                            task_id=task_id,
                            cycle_index=attempt,
                            phase="executing",
                            failure_fingerprint=failure_fingerprint,
                            outcome={"retryable_error": last_error, "attempt": attempt},
                        )
                        if repeated_retry_failure_count >= 3:
                            await runtime.record_guardrail_hit(
                                task_id=task_id,
                                guardrail_type="repeated_failure",
                                cycle_id=cycle_id,
                                details={"attempt": attempt, "failure_fingerprint": failure_fingerprint},
                            )
                            await runtime.record_warning(
                                task_id=task_id,
                                warning_type="repeated_failure",
                                message="A mesma falha se repetiu em tentativas consecutivas.",
                                details={"attempt": attempt, "failure_fingerprint": failure_fingerprint},
                            )
                            await runtime.pause_environment(
                                task_id=task_id,
                                reason="Guardrail do runtime: a mesma falha se repetiu em tentativas consecutivas.",
                            )
                            raise _RuntimeGuardrailError(
                                "Guardrail do runtime acionado: a mesma falha se repetiu em tentativas consecutivas."
                            ) from e
                    if attempt < max_attempts:
                        delay = min(TASK_RETRY_BASE_DELAY * (4 ** (attempt - 1)), TASK_RETRY_MAX_DELAY)
                        task_info.status = "retrying"
                        if RUNTIME_ENVIRONMENTS_ENABLED:
                            await runtime.events.publish(
                                task_id=task_id,
                                env_id=task_info.runtime_env_id,
                                attempt=attempt,
                                phase="executing",
                                event_type="retry.scheduled",
                                severity="warning",
                                payload={"error": last_error, "attempt": attempt, "delay_seconds": delay},
                            )
                        update_task_status(
                            task_id,
                            "retrying",
                            attempt=attempt,
                            error_message=last_error,
                            provider=run_result.provider if run_result else ctx.provider,
                            model=run_result.model if run_result else ctx.model,
                            session_id=run_result.session_id if run_result else ctx.session_id,
                            provider_session_id=(
                                run_result.provider_session_id if run_result else ctx.provider_session_id
                            ),
                        )
                        log.warning(
                            "task_retrying",
                            task_id=task_id,
                            attempt=attempt,
                            delay=delay,
                            error=last_error,
                        )
                        metrics.REQUESTS_TOTAL.labels(agent_id=_agent_id_label, status="retried").inc()
                        audit.emit_task_lifecycle(
                            "task.retried",
                            user_id=user_id,
                            task_id=task_id,
                            attempt=attempt,
                            error=last_error,
                        )
                        execution_timeline.append(
                            _make_timeline_item(
                                "task.retried",
                                "Nova tentativa agendada",
                                status="warning",
                                summary=f"A tentativa {attempt} falhou e será repetida em {delay}s.",
                                details={"attempt": attempt, "delay_seconds": delay, "error": last_error},
                            )
                        )
                        await asyncio.sleep(delay)
                    else:
                        break

            # All retries exhausted
            query_elapsed = time.time() - query_start_time
            task_info.status = "failed"
            task_info.error_message = last_error
            task_info.completed_at = time.time()
            update_task_status(
                task_id,
                "failed",
                error_message=last_error,
                completed_at=datetime.now().isoformat(),
                attempt=max_attempts,
                provider=run_result.provider if run_result else ctx.provider,
                model=run_result.model if run_result else ctx.model,
                session_id=run_result.session_id if run_result else ctx.session_id,
                provider_session_id=run_result.provider_session_id if run_result else ctx.provider_session_id,
            )
            log.warning("task_failed", task_id=task_id, error=last_error, attempts=max_attempts)
            metrics.REQUESTS_TOTAL.labels(agent_id=_agent_id_label, status="failed").inc()
            metrics.AUTONOMY_TIER_DISTRIBUTION.labels(
                agent_id=_agent_id_label,
                task_kind=ctx.task_kind,
                tier=getattr(getattr(ctx.effective_policy, "autonomy_tier", None), "value", "unknown"),
            ).inc()
            if ctx.task_kind == "deploy":
                metrics.ROLLBACK_NEEDED.labels(agent_id=_agent_id_label, task_kind=ctx.task_kind).inc()
            audit.emit_task_lifecycle(
                "task.failed",
                user_id=user_id,
                task_id=task_id,
                error=last_error,
                attempts=max_attempts,
                duration_ms=query_elapsed * 1000,
            )
            failed_timeline = execution_timeline + _tool_steps_to_timeline(
                run_result.tool_execution_trace if run_result else []
            )
            failed_timeline.append(
                _make_timeline_item(
                    "task.failed",
                    "Execução falhou",
                    status="error",
                    summary="Todas as tentativas foram consumidas sem sucesso.",
                    details={"attempts": max_attempts, "error": last_error},
                )
            )

            dlq_id = dlq_insert(
                task_id=task_id,
                user_id=user_id,
                chat_id=item.chat_id,
                query_text=item.query_text,
                error_message=last_error,
                error_class="RetryableError",
                attempt_count=max_attempts,
                model=task_info.model,
                original_created_at=datetime.fromtimestamp(task_info.created_at).isoformat(),
            )
            audit.emit_task_lifecycle("task.dead_letter", user_id=user_id, task_id=task_id, error=last_error)
            trace_payload = _build_execution_trace_payload(
                item=item,
                task_info=task_info,
                ctx=ctx,
                run_result=run_result,
                status="failed",
                work_dir=ctx.work_dir,
                timeline=failed_timeline,
                error_message=last_error,
            )
            audit.emit_execution_trace(
                user_id=user_id,
                task_id=task_id,
                query_text=trace_payload["query_text"],
                response_text=trace_payload["response_text"],
                model=trace_payload["model"],
                session_id=trace_payload["session_id"],
                work_dir=trace_payload["work_dir"],
                status="failed",
                cost_usd=trace_payload["cost_usd"],
                duration_ms=trace_payload["duration_ms"],
                stop_reason=trace_payload["stop_reason"],
                warnings=trace_payload["warnings"],
                tool_uses=trace_payload["tool_uses"],
                tools=trace_payload["tools"],
                timeline=trace_payload["timeline"],
                reasoning_summary=trace_payload["reasoning_summary"],
                raw_artifacts=trace_payload["raw_artifacts"],
                grounding=trace_payload["grounding"],
                confidence_reports=trace_payload["confidence_reports"],
                error_message=last_error,
                attempt=max_attempts,
                max_attempts=TASK_MAX_RETRY_ATTEMPTS,
                user_context={"user_id": user_id, "chat_id": item.chat_id},
            )
            if RUNTIME_ENVIRONMENTS_ENABLED:
                cycle_id = await runtime.record_loop_cycle(
                    task_id=task_id,
                    cycle_index=max_attempts,
                    phase="executing",
                    failure_fingerprint=_hash_text(last_error or "retry_exhausted"),
                    outcome={"retry_exhausted": True, "attempts": max_attempts},
                )
                await runtime.record_guardrail_hit(
                    task_id=task_id,
                    guardrail_type="retry_exhausted",
                    cycle_id=cycle_id,
                    details={"attempts": max_attempts},
                )
                await runtime.finalize_task(
                    task_id=task_id,
                    success=False,
                    error_message=last_error,
                    summary={
                        "provider": run_result.provider if run_result else ctx.provider,
                        "model": run_result.model if run_result else ctx.model,
                        "attempts": max_attempts,
                    },
                )
            await _record_execution_episode(
                user_id=user_id,
                task_id=task_id,
                status="failed",
                ctx=ctx,
                run_result=run_result,
                human_override_delta=1 if ctx.human_approval_used else 0,
            )
            asyncio.create_task(
                _record_procedural_memory(
                    query_text=item.query_text,
                    user_id=user_id,
                    task_id=task_id,
                    source_episode_id=getattr(ctx, "execution_episode_id", None),
                    status="failed",
                    ctx=ctx,
                    run_result=run_result,
                    error_message=last_error,
                )
            )
            await _finalize_scheduled_run(
                item=item,
                ctx=ctx,
                run_result=run_result,
                task_id=task_id,
                task_info=task_info,
                context=context,
                error_message=last_error,
                dlq_id=dlq_id,
                duration_ms=query_elapsed * 1000,
            )
            await _send_task_error(task_info, last_error or "unknown error", context, item)

    except _RuntimeGuardrailError as e:
        error_str = str(e)
        task_info.status = "failed"
        task_info.error_message = error_str
        task_info.completed_at = time.time()
        update_task_status(task_id, "failed", error_message=error_str, completed_at=datetime.now().isoformat())
        if item:
            await _finalize_scheduled_run(
                item=item,
                ctx=ctx,
                run_result=run_result,
                task_id=task_id,
                task_info=task_info,
                context=context,
                error_message=error_str,
            )
        if RUNTIME_ENVIRONMENTS_ENABLED:
            await runtime.finalize_task(task_id=task_id, success=False, error_message=error_str)
        await _send_task_error(task_info, error_str, context, item)
    except asyncio.CancelledError:
        cancellation_reason = task_info.error_message or "Cancelled by scheduler control."
        task_info.status = "cancelled"
        task_info.completed_at = time.time()
        update_task_status(
            task_id,
            "cancelled",
            error_message=cancellation_reason,
            completed_at=datetime.now().isoformat(),
        )
        if RUNTIME_ENVIRONMENTS_ENABLED:
            await runtime.finalize_task(
                task_id=task_id,
                success=False,
                error_message=cancellation_reason,
                summary={"cancelled": True},
                final_phase="cancelled_retained",
            )
        if item:
            await _finalize_scheduled_run(
                item=item,
                ctx=ctx,
                run_result=run_result,
                task_id=task_id,
                task_info=task_info,
                context=context,
                error_message=cancellation_reason,
            )
        raise
    except Exception as e:
        error_str = str(e)
        task_info.status = "failed"
        task_info.error_message = error_str
        task_info.completed_at = time.time()
        update_task_status(task_id, "failed", error_message=error_str, completed_at=datetime.now().isoformat())
        if RUNTIME_ENVIRONMENTS_ENABLED:
            await runtime.record_warning(
                task_id=task_id,
                warning_type="unexpected_exception",
                message=error_str,
            )
        log.exception("task_error", task_id=task_id, error=error_str)
        metrics.REQUESTS_TOTAL.labels(agent_id=_agent_id_label, status="failed").inc()
        if ctx and ctx.task_kind == "deploy":
            metrics.ROLLBACK_NEEDED.labels(agent_id=_agent_id_label, task_kind=ctx.task_kind).inc()
        audit.emit_task_lifecycle("task.failed", user_id=user_id, task_id=task_id, error=error_str)
        exception_timeline = execution_timeline + _tool_steps_to_timeline(
            run_result.tool_execution_trace if run_result else []
        )
        exception_timeline.append(
            _make_timeline_item(
                "task.failed",
                "Falha inesperada",
                status="error",
                summary="A execução encerrou por exceção fora do fluxo de retry.",
                details={"error": error_str},
            )
        )
        if item:
            trace_payload = _build_execution_trace_payload(
                item=item,
                task_info=task_info,
                ctx=ctx,
                run_result=run_result,
                status="failed",
                work_dir=ctx.work_dir if ctx else context.user_data.get("work_dir"),
                timeline=exception_timeline,
                error_message=error_str,
            )
            audit.emit_execution_trace(
                user_id=user_id,
                task_id=task_id,
                query_text=trace_payload["query_text"],
                response_text=trace_payload["response_text"],
                model=trace_payload["model"],
                session_id=trace_payload["session_id"],
                work_dir=trace_payload["work_dir"],
                status="failed",
                cost_usd=trace_payload["cost_usd"],
                duration_ms=trace_payload["duration_ms"],
                stop_reason=trace_payload["stop_reason"],
                warnings=trace_payload["warnings"],
                tool_uses=trace_payload["tool_uses"],
                tools=trace_payload["tools"],
                timeline=trace_payload["timeline"],
                reasoning_summary=trace_payload["reasoning_summary"],
                raw_artifacts=trace_payload["raw_artifacts"],
                grounding=trace_payload["grounding"],
                confidence_reports=trace_payload["confidence_reports"],
                error_message=error_str,
                attempt=task_info.attempt,
                max_attempts=TASK_MAX_RETRY_ATTEMPTS,
                user_context={"user_id": user_id, "chat_id": item.chat_id},
            )
            await _record_execution_episode(
                user_id=user_id,
                task_id=task_id,
                status="failed",
                ctx=ctx,
                run_result=run_result,
                human_override_delta=1 if (ctx and ctx.human_approval_used) else 0,
            )
            asyncio.create_task(
                _record_procedural_memory(
                    query_text=item.query_text,
                    user_id=user_id,
                    task_id=task_id,
                    source_episode_id=getattr(ctx, "execution_episode_id", None) if ctx else None,
                    status="failed",
                    ctx=ctx,
                    run_result=run_result,
                    error_message=error_str,
                )
            )
            await _finalize_scheduled_run(
                item=item,
                ctx=ctx,
                run_result=run_result,
                task_id=task_id,
                task_info=task_info,
                context=context,
                error_message=error_str,
            )
        if RUNTIME_ENVIRONMENTS_ENABLED:
            await runtime.finalize_task(task_id=task_id, success=False, error_message=error_str)
        await _send_task_error(task_info, error_str, context, item)
    finally:
        if heartbeat_task:
            heartbeat_task.cancel()
        if runtime_capacity is not None:
            await runtime_capacity.aclose()
        metrics.ACTIVE_TASKS.labels(agent_id=_agent_id_label).dec()
        chat_ids = _active_chat_ids.get(user_id)
        if chat_ids and item:
            chat_ids.discard(item.chat_id)
            if not chat_ids:
                _active_chat_ids.pop(user_id, None)
        if item:
            untrack_images(item.image_paths)
        if ctx and ctx.temp_paths:
            from koda.services.artifact_ingestion import cleanup_artifact_temp_paths

            cleanup_artifact_temp_paths(ctx.temp_paths)
        _unregister_task(task_info)


async def _process_queue(user_id: int, context: BotContext) -> None:
    """Dispatcher that dequeues items and spawns parallel task executors."""
    queue = _user_queues[user_id]
    ctx_user_id.set(user_id)
    spawned_tasks: list[asyncio.Task] = []

    try:
        while True:
            # Drain all currently queued items
            while not queue.empty():
                raw_item = await queue.get()

                # Check if task_id was already assigned in enqueue()
                task_id = None
                if isinstance(raw_item, tuple) and len(raw_item) == 5:
                    task_id = raw_item[4]
                elif isinstance(raw_item, tuple) and len(raw_item) == 4:
                    task_id = raw_item[3]
                elif isinstance(raw_item, dict):
                    task_id = raw_item.get("_task_id")

                # Skip cancelled tasks
                if task_id is not None and task_id in _cancelled_task_ids:
                    _cancelled_task_ids.discard(task_id)
                    queue.task_done()
                    continue

                # Determine chat_id and query_text for task creation
                if isinstance(raw_item, dict):
                    chat_id = raw_item.get("chat_id", 0)
                    query_text = raw_item.get("query_text", "continuation")
                    task_provider = raw_item.get("provider") or context.user_data.get("provider")
                else:
                    chat_id = raw_item[0].effective_chat.id
                    query_text = raw_item[1]
                    task_provider = context.user_data.get("provider")

                if task_id is None:
                    provider_sessions = context.user_data.get("provider_sessions", {})
                    task_id = create_task(
                        user_id,
                        chat_id,
                        query_text,
                        provider=task_provider,
                        model=get_provider_model(context.user_data, task_provider),
                        session_id=context.user_data.get("session_id"),
                        provider_session_id=provider_sessions.get(task_provider),
                        max_attempts=TASK_MAX_RETRY_ATTEMPTS,
                    )
                    from koda.services import audit as _audit

                    _audit.emit_task_lifecycle("task.created", user_id=user_id, task_id=task_id)
                    if RUNTIME_ENVIRONMENTS_ENABLED:
                        from koda.services.runtime import get_runtime_controller

                        await get_runtime_controller().register_queued_task(
                            task_id=task_id,
                            user_id=user_id,
                            chat_id=chat_id,
                            query_text=query_text,
                        )

                task_info = TaskInfo(
                    task_id=task_id,
                    user_id=user_id,
                    chat_id=chat_id,
                    query_text=query_text,
                )
                _register_task(task_info)
                log.info("task_created", task_id=task_id, user_id=user_id, query_preview=query_text[:60])

                t = asyncio.create_task(_execute_single_task(raw_item, user_id, context, task_id, task_info))
                task_info.asyncio_task = t
                spawned_tasks.append(t)

                queue.task_done()

            # Wait for spawned tasks, then re-check queue for items added during execution
            if spawned_tasks:
                await asyncio.gather(*spawned_tasks, return_exceptions=True)
                spawned_tasks.clear()
                if not queue.empty():
                    continue  # new items arrived while tasks were running
            break
    finally:
        _queue_workers.pop(user_id, None)


async def _send_typing(chat_id: int, context: BotContext) -> None:
    """Send typing action periodically."""
    try:
        while True:
            from telegram.constants import ChatAction

            with contextlib.suppress(Exception):
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            await asyncio.sleep(5)
    except asyncio.CancelledError:
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_runtime_context(application: Any, user_id: int, *, bot_override: Any | None = None) -> Any:
    """Build a lightweight context object for background scheduled runs."""
    from types import SimpleNamespace

    user_data = application.user_data.setdefault(user_id, {})
    return SimpleNamespace(
        application=application,
        bot=bot_override or application.bot,
        bot_data=getattr(application, "bot_data", {}),
        job_queue=getattr(application, "job_queue", None),
        user_data=user_data,
    )


async def enqueue(
    user_id: int,
    update: Update,
    context: BotContext,
    query_text: str,
    image_paths: list[str] | None = None,
    artifact_bundle: Any | None = None,
) -> int | None:
    """Enqueue a query and ensure a worker is running. Returns task_id."""
    if _shutting_down:
        await update.message.reply_text("Agent is shutting down. Please try again in a moment.")
        return None

    from koda.services import audit, metrics
    from koda.services.runtime import get_runtime_controller

    chat_id = update.effective_chat.id
    provider = context.user_data.get("provider")
    provider_sessions = context.user_data.get("provider_sessions", {})
    task_id = create_task(
        user_id,
        chat_id,
        query_text,
        provider=provider,
        model=get_provider_model(context.user_data, provider),
        session_id=context.user_data.get("session_id"),
        provider_session_id=provider_sessions.get(provider),
        max_attempts=TASK_MAX_RETRY_ATTEMPTS,
    )
    audit.emit_task_lifecycle("task.created", user_id=user_id, task_id=task_id)
    if RUNTIME_ENVIRONMENTS_ENABLED:
        await get_runtime_controller().register_queued_task(
            task_id=task_id,
            user_id=user_id,
            chat_id=chat_id,
            query_text=query_text,
        )

    queue = get_queue(user_id)
    queue_size = queue.qsize()

    await queue.put((update, query_text, image_paths, artifact_bundle, task_id))
    metrics.QUEUE_DEPTH.labels(agent_id=_agent_id_label).set(queue.qsize())
    audit.emit_task_lifecycle("task.queued", user_id=user_id, task_id=task_id)

    if queue_size > 0:
        await update.message.reply_text(f"Enfileirado (#{task_id}, {queue_size} na frente).")

    # Use lock to prevent race condition on worker spawn
    await _ensure_queue_worker(user_id, context)

    return cast(int | None, task_id)


async def enqueue_scheduled_run(
    *,
    user_id: int,
    chat_id: int,
    context: BotContext,
    query_text: str,
    scheduled_job_id: int,
    scheduled_run_id: int,
    dry_run: bool,
    provider: str | None,
    model: str | None,
    work_dir: str | None,
    session_id: str | None,
    trigger_reason: str,
) -> int:
    """Enqueue a scheduled job occurrence into the shared runtime queue."""
    from koda.services import audit, metrics
    from koda.services.runtime import get_runtime_controller
    from koda.utils.command_helpers import init_user_data

    init_user_data(context.user_data, user_id=user_id)
    resolved_provider = normalize_provider(provider or context.user_data.get("provider"))
    task_id = create_task(
        user_id,
        chat_id,
        query_text,
        provider=resolved_provider,
        model=model or get_provider_model(context.user_data, resolved_provider),
        session_id=session_id or context.user_data.get("session_id"),
        provider_session_id=context.user_data.get("provider_sessions", {}).get(resolved_provider),
        work_dir=work_dir or context.user_data.get("work_dir"),
        max_attempts=TASK_MAX_RETRY_ATTEMPTS,
    )
    if RUNTIME_ENVIRONMENTS_ENABLED:
        await get_runtime_controller().register_queued_task(
            task_id=task_id,
            user_id=user_id,
            chat_id=chat_id,
            query_text=query_text,
        )
    raw_item = {
        "_scheduled_run": True,
        "_task_id": task_id,
        "chat_id": chat_id,
        "query_text": query_text,
        "scheduled_job_id": scheduled_job_id,
        "scheduled_run_id": scheduled_run_id,
        "dry_run": dry_run,
        "provider": resolved_provider,
        "model": model,
        "work_dir": work_dir,
        "session_id": session_id,
        "trigger_reason": trigger_reason,
    }
    queue = get_queue(user_id)
    await queue.put(raw_item)
    metrics.QUEUE_DEPTH.labels(agent_id=_agent_id_label).set(queue.qsize())
    audit.emit_task_lifecycle(
        "task.queued",
        user_id=user_id,
        task_id=task_id,
        scheduled_job_id=scheduled_job_id,
        scheduled_run_id=scheduled_run_id,
    )
    await _ensure_queue_worker(user_id, context)
    return cast(int, task_id)


async def enqueue_continuation(
    user_id: int,
    chat_id: int,
    context: BotContext,
) -> None:
    """Enqueue a supervised-mode continuation (resume session for 1 more turn).

    Puts a special continuation dict into the queue to distinguish from normal items.
    Session ID is read from user_data["_supervised_session_id"].
    """
    session_id = context.user_data.get("_supervised_session_id")
    if not session_id:
        return
    queue = get_queue(user_id)
    await queue.put(
        {
            "_continuation": True,
            "chat_id": chat_id,
            "session_id": session_id,
            "provider": context.user_data.get("_supervised_provider"),
        }
    )

    await _ensure_queue_worker(user_id, context)


async def initiate_shutdown(telegram_bot: TelegramBotLike) -> None:
    """Gracefully shut down: stop accepting queries, notify active users, wait for workers."""
    global _shutting_down  # noqa: PLW0603
    _shutting_down = True
    log.info("shutdown_initiated", active_users=len(_active_chat_ids))

    # Notify users with active queries
    for _uid, chat_ids in list(_active_chat_ids.items()):
        for chat_id in chat_ids:
            with contextlib.suppress(Exception):
                await telegram_bot.send_message(
                    chat_id=chat_id,
                    text="⚠️ Agent is restarting. Your current query will complete if possible.",
                )

    # Wait for active workers (max 30s)
    active_workers = [t for t in _queue_workers.values() if not t.done()]
    if active_workers:
        log.info("shutdown_waiting_for_workers", count=len(active_workers))
        await asyncio.wait(active_workers, timeout=30)


async def enqueue_link_analysis(
    user_id: int,
    chat_id: int,
    context: BotContext,
    prompt: str,
) -> None:
    """Enqueue a link analysis prompt for provider processing."""
    queue = get_queue(user_id)
    await queue.put({"_link_analysis": True, "chat_id": chat_id, "query_text": prompt})

    lock = _get_worker_lock(user_id)
    async with lock:
        if user_id not in _queue_workers or _queue_workers[user_id].done():
            _queue_workers[user_id] = asyncio.create_task(_process_queue(user_id, context))
