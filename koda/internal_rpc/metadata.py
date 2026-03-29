"""Helpers for internal gRPC metadata propagation."""

from __future__ import annotations

from collections.abc import Mapping


def build_rpc_metadata(
    *,
    request_id: str | None = None,
    trace_id: str | None = None,
    agent_id: str | None = None,
    task_id: str | int | None = None,
    user_id: str | int | None = None,
    extra: Mapping[str, str] | None = None,
) -> tuple[tuple[str, str], ...]:
    """Build a normalized metadata tuple for internal gRPC calls."""
    pairs: list[tuple[str, str]] = []
    fields = {
        "x-request-id": request_id,
        "x-trace-id": trace_id,
        "x-agent-id": agent_id,
        "x-task-id": str(task_id) if task_id is not None else None,
        "x-user-id": str(user_id) if user_id is not None else None,
    }
    for key, value in fields.items():
        if value:
            pairs.append((key, value))
    if extra:
        for key, value in extra.items():
            normalized_key = str(key).strip().lower()
            normalized_value = str(value).strip()
            if normalized_key and normalized_value:
                pairs.append((normalized_key, normalized_value))
    return tuple(pairs)
