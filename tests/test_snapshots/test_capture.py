"""Tests for snapshot capture with mocked subsystems."""

from unittest.mock import MagicMock

import pytest

from koda.snapshots.capture import capture_snapshot


class TestCaptureFilesystem:
    @pytest.mark.asyncio
    async def test_captures_work_dir(self, tmp_path):
        # Create some files
        (tmp_path / "file1.txt").write_text("hello")
        (tmp_path / "file2.py").write_text("x = 1")
        (tmp_path / "subdir").mkdir()

        result = await capture_snapshot(1, str(tmp_path))
        assert result["scope_id"] == 1
        assert result["work_dir"] == str(tmp_path)
        assert "captured_at" in result
        fs = result["subsystems"]["filesystem"]
        assert fs["count"] == 3
        names = [e["name"] for e in fs["entries"]]
        assert "file1.txt" in names
        assert "subdir" in names

    @pytest.mark.asyncio
    async def test_nonexistent_dir(self):
        result = await capture_snapshot(1, "/nonexistent/path")
        # Filesystem should not be captured (dir does not exist)
        assert "filesystem" not in result["subsystems"] or result["subsystems"].get("filesystem", {}).get("error")

    @pytest.mark.asyncio
    async def test_entries_capped_at_500(self, tmp_path):
        for i in range(600):
            (tmp_path / f"file_{i:04d}.txt").write_text("x")
        result = await capture_snapshot(1, str(tmp_path))
        fs = result["subsystems"]["filesystem"]
        assert fs["count"] == 500


class TestCaptureSubsystemErrors:
    @pytest.mark.asyncio
    async def test_browser_import_error_swallowed(self, tmp_path, monkeypatch):
        """Browser subsystem import errors should be silently handled."""
        monkeypatch.setattr("koda.snapshots.capture.log", MagicMock())
        result = await capture_snapshot(1, str(tmp_path))
        # Should not crash
        assert "subsystems" in result
