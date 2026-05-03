"""Worker runner: consume Updates from koda-bot-gateway.

When ``BOT_GATEWAY_ENABLED=true`` the worker delegates Telegram polling
to the central Rust gateway. Each worker still constructs the same PTB
``Application`` (so handlers, post_init, error_handler all behave
identically), but instead of ``app.run_polling(...)`` it:

1. Initializes + starts the Application without polling.
2. Registers the agent's bot token with the gateway.
3. Subscribes to its per-agent Update stream (replay first, then live).
4. Decodes each Update via PTB's ``Update.de_json`` and calls
   ``app.process_update`` — blocking until handlers complete.
5. Acknowledges the update_id back to the gateway, deleting the durable
   row.

If ``app.process_update`` raises, the row stays in the gateway queue
and is replayed on the next reconnect — at-least-once delivery.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
from typing import Any

from koda import config
from koda.internal_rpc.bot_gateway import BotGatewayClient
from koda.logging_config import get_logger

log = get_logger(__name__)


def _agent_id_from_env() -> str:
    return (os.environ.get("AGENT_ID") or "").strip().upper()


async def run_bot_gateway_consumer(app: Any) -> None:
    """Drive ``app`` from the gateway stream until SIGINT/SIGTERM.

    ``app`` is the PTB ``Application`` already wired with handlers but
    NOT yet running. We initialize/start it here so post_init fires,
    then drive updates from gRPC instead of from ``run_polling``.
    """
    agent_id = _agent_id_from_env()
    if not agent_id:
        raise RuntimeError("bot_gateway_consumer_requires_agent_id_env")
    if not config.AGENT_TOKEN:
        raise RuntimeError("bot_gateway_consumer_requires_agent_token_env")

    stop = asyncio.Event()

    def _request_stop(*_: Any) -> None:
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _request_stop)

    log.info("bot_gateway_consumer_starting", agent_id=agent_id)
    await app.initialize()
    await app.start()
    try:
        async with BotGatewayClient() as client:
            await client.register_bot(agent_id, config.AGENT_TOKEN)
            consumer_task = asyncio.create_task(_drain_stream(app, client, agent_id))
            stop_task: asyncio.Task[Any] = asyncio.create_task(stop.wait())
            tasks: tuple[asyncio.Task[Any], ...] = (consumer_task, stop_task)
            done, _ = await asyncio.wait(
                set(tasks),
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in tasks:
                if not task.done():
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
            for task in done:
                exc = task.exception()
                if exc is not None and task is consumer_task:
                    raise exc
    finally:
        with contextlib.suppress(Exception):
            await app.stop()
        with contextlib.suppress(Exception):
            await app.shutdown()
        log.info("bot_gateway_consumer_stopped", agent_id=agent_id)


async def _drain_stream(app: Any, client: BotGatewayClient, agent_id: str) -> None:
    """Receive updates, dispatch through PTB, acknowledge after success."""
    from telegram import Update as TelegramUpdate

    async for envelope in client.subscribe(agent_id):
        try:
            payload = json.loads(envelope.update_json)
        except json.JSONDecodeError:
            log.exception(
                "bot_gateway_update_payload_undecodable",
                agent_id=agent_id,
                update_id=envelope.update_id,
            )
            await client.acknowledge_update(agent_id, envelope.update_id)
            continue
        update = TelegramUpdate.de_json(payload, app.bot)
        if update is None:
            log.warning(
                "bot_gateway_update_unrecognized_dropped",
                agent_id=agent_id,
                update_id=envelope.update_id,
            )
            await client.acknowledge_update(agent_id, envelope.update_id)
            continue
        try:
            await app.process_update(update)
        except Exception:
            # Don't ack on error: the gateway re-delivers on reconnect.
            log.exception(
                "bot_gateway_update_handler_raised",
                agent_id=agent_id,
                update_id=envelope.update_id,
            )
            continue
        await client.acknowledge_update(agent_id, envelope.update_id)
