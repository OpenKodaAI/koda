"""Inter-agent communication data models."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentMessage:
    """A message sent between agents."""

    from_agent: str
    to_agent: str
    content: str
    message_type: str = "text"  # text, delegation_request, delegation_result
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    message_id: str = ""


@dataclass
class DelegationRequest:
    """A task delegation request from one agent to another."""

    from_agent: str
    to_agent: str
    task: str
    context: dict[str, Any] = field(default_factory=dict)
    delegation_depth: int = 0
    timeout: float = 60.0
    request_id: str = ""


@dataclass
class DelegationResult:
    """The result of a delegation request."""

    request_id: str
    from_agent: str
    to_agent: str
    success: bool
    result: str = ""
    error: str | None = None
    duration_ms: float | None = None
