"""Tests for the ChannelAdapter base class."""

from unittest.mock import AsyncMock

from koda.channels.base import ChannelAdapter
from koda.channels.types import ChannelIdentity, IncomingMessage


class ConcreteAdapter(ChannelAdapter):
    """Minimal concrete subclass for testing the base class behavior."""

    channel_type = "test"
    is_official = True

    async def initialize(self, agent_id, secrets):
        pass

    async def start(self):
        pass

    async def stop(self):
        pass

    async def send_text(self, channel, msg):
        return "test-id"

    async def send_typing(self, channel):
        pass

    async def send_voice(self, channel, path, caption=""):
        pass

    async def send_document(self, channel, path, filename, caption=""):
        pass

    async def send_image(self, channel, path, caption=""):
        pass


def _make_incoming():
    channel = ChannelIdentity(
        channel_type="test",
        channel_id="ch-1",
        user_id="u-1",
        user_display_name="Tester",
    )
    return IncomingMessage(
        id="msg-1",
        channel=channel,
        text="hello",
        timestamp=1700000000.0,
    )


class TestSetMessageCallback:
    def test_stores_callback(self):
        adapter = ConcreteAdapter()
        callback = AsyncMock()

        adapter.set_message_callback(callback)

        assert adapter._on_message is callback

    def test_overwrites_previous_callback(self):
        adapter = ConcreteAdapter()
        first = AsyncMock()
        second = AsyncMock()

        adapter.set_message_callback(first)
        adapter.set_message_callback(second)

        assert adapter._on_message is second


class TestDispatchInbound:
    async def test_calls_registered_callback(self):
        adapter = ConcreteAdapter()
        callback = AsyncMock()
        adapter.set_message_callback(callback)
        msg = _make_incoming()

        await adapter._dispatch_inbound(msg)

        callback.assert_awaited_once_with(msg)

    async def test_no_callback_logs_warning_and_does_not_crash(self):
        adapter = ConcreteAdapter()
        msg = _make_incoming()

        # Should complete without exception when no callback is registered
        await adapter._dispatch_inbound(msg)
        # The method returns early; verify _on_message is still None
        assert adapter._on_message is None

    async def test_no_callback_does_not_raise(self):
        adapter = ConcreteAdapter()
        msg = _make_incoming()

        # Should complete without exception
        await adapter._dispatch_inbound(msg)


class TestHealth:
    def test_returns_default_dict(self):
        adapter = ConcreteAdapter()
        info = adapter.health()

        assert info["channel_type"] == "test"
        assert info["is_official"] is True
        assert info["status"] == "unknown"

    def test_contains_expected_keys(self):
        adapter = ConcreteAdapter()
        info = adapter.health()
        assert set(info.keys()) == {"channel_type", "is_official", "status"}
