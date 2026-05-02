"""Phase A.4 — verify OTel scaffold is actually invoked by the runtime.

Without these tests the tracing scaffold could land but never be
called (which is exactly the gap A.4 was created to close). The tests
are textual + import-time checks so they stay stable through formatter
reflows and don't require a live OTel collector.

Three invariants:

1. ``init_tracing`` must be called by every entrypoint that runs in
   production (``koda/__main__.py`` worker boot, supervisor ``start``).
2. ``start_span`` must wrap the dispatcher's hot path so traces show
   the worker → tool_dispatcher hierarchy.
3. The ``observability`` package must export a stable public surface
   so future call sites can import without circular trouble.
"""

from __future__ import annotations

from pathlib import Path


def _read_source(rel_path: str) -> str:
    return Path(rel_path).read_text(encoding="utf-8")


def test_main_worker_calls_init_tracing() -> None:
    src = _read_source("koda/__main__.py")
    assert "from koda.observability import init_tracing" in src or "from koda.observability" in src
    assert "init_tracing(" in src, (
        "koda/__main__.py must call init_tracing so worker spans are exported "
        "when OTEL_EXPORTER_OTLP_ENDPOINT is configured."
    )


def test_supervisor_start_calls_init_tracing() -> None:
    src = _read_source("koda/control_plane/supervisor.py")
    assert "init_tracing(" in src
    assert "koda-supervisor" in src, (
        "supervisor must register itself under a distinct OTel service "
        "name so the collector separates worker vs supervisor spans."
    )


def test_tool_dispatcher_wraps_execute_tool_in_span() -> None:
    src = _read_source("koda/services/tool_dispatcher.py")
    assert "from koda.observability import start_span" in src
    assert (
        'start_span(\n        "tool_dispatcher.execute_tool"' in src
        or 'start_span("tool_dispatcher.execute_tool"' in src
    )


def test_observability_package_exports_public_surface() -> None:
    from koda.observability import (
        extract_grpc_context,
        init_tracing,
        inject_grpc_context,
        is_tracing_enabled,
        start_span,
    )

    assert callable(init_tracing)
    assert callable(start_span)
    assert callable(inject_grpc_context)
    assert callable(extract_grpc_context)
    assert callable(is_tracing_enabled)


def test_init_tracing_is_idempotent_and_returns_false_without_endpoint(monkeypatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    from koda.observability import tracing

    tracing._reset_for_tests()
    assert tracing.init_tracing("any-service") is False
    # Second call still returns False — never throws even when
    # called repeatedly during reload-style test runs.
    assert tracing.init_tracing("any-service") is False


def test_start_span_no_op_does_not_swallow_exceptions(monkeypatch) -> None:
    """When tracing is disabled, the context manager must propagate
    exceptions raised inside the with-block — otherwise wrapping hot
    paths in a span would silently mask bugs."""
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    from koda.observability import start_span, tracing

    tracing._reset_for_tests()

    class _Boom(RuntimeError):
        pass

    raised = False
    try:
        with start_span("op"):
            raise _Boom("original")
    except _Boom:
        raised = True
    assert raised, "start_span no-op must NOT suppress exceptions"
