"""Phase 2D — distributed tracing scaffold.

Two invariants this scaffold MUST hold so the rest of the codebase
can call into it freely:

1. ``import koda.observability.tracing`` succeeds even without
   ``opentelemetry-sdk`` installed. Existing deploys can land this
   module without a dep bump.
2. Every public helper degrades to a no-op when tracing is disabled —
   ``start_span`` yields ``None``; ``inject_grpc_context`` is a
   passthrough; ``init_tracing`` returns ``False`` when no endpoint
   is configured.

Live OTLP export is exercised in integration tests against a real
collector — out of scope here.
"""

from __future__ import annotations

import pytest

from koda.observability import tracing


@pytest.fixture(autouse=True)
def _reset_tracing() -> None:
    tracing._reset_for_tests()


def test_init_tracing_returns_false_when_endpoint_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    assert tracing.init_tracing("koda-test") is False
    assert tracing.is_tracing_enabled() is False


def test_init_tracing_returns_false_when_sdk_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    # Block every opentelemetry import as if the package wasn't installed.
    import builtins

    real_import = builtins.__import__

    def _block_otel(name: str, *args, **kwargs):
        if name.startswith("opentelemetry"):
            raise ImportError("simulated missing dep")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _block_otel)
    assert tracing.init_tracing("koda-test") is False
    assert tracing.is_tracing_enabled() is False


def test_start_span_yields_none_when_disabled() -> None:
    with tracing.start_span("op", agent_id="A") as span:
        assert span is None


def test_inject_grpc_context_is_passthrough_when_disabled() -> None:
    md = [("x-existing", "v")]
    assert tracing.inject_grpc_context(md) == md


def test_extract_grpc_context_returns_none_when_disabled() -> None:
    assert tracing.extract_grpc_context([("traceparent", "abc")]) is None
    assert tracing.extract_grpc_context({"traceparent": "abc"}) is None
    assert tracing.extract_grpc_context(None) is None


def test_inject_does_not_mutate_input_list() -> None:
    md = [("x-existing", "v")]
    out = tracing.inject_grpc_context(md)
    assert out is not md  # always returns a new list


def test_coerce_attribute_handles_arbitrary_types() -> None:
    assert tracing._coerce_attribute(42) == 42
    assert tracing._coerce_attribute("s") == "s"
    assert tracing._coerce_attribute([1, "a", 2.0]) == [1, "a", 2.0]

    # Non-primitive falls back to repr/str
    class _Custom:
        def __str__(self) -> str:
            return "custom-string"

    assert tracing._coerce_attribute(_Custom()) == "custom-string"
