"""Token-bucket rate limiter middleware for the control-plane API.

Uses aiolimiter with an LRU dict for per-IP limiters, mirroring the pattern
in ``koda/utils/rate_limiter.py``.

Buckets are keyed by the TCP peer address. Only when the peer is a trusted
proxy (``CONTROL_PLANE_TRUSTED_PROXIES``: loopback and the dashboard by
default) is ``X-Forwarded-For`` read, from the right, skipping trusted hops;
the first untrusted address is the client. Entries further left are
client-supplied, so rotating them never yields a fresh bucket.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from functools import lru_cache

from aiohttp import web
from aiolimiter import AsyncLimiter

from koda.logging_config import get_logger
from koda.services.audit import emit_security

from .settings import (
    CONTROL_PLANE_AUTH_FAILURE_RATE_LIMIT,
    CONTROL_PLANE_RATE_LIMIT,
    CONTROL_PLANE_TRUSTED_PROXIES,
)

log = get_logger(__name__)

_IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
_IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

# Trusted-proxy hostnames (the `web` Compose service) are re-resolved at most
# this often, so a restarted dashboard container is trusted again quickly.
_TRUSTED_HOSTNAME_TTL_SECONDS = 10.0
_resolved_trusted_hostnames: dict[str, tuple[float, frozenset[_IPAddress]]] = {}

_MAX_CACHED_LIMITERS = 256

# Per-IP general-purpose rate limiters with LRU eviction.
_ip_limiters: OrderedDict[str, AsyncLimiter] = OrderedDict()

# Per-IP auth-failure rate limiters (stricter).
_auth_failure_limiters: OrderedDict[str, AsyncLimiter] = OrderedDict()

# Per-(endpoint,IP) strict limiters for sensitive auth paths.
# Key: f"{endpoint}:{ip}". Configured once at module load.
_endpoint_limiters: OrderedDict[str, AsyncLimiter] = OrderedDict()

# (max_burst, window_seconds) — deliberately tight on sensitive paths.
#
# NOTE on register-owner: the owner account is created exactly ONCE per
# instance lifetime, but the first-time setup UX often needs retries (password
# policy feedback, typos in the bootstrap code, copy/paste glitches). The
# global per-IP quota still caps raw volume at CONTROL_PLANE_RATE_LIMIT/min,
# so this budget only exists to stop a dedicated attacker from brute-forcing
# the bootstrap code — which is already 14 chars from a 32-symbol alphabet.
_SENSITIVE_ENDPOINT_BUDGETS: dict[str, tuple[int, int]] = {
    "/api/control-plane/auth/login": (10, 300),
    "/api/control-plane/auth/password/recover": (10, 3600),
    "/api/control-plane/auth/password/change": (20, 3600),
    "/api/control-plane/auth/profile": (60, 3600),
    "/api/control-plane/auth/register-owner": (30, 3600),
    "/api/control-plane/auth/recovery-codes/regenerate": (10, 3600),
    "/api/control-plane/auth/bootstrap/exchange": (30, 3600),
    "/api/control-plane/auth/bootstrap/codes": (10, 3600),
}


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


def _get_endpoint_limiter(endpoint: str, ip: str) -> AsyncLimiter | None:
    """Return the dedicated limiter for `endpoint` from `ip`, or None if the path is not sensitive."""
    budget = _SENSITIVE_ENDPOINT_BUDGETS.get(endpoint)
    if budget is None:
        return None
    max_burst, window = budget
    key = f"{endpoint}:{ip}"
    if key in _endpoint_limiters:
        _endpoint_limiters.move_to_end(key)
        return _endpoint_limiters[key]
    if len(_endpoint_limiters) >= _MAX_CACHED_LIMITERS:
        _endpoint_limiters.popitem(last=False)
    _endpoint_limiters[key] = AsyncLimiter(max_burst, window)
    return _endpoint_limiters[key]


def _parse_ip(value: object) -> _IPAddress | None:
    try:
        address = ipaddress.ip_address(str(value or "").strip())
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


@lru_cache(maxsize=4)
def _trusted_proxy_rules(entries: tuple[str, ...]) -> tuple[tuple[_IPNetwork, ...], tuple[str, ...]]:
    """Split the configured entries into IP networks and hostnames."""
    networks: list[_IPNetwork] = []
    hostnames: list[str] = []
    for entry in entries:
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            hostnames.append(entry.lower())
    return tuple(networks), tuple(hostnames)


async def _resolve_trusted_hostname(hostname: str) -> frozenset[_IPAddress]:
    now = time.monotonic()
    cached = _resolved_trusted_hostnames.get(hostname)
    if cached is not None and now - cached[0] < _TRUSTED_HOSTNAME_TTL_SECONDS:
        return cached[1]
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError, ValueError):
        infos = []
    resolved = frozenset(address for info in infos if (address := _parse_ip(info[4][0])) is not None)
    _resolved_trusted_hostnames[hostname] = (now, resolved)
    return resolved


async def _is_trusted_proxy(address: _IPAddress) -> bool:
    networks, hostnames = _trusted_proxy_rules(CONTROL_PLANE_TRUSTED_PROXIES)
    if any(address in network for network in networks):
        return True
    for hostname in hostnames:
        if address in await _resolve_trusted_hostname(hostname):
            return True
    return False


async def _client_ip(request: web.Request) -> str:
    """Return the address whose buckets this request spends."""
    peer = _parse_ip(request.remote)
    if peer is None:
        return str(request.remote or "unknown")
    forwarded = ",".join(request.headers.getall("X-Forwarded-For", ()))
    hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
    if not hops or not await _is_trusted_proxy(peer):
        return str(peer)
    client = peer
    for hop in reversed(hops):
        address = _parse_ip(hop)
        if address is None:
            # Unparseable hop: stop at the last address a trusted hop vouched for.
            break
        client = address
        if not await _is_trusted_proxy(address):
            break
    return str(client)


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

    ip = await _client_ip(request)

    # Dedicated sensitive-endpoint limiter runs FIRST so auth spam does not
    # eat the user's general per-IP quota for the rest of the dashboard.
    endpoint_limiter = _get_endpoint_limiter(request.path, ip)
    if endpoint_limiter is not None:
        if not endpoint_limiter.has_capacity():
            emit_security(
                "security.control_plane_endpoint_rate_limited",
                ip=ip,
                path=request.path,
            )
            log.warning("endpoint_rate_limit_exceeded", ip=ip, path=request.path)
            return _too_many_requests()
        await endpoint_limiter.acquire()

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
    _endpoint_limiters.clear()
    _resolved_trusted_hostnames.clear()
