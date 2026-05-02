"""OpenTelemetry tracing scaffold (Phase 2D).

Two contracts to honor:

1. **Zero hard dep**: ``import koda.observability.tracing`` must
   succeed even when ``opentelemetry-sdk`` is not installed. Every
   public helper degrades to a no-op so existing deploys can land this
   module without bumping requirements.
2. **Single config knob**: tracing turns on when
   ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set in env. The standard OTel
   resource attributes (``OTEL_SERVICE_NAME``, ``OTEL_RESOURCE_ATTRIBUTES``)
   are honored automatically by the OTLP exporter — operators don't
   need a koda-specific schema.

Usage::

    from koda.observability import init_tracing, start_span
    init_tracing("koda-web")
    with start_span("queue_manager.enqueue", agent_id=agent_id):
        ...

The supervisor / worker / sidecar entrypoints call ``init_tracing``
once during boot. Hot-path code uses ``start_span`` as a context
manager. Cross-process propagation rides on the existing internal_rpc
metadata via ``inject_grpc_context`` / ``extract_grpc_context``.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from koda.logging_config import get_logger

log = get_logger(__name__)

_TRACING_ENABLED = False
_TRACER: Any = None


def _otel_endpoint_configured() -> bool:
    return bool((os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip())


def is_tracing_enabled() -> bool:
    """True after a successful ``init_tracing`` call."""
    return _TRACING_ENABLED


def init_tracing(service_name: str) -> bool:
    """Wire the OpenTelemetry SDK + OTLP exporter for ``service_name``.

    Returns True when tracing is now active, False when it is not (no
    endpoint configured, SDK packages missing, or already initialized).
    Safe to call multiple times — subsequent calls return False.
    """
    global _TRACING_ENABLED, _TRACER
    if _TRACING_ENABLED:
        return False
    if not _otel_endpoint_configured():
        log.debug("tracing_endpoint_not_configured", service=service_name)
        return False
    try:
        from opentelemetry import trace  # type: ignore[import-not-found]
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # type: ignore[import-not-found]
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource  # type: ignore[import-not-found]
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import-not-found]
        from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore[import-not-found]
    except Exception:
        log.warning(
            "tracing_packages_missing_falling_back_to_noop",
            service=service_name,
            hint="pip install opentelemetry-sdk opentelemetry-exporter-otlp",
        )
        return False
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    _TRACER = trace.get_tracer("koda")
    _TRACING_ENABLED = True
    log.info("tracing_initialized", service=service_name)
    return True


@contextmanager
def start_span(name: str, **attributes: Any) -> Iterator[Any]:
    """Open an OTel span; degrade to a no-op when tracing is disabled.

    The yielded value is the span object when tracing is active, or
    ``None`` when it is not — callers should only set attributes via
    the kwargs argument so they don't have to branch on the return.
    """
    if not _TRACING_ENABLED or _TRACER is None:
        yield None
        return
    safe_attrs = {str(k): _coerce_attribute(v) for k, v in attributes.items() if v is not None}
    with _TRACER.start_as_current_span(name, attributes=safe_attrs) as span:
        yield span


def _coerce_attribute(value: Any) -> Any:
    """OTel only accepts primitive (or list of primitive) attribute
    values. Coerce common surrounding types to strings so the helper
    cannot fail at attribute-set time."""
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_coerce_attribute(v) for v in value]
    return str(value)


def inject_grpc_context(metadata: list[tuple[str, str]] | None = None) -> list[tuple[str, str]]:
    """Add the current OTel context to a gRPC metadata list.

    Returns the augmented list; callers can pass it as
    ``metadata=client.inject_grpc_context()`` when invoking a stub
    method. When tracing is disabled this is a passthrough (returns
    the input untouched).
    """
    md: list[tuple[str, str]] = list(metadata or [])
    if not _TRACING_ENABLED:
        return md
    try:
        from opentelemetry.propagate import inject  # type: ignore[import-not-found]
    except Exception:
        return md
    carrier: dict[str, str] = {}
    inject(carrier)
    md.extend((key, value) for key, value in carrier.items())
    return md


def extract_grpc_context(metadata: list[tuple[str, str]] | dict[str, str] | None) -> Any:
    """Extract an OTel context from incoming gRPC metadata.

    Returns the context object or ``None`` when tracing is disabled /
    no context found. Callers wrap their handler body with
    ``with trace.use_span(span, end_on_exit=False)`` when needed; the
    helper exists primarily so the metadata→context conversion stays
    in one place.
    """
    if not _TRACING_ENABLED or not metadata:
        return None
    try:
        from opentelemetry.propagate import extract  # type: ignore[import-not-found]
    except Exception:
        return None
    if isinstance(metadata, dict):
        carrier = {str(k): str(v) for k, v in metadata.items()}
    else:
        carrier = {str(k): str(v) for k, v in metadata}
    return extract(carrier)


def _reset_for_tests() -> None:
    """Test helper: clear the singleton state so tests can re-init.
    Production never calls this."""
    global _TRACING_ENABLED, _TRACER
    _TRACING_ENABLED = False
    _TRACER = None
