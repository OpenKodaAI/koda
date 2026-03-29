"""Evaluation persistence helpers for knowledge v2."""

from __future__ import annotations

from typing import Any

from koda.knowledge.repository import KnowledgeRepository


class KnowledgeEvaluationStore:
    """Thin repository-backed store for evaluation cases and runs."""

    def __init__(self, repository: KnowledgeRepository) -> None:
        self._repository = repository

    def list_cases(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return self._repository.list_evaluation_cases(limit=limit)

    def upsert_case(self, **payload: Any) -> int:
        return self._repository.upsert_evaluation_case(**payload)

    def update_case(self, case_key: str, **payload: Any) -> bool:
        return self._repository.update_evaluation_case(case_key, **payload)

    def list_runs(
        self,
        *,
        case_key: str | None = None,
        strategy: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self._repository.list_evaluation_runs(case_key=case_key, strategy=strategy, limit=limit)
