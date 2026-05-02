"""Cross-cutting observability scaffolding.

Phase 2D of ``docs/architecture/production-deployment-roadmap.md``
introduces distributed tracing across web → control-plane API →
worker → sidecar → DB. This package owns the wiring; the actual
exporters / vendors (Tempo, Honeycomb, Datadog) are an operational
choice and configured via standard ``OTEL_*`` env vars at boot.

Design rule: *all* OpenTelemetry imports are optional. When the
``opentelemetry-sdk`` distribution is not installed (or
``OTEL_EXPORTER_OTLP_ENDPOINT`` is unset) every helper degrades to a
no-op so the runtime never imposes a hard dependency on tracing.
"""

from koda.observability.tracing import (
    extract_grpc_context,
    init_tracing,
    inject_grpc_context,
    is_tracing_enabled,
    start_span,
)

__all__ = [
    "extract_grpc_context",
    "init_tracing",
    "inject_grpc_context",
    "is_tracing_enabled",
    "start_span",
]
