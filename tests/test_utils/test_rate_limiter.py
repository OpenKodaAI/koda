"""Tests for rate limiter."""

import pytest

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
