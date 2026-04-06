"""Tests for control-plane API rate limiting middleware."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.control_plane.rate_limit import (
    _auth_failure_limiters,
    _get_auth_failure_limiter,
    _get_ip_limiter,
    _ip_limiters,
    clear_limiters,
    control_plane_rate_limit_middleware,
)


@pytest.fixture(autouse=True)
def _clean_limiters():
    """Ensure limiter caches are empty before each test."""
    clear_limiters()
    yield
    clear_limiters()


def _make_request(*, ip: str = "10.0.0.1", path: str = "/api/control-plane/agents") -> MagicMock:
    request = MagicMock()
    request.headers = {}
    request.remote = ip
    request.path = path
    return request


def _ok_response() -> MagicMock:
    resp = MagicMock()
    resp.status = 200
    return resp


def _forbidden_response() -> MagicMock:
    resp = MagicMock()
    resp.status = 403
    return resp


@pytest.mark.asyncio
async def test_requests_within_limit_succeed() -> None:
    """Requests under the rate limit should pass through to the handler."""
    request = _make_request()
    ok = _ok_response()
    handler = AsyncMock(return_value=ok)

    with patch("koda.control_plane.rate_limit.CONTROL_PLANE_RATE_LIMIT", 10):
        clear_limiters()
        for _ in range(5):
            response = await control_plane_rate_limit_middleware(request, handler)
            assert response.status == 200

    assert handler.call_count == 5


@pytest.mark.asyncio
async def test_requests_exceeding_limit_get_429() -> None:
    """Once the bucket is exhausted the middleware should return 429."""
    request = _make_request()
    ok = _ok_response()
    handler = AsyncMock(return_value=ok)

    with patch("koda.control_plane.rate_limit.CONTROL_PLANE_RATE_LIMIT", 3):
        clear_limiters()
        results = []
        for _ in range(6):
            resp = await control_plane_rate_limit_middleware(request, handler)
            results.append(resp.status)

    assert 429 in results
    # The first 3 should succeed.
    assert results[:3] == [200, 200, 200]


@pytest.mark.asyncio
async def test_auth_failures_trigger_stricter_limits() -> None:
    """Auth failures (403) should consume from the stricter auth-failure bucket."""
    request = _make_request()
    forbidden = _forbidden_response()
    handler = AsyncMock(return_value=forbidden)

    with (
        patch("koda.control_plane.rate_limit.CONTROL_PLANE_RATE_LIMIT", 100),
        patch("koda.control_plane.rate_limit.CONTROL_PLANE_AUTH_FAILURE_RATE_LIMIT", 2),
        patch("koda.control_plane.rate_limit.emit_security") as mock_emit,
    ):
        clear_limiters()
        results = []
        for _ in range(5):
            resp = await control_plane_rate_limit_middleware(request, handler)
            results.append(resp.status)

    # First 2 auth failures pass through; subsequent ones hit 429.
    assert results[:2] == [403, 403]
    assert 429 in results[2:]
    # Audit events should have been emitted for the auth failures that passed.
    assert mock_emit.call_count >= 2


@pytest.mark.asyncio
async def test_different_ips_have_independent_buckets() -> None:
    """Two different IPs should not share rate-limit state."""
    request_a = _make_request(ip="10.0.0.1")
    request_b = _make_request(ip="10.0.0.2")
    ok = _ok_response()
    handler = AsyncMock(return_value=ok)

    with patch("koda.control_plane.rate_limit.CONTROL_PLANE_RATE_LIMIT", 3):
        clear_limiters()
        # Exhaust IP A.
        for _ in range(3):
            await control_plane_rate_limit_middleware(request_a, handler)

        # IP A should now be rate-limited.
        resp_a = await control_plane_rate_limit_middleware(request_a, handler)
        assert resp_a.status == 429

        # IP B should still be allowed.
        resp_b = await control_plane_rate_limit_middleware(request_b, handler)
        assert resp_b.status == 200


@pytest.mark.asyncio
async def test_stale_limiter_entries_evicted() -> None:
    """When the LRU cache is full, the oldest entry should be evicted."""
    with patch("koda.control_plane.rate_limit._MAX_CACHED_LIMITERS", 2):
        # Reimport won't help since the constant is read at call time,
        # so we test the underlying function directly.
        from koda.control_plane import rate_limit

        original_max = rate_limit._MAX_CACHED_LIMITERS
        try:
            rate_limit._MAX_CACHED_LIMITERS = 2  # type: ignore[attr-defined]
            clear_limiters()

            _get_ip_limiter("10.0.0.1")
            _get_ip_limiter("10.0.0.2")
            assert len(_ip_limiters) == 2

            # Adding a third should evict the oldest (10.0.0.1).
            _get_ip_limiter("10.0.0.3")
            assert "10.0.0.1" not in _ip_limiters
            assert "10.0.0.3" in _ip_limiters
            assert len(_ip_limiters) == 2
        finally:
            rate_limit._MAX_CACHED_LIMITERS = original_max  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_auth_failure_limiter_eviction() -> None:
    """Auth-failure limiter LRU eviction works the same way."""
    from koda.control_plane import rate_limit

    original_max = rate_limit._MAX_CACHED_LIMITERS
    try:
        rate_limit._MAX_CACHED_LIMITERS = 2  # type: ignore[attr-defined]
        clear_limiters()

        _get_auth_failure_limiter("10.0.0.1")
        _get_auth_failure_limiter("10.0.0.2")
        _get_auth_failure_limiter("10.0.0.3")

        assert "10.0.0.1" not in _auth_failure_limiters
        assert len(_auth_failure_limiters) == 2
    finally:
        rate_limit._MAX_CACHED_LIMITERS = original_max  # type: ignore[attr-defined]
