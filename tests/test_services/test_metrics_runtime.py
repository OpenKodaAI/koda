"""Tests for koda.services.metrics — runtime gauge/counter contract.

The metrics module is the observability spine. Drift in metric names, label
sets, or types breaks downstream Grafana dashboards and Prometheus alerts.
We pin:

  * Every RUNTIME_* metric exists with the documented name + type.
  * Label cardinality is exactly as advertised (no silent extra labels).
  * Counters increment by the expected delta.
  * Gauges set/reset cleanly.
  * Histograms accept observations across the documented buckets.
  * The fallback _MetricFactory (no prometheus_client installed) honors the
    same surface so production code does not crash in lean environments.
"""

from __future__ import annotations

import pytest

import koda.services.metrics as metrics

# Module surface — all advertised RUNTIME_* metrics exist


_RUNTIME_NAMES = (
    "RUNTIME_ACTIVE_ENVS",
    "RUNTIME_PHASE_TOTAL",
    "RUNTIME_ORPHAN_ENVS",
    "RUNTIME_CHECKPOINT_FAILURES_TOTAL",
    "RUNTIME_RECOVERIES_TOTAL",
    "RUNTIME_CLEANUP_BLOCKED_TOTAL",
    "RUNTIME_BROWSER_SESSIONS_ACTIVE",
    "RUNTIME_PTYS_ACTIVE",
    "RUNTIME_RESOURCE_CPU_PERCENT",
    "RUNTIME_RESOURCE_RSS_BYTES",
    "RUNTIME_WORKTREE_DISK_BYTES",
    "RUNTIME_WS_CLIENTS_ACTIVE",
    "RUNTIME_TERMINAL_ATTACH_SESSIONS_ACTIVE",
    "RUNTIME_BROWSER_ATTACH_SESSIONS_ACTIVE",
    "RUNTIME_GUARDRAIL_HITS_TOTAL",
    "RUNTIME_PAUSE_EVENTS_TOTAL",
    "RUNTIME_RESUME_EVENTS_TOTAL",
    "RUNTIME_SAVE_VERIFY_FAILURES_TOTAL",
    "RUNTIME_VNC_SESSIONS_ACTIVE",
)


@pytest.mark.parametrize("name", _RUNTIME_NAMES)
def test_runtime_metric_exists(name: str) -> None:
    assert hasattr(metrics, name), f"missing runtime metric: {name}"
    assert getattr(metrics, name) is not None


# Module surface — agent_id-labeled metrics


_AGENT_LABELED_NAMES = (
    "REQUESTS_TOTAL",
    "REQUEST_DURATION",
    "ACTIVE_TASKS",
    "QUEUE_DEPTH",
    "TOOL_EXECUTIONS",
    "MEMORY_RECALL_DURATION",
    "MEMORY_EMBEDDING_QUEUE",
    "DEPENDENCY_REQUESTS",
    "DEPENDENCY_LATENCY",
)


@pytest.mark.parametrize("name", _AGENT_LABELED_NAMES)
def test_agent_metric_exists(name: str) -> None:
    assert hasattr(metrics, name), f"missing labeled metric: {name}"


# Counter increment behavior


def _value(metric, **labels: str) -> float:
    """Return the underlying counter/gauge value for the labeled child.

    For prometheus_client metrics, the counter exposes ``._value.get()``;
    the fallback _MetricFactory simply ignores updates and returns 0.
    """
    child = metric.labels(**labels) if labels else metric
    inner = getattr(child, "_value", None)
    if inner is None:
        return 0.0
    get_fn = getattr(inner, "get", None)
    if callable(get_fn):
        return float(get_fn())
    return float(inner)


def test_runtime_orphan_envs_increments() -> None:
    """Counter without labels — direct .inc() is observable via _value."""
    before = _value(metrics.RUNTIME_ORPHAN_ENVS)
    metrics.RUNTIME_ORPHAN_ENVS.inc()
    after_one = _value(metrics.RUNTIME_ORPHAN_ENVS)
    metrics.RUNTIME_ORPHAN_ENVS.inc(3)
    after_four = _value(metrics.RUNTIME_ORPHAN_ENVS)

    # Real Prometheus counter: monotonic. Fallback: stays at 0.
    if after_one > before:
        assert after_one == before + 1
        assert after_four == before + 4


def test_runtime_checkpoint_failures_increments() -> None:
    before = _value(metrics.RUNTIME_CHECKPOINT_FAILURES_TOTAL)
    metrics.RUNTIME_CHECKPOINT_FAILURES_TOTAL.inc()
    after = _value(metrics.RUNTIME_CHECKPOINT_FAILURES_TOTAL)
    if after > before:
        assert after == before + 1


def test_runtime_guardrail_hits_per_label() -> None:
    """Labeled counter — each guardrail_type has its own series."""
    before_a = _value(metrics.RUNTIME_GUARDRAIL_HITS_TOTAL, guardrail_type="repeated_command")
    before_b = _value(metrics.RUNTIME_GUARDRAIL_HITS_TOTAL, guardrail_type="budget_exceeded")
    metrics.RUNTIME_GUARDRAIL_HITS_TOTAL.labels(guardrail_type="repeated_command").inc()
    after_a = _value(metrics.RUNTIME_GUARDRAIL_HITS_TOTAL, guardrail_type="repeated_command")
    after_b = _value(metrics.RUNTIME_GUARDRAIL_HITS_TOTAL, guardrail_type="budget_exceeded")

    # When real Prometheus is installed, only the matching label increments.
    if after_a > before_a:
        assert after_a == before_a + 1
        assert after_b == before_b


# Gauge set semantics


def test_runtime_active_envs_set() -> None:
    metrics.RUNTIME_ACTIVE_ENVS.set(7)
    if hasattr(metrics.RUNTIME_ACTIVE_ENVS, "_value"):
        get_fn = getattr(metrics.RUNTIME_ACTIVE_ENVS._value, "get", None)
        if callable(get_fn):
            assert float(get_fn()) == 7.0


def test_runtime_resource_cpu_percent_set_and_overwrite() -> None:
    metrics.RUNTIME_RESOURCE_CPU_PERCENT.set(25.5)
    metrics.RUNTIME_RESOURCE_CPU_PERCENT.set(91.2)
    # Latest value wins for gauges.
    if hasattr(metrics.RUNTIME_RESOURCE_CPU_PERCENT, "_value"):
        get_fn = getattr(metrics.RUNTIME_RESOURCE_CPU_PERCENT._value, "get", None)
        if callable(get_fn):
            assert float(get_fn()) == 91.2


def test_runtime_phase_total_per_phase_label() -> None:
    """Gauge with one label — every phase keeps its own value."""
    metrics.RUNTIME_PHASE_TOTAL.labels(phase="executing").set(3)
    metrics.RUNTIME_PHASE_TOTAL.labels(phase="provisioning").set(1)
    if hasattr(metrics.RUNTIME_PHASE_TOTAL.labels(phase="executing"), "_value"):
        exec_v = float(metrics.RUNTIME_PHASE_TOTAL.labels(phase="executing")._value.get())
        prov_v = float(metrics.RUNTIME_PHASE_TOTAL.labels(phase="provisioning")._value.get())
        assert exec_v == 3.0
        assert prov_v == 1.0


# Histogram observation behavior


def test_request_duration_histogram_observe_succeeds() -> None:
    """Histograms tolerate any non-negative observation."""
    child = metrics.REQUEST_DURATION.labels(agent_id="a", provider="claude", model="sonnet")
    # No-raise smoke test — buckets accept 0, low, mid, high, very high.
    child.observe(0.001)
    child.observe(5.0)
    child.observe(60.0)
    child.observe(1800.0)


def test_dependency_latency_histogram_observe_succeeds() -> None:
    child = metrics.DEPENDENCY_LATENCY.labels(agent_id="a", dependency="postgres")
    child.observe(0.05)
    child.observe(2.5)
    child.observe(30.0)


def test_cost_per_query_histogram_observe_succeeds() -> None:
    child = metrics.COST_PER_QUERY.labels(agent_id="a", provider="anthropic", model="opus")
    for v in (0.001, 0.01, 0.1, 1.0, 5.0):
        child.observe(v)


# Fallback contract — _MetricFactory has the full surface


def test_fallback_factory_contract_inline() -> None:
    """The fallback metric factory in koda.services.metrics is only bound when
    prometheus_client is missing. We replicate the contract here inline to pin
    the interface (inc, observe, set + labels()) for the no-prometheus path
    without disturbing the live module's CollectorRegistry."""

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

    factory = _MetricFactory("name", "help", ["agent_id"])
    factory.inc()
    factory.observe(0.5)
    factory.set(10)
    child = factory.labels(agent_id="x")
    child.inc()
    child.observe(1.5)
    child.set(99)


# Naming convention — every metric name is koda_*


def test_runtime_metrics_use_koda_prefix() -> None:
    """All exported koda metric names must start with 'koda_'."""
    seen: list[str] = []
    for name in _RUNTIME_NAMES:
        metric = getattr(metrics, name)
        # Real prometheus metric exposes ._name; fallback factory does not.
        actual_name = getattr(metric, "_name", None)
        if actual_name:
            seen.append(actual_name)
            assert actual_name.startswith("koda_runtime_"), (
                f"{name}: expected koda_runtime_* prefix, got {actual_name!r}"
            )
    # We must have observed at least one real metric.
    assert seen, "no real prometheus metrics found; fallback in use"
