"""Optional OpenTelemetry helpers for knowledge and answer pipelines."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from koda.knowledge.config import KNOWLEDGE_V2_OTEL_ENABLED


@contextmanager
def knowledge_span(name: str, **attributes: Any) -> Iterator[None]:
    """Create a best-effort OpenTelemetry span when the dependency is available."""
    if not KNOWLEDGE_V2_OTEL_ENABLED:
        yield
        return
    try:
        from opentelemetry import trace
    except Exception:
        yield
        return
    tracer = trace.get_tracer("koda.knowledge")
    with tracer.start_as_current_span(name) as span:
        for key, value in attributes.items():
            if value in (None, ""):
                continue
            span.set_attribute(f"knowledge.{key}", value)
        yield
