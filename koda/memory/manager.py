"""Memory manager: orchestrates extraction, storage, and recall."""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable
from pathlib import Path

from koda.config import AGENT_ID
from koda.knowledge.config import (
    KNOWLEDGE_CANDIDATE_FAILURE_THRESHOLD,
    KNOWLEDGE_CANDIDATE_MIN_CONFIDENCE,
    KNOWLEDGE_CANDIDATE_SUCCESS_THRESHOLD,
)
from koda.knowledge.task_policy_defaults import classify_task_kind
from koda.logging_config import get_logger
from koda.memory.config import (
    MEMORY_ENABLED,
    MEMORY_PROACTIVE_ENABLED,
    MEMORY_PROCEDURAL_ENABLED,
    MEMORY_RECALL_TIMEOUT,
)
from koda.memory.extractor import extract
from koda.memory.procedural import build_execution_memories, infer_validation_summary
from koda.memory.profile import MemoryProfile, load_memory_profile
from koda.memory.quality import record_memory_quality_counter
from koda.memory.recall import (
    build_memory_context,
    build_memory_resolution,
    build_proactive_context,
    build_procedural_context,
    clear_recall_cache,
)
from koda.memory.store import MemoryStore
from koda.memory.types import MemoryResolution
from koda.state.knowledge_governance_store import set_knowledge_candidate_status, upsert_knowledge_candidate

log = get_logger(__name__)


class MemoryManager:
    """Orchestrates the memory pipeline: pre_query (recall) and post_query (extract+store)."""

    def __init__(self, agent_id: str | None = None) -> None:
        self._agent_id = agent_id or AGENT_ID
        self._profile: MemoryProfile = load_memory_profile(self._agent_id)
        self._store: MemoryStore | None = None

    async def initialize(self) -> None:
        """Initialize the memory store. Call once at startup."""
        if not MEMORY_ENABLED:
            log.info("memory_disabled")
            return
        self._store = MemoryStore(self._agent_id)
        log.info("memory_manager_initialized", agent_id=self._agent_id)

    @property
    def store(self) -> MemoryStore | None:
        return self._store

    @property
    def profile(self) -> MemoryProfile:
        return self._profile

    async def pre_query(
        self,
        query: str,
        user_id: int,
        *,
        include_procedural: bool = True,
        session_id: str | None = None,
        project_key: str = "",
        environment: str = "",
        team: str = "",
        task_id: int | None = None,
        source_query_id: int | None = None,
        source_task_id: int | None = None,
        source_episode_id: int | None = None,
    ) -> str:
        """Recall relevant memories and return context string for system prompt.

        Returns empty string if memory is disabled or no relevant memories found.
        """
        if not MEMORY_ENABLED or not self._store:
            return ""

        try:
            import asyncio

            coros = [
                build_memory_context(
                    self._store,
                    query,
                    user_id,
                    profile=self._profile,
                    session_id=session_id,
                    project_key=project_key,
                    environment=environment,
                    team=team,
                    task_id=task_id,
                    source_query_id=source_query_id,
                    source_task_id=source_task_id,
                    source_episode_id=source_episode_id,
                )
            ]
            if MEMORY_PROACTIVE_ENABLED:
                coros.append(asyncio.to_thread(build_proactive_context, user_id, agent_id=self._agent_id))
            if MEMORY_PROCEDURAL_ENABLED and include_procedural:
                coros.append(
                    build_procedural_context(
                        self._store,
                        query,
                        user_id,
                        project_key=project_key,
                        environment=environment,
                        team=team,
                        session_id=session_id,
                    )
                )

            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*coros, return_exceptions=True),
                    timeout=MEMORY_RECALL_TIMEOUT,
                )
            except TimeoutError:
                log.warning("memory_pre_query_timeout")
                return ""

            first_result = results[0]
            context = first_result if isinstance(first_result, str) else ""
            if MEMORY_PROACTIVE_ENABLED and len(results) > 1:
                proactive_result = results[1]
                proactive = proactive_result if isinstance(proactive_result, str) else ""
                if proactive:
                    context = (context + "\n\n" + proactive) if context else proactive
            if MEMORY_PROCEDURAL_ENABLED:
                procedural_index = 2 if MEMORY_PROACTIVE_ENABLED else 1
                if len(results) > procedural_index:
                    procedural_result = results[procedural_index]
                    procedural = procedural_result if isinstance(procedural_result, str) else ""
                    if procedural:
                        context = (context + "\n\n" + procedural) if context else procedural

            return context
        except Exception:
            log.exception("memory_pre_query_error")
            return ""

    async def pre_query_details(
        self,
        query: str,
        user_id: int,
        *,
        include_procedural: bool = True,
        session_id: str | None = None,
        project_key: str = "",
        environment: str = "",
        team: str = "",
        task_id: int | None = None,
        source_query_id: int | None = None,
        source_task_id: int | None = None,
        source_episode_id: int | None = None,
    ) -> tuple[str, MemoryResolution]:
        """Return prompt context plus a structured resolution envelope for audit and gating."""
        if not MEMORY_ENABLED or not self._store:
            return "", MemoryResolution(context="")

        try:
            import asyncio

            memory_resolution_task = build_memory_resolution(
                self._store,
                query,
                user_id,
                profile=self._profile,
                session_id=session_id,
                project_key=project_key,
                environment=environment,
                team=team,
                task_id=task_id,
                source_query_id=source_query_id,
                source_task_id=source_task_id,
                source_episode_id=source_episode_id,
            )
            coros: list[Awaitable[object]] = [memory_resolution_task]
            if MEMORY_PROACTIVE_ENABLED:
                coros.append(asyncio.to_thread(build_proactive_context, user_id, agent_id=self._agent_id))
            if MEMORY_PROCEDURAL_ENABLED and include_procedural:
                coros.append(
                    build_procedural_context(
                        self._store,
                        query,
                        user_id,
                        project_key=project_key,
                        environment=environment,
                        team=team,
                        session_id=session_id,
                    )
                )

            results = await asyncio.gather(*coros, return_exceptions=True)
            base_candidate = results[0] if results else None
            base_resolution = (
                base_candidate if isinstance(base_candidate, MemoryResolution) else MemoryResolution(context="")
            )
            context_parts = [base_resolution.context] if base_resolution.context else []
            proactive_result = results[1] if MEMORY_PROACTIVE_ENABLED and len(results) > 1 else None
            if isinstance(proactive_result, str) and proactive_result:
                context_parts.append(proactive_result)
                base_resolution.selected_layers = sorted(set(base_resolution.selected_layers + ["proactive"]))
                base_resolution.trust_score = round(min(1.0, base_resolution.trust_score + 0.05), 4)
            if MEMORY_PROCEDURAL_ENABLED:
                procedural_index = 2 if MEMORY_PROACTIVE_ENABLED else 1
                procedural_result = results[procedural_index] if len(results) > procedural_index else None
                if isinstance(procedural_result, str) and procedural_result:
                    context_parts.append(procedural_result)
                    base_resolution.selected_layers = sorted(set(base_resolution.selected_layers + ["procedural"]))
                    base_resolution.trust_score = round(min(1.0, base_resolution.trust_score + 0.10), 4)
            combined_context = "\n\n".join(part for part in context_parts if part)
            base_resolution.context = combined_context
            return combined_context, base_resolution
        except Exception:
            log.exception("memory_pre_query_details_error")
            return "", MemoryResolution(context="")

    async def post_query(
        self,
        query: str,
        response: str,
        user_id: int,
        session_id: str | None = None,
        *,
        source_query_id: int | None = None,
        source_task_id: int | None = None,
        source_episode_id: int | None = None,
        project_key: str = "",
        environment: str = "",
        team: str = "",
    ) -> None:
        """Extract and store memories from a completed query-response pair."""
        if not MEMORY_ENABLED or not self._store:
            return

        try:
            from koda.services import metrics

            record_memory_quality_counter(self._agent_id, "extraction", "total")
            memories = await extract(
                query,
                response,
                user_id,
                session_id,
                agent_id=self._agent_id,
                source_query_id=source_query_id,
                source_task_id=source_task_id,
                source_episode_id=source_episode_id,
                project_key=project_key,
                environment=environment,
                team=team,
                profile=self._profile,
            )
            if memories:
                await self._store.add_batch(memories)
                clear_recall_cache(user_id)
                log.info("memory_extracted", count=len(memories), user_id=user_id)
                metrics.MEMORY_EXTRACTIONS.labels(
                    agent_id=(self._agent_id or "default").lower(), status="accepted"
                ).inc(len(memories))
                record_memory_quality_counter(self._agent_id, "extraction", "accepted", delta=len(memories))
            else:
                metrics.MEMORY_EXTRACTIONS.labels(
                    agent_id=(self._agent_id or "default").lower(), status="rejected"
                ).inc()
                record_memory_quality_counter(self._agent_id, "extraction", "rejected")
        except Exception:
            log.exception("memory_post_query_error")

    async def record_execution_pattern(
        self,
        *,
        query: str,
        user_id: int,
        task_id: int | None,
        source_episode_id: int | None = None,
        status: str,
        confidence_score: float | None,
        error_message: str | None,
        tool_uses: list[dict],
        tool_execution_trace: list[dict],
        knowledge_hits: list[dict],
        work_dir: str | None,
        model: str | None,
        task_kind: str | None = None,
        verified_before_finalize: bool = False,
        ungrounded_operationally: bool = False,
        action_plan: dict | None = None,
        project_key: str = "",
        environment: str = "",
        team: str = "",
    ) -> None:
        """Persist a best-effort procedural memory from a task outcome."""
        if not MEMORY_ENABLED or not MEMORY_PROCEDURAL_ENABLED or not self._store:
            return

        try:
            memories = build_execution_memories(
                query=query,
                user_id=user_id,
                task_id=task_id,
                status=status,
                confidence_score=confidence_score,
                error_message=error_message,
                tool_uses=tool_uses,
                tool_execution_trace=tool_execution_trace,
                knowledge_hits=knowledge_hits,
                work_dir=work_dir,
                model=model,
                task_kind=task_kind or classify_task_kind(query),
                project_key=project_key or Path(work_dir or "").name,
                environment=environment,
                team=team,
                owner=self._agent_id or "",
                source_episode_id=source_episode_id,
            )
            if memories:
                await self._store.add_batch(memories)
                clear_recall_cache(user_id)
            self._record_candidate(
                query=query,
                task_id=task_id,
                task_kind=task_kind or classify_task_kind(query),
                status=status,
                confidence_score=confidence_score,
                error_message=error_message,
                tool_uses=tool_uses,
                tool_execution_trace=tool_execution_trace,
                knowledge_hits=knowledge_hits,
                work_dir=work_dir,
                verified_before_finalize=verified_before_finalize,
                ungrounded_operationally=ungrounded_operationally,
                action_plan=action_plan or {},
                project_key=project_key,
                environment=environment,
                team=team,
            )
        except Exception:
            log.exception("memory_procedural_record_error")

    def _record_candidate(
        self,
        *,
        query: str,
        task_id: int | None,
        task_kind: str,
        status: str,
        confidence_score: float | None,
        error_message: str | None,
        tool_uses: list[dict],
        tool_execution_trace: list[dict],
        knowledge_hits: list[dict],
        work_dir: str | None,
        verified_before_finalize: bool,
        ungrounded_operationally: bool,
        action_plan: dict,
        project_key: str,
        environment: str,
        team: str,
    ) -> None:
        confidence = float(confidence_score or 0.0)
        validation_summary = infer_validation_summary(tool_uses)
        source_refs = [
            {
                "source_label": str(hit.get("source_label") or ""),
                "layer": str(hit.get("layer") or ""),
                "freshness": str(hit.get("freshness") or ""),
            }
            for hit in knowledge_hits
            if hit.get("source_label")
        ]
        tool_names = [str(step.get("tool")) for step in tool_execution_trace if step.get("tool")]
        if not tool_names:
            return

        normalized_sources = (
            ",".join(sorted({ref["source_label"] for ref in source_refs if ref["source_label"]})) or "none"
        )
        fingerprint_parts = [
            task_kind,
            project_key or Path(work_dir or "").name,
            environment,
            team,
            ",".join(tool_names),
            validation_summary,
            "success" if status == "completed" else "failure",
        ]
        if status != "completed":
            fingerprint_parts.append((error_message or "unknown error")[:120].lower())
        candidate_key = hashlib.sha256(
            "|".join(fingerprint_parts).encode("utf-8"),
            usedforsecurity=False,
        ).hexdigest()[:24]
        merge_key = hashlib.sha256(
            "|".join(
                [
                    task_kind,
                    project_key or Path(work_dir or "").name,
                    environment,
                    team,
                    ",".join(tool_names[:5]),
                ]
            ).encode("utf-8"),
            usedforsecurity=False,
        ).hexdigest()[:24]

        steps = [f"Use {tool_name} in the validated sequence." for tool_name in list(dict.fromkeys(tool_names))[:5]]
        verification_steps = []
        verification_note = str(action_plan.get("verification") or action_plan.get("success") or "").strip()
        if verification_note:
            verification_steps.append(verification_note)
        if validation_summary and validation_summary != "no explicit validation detected":
            verification_steps.append(f"Run validation with {validation_summary}.")
        rollback_note = str(action_plan.get("rollback") or "").strip()
        probable_cause = str(action_plan.get("probable_cause") or "").strip()

        summary = str(action_plan.get("summary") or query.strip().replace("\n", " ")[:160])
        proposed_runbook = {
            "title": f"{task_kind.replace('_', ' ').title()} routine",
            "summary": summary,
            "prerequisites": [
                note
                for note in [
                    str(action_plan.get("assumptions") or "").strip(),
                    f"Grounded sources: {normalized_sources}" if normalized_sources != "none" else "",
                ]
                if note
            ],
            "steps": steps,
            "verification": verification_steps,
            "rollback": rollback_note,
            "owner": self._agent_id or "",
        }
        evidence: list[dict[str, object]] = [
            {"kind": "validation", "value": validation_summary},
            {"kind": "verified_before_finalize", "value": verified_before_finalize},
            {"kind": "ungrounded_operationally", "value": ungrounded_operationally},
        ]
        if probable_cause:
            evidence.append({"kind": "probable_cause", "value": probable_cause})
        if error_message:
            evidence.append({"kind": "error", "value": error_message[:240]})

        diff_summary = (
            f"Observed {status} pattern for {task_kind}; tools={','.join(tool_names[:5])}; "
            f"validation={validation_summary}; sources={normalized_sources}"
        )
        candidate = upsert_knowledge_candidate(
            candidate_key=candidate_key,
            merge_key=merge_key,
            agent_id=self._agent_id,
            task_id=task_id,
            task_kind=task_kind,
            candidate_type="success_pattern" if status == "completed" else "risk_pattern",
            summary=summary,
            evidence=evidence,
            source_refs=source_refs,
            proposed_runbook=proposed_runbook,
            confidence_score=confidence,
            project_key=project_key or Path(work_dir or "").name,
            environment=environment,
            team=team,
            success_delta=1 if status == "completed" else 0,
            failure_delta=0 if status == "completed" else 1,
            verification_delta=1 if verified_before_finalize else 0,
            diff_summary=diff_summary,
        )

        promotion_policy = self._profile.promotion_policy or {}
        minimum_verified_successes = int(
            promotion_policy.get("minimum_verified_successes", KNOWLEDGE_CANDIDATE_SUCCESS_THRESHOLD)
        )
        requires_review = bool(promotion_policy.get("observed_pattern_requires_review", True))
        should_move_to_pending = False
        if status == "completed" and verified_before_finalize and confidence >= KNOWLEDGE_CANDIDATE_MIN_CONFIDENCE:
            should_move_to_pending = True
        if (
            candidate["success_count"] >= minimum_verified_successes
            and candidate["verification_count"] >= minimum_verified_successes
        ):
            should_move_to_pending = True
        if candidate["failure_count"] >= KNOWLEDGE_CANDIDATE_FAILURE_THRESHOLD:
            should_move_to_pending = True

        if should_move_to_pending and requires_review and candidate["review_status"] == "learning":
            set_knowledge_candidate_status(candidate["id"], review_status="pending")
