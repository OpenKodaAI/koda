"""Tests for control-plane API rate limiting middleware."""

from __future__ import annotations

import asyncio
import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from multidict import CIMultiDict

from koda.control_plane.rate_limit import (
    _auth_failure_limiters,
    _client_ip,
    _get_auth_failure_limiter,
    _get_ip_limiter,
    _ip_limiters,
    clear_limiters,
    control_plane_rate_limit_middleware,
)

LOGIN_PATH = "/api/control-plane/auth/login"


@pytest.fixture(autouse=True)
def _clean_limiters():
    """Ensure limiter caches are empty before each test."""
    clear_limiters()
    yield
    clear_limiters()


def _make_request(
    *,
    ip: str = "10.0.0.1",
    path: str = "/api/control-plane/agents",
    forwarded_for: str | None = None,
) -> MagicMock:
    request = MagicMock()
    request.headers = CIMultiDict({"X-Forwarded-For": forwarded_for} if forwarded_for is not None else {})
    request.remote = ip
    request.path = path
    return request


def _unauthorized_response() -> MagicMock:
    resp = MagicMock()
    resp.status = 401
    return resp


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


# --- client address resolution (trusted proxies) -----------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        LOGIN_PATH,
        "/api/control-plane/auth/password/recover",
        "/api/control-plane/auth/bootstrap/exchange",
    ],
)
async def test_untrusted_peer_cannot_rotate_x_forwarded_for(path: str) -> None:
    """A direct caller's X-Forwarded-For is ignored, so rotating it never mints a fresh bucket."""
    handler = AsyncMock(return_value=_ok_response())

    with patch("koda.control_plane.rate_limit.emit_security"):
        statuses = [
            (
                await control_plane_rate_limit_middleware(
                    _make_request(ip="203.0.113.7", path=path, forwarded_for=f"198.51.100.{n}"),
                    handler,
                )
            ).status
            for n in range(40)
        ]

    assert 429 in statuses
    # The sensitive budget is spent by the peer itself: once limited, it stays limited.
    first_limited = statuses.index(429)
    assert set(statuses[first_limited:]) == {429}


@pytest.mark.asyncio
async def test_untrusted_peer_cannot_rotate_out_of_auth_failure_bucket() -> None:
    handler = AsyncMock(return_value=_unauthorized_response())

    with (
        patch("koda.control_plane.rate_limit.CONTROL_PLANE_AUTH_FAILURE_RATE_LIMIT", 2),
        patch("koda.control_plane.rate_limit.emit_security"),
    ):
        statuses = [
            (
                await control_plane_rate_limit_middleware(
                    _make_request(ip="203.0.113.7", forwarded_for=f"198.51.100.{n}"),
                    handler,
                )
            ).status
            for n in range(5)
        ]

    assert statuses[:2] == [401, 401]
    assert set(statuses[2:]) == {429}


@pytest.mark.asyncio
async def test_trusted_proxy_gives_each_forwarded_client_its_own_login_bucket() -> None:
    """Through the dashboard (a trusted peer), one client's failures do not lock out another."""
    handler = AsyncMock(return_value=_ok_response())

    with patch("koda.control_plane.rate_limit.emit_security"):
        attacker = [
            (
                await control_plane_rate_limit_middleware(
                    _make_request(ip="127.0.0.1", path=LOGIN_PATH, forwarded_for="198.51.100.66"),
                    handler,
                )
            ).status
            for _ in range(20)
        ]
        owner = await control_plane_rate_limit_middleware(
            _make_request(ip="127.0.0.1", path=LOGIN_PATH, forwarded_for="192.0.2.10"),
            handler,
        )

    assert 429 in attacker
    assert owner.status == 200


@pytest.mark.asyncio
async def test_trusted_proxy_ignores_client_supplied_hops() -> None:
    """Only the hop the trusted proxy appended counts; spoofed entries to its left do not."""
    handler = AsyncMock(return_value=_ok_response())

    with patch("koda.control_plane.rate_limit.emit_security"):
        statuses = [
            (
                await control_plane_rate_limit_middleware(
                    _make_request(
                        ip="127.0.0.1",
                        path=LOGIN_PATH,
                        forwarded_for=f"10.9.{n}.1, 198.51.100.66",
                    ),
                    handler,
                )
            ).status
            for n in range(20)
        ]

    assert 429 in statuses


@pytest.mark.asyncio
async def test_client_ip_walks_trusted_hops_from_the_right() -> None:
    request = _make_request(ip="127.0.0.1", forwarded_for="10.0.0.9, 198.51.100.4, 127.0.0.1")
    with patch(
        "koda.control_plane.rate_limit.CONTROL_PLANE_TRUSTED_PROXIES",
        ("127.0.0.1", "::1"),
    ):
        assert await _client_ip(request) == "198.51.100.4"


@pytest.mark.asyncio
async def test_client_ip_uses_peer_for_untrusted_or_missing_forwarding() -> None:
    assert await _client_ip(_make_request(ip="203.0.113.7", forwarded_for="198.51.100.4")) == "203.0.113.7"
    assert await _client_ip(_make_request(ip="127.0.0.1")) == "127.0.0.1"


@pytest.mark.asyncio
async def test_client_ip_normalizes_ipv4_mapped_peers() -> None:
    request = _make_request(ip="::ffff:127.0.0.1", forwarded_for="198.51.100.4")
    assert await _client_ip(request) == "198.51.100.4"


@pytest.mark.asyncio
async def test_client_ip_stops_at_unparseable_hop() -> None:
    request = _make_request(ip="127.0.0.1", forwarded_for="198.51.100.4, not-an-ip")
    assert await _client_ip(request) == "127.0.0.1"


@pytest.mark.asyncio
async def test_client_ip_honours_empty_trusted_proxy_list() -> None:
    request = _make_request(ip="127.0.0.1", forwarded_for="198.51.100.4")
    with patch("koda.control_plane.rate_limit.CONTROL_PLANE_TRUSTED_PROXIES", ()):
        assert await _client_ip(request) == "127.0.0.1"


@pytest.mark.asyncio
async def test_client_ip_trusts_cidr_entries() -> None:
    request = _make_request(ip="172.18.0.1", forwarded_for="198.51.100.4")
    with patch("koda.control_plane.rate_limit.CONTROL_PLANE_TRUSTED_PROXIES", ("172.18.0.0/16",)):
        assert await _client_ip(request) == "198.51.100.4"


@pytest.mark.asyncio
async def test_client_ip_trusts_resolved_hostname_and_caches_lookup() -> None:
    """`web` (the dashboard Compose service) is trusted by its resolved address only."""
    loop = asyncio.get_running_loop()
    getaddrinfo = AsyncMock(return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.18.0.3", 0))])

    with (
        patch("koda.control_plane.rate_limit.CONTROL_PLANE_TRUSTED_PROXIES", ("web",)),
        patch.object(loop, "getaddrinfo", getaddrinfo),
    ):
        dashboard = await _client_ip(_make_request(ip="172.18.0.3", forwarded_for="198.51.100.4"))
        other_container = await _client_ip(_make_request(ip="172.18.0.9", forwarded_for="198.51.100.4"))
        again = await _client_ip(_make_request(ip="172.18.0.3", forwarded_for="198.51.100.5"))

    assert dashboard == "198.51.100.4"
    assert other_container == "172.18.0.9"
    assert again == "198.51.100.5"
    getaddrinfo.assert_awaited_once()


@pytest.mark.asyncio
async def test_client_ip_treats_unresolvable_hostname_as_untrusted() -> None:
    loop = asyncio.get_running_loop()
    getaddrinfo = AsyncMock(side_effect=socket.gaierror("no such host"))

    with (
        patch("koda.control_plane.rate_limit.CONTROL_PLANE_TRUSTED_PROXIES", ("web",)),
        patch.object(loop, "getaddrinfo", getaddrinfo),
    ):
        assert await _client_ip(_make_request(ip="172.18.0.3", forwarded_for="198.51.100.4")) == "172.18.0.3"


@pytest.mark.asyncio
async def test_real_loopback_proxy_gets_per_client_login_buckets() -> None:
    """End to end over a socket: the dashboard (on loopback) forwards each browser's address."""
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer

    async def login(_request: web.Request) -> web.Response:
        return web.json_response({"error": "Invalid credentials."}, status=400)

    app = web.Application(middlewares=[control_plane_rate_limit_middleware])
    app.router.add_post(LOGIN_PATH, login)

    with (
        patch("koda.control_plane.rate_limit.CONTROL_PLANE_TRUSTED_PROXIES", ("127.0.0.1", "::1")),
        patch("koda.control_plane.rate_limit.emit_security"),
    ):
        async with TestClient(TestServer(app, host="127.0.0.1")) as client:
            attacker = [
                (await client.post(LOGIN_PATH, headers={"X-Forwarded-For": "198.51.100.66"})).status for _ in range(11)
            ]
            owner = await client.post(LOGIN_PATH, headers={"X-Forwarded-For": "192.0.2.10"})

    assert attacker[:10] == [400] * 10
    assert attacker[10] == 429
    assert owner.status == 400
