"""Bench: tracing no-op context manager overhead.

The dispatcher wraps every tool call in ``with start_span(...):``.
When OTLP is unset, the span must be a near-zero context manager so
disabled tracing has no impact on the hot path."""

from __future__ import annotations

import pytest

from koda.observability import start_span, tracing

from .conftest import load_baseline, measure_ns_per_op


@pytest.fixture(autouse=True)
def _disable_tracing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    tracing._reset_for_tests()


def test_start_span_noop_within_baseline() -> None:
    def _call() -> None:
        with start_span("hot.path", agent_id="A"):
            pass

    measured = measure_ns_per_op(_call, iters=20_000)
    baseline = load_baseline("tracing_noop")
    assert measured < baseline["max_ns"], (
        f"tracing no-op regressed: {measured:.0f}ns/op > {baseline['max_ns']}ns/op. "
        f"This affects every tool call; even small regressions compound."
    )
