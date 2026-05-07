"""Tests for browser network interception tools."""

from unittest.mock import AsyncMock, patch

import pytest

from koda.services.tool_dispatcher import ToolContext


def _make_ctx(**overrides) -> ToolContext:
    defaults = dict(
        user_id=111,
        chat_id=111,
        work_dir="/tmp",
        user_data={"work_dir": "/tmp", "model": "m", "session_id": "s", "total_cost": 0.0, "query_count": 0},
        agent=AsyncMock(),
        agent_mode="autonomous",
    )
    defaults.update(overrides)
    return ToolContext(**defaults)


class TestNetworkCaptureStart:
    @pytest.mark.asyncio
    async def test_disabled(self):
        from koda.services.tool_dispatcher import _handle_browser_network_capture_start

        with patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", False):
            result = await _handle_browser_network_capture_start({}, _make_ctx())
        assert not result.success

    @pytest.mark.asyncio
    async def test_success(self):
        from koda.services.tool_dispatcher import _handle_browser_network_capture_start

        with (
            patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", True),
            patch("koda.services.browser_manager.browser_manager") as mock_bm,
        ):
            mock_bm.start_network_capture = AsyncMock(return_value="Network capture started.")
            mock_bm.ensure_started = AsyncMock(return_value=True)
            result = await _handle_browser_network_capture_start({}, _make_ctx())
        assert result.success


class TestNetworkCaptureStop:
    @pytest.mark.asyncio
    async def test_success(self):
        from koda.services.tool_dispatcher import _handle_browser_network_capture_stop

        with (
            patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", True),
            patch("koda.services.browser_manager.browser_manager") as mock_bm,
        ):
            mock_bm.stop_network_capture = AsyncMock(return_value="Capture stopped. 10 requests captured.")
            mock_bm.ensure_started = AsyncMock(return_value=True)
            result = await _handle_browser_network_capture_stop({}, _make_ctx())
        assert result.success


class TestNetworkRequests:
    @pytest.mark.asyncio
    async def test_success(self):
        from koda.services.tool_dispatcher import _handle_browser_network_requests

        with (
            patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", True),
            patch("koda.services.browser_manager.browser_manager") as mock_bm,
        ):
            mock_bm.get_captured_requests = lambda sid, limit=50, filter_str=None: (
                "Captured requests (1):\n  [GET] 200 https://api.example.com/data",
                [{"url": "https://api.example.com/data", "method": "GET", "status": 200}],
            )
            mock_bm.ensure_started = AsyncMock(return_value=True)
            result = await _handle_browser_network_requests({}, _make_ctx())
        assert result.success
        assert result.metadata.get("data") is not None


class TestNetworkMock:
    @pytest.mark.asyncio
    async def test_missing_pattern(self):
        from koda.services.tool_dispatcher import _handle_browser_network_mock

        with (
            patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", True),
            patch("koda.services.browser_manager.browser_manager") as mock_bm,
        ):
            mock_bm.ensure_started = AsyncMock(return_value=True)
            result = await _handle_browser_network_mock({}, _make_ctx())
        assert not result.success

    @pytest.mark.asyncio
    async def test_success(self):
        from koda.services.tool_dispatcher import _handle_browser_network_mock

        with (
            patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", True),
            patch("koda.services.browser_manager.browser_manager") as mock_bm,
        ):
            mock_bm.mock_route = AsyncMock(return_value="Route mocked: **/api/* \u2192 200")
            mock_bm.ensure_started = AsyncMock(return_value=True)
            result = await _handle_browser_network_mock(
                {"url_pattern": "**/api/*", "response": {"status": 200, "body": "{}"}}, _make_ctx()
            )
        assert result.success


class TestNetworkPrompt:
    def test_section_when_enabled(self):
        from koda.services.tool_prompt import build_agent_tools_prompt

        with (
            patch("koda.services.tool_prompt.BROWSER_FEATURES_ENABLED", True),
            patch("koda.services.tool_prompt.BROWSER_NETWORK_INTERCEPTION_ENABLED", True),
        ):
            prompt = build_agent_tools_prompt()
        assert "Network Interception" in prompt
        assert "browser_network_mock" not in prompt

    def test_no_section_when_disabled(self):
        from koda.services.tool_prompt import build_agent_tools_prompt

        with (
            patch("koda.services.tool_prompt.BROWSER_FEATURES_ENABLED", True),
            patch("koda.services.tool_prompt.BROWSER_NETWORK_INTERCEPTION_ENABLED", False),
        ):
            prompt = build_agent_tools_prompt()
        assert "Network Interception" not in prompt
