"""Tests for plugin tool handlers."""

from unittest.mock import AsyncMock, patch

import pytest

from koda.services.tool_dispatcher import ToolContext


def _make_ctx(**overrides: object) -> ToolContext:
    defaults: dict = dict(
        user_id=1,
        chat_id=1,
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


class TestPluginList:
    @pytest.mark.asyncio
    async def test_disabled(self) -> None:
        from koda.services.tool_dispatcher import _handle_plugin_list

        with patch("koda.services.tool_dispatcher.PLUGIN_SYSTEM_ENABLED", False):
            result = await _handle_plugin_list({}, _make_ctx())
        assert not result.success

    @pytest.mark.asyncio
    async def test_empty(self) -> None:
        from koda.services.tool_dispatcher import _handle_plugin_list

        with patch("koda.services.tool_dispatcher.PLUGIN_SYSTEM_ENABLED", True):
            result = await _handle_plugin_list({}, _make_ctx())
        assert result.success
        assert "No plugins" in result.output


class TestPluginInstall:
    @pytest.mark.asyncio
    async def test_missing_path(self) -> None:
        from koda.services.tool_dispatcher import _handle_plugin_install

        with patch("koda.services.tool_dispatcher.PLUGIN_SYSTEM_ENABLED", True):
            result = await _handle_plugin_install({}, _make_ctx())
        assert not result.success


class TestPluginUninstall:
    @pytest.mark.asyncio
    async def test_missing_name(self) -> None:
        from koda.services.tool_dispatcher import _handle_plugin_uninstall

        with patch("koda.services.tool_dispatcher.PLUGIN_SYSTEM_ENABLED", True):
            result = await _handle_plugin_uninstall({}, _make_ctx())
        assert not result.success


class TestPluginPrompt:
    def test_section_when_enabled(self) -> None:
        from koda.services.tool_prompt import build_agent_tools_prompt

        with patch("koda.services.tool_prompt.PLUGIN_SYSTEM_ENABLED", True):
            prompt = build_agent_tools_prompt()
        assert "Plugin Management" in prompt

    def test_no_section_when_disabled(self) -> None:
        from koda.services.tool_prompt import build_agent_tools_prompt

        with patch("koda.services.tool_prompt.PLUGIN_SYSTEM_ENABLED", False):
            prompt = build_agent_tools_prompt()
        assert "Plugin Management" not in prompt
