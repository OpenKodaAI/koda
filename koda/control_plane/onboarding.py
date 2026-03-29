"""Helpers for the public control-plane onboarding surface."""

from __future__ import annotations

import json
from typing import Any, cast

from aiohttp import web

from .settings import ROOT_DIR

_OPENAPI_PATH = ROOT_DIR / "docs" / "openapi" / "control-plane.json"


def load_control_plane_openapi_spec() -> dict[str, Any]:
    """Load the maintained public OpenAPI description for onboarding/control-plane APIs."""
    payload = json.loads(_OPENAPI_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("control-plane OpenAPI document must be a JSON object")
    return cast(dict[str, Any], payload)


def render_setup_page(request: web.Request) -> str:
    """Render a lightweight setup UI backed by the existing control-plane API."""
    return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Koda Setup</title>
    <style>
      :root {{
        color-scheme: light;
        --bg: #f4f7f8;
        --card: #ffffff;
        --ink: #162126;
        --muted: #5c6b73;
        --line: #d9e2e7;
        --accent: #0f766e;
        --accent-soft: #dff4f1;
        --danger: #b42318;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
        background: linear-gradient(180deg, #eef6f7 0%, var(--bg) 35%, #ffffff 100%);
        color: var(--ink);
      }}
      main {{
        max-width: 1040px;
        margin: 0 auto;
        padding: 32px 20px 48px;
      }}
      .hero {{
        display: grid;
        gap: 12px;
        margin-bottom: 24px;
      }}
      .hero h1 {{
        margin: 0;
        font-size: clamp(2rem, 5vw, 3.25rem);
        line-height: 1;
      }}
      .hero p {{
        margin: 0;
        max-width: 760px;
        color: var(--muted);
        font-size: 1.05rem;
      }}
      .grid {{
        display: grid;
        gap: 18px;
        grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      }}
      .card {{
        background: var(--card);
        border: 1px solid var(--line);
        border-radius: 18px;
        padding: 18px;
        box-shadow: 0 14px 40px rgba(15, 23, 42, 0.06);
      }}
      h2 {{
        margin: 0 0 10px;
        font-size: 1.1rem;
      }}
      .stack {{
        display: grid;
        gap: 12px;
      }}
      label {{
        display: grid;
        gap: 6px;
        color: var(--muted);
        font-size: 0.95rem;
      }}
      input, select, textarea, button {{
        font: inherit;
      }}
      input, select, textarea {{
        width: 100%;
        border: 1px solid var(--line);
        border-radius: 12px;
        padding: 12px 13px;
        background: #fff;
        color: var(--ink);
      }}
      textarea {{
        min-height: 92px;
        resize: vertical;
      }}
      .row {{
        display: grid;
        gap: 12px;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      }}
      .actions {{
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
      }}
      button {{
        border: 0;
        border-radius: 999px;
        padding: 11px 16px;
        cursor: pointer;
      }}
      .primary {{
        background: var(--accent);
        color: white;
      }}
      .secondary {{
        background: var(--accent-soft);
        color: var(--accent);
      }}
      .pill {{
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 6px 10px;
        border-radius: 999px;
        font-size: 0.85rem;
        background: #eef2f4;
        color: var(--muted);
      }}
      .pill.ok {{
        background: #ddf7eb;
        color: #05603a;
      }}
      .pill.warn {{
        background: #fff4db;
        color: #8a4b00;
      }}
      .pill.error {{
        background: #fde7e5;
        color: var(--danger);
      }}
      .status-list {{
        display: grid;
        gap: 10px;
      }}
      .status-item {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 12px;
        padding: 10px 12px;
        border: 1px solid var(--line);
        border-radius: 12px;
      }}
      pre {{
        margin: 0;
        white-space: pre-wrap;
        word-break: break-word;
        border-radius: 14px;
        background: #0f172a;
        color: #dbeafe;
        padding: 14px;
        min-height: 96px;
      }}
      .muted {{ color: var(--muted); }}
      a {{ color: var(--accent); }}
    </style>
  </head>
  <body>
    <main>
      <section class="hero">
        <span class="pill">Open source quickstart</span>
        <h1>Koda setup</h1>
        <p>
          The platform stack is already running. Use this control-plane surface to configure
          product settings such as access, providers, agents, and secrets. Infrastructure stays in
          Docker and bootstrap env, while ongoing product configuration lives here.
        </p>
      </section>

      <div class="grid">
        <section class="card stack">
          <h2>Bootstrap access</h2>
          <label>
            Control-plane token
            <input id="token" type="text" placeholder="Paste CONTROL_PLANE_API_TOKEN" />
          </label>
          <div class="actions">
            <button class="secondary" id="refresh-status" type="button">Refresh status</button>
            <a class="pill" href="/openapi/control-plane.json" target="_blank" rel="noreferrer">OpenAPI</a>
          </div>
          <div class="status-list" id="service-status"></div>
        </section>

        <section class="card stack">
          <h2>Account and access</h2>
          <div class="row">
            <label>
              Owner name
              <input id="owner-name" type="text" placeholder="Open Source Maintainer" />
            </label>
            <label>
              Owner email
              <input id="owner-email" type="email" placeholder="maintainer@example.com" />
            </label>
          </div>
          <div class="row">
            <label>
              Owner GitHub
              <input id="owner-github" type="text" placeholder="example-owner" />
            </label>
            <label>
              Allowed Telegram user IDs
              <input id="allowed-users" type="text" placeholder="123456789,987654321" />
            </label>
          </div>
          <p class="muted">
            The same IDs will be used as knowledge admins unless you set them later in the control plane.
          </p>
        </section>

        <section class="card stack">
          <h2>Default provider</h2>
          <div class="row">
            <label>
              Provider
              <select id="provider-id"></select>
            </label>
            <label>
              Auth mode
              <select id="provider-auth-mode">
                <option value="api_key">API key</option>
                <option value="local">Local/server</option>
              </select>
            </label>
          </div>
          <div class="row">
            <label>
              API key
              <input id="provider-api-key" type="password" placeholder="Optional for local mode" />
            </label>
            <label>
              Base URL
              <input id="provider-base-url" type="text" placeholder="Only used for local/server providers" />
            </label>
          </div>
          <label>
            Project ID
            <input id="provider-project-id" type="text" placeholder="Only for providers that require it" />
          </label>
          <p class="muted" id="provider-help">
            Choose a provider, configure it here, and Koda will verify the connection before saving defaults.
          </p>
        </section>

        <section class="card stack">
          <h2>First agent (optional)</h2>
          <div class="row">
            <label>
              Agent ID
              <input id="agent-id" type="text" value="AGENT_A" />
            </label>
            <label>
              Display name
              <input id="agent-display-name" type="text" value="AGENT_A" />
            </label>
          </div>
          <label>
            Telegram token
            <input id="agent-telegram-token" type="password" placeholder="Paste the BotFather token here" />
          </label>
          <p class="muted">
            If you provide a Telegram token, Koda will create, publish, and activate the
            first agent automatically. You can also skip this now and finish agent setup later in the
            interface.
          </p>
          <div class="actions">
            <button class="primary" id="save-setup" type="button">Save configuration</button>
          </div>
        </section>
      </div>

      <section class="card stack" style="margin-top: 18px;">
        <h2>Result</h2>
        <pre id="result">Refresh status to inspect the current stack.</pre>
      </section>
    </main>

    <script>
      const state = {{
        token: "",
        providers: [],
      }};

      const tokenInput = document.getElementById("token");
      const providerSelect = document.getElementById("provider-id");
      const authModeSelect = document.getElementById("provider-auth-mode");
      const providerHelp = document.getElementById("provider-help");
      const resultEl = document.getElementById("result");
      const statusEl = document.getElementById("service-status");

      function getToken() {{
        return tokenInput.value.trim();
      }}

      function authHeaders() {{
        state.token = getToken();
        const headers = {{"Content-Type": "application/json"}};
        if (state.token) {{
          headers["Authorization"] = `Bearer ${{state.token}}`;
        }}
        return headers;
      }}

      function statusClass(ok, ready) {{
        if (ok && ready) return "pill ok";
        if (ok) return "pill warn";
        return "pill error";
      }}

      function renderStatus(payload) {{
        statusEl.innerHTML = "";
        const entries = [
          ["Control plane", true, payload.control_plane.ready],
          ["Postgres", payload.storage.database.enabled, payload.storage.database.ready],
          ["Object storage", payload.storage.object_storage.enabled, payload.storage.object_storage.ready],
          ["Provider verified", payload.steps.provider_configured, payload.steps.provider_configured],
          ["Access configured", payload.steps.access_configured, payload.steps.access_configured],
          ["Agent ready", payload.steps.agent_ready, payload.steps.agent_ready],
        ];
        for (const [label, ok, ready] of entries) {{
          const item = document.createElement("div");
          item.className = "status-item";
          item.innerHTML =
            `<span>${{label}}</span><span class="${{statusClass(ok, ready)}}">` +
            `${{ready ? "ready" : ok ? "pending" : "missing"}}</span>`;
          statusEl.appendChild(item);
        }}
      }}

      function renderProviders(providers) {{
        state.providers = providers;
        providerSelect.innerHTML = "";
        for (const provider of providers) {{
          const option = document.createElement("option");
          option.value = provider.provider_id;
          option.textContent = `${{provider.title || provider.provider_id}}`;
          providerSelect.appendChild(option);
        }}
        if (providers.length) {{
          providerSelect.value = providers[0].provider_id;
          updateProviderHelp();
        }}
      }}

      function updateProviderHelp() {{
        const provider = state.providers.find((item) => item.provider_id === providerSelect.value);
        if (!provider) {{
          providerHelp.textContent = "Choose a provider and configure it.";
          return;
        }}
        const modes = (provider.supported_auth_modes || []).join(", ");
        providerHelp.textContent = `${{provider.title || provider.provider_id}} supports: ${{modes || "api_key"}}.`;
        const authMode = authModeSelect.value;
        const localOnly = authMode === "local";
        document.getElementById("provider-api-key").disabled = localOnly;
        document.getElementById("provider-base-url").disabled = !localOnly && provider.provider_id !== "ollama";
      }}

      async function refreshStatus() {{
        state.token = getToken();
        resultEl.textContent = "Loading status...";
        try {{
          const response = await fetch("/api/control-plane/onboarding/status", {{
            headers: authHeaders(),
          }});
          const payload = await response.json();
          if (!response.ok) throw new Error(payload.error || "status request failed");
          renderStatus(payload);
          renderProviders(payload.providers);
          resultEl.textContent = JSON.stringify(payload, null, 2);
        }} catch (error) {{
          resultEl.textContent = String(error);
        }}
      }}

      async function applySetup() {{
        state.token = getToken();
        resultEl.textContent = "Applying setup...";
        const payload = {{
          account: {{
            owner_name: document.getElementById("owner-name").value.trim(),
            owner_email: document.getElementById("owner-email").value.trim(),
            owner_github: document.getElementById("owner-github").value.trim(),
          }},
          access: {{
            allowed_user_ids: document.getElementById("allowed-users").value.trim(),
          }},
          provider: {{
            provider_id: providerSelect.value,
            auth_mode: authModeSelect.value,
            api_key: document.getElementById("provider-api-key").value.trim(),
            base_url: document.getElementById("provider-base-url").value.trim(),
            project_id: document.getElementById("provider-project-id").value.trim(),
          }},
          agent: {{
            agent_id: document.getElementById("agent-id").value.trim(),
            display_name: document.getElementById("agent-display-name").value.trim(),
            telegram_token: document.getElementById("agent-telegram-token").value.trim(),
          }},
        }};
        try {{
          const response = await fetch("/api/control-plane/onboarding/bootstrap", {{
            method: "POST",
            headers: authHeaders(),
            body: JSON.stringify(payload),
          }});
          const body = await response.json();
          if (!response.ok) throw new Error(body.error || "bootstrap failed");
          resultEl.textContent = JSON.stringify(body, null, 2);
          await refreshStatus();
        }} catch (error) {{
          resultEl.textContent = String(error);
        }}
      }}

      tokenInput.value = "";
      providerSelect.addEventListener("change", updateProviderHelp);
      authModeSelect.addEventListener("change", updateProviderHelp);
      document.getElementById("refresh-status").addEventListener("click", refreshStatus);
      document.getElementById("save-setup").addEventListener("click", applySetup);
      refreshStatus();
    </script>
  </body>
</html>
"""
