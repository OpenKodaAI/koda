"""Tests for rate limiter."""

from unittest.mock import patch

import pytest

from koda.utils import rate_limiter
from koda.utils.rate_limiter import acquire_rate_limit, check_rate_limit, get_limiter


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_allows_within_limit(self):
        user_id = 9999
        result = await acquire_rate_limit(user_id)
        assert result is True

    @pytest.mark.asyncio
    async def test_has_capacity_initially(self):
        user_id = 9998
        result = await check_rate_limit(user_id)
        assert result is True

    def test_get_limiter_creates_new(self):
        limiter = get_limiter(8888)
        assert limiter is not None

    def test_get_limiter_reuses_existing(self):
        limiter1 = get_limiter(7777)
        limiter2 = get_limiter(7777)
        assert limiter1 is limiter2

    @pytest.mark.asyncio
    async def test_rejects_after_limit_exhausted(self):
        """Core behavior: limiter should reject after capacity is exhausted."""
        user_id = 6666
        # Exhaust all tokens (default RATE_LIMIT_PER_MINUTE=10)
        for _ in range(10):
            result = await acquire_rate_limit(user_id)
            assert result is True

        # Next request should be rejected
        result = await acquire_rate_limit(user_id)
        assert result is False


class TestTTLEviction:
    """Tests for TTL-based eviction replacing LRU."""

    def setup_method(self):
        """Clear module state before each test."""
        rate_limiter._user_limiters.clear()
        rate_limiter._call_count = 0

    def test_active_user_preserved(self):
        """An active user's limiter must not be evicted."""
        limiter = get_limiter(100)
        # Access again — same object should be returned.
        assert get_limiter(100) is limiter

    def test_stale_entry_evicted(self):
        """Entries older than TTL are removed on sweep."""
        import time

        fake_time = [1000.0]

        def _mono():
            return fake_time[0]

        with patch.object(time, "monotonic", side_effect=_mono):
            # Insert at t=1000
            get_limiter(200)

        # Advance past TTL (300 s) and insert a new user to trigger sweep
        fake_time[0] = 1000.0 + rate_limiter._LIMITER_TTL_SECONDS + 1
        with patch.object(time, "monotonic", side_effect=_mono):
            # Force sweep by setting call_count to a multiple of 50
            rate_limiter._call_count = 49
            get_limiter(201)

        # The stale entry should have been swept.
        assert 200 not in rate_limiter._user_limiters

    def test_safety_cap(self):
        """Cache never exceeds _MAX_CACHED_LIMITERS."""
        # Use a small cap to keep the test fast.
        with patch.object(rate_limiter, "_MAX_CACHED_LIMITERS", 10), patch.object(rate_limiter, "_SWEEP_THRESHOLD", 5):
            for uid in range(15):
                get_limiter(uid)

            assert len(rate_limiter._user_limiters) <= 10

    def test_limiter_reused_across_calls(self):
        """Same user always receives the same limiter object."""
        a = get_limiter(300)
        b = get_limiter(300)
        c = get_limiter(300)
        assert a is b is c

    def test_new_limiter_for_unknown_user(self):
        """A previously unseen user gets a fresh limiter."""
        limiter = get_limiter(400)
        assert limiter is not None
        assert 400 in rate_limiter._user_limiters

    def test_timestamp_updated_on_access(self):
        """Accessing a limiter refreshes its timestamp."""
        import time

        fake_time = [1000.0]

        def _mono():
            return fake_time[0]

        with patch.object(time, "monotonic", side_effect=_mono):
            get_limiter(500)

        _, ts_before = rate_limiter._user_limiters[500]

        fake_time[0] = 1050.0
        with patch.object(time, "monotonic", side_effect=_mono):
            get_limiter(500)

        _, ts_after = rate_limiter._user_limiters[500]
        assert ts_after > ts_before
