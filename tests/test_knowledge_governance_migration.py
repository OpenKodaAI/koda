"""Regression tests for migration 019_knowledge_governance_tables.

The four governance tables (knowledge_candidates, knowledge_source_registry,
approved_runbooks, approved_guardrails) were referenced by
``koda/state/knowledge_governance_store.py`` but never actually created in
Postgres. Every agent worker would spam
``control_plane_runtime_governance_unavailable: relation "knowledge_candidates"
does not exist`` on every reconcile tick until this migration landed.
"""

from __future__ import annotations

import inspect


def test_migration_defines_all_four_governance_tables() -> None:
    """Ensure 019_knowledge_governance_tables was not silently dropped."""
    from koda.knowledge.v2.postgres_backend import KnowledgeV2PostgresBackend

    src = inspect.getsource(KnowledgeV2PostgresBackend._migrations)
    assert "019_knowledge_governance_tables" in src
    for table in (
        "knowledge_candidates",
        "approved_runbooks",
        "approved_guardrails",
        "knowledge_source_registry",
    ):
        assert f'"{table}"' in src, f"DDL for {table} missing from migration 019"


def test_knowledge_candidates_ddl_has_required_columns() -> None:
    """list_knowledge_candidates SELECTs 29 columns — DDL must declare all of them."""
    from koda.knowledge.v2.postgres_backend import KnowledgeV2PostgresBackend

    src = inspect.getsource(KnowledgeV2PostgresBackend._migrations)
    for column in (
        "candidate_key",
        "merge_key",
        "agent_id",
        "task_id",
        "task_kind",
        "candidate_type",
        "summary",
        "evidence_json",
        "source_refs_json",
        "proposed_runbook_json",
        "confidence_score",
        "review_status",
        "reviewer",
        "reviewed_at",
        "diff_summary",
        "review_note",
        "created_at",
        "updated_at",
        "project_key",
        "environment",
        "team",
        "support_count",
        "success_count",
        "failure_count",
        "verification_count",
        "promoted_runbook_id",
        "last_human_feedback_at",
        "last_promoted_version",
    ):
        assert column in src, f"knowledge_candidates column {column} not in DDL"


def test_approved_runbooks_ddl_matches_store_inserts() -> None:
    """approved_runbooks must carry every column the store INSERTs / SELECTs."""
    from koda.knowledge.v2.postgres_backend import KnowledgeV2PostgresBackend

    src = inspect.getsource(KnowledgeV2PostgresBackend._migrations)
    for column in (
        "runbook_key",
        "version",
        "title",
        "task_kind",
        "summary",
        "prerequisites_json",
        "steps_json",
        "verification_json",
        "rollback",
        "source_refs_json",
        "project_key",
        "environment",
        "team",
        "owner",
        "approved_by",
        "approved_at",
        "last_validated_by",
        "last_validated_at",
        "status",
        "lifecycle_status",
        "valid_from",
        "valid_until",
        "rollout_scope_json",
        "policy_overrides_json",
        "supersedes_runbook_id",
        "source_candidate_id",
    ):
        assert column in src, f"approved_runbooks column {column} not in DDL"


def test_approved_guardrails_ddl_matches_store_inserts() -> None:
    """approved_guardrails has a smaller surface — covered end-to-end."""
    from koda.knowledge.v2.postgres_backend import KnowledgeV2PostgresBackend

    src = inspect.getsource(KnowledgeV2PostgresBackend._migrations)
    for column in (
        "task_kind",
        "title",
        "severity",
        "reason",
        "source_label",
        "source_path",
        "project_key",
        "environment",
        "team",
        "owner",
        "status",
        "source_candidate_id",
        "created_at",
        "updated_at",
    ):
        assert column in src, f"approved_guardrails column {column} not in DDL"


def test_knowledge_source_registry_ddl_matches_store_inserts() -> None:
    from koda.knowledge.v2.postgres_backend import KnowledgeV2PostgresBackend

    src = inspect.getsource(KnowledgeV2PostgresBackend._migrations)
    for column in (
        "source_key",
        "project_key",
        "source_type",
        "layer",
        "source_label",
        "source_path",
        "owner",
        "freshness_days",
        "content_hash",
        "status",
        "is_canonical",
        "updated_at",
        "last_synced_at",
        "stale_after",
        "invalid_after",
        "sla_hours",
        "sync_mode",
        "last_success_at",
        "last_error",
        "workspace_fingerprint",
    ):
        assert column in src, f"knowledge_source_registry column {column} not in DDL"
