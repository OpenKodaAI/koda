"""Tests for image utilities."""

from koda.utils.images import (
    _in_flight_images,
    build_image_prompt,
    cleanup_previous_images,
    track_images,
    untrack_images,
)


class TestBuildImagePrompt:
    def test_with_caption(self):
        result = build_image_prompt("Analyze this", ["/tmp/img.jpg"])
        assert "Analyze this" in result
        assert "/tmp/img.jpg" in result

    def test_without_caption_uses_default(self):
        result = build_image_prompt(None, ["/tmp/img.jpg"])
        assert "Describe and analyze" in result

    def test_multiple_images(self):
        result = build_image_prompt("test", ["/tmp/a.jpg", "/tmp/b.png"])
        assert "/tmp/a.jpg" in result
        assert "/tmp/b.png" in result


class TestImageTracking:
    def test_track_and_untrack(self):
        track_images(["/tmp/test1.jpg"])
        assert "/tmp/test1.jpg" in _in_flight_images
        untrack_images(["/tmp/test1.jpg"])
        assert "/tmp/test1.jpg" not in _in_flight_images

    def test_untrack_none(self):
        untrack_images(None)  # should not raise


class TestCleanupPreviousImages:
    def test_no_last_query(self):
        user_data = {}
        cleanup_previous_images(user_data)  # should not raise

    def test_no_image_paths(self):
        user_data = {"last_query": {"text": "hello"}}
        cleanup_previous_images(user_data)  # should not raise

    def test_deletes_files(self, tmp_path):
        img = tmp_path / "test.jpg"
        img.write_text("fake image")
        user_data = {"last_query": {"text": "test", "image_paths": [str(img)]}}
        cleanup_previous_images(user_data)
        assert not img.exists()

    def test_skips_in_flight_images(self, tmp_path):
        """Bug fix test: images tracked as in-flight should not be deleted."""
        img = tmp_path / "queued.jpg"
        img.write_text("fake image")
        user_data = {"last_query": {"text": "test", "image_paths": [str(img)]}}

        track_images([str(img)])
        try:
            cleanup_previous_images(user_data)
            assert img.exists()  # should NOT be deleted
        finally:
            untrack_images([str(img)])

    def test_handles_missing_files(self):
        user_data = {"last_query": {"text": "test", "image_paths": ["/nonexistent/file.jpg"]}}
        cleanup_previous_images(user_data)  # should not raise
