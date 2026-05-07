"""Tests for webhook manager and tool handlers."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from koda.services.webhook_manager import WebhookManager


class TestWebhookManager:
    def test_register(self):
        mgr = WebhookManager()
        assert mgr.register("test", "/hooks/test") is None
        assert len(mgr.list_webhooks()) == 1

    def test_register_duplicate(self):
        mgr = WebhookManager()
        mgr.register("test", "/hooks/test")
        assert mgr.register("test", "/hooks/test") is not None

    def test_register_invalid_name(self):
        mgr = WebhookManager()
        assert mgr.register("bad name!", "/hooks/x") is not None

    def test_register_adds_leading_slash(self):
        mgr = WebhookManager()
        mgr.register("test", "hooks/test")
        hooks = mgr.list_webhooks()
        assert hooks[0]["path"] == "/hooks/test"

    def test_unregister(self):
        mgr = WebhookManager()
        mgr.register("test", "/hooks/test")
        assert mgr.unregister("test") is None
        assert len(mgr.list_webhooks()) == 0

    def test_unregister_nonexistent(self):
        mgr = WebhookManager()
        assert mgr.unregister("nope") is not None

    def test_receive_event(self):
        mgr = WebhookManager()
        mgr.register("test", "/hooks/test")
        assert mgr.receive_event("test", {"key": "value"}) is None
        events = mgr.get_recent_events("test")
        assert len(events) == 1
        assert events[0]["payload"]["key"] == "value"

    def test_receive_unknown_webhook(self):
        mgr = WebhookManager()
        assert mgr.receive_event("nope", {}) is not None

    def test_max_registrations(self):
        mgr = WebhookManager()
        mgr._max_registrations = 2
        mgr.register("a", "/a")
        mgr.register("b", "/b")
        assert mgr.register("c", "/c") is not None

    def test_event_log_bounded(self):
        mgr = WebhookManager()
        mgr._max_events = 5
        mgr.register("test", "/hooks/test")
        for i in range(10):
            mgr.receive_event("test", {"i": i})
        assert len(mgr._events) == 5

    def test_list_webhooks_fields(self):
        mgr = WebhookManager()
        mgr.register("secure", "/hooks/secure", secret="s3cret")
        hooks = mgr.list_webhooks()
        assert hooks[0]["has_secret"] is True
        assert hooks[0]["call_count"] == 0

    def test_receive_increments_call_count(self):
        mgr = WebhookManager()
        mgr.register("test", "/hooks/test")
        mgr.receive_event("test", {"a": 1})
        mgr.receive_event("test", {"a": 2})
        hooks = mgr.list_webhooks()
        assert hooks[0]["call_count"] == 2
        assert hooks[0]["last_called_at"] is not None

    @pytest.mark.asyncio
    async def test_wait_for_event_timeout(self):
        mgr = WebhookManager()
        mgr.register("test", "/hooks/test")
        event = await mgr.wait_for_event("webhook.test", timeout=0.1)
        assert event is None

    @pytest.mark.asyncio
    async def test_wait_for_event_received(self):
        mgr = WebhookManager()
        mgr.register("test", "/hooks/test")

        async def send_later():
            await asyncio.sleep(0.05)
            mgr.receive_event("test", {"msg": "hello"})

        asyncio.create_task(send_later())
        event = await mgr.wait_for_event("webhook.test", timeout=2)
        assert event is not None
        assert event.payload["msg"] == "hello"

    def test_verify_signature_no_secret(self):
        mgr = WebhookManager()
        mgr.register("test", "/hooks/test")
        assert mgr.verify_signature("test", b"data", "any") is True

    def test_get_recent_events_limit(self):
        mgr = WebhookManager()
        mgr.register("test", "/hooks/test")
        for i in range(10):
            mgr.receive_event("test", {"i": i})
        events = mgr.get_recent_events("test", limit=3)
        assert len(events) == 3


class TestWebhookHandlers:
    @pytest.mark.asyncio
    async def test_register_disabled(self):
        from koda.services.tool_dispatcher import ToolContext, _handle_webhook_register

        ctx = ToolContext(
            user_id=1,
            chat_id=1,
            work_dir="/tmp",
            user_data={"work_dir": "/tmp", "model": "m", "session_id": "s", "total_cost": 0.0, "query_count": 0},
            agent=AsyncMock(),
            agent_mode="autonomous",
        )
        with patch("koda.services.tool_dispatcher.WEBHOOK_ENABLED", False):
            result = await _handle_webhook_register({"name": "x", "path": "/x"}, ctx)
        assert not result.success

    @pytest.mark.asyncio
    async def test_register_success(self):
        from koda.services.tool_dispatcher import ToolContext, _handle_webhook_register

        ctx = ToolContext(
            user_id=1,
            chat_id=1,
            work_dir="/tmp",
            user_data={"work_dir": "/tmp", "model": "m", "session_id": "s", "total_cost": 0.0, "query_count": 0},
            agent=AsyncMock(),
            agent_mode="autonomous",
        )
        with (
            patch("koda.services.tool_dispatcher.WEBHOOK_ENABLED", True),
            patch("koda.services.webhook_manager.webhook_manager") as mock_wm,
        ):
            mock_wm.register = lambda n, p, s=None: None
            result = await _handle_webhook_register({"name": "test", "path": "/hooks/test"}, ctx)
        assert result.success

    @pytest.mark.asyncio
    async def test_register_missing_params(self):
        from koda.services.tool_dispatcher import ToolContext, _handle_webhook_register

        ctx = ToolContext(
            user_id=1,
            chat_id=1,
            work_dir="/tmp",
            user_data={"work_dir": "/tmp", "model": "m", "session_id": "s", "total_cost": 0.0, "query_count": 0},
            agent=AsyncMock(),
            agent_mode="autonomous",
        )
        with patch("koda.services.tool_dispatcher.WEBHOOK_ENABLED", True):
            result = await _handle_webhook_register({"name": "x"}, ctx)
        assert not result.success

    @pytest.mark.asyncio
    async def test_unregister_disabled(self):
        from koda.services.tool_dispatcher import ToolContext, _handle_webhook_unregister

        ctx = ToolContext(
            user_id=1,
            chat_id=1,
            work_dir="/tmp",
            user_data={"work_dir": "/tmp", "model": "m", "session_id": "s", "total_cost": 0.0, "query_count": 0},
            agent=AsyncMock(),
            agent_mode="autonomous",
        )
        with patch("koda.services.tool_dispatcher.WEBHOOK_ENABLED", False):
            result = await _handle_webhook_unregister({"name": "x"}, ctx)
        assert not result.success

    @pytest.mark.asyncio
    async def test_list_success(self):
        from koda.services.tool_dispatcher import ToolContext, _handle_webhook_list

        ctx = ToolContext(
            user_id=1,
            chat_id=1,
            work_dir="/tmp",
            user_data={"work_dir": "/tmp", "model": "m", "session_id": "s", "total_cost": 0.0, "query_count": 0},
            agent=AsyncMock(),
            agent_mode="autonomous",
        )
        with (
            patch("koda.services.tool_dispatcher.WEBHOOK_ENABLED", True),
            patch("koda.services.webhook_manager.webhook_manager") as mock_wm,
        ):
            mock_wm.list_webhooks = lambda: [{"name": "test", "path": "/x", "has_secret": False, "call_count": 0}]
            result = await _handle_webhook_list({}, ctx)
        assert result.success

    @pytest.mark.asyncio
    async def test_event_wait_disabled(self):
        from koda.services.tool_dispatcher import ToolContext, _handle_event_wait

        ctx = ToolContext(
            user_id=1,
            chat_id=1,
            work_dir="/tmp",
            user_data={"work_dir": "/tmp", "model": "m", "session_id": "s", "total_cost": 0.0, "query_count": 0},
            agent=AsyncMock(),
            agent_mode="autonomous",
        )
        with patch("koda.services.tool_dispatcher.WEBHOOK_ENABLED", False):
            result = await _handle_event_wait({"event_type": "webhook.test"}, ctx)
        assert not result.success

    @pytest.mark.asyncio
    async def test_event_wait_missing_event_type(self):
        from koda.services.tool_dispatcher import ToolContext, _handle_event_wait

        ctx = ToolContext(
            user_id=1,
            chat_id=1,
            work_dir="/tmp",
            user_data={"work_dir": "/tmp", "model": "m", "session_id": "s", "total_cost": 0.0, "query_count": 0},
            agent=AsyncMock(),
            agent_mode="autonomous",
        )
        with patch("koda.services.tool_dispatcher.WEBHOOK_ENABLED", True):
            result = await _handle_event_wait({}, ctx)
        assert not result.success


class TestWebhookPrompt:
    def test_section_when_enabled(self):
        from koda.services.tool_prompt import build_agent_tools_prompt

        with patch("koda.services.tool_prompt.WEBHOOK_ENABLED", True):
            prompt = build_agent_tools_prompt()
        assert "Webhooks" in prompt
        assert "webhook_register" not in prompt

    def test_no_section_when_disabled(self):
        from koda.services.tool_prompt import build_agent_tools_prompt

        with patch("koda.services.tool_prompt.WEBHOOK_ENABLED", False):
            prompt = build_agent_tools_prompt()
        assert "webhook_register" not in prompt
