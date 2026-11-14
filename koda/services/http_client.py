"""HTTP client with SSRF protection for search, fetch, and requests."""

import asyncio
import errno
import ipaddress
import os
import re
import socket
from dataclasses import dataclass
from typing import cast
from urllib.parse import quote_plus, urljoin

import aiohttp
from aiohttp.abc import AbstractResolver, ResolveResult
from aiohttp.helpers import is_ip_address
from aiohttp.resolver import ThreadedResolver
from yarl import URL

from koda.logging_config import get_logger

log = get_logger(__name__)

# RFC 6598 carrier-grade NAT space: not public, yet ``is_private`` is False for it.
_SHARED_ADDRESS_SPACE = ipaddress.ip_network("100.64.0.0/10")
# RFC 6052 NAT64 well-known prefix: DNS64 synthesizes these for IPv4-only hosts.
_NAT64_PREFIX = ipaddress.ip_network("64:ff9b::/96")
_SSRF_BLOCKED_MESSAGE = "Blocked: URL resolves to a private/reserved IP address."

_MAX_RESPONSE_SIZE = 500_000  # 500KB text limit
_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)
_USER_AGENT = "Koda/1.0"


class _PublicOnlyResolver(AbstractResolver):
    """aiohttp resolver that refuses hosts resolving to non-public addresses.

    aiohttp connects to exactly the addresses a resolver returns, so checking
    them here pins every connection to validated IPs: a DNS answer that changes
    between :func:`_check_url_safety` and connect (DNS rebinding) cannot reach a
    private destination.  aiohttp skips the resolver for IP-literal hosts; those
    cannot change and are covered by :func:`_check_url_safety`, which reads the
    host from the URL exactly as aiohttp does (``yarl.URL(url).raw_host``).
    """

    def __init__(self) -> None:
        self._resolver = ThreadedResolver()

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        results = await self._resolver.resolve(host, port, family)
        for result in results:
            if _is_private_ip(result["host"]):
                log.warning("ssrf_blocked", host=host, ip=result["host"], stage="connect")
                raise OSError(errno.EACCES, _SSRF_BLOCKED_MESSAGE)
        return results

    async def close(self) -> None:
        await self._resolver.close()


def public_only_connector() -> aiohttp.TCPConnector:
    """Return a connector that refuses non-public DNS answers at connect time.

    For callers that open their own :class:`aiohttp.ClientSession` after
    :func:`_check_url_safety` passed.  Resolvers never see IP literals, so such
    callers must still run that check and must not follow redirects unchecked
    (pass ``allow_redirects=False``).
    """
    return aiohttp.TCPConnector(resolver=_PublicOnlyResolver())


class _SessionHolder:
    """Lazily creates and reuses a single :class:`aiohttp.ClientSession` with connection pooling.

    Unless ``allow_private`` is set, the session resolves hosts through
    :class:`_PublicOnlyResolver`.  Guarded and private-network sessions never
    share a connector, so they never share its DNS cache either.

    The double-checked locking pattern is safe here because the code runs on a
    single-threaded asyncio event loop — no preemptive interleaving between the
    outer check and the lock acquisition.  Do **not** use from multiple OS threads.
    """

    def __init__(self, *, allow_private: bool = False) -> None:
        self._allow_private = allow_private
        self._session: aiohttp.ClientSession | None = None
        self._lock = asyncio.Lock()

    async def get(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            async with self._lock:
                if self._session is None or self._session.closed:
                    pool_limit = max(1, int(os.environ.get("HTTP_POOL_LIMIT", "20") or "20"))
                    resolver = None if self._allow_private else _PublicOnlyResolver()
                    self._session = aiohttp.ClientSession(
                        timeout=_REQUEST_TIMEOUT,
                        connector=aiohttp.TCPConnector(limit=pool_limit, ttl_dns_cache=300, resolver=resolver),
                    )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None


_holder = _SessionHolder()
_private_holder = _SessionHolder(allow_private=True)


async def _get_session(*, allow_private: bool = False) -> aiohttp.ClientSession:
    """Return the shared guarded session, or the private-network one when explicitly allowed."""
    return await (_private_holder if allow_private else _holder).get()


async def close_session() -> None:
    """Close the shared HTTP sessions.  Call during graceful shutdown."""
    await _holder.close()
    await _private_holder.close()


@dataclass(slots=True)
class UrlMetadata:
    """Safe metadata for a public URL after redirect resolution."""

    final_url: str
    content_type: str
    content_length: int | None
    status: int


def _is_private_ip(ip_str: str) -> bool:
    """Return True unless *ip_str* is a public unicast address.

    IPv4-mapped (``::ffff:127.0.0.1``) and NAT64 (``64:ff9b::7f00:1``) IPv6
    addresses are judged by the IPv4 address they embed, because that is where
    the kernel or the NAT64 gateway delivers them.  Unparseable input is blocked.
    """
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # Block unparseable addresses
    if isinstance(addr, ipaddress.IPv6Address):
        if addr.ipv4_mapped is not None:
            addr = addr.ipv4_mapped
        elif addr in _NAT64_PREFIX:
            addr = ipaddress.IPv4Address(int(addr) & 0xFFFFFFFF)
        elif addr.is_site_local:
            return True
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_unspecified
        or addr.is_multicast
        or addr in _SHARED_ADDRESS_SPACE
    )


def _check_url_safety(url: str, *, allow_private: bool = False) -> str | None:
    """Validate URL for SSRF. Returns error message or None if safe.

    The host is the one aiohttp connects to: :class:`yarl.URL` parses the URL
    and IDNA-encodes the host with UTS-46.  ``urlparse`` plus the stdlib IDNA
    2003 codec can read a different host from the same URL (UTS-46 maps some
    code points to ASCII digits or to nothing), so checking that host could
    pass a name that aiohttp then treats as a private IP literal.
    """
    try:
        parsed = URL(url)
    except ValueError:  # includes UnicodeError from IDNA encoding
        return "Invalid URL."

    if parsed.scheme not in ("http", "https"):
        return "Only http and https URLs are allowed."

    hostname = parsed.raw_host
    if not hostname:
        return "Invalid URL: no hostname."

    # aiohttp connects to anything it considers an IP literal without asking a
    # resolver, so judge the literal itself; one ipaddress cannot parse is blocked.
    if not allow_private and is_ip_address(hostname) and _is_private_ip(hostname):
        log.warning("ssrf_blocked", url=url, ip=hostname)
        return _SSRF_BLOCKED_MESSAGE

    # Resolve hostname to check IP
    try:
        infos = socket.getaddrinfo(hostname, None)
        if allow_private:
            private_only = True
            for info in infos:
                ip_str = str(info[4][0])
                if not _is_private_ip(ip_str):
                    private_only = False
                    break
            if private_only:
                return None
        else:
            for info in infos:
                ip_str = str(info[4][0])
                if _is_private_ip(ip_str):
                    log.warning("ssrf_blocked", url=url, ip=ip_str)
                    return _SSRF_BLOCKED_MESSAGE
    except (socket.gaierror, UnicodeError):
        return f"Could not resolve hostname: {hostname}"

    return None


async def _check_url_safety_off_loop(url: str, *, allow_private: bool = False) -> str | None:
    """Run :func:`_check_url_safety` in a worker thread: its DNS lookup blocks."""
    return await asyncio.to_thread(_check_url_safety, url, allow_private=allow_private)


async def fetch_url(url: str, *, max_size: int = _MAX_RESPONSE_SIZE, allow_private: bool = False) -> str:
    """Fetch a URL and return its text content.

    Returns the response text or an error message prefixed with 'Error:'.
    """
    safety_error = await _check_url_safety_off_loop(url, allow_private=allow_private)
    if safety_error:
        return f"Error: {safety_error}"

    try:
        session = await _get_session(allow_private=allow_private)
        resp = await _safe_request(session, "GET", url, allow_private=allow_private)
        if isinstance(resp, str):
            return f"Error: {resp}"
        try:
            if resp.status >= 400:
                return f"Error: HTTP {resp.status}"
            text = cast(str, await resp.text(encoding="utf-8", errors="replace"))
            if len(text) > max_size:
                text = text[:max_size] + "\n... (truncated)"
            return text
        finally:
            resp.release()
    except TimeoutError:
        return "Error: Request timed out."
    except Exception as e:
        return f"Error: {e}"


async def inspect_url(url: str, *, allow_private: bool = False) -> UrlMetadata | str:
    """Resolve redirects safely and return basic metadata without downloading the full body."""
    safety_error = await _check_url_safety_off_loop(url, allow_private=allow_private)
    if safety_error:
        return f"Error: {safety_error}"

    try:
        session = await _get_session(allow_private=allow_private)
        resp = await _safe_request(session, "GET", url, allow_private=allow_private)
        if isinstance(resp, str):
            return f"Error: {resp}"
        try:
            final_url = str(resp.url)
            content_type = resp.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            content_length_raw = resp.headers.get("Content-Length")
            try:
                content_length = int(content_length_raw) if content_length_raw else None
            except ValueError:
                content_length = None
            return UrlMetadata(
                final_url=final_url,
                content_type=content_type,
                content_length=content_length,
                status=resp.status,
            )
        finally:
            resp.release()
    except TimeoutError:
        return "Error: Request timed out."
    except Exception as e:
        return f"Error: {e}"


async def download_url_bytes(url: str, *, max_size: int, allow_private: bool = False) -> bytes | str:
    """Download a public URL as bytes with SSRF-safe redirect handling and explicit size caps."""
    safety_error = await _check_url_safety_off_loop(url, allow_private=allow_private)
    if safety_error:
        return f"Error: {safety_error}"

    try:
        session = await _get_session(allow_private=allow_private)
        resp = await _safe_request(session, "GET", url, allow_private=allow_private)
        if isinstance(resp, str):
            return f"Error: {resp}"
        try:
            if resp.status >= 400:
                return f"Error: HTTP {resp.status}"

            content_length_raw = resp.headers.get("Content-Length")
            try:
                content_length = int(content_length_raw) if content_length_raw else None
            except ValueError:
                content_length = None
            if content_length is not None and content_length > max_size:
                return f"Error: Response too large ({content_length} bytes > {max_size} bytes)."

            chunks: list[bytes] = []
            total = 0
            async for chunk in resp.content.iter_chunked(64 * 1024):
                total += len(chunk)
                if total > max_size:
                    return f"Error: Response exceeded size limit ({max_size} bytes)."
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            resp.release()
    except TimeoutError:
        return "Error: Request timed out."
    except Exception as e:
        return f"Error: {e}"


async def make_http_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: str | None = None,
    allow_private: bool = False,
) -> str:
    """Make an HTTP request and return status + response body."""
    safety_error = await _check_url_safety_off_loop(url, allow_private=allow_private)
    if safety_error:
        return f"Error: {safety_error}"

    method = method.upper()
    if method not in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
        return f"Error: Unsupported HTTP method: {method}"

    try:
        session = await _get_session(allow_private=allow_private)
        req_headers = {"User-Agent": _USER_AGENT}
        if headers:
            req_headers.update(headers)

        async with session.request(method, url, headers=req_headers, data=body, allow_redirects=False) as resp:
            status_line = f"HTTP {resp.status} {resp.reason}"
            resp_headers = "\n".join(f"  {k}: {v}" for k, v in list(resp.headers.items())[:20])

            if method == "HEAD":
                return f"{status_line}\n{resp_headers}"

            text = cast(str, await resp.text(encoding="utf-8", errors="replace"))
            if len(text) > _MAX_RESPONSE_SIZE:
                text = text[:_MAX_RESPONSE_SIZE] + "\n... (truncated)"
            return f"{status_line}\n{resp_headers}\n\n{text}"
    except TimeoutError:
        return "Error: Request timed out."
    except Exception as e:
        return f"Error: {e}"


async def _safe_request(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    max_redirects: int = 10,
    allow_private: bool = False,
) -> aiohttp.ClientResponse | str:
    request_headers = {"User-Agent": _USER_AGENT}
    if headers:
        request_headers.update(headers)

    current_url = url
    response: aiohttp.ClientResponse | None = None
    for _ in range(max_redirects + 1):
        safety_error = await _check_url_safety_off_loop(current_url, allow_private=allow_private)
        if safety_error:
            return safety_error if current_url == url else f"Redirect blocked — {safety_error}"

        response = await session.request(method, current_url, headers=request_headers, allow_redirects=False)
        if response.status not in (301, 302, 303, 307, 308):
            return response

        location = response.headers.get("Location", "")
        response.release()
        if not location:
            return "Redirect missing Location header."
        current_url = urljoin(current_url, location)
    return "Too many redirects."


async def search_web(query: str) -> str:
    """Search the web using DuckDuckGo HTML and return results."""
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"

    try:
        session = await _get_session()
        resp = await _safe_request(session, "GET", url)
        if isinstance(resp, str):
            return f"Error: {resp}"
        try:
            if resp.status >= 400:
                return f"Error: Search returned HTTP {resp.status}"
            html = await resp.text(encoding="utf-8", errors="replace")
        finally:
            resp.release()
    except TimeoutError:
        return "Error: Search timed out."
    except Exception as e:
        return f"Error: {e}"

    # Parse results from DuckDuckGo HTML
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        results = []
        for result in soup.select(".result"):
            title_el = result.select_one(".result__title a")
            snippet_el = result.select_one(".result__snippet")
            if title_el:
                title = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                results.append(f"• {title}\n  {href}\n  {snippet}")
            if len(results) >= 10:
                break

        if not results:
            return "No results found."
        return "\n\n".join(results)
    except ImportError:
        # Fallback: extract links with regex
        links = re.findall(r'class="result__url"[^>]*href="([^"]+)"', html)
        if not links:
            return "No results found (beautifulsoup4 not installed for rich parsing)."
        return "\n".join(links[:10])
