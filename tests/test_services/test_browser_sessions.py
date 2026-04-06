"""Tests for browser session persistence tools."""

from unittest.mock import AsyncMock, patch

import pytest

from koda.services.tool_dispatcher import ToolContext


def _make_ctx(**overrides) -> ToolContext:
    defaults = dict(
        user_id=111,
        chat_id=111,
        work_dir="/tmp",
        user_data={
            "work_dir": "/tmp",
            "model": "m",
            "session_id": "s",
            "total_cost": 0.0,
            "query_count": 0,
        },
        agent=AsyncMock(),
        agent_mode="autonomous",
    )
    defaults.update(overrides)
    return ToolContext(**defaults)


def _no_browser_error():
    """Patch _check_browser_available to return None (browser is fine)."""
    return patch(
        "koda.services.tool_dispatcher._check_browser_available",
        new=AsyncMock(return_value=None),
    )


class TestBrowserSessionSave:
    @pytest.mark.asyncio
    async def test_disabled(self):
        from koda.services.tool_dispatcher import _handle_browser_session_save

        with patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", False):
            result = await _handle_browser_session_save({"name": "test"}, _make_ctx())
        assert not result.success

    @pytest.mark.asyncio
    async def test_missing_name(self):
        from koda.services.tool_dispatcher import _handle_browser_session_save

        with _no_browser_error():
            result = await _handle_browser_session_save({}, _make_ctx())
        assert not result.success

    @pytest.mark.asyncio
    async def test_success(self):
        from koda.services.tool_dispatcher import _handle_browser_session_save

        mock_bm = AsyncMock()
        mock_bm.save_session = AsyncMock(return_value="Session 'test' saved. Cookies: 5, Origins: 2")
        with (
            _no_browser_error(),
            patch("koda.services.tool_dispatcher.browser_manager", mock_bm, create=True),
            patch("koda.services.browser_manager.browser_manager", mock_bm),
        ):
            result = await _handle_browser_session_save({"name": "test"}, _make_ctx())
        assert result.success


class TestBrowserSessionRestore:
    @pytest.mark.asyncio
    async def test_missing_name(self):
        from koda.services.tool_dispatcher import _handle_browser_session_restore

        with _no_browser_error():
            result = await _handle_browser_session_restore({}, _make_ctx())
        assert not result.success

    @pytest.mark.asyncio
    async def test_success(self):
        from koda.services.tool_dispatcher import _handle_browser_session_restore

        mock_bm = AsyncMock()
        mock_bm.restore_session = AsyncMock(return_value="Session 'test' restored. Cookies: 5.")
        with (
            _no_browser_error(),
            patch("koda.services.tool_dispatcher.browser_manager", mock_bm, create=True),
            patch("koda.services.browser_manager.browser_manager", mock_bm),
        ):
            result = await _handle_browser_session_restore({"name": "test"}, _make_ctx())
        assert result.success


class TestBrowserSessionList:
    @pytest.mark.asyncio
    async def test_success(self):
        from koda.services.tool_dispatcher import _handle_browser_session_list

        mock_bm = AsyncMock()
        mock_bm.list_sessions = lambda sid: (
            "Saved sessions (1):\n  test — 500 bytes",
            [{"name": "test", "size": 500}],
        )
        with (
            _no_browser_error(),
            patch("koda.services.tool_dispatcher.browser_manager", mock_bm, create=True),
            patch("koda.services.browser_manager.browser_manager", mock_bm),
        ):
            result = await _handle_browser_session_list({}, _make_ctx())
        assert result.success
        assert "test" in result.output


class TestSessionPrompt:
    def test_section_when_enabled(self):
        from koda.services.tool_prompt import build_agent_tools_prompt

        with (
            patch("koda.services.tool_prompt.BROWSER_FEATURES_ENABLED", True),
            patch("koda.services.tool_prompt.BROWSER_SESSION_PERSISTENCE_ENABLED", True),
        ):
            prompt = build_agent_tools_prompt()
        assert "Session Persistence" in prompt
        assert "browser_session_save" not in prompt

    def test_no_section_when_disabled(self):
        from koda.services.tool_prompt import build_agent_tools_prompt

        with (
            patch("koda.services.tool_prompt.BROWSER_FEATURES_ENABLED", True),
            patch("koda.services.tool_prompt.BROWSER_SESSION_PERSISTENCE_ENABLED", False),
        ):
            prompt = build_agent_tools_prompt()
        assert "Session Persistence" not in prompt
