"""Helpers for the public control-plane onboarding surface."""

from __future__ import annotations

import json
import os
from html import escape
from typing import Any, cast
from urllib.parse import urlsplit

from aiohttp import web

from .settings import ROOT_DIR

_OPENAPI_PATH = ROOT_DIR / "docs" / "openapi" / "control-plane.json"


def load_control_plane_openapi_spec() -> dict[str, Any]:
    """Load the maintained public OpenAPI description for onboarding/control-plane APIs."""
    payload = json.loads(_OPENAPI_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("control-plane OpenAPI document must be a JSON object")
    return cast(dict[str, Any], payload)


def _dashboard_urls(request: web.Request) -> tuple[str, str]:
    public_base = str(os.environ.get("WEB_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if public_base:
        return f"{public_base}/control-plane", "/control-plane"

    headers = getattr(request, "headers", {})
    forwarded_proto = str(headers.get("X-Forwarded-Proto") or "").split(",")[0].strip()
    forwarded_host = str(headers.get("X-Forwarded-Host") or "").split(",")[0].strip()
    scheme = forwarded_proto or getattr(request, "scheme", "") or "http"
    host = forwarded_host or headers.get("Host") or getattr(request, "host", "") or "127.0.0.1"
    parsed = urlsplit(f"{scheme}://{host}")
    hostname = parsed.hostname or "127.0.0.1"
    web_port = str(os.environ.get("WEB_PORT") or "3000").strip() or "3000"
    return f"{scheme}://{hostname}:{web_port}/control-plane", "/control-plane"


def render_setup_page(request: web.Request) -> str:
    """Render a compatibility page that points operators to the Next.js dashboard."""
    direct_dashboard_url, proxied_dashboard_path = _dashboard_urls(request)
    direct_dashboard_url = escape(direct_dashboard_url, quote=True)
    proxied_dashboard_path = escape(proxied_dashboard_path, quote=True)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Koda Dashboard Setup</title>
    <style>
      :root {{
        color-scheme: light;
        --bg: #09121b;
        --panel: rgba(9, 18, 27, 0.86);
        --card: rgba(255, 255, 255, 0.06);
        --ink: #f3f6fb;
        --muted: #a7b4c3;
        --line: rgba(255, 255, 255, 0.12);
        --accent: #67e8f9;
        --accent-strong: #0ea5e9;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        min-height: 100vh;
        font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
        background:
          radial-gradient(circle at top left, rgba(14, 165, 233, 0.24), transparent 34%),
          radial-gradient(circle at bottom right, rgba(103, 232, 249, 0.2), transparent 30%),
          var(--bg);
        color: var(--ink);
        display: grid;
        place-items: center;
        padding: 16px;
      }}
      main {{
        width: min(860px, calc(100vw - 32px));
        padding: 28px;
        border-radius: 28px;
        border: 1px solid var(--line);
        background: linear-gradient(180deg, rgba(9, 18, 27, 0.92), var(--panel));
        box-shadow: 0 28px 80px rgba(0, 0, 0, 0.45);
      }}
      .stack {{
        display: grid;
        gap: 18px;
      }}
      .pill {{
        display: inline-flex;
        width: fit-content;
        align-items: center;
        border-radius: 999px;
        border: 1px solid rgba(103, 232, 249, 0.26);
        background: rgba(103, 232, 249, 0.1);
        color: var(--accent);
        padding: 8px 12px;
        font-size: 0.82rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }}
      h1 {{
        margin: 0;
        font-size: clamp(2rem, 6vw, 3.35rem);
        line-height: 1;
      }}
      p {{
        margin: 0;
        color: var(--muted);
        line-height: 1.6;
      }}
      .actions {{
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
      }}
      .button {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border-radius: 999px;
        padding: 12px 18px;
        font-weight: 700;
        text-decoration: none;
        border: 1px solid transparent;
      }}
      .button.primary {{
        background: linear-gradient(135deg, var(--accent-strong), var(--accent));
        color: #06202c;
      }}
      .button.secondary {{
        border-color: var(--line);
        background: var(--card);
        color: var(--ink);
      }}
      .grid {{
        display: grid;
        gap: 14px;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      }}
      .item {{
        border: 1px solid var(--line);
        border-radius: 18px;
        padding: 16px;
        background: var(--card);
      }}
      .item strong {{
        display: block;
        margin-bottom: 6px;
        color: var(--ink);
      }}
      code {{
        display: inline-block;
        margin-top: 4px;
        padding: 3px 8px;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.08);
        color: var(--ink);
      }}
      @media (max-width: 720px) {{
        main {{
          padding: 22px;
        }}
      }}
    </style>
  </head>
  <body>
    <main class="stack">
      <span class="pill">Compatibility bridge</span>
      <h1>Configuration moved into the dashboard</h1>
      <p>
        Koda now completes first-run installation directly inside the Next dashboard. Use the
        dashboard for operator login, access policy, provider verification, and the first agent.
      </p>

      <div class="actions">
        <a class="button primary" href="{direct_dashboard_url}">Open dashboard setup</a>
        <a class="button secondary" href="{proxied_dashboard_path}">
          Open /control-plane via reverse proxy
        </a>
        <a class="button secondary" href="/openapi/control-plane.json" target="_blank" rel="noreferrer">
          OpenAPI
        </a>
      </div>

      <section class="grid">
        <article class="item">
          <strong>Step 1</strong>
          Open the dashboard, enter the short-lived setup code, and exchange it for the owner
          registration flow.
        </article>
        <article class="item">
          <strong>Step 2</strong>
          Create the local owner account and continue with an HTTP-only operator session.
        </article>
        <article class="item">
          <strong>Step 3</strong>
          Configure access policy, verify the default provider, and optionally create the first
          agent from the catalog.
        </article>
      </section>

      <p>
        Local quickstart usually opens the dashboard at:<br />
        <code>{direct_dashboard_url}</code>
      </p>
      <p>
        If you front Koda with a reverse proxy, publish the dashboard route and send operators to
        <code>{proxied_dashboard_path}</code>.
      </p>
    </main>
  </body>
</html>
"""
