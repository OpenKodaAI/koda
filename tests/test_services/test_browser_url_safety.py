"""Tests for koda.services.browser_manager._check_browser_url_safety.

The URL safety gate is the boundary between an agent and arbitrary network
egress through Playwright. It enforces:

  * data:/about: schemes are always allowed (no network).
  * http(s) with public hostname: respects upstream _check_url_safety.
  * http(s) with private hostname: allowed only when allow_private=True.
  * non-http(s) external schemes (ftp, file, ws, etc.): rejected.
  * Bad / no hostname: rejected with a clear message.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from koda.services.browser_manager import _check_browser_url_safety, _maybe_await

# data: / about: schemes are always allowed


@pytest.mark.parametrize(
    "url",
    [
        "data:text/html,<h1>Hello</h1>",
        "data:image/png;base64,iVBORw0KGgo=",
        "about:blank",
        "about:srcdoc",
    ],
)
def test_data_about_schemes_always_allowed(url: str) -> None:
    assert _check_browser_url_safety(url, allow_private=False) is None
    assert _check_browser_url_safety(url, allow_private=True) is None


# Non-http(s) schemes are rejected when allow_private (with explicit reason)


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/file",
        "file:///etc/passwd",
        "ws://example.com/socket",
        "wss://example.com/socket",
        "javascript:alert(1)",
        "ssh://server.example.com",
    ],
)
def test_non_http_schemes_rejected_in_private_mode(url: str) -> None:
    err = _check_browser_url_safety(url, allow_private=True)
    assert err is not None
    assert "http, https, data, and about" in err.lower()


# Missing hostname rejected in private mode


def test_missing_hostname_rejected_in_private_mode() -> None:
    err = _check_browser_url_safety("https://", allow_private=True)
    assert err is not None
    assert "hostname" in err.lower()


# Public URLs delegate to the upstream _check_url_safety


def test_public_url_delegates_to_check_url_safety_when_not_allow_private() -> None:
    with patch("koda.services.browser_manager._check_url_safety") as upstream:
        upstream.return_value = None
        out = _check_browser_url_safety("https://example.com", allow_private=False)
        assert out is None
        upstream.assert_called_once_with("https://example.com")


def test_public_url_returns_upstream_error() -> None:
    with patch("koda.services.browser_manager._check_url_safety") as upstream:
        upstream.return_value = "blocked: SSRF"
        out = _check_browser_url_safety("http://malicious.example", allow_private=False)
        assert out == "blocked: SSRF"


# ---------------------------------------------------------------------------
# allow_private branch: private-only resolution returns None; mixed resolution
# delegates to upstream
# ---------------------------------------------------------------------------


def test_private_hostname_allowed_when_allow_private_true() -> None:
    """When the hostname resolves to ONLY private IPs, allow_private=True
    bypasses upstream and returns None."""
    with patch("koda.services.browser_manager.socket.getaddrinfo") as getaddr:
        # Return a single private 10.0.0.x address.
        getaddr.return_value = [(0, 0, 0, "", ("10.0.0.5", 0))]
        out = _check_browser_url_safety("http://internal.svc/api", allow_private=True)
    assert out is None


def test_loopback_is_treated_as_private() -> None:
    with patch("koda.services.browser_manager.socket.getaddrinfo") as getaddr:
        getaddr.return_value = [(0, 0, 0, "", ("127.0.0.1", 0))]
        out = _check_browser_url_safety("http://localhost:8080/", allow_private=True)
    assert out is None


def test_link_local_is_treated_as_private() -> None:
    with patch("koda.services.browser_manager.socket.getaddrinfo") as getaddr:
        getaddr.return_value = [(0, 0, 0, "", ("169.254.169.254", 0))]
        out = _check_browser_url_safety("http://169.254.169.254/latest/", allow_private=True)
    assert out is None


def test_mixed_private_public_resolution_delegates_to_upstream() -> None:
    """If at least one resolved IP is public, the URL is treated as public —
    and the upstream safety check decides."""
    with (
        patch("koda.services.browser_manager.socket.getaddrinfo") as getaddr,
        patch("koda.services.browser_manager._check_url_safety") as upstream,
    ):
        getaddr.return_value = [
            (0, 0, 0, "", ("10.0.0.5", 0)),
            (0, 0, 0, "", ("8.8.8.8", 0)),
        ]
        upstream.return_value = None
        out = _check_browser_url_safety("http://hybrid.example/", allow_private=True)
        assert out is None
        upstream.assert_called_once_with("http://hybrid.example/")


def test_dns_resolution_failure_returns_clear_error() -> None:
    import socket as _socket

    with patch("koda.services.browser_manager.socket.getaddrinfo") as getaddr:
        getaddr.side_effect = _socket.gaierror("nodename nor servname provided")
        out = _check_browser_url_safety("http://nonexistent.invalid/", allow_private=True)
    assert out is not None
    assert "could not resolve" in out.lower()
    assert "nonexistent.invalid" in out


# _maybe_await — pure awaitable detection helper


async def test_maybe_await_does_nothing_for_non_awaitable() -> None:
    # Returns None for a plain int — must not raise.
    await _maybe_await(42)
    await _maybe_await("string")
    await _maybe_await(None)


async def test_maybe_await_awaits_coroutine() -> None:
    completed = False

    async def coro() -> None:
        nonlocal completed
        completed = True

    await _maybe_await(coro())
    assert completed is True


async def test_maybe_await_awaits_future() -> None:
    import asyncio

    fut: asyncio.Future[int] = asyncio.get_event_loop().create_future()
    fut.set_result(7)
    await _maybe_await(fut)
    # Future is consumed without raising.
    assert fut.done()
