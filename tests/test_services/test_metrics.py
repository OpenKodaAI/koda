"""Tests for Prometheus metrics module."""

from koda.services.metrics import (
    ACTIVE_TASKS,
    CACHE_HITS,
    CACHE_MISSES,
    CANDIDATE_PROMOTIONS,
    CLAUDE_EXECUTION,
    COST_PER_QUERY,
    COST_TOTAL,
    DEPENDENCY_LATENCY,
    DEPENDENCY_REQUESTS,
    EXECUTION_CONFIDENCE_BLOCKS,
    EXECUTION_CONFIDENCE_SCORE,
    GROUNDED_ANSWERS,
    HUMAN_OVERRIDE,
    KNOWLEDGE_HITS,
    KNOWLEDGE_MISSES,
    KNOWLEDGE_RECALL_DURATION,
    MEMORY_RECALL_DURATION,
    OPS_BENCHMARK_DURATION,
    OPS_BENCHMARK_RUNS,
    PROCEDURAL_HITS,
    PROCEDURAL_MISSES,
    PROVIDER_ADAPTER_CONTRACT_ERRORS_TOTAL,
    PROVIDER_COMPATIBILITY_STATE,
    PROVIDER_RESUME_DEGRADED_TOTAL,
    QUALITY_COCKPIT_FAILURES,
    QUEUE_DEPTH,
    RELEASE_BLOCKERS,
    REQUEST_DURATION,
    REQUESTS_TOTAL,
    ROLLBACK_NEEDED,
    ROUTE_OUTCOME_EVENTS,
    RUN_GRAPH_COMPLETENESS_GATES,
    SKILL_PACKAGE_EVENTS,
    SQUAD_HANDOFF_EVENTS,
    SQUAD_ROUTE_QUALITY,
    SQUAD_SYNTHESIS_GATE,
    STALE_SOURCE_USAGE,
    TOOL_EXECUTIONS,
    VERIFICATION_BEFORE_FINALIZE,
    WORKSPACE_IMPORT_APPLIES_TOTAL,
    WORKSPACE_IMPORT_BLOCKED_TOTAL,
    WORKSPACE_IMPORT_LIMIT_HITS_TOTAL,
    WORKSPACE_IMPORT_SCANS_TOTAL,
    WORKSPACE_IMPORT_SOURCES_TOTAL,
)


class TestMetricsExist:
    def test_all_metrics_defined(self):
        assert REQUESTS_TOTAL is not None
        assert REQUEST_DURATION is not None
        assert CLAUDE_EXECUTION is not None
        assert ACTIVE_TASKS is not None
        assert QUEUE_DEPTH is not None
        assert COST_PER_QUERY is not None
        assert COST_TOTAL is not None
        assert DEPENDENCY_REQUESTS is not None
        assert DEPENDENCY_LATENCY is not None
        assert TOOL_EXECUTIONS is not None
        assert CACHE_HITS is not None
        assert CACHE_MISSES is not None
        assert MEMORY_RECALL_DURATION is not None
        assert KNOWLEDGE_RECALL_DURATION is not None
        assert KNOWLEDGE_HITS is not None
        assert KNOWLEDGE_MISSES is not None
        assert PROCEDURAL_HITS is not None
        assert PROCEDURAL_MISSES is not None
        assert EXECUTION_CONFIDENCE_SCORE is not None
        assert EXECUTION_CONFIDENCE_BLOCKS is not None
        assert GROUNDED_ANSWERS is not None
        assert VERIFICATION_BEFORE_FINALIZE is not None
        assert CANDIDATE_PROMOTIONS is not None
        assert HUMAN_OVERRIDE is not None
        assert ROLLBACK_NEEDED is not None
        assert STALE_SOURCE_USAGE is not None
        assert PROVIDER_COMPATIBILITY_STATE is not None
        assert PROVIDER_RESUME_DEGRADED_TOTAL is not None
        assert PROVIDER_ADAPTER_CONTRACT_ERRORS_TOTAL is not None
        assert WORKSPACE_IMPORT_SCANS_TOTAL is not None
        assert WORKSPACE_IMPORT_SOURCES_TOTAL is not None
        assert WORKSPACE_IMPORT_APPLIES_TOTAL is not None
        assert WORKSPACE_IMPORT_BLOCKED_TOTAL is not None
        assert WORKSPACE_IMPORT_LIMIT_HITS_TOTAL is not None
        assert SQUAD_HANDOFF_EVENTS is not None
        assert SQUAD_ROUTE_QUALITY is not None
        assert SQUAD_SYNTHESIS_GATE is not None
        assert QUALITY_COCKPIT_FAILURES is not None
        assert RUN_GRAPH_COMPLETENESS_GATES is not None
        assert ROUTE_OUTCOME_EVENTS is not None
        assert SKILL_PACKAGE_EVENTS is not None
        assert RELEASE_BLOCKERS is not None
        assert OPS_BENCHMARK_RUNS is not None
        assert OPS_BENCHMARK_DURATION is not None

    def test_counter_increment(self):
        REQUESTS_TOTAL.labels(agent_id="test", status="completed").inc()

    def test_histogram_observe(self):
        REQUEST_DURATION.labels(
            agent_id="test",
            provider="claude",
            model="test-model",
        ).observe(1.5)

    def test_gauge_set(self):
        ACTIVE_TASKS.labels(agent_id="test").set(5)
        QUEUE_DEPTH.labels(agent_id="test").set(3)
        PROVIDER_COMPATIBILITY_STATE.labels(agent_id="test", provider="codex", turn_mode="resume_turn").set(1)

    def test_provider_counters_increment(self):
        PROVIDER_RESUME_DEGRADED_TOTAL.labels(agent_id="test", provider="codex").inc()
        PROVIDER_ADAPTER_CONTRACT_ERRORS_TOTAL.labels(
            agent_id="test",
            provider="codex",
            turn_mode="resume_turn",
        ).inc()

    def test_top_tier_metrics_accept_bounded_labels(self):
        RUN_GRAPH_COMPLETENESS_GATES.labels(
            agent_id="KODA",
            scenario="squad",
            status="failed",
            failure_category="missing_node_type",
        ).inc()
        ROUTE_OUTCOME_EVENTS.labels(
            agent_id="KODA",
            route_source="semantic",
            status="success",
            timeout="false",
        ).inc()
        SKILL_PACKAGE_EVENTS.labels(
            agent_id="KODA",
            event="evals_run",
            decision="allow",
            recommendation_status="recommended",
        ).inc()
        RELEASE_BLOCKERS.labels(
            agent_id="KODA",
            gate_id="run_graph_completeness",
            severity="high",
            status="failing",
        ).set(1)
        OPS_BENCHMARK_RUNS.labels(mode="quick", status="passed").inc()
        OPS_BENCHMARK_DURATION.labels(mode="quick").observe(0.25)


class TestMetricCatalog:
    FORBIDDEN_LABEL_NAMES = {
        "chat_id",
        "message",
        "path",
        "proposal_id",
        "raw_prompt",
        "raw_text",
        "run_id",
        "task_id",
        "text",
        "user_id",
    }

    def test_every_prometheus_metric_is_named_documented_and_prefixed(self):
        import koda.services.metrics as metrics

        seen = []
        for value in vars(metrics).values():
            actual_name = getattr(value, "_name", "")
            if not isinstance(actual_name, str) or not actual_name.startswith("koda_"):
                continue
            seen.append(actual_name)
            assert str(getattr(value, "_documentation", "")).strip(), actual_name
            assert actual_name == actual_name.lower(), actual_name
        assert len(seen) >= 80

    def test_metric_labels_stay_low_cardinality_and_safe(self):
        import koda.services.metrics as metrics

        for public_name, value in vars(metrics).items():
            actual_name = getattr(value, "_name", "")
            if not isinstance(actual_name, str) or not actual_name.startswith("koda_"):
                continue
            labels = tuple(getattr(value, "_labelnames", ()) or ())
            unsafe = self.FORBIDDEN_LABEL_NAMES.intersection(labels)
            assert not unsafe, f"{public_name} exposes unsafe/high-cardinality labels: {sorted(unsafe)}"
