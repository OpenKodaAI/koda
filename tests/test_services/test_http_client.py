"""Tests for HTTP client service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.services.http_client import (
    _check_url_safety,
    _is_private_ip,
    _SessionHolder,
    close_session,
    download_url_bytes,
    fetch_url,
    inspect_url,
    make_http_request,
)


def test_private_ip_detection():
    assert _is_private_ip("127.0.0.1") is True
    assert _is_private_ip("10.0.0.1") is True
    assert _is_private_ip("172.16.0.1") is True
    assert _is_private_ip("192.168.1.1") is True
    assert _is_private_ip("169.254.1.1") is True
    assert _is_private_ip("::1") is True
    # Public IPs
    assert _is_private_ip("8.8.8.8") is False
    assert _is_private_ip("1.1.1.1") is False
    assert _is_private_ip("93.184.216.34") is False


def test_url_safety_blocks_non_http():
    result = _check_url_safety("ftp://example.com")
    assert result is not None
    assert "http" in result.lower()


def test_url_safety_blocks_no_hostname():
    result = _check_url_safety("http://")
    assert result is not None


def test_url_safety_blocks_private_ip():
    with patch("koda.services.http_client.socket.getaddrinfo") as mock_gai:
        mock_gai.return_value = [(None, None, None, None, ("127.0.0.1", 80))]
        result = _check_url_safety("http://localhost")
        assert result is not None
        assert "private" in result.lower()


def test_url_safety_allows_public():
    with patch("koda.services.http_client.socket.getaddrinfo") as mock_gai:
        mock_gai.return_value = [(None, None, None, None, ("93.184.216.34", 80))]
        result = _check_url_safety("https://example.com")
        assert result is None  # safe


def test_url_safety_allows_private_when_explicit():
    with patch("koda.services.http_client.socket.getaddrinfo") as mock_gai:
        mock_gai.return_value = [(None, None, None, None, ("127.0.0.1", 80))]
        result = _check_url_safety("http://localhost", allow_private=True)
        assert result is None


@pytest.mark.asyncio
async def test_fetch_url_ssrf_blocked():
    with patch("koda.services.http_client.socket.getaddrinfo") as mock_gai:
        mock_gai.return_value = [(None, None, None, None, ("192.168.1.1", 80))]
        result = await fetch_url("http://internal-service")
        assert "Error:" in result
        assert "private" in result.lower()


@pytest.mark.asyncio
async def test_fetch_url_success():
    with patch("koda.services.http_client._check_url_safety", return_value=None):
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.url = "https://example.com"
        mock_resp.headers = {"Content-Type": "text/plain", "Content-Length": "11"}
        mock_resp.text = AsyncMock(return_value="Hello World")
        mock_resp.release = MagicMock()

        mock_session = AsyncMock()
        mock_session.request = AsyncMock(return_value=mock_resp)

        with patch("koda.services.http_client._get_session", return_value=mock_session):
            result = await fetch_url("https://example.com")
            assert result == "Hello World"


@pytest.mark.asyncio
async def test_fetch_url_allows_private_when_explicit():
    with patch("koda.services.http_client.socket.getaddrinfo") as mock_gai:
        mock_gai.return_value = [(None, None, None, None, ("127.0.0.1", 80))]
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.url = "http://localhost"
        mock_resp.headers = {"Content-Type": "text/plain", "Content-Length": "11"}
        mock_resp.text = AsyncMock(return_value="Hello World")
        mock_resp.release = MagicMock()

        mock_session = AsyncMock()
        mock_session.request = AsyncMock(return_value=mock_resp)

        with patch("koda.services.http_client._get_session", return_value=mock_session):
            result = await fetch_url("http://localhost", allow_private=True)

    assert result == "Hello World"


@pytest.mark.asyncio
async def test_inspect_url_returns_metadata():
    with patch("koda.services.http_client._check_url_safety", return_value=None):
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.url = "https://example.com/file.mp4"
        mock_resp.headers = {"Content-Type": "video/mp4; charset=binary", "Content-Length": "2048"}
        mock_resp.release = MagicMock()

        mock_session = AsyncMock()
        mock_session.request = AsyncMock(return_value=mock_resp)

        with patch("koda.services.http_client._get_session", return_value=mock_session):
            result = await inspect_url("https://example.com/file.mp4")

    assert result.final_url == "https://example.com/file.mp4"
    assert result.content_type == "video/mp4"
    assert result.content_length == 2048


@pytest.mark.asyncio
async def test_download_url_bytes_enforces_size_limit():
    with patch("koda.services.http_client._check_url_safety", return_value=None):
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.url = "https://example.com/big.bin"
        mock_resp.headers = {"Content-Length": "2048"}
        mock_resp.release = MagicMock()

        mock_session = AsyncMock()
        mock_session.request = AsyncMock(return_value=mock_resp)

        with patch("koda.services.http_client._get_session", return_value=mock_session):
            result = await download_url_bytes("https://example.com/big.bin", max_size=1024)

    assert isinstance(result, str)
    assert "too large" in result.lower()


@pytest.mark.asyncio
async def test_make_http_request_allows_private_when_explicit():
    with patch("koda.services.http_client.socket.getaddrinfo") as mock_gai:
        mock_gai.return_value = [(None, None, None, None, ("127.0.0.1", 80))]
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.reason = "OK"
        mock_resp.headers = {"Content-Type": "text/plain"}
        mock_resp.text = AsyncMock(return_value="OK")
        mock_resp.__aenter__.return_value = mock_resp
        mock_resp.__aexit__.return_value = None

        mock_session = AsyncMock()
        mock_session.request = MagicMock(return_value=mock_resp)

        with patch("koda.services.http_client._get_session", return_value=mock_session):
            result = await make_http_request("GET", "http://localhost", allow_private=True)

    assert "HTTP 200 OK" in result


# --- Session reuse and lifecycle tests ---


@pytest.mark.asyncio
async def test_session_holder_reuses_session():
    """Verify that _SessionHolder.get() returns the same session on repeated calls."""
    holder = _SessionHolder()
    mock_session = MagicMock()
    mock_session.closed = False

    with patch("koda.services.http_client.aiohttp.ClientSession", return_value=mock_session) as cls_mock:
        s1 = await holder.get()
        s2 = await holder.get()

    assert s1 is s2
    # ClientSession constructor called exactly once
    cls_mock.assert_called_once()


@pytest.mark.asyncio
async def test_session_holder_recreates_after_close():
    """After close(), the next get() should create a fresh session."""
    holder = _SessionHolder()

    first_session = MagicMock()
    first_session.closed = False
    second_session = MagicMock()
    second_session.closed = False

    with patch(
        "koda.services.http_client.aiohttp.ClientSession",
        side_effect=[first_session, second_session],
    ):
        s1 = await holder.get()
        assert s1 is first_session

        # Simulate close
        first_session.closed = False
        first_session.close = AsyncMock()
        await holder.close()
        assert first_session.close.called

        # Next get should create a new session
        s2 = await holder.get()
        assert s2 is second_session
        assert s2 is not s1


@pytest.mark.asyncio
async def test_close_session_is_idempotent():
    """Calling close_session() when no session exists should not raise."""
    holder = _SessionHolder()
    # No session created yet
    await holder.close()  # should not raise


@pytest.mark.asyncio
async def test_module_close_session():
    """The module-level close_session() delegates to _holder.close()."""
    with patch("koda.services.http_client._holder") as mock_holder:
        mock_holder.close = AsyncMock()
        await close_session()
        mock_holder.close.assert_awaited_once()


# --- SSRF guard: address classification, connect-time pinning, redirects ---


@pytest.mark.parametrize(
    "ip",
    [
        "0.0.0.0",  # "this host": Linux routes it to local listeners
        "0.1.2.3",
        "::",
        "100.64.0.1",  # RFC 6598 shared address space (carrier-grade NAT)
        "100.127.255.254",
        "::ffff:127.0.0.1",  # IPv4-mapped IPv6 loopback
        "::ffff:10.0.0.1",
        "::ffff:169.254.169.254",  # IPv4-mapped cloud metadata endpoint
        "::ffff:0.0.0.0",
        "224.0.0.1",
        "ff02::1",
        "240.0.0.1",
        "255.255.255.255",
        "198.18.0.1",
        "fec0::1",
        "fe80::1%eth0",
        "64:ff9b::7f00:1",  # NAT64 of 127.0.0.1
        "64:ff9b::a00:1",  # NAT64 of 10.0.0.1
        "not-an-ip",
    ],
)
def test_private_ip_detection_blocks_non_public_ranges(ip):
    assert _is_private_ip(ip) is True


@pytest.mark.parametrize("ip", ["8.8.8.8", "::ffff:8.8.8.8", "64:ff9b::808:808", "2001:4860:4860::8888", "100.128.0.1"])
def test_private_ip_detection_allows_public_unicast(ip):
    assert _is_private_ip(ip) is False


@pytest.mark.parametrize(
    "url",
    [
        "http://0.0.0.0:8080/",
        "http://[::]:8080/",
        "http://[::ffff:127.0.0.1]:8080/",
        "http://[::ffff:a9fe:a9fe]/latest/meta-data/",
        "http://100.64.0.1/",
    ],
)
def test_url_safety_blocks_unspecified_shared_and_mapped_literals(url):
    result = _check_url_safety(url)
    assert result is not None
    assert "private" in result.lower()


async def _start_local_server():
    from aiohttp import web

    async def secret(_request):
        return web.Response(text="internal-secret")

    app = web.Application()
    app.router.add_get("/secret", secret)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]
    return runner, port


@pytest.mark.asyncio
async def test_fetch_url_cannot_reach_local_service_via_unspecified_address():
    runner, port = await _start_local_server()
    holder = _SessionHolder()
    try:
        with patch("koda.services.http_client._holder", holder):
            result = await fetch_url(f"http://0.0.0.0:{port}/secret")
    finally:
        await holder.close()
        await runner.cleanup()

    assert "internal-secret" not in result
    assert result.startswith("Error:")


@pytest.mark.asyncio
async def test_fetch_url_pins_connection_against_dns_rebinding():
    """Every safety pre-check sees a public IP; the lookup used to connect rebinds to loopback.

    ``_check_url_safety`` resolves with no port while aiohttp resolves with the
    request port, which lets the fake DNS answer differently for the connection
    itself -- exactly what a TTL-0 rebinding server does between check and use.
    """
    import socket as socket_module

    runner, port = await _start_local_server()
    real_getaddrinfo = socket_module.getaddrinfo
    lookups: list[str] = []

    def rebinding_getaddrinfo(host, service, *args, **kwargs):
        if host != "rebind.koda.test":
            return real_getaddrinfo(host, service, *args, **kwargs)
        ip = "93.184.216.34" if service is None else "127.0.0.1"
        lookups.append(ip)
        return [(socket_module.AF_INET, socket_module.SOCK_STREAM, 6, "", (ip, service or 0))]

    holder = _SessionHolder()
    try:
        with (
            patch("koda.services.http_client._holder", holder),
            patch.object(socket_module, "getaddrinfo", rebinding_getaddrinfo),
        ):
            result = await fetch_url(f"http://rebind.koda.test:{port}/secret")
    finally:
        await holder.close()
        await runner.cleanup()

    assert "93.184.216.34" in lookups
    assert lookups[-1] == "127.0.0.1"  # the connect-time answer was consulted
    assert "internal-secret" not in result
    assert result.startswith("Error:")
    assert "private/reserved" in result


def _public_example_getaddrinfo(real_getaddrinfo):
    def fake(host, service, *args, **kwargs):
        if host == "example.com":
            return [(2, 1, 6, "", ("93.184.216.34", service or 0))]
        return real_getaddrinfo(host, service, *args, **kwargs)

    return fake


@pytest.mark.asyncio
async def test_fetch_url_blocks_redirect_to_unspecified_address():
    import socket as socket_module

    redirect = MagicMock()
    redirect.status = 302
    redirect.headers = {"Location": "http://0.0.0.0:2375/containers/json"}
    redirect.release = MagicMock()

    mock_session = AsyncMock()
    mock_session.request = AsyncMock(return_value=redirect)

    with (
        patch.object(socket_module, "getaddrinfo", _public_example_getaddrinfo(socket_module.getaddrinfo)),
        patch("koda.services.http_client._get_session", return_value=mock_session),
    ):
        result = await fetch_url("https://example.com/")

    assert result.startswith("Error: Redirect blocked")
    assert mock_session.request.await_count == 1


@pytest.mark.asyncio
async def test_search_web_revalidates_redirects():
    redirect = MagicMock()
    redirect.status = 302
    redirect.headers = {"Location": "http://169.254.169.254/latest/meta-data/"}
    redirect.release = MagicMock()

    mock_session = AsyncMock()
    mock_session.request = AsyncMock(return_value=redirect)

    from koda.services.http_client import search_web

    def fake_getaddrinfo(host, *_args, **_kwargs):
        return [(2, 1, 6, "", ("52.0.0.1" if host == "html.duckduckgo.com" else host, 0))]

    with (
        patch("koda.services.http_client.socket.getaddrinfo", side_effect=fake_getaddrinfo),
        patch("koda.services.http_client._get_session", return_value=mock_session),
    ):
        result = await search_web("koda")

    assert result.startswith("Error:")
    assert "private/reserved" in result
    assert mock_session.request.await_count == 1


@pytest.mark.asyncio
async def test_public_only_resolver_rejects_private_answers():
    from koda.services.http_client import _PublicOnlyResolver

    resolver = _PublicOnlyResolver()
    private_answer = [{"hostname": "h", "host": "10.0.0.5", "port": 80, "family": 2, "proto": 6, "flags": 0}]
    with (
        patch.object(resolver._resolver, "resolve", AsyncMock(return_value=private_answer)),
        pytest.raises(OSError, match="private/reserved"),
    ):
        await resolver.resolve("h", 80)

    public_answer = [{"hostname": "h", "host": "93.184.216.34", "port": 80, "family": 2, "proto": 6, "flags": 0}]
    with patch.object(resolver._resolver, "resolve", AsyncMock(return_value=public_answer)):
        assert await resolver.resolve("h", 80) == public_answer
    await resolver.close()


@pytest.mark.asyncio
async def test_private_access_uses_a_separate_unguarded_session():
    """allow_private gets its own session; the guarded one still refuses a private DNS answer.

    The unguarded session connects first, so a shared connector would serve the
    guarded request from its DNS cache and skip the connect-time check.
    """
    import socket as socket_module

    import aiohttp

    from koda.services.http_client import _get_session

    runner, port = await _start_local_server()
    real_getaddrinfo = socket_module.getaddrinfo

    def internal_getaddrinfo(host, service, *args, **kwargs):
        if host == "internal.koda.test":
            return [(socket_module.AF_INET, socket_module.SOCK_STREAM, 6, "", ("127.0.0.1", service or 0))]
        return real_getaddrinfo(host, service, *args, **kwargs)

    url = f"http://internal.koda.test:{port}/secret"
    strict = _SessionHolder()
    permissive = _SessionHolder(allow_private=True)
    try:
        with (
            patch("koda.services.http_client._holder", strict),
            patch("koda.services.http_client._private_holder", permissive),
            patch.object(socket_module, "getaddrinfo", internal_getaddrinfo),
        ):
            guarded = await _get_session()
            unguarded = await _get_session(allow_private=True)
            assert guarded is not unguarded

            async with unguarded.get(url) as resp:
                assert await resp.text() == "internal-secret"
            with pytest.raises(aiohttp.ClientConnectorError, match="private/reserved"):
                async with guarded.get(url):
                    pass
    finally:
        await strict.close()
        await permissive.close()
        await runner.cleanup()


@pytest.mark.asyncio
async def test_url_safety_dns_lookup_runs_off_the_event_loop():
    """The pre-check's getaddrinfo blocks, so it must not run on the event loop thread."""
    import threading

    from koda.services.http_client import search_web

    loop_thread = threading.current_thread()
    lookup_threads: list[threading.Thread] = []

    def fake_getaddrinfo(host, *_args, **_kwargs):
        lookup_threads.append(threading.current_thread())
        return [(2, 1, 6, "", ("93.184.216.34", 0))]

    response = MagicMock()
    response.status = 200
    response.headers = {}
    response.text = AsyncMock(return_value="<html></html>")
    response.release = MagicMock()
    mock_session = AsyncMock()
    mock_session.request = AsyncMock(return_value=response)
    # make_http_request uses ``session.request`` as an async context manager.
    request_context = MagicMock()
    request_context.__aenter__.return_value = response
    direct_session = MagicMock()
    direct_session.request = MagicMock(return_value=request_context)

    with patch("koda.services.http_client.socket.getaddrinfo", side_effect=fake_getaddrinfo):
        with patch("koda.services.http_client._get_session", return_value=mock_session):
            await search_web("koda")
            await fetch_url("https://example.com/")
            await inspect_url("https://example.com/")
            await download_url_bytes("https://example.com/", max_size=10)
        with patch("koda.services.http_client._get_session", return_value=direct_session):
            assert (await make_http_request("GET", "https://example.com/")).startswith("HTTP 200")

    assert len(lookup_threads) >= 5
    assert loop_thread not in lookup_threads
