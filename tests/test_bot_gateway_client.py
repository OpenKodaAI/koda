"""Python contract for koda-bot-gateway.

These tests pin three things so a future refactor cannot quietly drift:

1. ``BotGatewayClient.subscribe`` yields a typed dataclass (not raw
   protobuf) so callers don't depend on stub internals.
2. The opt-in flag ``BOT_GATEWAY_ENABLED`` defaults to ``False`` —
   single-host deployments keep their behavior unchanged after the
   gateway code lands.
3. ``__main__`` dispatches to the gateway runner ONLY when the flag is
   set, leaving ``app.run_polling`` as the legacy path.

The Rust service end-to-end behavior is covered in
``rust/koda-bot-gateway/src/{store,server,poller,telegram}.rs`` unit
tests.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from koda.internal_rpc import bot_gateway as client_mod


class _FakeStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.subscribe_payload: list[Any] = []

    def RegisterBot(self, request: Any) -> Any:
        self.calls.append(("RegisterBot", request))
        return _coro(SimpleNamespace(registered=True))

    def UnregisterBot(self, request: Any) -> Any:
        self.calls.append(("UnregisterBot", request))
        return _coro(SimpleNamespace(removed=True))

    def AcknowledgeUpdate(self, request: Any) -> Any:
        self.calls.append(("AcknowledgeUpdate", request))
        return _coro(SimpleNamespace(acknowledged=True))

    def SubscribeUpdates(self, request: Any) -> Any:
        self.calls.append(("SubscribeUpdates", request))
        return _AsyncIter(self.subscribe_payload)


async def _coro(value: Any) -> Any:
    return value


class _AsyncIter:
    def __init__(self, items: list[Any]) -> None:
        self._items = list(items)

    def __aiter__(self) -> _AsyncIter:
        return self

    async def __anext__(self) -> Any:
        if not self._items:
            raise StopAsyncIteration
        return self._items.pop(0)


def _build_client_with_fake_stub(monkeypatch: pytest.MonkeyPatch) -> tuple[client_mod.BotGatewayClient, _FakeStub]:
    fake_pb2 = SimpleNamespace(
        RegisterBotRequest=lambda **kw: SimpleNamespace(**kw),
        UnregisterBotRequest=lambda **kw: SimpleNamespace(**kw),
        AcknowledgeUpdateRequest=lambda **kw: SimpleNamespace(**kw),
        SubscribeUpdatesRequest=lambda **kw: SimpleNamespace(**kw),
    )
    stub = _FakeStub()
    client = client_mod.BotGatewayClient(target="127.0.0.1:50066")
    client._channel = object()
    client._pb2 = fake_pb2
    client._stub = stub
    return client, stub


@pytest.mark.asyncio
async def test_register_bot_sends_request_and_returns_bool(monkeypatch: pytest.MonkeyPatch) -> None:
    client, stub = _build_client_with_fake_stub(monkeypatch)
    ok = await client.register_bot("AGENT_A", "tok-a")
    assert ok is True
    assert stub.calls[0][0] == "RegisterBot"
    assert stub.calls[0][1].agent_id == "AGENT_A"
    assert stub.calls[0][1].bot_token == "tok-a"


@pytest.mark.asyncio
async def test_acknowledge_update_passes_update_id_as_int(monkeypatch: pytest.MonkeyPatch) -> None:
    client, stub = _build_client_with_fake_stub(monkeypatch)
    ok = await client.acknowledge_update("AGENT_A", 42)
    assert ok is True
    args = stub.calls[0][1]
    assert args.agent_id == "AGENT_A"
    assert args.update_id == 42
    assert isinstance(args.update_id, int)


@pytest.mark.asyncio
async def test_subscribe_yields_typed_dataclass(monkeypatch: pytest.MonkeyPatch) -> None:
    client, stub = _build_client_with_fake_stub(monkeypatch)
    stub.subscribe_payload = [
        SimpleNamespace(update_id=1, update_json='{"hello": "world"}'),
        SimpleNamespace(update_id=2, update_json='{"hello": "again"}'),
    ]
    received: list[client_mod.GatewayUpdate] = []
    async for update in client.subscribe("AGENT_A"):
        received.append(update)
    assert len(received) == 2
    assert received[0].agent_id == "AGENT_A"
    assert received[0].update_id == 1
    assert received[0].update_json == '{"hello": "world"}'
    assert isinstance(received[0], client_mod.GatewayUpdate)


@pytest.mark.asyncio
async def test_methods_require_start(monkeypatch: pytest.MonkeyPatch) -> None:
    client = client_mod.BotGatewayClient(target="127.0.0.1:50066")
    with pytest.raises(RuntimeError, match="not_started"):
        await client.register_bot("AGENT_A", "tok-a")


def test_default_flag_is_off() -> None:
    """Opt-in only — flipping the default to True would silently change
    every single-host deployment's polling behavior."""
    from koda.config import BOT_GATEWAY_ENABLED

    assert BOT_GATEWAY_ENABLED is False


def test_main_dispatches_to_runner_only_when_flag_is_set() -> None:
    """Search the source so the test stays stable through formatter
    reflows: __main__ must guard the gateway runner behind the flag."""
    src = Path("koda/__main__.py").read_text()
    assert "if BOT_GATEWAY_ENABLED:" in src
    assert "run_bot_gateway_consumer(app)" in src
    # Legacy path must still exist for the off-flag case.
    assert "app.run_polling(drop_pending_updates=TELEGRAM_DROP_PENDING_UPDATES)" in src
