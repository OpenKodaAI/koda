"""Structured logging setup with structlog + contextvars."""

import contextvars
import logging
import os
import sys
from collections.abc import MutableMapping
from typing import Any, cast

import structlog

# Context variables for request tracing
ctx_user_id: contextvars.ContextVar[int | None] = contextvars.ContextVar("user_id", default=None)
ctx_query_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("query_id", default=None)
ctx_agent_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("agent_id", default=None)
ctx_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)


def _add_context(
    logger: object,
    method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Inject contextvars into log events."""
    user_id = ctx_user_id.get()
    query_id = ctx_query_id.get()
    agent_id = ctx_agent_id.get()
    trace_id = ctx_trace_id.get()
    if user_id is not None:
        event_dict["user_id"] = user_id
    if query_id is not None:
        event_dict["query_id"] = query_id
    if agent_id is not None:
        event_dict["agent_id"] = agent_id
    if trace_id is not None:
        event_dict["trace_id"] = trace_id
    return event_dict


_k8s_pod_name = os.environ.get("POD_NAME", "")
_k8s_node_name = os.environ.get("NODE_NAME", "")
_k8s_namespace = os.environ.get("POD_NAMESPACE", "")


def _add_k8s_context(
    logger: object,
    method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Inject Kubernetes context from Downward API environment variables."""
    if _k8s_pod_name:
        event_dict["pod_name"] = _k8s_pod_name
    if _k8s_node_name:
        event_dict["node_name"] = _k8s_node_name
    if _k8s_namespace:
        event_dict["namespace"] = _k8s_namespace
    return event_dict


def _add_trace_context(
    logger: object,
    method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Inject OpenTelemetry trace context when available."""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx and ctx.trace_id:
            event_dict["otel_trace_id"] = format(ctx.trace_id, "032x")
            event_dict["otel_span_id"] = format(ctx.span_id, "016x")
    except Exception:
        pass
    return event_dict


# Sensitive keys that must NEVER appear in log output, regardless of caller.
# Matches are case-insensitive and compared against the full key.
_REDACTED_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "new_password",
        "current_password",
        "recovery_code",
        "session_token",
        "registration_token",
        "bootstrap_code",
        "code",
        "totp_secret",
        "api_key",
        "apikey",
        "secret",
        "private_key",
        "token",
        "authorization",
        "cookie",
    }
)


def _redact_sensitive(
    logger: object,
    method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Replace values of well-known sensitive keys with a marker string.

    Does not recurse into nested structures; callers should avoid logging
    entire payload dicts containing secrets. Centralized here so a single fix
    applies to every structlog call site.
    """
    for key in list(event_dict.keys()):
        if key.lower() in _REDACTED_KEYS and event_dict.get(key):
            event_dict[key] = "***"
    return event_dict


def setup_logging(json_output: bool | None = None) -> None:
    """Configure structlog with optional JSON output for production.

    If json_output is None, auto-detect from LOG_FORMAT env var.
    """
    if json_output is None:
        json_output = os.environ.get("LOG_FORMAT", "console").lower() == "json"

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        _add_context,
        _add_k8s_context,
        _add_trace_context,
        _redact_sensitive,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_output:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structlog logger."""
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))
