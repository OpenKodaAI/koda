"""`scripts/doctor.py` reads CONTROL_PLANE_API_TOKEN as the control plane does.

During a rotation `.env` holds a comma-separated list (`new-token,old-token`,
see `.env.example`). The control plane accepts each token of the list on its
own and never an unedited `replace-with-...` placeholder (``parse_api_tokens``).
So doctor's token check passes while one usable token remains, and
`--provider` sends one usable token, never the raw list.

The server below answers onboarding/status the way the control plane does:
anonymous callers get only the public fields, and the provider rows go only to
a caller whose bearer is one of the configured tokens.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import threading
import urllib.request
from collections.abc import AsyncIterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any, ClassVar

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from koda.control_plane.settings import parse_api_tokens

REPO_ROOT = Path(__file__).resolve().parent.parent
PROXY_VARIABLES = ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY", "all_proxy", "ALL_PROXY")


@pytest.fixture
def doctor(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location("doctor_under_test", REPO_ROOT / "scripts" / "doctor.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Only the HTTP calls to the control plane matter here.
    monkeypatch.setattr(module, "check_socket", lambda host, port, **_kw: {"ok": True, "host": host, "port": port})
    monkeypatch.setattr(module, "build_sandbox_doctor", lambda _env: {"status": "passed", "checks": []})
    for name in PROXY_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    return module


class _ControlPlane:
    def __init__(self, server: TestServer, received: list[str]) -> None:
        self.server = server
        self.received = received

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server.port}"


@pytest.fixture
async def control_plane(request: pytest.FixtureRequest) -> AsyncIterator[_ControlPlane]:
    configured: str = request.node.callspec.params["configured"]
    accepted, _ignored = parse_api_tokens(configured)
    received: list[str] = []

    async def onboarding_status(req: web.Request) -> web.Response:
        authorization = req.headers.get("Authorization", "")
        received.append(authorization)
        payload: dict[str, Any] = {"has_owner": True, "bootstrap_required": False}
        if authorization.removeprefix("Bearer ") in accepted:
            payload["providers"] = [{"provider_id": "claude", "verified": True}]
        return web.json_response(payload)

    async def health(_req: web.Request) -> web.Response:
        return web.json_response({"status": "healthy"})

    async def dashboard(_req: web.Request) -> web.Response:
        return web.Response(text="<html></html>", content_type="text/html")

    async def auth_status(_req: web.Request) -> web.Response:
        return web.json_response({"has_owner": True})

    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_get("/", dashboard)
    app.router.add_get("/api/control-plane/onboarding/status", onboarding_status)
    app.router.add_get("/api/control-plane/auth/status", auth_status)
    server = TestServer(app, host="127.0.0.1")
    await server.start_server()
    try:
        yield _ControlPlane(server, received)
    finally:
        await server.close()


def _check(payload: dict[str, Any], name: str) -> dict[str, Any]:
    return next(check for check in payload["checks"] if check["name"] == name)


async def _run_doctor(doctor: ModuleType, control_plane: _ControlPlane, configured: str) -> dict[str, Any]:
    env = {
        "CONTROL_PLANE_API_TOKEN": configured,
        "RUNTIME_LOCAL_UI_TOKEN": "r" * 64,
        "KNOWLEDGE_V2_POSTGRES_DSN": "postgresql://koda:4b1f0c2e9d8a7f6e5d4c3b2a19081726@127.0.0.1:5432/koda",
        "OBJECT_STORAGE_REQUIRED": "false",
    }
    # Doctor's HTTP client blocks, and the server runs on this event loop.
    return await asyncio.to_thread(
        doctor.run_doctor,
        env=env,
        base_url=control_plane.base_url,
        dashboard_url=control_plane.base_url,
        provider_id="claude",
    )


@pytest.mark.parametrize(
    ("configured", "expected_bearer"),
    [
        ("new-recovery-token,old-recovery-token", "new-recovery-token"),
        (" new-recovery-token , old-recovery-token ", "new-recovery-token"),
        # The control plane never accepts an unedited placeholder, whatever its case.
        ("Replace-With-a-random-token,new-recovery-token", "new-recovery-token"),
        ("only-recovery-token", "only-recovery-token"),
    ],
    ids=["new-old-rotation", "spaces-around-tokens", "placeholder-first", "single-token"],
)
async def test_doctor_provider_check_sends_one_token_of_the_configured_list(
    doctor: ModuleType, control_plane: _ControlPlane, configured: str, expected_bearer: str
) -> None:
    payload = await _run_doctor(doctor, control_plane, configured)

    # The public onboarding check goes out anonymously; only the provider check authenticates.
    assert [header for header in control_plane.received if header] == [f"Bearer {expected_bearer}"]
    assert _check(payload, "provider_verification")["ok"] is True
    assert _check(payload, "control_plane_api_token")["ok"] is True
    assert payload["ok"] is True


@pytest.mark.parametrize("configured", ["replace-with-a-random-token", " , "], ids=["placeholder", "empty-list"])
async def test_doctor_without_a_usable_token_fails_the_token_check_and_sends_none(
    doctor: ModuleType, control_plane: _ControlPlane, configured: str
) -> None:
    payload = await _run_doctor(doctor, control_plane, configured)

    assert [header for header in control_plane.received if header] == []
    assert _check(payload, "control_plane_api_token")["ok"] is False
    assert _check(payload, "provider_verification")["ok"] is False
    assert payload["ok"] is False


@pytest.mark.parametrize(
    "configured",
    [
        "",
        " , ",
        "only-token",
        "new-token,old-token",
        " new-token , , old-token ",
        "replace-with-a-random-token,new-token",
        "REPLACE-WITH-x,Replace-With-y",
        "new-token,replace-with-a-random-token",
    ],
)
def test_doctor_splits_the_token_list_as_the_control_plane_does(doctor: ModuleType, configured: str) -> None:
    """Doctor runs without Koda's dependencies, so it keeps its own copy of parse_api_tokens."""
    accepted, _ignored = parse_api_tokens(configured)

    assert doctor.api_tokens(configured) == accepted


class _RecordingProxy(BaseHTTPRequestHandler):
    """A forward HTTP proxy that records what it is sent and answers like a healthy control plane."""

    seen: ClassVar[list[tuple[str, str]]]

    def do_GET(self) -> None:
        self.seen.append((self.path, self.headers.get("Authorization", "")))
        body = json.dumps(
            {"status": "healthy", "has_owner": True, "providers": [{"provider_id": "claude", "verified": True}]}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: Any) -> None:
        pass


@pytest.mark.parametrize("configured", ["new-break-glass-token,old-break-glass-token"])
async def test_doctor_never_sends_the_bearer_through_an_http_proxy(
    doctor: ModuleType, control_plane: _ControlPlane, configured: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An http_proxy without a no_proxy entry for loopback would see the break-glass token in clear text.

    Doctor talks only to this install's control plane and dashboard, so it connects to them directly
    whatever the proxy settings say.
    """
    seen: list[tuple[str, str]] = []
    proxy = ThreadingHTTPServer(("127.0.0.1", 0), type("Proxy", (_RecordingProxy,), {"seen": seen}))
    thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    thread.start()
    try:
        proxy_url = f"http://127.0.0.1:{proxy.server_address[1]}"
        for name in PROXY_VARIABLES:
            monkeypatch.setenv(name, proxy_url)
        for name in ("no_proxy", "NO_PROXY"):
            monkeypatch.delenv(name, raising=False)
        # urlopen keeps the opener it built from the environment on first use; start from none.
        monkeypatch.setattr(urllib.request, "_opener", None)

        payload = await _run_doctor(doctor, control_plane, configured)
    finally:
        proxy.shutdown()
        proxy.server_close()
        thread.join(timeout=5)

    assert seen == []
    assert [header for header in control_plane.received if header] == ["Bearer new-break-glass-token"]
    assert _check(payload, "provider_verification")["ok"] is True
    assert _check(payload, "control_plane_health")["ok"] is True
    assert _check(payload, "web_dashboard")["ok"] is True
