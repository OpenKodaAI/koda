"""Tests for snapshot prompt section in tool_prompt."""

from unittest.mock import patch


class TestSnapshotPromptSection:
    @patch("koda.services.tool_prompt.SNAPSHOT_ENABLED", True)
    def test_snapshot_section_present_when_enabled(self):
        from koda.services.tool_prompt import build_agent_tools_prompt

        prompt = build_agent_tools_prompt()
        assert "Environment Snapshots" in prompt
        assert "snapshot_save" not in prompt
        assert "snapshot_delete" not in prompt

    @patch("koda.services.tool_prompt.SNAPSHOT_ENABLED", False)
    def test_snapshot_section_absent_when_disabled(self):
        from koda.services.tool_prompt import build_agent_tools_prompt

        prompt = build_agent_tools_prompt()
        assert "Environment Snapshots" not in prompt
