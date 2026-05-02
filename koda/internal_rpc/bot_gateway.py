"""Async gRPC client for koda-bot-gateway.

The Phase 1B service consolidates Telegram polling into a single Rust
process. Workers consume their per-agent stream via this client when
``BOT_GATEWAY_ENABLED=true`` and fall back to the legacy in-process
polling when it is not. See
``docs/architecture/production-deployment-roadmap.md`` (P2-6) for the
broader roadmap and ``proto/bot_gateway/v1/bot_gateway.proto`` for the
wire contract.
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator
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
class GatewayUpdate:
    """One Update streamed from the gateway. ``update_json`` is the
    verbatim Telegram payload — workers decode with ``Update.de_json``
    so the gateway never needs to model Telegram's evolving schema."""

    agent_id: str
    update_id: int
    update_json: str


class BotGatewayClient:
    """Async client wrapping the gateway gRPC stubs.

    Use as an async context manager so the underlying channel closes on
    error. Methods raise on transport failure — callers retry; offset
    durability is owned by the gateway-side queue, so ``acknowledge`` is
    the only operation that needs at-least-once retry semantics.
    """

    def __init__(self, target: str | None = None) -> None:
        raw_target = target or config.BOT_GATEWAY_GRPC_TARGET
        self._target, _ = resolve_grpc_target(raw_target)
        self._channel: Any = None
        self._stub: Any = None
        self._pb2: Any = None
        # Phase A.2 — fail-fast breaker for unary RPCs. Streams
        # (SubscribeUpdates) bypass the breaker because their lifetime
        # exceeds the breaker window; an outage during a stream is
        # surfaced through the consumer's reconnect loop.
        self._breaker = make_internal_breaker("bot_gateway")

    async def __aenter__(self) -> BotGatewayClient:
        await self.start()
        return self

    async def __aexit__(self, *_exc_info: Any) -> None:
        await self.stop()

    async def start(self) -> None:
        if self._channel is not None:
            return
        ensure_generated_proto_path()
        from bot_gateway.v1 import bot_gateway_pb2, bot_gateway_pb2_grpc

        self._channel = create_grpc_channel(self._target, async_channel=True)
        self._pb2 = bot_gateway_pb2
        self._stub = bot_gateway_pb2_grpc.BotGatewayServiceStub(self._channel)

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
            raise RuntimeError("bot_gateway_client_not_started_call_start_first")

    async def register_bot(self, agent_id: str, bot_token: str) -> bool:
        self._ensure_started()
        req = self._pb2.RegisterBotRequest(agent_id=agent_id, bot_token=bot_token)
        resp = await self._breaker.run(self._stub.RegisterBot, req)
        return bool(resp.registered)

    async def unregister_bot(self, agent_id: str) -> bool:
        self._ensure_started()
        req = self._pb2.UnregisterBotRequest(agent_id=agent_id)
        resp = await self._breaker.run(self._stub.UnregisterBot, req)
        return bool(resp.removed)

    async def acknowledge_update(self, agent_id: str, update_id: int) -> bool:
        self._ensure_started()
        req = self._pb2.AcknowledgeUpdateRequest(agent_id=agent_id, update_id=int(update_id))
        resp = await self._breaker.run(self._stub.AcknowledgeUpdate, req)
        return bool(resp.acknowledged)

    async def subscribe(self, agent_id: str) -> AsyncIterator[GatewayUpdate]:
        """Yield Updates for ``agent_id`` until the stream closes.

        The gateway first replays any rows still pending in
        ``cp_telegram_pending_updates`` (so a worker crash never loses
        messages), then keeps the stream open for live updates from
        the poller. Callers are expected to call ``acknowledge_update``
        after fully processing each yielded item.
        """
        self._ensure_started()
        req = self._pb2.SubscribeUpdatesRequest(agent_id=agent_id)
        async for update in self._stub.SubscribeUpdates(req):
            yield GatewayUpdate(
                agent_id=agent_id,
                update_id=int(update.update_id),
                update_json=str(update.update_json),
            )
