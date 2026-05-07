"""Rust-authoritative retrieval v2 built on top of current knowledge candidates."""

from __future__ import annotations

from typing import Protocol

from koda.knowledge.telemetry import knowledge_span
from koda.knowledge.types import QueryEnvelope, RetrievalBundle
from koda.logging_config import get_logger

log = get_logger(__name__)


class RetrievalEngineClient(Protocol):
    """Protocol for external retrieval engines that return a RetrievalBundle."""

    engine_name: str

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    def query(
        self,
        *,
        envelope: QueryEnvelope,
        max_results: int,
    ) -> RetrievalBundle: ...

    def health(self) -> dict[str, object]: ...


class KnowledgeRetrievalService:
    """Resolve structured retrieval bundles from intent, policy, and query scope."""

    def __init__(
        self,
        *,
        engine_client: RetrievalEngineClient | None = None,
    ) -> None:
        self._engine_client = engine_client

    @property
    def engine_name(self) -> str:
        if self._engine_client is None:
            return "unconfigured"
        configured_name = getattr(self._engine_client, "engine_name", "")
        if configured_name:
            return str(configured_name)
        return type(self._engine_client).__name__

    async def start(self) -> None:
        if self._engine_client is not None:
            await self._engine_client.start()

    async def stop(self) -> None:
        if self._engine_client is not None:
            await self._engine_client.stop()

    def health(self) -> dict[str, object]:
        return {
            "primary": (
                self._engine_client.health()
                if self._engine_client is not None
                else {
                    "service": "retrieval",
                    "implementation": "unconfigured",
                    "transport": "grpc",
                    "ready": False,
                    "verified": False,
                    "connected": False,
                    "engine_name": "unconfigured",
                    "authoritative": False,
                    "production_ready": False,
                    "cutover_allowed": False,
                }
            )
        }

    def query(
        self,
        *,
        envelope: QueryEnvelope,
        max_results: int,
    ) -> RetrievalBundle:
        with knowledge_span(
            "retrieval_v2.query",
            strategy=envelope.strategy.value,
            task_kind=envelope.task_kind,
            requires_write=envelope.requires_write,
            retrieval_engine=self.engine_name,
        ):
            if self._engine_client is None:
                raise RuntimeError("knowledge_retrieval_engine_unconfigured")
            primary_health_fn = getattr(self._engine_client, "health", None)
            primary_health = (
                primary_health_fn() if callable(primary_health_fn) else {"ready": True, "cutover_allowed": True}
            )
            if not bool(primary_health.get("cutover_allowed", primary_health.get("ready", False))):
                raise RuntimeError("knowledge_retrieval_engine_not_ready_for_cutover")
            bundle = self._engine_client.query(
                envelope=envelope,
                max_results=max_results,
            )
            bundle.effective_engine = str(bundle.effective_engine or self.engine_name or "rust_grpc")
            bundle.fallback_used = False
            return bundle
