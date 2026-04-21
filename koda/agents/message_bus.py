"""Agent message bus for inter-agent communication."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import Any

from koda.agents.models import AgentMessage, DelegationRequest, DelegationResult
from koda.logging_config import get_logger

log = get_logger(__name__)


class AgentMessageBus:
    """In-memory message bus with per-agent inbox queues."""

    def __init__(self) -> None:
        self._inboxes: dict[str, asyncio.Queue[AgentMessage]] = {}
        self._delegation_results: dict[str, asyncio.Event] = {}
        self._delegation_data: dict[str, DelegationResult] = {}
        self._message_log: list[AgentMessage] = []
        self._max_log: int = 500
        self._max_inbox_size: int = 100
        self._counter: int = 0
        self._persistence_path: str | None = None

    def set_persistence_path(self, path: str) -> None:
        self._persistence_path = path
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        if not self._persistence_path or not os.path.isfile(self._persistence_path):
            return
        try:
            with open(self._persistence_path) as f:
                data = json.load(f)
            for msg_data in data.get("messages", []):
                msg = AgentMessage(
                    from_agent=msg_data["from_agent"],
                    to_agent=msg_data["to_agent"],
                    content=msg_data.get("content", ""),
                    metadata=msg_data.get("metadata", {}),
                    message_id=msg_data.get("message_id", self._next_id()),
                    message_type=msg_data.get("message_type", "text"),
                    timestamp=msg_data.get("timestamp"),
                )
                self._message_log.append(msg)
            self._counter = data.get("counter", 0)
            log.info("message_bus_loaded", messages=len(self._message_log))
        except Exception as e:
            log.warning("message_bus_load_failed", error=str(e))

    def _save_to_disk(self) -> None:
        if not self._persistence_path:
            return
        try:
            data = {
                "counter": self._counter,
                "messages": [
                    {
                        "from_agent": m.from_agent,
                        "to_agent": m.to_agent,
                        "content": m.content,
                        "metadata": m.metadata,
                        "message_id": m.message_id,
                        "message_type": m.message_type,
                        "timestamp": m.timestamp,
                    }
                    for m in self._message_log[-self._max_log :]
                ],
            }
            os.makedirs(os.path.dirname(self._persistence_path) or ".", exist_ok=True)
            with open(self._persistence_path, "w") as f:
                json.dump(data, f, default=str)
        except Exception as e:
            log.warning("message_bus_save_failed", error=str(e))

    def _ensure_inbox(self, agent_id: str) -> asyncio.Queue[AgentMessage]:
        if agent_id not in self._inboxes:
            self._inboxes[agent_id] = asyncio.Queue(maxsize=self._max_inbox_size)
        return self._inboxes[agent_id]

    def _next_id(self) -> str:
        self._counter += 1
        return f"msg-{self._counter}-{uuid.uuid4().hex[:8]}"

    async def send(
        self,
        from_agent: str,
        to_agent: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Send a message to another agent. Returns message_id."""
        msg = AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            content=content,
            metadata=metadata or {},
            message_id=self._next_id(),
        )
        inbox = self._ensure_inbox(to_agent)
        try:
            inbox.put_nowait(msg)
        except asyncio.QueueFull:
            return f"Error: inbox full for agent '{to_agent}'."
        self._message_log.append(msg)
        if len(self._message_log) > self._max_log:
            self._message_log = self._message_log[-self._max_log :]
        log.info("agent_message_sent", from_agent=from_agent, to_agent=to_agent, msg_id=msg.message_id)
        self._save_to_disk()
        return msg.message_id

    async def receive(self, agent_id: str, timeout: float = 30.0) -> AgentMessage | None:
        """Receive next message from inbox. Returns None on timeout."""
        inbox = self._ensure_inbox(agent_id)
        try:
            return await asyncio.wait_for(inbox.get(), timeout=min(timeout, 300))
        except TimeoutError:
            return None

    async def delegate(self, request: DelegationRequest) -> DelegationResult:
        """Delegate a task to another agent and wait for result."""
        from koda.config import INTER_AGENT_MAX_DELEGATION_DEPTH

        if request.delegation_depth >= INTER_AGENT_MAX_DELEGATION_DEPTH:
            return DelegationResult(
                request_id=request.request_id,
                from_agent=request.from_agent,
                to_agent=request.to_agent,
                success=False,
                error=f"Max delegation depth ({INTER_AGENT_MAX_DELEGATION_DEPTH}) exceeded.",
            )

        request.request_id = request.request_id or self._next_id()
        event = asyncio.Event()
        self._delegation_results[request.request_id] = event

        # Send delegation request as message
        msg = AgentMessage(
            from_agent=request.from_agent,
            to_agent=request.to_agent,
            content=request.task,
            message_type="delegation_request",
            metadata={
                "request_id": request.request_id,
                "context": request.context,
                "delegation_depth": request.delegation_depth,
            },
            message_id=self._next_id(),
        )
        inbox = self._ensure_inbox(request.to_agent)
        try:
            inbox.put_nowait(msg)
        except asyncio.QueueFull:
            self._delegation_results.pop(request.request_id, None)
            return DelegationResult(
                request_id=request.request_id,
                from_agent=request.from_agent,
                to_agent=request.to_agent,
                success=False,
                error=f"Agent '{request.to_agent}' inbox full.",
            )

        # Wait for result
        try:
            await asyncio.wait_for(event.wait(), timeout=min(request.timeout, 300))
            result = self._delegation_data.pop(request.request_id, None)
            if result:
                return result
            return DelegationResult(
                request_id=request.request_id,
                from_agent=request.from_agent,
                to_agent=request.to_agent,
                success=False,
                error="No result received.",
            )
        except TimeoutError:
            return DelegationResult(
                request_id=request.request_id,
                from_agent=request.from_agent,
                to_agent=request.to_agent,
                success=False,
                error=f"Delegation timeout ({request.timeout}s).",
            )
        finally:
            self._delegation_results.pop(request.request_id, None)

    def resolve_delegation(self, request_id: str, result: DelegationResult) -> None:
        """Resolve a pending delegation with a result."""
        self._delegation_data[request_id] = result
        event = self._delegation_results.get(request_id)
        if event:
            event.set()

    async def broadcast(
        self,
        from_agent: str,
        content: str,
        exclude: set[str] | None = None,
    ) -> int:
        """Send message to all known agents. Returns count sent."""
        exclude = exclude or set()
        count = 0
        for agent_id in list(self._inboxes):
            if agent_id != from_agent and agent_id not in exclude:
                await self.send(from_agent, agent_id, content)
                count += 1
        return count

    def list_agents(self) -> list[dict[str, Any]]:
        """List all agents with inbox status."""
        return [
            {
                "agent_id": aid,
                "inbox_size": inbox.qsize(),
                "inbox_max": inbox.maxsize,
            }
            for aid, inbox in self._inboxes.items()
        ]

    def get_message_log(
        self,
        limit: int = 50,
        agent_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get recent messages."""
        msgs = self._message_log
        if agent_id:
            msgs = [m for m in msgs if m.from_agent == agent_id or m.to_agent == agent_id]
        return [
            {
                "from": m.from_agent,
                "to": m.to_agent,
                "content": m.content[:200],
                "type": m.message_type,
                "timestamp": m.timestamp,
                "id": m.message_id,
            }
            for m in msgs[-limit:]
        ]


_bus: AgentMessageBus | None = None


def get_message_bus() -> AgentMessageBus:
    """Return the singleton message bus instance."""
    global _bus  # noqa: PLW0603
    if _bus is None:
        _bus = AgentMessageBus()
    return _bus
