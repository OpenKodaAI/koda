"""Tests for progress utility functions."""

from koda.utils.progress import _format_elapsed


class TestFormatElapsed:
    def test_seconds(self):
        assert _format_elapsed(0) == "0s"
        assert _format_elapsed(30) == "30s"
        assert _format_elapsed(59) == "59s"

    def test_minutes(self):
        assert _format_elapsed(60) == "1m"
        assert _format_elapsed(150) == "2m30s"

    def test_hours(self):
        assert _format_elapsed(3600) == "1h"
        assert _format_elapsed(3900) == "1h5m"
