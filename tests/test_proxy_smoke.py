"""The bundled reverse proxy in a real nginx (``scripts/proxy_smoke.py``, ``scripts/docker_smoke.sh``).

The CI docker-smoke jobs load ``packages/cli/release/bundle/proxy/nginx.conf`` into a pinned nginx in
front of the Compose stack and run ``scripts/proxy_smoke.py check`` through it. The tests below hold
that wiring in place and run the same checks through a real nginx here, in front of two stand-ins
for the dashboard and the API. The stand-ins answer the way the real services do wherever the
checks tell the two apart (apps/web/src/proxy.ts, the dashboard's auth routes and relay in
apps/web/server.mjs; koda/control_plane/api.py), so a request routed to the wrong one fails.

The real-nginx tests need an nginx binary: ``KODA_TEST_NGINX``, else ``nginx`` on PATH or
``/usr/sbin/nginx``. Without one they skip; the docker smoke still runs the same checks in CI,
against the real stack.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import shutil
import socket
import subprocess
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from aiohttp import HttpVersion11, web

import scripts.proxy_smoke as proxy_smoke

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
        "api: GET /openapi/control-plane.json",
        "health: HTTP/1.0 request without a Host reaches the dashboard",
    ]


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

    async def relay(request: web.Request) -> web.WebSocketResponse:
        stack.remember("dashboard", request)
        socket_response = web.WebSocketResponse()
        await socket_response.prepare(request)
        # apps/web/server.mjs closes an unknown relay id with 4404 relay_not_found.
        await socket_response.close(code=4404, message=b"relay_not_found")
        return socket_response

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
        pytest.skip("no nginx binary (set KODA_TEST_NGINX); the docker smoke runs these checks in CI")
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

    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
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
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


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
        "/openapi/control-plane.json",
    ]
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
    }
