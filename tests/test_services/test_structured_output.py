"""Tests for structured data output feature."""

import asyncio
from unittest.mock import AsyncMock, patch

from koda.services.tool_dispatcher import AgentToolResult, format_tool_results


class TestAgentToolResultDataField:
    def test_data_defaults_to_none(self):
        r = AgentToolResult(tool="test", success=True, output="ok")
        assert r.data is None
        assert r.data_format is None

    def test_data_can_be_set(self):
        r = AgentToolResult(tool="test", success=True, output="ok", data={"key": "val"}, data_format="json")
        assert r.data == {"key": "val"}
        assert r.data_format == "json"

    def test_data_can_be_list(self):
        r = AgentToolResult(tool="test", success=True, output="ok", data=[1, 2, 3])
        assert r.data == [1, 2, 3]


class TestFormatToolResultsStructured:
    def test_no_data_unchanged(self):
        results = [AgentToolResult(tool="test", success=True, output="hello")]
        formatted = format_tool_results(results)
        assert "<structured_data" not in formatted
        assert "hello" in formatted

    def test_data_included_when_enabled(self):
        results = [AgentToolResult(tool="test", success=True, output="hello", data={"x": 1}, data_format="json")]
        with patch("koda.services.tool_dispatcher.STRUCTURED_DATA_OUTPUT_ENABLED", True):
            formatted = format_tool_results(results)
        assert "<structured_data" in formatted
        assert '"x": 1' in formatted or '"x":1' in formatted
        assert 'format="json"' in formatted
        # text output still present
        assert "hello" in formatted

    def test_data_excluded_when_disabled(self):
        results = [AgentToolResult(tool="test", success=True, output="hello", data={"x": 1})]
        with patch("koda.services.tool_dispatcher.STRUCTURED_DATA_OUTPUT_ENABLED", False):
            formatted = format_tool_results(results)
        assert "<structured_data" not in formatted

    def test_data_none_no_tag(self):
        results = [AgentToolResult(tool="test", success=True, output="hello", data=None)]
        with patch("koda.services.tool_dispatcher.STRUCTURED_DATA_OUTPUT_ENABLED", True):
            formatted = format_tool_results(results)
        assert "<structured_data" not in formatted

    def test_multiple_results_mixed(self):
        results = [
            AgentToolResult(tool="a", success=True, output="text1", data={"k": "v"}),
            AgentToolResult(tool="b", success=True, output="text2"),
        ]
        with patch("koda.services.tool_dispatcher.STRUCTURED_DATA_OUTPUT_ENABLED", True):
            formatted = format_tool_results(results)
        # First has structured data, second doesn't
        assert formatted.count("<structured_data") == 1

    def test_data_format_defaults_to_json(self):
        results = [AgentToolResult(tool="test", success=True, output="ok", data=[1, 2])]
        with patch("koda.services.tool_dispatcher.STRUCTURED_DATA_OUTPUT_ENABLED", True):
            formatted = format_tool_results(results)
        assert 'format="json"' in formatted

    def test_unserializable_data_silently_skipped(self):
        class BadObj:
            pass

        results = [AgentToolResult(tool="test", success=True, output="ok", data={"bad": BadObj()})]
        with patch("koda.services.tool_dispatcher.STRUCTURED_DATA_OUTPUT_ENABLED", True):
            formatted = format_tool_results(results)
        # Should not crash — default=str handles it, so structured_data IS present
        assert "ok" in formatted


class TestEnrichedHandlers:
    def test_cron_list_has_structured_data(self):
        from koda.services.tool_dispatcher import ToolContext, _handle_cron_list

        ctx = ToolContext(
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
        fake_jobs = [(1, "*/5 * * * *", "echo hi", "test", True)]
        with (
            patch("koda.services.tool_dispatcher.list_cron_jobs", create=True),
            patch("koda.services.cron_store.list_cron_jobs", return_value=fake_jobs),
        ):
            result = asyncio.run(_handle_cron_list({}, ctx))
        assert result.success
        assert result.data is not None
        assert result.data[0]["id"] == 1
        assert result.data[0]["expression"] == "*/5 * * * *"
        assert result.data[0]["enabled"] is True

    def test_cron_list_empty_no_data(self):
        from koda.services.tool_dispatcher import ToolContext, _handle_cron_list

        ctx = ToolContext(
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
        with patch("koda.services.cron_store.list_cron_jobs", return_value=[]):
            result = asyncio.run(_handle_cron_list({}, ctx))
        assert result.success
        assert result.data is None
