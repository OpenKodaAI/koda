"""Tests for ProgressTracker phase detection, status, and milestones."""

import time

from koda.utils.progress_tracker import ProgressTracker


class TestDetectPhase:
    def test_analyzing_no_tools(self):
        tracker = ProgressTracker(start_time=time.time())
        assert tracker.detect_phase([]) == "analyzing"

    def test_analyzing_read_only(self):
        tools = [
            {"name": "Read", "input": {"file_path": "/a/b.py"}},
            {"name": "Grep", "input": {"pattern": "foo"}},
        ]
        tracker = ProgressTracker(start_time=time.time())
        assert tracker.detect_phase(tools) == "analyzing"

    def test_implementing_with_write(self):
        tools = [
            {"name": "Read", "input": {"file_path": "/a/b.py"}},
            {"name": "Edit", "input": {"file_path": "/a/b.py"}},
        ]
        tracker = ProgressTracker(start_time=time.time())
        assert tracker.detect_phase(tools) == "implementing"

    def test_testing_with_pytest(self):
        tools = [
            {"name": "Bash", "input": {"command": "pytest tests/ -v"}},
        ]
        tracker = ProgressTracker(start_time=time.time())
        assert tracker.detect_phase(tools) == "testing"

    def test_testing_with_npm_test(self):
        tools = [
            {"name": "Bash", "input": {"command": "npm test"}},
        ]
        tracker = ProgressTracker(start_time=time.time())
        assert tracker.detect_phase(tools) == "testing"


class TestBuildStatus:
    def test_no_tools(self):
        tracker = ProgressTracker(start_time=time.time())
        status = tracker.build_status(30.0, [])
        assert "Analisando" in status
        assert "30s" in status

    def test_with_tools(self):
        tools = [
            {"name": "Read", "input": {"file_path": "/a/main.py"}},
            {"name": "Edit", "input": {"file_path": "/a/config.py"}},
            {"name": "Bash", "input": {"command": "pytest"}},
        ]
        tracker = ProgressTracker(start_time=time.time())
        status = tracker.build_status(45.0, tools)
        # Should have counters
        assert "\U0001f4d6" in status  # read icon
        assert "\u270f\ufe0f" in status  # write icon
        assert "\u26a1" in status  # exec icon
        # Should have last tool label
        assert "\u21b3" in status


class TestCheckMilestone:
    def test_not_before_30s(self):
        tracker = ProgressTracker(start_time=time.time())
        result = tracker.check_milestone(20.0, [])
        assert result is None

    def test_at_45s_interval(self):
        tracker = ProgressTracker(start_time=time.time())
        result = tracker.check_milestone(50.0, [{"name": "Read", "input": {}}])
        assert result is not None
        assert "50s" in result

    def test_skips_if_too_soon(self):
        tracker = ProgressTracker(start_time=time.time())
        # First milestone at 50s
        result1 = tracker.check_milestone(50.0, [])
        assert result1 is not None
        # Too soon (only 20s later, need 45s)
        result2 = tracker.check_milestone(70.0, [])
        assert result2 is None
        # After 45s interval (50 + 45 = 95)
        result3 = tracker.check_milestone(96.0, [])
        assert result3 is not None
