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
import os
import sys
import threading
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
DOCTOR = REPO_ROOT / "scripts" / "doctor.py"
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


def _write_env_file(tmp_path: Path, *, configured: str, port: int) -> Path:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                f"CONTROL_PLANE_API_TOKEN={configured}",
                "RUNTIME_LOCAL_UI_TOKEN=" + "r" * 64,
                # The control plane's port stands in for Postgres: only the TCP connect is probed.
                f"KNOWLEDGE_V2_POSTGRES_DSN=postgresql://koda:4b1f0c2e9d8a7f6e5d4c3b2a19081726@127.0.0.1:{port}/koda",
                "OBJECT_STORAGE_REQUIRED=false",
                f"STATE_ROOT_DIR={tmp_path / 'state'}",
                f"RUNTIME_EPHEMERAL_ROOT={tmp_path / 'runtime'}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return env_file


@pytest.mark.parametrize("configured", ["new-break-glass-token,old-break-glass-token"])
async def test_doctor_never_sends_the_bearer_through_an_http_proxy(
    control_plane: _ControlPlane, configured: str, tmp_path: Path
) -> None:
    """An http_proxy without a no_proxy entry for loopback would see the break-glass token in clear text.

    Doctor talks only to this install's control plane and dashboard, so it connects to them directly
    whatever the proxy settings say. The documented command runs doctor as a script, so the proxy
    variables are set before doctor is imported: an opener built from them at import time is caught too.
    """
    seen: list[tuple[str, str]] = []
    proxy = ThreadingHTTPServer(("127.0.0.1", 0), type("Proxy", (_RecordingProxy,), {"seen": seen}))
    thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    thread.start()
    try:
        proxy_url = f"http://127.0.0.1:{proxy.server_address[1]}"
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in PROXY_VARIABLES and key.lower() != "no_proxy" and key != "PYTHONPATH"
        }
        env.update({name: proxy_url for name in PROXY_VARIABLES})
        env["HOME"] = str(tmp_path / "home")
        env_file = _write_env_file(tmp_path, configured=configured, port=control_plane.server.port)
        # `python3 scripts/doctor.py --provider claude`, as docs/install/local.md runs it.
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-S",
            str(DOCTOR),
            "--env-file",
            str(env_file),
            "--base-url",
            control_plane.base_url,
            "--dashboard-url",
            control_plane.base_url,
            "--provider",
            "claude",
            cwd=str(tmp_path),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
    finally:
        proxy.shutdown()
        proxy.server_close()
        thread.join(timeout=5)

    payload = json.loads(stdout)
    assert seen == []
    assert [header for header in control_plane.received if header] == ["Bearer new-break-glass-token"]
    assert _check(payload, "provider_verification")["ok"] is True, stderr.decode()
    assert _check(payload, "control_plane_health")["ok"] is True
    assert _check(payload, "web_dashboard")["ok"] is True


class _RedirectingControlPlane:
    """A control plane whose authenticated onboarding/status answers a redirect.

    A forwarding server on 127.0.0.2 (another host) records what reaches it and answers
    like a control plane that accepts any bearer, so following the redirect would also
    report the provider as verified.
    """

    def __init__(self, base_url: str, received: list[str], forwarded: list[str]) -> None:
        self.base_url = base_url
        self.received = received
        self.forwarded = forwarded


@pytest.fixture
async def redirecting_control_plane(request: pytest.FixtureRequest) -> AsyncIterator[_RedirectingControlPlane]:
    target: str = request.param
    received: list[str] = []
    forwarded: list[str] = []

    async def stolen(req: web.Request) -> web.Response:
        forwarded.append(req.headers.get("Authorization", ""))
        return web.json_response(
            {"has_owner": True, "bootstrap_required": False, "providers": [{"provider_id": "claude", "verified": True}]}
        )

    other_host = web.Application()
    other_host.router.add_get("/steal", stolen)
    other_server = TestServer(other_host, host="127.0.0.2")
    await other_server.start_server()

    async def onboarding_status(req: web.Request) -> web.Response:
        authorization = req.headers.get("Authorization", "")
        received.append(authorization)
        if not authorization:
            return web.json_response({"has_owner": True, "bootstrap_required": False})
        location = (
            f"http://127.0.0.2:{other_server.port}/steal" if target == "other-host" else "/api/control-plane/steal"
        )
        raise web.HTTPFound(location)

    async def health(_req: web.Request) -> web.Response:
        return web.json_response({"status": "healthy"})

    async def dashboard(_req: web.Request) -> web.Response:
        # The dashboard sends `/` to the sign-in page; doctor still follows that.
        raise web.HTTPTemporaryRedirect("/login")

    async def login(_req: web.Request) -> web.Response:
        return web.Response(text="<html></html>", content_type="text/html")

    async def auth_status(_req: web.Request) -> web.Response:
        return web.json_response({"has_owner": True})

    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_get("/", dashboard)
    app.router.add_get("/login", login)
    app.router.add_get("/api/control-plane/onboarding/status", onboarding_status)
    app.router.add_get("/api/control-plane/steal", stolen)
    app.router.add_get("/api/control-plane/auth/status", auth_status)
    server = TestServer(app, host="127.0.0.1")
    await server.start_server()
    try:
        yield _RedirectingControlPlane(f"http://127.0.0.1:{server.port}", received, forwarded)
    finally:
        await server.close()
        await other_server.close()


@pytest.mark.parametrize("redirecting_control_plane", ["other-host", "same-host"], indirect=True)
async def test_doctor_never_sends_the_bearer_to_a_redirect(
    doctor: ModuleType, redirecting_control_plane: _RedirectingControlPlane
) -> None:
    """urllib copies Authorization onto a redirect to any host, so a 3xx could hand the bearer to another server.

    A control plane behind an SSO or edge proxy can answer 302 to an identity provider. Doctor
    sends the bearer to the URL it was given and to nothing else: it does not follow a redirect
    of a request that carries it, and the provider check fails and names the redirect instead
    of reporting what another server answered.
    """
    cp = redirecting_control_plane
    env = {
        "CONTROL_PLANE_API_TOKEN": "probe-break-glass-token-0123456789abcdef",
        "RUNTIME_LOCAL_UI_TOKEN": "r" * 64,
        "KNOWLEDGE_V2_POSTGRES_DSN": "postgresql://koda:4b1f0c2e9d8a7f6e5d4c3b2a19081726@127.0.0.1:5432/koda",
        "OBJECT_STORAGE_REQUIRED": "false",
    }
    payload = await asyncio.to_thread(
        doctor.run_doctor, env=env, base_url=cp.base_url, dashboard_url=cp.base_url, provider_id="claude"
    )

    assert [header for header in cp.received if header] == ["Bearer probe-break-glass-token-0123456789abcdef"]
    assert cp.forwarded == []
    provider = _check(payload, "provider_verification")
    assert provider["ok"] is False
    assert "redirect" in provider["error"]
    # A request without the bearer still follows a redirect: the dashboard answers `/` with one.
    assert _check(payload, "web_dashboard")["ok"] is True
    assert _check(payload, "onboarding_status")["ok"] is True


@pytest.fixture
async def redirect_to_other_host() -> AsyncIterator[tuple[str, list[str], list[str]]]:
    """`/start` on 127.0.0.1 answers a 302 to `/landing` on 127.0.0.2, and both record Authorization."""
    first_hop: list[str] = []
    second_hop: list[str] = []

    async def landing(req: web.Request) -> web.Response:
        second_hop.append(req.headers.get("Authorization", ""))
        return web.json_response({"landed": True})

    other_host = web.Application()
    other_host.router.add_get("/landing", landing)
    other_server = TestServer(other_host, host="127.0.0.2")
    await other_server.start_server()

    async def start(req: web.Request) -> web.Response:
        first_hop.append(req.headers.get("Authorization", ""))
        raise web.HTTPFound(f"http://127.0.0.2:{other_server.port}/landing")

    app = web.Application()
    app.router.add_get("/start", start)
    server = TestServer(app, host="127.0.0.1")
    await server.start_server()
    try:
        yield f"http://127.0.0.1:{server.port}/start", first_hop, second_hop
    finally:
        await server.close()
        await other_server.close()


async def test_doctor_attaches_credentials_as_unredirected_headers(
    doctor: ModuleType, redirect_to_other_host: tuple[str, list[str], list[str]]
) -> None:
    """The first of doctor's two protections: urllib never copies an unredirected header onto a redirect.

    test_doctor_never_sends_the_bearer_to_a_redirect covers the second (doctor refuses to redirect a
    request that carries credentials). This one opens doctor's request with urllib's default redirect
    handler, which follows the 302, so it still holds if a later change lets credentialed requests
    follow some redirects (a reverse proxy's trailing-slash 301, say).
    """
    from urllib.request import ProxyHandler, build_opener

    url, first_hop, second_hop = redirect_to_other_host
    request = doctor._request(url, {"Authorization": "Bearer probe-break-glass-token"})
    following_opener = build_opener(ProxyHandler({}))

    def follow() -> dict[str, Any]:
        with following_opener.open(request, timeout=10) as response:
            payload: dict[str, Any] = json.loads(response.read())
            return payload

    assert await asyncio.to_thread(follow) == {"landed": True}
    assert first_hop == ["Bearer probe-break-glass-token"]
    assert second_hop == [""]


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8090/api/control-plane/onboarding/status",
        "http://127.10.20.30:8090/api/control-plane/onboarding/status",
        "http://localhost:8090/api/control-plane/onboarding/status",
        "http://LOCALHOST.:8090/api/control-plane/onboarding/status",
        "http://[::1]:8090/api/control-plane/onboarding/status",
        "https://koda.example.com/api/control-plane/onboarding/status",
        "https://192.0.2.10:8090/api/control-plane/onboarding/status",
    ],
)
def test_doctor_attaches_credentials_over_https_or_to_this_host(doctor: ModuleType, url: str) -> None:
    request = doctor._request(url, {"Authorization": "Bearer probe-break-glass-token"})

    assert request.unredirected_hdrs == {"Authorization": "Bearer probe-break-glass-token"}


@pytest.mark.parametrize(
    "url",
    [
        "http://192.0.2.10:8090/api/control-plane/onboarding/status",
        "http://koda.example.com:8090/api/control-plane/onboarding/status",
        # Python resolves *.localhost through the system resolver, which does not promise loopback.
        "http://koda.localhost:8090/api/control-plane/onboarding/status",
        "http://0.0.0.0:8090/api/control-plane/onboarding/status",
        "http://[2001:db8::10]:8090/api/control-plane/onboarding/status",
        "HTTP://192.0.2.10:8090/api/control-plane/onboarding/status",
    ],
)
def test_doctor_refuses_to_attach_credentials_to_plain_http_off_this_host(doctor: ModuleType, url: str) -> None:
    with pytest.raises(ValueError, match="plain HTTP"):
        doctor._request(url, {"Authorization": "Bearer probe-break-glass-token"})
    # A request without credentials is not affected.
    assert doctor._request(url, None).full_url == url


class _RecordingOpener:
    """Stands in for doctor's opener: records each request, credentials included, and answers 200 JSON."""

    def __init__(self) -> None:
        self.seen: list[tuple[str, str]] = []

    def open(self, request: Any, timeout: float = 0.0) -> Any:
        headers = {**request.headers, **request.unredirected_hdrs}
        self.seen.append((request.full_url, headers.get("Authorization", "")))
        body = json.dumps(
            {"status": "healthy", "has_owner": True, "providers": [{"provider_id": "claude", "verified": True}]}
        ).encode()

        class _Response:
            status = 200
            headers = {"Content-Type": "application/json"}

            def read(self) -> bytes:
                return body

            def __enter__(self) -> _Response:
                return self

            def __exit__(self, *_exc: object) -> None:
                return None

        return _Response()


def test_doctor_provider_check_never_sends_the_bearer_in_clear_text_off_this_host(
    doctor: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--base-url http://<vps>:8090` from another machine would put the break-glass bearer on the network.

    The CLI only ever talks to loopback. Doctor sends the bearer to a plain-HTTP URL only on this
    host; for any other host the provider check fails, says why and how to run it instead, and the
    authenticated request is never made. The anonymous checks still run.
    """
    opener = _RecordingOpener()
    monkeypatch.setattr(doctor, "_DIRECT_OPENER", opener)
    env = {
        "CONTROL_PLANE_API_TOKEN": "probe-break-glass-token-0123456789abcdef",
        "RUNTIME_LOCAL_UI_TOKEN": "r" * 64,
        "KNOWLEDGE_V2_POSTGRES_DSN": "postgresql://koda:4b1f0c2e9d8a7f6e5d4c3b2a19081726@127.0.0.1:5432/koda",
        "OBJECT_STORAGE_REQUIRED": "false",
    }

    payload = doctor.run_doctor(
        env=env,
        base_url="http://192.0.2.10:8090",
        dashboard_url="http://192.0.2.10:3000",
        provider_id="claude",
    )

    assert opener.seen, "the anonymous checks still reach the control plane"
    assert [authorization for _url, authorization in opener.seen if authorization] == []
    provider = _check(payload, "provider_verification")
    assert provider["ok"] is False
    assert "plain HTTP" in provider["error"]
    assert "192.0.2.10" in provider["error"]
    assert "--base-url http://127.0.0.1:8090" in provider["error"]
    assert "probe-break-glass-token" not in json.dumps(payload)
    assert _check(payload, "control_plane_health")["ok"] is True
    assert _check(payload, "onboarding_status")["ok"] is True
    assert payload["ok"] is False
