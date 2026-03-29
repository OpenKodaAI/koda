"""Browser automation manager using Playwright."""

import asyncio
import contextlib
import inspect
import socket
import time
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
                "last_used": time.time(),
                "last_dialog": None,
                "created_at": time.time(),
                "last_url": "",
                "last_title": "",
                "last_screenshot_path": "",
            }
            log.info("browser_context_created", scope_id=scope_id)
            return self._contexts[scope_id]

    async def _close_context(self, scope_id: int) -> None:
        """Close a scope browser context."""
        ctx_data = self._contexts.pop(scope_id, None)
        if ctx_data:
            with contextlib.suppress(Exception):
                await ctx_data["context"].close()
            browser = ctx_data.get("browser")
            if browser is not None and browser is not self._browser:
                with contextlib.suppress(Exception):
                    await browser.close()
            log.info("browser_context_closed", scope_id=scope_id)

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

    async def navigate(self, scope_id: int, url: str) -> str:
        """Navigate to a URL. Returns page info with metadata."""
        safety_error = _check_browser_url_safety(url, allow_private=scope_id in self._runtime_live_scopes)
        if safety_error:
            return f"Error: {safety_error}"
        ctx = await self._get_or_create_context(scope_id)
        page = ctx["page"]
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
        ctx = await self._get_or_create_context(scope_id)
        page = ctx["page"]
        try:
            await page.click(selector, timeout=10000)
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
            return f"Clicked: {selector}\nCurrent URL: {cast(str, page.url)}"
        except Exception as e:
            return f"Error clicking '{selector}': {e}"

    async def type_text(self, scope_id: int, selector: str, text: str) -> str:
        """Type text into an element."""
        ctx = await self._get_or_create_context(scope_id)
        page = ctx["page"]
        try:
            await page.fill(selector, text, timeout=10000)
            return f"Typed into: {selector}"
        except Exception as e:
            return f"Error typing into '{selector}': {e}"

    async def screenshot(self, scope_id: int) -> bytes | None:
        """Take a screenshot. Returns PNG bytes or None."""
        ctx = await self._get_or_create_context(scope_id)
        page = ctx["page"]
        try:
            return cast(bytes, await page.screenshot(type="png"))
        except Exception:
            log.exception("screenshot_error", scope_id=scope_id)
            return None

    async def run_js(self, scope_id: int, script: str) -> str:
        """Execute JavaScript in the page context."""
        ctx = await self._get_or_create_context(scope_id)
        page = ctx["page"]
        try:
            result = await page.evaluate(script)
            return str(result) if result is not None else "(no return value)"
        except Exception as e:
            return f"JS Error: {e}"

    async def hover(self, scope_id: int, selector: str, timeout: int = 10000) -> str:
        """Hover over an element using smart element finding."""
        ctx = await self._get_or_create_context(scope_id)
        page = ctx["page"]
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
        ctx = await self._get_or_create_context(scope_id)
        page = ctx["page"]
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
        ctx = await self._get_or_create_context(scope_id)
        page = ctx["page"]
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
        ctx = await self._get_or_create_context(scope_id)
        page = ctx["page"]
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
        ctx = await self._get_or_create_context(scope_id)
        page = ctx["page"]
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
        from koda.config import IMAGE_TEMP_DIR

        ctx = await self._get_or_create_context(scope_id)
        page = ctx["page"]
        try:
            ts = int(time.time() * 1000)
            runtime_scope = self._runtime_live_scopes.get(scope_id) or {}
            runtime_dir = str(runtime_scope.get("runtime_dir") or "").strip()
            target_dir = IMAGE_TEMP_DIR if not runtime_dir else type(IMAGE_TEMP_DIR)(runtime_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
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
        ctx = await self._get_or_create_context(scope_id)
        page = ctx["page"]
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
        ctx = await self._get_or_create_context(scope_id)
        page = ctx["page"]
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
        ctx = await self._get_or_create_context(scope_id)
        page = ctx["page"]
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
        ctx = await self._get_or_create_context(scope_id)
        page = ctx["page"]
        try:
            start = time.time()
            await page.locator(selector).first.wait_for(state=state, timeout=timeout)
            elapsed = time.time() - start
            return f"Element '{selector}' is {state}. Waited {elapsed:.1f}s."
        except Exception as e:
            return f"Error waiting for '{selector}': {e}"

    async def go_back(self, scope_id: int) -> str:
        """Navigate back in browser history."""
        ctx = await self._get_or_create_context(scope_id)
        page = ctx["page"]
        try:
            await page.go_back(wait_until="domcontentloaded", timeout=15000)
            title = await page.title()
            return f"Navigated back.\nURL: {page.url}\nTitle: {title}"
        except Exception as e:
            return f"Error going back: {e}"

    async def go_forward(self, scope_id: int) -> str:
        """Navigate forward in browser history."""
        ctx = await self._get_or_create_context(scope_id)
        page = ctx["page"]
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

    async def set_cookie(self, scope_id: int, name: str, value: str, domain: str | None = None, path: str = "/") -> str:
        """Set a cookie. Domain is validated for SSRF safety."""
        if domain:
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
                current_url = ctx["page"].url
                cookie["url"] = current_url
            await context.add_cookies([cookie])
            return f"Cookie '{name}' set."
        except Exception as e:
            return f"Error setting cookie: {e}"

    async def submit_form(self, scope_id: int, selector: str | None = None) -> str:
        """Submit a form by clicking submit button or dispatching submit event."""
        ctx = await self._get_or_create_context(scope_id)
        page = ctx["page"]
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

    def get_session_snapshot(self, scope_id: int) -> dict[str, Any] | None:
        """Return lightweight browser session metadata for the frontend."""
        ctx = self._contexts.get(scope_id)
        if not ctx:
            return None
        page = ctx.get("page") if ctx else None
        page_url = getattr(page, "url", "") if page is not None else ""
        if not page_url and ctx:
            page_url = str(ctx.get("last_url") or "")
        snapshot = {
            "scope_id": scope_id,
            "url": page_url,
            "last_used": ctx.get("last_used") if ctx else None,
            "created_at": ctx.get("created_at") if ctx else None,
            "last_dialog": ctx.get("last_dialog") if ctx else None,
            "last_title": ctx.get("last_title") if ctx else None,
            "last_screenshot_path": ctx.get("last_screenshot_path") if ctx else None,
        }
        return snapshot

    def list_active_sessions(self) -> list[dict[str, Any]]:
        """List active browser sessions."""
        scope_ids = sorted(self._contexts)
        return [snapshot for scope_id in scope_ids if (snapshot := self.get_session_snapshot(scope_id))]


# Singleton instance
browser_manager = BrowserManager()
