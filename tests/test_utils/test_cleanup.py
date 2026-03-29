"""Tests for periodic temp file cleanup (P1-3)."""

import os
import time
from unittest.mock import patch

from koda.utils.images import _cleanup_stale_files, _in_flight_images


class TestCleanupStaleFiles:
    def test_removes_old_files(self, tmp_path):
        # Create a file with old mtime (2 hours ago)
        old_file = tmp_path / "old_image.jpg"
        old_file.write_text("old")
        old_mtime = time.time() - 7200
        os.utime(old_file, (old_mtime, old_mtime))

        with patch("koda.utils.images.IMAGE_TEMP_DIR", tmp_path):
            _cleanup_stale_files()

        assert not old_file.exists()

    def test_keeps_recent_files(self, tmp_path):
        recent_file = tmp_path / "recent_image.jpg"
        recent_file.write_text("recent")

        with patch("koda.utils.images.IMAGE_TEMP_DIR", tmp_path):
            _cleanup_stale_files()

        assert recent_file.exists()

    def test_skips_in_flight_files(self, tmp_path):
        old_file = tmp_path / "in_flight.jpg"
        old_file.write_text("in flight")
        old_mtime = time.time() - 7200
        os.utime(old_file, (old_mtime, old_mtime))

        _in_flight_images.add(str(old_file))
        try:
            with patch("koda.utils.images.IMAGE_TEMP_DIR", tmp_path):
                _cleanup_stale_files()
            assert old_file.exists()
        finally:
            _in_flight_images.discard(str(old_file))

    def test_skips_directories(self, tmp_path):
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        with patch("koda.utils.images.IMAGE_TEMP_DIR", tmp_path):
            _cleanup_stale_files()

        assert subdir.exists()

    def test_handles_missing_temp_dir(self, tmp_path):
        nonexistent = tmp_path / "nonexistent"
        with patch("koda.utils.images.IMAGE_TEMP_DIR", nonexistent):
            _cleanup_stale_files()  # Should not raise

    def test_mixed_old_and_new(self, tmp_path):
        old_file = tmp_path / "old.jpg"
        old_file.write_text("old")
        old_mtime = time.time() - 7200
        os.utime(old_file, (old_mtime, old_mtime))

        new_file = tmp_path / "new.jpg"
        new_file.write_text("new")

        with patch("koda.utils.images.IMAGE_TEMP_DIR", tmp_path):
            _cleanup_stale_files()

        assert not old_file.exists()
        assert new_file.exists()
