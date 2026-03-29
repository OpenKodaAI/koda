"""Tests for HTTP client service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.services.http_client import (
    _check_url_safety,
    _is_private_ip,
    download_url_bytes,
    fetch_url,
    inspect_url,
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
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session.request = AsyncMock(return_value=mock_resp)

        with patch("koda.services.http_client.aiohttp.ClientSession", return_value=mock_session):
            result = await fetch_url("https://example.com")
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
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session.request = AsyncMock(return_value=mock_resp)

        with patch("koda.services.http_client.aiohttp.ClientSession", return_value=mock_session):
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
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session.request = AsyncMock(return_value=mock_resp)

        with patch("koda.services.http_client.aiohttp.ClientSession", return_value=mock_session):
            result = await download_url_bytes("https://example.com/big.bin", max_size=1024)

    assert isinstance(result, str)
    assert "too large" in result.lower()
