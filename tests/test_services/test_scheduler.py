"""Tests for scheduling utilities."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from koda.services.scheduler import parse_interval, parse_time_delta, schedule_recurring, schedule_reminder


class TestParseTimeDelta:
    def test_seconds(self):
        assert parse_time_delta("30s") == timedelta(seconds=30)

    def test_minutes(self):
        assert parse_time_delta("5m") == timedelta(minutes=5)

    def test_hours(self):
        assert parse_time_delta("2h") == timedelta(hours=2)

    def test_days(self):
        assert parse_time_delta("1d") == timedelta(days=1)

    def test_longer_unit_names(self):
        assert parse_time_delta("30sec") == timedelta(seconds=30)
        assert parse_time_delta("5min") == timedelta(minutes=5)
        assert parse_time_delta("2hr") == timedelta(hours=2)
        assert parse_time_delta("1day") == timedelta(days=1)

    def test_invalid(self):
        assert parse_time_delta("abc") is None
        assert parse_time_delta("") is None
        assert parse_time_delta("5x") is None

    def test_with_whitespace(self):
        assert parse_time_delta(" 5m ") == timedelta(minutes=5)


class TestParseInterval:
    def test_every_minutes(self):
        assert parse_interval("every 30m") == timedelta(minutes=30)

    def test_every_hours(self):
        assert parse_interval("every 2h") == timedelta(hours=2)

    def test_every_days(self):
        assert parse_interval("every 1d") == timedelta(days=1)

    def test_invalid(self):
        assert parse_interval("30m") is None  # missing "every"
        assert parse_interval("every abc") is None
        assert parse_interval("") is None


@pytest.mark.asyncio
async def test_schedule_reminder_reports_auto_activation():
    with patch("koda.services.scheduler.create_reminder_job", return_value=12):
        message = await schedule_reminder(MagicMock(), 222, 111, timedelta(minutes=5), "Check the build")

    assert "job #12" in message
    assert "activated automatically" in message


@pytest.mark.asyncio
async def test_schedule_recurring_reports_auto_activation():
    context = MagicMock()
    context.user_data = {"provider": "codex", "model": "gpt-5.4-mini", "work_dir": "/tmp", "session_id": "sess-1"}

    with patch("koda.services.scheduler.create_agent_query_job", return_value=18):
        message = await schedule_recurring(context, 222, 111, timedelta(hours=2), "Check deploy status")

    assert "job #18" in message
    assert "activated automatically" in message
