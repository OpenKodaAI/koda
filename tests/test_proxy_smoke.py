"""The bundled reverse proxy in a real nginx (``scripts/proxy_smoke.py``, ``scripts/docker_smoke.sh``).

The CI docker-smoke jobs load ``packages/cli/release/bundle/proxy/nginx.conf`` into a pinned nginx in
front of the Compose stack and run ``scripts/proxy_smoke.py check`` through it. The tests below hold
that wiring in place and run the same checks through a real nginx here, in front of two stand-ins
for the dashboard and the API. The stand-ins answer the way the real services do wherever the
checks tell the two apart (apps/web/src/proxy.ts, the dashboard's auth routes, the relay in
apps/web/src/lib/runtime-relay-server.mjs; koda/control_plane/api.py), so a request routed to the
wrong one fails.

The real-nginx tests need an nginx binary: ``KODA_TEST_NGINX``, else ``nginx`` on PATH or
``/usr/sbin/nginx``. Without one they skip. The docker smoke runs ``proxy_smoke.run_checks``
through the pinned nginx in CI, against the real stack: the routing checks, and the body limits
(a 12 MiB API-token photo upload with a Content-Length and chunked, and nginx's 413 for a body over
1 MiB to the sign-in route and to a photo route without a token). The cases only these tests run
are the extra body-limit ones in test_the_bundled_proxy_passes_the_largest_upload_in_a_real_nginx
(the room photo route, a session cookie, a body over the photo limit, the internal upload location
and the paths next to the photo routes), the previous template, and the extra Host checks (a page
without a Host, a Host with a port); tests/test_release_proxy_routing.py checks the config's shape
for every route either way.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import secrets
import shutil
import socket
import subprocess
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from aiohttp import HttpVersion11, web

import scripts.proxy_smoke as proxy_smoke
from tests._owned_process import spawn_owned, stop_owned

Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]

ROOT = Path(__file__).resolve().parents[1]
DOCKER_SMOKE = ROOT / "scripts" / "docker_smoke.sh"
TEMPLATE = ROOT / "packages" / "cli" / "release" / "bundle" / "proxy" / "nginx.conf"

# The template this task replaced (before M1-E1-T16): /setup, /api/control-plane/* and
# /api/runtime/* went straight to the API. The smoke must reject it.
PREVIOUS_TEMPLATE = """\
server {
    listen 80;
    server_name _;

    location = /setup {
        proxy_pass http://127.0.0.1:8090/setup;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /api/control-plane/ {
        proxy_pass http://127.0.0.1:8090;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /api/runtime/ {
        proxy_pass http://127.0.0.1:8090;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location = /openapi/control-plane.json {
        proxy_pass http://127.0.0.1:8090/openapi/control-plane.json;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
"""


# ---------------------------------------------------------------------------
# The docker smoke runs the bundled config through a real nginx
# ---------------------------------------------------------------------------


def test_docker_smoke_runs_the_bundled_proxy_in_a_pinned_nginx() -> None:
    script = DOCKER_SMOKE.read_text(encoding="utf-8")

    assert 'PROXY_TEMPLATE="packages/cli/release/bundle/proxy/nginx.conf"' in script
    assert 'python3 scripts/proxy_smoke.py render --listen "127.0.0.1:${PROXY_PORT}" "${PROXY_TEMPLATE}"' in script
    # An exact version and its digest, overridable for local runs.
    assert 'PROXY_IMAGE="${PROXY_IMAGE:-nginx:1.30.6-alpine@sha256:' in script
    # The config replaces the image's stock site, in the http context, on the host network in front
    # of the loopback ports the stack publishes; nginx -t must accept it before the proxy starts.
    mount = '-v "${config}:/etc/nginx/conf.d/default.conf:ro"'
    assert script.count(mount) == 2
    assert '"${PROXY_IMAGE}" nginx -t' in script
    assert script.count("--network host") == 2
    assert 'wait_for_url "bundled proxy" "http://127.0.0.1:${PROXY_PORT}/api/health"' in script
    assert "control_plane/bootstrap.txt" in script
    assert (
        'python3 scripts/proxy_smoke.py check \\\n    --proxy-url "http://127.0.0.1:${PROXY_PORT}" --env-file .env'
        in script
    )
    # It runs on every smoke, after the stack is verified, and the proxy is always removed.
    main = script[script.index("main() {") :]
    assert main.index("verify_dashboard_is_trusted_by_api") < main.index("verify_bundled_proxy")
    assert main.index("verify_bundled_proxy") < main.index("stack passed endpoint verification")
    assert "stop_bundled_proxy; exit" in main
    assert 'docker logs "${PROXY_CONTAINER}"' in script


def test_the_checks_cover_browser_login_the_relay_and_api_token_calls() -> None:
    names = [result.name for result in proxy_smoke.run_checks("http://127.0.0.1:9", api_token="", bootstrap_code="")]

    assert names == [
        "browser: GET /setup is the dashboard",
        "browser: GET /login is the dashboard",
        "browser: API call without a session gets the dashboard's 401",
        "browser: owner registration with the bootstrap code",
        "browser: login",
        "browser: API call with the session cookie",
        "relay: WebSocket upgrade reaches the dashboard relay",
        "api-token: GET /api/control-plane/agents",
        "api-token: POST with a body",
        "api-token: a 12 MiB photo upload reaches the API",
        "api: GET /openapi/control-plane.json",
        "health: HTTP/1.0 request without a Host reaches the dashboard",
        "body limit: a sign-in body over 1 MiB gets nginx's 413",
        "body limit: a photo over 1 MiB without an API token gets nginx's 413",
    ]


def test_the_body_limit_checks_follow_the_app_and_nginx() -> None:
    """The smoke is standard-library only, so it keeps its own copy of the limits; they must agree."""
    from koda.control_plane import operator_profile_photos
    from koda.control_plane.operator_profile_photos import InvalidProfilePhotoError, save_operator_profile_photo

    assert proxy_smoke.LARGEST_PHOTO_BYTES == operator_profile_photos.MAX_INPUT_BYTES
    # nginx's client_max_body_size when the config sets none, which every dashboard request keeps.
    assert proxy_smoke.DEFAULT_BODY_LIMIT_BYTES == 1024 * 1024
    # The smoke's photo is no image: the API refuses it with this answer, before it stores anything.
    body, _ = proxy_smoke.multipart_photo(64)
    with pytest.raises(InvalidProfilePhotoError) as refused:
        save_operator_profile_photo("proxy-smoke", body)
    assert str(refused.value).startswith(proxy_smoke.API_UNDECODABLE_PHOTO)


def test_render_replaces_the_listen_address_and_upstreams() -> None:
    template = TEMPLATE.read_text(encoding="utf-8")

    rendered = proxy_smoke.render(template, listen="127.0.0.1:18080")
    assert "listen 127.0.0.1:18080;" in rendered
    assert "listen 80;" not in rendered
    assert rendered.replace("listen 127.0.0.1:18080;", "listen 80;") == template

    moved = proxy_smoke.render(template, listen="127.0.0.1:1", dashboard="127.0.0.1:2", api="127.0.0.1:3")
    assert "127.0.0.1:3000" not in moved
    assert "127.0.0.1:8090" not in moved
    assert moved.count("http://127.0.0.1:2") == template.count("http://127.0.0.1:3000")
    assert moved.count("http://127.0.0.1:3") == template.count("http://127.0.0.1:8090")


def test_render_refuses_a_template_it_cannot_rewrite() -> None:
    with pytest.raises(ValueError, match="listen 80;"):
        proxy_smoke.render("server { listen 443 ssl; }", listen="127.0.0.1:1")
    with pytest.raises(ValueError, match="127.0.0.1:8090"):
        proxy_smoke.render("server { listen 80; }", listen="127.0.0.1:1", api="127.0.0.1:2")


def test_read_env_file_finds_the_api_token(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("# comment\nCONTROL_PLANE_API_TOKENS=other\nCONTROL_PLANE_API_TOKEN='abc123'\n", encoding="utf-8")

    assert proxy_smoke.read_env_file(env, "CONTROL_PLANE_API_TOKEN") == "abc123"
    assert proxy_smoke.read_env_file(env, "MISSING") == ""


# ---------------------------------------------------------------------------
# Stand-ins for the dashboard and the API
# ---------------------------------------------------------------------------


@dataclass
class Stack:
    bootstrap_code: str = field(default_factory=lambda: secrets.token_hex(6))
    api_token: str = field(default_factory=lambda: secrets.token_hex(16))
    owner: tuple[str, str] | None = None
    api_sessions: set[str] = field(default_factory=set)
    dashboard_sessions: set[str] = field(default_factory=set)
    # (upstream, method, path, headers) of every request that reached an upstream.
    seen: list[tuple[str, str, str, dict[str, str]]] = field(default_factory=list)
    # (upstream, path, bytes read) of every photo upload body an upstream read.
    uploads: list[tuple[str, str, int]] = field(default_factory=list)

    def remember(self, upstream: str, request: web.Request) -> None:
        self.seen.append((upstream, request.method, request.path_qs, dict(request.headers)))

    def sign_in(self, email: str, password: str) -> str | None:
        if self.owner != (email, password):
            return None
        token = secrets.token_hex(8)
        self.api_sessions.add(token)
        return token


def _json(payload: object, status: int = 200) -> web.Response:
    return web.json_response(payload, status=status, headers={"Cache-Control": "no-store"})


def dashboard_app(stack: Stack) -> web.Application:
    """apps/web: pages, the session-cookie gate, the auth routes and the relay."""

    @web.middleware
    async def require_host(request: web.Request, handler: Handler) -> web.StreamResponse:
        # apps/web/src/lib/dashboard-server.mjs serves through Node's http.createServer with
        # `requireHostHeader` left on: an HTTP/1.1 request without Host gets 400 before any route.
        if request.version >= HttpVersion11 and "Host" not in request.headers:
            return web.Response(status=400, headers={"Connection": "close"})
        return await handler(request)

    async def page(request: web.Request) -> web.Response:
        stack.remember("dashboard", request)
        return web.Response(
            text='<html><script src="/_next/static/chunks/main.js"></script></html>', content_type="text/html"
        )

    async def health(request: web.Request) -> web.Response:
        return _json({"status": "ok"})

    def same_origin(request: web.Request) -> bool:
        # apps/web/src/lib/request-origin.ts: Origin must equal X-Forwarded-Proto://Host.
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        proto = request.headers.get("X-Forwarded-Proto", "http").split(",")[0].strip()
        return request.headers.get("Origin") == f"{proto}://{request.headers.get('Host', '')}"

    def signed_in(response: web.Response, api_session: str) -> web.Response:
        sealed = secrets.token_hex(8)
        stack.dashboard_sessions.add(sealed)
        response.set_cookie(proxy_smoke.SESSION_COOKIE, sealed, httponly=True, secure=True, samesite="Strict", path="/")
        response.set_cookie("koda_owner_exists", "1", path="/")
        return response

    async def control_plane(request: web.Request) -> web.Response:
        stack.remember("dashboard", request)
        if not same_origin(request):
            return _json({"error": "Cross-site dashboard mutations are blocked."}, 403)
        path = request.match_info["path"]
        if path == "auth/register-owner" and request.method == "POST":
            body = await request.json()
            if body.get("bootstrap_code") != stack.bootstrap_code:
                return _json({"error": "Invalid setup code."}, 400)
            stack.owner = (body["email"], body["password"])
            token = stack.sign_in(*stack.owner)
            assert token
            return signed_in(_json({"ok": True, "recovery_codes": ["AAAA-BBBB-CCCC"]}, 201), token)
        if path == "auth/login" and request.method == "POST":
            body = await request.json()
            token = stack.sign_in(body.get("identifier", ""), body.get("password", ""))
            if token is None:
                return _json({"error": "Invalid credentials."}, 401)
            return signed_in(_json({"ok": True, "auth": None}), token)
        if request.cookies.get(proxy_smoke.SESSION_COOKIE) not in stack.dashboard_sessions:
            return _json({"error": "Operator session is required."}, 401)
        return _json([])

    def relay_page_origin(request: web.Request) -> str | None:
        # dashboardOrigin in apps/web/src/lib/runtime-relay-server.mjs: the first X-Forwarded-Proto
        # entry (ws and wss read as http and https), else http, then the Host, lowercased.
        host = request.headers.get("Host", "")
        if not host:
            return None
        proto = request.headers.get("X-Forwarded-Proto", "").split(",")[0].strip().lower() or "http"
        scheme = {"wss": "https", "ws": "http"}.get(proto, proto)
        return f"{scheme}://{host.lower()}"

    async def relay(request: web.Request) -> web.Response:
        stack.remember("dashboard", request)
        connection = {token.strip().lower() for token in request.headers.get("Connection", "").split(",")}
        if request.headers.get("Upgrade", "").lower() != "websocket" or "upgrade" not in connection:
            # server.mjs refuses only in its "upgrade" event; a plain GET goes to Next.js, where
            # proxy.ts answers 401 without a session (the smoke sends none to the relay).
            response = _json({"error": "Operator session is required."}, 401)
            response.headers["Cache-Control"] = "no-store"
            return response
        # authorizeRelayUpgrade and refuseUpgrade in apps/web/src/lib/runtime-relay-server.mjs, before
        # any WebSocket work: 403 unless the Origin is the page's, then 404 for an unknown relay id
        # (no relay is attached here), each with no body and `Connection: close`.
        origin = request.headers.get("Origin")
        expected = relay_page_origin(request)
        status = 404 if origin is not None and expected is not None and origin.lower() == expected else 403
        return web.Response(status=status, headers={"Connection": "close"})

    app = web.Application(middlewares=[require_host])
    app.router.add_get("/api/health", health)
    for path in ("/", "/setup", "/login"):
        app.router.add_get(path, page)
    app.router.add_route("*", "/api/control-plane/{path:.*}", control_plane)
    app.router.add_get("/api/runtime/relay/{relay_id}", relay)
    return app


def api_app(stack: Stack) -> web.Application:
    """koda/control_plane/api.py: bearer-token auth, a legacy /setup page, no /api/runtime/*."""

    async def setup_page(request: web.Request) -> web.Response:
        stack.remember("api", request)
        return web.Response(text="<html><body>Koda control plane setup</body></html>", content_type="text/html")

    async def openapi(request: web.Request) -> web.Response:
        stack.remember("api", request)
        return _json({"openapi": "3.1.0", "paths": {"/api/control-plane/agents": {}}})

    async def control_plane(request: web.Request) -> web.Response:
        stack.remember("api", request)
        path = request.match_info["path"]
        if path == "auth/profile/photo" and request.method == "POST":
            # The API reads the whole multipart body, then checks the token and decodes the photo.
            size = 0
            async for chunk in request.content.iter_chunked(64 * 1024):
                size += len(chunk)
            stack.uploads.append(("api", request.path, size))
            if request.headers.get("Authorization", "").removeprefix("Bearer ").strip() != stack.api_token:
                return _json({"error": "operator session is required"}, 400)
            return _json({"error": f"{proxy_smoke.API_UNDECODABLE_PHOTO}: cannot identify image file"}, 400)
        if path in ("auth/login", "auth/register-owner") and request.method == "POST":
            body = await request.json()
            if path == "auth/register-owner":
                if body.get("bootstrap_code") != stack.bootstrap_code:
                    return _json({"error": "invalid bootstrap code"}, 400)
                stack.owner = (body["email"], body["password"])
                identifier, password = stack.owner
            else:
                identifier, password = body.get("identifier", ""), body.get("password", "")
            token = stack.sign_in(identifier, password)
            if token is None:
                return _json({"error": "invalid credentials"}, 401)
            return _json({"session_token": token, "auth": {}, "recovery_codes": ["AAAA-BBBB-CCCC"]})
        bearer = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if bearer != stack.api_token and bearer not in stack.api_sessions:
            return _json({"error": "operator session is required"}, 401)
        return _json([])

    app = web.Application()
    app.router.add_get("/setup", setup_page)
    app.router.add_get("/openapi/control-plane.json", openapi)
    app.router.add_route("*", "/api/control-plane/{path:.*}", control_plane)
    return app


@asynccontextmanager
async def serve(app: web.Application) -> AsyncIterator[str]:
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    try:
        host, port = runner.addresses[0][:2]
        yield f"{host}:{port}"
    finally:
        await runner.cleanup()


# ---------------------------------------------------------------------------
# A real nginx
# ---------------------------------------------------------------------------


def _nginx_binary() -> str | None:
    configured = os.environ.get("KODA_TEST_NGINX", "").strip()
    if configured:
        return configured
    return shutil.which("nginx") or ("/usr/sbin/nginx" if os.access("/usr/sbin/nginx", os.X_OK) else None)


@pytest.fixture(scope="module")
def nginx_binary() -> str:
    binary = _nginx_binary()
    if binary is None:
        pytest.skip("no nginx binary (set KODA_TEST_NGINX); the docker smoke runs proxy_smoke.run_checks in CI")
    return binary


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@contextmanager
def running_nginx(binary: str, workdir: Path, site_config: str) -> Iterator[str]:
    """Run *site_config* in nginx's http context, as /etc/nginx/conf.d/koda.conf would be, and yield its URL."""
    port = _free_port()
    site = workdir / "koda.conf"
    site.write_text(proxy_smoke.render(site_config, listen=f"127.0.0.1:{port}"), encoding="utf-8")
    temp = workdir / "temp"
    temp.mkdir()
    main = workdir / "nginx.conf"
    main.write_text(
        f"""
daemon off;
master_process off;
pid {workdir}/nginx.pid;
error_log {workdir}/error.log info;
events {{ worker_connections 64; }}
http {{
    access_log {workdir}/access.log;
    client_body_temp_path {temp}/body;
    proxy_temp_path {temp}/proxy;
    fastcgi_temp_path {temp}/fastcgi;
    uwsgi_temp_path {temp}/uwsgi;
    scgi_temp_path {temp}/scgi;
    include {site};
}}
""",
        encoding="utf-8",
    )
    command = [binary, "-p", str(workdir), "-c", str(main)]
    syntax = subprocess.run([*command, "-t"], capture_output=True, text=True, check=False)
    assert syntax.returncode == 0, syntax.stderr

    process = spawn_owned(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        deadline = time.monotonic() + 15
        while True:
            assert process.poll() is None, process.communicate()[0]
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    break
            except OSError:
                assert time.monotonic() < deadline, "nginx did not start listening"
                time.sleep(0.05)
        yield f"http://127.0.0.1:{port}"
    finally:
        stop_owned(process)


@asynccontextmanager
async def proxied_stack(binary: str, workdir: Path, template: str) -> AsyncIterator[tuple[Stack, str]]:
    """Run *template* in a real nginx in front of the stand-ins; yield them and the proxy URL."""
    stack = Stack()
    async with serve(dashboard_app(stack)) as dashboard, serve(api_app(stack)) as api:
        moved = template.replace(proxy_smoke.TEMPLATE_DASHBOARD, f"http://{dashboard}").replace(
            proxy_smoke.TEMPLATE_API, f"http://{api}"
        )
        with running_nginx(binary, workdir, moved) as proxy_url:
            yield stack, proxy_url


async def _smoke(binary: str, workdir: Path, template: str) -> tuple[Stack, list[proxy_smoke.Result]]:
    async with proxied_stack(binary, workdir, template) as (stack, proxy_url):
        results = await asyncio.to_thread(
            proxy_smoke.run_checks, proxy_url, api_token=stack.api_token, bootstrap_code=stack.bootstrap_code
        )
    return stack, results


async def test_the_relay_check_tells_the_dashboard_relay_from_the_api() -> None:
    """The relay check passes against the dashboard's relay and fails against the API, without nginx.

    The relay refuses an upgrade for an unknown relay id before the handshake, with an empty 404 for
    the page's Origin and an empty 403 for a foreign one; the API has no /api/runtime/relay/* route.
    """
    stack = Stack()
    async with serve(dashboard_app(stack)) as dashboard, serve(api_app(stack)) as api:
        detail = await asyncio.to_thread(proxy_smoke._relay_websocket, proxy_smoke.Proxy(f"http://{dashboard}"))
        with pytest.raises(proxy_smoke.CheckFailed, match="expected the relay's empty 404"):
            await asyncio.to_thread(proxy_smoke._relay_websocket, proxy_smoke.Proxy(f"http://{api}"))

    assert detail.startswith("404 for an unknown relay id, 403 for a foreign Origin")
    upgrades = [headers for upstream, _, path, headers in stack.seen if path.startswith("/api/runtime/relay/")]
    assert [headers["Origin"] for headers in upgrades] == [f"http://{dashboard}", "http://evil.example"]
    for headers in upgrades:
        assert headers["Upgrade"] == "websocket"
        assert headers["Connection"] == "Upgrade"
        assert headers["Sec-WebSocket-Version"] == "13"
        assert len(base64.b64decode(headers["Sec-WebSocket-Key"])) == 16


class _DropsTheUpgrade(proxy_smoke.Proxy):
    """Sends what a proxy location without the Upgrade headers forwards: no Upgrade, `Connection: close`."""

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: object | None = None,
    ) -> proxy_smoke.Response:
        kept = {name: value for name, value in (headers or {}).items() if name not in ("Upgrade", "Connection")}
        return super().request(method, path, headers={**kept, "Connection": "close"}, body=body)


async def test_the_relay_check_fails_when_the_upgrade_headers_are_dropped() -> None:
    """Without the Upgrade headers a relay path is a plain request, so proxy.ts answers it, not the relay.

    server.mjs refuses only upgrades; a plain GET goes to Next.js, where proxy.ts answers 401 without a
    session. A proxy location that forwards no Upgrade (the bundled `/api/runtime/` one) fails the check.
    """
    stack = Stack()
    async with serve(dashboard_app(stack)) as dashboard:
        plain = await asyncio.to_thread(
            proxy_smoke.Proxy(f"http://{dashboard}").request, "GET", f"{proxy_smoke.RELAY_PATH_PREFIX}unknown"
        )
        with pytest.raises(proxy_smoke.CheckFailed, match="got HTTP 401 .*Operator session is required"):
            await asyncio.to_thread(proxy_smoke._relay_websocket, _DropsTheUpgrade(f"http://{dashboard}"))

    assert (plain.status, plain.json()) == (401, {"error": "Operator session is required."})
    assert plain.headers.get("Cache-Control") == "no-store"


async def test_the_bundled_proxy_passes_the_smoke_in_a_real_nginx(nginx_binary: str, tmp_path: Path) -> None:
    stack, results = await _smoke(nginx_binary, tmp_path, TEMPLATE.read_text(encoding="utf-8"))

    assert [(result.name, result.detail) for result in results if not result.ok] == []

    # Each check reached the upstream it names, with the method, Host and X-Forwarded-For nginx sent.
    reached = [(upstream, method, path) for upstream, method, path, _ in stack.seen]
    assert ("dashboard", "POST", "/api/control-plane/auth/register-owner") in reached
    assert ("dashboard", "POST", "/api/control-plane/auth/login") in reached
    assert ("api", "POST", "/api/control-plane/auth/login") in reached
    assert ("api", "GET", "/api/control-plane/agents") in reached
    assert ("api", "GET", "/openapi/control-plane.json") in reached
    assert [path for upstream, _, path in reached if upstream == "api"] == [
        "/api/control-plane/agents",
        "/api/control-plane/auth/login",
        proxy_smoke.PROFILE_PHOTO_PATH,
        proxy_smoke.PROFILE_PHOTO_PATH,
        "/openapi/control-plane.json",
    ]
    # The API read both 12 MiB photos whole, sent with a Content-Length and chunked; no body over
    # 1 MiB reached the dashboard.
    photo, _ = proxy_smoke.multipart_photo(proxy_smoke.LARGEST_PHOTO_BYTES)
    assert stack.uploads == [("api", proxy_smoke.PROFILE_PHOTO_PATH, len(photo))] * 2
    assert ("dashboard", "POST", proxy_smoke.PROFILE_PHOTO_PATH) not in reached
    assert any(upstream == "dashboard" and path.startswith("/api/runtime/relay/") for upstream, _, path in reached)
    for _, _, _, headers in stack.seen:
        assert headers["X-Forwarded-For"] == "127.0.0.1"
        assert headers["Host"].startswith("127.0.0.1:")


async def test_the_bundled_proxy_serves_requests_without_host_in_a_real_nginx(
    nginx_binary: str, tmp_path: Path
) -> None:
    """An HTTP/1.0 request may carry no Host; HAProxy's default `option httpchk` health check is one.

    nginx proxies it as HTTP/1.1, which the dashboard refuses without a Host. `$http_host` is empty
    then, so the template falls back to the server name; a browser's Host still keeps its port.
    """
    template = TEMPLATE.read_text(encoding="utf-8")
    async with proxied_stack(nginx_binary, tmp_path, template) as (stack, proxy_url):
        proxy = proxy_smoke.Proxy(proxy_url)
        health = await asyncio.to_thread(proxy.raw_request, b"GET /api/health HTTP/1.0\r\n\r\n")
        page = await asyncio.to_thread(proxy.raw_request, b"GET /login HTTP/1.0\r\n\r\n")
        browser = await asyncio.to_thread(
            proxy.raw_request, b"GET /login HTTP/1.1\r\nHost: koda.example.com:8443\r\nConnection: close\r\n\r\n"
        )

    assert (health.status, json.loads(health.body)) == (200, {"status": "ok"})
    assert page.status == 200
    assert browser.status == 200
    hosts = [headers.get("Host") for upstream, _, path, headers in stack.seen if path == "/login"]
    # The template's `server_name _;`; an operator's own server_name takes its place.
    assert hosts == ["_", "koda.example.com:8443"]


async def test_the_smoke_rejects_the_previous_template(nginx_binary: str, tmp_path: Path) -> None:
    _, results = await _smoke(nginx_binary, tmp_path, PREVIOUS_TEMPLATE)

    failed = {result.name for result in results if not result.ok}
    assert failed == {
        # /setup came from the API, browser calls reached the API without the cookie exchange, and the
        # relay upgrade met the API, which has no /api/runtime/* routes.
        "browser: GET /setup is the dashboard",
        "browser: API call without a session gets the dashboard's 401",
        "browser: owner registration with the bootstrap code",
        "browser: login",
        "browser: API call with the session cookie",
        "relay: WebSocket upgrade reaches the dashboard relay",
        "api-token: POST with a body",
        # nginx's default of 1m everywhere: the API never saw a 12 MiB photo.
        "api-token: a 12 MiB photo upload reaches the API",
    }


# ---------------------------------------------------------------------------
# Upload size
# ---------------------------------------------------------------------------


def _upload_app(upstream: str, received: list[tuple[str, str, int]]) -> web.Application:
    """Reads the whole body, as the photo routes in koda/control_plane/api.py do, and records its size."""

    async def receive(request: web.Request) -> web.Response:
        size = 0
        async for chunk in request.content.iter_chunked(64 * 1024):
            size += len(chunk)
        received.append((upstream, request.path_qs, size))
        return _json({"received": size})

    app = web.Application()
    app.router.add_post("/{path:.*}", receive)
    return app


def _post(proxy_url: str, path: str, body: bytes, headers: dict[str, str], *, chunked: bool = False) -> int:
    """POST *body* with a Content-Length, or with ``chunked=True`` as a chunked body (no length declared)."""
    response = proxy_smoke.Proxy(proxy_url, timeout=60).post_bytes(path, body, headers=headers, chunked=chunked)
    if response.status == 413:
        # nginx's own answer, not an upstream's: the refused body reached neither.
        assert proxy_smoke.NGINX_TOO_LARGE in response.body, response.summary()
    return response.status


async def test_the_bundled_proxy_passes_the_largest_upload_in_a_real_nginx(nginx_binary: str, tmp_path: Path) -> None:
    """Only an API-token photo upload takes more than nginx's default client_max_body_size of 1m.

    A profile or room photo may be 12 MiB, so an API-token client can upload one to the API, with a
    Content-Length or chunked: the server block's rewrite sends it to an internal location with the
    photo limit before nginx checks a declared length, and nginx reads a chunked body in that same
    location. Every request the dashboard gets answers 413 over 1 MiB before any upstream sees it,
    the photo routes without a token included: a client without a session cannot push large bodies
    at the dashboard, which buffers them (up to 10 MiB in next 16.4.6) before any check. The
    dashboard's own photo upload, a cropped 512-pixel JPEG, fits within 1 MiB
    (tests/test_release_proxy_routing.py), and a client cannot ask for the upload location itself.
    """
    from koda.control_plane import operator_profile_photos
    from koda.squads import room_photos

    largest = max(operator_profile_photos.MAX_INPUT_BYTES, room_photos.MAX_INPUT_BYTES)
    body, content_type = proxy_smoke.multipart_photo(largest)
    # tests/test_release_proxy_routing.py keeps the limit within 1 MiB above the largest photo.
    oversized, _ = proxy_smoke.multipart_photo(largest + 1024 * 1024)
    # Over nginx's default of 1m, which every other request keeps.
    over_default, _ = proxy_smoke.multipart_photo(1024 * 1024)
    # A crop of exactly 1 MiB with its form: as much as the dashboard may get.
    framing = len(proxy_smoke.multipart_photo(0)[0])
    at_default, _ = proxy_smoke.multipart_photo(1024 * 1024 - framing)
    assert len(at_default) == 1024 * 1024 < len(over_default)
    received: list[tuple[str, str, int]] = []
    template = TEMPLATE.read_text(encoding="utf-8")
    anonymous = {"Content-Type": content_type}
    browser = {**anonymous, "Cookie": f"{proxy_smoke.SESSION_COOKIE}=sealed"}
    basic = {**browser, "Authorization": "Basic b3BlcmF0b3I6cGFzcw=="}
    api_token = {**anonymous, "Authorization": "Bearer koda-api-token"}
    profile = "/api/control-plane/auth/profile/photo"
    room = "/api/control-plane/dashboard/squads/threads/t-1/photo"
    internal = "/koda-api-photo-upload/auth/profile/photo"

    async with serve(_upload_app("dashboard", received)) as dashboard, serve(_upload_app("api", received)) as api:
        moved = template.replace(proxy_smoke.TEMPLATE_DASHBOARD, f"http://{dashboard}").replace(
            proxy_smoke.TEMPLATE_API, f"http://{api}"
        )
        with running_nginx(nginx_binary, tmp_path, moved) as proxy_url:
            accepted = [
                await asyncio.to_thread(_post, proxy_url, path, payload, headers, chunked=chunked)
                for path, payload, headers, chunked in [
                    (profile, body, api_token, False),
                    (room, body, api_token, False),
                    (profile, body, api_token, True),
                    (room, body, api_token, True),
                    (f"{profile}?source=cli", body, api_token, False),
                    (profile, at_default, browser, False),
                    (room, at_default, browser, True),
                ]
            ]
            refused = {
                (path, kind): await asyncio.to_thread(_post, proxy_url, path, payload, headers, chunked=chunked)
                for path, payload, headers, kind, chunked in [
                    (profile, oversized, api_token, "photo over 13m, API token", False),
                    (profile, oversized, api_token, "photo over 13m, chunked, API token", True),
                    (profile, over_default, browser, "session cookie", False),
                    (profile, over_default, browser, "session cookie, chunked", True),
                    (profile, over_default, anonymous, "no session", False),
                    (profile, over_default, anonymous, "no session, chunked", True),
                    (profile, over_default, basic, "HTTP Basic, not a token", False),
                    (room, over_default, browser, "session cookie", False),
                    (room, over_default, anonymous, "no session, chunked", True),
                    ("/api/control-plane/auth/login", over_default, anonymous, "no session", False),
                    ("/api/control-plane/auth/login", over_default, anonymous, "no session, chunked", True),
                    ("/setup", over_default, anonymous, "no session", False),
                    ("/api/runtime/agents", over_default, browser, "session cookie", False),
                    ("/api/control-plane/agents", over_default, api_token, "API token", False),
                    ("/api/control-plane/agents", over_default, api_token, "API token, chunked", True),
                    (f"{profile}/", over_default, api_token, "near the photo route, API token", False),
                    (f"{profile}/", over_default, anonymous, "near the photo route", False),
                ]
            }
            not_found = [
                await asyncio.to_thread(_post, proxy_url, internal, at_default, headers)
                for headers in (anonymous, browser, api_token)
            ]

    assert accepted == [200] * 7
    assert refused == dict.fromkeys(refused, 413)
    assert not_found == [404] * 3
    # The full body reached the upstream that serves each caller, under the path the client sent;
    # no refused body reached either.
    assert received == [
        ("api", profile, len(body)),
        ("api", room, len(body)),
        ("api", profile, len(body)),
        ("api", room, len(body)),
        ("api", f"{profile}?source=cli", len(body)),
        ("dashboard", profile, len(at_default)),
        ("dashboard", room, len(at_default)),
    ]
