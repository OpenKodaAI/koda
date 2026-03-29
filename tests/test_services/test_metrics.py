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
    PROCEDURAL_HITS,
    PROCEDURAL_MISSES,
    PROVIDER_ADAPTER_CONTRACT_ERRORS_TOTAL,
    PROVIDER_COMPATIBILITY_STATE,
    PROVIDER_RESUME_DEGRADED_TOTAL,
    QUEUE_DEPTH,
    REQUEST_DURATION,
    REQUESTS_TOTAL,
    ROLLBACK_NEEDED,
    STALE_SOURCE_USAGE,
    TOOL_EXECUTIONS,
    VERIFICATION_BEFORE_FINALIZE,
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
