"""Workflow data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkflowStep:
    id: str
    tool: str
    params: dict[str, Any] = field(default_factory=dict)
    condition: str | None = None  # "{{ steps.X.success }}" template
    on_failure: str = "stop"  # "stop", "continue", "skip"
    timeout: int = 60  # per-step timeout in seconds
    max_retries: int = 0  # retry count (0 = no retry)
    retry_delay: float = 1.0  # base delay for exponential backoff


@dataclass
class Workflow:
    name: str
    steps: list[WorkflowStep] = field(default_factory=list)
    description: str = ""
    created_by: int | None = None  # user_id
    created_at: float | None = None


@dataclass
class WorkflowRun:
    workflow_name: str
    status: str = "pending"  # pending, running, completed, failed
    step_results: dict[str, dict[str, Any]] = field(default_factory=dict)  # step_id -> result
    error: str | None = None
    started_at: float | None = None
    completed_at: float | None = None
