"""Message bus interface for inter-agent communication.

The Protocol defines the contract every bus implementation must satisfy. The
in-process implementation is `InMemoryMessageBus`; a Postgres-backed one will
land behind the same interface so cross-process delivery is a config flag.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from koda.agents.models import AgentMessage, DelegationRequest, DelegationResult


@runtime_checkable
class MessageBus(Protocol):
    async def send(
        self,
        from_agent: str,
        to_agent: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str: ...

    async def receive(self, agent_id: str, timeout: float = 30.0) -> AgentMessage | None: ...

    async def delegate(self, request: DelegationRequest) -> DelegationResult: ...

    def resolve_delegation(self, request_id: str, result: DelegationResult) -> None: ...

    async def broadcast(
        self,
        from_agent: str,
        content: str,
        exclude: set[str] | None = None,
    ) -> int: ...

    def list_agents(self) -> list[dict[str, Any]]: ...

    def get_message_log(
        self,
        limit: int = 50,
        agent_id: str | None = None,
    ) -> list[dict[str, Any]]: ...
