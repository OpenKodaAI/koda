"""Contract test for the bundled reverse proxy (``packages/cli/release/bundle/proxy/nginx.conf``).

The routing follows the auth model in docs/install/vps.md ("Reverse Proxy"):

- browsers talk only to the dashboard, which turns the HTTP-only session cookie into the API's
  bearer token, so pages and the browser-facing ``/api/control-plane/*`` and ``/api/runtime/*``
  routes go to ``127.0.0.1:3000``;
- the runtime relay (``/api/runtime/relay/*``) is a WebSocket, so the upgrade headers must reach
  the dashboard;
- only ``/api/control-plane/*`` requests carrying ``Authorization: Bearer`` (API-token clients) and
  ``/openapi/control-plane.json`` go to the API on ``127.0.0.1:8090``;
- every request adds the address it came from to ``X-Forwarded-For``, so the trusted-proxy
  settings charge rate limits to the real client;
- every request reaches the upstream with a ``Host``: the browser's, port included, or the server
  name when the client sent none;
- every request may carry a body as large as the largest upload the app accepts (a 12 MiB photo
  in a multipart form), where nginx's default ``client_max_body_size`` of 1m would refuse it.

The config is parsed and routed by a small model of nginx: exact and longest-prefix ``location``
matching, ``if`` with ``return``, ``error_page ... = @named``, ``map`` without regexes, and the
variables the config uses. Anything outside that model fails the test instead of being skipped,
so a change to the config either stays inside it or extends it. The runtime proof is
``scripts/proxy_smoke.py``: ``scripts/docker_smoke.sh`` (the CI docker-smoke jobs) loads this
config into a real nginx in front of the Compose stack and runs it there (browser login, the relay
WebSocket and API-token calls), and ``tests/test_proxy_smoke.py`` runs the same checks through a
real nginx when one is installed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from multidict import CIMultiDict

from koda.control_plane import rate_limit

ROOT = Path(__file__).resolve().parents[1]
NGINX_CONF = ROOT / "packages" / "cli" / "release" / "bundle" / "proxy" / "nginx.conf"

DASHBOARD = "http://127.0.0.1:3000"
API = "http://127.0.0.1:8090"
HOST = "koda.example.com"
# The address nginx accepted the connection from ($remote_addr).
CLIENT = "203.0.113.9"
# An X-Forwarded-For the client wrote itself.
SPOOFED = "198.51.100.7"

SESSION_COOKIE = {"Cookie": "koda_operator_session=sealed"}
BEARER = {"Authorization": "Bearer koda-api-token"}


# ---------------------------------------------------------------------------
# A minimal nginx config parser
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Directive:
    name: str
    args: tuple[str, ...]
    block: tuple[Directive, ...] | None = None


_ESCAPES = {"t": "\t", "r": "\r", "n": "\n"}


def _tokenize(text: str) -> list[tuple[str, str]]:
    """Split a config into ("word", value) and ("punct", ";" | "{" | "}") tokens, as nginx reads it."""
    tokens: list[tuple[str, str]] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
        elif char == "#":
            end = text.find("\n", index)
            index = len(text) if end == -1 else end
        elif char in ";{}":
            tokens.append(("punct", char))
            index += 1
        elif char in "\"'":
            value: list[str] = []
            index += 1
            while True:
                assert index < len(text), "unterminated quoted string"
                current = text[index]
                if current == char:
                    index += 1
                    break
                if current == "\\" and index + 1 < len(text):
                    following = text[index + 1]
                    if following in "\"'\\":
                        value.append(following)
                        index += 2
                        continue
                    if following in _ESCAPES:
                        value.append(_ESCAPES[following])
                        index += 2
                        continue
                value.append(current)
                index += 1
            tokens.append(("word", "".join(value)))
        else:
            start = index
            while index < len(text) and not text[index].isspace() and text[index] not in ";{}\"'":
                index += 1
            tokens.append(("word", text[start:index]))
    return tokens


def _parse(tokens: list[tuple[str, str]]) -> tuple[Directive, ...]:
    def block(position: int, nested: bool) -> tuple[tuple[Directive, ...], int]:
        items: list[Directive] = []
        words: list[str] = []
        while position < len(tokens):
            kind, value = tokens[position]
            position += 1
            if kind == "word":
                words.append(value)
            elif value == ";":
                assert words, "empty directive"
                items.append(Directive(words[0], tuple(words[1:])))
                words = []
            elif value == "{":
                assert words, "block without a directive"
                children, position = block(position, nested=True)
                items.append(Directive(words[0], tuple(words[1:]), children))
                words = []
            else:
                assert nested and not words, "unbalanced '}'"
                return tuple(items), position
        assert not nested and not words, "unterminated block or directive"
        return tuple(items), position

    return block(0, nested=False)[0]


# ---------------------------------------------------------------------------
# A minimal model of how nginx routes a request through that config
# ---------------------------------------------------------------------------

# Directives the model understands in the `server` block and inside a `location`; anything else
# fails the test.
# client_max_body_size is understood in the server block only, so one limit covers every location
# (the named API location included).
_SERVER_DIRECTIVES = {"client_max_body_size", "error_page", "listen", "location", "proxy_set_header", "server_name"}
_LOCATION_DIRECTIVES = {
    "error_page",
    "if",
    "proxy_http_version",
    "proxy_pass",
    "proxy_read_timeout",
    "proxy_send_timeout",
    "proxy_set_header",
}
# nginx's client_max_body_size when the config sets none.
_NGINX_DEFAULT_BODY_LIMIT = "1m"
# Header fields nginx redefines for every proxied request unless proxy_set_header says otherwise
# (an empty value is not sent). Hop-by-hop fields such as Upgrade never pass through on their own.
_NGINX_DEFAULT_HEADERS = {
    "host": "$proxy_host",
    "connection": "close",
    "keep-alive": "",
    "te": "",
    "transfer-encoding": "",
    "expect": "",
    "upgrade": "",
}
_VARIABLE = re.compile(r"\$(\w+)")


@dataclass(frozen=True)
class Location:
    label: str  # how it is declared: "/api/", "= /exact", "@named"
    prefix: str | None  # the matched path for exact and prefix locations
    block: tuple[Directive, ...]

    def all(self, name: str) -> list[Directive]:
        return [directive for directive in self.block if directive.name == name]

    def one(self, name: str) -> Directive:
        found = self.all(name)
        assert len(found) == 1, f"{self.label}: expected one {name}, found {len(found)}"
        return found[0]


@dataclass(frozen=True)
class Request:
    path: str
    headers: dict[str, str]  # lower-case names
    remote_addr: str = CLIENT


@dataclass(frozen=True)
class Route:
    location: Location
    upstream: str  # scheme://host:port of the proxy_pass
    target: str  # the request URI sent upstream
    http_version: str
    headers: dict[str, str]  # lower-case names, as sent upstream
    body_limit: int  # the largest request body nginx accepts, in bytes (client_max_body_size)


class NginxModel:
    def __init__(self, text: str) -> None:
        top = _parse(_tokenize(text))
        assert {directive.name for directive in top} <= {"map", "server"}, [d.name for d in top]
        self.maps: dict[str, tuple[str, dict[str, str]]] = {}
        for directive in top:
            if directive.name != "map":
                continue
            source, target = directive.args
            assert directive.block is not None
            table: dict[str, str] = {}
            for entry in directive.block:
                assert len(entry.args) == 1 and not entry.name.startswith("~"), f"map entry outside the model: {entry}"
                # nginx matches a map's string keys ignoring case.
                table[entry.name.lower()] = entry.args[0]
            self.maps[target.removeprefix("$")] = (source, table)

        servers = [directive for directive in top if directive.name == "server"]
        assert len(servers) == 1, "expected a single server block"
        assert servers[0].block is not None
        self.server = servers[0].block
        for directive in self.server:
            # TLS settings do not change routing; a server-level rewrite, return or if would.
            assert directive.name in _SERVER_DIRECTIVES or directive.name.startswith("ssl_"), (
                f"server: {directive.name} is outside the model"
            )
        self.scheme = "https" if any("ssl" in d.args for d in self.server if d.name == "listen") else "http"
        names = [d for d in self.server if d.name == "server_name"]
        assert len(names) == 1 and names[0].args, "expected one server_name directive"
        # The server's first name: what $host is when the request names no host.
        self.server_name = names[0].args[0]

        self.exact: dict[str, Location] = {}
        self.prefixes: dict[str, Location] = {}
        self.named: dict[str, Location] = {}
        for directive in self.server:
            if directive.name != "location":
                continue
            assert directive.block is not None
            for inner in directive.block:
                assert inner.name in _LOCATION_DIRECTIVES, (
                    f"location {directive.args}: {inner.name} is outside the model"
                )
            if len(directive.args) == 2 and directive.args[0] == "=":
                path = directive.args[1]
                self.exact[path] = Location(f"= {path}", path, directive.block)
            elif len(directive.args) == 1 and directive.args[0].startswith("@"):
                name = directive.args[0]
                self.named[name] = Location(name, None, directive.block)
            elif len(directive.args) == 1 and not directive.args[0].startswith(("~", "^~")):
                path = directive.args[0]
                self.prefixes[path] = Location(path, path, directive.block)
            else:
                raise AssertionError(f"location {directive.args} is outside the model (regex or ^~)")

    def locations(self) -> list[Location]:
        return [*self.prefixes.values(), *self.exact.values(), *self.named.values()]

    # -- variables ---------------------------------------------------------

    def variable(self, name: str, request: Request, location: Location) -> str:
        if name in self.maps:
            source, table = self.maps[name]
            key = self.expand(source, request, location).lower()
            # A map's resulting value can itself hold variables.
            return self.expand(table.get(key, table.get("default", "")), request, location)
        if name == "host":
            # The Host header without its port, or the server name when the request has none.
            host = request.headers.get("host", "")
            return host.lower().rsplit(":", 1)[0] if host else self.server_name
        if name == "scheme":
            return self.scheme
        if name == "remote_addr":
            return request.remote_addr
        if name == "proxy_add_x_forwarded_for":
            forwarded = request.headers.get("x-forwarded-for")
            return f"{forwarded}, {request.remote_addr}" if forwarded else request.remote_addr
        if name == "proxy_host":
            return self.upstream(location)[0].removeprefix("http://")
        if name.startswith("http_"):
            return request.headers.get(name.removeprefix("http_").replace("_", "-"), "")
        raise AssertionError(f"${name} is outside the model")

    def expand(self, value: str, request: Request, location: Location) -> str:
        return _VARIABLE.sub(lambda match: self.variable(match.group(1), request, location), value)

    # -- phases ------------------------------------------------------------

    def select(self, path: str) -> Location:
        if path in self.exact:
            return self.exact[path]
        matches = [prefix for prefix in self.prefixes if path.startswith(prefix)]
        assert matches, f"no location matches {path}"
        return self.prefixes[max(matches, key=len)]

    def condition(self, args: tuple[str, ...], request: Request, location: Location) -> bool:
        words = list(args)
        assert words and words[0].startswith("("), f"if {args}"
        words[0] = words[0][1:]
        if words[-1] == ")":
            words.pop()
        else:
            assert words[-1].endswith(")"), f"if {args}"
            words[-1] = words[-1][:-1]
        words = [word for word in words if word]
        value = self.expand(words[0], request, location)
        if len(words) == 1:
            return value not in ("", "0")
        operator, pattern = words[1], words[2]
        if operator == "=":
            return value == pattern
        if operator == "!=":
            return value != pattern
        if operator in ("~", "~*"):
            return re.search(pattern, value, re.IGNORECASE if operator == "~*" else 0) is not None
        raise AssertionError(f"if operator {operator} is outside the model")

    def rewrite(self, location: Location, request: Request) -> int | None:
        """Run the location's `if` blocks; return the status of a `return`, or None."""
        for directive in location.all("if"):
            if not self.condition(directive.args, request, location):
                continue
            assert directive.block is not None
            for inner in directive.block:
                assert inner.name == "return", f"if block: {inner.name} is outside the model"
                return int(inner.args[0])
        return None

    def error_page(self, location: Location, status: int) -> Location:
        # As with proxy_set_header, a location's own error_page directives replace the server's.
        pages = location.all("error_page") or [d for d in self.server if d.name == "error_page"]
        for directive in pages:
            *codes, equals, target = directive.args
            if str(status) in codes:
                assert equals == "=" and target in self.named, f"error_page {directive.args} is outside the model"
                return self.named[target]
        raise AssertionError(f"{location.label} returns a bare {status}")

    def body_limit(self) -> int:
        limits = [d for d in self.server if d.name == "client_max_body_size"]
        assert len(limits) <= 1, "client_max_body_size is set more than once"
        return _size(limits[0].args[0] if limits else _NGINX_DEFAULT_BODY_LIMIT)

    def upstream(self, location: Location) -> tuple[str, str | None]:
        url = location.one("proxy_pass").args[0]
        match = re.fullmatch(r"(http://[^/$]+)(/[^$]*)?", url)
        assert match, f"proxy_pass {url} is outside the model"
        return match.group(1), match.group(2)

    def route(self, path: str, headers: dict[str, str] | None = None, *, host: str | None = HOST) -> Route:
        """Route a request; ``host=None`` sends it without a Host header, as an HTTP/1.0 client may."""
        defaults = {"Host": host} if host is not None else {}
        request = Request(path, {name.lower(): value for name, value in {**defaults, **(headers or {})}.items()})
        location = self.select(path)
        status = self.rewrite(location, request)
        if status is not None:
            location = self.error_page(location, status)
            assert self.rewrite(location, request) is None

        upstream, uri = self.upstream(location)
        if uri is None:
            target = path
        else:
            assert location.prefix is not None, f"{location.label}: a URI in proxy_pass needs a path location"
            target = uri + path[len(location.prefix) :]

        set_headers = location.all("proxy_set_header") or [d for d in self.server if d.name == "proxy_set_header"]
        sent = {**request.headers, **_NGINX_DEFAULT_HEADERS}
        for directive in set_headers:
            field, value = directive.args
            sent[field.lower()] = value
        expanded = {field: self.expand(value, request, location) for field, value in sent.items()}
        versions = location.all("proxy_http_version")
        return Route(
            location=location,
            upstream=upstream,
            target=target,
            http_version=versions[-1].args[0] if versions else "1.0",
            headers={field: value for field, value in expanded.items() if value},
            body_limit=self.body_limit(),
        )


def _seconds(value: str) -> int:
    match = re.fullmatch(r"(\d+)(ms|s|m|h|d)?", value)
    assert match, value
    factor = {"ms": 0.001, "s": 1, "m": 60, "h": 3600, "d": 86400}[match.group(2) or "s"]
    return int(int(match.group(1)) * factor)


def _size(value: str) -> int:
    match = re.fullmatch(r"(\d+)([kKmMgG])?", value)
    assert match, f"size {value} is outside the model"
    factor = {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3}[(match.group(2) or "").lower()]
    return int(match.group(1)) * factor


@pytest.fixture(scope="module")
def nginx() -> NginxModel:
    return NginxModel(NGINX_CONF.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

DASHBOARD_ROUTES: list[tuple[str, dict[str, str]]] = [
    ("/", {}),
    ("/setup", {}),
    ("/login", {}),
    ("/forgot-password", {}),
    ("/control-plane", SESSION_COOKIE),
    ("/control-plane/setup", {}),
    ("/control-plane/agents/agent-1", SESSION_COOKIE),
    ("/oauth/callback", {}),
    ("/api/health", {}),
    # Browser API calls carry the session cookie, which only the dashboard turns into a token.
    ("/api/control-plane/onboarding/status", {}),
    ("/api/control-plane/auth/status", {}),
    ("/api/control-plane/auth/login", {}),
    ("/api/control-plane/auth/register-owner", {}),
    ("/api/control-plane/auth/password/recover", {}),
    ("/api/control-plane/auth/logout", SESSION_COOKIE),
    ("/api/control-plane/agents", SESSION_COOKIE),
    # A proxy that adds HTTP Basic auth in front must not divert browsers to the API.
    ("/api/control-plane/agents", {**SESSION_COOKIE, "Authorization": "Basic b3BlcmF0b3I6cGFzcw=="}),
    ("/api/runtime/agents/overview", SESSION_COOKIE),
    ("/api/runtime/agents/agent-1/sessions/session-1/stream", SESSION_COOKIE),
    ("/api/runtime/artifacts/artifact-1/download", SESSION_COOKIE),
    # The /api/runtime/* routes exist only in the dashboard, whatever the caller sends.
    ("/api/runtime/agents", BEARER),
    ("/api/runtime/relay/relay-1", {}),
]

API_ROUTES: list[tuple[str, dict[str, str]]] = [
    ("/api/control-plane/agents", BEARER),
    ("/api/control-plane/auth/tokens", {"authorization": "bearer koda-api-token"}),
    ("/api/control-plane/agents/agent-1/publish", {**BEARER, **SESSION_COOKIE}),
    ("/openapi/control-plane.json", {}),
]


def _route_id(route: tuple[str, dict[str, str]]) -> str:
    path, headers = route
    return f"{path} [{','.join(sorted(headers)) or 'no headers'}]"


@pytest.mark.parametrize("route", DASHBOARD_ROUTES, ids=[_route_id(route) for route in DASHBOARD_ROUTES])
def test_browser_paths_reach_the_dashboard(nginx: NginxModel, route: tuple[str, dict[str, str]]) -> None:
    path, headers = route
    routed = nginx.route(path, headers)

    assert routed.upstream == DASHBOARD, routed.location.label
    assert routed.target == path


@pytest.mark.parametrize("route", API_ROUTES, ids=[_route_id(route) for route in API_ROUTES])
def test_api_token_calls_and_the_openapi_document_reach_the_api(
    nginx: NginxModel, route: tuple[str, dict[str, str]]
) -> None:
    path, headers = route
    routed = nginx.route(path, headers)

    assert routed.upstream == API, routed.location.label
    assert routed.target == path
    if "authorization" in {name.lower() for name in headers}:
        assert routed.headers["authorization"].lower().startswith("bearer ")


def test_only_bearer_requests_and_the_openapi_document_can_reach_the_api(nginx: NginxModel) -> None:
    to_api = {location.label for location in nginx.locations() if nginx.upstream(location)[0] == API}
    assert to_api == {"= /openapi/control-plane.json", "@koda_control_plane_api"}

    # The named location is entered only from /api/control-plane/, when the request carries a
    # bearer token; every other location proxies to the dashboard.
    entered_from = [
        location.label
        for location in nginx.locations()
        for directive in location.all("error_page")
        if directive.args[-1] == "@koda_control_plane_api"
    ]
    assert entered_from == ["/api/control-plane/"]
    assert nginx.route("/api/control-plane/agents", {}).upstream == DASHBOARD
    assert nginx.route("/api/control-plane/agents", BEARER).upstream == API
    for location in nginx.locations():
        if location.label not in to_api:
            assert nginx.upstream(location)[0] == DASHBOARD, location.label


def test_runtime_relay_websocket_upgrade_reaches_the_dashboard(nginx: NginxModel) -> None:
    routed = nginx.route(
        "/api/runtime/relay/relay-1",
        {"Upgrade": "websocket", "Connection": "Upgrade", "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ=="},
    )

    assert routed.upstream == DASHBOARD
    assert routed.target == "/api/runtime/relay/relay-1"
    assert routed.http_version == "1.1"
    assert routed.headers["upgrade"] == "websocket"
    assert routed.headers["connection"] == "upgrade"
    assert routed.headers["sec-websocket-key"] == "dGhlIHNhbXBsZSBub25jZQ=="
    # The relay sends no pings; an idle terminal must not be cut after nginx's default 60 s.
    assert _seconds(routed.location.one("proxy_read_timeout").args[0]) >= 3600
    assert _seconds(routed.location.one("proxy_send_timeout").args[0]) >= 3600


def test_plain_requests_are_not_turned_into_upgrades(nginx: NginxModel) -> None:
    routed = nginx.route("/api/runtime/relay/relay-1", {})

    assert routed.upstream == DASHBOARD
    assert "upgrade" not in routed.headers
    assert routed.headers["connection"] == "close"


ALL_ROUTES = [*DASHBOARD_ROUTES, *API_ROUTES]


@pytest.mark.parametrize("route", ALL_ROUTES, ids=[_route_id(route) for route in ALL_ROUTES])
def test_every_route_appends_the_peer_to_x_forwarded_for(nginx: NginxModel, route: tuple[str, dict[str, str]]) -> None:
    path, headers = route

    direct = nginx.route(path, headers)
    spoofed = nginx.route(path, {**headers, "X-Forwarded-For": SPOOFED})

    assert direct.headers["x-forwarded-for"] == CLIENT
    assert spoofed.headers["x-forwarded-for"] == f"{SPOOFED}, {CLIENT}"
    assert direct.http_version == "1.1"
    # The dashboard checks a mutation's Origin against these two (apps/web/src/lib/request-origin.ts).
    assert direct.headers["host"] == HOST
    assert direct.headers["x-forwarded-proto"] == nginx.scheme


@pytest.mark.parametrize("route", ALL_ROUTES, ids=[_route_id(route) for route in ALL_ROUTES])
def test_every_route_passes_the_host_the_browser_sent_with_its_port(
    nginx: NginxModel, route: tuple[str, dict[str, str]]
) -> None:
    """The dashboard accepts a sign-in only when its Origin is X-Forwarded-Proto://Host.

    Browsers put a non-default port in both Origin and Host; nginx's $host drops it, so behind a
    proxy on such a port (https://koda.example.com:8443) every sign-in would be refused as
    cross-site.
    """
    path, headers = route
    browser_host = f"{HOST}:8443"

    routed = nginx.route(path, {**headers, "Host": browser_host})

    assert routed.headers["host"] == browser_host
    assert f"{routed.headers['x-forwarded-proto']}://{routed.headers['host']}" == f"{nginx.scheme}://{browser_host}"


@pytest.mark.parametrize("route", ALL_ROUTES, ids=[_route_id(route) for route in ALL_ROUTES])
def test_every_route_sends_a_host_when_the_client_sent_none(
    nginx: NginxModel, route: tuple[str, dict[str, str]]
) -> None:
    """An HTTP/1.0 request may carry no Host; HAProxy's default `option httpchk` health check is one.

    nginx proxies it as HTTP/1.1, and the dashboard's Node server (http.createServer in
    apps/web/src/lib/dashboard-server.mjs, `requireHostHeader` left on) answers an HTTP/1.1 request
    without Host with 400. `$http_host` is empty then and nginx leaves the header out, so the
    template must fall back to the server name.
    """
    path, headers = route

    routed = nginx.route(path, headers, host=None)

    assert routed.http_version == "1.1"
    assert routed.headers.get("host") == nginx.server_name
    assert routed.headers["x-forwarded-for"] == CLIENT


# The uploads the app accepts, from the dashboard (session cookie) and from API-token clients.
UPLOAD_ROUTES: list[tuple[str, dict[str, str]]] = [
    ("/api/control-plane/auth/profile/photo", SESSION_COOKIE),
    ("/api/control-plane/auth/profile/photo", BEARER),
    ("/api/control-plane/dashboard/squads/threads/thread-1/photo", SESSION_COOKIE),
    ("/api/control-plane/dashboard/squads/threads/thread-1/photo", BEARER),
    ("/api/control-plane/providers/supertonic/voices/import", SESSION_COOKIE),
    ("/api/control-plane/providers/supertonic/voices/import", BEARER),
]
# Room for what a multipart form adds around the file: boundaries, part headers, other fields.
MULTIPART_FRAMING_BYTES = 64 * 1024


def largest_upload_bytes() -> int:
    """The largest file any upload route accepts (the handlers read multipart bodies unbounded)."""
    from koda.control_plane import operator_profile_photos
    from koda.services import supertonic_manager
    from koda.squads import room_photos

    return max(
        operator_profile_photos.MAX_INPUT_BYTES,
        room_photos.MAX_INPUT_BYTES,
        supertonic_manager._MAX_CUSTOM_VOICE_BYTES,
    )


@pytest.mark.parametrize(
    "route", [*ALL_ROUTES, *UPLOAD_ROUTES], ids=[_route_id(r) for r in [*ALL_ROUTES, *UPLOAD_ROUTES]]
)
def test_every_route_accepts_the_largest_upload_the_app_accepts(
    nginx: NginxModel, route: tuple[str, dict[str, str]]
) -> None:
    """nginx answers 413 to a body over client_max_body_size before any upstream sees it.

    Its default is 1m, but a profile or room photo may be 12 MiB (``MAX_INPUT_BYTES`` in
    koda/control_plane/operator_profile_photos.py and koda/squads/room_photos.py), sent as
    multipart/form-data. The limit leaves room for the multipart framing around such a file and
    stays within 1 MiB above it, so it follows the app's own limit.
    """
    path, headers = route
    largest = largest_upload_bytes()

    routed = nginx.route(path, headers)

    assert routed.body_limit >= largest + MULTIPART_FRAMING_BYTES
    assert routed.body_limit <= largest + 1024 * 1024


def test_upload_routes_reach_the_upstream_that_serves_them(nginx: NginxModel) -> None:
    for path, headers in UPLOAD_ROUTES:
        expected = API if "authorization" in {name.lower() for name in headers} else DASHBOARD
        assert nginx.route(path, headers).upstream == expected, (path, headers)


@pytest.mark.parametrize(
    "path",
    [
        "/api/runtime/agents/agent-1/stream",
        "/api/runtime/agents/agent-1/sessions/session-1/stream",
    ],
)
def test_runtime_event_streams_stay_open_while_idle(nginx: NginxModel, path: str) -> None:
    """The runtime event streams send no heartbeat; nginx's default 60 s read timeout would cut them."""
    routed = nginx.route(f"{path}?after_seq=0", {**SESSION_COOKIE, "Accept": "text/event-stream"})

    assert routed.upstream == DASHBOARD
    assert routed.target == f"{path}?after_seq=0"
    assert routed.http_version == "1.1"
    assert _seconds(routed.location.one("proxy_read_timeout").args[0]) >= 3600


def test_install_guide_and_template_tell_operators_to_name_their_domain() -> None:
    """`server_name _` matches no domain; a stock `default_server` site would answer instead."""
    guide = " ".join((ROOT / "docs" / "install" / "vps.md").read_text(encoding="utf-8").split())
    template = NGINX_CONF.read_text(encoding="utf-8")

    assert "set `server_name` to your domain" in guide
    assert "`sites-enabled/default` with `listen 80 default_server`" in guide
    assert "`server_name koda.example.com;`" in template
    assert "sites-enabled/default with `listen 80 default_server`" in template


def test_install_guide_sends_only_api_token_requests_straight_to_the_api() -> None:
    guide = " ".join((ROOT / "docs" / "install" / "vps.md").read_text(encoding="utf-8").split())

    assert "forwards `/api/control-plane/*` straight to" not in guide
    assert (
        "If that proxy also forwards API-token requests (`/api/control-plane/*` with `Authorization: Bearer`)"
        " straight to `app:8090`" in guide
    )


async def test_api_rate_limiter_charges_the_client_behind_the_proxy(nginx: NginxModel) -> None:
    """With the proxy's peer trusted (`web,gateway`), the API charges nginx's $remote_addr."""
    routed = nginx.route("/api/control-plane/auth/login", {**BEARER, "X-Forwarded-For": SPOOFED})
    assert routed.upstream == API

    # `gateway` resolves to the address Docker's port proxy connects to the app container from.
    gateway = "172.18.0.1"
    request = MagicMock()
    request.remote = gateway
    request.headers = CIMultiDict({"X-Forwarded-For": routed.headers["x-forwarded-for"]})
    with patch.object(rate_limit, "CONTROL_PLANE_TRUSTED_PROXIES", (gateway,)):
        assert await rate_limit._client_ip(request) == CLIENT
