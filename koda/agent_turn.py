"""Versioned AgentTurn contract types for runtime snapshots.

This module intentionally does not import ``queue_manager``.  The adapter
helpers accept duck-typed objects so the current runtime can snapshot its turn
input/output shape without adding a dependency cycle.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Self, cast

AGENT_TURN_CONTRACT_VERSION = "agent_turn.v1"

AgentTurnRuntimeState = Literal[
    "queued",
    "running",
    "retrying",
    "stalled",
    "degraded",
    "failed",
    "cancelled",
    "completed",
]
AgentTurnErrorCategory = Literal[
    "configuration",
    "permission",
    "policy_denied",
    "dependency_unavailable",
    "timeout",
    "validation",
    "retryable",
    "non_retryable",
    "internal",
]
AgentTurnEventSeverity = Literal["debug", "info", "warning", "error"]
CompiledContextBlockStatus = Literal["included", "dropped"]

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonDict = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class CompiledContextBlock:
    """One prompt/context block as selected by the prompt budget planner."""

    contract_version: str = AGENT_TURN_CONTRACT_VERSION
    block_id: str = ""
    category: str = ""
    status: CompiledContextBlockStatus = "included"
    priority: int = 100
    token_estimate: int = 0
    final_token_estimate: int | None = None
    compression_strategy: str = ""
    drop_policy: str = ""
    compressed: bool = False
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return _dataclass_to_json_dict(self)

    def to_json(self) -> str:
        return _to_json(self.to_dict())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            contract_version=_as_str(data.get("contract_version"), AGENT_TURN_CONTRACT_VERSION),
            block_id=_as_str(data.get("block_id")),
            category=_as_str(data.get("category")),
            status=cast(CompiledContextBlockStatus, _as_str(data.get("status"), "included")),
            priority=_as_int(data.get("priority"), 100),
            token_estimate=_as_int(data.get("token_estimate"), 0),
            final_token_estimate=_as_optional_int(data.get("final_token_estimate")),
            compression_strategy=_as_str(data.get("compression_strategy")),
            drop_policy=_as_str(data.get("drop_policy")),
            compressed=bool(data.get("compressed", False)),
            reason=_as_optional_str(data.get("reason")),
            metadata=_as_plain_dict(data.get("metadata")),
        )

    @classmethod
    def from_json(cls, payload: str) -> Self:
        return cls.from_dict(_loads_json_dict(payload))


@dataclass(frozen=True, slots=True)
class AgentTurnEvent:
    """Versioned event envelope emitted during an agent turn."""

    contract_version: str = AGENT_TURN_CONTRACT_VERSION
    event_type: str = ""
    severity: AgentTurnEventSeverity = "info"
    message: str = ""
    timestamp: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    correlation: dict[str, Any] = field(default_factory=dict)
    run_graph_node_id: str | None = None

    def to_dict(self) -> JsonDict:
        return _dataclass_to_json_dict(self)

    def to_json(self) -> str:
        return _to_json(self.to_dict())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            contract_version=_as_str(data.get("contract_version"), AGENT_TURN_CONTRACT_VERSION),
            event_type=_as_str(data.get("event_type")),
            severity=cast(AgentTurnEventSeverity, _as_str(data.get("severity"), "info")),
            message=_as_str(data.get("message")),
            timestamp=_as_optional_str(data.get("timestamp")),
            payload=_as_plain_dict(data.get("payload")),
            correlation=_as_plain_dict(data.get("correlation")),
            run_graph_node_id=_as_optional_str(data.get("run_graph_node_id")),
        )

    @classmethod
    def from_json(cls, payload: str) -> Self:
        return cls.from_dict(_loads_json_dict(payload))


@dataclass(frozen=True, slots=True)
class AgentTurnError:
    """User-facing runtime error envelope for an agent turn."""

    contract_version: str = AGENT_TURN_CONTRACT_VERSION
    code: str = "runtime.internal"
    category: AgentTurnErrorCategory | str = "internal"
    message: str = ""
    retryable: bool = False
    user_action: str = "Inspect the trace and retry after resolving the root cause."
    trace_id: str | None = None
    run_graph_node_id: str | None = None
    detail_ref: str | None = None
    provider: str | None = None
    error_kind: str | None = None

    def to_dict(self) -> JsonDict:
        return _dataclass_to_json_dict(self)

    def to_json(self) -> str:
        return _to_json(self.to_dict())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            contract_version=_as_str(data.get("contract_version"), AGENT_TURN_CONTRACT_VERSION),
            code=_as_str(data.get("code"), "runtime.internal"),
            category=_as_str(data.get("category"), "internal"),
            message=_as_str(data.get("message")),
            retryable=bool(data.get("retryable", False)),
            user_action=_as_str(
                data.get("user_action"),
                "Inspect the trace and retry after resolving the root cause.",
            ),
            trace_id=_as_optional_str(data.get("trace_id")),
            run_graph_node_id=_as_optional_str(data.get("run_graph_node_id")),
            detail_ref=_as_optional_str(data.get("detail_ref")),
            provider=_as_optional_str(data.get("provider")),
            error_kind=_as_optional_str(data.get("error_kind")),
        )

    @classmethod
    def from_json(cls, payload: str) -> Self:
        return cls.from_dict(_loads_json_dict(payload))


@dataclass(frozen=True, slots=True)
class AgentTurnInput:
    """Resolved provider/runtime input for one agent turn."""

    contract_version: str = AGENT_TURN_CONTRACT_VERSION
    task_id: int | None = None
    provider: str = ""
    model: str = ""
    session_id: str = ""
    provider_session_id: str | None = None
    work_dir: str = ""
    compiled_prompt: str = ""
    agent_mode: str = ""
    permission_mode: str = ""
    max_turns: int = 0
    turn_mode: str = "new_turn"
    resume_requested: bool = False
    supports_native_resume: bool = True
    provider_available: bool = True
    dry_run: bool = False
    scheduled_job_id: int | None = None
    scheduled_run_id: int | None = None
    runtime_env_id: int | None = None
    runtime_classification: str = "light"
    runtime_environment_kind: str = "dev_worktree"
    task_kind: str = "general"
    warnings: tuple[str, ...] = ()
    fallback_chain: tuple[str, ...] = ()
    compiled_context_blocks: tuple[CompiledContextBlock, ...] = ()
    prompt_budget: dict[str, Any] = field(default_factory=dict)
    knowledge_hit_count: int = 0
    memory_trust_score: float = 0.0
    confidence_reports: tuple[dict[str, Any], ...] = ()
    effective_policy: dict[str, Any] | None = None
    ungrounded_operationally: bool = False
    stale_sources_present: bool = False
    verified_before_finalize: bool = False
    human_approval_used: bool = False
    execution_episode_id: int | None = None
    asset_refs: tuple[dict[str, Any], ...] = ()
    visual_paths: tuple[str, ...] = ()
    temp_paths: tuple[str, ...] = ()
    effort: str | int | None = None
    force_audio_response: bool = False
    executing_agent_id: str | None = None
    squad_thread_id: str | None = None
    squad_task_id: str | None = None
    parent_message_id: str | None = None
    delegation_chain: tuple[str, ...] = ()
    delegation_request_id: str | None = None
    delegation_origin_agent_id: str | None = None
    telegram_message_thread_id: int | None = None

    def to_dict(self) -> JsonDict:
        return _dataclass_to_json_dict(self)

    def to_json(self) -> str:
        return _to_json(self.to_dict())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            contract_version=_as_str(data.get("contract_version"), AGENT_TURN_CONTRACT_VERSION),
            task_id=_as_optional_int(data.get("task_id")),
            provider=_as_str(data.get("provider")),
            model=_as_str(data.get("model")),
            session_id=_as_str(data.get("session_id")),
            provider_session_id=_as_optional_str(data.get("provider_session_id")),
            work_dir=_as_str(data.get("work_dir")),
            compiled_prompt=_as_str(data.get("compiled_prompt")),
            agent_mode=_as_str(data.get("agent_mode")),
            permission_mode=_as_str(data.get("permission_mode")),
            max_turns=_as_int(data.get("max_turns"), 0),
            turn_mode=_as_str(data.get("turn_mode"), "new_turn"),
            resume_requested=bool(data.get("resume_requested", False)),
            supports_native_resume=bool(data.get("supports_native_resume", True)),
            provider_available=bool(data.get("provider_available", True)),
            dry_run=bool(data.get("dry_run", False)),
            scheduled_job_id=_as_optional_int(data.get("scheduled_job_id")),
            scheduled_run_id=_as_optional_int(data.get("scheduled_run_id")),
            runtime_env_id=_as_optional_int(data.get("runtime_env_id")),
            runtime_classification=_as_str(data.get("runtime_classification"), "light"),
            runtime_environment_kind=_as_str(data.get("runtime_environment_kind"), "dev_worktree"),
            task_kind=_as_str(data.get("task_kind"), "general"),
            warnings=_as_str_tuple(data.get("warnings")),
            fallback_chain=_as_str_tuple(data.get("fallback_chain")),
            compiled_context_blocks=tuple(
                CompiledContextBlock.from_dict(item)
                for item in _as_mapping_sequence(data.get("compiled_context_blocks"))
            ),
            prompt_budget=_as_plain_dict(data.get("prompt_budget")),
            knowledge_hit_count=_as_int(data.get("knowledge_hit_count"), 0),
            memory_trust_score=_as_float(data.get("memory_trust_score"), 0.0),
            confidence_reports=_as_dict_tuple(data.get("confidence_reports")),
            effective_policy=_as_optional_plain_dict(data.get("effective_policy")),
            ungrounded_operationally=bool(data.get("ungrounded_operationally", False)),
            stale_sources_present=bool(data.get("stale_sources_present", False)),
            verified_before_finalize=bool(data.get("verified_before_finalize", False)),
            human_approval_used=bool(data.get("human_approval_used", False)),
            execution_episode_id=_as_optional_int(data.get("execution_episode_id")),
            asset_refs=_as_dict_tuple(data.get("asset_refs")),
            visual_paths=_as_str_tuple(data.get("visual_paths")),
            temp_paths=_as_str_tuple(data.get("temp_paths")),
            effort=_as_optional_str_or_int(data.get("effort")),
            force_audio_response=bool(data.get("force_audio_response", False)),
            executing_agent_id=_as_optional_str(data.get("executing_agent_id")),
            squad_thread_id=_as_optional_str(data.get("squad_thread_id")),
            squad_task_id=_as_optional_str(data.get("squad_task_id")),
            parent_message_id=_as_optional_str(data.get("parent_message_id")),
            delegation_chain=_as_str_tuple(data.get("delegation_chain")),
            delegation_request_id=_as_optional_str(data.get("delegation_request_id")),
            delegation_origin_agent_id=_as_optional_str(data.get("delegation_origin_agent_id")),
            telegram_message_thread_id=_as_optional_int(data.get("telegram_message_thread_id")),
        )

    @classmethod
    def from_json(cls, payload: str) -> Self:
        return cls.from_dict(_loads_json_dict(payload))


@dataclass(frozen=True, slots=True)
class AgentTurnOutput:
    """Provider result and observable runtime output for one agent turn."""

    contract_version: str = AGENT_TURN_CONTRACT_VERSION
    status: AgentTurnRuntimeState | str = "completed"
    provider: str = ""
    model: str = ""
    result: str = ""
    session_id: str = ""
    provider_session_id: str | None = None
    cost_usd: float = 0.0
    error: bool = False
    stop_reason: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    tool_uses: tuple[dict[str, Any], ...] = ()
    native_items: tuple[dict[str, Any], ...] = ()
    tool_execution_trace: tuple[dict[str, Any], ...] = ()
    raw_output: str = ""
    warnings: tuple[str, ...] = ()
    fallback_chain: tuple[str, ...] = ()
    turn_mode: str = "new_turn"
    supports_native_resume: bool = True
    error_kind: str = ""
    retryable: bool = False
    runtime_terminal_id: int | None = None
    runtime_terminal_path: str | None = None
    events: tuple[AgentTurnEvent, ...] = ()
    error_details: AgentTurnError | None = None

    def to_dict(self) -> JsonDict:
        return _dataclass_to_json_dict(self)

    def to_json(self) -> str:
        return _to_json(self.to_dict())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        error_details = data.get("error_details")
        return cls(
            contract_version=_as_str(data.get("contract_version"), AGENT_TURN_CONTRACT_VERSION),
            status=_as_str(data.get("status"), "completed"),
            provider=_as_str(data.get("provider")),
            model=_as_str(data.get("model")),
            result=_as_str(data.get("result")),
            session_id=_as_str(data.get("session_id")),
            provider_session_id=_as_optional_str(data.get("provider_session_id")),
            cost_usd=_as_float(data.get("cost_usd"), 0.0),
            error=bool(data.get("error", False)),
            stop_reason=_as_str(data.get("stop_reason")),
            usage=_as_plain_dict(data.get("usage")),
            tool_uses=_as_dict_tuple(data.get("tool_uses")),
            native_items=_as_dict_tuple(data.get("native_items")),
            tool_execution_trace=_as_dict_tuple(data.get("tool_execution_trace")),
            raw_output=_as_str(data.get("raw_output")),
            warnings=_as_str_tuple(data.get("warnings")),
            fallback_chain=_as_str_tuple(data.get("fallback_chain")),
            turn_mode=_as_str(data.get("turn_mode"), "new_turn"),
            supports_native_resume=bool(data.get("supports_native_resume", True)),
            error_kind=_as_str(data.get("error_kind")),
            retryable=bool(data.get("retryable", False)),
            runtime_terminal_id=_as_optional_int(data.get("runtime_terminal_id")),
            runtime_terminal_path=_as_optional_str(data.get("runtime_terminal_path")),
            events=tuple(AgentTurnEvent.from_dict(item) for item in _as_mapping_sequence(data.get("events"))),
            error_details=(AgentTurnError.from_dict(error_details) if isinstance(error_details, Mapping) else None),
        )

    @classmethod
    def from_json(cls, payload: str) -> Self:
        return cls.from_dict(_loads_json_dict(payload))


def from_query_context(ctx: Any) -> AgentTurnInput:
    """Build an ``AgentTurnInput`` snapshot from a QueryContext-shaped object."""

    prompt_budget = _as_plain_dict(getattr(ctx, "prompt_budget", None))
    return AgentTurnInput(
        task_id=_as_optional_int(getattr(ctx, "task_id", None)),
        provider=_as_str(getattr(ctx, "provider", "")),
        model=_as_str(getattr(ctx, "model", "")),
        session_id=_as_str(getattr(ctx, "session_id", "")),
        provider_session_id=_as_optional_str(getattr(ctx, "provider_session_id", None)),
        work_dir=_as_str(getattr(ctx, "work_dir", "")),
        compiled_prompt=_as_str(getattr(ctx, "system_prompt", "")),
        agent_mode=_as_str(getattr(ctx, "agent_mode", "")),
        permission_mode=_as_str(getattr(ctx, "permission_mode", "")),
        max_turns=_as_int(getattr(ctx, "max_turns", 0), 0),
        turn_mode=_as_str(getattr(ctx, "turn_mode", "new_turn"), "new_turn"),
        resume_requested=bool(getattr(ctx, "resume_requested", False)),
        supports_native_resume=bool(getattr(ctx, "supports_native_resume", True)),
        provider_available=bool(getattr(ctx, "provider_available", True)),
        dry_run=bool(getattr(ctx, "dry_run", False)),
        scheduled_job_id=_as_optional_int(getattr(ctx, "scheduled_job_id", None)),
        scheduled_run_id=_as_optional_int(getattr(ctx, "scheduled_run_id", None)),
        runtime_env_id=_as_optional_int(getattr(ctx, "runtime_env_id", None)),
        runtime_classification=_as_str(getattr(ctx, "runtime_classification", "light"), "light"),
        runtime_environment_kind=_as_str(
            getattr(ctx, "runtime_environment_kind", "dev_worktree"),
            "dev_worktree",
        ),
        task_kind=_as_str(getattr(ctx, "task_kind", "general"), "general"),
        warnings=_as_str_tuple(getattr(ctx, "warnings", ())),
        fallback_chain=_as_str_tuple(getattr(ctx, "fallback_chain", ())),
        compiled_context_blocks=_context_blocks_from_prompt_budget(prompt_budget),
        prompt_budget=_prompt_budget_summary(prompt_budget),
        knowledge_hit_count=len(_as_sequence(getattr(ctx, "knowledge_hits", ()))),
        memory_trust_score=_as_float(getattr(ctx, "memory_trust_score", 0.0), 0.0),
        confidence_reports=_as_dict_tuple(getattr(ctx, "confidence_reports", ())),
        effective_policy=_to_optional_json_dict(getattr(ctx, "effective_policy", None)),
        ungrounded_operationally=bool(getattr(ctx, "ungrounded_operationally", False)),
        stale_sources_present=bool(getattr(ctx, "stale_sources_present", False)),
        verified_before_finalize=bool(getattr(ctx, "verified_before_finalize", False)),
        human_approval_used=bool(getattr(ctx, "human_approval_used", False)),
        execution_episode_id=_as_optional_int(getattr(ctx, "execution_episode_id", None)),
        asset_refs=_as_dict_tuple(getattr(ctx, "asset_refs", ())),
        visual_paths=_as_str_tuple(getattr(ctx, "visual_paths", ())),
        temp_paths=_as_str_tuple(getattr(ctx, "temp_paths", ())),
        effort=_as_optional_str_or_int(getattr(ctx, "effort", None)),
        force_audio_response=bool(getattr(ctx, "force_audio_response", False)),
        executing_agent_id=_as_optional_str(getattr(ctx, "executing_agent_id", None)),
        squad_thread_id=_as_optional_str(getattr(ctx, "squad_thread_id", None)),
        squad_task_id=_as_optional_str(getattr(ctx, "squad_task_id", None)),
        parent_message_id=_as_optional_str(getattr(ctx, "parent_message_id", None)),
        delegation_chain=_as_str_tuple(getattr(ctx, "delegation_chain", ())),
        delegation_request_id=_as_optional_str(getattr(ctx, "delegation_request_id", None)),
        delegation_origin_agent_id=_as_optional_str(getattr(ctx, "delegation_origin_agent_id", None)),
        telegram_message_thread_id=_as_optional_int(getattr(ctx, "telegram_message_thread_id", None)),
    )


def from_run_result(result: Any) -> AgentTurnOutput:
    """Build an ``AgentTurnOutput`` snapshot from a RunResult-shaped object."""

    is_error = bool(getattr(result, "error", False))
    error_kind = _as_str(getattr(result, "error_kind", ""))
    retryable = bool(getattr(result, "retryable", False))
    provider = _as_str(getattr(result, "provider", ""))
    return AgentTurnOutput(
        status=cast(AgentTurnRuntimeState, "failed" if is_error else "completed"),
        provider=provider,
        model=_as_str(getattr(result, "model", "")),
        result=_as_str(getattr(result, "result", "")),
        session_id=_as_str(getattr(result, "session_id", "")),
        provider_session_id=_as_optional_str(getattr(result, "provider_session_id", None)),
        cost_usd=_as_float(getattr(result, "cost_usd", 0.0), 0.0),
        error=is_error,
        stop_reason=_as_str(getattr(result, "stop_reason", "")),
        usage=_as_plain_dict(getattr(result, "usage", {})),
        tool_uses=_as_dict_tuple(getattr(result, "tool_uses", ())),
        native_items=_as_dict_tuple(getattr(result, "native_items", ())),
        tool_execution_trace=_as_dict_tuple(getattr(result, "tool_execution_trace", ())),
        raw_output=_as_str(getattr(result, "raw_output", "")),
        warnings=_as_str_tuple(getattr(result, "warnings", ())),
        fallback_chain=_as_str_tuple(getattr(result, "fallback_chain", ())),
        turn_mode=_as_str(getattr(result, "turn_mode", "new_turn"), "new_turn"),
        supports_native_resume=bool(getattr(result, "supports_native_resume", True)),
        error_kind=error_kind,
        retryable=retryable,
        runtime_terminal_id=_as_optional_int(getattr(result, "runtime_terminal_id", None)),
        runtime_terminal_path=_as_optional_str(getattr(result, "runtime_terminal_path", None)),
        error_details=_build_agent_turn_error(
            provider=provider,
            error_kind=error_kind,
            retryable=retryable,
            message=_as_str(getattr(result, "result", "")) or _as_str(getattr(result, "stop_reason", "")),
        )
        if is_error
        else None,
    )


def _build_agent_turn_error(
    *,
    provider: str,
    error_kind: str,
    retryable: bool,
    message: str,
) -> AgentTurnError:
    normalized_kind = error_kind.strip().lower() or "provider_error"
    category = _category_for_error_kind(normalized_kind, retryable=retryable)
    return AgentTurnError(
        code=f"runtime.{normalized_kind}",
        category=category,
        message=message or "Agent turn failed.",
        retryable=retryable,
        user_action=_user_action_for_error_category(category, retryable=retryable),
        provider=provider or None,
        error_kind=normalized_kind,
    )


def _category_for_error_kind(error_kind: str, *, retryable: bool) -> AgentTurnErrorCategory:
    if "timeout" in error_kind:
        return "timeout"
    if "permission" in error_kind or "auth" in error_kind:
        return "permission"
    if "policy" in error_kind or "denied" in error_kind:
        return "policy_denied"
    if "config" in error_kind:
        return "configuration"
    if "validation" in error_kind or "schema" in error_kind:
        return "validation"
    if "unavailable" in error_kind or "dependency" in error_kind or "provider" in error_kind:
        return "dependency_unavailable"
    return "retryable" if retryable else "internal"


def _user_action_for_error_category(category: str, *, retryable: bool) -> str:
    if category == "configuration":
        return "Open settings or run doctor, then retry the task."
    if category == "permission":
        return "Request access or update the relevant runtime grant."
    if category == "policy_denied":
        return "Inspect policy and choose a safer action."
    if category == "dependency_unavailable":
        return "Wait, retry, or inspect dependency health."
    if category == "timeout":
        return "Retry, cancel, or reduce scope."
    if category == "validation":
        return "Correct the input or schema and retry."
    if retryable:
        return "Retry the task or wait for automatic retry."
    return "Inspect the trace and retry after resolving the root cause."


def _context_blocks_from_prompt_budget(prompt_budget: Mapping[str, Any]) -> tuple[CompiledContextBlock, ...]:
    blocks: list[CompiledContextBlock] = []
    for status, key in (("included", "included_segments"), ("dropped", "dropped_segments")):
        for item in _as_mapping_sequence(prompt_budget.get(key)):
            blocks.append(
                CompiledContextBlock(
                    block_id=_as_str(item.get("segment_id")),
                    category=_as_str(item.get("category")),
                    status=cast(CompiledContextBlockStatus, status),
                    priority=_as_int(item.get("priority"), 100),
                    token_estimate=_as_int(item.get("token_estimate"), 0),
                    final_token_estimate=_as_optional_int(item.get("final_token_estimate")),
                    compression_strategy=_as_str(item.get("compression_strategy")),
                    drop_policy=_as_str(item.get("drop_policy")),
                    compressed=bool(item.get("compressed", False)),
                    reason=_as_optional_str(item.get("reason")),
                    metadata=_as_plain_dict(item.get("metadata")),
                )
            )
    return tuple(blocks)


def _prompt_budget_summary(prompt_budget: Mapping[str, Any]) -> dict[str, Any]:
    omitted = {"compiled_prompt", "included_segments", "dropped_segments"}
    return {str(key): _json_compatible(value) for key, value in prompt_budget.items() if str(key) not in omitted}


def _dataclass_to_json_dict(instance: Any) -> JsonDict:
    return {item.name: _json_compatible(getattr(instance, item.name)) for item in fields(instance)}


def _json_compatible(value: Any) -> JsonValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Enum):
        return _json_compatible(value.value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return _dataclass_to_json_dict(value)
    if isinstance(value, Mapping):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [_json_compatible(item) for item in value]
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return _json_compatible(to_dict())
        except Exception:
            return str(value)
    return str(value)


def _to_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_json_compatible(payload), sort_keys=True, separators=(",", ":"))


def _loads_json_dict(payload: str) -> dict[str, Any]:
    decoded = json.loads(payload)
    if not isinstance(decoded, dict):
        raise TypeError("AgentTurn JSON payload must decode to an object.")
    return decoded


def _as_plain_dict(value: Any) -> dict[str, Any]:
    json_value = _json_compatible(value)
    if isinstance(json_value, dict):
        return dict(json_value)
    return {}


def _as_optional_plain_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    return _as_plain_dict(value)


def _to_optional_json_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    return _as_plain_dict(value)


def _as_mapping_sequence(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _as_sequence(value: Any) -> tuple[Any, ...]:
    if isinstance(value, list | tuple | set | frozenset):
        return tuple(value)
    if value is None:
        return ()
    return (value,)


def _as_dict_tuple(value: Any) -> tuple[dict[str, Any], ...]:
    return tuple(_as_plain_dict(item) for item in _as_sequence(value))


def _as_str_tuple(value: Any) -> tuple[str, ...]:
    return tuple(_as_str(item) for item in _as_sequence(value))


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, Enum):
        return _as_str(value.value, default)
    return str(value)


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = _as_str(value)
    return text if text != "" else None


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_optional_str_or_int(value: Any) -> str | int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    return _as_str(value)
