"""Tests for memory/maintenance_scheduler.py."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from koda.memory.maintenance_scheduler import _seconds_until_hour


class TestSecondsUntilHour:
    def test_seconds_until_future_hour(self):
        """Target hour later today returns positive seconds."""
        now = datetime(2026, 3, 15, 10, 0, 0)
        with patch("koda.memory.maintenance_scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = _seconds_until_hour(14)
            assert result == pytest.approx(4 * 3600, abs=1)

    def test_seconds_until_past_hour(self):
        """Target hour already passed today → calculates for tomorrow."""
        now = datetime(2026, 3, 15, 16, 0, 0)
        with patch("koda.memory.maintenance_scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = _seconds_until_hour(3)
            # From 16:00 today to 03:00 tomorrow = 11 hours
            assert result == pytest.approx(11 * 3600, abs=1)

    def test_seconds_until_same_hour(self):
        """Exact current hour → target is tomorrow (target <= now)."""
        now = datetime(2026, 3, 15, 3, 0, 0)
        with patch("koda.memory.maintenance_scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = _seconds_until_hour(3)
            # Exactly 24 hours
            assert result == pytest.approx(24 * 3600, abs=1)


class TestStartMaintenanceLoop:
    @pytest.mark.asyncio
    async def test_first_run_no_previous(self):
        """No previous maintenance → runs immediately on startup."""
        mock_store = AsyncMock()
        summary = {"expired_cleaned": 0, "importance_decayed": 0, "ttls_extended": 0}

        with (
            patch("koda.memory.maintenance_scheduler.get_last_maintenance", return_value=None),
            patch(
                "koda.memory.maintenance_scheduler.run_maintenance", new_callable=AsyncMock, return_value=summary
            ) as mock_run,
            patch("koda.memory.maintenance_scheduler._seconds_until_hour", return_value=100),
            patch("koda.memory.maintenance_scheduler.asyncio.sleep", side_effect=asyncio.CancelledError),
        ):
            from koda.memory.maintenance_scheduler import start_maintenance_loop

            await start_maintenance_loop(mock_store)

            # Should have been called once on startup (first run)
            mock_run.assert_called_once_with(mock_store)

    @pytest.mark.asyncio
    async def test_catchup_over_24h(self):
        """Last maintenance >24h ago → runs immediately."""
        mock_store = AsyncMock()
        old_time = (datetime.now() - timedelta(hours=30)).isoformat()
        summary = {"expired_cleaned": 0, "importance_decayed": 0, "ttls_extended": 0}

        with (
            patch("koda.memory.maintenance_scheduler.get_last_maintenance", return_value=old_time),
            patch(
                "koda.memory.maintenance_scheduler.run_maintenance", new_callable=AsyncMock, return_value=summary
            ) as mock_run,
            patch("koda.memory.maintenance_scheduler._seconds_until_hour", return_value=100),
            patch("koda.memory.maintenance_scheduler.asyncio.sleep", side_effect=asyncio.CancelledError),
        ):
            from koda.memory.maintenance_scheduler import start_maintenance_loop

            await start_maintenance_loop(mock_store)

            # Should have been called once (catchup on startup)
            mock_run.assert_called_once_with(mock_store)

    @pytest.mark.asyncio
    async def test_no_catchup_recent(self):
        """Last maintenance 2h ago → does NOT run before entering loop."""
        mock_store = AsyncMock()
        recent_time = (datetime.now() - timedelta(hours=2)).isoformat()

        with (
            patch("koda.memory.maintenance_scheduler.get_last_maintenance", return_value=recent_time),
            patch("koda.memory.maintenance_scheduler.run_maintenance", new_callable=AsyncMock) as mock_run,
            patch("koda.memory.maintenance_scheduler._seconds_until_hour", return_value=100),
            patch("koda.memory.maintenance_scheduler.asyncio.sleep", side_effect=asyncio.CancelledError),
        ):
            from koda.memory.maintenance_scheduler import start_maintenance_loop

            await start_maintenance_loop(mock_store)

            # Should NOT have been called (recent, and sleep raises CancelledError before loop body)
            mock_run.assert_not_called()
