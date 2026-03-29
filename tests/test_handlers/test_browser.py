"""Tests for browser command handlers."""

from unittest.mock import AsyncMock, patch

import pytest

from koda.handlers.browser import cmd_browse, cmd_click, cmd_js, cmd_screenshot, cmd_type


@pytest.mark.asyncio
async def test_browse_disabled(mock_update, mock_context):
    mock_context.args = ["https://example.com"]
    with patch("koda.handlers.browser.BROWSER_FEATURES_ENABLED", False):
        await cmd_browse(mock_update, mock_context)
    assert "disabled" in mock_update.message.reply_text.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_browse_no_args(mock_update, mock_context):
    mock_context.args = []
    with (
        patch("koda.handlers.browser.BROWSER_FEATURES_ENABLED", True),
        patch("koda.handlers.browser.browser_manager") as mock_bm,
    ):
        mock_bm.ensure_started = AsyncMock(return_value=True)
        await cmd_browse(mock_update, mock_context)
    assert "Usage" in mock_update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_browse_navigates(mock_update, mock_context):
    mock_context.args = ["https://example.com"]
    with (
        patch("koda.handlers.browser.BROWSER_FEATURES_ENABLED", True),
        patch("koda.handlers.browser.browser_manager") as mock_bm,
    ):
        mock_bm.ensure_started = AsyncMock(return_value=True)
        mock_bm.navigate = AsyncMock(return_value="Navigated to: Example")
        await cmd_browse(mock_update, mock_context)
        mock_bm.navigate.assert_called_once_with(111, "https://example.com")


@pytest.mark.asyncio
async def test_click_no_args(mock_update, mock_context):
    mock_context.args = []
    with (
        patch("koda.handlers.browser.BROWSER_FEATURES_ENABLED", True),
        patch("koda.handlers.browser.browser_manager") as mock_bm,
    ):
        mock_bm.ensure_started = AsyncMock(return_value=True)
        await cmd_click(mock_update, mock_context)
    assert "Usage" in mock_update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_type_no_args(mock_update, mock_context):
    mock_context.args = []
    with (
        patch("koda.handlers.browser.BROWSER_FEATURES_ENABLED", True),
        patch("koda.handlers.browser.browser_manager") as mock_bm,
    ):
        mock_bm.ensure_started = AsyncMock(return_value=True)
        await cmd_type(mock_update, mock_context)
    assert "Usage" in mock_update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_screenshot_sends_photo(mock_update, mock_context):
    mock_context.args = []
    with (
        patch("koda.handlers.browser.BROWSER_FEATURES_ENABLED", True),
        patch("koda.handlers.browser.browser_manager") as mock_bm,
    ):
        mock_bm.ensure_started = AsyncMock(return_value=True)
        mock_bm.screenshot = AsyncMock(return_value=b"\x89PNG\r\n")
        mock_update.message.reply_photo = AsyncMock()
        await cmd_screenshot(mock_update, mock_context)
        mock_update.message.reply_photo.assert_called_once()


@pytest.mark.asyncio
async def test_js_no_args(mock_update, mock_context):
    mock_context.args = []
    with (
        patch("koda.handlers.browser.BROWSER_FEATURES_ENABLED", True),
        patch("koda.handlers.browser.browser_manager") as mock_bm,
    ):
        mock_bm.ensure_started = AsyncMock(return_value=True)
        await cmd_js(mock_update, mock_context)
    assert "Usage" in mock_update.message.reply_text.call_args[0][0]
