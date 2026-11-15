#!/usr/bin/env python3
"""Smoke-test the bundled reverse proxy (``packages/cli/release/bundle/proxy/nginx.conf``) in a real nginx.

``scripts/docker_smoke.sh`` starts nginx with the bundled config in front of the Compose stack and
runs ``check`` against it. The checks follow the auth model in docs/install/vps.md ("Reverse
Proxy") and each one tells the two upstreams apart, so a request that reaches the wrong one fails:

- browser path: the dashboard serves ``/setup`` and ``/login``, answers a browser API call without
  a session with its own 401, registers the owner with the bootstrap code and signs in through the
  proxy (a session cookie, never the API's bearer token), and then serves a cookie-authenticated
  ``/api/control-plane/*`` call;
- runtime relay: a WebSocket upgrade on ``/api/runtime/relay/<id>`` for an unknown relay id gets the
  relay's empty ``404`` with the page's Origin and its empty ``403`` with a foreign Origin, both
  before any handshake (``apps/web/src/lib/runtime-relay-server.mjs``); nginx and the API never
  answer 403 there, so the pair shows the upgrade reached the dashboard's ``server.mjs``;
- API-token path: ``Authorization: Bearer`` calls reach the API, a GET and a POST whose body the API
  must read (``auth/login`` answers with a ``session_token`` only there), and the API serves
  ``/openapi/control-plane.json``;
- a request without a Host (HTTP/1.0 allows it; HAProxy's default ``option httpchk`` health check
  is one) still gets the dashboard's ``/api/health`` answer: nginx proxies it as HTTP/1.1, which the
  dashboard's Node server refuses without a Host;
- body limits: an API-token photo upload of 12 MiB (the largest photo the API accepts) reaches the
  API, which decodes it, with a Content-Length and chunked; a body over 1 MiB to the sign-in route,
  or to a photo route without an API token, gets nginx's own 413 (the dashboard buffers a body
  before it checks anything, so nothing larger may reach it).

``render`` writes the template with the ``listen`` address (and, for tests, the upstream addresses)
replaced. Only the standard library is used, so the script runs on a bare CI runner. Secrets are
read from the environment or an env file and never printed.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import http.client
import io
import json
import os
import re
import secrets
import socket
import sys
from collections.abc import Callable, Iterator, Mapping
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
# apps/web/src/lib/runtime-relay-server.mjs refuses a relay upgrade before the WebSocket handshake
# with an empty answer: 403 unless the Origin is the page's (X-Forwarded-Proto and Host), then 404
# for an unknown relay id. Only the dashboard answers 403 there; nginx and the API never do.
RELAY_PATH_PREFIX = "/api/runtime/relay/"
RELAY_UNKNOWN_ID_STATUS = 404
RELAY_FOREIGN_ORIGIN_STATUS = 403
FOREIGN_ORIGIN = "http://evil.example"
TIMEOUT_SECONDS = 15.0

PROFILE_PHOTO_PATH = "/api/control-plane/auth/profile/photo"
# MAX_INPUT_BYTES in koda/control_plane/operator_profile_photos.py (tests/test_proxy_smoke.py holds
# the two together): the largest photo the API accepts, and nginx's default client_max_body_size.
LARGEST_PHOTO_BYTES = 12 * 1024 * 1024
DEFAULT_BODY_LIMIT_BYTES = 1024 * 1024
# The API's answer to photo bytes that are not an image (operator_profile_photos.py); only the API
# decodes a photo, so this answer can come from nowhere else.
API_UNDECODABLE_PHOTO = "could not decode image"
# nginx's own error page; an upstream's 413 would be its own (JSON) answer.
NGINX_TOO_LARGE = b"413 Request Entity Too Large"


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

    def post_bytes(
        self, path: str, body: bytes, *, headers: Mapping[str, str] | None = None, chunked: bool = False
    ) -> Response:
        """POST *body* with a Content-Length, or with ``chunked=True`` as a chunked body (no length declared)."""
        sent = {"Host": self.netloc, **(headers or {})}
        step = 256 * 1024
        payload: bytes | Iterator[bytes] = (
            (body[index : index + step] for index in range(0, len(body), step)) if chunked else body
        )
        connection = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        try:
            # nginx may answer 413 and close before the whole body is sent; its answer is still read.
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                connection.request("POST", path, body=payload, headers=sent)
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

    def websocket_upgrade(self, path: str, *, origin: str) -> Response:
        """Send a WebSocket upgrade for *path* from a page on *origin* and return the answer, whatever its status."""
        headers = {
            "Upgrade": "websocket",
            "Connection": "Upgrade",
            "Sec-WebSocket-Key": base64.b64encode(os.urandom(16)).decode("ascii"),
            "Sec-WebSocket-Version": "13",
            "Origin": origin,
        }
        # http.client reads no body after a 101, so this returns at once even if a server accepts it.
        return self.request("GET", path, headers=headers)


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
    path = f"{RELAY_PATH_PREFIX}proxy-smoke-{secrets.token_hex(8)}"
    for origin, status in ((proxy.origin, RELAY_UNKNOWN_ID_STATUS), (FOREIGN_ORIGIN, RELAY_FOREIGN_ORIGIN_STATUS)):
        response = proxy.websocket_upgrade(path, origin=origin)
        length = response.headers.get("Content-Length")
        accept = response.headers.get("Sec-WebSocket-Accept")
        _expect(
            response.status == status and length == "0" and not response.body and accept is None,
            f"expected the relay's empty {status} for Origin {origin}, got {response.summary()}"
            f" with Content-Length {length!r} and {'a' if accept else 'no'} Sec-WebSocket-Accept",
        )
    return (
        f"{RELAY_UNKNOWN_ID_STATUS} for an unknown relay id, {RELAY_FOREIGN_ORIGIN_STATUS} for a foreign Origin,"
        " both empty and before the handshake"
    )


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


def multipart_photo(size: int) -> tuple[bytes, str]:
    """A multipart/form-data body with one ``photo`` file of *size* bytes (not an image), and its type."""
    boundary = secrets.token_hex(16)
    head = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="photo"; filename="photo.jpg"\r\n'
        "Content-Type: image/jpeg\r\n\r\n"
    ).encode("ascii")
    tail = f"\r\n--{boundary}--\r\n".encode("ascii")
    return head + b"\xff" * size + tail, f"multipart/form-data; boundary={boundary}"


def _refused_by_the_proxy(response: Response) -> bool:
    return response.status == 413 and NGINX_TOO_LARGE in response.body and response.json() is None


def _api_token_photo_upload(proxy: Proxy, api_token: str, session: Session) -> str:
    _expect(bool(api_token), "no API token was provided")
    # The break-glass token acts as the owner, so the API reads and decodes the photo.
    _expect(session.registered, "needs the owner registered through the proxy")
    body, content_type = multipart_photo(LARGEST_PHOTO_BYTES)
    headers = {"Accept": "application/json", "Authorization": f"Bearer {api_token}", "Content-Type": content_type}
    for chunked in (False, True):
        response = proxy.post_bytes(PROFILE_PHOTO_PATH, body, headers=headers, chunked=chunked)
        payload = response.json()
        sent = "chunked" if chunked else "with a Content-Length"
        _expect(not _refused_by_the_proxy(response), f"nginx refused the photo {sent}: {response.summary()}")
        # The bytes are no image: the API answers 400 and stores nothing.
        _expect(
            response.status == 400
            and isinstance(payload, dict)
            and str(payload.get("error", "")).startswith(API_UNDECODABLE_PHOTO),
            f"expected the API's {API_UNDECODABLE_PHOTO!r} for the photo {sent}, got {response.summary()}",
        )
    return f"{LARGEST_PHOTO_BYTES} bytes reached the API, with a Content-Length and chunked"


def _too_large_without_token(proxy: Proxy, path: str, body: bytes, content_type: str) -> str:
    headers = {"Accept": "application/json", "Origin": proxy.origin, "Content-Type": content_type}
    for chunked in (False, True):
        response = proxy.post_bytes(path, body, headers=headers, chunked=chunked)
        sent = "chunked" if chunked else "with a Content-Length"
        _expect(
            _refused_by_the_proxy(response),
            f"expected nginx's 413 for {len(body)} bytes {sent}, got {response.summary()}",
        )
    return f"413 from nginx for {len(body)} bytes, with a Content-Length and chunked"


def _sign_in_body_over_default(proxy: Proxy) -> str:
    return _too_large_without_token(
        proxy, "/api/control-plane/auth/login", b"{" + b" " * DEFAULT_BODY_LIMIT_BYTES + b"}", "application/json"
    )


def _photo_over_default_without_token(proxy: Proxy) -> str:
    body, content_type = multipart_photo(DEFAULT_BODY_LIMIT_BYTES)
    return _too_large_without_token(proxy, PROFILE_PHOTO_PATH, body, content_type)


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
        (
            "api-token: a 12 MiB photo upload reaches the API",
            lambda: _api_token_photo_upload(proxy, api_token, session),
        ),
        ("api: GET /openapi/control-plane.json", lambda: _openapi(proxy)),
        ("health: HTTP/1.0 request without a Host reaches the dashboard", lambda: _request_without_host(proxy)),
        ("body limit: a sign-in body over 1 MiB gets nginx's 413", lambda: _sign_in_body_over_default(proxy)),
        (
            "body limit: a photo over 1 MiB without an API token gets nginx's 413",
            lambda: _photo_over_default_without_token(proxy),
        ),
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
