#!/usr/bin/env python3
"""Capture authenticated Koda screenshots for README and docs assets."""

from __future__ import annotations

import argparse
import asyncio
import base64
import contextlib
import hashlib
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import urljoin


def reexec_with_uv_for_missing_package(package: str) -> NoReturn:
    if os.environ.get("KODA_SCREENSHOT_UV_REEXEC") == "1":
        raise RuntimeError(f"{package} is required. Run `uv run python scripts/capture_docs_screenshots.py ...`.")
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError(f"{package} is required. Install dependencies or run this script with `uv run python`.")
    env = dict(os.environ)
    env["KODA_SCREENSHOT_UV_REEXEC"] = "1"
    os.execvpe(uv, [uv, "run", "python", *sys.argv], env)


try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ModuleNotFoundError:
    reexec_with_uv_for_missing_package("cryptography")

WEB_OPERATOR_SESSION_COOKIE = "koda_operator_session"
OWNER_EXISTS_HINT_COOKIE = "koda_has_owner"
DEFAULT_BASE_URL = "http://127.0.0.1:3000"
DEFAULT_OUT_DIR = "docs/assets/screenshots"
DEFAULT_AGENT_PREFIX = "DEMO_"
KODA_AGENT_ID = "KODA"
APP_TOUR_STORAGE_KEY = "ui:onboarding-tour"
APP_TOUR_CHAPTER_IDS = [
    "shell_intro",
    "overview",
    "control_plane_catalog",
    "control_plane_editor",
    "runtime",
    "sessions",
    "executions",
    "memory",
    "costs",
    "schedules",
    "dlq",
    "system_settings",
]


@dataclass(frozen=True)
class ScreenshotRoute:
    name: str
    path: str
    wait_for: str | None = None
    full_page: bool = True


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_env_file_fallback(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_environment(env_file: Path | None = None) -> None:
    path = env_file or repo_root() / ".env"
    try:
        from dotenv import load_dotenv
    except ModuleNotFoundError:
        load_env_file_fallback(path)
        return
    load_dotenv(path)


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def seal_web_operator_token(token: str, secret: str, *, nonce: bytes | None = None) -> str:
    plaintext = token.strip().encode("utf-8")
    if not plaintext:
        return ""
    key = hashlib.sha256(secret.strip().encode("utf-8")).digest()
    iv = nonce or os.urandom(12)
    encrypted = AESGCM(key).encrypt(iv, plaintext, None)
    ciphertext, tag = encrypted[:-16], encrypted[-16:]
    return ".".join((b64url(iv), b64url(ciphertext), b64url(tag)))


async def screenshot_page(page: Any, route: ScreenshotRoute, base_url: str, out_dir: Path) -> None:
    target = urljoin(base_url, route.path)
    await page.goto(target, wait_until="domcontentloaded", timeout=60_000)
    if route.wait_for:
        await page.locator(route.wait_for).first.wait_for(timeout=20_000)
    else:
        with contextlib.suppress(Exception):
            await page.wait_for_function(
                """
                () => {
                  const text = document.body?.innerText || "";
                  const skeletons = document.querySelectorAll(".skeleton").length;
                  return text.trim().length > 450 && skeletons === 0;
                }
                """,
                timeout=45_000,
            )
    with contextlib.suppress(Exception):
        await page.wait_for_load_state("networkidle", timeout=10_000)
    await page.wait_for_timeout(1_200)
    await page.evaluate(
        """
        () => {
          for (const item of document.querySelectorAll('[aria-live="polite"][aria-atomic="true"]')) {
            item.remove();
          }
        }
        """
    )
    await page.screenshot(path=str(out_dir / f"{route.name}.png"), full_page=route.full_page)


async def wait_for_dashboard_ready(context: Any, base_url: str) -> None:
    endpoints = [
        "/api/health",
        "/api/control-plane/dashboard/agents/summary",
        "/api/control-plane/dashboard/executions?limit=100",
        "/api/control-plane/dashboard/costs?period=30d&groupBy=auto&lang=en-US",
        "/api/control-plane/dashboard/sessions?limit=200",
    ]
    deadline = time.monotonic() + 75
    last_error = "not checked"
    while time.monotonic() < deadline:
        ready = True
        for endpoint in endpoints:
            try:
                response = await context.request.get(urljoin(base_url, endpoint), timeout=15_000)
                if not response.ok:
                    ready = False
                    last_error = f"{endpoint} returned HTTP {response.status}"
                    break
            except Exception as exc:
                ready = False
                last_error = f"{endpoint} failed: {exc}"
                break
        if ready:
            return
        await asyncio.sleep(2)
    raise RuntimeError(f"Dashboard did not become ready before capture: {last_error}")


async def install_docs_browser_state(context: Any) -> None:
    now_ms = int(time.time() * 1000)
    completed_tour_state = {
        "version": 2,
        "status": "completed",
        "currentStepId": None,
        "completedChapters": APP_TOUR_CHAPTER_IDS,
        "updatedAt": now_ms,
        "completedAt": now_ms,
        "skippedAt": None,
    }
    tour_key = json.dumps(APP_TOUR_STORAGE_KEY)
    tour_state = json.dumps(json.dumps(completed_tour_state))
    theme_preference = json.dumps(json.dumps("dark"))
    await context.add_init_script(
        f"""
        (() => {{
          window.localStorage.setItem({tour_key}, {tour_state});
          window.localStorage.setItem("ui:sidebar-collapsed", "false");
          window.localStorage.setItem("ui:theme-preference", {theme_preference});
          window.localStorage.setItem("koda.dashboard.setupChecklistDismissedAt", new Date().toISOString());
        }})();
        """
    )


async def install_sanitized_operator_status(context: Any) -> None:
    async def handle_auth_status(route: Any) -> None:
        response = await route.fetch()
        try:
            payload = await response.json()
        except (json.JSONDecodeError, ValueError):
            await route.fulfill(response=response)
            return
        if isinstance(payload, dict):
            payload["session_subject"] = "docs_demo"
            payload["operator"] = {
                "id": "usr_docs_demo",
                "username": "docs.operator",
                "email": "docs.operator@example.com",
                "display_name": "Docs Operator",
            }
        await route.fulfill(
            status=response.status,
            headers={"content-type": "application/json"},
            body=json.dumps(payload),
        )

    await context.route("**/api/control-plane/auth/status", handle_auth_status)


async def capture(args: argparse.Namespace) -> None:
    try:
        from playwright.async_api import Browser, async_playwright
    except ModuleNotFoundError:
        reexec_with_uv_for_missing_package("playwright")

    load_environment(args.env_file)
    token = args.token or os.environ.get("CONTROL_PLANE_API_TOKEN", "")
    secret = args.session_secret or os.environ.get("WEB_OPERATOR_SESSION_SECRET", "")
    if not token:
        raise RuntimeError("CONTROL_PLANE_API_TOKEN is required for authenticated screenshots.")
    if not secret:
        raise RuntimeError("WEB_OPERATOR_SESSION_SECRET is required to seal the dashboard session cookie.")

    base_url = str(args.base_url).rstrip("/") + "/"
    out_dir = Path(args.out).expanduser()
    if not out_dir.is_absolute():
        out_dir = repo_root() / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    demo_agent_id = f"{args.agent_prefix}ATLAS"
    routes = [
        ScreenshotRoute("overview", "/"),
        ScreenshotRoute("costs", "/costs"),
        ScreenshotRoute("executions", "/executions"),
        ScreenshotRoute("sessions", "/sessions"),
        ScreenshotRoute("control-plane", "/control-plane"),
        ScreenshotRoute("agent-detail", f"/control-plane/agents/{demo_agent_id}"),
        ScreenshotRoute("runtime", "/runtime"),
        ScreenshotRoute("routines-schedules", "/routines/schedules"),
        ScreenshotRoute("memory", "/memory"),
        ScreenshotRoute("memory-review", "/memory/review"),
    ]

    async with async_playwright() as playwright:
        browser: Browser = await playwright.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                viewport={"width": 1440, "height": 1100},
                device_scale_factor=1,
                color_scheme="dark",
            )
            await context.add_cookies(
                [
                    {
                        "name": WEB_OPERATOR_SESSION_COOKIE,
                        "value": seal_web_operator_token(token, secret),
                        "url": base_url,
                        "httpOnly": True,
                        "sameSite": "Strict",
                    },
                    {
                        "name": OWNER_EXISTS_HINT_COOKIE,
                        "value": "1",
                        "url": base_url,
                        "httpOnly": False,
                        "sameSite": "Lax",
                    },
                ]
            )
            await install_docs_browser_state(context)
            await install_sanitized_operator_status(context)
            await wait_for_dashboard_ready(context, base_url)
            task_response = await context.request.get(
                urljoin(base_url, f"/api/runtime/agents/{KODA_AGENT_ID}/tasks?limit=1")
            )
            if task_response.ok:
                try:
                    payload: Any = await task_response.json()
                except (json.JSONDecodeError, ValueError):
                    payload = None
                if isinstance(payload, list) and payload:
                    task_id = payload[0].get("id") if isinstance(payload[0], dict) else None
                    if task_id is not None:
                        routes.append(
                            ScreenshotRoute(
                                "runtime-task",
                                f"/runtime/{KODA_AGENT_ID}/tasks/{int(task_id)}",
                            )
                        )

            page = await context.new_page()
            for route in routes:
                try:
                    await screenshot_page(page, route, base_url, out_dir)
                    print(f"captured {route.name}.png", flush=True)
                except Exception as exc:
                    print(f"skipped {route.name}: {exc}", flush=True)
            await context.close()
        finally:
            await browser.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture Koda documentation screenshots.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Dashboard base URL.")
    parser.add_argument("--out", default=DEFAULT_OUT_DIR, help="Output directory for PNG screenshots.")
    parser.add_argument("--agent-prefix", default=DEFAULT_AGENT_PREFIX, help="Managed demo-agent prefix.")
    parser.add_argument("--env-file", type=Path, default=None, help="Path to the environment file to load.")
    parser.add_argument("--token", default="", help="Control-plane token. Defaults to CONTROL_PLANE_API_TOKEN.")
    parser.add_argument(
        "--session-secret",
        default="",
        help="Web session secret. Defaults to WEB_OPERATOR_SESSION_SECRET.",
    )
    return parser.parse_args()


def main() -> int:
    asyncio.run(capture(parse_args()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
