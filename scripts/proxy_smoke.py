#!/usr/bin/env python3
"""Smoke-test the bundled reverse proxy (``packages/cli/release/bundle/proxy/nginx.conf``) in a real nginx.

``scripts/docker_smoke.sh`` starts nginx with the bundled config in front of the Compose stack and
runs ``check`` against it. The checks follow the auth model in docs/install/vps.md ("Reverse
Proxy") and each one tells the two upstreams apart, so a request that reaches the wrong one fails:

- browser path: the dashboard serves ``/setup`` and ``/login``, answers a browser API call without
  a session with its own 401, registers the owner with the bootstrap code and signs in through the
  proxy (a session cookie, never the API's bearer token), and then serves a cookie-authenticated
  ``/api/control-plane/*`` call;
- runtime relay: a WebSocket handshake on ``/api/runtime/relay/<id>`` gets ``101`` and the relay's
  own close code ``4404 relay_not_found``, so the upgrade reached the dashboard's ``server.mjs``;
- API-token path: ``Authorization: Bearer`` calls reach the API, a GET and a POST whose body the API
  must read (``auth/login`` answers with a ``session_token`` only there), and the API serves
  ``/openapi/control-plane.json``;
- a request without a Host (HTTP/1.0 allows it; HAProxy's default ``option httpchk`` health check
  is one) still gets the dashboard's ``/api/health`` answer: nginx proxies it as HTTP/1.1, which the
  dashboard's Node server refuses without a Host.

``render`` writes the template with the ``listen`` address (and, for tests, the upstream addresses)
replaced. Only the standard library is used, so the script runs on a bare CI runner. Secrets are
read from the environment or an env file and never printed.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import http.client
import io
import json
import os
import re
import secrets
import socket
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "packages" / "cli" / "release" / "bundle" / "proxy" / "nginx.conf"

TEMPLATE_LISTEN = "listen 80;"
TEMPLATE_DASHBOARD = "http://127.0.0.1:3000"
TEMPLATE_API = "http://127.0.0.1:8090"

SESSION_COOKIE = "koda_operator_session"
DASHBOARD_NO_SESSION = "Operator session is required."
RELAY_NOT_FOUND = (4404, "relay_not_found")
WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
TIMEOUT_SECONDS = 15.0


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------


def render(template: str, *, listen: str, dashboard: str | None = None, api: str | None = None) -> str:
    """Return *template* listening on *listen* and, when given, proxying to other upstream addresses."""
    replacements = [(TEMPLATE_LISTEN, f"listen {listen};")]
    if dashboard:
        replacements.append((TEMPLATE_DASHBOARD, f"http://{dashboard}"))
    if api:
        replacements.append((TEMPLATE_API, f"http://{api}"))
    for old, new in replacements:
        if old not in template:
            raise ValueError(f"the proxy template no longer contains {old!r}")
        template = template.replace(old, new)
    return template


# ---------------------------------------------------------------------------
# HTTP and WebSocket clients
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Response:
    status: int
    headers: http.client.HTTPMessage
    body: bytes

    def json(self) -> object:
        try:
            return json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return None

    def cookies(self) -> dict[str, str]:
        found: dict[str, str] = {}
        for header in self.headers.get_all("Set-Cookie") or []:
            name, _, rest = header.partition("=")
            found[name.strip()] = rest.split(";", 1)[0].strip()
        return found

    def summary(self) -> str:
        """Status and a short body excerpt for failure messages, with tokens and codes left out."""
        payload = self.json()
        if isinstance(payload, dict):
            payload = {
                key: ("<redacted>" if "token" in key or "code" in key else value) for key, value in payload.items()
            }
            excerpt = json.dumps(payload)[:200]
        else:
            excerpt = self.body[:120].decode("utf-8", "replace").replace("\n", " ")
        return f"HTTP {self.status} {excerpt!r}"


class Proxy:
    def __init__(self, base_url: str, *, timeout: float = TIMEOUT_SECONDS) -> None:
        parts = urlsplit(base_url)
        if parts.scheme != "http" or not parts.hostname:
            raise ValueError(f"expected an http:// proxy URL, got {base_url!r}")
        self.host = parts.hostname
        self.port = parts.port or 80
        # The Host and Origin a browser on this page sends: the default port is left out.
        self.netloc = self.host if self.port == 80 else f"{self.host}:{self.port}"
        self.origin = f"http://{self.netloc}"
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: object | None = None,
    ) -> Response:
        sent = dict(headers or {})
        data: bytes | None = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            sent.setdefault("Content-Type", "application/json")
        sent.setdefault("Host", self.netloc)
        connection = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        try:
            connection.request(method, path, body=data, headers=sent)
            response = connection.getresponse()
            return Response(response.status, response.msg, response.read())
        finally:
            connection.close()

    def raw_request(self, request: bytes) -> Response:
        """Send *request* exactly as written (http.client always adds a Host) and read it to the end."""
        received = b""
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
            sock.sendall(request)
            while chunk := sock.recv(65536):
                received += chunk
        head, _, body = received.partition(b"\r\n\r\n")
        status_line, _, fields = head.partition(b"\r\n")
        parts = status_line.decode("latin-1").split(" ", 2)
        if len(parts) < 2 or not parts[0].startswith("HTTP/") or not parts[1].isdigit():
            raise CheckFailed(f"not an HTTP response: {status_line[:120]!r}")
        return Response(int(parts[1]), http.client.parse_headers(io.BytesIO(fields + b"\r\n\r\n")), body)

    def websocket_close(self, path: str) -> tuple[int, str]:
        """Open a WebSocket on *path* and return the close code and reason of the first frame the server sends."""
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        handshake = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {self.netloc}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            f"Origin: {self.origin}\r\n"
            "\r\n"
        )
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
            sock.sendall(handshake.encode("ascii"))
            buffer = b""
            while b"\r\n\r\n" not in buffer:
                chunk = sock.recv(4096)
                if not chunk:
                    raise CheckFailed(f"connection closed during the handshake: {buffer[:120]!r}")
                buffer += chunk
            head, _, buffer = buffer.partition(b"\r\n\r\n")
            lines = head.decode("latin-1").split("\r\n")
            status = lines[0].split(" ", 2)
            if len(status) < 2 or status[1] != "101":
                raise CheckFailed(f"expected 101 Switching Protocols, got {lines[0]!r}")
            fields = {
                name.strip().lower(): value.strip() for name, _, value in (line.partition(":") for line in lines[1:])
            }
            accept = base64.b64encode(hashlib.sha1((key + WEBSOCKET_GUID).encode("ascii")).digest()).decode("ascii")
            if fields.get("upgrade", "").lower() != "websocket" or fields.get("sec-websocket-accept") != accept:
                raise CheckFailed(f"the 101 is not a WebSocket handshake answer: {fields}")

            def read(count: int) -> bytes:
                nonlocal buffer
                while len(buffer) < count:
                    chunk = sock.recv(4096)
                    if not chunk:
                        raise CheckFailed("connection closed before a close frame arrived")
                    buffer += chunk
                taken, buffer = buffer[:count], buffer[count:]
                return taken

            first, second = read(2)
            opcode, length = first & 0x0F, second & 0x7F
            if second & 0x80:
                raise CheckFailed("the server sent a masked frame")
            if length == 126:
                length = int.from_bytes(read(2), "big")
            elif length == 127:
                length = int.from_bytes(read(8), "big")
            payload = read(length)
            if opcode != 0x8:
                raise CheckFailed(f"expected a close frame first, got opcode {opcode:#x}")
            code = int.from_bytes(payload[:2], "big") if len(payload) >= 2 else 1005
            reason = payload[2:].decode("utf-8", "replace")
            # Answer the close (client frames are masked) so the server sees a clean shutdown; it may
            # already have dropped the connection, which changes nothing about the answer.
            mask = os.urandom(4)
            reply = code.to_bytes(2, "big") if len(payload) >= 2 else b""
            with contextlib.suppress(OSError):
                sock.sendall(
                    bytes([0x88, 0x80 | len(reply)]) + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(reply))
                )
            return code, reason


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


class CheckFailed(Exception):
    pass


@dataclass
class Result:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Session:
    """Credentials made up for this run; the owner registered through the proxy uses them."""

    email: str = field(default_factory=lambda: f"owner-{secrets.token_hex(4)}@example.com")
    password: str = field(default_factory=lambda: f"Kq{secrets.token_hex(10)}!7Z")
    registered: bool = False
    cookies: dict[str, str] = field(default_factory=dict)

    def cookie_header(self) -> str:
        return "; ".join(f"{name}={value}" for name, value in self.cookies.items())


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailed(message)


def _dashboard_page(proxy: Proxy, path: str) -> str:
    response = proxy.request("GET", path, headers={"Accept": "text/html"})
    _expect(response.status == 200, f"expected 200, got {response.summary()}")
    # Next.js pages load their bundles from /_next/; the API's legacy /setup page does not.
    _expect(b"/_next/" in response.body, f"not a dashboard page: {response.summary()}")
    return "dashboard page"


def _browser_call_without_session(proxy: Proxy) -> str:
    response = proxy.request("GET", "/api/control-plane/agents", headers={"Accept": "application/json"})
    payload = response.json()
    _expect(
        response.status == 401 and isinstance(payload, dict) and payload.get("error") == DASHBOARD_NO_SESSION,
        f"expected the dashboard's 401 {DASHBOARD_NO_SESSION!r}, got {response.summary()}",
    )
    return "dashboard 401"


def _browser_mutation(proxy: Proxy, session: Session, path: str, body: object, *, status: int) -> Response:
    headers = {"Origin": proxy.origin, "Accept": "application/json"}
    if session.cookies:
        headers["Cookie"] = session.cookie_header()
    response = proxy.request("POST", path, headers=headers, body=body)
    payload = response.json()
    _expect(response.status == status, f"expected {status}, got {response.summary()}")
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise CheckFailed(f"not the dashboard's answer: {response.summary()}")
    # The API answers with the bearer token in the body; the dashboard seals it into a cookie.
    _expect("session_token" not in payload, "the response carries the API's session_token: it came from the API")
    cookie = response.cookies().get(SESSION_COOKIE, "")
    _expect(bool(cookie), f"no {SESSION_COOKIE} cookie was set: {response.summary()}")
    session.cookies.update({name: value for name, value in response.cookies().items() if value})
    return response


def _register_owner(proxy: Proxy, session: Session, bootstrap_code: str) -> str:
    _expect(bool(bootstrap_code), "no bootstrap code was provided")
    body = {"email": session.email, "password": session.password, "bootstrap_code": bootstrap_code}
    _browser_mutation(proxy, session, "/api/control-plane/auth/register-owner", body, status=201)
    session.registered = True
    return "owner registered, session cookie set"


def _login(proxy: Proxy, session: Session) -> str:
    _expect(session.registered, "needs the owner registered through the proxy")
    # Sign in as a browser that holds no session yet.
    session.cookies.clear()
    body = {"identifier": session.email, "password": session.password}
    _browser_mutation(proxy, session, "/api/control-plane/auth/login", body, status=200)
    return "session cookie set"


def _browser_call_with_session(proxy: Proxy, session: Session) -> str:
    _expect(bool(session.cookies), "needs the session from the browser login")
    response = proxy.request(
        "GET", "/api/control-plane/agents", headers={"Accept": "application/json", "Cookie": session.cookie_header()}
    )
    _expect(response.status == 200 and response.json() is not None, f"expected 200 JSON, got {response.summary()}")
    return "200"


def _relay_websocket(proxy: Proxy) -> str:
    code, reason = proxy.websocket_close(f"/api/runtime/relay/proxy-smoke-{secrets.token_hex(8)}")
    _expect((code, reason) == RELAY_NOT_FOUND, f"expected close {RELAY_NOT_FOUND}, got ({code}, {reason!r})")
    return f"101, then close {code} {reason}"


def _api_token_get(proxy: Proxy, api_token: str) -> str:
    _expect(bool(api_token), "no API token was provided")
    response = proxy.request(
        "GET",
        "/api/control-plane/agents",
        headers={"Accept": "application/json", "Authorization": f"Bearer {api_token}"},
    )
    # Without a session cookie the dashboard answers 401, so a 200 can only come from the API.
    _expect(response.status == 200 and response.json() is not None, f"expected the API's 200, got {response.summary()}")
    return "200 from the API"


def _api_token_post(proxy: Proxy, api_token: str, session: Session) -> str:
    _expect(bool(api_token), "no API token was provided")
    _expect(session.registered, "needs the owner registered through the proxy")
    response = proxy.request(
        "POST",
        "/api/control-plane/auth/login",
        headers={"Accept": "application/json", "Authorization": f"Bearer {api_token}"},
        body={"identifier": session.email, "password": session.password},
    )
    payload = response.json()
    # Only the API returns a session_token, and only for the credentials in the body.
    _expect(
        response.status == 200 and isinstance(payload, dict) and bool(payload.get("session_token")),
        f"expected the API's session_token, got {response.summary()}",
    )
    return "POST and its body reached the API"


def _openapi(proxy: Proxy) -> str:
    response = proxy.request("GET", "/openapi/control-plane.json", headers={"Accept": "application/json"})
    payload = response.json()
    _expect(
        response.status == 200 and isinstance(payload, dict) and "openapi" in payload and "paths" in payload,
        f"expected the OpenAPI document, got {response.summary()}",
    )
    return "200"


def _request_without_host(proxy: Proxy) -> str:
    response = proxy.raw_request(b"GET /api/health HTTP/1.0\r\n\r\n")
    payload = response.json()
    _expect(
        response.status == 200 and isinstance(payload, dict) and payload.get("status") == "ok",
        f"expected the dashboard's health answer, got {response.summary()}",
    )
    return "200 from the dashboard"


def run_checks(proxy_url: str, *, api_token: str, bootstrap_code: str) -> list[Result]:
    proxy = Proxy(proxy_url)
    session = Session()
    checks: list[tuple[str, Callable[[], str]]] = [
        ("browser: GET /setup is the dashboard", lambda: _dashboard_page(proxy, "/setup")),
        ("browser: GET /login is the dashboard", lambda: _dashboard_page(proxy, "/login")),
        ("browser: API call without a session gets the dashboard's 401", lambda: _browser_call_without_session(proxy)),
        (
            "browser: owner registration with the bootstrap code",
            lambda: _register_owner(proxy, session, bootstrap_code),
        ),
        ("browser: login", lambda: _login(proxy, session)),
        ("browser: API call with the session cookie", lambda: _browser_call_with_session(proxy, session)),
        ("relay: WebSocket upgrade reaches the dashboard relay", lambda: _relay_websocket(proxy)),
        ("api-token: GET /api/control-plane/agents", lambda: _api_token_get(proxy, api_token)),
        ("api-token: POST with a body", lambda: _api_token_post(proxy, api_token, session)),
        ("api: GET /openapi/control-plane.json", lambda: _openapi(proxy)),
        ("health: HTTP/1.0 request without a Host reaches the dashboard", lambda: _request_without_host(proxy)),
    ]
    results: list[Result] = []
    for name, check in checks:
        try:
            results.append(Result(name, True, check()))
        except CheckFailed as error:
            results.append(Result(name, False, str(error)))
        except (OSError, http.client.HTTPException) as error:
            results.append(Result(name, False, f"{type(error).__name__}: {error}"))
    return results


def read_env_file(path: Path, key: str) -> str:
    pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(key)}\s*=\s*(.*?)\s*$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            return match.group(1).strip("'\"")
    return ""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    render_parser = commands.add_parser("render", help="print the template with the listen address replaced")
    render_parser.add_argument("template", nargs="?", type=Path, default=TEMPLATE)
    render_parser.add_argument("--listen", required=True, help="address:port nginx listens on")
    render_parser.add_argument("--dashboard", help="address:port of the dashboard (default 127.0.0.1:3000)")
    render_parser.add_argument("--api", help="address:port of the control-plane API (default 127.0.0.1:8090)")

    check_parser = commands.add_parser("check", help="run the checks through a running proxy")
    check_parser.add_argument("--proxy-url", required=True)
    check_parser.add_argument(
        "--env-file", type=Path, help="read CONTROL_PLANE_API_TOKEN from this file unless it is in the environment"
    )

    args = parser.parse_args(argv)
    if args.command == "render":
        try:
            sys.stdout.write(
                render(
                    args.template.read_text(encoding="utf-8"),
                    listen=args.listen,
                    dashboard=args.dashboard,
                    api=args.api,
                )
            )
        except ValueError as error:
            print(f"[proxy-smoke] {error}", file=sys.stderr)
            return 1
        return 0

    api_token = os.environ.get("CONTROL_PLANE_API_TOKEN", "")
    if not api_token and args.env_file:
        api_token = read_env_file(args.env_file, "CONTROL_PLANE_API_TOKEN")
    bootstrap_code = os.environ.get("KODA_PROXY_SMOKE_BOOTSTRAP_CODE", "")
    results = run_checks(args.proxy_url, api_token=api_token, bootstrap_code=bootstrap_code)
    for result in results:
        print(f"[proxy-smoke] {'ok  ' if result.ok else 'FAIL'} {result.name}: {result.detail}")
    failed = [result for result in results if not result.ok]
    if failed:
        print(f"[proxy-smoke] {len(failed)} of {len(results)} checks failed through {args.proxy_url}", file=sys.stderr)
        return 1
    print(f"[proxy-smoke] all {len(results)} checks passed through {args.proxy_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
