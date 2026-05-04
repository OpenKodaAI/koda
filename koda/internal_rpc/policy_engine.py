"""Async gRPC client for koda-policy-engine.

When ``POLICY_ENGINE_ENABLED=true`` the queue_manager consults the
gateway on the message-ingest hot path and after every billed LLM
call. This module exposes a thin async wrapper so callers don't have
to know about the protobuf shapes; failures fall through to a
permissive default (allow with no warning) so a transient gateway
outage cannot block all user traffic. The shared circuit breaker
upgrades this fall-through into a structured policy.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any

from koda import config
from koda.internal_rpc.common import (
    create_grpc_channel,
    ensure_generated_proto_path,
    make_internal_breaker,
    resolve_grpc_target,
)
from koda.logging_config import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class IngestDecision:
    allowed: bool
    deny_reason: str
    retry_after_ms: int


@dataclass(frozen=True, slots=True)
class SpendDecision:
    remaining_budget_usd: float
    warning_threshold_crossed: bool
    hard_stop_threshold_crossed: bool


@dataclass(frozen=True, slots=True)
class SlotLease:
    acquired: bool
    slot_token: str
    active_holders: int
    max_holders: int


class PolicyEngineClient:
    """Async tonic client. Use as ``async with`` for proper teardown."""

    def __init__(self, target: str | None = None) -> None:
        raw_target = target or config.POLICY_ENGINE_GRPC_TARGET
        self._target, _ = resolve_grpc_target(raw_target)
        self._channel: Any = None
        self._stub: Any = None
        self._pb2: Any = None
        # every RPC call goes through this breaker so a
        # hung policy-engine fails fast in microseconds instead of
        # waiting on INTERNAL_RPC_DEADLINE_MS for every request.
        self._breaker = make_internal_breaker("policy_engine")

    async def __aenter__(self) -> PolicyEngineClient:
        await self.start()
        return self

    async def __aexit__(self, *_exc_info: Any) -> None:
        await self.stop()

    async def start(self) -> None:
        if self._channel is not None:
            return
        ensure_generated_proto_path()
        from policy_engine.v1 import policy_engine_pb2, policy_engine_pb2_grpc

        self._channel = create_grpc_channel(self._target, async_channel=True)
        self._pb2 = policy_engine_pb2
        self._stub = policy_engine_pb2_grpc.PolicyEngineServiceStub(self._channel)

    async def stop(self) -> None:
        if self._channel is None:
            return
        channel = self._channel
        self._channel = None
        self._stub = None
        self._pb2 = None
        close_result = channel.close()
        if inspect.isawaitable(close_result):
            await close_result

    def _ensure_started(self) -> None:
        if self._stub is None or self._pb2 is None:
            raise RuntimeError("policy_engine_client_not_started")

    async def check_ingest(self, workspace_id: str, agent_id: str, message_size_bytes: int = 0) -> IngestDecision:
        self._ensure_started()
        req = self._pb2.CheckIngestRequest(
            workspace_id=workspace_id,
            agent_id=agent_id,
            message_size_bytes=int(message_size_bytes),
        )
        resp = await self._breaker.run(self._stub.CheckIngest, req)
        return IngestDecision(
            allowed=bool(resp.allowed),
            deny_reason=str(resp.deny_reason or ""),
            retry_after_ms=int(resp.retry_after_ms or 0),
        )

    async def record_spend(
        self,
        workspace_id: str,
        agent_id: str,
        cost_usd: float,
        provider: str = "",
        model: str = "",
    ) -> SpendDecision:
        self._ensure_started()
        req = self._pb2.RecordSpendRequest(
            workspace_id=workspace_id,
            agent_id=agent_id,
            cost_usd=float(cost_usd),
            provider=provider,
            model=model,
        )
        resp = await self._breaker.run(self._stub.RecordSpend, req)
        return SpendDecision(
            remaining_budget_usd=float(resp.remaining_budget_usd or 0.0),
            warning_threshold_crossed=bool(resp.warning_threshold_crossed),
            hard_stop_threshold_crossed=bool(resp.hard_stop_threshold_crossed),
        )

    async def acquire_slot(self, workspace_id: str, agent_id: str, lease_ttl_seconds: int = 600) -> SlotLease:
        self._ensure_started()
        req = self._pb2.AcquireSlotRequest(
            workspace_id=workspace_id,
            agent_id=agent_id,
            lease_ttl_seconds=int(lease_ttl_seconds),
        )
        resp = await self._breaker.run(self._stub.AcquireSlot, req)
        return SlotLease(
            acquired=bool(resp.acquired),
            slot_token=str(resp.slot_token or ""),
            active_holders=int(resp.active_holders or 0),
            max_holders=int(resp.max_holders or 0),
        )

    async def release_slot(self, workspace_id: str, slot_token: str) -> bool:
        self._ensure_started()
        req = self._pb2.ReleaseSlotRequest(workspace_id=workspace_id, slot_token=slot_token)
        resp = await self._breaker.run(self._stub.ReleaseSlot, req)
        return bool(resp.released)


_PERMISSIVE_DECISION = IngestDecision(allowed=True, deny_reason="", retry_after_ms=0)


async def check_ingest_or_allow(
    client: PolicyEngineClient | None,
    *,
    agent_id: str,
    message_size_bytes: int = 0,
) -> IngestDecision:
    """Wrapper used by queue_manager: when the engine is disabled or
    unreachable, fall through to allow. The bot-gateway's at-least-once
    delivery means we never silently drop a user message — at worst we
    process it without a quota check during a gateway outage."""
    if client is None or not config.POLICY_ENGINE_ENABLED:
        return _PERMISSIVE_DECISION
    try:
        return await client.check_ingest(
            workspace_id=config.POLICY_ENGINE_WORKSPACE_ID,
            agent_id=agent_id,
            message_size_bytes=message_size_bytes,
        )
    except Exception:
        log.exception("policy_engine_check_ingest_failed_falling_through")
        return _PERMISSIVE_DECISION


async def record_spend_safe(
    client: PolicyEngineClient | None,
    *,
    agent_id: str,
    cost_usd: float,
    provider: str = "",
    model: str = "",
) -> SpendDecision | None:
    """Wrapper used by queue_manager: never raise on the LLM-success
    path. Spend ledger drift is preferable to losing the response we
    just generated."""
    if client is None or not config.POLICY_ENGINE_ENABLED or cost_usd <= 0:
        return None
    try:
        return await client.record_spend(
            workspace_id=config.POLICY_ENGINE_WORKSPACE_ID,
            agent_id=agent_id,
            cost_usd=cost_usd,
            provider=provider,
            model=model,
        )
    except Exception:
        log.exception("policy_engine_record_spend_failed")
        return None
