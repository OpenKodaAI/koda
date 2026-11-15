"""Canonical list of the tables that hold per-agent control-plane rows.

Every table in the schema with an ``agent_id`` column is either listed in
``PER_AGENT_TABLES`` or in ``AGENT_ID_TABLE_EXEMPTIONS``. That covers the tables
the migrations create and the three the runtime creates on first use in the
same schema: ``pending_approvals`` (``koda/state/pending_approvals.py``),
``approval_grants`` (``koda/state/approval_grants.py``) and
``artifact_objects`` (``rust/koda-artifact-engine``).
``tests/test_control_plane_agent_tables.py`` creates those three from their own
DDL, enumerates the migrated schema and fails when a table is in neither list,
so a new per-agent table cannot be forgotten by the legacy id repair or by
agent delete.
"""

from __future__ import annotations

# Control-plane tables whose rows belong to one agent definition. The legacy
# default-agent id repair rewrites the agent_id of every one of them.
PER_AGENT_TABLES: tuple[str, ...] = (
    "cp_agent_assignments",
    "cp_agent_config_versions",
    "cp_agent_connections",
    "cp_agent_documents",
    "cp_agent_sections",
    "cp_apply_operations",
    "cp_bot_gateway_tokens",
    "cp_connection_discovery_runs",
    "cp_knowledge_assets",
    "cp_mcp_agent_connections",
    "cp_mcp_capability_policies",
    "cp_mcp_capability_snapshots",
    "cp_mcp_discovered_prompts",
    "cp_mcp_discovered_resources",
    "cp_mcp_discovered_tools",
    "cp_mcp_oauth_sessions",
    "cp_mcp_oauth_tokens",
    "cp_mcp_tool_policies",
    "cp_mcp_user_servers",
    "cp_policy_spend_ledger",
    "cp_secret_values",
    "cp_skill_assets",
    "cp_telegram_offsets",
    "cp_telegram_pending_updates",
    "cp_template_assets",
)

# Per-agent tables that hard delete does not purge yet. Their rows outlive the
# agent and reattach when the id is recreated (D-054); M2-E3-T3 decides what
# delete does with them.
AGENT_DELETE_RETAINED_TABLES: frozenset[str] = frozenset(
    {
        "cp_agent_assignments",
        "cp_bot_gateway_tokens",
        "cp_connection_discovery_runs",
        "cp_mcp_capability_policies",
        "cp_mcp_capability_snapshots",
        "cp_mcp_discovered_prompts",
        "cp_mcp_discovered_resources",
        "cp_mcp_user_servers",
        "cp_policy_spend_ledger",
        "cp_secret_values",
        "cp_telegram_offsets",
        "cp_telegram_pending_updates",
    }
)

# Per-agent tables that ``ControlPlaneManager.delete_agent`` purges before it
# removes the ``cp_agent_definitions`` row.
AGENT_DELETE_TABLES: tuple[str, ...] = tuple(
    table for table in PER_AGENT_TABLES if table not in AGENT_DELETE_RETAINED_TABLES
)

# Tables with an agent_id column that are not per-agent control-plane state:
# runtime state, history, audit, evaluation, knowledge, memory, channel,
# skill-package and squad rows written by the runtime and other services. The
# legacy id repair does not rewrite them, and agent delete leaves them so
# historical records survive.
AGENT_ID_TABLE_EXEMPTIONS: frozenset[str] = frozenset(
    {
        "answer_judgements",
        "answer_traces",
        "approved_guardrails",
        "approved_runbooks",
        "artifact_derivatives",
        "artifact_manifests",
        "audit_events",
        "channel_gateway_events",
        "channel_gateway_identities",
        "channel_pairing_codes",
        "channel_unknown_senders",
        "child_runs",
        "correction_events",
        "dead_letter_queue",
        "digest_preferences",
        "eval_run_batches",
        "eval_suite_cases",
        "eval_suites",
        "evaluation_cases",
        "evaluation_runs",
        "execution_episodes",
        "execution_reliability_stats",
        "improvement_proposal_effects",
        "improvement_proposals",
        "knowledge_candidates",
        "knowledge_chunks",
        "knowledge_documents",
        "knowledge_embeddings",
        "knowledge_entities",
        "knowledge_ingest_jobs",
        "knowledge_relations",
        "knowledge_source_registry",
        "memory_embedding_jobs",
        "memory_maintenance_log",
        "memory_quality_counters",
        "memory_recall_audit",
        "napkin_log",
        "onboarding_readiness_runs",
        "query_history",
        "release_quality_runs",
        "response_cache",
        "retrieval_bundles",
        "retrieval_traces",
        "run_graph_edges",
        "run_graph_nodes",
        "run_replay_snapshots",
        "runtime_artifacts",
        "runtime_attach_sessions",
        "runtime_browser_sessions",
        "runtime_checkpoints",
        "runtime_environments",
        "runtime_events",
        "runtime_guardrail_hits",
        "runtime_loop_cycles",
        "runtime_port_allocations",
        "runtime_processes",
        "runtime_queue_items",
        "runtime_recovery_actions",
        "runtime_resource_samples",
        "runtime_service_endpoints",
        "runtime_terminals",
        "runtime_warnings",
        "scheduled_jobs",
        "script_library",
        "sessions",
        "skill_package_events",
        "skill_packages",
        "squad_member_capabilities",
        "squad_thread_participants",
        "tasks",
        "trajectory_exports",
        "user_cost_totals",
        # Created at runtime, outside the migrations, so they may not exist and
        # the legacy id repair cannot rewrite them. Per-agent approval and
        # artifact state: M2-E3-T3 decides whether hard delete purges them.
        "approval_grants",
        "artifact_objects",
        "pending_approvals",
    }
)
