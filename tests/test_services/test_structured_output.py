"""Tests for structured data output feature."""

from unittest.mock import patch

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
