"""Helpers for assembling knowledge query context outside queue_manager."""

from __future__ import annotations

from koda.knowledge.config import KNOWLEDGE_ALLOWED_SOURCE_LABELS, KNOWLEDGE_ALLOWED_WORKSPACE_ROOTS
from koda.knowledge.types import AutonomyTier, KnowledgeQueryContext, RetrievalStrategy


class QueryContextService:
    """Build structured knowledge query context from orchestration inputs."""

    def build_knowledge_query_context(
        self,
        *,
        query: str,
        task_id: int | None,
        agent_id: str | None,
        user_id: int | None,
        workspace_dir: str | None,
        workspace_fingerprint: str,
        project_key: str,
        task_kind: str,
        environment: str,
        team: str,
        autonomy_tier_target: AutonomyTier,
        task_risk: str,
        requires_write: bool,
        retrieval_strategy: RetrievalStrategy | None,
    ) -> KnowledgeQueryContext:
        return KnowledgeQueryContext(
            query=query,
            task_id=task_id,
            agent_id=agent_id,
            user_id=user_id,
            workspace_dir=workspace_dir,
            project_key=project_key,
            task_kind=task_kind,
            environment=environment,
            team=team,
            autonomy_tier_target=autonomy_tier_target,
            workspace_fingerprint=workspace_fingerprint,
            task_risk=task_risk,
            requires_write=requires_write,
            retrieval_strategy=retrieval_strategy,
            allowed_source_labels=tuple(KNOWLEDGE_ALLOWED_SOURCE_LABELS),
            allowed_workspace_roots=tuple(KNOWLEDGE_ALLOWED_WORKSPACE_ROOTS),
        )
