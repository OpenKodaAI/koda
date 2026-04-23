"""Tests for tool use parser."""

import json

from koda.utils.tool_parser import (
    format_completion_summary,
    format_tool_summary,
    parse_tool_uses,
    summarize_tool_uses,
)


class TestParseToolUses:
    def test_parse_tool_use_event(self):
        line = json.dumps(
            {
                "type": "tool_use",
                "name": "Read",
                "input": {"file_path": "/src/main.py"},
            }
        )
        tools = parse_tool_uses(line)
        assert len(tools) == 1
        assert tools[0]["name"] == "Read"
        assert "main.py" in tools[0]["input"]

    def test_parse_content_array(self):
        line = json.dumps(
            {
                "content": [
                    {"type": "tool_use", "name": "Edit", "input": {"file_path": "/a/b.py"}},
                    {"type": "text", "text": "some text"},
                ]
            }
        )
        tools = parse_tool_uses(line)
        assert len(tools) == 1
        assert tools[0]["name"] == "Edit"

    def test_no_tools(self):
        line = json.dumps({"type": "text", "text": "hello"})
        tools = parse_tool_uses(line)
        assert len(tools) == 0

    def test_multiple_lines(self):
        lines = "\n".join(
            [
                json.dumps({"type": "tool_use", "name": "Read", "input": {"file_path": "a.py"}}),
                json.dumps({"type": "tool_use", "name": "Edit", "input": {"file_path": "b.py"}}),
            ]
        )
        tools = parse_tool_uses(lines)
        assert len(tools) == 2

    def test_invalid_json_skipped(self):
        lines = "not json\n" + json.dumps({"type": "tool_use", "name": "Bash", "input": {"command": "ls"}})
        tools = parse_tool_uses(lines)
        assert len(tools) == 1

    def test_bash_summary(self):
        line = json.dumps(
            {
                "type": "tool_use",
                "name": "Bash",
                "input": {"command": "npm test"},
            }
        )
        tools = parse_tool_uses(line)
        assert tools[0]["input"] == "npm test"


class TestFormatToolSummary:
    def test_single_tool(self):
        tools = [{"name": "Read", "input": "main.py"}]
        result = format_tool_summary(tools)
        assert "Read(main.py)" in result
        assert result.startswith("🔧")

    def test_multiple_same_tool(self):
        tools = [
            {"name": "Read", "input": "a.py"},
            {"name": "Read", "input": "a.py"},
        ]
        result = format_tool_summary(tools)
        assert "x2" in result

    def test_empty_list(self):
        assert format_tool_summary([]) == ""

    def test_mixed_tools(self):
        tools = [
            {"name": "Read", "input": "a.py"},
            {"name": "Edit", "input": "b.py"},
        ]
        result = format_tool_summary(tools)
        assert "Read" in result
        assert "Edit" in result


class TestSummarizeToolUses:
    def test_basic_summarize(self):
        tool_uses = [
            {"name": "Read", "input": {"file_path": "/src/main.py"}},
            {"name": "Bash", "input": {"command": "npm test"}},
        ]
        result = summarize_tool_uses(tool_uses)
        assert "Read(main.py)" in result
        assert "Bash(npm test)" in result
        assert result.startswith("🔧")

    def test_empty_list(self):
        assert summarize_tool_uses([]) == ""

    def test_deduplicates(self):
        tool_uses = [
            {"name": "Read", "input": {"file_path": "/a.py"}},
            {"name": "Read", "input": {"file_path": "/b.py"}},
        ]
        result = summarize_tool_uses(tool_uses)
        assert "x2" in result

    def test_no_input(self):
        tool_uses = [{"name": "Unknown"}]
        result = summarize_tool_uses(tool_uses)
        assert "Unknown" in result


class TestFormatToolSummaryGrouped:
    def test_grouped_format_over_5_tools(self):
        tools = [
            {"name": "Read", "input": "a.py"},
            {"name": "Read", "input": "b.py"},
            {"name": "Read", "input": "c.py"},
            {"name": "Edit", "input": "d.py"},
            {"name": "Bash", "input": "npm test"},
            {"name": "Bash", "input": "npm build"},
        ]
        result = format_tool_summary(tools)
        assert "Ferramentas:" in result
        assert "Leitura:" in result
        assert "Escrita:" in result
        assert "Execu" in result  # Execução

    def test_compact_format_5_or_fewer(self):
        tools = [
            {"name": "Read", "input": "a.py"},
            {"name": "Edit", "input": "b.py"},
        ]
        result = format_tool_summary(tools)
        assert "Used:" in result
        assert "Ferramentas:" not in result


class TestFormatCompletionSummary:
    def test_short_task_returns_empty(self):
        tools = [{"name": "Read", "input": {"file_path": "/a.py"}}]
        assert format_completion_summary(tools, 5.0) == ""

    def test_few_tools_returns_empty(self):
        tools = [
            {"name": "Read", "input": {"file_path": "/a.py"}},
            {"name": "Edit", "input": {"file_path": "/b.py"}},
        ]
        assert format_completion_summary(tools, 30.0) == ""

    def test_long_task_returns_summary(self):
        tools = [
            {"name": "Read", "input": {"file_path": "/a/main.py"}},
            {"name": "Grep", "input": {"pattern": "TODO"}},
            {"name": "Edit", "input": {"file_path": "/a/config.py"}},
            {"name": "Bash", "input": {"command": "pytest"}},
        ]
        result = format_completion_summary(tools, 60.0)
        assert "Conclu" in result  # Concluído
        assert "1m" in result
        assert "config.py" in result
