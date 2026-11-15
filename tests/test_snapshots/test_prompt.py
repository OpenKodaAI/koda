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

    @patch("koda.services.tool_prompt.SNAPSHOT_ENABLED", True)
    def test_snapshot_restore_is_described_as_load_for_inspection(self):
        """F-SKL-14 (M6-E3-T6): the description matches the behaviour."""
        from koda.services.tool_prompt import build_agent_tools_prompt

        prompt = build_agent_tools_prompt()
        section = prompt.split("### Environment Snapshots", 1)[1].split("\n### ", 1)[0]
        restore_line = next(line for line in section.splitlines() if "`snapshot_restore`" in line)
        assert "Load a saved snapshot for inspection" in restore_line
        assert "does not restore" in restore_line
        assert "restore complete agent environment state" not in section
