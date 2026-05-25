"""Persistence service for execution episodes and reliability counters."""

from __future__ import annotations

from typing import Any


class ExecutionEpisodeService:
    """Keep execution episode persistence out of queue_manager orchestration flow."""

    def __init__(self, *, agent_id: str | None) -> None:
        self._agent_id = agent_id

    async def record_execution_episode(
        self,
        *,
        user_id: int,
        task_id: int | None,
        status: str,
        ctx: Any,
        run_result: Any,
        confidence_score: float,
        source_refs: list[dict[str, Any]],
        human_override_delta: int = 0,
    ) -> None:
        if ctx is None or run_result is None or task_id is None:
            return
        try:
            from koda.state.knowledge_governance_store import (
                create_execution_episode,
                update_execution_reliability_stats,
            )

            answer_evaluation = getattr(ctx, "answer_evaluation", None)

            def _eval_value(field: str, default: Any) -> Any:
                if answer_evaluation is None:
                    return default
                if isinstance(answer_evaluation, dict):
                    return answer_evaluation.get(field, default)
                return getattr(answer_evaluation, field, default)

            episode_id = create_execution_episode(
                agent_id=self._agent_id,
                task_id=task_id,
                user_id=user_id,
                task_kind=ctx.task_kind,
                project_key=getattr(ctx.knowledge_query_context, "project_key", ""),
                environment=getattr(ctx.knowledge_query_context, "environment", ""),
                team=getattr(ctx.knowledge_query_context, "team", ""),
                autonomy_tier=getattr(getattr(ctx.effective_policy, "autonomy_tier", None), "value", ""),
                approval_mode=str(getattr(ctx.effective_policy, "approval_mode", "")),
                status=status,
                confidence_score=float(confidence_score or 0.0),
                verified_before_finalize=ctx.verified_before_finalize,
                stale_sources_present=ctx.stale_sources_present,
                ungrounded_operationally=ctx.ungrounded_operationally,
                plan=ctx.last_action_plan,
                source_refs=source_refs,
                tool_trace=run_result.tool_execution_trace,
                retrieval_trace_id=getattr(getattr(ctx, "knowledge_resolution", None), "trace_id", None),
                retrieval_strategy=getattr(
                    getattr(getattr(ctx, "knowledge_resolution", None), "retrieval_strategy", None),
                    "value",
                    str(getattr(getattr(ctx, "knowledge_resolution", None), "retrieval_strategy", "") or ""),
                ),
                grounding_score=float(
                    getattr(getattr(ctx, "knowledge_resolution", None), "grounding_score", 0.0) or 0.0
                ),
                citation_coverage=float(
                    getattr(getattr(ctx, "knowledge_resolution", None), "citation_coverage", 0.0) or 0.0
                ),
                winning_sources=list(getattr(getattr(ctx, "knowledge_resolution", None), "winning_sources", []) or []),
                answer_citation_coverage=float(_eval_value("citation_coverage", 0.0) or 0.0),
                answer_gate_status=str(_eval_value("gate_status", "") or ""),
                answer_gate_reasons=list(_eval_value("gate_reasons", []) or []),
                post_write_review_required=bool(_eval_value("requires_review", False)),
            )
            ctx.execution_episode_id = episode_id
            update_execution_reliability_stats(
                agent_id=self._agent_id,
                task_kind=ctx.task_kind,
                project_key=getattr(ctx.knowledge_query_context, "project_key", ""),
                environment=getattr(ctx.knowledge_query_context, "environment", ""),
                successful=status == "completed",
                verified=ctx.verified_before_finalize,
                human_override_delta=human_override_delta,
                rollback_delta=1 if (status not in {"completed", "needs_review"} and ctx.task_kind == "deploy") else 0,
            )
        except Exception:
            from koda.logging_config import get_logger

            get_logger(__name__).exception("execution_episode_record_error")
