"""Tests for multi-tab browser support."""

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


def _patch_browser_available():
    """Patch _check_browser_available to return None (browser is available)."""
    return patch(
        "koda.services.tool_dispatcher._check_browser_available",
        new=AsyncMock(return_value=None),
    )


def _patch_browser_manager():
    """Patch browser_manager at the module it's imported from."""
    return patch("koda.services.browser_manager.browser_manager")


class TestBrowserTabOpen:
    @pytest.mark.asyncio
    async def test_disabled(self):
        from koda.services.tool_dispatcher import _handle_browser_tab_open

        with patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", False):
            result = await _handle_browser_tab_open({}, _make_ctx())
        assert not result.success

    @pytest.mark.asyncio
    async def test_success(self):
        from koda.services.tool_dispatcher import _handle_browser_tab_open

        with _patch_browser_available(), _patch_browser_manager() as mock_bm:
            mock_bm.open_tab = AsyncMock(
                return_value="Tab 1 opened and activated.\nURL: about:blank\nTitle: \nTotal tabs: 2"
            )
            result = await _handle_browser_tab_open({}, _make_ctx())
        assert result.success
        assert "Tab 1" in result.output


class TestBrowserTabClose:
    @pytest.mark.asyncio
    async def test_success(self):
        from koda.services.tool_dispatcher import _handle_browser_tab_close

        with _patch_browser_available(), _patch_browser_manager() as mock_bm:
            mock_bm.close_tab = AsyncMock(return_value="Tab 1 closed. Active tab: 0. Total: 1")
            result = await _handle_browser_tab_close({"tab_id": 1}, _make_ctx())
        assert result.success

    @pytest.mark.asyncio
    async def test_invalid_tab_id(self):
        from koda.services.tool_dispatcher import _handle_browser_tab_close

        with _patch_browser_available():
            result = await _handle_browser_tab_close({"tab_id": "abc"}, _make_ctx())
        assert not result.success


class TestBrowserTabSwitch:
    @pytest.mark.asyncio
    async def test_missing_tab_id(self):
        from koda.services.tool_dispatcher import _handle_browser_tab_switch

        with _patch_browser_available():
            result = await _handle_browser_tab_switch({}, _make_ctx())
        assert not result.success

    @pytest.mark.asyncio
    async def test_success(self):
        from koda.services.tool_dispatcher import _handle_browser_tab_switch

        with _patch_browser_available(), _patch_browser_manager() as mock_bm:
            mock_bm.switch_tab = AsyncMock(return_value="Switched to tab 0.\nURL: https://example.com\nTitle: Example")
            result = await _handle_browser_tab_switch({"tab_id": 0}, _make_ctx())
        assert result.success


class TestBrowserTabList:
    @pytest.mark.asyncio
    async def test_success(self):
        from koda.services.tool_dispatcher import _handle_browser_tab_list

        with _patch_browser_available(), _patch_browser_manager() as mock_bm:
            mock_bm.list_tabs = AsyncMock(
                return_value=(
                    "Tab 0 (active): Example — https://example.com",
                    [{"tab_id": 0, "url": "https://example.com", "title": "Example", "active": True}],
                )
            )
            result = await _handle_browser_tab_list({}, _make_ctx())
        assert result.success
        assert result.metadata is not None
        assert result.metadata["tabs"][0]["active"] is True


class TestBrowserTabCompare:
    @pytest.mark.asyncio
    async def test_too_few_tabs(self):
        from koda.services.tool_dispatcher import _handle_browser_tab_compare

        with _patch_browser_available():
            result = await _handle_browser_tab_compare({"tab_ids": [0]}, _make_ctx())
        assert not result.success

    @pytest.mark.asyncio
    async def test_success(self):
        from koda.services.tool_dispatcher import _handle_browser_tab_compare

        with _patch_browser_available(), _patch_browser_manager() as mock_bm:
            mock_bm.compare_tabs = AsyncMock(return_value="=== Tab 0 ===\nHello\n\n=== Tab 1 ===\nWorld")
            result = await _handle_browser_tab_compare({"tab_ids": [0, 1]}, _make_ctx())
        assert result.success


class TestBrowserPromptTabs:
    def test_tab_tools_in_prompt(self):
        from koda.services.tool_prompt import build_agent_tools_prompt

        with patch("koda.services.tool_prompt.BROWSER_FEATURES_ENABLED", True):
            prompt = build_agent_tools_prompt()
        assert "Tab Management" in prompt
        assert "browser_tab_open" not in prompt
