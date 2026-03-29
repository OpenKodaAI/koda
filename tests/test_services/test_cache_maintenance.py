"""Tests for cache maintenance scheduler."""

from unittest.mock import patch

import pytest

from koda.services.cache_maintenance import _run_cleanup


class TestRunCleanup:
    @patch("koda.services.cache_maintenance.script_cleanup_low_quality")
    @patch("koda.services.cache_maintenance.cache_enforce_user_limit")
    @patch("koda.services.cache_maintenance.cache_get_all_active_user_ids")
    @patch("koda.services.cache_maintenance.cache_cleanup_expired")
    @pytest.mark.asyncio
    async def test_cleanup_expired_entries(self, mock_expired, mock_user_ids, mock_enforce, mock_low_q):
        mock_expired.return_value = 5
        mock_user_ids.return_value = []
        mock_low_q.return_value = 0

        await _run_cleanup()
        assert "agent_id" in mock_expired.call_args.kwargs

    @patch("koda.services.cache_maintenance.script_cleanup_low_quality")
    @patch("koda.services.cache_maintenance.cache_enforce_user_limit")
    @patch("koda.services.cache_maintenance.cache_get_all_active_user_ids")
    @patch("koda.services.cache_maintenance.cache_cleanup_expired")
    @pytest.mark.asyncio
    async def test_enforce_per_user_limit(self, mock_expired, mock_user_ids, mock_enforce, mock_low_q):
        mock_expired.return_value = 0
        mock_user_ids.return_value = [111, 222]
        mock_enforce.return_value = 3
        mock_low_q.return_value = 0

        await _run_cleanup()
        assert mock_enforce.call_count == 2
        for call in mock_enforce.call_args_list:
            assert "agent_id" in call.kwargs

    @patch("koda.services.cache_maintenance.script_cleanup_low_quality")
    @patch("koda.services.cache_maintenance.cache_enforce_user_limit")
    @patch("koda.services.cache_maintenance.cache_get_all_active_user_ids")
    @patch("koda.services.cache_maintenance.cache_cleanup_expired")
    @pytest.mark.asyncio
    async def test_cleanup_low_quality_scripts(self, mock_expired, mock_user_ids, mock_enforce, mock_low_q):
        mock_expired.return_value = 0
        mock_user_ids.return_value = []
        mock_low_q.return_value = 2

        await _run_cleanup()
        kwargs = mock_low_q.call_args.kwargs
        assert kwargs["threshold"] == 0.1
        assert "agent_id" in kwargs
