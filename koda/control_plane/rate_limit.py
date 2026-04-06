"""Token-bucket rate limiter middleware for the control-plane API.

Uses aiolimiter with an LRU dict for per-IP limiters, mirroring the pattern
in ``koda/utils/rate_limiter.py``.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Awaitable, Callable

from aiohttp import web
from aiolimiter import AsyncLimiter

from koda.logging_config import get_logger
from koda.services.audit import emit_security

from .settings import CONTROL_PLANE_AUTH_FAILURE_RATE_LIMIT, CONTROL_PLANE_RATE_LIMIT

log = get_logger(__name__)

_MAX_CACHED_LIMITERS = 256

# Per-IP general-purpose rate limiters with LRU eviction.
_ip_limiters: OrderedDict[str, AsyncLimiter] = OrderedDict()

# Per-IP auth-failure rate limiters (stricter).
_auth_failure_limiters: OrderedDict[str, AsyncLimiter] = OrderedDict()


def _get_ip_limiter(ip: str) -> AsyncLimiter:
    """Return or create the general rate limiter for *ip*."""
    if ip in _ip_limiters:
        _ip_limiters.move_to_end(ip)
        return _ip_limiters[ip]
    if len(_ip_limiters) >= _MAX_CACHED_LIMITERS:
        _ip_limiters.popitem(last=False)
    _ip_limiters[ip] = AsyncLimiter(CONTROL_PLANE_RATE_LIMIT, 60)
    return _ip_limiters[ip]


def _get_auth_failure_limiter(ip: str) -> AsyncLimiter:
    """Return or create the auth-failure rate limiter for *ip*."""
    if ip in _auth_failure_limiters:
        _auth_failure_limiters.move_to_end(ip)
        return _auth_failure_limiters[ip]
    if len(_auth_failure_limiters) >= _MAX_CACHED_LIMITERS:
        _auth_failure_limiters.popitem(last=False)
    _auth_failure_limiters[ip] = AsyncLimiter(CONTROL_PLANE_AUTH_FAILURE_RATE_LIMIT, 60)
    return _auth_failure_limiters[ip]


def _client_ip(request: web.Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    peer = request.remote
    return peer or "unknown"


def _too_many_requests() -> web.Response:
    return web.json_response(
        {"error": "rate limit exceeded"},
        status=429,
        headers={"Retry-After": "60"},
    )


@web.middleware
async def control_plane_rate_limit_middleware(
    request: web.Request,
    handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
) -> web.StreamResponse:
    """Enforce per-IP rate limiting on all control-plane API requests."""
    # Exempt login session polling and code submission from rate limiting.
    if "/connection/login/" in request.path:
        return await handler(request)

    ip = _client_ip(request)

    # General rate check — single atomic acquire to avoid TOCTOU race.
    limiter = _get_ip_limiter(ip)
    if not limiter.has_capacity():
        log.warning("rate_limit_exceeded", ip=ip, path=request.path)
        return _too_many_requests()
    # has_capacity() is a non-blocking peek; acquire() consumes a token.
    # Both run on the single-threaded asyncio loop, so no interleaving
    # between the check and the acquire within this coroutine step.
    await limiter.acquire()

    response = await handler(request)

    # On auth failures (401/403) apply the stricter auth-failure bucket.
    if response.status in {401, 403}:
        emit_security(
            "security.control_plane_auth_failure",
            ip=ip,
            path=request.path,
            status=response.status,
        )
        auth_limiter = _get_auth_failure_limiter(ip)
        if not auth_limiter.has_capacity():
            log.warning("auth_failure_rate_limit_exceeded", ip=ip, path=request.path)
            return _too_many_requests()
        await auth_limiter.acquire()

    return response


def clear_limiters() -> None:
    """Reset all cached limiters. Intended for tests."""
    _ip_limiters.clear()
    _auth_failure_limiters.clear()
