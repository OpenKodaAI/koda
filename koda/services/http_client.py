"""HTTP client with SSRF protection for search, fetch, and requests."""

import ipaddress
import re
import socket
from dataclasses import dataclass
from typing import cast
from urllib.parse import quote_plus, urljoin, urlparse

import aiohttp

from koda.logging_config import get_logger

log = get_logger(__name__)

_SSRF_BLOCKED_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

_MAX_RESPONSE_SIZE = 500_000  # 500KB text limit
_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)
_USER_AGENT = "Koda/1.0"


@dataclass(slots=True)
class UrlMetadata:
    """Safe metadata for a public URL after redirect resolution."""

    final_url: str
    content_type: str
    content_length: int | None
    status: int


def _is_private_ip(ip_str: str) -> bool:
    """Check if an IP address is in a private/reserved range."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # Block unparseable addresses
    return any(addr in network for network in _SSRF_BLOCKED_RANGES)


def _check_url_safety(url: str) -> str | None:
    """Validate URL for SSRF. Returns error message or None if safe."""
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return "Only http and https URLs are allowed."

    hostname = parsed.hostname
    if not hostname:
        return "Invalid URL: no hostname."

    # Resolve hostname to check IP
    try:
        infos = socket.getaddrinfo(hostname, None)
        for info in infos:
            ip_str = str(info[4][0])
            if _is_private_ip(ip_str):
                log.warning("ssrf_blocked", url=url, ip=ip_str)
                return "Blocked: URL resolves to a private/reserved IP address."
    except socket.gaierror:
        return f"Could not resolve hostname: {hostname}"

    return None


async def fetch_url(url: str, *, max_size: int = _MAX_RESPONSE_SIZE) -> str:
    """Fetch a URL and return its text content.

    Returns the response text or an error message prefixed with 'Error:'.
    """
    safety_error = _check_url_safety(url)
    if safety_error:
        return f"Error: {safety_error}"

    try:
        async with aiohttp.ClientSession(timeout=_REQUEST_TIMEOUT) as session:
            resp = await _safe_request(session, "GET", url)
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


async def inspect_url(url: str) -> UrlMetadata | str:
    """Resolve redirects safely and return basic metadata without downloading the full body."""
    safety_error = _check_url_safety(url)
    if safety_error:
        return f"Error: {safety_error}"

    try:
        async with aiohttp.ClientSession(timeout=_REQUEST_TIMEOUT) as session:
            resp = await _safe_request(session, "GET", url)
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


async def download_url_bytes(url: str, *, max_size: int) -> bytes | str:
    """Download a public URL as bytes with SSRF-safe redirect handling and explicit size caps."""
    safety_error = _check_url_safety(url)
    if safety_error:
        return f"Error: {safety_error}"

    try:
        async with aiohttp.ClientSession(timeout=_REQUEST_TIMEOUT) as session:
            resp = await _safe_request(session, "GET", url)
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
) -> str:
    """Make an HTTP request and return status + response body."""
    safety_error = _check_url_safety(url)
    if safety_error:
        return f"Error: {safety_error}"

    method = method.upper()
    if method not in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
        return f"Error: Unsupported HTTP method: {method}"

    try:
        async with aiohttp.ClientSession(timeout=_REQUEST_TIMEOUT) as session:
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
) -> aiohttp.ClientResponse | str:
    request_headers = {"User-Agent": _USER_AGENT}
    if headers:
        request_headers.update(headers)

    current_url = url
    response: aiohttp.ClientResponse | None = None
    for _ in range(max_redirects + 1):
        safety_error = _check_url_safety(current_url)
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
        async with (
            aiohttp.ClientSession(timeout=_REQUEST_TIMEOUT) as session,
            session.get(url, headers={"User-Agent": _USER_AGENT}) as resp,
        ):
            if resp.status >= 400:
                return f"Error: Search returned HTTP {resp.status}"
            html = await resp.text(encoding="utf-8", errors="replace")
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
