"""Auth route matrix for the control-plane HTTP app.

Every route the supervisor serves gets three requests through the production middleware
stack (``ControlPlaneSupervisor.build_app``): one with no credentials, one with an unknown
bearer token and one with a valid operator session. A probe middleware added inside that
stack answers in place of the handler, so no handler runs and nothing is read or written.

Which routes are public is observed, never listed here. The observation is compared with
the records that must agree with it:

- the backend table of public routes and their methods, ``_PUBLIC_CONTROL_PLANE_API_ROUTES``;
- the operations ``docs/openapi/control-plane.json`` lets through without a token;
- the dashboard list in ``apps/web/src/lib/public-control-plane-paths.ts``, which the
  Next.js proxy and the BFF catch-all both read.

A new route that answers without credentials therefore fails here until the OpenAPI
document marks it public. HEAD routes have no OpenAPI operation of their own; each must
answer exactly like its GET twin. Outside /api/control-plane/ the middleware checks only
``/cluster/drain`` and ``/cluster/undrain``, and one line of OpenAPI would be enough, so the
routes there that answer without credentials are also pinned in ``ANONYMOUS_ROOT_ROUTES``.

The auth middleware skips the bearer check only when the router resolved the request to a
public route, with a method the table names for it. One request per route cannot show that
for every URL, so other spellings of each public path, and routes added under or beside
one, are sent byte for byte and must not reach a handler without a session.
``tests/test_control_plane_public_paths.py`` checks the same rule on a minimal app and
compares the backend and dashboard lists with each other.
"""

from __future__ import annotations

import asyncio
import json
import re
import urllib.parse
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any
from unittest.mock import patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from koda.control_plane import api as control_plane_api
from koda.control_plane import rate_limit
from koda.control_plane.operator_auth import OperatorAuthContext
from koda.control_plane.supervisor import ControlPlaneSupervisor

ROOT = Path(__file__).resolve().parents[1]
OPENAPI_PATH = ROOT / "docs" / "openapi" / "control-plane.json"
WEB_PUBLIC_PATHS_PATH = ROOT / "apps" / "web" / "src" / "lib" / "public-control-plane-paths.ts"
WEB_PROXY_PATH = ROOT / "apps" / "web" / "src" / "proxy.ts"
WEB_CATCH_ALL_PATH = ROOT / "apps" / "web" / "src" / "app" / "api" / "control-plane" / "[...path]" / "route.ts"

CONTROL_PLANE_PREFIX = "/api/control-plane/"
OPERATOR_TOKEN = "route-matrix-operator-token"
UNKNOWN_TOKEN = "route-matrix-unknown-token"
REACHED_HEADER = "X-Route-Matrix-Reached"
UNAUTHORIZED_BODY = {"error": "operator session is required"}
OPENAPI_METHODS = frozenset({"get", "put", "post", "delete", "patch"})
# Methods sent to each public path besides the ones it is public for.
VARIANT_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
# A protected route that the traversal variants below aim at.
PROTECTED_TARGET = "/api/control-plane/agents"

# Supervisor-internal deploy hooks (docs/operations/cluster-mode.md). The OpenAPI document
# leaves them out; every other registered route must be documented there.
SUPERVISOR_INTERNAL_ROUTES = frozenset(
    {
        ("GET", "/cluster/status"),
        ("POST", "/cluster/drain"),
        ("POST", "/cluster/undrain"),
    }
)

# The routes outside /api/control-plane/ that answer without a session, besides the HEAD twin
# aiohttp adds to each GET. The auth middleware checks only the root routes that change state
# (/cluster/drain and /cluster/undrain, D-033), so nothing in the code limits the others, and an
# OpenAPI entry alone does not make one acceptable: a new root route that answers without a
# session fails the matrix until it is listed here on purpose (and in
# docs/security/authentication.md).
ANONYMOUS_ROOT_ROUTES = frozenset(
    {
        ("GET", "/health"),
        ("GET", "/ready"),
        ("GET", "/openapi/control-plane.json"),
        ("GET", "/cluster/status"),
    }
)


@dataclass(frozen=True)
class RouteProbe:
    method: str
    path: str
    url: str
    anonymous_status: int
    anonymous_reached: str | None
    anonymous_body: Any
    unknown_token_status: int
    operator_status: int
    operator_reached: str | None

    @property
    def key(self) -> tuple[str, str]:
        return (self.method, self.path)

    @property
    def identity(self) -> str:
        return f"{self.method} {self.path}"

    @property
    def public(self) -> bool:
        return self.anonymous_reached is not None


@web.middleware
async def _answer_in_place_of_handler(request: web.Request, handler: Any) -> web.StreamResponse:
    """Innermost middleware: a request that gets here has passed every production one."""
    match_info = request.match_info
    if match_info.http_exception is not None:
        return await handler(request)  # the router's own 404 or 405
    route = match_info.route
    assert route.resource is not None
    return web.Response(status=204, headers={REACHED_HEADER: f"{route.method} {route.resource.canonical}"})


class _StubAuthService:
    """Knows one operator session token and nothing else."""

    def resolve_bearer_token(self, token: str) -> OperatorAuthContext | None:
        if token != OPERATOR_TOKEN:
            return None
        return OperatorAuthContext(
            auth_kind="session",
            subject_type="operator",
            user_id="route-matrix-user",
            username="route-matrix",
            email=None,
            display_name=None,
        )


def _build_supervisor_app() -> web.Application:
    with patch("koda.control_plane.supervisor.get_control_plane_manager", return_value=object()):
        supervisor = ControlPlaneSupervisor()
    app = supervisor.build_app()
    app.middlewares.append(_answer_in_place_of_handler)
    return app


def _sample_url(route: web.AbstractRoute) -> str:
    resource = route.resource
    assert resource is not None
    info = resource.get_info()
    if isinstance(resource, web.PlainResource):
        return str(info["path"])
    if isinstance(resource, web.DynamicResource):
        names = list(info["pattern"].groupindex)
        return str(resource.url_for(**{name: f"matrix-{name}" for name in names}))
    raise AssertionError(f"the route matrix cannot build a request for {resource!r}; extend _sample_url")


async def _send(client: TestClient, method: str, url: str, token: str | None) -> tuple[int, str | None, Any]:
    # Every request starts with fresh buckets: hundreds of 401s from one address would
    # otherwise trip the auth-failure limiter and turn into 429s.
    rate_limit.clear_limiters()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with client.request(method, url, headers=headers, allow_redirects=False) as response:
        body: Any = None
        if method != "HEAD" and response.content_type == "application/json":
            body = await response.json()
        return response.status, response.headers.get(REACHED_HEADER), body


async def _probe_routes(app: web.Application, routes: Iterable[web.AbstractRoute]) -> dict[tuple[str, str], RouteProbe]:
    probes: dict[tuple[str, str], RouteProbe] = {}
    targets = [(route.method, route.resource.canonical, _sample_url(route)) for route in routes if route.resource]
    with patch.object(control_plane_api, "_auth_service", _StubAuthService):
        async with TestClient(TestServer(app)) as client:
            for method, path, url in targets:
                anonymous_status, anonymous_reached, anonymous_body = await _send(client, method, url, None)
                unknown_token_status, _, _ = await _send(client, method, url, UNKNOWN_TOKEN)
                operator_status, operator_reached, _ = await _send(client, method, url, OPERATOR_TOKEN)
                probe = RouteProbe(
                    method=method,
                    path=path,
                    url=url,
                    anonymous_status=anonymous_status,
                    anonymous_reached=anonymous_reached,
                    anonymous_body=anonymous_body,
                    unknown_token_status=unknown_token_status,
                    operator_status=operator_status,
                    operator_reached=operator_reached,
                )
                assert probe.key not in probes, f"{probe.identity} is registered twice"
                probes[probe.key] = probe
    rate_limit.clear_limiters()
    return probes


async def _raw_request(
    server: TestServer, method: str, target: str, token: str | None = None
) -> tuple[int, str | None]:
    """Send ``target`` byte for byte; the aiohttp client would normalise dot segments.

    Returns the status and the route the probe middleware answered for, if any.
    """
    rate_limit.clear_limiters()
    authorization = f"Authorization: Bearer {token}\r\n" if token else ""
    request = f"{method} {target} HTTP/1.1\r\nHost: matrix\r\n{authorization}Connection: close\r\n\r\n"
    reader, writer = await asyncio.open_connection(server.host, server.port)
    try:
        writer.write(request.encode("ascii"))
        await writer.drain()
        raw = await reader.read()
    finally:
        writer.close()
        await writer.wait_closed()
    rate_limit.clear_limiters()
    head = raw.split(b"\r\n\r\n", 1)[0].decode("latin-1").split("\r\n")
    status = int(head[0].split(" ", 2)[1])
    headers = dict(line.split(": ", 1) for line in head[1:] if ": " in line)
    return status, headers.get(REACHED_HEADER)


@dataclass(frozen=True)
class RouteMatrix:
    registered_routes: int
    probes: dict[tuple[str, str], RouteProbe]

    def without_head(self) -> dict[tuple[str, str], RouteProbe]:
        return {key: probe for key, probe in self.probes.items() if probe.method != "HEAD"}

    def public_under_control_plane(self) -> set[tuple[str, str]]:
        return {
            key for key, probe in self.probes.items() if probe.public and probe.path.startswith(CONTROL_PLANE_PREFIX)
        }


def _with_head_twins(routes: Iterable[tuple[str, str]]) -> set[tuple[str, str]]:
    keys = set(routes)
    return keys | {("HEAD", path) for method, path in keys if method == "GET"}


def _anonymous_root_drift(probes: dict[tuple[str, str], RouteProbe]) -> list[str]:
    """Routes outside /api/control-plane/ whose anonymous answer differs from ``ANONYMOUS_ROOT_ROUTES``."""
    pinned = _with_head_twins(ANONYMOUS_ROOT_ROUTES)
    problems = []
    for key, probe in sorted(probes.items()):
        if probe.path.startswith(CONTROL_PLANE_PREFIX):
            continue
        if probe.public and key not in pinned:
            problems.append(f"{probe.identity}: answers without a session but is not in ANONYMOUS_ROOT_ROUTES")
        elif key in pinned and not probe.public:
            problems.append(f"{probe.identity}: needs a session now; drop it from ANONYMOUS_ROOT_ROUTES")
    return problems


@pytest.fixture(scope="module")
def route_matrix() -> RouteMatrix:
    async def run() -> RouteMatrix:
        app = _build_supervisor_app()
        routes = list(app.router.routes())
        return RouteMatrix(registered_routes=len(routes), probes=await _probe_routes(app, routes))

    return asyncio.run(run())


def _openapi_public_operations() -> dict[tuple[str, str], bool]:
    """``(METHOD, path) -> True`` when the operation's effective security allows anonymous calls."""
    spec = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    default_security = spec.get("security", [])
    operations: dict[tuple[str, str], bool] = {}
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            if method not in OPENAPI_METHODS:
                continue
            security = operation.get("security", default_security)
            operations[(method.upper(), path)] = not security or any(not requirement for requirement in security)
    return operations


def _openapi_drift(probes: dict[tuple[str, str], RouteProbe], openapi: dict[tuple[str, str], bool]) -> list[str]:
    problems = []
    for key, probe in sorted(probes.items()):
        if probe.method == "HEAD" or key in SUPERVISOR_INTERNAL_ROUTES:
            continue
        documented_public = openapi.get(key)
        if documented_public is None:
            problems.append(f"{probe.identity}: registered but missing from the OpenAPI document")
        elif probe.public and not documented_public:
            problems.append(f"{probe.identity}: answers without credentials but the OpenAPI requires bearerAuth")
        elif documented_public and not probe.public:
            problems.append(f"{probe.identity}: the OpenAPI marks it security: [] but it requires an operator session")
    return problems


def _head_drift(probes: dict[tuple[str, str], RouteProbe]) -> list[str]:
    """HEAD routes whose anonymous answer differs from the GET route aiohttp runs for them."""
    problems = []
    for _key, probe in sorted(probes.items()):
        if probe.method != "HEAD":
            continue
        twin = probes.get(("GET", probe.path))
        if twin is None:
            problems.append(f"{probe.identity}: no GET twin to take its security from; extend the matrix")
        elif probe.public and not twin.public:
            problems.append(
                f"{probe.identity}: answers without credentials, but GET {probe.path} requires an operator session"
            )
        elif twin.public and not probe.public:
            problems.append(
                f"{probe.identity}: requires an operator session, but GET {probe.path} answers without credentials"
            )
    return problems


def _ts_string_set(path: Path, const_name: str) -> set[str]:
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"const {const_name}\b[^=]*= new Set\(\[(.*?)\]\)", text, re.DOTALL)
    assert match, f"{const_name} not found in {path.relative_to(ROOT)}"
    entries = set(re.findall(r'"([^"]+)"', match.group(1)))
    assert entries, f"{const_name} in {path.relative_to(ROOT)} is empty"
    return entries


def _backend_public_routes() -> dict[str, frozenset[str]]:
    return dict(control_plane_api._PUBLIC_CONTROL_PLANE_API_ROUTES)


def _backend_public_operations() -> set[tuple[str, str]]:
    return {(method, path) for path, methods in _backend_public_routes().items() for method in methods}


def _backend_allowlist() -> set[str]:
    return set(control_plane_api._PUBLIC_CONTROL_PLANE_API_PATHS)


def test_every_registered_route_is_probed_through_the_supervisor_stack(route_matrix: RouteMatrix) -> None:
    probes = route_matrix.probes
    assert len(probes) == route_matrix.registered_routes
    # The supervisor adds its own routes next to the API ones; both must be in the matrix.
    assert ("GET", "/health") in probes
    assert ("GET", PROTECTED_TARGET) in probes

    problems = []
    for probe in probes.values():
        if probe.operator_reached != probe.identity:
            problems.append(
                f"{probe.identity} ({probe.url}): an operator session got {probe.operator_status}, "
                f"reached {probe.operator_reached!r}"
            )
        elif probe.public:
            if probe.anonymous_reached != probe.identity:
                problems.append(f"{probe.identity}: an anonymous request reached {probe.anonymous_reached!r}")
        elif probe.anonymous_status != 401 or probe.unknown_token_status != 401:
            problems.append(
                f"{probe.identity}: expected 401 without a valid session, got {probe.anonymous_status} "
                f"(no token) and {probe.unknown_token_status} (unknown token)"
            )
        elif probe.method != "HEAD" and probe.anonymous_body != UNAUTHORIZED_BODY:
            problems.append(f"{probe.identity}: 401 body {probe.anonymous_body!r}")
    assert problems == [], "\n".join(problems)


def test_routes_answering_without_credentials_match_openapi_security_none(route_matrix: RouteMatrix) -> None:
    problems = _openapi_drift(route_matrix.probes, _openapi_public_operations())
    assert problems == [], "\n".join(problems)


def test_head_routes_answer_like_their_get_twin(route_matrix: RouteMatrix) -> None:
    assert any(probe.method == "HEAD" for probe in route_matrix.probes.values())
    problems = _head_drift(route_matrix.probes)
    assert problems == [], "\n".join(problems)


def test_root_routes_answering_without_credentials_are_the_pinned_set(route_matrix: RouteMatrix) -> None:
    """Outside /api/control-plane/ the middleware checks nothing, so the set is pinned here."""
    missing = sorted(_with_head_twins(ANONYMOUS_ROOT_ROUTES) - set(route_matrix.probes))
    assert missing == [], f"in ANONYMOUS_ROOT_ROUTES but not registered: {missing}"
    problems = _anonymous_root_drift(route_matrix.probes)
    assert problems == [], "\n".join(problems)


# M4-E1-T8: the 410 stub for the old combined onboarding call and the HTML page that pointed
# operators to the dashboard's /setup (with the / redirect to it) are gone.
REMOVED_ROUTES = frozenset(
    {
        ("POST", "/api/control-plane/onboarding/bootstrap"),
        ("GET", "/setup"),
        ("GET", "/"),
    }
)


def test_removed_routes_are_not_registered_or_documented(route_matrix: RouteMatrix) -> None:
    registered = sorted(_with_head_twins(REMOVED_ROUTES) & set(route_matrix.probes))
    assert registered == []
    spec = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    documented = sorted(path for _method, path in REMOVED_ROUTES if path in spec["paths"])
    assert documented == []


def test_supervisor_internal_routes_are_registered_and_left_out_of_openapi(route_matrix: RouteMatrix) -> None:
    openapi = _openapi_public_operations()
    for key in SUPERVISOR_INTERNAL_ROUTES:
        assert key in route_matrix.probes, f"{key} is no longer registered; drop it from SUPERVISOR_INTERNAL_ROUTES"
        assert key not in openapi, f"{key} is documented now; drop it from SUPERVISOR_INTERNAL_ROUTES"


def test_backend_allowlist_equals_openapi_security_none_set() -> None:
    """The OpenAPI lets exactly the table's methods through without a token, path by path."""
    documented_public = {
        key
        for key, public in _openapi_public_operations().items()
        if public and key[1].startswith(CONTROL_PLANE_PREFIX)
    }
    assert {key for key in _backend_public_operations() if key[0] != "HEAD"} == documented_public


def test_backend_public_routes_are_exactly_the_routes_answering_without_credentials(
    route_matrix: RouteMatrix,
) -> None:
    observed = route_matrix.public_under_control_plane()
    backend = _backend_public_operations()
    assert backend - observed == set(), "public table entries that no registered route answers anonymously"
    assert observed - backend == set(), "control-plane routes that answer anonymously but are not in the public table"


def test_dashboard_public_list_equals_the_paths_answering_without_credentials(route_matrix: RouteMatrix) -> None:
    observed = {path for _method, path in route_matrix.public_under_control_plane()}
    assert _ts_string_set(WEB_PUBLIC_PATHS_PATH, "PUBLIC_CONTROL_PLANE_API_PATHS") == observed
    # The proxy and the BFF catch-all gate on that list, not on a copy of their own.
    shared_import = re.compile(
        r'import \{[^}]*\bisPublicControlPlaneApiPath\b[^}]*\} from "@/lib/public-control-plane-paths";'
    )
    for gate in (WEB_PROXY_PATH, WEB_CATCH_ALL_PATH):
        text = gate.read_text(encoding="utf-8")
        assert shared_import.search(text), f"{gate.relative_to(ROOT)} does not import the shared list"
        assert "isPublicControlPlaneApiPath(" in text, f"{gate.relative_to(ROOT)} does not gate on the shared list"


def test_cluster_drain_endpoints_require_an_operator_session(route_matrix: RouteMatrix) -> None:
    """D-033: drain and undrain change state, so they take an operator credential like the API."""
    cluster = {key: probe for key, probe in route_matrix.probes.items() if probe.path.startswith("/cluster/")}
    assert set(cluster) == _with_head_twins(SUPERVISOR_INTERNAL_ROUTES)
    for key in (("POST", "/cluster/drain"), ("POST", "/cluster/undrain")):
        probe = cluster[key]
        assert not probe.public
        assert (probe.anonymous_status, probe.unknown_token_status) == (401, 401)
        assert probe.anonymous_body == UNAUTHORIZED_BODY
        assert probe.operator_reached == probe.identity
    assert cluster[("GET", "/cluster/status")].public


async def _unreachable_handler(_request: web.Request) -> web.Response:
    raise AssertionError("the probe answers before any handler runs")


async def test_matrix_flags_new_routes_that_answer_without_credentials() -> None:
    """Adding an unauthenticated route must fail the matrix, even when it is documented."""
    app = _build_supervisor_app()
    made_public = f"{CONTROL_PLANE_PREFIX}matrix-public"
    new_routes = [
        app.router.add_get("/debug/state", _unreachable_handler),
        app.router.add_get(made_public, _unreachable_handler),
        app.router.add_get(f"{CONTROL_PLANE_PREFIX}matrix-new", _unreachable_handler),
    ]
    public_routes = MappingProxyType({**_backend_public_routes(), made_public: frozenset({"GET"})})
    with patch.object(control_plane_api, "_PUBLIC_CONTROL_PLANE_API_ROUTES", public_routes):
        probes = await _probe_routes(app, new_routes)

    # The author documents all three in the OpenAPI as ordinary, bearer-protected routes.
    assert _openapi_drift(probes, {key: False for key in probes}) == [
        f"GET {made_public}: answers without credentials but the OpenAPI requires bearerAuth",
        "GET /debug/state: answers without credentials but the OpenAPI requires bearerAuth",
    ]
    # Left undocumented, all three fail.
    assert len(_openapi_drift(probes, {})) == 3


async def test_matrix_flags_new_root_routes_even_when_the_openapi_marks_them_public() -> None:
    """A root route needs only one line of OpenAPI to pass the OpenAPI check; the pin still fails it."""
    app = _build_supervisor_app()
    app.router.add_get("/debug/state", _unreachable_handler)
    new_routes = [
        route for route in app.router.routes() if route.resource and route.resource.canonical == "/debug/state"
    ]
    probes = await _probe_routes(app, new_routes)

    assert {key: probe.public for key, probe in probes.items()} == {
        ("GET", "/debug/state"): True,
        ("HEAD", "/debug/state"): True,
    }
    # The author documents it as `security: []`: the OpenAPI comparison is satisfied.
    assert _openapi_drift(probes, {("GET", "/debug/state"): True}) == []
    assert _anonymous_root_drift(probes) == [
        "GET /debug/state: answers without a session but is not in ANONYMOUS_ROOT_ROUTES",
        "HEAD /debug/state: answers without a session but is not in ANONYMOUS_ROOT_ROUTES",
    ]


async def test_routes_added_under_or_beside_a_public_path_need_a_session() -> None:
    """A route cannot take over a public path, whatever URL the router resolves to it.

    Each URL below is, or decodes to, a public path or a path under one, and the router
    resolves it to a new route that the public table does not name. Matching the decoded path by prefix would let
    every one of them through without credentials while the route's one sample request got 401.
    """
    public = sorted(_backend_allowlist())[0]
    parent, _, last = public.rpartition("/")
    encoded_tail = urllib.parse.quote(public.removeprefix(CONTROL_PLANE_PREFIX), safe="")
    other_method = next(method for method in VARIANT_METHODS if method not in _backend_public_routes()[public])

    app = _build_supervisor_app()
    router = app.router
    # (new route, a URL the router resolves to it)
    added = [
        (router.add_get(f"{public}/details", _unreachable_handler), f"{public}/details"),
        (router.add_route(other_method, public, _unreachable_handler), public),
        (router.add_get(f"{parent}/{{provider}}/start", _unreachable_handler), f"{parent}/{last}/start"),
        # %2F stays inside one segment when the router matches, and decodes to "/" in the path.
        (
            router.add_get(f"{CONTROL_PLANE_PREFIX}{{section}}", _unreachable_handler),
            f"{CONTROL_PLANE_PREFIX}{encoded_tail}",
        ),
        (
            router.add_get(f"{CONTROL_PLANE_PREFIX}{{section}}/items", _unreachable_handler),
            f"{CONTROL_PLANE_PREFIX}{encoded_tail}/items",
        ),
        (router.add_get(f"{public}{{suffix}}", _unreachable_handler), f"{public}%2Fdetails"),
    ]
    # A sub-application's routes go through the same middleware stack, and the matrix lists them.
    sub_app = web.Application()
    added.append((sub_app.router.add_get("/{provider}/settings", _unreachable_handler), f"{parent}/{last}/settings"))
    app.add_subapp(parent, sub_app)
    new_routes = [route for route, _url in added]
    assert set(new_routes) <= set(app.router.routes())
    identities = [f"{route.method} {route.resource.canonical}" for route in new_routes if route.resource is not None]
    assert len(identities) == len(added)

    probes = {probe.identity: probe for probe in (await _probe_routes(app, new_routes)).values()}
    observed = []
    with patch.object(control_plane_api, "_auth_service", _StubAuthService):
        async with TestServer(app) as server:
            for (route, url), identity in zip(added, identities, strict=True):
                observed.append(
                    (
                        identity,
                        (probes[identity].anonymous_status, probes[identity].operator_reached),
                        url,
                        await _raw_request(server, route.method, url, OPERATOR_TOKEN),
                        await _raw_request(server, route.method, url),
                    )
                )
    # The sample request needs a session. So does the URL: an operator session shows that it
    # resolves to the new route, and without one it gets 401.
    assert observed == [
        (identity, (401, identity), url, (204, identity), (401, None))
        for (_route, url), identity in zip(added, identities, strict=True)
    ]


async def test_matrix_flags_head_requests_that_skip_the_auth_check() -> None:
    """aiohttp runs the GET handler for HEAD, so a HEAD request must be refused when GET is."""

    @web.middleware
    async def auth_skipping_head(request: web.Request, handler: Any) -> web.StreamResponse:
        if request.method == "HEAD":
            return await handler(request)
        return await control_plane_api.control_plane_auth_middleware(request, handler)

    with patch("koda.control_plane.supervisor.control_plane_auth_middleware", auth_skipping_head):
        app = _build_supervisor_app()
    routes = [
        route
        for route in app.router.routes()
        if route.resource is not None and route.resource.canonical == PROTECTED_TARGET
    ]
    probes = await _probe_routes(app, routes)

    assert {probe.method for probe in probes.values()} >= {"GET", "HEAD"}
    # The OpenAPI comparison leaves HEAD out, so only the twin check sees the bypass.
    assert _openapi_drift(probes, {key: False for key in probes}) == []
    assert _head_drift(probes) == [
        f"HEAD {PROTECTED_TARGET}: answers without credentials, but GET {PROTECTED_TARGET} requires an operator session"
    ]


def _variant_cases() -> list[tuple[str, str, int]]:
    """``(method, request target, expected status)``; none of them may reach a handler anonymously."""
    target_tail = PROTECTED_TARGET.removeprefix(CONTROL_PLANE_PREFIX)
    cases: list[tuple[str, str, int]] = []
    for public, methods in sorted(_backend_public_routes().items()):
        parent, _, last = public.rpartition("/")
        ups = "/".join([".."] * len(public.removeprefix(CONTROL_PLANE_PREFIX).split("/")))
        cases += [
            # Public paths match exactly: a sub-path or a trailing slash resolves to no public route.
            ("GET", f"{public}/x", 401),
            ("GET", f"{public}/", 401),
            # A longer or differently cased name is not the entry.
            ("GET", f"{public}x", 401),
            ("GET", f"{public};x", 401),
            ("GET", f"{parent}/{last.upper()}", 401),
            # Outside the case-sensitive /api/control-plane/ prefix, where nothing is registered.
            ("GET", public.upper(), 404),
            # Dot segments from the public entry to a protected route, plain and encoded.
            # The server does not resolve them, so they match no route.
            ("GET", f"{public}/{ups}/{target_tail}", 401),
            ("GET", f"{public}/{ups.replace('..', '%2e%2e')}/{target_tail}", 401),
            ("GET", f"{public}%2F{ups.replace('/', '%2F')}%2F{target_tail}", 401),
        ]
        # The public path with a method it is not public for.
        cases += [(method, public, 401) for method in VARIANT_METHODS if method not in methods]
    cases += [
        # Other spellings of the protected route itself.
        ("GET", f"/{PROTECTED_TARGET}", 404),
        ("GET", PROTECTED_TARGET.replace("/api/", "/api//", 1), 404),
        ("GET", PROTECTED_TARGET.replace("/control-plane/", "/control-plane//", 1), 401),
        ("GET", f"{PROTECTED_TARGET}/", 401),
        ("GET", PROTECTED_TARGET.replace("control-plane", "control%2Dplane", 1), 401),
        ("GET", PROTECTED_TARGET.replace("/api/", "/api%2F", 1), 401),
        ("GET", f"/x/..{PROTECTED_TARGET}", 404),
        ("GET", f"/health/..{PROTECTED_TARGET}", 404),
        ("GET", f"{PROTECTED_TARGET}?next={sorted(_backend_allowlist())[0]}", 401),
        ("GET", CONTROL_PLANE_PREFIX.rstrip("/"), 404),
    ]
    return cases


async def test_path_variants_never_reach_a_handler_without_credentials() -> None:
    cases = _variant_cases()
    app = _build_supervisor_app()
    observed = []
    async with TestServer(app) as server:
        for method, target in [("GET", PROTECTED_TARGET), *((method, target) for method, target, _ in cases)]:
            observed.append((method, target, *await _raw_request(server, method, target)))

    assert observed[0] == ("GET", PROTECTED_TARGET, 401, None), "PROTECTED_TARGET must be a protected route"
    assert observed[1:] == [(method, target, expected, None) for method, target, expected in cases]
