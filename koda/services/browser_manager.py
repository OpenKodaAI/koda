"""Browser automation manager using Playwright."""

import asyncio
import contextlib
import inspect
import socket
import time
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

from koda.logging_config import get_logger
from koda.services.http_client import _check_url_safety, _is_private_ip

log = get_logger(__name__)

_INACTIVITY_TIMEOUT = 30 * 60  # 30 minutes


async def _maybe_await(result: object) -> None:
    if inspect.isawaitable(result):
        await cast(Any, result)


def _check_browser_url_safety(url: str, *, allow_private: bool) -> str | None:
    parsed = urlparse(url)

    if parsed.scheme in {"data", "about"}:
        return None

    if not allow_private:
        return _check_url_safety(url)

    if parsed.scheme not in {"http", "https"}:
        return "Only http, https, data, and about URLs are allowed."

    hostname = parsed.hostname
    if not hostname:
        return "Invalid URL: no hostname."

    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return f"Could not resolve hostname: {hostname}"

    private_only = True
    for info in infos:
        ip_str = str(info[4][0])
        if not _is_private_ip(ip_str):
            private_only = False
            break

    if private_only:
        return None

    return _check_url_safety(url)


class BrowserManager:
    """Singleton managing Playwright browser contexts per runtime scope."""

    def __init__(self) -> None:
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._contexts: dict[int, dict[str, Any]] = {}  # scope_id -> {context, page, last_used}
        self._runtime_live_scopes: dict[int, dict[str, Any]] = {}
        self._cleanup_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Launch browser and start cleanup loop."""
        await self.ensure_started()

    async def _ensure_playwright_started(self) -> bool:
        """Start Playwright without forcing the default headless browser."""
        if self._playwright is not None:
            if self._cleanup_task is None or self._cleanup_task.done():
                self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            return True
        try:
            async with self._lock:
                if self._playwright is not None:
                    if self._cleanup_task is None or self._cleanup_task.done():
                        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
                    return True
                try:
                    from playwright.async_api import async_playwright

                    self._playwright = await async_playwright().start()
                    if self._cleanup_task is None or self._cleanup_task.done():
                        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
                    log.info("browser_playwright_started")
                    return True
                except ImportError:
                    log.warning("playwright_not_installed")
                except Exception:
                    log.exception("browser_playwright_start_failed")
                    if self._playwright is not None:
                        with contextlib.suppress(Exception):
                            await self._playwright.stop()
                    self._playwright = None
                return False
        except Exception:
            log.exception("browser_playwright_start_failed_outer")
            return False

    async def ensure_started(self) -> bool:
        """Start Playwright/Chromium on demand and report readiness."""
        if self._playwright is not None and self._browser is not None:
            if self._cleanup_task is None or self._cleanup_task.done():
                self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            return True
        if self._browser is not None:
            if self._cleanup_task is None or self._cleanup_task.done():
                self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            return True
        if not await self._ensure_playwright_started():
            return False
        try:
            async with self._lock:
                if self._playwright is not None and self._browser is not None:
                    if self._cleanup_task is None or self._cleanup_task.done():
                        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
                    return True
                try:
                    playwright = self._playwright
                    if playwright is None:
                        raise RuntimeError("Playwright is not available.")
                    if self._browser is None:
                        self._browser = await playwright.chromium.launch(headless=True)
                    if self._cleanup_task is None or self._cleanup_task.done():
                        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
                    log.info("browser_started")
                    return True
                except ImportError:
                    log.warning("playwright_not_installed")
                except Exception:
                    log.exception("browser_start_failed")
                    if self._browser is not None:
                        with contextlib.suppress(Exception):
                            await self._browser.close()
                    if self._playwright is not None:
                        with contextlib.suppress(Exception):
                            await self._playwright.stop()
                    self._browser = None
                    self._playwright = None
                return False
        except Exception:
            log.exception("browser_start_failed_outer")
            return False

    async def stop(self) -> None:
        """Close all contexts and browser."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._cleanup_task
            self._cleanup_task = None

        for scope_id in list(self._contexts):
            await self._close_context(scope_id)

        if self._browser:
            await self._browser.close()
            self._browser = None

        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

        log.info("browser_stopped")

    @property
    def is_available(self) -> bool:
        return self._browser is not None

    async def _get_or_create_context(self, scope_id: int) -> dict[str, Any]:
        """Get existing or create a browser context for a runtime scope."""
        if scope_id in self._contexts:
            self._contexts[scope_id]["last_used"] = time.time()
            return self._contexts[scope_id]

        async with self._lock:
            # Re-check after acquiring lock
            if scope_id in self._contexts:
                self._contexts[scope_id]["last_used"] = time.time()
                return self._contexts[scope_id]

            ready = await self.ensure_started()
            if not ready:
                raise RuntimeError("Browser is not available.")
            if self._browser is None:
                raise RuntimeError("Browser is not available.")
            browser = self._browser
            if browser is None:
                raise RuntimeError("Browser is not available.")
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0.0.0 Safari/537.36",
                record_video_dir=None,
            )
            page = await context.new_page()

            async def _handle_dialog(dialog: Any) -> None:
                self._contexts[scope_id]["last_dialog"] = dialog.message
                await _maybe_await(dialog.accept())

            def _on_dialog(dialog: Any) -> None:
                task = asyncio.create_task(_handle_dialog(dialog))

                def _consume_task(task_result: asyncio.Task[None]) -> None:
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        task_result.result()

                task.add_done_callback(_consume_task)

            await _maybe_await(page.on("dialog", _on_dialog))

            self._contexts[scope_id] = {
                "browser": browser,
                "context": context,
                "page": page,
                "tabs": {0: page},
                "active_tab": 0,
                "next_tab_id": 1,
                "last_used": time.time(),
                "last_dialog": None,
                "created_at": time.time(),
                "last_url": "",
                "last_title": "",
                "last_screenshot_path": "",
                "network_capture_active": False,
                "captured_requests": [],
                "mocked_routes": {},
            }
            log.info("browser_context_created", scope_id=scope_id)
            return self._contexts[scope_id]

    async def _close_context(self, scope_id: int) -> None:
        """Close a scope browser context."""
        ctx_data = self._contexts.pop(scope_id, None)
        if ctx_data:
            # Close all tab pages
            for tab_page in ctx_data.get("tabs", {}).values():
                with contextlib.suppress(Exception):
                    await tab_page.close()
            with contextlib.suppress(Exception):
                await ctx_data["context"].close()
            browser = ctx_data.get("browser")
            if browser is not None and browser is not self._browser:
                with contextlib.suppress(Exception):
                    await browser.close()
            log.info("browser_context_closed", scope_id=scope_id)

    def _get_active_page(self, scope_id: int) -> Any | None:
        """Get the active page for a scope. Returns None if no context exists."""
        ctx = self._contexts.get(scope_id)
        if not ctx:
            return None
        active_tab = ctx.get("active_tab", 0)
        tabs = ctx.get("tabs", {})
        return tabs.get(active_tab, ctx.get("page"))

    def _require_active_page(self, scope_id: int) -> Any:
        page = self._get_active_page(scope_id)
        if page is None:
            raise RuntimeError("No active page in browser context.")
        return page

    def _sync_active_page(self, scope_id: int) -> None:
        """Keep ctx['page'] in sync with the active tab."""
        ctx = self._contexts.get(scope_id)
        if ctx:
            active = self._get_active_page(scope_id)
            if active is not None:
                ctx["page"] = active

    def _resolve_output_dir(self, scope_id: int) -> Path:
        from koda.config import IMAGE_TEMP_DIR

        runtime_scope = self._runtime_live_scopes.get(scope_id) or {}
        runtime_dir = str(runtime_scope.get("runtime_dir") or "").strip()
        target_dir = IMAGE_TEMP_DIR if not runtime_dir else Path(runtime_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir

    async def _cleanup_loop(self) -> None:
        """Periodically close inactive browser contexts."""
        while True:
            await asyncio.sleep(60)
            now = time.time()
            stale_ids = [
                scope_id for scope_id, data in self._contexts.items() if now - data["last_used"] > _INACTIVITY_TIMEOUT
            ]
            for scope_id in stale_ids:
                async with self._lock:
                    ctx = self._contexts.get(scope_id)
                    if ctx and time.time() - ctx["last_used"] > _INACTIVITY_TIMEOUT:
                        await self._close_context(scope_id)

    async def _find_element(self, page: Any, selector: str, timeout: int = 10000) -> tuple[Any | None, str | None]:
        """Try multiple strategies to find an element. Returns (locator, None) or (None, error_str)."""
        strategies = [
            ("CSS", lambda: page.locator(selector)),
            ("text", lambda: page.get_by_text(selector)),
            ("button role", lambda: page.get_by_role("button", name=selector)),
            ("link role", lambda: page.get_by_role("link", name=selector)),
            ("placeholder", lambda: page.get_by_placeholder(selector)),
            ("label", lambda: page.get_by_label(selector)),
        ]
        per_strategy_timeout = min(2000, timeout // len(strategies))
        tried = []
        for name, locator_fn in strategies:
            try:
                loc = locator_fn()
                await loc.first.wait_for(state="visible", timeout=per_strategy_timeout)
                return loc.first, None
            except Exception:
                tried.append(name)
        return None, f"Element not found with selector '{selector}'. Tried: {', '.join(tried)}."

    async def navigate(self, scope_id: int, url: str, *, allow_private: bool | None = None) -> str:
        """Navigate to a URL. Returns page info with metadata."""
        from koda.config import BROWSER_ALLOW_PRIVATE_NETWORK

        # Determine effective allow_private: explicit parameter wins, then config flag
        # for runtime live scopes. The global kill-switch always blocks if False.
        if allow_private is not None:
            effective_allow_private = allow_private and BROWSER_ALLOW_PRIVATE_NETWORK
        else:
            effective_allow_private = (scope_id in self._runtime_live_scopes) and BROWSER_ALLOW_PRIVATE_NETWORK
        safety_error = _check_browser_url_safety(url, allow_private=effective_allow_private)
        if safety_error:
            return f"Error: {safety_error}"
        ctx = await self._get_or_create_context(scope_id)
        page = self._require_active_page(scope_id)
        try:
            try:
                await page.goto(url, wait_until="networkidle", timeout=15000)
            except Exception:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            title = cast(str, await page.title())
            ctx["last_url"] = cast(str, page.url)
            ctx["last_title"] = title
            ctx["last_used"] = time.time()
            counts = cast(
                dict[str, int],
                await page.evaluate("""() => ({
                links: document.querySelectorAll('a[href]').length,
                forms: document.querySelectorAll('form').length,
                inputs: document.querySelectorAll('input, textarea, select').length,
            })"""),
            )
            return (
                f"Navigated to: {title}\n"
                f"URL: {cast(str, page.url)}\n"
                f"Links: {counts['links']} | Forms: {counts['forms']} | Inputs: {counts['inputs']}"
            )
        except Exception as e:
            return f"Error navigating: {e}"

    async def click(self, scope_id: int, selector: str) -> str:
        """Click an element by CSS selector."""
        await self._get_or_create_context(scope_id)
        page = self._require_active_page(scope_id)
        try:
            await page.click(selector, timeout=10000)
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
            return f"Clicked: {selector}\nCurrent URL: {cast(str, page.url)}"
        except Exception as e:
            return f"Error clicking '{selector}': {e}"

    async def type_text(self, scope_id: int, selector: str, text: str) -> str:
        """Type text into an element."""
        await self._get_or_create_context(scope_id)
        page = self._require_active_page(scope_id)
        try:
            await page.fill(selector, text, timeout=10000)
            return f"Typed into: {selector}"
        except Exception as e:
            return f"Error typing into '{selector}': {e}"

    async def screenshot(self, scope_id: int) -> bytes | None:
        """Take a screenshot. Returns PNG bytes or None."""
        await self._get_or_create_context(scope_id)
        page = self._require_active_page(scope_id)
        try:
            return cast(bytes, await page.screenshot(type="png"))
        except Exception:
            log.exception("screenshot_error", scope_id=scope_id)
            return None

    async def run_js(self, scope_id: int, script: str) -> str:
        """Execute JavaScript in the page context."""
        await self._get_or_create_context(scope_id)
        page = self._require_active_page(scope_id)
        try:
            result = await page.evaluate(script)
            return str(result) if result is not None else "(no return value)"
        except Exception as e:
            return f"JS Error: {e}"

    async def execute_js(self, scope_id: int, script: str) -> str:
        """Compatibility wrapper used by the dispatcher."""
        return await self.run_js(scope_id, script)

    async def download_file(
        self,
        scope_id: int,
        url: str,
        filename: str | None = None,
        *,
        allow_private: bool = False,
    ) -> str:
        """Download a file through the active browser context and save it locally."""
        safety_error = _check_browser_url_safety(url, allow_private=allow_private)
        if safety_error:
            return f"Error: {safety_error}"

        await self._get_or_create_context(scope_id)
        page = self._require_active_page(scope_id)
        target_dir = self._resolve_output_dir(scope_id)
        safe_filename = Path(filename).name if filename else ""
        try:
            async with page.expect_download(timeout=15000) as download_info:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            download = await download_info.value
            suggested_name = Path(download.suggested_filename or "").name
            final_name = safe_filename or suggested_name or f"download_{int(time.time() * 1000)}"
            path = target_dir / final_name
            await download.save_as(str(path))
            return str(path)
        except Exception as e:
            return f"Error downloading file: {e}"

    async def upload_file(self, scope_id: int, selector: str, file_path: str) -> str:
        """Upload a local file to a file input."""
        await self._get_or_create_context(scope_id)
        page = self._require_active_page(scope_id)
        try:
            resolved_path = str(Path(file_path).expanduser().resolve())
            await page.locator(selector).set_input_files(resolved_path, timeout=10000)
            return f"Uploaded file to '{selector}': {resolved_path}"
        except Exception as e:
            return f"Error uploading file to '{selector}': {e}"

    async def set_viewport(self, scope_id: int, width: int, height: int) -> str:
        """Resize the active page viewport."""
        ctx = await self._get_or_create_context(scope_id)
        page = self._require_active_page(scope_id)
        try:
            await page.set_viewport_size({"width": width, "height": height})
            ctx["last_used"] = time.time()
            return f"Viewport set to {width}x{height}."
        except Exception as e:
            return f"Error setting viewport: {e}"

    async def page_to_pdf(self, scope_id: int) -> str:
        """Render the current page to PDF and return the saved file path."""
        await self._get_or_create_context(scope_id)
        page = self._require_active_page(scope_id)
        target_dir = self._resolve_output_dir(scope_id)
        path = target_dir / f"browser_{scope_id}_{int(time.time() * 1000)}.pdf"
        try:
            await page.pdf(path=str(path), print_background=True)
            return str(path)
        except Exception as e:
            return f"Error creating PDF: {e}"

    async def hover(self, scope_id: int, selector: str, timeout: int = 10000) -> str:
        """Hover over an element using smart element finding."""
        await self._get_or_create_context(scope_id)
        page = self._require_active_page(scope_id)
        elem, error = await self._find_element(page, selector, timeout)
        if error:
            return error
        if elem is None:
            return f"Element not found: {selector}"
        try:
            await elem.scroll_into_view_if_needed(timeout=5000)
            await elem.hover(timeout=timeout)
            return f"Hovered over '{selector}'.\nURL: {cast(str, page.url)}"
        except Exception as e:
            return f"Error hovering over '{selector}': {e}"

    async def press_key(self, scope_id: int, key: str, selector: str | None = None, timeout: int = 5000) -> str:
        """Press a keyboard key, optionally on a specific element."""
        if len(key) > 30:
            return "Error: key name too long (max 30 characters)."
        await self._get_or_create_context(scope_id)
        page = self._require_active_page(scope_id)
        try:
            if selector:
                elem, error = await self._find_element(page, selector, timeout)
                if error:
                    return error
                if elem is None:
                    return f"Element not found: {selector}"
                await elem.press(key, timeout=timeout)
            else:
                await page.keyboard.press(key)
            return f"Pressed key '{key}'.\nURL: {cast(str, page.url)}"
        except Exception as e:
            return f"Error pressing key '{key}': {e}"

    async def smart_click(self, scope_id: int, selector: str, timeout: int = 15000) -> str:
        """Click using smart element finding with fallback strategies."""
        await self._get_or_create_context(scope_id)
        page = self._require_active_page(scope_id)
        elem, error = await self._find_element(page, selector, timeout)
        if error:
            # List similar clickable elements to help
            try:
                clickables = cast(
                    list[str],
                    await page.evaluate("""() => {
                    const els = [...document.querySelectorAll('a, button, [role=button], [onclick]')];
                    return els.slice(0, 10).map(e => e.textContent?.trim().substring(0, 50) || e.tagName);
                }"""),
                )
                return f"{error}\nClickable elements on page: {', '.join(clickables)}"
            except Exception:
                return error
        if elem is None:
            return f"Element not found: {selector}"
        try:
            await elem.scroll_into_view_if_needed(timeout=5000)
            await elem.click(timeout=timeout)
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
            title = cast(str, await page.title())
            return f"Clicked successfully.\nURL: {cast(str, page.url)}\nTitle: {title}"
        except Exception as e:
            return f"Error clicking '{selector}': {e}"

    async def smart_type(
        self, scope_id: int, selector: str, text: str, clear_first: bool = True, timeout: int = 10000
    ) -> str:
        """Type into a field using smart element finding."""
        await self._get_or_create_context(scope_id)
        page = self._require_active_page(scope_id)
        elem, error = await self._find_element(page, selector, timeout)
        if error:
            return error
        if elem is None:
            return f"Element not found: {selector}"
        try:
            if clear_first:
                await elem.fill(text, timeout=timeout)
            else:
                await elem.type(text, timeout=timeout)
            try:
                value = await elem.input_value()
            except Exception:
                value = text
            return f"Typed into field. Current value: {value}"
        except Exception as e:
            return f"Error typing into '{selector}': {e}"

    async def select_option(
        self,
        scope_id: int,
        selector: str,
        *,
        value: str | None = None,
        label: str | None = None,
        index: int | None = None,
    ) -> str:
        """Select an option from a dropdown."""
        await self._get_or_create_context(scope_id)
        page = self._require_active_page(scope_id)
        try:
            loc = page.locator(selector)
            if value is not None:
                await loc.select_option(value=value, timeout=10000)
            elif label is not None:
                await loc.select_option(label=label, timeout=10000)
            elif index is not None:
                await loc.select_option(index=index, timeout=10000)
            else:
                return "Error: provide 'value', 'label', or 'index'."
            return f"Selected option in '{selector}'."
        except Exception as e:
            return f"Error selecting option in '{selector}': {e}"

    async def screenshot_to_file(self, scope_id: int, full_page: bool = False, selector: str | None = None) -> str:
        """Take a screenshot and save to file. Returns absolute file path."""
        ctx = await self._get_or_create_context(scope_id)
        page = self._require_active_page(scope_id)
        try:
            ts = int(time.time() * 1000)
            target_dir = self._resolve_output_dir(scope_id)
            path = target_dir / f"browser_{scope_id}_{ts}.png"
            if selector:
                loc = page.locator(selector)
                await loc.screenshot(path=str(path), timeout=15000)
            else:
                await page.screenshot(path=str(path), full_page=full_page, type="png")
            ctx["last_screenshot_path"] = str(path)
            ctx["last_url"] = cast(str, page.url)
            with contextlib.suppress(Exception):
                ctx["last_title"] = cast(str, await page.title())
            ctx["last_used"] = time.time()
            return str(path)
        except Exception as e:
            return f"Error taking screenshot: {e}"

    async def get_page_text(self, scope_id: int, selector: str | None = None, max_length: int = 50000) -> str:
        """Get text content of the page or a specific element."""
        await self._get_or_create_context(scope_id)
        page = self._require_active_page(scope_id)
        try:
            title = await page.title()
            url = page.url
            if selector:
                loc = page.locator(selector)
                text = await loc.first.inner_text(timeout=10000)
            else:
                text = await page.inner_text("body", timeout=10000)
            if len(text) > max_length:
                text = text[:max_length] + f"\n... (truncated, {len(text)} chars total)"
            return f"URL: {url}\nTitle: {title}\n---\n{text}"
        except Exception as e:
            return f"Error getting text: {e}"

    async def get_elements(self, scope_id: int, element_type: str = "all") -> str:
        """List interactive elements on the page."""
        await self._get_or_create_context(scope_id)
        page = self._require_active_page(scope_id)
        try:
            result = await page.evaluate(
                """(type) => {
                const MAX = 50;
                const out = {};
                const collect = (sel, category) => {
                    const els = [...document.querySelectorAll(sel)].slice(0, MAX);
                    out[category] = els.map((e, i) => {
                        const text = (e.textContent || '').trim().substring(0, 60);
                        const href = e.getAttribute('href') || '';
                        const elName = e.getAttribute('name') || '';
                        const id = e.id || '';
                        const placeholder = e.getAttribute('placeholder') || '';
                        const ariaLabel = e.getAttribute('aria-label') || '';
                        let desc = `[${i}] `;
                        if (id) desc += `#${id} `;
                        if (elName) desc += `name="${elName}" `;
                        if (placeholder) desc += `placeholder="${placeholder}" `;
                        if (ariaLabel) desc += `aria-label="${ariaLabel}" `;
                        if (href) desc += `href="${href.substring(0, 80)}" `;
                        if (text) desc += `"${text}"`;
                        return desc.trim();
                    });
                };
                if (type === 'all' || type === 'links') collect('a[href]', 'links');
                if (type === 'all' || type === 'buttons') {
                    collect(
                        'button, [role=button], input[type=button], input[type=submit]',
                        'buttons'
                    );
                }
                if (type === 'all' || type === 'inputs') {
                    collect('input:not([type=hidden]), textarea, select', 'inputs');
                }
                if (type === 'all' || type === 'forms') collect('form', 'forms');
                return out;
            }""",
                element_type,
            )
            lines = []
            for category, items in result.items():
                lines.append(f"\n### {category.title()} ({len(items)})")
                for item in items:
                    lines.append(f"  {item}")
            return "\n".join(lines) if lines else "No interactive elements found."
        except Exception as e:
            return f"Error listing elements: {e}"

    async def scroll(self, scope_id: int, direction: str = "down", amount: int = 500) -> str:
        """Scroll the page."""
        await self._get_or_create_context(scope_id)
        page = self._require_active_page(scope_id)
        try:
            if direction == "top":
                await page.evaluate("window.scrollTo(0, 0)")
            elif direction == "bottom":
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            elif direction == "up":
                await page.evaluate("(a) => window.scrollBy(0, -a)", amount)
            else:  # down
                await page.evaluate("(a) => window.scrollBy(0, a)", amount)
            pos = await page.evaluate(
                "() => ({ x: window.scrollX, y: window.scrollY, height: document.body.scrollHeight })"
            )
            return f"Scrolled {direction}. Position: y={pos['y']}/{pos['height']}"
        except Exception as e:
            return f"Error scrolling: {e}"

    async def wait_for(self, scope_id: int, selector: str, state: str = "visible", timeout: int = 30000) -> str:
        """Wait for an element to reach a given state."""
        await self._get_or_create_context(scope_id)
        page = self._require_active_page(scope_id)
        try:
            start = time.time()
            await page.locator(selector).first.wait_for(state=state, timeout=timeout)
            elapsed = time.time() - start
            return f"Element '{selector}' is {state}. Waited {elapsed:.1f}s."
        except Exception as e:
            return f"Error waiting for '{selector}': {e}"

    async def go_back(self, scope_id: int) -> str:
        """Navigate back in browser history."""
        await self._get_or_create_context(scope_id)
        page = self._require_active_page(scope_id)
        try:
            await page.go_back(wait_until="domcontentloaded", timeout=15000)
            title = await page.title()
            return f"Navigated back.\nURL: {page.url}\nTitle: {title}"
        except Exception as e:
            return f"Error going back: {e}"

    async def go_forward(self, scope_id: int) -> str:
        """Navigate forward in browser history."""
        await self._get_or_create_context(scope_id)
        page = self._require_active_page(scope_id)
        try:
            await page.go_forward(wait_until="domcontentloaded", timeout=15000)
            title = await page.title()
            return f"Navigated forward.\nURL: {page.url}\nTitle: {title}"
        except Exception as e:
            return f"Error going forward: {e}"

    async def get_cookies(self, scope_id: int, url: str | None = None) -> str:
        """Get cookies for the current context."""
        ctx = await self._get_or_create_context(scope_id)
        context = ctx["context"]
        try:
            if url:
                cookies = await context.cookies(url)
            else:
                cookies = await context.cookies()
            if not cookies:
                return "No cookies found."
            lines = []
            for c in cookies[:50]:
                lines.append(f"  {c['name']}={c['value'][:40]} (domain={c.get('domain', '')})")
            return f"Cookies ({len(cookies)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error getting cookies: {e}"

    async def set_cookie(
        self,
        scope_id: int,
        name: str,
        value: str,
        domain: str | None = None,
        path: str = "/",
        *,
        allow_private: bool = False,
    ) -> str:
        """Set a cookie. Domain is validated for SSRF safety."""
        if domain:
            from koda.config import BROWSER_ALLOW_PRIVATE_NETWORK

            skip_safety = allow_private and BROWSER_ALLOW_PRIVATE_NETWORK and scope_id in self._runtime_live_scopes
            if not skip_safety:
                from koda.services.http_client import _check_url_safety

                safety_error = _check_url_safety(f"https://{domain}/")
                if safety_error:
                    return f"Error: blocked domain — {safety_error}"
        ctx = await self._get_or_create_context(scope_id)
        context = ctx["context"]
        try:
            cookie = {"name": name, "value": value, "path": path}
            if domain:
                cookie["domain"] = domain
                cookie["url"] = f"https://{domain}/"
            else:
                current_url = self._require_active_page(scope_id).url
                cookie["url"] = current_url
            await context.add_cookies([cookie])
            return f"Cookie '{name}' set."
        except Exception as e:
            return f"Error setting cookie: {e}"

    async def submit_form(self, scope_id: int, selector: str | None = None) -> str:
        """Submit a form by clicking submit button or dispatching submit event."""
        await self._get_or_create_context(scope_id)
        page = self._require_active_page(scope_id)
        try:
            if selector:
                form = page.locator(selector)
                submit_btn = form.locator("input[type=submit], button[type=submit], button:not([type])")
            else:
                submit_btn = page.locator("input[type=submit], button[type=submit]")
            if await submit_btn.count() > 0:
                await submit_btn.first.click(timeout=10000)
            else:
                # Fallback: dispatch submit event
                if selector:
                    await page.eval_on_selector(selector, "el => el.requestSubmit ? el.requestSubmit() : el.submit()")
                else:
                    await page.eval_on_selector("form", "el => el.requestSubmit ? el.requestSubmit() : el.submit()")
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
            title = await page.title()
            return f"Form submitted.\nURL: {page.url}\nTitle: {title}"
        except Exception as e:
            return f"Error submitting form: {e}"

    async def start_network_capture(self, scope_id: int, url_pattern: str | None = None) -> str:
        """Start capturing network requests."""
        from koda.config import BROWSER_NETWORK_CAPTURE_LIMIT, BROWSER_NETWORK_INTERCEPTION_ENABLED

        if not BROWSER_NETWORK_INTERCEPTION_ENABLED:
            return "Error: network interception is not enabled. Set BROWSER_NETWORK_INTERCEPTION_ENABLED=true."
        ctx = await self._get_or_create_context(scope_id)
        if ctx.get("network_capture_active"):
            return "Capture already active. Stop it first or read captured requests."
        ctx["network_capture_active"] = True
        ctx["captured_requests"] = []
        page = ctx.get("page")
        if not page:
            return "Error: no active page."

        async def _on_request(request: Any) -> None:
            entry: dict[str, Any] = {
                "url": request.url,
                "method": request.method,
                "resource_type": request.resource_type,
                "timestamp": time.time(),
            }
            if url_pattern and url_pattern not in request.url:
                return
            captured = ctx.get("captured_requests", [])
            captured.append(entry)
            if len(captured) > BROWSER_NETWORK_CAPTURE_LIMIT:
                ctx["captured_requests"] = captured[-BROWSER_NETWORK_CAPTURE_LIMIT:]

        async def _on_response(response: Any) -> None:
            url = response.url
            captured = ctx.get("captured_requests", [])
            for entry in reversed(captured):
                if entry["url"] == url and "status" not in entry:
                    entry["status"] = response.status
                    entry["content_type"] = response.headers.get("content-type", "")
                    break

        def _sync_request_handler(request: Any) -> None:
            asyncio.create_task(_on_request(request))

        def _sync_response_handler(response: Any) -> None:
            asyncio.create_task(_on_response(response))

        page.on("request", _sync_request_handler)
        page.on("response", _sync_response_handler)
        ctx["_network_request_handler"] = _sync_request_handler
        ctx["_network_response_handler"] = _sync_response_handler

        filter_msg = f" (filter: {url_pattern})" if url_pattern else ""
        return f"Network capture started{filter_msg}. Use browser_network_requests to view captured data."

    async def stop_network_capture(self, scope_id: int) -> str:
        """Stop capturing network requests."""
        ctx = self._contexts.get(scope_id)
        if not ctx:
            return "Error: no browser context."
        if not ctx.get("network_capture_active"):
            return "No capture active."
        ctx["network_capture_active"] = False
        page = ctx.get("page")
        if page:
            handler = ctx.pop("_network_request_handler", None)
            if handler:
                with contextlib.suppress(Exception):
                    page.remove_listener("request", handler)
            handler = ctx.pop("_network_response_handler", None)
            if handler:
                with contextlib.suppress(Exception):
                    page.remove_listener("response", handler)
        count = len(ctx.get("captured_requests", []))
        return f"Capture stopped. {count} requests captured."

    def get_captured_requests(
        self, scope_id: int, limit: int = 50, filter_str: str | None = None
    ) -> tuple[str, list[dict[str, Any]]]:
        """Get captured network requests. Returns (text, structured_data)."""
        ctx = self._contexts.get(scope_id)
        if not ctx:
            return "Error: no browser context.", []
        captured = ctx.get("captured_requests", [])
        if filter_str:
            captured = [r for r in captured if filter_str.lower() in r.get("url", "").lower()]
        captured = captured[-limit:]
        if not captured:
            return "No captured requests.", []
        lines = [f"Captured requests ({len(captured)}):"]
        for r in captured:
            status = r.get("status", "???")
            lines.append(f"  [{r['method']}] {status} {r['url'][:120]}")
        return "\n".join(lines), captured

    async def mock_route(
        self,
        scope_id: int,
        url_pattern: str,
        response_status: int = 200,
        response_body: str = "",
        response_headers: dict[str, str] | None = None,
    ) -> str:
        """Mock a URL pattern with a custom response."""
        from koda.config import BROWSER_NETWORK_INTERCEPTION_ENABLED

        if not BROWSER_NETWORK_INTERCEPTION_ENABLED:
            return "Error: network interception is not enabled."
        ctx = await self._get_or_create_context(scope_id)
        page = ctx.get("page")
        if not page:
            return "Error: no active page."

        async def _route_handler(route: Any) -> None:
            await route.fulfill(
                status=response_status,
                body=response_body,
                headers=response_headers or {"content-type": "application/json"},
            )

        try:
            await page.route(url_pattern, _route_handler)
            mocks = ctx.get("mocked_routes", {})
            mocks[url_pattern] = {"status": response_status, "body_length": len(response_body)}
            ctx["mocked_routes"] = mocks
            return f"Route mocked: {url_pattern} → {response_status}"
        except Exception as e:
            return f"Error setting up mock: {e}"

    def get_session_snapshot(self, scope_id: int) -> dict[str, Any] | None:
        """Return lightweight browser session metadata for the frontend."""
        ctx = self._contexts.get(scope_id)
        if not ctx:
            return None
        page = self._get_active_page(scope_id)
        page_url = getattr(page, "url", "") if page is not None else ""
        if not page_url and ctx:
            page_url = str(ctx.get("last_url") or "")
        tabs = ctx.get("tabs", {})
        parsed = urlparse(page_url) if page_url else None
        origin = f"{parsed.scheme}://{parsed.hostname}" if parsed and parsed.hostname else page_url
        if parsed and parsed.port:
            origin = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
        snapshot = {
            "scope_id": scope_id,
            "url": page_url,
            "origin": origin,
            "hostname": parsed.hostname if parsed else None,
            "domain": parsed.hostname if parsed else None,
            "scheme": parsed.scheme if parsed else None,
            "last_used": ctx.get("last_used") if ctx else None,
            "created_at": ctx.get("created_at") if ctx else None,
            "last_dialog": ctx.get("last_dialog") if ctx else None,
            "last_title": ctx.get("last_title") if ctx else None,
            "last_screenshot_path": ctx.get("last_screenshot_path") if ctx else None,
            "active_tab": ctx.get("active_tab", 0),
            "tab_count": len(tabs),
        }
        return snapshot

    def list_active_sessions(self) -> list[dict[str, Any]]:
        """List active browser sessions."""
        scope_ids = sorted(self._contexts)
        return [snapshot for scope_id in scope_ids if (snapshot := self.get_session_snapshot(scope_id))]

    # ------------------------------------------------------------------
    # Tab management
    # ------------------------------------------------------------------

    async def open_tab(self, scope_id: int, url: str | None = None) -> str:
        """Open a new tab. Returns tab info."""
        from koda.config import BROWSER_MAX_TABS

        ctx = await self._get_or_create_context(scope_id)
        tabs = ctx.get("tabs", {})
        if len(tabs) >= BROWSER_MAX_TABS:
            return f"Error: maximum {BROWSER_MAX_TABS} tabs reached. Close a tab first."
        context = ctx["context"]
        try:
            page = await context.new_page()

            async def _handle_dialog(dialog: Any) -> None:
                self._contexts[scope_id]["last_dialog"] = dialog.message
                await _maybe_await(dialog.accept())

            def _on_dialog(dialog: Any) -> None:
                task = asyncio.create_task(_handle_dialog(dialog))

                def _consume(t: asyncio.Task[None]) -> None:
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        t.result()

                task.add_done_callback(_consume)

            await _maybe_await(page.on("dialog", _on_dialog))

            tab_id = ctx["next_tab_id"]
            ctx["next_tab_id"] = tab_id + 1
            ctx["tabs"][tab_id] = page
            ctx["active_tab"] = tab_id
            ctx["page"] = page  # sync
            ctx["last_used"] = time.time()
            if url:
                safety_error = _check_browser_url_safety(url, allow_private=scope_id in self._runtime_live_scopes)
                if safety_error:
                    return f"Tab {tab_id} opened (blank). URL blocked: {safety_error}"
                try:
                    try:
                        await page.goto(url, wait_until="networkidle", timeout=15000)
                    except Exception:
                        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                except Exception as e:
                    return f"Tab {tab_id} opened but navigation failed: {e}"
            title = await page.title() if url else "about:blank"
            return (
                f"Tab {tab_id} opened and activated.\nURL: {page.url}\nTitle: {title}\nTotal tabs: {len(ctx['tabs'])}"
            )
        except Exception as e:
            return f"Error opening tab: {e}"

    async def close_tab(self, scope_id: int, tab_id: int | None = None) -> str:
        """Close a tab. If closing active tab, switch to another."""
        ctx = self._contexts.get(scope_id)
        if not ctx:
            return "Error: no browser context."
        tabs = ctx.get("tabs", {})
        if tab_id is None:
            tab_id = ctx.get("active_tab", 0)
        if tab_id not in tabs:
            return f"Error: tab {tab_id} not found. Available: {sorted(tabs.keys())}"
        if len(tabs) <= 1:
            return "Error: cannot close the last tab."
        page = tabs.pop(tab_id)
        with contextlib.suppress(Exception):
            await page.close()
        # If we closed the active tab, switch to another
        if ctx["active_tab"] == tab_id:
            new_active = next(iter(tabs))
            ctx["active_tab"] = new_active
            ctx["page"] = tabs[new_active]
        ctx["last_used"] = time.time()
        return f"Tab {tab_id} closed. Active tab: {ctx['active_tab']}. Total: {len(tabs)}"

    async def switch_tab(self, scope_id: int, tab_id: int) -> str:
        """Switch to a different tab."""
        ctx = self._contexts.get(scope_id)
        if not ctx:
            return "Error: no browser context."
        tabs = ctx.get("tabs", {})
        if tab_id not in tabs:
            return f"Error: tab {tab_id} not found. Available: {sorted(tabs.keys())}"
        ctx["active_tab"] = tab_id
        ctx["page"] = tabs[tab_id]
        ctx["last_used"] = time.time()
        page = tabs[tab_id]
        try:
            title = await page.title()
            url = page.url
        except Exception:
            title = "(unknown)"
            url = "(unknown)"
        return f"Switched to tab {tab_id}.\nURL: {url}\nTitle: {title}"

    async def list_tabs(self, scope_id: int) -> tuple[str, list[dict[str, Any]]]:
        """List all open tabs. Returns (text, structured_data)."""
        ctx = self._contexts.get(scope_id)
        if not ctx:
            return "Error: no browser context.", []
        tabs = ctx.get("tabs", {})
        active = ctx.get("active_tab", 0)
        lines: list[str] = []
        data: list[dict[str, Any]] = []
        for tid, page in sorted(tabs.items()):
            try:
                url = page.url
                title = await page.title()
            except Exception:
                url = "(unknown)"
                title = "(unknown)"
            marker = " (active)" if tid == active else ""
            lines.append(f"Tab {tid}{marker}: {title} — {url}")
            data.append({"tab_id": tid, "url": url, "title": title, "active": tid == active})
        return "\n".join(lines), data

    async def compare_tabs(self, scope_id: int, tab_ids: list[int], selector: str | None = None) -> str:
        """Compare text content of two or more tabs."""
        ctx = self._contexts.get(scope_id)
        if not ctx:
            return "Error: no browser context."
        tabs = ctx.get("tabs", {})
        if len(tab_ids) < 2:
            return "Error: provide at least 2 tab_ids to compare."
        results: list[str] = []
        for tid in tab_ids:
            if tid not in tabs:
                return f"Error: tab {tid} not found."
            page = tabs[tid]
            try:
                if selector:
                    loc = page.locator(selector)
                    text = await loc.first.inner_text(timeout=10000)
                else:
                    text = await page.inner_text("body", timeout=10000)
                if len(text) > 5000:
                    text = text[:5000] + "... (truncated)"
            except Exception as e:
                text = f"(error: {e})"
            try:
                title = await page.title()
                url = page.url
            except Exception:
                title = "(unknown)"
                url = "(unknown)"
            results.append(f"=== Tab {tid}: {title} ({url}) ===\n{text}")
        return "\n\n".join(results)

    # --- Session persistence ---

    def _get_session_dir(self, scope_id: int) -> str:
        """Get the session storage directory for a scope."""
        import os

        from koda.config import BROWSER_SESSION_DIR, IMAGE_TEMP_DIR

        base = BROWSER_SESSION_DIR if BROWSER_SESSION_DIR else str(IMAGE_TEMP_DIR)
        return os.path.join(base, "browser_sessions", str(scope_id))

    async def save_session(self, scope_id: int, name: str) -> str:
        """Save the current browser session (cookies, localStorage) to disk."""
        import json as _json
        import os
        import re as _re

        from koda.config import BROWSER_SESSION_PERSISTENCE_ENABLED

        if not BROWSER_SESSION_PERSISTENCE_ENABLED:
            return "Error: session persistence is not enabled. Set BROWSER_SESSION_PERSISTENCE_ENABLED=true."
        if not _re.match(r"^[a-zA-Z0-9_-]{1,64}$", name):
            return "Error: invalid session name. Use alphanumeric, hyphens, underscores (1-64 chars)."

        ctx = self._contexts.get(scope_id)
        if not ctx:
            return "Error: no browser context."
        context = ctx.get("context")
        if not context:
            return "Error: no browser context object."

        try:
            state = await context.storage_state()
            session_dir = self._get_session_dir(scope_id)
            os.makedirs(session_dir, mode=0o700, exist_ok=True)
            path = os.path.join(session_dir, f"{name}.json")
            with open(path, "w") as f:
                _json.dump(state, f)
            os.chmod(path, 0o600)
            cookie_count = len(state.get("cookies", []))
            origin_count = len(state.get("origins", []))
            return f"Session '{name}' saved. Cookies: {cookie_count}, Origins: {origin_count}"
        except Exception as e:
            return f"Error saving session: {e}"

    async def restore_session(self, scope_id: int, name: str) -> str:
        """Restore a saved browser session. This replaces the current context."""
        import json as _json
        import os
        import re as _re

        from koda.config import BROWSER_SESSION_PERSISTENCE_ENABLED

        if not BROWSER_SESSION_PERSISTENCE_ENABLED:
            return "Error: session persistence is not enabled."
        if not _re.match(r"^[a-zA-Z0-9_-]{1,64}$", name):
            return "Error: invalid session name."

        session_dir = self._get_session_dir(scope_id)
        path = os.path.join(session_dir, f"{name}.json")
        if not os.path.isfile(path):
            return f"Error: session '{name}' not found."

        try:
            with open(path) as f:
                state = _json.load(f)
        except Exception as e:
            return f"Error loading session file: {e}"

        # Close existing context and create new one with saved state
        await self._close_context(scope_id)

        try:
            ready = await self.ensure_started()
            if not ready or self._browser is None:
                return "Error: browser not available."

            context = await self._browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0.0.0 Safari/537.36",
                storage_state=state,
            )
            page = await context.new_page()

            # Set up dialog handler
            async def _handle_dialog(dialog: Any) -> None:
                self._contexts[scope_id]["last_dialog"] = dialog.message
                await _maybe_await(dialog.accept())

            def _on_dialog(dialog: Any) -> None:
                task = asyncio.create_task(_handle_dialog(dialog))

                def _consume_task(task_result: asyncio.Task[None]) -> None:
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        task_result.result()

                task.add_done_callback(_consume_task)

            await _maybe_await(page.on("dialog", _on_dialog))

            self._contexts[scope_id] = {
                "browser": self._browser,
                "context": context,
                "page": page,
                "tabs": {0: page},
                "active_tab": 0,
                "next_tab_id": 1,
                "last_used": time.time(),
                "last_dialog": None,
                "created_at": time.time(),
                "last_url": "",
                "last_title": "",
                "last_screenshot_path": "",
            }

            cookie_count = len(state.get("cookies", []))
            return f"Session '{name}' restored. Cookies: {cookie_count}. Navigate to a URL to use the restored auth."
        except Exception as e:
            return f"Error restoring session: {e}"

    def list_sessions(self, scope_id: int) -> tuple[str, list[dict]]:
        """List saved sessions. Returns (text, structured_data)."""
        import os
        import time as _time

        session_dir = self._get_session_dir(scope_id)
        if not os.path.isdir(session_dir):
            return "No saved sessions.", []

        sessions: list[dict] = []
        for filename in sorted(os.listdir(session_dir)):
            if not filename.endswith(".json"):
                continue
            name = filename[:-5]
            path = os.path.join(session_dir, filename)
            stat = os.stat(path)
            sessions.append(
                {
                    "name": name,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                    "age_hours": round((_time.time() - stat.st_mtime) / 3600, 1),
                }
            )

        if not sessions:
            return "No saved sessions.", []

        lines = [f"Saved sessions ({len(sessions)}):"]
        for s in sessions:
            lines.append(f"  {s['name']} — {s['size']} bytes, {s['age_hours']}h ago")
        return "\n".join(lines), sessions


# Singleton instance
browser_manager = BrowserManager()
