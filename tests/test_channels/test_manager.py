"""Tests for the ChannelManager and channel detection logic."""

from unittest.mock import AsyncMock, patch

from koda.channels.base import ChannelAdapter
from koda.channels.manager import ChannelManager, detect_configured_channels


class MockAdapter(ChannelAdapter):
    """Minimal concrete adapter for testing lifecycle operations."""

    channel_type = "mock"
    is_official = True

    def __init__(self):
        self.initialized = False
        self.started = False
        self.stopped = False

    async def initialize(self, agent_id, secrets):
        self.initialized = True

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True

    async def send_text(self, channel, msg):
        return "mock_id"

    async def send_typing(self, channel):
        pass

    async def send_voice(self, channel, path, caption=""):
        pass

    async def send_document(self, channel, path, filename, caption=""):
        pass

    async def send_image(self, channel, path, caption=""):
        pass


class MockAdapterB(MockAdapter):
    """Second mock adapter for multi-channel tests."""

    channel_type = "mock_b"


# ---------------------------------------------------------------------------
# detect_configured_channels
# ---------------------------------------------------------------------------


class TestDetectConfiguredChannels:
    def test_empty_secrets_returns_empty(self):
        assert detect_configured_channels({}) == []

    def test_telegram_detected_when_agent_token_present(self):
        secrets = {"AGENT_TOKEN": "tok-123"}
        result = detect_configured_channels(secrets)
        assert "telegram" in result

    def test_whatsapp_detected_when_all_keys_present(self):
        secrets = {
            "WHATSAPP_ACCESS_TOKEN": "token",
            "WHATSAPP_PHONE_NUMBER_ID": "phone",
            "WHATSAPP_VERIFY_TOKEN": "verify",
            "WHATSAPP_APP_SECRET": "secret",
        }
        result = detect_configured_channels(secrets)
        assert "whatsapp" in result

    def test_whatsapp_not_detected_when_partial_keys(self):
        secrets = {"WHATSAPP_ACCESS_TOKEN": "token"}
        result = detect_configured_channels(secrets)
        assert "whatsapp" not in result

    def test_whatsapp_not_detected_when_key_is_empty_string(self):
        secrets = {
            "WHATSAPP_ACCESS_TOKEN": "token",
            "WHATSAPP_PHONE_NUMBER_ID": "",
            "WHATSAPP_VERIFY_TOKEN": "verify",
        }
        result = detect_configured_channels(secrets)
        assert "whatsapp" not in result

    def test_multiple_channels_detected(self):
        secrets = {
            "AGENT_TOKEN": "tg-tok",
            "DISCORD_BOT_TOKEN": "disc-tok",
        }
        result = detect_configured_channels(secrets)
        assert "telegram" in result
        assert "discord" in result

    def test_discord_detected(self):
        secrets = {"DISCORD_BOT_TOKEN": "abc"}
        result = detect_configured_channels(secrets)
        assert "discord" in result

    def test_slack_detected_when_all_keys_present(self):
        secrets = {
            "SLACK_BOT_TOKEN": "xoxb-...",
            "SLACK_APP_TOKEN": "xapp-...",
            "SLACK_SIGNING_SECRET": "secret",
        }
        result = detect_configured_channels(secrets)
        assert "slack" in result

    def test_slack_not_detected_with_partial_keys(self):
        secrets = {"SLACK_BOT_TOKEN": "xoxb-..."}
        result = detect_configured_channels(secrets)
        assert "slack" not in result


# ---------------------------------------------------------------------------
# ChannelManager
# ---------------------------------------------------------------------------


class TestChannelManager:
    def _make_manager(self):
        return ChannelManager(agent_id="test-agent")

    @staticmethod
    def _patch_registry(registry):
        """Patch both the registry dict and _populate_registry to prevent real adapter loading."""
        from contextlib import ExitStack

        stack = ExitStack()
        stack.enter_context(patch("koda.channels.manager._ADAPTER_REGISTRY", registry))
        stack.enter_context(patch("koda.channels.manager._populate_registry", lambda: None))
        return stack

    async def test_set_message_callback_propagates_to_adapters(self):
        mgr = self._make_manager()
        adapter = MockAdapter()
        mgr._adapters["mock"] = adapter

        callback = AsyncMock()
        mgr.set_message_callback(callback)

        assert mgr._message_callback is callback
        assert adapter._on_message is callback

    async def test_initialize_discovers_and_creates_adapters(self):
        registry = {"mock": MockAdapter}
        secrets = {"AGENT_TOKEN": "tok"}

        # Patch both the registry and detection to use our mock
        with (
            self._patch_registry(registry),
            patch(
                "koda.channels.manager.detect_configured_channels",
                return_value=["mock"],
            ),
        ):
            mgr = self._make_manager()
            await mgr.initialize(secrets)

        assert "mock" in mgr._adapters
        assert mgr._adapters["mock"].initialized is True

    async def test_initialize_skips_missing_adapter_class(self):
        registry = {}  # no adapter registered for "telegram"
        secrets = {"AGENT_TOKEN": "tok"}

        with (
            self._patch_registry(registry),
            patch(
                "koda.channels.manager.detect_configured_channels",
                return_value=["telegram"],
            ),
        ):
            mgr = self._make_manager()
            await mgr.initialize(secrets)

        assert mgr._adapters == {}

    async def test_initialize_propagates_callback(self):
        registry = {"mock": MockAdapter}
        callback = AsyncMock()

        with (
            self._patch_registry(registry),
            patch(
                "koda.channels.manager.detect_configured_channels",
                return_value=["mock"],
            ),
        ):
            mgr = self._make_manager()
            mgr._message_callback = callback
            await mgr.initialize({"AGENT_TOKEN": "tok"})

        assert mgr._adapters["mock"]._on_message is callback

    async def test_start_all_calls_start_on_all_adapters(self):
        mgr = self._make_manager()
        a = MockAdapter()
        b = MockAdapterB()
        mgr._adapters = {"mock": a, "mock_b": b}

        await mgr.start_all()

        assert a.started is True
        assert b.started is True
        assert mgr._running is True

    async def test_start_all_no_adapters_does_nothing(self):
        mgr = self._make_manager()
        await mgr.start_all()
        assert mgr._running is False

    async def test_stop_all_calls_stop_on_all_adapters(self):
        mgr = self._make_manager()
        a = MockAdapter()
        b = MockAdapterB()
        mgr._adapters = {"mock": a, "mock_b": b}

        await mgr.stop_all()

        assert a.stopped is True
        assert b.stopped is True

    async def test_stop_all_clears_adapters_dict(self):
        mgr = self._make_manager()
        mgr._adapters = {"mock": MockAdapter()}

        await mgr.stop_all()

        assert mgr._adapters == {}
        assert mgr._running is False

    def test_get_adapter_returns_existing(self):
        mgr = self._make_manager()
        adapter = MockAdapter()
        mgr._adapters["mock"] = adapter

        assert mgr.get_adapter("mock") is adapter

    def test_get_adapter_returns_none_for_missing(self):
        mgr = self._make_manager()
        assert mgr.get_adapter("nonexistent") is None

    def test_health_returns_structured_info(self):
        mgr = self._make_manager()
        adapter = MockAdapter()
        mgr._adapters["mock"] = adapter

        info = mgr.health()

        assert info["agent_id"] == "test-agent"
        assert info["running"] is False
        assert "mock" in info["channels"]
        assert info["channels"]["mock"]["channel_type"] == "mock"

    def test_health_empty_when_no_adapters(self):
        mgr = self._make_manager()
        info = mgr.health()
        assert info["channels"] == {}

    def test_adapters_property_returns_copy(self):
        mgr = self._make_manager()
        adapter = MockAdapter()
        mgr._adapters["mock"] = adapter

        copy = mgr.adapters
        assert copy == {"mock": adapter}
        # Mutating the copy should not affect the manager
        copy["injected"] = MockAdapter()
        assert "injected" not in mgr._adapters
