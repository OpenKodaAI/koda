"""Prometheus metrics for the Telegram coding agent runtime."""

try:
    from prometheus_client import Counter, Gauge, Histogram
except ModuleNotFoundError:  # pragma: no cover - exercised in lean test envs

    class _MetricChild:
        def inc(self, amount: float = 1.0) -> None:
            return

        def observe(self, value: float) -> None:
            return

        def set(self, value: float) -> None:
            return

    class _MetricFactory:
        def __init__(self, *args: object, **kwargs: object) -> None:
            return

        def labels(self, **kwargs: object) -> _MetricChild:
            return _MetricChild()

        def inc(self, amount: float = 1.0) -> None:
            return

        def observe(self, value: float) -> None:
            return

        def set(self, value: float) -> None:
            return

    Counter = Gauge = Histogram = _MetricFactory  # type: ignore[misc,assignment]

# --- Request metrics ---
REQUESTS_TOTAL = Counter(
    "koda_requests_total",
    "Total number of requests processed",
    ["agent_id", "status"],
)

REQUEST_DURATION = Histogram(
    "koda_request_duration_seconds",
    "End-to-end request duration",
    ["agent_id", "provider", "model"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1800),
)

# --- LLM runtime metrics ---
CLAUDE_EXECUTION = Histogram(
    "koda_claude_execution_seconds",
    "LLM execution duration by provider",
    ["agent_id", "provider", "model", "streaming"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1800),
)

# --- Task metrics ---
ACTIVE_TASKS = Gauge(
    "koda_active_tasks",
    "Number of currently active tasks",
    ["agent_id"],
)

QUEUE_DEPTH = Gauge(
    "koda_queue_depth",
    "Total number of queued items across all users",
    ["agent_id"],
)

# --- Cost metrics ---
COST_PER_QUERY = Histogram(
    "koda_cost_per_query_usd",
    "Cost per query in USD",
    ["agent_id", "provider", "model"],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0),
)

COST_TOTAL = Counter(
    "koda_cost_total_usd",
    "Cumulative cost in USD",
    ["agent_id", "provider", "model"],
)

# --- Dependency metrics ---
DEPENDENCY_REQUESTS = Counter(
    "koda_dependency_requests_total",
    "Requests to external dependencies",
    ["agent_id", "dependency", "status"],
)

DEPENDENCY_LATENCY = Histogram(
    "koda_dependency_latency_seconds",
    "Latency of dependency calls",
    ["agent_id", "dependency"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60),
)

# --- Provider compatibility metrics ---
PROVIDER_COMPATIBILITY_STATE = Gauge(
    "koda_provider_compatibility_state",
    "Provider compatibility state (0=unavailable, 1=degraded, 2=ready)",
    ["agent_id", "provider", "turn_mode"],
)

PROVIDER_RESUME_DEGRADED_TOTAL = Counter(
    "koda_provider_resume_degraded_total",
    "Resume attempts that had to degrade to transcript bootstrap",
    ["agent_id", "provider"],
)

PROVIDER_ADAPTER_CONTRACT_ERRORS_TOTAL = Counter(
    "koda_provider_adapter_contract_errors_total",
    "Provider CLI contract errors detected during execution",
    ["agent_id", "provider", "turn_mode"],
)

# --- Circuit breaker metrics ---
CIRCUIT_BREAKER_STATE = Gauge(
    "koda_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=half-open, 2=open)",
    ["agent_id", "dependency"],
)

# --- Tool metrics ---
TOOL_EXECUTIONS = Counter(
    "koda_tool_executions_total",
    "Agent tool executions",
    ["agent_id", "tool_name", "status"],
)

# --- Cache metrics ---
CACHE_HITS = Counter(
    "koda_cache_hits_total",
    "Cache hits",
    ["agent_id"],
)

CACHE_MISSES = Counter(
    "koda_cache_misses_total",
    "Cache misses",
    ["agent_id"],
)

# --- Memory metrics ---
MEMORY_RECALL_DURATION = Histogram(
    "koda_memory_recall_seconds",
    "Memory recall duration",
    ["agent_id"],
    buckets=(0.1, 0.5, 1, 2, 5, 10),
)

KNOWLEDGE_RECALL_DURATION = Histogram(
    "koda_knowledge_recall_seconds",
    "Grounded knowledge recall duration",
    ["agent_id"],
    buckets=(0.1, 0.5, 1, 2, 5, 10),
)

KNOWLEDGE_HITS = Counter(
    "koda_knowledge_hits_total",
    "Grounded knowledge recall hits",
    ["agent_id"],
)

KNOWLEDGE_MISSES = Counter(
    "koda_knowledge_misses_total",
    "Grounded knowledge recall misses",
    ["agent_id"],
)

KNOWLEDGE_TRACE_PERSISTED = Counter(
    "koda_knowledge_trace_persisted_total",
    "Persisted explainable retrieval traces",
    ["agent_id", "strategy"],
)

KNOWLEDGE_STRATEGY_SELECTIONS = Counter(
    "koda_knowledge_strategy_selections_total",
    "Knowledge retrieval strategy selections",
    ["agent_id", "strategy", "route"],
)

KNOWLEDGE_GROUNDING_SCORE = Histogram(
    "koda_knowledge_grounding_score",
    "Grounding score from knowledge retrieval traces",
    ["agent_id", "strategy"],
    buckets=(0.0, 0.25, 0.5, 0.65, 0.8, 0.9, 1.0),
)

KNOWLEDGE_CITATION_COVERAGE = Histogram(
    "koda_knowledge_citation_coverage",
    "Citation coverage for winning grounded sources",
    ["agent_id", "strategy"],
    buckets=(0.0, 0.25, 0.5, 0.75, 0.9, 1.0),
)

KNOWLEDGE_CITATION_SPAN_PRECISION = Histogram(
    "koda_knowledge_citation_span_precision",
    "Precision of structured answer citation spans",
    ["agent_id", "strategy"],
    buckets=(0.0, 0.25, 0.5, 0.75, 0.9, 1.0),
)

KNOWLEDGE_CONTRADICTION_ESCAPE = Counter(
    "koda_knowledge_contradiction_escape_total",
    "Contradiction escapes detected by the knowledge judge",
    ["agent_id", "strategy", "status"],
)

KNOWLEDGE_JUDGE_OUTCOMES = Counter(
    "koda_knowledge_judge_outcomes_total",
    "Final outcomes from the structured answer judge",
    ["agent_id", "status"],
)

PROCEDURAL_HITS = Counter(
    "koda_procedural_hits_total",
    "Procedural memory retrieval hits",
    ["agent_id"],
)

PROCEDURAL_MISSES = Counter(
    "koda_procedural_misses_total",
    "Procedural memory retrieval misses",
    ["agent_id"],
)

MEMORY_EXTRACTIONS = Counter(
    "koda_memory_extractions_total",
    "Memory extraction outcomes",
    ["agent_id", "status"],
)

MEMORY_RECALL_SELECTIONS = Counter(
    "koda_memory_recall_selections_total",
    "Selected recall items by layer",
    ["agent_id", "layer", "retrieval_source"],
)

MEMORY_RECALL_DISCARDS = Counter(
    "koda_memory_recall_discards_total",
    "Discarded recall candidates by reason",
    ["agent_id", "reason"],
)

MEMORY_DEDUP_DECISIONS = Counter(
    "koda_memory_dedup_decisions_total",
    "Memory deduplication decisions by reason",
    ["agent_id", "reason"],
)

MEMORY_STATUS_TRANSITIONS = Counter(
    "koda_memory_status_transitions_total",
    "Memory lifecycle transitions by agent",
    ["agent_id", "from_status", "to_status"],
)

MEMORY_CONFLICT_RESOLUTIONS = Counter(
    "koda_memory_conflict_resolutions_total",
    "Conflict resolution outcomes in memory recall and storage",
    ["agent_id", "outcome"],
)

MEMORY_EMBEDDING_REPAIRS = Counter(
    "koda_memory_embedding_repairs_total",
    "Embedding repair attempts and successes",
    ["agent_id", "status"],
)

MEMORY_EMBEDDING_QUEUE = Gauge(
    "koda_memory_embedding_queue",
    "Embedding repair jobs currently queued by status",
    ["agent_id", "status"],
)

MEMORY_EMBEDDING_REPAIR_LATENCY = Histogram(
    "koda_memory_embedding_repair_latency_seconds",
    "Latency for embedding repair batches",
    ["agent_id"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60),
)

EXECUTION_CONFIDENCE_SCORE = Histogram(
    "koda_execution_confidence_score",
    "Confidence scores evaluated before sensitive write steps",
    ["agent_id", "mode"],
    buckets=(0.0, 0.25, 0.5, 0.65, 0.8, 1.0),
)

EXECUTION_CONFIDENCE_BLOCKS = Counter(
    "koda_execution_confidence_blocks_total",
    "Number of write steps blocked by the confidence gate",
    ["agent_id", "reason"],
)

GROUNDED_ANSWERS = Counter(
    "koda_grounded_answers_total",
    "Queries completed with or without grounded sources",
    ["agent_id", "status"],
)

VERIFICATION_BEFORE_FINALIZE = Counter(
    "koda_verification_before_finalize_total",
    "Whether post-write verification happened before the final answer",
    ["agent_id", "task_kind", "status"],
)

KNOWLEDGE_EVALUATION_RUNS = Counter(
    "koda_knowledge_evaluation_runs_total",
    "Offline knowledge evaluation runs by strategy and metric family",
    ["agent_id", "strategy", "result"],
)

KNOWLEDGE_EVALUATION_SCORE = Histogram(
    "koda_knowledge_evaluation_score",
    "Offline knowledge evaluation scores",
    ["agent_id", "strategy", "metric"],
    buckets=(0.0, 0.25, 0.5, 0.65, 0.8, 0.9, 1.0),
)

# --- Runtime environment metrics ---
RUNTIME_ACTIVE_ENVS = Gauge(
    "koda_runtime_active_envs",
    "Number of currently active or retained runtime environments",
)

RUNTIME_PHASE_TOTAL = Gauge(
    "koda_runtime_phase_total",
    "Runtime environments grouped by phase",
    ["phase"],
)

RUNTIME_ORPHAN_ENVS = Counter(
    "koda_runtime_orphan_envs_total",
    "Runtime environments marked orphaned/recoverable after a stale sweep",
)

RUNTIME_CHECKPOINT_FAILURES_TOTAL = Counter(
    "koda_runtime_checkpoint_failures_total",
    "Checkpoint failures during runtime retention",
)

RUNTIME_RECOVERIES_TOTAL = Counter(
    "koda_runtime_recoveries_total",
    "Recovery actions that could reattach an environment",
)

RUNTIME_CLEANUP_BLOCKED_TOTAL = Counter(
    "koda_runtime_cleanup_blocked_total",
    "Cleanup requests blocked due to pinning or unsafe phase",
)

RUNTIME_BROWSER_SESSIONS_ACTIVE = Gauge(
    "koda_runtime_browser_sessions_active",
    "Active browser sessions attached to runtime environments",
)

RUNTIME_PTYS_ACTIVE = Gauge(
    "koda_runtime_ptys_active",
    "Tracked PTYs/terminals attached to runtime environments",
)

RUNTIME_RESOURCE_CPU_PERCENT = Gauge(
    "koda_runtime_resource_cpu_percent",
    "Latest sampled CPU percent for a runtime environment",
)

RUNTIME_RESOURCE_RSS_BYTES = Gauge(
    "koda_runtime_resource_rss_bytes",
    "Latest sampled RSS bytes for a runtime environment",
)

RUNTIME_WORKTREE_DISK_BYTES = Gauge(
    "koda_runtime_worktree_disk_bytes",
    "Latest sampled disk usage for a runtime worktree",
)

RUNTIME_WS_CLIENTS_ACTIVE = Gauge(
    "koda_runtime_ws_clients_active",
    "Active runtime websocket clients across event, terminal, and browser streams",
)

RUNTIME_TERMINAL_ATTACH_SESSIONS_ACTIVE = Gauge(
    "koda_runtime_terminal_attach_sessions_active",
    "Active terminal attach sessions",
)

RUNTIME_BROWSER_ATTACH_SESSIONS_ACTIVE = Gauge(
    "koda_runtime_browser_attach_sessions_active",
    "Active browser attach sessions",
)

RUNTIME_GUARDRAIL_HITS_TOTAL = Counter(
    "koda_runtime_guardrail_hits_total",
    "Guardrail hits that paused or stopped a runtime environment",
    ["guardrail_type"],
)

RUNTIME_PAUSE_EVENTS_TOTAL = Counter(
    "koda_runtime_pause_events_total",
    "Runtime pause requests and activations",
)

RUNTIME_RESUME_EVENTS_TOTAL = Counter(
    "koda_runtime_resume_events_total",
    "Runtime resume events after operator intervention",
)

RUNTIME_SAVE_VERIFY_FAILURES_TOTAL = Counter(
    "koda_runtime_save_verify_failures_total",
    "Save verification failures before cleanup",
)

RUNTIME_VNC_SESSIONS_ACTIVE = Gauge(
    "koda_runtime_vnc_sessions_active",
    "Active VNC/noVNC browser live sessions",
)

CANDIDATE_PROMOTIONS = Counter(
    "koda_candidate_promotions_total",
    "Knowledge candidate review outcomes",
    ["agent_id", "status"],
)

HUMAN_OVERRIDE = Counter(
    "koda_human_override_total",
    "Human approvals, denials, or timeouts during write execution",
    ["agent_id", "decision"],
)

ROLLBACK_NEEDED = Counter(
    "koda_rollback_needed_total",
    "Tasks that ended with rollback-worthy failure signals",
    ["agent_id", "task_kind"],
)

STALE_SOURCE_USAGE = Counter(
    "koda_stale_source_usage_total",
    "Queries that relied on at least one stale grounded source",
    ["agent_id", "layer"],
)

RUNBOOK_HITS = Counter(
    "koda_runbook_hits_total",
    "Whether a task resolved at least one approved runbook in runtime knowledge",
    ["agent_id", "task_kind", "status"],
)

HUMAN_CORRECTION_EVENTS = Counter(
    "koda_human_correction_events_total",
    "Structured human feedback events recorded after task completion",
    ["agent_id", "feedback_type"],
)

MEMORY_UTILITY_EVENTS = Counter(
    "koda_memory_utility_events_total",
    "Human-signaled utility outcomes for memory-guided work",
    ["agent_id", "outcome"],
)

RUNBOOK_GOVERNANCE_ACTIONS = Counter(
    "koda_runbook_governance_actions_total",
    "Governance actions applied to approved runbooks",
    ["agent_id", "action"],
)

RUNBOOK_GOVERNANCE_LATENCY = Histogram(
    "koda_runbook_governance_latency_seconds",
    "Latency for one runbook governance pass",
    ["agent_id"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60),
)

AUTONOMY_TIER_DISTRIBUTION = Counter(
    "koda_autonomy_tier_distribution_total",
    "Observed task executions by autonomy tier",
    ["agent_id", "task_kind", "tier"],
)

# --- Scheduler metrics ---
SCHEDULED_ACTIVE_JOBS = Gauge(
    "koda_scheduled_active_jobs",
    "Scheduled jobs currently managed by the unified scheduler",
    ["agent_id", "status"],
)

SCHEDULED_DUE_RUNS = Gauge(
    "koda_scheduled_due_runs",
    "Scheduled runs currently due for dispatch",
    ["agent_id"],
)

SCHEDULED_LEASED_RUNS = Gauge(
    "koda_scheduled_leased_runs",
    "Scheduled runs currently leased by a dispatcher",
    ["agent_id"],
)

SCHEDULED_RUN_TRANSITIONS = Counter(
    "koda_scheduled_run_transitions_total",
    "Scheduled run terminal or retry transitions",
    ["agent_id", "status"],
)

SCHEDULED_NOTIFICATION_FAILURES = Counter(
    "koda_scheduled_notification_failures_total",
    "Scheduler notification failures",
    ["agent_id"],
)
