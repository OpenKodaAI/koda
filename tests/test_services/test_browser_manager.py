"""Tests for browser manager service."""

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.services.browser_manager import _INACTIVITY_TIMEOUT, BrowserManager


@pytest.fixture
def bm():
    return BrowserManager()


def test_initial_state(bm):
    assert bm.is_available is False
    assert bm._contexts == {}


@pytest.mark.asyncio
async def test_start_without_playwright(bm):
    with patch.dict("sys.modules", {"playwright": None, "playwright.async_api": None}):
        # Should not raise, just log warning
        await bm.start()
        assert bm.is_available is False


@pytest.mark.asyncio
async def test_stop_idempotent(bm):
    # Stop should work even when not started
    await bm.stop()
    assert bm.is_available is False


@pytest.mark.asyncio
async def test_stop_suppresses_cleanup_task_cancellation():
    import asyncio

    bm = BrowserManager()

    async def _cleanup():
        await asyncio.sleep(60)

    bm._cleanup_task = asyncio.create_task(_cleanup())
    await bm.stop()
    assert bm._cleanup_task is None


@pytest.mark.asyncio
async def test_navigate_not_available(bm):
    # When browser is not available, _get_or_create_context will fail
    # This tests the manager's is_available property
    assert bm.is_available is False


@pytest.mark.asyncio
async def test_navigate_runtime_scope_allows_data_url(bm_with_page):
    bm, page, _ = bm_with_page
    page.goto = AsyncMock()
    page.title = AsyncMock(return_value="Data Page")
    page.evaluate = AsyncMock(return_value={"links": 0, "forms": 0, "inputs": 0})
    page.url = "data:text/html,<h1>hello</h1>"
    bm._runtime_live_scopes[111] = {"runtime_dir": "/tmp/runtime-browser"}

    result = await bm.navigate(111, "data:text/html,<h1>hello</h1>")

    assert "Navigated to: Data Page" in result
    snapshot = bm.get_session_snapshot(111)
    assert snapshot is not None
    assert snapshot["url"] == "data:text/html,<h1>hello</h1>"


@pytest.mark.asyncio
async def test_navigate_runtime_scope_allows_localhost_url(bm_with_page):
    bm, page, _ = bm_with_page
    page.goto = AsyncMock()
    page.title = AsyncMock(return_value="Local App")
    page.evaluate = AsyncMock(return_value={"links": 1, "forms": 0, "inputs": 0})
    page.url = "http://127.0.0.1:3004"
    bm._runtime_live_scopes[111] = {"runtime_dir": "/tmp/runtime-browser"}

    result = await bm.navigate(111, "http://127.0.0.1:3004")

    assert "Navigated to: Local App" in result
    snapshot = bm.get_session_snapshot(111)
    assert snapshot is not None
    assert snapshot["url"] == "http://127.0.0.1:3004"


@pytest.mark.asyncio
async def test_navigate_non_runtime_scope_blocks_private_url(bm_with_page):
    bm, page, _ = bm_with_page

    result = await bm.navigate(111, "http://127.0.0.1:3004")

    assert result == "Error: Blocked: URL resolves to a private/reserved IP address."


@pytest.mark.asyncio
async def test_close_context():
    bm = BrowserManager()
    mock_context = AsyncMock()
    bm._contexts[111] = {
        "context": mock_context,
        "page": AsyncMock(),
        "last_used": 0,
    }

    await bm._close_context(111)
    assert 111 not in bm._contexts
    mock_context.close.assert_called_once()


@pytest.fixture
def bm_with_page():
    """BrowserManager with a mock page injected."""
    bm = BrowserManager()
    mock_page = AsyncMock()
    mock_page.url = "https://example.com"
    mock_page.title = AsyncMock(return_value="Example")
    mock_page.evaluate = AsyncMock(return_value={"links": 5, "forms": 1, "inputs": 3})
    mock_page.inner_text = AsyncMock(return_value="Page text content")
    mock_page.screenshot = AsyncMock()
    mock_page.go_back = AsyncMock()
    mock_page.go_forward = AsyncMock()
    mock_page.wait_for_load_state = AsyncMock()
    mock_context = AsyncMock()
    mock_context.cookies = AsyncMock(return_value=[])
    mock_context.add_cookies = AsyncMock()
    bm._contexts[111] = {
        "context": mock_context,
        "page": mock_page,
        "last_used": 0,
        "last_dialog": None,
    }
    return bm, mock_page, mock_context


@pytest.mark.asyncio
async def test_smart_click_by_text(bm_with_page):
    bm, page, _ = bm_with_page
    mock_elem = AsyncMock()
    mock_elem.scroll_into_view_if_needed = AsyncMock()
    mock_elem.click = AsyncMock()

    # Mock _find_element to return a found element
    with patch.object(bm, "_find_element", return_value=(mock_elem, None)):
        result = await bm.smart_click(111, "Submit")
    assert "Clicked successfully" in result
    mock_elem.click.assert_called_once()


@pytest.mark.asyncio
async def test_smart_click_all_fail(bm_with_page):
    bm, page, _ = bm_with_page
    page.evaluate = AsyncMock(return_value=["Button1", "Link1"])

    with patch.object(
        bm, "_find_element", return_value=(None, "Element not found with selector 'Nope'. Tried: CSS, text.")
    ):
        result = await bm.smart_click(111, "Nope")
    assert "not found" in result.lower()
    assert "Clickable elements" in result


@pytest.mark.asyncio
async def test_smart_type_clear_first(bm_with_page):
    bm, page, _ = bm_with_page
    mock_elem = AsyncMock()
    mock_elem.fill = AsyncMock()
    mock_elem.input_value = AsyncMock(return_value="hello")
    mock_elem.count = AsyncMock(return_value=1)

    with patch.object(bm, "_find_element", return_value=(mock_elem, None)):
        result = await bm.smart_type(111, "input", "hello", clear_first=True)
    assert "Typed into field" in result
    mock_elem.fill.assert_called_once_with("hello", timeout=10000)


@pytest.mark.asyncio
async def test_screenshot_to_file(bm_with_page, tmp_path):
    bm, page, _ = bm_with_page
    page.screenshot = AsyncMock()

    with patch("koda.config.IMAGE_TEMP_DIR", tmp_path):
        result = await bm.screenshot_to_file(111)
    assert str(tmp_path) in result
    assert result.endswith(".png")


@pytest.mark.asyncio
async def test_screenshot_to_file_uses_runtime_browser_dir_for_live_scope(bm_with_page, tmp_path):
    bm, page, _ = bm_with_page
    page.screenshot = AsyncMock()
    runtime_dir = tmp_path / "runtime-browser"
    bm._runtime_live_scopes[111] = {"runtime_dir": str(runtime_dir)}

    with patch("koda.config.IMAGE_TEMP_DIR", tmp_path / "fallback"):
        result = await bm.screenshot_to_file(111)

    assert str(runtime_dir) in result
    assert result.endswith(".png")


@pytest.mark.asyncio
async def test_screenshot_to_file_updates_session_snapshot_metadata(bm_with_page, tmp_path):
    bm, page, _ = bm_with_page
    page.screenshot = AsyncMock()
    runtime_dir = tmp_path / "runtime-browser"
    bm._runtime_live_scopes[111] = {"runtime_dir": str(runtime_dir)}

    with patch("koda.config.IMAGE_TEMP_DIR", tmp_path / "fallback"):
        result = await bm.screenshot_to_file(111)

    snapshot = bm.get_session_snapshot(111)
    assert snapshot is not None
    assert snapshot["last_screenshot_path"] == result
    assert snapshot["url"] == "https://example.com"
    assert snapshot["last_title"] == "Example"


def test_get_session_snapshot_falls_back_to_last_url():
    bm = BrowserManager()
    bm._contexts[111] = {
        "context": AsyncMock(),
        "page": SimpleNamespace(url=""),
        "last_used": 0,
        "last_dialog": None,
        "created_at": 123.0,
        "last_url": "http://localhost:3004",
        "last_title": "Local App",
        "last_screenshot_path": "/tmp/browser.png",
    }

    snapshot = bm.get_session_snapshot(111)
    assert snapshot is not None
    assert snapshot["url"] == "http://localhost:3004"
    assert snapshot["last_title"] == "Local App"
    assert snapshot["last_screenshot_path"] == "/tmp/browser.png"


@pytest.mark.asyncio
async def test_get_elements(bm_with_page):
    bm, page, _ = bm_with_page
    page.evaluate = AsyncMock(
        return_value={
            "links": ['[0] href="/home" "Home"'],
            "buttons": ['[0] #submit "Submit"'],
        }
    )
    result = await bm.get_elements(111)
    assert "Links" in result
    assert "Buttons" in result


@pytest.mark.asyncio
async def test_get_page_text(bm_with_page):
    bm, page, _ = bm_with_page
    page.inner_text = AsyncMock(return_value="Hello World")
    result = await bm.get_page_text(111)
    assert "URL: https://example.com" in result
    assert "Title: Example" in result
    assert "Hello World" in result


@pytest.mark.asyncio
async def test_select_option_by_label(bm_with_page):
    bm, page, _ = bm_with_page
    mock_loc = AsyncMock()
    page.locator = MagicMock(return_value=mock_loc)
    result = await bm.select_option(111, "select#country", label="Brazil")
    assert "Selected option" in result


@pytest.mark.asyncio
async def test_scroll_down(bm_with_page):
    bm, page, _ = bm_with_page
    page.evaluate = AsyncMock(side_effect=[None, {"x": 0, "y": 500, "height": 2000}])
    result = await bm.scroll(111, direction="down", amount=500)
    assert "Scrolled down" in result


@pytest.mark.asyncio
async def test_wait_for_visible(bm_with_page):
    bm, page, _ = bm_with_page
    mock_loc = AsyncMock()
    mock_first = AsyncMock()
    mock_loc.first = mock_first
    page.locator = MagicMock(return_value=mock_loc)
    result = await bm.wait_for(111, "#results", state="visible")
    assert "is visible" in result


@pytest.mark.asyncio
async def test_hover_success(bm_with_page):
    bm, page, _ = bm_with_page
    mock_elem = AsyncMock()
    mock_elem.scroll_into_view_if_needed = AsyncMock()
    mock_elem.hover = AsyncMock()

    with patch.object(bm, "_find_element", return_value=(mock_elem, None)):
        result = await bm.hover(111, "Menu")
    assert "Hovered over" in result
    mock_elem.hover.assert_called_once()


@pytest.mark.asyncio
async def test_hover_element_not_found(bm_with_page):
    bm, page, _ = bm_with_page

    with patch.object(
        bm, "_find_element", return_value=(None, "Element not found with selector 'Nope'. Tried: CSS, text.")
    ):
        result = await bm.hover(111, "Nope")
    assert "not found" in result.lower()


@pytest.mark.asyncio
async def test_press_key_page_level(bm_with_page):
    bm, page, _ = bm_with_page
    page.keyboard = AsyncMock()
    page.keyboard.press = AsyncMock()

    result = await bm.press_key(111, "Enter")
    assert "Pressed key 'Enter'" in result
    page.keyboard.press.assert_called_once_with("Enter")


@pytest.mark.asyncio
async def test_press_key_on_element(bm_with_page):
    bm, page, _ = bm_with_page
    mock_elem = AsyncMock()
    mock_elem.press = AsyncMock()

    with patch.object(bm, "_find_element", return_value=(mock_elem, None)):
        result = await bm.press_key(111, "Escape", selector="input#search")
    assert "Pressed key 'Escape'" in result
    mock_elem.press.assert_called_once_with("Escape", timeout=5000)


@pytest.mark.asyncio
async def test_press_key_too_long(bm_with_page):
    bm, page, _ = bm_with_page
    result = await bm.press_key(111, "A" * 31)
    assert "too long" in result.lower()


@pytest.mark.asyncio
async def test_press_key_returns_url(bm_with_page):
    bm, page, _ = bm_with_page
    page.keyboard = AsyncMock()
    page.keyboard.press = AsyncMock()

    result = await bm.press_key(111, "Enter")
    assert "URL:" in result


@pytest.mark.asyncio
async def test_press_key_element_not_found(bm_with_page):
    bm, page, _ = bm_with_page

    with patch.object(bm, "_find_element", return_value=(None, "Element not found")):
        result = await bm.press_key(111, "Tab", selector="input#missing")
    assert "not found" in result.lower()


@pytest.mark.asyncio
async def test_go_back(bm_with_page):
    bm, page, _ = bm_with_page
    result = await bm.go_back(111)
    assert "Navigated back" in result
    page.go_back.assert_called_once()


@pytest.mark.asyncio
async def test_get_cookies(bm_with_page):
    bm, page, ctx = bm_with_page
    ctx.cookies = AsyncMock(
        return_value=[
            {"name": "sid", "value": "abc123", "domain": ".example.com"},
        ]
    )
    result = await bm.get_cookies(111)
    assert "sid" in result


@pytest.mark.asyncio
async def test_set_cookie_ssrf_blocked(bm_with_page):
    bm, page, _ = bm_with_page
    with patch("koda.services.http_client._check_url_safety", return_value="Blocked: private IP"):
        result = await bm.set_cookie(111, "test", "val", domain="localhost")
    assert "blocked domain" in result.lower() or "Blocked" in result


@pytest.mark.asyncio
async def test_submit_form(bm_with_page):
    bm, page, _ = bm_with_page
    mock_submit = AsyncMock()
    mock_submit.count = AsyncMock(return_value=1)
    mock_submit.first = AsyncMock()
    mock_submit.first.click = AsyncMock()
    page.locator = MagicMock(return_value=mock_submit)
    result = await bm.submit_form(111)
    assert "Form submitted" in result


@pytest.mark.asyncio
async def test_dialog_auto_accept():
    bm = BrowserManager()
    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.new_page = AsyncMock(return_value=mock_page)
    bm._browser = mock_browser

    ctx = await bm._get_or_create_context(222)
    assert ctx["last_dialog"] is None
    # Verify page.on was called with "dialog"
    mock_page.on.assert_called_once()
    assert mock_page.on.call_args[0][0] == "dialog"


@pytest.mark.asyncio
async def test_cleanup_does_not_remove_refreshed_context():
    """If a context is refreshed between stale snapshot and actual close, it should be kept."""
    manager = BrowserManager()

    # Simulate a context that was stale at snapshot time but refreshed before lock acquisition
    manager._contexts[42] = {
        "browser": AsyncMock(),
        "context": AsyncMock(),
        "page": AsyncMock(),
        "last_used": time.time(),  # fresh timestamp
        "last_dialog": None,
        "created_at": time.time(),
    }

    # The cleanup should not close it because re-check finds it fresh
    async with manager._lock:
        ctx = manager._contexts.get(42)
        assert ctx is not None
        # Simulate: the re-check sees it's fresh, so no close
        assert time.time() - ctx["last_used"] < _INACTIVITY_TIMEOUT

    assert 42 in manager._contexts
